"""The library-first authoring surface: ``@step`` and ``@dxf``.

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
  via the warm daemon when available, in-process otherwise. A real-file
  ``__main__`` bare call whose result is immediately discarded returns
  ``None`` without loading the shape back into the initiator. Callers that use
  the result, and interactive or instrumented callers, receive the materialized
  shape. A failed build raises ``SystemExit`` with the pipeline's exit code, so
  ``python model.py`` exits the way a build should.
- **A call inside a build composes.** While a build is running (any model's,
  any thread of this process), calling a decorated name is how an assembly uses
  its children: the call is a CHILD, decoded from its stored result when the
  store holds one for its inputs as they are, else run -- serially, in this
  process, as its own build with its own record -- and the shape handed back is
  its stored result, decoded (STORE.md §9a). The files a call owes (its STEP,
  its meshes) are queued and finished when the run that owns the command ends,
  children first (``build_run``). A drawing's body runs inline. The root model
  is only the first call.
- **A model is ``script::function``.** A file may hold several models; each is
  its own record, output and job (``cadgen.store.index.model_ref``), and they
  share the file's closure. ``__main__`` builds the ones it calls -- there is no
  flag that selects a model. A file's sole model writes ``<file>.<fmt>``; models
  sharing a file each write ``<function>.<fmt>``.

Per-run flags ride ``sys.argv`` of the top-level call: ``--force``,
``--verbose``, ``--json``, ``--profile``. Durable configuration lives
in the decorator call. A model function takes no parameters: it is one
configuration of one output. Parametric geometry lives in a plain factory the
model calls; another configuration is another model.

This module must import light (no OCP): the whole point is that a model
script's body costs ~0.2s before the gate and the warm handoff run.
"""

from __future__ import annotations

import contextlib
import dis
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
    "building",
]


def _caller_discards_model_result() -> bool:
    """Whether this wrapper's real-file ``__main__`` caller immediately POP_TOPs.

    This is deliberately a one-way proof: every observer, unfamiliar runtime,
    synthetic module and bytecode uncertainty keeps the historical materialized
    return. The caller is two frames above this helper (helper -> model wrapper
    -> call site).
    """
    if sys.implementation.name != "cpython":
        return False
    if sys.gettrace() is not None or sys.getprofile() is not None:
        return False
    monitoring = getattr(sys, "monitoring", None)
    if monitoring is not None:
        try:
            if any(monitoring.get_tool(tool_id) is not None for tool_id in range(6)):
                return False
        except Exception:
            return False
    try:
        caller = sys._getframe(2)
        if caller.f_trace is not None:
            return False
        if caller.f_code.co_name != "<module>" or caller.f_globals.get("__name__") != "__main__":
            return False
        main_module = sys.modules.get("__main__")
        if main_module is None or caller.f_globals is not vars(main_module):
            return False
        filename = Path(caller.f_code.co_filename)
        declared_filename = Path(str(caller.f_globals.get("__file__", "")))
        if (
            filename.suffix.lower() != ".py"
            or not filename.is_file()
            or declared_filename.resolve() != filename.resolve()
        ):
            return False
        following = next(
            (instruction for instruction in dis.get_instructions(caller.f_code)
             if instruction.offset > caller.f_lasti),
            None,
        )
        return following is not None and following.opname == "POP_TOP"
    except Exception:
        return False


# Whether a build is running on this thread. The pipeline enters ``building()``
# around the model body it executes, so a decorated name called from inside
# that body composes (returns geometry) while the same name called from
# ``__main__`` or a REPL builds. Thread-local because the daemon worker and the
# CLI can both host builds on threads that must not see each other's state.
_BUILD_STATE = threading.local()


class BuildFrame:
    """One model body in flight on this thread.

    ``children`` is recorded from the CALLS the body makes -- every child decoded
    or run for it -- never from what the geometry became."""

    def __init__(self, script_path: Path | None, function: str | None = None, parent: str | None = None) -> None:
        self.script_path = script_path
        # The decorated function this frame is building; None when unknown (a
        # caller that entered ``building()`` for a whole file).
        self.function = function
        # The model's identity, ``script::fn`` (cadgen.store.index.model_ref).
        self.model: str | None = model_ref(script_path, function) if script_path is not None else None
        # The model whose body called this one, for the build tree's events.
        self.parent = parent
        # (child model ref, the key of the result the call composed) -- one per CALL.
        self.children: list[tuple[str, str]] = []
        # A child whose build failed inside this body: the run fails with it even
        # when the body caught the exception (STORE.md §9a).
        self.failed: list[BaseException] = []


