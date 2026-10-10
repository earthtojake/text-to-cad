"""Buckling: how many times this load the part takes before its shape gives way sideways.

Linear (eigenvalue) buckling. A static solve under the study's fixtures and
loads runs first, inside it (the prestress σ0, and everything a static result
says about it); then the geometric stiffness of that prestress,
``Kg = ∫ σ0_ij ∂u_k/∂x_i ∂v_k/∂x_j``, and the eigenproblem
``K φ = λ (-Kg) φ`` through :mod:`cadgen._internal.fea.eigen`: the smallest
positive load factors λ, each with its buckled shape. At λ times the load the
part buckles in that shape.

What it writes: one series frame per buckling mode (``Mode 1 · 13.3×``), each
shape scaled so its largest motion is 1 mm (mode 1's also as the displacement
a viewer deforms by), the prestress von Mises (the same in every frame), the
load factors, the critical load (factor times the applied resultant), and the
``buckling`` check: the first load factor against a margin (3 unless the study
says). Stdlib only at import; numeric imports live inside the methods.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, SolveContext
from cadgen._internal.fea.analyses.modal import (
    apply_eigen_rung, eigen_estimate, factor_text, finding, governing_field, held_supports, materials_of, max_frames,
    mode_series, mode_shapes, parse_modes, raw_checks, solver_method, where_moves,
)
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs

if TYPE_CHECKING:
    import numpy as np

__all__ = ["BucklingAnalysis", "BucklingInputs", "NO_BUCKLING_FACTOR"]

#: The load factor reported when the load does not compress the part enough to buckle it at all
#: (only tension, or a load factor past this): it passes any margin.
NO_BUCKLING_FACTOR = 1e6
#: The margin a buckling check keeps when the study names none (spec 5.4).
DEFAULT_MARGIN = 3.0


@dataclass(frozen=True)
class BucklingInputs(StaticInputs):
    #: How many buckling shapes to find (``modes``, default 3).
    modes: int = 3
    #: The study's buckling checks, parsed (the study's own parse names a bad one).
    checks: tuple[dict, ...] = ()


def _buckling_check(check: dict, factors: list[float]) -> dict:
    """The buckling check judged on the load factors, without its ``where``: λ1 against the margin."""
    margin = float(check.get("margin", DEFAULT_MARGIN))
    factor = factors[0] if factors else NO_BUCKLING_FACTOR
    ratio = 1.0 / factor
    status = "fails" if factor < 1 else "close" if factor < margin else "passes"
    judged = {"kind": "buckling", "label": check.get("label") or kinds.BUCKLING.default_label,
              "value": round(factor, 4), "limit": margin, "unit": "×", "ratio": round(ratio, 6),
              "close_at": round(1.0 / margin, 6), "margin": margin, "status": status}
    if factors:
        judged["at"] = {"frame": 0, "value": round(factor, 4), "unit": "×"}
    return judged


class BucklingAnalysis:
    name: ClassVar[str] = "buckling"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Buckling"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "modes"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    # The shape first (the field the viewer opens on), then the prestress's stress, the same in every
    # frame; the stress is the scalar the GLB is coloured by.
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("mode_shape", "_DISPLACEMENT", "mode shape", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
    )
    checks: ClassVar[tuple] = (kinds.BUCKLING,)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "buckling", "margin": DEFAULT_MARGIN},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "load_scale", "threshold", "mode")
    default_controls: ClassVar[dict[str, dict]] = {
        "mode": {"drives": "mode", "type": "enum", "options": None},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = (
        "iterative", "local_refine", "defeature", "linear_elements", "idealise", "symmetry", "reduce_modes",
    )
    noun: ClassVar[str] = "this load"
    #: What the ladder's two passes compare ("the first load factor moved 0.4% between ...").
    governing_word: ClassVar[str] = "the first load factor"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> BucklingInputs:
        static = StaticAnalysis().parse(document)
        return BucklingInputs(
            static.face_refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
            material_needs=static.material_needs, modes=parse_modes(document, 3), checks=raw_checks(document, kinds.BUCKLING),
        )

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def _wanted(self, ctx: SolveContext | None, inputs: BucklingInputs) -> int:
        return max(getattr(getattr(ctx, "plan", None), "modes", None) or inputs.modes, 1)

    def estimate(self, ctx: SolveContext, inputs: BucklingInputs):
        """The prestress (one static solve) and the buckling shapes (:func:`modal.eigen_estimate`)."""
        return eigen_estimate(ctx, self._wanted(ctx, inputs), static_solves=1)

    def apply(self, rung, ctx: SolveContext, inputs: BucklingInputs):
        """``iterative``: LOBPCG with multigrid for the shapes (the prestress goes iterative by itself on a
        large model). ``reduce_modes``: the first shape only, the one the check reads. The mesh rungs the shared way."""
        from cadgen._internal.fea import fit

        if rung == "reduce_modes":
            if self._wanted(ctx, inputs) <= 1:
                return None
            ctx.plan.modes = 1
            return fit.Step("reduce_modes", f"Found the first buckling shape only, of the {inputs.modes} asked for, to fit; "
                            "it is the one the check reads", None, None, detail={"from_modes": inputs.modes, "to_modes": 1})
        return apply_eigen_rung(self, rung, ctx, inputs, words="Found the buckling shapes with an iterative solver "
                                "(LOBPCG with multigrid) instead of factorising the stiffness")

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """What local_refine's two passes follow and compare: where shape 1 strains the part, and its load factor."""
        factors = result.scalars["load_factors"]
        return result.scalars["governing_field"], factors[0] if factors else NO_BUCKLING_FACTOR

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: BucklingInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import eigen, operators

        space = ctx.space
        warnings: list[str] = []
        prestress = StaticAnalysis().solve(ctx, inputs)
        outcome = prestress.scalars["outcome"]
        timings = {f"prestress_{key}": value for key, value in prestress.timings.items()}

        started = time.perf_counter()
        materials = materials_of(ctx)
        sigma = operators.stress(space, materials, outcome.u)
        Kg = operators.geometric_stiffness(space, sigma)
        K = operators.stiffness(space, materials)
        held = held_supports(space, inputs.fixtures, ctx.ordinal_of)
        fixed = held.fixed
        free = np.setdiff1d(np.arange(space.dofs), fixed)
        K, Kg = held.local(K), held.local(Kg)   # a sloped or curved roller: in its nodes' own axes
        Kff, Gff = K[free][:, free].tocsr(), (-Kg)[free][:, free].tocsr()
        timings["assemble_s"] = time.perf_counter() - started

        started = time.perf_counter()
        wanted = self._wanted(ctx, inputs)
        if solver_method(ctx, len(free)) == "lobpcg":
            precond = eigen.amg_preconditioner(Kff, space.locations[free], space.component[free])
            found = eigen.solve_generalized(Gff, Kff, min(wanted + 2, Kff.shape[0] - 1), precond=precond, which="LA",
                                            method="lobpcg", maxiter=200)
        else:
            # Largest in magnitude: the buckling load factors and those of the load reversed both stand clear
            # of the cluster at zero, so Lanczos converges fast even when the load only stretches the part.
            found = eigen.solve_generalized(Gff, Kff, min(2 * wanted + 2, Kff.shape[0] - 1), which="LM", method="arpack")
        warnings.extend(found.warnings)
        timings["eigen_s"] = time.perf_counter() - started

        # μ = 1/λ: the largest positive μ are the smallest load factors. A μ at round-off size is no
        # buckling at all (a load that only stretches the part, or one far too small to matter).
        mu = found.values
        tiny = 1e-9 * max(float(np.abs(mu).max()), 1e-300)
        positive = np.flatnonzero(mu > max(tiny, 1.0 / NO_BUCKLING_FACTOR))
        keep = positive[np.argsort(-mu[positive])][:wanted]
        factors = [float(1.0 / mu[i]) for i in keep]
        if not factors:
            warnings.append("this load does not compress the part enough to buckle it; it buckles only if the load is reversed"
                            if (mu < -tiny).any() else "this load does not buckle the part")
        full = np.zeros((space.dofs, max(len(keep), 1)))
        if factors:
            full[free] = found.vectors[:, keep]
            full = held.global_vector(full)
        frames = min(len(factors), max_frames(ctx)) or 1
        shapes, _ = mode_shapes(space, full[:, :frames])
        governing = governing_field(space, materials, full[:, 0] / max(float(np.abs(full[:, 0]).max()), 1e-300))
        applied = np.asarray(prestress.applied, dtype=float)
        result = AnalysisResult(
            dof_locations=prestress.dof_locations,
            vertices=prestress.vertices,
            tets=prestress.tets,
            boundary_quadratic=prestress.boundary_quadratic,
            element_dofs=prestress.element_dofs,
            fields={"von_mises": outcome.von_mises, "mode_shape": shapes[0]},
            fields_by_part=dict(prestress.fields_by_part),
            deformation=shapes[0],
            series=mode_series(factors, factor_text, "×", frames) if factors else None,
            frame_fields={"mode_shape": shapes} if factors else {},
            scalars={
                "outcome": outcome,
                "load_factors": factors,
                "applied_resultant_N": float(np.linalg.norm(applied)),
                "magnitudes": [np.linalg.norm(shape, axis=1) for shape in shapes],
                "governing_field": governing,
                "analysis_warnings": list(warnings),
                "part_refs": None if ctx.assembly is None else [part.ref for part in ctx.assembly.parts],
            },
            reactions=prestress.reactions,
            applied=prestress.applied,
            dofs=int(space.dofs),
            solver=f"{prestress.solver}; {found.how}",
            timings={**timings, **{k: v for k, v in prestress.timings.items() if k == 'mesh_to_fem_s'}},
            warnings=list(prestress.warnings) + warnings,
            solved=prestress.solved,
        )
        return result

    # -- checks, findings ----------------------------------------------------------------------------

    def needs_finer(self, result: AnalysisResult, inputs: BucklingInputs, check_results: list[dict]) -> bool:
        """Solve once more on a finer mesh when the buckling check is close to its margin."""
        checks = check_results or [_buckling_check(dict(check), result.scalars["load_factors"])
                                   for check in (inputs.checks or self.default_checks)]
        return any(check["status"] == "close" for check in checks)

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        factors = result.scalars["load_factors"]
        return {"from_size_mm": round(size_mm, 4), "from_load_factor": round(factors[0], 4) if factors else None,
                "size_mm": round(finer_mm, 4), "load_factor": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        factors = finer.scalars["load_factors"]
        refined["load_factor"] = round(factors[0], 4) if factors else None
        finer.scalars["coarser_load_factors"] = coarse.scalars["load_factors"]
        return finer

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: BucklingInputs) -> dict:
        judged = _buckling_check(dict(check), result.scalars["load_factors"])
        judged["where"] = where_moves(ctx, result, result.scalars["magnitudes"][0], index)
        return judged

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: BucklingInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        scalars = result.scalars
        factors = scalars["load_factors"]
        whole = "The assembly" if assembly else "The part"
        found: list[dict] = []
        judged = check_results or [self.judge(check, i, ctx, result, inputs) for i, check in enumerate(ctx.study.checks)]
        for check in judged:
            if check["status"] == "passes":
                continue
            factor, margin = check["value"], check["margin"]
            if check["status"] == "fails":
                sentence = f"{whole} buckles at {factor_text(factor)} this load: the load as given already buckles it"
                kind, severity = "buckles", "error"
            else:
                sentence = f"{whole} buckles at {factor_text(factor)} this load, under the {margin:g}× margin it should keep"
                kind, severity = "close_to_buckling", "warning"
            found.append(finding(severity, kind, sentence,
                                 f"first load factor {factor:.4g} against a margin of {margin:g} ({check['label']})",
                                 [{"text": "bulges most here", **check["where"]}]))
        if factors:
            node = int(scalars["magnitudes"][0].argmax())
            critical = factors[0] * scalars["applied_resultant_N"]
            found.append(finding(
                "info", "first_buckling_mode",
                f"First buckling at {factor_text(factors[0])} this load ({critical:.4g} N in all)",
                "linear buckling of the perfect shape; a real part, never perfectly straight or loaded dead centre, "
                "buckles earlier, so keep a margin", [{"text": "bulges most here", "ref": None,
                                                      "at": [round(float(c), 3) for c in result.dof_locations[node]]}],
            ))
            weakest = min(result.solved, key=lambda part: math.inf if checks.safety_factor(part) is None else checks.safety_factor(part))
            yields_at = checks.safety_factor(weakest)
            if yields_at is not None and yields_at < factors[0]:
                found.append(finding(
                    "warning", "yields_before_buckling",
                    f"{whole} yields at {factor_text(yields_at)} this load, before it buckles at {factor_text(factors[0])}",
                    f"peak stress {weakest.peak_MPa:.4g} MPa against a {weakest.yield_MPa:g} MPa yield; past yield the "
                    "material, not the shape, gives way first and the buckling factor is optimistic",
                    [{"text": "peak stress", "ref": weakest.peak_face, "at": [round(c, 3) for c in weakest.peak_at]}],
                ))
        else:
            found.append(finding("info", "no_buckling", f"{whole} does not buckle under this load: it is not compressed",
                                 "no positive load factor was found", []))
        coarser = scalars.get("coarser_load_factors")
        if coarser and factors:
            moved = abs(factors[0] - coarser[0]) / factors[0]
            found.append(finding(
                "warning" if moved > 0.05 else "info", "mesh_not_converged" if moved > 0.05 else "mesh_converged",
                f"The first load factor moved {moved * 100:.1f} % on a finer mesh ({factor_text(coarser[0])} to "
                f"{factor_text(factors[0])})",
                "the check was close, so the part was solved again finer; the finer answer is the one reported", [],
            ))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        from cadgen._internal.fea.outputs import auto_deformation_scale

        return requested or auto_deformation_scale(1.0, bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: BucklingInputs, check_results: list[dict]) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks

        scalars = result.scalars
        factors = scalars["load_factors"]
        outcome = scalars["outcome"]
        peak = int(outcome.von_mises.argmax())
        weakest = min(result.solved, key=lambda part: math.inf if checks.safety_factor(part) is None else checks.safety_factor(part))
        yields_at = checks.floored_factor(weakest)
        summary: dict[str, Any] = {
            "load_factors": [round(f, 4) for f in factors],
            "critical_load_N": round(factors[0] * scalars["applied_resultant_N"], 4) if factors else None,
            "modes": [{"mode": i + 1, "load_factor": round(f, 4)} for i, f in enumerate(factors)],
            "modes_requested": inputs.modes,
            "applied_force_N": [round(x, 4) for x in result.applied],
            "reaction_force_N": [round(sum(r[c] for r in result.reactions), 4) for c in range(3)],
            "max_von_mises_MPa": round(float(outcome.von_mises[peak]), 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in outcome.dof_locations[peak]],
            "yield_MPa": weakest.yield_MPa,
            # How many times this load before the weakest part yields: compare it with the first load factor.
            "yield_factor": yields_at,
            "max_prestress_displacement_mm": round(float(np.linalg.norm(outcome.displacement, axis=1).max()), 6),
            "deformation_scale": scalars["deformation_scale"],
        }
        if scalars.get("part_refs"):
            summary["parts"] = [
                {"ref": scalars["part_refs"][i], "name": part.part, "material": part.material_name,
                 "yield_MPa": part.yield_MPa, "peak_MPa": round(part.peak_MPa, 4)}
                for i, part in enumerate(result.solved)
            ]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} buckling"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"mode_shape": (0.0, 1.0), "von_mises": (0.0, summary["max_von_mises_MPa"])}

    def extras_head(self, summary: dict) -> dict:
        return {"load_factor": summary["load_factors"][0] if summary["load_factors"] else None}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: BucklingInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        return {**StaticAnalysis().study_echo(inputs, bare), "modes_requested": inputs.modes}

    def human_lines(self, summary: dict) -> list[str]:
        factors = summary.get("load_factors", [])
        if not factors:
            return ["no buckling: this load does not compress it enough to buckle"]
        lines = [f"buckles first at {factor_text(factors[0])} this load ({summary['critical_load_N']:g} N); load factors "
                 + ", ".join(factor_text(f) for f in factors)]
        if summary.get("yield_factor") is not None and summary["yield_factor"] < factors[0]:
            lines.append(f"yields at {factor_text(summary['yield_factor'])} this load, before it buckles")
        lines.append(f"prestress: max von Mises {summary['max_von_mises_MPa']:g} MPa, "
                     f"applied {summary['applied_force_N']} N, reactions {summary['reaction_force_N']} N")
        return lines
