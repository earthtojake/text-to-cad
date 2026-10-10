"""Steady compressible flow of an ideal gas on the Taylor-Hood pair: a pressure-based solver, pseudo-time marched.

The unknowns are the flow solvers' own (:mod:`.navier_stokes`): quadratic
velocity, linear pressure, on the fluid's quadratic tetrahedra. The gas is
ideal (p = rho R T) and the flow adiabatic with one total temperature T0, so
its total enthalpy is the same everywhere (exact for steady adiabatic flow fed
from one reservoir, shocks included) and the temperature follows the speed:

    T = T0 - |u|^2 / (2 cp),    rho = p / (R T)

That leaves momentum and mass,

    rho (u . grad) u + grad p - div(mu grad u) - grad((mu/3 + mu_b) div u) = 0
    div(rho u) = 0

the momentum in the laminar solver's Laplacian form (its outlet condition stays
"do nothing" at the outlet's static pressure) plus the compressible part of
the viscous stress. Mass is written conservatively (integrated by parts, with
its flux through the inlets and outlets), so what enters leaves to the
solver's tolerance, and it is linearised in the pressure as well as the
velocity: rho u ~ rho_k u + (rho/p)_k u_k (p - p_k). That pressure term is what
makes the method pressure-based compressible rather than incompressible with
a variable density: it carries pressure waves along the flow, so the same
equations hold from a slow gas (where it vanishes and the solver is the
incompressible one, to the density) through transonic flow.

Linearisation is Newton's: the convection, the density's dependence on the
pressure and on the speed (in mass and in momentum), and Bernoulli's at a
total-pressure inlet are all in the matrix.

Stabilisation is SUPG on both equations, consistent (the streamline test
function weights each equation's whole residual, so it vanishes on the exact
flow and costs no total pressure in a smooth expansion): on the momentum
convection where the cell Peclet number passes 1, and on mass's pressure
transport where the flow nears or passes sonic (Mach 0.9 to 1.1 and up).
Shock capturing is a bulk viscosity mu_b = C rho h^2 |div u| where the gas is
compressed (div u < 0), which spreads a normal shock over a few elements.

The march is pseudo-transient continuation: each step solves the linearised
system with a local pseudo-time term (rho / dtau on momentum, (rho/p) / dtau on
mass, dtau = CFL h / (|u| + c)), from a first step that is potential flow; the
CFL grows as the steady residual falls (switched evolution relaxation), a step
that would move the gas by more than a fifth of the speed of sound is cut
back, and once the residual is a thousandth of its largest the stabilisation's
coefficients are held, so the march ends as Newton on fixed discrete
equations. Inlets are held by total pressure and total temperature (the
inflow's direction held, its speed free, pushed by the static pressure the
total pressure leaves at that speed) or by mass flow (the inflow speed from
the mass, the inlet's static pressure and the speed's own temperature,
updated each step); outlets by static pressure. Walls either slip (an inviscid
core: frictionless, the normal velocity held, in a frame rotated to each wall
node's normal) or hold (laminar no-slip, Sutherland's viscosity).
Continuation in the pressure difference (or the mass flow) steps a hard case
(a choked nozzle) up from a gentle one.

The equations are solved non-dimensional (velocity over the stagnation speed
of sound, density over the outlet's at T0, pressure over that density times
c0^2), so the numbers are of one size whatever the gas. Numeric imports live
inside the functions.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = ["AIR", "Gas", "GasInlet", "GasProblem", "GasSolution", "area_mach", "isentropic", "mach_from_area",
           "solve_gas", "sutherland"]


@dataclass(frozen=True)
class Gas:
    """An ideal gas: its ratio of specific heats, gas constant (J/kg K) and Sutherland viscosity."""

    name: str = "air"
    gamma: float = 1.4
    R: float = 287.0
    #: Sutherland's law: mu = mu_ref (T / T_ref)^1.5 (T_ref + S) / (T + S), Pa s and K.
    mu_ref: float = 1.716e-5
    T_ref: float = 273.15
    S: float = 110.4

    @property
    def cp(self) -> float:
        return self.gamma * self.R / (self.gamma - 1.0)


AIR = Gas()


def sutherland(gas: Gas, T):
    """The gas's dynamic viscosity at temperature ``T`` (K), Pa s."""
    return gas.mu_ref * (T / gas.T_ref) ** 1.5 * (gas.T_ref + gas.S) / (T + gas.S)


def isentropic(mach: float, gamma: float = 1.4) -> dict[str, float]:
    """Static over total temperature, pressure and density at ``mach``, and the area over the sonic area."""
    t = 1.0 / (1.0 + 0.5 * (gamma - 1.0) * mach * mach)
    return {"T": t, "p": t ** (gamma / (gamma - 1.0)), "rho": t ** (1.0 / (gamma - 1.0)), "A": area_mach(mach, gamma)}


def area_mach(mach: float, gamma: float = 1.4) -> float:
    """A / A* of isentropic flow at ``mach``."""
    g = gamma
    return (1.0 / mach) * ((2.0 / (g + 1.0)) * (1.0 + 0.5 * (g - 1.0) * mach * mach)) ** ((g + 1.0) / (2.0 * (g - 1.0)))


