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
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.mesh import VolumeMesh
    from cadgen._internal.fea.study import Fixture, Load, Material

__all__ = ["SolveOutcome", "solve_linear_static"]

#: Above this many free DOF the command refuses rather than swap the machine.
DOF_LIMIT = 1_500_000
#: Above this many it warns that the solve will be slow.
DOF_WARN = 400_000
#: Multigrid attempts (one random seed each) before the direct solver takes over.
_AMG_ATTEMPTS = 3
#: Below this many free DOF the direct solver wins on setup cost.
DIRECT_SOLVE_BELOW = 20_000

# The mesher's 10-node tet order mapped to skfem's; it lives with the element space now.
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
    #: (T, 10) the scalar DOF ids of each element's ten nodes, for reading a part's share of the fields.
    element_dofs: "np.ndarray"
    #: (T,) the largest von Mises at each element's quadrature points, MPa.
    element_von_mises_gauss: "np.ndarray"
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    solver: str = ""
    #: For an assembly, (parts, M): each part's own von Mises field, projected from its elements alone
    #: (zero off the part), so stress jumps across a change of material as it does in the part.
    #: ``von_mises`` is then their envelope.
    von_mises_parts: "np.ndarray | None" = None
    #: (N,) the displacement on the vector DOF, as solved.
    u: "np.ndarray | None" = field(default=None, repr=False)


def _element_mesh(volume: "VolumeMesh"):
    """scikit-fem's quadratic tet mesh from netgen's arrays, and node -> scalar DOF (:func:`femspace.element_mesh`)."""
    from cadgen._internal.fea.femspace import element_mesh

    return element_mesh(volume, 2)


def _rigid_body_modes(locations: "np.ndarray", component: "np.ndarray") -> "np.ndarray":
    """The near-nullspace pyamg needs for elasticity (:func:`operators.rigid_body_modes`)."""
    from cadgen._internal.fea.operators import rigid_body_modes

    return rigid_body_modes(locations, component)


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


def _solve_system(K, f, free: "np.ndarray", locations: "np.ndarray", component: "np.ndarray", warnings: list[str], method: str | None = None):
    """Displacement on the free DOF: direct for small systems, AMG+CG otherwise (:func:`operators.solve_spd`)."""
    from cadgen._internal.fea.operators import solve_spd

    return solve_spd(K, f, free, locations, component, warnings, method=method)


def _project_on_elements(scalar, field: "np.ndarray", rows: "np.ndarray") -> "np.ndarray":
    """The L2 projection of a quadrature-point field onto the scalar basis, over the elements ``rows`` only.

    The basis is built on those elements alone, so a part's projection costs
    its own elements, not the whole mesh's. Zero on the DOF no such element uses.
    """
    import numpy as np
    import scipy.sparse.linalg as spla
    from skfem import Basis, BilinearForm, ElementTetP2, LinearForm, asm

    elements = np.flatnonzero(rows)
    own = Basis(scalar.mesh, ElementTetP2(), elements=elements, quadrature=scalar.quadrature, dofs=scalar.dofs)
    used = np.unique(own.element_dofs)

    @BilinearForm
    def mass(u, v, w):
        return u * v

    @LinearForm
    def moment(v, w):
        return w["field"] * v

    M = asm(mass, own).tocsr()[used][:, used]
    b = asm(moment, own, field=field[elements])[used]
    inverse_diagonal = 1.0 / M.diagonal()
    solution, info = spla.cg(M, b, rtol=1e-10, atol=0.0, M=spla.LinearOperator(M.shape, lambda x: inverse_diagonal * x), maxiter=500)
    if info != 0:
        solution = spla.spsolve(M.tocsc(), b)
    result = np.zeros(scalar.N)
    result[used] = np.maximum(solution, 0.0)
    return result


