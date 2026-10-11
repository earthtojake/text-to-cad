"""Flow and bending together (lite): steady two-way fluid-structure interaction.

The study is a flow study's ``flow`` (:mod:`.cfd`, spec 5.14: internal with
inlets and outlets on sides of the part's bounding box, or external with a
free stream, and the fluid) plus the part's own ``material`` and ``fixtures``,
as a static study gives them. Where :mod:`.cfd`'s ``map_to_structure`` pushes
the flow's wall pressure onto the part once (one-way), this lets the part's
bending change the flow and the flow's push change the bending, until they
agree:

1. solve the flow around the part as it stands (laminar :mod:`..navier_stokes`,
   or :mod:`..turbulence`'s k-omega SST past the laminar range; ``flow.regime``
   chooses, ``"auto"`` by the Reynolds number);
2. carry the wall pressure and the wall shear, face by face, onto the part's
   wetted faces as a traction (the first pass is the one-way answer);
3. solve the part's linear elastic bending under it, its fixtures held;
4. move the fluid mesh's wetted walls by the part's displacement (the P2 field
   on the part's surface, interpolated onto the fluid's wall nodes) and carry
   that into the fluid by a stiffened harmonic mesh-motion solve (ALE: small
   elements stiffer, so the thin gaps next to the part keep their shape);
5. solve the flow again on the moved mesh, and repeat, the displacement
   relaxed by Aitken's dynamic factor (or a fixed one, ``coupling.method``
   ``"fixed_point"``), until the displacement and the load each change by less
   than ``coupling.tolerance`` of themselves.

A run that does not settle in ``coupling.max_iterations`` is never refused: it
reports its last state as not converged, with the residual it reached. A run
whose coupling grows instead of settling is restarted once with the inflow
ramped up in steps (25 %, 50 %, 100 %) and a smaller first relaxation.

What comes out is on the part: the von Mises stress, the displacement (the
deformed shape), the wall pressure and wall shear at the settled state; in the
summary, the flow's numbers, the coupling's iterations and residual, and the
one-way answer beside it (how much the bending changed the deflection and the
pressure drop). Checks ``stress``, ``displacement`` and ``pressure_drop``.

Stdlib only at import.
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext
from cadgen._internal.fea.study import DEFAULT_CHECKS, Fixture, parse_fixtures

__all__ = ["FsiAnalysis", "FsiInputs", "LIMITS", "METHODS", "REGIMES", "not_converged_sentence"]

LIMITS = ("Steady flow two-way coupled to a linear elastic part: no flutter, vortex shedding or other unsteady "
          "motion; small-to-moderate deflection, the flow mesh following the part (ALE mesh motion).",)
#: The flow's regime: by the Reynolds number (laminar up to the cfd limit), or as the study says.
REGIMES = ("auto", "laminar", "turbulent")
#: The coupling's relaxation: Aitken's dynamic factor, or a fixed one.
METHODS = ("aitken", "fixed_point")
#: Coupling defaults: relative tolerance on the displacement and the load, iteration cap, first relaxation.
TOLERANCE, MAX_ITERATIONS, RELAXATION = 1e-3, 25, 1.0
#: Aitken's factor is kept in this range.
OMEGA_RANGE = (0.05, 1.5)
#: The ramp (the ladder's continuation, and the restart of a coupling that grows): shares of the inflow.
RAMP = (0.25, 0.5, 1.0)
#: An intermediate ramp stage settles to this many times the tolerance.
STAGE_LOOSEN = 10.0
#: The coupling is growing, not settling, when its residual rises this many iterations running.
GROWING = 3
#: A relaxed step that folds the flow mesh is halved at most this many times.
BACKTRACK = 4
#: The cost model: coupling iterations expected, and a structural re-solve's share of its first solve.
EXPECTED_ITERATIONS, RESOLVE_SHARE = 4.0, 0.15
#: The whole coupling's time: this many times the study's time target (at least the default one) before it stops at
#: its last state and says so; each flow solve may take what is left of it, and at least FLOW_FLOOR_S.
COUPLING_BUDGET, FLOW_FLOOR_S = 2.0, 30.0
#: Engine units: MPa -> Pa, m/s -> mm/s.
PASCAL, SPEED = 1e6, 1000.0
#: A check is close once its value passes this share of its limit (pressure drop).
CLOSE_AT = 0.9


def not_converged_sentence(iterations: int, residual: float, tolerance: float) -> str:
    """The plain words for a coupling that did not settle, the same everywhere."""
    return (f"the flow and the bending did not settle in {iterations} coupling iterations (they still changed by "
            f"{residual:.1e} of themselves, short of {tolerance:.0e}): this is the last state, not a converged answer")


def budget_sentence(seconds: float) -> str:
    """The plain words for a coupling stopped by its time budget."""
    return (f"the coupling stopped at its time budget ({seconds:.0f} s, twice the study's time target or the default): a flow solve "
            "that does not settle, or a slow one, used it; raise fit.seconds, coarsen the flow mesh, or check the "
            "flow's regime")


@dataclass(frozen=True)
class FsiInputs(Inputs):
    #: The flow, as cfd (or cfd_turbulent) parses it, not mapped onto a structure.
    flow: Any = None
    #: "auto", "laminar" or "turbulent".
    regime: str = "auto"
    fixtures: tuple[Fixture, ...] = ()
    method: str = "aitken"
    relaxation: float = RELAXATION
    tolerance: float = TOLERANCE
    max_iterations: int = MAX_ITERATIONS


def _known(entry: dict, keys: set[str], where: str, words: str) -> None:
    unknown = set(entry) - keys
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; {words}")


def _coupling(raw: Any) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('coupling: expected an object like {"method": "aitken", "tolerance": 0.001, "max_iterations": 25}')
    _known(raw, {"method", "relaxation", "tolerance", "max_iterations"}, "coupling",
           "it takes method (\"aitken\" or \"fixed_point\"), relaxation, tolerance and max_iterations")
    out: dict[str, Any] = {}
    if "method" in raw:
        if raw["method"] not in METHODS:
            raise ValueError(f"coupling.method: {kinds.json_text(raw['method'])} is not one of {list(METHODS)}")
        out["method"] = raw["method"]
    if "relaxation" in raw:
        value = kinds.number(raw["relaxation"], where="coupling.relaxation", positive=True)
        if value > 1.5:
            raise ValueError(f"coupling.relaxation: the share of each new displacement taken, 0 to 1.5; got {value:g}")
        out["relaxation"] = value
    if "tolerance" in raw:
        value = kinds.number(raw["tolerance"], where="coupling.tolerance", positive=True)
        if value >= 0.5:
            raise ValueError(f"coupling.tolerance: the relative change to stop at, like 0.001; got {value:g}")
        out["tolerance"] = value
    if "max_iterations" in raw:
        value = raw["max_iterations"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 200:
            raise ValueError(f"coupling.max_iterations: a whole number from 1 to 200; got {kinds.json_text(value)}")
        out["max_iterations"] = value
    return out


def _at_speed(flow, share: float):
    """The flow inputs with every inflow speed times ``share``."""
    if share == 1.0:
        return flow
    if flow.kind == "external":
        return dataclasses.replace(flow, velocity_m_s=tuple(share * c for c in flow.velocity_m_s))
    return dataclasses.replace(flow, inlets=tuple(dataclasses.replace(i, velocity_m_s=share * i.velocity_m_s) for i in flow.inlets))


@contextlib.contextmanager
def _fluid_plan(ctx):
    """The plan as the flow reads it: local_refine's coarse pass coarsens the part alone, so the flow keeps the
    size the study asked for (its walls are where its numbers are set)."""
    plan = ctx.plan
    if plan is None or plan.refine_to_mm is None:
        yield
        return
    saved = plan.size_mm
    plan.size_mm = plan.refine_to_mm
    try:
        yield
    finally:
        plan.size_mm = saved


def _speed_words(flow) -> str:
    if flow.kind == "external":
        return f"{math.sqrt(sum(c * c for c in flow.velocity_m_s)):.3g} m/s"
    return f"{max(i.velocity_m_s for i in flow.inlets):.3g} m/s"


class FsiAnalysis:
    name: ClassVar[str] = "fsi"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Flow and bending"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"flow", "fixtures", "coupling"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("pressure", "_PRESSURE", "wall pressure", "Pa", signed=True),
        FieldSpec("wall_shear", "_WALL_SHEAR", "wall shear stress", "Pa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT, kinds.PRESSURE_DROP)
    default_checks: ClassVar[tuple[dict, ...]] = DEFAULT_CHECKS
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "pressure", "wall_shear", "displacement"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("continuation", "iterative", "fluid_coarsen", "local_refine")
    noun: ClassVar[str] = "this flow"
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> FsiInputs:
        from cadgen._internal.fea.analyses import get_analysis

        flow = document.get("flow")
        regime = "auto"
        if isinstance(flow, dict) and "regime" in flow:
            flow = dict(flow)
            regime = flow.pop("regime")
            if regime not in REGIMES:
                raise ValueError(f"flow.regime: {kinds.json_text(regime)} is not one of {list(REGIMES)} "
                                 "(auto: laminar up to Re 2000 in a pipe or Re 1000 around a body, turbulent past it)")
        if regime == "laminar" and isinstance(flow, dict) and ("turbulence_intensity" in flow or any(
                isinstance(inlet, dict) and "turbulence_intensity" in inlet for inlet in flow.get("inlets") or ())):
            raise ValueError("flow.turbulence_intensity: a laminar flow has no turbulence; leave it out, or set "
                             "flow.regime to \"turbulent\" or \"auto\"")
        # cfd_turbulent's parser reads the laminar flow's keys and each inlet's turbulence_intensity.
        parsed = get_analysis("cfd_turbulent").parse({"flow": flow})
        fixtures = parse_fixtures(document)
        coupling = _coupling(document.get("coupling"))
        refs = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        return FsiInputs(refs, refs, True, flow=parsed, regime=regime, fixtures=fixtures, **coupling)

    # -- the flow model ------------------------------------------------------------------------------

    def _engine_name(self, ctx: SolveContext, inputs: FsiInputs) -> str:
        if inputs.regime != "auto":
            return "cfd" if inputs.regime == "laminar" else "cfd_turbulent"
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.analyses.cfd import RE_LIMIT

        setup = get_analysis("cfd").setup_of(ctx, inputs.flow)
        return "cfd" if setup.reynolds <= RE_LIMIT[inputs.flow.kind] else "cfd_turbulent"

    def engine(self, ctx: SolveContext, inputs: FsiInputs):
        """The flow analysis that solves this study's flow: ``cfd`` (laminar) or ``cfd_turbulent``."""
        from cadgen._internal.fea.analyses import get_analysis

        return get_analysis(self._engine_name(ctx, inputs))

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: FsiInputs):
        from cadgen._internal.fea import fit

        with _fluid_plan(ctx):
            flow = self.engine(ctx, inputs).estimate(ctx, inputs.flow)
        structure = fit.solid_estimate(ctx)
        iterations = EXPECTED_ITERATIONS
        seconds = iterations * flow.seconds + structure.seconds * (1.0 + RESOLVE_SHARE * iterations)
        # The mesh motion: one scalar factorisation on the fluid's nodes, about a third of a flow solve's.
        seconds += 0.3 * flow.seconds
        memory = max(flow.memory_bytes, structure.memory_bytes)
        return fit.Estimate(dofs=int(flow.dofs + structure.dofs), memory_bytes=int(memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: FsiInputs):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.analyses.cfd import CONTINUE_FROM

        plan = ctx.plan
        engine = self.engine(ctx, inputs)
        if rung == "continuation":
            setup = get_analysis("cfd").setup_of(ctx, inputs.flow)
            if setup.reynolds <= CONTINUE_FROM or "continuation" in plan.taken:
                return None
            inner = engine.apply("continuation", ctx, inputs.flow)
            shares = ", ".join(f"{100 * share:.0f}%" for share in RAMP)
            words = (f"Ramped the inflow up in steps ({shares} of {_speed_words(inputs.flow)}), settling the flow and the "
                     "bending at each, so every stage starts near its answer")
            if inner is not None and plan.re_schedule:
                words += f"; each flow solve reaches Re {setup.reynolds:.0f} by continuation"
            return fit.Step("continuation", words, None, None,
                            detail={"ramp": list(RAMP), "reynolds": round(setup.reynolds, 2),
                                    **({"schedule": [round(re, 2) for re in plan.re_schedule]} if plan.re_schedule else {})})
        if rung == "iterative":
            if plan.solver != "direct":
                return None
            budget = ctx.budget
            before = self.estimate(ctx, inputs)
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            memory = before.memory_bytes > budget.memory_bytes
            saves = after.memory_bytes < 0.95 * before.memory_bytes if memory else after.seconds < 0.95 * before.seconds
            if not saves:
                plan.solver = "direct"
                return None
            why = "fit in memory" if memory else "finish sooner"
            return fit.Step("iterative", f"Used iterative solvers (Krylov with multigrid) for the flow and the bending to {why}",
                            None, None, detail={"solver": "iterative", "from_bytes": int(before.memory_bytes),
                                                "to_bytes": int(after.memory_bytes)})
        if rung == "fluid_coarsen":
            with _fluid_plan(ctx):
                return engine.apply("fluid_coarsen", ctx, inputs.flow)
        if rung == "local_refine":
            # Two passes of the whole coupling pay only where the part's own solve is most of the cost.
            with _fluid_plan(ctx):
                flow = engine.estimate(ctx, inputs.flow)
            if fit.solid_estimate(ctx).seconds * (1.0 + RESOLVE_SHARE * EXPECTED_ITERATIONS) < EXPECTED_ITERATIONS * flow.seconds:
                return None
            return fit.apply_generic("local_refine", self, ctx, inputs)
        return None

    def governing(self, result: AnalysisResult):
        """local_refine follows the part's stress; two passes compare its peak."""
        return result.fields["von_mises"], float(result.fields["von_mises"].max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: FsiInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import fluid_domain
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.analyses.cfd import RE_LIMIT, flow_numbers, reynolds_sentence, wall_to_part
        from cadgen._internal.fea.analyses.cfd_turbulent import laminar_sentence
        from cadgen._internal.fea.femspace import FemSpace

        timings: dict[str, float] = {}
        name = self._engine_name(ctx, inputs)
        engine = get_analysis(name)
        turbulent = name == "cfd_turbulent"
        material = ctx.study.material if ctx.study is not None else ctx.materials[0]
        setup = get_analysis("cfd").setup_of(ctx, inputs.flow)   # the same fluid region for either model
        domain = setup.domain
        timings["fluid_domain_s"] = domain.seconds
        with _fluid_plan(ctx):
            wall, far = engine.sizes(ctx, setup)
        if ctx.log:
            ctx.log(f"meshing the {domain.kind} flow region at {wall:.3g} mm" + (f" (free stream {far:.3g} mm)" if far > wall else ""))
        started = time.perf_counter()
        fluid = fluid_domain.mesh_fluid(domain, wall, far)
        reference = FemSpace.build(fluid, 2)
        timings["fluid_mesh_s"] = time.perf_counter() - started

        started = time.perf_counter()
        face_of = {face.index: face for face in domain.faces}
        row_kind = np.array([face_of[int(o)].kind if int(o) in face_of else "wall" for o in fluid.boundary_ordinal])
        coupling = Coupling(ctx, inputs, engine, turbulent, setup, fluid, reference, face_of, row_kind, material)
        timings["coupling_setup_s"] = time.perf_counter() - started

        state = coupling.run()
        timings.update({k: v for k, v in coupling.timings.items()})

        started = time.perf_counter()
        final = state.flow_state
        post = flow_numbers(final.space, fluid, face_of, row_kind, final.flow, inputs.flow)
        if turbulent:
            engine.wall_function_shear(final.space, row_kind, final.flow, post, inputs.flow.fluid.density_kg_m3 * 1e-12)
        pressure, shear = wall_to_part(ctx, reference, fluid, face_of, row_kind, post)
        one_way_post = coupling.one_way_post
        timings["post_s"] = time.perf_counter() - started

        warnings = list(final.flow.warnings)
        analysis_warnings: list[str] = []
        limit = RE_LIMIT[inputs.flow.kind]
        reynolds = {"value": float(f"{setup.reynolds:.4g}"), "limit": limit, "kind": inputs.flow.kind,
                    "length_mm": round(setup.length_mm, 4), "laminar": setup.reynolds <= limit}
        if not turbulent and setup.reynolds > limit:
            analysis_warnings.append(reynolds_sentence(setup.reynolds, limit))
        if turbulent and setup.reynolds < limit:
            analysis_warnings.append(laminar_sentence(setup.reynolds, limit))
        if not state.converged:
            # Said once as a finding (coupling_not_converged) and in extras.analysis.warnings, not again as a warning.
            analysis_warnings.append(not_converged_sentence(state.iterations, state.residual, inputs.tolerance))
        if coupling.out_of_time:
            analysis_warnings.append(budget_sentence(coupling.budget_s))
        if state.inverted:
            sentence = (f"the moved flow mesh folded over ({state.inverted} elements) at the deflection the coupling "
                        "reached: the deflection is too large for this mesh motion; the last unfolded state is reported")
            analysis_warnings.append(sentence)
            warnings.append(sentence)

        outcome = state.outcome
        fields = {"von_mises": outcome.von_mises, "pressure": pressure, "wall_shear": shear, "displacement": outcome.displacement}
        from cadgen._internal.fea.analyses.static import solved_record

        study = _StudyView(material, getattr(ctx.study, "margin", 2.0) if ctx.study is not None else 2.0)
        solved = [solved_record(ctx.volume, outcome, study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
        regime = "turbulent" if turbulent else "laminar"
        result = AnalysisResult(
            dof_locations=ctx.space.dof_locations, vertices=ctx.space.vertices, tets=ctx.space.tets,
            boundary_quadratic=ctx.space.boundary_quadratic, element_dofs=ctx.space.element_dofs, fields=fields,
            deformation=outcome.displacement, reactions=list(outcome.reactions), applied=tuple(outcome.applied),
            dofs=int(final.space.basis.N + final.flow.pressure_basis.N + outcome.dofs),
            solver=(f"partitioned two-way coupling ({state.method}), "
                    f"{'Taylor-Hood RANS k-omega SST' if turbulent else 'Taylor-Hood P2/P1 Navier-Stokes'}, "
                    f"linear elastic P2 tets, harmonic ALE mesh motion"),
            timings=timings, warnings=warnings, solved=solved,
            scalars={
                "post": post, "one_way_post": one_way_post, "reynolds": reynolds, "flow": final.flow, "regime": regime,
                "state": state, "outcome": outcome, "one_way": coupling.one_way, "yield_MPa": material.yield_strength,
                "wall_mm": wall, "far_mm": far,
                "fluid_mesh": {"elements": int(len(fluid.tets)), "nodes": int(len(fluid.nodes)),
                               "wall_size_mm": round(wall, 4), "far_size_mm": round(far, 4)},
                "analysis_warnings": analysis_warnings,
                "analysis_extras": {
                    "regime": regime,
                    **({"reynolds": reynolds} if not turbulent else {}),
                    "coupling": {"iterations": state.iterations, "converged": state.converged,
                                 "residual": float(f"{state.residual:.3g}"), "tolerance": inputs.tolerance,
                                 "method": state.method},
                },
            },
        )
        return result

    def needs_finer(self, result: AnalysisResult, inputs: FsiInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: FsiInputs) -> dict:
        from cadgen._internal.fea.analyses import get_analysis

        if check["kind"] in ("stress", "displacement"):
            return get_analysis("static").judge(check, index, ctx, result, inputs)
        return get_analysis("cfd").judge(check, index, ctx, result, inputs)

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: FsiInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.cfd import reynolds_sentence
        from cadgen._internal.fea.analyses.cfd_turbulent import laminar_sentence

        found: list[dict] = list(checks.findings(result.solved[0]))
        state = result.scalars["state"]
        if not state.converged:
            found.append({
                "check": "fea", "severity": "warning", "type": "coupling_not_converged",
                "summary": "T" + not_converged_sentence(state.iterations, state.residual, inputs.tolerance)[1:],
                "description": "raise coupling.max_iterations, lower coupling.relaxation, or ramp the flow (a slower flow first)",
                "items": [],
            })
        if state.ramped:
            found.append({
                "check": "fea", "severity": "info", "type": "coupling_ramped",
                "summary": "The coupling grew instead of settling from rest at full speed, so the inflow was ramped up in steps "
                           f"({', '.join(f'{100 * s:.0f}%' for s in RAMP)}) with a smaller first relaxation",
                "description": "the steady answer is the same; it was reached in stages", "items": [],
            })
        reynolds = result.scalars["reynolds"]
        turbulent = result.scalars["regime"] == "turbulent"
        if not turbulent and not reynolds["laminar"]:
            found.append({"check": "fea", "severity": "warning", "type": "reynolds_past_laminar",
                          "summary": reynolds_sentence(reynolds["value"], reynolds["limit"]),
                          "description": "the study asked for the laminar model (flow.regime); \"auto\" would solve it turbulent",
                          "items": []})
        if turbulent and reynolds["laminar"]:
            found.append({"check": "fea", "severity": "warning", "type": "reynolds_laminar_range",
                          "summary": laminar_sentence(reynolds["value"], reynolds["limit"]),
                          "description": "the study asked for the turbulent model (flow.regime); \"auto\" would solve it laminar",
                          "items": []})
        for check in check_results:
            if check["kind"] != "pressure_drop" or check["status"] == "passes":
                continue
            value = f"{check['value']:.4g} {check['unit']}"
            fails = check["status"] == "fails"
            found.append({
                "check": "fea", "severity": "error" if fails else "warning",
                "type": f"pressure_drop_{'over_limit' if fails else 'close_to_limit'}",
                "summary": f"The pressure drop is {value}, {'over' if fails else 'close to'} the {check['limit']:g} {check['unit']} allowed",
                "description": f"pressure drop {value} against a {check['limit']:g} {check['unit']} limit ({check['ratio']:.2f} of it)",
                "items": [{"text": "the pressure drop", **check["where"]}],
            })
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
        return requested or auto_deformation_scale(float(magnitude.max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: FsiInputs, check_results: list[dict]) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import floored

        post, flow, reynolds = result.scalars["post"], result.scalars["flow"], result.scalars["reynolds"]
        state, one_way, outcome = result.scalars["state"], result.scalars["one_way"], result.scalars["outcome"]
        one_post = result.scalars["one_way_post"]
        wet = post["wetted_nodes"]
        pressure, shear = result.fields["pressure"], result.fields["wall_shear"]
        magnitude = np.linalg.norm(outcome.displacement, axis=1)
        solved = result.solved[0]
        fluid = inputs.flow.fluid
        two_drop, one_drop = post["pressure_drop_Pa"], one_post["pressure_drop_Pa"]
        two_move, one_move = float(magnitude.max()), one_way["max_displacement_mm"]

        def change(two: float, one: float) -> float | None:
            return round(100.0 * (two - one) / abs(one), 4) if one else None

        summary: dict[str, Any] = {
            "flow_kind": inputs.flow.kind,
            "flow_regime": result.scalars["regime"],
            "fluid": {"name": fluid.name, "density_kg_m3": fluid.density_kg_m3, "viscosity_Pa_s": fluid.viscosity_Pa_s},
            "reynolds": dict(reynolds),
            "max_velocity_m_s": round(post["max_velocity_m_s"], 6),
            "flow_rate_m3_s": float(f"{post['flow_rate_m3_s']:.6g}"),
            "flow_rate_L_min": round(post["flow_rate_m3_s"] * 60000.0, 6),
            "pressure_drop_Pa": round(two_drop, 6),
            "inlet_pressure_Pa": round(post["inlet_pressure_Pa"], 6),
            "outlet_pressure_Pa": round(post["outlet_pressure_Pa"], 6),
            "max_wall_pressure_Pa": round(float(pressure[wet].max()), 6) if len(wet) else 0.0,
            "min_wall_pressure_Pa": round(float(pressure[wet].min()), 6) if len(wet) else 0.0,
            "max_wall_shear_Pa": round(float(shear[wet].max()), 6) if len(wet) else 0.0,
            "force_N": [round(float(c), 9) for c in post["force_N"]],
            "max_von_mises_MPa": round(float(outcome.von_mises.max()), 4),
            "max_von_mises_at_mm": [round(c, 3) for c in solved.peak_at],
            "yield_MPa": solved.yield_MPa,
            "max_displacement_mm": round(two_move, 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in outcome.dof_locations[int(magnitude.argmax())]],
            "safety_factor": floored(checks.safety_factor(solved)),
            "coupling": {
                "method": state.method, "iterations": state.iterations, "converged": state.converged,
                "residual": float(f"{state.residual:.3g}"), "load_change": float(f"{state.load_change:.3g}"),
                "tolerance": inputs.tolerance, "max_iterations": inputs.max_iterations,
                "relaxation": [round(w, 4) for w in state.relaxations], "history": [float(f"{r:.3g}") for r in state.history],
                "ramped": state.ramped, "flow_solves": state.flow_solves,
            },
            "one_way": {
                "max_displacement_mm": round(one_move, 6), "max_von_mises_MPa": round(one_way["max_von_mises_MPa"], 4),
                "pressure_drop_Pa": round(one_drop, 6), "force_N": [round(float(c), 9) for c in one_post["force_N"]],
            },
            "two_way_vs_one_way": {
                "displacement_change_pct": change(two_move, one_move),
                "pressure_drop_change_pct": change(two_drop, one_drop),
                "pressure_drop_change_Pa": round(two_drop - one_drop, 6),
            },
            "fluid_mesh": dict(result.scalars["fluid_mesh"]),
            "deformation_scale": result.scalars.get("deformation_scale"),
        }
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} flow and bending"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"von_mises": (0.0, summary["max_von_mises_MPa"]),
                "pressure": (summary["min_wall_pressure_Pa"], summary["max_wall_pressure_Pa"]),
                "wall_shear": (0.0, summary["max_wall_shear_Pa"]),
                "displacement": (0.0, summary["max_displacement_mm"])}

    def extras_head(self, summary: dict) -> dict:
        return {"safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: FsiInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        from cadgen._internal.fea.analyses import get_analysis

        flow = get_analysis("cfd").study_echo(inputs.flow, bare)["flow"]
        flow["regime"] = inputs.regime
        return {
            "flow": flow,
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "loads": [],
            "coupling": {"method": inputs.method, "relaxation": inputs.relaxation, "tolerance": inputs.tolerance,
                         "max_iterations": inputs.max_iterations},
        }

    def human_lines(self, summary: dict) -> list[str]:
        reynolds, coupling = summary["reynolds"], summary["coupling"]
        versus = summary["two_way_vs_one_way"]
        one = summary["one_way"]
        lines = [
            f"{summary['flow_kind']} {summary['flow_regime']} flow of {summary['fluid']['name']}: Re {reynolds['value']:.4g}, "
            f"coupled two ways with the part's bending",
            f"coupling: {coupling['iterations']} iterations ({coupling['method']}), "
            + (f"converged to {coupling['residual']:.1e}" if coupling["converged"]
               else f"NOT converged (last change {coupling['residual']:.1e}, tolerance {coupling['tolerance']:.0e})"),
            f"largest displacement {summary['max_displacement_mm']:.4g} mm (one-way {one['max_displacement_mm']:.4g} mm"
            + (f", {versus['displacement_change_pct']:+.3g}%" if versus["displacement_change_pct"] is not None else "") + ")",
            f"pressure drop {summary['pressure_drop_Pa']:.4g} Pa (one-way {one['pressure_drop_Pa']:.4g} Pa"
            + (f", {versus['pressure_drop_change_pct']:+.3g}%" if versus["pressure_drop_change_pct"] is not None else "")
            + f"), flow {summary['flow_rate_L_min']:.4g} L/min",
            f"peak von Mises {summary['max_von_mises_MPa']:.4g} MPa"
            + (f", safety factor {summary['safety_factor']:g}" if summary.get("safety_factor") is not None else ""),
        ]
        return lines


@dataclass(frozen=True)
class _StudyView:
    """What :func:`..static.solved_record` reads of a study: the material and the margin."""

    material: Any
    margin: float


# -- the coupling ------------------------------------------------------------------------------------


@dataclass
class FlowState:
    """One flow solve on the moved mesh: its space, its solution and the traction it puts on each wetted row."""

    space: Any
    flow: Any
    traction: Any          # (fluid wall rows, 3) MPa, on the part (pushing it)
    force: Any             # (3,) N, the total
    #: (fluid wall rows,) MPa: the pressure part of the traction, a scalar, which the part takes along its own normal.
    pressure: Any = None
    #: (fluid wall rows, 3) MPa: the rest of the traction: the shear, and the pressure's turn as the wall moved.
    shear: Any = None


@dataclass
class CouplingState:
    outcome: Any
    flow_state: FlowState
    converged: bool
    iterations: int
    residual: float
    load_change: float
    method: str
    history: list
    relaxations: list
    ramped: bool
    flow_solves: int
    inverted: int = 0


class Coupling:
    """The partitioned iteration: flow on the moved mesh, traction onto the part, bending, mesh motion, relaxation."""

    def __init__(self, ctx, inputs: FsiInputs, engine, turbulent: bool, setup, fluid, reference, face_of, row_kind, material):
        import numpy as np

        from cadgen._internal.fea.femspace import element_mesh

        self.ctx, self.inputs, self.engine, self.turbulent, self.setup = ctx, inputs, engine, turbulent, setup
        self.fluid, self.reference, self.face_of, self.row_kind = fluid, reference, face_of, row_kind
        self.material = material
        self.timings: dict[str, float] = {"flow_s": 0.0, "structure_s": 0.0, "mesh_motion_s": 0.0}
        self.flow_solves = 0
        _, self.node_to_dof = element_mesh(fluid, 2)
        self.solver = "iterative" if ctx.plan is not None and ctx.plan.solver == "iterative" else "direct"
        # The fluid's wall rows that are the part's faces, and their part ordinals.
        ordinal_of_row = np.array([face_of[int(o)].ordinal if int(o) in face_of else 0 for o in fluid.boundary_ordinal])
        self.wall_rows = np.flatnonzero(row_kind == "wall")
        self.wall_ordinal = ordinal_of_row[self.wall_rows]
        self.structure = Structure(ctx.space, ctx.volume, material, inputs.fixtures, ctx.ordinal_of, self.solver)
        self.interface = Interface(ctx.space, ctx.volume, reference, self.wall_rows, self.wall_ordinal)
        self.motion = MeshMotion(reference, fluid, row_kind, face_of, self.interface.fluid_nodes)
        self.one_way: dict = {}
        self.one_way_post: dict = {}
        # The time the coupling may take: each flow solve stops at what is left of it (a solve that cannot settle,
        # a laminar flow past a flap at Re 1600, once ran over an hour with no output), and no new iteration starts
        # once it is spent.
        from cadgen._internal.fea import fit

        budget = getattr(ctx, "budget", None)
        # A time target is what the ladder fits to, never a refusal: a small one does not cut the coupling short.
        self.budget_s = COUPLING_BUDGET * max(float(getattr(budget, "seconds", 0.0) or 0.0), fit.DEFAULT_SECONDS)
        self.began = time.perf_counter()
        self.out_of_time = False

    def left_s(self) -> float:
        """Seconds of the coupling's budget left."""
        return self.budget_s - (time.perf_counter() - self.began)

    def flow_log(self, line: str) -> None:
        if self.ctx.log:
            self.ctx.log(f"flow solve {self.flow_solves + 1}: {line}")

    # -- one flow solve ------------------------------------------------------------------------------

    def flow_at(self, displacement, share: float) -> "FlowState | int":
        """The flow with the part displaced by ``displacement`` (part scalar nodes, 3) at ``share`` of the inflow.
        An int (how many elements folded) when the moved mesh folds over."""
        import time

        import numpy as np

        from cadgen._internal.fea import navier_stokes, turbulence
        from cadgen._internal.fea.analyses.cfd_turbulent import MARCH, MARCH_FAST
        from cadgen._internal.fea.femspace import FemSpace

        started = time.perf_counter()
        wall = self.interface.to_fluid(displacement)
        moved_nodes = self.motion.extend(wall)
        nodes = self.fluid.nodes + moved_nodes[self.node_to_dof]
        folded = _folded(nodes, self.fluid.tets)
        self.timings["mesh_motion_s"] += time.perf_counter() - started
        if folded:
            return folded
        volume = dataclasses.replace(self.fluid, nodes=nodes)
        space = FemSpace.build(volume, 2)
        started = time.perf_counter()
        flow_inputs = _at_speed(self.inputs.flow, share)
        problem = self.engine.problem_of(space, volume, self.face_of, self.row_kind, flow_inputs, self.setup)
        plan = self.ctx.plan
        if self.turbulent:
            march = MARCH_FAST if plan is not None and "continuation" in plan.taken else MARCH
            flow = turbulence.solve_rans(problem, solver=self.solver, cfl=march, log=self.flow_log)
        else:
            reynolds = self.setup.reynolds * share
            schedule = tuple(min(1.0, re / reynolds) for re in plan.re_schedule if re <= reynolds * 1.0000001) \
                if plan is not None and plan.re_schedule and reynolds > 0 else ()
            if schedule and schedule[-1] < 1.0:
                schedule = (*schedule, 1.0)
            flow = navier_stokes.solve_flow(problem, schedule=schedule, solver=self.solver, log=self.flow_log,
                                            deadline_s=max(FLOW_FLOOR_S, self.left_s()))
            if flow.timed_out:
                self.out_of_time = True
        self.flow_solves += 1
        self.timings["flow_s"] += time.perf_counter() - started
        traction = self.traction(space, flow)
        force = (traction * self.interface.fluid_area[:, None]).sum(axis=0)
        pressure = self.wall_pressure(space, flow)
        # Split along the wall's normal at rest: what the wall has turned since (a leaning flap's pressure, turned with
        # it) stays in the rest, so the part still feels its pressure follow the bent wall.
        shear = traction - pressure[:, None] * self.interface.fluid_normal
        return FlowState(space, flow, traction, force, pressure, shear)

    def traction(self, space, flow):
        """(wall rows, 3) MPa: the fluid's push on the part over each wetted wall triangle, its mean over the
        triangle's mid-edge nodes (the quadratic triangle's rule): the pressure along the normal out of the fluid,
        less the viscous traction there (laminar), or plus the wall function's shear along the slip (turbulent).
        Evaluated at the nodes, so no point is mapped back into a moved curved element."""
        import numpy as np

        from cadgen._internal.fea.analyses.cfd import wall_triangles

        rows = self.wall_rows
        triangles, _, normal = wall_triangles(space, rows)            # normal out of the fluid
        mids = triangles[:, 3:]
        push = self.wall_pressure(space, flow)[:, None] * normal       # (F, 3)
        if self.turbulent:
            shear = np.zeros((space.scalar_count, 3))
            if len(flow.wall_nodes):
                rho = self.inputs.flow.fluid.density_kg_m3 * 1e-12
                tau = rho * flow.wall_u_tau ** 2
                slip = flow.wall_slip
                length = np.linalg.norm(slip, axis=1)
                shear[flow.wall_nodes] = tau[:, None] * slip / np.where(length > 0, length, 1.0)[:, None]
            return push + shear[triangles].mean(axis=1)
        mu = self.inputs.flow.fluid.viscosity_Pa_s * 1e-6
        gradient = _facet_gradients(space, flow.u, space.facets_of_rows(rows), mids)   # (F, 3 mids, 3, 3)
        strain = gradient + np.swapaxes(gradient, 2, 3)
        viscous = mu * np.einsum("fkij,fj->fki", strain, normal).mean(axis=1)
        return push - viscous

    def wall_pressure(self, space, flow):
        """(wall rows,) MPa: the flow's pressure on each wetted wall triangle, its mean over the mid-edge nodes."""
        import numpy as np

        from cadgen._internal.fea.analyses.cfd import wall_triangles

        triangles, _, _ = wall_triangles(space, self.wall_rows)
        p = np.zeros(space.scalar_count)
        p[: space.vertices] = flow.p[: space.vertices]
        edges = space.mesh.edges
        p[space.scalar.edge_dofs[0]] = 0.5 * (flow.p[edges[0]] + flow.p[edges[1]])
        return p[triangles[:, 3:]].mean(axis=1)

    # -- the iteration -------------------------------------------------------------------------------

    def run(self) -> CouplingState:
        import numpy as np

        inputs = self.inputs
        zero = np.zeros((self.ctx.space.scalar_count, 3))
        first = self.flow_at(zero, 1.0)
        if isinstance(first, int):  # cannot happen at rest; kept for the type
            raise RuntimeError("the flow mesh folded at rest")
        outcome, f = self.bend(first)
        self.one_way = {"max_displacement_mm": float(np.linalg.norm(outcome.displacement, axis=1).max()),
                        "max_von_mises_MPa": float(outcome.von_mises.max()), "outcome": outcome}
        self.one_way_post = self.post(first)
        ramp = self.ctx.plan is not None and "continuation" in self.ctx.plan.taken
        if ramp:
            return self.ramped(first, outcome, restarted=False)
        state = self.iterate(first, outcome, zero, 1.0, inputs.relaxation, inputs.tolerance, inputs.max_iterations)
        if state.growing:
            restarted = self.ramped(first, outcome, restarted=True)
            return restarted
        return state.state

    def ramped(self, first, outcome, *, restarted: bool) -> CouplingState:
        """The coupling settled at each share of the inflow in turn, each stage from the one before (scaled)."""
        inputs = self.inputs
        relaxation = min(inputs.relaxation, 0.5) if restarted else inputs.relaxation
        previous_share = 1.0
        guess = outcome.displacement
        history, relaxations, iterations = [], [], 0
        state = None
        for share in RAMP:
            final = share == RAMP[-1]
            # Each stage starts from the last one's displacement (the one-way answer first), scaled to its share.
            start = guess * (share / previous_share)
            begin = self.flow_at(start, share)
            if isinstance(begin, int):
                start = guess * 0.0
                begin = self.flow_at(start, share)
            bent, _ = self.bend(begin)
            run = self.iterate(begin, bent, start, share, relaxation, inputs.tolerance * (1.0 if final else STAGE_LOOSEN),
                               inputs.max_iterations)
            state = run.state
            history += state.history
            relaxations += state.relaxations
            iterations += state.iterations
            guess, previous_share = state.outcome.displacement, share
        state.history, state.relaxations, state.iterations = history, relaxations, iterations
        state.ramped = True
        state.flow_solves = self.flow_solves
        return state

    def iterate(self, flow_state, outcome, start, share: float, omega: float, tolerance: float, cap: int) -> "_Run":
        """Fixed-point iteration with Aitken (or fixed) relaxation from the part displaced by ``start``, whose flow is
        ``flow_state`` and whose bending under it is ``outcome``."""
        import numpy as np

        inputs = self.inputs
        nodes = self.interface.part_nodes
        current = start
        previous_residual = None
        previous_force = flow_state.force
        history: list[float] = []
        relaxations: list[float] = []
        rising = 0
        converged = False
        load_change = math.inf
        inverted = 0
        last_good = (flow_state, outcome)
        residual_norm = math.inf
        iterations = 1
        while True:
            residual = (outcome.displacement - current)[nodes].ravel()
            scale = float(np.linalg.norm(outcome.displacement[nodes]))
            residual_norm = float(np.linalg.norm(residual)) / scale if scale > 0 else 0.0
            history.append(residual_norm)
            if ctx_log := self.ctx.log:
                ctx_log(f"coupling {iterations} at {100 * share:.0f}% inflow: displacement change {residual_norm:.2e}, "
                        f"load change {load_change:.2e}")
            settled_load = load_change < tolerance or (iterations == 1 and residual_norm < tolerance)
            if residual_norm < tolerance and settled_load:
                converged = True
                break
            if len(history) > 1 and history[-1] > history[-2]:
                rising += 1
            else:
                rising = 0
            if iterations >= cap or rising >= GROWING:
                break
            if self.out_of_time or self.left_s() <= 0:
                # The budget is spent (or a flow solve stopped at it): the last state, said as not settled.
                self.out_of_time = True
                break
            if inputs.method == "aitken" and previous_residual is not None:
                delta = residual - previous_residual
                denominator = float(delta @ delta)
                if denominator > 0:
                    omega = -omega * float(previous_residual @ delta) / denominator
                    omega = min(max(omega, OMEGA_RANGE[0]), OMEGA_RANGE[1])
            elif inputs.method == "fixed_point":
                omega = inputs.relaxation
            relaxations.append(omega)
            previous_residual = residual
            # A step that folds the flow mesh over is halved, a few times, before the run stops at its last state.
            for _ in range(BACKTRACK):
                trial = current + omega * (outcome.displacement - current)
                moved = self.flow_at(trial, share)
                if not isinstance(moved, int):
                    break
                omega *= 0.5
            if isinstance(moved, int):
                inverted = moved
                break
            current = trial
            relaxations[-1] = omega
            force = moved.force
            load_change = float(np.linalg.norm(force - previous_force)) / max(float(np.linalg.norm(force)), 1e-300)
            previous_force = force
            flow_state = moved
            outcome, _ = self.bend(flow_state)
            last_good = (flow_state, outcome)
            iterations += 1
        flow_state, outcome = last_good
        growing = not converged and rising >= GROWING
        state = CouplingState(
            outcome=outcome, flow_state=flow_state, converged=converged, iterations=iterations, residual=residual_norm,
            load_change=load_change if math.isfinite(load_change) else residual_norm, method=inputs.method,
            history=history, relaxations=relaxations, ramped=False, flow_solves=self.flow_solves, inverted=inverted,
        )
        return _Run(state, growing)

    def bend(self, flow_state: FlowState):
        """The part's bending under the flow's traction: its outcome and its load vector."""
        import time

        started = time.perf_counter()
        f = self.interface.load(flow_state.traction, flow_state.pressure, flow_state.shear)
        outcome = self.structure.solve(f)
        self.timings["structure_s"] += time.perf_counter() - started
        return outcome, f

    def post(self, flow_state: FlowState) -> dict:
        from cadgen._internal.fea.analyses.cfd import flow_numbers

        post = flow_numbers(flow_state.space, self.fluid, self.face_of, self.row_kind, flow_state.flow, self.inputs.flow)
        return {"pressure_drop_Pa": post["pressure_drop_Pa"], "force_N": flow_state.force}


@dataclass
class _Run:
    state: CouplingState
    growing: bool


def _facet_gradients(space, u, facets, mids):
    """(F, 3, 3, 3) the velocity gradient at each wall triangle's three mid-edge nodes, in the one element the
    triangle closes (no averaging across the part's edges, where the gradient jumps), evaluated by a quadrature
    placed on that element's own nodes, so no point is mapped back into a moved curved element."""
    import numpy as np
    from skfem import CellBasis, ElementTetP2, ElementVector

    owner = space.mesh.f2t[0, facets]
    elements, local_element = np.unique(owner, return_inverse=True)
    element = ElementTetP2()
    points = np.ascontiguousarray(element.doflocs.T)
    basis = CellBasis(space.mesh, ElementVector(element), elements=elements,
                      quadrature=(points, np.full(points.shape[1], 1.0 / points.shape[1])))
    grad = basis.interpolate(u).grad                                    # (3, 3, E, 10)
    own = space.scalar.element_dofs[:, owner].T                         # (F, 10): the element's own node order
    local_node = (own[:, None, :] == mids[:, :, None]).argmax(axis=2)   # (F, 3)
    picked = grad[:, :, local_element[:, None], local_node]             # (3, 3, F, 3)
    return np.moveaxis(picked, (0, 1), (2, 3))


def _folded(nodes, tets) -> int:
    """How many tetrahedra the moved corners turn inside out (or flatten)."""
    import numpy as np

    corners = nodes[tets[:, :4]]
    volume = np.einsum("ij,ij->i", np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]),
                       corners[:, 3] - corners[:, 0])
    return int((volume <= 0).sum()) if (volume > 0).sum() > len(volume) // 2 else int((volume >= 0).sum())


# -- the part ----------------------------------------------------------------------------------------


class Structure:
    """The part's linear elastic stiffness, assembled and (small systems) factored once, solved for each load."""

    def __init__(self, space, volume, material, fixtures, ordinal_of: dict[str, int], solver: str):
        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.supports import not_held_sentence, supports_of, unheld_motions

        self.space, self.volume, self.material = space, volume, material
        K = operators.stiffness(space, material)
        supports = supports_of(space, fixtures, ordinal_of)
        if supports.rollers and (loose := unheld_motions(space, supports)):
            raise ValueError(not_held_sentence(loose))
        self.K, self.supports = K, supports
        self.local = supports.local(K)
        self.free = supports.free(space.basis.N)
        self.method = "iterative" if solver == "iterative" or len(self.free) >= operators.DIRECT_SOLVE_BELOW else "direct"
        self.factor = None
        self.how = ""
        if self.method == "direct":
            from scipy.sparse.linalg import splu

            self.factor = splu(self.local[self.free][:, self.free].tocsc())
            self.how = "superlu"
        self.warnings: list[str] = []
        self.np = np

    def solve(self, f):
        from cadgen._internal.fea import operators
        from cadgen._internal.fea.solve import SolveOutcome

        np = self.np
        space = self.space
        local = np.zeros(space.basis.N)
        load = self.supports.local_vector(f)
        if self.factor is not None:
            local[self.free] = self.factor.solve(load[self.free])
        else:
            local[self.free], self.how = operators.solve_spd(self.local, load, self.free, space.locations, space.component,
                                                             self.warnings, method="iterative")
        u = self.supports.global_vector(local)
        residual = self.K @ u - f
        reactions = [tuple(float(residual[dofs][space.component[dofs] == c].sum()) for c in range(3))
                     for dofs in self.supports.per_fixture]
        s = operators.stress(space, self.material, u)
        von_mises_q = operators.von_mises(s)
        von_mises = np.maximum(space.scalar.project(von_mises_q), 0.0)
        return SolveOutcome(
            dof_locations=space.dof_locations, displacement=space.nodal(u), von_mises=von_mises,
            von_mises_gauss_max=float(von_mises_q.max()), vertices=space.vertices, tets=space.tets,
            boundary_quadratic=space.boundary_quadratic, reactions=reactions,
            applied=tuple(float(f[space.component == c].sum()) for c in range(3)), dofs=int(space.basis.N),
            element_dofs=space.element_dofs, element_von_mises_gauss=von_mises_q.max(axis=1), warnings=list(self.warnings),
            solver=self.how, u=u,
        )


# -- the interface -----------------------------------------------------------------------------------


class Interface:
    """Where the fluid's walls meet the part's faces, both ways: the part's displacement onto the fluid's wall
    nodes (the P2 field on the part's surface triangles, evaluated where each fluid node sits), and the fluid's
    traction onto the part's wetted triangles (each takes the mean traction of the nearest fluid wall triangle on
    the same face). Built once, on the meshes at rest."""

    def __init__(self, space, volume, fluid_space, wall_rows, wall_ordinal):
        import numpy as np
        from scipy import sparse
        from scipy.spatial import cKDTree

        self.space = space
        locations = space.dof_locations
        boundary = space.boundary_quadratic
        fluid_boundary = fluid_space.boundary_quadratic[wall_rows]
        fluid_locations = fluid_space.dof_locations
        wetted = sorted(set(int(o) for o in wall_ordinal) - {0})
        self.wetted = wetted
        # The part's wetted rows and the fluid wall row each takes its traction from.
        part_rows = np.flatnonzero(np.isin(volume.boundary_ordinal, wetted))
        self.part_rows = part_rows
        self.part_nodes = np.unique(boundary[part_rows]) if len(part_rows) else np.zeros(0, dtype=np.int64)
        source = np.zeros(len(part_rows), dtype=np.int64)
        fluid_centres = fluid_locations[fluid_boundary[:, :3]].mean(axis=1)
        part_centres = locations[boundary[part_rows][:, :3]].mean(axis=1)
        part_ordinal = volume.boundary_ordinal[part_rows]
        for ordinal in wetted:
            on_fluid = np.flatnonzero(wall_ordinal == ordinal)
            on_part = np.flatnonzero(part_ordinal == ordinal)
            if len(on_fluid) == 0 or len(on_part) == 0:
                continue
            _, nearest = cKDTree(fluid_centres[on_fluid]).query(part_centres[on_part])
            source[on_part] = on_fluid[nearest]
        self.source = source
        # The fluid wall triangles' normals out of the fluid, at rest.
        from cadgen._internal.fea.analyses.cfd import wall_triangles

        self.fluid_normal = wall_triangles(fluid_space, wall_rows)[2]
        # The part's wetted faces as facets for integrating a load on them, and each facet's row in ``part_rows``.
        facets = space.facets_of_rows(part_rows) if len(part_rows) else np.zeros(0, dtype=np.int64)
        self.part_basis = space.basis.boundary(facets) if len(part_rows) else None
        if self.part_basis is not None:
            position = {int(facet): row for row, facet in enumerate(facets)}
            self.facet_order = np.array([position[int(facet)] for facet in self.part_basis.find], dtype=np.int64)
        else:
            self.facet_order = np.zeros(0, dtype=np.int64)
        corners = fluid_locations[fluid_boundary[:, :3]]
        self.fluid_area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        # The quadratic triangle's consistent load under an even traction: nothing at the corners, a third of the
        # (flat) area at each mid-edge node; summed into the part's vector DOF.
        from cadgen._internal.fea.navier_stokes import vector_dofs

        part_corners = locations[boundary[part_rows][:, :3]]
        self.part_area = 0.5 * np.linalg.norm(np.cross(part_corners[:, 1] - part_corners[:, 0],
                                                       part_corners[:, 2] - part_corners[:, 0]), axis=1)
        self.part_mids = boundary[part_rows][:, 3:6]
        self.dof_table = vector_dofs(space)

        # Each fluid wall node on a part face: the part's quadratic surface triangle it lies on, and its weights there.
        nodes, node_ordinal = [], []
        for ordinal in wetted:
            on = np.unique(fluid_boundary[wall_ordinal == ordinal])
            nodes.append(on)
            node_ordinal.append(np.full(len(on), ordinal))
        if nodes:
            all_nodes = np.concatenate(nodes)
            all_ordinal = np.concatenate(node_ordinal)
            all_nodes, first = np.unique(all_nodes, return_index=True)
            all_ordinal = all_ordinal[first]
        else:
            all_nodes = np.zeros(0, dtype=np.int64)
            all_ordinal = np.zeros(0, dtype=np.int64)
        self.fluid_nodes = all_nodes
        rows_i, cols, values = [], [], []
        order = _mid_order(locations, boundary)
        for ordinal in wetted:
            here = np.flatnonzero(all_ordinal == ordinal)
            triangles = boundary[volume.boundary_ordinal == ordinal]
            mids = order[volume.boundary_ordinal == ordinal]
            if len(here) == 0 or len(triangles) == 0:
                continue
            points = fluid_locations[all_nodes[here]]
            weights, chosen = _locate(points, locations, triangles)
            tri = triangles[chosen]
            mid = mids[chosen]
            # Corner weights l(2l - 1); each mid node 4 l_a l_b of the edge it sits on.
            l = weights
            for k in range(3):
                rows_i.append(here)
                cols.append(tri[:, k])
                values.append(l[:, k] * (2.0 * l[:, k] - 1.0))
            pairs = ((1, 2), (0, 2), (0, 1))
            for k in range(3):
                edge = mid[:, k]          # which corner pair mid node k joins
                a = np.array([pairs[e][0] for e in range(3)])[edge]
                b = np.array([pairs[e][1] for e in range(3)])[edge]
                rows_i.append(here)
                cols.append(tri[:, 3 + k])
                values.append(4.0 * l[np.arange(len(l)), a] * l[np.arange(len(l)), b])
        if rows_i:
            self.to_fluid_matrix = sparse.csr_matrix((np.concatenate(values), (np.concatenate(rows_i), np.concatenate(cols))),
                                                     shape=(len(all_nodes), space.scalar_count))
        else:
            self.to_fluid_matrix = sparse.csr_matrix((0, space.scalar_count))

    def to_fluid(self, displacement):
        """(fluid wall nodes, 3): the part's displacement where each fluid wall node sits."""
        return self.to_fluid_matrix @ displacement

    def load(self, traction, pressure=None, shear=None):
        """The part's load vector (N) from the traction on each fluid wall row (MPa, on the part).

        With ``pressure`` (MPa per fluid wall row) and ``shear`` (the rest of the traction, MPa: the traction less
        the pressure along the fluid wall's normal at rest), the pressure is taken as that scalar along the part's own
        normal, integrated over its curved faces as a static pressure load is, and only the rest as a vector. (Taken as a vector, the pressure carried the normal of the nearest fluid triangle, up to
        ten degrees off the part's on a bore meshed at a different size: a sideways push of a sixth of the pressure,
        varying from triangle to triangle, that a thin wall takes in bending, its softest way. A soft tube's bore
        dented in by four times its true swelling, and the coupling chased that noise and never settled.)"""
        import numpy as np
        from skfem import LinearForm, asm

        f = np.zeros(self.space.basis.N)
        if len(self.part_rows) == 0:
            return f
        if pressure is None:
            per = traction[self.source] * (self.part_area / 3.0)[:, None]   # (part rows, 3) N at each mid node
            for k in range(3):
                np.add.at(f, self.dof_table[self.part_mids[:, k]].ravel(), per.ravel())
            return f
        pressure = np.asarray(pressure, dtype=float)
        shear = np.zeros_like(traction) if shear is None else np.asarray(shear, dtype=float)
        basis = self.part_basis
        q = basis.X.shape[1]
        on_p = np.repeat(pressure[self.source][self.facet_order][:, None], q, axis=1)
        on_s = np.repeat(shear[self.source][self.facet_order].T[:, :, None], q, axis=2)    # (3, F, Q)

        @LinearForm
        def push(v, w):
            # The fluid's pressure pushes the part in, along minus its outward normal; the shear as it is.
            return sum((-w["p"] * w.n[i] + w["s"][i]) * v[i] for i in range(3))

        return asm(push, basis, p=on_p, s=on_s)


def _mid_order(locations, boundary):
    """(B, 3): for each boundary triangle's mid nodes 3, 4, 5, the corner pair it sits between: 0 for (1, 2),
    1 for (0, 2), 2 for (0, 1), found by place (the mesher's order is not assumed)."""
    import numpy as np

    corners = locations[boundary[:, :3]]
    centres = np.stack([0.5 * (corners[:, 1] + corners[:, 2]), 0.5 * (corners[:, 0] + corners[:, 2]),
                        0.5 * (corners[:, 0] + corners[:, 1])], axis=1)          # (B, 3 edges, 3)
    mids = locations[boundary[:, 3:6]]                                          # (B, 3 mids, 3)
    distance = np.linalg.norm(mids[:, :, None, :] - centres[:, None, :, :], axis=3)   # (B, mid, edge)
    return distance.argmin(axis=2)


def _locate(points, locations, triangles, candidates: int = 4):
    """For each point, the nearest of the surface triangles (by centroid, then by distance to the flat triangle
    through its corners) and the point's barycentric weights on it, clamped into the triangle."""
    import numpy as np
    from scipy.spatial import cKDTree

    corners = locations[triangles[:, :3]]
    centres = corners.mean(axis=1)
    k = min(candidates, len(triangles))
    _, near = cKDTree(centres).query(points, k=k)
    near = near.reshape(len(points), k)
    best = np.full(len(points), np.inf)
    chosen = np.zeros(len(points), dtype=np.int64)
    weights = np.zeros((len(points), 3))
    for j in range(k):
        index = near[:, j]
        a, b, c = corners[index, 0], corners[index, 1], corners[index, 2]
        e1, e2, d = b - a, c - a, points - a
        g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
        r1, r2 = (d * e1).sum(1), (d * e2).sum(1)
        det = g11 * g22 - g12 * g12
        det = np.where(np.abs(det) > 0, det, 1.0)
        s = (g22 * r1 - g12 * r2) / det
        t = (g11 * r2 - g12 * r1) / det
        lam = np.stack([1.0 - s - t, s, t], axis=1)
        lam = np.clip(lam, 0.0, 1.0)
        lam /= lam.sum(axis=1, keepdims=True)
        projected = lam[:, :1] * a + lam[:, 1:2] * b + lam[:, 2:] * c
        distance = np.linalg.norm(projected - points, axis=1)
        better = distance < best
        best[better] = distance[better]
        chosen[better] = index[better]
        weights[better] = lam[better]
    return weights, chosen


# -- the mesh motion ---------------------------------------------------------------------------------


class MeshMotion:
    """The fluid mesh's motion: a harmonic extension of the walls' displacement into the fluid, each element's
    stiffness the inverse of its size (small elements, by the part's thin gaps, move most nearly rigidly).

    Its boundary: the part's wetted walls move with the part; openings and an external box's sides stay put (a
    node on the rim of an opening moves with the wall, but not off the opening's plane); other walls stay put.
    Factored once on the mesh at rest."""

    def __init__(self, space, fluid, row_kind, face_of, wall_nodes):
        import numpy as np
        from scipy.sparse.linalg import splu
        from skfem import BilinearForm, asm
        from skfem.helpers import dot, grad

        basis = space.scalar
        volume = np.asarray(basis.dx).sum(axis=1)
        stiffness = (volume.mean() / np.maximum(volume, 1e-300))[:, None] * np.ones_like(np.asarray(basis.dx))

        @BilinearForm
        def laplace(u, v, w):
            return w["c"] * dot(grad(u), grad(v))

        A = asm(laplace, basis, c=stiffness).tocsr()
        boundary = space.boundary_quadratic
        held = np.unique(boundary)
        self.count = space.scalar_count
        self.held = held
        self.free = np.setdiff1d(np.arange(self.count), held)
        self.wall_nodes = wall_nodes
        self.A_fh = A[self.free][:, held]
        self.factor = splu(A[self.free][:, self.free].tocsc()) if len(self.free) else None
        # Rim nodes: on a wall and on an opening or side; they keep off the opening's normal.
        opening_of = np.array([face_of[int(o)].opening if int(o) in face_of else None for o in fluid.boundary_ordinal], dtype=object)
        normal_axis = np.full(self.count, -1, dtype=np.int64)
        for kind in ("inlet", "outlet", "side"):
            rows = np.flatnonzero(row_kind == kind)
            for row in rows:
                side = opening_of[row]
                if side:
                    normal_axis[boundary[row]] = "xyz".index(side[0])
        self.normal_axis = normal_axis

    def extend(self, wall):
        """(fluid scalar nodes, 3) the mesh displacement, given the wall nodes' (``wall``, in ``wall_nodes`` order)."""
        import numpy as np

        values = np.zeros((self.count, 3))
        values[self.wall_nodes] = wall
        rim = self.normal_axis[self.wall_nodes]
        on_rim = rim >= 0
        values[self.wall_nodes[on_rim], rim[on_rim]] = 0.0
        out = values.copy()
        if self.factor is not None:
            for c in range(3):
                out[self.free, c] = self.factor.solve(-(self.A_fh @ values[self.held, c]))
        return out
