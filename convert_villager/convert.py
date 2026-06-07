"""Catch-all batch converter: auto-detects /give, /summon, .schem.

For a mixed input directory, this dispatches each line / file to the right
implementor (villager, summon, give, schematic) automatically. If you only
care about one kind of input, prefer the dedicated scripts:

- ``villager.py`` — /give @p villager_spawn_egg{...}
- ``give.py``     — generic /give <item>{tag}
- ``summon.py``   — /summon <mob> {entity_nbt}
- ``schematic.py``— .schem files

Usage:
    python convert.py                       # batch: ./old/* -> ./new/
    python convert.py -i path -o path       # single file (extension-detected)
"""

from converter.cli import main


if __name__ == "__main__":
    main()
