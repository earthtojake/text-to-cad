"""Contact: node-to-surface pairing, the gap function and augmented Lagrange with Coulomb friction.

A contact pair is two parts meshed apart (nothing glued between them). One
part's surface is the *slave* side, the other part's surface the *master*
side. Small sliding: everything is paired once, on the undeformed geometry.

Each slave surface node gets one contact: a gap and, with friction, a sliding
displacement, both averaged over the slave surface around the node. The
average is integrated at twelve points on each slave triangle (a three-point
rule on each of its four corner triangles), each point paired with the
closest point of the master surface, found on flat triangles (a quadratic
boundary triangle is split into its four flat corner triangles, so a curved
master is followed to the mesh's own accuracy). At a point the gap is

    g = g0 + n · (Σ M_a u_a - Σ N_k u_k),

``n`` the master's outward normal there, ``M_a`` and ``N_k`` the slave and the
master triangle's own (quadratic) shape functions at the point and its closest
point, ``g0`` the gap before loading (an overlap no deeper than the contact
tolerance counts as touching, 0). A node's gap is these averaged with the
node's weight function (its hat on the corner triangles: positive, a share of
area for every node, corners and mid-edge nodes alike), over the node's share
of the paired area. A rigid plane is the same with no master nodes:
``g = n · (x + u - p0)``.

Why averaged gaps, and why so many points: a quadratic triangle carries a
uniform pressure on its mid-edge nodes alone (its corners take none), so
contacts at the slave *nodes* pass a force to a master meshed differently that
it does not see as a uniform pressure: flat blocks pressed together came out
30 % off between nodes. A contact at each integration point instead is over-
constrained (more points than nodes), so the points' own forces are not
unique, and friction, which caps each by μ times its own pressure, slips where
it should stick. Averaged gaps keep one contact per node and integrate the
force onto both sides consistently: flat blocks come out even to about 1 %.

The normal force at a node is augmented Lagrange: ``p = max(0, λ - ε g)`` with
the penalty ``ε`` scaled to the material and the node's area, and ``λ``
updated Uzawa-style (``λ ← p``) after each converged Newton solve, until it
stops changing: the penalty sets how fast it converges, not the answer.
Friction is Coulomb with a return map: the trial tangential force
``t = ε (s - s_slip)`` of the tangential relative displacement ``s`` sticks
while ``|t| ≤ μ p`` and slips on the cone, ``t = μ p t/|t|``, with the
consistent (unsymmetric) tangent of that return. The driver's linear solves
(SuperLU, or GMRES with AMG) take an unsymmetric matrix as it is.

:class:`ContactProblem` is a :class:`~.nonlinear_driver.NonlinearProblem`:
linear elastic parts, the contacts, and a very weak spring holding each body
nothing fixes (it rests only on contacts) against drifting where the contact
has no stiffness (sideways, frictionless). Its ``settle`` runs the Uzawa
updates at the converged load step and gives the driver the settled
displacement (or says it did not settle, and the driver cuts the step);
``commit`` keeps it. :func:`pressure_field` is each slave node's force over its
area, copied to the master side. Numeric imports live inside the functions.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = [
    "AUGMENT_TOLERANCE", "Constraints", "ContactProblem", "ContactResponse", "ContactState", "MAX_AUGMENTATIONS",
    "PENALTY", "PairSpec", "PlaneSpec", "body_of_nodes", "close_gaps", "closest_on_triangles", "pair_constraints",
    "plane_constraints", "pressure_field", "respond", "shape_weights", "stabilising_springs", "surface_triangles",
    "vector_dofs",
]

#: The penalty, ε = PENALTY · E · sqrt(node's area): stiff against the elements under the node, so a first solve
#: already presses in by about a ten-thousandth of the displacement, and a few Uzawa updates settle the rest.
PENALTY = 100.0
#: Uzawa updates at a load step stop once the normal forces change by less than this share (root mean square).
AUGMENT_TOLERANCE = 1e-2
#: Uzawa updates at most this many per load step (the stiffening ones included).
MAX_AUGMENTATIONS = 12
#: Each load step's first Newton solve uses this share of the normal penalty, and each Uzawa update stiffens it by
#: GROWTH up to the full value: a stiff penalty from a cold start chatters between open and closed points.
SOFT, GROWTH = 0.05, 4.0
#: A body that rests only on contacts is held by springs this share of its own mean stiffness (diagonal).
STABILISE = 1e-8
#: A slave triangle pairs with the master only where it faces it: the cosine between their normals under this.
FACING = -0.3
#: A closest point this far outside its triangle (in barycentric weight) is still taken as on it.
INSIDE = 0.05
#: Master triangles a point's closest point is looked for among (the nearest by centre).
CANDIDATES = 12
#: A quadratic triangle's four corner triangles, as indices into its nodes (c0 c1 c2 m01 m12 m20).
SUBTRIANGLES = ((0, 3, 5), (3, 1, 4), (5, 4, 2), (3, 4, 5))
#: Its nodes' barycentric weights in the triangle.
_NODE_WEIGHTS = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0.5, 0.5, 0), (0, 0.5, 0.5), (0.5, 0, 0.5))
_LOCAL = tuple(tuple(_NODE_WEIGHTS[k] for k in triangle) for triangle in SUBTRIANGLES)
#: Rounds of splitting each corner triangle in four before its three-point rule: the master's shape functions
#: kink across its own edges, inside a slave triangle, and only a fine rule passes them a uniform pressure evenly.
RULE_DEPTH = 2
#: Three points on a triangle exact to degree 2, in barycentric weights.
_THREE = ((2 / 3, 1 / 6, 1 / 6), (1 / 6, 2 / 3, 1 / 6), (1 / 6, 1 / 6, 2 / 3))


@dataclass(frozen=True)
class PairSpec:
    """One contact pair, resolved: the slave and master parts (domain indices), its friction and its index."""

    slave: int
    master: int
    friction: float
    index: int


@dataclass(frozen=True)
class PlaneSpec:
    """One rigid plane, resolved: a point, the unit normal (pointing to the parts' side), the parts it holds up."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    parts: tuple[int, ...]
    friction: float
    index: int


@dataclass
class Constraints:
    """Every slave node in contact with a master surface or a plane: one row each, vectorised."""

    #: (m,) which contact the row belongs to: a pair's index, or ``-1 - plane index`` for a plane.
    owner: "np.ndarray"
    #: (m,) the slave node (scalar DOF).
    node: "np.ndarray"
    #: (m, 3) where it is, before loading.
    position: "np.ndarray"
    #: (m, 3) unit normal, out of the master (or the plane) towards the slave.
    normal: "np.ndarray"
    #: (m,) the gap before loading, mm (>= 0).
    gap0: "np.ndarray"
    #: (m,) the paired area the node stands for, mm².
    area: "np.ndarray"
    #: (m,) the normal and tangential penalty, N/mm.
    penalty: "np.ndarray"
    #: (m,) Coulomb's μ.
    friction: "np.ndarray"
    #: (m, scalar DOF) CSR: the relative displacement of each row is ``weights @ u`` per component (slave nodes
    #: positive, master nodes negative).
    weights: Any

    @property
    def count(self) -> int:
        return int(len(self.owner))

    def master_nodes(self, rows) -> "np.ndarray":
        """The master nodes (scalar DOFs) rows ``rows`` (a mask or indices) lean on."""
        import numpy as np

        part = self.weights[rows].tocoo()
        return np.unique(part.col[part.data < 0])

    @classmethod
    def concatenate(cls, parts: "list[Constraints]", count: int) -> "Constraints":
        """The rows of every part, in order; ``count`` is the scalar DOF count (the weights' width)."""
        import numpy as np
        import scipy.sparse as sparse

        parts = [part for part in parts if part.count]
        if not parts:
            return cls(np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0),
                       np.zeros(0), np.zeros(0), np.zeros(0), sparse.csr_matrix((0, count)))
        names = ("owner", "node", "position", "normal", "gap0", "area", "penalty", "friction")
        return cls(*(np.concatenate([getattr(p, name) for p in parts]) for name in names),
                   sparse.vstack([p.weights for p in parts]).tocsr())


