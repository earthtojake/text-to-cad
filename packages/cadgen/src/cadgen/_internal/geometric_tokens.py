"""Geometric tokens: the names of the elements no construction names.

An element a model's run made is named by its lineage (``kernel_trace``). An
element with none -- every face, edge and vertex of an imported file, and those
a model took from a shape no feature of its run made -- is named by its
**geometric token**: ``f:``, ``e:`` or ``v:`` and twelve hexadecimal characters,
a hash of the element's geometry within its body under one scheme string,
``GEOMETRIC_TOKEN_SCHEME``, and of nothing positional, so the token survives a
STEP round trip of the body and whatever order OCCT lists the elements in. This
is the fallback matcher, measured on demand -- where a part's display data is
derived (``cadgen.store.parts``, in the build pool), and where a reader resolves
a ref in this form against a body its lineage names (``read_scene``, ``store
where``) -- and remembered by the component's bytes (``component_tokens``):
nothing on the way from a model's run to its record measures one (README law 20).

Rounding is relative to the body's extent: the quantum is the power of two at
or below ``RELATIVE_QUANTUM`` times the diagonal of the body's tight box (a
power of two so the quantum itself is exact and moves only when the extent
crosses one).

What is read, and why:

- A face's signature is its surface class, its tight box rounded and its
  oriented normal at its parametric middle rounded to quarters (an orientation
  signal that tells the coincident faces of two solids apart). Not its centroid
  and not its area: both are integrals over the trim, and the STEP translation
  moves them by more than the quantum on faces whose boundary it approximates
  again, where the box's extremes survive like vertices do.
- An edge's signature is its curve class, its rounded end points as a sorted
  pair, and its rounded length. A vertex's is its rounded point.
- A surface or curve class is the kernel's type with the pairs the STEP
  translation exchanges folded together: a Bezier is read as a B-spline, a
  torus can be read as a surface of revolution.
- Two elements of one body with equal signatures (the coincident faces of two
  solids in a compound, two vertices at one point) are told apart
  deterministically: ordered by their exact values, each after the first
  hashes its rank as well.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

__all__ = ["GEOMETRIC_TOKEN_SCHEME", "RELATIVE_QUANTUM", "TOKEN_RE", "component_tokens", "element_names",
           "element_tokens", "quantum_for_extent"]

# The ONLY version on a geometric token. Bump it when the same shape must be
# named differently (what a signature reads, or how it rounds, changes), and
# bump cadgen.store.parts.PART_VERSION with it (STORE.md §2).
GEOMETRIC_TOKEN_SCHEME = "cadgen-geometric-token-v1"
# The rounding quantum as a fraction of the body's extent, before it is taken
# to a power of two: 2**-12 is 2.4e-4, half the display chord tolerance
# (tessellation_policy.DISPLAY_TESSELLATION, 5e-4 of the extent).
RELATIVE_QUANTUM = 2.0 ** -12
# The normal of a face is rounded to this many steps per unit: an orientation
# signal, telling the coincident faces of two solids apart, not a measurement.
_NORMAL_STEPS = 4
_HEX = 12
TOKEN_RE = re.compile(r"^[fev]:[0-9a-f]{12}$")
# Types the STEP translation exchanges read as one class.
_TYPE_CLASSES = {
    "beziersurface": "spline", "bsplinesurface": "spline",
    "beziercurve": "spline", "bsplinecurve": "spline",
    "torus": "revolution", "surfaceofrevolution": "revolution",
}


def quantum_for_extent(extent: float) -> float:
    """The rounding quantum of a body whose tight box has diagonal ``extent``:
    the power of two at or below ``RELATIVE_QUANTUM * extent``. A body with no
    extent (a vertex, a point-like shape) rounds at 2**-40."""
    scaled = float(extent) * RELATIVE_QUANTUM
    if not math.isfinite(scaled) or scaled <= 0.0:
        return 2.0 ** -40
    return 2.0 ** math.floor(math.log2(scaled))


def _digest(kind: str, material: Any) -> str:
    payload = json.dumps(material, separators=(",", ":"), sort_keys=False, allow_nan=False)
    return hashlib.sha256(f"{GEOMETRIC_TOKEN_SCHEME}\0{kind}\0{payload}".encode()).hexdigest()


def _rounded(value: float, quantum: float) -> int:
    scaled = value / quantum
    if not math.isfinite(scaled):
        raise ValueError("geometry coordinate is not finite")
    return int(round(scaled))


def _enum(value: Any, prefix: str) -> str:
    name = getattr(value, "name", str(value))
    name = name[len(prefix):].lower() if name.startswith(prefix) else name.lower()
    return _TYPE_CLASSES.get(name, name)


def _face_facts(face: Any, metrics: dict[str, Any]) -> dict[str, Any]:
    """The face's signature material: its surface class, its tight box and area as
    ``topology_extract.component_metrics`` measured them, and its normal at its parametric
    middle."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Pnt, gp_Vec

    if "area" not in metrics:
        raise ValueError("a face of the component has no measurable area")
    normal = [0, 0, 0]
    try:
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
        point, vector = gp_Pnt(), gp_Vec()
        BRepGProp_Face(face).Normal((umin + umax) / 2.0, (vmin + vmax) / 2.0, point, vector)
        length = vector.Magnitude()
        if math.isfinite(length) and length > 1e-12:
            normal = [int(round(_NORMAL_STEPS * c / length)) for c in (vector.X(), vector.Y(), vector.Z())]
    except Exception:  # noqa: BLE001 - a face whose normal cannot be read is named without one
        normal = [0, 0, 0]
    box = metrics.get("bbox")
    return {
        "type": _enum(BRepAdaptor_Surface(face, False).GetType(), "GeomAbs_"),
        "box": tuple(float(value) for value in box) if box is not None else None,
        "normal": normal,
        "area": float(metrics["area"]),
    }


