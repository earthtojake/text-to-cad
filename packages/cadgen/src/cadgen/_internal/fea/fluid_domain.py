"""The fluid a flow study solves in: an OCP boolean around (or through) the part, and its mesh.

Internal flow (through a pipe, a manifold, a channel): the part's bounding box,
exact on the opening planes the study names and a little larger on its other
sides, minus the part. What is left is the passage the flow runs through, plus
the air around the part. The passage is the solid that opens on every named
opening plane and on no other side of the box: the air around the part also
touches the box's other sides. A study whose openings name a side the part has
no opening on is a study error that names the sides it does have.

External flow (around a body): a box reaching 2 L upstream, 5 L downstream and
2 L to the sides (L the part's largest extent), minus the part. Each box side
the free stream enters through is an inlet, each it leaves through an outlet,
each it runs along a slip wall.

Each face of the fluid is classified: a wall (an image of one of the part's
faces through the boolean's history, so it carries the part's ``#o1.fN`` ref
and the wall pressure lands on the face the viewer shows), an inlet, an outlet
or a slip side. The mesh is netgen's, through the same BREP hand-off and the
same fingerprint matcher as the part's own mesh (:mod:`.mesh`, read only), and
its local sizes are the fluid size field: fine at walls and openings, coarser
in the free stream when the ladder's ``fluid_coarsen`` asks for it.

Numeric imports live inside the functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadgen._internal.fea.mesh import VolumeMesh

__all__ = ["OPENINGS", "FluidDomain", "FluidFace", "build_domain", "fine_faces", "mesh_fluid", "opening_words"]

#: The sides of the part's bounding box an opening can name, in axis order.
OPENINGS = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
#: External flow: the box reaches this many part lengths upstream, downstream and to the sides.
UPSTREAM, DOWNSTREAM, SIDES = 2.0, 5.0, 2.0
#: Internal flow: the box's sides that are not openings stand off the part by this share of its diagonal.
STANDOFF = 0.1


def opening_words(opening: str) -> str:
    """"x_min" -> "the low X side"."""
    axis, side = opening.split("_")
    return f"the {'low' if side == 'min' else 'high'} {axis.upper()} side"


def _axis_side(opening: str) -> tuple[int, int]:
    axis, side = opening.split("_")
    return "xyz".index(axis), 0 if side == "min" else 1


@dataclass
class FluidFace:
    """One face of the fluid region and what the flow does there."""

    #: 1-based position in the fluid shape's face map (netgen's face index + 1 once matched).
    index: int
    #: "wall" (the part's surface, no slip), "inlet", "outlet" or "side" (an external box side, slip).
    kind: str
    area: float
    perimeter: float
    centre: tuple[float, float, float]
    #: A wall's part face: its cadgen ordinal and ref (0 and None when it is not one of the part's faces).
    ordinal: int = 0
    ref: str | None = None
    #: The box side an opening or a slip side lies on ("x_min").
    opening: str | None = None


@dataclass
class FluidDomain:
    """The fluid region of a flow study: the solid(s) netgen meshes and what each face is."""

    shape: Any
    kind: str                                  # "internal" or "external"
    faces: list[FluidFace]
    volume_mm3: float
    #: The part's bounding box (low, high), mm.
    part_box: tuple[tuple[float, float, float], tuple[float, float, float]]
    #: The fluid box (low, high), mm.
    box: tuple[tuple[float, float, float], tuple[float, float, float]]
    #: The part's largest extent, mm: an external flow's length scale.
    length_mm: float
    seconds: float = 0.0
    #: Part ordinals whose faces the fluid wets.
    wetted: set[int] = field(default_factory=set)

    def of_kind(self, *kinds: str) -> list[FluidFace]:
        return [face for face in self.faces if face.kind in kinds]

    @property
    def wall_area_mm2(self) -> float:
        return sum(face.area for face in self.faces if face.kind == "wall")


# -- geometry helpers ---------------------------------------------------------------------------------


def _bounds(shape) -> tuple[list[float], list[float]]:
    """The exact bounding box (no tolerance gap), mm."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return [xmin, ymin, zmin], [xmax, ymax, zmax]


