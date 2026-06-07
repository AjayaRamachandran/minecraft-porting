"""Level 2: EntityConverter — entity NBT with items inside.

Walks an entity's NBT compound and converts every item it finds via
:class:`~.item_converter.ItemConverter`. Also promotes the entity's
``CustomName`` from a JSON-string text component to NBT compound form.

Covered item-bearing fields (any subset may appear depending on entity type):
- Villager-style trades: ``Offers.Recipes[].{buy, buyB, sell}``
- Mob equipment: ``HandItems``, ``ArmorItems`` (positional lists; empty slots
  are ``{}``)
- Container-style: ``Inventory``, ``Items`` (lists with optional ``Slot`` field)
- Single-item fields: ``Item``, ``SaddleItem``, ``ArmorItem``, ``Body``,
  ``Trident`` (added defensively)
- ``Passengers`` — recurses into each rider's entity NBT

Other fields pass through unchanged. The class is intentionally agnostic to
the *meaning* of each entity type: the wrapping command (``/summon …`` or
``/give …_spawn_egg``) is the implementor's responsibility.
"""

from __future__ import annotations

from .item_converter import ItemConverter
from .snbt import Num, Str
from .text_components import convert_text_component


# Fields known to hold a list of item-stack NBTs.
_ITEM_LIST_FIELDS = ("HandItems", "ArmorItems", "Inventory", "Items")
# Fields known to hold a single item-stack NBT.
_SINGLE_ITEM_FIELDS = ("Item", "SaddleItem", "ArmorItem", "Body", "Trident")

# Legacy ArmorDropChances is ordered feet→legs→chest→head, HandDropChances is
# mainhand→offhand. Modern format collapses both into a single `drop_chances`
# compound keyed by slot name.
_ARMOR_DROP_SLOTS = ("feet", "legs", "chest", "head")
_HAND_DROP_SLOTS = ("mainhand", "offhand")


def _looks_like_item(node) -> bool:
    return isinstance(node, dict) and isinstance(node.get("id"), Str)