@dataclass
class ContactState:
    """What a converged step keeps: the multipliers (normal force, N) and the committed slip (mm)."""

    multiplier: "np.ndarray"
    slip: "np.ndarray"

    @classmethod
    def zeros(cls, count: int) -> "ContactState":
        import numpy as np

        return cls(np.zeros(count), np.zeros((count, 3)))


@dataclass
class ContactResponse:
    """The contacts at one displacement: the force on every DOF, the tangent, and what each row is doing."""

    force: "np.ndarray"
    matrix: Any
    gap: "np.ndarray"
    normal_force: "np.ndarray"
    tangential: "np.ndarray"      # (m, 3) tangential force
    sliding: "np.ndarray"         # (m, 3) tangential relative displacement
    pressing: "np.ndarray"        # a normal force on it
    slipping: "np.ndarray"


def vector_dofs(space: "FemSpace") -> "np.ndarray":
    """(scalar_count, 3) the vector DOF of each scalar DOF and component."""
    import numpy as np

    out = np.zeros((space.scalar_count, 3), dtype=np.int64)
    for c in range(3):
        out[space.scalar.nodal_dofs[0], c] = space.basis.nodal_dofs[c]
        if space.order == 2:
            out[space.scalar.edge_dofs[0], c] = space.basis.edge_dofs[c]
    return out


