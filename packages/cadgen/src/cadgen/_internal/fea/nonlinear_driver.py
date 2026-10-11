"""The nonlinear driver: the load in steps, Newton's method in each, a step cut when it does not converge.

Shared by every nonlinear analysis (``nonlinear`` now, ``contact`` next). A
:class:`NonlinearProblem` says how its internal force and tangent stiffness
follow the displacement (``evaluate``) and what a converged step keeps
(``commit``: plastic history, contact multipliers); the driver does the rest.
:func:`solve_path` takes the load factor λ from 0 to 1 in ``steps`` equal
steps. Each step is Newton's method on ``f_int(u) = λ f_ext`` over the free
DOF, with a backtracking line search on the residual. A step that does not
converge is cut in half and tried again from the last converged state, up to
:data:`MAX_HALVINGS` times; the driver then carries on at the step it got
through with (the smallest it needed). A converged step that moves the part
more than 500 times (:data:`RUNAWAY`) as far as the elastic part would for the same load is cut the same
way: the part is running away (a plastic hinge has formed). A step that still does not converge at
the smallest size is where the part stops carrying more load: the path ends
there, ``collapsed``, at the last converged λ: a result, never a refusal.

With ``adaptive`` (the ladder's ``adaptive_steps`` rung) the step also grows
again, doubling up to :data:`MAX_GROWTH` times the starting step, after a step
Newton got through in :data:`EASY_ITERATIONS` iterations or fewer: fewer
solves where the response is smooth.

A problem may settle a converged step further (contact's Uzawa updates: its optional ``settle`` and
``rollback``): a step that does not settle is cut the same way, and one that still does not at the
smallest step is kept, marked (``StepRecord.settled``), with a warning; never a refusal.

Each Newton step's linear solve is direct (SuperLU) or, on the ladder's
``iterative`` rung, Newton-Krylov: GMRES preconditioned by smoothed-aggregation
AMG on the tangent (the six rigid-body modes as its near-nullspace), the
hierarchy kept for the whole load step and rebuilt when GMRES stalls.
Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "EASY_ITERATIONS", "MAX_GROWTH", "MAX_HALVINGS", "MAX_ITERATIONS", "LinearSolver", "NonlinearProblem", "PathResult",
    "Settled", "StepRecord", "TOLERANCE", "newton", "solve_path",
]

#: A step that does not converge is halved at most this many times before the path ends (spec 5.16).
MAX_HALVINGS = 6
#: Newton iterations a step may take.
MAX_ITERATIONS = 25
#: A Newton step still this far from converged after STALLED_AFTER iterations is given up (and the load step cut).
STALLED_AFTER, STALLED_ABOVE = 12, 1e-3
#: A converged step that moved the part more than 1/RUNAWAY times what the elastic part would move for the same load
#: is a runaway: the part keeps moving with almost no extra load (a plastic hinge, a snap). It is cut like a step
#: that did not converge, so the collapse is found to within the smallest step.
RUNAWAY = 2e-3
#: Converged when the free residual is this share of the applied load (or of the internal force, when larger).
TOLERANCE = 1e-6
#: With adaptive steps: a step that converged in this many iterations or fewer lets the next one double.
EASY_ITERATIONS = 4
#: With adaptive steps: the step grows to at most this many times the starting step.
MAX_GROWTH = 4
#: Line search: the most halvings of a Newton correction, and the decrease it must make (Armijo).
LINE_SEARCH_CUTS, ARMIJO = 6, 1e-4
#: Line search: a step is also good when the energy along it, |du·r|, falls to this share of its start.
ENERGY_DROP = 0.5


class NonlinearProblem(Protocol):
    """What the driver needs of a nonlinear problem. ``u`` is the full DOF vector (fixed DOF held at 0)."""

    size: int
    free: "np.ndarray"             # the DOF Newton solves for
    external: "np.ndarray"         # the full load (λ = 1), on every DOF
    locations: "np.ndarray | None"  # (size, 3) and (size,): elasticity's rigid-body modes for AMG; None for a scalar
    component: "np.ndarray | None"

    def evaluate(self, u: "np.ndarray", *, tangent: bool) -> "tuple[np.ndarray, Any]":
        """(internal force, tangent stiffness or None) at ``u``, from the last committed state. A NaN in the
        force says the state is not physical (an element inside out): the driver backs off."""

    def commit(self, u: "np.ndarray", factor: float) -> None:
        """Keep the state at ``u``: the step to load factor ``factor`` converged."""

    # Optional, for a problem that settles further at a converged step (contact's Uzawa updates):
    #   settle(u, factor) -> Settled: the settled displacement, and whether it settled; the driver records and
    #       continues from that displacement, and commits it.
    #   rollback() -> None: forget what an unsettled settle changed, so the step can be cut and tried again.


@dataclass
class Settled:
    """What a problem's ``settle`` gives back: the displacement to keep, and whether its forces settled there."""

    u: "np.ndarray"
    settled: bool = True


