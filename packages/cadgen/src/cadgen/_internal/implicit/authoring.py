"""``@implicit.part``: a model whose result is a field.

The same shape as the STEP decorators an author already knows: the
decorator only declares; a top-level call builds; a call from inside another
part's body composes (returns the field). The default output is a STEP, the
field's B-rep with its blends as fillets, so the part opens in the viewer as
any STEP does; a tree the kernel cannot build falls back to a mesh and says
so. Beside the first output goes the tape, the field as data, which
``cadgen implicit build|measure|faces`` operate on afterwards. Nothing goes
through the store: the tape is the source and every output derives from it.
"""

from __future__ import annotations

import inspect
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from cadgen._internal.implicit.field import Field
from cadgen.results import ImplicitBuildResult, ImplicitOutput

__all__ = ["part", "build_part", "MESH_SUFFIXES"]

MESH_SUFFIXES = (".glb", ".stl")
STEP_SUFFIXES = (".step", ".stp")
OUTPUT_SUFFIXES = MESH_SUFFIXES + STEP_SUFFIXES

_state = threading.local()


def _depth() -> int:
    return getattr(_state, "depth", 0)


class PartDecl:
    """What one ``@implicit.part`` declared: the function, its outputs and its resolution."""

    def __init__(
        self,
        func: Callable[[], Field],
        *,
        out: str | Sequence[str] | None,
        resolution: float | None,
        crease_deg: float,
        script: Path,
    ) -> None:
        self.func = func
        self.script = script
        self.resolution = None if resolution is None else float(resolution)
        self.crease_deg = float(crease_deg)
        outs = [out] if isinstance(out, (str, Path)) else list(out or [])
        if not outs:
            outs = [script.stem + ".step"]
        self.outputs: list[Path] = []
        for candidate in outs:
            path = Path(candidate)
            if path.suffix.lower() not in OUTPUT_SUFFIXES:
                raise ValueError(
                    f"@implicit.part out={str(candidate)!r}: an implicit part writes {' or '.join(MESH_SUFFIXES)} meshes, "
                    f"or {' or '.join(STEP_SUFFIXES)} for its B-rep"
                )
            if not path.is_absolute():
                path = script.parent / path
            self.outputs.append(path)

    @property
    def name(self) -> str:
        return self.func.__name__

    def field(self) -> Field:
        _state.depth = _depth() + 1
        try:
            result = self.func()
        finally:
            _state.depth = _depth() - 1
        if not isinstance(result, Field):
            raise TypeError(f"@implicit.part {self.name} must return an implicit Field, got {type(result).__name__}")
        return result


def _script_of(func: Callable[..., Any]) -> Path:
    try:
        return Path(inspect.getfile(func)).resolve()
    except (TypeError, OSError):
        return Path.cwd() / f"{func.__name__}.py"


def build_part(
    decl: PartDecl,
    *,
    resolution: float | None = None,
    verbose: bool = False,
) -> ImplicitBuildResult:
    """Evaluate the part's field, contour it once and write every declared output plus the tape."""
    from cadgen._internal.implicit.mesh import contour
    from cadgen._internal.implicit.tape import is_tapeable, tape_path_for, write_tape
    from cadgen._internal.implicit.writers import write_glb, write_stl

    t0 = time.perf_counter()
    field = decl.field()
    cell = resolution if resolution is not None else decl.resolution
    outputs: list[ImplicitOutput] = []
    warnings: list[str] = []
    step_outputs = [out for out in decl.outputs if out.suffix.lower() in STEP_SUFFIXES]
    mesh_outputs = [out for out in decl.outputs if out.suffix.lower() in MESH_SUFFIXES]
    # The STEP first: the B-rep with the field's blends as OCC fillets. A tree the
    # kernel cannot build (a custom field, a shell OCC refuses) falls back to a mesh
    # of the same name, and the result says why.
    for out in step_outputs:
        from cadgen._internal.implicit.brep import BrepReport, Unrepresentable, to_brep

        report = BrepReport()
        try:
            shape = to_brep(field, blends="fillet", report=report)
        except Unrepresentable as error:
            fallback = out.with_suffix(".glb")
            warnings.append(f"no STEP for {out.name}: {error}; wrote {fallback.name} instead")
            if fallback not in mesh_outputs:
                mesh_outputs.append(fallback)
            continue
        from cadgen import build123d as bd

        shape.label = decl.name
        out.parent.mkdir(parents=True, exist_ok=True)
        bd.export_step(shape, str(out))
        outputs.append(ImplicitOutput(path=out, fmt="step"))
        print(f"[cadgen] wrote STEP: {out}", file=sys.stderr)
        warnings.extend(f"STEP: {warning}" for warning in report.warnings)
    mesh = None
    if mesh_outputs:
        mesh = contour(field, resolution=cell, crease_deg=decl.crease_deg)
        for out in mesh_outputs:
            fmt = out.suffix.lower()[1:]
            if fmt == "glb":
                write_glb(mesh, out, name=decl.name)
            else:
                write_stl(mesh, out, name=decl.name)
            outputs.append(ImplicitOutput(path=out, fmt=fmt))
            print(f"[cadgen] wrote {fmt.upper()}: {out}", file=sys.stderr)
    tape: Path | None = None
    if is_tapeable(field):
        tape = write_tape(field, tape_path_for(decl.outputs[0]), name=decl.name, resolution=cell if cell else (mesh.resolution if mesh else None))
        if verbose:
            print(f"[cadgen] wrote tape: {tape}", file=sys.stderr)
    else:
        warnings.append("the part uses a custom field or a B-rep with no file, so no tape was written: it can be rebuilt only by running its script")
    empty = mesh is not None and mesh.triangle_count == 0
    if empty:
        warnings.append("the field has no surface inside its bounds: nothing was contoured (is every solid unioned in, and does a custom field declare its bounds?)")
    from cadgen._internal.implicit.field import leaves as _leaves

    all_leaves = mesh.leaves if mesh is not None else _leaves(field)
    box = field.bounds
    return ImplicitBuildResult(
        ok=bool(outputs) and not empty,
        name=decl.name,
        outputs=tuple(outputs),
        tape=tape,
        resolution=mesh.resolution if mesh is not None else (cell or 0.0),
        grid=mesh.grid if mesh is not None else (0, 0, 0),
        triangles=mesh.triangle_count if mesh is not None else 0,
        vertices=mesh.vertex_count if mesh is not None else 0,
        leaves=tuple(
            {"id": index, "kind": leaf.kind, "label": leaf.label or "", "site": leaf.site or ""} for index, leaf in enumerate(all_leaves)
        ),
        bounds={"min": list(box.min), "max": list(box.max)},
        timings={**(mesh.timings if mesh is not None else {}), "total_s": time.perf_counter() - t0},
        warnings=tuple(warnings),
    )


