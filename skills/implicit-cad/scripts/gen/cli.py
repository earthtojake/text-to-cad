"""`scripts/gen` for implicit CAD: build the render package for .implicit.js models.

Mirrors `skills/cad/scripts/gen` point for point -- positional targets, `--force`,
`--verbose`, one format-specific bake knob (`--resolution`), sequential per-target locks, a
CliLogger on stderr and one self-erasing progress line -- because there is ONE producer
(`cadgen.implicit_artifact`) behind both this and the viewer's POST, and the CLI's job is to
present it, not to reimplement any part of it.

Always builds the package. `--write` ALSO leaves the sibling `<name>.glb` beside the source
(§0.1), in the export preset -- the package's own `model.glb` is quantized and
meshopt-compressed for the viewer, which is the wrong file to hand a slicer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen.coordination import render_progress_bar

# Sentinel for --write without a path: write each target's sibling <name>.glb.
DEFAULT_GLB_OUTPUT = "__default_sibling_glb__"

IMPLICIT_SUFFIXES = (".implicit.js", ".implicit.mjs")


def build_implicit_artifact(*args, **kwargs):
    from cadgen.implicit_artifact import build_implicit_artifact as build

    return build(*args, **kwargs)


class _ProgressLine:
    """One self-erasing status line for the build in flight.

    Repaints in place with ``\\r`` and erases itself when the build ends, so the only durable
    output is the logger's own lines. Silent when stderr is not a tty (a redirected log wants
    lines, not a bar smeared over hundreds of writes) and under ``--verbose``, where the
    logger is already narrating.
    """

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = bool(enabled) and getattr(sys.stderr, "isatty", lambda: False)()
        self._width = 0

    def __call__(self, event: object) -> None:
        if not self._enabled or getattr(event, "finished", False):
            return
        ratio = float(getattr(event, "ratio", 0.0) or 0.0)
        label = str(getattr(event, "label", "") or "working").lower()
        text = f"{render_progress_bar(ratio)} {int(ratio * 100):>3d}%  {label}"
        if getattr(event, "determinate", False) and getattr(event, "total", None):
            text = f"{text} {event.done}/{event.total}"
        padding = max(0, self._width - len(text))
        self._width = len(text)
        print(f"\r{text}{' ' * padding}", end="", file=sys.stderr, flush=True)

    def clear(self) -> None:
        if not self._enabled or not self._width:
            return
        print(f"\r{' ' * self._width}\r", end="", file=sys.stderr, flush=True)
        self._width = 0


def _sibling_glb_output(target: str) -> str:
    lowered = target.lower()
    for suffix in IMPLICIT_SUFFIXES:
        if lowered.endswith(suffix):
            return f"{target[: -len(suffix)]}.glb"
    return str(Path(target).with_suffix(".glb"))


def _validate_targets(targets: Sequence[str], *, parser: argparse.ArgumentParser) -> None:
    for target in targets:
        if not str(target).lower().endswith(IMPLICIT_SUFFIXES):
            parser.error(
                f"scripts/gen builds implicit CAD models only: {target}. "
                "Targets must be <name>.implicit.js sources."
            )


def _output_for_target(
    target: str,
    write: str | None,
    *,
    target_count: int,
    parser: argparse.ArgumentParser,
) -> Path | None:
    if write is None:
        return None
    if write == DEFAULT_GLB_OUTPUT:
        return Path(_sibling_glb_output(target))
    if target_count != 1:
        parser.error("--write with an explicit path requires exactly one target")
    return Path(write)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/gen",
        description=(
            "Build CAD Viewer render packages for explicit .implicit.js targets. Writes a "
            "sibling .glb only with --write; use scripts/export for STL/3MF/GLB files."
        ),
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Explicit implicit CAD source(s) to build (<name>.implicit.js).",
    )
    parser.add_argument(
        "--write",
        nargs="?",
        const=DEFAULT_GLB_OUTPUT,
        metavar="OUTPUT",
        help=(
            "Also write the model's GLB beside the source. Without a path, each target "
            "writes its sibling <name>.glb; an explicit path requires exactly one target "
            "and resolves from the command cwd. The render package is always built."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild render packages even when current artifacts match the source closure.",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        help="Longest-axis sampling resolution to bake. Default: the shipped bake resolution.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        help="Worker threads for sampling/polygonizing. Default: this machine's parallelism.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )
    return parser



def report_cli_error(*args, **kwargs):
    from cadgen._internal.cli_errors import report_cli_error as report

    return report(*args, **kwargs)

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _validate_targets(args.targets, parser=parser)
    logger = CliLogger("scripts/gen", verbose=bool(args.verbose))
    exit_code = 0
    for target in args.targets:
        output = _output_for_target(
            target,
            args.write,
            target_count=len(args.targets),
            parser=parser,
        )
        # Sequential, one lock at a time: two targets are two packages, and a build that
        # queued behind a peer must re-check freshness under the lock rather than assume.
        line = _ProgressLine(enabled=not logger.verbose)
        try:
            with logger.timed(f"generated {target}"):
                payload = build_implicit_artifact(
                    repo_root=Path.cwd(),
                    source_path=Path(target),
                    resolution=args.resolution,
                    threads=args.threads,
                    write_glb=output,
                    force=bool(args.force),
                    logger=logger,
                    sink=line,
                )
        except Exception as exc:  # noqa: BLE001 - one bad target must not abort the run
            line.clear()
            logger.warning(f"{target}: {exc}")
            exit_code = 1
            continue
        line.clear()
        if payload.get("skipped"):
            logger.info(f"{target} is current; skipped regeneration")
        else:
            stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
            triangles = stats.get("triangleCount")
            detail = f" ({triangles:,} triangles)" if isinstance(triangles, int) else ""
            logger.info(f"generated {payload.get('packagePath', target)}{detail}")
        written = payload.get("path")
        if written:
            logger.info(f"wrote {written}")
    logger.total()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