def solve_linear_static(
    volume: "VolumeMesh",
    material: "Material | Sequence[Material]",
    fixtures: "tuple[Fixture, ...]",
    loads: "tuple[Load, ...]",
    ordinal_of: dict[str, int],
    *,
    log=None,
    automatic: bool = False,
    body_loads: "Sequence[Sequence[float]]" = (),
    initial_strain=None,
    facet_pressures: "np.ndarray | None" = None,
    solver: str | None = None,
    space: "FemSpace | None" = None,
) -> SolveOutcome:
    """Solve one study on a meshed occurrence. ``ordinal_of`` maps face refs to ordinals.

    ``automatic`` marks the re-solve cadgen chose the size of, which words its warnings accordingly.
    For an assembly (``volume.domain`` set) ``material`` is one material per part, indexed by
    domain, and E and nu vary from element to element.

    The keywords default to today's solve. ``body_loads`` are uniform body
    accelerations b in mm/s^2, each adding ∫ ρ b·v (gravity is b = g; a part
    accelerated by a carries b = -a); they count in ``applied``, so reactions
    still balance. ``initial_strain`` is a stress-free strain at the vector
    basis's quadrature points ((elements, quadrature) isotropic, like α ΔT, or a
    (3, 3, elements, quadrature) tensor): its load is added and the stress is
    recovered from the elastic part. ``facet_pressures`` is one pressure (MPa,
    positive pushing in) per row of ``volume.boundary``. ``solver`` forces
    ``"direct"``, ``"iterative"`` or ``"matrix_free"``; ``space`` reuses a
    :class:`~cadgen._internal.fea.femspace.FemSpace` built on ``volume``.
    """
    import numpy as np
    from cadgen._internal.fea import operators
    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.mesh import small_feature_mm
    from skfem import LinearForm, asm

    timings: dict[str, float] = {}
    warnings: list[str] = []
    started = time.perf_counter()
    if space is None:
        space = FemSpace.build(volume)
    mesh, basis, scalar = space.mesh, space.basis, space.scalar
    timings["mesh_to_fem_s"] = time.perf_counter() - started
    if log:
        log(f"element mesh: {mesh.t.shape[1]} tets, {basis.N} DOF")
    if basis.N > DOF_LIMIT:
        raise RuntimeError(
            f"{basis.N} degrees of freedom is past the {DOF_LIMIT} limit; raise mesh.size_mm "
            f"(now {volume.max_h:.3g} mm) and run again"
        )
    if basis.N > DOF_WARN:
        warnings.append(dof_warning(basis.N, automatic, small_feature_mm(volume)))
    locations, component = space.locations, space.component
    materials = list(material) if volume.domain is not None else material

    def facets_of(refs) -> "np.ndarray":
        return space.facets_of(refs, ordinal_of)

    # Stiffness
    started = time.perf_counter()
    if solver == "matrix_free":
        K = operators.ElementChunkOperator(space, materials)
    else:
        K = operators.stiffness(space, materials)
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
    for acceleration in body_loads:
        f += operators.body_force(space, materials, acceleration)
    if facet_pressures is not None:
        pressures = np.asarray(facet_pressures, dtype=float)
        loaded = np.flatnonzero(pressures)
        if len(loaded):
            facets = space.facets_of_rows(loaded)
            facet_basis = basis.boundary(facets)
            on_facet = np.repeat(pressures[loaded][:, None], facet_basis.X.shape[1], axis=1)

            @LinearForm
            def surface(v, w):
                return -w["p"] * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

            f += asm(surface, facet_basis, p=on_facet)
    if initial_strain is not None:
        f += operators.initial_strain_load(space, materials, initial_strain)
    applied = tuple(float(f[component == c].sum()) for c in range(3))

    # Fixtures
    fixture_dofs = [basis.get_dofs(facets_of(fixture.faces)).all() for fixture in fixtures]
    fixed = np.unique(np.concatenate(fixture_dofs))
    free = np.setdiff1d(np.arange(basis.N), fixed)

    started = time.perf_counter()
    u = np.zeros(basis.N)
    method = {"direct": "direct", "iterative": "iterative"}.get(solver or "")
    u[free], how = _solve_system(K, f, free, locations, component, warnings, method)
    timings["solve_s"] = time.perf_counter() - started
    if log:
        log(f"solved with {how} in {timings['solve_s']:.1f}s")

    # Reactions: K u - f on the fixed DOF, summed per fixture and component.
    residual = K @ u - f
    reactions = [
        tuple(float(residual[dofs][component[dofs] == c].sum()) for c in range(3))
        for dofs in fixture_dofs
    ]

    # Stress recovery
    started = time.perf_counter()
    s = operators.stress(space, materials, u, initial_strain)
    von_mises_q = operators.von_mises(s)
    von_mises_parts = None
    if volume.domain is None:
        von_mises = np.maximum(scalar.project(von_mises_q), 0.0)
    else:
        von_mises_parts = np.zeros((len(material), scalar.N))
        for index in range(len(material)):
            von_mises_parts[index] = _project_on_elements(scalar, von_mises_q, np.asarray(volume.domain) == index)
        von_mises = von_mises_parts.max(axis=0)
    displacement = space.nodal(u)
    timings["stress_s"] = time.perf_counter() - started

    return SolveOutcome(
        dof_locations=space.dof_locations,
        displacement=displacement,
        von_mises=von_mises,
        von_mises_gauss_max=float(von_mises_q.max()),
        vertices=space.vertices,
        tets=space.tets,
        boundary_quadratic=space.boundary_quadratic,
        reactions=reactions,
        applied=applied,
        dofs=int(basis.N),
        element_dofs=space.element_dofs,
        element_von_mises_gauss=von_mises_q.max(axis=1),
        timings=timings,
        warnings=warnings,
        solver=how,
        von_mises_parts=von_mises_parts,
        u=u,
    )
