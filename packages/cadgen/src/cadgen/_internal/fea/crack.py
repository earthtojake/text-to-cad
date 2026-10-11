"""A crack in a part, for linear-elastic fracture mechanics: what the ``fracture`` analysis cuts, meshes and measures.

The crack is a flat region in a plane, described by the study (:class:`CrackSpec`):
an edge crack (straight across the section, ``size_mm`` deep from a face), a
through crack (``2 × size_mm`` long, through the thickness of the face it
crosses), a semi-elliptical surface crack (``size_mm`` deep, ``length_mm`` long
on its face) or an embedded elliptical one (semi-axes ``size_mm`` and
``length_mm / 2``). It goes into the part in three steps:

1. **Cut** (:func:`cut`): OpenCascade's splitter cuts the part along the whole
   crack plane with two faces, the crack itself and the rest of the plane (the
   ligament), so the part becomes solids that share their faces on that plane
   and the crack's front is an edge between the two. Each face of the result is
   traced to the part's own ordinal (:func:`cadgen._internal.fea.defeature.trace`);
   the crack's faces get :data:`CRACK_ORDINAL`, the ligament's
   :data:`LIGAMENT_ORDINAL`. The front is meshed fine: :func:`front_points`
   gives the mesher local sizes in a tube around it.
2. **Open** (:func:`open_crack`): on the conforming mesh, every node of the
   crack's faces except the front's is duplicated, and the elements on the far
   side of the plane take the copies, so the two faces of the crack move apart.
   The ligament's triangles are interior and dropped; the crack's become two
   traction-free surfaces. The front is read off the mesh as chains of nodes
   (:class:`Front`), each point with its own crack-extension direction.
3. **Measure** (:func:`stress_intensity`): the domain interaction integral
   (Shih and Asaro; Moran and Shih) over a tube of elements around the front,
   with the Williams near-tip fields as the auxiliary states, separates K_I,
   K_II and K_III at stations along each front, and the domain J-integral gives
   the energy release rate beside them. The integral is taken over two domain
   sizes; how far K moves between them is the accuracy it states.

The near-tip elements are ordinary quadratic tetrahedra, not quarter-point
ones: netgen's tetrahedra around a front are not the collapsed bricks a
quarter-point element needs, and moving the mid-edge nodes of arbitrary tets
spoils their mapping, so the front is meshed fine instead (a "spider web" of
about :data:`ELEMENTS_ACROSS` elements across the J domain), and the domain
integral, which is insensitive to the near-tip error, reads K from it. The
auxiliary fields are the plane-strain ones: K at a point where the front meets a
free surface is the plane-strain equivalent (the 3D corner field there is not
the square-root one). Curvature terms of a curved front are left out (the
integral is exact for a straight front and within a few percent for an ellipse
whose front is meshed fine).

:func:`paris_life` integrates Paris's law da/dN = C (ΔK)^m from the crack's
size to the size where K reaches the toughness, holding the crack's geometry
factor Y = K / (σ √(πa)) at the value solved. Stdlib at import (the parse);
numeric and OCP work inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cadgen._internal.fea.defeature import Prepared

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "CRACK_KEYS", "CRACK_ORDINAL", "CrackGeometry", "CrackSpec", "CrackedPrepared", "ELEMENTS_ACROSS", "Front", "FrontK",
    "KINDS", "LIGAMENT_ORDINAL", "PLANES", "cut", "domain_radius", "front_points", "front_polylines", "join_fronts", "mirror_front",
    "open_crack", "paris_life", "paris_life_closed_form", "parse_crack", "resolve", "stress_intensity", "unfold_fronts",
]

#: The ordinal of the crack's faces and of the rest of its plane (the ligament) in a cut shape: no part has that many faces.
CRACK_ORDINAL = 2_000_000
LIGAMENT_ORDINAL = 2_000_001
KINDS = ("edge", "through", "surface", "embedded")
CRACK_KEYS = frozenset({"kind", "face", "at_mm", "normal", "plane", "size_mm", "length_mm", "along"})
#: A plane named by its two axes: its normal.
PLANES = {"xy": (0.0, 0.0, 1.0), "yz": (1.0, 0.0, 0.0), "xz": (0.0, 1.0, 0.0), "zx": (0.0, 1.0, 0.0),
          "yx": (0.0, 0.0, 1.0), "zy": (1.0, 0.0, 0.0)}
#: The J domain's radius as a share of the crack's smaller size (its depth, its half length).
DOMAIN_SHARE = 0.4
#: Elements across the J domain's radius at the front (the front's mesh size is the radius over this).
ELEMENTS_ACROSS = 6.0
#: The J domain's inner plateau (q = 1) as a share of its radius: the near-tip elements carry no weight.
PLATEAU = 1.0 / 3.0
#: The second, smaller domain K is also read on, as a share of the first: their difference is the accuracy stated.
SECOND_DOMAIN = 0.6
#: The fewest elements across the J domain the front may be meshed with when a budget asks for coarser.
MIN_ELEMENTS_ACROSS = 3.0
MM_PER_M = 1000.0


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def _number(value: Any, where: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{where}: expected a number, got {_json(value)}")
    if positive and not value > 0:
        raise ValueError(f"{where}: must be > 0, got {value}")
    return float(value)


def _vector(value: Any, where: str, words: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{where}: {words}, as [x, y, z]")
    out = tuple(_number(c, where) for c in value)
    return out  # type: ignore[return-value]


def _unit(vector: tuple[float, float, float], where: str) -> tuple[float, float, float]:
    size = math.sqrt(sum(c * c for c in vector))
    if not size > 0:
        raise ValueError(f"{where}: the direction is zero")
    return tuple(c / size for c in vector)  # type: ignore[return-value]


@dataclass(frozen=True)
class CrackSpec:
    """The crack as the study describes it (``crack``), checked; the part's geometry resolves it (:func:`resolve`)."""

    kind: str
    #: The face the crack opens from (edge, surface) or crosses (through); ``None`` for an embedded crack.
    face: str | None
    #: A point on the crack's mouth (edge, surface), its centre (through, embedded), mm.
    at: tuple[float, float, float]
    #: The crack plane's unit normal: the direction its faces open.
    normal: tuple[float, float, float]
    #: Depth (edge, surface), half length (through) or semi-axis (embedded), mm.
    size_mm: float
    #: The surface crack's length on its face (2c), or the embedded crack's other axis (2c); ``None`` for 2 × size.
    length_mm: float | None = None
    #: The through crack's length direction, or the embedded crack's ``length_mm`` axis; ``None`` for the default.
    along: tuple[float, float, float] | None = None

    def as_dict(self) -> dict:
        out: dict = {"kind": self.kind, "face": self.face, "at_mm": list(self.at), "normal": [round(c, 9) for c in self.normal],
                     "size_mm": self.size_mm}
        if self.length_mm is not None:
            out["length_mm"] = self.length_mm
        if self.along is not None:
            out["along"] = [round(c, 9) for c in self.along]
        return out