def _box(low, high):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    return BRepPrimAPI_MakeBox(gp_Pnt(*low), gp_Pnt(*high)).Shape()


def _faces(shape) -> list:
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    return [faces.FindKey(k) for k in range(1, faces.Extent() + 1)]


def _solids(shape) -> list:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    solids = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_SOLID, solids)
    return [solids.FindKey(k) for k in range(1, solids.Extent() + 1)]


def _volume(shape) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def _area_centre_perimeter(face) -> tuple[float, tuple[float, float, float], float]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    centre = props.CentreOfMass()
    line = GProp_GProps()
    BRepGProp.LinearProperties_s(face, line)
    return float(props.Mass()), (centre.X(), centre.Y(), centre.Z()), float(line.Mass())


def _plane_of(face, box_low, box_high, tol: float) -> str | None:
    """The box side a planar face lies flat on ("x_min"), or None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopoDS import TopoDS

    if BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType() != GeomAbs_Plane:
        return None
    low, high = _bounds(face)
    for axis in range(3):
        if high[axis] - low[axis] > tol:
            continue
        middle = 0.5 * (low[axis] + high[axis])
        if abs(middle - box_low[axis]) <= tol:
            return OPENINGS[2 * axis]
        if abs(middle - box_high[axis]) <= tol:
            return OPENINGS[2 * axis + 1]
    return None


def _sides_of(solid, box_low, box_high, tol: float) -> set[str]:
    return {side for face in _faces(solid) if (side := _plane_of(face, box_low, box_high, tol)) is not None}


def _cut(box, part):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    cut = BRepAlgoAPI_Cut(box, part)
    if not cut.IsDone():
        raise RuntimeError("the boolean that makes the fluid region from the part failed")
    return cut


def _wall_images(cut, part) -> dict:
    """Each image of a part face in the cut, keyed for lookup -> the part face's cadgen ordinal."""
    from cadgen._internal.entity_ordinals import entity_map

    faces = entity_map(part, "face")
    images: list[tuple[Any, int]] = []
    for ordinal in range(1, faces.Extent() + 1):
        face = faces.FindKey(ordinal)
        modified = list(cut.Modified(face))
        if modified:
            images += [(image, ordinal) for image in modified]
        elif not cut.IsDeleted(face):
            images.append((face, ordinal))
    return images


def _compound(solids):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    if len(solids) == 1:
        return solids[0]
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for solid in solids:
        builder.Add(compound, solid)
    return compound


# -- the fluid region ---------------------------------------------------------------------------------


def build_domain(part, kind: str, *, openings: dict[str, str] | None = None,
                 velocity: tuple[float, float, float] | None = None, refs: dict[int, str] | None = None) -> FluidDomain:
    """The fluid region around ``part`` (an OCP shape, placed) and what each of its faces is.

    Internal: ``openings`` maps each named side ("x_min") to "inlet" or "outlet". External:
    ``velocity`` is the free stream's direction (any length). ``refs`` names the part's faces by
    cadgen ordinal (``{3: "#o1.f3"}``). ValueError for an opening the part does not have there.
    """
    started = time.perf_counter()
    low, high = _bounds(part)
    extent = [h - l for l, h in zip(low, high)]
    diagonal = sum(e * e for e in extent) ** 0.5
    if not diagonal > 0:
        raise RuntimeError("the part has no volume to put in a flow")
    length = max(extent)
    tol = 1e-6 * max(diagonal, 1.0)
    refs = refs or {}
    if kind == "internal":
        solids, box_low, box_high, cut = _internal(part, openings or {}, low, high, diagonal, tol)
        roles = dict(openings or {})
    else:
        solids, box_low, box_high, cut = _external(part, velocity, low, high, length, tol)
        roles = {}
    shape = _compound(solids)

    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    wall_of: dict[int, int] = {}
    for image, ordinal in _wall_images(cut, part):
        index = face_map.FindIndex(image)
        if index > 0:
            wall_of[index] = ordinal
    faces: list[FluidFace] = []
    direction = None
    if velocity is not None:
        norm = sum(c * c for c in velocity) ** 0.5
        direction = [c / norm for c in velocity]
    for index in range(1, face_map.Extent() + 1):
        face = face_map.FindKey(index)
        area, centre, perimeter = _area_centre_perimeter(face)
        side = _plane_of(face, box_low, box_high, tol)
        if index in wall_of:
            ordinal = wall_of[index]
            faces.append(FluidFace(index, "wall", area, perimeter, centre, ordinal, refs.get(ordinal)))
        elif kind == "internal" and side in roles:
            faces.append(FluidFace(index, roles[side], area, perimeter, centre, opening=side))
        elif kind == "external" and side is not None:
            axis, high_side = _axis_side(side)
            outward = 1.0 if high_side else -1.0
            along = direction[axis] * outward
            role = "outlet" if along > 1e-9 else "inlet" if along < -1e-9 else "side"
            faces.append(FluidFace(index, role, area, perimeter, centre, opening=side))
        else:
            # Not traced to a part face nor on an opening: the part's surface all the same (a wall).
            faces.append(FluidFace(index, "wall", area, perimeter, centre))
    return FluidDomain(
        shape=shape, kind=kind, faces=faces, volume_mm3=sum(_volume(solid) for solid in solids),
        part_box=(tuple(low), tuple(high)), box=(tuple(box_low), tuple(box_high)), length_mm=length,
        seconds=time.perf_counter() - started, wetted={face.ordinal for face in faces if face.ordinal},
    )


