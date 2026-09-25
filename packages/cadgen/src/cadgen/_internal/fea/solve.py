"""Linear static elasticity on a :class:`VolumeMesh`: scikit-fem assembly, pyamg solve.

Quadratic (10-node) tetrahedra, isotropic linear elasticity, small strain.
Fixed faces clamp every displacement component; a force is spread as a
uniform traction over its faces; a pressure acts along the inward normal.
The solve is algebraic multigrid (smoothed aggregation with the six rigid-body
modes as the near-nullspace) accelerated by conjugate gradients, which is what
makes a 150k-DOF part a seconds-long solve where SciPy's direct solver takes
minutes; small systems go straight to the direct solver.

Stress is recovered at the quadrature points from the displacement gradient,
von Mises is formed there, and its nodal field is the L2 projection onto the
quadratic scalar basis. Both maxima are reported: the Gauss-point value is
the higher and the more mesh-dependent of the two, and the difference between
them is itself a signal of a singularity or an under-resolved region.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.mesh import VolumeMesh
    from cadgen._internal.fea.study import Fixture, Load, Material

__all__ = ["SolveOutcome", "solve_linear_static"]

#: Above this many free DOF the command refuses rather than swap the machine.
DOF_LIMIT = 1_500_000
#: Above this many it warns that the solve will be slow.
DOF_WARN = 400_000
#: Below this many free DOF the direct solver wins on setup cost.
DIRECT_SOLVE_BELOW = 20_000

# The six local edges of a tetrahedron as corner pairs; the order is irrelevant
# here because every mid-edge node is matched to its corner pair by position.
_LOCAL_EDGES = ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))


@dataclass
class SolveOutcome:
    #: (M, 3) coordinates of every scalar DOF: corner vertices first, then edge midpoints.
    dof_locations: "np.ndarray"
    #: (M, 3) displacement at each DOF location, mm.
    displacement: "np.ndarray"
    #: (M,) von Mises at each DOF location, MPa (L2 projection).
    von_mises: "np.ndarray"
    #: The raw quadrature-point maximum, MPa.
    von_mises_gauss_max: float
    #: Corner-vertex count; ``dof_locations[:vertices]`` are the linear mesh's points.
    vertices: int
    #: (T, 4) corner connectivity in vertex ids.
    tets: "np.ndarray"
    #: (B, 3) boundary triangles in vertex ids, wound outward.
    boundary_triangles: "np.ndarray"
    #: (B, 6) the same triangles with their mid-edge nodes, in scalar DOF ids.
    boundary_quadratic: "np.ndarray"
    #: (B,) the face ordinal each boundary triangle lies on.
    boundary_ordinal: "np.ndarray"
    #: Per fixture (by index): reaction force vector in N.
    reactions: list[tuple[float, float, float]]
    #: Total applied force in N, summed over the loads.
    applied: tuple[float, float, float]
    dofs: int
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    solver: str = ""


def _vertex_mesh(volume: "VolumeMesh"):
    """scikit-fem's quadratic tet mesh from netgen's arrays, plus the maps between them."""
    import numpy as np
    from skfem import MeshTet1, MeshTet2

    corners = volume.tets[:, :4]
    used, inverse = np.unique(corners, return_inverse=True)
    vertices = len(used)
    node_to_vertex = np.full(len(volume.nodes), -1, dtype=np.int64)
    node_to_vertex[used] = np.arange(vertices)
    t = np.ascontiguousarray(inverse.reshape(corners.shape).T)
    p = np.ascontiguousarray(volume.nodes[used].T)
    linear = MeshTet1(p, t)

    # Which mid-edge node sits between which corner pair, by position: the one
    # nearest the pair's midpoint. A curved edge moves it off the midpoint by
    # far less than an edge length, so the choice is unambiguous.
    pairs = np.array(_LOCAL_EDGES)
    pc = volume.nodes[corners]                              # (E, 4, 3)
    mids = volume.nodes[volume.tets[:, 4:]]                 # (E, 6, 3)
    midpoints = 0.5 * (pc[:, pairs[:, 0]] + pc[:, pairs[:, 1]])
    distance = np.linalg.norm(midpoints[:, :, None, :] - mids[:, None, :, :], axis=-1)
    pick = distance.argmin(axis=2)                          # (E, 6): mid slot per local edge
    if not np.array_equal(np.sort(pick, axis=1), np.tile(np.arange(6), (len(pick), 1))):
        raise RuntimeError("could not pair the mesher's mid-edge nodes with element edges")
    mid_node = np.take_along_axis(volume.tets[:, 4:], pick, axis=1)  # (E, 6) node ids
    a = node_to_vertex[corners[:, pairs[:, 0]]]
    b = node_to_vertex[corners[:, pairs[:, 1]]]
    keys = np.minimum(a, b) * vertices + np.maximum(a, b)
    key_flat, first = np.unique(keys.ravel(), return_index=True)
    mid_flat = mid_node.ravel()[first]

    edges = linear.edges.astype(np.int64)                    # (2, ne) vertex ids
    edge_keys = np.minimum(edges[0], edges[1]) * vertices + np.maximum(edges[0], edges[1])
    where = np.searchsorted(key_flat, edge_keys)
    if not np.array_equal(key_flat[where], edge_keys):
        raise RuntimeError("the mesher's edges and the element edges disagree")
    edge_mid = mid_flat[where]
    doflocs = np.hstack([p, volume.nodes[edge_mid].T])
    quadratic = MeshTet2(doflocs, t)
    # Every mesher node -> its scalar DOF: corners are vertices, mid-edge nodes
    # follow in skfem's edge order.
    node_to_dof = node_to_vertex.copy()
    node_to_dof[edge_mid] = vertices + np.arange(len(edge_mid))
    return quadratic, node_to_dof, vertices


def _facet_index(mesh, triangles: "np.ndarray", vertices: int) -> "np.ndarray":
    """skfem facet ids for boundary triangles given as sorted-able vertex triples."""
    import numpy as np

    facets = np.sort(mesh.facets.astype(np.int64), axis=0)
    keys = (facets[0] * vertices + facets[1]) * vertices + facets[2]
    order = np.argsort(keys)
    sorted_keys = keys[order]
    tri = np.sort(triangles.astype(np.int64), axis=1)
    wanted = (tri[:, 0] * vertices + tri[:, 1]) * vertices + tri[:, 2]
    where = np.searchsorted(sorted_keys, wanted)
    where = np.clip(where, 0, len(sorted_keys) - 1)
    if not np.array_equal(sorted_keys[where], wanted):
        raise RuntimeError("a boundary triangle of the mesher is not a facet of the element mesh")
    return order[where]


def _rigid_body_modes(locations: "np.ndarray", component: "np.ndarray") -> "np.ndarray":
    """The near-nullspace pyamg needs for elasticity: 3 translations, 3 rotations."""
    import numpy as np

    n = len(component)
    x, y, z = locations[:, 0], locations[:, 1], locations[:, 2]
    B = np.zeros((n, 6))
    for c in range(3):
        B[component == c, c] = 1.0
    # rotation about z: (-y, x, 0); about x: (0, -z, y); about y: (z, 0, -x)
    B[component == 0, 3] = -y[component == 0]
    B[component == 1, 3] = x[component == 1]
    B[component == 1, 4] = -z[component == 1]
    B[component == 2, 4] = y[component == 2]
    B[component == 0, 5] = z[component == 0]
    B[component == 2, 5] = -x[component == 2]
    return B


def _solve_system(K, f, free: "np.ndarray", locations: "np.ndarray", component: "np.ndarray", warnings: list[str]):
    """Displacement on the free DOF: direct for small systems, AMG+CG otherwise."""
    import numpy as np
    import scipy.sparse.linalg as spla

    Kff = K[free][:, free].tocsr()
    ff = f[free]
    if Kff.shape[0] < DIRECT_SOLVE_BELOW:
        return spla.spsolve(Kff.tocsc(), ff), "superlu"
    import pyamg

    B = _rigid_body_modes(locations[free], component[free])
    ml = pyamg.smoothed_aggregation_solver(Kff, B=B, symmetry="symmetric", strength="symmetric", max_coarse=500)
    residuals: list[float] = []
    u = ml.solve(ff, tol=1e-8, accel="cg", maxiter=600, residuals=residuals)
    relative = residuals[-1] / max(residuals[0], 1e-300) if residuals else 1.0
    if relative > 1e-6:
        warnings.append(
            f"the multigrid solve stopped at a relative residual of {relative:.1e} after {len(residuals)} "
            "iterations; falling back to the direct solver (slower). Check that the fixtures hold the part."
        )
        return spla.spsolve(Kff.tocsc(), ff), "superlu (after amg)"
    return u, f"amg+cg ({len(residuals)} iterations)"


def solve_linear_static(
    volume: "VolumeMesh",
    material: "Material",
    fixtures: "tuple[Fixture, ...]",
    loads: "tuple[Load, ...]",
    ordinal_of: dict[str, int],
    *,
    log=None,
) -> SolveOutcome:
    """Solve one study on a meshed occurrence. ``ordinal_of`` maps face refs to ordinals."""
    import numpy as np
    from skfem import Basis, ElementTetP2, ElementVector, LinearForm, asm
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    timings: dict[str, float] = {}
    warnings: list[str] = []
    started = time.perf_counter()
    mesh, node_to_dof, vertices = _vertex_mesh(volume)
    node_to_vertex = np.where(node_to_dof < vertices, node_to_dof, -1)
    element = ElementVector(ElementTetP2())
    basis = Basis(mesh, element)
    scalar = basis.with_element(ElementTetP2())
    timings["mesh_to_fem_s"] = time.perf_counter() - started
    if log:
        log(f"element mesh: {mesh.t.shape[1]} tets, {basis.N} DOF")
    if basis.N > DOF_LIMIT:
        raise RuntimeError(
            f"{basis.N} degrees of freedom is past the {DOF_LIMIT} limit; raise mesh.size_mm "
            f"(now {volume.max_h:.3g} mm) and run again"
        )
    if basis.N > DOF_WARN:
        warnings.append(f"{basis.N} degrees of freedom: expect a slow solve; a larger mesh.size_mm is usually enough")

    # DOF bookkeeping: skfem numbers scalar DOF vertices first, then edges.
    if not (np.array_equal(scalar.nodal_dofs[0], np.arange(vertices))
            and np.array_equal(scalar.edge_dofs[0], vertices + np.arange(mesh.edges.shape[1]))):
        raise RuntimeError("unexpected degree-of-freedom numbering in the element basis")
    scalar_count = vertices + mesh.edges.shape[1]
    locations = np.zeros((basis.N, 3))
    component = np.zeros(basis.N, dtype=np.int64)
    scalar_index = np.zeros(basis.N, dtype=np.int64)
    for c in range(3):
        for dofs, where in ((basis.nodal_dofs[c], scalar.nodal_dofs[0]), (basis.edge_dofs[c], scalar.edge_dofs[0])):
            locations[dofs] = mesh.doflocs[:, where].T
            component[dofs] = c
            scalar_index[dofs] = where

    boundary_vertices = node_to_vertex[volume.boundary[:, :3]]
    if (boundary_vertices < 0).any():
        raise RuntimeError("a boundary triangle references a node that is not a corner vertex")
    boundary_quadratic = node_to_dof[volume.boundary]
    if (boundary_quadratic < 0).any():
        raise RuntimeError("a boundary triangle references a node the element mesh does not know")

    def facets_of(refs) -> "np.ndarray":
        ordinals = [ordinal_of[ref] for ref in refs]
        mask = np.isin(volume.boundary_ordinal, ordinals)
        if not mask.any():
            raise RuntimeError(f"no boundary triangles lie on {', '.join(refs)}")
        return _facet_index(mesh, boundary_vertices[mask], vertices)

    # Stiffness
    started = time.perf_counter()
    lam, mu = lame_parameters(material.E, material.nu)
    K = asm(linear_elasticity(lam, mu), basis)
    timings["assemble_s"] = time.perf_counter() - started

    # Loads
    f = np.zeros(basis.N)
    applied = np.zeros(3)
    for load in loads:
        facet_basis = basis.boundary(facets_of(load.faces))
        area = float(facet_basis.dx.sum())
        if load.type == "force":
            traction = np.asarray(load.vector, dtype=float) / area
            applied += np.asarray(load.vector, dtype=float)

            @LinearForm
            def form(v, w, traction=traction):
                return traction[0] * v.value[0] + traction[1] * v.value[1] + traction[2] * v.value[2]

        else:
            pressure = float(load.pressure)

            @LinearForm
            def form(v, w, pressure=pressure):
                n = getattr(w.n, "value", w.n)
                return -pressure * (n[0] * v.value[0] + n[1] * v.value[1] + n[2] * v.value[2])

        contribution = asm(form, facet_basis)
        f += contribution
        if load.type == "pressure":
            applied += np.array([contribution[basis.nodal_dofs[c]].sum() + contribution[basis.edge_dofs[c]].sum() for c in range(3)])

    # Fixtures
    fixture_dofs = [basis.get_dofs(facets_of(fixture.faces)).all() for fixture in fixtures]
    fixed = np.unique(np.concatenate(fixture_dofs))
    free = np.setdiff1d(np.arange(basis.N), fixed)

    started = time.perf_counter()
    u = np.zeros(basis.N)
    u[free], solver = _solve_system(K, f, free, locations, component, warnings)
    timings["solve_s"] = time.perf_counter() - started
    if log:
        log(f"solved with {solver} in {timings['solve_s']:.1f}s")

    # Reactions: K u - f on the fixed DOF, summed per fixture and component.
    residual = K @ u - f
    reactions = []
    for dofs in fixture_dofs:
        reactions.append(tuple(float(residual[dofs][component[dofs] == c].sum()) for c in range(3)))

    # Stress recovery
    started = time.perf_counter()
    grad = basis.interpolate(u).grad                          # (3, 3, elements, quadrature)
    strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    stress = 2.0 * mu * strain
    for i in range(3):
        stress[i, i] += lam * trace
    s = stress
    von_mises_q = np.sqrt(
        0.5 * ((s[0, 0] - s[1, 1]) ** 2 + (s[1, 1] - s[2, 2]) ** 2 + (s[2, 2] - s[0, 0]) ** 2)
        + 3.0 * (s[0, 1] ** 2 + s[1, 2] ** 2 + s[0, 2] ** 2)
    )
    von_mises = np.maximum(scalar.project(von_mises_q), 0.0)
    displacement = np.zeros((scalar_count, 3))
    for c in range(3):
        displacement[scalar.nodal_dofs[0], c] = u[basis.nodal_dofs[c]]
        displacement[scalar.edge_dofs[0], c] = u[basis.edge_dofs[c]]
    timings["stress_s"] = time.perf_counter() - started

    return SolveOutcome(
        dof_locations=np.ascontiguousarray(mesh.doflocs.T),
        displacement=displacement,
        von_mises=von_mises,
        von_mises_gauss_max=float(von_mises_q.max()),
        vertices=vertices,
        tets=np.ascontiguousarray(mesh.t.T),
        boundary_triangles=boundary_vertices,
        boundary_quadratic=boundary_quadratic,
        boundary_ordinal=volume.boundary_ordinal,
        reactions=reactions,
        applied=tuple(float(x) for x in applied),
        dofs=int(basis.N),
        timings=timings,
        warnings=warnings,
        solver=solver,
    )