def parse_crack(raw: Any, where: str = "crack") -> CrackSpec:
    """The study's ``crack`` block, checked (stdlib). A ValueError names the field and says what to give."""
    example = '{"kind": "edge", "face": "#o1.f4", "at_mm": [0, 0, 5], "normal": [0, 1, 0], "size_mm": 2}'
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: describe the crack, like {example}")
    unknown = set(raw) - CRACK_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a crack takes {sorted(CRACK_KEYS)}")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError(f"{where}.kind: {_json(kind)} is not one of {list(KINDS)} (edge: straight across the section from a "
                         "face; through: through the thickness; surface: a half-ellipse on a face; embedded: inside)")
    if "size_mm" not in raw:
        words = {"edge": "its depth from the face", "surface": "its depth from the face", "through": "half its length",
                 "embedded": "its radius (the semi-axis across length_mm)"}[kind]
        raise ValueError(f"{where}.size_mm: the crack's size, {words}, in mm")
    size = _number(raw["size_mm"], f"{where}.size_mm", positive=True)
    if ("normal" in raw) == ("plane" in raw):
        raise ValueError(f'{where}: give the crack plane as "normal" ([x, y, z], the way its faces open) or "plane" '
                         f'({", ".join(sorted(set(PLANES)))}), exactly one')
    if "plane" in raw:
        if raw["plane"] not in PLANES:
            raise ValueError(f"{where}.plane: {_json(raw['plane'])} is not one of {sorted(set(PLANES))}")
        normal = PLANES[raw["plane"]]
    else:
        normal = _unit(_vector(raw["normal"], f"{where}.normal", "the crack plane's normal"), f"{where}.normal")
    if "at_mm" not in raw:
        words = "the centre of the crack" if kind in ("through", "embedded") else "a point on the face where the crack opens"
        raise ValueError(f"{where}.at_mm: {words}, as [x, y, z] in mm")
    at = _vector(raw["at_mm"], f"{where}.at_mm", "the crack's point")
    face = raw.get("face")
    if kind == "embedded":
        if face is not None:
            raise ValueError(f"{where}.face: an embedded crack opens from no face; leave face out (at_mm is its centre)")
    elif not isinstance(face, str) or not face.strip():
        words = "the face the crack crosses (its thickness direction)" if kind == "through" else "the face the crack opens from"
        raise ValueError(f'{where}.face: {words}, like "#o1.f4"')
    length = None
    if "length_mm" in raw:
        if kind not in ("surface", "embedded"):
            raise ValueError(f"{where}.length_mm: goes with a surface or embedded crack; an {kind} crack's size is size_mm alone")
        length = _number(raw["length_mm"], f"{where}.length_mm", positive=True)
    along = None
    if "along" in raw:
        if kind not in ("through", "embedded"):
            raise ValueError(f"{where}.along: goes with a through or embedded crack (the direction of its length)")
        along = _unit(_vector(raw["along"], f"{where}.along", "the crack's length direction"), f"{where}.along")
        if abs(sum(a * b for a, b in zip(along, normal))) > 1e-6:
            raise ValueError(f"{where}.along: must lie in the crack plane (perpendicular to its normal)")
    return CrackSpec(kind, face.strip() if isinstance(face, str) else None, at, normal, size, length, along)


# -- geometry -----------------------------------------------------------------------------------------


@dataclass
class CrackGeometry:
    """The crack in the part's coordinates: its plane, in-plane axes and size, ready to cut and to measure."""

    spec: CrackSpec
    #: The crack plane passes through ``at``; ``n`` its unit normal (the "+" side is along it).
    at: Any
    n: Any
    #: In-plane unit axes: ``d`` into the part (edge, surface: from the face; through: along its length), ``t = n × d``.
    d: Any
    t: Any
    #: Semi-axes along d and t (edge: depth a and unbounded; through: half length a and unbounded).
    a: float
    c: float
    #: How far the tools reach: well past the part.
    reach: float

    @property
    def kind(self) -> str:
        return self.spec.kind

    @property
    def size(self) -> float:
        """The crack's smaller size: what its J domain and front mesh scale with."""
        return min(self.a, self.c) if self.kind in ("surface", "embedded") else self.a


