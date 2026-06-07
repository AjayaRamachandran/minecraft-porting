"""Implementor: ``/give @p villager_spawn_egg{…}`` with trades.

Spawn-egg items carry their about-to-be-spawned entity's NBT inside an
``EntityTag`` field. For villagers this also includes the trade ``Offers``,
which contain nested item NBTs.

The shape we convert is:

    /give <target> villager_spawn_egg{display:{…}, EntityTag:{…, Offers:{…}}}

becomes:

    give <target> villager_spawn_egg[minecraft:custom_name=…, minecraft:entity_data={id:"minecraft:villager", …}]

This implementor is responsible for the orchestration:

1. Strip ``EntityTag`` out of the item-tag block.
2. Run the remaining tag fields through Level 1 (item converter).
3. Run ``EntityTag`` through Level 2 (entity converter), prepending the
   required ``id:"minecraft:villager"`` field that ``minecraft:entity_data``
   needs.
4. Merge the Level 2 result back in as the ``minecraft:entity_data`` component.
"""

from __future__ import annotations

from typing import Optional

from ..command_parsing import GIVE_RE, split_top_level_nbt
from ..snbt import Str, snbt_parse


# Mapping from spawn-egg item id → entity id. Extend as new entity types
# come in; the generic shape (Foo_spawn_egg → minecraft:foo) covers most.
SPAWN_EGG_TO_ENTITY = {
    "villager_spawn_egg": "minecraft:villager",
}


def _entity_id_for(item: str) -> str:
    item = item.lower()
    if item in SPAWN_EGG_TO_ENTITY:
        return SPAWN_EGG_TO_ENTITY[item]
    if item.endswith("_spawn_egg"):
        return "minecraft:" + item[: -len("_spawn_egg")]
    return "minecraft:" + item


def try_convert_line(line: str, pipeline) -> Optional[str]:
    """Return the rewritten line, or ``None`` if this is not a spawn-egg /give."""
    stripped = line.strip()
    if not stripped:
        return None
    m = GIVE_RE.match(stripped)
    if not m:
        return None
    item = m.group("item").lower()
    if not (item.endswith("_spawn_egg") or item == "spawn_egg"):
        return None

    nbt_text, trailing = split_top_level_nbt(m.group("rest"))
    if nbt_text is None:
        # Plain spawn egg without NBT — nothing to convert.
        return None

    tag = snbt_parse(nbt_text)
    if not isinstance(tag, dict):
        return None

    # Split EntityTag out of the item tag so Level 1 sees only standard fields.
    entity_tag = tag.pop("EntityTag", None)
    item_id = f"minecraft:{item}"
    comps = pipeline.item.convert_tag_to_components(tag, item_id, ctx=f"give/{item}")

    if isinstance(entity_tag, dict):
        entity_id = _entity_id_for(item)
        # entity_data demands an `id:` field naming the entity type.
        ed_input = {"id": Str(entity_id, '"'), **entity_tag}
        comps["minecraft:entity_data"] = pipeline.entity.convert_entity_nbt(
            ed_input, entity_id, ctx=f"give/{item}/EntityTag"
        )

    block = pipeline.item.render_components_bracket(dict(sorted(comps.items())))
    return f"give {m.group('target')} {item}{block}{trailing}"
