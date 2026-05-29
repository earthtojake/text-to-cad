"""CLI for the analyze tool.

Keep build123d/OCP imports lazy: ``analyze --help`` and module import must not
pull in heavy CAD modules (mirrors the cadpy_inspect convention and its test).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if __package__ in {None, ""}:
    _scripts_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_scripts_dir))

from cadpy_common.package_path import ensure_cadpy_package_path

ensure_cadpy_package_path()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze",
        description="Structural analysis of STEP geometry: mass properties, "
        "interference, clearance, and cross-sections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  analyze props part.step\n"
            "  analyze interference a.step b.step\n"
            "  analyze clearance plate.step pocket.step\n"
            "  analyze section arm.step --axis z --slices 20\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    props = sub.add_parser(
        "props",
        help="Volume, surface area, center of mass, and inertia tensor.",
    )
    props.add_argument("target", help="STEP/STP path or @cad[...] entry.")
    _add_output_arguments(props)
    props.set_defaults(handler=run_props)

    inter = sub.add_parser(
        "interference",
        help="Boolean-intersection (overlap) volume between two solids.",
    )
    inter.add_argument("a", help="First STEP/STP path or @cad[...] entry.")
    inter.add_argument("b", help="Second STEP/STP path or @cad[...] entry.")
    _add_output_arguments(inter)
    inter.set_defaults(handler=run_interference)

    clear = sub.add_parser(
        "clearance",
        help="Min surface distance + status (apart/touching/containing/interpenetrating).",
    )
    clear.add_argument("a", help="First STEP/STP path or @cad[...] entry.")
    clear.add_argument("b", help="Second STEP/STP path or @cad[...] entry.")
    _add_output_arguments(clear)
    clear.set_defaults(handler=run_clearance)

    section = sub.add_parser(
        "section",
        help="Cross-section area sampled along an axis.",
    )
    section.add_argument("target", help="STEP/STP path or @cad[...] entry.")
    section.add_argument("--axis", choices=("x", "y", "z"), default="z")
    section.add_argument("--slices", type=int, default=10, help="Number of stations (>=2). Default: 10.")
    _add_output_arguments(section)
    section.set_defaults(handler=run_section)

    return parser


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--quiet", action="store_true")


def _emit(args: argparse.Namespace, result: dict) -> int:
    if getattr(args, "format", "json") == "text":
        print(_format_text(args.command, result))
    else:
        indent = None if getattr(args, "quiet", False) else 2
        print(json.dumps(result, indent=indent, sort_keys=False))
    return 0 if result.get("ok", True) else 2


def _run(args: argparse.Namespace, fn) -> int:
    # Import geometry lazily so --help stays free of build123d/OCP.
    from cadpy_analyze.geometry import AnalyzeError

    try:
        result = fn()
        result.setdefault("ok", True)
    except AnalyzeError as exc:
        result = {"ok": False, "errors": [{"message": str(exc)}]}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "errors": [{"type": type(exc).__name__, "message": str(exc)}]}
    return _emit(args, result)


def run_props(args: argparse.Namespace) -> int:
    def fn():
        from cadpy_analyze import geometry

        shape = geometry.load_solid(args.target)
        payload = geometry.mass_properties(shape)
        payload["target"] = str(args.target)
        return payload

    return _run(args, fn)


def run_interference(args: argparse.Namespace) -> int:
    def fn():
        from cadpy_analyze import geometry

        a = geometry.load_solid(args.a)
        b = geometry.load_solid(args.b)
        payload = geometry.interference(a, b)
        payload["a"] = str(args.a)
        payload["b"] = str(args.b)
        return payload

    return _run(args, fn)


def run_clearance(args: argparse.Namespace) -> int:
    def fn():
        from cadpy_analyze import geometry

        a = geometry.load_solid(args.a)
        b = geometry.load_solid(args.b)
        payload = geometry.clearance(a, b)
        payload["a"] = str(args.a)
        payload["b"] = str(args.b)
        return payload

    return _run(args, fn)


def run_section(args: argparse.Namespace) -> int:
    def fn():
        from cadpy_analyze import geometry

        shape = geometry.load_solid(args.target)
        payload = geometry.cross_sections(shape, axis=args.axis, num_slices=args.slices)
        payload["target"] = str(args.target)
        return payload

    return _run(args, fn)


def _format_text(command: str, result: dict) -> str:
    if not result.get("ok", True):
        errors = result.get("errors", [])
        return "\n".join(str(e.get("message")) for e in errors) or "error"
    if command == "props":
        com = result.get("centerOfMass")
        inertia = result.get("inertiaAboutCom", {})
        return (
            f"volume={result.get('volume')} area={result.get('area')} com={com}\n"
            f"inertia(COM) {inertia}"
        )
    if command == "interference":
        return f"interferes={result.get('interferes')} volume={result.get('volume')}"
    if command == "clearance":
        return (
            f"clearance={result.get('clearance')} status={result.get('status')} "
            f"containment={result.get('containment')} "
            f"intersectionVolume={result.get('intersectionVolume')}"
        )
    if command == "section":
        return f"axis={result.get('axis')} minArea={result.get('minArea')} maxArea={result.get('maxArea')}"
    return json.dumps(result)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
