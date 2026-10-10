"""Composite: a laminated plate, ply by ply. Tier 3 (lite).

The study gives the plies (``layup``, from the bottom face up: each its ply
material, angle and thickness), the ply materials (``laminae``: E1, E2, nu12,
G12 and the strengths Xt, Xc, Yt, Yc, S) and, optionally, the plies' 0°
direction (``layup_axis``; the global X axis, or Y for a plate facing X, laid
into the plate). Fixtures and loads are static's.

The part must be a flat plate of even thickness (shell.py's rules, any
thickness), and the plies must add up to that thickness. A thin plate
(thickness under 5 % of its smaller span) is solved on its mid-surface as a
Reissner-Mindlin shell whose stiffness is classical laminate theory's A, B and
D (laminate.py), with the plies' transverse shear: fast, and what CLT is for. A
thick one is meshed as a solid in which every point takes its ply's 3D
orthotropic stiffness (laminate.LayeredMaterial). Either way each ply's
in-plane stresses, in its own fibre axes, are judged by Tsai-Wu and by max
stress at its top and bottom; the ``ply_failure`` check takes the worst ply
anywhere (index 1 fails). Fields: von Mises (the envelope over the plies),
displacement and the failure index (the envelope).

Plies are numbered from the bottom face: the face the laminate's normal points
away from, its normal being the plate's normal turned so its largest
component is positive (+Z for a plate in XY).

Limits: linear, no delamination or progressive damage (the first ply to fail
is the answer), CLT's perfectly bonded plies in plane stress. Ladder: the solid
path takes iterative, local_refine and symmetry (about a plane across a
direction every ply is symmetric about); the shell path is already small and
needs none. Stdlib at import.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, SolveContext
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs

__all__ = ["CompositeAnalysis", "CompositeInputs"]

#: The plies' total and the plate's thickness may differ by this share (rounding in a CAD model).
THICKNESS_AGREE = 0.02
LIMITS = (
    "Linear: small deflections and every ply elastic up to failure; no delamination and no progressive damage, "
    "so the answer is the first ply to fail.",
    "Classical laminate theory: plies perfectly bonded, each in plane stress (through-thickness stresses are not "
    "judged); a thick plate is meshed as a solid with each ply's stiffness at its height.",
)
NOT_A_PLATE = (
    "composite: a layup needs a flat plate of even thickness (two parallel faces, every other face across them), "
    "and this part is not one; for another shape, give a static study an orthotropic material"
)


@dataclass(frozen=True)
class CompositeInputs(StaticInputs):
    laminate: Any = None
    #: Each ply as the study gave it (material name, angle, thickness), bottom first.
    plies: tuple = ()
    #: The plies' 0° direction the study gave, else ``None`` (the default).
    axis: tuple[float, float, float] | None = None
    #: The ply materials the study named (``laminae``), each its numbers as given, for the result's study echo.
    laminae: dict = field(default_factory=dict, compare=False, hash=False)
    #: What the solve resolved (the method, the frame), written once by ``solve``.
    resolved: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class _Setup:
    plate: Any
    #: The laminate's normal (plies stacked along it) and whether it is the plate's own normal turned over.
    normal: tuple[float, float, float]
    flipped: bool
    axis: tuple[float, float, float]
    thin: bool
    #: The bottom face's height along ``normal``.
    base: float


def _orient(plate, given) -> tuple[tuple[float, float, float], bool, tuple[float, float, float]]:
    """The laminate's normal (the plate's, its largest component positive), whether that turned it over, and the
    0° direction laid into the plate (``given``, else global X, or Y for a plate facing X)."""
    n = tuple(float(c) for c in plate.normal)
    big = max(range(3), key=lambda i: abs(n[i]))
    flipped = n[big] < 0
    m = tuple(-c + 0.0 for c in n) if flipped else n
    axis = given if given is not None else ((0.0, 1.0, 0.0) if big == 0 else (1.0, 0.0, 0.0))
    along = sum(a * b for a, b in zip(axis, m))
    laid = [a - along * b for a, b in zip(axis, m)]
    size = math.sqrt(sum(c * c for c in laid))
    if size < 1e-6:
        raise ValueError("study.layup_axis: the 0° direction runs through the plate's thickness; give one along the plate")
    return m, flipped, tuple(c / size for c in laid)  # type: ignore[return-value]


def _plate(geometry):
    from cadgen._internal.fea import shell

    if geometry is None or geometry.shape is None:
        return None
    return shell.cached(geometry.shape, "laminate",
                        lambda shape: shell.detect_plate(shape, geometry.volume_mm3, geometry.area_mm2, thin=math.inf))


def _setup(ctx, inputs: CompositeInputs) -> _Setup:
    from cadgen._internal.fea import shell

    plate = _plate(ctx.geometry)
    if plate is None:
        raise ValueError(NOT_A_PLATE)
    total = inputs.laminate.thickness
    if abs(total - plate.thickness) > THICKNESS_AGREE * plate.thickness:
        raise ValueError(f"study.layup: the plies add up to {total:.4g} mm, but the plate is {plate.thickness:.4g} mm "
                         "thick; make the plies' thickness_mm add up to the part's thickness")
    m, flipped, axis = _orient(plate, inputs.axis)
    bottom = plate.top_level - plate.thickness   # along the plate's own normal
    base = -plate.top_level if flipped else bottom
    return _Setup(plate, m, flipped, axis, plate.slenderness < shell.THIN, base)


def _layered(setup: _Setup, inputs: CompositeInputs):
    from cadgen._internal.fea.laminate import layered_material

    return layered_material(inputs.laminate, setup.normal, setup.axis, setup.base, "laminate")


def _angle_words(angle: float) -> str:
    text = f"{angle:.4g}"
    if text in ("0", "-0"):
        return "0°"
    return f"+{text}°" if angle > 0 else f"{text}°"


def _ply_failure(lamina, s1, s2, t12):
    """(Tsai-Wu, max-stress) of ply stresses, arrays alike."""
    from cadgen._internal.fea.laminate import max_stress, tsai_wu

    return tsai_wu(lamina, s1, s2, t12), max_stress(lamina, s1, s2, t12)


class CompositeAnalysis(StaticAnalysis):
    name: ClassVar[str] = "composite"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Composite"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "layup", "laminae", "layup_axis"})
    #: The plies carry the materials (``laminae``): the study's ``material`` is not needed.
    material_required: ClassVar[bool] = False
    material_needs: ClassVar[frozenset[str]] = frozenset()
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress (ply envelope)", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
        FieldSpec("failure_index", "_FAILURE_INDEX", "failure index", ""),
    )
    checks: ClassVar[tuple] = (kinds.PLY_FAILURE, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "ply_failure"},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold")
    default_controls: ClassVar[dict[str, dict]] = {
        "field": {"drives": "field", "type": "enum", "options": ["failure_index", "von_mises", "displacement"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "symmetry")
    governing_word: ClassVar[str] = "peak failure index"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> CompositeInputs:
        from cadgen._internal.fea.laminate import parse_layup

        if "material" in document:
            raise ValueError("study.material: a composite study takes its materials from the plies (study.laminae, or "
                             "each ply's material); leave material out")
        static = super().parse(document)
        laminate, plies, axis = parse_layup(document)
        if any(load.body for load in static.loads) and not laminate.density() > 0:
            raise ValueError("study.laminae: a body load needs every ply material's density_t_per_mm3, like 1.6e-9")
        return CompositeInputs(
            static.face_refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
            laminate=laminate, plies=tuple(plies), axis=axis,
            laminae={str(name): {key: value for key, value in spec.items() if isinstance(value, (int, float))
                                 and not isinstance(value, bool)}
                     for name, spec in (document.get("laminae") or {}).items() if isinstance(spec, dict)},
        )

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: CompositeInputs):
        """A thin plate: the shell (its carrier mesh and mid-surface), planned here once; a thick one: the solid."""
        from cadgen._internal.fea import fit, shell

        plate = _plate(ctx.geometry)
        plan = ctx.plan
        # A roller slides along its face, which the mid-surface (whole nodes held) cannot: the layered solid takes it.
        from cadgen._internal.fea.supports import has_rollers

        if plate is not None and plate.slenderness < shell.THIN and ctx.assembly is None and not has_rollers(inputs.fixtures):
            if plan.idealisation == "solid" and not plan.taken:
                plan.idealisation = "shell"
                plan.size_mm = max(float(plan.requested_mm or 0.0), plate.span / shell.CARRIER_ACROSS)
            if plan.idealisation == "shell":
                h = shell.element_size(plate, plan.requested_mm)
                return shell.idealised_cost(ctx, 6 * (shell.triangles_for(plate.area, h) + 1), 42.0)
        return fit.solid_estimate(ctx)

    def apply(self, rung, ctx: SolveContext, inputs: CompositeInputs):
        from cadgen._internal.fea import fit

        if ctx.plan.idealisation == "shell":
            return None   # the laminated shell is already the small model
        return fit.apply_generic(rung, self, ctx, inputs)

    def symmetric_about(self, plane, inputs: CompositeInputs, ctx: SolveContext) -> bool:
        """Static's rule, and every ply its own mirror image about the plane (a plane across one of its directions
        in the plate's plane)."""
        if not super().symmetric_about(plane, inputs, ctx):
            return False
        plate = _plate(ctx.geometry)
        if plate is None:
            return False
        return _layered(_setup(ctx, inputs), inputs).mirrors_onto_itself(plane.component)

    def governing(self, result: AnalysisResult):
        return result.fields["failure_index"], float(result.scalars["worst"]["index"])

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: CompositeInputs) -> AnalysisResult:
        setup = _setup(ctx, inputs)
        if ctx.plan is not None and ctx.plan.idealisation == "shell":
            result = self._solve_shell(ctx, inputs, setup)
        else:
            result = self._solve_solid(ctx, inputs, setup)
        inputs.resolved.update(method=result.scalars["method"], normal=setup.normal, axis=setup.axis)
        return result

    def _plies_bottom_up(self, inputs: CompositeInputs, setup: _Setup):
        """The plies as the solve sees them (along the plate's own normal) and each one's index in the study."""
        laminate = inputs.laminate
        count = len(laminate.plies)
        if setup.flipped:
            return laminate.flipped(), [count - 1 - k for k in range(count)]
        return laminate, list(range(count))

    def _solve_shell(self, ctx: SolveContext, inputs: CompositeInputs, setup: _Setup) -> AnalysisResult:
        """The plate's mid-surface with CLT's A, B, D and H; each ply judged at its top and bottom."""
        import time

        import numpy as np

        from cadgen._internal.fea import shell

        plate = setup.plate
        seen, index_of = self._plies_bottom_up(inputs, setup)
        A, B, D = seen.abd()
        abd = {"A": A, "B": B, "D": D, "H": seen.shear(), "axis": setup.axis}
        h = shell.element_size(plate, ctx.plan.requested_mm)
        first = seen.plies[0].lamina
        mid = shell.solve_mid_surface(ctx, inputs, plate, h, E=first.E1, nu=0.3, density=seen.density(), abd=abd)
        model, u, frame, triangles, nodes = mid.model, mid.u, mid.frame, mid.model.triangles, mid.model.nodes
        n, t = model.normal, plate.thickness
        started = time.perf_counter()
        local = np.einsum("tij,tj->ti", shell.rotation_blocks(frame, 6), u[mid.connectivity])
        strain = np.einsum("tki,ti->tk", mid.membrane, local)          # element axes: e_x, e_y, g_xy
        curvature = np.einsum("tki,ti->tk", mid.bending, local)
        c, s = shell.laminate_rotation(frame, n, setup.axis)
        phi = np.arctan2(s, c)
        z = seen.interfaces()
        count = len(triangles)
        plies = len(seen.plies)
        vm = np.zeros((plies, 2, count))
        tw = np.zeros((plies, 2, count))
        ms = np.zeros((plies, 2, count))
        stress = np.zeros((plies, 2, count, 3))
        for k, ply in enumerate(seen.plies):
            theta = math.radians(ply.angle_deg) - phi
            T = shell.strain_rotation(np.cos(theta), np.sin(theta))     # element axes -> this ply's axes
            Q = ply.lamina.Q()
            for side, height in enumerate((z[k], z[k + 1])):
                in_ply = np.einsum("tij,tj->ti", T, strain + height * curvature)
                sigma = in_ply @ Q.T                                     # sigma1, sigma2, tau12
                stress[k, side] = sigma
                s1, s2, t12 = sigma[:, 0], sigma[:, 1], sigma[:, 2]
                vm[k, side] = np.sqrt(np.maximum(s1 * s1 - s1 * s2 + s2 * s2 + 3.0 * t12 * t12, 0.0))
                tw[k, side], ms[k, side] = _ply_failure(ply.lamina, s1, s2, t12)
        worst = self._worst(inputs, seen, index_of, tw, ms, stress, nodes[triangles].mean(axis=1), z)
        index = np.maximum(tw, ms).max(axis=(0, 1))
        envelope = vm.max(axis=(0, 1))
        flat = np.c_[nodes @ model.e1, nodes @ model.e2]
        nodal = shell.node_patch_fit(flat, triangles, np.c_[envelope, index])
        points = ctx.space.dof_locations if ctx.space is not None else ctx.volume.nodes
        height = np.clip(points @ n - plate.mid_level, -0.5 * t, 0.5 * t)
        where, weights = shell.locate(np.c_[points @ model.e1, points @ model.e2], flat, triangles)
        corner = triangles[where]
        U = u.reshape(-1, 6)
        translation = np.einsum("pk,pkc->pc", weights, U[corner, :3])
        rotation = np.einsum("pk,pkc->pc", weights, U[corner, 3:])
        displacement = translation + np.cross(rotation, height[:, None] * n[None, :])
        mapped = np.einsum("pk,pkc->pc", weights, nodal[corner])
        timings = dict(mid.timings, stress_s=time.perf_counter() - started)
        outcome = shell.outcome_on_carrier(ctx, displacement, mapped[:, 0], float(envelope.max()), mid.reactions,
                                           mid.applied, mid.size, timings, "direct (laminated shell)")
        detail = {"nodes": int(mid.count), "elements": int(count), "element_size_mm": round(h, 4)}
        A_user, B_user, D_user = inputs.laminate.abd()
        return self._result(outcome, np.maximum(mapped[:, 1], 0.0), worst, "shell", {
            **detail, "A": A_user.tolist(), "B": B_user.tolist(), "D": D_user.tolist(),
        }, [self._ply_record(inputs, k, float(tw[index_of.index(k)].max()), float(ms[index_of.index(k)].max()))
            for k in range(plies)])

    def _solve_solid(self, ctx: SolveContext, inputs: CompositeInputs, setup: _Setup) -> AnalysisResult:
        """The plate meshed as a solid, every point its ply's 3D orthotropic stiffness; each ply judged at its points."""
        import numpy as np

        from cadgen._internal.fea import operators, solve

        material = _layered(setup, inputs)
        extra: dict[str, Any] = {}
        if any(load.body for load in inputs.loads):
            extra["body_loads"] = inputs.body_accelerations
        if ctx.space is not None:
            extra["space"] = ctx.space
        loads = inputs.surface_loads if extra.get("body_loads") else inputs.loads
        plan = ctx.plan
        planes = list(plan.prepared.planes) if plan is not None and plan.prepared is not None else []
        if plan is not None and plan.solver != "direct":
            extra["solver"] = plan.solver
        if planes:
            share = 0.5 ** len(planes)
            loads = tuple(dataclasses.replace(load, vector=tuple(share * c for c in load.vector)) if load.type == "force" else load
                          for load in loads)
            extra["rollers"] = [((p.ordinal,), p.component) for p in planes]
        outcome = solve.solve_linear_static(ctx.volume, material, inputs.fixtures, loads, ctx.ordinal_of, log=ctx.log,
                                            automatic=ctx.automatic, **extra)
        space = ctx.space
        if space is None:
            from cadgen._internal.fea.femspace import FemSpace

            space = FemSpace.build(ctx.volume)
        sigma = operators.stress(space, material, outcome.u)                        # (3, 3, elements, quadrature)
        stack = material.layers
        points = np.asarray(space.basis.global_coordinates().value)
        ply = stack.ply_index(points)
        laminate = inputs.laminate
        plies = len(laminate.plies)
        index = np.zeros(ply.shape)
        tw_max, ms_max = np.full(plies, -np.inf), np.full(plies, -np.inf)
        best = None
        for k, entry in enumerate(laminate.plies):
            d1, d2, _ = (np.asarray(d) for d in stack.directions[k])
            s1 = np.einsum("i,ij...,j->...", d1, sigma, d1)
            s2 = np.einsum("i,ij...,j->...", d2, sigma, d2)
            t12 = np.einsum("i,ij...,j->...", d1, sigma, d2)
            tw, ms = _ply_failure(entry.lamina, s1, s2, t12)
            inside = ply == k
            if not inside.any():
                continue
            here = np.where(inside, np.maximum(tw, ms), -np.inf)
            index = np.where(inside, np.maximum(tw, ms), index)
            tw_max[k], ms_max[k] = float(tw[inside].max()), float(ms[inside].max())
            at = np.unravel_index(int(np.argmax(here)), here.shape)
            if best is None or here[at] > best[0]:
                best = (float(here[at]), k, at, float(tw[at]), float(ms[at]), (float(s1[at]), float(s2[at]), float(t12[at])))
        nodal = np.maximum(space.scalar.project(index), 0.0)
        location = points[:, best[2][0], best[2][1]]
        worst = self._worst_record(inputs, best[1], best[3], best[4], best[5], location)
        records = [self._ply_record(inputs, k, tw_max[k], ms_max[k]) for k in range(plies)]
        volume = ctx.volume
        if planes:
            volume, outcome, nodal = self._unfold(volume, outcome, planes, nodal)
            ctx.volume = volume
        return self._result(outcome, nodal, worst, "solid", {"elements": int(len(volume.tets))}, records)

    @staticmethod
    def _unfold(volume, outcome, planes, nodal):
        """Static's mirror back into the whole part (analyses.static._unfold), carrying the failure index too."""
        import dataclasses as dc

        import numpy as np

        from cadgen._internal.fea import symmetry

        for plane in reversed(planes):
            whole, keep = symmetry.unfold_volume(volume, plane)
            locations, scalars, vectors, boundary, tets, elements, vertices = symmetry.unfold_fields(
                plane, outcome.vertices, outcome.dof_locations, keep,
                scalars={"von_mises": outcome.von_mises, "failure_index": nodal},
                vectors={"displacement": outcome.displacement}, boundary=outcome.boundary_quadratic, tets=outcome.tets,
                element_dofs=outcome.element_dofs,
            )
            outcome = dc.replace(
                outcome, dof_locations=locations, von_mises=scalars["von_mises"], displacement=vectors["displacement"],
                boundary_quadratic=boundary, tets=tets, element_dofs=elements, vertices=vertices,
                element_von_mises_gauss=np.concatenate([outcome.element_von_mises_gauss] * 2),
                reactions=[symmetry.unfold_force(plane, r) for r in outcome.reactions],
                applied=symmetry.unfold_force(plane, outcome.applied), u=None,
            )
            nodal = scalars["failure_index"]
            volume = whole
        return volume, outcome, np.asarray(nodal)

    # -- the worst ply -------------------------------------------------------------------------------

    def _worst(self, inputs, seen, index_of, tw, ms, stress, centroids, z):
        """The worst ply over every element and both its faces (shell): its number in the study, its numbers."""
        import numpy as np

        combined = np.maximum(tw, ms)
        k, side, element = np.unravel_index(int(np.argmax(combined)), combined.shape)
        s1, s2, t12 = (float(v) for v in stress[k, side, element])
        return self._worst_record(inputs, index_of[k], float(tw[k, side, element]), float(ms[k, side, element]),
                                  (s1, s2, t12), centroids[element])

    @staticmethod
    def _worst_record(inputs, k: int, tw: float, ms: float, stresses, location) -> dict:
        ply = inputs.laminate.plies[k]
        return {
            "ply": k + 1, "angle_deg": ply.angle_deg, "material": ply.lamina.name, "index": max(tw, ms),
            "tsai_wu": tw, "max_stress": ms, "criterion": "tsai_wu" if tw >= ms else "max_stress",
            "stress_MPa": {"sigma1": stresses[0], "sigma2": stresses[1], "tau12": stresses[2]},
            "at": tuple(float(c) for c in location),
        }

    @staticmethod
    def _ply_record(inputs, k: int, tw: float, ms: float) -> dict:
        """One ply's worst: its Tsai-Wu and max-stress maxima (``None`` for a ply no point of the mesh lies in)."""
        ply = inputs.laminate.plies[k]
        seen = math.isfinite(tw)
        return {"ply": k + 1, "angle_deg": ply.angle_deg, "material": ply.lamina.name, "thickness_mm": ply.thickness,
                "max_failure_index": max(tw, ms) if seen else None, "max_tsai_wu": tw if seen else None,
                "max_max_stress": ms if seen else None}

    def _result(self, outcome, failure_index, worst, method: str, detail: dict, plies: list) -> AnalysisResult:
        return AnalysisResult(
            dof_locations=outcome.dof_locations, vertices=outcome.vertices, tets=outcome.tets,
            boundary_quadratic=outcome.boundary_quadratic, element_dofs=outcome.element_dofs,
            fields={"von_mises": outcome.von_mises, "displacement": outcome.displacement, "failure_index": failure_index},
            deformation=outcome.displacement,
            scalars={"outcome": outcome, "worst": worst, "method": method, "detail": detail, "plies": plies,
                     "part_refs": None, "analysis_extras": {}},
            reactions=list(outcome.reactions), applied=tuple(outcome.applied), dofs=outcome.dofs,
            solver=outcome.solver, timings=dict(outcome.timings), warnings=list(outcome.warnings), solved=None,
        )

    # -- the automatic finer solve and local_refine's passes -----------------------------------------

    def needs_finer(self, result: AnalysisResult, inputs: CompositeInputs, check_results: list[dict]) -> bool:
        return False

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_failure_index": round(result.scalars["worst"]["index"], 6),
                "size_mm": round(finer_mm, 4), "max_failure_index": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_failure_index"] = round(finer.scalars["worst"]["index"], 6)
        return finer

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: CompositeInputs) -> dict:
        from cadgen._internal.fea import checks

        if check["kind"] == "displacement":
            return super().judge(check, index, ctx, result, inputs)
        worst = result.scalars["worst"]
        criterion = check.get("criterion")
        value = worst["index"] if criterion is None else self._by_criterion(result, criterion)
        ratio = value / 1.0
        peak = kinds.field_max_over(
            result.fields["failure_index"], (), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        ply = worst if criterion is None else result.scalars.get(f"worst_{criterion}", worst)
        return {
            "kind": "ply_failure", "label": check.get("label") or kinds.PLY_FAILURE.default_label,
            "value": round(value, 6), "limit": 1.0, "unit": "", "ratio": round(ratio, 6), "close_at": 0.9,
            "status": checks.check_status(ratio, 0.9),
            "where": {"ref": peak.ref, "at": [round(c, 3) for c in ply["at"]]},
            "ply": ply["ply"], "angle_deg": ply["angle_deg"],
            "criterion": criterion or ply["criterion"],
        }

    @staticmethod
    def _by_criterion(result: AnalysisResult, criterion: str) -> float:
        """The worst value of one criterion over every ply (its ply recorded for the row)."""
        plies = result.scalars["plies"]
        worst = result.scalars["worst"]
        key = {"tsai_wu": "max_tsai_wu", "max_stress": "max_max_stress"}[criterion]
        best = max((r for r in plies if r[key] is not None), key=lambda r: r[key])
        result.scalars[f"worst_{criterion}"] = {**worst, "ply": best["ply"], "angle_deg": best["angle_deg"]}
        return float(best[key])

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: CompositeInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        worst = result.scalars["worst"]
        found = []

        def finding(severity, kind, summary, description, items=()):
            return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description,
                    "items": list(items)}

        place = [{"text": f"ply {worst['ply']} ({_angle_words(worst['angle_deg'])}) at its worst", "ref": None,
                  "at": [round(c, 3) for c in worst["at"]]}]
        line = ply_line(worst["ply"], worst["angle_deg"], worst["index"])
        criterion = "Tsai-Wu" if worst["criterion"] == "tsai_wu" else "max stress"
        if worst["index"] > 1.0:
            found.append(finding("error", "ply_fails", f"A ply fails: {line} ({criterion})",
                                 "the first ply to fail; past it a real laminate cracks or delaminates, which this "
                                 "linear model does not follow", place))
        elif worst["index"] > 0.9:
            found.append(finding("warning", "ply_close", f"Close to failing: {line} ({criterion})",
                                 "within 10 % of the first ply failure", place))
        method = ("a laminated shell by classical laminate theory (A, B and D from the plies)"
                  if result.scalars["method"] == "shell" else
                  "a solid with each ply's orthotropic stiffness at its height (the plate is too thick for plate theory)")
        found.append(finding("info", "composite_method", f"Solved as {method}", " ".join(LIMITS)))
        assumed = sorted({words for ply in inputs.laminate.plies for words in ply.lamina.assumed})
        if assumed:
            found.append(finding("info", "lamina_assumed", "Assumed for the ply materials: " + "; ".join(assumed),
                                 "values the laminae did not give, taken by transverse isotropy; give them to replace"))
        return found

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: CompositeInputs, check_results: list[dict]) -> dict:
        import numpy as np

        from cadgen._internal.fea.laminate import notation

        outcome = result.scalars["outcome"]
        magnitude = np.linalg.norm(outcome.displacement, axis=1)
        moved = int(magnitude.argmax())
        worst = result.scalars["worst"]
        reaction_total = tuple(sum(r[c] for r in outcome.reactions) for c in range(3))

        def rounded(value):
            return None if value is None else round(float(value), 6)

        return {
            "method": result.scalars["method"],
            "layup": {"plies": [dict(ply) for ply in inputs.plies], "notation": notation(inputs.laminate),
                      "thickness_mm": round(inputs.laminate.thickness, 6), "count": len(inputs.plies)},
            "max_failure_index": round(worst["index"], 6),
            "worst_ply": {
                "ply": worst["ply"], "angle_deg": worst["angle_deg"], "material": worst["material"],
                "criterion": worst["criterion"], "tsai_wu": round(worst["tsai_wu"], 6), "max_stress": round(worst["max_stress"], 6),
                "stress_MPa": {key: round(value, 4) for key, value in worst["stress_MPa"].items()},
                "at_mm": [round(c, 3) for c in worst["at"]],
            },
            "plies": [{key: (rounded(value) if key.startswith("max_") else value) for key, value in record.items()}
                      for record in result.scalars["plies"]],
            "max_von_mises_MPa": round(float(outcome.von_mises.max()), 4),
            "max_displacement_mm": round(float(magnitude.max()), 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in outcome.dof_locations[moved]],
            "applied_force_N": [round(x, 4) for x in outcome.applied],
            "reaction_force_N": [round(x, 4) for x in reaction_total],
            "deformation_scale": result.scalars["deformation_scale"],
            "detail": {key: ([[round(float(v), 6) for v in row] for row in value] if isinstance(value, list) else value)
                       for key, value in result.scalars["detail"].items()},
            "checks": check_results,
        }

    def extras_name(self, stem: str) -> str:
        return f"{stem} composite"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        return {"von_mises": (0.0, summary["max_von_mises_MPa"]), "displacement": (0.0, summary["max_displacement_mm"]),
                "failure_index": (0.0, round(float(result.fields["failure_index"].max()), 6))}

    def extras_head(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: CompositeInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        from cadgen._internal.fea.laminate import notation

        echo = super().study_echo(inputs, bare)
        layup = {"plies": [dict(ply) for ply in inputs.plies], "notation": notation(inputs.laminate),
                 "thickness_mm": round(inputs.laminate.thickness, 6)}
        if "axis" in inputs.resolved:
            layup["axis"] = [round(c, 6) + 0.0 for c in inputs.resolved["axis"]]
            layup["normal"] = [round(c, 6) + 0.0 for c in inputs.resolved["normal"]]
            layup["method"] = inputs.resolved["method"]
        echo["layup"] = layup
        if inputs.laminae:
            echo["laminae"] = {name: dict(numbers) for name, numbers in inputs.laminae.items()}
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        layup, worst = summary["layup"], summary["worst_ply"]
        method = "laminated shell (CLT)" if summary["method"] == "shell" else "layered solid"
        criterion = "Tsai-Wu" if worst["criterion"] == "tsai_wu" else "max stress"
        return [
            f"layup {layup['count']} plies, {layup['notation']}, {layup['thickness_mm']:g} mm, solved as a {method}",
            f"{ply_line(worst['ply'], worst['angle_deg'], summary['max_failure_index'])} ({criterion}; "
            f"Tsai-Wu {worst['tsai_wu']:.3g}, max stress {worst['max_stress']:.3g})",
            f"max von Mises {summary['max_von_mises_MPa']} MPa (ply envelope)",
            f"max displacement {summary['max_displacement_mm']} mm at {summary['max_displacement_at_mm']}",
            f"applied {summary['applied_force_N']} N, reactions {summary['reaction_force_N']} N",
        ]


def ply_line(ply: int, angle: float, index: float) -> str:
    """The check's row: "Worst ply 3 (+45°), failure index 0.82"."""
    return f"Worst ply {ply} ({_angle_words(angle)}), failure index {index:.2f}"
