"""Implementor: ``.schem`` file conversion (Level 3 wrapper).

A thin façade around :class:`~..schematic_converter.SchematicConverter` that
matches the implementor calling convention (``convert_file(in_path, out_path,
pipeline)``) used by the CLI for file-level work.
"""

from __future__ import annotations

from pathlib import Path


def convert_file(in_path, out_path, pipeline) -> None:
    """Convert one ``.schem`` file end-to-end.

    Raises ``RuntimeError`` if the ``mcschematic`` library isn't installed
    (see :meth:`SchematicConverter.convert_schematic_file`).
    """
    pipeline.schematic.convert_schematic_file(Path(in_path), Path(out_path))