def _face_normal(face, point) -> tuple[float, float, float] | None:
    """The face's outward unit normal at the point nearest ``point``."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_REVERSED

    surface = BRep_Tool.Surface_s(face)
    projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), surface)
    if projector.NbPoints() == 0:
        return None
    u, v = projector.LowerDistanceParameters()
    props = BRepLProp_SLProps(BRepAdaptor_Surface(face), u, v, 1, 1e-7)
    if not props.IsNormalDefined():
        return None
    normal = props.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    return (normal.X(), normal.Y(), normal.Z())


def _nearest_on(shape, point) -> tuple[tuple[float, float, float], float]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    dist = BRepExtrema_DistShapeShape(vertex, shape)
    if not dist.IsDone() or dist.NbSolution() == 0:
        return tuple(point), math.inf  # type: ignore[return-value]
    p = dist.PointOnShape2(1)
    return (p.X(), p.Y(), p.Z()), float(dist.Value())


def _inside(shape, point, tolerance: float) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    classifier = BRepClass3d_SolidClassifier(shape, gp_Pnt(*point), tolerance)
    return classifier.State() == TopAbs_IN


def _diagonal(shape) -> float:
    from cadgen._internal.fea.mesh import shape_diagonal

    return shape_diagonal(shape)


def resolve(spec: CrackSpec, shape, face=None, face_ref: str | None = None) -> CrackGeometry:
    """The crack on the part ``shape`` (OCP), ``face`` the OCP face ``spec.face`` names. A ValueError says
    in a sentence what is wrong with where the crack is."""
    import numpy as np

    n = np.array(spec.normal, dtype=float)
    diagonal = _diagonal(shape)
    reach = 4.0 * max(diagonal, spec.size_mm, 1.0)
    at = np.array(spec.at, dtype=float)
    a = spec.size_mm
    name = face_ref or spec.face
    if spec.kind in ("edge", "surface", "through"):
        snapped, gap = _nearest_on(face, spec.at)
        if spec.kind != "through":
            if gap > max(0.05 * a, 1e-6 * diagonal):
                raise ValueError(f"crack.at_mm: the point is {gap:.3g} mm from {name}; give a point on the face the crack "
                                 f"opens from (the nearest is {[round(c, 3) for c in snapped]})")
            at = np.array(snapped, dtype=float)
        outward = _face_normal(face, snapped)
        if outward is None:
            raise ValueError(f"crack.face: cadgen could not find which way {name} faces at the crack; choose a smooth face")
        m = np.array(outward, dtype=float)
        in_plane = m - (m @ n) * n
        if np.linalg.norm(in_plane) < 1e-3:
            raise ValueError(f"crack.normal: the crack plane lies along {name}; a crack opens into the part, so its plane "
                             "must cross the face")
        in_plane /= np.linalg.norm(in_plane)
    if spec.kind in ("edge", "surface"):
        d = -in_plane
        # Into the part: a little way along d from the mouth is inside it.
        probe = 1e-3 * max(a, 1e-3 * diagonal)
        if not _inside(shape, tuple(at + probe * d), 1e-7) and _inside(shape, tuple(at - probe * d), 1e-7):
            d = -d
        t = np.cross(n, d)
        c = 0.5 * spec.length_mm if spec.length_mm is not None else a
        if spec.kind == "edge":
            c = math.inf
    elif spec.kind == "through":
        thickness = in_plane
        if spec.along is not None:
            d = np.array(spec.along, dtype=float)
            if abs(d @ thickness) > 1e-3:
                raise ValueError(f"crack.along: a through crack runs through the thickness of {name}; its length must lie "
                                 "across that face, not through it")
        else:
            d = np.cross(n, thickness)
        d /= np.linalg.norm(d)
        t = np.cross(n, d)
        c = math.inf
        if not _inside(shape, tuple(at), 1e-7):
            raise ValueError(f"crack.at_mm: the through crack's centre {list(spec.at)} is not inside the part")
    else:  # embedded
        if spec.along is not None:
            t = np.array(spec.along, dtype=float)
        else:
            axis = int(np.argmin(np.abs(n)))
            helper = np.zeros(3)
            helper[axis] = 1.0
            t = np.cross(n, helper)
        t /= np.linalg.norm(t)
        d = np.cross(t, n)
        c = 0.5 * spec.length_mm if spec.length_mm is not None else a
        for angle in np.linspace(0.0, 2.0 * math.pi, 24, endpoint=False):
            rim = at + a * math.cos(angle) * d + c * math.sin(angle) * t
            if not _inside(shape, tuple(rim), 1e-7):
                raise ValueError("crack: the embedded crack reaches the part's surface at "
                                 f"{[round(float(x), 3) for x in rim]}; use a surface crack there, or a smaller one")
    return CrackGeometry(spec, at, n / np.linalg.norm(n), d, t, float(a), float(c), float(reach))


def _rectangle(geometry: CrackGeometry, d_range, t_range):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    at, d, t = geometry.at, geometry.d, geometry.t
    polygon = BRepBuilderAPI_MakePolygon()
    for u, v in ((d_range[0], t_range[0]), (d_range[1], t_range[0]), (d_range[1], t_range[1]), (d_range[0], t_range[1])):
        p = at + u * d + v * t
        polygon.Add(gp_Pnt(*map(float, p)))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire(), True).Face()


def _ellipse(geometry: CrackGeometry):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax2, gp_Dir, gp_Elips, gp_Pnt

    major_d = geometry.a >= geometry.c
    x_axis = geometry.d if major_d else geometry.t
    major, minor = (geometry.a, geometry.c) if major_d else (geometry.c, geometry.a)
    if abs(major - minor) <= 1e-12 * major:
        minor = major  # a circle
    frame = gp_Ax2(gp_Pnt(*map(float, geometry.at)), gp_Dir(*map(float, geometry.n)), gp_Dir(*map(float, x_axis)))
    edge = BRepBuilderAPI_MakeEdge(gp_Elips(frame, float(major), float(minor))).Edge()
    return BRepBuilderAPI_MakeFace(BRepBuilderAPI_MakeWire(edge).Wire(), True).Face()


def crack_face(geometry: CrackGeometry):
    """The crack as an OCP face in its plane, reaching past the part where it runs across it."""
    reach = geometry.reach
    if geometry.kind == "edge":
        return _rectangle(geometry, (-geometry.a, geometry.a), (-reach, reach))
    if geometry.kind == "through":
        return _rectangle(geometry, (-geometry.a, geometry.a), (-reach, reach))
    return _ellipse(geometry)


@dataclass
class CrackedPrepared(Prepared):
    """The part (or a rung's shape of it) cut along the crack plane: what the mesher meshes for a fracture study.

    ``origin`` traces each face as :class:`Prepared` does, the crack's faces under :data:`CRACK_ORDINAL` and the
    ligament's under :data:`LIGAMENT_ORDINAL`; ``size_field`` keeps the front fine (the mesher merges it with any
    other); ``base`` is what was cut (``None`` for the part itself), so a rung that changes the shape is cut again."""

    base: Any = None
    crack: CrackGeometry | None = None
    size_field: dict | None = None
    #: The front's element size and the J domain's radius it was meshed for, mm.
    front_mm: float = 0.0
    radius_mm: float = 0.0


def cut(geometry: CrackGeometry, shape, origin: list[int] | None, *, base=None, front_mm: float, radius_mm: float) -> CrackedPrepared:
    """``shape`` cut along the crack's plane by the crack and the ligament, every face traced (``origin`` the
    shape's own, ``None`` for the part's ordinals). A crack that misses the part is a ValueError."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Splitter
    from OCP.TopTools import TopTools_ListOfShape

    from cadgen._internal.fea.defeature import face_map, trace

    crack = crack_face(geometry)
    plane = _rectangle(geometry, (-geometry.reach, geometry.reach), (-geometry.reach, geometry.reach))
    ligament = BRepAlgoAPI_Cut(plane, crack).Shape()
    splitter = BRepAlgoAPI_Splitter()
    arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(shape)
    tools.Append(crack)
    tools.Append(ligament)
    splitter.SetArguments(arguments)
    splitter.SetTools(tools)
    splitter.SetRunParallel(False)
    splitter.Build()
    if not splitter.IsDone():
        raise ValueError("crack: OpenCascade could not cut the crack into the part; check where it is and how big")
    result = splitter.Shape()
    traced = trace(splitter, shape, result, origin)
    faces = face_map(result)
    cracked = [faces.FindIndex(image) for image in splitter.Modified(crack)]
    cracked = [index for index in cracked if index > 0]
    if not cracked:
        raise ValueError(f"crack: the {geometry.kind} crack at {[round(float(c), 3) for c in geometry.at]} does not cut the part; "
                         "check at_mm, normal and size_mm")
    for index in cracked:
        traced[index - 1] = CRACK_ORDINAL
    traced = [LIGAMENT_ORDINAL if value == 0 else value for value in traced]
    prepared = CrackedPrepared(result, traced, list(getattr(base, "planes", []) or []), base=base, crack=geometry,
                               front_mm=front_mm, radius_mm=radius_mm)
    prepared.size_field = {"points": front_points(geometry, shape, front_mm, radius_mm), "radius_mm": 0.0}
    return prepared


