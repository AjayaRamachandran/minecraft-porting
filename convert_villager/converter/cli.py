"""Command-line entry point + reusable runners.

This module hosts three callable entry points:

- :func:`main` — the multi-implementor batch CLI used by ``convert.py``.
  Registers every line implementor in priority order (villager → summon →
  give) and falls back to schematic for ``.schem`` files.
- :func:`run_with_implementor` — dedicated runner for one specific line
  implementor; used by the per-implementor top-level scripts
  (``give.py``, ``villager.py``, ``summon.py``) so each script only handles
  its own kind of line.
- :func:`run_schematic` — file-level runner for ``.schem`` inputs, used by
  ``schematic.py``.

Defaults match the original tool: ``./old/*.mcfunction → ./new/`` with the
resource pack at ``../1_21_11_pack``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .implementors import (
    execute_command,
    give_command,
    schematic_file,
    spawner_command,
    summon_command,
    villager_command,
)
from .pipeline import ConverterPipeline


# Default locations relative to this package's parent directory (the
# `convert_villager/` folder that contains old/, new/, test/).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACK_DIR = _PROJECT_ROOT.parent / "1_21_11_pack"
DEFAULT_OLD_PACK_DIR = _PROJECT_ROOT.parent / "1_20_1_pack"
DEFAULT_IN_DIR = _PROJECT_ROOT / "old"
DEFAULT_OUT_DIR = _PROJECT_ROOT / "new"


def build_pipeline(pack_dir, threshold: float, old_pack_dir=None) -> ConverterPipeline:
    """Construct a pipeline and register every line implementor on it.

    Order is significant: villager wins over generic give when a /give line
    happens to be a spawn egg.
    """
    pipeline = ConverterPipeline(pack_dir, old_pack_dir=old_pack_dir, threshold=threshold)
    pipeline.register_line_implementor(villager_command.try_convert_line)
    pipeline.register_line_implementor(spawner_command.try_convert_line)
    pipeline.register_line_implementor(summon_command.try_convert_line)
    pipeline.register_line_implementor(give_command.try_convert_line)
    pipeline.register_line_implementor(execute_command.try_convert_line)
    return pipeline


def process_mcfunction_file(in_path, out_path, pipeline: ConverterPipeline) -> None:
    """Convert a .mcfunction file line by line through the registered implementors."""
    src = Path(in_path).read_text(encoding="utf-8")
    out_lines: list[str] = []
    for line in src.splitlines():
        if not line.strip():
            out_lines.append("")
            continue
        try:
            out_lines.append(pipeline.dispatch_line(line))
        except Exception as ex:  # noqa: BLE001
            pipeline.warnings.append(f"[{in_path}] line conversion failed: {ex}")
            out_lines.append(line)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-i", "--input", help="single input file")
    parser.add_argument("-o", "--output", help="single output file (required with -i)")
    parser.add_argument("--in-dir", default=str(DEFAULT_IN_DIR),
                        help="batch mode: input directory (default: ./old)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help="batch mode: output directory (default: ./new)")
    parser.add_argument("--pack", default=str(DEFAULT_PACK_DIR),
                        help="new resource-pack root (default: ../1_21_11_pack)")
    parser.add_argument("--old-pack", default=str(DEFAULT_OLD_PACK_DIR),
                        help="old resource-pack root for deterministic "
                             "custom_model_data lookup (default: ../1_20_1_pack)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="warn when fuzzy-match score is below this (default: 0.5)")
    parser.add_argument("-v", "--verbose", action="store_true")


def run_with_implementor(try_convert_line, description: str, argv=None) -> None:
    """Run a single line implementor as a standalone script.

    The pipeline is built with **only** ``try_convert_line`` registered. Lines
    the implementor doesn't claim pass through unchanged — exactly the behavior
    you want when a script is dedicated to one command kind (e.g. ``villager.py``
    leaves ``/summon`` lines alone).

    The batch behaviour mirrors the multi-implementor CLI:
    ``./old/*.mcfunction → ./new/`` by default, or single-file with ``-i/-o``.
    """
    parser = argparse.ArgumentParser(description=description)
    _add_common_args(parser)
    args = parser.parse_args(argv)

    pipeline = ConverterPipeline(
        args.pack, old_pack_dir=args.old_pack, threshold=args.threshold,
    )
    pipeline.register_line_implementor(try_convert_line)
    if args.verbose:
        print(f"[info] {len(pipeline.custom_index)} new-pack item models, "
              f"{len(pipeline.cmd_map)} CMD overrides from old pack",
              file=sys.stderr)

    if args.input:
        if not args.output:
            parser.error("--output is required when --input is used")
        process_mcfunction_file(Path(args.input), Path(args.output), pipeline)
        if args.verbose:
            print(f"[info] wrote {args.output}", file=sys.stderr)
    else:
        in_dir = Path(args.in_dir)
        out_dir = Path(args.out_dir)
        if not in_dir.is_dir():
            parser.error(f"input dir not found: {in_dir}")
        files = sorted(in_dir.glob("*.mcfunction"))
        if not files:
            print(f"[info] no .mcfunction files in {in_dir}", file=sys.stderr)
        for f in files:
            process_mcfunction_file(f, out_dir / f.name, pipeline)
            if args.verbose:
                print(f"[info] wrote {out_dir / f.name}", file=sys.stderr)

    for w in pipeline.warnings:
        print(f"WARN: {w}", file=sys.stderr)


def run_schematic(description: str, argv=None) -> None:
    """Standalone runner for the schematic implementor.

    ``.schem`` inputs only — line implementors are not registered because the
    schematic walk uses :func:`ConverterPipeline.dispatch_line` separately for
    command-block contents, and that path needs the full set wired up. So we
    register all line implementors here too.
    """
    parser = argparse.ArgumentParser(description=description)
    _add_common_args(parser)
    args = parser.parse_args(argv)

    pipeline = ConverterPipeline(
        args.pack, old_pack_dir=args.old_pack, threshold=args.threshold,
    )
    # Command-block payloads use the same line dispatch as .mcfunction files.
    pipeline.register_line_implementor(villager_command.try_convert_line)
    pipeline.register_line_implementor(spawner_command.try_convert_line)
    pipeline.register_line_implementor(summon_command.try_convert_line)
    pipeline.register_line_implementor(give_command.try_convert_line)
    pipeline.register_line_implementor(execute_command.try_convert_line)

    if args.input:
        if not args.output:
            parser.error("--output is required when --input is used")
        schematic_file.convert_file(Path(args.input), Path(args.output), pipeline)
        if args.verbose:
            print(f"[info] wrote {args.output}", file=sys.stderr)
    else:
        in_dir = Path(args.in_dir)
        out_dir = Path(args.out_dir)
        if not in_dir.is_dir():
            parser.error(f"input dir not found: {in_dir}")
        files = sorted(in_dir.glob("*.schem"))
        if not files:
            print(f"[info] no .schem files in {in_dir}", file=sys.stderr)
        for f in files:
            schematic_file.convert_file(f, out_dir / f.name, pipeline)
            if args.verbose:
                print(f"[info] wrote {out_dir / f.name}", file=sys.stderr)

    for w in pipeline.warnings:
        print(f"WARN: {w}", file=sys.stderr)


def _dispatch_file(in_path: Path, out_path: Path, pipeline: ConverterPipeline) -> None:
    suffix = in_path.suffix.lower()
    if suffix == ".mcfunction":
        process_mcfunction_file(in_path, out_path, pipeline)
    elif suffix == ".schem":
        schematic_file.convert_file(in_path, out_path, pipeline)
    else:
        raise SystemExit(f"unsupported input extension: {suffix} ({in_path})")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert legacy Minecraft mcfunction / schem files to 1.21.11 format."
    )
    _add_common_args(parser)
    args = parser.parse_args(argv)

    pipeline = build_pipeline(args.pack, args.threshold, old_pack_dir=args.old_pack)
    if args.verbose:
        print(f"[info] {len(pipeline.custom_index)} new-pack item models, "
              f"{len(pipeline.cmd_map)} CMD overrides from old pack",
              file=sys.stderr)

    if args.input:
        if not args.output:
            parser.error("--output is required when --input is used")
        in_path = Path(args.input)
        out_path = Path(args.output)
        _dispatch_file(in_path, out_path, pipeline)
        if args.verbose:
            print(f"[info] wrote {out_path}", file=sys.stderr)
    else:
        in_dir = Path(args.in_dir)
        out_dir = Path(args.out_dir)
        if not in_dir.is_dir():
            parser.error(f"input dir not found: {in_dir}")
        files = sorted(p for p in in_dir.iterdir()
                       if p.suffix.lower() in (".mcfunction", ".schem"))
        if not files:
            print(f"[info] no .mcfunction / .schem files in {in_dir}", file=sys.stderr)
        for f in files:
            _dispatch_file(f, out_dir / f.name, pipeline)
            if args.verbose:
                print(f"[info] wrote {out_dir / f.name}", file=sys.stderr)

    for w in pipeline.warnings:
        print(f"WARN: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
