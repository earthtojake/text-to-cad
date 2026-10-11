"""Time stepping: second-order (structural) and first-order (heat) systems marched through time.

Three integrators the time-dependent analyses share:

- :func:`newmark`: M ü + C u̇ + K u = f(t) by Newmark's average acceleration
  (β = 1/4, γ = 1/2): unconditionally stable and with no numerical damping, so
  an undamped part keeps ringing at its full size. With ``adaptive`` the step
  is controlled by the local error estimate of Zienkiewicz and Xie,
  e = Δt² (β − 1/6) (aₙ₊₁ − aₙ), measured on the lowest modes' coordinates
  (a mesh-scale ripple no step resolves must not drive it down): a step whose
  error passes ``tolerance`` of the largest motion so far is taken again at
  half the size, and one well under it lets the next step double.
- :func:`modal_march`: each mode an oscillator q̈ + 2ζωq̇ + ω²q = p(t),
  integrated exactly for a load that is linear between the time points (the
  recurrence of Nigam and Jennings): no step-size error at all for a step, a
  ramp or a table, and only the load's own interpolation for a curve.
- :func:`theta`: C u̇ + K u = f(t) by the θ method (θ = 1 backward Euler,
  θ = 1/2 Crank-Nicolson), with step doubling when ``adaptive``.

Each takes the matrices on the free DOF already (held DOF removed) and calls
``on_step(t, u, ...)`` at t = 0 and after every accepted step, so an analysis
keeps what it needs (a curve, an envelope, the frames) without the run storing
every state. Units are the caller's; numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "NEWMARK_TOLERANCE", "THETA_TOLERANCE", "March", "modal_march", "newmark", "newmark_error", "rayleigh", "theta",
]

#: Newmark's adaptive steps keep each step's local error under this share of the largest motion so far.
NEWMARK_TOLERANCE = 1e-3
#: The θ method's adaptive steps keep the whole step and its two halves within this share of the state's range.
THETA_TOLERANCE = 1e-3
#: A step under this error share times the tolerance lets the next step double.
GROW_BELOW = 1.0 / 8.0
#: Adaptive steps never halve more than this many times below the first step.
MAX_HALVINGS = 12
#: Factorisations an adaptive run keeps, one per step size it has used.
_CACHE = 8


@dataclass
class March:
    """What a time march did: its step counts and sizes, and how it solved."""

    steps: int = 0
    rejected: int = 0
    smallest_step: float = 0.0
    largest_step: float = 0.0
    factorisations: int = 0
    how: str = ""
    warnings: list[str] = field(default_factory=list)


def rayleigh(omega_1: float, omega_2: float | None, zeta: float) -> tuple[float, float]:
    """(α, β) of Rayleigh damping C = αM + βK with damping ratio ``zeta`` at ω₁ and ω₂ (rad/s).

    ζ(ω) = α/(2ω) + βω/2, so with two modes α = 2ζω₁ω₂/(ω₁+ω₂), β = 2ζ/(ω₁+ω₂); with one mode
    (``omega_2`` None or equal) it is ζ at ω₁ exactly by α = ζω₁, β = ζ/ω₁."""
    if zeta == 0 or omega_1 <= 0:
        return 0.0, 0.0
    if omega_2 is None or abs(omega_2 - omega_1) <= 1e-9 * omega_1:
        return zeta * omega_1, zeta / omega_1
    total = omega_1 + omega_2
    return 2.0 * zeta * omega_1 * omega_2 / total, 2.0 * zeta / total


def newmark_error(dt: float, a_old: "np.ndarray", a_new: "np.ndarray", beta: float = 0.25) -> "np.ndarray":
    """Newmark's local displacement error estimate over one step: Δt² (β − 1/6) (aₙ₊₁ − aₙ)."""
    return (dt * dt * (beta - 1.0 / 6.0)) * (a_new - a_old)


