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
  gate, locks/progress, incremental package build, ``.step``/``.dxf`` output —
  via the warm daemon when available, in-process otherwise. It returns
  ``None``: the caller is the build's initiator, and loading the shape back
  into it would force the kernel import the gate exists to avoid. A failed
  build raises ``SystemExit`` with the pipeline's exit code, so ``python
  model.py`` exits the way a build should.
- **A call inside a build composes.** While a build is running (any model's,
  any thread of this process), calling a decorated name runs its body and
  returns the shape (or drawing) — this is how an assembly uses its children.
  Nothing is written for the child; wrap the call in ``cadgen.compose.memo``
  to cache it across builds.
- **One model per file.** Entry identity (refs, packages, closures) is keyed
  by the source file everywhere in the pipeline, so a file defines exactly one
  ``@step`` or ``@dxf`` model.

Per-run flags ride ``sys.argv`` of the top-level call: ``--force``,
``--verbose``, ``--json``, ``-o/--output``, ``--mesh-tolerance``,
``--mesh-angular-tolerance``, ``--lock-timeout``. Durable configuration lives
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
from cadgen.metadata import MeshExportDecl, resolve_model_output_path

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


def build_in_progress() -> bool:
    return getattr(_BUILD_STATE, "depth", 0) > 0


@contextlib.contextmanager
def building() -> Iterator[None]:
    """Mark this thread as executing a model body (the pipeline's call site)."""
    _BUILD_STATE.depth = getattr(_BUILD_STATE, "depth", 0) + 1
    try:
        yield
    finally:
        _BUILD_STATE.depth -= 1


@dataclass(frozen=True)
class ModelDef:
    """One registered model: the decorated function plus its durable options."""

    func: Callable[..., Any]
    fmt: str  # "step" | "dxf"
    script_path: Path
    out: str | None
    kind: str | None
    mesh_tolerance: float | None
    mesh_angular_tolerance: float | None
    # Typed mates (kinematics= dict, validated at decoration); axis refs
    # resolve at build and the block lands in the model's sidecar. STEP only.
    kinematics: KinematicsDef | None = None
    # The kinematics dict's "at" bake point resolved to {dof: value}: the
    # artifact is WRITTEN at this configuration (and is therefore its own q=0).
    # None = authored rest.
    bake_pose: dict[str, float] | None = None
    # Script-relative path of the .anim.js choreography module; its TEXT is
    # copied into the sidecar at build (never a path in generated files).
    animation: str | None = None
    # Declared mesh serializations (@stl/@glb/@threemf). STEP models only.
    mesh_exports: tuple[MeshExportDecl, ...] = ()

    @property
    def output_path(self) -> Path:
        return resolve_model_output_path(self.script_path, fmt=self.fmt, explicit_out=self.out)


# Keyed by resolved script path. One model per file is a hard rule (see module
# docstring), so the value is a single ModelDef, not a list.
_REGISTRY: dict[Path, ModelDef] = {}


def registered_model(script_path: Path) -> ModelDef | None:
    return _REGISTRY.get(Path(script_path).resolve())


def registered_models() -> dict[Path, ModelDef]:
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
    existing = _REGISTRY.get(defn.script_path)
    if existing is not None and existing.func.__qualname__ != defn.func.__qualname__:
        raise RuntimeError(
            f"{defn.script_path.name} defines more than one CAD model "
            f"({existing.func.__name__} and {defn.func.__name__}); a model file "
            "defines exactly one @step or @dxf entry — split it into two files"
        )
    _REGISTRY[defn.script_path] = defn


def _reject_unknown_kwargs(deco_name: str, kwargs: dict[str, Any]) -> None:
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"@{deco_name} got an unexpected keyword argument: {unexpected}")


