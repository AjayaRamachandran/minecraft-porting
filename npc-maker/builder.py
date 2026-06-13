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


def normalize(data: dict) -> dict:
    """Return a 1.1-format copy of ``data``, migrating 1.0 inputs forward.

    Version is taken from ``builder_version`` (string). A missing version is
    treated as 1.0 — that's what the original hand-written JSONs are.
    """
    version = str(data.get("builder_version", "1.0"))
    conversations = data.get("conversations", []) or []

    if version == "1.1":
        npc_name = data.get("npc_name", "")
        name_color = data.get("name_color") or DEFAULT_NAME_COLOR
    else:
        # 1.0 → 1.1: lift the per-node name (they were all identical) up to the
        # NPC level, default the colour, and drop per-node names.
        npc_name = ""
        for conv in conversations:
            if conv.get("npc_name"):
                npc_name = conv["npc_name"]
                break
        name_color = DEFAULT_NAME_COLOR

    norm_convs = []
    for conv in conversations:
        norm_convs.append({
            "scoreboard_tag": str(conv.get("scoreboard_tag", "")),
            "message": conv.get("message", ""),
            "choices": [
                {"text": c.get("text", ""), "direct": str(c.get("direct", ""))}
                for c in (conv.get("choices") or [])
            ],
        })

    return {
        "builder_version": "1.1",
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


def _choice_command(prefix: str, tag: str, text: str, direct: str) -> str:
    """A clickable choice line. Uses 1.21.5+ click_event/command keys."""
    payload = {
        "text": f"> [{text}]",
        "color": "light_purple",
        "click_event": {"action": "run_command", "command": f"/trigger {prefix}{direct}"},
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"/execute as @a[scores={{{prefix}{tag}=1}}] run tellraw @s {body}"


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
    links: list[list] = []     # [scoreboard_tag, [target_tags...]]
    height_map: list[list] = []  # [x, scoreboard_tag, next_free_y]

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

        links.append([tag, [c["direct"] for c in conv["choices"]]])

        for choice in conv["choices"]:
            y += 1
            choice_cmd = _choice_command(prefix, tag, choice["text"], choice["direct"])
            out.append(choice_cmd)
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", choice_cmd))
            # Mark the player's current node so the link section knows which
            # branches they're allowed to enable.
            y += 1
            mark = (f"/execute as @a[scores={{{prefix}{tag}=1}}] run "
                    f"scoreboard players set @s {prefix} {tag}")
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", mark))

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

    # --- entry point + break-safe link wiring ------------------------------
    x = 0
    y = 0
    z = 0
    entry_tag = conversations[0]["scoreboard_tag"]
    schem.setBlock((x, y, z), _cmd_block("repeating_command_block",
                   f"/execute as @a run scoreboard players enable @s {prefix}{entry_tag}"))

    for head, branches in links:
        for branch in branches:
            # Branches pointing at a node that doesn't exist are "unlinked"
            # tags the user wires up in-game; we don't manage their objectives
            # here, so skip them (and avoid the original's stale-coordinate bug).
            target = next((hm for hm in height_map if hm[1] == branch), None)
            if target is None:
                continue
            x = target[0]
            y = target[2]
            target[2] += 1
            y += 1
            link_cmd = (f"/execute as @a[scores={{{prefix}={head}}}] run "
                        f"scoreboard players enable @s {prefix}{branch}")
            schem.setBlock((x, y, z), _cmd_block("chain_command_block", link_cmd))

    return schem, "\n".join(out) + "\n"
