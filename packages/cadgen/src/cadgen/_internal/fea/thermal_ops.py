"""Heat on a :class:`~cadgen._internal.fea.femspace.FemSpace`: the boundary terms, the steady solve and the time march.

The conduction matrix and the heat capacity come from :mod:`operators`; this
module adds what a thermal study puts on the faces and solves it:

- faces held at a temperature (fixed DOF, set and condensed out);
- heat in, as a total power spread evenly over its faces or as a flux;
- convection, a film ``h (T - T_inf)`` on its faces;
- radiation (:mod:`.radiation`), to the surroundings and between faces: a
  nonlinear term in T⁴, so a system with any is solved by Newton's method.

Units are the engine's: mm, s, temperature in °C (only differences matter),
power in mW, conductivity in mW/(mm K) (numerically W/(m K)), h and flux in
mW/mm² (the study's W/(m² K) and W/m² divided by 1000).

:func:`solve_steady` solves K T = f with the fixed temperatures condensed out
(direct for small systems, multigrid CG otherwise, or as the plan says).
:func:`march` steps C dT/dt + K T = f(t) by backward Euler, with each entry's
schedule (a piecewise-linear factor against time); ``adaptive`` lets the step
grow and shrink by step doubling. :func:`heat_balance` is the heat that goes
in and out through each entry, and :func:`heat_flux` the conducted flux's
magnitude at the nodes. Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.materials import Material

__all__ = [
    "ADAPTIVE_TOLERANCE", "Fixed", "Film", "Heat", "March", "ThermalSystem", "assemble", "factor_at",
    "heat_balance", "heat_flux", "march", "solve_steady",
]

#: Step doubling's tolerance on a step's temperature error, as a share of the temperature range.
ADAPTIVE_TOLERANCE = 0.002
#: A study's W/(m² K) and W/m² in the engine's mW/mm².
PER_M2 = 1e-3
#: A study's W in the engine's mW.
WATT = 1e3


def factor_at(history: Sequence[Sequence[float]] | None, t: float) -> float:
    """A piecewise-linear schedule's factor at time ``t``: 1 with none; flat before its first point and after its last."""
    if not history:
        return 1.0
    if t <= history[0][0]:
        return float(history[0][1])
    for (t0, f0), (t1, f1) in zip(history, history[1:]):
        if t <= t1:
            return float(f0 + (f1 - f0) * (t - t0) / (t1 - t0))
    return float(history[-1][1])


@dataclass
class Fixed:
    """Faces held at a temperature: their scalar DOF and the temperature (°C) at factor 1."""

    dofs: "np.ndarray"
    celsius: float
    history: tuple = ()


@dataclass
class Heat:
    """Heat into faces: its load vector (mW per DOF) at factor 1, and the power that is (W)."""

    load: "np.ndarray"
    watts: float
    history: tuple = ()


@dataclass
class Film:
    """Convection on faces: the film matrix ∫ h T v, its load ∫ h T_inf v at factor 1, and the ambient (°C)."""

    matrix: Any
    load: "np.ndarray"
    ambient: float
    history: tuple = ()


@dataclass
class ThermalSystem:
    """What a thermal study assembles to: conduction plus every film, and each boundary entry on its own."""

    space: "FemSpace"
    conduction: Any
    fixed: list[Fixed] = field(default_factory=list)
    heat: list[Heat] = field(default_factory=list)
    films: list[Film] = field(default_factory=list)
    #: The study's radiation (:class:`cadgen._internal.fea.radiation.Radiation`), or None: none makes it linear.
    radiation: Any = None

    @property
    def size(self) -> int:
        return int(self.space.scalar.N)

    @property
    def stiffness(self):
        """K = conduction + every film."""
        K = self.conduction
        for film in self.films:
            K = K + film.matrix
        return K.tocsr()

    def load(self, t: float | None = None) -> "np.ndarray":
        """f at time ``t`` (each entry's schedule applied), or at factor 1 when ``t`` is None."""
        import numpy as np

        f = np.zeros(self.size)
        for entry in (*self.heat, *self.films):
            f += entry.load * (1.0 if t is None else factor_at(entry.history, t))
        return f

    def fixed_values(self, t: float | None = None) -> tuple["np.ndarray", "np.ndarray"]:
        """The fixed DOF and their temperatures at ``t``; a DOF on two entries' faces keeps the first's."""
        import numpy as np

        dofs: list = []
        values: list = []
        seen = np.zeros(self.size, dtype=bool)
        for entry in self.fixed:
            new = entry.dofs[~seen[entry.dofs]]
            seen[new] = True
            dofs.append(new)
            values.append(np.full(len(new), entry.celsius * (1.0 if t is None else factor_at(entry.history, t))))
        if not dofs:
            return np.zeros(0, dtype=np.int64), np.zeros(0)
        return np.concatenate(dofs).astype(np.int64), np.concatenate(values)


