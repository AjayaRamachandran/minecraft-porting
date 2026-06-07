"""Shared utilities for line-level command implementors.

The give / villager / summon implementors all need to:
1. Match a line against a command signature.
2. Pull a top-level ``{…}`` SNBT block out of the remainder while respecting
   nested braces inside single- and double-quoted strings.

Those steps live here so each implementor stays focused on the mapping logic
rather than re-implementing string parsing.
"""

from __future__ import annotations

import re
from typing import Optional


# Matches the prefix `/?give <target> [minecraft:]<item>` followed by anything.
# Use this for both generic /give and the villager spawn-egg case — the
# implementor inspects the captured `item` group to decide if it should claim
# the line.
GIVE_RE = re.compile(
    r"^(?P<lead>/?)\s*(?P<cmd>give)\s+(?P<target>\S+)\s+"
    r"(?:minecraft:)?(?P<item>[a-z0-9_./]+)\b(?P<rest>.*)$",
    re.IGNORECASE,
)

# Matches `/?summon <entity_id> [<pos>]` followed by optional NBT.
# The entity id, position, and rest are captured separately; the rest may or
# may not begin with a `{`.
SUMMON_RE = re.compile(
    r"^(?P<lead>/?)\s*(?P<cmd>summon)\s+(?:minecraft:)?(?P<entity>[a-z0-9_./]+)"
    r"(?:\s+(?P<pos>\S+\s+\S+\s+\S+))?(?P<rest>.*)$",
    re.IGNORECASE,
)


def split_top_level_nbt(rest: str) -> tuple[Optional[str], str]:
    """Pull a top-level ``{…}`` SNBT block off the front of ``rest``.

    Skips quoted strings so a ``{`` inside ``'{"text":"…"}'`` doesn't confuse
    brace tracking. Returns ``(nbt_text, trailing)`` where ``nbt_text`` is the
    full ``{…}`` substring (or ``None`` if ``rest`` doesn't start with a
    compound after optional leading whitespace) and ``trailing`` is everything
    that came after it (typically the ``/give`` count or empty).
    """
    s = rest.lstrip()
    leading_ws = rest[:len(rest) - len(s)]
    if not s.startswith("{"):
        return None, leading_ws + s

    depth = 0
    in_str: Optional[str] = None
    i = 0
    while i < len(s):
        c = s[i]
        if in_str is not None:
            if c == "\\":
                i += 2  # skip escaped char
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c == '"' or c == "'":
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[:i + 1], s[i + 1:]
        i += 1
    raise ValueError("unmatched braces in NBT block")
