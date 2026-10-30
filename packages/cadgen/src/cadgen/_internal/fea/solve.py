"""Linear static elasticity on a :class:`VolumeMesh`, solved by CalculiX (calculix.py).

Quadratic (10-node) tetrahedra, isotropic linear elasticity, small strain. Fixed faces clamp every displacement
component and rollers hold their normal (supports.py); a force is spread as a uniform traction over its faces and a
pressure acts along the inward normal, each integrated over the curved six-node boundary triangles into nodal forces;
gravity and acceleration are integrated over the curved ten-node elements the same way. CalculiX is given nodal forces
only, so the load applied is exactly their sum. CalculiX prints the displacement, the reactions and the stress
at each element's four integration points.

Von Mises is formed at the integration points. Its nodal field is each element's stress extrapolated linearly from
its four points to its corners (its mid-edge nodes take the mean of their two), von Mises taken there and averaged over
the elements at a node; in an assembly, over each part's elements alone, so stress jumps across a change of material as
it does in the part. Both maxima are reported: the integration-point value is the more mesh-dependent of the two, and
the difference between them is itself a signal of a singularity or an under-resolved region.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.mesh import VolumeMesh
    from cadgen._internal.fea.study import Fixture, Load, Material

__all__ = ["DOF_LIMIT", "DOF_WARN", "SolveOutcome", "dof_warning", "solve_linear_static"]

#: CalculiX's direct solver (SPOOLES) fills in as a direct solver does: 140k DOF took 10 s and 1.8 GB, 207k 74 s and
#: 4.3 GB. Above DOF_WARN a solve warns that it will be slow; above DOF_LIMIT the automatic finer re-solve is not
#: taken (:func:`run.finer_mesh_size`). A first solve this large is never refused.
DOF_WARN = 150_000
DOF_LIMIT = 250_000
# A six-point rule on the reference triangle (exact to degree 4): (ξ, η) and weights summing to its area, 1/2.
_A1, _B1, _W1 = 0.445948490915965, 0.091576213509771, 0.111690794839005
_A2, _B2, _W2 = 0.108103018168070, 0.816847572980459, 0.054975871827661
_TRIANGLE_POINTS = ((_A1, _A1), (1 - 2 * _A1, _A1), (_A1, 1 - 2 * _A1), (_B1, _B1), (1 - 2 * _B1, _B1), (_B1, 1 - 2 * _B1))
_TRIANGLE_WEIGHTS = (_W1,) * 3 + (_W2,) * 3


@dataclass
class SolveOutcome:
    #: (M, 3) the mesh's nodes: corner vertices first, then mid-edge nodes.
    dof_locations: "np.ndarray"
    #: (M, 3) displacement at each node, mm.
    displacement: "np.ndarray"
    #: (M,) von Mises at each node, MPa.
    von_mises: "np.ndarray"
    #: The raw integration-point maximum, MPa.
    von_mises_gauss_max: float
    #: Corner-vertex count; ``dof_locations[:vertices]`` are the linear mesh's points.
    vertices: int
    #: (T, 4) corner connectivity.
    tets: "np.ndarray"
    #: (B, 6) the boundary triangles with their mid-edge nodes.
    boundary_quadratic: "np.ndarray"
    #: Per fixture (by index): reaction force vector in N.
    reactions: list[tuple[float, float, float]]
    #: Total applied force in N, summed over the loads.
    applied: tuple[float, float, float]
    dofs: int
    #: (T, 10) each element's ten nodes, for reading a part's share of the fields.
    element_dofs: "np.ndarray"
    #: (T,) the largest von Mises at each element's integration points, MPa.
    element_von_mises_gauss: "np.ndarray"
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    solver: str = ""
    #: For an assembly, (parts, M): each part's own von Mises field, from its elements alone (zero off the part), so
    #: stress jumps across a change of material as it does in the part. ``von_mises`` is then their envelope.
    von_mises_parts: "np.ndarray | None" = None


def dof_warning(dofs: int, automatic: bool, small_feature_mm: float | None = None) -> str:
    """The slow-solve warning; the automatic finer re-solve chose its own size, so it never blames the person's.

    ``small_feature_mm`` is set when small features, not the element size, drove the mesh: then a larger size is no cure.
    """
    if automatic:
        return f"the automatic finer check used {dofs} degrees of freedom, so this study took longer"
    if small_feature_mm is not None:
        return (
            f"{dofs} degrees of freedom: expect a slow solve; small features (thin walls, fillets, chamfers) set the mesh here "
            f"(elements down to {small_feature_mm:.2g} mm), so a larger mesh.size_mm won't help much"
        )
    return f"{dofs} degrees of freedom: expect a slow solve; a larger mesh.size_mm is usually enough"


def _surface_quadrature(points: "np.ndarray", triangles: "np.ndarray") -> "tuple[np.ndarray, np.ndarray]":
    """``(weights, normals)`` for the six-node ``triangles`` (corners, then the nodes on edges 1-2, 0-2, 0-1, as the
    mesher writes them): ``weights`` (B, P, 6) is ∫ N_i dA at each rule point (summing to each triangle's area over P
    and i), ``normals`` (B, P, 3) the outward unit normal there."""
    import numpy as np

    c0, c1, c2, m12, m02, m01 = (points[triangles[:, k]] for k in range(6))
    weights, normals = [], []
    for (xi, eta), w in zip(_TRIANGLE_POINTS, _TRIANGLE_WEIGHTS):
        l0, l1, l2 = 1.0 - xi - eta, xi, eta
        shape = np.array([l0 * (2 * l0 - 1), l1 * (2 * l1 - 1), l2 * (2 * l2 - 1), 4 * l1 * l2, 4 * l0 * l2, 4 * l0 * l1])
        d_xi = (-(4 * l0 - 1)) * c0 + (4 * l1 - 1) * c1 + 4 * l2 * m12 - 4 * l2 * m02 + 4 * (l0 - l1) * m01
        d_eta = (-(4 * l0 - 1)) * c0 + (4 * l2 - 1) * c2 + 4 * l1 * m12 + 4 * (l0 - l2) * m02 - 4 * l1 * m01
        jacobian = np.cross(d_xi, d_eta)
        area = np.linalg.norm(jacobian, axis=1)
        weights.append(w * area[:, None] * shape[None, :])
        normals.append(jacobian / np.where(area > 0, area, 1.0)[:, None])
    return np.stack(weights, axis=1), np.stack(normals, axis=1)


def nodal_forces(volume: "VolumeMesh", loads: "tuple[Load, ...]", ordinal_of: dict[str, int]) -> "np.ndarray":
    """(N, 3) the face loads as nodal forces, N: a force as a uniform traction over its faces' area, a pressure
    (MPa, positive pushing in) along the inward normal."""
    import numpy as np

    forces = np.zeros((len(volume.nodes), 3))
    ordinal = np.asarray(volume.boundary_ordinal)
    boundary = np.asarray(volume.boundary)
    for load in loads:
        if load.body:
            continue
        rows = np.flatnonzero(np.isin(ordinal, [ordinal_of[ref] for ref in load.faces]))
        if not len(rows):
            raise ValueError(f"the {load.type} on {', '.join(load.faces)} lands on no element of the mesh")
        weights, normals = _surface_quadrature(volume.nodes, boundary[rows])
        if load.type == "force":
            traction = np.asarray(load.vector, dtype=float) / float(weights.sum())
            per_node = weights.sum(axis=1)[:, :, None] * traction           # (B, 6, 3)
        else:  # pressure, pushing in: along -n
            per_node = -float(load.pressure) * np.einsum("bpi,bpk->bik", weights, normals)
        np.add.at(forces, boundary[rows].ravel(), per_node.reshape(-1, 3))
    return forces


#: Body loads integrate over each element with this many Gauss points along each of a collapsed cube's three axes.
_BODY_POINTS = 4
#: Elements integrated at once, to keep the arrays small.
_CHUNK = 4096


def _tet_rule() -> "tuple[np.ndarray, np.ndarray]":
    """``(points, weights)`` on the reference tetrahedron (natural coordinates; weights summing to its volume, 1/6):
    Gauss-Legendre on the unit cube collapsed onto it, exact well past the degree of a curved ten-node element's
    ∫ N det J."""
    import numpy as np

    g, w = np.polynomial.legendre.leggauss(_BODY_POINTS)
    g, w = (g + 1.0) / 2.0, w / 2.0
    a, b, c = (axis.ravel() for axis in np.meshgrid(g, g, g, indexing="ij"))
    wa, wb, wc = (axis.ravel() for axis in np.meshgrid(w, w, w, indexing="ij"))
    points = np.c_[a * (1 - b) * (1 - c), b * (1 - c), c]
    return points, wa * wb * wc * (1 - b) * (1 - c) ** 2


def body_forces(volume: "VolumeMesh", density: "np.ndarray", accelerations: "Sequence[Sequence[float]]") -> "np.ndarray":
    """(N, 3) the body loads as nodal forces, N: each acceleration b (mm/s^2) as ∫ ρ b N_i dV over the curved elements,
    ``density`` (tonne/mm^3) per element."""
    import numpy as np

    from cadgen._internal.fea.calculix import NETGEN_EDGES

    total = np.sum(np.asarray(accelerations, dtype=float).reshape(-1, 3), axis=0)
    forces = np.zeros((len(volume.nodes), 3))
    if not np.any(total):
        return forces
    points, weights = _tet_rule()
    l = np.c_[1.0 - points.sum(axis=1), points]                                     # (Q, 4) barycentric
    shape = np.concatenate([l * (2 * l - 1), np.stack([4 * l[:, i] * l[:, j] for i, j in NETGEN_EDGES], axis=1)], axis=1)
    d_l = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    d_shape = np.concatenate([(4 * l - 1)[:, :, None] * d_l[None], np.stack(
        [4 * (l[:, i, None] * d_l[j] + l[:, j, None] * d_l[i]) for i, j in NETGEN_EDGES], axis=1)], axis=1)  # (Q, 10, 3)
    tets = np.asarray(volume.tets)
    for start in range(0, len(tets), _CHUNK):
        rows = tets[start:start + _CHUNK]
        x = volume.nodes[rows]                                                       # (E, 10, 3)
        jacobian = np.einsum("eak,qal->eqkl", x, d_shape)                           # (E, Q, 3, 3)
        dv = np.abs(np.linalg.det(jacobian)) * weights                              # (E, Q)
        per_node = np.einsum("eq,qa->ea", dv, shape) * np.asarray(density)[start:start + _CHUNK, None]  # ∫ ρ N_a dV
        np.add.at(forces, rows.ravel(), (per_node[:, :, None] * total).reshape(-1, 3))
    return forces


def _corner_extrapolation() -> "np.ndarray":
    """(4, 4) the corner values of a linear field from its values at C3D10's four integration points (point k
    nearest corner k): the inverse of the corner shape functions there."""
    import numpy as np

    from cadgen._internal.fea.calculix import C3D10_POINTS

    return np.linalg.inv(np.array(C3D10_POINTS))


def _von_mises(s: "np.ndarray") -> "np.ndarray":
    """Von Mises of stresses ``(..., 6)`` ordered xx, yy, zz, xy, xz, yz."""
    import numpy as np

    xx, yy, zz, xy, xz, yz = (s[..., k] for k in range(6))
    return np.sqrt(np.maximum(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy ** 2 + xz ** 2 + yz ** 2), 0.0))


def solve_linear_static(volume: "VolumeMesh", material: "Material | Sequence[Material]",
                        fixtures: "tuple[Fixture, ...]", loads: "tuple[Load, ...]", ordinal_of: dict[str, int], *,
                        log=None, automatic: bool = False, body_loads: "Sequence[Sequence[float]]" = ()) -> SolveOutcome:
    """Solve one study on a meshed occurrence. ``ordinal_of`` maps face refs to ordinals.

    ``automatic`` marks the re-solve cadgen chose the size of, which words its warnings accordingly.
    For an assembly (``volume.domain`` set) ``material`` is one material per part, indexed by domain.
    ``body_loads`` are uniform body accelerations b in mm/s^2, each adding ∫ ρ b·v (gravity is b = g; a part
    accelerated by a carries b = -a); they count in ``applied``, so reactions still balance.
    """
    import numpy as np

    from cadgen._internal.fea import calculix
    from cadgen._internal.fea.mesh import small_feature_mm
    from cadgen._internal.fea.supports import check_held, supports_of

    timings: dict[str, float] = {}
    warnings: list[str] = []
    ccx = calculix.find_ccx()
    nodes, tets = np.asarray(volume.nodes), np.asarray(volume.tets)
    if tets.shape[1] != 10:
        raise ValueError("a static solve needs quadratic (10-node) tetrahedra")
    count = len(nodes)
    if log:
        log(f"element mesh: {len(tets)} tets, {3 * count} DOF")
    if 3 * count > DOF_WARN:
        warnings.append(dof_warning(3 * count, automatic, small_feature_mm(volume)))
    materials = list(material) if volume.domain is not None else [material]
    part_of = np.zeros(len(tets), dtype=np.int64) if volume.domain is None else np.asarray(volume.domain, dtype=np.int64)

    forces = nodal_forces(volume, loads, ordinal_of)
    if len(body_loads):
        forces += body_forces(volume, np.array([m.density for m in materials])[part_of], body_loads)
    applied = forces.sum(axis=0)
    supports = supports_of(volume, fixtures, ordinal_of)
    check_held(volume, supports)

    started = time.perf_counter()
    elements = calculix.c3d10_elements(nodes, tets)
    dat = calculix.run(ccx, lambda path: calculix.write_inp(
        path, nodes, elements, part_of, materials, supports.held(), supports.frames, forces))
    printed = calculix.read_dat(dat)
    timings["solve_s"] = time.perf_counter() - started
    if log:
        log(f"solved with {ccx.label} in {timings['solve_s']:.1f}s")

    displacement = np.zeros((count, 3))
    u = printed["U"]
    displacement[u[:, 0].astype(np.int64) - 1] = u[:, 1:4]
    # CalculiX's RF is the elements' force on a node (K u). The reaction is what the support adds, K u - f, along each
    # held direction only: along a direction a node is free in, K u is just the force applied there (a top edge's
    # load on a node held across it), and on a held one the load applied there (the clamped face's own weight) is
    # carried by the support too.
    reaction = np.zeros(3 * count)
    if "RF" in printed:
        rf = np.zeros((count, 3))
        rows = printed["RF"]
        rf[rows[:, 0].astype(np.int64) - 1] = rows[:, 1:4]
        for node, axis in supports.held():
            frame = supports.frames.get(node)
            if frame is None:
                reaction[3 * node + axis] = rf[node, axis] - forces[node, axis]
            else:
                along = frame[:, axis]
                reaction[3 * node:3 * node + 3] += (along @ (rf[node] - forces[node])) * along
    reactions = [tuple(float(reaction[dofs][dofs % 3 == c].sum()) for c in range(3)) for dofs in supports.per_fixture]

    started = time.perf_counter()
    stress = np.full((len(tets), 4, 6), np.nan)
    s = printed["S"]
    stress[s[:, 0].astype(np.int64) - 1, s[:, 1].astype(np.int64) - 1] = s[:, 2:8]
    if np.isnan(stress).any():
        raise RuntimeError("CalculiX's stresses leave elements out")
    at_points = _von_mises(stress)                                          # (T, 4)
    corners = np.einsum("ck,tkj->tcj", _corner_extrapolation(), stress)     # (T, 4, 6) at C3D10's corners
    mids = np.stack([(corners[:, i] + corners[:, j]) / 2.0 for i, j in calculix.C3D10_EDGES], axis=1)
    at_nodes = _von_mises(np.concatenate([corners, mids], axis=1))          # (T, 10), in C3D10's order

    def averaged(rows) -> "np.ndarray":
        total, seen = np.zeros(count), np.zeros(count)
        np.add.at(total, elements[rows].ravel(), at_nodes[rows].ravel())
        np.add.at(seen, elements[rows].ravel(), 1.0)
        return np.divide(total, seen, out=np.zeros(count), where=seen > 0)

    von_mises_parts = None
    if volume.domain is None:
        von_mises = averaged(slice(None))
    else:
        von_mises_parts = np.stack([averaged(part_of == index) for index in range(len(materials))])
        von_mises = von_mises_parts.max(axis=0)
    timings["stress_s"] = time.perf_counter() - started

    return SolveOutcome(
        dof_locations=nodes, displacement=displacement, von_mises=von_mises,
        von_mises_gauss_max=float(at_points.max()), vertices=int(tets[:, :4].max()) + 1, tets=tets[:, :4],
        boundary_quadratic=np.asarray(volume.boundary), reactions=reactions,
        applied=tuple(float(c) for c in applied), dofs=3 * count, element_dofs=tets,
        element_von_mises_gauss=at_points.max(axis=1), timings=timings, warnings=warnings, solver=ccx.label,
        von_mises_parts=von_mises_parts,
    )
