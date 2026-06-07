"""Implementor: ``/summon <mob> [x y z] {entity_nbt}``.

The NBT block here is entity NBT (not item NBT), so it goes straight to
Level 2. Any items carried by the mob (``HandItems``, ``ArmorItems``,
``Inventory``, ``Items``, …) and the mob's ``CustomName`` are upgraded as a
side effect of the Level 2 walk.

In modern Minecraft the ``/summon`` NBT block is still SNBT (no bracketed
component form for entities), so the rewritten line keeps the trailing
``{…}`` shape.
"""

from __future__ import annotations

from typing import Optional

from ..command_parsing import SUMMON_RE, split_top_level_nbt
from ..snbt import snbt_dump, snbt_parse


def try_convert_line(line: str, pipeline) -> Optional[str]:
    """Return the rewritten ``/summon`` line, or ``None`` if not a match."""
    stripped = line.strip()
    if not stripped:
        return None
    m = SUMMON_RE.match(stripped)
    if not m:
        return None

    nbt_text, trailing = split_top_level_nbt(m.group("rest"))
    if nbt_text is None:
        return None  # no NBT to convert

    entity_nbt = snbt_parse(nbt_text)
    if not isinstance(entity_nbt, dict):
        return None

    entity_raw = m.group("entity").lower()
    entity_id = entity_raw if ":" in entity_raw else f"minecraft:{entity_raw}"
    new_nbt = pipeline.entity.convert_entity_nbt(
        entity_nbt, entity_id, ctx=f"summon/{entity_raw}"
    )

    parts = ["summon", entity_raw]
    pos = m.group("pos")
    if pos:
        parts.append(pos)
    return " ".join(parts) + " " + snbt_dump(new_nbt) + trailing