def _normalize_animation(animation: object, *, fmt: str) -> str | None:
    if animation is None:
        return None
    text = str(animation).strip()
    if not text.lower().endswith(".js"):
        raise ValueError(
            f"@{fmt} animation must name a .js module beside the script "
            f"(e.g. animation='arm.anim.js'), got {animation!r}"
        )
    return text


def _decorator(
    fmt: str,
    *,
    out: str | None,
    kind: str | None,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    kinematics: object = None,
    animation: object = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if kind is not None and kind not in {"part", "assembly"}:
        raise ValueError(f"@{fmt} kind must be 'part' or 'assembly', got {kind!r}")
    kinematics_def = (
        normalize_kinematics(kinematics, where=f"@{fmt}") if kinematics is not None else None
    )
    bake_pose = None if kinematics_def is None else kinematics_def.at
    animation_path = _normalize_animation(animation, fmt=fmt)

    def apply(func: Callable[..., Any]) -> Callable[..., Any]:
        _validate_signature(func, fmt=fmt)
        script_path = _script_path_of(func)
        pending = tuple(getattr(func, "__cadgen_pending_mesh_exports__", ()))
        if pending and fmt != "step":
            names = ", ".join(f"@{_MESH_FMT_DECORATOR[d.fmt]}" for d in pending)
            raise TypeError(
                f"{script_path.name} stacks {names} on a @{fmt} drawing; "
                "STL/3MF/GLB derive from a @step model's geometry"
            )
        if pending:
            try:
                delattr(func, "__cadgen_pending_mesh_exports__")
            except AttributeError:
                pass
        defn = ModelDef(
            func=func,
            fmt=fmt,
            script_path=script_path,
            out=out,
            kind=kind,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
            kinematics=kinematics_def,
            bake_pose=bake_pose,
            animation=animation_path,
            mesh_exports=pending,
        )
        _register(defn)
        func.__cadgen_model__ = defn  # type: ignore[attr-defined]

        @functools.wraps(func)
        def model(*args: Any, **kwargs: Any) -> Any:
            if build_in_progress():
                # Composition: an assembly's body asked for this child's geometry.
                return func(*args, **kwargs)
            if args or kwargs:
                raise TypeError(
                    f"{func.__name__}() takes no arguments: a model is one configuration "
                    "of one output. Calling it builds that output."
                )
            # A top-level call builds. The registry entry may have been extended by a
            # mesh decorator stacked ABOVE @step since `defn` was captured, so read it
            # back rather than closing over the original.
            current = _REGISTRY.get(script_path, defn)
            code = _build(current)
            if code != 0:
                raise SystemExit(code)
            return None

        model.__cadgen_model__ = defn  # type: ignore[attr-defined]
        return model

    return apply


def step(
    func: Callable[..., Any] | None = None,
    *,
    out: str | None = None,
    kind: str | None = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    kinematics: object = None,
    animation: str | None = None,
    **unsupported: Any,
):
    """Declare a STEP model. Usable bare (``@step``) or configured (``@step(...)``).

    ``kinematics=`` takes the typed-mates dict (see ``cadgen.kinematics``),
    whose ``"at"`` key names the configuration to BAKE the artifact at (a
    preset name or ``{dof: value}``; the written artifact is its own q=0).
    ``animation=`` names a ``.js`` choreography module beside the script whose
    text is copied into the sidecar. STEP is the only format with animation —
    mesh exports are static bakes.
    """
    _reject_unknown_kwargs("step", unsupported)
    decorator = _decorator(
        "step",
        out=out,
        kind=kind,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
        kinematics=kinematics,
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
    for elsewhere in ("kinematics", "animation"):
        if elsewhere in unsupported:
            raise TypeError(
                f"@dxf takes no {elsewhere}=: a drawing is 2D geometry — kinematics "
                "and its 'at' bake point live on @step and the mesh decorators, "
                "and animation is @step-only"
            )
    _reject_unknown_kwargs("dxf", unsupported)
    decorator = _decorator(
        "dxf", out=out, kind=None, mesh_tolerance=None, mesh_angular_tolerance=None
    )
    return decorator(func) if func is not None else decorator


_MESH_FMT_DECORATOR = {"stl": "stl", "glb": "glb", "3mf": "threemf"}


def _validate_variant(existing, decl: MeshExportDecl, deco_name: str) -> None:
    """Variants of one format are allowed; ambiguous duplicates are not: two
    bare declarations collide at the sibling default, two identical out=
    targets collide outright."""
    if decl.out is None:
        if any(d.fmt == decl.fmt and d.out is None for d in existing):
            raise TypeError(
                f"bare @{deco_name} is declared more than once; at most one "
                "declaration per format may omit out= (the sibling default)"
            )
    elif any(d.fmt == decl.fmt and d.out == decl.out for d in existing):
        raise TypeError(f"@{deco_name} is declared twice for the same target {decl.out!r}")


def _mesh_export_decorator(deco_name: str, fmt: str):
    """Factory for ``@stl``/``@glb``/``@threemf``: metadata-attachers, never
    wrappers. Below ``@step`` they park a pending declaration on the raw
    function; above it they extend the registered model. Both routes converge
    in the loader import, so stacking order is behavior-neutral."""
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
        if "animation" in unsupported:
            raise TypeError(
                f"@{deco_name} takes no animation=: mesh exports are static "
                "bakes with no sidecar — animation is a STEP-x-viewer concern "
                "and lives on @step only"
            )
        _reject_unknown_kwargs(deco_name, unsupported)
        if out is not None and not str(out).lower().endswith(suffix):
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
            bake_pose=None if kinematics_def is None else kinematics_def.at,
        )

        def attach(target: Callable[..., Any]) -> Callable[..., Any]:
            existing_model: ModelDef | None = getattr(target, "__cadgen_model__", None)
            if existing_model is not None:
                # Above @step: extend the registered model in place.
                if existing_model.fmt != "step":
                    raise TypeError(
                        f"@{deco_name} declares a mesh export of a @step model; "
                        f"{existing_model.script_path.name} is a @{existing_model.fmt} drawing"
                    )
                _validate_variant(existing_model.mesh_exports, decl, deco_name)
                updated = _replace(
                    existing_model, mesh_exports=(*existing_model.mesh_exports, decl)
                )
                _REGISTRY[updated.script_path] = updated
                target.__cadgen_model__ = updated  # type: ignore[attr-defined]
                return target
            # Below @step: park a pending declaration for @step to consume.
            pending = list(getattr(target, "__cadgen_pending_mesh_exports__", ()))
            _validate_variant(pending, decl, deco_name)
            pending.append(decl)
            target.__cadgen_pending_mesh_exports__ = tuple(pending)  # type: ignore[attr-defined]
            return target

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
        "build123d as bd` instead of importing build123d/OCP, and keep `bd.<anything>` "
        "out of module-level constants and default arguments (each one resolves the "
        "attribute at import). Then a call on a current model returns without the "
        "~2.5s import (see the cad skill docs).",
        file=sys.stderr,
    )


def _build(defn: ModelDef) -> int:
    """Run the pipeline for a top-level call of a model and return its exit code."""
    argv = sys.argv[1:]
    _maybe_hint_eager_imports(defn)

    # Warm handoff BEFORE any heavy import. The daemon worker imports the module
    # under a loader name (never __main__), so its `__main__` block does not run
    # there; the runner executes the model body inside `building()`.
    if os.environ.get("CADGEN_DAEMON") != "0" and not os.environ.get("CADGEN_DAEMON_CHILD"):
        try:
            from cadgen.daemon.client import run_via_daemon
        except ModuleNotFoundError:
            warm_exit: int | None = None
        else:
            warm_exit = run_via_daemon(
                "run",
                [str(defn.script_path), *argv],
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

    return run_model_argv(
        [str(defn.script_path), *argv], prog=f"python {defn.script_path.name}"
    )
