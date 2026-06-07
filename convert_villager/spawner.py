"""Callable script: convert legacy /give @p spawner{...BlockEntityTag:{...}} lines.

Handles the spawner-as-item case where a /give command bundles a configured
spawner via its BlockEntityTag. Walks SpawnData and SpawnPotentials entities
through the entity converter so embedded items, custom names, and legacy
attribute/drop-chance fields get modernized too.

Usage:
    python spawner.py                       # batch: ./old/*.mcfunction -> ./new/
    python spawner.py -i path -o path       # single file
"""

from converter.cli import run_with_implementor
from converter.implementors.spawner_command import try_convert_line


if __name__ == "__main__":
    run_with_implementor(try_convert_line, __doc__.splitlines()[0])