def _opening_sides(part, low, high, tol: float) -> set[str]:
    """The box sides the part opens on: those where a face of the part lies flat with a hole in it."""
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    sides = set()
    for face in _faces(part):
        side = _plane_of(face, low, high, tol)
        if side is None or side in sides:
            continue
        wires = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(face, TopAbs_WIRE, wires)
        if wires.Extent() > 1:
            sides.add(side)
    return sides


def _internal(part, openings: dict[str, str], low, high, diagonal: float, tol: float):
    """The passage(s) through the part that open on exactly the named sides.

    The box is exact on every side the part opens on (a face there with a hole) and on every named
    side, and stands off the part elsewhere, so the air around the part touches a side no passage
    does. A passage is a solid of the cut that touches only exact sides.
    """
    named = set(openings)
    available = _opening_sides(part, low, high, tol)
    order = OPENINGS.index
    if missing := sorted(named - available, key=order):
        where = (f"its openings are on {', '.join(sorted(available, key=order))}" if available
                 else "it has no face on its bounding box with a hole in it")
        raise ValueError(
            f"flow: the part has no opening on {', '.join(f'{opening_words(m)} ({m})' for m in missing)}; {where}; "
            "name those sides as the inlets and outlets (or use kind \"external\" for flow around it)")
    exact = named | available
    standoff = STANDOFF * diagonal
    box_low, box_high = list(low), list(high)
    for axis in range(3):
        if OPENINGS[2 * axis] not in exact:
            box_low[axis] -= standoff
        if OPENINGS[2 * axis + 1] not in exact:
            box_high[axis] += standoff
    cut = _cut(_box(box_low, box_high), part)
    passages = []
    for solid in _solids(cut.Shape()):
        sides = _sides_of(solid, box_low, box_high, tol)
        if sides and sides <= exact:
            passages.append((solid, sides))
    keep = [solid for solid, sides in passages if sides == named]
    if keep:
        return keep, box_low, box_high, cut
    words = " and ".join(sorted(named, key=order))
    wider = [sides - named for _, sides in passages if named <= sides]
    if wider:
        extra = min(wider, key=len)
        raise ValueError(f"flow: the passage from {words} also opens on {', '.join(sorted(extra, key=order))}; "
                         "name every opening of the passage as an inlet or an outlet")
    found = "; ".join(", ".join(sorted(sides, key=order)) for _, sides in passages)
    raise ValueError(f"flow: no single passage through the part joins {words}"
                     + (f"; its passages open on {found}" if found else ""))


