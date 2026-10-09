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

# netgen's 10-node tetrahedron lists the four corners, then the mid-edge nodes of
# edges (0,1) (0,2) (0,3) (1,2) (1,3) (2,3); skfem's quadratic tet wants them on
# edges (0,1) (1,2) (0,2) (0,3) (1,3) (2,3). One fixed permutation maps the
# former to the latter -- the mesher does not vary its order.
NETGEN_TET10_TO_SKFEM = (0, 1, 2, 3, 4, 7, 5, 6, 8, 9)


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
    #: (B, 6) the boundary triangles with their mid-edge nodes, in scalar DOF ids.
    boundary_quadratic: "np.ndarray"
    #: Per fixture (by index): reaction force vector in N.
    reactions: list[tuple[float, float, float]]
    #: Total applied force in N, summed over the loads.
    applied: tuple[float, float, float]
    dofs: int
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    solver: str = ""


def _element_mesh(volume: "VolumeMesh"):
    """scikit-fem's quadratic tet mesh from netgen's arrays, and node -> scalar DOF.

    skfem renumbers on construction (corner vertices first, then edge nodes);
    the map back to the mesher's node ids falls out of its element DOF table.
    """
    import numpy as np
    from skfem import MeshTet2

    connectivity = np.ascontiguousarray(volume.tets[:, NETGEN_TET10_TO_SKFEM].T)
    mesh = MeshTet2(np.ascontiguousarray(volume.nodes.T), connectivity)
    node_to_dof = np.full(len(volume.nodes), -1, dtype=np.int64)
    node_to_dof[connectivity] = mesh.dofs.element_dofs
    if (node_to_dof < 0).any():
        raise RuntimeError("the mesher produced nodes that no element uses")
    return mesh, node_to_dof


class _FacetLookup:
    """skfem facet ids for boundary triangles given as vertex triples; the
    facet table is keyed once and reused for every fixture and load."""

    def __init__(self, mesh, vertices: int):
        import numpy as np

        self._vertices = vertices
        facets = np.sort(mesh.facets.astype(np.int64), axis=0)
        keys = (facets[0] * vertices + facets[1]) * vertices + facets[2]
        self._order = np.argsort(keys)
        self._keys = keys[self._order]

    def __call__(self, triangles: "np.ndarray") -> "np.ndarray":
        import numpy as np

        tri = np.sort(triangles.astype(np.int64), axis=1)
        wanted = (tri[:, 0] * self._vertices + tri[:, 1]) * self._vertices + tri[:, 2]
        where = np.clip(np.searchsorted(self._keys, wanted), 0, len(self._keys) - 1)
        if not np.array_equal(self._keys[where], wanted):
            raise RuntimeError("a boundary triangle of the mesher is not a facet of the element mesh")
        return self._order[where]


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
    mesh, node_to_dof = _element_mesh(volume)
    vertices = int(mesh.t.max()) + 1
    basis = Basis(mesh, ElementVector(ElementTetP2()))
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
    for c in range(3):
        for dofs, where in ((basis.nodal_dofs[c], scalar.nodal_dofs[0]), (basis.edge_dofs[c], scalar.edge_dofs[0])):
            locations[dofs] = mesh.doflocs[:, where].T
            component[dofs] = c

    boundary_quadratic = node_to_dof[volume.boundary]
    boundary_vertices = boundary_quadratic[:, :3]
    if (boundary_vertices >= vertices).any():
        raise RuntimeError("a boundary triangle's corner is not a corner vertex of the element mesh")
    facet_lookup = _FacetLookup(mesh, vertices)

    def facets_of(refs) -> "np.ndarray":
        ordinals = [ordinal_of[ref] for ref in refs]
        mask = np.isin(volume.boundary_ordinal, ordinals)
        if not mask.any():
            raise RuntimeError(f"no boundary triangles lie on {', '.join(refs)}")
        return facet_lookup(boundary_vertices[mask])

    # Stiffness
    started = time.perf_counter()
    lam, mu = lame_parameters(material.E, material.nu)
    K = asm(linear_elasticity(lam, mu), basis)
    timings["assemble_s"] = time.perf_counter() - started

    # Loads
    f = np.zeros(basis.N)
    for load in loads:
        facet_basis = basis.boundary(facets_of(load.faces))
        if load.type == "force":
            traction = np.asarray(load.vector, dtype=float) / float(facet_basis.dx.sum())

            @LinearForm
            def form(v, w, traction=traction):
                return traction[0] * v[0] + traction[1] * v[1] + traction[2] * v[2]

        else:
            pressure = float(load.pressure)

            @LinearForm
            def form(v, w, pressure=pressure):
                return -pressure * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

        f += asm(form, facet_basis)
    applied = tuple(float(f[component == c].sum()) for c in range(3))

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
    reactions = [
        tuple(float(residual[dofs][component[dofs] == c].sum()) for c in range(3))
        for dofs in fixture_dofs
    ]

    # Stress recovery
    started = time.perf_counter()
    grad = basis.interpolate(u).grad                          # (3, 3, elements, quadrature)
    strain = 0.5 * (grad + np.transpose(grad, (1, 0, 2, 3)))
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    s = 2.0 * mu * strain
    for i in range(3):
        s[i, i] += lam * trace
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
        boundary_quadratic=boundary_quadratic,
        reactions=reactions,
        applied=applied,
        dofs=int(basis.N),
        timings=timings,
        warnings=warnings,
        solver=solver,
    )
