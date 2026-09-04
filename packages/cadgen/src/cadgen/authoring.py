"""The library-first authoring surface: ``@step`` and ``@dxf``
(design/library-first-generation.md).

A CAD model is a plain Python script; the decorator declares the model and
``__main__`` builds it by calling it::

    from cadgen import build123d as bd
    from cadgen import step

    @step()                      # out= defaults to <stem>.step beside the
    def bracket():               # script; pass out="..." to relocate
        return bd.Box(40, 10, 10)

    if __name__ == "__main__":
        bracket()

Semantics:

- **Decoration only declares.** Applying ``@step``/``@dxf`` registers the
  model and returns a callable of the same name. Nothing runs at decoration
  time and nothing runs on import; a model file can be imported, inspected and
  composed freely.
- **A top-level call builds.** Calling the decorated name when no build is in
  progress (``__main__``, a REPL, a test) runs the full pipeline — freshness
  gate, progress, incremental package build, ``.step``/``.dxf`` output —
  via the warm daemon when available, in-process otherwise. It returns
  ``None``: the caller is the build's initiator, and loading the shape back
  into it would force the kernel import the gate exists to avoid. A failed
  build raises ``SystemExit`` with the pipeline's exit code, so ``python
  model.py`` exits the way a build should.
- **A call inside a build composes.** While a build is running (any model's,
  any thread of this process), calling a decorated name runs its body and
  returns the shape (or drawing) — this is how an assembly uses its children.
  A model called from inside another model's build is a CHILD: it is built (or
  loaded from the store when current) and its tree is linked into the parent.
- **One model per file.** Entry identity (refs, packages, closures) is keyed
  by the source file everywhere in the pipeline, so a file defines exactly one
  ``@step`` or ``@dxf`` model.

Per-run flags ride ``sys.argv`` of the top-level call: ``--force``,
``--verbose``, ``--json``, ``--mesh-tolerance``,
``--mesh-angular-tolerance``. Durable configuration lives
in the decorator call. A model function takes no parameters: it is one
configuration of one output. Parametric geometry lives in a plain factory the
model calls; another configuration is another model.

This module must import light (no OCP): the whole point is that a model
script's body costs ~0.2s before the gate and the warm handoff run.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from cadgen.kinematics import KinematicsDef, normalize_kinematics
from cadgen.metadata import MeshExportDecl, normalize_mesh_numeric, resolve_model_output_path
from cadgen.store.index import model_ref

__all__ = [
    "step",
    "dxf",
    "stl",
    "glb",
    "threemf",
    "ModelDef",
    "registered_model",
    "registered_models",
    "building",
    "build_in_progress",
]


# Whether a build is running on this thread. The pipeline enters ``building()``
# around the model body it executes, so a decorated name called from inside
# that body composes (returns geometry) while the same name called from
# ``__main__`` or a REPL builds. Thread-local because the daemon worker and the
# CLI can both host builds on threads that must not see each other's state.
_BUILD_STATE = threading.local()


class BuildFrame:
    """One model body in flight on this thread.

    ``children`` is recorded from the CALLS the body makes — every child wrapper
    entered — never from what the geometry became; ``pins`` is the resolution
    map: the first tree a child resolved to is the tree every later call in this
    build composes (snapshot isolation)."""

    def __init__(self, script_path: Path | None, function: str | None = None) -> None:
        self.script_path = script_path
        # The decorated function this frame is building; None when unknown (a
        # caller that entered ``building()`` for a whole file).
        self.function = function
        # The model's identity, ``script::fn`` (cadgen.store.index.model_ref).
        self.model: str | None = model_ref(script_path, function) if script_path is not None else None
        # (child model ref, the LazyCompound the call returned) — one entry per CALL.
        self.children: list[tuple[str, Any]] = []
        # The resolution map: child model ref -> the tree this build composes.
        self.pins: dict[str, str] = {}
        # One job per stale child per build, however many times it is called.
        self.jobs: dict[str, Any] = {}
        # The root request this build belongs to (for the build tree's events).
        self.root_id: str | None = os.environ.get("CADGEN_ROOT_ID") or None

    def pin(self, child: str, tree: str) -> str:
        return self.pins.setdefault(str(child), tree)

    def child_trees(self) -> list[tuple[str, str]]:
        """Every child call with the tree it resolved to; waits for pending jobs."""
        return [(child, lazy.tree_hash()) for child, lazy in self.children]


def _same_file(left: Path, right: Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except (OSError, RuntimeError):
        return Path(left) == Path(right)


def build_in_progress() -> bool:
    return bool(getattr(_BUILD_STATE, "frames", None))


def current_frame() -> BuildFrame | None:
    frames = getattr(_BUILD_STATE, "frames", None)
    return frames[-1] if frames else None


@contextlib.contextmanager
def building(script_path: Path | None = None, function: str | None = None) -> Iterator[BuildFrame]:
    """Mark this thread as executing a model body (the pipeline's call site).
    Yields the frame that collects the body's child pins."""
    frames = getattr(_BUILD_STATE, "frames", None)
    if frames is None:
        frames = _BUILD_STATE.frames = []
    frame = BuildFrame(script_path, function)
    frames.append(frame)
    try:
        yield frame
    finally:
        frames.pop()


@dataclass(frozen=True)
class ModelDef:
    """One registered model: the decorated function plus its durable options."""

    func: Callable[..., Any]
    fmt: str  # "step" | "dxf"
    script_path: Path
    out: str | None
    mesh_tolerance: float | None
    mesh_angular_tolerance: float | None
    # Typed mates (kinematics= dict, validated at decoration); axis refs
    # resolve at build and the block lands in the model's sidecar. STEP only.
    kinematics: KinematicsDef | None = None
    # Declared mesh serializations (@stl/@glb/@threemf). STEP models only.
    mesh_exports: tuple[MeshExportDecl, ...] = ()
    # False for a MESH-ONLY model (@stl/@glb/@threemf with no @step): the same
    # tree and record as any model, but the .step is not among its outputs and
    # is never written. STEP is one output kind, not the primary.
    step_output: bool = True
    # (mtime_ns, size) of the script when this definition was registered: the
    # metadata reader reuses the entry while the file on disk is those bytes.
    stamp: tuple[int, int] | None = None

    @property
    def name(self) -> str:
        """The decorated function's name: the model's own name."""
        return self.func.__name__

    @property
    def ref(self) -> str:
        """The model's identity, ``/abs/script.py::name`` (cadgen.store.index)."""
        return model_ref(self.script_path, self.name)

    @property
    def output_path(self) -> Path:
        return resolve_model_output_path(
            self.script_path, fmt=self.fmt, explicit_out=self.out, function=self.name
        )


# Keyed by model ref (``script::function``). A file may hold several models --
# each its own record, output and job; they share the file's closure.
_REGISTRY: dict[str, ModelDef] = {}


def registered_model(script_path: Path, function: str | None = None) -> ModelDef | None:
    """The model ``function`` declares in ``script_path``, or the file's sole
    registered model when ``function`` is None (None when it holds several)."""
    if function is not None:
        return _REGISTRY.get(model_ref(script_path, function))
    found = registered_models_in(script_path)
    return found[0] if len(found) == 1 else None


def registered_models_in(script_path: Path) -> list[ModelDef]:
    """Every model registered from ``script_path``, in registration order."""
    resolved = Path(script_path).resolve()
    return [defn for defn in _REGISTRY.values() if defn.script_path == resolved]


def registered_models() -> dict[str, ModelDef]:
    return dict(_REGISTRY)


def _script_path_of(func: Callable[..., Any]) -> Path:
    source = inspect.getsourcefile(func) or func.__code__.co_filename
    return Path(source).resolve()


def _validate_signature(func: Callable[..., Any], *, fmt: str) -> None:
    """A model takes no parameters.

    A model is one configuration with one declared output; there is nothing
    for an argument to select. Geometry that varies belongs in a plain factory
    function the model calls — ``def _bracket(width): ...`` and
    ``@step def bracket(): return _bracket(40.0)`` — and a second configuration
    is a second model with its own output. Enforced here and by the static
    parser (cadgen.metadata) so a build never has to guess what to pass.
    """
    parameters = list(inspect.signature(func).parameters.values())
    if parameters:
        listed = ", ".join(p.name for p in parameters)
        raise TypeError(
            f"@{fmt} model {func.__name__}() takes no parameters (got: {listed}). A "
            "model is one configuration of one output: move the parameters to a "
            f"plain factory function and have {func.__name__}() call it with the "
            "values this model uses; a different configuration is a different model."
        )


def _register(defn: ModelDef) -> None:
    _REGISTRY[defn.ref] = defn


def _declaring(func: Callable[..., Any]) -> "_Declaring":
    """A context that reports a decoration-time failure the way the runner
    reports a build failure -- one ``[python <file>.py] FAILED: …`` line on
    stderr, the full traceback under ``--verbose``, exit 1 -- when the decorated
    function's module is the script being run. Imported by a parent's build, the
    exception propagates and the parent's runner reports it as the parent's
    failure carrying the child's message."""
    return _Declaring(getattr(func, "__module__", None), _script_path_of(func))


def _declaring_here() -> "_Declaring":
    """The same reporter for a decorator FACTORY (``@step(out=…)``), where no
    function is known yet: the module is the first caller outside cadgen."""
    frame = sys._getframe(1)
    while frame is not None and str(frame.f_globals.get("__name__", "")).split(".")[0] == "cadgen":
        frame = frame.f_back
    if frame is None:
        return _Declaring(None, None)
    module = frame.f_globals.get("__name__")
    file = frame.f_globals.get("__file__")
    return _Declaring(module, Path(file).resolve() if file else None)


class _Declaring:
    def __init__(self, module: str | None, script: Path | None) -> None:
        self.module = module
        self.script = script

    def __enter__(self) -> "_Declaring":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None or isinstance(exc, (SystemExit, KeyboardInterrupt)):
            return False
        if self.module != "__main__" or self.script is None:
            # Raised while another module imported this one. It propagates as an
            # ordinary exception -- a parent's runner reports it as the parent's
            # failure -- and, should it reach the top of a script run uncaught, the
            # hook below prints it as that script's one-line failure.
            exc.__cadgen_declaration__ = True  # type: ignore[attr-defined]
            return False
        from cadgen._internal.cli_errors import report_cli_error

        report_cli_error(exc, tool=f"python {self.script.name}", verbose="--verbose" in sys.argv[1:])
        raise SystemExit(1)


def _report_uncaught_declaration(exc_type, exc, tb) -> None:
    """``sys.excepthook``: a declaration failure that escaped to the top of a
    script run (the script imported a model file whose decorator refused its
    arguments) is reported like the runner reports a build failure, instead of
    a traceback. Anything else goes to the previous hook."""
    main = sys.modules.get("__main__")
    file = getattr(main, "__file__", None) if main is not None else None
    if getattr(exc, "__cadgen_declaration__", False) and file and "--verbose" not in sys.argv[1:]:
        from cadgen._internal.cli_errors import report_cli_error

        report_cli_error(exc, tool=f"python {Path(file).name}", verbose=False)
        return
    _PREVIOUS_EXCEPTHOOK(exc_type, exc, tb)


_PREVIOUS_EXCEPTHOOK = sys.excepthook
if sys.excepthook is not _report_uncaught_declaration:
    sys.excepthook = _report_uncaught_declaration


def _script_stamp(script_path: Path) -> tuple[int, int] | None:
    try:
        stat = Path(script_path).stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _checked_out(out: Any, *, where: str) -> str | None:
    """``out=`` is any Python expression that evaluates to a non-empty path string."""
    if out is None:
        return None
    if isinstance(out, os.PathLike):
        out = os.fspath(out)
    if not isinstance(out, str) or not out.strip():
        raise TypeError(f"{where} out= must be a non-empty path string (got {out!r})")
    if "\\" in out:
        # A declaration travels with the script to every platform: POSIX separators.
        raise ValueError(f"{where} out= must use POSIX '/' separators (got {out!r})")
    return out.strip()


def _checked_tolerance(value: Any, field_name: str, *, where: str) -> float | None:
    if value is None:
        return None
    try:
        return normalize_mesh_numeric(value, field_name=field_name)
    except ValueError as exc:
        raise TypeError(f"{where} {exc}") from exc


def _reject_unknown_kwargs(deco_name: str, kwargs: dict[str, Any]) -> None:
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"@{deco_name} got an unexpected keyword argument: {unexpected}")


