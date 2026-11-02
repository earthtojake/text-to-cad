"""cad: CAD models as Python, built by its engine (``cad.engine``) into documents (``.xbf``)
and the files they declare.

The root exports exactly the engine's surface -- ``model``, the decorators (``xbf``, ``step``,
``glb``, ``stl``, ``threemf``, ``dxf``), ``memo``, face painting (``paint``), the readers (``read_step``, ``read_xbf``, ``read_mesh``) -- its operations on
documents as functions (``export``, ``snapshot``, ``inspect``) and ``__version__``; process
control (``cad serve``, ``status``, ``stop``, ``server``) is the ``cad`` command's alone. Two
namespaces hold the standards' names: ``cad.ap242`` the mechanism's (``mechanism_state``,
``configuration_sequence``, ``gear_pair``, ``rack_and_pinion_pair``, ``screw_pair``, ``posed``) and
``cad.gltf`` a GLB's own ``animation``. Every name loads on first use: ``import cad``
imports no CAD kernel, and ``import build123d`` binds a module the kernel loads into on its
first attribute (``_internal/lazy_kernel.py``).
"""

from functools import cache as _cache
from typing import TYPE_CHECKING as _TYPE_CHECKING

# Before anything imports build123d, which every entry point of the library eventually does:
# build123d parses EVERY font in the system font folders at import time, with no
# per-file guard, so one malformed file aborts the import and every cad command
# with it (issue #322, upstream in build123d's register_folder), as does a font with
# no family name, whose empty name OCCT refuses (#636). This hides the fonts build123d
# cannot register from that one listing.
#
# It belongs here rather than in a launcher because the `cad` command, the engine's
# warm workers and `python -m cad.X` children all reach the library by different routes, and a
# fix that covered only one of them would leave the builds it spawns still broken.
#
# Cost where nothing is wrong: one str.endswith per glob call. CAD_FONT_GUARD=0
# opts out.
from cad._internal.font_scan import install_font_guard as _install_font_guard
from cad._internal.lazy_kernel import install as _install_lazy_kernel

# ``import build123d as bd`` binds a module the kernel loads into on its first attribute
# (``_internal/lazy_kernel.py``). The wheel's cad-lazy-kernel.pth installs it at interpreter
# start; this covers an editable install, where that file is not placed. Idempotent.
_install_lazy_kernel()
del _install_lazy_kernel

_install_font_guard()
del _install_font_guard

# The library installs nothing of the server's: what the engine's verbs did is told to the functions in
# cad.engine.api.observers, which the server's commands fill (``cad_server._internal.engine_telemetry``),
# and a process the server did not start -- a model's own, in the CAD kernel environment -- counts nothing.

# The engine's surface (``cad.engine.__all__``) and its operations on documents as functions
# (``cad.engine.api``).
_ENGINE = ("model", "xbf", "memo", "step", "glb", "stl", "threemf", "dxf", "paint",
           "read_step", "read_xbf", "read_mesh")
_VERBS = ("export", "snapshot", "inspect")

__all__ = [
    "__version__",
    *_ENGINE,
    *_VERBS,
]


def __getattr__(name: str):
    if name in _ENGINE:
        import cad.engine as _engine

        return getattr(_engine, name)
    if name in _VERBS:
        from cad.engine import api

        return getattr(api, name)
    if name == "__version__":
        return _resolve_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far: what ``dir()`` and
    completion offer, without loading any of them, nor the kernel."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if _TYPE_CHECKING:
    # Mirrors the lazy __getattr__ above so type checkers and editors see the root exports
    # without importing OCP. Every name here must have a branch there, and comes from the
    # module that defines it.
    from cad.engine.api import export, inspect, snapshot
    from cad.engine.model import (dxf, glb, memo, model, paint, read_step, read_xbf, step, stl, threemf, xbf)
    from cad.engine.reader import read_mesh


@_cache
def _resolve_version() -> str:
    """The version declared beside this very package (``_internal.version.declared_version``):
    the source tree's pyproject for a checkout, the dist-info beside it for an install.
    Never the first ``cad`` metadata on ``sys.path``, which can be another install's.
    Resolved once per process: the code that answers cannot change under a running one."""
    import pathlib

    from cad._internal.version import declared_version

    return declared_version(pathlib.Path(__file__).resolve().parent)
