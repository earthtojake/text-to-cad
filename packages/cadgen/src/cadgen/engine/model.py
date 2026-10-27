"""Models: the decorators, a model's identity, and what calling one does.

A model is a parameterless function that returns a build123d shape. It becomes a document
through exactly one of two declarations: bare ``@model`` (a document with no file), or one or
more file decorators -- ``@xbf``, ``@step``, ``@glb``, ``@stl``, ``@threemf`` and ``@dxf`` (the
drawing of a planar result: a sketch, a face, wires or edges) -- a document with those files;
``@model`` stacked with a file decorator is refused. By default its id uses ``script.py::function``.
An explicit ``name=`` uses the script folder and that name instead, independent of the declaring file. Every file decorator
requires its output path: ``@xbf("XBF/part.xbf")`` or ``@step(out="part.step")``. Relative paths
are relative to the script. Everything else is the model's code: its material, colours, joints,
the pose its joints are connected at (the pose every file shows), its mechanism states, couplings
and configuration sequences (``mechanism_state``, ``gear_pair`` and its siblings,
``configuration_sequence``). A picture is the ``snapshot`` verb's, never a declaration. The outputs
are kept in the order the decorators are written, top to bottom, and the xbf, when declared, is
always written first.

The decorated function is a ``Model``: the function, its id (``.id``: ``ids.model_id`` of its
script and function, or its folder and explicit ``name=``) and the debug seam
``.build(verify=, profile=)``. Decoration only declares: imports and definitions never build or
exit the caller. A call builds the model through the engine and returns its document's handle
(``api.Document``: ``.id``, ``.url``, ``.name``, ``.shape``, ``.export``, ``.snapshot``), never a
bare shape. The script's own Python control flow, including its main block, selects calls.

Called inside a build, a model is a child: its body runs in the same run, with the same memo,
and the call returns the child document's handle, whose ``.shape`` is the result in this process:
a sub-assembly of whatever the caller makes of it, labelled with the child's function name when
its body gave it no label. A model is a pure function of its source, so a second call in one
build hands back a new placement of the same result -- new objects sharing the first call's
geometry -- rather than running the body again: a child used four times is one prototype placed
four times. A child writes the files it declares, as a target does: once a build, from its own
document (``BuildContext.children``, ``build``). Called outside a build, a model asks its warm
worker to build it.

``model(shape, name=...)`` hands a shape over from a script or a REPL: no function, no body to
run again (``api.hand_over``).
"""

from __future__ import annotations

import functools
import sys
import inspect
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cadgen.engine.ids import canonical, check_name, model_id

__all__ = ["KINDS", "Memo", "Model", "Output", "Target", "configuration_sequence", "dxf", "glb", "mechanism_state", "memo",
           "model", "paint", "read_step", "read_xbf", "step", "stl", "threemf", "xbf", "models_in"]

# The suffix each output kind writes, and the default file name's.
SUFFIXES = {"xbf": ".xbf", "step": ".step", "glb": ".glb", "stl": ".stl", "threemf": ".3mf", "dxf": ".dxf"}
_ACCEPTED = {"xbf": (".xbf",), "step": (".step", ".stp"), "glb": (".glb",), "stl": (".stl",), "threemf": (".3mf",),
             "dxf": (".dxf",)}
KINDS = tuple(SUFFIXES)
# The default folder for an xbf requested by a build flag without a path.
XBF_FOLDER = "XBF"

_CONTEXT = threading.local()
# Every model defined since a build began, by its identity (``script::function``): a body
# a replay ran is known by its name alone, and this says which of them are models
# (``BuildContext.children``). A build forgets them before it loads the script.
_MODELS: dict[str, "Model"] = {}


@dataclass(frozen=True)
class Output:
    """One file a model declares: its kind and path (None requests the CLI default)."""

    kind: str
    out: str | None


@dataclass(frozen=True)
class Target:
    """One file a build writes: its kind and its path."""

    kind: str
    path: Path


def check_output(kind: str, out: Any, where: str) -> None:
    """A path a decorator or a flag gives for ``kind``: a string ending in the kind's suffix."""
    if out is None:
        return
    if not isinstance(out, (str, os.PathLike)) or not os.fspath(out):
        raise TypeError(f"{where} takes a path")
    if Path(out).suffix.lower() not in _ACCEPTED[kind]:
        raise ValueError(f"{where}: the file must end in {' or '.join(_ACCEPTED[kind])}, not {os.fspath(out)!r}")


def _told(error: BaseException, said: str | None = None) -> None:
    """A failed build the program's own call reported (its model's frames and the ``failed`` line,
    ``cli._reported``), or a call the engine never served (none runs and none can start, a sandbox's
    refusal, its port held) whose one line is ``said``: raised as ever, so a caller may catch it,
    and, left uncaught, ending the program with status 1 and nothing more said than ``said`` on
    stderr, as a ``cadgen`` verb says it -- not a traceback of this process's client code."""
    error._told = True  # type: ignore[attr-defined]
    error._said = said  # type: ignore[attr-defined]
    hook = sys.excepthook
    if getattr(hook, "_cadgen_told", False):
        return

    def quiet(kind: type[BaseException], value: BaseException, trace: Any) -> None:
        if not getattr(value, "_told", False):
            hook(kind, value, trace)
        elif getattr(value, "_said", None):
            print(value._said, file=sys.stderr, flush=True)

    quiet._cadgen_told = True  # type: ignore[attr-defined]
    sys.excepthook = quiet


