"""Heat carried by a flow: the fluid's energy equation, coupled to conduction in the part, solved as one system.

The flow is solved first (:mod:`.navier_stokes` or :mod:`.turbulence`) and is
not changed by the heat (constant properties, no buoyancy). The fluid's
temperature then obeys steady advection-diffusion,

    ρ c_p u · ∇T − ∇ · ((k + ρ c_p ν_t / Pr_t) ∇T) = 0,

on linear tetrahedra over the fluid mesh (the corner vertices of its quadratic
elements), stabilised by SUPG (the streamline upwind / Petrov-Galerkin test
function, Shakib's time scale). Linear temperature is the Taylor-Hood pressure's
own space, so the discrete velocity is exactly divergence-free against it: the
heat the walls put in leaves through the outlets as m c_p ΔT, to the solver's
tolerance, with no loss to the discretisation. An inlet brings in fluid at its
temperature by Danckwerts' condition (the enthalpy coming in is ρ c_p |u · n|
T_in, conducted and carried together), not by holding the inlet plane at
T_in: a held plane next to a hot wall would be a heat sink that is not there.
Outlets and walls that are not the part's let no heat through by conduction.
Walls carry no enthalpy across: where a wall function lets the velocity slip
(turbulent flow) or a side of an external box slips, the discrete u · n is not
exactly zero between nodes, so the advective flux it would carry out,
∫ ρ c_p (u · n) T v, is taken back on those faces (:func:`impermeable`). A
turbulent flow adds the eddy diffusivity ν_t / Pr_t (ν_t = k / ω,
Pr_t = 0.85).

The part's conduction is the thermal analysis's system (:mod:`.thermal_ops`) on
its own mesh. The two meshes do not match at the wetted wall, so they are tied
there by interpolation: each fluid wall vertex lies on the part's surface, and
its temperature is the part's quadratic temperature at that point (Π, the
part's surface triangle's shape functions at its closest point). For laminar
flow the tie is exact continuity: the fluid's wall temperatures are eliminated
(T_f,wall = Π T_s), and the heat their equations need goes into the part
through Πᵀ, which conserves it (each row of Π sums to 1). For turbulent flow the
wall-function layer sits between them, a film of the thermal law of the wall
(Jayatilleke's T⁺ = Pr_t (u⁺ + P)) at each wall vertex, h = ρ c_p u_τ / T⁺,
coupling the part's surface to the fluid's first layer, conservative in the
same way. Either way the whole is one sparse, non-symmetric linear system:
SuperLU, or GMRES with an incomplete-LU preconditioner (the ladder's
``iterative``), falling back to SuperLU if it stalls.

Units are the engine's: mm, s, mW, °C; ρ c_p in mJ/(mm³ K). Numeric imports
live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "Coupled", "FLUID_HEAT", "PRANDTL_T", "boundary_flux", "coupled_solve", "energy_matrix", "impermeable", "inflow",
    "interface_map", "lumped_area", "thermal_wall_film",
]

#: Fluids by name at 20 °C: thermal conductivity W/(m K) and specific heat J/(kg K) (Incropera, Fundamentals of
#: Heat and Mass Transfer, tables A.4 (air, 300 K) and A.6 (saturated water, 295 K)).
FLUID_HEAT = {"air": (0.0263, 1007.0), "water": (0.606, 4181.0)}
#: The turbulent Prandtl number of the eddy diffusivity and the thermal wall function.
PRANDTL_T = 0.85
#: The law of the wall's constants (as the turbulence model's wall function): κ, E.
KAPPA, E_WALL = 0.41, 9.793
#: GMRES on the coupled system: relative tolerance and iteration cap.
KRYLOV_TOL, MAX_KRYLOV = 1e-10, 2000


def energy_matrix(space, u: "np.ndarray", rho_cp: float, k: float, nu_t: "np.ndarray | None" = None):
    """The fluid's energy operator on linear elements over ``space`` (the fluid's quadratic space) at velocity
    ``u`` (its vector DOF, mm/s): advection, diffusion (with the eddy diffusivity from ``nu_t`` at the corner
    vertices, mm²/s) and SUPG. Returns the matrix (vertices × vertices) and the linear basis."""
    import numpy as np
    from skfem import BilinearForm, ElementTetP1, asm
    from skfem.helpers import dot, grad

    basis = space.basis.with_element(ElementTetP1())
    velocity = space.basis.interpolate(u)
    b = velocity.value                                       # (3, elements, quadrature)
    volume = np.asarray(basis.dx).sum(axis=1)
    h = np.cbrt(6.0 * math.sqrt(2.0) * volume)[:, None]       # the edge of a regular tet of that volume
    diffusivity = np.full(b.shape[1:], k / rho_cp)
    if nu_t is not None:
        diffusivity = diffusivity + basis.interpolate(np.maximum(nu_t, 0.0)).value / PRANDTL_T
    speed = np.linalg.norm(b, axis=0)
    tau = 1.0 / np.sqrt((2.0 * speed / h) ** 2 + 9.0 * (4.0 * diffusivity / h ** 2) ** 2 + 1e-300)

    @BilinearForm
    def transport(T, v, w):
        along = dot(w["b"], grad(T))
        return w["rc"] * (along * v + w["kappa"] * dot(grad(T), grad(v)) + w["tau"] * dot(w["b"], grad(v)) * along)

    A = asm(transport, basis, b=b, kappa=diffusivity, tau=tau, rc=np.full(b.shape[1:], rho_cp))
    return A.tocsr(), basis


def inflow(space, rows: "np.ndarray", u: "np.ndarray", rho_cp: float, celsius: float):
    """Danckwerts' inlet on boundary triangles ``rows``: the matrix ∫ ρ c_p |u · n|⁻ T v and the load
    ∫ ρ c_p |u · n|⁻ T_in v (|u · n|⁻ the speed coming in), on the linear temperature."""
    import numpy as np
    from skfem import BilinearForm, ElementTetP1, LinearForm, asm
    from skfem.helpers import dot

    facets = space.facets_of_rows(rows)
    vector = space.basis.boundary(facets)
    scalar = vector.with_element(ElementTetP1())
    velocity = vector.interpolate(u)

    @BilinearForm
    def taken(T, v, w):
        return rho_cp * np.maximum(-dot(w["u"], w.n), 0.0) * T * v

    @LinearForm
    def brought(v, w):
        return rho_cp * np.maximum(-dot(w["u"], w.n), 0.0) * celsius * v

    return asm(taken, scalar, u=velocity).tocsr(), asm(brought, scalar, u=velocity)


def impermeable(space, rows: "np.ndarray", u: "np.ndarray", rho_cp: float):
    """-∫ ρ c_p (u · n) T v over boundary triangles ``rows`` (walls, slip sides): what makes them carry no
    enthalpy across when the discrete velocity is not exactly tangential there. Zero where u is zero (no slip)."""
    from skfem import BilinearForm, ElementTetP1, asm
    from skfem.helpers import dot

    facets = space.facets_of_rows(rows)
    vector = space.basis.boundary(facets)
    scalar = vector.with_element(ElementTetP1())

    @BilinearForm
    def back(T, v, w):
        return -rho_cp * dot(w["u"], w.n) * T * v

    return asm(back, scalar, u=vector.interpolate(u)).tocsr()


def lumped_area(space, rows: "np.ndarray") -> "np.ndarray":
    """(vertices,) the area each corner vertex of boundary triangles ``rows`` carries (a third of each flat
    triangle's), mm²."""
    import numpy as np

    triangles = space.boundary_quadratic[rows][:, :3]
    corners = space.dof_locations[triangles]
    area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    out = np.zeros(space.vertices)
    np.add.at(out, triangles.ravel(), np.repeat(area / 3.0, 3))
    return out


def _shape(triangles: "np.ndarray", locations: "np.ndarray", bary: "np.ndarray") -> "np.ndarray":
    """(P, 6) or (P, 3) shape-function values at barycentric ``bary`` of each triangle's corners and mid-edge
    nodes (each mid node's corners found by place, not assumed)."""
    import numpy as np

    if triangles.shape[1] == 3:
        return bary
    pairs = ((0, 1), (1, 2), (0, 2))
    corner = locations[triangles[:, :3]]
    mids = locations[triangles[:, 3:]]
    halves = np.stack([0.5 * (corner[:, a] + corner[:, b]) for a, b in pairs], axis=1)
    which = np.argmin(np.linalg.norm(mids[:, :, None, :] - halves[:, None, :, :], axis=3), axis=2)   # (P, 3 mids)
    values = np.zeros((len(triangles), 6))
    values[:, :3] = bary * (2.0 * bary - 1.0)
    for m in range(3):
        a = np.array([pairs[k][0] for k in which[:, m]])
        b = np.array([pairs[k][1] for k in which[:, m]])
        rows = np.arange(len(triangles))
        values[:, 3 + m] = 4.0 * bary[rows, a] * bary[rows, b]
    return values


def interface_map(part_space, part_rows: "np.ndarray", points: "np.ndarray"):
    """(len(points), part scalar DOF) sparse: each point's temperature from the part's, by the shape functions of
    the closest of the part's surface triangles ``part_rows`` (its projection, clamped into the triangle). Each row
    sums to 1. Returns the matrix and each point's distance from the surface, mm."""
    import numpy as np
    from scipy import sparse
    from scipy.spatial import cKDTree

    triangles = part_space.boundary_quadratic[part_rows]
    locations = part_space.dof_locations
    corners = locations[triangles[:, :3]]
    centroid = corners.mean(axis=1)
    near = min(8, len(triangles))
    _, candidates = cKDTree(centroid).query(points, k=near)
    candidates = np.asarray(candidates).reshape(len(points), near)
    best = np.zeros(len(points), dtype=np.int64)
    best_bary = np.zeros((len(points), 3))
    best_score = np.full(len(points), np.inf)
    for column in range(near):
        tri = corners[candidates[:, column]]
        e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        d = points - tri[:, 0]
        a11, a12, a22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
        b1, b2 = (d * e1).sum(1), (d * e2).sum(1)
        det = np.where(np.abs(a11 * a22 - a12 * a12) > 1e-300, a11 * a22 - a12 * a12, 1e-300)
        s = (a22 * b1 - a12 * b2) / det
        t = (a11 * b2 - a12 * b1) / det
        bary = np.stack([1.0 - s - t, s, t], axis=1)
        size = np.sqrt(np.maximum(a11, a22))
        normal = np.cross(e1, e2)
        normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-300)[:, None]
        off = np.abs((d * normal).sum(1))
        outside = np.clip(-bary, 0.0, None).sum(1) * size
        score = off + outside
        better = score < best_score
        best[better] = candidates[better, column]
        best_bary[better] = bary[better]
        best_score[better] = score[better]
    bary = np.clip(best_bary, 0.0, None)
    bary /= np.maximum(bary.sum(axis=1), 1e-300)[:, None]
    chosen = triangles[best]
    values = _shape(chosen, locations, bary)
    rows = np.repeat(np.arange(len(points)), chosen.shape[1])
    matrix = sparse.csr_matrix((values.ravel(), (rows, chosen.ravel())), shape=(len(points), part_space.scalar_count))
    return matrix, best_score


