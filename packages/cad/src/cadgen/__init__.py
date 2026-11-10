"""``cadgen``: the library's deprecated alias, kept so a model written for it runs as it is.

Every name of ``cadgen`` is the library's own (``cad``), and every module ``cadgen.<x>`` is the module
``cad.<x>`` itself -- the same object, never a second copy -- so ``from cadgen import model``, ``from
cadgen.geometry import overlap_volume`` and ``from cadgen.gltf import animation`` resolve to what the
``cad`` spellings do, and ``cadgen.ap242 is cad.ap242``. Importing it, or any module under it, says once
per process that it is deprecated (``cad._internal.aliases.warn``), at the line that imported it: a
module under it imports this one first. Only the library has this name: the server and the stdio transport have none. A name 0.7 had and 0.8 took out (``build123d``,
``read_scene``, ...) fails as any missing name does; a program ``cad run`` runs then says the guide from 0.7
to 0.8 too (``cad._internal.program``).
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from typing import Any

import cad as _cad
from cad._internal.aliases import warn as _warn

_warn("cadgen", "cad")

# A library module's own spec, kept while the import system stamps the alias's on it.
_OWN_SPECS: dict[str, Any] = {}


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """``cadgen.<x>`` found as the module ``cad.<x>``: imported under its own name, handed out as is."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if not fullname.startswith(__name__ + "."):
            return None
        real = "cad" + fullname[len(__name__):]
        if real not in sys.modules and importlib.util.find_spec(real) is None:
            return None  # no such module: the import fails naming the cadgen spelling, as for any name
        return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec: Any) -> Any:
        module = importlib.import_module("cad" + spec.name[len(__name__):])
        _OWN_SPECS[spec.name] = module.__spec__
        return module

    def exec_module(self, module: Any) -> None:
        # Run once already, as ``cad.<x>``. The import system stamped the alias's spec on it: put its own
        # back, so the module stays what it was (its name, its reload, its submodules).
        module.__spec__ = _OWN_SPECS.pop(module.__spec__.name, module.__spec__)


if not any(isinstance(finder, _Alias) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Alias())


def __getattr__(name: str) -> Any:
    return getattr(_cad, name)


def __dir__() -> list[str]:
    return dir(_cad)
