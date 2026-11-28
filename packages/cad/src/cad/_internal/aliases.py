"""The library's earlier spellings, each an alias of the object it names now.

An alias is the SAME object as its new path (``cad.read_step is cad.step.read``), looked up through
this table alone. Each warns with ``CadDeprecationWarning`` once per name per process, from the lookup,
naming the new path: ``cad.read_step is deprecated; use cad.step.read``. A module alias
(``cad.ap242``) is the module it names now, imported under its old name too. Aliases are kept out of
every ``__all__`` and every document but this table and the migration guide; a test pins the table.
``cadgen``, the library's earlier import name, is no entry of the table: its own module says so through
``warn`` when it is imported (``cadgen/__init__.py``).

The document types' operations (``cad.xbf.export``, ``cad.step.dfm``, ``cad.kicad_pcb.drc``, ...) and the
callable forms of the file types (``xbf(shape, "part.xbf")``, ``step(shape, "part.step")``) are aliases too:
each answers as the verb that does it now (``cad.export``, ``cad.dfm``, ``cad.kicad.drc``; ``OPERATION_VERBS``),
built where its type is (``cad._internal.verbs``, ``cad._internal.document_type``), and says so once per name per
process through ``spelled``, where ``SPELLINGS_WARN``, the one switch, is on and a program called it -- never the
library, the server or the transport calling one of its own. So does a function an integration had whose work a
verb does now (``VERB_ALIASES``: ``cad.build123d.dfm(shape)`` is ``cad.dfm(shape)``), built here: it runs what it
ran, as it ran it.

A build's stderr is the model's log, and a model's own process imports its script first, so the
warning reaches the person or the agent who ran it: in their terminal, before the worker's build. That
process owns the line: the worker that builds the program's models imports the same script again
(``cad.engine.build``) with these warnings ignored, each still counting as said, so a run says each
alias once; an alias only a model's body spells, which runs in the worker alone, the worker says. A file
under the working folder is named relative to it, as the person wrote it (``arm.py:2``), in either process.
"""

from __future__ import annotations

import functools
import importlib
import importlib.abc
import importlib.util
import os
import sys
from pkgutil import resolve_name as _resolve
import warnings
from typing import Any

__all__ = ["ASSIGNED", "CadDeprecationWarning", "MODULE_ALIASES", "NAME_ALIASES", "OPERATION_VERBS", "SPELLINGS_WARN",
           "VERB_ALIASES", "current", "lookup", "spelled", "warn"]


class CadDeprecationWarning(FutureWarning):
    """A spelling the library still answers, under the name it has now. A ``FutureWarning``, so Python
    shows it by default: the people who read it are a model's authors, not a library's developers."""


#: ``owner -> {old name: new dotted path}``: a name of a module, answered by the object at the new path.
NAME_ALIASES: dict[str, dict[str, str]] = {
    "cad": {
        "read_step": "cad.step.read",
        "read_xbf": "cad.xbf.read",
        "read_mesh": "cad.stl.read",
        "memo": "cad.build123d.memo",
        "paint": "cad.build123d.paint",
    },
    # The 0.10 call shapes, each a CheckResult or a CheckFinding.
    "cad.results": {"ValidationResult": "cad.results._ValidationResult", "ValidationIssue": "cad.results._ValidationIssue"},
    # build123d's own calls under names of ours (``Plane.to_local_coords``, ``offset``, ``fuse``): a drawing calls them.
    "cad.build123d": {
        "flat_pattern": "cad.build123d._flatten.flat_pattern",
        "planar_faces": "cad.build123d._flatten.planar_faces",
        "flatten_face": "cad.build123d._flatten.flatten_face",
        "flatten_faces": "cad.build123d._flatten.flatten_faces",
        "union_faces": "cad.build123d._flatten.union_faces",
        "offset_profile": "cad.build123d._flatten.offset_profile",
    },
    # MuJoCo's own compile under names of ours: a script compiles with MuJoCo, and ``check`` is the check.
    "cad.mujoco": {"compile_model": "cad.mujoco._compile.compile_model",
                   "compile_findings": "cad.mujoco._compile.compile_findings"},
}

#: What the deprecation says to use instead, where the new path is not one object.
_ADVICE = {
    "cad.results.ValidationResult": "cad.results.CheckResult (findings=, each with location=)",
    "cad.results.ValidationIssue": "cad.results.CheckFinding (severity, code, message, location=, hint=)",
    "cad.flatten": "build123d's own calls: bd.Plane(face).to_local_coords(face) lays a face into XY, bd.offset "
                   "compensates for kerf",
    "cad.build123d.flat_pattern": "build123d's own calls: bd.Plane(face).to_local_coords(face) on the part's "
                                  "face, then bd.offset(profile, amount=kerf)",
    "cad.build123d.planar_faces": "build123d's own selectors: shape.faces().filter_by(bd.GeomType.PLANE), then "
                                  ".filter_by(bd.Axis.Z) and .sort_by(bd.Axis.Z)",
    "cad.build123d.flatten_face": "bd.Plane(face).to_local_coords(face), build123d's own",
    "cad.build123d.flatten_faces": "bd.Plane(face).to_local_coords(face) for each face, build123d's own",
    "cad.build123d.union_faces": "a + b, or a.fuse(b).clean(), build123d's own",
    "cad.build123d.offset_profile": "bd.offset(profile, amount=...), build123d's own",
    "cad.mujoco.compile_model": "mujoco.MjModel.from_xml_path, MuJoCo's own",
    "cad.mujoco.compile_findings": "cad.mujoco.check, whose result holds the compile's findings",
}