@dataclass
class StepRecord:
    factor: float                   # the load factor reached, 0..1
    iterations: int
    u: "np.ndarray"                 # the full displacement there
    residual: float                 # the free residual's norm, relative
    #: False when the problem's ``settle`` did not settle at this step even at the smallest step: it was kept,
    #: and its forces do not balance (contact); True for every step of a problem with nothing to settle.
    settled: bool = True


@dataclass
class PathResult:
    records: list[StepRecord]
    collapsed: bool
    #: The last load factor the part carried (1.0 when it carried the whole load).
    factor: float
    starting_step: float
    smallest_step: float
    cuts: int
    iterations: int
    how: str
    seconds: float
    warnings: list[str] = field(default_factory=list)
    #: The path stopped cutting its steps because ``deadline_s`` had passed (it is ``collapsed`` there).
    out_of_time: bool = False

    @property
    def u(self) -> "np.ndarray":
        return self.records[-1].u

    @property
    def unsettled(self) -> list[float]:
        """The load factors of the steps kept although they did not settle (``StepRecord.settled``)."""
        return [record.factor for record in self.records if not record.settled]


class LinearSolver:
    """The Newton step's linear solve: SuperLU, or GMRES with an AMG hierarchy kept per load step."""

    def __init__(self, problem: NonlinearProblem, method: str):
        self.problem = problem
        self.method = method
        self.hierarchy = None
        self.gmres_iterations = 0
        self.factorisations = 0

    def new_step(self) -> None:
        self.hierarchy = None

    def _amg(self, Kff):
        import pyamg

        from cadgen._internal.fea.operators import rigid_body_modes

        problem = self.problem
        B = None
        if problem.locations is not None:
            B = rigid_body_modes(problem.locations[problem.free], problem.component[problem.free])
        return pyamg.smoothed_aggregation_solver(Kff, B=B, symmetry="symmetric", strength="symmetric",
                                                 smooth="energy", max_coarse=500)

    def solve(self, Kff, r: "np.ndarray") -> "np.ndarray | None":
        import numpy as np
        import scipy.sparse.linalg as spla

        if self.method != "iterative":
            self.factorisations += 1
            try:
                return spla.splu(Kff.tocsc()).solve(r)
            except RuntimeError:  # singular: the tangent lost all stiffness somewhere
                return None
        for attempt in range(2):
            if self.hierarchy is None or attempt:
                try:
                    self.hierarchy = self._amg(Kff)
                except Exception:  # a hierarchy pyamg cannot build is a step that does not converge
                    return None
            count = 0

            def tick(_):
                nonlocal count
                count += 1

            x, info = spla.gmres(Kff, r, rtol=1e-8, atol=0.0, restart=60, maxiter=8, M=self.hierarchy.aspreconditioner(),
                                 callback=tick, callback_type="pr_norm")
            self.gmres_iterations += count
            if info == 0 and np.all(np.isfinite(x)):
                return x
        return None

    @property
    def how(self) -> str:
        if self.method == "iterative":
            return f"Newton-Krylov: gmres + amg ({self.gmres_iterations} gmres iterations)"
        return f"Newton, superlu ({self.factorisations} factorisations)"


def _residual(problem: NonlinearProblem, u: "np.ndarray", factor: float) -> "tuple[np.ndarray, float, Any]":
    """(free residual, its scale, internal force) at ``u``; the scale is the larger of the applied and internal force."""
    import numpy as np

    internal, _ = problem.evaluate(u, tangent=False)
    free = problem.free
    r = factor * problem.external[free] - internal[free]
    return r, float(np.linalg.norm(internal[free])), internal


