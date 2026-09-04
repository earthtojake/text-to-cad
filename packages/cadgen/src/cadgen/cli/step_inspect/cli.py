from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
from typing import Sequence

from cadgen.cli_logging import CliLogger


def _inspect_api():
    from . import inspect

    return inspect


# The skill entrypoint's name, which is what `--help` must say when invoked that way.
# `cadgen <command>` passes its own name instead, so each front door names itself.
DEFAULT_PROG = "cadgen step inspect"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Inspect selector refs, geometry facts, and measurements.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  cadgen step inspect refs STEP/foo.step '#f9' --detail --facts\n"
            "  cadgen step inspect measure STEP/foo.step --from '#f1' --to '#f2' --axis z\n"
            "  cadgen step inspect align STEP/foo.step --moving '#f1' --target '#f2' --mode flush --axis z\n"
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
            "  cadgen step inspect refs STEP/foo.step '#f9' --detail --facts\n"
            "  cadgen step inspect refs STEP/foo.step '#f1' '#e2' --positioning\n"
            "  cadgen step inspect refs STEP/foo.step --input-file /tmp/refs.txt --planes\n"
        ),
    )
    refs_parser.add_argument(
        "inputs",
        nargs="*",
        help=(
            "STEP/CAD entry target followed by optional selector refs like #o1.2.f1. "
            "An occurrence ref may name a subassembly; it reports the parts beneath it."
        ),
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
    refs_parser.set_defaults(handler=run_subcommand)

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
    diff_parser.set_defaults(handler=run_subcommand)

    frame_parser = subparsers.add_parser(
        "frame",
        help="Return the world frame for an occurrence or selector's owning occurrence.",
        description=(
            "A part ref reports that occurrence's transform. A SUBASSEMBLY ref reports "
            "the branch: its name from the instance tree, and the extent and center of "
            "the parts beneath it. Group placement is baked into each part's absolute "
            "transform, so a subassembly node has no transform of its own to report."
        ),
    )
    frame_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    frame_parser.add_argument(
        "selector",
        nargs="?",
        default="",
        help="Optional selector ref such as #o1.2, which may name a subassembly.",
    )
    _add_output_arguments(frame_parser)
    frame_parser.set_defaults(handler=run_subcommand)

    measure_parser = subparsers.add_parser(
        "measure",
        help="Measure signed coordinate distance between two selectors in one STEP entry.",
    )
    measure_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    measure_parser.add_argument("--from", dest="from_selector", required=True, help="Moving/source selector ref.")
    measure_parser.add_argument("--to", dest="to_selector", required=True, help="Target selector ref.")
    measure_parser.add_argument("--axis", choices=("x", "y", "z"), help="Axis to measure along. Inferred when possible.")
    _add_output_arguments(measure_parser)
    measure_parser.set_defaults(handler=run_subcommand)

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
    align_parser.set_defaults(handler=run_subcommand)

    interfere_parser = subparsers.add_parser(
        "interfere",
        help="Report part-vs-part interpenetration as boolean intersection volume.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  cadgen step inspect interfere models/car/car.step.py\n"
            "  cadgen step inspect interfere models/car/car.step.py --refs o1.1,o1.7\n"
            "  cadgen step inspect interfere models/car/car.step --tolerance 25\n"
        ),
    )
    interfere_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    interfere_parser.add_argument(
        "--refs",
        default="",
        help="Comma-separated occurrence refs to restrict the check to. A ref matches its whole subtree.",
    )
    interfere_parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Intersection volume (mm^3) below which an overlap counts as contact, not a clash.",
    )
    interfere_parser.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Cap the number of boolean tests. Truncated pairs are reported in stats.",
    )
    _add_output_arguments(interfere_parser)
    interfere_parser.set_defaults(handler=run_subcommand)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Report per-solid geometric validity: topology, closure, and orientation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Check each leaf occurrence for topological validity, watertightness, "
            "self-intersection, and positive volume. This is the geometry-soundness "
            "check; `refs --facts` reports counts and bounds and its \"ok\" field "
            "covers ref resolution only.\n\n"
            "Occurrences that share one shape (the same part placed many times) are "
            "checked ONCE for topology, closure, solid presence and volume, in parallel "
            "across a process pool (CADGEN_VALIDATE_WORKERS overrides the size; 1 runs "
            "in-process), and a finding names every occurrence it applies to. The "
            "self-intersection test is numeric and can differ by placement, so by "
            "default it runs once per shape at its first placement -- the report says so "
            "in selfIntersectionCheck -- and --every-placement runs it on every copy.\n\n"
            "A stale generated document is rebuilt from its script first; that decision is "
            "announced on stderr.\n\n"
            "examples:\n"
            "  cadgen step inspect validate models/car/car.step\n"
            "  cadgen step inspect validate models/car/car.step --refs o1.1,o1.7\n"
            "  cadgen step inspect validate models/panel/panel.step --allow-open\n"
            "  cadgen step inspect validate models/car/car.step --every-placement --out validate.json\n"
        ),
    )
    validate_parser.add_argument("entry", help="CAD STEP path or CAD entry target.")
    validate_parser.add_argument(
        "--refs",
        default="",
        help="Comma-separated occurrence refs to restrict the check to. A ref matches its whole subtree.",
    )
    validate_parser.add_argument(
        "--allow-open",
        action="store_true",
        help="Treat surface/shell geometry as intended, suppressing openShell and noSolid findings.",
    )
    validate_parser.add_argument(
        "--skip-self-intersection",
        action="store_true",
        help="Skip the boolean self-intersection test, which dominates runtime on large assemblies.",
    )
    validate_parser.add_argument(
        "--every-placement",
        action="store_true",
        help=(
            "Run the self-intersection test on every placed copy of a shape, not once at its "
            "first placement. Topology, closure and volume are still checked once per shape."
        ),
    )
    validate_parser.add_argument(
        "--out",
        default=None,
        help=(
            "Also write the JSON report to this path, rewritten after every shape checked "
            "with \"partial\": true until the run completes -- so a killed run leaves a "
            "readable document. Stdout still carries the final report."
        ),
    )
    _add_output_arguments(validate_parser)
    validate_parser.set_defaults(handler=run_subcommand)

    # Output is ALWAYS JSON; `--json` is accepted on every subcommand so
    # muscle memory from verbs that need the flag does not error.
    for subparser in subparsers.choices.values():
        subparser.add_argument(
            "--json",
            action="store_true",
            dest="_json_noop",
            help="Accepted for symmetry with other tools; output is always JSON.",
        )

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


