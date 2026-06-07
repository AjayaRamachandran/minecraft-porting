"""Level 3: SchematicConverter — walks a .schem file and rewrites embedded data.

These schematics are stored in Sponge v3 format and are themselves valid
1.21.11 — what's *inside* them (command-block payloads, container item NBTs,
spawner entities) is the legacy pre-1.20.5 stuff that needs translating.

Targets three categories of block entity:

1. **Containers** (chest, barrel, dispenser, dropper, hopper, shulker_box,
   trapped_chest, brewing_stand, furnace family). Their ``Items`` list is run
   through Level 1 item-by-item.
2. **Spawners** (mob spawners and trial spawners). Both ``SpawnData.entity``
   and each ``SpawnPotentials[].data.entity`` go through Level 2 so any items
   they hold and their ``CustomName`` are updated.
3. **Command blocks** (command_block, chain_command_block, repeating_command_block,
   plus jigsaw). The ``Command`` field is run through the line dispatcher used
   for ``.mcfunction`` files, so embedded ``/give``, ``/summon``, etc. get the
   same treatment as standalone command lines.

Schematic I/O uses :mod:`nbtlib` directly (the ``mcschematic`` package's
high-level wrapper doesn't yet parse Sponge v3). nbtlib is a transitive
dependency of mcschematic, so installing one gets you both.

The per-block rewrite is exposed as :meth:`convert_block_entity_nbt` (operates
on raw SNBT-style trees) so it can be unit-tested without a real ``.schem``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .entity_converter import EntityConverter
from .item_converter import ItemConverter
from .snbt import Str, snbt_dump, snbt_parse


# Block IDs whose block-entity NBT carries an Items list to be re-converted.
CONTAINER_BLOCK_IDS = frozenset({
    "minecraft:chest", "minecraft:trapped_chest", "minecraft:barrel",
    "minecraft:dispenser", "minecraft:dropper", "minecraft:hopper",
    "minecraft:shulker_box", "minecraft:brewing_stand",
    "minecraft:furnace", "minecraft:blast_furnace", "minecraft:smoker",
    "minecraft:campfire", "minecraft:soul_campfire",
    "minecraft:chiseled_bookshelf", "minecraft:decorated_pot",
    "minecraft:crafter",
})

SPAWNER_BLOCK_IDS = frozenset({
    # Block-entity ids — the *block* is "minecraft:spawner" but the *block
    # entity* identifier in NBT is "minecraft:mob_spawner".
    "minecraft:spawner", "minecraft:mob_spawner", "minecraft:trial_spawner",
})

COMMAND_BLOCK_IDS = frozenset({
    "minecraft:command_block", "minecraft:chain_command_block",
    "minecraft:repeating_command_block", "minecraft:jigsaw",
})


class SchematicConverter:
    """Rewrites containers, spawners, and command-blocks inside a .schem file.

    Parameters
    ----------
    item_converter:
        Level 1 — used for items inside containers.
    entity_converter:
        Level 2 — used for entities inside spawners (and as items' fallback
        path for ``CustomName``).
    line_dispatcher:
        Callable ``(line: str) -> str`` that converts a single command line
        the same way the CLI does. Lets command-block contents reuse the give
        / villager / summon implementors.
    warnings:
        Mutable list for diagnostics.
    """

    def __init__(
        self,
        item_converter: ItemConverter,
        entity_converter: EntityConverter,
        line_dispatcher: Callable[[str], str],
        warnings: list[str],
    ):
        self.item = item_converter
        self.entity = entity_converter
        self.dispatch_line = line_dispatcher
        self.warnings = warnings

    # ----- public entry points ------------------------------------------

    def convert_schematic_file(self, in_path, out_path) -> None:
        """Load a ``.schem``, rewrite legacy embedded data in every supported
        block entity, save the result.

        Uses :mod:`nbtlib` to load/save the NBT directly. Block-entity NBT
        round-trips through SNBT when calling Level 1 / Level 2 so the same
        in-memory tree types (``Num``, ``Str``, ``dict``, …) work everywhere.
        """
        try:
            import nbtlib  # type: ignore
        except ImportError as ex:
            raise RuntimeError(
                "Schematic conversion requires nbtlib. Install with: "
                "pip install mcschematic (which pulls in nbtlib)"
            ) from ex

        schem = nbtlib.load(str(in_path))
        # Sponge v3 wraps everything under "Schematic"; older versions inline
        # the same fields at the top level.
        root = schem["Schematic"] if "Schematic" in schem else schem
        blocks = root.get("Blocks") if hasattr(root, "get") else None
        be_list = (blocks.get("BlockEntities")
                   if blocks is not None and hasattr(blocks, "get")
                   else root.get("BlockEntities") if hasattr(root, "get") else None)
        if be_list is None:
            self.warnings.append(f"[{in_path}] no BlockEntities — nothing to convert")
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            schem.save(str(out_path), gzipped=True)
            return

        changed = 0
        for i, be in enumerate(be_list):
            bid = str(be.get("Id") or be.get("id") or "")
            # v3 stores per-block NBT under a nested "Data" compound; older
            # versions inline those fields directly on the BlockEntity.
            data = be["Data"] if "Data" in be else be
            ctx = f"{Path(in_path).name}#BE[{i}]:{bid}"
            if self._rewrite_block_entity(bid, data, ctx, nbtlib):
                changed += 1

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        schem.save(str(out_path), gzipped=True)
        self.warnings.append(f"[{in_path}] rewrote {changed}/{len(be_list)} block entities")

    # ----- per-BE rewrite (operates on nbtlib trees) --------------------

    def _rewrite_block_entity(self, bid: str, data, ctx: str, nbtlib) -> bool:
        """Modernize one block entity's NBT in place. Returns True if anything changed."""
        if bid in COMMAND_BLOCK_IDS:
            return self._rewrite_command_block(data, ctx, nbtlib)
        if bid in CONTAINER_BLOCK_IDS:
            return self._rewrite_container(data, ctx, nbtlib)
        if bid in SPAWNER_BLOCK_IDS:
            return self._rewrite_spawner(data, ctx, nbtlib)
        return False

    def _rewrite_command_block(self, data, ctx: str, nbtlib) -> bool:
        cmd = data.get("Command") if hasattr(data, "get") else None
        if cmd is None:
            return False
        original = str(cmd)
        new_text = self.dispatch_line(original)
        if new_text == original:
            return False
        data["Command"] = nbtlib.String(new_text)
        return True

    def _rewrite_container(self, data, ctx: str, nbtlib) -> bool:
        items = data.get("Items") if hasattr(data, "get") else None
        if not isinstance(items, list) or not items:
            return False
        new_items = []
        any_change = False
        for j, item_tag in enumerate(items):
            converted, did = self._round_trip_item(item_tag, f"{ctx}.Items[{j}]", nbtlib)
            new_items.append(converted)
            any_change = any_change or did
        if not any_change:
            return False
        # Replace contents while preserving the list's tag-type information.
        items.clear()
        items.extend(new_items)
        return True

    def _rewrite_spawner(self, data, ctx: str, nbtlib) -> bool:
        any_change = False
        spawn_data = data.get("SpawnData") if hasattr(data, "get") else None
        if isinstance(spawn_data, dict) and "entity" in spawn_data:
            new_entity, did = self._round_trip_entity(
                spawn_data["entity"], f"{ctx}.SpawnData.entity", nbtlib
            )
            if did:
                spawn_data["entity"] = new_entity
                any_change = True
        pots = data.get("SpawnPotentials") if hasattr(data, "get") else None
        if isinstance(pots, list):
            for k, pot in enumerate(pots):
                if not hasattr(pot, "get"):
                    continue
                pd = pot.get("data")
                if isinstance(pd, dict) and "entity" in pd:
                    new_entity, did = self._round_trip_entity(
                        pd["entity"], f"{ctx}.SpawnPotentials[{k}].data.entity", nbtlib
                    )
                    if did:
                        pd["entity"] = new_entity
                        any_change = True
        return any_change

    # ----- nbtlib <-> Level1/Level2 bridging ----------------------------

    def _round_trip_item(self, item_tag, ctx: str, nbtlib):
        """Run a single item-stack NBT through Level 1. Returns (new_tag, changed).

        Level 1 handles every shape (legacy, half-migrated, modern); we just
        round-trip via SNBT and report whether anything actually changed so the
        ``rewrote N/M`` count stays accurate.
        """
        if not hasattr(item_tag, "snbt"):
            return item_tag, False
        try:
            parsed = snbt_parse(item_tag.snbt())
        except ValueError as ex:
            self.warnings.append(f"[{ctx}] item NBT parse failed: {ex}")
            return item_tag, False
        if not isinstance(parsed, dict):
            return item_tag, False
        new_node = self.item.convert_item_nbt(parsed, ctx)
        new_snbt = snbt_dump(new_node)
        if new_snbt == item_tag.snbt():
            return item_tag, False
        return nbtlib.parse_nbt(new_snbt), True

    def _round_trip_entity(self, entity_tag, ctx: str, nbtlib):
        """Run a single entity NBT through Level 2. Returns (new_tag, changed)."""
        if not hasattr(entity_tag, "snbt"):
            return entity_tag, False
        try:
            parsed = snbt_parse(entity_tag.snbt())
        except ValueError as ex:
            self.warnings.append(f"[{ctx}] entity NBT parse failed: {ex}")
            return entity_tag, False
        if not isinstance(parsed, dict):
            return entity_tag, False
        id_node = parsed.get("id")
        entity_id = id_node.value if isinstance(id_node, Str) else "minecraft:entity"
        new_node = self.entity.convert_entity_nbt(parsed, entity_id, ctx)
        new_snbt = snbt_dump(new_node)
        if new_snbt == entity_tag.snbt():
            return entity_tag, False
        return nbtlib.parse_nbt(new_snbt), True

    def convert_block_entity_nbt(self, block_id: str, be_nbt: dict, ctx: str) -> dict:
        """Modernize one block entity's NBT. Returns the new NBT compound.

        The block-entity rewrite logic itself is independent of the .schem
        loader, so the same routine can be reused if/when we add support for
        ``.litematic``, raw region files, or test-driven NBT trees.
        """
        if block_id in CONTAINER_BLOCK_IDS:
            return self._convert_container(be_nbt, ctx)
        if block_id in SPAWNER_BLOCK_IDS:
            return self._convert_spawner(be_nbt, ctx)
        if block_id in COMMAND_BLOCK_IDS:
            return self._convert_command_block(be_nbt, ctx)
        return be_nbt

    # ----- internal helpers ---------------------------------------------

    def _convert_container(self, be_nbt: dict, ctx: str) -> dict:
        items = be_nbt.get("Items")
        if not isinstance(items, list):
            return be_nbt
        new_items: list = []
        for i, it in enumerate(items):
            if isinstance(it, dict) and isinstance(it.get("id"), Str):
                slot = it.get("Slot")
                converted = self.item.convert_item_nbt(it, f"{ctx}.Items[{i}]")
                if slot is not None:
                    converted["Slot"] = slot
                new_items.append(converted)
            else:
                new_items.append(it)
        new_be = dict(be_nbt)
        new_be["Items"] = new_items
        return new_be

    def _convert_spawner(self, be_nbt: dict, ctx: str) -> dict:
        new_be = dict(be_nbt)
        spawn_data = be_nbt.get("SpawnData")
        if isinstance(spawn_data, dict):
            new_be["SpawnData"] = self._convert_spawn_data(spawn_data, f"{ctx}.SpawnData")
        potentials = be_nbt.get("SpawnPotentials")
        if isinstance(potentials, list):
            new_be["SpawnPotentials"] = [
                self._convert_spawn_potential(p, f"{ctx}.SpawnPotentials[{i}]")
                for i, p in enumerate(potentials)
            ]
        return new_be

    def _convert_spawn_potential(self, potential, ctx: str):
        if not isinstance(potential, dict):
            return potential
        new_p = dict(potential)
        data = new_p.get("data")
        if isinstance(data, dict):
            new_p["data"] = self._convert_spawn_data(data, f"{ctx}.data")
        return new_p

    def _convert_spawn_data(self, data: dict, ctx: str) -> dict:
        """SpawnData wraps an entity under the 'entity' key."""
        new_data = dict(data)
        entity = data.get("entity")
        if isinstance(entity, dict):
            id_node = entity.get("id")
            entity_id = id_node.value if isinstance(id_node, Str) else "minecraft:entity"
            new_data["entity"] = self.entity.convert_entity_nbt(entity, entity_id, ctx)
        return new_data

    def _convert_command_block(self, be_nbt: dict, ctx: str) -> dict:
        cmd = be_nbt.get("Command")
        if not isinstance(cmd, Str):
            return be_nbt
        raw = cmd.value
        # Only rewrite commands the dispatcher actually recognizes (give/summon
        # right now). Anything else (say, /tp or /scoreboard) round-trips
        # unchanged because the dispatcher returns the input untouched.
        new_text = self.dispatch_line(raw)
        if new_text == raw:
            return be_nbt
        new_be = dict(be_nbt)
        new_be["Command"] = Str(new_text, cmd.quote or '"')
        self.warnings.append(f"[{ctx}] rewrote command-block payload")
        return new_be