def _run_flags(argv: Sequence[str]) -> tuple[float | None, bool, bool]:
    """The per-run flags a part's script accepts on its own argv: --resolution, --json, --verbose."""
    import argparse

    parser = argparse.ArgumentParser(add_help=True, description="build this implicit part")
    parser.add_argument("--resolution", type=float, default=None, help="grid cell size, overriding the decorator's")
    parser.add_argument("--json", action="store_true", help="print the build result as one JSON line")
    parser.add_argument("--verbose", action="store_true", help="narrate on stderr")
    args = parser.parse_args(list(argv))
    return args.resolution, args.json, args.verbose


def part(
    func: Callable[[], Field] | None = None,
    *,
    out: str | Sequence[str] | None = None,
    resolution: float | None = None,
    crease_deg: float = 35.0,
):
    """Declare an implicit part.

    out: the file(s) to write, relative to the script: ``.step`` for the part's
        B-rep (the field's blends become fillets; a tree the kernel cannot build
        falls back to a ``.glb`` of the same name), ``.glb`` or ``.stl`` for a
        mesh. Omitted, ``<script stem>.step`` beside the script. The tape is
        written beside the first output as ``<stem>.implicit.json``.
    resolution: grid cell size in the model's units. Omitted, a 1/120th of the
        part's bounding diagonal.
    crease_deg: normals disagreeing with a face by more than this angle shade
        as a sharp edge.
    """

    def decorate(target: Callable[[], Field]):
        decl = PartDecl(target, out=out, resolution=resolution, crease_deg=crease_deg, script=_script_of(target))

        def wrapper() -> Any:
            if _depth() > 0:
                return decl.field()
            argv = sys.argv[1:] if _main_is(decl.script) else []
            run_resolution, as_json, verbose = _run_flags(argv) if argv else (None, False, False)
            try:
                result = build_part(decl, resolution=run_resolution, verbose=verbose)
            except Exception as error:  # a failed build exits like a failed STEP build
                if as_json:
                    import json

                    print(json.dumps({"ok": False, "error": str(error)}))
                else:
                    print(f"[cadgen] {decl.name}: {error}", file=sys.stderr)
                raise SystemExit(1) from error
            if as_json:
                import dataclasses
                import json

                print(json.dumps(dataclasses.asdict(result), default=str))
            else:
                for line in result.human_lines():
                    print(line, file=sys.stderr)
            if not result.ok:
                raise SystemExit(1)
            return result

        wrapper.__name__ = target.__name__
        wrapper.__doc__ = target.__doc__
        wrapper.__wrapped__ = target  # type: ignore[attr-defined]
        wrapper.__implicit_part__ = decl  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return decorate(func)
    return decorate


def _main_is(script: Path) -> bool:
    main = sys.modules.get("__main__")
    file = getattr(main, "__file__", None)
    if not file:
        return False
    try:
        return Path(file).resolve() == script
    except OSError:
        return False
