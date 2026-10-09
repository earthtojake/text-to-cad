"""An assembly's parts, the faces where they touch, and the parts glued into one shape.

A part is one leaf occurrence of the STEP scene, placed in world coordinates.
Two parts are in contact when a face of one lies on a face of the other, or
within the contact tolerance of it, over an area. Each stage cheaply drops
pairs the next would spend long on: a sweep over the parts' boxes (enlarged by
the tolerance), the boxes of each pair's faces, a lower bound on the distance
from sampled tessellations, then ``BRepExtrema_DistShapeShape`` for the gap,
then the common area of the two faces (the second moved across the gap first)
so that parts meeting only along an edge or at a point are not in contact.

Gluing is OpenCascade's general fuse (``BOPAlgo_Builder``): parts that share a
face come out sharing ONE face, so netgen meshes them with shared nodes there
and the mesh is conforming without any tie constraints. Only bonded parts are
glued together; a group with a gap is glued with a fuzzy value of the
tolerance, which closes the gap by moving geometry up to that far.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadgen.step_scene import StepScene

__all__ = ["Contact", "Glued", "Part", "detect_contacts", "glue", "list_parts", "part_centre", "part_faces", "part_gap"]

# OpenCascade's own confusion distance: a gap below it is touching.
_TOUCHING_MM = 1e-7
# Overlap below this is an edge or a point, not a face in contact.
_MIN_AREA_MM2 = 1e-6
# The tessellation behind the faces' distance bound: its deviation from the
# surface, angle between normals, and the longest triangle edge it is cut to.
_DEFLECTION_MM = 0.5
_ANGLE_RAD = 0.5
_SAMPLE_MM = 2.0
_SAMPLES_PER_FACE = 400
# Past this many triangles on one face the cutting stops and the bound is looser.
_MAX_TRIANGLES = 20_000


@dataclass(frozen=True)
class Part:
    """One placed leaf occurrence of an assembly."""

    #: The occurrence's selector (``#o1.2``).
    ref: str
    #: The occurrence's label, else its ref.
    name: str
    volume_mm3: float
    #: The placed OCP shape (world coordinates), owned by this part.
    shape: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class Contact:
    """Two parts whose faces touch, or face each other within the tolerance.

    ``a`` is the smaller part (by volume), the one attached to ``b``.
    """

    a: str
    b: str
    area_mm2: float
    gap_mm: float


@dataclass
class Glued:
    """The parts glued into one compound, with where each part went."""

    #: A compound of every part's solids, bonded ones sharing their common faces.
    shape: Any
    #: The part index of each solid of ``shape``, in explorer order.
    solid_part: list[int]
    #: Per part, per face ordinal (index 0 = ordinal 1): the 1-based indices of
    #: the faces of ``shape`` that face became (several when gluing split it).
    face_images: list[list[list[int]]]
    #: The fuzzy value the glue used (0 when every bonded pair touches).
    fuzzy_mm: float


def list_parts(scene: "StepScene") -> list[Part]:
    """Every leaf occurrence of the scene, in scene order."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    parts = []
    for leaf in scene.leaves():
        shape = leaf.shape().wrapped
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        parts.append(Part(ref=leaf.ref, name=leaf.label or leaf.ref, volume_mm3=float(props.Mass()), shape=shape))
    return parts


def part_faces(shape) -> list:
    """The faces of a shape in cadgen's face-ordinal order (index 0 = ordinal 1)."""
    from cadgen._internal.entity_ordinals import entity_map

    faces = entity_map(shape, "face")
    return [faces.FindKey(i) for i in range(1, faces.Extent() + 1)]