#: ``old module -> new module``: a module the library had, answered by the module that holds its names now.
MODULE_ALIASES: dict[str, str] = {
    "cad.ap242": "cad.build123d",
    "cad.gltf": "cad.build123d",
    "cad.geometry": "cad.build123d._geometry",
    "cad.flatten": "cad.build123d._flatten",
    "cad.findings": "cad._internal.findings",
    "cad.xml_common": "cad._internal.xml_common",
    "cad.check_fonts": "cad._internal.check_fonts",
    "cad.urdf_source": "cad.urdf._source",
    "cad.srdf_source": "cad.srdf._source",
    "cad.srdf_validation": "cad.srdf._validation",
    # The word for writing the file a model is saved as, before the file's own type named it: ``cad.xbf``, its
    # decorator (@model is @xbf), its reader (model.read is xbf.read) and its operations (cad.model.export is
    # cad.xbf.export).
    "cad.model": "cad.xbf",
}

#: What an alias keeps of the function it runs (``functools.wraps(done, assigned=ASSIGNED)``): its annotations too,
#: which a command line is made from (``cad_server._internal.cli_from_function``). From Python 3.14
#: ``functools.WRAPPER_ASSIGNMENTS`` copies ``__annotate__`` in their place, which is None for a function whose
#: annotations were set by hand (a check's: ``manufacturing.dfm_for``), and so left the alias none.
ASSIGNED = (*functools.WRAPPER_ASSIGNMENTS, "__annotations__")

#: Whether the document types' operations and the file types' callable forms say they are deprecated (``spelled``):
#: the one switch. Off, each answers as its verb does and says nothing.
SPELLINGS_WARN = True

#: ``operation -> what to use instead``: the verb each document type's operation is an alias of (``cad.xbf.export``
#: is ``cad.export``'s), as its warning names it.
OPERATION_VERBS: dict[str, str] = {
    "export": "cad.export",
    "snapshot": "cad.snapshot",
    "inspect": "cad.inspect",
    "dfm": "cad.dfm",
    "interference": "cad.inspect(source, interference=True)",
    "ranges": "cad.inspect(source, ranges=True)",
    "solve": "cad.fea",
    "validate": "cad.inspect",
    "drc": "cad.kicad.drc",
    "erc": "cad.kicad.erc",
}

#: ``owner -> {old name: (the function it runs, the verb that does it now)}``: a function of an integration's whose
#: work is a verb's now, answered by one that runs what it ran, as it ran it, and says once, where a program calls it,
#: that it is deprecated (``spelled``): a live build123d shape's manufacturing check is ``cad.dfm``'s.
VERB_ALIASES: dict[str, dict[str, tuple[str, str]]] = {
    "cad.build123d": {"dfm": ("cad.build123d._dfm_check.dfm", "cad.dfm")},
}

# The library's, the server's and the transport's own modules: a spelling one of them calls is no program's.
_OWN = ("cad", "cad_server", "cad_mcp")

_WARNED: set[str] = set()
# A module alias's module's own spec, kept while the import system stamps the alias's on it.
_OWN_SPECS: dict[str, Any] = {}
# Each of ``VERB_ALIASES``' functions, made once: one object, every lookup.
_CALLED: dict[str, Any] = {}


# The frames a warning never points at: the library's own and the import system's, so it names the
# line of the program that spelled the old name.
_LIBRARY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ``importlib``'s own (``import_module``, which ``from cad import xbf`` reaches through the root's lookup) as well.
_SKIPPED = (_LIBRARY + os.sep, os.path.join(os.path.dirname(_LIBRARY), "cadgen") + os.sep, "<frozen importlib",
            os.path.dirname(os.path.abspath(importlib.__file__)) + os.sep)


def warn(old: str, new: str) -> None:
    """Say once per process that ``old`` is deprecated, naming ``new``, at the caller's line: the first frame
    outside the library and the import system, its file relative to the working folder when it lies in it.
    The warnings filters still decide (``-W error`` raises it), and one they ignore counts as said."""
    if old in _WARNED:
        return
    _WARNED.add(old)
    message = f"{old} is deprecated; use {_ADVICE.get(old, new)}"
    frame = sys._getframe(1)
    while frame is not None and frame.f_code.co_filename.startswith(_SKIPPED):
        frame = frame.f_back
    if frame is None:
        warnings.warn(message, CadDeprecationWarning, stacklevel=2)
        return
    found = frame.f_globals
    warnings.warn_explicit(message, CadDeprecationWarning, _shown(frame.f_code.co_filename), frame.f_lineno,
                           module=found.get("__name__", "<string>"), registry=found.setdefault("__warningregistry__", {}))


