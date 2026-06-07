"""Implementor: ``/give @p spawner{... BlockEntityTag:{...} ...}``.

Spawner items carry their pre-set spawner block-entity NBT inside
``BlockEntityTag``. The modern equivalent is the ``minecraft:block_entity_data``
component. Inside it, ``SpawnData.entity`` and each
``SpawnPotentials[].data.entity`` are entity NBTs and go through Level 2 so
embedded items, custom names, legacy ``Attributes``/``HandItems``/etc. all
get modernized.

Orchestration mirrors :mod:`.villager_command`:

1. Pop ``BlockEntityTag`` off the legacy item-tag block.
2. Run the remaining fields through Level 1.
3. Wrap the BlockEntityTag in ``minecraft:block_entity_data`` (prepending the
   required ``id:"minecraft:mob_spawner"``) and walk it via
   :meth:`EntityConverter.convert_spawner_be`.
"""

from __future__ import annotations

from typing import Optional

from ..command_parsing import GIVE_RE, split_top_level_nbt
from ..snbt import Str, snbt_parse


# Spawner item id → block-entity id used inside the `entity_data` wrapping.
SPAWNER_ITEM_TO_BE_ID = {
    "spawner":        "minecraft:mob_spawner",
    "trial_spawner":  "minecraft:trial_spawner",
}


def try_convert_line(line: str, pipeline) -> Optional[str]:
    """Return the rewritten line, or ``None`` if not a spawner /give we handle."""
    stripped = line.strip()
    if not stripped:
        return None
    m = GIVE_RE.match(stripped)
    if not m:
        return None
    item = m.group("item").lower()
    if item not in SPAWNER_ITEM_TO_BE_ID:
        return None

    nbt_text, trailing = split_top_level_nbt(m.group("rest"))
    if nbt_text is None:
        return None  # plain `/give @p spawner [count]` — nothing to convert

    tag = snbt_parse(nbt_text)
    if not isinstance(tag, dict):
        return None

    be_tag = tag.pop("BlockEntityTag", None)
    item_id = f"minecraft:{item}"
    comps = pipeline.item.convert_tag_to_components(tag, item_id, ctx=f"give/{item}")

    if isinstance(be_tag, dict):
        be_id = SPAWNER_ITEM_TO_BE_ID[item]
        walked = pipeline.entity.convert_spawner_be(be_tag, ctx=f"give/{item}/BlockEntityTag")
        comps["minecraft:block_entity_data"] = {"id": Str(be_id, '"'), **walked}

    block = pipeline.item.render_components_bracket(dict(sorted(comps.items())))
    return f"give {m.group('target')} {item}{block}{trailing}"
