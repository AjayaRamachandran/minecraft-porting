# convert_villager

Convert legacy (pre-1.20.5) Minecraft mcfunction and schematic files to the
1.21.11 data-component format.

## Layout

```
convert_villager/
├── villager.py       ← callable: /give @p villager_spawn_egg{...}
├── give.py           ← callable: generic /give <target> <item>{tag}
├── summon.py         ← callable: /summon <mob> {entity_nbt}
├── schematic.py      ← callable: .schem files
├── convert.py        ← callable: auto-detect everything in old/
├── old/              ← put legacy files here
├── new/              ← converter writes here
├── test/             ← reserved for expected-output fixtures
└── converter/        ← backend library (the "generators")
```

The `converter/` package contains the layered conversion logic:

- **Level 1** `item_converter.py` — single-item NBT → components
- **Level 2** `entity_converter.py` — entity NBT (uses Level 1 for items inside)
- **Level 3** `schematic_converter.py` — `.schem` block entities (uses L1/L2)

Plus shared helpers: `snbt.py`, `text_components.py`, `custom_models.py`,
`command_parsing.py`, `pipeline.py`.

## Pack assumptions

The converter resolves custom item textures by reading the resource packs
expected one directory up:

- `../1_21_11_pack/assets/minecraft/items/custom/*.json` — new-pack textures
- `../1_20_1_pack/assets/minecraft/models/item/*.json` — old-pack
  `custom_model_data` overrides

If both packs are present, `CustomModelData` is resolved deterministically:
the old pack's `models/item/<base>.json` says
`{"predicate":{"custom_model_data":3016},"model":"custom/darkpick"}`, so a
`CustomModelData:3016` on a `netherite_pickaxe` becomes
`minecraft:item_model="minecraft:custom/darkpick"`. When the CMD isn't in the
old pack or the resolved stem is missing from the new pack, the converter
falls back to fuzzy-matching the item's display name against new-pack
filenames.

## Scripts

Each callable script accepts the same flags. The default is the batch flow:
read every supported file in `old/` and write the converted result to `new/`.

| Script         | What it touches                                           |
| -------------- | --------------------------------------------------------- |
| `villager.py`  | `/give @p villager_spawn_egg{...}` lines (with trades)    |
| `give.py`      | Generic `/give @p <item>{tag}` lines (no spawn eggs)      |
| `summon.py`    | `/summon <mob> [pos] {entity_nbt}` lines                  |
| `schematic.py` | `.schem` files — containers, spawners, command blocks     |
| `convert.py`   | Auto-dispatch: every kind of line + `.schem` files        |

### Common flags

| Flag                  | Default              | What it does                                                                   |
| --------------------- | -------------------- | ------------------------------------------------------------------------------ |
| `-i PATH`             |                      | Single input file. Requires `-o`.                                              |
| `-o PATH`             |                      | Single output file. Required with `-i`.                                        |
| `--in-dir DIR`        | `./old`              | Batch mode: directory of input files.                                          |
| `--out-dir DIR`       | `./new`              | Batch mode: directory for converted files.                                     |
| `--pack DIR`          | `../1_21_11_pack`    | New resource-pack root (must contain `assets/minecraft/items/custom`).         |
| `--old-pack DIR`      | `../1_20_1_pack`     | Old pack root, for deterministic CMD lookup. Omit to force fuzzy-only.         |
| `--threshold FLOAT`   | `0.5`                | Warn when a fuzzy-match score is below this (deterministic CMD hits ignore).   |
| `-v` / `--verbose`    | off                  | Print index size and per-file progress to stderr.                              |

### Examples

Batch-convert the villager spawn-egg files in `old/` to `new/`:

```
python villager.py
```

Convert a single mcfunction file with verbose progress and a stricter
fuzzy-match warning threshold:

```
python villager.py -i old/vulcansmith.mcfunction -o new/vulcansmith.mcfunction -v --threshold 0.7
```

Run every implementor against a mixed input file (auto-detects /give,
/summon, .schem):

```
python convert.py -i old/whatever.mcfunction -o new/whatever.mcfunction
```

Disable the deterministic CMD path (force fuzzy-only, useful for sanity
checks):

```
python villager.py --old-pack ""    # empty path → skipped
```

## What gets converted

Per item:
- `display.Name` → `minecraft:custom_name` (NBT text component, not JSON string)
- `display.Lore` → `minecraft:lore` (list of NBT text components)
- `Unbreakable:1b` → `minecraft:unbreakable={}`
- `CustomModelData:N` → dropped; replaced by `minecraft:item_model="minecraft:custom/<stem>"`
- `Enchantments:[{id,lvl}]` → flat `minecraft:enchantments={"<id>":<level>,…}`
- `AttributeModifiers` → `minecraft:attribute_modifiers` (operation codes
  translated, UUIDs replaced with synthetic namespaced IDs)
- `CanDestroy` → `minecraft:can_break={blocks:[…]}`
- `HideFlags:N` → `minecraft:tooltip_display={hidden_components:[…]}`

Per entity (villagers, summoned mobs):
- `CustomName` → NBT text component
- `Offers.Recipes[].{buy,buyB,sell}` → each item run through Level 1
- `HandItems:[main,off]` + `ArmorItems:[feet,legs,chest,head]` → converted to
  `equipment:{mainhand:…,feet:…,…}` (Minecraft 1.21.4+ no longer reads the
  positional arrays; each non-empty slot is run through Level 1)
- `Inventory`, `Items` → each item run through Level 1
- `SaddleItem`, `Item`, `ArmorItem`, `Body`, `Trident` → run through Level 1
- `Passengers[]` → recurse into rider NBT

Per schematic block entity:
- Container (chest, barrel, hopper, dispenser, shulker_box, …): `Items` → Level 1
- Spawner / trial_spawner: `SpawnData.entity` and each `SpawnPotentials[].data.entity` → Level 2
- Command block / jigsaw: `Command` payload re-runs through the line dispatcher

## Status

- mcfunction conversion: ✅ working
- `.schem` conversion: ✅ working (Sponge v3 format, via `nbtlib` directly).
  Install with `pip install mcschematic` (pulls in `nbtlib` as a transitive
  dependency). Each `.schem` reports `rewrote N/M block entities` to stderr —
  the unchanged ones are block entities whose payload the converter doesn't
  recognize (signs, banner text, etc.) or whose embedded command isn't a
  /give or /summon.

## Diagnostics

Warnings print to stderr. The patterns to watch for:

- `[ctx] CMD N not in old pack; nearest CMD M -> stem` — exact CMD missing from
  the old pack's overrides; resolved to the nearest CMD for the same base item
  (mirrors Minecraft's own predicate selection). Usually fine.
- `[ctx] CMD N → 'stem' not in new pack; nearest CMD M -> stem` — old pack had
  the CMD but the asset wasn't ported to the new pack; resolved to nearest CMD
  instead. Port the missing asset when you get a chance.
- `[ctx] low-confidence custom-model match …` — fell all the way back to fuzzy
  display-name matching with a low score. No CMD coverage existed for this base
  item in the old pack. Check the result manually.
- `[ctx] CMD N → 'stem' not present in new pack; fuzzy fallback …` — old pack
  had the CMD, new pack is missing the asset *and* no other CMD for this base
  item exists in the new pack. Port the asset.
- `[ctx] no custom-model candidate …` — neither CMD tier nor fuzzy matching
  produced a result.
