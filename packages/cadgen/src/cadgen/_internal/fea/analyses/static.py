"""Static: will it hold, and how far does it move. Linear elasticity under fixtures, face loads and body loads.

This is the solve ``cadgen fea`` always ran, moved here from ``run.py``
unchanged: the call into :func:`cadgen._internal.fea.solve.solve_linear_static`
(through the module, so a test may patch it), the per-part numbers the checks
read (:class:`~cadgen._internal.fea.checks.Solved`), the stress and
displacement checks, the findings, the summary and the GLB extras. New here:
``gravity`` and ``acceleration`` body loads (in g, no faces). Stdlib only at
import; numeric imports live inside the methods.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, SolveContext
from cadgen._internal.fea.study import _DEFAULT_CONTROLS, DEFAULT_CHECKS, VIEW_DRIVES, Fixture, Load, parse_fixtures, parse_loads

if TYPE_CHECKING:
    from cadgen._internal.fea.checks import Solved

__all__ = ["StaticAnalysis", "StaticInputs"]

#: Standard gravity, mm/s^2 (operators.G0_MM_S2, kept here so parsing imports no numerics).
G0_MM_S2 = 9806.65


@dataclass(frozen=True)
class StaticInputs(Inputs):
    fixtures: tuple[Fixture, ...] = ()
    #: Every load in the study's order: on faces (force, pressure) and on the whole part (gravity, acceleration).
    loads: tuple[Load, ...] = ()
    #: Material properties these loads need beyond the analysis's own: density for a body load.
    material_needs: frozenset[str] = frozenset()

    @property
    def surface_loads(self) -> tuple[Load, ...]:
        return tuple(load for load in self.loads if not load.body)

    @property
    def body_accelerations(self) -> list[tuple[float, float, float]]:
        """Each body load as the acceleration b (mm/s^2) of ∫ ρ b·v: gravity is g, an accelerated part -a."""
        sign = {"gravity": 1.0, "acceleration": -1.0}
        return [tuple(sign[load.type] * G0_MM_S2 * c for c in load.vector_g) for load in self.loads if load.body]


def _solved(volume, outcome, study, ordinal_of: dict[str, int], part: str, fixtures) -> "Solved":
    """The numbers of one solve the checks read, faces as bare ``#o1.fN`` refs.

    The study may name a face with a document prefix (``part.step#o1.f17``) or a
    label; both go through the ordinal to the scene's own ref, so a fixture and
    the peak's face compare as the same string.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    fixed_ordinals = {ordinal_of[ref] for fixture in fixtures for ref in fixture.faces}
    magnitude = np.linalg.norm(outcome.displacement, axis=1)
    peak_node = int(outcome.von_mises.argmax())
    moved_node = int(magnitude.argmax())
    extent = volume.nodes.max(axis=0) - volume.nodes.min(axis=0)
    return Solved(
        material_name=study.material.name,
        yield_MPa=study.material.yield_strength,
        peak_MPa=float(outcome.von_mises[peak_node]),
        peak_gauss_MPa=outcome.von_mises_gauss_max,
        peak_at=tuple(float(c) for c in outcome.dof_locations[peak_node]),
        peak_face=_peak_face(volume, outcome, peak_node, fixed_ordinals),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude[moved_node]),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(extent)),
        margin=study.margin,
        coarser_peak_MPa=None,
        part=part,
        dofs=outcome.dofs,
    )


