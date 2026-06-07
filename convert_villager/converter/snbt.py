"""SNBT (Stringified NBT) parser and writer.

Used by every level of the converter. Keeps Minecraft's typed-number suffixes
(`1b`, `5s`, `0.7d`), typed int/byte/long arrays (`[I;…]`), and the two string
quote styles (single vs double) intact through a parse/edit/dump round-trip.

Public surface:
- Node types:   ``Num``, ``Str``, ``TypedArr``
- Parsing:      ``snbt_parse(src) -> node``
- Serializing:  ``snbt_dump(node) -> str``

The parser produces plain ``dict`` and ``list`` for compounds and untyped lists
so callers can mutate them naturally; numbers, strings, and typed arrays are
wrapped in the classes above to preserve type information.
"""

from __future__ import annotations

import re


class Num:
    """An NBT scalar number with an explicit type suffix.

    ``suffix`` is one of '', 'b', 's', 'l', 'f', 'd' (empty = int).
    """

    __slots__ = ("value", "suffix")

    def __init__(self, value, suffix: str = ""):
        self.value = value
        self.suffix = suffix

    def __repr__(self) -> str:
        return f"Num({self.value!r},{self.suffix!r})"


class Str:
    """An NBT string preserving its source quote style ('"', "'", or '' for bare)."""

    __slots__ = ("value", "quote")

    def __init__(self, value: str, quote: str = '"'):
        self.value = value
        self.quote = quote

    def __repr__(self) -> str:
        return f"Str({self.value!r},{self.quote!r})"


class TypedArr:
    """A typed NBT array — ``[B;…]``, ``[I;…]``, or ``[L;…]``."""

    __slots__ = ("kind", "items")

    def __init__(self, kind: str, items: list):
        self.kind = kind
        self.items = items

    def __repr__(self) -> str:
        return f"TypedArr({self.kind!r},{self.items!r})"


_KEY_RE = re.compile(r"[A-Za-z0-9_.\-+]+")
_NUM_RE = re.compile(r"(-?\d*\.?\d+(?:[eE][+-]?\d+)?)([bBsSlLfFdD])?")


