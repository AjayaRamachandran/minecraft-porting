"""Implementors — user-facing entry points built on top of the level converters.

Each module here represents one kind of input the user wants converted:

- :mod:`.give_command` — generic ``/give <target> <item>{tag}`` lines (Level 1).
- :mod:`.villager_command` — ``/give @p villager_spawn_egg{…}`` lines with trades (Level 2).
- :mod:`.summon_command` — ``/summon <mob> … {entity_nbt}`` lines (Level 2).
- :mod:`.schematic_file` — ``.schem`` files (Level 3).

Line implementors expose ``try_convert_line(line, pipeline) -> str | None`` —
returning ``None`` means "I don't claim this line, try the next one". File
implementors expose ``convert_file(in_path, out_path, pipeline) -> None``.
"""
