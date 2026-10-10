"""Steady incompressible Navier-Stokes on Taylor-Hood tetrahedra: Stokes, Picard, Newton, Reynolds continuation.

The velocity is quadratic (``ElementVector(ElementTetP2())``), the pressure
linear (``ElementTetP1()``), on the fluid's quadratic (curved) tetrahedra:
the inf-sup stable Taylor-Hood pair, so the pressure needs no stabilisation.
The momentum equation is written in its Laplacian form,

    mu (grad u, grad v) + rho ((u . grad) u, v) - (p, div v) = - p_out (n, v)_outlet
    (q, div u) = 0

whose natural condition at an outlet is "do nothing" at the outlet's
pressure: fully developed flow leaves through it undisturbed. Walls hold the
velocity at zero, inlets at their profile, slip sides only its normal
component.

The equations are solved divided by mu, for the velocity and p / mu, so the
momentum and the continuity rows are of one size whatever the fluid (water's
mu is 1e-9 MPa s in the engine's units). The order is the textbook one:
Stokes first (the convection left out), then Picard (Oseen) iterations,
convection taken at the previous velocity, down to a residual of 1e-3, then
Newton down to 1e-8, both relative to the Stokes problem's right-hand side.
When Newton does not converge from there, the Reynolds number is reached by
continuation: the density is stepped through Re/8, Re/4, Re/2 and Re, each
stage starting from the one before (a stage that fails is halved, a few
times). A run that still does not reach 1e-8 returns its best state and says
how far it got; it is never refused.

Linear systems are solved by SuperLU, or (the ladder's ``iterative`` rung)
by Krylov methods with a block preconditioner: algebraic multigrid on the
velocity block and the pressure mass matrix's diagonal for the Schur
complement, MINRES for the symmetric Stokes system and GMRES for Oseen and
Newton. A Krylov solve that stalls falls back to SuperLU and says so.

Units are the engine's: mm, s, tonne, N, MPa. Numeric imports live inside
the functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = ["CONTINUATION", "FlowProblem", "FlowSolution", "developed_profile", "fill_unreached_pressures", "solve_flow",
           "unreached_pressures", "vector_dofs"]

#: Picard stops at this residual (relative to the Stokes right-hand side), Newton at this one.
PICARD_TOL, NEWTON_TOL = 1e-3, 1e-8
#: A continuation stage short of the target stops here: close enough to start the next from.
STAGE_TOL = 1e-4
#: Iteration caps: Picard's, and Newton's per stage.
MAX_PICARD, MAX_NEWTON = 40, 25
#: Reynolds continuation: the share of the target Re each stage solves at.
CONTINUATION = (0.125, 0.25, 0.5, 1.0)
#: A continuation stage that fails is split this many times at most.
MAX_SPLITS = 3
#: Krylov solves: the relative tolerance, and the restart length and iteration cap of GMRES.
KRYLOV_TOL, RESTART, MAX_KRYLOV = 1e-10, 200, 3000


@dataclass
class FlowProblem:
    """What the solver needs: the space, the fluid and the boundary conditions."""

    space: "FemSpace"                 # the fluid's quadratic space (velocity: its vector basis)
    rho: float                        # tonne/mm^3
    mu: float                         # MPa s
    dirichlet: "np.ndarray"           # vector DOF ids with a prescribed velocity
    values: "np.ndarray"              # their values, mm/s
    #: (skfem facets, pressure MPa) of each outlet: do-nothing at that pressure.
    outlets: list[tuple["np.ndarray", float]] = field(default_factory=list)


@dataclass
class FlowSolution:
    u: "np.ndarray"                   # vector DOF values, mm/s
    p: "np.ndarray"                   # P1 pressure at the mesh's corner vertices, MPa
    pressure_basis: Any
    converged: bool
    residual: float                   # the last relative residual
    picard: int                       # Picard iterations, every stage together
    newton: int                       # Newton iterations, every stage together
    stages: list[float]               # the Re fractions solved at (1.0 alone without continuation)
    continued: bool                   # continuation was used
    solver: str                       # "direct" or "iterative"
    linear_solves: int
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def vector_dofs(space: "FemSpace") -> "np.ndarray":
    """(scalar_count, 3): the vector basis's DOF of each scalar node and component."""
    import numpy as np

    table = np.zeros((space.scalar_count, 3), dtype=np.int64)
    for c in range(3):
        table[space.scalar.nodal_dofs[0], c] = space.basis.nodal_dofs[c]
        if space.order == 2:
            table[space.scalar.edge_dofs[0], c] = space.basis.edge_dofs[c]
    return table