def _external(part, velocity, low, high, length: float, tol: float):
    """The box around the part, 2 L upstream, 5 L downstream and 2 L to the sides, minus the part."""
    dominant = max(range(3), key=lambda axis: abs(velocity[axis]))
    box_low, box_high = [], []
    for axis in range(3):
        before, after = SIDES * length, SIDES * length
        if axis == dominant:
            before, after = (UPSTREAM * length, DOWNSTREAM * length) if velocity[axis] > 0 else (DOWNSTREAM * length, UPSTREAM * length)
        box_low.append(low[axis] - before)
        box_high.append(high[axis] + after)
    cut = _cut(_box(box_low, box_high), part)
    # A closed cavity inside the part is not in the flow: keep what touches the box.
    solids = [solid for solid in _solids(cut.Shape()) if _sides_of(solid, box_low, box_high, tol)]
    if not solids:
        raise RuntimeError("the boolean that makes the fluid region around the part left no fluid")
    return solids, box_low, box_high, cut


# -- the mesh -----------------------------------------------------------------------------------------


def fine_faces(domain: FluidDomain) -> list[FluidFace]:
    """The faces kept at the wall size: the part's walls, and an internal flow's openings (an external
    box's sides are far field)."""
    kinds = ("wall",) if domain.kind == "external" else ("wall", "inlet", "outlet")
    return [face for face in domain.faces if face.kind in kinds]


def mesh_fluid(domain: FluidDomain, wall_mm: float, far_mm: float | None = None, *, order: int = 2) -> "VolumeMesh":
    """netgen's tetrahedra of the fluid: ``wall_mm`` at walls and openings, up to ``far_mm`` away from them.

    The mesh's ``boundary_ordinal`` is each boundary triangle's fluid face index (``domain.faces``),
    matched by the part mesher's fingerprint matcher; ``faces`` holds a fingerprint per fluid face.
    """
    import tempfile
    from pathlib import Path

    import numpy as np

    from cadgen._internal.fea import mesh as part_mesh
    from cadgen._internal.fea.mesh import FaceFingerprint, VolumeMesh, require_fea_stack
    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr

    require_fea_stack()
    far = float(far_mm) if far_mm and far_mm > wall_mm else float(wall_mm)
    prints = [FaceFingerprint(face.ref or f"fluid face {face.index}", face.index, face.area, face.centre) for face in domain.faces]
    low, high = (np.array(corner) for corner in domain.box)
    diagonal = float(np.linalg.norm(high - low))
    size_field = None
    if far > wall_mm:
        size_field = {"faces": {face.index: float(wall_mm) for face in fine_faces(domain)}}
    started = time.perf_counter()
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-cfd-") as tmp:
        brep = Path(tmp) / "fluid.brep"
        part_mesh.write_brep(domain.shape, brep)
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            geometry = ngocc.OCCGeometry(str(brep))
            mapping = part_mesh.match_faces(prints, list(geometry.faces), diagonal)
            keys = {index: [ordinal] for index, ordinal in mapping.items()}
            mesh = part_mesh.generate_mesh(geometry, ngocc, far, 1.0, order, size_field, keys)
            coordinates = np.array(mesh.Coordinates(), dtype=float, copy=True)
            e3 = mesh.Elements3D().NumPy().copy()
            e2 = mesh.Elements2D().NumPy().copy()
            del mesh, geometry
    if len(e3) == 0:
        raise RuntimeError("the mesher produced no fluid elements")
    part_mesh.require_elements(e3, order)
    width = 10 if order == 2 else 4
    index_of = np.zeros(int(e2["index"].max()) + 1, dtype=np.int64)
    for index, ordinal in mapping.items():
        index_of[index + 1] = ordinal
    return VolumeMesh(
        nodes=coordinates,
        tets=np.ascontiguousarray(e3["nodes"][:, :width].astype(np.int64) - 1),
        boundary=np.ascontiguousarray(e2["nodes"][:, :6 if order == 2 else 3].astype(np.int64) - 1),
        boundary_ordinal=index_of[e2["index"].astype(np.int64)],
        faces={fp.ordinal: fp for fp in prints},
        max_h=far,
        bbox_diagonal=diagonal,
        seconds=time.perf_counter() - started,
    )
