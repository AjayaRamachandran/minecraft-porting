"""Level 2: EntityConverter — entity NBT with items inside.

Walks an entity's NBT compound and converts every item it finds via
:class:`~.item_converter.ItemConverter`. Also promotes the entity's
``CustomName`` from a JSON-string text component to NBT compound form.

Covered item-bearing fields (any subset may appear depending on entity type):
- Villager-style trades: ``Offers.Recipes[].{buy, buyB, sell}``
- Mob equipment: legacy ``HandItems`` / ``ArmorItems`` positional arrays are
  converted to the 1.21.4+ ``equipment:{slot:item}`` compound; an existing
  ``equipment`` key is preserved and takes priority over the legacy arrays.
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


# Fields known to hold a list of item-stack NBTs (container-style only;
# HandItems/ArmorItems are handled separately and converted to `equipment`).
_ITEM_LIST_FIELDS = ("Inventory", "Items")
# Fields known to hold a single item-stack NBT.
_SINGLE_ITEM_FIELDS = ("Item", "SaddleItem", "ArmorItem", "Body", "Trident")

# Slot-name order for the old positional arrays.  These tuples do double duty:
# drop-chance merging AND equipment slot mapping (the slot names are the same).
_ARMOR_DROP_SLOTS = ("feet", "legs", "chest", "head")
_HAND_DROP_SLOTS = ("mainhand", "offhand")

# ---------------------------------------------------------------------------
# EHP / absorption / resistance rebalancing
# ---------------------------------------------------------------------------
# Minecraft 1.21+ caps the attributes that build effective HP:
#   * minecraft:max_health     -> 1024  (real HP)
#   * minecraft:max_absorption -> 2048  (absorption HP)
# and, crucially, absorption hearts set via ``AbsorptionAmount`` are clamped on
# spawn to the entity's ``max_absorption`` attribute. Legacy mobs that carry e.g.
# ``AbsorptionAmount:700f`` with no ``max_absorption`` attribute therefore lose
# all their absorption (it defaults to ~0), gutting their effective HP.
_EHP_HP_CAP = 1024.0           # max real HP
_EHP_ABSORB_CAP = 2048.0       # max absorption HP
_EHP_BASE_CAP = _EHP_HP_CAP + _EHP_ABSORB_CAP   # 3072 — most EHP without resistance
_EHP_HARD_CAP = 15000.0        # new in-game effective-HP ceiling

# Resistance tiers, lowest → highest. Each is (EHP multiplier, effect amplifier).
# multiplier = 1 / (1 - damage_reduction); amplifier is the NBT level (Res I == 0b).
#   Res I  (0): 20% DR -> 1.25x     Res III (2): 60% DR -> 2.5x
#   Res II (1): 40% DR -> 1.667x    Res IV  (3): 80% DR -> 5x
_RESISTANCE_TIERS = (
    (1.0,        None),  # no resistance — base EHP only
    (1.25,       0),     # Resistance I
    (5.0 / 3.0,  1),     # Resistance II  (1/0.6)
    (2.5,        2),     # Resistance III
    (5.0,        3),     # Resistance IV
)


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
        - ``HandItems:[main,off]`` / ``ArmorItems:[feet,legs,chest,head]`` →
          ``equipment:{mainhand:…,offhand:…,feet:…,…}`` (Minecraft 1.21.4+
          no longer reads the positional arrays from spawner/summon entity NBT)
        - ``equipment:{<slot>:item}`` items routed through Level 1 so
          half-migrated CMD components get their ``item_model`` filled in.
        """
        out: dict = {}
        hand_items = None
        armor_items = None

        for k, v in entity_nbt.items():
            if k == "CustomName":
                out[k] = convert_text_component(v)
            elif k == "Offers":
                out[k] = self._convert_offers(v, f"{ctx}.Offers")
            elif k == "Passengers" and isinstance(v, list):
                out[k] = [self._convert_passenger(p, f"{ctx}.Passengers[{i}]")
                          for i, p in enumerate(v)]
            elif k == "HandItems" and isinstance(v, list):
                hand_items = [self._convert_maybe_item(it, f"{ctx}.HandItems[{i}]")
                              for i, it in enumerate(v)]
            elif k == "ArmorItems" and isinstance(v, list):
                armor_items = [self._convert_maybe_item(it, f"{ctx}.ArmorItems[{i}]")
                               for i, it in enumerate(v)]
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

        # Fold legacy HandItems/ArmorItems into the modern equipment compound.
        # Minecraft 1.21.4+ no longer reads the old positional arrays; slots
        # already present in an existing `equipment` key take priority.
        if hand_items is not None or armor_items is not None:
            equip = out.get("equipment")
            equip = dict(equip) if isinstance(equip, dict) else {}
            if hand_items is not None:
                for slot, item in zip(_HAND_DROP_SLOTS, hand_items):
                    if _looks_like_item(item) and slot not in equip:
                        equip[slot] = item
            if armor_items is not None:
                for slot, item in zip(_ARMOR_DROP_SLOTS, armor_items):
                    if _looks_like_item(item) and slot not in equip:
                        equip[slot] = item
            if equip:
                out["equipment"] = equip

        # Re-fit effective HP into 1.21+ caps: back absorption with a
        # max_absorption attribute, spill over-cap health into absorption, and
        # use Resistance to recover EHP that no longer fits in raw hearts.
        self._apply_ehp_caps(out, ctx)

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

    # ----- EHP / absorption / resistance --------------------------------

    def _apply_ehp_caps(self, out: dict, ctx: str) -> None:
        """Make a mob's effective HP survive the 1.21+ attribute caps.

        Three cases, decided by the entity's max_health attribute (``H``) and
        ``AbsorptionAmount`` (``A``):

        1. *Nothing to do* — no absorption and health within cap. Left untouched
           (this also skips non-living entities, which have neither field).
        2. *Within caps* (``H<=1024`` and ``A<=2048``) — structure is preserved
           verbatim; we only add a ``max_absorption`` attribute equal to ``A`` so
           the absorption hearts aren't clamped away on spawn.
        3. *Over a cap* (``H>1024`` or ``A>2048``) — the mob's canonical EHP
           (``H+A``, clamped to 15000) is re-fit into ``1024`` real HP + absorption,
           applying the lowest Resistance tier whose multiplier keeps the 3072
           base EHP at or above the target. Health/AbsorptionAmount/max_health/
           max_absorption are all rewritten and a Resistance effect is added.
        """
        attrs = out.get("attributes")
        attrs = attrs if isinstance(attrs, list) else None
        H = self._attr_base(attrs, "max_health")
        a_node = out.get("AbsorptionAmount")
        A = float(a_node.value) if isinstance(a_node, Num) else 0.0

        has_absorption = A > 0.0
        over_hp = H is not None and H > _EHP_HP_CAP
        over_absorb = A > _EHP_ABSORB_CAP

        # Case 1 — ordinary mob, nothing to fix (also covers non-living NBT).
        if not has_absorption and not over_hp:
            return

        # Case 2 — within caps: keep everything, just back the absorption.
        if not over_hp and not over_absorb:
            self._set_attr_base(out, "minecraft:max_absorption", A)
            return

        # Case 3 — over a cap: redistribute + Resistance to preserve EHP.
        target = (H if H is not None else 0.0) + A
        capped = min(target, _EHP_HARD_CAP)
        if target > _EHP_HARD_CAP:
            self.warnings.append(
                f"[{ctx}] EHP {target:.0f} exceeds cap; clamped to {_EHP_HARD_CAP:.0f}"
            )

        mult, amplifier = self._pick_resistance(capped)
        base_ehp = capped / mult
        real_hp = round(min(base_ehp, _EHP_HP_CAP), 2)
        absorption = round(base_ehp - real_hp, 2)   # <= 2048 by construction

        self._set_attr_base(out, "minecraft:max_health", real_hp)
        out["Health"] = Num(real_hp, "f")
        out["AbsorptionAmount"] = Num(absorption, "f")
        self._set_attr_base(out, "minecraft:max_absorption", absorption)
        if amplifier is not None:
            self._add_resistance(out, amplifier)

    @staticmethod
    def _pick_resistance(target: float):
        """Lowest ``(multiplier, amplifier)`` tier whose base EHP reaches ``target``."""
        for mult, amplifier in _RESISTANCE_TIERS:
            if target <= _EHP_BASE_CAP * mult + 1e-6:
                return mult, amplifier
        return _RESISTANCE_TIERS[-1]  # Res IV — only reachable above the hard cap

    @staticmethod
    def _attr_base(attrs, suffix: str):
        """Return the ``base`` (as float) of the attribute whose id ends in
        ``suffix`` (e.g. ``"max_health"``), or ``None`` if absent."""
        if not attrs:
            return None
        for a in attrs:
            if not isinstance(a, dict):
                continue
            idn = a.get("id")
            name = idn.value if isinstance(idn, Str) else None
            if name and name.rsplit(":", 1)[-1] == suffix:
                base = a.get("base")
                if isinstance(base, Num):
                    return float(base.value)
        return None

    def _set_attr_base(self, out: dict, attr_id: str, value: float) -> None:
        """Set (or create) the attribute ``attr_id``'s ``base`` to ``value`` (double)."""
        attrs = out.get("attributes")
        if not isinstance(attrs, list):
            attrs = []
            out["attributes"] = attrs
        suffix = attr_id.rsplit(":", 1)[-1]
        new_base = Num(float(value), "d")
        for a in attrs:
            if not isinstance(a, dict):
                continue
            idn = a.get("id")
            name = idn.value if isinstance(idn, Str) else None
            if name and name.rsplit(":", 1)[-1] == suffix:
                a["base"] = new_base
                return
        attrs.append({"id": Str(attr_id, '"'), "base": new_base})

    def _add_resistance(self, out: dict, amplifier: int) -> None:
        """Add an infinite, hidden Resistance effect at ``amplifier`` (Res I == 0).

        Any pre-existing Resistance in ``active_effects`` is replaced; other
        effects are preserved.
        """
        effects = out.get("active_effects")
        new_effects: list = []
        if isinstance(effects, list):
            for e in effects:
                if isinstance(e, dict):
                    idn = e.get("id")
                    name = idn.value if isinstance(idn, Str) else ""
                    if name.rsplit(":", 1)[-1] == "resistance":
                        continue
                new_effects.append(e)
        new_effects.append({
            "id":             Str("minecraft:resistance", '"'),
            "amplifier":      Num(amplifier, "b"),
            # max signed int ticks (~3.4 years) — effectively permanent without
            # relying on the -1 "infinite" sentinel.
            "duration":       Num(2147483647, ""),
            "ambient":        Num(0, "b"),
            "show_particles": Num(0, "b"),   # noParticles
            "show_icon":      Num(0, "b"),
        })
        out["active_effects"] = new_effects

    @staticmethod
    def _merge_drop_chances(out: dict, slots: tuple, values: list) -> None:
        dc = out.setdefault("drop_chances", {})
        for slot, value in zip(slots, values):
            # Pre-1.21: large negative sentinels (e.g. -327.67f) blocked Looting
            # because the check was `rand < chance + looting*0.01` and negatives
            # were always false.  In 1.21+, drop_chances ≤ 0.0f is absolute 0%
            # (Looting does not apply), so 0.0f is the canonical "never drop" value.
            # Negative values may fall outside Minecraft's expected [0, 2] range and
            # default back to 0.085f, which would cause unintended drops.
            raw = float(value.value if hasattr(value, "value") else value)
            dc[slot] = Num(max(0.0, raw), "f")

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