def _materials(materials) -> list:
    return list(materials) if isinstance(materials, (list, tuple)) else [materials]


def assemble(
    space: "FemSpace",
    materials: "Material | Sequence[Material]",
    *,
    fixed: Sequence[tuple["np.ndarray", float, tuple]] = (),
    heat: Sequence[tuple["np.ndarray", float | None, float | None, tuple]] = (),
    films: Sequence[tuple["np.ndarray", float, float, tuple]] = (),
    radiation: Sequence[tuple["np.ndarray", float, float, bool]] = (),
    log: Callable[[str], None] | None = None,
) -> ThermalSystem:
    """The thermal system of a study on ``space``, each entry by its skfem facets.

    ``fixed``: (facets, °C, history). ``heat``: (facets, W or None, W/m² or None,
    history), a power spread evenly over the faces' area or a flux. ``films``:
    (facets, h in W/(m² K), ambient °C, history). ``radiation``: (boundary rows,
    emissivity, ambient °C, whether it exchanges with the other such faces).
    """
    import numpy as np
    from skfem import LinearForm, asm

    from cadgen._internal.fea import operators

    system = ThermalSystem(space=space, conduction=operators.conduction(space, materials))
    for facets, celsius, history in fixed:
        system.fixed.append(Fixed(np.asarray(space.scalar.get_dofs(facets).all(), dtype=np.int64), float(celsius), tuple(history)))
    for facets, watts, per_m2, history in heat:
        boundary = space.scalar.boundary(facets)
        area = float(boundary.dx.sum())
        flux = watts * WATT / area if watts is not None else per_m2 * PER_M2

        @LinearForm
        def into(v, w, flux=flux):
            return flux * v

        load = asm(into, boundary)
        system.heat.append(Heat(load, float(load.sum()) / WATT, tuple(history)))
    for facets, h, ambient, history in films:
        matrix, load = operators.convection(space, facets, h * PER_M2, ambient)
        system.films.append(Film(matrix, load, float(ambient), tuple(history)))
    if radiation:
        from cadgen._internal.fea import radiation as radiating

        system.radiation = radiating.assemble(
            space, [rows for rows, _, _, _ in radiation], [e for _, e, _, _ in radiation],
            [ambient for _, _, ambient, _ in radiation], [bool(flag) for _, _, _, flag in radiation], log=log,
        )
    return system


def _method(solver: str | None) -> str | None:
    """The plan's solver as :func:`operators.solve_spd`'s method: an iterative plan forces multigrid; else by size."""
    return "iterative" if solver in ("iterative", "matrix_free") else None


def solve_steady(system: ThermalSystem, warnings: list[str], *, solver: str | None = None) -> tuple["np.ndarray", str]:
    """The steady temperature (°C at every scalar DOF) and how it was solved."""
    import numpy as np

    from cadgen._internal.fea import operators

    K = system.stiffness
    f = system.load()
    x = np.zeros(system.size)
    dofs, values = system.fixed_values()
    x[dofs] = values
    free = np.setdiff1d(np.arange(system.size), dofs)
    if system.radiation is not None:
        return _solve_radiating(system, K, f, x, free, warnings, solver)
    x[free], how = operators.solve_spd(K, f - K @ x, free, None, None, warnings, method=_method(solver))
    return x, how


