from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR))

from urdf.findings import ValidationResult
from urdf.source import UrdfSource, validate_urdf_file

URDF_SUFFIX = ".urdf"


def validate_urdf_targets(
    targets: Sequence[str],
    *,
    strict: bool = False,
    output_format: str = "text",
    package_map: dict[str, Path] | None = None,
) -> int:
    target_paths = [_resolve_target_path(target) for target in targets]
    reports: list[dict[str, object]] = []
    failed = False
    for target_path in target_paths:
        report = _validate_target(target_path, strict=strict, output_format=output_format, package_map=package_map)
        reports.append(report)
        if not report["ok"]:
            failed = True
    if output_format == "json":
        print(json.dumps({"files": reports}, indent=2))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/validate",
        description="Validate explicit URDF targets.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Explicit .urdf file to validate.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as failures.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output format: human-readable text (default) or a JSON findings document.",
    )
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Resolve package://NAME/... mesh URIs against PATH. Repeatable.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Narrate each target and its timing on stderr.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verbose:
        # Narration goes to stderr; the findings document on stdout stays exactly the same
        # so `--verbose` never changes what a caller parses.
        for target in args.targets:
            print(f"[urdf] validating {target}", file=sys.stderr)
    package_map = _parse_package_map(args.package, parser)
    return validate_urdf_targets(
        args.targets,
        strict=args.strict,
        output_format=args.output_format,
        package_map=package_map,
    )


def _parse_package_map(entries: Sequence[str], parser: argparse.ArgumentParser) -> dict[str, Path] | None:
    if not entries:
        return None
    package_map: dict[str, Path] = {}
    for entry in entries:
        name, separator, raw_path = str(entry).partition("=")
        if not separator or not name.strip() or not raw_path.strip():
            parser.error(f"--package expects NAME=PATH, got {entry!r}")
        package_map[name.strip()] = Path(raw_path.strip()).expanduser()
    return package_map


def _resolve_target_path(raw_target: object) -> Path:
    value = str(raw_target or "").strip()
    if not value:
        raise ValueError("urdf target must be a non-empty path")
    target_path = Path(value).expanduser()
    return target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()


def _validate_target(
    target_path: Path,
    *,
    strict: bool,
    output_format: str,
    package_map: dict[str, Path] | None,
) -> dict[str, object]:
    display = _display_path(target_path)
    text_mode = output_format == "text"
    if target_path.suffix.lower() != URDF_SUFFIX:
        return _report_precheck_failure(display, "target must be a .urdf file", text_mode)
    if not target_path.is_file():
        return _report_precheck_failure(display, "file not found", text_mode)

    source, result = validate_urdf_file(target_path, package_map=package_map)
    result = result.deduplicated()
    ok = _report_findings(display, result, strict=strict, text_mode=text_mode)
    summary = _summary_line(display, source) if source is not None else ""
    if text_mode and ok and summary:
        print(summary)
    return {
        "path": display,
        "ok": ok,
        "summary": summary,
        "findings": [finding.to_dict() for finding in result.all_findings()],
    }


def _report_precheck_failure(display: str, message: str, text_mode: bool) -> dict[str, object]:
    if text_mode:
        print(f"FAIL {display}: {message}", file=sys.stderr)
    return {
        "path": display,
        "ok": False,
        "summary": "",
        "findings": [{"severity": "error", "code": "invalid_target", "message": message}],
    }


def _report_findings(display: str, result: ValidationResult, *, strict: bool, text_mode: bool) -> bool:
    if text_mode:
        for finding in result.all_findings():
            print(finding.format(), file=sys.stderr)
    blocking = len(result.errors) + (len(result.warnings) if strict else 0)
    if blocking:
        if text_mode:
            print(f"FAIL {display}: {blocking} blocking finding(s)", file=sys.stderr)
        return False
    return True


def _summary_line(display: str, source: UrdfSource) -> str:
    movable = sum(1 for joint in source.joints if joint.joint_type != "fixed")
    mass_text = f", total mass {source.total_mass:.4g} kg" if source.total_mass > 0 else ""
    return (
        f"OK {display}: robot {source.robot_name!r}, root {source.root_link!r}, "
        f"{len(source.links)} links, {len(source.joints)} joints ({movable} movable), "
        f"{len(source.mesh_paths)} resolved mesh references{mass_text}"
    )


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