def _calls_after(frame: Any) -> bool:
    """Whether the program's code calls a model after the line ``frame`` stands at: what its stopping
    there leaves unbuilt. Read from the source of the frame's file (a call is a model's when its name,
    or ``module.name``, is one in the frame's globals); one that cannot be read is said to."""
    import ast

    try:
        tree = ast.parse(Path(frame.f_code.co_filename).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return True
    names = frame.f_globals

    def model_at(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return isinstance(names.get(node.id), Model)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return isinstance(getattr(names.get(node.value.id), node.attr, None), Model)
        return False

    return any(isinstance(node, ast.Call) and node.lineno > frame.f_lineno and model_at(node.func)
               for node in ast.walk(tree))


class Model:
    """A decorated function: the body, the script it lives in, the outputs it declares."""

    def __init__(self, function: Callable[[], Any]) -> None:
        if not callable(function) or not inspect.isfunction(function):
            raise TypeError("a model decorator takes a function")
        parameters = [p for p in inspect.signature(function).parameters.values()
                      if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
        if parameters:
            raise TypeError(f"model {function.__name__!r} takes parameters; a model takes none")
        functools.update_wrapper(self, function)
        self.function = function
        self.name = function.__name__
        filename = function.__code__.co_filename
        if not os.path.isfile(filename):
            raise ValueError(f"model {self.name!r} is defined in {filename}, no saved .py file: a function becomes a "
                             "document from the file it is in. Where the code is in no file (a notebook cell, a "
                             f"REPL), build the shape and hand it over: model(shape, name={self.name!r})")
        self.script = Path(canonical(filename))
        self.outputs: list[Output] = []
        # The name within the script folder; None keeps the script/function id.
        self.explicit_name: str | None = None
        self._bare = False  # declared by ``@model``
        self.__xbf_model__ = True
        _MODELS[f"{self.script}::{self.name}"] = self

    @property
    def id(self) -> str:
        """The script/function id by default, or the folder/name id of an explicit name."""
        return model_id(self.script, self.name, self.explicit_name)

    @property
    def fingerprint(self) -> str | None:
        """SHA-256 of its script's bytes (``identity.fingerprint``), read once a build per script
        (``_FINGERPRINTS``) and only when a report or a re-attachment asks: never at declaration."""
        script = str(self.script)
        if script not in _FINGERPRINTS:
            from cadgen.engine.identity import fingerprint

            _FINGERPRINTS[script] = fingerprint(self.script)
        return _FINGERPRINTS[script]

    @property
    def source(self) -> dict[str, Any]:
        """What a build's report says of this model's declaration: its script and function, its
        first line, its explicit name, its script's fingerprint and its module."""
        return {"script": str(self.script), "name": self.name,
                "line": self.function.__code__.co_firstlineno, "explicit_name": self.explicit_name,
                "fingerprint": self.fingerprint, "module": self.function.__module__}

    def declared(self, by: str) -> "Model":
        """One declaration more on this function: ``model`` (bare ``@model``) or a file kind. A
        function becomes a document through ``@model`` or through its file decorators, never both."""
        kinds = [output.kind for output in self.outputs] if by == "model" else [by] if self._bare else []
        if kinds:
            raise TypeError(f"model {self.name!r} is declared by @model and @{kinds[0]}: a function becomes a "
                            "document through @model (a document with no file) or through its file decorators "
                            f"(a document with those files), never both; drop @model")
        if by == "model":
            self._bare = True
        return self

    def named(self, name: str | None) -> "Model":
        """The explicit ``name=`` a declaration gives: this model's name in its script's folder, its
        id the folder's and the name's. One declaration per name in a folder: in this process
        (``claim``), and against the file the registry's record of it points at
        (``identity.claimed``); refused naming both ``file:line``."""
        if name is None:
            return self
        check_name(name)
        if self.explicit_name is not None and self.explicit_name != name:
            raise TypeError(f"model {self.name!r} declares two names, {self.explicit_name!r} and {name!r}")
        line = self.function.__code__.co_firstlineno
        claim(str(self.script.parent), name, str(self.script), self.name, line)
        from cadgen.engine import registry

        held = registry.current()
        if held is not None:
            from cadgen.engine.identity import claimed

            claimed(held, {"script": str(self.script), "name": self.name, "line": line}, name)
        self.explicit_name = name
        return self

    @property
    def address(self) -> str:
        return getattr(self, "_address", f"{self.script}::{self.name}")

    @property
    def identity(self) -> str:
        return f"{self.script.name}::{self.name}"

    def __repr__(self) -> str:
        return f"<model {self.identity}>"

    def __call__(self) -> Any:
        build = getattr(_CONTEXT, "build", None)
        if build is not None:
            return build.child(self)
        from cadgen.engine import api
        from cadgen.engine.cli import _log, _reported

        # Decoration only declares. The caller's control flow reaches this build,
        # and resumes after it; importing the engine never runs or exits a script.
        # A call the program's own code makes (``python caller.py``) is reported, wherever the
        # model is defined: ``caller.py`` calling ``parts.cube()`` prints cube's id and view.
        caller = sys._getframe(1)
        program = caller.f_globals.get("__name__") == "__main__"
        previous = getattr(_CONTEXT, "program", False)
        _CONTEXT.program = program
        try:
            built = self.build(log=_log if program else None)
        except (ConnectionError, api.EngineError) as error:
            # The engine not reached, or refusing the call before any build (``api._ask``): one line,
            # said only if nothing catches it (``_told``).
            _told(error, f"cadgen: {error}")
            raise
        finally:
            _CONTEXT.program = previous
        if program:
            _reported(built.models, built.wall, built.fresh, False)
        if not built.ok:
            error = api.EngineError(next(row.get("error", "model failed") for row in built.models if not row.get("ok")))
            if program:
                # Said only if nothing catches it: the program stops here, and Python, not the
                # engine, decides which calls run (law 11), so the models it calls after this one
                # are not built -- and each keeps the document of its last run until it runs again.
                _told(error, f"the run stopped at {self.name}" + (": a model it calls after this one is not built"
                                                                    if _calls_after(caller) else ""))
            raise error
        return api.Document(self.name, self.script, built.models[0], Path.cwd())

    def _path(self, kind: str, out: Any) -> Path:
        if out is None:
            out = Path(XBF_FOLDER) / f"{self.name}.xbf" if kind == "xbf" else Path(self.name + SUFFIXES[kind])
        path = Path(out)
        if not path.is_absolute():
            path = self.script.parent / path
        return Path(_normalized(path))

    def targets(self) -> list[tuple[str, Path]]:
        """Each declared output as ``(kind, path)``, the xbf first, then the derived files
        in the order the decorators are written; a relative path is relative to the
        script's folder, and an output with no path is its default (``XBF/<function>.xbf``,
        ``<function><suffix>``) beside the script."""
        return [(target.kind, target.path) for target in self.plan()]

    def plan(self) -> list[Target]:
        """The files a build of this model writes: what its decorators declare (law 10), the
        xbf first, then the derived files in the order the decorators are written."""
        return [Target(output.kind, self._path(output.kind, output.out))
                for output in sorted(self.outputs, key=lambda output: output.kind != "xbf")]

    # --- the verbs, through the daemon (``cadgen.engine.api``) -----------------------------

    def build(self, *, verify: bool = False, profile: bool = False, log: Callable[[str], None] | None = None, daemon: bool = True) -> Any:
        """Build this model, through the daemon (``daemon=False``: in this process): it and every
        child model it calls write what their decorators declare, when the script explicitly calls it (``api.build_script``); a ``Report``. ``verify`` runs every body
        the memo would replay and compares its result with the logged one. ``profile`` measures
        the actual build call without forcing cache misses (engine README, Profiling)."""
        from cadgen.engine import api

        return api.build_script(self.script, [self.name], verify=verify, profile=profile, log=log, daemon=daemon)


def _normalized(path: Path) -> str:
    return os.path.normpath(os.path.abspath(path))


# --- a script as Python's import system has it --------------------------------------------


def module_of(script: Path) -> tuple[str, str | None, Path | None]:
    """The module Python's import system makes of a script: its name, its package, and the
    folder its package imports from. Inside a package -- the script's folder, and each folder
    above it up to the topmost, holding an ``__init__.py`` -- that is its dotted name
    (``proj.parts.model``; a package's own ``__init__.py`` is the package), the package, and the
    folder above the topmost package; anywhere else, its stem, None and None. A dot in a folder's
    name ends the package below that folder, and a dot in the script's stem leaves it loose: no
    dotted name can spell either."""
    script = Path(script).resolve()
    names: list[str] = []
    folder = script.parent
    if "." not in script.stem:
        while "." not in folder.name and folder.parent != folder and (folder / "__init__.py").is_file():
            names.append(folder.name)
            folder = folder.parent
    if not names:
        return script.stem, None, None
    package = ".".join(reversed(names))
    return (package if script.name == "__init__.py" else f"{package}.{script.stem}"), package, folder


def seat(script: Path, root: Path | None) -> None:
    """The module search path a script's imports resolve on: its folder first, as ``python
    script.py`` has it, so a module beside it imports by its own name; then its package's root
    (``module_of``), as ``python -m`` has it, so the package imports by its name. Each is moved
    there if the path holds it already."""
    import sys

    for folder in ([str(root)] if root is not None else []) + [str(Path(script).resolve().parent)]:
        if folder in sys.path:
            sys.path.remove(folder)
        sys.path.insert(0, folder)


def as_package_module(main: Any) -> None:
    """``python proj/parts/model.py``: a script run by its path from inside a package is given,
    the moment it imports the engine, what ``python -m proj.parts.model`` gives it -- its
    module's spec and package (``module_of``) and its package's root on the module search path
    (``seat``) -- so its relative imports, and the package by its name, resolve below that
    import as they do under ``-m`` and in the worker that builds it (``build.load_script``). It
    is still ``__main__``. A loose script is left as Python ran it."""
    import importlib.util

    script = Path(main.__file__).resolve()
    name, package, root = module_of(script)
    if package is None:
        return
    spec = importlib.util.spec_from_file_location(name, script)
    if spec is None:
        return
    seat(script, root)
    main.__spec__, main.__package__ = spec, package


# Where a model's document is kept: ``pointer``, a model in a saved file, which the engine's registry
# points at and knows the program that builds it again; ``memory``, kept in its worker's memory only,
# gone when the worker is. A shape handed over (``model(shape, name=...)``) is a third, ``shape``: its
# document is the bytes handed over, held and cached as a drained document is, with nothing to run.

# Each explicit name a declaration in this process gives, by its namespace (the script's folder),
# and the declaration that gave it: its script, its function and its first line. A build forgets
# them before it loads the script, as it forgets the models (``_MODELS``).
_NAMES: dict[tuple[str, str], tuple[str, str, int]] = {}
# Each script's fingerprint (``Model.fingerprint``), read once a build: forgotten with ``_NAMES``.
_FINGERPRINTS: dict[str, str | None] = {}


def claim(namespace: str, name: str, script: str, function: str, line: int) -> None:
    """``script``'s function ``function`` takes the explicit name ``name`` in ``namespace``; refused,
    naming both ``file:line``, when another declaration of this process has it -- another function,
    in this file or another. The same function declared again (a module loaded again, its line
    moved) keeps it."""
    other = _NAMES.setdefault((namespace, name), (script, function, line))
    if other[:2] != (script, function):
        raise ValueError(f"name {name!r} in namespace {namespace} is claimed by {other[0]}:{other[2]} and "
                         f"{script}:{line}; give one declaration another name")
    _NAMES[(namespace, name)] = (script, function, line)


def _no_animations(animations: Any) -> None:
    if animations is not None:
        raise TypeError("a model decorator takes no animations=: a model's body declares its animations "
                        "(animation(...)); animations= goes with a shape handed over, model(shape, name=...)")


def model(target: Any = None, /, *, name: str | None = None, animations: Any = None) -> Any:
    """Declare a model, optionally named within its script folder, or hand over a named shape."""
    if target is None:
        _no_animations(animations)
        if name is not None:
            check_name(name)
        return lambda function: model(function, name=name)
    if isinstance(target, Model) or inspect.isfunction(target):
        _no_animations(animations)
        found = target if isinstance(target, Model) else Model(target)
        return found.declared("model").named(name)
    from cadgen.engine import api

    caller = sys._getframe(1)
    while caller.f_back is not None and caller.f_code.co_filename == __file__:
        caller = caller.f_back
    return api.hand_over(target, name, animations=animations, frame=caller)


def _decorator(kind: str) -> Callable[..., Any]:
    def decorate(out: Any, *, name: str | None = None) -> Any:
        if out is None:
            raise TypeError(f"@{kind} requires an output path")
        check_output(kind, out, f"@{kind}(out=...)")
        if name is not None:
            check_name(name)

        def apply(target: Any) -> Model:
            model = target if isinstance(target, Model) else Model(target)
            model.declared(kind)
            if any(output.kind == kind for output in model.outputs):
                raise TypeError(f"model {model.name!r} declares @{kind} twice")
            model.outputs.insert(0, Output(kind, os.fspath(out)))
            return model.named(name)

        return apply

    decorate.__name__ = kind
    decorate.__qualname__ = kind
    decorate.__doc__ = (f"Declare an explicit output: @{kind}(out='path{SUFFIXES[kind]}'), optionally named "
                        "within the script folder by name=. The output path is required; decoration builds nothing.")
    return decorate


xbf = _decorator("xbf")
step = _decorator("step")
glb = _decorator("glb")
stl = _decorator("stl")
threemf = _decorator("threemf")
dxf = _decorator("dxf")


# --- @memo: a function worth replaying -------------------------------------------------


class Memo:
    """A function marked ``@memo``: one the engine may replay instead of executing.

    Called inside a build, a call is a body (``kernel/memo.py``, ``body``): keyed by the
    code it reaches (``sources.Symbols``, as a model's body is), the files it reads, and
    its arguments by value (``memo.call_key``), its kernel calls logged, and on a later
    build with the same key replayed without running -- the trace, so every element name,
    is what a run leaves. A second call with the same arguments in one build is a new
    placement of the first's result, as a child model's is. A call whose arguments cannot
    be keyed, or that returns no geometry, runs every time, and the build's report says
    which function and why (``retention.fallbacks``). Called outside a build, it is its
    function. It writes no file and declares none."""

    def __init__(self, function: Callable[..., Any]) -> None:
        if not inspect.isfunction(function):
            raise TypeError("@memo takes a function")
        parameters = list(inspect.signature(function).parameters)
        if parameters and parameters[0] in ("self", "cls"):
            raise TypeError(f"@memo on {function.__qualname__!r}: a method is not markable (its first parameter "
                            f"is {parameters[0]}); mark a function of the values it needs")
        functools.update_wrapper(self, function)
        self.function = function
        self.name = function.__qualname__
        source = inspect.getsourcefile(function) or inspect.getfile(function)
        self.script = Path(canonical(source))
        self.__xbf_memo__ = True

    @property
    def identity(self) -> str:
        return f"{self.script.name}::{self.name}"

    def __repr__(self) -> str:
        return f"<memo {self.identity}>"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        build = getattr(_CONTEXT, "build", None)
        if build is None:
            return self.function(*args, **kwargs)
        return build.memo(self, args, kwargs)


def memo(function: Any = None, /, **options: Any) -> Any:
    """Mark a function worth replaying: ``@memo``, bare. Its arguments are keyed by value
    (plain values, build123d's value types, materials, shapes the engine made); it returns
    geometry (a shape, or a tuple, list or dict of shapes); it writes nothing outside
    itself. A verifying build (``Model.build(verify=True)``)
    runs every call the engine would replay and compares what it makes with what was logged."""
    if options or function is None:
        raise TypeError("@memo takes no arguments: write @memo")
    if isinstance(function, Model):
        raise TypeError(f"@memo on model {function.name!r}: a model is already replayed; @memo marks a function")
    return Memo(function)


def models_in(namespace: dict[str, Any], script: Path) -> list[Model]:
    """The models a script's module defines, in definition order: those whose function
    lives in the script itself (a model it imports is a child, not one of its own)."""
    script = Path(script).resolve()
    found = []
    for value in namespace.values():
        if isinstance(value, Model) and value.script == script and value not in found:
            found.append(value)
    return found


# --- what a model's code may call --------------------------------------------------------


def paint(shape: Any, faces: Any, color: Any) -> Any:
    """Colour faces of a part, or give them a material: ``faces`` (a face, or several) of
    ``shape`` take ``color`` -- an sRGB hex string (``"#e68019"``, ``"#e68019cc"``), 0-255
    integers (three, or four with alpha), a build123d ``Color``, or a ``bd_materials.FinishedMaterial`` -- in the
    document, by their ordinal in the part. The colour is the one ``shape.color`` would give
    the same value (``colors``). A face holds one paint: a colour
    replaces its material, a material its colour. Returns ``shape``, whose paints the
    memo keys like its label.

    A part's material is set as its colour is, on the shape: ``part.material =
    bd_materials.metals.mild_steel()``; on an assembly, it is every part's below it that has none. Both
    are attributes of the object, and travel as build123d moves them: a copy, ``moved``
    and ``located`` keep them. Material assignment uses build123d's native property;
    set an explicit colour after assigning a material to override its PBR base colour.
    Paint and materials are for finished parts: set them after the last
    operation, so an edit of one is no kernel call (the memo keys them with the shape,
    and a compound does not hold its children's materials in its key)."""
    import build123d as bd
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    from cadgen.engine.colors import linear
    from cadgen.engine.kernel.memo import FACE_COLORS, FACE_MATERIALS
    from bd_materials import FinishedMaterial

    material = color if isinstance(color, FinishedMaterial) else None
    rgba = None if material is not None else tuple(linear(color, "paint's color"))
    mapped = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, mapped)
    painted = dict(shape.__dict__.get(FACE_COLORS) or {})
    given = dict(shape.__dict__.get(FACE_MATERIALS) or {})
    for face in ([faces] if isinstance(faces, bd.Shape) else list(faces)):
        ordinal = mapped.FindIndex(face.wrapped)
        if not ordinal:
            raise ValueError("paint: a face that is not one of the shape's")
        if material is not None:
            given[ordinal] = material
            painted.pop(ordinal, None)
        else:
            painted[ordinal] = rgba
            given.pop(ordinal, None)
    shape.__dict__[FACE_COLORS] = painted
    if given:
        shape.__dict__[FACE_MATERIALS] = given
    else:
        shape.__dict__.pop(FACE_MATERIALS, None)
    return shape


def mechanism_state(assembly: Any, name: str, **values: Any) -> Any:
    """Name a state of an assembly's mechanism (AP242's ``mechanism_state_representation``):
    ``mechanism_state(arm, "raised", elbow=90)`` sets the joint labelled ``elbow`` to 90
    degrees in the state ``raised`` (a number per joint, or for a joint of several values a
    sequence: a cylindrical joint's angle and position, a ball joint's three angles). The
    joints are build123d's, placed with ``connect_to``; the values they were connected at are
    the as-built state, and a joint a mechanism state does not name stays as built. The
    document keeps every mechanism state; the viewer offers them as presets, ``--pose NAME``
    draws a snapshot at one, and a configuration sequence's waypoint may name
    one. A mechanism state never changes the build: every file shows the model as built. A
    value outside its joint's range fails the build, in one line naming the state, the joint,
    the value and the range; one on a bound is within it. Returns ``assembly``."""
    from cadgen.engine import mechanism

    return mechanism.mechanism_state(assembly, name, **values)


def configuration_sequence(assembly: Any, name: str, waypoints_or_fn: Any = None, *, sweep: Any = None,
                           duration: Any = None, ease: str = "cubic", **removed: Any) -> Any:
    """Name a configuration sequence of an assembly's mechanism (AP242's
    ``interpolated_configuration_sequence``), by joint label: waypoints ``[(t, pose), ...]``
    (``t`` in seconds from 0, ``pose`` a mechanism state's name or ``{joint: value}``, the rest
    as built), ``sweep={joint: (from, to)}`` with ``duration``, or a function ``t -> {joint:
    value}`` with ``duration``. ``ease`` is ``cubic`` (eased in and out at every waypoint:
    AP242's synchronous interpolation) or ``linear``. A sequence is a finite clip; a player
    repeats it::

        configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])
        configuration_sequence(arm, "wave", [(0, {"wrist": -30}), (1, {"wrist": 30}), (2, {"wrist": -30})])
        configuration_sequence(arm, "nod", lambda t: {"elbow": 45 + 20 * math.sin(t)}, duration=6)

    The document keeps the definition, never frames (a function as its samples); a GLB
    export bakes it into a clip of the same name, and STEP, STL and 3MF ignore it. It never
    moves the build: the model is as its joints connect it. Returns ``assembly``."""
    from cadgen.engine import mechanism

    return mechanism.configuration_sequence(assembly, name, waypoints_or_fn, sweep=sweep, duration=duration, ease=ease,
                                            **removed)


def animation(assembly: Any, name: str, *, duration: Any) -> Any:
    """Name an animation of an assembly: a GLB's own choreography, ``duration`` seconds long,
    returned as a builder of glTF channels; its calls chain::

        show = animation(car, "showcase", duration=6)
        show.channel("lid", path="translation", keys=[(0, (0, 0, 0)), (1, (0, 0, 40))])
        show.rotation("wheel*", axis=(0, 1, 0), turns=3, start=1, interpolation="LINEAR")
        show.translation("door", by=(0, 300, 0), start=2, end=4)
        show.explode("body/*", radial=True, distance=40, end=2)       # helpers, compiled to channels
        show.hide("roof", at=3)                                       # a STEP scale channel to 0
        show.pose(at={0: "shut", 5: {"doors": 1}})                    # the mechanism, by its FK

    ``.channel(parts, path=, keys=, interpolation=)`` is glTF's channel (``path``
    ``translation``, ``rotation`` or ``scale``; ``interpolation`` ``CUBICSPLINE``, ``LINEAR`` or
    ``STEP``); ``.translation``, ``.rotation`` and ``.scale`` are channels from a start to an end.
    Parts are named as a ref's owner names them (a label, ``hand/finger.2``), or by a glob
    (``wheel*``). A configuration sequence is the mechanism's and the document keeps it; an animation is the GLB's:
    never written into the xbf, baked into every GLB the model declares when that GLB is written.
    Returns the builder."""
    from cadgen.engine.animations import animation as build

    return build(assembly, name, duration=duration)


def _read_step(path: Any) -> Any:
    from cadgen.engine.document import read_step_shape

    return read_step_shape(path)


_READ_STEP: Callable[[Any], Any] | None = None


def read_step(path: Any) -> Any:
    """A STEP file as a build123d shape: a compound tree of its assembly, every part and
    group labelled, coloured and given its material as the file has them. Parsed once per
    worker and held, in a reader process of the build's (its working memory never the
    worker's): a later build's read of the same bytes is the memo's hit, the same objects."""
    global _READ_STEP
    if _READ_STEP is None:
        from cadgen.engine.kernel.memo import wrap_function

        _READ_STEP = wrap_function("read_step", _read_step)
    import os

    from cadgen.engine.reader import refuse_written

    # Before the memo: a read of a file this build writes is refused, whether or not the memo holds it.
    refuse_written(path, "read_step")
    return _READ_STEP(os.fspath(path))


def _read_xbf(path: Any) -> Any:
    from cadgen.engine.document import read_xbf_shape

    return read_xbf_shape(path)


_READ_XBF: Callable[[Any], Any] | None = None


def read_xbf(path: Any) -> Any:
    """An engine document (``.xbf``) as a build123d shape: a copy of its geometry, as
    ``read_step`` gives a STEP's -- a compound tree of its assembly, every part and group
    named, coloured and given its materials (painted faces too) as the document has them,
    each element named as the document names it. Its mechanism and configurations are not
    imported: a part is a part. Read once per worker and held, keyed by the file's bytes, as
    ``read_step`` is. The fast way to bring a vendor STEP in: convert it once (``cadgen
    export vendor.step vendor.xbf``) and read the xbf."""
    global _READ_XBF
    if _READ_XBF is None:
        from cadgen.engine.kernel.memo import wrap_function

        _READ_XBF = wrap_function("read_xbf", _read_xbf)
    import os

    from cadgen.engine.reader import refuse_written

    refuse_written(path, "read_xbf")  # before the memo, as read_step's
    return _READ_XBF(os.fspath(path))


# --- a build's context -------------------------------------------------------------------


def instance(shape: Any) -> Any:
    """A new placement of ``shape``: new objects, of the same classes and attributes,
    sharing its geometry -- its TopoDS handle, and its children's -- with no kernel
    call. What a second call of a child model in one build hands back.

    What a model may change in place is each placement's own: every dict and list it holds
    is copied (a joint added to one placement is not on another), and its joints are new
    joints on the new objects, a joint connected to one in the same placement connected to
    that one's copy."""
    copied: dict[int, Any] = {}
    made = _instance(shape, copied)
    for joint in copied.values():
        other = joint.connected_to
        if other is not None and id(other) in copied:
            joint.connected_to = copied[id(other)]
    return made


def _instance(shape: Any, copied: dict[int, Any]) -> Any:
    import copy

    cls = type(shape)
    made = cls.__new__(cls)
    attrs = dict(shape.__dict__)
    children = attrs.pop("_NodeMixin__children", None)
    attrs.pop("_NodeMixin__parent", None)
    wrapped = attrs.get("_wrapped")
    if wrapped is not None:
        from build123d.topology.shape_core import downcast

        # ``Located`` hands back a bare ``TopoDS_Shape``: the placement holds its own class's
        # handle (a ``TopoDS_Solid``), as the shape it copies does, so its measures are the shape's.
        attrs["_wrapped"] = downcast(wrapped.Located(wrapped.Location()))
    attrs = {name: dict(value) if type(value) is dict else list(value) if type(value) is list else value
             for name, value in attrs.items()}
    joints = attrs.get("joints")
    if joints:
        from build123d import Joint

        for label, joint in joints.items():
            if isinstance(joint, Joint):
                joints[label] = copied[id(joint)] = copy.copy(joint)
                joints[label].parent = made
    made.__dict__.update(attrs)
    if children:
        copies = [_instance(child, copied) for child in children]
        for child in copies:
            child.__dict__["_NodeMixin__parent"] = made
        made.__dict__["_NodeMixin__children"] = copies
    return made


@functools.cache
def _engine_version() -> str:
    """The engine's own code, by its bytes: a body replayed is one this engine ran."""
    from cadgen.engine.sources import digest

    here = Path(__file__).resolve().parent
    return ":" + "".join(digest(path)[:12] for path in sorted([*here.glob("*.py"), *here.glob("kernel/*.py")]))


class BuildContext:
    """The models a build runs on this thread: the children each body calls, built once
    and placed again, and how long each took."""

    def __init__(self) -> None:
        self.results: dict[str, tuple[Any, Any]] = {}
        self.timings: dict[str, float] = {}
        self.stack: list[str] = []
        self.sources: dict[str, str] = {}
        self.resolved: dict[str, list] = {}
        # The first-party modules the script's load imported (``build`` sets it), the
        # build's symbol resolution, the time keys took and each body's fallbacks.
        self.loaded: set[str] | None = None
        # The build's folder: the script's (``build`` sets it).
        self.base: Path | None = None
        self.symbols: Any = None
        self.key_seconds = 0.0
        self.fallbacks: dict[str, list[str]] = {}
        # The script the build loaded (``build`` sets it): a model of another file is closed
        # over as a build of its own script closes it (``modules``).
        self.script: Path | None = None
        # The models the running target's body called, each once, in the order first called
        # (``child``): with those a replay ran, what the build writes after the run (``children``).
        self.called: dict[str, Model] = {}
        # Per script of a child model from another file: the resolution its closure is made with.
        self.others: dict[Path, Any] = {}

    def source(self, model: Model) -> str:
        """What a model's body is made of: the symbols its function reaches, a module's
        bytes where one cannot be followed (``sources.Symbols``), and the engine's own
        code; worked out once a build."""
        key = str(model.script) + "::" + model.name
        found = self.sources.get(key)
        if found is None:
            import time

            from cadgen.engine.sources import Symbols

            started = time.perf_counter()
            if self.symbols is None:
                self.symbols = Symbols(self.resolved, self.loaded, self.base)
            digest, reasons = self.symbols.key(model.function)
            if reasons:
                self.fallbacks[model.identity] = reasons
            found = self.sources[key] = digest + _engine_version()
            self.key_seconds += time.perf_counter() - started
        return found

    def modules(self, model: Model) -> tuple[dict[str, str], bool]:
        """A model's closure by file (``sources.Symbols.modules``), worked out with its key. A
        child model of another script is closed over as a build of that script closes it: from
        its folder, over the modules of this load that its script imports
        (``sources.closure_files``), so its document is the one a build of its own writes."""
        self.source(model)
        if self.script is None or model.script == self.script:
            return self.symbols.modules(model.function)
        symbols = self.others.get(model.script)
        if symbols is None:
            import sys

            from cadgen.engine.sources import Symbols, closure_files

            module = getattr(model.function, "__module__", None) or model.script.stem
            own = set(closure_files(model.script, module, self.resolved))

            def imported(name: str) -> bool:
                file = getattr(sys.modules.get(name), "__file__", None)
                return bool(file) and Path(file).resolve() in own

            loaded = {name for name in self.loaded or () if imported(name)}
            symbols = self.others[model.script] = Symbols(self.resolved, loaded, model.script.parent)
        return symbols.modules(model.function)

    def named(self, model: Model) -> dict[str, dict[str, str]]:
        """What ``modules`` digests per file, by name (``sources.Symbols.symbols``)."""
        self.modules(model)
        held = self.symbols if self.script is None or model.script == self.script else self.others[model.script]
        return held.symbols(model.function)

    def __enter__(self) -> "BuildContext":
        self.previous = getattr(_CONTEXT, "build", None)
        _CONTEXT.build = self
        return self

    def __exit__(self, *exc: object) -> None:
        _CONTEXT.build = self.previous

    def run(self, model: Model) -> Any:
        """A model's body, as the build's root or as a child."""
        import time

        key = str(model.script) + "::" + model.name
        if key in self.stack:
            raise RecursionError(f"model {model.identity} calls itself")
        from cadgen.engine.kernel import memo

        self.stack.append(key)
        started = time.perf_counter()
        try:
            with memo.scope(key):
                # One coarse entry above the body's calls: not called when the bytes it is
                # made of are what they were (``memo.body``).
                result = memo.body(key, lambda: self.source(model), model.function)
        finally:
            self.stack.pop()
        self.timings[model.identity] = self.timings.get(model.identity, 0.0) + time.perf_counter() - started
        check_result(model, result)
        return result

    def root(self, model: Model) -> Any:
        """A model the build was asked for: its body, kept for a later model of the same
        build that calls it as a child."""
        result = self.run(model)
        self.results.setdefault(str(model.script) + "::" + model.name, (result, instance(result)))
        return result

    def child(self, model: Model) -> Any:
        key = str(model.script) + "::" + model.name
        self.called.setdefault(key, model)
        found = self.results.get(key)
        if found is not None:
            from cadgen.engine.kernel import memo

            memo.used(key)  # the calling body's replay needs this one's run
            made = instance(found[1])
        else:
            _say("entering", model.name)
            made = self.run(model)
            _say("leaving", model.name)
            self.results[key] = (made, instance(made))
        if not made.__dict__.get("label"):
            made.label = model.name
        from cadgen.engine.api import Document

        # The child's document, whose shape is this process's result: the caller composes ``.shape``.
        return Document.inside(model, made)

    def children(self, model: Model, run: Any, before: set[str]) -> list[tuple[Model, Any]]:
        """The models that ran as children in ``model``'s run, each once, in the order they
        first ran, each with a new placement of its result as its body returned it: those
        its body called (``child``), and those a replay ran without a call -- the bodies
        ``run`` ran or replayed that it had not before (``before``), the models among them
        known by identity (``_MODELS``)."""
        key = str(model.script) + "::" + model.name
        names = list(self.called) + [name for name in run.statuses if name not in before and name not in self.called]
        found = []
        for name in names:
            child = self.called.get(name) or _MODELS.get(name)
            if name == key or child is None:
                continue  # the target itself, or a @memo call
            held = self.results.get(name)
            made = instance(held[1]) if held is not None else run.placement(name)
            if made is not None:
                found.append((child, made))
        return found

    def memo(self, marked: Memo, args: tuple, kwargs: dict) -> Any:
        """A ``@memo`` call: a body named by the function and its arguments' digest, run or
        replayed (``memo.body``); the same call again in this build a new placement of its
        result. Arguments the memo cannot key, or a result that is no geometry, run it on
        every call, and the report's fallbacks say why."""
        import time

        from cadgen.engine.kernel import memo as kernel

        family = str(marked.script) + "::" + marked.name
        try:
            digest, inputs = kernel.call_key(args, kwargs)
        except kernel.Unkeyable as error:
            self._fallback(marked, f"runs on every call: {error}")
            return marked.function(*args, **kwargs)
        name = f"{family}({digest})" if args or kwargs else family
        found = self.results.get(name)
        if found is not None:
            kernel.used(name)  # the calling body's replay needs this one's run
            return _placement(found[1])
        if name in self.stack:
            raise RecursionError(f"{marked.identity} calls itself with the same arguments")
        self.stack.append(name)
        started = time.perf_counter()
        _say("entering", marked.name)
        try:
            with kernel.scope(name):
                result = kernel.body(name, lambda: self.source(marked), lambda: marked.function(*args, **kwargs),
                                     inputs=inputs, family=family)
        finally:
            self.stack.pop()
        _say("leaving", marked.name)
        self.timings[marked.identity] = self.timings.get(marked.identity, 0.0) + time.perf_counter() - started
        if not kernel.geometric(result):
            kernel.direct(name)
            self._fallback(marked, f"runs on every call: it returned {type(result).__name__}, not geometry "
                                   "(a shape, or a tuple, list or dict of shapes)")
            return result
        # Shapes it made past the engine (OCCT's own makers) are keyed by the call itself, so
        # what this caller makes of them is kept too.
        result = kernel.adopt(name, result)
        self.results[name] = (result, _placement(result))
        return result

    def _fallback(self, marked: Memo, reason: str) -> None:
        reasons = self.fallbacks.setdefault(marked.identity, [])
        if reason not in reasons:
            reasons.append(reason)
        self.timings.setdefault(marked.identity, 0.0)


def _say(stage: str, name: str) -> None:
    """A body inside the model's begins or ends (``progress.Progress.entering``, ``leaving``):
    said to this process's build, by its function's name; nothing outside a build, and never a
    failure. A body that raises says no end: the build's last frame is where it failed."""
    from cadgen.engine import progress

    said = progress.current()
    if said is None:
        return
    try:
        getattr(said, stage)(name)
    except Exception:  # noqa: BLE001 - saying where a build is never fails it
        pass


def _placement(value: Any) -> Any:
    """A new placement of a ``@memo`` result: ``instance`` of each shape it holds."""
    if isinstance(value, (list, tuple)):
        return type(value)(_placement(item) for item in value)
    if isinstance(value, dict):
        return {name: _placement(item) for name, item in value.items()}
    return instance(value)


def check_result(model: Model, result: Any) -> None:
    import build123d as bd

    if not isinstance(result, bd.Shape):
        raise TypeError(f"model {model.identity} returned {type(result).__name__}; a model returns a build123d shape")
    if result.__dict__.get("_wrapped") is None:
        raise ValueError(f"model {model.identity} returned an empty shape")


# Keep the public decorator and the implementation module one identity, even
# after an explicit import of cadgen.engine.model (as with engine.materials).
import sys as _sys
from types import ModuleType as _ModuleType


class _ModelModule(_ModuleType):
    def __call__(self, function: Any = None, /, **options: Any) -> Any:
        return model(function, **options)


_sys.modules[__name__].__class__ = _ModelModule