def spelled(old: str, new: str, *, depth: int = 2) -> None:
    """Say that ``old`` -- a document type's operation (``cad.step.dfm``), a file type's callable form
    (``cad.xbf(shape, ...)``) or an integration's function a verb does now (``cad.build123d.dfm``) -- is deprecated,
    naming ``new``, once per process (``warn``), where
    ``SPELLINGS_WARN`` is on and the frame ``depth`` above this one (the alias's caller) is a program's: never
    one of the library's, the server's or the transport's own modules (``_OWN``), which call their own."""
    if not SPELLINGS_WARN or old in _WARNED:
        return
    try:
        caller = sys._getframe(depth)
    except ValueError:
        caller = None
    name = str(caller.f_globals.get("__name__", "")) if caller is not None else ""
    if name.split(".")[0] in _OWN:
        return
    warn(old, new)


def _shown(filename: str) -> str:
    """A file as the person names it: relative to the working folder when it lies inside it, else as given."""
    if not os.path.isabs(filename):
        return filename
    try:
        relative = os.path.relpath(os.path.realpath(filename), os.path.realpath(os.getcwd()))
    except (OSError, ValueError):  # no working folder, another drive (Windows)
        return filename
    return filename if relative.startswith(os.pardir) else relative


def current(dotted: str) -> str:
    """The library's name ``dotted`` (``cad.read_step``, ``cad.ap242.posed``, ``cadgen.memo``) as it is spelled
    now, by this table alone, without importing anything (``cad.step.read``, ``cad.build123d.posed``,
    ``cad.build123d.memo``); a name that is no alias, as it is, ``cadgen`` read as ``cad``. What a static
    scan of a program reads its integrations by (``cad._internal.integrations.for_name``)."""
    parts = dotted.split(".")
    if parts[0] == "cadgen":
        parts[0] = "cad"
    for size in range(len(parts), 1, -1):
        module = MODULE_ALIASES.get(".".join(parts[:size]))
        if module is not None:
            parts = [*module.split("."), *parts[size:]]
            break
    for size in range(len(parts) - 1, 0, -1):
        target = NAME_ALIASES.get(".".join(parts[:size]), {}).get(parts[size])
        if target is not None:
            parts = [*target.split("."), *parts[size + 1:]]
            break
    return ".".join(parts)


def _verb_alias(owner: str, name: str) -> Any:
    """``owner.name`` of ``VERB_ALIASES``: the function it runs, saying once where a program calls it that it is
    deprecated, naming the verb (``spelled``). Made once."""
    old = f"{owner}.{name}"
    found = _CALLED.get(old)
    if found is None:
        target, new = VERB_ALIASES[owner][name]

        @functools.wraps(_resolve(target), assigned=ASSIGNED)
        def alias(*args: Any, **kwargs: Any) -> Any:
            spelled(old, new)
            return _resolve(target)(*args, **kwargs)  # what it ran, as it is now

        alias.__module__ = owner
        found = _CALLED[old] = alias
    return found


def lookup(owner: str, name: str) -> Any:
    """The object an old ``owner.name`` is an alias of, after its warning (a ``VERB_ALIASES`` function's says it as
    it is called); ``AttributeError`` for a name that is no alias."""
    if name in VERB_ALIASES.get(owner, {}):
        return _verb_alias(owner, name)
    target = NAME_ALIASES.get(owner, {}).get(name)
    if target is not None:
        warn(f"{owner}.{name}", target)
        return _resolve(target)
    module = MODULE_ALIASES.get(f"{owner}.{name}")
    if module is not None:
        return importlib.import_module(f"{owner}.{name}")  # the finder below warns and hands it out
    raise AttributeError(f"module {owner!r} has no attribute {name!r}")


class _ModuleAliases(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """``import cad.ap242`` found as the module ``cad.build123d``: imported under its old name, handed
    out as is, after the warning. Run as a program (``python -m cad.check_fonts``), it runs the new one."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname not in MODULE_ALIASES:
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec: Any) -> Any:
        new = MODULE_ALIASES[spec.name]
        warn(spec.name, new)
        module = importlib.import_module(new)
        _OWN_SPECS[spec.name] = module.__spec__
        return module

    def exec_module(self, module: Any) -> None:
        # Run once already, under its own name. The import system stamped the alias's spec on it: put
        # its own back, so the module stays what it was (its name, its reload, its submodules).
        module.__spec__ = _OWN_SPECS.pop(module.__spec__.name, module.__spec__)

    def get_code(self, fullname: str) -> Any:
        new = MODULE_ALIASES[fullname]
        return compile(f"import runpy, sys\nfrom cad._internal.aliases import warn\nwarn({fullname!r}, {new!r})\n"
                       f"runpy.run_module({new!r}, run_name='__main__', alter_sys=True)\n", fullname, "exec")


def install() -> None:
    """Put the module aliases' finder first, once per process."""
    if not any(isinstance(finder, _ModuleAliases) for finder in sys.meta_path):
        sys.meta_path.insert(0, _ModuleAliases())
