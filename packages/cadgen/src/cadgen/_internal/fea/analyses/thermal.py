"""Heat: the steady temperature from faces held at a temperature, heat put in and air carrying it away.

The study (spec 5.5) names ``temperatures`` (faces held at °C), ``heat`` (a
total power in W spread evenly over its faces, or a flux in W/m²) and
``convection`` (a film coefficient in W/(m² K) and the ambient °C). At least
one held temperature or convection is required: a part only heated, with
nowhere for the heat to go, has no steady temperature. That is the anchor
rule, about the study, never about its size.

The solve is :mod:`cadgen._internal.fea.thermal_ops` on the study's element
space. It writes the ``temperature`` field (°C, signed: its colours run from
its own coolest) and the ``heat_flux`` magnitude (W/m²); nothing deforms. A
``temperature`` check judges the hottest point (over its faces, else the whole
part) against ``max_C``, measured from the coolest temperature the study sets
(``reference_C``). The heat in and out are summed per entry, and a balance
off by more than 1 % is a warning.

The parsing here is shared with ``thermal_transient`` (which adds schedules)
and ``thermal_stress`` (which solves this first). Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext

__all__ = [
    "Convection", "FixedTemperature", "HeatInput", "ThermalAnalysis", "ThermalInputs", "ladder_estimate", "parse_heat_keys",
    "temperature_check",
]

#: A heat balance off by more than this share is a warning.
BALANCE_WARN = 0.01
#: A temperature check is close once it has used this share of the room between the reference and its limit.
CLOSE_AT = 0.9
HEAT_KEYS = ("temperatures", "heat", "convection")


@dataclass(frozen=True)
class FixedTemperature:
    faces: tuple[str, ...]
    celsius: float
    #: ((t_s, factor), ...): a piecewise-linear schedule on the temperature (thermal_transient only).
    history: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class HeatInput:
    faces: tuple[str, ...]
    #: The total power over all of ``faces``, W; or None for a flux.
    watts: float | None = None
    #: A heat flux, W/m²; or None for a power.
    per_m2: float | None = None
    history: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Convection:
    faces: tuple[str, ...]
    h: float
    ambient: float
    history: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class ThermalInputs(Inputs):
    temperatures: tuple[FixedTemperature, ...] = ()
    heat: tuple[HeatInput, ...] = ()
    convection: tuple[Convection, ...] = ()
    #: The coolest temperature the study sets (held, ambient, the start): what a temperature check is measured from.
    reference_C: float = 20.0

    @property
    def heat_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref for group in (*self.temperatures, *self.heat, *self.convection) for ref in group.faces))


def _entries(document: dict, key: str, example: str) -> list:
    raw = document.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"study.{key}: expected a list like [{example}]")
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{key}[{index}]: expected an object like {example}")
    return raw


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def parse_history(entry: dict, where: str, *, allowed: bool) -> tuple[tuple[float, float], ...]:
    """An entry's ``history``: [[t_s, factor], ...], times rising from 0 or later. Only a transient study takes one."""
    if "history" not in entry:
        return ()
    if not allowed:
        raise ValueError(f"{where}.history: a schedule over time is for thermal_transient studies; a steady study has no time")
    raw = entry["history"]
    if not isinstance(raw, list) or not raw or not all(isinstance(point, list) and len(point) == 2 for point in raw):
        raise ValueError(f"{where}.history: the schedule as [[t_s, factor], ...], like [[0, 1], [300, 1], [301, 0]]")
    points = []
    for index, (t, factor) in enumerate(raw):
        t = kinds.number(t, where=f"{where}.history[{index}][0]")
        factor = kinds.number(factor, where=f"{where}.history[{index}][1]")
        if t < 0:
            raise ValueError(f"{where}.history[{index}]: times start at 0 s, got {t:g}")
        if points and not t > points[-1][0]:
            raise ValueError(f"{where}.history[{index}]: times must rise; {t:g} s is not after {points[-1][0]:g} s")
        points.append((t, factor))
    return tuple(points)


