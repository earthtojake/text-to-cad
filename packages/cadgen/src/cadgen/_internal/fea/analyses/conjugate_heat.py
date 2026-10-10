"""Cooled by flow (lite): heat carried by a flowing fluid into and out of the part, solved with its conduction.

The study takes a flow study's ``flow`` (spec 5.14: ``internal``, through the
part, inlets and outlets on sides of its bounding box; or ``external``, a free
stream around it; the fluid), with the heat added: each inlet's
``temperature_C`` (an external flow's ``flow.temperature_C``), and for a fluid
given by its numbers its ``conductivity_W_mK`` and ``specific_heat_J_kgK``
(``air`` and ``water`` know theirs). ``flow.regime`` is ``"laminar"`` (the
:mod:`.cfd` solver), ``"turbulent"`` (:mod:`.cfd_turbulent`'s k-omega SST, which
also takes ``turbulence_intensity``) or ``"auto"`` (the default: turbulent past
Re 2000 internal, 1000 external). The part takes a thermal study's keys:
``heat`` (into its faces), ``temperatures`` (faces held) and ``convection``
(air on faces the flow does not wet), and the ``material`` its conduction needs.
No anchor is required: the fluid coming in at its temperature carries the heat
away.

The flow is solved first on the fluid's own mesh (:mod:`..fluid_domain`), then
the heat on both meshes at once (:mod:`..conjugate`): advection-diffusion with
SUPG in the fluid, conduction in the part, tied at the wetted walls (continuity
for laminar flow, the thermal law of the wall for turbulent). What comes out is
on the part's surface: its ``temperature``; ``fluid_temperature``, the
speed-weighted mean temperature of the fluid within one passage width of each
wetted point (internal; a few wall elements for external flow), the inlet's
temperature where nothing is wetted; ``wall_heat_flux`` (W/m², into the fluid,
signed); ``heat_transfer_coefficient`` (W/(m² K), that flux over the wall's
temperature less the local fluid temperature, or the free stream's for an
external flow); and the wall ``pressure``. The summary gives each outlet's
mixed temperature, the heat the walls put into the fluid against the m c_p ΔT
it carries out (a balance off by more than 1 % is a warning), the mean heat
transfer coefficient and the Nusselt number on the hydraulic diameter, the
pressure drop and the hottest point of the part. Checks: ``temperature``
(the part), ``pressure_drop`` and ``velocity``.

Its limits are written into every result: "Steady; the flow carries the heat
but is not changed by it (no buoyancy, constant properties)". One part, as a
flow study.

Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext
from cadgen._internal.fea.analyses.thermal import (
    HEAT_KEYS, ThermalInputs, check_limits, heat_echo, parse_heat_keys, space_result, temperature_check, temperature_findings,
)

__all__ = ["ConjugateHeatAnalysis", "ConjugateInputs", "LIMITS", "REGIMES"]

LIMITS = ("Steady; the flow carries the heat but is not changed by it (no buoyancy, constant properties).",)
REGIMES = ("auto", "laminar", "turbulent")
#: A flow's energy balance (walls in against m c_p ΔT out) off by more than this share is a warning.
BALANCE_WARN = 0.01
#: An external flow's local fluid temperature is the mean within this many wall elements of the wall.
EXTERNAL_REACH = 2.0
#: The part's heat transfer coefficient is not said where the wall is within this share of the span of the fluid.
QUIET = 1e-4


@dataclass(frozen=True)
class ConjugateInputs(Inputs):
    #: The flow, as cfd_turbulent parses it (a laminar flow reads the same keys).
    flow: Any = None
    regime: str = "auto"
    fluid_conductivity: float = 0.0          # W/(m K)
    fluid_specific_heat: float = 0.0         # J/(kg K)
    #: Each inlet's temperature, in the inlets' order; an external flow's free stream alone.
    inlet_C: tuple[float, ...] = ()
    #: The part's heat keys, as a thermal study's.
    thermal: ThermalInputs | None = None
    reference_C: float = 20.0


# -- parse --------------------------------------------------------------------------------------------


def _strip(document: dict) -> tuple[dict, str, tuple[float, float] | None, tuple[float, ...]]:
    """The flow study without its heat keys (what the flow parsers read), the regime, the fluid's heat numbers
    (None for a named fluid) and each inlet's temperature."""
    flow = document.get("flow")
    if not isinstance(flow, dict):
        raise ValueError('study.flow: a cooled-by-flow study needs its flow, like {"kind": "internal", "fluid": "water", '
                         '"inlets": [{"opening": "x_min", "velocity_m_s": 0.5, "temperature_C": 20}], '
                         '"outlets": [{"opening": "x_max", "pressure_Pa": 0}]}')
    flow = dict(flow)
    regime = flow.pop("regime", "auto")
    if regime not in REGIMES:
        raise ValueError(f"flow.regime: {kinds.json_text(regime)} is not one of {list(REGIMES)} "
                         "(auto: laminar below Re 2000 internal or 1000 external, turbulent above)")
    heat_numbers = None
    fluid = flow.get("fluid")
    if isinstance(fluid, dict):
        fluid = dict(fluid)
        for key, words in (("conductivity_W_mK", "how well the fluid conducts heat, in W/(m K) (water 0.6, air 0.026, oil 0.13)"),
                           ("specific_heat_J_kgK", "the heat it takes to warm the fluid, in J/(kg K) (water 4181, air 1007, oil 2000)")):
            if key not in fluid:
                raise ValueError(f"flow.fluid.{key}: a fluid given by its numbers carries heat by its {key.split('_')[0]} too: {words}")
        heat_numbers = (kinds.number(fluid.pop("conductivity_W_mK"), where="flow.fluid.conductivity_W_mK", positive=True),
                        kinds.number(fluid.pop("specific_heat_J_kgK"), where="flow.fluid.specific_heat_J_kgK", positive=True))
        flow["fluid"] = fluid
    temperatures: list[float] = []
    if flow.get("kind", "internal") == "external":
        if "temperature_C" not in flow:
            raise ValueError("flow.temperature_C: the temperature of the free stream, in °C")
        temperatures.append(kinds.number(flow.pop("temperature_C"), where="flow.temperature_C"))
    elif isinstance(flow.get("inlets"), list):
        inlets = []
        for index, entry in enumerate(flow["inlets"]):
            if isinstance(entry, dict):
                entry = dict(entry)
                if "temperature_C" not in entry:
                    raise ValueError(f"flow.inlets[{index}].temperature_C: the temperature the fluid comes in at, in °C")
                temperatures.append(kinds.number(entry.pop("temperature_C"), where=f"flow.inlets[{index}].temperature_C"))
            inlets.append(entry)
        flow["inlets"] = inlets
    for value, where in zip(temperatures, ["flow.temperature_C"] if flow.get("kind") == "external" else
                            [f"flow.inlets[{i}].temperature_C" for i in range(len(temperatures))]):
        if value < -273.15:
            raise ValueError(f"{where}: {value:g} °C is below absolute zero")
    return {"flow": flow}, regime, heat_numbers, tuple(temperatures)


