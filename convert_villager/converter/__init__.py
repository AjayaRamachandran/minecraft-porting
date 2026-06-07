"""Layered Minecraft data converter — legacy NBT → 1.21.11 components.

Architecture (in dependency order):

- :mod:`.snbt`, :mod:`.text_components`, :mod:`.custom_models`,
  :mod:`.command_parsing` — pure helpers reused across every level.
- :mod:`.item_converter` — **Level 1**: ItemConverter (single item NBT).
- :mod:`.entity_converter` — **Level 2**: EntityConverter (walks entity NBT,
  delegates items to Level 1).
- :mod:`.schematic_converter` — **Level 3**: SchematicConverter (walks block
  entities in a ``.schem``, delegates items to Level 1, entities to Level 2,
  and command-block text to the line dispatcher).
- :mod:`.pipeline` — ConverterPipeline (shared state + line implementor
  registry).
- :mod:`.implementors` — user-facing entry points (one per command/file kind).
- :mod:`.cli` — argparse entry point that wires everything together.

Top-level imports below provide the most commonly used names so callers can
write ``from converter import ConverterPipeline`` without remembering the
sub-module layout.
"""

from .entity_converter import EntityConverter
from .item_converter import ItemConverter
from .pipeline import ConverterPipeline

__all__ = ["ConverterPipeline", "EntityConverter", "ItemConverter"]
