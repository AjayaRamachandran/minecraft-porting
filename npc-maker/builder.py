"""NPC schematic builder — generates 1.21.11-format command-block NPCs.

This is the reusable core extracted from the original ``main.py`` script and
ported to Minecraft 1.21.11. Two things changed in the port:

1. **tellraw click events** — pre-1.21.5 used ``clickEvent`` with a ``value``
   field; 1.21.5+ renamed these to ``click_event`` / ``command`` (for the
   ``run_command``/``suggest_command`` actions). The choice buttons emit the
   modern keys. (Mirrors ``convert_villager/converter/text_components.py``.)
2. **schematic version** — the original saved as ``JE_1_19_1``; we now save
   with the newest version ``mcschematic`` supports (``JE_1_21_5``), which
   WorldEdit loads and upgrades cleanly into 1.21.11. (There is no 1.21.11
   enum in mcschematic.)

The "break-safe" trigger design is preserved exactly: players can only enable
the trigger objectives for choices reachable from the conversation node they
are currently on, so the NPC can never be driven into an invalid state.

Two input formats are accepted (see :func:`normalize`):

- **1.0** (legacy) — each conversation carries its own ``npc_name``; no global
  name/colour. This is what the old ``jsons/*.json`` files use.
- **1.1** (current) — a single global ``npc_name`` + ``name_color`` for the
  whole NPC; conversations only carry ``scoreboard_tag`` / ``message`` /
  ``choices``. More compact, and matches the web editor's model.

Anything in 1.0 is migrated forward to 1.1 before generation.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_NAME_COLOR = "gold"
SCHEM_VERSION_NAME = "JE_1_21_5"  # newest mcschematic supports; loads into 1.21.11


def _esc_snbt_single(s: str) -> str:
    """Escape a string for embedding inside an SNBT single-quoted string.

    The command payload is stored as ``Command:'<cmd>'`` and parsed by
    ``nbtlib.parse_nbt`` (via mcschematic). A literal apostrophe in a dialogue
    message would otherwise terminate the string early, so backslashes and
    single quotes are escaped.
    """
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _converter_imports():
    """Lazily import the converter's SNBT renderer (shared with the converter).

    builder.py also runs standalone via ``main.py`` and through the web backend,
    so the import path to ``convert_villager/`` is set up on demand rather than
    at module load. Reuses :meth:`ItemConverter.render_components_bracket` and
    the ``Num``/``Str`` SNBT node types so give-command components render
    exactly like the converter's ``/give`` output.
    """
    import sys
    from pathlib import Path

    cv = Path(__file__).resolve().parent.parent / "convert_villager"
    if str(cv) not in sys.path:
        sys.path.insert(0, str(cv))
    from converter.item_converter import ItemConverter  # noqa: PLC0415
    from converter.snbt import Num, Str  # noqa: PLC0415
    return ItemConverter, Num, Str


def _json_to_snbt(value, Num, Str):
    """Convert plain JSON component values into SNBT nodes for rendering.

    Booleans become byte ``1b``/``0b`` (checked before int — ``bool`` is a
    subclass of ``int``), ints stay untyped, floats get the ``d`` suffix, and
    strings are double-quoted. Compounds/lists recurse.
    """
    if isinstance(value, bool):
        return Num(1 if value else 0, "b")
    if isinstance(value, int):
        return Num(value, "")
    if isinstance(value, float):
        return Num(value, "d")
    if isinstance(value, str):
        return Str(value, '"')
    if isinstance(value, dict):
        return {k: _json_to_snbt(v, Num, Str) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_to_snbt(v, Num, Str) for v in value]
    if value is None:
        return Str("", '"')
    raise TypeError(f"cannot convert to SNBT: {type(value).__name__}")


def _norm_item(it: dict) -> dict:
    """Normalize one give-item: ``{base_item, count, components}`` (raw JSON)."""
    base = str(it.get("base_item") or "paper")
    if base.startswith("minecraft:"):
        base = base.split(":", 1)[1]
    return {
        "base_item": base,
        "count": int(it.get("count", 1) or 1),
        "components": it.get("components") or {},
    }


def _give_command(item: dict) -> str:
    """Render a single ``give @p minecraft:<base>[<components>] <count>`` command.

    No leading slash — this is the body after ``... run`` in an /execute. The
    component bracket is produced by the converter's renderer.
    """
    ItemConverter, Num, Str = _converter_imports()
    comps = {k: _json_to_snbt(v, Num, Str) for k, v in (item["components"] or {}).items()}
    bracket = ItemConverter.render_components_bracket(comps)
    return f"give @p minecraft:{item['base_item']}{bracket} {item['count']}"


def _held_item_predicate(item: dict) -> str:
    """Return an item predicate string for ``execute if items`` and ``clear``.

    Matches by base item type plus ``minecraft:item_model`` when present, which
    uniquely identifies custom library items without requiring a full component
    match.
    """
    base = item["base_item"]
    model = (item.get("components") or {}).get("minecraft:item_model")
    if model:
        return f'minecraft:{base}[minecraft:item_model="{model}"]'
    return f"minecraft:{base}"


def _norm_gate_scoreboard(g) -> dict | None:
    """Normalize a scoreboard gate ``{objective, score}`` or return ``None``."""
    if not g:
        return None
    obj = str(g.get("objective") or "").strip()
    if not obj:
        return None
    return {"objective": obj, "score": int(g.get("score") or 0)}


def _norm_gate_held_item(g) -> dict | None:
    """Normalize a held-item gate (same shape as a give-item) or return ``None``."""
    if not g or not g.get("base_item"):
        return None
    return _norm_item(g)


def normalize(data: dict) -> dict:
    """Return a current-format copy of ``data``, migrating older inputs forward.

    Version is taken from ``builder_version`` (string). A missing version is
    treated as 1.0 — that's what the original hand-written JSONs are. 1.0/1.1
    inputs simply carry no per-choice ``items`` and produce byte-identical
    output to before. 1.2 adds optional ``items`` on choices (drag-to-give).
    1.3 adds optional ``gates`` on choices (scoreboard + held-item conditions).
    """
    version = str(data.get("builder_version", "1.0"))
    conversations = data.get("conversations", []) or []

    if version != "1.0":
        npc_name = data.get("npc_name", "")
        name_color = data.get("name_color") or DEFAULT_NAME_COLOR
    else:
        # 1.0 → current: lift the per-node name (they were all identical) up to
        # the NPC level, default the colour, and drop per-node names.
        npc_name = ""
        for conv in conversations:
            if conv.get("npc_name"):
                npc_name = conv["npc_name"]
                break
        name_color = DEFAULT_NAME_COLOR

    norm_convs = []
    for conv in conversations:
        norm_choices = []
        for c in (conv.get("choices") or []):
            gates_raw = c.get("gates") or {}
            sg = _norm_gate_scoreboard(gates_raw.get("scoreboard"))
            hg = _norm_gate_held_item(gates_raw.get("held_item"))
            norm_choices.append({
                "text": c.get("text", ""),
                "direct": str(c.get("direct", "")),
                "items": [_norm_item(it) for it in (c.get("items") or [])],
                "gates": {
                    "scoreboard": sg,
                    "held_item": hg,
                    "consume_held_item": bool(gates_raw.get("consume_held_item", True)) if hg else True,
                },
            })
        norm_convs.append({
            "scoreboard_tag": str(conv.get("scoreboard_tag", "")),
            "message": conv.get("message", ""),
            "choices": norm_choices,
        })

    return {
        "builder_version": "1.3",
        "npc_variable_initial": data.get("npc_variable_initial", "npc"),
        "npc_name": npc_name,
        "name_color": name_color,
        "conversations": norm_convs,
    }


def _dialogue_command(prefix: str, tag: str, npc_name: str, name_color: str, message: str) -> str:
    """The repeating-block line: prints '[Name] message' to players on this node."""
    payload = [
        {"text": f"[{npc_name}]", "color": name_color},
        {"text": f" {message}", "color": "white"},
    ]
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"/execute as @a[scores={{{prefix}{tag}=1}}] run tellraw @s {body}"


def _choice_command(prefix: str, tag: str, text: str, trigger_obj: str,
                    score_gate: dict | None = None,
                    held_item_gate: dict | None = None) -> str:
    """A clickable choice line. Uses 1.21.5+ click_event/command keys.

    ``trigger_obj`` is the full objective the click ``/trigger``s — the target
    node's objective for a normal choice, or a per-choice staging objective for
    a give/gated choice.

    Optional gates narrow which players see the option:
    - ``score_gate`` adds a scoreboard score condition to the entity selector.
    - ``held_item_gate`` wraps the tellraw in an ``if items`` sub-command so only
      players currently holding the required item see the choice.
    """
    payload = {
        "text": f"> [{text}]",
        "color": "light_purple",
        "click_event": {"action": "run_command", "command": f"/trigger {trigger_obj}"},
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    scores_part = f"{prefix}{tag}=1"
    if score_gate:
        scores_part += f",{score_gate['objective']}={score_gate['score']}"

    if held_item_gate:
        pred = _held_item_predicate(held_item_gate)
        return (f"/execute as @a[scores={{{scores_part}}}] "
                f"if items entity @s weapon.mainhand {pred} run tellraw @s {body}")
    return f"/execute as @a[scores={{{scores_part}}}] run tellraw @s {body}"


def _cmd_block(block_id: str, command: str, *, auto: bool = True) -> str:
    """SNBT block-data string for a command block holding ``command``."""
    auto_part = "auto:1b," if auto else ""
    return f"{block_id}[facing=up]{{{auto_part}Command:'{_esc_snbt_single(command)}'}}"


def build(data: dict):
    """Build the NPC schematic from ``data`` (any supported version).

    Returns ``(schematic, output_text)`` where ``output_text`` is the
    human-readable command listing (the old ``output.txt`` content). The
    schematic is an :class:`mcschematic.MCSchematic`; the caller saves it.
    """
    import mcschematic  # imported lazily so normalize()/commands work without it

    data = normalize(data)
    prefix = data["npc_variable_initial"]
    npc_name = data["npc_name"]
    name_color = data["name_color"]
    conversations = data["conversations"]

    if not conversations:
        raise ValueError("NPC has no conversation nodes.")

    schem = mcschematic.MCSchematic()
    out: list[str] = [
        "Below are the commands for your NPC. The first in each group runs in a "
        "repeat command block, the others in chain.\n",
    ]

    x = 0
    links: list[dict] = []      # {"head", "branch", "score_gate"} for normal choices
    height_map: list[list] = []  # [x, scoreboard_tag, next_free_y]
    give_stages: list[dict] = []  # per-staging-objective metadata
    stage = 1000               # global staging-objective counter (no node-tag clash)

    # --- per-conversation columns ------------------------------------------
    for conv in conversations:
        x += 1
        y = 0
        z = 0
        tag = conv["scoreboard_tag"]
        out.append(f"Commands for {npc_name} (node {tag})\n")

        dialogue = _dialogue_command(prefix, tag, npc_name, name_color, conv["message"])
        out.append(dialogue)
        schem.setBlock((x, y, z), _cmd_block("repeating_command_block", dialogue))

        for choice in conv["choices"]:
            gates = choice.get("gates") or {}
            score_gate = gates.get("scoreboard")          # None or {objective, score}
            held_gate = gates.get("held_item")             # None or item dict
            consume_held = gates.get("consume_held_item", True)

            # Staging is needed when giving items OR consuming a held item,
            # since both require a per-click flag to fire exactly once.
            has_give = bool(choice["items"])
            needs_staging = has_give or (bool(held_gate) and consume_held)

            trigger_obj = f"{prefix}g{stage}" if needs_staging else f"{prefix}{choice['direct']}"

            y += 1
            choice_cmd = _choice_command(prefix, tag, choice["text"], trigger_obj,
                                         score_gate=score_gate, held_item_gate=held_gate)
            out.append(choice_cmd)
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", choice_cmd))
            # Mark the player's current node so the link section knows which
            # branches (and staging objectives) they're allowed to enable.
            y += 1
            mark = (f"/execute as @a[scores={{{prefix}{tag}=1}}] run "
                    f"scoreboard players set @s {prefix} {tag}")
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", mark))

            if needs_staging:
                # Staging group, gated on the per-choice staging objective.
                # Fires exactly once for players who clicked THIS choice.
                gate_str = f"/execute as @a[scores={{{prefix}g{stage}=1..}}] run "

                # Give items (if any).
                for it in choice["items"]:
                    y += 1
                    give = gate_str + _give_command(it)
                    out.append(give)
                    schem.setBlock((x, y, z), _cmd_block("chain_command_block", give))

                # Consume the held item gate (if any and consume is enabled).
                if held_gate and consume_held:
                    y += 1
                    pred = _held_item_predicate(held_gate)
                    clr_item = gate_str + f"clear @s {pred} 1"
                    out.append(clr_item)
                    schem.setBlock((x, y, z), _cmd_block("chain_command_block", clr_item))

                # Advance / route.
                y += 1
                if choice["direct"]:
                    adv = gate_str + f"scoreboard players set @s {prefix}{choice['direct']} 1"
                else:
                    adv = gate_str + f"scoreboard players set @s {prefix} 0"
                out.append(adv)
                schem.setBlock((x, y, z), _cmd_block("chain_command_block", adv))

                # Clear the staging score (must be last gated block) + reset.
                y += 1
                clr = gate_str + f"scoreboard players set @s {prefix}g{stage} 0"
                out.append(clr)
                schem.setBlock((x, y, z), _cmd_block("chain_command_block", clr))
                y += 1
                rst = f"/scoreboard players reset @a {prefix}g{stage}"
                schem.setBlock((x, y, z), _cmd_block("chain_command_block", rst))

                give_stages.append({
                    "stage": stage,
                    "head": tag,
                    "score_gate": score_gate,
                    "held_item_gate": held_gate,
                    "consume_held": consume_held,
                })
                stage += 1
            elif choice["direct"]:
                # Normal (non-staging) choice: record for break-safe enable wiring.
                # Carry held_gate here when consume is off — the enable still needs
                # the ``if items`` check even though nothing is consumed.
                links.append({
                    "head": tag,
                    "branch": choice["direct"],
                    "score_gate": score_gate,
                    "held_item_gate": held_gate if not consume_held else None,
                })

        if not conv["choices"]:
            y += 1
            mark = (f"/execute as @a[scores={{{prefix}{tag}=1}}] run "
                    f"scoreboard players set @s {prefix} 0")
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", mark))

        # Close out the node: clear its trigger score so the column stops firing.
        closer = (f"/execute as @a[scores={{{prefix}{tag}=1}}] run "
                  f"scoreboard players set @s {prefix}{tag} 0")
        out.append(closer + "\n")
        y += 1
        schem.setBlock((x, y, z), _cmd_block("chain_command_block", closer))
        y += 1
        reset = f"/scoreboard players reset @a {prefix}{tag}"
        schem.setBlock((x, y, z), _cmd_block("chain_command_block", reset))

        height_map.append([x, tag, y])

    # --- initialization blocks (objective add/remove + buttons) ------------
    out.append("\nYou will need to initialize your NPCs with the following commands.\n")
    x = 0
    y = 0
    z = 1
    schem.setBlock((x, y, z), _cmd_block("command_block",
                   f"/scoreboard objectives add {prefix} dummy", auto=False))
    schem.setBlock((x, y + 1, z), "stone_button[face=floor]")
    schem.setBlock((x, y, z + 2), _cmd_block("command_block",
                   f"/scoreboard objectives remove {prefix}", auto=False))
    schem.setBlock((x, y + 1, z + 2), "stone_button[face=floor]")
    for conv in conversations:
        z = 1
        x += 1
        tag = conv["scoreboard_tag"]
        initialize = f"/scoreboard objectives add {prefix}{tag} trigger"
        destroy = f"/scoreboard objectives remove {prefix}{tag}"
        out.append(initialize)
        schem.setBlock((x, y, z), _cmd_block("command_block", initialize, auto=False))
        schem.setBlock((x, y, z + 2), _cmd_block("command_block", destroy, auto=False))
        schem.setBlock((x, y + 1, z), "redstone_wire")
        schem.setBlock((x, y + 1, z + 2), "redstone_wire")
    # One trigger objective per give-choice, continuing the same powered row.
    for gs in give_stages:
        z = 1
        x += 1
        obj = f"{prefix}g{gs['stage']}"
        initialize = f"/scoreboard objectives add {obj} trigger"
        destroy = f"/scoreboard objectives remove {obj}"
        out.append(initialize)
        schem.setBlock((x, y, z), _cmd_block("command_block", initialize, auto=False))
        schem.setBlock((x, y, z + 2), _cmd_block("command_block", destroy, auto=False))
        schem.setBlock((x, y + 1, z), "redstone_wire")
        schem.setBlock((x, y + 1, z + 2), "redstone_wire")

    # --- entry point + break-safe link wiring ------------------------------
    x = 0
    y = 0
    z = 0
    entry_tag = conversations[0]["scoreboard_tag"]
    schem.setBlock((x, y, z), _cmd_block("repeating_command_block",
                   f"/execute as @a run scoreboard players enable @s {prefix}{entry_tag}"))

    for link in links:
        head = link["head"]
        branch = link["branch"]
        score_gate = link["score_gate"]
        held_item_gate = link.get("held_item_gate")
        # Branches pointing at a node that doesn't exist are "unlinked" tags
        # the user wires up in-game; skip them to avoid stale-coordinate bugs.
        target = next((hm for hm in height_map if hm[1] == branch), None)
        if target is None:
            continue
        x = target[0]
        y = target[2]
        target[2] += 1
        y += 1
        scores_sel = f"{prefix}={head}"
        if score_gate:
            scores_sel += f",{score_gate['objective']}={score_gate['score']}"
        if held_item_gate:
            pred = _held_item_predicate(held_item_gate)
            link_cmd = (f"/execute as @a[scores={{{scores_sel}}}] "
                        f"if items entity @s weapon.mainhand {pred} run "
                        f"scoreboard players enable @s {prefix}{branch}")
        else:
            link_cmd = (f"/execute as @a[scores={{{scores_sel}}}] run "
                        f"scoreboard players enable @s {prefix}{branch}")
        schem.setBlock((x, y, z), _cmd_block("chain_command_block", link_cmd))

    # Break-safe enable for each staging objective (give-choices and gated
    # choices). Only players on the head node may /trigger it. For held-item
    # gates the enable is additionally wrapped in an ``if items`` check so the
    # trigger stays disabled unless the player is actually holding the item.
    for gs in give_stages:
        head = gs["head"]
        score_gate = gs.get("score_gate")
        held_item_gate = gs.get("held_item_gate")
        target = next((hm for hm in height_map if hm[1] == head), None)
        if target is None:
            continue
        x = target[0]
        y = target[2]
        target[2] += 1
        y += 1
        scores_sel = f"{prefix}={head}"
        if score_gate:
            scores_sel += f",{score_gate['objective']}={score_gate['score']}"
        if held_item_gate:
            pred = _held_item_predicate(held_item_gate)
            link_cmd = (f"/execute as @a[scores={{{scores_sel}}}] "
                        f"if items entity @s weapon.mainhand {pred} run "
                        f"scoreboard players enable @s {prefix}g{gs['stage']}")
        else:
            link_cmd = (f"/execute as @a[scores={{{scores_sel}}}] run "
                        f"scoreboard players enable @s {prefix}g{gs['stage']}")
        schem.setBlock((x, y, z), _cmd_block("chain_command_block", link_cmd))

    return schem, "\n".join(out) + "\n"
