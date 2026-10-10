"""Steady RANS on the Taylor-Hood flow: k-omega SST with wall functions, by pseudo-transient continuation.

The mean flow is the laminar solver's pair (:mod:`.navier_stokes`): quadratic
velocity, linear pressure, on the fluid's quadratic tetrahedra, now with the
eddy viscosity added to the fluid's own,

    (u . grad) u - div((nu + nu_t) grad u) + grad p = 0,    div u = 0

(the pressure kinematic, p / rho; the momentum in the laminar solver's Laplacian
form, whose outlet condition stays "do nothing"). The eddy viscosity is Menter's
k-omega SST (2003): two scalar transport equations, for the turbulent kinetic
energy k and its specific dissipation omega, on linear elements on the same
mesh, with the SST blending (F1, F2) read from the wall distance, the production
limiter and the cross-diffusion term. They are convection-dominated, so both are
stabilised by SUPG (the streamline upwind / Petrov-Galerkin test function, with
the reaction and source terms in its residual).

Walls use wall functions, imposed the finite-element way: the velocity at a wall
slips tangentially (its normal part is held at zero, in a frame rotated to each
wall node's normal), and the wall pulls it back with the shear of the law of the
wall, tau_w = rho u_tau^2 along the slip, u_tau from Spalding's law at a
distance delta from the wall. delta is half the wall element's own depth, never
less than y+ 30 (the start of the log layer), so the first element always sits
in the log layer whatever the mesh. k and omega at the wall take their
log-layer values there: k = u_tau^2 / sqrt(beta*), omega = u_tau / (sqrt(beta*)
kappa delta), blended with the viscous omega.

The solve is pseudo-transient continuation: from a Stokes-like start with a
mixing-length eddy viscosity (internal flow) or the free stream's (external),
every step solves the mean flow with the eddy viscosity frozen and a local
pseudo-time term (CFL-limited), then k, then omega, each with the new velocity.
The pseudo-time step grows as the change per step shrinks (switched evolution
relaxation), so the march ends as plain Picard on the steady equations. It
stops when the velocity changes by under 1e-5 of the reference speed and k by
under 1e-4 of its largest value in one step; a run that does not get there
returns its last state and says how far it got.

Fully developed inflow: :func:`developed_turbulent` solves the same model on an
opening's own cross-section (the axial velocity, k and omega of a long straight
duct of that shape, at the inlet's mean speed), so an inlet can be fed as from a
long pipe. Its friction factor is the pipe's, to compare with Colebrook.

Units are the engine's: mm, s, tonne; viscosities kinematic, mm^2/s. Numeric
imports live inside the functions.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = ["BETA_STAR", "KAPPA", "RansProblem", "RansSolution", "YPLUS_LOG", "colebrook", "developed_turbulent",
           "inlet_turbulence", "solve_rans", "spalding_u_tau"]

#: The law of the wall: von Karman's constant and the log law's intercept (u+ = ln(y+) / kappa + B).
KAPPA, B = 0.41, 5.2
#: k-omega SST (Menter 2003): beta*, a1, and the inner (1) and outer (2) sets the blending F1 mixes.
BETA_STAR, A1 = 0.09, 0.31
INNER = {"alpha": 5.0 / 9.0, "beta": 0.075, "sigma_k": 0.85, "sigma_w": 0.5}
OUTER = {"alpha": 0.44, "beta": 0.0828, "sigma_k": 1.0, "sigma_w": 0.856}
#: The wall function's distance: this share of the wall element's depth, and never under this y+.
WALL_SHARE, YPLUS_LOG = 0.5, 30.0
#: A wall node whose facets' normals spread past this cosine is a sharp edge: held still, not slipping.
SHARP_COS = math.cos(math.radians(30.0))
#: The share of the wall function's new pull taken each step (the rest is the last step's).
ROBIN_RELAX = 0.5
#: The share of the new k and omega taken each step.
SCALAR_RELAX = 0.6
#: The march: the starting CFL and its growth per step that shrank the change; the default stopping tolerances.
CFL_START, CFL_GROWTH, CFL_MAX = 5.0, 2.0, 1e6
#: A step counts as progress when it shrinks the change below this share of the last; the CFL's floor.
SHRINK, CFL_MIN = 0.9, 0.5
#: After this many steps of progress in a row, the ceiling a stall set is doubled.
RECOVER = 10
VELOCITY_TOL, K_TOL = 1e-5, 1e-4
MAX_STEPS = 300
#: Krylov (the ladder's iterative rung): tolerance, restart and iteration cap of GMRES.
KRYLOV_TOL, RESTART, MAX_KRYLOV = 1e-9, 200, 3000
#: A kept factor preconditions GMRES on the next steps' matrices for at most this many iterations.
LAGGED_ITERATIONS = 40
#: ... to this relative residual: the march's own steps settle the flow, so each step's solve need not be exact.
LAGGED_TOL = 1e-8


def colebrook(reynolds: float, roughness_ratio: float = 0.0) -> float:
    """The Darcy friction factor of a full pipe from Colebrook-White (smooth by default): the Moody chart."""
    f = 0.02
    for _ in range(100):
        f_new = (-2.0 * math.log10(roughness_ratio / 3.7 + 2.51 / (reynolds * math.sqrt(f)))) ** -2
        if abs(f_new - f) < 1e-14:
            return f_new
        f = f_new
    return f


def blasius_u_tau(speed: float, length: float, nu: float) -> float:
    """A first guess of the friction velocity from Blasius (f = 0.316 Re^-1/4), for the start only."""
    reynolds = max(speed * length / nu, 1.0)
    return speed * math.sqrt(0.316 * reynolds ** -0.25 / 8.0)


def inlet_turbulence(speed: float, intensity: float, length: float, nu: float, *, viscosity_ratio: float | None = None):
    """(k, omega) of a stream at ``speed`` with turbulence ``intensity`` (0.05 = 5 %): k = 3/2 (I U)^2 and
    omega from a mixing length ``length`` (omega = sqrt(k) / (beta*^1/4 l)), or from an eddy-to-fluid
    viscosity ratio when one is given (a free stream's)."""
    k = max(1.5 * (intensity * speed) ** 2, 1e-12 * speed * speed + 1e-30)
    if viscosity_ratio is not None:
        return k, k / (viscosity_ratio * nu)
    return k, math.sqrt(k) / (BETA_STAR ** 0.25 * length)


def spalding_u_tau(speed, y, nu: float):
    """The friction velocity from Spalding's law of the wall, given the slip speed at distance ``y``.

    Spalding's single formula, y+ = u+ + e^(-kappa B) (e^(kappa u+) - 1 - kappa u+ - (kappa u+)^2/2 - (kappa u+)^3/6),
    holds through the viscous sublayer, the buffer and the log layer, so it needs no switch. Solved
    for u_tau by Newton's method, element-wise."""
    import numpy as np

    speed = np.maximum(np.asarray(speed, dtype=float), 1e-30)
    y = np.broadcast_to(np.asarray(y, dtype=float), speed.shape)
    e = math.exp(-KAPPA * B)
    # Start from the larger of the viscous and the log-layer guesses.
    u_tau = np.maximum(np.sqrt(nu * speed / y), speed / 25.0)
    for _ in range(50):
        up = speed / u_tau
        ku = np.minimum(KAPPA * up, 50.0)
        g = up + e * (np.exp(ku) - 1.0 - ku - 0.5 * ku ** 2 - ku ** 3 / 6.0) - y * u_tau / nu
        dg_dup = 1.0 + e * KAPPA * (np.exp(ku) - 1.0 - ku - 0.5 * ku ** 2)
        slope = -dg_dup * up / u_tau - y / nu
        step = g / slope
        new = u_tau - step
        u_tau = np.where(new > 0.2 * u_tau, np.where(new < 5.0 * u_tau, new, 5.0 * u_tau), 0.2 * u_tau)
        if float(np.abs(step).max(initial=0.0)) < 1e-12 * float(u_tau.max(initial=1.0)):
            break
    return u_tau


def _wall_omega(u_tau, delta, nu: float):
    """omega at the wall function's distance: the viscous and the log-layer values blended (Menter)."""
    import numpy as np

    viscous = 6.0 * nu / (INNER["beta"] * delta ** 2)
    log = u_tau / (math.sqrt(BETA_STAR) * KAPPA * delta)
    return np.sqrt(viscous ** 2 + log ** 2)


def _sst(k, grad_k, w, grad_w, s2, y, nu: float, floors: tuple[float, float], pinned=None):
    """The SST closure at points: eddy viscosity, F1, the blended coefficients and the cross-diffusion term.

    ``pinned`` (mask, omega) puts omega at its law-of-the-wall value in the elements touching a wall: omega
    falls as 1 / y there, far too steeply for a linear element to follow, and the element's straight line
    between the wall's value and the next node's would read it high all across the first element (the
    eddy viscosity low, the wall's pull and the pressure drop low with it). Wall-function codes set the
    wall cell's omega from the log law for the same reason."""
    import numpy as np

    k = np.maximum(k, floors[0])
    w = np.maximum(w, floors[1])
    if pinned is not None:
        w = np.where(pinned[0], pinned[1], w)
    dot = np.einsum("i...,i...->...", grad_k, grad_w)
    cd = np.maximum(2.0 * OUTER["sigma_w"] * dot / w, 1e-20)
    root = np.sqrt(k)
    viscous = 500.0 * nu / (y * y * w)
    arg1 = np.minimum(np.maximum(root / (BETA_STAR * w * y), viscous), 4.0 * OUTER["sigma_w"] * k / (cd * y * y))
    f1 = np.tanh(arg1 ** 4)
    arg2 = np.maximum(2.0 * root / (BETA_STAR * w * y), viscous)
    f2 = np.tanh(arg2 ** 2)
    nut = A1 * k / np.maximum(A1 * w, np.sqrt(s2) * f2)
    blend = {key: f1 * INNER[key] + (1.0 - f1) * OUTER[key] for key in INNER}
    cross = (1.0 - f1) * 2.0 * OUTER["sigma_w"] * dot / w
    return nut, f1, blend, cross, k, w


def _strain2(gradient):
    """2 S_ij S_ij from a velocity gradient (d, d, ...)."""
    import numpy as np

    sym = 0.5 * (gradient + np.swapaxes(gradient, 0, 1))
    return 2.0 * np.einsum("ij...,ij...->...", sym, sym)


def _supg_tau(speed, h, diffusion, reaction):
    """SUPG's time scale per point (Shakib's form, with the reaction rate)."""
    import numpy as np

    return 1.0 / np.sqrt((2.0 * speed / h) ** 2 + 9.0 * (4.0 * diffusion / h ** 2) ** 2 + reaction ** 2 + 1e-300)


def _scalar_forms():
    from skfem import BilinearForm, LinearForm
    from skfem.helpers import dot, grad

    @BilinearForm
    def transport(c, phi, w):
        b = w["b"]
        advect = dot(b, grad(c))
        rate = w["m"] + w["r"]
        return rate * c * phi + w["d"] * dot(grad(c), grad(phi)) + advect * phi + w["tau"] * dot(b, grad(phi)) * (advect + rate * c)

    @LinearForm
    def source(phi, w):
        return (w["s"] + w["m"] * w["old"]) * (phi + w["tau"] * dot(w["b"], grad(phi)))

    return transport, source


def _solve_scalar(basis, transport, source, coefficients, fixed, values, previous):
    """One transport solve (k or omega) with its Dirichlet nodes held."""
    import numpy as np
    from scipy.sparse.linalg import splu
    from skfem import asm

    A = asm(transport, basis, **coefficients).tocsr()
    rhs = asm(source, basis, **coefficients)
    x = np.zeros(basis.N)
    x[fixed] = values
    free = np.ones(basis.N, dtype=bool)
    free[fixed] = False
    b = rhs[free] - A[free][:, fixed] @ values
    x[free] = splu(A[free][:, free].tocsc()).solve(b)
    if not np.all(np.isfinite(x)):
        return previous
    return x


# -- fully developed flow on an opening ---------------------------------------------------------------


@dataclass
class Developed:
    """The settled turbulent flow of a long straight duct with an opening's cross-section."""

    w: dict[int, float]            # axial speed by scalar node, mm/s (mean: the inlet's speed)
    k: dict[int, float]            # by scalar node, mm^2/s^2
    omega: dict[int, float]        # by scalar node, 1/s
    friction_factor: float         # Darcy's f = (dp/dx) D_h / (rho U^2 / 2)
    gradient: float                # the kinematic pressure gradient that drives it, mm/s^2
    u_tau: float                   # the mean friction velocity on its wall, mm/s
    steps: int
    converged: bool


def _developed_on(mesh, speed: float, nu: float, *, max_steps: int = 400):
    """The developed duct flow on a triangle mesh (its whole boundary a wall): axial speed (P2), k and omega (P1)."""
    import numpy as np
    from scipy.sparse.linalg import splu
    from scipy.spatial import cKDTree
    from skfem import Basis, BilinearForm, ElementTriP1, ElementTriP2, FacetBasis, LinearForm, asm, condense, solve
    from skfem.helpers import dot, grad

    bw = Basis(mesh, ElementTriP2())
    bk = bw.with_element(ElementTriP1())
    walls = mesh.boundary_facets()
    fb = FacetBasis(mesh, ElementTriP2(), facets=walls)

    @BilinearForm
    def diffusion(u, v, w):
        return w["c"] * dot(grad(u), grad(v))

    @BilinearForm
    def mass(u, v, w):
        return w["c"] * u * v

    @LinearForm
    def load(v, w):
        return w["c"] * v

    one = asm(load, bw, c=1.0)
    area = float(one.sum())
    edge = mesh.p[:, mesh.facets[0, walls]] - mesh.p[:, mesh.facets[1, walls]]
    lengths = np.linalg.norm(edge, axis=0)
    perimeter = float(lengths.sum())
    diameter = 4.0 * area / perimeter
    e1 = mesh.p[:, mesh.t[1]] - mesh.p[:, mesh.t[0]]
    e2 = mesh.p[:, mesh.t[2]] - mesh.p[:, mesh.t[0]]
    tri_area = 0.5 * np.abs(e1[0] * e2[1] - e1[1] * e2[0])
    depth = 2.0 * tri_area[mesh.f2t[0, walls]] / lengths
    wall_nodes = np.unique(mesh.facets[:, walls])

    # Wall distance at every point the closure reads: to the wall's quadrature points.
    wall_points = fb.global_coordinates().value.reshape(2, -1).T
    tree = cKDTree(np.vstack([wall_points, mesh.p[:, wall_nodes].T]))
    owner = np.concatenate([np.repeat(np.arange(len(walls)), fb.global_coordinates().value.shape[2]),
                            np.full(len(wall_nodes), -1)])
    node_facets = [np.flatnonzero((mesh.facets[0, walls] == n) | (mesh.facets[1, walls] == n)) for n in wall_nodes]
    node_facets_first = np.array([facets[0] for facets in node_facets], dtype=np.int64)
    points = bk.global_coordinates().value.reshape(2, -1).T
    distance, nearest = tree.query(points)

    floors = (1e-12 * speed * speed, 1e-8 * speed / diameter)
    u_tau = np.full(len(walls), blasius_u_tau(speed, diameter, nu))
    delta = np.maximum(WALL_SHARE * depth, YPLUS_LOG * nu / u_tau)

    def node_delta():
        return np.array([delta[facets].mean() for facets in node_facets])

    near_wall = np.isin(mesh.t, wall_nodes).any(axis=0)[:, None]

    def pin(y):
        facet = owner[nearest]
        facet = np.where(facet >= 0, facet, node_facets_first[np.maximum(nearest - len(wall_points), 0)])
        return near_wall, _wall_omega(u_tau[facet].reshape(y.shape), y, nu)

    def y_at():
        facet = owner[nearest]
        own = np.where(facet >= 0, delta[np.maximum(facet, 0)], 0.0)
        # A node of the wall: its facets' mean.
        if (facet < 0).any():
            nodes_d = node_delta()
            node_index = nearest[facet < 0] - len(wall_points)
            own[facet < 0] = nodes_d[node_index]
        return (distance + own).reshape(bk.global_coordinates().value.shape[1:])

    # Start: a mixing-length eddy viscosity from the wall distance.
    y = y_at()
    ymax = float(y.max())
    vertices = bk.doflocs.T
    yv = tree.query(vertices)[0] + float(delta.mean())
    nut_v = np.maximum(KAPPA * u_tau.mean() * yv * (1.0 - yv / (2.0 * ymax)), 1e-3 * nu)
    omega = u_tau.mean() / (math.sqrt(BETA_STAR) * KAPPA * yv)
    k = nut_v * omega
    w = np.zeros(bw.N)
    gradient = 0.0
    transport, source = _scalar_forms()
    zero2 = np.zeros((2,) + y.shape)
    converged = False
    step = 0
    for step in range(max_steps):
        kk, ww = bk.interpolate(k), bk.interpolate(omega)
        wi = bw.interpolate(w)
        s2 = wi.grad[0] ** 2 + wi.grad[1] ** 2
        nut, f1, blend, cross, kq, wq = _sst(kk.value, kk.grad, ww.value, ww.grad, s2, y, nu, floors, pin(y))
        if step == 0:
            K = asm(diffusion, bw, c=nu + nut)
            w1 = solve(*condense(K, one, D=bw.get_dofs().all()))
        else:
            slip = np.abs(fb.interpolate(w).value)
            tau = spalding_u_tau(slip, delta[:, None], nu)
            alpha = tau ** 2 / np.maximum(slip, 1e-30)
            K = asm(diffusion, bw, c=nu + nut) + asm(mass, fb, c=alpha)
            w1 = splu(K.tocsc()).solve(one)
        g = speed * area / float(one @ w1)
        w_new = g * w1
        change = float(np.abs(w_new - w).max()) / speed
        w = w_new if step < 2 else 0.5 * w + 0.5 * w_new
        gradient = g
        # The wall function's numbers from the new slip speed; the distance floor follows u_tau.
        slip = np.abs(fb.interpolate(w).value)
        tau_q = spalding_u_tau(slip, delta[:, None], nu)
        u_tau = 0.5 * u_tau + 0.5 * tau_q.mean(axis=1)
        delta = np.maximum(WALL_SHARE * depth, YPLUS_LOG * nu / u_tau)
        y = y_at()
        nd = node_delta()
        un = spalding_u_tau(np.abs(w[bw.nodal_dofs[0][wall_nodes]]), nd, nu)
        k_wall, omega_wall = un ** 2 / math.sqrt(BETA_STAR), _wall_omega(un, nd, nu)
        wi = bw.interpolate(w)
        s2 = wi.grad[0] ** 2 + wi.grad[1] ** 2
        production = np.minimum(nut * s2, 10.0 * BETA_STAR * kq * wq)
        base = {"b": zero2, "m": 0.0, "tau": 0.0}
        k_new = _solve_scalar(bk, transport, source, {**base, "r": BETA_STAR * wq, "d": nu + blend["sigma_k"] * nut,
                                                       "s": production, "old": 0.0}, wall_nodes, k_wall, k)
        k_new = np.maximum(k_new, floors[0])
        w_new = _solve_scalar(bk, transport, source, {
            **base, "r": 2.0 * blend["beta"] * wq + np.maximum(-cross, 0.0) / wq, "d": nu + blend["sigma_w"] * nut,
            "s": blend["alpha"] * production / np.maximum(nut, 1e-30) + blend["beta"] * wq ** 2 + np.maximum(cross, 0.0),
            "old": 0.0}, wall_nodes, omega_wall, omega)
        w_new = np.maximum(w_new, floors[1])
        dk = float(np.abs(k_new - k).max()) / max(float(k.max()), 1e-30)
        k = 0.6 * k_new + 0.4 * k
        omega = 0.6 * w_new + 0.4 * omega
        if step > 5 and change < 1e-6 and dk < 1e-5:
            converged = True
            break
    friction = 2.0 * gradient * diameter / speed ** 2
    return bw, bk, w, k, omega, Developed({}, {}, {}, friction, gradient, float(u_tau.mean()), step + 1, converged)


def developed_turbulent(locations: "np.ndarray", rows: "np.ndarray", axis: int, speed: float, nu: float) -> Developed:
    """The settled turbulent flow of a long straight duct of the opening's shape, by scalar node.

    ``rows`` are the opening's quadratic boundary triangles (scalar node ids), flat on a plane normal to
    ``axis``; ``speed`` the mean axial speed (mm/s), ``nu`` the kinematic viscosity (mm^2/s). Every
    edge of the opening is the duct's wall."""
    import numpy as np
    from skfem import MeshTri

    corners = np.unique(rows[:, :3])
    local = {int(n): i for i, n in enumerate(corners)}
    keep = [a for a in range(3) if a != axis]
    points = np.ascontiguousarray(locations[corners][:, keep].T)
    triangles = np.vectorize(local.get)(rows[:, :3]).astype(np.int64)
    mesh = MeshTri(points, np.ascontiguousarray(triangles.T))
    bw, bk, w, k, omega, out = _developed_on(mesh, speed, nu)
    out.w = {int(n): float(w[bw.nodal_dofs[0][i]]) for n, i in local.items()}
    out.k = {int(n): float(k[i]) for n, i in local.items()}
    out.omega = {int(n): float(omega[i]) for n, i in local.items()}
    facet_of = {tuple(pair): j for j, pair in enumerate(np.sort(mesh.facets, axis=0).T.tolist())}
    for row, tri in zip(rows, triangles):
        for m in range(3, 6):
            node = int(row[m])
            if node in out.w:
                continue
            here = locations[node]
            a, b = min(((0, 1), (1, 2), (0, 2)),
                       key=lambda e: float(np.linalg.norm(0.5 * (locations[row[e[0]]] + locations[row[e[1]]]) - here)))
            pair = tuple(sorted((int(tri[a]), int(tri[b]))))
            out.w[node] = float(w[bw.facet_dofs[0][facet_of[pair]]])
            out.k[node] = 0.5 * (float(k[pair[0]]) + float(k[pair[1]]))
            out.omega[node] = 0.5 * (float(omega[pair[0]]) + float(omega[pair[1]]))
    return out


# -- the 3D solve -------------------------------------------------------------------------------------


@dataclass
class RansProblem:
    """What the RANS solver needs: the space, the fluid, and where each kind of boundary is."""

    space: "FemSpace"                 # the fluid's quadratic space
    rho: float                        # tonne/mm^3
    nu: float                         # kinematic viscosity, mm^2/s
    dirichlet: "np.ndarray"           # vector DOF ids with a prescribed velocity (inlets, slip sides' normal)
    values: "np.ndarray"              # their values, mm/s
    #: Boundary rows (of ``space.boundary_quadratic``) of the walls the wall function acts on.
    wall_rows: "np.ndarray"
    #: Scalar (corner) nodes with prescribed k and omega (the inlets), and their values.
    inflow_nodes: "np.ndarray"
    inflow_k: "np.ndarray"
    inflow_omega: "np.ndarray"
    #: (skfem facets, kinematic pressure p / rho, mm^2/s^2) of each outlet: do-nothing at that pressure.
    outlets: list[tuple["np.ndarray", float]] = field(default_factory=list)
    #: The reference speed (mm/s) and length (mm) the start and the stopping rule read.
    speed: float = 1.0
    length: float = 1.0
    kind: str = "internal"
    #: The free stream's (or an inlet's) k and omega, the start of an external flow.
    free_k: float = 0.0
    free_omega: float = 0.0
    #: Inlet and outlet facets, whose mean pressures the march watches settle.
    inlet_facets: "np.ndarray | None" = None
    outlet_facets: "np.ndarray | None" = None


@dataclass
class RansSolution:
    u: "np.ndarray"                   # vector DOF values, mm/s
    p: "np.ndarray"                   # P1 pressure at the corner vertices, MPa
    pressure_basis: Any
    k: "np.ndarray"                   # P1, mm^2/s^2
    omega: "np.ndarray"               # P1, 1/s
    converged: bool
    residual: float                   # the last step's largest velocity change over the reference speed
    steps: int
    solver: str
    linear_solves: int
    #: The wall function's numbers by scalar node on the walls: friction velocity (mm/s) and y+ of its distance.
    wall_nodes: "np.ndarray"
    wall_u_tau: "np.ndarray"
    wall_slip: "np.ndarray"           # (n, 3) the slip velocity at each wall node, mm/s
    yplus: tuple[float, float, float]  # min, mean, max over the wall facets
    nut_ratio: tuple[float, float]     # the eddy-to-fluid viscosity ratio: volume mean, max
    history: list[float] = field(default_factory=list)   # the pressure drop (kinematic) per step, internal flow
    #: Direct solves: the matrices factored, and the solves a kept factor finished (preconditioning GMRES).
    factorizations: int = 0
    reused: int = 0
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def _momentum_forms():
    """The momentum's forms, on the scalar quadratic basis: every term acts on each velocity component alike,
    so the vector operator is three copies of the scalar one (:func:`_expand`), nine times cheaper to build."""
    from skfem import BilinearForm, LinearForm
    from skfem.helpers import div, dot, grad

    @BilinearForm
    def momentum(u, v, w):
        b, gu, gv = w["b"], grad(u), grad(v)
        cu = b[0] * gu[0] + b[1] * gu[1] + b[2] * gu[2]
        cv = b[0] * gv[0] + b[1] * gv[1] + b[2] * gv[2]
        return (w["m"] * u * v + w["nu"] * (gu[0] * gv[0] + gu[1] * gv[1] + gu[2] * gv[2]) + cu * v
                + w["sd"] * cu * cv)

    @BilinearForm
    def weighted_mass(u, v, w):
        return w["c"] * u * v

    @BilinearForm
    def divergence(u, q, _):
        return div(u) * q

    @LinearForm
    def outflow(v, w):
        return dot(w.n, v)

    return momentum, weighted_mass, divergence, outflow


def _expand(scalar, table, n: int):
    """The vector operator of a scalar one: the same block on each of the three velocity components."""
    import numpy as np
    from scipy import sparse

    coo = scalar.tocoo()
    rows = np.concatenate([table[coo.row, c] for c in range(3)])
    cols = np.concatenate([table[coo.col, c] for c in range(3)])
    return sparse.csr_matrix((np.tile(coo.data, 3), (rows, cols)), shape=(n, n))


def wall_rotation(space, normals_of, held, table):
    """The wall nodes' rotation to (normal, tangent, tangent), and the rotated DOFs to hold.

    Returns T (velocity DOFs, sparse, orthogonal) and the DOFs (in the rotated frame) held at zero: each
    smooth wall node's normal slot, every slot of a sharp-edge node (held still: no one slip direction)."""
    import numpy as np
    from scipy import sparse

    nodes = np.array(sorted(set(normals_of) - set(held)), dtype=np.int64)
    n = space.basis.N
    data_rows, data_cols, data = [], [], []
    zero: list[int] = []
    touched = np.zeros(n, dtype=bool)
    for node in nodes:
        normals = np.array(normals_of[int(node)])
        mean = normals.sum(axis=0)
        length = np.linalg.norm(mean)
        dofs = table[node]
        touched[dofs] = True
        if length == 0 or (normals @ (mean / length)).min() < SHARP_COS:
            for c in range(3):
                data_rows.append(dofs[c]); data_cols.append(dofs[c]); data.append(1.0)
            zero.extend(int(d) for d in dofs)
            continue
        normal = mean / length
        helper = np.eye(3)[int(np.argmin(np.abs(normal)))]
        t1 = np.cross(normal, helper); t1 /= np.linalg.norm(t1)
        t2 = np.cross(normal, t1)
        frame = np.stack([normal, t1, t2], axis=1)   # columns: the local axes in global coordinates
        for c in range(3):
            for j in range(3):
                data_rows.append(dofs[c]); data_cols.append(dofs[j]); data.append(frame[c, j])
        zero.append(int(dofs[0]))
    rest = np.flatnonzero(~touched)
    data_rows.extend(rest.tolist()); data_cols.extend(rest.tolist()); data.extend([1.0] * len(rest))
    T = sparse.csr_matrix((data, (data_rows, data_cols)), shape=(n, n))
    return T, np.array(zero, dtype=np.int64)


def wall_geometry(space, wall_rows):
    """Each wall row's skfem facet and its element's depth (3 V / A), and the wall's normals by node."""
    import numpy as np

    triangles = space.boundary_quadratic[wall_rows]
    corners = space.dof_locations[triangles[:, :3]]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    normal = cross / np.where(area > 0, 2.0 * area, 1.0)[:, None]
    facets = space.facets_of_rows(wall_rows)
    element = space.mesh.f2t[0, facets]
    inside = space.mesh.p[:, space.mesh.t[:, element]].mean(axis=1).T
    flip = np.einsum("ij,ij->i", normal, inside - corners[:, 0]) > 0
    normal[flip] *= -1.0                       # out of the fluid
    p = space.mesh.p
    t = space.mesh.t[:4, element]
    volume = np.abs(np.einsum("ij,ij->j", np.cross(p[:, t[1]] - p[:, t[0]], p[:, t[2]] - p[:, t[0]], axis=0),
                              p[:, t[3]] - p[:, t[0]])) / 6.0
    depth = 3.0 * volume / np.maximum(area, 1e-300)
    normals_of = _node_normals(space, triangles, normal, area)
    return facets, depth, normals_of


def _node_normals(space, triangles, flat_normal, area) -> dict[int, list]:
    """Each wall node's normals, one per wall triangle it is on, of the curved (quadratic) surface at that node.

    A flat triangle through a curved wall's corners leans off the true normal (on a pipe by half the
    angle between its corners), and holding the velocity along that lean would push fluid through the
    wall; the quadratic triangle's own normal at the node does not. Each is weighted by its triangle's area.
    """
    import numpy as np

    locations = space.dof_locations
    # Each mid node's two corners, by place (the mesher's order of the mid nodes is not assumed).
    pairs = ((0, 1), (1, 2), (0, 2))
    corner = locations[triangles[:, :3]]
    mids = locations[triangles[:, 3:]]
    halves = np.stack([0.5 * (corner[:, a] + corner[:, b]) for a, b in pairs], axis=1)     # (T, 3 pairs, 3)
    which = np.argmin(np.linalg.norm(mids[:, :, None, :] - halves[:, None, :, :], axis=3), axis=2)  # (T, 3 mids)
    # The quadratic triangle x(s, t) on corners (0,0), (1,0), (0,1); its mid nodes on the pairs' midpoints.
    reference = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])

    def derivatives(s, t):
        """d N / d s and d N / d t of the six shape functions: three corners, then mids on pairs (0,1), (1,2), (0,2)."""
        l0, l1, l2 = 1.0 - s - t, s, t
        ds = np.array([-(4 * l0 - 1), 4 * l1 - 1, 0.0, 4 * (l0 - l1), 4 * l2, -4 * l2])
        dt = np.array([-(4 * l0 - 1), 0.0, 4 * l2 - 1, -4 * l1, 4 * l1, 4 * (l0 - l2)])
        return ds, dt

    out: dict[int, list] = {}
    for index, row in enumerate(triangles):
        nodes = np.empty((6, 3))
        nodes[:3] = corner[index]
        for m in range(3):
            nodes[3 + which[index, m]] = mids[index, m]
        local = list(row[:3]) + [None, None, None]
        for m in range(3):
            local[3 + which[index, m]] = row[3 + m]
        points = list(reference) + [0.5 * (reference[a] + reference[b]) for a, b in pairs]
        for j, (s_, t_) in enumerate(points):
            ds, dt = derivatives(s_, t_)
            normal = np.cross(ds @ nodes, dt @ nodes)
            length = np.linalg.norm(normal)
            if length == 0:
                normal = flat_normal[index]
            else:
                normal = normal / length
                if normal @ flat_normal[index] < 0:
                    normal = -normal
            out.setdefault(int(local[j]), []).append(normal * area[index])
    return {node: [n / np.linalg.norm(n) for n in normals] for node, normals in out.items()}