def body_of_nodes(space: "FemSpace") -> "tuple[np.ndarray, np.ndarray]":
    """(node part, node body): each scalar DOF's part (domain; 0 for one part) and its connected piece of mesh."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    elements = space.element_dofs                                   # (E, nodes per element)
    count = space.scalar_count
    first = np.repeat(elements[:, :1], elements.shape[1], axis=1).ravel()
    graph = sparse.coo_matrix((np.ones(first.size), (first, elements.ravel())), shape=(count, count))
    _, body = connected_components(graph, directed=False)
    part = np.zeros(count, dtype=np.int64)
    if space.domain is not None:
        part[elements.ravel()] = np.repeat(np.asarray(space.domain, dtype=np.int64), elements.shape[1])
    return part, body


def surface_triangles(space: "FemSpace", rows: "np.ndarray") -> "np.ndarray":
    """(B, 6) boundary triangles ``rows`` as scalar DOFs, outward by the right-hand rule: corners 0, 1, 2, then the
    mid-edge nodes of edges (0, 1), (1, 2), (2, 0); a linear triangle repeats its corners."""
    import numpy as np

    rows = np.asarray(rows)
    boundary = space.boundary_quadratic[rows]
    points = space.dof_locations
    corners = boundary[:, :3]
    # Outward: away from the tetrahedron the triangle bounds.
    element = space.mesh.f2t[0, space.facets_of_rows(rows)]
    centre = space.mesh.p[:, space.mesh.t[:, element]].mean(axis=1).T
    a, b, c = (points[corners[:, k]] for k in range(3))
    flip = np.einsum("ij,ij->i", np.cross(b - a, c - a), (a + b + c) / 3.0 - centre) < 0
    corners = np.where(flip[:, None], corners[:, [0, 2, 1]], corners)
    if boundary.shape[1] == 3:
        return np.concatenate([corners, corners], axis=1)
    # Each mid-edge node goes to the edge whose midpoint it is nearest, one node to each edge: of the six ways to
    # assign them, the nearest overall.
    mids = boundary[:, 3:]
    edge_mid = np.stack([(points[corners[:, i]] + points[corners[:, (i + 1) % 3]]) / 2.0 for i in range(3)], axis=1)
    distance = np.linalg.norm(points[mids][:, :, None, :] - edge_mid[:, None, :, :], axis=3)   # (B, mid, edge)
    orders = list(itertools.permutations(range(3)))                                          # orders[o][edge] = mid
    cost = np.stack([sum(distance[:, order[e], e] for e in range(3)) for order in orders], axis=1)
    best = np.asarray(orders)[cost.argmin(axis=1)]
    return np.concatenate([corners, np.take_along_axis(mids, best, axis=1)], axis=1)


def shape_weights(L: "np.ndarray", quadratic: bool) -> "np.ndarray":
    """(m, 6) a triangle's shape functions at barycentric ``L`` (m, 3): quadratic (corners, then the mid-edge nodes of
    edges (0, 1), (1, 2), (2, 0)), or linear (the corners, then three zeros)."""
    import numpy as np

    if not quadratic:
        return np.concatenate([L, np.zeros_like(L)], axis=1)
    l0, l1, l2 = L[:, 0], L[:, 1], L[:, 2]
    return np.stack([l0 * (2 * l0 - 1), l1 * (2 * l1 - 1), l2 * (2 * l2 - 1), 4 * l0 * l1, 4 * l1 * l2, 4 * l2 * l0], axis=1)


def _corner_triangles(quadratic: bool) -> "tuple[np.ndarray, np.ndarray]":
    """(k, 3) the flat triangles a triangle is split into, as indices into its six nodes, and (k, 3, 3) where their
    corners sit in it (barycentric): four for a quadratic triangle, itself for a linear one."""
    import numpy as np

    if quadratic:
        return np.asarray(SUBTRIANGLES), np.asarray(_LOCAL, dtype=float)
    return np.array([[0, 1, 2]]), np.eye(3)[None]


def _flat(space: "FemSpace", triangles: "np.ndarray") -> "tuple[np.ndarray, np.ndarray, np.ndarray]":
    """The flat triangles a surface is searched on: (k·B, 3) scalar DOFs, each one's parent row, and where its
    corners sit in the parent (k·B, 3, 3 barycentric)."""
    import numpy as np

    pieces, local = _corner_triangles(space.order == 2)
    k = len(pieces)
    flat = triangles[:, pieces].reshape(-1, 3)
    return flat, np.repeat(np.arange(len(triangles)), k), np.broadcast_to(local[None], (len(triangles), k, 3, 3)).reshape(-1, 3, 3).copy()


def _rule(depth: int) -> "tuple[np.ndarray, np.ndarray]":
    """Points on a triangle, barycentric, and each one's share of its area: the three-point rule on each triangle of
    ``depth`` rounds of splitting it in four (3 · 4^depth points)."""
    import numpy as np

    corners = [np.eye(3)]
    for _ in range(depth):
        corners = [np.asarray(_LOCAL) @ triangle for triangle in corners]
        corners = [piece for group in corners for piece in group]
    points = np.concatenate([np.asarray(_THREE) @ triangle for triangle in corners])
    return points, np.full(len(points), 1.0 / len(points))


def contact_points(space: "FemSpace", triangles: "np.ndarray"):
    """Each triangle's integration points: :data:`RULE_DEPTH` rounds of splitting each flat corner triangle, three
    points on each piece. Returns (P, 3) positions, (P, 6) the triangle's shape functions there, (P, 6) each node's
    averaging weight (its hat on the corner triangles), (P,) the area each point stands for, (P, 3) the triangle's
    outward normal and (P,) its row."""
    import numpy as np

    points = space.dof_locations
    pieces, local = _corner_triangles(space.order == 2)
    inner, share = _rule(RULE_DEPTH)                                               # in a corner triangle
    L = np.einsum("qk,tkj->tqj", inner, local).reshape(-1, 3)                      # in the triangle
    N = shape_weights(L, space.order == 2)
    hat = np.zeros((len(L), 6))
    for t, piece in enumerate(pieces):
        hat[t * len(inner):(t + 1) * len(inner)][:, piece] = inner
    nodes = points[triangles]                                                      # (B, 6, 3)
    position = np.einsum("qa,bac->bqc", N, nodes).reshape(-1, 3)
    a, b, c = nodes[:, 0], nodes[:, 1], nodes[:, 2]
    cross = np.cross(b - a, c - a)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    normal = cross / np.where(area > 0, 2.0 * area, 1.0)[:, None]
    count, each = len(triangles), len(L)
    weight = np.tile(share, len(pieces)) / len(pieces)
    return (position, np.broadcast_to(N[None], (count, each, 6)).reshape(-1, 6),
            np.broadcast_to(hat[None], (count, each, 6)).reshape(-1, 6), (area[:, None] * weight[None]).ravel(),
            np.repeat(normal, each, axis=0), np.repeat(np.arange(count), each))


def closest_on_triangles(P: "np.ndarray", A: "np.ndarray", B: "np.ndarray", C: "np.ndarray"):
    """The closest point of each triangle (A, B, C) to each point P, all (m, 3): (point, barycentric (m, 3) of that
    point, the unclamped projection's smallest barycentric weight)."""
    import numpy as np

    e0, e1 = B - A, C - A
    v = P - A
    d00 = np.einsum("ij,ij->i", e0, e0)
    d01 = np.einsum("ij,ij->i", e0, e1)
    d11 = np.einsum("ij,ij->i", e1, e1)
    d20 = np.einsum("ij,ij->i", v, e0)
    d21 = np.einsum("ij,ij->i", v, e1)
    determinant = d00 * d11 - d01 * d01
    denominator = np.where(np.abs(determinant) > 0, determinant, 1.0)
    beta = (d11 * d20 - d01 * d21) / denominator
    gamma = (d00 * d21 - d01 * d20) / denominator
    bary = np.stack([1.0 - beta - gamma, beta, gamma], axis=1)
    lowest = bary.min(axis=1)
    point = A + beta[:, None] * e0 + gamma[:, None] * e1
    out = lowest < 0
    if out.any():
        # Outside: the nearest point of the three edges.
        best = np.full(out.sum(), np.inf)
        best_point = np.zeros((out.sum(), 3))
        best_bary = np.zeros((out.sum(), 3))
        corners = (A[out], B[out], C[out])
        p = P[out]
        for i, j in ((0, 1), (1, 2), (2, 0)):
            start, edge = corners[i], corners[j] - corners[i]
            length = np.einsum("ij,ij->i", edge, edge)
            t = np.clip(np.einsum("ij,ij->i", p - start, edge) / np.where(length > 0, length, 1.0), 0.0, 1.0)
            q = start + t[:, None] * edge
            distance = np.linalg.norm(p - q, axis=1)
            better = distance < best
            best = np.where(better, distance, best)
            best_point[better] = q[better]
            weights = np.zeros((out.sum(), 3))
            weights[:, i] = 1.0 - t
            weights[:, j] = t
            best_bary[better] = weights[better]
        point[out] = best_point
        bary[out] = best_bary
    return point, bary, lowest


def _rows_of_part(space: "FemSpace", node_part: "np.ndarray", parts) -> "np.ndarray":
    import numpy as np

    return np.flatnonzero(np.isin(node_part[space.boundary_quadratic[:, 0]], list(parts)))


def _by_node(space: "FemSpace", owner: int, slave: "np.ndarray", hat: "np.ndarray", area: "np.ndarray",
             slave_N: "np.ndarray", master: "np.ndarray | None", master_N: "np.ndarray | None", normal: "np.ndarray",
             gap: "np.ndarray", E: "np.ndarray", friction: float) -> Constraints:
    """The paired points gathered onto the slave nodes (module docstring): each node's averaging weight over its
    paired area, its averaged normal and gap, and the weights of its relative displacement."""
    import numpy as np
    import scipy.sparse as sparse

    count = space.scalar_count
    omega = hat * area[:, None]                                                    # (P, 6) each point's pull on a node
    node_area = np.zeros(count)
    rows, cols, values = [], [], []
    for j in range(6):
        on = omega[:, j] > 0
        if not on.any():
            continue
        node_area += np.bincount(slave[on, j], weights=omega[on, j], minlength=count)
        for k in range(6):
            rows.append(slave[on, j])
            cols.append(slave[on, k])
            values.append(omega[on, j] * slave_N[on, k])
            if master is not None:
                rows.append(slave[on, j])
                cols.append(master[on, k])
                values.append(-omega[on, j] * master_N[on, k])
    nodes = np.flatnonzero(node_area > 0)
    raw = sparse.coo_matrix((np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))), shape=(count, count)).tocsr()
    scale = sparse.diags(1.0 / node_area[nodes])
    weights = (scale @ raw[nodes]).tocsr()
    weights.eliminate_zeros()

    def average(values_per_point):
        out = np.zeros(count)
        for j in range(6):
            out += np.bincount(slave[:, j], weights=omega[:, j] * values_per_point, minlength=count)
        return out[nodes] / node_area[nodes]

    n = np.stack([average(normal[:, k]) for k in range(3)], axis=1)
    n /= np.linalg.norm(n, axis=1)[:, None]
    stiffness = np.zeros(count)
    for j in range(6):
        stiffness += np.bincount(slave[:, j], weights=omega[:, j] * E, minlength=count)
    E_node = stiffness[nodes] / node_area[nodes]
    return Constraints(
        owner=np.full(len(nodes), owner, dtype=np.int64), node=nodes, position=space.dof_locations[nodes], normal=n,
        gap0=np.maximum(average(gap), 0.0), area=node_area[nodes], penalty=PENALTY * E_node * np.sqrt(node_area[nodes]),
        friction=np.full(len(nodes), float(friction)), weights=weights,
    )


