---
name: inspect-schematic
description: Inspect and query Minecraft .schem schematic files — exploring block entities, spawner configurations, command-block payloads, block palettes, and NBT data. Use this skill whenever the user asks about what's inside a schematic, wants to find a mob, spawner, command, or item within a .schem file, wants spawn rates or weights, or needs to search/grep schematic NBT data.
---

# inspect-schematic

Use `python .claude/skills/inspect-schematic/scripts/schem.py` to explore
Minecraft `.schem` files without opening them in-game.

Schematics in this project live under `convert_villager/old/` (originals)
and `convert_villager/new/` (converted output).

## Quick reference

```
python .claude/skills/inspect-schematic/scripts/schem.py info      <file>
python .claude/skills/inspect-schematic/scripts/schem.py list-bes  <file> [--type TYPE]
python .claude/skills/inspect-schematic/scripts/schem.py get-be    <file> <x> <y> <z>
python .claude/skills/inspect-schematic/scripts/schem.py grep      <file> <pattern> [-i] [-r] [-C N]
python .claude/skills/inspect-schematic/scripts/schem.py spawners  <file> [--mob NAME] [--full]
python .claude/skills/inspect-schematic/scripts/schem.py commands  <file> [--grep PATTERN]
python .claude/skills/inspect-schematic/scripts/schem.py blocks    <file>
```

---

## Subcommand guide

### `info` — overview
Start here. Shows dimensions, total block-entity count, and a breakdown by type.

### `list-bes` — block entity table
Lists every block entity with its position and a one-line summary.
`--type` filters by a substring of the type id (`--type spawner`, `--type command`, `--type chest`).

### `get-be` — full NBT dump at a position
Dumps the complete SNBT for one block entity. Positions come from `list-bes`.

### `grep` — search across all NBT
Searches every block entity's serialized NBT text for a string or regex.
`-i` case-insensitive, `-r` regex mode, `-C N` context segments around hits.
This searches inside command-block Command fields too, so it finds mob names,
item ids, enchantments, or any NBT key/value anywhere in the schematic.

### `spawners` — spawn-weight analysis
Shows every spawner configuration in the schematic with a full weight/chance
breakdown. Crucially, it finds spawner data in **two places**:
- Block entities with type `mob_spawner` or `trial_spawner`
- Command blocks whose payload is a `/give @p spawner{BlockEntityTag:{...}}`
  command (a common pattern for storing spawner presets)

Both are reported uniformly. For each spawner it prints SpawnCount, delay
range, and a table of each potential variant with weight, % chance, entity
id, and custom name.

`--mob` filters by mob name/id substring. `--full` adds attribute values and equipment slots per variant.

Spawn chance = `weight / sum_of_all_weights * 100%`

### `commands` — command-block listing
Lists every command-block payload with its position.
`--grep` filters to commands containing a substring.

### `blocks` — block palette
Shows every distinct block state in the palette and how many times it appears.

---

## Typical workflows

**"What are the spawn rates/weights for mob X?"**
```
python ... spawners <file> --mob <name>
```

**"Give me full details on a spawner — attributes, equipment, etc."**
```
python ... spawners <file> --mob <name> --full
```

**"Find everywhere a specific item, CMD number, or string appears"**
```
python ... grep <file> "CustomModelData:3027" -i -C 2
```

**"I know the block position — show me everything about that block entity"**
```
python ... get-be <file> <x> <y> <z>
```

**"What command blocks are in this schematic and what do they do?"**
```
python ... commands <file>
```

**"Compare old vs new conversion output"**
Run the same subcommand against `convert_villager/old/<file>` and
`convert_villager/new/<file>` to diff the before/after.

---

## Interpreting spawner output

- **SpawnCount** -- mobs spawned per activation
- **Delay range** -- random tick range between activations (200 ticks ~ 10 s)
- **SpawnRange** -- block radius in which mobs can be placed
- **MaxNearbyEntities** -- spawner pauses when this many of the type are within a 17x17x9 area
- **RequiredPlayerRange** -- player must be within this many blocks to activate
- **weight / chance** -- relative probability of each variant on any given spawn event
