from __future__ import annotations

import argparse
import contextlib
import io
import json
import shlex
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    package_dir = Path(__file__).resolve().parent
    inspect_dir = package_dir.parent
    scripts_dir = inspect_dir.parent
    sys.path.insert(0, str(scripts_dir))
    from cadpy_common.package_path import ensure_cadpy_package_path

    ensure_cadpy_package_path()
else:
    from cadpy_common.package_path import ensure_cadpy_package_path

    ensure_cadpy_package_path()

from cadpy.cli_logging import CliLogger


def _inspect_api():
    if __package__ in {None, ""}:
        from cadpy_inspect.inspect_refs import inspect
    else:
        from . import inspect
    return inspect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect",
        description="Inspect selector refs, geometry facts, and measurements.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  inspect refs STEP/foo.step '#f9' --detail --facts\n"
            "  inspect measure STEP/foo.step --from '#f1' --to '#f2' --axis z\n"
            "  inspect align STEP/foo.step --moving '#f1' --target '#f2' --mode flush --axis z\n"
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show detailed progress and timing information.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    refs_parser = subparsers.add_parser(
        "refs",
        help="Resolve whole-entry or selector refs from generated GLB topology.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  inspect refs STEP/foo.step '#f9' --detail --facts\n"
            "  inspect refs STEP/foo.step '#f1' '#e2' --positioning\n"
            "  inspect refs STEP/foo.step --input-file /tmp/refs.txt --planes\n"
        ),
    )
    refs_parser.add_argument(
        "inputs",
        nargs="*",
        help="STEP/CAD entry target followed by optional selector refs like #o1.2.f1.",
    )
    refs_parser.add_argument(
        "--input-file",
        type=Path,
        help="Read token text from a file instead of CLI input or stdin.",
    )
    refs_parser.add_argument(
        "--detail",
        action="store_true",
        help="Include detailed geometry facts for selected face/edge refs.",
    )
    refs_parser.add_argument(
        "--facts",
        action="store_true",
        help="Include compact geometry facts for whole-entry refs and resolved selectors.",
    )
    refs_parser.add_argument(
        "--positioning",
        action="store_true",
        help="Include placement-ready frame, point, plane, axis, and coordinate facts.",
    )
    refs_parser.add_argument(
        "--planes",
        action="store_true",
        help="Include grouped major planar faces for each whole entry.",
    )
    _add_plane_report_arguments(refs_parser)
    refs_parser.add_argument(
        "--topology",
        action="store_true",
        help="Include full face/edge selector lists for whole-entry refs. Expensive on large topology GLBs.",
    )
    _add_output_arguments(refs_parser)
    refs_parser.set_defaults(handler=run_refs)

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two CAD STEP refs and summarize selector-level changes.",
    )
    diff_parser.add_argument("left", help="Left CAD STEP path.")
    diff_parser.add_argument("right", help="Right CAD STEP path.")
    diff_parser.add_argument(
        "--planes",
        action="store_true",
        help="Include major planar face groups for both sides.",
    )
    _add_plane_report_arguments(diff_parser)
    _add_output_arguments(diff_parser)
    diff_parser.set_defaults(handler=run_diff)

    frame_parser = subparsers.add_parser(
        "frame",
        help="Return the world frame for an occurrence or selector's owning occurrence.",
    )
    frame_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    frame_parser.add_argument("selector", nargs="?", default="", help="Optional selector ref such as #o1.2.")
    _add_output_arguments(frame_parser)
    frame_parser.set_defaults(handler=run_frame)

    measure_parser = subparsers.add_parser(
        "measure",
        help="Measure signed coordinate distance between two selectors in one STEP entry.",
    )
    measure_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    measure_parser.add_argument("--from", dest="from_selector", required=True, help="Moving/source selector ref.")
    measure_parser.add_argument("--to", dest="to_selector", required=True, help="Target selector ref.")
    measure_parser.add_argument("--axis", choices=("x", "y", "z"), help="Axis to measure along. Inferred when possible.")
    _add_output_arguments(measure_parser)
    measure_parser.set_defaults(handler=run_measure)

    align_parser = subparsers.add_parser(
        "align",
        help="Calculate a read-only translation delta for simple selector alignment.",
    )
    align_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    align_parser.add_argument("--moving", required=True, help="Moving/source selector ref.")
    align_parser.add_argument("--target", required=True, help="Target selector ref.")
    align_parser.add_argument("--mode", choices=("flush", "center"), default="flush", help="Alignment mode. Default: flush.")
    align_parser.add_argument("--offset", type=float, default=0.0, help="Offset in mm. For flush, applies along target normal when axis-aligned.")
    align_parser.add_argument("--axis", choices=("x", "y", "z"), help="Axis to use for flush or one-axis center alignment.")
    _add_output_arguments(align_parser)
    align_parser.set_defaults(handler=run_align)

    worker_parser = subparsers.add_parser(
        "worker",
        help="Run a persistent JSONL inspect worker.",
        description=(
            "Read JSONL requests from stdin and write one JSONL response per request. "
            "Each request is an object with argv: [<inspect-subcommand>, ...] and optional id."
        ),
    )
    worker_parser.set_defaults(handler=run_worker)

    batch_parser = subparsers.add_parser(
        "batch",
        help="Run JSONL inspect requests from stdin in one process.",
        description=worker_parser.description,
    )
    batch_parser.set_defaults(handler=run_worker)

    return parser


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json", help="Output format. Default: json.")
    parser.add_argument("--quiet", action="store_true", help="Reduce nonessential output.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Include extra human-readable detail where available.",
    )


