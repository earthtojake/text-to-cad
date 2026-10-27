"""cadgen: CAD models as Python, built by its engine (``cadgen.engine``) into documents (``.xbf``)
and the files they declare.

The root exports exactly the engine's surface -- ``model``, the decorators (``xbf``, ``step``,
``glb``, ``stl``, ``threemf``, ``dxf``), ``memo``, face painting (``paint``), the readers (``read_step``, ``read_xbf``, ``read_mesh``) -- its operations on
documents as functions (``export``, ``snapshot``, ``inspect``) and ``__version__``; process
control (``cadgen serve``, ``status``, ``stop``, ``server``) is the ``cadgen`` command's alone. Two
namespaces hold the standards' names: ``cadgen.ap242`` the mechanism's (``mechanism_state``,
``configuration_sequence``, ``gear_pair``, ``rack_and_pinion_pair``, ``screw_pair``, ``posed``) and
``cadgen.gltf`` a GLB's own ``animation``. Every name loads on first use: ``import cadgen``
imports no CAD kernel, and ``import build123d`` binds a module the kernel loads into on its
first attribute (``_internal/lazy_kernel.py``).
"""

from functools import cache as _cache
from typing import TYPE_CHECKING as _TYPE_CHECKING

# Before anything imports build123d, which every cadgen entry point eventually does:
# build123d parses EVERY font in the system font folders at import time, with no
# per-file guard, so one malformed file aborts the import and every cadgen command
# with it (issue #322, upstream in build123d's register_folder), as does a font with
# no family name, whose empty name OCCT refuses (#636). This hides the fonts build123d
# cannot register from that one listing.
#
# It belongs here rather than in a launcher because the `cadgen` front door, the engine's
# warm workers and `python -m cadgen.X` children all reach cadgen by different routes, and a
# fix that covered only one of them would leave the builds it spawns still broken.
#
# Cost where nothing is wrong: one str.endswith per glob call. CADGEN_FONT_GUARD=0
# opts out.
from cadgen._internal.font_scan import install_font_guard as _install_font_guard
from cadgen._internal.lazy_kernel import install as _install_lazy_kernel
from cadgen._internal.engine_telemetry import install as _install_engine_telemetry

# ``import build123d as bd`` binds a module the kernel loads into on its first attribute
# (``_internal/lazy_kernel.py``). The wheel's cadgen-lazy-kernel.pth installs it at interpreter
# start; this covers an editable install, where that file is not placed. Idempotent.
_install_lazy_kernel()
del _install_lazy_kernel

_install_font_guard()
del _install_font_guard

# The engine counts nothing (its law 3: it imports nothing of cadgen): it tells what each of its verbs did to
# the functions in cadgen.engine.api.observers. cadgen's telemetry is one, appended here for the reason the
# font guard is installed here: every route into the engine -- `python model.py`, a `cadgen export` or
# `snapshot`, `cadgen.export()` -- comes through this package first. Appended as the engine's verbs are
# imported, never sooner: a process that uses no engine imports none of it.
_install_engine_telemetry()
del _install_engine_telemetry

from cadgen._internal.engine_host import install as _install_engine_host

_install_engine_host()
del _install_engine_host

# The engine's surface (``cadgen.engine.__all__``) and its operations on documents as functions
# (``cadgen.engine.api``).
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
        import cadgen.engine as _engine

        return getattr(_engine, name)
    if name in _VERBS:
        from cadgen.engine import api

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
    from cadgen.engine.api import export, inspect, snapshot
    from cadgen.engine.model import (
        dxf,
        glb,
        memo,
        model,
        paint,
        read_step,
        read_xbf,
        step,
        stl,
        threemf,
        xbf,
    )
    from cadgen.engine.reader import read_mesh


@_cache
def _resolve_version() -> str:
    """The version declared beside this very package (``_internal.version.declared_version``):
    the source tree's pyproject for a checkout, the dist-info beside it for an install.
    Never the first ``cadgen`` metadata on ``sys.path``, which can be another install's.
    Resolved once per process: the code that answers cannot change under a running one."""
    import pathlib

    from cadgen._internal.version import declared_version

    return declared_version(pathlib.Path(__file__).resolve().parent)
