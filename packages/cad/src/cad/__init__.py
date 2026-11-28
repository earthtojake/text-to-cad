"""cad: CAD models as Python, built by its engine (``cad.engine``) into documents and the files they
declare.

The root holds ``__version__``, ``CadDeprecationWarning``, the verbs and the document types. The verbs are what
is done to a document, one to one with the ``cad`` command's (``cad export SRC DST``): ``export`` (a document,
a mesh, a KiCad file or a shape written to another format, what the destination says: a file by its suffix, or of a
KiCad file a folder or a ``.zip`` too, ``as_`` naming the kind where it cannot), ``inspect``
(what a document holds, a robot description's conformance; ``interference=True``, ``ranges=True``), ``snapshot``,
``dfm`` and ``fea``, each taking a file or the handle a model's call returns (``export`` and ``dfm`` a shape a program
holds too, written or checked in its own process); and ``save``, a shape a program holds saved as a model's
``.xbf``. The document types are one object each (``cad.registry``):
``xbf`` (the engine's own document, saved as its ``.xbf``, which a model built from code writes and the engine
holds in its memory), ``step``, ``glb``, ``stl``, ``threemf``, ``dxf``, ``urdf``, ``srdf``, ``kicad_pcb`` and
``kicad_sch``. A type is its decorator where it has one (``@xbf``, ``@step("arm.step")``), its edit where its
files are changed in place (``with kicad_pcb.edit("board.kicad_pcb") as board:``) and its reader where it has
one (``step.read``, ``xbf.read``). Our helpers that take build123d's objects are
the build123d integration's, ``cad.build123d`` (``memo``, ``paint``, the AP242 mechanism, a GLB's
``animation``, measurements, flat patterns); those that take trimesh's are the trimesh integration's,
``cad.trimesh`` (a mesh's 3D printing measurements: ``printing``, ``orientations``); KiCad's own checks are the
kicad integration's, ``cad.kicad`` (``drc``, ``erc``, and ``route``, copper inside a board's edit); those that call
MuJoCo are the mujoco integration's, ``cad.mujoco`` (a document as a ``mujoco.MjSpec``, a part's collision chosen on
it, the spec saved, and a MuJoCo model checked by MuJoCo's own compiler: ``spec``, ``fit``, ``save``, ``check``); and those that take Blender's are the blender integration's, ``cad.blender`` (``load``: a
GLB in Blender's scene, for a render). Process control (``cad server``) is the ``cad`` command's alone. Every
name loads on first use: ``import cad`` imports no CAD kernel, and ``import build123d`` binds a module the kernel
loads into on its first attribute (``_internal/lazy_kernel.py``). The earlier spellings (``cad.read_step``,
``cad.read_xbf``, ``cad.ap242``, ``cad.model``, a type's operations such as ``cad.xbf.export``, ...) are aliases
of what they name now, each saying so once (``_internal/aliases.py``).
"""

import time as _time
from functools import cache as _cache
from typing import TYPE_CHECKING as _TYPE_CHECKING

# When this library's code began to load in this process: what measures a manufacturing check here
# (``cad.engine._measuring.measuring``, taken when one is first asked) says a code edited since as no other's.
_LOADED_NS = _time.time_ns()
del _time

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
# (``_internal/lazy_kernel.py``). The wheel's cad.pth installs it at interpreter
# start; this covers an editable install, where that file is not placed. Idempotent.
_install_lazy_kernel()
del _install_lazy_kernel

_install_font_guard()
del _install_font_guard

# The library installs nothing of the server's: what the engine's verbs did is told to the functions in
# cad.engine.api.observers, which the server's commands fill (``cad_server._internal.engine_telemetry``),
# and a process the server did not start -- a model's own, in the CAD kernel environment -- counts nothing.

# The document types (``cad.registry``), each a subpackage that is a ``DocumentType``. ``cad.model``, the earlier
# spelling of ``cad.xbf``, is an alias of it (``_internal/aliases.py``).
_TYPES = ("xbf", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf", "kicad_pcb", "kicad_sch")

# The integrations' namespaces (``cad.registry.INTEGRATIONS``): our helpers that take each tool's objects.
_INTEGRATIONS = ("build123d", "kicad", "trimesh", "mujoco", "coacd", "netgen", "calculix", "blender", "orcaslicer")

# The verbs (``_internal/verbs.py``): what is done to a document, one to one with the ``cad`` command's.
_VERBS = ("export", "inspect", "snapshot", "dfm", "fea", "save")

__all__ = [
    "__version__",
    "CadDeprecationWarning",
    *_VERBS,
    *_TYPES,
]

from cad._internal.aliases import CadDeprecationWarning
from cad._internal.aliases import install as _install_aliases

_install_aliases()
del _install_aliases


def __getattr__(name: str):
    if name in _VERBS:
        from cad._internal import verbs

        value = getattr(verbs, name)
        globals()[name] = value
        return value
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
    # A submodule by its own name: a module alias imported (``cad.model``, which is ``cad.xbf``) is none.
    return sorted({*__all__, *(name for name, value in globals().items() if name.startswith("__")
                               or getattr(value, "__name__", "") == f"{__name__}.{name}")})


if _TYPE_CHECKING:
    # Mirrors the lazy __getattr__ above so type checkers and editors see the root without importing
    # OCP. Every name here must have a branch there.
    from cad import dxf, glb, kicad_pcb, kicad_sch, srdf, step, stl, threemf, urdf, xbf
    from cad._internal.verbs import dfm, export, fea, inspect, save, snapshot


@_cache
def _resolve_version() -> str:
    """The version declared beside this very package (``_internal.version.declared_version``):
    the source tree's pyproject for a checkout, the dist-info beside it for an install.
    Never the first ``cad`` metadata on ``sys.path``, which can be another install's.
    Resolved once per process: the code that answers cannot change under a running one."""
    import pathlib

    from cad._internal.version import declared_version

    return declared_version(pathlib.Path(__file__).resolve().parent)
