"""CLI for the opt-in modal FEA tool.

build123d / netgen / ngsolve are imported lazily inside the handler so that
``fea --help`` and ``fea materials`` work without the solver stack installed.
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

from cadpy_fea import materials as materials_mod


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fea",
        description="Opt-in linear-elastic modal analysis of a STEP part "
        "(Netgen + ngsolve). First-pass design estimate, not certification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  fea modal spring.step --material pla --fixed outer --modes 6\n"
            "  fea modal bracket.step --material aluminum --fixed bottom\n"
            "  fea materials\n"
            "\nRequires: pip install ngsolve netgen-occt\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    modal = sub.add_parser("modal", help="Compute the lowest natural frequencies and mode shapes.")
    modal.add_argument("target", help="STEP/STP path.")
    modal.add_argument("--material", default="aluminum", help="Material name (see `fea materials`). Default: aluminum.")
    modal.add_argument(
        "--fixed",
        default="auto",
        choices=("auto", "bottom", "top", "outer", "largest"),
        help="Which face(s) to clamp. Default: auto.",
    )
    modal.add_argument("--modes", type=int, default=6, help="Number of modes to compute. Default: 6.")
    modal.add_argument("--maxh", type=float, default=0.0, help="Max mesh element size (model units). 0 = auto.")
    modal.add_argument("--order", type=int, default=2, help="FE polynomial order. Default: 2.")
    modal.add_argument("--units", choices=("mm", "m"), default="mm", help="STEP length units. Default: mm.")
    modal.add_argument(
        "--modal-glb",
        default="",
        help="Write an animated modal GLB (one morph target + baked animation "
        "clip per mode) to this path for browser playback in CAD Viewer.",
    )
    modal.add_argument(
        "--amplitude",
        type=float,
        default=0.12,
        help="Peak mode-shape deflection as a fraction of the model diagonal "
        "(morph weight=1). Default: 0.12.",
    )
    _add_output_arguments(modal)
    modal.set_defaults(handler=run_modal)

    mats = sub.add_parser("materials", help="List the built-in material table.")
    _add_output_arguments(mats)
    mats.set_defaults(handler=run_materials)

    return parser


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--quiet", action="store_true")


def run_materials(args: argparse.Namespace) -> int:
    items = sorted(
        materials_mod.MATERIALS.items(),
        key=lambda kv: (kv[1].category, kv[0]),
    )
    if getattr(args, "format", "json") == "text":
        current = None
        for name, m in items:
            if m.category != current:
                current = m.category
                print(f"# {current}")
            print(f"  {name:16s} E={m.E:.3g} Pa  nu={m.nu}  rho={m.rho} kg/m^3  zeta={m.zeta}")
        return 0
    table = {
        name: {"E": m.E, "nu": m.nu, "rho": m.rho, "category": m.category, "zeta": m.zeta}
        for name, m in items
    }
    print(json.dumps({"ok": True, "count": len(table), "materials": table}, indent=2))
    return 0


def run_modal(args: argparse.Namespace) -> int:
    try:
        material = materials_mod.get_material(args.material)
    except KeyError as exc:
        return _emit(args, {"ok": False, "errors": [{"message": str(exc)}]})

    try:
        from cadpy_fea import modal as modal_mod
    except Exception as exc:  # noqa: BLE001 - solver stack missing
        return _emit(args, {
            "ok": False,
            "errors": [{
                "message": "Modal FEA requires the ngsolve/netgen solver stack. "
                "Install it with: pip install ngsolve netgen-occt",
                "detail": str(exc),
            }],
        })

    try:
        result = modal_mod.run_modal(
            args.target,
            material,
            fixed=args.fixed,
            num_modes=args.modes,
            maxh=args.maxh,
            units_mm=(args.units == "mm"),
            order=args.order,
            emit_glb=(args.modal_glb or None),
            amplitude=args.amplitude,
        )
    except modal_mod.ModalError as exc:
        result = {"ok": False, "errors": [{"message": str(exc)}]}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "errors": [{"type": type(exc).__name__, "message": str(exc)}]}
    return _emit(args, result)


def _emit(args: argparse.Namespace, result: dict) -> int:
    if getattr(args, "format", "json") == "text":
        print(_format_text(result))
    else:
        indent = None if getattr(args, "quiet", False) else 2
        print(json.dumps(result, indent=indent, sort_keys=False))
    return 0 if result.get("ok", True) else 2


def _format_text(result: dict) -> str:
    if not result.get("ok", True):
        return "\n".join(str(e.get("message")) for e in result.get("errors", [])) or "error"
    lines = [
        f"target={result.get('target')} material={result.get('material', {}).get('name')} "
        f"mesh={result.get('mesh', {}).get('elements')} elems",
    ]
    for mode in result.get("modes", []):
        lines.append(
            f"  mode {mode['index']:>2}: {mode['frequencyHz']:>10.3f} Hz  {mode['description']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
