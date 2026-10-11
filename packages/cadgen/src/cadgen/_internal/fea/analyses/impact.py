"""Drop impact: a part dropped onto a rigid floor, simulated through time. Tier 3 (lite).

The study (spec 5.15) gives the drop (``height_mm``, the ``direction`` it falls,
default straight down, a ``"rigid"`` floor and an optional ``friction``
coefficient), how long to follow it (``window_ms``, or ``"auto"``: three times
the contact-time estimate) and, optionally, ``plasticity``
(``{"tangent_MPa": ...}``, bilinear J2 from the material's yield). The part is
meshed with linear tetrahedra (``mesh.order`` 1 is the only order) and
followed from the moment its lowest point touches the floor, every node moving
at the impact speed v = √(2 g h), by central differences
(:mod:`cadgen._internal.fea.explicit`).

The contact-time estimate is the elastic one: a stress wave runs from the
landing point to the far end and back while the part is pressed on the floor,
t_c = 2 L / c, L the part's length along the fall and c = √(E/ρ). A bar dropped
end-on stays on the floor exactly that long and feels ρ c v (the benchmark).

What it writes: a time series (up to ``Budget.max_frames`` frames, evenly
spaced plus the moment of the peak stress), each with the displacement (relative
to the centre of mass's travel) and von Mises; their envelopes over the run; the
plastic strain at the end when plasticity is given; and two curves, the floor's
push against time and the rigid-body g it gives (push / mass). The reported
stress and push are low-pass filtered at the mesh's own resolution (a few
element transits), like a crash test's channel filter. Checks: ``stress`` (peak
von Mises against yield), ``acceleration`` (``limit_g``: the rigid-body g, or
over ``faces`` their mean deceleration) and ``plastic_strain``
(``limit_percent``, with plasticity).

Limits, said everywhere: "Rigid floor; linear tets; elastic unless plasticity is
given." The ladder: ``iterative`` (the matrix-free force loop is already the
method, so it never says anything), ``window`` (stop after the first contact
pulse plus 20 %), ``subcycling`` (the small elements at a smaller step),
``mass_scaling`` (added mass on the smallest elements, at most 5 % of the part's
and always reported with its effect on peak g), then the shared
``local_refine`` and ``defeature``. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext

if TYPE_CHECKING:
    import numpy as np

__all__ = ["ImpactAnalysis", "ImpactInputs", "LIMITS_LINE", "contact_time_estimate", "time_words"]

G0_MM_S2 = 9806.65
DROP_KEYS = frozenset({"height_mm", "direction", "floor", "friction"})
PLASTICITY_KEYS = frozenset({"tangent_MPa"})
LIMITS_LINE = "Rigid floor; linear tets; elastic unless plasticity is given."
#: ``window_ms: "auto"`` follows this many times the contact-time estimate.
AUTO_WINDOWS = 3.0
#: An automatic window is a guess: while the part is still on the floor at its end, the run goes on until the first
#: contact pulse ends (plus 20 %), up to this many times the window.
AUTO_EXTEND = 4.0
#: A peak stress over this many times ρ c v (a plain bar end-on) is explained: at the landing patch, or concentrated
#: on its way (a change of section, a sharp shoulder).
WAVE_OVER = 1.3
#: The window rung expects the run to stop about this long after first contact, in contact-time estimates.
WINDOW_EXPECTED = 1.2
#: The mass-scaling rung's effect on peak g is measured on this share of the window, rerun unscaled.
CHECK_SHARE = 0.1
#: ... when that fits the time target or costs at most this share of the run itself (at worst, twice the time).
RERUN_SHARE = 1.0
#: Bytes per element (its arrays, the force loop's chunk temporaries) and per node (state, envelopes).
BYTES_PER_ELEMENT, BYTES_PER_NODE = 1_500.0, 400.0
#: An acceleration check's label when the study gives none: the peak g the floor gives the part.
ACCELERATION_LABEL = "Peak g"
#: A check is close at 90 % of its limit.
_CLOSE_AT = 0.9
_CURVE_POINTS = 600

#: The last model built, by its volume mesh: estimate, the rungs and the solve share it.
_MODELS: dict[int, tuple[Any, Any, Any]] = {}


@dataclass(frozen=True)
class ImpactInputs(Inputs):
    height_mm: float = 0.0
    #: The way it falls, unit.
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    direction_given: bool = False
    friction: float = 0.0
    #: The window in s; ``None`` for "auto" (three contact-time estimates).
    window_s: float | None = None
    #: Plasticity's tangent modulus (MPa) when the study gives plasticity, else ``None`` (elastic).
    tangent_MPa: float | None = None
    plastic: bool = False
    #: Material properties the study's materials must have (the yield, with plasticity).
    material_needs: frozenset = frozenset()
    #: What the solve found (the faces that met the floor), for the echo: written once, by ``solve``.
    resolved: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def speed_mm_s(self) -> float:
        return math.sqrt(2.0 * G0_MM_S2 * self.height_mm)


def contact_time_estimate(length_mm: float, youngs_MPa: float, density: float) -> float:
    """How long a part of length ``length_mm`` along the fall stays on a rigid floor: the stress wave's round trip,
    2 L / c with c = √(E/ρ) (MPa and t/mm³ give mm/s), in s."""
    return 2.0 * length_mm / math.sqrt(youngs_MPa / density)


def time_words(seconds: float) -> str:
    """A short time as the scrubber says it: "0 s", "39.6 µs", "1.2 ms", "1.5 s"."""
    def figure(value: float) -> str:
        text = f"{value:.3g}"
        return text if "e" not in text else f"{value:.0f}"

    if seconds == 0:
        return "0 s"
    if seconds < 1e-3:
        return f"{figure(seconds * 1e6)} µs"
    if seconds < 1:
        return f"{figure(seconds * 1e3)} ms"
    return f"{figure(seconds)} s"


def _figure(value: float) -> str:
    return f"{value:.3g}" if abs(value) < 1000 else f"{value:,.0f}"


def height_words(height_mm: float) -> str:
    return f"{_figure(height_mm / 1000)} m" if height_mm >= 1000 else f"{_figure(height_mm)} mm"


def _drop(document: dict) -> dict:
    raw = document.get("drop")
    where = "drop"
    if not isinstance(raw, dict):
        raise ValueError('study.drop: expected an object like {"height_mm": 1000, "direction": [0, 0, -1], "floor": "rigid"}')
    unknown = set(raw) - DROP_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; an impact's drop takes {sorted(DROP_KEYS)}")
    if "height_mm" not in raw:
        raise ValueError(f"{where}.height_mm: how far it falls, in mm (1000 for 1 m)")
    height = kinds.number(raw["height_mm"], where=f"{where}.height_mm", positive=True)
    direction, given = (0.0, 0.0, -1.0), False
    if "direction" in raw:
        vector = raw["direction"]
        if not isinstance(vector, list) or len(vector) != 3:
            raise ValueError(f"{where}.direction: the way it falls as [x, y, z], like [0, 0, -1] for straight down")
        components = [kinds.number(c, where=f"{where}.direction") for c in vector]
        size = math.sqrt(sum(c * c for c in components))
        if not size > 0:
            raise ValueError(f"{where}.direction: the direction is zero")
        direction, given = tuple(c / size + 0.0 for c in components), True
    floor = raw.get("floor", "rigid")
    if floor != "rigid":
        raise ValueError(f'{where}.floor: only a rigid floor is modelled, so "rigid", got {kinds.json_text(floor)}')
    friction = kinds.number(raw.get("friction", 0.0), where=f"{where}.friction")
    if friction < 0:
        raise ValueError(f"{where}.friction: a friction coefficient is 0 or more, got {friction:g}")
    return {"height_mm": height, "direction": direction, "direction_given": given, "friction": friction}


def _window(document: dict) -> float | None:
    raw = document.get("window_ms", "auto")
    if raw == "auto":
        return None
    return kinds.number(raw, where="window_ms", positive=True) / 1000.0


def _plasticity(document: dict) -> tuple[bool, float | None]:
    if "plasticity" not in document:
        return False, None
    raw = document["plasticity"]
    if not isinstance(raw, dict):
        raise ValueError('study.plasticity: expected an object like {"tangent_MPa": 200} (the slope past yield)')
    unknown = set(raw) - PLASTICITY_KEYS
    if unknown:
        raise ValueError(f"plasticity: unknown keys {sorted(unknown)}; plasticity takes {sorted(PLASTICITY_KEYS)}")
    if "tangent_MPa" not in raw:
        return True, None
    tangent = kinds.number(raw["tangent_MPa"], where="plasticity.tangent_MPa")
    if tangent < 0:
        raise ValueError(f"plasticity.tangent_MPa: the slope past yield is 0 (perfectly plastic) or more, got {tangent:g}")
    return True, tangent


def _model(ctx: SolveContext):
    """The explicit model of ``ctx.volume`` (cached on it): its element arrays, lumped mass and element steps."""
    from cadgen._internal.fea import explicit

    volume = ctx.volume
    cached = _MODELS.get(id(volume))
    if cached is not None and cached[0] is volume and cached[1] == _material_key(ctx):
        return cached[2]
    # The mesher's arrays: a linear element space keeps its numbering, so nodal results line up with the space's.
    nodes, tets, boundary, domain = volume.nodes, volume.tets[:, :4], volume.boundary[:, :3], volume.domain
    E, nu, rho = _per_element(ctx.materials, domain, len(tets))
    model = explicit.build_model(nodes, tets, boundary, youngs=E, poisson=nu, density=rho)
    _MODELS.clear()
    _MODELS[id(volume)] = (volume, _material_key(ctx), model)
    return model


def _material_key(ctx: SolveContext) -> tuple:
    return tuple((m.E, m.nu, m.density) for m in ctx.materials)


def _per_element(materials, domain, elements: int):
    import numpy as np

    if domain is None or len(materials) == 1:
        m = materials[0]
        return m.E, m.nu, m.density
    index = np.asarray(domain, dtype=np.int64)
    pick = lambda values: np.asarray(values, dtype=float)[index]  # noqa: E731
    return pick([m.E for m in materials]), pick([m.nu for m in materials]), pick([m.density for m in materials])


def _length_along(model, direction) -> float:
    import numpy as np

    height = model.nodes @ np.asarray(direction, dtype=float)
    return float(height.max() - height.min())


def _slowest(ctx: SolveContext):
    """The material with the slowest bar wave speed √(E/ρ): the one that keeps the part on the floor longest."""
    return min(ctx.materials, key=lambda m: m.E / m.density)


class ImpactAnalysis:
    name: ClassVar[str] = "impact"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Drop impact"
    estimate_only: ClassVar[bool] = False
    #: Its explicit elements are the same in every direction: study.parse_study refuses an orthotropic material.
    isotropic_only: ClassVar[bool] = True
    limits: ClassVar[tuple[str, ...]] = (LIMITS_LINE,)
    study_keys: ClassVar[frozenset[str]] = frozenset({"drop", "window_ms", "plasticity"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    mesh_orders: ClassVar[tuple[int, ...]] = (1,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("von_mises_peak", "_VON_MISES_PEAK", "von Mises stress (peak over time)", "MPa"),
        FieldSpec("displacement_peak", "_DISPLACEMENT_PEAK", "displacement (largest over time)", "mm"),
        FieldSpec("plastic_strain", "_PLASTIC_STRAIN", "plastic strain (at the end)", "%"),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.ACCELERATION, kinds.PLASTIC_STRAIN)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress"},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "von_mises_peak", "displacement_peak"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "window", "subcycling", "mass_scaling", "local_refine", "defeature")
    noun: ClassVar[str] = "this drop"
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ImpactInputs:
        drop = _drop(document)
        window = _window(document)
        plastic, tangent = _plasticity(document)
        raw_checks = ((document.get("view") or {}).get("checks") or []) if isinstance(document.get("view"), dict) else []
        if not plastic and any(isinstance(c, dict) and c.get("kind") == "plastic_strain" for c in raw_checks):
            raise ValueError(
                'view.checks: a plastic_strain check needs plasticity (like "plasticity": {"tangent_MPa": 200}); '
                "without it the part stays elastic and never bends for good"
            )
        return ImpactInputs(
            (), (), False, window_s=window, tangent_MPa=tangent, plastic=plastic,
            material_needs=frozenset({"yield_strength"}) if plastic else frozenset(), **drop,
        )

    # -- the ladder ----------------------------------------------------------------------------------

    def _window_s(self, ctx: SolveContext, inputs: ImpactInputs, model) -> tuple[float, float]:
        """(the window to follow, the contact-time estimate), s."""
        slowest = _slowest(ctx)
        estimate = contact_time_estimate(_length_along(model, inputs.direction), slowest.E, slowest.density)
        window = inputs.window_s if inputs.window_s is not None else AUTO_WINDOWS * estimate
        return window, estimate

    @staticmethod
    def _added_mass(plan, model):
        """The density mass scaling adds to each element for the plan's target step, and its share of the mass: never past
        the 5 % cap, even on a mesh other than the one the target was chosen on (local_refine remeshes after it)."""
        from cadgen._internal.fea import explicit

        if plan.mass_scale_dt is None:
            return None, 0.0
        added, share = explicit.mass_scaling(model, plan.mass_scale_dt)
        if share > explicit.MASS_SCALE_CAP * (1 + 1e-9):
            reached, _ = explicit.max_mass_scaling(model, explicit.MASS_SCALE_CAP, plan.mass_scale_dt)
            added, share = explicit.mass_scaling(model, reached)
        return added, share

    def _element_dt(self, ctx: SolveContext, model):
        """The elements' own steps under the plan's mass scaling."""
        added, _ = self._added_mass(ctx.plan, model)
        if added is None:
            return model.element_dt
        return model.element_dt * ((model.rho + added) / model.rho) ** 0.5

    @staticmethod
    def _substeps(plan, model, element_dt) -> int:
        """The substeps the plan's subcycling takes: its own count, or, after mass scaling evened out the element steps,
        the best count on the scaled ones (1 when none saves)."""
        from cadgen._internal.fea import explicit

        if plan.subcycle <= 1:
            return 1
        if plan.mass_scale_dt is None:
            return plan.subcycle
        return explicit.best_subcycle(element_dt, model.tets, model.count)[0]

    def _cost(self, ctx: SolveContext, inputs: ImpactInputs, model) -> tuple[float, float, int]:
        """(seconds, memory bytes, elements) of the plan's run, on the mesh it would make."""
        from cadgen._internal.fea import explicit, fit

        plan = ctx.plan
        element_dt = self._element_dt(ctx, model)
        window, estimate = self._window_s(ctx, inputs, model)
        if plan.window_s is not None:
            window = min(window, plan.window_s)
        share = 1.0
        substeps = self._substeps(plan, model, element_dt)
        if substeps > 1:
            share = explicit.subcycle_work(element_dt, model.tets, model.count, substeps)
        step = explicit.SAFETY * float(element_dt.min())
        elements = float(model.elements)
        if getattr(ctx, "meshed_plan", None) != fit.mesh_key(plan) and ctx.geometry is not None:
            # Another mesh than the one made: its elements from the geometry, its step scaled with the element size.
            elements, _, _ = fit.plan_counts(ctx)
            if plan.size_mm and ctx.volume.max_h:
                step *= plan.size_mm / ctx.volume.max_h
        steps = window / step
        seconds = steps * (fit.SECONDS_PER_STEP + fit.SECONDS_PER_ELEMENT_STEP * elements * share)
        frames = int(getattr(ctx.budget, "max_frames", 24) or 24)
        nodes = elements / 4.0
        memory = fit.BASE_BYTES + BYTES_PER_ELEMENT * elements + BYTES_PER_NODE * nodes + 2 * frames * (12 * nodes + 4 * elements)
        return seconds, memory, int(elements)

    def estimate(self, ctx: SolveContext, inputs: ImpactInputs):
        """The run's cost: elements × steps, the step set by the smallest element. Only the mesh knows that element, so
        before meshing the estimate is nil and the ladder runs once the part is meshed."""
        from cadgen._internal.fea import fit

        if ctx.volume is None:
            return fit.Estimate(dofs=0, memory_bytes=fit.BASE_BYTES, seconds=0.0)
        model = _model(ctx)
        seconds, memory, elements = self._cost(ctx, inputs, model)
        return fit.Estimate(dofs=3 * int(elements / 4), memory_bytes=int(memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: ImpactInputs):
        from cadgen._internal.fea import explicit, fit

        if rung == "iterative":
            return None  # the force loop is matrix-free already: nothing to change, nothing to say
        if rung in ("local_refine", "defeature"):
            return fit.apply_generic(rung, self, ctx, inputs)
        if ctx.volume is None:
            return None
        model = _model(ctx)
        plan = ctx.plan
        if rung == "window":
            if plan.window_s is not None:
                return None
            window, estimate = self._window_s(ctx, inputs, model)
            expected = WINDOW_EXPECTED * estimate
            if expected >= 0.95 * window:
                return None
            plan.window_s = expected
            step = fit.Step(
                "window",
                f"Stopped once the first impact was over (the floor stopped pushing, plus 20%) instead of following the "
                f"whole {time_words(window)}, to fit",
                "the first impact and its peak are kept; a second bounce or later ringing is not followed", None,
                detail={"window_ms": round(window * 1e3, 6), "expected_ms": round(expected * 1e3, 6)},
            )
            return step
        if rung == "subcycling":
            if plan.subcycle > 1:
                return None
            element_dt = self._element_dt(ctx, model)
            n, share = explicit.best_subcycle(element_dt, model.tets, model.count)
            if n <= 1:
                return None
            plan.subcycle = n
            _, touching, _, _, _ = explicit.subcycle_partition(element_dt, model.tets, model.count, n)
            percent = 100.0 * float(touching.mean())
            step = fit.Step(
                "subcycling",
                f"Stepped the {percent:.0f}% of elements with the smallest stable step (and their neighbours) {n}× as often "
                "as the rest, to fit",
                "each region still steps within its own stability limit; where the two meet, the larger step's motion is "
                "interpolated through the small steps", None,
                detail={"substeps": n, "fine_share": round(percent / 100.0, 4), "work_share": round(share, 4)},
            )
            return step
        if rung == "mass_scaling":
            if plan.mass_scale_dt is not None:
                return None
            # The step mass scaling alone needs (it evens out the steps subcycling would have split).
            saved, plan.subcycle = plan.subcycle, 1
            try:
                seconds, _, _ = self._cost(ctx, inputs, model)
            finally:
                plan.subcycle = saved
            target_seconds = max(ctx.budget.seconds, 1e-9)
            smallest = float(model.element_dt.min())
            wanted = smallest * max(1.0, seconds / target_seconds)
            reached, share = explicit.max_mass_scaling(model, explicit.MASS_SCALE_CAP, wanted)
            if reached <= 1.02 * smallest:
                return None
            plan.mass_scale_dt = reached
            added, _ = explicit.mass_scaling(model, reached)
            heavier = int((added > 0).sum())
            step = fit.Step(
                "mass_scaling",
                f"Added {share * 100:.1f}% to the part's mass, on its {heavier} smallest elements, so the time step could "
                f"grow {reached / smallest:.2f}× to fit",
                f"peak g may read up to about {share * 100:.1f}% off (the added mass, not yet measured)", share * 100.0,
                detail={"added_share": round(share, 6), "elements": heavier, "step_gain": round(reached / smallest, 4),
                        "measured": False},
            )
            return step
        return None

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """local_refine keeps the mesh fine where the part is stressed most over the run."""
        envelope = result.fields["von_mises_peak"]
        return envelope, float(envelope.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: ImpactInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import explicit
        from cadgen._internal.fea.analyses.modal import max_frames

        plan = ctx.plan
        timings: dict[str, float] = {}
        started = time.perf_counter()
        model = _model(ctx)
        timings["assemble_s"] = time.perf_counter() - started
        volume = ctx.volume
        window, estimate = self._window_s(ctx, inputs, model)
        stop_after_pulse = plan.window_s is not None
        added, share = self._added_mass(plan, model)
        plastic = None
        if inputs.plastic:
            plastic = self._plastic(ctx, inputs, model)
        subcycle = self._substeps(plan, model, self._element_dt(ctx, model))
        drop = explicit.Drop(inputs.direction, inputs.speed_mm_s, inputs.friction)
        watch = self._watch(ctx, model)
        frames_wanted = max_frames(ctx)
        started = time.perf_counter()
        # The automatic window is the estimate's: past it, a part still on the floor is followed until it lifts off.
        extend_to = AUTO_EXTEND * window if inputs.window_s is None and not stop_after_pulse else None
        run = explicit.simulate(model, drop, end_s=window, stop_after_pulse=stop_after_pulse, subcycle=subcycle,
                                added_rho=added, plastic=plastic, frames=frames_wanted, log=ctx.log, watch=watch,
                                extend_to_s=extend_to)
        timings["march_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"impact: {run.steps} steps of {run.dt * 1e6:.3g} µs to {run.end_s * 1e6:.4g} µs in {run.seconds:.1f}s")
        mass = float((model.rho * model.volume).sum())
        mass_check = None
        if added is not None and share > 0:
            mass_check = self._mass_effect(ctx, model, drop, run.end_s, run, plastic, watch,
                                           seconds_used=timings["march_s"])
        scaled = None
        if added is not None:
            scaled = {"elements": int((added > 0).sum()),
                      "gain": float((model.element_dt * ((model.rho + added) / model.rho) ** 0.5).min() / model.element_dt.min())}
        settled_steps = self._settled_steps(run, window, share, mass_check, mass, scaled)

        nodal = model.nodal
        frame_vm = [nodal(vm) for vm in run.frame_vm]
        frame_u = list(run.frame_u)
        # The viewer opens on the frame of the peak stress.
        default = 0 if run.peak_t is None else min(range(len(run.frame_t)), key=lambda i: abs(run.frame_t[i] - run.peak_t))
        series = Series(kind="time", unit="s", default=default, frames=[
            SeriesFrame(value=round(t, 12), label=time_words(t), attributes={
                "von_mises": "_VON_MISES" if i == 0 else f"_VON_MISES_F{i}",
                "displacement": "_DISPLACEMENT" if i == 0 else f"_DISPLACEMENT_F{i}",
            })
            for i, t in enumerate(run.frame_t)
        ])
        vm_peak = nodal(run.vm_peak)
        fields = {"von_mises": frame_vm[0], "displacement": frame_u[0], "von_mises_peak": vm_peak,
                  "displacement_peak": run.u_peak}
        if run.plastic is not None:
            fields["plastic_strain"] = nodal(run.plastic) * 100.0
        curve_t, curve_f = _thin(run.curve_t, run.curve_force)
        g = [f / mass / G0_MM_S2 for f in curve_f]
        onto = self._onto(volume, model, run)
        inputs.resolved["onto"] = onto
        inputs.resolved["window_s"] = window
        space = ctx.space
        return AnalysisResult(
            dof_locations=space.dof_locations if space is not None else model.nodes,
            vertices=space.vertices if space is not None else model.count,
            tets=space.tets if space is not None else model.tets,
            boundary_quadratic=space.boundary_quadratic if space is not None else model.boundary,
            element_dofs=space.element_dofs if space is not None else model.tets,
            fields=fields,
            deformation=frame_u[0],
            series=series,
            frame_fields={"von_mises": frame_vm, "displacement": frame_u},
            curves={
                "contact_force_N": {"x": [round(t, 12) for t in curve_t], "x_unit": "s",
                                    "y": [round(f, 6) for f in curve_f], "y_unit": "N"},
                "rigid_body_g": {"x": [round(t, 12) for t in curve_t], "x_unit": "s",
                                 "y": [round(v, 6) for v in g], "y_unit": "g"},
            },
            scalars={
                "run": run, "model_mass_t": mass, "window_s": window, "contact_estimate_s": estimate,
                "window_auto": inputs.window_s is None, "stop_after_pulse": stop_after_pulse, "added_share": share,
                "mass_check": mass_check, "frame_t": list(run.frame_t), "watch": watch,
                "element_peak_t": run.vm_peak_t, "element_peak": run.vm_peak,
                "yields": [m.yield_strength for m in ctx.materials], "node_domain": _node_domain(model, space),
                "margin": float(getattr(ctx.study, "margin", 2.0) or 2.0), "analysis_warnings": [],
                "elements": model.elements, "length_mm": _length_along(model, inputs.direction), "subcycle": run.subcycle,
                "settled_steps": settled_steps,
            },
            dofs=3 * model.count,
            solver=(f"explicit central difference, lumped mass, {run.steps} steps of {run.dt * 1e6:.3g} µs"
                    + (f", subcycled {run.subcycle}×" if run.subcycle > 1 else "")
                    + (f", mass scaled +{share * 100:.1f}%" if added is not None else "")),
            timings=timings,
            warnings=[],
        )

    def _plastic(self, ctx: SolveContext, inputs: ImpactInputs, model):
        import numpy as np

        from cadgen._internal.fea import explicit

        yields, hardening = [], []
        for material in ctx.materials:
            tangent = inputs.tangent_MPa if inputs.tangent_MPa is not None else (material.tangent or 0.0)
            if tangent >= material.E:
                raise ValueError(f"plasticity.tangent_MPa: the slope past yield ({tangent:g} MPa) must be under "
                                 f"{material.name}'s Young's modulus ({material.E:g} MPa)")
            yields.append(float(material.yield_strength))
            hardening.append(material.E * tangent / (material.E - tangent))
        domain = ctx.space.domain if ctx.space is not None else None
        if domain is None or len(ctx.materials) == 1:
            return explicit.Plastic(yields[0], hardening[0])
        index = np.asarray(domain, dtype=np.int64)
        return explicit.Plastic(np.asarray(yields)[index], np.asarray(hardening)[index])

    def _watch(self, ctx: SolveContext, model) -> dict:
        """The node groups an acceleration check over faces follows: one per check, its faces' boundary nodes."""
        import numpy as np

        groups = {}
        for index, check in enumerate(getattr(ctx.study, "checks", ()) or ()):
            if check.get("kind") != "acceleration" or not check.get("faces"):
                continue
            ordinals = [ctx.ordinal_of[ref] for ref in check["faces"]]
            rows = np.isin(ctx.volume.boundary_ordinal, ordinals)
            groups[f"check{index}"] = np.unique(model.boundary[rows])
        return groups

    def _mass_effect(self, ctx, model, drop, window, run, plastic, watch, *, seconds_used: float):
        """Mass scaling's effect on peak g: the first 10 % of the window that ran, rerun unscaled, when the time target
        allows."""
        from cadgen._internal.fea import explicit, fit

        span = CHECK_SHARE * window
        steps = span / (explicit.SAFETY * float(model.element_dt.min()))
        cost = steps * (fit.SECONDS_PER_STEP + fit.SECONDS_PER_ELEMENT_STEP * model.elements)
        # Measured when it fits the time target, or costs no more than the run itself.
        if seconds_used + cost > ctx.budget.seconds and cost > RERUN_SHARE * seconds_used:
            return {"measured": False, "span_s": span, "cost_s": cost}
        check = explicit.simulate(model, drop, end_s=span, plastic=plastic, frames=2, watch=watch)
        scaled = max((f for t, f in zip(run.curve_t, run.curve_force) if t <= span * (1 + 1e-9)), default=0.0)
        unscaled = check.peak_force
        pct = 100.0 * abs(scaled - unscaled) / unscaled if unscaled > 0 else 0.0
        return {"measured": True, "span_s": span, "scaled_N": scaled, "unscaled_N": unscaled, "pct": pct,
                "seconds": check.seconds}

    @staticmethod
    def _settled_steps(run, window: float, share: float, mass_check: dict | None, mass: float,
                       scaled: dict | None) -> dict[str, dict]:
        """What each rung's step says once the run is done (window, subcycling, mass_scaling), for :meth:`settle_steps`:
        ``{rung: {"words", "accuracy", "accuracy_pct", "detail"}}``. A rung not taken is never said again."""
        window_words = (
            f"Stopped at {time_words(run.end_s)}, once the first impact was over (the floor stopped pushing "
            f"at {time_words(run.pulse_end_s)}, plus 20%), instead of following the whole {time_words(window)}, to fit"
            if run.stopped_early else
            f"Was ready to stop once the first impact was over, but the floor was still pushing, so the whole "
            f"{time_words(window)} was followed"
        )
        subcycle_words = (
            f"Stepped the {run.fine_share * 100:.0f}% of elements with the smallest stable step (and their "
            f"neighbours) {run.subcycle}× as often as the rest, to fit"
            if run.subcycle > 1 else
            "Was ready to step the smallest elements more often, but on the final mesh (after mass scaling, where "
            "taken) no group of small elements was worth it, so every element shared one step"
        )
        mass_step: dict = {"detail": {"added_share": round(share, 6), "added_t": round(share * mass, 12)}}
        if share > 0 and scaled is not None:
            mass_step["words"] = (f"Added {share * 100:.1f}% to the part's mass, on its {scaled['elements']} smallest "
                                  f"elements, so the time step could grow {scaled['gain']:.2f}× to fit")
            mass_step["detail"].update({"elements": scaled["elements"], "step_gain": round(scaled["gain"], 4)})
        if share <= 0:
            mass_step.update(words="Was ready to add mass to the smallest elements, but the final mesh had none small "
                                   "enough to need it", accuracy="no mass was added, so peak g is unchanged", accuracy_pct=0.0)
        elif mass_check and mass_check.get("measured"):
            pct = mass_check["pct"]
            mass_step.update(accuracy=f"peak g moved {pct:.1f}% against an unscaled rerun of the first "
                                      f"{time_words(mass_check['span_s'])}", accuracy_pct=pct)
            mass_step["detail"].update({"measured": True, "unscaled_peak_N": round(mass_check["unscaled_N"], 4),
                                        "scaled_peak_N": round(mass_check["scaled_N"], 4)})
        else:
            mass_step.update(accuracy=f"peak g may read up to about {share * 100:.1f}% off (the added mass; no time was "
                                      "left to rerun it unscaled)", accuracy_pct=share * 100.0)
        return {
            "window": {"words": window_words,
                       "detail": {"stopped_ms": round(run.end_s * 1e3, 6), "stopped_early": run.stopped_early}},
            "subcycling": {"words": subcycle_words,
                           "detail": {"fine_share": round(run.fine_share, 4), "substeps_used": run.subcycle}},
            "mass_scaling": mass_step,
        }

    def settle_steps(self, result: AnalysisResult, steps: list) -> list:
        """The window, subcycling and mass_scaling steps said again once the run is done (run.py calls this after
        the solve; each settled step is a new one, never changed in place)."""
        from cadgen._internal.fea import fit

        for rung, settled in result.scalars.get("settled_steps", {}).items():
            steps = fit.settle_step(steps, rung, settled)
        return steps

    def _onto(self, volume, model, run) -> list[str]:
        """The faces that met the floor: every boundary triangle whose corners all touched it."""
        import numpy as np

        rows = run.touched[model.boundary].all(axis=1)
        ordinals = sorted({int(o) for o in volume.boundary_ordinal[rows]} - {0})
        return [volume.faces[o].ref for o in ordinals if o in volume.faces]

    # -- checks, findings ----------------------------------------------------------------------------

    def needs_finer(self, result: AnalysisResult, inputs: ImpactInputs, check_results: list[dict]) -> bool:
        """An explicit run is not repeated finer on its own: its cost grows with the fourth power of the element size."""
        return False

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_MPa": round(self._stress_peak(result)[1], 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_von_mises_MPa"] = round(self._stress_peak(finer)[1], 4)
        return finer

    def _frame_at(self, result: AnalysisResult, when: float) -> int:
        times = result.scalars["frame_t"]
        return min(range(len(times)), key=lambda i: (abs(times[i] - when), i))

    def _at(self, result: AnalysisResult, when: float) -> dict:
        return {"frame": self._frame_at(result, when), "value": round(when, 12), "unit": "s", "time_s": round(when, 12)}

    def _stress_peak(self, result: AnalysisResult) -> tuple[int, float, float]:
        """(node, MPa, s) of the highest von Mises over the run (the nodal envelope; its time, its worst element's)."""
        envelope = result.fields["von_mises_peak"]
        node = int(envelope.argmax())
        element = int(result.scalars["element_peak"].argmax())
        return node, float(envelope[node]), float(result.scalars["element_peak_t"][element])

    def _wave_finding(self, ctx: SolveContext, result: AnalysisResult, inputs: ImpactInputs) -> tuple[str, str] | None:
        """Why the peak is well over ρ c v, the stress a plain bar dropped end-on feels (summary and description), or
        None. Away from the floor the stress wave was concentrated on its way: where the part widens the wave steps up
        (by 2 A2 / (A1 + A2), up to 2×) and a sharp shoulder concentrates it further. At the floor, the wave a widening
        sends back meets the floor's push again (a bar widening from A1 to A2 feels 1 + 2 (A2 - A1) / (A2 + A1) times
        ρ c v at its landing end), and a landing on a small patch (an edge, a corner, a chamfer) is stiff on linear
        tets: the finding names both."""
        import numpy as np

        node, peak, _ = self._stress_peak(result)
        domains = result.scalars["node_domain"]
        material = ctx.materials[0 if domains is None or len(ctx.materials) == 1 else int(domains[node])]
        rho_c_v = material.density * math.sqrt(material.E / material.density) * inputs.speed_mm_s
        if not (rho_c_v > 0 and peak > WAVE_OVER * rho_c_v):
            return None
        d = np.asarray(inputs.direction, dtype=float)
        d = d / np.linalg.norm(d)
        height = np.asarray(result.dof_locations) @ d
        size = float(getattr(ctx.volume, "max_h", 0.0) or 0.05 * result.scalars["length_mm"])
        times = f"{peak / rho_c_v:.1f}×"
        base = f"ρ c v = {rho_c_v:.3g} MPa"
        if float(height.max() - height[node]) <= 2.0 * size:
            return (f"The peak stress is {times} the {base} a plain bar dropped end-on feels, where it lands: the wave sent "
                    "back from where the part widens meets the floor's push there again, and where the floor meets only a "
                    "small patch (an edge, a corner or a chamfer) the linear tets are stiff; a fillet or a finer mesh "
                    "there tells the two apart",
                    f"peak {peak:.4g} MPa within two elements of the floor; ρ c v with c = √(E/ρ) and v the impact speed")
        return (f"The peak stress is {times} the {base} a plain bar dropped end-on feels, away from where it lands: "
                "the impact's stress wave is concentrated on its way, where the part widens (the wave steps up there, "
                "up to 2×) and at a sharp shoulder or corner; a fillet there lowers it",
                f"peak {peak:.4g} MPa {float(height.max() - height[node]):.3g} mm from the floor; ρ c v with c = √(E/ρ) "
                "and v the impact speed")

    def _yield_at(self, result: AnalysisResult, node: int) -> float:
        domains = result.scalars["node_domain"]
        yields = result.scalars["yields"]
        if domains is None or len(yields) == 1:
            return yields[0]
        return yields[int(domains[node])]

    def peak_g(self, result: AnalysisResult) -> tuple[float, float]:
        """(peak rigid-body g, when): the floor's filtered push over the part's mass."""
        run = result.scalars["run"]
        return run.peak_force / result.scalars["model_mass_t"] / G0_MM_S2, run.peak_force_t

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: ImpactInputs) -> dict:
        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import peak_face

        kind = check["kind"]
        if kind == "stress":
            node, peak, when = self._stress_peak(result)
            at = tuple(float(c) for c in result.dof_locations[node])
            solved = checks.Solved(
                material_name="", yield_MPa=self._yield_at(result, node), peak_MPa=peak, peak_gauss_MPa=peak, peak_at=at,
                peak_face=peak_face(ctx.volume, result, node, set()), fixed_faces=(), max_displacement_mm=0.0,
                displacement_at=at, bbox_diagonal_mm=0.0, margin=result.scalars["margin"], coarser_peak_MPa=None, part="",
            )
            return {**checks.stress_check(solved, label=check.get("label")), "at": self._at(result, when)}
        if kind == "acceleration":
            run = result.scalars["run"]
            name = f"check{index}"
            if check.get("faces") and name in run.watched:
                value_mm, when = run.watched[name]
                value = value_mm / G0_MM_S2
                faces = tuple(ctx.volume.faces[ctx.ordinal_of[ref]].ref for ref in check["faces"])
                ref = faces[0]
                at = tuple(float(c) for c in result.dof_locations[result.scalars["watch"][name]].mean(axis=0))
            else:
                value, when = self.peak_g(result)
                faces, ref = (), None
                at = tuple(float(c) for c in result.dof_locations.mean(axis=0))
            ratio = value / check["limit_g"]
            judged = {
                "kind": "acceleration", "label": check.get("label") or ACCELERATION_LABEL,
                "value": round(value, 4), "limit": check["limit_g"], "unit": "g", "ratio": round(ratio, 6),
                "close_at": _CLOSE_AT, "status": checks.check_status(ratio, _CLOSE_AT),
                "where": {"ref": ref, "at": [round(c, 3) for c in at]},
            }
            if faces:
                judged["faces"] = list(faces)
            judged["at"] = self._at(result, when)
            return judged
        # plastic_strain: the permanent strain left at the end.
        strain = result.fields.get("plastic_strain")
        import numpy as np

        values = strain if strain is not None else np.zeros(len(result.dof_locations))
        node = int(values.argmax())
        value = float(values[node])
        ratio = value / check["limit_percent"]
        end = result.scalars["frame_t"][-1]
        return {
            "kind": "plastic_strain", "label": check.get("label") or kinds.PLASTIC_STRAIN.default_label,
            "value": round(value, 6), "limit": check["limit_percent"], "unit": "%", "ratio": round(ratio, 6),
            "close_at": _CLOSE_AT, "status": checks.check_status(ratio, _CLOSE_AT),
            "where": {"ref": peak_face(ctx.volume, result, node, set()),
                      "at": [round(float(c), 3) for c in result.dof_locations[node]]},
            "at": self._at(result, end),
        }

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ImpactInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.modal import finding

        scalars = result.scalars
        run = scalars["run"]
        whole = "the assembly" if assembly else "the part"
        found: list[dict] = []
        for check in check_results:
            status = check["status"]
            if status not in ("fails", "close"):
                continue
            when = time_words(check["at"]["value"])
            severity = "error" if status == "fails" else "warning"
            item = [{"text": check["label"], **check["where"]}]
            if check["kind"] == "stress":
                if status == "fails":
                    sentence = (f"At {when} after landing, {whole} reaches {check['value']:.3g} MPa, over its "
                                f"{check['limit']:g} MPa yield ({check['label']})")
                else:
                    sentence = (f"At {when} after landing, {whole} reaches {check['value']:.3g} MPa, inside the "
                                f"{check['margin']:g}× margin under its {check['limit']:g} MPa yield ({check['label']})")
                found.append(finding(severity, "impact_yields" if status == "fails" else "impact_close_to_yield", sentence,
                                     f"peak von Mises over the impact {check['value']:.4g} MPa at {when}", item))
            elif check["kind"] == "acceleration":
                verb = "more than" if status == "fails" else "close to"
                found.append(finding(severity, "impact_g_over_limit" if status == "fails" else "impact_g_close",
                                     f"It takes {_figure(check['value'])} g at {when}, {verb} the {check['limit']:g} g allowed "
                                     f"({check['label']})", "the peak deceleration of the floor's push, filtered", item))
            elif check["kind"] == "plastic_strain":
                verb = "more than" if status == "fails" else "close to"
                found.append(finding(severity, "impact_bends_for_good" if status == "fails" else "impact_plastic_close",
                                     f"It is left bent for good: {check['value']:.3g}% permanent strain, {verb} the "
                                     f"{check['limit']:g}% allowed ({check['label']})",
                                     "the plastic strain left at the end of the run", item))
        wave = self._wave_finding(ctx, result, inputs)
        if wave is not None:
            found.append(finding("info", "impact_stress_wave", *wave, []))
        g, g_at = self.peak_g(result)
        contact = run.pulse_end_s
        found.append(finding(
            "info", "impact_peak",
            f"The floor stops it with a peak of {_figure(g)} g at {time_words(g_at)}"
            + (f"; it is on the floor for {time_words(contact)}" if contact is not None else ""),
            f"{LIMITS_LINE} The floor's push peaks at {run.peak_force:.4g} N; g is that push over the part's mass",
            [],
        ))
        if contact is None:
            found.append(finding(
                "info", "still_in_contact",
                f"Still pressing on the floor at the end ({time_words(run.end_s)}): run longer (window_ms) to follow the "
                "whole impact",
                f"the contact-time estimate was {time_words(scalars['contact_estimate_s'])}", [],
            ))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(float(result.fields["displacement_peak"].max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: ImpactInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars = result.scalars
        run = scalars["run"]
        node, peak, when = self._stress_peak(result)
        envelope = result.fields["displacement_peak"]
        d_node = int(envelope.argmax())
        yield_MPa = self._yield_at(result, node)
        factor = yield_MPa / peak if peak > 0 else None
        g, g_at = self.peak_g(result)
        mass = scalars["model_mass_t"]
        speed = inputs.speed_mm_s
        summary: dict[str, Any] = {
            "limits": LIMITS_LINE,
            "drop": {
                "height_mm": inputs.height_mm, "impact_speed_m_s": round(speed / 1000.0, 4),
                "direction": [round(c, 6) for c in inputs.direction], "floor": "rigid", "friction": inputs.friction,
            },
            "window_ms": round(scalars["window_s"] * 1e3, 9),
            "window_auto": scalars["window_auto"],
            "contact_time_estimate_ms": round(scalars["contact_estimate_s"] * 1e3, 9),
            "contact_ms": None if run.pulse_end_s is None else round(run.pulse_end_s * 1e3, 9),
            "end_ms": round(run.end_s * 1e3, 9),
            "stopped_after_pulse": run.stopped_early,
            # The automatic window was followed on past its end until the first impact was over.
            "extended_to_pulse_end": run.extended,
            "step_us": round(run.dt * 1e6, 9),
            "steps": run.steps,
            "subcycle": scalars["subcycle"],
            "mass_added_percent": round(scalars["added_share"] * 100.0, 4),
            "mass_kg": round(mass * 1000.0, 9),
            "max_von_mises_MPa": round(peak, 4),
            "max_von_mises_at_ms": round(when * 1e3, 9),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[node]],
            "yield_MPa": yield_MPa,
            "safety_factor": None if factor is None else math.floor(factor * 1000) / 1000,
            "peak_force_N": round(run.peak_force, 4),
            "peak_g": round(g, 4),
            "peak_g_at_ms": round(g_at * 1e3, 9),
            "max_displacement_mm": round(float(envelope[d_node]), 6),
            "max_displacement_at_ms": round(float(run.u_peak_t[d_node]) * 1e3, 9),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[d_node]],
            "filter_us": round(run.filter_s * 1e6, 6),
            "unfiltered": {"max_von_mises_MPa": round(run.raw_peak_vm, 4), "peak_force_N": round(run.raw_peak_force, 4)},
            # The centre of mass's speed away from the floor at the end (negative: still moving toward it).
            "rebound_speed_m_s": round(-run.energy["centre_velocity_end_mm_s"] / 1000.0, 4),
            "frames": len(scalars["frame_t"]),
            "plastic": inputs.plastic,
            "deformation_scale": scalars["deformation_scale"],
        }
        if inputs.plastic:
            strain = result.fields["plastic_strain"]
            summary["tangent_MPa"] = inputs.tangent_MPa
            summary["max_plastic_strain_percent"] = round(float(strain.max()), 6)
            summary["max_plastic_strain_at_mm"] = [round(float(c), 3) for c in result.dof_locations[int(strain.argmax())]]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} drop impact"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        vm = max(float(v.max()) for v in result.frame_fields["von_mises"])
        disp = max(float(np.linalg.norm(d, axis=1).max()) for d in result.frame_fields["displacement"])
        ranges = {"von_mises": (0.0, round(vm, 4)), "displacement": (0.0, round(disp, 6)),
                  "von_mises_peak": (0.0, summary["max_von_mises_MPa"]), "displacement_peak": (0.0, summary["max_displacement_mm"])}
        if "plastic_strain" in result.fields:
            ranges["plastic_strain"] = (0.0, round(float(result.fields["plastic_strain"].max()), 6))
        return ranges

    def extras_head(self, summary: dict) -> dict:
        return {"peak_g": summary["peak_g"], "safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: ImpactInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo: dict[str, Any] = {
            "drop": {"height_mm": inputs.height_mm, "direction": [float(c) for c in inputs.direction], "floor": "rigid",
                     "friction": inputs.friction, "onto": list(inputs.resolved.get("onto", []))},
            "window_ms": "auto" if inputs.window_s is None else round(inputs.window_s * 1e3, 9),
        }
        if inputs.plastic:
            echo["plasticity"] = {"tangent_MPa": inputs.tangent_MPa}
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        drop = summary["drop"]
        contact = summary["contact_ms"]
        lines = [
            summary["limits"],
            f"{height_words(drop['height_mm'])} drop at {drop['impact_speed_m_s']} m/s onto a rigid floor, falling along "
            f"{drop['direction']}; followed for {time_words(summary['end_ms'] / 1e3)} in {summary['steps']} steps of "
            f"{summary['step_us']:.3g} µs"
            + (" (stopped after the first impact)" if summary["stopped_after_pulse"] else "")
            + (f" (on past the automatic {time_words(summary['window_ms'] / 1e3)}, until the first impact was over)"
               if summary.get("extended_to_pulse_end") else ""),
            f"peak {_figure(summary['peak_g'])} g ({summary['peak_force_N']:.4g} N from the floor) at "
            f"{time_words(summary['peak_g_at_ms'] / 1e3)}; "
            + (f"on the floor for {time_words(contact / 1e3)}" if contact is not None else "still on the floor at the end")
            + f" (estimate {time_words(summary['contact_time_estimate_ms'] / 1e3)})",
            f"peak stress {summary['max_von_mises_MPa']:.4g} MPa at {time_words(summary['max_von_mises_at_ms'] / 1e3)}, "
            f"yield {summary['yield_MPa']:g} MPa; moves up to {summary['max_displacement_mm']:.3g} mm (relative to its travel)",
        ]
        if summary.get("plastic"):
            lines.append(f"left bent for good: up to {summary['max_plastic_strain_percent']:.3g}% plastic strain")
        if summary["mass_added_percent"] > 0:
            lines.append(f"mass scaled: +{summary['mass_added_percent']:.2f}% of the part's mass on its smallest elements")
        return lines


def _thin(times: list[float], values: list[float]) -> tuple[list[float], list[float]]:
    """At most _CURVE_POINTS points of a curve, its peak and both ends kept."""
    if len(times) <= _CURVE_POINTS:
        return list(times), list(values)
    stride = math.ceil(len(times) / _CURVE_POINTS)
    top = max(range(len(values)), key=values.__getitem__)
    keep = sorted({0, len(times) - 1, top, *range(0, len(times), stride)})
    return [times[i] for i in keep], [values[i] for i in keep]


def _node_domain(model, space) -> "np.ndarray | None":
    import numpy as np

    if space is None or space.domain is None:
        return None
    out = np.zeros(model.count, dtype=np.int64)
    out[model.tets] = np.asarray(space.domain)[:, None]
    return out