def _solve_radiating(system: ThermalSystem, K, f, x, free, warnings: list[str], solver: str | None):
    """The steady temperature with radiation: Newton on the T⁴ from the warmest ambient the study sets."""
    from cadgen._internal.fea import radiation

    start = max([*system.radiation.ambients, *(film.ambient for film in system.films), *(e.celsius for e in system.fixed)])
    x[free] = start
    x, iterations = radiation.newton_solve(K, f, x, free, system.radiation, warnings, method=_method(solver))
    exchange = system.radiation.enclosure is not None
    how = ("superlu, bordered by the radiation patches" if exchange else
           "multigrid CG" if _method(solver) or len(free) >= _direct_below() else "superlu")
    return x, f"{how}, Newton ({iterations} iterations) on the radiation"


def heat_balance(system: ThermalSystem, T: "np.ndarray", t: float | None = None) -> dict:
    """The heat (W) that goes in through each entry at the solved ``T``: positive in, negative out.

    Heat put in is its power. A film carries ∫ h (T - T_inf) out. A face held
    at a temperature passes what the conduction there needs: the residual of
    K T = f on its DOF (a DOF on several held faces counts once, for the first).
    ``in_W`` and ``out_W`` total them; ``imbalance`` is their mismatch as a share
    of the larger (zero but for the solver's tolerance, and zero when under a
    microwatt flows at all).
    """
    import numpy as np

    K = system.stiffness
    residual = K @ T - system.load(t)
    if system.radiation is not None:
        residual = residual + system.radiation.residual(T)
    fixed = []
    seen = np.zeros(system.size, dtype=bool)
    for entry in system.fixed:
        new = entry.dofs[~seen[entry.dofs]]
        seen[new] = True
        fixed.append(float(residual[new].sum()) / WATT)
    heat = [entry.watts * (1.0 if t is None else factor_at(entry.history, t)) for entry in system.heat]
    films = [
        -float((film.matrix @ T - film.load * (1.0 if t is None else factor_at(film.history, t))).sum()) / WATT
        for film in system.films
    ]
    radiated = [-power for power in system.radiation.powers(T)] if system.radiation is not None else []
    flows = [*fixed, *heat, *films, *radiated]
    heat_in = sum(flow for flow in flows if flow > 0)
    heat_out = -sum(flow for flow in flows if flow < 0)
    larger = max(heat_in, heat_out)
    balance = {
        "fixed_W": fixed, "heat_W": heat, "films_W": films, "in_W": heat_in, "out_W": heat_out,
        # Under a microwatt nothing flows: what is left is the solver's rounding, not heat.
        "imbalance": abs(heat_in - heat_out) / larger if larger > 1e-6 else 0.0,
    }
    if system.radiation is not None:
        balance["radiation_W"] = radiated
    return balance


def heat_flux(space: "FemSpace", materials: "Material | Sequence[Material]", T: "np.ndarray") -> "np.ndarray":
    """|k ∇T| projected to the nodes, in W/m² (the engine's mW/mm² times 1000)."""
    import numpy as np

    from cadgen._internal.fea import operators

    k = operators.domain_values(space, [m.conductivity for m in _materials(materials)], space.scalar)
    grad = space.scalar.interpolate(T).grad                          # (3, elements, quadrature)
    magnitude = np.sqrt((grad ** 2).sum(axis=0)) * k
    return np.maximum(space.scalar.project(magnitude), 0.0) * 1e3


# -- the time march ----------------------------------------------------------------------------------


