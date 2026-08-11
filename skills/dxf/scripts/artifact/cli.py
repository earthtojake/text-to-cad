from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path


def build_dxf_artifact(*args, **kwargs):
    from cadgen.dxf_artifact import build_dxf_artifact as build

    return build(*args, **kwargs)


def _add_artifact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        help=(
            "Drawing to build the render package for: an imported .dxf file or a "
            "gen_dxf() Python source."
        ),
    )
    parser.add_argument(
        "--write",
        metavar="PATH",
        help=(
            "Also write the package's drawing DXF to this path. For a generated source "
            "this is the export scripts/gen --write produces; for an imported .dxf it is "
            "a copy of the drawing the package holds."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even when a current drawing package exists.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/artifact",
        description=(
            "Build the hidden __cadgen__ drawing package (drawing DXF + 3D preview.glb) "
            "for one drawing — the same on-demand build snapshot and the CAD Viewer run. "
            "This is the only CLI that accepts an IMPORTED .dxf: scripts/gen runs "
            "gen_dxf() generators, and an imported drawing has no generator to run."
        ),
    )
    _add_artifact_arguments(parser)
    return parser



def report_cli_error(*args, **kwargs):
    from cadgen._internal.cli_errors import report_cli_error as report

    return report(*args, **kwargs)

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    target = str(args.target)
    # `.dxf.py` ends in `.py`, so check the compound suffix first — a generator whose
    # name contains ".dxf" must not be mistaken for an imported drawing.
    lowered = target.lower()
    if not lowered.endswith(".dxf") and not lowered.endswith(".py"):
        parser.error(
            f"scripts/artifact target must be a .dxf file or a gen_dxf() Python source: {target}"
        )
    from cadgen.cli_logging import CliLogger

    logger = CliLogger("dxf-artifact", verbose=bool(args.verbose))
    try:
        payload = build_dxf_artifact(
            repo_root=Path.cwd(),
            source_path=Path(target),
            export=Path(args.write) if args.write else None,
            force=bool(args.force),
            logger=logger,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        return report_cli_error(exc, tool="scripts/artifact", verbose=bool(args.verbose))
    logger.total()
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
