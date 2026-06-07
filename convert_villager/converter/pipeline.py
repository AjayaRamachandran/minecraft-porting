"""Shared converter state and line dispatch.

``ConverterPipeline`` is the single object an implementor needs to do its job:
it owns the warning sink, the resource-pack custom-item index, and the
configured instances of Levels 1/2/3.

The pipeline also exposes :meth:`dispatch_line` for routing a single line
through registered line-level implementors. Implementors are registered by
the CLI (or any other host) — the pipeline itself doesn't import them, which
keeps the dependency graph one-way (pipeline → converters; cli/implementors →
pipeline).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .custom_models import CustomModelResolver
from .entity_converter import EntityConverter
from .item_converter import ItemConverter


# A line-level implementor is a function that, given a raw line and the
# pipeline, returns either the converted line (str) or None to mean
# "I don't handle this kind of line — let the next implementor try".
LineImplementor = Callable[[str, "ConverterPipeline"], Optional[str]]


class ConverterPipeline:
    """Shared state container passed to every implementor.

    Parameters
    ----------
    pack_dir:
        Path to the 1.21.11 resource pack root (the directory containing
        ``assets/minecraft/items/custom/``). Used for the destination side of
        custom-model resolution.
    old_pack_dir:
        Optional path to the 1.20.1 pack root. When given, the converter uses
        the old pack's ``models/item/*.json`` ``custom_model_data`` overrides
        for deterministic CMD → model resolution. Without it, every legacy
        item falls back to fuzzy display-name matching.
    threshold:
        Fuzzy-match score below which the item converter logs warnings.
        Doesn't affect deterministic CMD hits.
    """

    def __init__(self, pack_dir, old_pack_dir=None, threshold: float = 0.5):
        self.warnings: list[str] = []
        self.resolver = CustomModelResolver(
            new_pack_dir=Path(pack_dir),
            old_pack_dir=Path(old_pack_dir) if old_pack_dir else None,
        )
        # Convenience aliases for the CLI's diagnostic output.
        self.custom_index: list[str] = self.resolver.new_index
        self.cmd_map: dict = self.resolver.cmd_map

        self.item = ItemConverter(self.resolver, threshold, self.warnings)
        self.entity = EntityConverter(self.item, self.warnings)
        self._line_implementors: list[LineImplementor] = []
        self._schematic = None  # lazy — see :prop:`schematic`

    # ----- line implementor registry ------------------------------------

    def register_line_implementor(self, fn: LineImplementor) -> None:
        """Add a line-level implementor. Earlier registrations win on match."""
        self._line_implementors.append(fn)

    def dispatch_line(self, line: str) -> str:
        """Run a single line through every registered implementor.

        The first implementor that returns a non-None value wins. If none
        match, the line is returned unchanged.
        """
        for impl in self._line_implementors:
            result = impl(line, self)
            if result is not None:
                return result
        return line

    # ----- Level 3 schematic (lazy) -------------------------------------

    @property
    def schematic(self):
        """Return a SchematicConverter, instantiating it on first access."""
        if self._schematic is None:
            from .schematic_converter import SchematicConverter
            self._schematic = SchematicConverter(
                self.item, self.entity, self.dispatch_line, self.warnings
            )
        return self._schematic