def parse_heat_keys(document: dict, *, transient: bool = False) -> tuple[tuple, tuple, tuple]:
    """The study's ``temperatures``, ``heat`` and ``convection``, each checked; ValueError names the field."""
    temperatures = []
    for index, entry in enumerate(_entries(document, "temperatures", '{"faces": ["#o1.f1"], "C": 25}')):
        where = f"temperatures[{index}]"
        _known(entry, {"faces", "C", "history"}, where, "a held temperature takes faces, C" + (" and history" if transient else ""))
        if "C" not in entry:
            raise ValueError(f"{where}.C: the temperature the faces are held at, in °C")
        celsius = kinds.number(entry["C"], where=f"{where}.C")
        if celsius < -273.15:
            raise ValueError(f"{where}.C: {celsius:g} °C is below absolute zero")
        temperatures.append(FixedTemperature(kinds.faces(entry, where=where), celsius,
                                             parse_history(entry, where, allowed=transient)))
    heat = []
    for index, entry in enumerate(_entries(document, "heat", '{"faces": ["#o1.f7"], "W": 15}')):
        where = f"heat[{index}]"
        _known(entry, {"faces", "W", "W_per_m2", "history"}, where,
               "heat takes faces and W (the total power) or W_per_m2 (a flux)" + (", and history" if transient else ""))
        given = [key for key in ("W", "W_per_m2") if key in entry]
        if len(given) != 1:
            raise ValueError(f"{where}: give W (the total power over its faces) or W_per_m2 (a heat flux), exactly one")
        value = kinds.number(entry[given[0]], where=f"{where}.{given[0]}")
        if value == 0:
            raise ValueError(f"{where}.{given[0]}: the heat is zero")
        faces = kinds.faces(entry, where=where)
        history = parse_history(entry, where, allowed=transient)
        heat.append(HeatInput(faces, value, None, history) if given[0] == "W" else HeatInput(faces, None, value, history))
    convection = []
    for index, entry in enumerate(_entries(document, "convection", '{"faces": ["#o1.f3"], "h_W_m2K": 10, "ambient_C": 25}')):
        where = f"convection[{index}]"
        _known(entry, {"faces", "h_W_m2K", "ambient_C", "history"}, where,
               "convection takes faces, h_W_m2K and ambient_C" + (" and history (on the ambient)" if transient else ""))
        if "h_W_m2K" not in entry:
            raise ValueError(f"{where}.h_W_m2K: how well the air or liquid carries heat off, in W/(m² K) "
                             "(still air about 5-10, a fan 25-100, water 500 or more)")
        if "ambient_C" not in entry:
            raise ValueError(f"{where}.ambient_C: the temperature of the air or liquid, in °C")
        h = kinds.number(entry["h_W_m2K"], where=f"{where}.h_W_m2K", positive=True)
        ambient = kinds.number(entry["ambient_C"], where=f"{where}.ambient_C")
        convection.append(Convection(kinds.faces(entry, where=where), h, ambient, parse_history(entry, where, allowed=transient)))
    return tuple(temperatures), tuple(heat), tuple(convection)


def reference_of(temperatures, convection, *extra: float) -> float:
    """The coolest temperature the study sets: held, ambient, or ``extra`` (a transient's start)."""
    values = [entry.celsius for entry in temperatures] + [entry.ambient for entry in convection] + list(extra)
    return min(values) if values else 20.0


def check_limits(document: dict, reference: float) -> None:
    """Each temperature check's ``max_C`` must sit above the reference; ValueError names it (spec 6)."""
    view = document.get("view")
    checks = view.get("checks") if isinstance(view, dict) else None
    if not isinstance(checks, list):
        return
    for index, check in enumerate(checks):
        if isinstance(check, dict) and check.get("kind") == "temperature":
            limit = check.get("max_C")
            if isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit) and limit <= reference:
                raise ValueError(
                    f"view.checks[{index}].max_C: {limit:g} °C is not above {reference:g} °C, the coolest temperature the "
                    "study sets, so the part could never pass; give the hottest it may get"
                )