def _edge_facts(edge: Any, metrics: dict[str, Any]) -> dict[str, Any]:
    """The edge's signature material: its curve class, its end points, and its centre
    and length as ``topology_extract.component_metrics`` measured them."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    degenerate = BRep_Tool.Degenerated_s(edge)
    first, last = _edge_ends(edge)
    if degenerate:
        centre, length = (first.X(), first.Y(), first.Z()), 0.0
    else:
        if "length" not in metrics:
            raise ValueError("an edge of the component has no measurable length")
        centre, length = tuple(float(value) for value in metrics["center"]), float(metrics["length"])
    return {
        "type": "degenerate" if degenerate else _enum(BRepAdaptor_Curve(edge).GetType(), "GeomAbs_"),
        "ends": sorted([(first.X(), first.Y(), first.Z()), (last.X(), last.Y(), last.Z())]),
        "centre": centre,
        "length": length,
    }


def _edge_ends(edge: Any) -> tuple[Any, Any]:
    """The edge's end points: its vertices', or, for an edge the kernel built without
    vertices (a closed edge of a loft or sweep), the ends of its curve."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopExp import TopExp

    first, last = TopExp.FirstVertex_s(edge, True), TopExp.LastVertex_s(edge, True)
    if not first.IsNull() and not last.IsNull():
        return BRep_Tool.Pnt_s(first), BRep_Tool.Pnt_s(last)
    curve = BRepAdaptor_Curve(edge)
    return curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())


def _point(point: tuple[float, ...], quantum: float) -> list[int]:
    return [_rounded(point[0], quantum), _rounded(point[1], quantum), _rounded(point[2], quantum)]


def _tokens(prefix: str, signatures: list[tuple[list, tuple]]) -> list[str]:
    """One token per element, in the elements' order. Equal signatures are
    ranked by their exact values (then by their position, for elements whose
    exact geometry coincides too) and each rank after the first is hashed in."""
    by_signature: dict[str, list[int]] = {}
    keys = [json.dumps(signature, separators=(",", ":")) for signature, _exact in signatures]
    for index, key in enumerate(keys):
        by_signature.setdefault(key, []).append(index)
    tokens = [""] * len(signatures)
    for members in by_signature.values():
        if len(members) == 1:
            tokens[members[0]] = f"{prefix}:{_digest(prefix, signatures[members[0]][0])[:_HEX]}"
            continue
        ranked = sorted(members, key=lambda index: (signatures[index][1], index))
        for rank, index in enumerate(ranked):
            material = signatures[index][0] if rank == 0 else [signatures[index][0], rank]
            tokens[index] = f"{prefix}:{_digest(prefix, material)[:_HEX]}"
    return tokens


def _maps(shape: Any):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    maps = []
    for kind in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
        found = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, kind, found)
        maps.append(found)
    return maps


