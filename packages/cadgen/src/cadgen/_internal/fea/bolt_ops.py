"""Bolts: metric sizes, the joint-stiffness hand calc, where a bolt bears on the parts, and the pretensioned shank.

A bolt is not meshed. Its shank is a spring along the bolt's axis tying the
part under its head to the part under its nut (spec 2.1, "pretension
elements on the contact driver"):

- **Where it bears.** The study names the hole walls (cylindrical faces) or
  the head and nut bearing faces themselves (flat faces: a spot face or a
  washer face, all of which bears). From hole walls :func:`locate` fits the
  bolt's axis and the hole's radius, and the bearing areas are the annuli
  from the hole to the head's bearing diameter ``d_w`` on the outermost faces
  of the two parts that face away from each other. Each bearing area is
  integrated with contact_ops' fine rule on the surface triangles, so a coarse
  mesh still bears on the annulus' true area.
- **The spider.** Each end of the shank is a distributing (RBE3-like) spider:
  the end moves with the bearing area's mean axial displacement, and the
  shank's force spreads over the area as a uniform pressure (the work-conjugate
  pair, so nothing stiffens the parts). ``e = a · (ū_nut − ū_head)``, ``a`` the
  unit axis from head to nut, is the shank's stretch; ``g`` is its gradient,
  so the shank's force on the parts is ``−F g``.
- **Pretension, in two steps.** Step 1 pulls head and nut together with the
  preload ``F_V`` (``−F_V g`` as a load) while the clamped parts settle in
  frictional contact. Then the shank is locked: its unstretched length is set so
  that it carries exactly ``F_V`` where step 1 left it (the "length adjusted to
  hit the preload"), and from there it is a spring of the bolt's stiffness
  ``k_b``: ``F = F_V + k_b (e − e_1)``, never below 0 (a bolt does not push).
  Step 2 applies the study's loads. :class:`BoltedProblem` is
  :class:`~.contact_ops.ContactProblem` with the locked shanks added and the
  step-1 displacement as its starting point.

The bolt's stiffness and the clamped parts' are VDI 2230 Part 1 (2015), for a
through-bolted joint (DSV) with a hexagon head and nut:

- bolt, section 5.1.1: ``δ_S = δ_SK + δ_1 + δ_G + δ_M``, the head
  ``l_SK = 0.5 d`` and the nut ``l_M = 0.4 d`` on the nominal section
  ``A_N = π d²/4``, the engaged thread ``l_G = 0.5 d`` on the minor section
  ``A_d3`` (``d3 = d − 1.22687 P``), and a plain shank of the nominal
  diameter through the clamp length ``l_K``; ``k_b = 1/δ_S``;
- clamped parts, section 5.1.2.2: the deformation cone, ``tan φ = 0.362 +
  0.032 ln(β_L/2) + 0.153 ln y`` (``β_L = l_K/d_w``, ``y = D_A/d_w``), the
  cone's compliance where the parts are wider than its foot (``D_A ≥ d_w +
  l_K tan φ``), cone and sleeve between, and the sleeve
  ``A = π (D_A² − d_h²)/4`` where they are no wider than the head;
- the load factor ``Φ = k_b/(k_b + k_c)`` for a load brought in under the head
  and nut, the clamp lost under a separating load ``F_A`` being ``(1 − Φ) F_A``.

Sizes are ISO 261 coarse threads with the ISO 898-1 stress area, the ISO 273
medium clearance hole and the ISO 4014/4017 head's bearing diameter; proof
stresses are ISO 898-1 (steel) and ISO 3506-1 (stainless, the 0.2 % proof
stress). Stdlib at import; numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cadgen._internal.fea.contact_ops import ContactProblem

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = [
    "BoltGeometry", "BoltSize", "BoltSpring", "BoltedProblem", "DEFAULT_GRADE", "DEFAULT_NUT_FACTOR", "PROOF_MPa", "SIZES",
    "bolt_compliance", "bolt_size", "joint_compliance", "load_factor", "locate", "preload_from_torque",
]

#: The nut factor ``K`` of ``F = T / (K d)`` when the study names none: dry, unlubricated steel.
DEFAULT_NUT_FACTOR = 0.2
#: The property class a bolt is when the study names none.
DEFAULT_GRADE = "8.8"
#: The axial ends (head and nut) of the minor diameter: ``d3 = d − H_MINOR · P`` (ISO 724).
H_MINOR = 1.22687
#: VDI 2230 substitute lengths, in bolt diameters: hexagon head, engaged thread, nut (through-bolted joint).
L_HEAD, L_THREAD, L_NUT = 0.5, 0.5, 0.4
#: A face whose triangles' normals stay within this cosine of their mean is flat (a bearing face); else it is a hole wall.
FLAT = math.cos(math.radians(2.0))
#: A bearing triangle faces along the axis to within this cosine.
ALONG = 0.95
#: The bearing plane: points within this share of the bolt's diameter of the outermost face count as on it.
PLANE_SHARE = 0.02


@dataclass(frozen=True)
class BoltSize:
    """A metric bolt: nominal diameter, pitch, stress area, clearance hole, head bearing diameter (mm, mm²)."""

    name: str
    d: float
    pitch: float
    stress_area: float
    hole: float
    head: float

    @property
    def minor(self) -> float:
        return self.d - H_MINOR * self.pitch

    @property
    def nominal_area(self) -> float:
        return math.pi * self.d ** 2 / 4.0

    @property
    def minor_area(self) -> float:
        return math.pi * self.minor ** 2 / 4.0


def _size(name: str, d: float, pitch: float, stress_area: float, hole: float, head: float) -> BoltSize:
    return BoltSize(name, d, pitch, stress_area, hole, head)


#: ISO 261 coarse thread, ISO 898-1 stress area A_s, ISO 273 medium clearance hole d_h, ISO 4017 head bearing d_w (min).
SIZES: dict[str, BoltSize] = {size.name: size for size in (
    _size("M3", 3.0, 0.5, 5.03, 3.4, 4.57),
    _size("M4", 4.0, 0.7, 8.78, 4.5, 5.88),
    _size("M5", 5.0, 0.8, 14.2, 5.5, 6.88),
    _size("M6", 6.0, 1.0, 20.1, 6.6, 8.88),
    _size("M8", 8.0, 1.25, 36.6, 9.0, 11.63),
    _size("M10", 10.0, 1.5, 58.0, 11.0, 14.63),
    _size("M12", 12.0, 1.75, 84.3, 13.5, 16.63),
    _size("M14", 14.0, 2.0, 115.0, 15.5, 19.64),
    _size("M16", 16.0, 2.0, 157.0, 17.5, 22.49),
    _size("M20", 20.0, 2.5, 245.0, 22.0, 28.19),
    _size("M24", 24.0, 3.0, 353.0, 26.0, 33.61),
    _size("M30", 30.0, 3.5, 561.0, 33.0, 42.75),
)}

#: Proof stress, MPa: ISO 898-1 property classes (8.8 is 600 above M16) and ISO 3506-1 stainless (0.2 % proof stress).
PROOF_MPa: dict[str, float] = {
    "4.6": 225.0, "4.8": 310.0, "5.6": 280.0, "5.8": 380.0, "6.8": 440.0, "8.8": 580.0, "9.8": 650.0, "10.9": 830.0,
    "12.9": 970.0, "A2-70": 450.0, "A4-70": 450.0, "A2-80": 600.0, "A4-80": 600.0,
}


def bolt_size(diameter: float) -> BoltSize:
    """The size of a bolt given only its diameter: the table's when it is one, else scaled from the nearest table size
    (pitch, hole and head in proportion; the stress area from ISO 898-1, ``π/4 (d − 0.9382 P)²``)."""
    for size in SIZES.values():
        if abs(size.d - diameter) < 1e-9:
            return size
    near = min(SIZES.values(), key=lambda s: abs(math.log(s.d / diameter)))
    ratio = diameter / near.d
    pitch = near.pitch * ratio
    return BoltSize(f"Ø{diameter:g}", diameter, pitch, math.pi / 4.0 * (diameter - 0.9382 * pitch) ** 2,
                    near.hole * ratio, near.head * ratio)


def proof_load(size: BoltSize, grade: str) -> float:
    """The proof load, N: the proof stress times the stress area (class 8.8 is 600 MPa above M16)."""
    stress = PROOF_MPa[grade]
    if grade == "8.8" and size.d > 16.0:
        stress = 600.0
    return stress * size.stress_area


def preload_from_torque(torque_Nm: float, nut_factor: float, diameter_mm: float) -> float:
    """``F = T / (K d)``, N: the preload a tightening torque gives with nut factor ``K``."""
    return torque_Nm * 1000.0 / (nut_factor * diameter_mm)


def bolt_compliance(size: BoltSize, clamp_mm: float, E: float) -> dict[str, float]:
    """VDI 2230 section 5.1.1 (module docstring): each part's compliance, mm/N, and ``total``."""
    parts = {
        "head": L_HEAD * size.d / (E * size.nominal_area),
        "shank": clamp_mm / (E * size.nominal_area),
        "thread": L_THREAD * size.d / (E * size.minor_area),
        "nut": L_NUT * size.d / (E * size.nominal_area),
    }
    parts["total"] = sum(parts.values())
    return parts