def pair_constraints(space: "FemSpace", pair: PairSpec, node_part: "np.ndarray", E: float, *,
                     search_mm: float, tolerance_mm: float) -> Constraints:
    """The slave part's surface nodes against the master part's surface (module docstring).

    A slave point is paired when its closest point lies on (or just off, :data:`INSIDE`) a master triangle that its
    own triangle faces, no farther than ``search_mm`` and no deeper inside than ``tolerance_mm``."""
    import numpy as np
    from scipy.spatial import cKDTree

    points = space.dof_locations
    empty = Constraints.concatenate([], space.scalar_count)
    slave_rows = _rows_of_part(space, node_part, [pair.slave])
    master_rows = _rows_of_part(space, node_part, [pair.master])
    if not len(slave_rows) or not len(master_rows):
        return empty
    slaves = surface_triangles(space, slave_rows)
    masters = surface_triangles(space, master_rows)
    position, slave_N, hat, area, slave_normal, slave_of = contact_points(space, slaves)
    flat, parent, local = _flat(space, masters)
    A, B, C = (points[flat[:, k]] for k in range(3))
    centres = (A + B + C) / 3.0
    reach = float(np.max(np.linalg.norm(np.stack([A - centres, B - centres, C - centres]), axis=2)))
    # Candidates: the flat triangles whose centres are nearest the point, within the search distance plus a triangle.
    k = min(CANDIDATES, len(centres))
    distance, found = cKDTree(centres).query(position, k=k, distance_upper_bound=search_mm + reach)
    distance, found = distance.reshape(len(position), k), found.reshape(len(position), k)
    hit = np.isfinite(distance)
    if not hit.any():
        return empty
    point_of = np.nonzero(hit)[0]
    triangle = found[hit]
    P = position[point_of]
    closest, bary, lowest = closest_on_triangles(P, A[triangle], B[triangle], C[triangle])
    cross = np.cross(B[triangle] - A[triangle], C[triangle] - A[triangle])
    normal = cross / np.linalg.norm(cross, axis=1)[:, None]
    gap = np.einsum("ij,ij->i", P - closest, normal)
    span = np.linalg.norm(P - closest, axis=1)
    facing = np.einsum("ij,ij->i", slave_normal[point_of], normal) < FACING
    usable = facing & (lowest >= -INSIDE) & (gap <= search_mm) & (gap >= -tolerance_mm - 1e-9)
    if not usable.any():
        return empty
    # Each point's nearest usable triangle.
    score = np.where(usable, span, np.inf)
    order = np.lexsort((score, point_of))
    first = np.ones(len(order), dtype=bool)
    first[1:] = point_of[order][1:] != point_of[order][:-1]
    chosen = order[first]
    chosen = chosen[np.isfinite(score[chosen])]
    point = point_of[chosen]
    flat_index = triangle[chosen]
    # The closest point in the master's own triangle, and its shape functions there.
    master_N = shape_weights(np.einsum("mk,mkj->mj", bary[chosen], local[flat_index]), space.order == 2)
    return _by_node(space, pair.index, slaves[slave_of[point]], hat[point], area[point], slave_N[point],
                    masters[parent[flat_index]], master_N, normal[chosen], gap[chosen], np.full(len(point), E), pair.friction)


