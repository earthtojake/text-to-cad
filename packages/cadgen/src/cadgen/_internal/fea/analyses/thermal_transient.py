"""Heat over time: temperature against time from a start, with heat, held temperatures and air that change on a schedule.

The study (spec 5.6) takes the thermal keys (``temperatures``, ``heat``,
``convection``), each entry with an optional ``history`` ([[t_s, factor], ...],
piecewise linear, multiplying its W, W/m², C or ambient_C), plus
``initial_C`` (the start, default 20 °C), ``end_s`` and ``step_s`` (a number,
or ``"auto"``: a two-hundredth of the run). An insulated part warming up is
well posed over time, so no anchor is required; something must change its
temperature, though. ``radiation`` is the steady study's (to the surroundings,
and between faces with ``surface_to_surface``), with no schedule: each step
solves its T⁴ by Newton's method.

Backward Euler (θ = 1), :func:`cadgen._internal.fea.thermal_ops.march`; the
ladder's ``adaptive_steps`` rung controls the step by step doubling. It keeps
its own march rather than :func:`cadgen._internal.fea.timestep.theta`: a held
temperature here follows its ``history``, so each step sets the held DOF at
the step's end on the full (C + Δt K) system, a Δt-dependent coupling theta's
``load(t)`` on the free DOF cannot carry; and its step error is judged against
the temperature spread the study sets (at least 1 °C), where theta's is judged
against the state's largest absolute value. The
``temperature`` and ``heat_flux`` fields are written per frame, up to
``Budget.max_frames`` of them (24): evenly spaced from t = 0 plus the hottest
step, which the viewer opens on. The ``max_temperature_C`` curve runs over
every step. A ``temperature`` check judges the highest temperature over all
time (over its faces, else the whole part), and says when (``at.time_s``) and
at which frame. Stdlib only at import.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.thermal import (
    HEAT_KEYS, RADIATION_KEY, ThermalAnalysis, ThermalInputs, build_system, check_limits, heat_echo, ladder_estimate,
    parse_heat_keys, parse_radiation, plan_solver, radiation_line, radiation_summary, reference_of, space_result,
    temperature_check,
)

__all__ = ["ThermalTransientAnalysis", "TransientInputs", "time_label"]

#: ``step_s: "auto"`` takes this many steps over the run.
AUTO_STEPS = 200
#: Frames a series keeps when the budget does not say.
MAX_FRAMES = 24


@dataclass(frozen=True)
class TransientInputs(ThermalInputs):
    initial_C: float = 20.0
    end_s: float = 0.0
    #: The step in s; ``None`` for "auto" (end_s / 200).
    step_s: float | None = None

    @property
    def first_step(self) -> float:
        return self.step_s if self.step_s is not None else self.end_s / AUTO_STEPS


def time_label(seconds: float) -> str:
    """A time as the scrubber says it: "0 s", "12 ms", "1.5 s", "45 s", "5 min", "2.5 h"."""
    def figure(value: float) -> str:
        text = f"{value:.3g}"
        return text if "e" not in text else f"{value:.0f}"

    if seconds == 0:
        return "0 s"
    if seconds < 1:
        return f"{figure(seconds * 1000)} ms"
    if seconds < 120:
        return f"{figure(seconds)} s"
    if seconds < 7200:
        return f"{figure(seconds / 60)} min"
    return f"{figure(seconds / 3600)} h"


class ThermalTransientAnalysis(ThermalAnalysis):
    name: ClassVar[str] = "thermal_transient"
    word: ClassVar[str] = "Heat over time"
    study_keys: ClassVar[frozenset[str]] = frozenset({*HEAT_KEYS, RADIATION_KEY, "initial_C", "end_s", "step_s"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"conductivity", "specific_heat", "density"})
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True, per_frame=True),
        FieldSpec("heat_flux", "_HEAT_FLUX", "heat flux", "W/m²", per_frame=True),
    )
    drives: ClassVar[tuple[str, ...]] = ("field", "frame", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["temperature", "heat_flux"]},
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "defeature", "linear_elements", "symmetry", "adaptive_steps")

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> TransientInputs:
        temperatures, heat, convection = parse_heat_keys(document, transient=True)
        radiation = parse_radiation(document)
        if not (temperatures or heat or convection or radiation):
            raise ValueError(
                "study: nothing changes the part's temperature; add 'heat' (heat put in), 'temperatures' (faces held at a "
                "temperature), 'convection' (air or liquid at a temperature) or 'radiation' (faces radiating to the surroundings)"
            )
        initial = kinds.number(document.get("initial_C", 20.0), where="initial_C")
        if "end_s" not in document:
            raise ValueError("study.end_s: how long to follow the temperatures, in seconds, like 600 for ten minutes")
        end = kinds.number(document["end_s"], where="end_s", positive=True)
        raw_step = document.get("step_s", "auto")
        step = None
        if raw_step != "auto":
            step = kinds.number(raw_step, where="step_s", positive=True)
            if step > end:
                raise ValueError(f"step_s: the step ({step:g} s) is longer than the run ({end:g} s); use a shorter step or \"auto\"")
        reference = reference_of(temperatures, convection, initial, *(entry.ambient for entry in radiation))
        check_limits(document, reference)
        refs = tuple(dict.fromkeys(ref for group in (*temperatures, *heat, *convection, *radiation) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for group in (*temperatures, *convection, *radiation) for ref in group.faces))
        return TransientInputs(refs, anchors, False, temperatures=temperatures, heat=heat, convection=convection,
                               reference_C=reference, initial_C=initial, end_s=end, step_s=step, radiation=radiation)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: TransientInputs):
        """The scalar problem's estimate plus a solve a step; step doubling takes three solves a step, but the
        steps grow where little changes: about half the solves of the fixed steps, as measured on lumped cooling."""
        steps = max(1, round(inputs.end_s / inputs.first_step))
        if ctx.plan.adaptive_steps:
            steps = max(1, steps // 2)
        if inputs.radiation:
            steps *= 3  # Newton on the T⁴: a few solves a step
        frames = int(getattr(ctx.budget, "max_frames", MAX_FRAMES) or MAX_FRAMES)
        return ladder_estimate(ctx, steps=steps, frames=frames)

    def apply(self, rung, ctx: SolveContext, inputs: TransientInputs):
        if rung != "adaptive_steps":
            return super().apply(rung, ctx, inputs)
        from cadgen._internal.fea.fit import Step
        from cadgen._internal.fea.thermal_ops import ADAPTIVE_TOLERANCE

        if ctx.plan.adaptive_steps:
            return None
        ctx.plan.adaptive_steps = True
        share = ADAPTIVE_TOLERANCE * 100
        return Step(
            rung="adaptive_steps",
            words="Let the time step grow while the temperatures change slowly, checking each step against two half steps, "
                  "to fit the time target",
            accuracy=f"each step kept within {share:g}% of the temperature range of its two half steps",
            accuracy_pct=share,
            detail={"first_step_s": round(inputs.first_step, 9), "tolerance": ADAPTIVE_TOLERANCE},
        )

    def governing(self, result: AnalysisResult):
        """local_refine keeps the mesh fine where it got hottest over all time; two passes compare the hottest."""
        run = result.scalars["march"]
        return run.node_peak, float(run.hottest)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: TransientInputs) -> AnalysisResult:
        import time

        from cadgen._internal.fea import operators, thermal_ops

        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        system = build_system(ctx, inputs)
        capacity = operators.capacity(ctx.space, list(ctx.materials))
        timings["assemble_s"] = time.perf_counter() - started
        adaptive = bool(getattr(ctx.plan, "adaptive_steps", False))
        frames = int(getattr(ctx.budget, "max_frames", MAX_FRAMES) or MAX_FRAMES)
        started = time.perf_counter()
        run = thermal_ops.march(
            system, capacity, inputs.initial_C, inputs.end_s, inputs.first_step, warnings,
            frames=frames, adaptive=adaptive, solver=plan_solver(ctx), log=ctx.log,
        )
        timings["solve_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"followed the temperatures for {inputs.end_s:g} s in {run.steps} steps in {timings['solve_s']:.1f}s")
        temperatures = [state for _, state in run.frames]
        fluxes = [thermal_ops.heat_flux(ctx.space, list(ctx.materials), state) for state in temperatures]
        series = Series(kind="time", unit="s", default=run.hottest_frame, frames=[
            SeriesFrame(value=round(t, 9), label=time_label(t), attributes={
                "temperature": "_TEMPERATURE" if i == 0 else f"_TEMPERATURE_F{i}",
                "heat_flux": "_HEAT_FLUX" if i == 0 else f"_HEAT_FLUX_F{i}",
            })
            for i, (t, _) in enumerate(run.frames)
        ])
        how = ("multigrid CG" if plan_solver(ctx) or system.size >= operators.DIRECT_SOLVE_BELOW else "superlu") + \
            f", backward Euler, {run.steps} {'adaptive ' if adaptive else ''}steps"
        if system.radiation is not None:
            how += f", Newton on the radiation ({run.solves} solves)"
        result = space_result(
            ctx.space,
            # Frame 0 (t = 0) is the fields' own attribute; the viewer opens on the series' default, the hottest.
            {"temperature": temperatures[0], "heat_flux": fluxes[0]},
            series=series, frame_fields={"temperature": temperatures, "heat_flux": fluxes},
            curves={"max_temperature_C": {"x": [round(t, 9) for t in run.curve_t], "x_unit": "s",
                                          "y": [round(v, 6) for v in run.curve_max], "y_unit": "°C"}},
            solver=how, timings=timings, warnings=warnings,
            scalars={"march": run, "reference_C": inputs.reference_C, "analysis_warnings": [], "adaptive": adaptive},
        )
        radiated = radiation_summary(system, inputs, run.final)
        if radiated is not None:
            # What the faces radiate at the end of the run.
            result.scalars["radiation"] = radiated
        if ctx.assembly is not None:
            from cadgen._internal.fea.analyses.thermal import part_maxima

            result.scalars["part_max"] = part_maxima(ctx, run.node_peak)
            result.scalars["parts"] = ctx.assembly
        result.scalars["summary"] = self.summary(result, inputs, [])
        return result

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: TransientInputs) -> dict:
        run = result.scalars["march"]
        peak = kinds.field_max_over(
            run.node_peak, tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        when = float(run.node_peak_time[peak.node])
        times = [t for t, _ in run.frames]
        frame = min(range(len(times)), key=lambda i: (abs(times[i] - when), i))
        at = {"frame": frame, "value": round(when, 9), "unit": "s", "time_s": round(when, 9)}
        return temperature_check(check, peak.value, inputs.reference_C, at=peak.at, ref=peak.ref, faces=peak.faces,
                                 extra={"at": at})

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: TransientInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.thermal import temperature_findings

        found = temperature_findings(check_results, assembly=assembly)
        run = result.scalars["march"]
        if run.hottest_time >= inputs.end_s * (1 - 1e-9) and run.hottest > inputs.initial_C + 1e-6:
            last = run.curve_max[-2] if len(run.curve_max) > 1 else run.hottest
            found.append({
                "check": "fea", "severity": "info", "type": "still_heating",
                "summary": f"Still warming at the end ({run.hottest:.4g} °C at {time_label(inputs.end_s)}): "
                           "run longer to see where it settles, or solve it steady",
                "description": f"the hottest point rose {run.hottest - last:.3g} °C over the last step",
                "items": [],
            })
        return found

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: TransientInputs, check_results: list[dict]) -> dict:
        run = result.scalars["march"]
        hottest_state = result.frame_fields["temperature"][run.hottest_frame]
        hottest_node = int(hottest_state.argmax())
        temperatures = result.frame_fields["temperature"]
        summary = {
            "max_temperature_C": round(run.hottest, 4),
            "max_at_s": round(run.hottest_time, 9),
            "max_at_mm": [round(float(c), 3) for c in result.dof_locations[hottest_node]],
            "min_temperature_C": round(min(float(state.min()) for state in temperatures), 4),
            "final_max_temperature_C": round(float(run.final.max()), 4),
            "max_heat_flux_W_m2": round(max(float(flux.max()) for flux in result.frame_fields["heat_flux"]), 4),
            "initial_C": inputs.initial_C,
            "end_s": inputs.end_s,
            "step_s": round(inputs.first_step, 9),
            "steps": run.steps,
            "adaptive": result.scalars["adaptive"],
            "smallest_step_s": round(run.smallest_step, 9),
            "largest_step_s": round(run.largest_step, 9),
            "frames": len(run.frames),
            "reference_C": round(inputs.reference_C, 4),
        }
        if "radiation" in result.scalars:
            summary["radiation_at_end"] = result.scalars["radiation"]
        if "part_max" in result.scalars:
            plan = result.scalars["parts"]
            summary["parts"] = [
                {"ref": part.ref, "name": plan.names[i], "material": plan.materials[i].name,
                 "max_temperature_C": round(result.scalars["part_max"][i], 4)}
                for i, part in enumerate(plan.parts)
            ]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} temperature over time"

    def study_echo(self, inputs: TransientInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        return {**heat_echo(inputs, bare), "initial_C": inputs.initial_C, "end_s": inputs.end_s,
                "step_s": "auto" if inputs.step_s is None else inputs.step_s}

    def human_lines(self, summary: dict) -> list[str]:
        lines = [
            f"hottest {summary['max_temperature_C']:g} °C at {time_label(summary['max_at_s'])}, at {summary['max_at_mm']} mm; "
            f"{summary['final_max_temperature_C']:g} °C at the end",
            f"followed from {summary['initial_C']:g} °C for {time_label(summary['end_s'])} in {summary['steps']} "
            f"{'adaptive ' if summary['adaptive'] else ''}steps",
        ]
        if summary.get("radiation_at_end"):
            lines.append("at the end, " + radiation_line(summary["radiation_at_end"]))
        return lines