class _Parser:
    def __init__(self, src: str):
        self.src = src
        self.i = 0

    def _err(self, msg: str):
        ctx_a = self.src[max(0, self.i - 30):self.i]
        ctx_b = self.src[self.i:self.i + 30]
        raise ValueError(f"SNBT parse error at {self.i}: {msg}\n  ...{ctx_a}<HERE>{ctx_b}...")

    def _peek(self, n: int = 0) -> str:
        j = self.i + n
        return self.src[j] if j < len(self.src) else ""

    def _ws(self):
        while self.i < len(self.src) and self.src[self.i] in " \t\r\n":
            self.i += 1

    def parse(self):
        self._ws()
        c = self._peek()
        if c == "{":
            return self._compound()
        if c == "[":
            return self._array()
        if c == '"' or c == "'":
            return self._string()
        return self._literal()

    def _compound(self) -> dict:
        self.i += 1
        out: dict = {}
        self._ws()
        if self._peek() == "}":
            self.i += 1
            return out
        while True:
            self._ws()
            key = self._key()
            self._ws()
            if self._peek() != ":":
                self._err("expected ':' after key")
            self.i += 1
            out[key] = self.parse()
            self._ws()
            c = self._peek()
            if c == ",":
                self.i += 1
                continue
            if c == "}":
                self.i += 1
                return out
            self._err("expected ',' or '}'")

    def _key(self) -> str:
        if self._peek() in ('"', "'"):
            return self._string().value
        m = _KEY_RE.match(self.src, self.i)
        if not m:
            self._err("expected key")
        self.i = m.end()
        return m.group(0)

    def _array(self):
        self.i += 1
        if self._peek() in "BIL" and self._peek(1) == ";":
            kind = self._peek()
            self.i += 2
            items: list = []
            self._ws()
            if self._peek() == "]":
                self.i += 1
                return TypedArr(kind, items)
            while True:
                self._ws()
                items.append(self.parse())
                self._ws()
                c = self._peek()
                if c == ",":
                    self.i += 1
                    continue
                if c == "]":
                    self.i += 1
                    return TypedArr(kind, items)
                self._err("expected ',' or ']' in typed array")
        items = []
        self._ws()
        if self._peek() == "]":
            self.i += 1
            return items
        while True:
            self._ws()
            items.append(self.parse())
            self._ws()
            c = self._peek()
            if c == ",":
                self.i += 1
                continue
            if c == "]":
                self.i += 1
                return items
            self._err("expected ',' or ']' in list")

    def _string(self) -> Str:
        quote = self.src[self.i]
        self.i += 1
        buf: list[str] = []
        while self.i < len(self.src):
            c = self.src[self.i]
            if c == "\\":
                self.i += 1
                if self.i >= len(self.src):
                    self._err("unterminated escape in string")
                nxt = self.src[self.i]
                # Interpret SNBT/JSON-style escapes so the stored value is the
                # actual logical content. snbt_dump re-escapes on the way out
                # to keep the round-trip clean. Without this, JSON-encoded
                # text components inside double-quoted SNBT strings come out
                # with literal backslashes and json.loads would reject them.
                if nxt == "n":
                    buf.append("\n")
                elif nxt == "r":
                    buf.append("\r")
                elif nxt == "t":
                    buf.append("\t")
                else:
                    # \" \\ \' \/ and any other -> the bare char
                    buf.append(nxt)
                self.i += 1
            elif c == quote:
                self.i += 1
                return Str("".join(buf), quote)
            else:
                buf.append(c)
                self.i += 1
        self._err("unterminated string")
        raise AssertionError("unreachable")

    def _literal(self):
        start = self.i
        while self.i < len(self.src) and self.src[self.i] not in ",}]: \t\r\n":
            self.i += 1
        tok = self.src[start:self.i]
        if not tok:
            self._err("unexpected character")
        m = _NUM_RE.fullmatch(tok)
        if m:
            num_part, suf = m.group(1), (m.group(2) or "").lower()
            is_float = ("." in num_part) or ("e" in num_part.lower()) or suf in ("f", "d")
            value = float(num_part) if is_float else int(num_part)
            return Num(value, suf)
        if tok == "true":
            return Num(1, "b")
        if tok == "false":
            return Num(0, "b")
        return Str(tok, "")


def snbt_parse(src: str):
    """Parse an SNBT string into a tree of dict/list/Num/Str/TypedArr nodes."""
    p = _Parser(src)
    p._ws()
    return p.parse()


def _fmt_num(n: Num) -> str:
    v = n.value
    if isinstance(v, float):
        s = repr(v)
        if n.suffix in ("f", "d"):
            if s.endswith(".0"):
                s = s[:-2]
        else:
            if "." not in s and "e" not in s.lower():
                s += ".0"
    else:
        s = str(v)
    return s + n.suffix


def snbt_dump(node) -> str:
    """Serialize a node tree (produced by :func:`snbt_parse` or built by hand) back to SNBT."""
    if isinstance(node, dict):
        parts: list[str] = []
        for k, v in node.items():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-+]*", k):
                ks = k
            else:
                ks = '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'
            parts.append(f"{ks}:{snbt_dump(v)}")
        return "{" + ",".join(parts) + "}"
    if isinstance(node, list):
        return "[" + ",".join(snbt_dump(x) for x in node) + "]"
    if isinstance(node, TypedArr):
        return f"[{node.kind};" + ",".join(snbt_dump(x) for x in node.items) + "]"
    if isinstance(node, Num):
        return _fmt_num(node)
    if isinstance(node, Str):
        if node.quote == "":
            return node.value
        if node.quote == "'":
            return "'" + node.value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return '"' + node.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(node, bool):
        return "1b" if node else "0b"
    raise TypeError(f"cannot dump SNBT node: {type(node).__name__}")