def joint_compliance(head: float, hole: float, clamp_mm: float, outside: float, E: float) -> dict[str, float]:
    """VDI 2230 section 5.1.2.2 (module docstring), through-bolted (w = 1): the clamped parts' compliance, mm/N,
    with the cone angle and which body it is (``sleeve``, ``cone`` or ``cone and sleeve``)."""
    d_w, d_h, l_K, D_A = head, hole, clamp_mm, outside
    if D_A <= d_w:
        area = math.pi / 4.0 * (D_A ** 2 - d_h ** 2)
        return {"total": l_K / (E * area), "tan_phi": float("nan"), "body": "sleeve", "D_A": D_A}
    beta = l_K / d_w
    y = min(D_A / d_w, 10.0)
    tan = 0.362 + 0.032 * math.log(beta / 2.0) + 0.153 * math.log(y)
    limit = d_w + l_K * tan
    cone = 2.0 * math.log(((d_w + d_h) * (d_w + l_K * tan - d_h)) / ((d_w - d_h) * (d_w + l_K * tan + d_h))) / (
        E * math.pi * d_h * tan)
    if D_A >= limit:
        return {"total": cone, "tan_phi": tan, "body": "cone", "D_A": D_A}
    mixed = ((2.0 / (d_h * tan)) * math.log(((d_w + d_h) * (D_A - d_h)) / ((d_w - d_h) * (D_A + d_h)))
             + (4.0 / (D_A ** 2 - d_h ** 2)) * (l_K - (D_A - d_w) / tan)) / (E * math.pi)
    return {"total": mixed, "tan_phi": tan, "body": "cone and sleeve", "D_A": D_A}