class _Stepper:
    """Backward Euler steps (C + dt K) T1 = C T0 + dt f(t1), the fixed DOF set at t1; one factorisation per step size."""

    def __init__(self, system: ThermalSystem, capacity, warnings: list[str], solver: str | None):
        import numpy as np

        self.system = system
        self.C = capacity.tocsr()
        self.K = system.stiffness
        self.warnings = warnings
        self.iterative = solver in ("iterative", "matrix_free") or (solver is None and system.size >= _direct_below())
        dofs, _ = system.fixed_values()
        self.fixed = dofs
        self.free = np.setdiff1d(np.arange(system.size), dofs)
        self._cache: dict[float, Any] = {}
        self.solves = 0

    def _solver(self, dt: float):
        key = float(dt)
        if key not in self._cache:
            import scipy.sparse.linalg as spla

            A = (self.C + dt * self.K).tocsr()
            Aff = A[self.free][:, self.free].tocsr()
            if self.iterative:
                import pyamg

                ml = pyamg.smoothed_aggregation_solver(Aff, symmetry="symmetric", strength="symmetric", smooth="energy", max_coarse=500)
                solve = (lambda rhs, x0, ml=ml: ml.solve(rhs, x0=x0, tol=1e-10, accel="cg", maxiter=400))
            else:
                lu = spla.splu(Aff.tocsc())
                solve = (lambda rhs, x0, lu=lu: lu.solve(rhs))
            self._cache = {k: v for k, v in list(self._cache.items())[-3:]}  # a few step sizes at a time
            self._cache[key] = (A, solve)
        return self._cache[key]

    def step(self, T: "np.ndarray", t: float, dt: float) -> "np.ndarray":
        import numpy as np

        A, solve = self._solver(dt)
        t1 = t + dt
        _, values = self.system.fixed_values(t1)
        x = np.zeros_like(T)
        x[self.fixed] = values
        rhs = self.C @ T + dt * self.system.load(t1) - A @ x
        x[self.free] = solve(rhs[self.free], T[self.free])
        self.solves += 1
        return x


class _RadiatingStepper(_Stepper):
    """Backward Euler with radiation: each step's C (T1 - T0) + dt (K T1 - f(t1) + R(T1)) = 0 by Newton on the T⁴."""

    def __init__(self, system: ThermalSystem, capacity, warnings: list[str], solver: str | None):
        super().__init__(system, capacity, warnings, solver)
        self.newton = 0

    def step(self, T: "np.ndarray", t: float, dt: float) -> "np.ndarray":
        import numpy as np

        from cadgen._internal.fea import radiation

        t1 = t + dt
        _, values = self.system.fixed_values(t1)
        x = T.copy()
        x[self.fixed] = values
        base = (self.C + dt * self.K).tocsr()
        load = self.C @ T + dt * self.system.load(t1)
        method = "iterative" if self.iterative else None
        x, iterations = radiation.newton_solve(base, load, x, self.free, self.system.radiation, self.warnings,
                                               scale=dt, method=method)
        self.solves += iterations
        self.newton += iterations
        return x


def _direct_below() -> int:
    from cadgen._internal.fea.operators import DIRECT_SOLVE_BELOW

    return DIRECT_SOLVE_BELOW


@dataclass
class March:
    """What a time march kept: the frames, the hottest step, each node's own peak, the max-temperature curve."""

    #: (time s, temperatures) at the frames asked for, the hottest step among them, in time order.
    frames: list[tuple[float, "np.ndarray"]]
    #: The frame that is the hottest step.
    hottest_frame: int
    hottest_time: float
    hottest: float
    #: Each node's highest temperature over all time, and when it was reached.
    node_peak: "np.ndarray"
    node_peak_time: "np.ndarray"
    #: Every accepted step's time and highest temperature (thinned to at most ``curve_points``), t = 0 first.
    curve_t: list[float]
    curve_max: list[float]
    steps: int
    solves: int
    smallest_step: float
    largest_step: float
    final: "np.ndarray"
    rejected: int = 0