def _solved_part(volume, outcome, study, plan, index: int, ordinal_of: dict[str, int], fixtures) -> "Solved":
    """One part of a solved assembly, as the checks read it: its own peak, yield and displacement.

    The part's elements pick its share of the fields; faces are those of the part alone.
    """
    import numpy as np

    from cadgen._internal.fea.checks import Solved

    part, material = plan.parts[index], plan.materials[index]
    rows = volume.domain == index
    dofs = np.unique(outcome.element_dofs[rows])
    field = outcome.von_mises_parts[index]  # the part's own stress, not smoothed across a joint
    own = {position for position, fp in volume.faces.items() if fp.ref.startswith(f"{part.ref}.f")}
    fixed_ordinals = {ordinal_of[ref] for fixture in fixtures for ref in fixture.faces} & own
    magnitude = np.linalg.norm(outcome.displacement[dofs], axis=1)
    peak_node = int(dofs[field[dofs].argmax()])
    moved_node = int(dofs[magnitude.argmax()])
    corners = volume.nodes[np.unique(volume.tets[rows][:, :4])]
    here = outcome.dof_locations[peak_node]
    joint_with, nearest = None, 0.5 * volume.max_h
    rim = np.unique(volume.boundary)
    for pair, triangles in volume.interface_triangles.items():
        if index not in pair:
            continue
        edge = np.intersect1d(np.unique(triangles), rim)
        if len(edge) == 0:
            continue
        gap = float(np.linalg.norm(volume.nodes[edge] - here, axis=1).min())
        if gap <= nearest:
            joint_with, nearest = plan.names[pair[1] if pair[0] == index else pair[0]], gap
    return Solved(
        material_name=material.name,
        yield_MPa=material.yield_strength,
        peak_MPa=float(field[peak_node]),
        peak_gauss_MPa=float(outcome.element_von_mises_gauss[rows].max()),
        peak_at=tuple(float(c) for c in here),
        peak_face=_peak_face(volume, outcome, peak_node, fixed_ordinals, own),
        fixed_faces=tuple(volume.faces[ordinal].ref for ordinal in sorted(fixed_ordinals)),
        max_displacement_mm=float(magnitude.max()),
        displacement_at=tuple(float(c) for c in outcome.dof_locations[moved_node]),
        bbox_diagonal_mm=float(np.linalg.norm(corners.max(axis=0) - corners.min(axis=0))),
        margin=study.margin,
        coarser_peak_MPa=None,
        part=plan.names[index],
        dofs=outcome.dofs,
        assembly=True,
        joint_with=joint_with,
    )


def _peak_face(
    volume, outcome, peak_node: int, fixed_ordinals: set[int], own: set[int] | None = None
) -> str | None:
    """The ``#o1.fN`` face the peak sits on, or ``None`` inside the part and away from every fixed face.

    The peak is at a fixture, and names that fixed face, when its node touches a
    fixed face (a node on an edge touches two) or lies within half an element
    of a fixed face's boundary nodes: a peak on a clamp's rim is a peak at the
    clamp, whichever face the mesher gave the rim node. Otherwise the face
    whose boundary triangles hold the node. In an assembly ``own`` limits the
    faces to the part the peak is in: a node on a joint is on both parts' faces."""
    import numpy as np

    rows = (outcome.boundary_quadratic == peak_node).any(axis=1)
    ordinals = sorted({int(o) for o in volume.boundary_ordinal[rows]} - {0})
    if own is not None:
        ordinals = [ordinal for ordinal in ordinals if ordinal in own]
        fixed_ordinals = fixed_ordinals & own
    touched = [ordinal for ordinal in ordinals if ordinal in fixed_ordinals]
    if touched:
        return volume.faces[touched[0]].ref
    here = outcome.dof_locations[peak_node]
    nearest: tuple[float, int] | None = None
    for ordinal in sorted(fixed_ordinals):
        nodes = np.unique(outcome.boundary_quadratic[volume.boundary_ordinal == ordinal])
        if len(nodes) == 0:
            continue
        gap = float(np.linalg.norm(outcome.dof_locations[nodes] - here, axis=1).min())
        if gap <= 0.5 * volume.max_h and (nearest is None or gap < nearest[0]):
            nearest = (gap, ordinal)
    if nearest is not None:
        return volume.faces[nearest[1]].ref
    return volume.faces[ordinals[0]].ref if ordinals else None


def _unfold(volume, outcome, planes):
    """The solved half (or quarter) mirrored back into the whole part: its mesh and every field the checks read."""
    import dataclasses

    import numpy as np

    from cadgen._internal.fea import symmetry

    for plane in reversed(planes):
        whole, keep = symmetry.unfold_volume(volume, plane)
        locations, scalars, vectors, boundary, tets, elements, vertices = symmetry.unfold_fields(
            plane, outcome.vertices, outcome.dof_locations, keep, scalars={"von_mises": outcome.von_mises},
            vectors={"displacement": outcome.displacement}, boundary=outcome.boundary_quadratic, tets=outcome.tets,
            element_dofs=outcome.element_dofs,
        )
        outcome = dataclasses.replace(
            outcome, dof_locations=locations, von_mises=scalars["von_mises"], displacement=vectors["displacement"],
            boundary_quadratic=boundary, tets=tets, element_dofs=elements, vertices=vertices,
            element_von_mises_gauss=np.concatenate([outcome.element_von_mises_gauss] * 2),
            reactions=[symmetry.unfold_force(plane, r) for r in outcome.reactions],
            applied=symmetry.unfold_force(plane, outcome.applied), u=None,
        )
        volume = whole
    return volume, outcome