class _Krylov:
    """GMRES with a block preconditioner (multigrid on the velocity, the pressure mass diagonal); None when it stalls."""

    def __init__(self, nv: int, mass_diagonal):
        self.nv, self.mp = nv, mass_diagonal
        self.stalled = False

    def __call__(self, K, b):
        import numpy as np
        import pyamg
        from scipy.sparse.linalg import LinearOperator, gmres

        nv = self.nv
        A = K[:nv, :nv]
        Bf = K[nv:, :nv]
        ml = pyamg.smoothed_aggregation_solver((0.5 * (A + A.T)).tocsr(), B=None, max_coarse=500)
        amg = ml.aspreconditioner(cycle="V")
        inv_mp = 1.0 / np.where(self.mp > 0, self.mp, 1.0)

        def apply(r):
            zu = amg @ r[:nv]
            return np.concatenate([zu, -inv_mp * (r[nv:] - Bf @ zu)])

        M = LinearOperator(K.shape, matvec=apply, dtype=float)
        x, info = gmres(K, b, M=M, rtol=KRYLOV_TOL, restart=RESTART, maxiter=MAX_KRYLOV // RESTART + 1)
        # GMRES judges itself on the preconditioned residual: the true one decides.
        if not np.all(np.isfinite(x)) or np.linalg.norm(K @ x - b) > 1e-6 * max(np.linalg.norm(b), 1e-300):
            self.stalled = True
            return None
        return x


def factor_saddle(K):
    """SuperLU of the saddle-point system: the symmetric-structure ordering on diagonal pivots first (several
    times faster here), checked on a test vector, and the default partial pivoting when that is not accurate."""
    import numpy as np
    from scipy.sparse.linalg import splu

    try:
        lu = splu(K, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0, options={"SymmetricMode": True})
        probe = np.random.default_rng(0).standard_normal(K.shape[0])
        x = lu.solve(probe)
        if np.all(np.isfinite(x)) and np.linalg.norm(K @ x - probe) <= 1e-9 * np.linalg.norm(probe):
            return lu
    except RuntimeError:
        pass
    return splu(K)


def solve_rans(problem: RansProblem, *, solver: str = "direct", cfl: tuple[float, float] = (CFL_START, CFL_GROWTH),
               tolerance: float = VELOCITY_TOL, max_steps: int = MAX_STEPS,
               log: Callable[[str], None] | None = None) -> RansSolution:
    """The steady RANS flow of ``problem`` by pseudo-transient continuation (see the module's words).

    ``cfl`` is the march's starting CFL number and its growth per step; ``solver`` "direct" (SuperLU)
    or "iterative" (GMRES with a block multigrid preconditioner, finished by SuperLU if it stalls)."""
    import numpy as np
    from scipy import sparse
    from scipy.spatial import cKDTree
    from skfem import BilinearForm, ElementTetP1, ElementTetP2, ElementVector, FacetBasis, asm

    from cadgen._internal.fea.navier_stokes import vector_dofs

    timings: dict[str, float] = {}
    started = time.perf_counter()
    space = problem.space
    nu, U, L = problem.nu, max(problem.speed, 1e-12), max(problem.length, 1e-12)
    V = space.basis
    Q = V.with_element(ElementTetP1())
    momentum, weighted_mass, divergence, outflow = _momentum_forms()
    S = space.scalar

    transport, source = _scalar_forms()
    table = vector_dofs(space)
    nv, npr = V.N, Q.N
    Bm = (-asm(divergence, V, Q)).tocsr()

    @BilinearForm
    def pmass(p, q, _):
        return p * q

    Mp = np.asarray(asm(pmass, Q).diagonal())

    # Element size (a regular tet's edge of the same volume), at every quadrature point.
    volume = np.asarray(V.dx).sum(axis=1)
    h = np.cbrt(6.0 * np.sqrt(2.0) * volume)[:, None]

    # Walls: facets, normals, depth, the rotation that lets them slip, and the facet basis the law acts on.
    wall_rows = np.asarray(problem.wall_rows, dtype=np.int64)
    has_walls = len(wall_rows) > 0
    dof_node = np.zeros(nv, dtype=np.int64)
    for c in range(3):
        dof_node[table[:, c]] = np.arange(space.scalar_count)
    held_nodes = set(np.unique(dof_node[np.asarray(problem.dirichlet, dtype=np.int64)]).tolist())
    if has_walls:
        facets, depth, normals_of = wall_geometry(space, wall_rows)
        T, rotated_zero = wall_rotation(space, normals_of, held_nodes, table)
        fbV = FacetBasis(space.mesh, ElementVector(ElementTetP2()), facets=facets)
        fbS = FacetBasis(space.mesh, ElementTetP2(), facets=facets)
        wall_points = fbV.global_coordinates().value.reshape(3, -1).T
        per_facet = fbV.global_coordinates().value.shape[2]
        wall_corner_nodes = np.unique(space.boundary_quadratic[wall_rows][:, :3])
        wall_all_nodes = np.unique(space.boundary_quadratic[wall_rows])
        node_rows: dict[int, list[int]] = {}
        for i, row in enumerate(space.boundary_quadratic[wall_rows]):
            for node in row:
                node_rows.setdefault(int(node), []).append(i)
        tree = cKDTree(wall_points)
        near_wall = np.isin(space.mesh.t[:4], wall_corner_nodes).any(axis=0)[:, None]
    else:
        T = sparse.identity(nv, format="csr")
        rotated_zero = np.zeros(0, dtype=np.int64)
        wall_corner_nodes = wall_all_nodes = np.zeros(0, dtype=np.int64)
        depth = np.zeros(0)
    Tbig = sparse.block_diag([T, sparse.identity(npr)], format="csr")

    # Held velocity DOFs (in the rotated frame, where held ones are unrotated) and their values.
    held = np.concatenate([np.asarray(problem.dirichlet, dtype=np.int64), rotated_zero])
    held_values = np.concatenate([np.asarray(problem.values, dtype=float), np.zeros(len(rotated_zero))])
    held, first = np.unique(held, return_index=True)
    held_values = held_values[first]
    n = nv + npr
    free = np.ones(n, dtype=bool)
    free[held] = False
    free_ids = np.flatnonzero(free)

    # Outlet loads (do nothing at each outlet's pressure).
    f_out = np.zeros(nv)
    for out_facets, pressure in problem.outlets:
        if pressure:
            f_out -= pressure * asm(outflow, V.boundary(out_facets))

    # Wall distance at the scalar quadrature points (to the wall's quadrature points) and at the vertices.
    q_points = Q.global_coordinates().value.reshape(3, -1).T
    q_shape = Q.global_coordinates().value.shape[1:]
    vertices = space.dof_locations[: space.vertices]
    if has_walls:
        q_distance, q_nearest = tree.query(q_points)
        q_facet = q_nearest // per_facet
        v_distance, v_nearest = tree.query(vertices)
        v_facet = v_nearest // per_facet
    else:
        q_distance = np.full(len(q_points), 1e3 * L)
        q_facet = np.zeros(len(q_points), dtype=np.int64)
        v_distance = np.full(len(vertices), 1e3 * L)
        v_facet = np.zeros(len(vertices), dtype=np.int64)
    floors = (1e-12 * U * U, 1e-8 * U / L)
    timings["setup_s"] = time.perf_counter() - started

    # The wall function's distance: half the wall element's depth, never under y+ 30.
    u_tau_facet = np.full(len(depth), blasius_u_tau(U, L, nu)) if has_walls else np.zeros(0)

    def deltas():
        return np.maximum(WALL_SHARE * depth, YPLUS_LOG * nu / np.maximum(u_tau_facet, 1e-30))

    delta = deltas() if has_walls else np.zeros(0)

    def wall_y(dist, facet):
        return dist + (delta[facet] if has_walls else 0.0)

    # The start: a mixing-length eddy viscosity (internal flow) or the free stream's (external).
    yv = wall_y(v_distance, v_facet)
    ymax = float(yv.max()) if len(yv) else L
    u_tau0 = blasius_u_tau(U, L, nu)
    if problem.kind == "internal":
        nut_v = np.maximum(KAPPA * u_tau0 * yv * (1.0 - np.minimum(yv, ymax) / (2.0 * ymax)), 1e-3 * nu)
        omega = u_tau0 / (math.sqrt(BETA_STAR) * KAPPA * yv)
        k = nut_v * omega
    else:
        omega = np.maximum(problem.free_omega, (u_tau0 / (math.sqrt(BETA_STAR) * KAPPA * yv)) if has_walls else 0.0)
        k = np.full(space.vertices, max(problem.free_k, floors[0]))
    k = np.asarray(k, dtype=float); omega = np.asarray(omega, dtype=float) * np.ones(space.vertices)
    inflow = np.asarray(problem.inflow_nodes, dtype=np.int64)
    k[inflow], omega[inflow] = problem.inflow_k, problem.inflow_omega

    krylov = _Krylov(int(free[:nv].sum()), Mp[free[nv:]]) if solver == "iterative" else None
    warnings: list[str] = []
    solves = 0

    factor: dict[str, Any] = {"lu": None, "fresh": 0}

    def lagged(K, b):
        """A direct solve that keeps its factor: the next steps' matrices differ a little (the eddy viscosity,
        the convecting velocity, the pseudo-time step), so the kept factor preconditions GMRES on them, and the
        matrix is factored afresh only when that takes too many iterations."""
        from scipy.sparse.linalg import LinearOperator, gmres

        lu = factor["lu"]
        if lu is not None:
            M = LinearOperator(K.shape, matvec=lu.solve, dtype=float)
            x, _ = gmres(K, b, x0=lu.solve(b), M=M, rtol=LAGGED_TOL, restart=LAGGED_ITERATIONS, maxiter=1)
            # GMRES judges itself on the preconditioned residual: the true one decides.
            if np.all(np.isfinite(x)) and np.linalg.norm(K @ x - b) <= 10 * LAGGED_TOL * max(np.linalg.norm(b), 1e-300):
                factor["reused"] = factor.get("reused", 0) + 1
                return x
        lu = factor_saddle(K)
        factor["lu"], factor["fresh"] = lu, factor["fresh"] + 1
        return lu.solve(b)

    def linear(K, rhs):
        """K x = rhs in the rotated frame with the held DOFs fixed; x back in the global frame."""
        nonlocal solves
        solves += 1
        Kr = (Tbig.T @ K @ Tbig).tocsr()
        br = Tbig.T @ rhs
        x = np.zeros(n)
        x[held] = held_values
        b = br[free_ids] - Kr[free_ids][:, held] @ held_values
        K_ff = Kr[free_ids][:, free_ids]
        solved = None
        if krylov is not None and not krylov.stalled:
            solved = krylov(K_ff.tocsr(), b)
            if solved is None and not warnings:
                warnings.append("the iterative flow solver stalled, so the direct solver finished the run")
        if solved is None:
            solved = lagged(K_ff.tocsc(), b)
        x[free_ids] = solved
        if not np.all(np.isfinite(x)):
            raise RuntimeError("the turbulent flow's linear solve produced non-finite values")
        return Tbig @ x

    def closure(u, k, omega):
        ui = V.interpolate(u)
        kk, ww = Q.interpolate(k), Q.interpolate(omega)
        s2 = _strain2(ui.grad)
        y = wall_y(q_distance, q_facet).reshape(q_shape)
        pinned = None
        if has_walls:
            pinned = (near_wall, _wall_omega(u_tau_facet[q_facet].reshape(q_shape), y, nu))
        nut, f1, blend, cross, kq, wq = _sst(kk.value, kk.grad, ww.value, ww.grad, s2, y, nu, floors, pinned)
        return ui, s2, nut, blend, cross, kq, wq

    def pressure_drop(x) -> float:
        if problem.inlet_facets is None or problem.outlet_facets is None:
            return 0.0
        p = x[nv:]

        def mean(fac):
            fb = FacetBasis(space.mesh, ElementTetP1(), facets=fac)
            values = fb.interpolate(p).value
            dx = fb.dx
            return float((values * dx).sum() / dx.sum())

        return mean(problem.inlet_facets) - mean(problem.outlet_facets)

    # Stokes-like start: the eddy viscosity frozen, no convection, no pseudo-time.
    u = np.zeros(nv)
    x = np.zeros(n)
    ui, s2, nut, blend, cross, kq, wq = closure(u, k, omega)
    zero3 = np.zeros((3,) + q_shape)
    K = sparse.bmat([[_expand(asm(momentum, S, b=zero3, m=0.0, nu=nu + nut, sd=0.0), table, nv), Bm.T], [Bm, None]], format="csr")
    x = linear(K, np.concatenate([f_out, np.zeros(npr)]))
    u = x[:nv]
    cfl_now, growth = cfl
    robin: dict[str, Any] = {"alpha": None}
    ceiling, streak = CFL_MAX, 0
    history: list[float] = []
    last_change = math.inf
    converged = False
    change = math.inf
    step = 0
    started = time.perf_counter()
    for step in range(1, max_steps + 1):
        ui, s2, nut, blend, cross, kq, wq = closure(u, k, omega)
        speed_q = np.linalg.norm(ui.value, axis=0)
        nu_eff = nu + nut
        dtau = cfl_now * h / (speed_q + 2.0 * nu_eff / h + 1e-30)
        m = 1.0 / dtau
        # Streamline diffusion where the cell Peclet number passes 1 (as the laminar solver).
        hp = 0.5 * h
        peclet = speed_q * hp / (2.0 * nu_eff)
        with np.errstate(divide="ignore", invalid="ignore"):
            sd = np.where(peclet > 1.0, hp / (2.0 * speed_q) * (1.0 - 1.0 / peclet), 0.0)
        A = _expand(asm(momentum, S, b=ui.value, m=m, nu=nu_eff, sd=sd), table, nv)
        rhs_u = f_out + _expand(asm(weighted_mass, S, c=m), table, nv) @ u
        if has_walls:
            slip = fbV.interpolate(u).value
            nrm = fbV.normals
            tangential = slip - np.einsum("i...,i...->...", slip, nrm) * nrm
            speed_w = np.linalg.norm(tangential, axis=0)
            tau_q = spalding_u_tau(speed_w, delta[:, None], nu)
            alpha = tau_q ** 2 / np.maximum(speed_w, 1e-30)
            # The wall's pull per unit slip grows with the slip, so taken at the last step's slip alone it can
            # flip between a slow and a fast wall node from step to step: half of it is carried over.
            if robin["alpha"] is not None:
                alpha = ROBIN_RELAX * alpha + (1.0 - ROBIN_RELAX) * robin["alpha"]
            robin["alpha"] = alpha
            A = A + _expand(asm(weighted_mass, fbS, c=alpha), table, nv)
        K = sparse.bmat([[A, Bm.T], [Bm, None]], format="csr")
        x_new = linear(K, np.concatenate([rhs_u, np.zeros(npr)]))
        u_new = x_new[:nv]
        change = float(np.abs(u_new - u).max()) / U
        u, x = u_new, x_new

        # The wall function from the new slip: u_tau per facet, the distance floor, k and omega at the wall.
        ui, s2, nut, blend, cross, kq, wq = closure(u, k, omega)
        fixed_nodes, k_fixed, w_fixed = [inflow], [np.asarray(problem.inflow_k, dtype=float)], [np.asarray(problem.inflow_omega, dtype=float)]
        if has_walls:
            slip = fbV.interpolate(u).value
            nrm = fbV.normals
            tangential = slip - np.einsum("i...,i...->...", slip, nrm) * nrm
            tau_q = spalding_u_tau(np.linalg.norm(tangential, axis=0), delta[:, None], nu)
            u_tau_facet = 0.5 * u_tau_facet + 0.5 * tau_q.mean(axis=1)
            delta = deltas()
            nodal = space.nodal(u)
            corner = np.setdiff1d(wall_corner_nodes, inflow)
            nd = np.array([delta[node_rows[int(c)]].mean() for c in corner])
            normal_c = np.array([np.mean(normals_of[int(c)], axis=0) for c in corner]) if len(corner) else np.zeros((0, 3))
            normal_c /= np.maximum(np.linalg.norm(normal_c, axis=1), 1e-30)[:, None]
            vel = nodal[corner]
            tang = vel - np.einsum("ij,ij->i", vel, normal_c)[:, None] * normal_c
            un = spalding_u_tau(np.linalg.norm(tang, axis=1), nd, nu)
            fixed_nodes.append(corner)
            k_fixed.append(un ** 2 / math.sqrt(BETA_STAR))
            w_fixed.append(_wall_omega(un, nd, nu))
        fixed = np.concatenate(fixed_nodes)
        k_values, w_values = np.concatenate(k_fixed), np.concatenate(w_fixed)
        fixed, first = np.unique(fixed, return_index=True)
        k_values, w_values = k_values[first], w_values[first]

        speed_q = np.linalg.norm(ui.value, axis=0)
        production = np.minimum(nut * s2, 10.0 * BETA_STAR * kq * wq)
        m_s = 1.0 / (cfl_now * h / (speed_q + 2.0 * (nu + nut) / h + 1e-30))
        d_k = nu + blend["sigma_k"] * nut
        r_k = BETA_STAR * wq
        k_old_q = Q.interpolate(k).value
        k_new = _solve_scalar(Q, transport, source, {
            "b": ui.value, "m": m_s, "r": r_k, "d": d_k, "s": production, "old": k_old_q,
            "tau": _supg_tau(speed_q, h, d_k, r_k + m_s)}, fixed, k_values, k)
        k_new = np.maximum(k_new, floors[0])
        d_w = nu + blend["sigma_w"] * nut
        r_w = 2.0 * blend["beta"] * wq + np.maximum(-cross, 0.0) / wq
        w_old_q = Q.interpolate(omega).value
        omega_new = _solve_scalar(Q, transport, source, {
            "b": ui.value, "m": m_s, "r": r_w, "d": d_w,
            "s": blend["alpha"] * production / np.maximum(nut, 1e-30) + blend["beta"] * wq ** 2 + np.maximum(cross, 0.0),
            "old": w_old_q, "tau": _supg_tau(speed_q, h, d_w, r_w + m_s)}, fixed, w_values, omega)
        omega_new = np.maximum(omega_new, floors[1])
        dk = float(np.abs(k_new - k).max()) / max(float(k.max()), 1e-30)
        k = SCALAR_RELAX * k_new + (1.0 - SCALAR_RELAX) * k
        omega = SCALAR_RELAX * omega_new + (1.0 - SCALAR_RELAX) * omega
        drop = pressure_drop(x)
        history.append(drop)

        if log and (step % 10 == 0 or step < 3):
            log(f"turbulent flow: step {step}, CFL {cfl_now:.3g}, velocity change {change:.1e}, k change {dk:.1e}")
        if change < tolerance and dk < 10.0 * tolerance:
            converged = True
            break
        # Switched evolution relaxation: a step that shrank the change clearly earns a longer pseudo-time step.
        # One that did not (the convection taken at the last step's velocity can swing between two states near
        # a stagnation point at long steps) halves it, and the march never again goes past half the step that
        # stalled, down to a CFL of CFL_MIN, where it is a true time march and settles.
        if change < SHRINK * last_change:
            streak += 1
            if streak >= RECOVER:
                ceiling, streak = min(2.0 * ceiling, CFL_MAX), 0
            cfl_now = min(cfl_now * growth, ceiling)
        else:
            ceiling = max(cfl_now / 2.0, CFL_MIN)
            cfl_now, streak = ceiling, 0
        last_change = change
    timings["march_s"] = time.perf_counter() - started
    if not converged:
        warnings.append(f"the turbulent flow stopped after {step} steps still changing by {change:.1e} of its speed a step, "
                        f"short of {tolerance:.0e}: its numbers are approximate")

    # What the walls carry: u_tau and slip at every wall node; y+ of the wall function's distance.
    wall_u_tau = np.zeros(0)
    slip_nodal = np.zeros((0, 3))
    yplus = (0.0, 0.0, 0.0)
    if has_walls:
        nodal = space.nodal(u)
        normal_n = np.array([np.mean(normals_of[int(c)], axis=0) for c in wall_all_nodes])
        normal_n /= np.maximum(np.linalg.norm(normal_n, axis=1), 1e-30)[:, None]
        vel = nodal[wall_all_nodes]
        slip_nodal = vel - np.einsum("ij,ij->i", vel, normal_n)[:, None] * normal_n
        nd = np.array([delta[node_rows[int(c)]].mean() for c in wall_all_nodes])
        wall_u_tau = spalding_u_tau(np.linalg.norm(slip_nodal, axis=1), nd, nu)
        yp = delta * u_tau_facet / nu
        yplus = (float(yp.min()), float(yp.mean()), float(yp.max()))
    ui, s2, nut, blend, cross, kq, wq = closure(u, k, omega)
    dx = np.asarray(Q.dx)
    ratio = (float((nut * dx).sum() / dx.sum() / nu), float(nut.max() / nu))
    return RansSolution(
        u=u, p=problem.rho * x[nv:], pressure_basis=Q, k=k, omega=omega, converged=converged, residual=change,
        steps=step, solver=solver, linear_solves=solves, wall_nodes=wall_all_nodes, wall_u_tau=wall_u_tau,
        wall_slip=slip_nodal, yplus=yplus, nut_ratio=ratio, history=history, factorizations=factor["fresh"],
        reused=factor.get("reused", 0), warnings=warnings, timings=timings,
    )
