"""Text-component helpers.

Pre-1.20.5 mcfunctions stored display names and lore as JSON strings:
``'{"text":"Foo","color":"red","bold":true}'``. From 1.21.5+ the game expects
text components in native SNBT form (NBT compound) with boolean fields as
NBT bytes (``1b``/``0b``). This module bridges the two representations.

Public surface:
- :func:`convert_text_component` — Convert a single SNBT ``Str`` whose value is
  JSON text (or any other node) into an NBT-compound text component.
- :func:`convert_lore_list` — Apply :func:`convert_text_component` to every entry
  of an old-style lore list.
- :func:`extract_plain_text` — Best-effort flatten of a text component down to
  its user-visible text, for fuzzy matching against custom-item filenames.
"""

from __future__ import annotations

import json
import re

from .snbt import Num, Str


_TEXT_BOOL_KEYS = {"bold", "italic", "underlined", "strikethrough", "obfuscated"}

# 1.21.5+: camelCase event keys were renamed to snake_case
_COMPONENT_KEY_RENAMES: dict[str, str] = {
    "clickEvent": "click_event",
    "hoverEvent": "hover_event",
}

# Within a click_event compound, the "value" sub-key is renamed based on the action
_CLICK_VALUE_RENAMES: dict[str, str] = {
    "run_command": "command",
    "suggest_command": "command",
    "open_url": "url",
}


def _convert_click_event_dict(event: dict) -> dict:
    """Rename click_event sub-keys per 1.21.5+ spec (value→command/url)."""
    action = event.get("action", "")
    value_key = _CLICK_VALUE_RENAMES.get(action, "value")
    return {
        (value_key if k == "value" else k): _json_obj_to_snbt(v)
        for k, v in event.items()
    }


def _json_obj_to_snbt(node):
    """Convert a parsed JSON value into the corresponding SNBT node tree.

    Boolean style flags become NBT bytes; numbers become Num; strings become Str.
    Event keys are renamed from camelCase to snake_case (1.21.5+).
    """
    if isinstance(node, bool):
        return Num(1 if node else 0, "b")
    if isinstance(node, int):
        return Num(node, "")
    if isinstance(node, float):
        return Num(node, "d")
    if isinstance(node, str):
        return Str(node, '"')
    if isinstance(node, list):
        return [_json_obj_to_snbt(x) for x in node]
    if isinstance(node, dict):
        out: dict = {}
        for k, v in node.items():
            new_key = _COMPONENT_KEY_RENAMES.get(k, k)
            if k in ("clickEvent", "click_event") and isinstance(v, dict):
                out[new_key] = _convert_click_event_dict(v)
            elif k in _TEXT_BOOL_KEYS and isinstance(v, bool):
                out[new_key] = Num(1 if v else 0, "b")
            else:
                out[new_key] = _json_obj_to_snbt(v)
        return out
    if node is None:
        return Str("", '"')
    raise ValueError(f"unhandled JSON node: {node!r}")


def convert_text_component(node):
    """Promote a JSON-string text component to its NBT-compound form.

    If ``node`` is an SNBT ``Str`` whose value looks like JSON (starts with ``{``
    or ``[``), parse it and re-emit as SNBT. Anything else is returned unchanged.
    """
    if isinstance(node, Str):
        raw = node.value.strip()
        if raw.startswith("{") or raw.startswith("["):
            try:
                return _json_obj_to_snbt(json.loads(raw))
            except json.JSONDecodeError:
                return node
    return node


def convert_lore_list(lore: list) -> list:
    """Apply :func:`convert_text_component` to every entry of a lore list."""
    return [convert_text_component(x) for x in lore]


def extract_plain_text(node) -> str:
    """Return the user-visible text of a text-component node (best effort)."""
    if isinstance(node, Str):
        raw = node.value
        m = re.search(r'"text"\s*:\s*"([^"]*)"', raw)
        if m:
            return m.group(1)
        return raw
    if isinstance(node, dict):
        t = node.get("text")
        if isinstance(t, Str):
            return t.value
        if isinstance(t, str):
            return t
    return ""