def plane_constraints(space: "FemSpace", plane: PlaneSpec, node_part: "np.ndarray", E_of_part: "dict[int, float]",
                      *, search_mm: float, tolerance_mm: float) -> Constraints:
    """The surface nodes of the plane's parts on triangles that face it, within ``search_mm`` of it."""
    import numpy as np

    empty = Constraints.concatenate([], space.scalar_count)
    rows = _rows_of_part(space, node_part, plane.parts)
    if not len(rows):
        return empty
    triangles = surface_triangles(space, rows)
    position, N, hat, area, normal_of, of = contact_points(space, triangles)
    n = np.asarray(plane.normal, dtype=float)
    gap = (position - np.asarray(plane.point, dtype=float)) @ n
    usable = (normal_of @ n < FACING) & (gap <= search_mm) & (gap >= -tolerance_mm - 1e-9)
    if not usable.any():
        return empty
    point = np.flatnonzero(usable)
    E = np.array([E_of_part[int(p)] for p in node_part[triangles[of[point], 0]]])
    return _by_node(space, -1 - plane.index, triangles[of[point]], hat[point], area[point], N[point], None, None,
                    np.repeat(n[None, :], len(point), axis=0), gap[point], E, plane.friction)


def respond(constraints: Constraints, u: "np.ndarray", state: ContactState, vdofs: "np.ndarray", *, tangent: bool,
            scale: float = 1.0, stick: bool = False) -> ContactResponse:
    """The contacts' force (and tangent) at ``u`` from the committed ``state``: augmented normal force, and the
    tangential force by a return map onto μ times the multiplier (fixed through a Newton solve, so stick and slip do
    not chase a pressure that moves with every iteration; the Uzawa updates bring it to μ p). The normal penalty is
    at ``scale`` times its own; the tangential one stays whole. ``stick`` holds every touching point from sliding
    (a step's first, soft solve). ``vdofs`` is :func:`vector_dofs`."""
    import numpy as np
    import scipy.sparse as sparse

    c = constraints
    m = c.count
    size = int(vdofs.size)
    if not m:
        empty = np.zeros(0)
        return ContactResponse(np.zeros(size), sparse.csr_matrix((size, size)) if tangent else None, empty, empty,
                               np.zeros((0, 3)), np.zeros((0, 3)), empty.astype(bool), empty.astype(bool))
    W = c.weights
    d = W @ u[vdofs]                                                      # (m, 3) relative displacement, slave minus master
    n = c.normal
    gap = c.gap0 + np.einsum("mc,mc->m", n, d)
    eps = c.penalty * scale
    trial = state.multiplier - eps * gap
    p = np.maximum(trial, 0.0)
    # Touching (or held closed by its multiplier) gives the tangent its stiffness, so a part resting with no gap is held.
    closed = (trial > 0) | (gap <= 0)
    pressing = trial > 0
    nn = n[:, :, None] * n[:, None, :]
    P = np.eye(3)[None] - nn                                              # (m, 3, 3) the tangent plane's projector
    sliding = np.einsum("mij,mj->mi", P, d)
    t = np.zeros((m, 3))
    slipping = np.zeros(m, dtype=bool)
    D = (eps * closed)[:, None, None] * nn if tangent else None
    rubbing = closed & (c.friction > 0)
    if rubbing.any():
        r = np.flatnonzero(rubbing)
        stiff = c.penalty[r]
        t_trial = stiff[:, None] * (sliding[r] - state.slip[r])
        size_t = np.linalg.norm(t_trial, axis=1)
        limit = c.friction[r] * state.multiplier[r]
        slip = (size_t > limit) & (not stick)
        e = np.where(size_t[:, None] > 0, t_trial / np.where(size_t > 0, size_t, 1.0)[:, None], 0.0)
        t[r] = np.where(slip[:, None], limit[:, None] * e, t_trial)
        slipping[r] = slip
        if tangent:
            stick_D = stiff[:, None, None] * P[r]
            ratio = np.where(size_t > 0, limit / np.where(size_t > 0, size_t, 1.0), 0.0)
            slip_D = (ratio * stiff)[:, None, None] * (P[r] - e[:, :, None] * e[:, None, :])
            D[r] += np.where(slip[:, None, None], slip_D, stick_D)
    relative = t - p[:, None] * n
    force = np.zeros(size)
    nodal = W.T @ relative                                                # (scalar DOF, 3)
    for k in range(3):
        force[vdofs[:, k]] = nodal[:, k]
    matrix = None
    if tangent:
        live = np.flatnonzero(closed)
        rows_out, cols_out, data = [], [], []
        if len(live):
            Wl = W[live]
            for i in range(3):
                for j in range(3):
                    if not np.any(D[live, i, j]):
                        continue
                    block = (Wl.T @ sparse.diags(D[live, i, j]) @ Wl).tocoo()
                    rows_out.append(vdofs[block.row, i])
                    cols_out.append(vdofs[block.col, j])
                    data.append(block.data)
        if data:
            matrix = sparse.coo_matrix((np.concatenate(data), (np.concatenate(rows_out), np.concatenate(cols_out))),
                                       shape=(size, size)).tocsr()
        else:
            matrix = sparse.csr_matrix((size, size))
    return ContactResponse(force, matrix, gap, p, t, sliding, pressing, slipping)


