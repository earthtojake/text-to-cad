"""``cadgen``: the library's earlier name, kept so a model written for it runs as it is.

Every name of ``cadgen`` is the library's own (``cad``), and every module ``cadgen.<x>`` is the module
``cad.<x>`` itself -- the same object, never a second copy -- so ``from cadgen import model``, ``from
cadgen.geometry import overlap_volume`` and ``from cadgen.gltf import animation`` resolve to what the
``cad`` spellings do, and ``cadgen.ap242 is cad.ap242``. Nothing is said of it. Only the library has
this name: the server and the stdio transport have none.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from typing import Any

import cad as _cad


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
        return importlib.import_module("cad" + spec.name[len(__name__):])

    def exec_module(self, module: Any) -> None:
        pass  # run once already, as ``cad.<x>``


if not any(isinstance(finder, _Alias) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Alias())


def __getattr__(name: str) -> Any:
    return getattr(_cad, name)


def __dir__() -> list[str]:
    return dir(_cad)