# -- the analysis -------------------------------------------------------------------------------------


class ConjugateHeatAnalysis:
    name: ClassVar[str] = "conjugate_heat"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Cooled by flow"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"flow", *HEAT_KEYS})
    material_needs: ClassVar[frozenset[str]] = frozenset({"conductivity"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("temperature", "_TEMPERATURE", "temperature", "°C", signed=True),
        FieldSpec("fluid_temperature", "_FLUID_TEMPERATURE", "fluid temperature", "°C", signed=True),
        FieldSpec("wall_heat_flux", "_WALL_HEAT_FLUX", "heat into the flow", "W/m²", signed=True),
        FieldSpec("heat_transfer_coefficient", "_HEAT_TRANSFER_COEFFICIENT", "heat transfer coefficient", "W/m²K"),
        FieldSpec("pressure", "_PRESSURE", "wall pressure", "Pa", signed=True),
    )
    checks: ClassVar[tuple] = (kinds.TEMPERATURE, kinds.PRESSURE_DROP, kinds.VELOCITY)
    default_checks: ClassVar[tuple[dict, ...]] = ()
    drives: ClassVar[tuple[str, ...]] = ("field", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum",
                  "options": ["temperature", "fluid_temperature", "wall_heat_flux", "heat_transfer_coefficient", "pressure"]},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "fluid_coarsen", "continuation", "local_refine")
    noun: ClassVar[str] = "this heat"
    governing_word: ClassVar[str] = "the hottest temperature"

    def __init__(self):
        from cadgen._internal.fea.analyses.cfd import CfdAnalysis
        from cadgen._internal.fea.analyses.cfd_turbulent import CfdTurbulentAnalysis

        self.laminar = CfdAnalysis()
        self.turbulent = CfdTurbulentAnalysis()

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ConjugateInputs:
        from cadgen._internal.fea import conjugate
        from cadgen._internal.fea.analyses.thermal import reference_of

        stripped, regime, heat_numbers, inlet_C = _strip(document)
        try:
            flow = self.turbulent.parse(stripped)
        except ValueError as exc:
            words = str(exc).replace("an inlet takes opening, velocity_m_s, profile and turbulence_intensity",
                                     "an inlet takes opening, velocity_m_s, temperature_C, profile and turbulence_intensity")
            words = words.replace("an external flow takes kind, fluid, velocity_m_s and turbulence_intensity",
                                  "an external flow takes kind, fluid, velocity_m_s, temperature_C and turbulence_intensity")
            words = words.replace("an internal flow takes kind, fluid, inlets and outlets",
                                  "an internal flow takes kind, fluid, regime, inlets and outlets")
            words = words.replace("a fluid takes density_kg_m3, viscosity_Pa_s and a name",
                                  "a fluid takes density_kg_m3, viscosity_Pa_s, conductivity_W_mK, specific_heat_J_kgK and a name")
            raise ValueError(words) from None
        raw = document["flow"]
        intensity_given = "turbulence_intensity" in raw or any(
            isinstance(entry, dict) and "turbulence_intensity" in entry for entry in raw.get("inlets", []) or [])
        if regime == "laminar" and intensity_given:
            raise ValueError("flow.turbulence_intensity: a laminar flow has no turbulence; leave it out, or set regime "
                             "to \"turbulent\" or \"auto\"")
        if heat_numbers is None:
            heat_numbers = conjugate.FLUID_HEAT[flow.fluid.name]
        temperatures, heat, convection = parse_heat_keys(document)
        reference = reference_of(temperatures, convection, *inlet_C)
        check_limits(document, reference)
        refs = tuple(dict.fromkeys(ref for group in (*temperatures, *heat, *convection) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for group in (*temperatures, *convection) for ref in group.faces))
        thermal = ThermalInputs(refs, anchors, False, temperatures=temperatures, heat=heat, convection=convection,
                                reference_C=reference)
        return ConjugateInputs(refs, anchors, False, flow=flow, regime=regime, fluid_conductivity=heat_numbers[0],
                               fluid_specific_heat=heat_numbers[1], inlet_C=inlet_C, thermal=thermal, reference_C=reference)

    # -- the flow's solver and its sizes -------------------------------------------------------------

    @contextmanager
    def fluid_plan(self, ctx: SolveContext):
        """The plan as the flow reads it: its wall size is the study's own mesh size where it gives one (else the
        flow's default), never the part's coarse pass of local_refine."""
        plan = ctx.plan
        saved = plan.size_mm
        plan.size_mm = getattr(ctx.study, "mesh_size", None) if ctx.study is not None else None
        try:
            yield plan
        finally:
            plan.size_mm = saved

    def regime_of(self, ctx: SolveContext, inputs: ConjugateInputs) -> str:
        """laminar or turbulent: the study's, or (auto) by the Reynolds number against the laminar range."""
        if inputs.regime != "auto":
            return inputs.regime
        from cadgen._internal.fea.analyses.cfd import RE_LIMIT

        with self.fluid_plan(ctx):
            setup = self.laminar.setup_of(ctx, inputs.flow)
        return "turbulent" if setup.reynolds > RE_LIMIT[inputs.flow.kind] else "laminar"

    def delegate(self, ctx: SolveContext, inputs: ConjugateInputs):
        return self.turbulent if self.regime_of(ctx, inputs) == "turbulent" else self.laminar

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: ConjugateInputs):
        """The flow's estimate (its delegate's), plus the part's temperatures and the coupled heat solve."""
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.thermal import ladder_estimate

        delegate = self.delegate(ctx, inputs)
        with self.fluid_plan(ctx):
            flow = delegate.estimate(ctx, inputs.flow)
        solid = ladder_estimate(ctx)
        # The fluid's temperatures: one vertex per ~15 flow DOF, a non-symmetric factorisation.
        n = flow.dofs / 15.0 + solid.dofs
        energy = 2e-8 * n ** 1.5 + 1e-5 * n
        return fit.Estimate(dofs=int(flow.dofs + solid.dofs), memory_bytes=int(max(flow.memory_bytes, solid.memory_bytes)),
                            seconds=float(flow.seconds + solid.seconds + energy))

    def apply(self, rung, ctx: SolveContext, inputs: ConjugateInputs):
        from cadgen._internal.fea import fit

        plan, budget = ctx.plan, ctx.budget
        if rung == "iterative":
            if plan.solver != "direct":
                return None
            before = self.estimate(ctx, inputs)
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            memory = before.memory_bytes > budget.memory_bytes
            saves = after.memory_bytes < 0.95 * before.memory_bytes if memory else after.seconds < 0.95 * before.seconds
            if not saves:
                plan.solver = "direct"
                return None
            why = "fit in memory" if memory else "finish sooner"
            return fit.Step("iterative", f"Used iterative solvers for the flow and the heat (Krylov, preconditioned) to {why}",
                            None, None, detail={"solver": "iterative", "from_bytes": int(before.memory_bytes),
                                                "to_bytes": int(after.memory_bytes)})
        if rung in ("fluid_coarsen", "continuation"):
            delegate = self.delegate(ctx, inputs)
            with self.fluid_plan(ctx):
                step = delegate.apply(rung, ctx, inputs.flow)
            if step is not None and rung == "fluid_coarsen":
                from dataclasses import replace

                # The heat, not only the pressure drop, is what a coarser core costs here.
                step = replace(step, accuracy="the fluid's core is resolved more coarsely, so the heat it takes from the walls "
                                              "may read a little high; the walls keep their size and the energy balance stays exact")
            return step
        if rung == "local_refine":
            return fit.apply_generic(rung, self, ctx, inputs)
        return None

    def governing(self, result: AnalysisResult):
        """local_refine keeps the part's mesh fine where it is hottest; two passes compare the hottest temperature."""
        T = result.fields["temperature"]
        return T, float(T.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: ConjugateInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import conjugate, fluid_domain, navier_stokes, turbulence
        from cadgen._internal.fea.analyses.cfd import DENSITY, RE_LIMIT, VISCOSITY, flow_numbers, reynolds_sentence, wall_to_part
        from cadgen._internal.fea.analyses.cfd_turbulent import MARCH, MARCH_FAST, laminar_sentence
        from cadgen._internal.fea.analyses.thermal import build_system
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea import thermal_ops

        timings: dict[str, float] = {}
        regime = self.regime_of(ctx, inputs)
        turbulent = regime == "turbulent"
        delegate = self.turbulent if turbulent else self.laminar
        flow_inputs = inputs.flow
        with self.fluid_plan(ctx):
            setup = delegate.setup_of(ctx, flow_inputs)
            wall, far = delegate.sizes(ctx, setup)
        domain = setup.domain
        timings["fluid_domain_s"] = domain.seconds
        if ctx.log:
            ctx.log(f"meshing the {domain.kind} flow region at {wall:.3g} mm" + (f" (free stream {far:.3g} mm)" if far > wall else ""))
        started = time.perf_counter()
        fluid = fluid_domain.mesh_fluid(domain, wall, far)
        space = FemSpace.build(fluid, 2)
        timings["fluid_mesh_s"] = time.perf_counter() - started

        # The flow, first: it carries the heat and is not changed by it.
        started = time.perf_counter()
        face_of = {face.index: face for face in domain.faces}
        row_kind = np.array([face_of[int(o)].kind if int(o) in face_of else "wall" for o in fluid.boundary_ordinal])
        solver = "iterative" if ctx.plan.solver == "iterative" else "direct"
        problem = delegate.problem_of(space, fluid, face_of, row_kind, flow_inputs, setup)
        if turbulent:
            march = MARCH_FAST if "continuation" in ctx.plan.taken else MARCH
            flow = turbulence.solve_rans(problem, solver=solver, cfl=march, log=ctx.log)
        else:
            schedule = tuple(re / setup.reynolds for re in ctx.plan.re_schedule) if ctx.plan.re_schedule and setup.reynolds > 0 else ()
            flow = navier_stokes.solve_flow(problem, schedule=schedule, solver=solver, log=ctx.log)
        timings["flow_s"] = time.perf_counter() - started
        post = flow_numbers(space, fluid, face_of, row_kind, flow, flow_inputs)
        rho = flow_inputs.fluid.density_kg_m3 * DENSITY
        if turbulent:
            delegate.wall_function_shear(space, row_kind, flow, post, rho)
        pressure, _ = wall_to_part(ctx, space, fluid, face_of, row_kind, post)

        # The heat: the fluid's energy and the part's conduction, tied at the wetted walls.
        started = time.perf_counter()
        cp = inputs.fluid_specific_heat * 1e6
        rho_cp = rho * cp
        k_f = inputs.fluid_conductivity
        nu = flow_inputs.fluid.viscosity_Pa_s * VISCOSITY / rho
        nu_t = np.asarray(flow.k) / np.maximum(np.asarray(flow.omega), 1e-300) if turbulent else None
        A_f, _ = conjugate.energy_matrix(space, flow.u, rho_cp, k_f, nu_t)
        vertices = space.vertices
        ordinal_of_row = np.array([face_of[int(o)].ordinal if int(o) in face_of else 0 for o in fluid.boundary_ordinal])
        wall_rows = (row_kind == "wall") & (ordinal_of_row > 0)
        if not wall_rows.any():
            raise ValueError("the flow wets none of the part's faces, so no heat passes between them; check the openings")
        wall_nodes: list = []
        blocks = []
        taken = np.zeros(vertices, dtype=bool)
        volume = ctx.volume
        for ordinal in sorted(set(int(o) for o in ordinal_of_row[wall_rows])):
            nodes = np.unique(space.boundary_quadratic[wall_rows & (ordinal_of_row == ordinal)][:, :3])
            nodes = nodes[~taken[nodes]]
            part_rows = np.flatnonzero(volume.boundary_ordinal == ordinal)
            if not len(nodes) or not len(part_rows):
                continue
            taken[nodes] = True
            matrix, _ = conjugate.interface_map(ctx.space, part_rows, space.dof_locations[nodes])
            wall_nodes.append(nodes)
            blocks.append(matrix)
        from scipy import sparse

        wall_nodes = np.concatenate(wall_nodes)
        Pi = sparse.vstack(blocks).tocsr()
        # Inlets bring the fluid in at their temperature (Danckwerts: the enthalpy coming in, nothing held).
        opening_of = np.array([face_of[int(o)].opening if int(o) in face_of else None for o in fluid.boundary_ordinal], dtype=object)
        f_f = np.zeros(vertices)
        entering = [(np.flatnonzero(row_kind == "inlet"), inputs.inlet_C[0])] if flow_inputs.kind == "external" else [
            (np.flatnonzero((row_kind == "inlet") & (opening_of == inlet.opening)), celsius)
            for inlet, celsius in zip(flow_inputs.inlets, inputs.inlet_C)]
        for rows, celsius in entering:
            if len(rows):
                taken_in, brought = conjugate.inflow(space, rows, flow.u, rho_cp, celsius)
                A_f = (A_f + taken_in).tocsr()
                f_f += brought
        held_nodes, held_values = np.zeros(0, dtype=np.int64), np.zeros(0)
        closed = np.flatnonzero((row_kind != "inlet") & (row_kind != "outlet"))
        if turbulent or flow_inputs.kind == "external":
            # Slip at a wall function or an external box's side: no enthalpy through it.
            A_f = (A_f + conjugate.impermeable(space, closed, flow.u, rho_cp)).tocsr()

        system = build_system(ctx, inputs.thermal)
        K_s, f_s = system.stiffness, system.load()
        solid_fixed = system.fixed_values()
        film_matrix = None
        if turbulent:
            film_matrix = self._wall_film(space, flow, wall_rows, wall_nodes, rho, cp, nu, k_f)
        coupled = conjugate.coupled_solve(K_s, f_s, solid_fixed, A_f, (held_nodes, held_values), wall_nodes, Pi,
                                          f_f=f_f, film_matrix=film_matrix, solver=solver)
        timings["heat_s"] = time.perf_counter() - started
        T_s, T_f = coupled.solid, coupled.fluid
        if ctx.log:
            ctx.log(f"heat: {coupled.how}, {len(T_f)} fluid and {len(T_s)} part temperatures")

        # The numbers: heat into the fluid at the walls against what the flow carries out.
        flows = {}
        for kind in ("inlet", "outlet"):
            rows_all = np.flatnonzero(row_kind == kind)
            for opening in sorted(set(opening_of[rows_all].tolist()), key=str):
                rows = rows_all[opening_of[rows_all] == opening]
                volume_flow, carried = conjugate.boundary_flux(space, rows, flow.u, T_f, rho_cp)
                flows[(kind, opening)] = (volume_flow, carried)
        out_heat = sum(carried for (kind, _), (_, carried) in flows.items() if kind == "outlet")
        # m c_p ΔT: the enthalpy leaving through the outlets less what the inlets brought in at their temperature.
        carried_W = (out_heat - float(f_f.sum())) / 1e3
        wall_W = float(coupled.wall_power.sum()) / 1e3
        inflow = -sum(volume_flow for (kind, _), (volume_flow, _) in flows.items() if kind == "inlet")
        outflow = sum(volume_flow for (kind, _), (volume_flow, _) in flows.items() if kind == "outlet")
        # Each outlet's mixed temperature, measured from the inlets' (so a flow that leaks a little through a
        # slipping wall moves only the rise, not the whole temperature).
        t_in = float(f_f.sum()) / (rho_cp * inflow) if inflow > 0 else float(np.mean(inputs.inlet_C))
        outlets = []
        for (kind, opening), (volume_flow, carried) in flows.items():
            if kind == "outlet" and abs(volume_flow) > 0:
                outlets.append({"opening": opening, "temperature_C": t_in + (carried - rho_cp * t_in * volume_flow) / (rho_cp * volume_flow),
                                "flow_m3_s": volume_flow * 1e-9})
        # All outlets together, mixed (what a probe in the outlet pipe reads); and the inlets' temperature plus the
        # rise the energy balance gives (m c_p ΔT = the heat the walls put in). The two are one for laminar flow,
        # whose walls hold the fluid still; a wall function lets a little slip through, and moves them apart.
        outlet_mean = (sum(o["temperature_C"] * o["flow_m3_s"] for o in outlets) / sum(o["flow_m3_s"] for o in outlets)
                       if outlets else float("nan"))
        outlet_balance = t_in + (out_heat - float(f_f.sum())) / (rho_cp * inflow) if inflow > 0 else float("nan")
        # The fluid's books: what the walls put in leaves as m c_p ΔT.
        larger = max(abs(wall_W), abs(carried_W))
        fluid_balance = abs(wall_W - carried_W) / larger if larger > 1e-9 else 0.0
        balance = thermal_ops.heat_balance(system, T_s)
        # The part's own balance, with what it gives the fluid counted out of it.
        part_in = balance["in_W"] + max(-wall_W, 0.0)
        part_out = balance["out_W"] + max(wall_W, 0.0)
        part_balance = abs(part_in - part_out) / max(part_in, part_out) if max(part_in, part_out) > 1e-9 else 0.0

        # On the part's surface: the wall heat flux, the local fluid temperature, the heat transfer coefficient.
        area = conjugate.lumped_area(space, np.flatnonzero(wall_rows))
        q = np.zeros(vertices)
        q[wall_nodes] = coupled.wall_power / np.maximum(area[wall_nodes], 1e-300) * 1e3     # W/m²
        wall_T = np.zeros(vertices)
        wall_T[wall_nodes] = Pi @ T_s
        speed = np.linalg.norm(post["nodal_velocity"][:vertices], axis=1)
        lumped = self._lumped_volume(space)
        if flow_inputs.kind == "internal":
            reach = setup.length_mm
        else:
            reach = EXTERNAL_REACH * wall
        local = self._local_fluid(space.dof_locations[:vertices], T_f, speed * lumped, wall_nodes, reach)
        fluid_T = np.zeros(vertices)
        fluid_T[wall_nodes] = local
        reference = fluid_T if flow_inputs.kind == "internal" else np.full(vertices, inputs.inlet_C[0])
        span = max(float(np.ptp(T_f)), float(np.ptp(T_s)), 1e-9)
        difference = wall_T - reference
        coefficient = np.zeros(vertices)
        loud = np.zeros(vertices, dtype=bool)
        loud[wall_nodes] = np.abs(difference[wall_nodes]) > QUIET * span
        coefficient[loud] = q[loud] / difference[loud]
        part_values = self._to_part(ctx, space, fluid, face_of, row_kind, {"flux": q, "fluid": fluid_T, "h": coefficient},
                                    default={"fluid": min(inputs.inlet_C)})
        wetted_area = float(area[wall_nodes].sum())
        mean_wall = float((wall_T[wall_nodes] * area[wall_nodes]).sum() / max(wetted_area, 1e-300))
        difference_mean = mean_wall - float(inputs.inlet_C[0])
        if flow_inputs.kind == "internal" and math.isfinite(outlet_mean):
            # The log-mean temperature difference between the wall and the fluid, in to out (a heat exchanger's).
            first, last = mean_wall - float(np.mean(inputs.inlet_C)), mean_wall - outlet_mean
            if first * last > 0 and abs(first - last) > 1e-9 * max(abs(first), 1.0):
                difference_mean = (first - last) / math.log(first / last)
            else:
                difference_mean = 0.5 * (first + last)
        reference_mean = mean_wall - difference_mean
        mean_h = (wall_W * 1e6 / wetted_area / difference_mean) if abs(difference_mean) > QUIET * span else None

        warnings = list(getattr(flow, "warnings", [])) + coupled.warnings
        analysis_warnings = []
        limit = RE_LIMIT[flow_inputs.kind]
        reynolds = {"value": round(setup.reynolds, 2), "limit": limit, "kind": flow_inputs.kind,
                    "length_mm": round(setup.length_mm, 4)}
        if not turbulent and setup.reynolds > limit:
            analysis_warnings.append(reynolds_sentence(setup.reynolds, limit).replace("run the same study as cfd_turbulent",
                                                                                       "set flow.regime to \"turbulent\""))
        if turbulent and setup.reynolds < limit:
            analysis_warnings.append(laminar_sentence(setup.reynolds, limit).replace("the laminar cfd analysis",
                                                                                     "flow.regime \"laminar\""))
        if fluid_balance > BALANCE_WARN:
            analysis_warnings.append(f"the heat the walls put into the fluid ({wall_W:.4g} W) and what the flow carries out "
                                     f"({carried_W:.4g} W) differ by {fluid_balance:.1%}: the heat solve did not settle")
        rise = outlet_balance - t_in
        if math.isfinite(outlet_mean) and abs(rise) > 0 and abs(outlet_mean - outlet_balance) > BALANCE_WARN * abs(rise):
            analysis_warnings.append(
                f"the fluid leaves at {outlet_mean:.6g} °C mixed, against {outlet_balance:.6g} °C from the energy balance "
                f"({abs(outlet_mean - outlet_balance) / abs(rise):.1%} of the rise): the flow carries {post['imbalance']:.2%} more "
                "or less out than in (a slipping wall function), which a small rise in a large flow magnifies")
        if not getattr(flow, "converged", True):
            analysis_warnings.append("the flow solve did not settle, so the heat it carries is approximate")
        prandtl = rho * cp * nu / k_f
        result = space_result(
            ctx.space,
            {"temperature": T_s, "fluid_temperature": part_values["fluid"], "wall_heat_flux": part_values["flux"],
             "heat_transfer_coefficient": part_values["h"], "pressure": pressure},
            solver=f"{'RANS (k-omega SST)' if turbulent else 'Taylor-Hood Navier-Stokes'} flow, then the heat: "
                   f"linear SUPG energy in the fluid coupled to the part ({coupled.how})",
            timings={**timings, **{f"flow_{k}": v for k, v in getattr(flow, "timings", {}).items()}},
            warnings=warnings,
            scalars={
                "post": post, "flow": flow, "regime": regime, "reynolds": reynolds, "prandtl": prandtl,
                "coupled": coupled, "fluid_temperatures": T_f, "wall_W": wall_W, "carried_W": carried_W,
                "fluid_balance": fluid_balance, "part_balance": part_balance, "balance": balance, "outlets": outlets,
                "outlet_mean_C": outlet_mean, "outlet_balance_C": outlet_balance, "mass_flow_kg_s": rho * inflow * 1e3, "inflow_mm3_s": inflow,
                "wetted_area_mm2": wetted_area, "mean_wall_C": mean_wall,
                "mean_h": mean_h, "reference_mean_C": reference_mean,
                "fluid_mesh": {"elements": int(len(fluid.tets)), "nodes": int(len(fluid.nodes)),
                               "wall_size_mm": round(wall, 4), "far_size_mm": round(far, 4)},
                "reference_C": inputs.reference_C, "analysis_warnings": analysis_warnings,
                "analysis_extras": {"reynolds": reynolds, "regime": regime},
                "wall_nodes": wall_nodes, "wall_flux": q, "wall_temperature": wall_T, "local_fluid": fluid_T,
                "hydraulic_mm": setup.length_mm, "fluid_space": space,
            },
        )
        result.dofs = int(len(T_s) + len(T_f) + problem.space.basis.N)
        result.scalars["summary"] = self.summary(result, inputs, [])
        return result

    @staticmethod
    def _lumped_volume(space) -> "Any":
        """(vertices,) each corner vertex's share of the fluid volume (linear elements, lumped), mm³."""
        from skfem import ElementTetP1, LinearForm, asm

        @LinearForm
        def unit(v, _):
            return v

        return asm(unit, space.basis.with_element(ElementTetP1()))

    @staticmethod
    def _local_fluid(points, T_f, weight, wall_nodes, reach: float):
        """At each wall vertex, the mean fluid temperature within ``reach`` mm, weighted by speed × volume (the
        fluid that is moving past, so the still layer at the wall counts for little)."""
        import numpy as np
        from scipy.spatial import cKDTree

        tree = cKDTree(points)
        out = np.zeros(len(wall_nodes))
        groups = tree.query_ball_point(points[wall_nodes], r=reach)
        for i, near in enumerate(groups):
            near = np.asarray(near, dtype=np.int64)
            w = weight[near]
            total = float(w.sum())
            out[i] = float((w * T_f[near]).sum() / total) if total > 0 else float(T_f[near].mean())
        return out

    @staticmethod
    def _wall_film(space, flow, wall_rows, wall_nodes, rho: float, cp: float, nu: float, k: float):
        """The thermal law of the wall's film on the coupled walls, as the fluid's boundary mass weighted by h."""
        import numpy as np
        from skfem import BilinearForm, ElementTetP1, asm

        from cadgen._internal.fea import conjugate

        vertices = space.vertices
        u_tau = np.zeros(vertices)
        slip = np.zeros((vertices, 3))
        nodes = np.asarray(flow.wall_nodes, dtype=np.int64)
        corner = nodes < vertices
        u_tau[nodes[corner]] = np.asarray(flow.wall_u_tau)[corner]
        slip[nodes[corner]] = np.asarray(flow.wall_slip)[corner]
        h = np.zeros(vertices)
        h[wall_nodes] = conjugate.thermal_wall_film(rho, cp, nu, k, u_tau[wall_nodes], slip[wall_nodes])
        boundary = space.basis.with_element(ElementTetP1()).boundary(space.facets_of_rows(np.flatnonzero(wall_rows)))

        @BilinearForm
        def film(u, v, w):
            return w["h"] * u * v

        return asm(film, boundary, h=boundary.interpolate(h)).tocsr()

    @staticmethod
    def _to_part(ctx: SolveContext, space, fluid, face_of, row_kind, values: dict, *, default: dict) -> dict:
        """Fluid wall-vertex values carried onto the part's surface nodes, face by face (the nearest fluid wall
        vertex on the same face); a part node the fluid does not wet takes ``default`` (else 0)."""
        import numpy as np
        from scipy.spatial import cKDTree

        part_space, volume = ctx.space, ctx.volume
        out = {name: np.full(part_space.scalar_count, float(default.get(name, 0.0))) for name in values}
        ordinal_of_row = np.array([face_of[int(o)].ordinal if int(o) in face_of else 0 for o in fluid.boundary_ordinal])
        for ordinal in sorted(set(int(o) for o in ordinal_of_row[row_kind == "wall"]) - {0}):
            source = np.unique(space.boundary_quadratic[(row_kind == "wall") & (ordinal_of_row == ordinal)][:, :3])
            target = np.unique(part_space.boundary_quadratic[volume.boundary_ordinal == ordinal])
            if not len(source) or not len(target):
                continue
            _, nearest = cKDTree(space.dof_locations[source]).query(part_space.dof_locations[target])
            for name, field in values.items():
                out[name][target] = field[source[nearest]]
        return out

    def needs_finer(self, result: AnalysisResult, inputs: ConjugateInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: ConjugateInputs) -> dict:
        if check["kind"] == "temperature":
            peak = kinds.field_max_over(
                result.fields["temperature"], tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
                boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
                ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
            )
            return temperature_check(check, peak.value, inputs.reference_C, at=peak.at, ref=peak.ref, faces=peak.faces)
        return self.laminar.judge(check, index, ctx, result, inputs.flow)

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ConjugateInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        found = temperature_findings(check_results, assembly=assembly)
        for check in check_results:
            if check["kind"] not in ("pressure_drop", "velocity") or check["status"] == "passes":
                continue
            what = "pressure drop" if check["kind"] == "pressure_drop" else "fastest flow"
            value = f"{check['value']:.4g} {check['unit']}"
            fails = check["status"] == "fails"
            found.append({
                "check": "fea", "severity": "error" if fails else "warning",
                "type": f"{check['kind']}_{'over_limit' if fails else 'close_to_limit'}",
                "summary": f"The {what} is {value}, {'over' if fails else 'close to'} the {check['limit']:g} {check['unit']} allowed",
                "description": f"{what} {value} against a {check['limit']:g} {check['unit']} limit ({check['ratio']:.2f} of it)",
                "items": [{"text": f"the {what}", **check["where"]}],
            })
        for sentence in result.scalars["analysis_warnings"]:
            kind = ("reynolds_past_laminar" if "past the laminar range" in sentence else
                    "reynolds_laminar_range" if "in the laminar range" in sentence else
                    "fluid_heat_balance" if sentence.startswith("the heat the walls") else
                    "outlet_temperature_spread" if sentence.startswith("the fluid leaves") else "flow_unsettled")
            found.append({"check": "fea", "severity": "warning", "type": kind, "summary": sentence[0].upper() + sentence[1:],
                          "description": "the heat is carried by the flow this solve found", "items": []})
        scalars = result.scalars
        outlet = scalars["outlet_mean_C"]
        if math.isfinite(outlet):
            found.append({
                "check": "fea", "severity": "info", "type": "fluid_warms",
                "summary": f"The fluid leaves at {outlet:.4g} °C (in at {', '.join(f'{c:g}' for c in inputs.inlet_C)} °C), "
                           f"carrying {scalars['carried_W']:.4g} W",
                "description": f"{scalars['mass_flow_kg_s'] * 1000:.4g} g/s of {inputs.flow.fluid.name}; the walls put "
                               f"{scalars['wall_W']:.4g} W into it",
                "items": [],
            })
        return found

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        return None

    def summary(self, result: AnalysisResult, inputs: ConjugateInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars, post, flow = result.scalars, result.scalars["post"], result.scalars["flow"]
        T = result.fields["temperature"]
        hottest = int(T.argmax())
        T_f = scalars["fluid_temperatures"]
        wall = scalars["wall_nodes"]
        flux, h = scalars["wall_flux"][wall], result.fields["heat_transfer_coefficient"]
        reynolds = dict(scalars["reynolds"])
        mean_h = scalars["mean_h"]
        summary: dict[str, Any] = {
            "flow_kind": inputs.flow.kind,
            "regime": scalars["regime"],
            "fluid": {"name": inputs.flow.fluid.name, "density_kg_m3": inputs.flow.fluid.density_kg_m3,
                      "viscosity_Pa_s": inputs.flow.fluid.viscosity_Pa_s, "conductivity_W_mK": inputs.fluid_conductivity,
                      "specific_heat_J_kgK": inputs.fluid_specific_heat},
            "reynolds": reynolds,
            "prandtl": round(scalars["prandtl"], 6),
            "peclet": round(scalars["prandtl"] * reynolds["value"], 4),
            "max_temperature_C": round(float(T.max()), 4),
            "min_temperature_C": round(float(T.min()), 4),
            "max_at_mm": [round(float(c), 3) for c in result.dof_locations[hottest]],
            "inlet_temperature_C": [round(c, 4) for c in inputs.inlet_C],
            "outlet_temperature_C": round(scalars["outlet_mean_C"], 6) if math.isfinite(scalars["outlet_mean_C"]) else None,
            "outlet_temperature_by_balance_C": (round(scalars["outlet_balance_C"], 6) if math.isfinite(scalars["outlet_balance_C"])
                                                else None),
            "outlets": [{"opening": o["opening"], "temperature_C": round(o["temperature_C"], 6),
                         "flow_m3_s": float(f"{o['flow_m3_s']:.6g}")} for o in scalars["outlets"]],
            "max_fluid_temperature_C": round(float(T_f.max()), 4),
            "min_fluid_temperature_C": round(float(T_f.min()), 4),
            "heat_to_fluid_W": round(scalars["wall_W"], 6),
            "heat_carried_W": round(scalars["carried_W"], 6),
            "fluid_balance": round(scalars["fluid_balance"], 6),
            "mass_flow_kg_s": float(f"{scalars['mass_flow_kg_s']:.6g}"),
            "part_heat_in_W": round(scalars["balance"]["in_W"], 6),
            "part_balance": round(scalars["part_balance"], 6),
            "wetted_area_mm2": round(scalars["wetted_area_mm2"], 4),
            "mean_wall_temperature_C": round(scalars["mean_wall_C"], 4),
            "max_wall_heat_flux_W_m2": round(float(flux.max()), 4) if len(flux) else 0.0,
            "min_wall_heat_flux_W_m2": round(float(flux.min()), 4) if len(flux) else 0.0,
            "max_heat_transfer_coefficient_W_m2K": round(float(h.max()), 4),
            "mean_heat_transfer_coefficient_W_m2K": None if mean_h is None else round(mean_h, 4),
            "nusselt": (None if mean_h is None or inputs.flow.kind != "internal" else
                        round(mean_h * scalars["hydraulic_mm"] / 1000.0 / inputs.fluid_conductivity, 4)),
            "pressure_drop_Pa": round(post["pressure_drop_Pa"], 6),
            "flow_balance": round(post["imbalance"], 6),
            "flow_rate_m3_s": float(f"{post['flow_rate_m3_s']:.6g}"),
            "flow_rate_L_min": round(post["flow_rate_m3_s"] * 60000.0, 6),
            "max_velocity_m_s": round(post["max_velocity_m_s"], 6),
            "fluid_mesh": dict(scalars["fluid_mesh"]),
            "reference_C": round(inputs.reference_C, 4),
        }
        wet = post.get("wetted_nodes", np.zeros(0, dtype=np.int64))
        pressure = result.fields["pressure"]
        summary["max_wall_pressure_Pa"] = round(float(pressure[wet].max()), 6) if len(wet) else 0.0
        summary["min_wall_pressure_Pa"] = round(float(pressure[wet].min()), 6) if len(wet) else 0.0
        local = result.fields["fluid_temperature"]
        summary["wall_fluid_temperature_C"] = [round(float(local[wet].min()), 4), round(float(local[wet].max()), 4)] if len(wet) \
            else [summary["min_fluid_temperature_C"], summary["max_fluid_temperature_C"]]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} cooled by flow"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        fluid = summary["wall_fluid_temperature_C"]
        low_fluid = min(fluid[0], *summary["inlet_temperature_C"])
        h = result.fields["heat_transfer_coefficient"]
        return {
            "temperature": (summary["min_temperature_C"], summary["max_temperature_C"]),
            "fluid_temperature": (low_fluid, max(fluid[1], low_fluid)),
            "wall_heat_flux": (min(summary["min_wall_heat_flux_W_m2"], 0.0), max(summary["max_wall_heat_flux_W_m2"], 0.0)),
            "heat_transfer_coefficient": (0.0, round(float(h.max()), 4)),
            "pressure": (summary["min_wall_pressure_Pa"], summary["max_wall_pressure_Pa"]),
        }

    def extras_head(self, summary: dict) -> dict:
        return {}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: ConjugateInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = self.turbulent.study_echo(inputs.flow, bare)
        flow = echo["flow"]
        flow["regime"] = inputs.regime
        flow["fluid"].update({"conductivity_W_mK": inputs.fluid_conductivity, "specific_heat_J_kgK": inputs.fluid_specific_heat})
        if inputs.flow.kind == "external":
            flow["temperature_C"] = inputs.inlet_C[0]
        else:
            for entry, celsius in zip(flow["inlets"], inputs.inlet_C):
                entry["temperature_C"] = celsius
        if inputs.regime == "laminar":
            for entry in flow.get("inlets", []):
                entry.pop("turbulence_intensity", None)
            flow.pop("turbulence_intensity", None)
        return {**echo, **heat_echo(inputs.thermal, bare)}

    def human_lines(self, summary: dict) -> list[str]:
        reynolds = summary["reynolds"]
        outlet = summary["outlet_temperature_C"]
        lines = [
            f"{summary['flow_kind']} {summary['regime']} flow of {summary['fluid']['name']}: Re {reynolds['value']:.4g}, "
            f"Pr {summary['prandtl']:.3g}",
            f"part hottest {summary['max_temperature_C']:g} °C at {summary['max_at_mm']} mm, coolest {summary['min_temperature_C']:g} °C",
            f"fluid in at {', '.join(f'{c:g}' for c in summary['inlet_temperature_C'])} °C"
            + (f", out at {outlet:.4g} °C" if outlet is not None else "")
            + f"; walls put {summary['heat_to_fluid_W']:.4g} W into it, it carries {summary['heat_carried_W']:.4g} W out",
        ]
        if summary["mean_heat_transfer_coefficient_W_m2K"] is not None:
            lines.append(f"mean heat transfer coefficient {summary['mean_heat_transfer_coefficient_W_m2K']:.4g} W/m²K"
                         + (f" (Nusselt {summary['nusselt']:.3g})" if summary.get("nusselt") is not None else "")
                         + f" over {summary['wetted_area_mm2']:.4g} mm² wetted")
        lines.append(f"pressure drop {summary['pressure_drop_Pa']:.4g} Pa, flow {summary['flow_rate_L_min']:.4g} L/min")
        return lines