class ContactProblem:
    """Linear elastic parts in contact: what :func:`~.nonlinear_driver.solve_path` follows (module docstring).

    ``stiffness`` is the parts' (CSR, every DOF), ``free`` the DOF not fixed, ``external`` the full load,
    ``stabilise`` (size,) the weak springs of bodies held only by contacts. ``method`` is the driver's solver,
    which the Uzawa updates at each load step use too. ``on_commit(u, response)`` is told each converged
    step (after its Uzawa updates)."""

    def __init__(self, space: "FemSpace", stiffness, free: "np.ndarray", external: "np.ndarray",
                 constraints: Constraints, stabilise: "np.ndarray", *, method: str = "direct",
                 on_commit: "Callable[[np.ndarray, ContactResponse], None] | None" = None):
        import scipy.sparse as sparse

        self.space = space
        self.size = int(space.basis.N)
        self.free = free
        self.external = external
        self.locations = space.locations
        self.component = space.component
        self.constraints = constraints
        self.vdofs = vector_dofs(space)
        self.state = ContactState.zeros(constraints.count)
        self.stiffness = (stiffness + sparse.diags(stabilise)).tocsr()
        self.method = method
        self.on_commit = on_commit
        #: The normal penalty's share in use: soft for each load step's first Newton solve, full once Uzawa stiffens it.
        self.scale = SOFT
        #: A load step's first solve holds touching points from sliding; the Uzawa updates let them slip.
        self.stick = True
        #: Uzawa updates over the whole path, and the largest relative change in normal force left at the end of a step.
        self.augmentations = 0
        self.unsettled = 0.0
        #: What the last settle started from (rollback restores it) and the change it ended with (commit reads it).
        self._before = None
        self._change = None

    def evaluate(self, u, *, tangent):
        response = self.response(u, tangent=tangent)
        internal = self.stiffness @ u + response.force
        return internal, ((self.stiffness + response.matrix).tocsr() if tangent else None)

    def response(self, u, *, tangent: bool = False) -> ContactResponse:
        return respond(self.constraints, u, self.state, self.vdofs, tangent=tangent, scale=self.scale, stick=self.stick)

    def settle(self, u, factor):
        """Uzawa at this load step: λ ← p and solve again from ``u``, stiffening the penalties to their full value on
        the way (each solve starts next to its answer, so the stiff ones converge where a cold start may chatter
        between open and closed points), until the normal forces settle. Returns the settled displacement
        (:class:`~.nonlinear_driver.Settled`), ``settled`` False when a re-solve at the full penalty found no
        equilibrium: the forces there do not balance, and the driver cuts the step (:meth:`rollback`) or, at its
        smallest, keeps it marked. ``u`` is not changed."""
        import numpy as np

        from cadgen._internal.fea import nonlinear_driver as driver

        self._before = (self.state.multiplier.copy(), self.state.slip.copy(), self.scale, self.stick, self.augmentations)
        u = u.copy()
        change = 0.0
        stiffen = True
        settled = True
        for _ in range(MAX_AUGMENTATIONS):
            p = self.response(u).normal_force
            norm = float(np.linalg.norm(p))
            change = float(np.linalg.norm(p - self.state.multiplier)) / norm if norm > 0 else 0.0
            stiffer = stiffen and self.scale < 1.0
            if change <= AUGMENT_TOLERANCE and not stiffer:
                break
            kept = (self.state.multiplier, self.scale)
            self.state.multiplier = p.copy()
            self.stick = False
            if stiffer:
                self.scale = min(1.0, self.scale * GROWTH)
            found, _, _ = driver.newton(self, driver.LinearSolver(self, self.method), u, factor)
            if found is None:
                # A stiffening that did not converge stops stiffening; a re-solve at the full penalty that finds no
                # equilibrium leaves the forces unbalanced: the step did not settle.
                self.state.multiplier, self.scale = kept
                if not stiffer:
                    settled = False
                    break
                stiffen = False
                continue
            u = found
            self.augmentations += 1
        self._change = change
        return driver.Settled(u, settled)

    def rollback(self):
        """Forget what the last :meth:`settle` changed: the driver cuts the step and tries a smaller one."""
        multiplier, slip, self.scale, self.stick, self.augmentations = self._before
        self.state.multiplier, self.state.slip = multiplier, slip

    def commit(self, u, factor):
        """Keep the step at ``u`` (settled, or kept unsettled at the smallest step): the multipliers and the slip it
        reached, and tell ``on_commit``. A problem driven without :meth:`settle` settles here first."""
        import numpy as np

        if getattr(self, "_change", None) is None:
            u[:] = self.settle(u, factor).u
        change, self._change = self._change, None
        self.unsettled = max(self.unsettled, change if change > AUGMENT_TOLERANCE else 0.0)
        response = self.response(u)
        self.state.multiplier = response.normal_force.copy()
        rubbing = self.constraints.friction > 0
        if rubbing.any():
            eps = self.constraints.penalty
            self.state.slip = np.where(rubbing[:, None], response.sliding - response.tangential / eps[:, None], 0.0)
        self.scale, self.stick = SOFT, True
        if self.on_commit is not None:
            self.on_commit(u, response)