# --- the subcommands, each a shell over cadgen.step.inspect -------------------
#
# The verb owns the inspection; the CLI owns argv. So a subcommand is TWO small
# things -- how to read its namespace into a verb call, and how to format the
# report that comes back -- and both the printing front door and the in-process
# runner below drive them, so the CLI and a Python caller cannot come to answer
# the same question differently (design/format-doors.md).
#
# `identity` is the fields a subcommand's error report carried before the verb
# was reached: they name what the CALLER asked about, which is something the
# verb never sees, and a resolution failure never gets far enough to include.


def _inspect_verb():
    from cadgen import step

    return step.inspect


def _comma_refs(args: argparse.Namespace) -> list[str]:
    return [ref for ref in str(getattr(args, "refs", "") or "").split(",") if ref.strip()]


def _refs_call(args: argparse.Namespace) -> dict:
    entry_target, refs_text = _read_refs_input(args)
    return {
        "target": entry_target,
        "refs": refs_text.splitlines(),
        "inspection": "refs",
        "detail": bool(args.detail),
        "topology": bool(args.topology),
        "facts": bool(args.facts),
        "positioning": bool(args.positioning),
        "planes": bool(args.planes),
        "plane_coordinate_tolerance": float(args.plane_coordinate_tolerance),
        "plane_min_area_ratio": float(args.plane_min_area_ratio),
        "plane_limit": int(args.plane_limit),
    }


def _diff_call(args: argparse.Namespace) -> dict:
    return {
        "target": args.left,
        "against": args.right,
        "inspection": "diff",
        "planes": bool(args.planes),
        "plane_coordinate_tolerance": float(args.plane_coordinate_tolerance),
        "plane_min_area_ratio": float(args.plane_min_area_ratio),
        "plane_limit": int(args.plane_limit),
    }


