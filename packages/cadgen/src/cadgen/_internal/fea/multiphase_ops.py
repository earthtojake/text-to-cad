"""Two immiscible fluids on Taylor-Hood elements: a conservative level set, variable density and viscosity.

The flow is incompressible Navier-Stokes with the density and viscosity of
whichever fluid is where, on triangles (2D) or tetrahedra (3D), in SI units:
quadratic velocity, linear pressure (the inf-sup stable Taylor-Hood pair), the
momentum equation in its stress form so the viscosity may jump,

    rho (du/dt + (u . grad) u) = -grad p + div(2 mu D(u)) + rho (g - a(t)) + f_sigma
    div u = 0

``a(t)`` is the container's own acceleration: the equations are written in its
frame, so a shaken tank is a body force -rho a. ``f_sigma`` is the surface
tension, Brackbill's continuum surface force in its tensor form (Lafaurie et
al.), -sigma (|grad H| I - grad H grad H / |grad H|) : grad v, which needs no
curvature.

**The interface.** A level set: the signed distance d to the interface
(positive in the liquid), linear on the pressure's corners and carried by the
flow (Crank-Nicolson with SUPG). The liquid's share is the smoothed step
H(d) = 1/2 (1 + tanh(d / 2 epsilon)), evaluated at each quadrature point from
d's linear interpolant, and the density and viscosity follow it. For a level
interface d is linear and exact, so the density's level lines are flat on any
mesh and a still two-fluid column stays still (the share's own linear
interpolant would wobble from element to element, and gravity, against a
1000:1 density ratio, would turn that wobble into fast spurious air currents).

When the flow has stretched or squeezed d away from a distance (its gradient
off 1 by more than ``PROFILE_TOL`` across the band), it is rebuilt
geometrically: the zero level is cut out of the mesh (segments, or the
triangles of marching tetrahedra) and each corner takes its true distance to
those pieces. **Volume.** The liquid's volume, the integral of H(d), is
monitored every step and kept by the one uniform shift d + delta that restores
it (Newton on delta; an inlet's or outlet's flux is counted in what it should
be), so it is conserved to round-off and the drift each step would have had is
reported.

**Gravity.** The hydrostatic part of the pressure is split off before the
solve, from the level function itself: with f = g - a(t),

    Phi = rho_gas f . x + (rho_liquid - rho_gas) |f| epsilon ln(1 + exp(d / epsilon))

whose gradient is exactly rho f wherever grad d points along f (a level
interface), so the momentum equation is driven by rho f - grad Phi =
(rho_liquid - rho_gas) H(d) (f - |f| grad d): zero for a still, level
interface, and the true restoring force of a tilted one. The flow's own
linear pressure carries the rest; the pressure written is the two together.

**Time.** The momentum by variable-step BDF2 (backward Euler for the first
step), convection linearised about the extrapolated velocity with streamline
diffusion past a cell Peclet number of 1, one linear solve a step (the
momentum block assembled in batches of elements, not pair by pair); the level set by Crank-Nicolson
with SUPG. Steps are CFL-limited (``cfl`` times the smallest element over the
fastest speed), capillary-limited with surface tension, grow by at most 1.5 a
step, and land on the times asked for.

**Boundaries.** Walls slide freely by default (a penalty on the normal
velocity, so a contact line moves) or hold the fluid (no slip). Inlets give a
velocity and a fluid; outlets a pressure (do-nothing, backflow stabilised). A
closed container's pressure is pinned to 0 at its highest corner.

Linear solves: SuperLU, or (``solver="iterative"``) GMRES with a block
preconditioner, algebraic multigrid on the momentum block and a
Cahouet-Chabard Schur complement; a Krylov solve that stalls falls back to
SuperLU and says so. Numeric imports inside the functions.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Opening", "Phases", "State", "TwoPhaseProblem", "TwoPhaseSolver", "heaviside", "interface_heights"]

#: Step growth at most this factor a step (variable-step BDF2 stays stable well inside 1 + sqrt 2).
GROWTH = 1.5
#: The slip penalty: this many times the stiffest term's size at a wall (mass and viscosity).
PENALTY = 1e3
#: The interface's half thickness epsilon as a share of the mean element size.
EPSILON_SHARE = 0.35
#: The profile is rebuilt once the band's mean |grad d| is off 1 by more than this.
PROFILE_TOL = 0.15
#: Elements per batch of the vectorised assembly.
CHUNK = 2000
#: An inlet's level function: this many epsilons into the fluid it brings.
INLET_DEPTH = 6.0
#: Krylov solves: relative tolerance, restart and cap.
KRYLOV_TOL, RESTART, MAX_KRYLOV = 1e-8, 100, 1500


@dataclass(frozen=True)
class Phases:
    """The two fluids: the liquid's (H = 1) and the gas's (H = 0) density kg/m^3 and viscosity Pa s, and the
    surface tension between them, N/m (0 for none)."""

    rho_liquid: float
    rho_gas: float
    mu_liquid: float
    mu_gas: float
    sigma: float = 0.0


@dataclass
class Opening:
    """An inlet (a velocity and the fluid it brings) or an outlet (a pressure) on boundary facets."""

    facets: Any                                # skfem facet indices
    kind: str                                  # "inlet" or "outlet"
    velocity: Any = None                       # inlet: the velocity vector, m/s
    phase: float = 1.0                         # inlet: 1 brings liquid, 0 gas
    pressure: float = 0.0                      # outlet: Pa


@dataclass
class TwoPhaseProblem:
    mesh: Any                                  # skfem MeshTri or MeshTet, metres
    phases: Phases
    distance: Any                              # signed distance to the interface at the vertices, m (> 0 in the liquid)
    gravity: Any                               # (dim,) m/s^2
    #: The container's own acceleration a(t), m/s^2 (the fluid feels -a); None for a still container.
    acceleration: Callable[[float], Any] | None = None
    noslip: Any = None                         # facets holding the fluid (default none)
    openings: list[Opening] = field(default_factory=list)
    #: The interface's half thickness, m; default ``EPSILON_SHARE`` of the mean element size.
    epsilon: float | None = None


@dataclass
class State:
    """The flow at a step: time, the step taken, velocity (vector DOFs), pressure (vertex values, Pa, gauge to the
    pin), the liquid's share H(d) and the level set d (vertex values)."""

    t: float
    dt: float
    step: int
    u: Any
    p: Any
    share: Any
    distance: Any
    volume: float                              # the liquid's volume, the integral of H(d), m^3 (m^2 in 2D)
    max_speed: float