def _add_plane_report_arguments(
    parser: argparse.ArgumentParser,
    *,
    prefix: str = "plane-",
) -> None:
    coordinate_flags = [f"--{prefix}coordinate-tolerance"]
    area_flags = [f"--{prefix}min-area-ratio"]
    limit_flags = [f"--{prefix}limit"]
    parser.add_argument(
        *coordinate_flags,
        dest="plane_coordinate_tolerance",
        type=float,
        default=1e-3,
        help="Merge planar face groups whose axis coordinate differs by at most this value. Default: 0.001",
    )
    parser.add_argument(
        *area_flags,
        dest="plane_min_area_ratio",
        type=float,
        default=0.05,
        help="Drop planar groups smaller than this fraction of total planar area. Default: 0.05",
    )
    parser.add_argument(
        *limit_flags,
        dest="plane_limit",
        type=int,
        default=12,
        help="Maximum number of plane groups to emit. Default: 12",
    )


def run_refs(args: argparse.Namespace) -> int:
    inspect = _inspect_api()
    try:
        entry_target, refs_text = _read_refs_input(args)
        result = inspect.inspect_cad_refs(
            entry_target,
            refs_text,
            detail=bool(args.detail),
            include_topology=bool(args.topology),
            facts=bool(args.facts),
            positioning=bool(args.positioning),
            planes=bool(args.planes),
            plane_coordinate_tolerance=float(args.plane_coordinate_tolerance),
            plane_min_area_ratio=float(args.plane_min_area_ratio),
            plane_limit=int(args.plane_limit),
        )
    except inspect.CadRefError as exc:
        result = {
            "ok": False,
            "tokens": [],
            "errors": [inspect.cad_ref_error_payload(exc)],
        }

    _emit_result(args, result, _format_refs_text)
    return 0 if bool(result.get("ok")) else 2


def run_diff(args: argparse.Namespace) -> int:
    inspect = _inspect_api()
    try:
        result = inspect.diff_entry_targets(
            args.left,
            args.right,
            planes=bool(args.planes),
            plane_coordinate_tolerance=float(args.plane_coordinate_tolerance),
            plane_min_area_ratio=float(args.plane_min_area_ratio),
            plane_limit=int(args.plane_limit),
        )
    except inspect.CadRefError as exc:
        result = {
            "ok": False,
            "left": {"cadPath": _safe_cad_path(args.left)},
            "right": {"cadPath": _safe_cad_path(args.right)},
            "errors": [inspect.cad_ref_error_payload(exc)],
        }

    _emit_result(args, result, _format_diff_text)
    return 0 if bool(result.get("ok")) else 2


def run_frame(args: argparse.Namespace) -> int:
    inspect = _inspect_api()
    try:
        result = inspect.inspect_target_frame(args.entry, args.selector)
    except inspect.CadRefError as exc:
        result = {
            "ok": False,
            "target": args.entry,
            "errors": [inspect.cad_ref_error_payload(exc)],
        }

    _emit_result(args, result, _format_frame_text)
    return 0 if bool(result.get("ok")) else 2


