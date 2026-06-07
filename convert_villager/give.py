"""Callable script: convert legacy /give <target> <item>{tag} lines.

Generic /give converter for items that DO NOT carry an EntityTag — that is,
everything except spawn eggs. Use ``villager.py`` for villager spawn eggs.

Usage:
    python give.py                          # batch: ./old/*.mcfunction -> ./new/
    python give.py -i path -o path          # single file
"""

from converter.cli import run_with_implementor
from converter.implementors.give_command import try_convert_line


if __name__ == "__main__":
    run_with_implementor(try_convert_line, __doc__.splitlines()[0])