class BuildRun:
    """One top-level build in this process, shared by every frame nested in it:
    the models decoded or run so far, each once per run (``results``: model ->
    (key, tree)), the files those calls owe (``exports``: each a
    ``generation._Export``, queued as its model's result is recorded and finished
    when the run ends, in that order) and what the root command owns for the run
    (its logger)."""

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger
        self.results: dict[str, tuple[str, str]] = {}
        self.exports: list[Any] = []

    def finish(self) -> None:
        """Finish every export queued in this run, in the order queued -- children before
        the parent that called them -- each writing the files its model owes. Every export
        has its turn; the first failure is raised after the last one, the others printed."""
        failure: Exception | None = None
        for export in self.exports:
            try:
                export.finish()
            except Exception as error:  # noqa: BLE001 - the next export still gets its turn
                if failure is None:
                    failure = error
                else:
                    print(f"[cadgen] {type(error).__name__}: {error}", file=sys.stderr)
        self.exports.clear()
        if failure is not None:
            raise failure

    def abandon(self) -> None:
        """Leave every queued export unfinished: its file stays as it was, and the next
        run exports again what is owed."""
        for export in self.exports:
            export.abandon()
        self.exports.clear()


def current_run() -> BuildRun | None:
    return getattr(_BUILD_STATE, "run", None)


@contextlib.contextmanager
def build_run(logger: Any = None) -> Iterator[BuildRun]:
    """The run a top-level command owns (``generation``): every decorated call made
    inside it, at any depth, belongs to this run, and the run finishes the exports
    those calls queued as it ends -- after the command's own body, before it reports
    its result. A run that failed still finishes them (the children built before the
    failure owe their files, and the pool is writing them), its own failure the one
    reported; an interrupted one abandons them. Nests for a build started inside a
    build (a test's), each its own."""
    previous = current_run()
    run = _BUILD_STATE.run = BuildRun(logger)
    try:
        try:
            yield run
        except Exception:
            try:
                run.finish()
            except Exception as error:  # noqa: BLE001 - the run's own failure is the one reported
                print(f"[cadgen] {type(error).__name__}: {error}", file=sys.stderr)
            raise
        except BaseException:
            run.abandon()
            raise
        run.finish()
    finally:
        _BUILD_STATE.run = previous


