"""Callable script: convert legacy /give @p villager_spawn_egg{...} lines.

Dedicated to villager spawn-egg /give commands. Other lines pass through
untouched, so you can run this on a mixed file and only villager trades will
be modernized.

Usage:
    python villager.py                      # batch: ./old/*.mcfunction -> ./new/
    python villager.py -i path -o path      # single file
    python villager.py --pack ../pack -v    # custom pack root + verbose
"""

from converter.cli import run_with_implementor
from converter.implementors.villager_command import try_convert_line


if __name__ == "__main__":
    run_with_implementor(try_convert_line, __doc__.splitlines()[0])