def close_gaps(constraints: Constraints, body_of_node: "np.ndarray", vdofs: "np.ndarray", external: "np.ndarray",
               floating: "list[int]") -> "np.ndarray":
    """Move each body that rests on contacts alone, rigidly, along its load until its nearest contact touches.

    A part placed a hair off another (or off a curve it touches at a point) has nothing to stand on at the first
    Newton step, and a step against its drift springs alone flings it far through the other part. The move is a
    rigid one, so it stresses nothing: ``constraints.gap0`` is updated in place, and the returned (size,) move is
    what the caller adds to the displacement it reports. ``body_of_node`` is each scalar DOF's body."""
    import numpy as np

    move = np.zeros(len(external))
    if not constraints.count:
        return move
    c = constraints
    for body in floating:
        on = body_of_node == body
        load = np.array([external[vdofs[on, k]].sum() for k in range(3)])
        size = float(np.linalg.norm(load))
        if not size > 0:
            continue
        direction = load / size
        # How fast each gap changes as the body moves along its load: its nodes' weights, along the normal.
        rate = (c.weights @ on.astype(float)) * (c.normal @ direction)
        closing = rate < -1e-12
        if not closing.any():
            continue
        travel = float((c.gap0[closing] / -rate[closing]).min())
        if not travel > 0:
            continue
        c.gap0 = np.maximum(c.gap0 + rate * travel, 0.0)
        for k in range(3):
            move[vdofs[on, k]] += travel * direction[k]
    return move


