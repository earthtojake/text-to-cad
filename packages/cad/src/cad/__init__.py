"""cad: CAD models as Python, built by its engine (``cad.engine``) into documents and the files they
declare.

The root holds ``__version__``, ``CadDeprecationWarning`` and the document types, one object each
(``cad.registry``): ``model`` (a model built from code, held in the engine's memory, with no file), ``xbf``,
``step``, ``glb``, ``stl``, ``threemf``, ``dxf``, ``urdf``, ``sdf``, ``srdf``, ``mjcf``, ``kicad_pcb`` and
``kicad_sch``. A type is its decorator where it has one (``@model``, ``@step("arm.step")``), its edit where
its files are changed in place (``with kicad_pcb.edit("board.kicad_pcb") as board:``), its reader where it
has one (``step.read``) and its
operations, one to one with the ``cad <type> <operation>`` commands: ``.export`` and ``.snapshot``,
``.inspect``, and those named for what they do (``.dfm``, ``.drc``, ``.erc``, ``.validate``). Our helpers that take build123d's objects are
the build123d integration's, ``cad.build123d`` (``memo``, ``paint``, the AP242 mechanism, a GLB's
``animation``, measurements, flat patterns); those that take trimesh's are the trimesh integration's,
``cad.trimesh`` (a mesh's manufacturing measurements: ``molding``, ``pulls``, ``printing``,
``orientations``); those that call MuJoCo are the mujoco integration's, ``cad.mujoco`` (an MJCF compiled by
MuJoCo's compiler: ``compile_model``, ``compile_findings``). Process control (``cad serve``, ``status``, ``stop``,
``server``) is the ``cad`` command's alone. Every name loads on first use: ``import cad`` imports no CAD
kernel, and ``import build123d`` binds a module the kernel loads into on its first attribute
(``_internal/lazy_kernel.py``). The earlier spellings (``cad.read_step``, ``cad.export``, ``cad.ap242``,
...) are aliases of what they name now, each saying so once (``_internal/aliases.py``).
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

# The document types (``cad.registry.DOCUMENT_TYPES``), each a subpackage that is a ``DocumentType``.
_TYPES = ("model", "xbf", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf", "sdf", "mjcf", "kicad_pcb", "kicad_sch")

# The integrations' namespaces (``cad.registry.INTEGRATIONS``): our helpers that take each tool's objects.
_INTEGRATIONS = ("build123d", "kicad", "mujoco", "trimesh")

__all__ = [
    "__version__",
    "CadDeprecationWarning",
    *_TYPES,
]

from cad._internal.aliases import CadDeprecationWarning
from cad._internal.aliases import install as _install_aliases

_install_aliases()
del _install_aliases


def __getattr__(name: str):
    if name in _TYPES or name in _INTEGRATIONS:
        import importlib

        return importlib.import_module(f"{__name__}.{name}")
    if name == "__version__":
        return _resolve_version()
    from cad._internal.aliases import lookup

    return lookup(__name__, name)


def __dir__() -> list[str]:
    """Its public names (``__all__``) and the submodules imported so far: what ``dir()`` and
    completion offer, without loading any of them, nor the kernel."""
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "").startswith(__name__ + "."))})


if _TYPE_CHECKING:
    # Mirrors the lazy __getattr__ above so type checkers and editors see the root without importing
    # OCP. Every name here must have a branch there.
    from cad import dxf, glb, kicad_pcb, kicad_sch, mjcf, model, sdf, srdf, step, stl, threemf, urdf, xbf


@_cache
def _resolve_version() -> str:
    """The version declared beside this very package (``_internal.version.declared_version``):
    the source tree's pyproject for a checkout, the dist-info beside it for an install.
    Never the first ``cad`` metadata on ``sys.path``, which can be another install's.
    Resolved once per process: the code that answers cannot change under a running one."""
    import pathlib

    from cad._internal.version import declared_version

    return declared_version(pathlib.Path(__file__).resolve().parent)
