"""An assembly's parts, the faces where they touch, and the parts glued into one shape.

A part is one leaf occurrence of the STEP scene, placed in world coordinates.
Two parts are in contact when a face of one lies on a face of the other, or
within the contact tolerance of it, over an area: a bounding-box prefilter
enlarged by the tolerance, then ``BRepExtrema_DistShapeShape`` for the gap,
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

__all__ = ["Contact", "Glued", "Part", "detect_contacts", "glue", "list_parts", "part_faces"]

# OpenCascade's own confusion distance: a gap below it is touching.
_TOUCHING_MM = 1e-7
# Overlap below this is an edge or a point, not a face in contact.
_MIN_AREA_MM2 = 1e-6


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
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    box.Enlarge(enlarge)
    return box


def _distance(a, b):
    """The extrema between two shapes, or ``None`` when OpenCascade finds none."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    extrema = BRepExtrema_DistShapeShape(a, b)
    extrema.Perform()
    return extrema if extrema.IsDone() and extrema.NbSolution() > 0 else None


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


def detect_contacts(parts: list[Part], tolerance_mm: float) -> list[Contact]:
    """Every pair of parts in face contact within ``tolerance_mm``, in part order.

    The gap is the smallest gap between faces in contact; the area is the sum
    of their common areas.
    """
    reach = tolerance_mm * (1 + 1e-6) + _TOUCHING_MM
    boxes = [_box(part.shape, reach) for part in parts]
    faces = [[(face, _box(face, reach)) for face in part_faces(part.shape)] for part in parts]
    contacts = []
    for i, first in enumerate(parts):
        for j in range(i + 1, len(parts)):
            second = parts[j]
            if boxes[i].IsOut(boxes[j]):
                continue
            extrema = _distance(first.shape, second.shape)
            if extrema is None or extrema.Value() > reach:
                continue
            area, gap = 0.0, None
            for face_a, box_a in faces[i]:
                for face_b, box_b in faces[j]:
                    if box_a.IsOut(box_b):
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