def domain_radius(geometry: CrackGeometry) -> float:
    """The J domain's radius: a share of the crack's smaller size."""
    return DOMAIN_SHARE * geometry.size


def front_polylines(geometry: CrackGeometry, shape) -> list:
    """The front(s) as dense point lists, clipped to the part's box: what the local sizes follow before meshing."""
    import numpy as np

    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    low = np.array(box.Get()[:3])
    high = np.array(box.Get()[3:])
    corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    at, d, t = geometry.at, geometry.d, geometry.t

    def line(offset: float):
        span = (corners - at) @ t
        lo, hi = float(span.min()), float(span.max())
        count = 400
        return [at + offset * d + v * t for v in np.linspace(lo, hi, count)]

    if geometry.kind == "edge":
        return [line(geometry.a)]
    if geometry.kind == "through":
        return [line(geometry.a), line(-geometry.a)]
    angles = np.linspace(0.0, 2.0 * math.pi, 721)
    points = [at + geometry.a * math.cos(phi) * d + geometry.c * math.sin(phi) * t for phi in angles]
    inside = [p for p in points if np.all(p >= low - 1e-6) and np.all(p <= high + 1e-6)]
    return [inside]


def front_points(geometry: CrackGeometry, shape, size_mm: float, radius_mm: float) -> list[list[float]]:
    """Local sizes for the mesher: ``size_mm`` along the front and on two rings around it (at half the J domain's
    radius and at a little past it), so the whole domain is meshed at about that size."""
    import numpy as np

    out: list[list[float]] = []
    n = geometry.n
    for points in front_polylines(geometry, shape):
        if len(points) < 2:
            continue
        points = np.asarray(points)
        steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(steps)])
        length = float(s[-1])
        spacing = max(2.0 * size_mm, length / 150.0)
        count = max(2, int(math.ceil(length / spacing)) + 1)
        for target in np.linspace(0.0, length, count):
            k = int(np.clip(np.searchsorted(s, target), 1, len(points) - 1))
            w = (target - s[k - 1]) / max(steps[k - 1], 1e-300)
            p = points[k - 1] + w * (points[k] - points[k - 1])
            tangent = points[k] - points[k - 1]
            tangent /= max(np.linalg.norm(tangent), 1e-300)
            across = np.cross(tangent, n)
            out.append([*map(float, p), float(size_mm)])
            for ring in (0.5 * radius_mm, 1.15 * radius_mm):
                for angle in np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False):
                    q = p + ring * (math.cos(angle) * across + math.sin(angle) * n)
                    out.append([*map(float, q), float(size_mm)])
    return out


# -- opening the crack in the mesh --------------------------------------------------------------------

# A 6-node triangle as netgen lists it: corners 0, 1, 2, then the mid-edge nodes of edges (1, 2), (0, 2), (0, 1).
_TRIANGLE_EDGES = ((1, 2, 3), (0, 2, 4), (0, 1, 5))


def _flip(rows):
    import numpy as np

    return np.ascontiguousarray(rows[:, [0, 2, 1, 3, 5, 4]])


def _facing(rows, nodes, direction):
    """The triangles wound so their normal points along ``direction``."""
    import numpy as np

    a, b, c = (nodes[rows[:, k]] for k in range(3))
    normal = np.cross(b - a, c - a)
    wrong = normal @ direction < 0
    rows = rows.copy()
    rows[wrong] = _flip(rows[wrong])
    return rows


def _unique_rows(rows):
    import numpy as np

    if len(rows) == 0:
        return rows
    _, first = np.unique(np.sort(rows[:, :3], axis=1), axis=0, return_index=True)
    return rows[np.sort(first)]


@dataclass
class Front:
    """One connected crack front: its points in order (corner and mid-edge nodes), each one's crack-extension
    direction ``e1`` (in the crack plane, away from the crack), the plane's normal ``n`` and whether it closes."""

    points: Any
    e1: Any
    n: Any
    closed: bool = False

    @property
    def s(self):
        import numpy as np

        steps = np.linalg.norm(np.diff(self.points, axis=0), axis=1)
        return np.concatenate([[0.0], np.cumsum(steps)])

    @property
    def length(self) -> float:
        import numpy as np

        extra = float(np.linalg.norm(self.points[0] - self.points[-1])) if self.closed else 0.0
        return float(self.s[-1]) + extra


