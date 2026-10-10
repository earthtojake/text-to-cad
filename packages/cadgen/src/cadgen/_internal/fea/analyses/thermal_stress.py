"""Heat stress: the stress and movement a temperature field puts in a part, with any mechanical loads on top.

The study (spec 5.7) takes the thermal keys (``temperatures``, ``heat``,
``convection``, as a steady ``thermal`` study), ``fixtures`` and optional
``loads`` (as ``static``, gravity and acceleration included) and
``reference_C``, the temperature at which the part is stress-free (default
20 °C). The thermal analysis runs first on the same element space (its
``upstream``); its temperature T becomes the stress-free strain α (T - T_ref)
of a linear static solve (:func:`cadgen._internal.fea.solve.solve_linear_static`'s
``initial_strain``), whose stress is σ = C:(ε - α ΔT I).

Everything after the solve is static's: the stress and displacement checks,
the findings, the summary and the extras (this class is static's, with the
heat added), plus the ``temperature`` field and the temperatures in the
summary. The load control scales ΔT and the mechanical loads together, which
is exact because both act linearly. Stdlib only at import.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, SolveContext
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs, _solved, _solved_part
from cadgen._internal.fea.analyses.thermal import HEAT_KEYS, ThermalAnalysis, heat_echo
from cadgen._internal.fea.study import VIEW_DRIVES, parse_fixtures, parse_loads

__all__ = ["ThermalStressAnalysis", "ThermalStressInputs"]

#: The stress-free temperature when the study does not say: a room's.
REFERENCE_C = 20.0


@dataclass(frozen=True)
class ThermalStressInputs(StaticInputs):
    #: What the upstream thermal solve parsed of the same study.
    thermal: Any = None
    #: The temperature at which the part is stress-free, °C.
    reference_C: float = REFERENCE_C


class ThermalStressAnalysis(StaticAnalysis):
    name: ClassVar[str] = "thermal_stress"
    word: ClassVar[str] = "Heat stress"
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "reference_C", *HEAT_KEYS})
    material_needs: ClassVar[frozenset[str]] = frozenset({"conductivity", "expansion"})
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True),
    )
    drives: ClassVar[tuple[str, ...]] = VIEW_DRIVES
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "temperature"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ("thermal",)
    noun: ClassVar[str] = "this heat"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ThermalStressInputs:
        thermal = ThermalAnalysis().parse(document)
        fixtures = parse_fixtures(document)
        loads = parse_loads(document, required=False)
        reference = kinds.number(document.get("reference_C", REFERENCE_C), where="reference_C")
        refs = tuple(dict.fromkeys([*(ref for group in (*fixtures, *loads) for ref in group.faces), *thermal.face_refs]))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        needs = frozenset({"density"}) if any(load.body for load in loads) else frozenset()
        return ThermalStressInputs(refs, anchors, True, fixtures=fixtures, loads=loads, material_needs=needs,
                                   thermal=thermal, reference_C=reference)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: ThermalStressInputs):
        """The elastic solve (static's estimate) and the temperature solve before it, on the same mesh."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.thermal import ladder_estimate

        mechanical, heat = fit.solid_estimate(ctx), ladder_estimate(ctx)
        return fit.Estimate(dofs=mechanical.dofs, memory_bytes=max(mechanical.memory_bytes, heat.memory_bytes),
                            seconds=mechanical.seconds + heat.seconds)

    def symmetric_about(self, plane, inputs: ThermalStressInputs, ctx: SolveContext) -> bool:
        """Never yet: the temperatures are not solved on a half, so neither is their stress."""
        return False

    # -- solve ---------------------------------------------------------------------------------------

    def thermal_strain(self, ctx: SolveContext, temperature, reference: float):
        """α (T - T_ref) at the element space's quadrature points: (elements, quadrature), α per part."""
        from cadgen._internal.fea import operators

        space = ctx.space
        rise = space.scalar.interpolate(temperature - reference).value          # (elements, quadrature)
        alpha = operators.domain_values(space, [m.expansion for m in ctx.materials], space.scalar)
        return alpha * rise

    def solve(self, ctx: SolveContext, inputs: ThermalStressInputs) -> AnalysisResult:
        from cadgen._internal.fea import solve

        upstream = ctx.upstream.get("thermal")
        if upstream is None:  # solved on its own, outside run.py's upstream chaining
            upstream = ThermalAnalysis().solve(ctx, inputs.thermal)
            ctx.upstream["thermal"] = upstream
        temperature = upstream.fields["temperature"]
        volume, study, plan = ctx.volume, ctx.study, ctx.assembly
        materials = study.material if plan is None else plan.materials
        extra: dict[str, Any] = {"initial_strain": self.thermal_strain(ctx, temperature, inputs.reference_C), "space": ctx.space}
        if any(load.body for load in inputs.loads):
            extra["body_loads"] = inputs.body_accelerations
        solver = getattr(ctx.plan, "solver", None)
        if solver in ("iterative", "matrix_free"):
            extra["solver"] = solver
        outcome = solve.solve_linear_static(
            volume, materials, inputs.fixtures, inputs.surface_loads, ctx.ordinal_of, log=ctx.log, automatic=ctx.automatic, **extra
        )
        if plan is None:
            solved = [_solved(volume, outcome, study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
        else:
            solved = [_solved_part(volume, outcome, study, plan, index, ctx.ordinal_of, inputs.fixtures) for index in range(len(plan.parts))]
        result = self._result(outcome, solved, plan)
        result.fields["temperature"] = temperature
        result.scalars["reference_C"] = inputs.reference_C
        result.scalars["thermal"] = upstream.scalars.get("summary")
        result.timings.update({f"thermal_{key}": value for key, value in upstream.timings.items()})
        result.warnings = list(upstream.scalars.get("analysis_warnings", ())) + list(result.warnings)
        result.scalars["analysis_warnings"] = list(upstream.scalars.get("analysis_warnings", ()))
        return result

    # -- judging and findings ------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ThermalStressInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        found = []
        for finding in super().findings(ctx, result, inputs, check_results, assembly=assembly):
            if finding["type"] == "no_load":
                finding = {**finding, "summary": "Nothing stresses the part: its temperature stays at the stress-free "
                                                 f"{inputs.reference_C:g} °C and no load reaches it, or it is free to grow"}
            found.append(finding)
        thermal = result.scalars.get("thermal") or {}
        if thermal:
            hottest, coolest = thermal["max_temperature_C"], thermal["min_temperature_C"]
            rise = max(abs(hottest - inputs.reference_C), abs(coolest - inputs.reference_C))
            found.append({
                "check": "fea", "severity": "info", "type": "heated",
                "summary": f"Heated to {hottest:g} °C at most (coolest {coolest:g} °C), against a stress-free "
                           f"{inputs.reference_C:g} °C: up to {rise:.3g} °C of change drives the stress",
                "description": "the temperature comes from the thermal solve of the same study, on the same mesh",
                "items": [{"text": "the hottest point", "ref": None, "at": thermal["max_at_mm"]}],
            })
        return found

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: ThermalStressInputs, check_results: list[dict]) -> dict:
        summary = super().summary(result, inputs, check_results)
        temperature = result.fields["temperature"]
        checks = summary.pop("checks")
        summary.update({
            "max_temperature_C": round(float(temperature.max()), 4),
            "min_temperature_C": round(float(temperature.min()), 4),
            "reference_C": round(inputs.reference_C, 4),
            "checks": checks,
        })
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} heat stress"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {**super().field_ranges(summary, result),
                "temperature": (summary["min_temperature_C"], summary["max_temperature_C"])}

    def study_echo(self, inputs: ThermalStressInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        return {**super().study_echo(inputs, bare), **heat_echo(inputs.thermal, bare), "reference_C": inputs.reference_C}

    def human_lines(self, summary: dict) -> list[str]:
        factor = summary.get("safety_factor")
        lines = [
            f"max von Mises {summary['max_von_mises_MPa']:g} MPa at {summary['max_von_mises_at_mm']} mm "
            f"(yield {summary['yield_MPa']:g} MPa" + (f", safety factor {factor:g})" if factor is not None else ")"),
            f"max displacement {summary['max_displacement_mm']:g} mm at {summary['max_displacement_at_mm']} mm",
            f"temperatures {summary['min_temperature_C']:g} to {summary['max_temperature_C']:g} °C, "
            f"stress-free at {summary['reference_C']:g} °C",
        ]
        if any(summary["applied_force_N"]):
            lines.append(f"applied {summary['applied_force_N']} N, reactions {summary['reaction_force_N']} N")
        return lines
