"""``import build123d`` binds the module; the kernel loads on its first attribute.

A model script's module body should cost nothing until the engine has decided whether to build
-- in the process that only hands the build to the warm worker, it never loads the kernel at
all -- yet the idiom every build123d author writes is ``import build123d as bd`` at the top.
This ``sys.meta_path`` finder makes that idiom free: for the top-level names ``build123d`` and
``OCP`` alone it returns the ordinary spec (``PathFinder``'s) with its loader wrapped in
``importlib.util.LazyLoader``, so the import binds a module whose body runs on the first
attribute anything reads from it (``bd.Box``), in whichever process that is.

``from build123d import Box`` reads an attribute to bind ``Box``, so it loads the kernel there and
then, as without the finder; ``import OCP.Standard`` loads ``OCP`` to find its submodule, and the
submodule as ever. Only the top-level packages are lazy: a submodule is imported when asked.

Every later ``import build123d`` -- a project's helper module importing it as the script did --
binds the same module and loads nothing. The import system reads a module's ``__spec__`` on each
import that finds it in ``sys.modules`` (to wait on one still initializing), and the standard
library's lazy module loads on any attribute, so the module is a ``KernelModule``, which answers
``__spec__`` as it stands and hands every other first read to the standard library's load.

Installed twice, harmlessly (``install`` is idempotent): by ``cadgen-lazy-kernel.pth`` in the
site-packages of an environment cadgen is installed into, before any import, and by cadgen's
package ``__init__`` for an editable install, where a wheel's ``.pth`` is not placed. Importing
this module imports no kernel.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import types
from importlib.machinery import PathFinder
from typing import Any

KERNEL = ("build123d", "OCP")


_SWAP = threading.Lock()


class KernelModule(types.ModuleType):
    """A lazy kernel module: ``__spec__`` read as it stands, every other attribute the first
    read of the standard library's lazy module, which loads it."""

    def __getattribute__(self, attr: str) -> Any:
        if attr == "__spec__":
            return object.__getattribute__(self, attr)
        with _SWAP:
            if type(self) is KernelModule:  # by type(): reading ``__class__`` would come back here
                self.__class__ = importlib.util._LazyModule  # noqa: SLF001
        try:
            return getattr(self, attr)
        except AttributeError as error:
            # A name the module lacks is the asker's mistake, raised from here as Python raises it,
            # never as a failure of this frame's own (``analytics.signature``).
            raise error.with_traceback(None) from None

    def __delattr__(self, attr: str) -> None:
        self.__getattribute__(attr)
        delattr(self, attr)


class KernelLoader(importlib.util.LazyLoader):
    """``LazyLoader``, its module a ``KernelModule``."""

    def exec_module(self, module: types.ModuleType) -> None:
        super().exec_module(module)
        module.__class__ = KernelModule


class LazyKernelFinder:
    """Finds ``build123d`` and ``OCP`` as ``PathFinder`` does, their loaders made lazy."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname not in KERNEL:
            return None
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return None  # nothing to defer: the next finder imports it as ever
        spec.loader = KernelLoader(spec.loader)
        return spec


def install() -> None:
    """Put the finder first on ``sys.meta_path``, once."""
    if not any(isinstance(finder, LazyKernelFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, LazyKernelFinder())


def loaded(name: str) -> bool:
    """Whether ``name`` is imported and its body has run: a lazy module bound by ``import`` and
    never read from is not loaded."""
    module = sys.modules.get(name)
    # By its exact type: an isinstance check that misses reads ``__class__``, which loads it.
    return module is not None and type(module) not in (KernelModule, importlib.util._LazyModule)  # noqa: SLF001


install()
