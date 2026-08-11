from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sdf.external import run_gz_sdf_check
from sdf.source import SdfSource, SdfSourceError, parse_sdf_xml
from sdf.validation import validate_sdf_xml

SDF_SUFFIX = ".sdf"


def validate_sdf_targets(
    targets: Sequence[str],
    *,
    gz_check: str = "auto",
    strict: bool = False,
    output_format: str = "text",
) -> int:
    target_paths = [_resolve_target_path(target) for target in targets]
    reports: list[dict[str, object]] = []
    failed = False
    for target_path in target_paths:
        report = _validate_target(target_path, gz_check=gz_check, strict=strict, output_format=output_format)
        reports.append(report)
        if not report["ok"]:
            failed = True
    if output_format == "json":
        print(json.dumps({"files": reports}, indent=2))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/validate",
        description="Validate explicit SDFormat/SDF targets.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Explicit .sdf file to validate.",
    )
    parser.add_argument(
        "--gz-check",
        choices=("auto", "required", "never"),
        default="auto",
        help="Optionally run 'gz sdf --check' as external validation.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat bundled validation warnings as failures.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output format: human-readable text (default) or a JSON findings document.",
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
            print(f"[sdf] validating {target}", file=sys.stderr)
    return validate_sdf_targets(
        args.targets,
        gz_check=args.gz_check,
        strict=args.strict,
        output_format=args.output_format,
    )


def _resolve_target_path(raw_target: object) -> Path:
    value = str(raw_target or "").strip()
    if not value:
        raise ValueError("sdf target must be a non-empty path")
    target_path = Path(value).expanduser()
    return target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()


def _validate_target(
    target_path: Path,
    *,
    gz_check: str,
    strict: bool,
    output_format: str,
) -> dict[str, object]:
    display = _display_path(target_path)
    text_mode = output_format == "text"
    if target_path.suffix.lower() != SDF_SUFFIX:
        return _report_precheck_failure(display, "target must be a .sdf file", text_mode)
    if not target_path.is_file():
        return _report_precheck_failure(display, "file not found", text_mode)
    try:
        xml_text = target_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _report_precheck_failure(display, str(exc), text_mode)

    validation = validate_sdf_xml(xml_text, source_path=target_path, base_dir=target_path.parent)
    validation.extend(run_gz_sdf_check(xml_text, output_path=target_path, mode=gz_check))
    validation = validation.deduplicated()

    if text_mode:
        for finding in validation.all_findings():
            print(finding.format(), file=sys.stderr)
    blocking = len(validation.errors) + (len(validation.warnings) if strict else 0)
    summary = ""
    ok = not blocking
    if ok:
        try:
            source = parse_sdf_xml(xml_text, source_path=target_path, base_dir=target_path.parent)
            summary = _summary_line(display, source)
        except SdfSourceError as exc:
            ok = False
            if text_mode:
                print(f"FAIL {display}: {exc}", file=sys.stderr)
    if text_mode:
        if ok and summary:
            print(summary)
        elif blocking:
            print(f"FAIL {display}: {blocking} blocking finding(s)", file=sys.stderr)
    return {
        "path": display,
        "ok": ok,
        "summary": summary,
        "findings": [finding.to_dict() for finding in validation.all_findings()],
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


def _summary_line(display: str, source: SdfSource) -> str:
    scope = []
    if source.world_names:
        scope.append(f"worlds {list(source.world_names)!r}")
    if source.model_names:
        scope.append(f"models {list(source.model_names)!r}")
    scope_text = ", ".join(scope) if scope else "no models or worlds"
    return (
        f"OK {display}: SDF {source.version}, {scope_text}, "
        f"{len(source.links)} links, {len(source.joints)} joints, "
        f"{len(source.mesh_paths)} resolved mesh references"
    )


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