def _box(shape, enlarge: float):
    """The tight bounding box of a shape (computed from its geometry, not its control points), grown by ``enlarge``."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if not box.IsVoid():
        box.Enlarge(enlarge)
    return box


def _close_pairs(boxes: list) -> list[tuple[int, int]]:
    """The index pairs ``i < j`` whose boxes meet, in order: a sweep along X over the boxes sorted by their low end.

    Each box is compared only with the ones that start before it ends, so a
    long assembly costs its neighbours, not every pair of parts.
    """
    bounds = [(index, box.Get()) for index, box in enumerate(boxes) if not box.IsVoid()]
    bounds.sort(key=lambda item: item[1][0])
    pairs = []
    for position, (i, a) in enumerate(bounds):
        for j, b in bounds[position + 1:]:
            if b[0] > a[3]:
                break
            if b[1] <= a[4] and a[1] <= b[4] and b[2] <= a[5] and a[2] <= b[5]:
                pairs.append((min(i, j), max(i, j)))
    return sorted(pairs)


class _Faces:
    """One part's faces with a bounding box and a lower bound on distance from a sampled surface.

    The bound: every point of a face is within ``radius`` of one of its
    ``samples`` (the vertices of a tessellation whose triangles are cut down to
    ``_SAMPLE_MM``, or coarser on a large face, plus the tessellation's own deviation), so two faces whose
    nearest samples are farther apart than the contact reach plus both radii
    cannot be in contact, and need no exact distance. A face with no
    tessellation has no bound.
    """

    def __init__(self, shape, reach: float):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh

        BRepMesh_IncrementalMesh(shape, _DEFLECTION_MM, False, _ANGLE_RAD, False)
        self.faces = part_faces(shape)
        self.boxes = [_box(face, reach) for face in self.faces]
        self.bounds = [_sampled(face) for face in self.faces]


def _sampled(face):
    """``(KD-tree of samples, radius)`` of a face, or ``None`` when it has no tessellation."""
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from scipy.spatial import cKDTree

    location = TopLoc_Location()
    mesh = BRep_Tool.Triangulation_s(TopoDS.Face_s(face), location)
    if mesh is None or mesh.NbTriangles() == 0:
        return None
    move = location.Transformation()
    nodes = [mesh.Node(i).Transformed(move) for i in range(1, mesh.NbNodes() + 1)]
    points = np.array([(p.X(), p.Y(), p.Z()) for p in nodes])
    corners = np.array([[mesh.Triangle(i).Value(k) - 1 for k in (1, 2, 3)] for i in range(1, mesh.NbTriangles() + 1)])
    triangles = points[corners]
    # Cut to _SAMPLE_MM, or coarser on a big face so that it holds about _SAMPLES_PER_FACE samples.
    area = float(np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1).sum()) / 2
    limit = max(_SAMPLE_MM, (area / _SAMPLES_PER_FACE) ** 0.5)
    while len(triangles) < _MAX_TRIANGLES:
        lengths = np.linalg.norm(triangles - np.roll(triangles, -1, axis=1), axis=2)  # edge k joins corner k to k + 1
        longest = lengths.argmax(axis=1)
        split = lengths[np.arange(len(triangles)), longest] > limit
        if not split.any():
            break
        # Roll each triangle so its longest edge joins corners 0 and 1, then cut that edge in two.
        rolled = _rotate(triangles[split], longest[split])
        middle = (rolled[:, 0] + rolled[:, 1]) / 2
        halves = np.concatenate([
            np.stack([rolled[:, 0], middle, rolled[:, 2]], axis=1),
            np.stack([middle, rolled[:, 1], rolled[:, 2]], axis=1),
        ])
        triangles = np.concatenate([triangles[~split], halves])
    lengths = np.linalg.norm(triangles - np.roll(triangles, -1, axis=1), axis=2)
    # One sample per cell of half the cut size: a sample stands for the points within a cell's diagonal of it.
    cell = limit / 2
    _, first = np.unique(np.floor(triangles.reshape(-1, 3) / cell).astype(np.int64), axis=0, return_index=True)
    radius = float(lengths.max()) + cell * 3 ** 0.5 + 2 * _DEFLECTION_MM
    return cKDTree(triangles.reshape(-1, 3)[first]), radius


def _rotate(triangles, longest):
    """Each triangle with its corners rolled so corner ``longest`` comes first."""
    import numpy as np

    order = (np.arange(3)[None, :] + longest[:, None]) % 3
    return np.take_along_axis(triangles, order[:, :, None], axis=1)


def _too_far(a, b, reach: float) -> bool:
    """True when the sampled bounds prove two faces are farther apart than ``reach``."""
    if a is None or b is None:
        return False
    nearest, _ = a[0].query(b[0].data, k=1)
    return float(nearest.min()) - a[1] - b[1] > reach


def _distance(a, b):
    """The extrema between two shapes, or ``None`` when OpenCascade finds none."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    extrema = BRepExtrema_DistShapeShape(a, b)
    extrema.Perform()
    return extrema if extrema.IsDone() and extrema.NbSolution() > 0 else None


def part_gap(first: Part, second: Part) -> float | None:
    """The distance between two parts in mm (0 = touching), or ``None`` when the kernel finds none."""
    extrema = _distance(first.shape, second.shape)
    return None if extrema is None else float(extrema.Value())


def part_centre(part: Part) -> tuple[float, float, float]:
    """The centre of a part's bounding box, mm."""
    xmin, ymin, zmin, xmax, ymax, zmax = _box(part.shape, 0.0).Get()
    return ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)


