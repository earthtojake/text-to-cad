"""The library's earlier spellings, each an alias of the object it names now.

An alias is the SAME object as its new path (``cad.read_step is cad.step.read``), looked up through
this table alone. Each warns with ``CadDeprecationWarning`` once per name per process, from the lookup,
naming the new path: ``cad.read_step is deprecated; use cad.step.read``. A module alias
(``cad.ap242``) is the module it names now, imported under its old name too. Aliases are kept out of
every ``__all__`` and every document but this table and the migration guide; a test pins the table.

A build's stderr is the model's log, and a model's own process imports its script first, so the
warning reaches the person or the agent who ran it: in their terminal, before the worker's build.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import os
import sys
from pkgutil import resolve_name as _resolve
import warnings
from typing import Any

__all__ = ["CadDeprecationWarning", "MODULE_ALIASES", "NAME_ALIASES", "lookup", "warn"]


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
        # A model's export, its handle's or its id's: a file's is its own type's (cad.step.export, ...).
        "export": "cad.model.export",
        "snapshot": "cad.engine.api.snapshot",
        "inspect": "cad.engine.api.inspect",
    },
    # The 0.10 call shapes, each a CheckResult or a CheckFinding.
    "cad.results": {"ValidationResult": "cad.results._ValidationResult", "ValidationIssue": "cad.results._ValidationIssue"},
}

#: What the deprecation says to use instead, where the new path is not one object: the root's
#: operations are each document type's now.
_ADVICE = {
    "cad.export": "cad.model.export (a file's: cad.<document_type>.export, cad.step.export, ...)",
    "cad.snapshot": "cad.<document_type>.snapshot (cad.model.snapshot, cad.stl.snapshot, ...)",
    "cad.inspect": "cad.<document_type>.inspect (cad.model.inspect, cad.step.inspect, ...)",
    "cad.results.ValidationResult": "cad.results.CheckResult (findings=, each with location=)",
    "cad.results.ValidationIssue": "cad.results.CheckFinding (severity, code, message, location=, hint=)",
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
    "cad.sdf_source": "cad.sdf._source",
    "cad.sdf_validation": "cad.sdf._validation",
    "cad.sdf_external": "cad.sdf._external",
    "cad.srdf_source": "cad.srdf._source",
    "cad.srdf_validation": "cad.srdf._validation",
}

_WARNED: set[str] = set()
# A module alias's module's own spec, kept while the import system stamps the alias's on it.
_OWN_SPECS: dict[str, Any] = {}


# The frames a warning never points at: the library's own and the import system's, so it names the
# line of the program that spelled the old name.
_SKIPPED = (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "<frozen importlib")


def warn(old: str, new: str) -> None:
    """Say once per process that ``old`` is deprecated, naming ``new``, at the caller's line."""
    if old in _WARNED:
        return
    _WARNED.add(old)
    warnings.warn(f"{old} is deprecated; use {_ADVICE.get(old, new)}", CadDeprecationWarning,
                  skip_file_prefixes=_SKIPPED)


def lookup(owner: str, name: str) -> Any:
    """The object an old ``owner.name`` is an alias of, after its warning; ``AttributeError`` for a name
    that is no alias."""
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