class _Solver:
    """Solves with one matrix: a SuperLU factor, or multigrid-preconditioned CG warm-started from the last answer."""

    def __init__(self, A, kind: str, near_null=None):
        import scipy.sparse.linalg as spla

        self.kind = kind
        self.last = None
        if kind == "direct":
            self._lu = spla.splu(A.tocsc())
        else:
            import pyamg

            self._A = A.tocsr()
            self._ml = pyamg.smoothed_aggregation_solver(
                self._A, B=near_null, symmetry="symmetric", strength="symmetric", smooth="energy", max_coarse=500)
        self.iterations = 0

    def __call__(self, b: "np.ndarray") -> "np.ndarray":
        if self.kind == "direct":
            return self._lu.solve(b)
        residuals: list[float] = []
        x = self._ml.solve(b, x0=self.last, tol=1e-10, accel="cg", maxiter=400, residuals=residuals)
        self.iterations += len(residuals)
        self.last = x
        return x


def _clamp_to(t: float, dt: float, stops: Sequence[float], end: float) -> float:
    """``dt``, shortened so the step lands on the next stop (a load's corner, the end) rather than passing it."""
    for stop in stops:
        if stop > t * (1 + 1e-12) + 1e-300 and t + dt > stop * (1 + 1e-9):
            return stop - t
    return min(dt, end - t)


