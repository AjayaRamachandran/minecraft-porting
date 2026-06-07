"""Implementor: generic ``/give`` command line.

Handles the common shape ``/give <target> <item>{old_tag} [count]`` for items
that don't carry an ``EntityTag`` (spawn eggs are claimed by
:mod:`.villager_command` ahead of us).

The legacy ``{...}`` block after the item id corresponds to what used to be
the ItemStack's ``tag`` field, so it can be fed directly to Level 1's
``convert_tag_to_components``.
"""

from __future__ import annotations

from typing import Optional

from ..command_parsing import GIVE_RE, split_top_level_nbt
from ..snbt import Str, snbt_parse


def try_convert_line(line: str, pipeline) -> Optional[str]:
    """Return the rewritten line, or ``None`` if this is not a /give we handle."""
    stripped = line.strip()
    if not stripped:
        return None
    m = GIVE_RE.match(stripped)
    if not m:
        return None
    item = m.group("item").lower()
    # Defer spawn-egg lines to the villager implementor (registered first).
    if item.endswith("_spawn_egg") or item == "spawn_egg":
        return None
    # Defer spawner items — they need the spawner implementor's BlockEntityTag
    # handling, which generic /give can't model.
    if item in ("spawner", "trial_spawner"):
        return None

    nbt_text, trailing = split_top_level_nbt(m.group("rest"))
    if nbt_text is None:
        return None  # plain `/give @p item count` with no NBT — leave alone

    tag = snbt_parse(nbt_text)
    if not isinstance(tag, dict):
        return None

    # Strip special structural keys before Level 1 so they don't land in custom_data.
    entity_tag = tag.pop("EntityTag", None)
    block_entity_tag = tag.pop("BlockEntityTag", None)

    item_id = f"minecraft:{item}" if ":" not in item else item
    comps = pipeline.item.convert_tag_to_components(tag, item_id, ctx=f"give/{item}")

    if isinstance(entity_tag, dict):
        eid = item_id
        ed_input = {"id": Str(eid, '"'), **entity_tag}
        comps["minecraft:entity_data"] = pipeline.entity.convert_entity_nbt(
            ed_input, eid, ctx=f"give/{item}/EntityTag"
        )

    if isinstance(block_entity_tag, dict):
        # Convert any items stored inside the block entity (e.g. shulker box contents).
        new_be: dict = {}
        for k, v in block_entity_tag.items():
            if k == "Items" and isinstance(v, list):
                new_be[k] = [
                    pipeline.item.convert_item_nbt(it, f"give/{item}/BlockEntityTag.Items[{i}]")
                    if isinstance(it, dict) and "id" in it else it
                    for i, it in enumerate(v)
                ]
            else:
                new_be[k] = v
        comps["minecraft:block_entity_data"] = new_be

    block = pipeline.item.render_components_bracket(dict(sorted(comps.items())))
    return f"give {m.group('target')} {item}{block}{trailing}"