def heaviside(distance, epsilon: float):
    """The level set's profile: 1/2 (1 + tanh(d / 2 epsilon)), d the signed distance (positive in the liquid)."""
    import numpy as np

    return 0.5 * (1.0 + np.tanh(np.asarray(distance, dtype=float) / (2.0 * epsilon)))


def interface_heights(mesh, distance, up) -> "Any":
    """Where the interface (d = 0) crosses the mesh's edges, as heights along ``up`` (a unit vector): one per crossing."""
    import numpy as np

    edges = mesh.edges if mesh.p.shape[0] == 3 else mesh.facets
    a, b = distance[edges[0]], distance[edges[1]]
    cross = a * b < 0
    if not cross.any():
        return np.zeros(0)
    s = a[cross] / (a[cross] - b[cross])
    za = up @ mesh.p[:, edges[0, cross]]
    zb = up @ mesh.p[:, edges[1, cross]]
    return za + s * (zb - za)


def _elements(dim: int):
    from skfem import ElementTetP1, ElementTetP2, ElementTriP1, ElementTriP2, ElementVector

    if dim == 2:
        return ElementVector(ElementTriP2()), ElementTriP1()
    return ElementVector(ElementTetP2()), ElementTetP1()


def _forms():
    import numpy as np
    from skfem import BilinearForm, LinearForm
    from skfem.helpers import div, dot, grad

    @BilinearForm
    def divergence(u, q, _):
        return -div(u) * q

    @BilinearForm
    def normal_penalty(u, v, w):
        return dot(u, w.n) * dot(v, w.n)

    @BilinearForm
    def backflow(u, v, w):            # 1/2 rho |min(a . n, 0)| u . v on an outlet
        return 0.5 * w["rho"] * np.maximum(-dot(w["a"], w.n), 0.0) * dot(u, v)

    @LinearForm
    def capillary(v, w):              # -(|g| I - g g / |g|) : grad v, g = grad H
        g = w["g"]
        size = np.sqrt((g * g).sum(axis=0))
        safe = np.where(size > 0, size, 1.0)
        gv = grad(v)
        trace = np.einsum("ii...->...", gv)
        return -(size * trace - np.einsum("i...,ij...,j...->...", g, gv, g) / safe)

    @LinearForm
    def outflow(v, w):
        return dot(w.n, v)

    @BilinearForm
    def scalar_mass(u, v, _):
        return u * v

    @BilinearForm
    def supg_mass(u, v, w):           # tau d (a . grad w)
        return w["tau"] * u * dot(w["a"], grad(v))

    @BilinearForm
    def supg_convection(u, v, w):     # (a . grad d)(w + tau a . grad w)
        ag = dot(w["a"], grad(u))
        return ag * v + w["tau"] * ag * dot(w["a"], grad(v))

    @BilinearForm
    def inverse_density_laplace(u, v, w):
        return dot(grad(u), grad(v)) / w["rho"]

    @LinearForm
    def potential_push(v, w):         # Phi (v . n): the hydrostatic split's pressure on an outlet
        return w["Phi"] * dot(v, w.n)

    return dict(divergence=divergence, normal_penalty=normal_penalty, backflow=backflow, capillary=capillary, outflow=outflow, scalar_mass=scalar_mass, supg_mass=supg_mass,
                supg_convection=supg_convection, inverse_density_laplace=inverse_density_laplace,
                potential_push=potential_push)


# -- the interface's pieces and the distance to them ----------------------------------------------------


def _segments(points, level, cells):
    """2D: the zero level of a linear function on triangles, as segments (S, 2, 2)."""
    import numpy as np

    s = level[cells].astype(float)                                           # (3, T)
    s = np.where(s == 0, 1e-14, s)
    crossing = (s.max(axis=0) > 0) & (s.min(axis=0) < 0)
    tri, s = cells[:, crossing], s[:, crossing]
    ends = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        cut = s[a] * s[b] < 0
        t = np.where(cut, s[a] / np.where(cut, s[a] - s[b], 1.0), np.nan)
        ends.append(points[:, tri[a]].T + t[:, None] * (points[:, tri[b]] - points[:, tri[a]]).T)
    ends = np.stack(ends, axis=1)                                   # (T, 3, 2), NaN where an edge is not cut
    order = np.argsort(np.isnan(ends[:, :, 0]), axis=1, kind="stable")
    return np.take_along_axis(ends, order[:, :, None], axis=1)[:, :2]


