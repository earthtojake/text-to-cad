"""Creep (lite): the slow, permanent stretch of a part under a load held for a long time, usually hot.

The study (spec 2.1) takes static's ``fixtures`` and ``loads``, held constant
for ``duration_h`` hours, ``steps`` (the time steps it starts with, 20) and an
optional ``temperature_C`` (a note: the creep data must be for the temperature
the part runs at; a material whose creep block says another one is warned
about). The material gives its creep law:

    "creep": {"A": 1e-20, "n": 5, "m": 0, "units": "MPa, hours"}

the Norton power law (with optional time hardening), creep strain rate
A σ^n t^m, σ the von Mises stress in MPa and t in hours (or seconds). A study
whose materials have no creep block is refused with a sentence asking for one;
in an assembly a part without one stays elastic.

The load goes on at once (the elastic answer at 0 h), then the creep strain
grows at every quadrature point by backward Euler with the consistent tangent
(:mod:`..creep_law`), Newton's method on the whole part each time step
(:mod:`..nonlinear_driver`). Each step's local error (backward against forward
Euler, as a share of the stress) is kept under :data:`TOLERANCE` by cutting the
step; with the ladder's ``adaptive_steps`` the steps also grow past the
starting size where the creep is steady. Where the stress is held by a fixed
stretch rather than a load, it relaxes, and the results show it: the stress
frames fall, the summary gives the peak at the start and at the end, and the
stress curve against time is written.

What it writes: a series of time frames (``kind: "time"``, unit ``h``, at most
``Budget.max_frames``, spread evenly in time from 0 h, the last the default),
each with the von Mises stress, the displacement and the equivalent creep
strain in percent. Checks: ``creep_strain`` (``limit_percent``; by default 1 %),
``stress`` (its largest peak over the time, against yield) and ``displacement``
(at the end). Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.nonlinear import NonlinearAnalysis, _external, _material_specs, _Outcome
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs

if TYPE_CHECKING:
    import numpy as np

__all__ = ["CreepAnalysis", "CreepInputs", "DEFAULT_CREEP_LIMIT", "DEFAULT_STEPS", "LIMITS", "TOLERANCE", "hours_label"]

#: Time steps a study starts with when it names none.
DEFAULT_STEPS = 20
#: The most starting steps a study may ask for.
MAX_STEPS = 1000
#: A time step whose local error passes this share of the stress is cut in half and taken again.
TOLERANCE = 2e-3
#: Points under this share of the peak stress do not drive the step size (their relative error means little).
ERROR_FLOOR = 0.05
#: A step is halved at most this many times below the starting step.
MAX_HALVINGS = 16
#: With adaptive steps, a step grows to at most this many times the starting one.
MAX_GROWTH = 64
#: The creep strain a creep_strain check allows when the study names no check, in percent.
DEFAULT_CREEP_LIMIT = 1.0
#: Newton iterations a time step takes on average, and steps taken per starting step (cuts included).
NEWTON_PER_STEP, STEPS_PER_STEP = 3.0, 1.5
#: Quadrature points per quadratic tet, for the state's memory.
POINTS_PER_TET = 11
MAX_FRAMES = 24

#: What this lite solver leaves out, written into its output, its verdict's Details and the skill.
LIMITS = (
    "Creep is Norton's power law (steady, secondary creep, with optional time hardening): no tertiary creep, "
    "no rupture and no damage, so a part near the end of its creep life reads safer than it is",
    "The creep data hold at one temperature: the part is taken to be at that temperature throughout",
    "Isotropic, small strain: creep keeps the volume and follows the von Mises stress; rotations stay small",
    "Loads and fixtures are held constant for the whole time; nothing is unloaded or cycled",
)


def _figure(value: float) -> str:
    text = f"{value:.3g}"
    return text if "e" not in text else f"{value:.0f}"


def hours_label(hours: float) -> str:
    """A time as the scrubber says it: "0 h", "2.5 h", "250 h", "10,000 h"."""
    if hours >= 1000.0:
        return f"{hours:,.0f} h"
    if hours >= 10.0:
        return f"{hours:.0f} h"
    return f"{_figure(hours)} h"


@dataclass(frozen=True)
class CreepInputs(StaticInputs):
    duration_h: float = 1.0
    steps: int = DEFAULT_STEPS
    temperature_C: float | None = None


def _creep_materials(document: dict) -> list[tuple[str, Any]]:
    from cadgen._internal.fea.materials import material_from_spec

    return [(where, material_from_spec(spec)) for where, spec in _material_specs(document)]


def _require_creep(document: dict) -> list:
    materials = _creep_materials(document)
    if not any(material.creep for _, material in materials):
        name = materials[0][1].name if materials else "steel"
        raise ValueError(
            "material.creep: a creep study needs the material's creep law, the Norton constants A and n from the "
            f'grade\'s creep data at the temperature it runs at, like {{"name": "{name}", "creep": {{"A": 1e-20, "n": 5, '
            '"m": 0, "units": "MPa, hours"}}}} (creep strain rate = A σ^n, σ in MPa); cadgen has no creep table of its own'
        )
    return materials


def _duration(document: dict) -> float:
    if "duration_h" not in document:
        raise ValueError("duration_h: how long the load is held, in hours, like 10000")
    return kinds.number(document["duration_h"], where="duration_h", positive=True)


def _steps(document: dict) -> int:
    raw = document.get("steps", DEFAULT_STEPS)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= MAX_STEPS:
        raise ValueError(f"steps: the number of time steps to start with, a whole number from 1 to {MAX_STEPS}, "
                         f"got {kinds.json_text(raw)}")
    return raw


# -- the problem the driver solves -----------------------------------------------------------------------


class _CreepProblem:
    """The part over one time step: the free DOF, the constant load, the committed creep state."""

    def __init__(self, space, free, external, params):
        from cadgen._internal.fea.creep_law import CreepState
        from cadgen._internal.fea.plasticity import ElementOps

        self.space = space
        self.ops = ElementOps(space.basis)
        self.size = int(space.basis.N)
        self.free = free
        self.external = external
        self.locations = space.locations
        self.component = space.component
        self.params = params
        self.state = CreepState.zeros(tuple(self.ops.dx.shape))
        self.t0 = self.t1 = 0.0

    def step(self, t0: float, t1: float) -> None:
        self.t0, self.t1 = t0, t1

    def update(self, u, tangent):
        from cadgen._internal.fea.creep_law import norton_update
        from cadgen._internal.fea.plasticity import mean_dilatation_strain

        return norton_update(mean_dilatation_strain(self.ops.gradient(u), self.ops), self.state, self.params, self.t0, self.t1,
                             tangent=tangent)

    def evaluate(self, u, *, tangent):
        import numpy as np

        update = self.update(u, tangent)
        if not tangent:
            return self.ops.force(update.stress), None
        # Mean dilatation, as J2: the deviatoric tangent at the points, the bulk modulus on each element's mean volume change.
        C = update.tangent
        bulk = np.broadcast_to(np.asarray(self.params.bulk, dtype=float), self.ops.dx.shape)
        for i in range(3):
            for k in range(3):
                C[i, i, k, k] -= bulk
        K = self.ops.matrix(C) + self.ops.volumetric_matrix(bulk[:, 0])
        return self.ops.force(update.stress), K

    def error(self, update) -> float:
        """The step's local error: the largest over the points that carry at least ERROR_FLOOR of the peak stress."""
        import numpy as np

        stress = np.maximum(update.state.von_mises, self.state.von_mises)
        peak = float(stress.max())
        if peak <= 0:
            return 0.0
        return float(update.error[stress >= ERROR_FLOOR * peak].max())

    def commit(self, update) -> None:
        self.state = update.state