def thermal_wall_film(rho: float, cp: float, nu: float, k: float, u_tau: "np.ndarray", slip: "np.ndarray") -> "np.ndarray":
    """The thermal law of the wall's film at each wall vertex, mW/(mm² K): h = ρ c_p u_τ / T⁺, with
    T⁺ = Pr_t (u⁺ + P(Pr / Pr_t)) and u⁺ = |slip| / u_τ (Jayatilleke's P = 9.24 ((Pr/Pr_t)^0.75 - 1)(1 + 0.28 e^(-0.007 Pr/Pr_t)))."""
    import numpy as np

    prandtl = rho * cp * nu / k
    ratio = prandtl / PRANDTL_T
    jump = 9.24 * (ratio ** 0.75 - 1.0) * (1.0 + 0.28 * math.exp(-0.007 * ratio))
    u_plus = np.linalg.norm(slip, axis=1) / np.maximum(u_tau, 1e-300)
    t_plus = np.maximum(PRANDTL_T * (u_plus + jump), prandtl * 1.0)
    return rho * cp * u_tau / t_plus


@dataclass
class Coupled:
    """The coupled solve's answer: the part's temperatures (its scalar DOF), the fluid's (its corner vertices),
    the heat each coupled fluid wall vertex takes in (mW), and how it was solved."""

    solid: "np.ndarray"
    fluid: "np.ndarray"
    wall_nodes: "np.ndarray"
    wall_power: "np.ndarray"
    inlet_power: float
    how: str
    warnings: list[str] = field(default_factory=list)