def newton(problem: NonlinearProblem, linear: LinearSolver, u0: "np.ndarray", factor: float,
           max_iterations: int = MAX_ITERATIONS, tolerance: float = TOLERANCE) -> "tuple[np.ndarray | None, int, float]":
    """Newton with a backtracking line search to load factor ``factor`` from ``u0``: (u, iterations, relative residual),
    ``u`` None when it did not converge. ``u0`` is not changed. A problem's own re-solves (contact's ``settle``) call
    it with their own :class:`LinearSolver`."""
    import numpy as np

    free = problem.free
    applied = factor * float(np.linalg.norm(problem.external[free]))
    u = u0.copy()
    linear.new_step()
    relative = math.inf
    for iteration in range(1, max_iterations + 1):
        internal, K = problem.evaluate(u, tangent=True)
        if not np.all(np.isfinite(internal)):
            return None, iteration, math.inf
        r = factor * problem.external[free] - internal[free]
        scale = max(applied, float(np.linalg.norm(internal[free])), 1e-300)
        norm = float(np.linalg.norm(r))
        relative = norm / scale
        if relative <= tolerance:
            return u, iteration - 1, relative
        if iteration > STALLED_AFTER and relative > STALLED_ABOVE:
            return None, iteration, relative
        Kff = K[free][:, free].tocsr()
        du = linear.solve(Kff, r)
        if du is None or not np.all(np.isfinite(du)):
            return None, iteration, relative
        # Backtracking: the longest step along du (1, 1/2, ...) that lowers the residual enough, or the energy
        # along du (|du·r|, which a nearly incompressible rubber's residual norm misjudges); else the best tried,
        # so a hard iteration still moves.
        alpha, best = 1.0, None
        slope = abs(float(du @ r))
        for _ in range(LINE_SEARCH_CUTS + 1):
            trial = u.copy()
            trial[free] += alpha * du
            r_trial, _, internal_trial = _residual(problem, trial, factor)
            finite = bool(np.all(np.isfinite(internal_trial)))
            trial_norm = float(np.linalg.norm(r_trial)) if finite else math.inf
            if finite and (best is None or trial_norm < best[1]):
                best = (trial, trial_norm)
            if finite and (trial_norm <= (1.0 - ARMIJO * alpha) * norm or abs(float(du @ r_trial)) <= ENERGY_DROP * slope):
                best = (trial, trial_norm)
                break
            alpha *= 0.5
        if best is None:
            return None, iteration, relative
        if best[1] > 1e6 * max(norm, applied):
            return None, iteration, relative
        u = best[0]
    internal, _ = problem.evaluate(u, tangent=False)
    if not np.all(np.isfinite(internal)):
        return None, max_iterations, math.inf
    r = factor * problem.external[free] - internal[free]
    relative = float(np.linalg.norm(r)) / max(applied, float(np.linalg.norm(internal[free])), 1e-300)
    return (u if relative <= tolerance else None), max_iterations, relative


def _elastic_reach(problem: NonlinearProblem, linear: LinearSolver) -> float | None:
    """The largest displacement the full load would give the unloaded part, solved linearly (the stiffness a
    runaway step is measured against); None when that tangent cannot be solved."""
    import numpy as np

    _, K = problem.evaluate(np.zeros(problem.size), tangent=True)
    linear.new_step()
    d = linear.solve(K[problem.free][:, problem.free].tocsr(), problem.external[problem.free])
    reach = float(np.abs(d).max()) if d is not None and np.all(np.isfinite(d)) else 0.0
    return reach if reach > 0 else None


