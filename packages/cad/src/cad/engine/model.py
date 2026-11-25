"""Models: the decorators, a model's identity, and what calling one does.

A model is a parameterless function that returns a build123d shape. Its declarations, alone or combined,
each write a file: ``@model`` the model's ``.xbf``, its document, and the file decorators ``@step``, ``@glb``,
``@stl``, ``@threemf`` and ``@dxf`` (the drawing of a planar result: a sketch, a face, wires or edges) their own
file each and nothing else; the same kind twice is refused. A function with file decorators alone writes no
``.xbf``, so it is no model document, and is built from nothing after the engine restarts (its build says so:
``build._unsaved``). ``@xbf`` is an earlier spelling of ``@model``, an alias of it (``cad._internal.aliases``). A
model's document is its ``.xbf``, and its id is that file's (``Model.id``, ``ids.file_id``): ``name=`` names the
model, and so its files where no path is given. A path is optional on every one, positional or ``out=``
(``@model("XBF/part.xbf")``, ``@step(out="part.step")``), relative to the script; omitted (``@step``, ``@step()``,
``@glb(tolerance=0.1)``), it is the model's name and the kind's suffix beside the script (``Model.plan``). Each
decorator is a function of the same arguments too, given a shape first: ``model(shape, "crate.xbf", name=...)``
hands it over as a model (``api.hand_over``), ``step(shape, "crate.step")`` writes that file of it alone
(``api.write_shape``). Everything else is the model's code: its material,
colours, joints, the pose its joints are connected at (the pose every file shows), its mechanism
states, couplings and configuration sequences (``mechanism_state``, ``gear_pair`` and its siblings,
``configuration_sequence``). A picture is the ``snapshot`` verb's, never a declaration. The outputs
are kept in the order the decorators are written, top to bottom, and an xbf is always written first.

The decorated function is a ``Model``: the function, its id (``.id``: ``ids.file_id`` of its ``.xbf``,
``Model.xbf``, else of its first file) and the debug seam
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

``model(shape, name=...)`` hands a shape over: no function, no body to run again (``api.hand_over``); it writes
its ``.xbf`` at the path given second (``model(shape, "crate.xbf", name=...)``), else ``<name>.xbf``, a relative path
resolved as every path is: against the calling script's folder, or the working folder where there is no script.
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

from cad.engine.ids import canonical, check_name, file_id

__all__ = ["KINDS", "Memo", "Model", "Output", "Target", "configuration_sequence", "dxf", "glb", "mechanism_state", "memo",
           "model", "paint", "read_step", "read_xbf", "step", "stl", "threemf", "models_in"]

# The suffix each output kind writes, and the default file name's.
SUFFIXES = {"xbf": ".xbf", "step": ".step", "glb": ".glb", "stl": ".stl", "threemf": ".3mf", "dxf": ".dxf"}
_ACCEPTED = {"xbf": (".xbf",), "step": (".step", ".stp"), "glb": (".glb",), "stl": (".stl",), "threemf": (".3mf",),
             "dxf": (".dxf",)}
KINDS = tuple(SUFFIXES)

_CONTEXT = threading.local()
# Every model defined since a build began, by its identity (``script::function``): a body
# a replay ran is known by its name alone, and this says which of them are models
# (``BuildContext.children``). A build forgets them before it loads the script.
_MODELS: dict[str, "Model"] = {}


@dataclass(frozen=True)
class Output:
    """One file a model declares: its kind and path (None: its default, ``Model.plan``), and a GLB's,
    an STL's or a 3MF's own mesh tolerance in mm and angle in degrees (None: the engine's)."""

    kind: str
    out: str | None
    tolerance: float | None = None
    angle: float | None = None


@dataclass(frozen=True)
class Target:
    """One file a build writes: its kind, its path and its mesh tolerance and angle (``Output``'s)."""

    kind: str
    path: Path
    tolerance: float | None = None
    angle: float | None = None


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
        # The name ``name=`` gives it, which its files take where no path is given; None: its function's.
        self.explicit_name: str | None = None
        self.__xbf_model__ = True
        _MODELS[f"{self.script}::{self.name}"] = self

    @property
    def xbf(self) -> Path | None:
        """The ``.xbf`` ``@model`` writes, its document: at its path, else ``<name>.xbf`` beside the script; None
        for a function with file decorators alone."""
        return next((target.path for target in self.plan() if target.kind == "xbf"), None)

    @property
    def id(self) -> str:
        """Its document's id: its ``.xbf``'s (``ids.file_id``), worked out without asking the engine; of a function
        with file decorators alone, its first file's."""
        xbf = self.xbf
        return file_id(xbf if xbf is not None else self.plan()[0].path)

    @property
    def fingerprint(self) -> str | None:
        """SHA-256 of its script's bytes (``identity.fingerprint``), read once a build per script
        (``_FINGERPRINTS``) and only when a report or a re-attachment asks: never at declaration."""
        script = str(self.script)
        if script not in _FINGERPRINTS:
            from cad.engine.identity import fingerprint

            _FINGERPRINTS[script] = fingerprint(self.script)
        return _FINGERPRINTS[script]

    @property
    def source(self) -> dict[str, Any]:
        """What a build's report says of this model's declaration: its script and function, its
        first line, its explicit name, its script's fingerprint, its module and its ``.xbf`` (None without one)."""
        xbf = self.xbf
        return {"script": str(self.script), "name": self.name,
                "line": self.function.__code__.co_firstlineno, "explicit_name": self.explicit_name,
                "fingerprint": self.fingerprint, "module": self.function.__module__,
                "xbf": str(xbf) if xbf is not None else None}

    def declare(self, output: Output) -> "Model":
        """One file more on this function, its declaration's (``_declare``, bare ``@model``): declarations
        stack, each adding its file, and one of a kind the function declares already is refused, as
        nothing would say which of the two is the model's."""
        if any(found.kind == output.kind for found in self.outputs):
            what = "its .xbf" if output.kind == "xbf" else f"@{output.kind}"
            raise TypeError(f"model {self.name!r} declares {what} twice: keep one {_said(output.kind)}")
        self.outputs.insert(0, output)
        return self

    def named(self, name: str | None) -> "Model":
        """The ``name=`` a declaration gives: this model's name, which its files take where no path is given."""
        if name is None:
            return self
        check_name(name)
        if self.explicit_name is not None and self.explicit_name != name:
            raise TypeError(f"model {self.name!r} declares two names, {self.explicit_name!r} and {name!r}")
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
        from cad.engine import api
        from cad.engine.said import log, reported

        # Decoration only declares. The caller's control flow reaches this build,
        # and resumes after it; importing the engine never runs or exits a script.
        # A call the program's own code makes (``python caller.py``) is reported, wherever the
        # model is defined: ``caller.py`` calling ``parts.cube()`` prints cube's id and view.
        caller = sys._getframe(1)
        program = caller.f_globals.get("__name__") == "__main__"
        previous = getattr(_CONTEXT, "program", False)
        _CONTEXT.program = program
        try:
            built = self.build(log=log if program else None)
        except (ConnectionError, api.EngineError) as error:
            # The engine not reached, or refusing the call before any build (``api._ask``): one line,
            # said only if nothing catches it (``_told``).
            _told(error, f"cad: {error}")
            raise
        finally:
            _CONTEXT.program = previous
        if program:
            reported(built.models, built.wall, built.fresh, False)
        # Once a run, after its report: the server is another release than this library, under one contract.
        api.say_notice()
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
            out = (self.explicit_name or self.name) + SUFFIXES[kind]
        path = Path(out)
        if not path.is_absolute():
            path = self.script.parent / path
        return Path(_normalized(path))

    def targets(self) -> list[tuple[str, Path]]:
        """Each file a build writes as ``(kind, path)``, the xbf first, then the derived files
        in the order the decorators are written (``plan``)."""
        return [(target.kind, target.path) for target in self.plan()]

    def files(self) -> list[Output]:
        """What this model writes: the files its decorators declare, each its own -- ``@model`` its ``.xbf``, a file
        decorator its file (law 10). The xbf first."""
        return sorted(self.outputs, key=lambda output: output.kind != "xbf")

    def plan(self) -> list[Target]:
        """The files a build of this model writes (``files``): its ``.xbf`` where ``@model`` declares one, then the
        derived files in the order the decorators are written. A relative path is relative to the script's folder, and a file with
        none is the model's name (``name=``, else its function's) and the kind's suffix beside the script:
        ``arm.xbf``, ``arm.step``."""
        return [Target(output.kind, self._path(output.kind, output.out), output.tolerance, output.angle)
                for output in self.files()]

    # --- the verbs, through the daemon (``cad.engine.api``) -----------------------------

    def build(self, *, verify: bool = False, profile: bool = False, log: Callable[[str], None] | None = None, daemon: bool = True) -> Any:
        """Build this model, through the daemon (``daemon=False``: in this process): it and every
        child model it calls write what their decorators declare, when the script explicitly calls it (``api.build_script``); a ``Report``. ``verify`` runs every body
        the memo would replay and compares its result with the logged one. ``profile`` measures
        the actual build call without forcing cache misses (engine README, Profiling)."""
        from cad.engine import api

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
    """The module search path a script's imports resolve on: its folder, so a module beside it imports
    by its own name, then its package's root (``module_of``), as ``python -m`` has it, so the package
    imports by its name -- both LAST, after everything installed, where ``python script.py`` puts the
    folder first: a project's module bearing the library's name (a ``cad.py`` beside a model) never
    stands in for the library. Each is moved there if the path holds it already."""
    import sys

    for folder in [str(Path(script).resolve().parent)] + ([str(root)] if root is not None else []):
        while folder in sys.path:
            sys.path.remove(folder)
        sys.path.append(folder)


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


# Each script's fingerprint (``Model.fingerprint``), read once a build.
_FINGERPRINTS: dict[str, str | None] = {}


def _no_animations(animations: Any) -> None:
    if animations is not None:
        raise TypeError("a model decorator takes no animations=: a model's body declares its animations "
                        "(animation(...)); animations= goes with a shape handed over, model(shape, name=...)")


def _given(target: Any, file: Any, out: Any) -> tuple[Any, Any, Any]:
    """What a declaration's call is given (``model``, a file decorator): the function it decorates or None, the path
    of its file -- a path given first, else the one given second, else ``out=`` -- and the shape it writes or None."""
    if isinstance(target, Model) or inspect.isfunction(target):
        return target, file if file is not None else out, None
    if target is None or isinstance(target, (str, os.PathLike)):
        return None, target if target is not None else file if file is not None else out, None
    return None, file if file is not None else out, target


def _program() -> Any:
    """The frame of the program's line that called a declaration with a shape: past this module and ``cad.<type>``'s
    own call of it (``cad._internal.document_type``)."""
    caller = sys._getframe(2)
    while caller.f_back is not None and (caller.f_code.co_filename == __file__
                                         or caller.f_globals.get("__name__") == "cad._internal.document_type"):
        caller = caller.f_back
    return caller


def model(target: Any = None, file: Any = None, /, *, out: Any = None, name: str | None = None,
          animations: Any = None) -> Any:
    """Write to disk as a model. On a function: declare a model, optionally named (``name=``), and the ``.xbf`` each
    run saves it as -- at its path, relative to the script (``@model("XBF/arm.xbf")``, or ``out=``, as every file
    decorator takes it), else ``<name>.xbf`` beside the script (bare ``@model``). Given a shape first: hand it over as
    a named model (``model(shape, name=...)``, and ``model(shape, "crate.xbf", name=...)`` for a path:
    ``api.hand_over``). A path given first is the path; else the one given second; else ``out=``."""
    function, path, shape = _given(target, file, out)
    if shape is None:
        _no_animations(animations)
        if function is not None:
            return _declare("xbf", path, name)(function)  # bare ``@model``: the function itself
        return _declare("xbf", path, name)
    check_output("xbf", path, "model(shape, '….xbf', name=...)")
    from cad.engine import api

    return api.hand_over(shape, name, animations=animations, frame=_program(), out=path)


def _said(kind: str) -> str:
    """A file declaration as a script spells it: a model's own ``.xbf`` is ``@model``'s, every other file its
    decorator's."""
    return "@model" if kind == "xbf" else f"@{kind}"


def _declare(kind: str, out: Any, name: str | None, tolerance: float | None = None, angle: float | None = None) -> Any:
    """One file a model declares, of ``kind`` at ``out`` (None: its default, ``Model.plan``): the decorator a
    file declaration is -- ``@step(out)``, and ``@model(out)`` for the ``.xbf`` -- which records the output on the function's ``Model`` (``Model.plan`` is what a build writes)."""
    from cad.engine.export import angle_of, tolerance_of

    check_output(kind, out, "@model('….xbf')" if kind == "xbf" else f"@{kind}(out=...)")
    if name is not None:
        check_name(name)
    given = [] if out is None else [out]
    tolerance, angle = tolerance_of(tolerance, given), angle_of(angle, given)

    def apply(target: Any) -> Model:
        model = target if isinstance(target, Model) else Model(target)
        model.declare(Output(kind, None if out is None else os.fspath(out), tolerance, angle))
        return model.named(name)

    return apply


def _decorator(kind: str) -> Callable[..., Any]:
    from cad.engine.export import TOLERANT

    def declared(target: Any, file: Any, out: Any, name: str | None, *options: Any) -> Any:
        function, path, shape = _given(target, file, out)
        if shape is not None:
            check_output(kind, path, f"{kind}(shape, 'path{SUFFIXES[kind]}')")
            from cad.engine import api

            return api.write_shape(shape, kind, path, name, _program(), *options)
        if function is not None:
            return _declare(kind, path, name, *options)(function)  # bare (``@step``): its file the default
        return _declare(kind, path, name, *options)

    # A GLB, an STL and a 3MF take their own mesh tolerance and angle (``export/__init__.py``); no other
    # kind is meshed.
    if kind in TOLERANT:
        def decorate(target: Any = None, file: Any = None, /, *, out: Any = None, name: str | None = None,
                     tolerance: float | None = None, angle: float | None = None) -> Any:
            return declared(target, file, out, name, tolerance, angle)
    else:
        def decorate(target: Any = None, file: Any = None, /, *, out: Any = None, name: str | None = None) -> Any:
            return declared(target, file, out, name)

    decorate.__name__ = kind
    decorate.__qualname__ = kind
    decorate.__doc__ = (f"Write a {SUFFIXES[kind]} file. On a function: declare the file it writes and nothing else, "
                        f"@{kind}('path{SUFFIXES[kind]}') or out=, relative to the script; with none (@{kind}, "
                        f"@{kind}()), <name>{SUFFIXES[kind]} beside the script, the model's name= or its function's. "
                        "Decoration builds nothing. Given a shape first, write that file of it now: "
                        f"{kind}(shape, 'path{SUFFIXES[kind]}'), relative to the calling script's folder."
                        + (" tolerance= and angle= mesh it to within an absolute tolerance in mm and an angle in "
                           "degrees, as cad model export --tolerance and --angle do." if kind in TOLERANT else ""))
    return decorate


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

    from cad.engine.colors import linear
    from cad.engine.kernel.memo import FACE_COLORS, FACE_MATERIALS
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
    from cad.engine import mechanism

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
    from cad.engine import mechanism

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
    from cad.engine.animations import animation as build

    return build(assembly, name, duration=duration)


def _read_step(path: Any) -> Any:
    from cad.engine.document import read_step_shape

    return read_step_shape(path)


_READ_STEP: Callable[[Any], Any] | None = None


def read_step(path: Any) -> Any:
    """A STEP file as a build123d shape: a compound tree of its assembly, every part and
    group labelled, coloured and given its material as the file has them. Parsed once per
    worker and held, in a reader process of the build's (its working memory never the
    worker's): a later build's read of the same bytes is the memo's hit, the same objects."""
    global _READ_STEP
    if _READ_STEP is None:
        from cad.engine.kernel.memo import wrap_function

        _READ_STEP = wrap_function("read_step", _read_step)
    import os

    from cad.engine.reader import refuse_written

    # Before the memo: a read of a file this build writes is refused, whether or not the memo holds it.
    refuse_written(path, "step.read")
    return _READ_STEP(os.fspath(path))


def _read_xbf(path: Any) -> Any:
    from cad.engine.document import read_xbf_shape

    return read_xbf_shape(path)


_READ_XBF: Callable[[Any], Any] | None = None


def read_xbf(path: Any) -> Any:
    """``model.read(path)``: a model saved as a file (``.xbf``) as a build123d shape: a copy of its
    geometry, as ``read_step`` gives a STEP's -- a compound tree of its assembly, every part and group
    named, coloured and given its materials (painted faces too) as the document has them,
    each element named as the document names it. Its mechanism and configurations are not
    imported: a part is a part. Read once per worker and held, keyed by the file's bytes, as
    ``read_step`` is. The fast way to bring a vendor STEP in: convert it once (``cad step
    export vendor.step vendor.xbf``) and read the xbf. Any other file is refused by name, with
    the reader that takes it (``step.read``, ``stl.read``)."""
    global _READ_XBF
    if _READ_XBF is None:
        from cad.engine.kernel.memo import wrap_function

        _READ_XBF = wrap_function("read_xbf", _read_xbf)
    import os

    from cad.engine.reader import refuse_other_file, refuse_written

    refuse_other_file(path, "model.read", ".xbf")  # before the memo too
    refuse_written(path, "model.read")  # before the memo, as read_step's
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

        from cad.engine.kernel.memo import own_joints

        joints = attrs["joints"] = own_joints(joints, made)
        for label, joint in joints.items():
            if isinstance(joint, Joint):
                own = copied[id(joint)] = copy.copy(joint)
                dict.__setitem__(joints, label, own)  # as a dict is: a JointDict's own would move it
                own.parent = made
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
    from cad.engine.sources import digest

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
        # The parameters the script's load declared (``parameters.recording``; ``build`` sets it).
        self.declared: list = []
        # A preview's values (``build.preview``), as text: a body whose key falls back to a module's bytes
        # (which a preview leaves as they are) is keyed by them too, so it never replays another value's run.
        self.preview: str | None = None

    def source(self, model: Model) -> str:
        """What a model's body is made of: the symbols its function reaches, a module's
        bytes where one cannot be followed (``sources.Symbols``), and the engine's own
        code; worked out once a build."""
        key = str(model.script) + "::" + model.name
        found = self.sources.get(key)
        if found is None:
            import time

            from cad.engine.sources import Symbols

            started = time.perf_counter()
            if self.symbols is None:
                self.symbols = Symbols(self.resolved, self.loaded, self.base)
            digest, reasons = self.symbols.key(model.function)
            if reasons:
                self.fallbacks[model.identity] = reasons
            found = self.sources[key] = digest + _engine_version() + (
                f"|preview {self.preview}" if reasons and self.preview is not None else "")
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

            from cad.engine.sources import Symbols, closure_files

            module = getattr(model.function, "__module__", None) or model.script.stem
            own = set(closure_files(model.script, module, self.resolved))

            def imported(name: str) -> bool:
                file = getattr(sys.modules.get(name), "__file__", None)
                return bool(file) and Path(file).resolve() in own

            loaded = {name for name in self.loaded or () if imported(name)}
            symbols = self.others[model.script] = Symbols(self.resolved, loaded, model.script.parent)
        return symbols.modules(model.function)

    def parameters(self, model: Model) -> list[dict[str, Any]]:
        """A model's parameters (``parameters.rows``): those its script's load declared, each with where
        it is in the code and whether it can be written -- its own file's alone. A child model of another
        script lists what a build of that script would: the declarations of the files its own script
        imports (``sources.closure_files``), so its document is the one a build of its own writes."""
        from cad.engine import parameters

        if not self.declared:
            return []
        files = None
        if self.script is not None and model.script != self.script:
            from cad.engine.sources import closure_files

            module = getattr(model.function, "__module__", None) or model.script.stem
            files = {canonical(path) for path in closure_files(model.script, module, self.resolved)}
        return parameters.rows(self.declared, str(model.script), files)

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
        from cad.engine.kernel import memo

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
            from cad.engine.kernel import memo

            memo.used(key)  # the calling body's replay needs this one's run
            made = instance(found[1])
        else:
            _say("entering", model.name)
            made = self.run(model)
            _say("leaving", model.name)
            self.results[key] = (made, instance(made))
        if not made.__dict__.get("label"):
            made.label = model.name
        from cad.engine.api import Document

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

        from cad.engine.kernel import memo as kernel

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
    from cad.engine import progress

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
    """A body's result, refused unless one producer (``cad.registry``) makes its document and every file
    the model declares of it: today a model returns a build123d shape, the build123d integration's."""
    from cad.registry import producer_for

    for kind in dict.fromkeys(("model", *(output.kind for output in model.outputs))):
        producer_for(kind, result, where=f"model {model.identity}")
    if result.__dict__.get("_wrapped") is None:
        raise ValueError(f"model {model.identity} returned an empty shape")


# Keep the public decorator and the implementation module one identity, even
# after an explicit import of cad.engine.model (as with engine.materials).
import sys as _sys
from types import ModuleType as _ModuleType


class _ModelModule(_ModuleType):
    def __call__(self, *args: Any, **options: Any) -> Any:
        return model(*args, **options)  # ``model``'s own signature, and its own words for a call it refuses

    def __getattr__(self, name: str) -> Any:
        # An earlier spelling (``xbf``, the model's own declaration: ``model``), after its warning.
        if name.startswith("__"):
            raise AttributeError(name)
        from cad._internal.aliases import lookup

        return lookup(self.__name__, name)


_sys.modules[__name__].__class__ = _ModelModule
