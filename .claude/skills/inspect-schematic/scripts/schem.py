#!/usr/bin/env python3
"""schem.py -- Minecraft schematic inspector.

Reads Sponge v3 .schem files and lets you explore their block entities,
blocks, and embedded command data without opening them in-game.

Commands
--------
info       <file>                       Overall dimensions and block-entity summary
list-bes   <file> [--type TYPE]         All block entities with position and one-line summary
get-be     <file> <x> <y> <z>          Full SNBT dump of a single block entity
grep       <file> <pattern> [-i] [-r] [-C N]   Search all block-entity NBT text
spawners   <file> [--mob NAME] [--full] All spawner data: BE spawners + /give spawner commands
commands   <file> [--grep PAT]          All command-block commands (grep optional)
blocks     <file>                       Block palette with frequency counts

Requires:  pip install mcschematic   (pulls in nbtlib)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import nbtlib  # type: ignore
except ImportError:
    sys.exit("nbtlib is required:  pip install mcschematic")

# ---------------------------------------------------------------------------
# Schematic loading helpers
# ---------------------------------------------------------------------------

def _load(path: str):
    schem = nbtlib.load(str(path))
    root = schem.get("Schematic", schem)
    return root


def _be_list(root) -> list:
    blocks = root.get("Blocks") if hasattr(root, "get") else None
    if blocks is not None and hasattr(blocks, "get"):
        lst = blocks.get("BlockEntities")
        if lst is not None:
            return lst
    lst = root.get("BlockEntities") if hasattr(root, "get") else None
    return lst or []


def _pos(be) -> tuple[int, int, int]:
    p = be.get("Pos") if hasattr(be, "get") else None
    if p and len(p) >= 3:
        return (int(p[0]), int(p[1]), int(p[2]))
    return (0, 0, 0)


def _bid(be) -> str:
    data = be.get("Data", be) if hasattr(be, "get") else be
    raw = data.get("Id") or data.get("id") if hasattr(data, "get") else None
    return str(raw) if raw else "unknown"


def _data(be):
    return be.get("Data", be) if hasattr(be, "get") else be


def _snbt(tag) -> str:
    return tag.snbt() if hasattr(tag, "snbt") else str(tag)


def _s(v) -> str:
    return str(v)


# ---------------------------------------------------------------------------
# Name extraction from legacy JSON-string CustomName or modern NBT compound
# ---------------------------------------------------------------------------

def _name(raw) -> str:
    if raw is None:
        return ""
    # 1.21+ CustomName is stored as an NBT Compound directly, not a JSON string
    if hasattr(raw, "get") and hasattr(raw, "items"):
        text = raw.get("text")
        return str(text) if text is not None else ""
    s = _s(raw).strip()
    # Unwrap nbtlib string quoting
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1].replace('\\"', '"')
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1].replace("\\'", "'")
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj.get("text", "")
        return str(obj)
    except Exception:
        m = re.search(r'"?text"?\s*:\s*["\']([^"\']*)["\']', s)
        if m:
            return m.group(1)
        return s


# ---------------------------------------------------------------------------
# Balanced-content extractors for NBT parsing
# ---------------------------------------------------------------------------

def _extract_balanced_brace(s: str, start: int) -> str:
    """Extract {..} starting at position start (where s[start]=='{')."""
    depth, in_str, i = 0, None, start
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2; continue
            if c == in_str:
                in_str = None
        else:
            if c in ('"', "'"):
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        i += 1
    return s[start:]


def _extract_balanced_bracket(s: str, start: int) -> str:
    """Extract [...] starting at position start (where s[start]=='[')."""
    depth, in_str, i = 0, None, start
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2; continue
            if c == in_str:
                in_str = None
        else:
            if c in ('"', "'"):
                in_str = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        i += 1
    return s[start:]


# ---------------------------------------------------------------------------
# Spawner data parsing (works for both BE spawners and parsed command NBT)
# ---------------------------------------------------------------------------

def _parse_potentials(data) -> list[dict]:
    """Return a list of dicts: {weight, entity_id, custom_name, raw_entity}."""
    out = []
    pots = data.get("SpawnPotentials") if hasattr(data, "get") else None
    if not pots:
        # SpawnData-only spawner (single variant, no weight list)
        sd = data.get("SpawnData") if hasattr(data, "get") else None
        if sd and hasattr(sd, "get"):
            ent = sd.get("entity") or sd
            out.append({
                "weight": 1,
                "entity_id": _s(ent.get("id", "?")).split(":")[-1] if hasattr(ent, "get") else "?",
                "custom_name": _name(ent.get("CustomName") if hasattr(ent, "get") else None),
                "raw_entity": ent,
            })
        return out
    for p in pots:
        if not hasattr(p, "get"):
            continue
        w = int(p.get("weight", 1))
        pd = p.get("data") or {}
        ent = pd.get("entity") if hasattr(pd, "get") else {}
        if ent is None:
            ent = {}
        eid = _s(ent.get("id", "?")).split(":")[-1] if hasattr(ent, "get") else "?"
        cname = _name(ent.get("CustomName") if hasattr(ent, "get") else None)
        out.append({"weight": w, "entity_id": eid, "custom_name": cname, "raw_entity": ent})
    return out


def _spawner_summary(data) -> str:
    """One-line summary of a spawner."""
    count = data.get("SpawnCount", "?") if hasattr(data, "get") else "?"
    pots = _parse_potentials(data)
    total = sum(p["weight"] for p in pots)
    labels = []
    for p in pots:
        label = p["custom_name"] or p["entity_id"]
        labels.append(f"{label}({p['weight']}/{total})")
    return f"count={count}  {', '.join(labels[:4])}{'...' if len(labels) > 4 else ''}"


# ---------------------------------------------------------------------------
# Command-block spawner extraction — handles both old (1.20-) and new (1.21+) formats
# ---------------------------------------------------------------------------

def _extract_spawner_cmd(cmd_str: str) -> Optional[dict]:
    """
    Parse a /give spawner command and return the spawner's block-entity data.

    Handles two formats:
      Old (pre-1.21): /give @p spawner{display:{Name:'...'}, BlockEntityTag:{...}}
      New (1.21+):    give @p spawner[minecraft:block_entity_data={...}, minecraft:custom_name={...}]

    Returns the block-entity data compound with a '_display_name' key injected, or None.
    """
    stripped = cmd_str.strip()

    # --- Old format: spawner{...} ---
    m_old = re.match(
        r"/?give\s+\S+\s+(?:minecraft:)?(spawner|trial_spawner)\s*(\{)",
        stripped, re.IGNORECASE | re.DOTALL,
    )
    if m_old:
        raw_nbt = _extract_balanced_brace(stripped, m_old.start(2))
        try:
            tag = nbtlib.parse_nbt(raw_nbt)
        except Exception:
            return None
        if not hasattr(tag, "get"):
            return None
        display = tag.get("display")
        name_raw = display.get("Name") if hasattr(display, "get") else None
        display_name = _name(name_raw) if name_raw else ""
        be_tag = tag.get("BlockEntityTag")
        if not hasattr(be_tag, "get"):
            return None
        be_tag["_display_name"] = nbtlib.String(display_name)
        return be_tag

    # --- New 1.21+ format: spawner[minecraft:block_entity_data={...}] ---
    m_new = re.match(
        r"/?give\s+\S+\s+(?:minecraft:)?(spawner|trial_spawner)\s*(\[)",
        stripped, re.IGNORECASE,
    )
    if not m_new:
        return None

    bracket_str = _extract_balanced_bracket(stripped, m_new.start(2))
    inner = bracket_str[1:-1] if len(bracket_str) >= 2 else bracket_str

    # Extract minecraft:block_entity_data={...}
    bed_m = re.search(r'\bminecraft:block_entity_data=(\{)', inner)
    if not bed_m:
        return None
    nbt_str = _extract_balanced_brace(inner, bed_m.start(1))
    try:
        be_tag = nbtlib.parse_nbt(nbt_str)
    except Exception:
        return None
    if not hasattr(be_tag, "get"):
        return None

    # Extract minecraft:custom_name={...} for the spawner item's display name
    display_name = ""
    cn_m = re.search(r'\bminecraft:custom_name=(\{)', inner)
    if cn_m:
        cn_str = _extract_balanced_brace(inner, cn_m.start(1))
        try:
            cn_tag = nbtlib.parse_nbt(cn_str)
            if hasattr(cn_tag, "get"):
                text_val = cn_tag.get("text")
                display_name = str(text_val) if text_val is not None else ""
        except Exception:
            pass

    be_tag["_display_name"] = nbtlib.String(display_name)
    return be_tag


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_info(root, args):
    w, h, l = (root.get(k, 0) for k in ("Width", "Height", "Length"))
    bes = _be_list(root)
    print(f"Dimensions:      {w} x {h} x {l}  ({int(w) * int(h) * int(l):,} blocks)")
    print(f"Block entities:  {len(bes)}")
    counts: dict[str, int] = {}
    for be in bes:
        counts[_bid(be)] = counts.get(_bid(be), 0) + 1
    if counts:
        print("  by type:")
        for t, c in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {t:55s} x{c}")


def cmd_list_bes(root, args):
    bes = _be_list(root)
    tf = args.type.lower() if args.type else None
    print(f"{'Pos':18} {'Type':42} Summary")
    print("-" * 100)
    for be in bes:
        pos = _pos(be)
        t = _bid(be)
        if tf and tf not in t.lower():
            continue
        d = _data(be)
        if "spawner" in t:
            summary = _spawner_summary(d)
        elif "command" in t:
            cmd_val = d.get("Command", "") if hasattr(d, "get") else ""
            summary = _s(cmd_val)[:70] + ("..." if len(_s(cmd_val)) > 70 else "")
        elif any(x in t for x in ("chest", "barrel", "hopper", "shulker")):
            items = d.get("Items", []) if hasattr(d, "get") else []
            summary = f"{len(items)} items"
        else:
            summary = ""
        print(f"({pos[0]:4},{pos[1]:3},{pos[2]:4})   {t:42} {summary}")


def cmd_get_be(root, args):
    bes = _be_list(root)
    target = (args.x, args.y, args.z)
    for be in bes:
        if _pos(be) == target:
            d = _data(be)
            print(f"Block entity at {target}  type={_bid(be)}")
            print()
            try:
                print(d.snbt(compact=False))
            except Exception:
                print(_snbt(d))
            return
    print(f"No block entity at {target}")


def cmd_grep(root, args):
    bes = _be_list(root)
    flags = re.IGNORECASE if args.i else 0
    pat = args.pattern if args.regex else re.escape(args.pattern)
    rx = re.compile(pat, flags)
    ctx = max(0, args.C)
    hits = 0
    for be in bes:
        pos = _pos(be)
        t = _bid(be)
        d = _data(be)
        text = _snbt(d)
        if not rx.search(text):
            continue
        print(f"\n{'='*60}")
        print(f"  {t}  at {pos}")
        print(f"{'='*60}")
        # Split on commas for rough line-by-line view
        segs = [s.strip() for s in re.split(r",(?![^{[]*[}\]])", text)]
        matching = [i for i, s in enumerate(segs) if rx.search(s)]
        shown: set[int] = set()
        for mi in matching:
            for j in range(max(0, mi - ctx), min(len(segs), mi + ctx + 1)):
                shown.add(j)
        for j in sorted(shown):
            marker = ">>>" if rx.search(segs[j]) else "   "
            print(f"  {marker} {segs[j][:160]}")
        hits += 1
    print(f"\n{'-'*40}")
    print(f"Matched {hits} block entit{'ies' if hits != 1 else 'y'}")


def cmd_spawners(root, args):
    bes = _be_list(root)
    mob_filter = args.mob.lower() if args.mob else None
    results: list[tuple[str, tuple, dict]] = []  # (source_label, pos, data)

    # 1. Block-entity spawners
    for be in bes:
        t = _bid(be)
        if "spawner" not in t:
            continue
        results.append(("BE spawner", _pos(be), _data(be)))

    # 2. Command blocks with /give spawner{...} or spawner[...]
    for be in bes:
        t = _bid(be)
        if "command" not in t:
            continue
        d = _data(be)
        cmd_val = _s(d.get("Command", "") if hasattr(d, "get") else "")
        be_tag = _extract_spawner_cmd(cmd_val)
        if be_tag is not None:
            results.append(("cmd block", _pos(be), be_tag))

    if not results:
        print("No spawners found.")
        return

    for source, pos, data in results:
        pots = _parse_potentials(data)
        if mob_filter:
            combined = " ".join(
                (p["custom_name"] + " " + p["entity_id"]).lower() for p in pots
            )
            if mob_filter not in combined:
                continue

        display_name_raw = data.get("_display_name") if hasattr(data, "get") else None
        display_name = _s(display_name_raw) if display_name_raw else ""

        print()
        header = f"  [{source}  pos={pos}]"
        if display_name:
            header += f"  \"{display_name}\""
        print("=" * max(len(header) + 2, 70))
        print(header)
        print("=" * max(len(header) + 2, 70))

        sc = data.get("SpawnCount", "?") if hasattr(data, "get") else "?"
        mn = data.get("MinSpawnDelay", "?") if hasattr(data, "get") else "?"
        mx = data.get("MaxSpawnDelay", "?") if hasattr(data, "get") else "?"
        sr = data.get("SpawnRange", "?") if hasattr(data, "get") else "?"
        mne = data.get("MaxNearbyEntities", "?") if hasattr(data, "get") else "?"
        rpr = data.get("RequiredPlayerRange", "?") if hasattr(data, "get") else "?"

        print(f"  SpawnCount:          {sc}")
        print(f"  Delay (ticks):       {mn} - {mx}")
        print(f"  SpawnRange:          {sr}")
        print(f"  MaxNearbyEntities:   {mne}")
        print(f"  RequiredPlayerRange: {rpr}")

        total = sum(p["weight"] for p in pots)
        print(f"  SpawnPotentials:     {len(pots)} variant(s)  total weight={total}")
        print()
        print(f"  {'#':>2}  {'weight':>6}  {'chance':>7}  {'entity':22} name")
        print(f"  {'-'*2}  {'-'*6}  {'-'*7}  {'-'*22} {'-'*25}")
        for i, p in enumerate(pots):
            chance = 100.0 * p["weight"] / total if total else 0.0
            name = p["custom_name"] or "--"
            eid = p["entity_id"]
            print(f"  {i:>2}  {p['weight']:>6}  {chance:>6.1f}%  {eid:22} {name}")

            if args.full:
                ent = p["raw_entity"]
                if hasattr(ent, "get"):
                    attrs = ent.get("attributes") or ent.get("Attributes") or []
                    for a in attrs:
                        if not hasattr(a, "get"):
                            continue
                        aid = _s(a.get("id", a.get("Name", "?")))
                        base = a.get("base", a.get("Base", "?"))
                        print(f"            attr  {aid} = {base}")

                    # New format: equipment compound + drop_chances compound
                    equip = ent.get("equipment")
                    dc_new = ent.get("drop_chances")
                    if equip and hasattr(equip, "get"):
                        for slot, item in equip.items():
                            iid = _s(item.get("id", "?")) if hasattr(item, "get") else "?"
                            comps = item.get("components") if hasattr(item, "get") else None
                            mdl = ""
                            if comps and hasattr(comps, "get"):
                                mdl_raw = comps.get("minecraft:item_model")
                                mdl = f"  model={_s(mdl_raw)}" if mdl_raw else ""
                            drop_str = ""
                            if dc_new and hasattr(dc_new, "get"):
                                dv = dc_new.get(slot)
                                if dv is not None:
                                    f = float(dv)
                                    drop_str = "  drop=never" if f < 0 else f"  drop={f*100:.1f}%"
                            print(f"            equip/{slot:<8} {iid}{mdl}{drop_str}")

                    # Old format: ArmorItems/HandItems arrays + ArmorDropChances/HandDropChances
                    _OLD_ARMOR_SLOTS = ["feet", "legs", "chest", "head"]
                    _OLD_HAND_SLOTS  = ["mainhand", "offhand"]
                    for items_key, slots, chances_key in [
                        ("ArmorItems", _OLD_ARMOR_SLOTS, "ArmorDropChances"),
                        ("HandItems",  _OLD_HAND_SLOTS,  "HandDropChances"),
                    ]:
                        items_arr   = ent.get(items_key)
                        chances_arr = ent.get(chances_key)
                        if not items_arr:
                            continue
                        for idx, item in enumerate(items_arr):
                            if not hasattr(item, "get"):
                                continue
                            iid = item.get("id") or item.get("Id")
                            if not iid:
                                continue
                            slot = slots[idx] if idx < len(slots) else str(idx)
                            drop_str = ""
                            if chances_arr and idx < len(chances_arr):
                                f = float(chances_arr[idx])
                                drop_str = "  drop=never" if f < 0 else f"  drop={f*100:.1f}%"
                            print(f"            equip/{slot:<8} {iid}{drop_str}")
        print()


def cmd_commands(root, args):
    bes = _be_list(root)
    gp = args.grep
    rx = re.compile(re.escape(gp), re.IGNORECASE) if gp else None
    count = 0
    for be in bes:
        t = _bid(be)
        if "command" not in t and "jigsaw" not in t:
            continue
        pos = _pos(be)
        d = _data(be)
        cmd_val = _s(d.get("Command", "") if hasattr(d, "get") else "")
        if rx and not rx.search(cmd_val):
            continue
        short_type = t.split(":")[-1]
        print(f"({pos[0]:4},{pos[1]:3},{pos[2]:4})  {short_type:35}  {cmd_val[:120]}"
              + ("..." if len(cmd_val) > 120 else ""))
        count += 1
    print(f"\n{count} command block(s)" + (f" matching '{gp}'" if gp else ""))


def cmd_blocks(root, args):
    blocks = root.get("Blocks") if hasattr(root, "get") else None
    if not blocks or not hasattr(blocks, "get"):
        print("No Blocks section found.")
        return
    palette = blocks.get("Palette") if hasattr(blocks, "get") else None
    raw_data = blocks.get("Data") if hasattr(blocks, "get") else None

    if palette:
        # Count usage if block data array is present
        usage: dict[int, int] = {}
        if raw_data:
            try:
                arr = bytes(raw_data)
                for b in arr:
                    usage[b] = usage.get(b, 0) + 1
            except Exception:
                pass
        print(f"Palette: {len(palette)} block type(s)")
        print(f"  {'idx':>4}  {'count':>8}  block state")
        print(f"  {'-'*4}  {'-'*8}  {'-'*50}")
        for state, idx in sorted(palette.items(), key=lambda x: int(x[1])):
            idx_i = int(idx)
            cnt = usage.get(idx_i, 0)
            print(f"  {idx_i:>4}  {cnt:>8}  {state}")
    else:
        print("No palette found.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Minecraft Schematic Inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd", metavar="command", required=True)

    def _add(name, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("file", help="Path to .schem file")
        return p

    _add("info", "Overall dimensions and block-entity summary")

    p = _add("list-bes", "List all block entities")
    p.add_argument("--type", metavar="TYPE", help="Filter by type substring")

    p = _add("get-be", "Dump block entity NBT at a position")
    p.add_argument("x", type=int); p.add_argument("y", type=int); p.add_argument("z", type=int)

    p = _add("grep", "Search all block-entity NBT for a pattern")
    p.add_argument("pattern")
    p.add_argument("-i", action="store_true", help="Case insensitive")
    p.add_argument("-r", "--regex", action="store_true", help="Treat pattern as regex")
    p.add_argument("-C", type=int, default=2, metavar="N", help="Context segments (default 2)")

    p = _add("spawners", "List all spawner configurations with weights/chances")
    p.add_argument("--mob", metavar="NAME", help="Filter by mob name/id substring")
    p.add_argument("--full", action="store_true", help="Also print attributes and equipment")

    p = _add("commands", "List command-block commands")
    p.add_argument("--grep", metavar="PATTERN", help="Filter by substring")

    _add("blocks", "Show block palette with usage counts")

    args = ap.parse_args()
    root = _load(args.file)
    {
        "info":      cmd_info,
        "list-bes":  cmd_list_bes,
        "get-be":    cmd_get_be,
        "grep":      cmd_grep,
        "spawners":  cmd_spawners,
        "commands":  cmd_commands,
        "blocks":    cmd_blocks,
    }[args.cmd](root, args)


if __name__ == "__main__":
    main()
