# MinecraftPorting

Tools for porting a Minecraft setup from the **1.20.1** era to **1.21.11**.

Two big things changed across those versions, and this repo has a piece for each:

1. **Resource packs** moved from `custom_model_data` overrides to the new
   "items model definition" system (1.21.4+).
2. **Commands and data** moved from the old NBT tag format
   (`/give @p item{...}`) to the new data-component format
   (`/give @p item[...]`).

## What's in here

```
MinecraftPorting/
├── 1_20_1_pack/            ← the legacy resource pack (source)
├── 1_21_11_pack/           ← the migrated resource pack (target)
├── migrate_to_1_21_4.ps1   ← converts a pack's model definitions to 1.21.4+
└── convert_villager/       ← converts mcfunction & .schem files to data components
```

### `migrate_to_1_21_4.ps1` — resource pack migration

Rewrites a resource pack's model definitions so custom items work on 1.21.4+.
It strips the old `overrides` arrays out of `models/item/*.json`, then generates
the new `items/<base>.json` and `items/custom/<name>.json` definition files.
After migrating, custom items are given with the new model syntax:

```
/give @p diamond_sword[minecraft:item_model="minecraft:custom/abandoned_knife"]
```

### `convert_villager/` — command & data conversion

Converts legacy mcfunction lines (`/give`, `/summon`, villager trades) and
`.schem` schematic files into the 1.21.11 data-component format, resolving
custom item textures against the two resource packs above.

For the full technical details — script reference, flags, the layered
converter architecture, and exactly which NBT fields map to which components —
see **[convert_villager/README.md](convert_villager/README.md)**.

## Typical workflow

1. Run `migrate_to_1_21_4.ps1` against the resource pack to bring its model
   definitions up to 1.21.4+.
2. Use the converters in `convert_villager/` to port mcfunction and `.schem`
   files into the new data-component format.