def march(
    system: ThermalSystem,
    capacity,
    initial_C: float,
    end_s: float,
    step_s: float,
    warnings: list[str],
    *,
    frames: int = 24,
    adaptive: bool = False,
    solver: str | None = None,
    curve_points: int = 400,
    tolerance: float = ADAPTIVE_TOLERANCE,
    log: Callable[[str], None] | None = None,
) -> March:
    """C dT/dt + K T = f(t) from ``initial_C`` to ``end_s`` by backward Euler, steps of ``step_s``.

    ``adaptive`` controls the step by step doubling: each step is taken whole
    and as two halves, and the two combined (2 x halves - whole, which cancels
    backward Euler's first-order error); a step whose two answers differ by more
    than ``tolerance`` of the temperature range is retried at half the size, and
    one well under it lets the next step double (never past a tenth of the run).
    The state is kept at ``frames - 1`` evenly spaced times from 0 (the first
    step at or past each), plus the hottest step.
    """
    import numpy as np

    stepper = (_RadiatingStepper if system.radiation is not None else _Stepper)(system, capacity, warnings, solver)
    T = np.full(system.size, float(initial_C))
    dofs, values = system.fixed_values(0.0)
    T[dofs] = values
    even = max(frames - 1, 1)
    targets = [end_s * i / (even - 1) for i in range(even)] if even > 1 else [0.0]
    kept: list[tuple[float, np.ndarray]] = [(0.0, T.copy())]
    next_target = 1
    hottest = float(T.max())
    hottest_time, hottest_state = 0.0, T.copy()
    node_peak, node_peak_time = T.copy(), np.zeros(system.size)
    curve_t, curve_max = [0.0], [hottest]
    t, steps, rejected = 0.0, 0, 0
    dt = float(step_s)
    smallest, largest = math.inf, 0.0
    largest_step = end_s / 10.0
    # The temperature range the step error is judged against: the spread the study sets, at least one degree.
    span = [float(initial_C)] + [entry.celsius for entry in system.fixed] + [film.ambient for film in system.films]
    if system.radiation is not None:
        span += system.radiation.ambients
    scale = max(1.0, max(span) - min(span))
    finish = end_s * (1 - 1e-12)
    while t < finish:
        dt = min(dt, end_s - t)
        if adaptive:
            whole = stepper.step(T, t, dt)
            half = stepper.step(T, t, dt / 2)
            two = stepper.step(half, t + dt / 2, dt / 2)
            error = float(np.abs(two - whole).max())
            scale = max(scale, float(two.max() - two.min()))
            if error > tolerance * scale and dt > end_s * 1e-9:
                dt /= 2
                rejected += 1
                continue
            # The two halves and the whole step together cancel backward Euler's first-order error
            # (local Richardson extrapolation): still L-stable, and exactly as conservative.
            T_next = 2.0 * two - whole
        else:
            T_next = stepper.step(T, t, dt)
        t += dt
        steps += 1
        smallest, largest = min(smallest, dt), max(largest, dt)
        T = T_next
        peak = float(T.max())
        curve_t.append(t)
        curve_max.append(peak)
        higher = T > node_peak
        node_peak[higher] = T[higher]
        node_peak_time[higher] = t
        if peak > hottest:
            hottest, hottest_time, hottest_state = peak, t, T.copy()
        while next_target < len(targets) and t >= targets[next_target] * (1 - 1e-9):
            if not kept or kept[-1][0] != t:
                kept.append((t, T.copy()))
            next_target += 1
        if adaptive and error < tolerance * scale / 8:
            dt = min(2 * dt, largest_step)
        if log and steps % 100 == 0:
            log(f"time march: {steps} steps, t = {t:.4g} s of {end_s:.4g} s")
    if all(time != hottest_time for time, _ in kept):
        kept.append((hottest_time, hottest_state))
        kept.sort(key=lambda frame: frame[0])
    hottest_frame = next(i for i, (time, _) in enumerate(kept) if time == hottest_time)
    if len(curve_t) > curve_points:
        stride = math.ceil(len(curve_t) / curve_points)
        keep = sorted({0, len(curve_t) - 1, int(np.argmax(curve_max)), *range(0, len(curve_t), stride)})
        curve_t, curve_max = [curve_t[i] for i in keep], [curve_max[i] for i in keep]
    return March(
        frames=kept, hottest_frame=hottest_frame, hottest_time=hottest_time, hottest=hottest, node_peak=node_peak,
        node_peak_time=node_peak_time, curve_t=curve_t, curve_max=curve_max, steps=steps, solves=stepper.solves,
        smallest_step=smallest if steps else 0.0, largest_step=largest, final=T, rejected=rejected,
    )