def run_measure(args: argparse.Namespace) -> int:
    inspect = _inspect_api()
    try:
        result = inspect.measure_targets(args.entry, args.from_selector, args.to_selector, axis=args.axis)
    except inspect.CadRefError as exc:
        result = {
            "ok": False,
            "entry": args.entry,
            "from": args.from_selector,
            "to": args.to_selector,
            "errors": [inspect.cad_ref_error_payload(exc)],
        }

    _emit_result(args, result, _format_measure_text)
    return 0 if bool(result.get("ok")) else 2


def run_align(args: argparse.Namespace) -> int:
    inspect = _inspect_api()
    try:
        result = inspect.align_targets(
            args.entry,
            args.moving,
            args.target,
            mode=args.mode,
            offset=float(args.offset),
            axis=args.axis,
        )
    except inspect.CadRefError as exc:
        result = {
            "ok": False,
            "entry": args.entry,
            "moving": args.moving,
            "target": args.target,
            "errors": [inspect.cad_ref_error_payload(exc)],
        }

    _emit_result(args, result, _format_align_text)
    return 0 if bool(result.get("ok")) else 2


def run_worker(args: argparse.Namespace) -> int:
    _ = args
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        response = _worker_response(line)
        print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


def _worker_response(line: str) -> dict[str, object]:
    request_id: object = None
    try:
        request = json.loads(line)
        argv = _worker_request_argv(request)
        if isinstance(request, dict):
            request_id = request.get("id")
        exit_code, result = inspect_command_result(argv)
    except Exception as exc:
        exit_code = 2
        result = {
            "ok": False,
            "errors": [_exception_error_payload(exc)],
        }
    response: dict[str, object] = {
        "ok": exit_code == 0,
        "exitCode": exit_code,
        "result": result,
    }
    if request_id is not None:
        response["id"] = request_id
    return response


def _worker_request_argv(request: object) -> list[str]:
    if isinstance(request, dict):
        raw_argv = request.get("argv")
    else:
        raw_argv = request
    if isinstance(raw_argv, str):
        return shlex.split(raw_argv)
    if isinstance(raw_argv, list) and all(isinstance(item, (str, int, float)) for item in raw_argv):
        return [str(item) for item in raw_argv]
    raise ValueError("Worker request must be a JSON object with argv, a JSON argv array, or a shell-style argv string.")


def inspect_command_result(argv: Sequence[str]) -> tuple[int, dict[str, object]]:
    command_argv = [str(item) for item in argv]
    if not command_argv:
        return 2, {"ok": False, "errors": [{"message": "empty inspect command"}]}
    if command_argv[0] in {"worker", "batch"}:
        return 2, {"ok": False, "errors": [{"message": f"Unsupported worker command: {command_argv[0]}"}]}
    stderr = io.StringIO()
    try:
        parser = build_parser()
        with contextlib.redirect_stderr(stderr):
            args = parser.parse_args(command_argv)
    except SystemExit as exc:
        return _system_exit_result(exc, stderr=stderr.getvalue())

    try:
        if args.command == "refs":
            if not args.inputs and not args.input_file:
                raise _inspect_api().CadRefError("No STEP/CAD entry target provided.")
            entry_target, refs_text = _read_refs_input(args)
            inspect = _inspect_api()
            result = inspect.inspect_cad_refs(
                entry_target,
                refs_text,
                detail=bool(args.detail),
                include_topology=bool(args.topology),
                facts=bool(args.facts),
                positioning=bool(args.positioning),
                planes=bool(args.planes),
                plane_coordinate_tolerance=float(args.plane_coordinate_tolerance),
                plane_min_area_ratio=float(args.plane_min_area_ratio),
                plane_limit=int(args.plane_limit),
            )
        elif args.command == "diff":
            inspect = _inspect_api()
            result = inspect.diff_entry_targets(
                args.left,
                args.right,
                planes=bool(args.planes),
                plane_coordinate_tolerance=float(args.plane_coordinate_tolerance),
                plane_min_area_ratio=float(args.plane_min_area_ratio),
                plane_limit=int(args.plane_limit),
            )
        elif args.command == "frame":
            result = _inspect_api().inspect_target_frame(args.entry, args.selector)
        elif args.command == "measure":
            result = _inspect_api().measure_targets(args.entry, args.from_selector, args.to_selector, axis=args.axis)
        elif args.command == "align":
            result = _inspect_api().align_targets(
                args.entry,
                args.moving,
                args.target,
                mode=args.mode,
                offset=float(args.offset),
                axis=args.axis,
            )
        else:
            raise _inspect_api().CadRefError(f"Unsupported inspect command: {args.command}")
    except _inspect_api().CadRefError as exc:
        result = {"ok": False, "errors": [_inspect_api().cad_ref_error_payload(exc)]}
    except Exception as exc:
        result = {"ok": False, "errors": [_exception_error_payload(exc)]}
    return (0 if bool(result.get("ok")) else 2), result