def _same_file(left: Path, right: Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except (OSError, RuntimeError):
        return Path(left) == Path(right)


def current_frame() -> BuildFrame | None:
    frames = getattr(_BUILD_STATE, "frames", None)
    return frames[-1] if frames else None


@contextlib.contextmanager
def building(script_path: Path | None = None, function: str | None = None) -> Iterator[BuildFrame]:
    """Mark this thread as executing a model body (the pipeline's call site).
    Yields the frame that collects the body's children."""
    frames = getattr(_BUILD_STATE, "frames", None)
    if frames is None:
        frames = _BUILD_STATE.frames = []
    enclosing = frames[-1] if frames else None
    frame = BuildFrame(script_path, function, parent=enclosing.model if enclosing is not None else None)
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
    # Typed mates (kinematics= dict, validated at decoration); axis refs
    # resolve at build and the block lands in the model's sidecar. STEP only.
    kinematics: KinematicsDef | None = None
    # Named intrinsic material declarations and the animation clips. Both are
    # validated at decoration and resolved during publication, where the clips
    # are baked to keyframes against the written document.
    materials: dict[str, Any] | None = None
    animation: dict[str, Any] | None = None
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

# Keyed by resolved script path: every first-party file EXECUTED while the
# generation loader last loaded the script, with its (mtime_ns, size) then. A
# model's declarations are evaluated at import from whatever the script imports
# (``from lib.dims import NAME`` feeding ``out=``), so a registry entry is only as
# fresh as ALL of those files, not just the script's own bytes -- a warm worker
# that checked the script alone rebuilt an edited helper's model under its OLD
# output name. A script that registered by running as ``__main__`` has no entry:
# that process executed it from disk itself.
_IMPORT_CLOSURES: dict[Path, tuple[tuple[Path, tuple[int, int] | None], ...]] = {}


def record_import_closure(script_path: Path, executed_files) -> None:
    """Remember which files fed ``script_path``'s registrations, and their bytes."""
    resolved = Path(script_path).resolve()
    _IMPORT_CLOSURES[resolved] = tuple(
        (path, _script_stamp(path)) for path in sorted(executed_files) if path != resolved
    )


def import_closure_current(script_path: Path) -> bool:
    """False once any file that fed the script's last load holds different bytes."""
    closure = _IMPORT_CLOSURES.get(Path(script_path).resolve(), ())
    return all(_script_stamp(path) == stamp for path, stamp in closure)


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
        from cadgen._internal.cli_from_function import report_failure

        report_failure(
            exc, prog=f"python {self.script.name}",
            as_json="--json" in sys.argv[1:], verbose="--verbose" in sys.argv[1:],
        )
        raise SystemExit(1)


def _report_uncaught_declaration(exc_type, exc, tb) -> None:
    """``sys.excepthook``: a declaration failure that escaped to the top of a
    script run (the script imported a model file whose decorator refused its
    arguments) is reported like the runner reports a build failure, instead of
    a traceback. Anything else goes to the previous hook."""
    main = sys.modules.get("__main__")
    # CPython 3.13.15+ and 3.14.7+ (gh-152132) remove ``__main__.__file__`` before
    # they call this hook; a ``python script.py`` run still names the script in
    # ``sys.argv[0]``.
    file = getattr(main, "__file__", None) or (sys.argv[0] if sys.argv else None)
    if getattr(exc, "__cadgen_declaration__", False) and file and "--verbose" not in sys.argv[1:]:
        from cadgen._internal.cli_from_function import report_failure

        report_failure(exc, prog=f"python {Path(file).name}", as_json="--json" in sys.argv[1:])
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
    kinematics: object = None,
    materials: object = None,
    animation: object = None,
    step_output: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    with _declaring_here():
        kinematics_def = (
            normalize_kinematics(kinematics, where=f"@{fmt}") if kinematics is not None else None
        )
        from cadgen._internal.source_sidecar import normalize_materials
        from cadgen.animation import normalize_clips

        materials_def = normalize_materials(materials, where=f"@{fmt} materials=")
        animation_def = normalize_clips(animation, where=f"@{fmt} animation=")
        out = _checked_out(out, where=f"@{fmt}")

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
            kinematics=kinematics_def,
            materials=materials_def,
            animation=animation_def,
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
                    # another build it is just its body (2D geometry), no result of its own.
                    return func()
                # Composition: a parent's body asked for this child. The same rule as
                # the top level -- decode its stored result, or run it -- and the
                # geometry handed back is that result, decoded.
                return _child(_REGISTRY.get(defn.ref, defn), frame)
            if args or kwargs:
                raise TypeError(
                    f"{func.__name__}() takes no arguments: a model is one configuration "
                    "of one output. Calling it builds that output."
                )
            # A top-level call builds. The registry entry may have been extended by a
            # mesh decorator stacked ABOVE @step since `defn` was captured, so read it
            # back rather than closing over the original.
            current = _REGISTRY.get(defn.ref, defn)
            from cadgen.daemon.executors import capture_source_result

            with capture_source_result(current.ref) as built:
                code = _build(current)
                built._finish(code)
            if code != 0:
                raise SystemExit(code)
            tree = built.wait_result() if current.fmt == "step" else None
            if current.fmt == "step" and _caller_discards_model_result():
                return None
            # ...and hands back the geometry it built (or found current), so a plain
            # used return, notebook or REPL gets the shape a parent would: the model's
            # tree materialized. A drawing has no tree and returns None. The bare-call
            # shortcut above still waits for the checked source result before deciding,
            # so persistence failures remain observable.
            return _built_geometry(current, tree=tree)

        model.__cadgen_model__ = defn  # type: ignore[attr-defined]
        # A model's body runs in its own build, reached through a call -- never
        # inline behind a caller's closure. functools.wraps would hand it out as
        # __wrapped__ (``arm.__wrapped__()``, ``inspect.unwrap``).
        del model.__wrapped__
        return model

    return apply


def step(
    func: Callable[..., Any] | None = None,
    *,
    out: str | None = None,
    kinematics: object = None,
    materials: object = None,
    animation: object = None,
    **unsupported: Any,
):
    """Declare a STEP model. Usable bare (``@step``) or configured (``@step(...)``).

    ``kinematics=`` takes the typed-mates dict (see ``cadgen.kinematics``).
    ``materials=`` declares named definitions and label/group assignments;
    ``animation=`` takes a dict of clip id -> ``cadgen.clip(update, duration=...)``,
    baked to keyframes when the model builds (see ``cadgen.animation``). No
    decorator argument changes the geometry a model writes: the geometry is the
    function's return value; the arguments decide where the files land and
    what the sidecar declares. No decorator names
    declaration changes the STEP geometry or its authored colors.
    """
    with _declaring_here():
        _reject_unknown_kwargs("step", unsupported)
    decorator = _decorator(
        "step",
        out=out,
        kinematics=kinematics,
        materials=materials,
        animation=animation,
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
    decorator = _decorator("dxf", out=out)
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
            wrapper = _decorator("step", out=None, step_output=False)(target)
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


def _child(defn: ModelDef, frame: BuildFrame) -> Any:
    """A parent's body called a child: its stored result, decoded, or the result
    of running it now, serially, in this process (STORE.md §9a).

    The same gate as the top level, in the caller's own process: the child's
    record is read, and its body runs here -- its own build, publishing its own
    record and exporting its own files -- only when the store holds no result
    for its inputs as they are. Either way the geometry handed back is the
    stored result decoded (``store.materialize``), so the parent's own features
    see a child the same way on a hit and on a miss, a child runs once per run
    however often it is called, and children are recorded from the CALLS, never
    from the geometry. A child's failure fails the run even when the body
    catches it: the run notes it on the frame.

    To the parent's capture the child's pipeline is cadgen's own reading
    (``filetrace.paused``): what the child's gate hashes, what its export writes
    and its verify parses, what its body read -- its body records in a capture of its
    own -- is the child's, and the child is the parent's input by its result.
    """
    from cadgen._internal.build_timing import cadgen_work, child_build
    from cadgen._internal.filetrace import paused
    from cadgen._internal.generation import build_child
    from cadgen.daemon import telemetry
    from cadgen.store.materialize import materialize

    child = defn.ref
    if any(f.model == child for f in _frames() if f.model is not None):
        raise RuntimeError(
            f"{defn.script_path.name}::{defn.name} is called while it is itself being built: "
            "a model may not depend on itself"
        )
    telemetry.job_child()  # an assembly, for a build this process counts itself (``cold_build``)
    try:
        with child_build(), paused():
            key, tree = build_child(defn)
    except BaseException as exc:
        frame.failed.append(exc)
        raise
    frame.children.append((child, key))
    # Loading the child's geometry is cadgen's time, not the parent's model code.
    with cadgen_work():
        return materialize(tree, label=defn.name)


def _frames() -> list[BuildFrame]:
    return list(getattr(_BUILD_STATE, "frames", None) or [])


def _build(defn: ModelDef) -> int:
    """Run the pipeline for a top-level call of a model and return its exit code."""
    # The user's flags are parsed HERE, in the process they started, before any
    # handoff: `--help` and a usage error end the run now (exit 0 / exit 2) on the
    # warm path exactly as on the cold one. Handed to the daemon unparsed, `--help`
    # came back as a job that exited 0 having built nothing, and the wait for its
    # source result raised. The parser is argparse over stdlib -- no CAD import.
    from cadgen.cli._run_model import check_user_flags

    argv = check_user_flags(
        sys.argv[1:], prog=f"python {defn.script_path.name}", called=defn.name
    )
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
        from cadgen.daemon import telemetry

        # Counted here as the daemon counts the builds it answers: no daemon answered this one.
        return telemetry.cold_build(
            "dxf" if defn.fmt == "dxf" else "step", "script",
            lambda: run_model_argv([*target, *argv], prog=f"python {defn.script_path.name}"),
            meshes=bool(defn.mesh_exports),
        )


def _built_geometry(defn: ModelDef, *, tree: str | None) -> Any:
    """What a top-level call hands back after its build: the model's tree,
    materialized -- the geometry a parent composing this model would receive.
    None for a drawing (no tree). Never resolves a mutable model record."""
    if defn.fmt != "step":
        return None
    from cadgen.store.materialize import materialize

    if not tree:
        raise RuntimeError(f"{defn.ref}: successful build supplied no source result")
    return materialize(tree, label=defn.name)
