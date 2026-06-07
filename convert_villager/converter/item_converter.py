"""Level 1: ItemConverter — single-item data conversion.

Converts a single item's legacy NBT (``{id, Count, tag}``) into the modern
1.21.11 component representation (``{id, count, components}``), and emits the
``[component=value,…]`` form needed by the ``/give`` command syntax.

The converter handles every standard item-tag field:
- ``display.Name`` / ``display.Lore`` → ``minecraft:custom_name`` / ``minecraft:lore``
- ``Unbreakable`` → ``minecraft:unbreakable``
- ``CustomModelData`` → **dropped**, replaced with ``minecraft:item_model`` chosen
  by fuzzy-matching the display name against the resource-pack's custom items
- ``Enchantments`` → ``minecraft:enchantments`` (flat id→level map, no ``levels:`` wrapper)
- ``AttributeModifiers`` → ``minecraft:attribute_modifiers``
  (operation codes translated, UUIDs dropped, synthetic ``id`` generated)
- ``CanDestroy`` → ``minecraft:can_break``
- ``HideFlags`` → ``minecraft:tooltip_display`` (``hidden_components``)

Non-standard fields (notably ``EntityTag`` on spawn eggs) are NOT handled here:
the caller — typically an implementor or :class:`~.entity_converter.EntityConverter`
— is responsible for splitting them off and routing them to the right level.
This keeps Level 1 self-contained.
"""

from __future__ import annotations

from .custom_models import CustomModelResolver
from .snbt import Num, Str, snbt_dump
from .text_components import convert_lore_list, convert_text_component, extract_plain_text


ATTRIBUTE_OPERATIONS = {0: "add_value", 1: "add_multiplied_base", 2: "add_multiplied_total"}

# Legacy / non-canonical enchantment IDs the source data has been observed to
# use. Map them to the official 1.21 IDs so the resulting /give command
# parses. Anything not here is passed through as-is — if the game rejects it,
# add the rename here.
LEGACY_ENCHANT_RENAMES = {
    "minecraft:sweeping":   "minecraft:sweeping_edge",
    "minecraft:oxygen":     "minecraft:respiration",
    "minecraft:waterworker": "minecraft:aqua_affinity",
}

HIDE_FLAGS_BITS: list[tuple[int, str]] = [
    (1,   "minecraft:enchantments"),
    (2,   "minecraft:attribute_modifiers"),
    (4,   "minecraft:unbreakable"),
    (8,   "minecraft:can_break"),
    (16,  "minecraft:can_place_on"),
    (32,  "minecraft:stored_enchantments"),
    (64,  "minecraft:dyed_color"),
    (128, "minecraft:trim"),
]


def _normalize_attribute_name(raw: str) -> str:
    """``generic.attack_damage`` → ``minecraft:attack_damage``."""
    name = raw
    if "." in name and ":" not in name:
        name = name.split(".", 1)[1]
    if ":" not in name:
        name = "minecraft:" + name
    return name