def temperature_check(check: dict, value: float, reference: float, *, at, ref, faces, extra: dict | None = None) -> dict:
    """A temperature check's result: the hottest point against ``max_C``, measured from ``reference``.

    ratio = (T - reference) / (limit - reference): over 1 fails, past 0.9 is close.
    """
    from cadgen._internal.fea.checks import check_status

    limit = check["max_C"]
    ratio = (value - reference) / (limit - reference)
    return {
        "kind": "temperature",
        "label": check.get("label") or "Heat",
        "value": round(value, 4),
        "limit": limit,
        "unit": "°C",
        "ratio": round(ratio, 6),
        "close_at": CLOSE_AT,
        "status": check_status(ratio, CLOSE_AT),
        "where": {"ref": ref, "at": [round(c, 3) for c in at]},
        **({"faces": list(faces)} if faces else {}),
        "reference": round(reference, 4),
        **(extra or {}),
    }


def temperature_findings(check_results: list[dict], *, assembly: bool) -> list[dict]:
    """A finding for each temperature check that fails (an error) or is close (a warning), in plain words."""
    found = []
    for result in check_results:
        if result["kind"] != "temperature" or result["status"] == "passes":
            continue
        labelled = result["label"] != "Heat"
        subject = f"'{result['label']}'" if labelled else "The checked faces" if result.get("faces") else (
            "The assembly" if assembly else "The part")
        when = f" at {result['at']['value']:g} s" if isinstance(result.get("at"), dict) and "value" in result["at"] else ""
        if result["status"] == "fails":
            summary = (f"{subject} {'reach' if subject == 'The checked faces' else 'reaches'} {result['value']:.4g} °C{when}, "
                       f"hotter than the {result['limit']:g} °C allowed")
            severity, kind = "error", "temperature_over_limit"
        else:
            summary = (f"{subject} {'get' if subject == 'The checked faces' else 'gets'} to {result['value']:.4g} °C{when}, "
                       f"close to the {result['limit']:g} °C allowed")
            severity, kind = "warning", "temperature_close_to_limit"
        found.append({
            "check": "fea", "severity": severity, "type": kind, "summary": summary,
            "description": f"hottest {result['value']:.4g} °C against a {result['limit']:g} °C limit, "
                           f"measured from {result['reference']:g} °C: {result['ratio']:.2f} of the room used",
            "items": [{"text": "the hottest point", **result["where"]}],
        })
    return found