def load_factor(bolt_compliance_total: float, joint_compliance_total: float) -> float:
    """``Φ = k_b / (k_b + k_c) = δ_P / (δ_S + δ_P)``: the share of a separating load the bolt takes."""
    return joint_compliance_total / (bolt_compliance_total + joint_compliance_total)


# -- where a bolt bears ------------------------------------------------------------------------------------


@dataclass
class Bearing:
    """One end of the shank: its bearing area's nodal weights (∫ N dA over the area) and where it is."""

    nodes: "np.ndarray"            # scalar DOFs with a weight
    weights: "np.ndarray"          # their ∫ N dA, mm² (sums to the area)
    area: float                    # mm²
    centre: "np.ndarray"           # (3,) the area's centroid
    share: "np.ndarray"            # (scalar_count,) each node's share of its surrounding surface inside the area (0..1)
    flat: bool                     # a named flat face (all of it bears) rather than an annulus found
    normal: "np.ndarray"           # (3,) the area's mean outward unit normal


@dataclass
class BoltGeometry:
    axis: "np.ndarray"             # (3,) unit, from the head towards the nut
    centre: "np.ndarray"           # (3,) a point on the axis
    hole_radius: float | None      # the fitted hole's radius (None when only flat faces were named)
    head: Bearing
    nut: Bearing
    clamp_mm: float                # l_K: the axial distance between the two bearing areas
    outside_mm: float              # D_A: twice the nearest outer edge of the clamped parts from the axis