def open_crack(volume, geometry: CrackGeometry):
    """The mesh with the crack opened: (volume, fronts). Every node on the crack's faces but the front's is duplicated,
    the elements on the far side of the plane take the copies, the ligament's triangles are dropped and the crack's
    become two traction-free surfaces (ordinal 0, each facing out of its own side)."""
    import dataclasses

    import numpy as np

    nodes, tets = volume.nodes, volume.tets
    ordinal = volume.boundary_ordinal
    crack_rows = _unique_rows(volume.boundary[ordinal == CRACK_ORDINAL])
    ligament_rows = _unique_rows(volume.boundary[ordinal == LIGAMENT_ORDINAL])
    if len(crack_rows) == 0:
        raise RuntimeError("the mesher left no triangles on the crack's faces")
    on_front = np.intersect1d(np.unique(crack_rows), np.unique(ligament_rows))
    dup = np.setdiff1d(np.unique(crack_rows), on_front)
    count = len(nodes)
    remap = np.arange(count + len(dup))
    remap[dup] = count + np.arange(len(dup))
    at, n = geometry.at, geometry.n

    def side(rows_or_tets, width: int):
        centroid = nodes[rows_or_tets[:, :width]].mean(axis=1)
        return (centroid - at) @ n

    minus_tets = side(tets, 4) < 0
    new_tets = tets.copy()
    new_tets[minus_tets] = remap[tets[minus_tets]]
    outer = (ordinal != CRACK_ORDINAL) & (ordinal != LIGAMENT_ORDINAL)
    outer_rows = volume.boundary[outer].copy()
    minus_rows = side(outer_rows, 3) < 0
    outer_rows[minus_rows] = remap[outer_rows[minus_rows]]
    plus_face = _facing(crack_rows, nodes, -n)
    minus_face = remap[_facing(crack_rows, nodes, n)]
    boundary = np.concatenate([outer_rows, plus_face, minus_face])
    boundary_ordinal = np.concatenate([ordinal[outer], np.zeros(2 * len(crack_rows), dtype=ordinal.dtype)])
    opened = dataclasses.replace(volume, nodes=np.concatenate([nodes, nodes[dup]]), tets=new_tets, boundary=boundary,
                                 boundary_ordinal=boundary_ordinal)
    return opened, _fronts(nodes, crack_rows, set(on_front.tolist()), n)