def _floored(factor: float | None) -> float | None:
    # Floored, so a factor just under a threshold is never shown as reaching it.
    return None if factor is None else math.floor(factor * 1000) / 1000


class StaticAnalysis:
    name: ClassVar[str] = "static"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Strength"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = DEFAULT_CHECKS
    drives: ClassVar[tuple[str, ...]] = VIEW_DRIVES
    default_controls: ClassVar[dict[str, dict]] = _DEFAULT_CONTROLS
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "defeature", "linear_elements", "idealise", "symmetry")
    #: The noun of the viewer's load control and the verdict's takeaway ("OK up to 1.6× this load").
    noun: ClassVar[str] = "this load"
    #: What the ladder's two passes compare, in its words ("peak stress moved 2.1% between ...").
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> StaticInputs:
        fixtures = parse_fixtures(document)
        loads = parse_loads(document)
        refs = tuple(dict.fromkeys(ref for group in (*fixtures, *loads) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        needs = frozenset({"density"}) if any(load.body for load in loads) else frozenset()
        return StaticInputs(refs, anchors, True, fixtures=fixtures, loads=loads, material_needs=needs)

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: StaticInputs):
        """One elastic solve on the plan's mesh (fit.solid_estimate): the space, the matrix, the solver's own."""
        from cadgen._internal.fea import fit

        return fit.solid_estimate(ctx)

    def apply(self, rung, ctx: SolveContext, inputs: StaticInputs):
        from cadgen._internal.fea import fit

        return fit.apply_generic(rung, self, ctx, inputs)

    def symmetric_about(self, plane, inputs: StaticInputs, ctx: SolveContext) -> bool:
        """Whether every fixture, load and check is its own mirror image about ``plane``: the same set of
        faces, and no force or body load across it. One part only."""
        if ctx.assembly is not None:
            return False
        axis = plane.component
        from cadgen._internal.fea.materials import mirror_symmetric

        # An orthotropic material mirrors onto itself only about a plane across one of its own directions.
        if not all(material is None or mirror_symmetric(material, axis) for material in (getattr(ctx, "materials", None) or ())):
            return False

        def maps_onto_itself(refs) -> bool:
            ordinals = {ctx.ordinal_of[ref] for ref in refs}
            return {plane.mirror.get(o) for o in ordinals} == ordinals

        checks = ctx.study.checks if ctx.study is not None else ()
        groups = [fixture.faces for fixture in inputs.fixtures] + [load.faces for load in inputs.surface_loads]
        groups += [tuple(check["faces"]) for check in checks if check.get("faces")]
        if not all(maps_onto_itself(group) for group in groups):
            return False
        for load in inputs.loads:
            vector = load.vector_g if load.body else (load.vector if load.type == "force" else None)
            if vector is not None and abs(vector[axis]) > 1e-9 * max(math.sqrt(sum(c * c for c in vector)), 1e-300):
                return False
        return True

    def governing(self, result: AnalysisResult):
        """local_refine follows the stress field; two passes compare the weakest part's peak."""
        return result.fields["von_mises"], self.weakest(result).peak_MPa

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: StaticInputs) -> AnalysisResult:
        import dataclasses

        from cadgen._internal.fea import fit, solve

        # The ladder's idealise rung: a thin plate as a shell, a slender bar as a beam (fit.IDEALISERS).
        if (idealised := fit.solve_idealised(self, ctx, inputs)) is not None:
            return idealised
        volume, study, plan = ctx.volume, ctx.study, ctx.assembly
        materials = study.material if plan is None else plan.materials
        extra: dict[str, Any] = {}
        if any(load.body for load in inputs.loads):
            extra["body_loads"] = inputs.body_accelerations
        if ctx.space is not None:
            extra["space"] = ctx.space
        loads = study.loads if not extra.get("body_loads") else inputs.surface_loads
        fit_plan = ctx.plan
        planes = list(fit_plan.prepared.planes) if fit_plan is not None and fit_plan.prepared is not None else []
        if fit_plan is not None and fit_plan.solver != "direct":
            extra["solver"] = fit_plan.solver
        if planes:
            # The half carries its share of each force (its faces are that share of the faces); a pressure,
            # a body load and a fixture act on what is there. The cut faces may slide in their plane only.
            share = 0.5 ** len(planes)
            loads = tuple(dataclasses.replace(load, vector=tuple(share * c for c in load.vector)) if load.type == "force" else load
                          for load in loads)
            extra["rollers"] = [((p.ordinal,), p.component) for p in planes]
        outcome = solve.solve_linear_static(
            volume, materials, inputs.fixtures, loads, ctx.ordinal_of, log=ctx.log, automatic=ctx.automatic, **extra
        )
        if planes:
            volume, outcome = _unfold(volume, outcome, planes)
            ctx.volume = volume
        if plan is None:
            solved = [_solved(volume, outcome, study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
        else:
            solved = [_solved_part(volume, outcome, study, plan, index, ctx.ordinal_of, inputs.fixtures) for index in range(len(plan.parts))]
        return self._result(outcome, solved, plan)

    def _result(self, outcome, solved, plan) -> AnalysisResult:
        return AnalysisResult(
            dof_locations=outcome.dof_locations,
            vertices=outcome.vertices,
            tets=outcome.tets,
            boundary_quadratic=outcome.boundary_quadratic,
            element_dofs=outcome.element_dofs,
            fields={"von_mises": outcome.von_mises, "displacement": outcome.displacement},
            fields_by_part={} if outcome.von_mises_parts is None else {"von_mises": outcome.von_mises_parts},
            deformation=outcome.displacement,
            scalars={"outcome": outcome, "part_refs": None if plan is None else [part.ref for part in plan.parts]},
            reactions=list(outcome.reactions),
            applied=tuple(outcome.applied),
            dofs=outcome.dofs,
            solver=outcome.solver,
            timings=dict(outcome.timings),
            warnings=outcome.warnings,
            solved=solved,
        )

    @staticmethod
    def weakest(result: AnalysisResult) -> "Solved":
        from cadgen._internal.fea import checks

        return min(result.solved, key=lambda part: math.inf if checks.safety_factor(part) is None else checks.safety_factor(part))

    # -- the automatic finer solve -------------------------------------------------------------------

    def needs_finer(self, result: AnalysisResult, inputs: StaticInputs, check_results: list[dict]) -> bool:
        from cadgen._internal.fea import checks

        return checks.needs_finer(checks.safety_factor(self.weakest(result)))

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        """The sidecar's ``refined``, before the finer solve: the first solve's size and governing peak."""
        weakest = self.weakest(result)
        return {
            "from_size_mm": round(size_mm, 4),
            "from_max_von_mises_MPa": round(weakest.peak_MPa, 4),
            "size_mm": round(finer_mm, 4),
            "max_von_mises_MPa": None,
            **({"part": weakest.part} if assembly else {}),
        }

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        """The finer solve is the one written; the first solve's peak rides along for convergence only."""
        import dataclasses

        index = next(i for i, part in enumerate(coarse.solved) if part is self.weakest(coarse))
        # Like with like: the finer peak of the part whose first-solve peak is recorded.
        refined["max_von_mises_MPa"] = round(finer.solved[index].peak_MPa, 4)
        finer.solved = [
            dataclasses.replace(fine, coarser_peak_MPa=first.peak_MPa, coarser_dofs=coarse.dofs)
            for fine, first in zip(finer.solved, coarse.solved)
        ]
        return finer

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: StaticInputs) -> dict:
        """The stress check is the weakest part's. A displacement check takes the largest displacement
        magnitude over the nodes of its faces' surface triangles (faces of several parts alike), else
        over the whole model, and names the face it is on."""
        import numpy as np

        from cadgen._internal.fea import checks

        if check["kind"] == "stress":
            return checks.stress_check(self.weakest(result), label=check.get("label"))
        magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
        peak = kinds.field_max_over(
            magnitude, tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        return checks.displacement_check(
            peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces, label=check.get("label"),
        )

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: StaticInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        if not assembly:
            return checks.findings(self.weakest(result))
        return checks.assembly_findings(result.solved)

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        import numpy as np

        from cadgen._internal.fea.outputs import auto_deformation_scale

        magnitude = np.linalg.norm(result.fields["displacement"], axis=1)
        return requested or auto_deformation_scale(float(magnitude.max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: StaticInputs, check_results: list[dict]) -> dict:
        """The one place the numbers are rounded; the GLB's extras and the sidecar are derived from it."""
        import numpy as np

        from cadgen._internal.fea import checks

        outcome = result.scalars["outcome"]
        magnitude = np.linalg.norm(outcome.displacement, axis=1)
        max_disp_index = int(magnitude.argmax())
        max_vm_index = int(outcome.von_mises.argmax())
        reaction_total = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))
        solved = self.weakest(result)
        summary = {
            "max_von_mises_MPa": round(float(outcome.von_mises[max_vm_index]), 4),
            "max_von_mises_gauss_MPa": round(outcome.von_mises_gauss_max, 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_vm_index]],
            "yield_MPa": result.scalars["yield_MPa"],
            "max_displacement_mm": round(float(magnitude.max()), 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in outcome.dof_locations[max_disp_index]],
            "applied_force_N": [round(x, 4) for x in outcome.applied],
            "reaction_force_N": [round(x, 4) for x in reaction_total],
            "deformation_scale": result.scalars["deformation_scale"],
        }
        summary["safety_factor"] = _floored(checks.safety_factor(solved))
        refs = result.scalars["part_refs"]
        if refs is not None:
            # The headline is the weakest part: its yield and safety factor; the peak and the colours span the assembly.
            summary["yield_MPa"] = solved.yield_MPa
            summary["weakest_part"] = solved.part
            summary["weakest_part_peak_MPa"] = round(solved.peak_MPa, 4)
            summary["weakest_part_peak_at_mm"] = [round(c, 3) for c in solved.peak_at]
            summary["parts"] = [
                {
                    "ref": refs[i],
                    "name": part.part,
                    "material": part.material_name,
                    "yield_MPa": part.yield_MPa,
                    "peak_MPa": round(part.peak_MPa, 4),
                    "peak_gauss_MPa": round(part.peak_gauss_MPa, 4),
                    "peak_at_mm": [round(c, 3) for c in part.peak_at],
                    "safety_factor": _floored(checks.safety_factor(part)),
                    "max_displacement_mm": round(part.max_displacement_mm, 6),
                }
                for i, part in enumerate(result.solved)
            ]
        # Each check the study asked for (the stress check alone by default), judged at the load as solved.
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} von Mises"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"von_mises": (0.0, summary["max_von_mises_MPa"]), "displacement": (0.0, summary["max_displacement_mm"])}

    def extras_head(self, summary: dict) -> dict:
        """Static's keys right after the deformation scale: the summary's safety factor, for the viewer's plain line."""
        return {"safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        """What the viewer reads for an assembly (`_PART` indexes `parts`): the weakest part's line."""
        return {
            "weakest_part": summary["weakest_part"],
            "weakest_part_peak_MPa": summary["weakest_part_peak_MPa"],
            "max_displacement_mm": summary["max_displacement_mm"],
            "parts": [
                {key: part[key] for key in ("ref", "name", "material", "yield_MPa", "peak_MPa", "safety_factor", "max_displacement_mm")}
                for part in summary["parts"]
            ],
        }

    def study_echo(self, inputs: StaticInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        def load_echo(load: Load) -> dict:
            if load.body:
                return {"type": load.type, "vector_g": [float(c) for c in load.vector_g]}
            return {"type": load.type, "faces": bare(load.faces),
                    **({"vector_N": [float(c) for c in load.vector]} if load.type == "force" else {"pressure_MPa": load.pressure})}

        return {
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "loads": [load_echo(load) for load in inputs.loads],
        }

    def human_lines(self, summary: dict) -> list[str]:
        """Static's own CLI lines are :class:`cadgen.results.FeaResult`'s, unchanged."""
        return []
