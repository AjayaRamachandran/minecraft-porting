"""Implementor: execute commands with legacy nbt= selector patterns.

Transforms ``tag:{…}`` item-NBT checks in selector arguments from the
pre-1.20.5 ``tag`` field to the modern ``components`` structure, and handles
other legacy patterns that appear in the run-clause of execute commands.

Patterns handled:
- ``tag:{SIMPLE_FLAG:1b}``       → ``components:{"minecraft:custom_data":{SIMPLE_FLAG:1b}}``
- ``tag:{CustomModelData:N}``    → ``components:{"minecraft:item_model":"minecraft:custom/STEM"}``
  (model name resolved from old pack, same as item_converter — CMD is never preserved)
- ``tag:{display:{Name:'JSON'}}``→ ``components:{"minecraft:custom_name":{…snbt…}}``
- ``Count:1b`` removed from SelectedItem checks (field renamed to ``count`` in 1.20.5+)
- ``ActiveEffects:[{Id:N,Amplifier:Mb}]`` → ``active_effects:[{id:"minecraft:EFFECT",amplifier:Mb}]``
- ``run clear <target> <item>{CustomModelData:N}`` → bracket item_model form
- ``run clear <target> <item>{FLAG:1b}``           → bracket custom_data form
"""

from __future__ import annotations

import re
from typing import Optional

from ..snbt import Str, snbt_dump
from ..text_components import convert_text_component


# Numeric effect ID → modern string id (Java Edition 1.20.4 registry order).
LEGACY_EFFECT_IDS: dict[int, str] = {
    1:  "minecraft:speed",
    2:  "minecraft:slowness",
    3:  "minecraft:haste",
    4:  "minecraft:mining_fatigue",
    5:  "minecraft:strength",
    6:  "minecraft:instant_health",
    7:  "minecraft:instant_damage",
    8:  "minecraft:jump_boost",
    9:  "minecraft:nausea",
    10: "minecraft:regeneration",
    11: "minecraft:resistance",
    12: "minecraft:fire_resistance",
    13: "minecraft:water_breathing",
    14: "minecraft:invisibility",
    15: "minecraft:blindness",
    16: "minecraft:night_vision",
    17: "minecraft:hunger",
    18: "minecraft:weakness",
    19: "minecraft:poison",
    20: "minecraft:wither",
    21: "minecraft:health_boost",
    22: "minecraft:absorption",
    23: "minecraft:saturation",
    24: "minecraft:glowing",
    25: "minecraft:levitation",
    26: "minecraft:luck",
    27: "minecraft:unluck",
    28: "minecraft:slow_falling",
    29: "minecraft:conduit_power",
    30: "minecraft:dolphins_grace",
    31: "minecraft:bad_omen",
    32: "minecraft:hero_of_the_village",
    33: "minecraft:darkness",
}


def _json_to_snbt(json_str: str) -> str:
    """Convert a JSON text-component string to its SNBT compound form."""
    converted = convert_text_component(Str(json_str, "'"))
    return snbt_dump(converted)


_DISPLAY_NAME_RE = re.compile(r"tag:\{display:\{Name:'([^']+)'\}\}")
_CMD_RE = re.compile(r"tag:\{CustomModelData:(\d+)\}")
_FLAG_RE = re.compile(r"tag:\{([a-zA-Z0-9_]+):1b\}")
# Handles both "Count:1b," (middle) and ",Count:1b" (end before closing brace).
_COUNT_RE = re.compile(r"Count:1b,\s*|,\s*Count:1b\b")

_ACTIVE_EFFECTS_RE = re.compile(
    r'ActiveEffects:\[\s*\{\s*Id\s*:\s*(\d+)\s*,\s*Amplifier\s*:\s*(\d+b)\s*\}\s*\]'
)

# clear <target> <item>{CustomModelData:N}  (optionally prefixed by "run ")
_CLEAR_CMD_TAG_RE = re.compile(
    r'((?:run\s+)?/?clear\s+\S+\s+[a-zA-Z0-9:_]+)\{CustomModelData:(\d+)\}'
)
# clear <target> <item>{FLAG:1b}
_CLEAR_FLAG_TAG_RE = re.compile(
    r'((?:run\s+)?/?clear\s+\S+\s+[a-zA-Z0-9:_]+)\{([a-zA-Z0-9_]+):1b\}'
)


