"""Custom-item model resolution: CMD lookup + nearest-CMD + fuzzy fallback.

1.21+ replaces the old ``CustomModelData`` integer with a
``minecraft:item_model`` component pointing at a JSON file under
``assets/<namespace>/items/`` in the resource pack. There are three ways to
map an old item to the right new model, tried in order:

1. **CMD lookup (deterministic).** The old pack's
   ``assets/minecraft/models/item/<base>.json`` files contain an ``overrides``
   list, each entry mapping ``custom_model_data: N`` to a model path like
   ``"custom/darkpick"``. Look up ``(base_item, N)``, take the filename stem
   (``darkpick``), and use it directly if the new pack has the matching
   ``items/custom/darkpick.json``. This is essentially failure-free as long as
   both packs are in sync.
2. **Nearest-CMD (Minecraft-native fallback).** When the exact CMD is absent
   from the old pack's overrides, or its stem is missing from the new pack,
   find the closest CMD value for the same base item whose stem *does* exist in
   the new pack. Minecraft's own predicate selection uses the largest CMD ≤ the
   item's value, so this tier mirrors that behaviour; it falls back to the
   smallest CMD above the item's value if nothing is ≤.
3. **Fuzzy match (last resort).** When neither CMD tier produces a hit,
   compare the item's display-name text against the new pack's custom filenames.
   Candidates are first restricted by base-item type
   (:data:`BASE_TYPE_KEYWORDS`) to avoid implausible cross-type hits.

Public surface:
- :func:`load_custom_index` — list of stems in the new pack's ``items/custom/``.
- :func:`load_cmd_override_map` — ``(base, cmd) → stem`` from the old pack.
- :class:`CustomModelResolver` — combined resolver (CMD → nearest-CMD → fuzzy).
- :func:`find_custom_model` — low-level fuzzy matcher (used by the resolver).
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Keyword hints used to restrict candidate custom-item filenames per base item.
# Order in each list doesn't matter — any substring hit qualifies the filename.
BASE_TYPE_KEYWORDS: dict[str, list[str]] = {
    "pickaxe":     ["pick"],
    "axe":         ["axe", "hatchet", "cleaver"],
    "hoe":         ["hoe", "sickle", "scythe"],
    "shovel":      ["shov"],
    "sword":       ["sword", "blade", "saber", "katana", "claymore", "rapier",
                    "scim", "khopesh", "machete", "cutlass", "broadsword",
                    "greatsword", "flamberge", "lightsaber", "lash", "fang",
                    "edge", "shank", "deathblade", "felblade"],
    "knife":       ["knife", "dagger", "shank"],
    "helmet":      ["helm", "cap", "hood", "crown"],
    "chestplate":  ["chest", "plate", "tunic", "robe"],
    "leggings":    ["legg", "pants", "skirt", "greaves"],
    "boots":       ["boot", "shoe", "sandals"],
    "ingot":       ["ingot", "bar"],
    "flint":       ["gem", "shard", "crystal", "stone", "pearl", "scale",
                    "coin", "ash", "powder", "rune", "scarab", "ore", "raw",
                    "rock", "orb", "onyx"],
    "magma_cream": ["magma", "cream", "lava"],
    "feather":     ["feather", "wing"],
    "stick":       ["handle", "stick", "rod", "staff", "branch"],
    "wooden_sword": ["handle", "stick"],
    "book":        ["book", "tome", "scroll", "manual"],
}


def load_custom_index(pack_dir) -> list[str]:
    """Return sorted filename stems found in ``<pack_dir>/assets/minecraft/items/custom/``."""
    custom_dir = Path(pack_dir) / "assets" / "minecraft" / "items" / "custom"
    if not custom_dir.is_dir():
        raise FileNotFoundError(f"custom items dir not found: {custom_dir}")
    return sorted(p.stem for p in custom_dir.glob("*.json"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _base_type(item_id: str) -> str | None:
    name = item_id.split(":", 1)[-1]
    for key in sorted(BASE_TYPE_KEYWORDS.keys(), key=len, reverse=True):
        if name == key or name.endswith("_" + key):
            return key
    return None


def find_custom_model(display_text: str, item_id: str, custom_index: list[str]):
    """Pick the best custom-item filename stem for the given display name + item id.

    Returns ``(best_stem, score, restricted_pool_size)``. ``restricted_pool_size``
    is the number of candidates surviving the base-type filter; it's 0 when the
    filter found nothing and the search fell back to the full index.
    """
    if not custom_index:
        return None, 0.0, 0
    base_type = _base_type(item_id)
    candidates: list[str] = []
    if base_type:
        for kw in BASE_TYPE_KEYWORDS.get(base_type, []):
            for fname in custom_index:
                if kw in fname.lower() and fname not in candidates:
                    candidates.append(fname)
    restricted_pool_size = len(candidates)
    if not candidates:
        candidates = custom_index
    target = _norm(display_text)
    best, best_score = None, -1.0
    for fname in candidates:
        score = difflib.SequenceMatcher(None, target, _norm(fname)).ratio()
        if score > best_score:
            best_score = score
            best = fname
    return best, best_score, restricted_pool_size


def load_cmd_override_map(old_pack_dir) -> dict[tuple[str, int], str]:
    """Build the deterministic ``(base_item, cmd) → model_stem`` map from the old pack.

    Walks every ``assets/minecraft/models/item/*.json`` in ``old_pack_dir``,
    parses its ``overrides`` list, and records each
    ``custom_model_data → model`` entry. Model paths like ``"custom/foo"``,
    ``"minecraft:custom/foo"``, or ``"item/custom/foo"`` all yield the stem
    ``"foo"``.

    Returns an empty dict if the directory is missing — callers should treat
    that as "fall back to fuzzy matching".
    """
    out: dict[tuple[str, int], str] = {}
    models_dir = Path(old_pack_dir) / "assets" / "minecraft" / "models" / "item"
    if not models_dir.is_dir():
        return out
    for jpath in sorted(models_dir.glob("*.json")):
        try:
            with open(jpath, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        overrides = doc.get("overrides") or []
        if not isinstance(overrides, list):
            continue
        base = jpath.stem
        for ov in overrides:
            if not isinstance(ov, dict):
                continue
            pred = ov.get("predicate") or {}
            cmd = pred.get("custom_model_data")
            model = ov.get("model")
            if cmd is None or not isinstance(model, str):
                continue
            try:
                cmd_int = int(cmd)
            except (TypeError, ValueError):
                continue
            # "minecraft:custom/foo" / "custom/foo" / "item/custom/foo" → "foo"
            stem = Path(model.split(":")[-1]).stem
            out[(base, cmd_int)] = stem
    return out


@dataclass
class ResolveResult:
    """Outcome of a :meth:`CustomModelResolver.resolve` call.

    Attributes
    ----------
    stem:
        Filename stem in the new pack's ``items/custom/`` (e.g. ``"darkpick"``),
        or ``None`` if even fuzzy matching couldn't produce a candidate.
    source:
        ``"cmd"`` — exact CMD lookup hit;
        ``"nearest-cmd"`` — exact CMD absent or its stem missing from new pack,
        resolved via nearest CMD for the same base item (mirrors Minecraft's own
        predicate selection);
        ``"fuzzy"`` — no CMD info or no CMD coverage for this base item, fell
        back to display-name matching;
        ``"fuzzy-fallback"`` — exact CMD pointed at a stem that doesn't exist in
        the new pack *and* no nearest-CMD candidate was found, fuzzy only.
    score:
        1.0 for ``cmd`` and ``nearest-cmd``; the SequenceMatcher ratio for
        fuzzy variants.
    restricted:
        Whether the fuzzy candidate pool was restricted by base-type keywords.
    note:
        Extra diagnostic context (nearest-CMD distance or fuzzy-fallback reason).
    """

    stem: Optional[str]
    source: str
    score: float
    restricted: bool = False
    note: str = ""


class CustomModelResolver:
    """Two-tier resolver: deterministic CMD lookup first, fuzzy match second.

    Parameters
    ----------
    new_pack_dir:
        Path to the 1.21.11 pack root (contains ``assets/minecraft/items/custom``).
    old_pack_dir:
        Optional path to the 1.20.1 pack root (contains
        ``assets/minecraft/models/item``). When omitted, every lookup falls
        straight through to fuzzy matching.
    """

    def __init__(self, new_pack_dir, old_pack_dir=None):
        self.new_index: list[str] = load_custom_index(new_pack_dir)
        self._new_index_set: set[str] = set(self.new_index)
        self.cmd_map: dict[tuple[str, int], str] = (
            load_cmd_override_map(old_pack_dir) if old_pack_dir else {}
        )
        # Per-base sorted list of (cmd, stem) pairs whose stem exists in the
        # new pack.  Used for nearest-CMD resolution.
        self._cmd_by_base: dict[str, list[tuple[int, str]]] = {}
        for (base, cmd), stem in self.cmd_map.items():
            if stem in self._new_index_set:
                self._cmd_by_base.setdefault(base, []).append((cmd, stem))
        for lst in self._cmd_by_base.values():
            lst.sort()

    def _nearest_cmd_stem(self, base: str, cmd_int: int) -> Optional[tuple[str, int]]:
        """Return ``(stem, matched_cmd)`` for the nearest CMD that maps to a stem
        present in the new pack.

        Prefers the largest CMD ≤ ``cmd_int`` (Minecraft's own predicate
        selection), falling back to the smallest CMD > ``cmd_int`` if none
        exists below.
        """
        candidates = self._cmd_by_base.get(base)
        if not candidates:
            return None
        below = [(cmd, stem) for cmd, stem in candidates if cmd <= cmd_int]
        if below:
            cmd, stem = max(below, key=lambda x: x[0])
            return stem, cmd
        above = [(cmd, stem) for cmd, stem in candidates if cmd > cmd_int]
        if above:
            cmd, stem = min(above, key=lambda x: x[0])
            return stem, cmd
        return None

    def resolve(self, item_id: str, cmd_value, display_text: str) -> ResolveResult:
        """Resolve a (base item, optional CMD, display name) tuple to a new-pack stem.

        ``cmd_value`` may be ``None`` (no CMD on the legacy item), an int, or an
        :class:`~.snbt.Num`. The resolver tolerates anything int-castable.
        """
        cmd_int: Optional[int] = None
        if cmd_value is not None:
            raw = getattr(cmd_value, "value", cmd_value)
            try:
                cmd_int = int(raw)
            except (TypeError, ValueError):
                cmd_int = None

        if cmd_int is not None and self.cmd_map:
            base = item_id.split(":", 1)[-1]
            exact_stem = self.cmd_map.get((base, cmd_int))
            if exact_stem is not None and exact_stem in self._new_index_set:
                return ResolveResult(exact_stem, source="cmd", score=1.0)

            # Exact CMD missing or its stem absent from new pack — try the
            # nearest CMD for this base item that does exist in the new pack.
            nearest = self._nearest_cmd_stem(base, cmd_int)
            if nearest is not None:
                near_stem, near_cmd = nearest
                if exact_stem is None:
                    note = f"CMD {cmd_int} not in old pack; nearest CMD {near_cmd}"
                else:
                    note = (f"CMD {cmd_int} → {exact_stem!r} not in new pack; "
                            f"nearest CMD {near_cmd}")
                return ResolveResult(
                    near_stem, source="nearest-cmd", score=1.0, note=note
                )

            # No CMD-based candidate at all — fall through to fuzzy, but flag
            # if we had an exact hit that just wasn't ported to the new pack.
            if exact_stem is not None:
                best, score, restricted = find_custom_model(
                    display_text, item_id, self.new_index
                )
                return ResolveResult(
                    best,
                    source="fuzzy-fallback",
                    score=score,
                    restricted=bool(restricted),
                    note=f"CMD {cmd_int} → {exact_stem!r} not present in new pack",
                )

        best, score, restricted = find_custom_model(display_text, item_id, self.new_index)
        return ResolveResult(
            best, source="fuzzy", score=score, restricted=bool(restricted)
        )