def _fronts(nodes, crack_rows, on_front: set, n) -> list[Front]:
    """The front's edges (a crack triangle's edge whose three nodes are all on the ligament too), chained in order."""
    import numpy as np

    edges: dict[tuple[int, int], tuple[int, int]] = {}  # (corner, corner) -> (mid-edge node, third corner)
    for row in crack_rows:
        for i, j, k in _TRIANGLE_EDGES:
            a, b, mid = int(row[i]), int(row[j]), int(row[k])
            if a in on_front and b in on_front and mid in on_front:
                third = int(row[3 - i - j])
                edges[(min(a, b), max(a, b))] = (mid, third)
    if not edges:
        raise RuntimeError("the crack's front was not found in the mesh")
    near: dict[int, list[int]] = {}
    for a, b in edges:
        near.setdefault(a, []).append(b)
        near.setdefault(b, []).append(a)
    seen: set[tuple[int, int]] = set()
    fronts = []
    starts = [node for node, others in near.items() if len(others) == 1] + list(near)
    for start in starts:
        if all((min(start, o), max(start, o)) in seen for o in near[start]):
            continue
        chain = [start]
        mids, thirds = [], []
        current = start
        closed = False
        while True:
            step = next((o for o in near[current] if (min(current, o), max(current, o)) not in seen), None)
            if step is None:
                break
            key = (min(current, step), max(current, step))
            seen.add(key)
            mid, third = edges[key]
            mids.append(mid)
            thirds.append(third)
            if step == start:
                closed = True
                break
            chain.append(step)
            current = step
        if not mids:
            continue
        order: list[int] = []
        for index, corner in enumerate(chain):
            order.append(corner)
            if index < len(mids):
                order.append(mids[index])
        points = nodes[np.array(order)]
        # Each edge's direction away from the crack: in the plane, across the edge, away from its triangle's third corner.
        e1_edges = []
        for index, mid in enumerate(mids):
            a = nodes[order[2 * index]]
            b = nodes[order[2 * index + 2]] if 2 * index + 2 < len(order) else nodes[order[0]]
            tangent = b - a
            across = np.cross(tangent, n)
            across -= (across @ n) * n
            across /= max(np.linalg.norm(across), 1e-300)
            if across @ (nodes[thirds[index]] - nodes[mid]) > 0:
                across = -across
            e1_edges.append(across)
        e1 = np.zeros_like(points)
        for index in range(len(points)):
            if index % 2 == 1:
                e1[index] = e1_edges[index // 2]
            else:
                around = [e1_edges[k] for k in (index // 2 - 1, index // 2) if 0 <= k < len(e1_edges)]
                if closed and index == 0:
                    around.append(e1_edges[-1])
                e1[index] = np.mean(around, axis=0)
        e1 -= (e1 @ n)[:, None] * n
        e1 /= np.maximum(np.linalg.norm(e1, axis=1), 1e-300)[:, None]
        fronts.append(Front(points, e1, np.asarray(n, dtype=float), closed))
    return fronts


def mirror_front(front: Front, plane) -> Front:
    """A front's mirror image about a symmetry plane (:class:`cadgen._internal.fea.symmetry.Plane`)."""
    return Front(plane.reflect(front.points)[::-1], plane.reflect_vectors(front.e1)[::-1],
                 plane.reflect_vectors(front.n[None, :])[0], front.closed)


def join_fronts(fronts: list[Front], tolerance: float) -> list[Front]:
    """Fronts whose ends meet joined into one (a half front and its mirror image); a chain whose ends meet closes."""
    import numpy as np

    fronts = list(fronts)
    joined = True
    while joined:
        joined = False
        for i in range(len(fronts)):
            for j in range(len(fronts)):
                if i == j or fronts[i].closed or fronts[j].closed:
                    continue
                a, b = fronts[i], fronts[j]
                for flip_a in (False, True):
                    for flip_b in (False, True):
                        pa = a.points[::-1] if flip_a else a.points
                        pb = b.points[::-1] if flip_b else b.points
                        if np.linalg.norm(pa[-1] - pb[0]) <= tolerance:
                            ea = a.e1[::-1] if flip_a else a.e1
                            eb = b.e1[::-1] if flip_b else b.e1
                            merged = Front(np.concatenate([pa, pb[1:]]), np.concatenate([ea, eb[1:]]), a.n)
                            fronts = [f for k, f in enumerate(fronts) if k not in (i, j)] + [merged]
                            joined = True
                            break
                    if joined:
                        break
                if joined:
                    break
            if joined:
                break
    for front in fronts:
        if not front.closed and len(front.points) > 3 and np.linalg.norm(front.points[0] - front.points[-1]) <= tolerance:
            front.points, front.e1, front.closed = front.points[:-1], front.e1[:-1], True
    return fronts


def unfold_fronts(fronts: list[Front], planes, tolerance: float) -> list[Front]:
    """The fronts of a symmetric half (or quarter) mirrored into the whole part, the halves joined."""
    for plane in reversed(list(planes)):
        fronts = join_fronts(fronts + [mirror_front(front, plane) for front in fronts], tolerance)
    return fronts


# -- the interaction integral -------------------------------------------------------------------------


def _p2_tet(points):
    """Quadratic tet shape functions and their reference gradients at ``points`` (3, Q), skfem's node order:
    corners 0..3, then edges (0,1) (1,2) (0,2) (0,3) (1,3) (2,3)."""
    import numpy as np

    x, y, z = points
    L = np.array([1.0 - x - y - z, x, y, z])  # (4, Q)
    dL = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])  # (4, 3)
    Q = points.shape[1]
    N = np.zeros((10, Q))
    dN = np.zeros((10, 3, Q))
    for i in range(4):
        N[i] = L[i] * (2.0 * L[i] - 1.0)
        dN[i] = (4.0 * L[i] - 1.0)[None, :] * dL[i][:, None]
    for k, (i, j) in enumerate(((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)), 4):
        N[k] = 4.0 * L[i] * L[j]
        dN[k] = 4.0 * (L[i][None, :] * dL[j][:, None] + L[j][None, :] * dL[i][:, None])
    return N, dN


def _williams(r, theta, kappa, mu):
    """The plane-strain near-tip displacements for a unit K (local x1 ahead, x2 normal, x3 along the front):
    three (3, P) arrays, modes I, II and III."""
    import numpy as np

    root = np.sqrt(r / (2.0 * math.pi))
    half = theta / 2.0
    c, s = np.cos(half), np.sin(half)
    zero = np.zeros_like(r)
    one = root / (2.0 * mu)
    mode_1 = np.array([one * c * (kappa - 1.0 + 2.0 * s * s), one * s * (kappa + 1.0 - 2.0 * c * c), zero])
    mode_2 = np.array([one * s * (kappa + 1.0 + 2.0 * c * c), -one * c * (kappa - 1.0 - 2.0 * s * s), zero])
    mode_3 = np.array([zero, zero, (2.0 / mu) * root * s])
    return mode_1, mode_2, mode_3


def _williams_gradients(r, theta, kappa, mu):
    """Each mode's displacement gradient in the local frame, (3 modes, 3, 3, P): d u_i / d x_j, nothing along x3."""
    import numpy as np

    h = 1e-6
    base = _williams(r, theta, kappa, mu)
    ahead = _williams(r, theta + h, kappa, mu)
    behind = _williams(r, theta - h, kappa, mu)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    out = np.zeros((3, 3, 3, r.shape[0]))
    for mode in range(3):
        d_r = base[mode] / (2.0 * r)                   # u = sqrt(r) f(θ)
        d_theta = (ahead[mode] - behind[mode]) / (2.0 * h)
        out[mode, :, 0] = cos_t * d_r - sin_t / r * d_theta
        out[mode, :, 1] = sin_t * d_r + cos_t / r * d_theta
    return out


def _project(points, front: Front):
    """For each point: the nearest point on the front polyline, its arc position s, its e1 and its distance."""
    import numpy as np

    P = front.points
    E = front.e1
    if front.closed:
        P = np.concatenate([P, P[:1]])
        E = np.concatenate([E, E[:1]])
    a, b = P[:-1], P[1:]
    seg = b - a
    length2 = np.maximum((seg * seg).sum(axis=1), 1e-300)
    s_start = np.concatenate([[0.0], np.cumsum(np.sqrt(length2))])[:-1]
    best_d = np.full(len(points), np.inf)
    best = np.zeros((len(points), 3))
    best_s = np.zeros(len(points))
    best_e = np.zeros((len(points), 3))
    chunk = max(1, 2_000_000 // max(len(a), 1))
    for start in range(0, len(points), chunk):
        X = points[start:start + chunk]
        rel = X[:, None, :] - a[None, :, :]
        w = np.clip((rel * seg[None]).sum(axis=2) / length2[None], 0.0, 1.0)
        foot = a[None] + w[..., None] * seg[None]
        dist = np.linalg.norm(X[:, None, :] - foot, axis=2)
        k = dist.argmin(axis=1)
        rows = np.arange(len(X))
        wk = w[rows, k]
        best_d[start:start + chunk] = dist[rows, k]
        best[start:start + chunk] = foot[rows, k]
        best_s[start:start + chunk] = s_start[k] + wk * np.sqrt(length2[k])
        e = (1.0 - wk)[:, None] * E[k] + wk[:, None] * E[k + 1]
        best_e[start:start + chunk] = e / np.maximum(np.linalg.norm(e, axis=1), 1e-300)[:, None]
    return best, best_s, best_e, best_d


@dataclass
class FrontK:
    """K along each front, at its stations: MPa√m. ``spread`` is how far K moved between the two J domains (a share)."""

    #: One entry per station: (front index, arc position mm, point mm, K_I, K_II, K_III, J N/mm, K_I on the second domain, end).
    front: list = field(default_factory=list)
    s_mm: list = field(default_factory=list)
    at_mm: list = field(default_factory=list)
    K_I: list = field(default_factory=list)
    K_II: list = field(default_factory=list)
    K_III: list = field(default_factory=list)
    J_N_mm: list = field(default_factory=list)
    K_eq_second: list = field(default_factory=list)
    end: list = field(default_factory=list)
    radius_mm: float = 0.0
    nu: float = 0.3

    def K_eq(self, index: int) -> float:
        """The equivalent K (the energy one): √(K_I² + K_II² + K_III²/(1 − ν))."""
        return math.sqrt(max(self.K_I[index], 0.0) ** 2 + self.K_II[index] ** 2 + self.K_III[index] ** 2 / (1.0 - self.nu))

    @property
    def governing(self) -> int:
        return max(range(len(self.K_I)), key=self.K_eq)

    @property
    def spread(self) -> float:
        """The largest relative change of the equivalent K between the two domains, over the stations inside the part
        (a station where the front meets a free surface reads the corner's own field, which no domain resolves; it
        counts only when the front has no other)."""
        peak = max((self.K_eq(i) for i in range(len(self.K_I))), default=0.0)
        if not peak > 0:
            return 0.0
        inside = [i for i in range(len(self.K_I)) if not self.end[i]] or list(range(len(self.K_I)))
        return max(abs(self.K_eq(i) - self.K_eq_second[i]) / peak for i in inside)


def _stations(front: Front, spacing: float):
    """Station positions along a front (arc mm) and the hat half-width: about ``spacing`` apart, ends included."""
    import numpy as np

    length = front.length
    intervals = max(1, int(round(length / max(spacing, 1e-9))))
    width = length / intervals
    if front.closed:
        return np.arange(intervals) * width, width
    return np.linspace(0.0, length, intervals + 1), width


def _hat(s, centre, width, length, closed):
    import numpy as np

    gap = np.abs(s - centre)
    if closed:
        gap = np.minimum(gap, length - gap)
    return np.clip(1.0 - gap / width, 0.0, 1.0)


def _radial(r, radius):
    import numpy as np

    inner = PLATEAU * radius
    return np.clip((radius - r) / (radius - inner), 0.0, 1.0)


def stress_intensity(locations, element_dofs, displacement, E: float, nu: float, fronts: list[Front], radius_mm: float,
                     *, spacing_mm: float | None = None) -> FrontK:
    """K_I, K_II and K_III (MPa√m) and J (N/mm) at stations along each front, by the domain interaction integral.

    ``locations`` (M, 3) and ``displacement`` (M, 3) are per scalar DOF, ``element_dofs`` (E, 10) each quadratic
    element's in skfem's order. The domain around a station is a tube of ``radius_mm`` about the front (q = 1 within
    a third of it, falling to 0 at it) times a hat along the front; K is also read on a domain 0.6 times as big.
    """
    import numpy as np
    from scipy.spatial import cKDTree
    from skfem.quadrature import get_quadrature
    from skfem.refdom import RefTet

    mu = E / (2.0 * (1.0 + nu))
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    kappa = 3.0 - 4.0 * nu
    E_prime = E / (1.0 - nu * nu)
    X_ref, W_ref = get_quadrature(RefTet, 4)
    N, dN = _p2_tet(X_ref)
    out = FrontK(radius_mm=radius_mm, nu=nu)
    spacing = spacing_mm or max(0.5 * radius_mm, 1e-9)
    corners = element_dofs[:, :4]
    for f_index, front in enumerate(fronts):
        tree = cKDTree(np.concatenate([front.points, 0.5 * (front.points[1:] + front.points[:-1])]))
        near_nodes = np.flatnonzero(tree.query(locations, distance_upper_bound=1.2 * radius_mm + 1e-9)[0] < np.inf)
        near = np.zeros(len(locations), bool)
        near[near_nodes] = True
        elements = np.flatnonzero(near[element_dofs].any(axis=1))
        if not len(elements):
            continue
        dofs = element_dofs[elements]
        Xe = locations[dofs]                                  # (E, 10, 3)
        Ue = displacement[dofs]                               # (E, 10, 3)
        jac = np.einsum("eai,ajq->eqij", Xe, dN)              # dx_i / dξ_j: (E, Q, 3, 3)
        det = np.linalg.det(jac)
        inv = np.linalg.inv(jac)                              # dξ / dx
        dNdx = np.einsum("ajq,eqji->eqai", dN, inv)           # (E, Q, 10, 3)
        H = np.einsum("eaj,eqai->eqji", Ue, dNdx)             # du_j/dx_i (E, Q, 3, 3)
        eps = 0.5 * (H + np.swapaxes(H, 2, 3))
        trace = np.trace(eps, axis1=2, axis2=3)
        sigma = 2.0 * mu * eps + lam * trace[..., None, None] * np.eye(3)
        W = 0.5 * np.einsum("eqij,eqij->eq", sigma, eps)
        gauss = np.einsum("eai,aq->eqi", Xe, N)               # (E, Q, 3)
        dV = np.abs(det) * W_ref[None, :]
        flat = gauss.reshape(-1, 3)
        foot, s_g, e1_g, _ = _project(flat, front)
        e2 = np.broadcast_to(front.n, e1_g.shape)
        e3 = np.cross(e1_g, e2)
        rel = flat - foot
        x1 = (rel * e1_g).sum(axis=1)
        x2 = (rel * e2).sum(axis=1)
        r = np.maximum(np.hypot(x1, x2), 1e-12 * radius_mm)
        theta = np.arctan2(x2, x1)
        local = _williams_gradients(r, theta, kappa, mu)      # (3 modes, 3, 3, P)
        frame = np.stack([e1_g, e2, e3], axis=1)              # (P, 3, 3): rows e1, e2, e3
        # The auxiliary gradient in global axes: Qᵀ L Q.
        aux_H = np.einsum("pki,mklp,plj->mpij", frame, local, frame)
        aux_eps = 0.5 * (aux_H + np.swapaxes(aux_H, 2, 3))
        aux_trace = np.trace(aux_eps, axis1=2, axis2=3)
        aux_sigma = 2.0 * mu * aux_eps + lam * aux_trace[..., None, None] * np.eye(3)
        shape = H.shape[:2]
        sig = sigma.reshape(-1, 3, 3)
        Hg = H.reshape(-1, 3, 3)                              # [p, j, m] = du_j/dx_m
        W_int = np.einsum("pjk,mpjk->mp", sig, aux_eps)
        # P_im for J and for each mode: σ_ij H_jm (+ σ^aux_ij H_jm + σ_ij H^aux_jm) − W δ_im.
        P_J = np.einsum("pij,pjm->pim", sig, Hg) - W.reshape(-1)[:, None, None] * np.eye(3)
        P_aux = (np.einsum("pij,mpjk->mpik", sig, aux_H) + np.einsum("mpij,pjk->mpik", aux_sigma, Hg)
                 - W_int[..., None, None] * np.eye(3))
        node_foot, node_s, node_e1, node_r = _project(locations[np.unique(dofs)], front)
        node_ids = np.unique(dofs)
        lookup = np.full(len(locations), -1)
        lookup[node_ids] = np.arange(len(node_ids))
        stations, width = _stations(front, spacing)
        s_dense = front.s
        length = front.length
        for centre in stations:
            hat_nodes = _hat(node_s, centre, width, length, front.closed)
            norm = _hat_integral(front, centre, width)
            values = []
            for radius in (radius_mm, SECOND_DOMAIN * radius_mm):
                q = _radial(node_r, radius) * hat_nodes
                if not q.any():
                    values.append(None)
                    continue
                qv = q[:, None] * node_e1                     # (nodes, 3)
                q_e = qv[lookup[dofs]]                        # (E, 10, 3)
                G = np.einsum("eam,eqai->eqmi", q_e, dNdx).reshape(-1, 3, 3)   # dq_m/dx_i
                weight = dV.reshape(-1)
                J = float((np.einsum("pim,pmi->p", P_J, G) * weight).sum()) / norm
                I = [float((np.einsum("pim,pmi->p", P_aux[m], G) * weight).sum()) / norm for m in range(3)]
                values.append((J, I))
            if values[0] is None:
                continue
            J, I = values[0]
            K_I = E_prime * I[0] / 2.0
            K_II = E_prime * I[1] / 2.0
            K_III = mu * I[2]
            scale = 1.0 / math.sqrt(MM_PER_M)  # MPa√mm to MPa√m
            second = values[1] if values[1] is not None else values[0]
            k2 = (E_prime * second[1][0] / 2.0, E_prime * second[1][1] / 2.0, mu * second[1][2])
            point = _point_at(front, centre)
            out.front.append(f_index)
            out.s_mm.append(float(centre))
            out.at_mm.append([float(c) for c in point])
            out.K_I.append(K_I * scale)
            out.K_II.append(K_II * scale)
            out.K_III.append(K_III * scale)
            out.J_N_mm.append(J)
            out.K_eq_second.append(math.sqrt(max(k2[0], 0.0) ** 2 + k2[1] ** 2 + k2[2] ** 2 / (1.0 - nu)) * scale)
            out.end.append(bool(not front.closed and (centre <= 1e-9 * length or centre >= length * (1 - 1e-9))))
        del shape, s_dense
    return out


def _hat_integral(front: Front, centre: float, width: float) -> float:
    """∫ hat ds along the front: the width inside it, half at an open end."""
    import numpy as np

    s = np.linspace(0.0, front.length, 4001)
    return float(np.trapezoid(_hat(s, centre, width, front.length, front.closed), s)) if hasattr(np, "trapezoid") else \
        float(np.trapz(_hat(s, centre, width, front.length, front.closed), s))


def _point_at(front: Front, s_target: float):
    import numpy as np

    s = front.s
    k = int(np.clip(np.searchsorted(s, s_target), 1, len(s) - 1))
    w = (s_target - s[k - 1]) / max(s[k] - s[k - 1], 1e-300)
    return front.points[k - 1] + min(max(w, 0.0), 1.0) * (front.points[k] - front.points[k - 1])


# -- Paris's law --------------------------------------------------------------------------------------


def delta_K_share(load_ratio: float) -> float:
    """ΔK / K_max for a load ratio R = K_min / K_max: 1 − R, and K_max itself when the load reverses (R < 0:
    the compressive part closes the crack and grows nothing)."""
    return 1.0 - load_ratio if load_ratio >= 0 else 1.0


def paris_life(K_max: float, a_mm: float, toughness: float, C: float, m: float, load_ratio: float = 0.0,
               final_mm: float | None = None, steps: int = 4000) -> dict:
    """Cycles for the crack to grow from ``a_mm`` to the size where K_max reaches ``toughness`` (or ``final_mm``),
    integrating da/dN = C (ΔK)^m numerically (Simpson's rule in ln a), with K = K_max √(a / a0) (the geometry factor
    held). K in MPa√m, C in m/cycle per (MPa√m)^m. Returns the cycles, the critical size and the rate at the start."""
    critical_mm = a_mm * (toughness / K_max) ** 2 if K_max > 0 else math.inf
    end = critical_mm if final_mm is None else min(final_mm, critical_mm)
    share = delta_K_share(load_ratio)
    rate0 = C * (share * K_max) ** m  # m per cycle
    if not end > a_mm or K_max <= 0:
        return {"cycles": 0.0 if K_max > 0 else math.inf, "critical_mm": critical_mm, "final_mm": end,
                "rate_mm_per_cycle": rate0 * MM_PER_M}
    lo, hi = math.log(a_mm), math.log(end)
    count = steps + (steps % 2)
    h = (hi - lo) / count
    total = 0.0
    for k in range(count + 1):
        x = lo + k * h
        a = math.exp(x)
        dK = share * K_max * math.sqrt(a / a_mm)
        f = (a / MM_PER_M) / (C * dK ** m)  # dN/d(ln a) = a / (da/dN), a in m
        total += f * (1 if k in (0, count) else 4 if k % 2 else 2)
    return {"cycles": total * h / 3.0, "critical_mm": critical_mm, "final_mm": end, "rate_mm_per_cycle": rate0 * MM_PER_M}


def paris_life_closed_form(sigma_range: float, Y: float, a0_mm: float, af_mm: float, C: float, m: float) -> float:
    """Cycles from a0 to af at a constant geometry factor Y and stress range Δσ (MPa): Norton's eq. 6.4b,
    N = (af^(1−m/2) − a0^(1−m/2)) / (C Y^m π^(m/2) Δσ^m (1 − m/2)), a in m (m = 2: the logarithm)."""
    a0, af = a0_mm / MM_PER_M, af_mm / MM_PER_M
    factor = C * Y ** m * math.pi ** (m / 2.0) * sigma_range ** m
    if abs(m - 2.0) < 1e-12:
        return math.log(af / a0) / factor
    return (af ** (1.0 - m / 2.0) - a0 ** (1.0 - m / 2.0)) / (factor * (1.0 - m / 2.0))