def _system_exit_result(exc: SystemExit, *, stderr: str = "") -> tuple[int, dict[str, object]]:
    try:
        exit_code = int(exc.code or 0)
    except (TypeError, ValueError):
        exit_code = 2
    ok = exit_code == 0
    message = stderr.strip() or str(exc)
    return exit_code, {"ok": ok, "errors": [] if ok else [{"message": message}]}


def _exception_error_payload(exc: Exception) -> dict[str, object]:
    inspect = _inspect_api()
    if isinstance(exc, inspect.CadRefError):
        return inspect.cad_ref_error_payload(exc)
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _emit_result(args: argparse.Namespace, result: dict[str, object], text_formatter) -> None:
    if getattr(args, "format", "json") == "text":
        text = text_formatter(
            result,
            quiet=bool(getattr(args, "quiet", False)),
            verbose=bool(getattr(args, "verbose", False)),
        )
        if text:
            print(text)
        return
    indent = None if bool(getattr(args, "quiet", False)) else 2
    print(json.dumps(result, indent=indent, sort_keys=False))


def _format_refs_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    lines: list[str] = []
    for token in result.get("tokens", []):
        if not isinstance(token, dict):
            continue
        summary = token.get("summary") if isinstance(token.get("summary"), dict) else {}
        headline = f"{token.get('cadPath')} faces={summary.get('faceCount')} edges={summary.get('edgeCount')}"
        lines.append(headline)
        if quiet:
            continue
        entry_facts = token.get("entryFacts") if isinstance(token.get("entryFacts"), dict) else {}
        if entry_facts:
            lines.append(f"  facts: {_format_entry_facts_text(entry_facts)}")
        entry_positioning = token.get("entryPositioning") if isinstance(token.get("entryPositioning"), dict) else {}
        if entry_positioning:
            bbox_facts = entry_positioning.get("bboxFacts") if isinstance(entry_positioning.get("bboxFacts"), dict) else {}
            if bbox_facts and bbox_facts != entry_facts:
                lines.append(f"  positioning: {_format_entry_facts_text(bbox_facts)}")
        planes = token.get("planes") if isinstance(token.get("planes"), list) else []
        if planes:
            lines.extend(_format_planes_text(planes))
        for selection in token.get("selections", []):
            if isinstance(selection, dict):
                lines.append(f"  {selection.get('displaySelector')}: {selection.get('summary')}")
                if verbose and selection.get("copyText"):
                    lines.append(f"    {selection.get('copyText')}")
    return "\n".join(lines)