def mach_from_area(ratio: float, supersonic: bool, gamma: float = 1.4) -> float:
    """The Mach number at A / A* = ``ratio`` (>= 1) on the subsonic or the supersonic branch, by bisection."""
    low, high = (1.0, 50.0) if supersonic else (1e-9, 1.0)
    for _ in range(200):
        middle = 0.5 * (low + high)
        above = area_mach(middle, gamma) > ratio
        if supersonic:
            low, high = (low, middle) if above else (middle, high)
        else:
            low, high = (middle, high) if above else (low, middle)
    return 0.5 * (low + high)


@dataclass
class GasInlet:
    """One inlet: its boundary rows, the inflow's direction, its profile and what holds it."""

    rows: "np.ndarray"                 # boundary triangle rows of the opening
    nodes: "np.ndarray"                # the scalar nodes the inflow velocity is held at
    weights: "np.ndarray"              # the profile at those nodes, mean 1 over the opening's area
    direction: "np.ndarray"            # unit inflow direction (into the fluid)
    area_mm2: float
    #: "total" (total_pressure_Pa, absolute), "mass" (mass_flow_kg_s) or "velocity" (velocity_m_s: a free stream).
    kind: str = "total"
    total_pressure_Pa: float = 0.0
    mass_flow_kg_s: float = 0.0
    velocity_m_s: float = 0.0


@dataclass
class GasProblem:
    space: "FemSpace"
    gas: Gas
    total_temperature_K: float
    inlets: list[GasInlet]
    #: (boundary rows, absolute static pressure Pa) of each outlet.
    outlets: list[tuple["np.ndarray", float]]
    wall_rows: "np.ndarray"
    walls: str = "slip"                # "slip" (inviscid core) or "no_slip" (laminar)
    #: Rows that always slip whatever the walls do (an external flow's far box sides).
    slip_rows: "np.ndarray | None" = None


@dataclass
class GasSolution:
    u: "np.ndarray"                    # vector DOFs, mm/s
    p: "np.ndarray"                    # absolute static pressure at the corner vertices, Pa
    pressure_basis: Any
    temperature_K: "np.ndarray"        # at every scalar node
    mach: "np.ndarray"                 # at every scalar node
    density: "np.ndarray"              # at every scalar node, kg/m^3
    pressure_nodes_Pa: "np.ndarray"    # absolute, at every scalar node (edges: their corners' mean)
    converged: bool
    residual: float
    steps: int
    stages: list[float]
    continued: bool
    solver: str
    linear_solves: int
    #: Mass through each inlet and each outlet, kg/s, positive along the flow.
    inflow_kg_s: list[float]
    outflow_kg_s: list[float]
    inlet_static_Pa: list[float]
    inlet_total_Pa: list[float]
    shock_cells: int = 0
    #: Each element's sharpest compression, -div u h / c (a normal shock spread over a few elements reads ~0.3).
    compression: "np.ndarray | None" = None
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    history: list[float] = field(default_factory=list)


#: The march: starting CFL, growth per step that lowered the residual, its ceiling and floor.
CFL_START, CFL_GROWTH, CFL_MAX, CFL_MIN = 5.0, 2.0, 1e8, 0.5
#: The march stops when the steady residual has fallen by this much and the state changes by less than this.
RESIDUAL_TOL, CHANGE_TOL = 1e-7, 1e-6
#: An intermediate continuation stage stops at these.
STAGE_RESIDUAL, STAGE_CHANGE = 1e-4, 1e-4
MAX_STEPS = 150
#: Continuation: the shares of the drive each stage solves at.
CONTINUATION = (0.5, 1.0)
#: The share of the new inflow speed taken each step.
INLET_RELAX = 0.5
#: Shock capturing: mu_b = C rho h^2 |div u| where the gas is compressed.
SHOCK_C = 4.0
#: Pressure upwinding: off below this Mach number, full from this one up.
UPWIND_FROM, UPWIND_FULL = 0.9, 1.1
#: The most one pseudo-time step may move the velocity (a share of c0) or the pressure (of the outlet's).
STEP_LIMIT = 0.2
#: The stabilisation's coefficients are held once the steady residual is under this share of its largest.
FREEZE_AT = 1e-3
#: The share of the shock capturing's and the upwinding's new coefficients taken each step.
RELAX = 0.3
#: The coldest the temperature may get, as a share of T0 (a guard, never reached in a converged flow).
T_FLOOR = 0.05


def _facet_forms():
    from skfem import BilinearForm, LinearForm
    from skfem.helpers import dot

    @BilinearForm
    def flux_u(u, q, w):  # (rho u + (d rho / d u . u) b) . n q on the openings
        return (w["rho"] * dot(u, w.n) + w["k"] * dot(w["b"], u) * dot(w["b"], w.n)) * q

    @BilinearForm
    def flux_p(p, q, w):  # psi (b . n) p q on the openings
        return w["psi"] * dot(w["b"], w.n) * p * q

    @LinearForm
    def flux_rhs(q, w):
        return (w["psi"] * w["pk"] + w["k"] * dot(w["b"], w["b"])) * dot(w["b"], w.n) * q

    @LinearForm
    def outflow(v, w):
        return dot(w.n, v)

    def _static(w):
        import numpy as np

        t = np.maximum(1.0 - 0.5 * (w["g"] - 1.0) * dot(w["b"], w["b"]), T_FLOOR)
        return w["p0"] * t ** (w["g"] / (w["g"] - 1.0)), w["g"] * w["p0"] * t ** (1.0 / (w["g"] - 1.0))

    @BilinearForm
    def bernoulli(u, v, w):  # -rho_s (b . u)(n . v): the static pressure's fall with the speed
        _, rho_s = _static(w)
        return -rho_s * dot(w["b"], u) * dot(w.n, v)

    @LinearForm
    def inlet_rhs(v, w):  # (p_s(b) + rho_s b . b - p_ref)(n . v)
        p_s, rho_s = _static(w)
        return (p_s + rho_s * dot(w["b"], w["b"]) - w["pref"]) * dot(w.n, v)

    return flux_u, flux_p, flux_rhs, outflow, bernoulli, inlet_rhs