# subcommand -> (verb call from argv, identity fields, extra exceptions to report
# rather than raise, text formatter).
_SUBCOMMANDS: dict[str, tuple] = {
    "refs": (_refs_call, lambda args: {"tokens": []}, (), lambda: _format_refs_text),
    "diff": (
        _diff_call,
        lambda args: {
            "left": {"document": _safe_cad_path(args.left)},
            "right": {"document": _safe_cad_path(args.right)},
        },
        (),
        lambda: _format_diff_text,
    ),
    "frame": (
        lambda args: {
            "target": args.entry,
            "refs": [args.selector] if args.selector else [],
            "inspection": "frame",
        },
        lambda args: {"target": args.entry},
        (),
        lambda: _format_frame_text,
    ),
    "measure": (
        lambda args: {
            "target": args.entry,
            "refs": [args.from_selector, args.to_selector],
            "inspection": "measure",
            "axis": args.axis or "",
        },
        lambda args: {"entry": args.entry, "from": args.from_selector, "to": args.to_selector},
        (),
        lambda: _format_measure_text,
    ),
    "align": (
        lambda args: {
            "target": args.entry,
            "inspection": "align",
            "moving": args.moving,
            "onto": args.target,
            "align_mode": args.mode,
            "offset": float(args.offset),
            "axis": args.axis or "",
        },
        lambda args: {"entry": args.entry, "moving": args.moving, "target": args.target},
        (),
        lambda: _format_align_text,
    ),
    # The two that reach the kernel directly, so an OCP failure is a finding
    # rather than a traceback through the CLI.
    "interfere": (
        lambda args: {
            "target": args.entry,
            "refs": _comma_refs(args),
            "inspection": "interfere",
            "tolerance": args.tolerance,
            "max_pairs": args.max_pairs,
        },
        lambda args: {"entry": args.entry},
        (OSError, RuntimeError, ValueError),
        lambda: _format_interfere_text,
    ),
    "validate": (
        lambda args: {
            "target": args.entry,
            "refs": _comma_refs(args),
            "inspection": "validate",
            "allow_open": bool(getattr(args, "allow_open", False)),
            "skip_self_intersection": bool(getattr(args, "skip_self_intersection", False)),
            "every_placement": bool(getattr(args, "every_placement", False)),
            "out": Path(args.out) if getattr(args, "out", None) else None,
        },
        lambda args: {"entry": args.entry},
        (OSError, RuntimeError, ValueError),
        lambda: _format_validate_text,
    ),
}


def _with_identity(report: dict, identity: dict | None) -> dict:
    """``report`` with the caller's identity fields folded in.

    ``ok`` stays first and the report's own values win: the key ORDER is what a
    reader of these documents has always seen.
    """
    rest = {key: value for key, value in report.items() if key != "ok"}
    return {"ok": bool(report.get("ok")), **(identity or {}), **rest}


def inspect_report(args: argparse.Namespace) -> tuple[bool, dict]:
    """One subcommand's ``(ok, report)``, whoever is asking."""
    inspect = _inspect_api()
    build_call, identity, catch, _ = _SUBCOMMANDS[args.command]
    try:
        call = build_call(args)
    except inspect.CadRefError as exc:
        # Reading the subcommand's own input failed (a missing entry target, an
        # unreadable --input-file); the verb was never reached.
        return False, _with_identity(
            {"ok": False, "errors": [inspect.cad_ref_error_payload(exc)]}, identity(args)
        )
    try:
        result = _inspect_verb()(**call)
    except (inspect.CadRefError, *catch) as exc:
        payload = (
            inspect.cad_ref_error_payload(exc)
            if isinstance(exc, inspect.CadRefError)
            else {"message": str(exc)}
        )
        return False, _with_identity({"ok": False, "errors": [payload]}, identity(args))
    if result.ok:
        return True, result.report
    return False, _with_identity(result.report, identity(args))


def run_subcommand(args: argparse.Namespace) -> int:
    """The parser's handler for every subcommand: inspect, then print."""
    ok, report = inspect_report(args)
    _emit_result(args, report, _SUBCOMMANDS[args.command][3]())
    return 0 if ok else 2


def inspect_command_result(argv: Sequence[str]) -> tuple[int, dict[str, object]]:
    """Run one inspect command IN PROCESS, returning ``(exit code, report)``.

    The same subcommand table the printing front door uses, so this cannot drift
    from what `cadgen step inspect` answers. Only the failure handling differs:
    a caller in-process gets an argparse exit turned into a report rather than a
    SystemExit, and gets ANY exception reported rather than raised — nothing here
    may take a worker down.
    """
    command_argv = [str(item) for item in argv]
    if not command_argv:
        return 2, {"ok": False, "errors": [{"message": "empty inspect command"}]}
    stderr = io.StringIO()
    try:
        parser = build_parser()
        with contextlib.redirect_stderr(stderr):
            args = parser.parse_args(command_argv)
    except SystemExit as exc:
        return _system_exit_result(exc, stderr=stderr.getvalue())

    try:
        ok, report = inspect_report(args)
    except Exception as exc:  # noqa: BLE001 - a worker must get a payload, never a raise
        return 2, {"ok": False, "errors": [_exception_error_payload(exc)]}
    return (0 if ok else 2), report


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
    # Compact, always. JSON here is read by an agent; indentation was 38% of the payload on
    # a large model and a person who wants it laid out can pipe through `jq .`. --quiet
    # still shapes the TEXT format (--format text), which is where it means something.
    print(json.dumps(result, separators=(",", ":"), sort_keys=False))