def _extent(face_boxes: list[tuple[float, ...] | None], points: list[tuple[float, ...]]) -> float:
    """The diagonal of the union of the faces' tight boxes and the vertex points."""
    low = [math.inf] * 3
    high = [-math.inf] * 3
    for box in face_boxes:
        if box is None:
            continue
        for axis in range(3):
            low[axis] = min(low[axis], box[axis])
            high[axis] = max(high[axis], box[axis + 3])
    for point in points:
        for axis in range(3):
            low[axis] = min(low[axis], point[axis])
            high[axis] = max(high[axis], point[axis])
    if any(not math.isfinite(v) for v in (*low, *high)):
        return 0.0
    return math.sqrt(sum((high[axis] - low[axis]) ** 2 for axis in range(3)))


def element_tokens(shape: Any, *, brep: str | None = None) -> dict[str, list[str]]:
    """The geometric token of every face, edge and vertex of one unlocated
    component shape (a ``TopoDS_Shape``): ``{"faces": [...], "edges": [...],
    "vertices": [...]}``, in ``TopExp.MapShapes_s`` order so a caller joins them to
    the topology facts and the mesh by ordinal. ``brep``, the component's BREP
    object hash when the caller has it, lets the faces' and edges' exact metrics be
    the ones this process already measured (``topology_extract.component_metrics``)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    from cadgen._internal.topology_extract import component_metrics

    metrics = component_metrics(shape, brep=brep, face_boxes=True)
    faces, edges, vertices = _maps(shape)
    face_facts = [_face_facts(TopoDS.Face_s(faces.FindKey(i)), metrics["faces"][i - 1])
                  for i in range(1, faces.Extent() + 1)]
    edge_facts = [_edge_facts(TopoDS.Edge_s(edges.FindKey(i)), metrics["edges"][i - 1])
                  for i in range(1, edges.Extent() + 1)]
    points = []
    for i in range(1, vertices.Extent() + 1):
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i)))
        points.append((point.X(), point.Y(), point.Z()))
    quantum = quantum_for_extent(_extent([facts["box"] for facts in face_facts], points))

    face_signatures = [
        ([facts["type"], [_rounded(v, quantum) for v in facts["box"]] if facts["box"] else None, facts["normal"]],
         (*(facts["box"] or ()), facts["area"]))
        for facts in face_facts
    ]
    edge_signatures = [
        ([facts["type"], [_point(facts["ends"][0], quantum), _point(facts["ends"][1], quantum)],
          _rounded(facts["length"], quantum)],
         (*facts["centre"], facts["length"]))
        for facts in edge_facts
    ]
    vertex_signatures = [(_point(point, quantum), point) for point in points]
    return {
        "faces": _tokens("f", face_signatures),
        "edges": _tokens("e", edge_signatures),
        "vertices": _tokens("v", vertex_signatures),
    }


def component_tokens(shape: Any, component: tuple[str, str] | None = None) -> dict[str, list[str]]:
    """:func:`element_tokens` of ``shape``, remembered by the stored component it was
    decoded from -- ``component``, its codec and BREP object -- in the store's
    ``index/bounds`` (``bounds.cached_tokens``), so a body is measured once wherever
    its tokens are asked for; measured here, unremembered, when ``component`` is None."""
    if component is None:
        return element_tokens(shape)
    from cadgen.store.bounds import cached_tokens

    codec, brep = component
    return cached_tokens(codec, brep, lambda: element_tokens(shape, brep=brep))


def element_names(lineage: dict[str, Any] | None, shape: Any, *,
                  component: tuple[str, str] | None = None) -> dict[str, list[str]]:
    """Every face's, edge's and vertex's name in ``shape`` (one unlocated component), by
    ordinal: the name ``lineage`` gives it (``component_package.read_lineage``), and the
    geometric token of each element it does not name -- measured only when one has none
    (:func:`component_tokens`, remembered by ``component`` when given)."""
    plurals = ("faces", "edges", "vertices")
    names = {plural: list(lineage[plural]) if lineage is not None else None for plural in plurals}
    if all(listed is not None and None not in listed for listed in names.values()):
        return names
    tokens = component_tokens(shape, component)
    for plural, listed in names.items():
        if listed is None:
            names[plural] = tokens[plural]
            continue
        if len(listed) != len(tokens[plural]):
            raise ValueError(f"the lineage does not describe this shape: it names {len(listed)} {plural}, "
                             f"the shape has {len(tokens[plural])}")
        names[plural] = [token if name is None else name for name, token in zip(listed, tokens[plural])]
    return names
