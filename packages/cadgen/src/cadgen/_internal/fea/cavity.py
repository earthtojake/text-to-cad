"""The inside of a container: the space a liquid fills in a tank, a cup or a channel, and its mesh.

The cavity is an OCP boolean: the part's bounding box, exact on every side the
part opens on (a face lying flat on that side with a hole in it: an open top)
and standing off the part on the others, minus the part. The air around the
part touches a stand-off side; the inside does not. So the cavity is the
largest solid of the cut that touches no side but the part's own openings: a
sealed tank's inside touches none, an open tank's touches its open top.

Each face of the cavity is a wall (an image of one of the part's faces through
the boolean's history, carrying the part's ``#o1.fN`` ref, so the pressure
lands on the face the viewer shows) or an opening (flat on one of the part's
open sides, ``x_min`` ... ``z_max``). The mesh is netgen's linear tetrahedra,
through the part mesher's BREP hand-off and fingerprint matcher (:mod:`.mesh`,
read only), optionally finer in a band (the sweep of a free surface).

Numeric imports live inside the functions.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadgen._internal.fea.fluid_domain import FluidDomain
    from cadgen._internal.fea.mesh import VolumeMesh

__all__ = ["OPENINGS", "build_cavity", "mesh_cavity", "skfem_mesh"]

OPENINGS = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
#: The box's stand-off from the part on its closed sides, as a share of the part's diagonal.
STANDOFF = 0.1


def _bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return [xmin, ymin, zmin], [xmax, ymax, zmax]


def _map(shape, kind):
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, found)
    return found


def _list(shape, kind) -> list:
    found = _map(shape, kind)
    return [found.FindKey(k) for k in range(1, found.Extent() + 1)]


def _volume(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def _surface(face):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    centre = props.CentreOfMass()
    line = GProp_GProps()
    BRepGProp.LinearProperties_s(face, line)
    return float(props.Mass()), (centre.X(), centre.Y(), centre.Z()), float(line.Mass())


def _side(face, low, high, tol: float) -> str | None:
    """The box side a planar face lies flat on ("z_max"), or None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopoDS import TopoDS

    if BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType() != GeomAbs_Plane:
        return None
    flo, fhi = _bounds(face)
    for axis in range(3):
        if fhi[axis] - flo[axis] > tol:
            continue
        middle = 0.5 * (flo[axis] + fhi[axis])
        if abs(middle - low[axis]) <= tol:
            return OPENINGS[2 * axis]
        if abs(middle - high[axis]) <= tol:
            return OPENINGS[2 * axis + 1]
    return None