def _triangles(space: "FemSpace", rows: "np.ndarray"):
    """Unit normals (outward), areas and centroids of boundary rows ``rows``."""
    import numpy as np

    from cadgen._internal.fea.contact_ops import surface_triangles

    triangles = surface_triangles(space, rows)
    points = space.dof_locations
    a, b, c = (points[triangles[:, k]] for k in range(3))
    cross = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    normal = cross / np.where(area > 0, 2.0 * area, 1.0)[:, None]
    return triangles, normal, area, (a + b + c) / 3.0


def _bearing(space: "FemSpace", rows: "np.ndarray", keep) -> Bearing | None:
    """The area of boundary rows ``rows`` where ``keep(position (P, 3)) -> (P,) bool`` holds, integrated finely."""
    import numpy as np

    from cadgen._internal.fea.contact_ops import _contact_points, surface_triangles

    if not len(rows):
        return None
    triangles = surface_triangles(space, rows)
    position, N, hat, area, normal, row = _contact_points(space, triangles)
    inside = keep(position)
    if not inside.any():
        return None
    count = space.scalar_count
    weights = np.zeros(count)
    inside_hat = np.zeros(count)
    total_hat = np.zeros(count)
    for j in range(6):
        nodes = triangles[row, j]
        weights += np.bincount(nodes, weights=N[:, j] * area * inside, minlength=count)
        inside_hat += np.bincount(nodes, weights=hat[:, j] * area * inside, minlength=count)
        total_hat += np.bincount(nodes, weights=hat[:, j] * area, minlength=count)
    used = np.flatnonzero(np.abs(weights) > 0)
    total = float((area * inside).sum())
    centre = (position[inside] * area[inside, None]).sum(axis=0) / total
    share = np.where(total_hat > 0, inside_hat / np.where(total_hat > 0, total_hat, 1.0), 0.0)
    mean = (normal[inside] * area[inside, None]).sum(axis=0)
    return Bearing(used, weights[used], total, centre, share, False, mean / max(float(np.linalg.norm(mean)), 1e-300))