def developed_profile(locations: "np.ndarray", rows: "np.ndarray", axis: int) -> dict[int, float]:
    """The fully developed laminar profile over an opening, scaled to a mean of 1, by scalar node.

    ``rows`` are the opening's quadratic boundary triangles (three corners, three mid-edge nodes) in
    scalar node ids, flat on a plane normal to ``axis``. Fully developed laminar flow through any
    cross-section solves -lap(w) = const with w = 0 on its edge (Poiseuille's parabola in a round
    pipe), so that is solved on the opening itself with quadratic triangles, each node taking its
    own value. Nodes on the opening's edge are 0.
    """
    import numpy as np
    from skfem import Basis, BilinearForm, ElementTriP2, LinearForm, MeshTri, asm, condense, solve
    from skfem.helpers import dot, grad

    corners = np.unique(rows[:, :3])
    local = {int(n): k for k, n in enumerate(corners)}
    keep = [a for a in range(3) if a != axis]
    points = np.ascontiguousarray(locations[corners][:, keep].T)
    triangles = np.vectorize(local.get)(rows[:, :3]).astype(np.int64)
    mesh = MeshTri(points, np.ascontiguousarray(triangles.T))
    basis = Basis(mesh, ElementTriP2())

    @BilinearForm
    def laplace(u, v, _):
        return dot(grad(u), grad(v))

    @LinearForm
    def unit(v, _):
        return v

    stiffness, load = asm(laplace, basis), asm(unit, basis)
    w = solve(*condense(stiffness, load, D=basis.get_dofs()))
    mean = float(load @ w) / float(load.sum())
    if not mean > 0:
        return {}
    w = w / mean
    out = {int(n): float(w[basis.nodal_dofs[0][k]]) for n, k in local.items()}
    # Each mid-edge node: the quadratic edge DOF of the edge between the two corners it sits between.
    facet_of = {tuple(pair): k for k, pair in enumerate(np.sort(mesh.facets, axis=0).T.tolist())}
    for row, tri in zip(rows, triangles):
        for m in range(3, 6):
            node = int(row[m])
            if node in out:
                continue
            # The mid node sits halfway between two of the corners: find which pair by place.
            here = locations[node]
            best = min(((a, b) for a, b in ((0, 1), (1, 2), (0, 2))),
                       key=lambda e: float(np.linalg.norm(0.5 * (locations[row[e[0]]] + locations[row[e[1]]]) - here)))
            pair = tuple(sorted((int(tri[best[0]]), int(tri[best[1]]))))
            out[node] = float(w[basis.facet_dofs[0][facet_of[pair]]])
    return out


def unreached_pressures(B, velocity_held: "np.ndarray") -> "np.ndarray":
    """The pressure DOFs no free velocity DOF reaches: their column of the saddle point is empty.

    ``B`` is the (pressure, velocity) divergence matrix and ``velocity_held`` the velocity DOFs with a
    prescribed value. A linear pressure node where an inlet meets the walls at a sharp corner (a
    rectangular duct's inlet edge and corners) can have every velocity DOF of every tetrahedron around
    it prescribed: no momentum equation sees that pressure and its continuity equation holds only
    prescribed values, so the saddle-point matrix is exactly singular there. Those pressures are taken
    out of the solve and given their neighbours' value afterwards (:func:`fill_unreached_pressures`):
    the flow never felt them, so this changes no velocity and no other pressure.
    """
    import numpy as np

    B = B.tocsr()
    free = np.ones(B.shape[1], dtype=float)
    free[np.asarray(velocity_held, dtype=np.int64)] = 0.0
    magnitude = abs(B)
    reach = np.asarray(magnitude @ free).ravel()
    scale = float(magnitude.max()) if magnitude.nnz else 0.0
    return np.flatnonzero(reach <= 1e-12 * max(scale, 1e-300))


def fill_unreached_pressures(p: "np.ndarray", unreached: "np.ndarray", element_dofs: "np.ndarray") -> "np.ndarray":
    """``p`` with each unreached pressure DOF set to the mean of its solved neighbours (sharing an element).

    ``element_dofs`` is the pressure basis's (nodes per element, elements) DOF table. Taken in waves, so a
    node whose neighbours are all unreached too takes the next wave's values.
    """
    import numpy as np

    p = np.array(p, dtype=float)
    pending = set(int(d) for d in np.asarray(unreached).tolist())
    if not pending:
        return p
    neighbours: dict[int, set[int]] = {d: set() for d in pending}
    for column in np.asarray(element_dofs).T:
        nodes = [int(n) for n in column]
        for n in nodes:
            if n in neighbours:
                neighbours[n].update(nodes)
    while pending:
        wave = {}
        for d in pending:
            known = [n for n in neighbours[d] if n != d and n not in pending]
            if known:
                wave[d] = float(np.mean(p[known]))
        if not wave:
            break
        for d, value in wave.items():
            p[d] = value
        pending -= set(wave)
    return p