def solve_gas(problem: GasProblem, *, schedule: tuple[float, ...] = (), solver: str = "direct",
              cfl: tuple[float, float] = (CFL_START, CFL_GROWTH), max_steps: int = MAX_STEPS,
              log: Callable[[str], None] | None = None) -> GasSolution:
    """The steady compressible flow of ``problem`` by pseudo-transient continuation (see the module's words).

    ``schedule`` (the ladder's continuation) solves first at those shares of the inlets' drive (the
    pressure difference over the outlet's, or the mass flow) and finishes at the full one; without one,
    continuation is taken only when the march does not settle at the target."""
    import numpy as np
    from scipy import sparse
    from skfem import ElementTetP1, FacetBasis, asm

    from cadgen._internal.fea.turbulence import _factor, _rotation, _wall_geometry

    timings: dict[str, float] = {}
    started = time.perf_counter()
    space, gas = problem.space, problem.gas
    g = gas.gamma
    T0 = float(problem.total_temperature_K)
    c0 = math.sqrt(g * gas.R * T0) * 1000.0                  # mm/s
    p_ref = float(problem.outlets[0][1])                      # Pa, absolute
    rho_ref = p_ref / (gas.R * T0)                            # kg/m^3
    scale_p = rho_ref * (c0 / 1000.0) ** 2                    # Pa per unit non-dimensional pressure
    P_REF = p_ref / scale_p                                   # = 1 / gamma
    cp = 1.0 / (g - 1.0)                                      # cp T0 / c0^2

    def mu_nd(T):  # Sutherland, over rho_ref c0 (1 mm)
        return sutherland(gas, T * T0) / (rho_ref * (c0 / 1000.0) * 1e-3)

    ops = _Operators(space)
    f_flux_u, f_flux_p, f_flux_rhs, f_out, f_bernoulli, f_inlet_rhs = _facet_forms()
    V = space.basis
    Q = V.with_element(ElementTetP1())
    nv, npr = V.N, Q.N
    n = nv + npr
    table = ops.table
    E, Qn = ops.shape
    volume = np.asarray(ops.S.dx).sum(axis=1)
    h = np.repeat(np.cbrt(6.0 * np.sqrt(2.0) * volume), Qn)   # a regular tet's edge of the same volume, per point
    Mp = np.asarray((ops.N1T @ sparse.diags(ops.dx) @ ops.N1).diagonal())

    boundary = space.boundary_quadratic
    open_rows = np.concatenate([inlet.rows for inlet in problem.inlets] + [rows for rows, _ in problem.outlets])
    open_facets = space.facets_of_rows(open_rows)
    fbV = FacetBasis(space.mesh, V.elem, facets=open_facets)
    fbQ = fbV.with_element(ElementTetP1())

    # Outlets: do nothing at each one's static pressure (gauge over the first outlet's, non-dimensional).
    f_outlets = np.zeros(nv)
    for rows, pressure in problem.outlets:
        gauge = (pressure - p_ref) / scale_p
        if gauge:
            f_outlets -= gauge * asm(f_out, V.boundary(space.facets_of_rows(rows)))

    # Held velocity: walls (no slip: every component; slip: the normal one, rotated), inlets.
    wall_rows = np.asarray(problem.wall_rows, dtype=np.int64)
    slip_rows = np.asarray(problem.slip_rows if problem.slip_rows is not None else [], dtype=np.int64)
    inlet_nodes = np.unique(np.concatenate([inlet.nodes for inlet in problem.inlets])) if problem.inlets else np.zeros(0, int)
    if problem.walls == "slip":
        slipping, wall_nodes = np.concatenate([wall_rows, slip_rows]), np.zeros(0, dtype=np.int64)
    else:
        slipping = slip_rows
        wall_nodes = np.unique(boundary[wall_rows]) if len(wall_rows) else np.zeros(0, dtype=np.int64)
    wall_dofs = table[wall_nodes].ravel()
    if len(slipping):
        _, _, normals_of = _wall_geometry(space, slipping)
        T, rotated_zero = _rotation(space, normals_of, set(int(i) for i in inlet_nodes) | set(int(i) for i in wall_nodes), table)
    else:
        T, rotated_zero = sparse.identity(nv, format="csr"), np.zeros(0, dtype=np.int64)
    Tbig = sparse.block_diag([T, sparse.identity(npr)], format="csr")
    # A mass-flow inlet holds its velocity; a total-pressure inlet holds only its direction (the components
    # across it at zero) and is pushed by the static pressure its total pressure leaves at the speed it has.
    inlet_dofs = np.concatenate([np.zeros(0, dtype=np.int64)] + [
        table[inlet.nodes][:, [c for c in range(3) if inlet.kind != "total" or abs(inlet.direction[c]) < 0.5]].ravel()
        for inlet in problem.inlets])
    total_bases = [(i, V.boundary(space.facets_of_rows(inlet.rows))) for i, inlet in enumerate(problem.inlets) if inlet.kind == "total"]
    held = np.unique(np.concatenate([inlet_dofs, wall_dofs, rotated_zero]).astype(np.int64))
    free = np.ones(n, dtype=bool)
    free[held] = False
    free_ids = np.flatnonzero(free)
    timings["setup_s"] = time.perf_counter() - started

    inlet_bases = [FacetBasis(space.mesh, ElementTetP1(), facets=space.facets_of_rows(inlet.rows)) for inlet in problem.inlets]

    def mean_on(fb, p) -> float:
        values = fb.interpolate(p).value
        return float((values * fb.dx).sum() / fb.dx.sum())

    def inflow_speed(index: int, share: float, p, current: float) -> float:
        """The inlet's target mean speed (non-dimensional) at the inlet's static pressure now."""
        inlet = problem.inlets[index]
        static = max(P_REF + mean_on(inlet_bases[index], p), 1e-3 * P_REF)
        if inlet.kind == "total":
            p0 = (p_ref + share * (inlet.total_pressure_Pa - p_ref)) / scale_p
            ratio = min(static / p0, 1.0) if p0 > 0 else 1.0
            return math.sqrt(max(2.0 * cp * (1.0 - ratio ** ((g - 1.0) / g)), 0.0))
        if inlet.kind == "velocity":
            return share * inlet.velocity_m_s * 1000.0 / c0
        # Mass flow: speed = mdot / (rho A), rho at the static pressure and the temperature of this speed.
        mdot = share * inlet.mass_flow_kg_s / (rho_ref * (c0 / 1000.0) * inlet.area_mm2 * 1e-6)
        speed = current
        for _ in range(30):
            temperature = max(1.0 - 0.5 * (g - 1.0) * speed * speed, T_FLOOR)
            speed = mdot / max(g * static / temperature, 1e-12)
        return speed

    def held_values(speeds: list[float]) -> "np.ndarray":
        values = np.zeros(n)
        for inlet, speed in zip(problem.inlets, speeds):
            if inlet.kind == "total":
                continue
            for c in range(3):
                values[table[inlet.nodes, c]] = speed * inlet.weights * inlet.direction[c]
        if len(wall_dofs):
            values[wall_dofs] = 0.0
        return values[held]

    solves = {"count": 0}
    warnings: list[str] = []

    def linear(K, rhs, values):
        solves["count"] += 1
        Kr = (Tbig.T @ K @ Tbig).tocsr()
        br = Tbig.T @ rhs
        x = np.zeros(n)
        x[held] = values
        b = br[free_ids] - Kr[free_ids][:, held] @ values
        K_ff = Kr[free_ids][:, free_ids].tocsc()
        solved = None
        if solver == "iterative":
            solved = _gmres(K_ff, b, int(free[:nv].sum()), Mp[free[nv:]])
            if solved is None and not warnings:
                warnings.append("the iterative flow solver stalled, so the direct solver finished the run")
        if solved is None:
            solved = _factor(K_ff).solve(b)
        x[free_ids] = solved
        if not np.all(np.isfinite(x)):
            raise RuntimeError("the gas flow's linear solve produced non-finite values")
        return Tbig @ x

    dx = ops.dx
    D, DT = ops.D, ops.DT
    frozen: dict[str, Any] = {"coefficients": None, "last": None}

    def system(u, p, cfl_now: float, floor: float, share: float = 1.0, uniform: bool = False):
        """The linearised step at (u, p): the matrix, its right-hand side, the peak Mach and the shock cells."""
        b, gb = ops.velocity(u)
        pq = ops.N1 @ p
        speed2 = (b ** 2).sum(axis=0)
        temperature = np.maximum(1.0 - 0.5 * (g - 1.0) * speed2, T_FLOOR)
        psi = g / temperature
        rho = psi * np.maximum(P_REF + pq, 1e-6 * P_REF)
        speed = np.sqrt(speed2)
        sound = np.sqrt(temperature)
        mach = speed / sound
        viscous = mu_nd(temperature)
        mu = viscous if problem.walls == "no_slip" else np.zeros_like(temperature)
        divergence = gb[0, 0] + gb[1, 1] + gb[2, 2]
        bulk = mu / 3.0 + SHOCK_C * rho * h * h * np.maximum(-divergence, 0.0)
        # From rest the first step's pseudo-time is one everywhere: m u + grad p = 0 with div u = 0 is potential flow.
        dtau = cfl_now * (float(h.mean()) if uniform else h) / (np.maximum(speed, floor) + sound)
        m = rho / dtau
        mc = psi / dtau
        hp = 0.5 * h
        peclet = speed * hp / (2.0 * np.maximum(viscous / rho, 1e-30))
        with np.errstate(divide="ignore", invalid="ignore"):
            sd = np.where(peclet > 1.0, rho * hp / (2.0 * speed) * (1.0 - 1.0 / peclet), 0.0)
            switch = np.clip((mach - UPWIND_FROM) / (UPWIND_FULL - UPWIND_FROM), 0.0, 1.0)
            tau = np.where(speed > 0, switch * h / (2.0 * speed), 0.0)
        # Near the steady state the stabilisation's coefficients are held (they follow the flow nonlinearly and
        # would otherwise make the last steps a slow fixed point, or a limit cycle at a shock).
        if frozen["coefficients"] is not None:
            bulk, sd, tau = frozen["coefficients"]
        elif frozen["last"] is not None and not uniform:
            # The shock's viscosity and the upwinding switch follow the flow from step to step; taken whole, a shock
            # sitting between two elements flips them back and forth. They move a share of the way each step.
            bulk = RELAX * bulk + (1.0 - RELAX) * frozen["last"][0]
            tau = RELAX * tau + (1.0 - RELAX) * frozen["last"][2]
        frozen["last"] = (bulk, sd, tau)
        C2 = sum(sparse.diags(b[c]) @ ops.G2[c] for c in range(3)).tocsr()
        scalar = ops.N2T @ sparse.diags(dx * rho) @ C2 + ops.N2T @ sparse.diags(dx * m) @ ops.N2
        scalar = scalar + C2.T @ sparse.diags(dx * sd) @ C2
        if problem.walls == "no_slip":
            scalar = scalar + sum(ops.G2T[c] @ sparse.diags(dx * mu) @ ops.G2[c] for c in range(3))
        A = ops.expand(scalar) + DT @ sparse.diags(dx * bulk) @ D
        f_u = ops.expand(ops.N2T @ sparse.diags(dx * m) @ ops.N2) @ u + f_outlets
        # Newton's part of the convection: rho (u . grad) u_k, and its right-hand side rho (u_k . grad) u_k.
        rows, cols, data = [], [], []
        for i in range(3):
            f_u[table[:, i]] += ops.N2T @ (dx * rho * np.einsum("j...,j...->...", gb[i], b))
            for j in range(3):
                block = (ops.N2T @ sparse.diags(dx * rho * gb[i, j]) @ ops.N2).tocoo()
                rows.append(table[block.row, i]); cols.append(table[block.col, j]); data.append(block.data)
        A = A + sparse.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(nv, nv))
        Cu = -sum(ops.G1T[c] @ sparse.diags(dx * rho) @ ops.N2 @ ops.pick[c] for c in range(3))
        # The density falls with the speed (T = T0 - |u|^2 / 2 cp): d rho / d u = rho (gamma - 1) u / T, Newton's part.
        k = rho * (g - 1.0) / temperature
        Cu = Cu - sum(ops.G1T[c] @ sparse.diags(dx * k * b[c] * b[j]) @ ops.N2 @ ops.pick[j] for c in range(3) for j in range(3))
        # ... and the momentum's density too: d rho (u_k . grad) u_k, with d rho = (rho/p) dp + (d rho / d u) . du.
        acc = np.einsum("ij...,j...->i...", gb, b)
        rows, cols, data, p_rows, p_cols, p_data = [], [], [], [], [], []
        for i in range(3):
            f_u[table[:, i]] += ops.N2T @ (dx * (psi * pq + k * speed2) * acc[i])
            block = (ops.N2T @ sparse.diags(dx * psi * acc[i]) @ ops.N1).tocoo()
            p_rows.append(table[block.row, i]); p_cols.append(block.col); p_data.append(block.data)
            for j in range(3):
                block = (ops.N2T @ sparse.diags(dx * k * acc[i] * b[j]) @ ops.N2).tocoo()
                rows.append(table[block.row, i]); cols.append(table[block.col, j]); data.append(block.data)
        A = A + sparse.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(nv, nv))
        density_p = sparse.csr_matrix((np.concatenate(p_data), (np.concatenate(p_rows), np.concatenate(p_cols))), shape=(nv, npr))
        Bq = sum(sparse.diags(b[c]) @ ops.G1[c] for c in range(3)).tocsr()
        Cp = -sum(ops.G1T[c] @ sparse.diags(dx * psi * b[c]) @ ops.N1 for c in range(3))
        Cp = Cp + ops.N1T @ sparse.diags(dx * mc) @ ops.N1 + Bq.T @ sparse.diags(dx * tau * psi) @ Bq
        # The upwinding is SUPG: it weights mass's whole residual along the flow, div(rho u) = (rho/p) u . grad p
        # + rho div u + (d rho / d u) . (grad u) u, so it vanishes on the exact flow and moves no mass.
        Cu = Cu + Bq.T @ sparse.diags(dx * tau * rho) @ D
        Cu = Cu + sum(Bq.T @ sparse.diags(dx * tau * k * b[i] * b[j]) @ ops.G2[j] @ ops.pick[i] for i in range(3) for j in range(3))
        f_p = -sum(ops.G1T[c] @ (dx * psi * b[c] * pq) for c in range(3)) + ops.N1T @ (dx * mc * pq)
        f_p = f_p - sum(ops.G1T[c] @ (dx * k * b[c] * speed2) for c in range(3))
        # The mass flux through the openings.
        bu = fbV.interpolate(u).value
        pv = fbQ.interpolate(p).value
        ft = np.maximum(1.0 - 0.5 * (g - 1.0) * (bu ** 2).sum(axis=0), T_FLOOR)
        fpsi = g / ft
        frho = fpsi * np.maximum(P_REF + pv, 1e-6 * P_REF)
        fk = frho * (g - 1.0) / ft
        Cu = Cu + asm(f_flux_u, fbV, fbQ, rho=frho, b=bu, k=fk)
        Cp = Cp + asm(f_flux_p, fbQ, b=bu, psi=fpsi)
        f_p = f_p + asm(f_flux_rhs, fbQ, b=bu, psi=fpsi, pk=pv, k=fk)
        # Total-pressure inlets: do nothing at the static pressure their total pressure leaves at the local speed,
        # p_s = p0 (T / T0)^(gamma / (gamma - 1)), with Bernoulli's derivative dp_s = -rho_s u . du in the matrix.
        for index, fb in total_bases:
            inlet = problem.inlets[index]
            p0 = (p_ref + share * (inlet.total_pressure_Pa - p_ref)) / scale_p
            A = A + asm(f_bernoulli, fb, b=fb.interpolate(u).value, p0=p0, g=g)
            f_u = f_u - asm(f_inlet_rhs, fb, b=fb.interpolate(u).value, p0=p0, g=g, pref=P_REF)
        # SUPG's pressure part: the streamline test function sees the whole momentum residual, so the
        # stabilisation vanishes on the exact flow (no total-pressure loss from it in a smooth expansion).
        weight = sparse.diags(dx * sd / rho)
        rows_p, cols_p, data_p = [], [], []
        for i in range(3):
            block = (C2.T @ weight @ ops.G1[i]).tocoo()
            rows_p.append(table[block.row, i]); cols_p.append(block.col); data_p.append(block.data)
        Gp = ops.grad_p + density_p + sparse.csr_matrix((np.concatenate(data_p), (np.concatenate(rows_p), np.concatenate(cols_p))),
                                                    shape=(nv, npr))
        K = sparse.bmat([[A, Gp], [Cu, Cp]], format="csr")
        shocks = int(((divergence < 0) & (mach > 0.8)).reshape(E, Qn).any(axis=1).sum())
        return K, np.concatenate([f_u, f_p]), float(mach.max()), shocks

    def inflow_now(inlet: GasInlet, u):
        nodal = np.stack([u[table[inlet.nodes, c]] for c in range(3)], axis=1)
        return float(np.mean(nodal @ inlet.direction))

    def march(x, share: float, residual_tol: float, change_tol: float, steps_left: int, cfl_start: float):
        """Pseudo-time steps at ``share`` of the drive until the steady residual and the change settle."""
        u, p = x[:nv], x[nv:]
        speeds = [inflow_now(inlet, u) for inlet in problem.inlets]
        if not any(speeds):
            speeds = [0.5 * inflow_speed(i, share, p, 0.0) for i in range(len(problem.inlets))]
        # The speed the drive could reach (the total pressure expanded to the outlet's): the march's speed floor.
        drive = max([inflow_speed(i, share, np.zeros_like(p), 0.0) for i in range(len(problem.inlets))] + [1e-6])
        cfl_now, growth = cfl_start, cfl[1]
        largest = 0.0
        last = math.inf
        residual = change = math.inf
        steps = 0
        shocks = 0
        history = []
        for steps in range(1, steps_left + 1):
            targets = [inflow_speed(i, share, p, speed) for i, speed in enumerate(speeds)]
            speeds = [s + INLET_RELAX * (t - s) for s, t in zip(speeds, targets)]
            values = held_values(speeds)
            floor = 0.1 * max(max(speeds, default=0.0), drive)
            K, rhs, peak, shocks = system(u, p, cfl_now, floor, share, uniform=not np.any(u))
            # The steady residual of the current state (the pseudo-time terms cancel at it), the inflow as held.
            xr = Tbig.T @ x
            xr[held] = values
            xs = Tbig @ xr
            residual_abs = float(np.linalg.norm((Tbig.T @ (K @ xs - rhs))[free_ids]))
            largest = max(largest, residual_abs)
            residual = residual_abs / max(largest, 1e-300)
            x_new = linear(K, rhs, values)
            # A step that would move the gas by more than STEP_LIMIT of the speed of sound (or its pressure by that
            # share) is cut back along its own direction: the march stays where the linearisation holds.
            delta = x_new - x
            reach = max(float(np.abs(delta[:nv]).max()) / STEP_LIMIT, float(np.abs(delta[nv:]).max()) / (STEP_LIMIT * P_REF))
            alpha = min(1.0, 1.0 / reach) if reach > 0 else 1.0
            x_new = x + alpha * delta
            scale = max(float(np.abs(x_new[:nv]).max()), 1e-12)
            change = max(float(np.abs(x_new[:nv] - u).max()) / scale,
                         float(np.abs(x_new[nv:] - p).max()) / max(scale * scale, 1e-12))
            x = x_new
            u, p = x[:nv], x[nv:]
            history.append(residual)
            if frozen["coefficients"] is None and residual < FREEZE_AT and alpha == 1.0:
                frozen["coefficients"] = frozen["last"]
            if log and (steps % 10 == 0 or steps < 4):
                log(f"gas flow: share {share:.3g}, step {steps}, CFL {cfl_now:.3g}, residual {residual:.1e}, "
                    f"change {change:.1e}, peak Mach {peak:.3f}")
            inflow_settled = all(abs(t - s) <= 10 * change_tol * max(abs(t), 1e-12) for s, t in zip(speeds, targets))
            if residual < residual_tol and change < change_tol and inflow_settled:
                return True, x, residual, steps, shocks, history
            # Switched evolution relaxation on the steady residual; a cut step or a growing residual halves the CFL.
            if alpha < 1.0 or residual > 2.0 * last:
                cfl_now = max(cfl_now / 2.0, CFL_MIN)
            elif residual < last:
                cfl_now = min(cfl_now * growth, CFL_MAX)
            last = residual
        return False, x, residual, steps, shocks, history


    def stepped(x, shares):
        ok, residual, total, history, shocks = True, math.inf, 0, [], 0
        for share in shares:
            final = share >= 1.0 - 1e-12
            frozen["coefficients"] = None
            frozen["last"] = None
            ok, x, residual, steps, shocks, h_ = march(x, share, RESIDUAL_TOL if final else STAGE_RESIDUAL,
                                                       CHANGE_TOL if final else STAGE_CHANGE, max_steps, cfl[0])
            total += steps
            history += h_
            if log:
                log(f"gas flow: stage {share:.3g} of the drive, residual {residual:.2e}")
        return ok, x, residual, total, history, shocks

    started = time.perf_counter()
    x0 = np.zeros(n)
    continued = bool(schedule)
    if schedule:
        stages = list(schedule)
        ok, x, residual, total_steps, history, shocks = stepped(x0, stages)
    else:
        stages = [1.0]
        ok, x, residual, total_steps, history, shocks = stepped(x0, stages)
        if not ok:
            if log:
                log(f"gas flow: the march did not settle at the full drive (residual {residual:.2e}); stepping it up")
            continued = True
            ok2, x2, residual2, steps2, history2, shocks2 = stepped(np.zeros(n), list(CONTINUATION))
            total_steps += steps2
            history += history2
            if ok2 or residual2 < residual:
                ok, x, residual, stages, shocks = ok2, x2, residual2, list(CONTINUATION), shocks2
    timings["march_s"] = time.perf_counter() - started
    if not ok:
        warnings.append(f"the gas flow stopped at a residual of {residual:.1e} of its largest, short of {RESIDUAL_TOL:.0e}: "
                        "its numbers are approximate")

    # Back to engine units at the nodes.
    u_nd, p_nd = x[:nv], x[nv:]
    nodal = space.nodal(u_nd)
    speed2 = (nodal ** 2).sum(axis=1)
    temperature = np.maximum(1.0 - 0.5 * (g - 1.0) * speed2, T_FLOOR)
    p_nodes = np.zeros(space.scalar_count)
    p_nodes[: space.vertices] = p_nd[: space.vertices]
    edges = space.mesh.edges
    p_nodes[space.scalar.edge_dofs[0]] = 0.5 * (p_nd[edges[0]] + p_nd[edges[1]])
    density = g * (P_REF + p_nodes) / temperature * rho_ref

    def mass_through(rows) -> float:
        fb = FacetBasis(space.mesh, V.elem, facets=space.facets_of_rows(rows))
        fq = fb.with_element(ElementTetP1())
        bu = fb.interpolate(u_nd).value
        pv = fq.interpolate(p_nd).value
        tf = np.maximum(1.0 - 0.5 * (g - 1.0) * (bu ** 2).sum(axis=0), T_FLOOR)
        rho = g * (P_REF + pv) / tf
        flux = (rho * np.einsum("i...,i...->...", bu, fb.normals) * fb.dx).sum()
        return float(flux) * rho_ref * (c0 / 1000.0) * 1e-6

    b_end, gb_end = ops.velocity(u_nd)
    t_end = np.maximum(1.0 - 0.5 * (g - 1.0) * (b_end ** 2).sum(axis=0), T_FLOOR)
    compression = (-(gb_end[0, 0] + gb_end[1, 1] + gb_end[2, 2]) * h / np.sqrt(t_end)).reshape(E, Qn).max(axis=1)
    inflow = [-mass_through(inlet.rows) for inlet in problem.inlets]
    outflow = [mass_through(rows) for rows, _ in problem.outlets]
    inlet_static = [(P_REF + mean_on(fb, p_nd)) * scale_p for fb in inlet_bases]
    inlet_total = []
    for inlet, static in zip(problem.inlets, inlet_static):
        speed = inflow_now(inlet, u_nd)
        t = max(1.0 - 0.5 * (g - 1.0) * speed * speed, T_FLOOR)
        inlet_total.append(static * t ** (-g / (g - 1.0)))
    return GasSolution(
        u=u_nd * c0, p=(P_REF + p_nd) * scale_p, pressure_basis=Q, temperature_K=temperature * T0,
        mach=np.sqrt(speed2 / temperature), density=density, pressure_nodes_Pa=(P_REF + p_nodes) * scale_p, converged=ok,
        residual=float(residual), steps=total_steps, stages=stages, continued=continued, solver=solver,
        linear_solves=solves["count"], inflow_kg_s=inflow, outflow_kg_s=outflow, inlet_static_Pa=inlet_static,
        inlet_total_Pa=inlet_total, shock_cells=shocks, compression=compression, warnings=warnings, timings=timings, history=history,
    )