def locate(space: "FemSpace", boundary_ordinal: "np.ndarray", node_part: "np.ndarray", ordinals: list[int],
           head_part: int, nut_part: int, size: BoltSize, where: str) -> BoltGeometry:
    """Where a bolt bears (module docstring): from the hole walls and bearing faces ``ordinals`` (face ordinals), the
    axis, the head's bearing area on ``head_part`` and the nut's on ``nut_part``. A ValueError at ``where`` says what
    is missing in words."""
    import numpy as np

    points = space.dof_locations
    rows = np.flatnonzero(np.isin(boundary_ordinal, ordinals))
    if not len(rows):
        raise ValueError(f"{where}.holes: the faces named have no surface left to bear on")
    triangles, normal, area, centroid = _triangles(space, rows)
    part_of = node_part[triangles[:, 0]]
    ordinal_of_row = np.asarray(boundary_ordinal)[rows]
    flat_rows: dict[int, list[int]] = {head_part: [], nut_part: []}
    wall: list[int] = []
    for ordinal in np.unique(ordinal_of_row):
        mine = np.flatnonzero(ordinal_of_row == ordinal)
        part = int(part_of[mine[0]])
        if part not in (head_part, nut_part):
            raise ValueError(f"{where}.holes: a face named is on neither of the two parts the bolt clamps")
        mean = (normal[mine] * area[mine, None]).sum(axis=0)
        length = float(np.linalg.norm(mean))
        flat = length > 0 and bool((normal[mine] @ (mean / length) >= FLAT).all())
        (flat_rows[part] if flat else wall).extend(mine.tolist())

    hole_radius = None
    if wall:
        w = np.asarray(wall)
        M = (normal[w, :, None] * normal[w, None, :] * area[w, None, None]).sum(axis=0)
        _, vectors = np.linalg.eigh(M)
        axis = vectors[:, 0]
        # The hole's centre and radius: an algebraic circle fit of the wall's nodes, in the plane across the axis.
        nodes = np.unique(triangles[w])
        p = points[nodes]
        e1 = np.cross(axis, [1.0, 0.0, 0.0] if abs(axis[0]) < 0.9 else [0.0, 1.0, 0.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(axis, e1)
        x, y = p @ e1, p @ e2
        A = np.stack([2 * x, 2 * y, np.ones_like(x)], axis=1)
        (cx, cy, c0), *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
        hole_radius = float(math.sqrt(max(c0 + cx * cx + cy * cy, 0.0)))
        centre = cx * e1 + cy * e2 + float((p @ axis).mean()) * axis
    else:
        named = flat_rows[head_part] or flat_rows[nut_part]
        if not flat_rows[head_part] or not flat_rows[nut_part]:
            raise ValueError(f"{where}.holes: name the hole's walls, or a flat bearing face on each part (the face under "
                             "the head and the face under the nut)")
        n = np.asarray(named)
        axis = (normal[n] * area[n, None]).sum(axis=0)
        axis /= np.linalg.norm(axis)
        centre = (centroid[n] * area[n, None]).sum(axis=0) / float(area[n].sum())

    def mean_along(part: int) -> float:
        on = node_part == part
        return float((points[on] @ axis).mean())

    # The axis points from the head to the nut.
    if mean_along(head_part) > mean_along(nut_part):
        axis = -axis
    boundary = space.boundary_quadratic
    every_part = node_part[boundary[:, 0]]

    def radius_of(position):
        offset = position - centre
        return np.linalg.norm(offset - np.outer(offset @ axis, axis), axis=1)

    def end(part: int, outward: "np.ndarray", word: str) -> Bearing:
        given = flat_rows[part]
        if given:
            found = _bearing(space, rows[np.asarray(given)], lambda position: np.ones(len(position), bool))
            found.flat = True
            return found
        candidates = np.flatnonzero(every_part == part)
        corners_of, n, _, centroid_c = _triangles(space, candidates)
        inner = (hole_radius or 0.0) * (1.0 - 1e-3)
        outer = 0.5 * size.head

        def annulus(position):
            r = radius_of(position)
            return (r >= inner) & (r <= outer)

        # Triangles facing outward along the axis that reach into the annulus; of those, the outermost plane (a
        # stepped part has several): the face the head (nut) sits on.
        edge = np.linalg.norm(points[corners_of[:, 0]] - points[corners_of[:, 1]], axis=1)
        near = (n @ outward >= ALONG) & (radius_of(centroid_c) <= outer + edge)
        if not near.any():
            raise ValueError(f"{where}: no face of the {word} part faces outward around the hole, under the "
                             f"{size.head:.3g} mm the {size.name} {word} bears on")
        along = centroid_c @ outward
        top = float(along[near].max())
        found = _bearing(space, candidates[near & (np.abs(along - top) <= PLANE_SHARE * size.d + 1e-9)], annulus)
        if found is None:
            raise ValueError(f"{where}: no face of the {word} part faces outward around the hole, under the "
                             f"{size.head:.3g} mm the {size.name} {word} bears on")
        return found

    head = end(head_part, -axis, "head")
    nut = end(nut_part, axis, "nut")
    # The bearing faces are flat and square to the bolt: their normals give its axis exactly, where the hole wall's
    # meshed facets give it only to the mesh's accuracy (a tilt would push the parts sideways by the preload).
    flat_normal = nut.normal - head.normal
    if float(np.linalg.norm(flat_normal)) > 0 and float(flat_normal @ axis) > 0:
        axis = flat_normal / float(np.linalg.norm(flat_normal))
    clamp = float(abs((nut.centre - head.centre) @ axis))
    if not clamp > 0:
        raise ValueError(f"{where}: the head and nut bearing faces are in one plane; name the faces the head and the nut sit on")

    # D_A: twice the nearest outer side face (one along the axis) of either part from the axis.
    outside = math.inf
    for part in (head_part, nut_part):
        mine = np.flatnonzero(every_part == part)
        _, n, _, _ = _triangles(space, mine)
        side = mine[np.abs(n @ axis) < 0.5]
        if not len(side):
            continue
        r = radius_of(points[np.unique(boundary[side][:, :3])])
        r = r[r > 1.2 * max(hole_radius or 0.0, 0.5 * size.d)]
        if len(r):
            outside = min(outside, 2.0 * float(r.min()))
    return BoltGeometry(axis, centre, hole_radius, head, nut, clamp, outside)


# -- the pretensioned shank --------------------------------------------------------------------------------


@dataclass
class BoltSpring:
    """One locked shank: ``F = preload + k (g·u − stretch0)`` along ``g`` (vector DOFs ``index``, values ``value``)."""

    index: "np.ndarray"
    value: "np.ndarray"
    k: float
    preload: float
    stretch0: float = 0.0
    _outer: Any = field(default=None, repr=False)

    def stretch(self, u: "np.ndarray") -> float:
        return float(self.value @ u[self.index])

    def force(self, u: "np.ndarray") -> float:
        return max(0.0, self.preload + self.k * (self.stretch(u) - self.stretch0))

    def outer(self, size: int):
        import numpy as np
        import scipy.sparse as sparse

        if self._outer is None:
            n = len(self.index)
            self._outer = sparse.coo_matrix(
                (self.k * np.outer(self.value, self.value).ravel(), (np.repeat(self.index, n), np.tile(self.index, n))),
                shape=(size, size)).tocsr()
        return self._outer


def shank_gradient(space: "FemSpace", geometry: BoltGeometry) -> "tuple[np.ndarray, np.ndarray]":
    """``g`` as (vector DOFs, values): ``g·u`` is the shank's stretch, the nut's mean axial move minus the head's."""
    import numpy as np

    from cadgen._internal.fea.contact_ops import vector_dofs

    vdofs = vector_dofs(space)
    index, value = [], []
    for bearing, sign in ((geometry.nut, 1.0), (geometry.head, -1.0)):
        for c in range(3):
            if abs(geometry.axis[c]) < 1e-15:
                continue
            index.append(vdofs[bearing.nodes, c])
            value.append(sign * geometry.axis[c] * bearing.weights / bearing.area)
    index, value = np.concatenate(index), np.concatenate(value)
    order = np.argsort(index, kind="stable")
    index, value = index[order], value[order]
    unique, start = np.unique(index, return_index=True)
    return unique, np.add.reduceat(value, start)


class BoltedProblem(ContactProblem):
    """The contact problem with bolts (module docstring). Before :meth:`lock` the shanks are not there (step 1 loads
    their preload as ``external``); after it, each is a :class:`BoltSpring` and the displacement the driver solves
    for is measured from where step 1 left the parts (``offset``)."""

    def __init__(self, *args, springs: "list[BoltSpring]", normal_scale: "np.ndarray | None" = None, drift: Any = None,
                 **kwargs):
        import numpy as np

        super().__init__(*args, **kwargs)
        self.springs = springs
        self.offset = np.zeros(self.size)
        self.locked = False
        self.stuck = np.zeros((self.constraints.count, 3))
        #: (rows,) the normal penalty's share of each row's own penalty: rows whose ``penalty`` was softened for
        #: friction keep their normal penalty whole this way.
        self.normal_scale = np.ones(self.constraints.count) if normal_scale is None else np.asarray(normal_scale, dtype=float)
        #: Springs to ground on the step-2 displacement only (from the locked state), every direction: what keeps a
        #: part whose joint opens from tilting or drifting along the bolt, with nothing of the preload in them.
        self.drift = drift

    def lock(self, u: "np.ndarray", external: "np.ndarray", friction: "np.ndarray | None" = None) -> None:
        """Lock each shank where step 1 left it (carrying its preload) and take ``external`` as step 2's load.

        ``friction`` (per contact row) turns friction on from here: step 1 tightens the bolts with the clamped faces
        sliding freely (they settle as the nut turns, and their Poisson bulge under the preload slips anyway), and
        from the locked state they stick until the sideways load makes them slip."""
        import numpy as np

        if friction is not None:
            self.constraints.friction = np.asarray(friction, dtype=float).copy()
            self.state.slip = self.response(u).sliding.copy()
        self.offset = u.copy()
        for spring in self.springs:
            spring.stretch0 = spring.stretch(u)
        self.locked = True
        self.external = external

    def commit(self, u, factor):
        """Contact's commit (the Uzawa updates), keeping first the tangential forces of the step's solve with every
        touching point stuck (``stuck``): the sideways force the faces must carry for the joint to hold, which a
        joint that slips cannot settle into."""
        self.stuck = self.response(u).tangential.copy()
        super().commit(u, factor)

    def full(self, u: "np.ndarray") -> "np.ndarray":
        return u + self.offset

    def response(self, u, *, tangent: bool = False):
        from cadgen._internal.fea.contact_ops import respond

        return respond(self.constraints, u + self.offset, self.state, self.vdofs, tangent=tangent,
                       scale=self.scale * self.normal_scale, stick=self.stick)

    def evaluate(self, u, *, tangent):
        full = u + self.offset
        response = self.response(u, tangent=tangent)
        internal = self.stiffness @ full + response.force
        matrix = (self.stiffness + response.matrix) if tangent else None
        if self.locked and self.drift is not None:
            internal = internal + self.drift @ u
            if tangent:
                matrix = matrix + self.drift
        if self.locked:
            for spring in self.springs:
                force = spring.force(full)
                if force > 0:
                    internal[spring.index] += force * spring.value
                    if tangent:
                        matrix = matrix + spring.outer(self.size)
        return internal, (matrix.tocsr() if tangent else None)

    def forces(self, full: "np.ndarray") -> list[float]:
        """Each bolt's force at the full displacement ``full`` (its preload before the lock)."""
        return [spring.force(full) if self.locked else spring.preload for spring in self.springs]


def drift_springs(stiffness, vdofs: "np.ndarray", bodies: "list[tuple[np.ndarray, np.ndarray | None]]", share: float):
    """Springs to ground holding each body that nothing fixes from drifting, ``share`` of its mean stiffness (diagonal)
    per node: ``bodies`` are (its scalar DOFs, the bolt axis it is clamped along or None). A bolted body's spring is
    across the axis only, so the preload, which moves it along the axis, loads none of it (a spring there would be a
    support the study does not have); contact and the bolt hold it along the axis."""
    import numpy as np
    import scipy.sparse as sparse

    size = stiffness.shape[0]
    diagonal = np.abs(stiffness.diagonal())
    rows, cols, data = [], [], []
    for nodes, axis in bodies:
        if not len(nodes):
            continue
        k = share * float(diagonal[vdofs[nodes].ravel()].mean())
        block = np.eye(3) if axis is None else np.eye(3) - np.outer(axis, axis)
        for i in range(3):
            for j in range(3):
                if abs(block[i, j]) > 1e-15:
                    rows.append(vdofs[nodes, i])
                    cols.append(vdofs[nodes, j])
                    data.append(np.full(len(nodes), k * block[i, j]))
    if not data:
        return sparse.csr_matrix((size, size))
    return sparse.coo_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(size, size)).tocsr()
