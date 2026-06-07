"""Callable script: convert .schem files (Sponge schematic) to 1.21.11.

For every container, spawner, and command block inside the schematic:
- Container ``Items`` lists are run through the item converter (Level 1).
- Spawner ``SpawnData`` / ``SpawnPotentials`` entities are run through the
  entity converter (Level 2).
- Command-block ``Command`` payloads are run through the same line dispatcher
  used for .mcfunction files (so embedded /give and /summon get updated).

Requires the ``mcschematic`` package: ``pip install mcschematic``.

Usage:
    python schematic.py                     # batch: ./old/*.schem -> ./new/
    python schematic.py -i path -o path     # single file
"""

from converter.cli import run_schematic


if __name__ == "__main__":
    run_schematic(__doc__.splitlines()[0])