class ItemConverter:
    """Converts a single item's legacy tag block to the new component format.

    Parameters
    ----------
    resolver:
        :class:`~.custom_models.CustomModelResolver` that translates each
        legacy ``CustomModelData`` integer to a filename stem in the new
        resource pack. Falls back to fuzzy name matching when the CMD isn't
        in the old pack's overrides.
    threshold:
        Score below which fuzzy matches log a low-confidence warning. Doesn't
        affect deterministic CMD hits, which always succeed silently.
    warnings:
        Mutable list the converter appends free-text diagnostics to.
    """

    # Standard fields recognized by :meth:`convert_tag_to_components`. The
    # implementor for spawn-eggs strips ``EntityTag`` out before calling us,
    # so it isn't listed here.
    KNOWN_TAG_FIELDS = frozenset({
        "display", "Unbreakable", "CustomModelData", "Enchantments",
        "AttributeModifiers", "CanDestroy", "HideFlags", "Trim", "SkullOwner",
    })

    def __init__(self, resolver: CustomModelResolver, threshold: float, warnings: list[str]):
        self.resolver = resolver
        self.threshold = threshold
        self.warnings = warnings

    # ----- public API ----------------------------------------------------

    def convert_tag_to_components(self, tag: dict, item_id: str, ctx: str) -> dict:
        """Convert an old ``tag`` block into a sorted components dict.

        Unknown fields are silently ignored — the caller can preprocess to
        handle them.
        """
        comps: dict = {}
        display_text_label = ""

        display = tag.get("display")
        if isinstance(display, dict):
            name = display.get("Name")
            if name is not None:
                comps["minecraft:custom_name"] = convert_text_component(name)
                display_text_label = extract_plain_text(name)
            lore = display.get("Lore")
            if isinstance(lore, list) and lore:
                comps["minecraft:lore"] = convert_lore_list(lore)
            # Dyed leather (and similar): `display:{color:N}` → minecraft:dyed_color=N
            color = display.get("color")
            if isinstance(color, Num):
                comps["minecraft:dyed_color"] = Num(int(color.value), "")

        unbreak = tag.get("Unbreakable")
        if isinstance(unbreak, Num) and unbreak.value:
            comps["minecraft:unbreakable"] = {}

        cmd_node = tag.get("CustomModelData")
        if cmd_node is not None:
            self._apply_item_model(comps, display_text_label, item_id, cmd_node, ctx)

        enchants = tag.get("Enchantments")
        if isinstance(enchants, list):
            self._apply_enchantments(comps, enchants)

        attrs = tag.get("AttributeModifiers")
        if isinstance(attrs, list):
            self._apply_attribute_modifiers(comps, attrs)

        can_destroy = tag.get("CanDestroy")
        if isinstance(can_destroy, list) and can_destroy:
            comps["minecraft:can_break"] = {"blocks": can_destroy}

        trim = tag.get("Trim")
        if isinstance(trim, dict) and trim:
            # Old `Trim:{material, pattern}` has the same inner shape as the
            # new `minecraft:trim` component — just promote it.
            comps["minecraft:trim"] = trim

        skull_owner = tag.get("SkullOwner")
        if isinstance(skull_owner, dict):
            profile = self._build_profile(skull_owner)
            if profile:
                comps["minecraft:profile"] = profile

        hide_flags = tag.get("HideFlags")
        if isinstance(hide_flags, Num) and hide_flags.value:
            bits = int(hide_flags.value)
            hidden = [Str(n, '"') for bit, n in HIDE_FLAGS_BITS if bits & bit]
            if hidden:
                comps["minecraft:tooltip_display"] = {"hidden_components": hidden}

        # Any remaining unknown keys are custom item data (e.g. rune1:1b,
        # boot1:1b) — preserve them in minecraft:custom_data so that
        # selector-based nbt= checks can find them.
        custom_data = {k: v for k, v in tag.items() if k not in self.KNOWN_TAG_FIELDS}
        if custom_data:
            comps["minecraft:custom_data"] = custom_data

        return dict(sorted(comps.items()))

    def convert_item_nbt(self, item_dict: dict, ctx: str) -> dict:
        """Bring any item-stack NBT to 1.21.11 format.

        Three input shapes handled:

        1. **Legacy** (``{id, Count, tag}``) — full conversion to
           ``{id, count, components}``.
        2. **Half-migrated** (``{id, count, components}`` carrying a
           ``minecraft:custom_model_data`` but no ``minecraft:item_model``) —
           resolve the CMD integer via the old pack and add ``item_model``,
           leaving everything else intact. ``Slot`` and other container
           metadata round-trip cleanly.
        3. **Fully modern** — passed through unchanged.
        """
        if ("Count" in item_dict) or ("tag" in item_dict):
            return self._convert_legacy_item(item_dict, ctx)
        return self._upgrade_modern_item(item_dict, ctx)

    def _convert_legacy_item(self, item_dict: dict, ctx: str) -> dict:
        new_item: dict = {}
        id_node = item_dict.get("id")
        item_id = id_node.value if isinstance(id_node, Str) else "minecraft:unknown"
        new_item["id"] = id_node if id_node is not None else Str(item_id, '"')

        count_node = item_dict.get("Count")
        if isinstance(count_node, Num):
            new_item["count"] = Num(int(count_node.value), "")
        else:
            new_item["count"] = Num(1, "")

        # Preserve container-position metadata if the caller stored an item
        # alongside other slot-keyed entries (chest, hopper, inventory, …).
        if "Slot" in item_dict:
            new_item["Slot"] = item_dict["Slot"]

        tag = item_dict.get("tag")
        if isinstance(tag, dict):
            comps = self.convert_tag_to_components(tag, item_id, ctx)
            if comps:
                new_item["components"] = comps
        return new_item

    def _upgrade_modern_item(self, item_dict: dict, ctx: str) -> dict:
        """Add ``minecraft:item_model`` from a half-migrated CMD component.

        The auto-port from 1.20→1.21 wraps the legacy integer CMD into
        ``custom_model_data={floats:[N.0f]}`` but doesn't pick a model path
        (that needs resource-pack knowledge). We have the pack's overrides
        loaded, so we can finish the job.
        """
        components = item_dict.get("components")
        if not isinstance(components, dict):
            return item_dict
        cmd_comp = components.get("minecraft:custom_model_data")
        if cmd_comp is None or "minecraft:item_model" in components:
            return item_dict

        cmd_int = None
        if isinstance(cmd_comp, dict):
            floats = cmd_comp.get("floats")
            if isinstance(floats, list) and floats:
                first = floats[0]
                raw = first.value if hasattr(first, "value") else first
                try:
                    cmd_int = int(raw)
                except (TypeError, ValueError):
                    cmd_int = None
        if cmd_int is None:
            return item_dict

        id_node = item_dict.get("id")
        if not isinstance(id_node, Str):
            return item_dict
        item_id = id_node.value

        display_text = ""
        name_comp = components.get("minecraft:custom_name")
        if isinstance(name_comp, dict):
            t = name_comp.get("text")
            if isinstance(t, Str):
                display_text = t.value

        new_components = dict(components)
        self._apply_item_model(new_components, display_text, item_id, cmd_int, ctx)
        if "minecraft:item_model" not in new_components:
            return item_dict

        new_components = dict(sorted(new_components.items()))
        new_item = dict(item_dict)
        new_item["components"] = new_components
        return new_item

    @staticmethod
    def render_components_bracket(comps: dict) -> str:
        """Render a components dict as ``[k=v,…]`` for ``/give`` command syntax."""
        if not comps:
            return ""
        parts = [f"{cid}={snbt_dump(comps[cid])}" for cid in sorted(comps.keys())]
        return "[" + ",".join(parts) + "]"

    # ----- internal helpers ---------------------------------------------

    def _apply_item_model(self, comps: dict, display_text: str, item_id: str,
                          cmd_value, ctx: str):
        result = self.resolver.resolve(item_id, cmd_value, display_text)
        if result.stem is None:
            self.warnings.append(
                f"[{ctx}] no custom-model candidate for '{display_text}' "
                f"(id={item_id}, cmd={getattr(cmd_value, 'value', cmd_value)})"
            )
            return
        comps["minecraft:item_model"] = Str(f"minecraft:custom/{result.stem}", '"')

        # Deterministic CMD hits don't get a warning. Everything else does:
        # nearest-cmd always (approximation); fuzzy-fallback always (missing
        # asset); pure fuzzy only when below the confidence threshold.
        if result.source == "cmd":
            return
        cmd_repr = getattr(cmd_value, "value", cmd_value)
        if result.source == "nearest-cmd":
            self.warnings.append(
                f"[{ctx}] {result.note} -> {result.stem} "
                f"(id={item_id}, cmd={cmd_repr})"
            )
        elif result.source == "fuzzy-fallback":
            self.warnings.append(
                f"[{ctx}] {result.note}; fuzzy fallback for '{display_text}' "
                f"(id={item_id}, cmd={cmd_repr}) -> {result.stem} "
                f"(score={result.score:.2f})"
            )
        elif result.score < self.threshold:
            pool = "restricted" if result.restricted else "full"
            self.warnings.append(
                f"[{ctx}] low-confidence custom-model match "
                f"'{display_text}' (id={item_id}, cmd={cmd_repr}) -> {result.stem} "
                f"(score={result.score:.2f}, pool={pool})"
            )

    @staticmethod
    def _build_profile(skull_owner: dict):
        """Legacy ``SkullOwner`` → modern ``minecraft:profile`` compound.

        Old shape::
            {Id:[I;…], Name:?, Properties:{textures:[{Value:"<b64>", Signature:?}]}}

        New shape::
            {id:[I;…], name:?, properties:[{name:"textures", value:"<b64>", signature:?}]}

        Note the casing flip: ``Properties`` / ``Value`` / ``Signature`` are
        uppercase legacy; ``properties`` / ``value`` / ``signature`` are
        lowercase modern, plus a ``name:"textures"`` discriminator is added
        because the modern property list is generic (not implicitly textures).
        """
        out: dict = {}
        sid = skull_owner.get("Id")
        if sid is not None:
            out["id"] = sid
        name = skull_owner.get("Name")
        if isinstance(name, Str):
            out["name"] = name
        props = skull_owner.get("Properties")
        if isinstance(props, dict):
            textures = props.get("textures")
            if isinstance(textures, list):
                new_props: list = []
                for tex in textures:
                    if not isinstance(tex, dict):
                        continue
                    entry: dict = {"name": Str("textures", '"')}
                    value = tex.get("Value")
                    if isinstance(value, Str):
                        entry["value"] = value
                    sig = tex.get("Signature")
                    if isinstance(sig, Str):
                        entry["signature"] = sig
                    if "value" in entry:
                        new_props.append(entry)
                if new_props:
                    out["properties"] = new_props
        return out or None

    @staticmethod
    def _apply_enchantments(comps: dict, enchants: list):
        levels: dict = {}
        for e in enchants:
            if not isinstance(e, dict):
                continue
            eid = e.get("id")
            lvl = e.get("lvl")
            if isinstance(eid, Str) and isinstance(lvl, Num):
                ench_id = LEGACY_ENCHANT_RENAMES.get(eid.value, eid.value)
                levels[ench_id] = Num(int(lvl.value), "")
        if levels:
            # 1.21.5+: flat id->level map (no `levels:` wrapper)
            comps["minecraft:enchantments"] = levels

    @staticmethod
    def _apply_attribute_modifiers(comps: dict, attrs: list):
        modifiers: list = []
        for idx, a in enumerate(attrs):
            if not isinstance(a, dict):
                continue
            attr_node = a.get("AttributeName")
            if not isinstance(attr_node, Str):
                continue
            attr_full = _normalize_attribute_name(attr_node.value)
            attr_path = attr_full.split(":", 1)[-1]
            amount_node = a.get("Amount")
            amount = amount_node.value if isinstance(amount_node, Num) else 0
            op_node = a.get("Operation")
            op_int = int(op_node.value) if isinstance(op_node, Num) else 0
            op_str = ATTRIBUTE_OPERATIONS.get(op_int, "add_value")
            slot_node = a.get("Slot")
            slot = slot_node.value if isinstance(slot_node, Str) else "mainhand"
            modifiers.append({
                "type":      Str(attr_full, '"'),
                "amount":    Num(float(amount), "d"),
                "operation": Str(op_str, '"'),
                "slot":      Str(slot, '"'),
                "id":        Str(f"converted:{slot}_{attr_path}_{idx}", '"'),
            })
        if modifiers:
            comps["minecraft:attribute_modifiers"] = modifiers