def _format_refs_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    lines: list[str] = []
    for token in result.get("tokens", []):
        if not isinstance(token, dict):
            continue
        summary = token.get("summary") if isinstance(token.get("summary"), dict) else {}
        headline = f"{token.get('document')} faces={summary.get('faceCount')} edges={summary.get('edgeCount')}"
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


def _format_interfere_text(result: dict, *, quiet: bool = False, verbose: bool = False) -> str:
    errors = result.get("errors") or []
    if errors:
        return "\n".join(str(error.get("message") or error) for error in errors)
    stats = result.get("stats") or {}
    clashes = result.get("clashes") or []
    intra = result.get("intraPartOverlaps") or []
    root = result.get("root") or {}
    lines = [
        f"entry     : {result.get('entry', '')}",
        f"tolerance : {result.get('tolerance')} mm^3",
    ]
    if "parts" in stats:
        root_label = (
            f"{root.get('name') or ''} [{root.get('ref')}]".strip()
            if root.get("ref")
            else "the document roots"
        )
        lines.append(
            f"parts     : {stats.get('parts', 0)} components of {root_label}; "
            "a part's own bodies are not clashes"
        )
    lines.append(
        f"pairs     : {stats.get('pairs_tested', 0)} tested, "
        f"{stats.get('pairs_skipped_bbox', 0)} rejected by bbox, "
        f"{stats.get('pairs_total', 0)} total "
        f"({stats.get('occurrences', 0)} bodies)"
    )
    truncated = int(stats.get("pairs_truncated", 0) or 0)
    if truncated:
        lines.append(f"TRUNCATED : {truncated} pairs were not tested (--max-pairs)")

    def _clash_line(clash: dict) -> str:
        a = clash.get("a") or {}
        b = clash.get("b") or {}
        return (
            f"  {clash.get('volume', 0.0):12.1f} mm^3  "
            f"{a.get('name', '')} [{a.get('ref', '')}]  x  {b.get('name', '')} [{b.get('ref', '')}]"
        )

    def _intra_summary() -> list[str]:
        # Grouped per part: the count is what matters to the verdict's reader,
        # and 300 records of a servo's motor inside its case belong in --json.
        if not intra:
            return []
        by_part: dict[str, list[dict]] = {}
        for overlap in intra:
            part = overlap.get("part") or {}
            by_part.setdefault(f"{part.get('name', '')} [{part.get('ref', '')}]", []).append(overlap)
        out = [
            f"intra-part: {len(intra)} overlap(s) between bodies of one part in {len(by_part)} part(s) "
            "- not clashes; --refs <part> tests one part's bodies against each other"
        ]
        for label, overlaps in by_part.items():
            largest = max(float(o.get("volume", 0.0) or 0.0) for o in overlaps)
            out.append(f"  {label}: {len(overlaps)} overlap(s), largest {largest:.1f} mm^3")
        return out

    if not result.get("conclusive", True):
        reason = result.get("inconclusiveReason") or "no pairs were tested"
        lines.append(f"result    : INCONCLUSIVE - {reason}")
        lines.extend(_intra_summary())
        return "\n".join(lines)
    if not clashes:
        lines.append("result    : PASS - no interpenetration between parts above tolerance")
        lines.extend(_intra_summary())
        return "\n".join(lines)
    lines.append(f"result    : FAIL - {len(clashes)} clash(es)")
    lines.extend(_clash_line(clash) for clash in clashes)
    lines.extend(_intra_summary())
    return "\n".join(lines)