def _overlap_area(face_a, face_b, extrema) -> float:
    """The area the two faces share once ``face_b`` is moved across the gap onto ``face_a``."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    if extrema.Value() > _TOUCHING_MM:
        move = gp_Trsf()
        move.SetTranslation(gp_Vec(extrema.PointOnShape2(1), extrema.PointOnShape1(1)))
        face_b = face_b.Moved(TopLoc_Location(move))
    common = BRepAlgoAPI_Common(face_a, face_b)
    if not common.IsDone():
        return 0.0
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(common.Shape(), props)
    return float(props.Mass())


def detect_contacts(parts: list[Part], tolerance_mm: float, *, log=None) -> list[Contact]:
    """Every pair of parts in face contact within ``tolerance_mm``, in part order.

    The gap is the smallest gap between faces in contact; the area is the sum
    of their common areas. Boxes first (a sweep, :func:`_close_pairs`), then each
    face pair's box and sampled bound, and only the faces left get the exact
    distance and area. ``log`` is told how many close pairs there are to check.
    """
    reach = tolerance_mm * (1 + 1e-6) + _TOUCHING_MM
    candidates = _close_pairs([_box(part.shape, reach) for part in parts])
    if log:
        log(f"checking {len(candidates)} close part pairs for touching faces")
    faces: dict[int, _Faces] = {}

    def faces_of(index: int) -> _Faces:
        if index not in faces:
            faces[index] = _Faces(parts[index].shape, reach)
        return faces[index]

    contacts = []
    for i, j in candidates:
        first, second = parts[i], parts[j]
        mine, theirs = faces_of(i), faces_of(j)
        area, gap = 0.0, None
        for face_a, box_a, bound_a in zip(mine.faces, mine.boxes, mine.bounds):
            for face_b, box_b, bound_b in zip(theirs.faces, theirs.boxes, theirs.bounds):
                if box_a.IsOut(box_b) or _too_far(bound_a, bound_b, reach):
                    continue
                extrema = _distance(face_a, face_b)
                if extrema is None or extrema.Value() > reach:
                    continue
                overlap = _overlap_area(face_a, face_b, extrema)
                if overlap > _MIN_AREA_MM2:
                    area += overlap
                    gap = extrema.Value() if gap is None else min(gap, extrema.Value())
        if gap is None:
            continue
        a, b = (first, second) if first.volume_mm3 <= second.volume_mm3 else (second, first)
        contacts.append(Contact(a=a.ref, b=b.ref, area_mm2=area, gap_mm=0.0 if gap <= _TOUCHING_MM else gap))
    return contacts


def _groups(count: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    """The parts joined by ``pairs``, directly or through others, as sorted groups."""
    root = list(range(count))

    def find(i: int) -> int:
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i

    for a, b in pairs:
        root[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def glue(shapes: list, bonded: list[tuple[int, int, float]], tolerance_mm: float) -> Glued:
    """Glue the shapes joined by ``bonded`` (``(part, part, gap_mm)``) into one compound.

    Each group of parts bonded to each other is fused on its own (fuzzy at the
    tolerance when a pair in it has a gap); parts in different groups only sit
    side by side in the compound and share nothing.
    """
    from OCP.BOPAlgo import BOPAlgo_Builder
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS_Compound
    from OCP.TopTools import TopTools_IndexedMapOfShape

    compound, maker = TopoDS_Compound(), BRep_Builder()
    maker.MakeCompound(compound)
    builder_of: dict[int, Any] = {}
    fuzzy_mm = 0.0
    for group in _groups(len(shapes), [(a, b) for a, b, _ in bonded]):
        if len(group) == 1:
            maker.Add(compound, shapes[group[0]])
            continue
        builder = BOPAlgo_Builder()
        for index in group:
            builder.AddArgument(shapes[index])
        if any(gap > _TOUCHING_MM for a, b, gap in bonded if a in group):
            builder.SetFuzzyValue(tolerance_mm)
            fuzzy_mm = tolerance_mm
        builder.Perform()
        if builder.HasErrors():
            names = ", ".join(str(index) for index in group)
            raise RuntimeError(f"could not glue parts {names} into one shape")
        maker.Add(compound, builder.Shape())
        for index in group:
            builder_of[index] = builder

    def images(index: int, shape) -> list:
        builder = builder_of.get(index)
        if builder is None:
            return [shape]
        if builder.IsDeleted(shape):
            return []
        modified = builder.Modified(shape)
        return list(modified) if modified.Size() else [shape]

    solids = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(compound, TopAbs_SOLID, solids)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(compound, TopAbs_FACE, faces)

    solid_part = [-1] * solids.Extent()
    face_images = []
    for index, shape in enumerate(shapes):
        own = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_SOLID, own)
        for k in range(1, own.Extent() + 1):
            for image in images(index, own.FindKey(k)):
                found = solids.FindIndex(image)
                if found == 0:
                    raise RuntimeError(f"part {index}'s solid {k} is missing from the glued shape")
                solid_part[found - 1] = index
        per_face = []
        for ordinal, face in enumerate(part_faces(shape), 1):
            found = [faces.FindIndex(image) for image in images(index, face)]
            if not found or 0 in found:
                raise RuntimeError(f"part {index}'s face {ordinal} did not survive gluing")
            per_face.append(found)
        face_images.append(per_face)
    if -1 in solid_part:
        raise RuntimeError("the glued shape holds a solid no part made")
    return Glued(shape=compound, solid_part=solid_part, face_images=face_images, fuzzy_mm=fuzzy_mm)