# -- the forms ----------------------------------------------------------------------------------------


def _forms():
    import numpy as np
    from skfem import BilinearForm, LinearForm
    from skfem.helpers import ddot, div, dot, grad

    def along(gradient, vector):  # (vector . grad) of a vector field: gradient[i, j] vector[j]
        return np.einsum("ij...,j...->i...", gradient, vector)

    @BilinearForm
    def laplace(u, v, _):
        return ddot(grad(u), grad(v))

    @BilinearForm
    def divergence(u, q, _):
        return div(u) * q

    @BilinearForm
    def mass(p, q, _):
        return p * q

    @BilinearForm
    def convection(u, v, w):  # (w . grad) u . v
        return dot(along(grad(u), w["w"].value), v)

    @BilinearForm
    def streamline(u, v, w):  # delta (w . grad) u . (w . grad) v
        return w["delta"] * dot(along(grad(u), w["w"].value), along(grad(v), w["w"].value))

    @BilinearForm
    def newton(u, v, w):  # (u . grad) w . v
        return dot(along(w["w"].grad, u.value), v)

    @LinearForm
    def self_convection(v, w):  # (w . grad) w . v
        return dot(along(w["w"].grad, w["w"].value), v)

    @LinearForm
    def outflow(v, w):
        return dot(w.n, v)

    return laplace, divergence, mass, convection, streamline, newton, self_convection, outflow


# -- the solver ---------------------------------------------------------------------------------------