def _triangles(points, level, cells):
    """3D: the zero level of a linear function on tetrahedra (marching tetrahedra), as triangles (T, 3, 3)."""
    import numpy as np

    s = level[cells].astype(float)                                           # (4, E)
    s = np.where(s == 0, 1e-14, s)
    above = (s > 0).sum(axis=0)
    out = []

    def cut(tet, sv, a, b):                                          # the crossing on edge (a, b), per tet
        sa = np.take_along_axis(sv, a[None], axis=0)[0]
        sb = np.take_along_axis(sv, b[None], axis=0)[0]
        pa = points[:, np.take_along_axis(tet, a[None], axis=0)[0]].T
        pb = points[:, np.take_along_axis(tet, b[None], axis=0)[0]].T
        return pa + (sa / (sa - sb))[:, None] * (pb - pa)

    for count in (1, 3):
        sel = above == count
        if not sel.any():
            continue
        tet, sv = cells[:, sel], s[:, sel]
        lone = np.argmax(sv > 0, axis=0) if count == 1 else np.argmax(sv < 0, axis=0)
        others = np.array([[k for k in range(4) if k != j] for j in range(4)])[lone].T   # (3, E)
        out.append(np.stack([cut(tet, sv, lone, others[k]) for k in range(3)], axis=1))
    sel = above == 2
    if sel.any():
        tet, sv = cells[:, sel], s[:, sel]
        order = np.argsort(-sv, axis=0)                              # the two above first
        a, b, c, d = order
        p1, p2, p3, p4 = cut(tet, sv, a, c), cut(tet, sv, b, c), cut(tet, sv, b, d), cut(tet, sv, a, d)
        out.append(np.stack([p1, p2, p3], axis=1))
        out.append(np.stack([p1, p3, p4], axis=1))
    return np.concatenate(out, axis=0) if out else np.zeros((0, 3, 3))


