"""``cad.trimesh``: the trimesh integration -- our measurements of a triangle mesh for manufacturing,
taking trimesh's ``Trimesh`` (its extra, ``cad[trimesh]``: trimesh, with rtree for its ray casts and
scipy for its connected bodies).

Each returns the report as plain data, every figure in millimetres, degrees and square millimetres --
facts, never verdicts: nothing here compares a figure against a process's limit:

- ``molding(mesh, pull="z")``: injection molding along one pull -- the mesh, its scale, draft (the wall
  area by draft, zero-draft walls, the lowest wall draft, which way the walls open), undercut
  candidates (a straight two-half pull's occlusion test, per body) and the projected area;
- ``pulls(mesh)``: draft and undercuts for each candidate pull, x, y, z and the mesh's principal axes;
- ``printing(mesh)``: 3D printing -- the mesh, its scale, overhangs, wall thickness (ray cast, per body)
  and an estimate of the support volume;
- ``orientations(mesh)``: support area and build height for six axis-aligned orientations.

A family that cannot be measured leaves ``{"error": ...}`` where its facts would be, and the report
says so (``partial``, ``partial_sections``). The mesh is never changed: each measures a copy, scaled
by ``units`` to millimetres (molding also drops its zero-area triangles, whose normals have no
direction).

A file is measured by its document type's check -- ``cad.stl.check("part.stl", process="molding")``,
``cad.xbf.check(model_handle, process="printing")`` -- which answers a ``CheckResult`` whose
``measurements`` is this report and whose findings say what it shows (``cad <type> check --process``).
Everything loads on first use: ``import cad.trimesh`` imports no trimesh.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = ["molding", "orientations", "printing", "pulls"]


def _pull(pull: str | Sequence[float]) -> Any:
    from cad.trimesh._molding import _pull_vector

    return _pull_vector(pull if isinstance(pull, str) else ",".join(f"{float(value)!r}" for value in pull))


def _copy(mesh: Any, units: str) -> Any:
    from cad._internal.manufacturing import UNITS_MM

    if units not in UNITS_MM:
        raise ValueError(f"units is one of {', '.join(UNITS_MM)}, not {units!r}")
    copied = mesh.copy()
    if UNITS_MM[units] != 1.0:
        copied.apply_scale(UNITS_MM[units])
    return copied


def molding(mesh: Any, *, pull: str | Sequence[float] = "z", units: str = "mm", wall_limit: float = 45.0,
            zero_tol: float = 0.05) -> dict[str, Any]:
    """Injection molding's measurements of ``mesh`` (a ``trimesh.Trimesh``) along ``pull``: an axis
    (``"z"``, ``"-y"``), ``"x,y,z"`` components or three numbers. ``wall_limit``: faces at or above this
    many degrees from the pull are not walls; ``zero_tol``: draft under this many degrees is zero."""
    from cad.trimesh import _molding

    vector = _pull(pull)
    copied = mesh.copy()
    return _molding.measure(_molding._prepared(copied, units), vector, float(wall_limit), float(zero_tol))


def pulls(mesh: Any, *, units: str = "mm", wall_limit: float = 45.0, zero_tol: float = 0.05) -> dict[str, Any]:
    """``molding``'s draft and undercuts for each candidate pull: x, y, z and the mesh's principal axes
    (``+axis`` and ``-axis`` are one candidate: draft does not change with the pull's sign)."""
    from cad.trimesh import _molding

    return _molding.pulls(_molding._prepared(mesh.copy(), units), float(wall_limit), float(zero_tol))


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