def _newton(problem: _CreepProblem, linear, u0: "np.ndarray", max_iterations: int, tolerance: float):
    """Newton's method on f_int(u) = f_ext over the free DOF from ``u0`` (its held DOF kept): (u or None, iterations).

    Converged when the free residual is ``tolerance`` of the force scale: the larger of the load and the internal
    force over every DOF (reactions included, so a part held at a fixed stretch with no load has a scale too). A
    correction that raises the residual is halved, up to six times."""
    import numpy as np

    free = problem.free
    u = u0.copy()
    linear.new_step()
    applied = float(np.linalg.norm(problem.external))
    for iteration in range(max_iterations + 1):
        internal, K = problem.evaluate(u, tangent=True)
        if not np.all(np.isfinite(internal)):
            return None, iteration
        r = problem.external[free] - internal[free]
        norm = float(np.linalg.norm(r))
        if norm <= tolerance * max(applied, float(np.linalg.norm(internal)), 1e-300):
            return u, iteration
        if iteration == max_iterations:
            break
        du = linear.solve(K[free][:, free].tocsr(), r)
        if du is None or not np.all(np.isfinite(du)):
            return None, iteration
        alpha = 1.0
        for _ in range(7):
            trial = u.copy()
            trial[free] += alpha * du
            internal_trial, _ = problem.evaluate(trial, tangent=False)
            if np.all(np.isfinite(internal_trial)) and np.linalg.norm(problem.external[free] - internal_trial[free]) < norm:
                break
            alpha *= 0.5
        u = trial
    return None, max_iterations