def _decorator(
    fmt: str,
    *,
    out: str | None,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    kinematics: object = None,
    step_output: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    with _declaring_here():
        kinematics_def = (
            normalize_kinematics(kinematics, where=f"@{fmt}") if kinematics is not None else None
        )
        out = _checked_out(out, where=f"@{fmt}")
        mesh_tolerance = _checked_tolerance(mesh_tolerance, "mesh_tolerance", where=f"@{fmt}")
        mesh_angular_tolerance = _checked_tolerance(
            mesh_angular_tolerance, "mesh_angular_tolerance", where=f"@{fmt}"
        )

    def apply(func: Callable[..., Any]) -> Callable[..., Any]:
        with _declaring(func):
            return _apply(func)

    def _apply(func: Callable[..., Any]) -> Callable[..., Any]:
        pending: tuple[MeshExportDecl, ...] = ()
        prior: ModelDef | None = getattr(func, "__cadgen_model__", None)
        if prior is not None:
            prior = _REGISTRY.get(prior.ref, prior)  # the registry is authoritative
        if prior is not None and not prior.step_output:
            # A mesh decorator BELOW this one already declared the function a
            # mesh-only model (and handed back its wrapper). @step takes the RAW
            # function and its declarations over (stacking order stays neutral);
            # a drawing cannot.
            if fmt != "step":
                names = ", ".join(f"@{_MESH_FMT_DECORATOR[d.fmt]}" for d in prior.mesh_exports)
                raise ValueError(
                    f"{prior.script_path.name} stacks {names} on a @{fmt} drawing; "
                    "STL/3MF/GLB derive from a @step model's geometry"
                )
            pending = prior.mesh_exports
            func = prior.func
        _validate_signature(func, fmt=fmt)
        script_path = _script_path_of(func)
        defn = ModelDef(
            func=func,
            fmt=fmt,
            script_path=script_path,
            out=out,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
            kinematics=kinematics_def,
            mesh_exports=pending,
            step_output=step_output,
            stamp=_script_stamp(script_path),
        )
        _register(defn)
        func.__cadgen_model__ = defn  # type: ignore[attr-defined]

        @functools.wraps(func)
        def model(*args: Any, **kwargs: Any) -> Any:
            frame = current_frame()
            if frame is not None:
                if args or kwargs:
                    raise TypeError(f"{func.__name__}() takes no arguments: a model is one configuration of one output.")
                if (
                    frame.script_path is not None
                    and _same_file(frame.script_path, script_path)
                    and (frame.function is None or frame.function == func.__name__)
                ):
                    # The pipeline building THIS model is asking for its body. (Another
                    # model of the same file is a child like any other.)
                    return func()
                if fmt == "dxf":
                    # A drawing composes models, never the reverse: called inside
                    # another build it is just its body (2D geometry), nothing to pin.
                    return func()
                # Composition: a parent's body asked for this child. Same rule as the
                # top level — stale → build, then hand back its geometry — except the
                # geometry is materialized from the child's tree and the call is
                # pinned into the parent's record.
                return _compose_child(_REGISTRY.get(defn.ref, defn))
            if args or kwargs:
                raise TypeError(
                    f"{func.__name__}() takes no arguments: a model is one configuration "
                    "of one output. Calling it builds that output."
                )
            # A top-level call builds. The registry entry may have been extended by a
            # mesh decorator stacked ABOVE @step since `defn` was captured, so read it
            # back rather than closing over the original.
            current = _REGISTRY.get(defn.ref, defn)
            code = _build(current)
            if code != 0:
                raise SystemExit(code)
            # ...and hands back the geometry it built (or found current), so a plain
            # script, a notebook or a REPL gets the shape a parent would: the model's
            # tree materialized. A drawing has no tree and returns None.
            return _built_geometry(current)

        model.__cadgen_model__ = defn  # type: ignore[attr-defined]
        return model

    return apply


def step(
    func: Callable[..., Any] | None = None,
    *,
    out: str | None = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    kinematics: object = None,
    **unsupported: Any,
):
    """Declare a STEP model. Usable bare (``@step``) or configured (``@step(...)``).

    ``kinematics=`` takes the typed-mates dict (see ``cadgen.kinematics``). No
    decorator argument changes the geometry a model writes: the geometry is the
    function's return value; the arguments decide where the files land, how
    they are written, and what the sidecar declares. No decorator names
    JavaScript: choreography is the render module beside the document
    (``<name>.step.js``), which the viewer loads by name and no build reads.
    """
    with _declaring_here():
        _reject_unknown_kwargs("step", unsupported)
    decorator = _decorator(
        "step",
        out=out,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        kinematics=kinematics,
    )
    return decorator(func) if func is not None else decorator


def dxf(
    func: Callable[..., Any] | None = None,
    *,
    out: str | None = None,
    **unsupported: Any,
):
    """Declare a DXF drawing. Usable bare (``@dxf``) or configured (``@dxf(...)``)."""
    if "kinematics" in unsupported:
        raise TypeError(
            "@dxf takes no kinematics=: a drawing is 2D geometry — kinematics "
            "lives on @step and the mesh decorators"
        )
    with _declaring_here():
        _reject_unknown_kwargs("dxf", unsupported)
    decorator = _decorator(
        "dxf", out=out, mesh_tolerance=None, mesh_angular_tolerance=None
    )
    return decorator(func) if func is not None else decorator


_MESH_FMT_DECORATOR = {"stl": "stl", "glb": "glb", "3mf": "threemf"}


def _validate_variant(existing, decl: MeshExportDecl, deco_name: str) -> None:
    """Variants of one format are allowed; ambiguous duplicates are not: two
    bare declarations collide at the sibling default, two identical out=
    targets collide outright."""
    if decl.out is None:
        if any(d.fmt == decl.fmt and d.out is None for d in existing):
            raise ValueError(
                f"bare @{deco_name} is declared more than once; at most one "
                "declaration per format may omit out= (the sibling default)"
            )
    elif any(d.fmt == decl.fmt and d.out == decl.out for d in existing):
        raise ValueError(f"@{deco_name} is declared twice for the same target {decl.out!r}")


def _mesh_export_decorator(deco_name: str, fmt: str):
    """Factory for ``@stl``/``@glb``/``@threemf``. Above ``@step`` they extend
    the registered model; alone (or below ``@step``) they declare a mesh-only
    model that a later ``@step`` takes over. Both routes converge in the loader
    import, so stacking order is behavior-neutral, and a model with no ``@step``
    at all is still a model — one that writes no STEP."""
    from dataclasses import replace as _replace

    suffix = f".{fmt}"

    def decorator_factory(
        func: Callable[..., Any] | None = None,
        *,
        out: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
        kinematics: object = None,
        **unsupported: Any,
    ):
        with _declaring_here():
            _reject_unknown_kwargs(deco_name, unsupported)
            out = _checked_out(out, where=f"@{deco_name}")
            mesh_tolerance = _checked_tolerance(mesh_tolerance, "mesh_tolerance", where=f"@{deco_name}")
            mesh_angular_tolerance = _checked_tolerance(
                mesh_angular_tolerance, "mesh_angular_tolerance", where=f"@{deco_name}"
            )
            if out is not None and not out.lower().endswith(suffix):
                raise ValueError(f"@{deco_name} out= must end with '{suffix}': {out!r}")
            kinematics_def = (
                normalize_kinematics(kinematics, where=f"@{deco_name}")
                if kinematics is not None
                else None
            )
        decl = MeshExportDecl(
            fmt=fmt,
            out=out,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
            kinematics=kinematics_def,
        )

        def attach(target: Callable[..., Any]) -> Callable[..., Any]:
            with _declaring(target):
                return _attach(target)

        def _attach(target: Callable[..., Any]) -> Callable[..., Any]:
            existing_model: ModelDef | None = getattr(target, "__cadgen_model__", None)
            if existing_model is not None:
                # Above @step: extend the registered model in place.
                if existing_model.fmt != "step":
                    raise ValueError(
                        f"@{deco_name} declares a mesh export of a @step model; "
                        f"{existing_model.script_path.name} is a @{existing_model.fmt} drawing"
                    )
                _validate_variant(existing_model.mesh_exports, decl, deco_name)
                # Decorators apply bottom-up; keeping source (top-down) order means
                # the declaration nearest the top of the file is listed first.
                updated = _replace(
                    existing_model, mesh_exports=(decl, *existing_model.mesh_exports)
                )
                _REGISTRY[updated.ref] = updated
                target.__cadgen_model__ = updated  # type: ignore[attr-defined]
                return target
            # No @step (yet): a mesh decorator alone declares a MODEL — the same
            # tree, record and job as any model — whose outputs are its mesh
            # declarations; its .step is never written. A @step stacked above takes
            # the declarations over, so stacking order stays neutral.
            wrapper = _decorator(
                "step", out=None, mesh_tolerance=None,
                mesh_angular_tolerance=None, step_output=False,
            )(target)
            registered = _REGISTRY[model_ref(_script_path_of(target), target.__name__)]
            updated = _replace(registered, mesh_exports=(decl,))
            _REGISTRY[updated.ref] = updated
            wrapper.__cadgen_model__ = updated  # type: ignore[attr-defined]
            target.__cadgen_model__ = updated  # type: ignore[attr-defined]
            return wrapper

        return attach(func) if func is not None else attach

    decorator_factory.__name__ = deco_name
    return decorator_factory


stl = _mesh_export_decorator("stl", "stl")
glb = _mesh_export_decorator("glb", "glb")
threemf = _mesh_export_decorator("threemf", "3mf")


def _maybe_hint_eager_imports(defn: ModelDef) -> None:
    if os.environ.get("CADGEN_DAEMON_CHILD"):
        return
    if "OCP" not in sys.modules and "build123d" not in sys.modules:
        return
    from cadgen._internal.kernel_import_site import first_import_site

    site = first_import_site()
    where = ""
    if site is not None:
        path, line, source = site
        where = f" at {os.path.relpath(path) if os.path.isabs(path) else path}:{line}"
        if source:
            where += f" ({source.strip()})"
    print(
        f"hint: the CAD kernel was imported before {defn.script_path.name}'s build was "
        f"asked for{where}. Module bodies must not touch it: use `from cadgen import "
        "build123d as bd` instead of importing build123d/OCP, keep `bd.<anything>` "
        "out of module-level constants and default arguments (each one resolves the "
        "attribute at import), and call `read_step` inside the model body or a "
        "function it calls, never at module level (reading a vendor STEP at import "
        "pays the kernel AND the parse on every current rerun). Then a call on a "
        "current model returns without the ~2.5s import (see the cad skill docs).",
        file=sys.stderr,
    )


def _compose_child(defn: ModelDef) -> Any:
    """A parent's body called a child: submit it if stale, hand back a promise.

    ``stale → submit → lazy`` — the same gate as the top level, but the call
    returns at once with a :class:`cadgen.store.lazy.LazyCompound`: a stale
    child's build is running on the pool (its own worker, or a transient
    subprocess) while this body keeps calling its other children; a current
    child is a promise with no job. Geometry arrives when the parent first reads
    it — normally at the closing ``Compound(children=[...])`` — so siblings
    build in parallel. The first tree a child resolves to in this build is
    pinned (snapshot isolation); the same stale child called twice shares one
    job; children are recorded from the CALLS, never from the geometry.
    """
    from cadgen.store.gate import stale
    from cadgen.store.lazy import LazyCompound

    frame = current_frame()
    child = defn.ref
    if frame is not None and any(f.model == child for f in _frames() if f.model is not None):
        raise RuntimeError(
            f"{defn.script_path.name}::{defn.name} is called while it is itself being built: "
            "a model may not depend on itself"
        )
    from cadgen.daemon.executors import emit_event, model_event, submit

    parent = frame.model if frame is not None else None
    job = None
    tree: str | None = frame.pins.get(child) if frame is not None else None
    if frame is not None and child in frame.jobs:
        job = frame.jobs[child]
    elif tree is None:
        verdict = stale(child)
        if verdict.stale:
            job = submit(
                child, force=False, root_id=getattr(frame, "root_id", None), parent=parent,
                closure=verdict.closure,
            )
            if frame is not None:
                frame.jobs[child] = job
        else:
            # Current: pin its tree NOW, at the call. A rebuild of this child between
            # here and the force must not change what this build composes.
            from cadgen.store.records import read_record

            tree = str((read_record(child) or {}).get("tree") or "") or None
            # No work: the tree summarizes current children on the parent's line.
            emit_event(model_event(child, "current", parent=parent))
    lazy = LazyCompound(child, job, frame=frame, label=defn.name, tree=tree)
    if frame is not None:
        frame.children.append((child, lazy))
    return lazy


def _frames() -> list[BuildFrame]:
    return list(getattr(_BUILD_STATE, "frames", None) or [])


def _build(defn: ModelDef) -> int:
    """Run the pipeline for a top-level call of a model and return its exit code."""
    argv = sys.argv[1:]
    _maybe_hint_eager_imports(defn)

    # This process is the ROOT of a build tree: it owns the terminal and renders the
    # graph as child events come back through the pool (cadgen.cli_tree). Warm or
    # cold, the tree is drawn here; the daemon relays its workers' events to us.
    from cadgen.cli_tree import build_tree

    with build_tree(json_lines="--json" in argv):
        # Warm handoff BEFORE any heavy import. The daemon worker imports the module
        # under a loader name (never __main__), so its `__main__` block does not run
        # there; the runner executes the model body inside `building()`.
        # A file holding several models names the one this call builds.
        target = [str(defn.script_path)]
        if len(registered_models_in(defn.script_path)) > 1:
            target += ["--model", defn.name]
        if os.environ.get("CADGEN_DAEMON") != "0" and not os.environ.get("CADGEN_DAEMON_CHILD"):
            try:
                from cadgen.daemon.client import run_via_daemon
            except ModuleNotFoundError:
                warm_exit: int | None = None
            else:
                warm_exit = run_via_daemon(
                    "run",
                    [*target, *argv],
                    os.getcwd(),
                    prog=f"python {defn.script_path.name}",
                )
            if warm_exit is not None:
                return warm_exit

        # A cold @dxf run used to re-exec itself here with PYTHONHASHSEED=0, because
        # ezdxf's emitted order depended on string hashing. The engine's emitter makes
        # DXF bytes a function of the drawing's geometry instead
        # (cadgen._internal.dxf_emit), so a cold run needs no interpreter restart and
        # @dxf reaches the pipeline by exactly the route @step does.
        from cadgen.cli._run_model import run_model_argv

        return run_model_argv([*target, *argv], prog=f"python {defn.script_path.name}")


def _built_geometry(defn: ModelDef) -> Any:
    """What a top-level call hands back after its build: the model's tree,
    materialized -- the geometry a parent composing this model would receive.
    None for a drawing (no tree) or when no record was left."""
    if defn.fmt != "step":
        return None
    from cadgen.store.lazy import materialize_model
    from cadgen.store.records import read_record

    tree = str((read_record(defn.ref) or {}).get("tree") or "")
    if not tree:
        return None
    return materialize_model(tree, label=defn.name)