def build_cavity(part, *, refs: dict[int, str] | None = None) -> "FluidDomain":
    """The space inside ``part`` (an OCP shape, placed) and what each of its faces is.

    The domain's ``kind`` is "cavity"; its faces are "wall" or "opening" (with the side, ``opening``).
    ValueError, in words, when the part has no inside a liquid could fill.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_WIRE
    from OCP.gp import gp_Pnt

    from cadgen._internal.entity_ordinals import entity_map
    from cadgen._internal.fea.fluid_domain import FluidDomain, FluidFace

    started = time.perf_counter()
    low, high = _bounds(part)
    extent = [h - l for l, h in zip(low, high)]
    diagonal = sum(e * e for e in extent) ** 0.5
    if not diagonal > 0:
        raise RuntimeError("the part has no volume to hold a liquid")
    tol = 1e-6 * max(diagonal, 1.0)
    # The sides the part opens on: a face lying flat there with a hole in it.
    open_sides = set()
    for face in _list(part, TopAbs_FACE):
        side = _side(face, low, high, tol)
        if side is not None and _map(face, TopAbs_WIRE).Extent() > 1:
            open_sides.add(side)
    box_low, box_high = list(low), list(high)
    standoff = STANDOFF * diagonal
    for axis in range(3):
        if OPENINGS[2 * axis] not in open_sides:
            box_low[axis] -= standoff
        if OPENINGS[2 * axis + 1] not in open_sides:
            box_high[axis] += standoff
    cut = BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(gp_Pnt(*box_low), gp_Pnt(*box_high)).Shape(), part)
    if not cut.IsDone():
        raise RuntimeError("the boolean that finds the inside of the part failed")
    inside = []
    for solid in _list(cut.Shape(), TopAbs_SOLID):
        sides = {s for face in _list(solid, TopAbs_FACE) if (s := _side(face, box_low, box_high, tol)) is not None}
        if sides <= open_sides:
            inside.append((_volume(solid), solid, sides))
    if not inside:
        raise ValueError("multiphase: the part has no inside to hold a liquid; it needs a cavity (a tank, a cup, a "
                         "channel closed at the bottom), open at most on a side of its bounding box")
    volume, solid, sides = max(inside, key=lambda item: item[0])

    faces_map = _map(solid, TopAbs_FACE)
    part_faces = entity_map(part, "face")
    wall_of: dict[int, int] = {}
    for ordinal in range(1, part_faces.Extent() + 1):
        face = part_faces.FindKey(ordinal)
        images = list(cut.Modified(face)) or ([] if cut.IsDeleted(face) else [face])
        for image in images:
            index = faces_map.FindIndex(image)
            if index > 0:
                wall_of[index] = ordinal
    refs = refs or {}
    faces = []
    for index in range(1, faces_map.Extent() + 1):
        face = faces_map.FindKey(index)
        area, centre, perimeter = _surface(face)
        side = _side(face, box_low, box_high, tol)
        if index in wall_of:
            faces.append(FluidFace(index, "wall", area, perimeter, centre, wall_of[index], refs.get(wall_of[index])))
        elif side in sides:
            faces.append(FluidFace(index, "opening", area, perimeter, centre, opening=side))
        else:
            faces.append(FluidFace(index, "wall", area, perimeter, centre))
    clow, chigh = _bounds(solid)
    return FluidDomain(
        shape=solid, kind="cavity", faces=faces, volume_mm3=volume,
        part_box=(tuple(low), tuple(high)), box=(tuple(clow), tuple(chigh)),
        length_mm=max(h - l for l, h in zip(clow, chigh)),
        seconds=time.perf_counter() - started, wetted={face.ordinal for face in faces if face.ordinal},
    )


def mesh_cavity(domain: "FluidDomain", size_mm: float, *, band: dict | None = None) -> "VolumeMesh":
    """netgen's linear tetrahedra of the cavity at ``size_mm``; ``band`` ``{"points": [[x, y, z, h], ...],
    "radius_mm": r}`` meshes finer around its points. ``boundary_ordinal`` is each boundary triangle's cavity face index."""
    import tempfile
    from pathlib import Path

    import numpy as np

    from cadgen._internal.fea import mesh as part_mesh
    from cadgen._internal.fea.mesh import FaceFingerprint, VolumeMesh, require_fea_stack
    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr

    require_fea_stack()
    prints = [FaceFingerprint(face.ref or f"cavity face {face.index}", face.index, face.area, face.centre) for face in domain.faces]
    low, high = (np.array(corner) for corner in domain.box)
    diagonal = float(np.linalg.norm(high - low))
    started = time.perf_counter()
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-cavity-") as tmp:
        brep = Path(tmp) / "cavity.brep"
        part_mesh.write_brep(domain.shape, brep)
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = part_mesh.match_faces(prints, list(geometry.faces), diagonal)
            keys = {index: [ordinal] for index, ordinal in mapping.items()}
            mesh = part_mesh.generate_mesh(geometry, ngocc, float(size_mm), 1.0, 1, band, keys)
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            del mesh, geometry
    if len(e3) == 0:
        raise RuntimeError("the mesher produced no elements inside the part")
    index_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, ordinal in mapping.items():
        index_of[index + 1] = ordinal
    return VolumeMesh(
        nodes=coordinates,
        tets=np.ascontiguousarray(e3["nodes"][:, :4].astype(np.int64) - 1),
        boundary=np.ascontiguousarray(e2["nodes"][:, :3].astype(np.int64) - 1),
        boundary_ordinal=index_of[e2["index"].astype(np.int64)],
        faces={fp.ordinal: fp for fp in prints},
        max_h=float(size_mm),
        bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started,
    )


def skfem_mesh(volume: "VolumeMesh") -> tuple[Any, Any]:
    """The cavity's mesh as skfem's (corners only, metres), and each skfem boundary facet's cavity face index."""
    import numpy as np
    from skfem import MeshTet

    used = np.unique(volume.tets)
    renumber = np.full(len(volume.nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    mesh = MeshTet(np.ascontiguousarray(volume.nodes[used].T * 1e-3), np.ascontiguousarray(renumber[volume.tets].T))
    face_of = {tuple(sorted(renumber[tri])): int(o) for tri, o in zip(volume.boundary, volume.boundary_ordinal)}
    boundary = mesh.boundary_facets()
    keys = np.sort(mesh.facets[:, boundary], axis=0).T
    facet_face = np.array([face_of.get(tuple(int(v) for v in key), 0) for key in keys], dtype=np.int64)
    return mesh, (boundary, facet_face)