@dataclass
class _Path:
    """What the time march did."""

    times: list[float]
    seconds: float
    steps: int
    rejected: int
    cuts: int
    iterations: int
    smallest_step: float
    largest_step: float
    stopped: bool
    how: str


def _march(problem: _CreepProblem, duration: float, steps: int, *, solver: str, adaptive: bool, keep: int,
           log: Callable[[str], None] | None, u0: "np.ndarray | None" = None):
    """The elastic answer at 0 h, then backward Euler time steps to ``duration``. Returns the path, the frames kept
    (t, u, von Mises at the points, creep strain at the points), and each accepted step's curve point.

    ``u0``: a starting displacement whose held DOF keep their values (a stretch held fixed); zeros by default."""
    import time

    import numpy as np

    from cadgen._internal.fea import nonlinear_driver

    started = time.perf_counter()
    linear = nonlinear_driver._Linear(problem, "iterative" if solver in ("iterative", "matrix_free") else "direct")
    max_iterations, tolerance = nonlinear_driver.MAX_ITERATIONS, nonlinear_driver.TOLERANCE

    def solve(u, t0, t1):
        problem.step(t0, t1)
        return _newton(problem, linear, u, max_iterations, tolerance)

    u = np.zeros(problem.size) if u0 is None else np.array(u0, dtype=float)
    u, iterations = solve(u, 0.0, 0.0)
    if u is None:  # an elastic part Newton cannot hold: a singular tangent
        raise ValueError("the part is not held: the fixtures leave it free to move; fix at least one face")
    update = problem.update(u, False)
    problem.commit(update)
    targets = [duration * k / max(keep - 1, 1) for k in range(1, max(keep, 2))]
    frames = [(0.0, u.copy(), update.state.von_mises.copy(), update.state.equivalent.copy())]
    curve = [(0.0, None, float(update.state.von_mises.max()), 0.0)]
    base = duration / steps
    smallest_allowed = base / 2 ** MAX_HALVINGS
    dt, t = base, 0.0
    accepted = rejected = cuts = 0
    smallest, largest = math.inf, 0.0
    stopped = False
    next_target = 0
    while duration - t > 1e-9 * duration:
        dt = min(dt, duration - t)
        if duration - (t + dt) < 1e-6 * dt:  # do not leave a sliver at the end
            dt = duration - t
        found, taken = solve(u, t, t + dt)
        iterations += taken
        if found is None:
            if dt <= smallest_allowed * (1.0 + 1e-9):
                stopped = True
                break
            dt = max(dt / 2.0, smallest_allowed)
            cuts += 1
            if log:
                log(f"time step to {t + dt * 2:.4g} h did not converge; cutting it to {dt:.4g} h")
            continue
        update = problem.update(found, False)
        error = problem.error(update)
        if error > TOLERANCE and dt > smallest_allowed * (1.0 + 1e-9):
            dt = max(dt / 2.0, smallest_allowed)
            rejected += 1
            continue
        problem.commit(update)
        u = found
        t = t + dt
        accepted += 1
        smallest, largest = min(smallest, dt), max(largest, dt)
        curve.append((t, None, float(update.state.von_mises.max()), float(update.state.equivalent.max())))
        if next_target < len(targets) and t >= targets[next_target] * (1.0 - 1e-9):
            frames.append((t, u.copy(), update.state.von_mises.copy(), update.state.equivalent.copy()))
            while next_target < len(targets) and t >= targets[next_target] * (1.0 - 1e-9):
                next_target += 1
        if log:
            log(f"{hours_label(t)} in {taken} Newton iterations (step {dt:.4g} h, error {error:.2g})")
        grow = 2.0 if error <= 0 else min(2.0, max(1.0, 0.9 * math.sqrt(TOLERANCE / error)))
        dt = dt * grow
        dt = min(dt, MAX_GROWTH * base) if adaptive else min(dt, base)
    problem.step(t, t)  # what is evaluated after the march is the committed state, with no more time to creep
    if frames[-1][0] < t:  # a march that stopped early: its last converged state is the last frame
        frames.append((t, u.copy(), problem.state.von_mises.copy(), problem.state.equivalent.copy()))
    path = _Path(times=[c[0] for c in curve], seconds=time.perf_counter() - started, steps=accepted, rejected=rejected,
                 cuts=cuts, iterations=iterations, smallest_step=0.0 if smallest is math.inf else smallest,
                 largest_step=largest, stopped=stopped, how=linear.how)
    return path, frames, curve