class EntityConverter:
    """Walks entity NBT and rewrites items + text components in place-style copies.

    Parameters
    ----------
    item_converter:
        Used to convert each item-stack NBT encountered during the walk.
    warnings:
        Mutable list the converter appends free-text diagnostics to.
    """

    def __init__(self, item_converter: ItemConverter, warnings: list[str]):
        self.item = item_converter
        self.warnings = warnings

    def convert_entity_nbt(self, entity_nbt: dict, entity_id: str, ctx: str) -> dict:
        """Return a new entity NBT dict with items + custom name modernized.

        ``entity_id`` is the entity type (e.g. ``"minecraft:villager"``). It is
        used only for diagnostic context — the dict's own ``id`` field, if
        present, is preserved untouched.

        Performs these legacy → modern transforms on top of recursing items:
        - ``CustomName`` JSON string → NBT text component
        - ``Attributes:[{Name,Base}]`` → ``attributes:[{id,base}]`` (renamed
          + field-renamed)
        - ``ArmorDropChances`` / ``HandDropChances`` lists → unified
          ``drop_chances:{<slot>:F}`` compound
        - ``equipment:{<slot>:item}`` items routed through Level 1 so
          half-migrated CMD components get their ``item_model`` filled in.
        """
        out: dict = {}
        for k, v in entity_nbt.items():
            if k == "CustomName":
                out[k] = convert_text_component(v)
            elif k == "Offers":
                out[k] = self._convert_offers(v, f"{ctx}.Offers")
            elif k == "Passengers" and isinstance(v, list):
                out[k] = [self._convert_passenger(p, f"{ctx}.Passengers[{i}]")
                          for i, p in enumerate(v)]
            elif k in _ITEM_LIST_FIELDS and isinstance(v, list):
                out[k] = [self._convert_maybe_item(it, f"{ctx}.{k}[{i}]")
                          for i, it in enumerate(v)]
            elif k in _SINGLE_ITEM_FIELDS and _looks_like_item(v):
                out[k] = self.item.convert_item_nbt(v, f"{ctx}.{k}")
            elif k == "Attributes" and isinstance(v, list):
                out["attributes"] = self._convert_legacy_attributes(v)
            elif k == "ArmorDropChances" and isinstance(v, list):
                self._merge_drop_chances(out, _ARMOR_DROP_SLOTS, v)
            elif k == "HandDropChances" and isinstance(v, list):
                self._merge_drop_chances(out, _HAND_DROP_SLOTS, v)
            elif k == "equipment" and isinstance(v, dict):
                out[k] = self._convert_equipment(v, f"{ctx}.equipment")
            else:
                out[k] = v
        return out

    def convert_spawner_be(self, be_tag: dict, ctx: str) -> dict:
        """Walk a spawner block-entity payload, routing entities through Level 2.

        Handles both the field names that show up in a /give-spawner
        ``BlockEntityTag`` and the same fields on an in-world spawner block
        entity. Static numeric fields (``SpawnCount``, delays, ranges, …)
        pass through unchanged.
        """
        out: dict = {}
        for k, v in be_tag.items():
            if k == "SpawnData" and isinstance(v, dict):
                out[k] = self._convert_spawn_data(v, f"{ctx}.SpawnData")
            elif k == "SpawnPotentials" and isinstance(v, list):
                out[k] = [self._convert_spawn_potential(p, f"{ctx}.SpawnPotentials[{i}]")
                          for i, p in enumerate(v)]
            else:
                out[k] = v
        return out

    # ----- internal helpers ---------------------------------------------

    def _convert_maybe_item(self, node, ctx: str):
        """Convert ``node`` if it looks like an item stack, else leave as-is."""
        if _looks_like_item(node):
            return self.item.convert_item_nbt(node, ctx)
        return node

    def _convert_passenger(self, node, ctx: str):
        """Recurse into a passenger entity's NBT."""
        if isinstance(node, dict):
            id_node = node.get("id")
            sub_id = id_node.value if isinstance(id_node, Str) else "minecraft:entity"
            return self.convert_entity_nbt(node, sub_id, ctx)
        return node

    def _convert_legacy_attributes(self, attrs: list) -> list:
        """``Attributes:[{Name:"generic.X",Base:N}]`` → ``[{id:"minecraft:X",base:N}]``."""
        out: list = []
        for a in attrs:
            if not isinstance(a, dict):
                continue
            name_n = a.get("Name")
            if not isinstance(name_n, Str):
                continue
            name = name_n.value
            if "." in name and ":" not in name:
                # "generic.max_health" → "max_health"
                name = name.split(".", 1)[1]
            if ":" not in name:
                name = "minecraft:" + name
            base_n = a.get("Base")
            base_val = base_n.value if isinstance(base_n, Num) else 0
            new_entry: dict = {
                "id":   Str(name, '"'),
                "base": Num(float(base_val), "d"),
            }
            # Most entity attributes don't carry Modifiers in vanilla; pass
            # them through verbatim if present so we don't drop data.
            if "Modifiers" in a:
                new_entry["modifiers"] = a["Modifiers"]
            out.append(new_entry)
        return out

    @staticmethod
    def _merge_drop_chances(out: dict, slots: tuple, values: list) -> None:
        dc = out.setdefault("drop_chances", {})
        for slot, value in zip(slots, values):
            dc[slot] = value

    def _convert_equipment(self, equip: dict, ctx: str) -> dict:
        result: dict = {}
        for slot, item in equip.items():
            if _looks_like_item(item):
                result[slot] = self.item.convert_item_nbt(item, f"{ctx}.{slot}")
            else:
                result[slot] = item
        return result

    def _convert_spawn_data(self, data, ctx: str):
        if not isinstance(data, dict):
            return data
        new_data = dict(data)
        ent = data.get("entity")
        if isinstance(ent, dict):
            id_node = ent.get("id")
            eid = id_node.value if isinstance(id_node, Str) else "minecraft:entity"
            new_data["entity"] = self.convert_entity_nbt(ent, eid, f"{ctx}.entity")
        return new_data

    def _convert_spawn_potential(self, pot, ctx: str):
        if not isinstance(pot, dict):
            return pot
        new_p = dict(pot)
        data = pot.get("data")
        if isinstance(data, dict):
            new_p["data"] = self._convert_spawn_data(data, f"{ctx}.data")
        return new_p

    def _convert_offers(self, offers, ctx: str):
        """Convert villager trade offers — each recipe's buy/buyB/sell item."""
        if not isinstance(offers, dict):
            return offers
        recipes = offers.get("Recipes")
        if not isinstance(recipes, list):
            return offers
        new_recipes: list = []
        for i, recipe in enumerate(recipes):
            if not isinstance(recipe, dict):
                new_recipes.append(recipe)
                continue
            new_recipe: dict = {}
            for k, v in recipe.items():
                if k in ("buy", "buyB", "sell") and _looks_like_item(v):
                    new_recipe[k] = self.item.convert_item_nbt(
                        v, f"{ctx}/trade[{i}].{k}"
                    )
                else:
                    new_recipe[k] = v
            new_recipes.append(new_recipe)
        new_offers = dict(offers)
        new_offers["Recipes"] = new_recipes
        return new_offers
