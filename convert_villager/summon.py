"""Callable script: convert legacy /summon <mob> [pos] {entity_nbt} lines.

Walks the mob's entity NBT and converts any items it holds (``HandItems``,
``ArmorItems``, ``Inventory``, ``Items``, ``Offers``, …) plus ``CustomName``
to the 1.21.11 component format.

Usage:
    python summon.py                        # batch: ./old/*.mcfunction -> ./new/
    python summon.py -i path -o path        # single file
"""

from converter.cli import run_with_implementor
from converter.implementors.summon_command import try_convert_line


if __name__ == "__main__":
    run_with_implementor(try_convert_line, __doc__.splitlines()[0])
