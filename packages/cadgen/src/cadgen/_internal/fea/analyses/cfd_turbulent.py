"""Turbulent flow (lite): steady RANS (k-omega SST) through or around the part, and its push on the part.

The study is the laminar flow's (:mod:`.cfd`, spec 5.14): ``flow`` (``internal``
with inlets and outlets on sides of the part's bounding box, or ``external``
with a free stream), the fluid, and an optional ``map_to_structure``. Each
inlet (and an external flow) may add its ``turbulence_intensity`` (a share,
0.05 = 5 %). The fluid region and its mesh are the laminar flow's
(:mod:`..fluid_domain`); the flow is :mod:`..turbulence`: the Taylor-Hood mean
flow with Menter's k-omega SST eddy viscosity, SUPG-stabilised k and omega,
wall functions (Spalding's law, the first element kept in the log layer), and
pseudo-transient continuation from a Stokes start.

An inlet's ``"developed"`` profile is the settled turbulent flow of a long
straight duct of the opening's shape, solved on the opening by the same model
(axial speed, k and omega), so a pipe fed that way is fully developed from its
inlet; ``"uniform"`` is one speed with k and omega from the intensity.

What comes out is the laminar flow's: the wall ``pressure`` (Pa, gauge) and
``wall_shear`` (Pa, the wall function's rho u_tau^2) on the part's wetted faces,
the pressure drop, flow rates, fastest speed and force in the summary, checks
``pressure_drop`` and ``velocity``, and with ``map_to_structure`` the wall
pressure applied to a static solve of the part (stress and displacement join).
The summary adds the turbulence: the eddy-to-fluid viscosity ratio (mean and
largest), the wall function's y+ and the march's steps.

Its limits are written into every result: "Steady RANS (k-omega SST), wall
functions, incompressible". Below Re 2000 (internal, the inlet's hydraulic
diameter) or Re 1000 (external, the part's length) the flow is likely laminar:
it still solves, and says the laminar ``cfd`` is the better model there.

Stdlib only at import.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, SolveContext
from cadgen._internal.fea.analyses.cfd import (
    DENSITY, PASCAL, RE_LIMIT, SPEED, VISCOSITY, CfdAnalysis, CfdInputs, flux_of, flow_numbers, wall_to_part, wall_triangles,
)

__all__ = ["CfdTurbulentAnalysis", "CfdTurbulentInputs", "LIMITS", "laminar_sentence"]

LIMITS = ("Steady RANS (k-omega SST), wall functions, incompressible",)
#: Turbulence intensity by default: an internal inlet's, and an external free stream's.
INTENSITY = {"internal": 0.05, "external": 0.01}
#: A uniform internal inlet's turbulence length scale, as a share of its hydraulic diameter.
LENGTH_SHARE = 0.07
#: An external free stream's eddy-to-fluid viscosity ratio.
FREE_STREAM_RATIO = 10.0
#: Internal flow: elements across the narrowest opening's hydraulic diameter by default (the wall function
#: puts its distance at half the first element's depth, so the pipe needs a few more than laminar flow).
ACROSS = 10.0
#: The march's CFL (start, growth per step): by default, and with the ladder's continuation rung.
MARCH, MARCH_FAST = (5.0, 2.0), (50.0, 4.0)
#: The cost model, measured on the pipe benchmark: pseudo-time steps expected (an internal flow fed developed
#: starts near its answer; an external one starts from the free stream), fewer with the continuation rung; the
#: matrices factored afresh (a kept factor preconditions the other steps' solves, each about this share of a
#: factorisation); and assembly per step against the laminar solver's.
STEPS = {"internal": 15.0, "external": 40.0}
FAST_SHARE = 0.85
FACTORS, REUSE_SHARE, ASSEMBLIES = 3.0, 0.2, 2.0
#: A Krylov solve here (the rotated walls, the eddy viscosity's spread) costs this many laminar ones.
ITERATIVE_FACTOR = 4.0
#: A check is close once its value passes this share of its limit.
CLOSE_AT = 0.9


def laminar_sentence(value: float, limit: int) -> str:
    """The warning below the turbulent range, the same words everywhere."""
    return (f"Re {value:.0f} is in the laminar range (below Re {limit}): real flow there is likely laminar, so a "
            "turbulence model overstates the pressure drop; the laminar cfd analysis fits it better")


@dataclass(frozen=True)
class CfdTurbulentInputs(CfdInputs):
    #: Each inlet's turbulence intensity (a share), in the inlets' order; an external free stream's alone.
    intensities: tuple[float, ...] = ()
    intensity: float = INTENSITY["external"]


def _intensity(raw: Any, where: str) -> float:
    value = kinds.number(raw, where=where, positive=True)
    if value > 1.0:
        raise ValueError(f"{where}: a share of the mean speed, like 0.05 for 5 %; got {value:g}")
    return value


def _strip(document: dict) -> tuple[dict, tuple[float, ...], float]:
    """The study without its turbulence keys (what the laminar parser reads), and the intensities."""
    flow = document.get("flow")
    if not isinstance(flow, dict):
        return document, (), INTENSITY["external"]
    flow = dict(flow)
    intensity = INTENSITY["external"]
    if "turbulence_intensity" in flow:
        if flow.get("kind", "internal") != "external":
            raise ValueError("flow.turbulence_intensity: an internal flow gives it per inlet "
                             '(flow.inlets[i].turbulence_intensity, like 0.05)')
        intensity = _intensity(flow.pop("turbulence_intensity"), "flow.turbulence_intensity")
    intensities: list[float] = []
    if isinstance(flow.get("inlets"), list):
        inlets = []
        for index, entry in enumerate(flow["inlets"]):
            if isinstance(entry, dict):
                entry = dict(entry)
                intensities.append(_intensity(entry.pop("turbulence_intensity"), f"flow.inlets[{index}].turbulence_intensity")
                                   if "turbulence_intensity" in entry else INTENSITY["internal"])
            inlets.append(entry)
        flow["inlets"] = inlets
    return {**document, "flow": flow}, tuple(intensities), intensity


class CfdTurbulentAnalysis(CfdAnalysis):
    name: ClassVar[str] = "cfd_turbulent"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Turbulent flow"
    limits: ClassVar[tuple[str, ...]] = LIMITS
    ladder: ClassVar[tuple[str, ...]] = ("fluid_coarsen", "continuation", "iterative")
    noun: ClassVar[str] = "this flow"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> CfdTurbulentInputs:
        stripped, intensities, intensity = _strip(document)
        try:
            base = super().parse(stripped)
        except ValueError as exc:
            words = str(exc)
            if "an inlet takes opening, velocity_m_s and profile" in words:
                words = words.replace("velocity_m_s and profile", "velocity_m_s, profile and turbulence_intensity")
            elif "an external flow takes kind, fluid and velocity_m_s" in words:
                words = words.replace("kind, fluid and velocity_m_s", "kind, fluid, velocity_m_s and turbulence_intensity")
            raise ValueError(words) from None
        values = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}
        return CfdTurbulentInputs(**values, intensities=intensities, intensity=intensity)

    # -- sizes and the ladder ------------------------------------------------------------------------

    def sizes(self, ctx: SolveContext, setup) -> tuple[float, float]:
        plan = ctx.plan
        if setup.domain.kind == "internal" and not (plan is not None and plan.size_mm):
            wall = setup.wall_mm * 4.0 / ACROSS
            far = plan.fluid_far_size_mm if plan is not None and plan.fluid_far_size_mm else wall
            return wall, max(far, wall)
        return super().sizes(ctx, setup)

    def estimate(self, ctx: SolveContext, inputs: CfdTurbulentInputs):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses import cfd

        setup = self._setup(ctx, inputs)
        plan = ctx.plan
        wall, far = self.sizes(ctx, setup)
        tets = self._tets(setup, wall, far)
        n = 3.0 * cfd.NODES_PER_TET * tets + 0.25 * tets
        steps = STEPS[inputs.kind] * (FAST_SHARE if "continuation" in plan.taken else 1.0)
        build = cfd.BYTES_PER_TET * tets
        matrix = 12.0 * cfd.NNZ_PER_ROW * n
        if plan.solver == "iterative":
            per, memory = ITERATIVE_FACTOR * cfd.ITERATIVE_S * n, build + matrix * (1.0 + fit.AMG_COPIES)
            solves = steps + 1.0
        else:
            per, memory = cfd.DIRECT_S * n ** 1.5, build + matrix * 2.0 + 16.0 * cfd.FILL * n ** 1.5
            solves = FACTORS + REUSE_SHARE * steps
        seconds = cfd.MESH_S * tets + solves * per + steps * ASSEMBLIES * cfd.ASSEMBLE_S * tets
        if inputs.mapped:
            structure = fit.solid_estimate(ctx)
            memory = max(memory, structure.memory_bytes - fit.BASE_BYTES)
            seconds += structure.seconds
        return fit.Estimate(dofs=int(n), memory_bytes=int(fit.BASE_BYTES + memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: CfdTurbulentInputs):
        from cadgen._internal.fea import fit

        if rung == "continuation":
            if "continuation" in ctx.plan.taken:
                return None
            return fit.Step(
                "continuation",
                f"Marched to the steady turbulent flow in longer pseudo-time steps (CFL from {MARCH_FAST[0]:g}, growing "
                f"{MARCH_FAST[1]:g}x a step) so it settles in fewer solves", None, None,
                detail={"cfl_start": MARCH_FAST[0], "cfl_growth": MARCH_FAST[1]})
        return super().apply(rung, ctx, inputs)

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: CfdTurbulentInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import fluid_domain, turbulence
        from cadgen._internal.fea.femspace import FemSpace

        timings: dict[str, float] = {}
        setup = self._setup(ctx, inputs)
        domain = setup.domain
        timings["fluid_domain_s"] = domain.seconds
        wall, far = self.sizes(ctx, setup)
        if ctx.log:
            ctx.log(f"meshing the {domain.kind} flow region at {wall:.3g} mm" + (f" (free stream {far:.3g} mm)" if far > wall else ""))
        started = time.perf_counter()
        fluid = fluid_domain.mesh_fluid(domain, wall, far)
        space = FemSpace.build(fluid, 2)
        timings["fluid_mesh_s"] = time.perf_counter() - started

        started = time.perf_counter()
        face_of = {face.index: face for face in domain.faces}
        row_kind = np.array([face_of[int(o)].kind if int(o) in face_of else "wall" for o in fluid.boundary_ordinal])
        problem, developed = self._problem(space, fluid, face_of, row_kind, inputs, setup)
        timings["inlet_s"] = time.perf_counter() - started
        started = time.perf_counter()
        solver = "iterative" if ctx.plan.solver == "iterative" else "direct"
        march = MARCH_FAST if "continuation" in ctx.plan.taken else MARCH
        flow = turbulence.solve_rans(problem, solver=solver, cfl=march, log=ctx.log)
        timings["flow_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"turbulent flow: {flow.steps} pseudo-time steps, last change {flow.residual:.1e}")

        started = time.perf_counter()
        post = flow_numbers(space, fluid, face_of, row_kind, flow, inputs)
        self._wall_function_shear(space, row_kind, flow, post, inputs.fluid.density_kg_m3 * DENSITY)
        pressure, shear = wall_to_part(ctx, space, fluid, face_of, row_kind, post)
        timings["post_s"] = time.perf_counter() - started

        warnings = list(flow.warnings)
        analysis_warnings = []
        limit = RE_LIMIT[inputs.kind]
        reynolds = {"value": round(setup.reynolds, 2), "limit": limit, "kind": inputs.kind,
                    "length_mm": round(setup.length_mm, 4), "turbulent": setup.reynolds >= limit}
        if setup.reynolds < limit:
            analysis_warnings.append(laminar_sentence(setup.reynolds, limit))
        if post["imbalance"] > 0.01:
            analysis_warnings.append(f"the flow in and out differ by {post['imbalance']:.1%}: the solve did not settle; "
                                     "check the result with a finer mesh")
        if not flow.converged:
            analysis_warnings += [w for w in flow.warnings if w.startswith("the turbulent flow stopped")]

        fields = {"pressure": pressure, "wall_shear": shear}
        result = AnalysisResult(
            dof_locations=ctx.space.dof_locations, vertices=ctx.space.vertices, tets=ctx.space.tets,
            boundary_quadratic=ctx.space.boundary_quadratic, element_dofs=ctx.space.element_dofs, fields=fields,
            dofs=int(space.basis.N + flow.pressure_basis.N + 2 * flow.pressure_basis.N),
            solver=f"Taylor-Hood P2/P1 RANS, k-omega SST (P1, SUPG), {'GMRES + multigrid' if solver == 'iterative' else 'direct'}",
            timings={**timings, **{f"flow_{k}": v for k, v in flow.timings.items()}}, warnings=warnings,
            scalars={
                "post": post, "reynolds": reynolds, "flow": flow, "wall_mm": wall, "far_mm": far, "developed": developed,
                "fluid_mesh": {"elements": int(len(fluid.tets)), "nodes": int(len(fluid.nodes)),
                               "wall_size_mm": round(wall, 4), "far_size_mm": round(far, 4)},
                "analysis_warnings": analysis_warnings,
                "analysis_extras": {"turbulence": {"model": "k-omega SST", "reynolds": reynolds["value"],
                                                   "kind": inputs.kind, "viscosity_ratio_max": round(flow.nut_ratio[1], 2)}},
            },
        )
        if inputs.mapped:
            started = time.perf_counter()
            self._structure(ctx, inputs, result, pressure)
            result.timings["structure_s"] = time.perf_counter() - started
        return result

    def _problem(self, space, fluid, face_of, row_kind, inputs: CfdTurbulentInputs, setup):
        """The RANS problem: inlets (velocity, k and omega), slip sides, outlets, and the walls the law acts on."""
        import numpy as np

        from cadgen._internal.fea import navier_stokes, turbulence

        table = navier_stokes.vector_dofs(space)
        locations = space.dof_locations
        boundary = space.boundary_quadratic
        rho = inputs.fluid.density_kg_m3 * DENSITY
        nu = inputs.fluid.viscosity_Pa_s * VISCOSITY / rho
        values: dict[int, float] = {}
        k_in: dict[int, float] = {}
        w_in: dict[int, float] = {}
        outlets = []
        developed: dict[str, dict] = {}
        opening_of = np.array([face_of[int(o)].opening if int(o) in face_of else None for o in fluid.boundary_ordinal], dtype=object)
        inlet_rows = np.flatnonzero(row_kind == "inlet")
        outlet_rows = np.flatnonzero(row_kind == "outlet")
        if inputs.kind == "external":
            stream = np.array(inputs.velocity_m_s, dtype=float) * SPEED
            speed = float(np.linalg.norm(stream))
            k0, w0 = turbulence.inlet_turbulence(speed, inputs.intensity, setup.length_mm, nu, viscosity_ratio=FREE_STREAM_RATIO)
            for side in np.unique(opening_of[row_kind == "side"]):
                axis = "xyz".index(side[0])
                for node in np.unique(boundary[(row_kind == "side") & (opening_of == side)]):
                    values[int(table[node, axis])] = 0.0
            for node in np.unique(boundary[inlet_rows]):
                for c in range(3):
                    values[int(table[node, c])] = float(stream[c])
                if node < space.vertices:
                    k_in[int(node)], w_in[int(node)] = k0, w0
            outlets.append((space.facets_of_rows(outlet_rows), 0.0))
            length, free = setup.length_mm, (k0, w0)
        else:
            speed = 0.0
            for inlet, intensity in zip(inputs.inlets, inputs.intensities or (INTENSITY["internal"],) * len(inputs.inlets)):
                rows = np.flatnonzero((row_kind == "inlet") & (opening_of == inlet.opening))
                axis, high = "xyz".index(inlet.opening[0]), inlet.opening.endswith("max")
                inward = -1.0 if high else 1.0
                area = sum(face.area for face in face_of.values() if face.kind == "inlet" and face.opening == inlet.opening)
                perimeter = sum(face.perimeter for face in face_of.values() if face.kind == "inlet" and face.opening == inlet.opening)
                diameter = 4.0 * area / perimeter if perimeter > 0 else setup.length_mm
                mean = inlet.velocity_m_s * SPEED
                speed = max(speed, mean)
                if inlet.profile == "developed":
                    settled = turbulence.developed_turbulent(locations, boundary[rows], axis, mean, nu)
                    shape, ks, ws = settled.w, settled.k, settled.omega
                    developed[inlet.opening] = {"friction_factor": settled.friction_factor, "u_tau_mm_s": settled.u_tau,
                                                "converged": settled.converged}
                else:
                    k0, w0 = turbulence.inlet_turbulence(mean, intensity, LENGTH_SHARE * diameter, nu)
                    nodes = np.unique(boundary[rows])
                    shape = {int(node): mean for node in nodes}
                    ks = {int(node): k0 for node in nodes}
                    ws = {int(node): w0 for node in nodes}
                # The mean speed over the opening's true area: scale the profile so its flux is V A.
                flux = flux_of(space, rows, shape, axis)
                scale = mean * area / flux if flux > 0 else 1.0
                for node, w in shape.items():
                    for c in range(3):
                        values[int(table[node, c])] = inward * scale * w if c == axis else 0.0
                for node in ks:
                    if node < space.vertices:
                        k_in[node], w_in[node] = ks[node], ws[node]
            for outlet in inputs.outlets:
                rows = np.flatnonzero((row_kind == "outlet") & (opening_of == outlet.opening))
                outlets.append((space.facets_of_rows(rows), outlet.pressure_Pa / PASCAL / rho))
            length, free = setup.length_mm, (0.0, 0.0)
        dofs = np.fromiter(values.keys(), dtype=np.int64, count=len(values))
        given = np.fromiter(values.values(), dtype=float, count=len(values))
        inflow = np.fromiter(k_in.keys(), dtype=np.int64, count=len(k_in))
        problem = turbulence.RansProblem(
            space=space, rho=rho, nu=nu, dirichlet=dofs, values=given, wall_rows=np.flatnonzero(row_kind == "wall"),
            inflow_nodes=inflow, inflow_k=np.array([k_in[int(n)] for n in inflow]),
            inflow_omega=np.array([w_in[int(n)] for n in inflow]), outlets=outlets, speed=speed, length=length,
            kind=inputs.kind, free_k=free[0], free_omega=free[1],
            inlet_facets=space.facets_of_rows(inlet_rows) if len(inlet_rows) else None,
            outlet_facets=space.facets_of_rows(outlet_rows) if len(outlet_rows) else None,
        )
        return problem, developed

    @staticmethod
    def _wall_function_shear(space, row_kind, flow, post: dict, rho: float) -> None:
        """The wall shear is the wall function's, rho u_tau^2 along the slip; the force on the part follows it."""
        import numpy as np

        shear = np.zeros(space.scalar_count)
        traction = np.zeros((space.scalar_count, 3))
        if len(flow.wall_nodes):
            tau = rho * flow.wall_u_tau ** 2                       # MPa
            slip = flow.wall_slip
            length = np.linalg.norm(slip, axis=1)
            shear[flow.wall_nodes] = tau
            traction[flow.wall_nodes] = tau[:, None] * slip / np.where(length > 0, length, 1.0)[:, None]
        post["shear_nodes_Pa"] = shear * PASCAL
        walls = np.flatnonzero(row_kind == "wall")
        if len(walls):
            # Force of the fluid on the part: its pressure along the wall's normal (out of the fluid) and its drag.
            triangles, area, normal = wall_triangles(space, walls)
            mids = triangles[:, 3:]
            pressure = post["pressure_nodes_Pa"] / PASCAL
            per = pressure[mids].mean(axis=1)[:, None] * normal + traction[mids].mean(axis=1)
            post["force_N"] = (area[:, None] * per).sum(axis=0)

    # -- what is written -----------------------------------------------------------------------------

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: CfdTurbulentInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        found: list[dict] = []
        if result.solved:
            found += checks.findings(result.solved[0])
        reynolds = result.scalars["reynolds"]
        if not reynolds["turbulent"]:
            found.append({
                "check": "fea", "severity": "warning", "type": "reynolds_laminar_range",
                "summary": laminar_sentence(reynolds["value"], reynolds["limit"]),
                "description": f"Re {reynolds['value']:.0f} from the {'inlet hydraulic diameter' if inputs.kind == 'internal' else 'part length'} "
                               f"of {reynolds['length_mm']:.4g} mm",
                "items": [],
            })
        flow = result.scalars["flow"]
        if not flow.converged:
            found.append({
                "check": "fea", "severity": "warning", "type": "turbulent_unsettled",
                "summary": f"The turbulent flow was still changing by {flow.residual:.1e} of its speed a step when it stopped",
                "description": "its numbers are approximate; a finer or a coarser mesh may settle", "items": [],
            })
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
        post = result.scalars["post"]
        if post["imbalance"] > 0.01:
            found.append({
                "check": "fea", "severity": "warning", "type": "flow_balance",
                "summary": f"The flow in and out differ by {post['imbalance']:.1%}: the flow may not have settled",
                "description": "the solve leaves fluid unaccounted for; a finer mesh should close it", "items": [],
            })
        return found

    def summary(self, result: AnalysisResult, inputs: CfdTurbulentInputs, check_results: list[dict]) -> dict:
        import numpy as np

        post, flow, reynolds = result.scalars["post"], result.scalars["flow"], result.scalars["reynolds"]
        wet = post["wetted_nodes"]
        pressure, shear = result.fields["pressure"], result.fields["wall_shear"]
        summary: dict[str, Any] = {
            "flow_kind": inputs.kind,
            "fluid": {"name": inputs.fluid.name, "density_kg_m3": inputs.fluid.density_kg_m3,
                      "viscosity_Pa_s": inputs.fluid.viscosity_Pa_s},
            "reynolds": dict(reynolds),
            "max_velocity_m_s": round(post["max_velocity_m_s"], 6),
            "max_velocity_at_mm": [round(float(c), 3) for c in post["max_velocity_at"]],
            "flow_rate_m3_s": float(f"{post['flow_rate_m3_s']:.6g}"),
            "flow_rate_L_min": round(post["flow_rate_m3_s"] * 60000.0, 6),
            "outflow_rate_m3_s": float(f"{post['outflow_rate_m3_s']:.6g}"),
            "flow_balance": round(post["imbalance"], 6),
            "pressure_drop_Pa": round(post["pressure_drop_Pa"], 6),
            "inlet_pressure_Pa": round(post["inlet_pressure_Pa"], 6),
            "outlet_pressure_Pa": round(post["outlet_pressure_Pa"], 6),
            "max_wall_pressure_Pa": round(float(pressure[wet].max()), 6) if len(wet) else 0.0,
            "min_wall_pressure_Pa": round(float(pressure[wet].min()), 6) if len(wet) else 0.0,
            "max_wall_shear_Pa": round(float(shear[wet].max()), 6) if len(wet) else 0.0,
            "force_N": [round(float(c), 9) for c in post["force_N"]],
            "turbulence": {
                "model": "k-omega SST", "wall_treatment": "wall functions (Spalding, y+ >= 30)",
                "viscosity_ratio_mean": round(flow.nut_ratio[0], 3), "viscosity_ratio_max": round(flow.nut_ratio[1], 3),
                "wall_yplus": {"min": round(flow.yplus[0], 2), "mean": round(flow.yplus[1], 2), "max": round(flow.yplus[2], 2)},
            },
            "solve": {"steps": flow.steps, "linear_solves": flow.linear_solves, "factorizations": flow.factorizations, "residual": float(f"{flow.residual:.3g}"),
                      "converged": flow.converged, "solver": flow.solver},
            "fluid_mesh": dict(result.scalars["fluid_mesh"]),
            "deformation_scale": result.scalars.get("deformation_scale"),
        }
        developed = result.scalars.get("developed") or {}
        if developed:
            summary["developed_inlets"] = {opening: {"friction_factor": round(entry["friction_factor"], 6)}
                                           for opening, entry in developed.items()}
        if result.solved:
            from cadgen._internal.fea import checks
            from cadgen._internal.fea.analyses.static import floored

            outcome = result.scalars["outcome"]
            magnitude = np.linalg.norm(outcome.displacement, axis=1)
            solved = result.solved[0]
            summary.update({
                "max_von_mises_MPa": round(float(outcome.von_mises.max()), 4),
                "max_von_mises_at_mm": [round(c, 3) for c in solved.peak_at],
                "yield_MPa": solved.yield_MPa,
                "max_displacement_mm": round(float(magnitude.max()), 6),
                "safety_factor": floored(checks.safety_factor(solved)),
            })
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} turbulent flow"

    def study_echo(self, inputs: CfdTurbulentInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = super().study_echo(inputs, bare)
        flow = echo["flow"]
        if inputs.kind == "external":
            flow["turbulence_intensity"] = inputs.intensity
        else:
            for entry, intensity in zip(flow["inlets"], inputs.intensities):
                entry["turbulence_intensity"] = intensity
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        reynolds, solve, turbulence = summary["reynolds"], summary["solve"], summary["turbulence"]
        lines = [
            f"{summary['flow_kind']} turbulent flow of {summary['fluid']['name']}: Re {reynolds['value']:.4g} "
            f"({'turbulent' if reynolds['turbulent'] else 'in the laminar range, below Re ' + str(reynolds['limit'])}), "
            "k-omega SST with wall functions",
            f"pressure drop {summary['pressure_drop_Pa']:.4g} Pa, flow {summary['flow_rate_L_min']:.4g} L/min, "
            f"fastest {summary['max_velocity_m_s']:.4g} m/s",
            f"wall pressure {summary['min_wall_pressure_Pa']:.4g} to {summary['max_wall_pressure_Pa']:.4g} Pa, "
            f"wall shear up to {summary['max_wall_shear_Pa']:.4g} Pa, force on the part {summary['force_N']} N",
            f"eddy viscosity up to {turbulence['viscosity_ratio_max']:.4g}x the fluid's (mean {turbulence['viscosity_ratio_mean']:.3g}x), "
            f"wall y+ {turbulence['wall_yplus']['min']:.3g} to {turbulence['wall_yplus']['max']:.3g}",
            f"solved in {solve['steps']} pseudo-time steps, last change {solve['residual']:.1e}"
            + ("" if solve["converged"] else " (not settled)"),
        ]
        if "max_von_mises_MPa" in summary:
            lines.append(f"under the flow's pressure: peak von Mises {summary['max_von_mises_MPa']:.4g} MPa, "
                         f"largest displacement {summary['max_displacement_mm']:.4g} mm"
                         + (f", safety factor {summary['safety_factor']:g}" if summary.get("safety_factor") is not None else ""))
        return lines