def coupled_solve(K_s, f_s, solid_fixed: tuple["np.ndarray", "np.ndarray"], A_f, fluid_fixed: tuple["np.ndarray", "np.ndarray"],
                  wall_nodes: "np.ndarray", Pi, *, f_f: "np.ndarray | None" = None, film_matrix=None,
                  solver: str = "direct") -> Coupled:
    """Solve the part (K_s T_s = f_s, ``solid_fixed`` held) and the fluid (A_f T_f = f_f, ``fluid_fixed`` held)
    tied at ``wall_nodes`` (fluid vertices) by Π (rows: wall nodes; columns: the part's DOF).

    Without ``film_matrix`` the tie is continuity (T_f,wall = Π T_s), eliminated; with it (the fluid's boundary
    mass weighted by the wall film, vertices × vertices) the two are joined through that film.
    """
    import numpy as np
    from scipy import sparse

    Ns, Nf = K_s.shape[0], A_f.shape[0]
    f_f = np.zeros(Nf) if f_f is None else np.asarray(f_f, dtype=float)
    warnings: list[str] = []
    wall_nodes = np.asarray(wall_nodes, dtype=np.int64)
    Pi = sparse.csr_matrix(Pi)
    if film_matrix is None:
        others = np.setdiff1d(np.arange(Nf), wall_nodes)
        position = np.full(Nf, -1, dtype=np.int64)
        position[others] = np.arange(len(others))
        select = sparse.csr_matrix((np.ones(len(others)), (others, np.arange(len(others)))), shape=(Nf, len(others)))
        place = sparse.csr_matrix((np.ones(len(wall_nodes)), (wall_nodes, np.arange(len(wall_nodes)))), shape=(Nf, len(wall_nodes)))
        Qf = sparse.hstack([place @ Pi, select]).tocsr()
        Q = sparse.vstack([sparse.hstack([sparse.identity(Ns), sparse.csr_matrix((Ns, len(others)))]), Qf]).tocsr()
        A_full = sparse.block_diag([K_s, A_f]).tocsr()
        A = (Q.T @ A_full @ Q).tocsr()
        b = Q.T @ np.concatenate([f_s, f_f])
        fluid_held = position[fluid_fixed[0]]
        keep = fluid_held >= 0
        fixed = np.concatenate([solid_fixed[0], Ns + fluid_held[keep]]).astype(np.int64)
        values = np.concatenate([solid_fixed[1], fluid_fixed[1][keep]])
    else:
        Pfull = sparse.csr_matrix((np.ones(len(wall_nodes)), (wall_nodes, np.arange(len(wall_nodes)))), shape=(Nf, len(wall_nodes))) @ Pi
        M = sparse.csr_matrix(film_matrix)
        A = sparse.bmat([[K_s + Pfull.T @ M @ Pfull, -(Pfull.T @ M)], [-(M @ Pfull), A_f + M]], format="csr")
        b = np.concatenate([f_s, f_f])
        fixed = np.concatenate([solid_fixed[0], Ns + np.asarray(fluid_fixed[0], dtype=np.int64)]).astype(np.int64)
        values = np.concatenate([solid_fixed[1], fluid_fixed[1]])
        Q = None
    n = A.shape[0]
    x = np.zeros(n)
    fixed, first = np.unique(fixed, return_index=True)
    x[fixed] = values[first]
    free = np.setdiff1d(np.arange(n), fixed)
    A_ff = A[free][:, free].tocsc()
    rhs = b[free] - A[free][:, fixed] @ x[fixed]
    how = "superlu"
    solved = None
    if solver == "iterative":
        from scipy.sparse.linalg import LinearOperator, gmres, spilu

        try:
            ilu = spilu(A_ff, drop_tol=1e-5, fill_factor=20)
            M = LinearOperator(A_ff.shape, matvec=ilu.solve, dtype=float)
            guess, info = gmres(A_ff, rhs, M=M, rtol=KRYLOV_TOL, restart=200, maxiter=MAX_KRYLOV // 200 + 1)
            if info == 0 and np.all(np.isfinite(guess)) and np.linalg.norm(A_ff @ guess - rhs) <= 1e-7 * max(np.linalg.norm(rhs), 1e-300):
                solved, how = guess, "GMRES + incomplete LU"
        except RuntimeError:
            solved = None
        if solved is None:
            warnings.append("the iterative heat solver stalled, so the direct solver finished it")
    if solved is None:
        from scipy.sparse.linalg import splu

        solved = splu(A_ff).solve(rhs)
    x[free] = solved
    if not np.all(np.isfinite(x)):
        raise RuntimeError("the coupled heat solve produced non-finite temperatures")
    if Q is not None:
        full = Q @ x
        T_s, T_f = full[:Ns], full[Ns:]
        residual = A_f @ T_f - f_f
        wall_power = residual[wall_nodes]
    else:
        T_s, T_f = x[:Ns], x[Ns:]
        # The film carries M (Π T_s - T_f) into the fluid at its wall vertices (M lives on them alone).
        gap = np.zeros(Nf)
        gap[wall_nodes] = Pi @ T_s - T_f[wall_nodes]
        into = sparse.csr_matrix(film_matrix) @ gap
        wall_power = into[wall_nodes]
        residual = A_f @ T_f - f_f - into
    held = np.asarray(fluid_fixed[0], dtype=np.int64)
    held = held[~np.isin(held, wall_nodes)]
    inlet_power = float(residual[held].sum())
    return Coupled(solid=T_s, fluid=T_f, wall_nodes=wall_nodes, wall_power=wall_power, inlet_power=inlet_power,
                   how=how, warnings=warnings)


def boundary_flux(space, rows: "np.ndarray", u: "np.ndarray", T: "np.ndarray", rho_cp: float) -> tuple[float, float]:
    """Over boundary triangles ``rows`` of the fluid: the volume flow ∫ u · n (mm³/s) and the heat carried
    ∫ ρ c_p (u · n) T (mW), n out of the fluid, with the quadratic velocity and the linear temperature."""
    import numpy as np
    from skfem import ElementTetP1, Functional, asm
    from skfem.helpers import dot

    if len(rows) == 0:
        return 0.0, 0.0
    facets = space.facets_of_rows(rows)
    vector = space.basis.boundary(facets)
    scalar = vector.with_element(ElementTetP1())
    velocity = vector.interpolate(u)
    temperature = scalar.interpolate(T)

    @Functional
    def volume(w):
        return dot(w["u"], w.n)

    @Functional
    def heat(w):
        return dot(w["u"], w.n) * w["T"]

    flow = float(asm(volume, vector, u=velocity))
    carried = float(rho_cp * asm(heat, vector, u=velocity, T=temperature))
    return flow, carried
