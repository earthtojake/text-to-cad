"""``cad.trimesh``: the trimesh integration -- our measurements of a triangle mesh for 3D printing,
taking trimesh's ``Trimesh`` (its extra, ``cad[trimesh]``: trimesh, with rtree for its closest points,
scipy for its connected bodies and networkx for filling the face a body shares with another; the rays are
the library's own, in bounded memory).

Each returns the report as plain data, every figure in millimetres, degrees and square millimetres --
facts, never verdicts: nothing here compares a figure against a process's limit:

- ``printing(mesh)``: 3D printing -- the mesh, its scale, overhangs, wall thickness (ray cast, per body)
  and an estimate of the support volume;
- ``orientations(mesh)``: support area and build height for six axis-aligned orientations.

A family that cannot be measured leaves ``{"error": ...}`` where its facts would be, and the report
says so (``partial``, ``partial_sections``). The mesh is never changed: each measures a copy, scaled
by ``units`` to millimetres and cleaned as a file's mesh is (``_mesh``: welded, its collapsed triangles and
doubled slivers and zero-area debris dropped, its tessellation's cracks closed; watertightness judged per
body) and put through the same gate: a mesh with no inside to measure -- no triangles, a corner that is no
number, more than two million triangles, a one-sided surface, a closed one of no volume -- raises
``cad._internal.dfm.Unmeasured`` (its ``code`` and ``message`` the check's one finding), and what the gate
repaired is in the report's ``mesh``.

Injection molding is judged on exact geometry alone (a mesh's chords misread its draft, undercuts and walls):
check the part's STEP or model. A file is measured by its document type's check -- ``cad.stl.dfm("part.stl")``,
``cad.xbf.dfm(model_handle, process="printing")`` -- which answers a ``CheckResult`` whose
``measurements`` is this report and whose findings say what it shows (``cad <type> dfm --process``).
Everything loads on first use: ``import cad.trimesh`` imports no trimesh.
"""

from __future__ import annotations

from typing import Any

__all__ = ["orientations", "printing"]


def _copy(mesh: Any, units: str) -> Any:
    """A copy of ``mesh`` made millimetres and cleaned as a file's is (``_mesh.prepared``)."""
    from cad.trimesh import _mesh

    return _mesh.prepared(mesh.copy(), units)


def printing(mesh: Any, *, units: str = "mm", samples: int = 2000, angle_limit: float = 45.0) -> dict[str, Any]:
    """3D printing's measurements of ``mesh`` (a ``trimesh.Trimesh``) as it stands on the plate (its
    lowest point): overhangs and support counted for down-facing faces under ``angle_limit`` degrees from
    horizontal, wall thickness from ``samples`` rays."""
    from cad.trimesh import _printing

    return _printing.measure(_copy(mesh, units), int(samples), float(angle_limit))


def orientations(mesh: Any, *, units: str = "mm", angle_limit: float = 45.0) -> dict[str, Any]:
    """``printing``'s support area and build height for six axis-aligned orientations of ``mesh``."""
    from cad.trimesh import _printing

    return _printing.orientations(_copy(mesh, units), float(angle_limit))