def stabilising_springs(stiffness, size: int, free_bodies: "list[np.ndarray]") -> "np.ndarray":
    """(size,) a spring on each DOF of the bodies held only by contacts: STABILISE times their mean diagonal."""
    import numpy as np

    springs = np.zeros(size)
    diagonal = stiffness.diagonal()
    for dofs in free_bodies:
        if len(dofs):
            springs[dofs] = STABILISE * float(np.abs(diagonal[dofs]).mean())
    return springs


def pressure_field(space: "FemSpace", constraints: Constraints, normal_force: "np.ndarray") -> "np.ndarray":
    """The contact pressure (MPa) at every scalar DOF: each slave node's normal force over its area; on the master
    side, the nearest slave node's; 0 elsewhere."""
    import numpy as np
    from scipy.spatial import cKDTree

    out = np.zeros(space.scalar_count)
    c = constraints
    if not c.count or not (normal_force > 0).any():
        return out
    np.maximum.at(out, c.node, normal_force / c.area)
    # The master side: the nearest slave node's pressure, within a node's spacing.
    for owner in np.unique(c.owner[c.owner >= 0]):
        mine = c.owner == owner
        slaves = c.node[mine]
        masters = c.master_nodes(mine)
        spacing = 2.0 * math.sqrt(float(c.area[mine].max()))
        distance, nearest = cKDTree(space.dof_locations[slaves]).query(space.dof_locations[masters])
        near = distance <= spacing
        out[masters[near]] = np.maximum(out[masters[near]], out[slaves[nearest[near]]])
    return out