class _System:
    """The assembled pieces and the reduced (Dirichlet-free) linear solves."""

    def __init__(self, problem: FlowProblem, solver: str, log):
        import numpy as np
        from scipy import sparse
        from skfem import ElementTetP1, asm

        self.problem, self.solver, self.log = problem, solver, log
        self.warnings: list[str] = []
        self.solves = 0
        space = problem.space
        self.basis = space.basis
        self.pbasis = self.basis.with_element(ElementTetP1())
        (self.f_laplace, self.f_div, self.f_mass, self.f_conv, self.f_sd, self.f_newton, self.f_self,
         self.f_out) = _forms()
        # Each element's size for the streamline diffusion (a quadratic element resolves half of it).
        volume = np.asarray(self.basis.dx).sum(axis=1)
        self.h = 0.5 * np.cbrt(6.0 * np.sqrt(2.0) * volume)
        self.nu_inv = problem.rho / problem.mu      # 1 / kinematic viscosity, s/mm^2
        self.L = asm(self.f_laplace, self.basis).tocsr()
        self.B = (-asm(self.f_div, self.basis, self.pbasis)).tocsr()   # (Np, Nu)
        self.Mp = asm(self.f_mass, self.pbasis).tocsr()
        self.nu, self.np_ = self.basis.N, self.pbasis.N
        self.n = self.nu + self.np_
        f = np.zeros(self.nu)
        for facets, pressure in problem.outlets:
            if pressure:
                f -= (pressure / problem.mu) * asm(self.f_out, self.basis.boundary(facets))
        self.f = np.concatenate([f, np.zeros(self.np_)])
        held = np.asarray(problem.dirichlet, dtype=np.int64)
        # Pressures no free velocity reaches (an inlet's sharp corners) leave the solve; filled after it.
        self.unreached = unreached_pressures(self.B, held)
        self.D = np.concatenate([held, self.nu + self.unreached])
        self.xD = np.concatenate([np.asarray(problem.values, dtype=float), np.zeros(len(self.unreached))])
        free = np.ones(self.n, dtype=bool)
        free[self.D] = False
        self.I = np.flatnonzero(free)
        self.velocity_free = self.I[self.I < self.nu]
        self.sparse = sparse

    def matrix(self, A):
        """The saddle-point matrix [[A, B^T], [B, 0]] with momentum block ``A``."""
        sparse = self.sparse
        return sparse.bmat([[A, self.B.T], [self.B, None]], format="csr")

    def oseen(self, u, scale: float):
        """mu-scaled momentum block at velocity ``u``: L + (rho/mu) * scale * C(u)."""
        from skfem import asm

        if scale == 0:
            return self.L
        field = self.basis.interpolate(u)
        A = self.L + (self.nu_inv * scale) * asm(self.f_conv, self.basis, w=field)
        delta = self._delta(field, scale)
        if delta is not None:
            A = A + (self.nu_inv * scale) * asm(self.f_sd, self.basis, w=field, delta=delta)
        return A.tocsr()

    def _delta(self, field, scale: float):
        """Streamline diffusion's time scale per element and point: h / 2|w| (1 - 1/Pe) where the cell
        Peclet number Pe = |w| h / 2 nu passes 1, else 0. It acts only along the flow's own direction,
        so fully developed flow (no change along a streamline) is untouched. None where it is 0 everywhere."""
        import numpy as np

        speed = np.linalg.norm(field.value, axis=0)
        nu = 1.0 / (self.nu_inv * scale)
        h = self.h[:, None]
        peclet = speed * h / (2.0 * nu)
        if not (peclet > 1.0).any():
            return None
        with np.errstate(divide="ignore", invalid="ignore"):
            delta = np.where(peclet > 1.0, h / (2.0 * speed) * (1.0 - 1.0 / peclet), 0.0)
        return delta

    def newton_parts(self, u, scale: float):
        from skfem import asm

        field = self.basis.interpolate(u)
        jacobian = (self.nu_inv * scale) * asm(self.f_newton, self.basis, w=field)
        rhs = (self.nu_inv * scale) * asm(self.f_self, self.basis, w=field)
        return jacobian.tocsr(), rhs

    def reduced_rhs(self, K, rhs):
        x = self._lifted()
        return rhs[self.I] - K[self.I][:, self.D] @ self.xD, x

    def _lifted(self):
        import numpy as np

        x = np.zeros(self.n)
        x[self.D] = self.xD
        return x

    def residual(self, K, x, rhs=None) -> "np.ndarray":
        rhs = self.f if rhs is None else rhs
        return (K @ x - rhs)[self.I]

    def solve(self, K, rhs, *, symmetric: bool = False):
        """The full state of K x = rhs with the Dirichlet values held."""
        import numpy as np

        self.solves += 1
        K = K.tocsr()
        b, x = self.reduced_rhs(K, rhs)
        K_II = K[self.I][:, self.I].tocsc()
        if self.solver == "iterative":
            solved = self._krylov(K_II, b, symmetric)
            if solved is not None:
                x[self.I] = solved
                return x
        from scipy.sparse.linalg import splu

        x[self.I] = splu(K_II).solve(b)
        if not np.all(np.isfinite(x)):
            raise RuntimeError("the flow's linear solve produced non-finite values")
        return x

    def _krylov(self, K_II, b, symmetric: bool):
        """MINRES (Stokes) or GMRES (Oseen, Newton) with the block preconditioner; None when it stalls."""
        import numpy as np
        import pyamg
        from scipy.sparse.linalg import LinearOperator, gmres, minres

        nv = len(self.velocity_free)
        A = K_II[:nv, :nv]
        Bf = K_II[nv:, :nv]
        sym = (0.5 * (A + A.T)).tocsr()
        ml = pyamg.smoothed_aggregation_solver(sym, B=None, max_coarse=500)
        amg = ml.aspreconditioner(cycle="V")
        mp = np.asarray(self.Mp.diagonal())[self.I[nv:] - self.nu]
        inv_mp = 1.0 / np.where(mp > 0, mp, 1.0)

        if symmetric:
            def apply(r):
                return np.concatenate([amg @ r[:nv], inv_mp * r[nv:]])
        else:
            def apply(r):
                zu = amg @ r[:nv]
                return np.concatenate([zu, -inv_mp * (r[nv:] - Bf @ zu)])

        M = LinearOperator(K_II.shape, matvec=apply, dtype=float)
        if symmetric:
            x, info = minres(K_II, b, M=M, rtol=KRYLOV_TOL, maxiter=MAX_KRYLOV)
        else:
            x, info = gmres(K_II, b, M=M, rtol=KRYLOV_TOL, restart=RESTART, maxiter=MAX_KRYLOV // RESTART + 1)
        if info != 0 or not np.all(np.isfinite(x)):
            if not self.warnings:
                self.warnings.append("the iterative flow solver stalled, so the direct solver finished the step")
            return None
        if np.linalg.norm(K_II @ x - b) > 1e-6 * max(np.linalg.norm(b), 1e-300):
            if not self.warnings:
                self.warnings.append("the iterative flow solver stalled, so the direct solver finished the step")
            return None
        return x


def _norm(vector) -> float:
    import numpy as np

    return float(np.linalg.norm(vector))


def solve_flow(problem: FlowProblem, *, schedule: tuple[float, ...] = (), solver: str = "direct",
               log: Callable[[str], None] | None = None) -> FlowSolution:
    """The steady flow of ``problem``: Stokes, then Picard to 1e-3, then Newton to 1e-8.

    ``schedule`` (the ladder's continuation, fractions of the target Re) steps the Reynolds number up
    from the start; without one, continuation is taken only when Newton fails at the target.
    """
    import numpy as np

    timings: dict[str, float] = {}
    started = time.perf_counter()
    system = _System(problem, solver, log)
    timings["assemble_s"] = time.perf_counter() - started
    counts = {"picard": 0, "newton": 0}

    started = time.perf_counter()
    K0 = system.matrix(system.L)
    reference = max(_norm(system.reduced_rhs(K0, system.f)[0]), 1e-300)
    stokes = system.solve(K0, system.f, symmetric=True)

    def state(x, scale):
        """The momentum block at x's velocity and x's relative residual there."""
        A = system.oseen(x[:system.nu], scale)
        return A, _norm(system.residual(system.matrix(A), x)) / reference

    def nonlinear(x, scale, tol=NEWTON_TOL) -> tuple[bool, "np.ndarray", float]:
        """Picard to PICARD_TOL, then Newton to ``tol``, at ``scale`` times the density."""
        A, r = state(x, scale)
        for _ in range(MAX_PICARD):
            if r < PICARD_TOL or not np.isfinite(r):
                break
            x = system.solve(system.matrix(A), system.f)
            counts["picard"] += 1
            A, r = state(x, scale)
        best, best_r = x, r
        for _ in range(MAX_NEWTON):
            if r < tol:
                return True, x, r
            if not np.isfinite(r) or r > 1e3 * max(best_r, 1e-12):
                return False, best, best_r
            jacobian, extra = system.newton_parts(x[:system.nu], scale)
            rhs = system.f.copy()
            rhs[:system.nu] += extra
            x = system.solve(system.matrix(A + jacobian), rhs)
            counts["newton"] += 1
            A, r = state(x, scale)
            if r < best_r:
                best, best_r = x, r
        return best_r < tol, best, best_r

    def continue_from(x, fractions) -> tuple[bool, "np.ndarray", float, list[float]]:
        done: list[float] = []
        last = 0.0
        ok, r = True, 0.0
        queue = list(fractions)
        splits = 0
        while queue:
            target = queue.pop(0)
            # An intermediate stage only needs to land near its flow; the target is solved to NEWTON_TOL.
            final = target >= 1.0 - 1e-12
            ok, trial, r = nonlinear(x, target, NEWTON_TOL if final else STAGE_TOL)
            if ok or splits >= MAX_SPLITS:
                x, last = trial, target
                done.append(target)
                if log:
                    log(f"flow: Re stage {target:.3g} of the target, residual {r:.2e}")
                continue
            splits += 1
            queue[:0] = [0.5 * (last + target), target]
        return ok, x, r, done

    continued = bool(schedule)
    if schedule:
        ok, x, r, stages = continue_from(stokes, schedule)
    else:
        ok, x, r = nonlinear(stokes, 1.0)
        stages = [1.0]
        if not ok:
            continued = True
            if log:
                log(f"flow: Newton did not converge at the target (residual {r:.2e}); stepping the Reynolds number up")
            ok2, x2, r2, stages = continue_from(stokes, CONTINUATION)
            if ok2 or r2 < r:
                ok, x, r = ok2, x2, r2
    timings["nonlinear_s"] = time.perf_counter() - started
    warnings = list(system.warnings)
    if not ok:
        warnings.append(f"the flow solve stopped at a residual of {r:.1e}, short of 1e-8: its numbers are approximate")
    pressure = fill_unreached_pressures(problem.mu * x[system.nu:], system.unreached, system.pbasis.element_dofs)
    return FlowSolution(
        u=x[:system.nu], p=pressure, pressure_basis=system.pbasis, converged=ok, residual=r,
        picard=counts["picard"], newton=counts["newton"], stages=stages, continued=continued, solver=solver,
        linear_solves=system.solves, warnings=warnings, timings=timings,
    )