class _Operators:
    """Every element integral the march needs, as sparse products of quadrature-point operators.

    Each basis function's value and gradient at every quadrature point is laid out once as a sparse
    (points x DOFs) matrix (N for values, G[c] for each derivative); a form with a weight w at the points
    is then N^T diag(w dx) N, G^T diag(w dx) N, ..., which is far quicker than assembling the vector
    forms element by element every step."""

    def __init__(self, space):
        import numpy as np
        from scipy import sparse
        from skfem import ElementTetP1

        from cadgen._internal.fea.navier_stokes import vector_dofs

        S = space.scalar
        P = S.with_element(ElementTetP1())
        self.S, self.P = S, P
        self.shape = S.dx.shape                                   # (E, Qn)
        E, Qn = self.shape
        self.dx = np.asarray(S.dx).ravel()
        self.m = E * Qn
        rows = np.arange(self.m).reshape(E, Qn)

        def operators(basis, count):
            dofs = basis.element_dofs                             # (local, E)
            value, grads = [], [[], [], []]
            r = np.broadcast_to(rows[None], (dofs.shape[0], E, Qn)).ravel()
            c = np.broadcast_to(dofs[:, :, None], (dofs.shape[0], E, Qn)).ravel()
            values = np.stack([basis.basis[a][0].value for a in range(dofs.shape[0])]).ravel()
            N = sparse.csr_matrix((values, (r, c)), shape=(self.m, count))
            G = []
            for k in range(3):
                g = np.stack([basis.basis[a][0].grad[k] for a in range(dofs.shape[0])]).ravel()
                G.append(sparse.csr_matrix((g, (r, c)), shape=(self.m, count)))
            return N, G

        self.ns, self.np_ = S.N, P.N
        self.N2, self.G2 = operators(S, self.ns)
        self.N1, self.G1 = operators(P, self.np_)
        self.table = vector_dofs(space)
        self.nv = space.basis.N
        # Component selectors: scalar node values of component c from the vector DOFs.
        self.pick = [sparse.csr_matrix((np.ones(self.ns), (np.arange(self.ns), self.table[:, c])), shape=(self.ns, self.nv))
                     for c in range(3)]
        self.D = sum(self.G2[c] @ self.pick[c] for c in range(3)).tocsr()          # div u at the points
        self.N2T = self.N2.T.tocsr()
        self.G2T = [g.T.tocsr() for g in self.G2]
        self.G1T = [g.T.tocsr() for g in self.G1]
        self.N1T = self.N1.T.tocsr()
        self.DT = self.D.T.tocsr()
        # -(p, div v): constant.
        self.grad_p = (-(self.DT @ sparse.diags(self.dx) @ self.N1)).tocsr()

    def weighted(self, left_T, weight, right):
        from scipy import sparse

        return (left_T @ sparse.diags(weight * self.dx) @ right).tocsr()

    def expand(self, scalar):
        """A scalar block repeated on each velocity component (vector DOF numbering)."""
        import numpy as np
        from scipy import sparse

        coo = scalar.tocoo()
        rows = np.concatenate([self.table[coo.row, c] for c in range(3)])
        cols = np.concatenate([self.table[coo.col, c] for c in range(3)])
        return sparse.csr_matrix((np.tile(coo.data, 3), (rows, cols)), shape=(self.nv, self.nv))

    def velocity(self, u):
        """(3, M) velocity and (3, 3, M) its gradient [i, j] = d u_i / d x_j at the points."""
        import numpy as np

        comps = [self.pick[c] @ u for c in range(3)]
        value = np.stack([self.N2 @ comp for comp in comps])
        grad = np.stack([np.stack([self.G2[j] @ comp for j in range(3)]) for comp in comps])
        return value, grad


def _gmres(K, b, nv: int, mass_diagonal):
    """GMRES with a block preconditioner (multigrid on the velocity, the pressure mass diagonal); None when it stalls."""
    import numpy as np
    import pyamg
    from scipy.sparse.linalg import LinearOperator, gmres

    K = K.tocsr()
    A = K[:nv, :nv]
    Bf = K[nv:, :nv]
    try:
        ml = pyamg.smoothed_aggregation_solver((0.5 * (A + A.T)).tocsr(), B=None, max_coarse=500)
    except Exception:  # noqa: BLE001 - a hierarchy that cannot be built is a stall
        return None
    amg = ml.aspreconditioner(cycle="V")
    inv_mp = 1.0 / np.where(mass_diagonal > 0, mass_diagonal, 1.0)

    def apply(r):
        zu = amg @ r[:nv]
        return np.concatenate([zu, -inv_mp * (r[nv:] - Bf @ zu)])

    M = LinearOperator(K.shape, matvec=apply, dtype=float)
    x, _ = gmres(K, b, M=M, rtol=1e-10, restart=200, maxiter=15)
    if not np.all(np.isfinite(x)) or np.linalg.norm(K @ x - b) > 1e-6 * max(np.linalg.norm(b), 1e-300):
        return None
    return x