def _segment_distance(p, a, b):
    import numpy as np

    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-300), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def _triangle_distance(p, a, b, c):
    """Distance from points to triangles, row by row (Ericson's closest point, vectorised)."""
    import numpy as np

    def d(x, y):
        return np.einsum("ij,ij->i", x, y)

    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = d(ab, ap), d(ac, ap)
    bp = p - b
    d3, d4 = d(ab, bp), d(ac, bp)
    cp = p - c
    d5, d6 = d(ab, cp), d(ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = 1.0 / (va + vb + vc)
        closest = a + (vb * denom)[:, None] * ab + (vc * denom)[:, None] * ac          # inside the face
        t_ab = d1 / (d1 - d3)
        t_ac = d2 / (d2 - d6)
        t_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
    # Edges, then corners (Ericson's order reversed: the later a region here, the more it wins).
    regions = [
        ((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), b + t_bc[:, None] * (c - b)),
        ((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + t_ac[:, None] * ac),
        ((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + t_ab[:, None] * ab),
        ((d6 >= 0) & (d5 <= d6), c),
        ((d3 >= 0) & (d4 <= d3), b),
        ((d1 <= 0) & (d2 <= 0), a),
    ]
    for mask, point in regions:
        closest = np.where(mask[:, None], point, closest)
    return np.linalg.norm(p - closest, axis=1)


class TwoPhaseSolver:
    """The march: build once, then ``run`` steps to the end, calling back after each."""

    def __init__(self, problem: TwoPhaseProblem, *, solver: str = "direct", cfl: float = 0.5,
                 log: Callable[[str], None] | None = None):
        import numpy as np
        from skfem import Basis, FacetBasis, asm

        self.problem, self.solver, self.cfl, self.log = problem, solver, cfl, log
        mesh = problem.mesh
        self.mesh = mesh
        self.dim = mesh.p.shape[0]
        self.forms = _forms()
        velocity, scalar = _elements(self.dim)
        self.ubasis = Basis(mesh, velocity, intorder=4)
        self.pbasis = self.ubasis.with_element(scalar)
        self.nu, self.np_ = self.ubasis.N, self.pbasis.N
        self.n = self.nu + self.np_
        self.phases = problem.phases
        self.gravity = np.asarray(problem.gravity, dtype=float)
        g = float(np.linalg.norm(self.gravity))
        self.up = -self.gravity / g if g > 0 else np.eye(self.dim)[-1]

        volume = np.asarray(self.ubasis.dx).sum(axis=1)
        self.h = np.cbrt(6.0 * math.sqrt(2.0) * volume) if self.dim == 3 else np.sqrt(4.0 * volume / math.sqrt(3.0))
        self.h_min, self.h_mean, self.h_max = float(self.h.min()), float(self.h.mean()), float(self.h.max())
        self.epsilon = float(problem.epsilon) if problem.epsilon else EPSILON_SHARE * self.h_mean

        self.B = asm(self.forms["divergence"], self.ubasis, self.pbasis).tocsr()       # (np, nu)
        self.Mphi = asm(self.forms["scalar_mass"], self.pbasis).tocsr()
        self.weights = np.asarray(self.Mphi.sum(axis=0)).ravel()                       # the integral of each hat
        self.Mp_diag = np.asarray(self.Mphi.diagonal())
        self.top = int(np.argmax(self.up @ mesh.p))
        self.f_now = self.gravity.copy()

        # Boundary facets: openings, no-slip, and the rest slide.
        boundary = mesh.boundary_facets()
        opening_facets = np.concatenate([np.asarray(o.facets, dtype=np.int64) for o in problem.openings]) \
            if problem.openings else np.zeros(0, dtype=np.int64)
        noslip = np.asarray(problem.noslip if problem.noslip is not None else [], dtype=np.int64)
        slip = np.setdiff1d(boundary, np.concatenate([opening_facets, noslip]))
        self.slip_facets, self.noslip_facets = slip, noslip
        self.wall_facets = np.setdiff1d(boundary, opening_facets)
        self.P = asm(self.forms["normal_penalty"], FacetBasis(mesh, velocity, facets=slip, intorder=4)).tocsr() \
            if len(slip) else None

        # Dirichlet velocity: inlets at their velocity, no-slip walls at 0 (walls win at a rim).
        values: dict[int, float] = {}
        component = self._component_of()
        for opening in problem.openings:
            if opening.kind == "inlet":
                vel = np.asarray(opening.velocity, dtype=float)
                for dof in self.ubasis.get_dofs(facets=np.asarray(opening.facets, dtype=np.int64)).flatten():
                    values[int(dof)] = float(vel[component[dof]])
        if len(noslip):
            for dof in self.ubasis.get_dofs(facets=noslip).flatten():
                values[int(dof)] = 0.0
        self.D_u = np.fromiter(values.keys(), dtype=np.int64, count=len(values))
        self.x_u = np.fromiter(values.values(), dtype=float, count=len(values))

        # Outlets: their pressure (do-nothing) and backflow.
        self.outlet_rhs = np.zeros(self.nu)
        self.outlet_bases = []
        for opening in problem.openings:
            if opening.kind == "outlet":
                fb = FacetBasis(mesh, velocity, facets=np.asarray(opening.facets, dtype=np.int64), intorder=4)
                self.outlet_bases.append((fb, fb.with_element(scalar)))
                if opening.pressure:
                    self.outlet_rhs -= opening.pressure * asm(self.forms["outflow"], fb)
        # The level set at inlets: inside the fluid each brings.
        inlet_values: dict[int, float] = {}
        for opening in problem.openings:
            if opening.kind == "inlet":
                for vertex in np.unique(mesh.facets[:, np.asarray(opening.facets, dtype=np.int64)]):
                    inlet_values[int(vertex)] = INLET_DEPTH * self.epsilon * (1.0 if opening.phase >= 0.5 else -1.0)
        self.D_d = np.fromiter(inlet_values.keys(), dtype=np.int64, count=len(inlet_values))
        self.x_d = np.fromiter(inlet_values.values(), dtype=float, count=len(inlet_values))
        self.open = bool(problem.openings)
        # A closed container (no outlet): the flow's pressure is pinned to 0 at its highest corner.
        self.pin = None if any(o.kind == "outlet" for o in problem.openings) else self.top

        free = np.ones(self.n, dtype=bool)
        free[self.D_u] = False
        if self.pin is not None:
            free[self.nu + self.pin] = False
        self.I = np.flatnonzero(free)
        self.warnings: list[str] = []
        self.solves = 0
        self.krylov_fallbacks = 0
        self.rebuilds = 0
        self._walls = None
        self.timings: dict[str, float] = {"assemble_s": 0.0, "solve_s": 0.0, "level_set_s": 0.0}

        self.distance = np.asarray(problem.distance, dtype=float).copy()
        if len(self.D_d):
            self.distance[self.D_d] = self.x_d
        self.dx = np.asarray(self.pbasis.dx)
        self.volume0 = self.volume(self.distance)
        self.expected_volume = self.volume0
        self.max_drift = 0.0
        self.corrections = 0

    # -- helpers ------------------------------------------------------------------------------------

    def _component_of(self):
        """Each vector DOF's component (0, 1, 2)."""
        import numpy as np

        out = np.zeros(self.nu, dtype=np.int64)
        for table in (self.ubasis.nodal_dofs, self.ubasis.facet_dofs, self.ubasis.edge_dofs):
            for c in range(table.shape[0]):
                out[table[c]] = c
        return out

    def fraction(self, distance):
        """The liquid's share at the quadrature points: H of the level function's linear interpolant."""
        return heaviside(self.pbasis.interpolate(distance).value, self.epsilon)

    def properties(self, distance):
        """(rho, mu) at the quadrature points."""
        h = self.fraction(distance)
        ph = self.phases
        return ph.rho_gas + (ph.rho_liquid - ph.rho_gas) * h, ph.mu_gas + (ph.mu_liquid - ph.mu_gas) * h

    def volume(self, distance, shift: float = 0.0) -> float:
        """The liquid's volume: the integral of H(d + shift), m^3 (m^2 in 2D)."""
        return float((self.dx * heaviside(self.pbasis.interpolate(distance).value + shift, self.epsilon)).sum())

    def share(self, distance):
        """The liquid's share at the corners, H(d)."""
        return heaviside(distance, self.epsilon)

    def nodal_velocity(self, u):
        """(vertices, dim) the velocity at the mesh's corners."""
        import numpy as np

        return np.stack([u[self.ubasis.nodal_dofs[c]] for c in range(self.dim)], axis=1)

    def body_acceleration(self, t: float):
        """The body force per unit mass the fluid feels in the container's frame: g - a(t)."""
        import numpy as np

        if self.problem.acceleration is None:
            return self.gravity.copy()
        return self.gravity - np.asarray(self.problem.acceleration(t), dtype=float)

    def _tau_steady(self, speed, nu):
        """Streamline diffusion's time scale: h / 2|a| (1 - 1/Pe) past a cell Peclet number of 1, else 0."""
        import numpy as np

        h = self.h[:, None]
        peclet = speed * h / (2.0 * nu)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(peclet > 1.0, h / (2.0 * speed) * (1.0 - 1.0 / peclet), 0.0)

    def _tau(self, speed, dt: float):
        import numpy as np

        return 1.0 / np.sqrt((2.0 / dt) ** 2 + (2.0 * speed / self.h[:, None]) ** 2)

    def potential(self, distance, x, f):
        """The hydrostatic split Phi at points ``x`` (dim, ...) with level function values ``distance`` there, Pa."""
        import numpy as np

        ph = self.phases
        size = float(np.linalg.norm(f))
        return ph.rho_gas * np.einsum("i,i...->...", f, x) \
            + (ph.rho_liquid - ph.rho_gas) * size * self.epsilon * np.logaddexp(0.0, distance / self.epsilon)

    def pressure(self, p, distance) -> "Any":
        """The pressure at the mesh's corners, Pa: the flow's own plus the hydrostatic split's; gauge to the highest
        corner in a closed container."""
        total = p + self.potential(distance, self.mesh.p, self.f_now)
        return total - total[self.pin] if self.pin is not None else total

    def wall_force(self, p, about=None):
        """The fluid's pressure force on the walls, N (N/m in 2D): the integral of p n, n out of the fluid; and its
        moment about ``about`` (3 components; z alone in 2D), N m. ``p`` at the corners."""
        import numpy as np
        from skfem import FacetBasis

        if self._walls is None:
            if len(self.wall_facets) == 0:
                return np.zeros(self.dim), np.zeros(3)
            fb = FacetBasis(self.mesh, _elements(self.dim)[1], facets=self.wall_facets, intorder=3)
            self._walls = (fb, np.asarray(fb.normals), np.asarray(fb.dx), np.asarray(fb.global_coordinates().value))
        fb, normals, dx, x = self._walls
        pq = fb.interpolate(p).value * dx                                   # (F, Q)
        force = np.einsum("ifq,fq->i", normals, pq)
        moment = np.zeros(3)
        if about is not None:
            arm = x - np.asarray(about, dtype=float)[:, None, None]
            if self.dim == 3:
                moment = np.einsum("ifq,fq->i", np.cross(arm, normals, axis=0), pq)
            else:
                moment[2] = float(((arm[0] * normals[1] - arm[1] * normals[0]) * pq).sum())
        return force, moment

    def set_level_set(self, distance):
        """Start from this level set instead (and its liquid volume)."""
        import numpy as np

        self.distance = np.asarray(distance, dtype=float).copy()
        if len(self.D_d):
            self.distance[self.D_d] = self.x_d
        self.volume0 = self.expected_volume = self.volume(self.distance)

    def at_points(self, points):
        """A matrix taking corner values to values at ``points`` (dim, N), each inside the mesh; and which were."""
        import numpy as np
        from scipy import sparse

        points = np.asarray(points, dtype=float)
        finder = self.mesh.element_finder()
        try:
            elements = finder(*points)
        except ValueError:
            elements = np.array([self._find(finder, points[:, k]) for k in range(points.shape[1])])
        inside = elements >= 0
        rows, cols, vals = [], [], []
        for k in np.flatnonzero(inside):
            corners = self.mesh.p[:, self.mesh.t[:, elements[k]]]
            T = (corners[:, 1:] - corners[:, :1])
            lam = np.linalg.solve(T, points[:, k] - corners[:, 0])
            weights = np.concatenate([[1.0 - lam.sum()], lam])
            rows += [k] * len(weights)
            cols += list(self.mesh.t[:, elements[k]])
            vals += list(weights)
        return sparse.csr_matrix((vals, (rows, cols)), shape=(points.shape[1], self.mesh.p.shape[1])), inside

    @staticmethod
    def _find(finder, point) -> int:
        try:
            return int(finder(*point[:, None])[0])
        except ValueError:
            return -1

    # -- the level set ------------------------------------------------------------------------------

    def advect(self, distance, u_adv, dt: float):
        """The level set carried by the flow: Crank-Nicolson with SUPG."""
        import numpy as np
        from skfem import asm

        a = self.ubasis.interpolate(u_adv).value
        speed = np.sqrt((a * a).sum(axis=0))
        tau = self._tau(speed, dt)
        Ms = self.Mphi + asm(self.forms["supg_mass"], self.pbasis, a=a, tau=tau)
        Cs = asm(self.forms["supg_convection"], self.pbasis, a=a, tau=tau)
        return self._solve_scalar((Ms + 0.5 * dt * Cs).tocsr(), (Ms - 0.5 * dt * Cs) @ distance, self.D_d, self.x_d)

    def profile_error(self, distance) -> float:
        """How far the level function's gradient is from 1 across the band (mean over its elements)."""
        import numpy as np

        g = self.pbasis.interpolate(distance).grad[..., 0]          # (dim, E): constant per element
        corners = distance[self.mesh.t]
        band = np.abs(corners).max(axis=0) < 2.0 * self.epsilon
        if not band.any():
            return 0.0
        return float(np.abs(np.sqrt((g[:, band] ** 2).sum(axis=0)) - 1.0).mean())

    def rebuild(self, distance):
        """The true signed distance to the level set's zero level at every corner."""
        import numpy as np
        from scipy.spatial import cKDTree

        points = self.mesh.p
        sign = np.where(distance >= 0, 1.0, -1.0)
        pieces = _triangles(points, distance, self.mesh.t) if self.dim == 3 else _segments(points, distance, self.mesh.t)
        if len(pieces) == 0:
            return distance
        k = min(12, len(pieces))
        _, index = cKDTree(pieces.mean(axis=1)).query(points.T, k=k)
        index = index.reshape(points.shape[1], k)
        best = np.full(points.shape[1], np.inf)
        p = points.T
        for column in range(k):
            piece = pieces[index[:, column]]
            dist = _triangle_distance(p, piece[:, 0], piece[:, 1], piece[:, 2]) if self.dim == 3 \
                else _segment_distance(p, piece[:, 0], piece[:, 1])
            best = np.fmin(best, dist)                   # a degenerate piece (zero area) gives NaN: skip it
        best = np.where(np.isfinite(best), best, np.abs(distance))
        out = sign * best
        if len(self.D_d):
            out[self.D_d] = self.x_d
        return out

    def keep_volume(self, distance, target: float):
        """d + delta, with the one shift delta that gives the liquid volume ``target``."""
        eps = self.epsilon
        level = self.pbasis.interpolate(distance).value
        delta = 0.0
        for _ in range(30):
            share = heaviside(level + delta, eps)
            miss = float((self.dx * share).sum()) - target
            slope = float((self.dx * share * (1.0 - share)).sum()) / eps
            if slope <= 0 or abs(miss) <= 1e-14 * max(abs(target), 1e-300):
                break
            delta -= miss / slope
        out = distance + delta
        if len(self.D_d):
            out[self.D_d] = self.x_d
        return out

    def _solve_scalar(self, A, b, D, xD, lu=None):
        import numpy as np
        from scipy.sparse.linalg import splu

        x = np.zeros(A.shape[0])
        x[D] = xD
        keep = np.ones(A.shape[0], dtype=bool)
        keep[D] = False
        idx = np.flatnonzero(keep)
        rhs = b[idx] - (A[idx][:, D] @ xD if len(D) else 0.0)
        if lu is None:
            lu = splu(A[idx][:, idx].tocsc())
        x[idx] = lu.solve(rhs)
        return x

    def interface_step(self, distance, u_adv, dt: float):
        """Carry the level set, rebuild it when it has drifted from a distance, keep the liquid's volume."""
        distance = self.advect(distance, u_adv, dt)
        if self.open:
            self.expected_volume += dt * self._inflow(distance, u_adv)
        target = self.expected_volume
        self.max_drift = max(self.max_drift, abs(self.volume(distance) - target) / max(abs(self.volume0), 1e-300))
        if self.profile_error(distance) > PROFILE_TOL:
            self.rebuilds += 1
            distance = self.rebuild(distance)
        return self.keep_volume(distance, target)

    # -- the momentum -------------------------------------------------------------------------------

    def momentum(self, u_n, u_nm1, distance, t_new: float, dt: float, dt_old: float | None):
        """One BDF2 (or, first, backward-Euler) step: the new velocity and the flow's own pressure."""
        import numpy as np
        from scipy import sparse
        from skfem import asm

        started = time.perf_counter()
        if dt_old is None:
            c0, c1, c2 = 1.0 / dt, -1.0 / dt, 0.0
            u_star = u_n
        else:
            w = dt / dt_old
            c0 = (1.0 + 2.0 * w) / ((1.0 + w) * dt)
            c1 = -(1.0 + w) / dt
            c2 = w * w / ((1.0 + w) * dt)
            u_star = (1.0 + w) * u_n - w * u_nm1
        rho, mu = self.properties(distance)
        a = self.ubasis.interpolate(u_star).value
        speed = np.sqrt((a * a).sum(axis=0))
        tau = self._tau_steady(speed, mu / rho)
        A = self._momentum_matrix(rho, mu, a, tau, c0)
        rho_max = max(self.phases.rho_liquid, self.phases.rho_gas)
        mu_max = max(self.phases.mu_liquid, self.phases.mu_gas)
        if self.P is not None:
            A = A + PENALTY * (rho_max * self.h_mean * c0 + mu_max / self.h_mean) * self.P
        for fb, fs in self.outlet_bases:
            share = heaviside(fs.interpolate(distance).value, self.epsilon)
            rho_f = self.phases.rho_gas + (self.phases.rho_liquid - self.phases.rho_gas) * share
            A = A + asm(self.forms["backflow"], fb, a=fb.interpolate(u_star).value, rho=rho_f)
        f = self.body_acceleration(t_new)
        self.f_now = f
        level = self.pbasis.interpolate(distance)
        # rho f - grad Phi = (rho_l - rho_g) H(d) (f - |f| grad d): what drives the flow once the hydrostatic split is off.
        share = heaviside(level.value, self.epsilon)
        drive = (self.phases.rho_liquid - self.phases.rho_gas) * share[None] \
            * (f[:, None, None] - float(np.linalg.norm(f)) * level.grad)
        history = self.ubasis.interpolate(c1 * u_n + c2 * u_nm1).value
        rhs_u = self._vector_load(drive - rho[None] * history) + self.outlet_rhs
        for fb, fs in self.outlet_bases:
            d_f = fs.interpolate(distance).value
            rhs_u = rhs_u + asm(self.forms["potential_push"], fb, Phi=self.potential(d_f, fb.global_coordinates().value, f))
        if self.phases.sigma > 0:
            slope = 1.0 / (4.0 * self.epsilon * np.cosh(level.value / (2.0 * self.epsilon)) ** 2)
            rhs_u = rhs_u + self.phases.sigma * asm(self.forms["capillary"], self.ubasis, g=slope * level.grad)
        K = sparse.bmat([[A, self.B.T], [self.B, None]], format="csr")
        rhs = np.concatenate([rhs_u, np.zeros(self.np_)])
        self.timings["assemble_s"] += time.perf_counter() - started
        started = time.perf_counter()
        x = self._solve(K, rhs, rho=rho, mu_max=mu_max, c0=c0)
        self.timings["solve_s"] += time.perf_counter() - started
        return x[:self.nu], x[self.nu:]

    # Vectorised assembly of the momentum block: skfem's loop over every pair of the 30 (3D) local basis functions
    # is the run's cost on a small mesh, so the local matrices are batched products over chunks of elements instead.

    def _chunks(self):
        n_el = self.mesh.t.shape[1]
        for start in range(0, n_el, CHUNK):
            yield slice(start, min(start + CHUNK, n_el))

    def _local(self, part):
        """The basis functions' values (E, n, d, Q) and gradients (E, n, d, d, Q) on a chunk of elements."""
        import numpy as np

        values = np.stack([b[0].value[:, part] for b in self.ubasis.basis]).transpose(2, 0, 1, 3)
        grads = np.stack([b[0].grad[:, :, part] for b in self.ubasis.basis]).transpose(3, 0, 1, 2, 4)
        return values, grads

    def _momentum_matrix(self, rho, mu, a, tau, c0: float):
        """rho c0 (u, v) + rho ((a . grad) u, v) + rho tau ((a . grad) u, (a . grad) v) + 2 mu (D(u), D(v))."""
        import numpy as np
        from scipy import sparse

        dx = np.asarray(self.ubasis.dx)
        dofs = self.ubasis.element_dofs                               # (n, E)
        n = dofs.shape[0]
        rows, cols, data = [], [], []
        for part in self._chunks():
            values, grads = self._local(part)                         # (E, n, d, Q), (E, n, d, d, Q)
            E, _, d, Q = values.shape
            conv = \
                np.einsum("enklq,elq->enkq", grads, a[:, part].transpose(1, 0, 2))
            sym = 0.5 * (grads + grads.transpose(0, 1, 3, 2, 4))
            w = dx[part]
            V = values.reshape(E, n, d * Q)
            C = conv.reshape(E, n, d * Q)
            S = sym.reshape(E, n, d * d * Q)

            def weight(field, times):
                return np.repeat(field[:, None, :], times, axis=1).reshape(E, times * Q)

            r = rho[part] * w
            K = (V * weight(c0 * r, d)[:, None, :]) @ V.transpose(0, 2, 1)
            K += (V * weight(r, d)[:, None, :]) @ C.transpose(0, 2, 1)
            K += (C * weight(r * tau[part], d)[:, None, :]) @ C.transpose(0, 2, 1)
            K += (S * weight(2.0 * mu[part] * w, d * d)[:, None, :]) @ S.transpose(0, 2, 1)
            local = dofs[:, part]                                     # (n, E)
            rows.append(np.broadcast_to(local.T[:, :, None], (E, n, n)).ravel())
            cols.append(np.broadcast_to(local.T[:, None, :], (E, n, n)).ravel())
            data.append(K.ravel())
        return sparse.coo_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
                                 shape=(self.nu, self.nu)).tocsr()

    def _vector_load(self, field):
        """The integral of field . v for every velocity test function; ``field`` (d, E, Q) at the quadrature points."""
        import numpy as np

        dx = np.asarray(self.ubasis.dx)
        dofs = self.ubasis.element_dofs
        out = np.zeros(self.nu)
        for part in self._chunks():
            values, _ = self._local(part)
            local = np.einsum("enkq,keq,eq->en", values, field[:, part], dx[part])
            np.add.at(out, dofs[:, part].T.ravel(), local.ravel())
        return out

    def _solve(self, K, rhs, *, rho, mu_max: float, c0: float):
        import numpy as np

        self.solves += 1
        x = np.zeros(self.n)
        x[self.D_u] = self.x_u
        fixed = np.setdiff1d(np.arange(self.n), self.I)
        b = rhs[self.I] - K[self.I][:, fixed] @ x[fixed]
        K_II = K[self.I][:, self.I].tocsc()
        if self.solver == "iterative":
            solved = self._krylov(K_II, b, rho=rho, mu_max=mu_max, c0=c0)
            if solved is not None:
                x[self.I] = solved
                return x
        x[self.I] = self._direct(K_II, b)
        return x

    @staticmethod
    def _direct(K_II, b):
        """SuperLU: first in symmetric mode on the symmetric pattern (several times faster on this saddle point),
        else with column ordering and partial pivoting."""
        import numpy as np
        from scipy.sparse.linalg import splu

        try:
            solution = splu(K_II, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                            options={"SymmetricMode": True}).solve(b)
            if np.all(np.isfinite(solution)) and np.linalg.norm(K_II @ solution - b) <= 1e-8 * max(np.linalg.norm(b), 1e-300):
                return solution
        except RuntimeError:
            pass
        solution = splu(K_II).solve(b)
        if not np.all(np.isfinite(solution)):
            raise RuntimeError("the two-fluid flow's linear solve produced non-finite values")
        return solution

    def _krylov(self, K_II, b, *, rho, mu_max: float, c0: float):
        """GMRES with block-triangular preconditioning: AMG on the momentum block, Cahouet-Chabard for the Schur
        complement (c0 times the inverse of a 1/rho pressure Laplacian, plus mu over the pressure mass)."""
        import numpy as np
        import pyamg
        from scipy import sparse
        from scipy.sparse.linalg import LinearOperator, gmres
        from skfem import asm

        nv = int((self.I < self.nu).sum())
        A = K_II[:nv, :nv]
        Bf = K_II[nv:, :nv]
        pressure = self.I[nv:] - self.nu
        L = asm(self.forms["inverse_density_laplace"], self.pbasis, rho=rho).tocsr()[pressure][:, pressure]
        mp = self.Mp_diag[pressure]
        L = L + 1e-10 * float(abs(L).max()) * sparse.identity(len(pressure), format="csr")
        try:
            ml_u = pyamg.smoothed_aggregation_solver((0.5 * (A + A.T)).tocsr(), max_coarse=500)
            ml_p = pyamg.smoothed_aggregation_solver(L.tocsr(), max_coarse=500)
        except Exception:  # noqa: BLE001  (a hierarchy that cannot be built: the direct solver finishes)
            return None
        amg_u, amg_p = ml_u.aspreconditioner(cycle="V"), ml_p.aspreconditioner(cycle="V")
        inv_mp = 1.0 / np.where(mp > 0, mp, 1.0)

        def apply(r):
            zu = amg_u @ r[:nv]
            rp = r[nv:] - Bf @ zu
            return np.concatenate([zu, -(c0 * (amg_p @ rp) + mu_max * inv_mp * rp)])

        M = LinearOperator(K_II.shape, matvec=apply, dtype=float)
        x, info = gmres(K_II, b, M=M, rtol=KRYLOV_TOL, restart=RESTART, maxiter=MAX_KRYLOV // RESTART + 1)
        if info != 0 or not np.all(np.isfinite(x)) or np.linalg.norm(K_II @ x - b) > 1e-6 * max(np.linalg.norm(b), 1e-300):
            self.krylov_fallbacks += 1
            if not any("iterative" in w for w in self.warnings):
                self.warnings.append("the iterative two-fluid solver stalled on some steps, so the direct solver finished them")
            return None
        return x

    # -- the march ----------------------------------------------------------------------------------

    def capillary_step(self) -> float:
        """Brackbill's capillary limit, sqrt((rho_l + rho_g) h^3 / (4 pi sigma)); inf with no surface tension."""
        ph = self.phases
        if ph.sigma <= 0:
            return math.inf
        return math.sqrt((ph.rho_liquid + ph.rho_gas) * self.h_min ** 3 / (4.0 * math.pi * ph.sigma))

    def run(self, end_s: float, *, dt_max: float, stops: Sequence[float] = (), dt_first: float | None = None,
            on_step: Callable[[State], None] | None = None) -> State:
        """March from rest to ``end_s``: steps CFL-limited and at most ``dt_max``, landing on each of ``stops``."""
        import numpy as np

        u_n = np.zeros(self.nu)
        u_n[self.D_u] = self.x_u
        u_nm1 = u_n.copy()
        distance = self.distance
        t, step, dt_old = 0.0, 0, None
        stops = sorted(s for s in stops if 0 < s < end_s) + [end_s]
        state = State(0.0, 0.0, 0, u_n, self.pressure(np.zeros(self.np_), distance), self.share(distance), distance,
                      self.volume0, 0.0)
        if on_step:
            on_step(state)
        dt_cap = min(dt_max, self.capillary_step())
        dt = min(dt_first or dt_cap, dt_cap)
        tiny = 1e-12 * max(end_s, 1.0)
        while t < end_s - tiny:
            speed = float(np.linalg.norm(self.nodal_velocity(u_n), axis=1).max())
            limit = dt_cap if speed <= 0 else min(dt_cap, self.cfl * self.h_min / speed)
            dt = min(limit, GROWTH * dt_old) if dt_old else min(limit, dt)
            target = next(s for s in stops if s > t + tiny)
            if t + dt > target - 1e-9 * dt:
                dt = target - t
            elif t + 1.5 * dt > target:      # no sliver of a step before a stop
                dt = 0.5 * (target - t)
            started = time.perf_counter()
            u_adv = u_n if dt_old is None else (1.0 + 0.5 * dt / dt_old) * u_n - 0.5 * dt / dt_old * u_nm1
            distance = self.interface_step(distance, u_adv, dt)
            self.timings["level_set_s"] += time.perf_counter() - started
            u_new, p = self.momentum(u_n, u_nm1, distance, t + dt, dt, dt_old)
            if not np.all(np.isfinite(u_new)):
                raise RuntimeError("the two-fluid flow blew up; a smaller step or a finer mesh is needed")
            u_nm1, u_n = u_n, u_new
            t += dt
            step += 1
            dt_old = dt
            speed = float(np.linalg.norm(self.nodal_velocity(u_n), axis=1).max())
            state = State(t, dt, step, u_n, self.pressure(p, distance), self.share(distance), distance,
                          self.volume(distance), speed)
            if on_step:
                on_step(state)
        self.distance = distance
        return state

    def _inflow(self, distance, u) -> float:
        """The liquid's volume flow into the container through its openings, m^3/s: minus the integral of H u . n."""
        import numpy as np
        from skfem import FacetBasis, Functional

        total = 0.0
        velocity, scalar = _elements(self.dim)
        for opening in self.problem.openings:
            fu = FacetBasis(self.mesh, velocity, facets=np.asarray(opening.facets, dtype=np.int64), intorder=3)
            fp = fu.with_element(scalar)
            total -= Functional(lambda w: w["phi"] * (w["u"] * w.n).sum(axis=0)).assemble(
                fu, u=fu.interpolate(u).value, phi=heaviside(fp.interpolate(distance).value, self.epsilon))
        return float(total)
