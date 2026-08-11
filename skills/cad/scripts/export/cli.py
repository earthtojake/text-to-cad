from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from cadgen.metadata import normalize_mesh_numeric

# Sentinel for a format flag passed without a path: export to the default sibling
# path (`<name>.<ext>` beside the model's logical STEP).
DEFAULT_OUTPUT = "__default_sibling_output__"


def export_cad_target(*args, **kwargs):
    from cadgen.step_export_target import export_cad_target as export

    return export(*args, **kwargs)


def report_cli_error(*args, **kwargs):
    from cadgen._internal.cli_errors import report_cli_error as report

    return report(*args, **kwargs)


def _normalize_cli_numeric(value: object, *, field_name: str, parser: argparse.ArgumentParser) -> float | None:
    try:
        return normalize_mesh_numeric(value, field_name=field_name)
    except ValueError as exc:
        parser.error(str(exc))
    return None


def _add_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        help="CAD model to export: a gen_step() Python source or an imported STEP/STP file.",
    )
    parser.add_argument(
        "--stl",
        nargs="?",
        const=DEFAULT_OUTPUT,
        metavar="OUTPUT",
        help="Export an STL mesh. Without a path, writes the sibling <name>.stl.",
    )
    parser.add_argument(
        "--3mf",
        dest="three_mf",
        nargs="?",
        const=DEFAULT_OUTPUT,
        metavar="OUTPUT",
        help="Export a 3MF mesh. Without a path, writes the sibling <name>.3mf.",
    )
    parser.add_argument(
        "--glb",
        nargs="?",
        const=DEFAULT_OUTPUT,
        metavar="OUTPUT",
        help="Export a native Y-up GLB mesh. Without a path, writes the sibling <name>.glb.",
    )
    parser.add_argument(
        "--mesh-tolerance",
        type=float,
        help="Positive shared mesh linear deflection for STL, 3MF, and native GLB outputs.",
    )
    parser.add_argument(
        "--mesh-angular-tolerance",
        type=float,
        help="Positive shared mesh angular deflection for STL, 3MF, and native GLB outputs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Print the export result as one JSON line on stdout instead of the "
            "'wrote STL: ...' lines. Human progress stays on stderr."
        ),
    )


def _requested_outputs(args: argparse.Namespace) -> list[tuple[str, str | None]]:
    outputs: list[tuple[str, str | None]] = []
    for fmt, value in (
        ("stl", args.stl),
        ("3mf", args.three_mf),
        ("glb", args.glb),
    ):
        if value is None:
            continue
        outputs.append((fmt, None if value == DEFAULT_OUTPUT else value))
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/export",
        description=(
            "Export one CAD model — a gen_step() Python source or an imported STEP/STP "
            "file — to STL/3MF/GLB. The model is built once per run, so all requested "
            "formats come from identical geometry. Writes no .step file: use "
            "scripts/gen --write-step to write a generated model's STEP."
        ),
    )
    _add_export_arguments(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    outputs = _requested_outputs(args)
    if not outputs:
        parser.error("at least one export format is required: --stl, --3mf, or --glb")
    mesh_tolerance = _normalize_cli_numeric(
        args.mesh_tolerance,
        field_name="mesh_tolerance",
        parser=parser,
    )
    mesh_angular_tolerance = _normalize_cli_numeric(
        args.mesh_angular_tolerance,
        field_name="mesh_angular_tolerance",
        parser=parser,
    )
    try:
        payload = export_cad_target(
            args.target,
            outputs,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
            verbose=bool(args.verbose),
        )
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        return report_cli_error(exc, tool="scripts/export", verbose=bool(args.verbose))
    if args.json:
        print(json.dumps({"ok": True, **payload}, separators=(",", ":")))
        return 0
    for entry in payload["files"]:
        print(f"wrote {entry['format'].upper()}: {entry['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
