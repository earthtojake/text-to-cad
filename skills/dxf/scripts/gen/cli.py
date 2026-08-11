from __future__ import annotations

import argparse
from collections.abc import Sequence


def report_cli_error(*args, **kwargs):
    from cadgen._internal.cli_errors import report_cli_error as report

    return report(*args, **kwargs)


def generate_dxf_targets(*args, **kwargs):
    from cadgen.generation import generate_dxf_targets as generate

    return generate(*args, **kwargs)


def validate_dxf_files(targets: Sequence[str]) -> int:
    """Run the generation-time drawing checks post-hoc on existing .dxf files.
    One unreadable/corrupt file is a per-file FAIL, never an aborted run."""
    from cadgen.drawing_checks import validate_dxf_file

    exit_code = 0
    for target in targets:
        try:
            findings = validate_dxf_file(target)
        except Exception as exc:  # noqa: BLE001 — missing/corrupt file -> per-file FAIL
            print(f"[dxf] {target}: FAIL")
            print(f"[dxf]   [error] unreadable: {exc}")
            exit_code = 1
            continue
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            exit_code = 1
        status = "FAIL" if errors else "ok"
        print(f"[dxf] {target}: {status}")
        for finding in findings:
            print(f"[dxf]   {finding.render()}")
    return exit_code


def _targets_include_output_pairs(targets: Sequence[str]) -> bool:
    return any("=" in str(target or "") for target in targets)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/gen",
        description=(
            "Build drawing-package render artifacts (and on-demand DXF exports) from "
            "Python gen_dxf() sources."
        ),
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Explicit Python source file or SOURCE.py=OUTPUT.dxf pair defining gen_dxf() to generate.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="Export the generated DXF file to this path. Valid only with one plain generated Python target.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also write the sibling <name>.dxf export (the drawing package is always built).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when the cached drawing package is current.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate existing .dxf files with the generation-time drawing checks instead of generating.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.validate:
        if args.output is not None or args.write or args.force:
            parser.error("--validate cannot be combined with generation flags")
        return validate_dxf_files(args.targets)
    if args.output is not None:
        if _targets_include_output_pairs(args.targets):
            parser.error("--output cannot be combined with SOURCE=OUTPUT targets")
        if len(args.targets) != 1:
            parser.error("--output can only be used with exactly one target")
    try:
        return generate_dxf_targets(
            args.targets,
            output=args.output,
            write_dxf=bool(args.write),
            force=bool(args.force),
            verbose=bool(args.verbose),
        )
    except Exception as exc:  # noqa: BLE001 — the CLI boundary: report, do not traceback
        return report_cli_error(exc, tool="scripts/gen", verbose=bool(args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
