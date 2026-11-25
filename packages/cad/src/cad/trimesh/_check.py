"""The manufacturing check of a mesh, measured with trimesh: what ``cad.<type>.dfm(source,
process="printing")`` runs for an STL, a 3MF or a GLB once its options are resolved
(``cad._internal.manufacturing``, which refuses every other process for a mesh: they are judged on exact
geometry).

**The mesh.** An STL is measured as read and cleaned (``_mesh``: welded, its collapsed triangles and
doubled slivers and debris dropped, its tessellation's cracks closed); a 3MF or a GLB is read by the library's own readers (its
objects placed by its build, its units -- a 3MF's declared unit, a GLB's glTF metres, Y up -- made
millimetres, Z up, as the viewer reads it) and written as one STL in a temporary folder, with no CAD
kernel. The temporary folder is gone when the check returns: the check writes nothing beside its source.

**The report** is the measurement's (``_printing``: every family, ``partial`` and
``partial_sections``), facts alone; the type side makes the result of it (``manufacturing.finish``: the
process's findings and the rules' verdicts). Every place is ``x, y, z`` in millimetres: a mesh has no
faces a ref names.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cad._internal.dfm import Unmeasured

__all__ = ["measure"]

_MESHES = (".3mf", ".glb")


def _mesh_file(path: Path, folder: Path) -> Path:
    """The STL the check measures: the source's own, else one the library writes of it in ``folder``."""
    from cad.engine.api import export

    if path.suffix.lower() == ".stl":
        return path
    written = folder / "measured.stl"
    export(path, written, daemon=False, progress=False)  # numpy alone: no kernel, no engine
    return written


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The report of the mesh ``source`` for ``process`` (printing), or ``Unmeasured``."""
    from cad._internal.dfm.printing import angle_limit
    from cad.trimesh import _mesh, _printing

    path = Path(source).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="cad-check-") as folder:
        try:
            stl = _mesh_file(path, Path(folder))
            mesh = _mesh.load(str(stl), options["units"])
        except Unmeasured:  # the gate's own refusal (``_mesh.readable``, ``_mesh.sound``), in its words
            raise
        except Exception as error:  # noqa: BLE001 - a mesh that does not read is the check's answer
            raise Unmeasured("mesh_unreadable", f"failed to load mesh: {error}") from None
        if process == "printing":
            if candidates:
                report = _printing.orientations(mesh, angle_limit(options), options)
            else:
                report = _printing.measure(mesh, options["samples"], angle_limit(options), options)
        else:
            raise Unmeasured("needs_exact_geometry", f"a {process} check measures exact geometry: check the "
                             "part's STEP or model")
    return {"source": {"type": document_type, "measured_as": "mesh"}, **report}