def newmark(
    M,
    C,
    K,
    load: Callable[[float], "np.ndarray"],
    end_s: float,
    step_s: float,
    *,
    u0: "np.ndarray | None" = None,
    v0: "np.ndarray | None" = None,
    beta: float = 0.25,
    gamma: float = 0.5,
    adaptive: bool = False,
    tolerance: float = NEWMARK_TOLERANCE,
    largest_step: float | None = None,
    stops: Sequence[float] = (),
    solver: str = "direct",
    near_null=None,
    error_modes: "np.ndarray | None" = None,
    on_step: Callable[[float, "np.ndarray", "np.ndarray", "np.ndarray"], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> March:
    """M ü + C u̇ + K u = load(t) from t = 0 to ``end_s`` by Newmark's method, first step ``step_s``.

    ``C`` may be ``None`` (undamped). ``stops`` are times a step must land on (a load's corners), as is
    ``end_s``. ``solver`` is ``"direct"`` (SuperLU of K + C γ/(βΔt) + M/(βΔt²), once per step size) or
    ``"iterative"`` (multigrid CG, warm-started; ``near_null`` its near-nullspace, the rigid motions).
    ``adaptive`` controls the step by :func:`newmark_error` (see the module), its size measured on
    ``error_modes`` (mass-normalised columns, the lowest modes: the motion that matters) when given, else
    in the mass norm. ``on_step(t, u, v, a)`` sees
    t = 0 and every accepted step; the arrays are the integrator's own, so copy what is kept.
    """
    import numpy as np
    import scipy.sparse.linalg as spla

    n = K.shape[0]
    u = np.zeros(n) if u0 is None else np.asarray(u0, dtype=float).copy()
    v = np.zeros(n) if v0 is None else np.asarray(v0, dtype=float).copy()
    run = March(how=("superlu" if solver == "direct" else "multigrid CG") + ", Newmark average acceleration")
    # The start's acceleration from the equation itself: M a = f - C v - K u.
    rhs = load(0.0) - K @ u - (C @ v if C is not None else 0.0)
    if solver == "direct":
        a = spla.splu(M.tocsc()).solve(rhs)
    else:
        diagonal = M.diagonal()
        a, info = spla.cg(M, rhs, M=spla.LinearOperator(M.shape, matvec=lambda x: x / diagonal), rtol=1e-12, maxiter=2000)
        if info:
            run.warnings.append("the starting acceleration's solve did not converge; the first steps may be off")
    if on_step:
        on_step(0.0, u, v, a)
    cache: dict[float, _Solver] = {}

    def solver_for(dt: float) -> _Solver:
        key = float(dt)
        if key not in cache:
            if len(cache) >= _CACHE:
                cache.pop(next(iter(cache)))
            A = K + M * (1.0 / (beta * dt * dt))
            if C is not None:
                A = A + C * (gamma / (beta * dt))
            cache[key] = _Solver(A, solver, near_null)
            run.factorisations += 1
        return cache[key]

    watched = None if error_modes is None else (M @ error_modes)

    def size(x) -> float:
        # The size of a motion as the watched modes see it (their modal coordinates), else mass-weighted: a
        # mesh-scale ripple the step cannot resolve anyway must not drive the step down.
        if watched is not None:
            return float(np.linalg.norm(watched.T @ x))
        return math.sqrt(max(float(x @ (M @ x)), 0.0))

    stops = sorted(float(s) for s in stops if 0 < s < end_s)
    t = 0.0
    dt = float(step_s)
    first = dt
    largest = float(largest_step) if largest_step else end_s
    smallest, biggest = math.inf, 0.0
    scale = 0.0
    finish = end_s * (1 - 1e-12)
    while t < finish:
        h = _clamp_to(t, dt, stops, end_s)
        a0 = 1.0 / (beta * h * h)
        a2 = 1.0 / (beta * h)
        a3 = 1.0 / (2.0 * beta) - 1.0
        f = load(t + h)
        rhs = f + M @ (a0 * u + a2 * v + a3 * a)
        if C is not None:
            c1 = gamma / (beta * h)
            c4 = gamma / beta - 1.0
            c5 = h * (gamma / (2.0 * beta) - 1.0)
            rhs = rhs + C @ (c1 * u + c4 * v + c5 * a)
        u_new = solver_for(h)(rhs)
        a_new = a0 * (u_new - u) - a2 * v - a3 * a
        v_new = v + h * ((1.0 - gamma) * a + gamma * a_new)
        if adaptive:
            error = size(newmark_error(h, a, a_new, beta))
            scale = max(scale, size(u_new))
            if scale > 0 and error > tolerance * scale and h > first / 2 ** MAX_HALVINGS:
                dt = h / 2
                run.rejected += 1
                continue
        t += h
        run.steps += 1
        smallest, biggest = min(smallest, h), max(biggest, h)
        u, v, a = u_new, v_new, a_new
        if on_step:
            on_step(t, u, v, a)
        if adaptive:
            if scale == 0 or error < GROW_BELOW * tolerance * scale:
                dt = min(2 * h, largest)
            else:
                dt = h
        if log and run.steps % 200 == 0:
            log(f"time march: {run.steps} steps, t = {t:.4g} s of {end_s:.4g} s")
    run.smallest_step = smallest if run.steps else 0.0
    run.largest_step = biggest
    if solver != "direct":
        iterations = sum(s.iterations for s in cache.values())
        run.how += f" ({iterations} CG iterations)"
    return run


def _coefficients(omega: "np.ndarray", zeta: "np.ndarray", dt: float):
    """The eight Nigam-Jennings coefficients per mode for a step ``dt`` (unit modal mass, 0 ≤ ζ < 1)."""
    import numpy as np

    w = np.asarray(omega, dtype=float)
    z = np.broadcast_to(np.asarray(zeta, dtype=float), w.shape)
    root = np.sqrt(1.0 - z * z)
    wd = w * root
    e = np.exp(-z * w * dt)
    s = np.sin(wd * dt)
    c = np.cos(wd * dt)
    k = w * w
    zr = z / root
    A = e * (zr * s + c)
    B = e * s / wd
    C = (2 * z / (w * dt) + e * (((1 - 2 * z * z) / (wd * dt) - zr) * s - (1 + 2 * z / (w * dt)) * c)) / k
    D = (1 - 2 * z / (w * dt) + e * ((2 * z * z - 1) / (wd * dt) * s + 2 * z / (w * dt) * c)) / k
    A1 = -e * (w / root) * s
    B1 = e * (c - zr * s)
    C1 = (-1 / dt + e * ((w / root + z / (dt * root)) * s + c / dt)) / k
    D1 = (1 - e * (zr * s + c)) / (k * dt)
    return A, B, C, D, A1, B1, C1, D1


def modal_march(omega: "np.ndarray", zeta, times: "np.ndarray", P: "np.ndarray",
                q0: "np.ndarray | None" = None, v0: "np.ndarray | None" = None) -> tuple["np.ndarray", "np.ndarray"]:
    """(Q, V), each (times, modes): every mode's coordinate and velocity at ``times`` (ascending, from 0) under
    modal loads ``P`` (times, modes), exactly for a load linear between the times. ``omega`` rad/s (> 0),
    ``zeta`` one damping ratio (0 ≤ ζ < 1) or one per mode; unit modal mass (mass-normalised modes)."""
    import numpy as np

    times = np.asarray(times, dtype=float)
    P = np.asarray(P, dtype=float)
    m = len(omega)
    Q = np.zeros((len(times), m))
    V = np.zeros((len(times), m))
    Q[0] = 0.0 if q0 is None else q0
    V[0] = 0.0 if v0 is None else v0
    steps = np.diff(times)
    cache: dict[float, tuple] = {}
    for i, dt in enumerate(steps):
        key = round(float(dt), 15)
        if key not in cache:
            cache[key] = _coefficients(omega, zeta, float(dt))
        A, B, C, D, A1, B1, C1, D1 = cache[key]
        Q[i + 1] = A * Q[i] + B * V[i] + C * P[i] + D * P[i + 1]
        V[i + 1] = A1 * Q[i] + B1 * V[i] + C1 * P[i] + D1 * P[i + 1]
    return Q, V


def theta(
    C,
    K,
    load: Callable[[float], "np.ndarray"],
    end_s: float,
    step_s: float,
    *,
    u0: "np.ndarray | None" = None,
    theta: float = 1.0,
    adaptive: bool = False,
    tolerance: float = THETA_TOLERANCE,
    largest_step: float | None = None,
    solver: str = "direct",
    on_step: Callable[[float, "np.ndarray"], None] | None = None,
) -> March:
    """C u̇ + K u = load(t) from ``u0`` by the θ method: (C/Δt + θK) uₙ₊₁ = (C/Δt − (1−θ)K) uₙ + θfₙ₊₁ + (1−θ)fₙ.

    ``adaptive`` takes each step whole and as two halves; a step whose two answers differ by more than
    ``tolerance`` of the state's range is taken again at half the size, one well under it lets the next
    double (never past ``largest_step``, default a tenth of the run). ``on_step(t, u)`` sees t = 0 and
    every accepted step (the array is the integrator's own).
    """
    import numpy as np

    n = K.shape[0]
    u = np.zeros(n) if u0 is None else np.asarray(u0, dtype=float).copy()
    run = March(how=("superlu" if solver == "direct" else "multigrid CG") + f", θ = {theta:g}")
    cache: dict[float, _Solver] = {}

    def solve(dt: float, rhs):
        key = float(dt)
        if key not in cache:
            if len(cache) >= _CACHE:
                cache.pop(next(iter(cache)))
            cache[key] = _Solver(C * (1.0 / dt) + K * theta, solver)
            run.factorisations += 1
        return cache[key](rhs)

    def step(state, t: float, dt: float):
        rhs = C @ state * (1.0 / dt) - (1.0 - theta) * (K @ state) + theta * load(t + dt)
        if theta < 1.0:
            rhs = rhs + (1.0 - theta) * load(t)
        return solve(dt, rhs)

    if on_step:
        on_step(0.0, u)
    t, dt = 0.0, float(step_s)
    first = dt
    largest = float(largest_step) if largest_step else end_s / 10.0
    smallest, biggest = math.inf, 0.0
    # The state's size the step error is judged against: its range, or its largest value for a single number.
    scale = max(float(np.ptp(u)) if n else 0.0, float(np.abs(u).max()) if n else 0.0, 1e-300)
    finish = end_s * (1 - 1e-12)
    while t < finish:
        h = min(dt, end_s - t)
        if adaptive:
            whole = step(u, t, h)
            half = step(u, t, h / 2)
            two = step(half, t + h / 2, h / 2)
            error = float(np.abs(two - whole).max())
            scale = max(scale, float(np.ptp(two)), float(np.abs(two).max()))
            if error > tolerance * scale and h > first / 2 ** MAX_HALVINGS:
                dt = h / 2
                run.rejected += 1
                continue
            # Local Richardson extrapolation for backward Euler; the halves themselves for a second-order θ.
            u_new = 2.0 * two - whole if theta == 1.0 else two
        else:
            u_new = step(u, t, h)
        t += h
        run.steps += 1
        smallest, biggest = min(smallest, h), max(biggest, h)
        u = u_new
        if on_step:
            on_step(t, u)
        if adaptive and error < GROW_BELOW * tolerance * scale:
            dt = min(2 * h, largest)
    run.smallest_step = smallest if run.steps else 0.0
    run.largest_step = biggest
    return run