class CreepAnalysis(NonlinearAnalysis):
    name: ClassVar[str] = "creep"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Creep"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "duration_h", "steps", "temperature_C"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("creep_strain", "_CREEP_STRAIN", "creep strain", "%", per_frame=True),
    )
    checks: ClassVar[tuple] = (kinds.CREEP_STRAIN, kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "creep_strain", "limit_percent": DEFAULT_CREEP_LIMIT},)
    # No load_scale: creep is not proportional to the load (σ^n), so a load multiple says nothing.
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "creep_strain"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "adaptive_steps", "local_refine", "defeature", "symmetry")
    noun: ClassVar[str] = "this load"
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> CreepInputs:
        static = StaticAnalysis().parse(document)
        materials = _require_creep(document)
        duration = _duration(document)
        steps = _steps(document)
        temperature = None
        if "temperature_C" in document:
            temperature = kinds.number(document["temperature_C"], where="temperature_C")
        view = document.get("view")
        checks = view.get("checks") if isinstance(view, dict) else None
        if isinstance(checks, list):
            yieldless = any(material.yield_strength is None for _, material in materials)
            for index, check in enumerate(checks):
                if isinstance(check, dict) and check.get("kind") == "stress" and yieldless:
                    raise ValueError(f"view.checks[{index}]: a stress check compares the peak with a yield strength; give "
                                     "the material's yield_MPa, or check its creep strain")
        return CreepInputs(
            static.face_refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
            material_needs=static.material_needs, duration_h=duration, steps=steps, temperature_C=temperature,
        )

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def _load_steps(self, ctx: SolveContext, inputs: CreepInputs) -> float:
        """Time steps the plan expects: the starting count with its cuts, fewer where adaptive steps let them grow."""
        steps = float(inputs.steps) * STEPS_PER_STEP
        if getattr(ctx.plan, "adaptive_steps", False):
            steps = max(4.0, steps / 2.0)
        return steps

    def estimate(self, ctx: SolveContext, inputs: CreepInputs):
        """As nonlinear's (a Newton solve per step on the tangent), with creep's steps and Newton iterations a step."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses import nonlinear

        cost = super().estimate(ctx, inputs)
        scale = NEWTON_PER_STEP / nonlinear.NEWTON_PER_STEP
        return fit.Estimate(dofs=cost.dofs, memory_bytes=cost.memory_bytes, seconds=float(cost.seconds * scale))

    def apply(self, rung, ctx: SolveContext, inputs: CreepInputs):
        from cadgen._internal.fea import fit

        if rung == "iterative":
            return self._apply_iterative(ctx, inputs)
        if rung == "adaptive_steps":
            if ctx.plan.adaptive_steps:
                return None
            ctx.plan.adaptive_steps = True
            return fit.Step(
                "adaptive_steps",
                f"Let the time steps grow (up to {MAX_GROWTH}× the {inputs.steps} starting ones) where the creep is steady, "
                f"still cutting any step whose error passes {TOLERANCE * 100:g} % of the stress, to fit the time target",
                None, None, detail={"starting_steps": inputs.steps, "max_growth": MAX_GROWTH, "tolerance": TOLERANCE},
            )
        return fit.apply_generic(rung, self, ctx, inputs)

    def governing(self, result: AnalysisResult):
        """local_refine follows the largest stress over the time; two passes compare its peak."""
        stress = result.frame_fields["von_mises"][result.scalars["peak_frame"]]
        return stress, float(stress.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: CreepInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea.creep_law import creep_params

        space = ctx.space
        basis = space.basis
        materials = list(ctx.materials)
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        fit_plan = ctx.plan
        planes = list(fit_plan.prepared.planes) if fit_plan is not None and fit_plan.prepared is not None else []
        share = 0.5 ** len(planes)
        external = _external(space, materials, inputs.surface_loads, inputs.body_accelerations, ctx.ordinal_of, share)
        fixture_dofs = [basis.get_dofs(space.facets_of(fixture.faces, ctx.ordinal_of)).all() for fixture in inputs.fixtures]
        held = list(fixture_dofs)
        for plane in planes:
            dofs = basis.get_dofs(space.facets_of_ordinals([plane.ordinal], "a symmetry plane")).all()
            held.append(dofs[space.component[dofs] == plane.component])
        fixed = np.unique(np.concatenate(held)) if held else np.zeros(0, dtype=np.int64)
        free = np.setdiff1d(np.arange(basis.N), fixed)
        if not any(m.creep for m in materials):
            raise ValueError("material.creep: no part of this study has a creep law; add a creep block to its material")
        if len(materials) > 1 and not all(m.creep for m in materials):
            warnings.append("parts with no creep block in their material stay elastic: they do not creep")
        problem = _CreepProblem(space, free, external, creep_params(space, materials))
        timings["assemble_s"] = time.perf_counter() - started

        solver = getattr(fit_plan, "solver", "direct") if fit_plan is not None else "direct"
        adaptive = bool(getattr(fit_plan, "adaptive_steps", False)) if fit_plan is not None else False
        frames_max = int(getattr(ctx.budget, "max_frames", MAX_FRAMES) or MAX_FRAMES) if ctx.budget is not None else MAX_FRAMES
        path, frames, curve = _march(problem, inputs.duration_h, inputs.steps, solver=solver, adaptive=adaptive,
                                     keep=max(frames_max, 2), log=ctx.log)
        timings["solve_s"] = path.seconds
        reached = path.times[-1]
        if ctx.log:
            ctx.log(f"followed the creep to {hours_label(reached)} in {path.steps} time steps ({path.rejected} cut for "
                    f"accuracy), {path.iterations} Newton iterations, in {path.seconds:.1f}s")
        data_temperatures = {m.creep.get("temperature_C") for m in materials if m.creep and "temperature_C" in m.creep}
        if inputs.temperature_C is not None:
            for value in sorted(data_temperatures):
                if abs(value - inputs.temperature_C) > 0.5:
                    warnings.append(f"the creep data are for {value:g} °C and the study runs at {inputs.temperature_C:g} °C; "
                                    "creep changes steeply with temperature, so use data for the temperature it runs at")

        started = time.perf_counter()

        def nodal(values):
            # The L2 projection, never past the quadrature points' own range (it overshoots where a field turns sharply).
            return np.clip(space.scalar.project(values), 0.0, float(values.max()))

        stress_frames = [nodal(vm_q) for _, _, vm_q, _ in frames]
        displacement_frames = [space.nodal(u) for _, u, _, _ in frames]
        creep_frames = [nodal(100.0 * p_q) for _, _, _, p_q in frames]
        gauss_peaks = [float(vm_q.max()) for _, _, vm_q, _ in frames]
        final_u = frames[-1][1]
        internal, _ = problem.evaluate(final_u, tangent=False)
        residual = internal - external
        reactions = [tuple(float(residual[dofs][space.component[dofs] == c].sum()) for c in range(3)) for dofs in fixture_dofs]
        applied = tuple(float(external[space.component == c].sum()) for c in range(3))
        creep_gauss = float(problem.state.equivalent.max()) * 100.0
        dof_locations, boundary, tets, element_dofs, vertices = (space.dof_locations, space.boundary_quadratic, space.tets,
                                                                  space.element_dofs, space.vertices)
        if planes:
            from cadgen._internal.fea import symmetry

            volume = ctx.volume
            for plane in reversed(planes):
                whole, keep = symmetry.unfold_volume(volume, plane)
                scalars = {f"vm{i}": values for i, values in enumerate(stress_frames)}
                scalars.update({f"cs{i}": values for i, values in enumerate(creep_frames)})
                vectors = {f"u{i}": values for i, values in enumerate(displacement_frames)}
                dof_locations, scalars, vectors, boundary, tets, element_dofs, vertices = symmetry.unfold_fields(
                    plane, vertices, dof_locations, keep, scalars=scalars, vectors=vectors, boundary=boundary, tets=tets,
                    element_dofs=element_dofs,
                )
                stress_frames = [scalars[f"vm{i}"] for i in range(len(stress_frames))]
                creep_frames = [scalars[f"cs{i}"] for i in range(len(creep_frames))]
                displacement_frames = [vectors[f"u{i}"] for i in range(len(displacement_frames))]
                reactions = [symmetry.unfold_force(plane, r) for r in reactions]
                applied = symmetry.unfold_force(plane, applied)
                volume = whole
            ctx.volume = volume
        timings["stress_s"] = time.perf_counter() - started

        times = [t for t, _, _, _ in frames]
        attributes = {"von_mises": "_VON_MISES", "displacement": "_DISPLACEMENT", "creep_strain": "_CREEP_STRAIN"}
        series = Series(kind="time", unit="h", default=len(frames) - 1, frames=[
            SeriesFrame(value=round(t, 6), label=hours_label(t),
                        attributes={name: attribute if i == 0 else f"{attribute}_F{i}" for name, attribute in attributes.items()})
            for i, t in enumerate(times)
        ])
        frame_fields = {"von_mises": stress_frames, "displacement": displacement_frames, "creep_strain": creep_frames}
        fields = {name: values[0] for name, values in frame_fields.items()}
        final_fields = {name: values[-1] for name, values in frame_fields.items()}
        peaks = [float(values.max()) for values in stress_frames]
        peak_frame = int(np.argmax(peaks))
        curve_x = [round(t, 6) for t, _, _, _ in curve]
        curves = {
            "max_von_mises_MPa": {"x": curve_x, "x_unit": "h", "y": [round(c[2], 6) for c in curve], "y_unit": "MPa"},
            "max_creep_strain_percent": {"x": curve_x, "x_unit": "h", "y": [round(100.0 * c[3], 8) for c in curve], "y_unit": "%"},
            "max_displacement_mm": {"x": [round(t, 6) for t in times], "x_unit": "h", "y_unit": "mm",
                                    "y": [round(float(np.linalg.norm(d, axis=1).max()), 6) for d in displacement_frames]},
        }
        analysis_warnings = []
        if path.stopped:
            analysis_warnings.append(f"Creep runs away after about {hours_label(reached)}")
        how = f"{path.how}, {path.steps} {'adaptive ' if adaptive else ''}backward Euler time steps"
        return AnalysisResult(
            dof_locations=dof_locations, vertices=vertices, tets=tets, boundary_quadratic=boundary, element_dofs=element_dofs,
            fields=fields, deformation=displacement_frames[0], series=series, frame_fields=frame_fields, curves=curves,
            reactions=reactions, applied=applied, dofs=int(basis.N), solver=how, timings=timings, warnings=warnings,
            scalars={
                "path": path, "final": final_fields, "reached_h": reached, "stopped": path.stopped, "adaptive": adaptive,
                "von_mises_gauss_peaks": gauss_peaks, "creep_gauss_max": creep_gauss, "peak_frame": peak_frame,
                "frame_times": times, "analysis_warnings": analysis_warnings, "data_temperatures": sorted(data_temperatures),
                "part_refs": None if ctx.assembly is None else [part.ref for part in ctx.assembly.parts],
            },
        )

    # -- judging -------------------------------------------------------------------------------------

    def _at(self, result: AnalysisResult, frame: int | None = None) -> dict:
        frame = len(result.series.frames) - 1 if frame is None else frame
        return {"frame": frame, "value": result.series.frames[frame].value, "unit": "h"}

    def _solved_at(self, ctx: SolveContext, result: AnalysisResult, inputs: CreepInputs, frame: int):
        """The stress check's numbers at one frame: the peak, and the yield of the part it is in."""
        import numpy as np

        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import _peak_face

        stress = result.frame_fields["von_mises"][frame]
        moved = np.linalg.norm(result.frame_fields["displacement"][frame], axis=1)
        peak = int(stress.argmax())
        node_moved = int(moved.argmax())
        materials = list(ctx.materials)
        material = materials[0]
        if len(materials) > 1 and ctx.volume.domain is not None:
            element = int(np.flatnonzero((result.element_dofs == peak).any(axis=1))[0])
            material = materials[int(ctx.volume.domain[element])]
        volume = ctx.volume
        fixed = {ctx.ordinal_of[ref] for fixture in inputs.fixtures for ref in fixture.faces}
        outcome = _Outcome(result.boundary_quadratic, result.dof_locations)
        extent = result.dof_locations.max(axis=0) - result.dof_locations.min(axis=0)
        return checks.Solved(
            material_name=material.name, yield_MPa=material.yield_strength, peak_MPa=float(stress[peak]),
            peak_gauss_MPa=float(result.scalars["von_mises_gauss_peaks"][frame]),
            peak_at=tuple(float(c) for c in result.dof_locations[peak]),
            peak_face=_peak_face(volume, outcome, peak, fixed),
            fixed_faces=tuple(volume.faces[o].ref for o in sorted(fixed) if o in volume.faces),
            max_displacement_mm=float(moved[node_moved]),
            displacement_at=tuple(float(c) for c in result.dof_locations[node_moved]),
            bbox_diagonal_mm=float(np.linalg.norm(extent)), margin=ctx.study.margin if ctx.study is not None else 2.0,
            coarser_peak_MPa=None, part=ctx.part_name, dofs=result.dofs,
        )

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: CreepInputs) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks

        final = result.scalars["final"]
        where = f"view.checks[{index}]"
        common = dict(boundary=result.boundary_quadratic, boundary_ordinal=ctx.volume.boundary_ordinal,
                      locations=result.dof_locations, face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of, where=where)
        if check["kind"] == "stress":
            frame = result.scalars["peak_frame"]
            judged = checks.stress_check(self._solved_at(ctx, result, inputs, frame), label=check.get("label"))
            judged["at"] = self._at(result, frame)
        elif check["kind"] == "displacement":
            peak = kinds.field_max_over(np.linalg.norm(final["displacement"], axis=1), tuple(check.get("faces", ())), **common)
            judged = checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces,
                                               label=check.get("label"))
            judged["at"] = self._at(result)
        else:
            peak = kinds.field_max_over(final["creep_strain"], (), **common)
            limit = float(check["limit_percent"])
            ratio = peak.value / limit
            judged = {
                "kind": "creep_strain", "label": check.get("label") or kinds.CREEP_STRAIN.default_label,
                "value": round(peak.value, 6), "limit": limit, "unit": "%", "ratio": round(ratio, 6), "close_at": 0.9,
                "status": checks.check_status(ratio, 0.9), "where": {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]},
                "duration_h": round(result.scalars["reached_h"], 6),
            }
            judged["at"] = self._at(result)
        if result.scalars["stopped"]:
            # The creep ran away before the whole time: whatever the numbers when it stopped, the check fails.
            judged["status"] = "fails"
            judged["stopped_at_h"] = round(result.scalars["reached_h"], 6)
        return judged

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: CreepInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        scalars = result.scalars
        path = scalars["path"]
        whole = "The assembly" if assembly else "The part"
        found: list[dict] = []

        def finding(severity, kind, summary, description, items=()):
            return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description,
                    "items": list(items)}

        if scalars["stopped"]:
            found.append(finding(
                "error", "creep_runs_away",
                f"{whole}'s creep runs away after about {hours_label(scalars['reached_h'])}, before the "
                f"{hours_label(inputs.duration_h)} asked",
                "past that time Newton's method finds no equilibrium even in the smallest time step; the last frame is the last "
                "state found", []))
        for check in check_results:
            if check["kind"] == "creep_strain" and check["status"] == "fails" and not scalars["stopped"]:
                found.append(finding(
                    "error", "creeps_too_far",
                    f"{whole} creeps too far: {check['value']:.3g} % creep strain after {hours_label(check['duration_h'])}, "
                    f"more than the {check['limit']:g} % allowed",
                    f"equivalent creep strain {check['value']:.4g} % at the end of the hold ({check['label']})",
                    [{"text": "most creep strain", **check["where"]}],
                ))
        start, end = result.frame_fields["von_mises"][0].max(), result.frame_fields["von_mises"][-1].max()
        if start > 0 and end < 0.98 * start:
            found.append(finding(
                "info", "stress_relaxes",
                f"The peak stress relaxes from {start:.4g} MPa to {end:.4g} MPa over the hold ({(1 - end / start) * 100:.0f} % less)",
                "creep lets the most stressed regions shed load to the rest; the strength check judges the largest peak over the "
                "hold, the instant the load goes on", []))
        if path.rejected:
            found.append(finding(
                "info", "time_steps_cut",
                f"Cut {path.rejected} time steps to keep each step's error under {TOLERANCE * 100:g} % of the stress",
                f"the smallest step taken was {path.smallest_step:.3g} h", []))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: CreepInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars = result.scalars
        path = scalars["path"]
        final = scalars["final"]
        moved = np.linalg.norm(final["displacement"], axis=1)
        peak = int(final["von_mises"].argmax())
        node_moved = int(moved.argmax())
        creep = final["creep_strain"]
        node = int(creep.argmax())
        start = float(result.frame_fields["von_mises"][0].max())
        end = float(final["von_mises"][peak])
        reached = scalars["reached_h"]
        summary: dict[str, Any] = {
            "status": (f"Creep runs away after about {hours_label(reached)}" if scalars["stopped"]
                       else f"Held for {hours_label(inputs.duration_h)}"),
            "stopped": scalars["stopped"],
            "duration_h": round(inputs.duration_h, 6),
            "reached_h": round(reached, 6),
            "temperature_C": inputs.temperature_C,
            "creep_data_temperature_C": scalars["data_temperatures"] or None,
            "max_creep_strain_percent": round(float(creep[node]), 6),
            "max_creep_strain_gauss_percent": round(scalars["creep_gauss_max"], 6),
            "max_creep_strain_at_mm": [round(float(c), 3) for c in result.dof_locations[node]],
            "initial_max_von_mises_MPa": round(start, 4),
            "max_von_mises_MPa": round(end, 4),
            "max_von_mises_gauss_MPa": round(scalars["von_mises_gauss_peaks"][-1], 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[peak]],
            "relaxation_percent": round((1.0 - end / start) * 100.0, 4) if start > 0 else 0.0,
            "initial_max_displacement_mm": round(float(np.linalg.norm(result.frame_fields["displacement"][0], axis=1).max()), 6),
            "max_displacement_mm": round(float(moved[node_moved]), 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[node_moved]],
            "applied_force_N": [round(x, 4) for x in result.applied],
            "reaction_force_N": [round(sum(r[c] for r in result.reactions), 4) for c in range(3)],
            "steps_requested": inputs.steps,
            "steps": path.steps,
            "steps_cut": path.rejected + path.cuts,
            "smallest_step_h": round(path.smallest_step, 9),
            "largest_step_h": round(path.largest_step, 6),
            "newton_iterations": path.iterations,
            "adaptive": scalars["adaptive"],
            "frames": len(result.series.frames),
            "deformation_scale": scalars.get("deformation_scale"),
        }
        if scalars.get("part_refs"):
            summary["parts"] = [{"ref": ref} for ref in scalars["part_refs"]]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} creep"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        frames = result.frame_fields
        return {
            "von_mises": (0.0, round(max(float(f.max()) for f in frames["von_mises"]), 4)),
            "displacement": (0.0, round(max(float(np.linalg.norm(f, axis=1).max()) for f in frames["displacement"]), 6)),
            "creep_strain": (0.0, round(max(float(f.max()) for f in frames["creep_strain"]), 6)),
        }

    def extras_head(self, summary: dict) -> dict:
        return {"duration_h": summary["duration_h"], "reached_h": summary["reached_h"], "stopped": summary["stopped"]}

    def study_echo(self, inputs: CreepInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = {**StaticAnalysis().study_echo(inputs, bare), "duration_h": inputs.duration_h, "steps": inputs.steps}
        if inputs.temperature_C is not None:
            echo["temperature_C"] = inputs.temperature_C
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        head = summary["status"].lower()
        lines = [f"{head}: creep strain {summary['max_creep_strain_percent']:.3g} %, max displacement "
                 f"{summary['max_displacement_mm']:g} mm (from {summary['initial_max_displacement_mm']:g} mm at 0 h)",
                 f"peak stress {summary['initial_max_von_mises_MPa']:g} MPa when loaded, {summary['max_von_mises_MPa']:g} MPa "
                 f"at the end ({summary['relaxation_percent']:.0f} % relaxed)"]
        lines.append(f"followed in {summary['steps']} {'adaptive ' if summary['adaptive'] else ''}time steps "
                     f"({summary['newton_iterations']} Newton iterations"
                     + (f", {summary['steps_cut']} cut, smallest {summary['smallest_step_h']:.3g} h" if summary["steps_cut"] else "")
                     + ")")
        return lines