def _format_number(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _format_vector(value: object) -> str:
    if not isinstance(value, list):
        return str(value)
    return "[" + ", ".join(_format_number(component) for component in value) + "]"


def _format_entry_facts_text(facts: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("size", "center", "extentAxis", "diag", "kind"):
        if key not in facts:
            continue
        value = facts.get(key)
        if isinstance(value, list):
            parts.append(f"{key}={_format_vector(value)}")
        else:
            parts.append(f"{key}={_format_number(value)}")
    return " ".join(parts)


def _format_planes_text(planes: list[object], *, limit: int = 3) -> list[str]:
    lines = [f"  planes: {len(planes)} major groups"]
    for plane in planes[:limit]:
        if not isinstance(plane, dict):
            continue
        axis = plane.get("axis")
        coordinate = _format_number(plane.get("coordinate"))
        normal_sign = plane.get("normalSign")
        face_count = plane.get("faceCount")
        area = _format_number(plane.get("totalArea"))
        lines.append(
            f"    {axis}={coordinate} normalSign={normal_sign} faces={face_count} area={area}"
        )
    if len(planes) > limit:
        lines.append(f"    ... {len(planes) - limit} more")
    return lines


def _format_diff_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    diff = result.get("diff") if isinstance(result.get("diff"), dict) else {}
    fields = ("topologyChanged", "geometryChanged", "bboxChanged", "kindChanged")
    lines = [", ".join(f"{field}={diff.get(field)}" for field in fields)]
    if not quiet:
        lines.append(f"faceDelta={diff.get('faceCountDelta')} edgeDelta={diff.get('edgeCountDelta')}")
    if verbose:
        lines.append(f"sizeDelta={diff.get('sizeDelta')} centerDelta={diff.get('centerDelta')}")
    return "\n".join(lines)


def _format_frame_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    frame = result.get("frame") if isinstance(result.get("frame"), dict) else {}
    lines = [f"{result.get('copyText', result.get('cadPath'))} translation={frame.get('translation')}"]
    if verbose and not quiet:
        lines.append(f"localAxes={frame.get('localAxes')}")
    return "\n".join(lines)


def _format_measure_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    measurement = result.get("measurement") if isinstance(result.get("measurement"), dict) else {}
    lines = [
        f"axis={result.get('axis')} signed={measurement.get('signedDistance')} absolute={measurement.get('absoluteDistance')}"
    ]
    if verbose and not quiet:
        lines.append(f"euclidean={measurement.get('euclideanDistance')} vector={measurement.get('vectorRelationship')}")
    return "\n".join(lines)


def _format_align_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    alignment = result.get("alignment") if isinstance(result.get("alignment"), dict) else {}
    lines = [f"mode={result.get('mode')} axis={result.get('axis')} translation={alignment.get('translationVector')}"]
    if verbose and not quiet:
        lines.append(f"transformTranslationDelta={alignment.get('transformTranslationDelta')}")
    return "\n".join(lines)


def _format_errors(result: dict[str, object]) -> str:
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    messages = [str(error.get("message")) for error in errors if isinstance(error, dict) and error.get("message")]
    return "\n".join(messages) if messages else "error"


def _read_refs_input(args: argparse.Namespace) -> tuple[str, str]:
    inspect = _inspect_api()
    raw_inputs = [str(value) for value in getattr(args, "inputs", ()) if str(value).strip()]
    if args.input_file:
        if len(raw_inputs) != 1:
            raise inspect.CadRefError("Pass exactly one STEP/CAD entry target with --input-file.")
        try:
            text = args.input_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise inspect.CadRefError(f"Failed to read input file: {args.input_file}") from exc
        entry_target = raw_inputs[0]
    else:
        if not raw_inputs:
            raise inspect.CadRefError("No STEP/CAD entry target provided.")
        entry_target = raw_inputs[0]
        text = "\n".join(raw_inputs[1:])

    try:
        inspect.entry_target_from_target(entry_target)
    except inspect.CadRefError as exc:
        raise inspect.CadRefError(f"Invalid STEP/CAD entry target: {entry_target}") from exc

    if not str(text).strip():
        return entry_target, ""

    nonempty_lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    for line in nonempty_lines:
        parsed_tokens = inspect.syntax.parse_cad_tokens(line)
        if len(parsed_tokens) != 1 or parsed_tokens[0].token.strip() != line:
            raise inspect.CadRefError(f"Invalid selector ref {line!r}; expected #o1.2, #f1, or #o1.2.f1.")
    return entry_target, "\n".join(nonempty_lines)


def _safe_cad_path(target: str) -> str:
    inspect = _inspect_api()
    try:
        return inspect.cad_path_from_target(target)
    except inspect.CadRefError:
        return str(target)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command_label = str(getattr(args, "command", "inspect") or "inspect")
    logger = CliLogger("scripts/inspect", verbose=bool(getattr(args, "verbose", False)))
    try:
        with logger.timed(command_label):
            return int(args.handler(args))
    except _inspect_api().CadRefError as exc:
        _emit_result(args, {"ok": False, "errors": [_inspect_api().cad_ref_error_payload(exc)]}, _format_errors)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
