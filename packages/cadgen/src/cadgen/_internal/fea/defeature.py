"""Leaving small features out of the mesh: the ladder's ``defeature`` rung.

A fillet, a chamfer or a hole much smaller than the elements around it makes
the mesher refine to its own size, however coarse the study asked for. Far
from every load, fixture and check such a feature barely moves the answer, so
the ladder may remove it for meshing with OpenCascade's
``BRepAlgoAPI_Defeaturing`` (the faces grow back over it). Named faces are
never removed, and nothing within three element sizes of one is. The faces
that remain keep their cadgen ordinals: each face of the defeatured shape is
traced back through the operation's history to the face it came from
(:class:`Prepared`), so a study's ``#o1.f17`` means the same face on the
simplified part. OCP imports live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadgen._internal.fea.fit import FaceInfo, Geometry

__all__ = ["Feature", "Prepared", "defeature", "describe", "small_features"]

#: The size and distance rules, in coarse elements (fit.SMALL_FEATURE_ELEMENTS, fit.FAR_ELEMENTS).
SMALL, FAR = 2.0, 3.0


@dataclass
class Prepared:
    """A shape to mesh in place of the occurrence's, each face traced to the occurrence's ordinal it came from."""

    shape: Any
    #: Per face of ``shape`` (cadgen order, index 0 = face 1): the occurrence's ordinal, or a symmetry plane's
    #: own ordinal (:data:`cadgen._internal.fea.symmetry.PLANE_ORDINAL`), or 0 for a face of neither.
    origin: list[int]
    #: The symmetry planes cut (:class:`cadgen._internal.fea.symmetry.Plane`), in the order they were cut.
    planes: list = field(default_factory=list)


@dataclass(frozen=True)
class Feature:
    """One small feature: its kind ("fillet", "chamfer", "hole") and the faces that make it."""

    kind: str
    faces: "tuple[FaceInfo, ...]"
    size_mm: float


def _face_map(shape):
    from cadgen._internal.entity_ordinals import entity_map

    return entity_map(shape, "face")


def _u_span(face) -> float:
    from OCP.BRepTools import BRepTools

    u0, u1, _, _ = BRepTools.UVBounds_s(face)
    return abs(u1 - u0)


def _is_hole(face) -> bool:
    """A full cylinder with the material outside it: its normal points at its axis."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.TopAbs import TopAbs_REVERSED

    if _u_span(face) < 2 * math.pi - 1e-3:
        return False
    adaptor = BRepAdaptor_Surface(face)
    u0, u1, v0, v1 = adaptor.FirstUParameter(), adaptor.LastUParameter(), adaptor.FirstVParameter(), adaptor.LastVParameter()
    props = BRepLProp_SLProps(adaptor, 0.5 * (u0 + u1), 0.5 * (v0 + v1), 1, 1e-6)
    if not props.IsNormalDefined():
        return False
    normal = props.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    point = props.Value()
    axis = adaptor.Cylinder().Axis()
    origin, direction = axis.Location(), axis.Direction()
    rel = (point.X() - origin.X(), point.Y() - origin.Y(), point.Z() - origin.Z())
    along = rel[0] * direction.X() + rel[1] * direction.Y() + rel[2] * direction.Z()
    radial = (rel[0] - along * direction.X(), rel[1] - along * direction.Y(), rel[2] - along * direction.Z())
    return radial[0] * normal.X() + radial[1] * normal.Y() + radial[2] * normal.Z() < 0


def _plane_normal(face):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_Plane:
        return None
    d = adaptor.Plane().Axis().Direction()
    return (d.X(), d.Y(), d.Z())