def _format_validate_text(result: dict, *, quiet: bool = False, verbose: bool = False) -> str:
    errors = result.get("errors") or []
    if errors:
        return "\n".join(str(error.get("message") or error) for error in errors)
    parts = result.get("parts") or []
    occurrences = result.get("occurrenceCount", 0)
    prototypes = result.get("prototypeCount")
    shapes = f" ({prototypes} unique shape(s))" if prototypes is not None else ""
    lines = [
        f"entry       : {result.get('entry', '')}",
        f"occurrences : {occurrences}{shapes}",
    ]
    mode = result.get("selfIntersectionCheck")
    if mode:
        lines.append(
            "self-int.   : "
            + {
                "first-placement": "checked once per shape, at its first placement (--every-placement checks each copy)",
                "every-placement": "checked on every placed copy",
                "skipped": "skipped (--skip-self-intersection)",
            }.get(str(mode), str(mode))
        )
    if result.get("partial"):
        lines.append(
            f"result      : PARTIAL - {result.get('checkedPrototypeCount', 0)}/{prototypes} shape(s) checked"
        )
    if not parts:
        if not result.get("partial"):
            lines.append("result      : PASS - all solids valid, closed, and positive volume")
        return "\n".join(lines)
    failures = result.get("failureCount", len(parts))
    lines.append(f"result      : FAIL - {failures} occurrence(s) in {len(parts)} finding(s)")
    for part in parts:
        reasons = ", ".join(part.get("reasons") or [])
        members = part.get("occurrences") or []
        more = f"  (+{len(members) - 1} more placement(s))" if len(members) > 1 else ""
        lines.append(f"  {reasons:44s} {part.get('name', '')} [{part.get('ref', '')}]{more}")
        if verbose:
            volumes = part.get("volumes") or []
            lines.append(f"      solids={part.get('solidCount', 0)} volumes={volumes}")
            if len(members) > 1:
                lines.append(
                    "      also: " + ", ".join(str(member.get("ref", "")) for member in members[1:])
                )
    return "\n".join(lines)


def _format_frame_text(result: dict[str, object], *, quiet: bool, verbose: bool) -> str:
    if not result.get("ok"):
        return _format_errors(result)
    frame = result.get("frame") if isinstance(result.get("frame"), dict) else {}
    head = str(result.get("copyText", result.get("document")))
    if result.get("occurrenceKind") == "group":
        # A subassembly node carries no transform of its own -- group placement lives in
        # each leaf's absolute transform -- so report the branch's extent, which is the
        # question a frame on a group is actually asking, and name the branch.
        members = result.get("members") if isinstance(result.get("members"), list) else []
        lines = [
            f"{head} group {frame.get('name', '')} "
            f"({len(members)} parts) center={frame.get('center')}"
        ]
        if verbose and not quiet:
            lines.append(f"bbox={frame.get('bbox')}")
            lines.append(f"members={', '.join(str(member) for member in members)}")
        return "\n".join(lines)
    lines = [f"{head} translation={frame.get('translation')}"]
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


def _split_fused_target(entry_target: str) -> tuple[str, str]:
    """Split ``model.step.py#o1.2`` into (entry target, selector ref).

    The fused form is what the viewer's "Copy ``model#o1.6``" button hands
    users, so it must be accepted wherever an entry target is; the tail keeps
    its ``#`` so it parses like any other selector line."""
    head, sep, tail = entry_target.partition("#")
    if sep and head.strip() and tail.strip():
        return head.strip(), f"#{tail.strip()}"
    return entry_target, ""


def _read_refs_input(args: argparse.Namespace) -> tuple[str, str]:
    inspect = _inspect_api()
    raw_inputs = [str(value) for value in getattr(args, "inputs", ()) if str(value).strip()]
    if args.input_file:
        if len(raw_inputs) != 1:
            raise inspect.CadRefError("Pass exactly one STEP/CAD entry target with --input-file.")
        # Native path semantics, like every other cadgen path argument: relative
        # against the process cwd, absolute anywhere, '~' expanded. argparse hands
        # back a bare Path, which leaves a literal "~" directory to fail on.
        input_file = args.input_file.expanduser()
        try:
            text = input_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise inspect.CadRefError(f"Failed to read input file: {input_file}") from exc
        entry_target, fused_ref = _split_fused_target(raw_inputs[0])
        if fused_ref:
            text = fused_ref + "\n" + text
    else:
        if not raw_inputs:
            raise inspect.CadRefError("No STEP/CAD entry target provided.")
        entry_target, fused_ref = _split_fused_target(raw_inputs[0])
        text = "\n".join(([fused_ref] if fused_ref else []) + raw_inputs[1:])

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


def main(argv: list[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    command_label = str(getattr(args, "command", "inspect") or "inspect")
    logger = CliLogger("cadgen step inspect", verbose=bool(getattr(args, "verbose", False)))
    try:
        with logger.timed(command_label):
            return int(args.handler(args))
    except _inspect_api().CadRefError as exc:
        _emit_result(args, {"ok": False, "errors": [_inspect_api().cad_ref_error_payload(exc)]}, _format_errors)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