def _replace_cmd_in_selector(cmd_str: str, pipeline) -> str:
    """Replace tag:{CustomModelData:N} with item_model component.

    Looks backward from each match to find the enclosing item's ``id:`` field,
    then resolves the CMD via the old pack — the same path item_converter uses.
    CMD integers are never preserved in output; if resolution fails the
    command gets a warning and the floats fallback is used.
    """
    parts: list[str] = []
    last = 0
    for m in _CMD_RE.finditer(cmd_str):
        prefix = cmd_str[:m.start()]
        id_match = re.search(r'id:"([^"]+)"', prefix)
        item_id = id_match.group(1) if id_match else ""
        cmd_n = int(m.group(1))
        result = pipeline.resolver.resolve(item_id, cmd_n, "")
        if result.stem:
            rep = f'components:{{"minecraft:item_model":"minecraft:custom/{result.stem}"}}'
        else:
            pipeline.warnings.append(
                f"[execute/selector] no model for item={item_id!r} cmd={cmd_n}"
            )
            rep = f'components:{{"minecraft:custom_model_data":{{floats:[{cmd_n}.0f]}}}}'
        parts.append(cmd_str[last:m.start()])
        parts.append(rep)
        last = m.end()
    parts.append(cmd_str[last:])
    return "".join(parts)


def _replace_cmd_in_clear(cmd_str: str, pipeline) -> str:
    """Replace item{CustomModelData:N} in clear commands with bracket item_model form."""
    parts: list[str] = []
    last = 0
    for m in _CLEAR_CMD_TAG_RE.finditer(cmd_str):
        clear_prefix = m.group(1)
        item_match = re.search(r'([a-zA-Z0-9:_]+)$', clear_prefix)
        item_raw = item_match.group(1) if item_match else ""
        item_id = item_raw if ":" in item_raw else f"minecraft:{item_raw}"
        cmd_n = int(m.group(2))
        result = pipeline.resolver.resolve(item_id, cmd_n, "")
        if result.stem:
            rep = f'{clear_prefix}[minecraft:item_model="minecraft:custom/{result.stem}"]'
        else:
            pipeline.warnings.append(
                f"[execute/clear] no model for item={item_id!r} cmd={cmd_n}"
            )
            rep = f'{clear_prefix}[minecraft:custom_model_data={{floats:[{cmd_n}.0f]}}]'
        parts.append(cmd_str[last:m.start()])
        parts.append(rep)
        last = m.end()
    parts.append(cmd_str[last:])
    return "".join(parts)


def _transform_nbt_selector(cmd: str, pipeline) -> str:
    """Apply all legacy transforms to a command string."""

    # 1. tag:{display:{Name:'JSON'}} → custom_name component (most specific first)
    def _replace_display(m: re.Match) -> str:
        snbt = _json_to_snbt(m.group(1))
        return f'components:{{"minecraft:custom_name":{snbt}}}'

    cmd = _DISPLAY_NAME_RE.sub(_replace_display, cmd)

    # 2. tag:{CustomModelData:N} → item_model component (resolved, not raw floats)
    cmd = _replace_cmd_in_selector(cmd, pipeline)

    # 3. tag:{SIMPLE_FLAG:1b} → custom_data component
    cmd = _FLAG_RE.sub(
        r'components:{"minecraft:custom_data":{\1:1b}}',
        cmd,
    )

    # 4. Remove Count:1b (renamed to lowercase count in 1.20.5+)
    cmd = _COUNT_RE.sub("", cmd)

    # 5. ActiveEffects:[{Id:N,Amplifier:Mb}] → active_effects with string id
    def _replace_active_effects(m: re.Match) -> str:
        eid = int(m.group(1))
        effect = LEGACY_EFFECT_IDS.get(eid, f"minecraft:effect_{eid}")
        amp = m.group(2)
        return f'active_effects:[{{id:"{effect}",amplifier:{amp}}}]'

    cmd = _ACTIVE_EFFECTS_RE.sub(_replace_active_effects, cmd)

    # 6. clear <target> <item>{CustomModelData:N} → bracket item_model form
    cmd = _replace_cmd_in_clear(cmd, pipeline)

    # 7. clear <target> <item>{FLAG:1b} → bracket custom_data form
    cmd = _CLEAR_FLAG_TAG_RE.sub(
        r'\1[minecraft:custom_data={\2:1b}]',
        cmd,
    )

    return cmd


def try_convert_line(line: str, pipeline) -> Optional[str]:
    """Return rewritten execute command if it contains legacy patterns."""
    stripped = line.strip()
    if not re.match(r"^/?execute\b", stripped, re.IGNORECASE):
        return None
    transformed = _transform_nbt_selector(stripped, pipeline)
    if transformed == stripped:
        return None
    return transformed