def _neighbours(shape, faces) -> dict[int, set[int]]:
    """Face ordinal -> the ordinals of the faces sharing an edge with it."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    edges = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edges)
    near: dict[int, set[int]] = {}
    for k in range(1, edges.Extent() + 1):
        owners = [faces.FindIndex(f) for f in edges.FindFromIndex(k)]
        for a in owners:
            for b in owners:
                if a != b:
                    near.setdefault(a, set()).add(b)
    return near


def _distance(a, b) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    dist = BRepExtrema_DistShapeShape(a, b)
    return float(dist.Value()) if dist.IsDone() else 0.0


def small_features(geometry: "Geometry", size_mm: float, named: set[int]) -> list[Feature]:
    """The fillets, chamfers and holes under two elements of ``size_mm`` that lie more than three element
    sizes from every face in ``named`` (ordinals). Named faces are never among them."""
    shape = geometry.shape
    faces = _face_map(shape)
    near = _neighbours(shape, faces)
    info = {face.ordinal: face for face in geometry.faces}
    small = SMALL * size_mm
    candidates: list[Feature] = []
    for ordinal, face_info in info.items():
        if ordinal in named:
            continue
        face = _as_face(faces.FindKey(ordinal))
        kind = None
        if face_info.kind == "cylinder":
            if _is_hole(face):
                kind = "hole" if 2 * face_info.size_mm < small else None
            elif _u_span(face) < 2 * math.pi - 1e-3 and face_info.size_mm < small:
                kind = "fillet"
        elif face_info.kind in ("torus", "sphere") and face_info.size_mm < small:
            kind = "fillet"
        elif face_info.kind == "plane" and face_info.size_mm < small:
            normal = _plane_normal(face)
            slanted = 0
            for other in near.get(ordinal, ()):
                other_normal = _plane_normal(_as_face(faces.FindKey(other)))
                if normal is None or other_normal is None:
                    continue
                angle = math.degrees(math.acos(min(1.0, abs(sum(a * b for a, b in zip(normal, other_normal))))))
                if 10.0 < angle < 80.0:
                    slanted += 1
            kind = "chamfer" if slanted >= 2 else None
        if kind is not None:
            candidates.append(Feature(kind, (face_info,), face_info.size_mm))
    if not candidates:
        return []
    named_shapes = [faces.FindKey(ordinal) for ordinal in named if 1 <= ordinal <= faces.Extent()]
    far = FAR * size_mm
    kept = [
        feature for feature in candidates
        if all(_distance(faces.FindKey(face.ordinal), other) > far for face in feature.faces for other in named_shapes)
    ]
    return kept


def _as_face(shape):
    from OCP.TopoDS import TopoDS

    return TopoDS.Face_s(shape)


def defeature(geometry: "Geometry", features: list[Feature], prepared: Prepared | None = None) -> Prepared | None:
    """The part with ``features`` removed, each remaining face traced to its ordinal; ``None`` when
    OpenCascade cannot remove them (the rung then does not apply)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
    from OCP.BRepCheck import BRepCheck_Analyzer

    shape = geometry.shape
    faces = _face_map(shape)
    tool = BRepAlgoAPI_Defeaturing()
    tool.SetShape(shape)
    tool.SetRunParallel(False)
    tool.SetToFillHistory(True)
    for feature in features:
        for face in feature.faces:
            tool.AddFaceToRemove(faces.FindKey(face.ordinal))
    try:
        tool.Build()
    except Exception:  # noqa: BLE001 - a kernel failure means the rung does not apply
        return None
    if not tool.IsDone() or getattr(tool, "HasErrors", lambda: False)():
        return None
    result = tool.Shape()
    if result is None or result.IsNull() or not BRepCheck_Analyzer(result).IsValid():
        return None
    return Prepared(result, trace(tool, shape, result))


def trace(operation, before, after, origin_before: list[int] | None = None) -> list[int]:
    """Per face of ``after``: the ordinal (through ``origin_before``) of the face of ``before`` it came from, else 0."""
    from OCP.TopTools import TopTools_ListOfShape

    old = _face_map(before)
    new = _face_map(after)
    origin = [0] * new.Extent()
    for k in range(1, old.Extent() + 1):
        face = old.FindKey(k)
        source = k if origin_before is None else origin_before[k - 1]
        images: list = []
        if operation is not None:
            modified = operation.Modified(face)
            if isinstance(modified, TopTools_ListOfShape):
                images = list(modified)
        if not images and new.Contains(face):
            images = [face]
        for image in images:
            index = new.FindIndex(image)
            if index > 0 and origin[index - 1] == 0:
                origin[index - 1] = source
    return origin


def describe(features: list[Feature]) -> str:
    """"6 small fillets", "2 small holes and a small chamfer"."""
    counts: dict[str, int] = {}
    for feature in features:
        counts[feature.kind] = counts.get(feature.kind, 0) + 1
    parts = [f"{n} small {kind}s" if n > 1 else f"a small {kind}" for kind, n in sorted(counts.items())]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