def solve_path(
    problem: NonlinearProblem,
    *,
    steps: int,
    solver: str = "direct",
    adaptive: bool = False,
    max_halvings: int = MAX_HALVINGS,
    max_iterations: int = MAX_ITERATIONS,
    tolerance: float = TOLERANCE,
    runaway: float | None = RUNAWAY,
    log: Callable[[str], None] | None = None,
    deadline_s: float | None = None,
) -> PathResult:
    """Follow the load from λ = 0 to 1 in ``steps`` starting steps (module docstring). Never raises for a load
    the part cannot carry: the result is ``collapsed`` at the last converged load factor.

    ``runaway`` (None to turn it off): a step whose stiffness, load over the largest displacement it adds, falls
    under this share of the unloaded part's is cut as if it had not converged.

    ``deadline_s``: seconds after which a step that needs cutting is not cut again: the path ends there, ``collapsed``
    and ``out_of_time``, with a warning that says so. A path still getting through its steps is never stopped; one
    cutting a stuck step over and over (each cut a dozen re-solves) ends in minutes, not hours."""
    import numpy as np

    started = time.perf_counter()
    steps = max(int(steps), 1)
    base = 1.0 / steps
    smallest_allowed = base / 2 ** max_halvings
    step = base
    smallest = base
    linear = LinearSolver(problem, "iterative" if solver in ("iterative", "matrix_free") else "direct")
    u = np.zeros(problem.size)
    factor = 0.0
    records: list[StepRecord] = []
    cuts = 0
    iterations = 0
    collapsed = False
    warnings: list[str] = []
    elastic = _elastic_reach(problem, linear) if runaway else None
    out_of_time = False

    def late() -> bool:
        nonlocal out_of_time
        if deadline_s is not None and time.perf_counter() - started > deadline_s:
            out_of_time = True
        return out_of_time

    while factor < 1.0 - 1e-12:
        target = min(1.0, factor + step)
        found, taken, relative = newton(problem, linear, u, target, max_iterations, tolerance)
        iterations += taken
        if found is not None and elastic:
            moved = float(np.abs(found - u).max())
            if moved > 0 and (target - factor) * elastic / moved < runaway:
                found, relative = None, math.inf
        if found is None:
            if step <= smallest_allowed * (1.0 + 1e-9) or late():
                collapsed = True
                break
            step = max(step / 2.0, smallest_allowed)
            smallest = min(smallest, step)
            cuts += 1
            if log:
                why = "ran away (moved far for the load)" if relative == math.inf else f"did not converge (residual {relative:.2g})"
                log(f"load step to {target * 100:.4g}% {why}; cutting it to {step * 100:.4g}%")
            continue
        settled = True
        settle = getattr(problem, "settle", None)
        if settle is not None:
            outcome = settle(found, target)
            if not outcome.settled and late():
                # Past the deadline a step that does not settle ends the path, at any size: kept unsettled steps
                # marching on at the smallest one can take as long as cutting.
                problem.rollback()
                collapsed = True
                break
            if not outcome.settled and step > smallest_allowed * (1.0 + 1e-9):
                # Its forces did not settle: forget the step and take a smaller one, as for one that did not converge.
                problem.rollback()
                step = max(step / 2.0, smallest_allowed)
                smallest = min(smallest, step)
                cuts += 1
                if log:
                    log(f"load step to {target * 100:.4g}% did not settle; cutting it to {step * 100:.4g}%")
                continue
            found, settled = outcome.u, outcome.settled
            if not settled:
                warnings.append(f"the step to {target * 100:.4g}% of the load did not settle even at the smallest step; "
                                "it was kept, and its forces do not balance")
        u = found
        problem.commit(u, target)
        records.append(StepRecord(target, taken, u.copy(), relative, settled))
        if log:
            log(f"load {target * 100:.4g}% in {taken} Newton iterations")
        factor = target
        if adaptive and taken <= EASY_ITERATIONS and settled:
            step = min(2.0 * step, MAX_GROWTH * base)
    if out_of_time:
        warnings.append(f"stopped cutting the load steps after {time.perf_counter() - started:.0f} s, past the "
                        f"{deadline_s:.0f} s allowed: the load could not be followed past {factor * 100:.4g}%")
        if log:
            log(warnings[-1])
    elif collapsed and log:
        log(f"no equilibrium past {factor * 100:.4g}% of the load: the part collapses there")
    return PathResult(
        records=records, collapsed=collapsed, factor=factor, starting_step=base, smallest_step=smallest, cuts=cuts,
        iterations=iterations, how=linear.how, seconds=time.perf_counter() - started, warnings=warnings,
        out_of_time=out_of_time,
    )