def heat_echo(inputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
    """``extras.study``'s ``temperatures``, ``heat`` and ``convection``, faces bare, each schedule where it has one."""
    def history(entry) -> dict:
        return {"history": [list(point) for point in entry.history]} if entry.history else {}

    return {
        "temperatures": [{"faces": bare(entry.faces), "C": entry.celsius, **history(entry)} for entry in inputs.temperatures],
        "heat": [{"faces": bare(entry.faces), **({"W": entry.watts} if entry.watts is not None else {"W_per_m2": entry.per_m2}),
                  **history(entry)} for entry in inputs.heat],
        "convection": [{"faces": bare(entry.faces), "h_W_m2K": entry.h, "ambient_C": entry.ambient, **history(entry)}
                       for entry in inputs.convection],
    }


def build_system(ctx: SolveContext, inputs):
    """The thermal system of ``inputs`` on the context's space, each entry on the facets of its faces."""
    from cadgen._internal.fea import thermal_ops

    space = ctx.space

    def facets(refs):
        return space.facets_of(refs, ctx.ordinal_of)

    return thermal_ops.assemble(
        space, list(ctx.materials),
        fixed=[(facets(entry.faces), entry.celsius, entry.history) for entry in inputs.temperatures],
        heat=[(facets(entry.faces), entry.watts, entry.per_m2, entry.history) for entry in inputs.heat],
        films=[(facets(entry.faces), entry.h, entry.ambient, entry.history) for entry in inputs.convection],
    )


def plan_solver(ctx: SolveContext) -> str | None:
    """The solver the ladder's plan chose (``iterative``), else None: by size."""
    solver = getattr(ctx.plan, "solver", None)
    return solver if solver in ("iterative", "matrix_free") else None


def space_result(space, fields: dict, **more) -> AnalysisResult:
    """An AnalysisResult on the space's nodes: its locations, elements and boundary, these fields, nothing deformed."""
    return AnalysisResult(
        dof_locations=space.dof_locations, vertices=space.vertices, tets=space.tets,
        boundary_quadratic=space.boundary_quadratic, element_dofs=space.element_dofs, fields=fields,
        dofs=int(space.scalar.N), **more,
    )


def part_maxima(ctx: SolveContext, values) -> list[float]:
    """An assembly's per-part maximum of a nodal field: each part's elements' nodes."""
    import numpy as np

    plan, volume = ctx.assembly, ctx.volume
    dofs = ctx.space.element_dofs
    return [float(values[np.unique(dofs[volume.domain == index])].max()) for index in range(len(plan.parts))]


def ladder_estimate(ctx: SolveContext, *, steps: int = 0, frames: int = 0):
    """The ladder's estimate of the plan's scalar (temperature) problem: one solve, and ``steps`` more on its matrix.

    fit.solid_estimate with one component a node. There is no matrix-free
    operator for the temperatures, so a matrix-free plan costs as the multigrid
    one (and the ladder never prefers it). A time march adds a solve a step on
    the factor or the hierarchy it already has, and keeps ``frames`` states of
    two fields.
    """
    from cadgen._internal.fea import fit

    plan = ctx.plan
    saved = plan.solver
    if saved == "matrix_free":
        plan.solver = "iterative"
    try:
        nodes = fit._plan_counts(ctx)[1]
        frame_bytes = 2 * 8.0 * nodes * frames
        base = fit.solid_estimate(ctx, components=1, extra_bytes=frame_bytes)
        n = base.dofs
        iterative = plan.solver == "iterative" or n >= fit.DIRECT_BELOW
        # A step: a pass over the factor (fill ~ n^1.5), or a few warm-started multigrid cycles.
        per_step = 0.3 * fit.AMG_SECONDS_PER_DOF * n if iterative else 4e-9 * fit.FILL * n ** 1.5 + 2e-7 * n
    finally:
        plan.solver = saved
    return fit.Estimate(dofs=base.dofs, memory_bytes=base.memory_bytes, seconds=base.seconds + steps * per_step)


class ThermalAnalysis:
    name: ClassVar[str] = "thermal"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Heat"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset(HEAT_KEYS)
    material_needs: ClassVar[frozenset[str]] = frozenset({"conductivity"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True),
        FieldSpec("heat_flux", "_HEAT_FLUX", "heat flux", "W/m²"),
    )
    checks: ClassVar[tuple] = (kinds.TEMPERATURE,)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["temperature", "heat_flux"]},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "defeature", "linear_elements", "symmetry")
    noun: ClassVar[str] = "this heat"
    #: What the ladder's two passes compare, in its words ("the hottest temperature moved 0.4% between ...").
    governing_word: ClassVar[str] = "the hottest temperature"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ThermalInputs:
        temperatures, heat, convection = parse_heat_keys(document)
        if not temperatures and not convection:
            raise ValueError(
                "study: a part only heated, with nowhere for the heat to go, has no steady temperature; add a "
                "'temperatures' entry (faces held at a temperature) or a 'convection' entry (air or liquid carrying heat away)"
            )
        reference = reference_of(temperatures, convection)
        check_limits(document, reference)
        refs = tuple(dict.fromkeys(ref for group in (*temperatures, *heat, *convection) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for group in (*temperatures, *convection) for ref in group.faces))
        return ThermalInputs(refs, anchors, True, temperatures=temperatures, heat=heat, convection=convection,
                             reference_C=reference)

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: ThermalInputs):
        return ladder_estimate(ctx)

    def apply(self, rung, ctx: SolveContext, inputs: ThermalInputs):
        """The shared solid rungs (fit.apply_generic). ``symmetry`` is skipped: there is no ``symmetric_about``
        yet, so the temperatures are never solved on a half and mirrored."""
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    def governing(self, result: AnalysisResult):
        """local_refine keeps the mesh fine where it is hottest; two passes compare the hottest temperature."""
        T = result.fields["temperature"]
        return T, float(T.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: ThermalInputs) -> AnalysisResult:
        import time

        from cadgen._internal.fea import thermal_ops

        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        system = build_system(ctx, inputs)
        timings["assemble_s"] = time.perf_counter() - started
        started = time.perf_counter()
        T, how = thermal_ops.solve_steady(system, warnings, solver=plan_solver(ctx))
        timings["solve_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"solved the temperatures with {how} in {timings['solve_s']:.1f}s")
        flux = thermal_ops.heat_flux(ctx.space, list(ctx.materials), T)
        balance = thermal_ops.heat_balance(system, T)
        analysis_warnings = []
        if balance["imbalance"] > BALANCE_WARN:
            analysis_warnings.append(
                f"the heat in ({balance['in_W']:.4g} W) and out ({balance['out_W']:.4g} W) differ by "
                f"{balance['imbalance']:.1%}: the solve did not settle; check the result with a finer mesh"
            )
        result = space_result(
            ctx.space, {"temperature": T, "heat_flux": flux}, solver=how, timings=timings,
            warnings=warnings + analysis_warnings,
            scalars={"balance": balance, "reference_C": inputs.reference_C, "analysis_warnings": analysis_warnings},
        )
        if ctx.assembly is not None:
            result.scalars["part_max"] = part_maxima(ctx, T)
            result.scalars["parts"] = ctx.assembly
        result.scalars["summary"] = self.summary(result, inputs, [])
        return result

    def needs_finer(self, result: AnalysisResult, inputs: ThermalInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: ThermalInputs) -> dict:
        peak = kinds.field_max_over(
            result.fields["temperature"], tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        return temperature_check(check, peak.value, inputs.reference_C, at=peak.at, ref=peak.ref, faces=peak.faces)

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ThermalInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        found = temperature_findings(check_results, assembly=assembly)
        balance = result.scalars["balance"]
        if balance["imbalance"] > BALANCE_WARN:
            found.append({
                "check": "fea", "severity": "warning", "type": "heat_balance",
                "summary": f"The heat in ({balance['in_W']:.4g} W) and out ({balance['out_W']:.4g} W) differ by "
                           f"{balance['imbalance']:.1%}: the temperatures may not have settled",
                "description": "the solve's residual leaves heat unaccounted for; a finer mesh or another solver should close it",
                "items": [],
            })
        if not inputs.heat and len({*(e.celsius for e in inputs.temperatures), *(e.ambient for e in inputs.convection)}) == 1:
            found.append({
                "check": "fea", "severity": "info", "type": "no_heat",
                "summary": f"No heat goes in, so the whole part sits at {inputs.reference_C:g} °C",
                "description": "every held temperature and ambient is the same and nothing heats it", "items": [],
            })
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        return None

    def summary(self, result: AnalysisResult, inputs: ThermalInputs, check_results: list[dict]) -> dict:
        T, flux = result.fields["temperature"], result.fields["heat_flux"]
        hottest = int(T.argmax())
        balance = result.scalars["balance"]
        summary = {
            "max_temperature_C": round(float(T.max()), 4),
            "min_temperature_C": round(float(T.min()), 4),
            "max_at_mm": [round(float(c), 3) for c in result.dof_locations[hottest]],
            "max_heat_flux_W_m2": round(float(flux.max()), 4),
            "heat_in_W": round(balance["in_W"], 6),
            "heat_out_W": round(balance["out_W"], 6),
            "heat_balance": round(balance["imbalance"], 6),
            "reference_C": round(inputs.reference_C, 4),
        }
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
        return f"{stem} temperature"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"temperature": (summary["min_temperature_C"], summary["max_temperature_C"]),
                "heat_flux": (0.0, summary["max_heat_flux_W_m2"])}

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": [{key: part[key] for key in ("ref", "name", "material", "max_temperature_C")} for part in summary["parts"]]}

    def study_echo(self, inputs: ThermalInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        return heat_echo(inputs, bare)

    def human_lines(self, summary: dict) -> list[str]:
        return [
            f"hottest {summary['max_temperature_C']:g} °C at {summary['max_at_mm']} mm, coolest {summary['min_temperature_C']:g} °C",
            f"heat in {summary['heat_in_W']:.4g} W, out {summary['heat_out_W']:.4g} W; "
            f"peak heat flow {summary['max_heat_flux_W_m2']:.4g} W/m²",
        ]
