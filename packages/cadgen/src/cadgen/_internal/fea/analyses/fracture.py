"""Fracture (lite): will a crack in the part grow, and how many cycles until it does. Tier 3, linear-elastic fracture mechanics.

The study describes the crack (``crack``, :func:`cadgen._internal.fea.crack.parse_crack`):
an edge, through, semi-elliptical surface or embedded elliptical crack, where it is
and how big. The analysis cuts it into the part along its plane, meshes the front
fine, opens it (the nodes of its faces duplicated, the front's shared), solves the
static load case on the cracked part (static's solve, unchanged) and reads the
stress intensity factors K_I, K_II and K_III at stations along the front by the
domain interaction integral (:mod:`cadgen._internal.fea.crack`).

Its checks:

- ``fracture``: the largest equivalent K along the front, √(K_I² + K_II² +
  K_III²/(1 − ν)), against the material's fracture toughness K_IC, held to a
  margin (1.5 by default). It scales with the load (K is linear in it).
- ``crack_life``: with a ``growth`` block, Paris's law da/dN = C (ΔK)^m
  integrated from the crack's size to the size where K reaches K_IC, at the
  study's load ratio R (ΔK = (1 − R) K_max; the whole K_max for a reversing
  load), against the cycles needed, held to a margin (2 by default).

The fields are static's: von Mises stress (singular at the front: its colours are
capped at the 99th percentile) and displacement, which shows the crack opening.
The K along the front is a curve in the sidecar. Ladder: iterative, local_refine
(the front stays fine: its local sizes ride with the cut shape), defeature (the
crack is cut into the simplified part) and symmetry (about a plane the crack is
its own mirror image across, never its own plane: the front halves are joined).
Stdlib at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, SolveContext
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs
from cadgen._internal.fea.crack import CrackSpec, parse_crack

if TYPE_CHECKING:
    from cadgen._internal.fea.crack import CrackGeometry, CrackedPrepared

__all__ = ["FractureAnalysis", "FractureInputs", "Growth", "LIMITS", "crack_words", "point_words"]

LIMITS = (
    "Linear-elastic fracture mechanics: the material stays elastic around the crack (small-scale yielding); "
    "no ductile tearing or plastic collapse",
    "K where the front meets a free surface is read as the plane-strain value",
    "Crack growth holds the crack's shape and geometry factor as solved, growing straight on in its own plane",
)
GROWTH_KEYS = frozenset({"load_ratio", "paris_C", "paris_m", "final_mm"})
#: The von Mises colours stop at this quantile: the field is singular at the front.
COLOUR_QUANTILE = 0.99
#: K moving more than this share between the two J domains is said as a finding.
SPREAD_WARNING = 0.05


@dataclass(frozen=True)
class Growth:
    """Crack growth by Paris's law: the load ratio R = K_min / K_max, the study's own C and m (else the
    material's), and a size to stop at (else where K reaches K_IC)."""

    load_ratio: float = 0.0
    paris_C: float | None = None
    paris_m: float | None = None
    final_mm: float | None = None

    def as_dict(self) -> dict:
        return {key: value for key, value in (("load_ratio", self.load_ratio), ("paris_C", self.paris_C),
                                              ("paris_m", self.paris_m), ("final_mm", self.final_mm)) if value is not None}


@dataclass(frozen=True)
class FractureInputs(StaticInputs):
    crack: CrackSpec | None = None
    growth: Growth | None = None


def _growth(raw: Any) -> Growth:
    where = "growth"
    example = '{"load_ratio": 0.1}'
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: expected an object like {example} (and paris_C, paris_m when the material has none)")
    unknown = set(raw) - GROWTH_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; growth takes {sorted(GROWTH_KEYS)}")
    ratio = kinds.number(raw.get("load_ratio", 0.0), where=f"{where}.load_ratio")
    if not -1.0 <= ratio < 1.0:
        raise ValueError(f"{where}.load_ratio: R = lowest / highest load, from -1 (fully reversed) up to but not 1 "
                         f"(a steady load grows no fatigue crack), got {ratio:g}")
    C = kinds.number(raw["paris_C"], where=f"{where}.paris_C", positive=True) if "paris_C" in raw else None
    m = kinds.number(raw["paris_m"], where=f"{where}.paris_m", positive=True) if "paris_m" in raw else None
    if (C is None) != (m is None):
        raise ValueError(f"{where}: give paris_C and paris_m together (da/dN = C ΔK^m, C in m/cycle with ΔK in MPa√m)")
    if m is not None and not 1.0 <= m <= 10.0:
        raise ValueError(f"{where}.paris_m: the Paris exponent is between 1 and 10 (metals: about 2 to 4), got {m:g}")
    final = kinds.number(raw["final_mm"], where=f"{where}.final_mm", positive=True) if "final_mm" in raw else None
    return Growth(ratio, C, m, final)


def _judged_kinds(document: dict, default: tuple[dict, ...]) -> set[str]:
    view = document.get("view")
    checks = view.get("checks") if isinstance(view, dict) else None
    entries = checks if isinstance(checks, list) and checks else default
    return {entry.get("kind") for entry in entries if isinstance(entry, dict)}


def crack_words(spec: dict, face_word: str | None = None) -> str:
    """The crack in a sentence: "2 mm edge crack on face 4", "1.5 mm deep surface crack, 6 mm long, on face 4"."""
    def mm(value: float) -> str:
        return f"{float(value):.3g} mm"

    face = face_word or spec.get("face")
    kind, size = spec["kind"], spec["size_mm"]
    if kind == "edge":
        return f"{mm(size)} edge crack on {face}"
    if kind == "surface":
        length = spec.get("length_mm") or 2 * size
        return f"{mm(size)} deep surface crack, {mm(length)} long, on {face}"
    if kind == "through":
        return f"{mm(2 * size)} through crack across {face}"
    length = spec.get("length_mm") or 2 * size
    return f"{mm(2 * size)} embedded crack" + ("" if abs(length - 2 * size) < 1e-9 else f" by {mm(length)}")


def point_words(kind: str, *, end: bool, deepest: bool) -> str:
    """Where along the front K is largest, in words: "the deepest point", "the surface", "mid-front"."""
    if end:
        return "the surface"
    if kind == "surface" and deepest:
        return "the deepest point"
    if kind == "embedded":
        return "the crack's edge"
    return "mid-front"


def _cycles(value: float) -> str:
    if not math.isfinite(value):
        return "no end"
    if value >= 1e9:
        return f"{value / 1e9:.3g} billion"
    if value >= 1e6:
        return f"{value / 1e6:.3g} million"
    return f"{round(value):,}"


def _floored(value: float) -> float:
    return math.floor(value * 1000) / 1000


class FractureAnalysis(StaticAnalysis):
    name: ClassVar[str] = "fracture"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Cracks"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    isotropic_only: ClassVar[bool] = True
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "crack", "growth"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    checks: ClassVar[tuple] = (kinds.FRACTURE, kinds.CRACK_LIFE, kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "fracture", "margin": 1.5},)
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "local_refine", "defeature", "symmetry")
    noun: ClassVar[str] = "this load"
    governing_word: ClassVar[str] = "K"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> FractureInputs:
        static = StaticAnalysis.parse(self, document)
        if "crack" not in document:
            raise ValueError('study.crack: a fracture study describes its crack, like {"kind": "edge", "face": "#o1.f4", '
                             '"at_mm": [0, 0, 5], "normal": [0, 1, 0], "size_mm": 2}')
        crack = parse_crack(document["crack"])
        growth = _growth(document["growth"]) if "growth" in document else None
        judged = _judged_kinds(document, self.default_checks)
        if "crack_life" in judged and growth is None:
            raise ValueError('view.checks: a crack_life check needs a growth block, like "growth": {"load_ratio": 0.1}')
        needs = set(static.material_needs)
        if "fracture" in judged or growth is not None:
            needs.add("fracture_toughness")
        if growth is not None and growth.paris_C is None:
            needs.update({"paris_C", "paris_m"})
        refs = tuple(dict.fromkeys((*static.face_refs, *((crack.face,) if crack.face else ()))))
        return FractureInputs(refs, static.anchor_refs, True, fixtures=static.fixtures, loads=static.loads,
                              material_needs=frozenset(needs), crack=crack, growth=growth)

    # -- the crack in the shape the mesher meshes ----------------------------------------------------

    def crack_geometry(self, ctx: SolveContext, inputs: FractureInputs) -> "CrackGeometry":
        """The study's crack on the part (OCP): its plane, axes and size. One part only."""
        from cadgen._internal.fea import crack
        from cadgen._internal.fea.defeature import face_map

        geometry = ctx.geometry
        if ctx.assembly is not None or geometry is None or geometry.shape is None:
            raise ValueError("crack: a fracture study cracks one part; solve the cracked part alone with --occurrence")
        face = None
        if inputs.crack.face is not None:
            from OCP.TopoDS import TopoDS

            ordinal = ctx.ordinal_of[inputs.crack.face]
            face = TopoDS.Face_s(face_map(geometry.shape).FindKey(ordinal))
        return crack.resolve(inputs.crack, geometry.shape, face, inputs.crack.face)

    def cracked(self, ctx: SolveContext, inputs: FractureInputs, *, front_mm: float | None = None) -> "CrackedPrepared":
        """The plan's shape with the crack cut into it: made the first time the plan is costed, and again after a
        rung that changes the shape (defeature, symmetry). ``front_mm`` overrides the front's element size."""
        from cadgen._internal.fea import crack

        plan = ctx.plan
        current = plan.prepared
        if isinstance(current, crack.CrackedPrepared) and front_mm is None:
            return current
        base = current.base if isinstance(current, crack.CrackedPrepared) else current
        geometry = self.crack_geometry(ctx, inputs)
        radius = crack.domain_radius(geometry)
        size = front_mm or (current.front_mm if isinstance(current, crack.CrackedPrepared) else radius / crack.ELEMENTS_ACROSS)
        shape = ctx.geometry.shape if base is None else base.shape
        plan.prepared = crack.cut(geometry, shape, None if base is None else list(base.origin), base=base,
                                  front_mm=size, radius_mm=radius)
        return plan.prepared

    # -- the ladder ----------------------------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: FractureInputs):
        """Static's solve on the plan's mesh plus the tube of fine elements around the front (when the mesh is not
        counted already)."""
        from cadgen._internal.fea import fit

        prepared = self.cracked(ctx, inputs)
        base = fit.solid_estimate(ctx)
        if ctx.volume is not None and getattr(ctx, "meshed_plan", None) == fit.mesh_key(ctx.plan):
            return base
        length = _front_length(prepared)
        h = max(prepared.front_mm, 1e-9)
        share = 0.5 ** len(ctx.plan.symmetry)
        tube = fit.VOLUME_TETS * math.pi * (1.3 * prepared.radius_mm) ** 2 * length * share / h ** 3
        extra = fit.solve_cost(tube, tube * fit.NODES_PER_TET[2], solver=ctx.plan.solver)
        return fit.Estimate(base.dofs + extra.dofs, base.memory_bytes + extra.memory_bytes - fit.BASE_BYTES,
                            base.seconds + extra.seconds)

    def apply(self, rung, ctx: SolveContext, inputs: FractureInputs):
        """The shared rungs, each on the uncracked shape, the crack cut in again after a rung that changes it. After
        local_refine, a front still too costly for the budget is meshed coarser (never under three elements across its
        J domain), and the step says so with what it costs K."""
        from cadgen._internal.fea import crack, fit

        cracked = self.cracked(ctx, inputs)
        plan = ctx.plan
        plan.prepared = cracked.base
        try:
            step = fit.apply_generic(rung, self, ctx, inputs)
        finally:
            if plan.prepared is cracked.base:
                plan.prepared = cracked
            else:  # the rung made a new shape (defeatured, a symmetric half): cut the crack into it
                self.cracked(ctx, inputs, front_mm=cracked.front_mm)
        if rung == "local_refine" and step is not None:
            import dataclasses

            words = f"{step.words}; the crack front is still meshed at {cracked.front_mm:.3g} mm"
            step = dataclasses.replace(step, words=words, detail={**step.detail, "front_mm": round(cracked.front_mm, 4)})
            if not self.estimate(ctx, inputs).fits(ctx.budget):
                coarser = self._coarser_front(ctx, inputs)
                if coarser is not None:
                    across = cracked.radius_mm / coarser
                    step = dataclasses.replace(
                        step,
                        words=(f"{step.words.split('; the crack front')[0]}; the crack front is meshed at {coarser:.3g} mm, "
                               f"{across:.1g} elements across its J domain"),
                        accuracy=f"the front is meshed coarser than the {crack.ELEMENTS_ACROSS:g} elements across its J domain "
                                 "wanted; the K stated carries the change between two J domains",
                        detail={**step.detail, "front_mm": round(coarser, 4)},
                    )
        return step

    def _coarser_front(self, ctx: SolveContext, inputs: FractureInputs) -> float | None:
        """The finest front size, down to three elements across the J domain, that fits the budget (else the coarsest)."""
        from cadgen._internal.fea import crack

        cracked = ctx.plan.prepared
        radius = cracked.radius_mm
        finest = cracked.front_mm
        coarsest = radius / crack.MIN_ELEMENTS_ACROSS
        if coarsest <= finest * 1.05:
            return None
        chosen = coarsest
        for k in range(1, 9):
            size = finest * (coarsest / finest) ** (k / 8)
            self.cracked(ctx, inputs, front_mm=size)
            if self.estimate(ctx, inputs).fits(ctx.budget):
                chosen = size
                break
        self.cracked(ctx, inputs, front_mm=chosen)
        return chosen

    def symmetric_about(self, plane, inputs: FractureInputs, ctx: SolveContext) -> bool:
        """Static's rule (fixtures, loads and checks their own mirror images), and the crack its own mirror image
        across a plane that holds its normal (never the crack's own plane: its faces are free, its ligament is not)."""
        import numpy as np

        if not StaticAnalysis.symmetric_about(self, plane, inputs, ctx):
            return False
        geometry = self.crack_geometry(ctx, inputs)
        axis = plane.component
        if abs(geometry.n[axis]) > 1e-9:
            return False
        extent = min(geometry.reach, max(4.0 * geometry.a, 4.0 * (geometry.c if math.isfinite(geometry.c) else geometry.a), 1.0))
        u = np.linspace(-extent, extent, 41)
        grid = np.array([geometry.at + x * geometry.d + y * geometry.t for x in u for y in u])
        mirrored = plane.reflect(grid)
        return bool(np.array_equal(_inside_crack(geometry, grid), _inside_crack(geometry, mirrored)))

    def governing(self, result: AnalysisResult):
        """local_refine follows the stress field (it peaks at the front); two passes compare the largest K."""
        return result.fields["von_mises"], float(result.scalars["K_max"])

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: FractureInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import crack
        from cadgen._internal.fea.femspace import FemSpace

        prepared = self.cracked(ctx, inputs)
        if not (ctx.volume.boundary_ordinal == crack.CRACK_ORDINAL).any():
            raise RuntimeError("the mesh carries no crack faces: the cracked shape was not the one meshed")
        started = time.perf_counter()
        volume, fronts = crack.open_crack(ctx.volume, prepared.crack)
        ctx.volume = volume
        ctx.space = FemSpace.build(volume, 2)
        opened = time.perf_counter() - started
        result = StaticAnalysis.solve(self, ctx, inputs)
        if prepared.planes:
            fronts = crack.unfold_fronts(fronts, prepared.planes, 1e-6 * max(volume.bbox_diagonal, 1.0))
        material = ctx.materials[0]
        started = time.perf_counter()
        front_k = crack.stress_intensity(result.dof_locations, result.element_dofs, result.fields["displacement"],
                                         material.E, material.nu, fronts, prepared.radius_mm)
        if not front_k.K_I:
            raise RuntimeError("no element of the mesh lies around the crack front; the J domain is empty")
        result.timings["crack_s"] = opened + time.perf_counter() - started
        index = front_k.governing
        deepest = self._deepest(prepared.crack, front_k)
        point = point_words(prepared.crack.kind, end=front_k.end[index], deepest=index == deepest)
        K_max = front_k.K_eq(index)
        result.scalars.update({
            "front_k": front_k, "fronts": fronts, "crack_geometry": prepared.crack, "K_max": K_max, "K_index": index,
            "K_point": point, "front_mm": prepared.front_mm, "radius_mm": prepared.radius_mm,
            "toughness": material.fracture_toughness,
        })
        if inputs.growth is not None:
            growth = inputs.growth
            C = growth.paris_C if growth.paris_C is not None else material.paris_C
            m = growth.paris_m if growth.paris_m is not None else material.paris_m
            life = crack.paris_life(K_max, inputs.crack.size_mm, material.fracture_toughness, C, m, growth.load_ratio,
                                    growth.final_mm)
            life.update({"paris_C": C, "paris_m": m, "load_ratio": growth.load_ratio})
            result.scalars["growth"] = life
        # The K along each front, as curves (K against the position along the front; `front` says which front).
        x = [round(s, 6) for s in front_k.s_mm]
        result.curves = {
            name: {"x": x, "x_unit": "mm", "y": [round(v, 6) for v in values], "y_unit": "MPa√m", "front": list(front_k.front)}
            for name, values in (("K_I", front_k.K_I), ("K_II", front_k.K_II), ("K_III", front_k.K_III))
        }
        result.scalars["analysis_extras"] = {"crack": {"kind": inputs.crack.kind, "K_max_MPa_sqrt_m": round(K_max, 4)}}
        del np
        return result

    @staticmethod
    def _deepest(geometry, front_k) -> int:
        """The station deepest into the part along the crack's depth direction."""
        import numpy as np

        depth = [float(np.dot(np.asarray(at) - geometry.at, geometry.d)) for at in front_k.at_mm]
        return int(np.argmax(depth)) if depth else 0

    # -- the automatic finer solve: the front is meshed to the crack's size, not the study's -------------

    def needs_finer(self, result: AnalysisResult, inputs: FractureInputs, check_results: list[dict]) -> bool:
        return False

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_K_max_MPa_sqrt_m": round(float(result.scalars["K_max"]), 4),
                "size_mm": round(finer_mm, 4), "K_max_MPa_sqrt_m": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["K_max_MPa_sqrt_m"] = round(float(finer.scalars["K_max"]), 4)
        return finer

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: FractureInputs) -> dict:
        if check["kind"] == "fracture":
            return self._fracture_check(check, result)
        if check["kind"] == "crack_life":
            return self._life_check(check, result)
        return StaticAnalysis.judge(self, check, index, ctx, result, inputs)

    def _fracture_check(self, check: dict, result: AnalysisResult) -> dict:
        K = float(result.scalars["K_max"])
        toughness = float(result.scalars["toughness"])
        margin = float(check.get("margin", 1.5))
        ratio = K / toughness
        status = "fails" if ratio >= 1.0 else "close" if ratio * margin > 1.0 else "passes"
        front_k = result.scalars["front_k"]
        at = front_k.at_mm[result.scalars["K_index"]]
        return {
            "kind": "fracture", "label": check.get("label") or "Crack", "value": round(K, 4), "limit": toughness,
            "unit": "MPa√m", "ratio": round(ratio, 6), "close_at": round(1.0 / margin, 6), "margin": margin, "status": status,
            "where": {"ref": None, "at": [round(c, 3) for c in at]}, "point": result.scalars["K_point"],
        }

    def _life_check(self, check: dict, result: AnalysisResult) -> dict:
        growth = result.scalars["growth"]
        life = float(growth["cycles"])
        need = float(check["cycles"])
        margin = float(check.get("margin", 2.0))
        ratio = need / life if life > 0 else math.inf
        status = "fails" if life < need else "close" if life < margin * need else "passes"
        front_k = result.scalars["front_k"]
        at = front_k.at_mm[result.scalars["K_index"]]
        return {
            "kind": "crack_life", "label": check.get("label") or "Crack life",
            "value": float(f"{life:.4g}") if math.isfinite(life) else None, "limit": need, "unit": "cycles",
            "ratio": round(ratio, 6) if math.isfinite(ratio) else None, "close_at": round(1.0 / margin, 6), "margin": margin,
            "status": status, "where": {"ref": None, "at": [round(c, 3) for c in at]}, "need": need,
            "life": float(f"{life:.4g}") if math.isfinite(life) else None,
            "critical_mm": round(float(growth["final_mm"]), 4) if math.isfinite(growth["final_mm"]) else None,
        }

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: FractureInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        """In plain words: the crack grows or how close it is, its life, whether LEFM holds there, how sure K is, and
        a crack loaded in shear or pressed shut. Static's stress findings are left out: the stress at a crack's front
        is singular, so its peak says nothing about strength."""
        found = []
        front_k = result.scalars["front_k"]
        index = result.scalars["K_index"]
        K = float(result.scalars["K_max"])
        toughness = result.scalars["toughness"]
        point = result.scalars["K_point"]
        at = {"text": f"the crack front at {point}", "ref": None, "at": [round(c, 3) for c in front_k.at_mm[index]]}
        for judged in check_results:
            if judged["kind"] == "fracture" and judged["status"] == "fails":
                found.append(_finding("error", "crack_grows",
                                      f"The crack grows at this load: K {K:.3g} MPa√m at {point} reaches the toughness "
                                      f"{toughness:.3g} MPa√m", f"K/K_IC {K / toughness:.3f}", [at]))
            elif judged["kind"] == "fracture" and judged["status"] == "close":
                found.append(_finding("warning", "low_fracture_margin",
                                      f"The crack holds, but K {K:.3g} MPa√m at {point} is within the {judged['margin']:g} "
                                      f"margin of the toughness {toughness:.3g} MPa√m", f"K_IC/K {toughness / K:.3f}", [at]))
            elif judged["kind"] == "crack_life" and judged["status"] in ("fails", "close"):
                life = judged["life"]
                words = "no time" if life is not None and life < 1 else f"about {_cycles(life)} cycles" if life else "no end"
                found.append(_finding("error" if judged["status"] == "fails" else "warning",
                                      "crack_life_short" if judged["status"] == "fails" else "low_crack_life_margin",
                                      f"The crack grows to its critical size in {words}, "
                                      + ("short of" if judged["status"] == "fails" else "within the margin of")
                                      + f" the {_cycles(judged['need'])} cycles it needs", f"Paris's law at R {inputs.growth.load_ratio:g}",
                                      [at]))
        material = ctx.materials[0]
        size = inputs.crack.size_mm
        if material.yield_strength and K > 0:
            plastic = 2.5 * (K / material.yield_strength) ** 2 * 1000.0  # mm: ASTM E399's size for plane strain
            if plastic > size:
                found.append(_finding(
                    "warning", "lefm_limit",
                    f"The plastic zone at the crack front is not small next to the crack ({size:.3g} mm): LEFM stretches here, "
                    "and the real crack is less stable than K says; treat the answer as approximate",
                    f"2.5 (K/yield)² = {plastic:.3g} mm, more than the crack's {size:.3g} mm", [at]))
        spread = front_k.spread
        if spread > SPREAD_WARNING:
            found.append(_finding(
                "warning", "front_accuracy",
                f"K moved {100 * spread:.1f}% between the two J domains around the front, so it is known to about that much",
                f"front meshed at {result.scalars['front_mm']:.3g} mm, J domain {result.scalars['radius_mm']:.3g} mm", [at]))
        K_I, K_II, K_III = front_k.K_I[index], front_k.K_II[index], front_k.K_III[index]
        if K_I < 0:
            found.append(_finding(
                "warning", "crack_closed",
                "The load presses the crack shut (K_I is negative): its faces would touch, which this analysis does not model",
                f"K_I {K_I:.3g} MPa√m", [at]))
        elif max(abs(K_II), abs(K_III)) > 0.1 * max(K_I, 1e-12):
            found.append(_finding(
                "info", "mixed_mode",
                f"The crack is also sheared (K_II {K_II:.2g}, K_III {K_III:.2g} MPa√m beside K_I {K_I:.2g}); the K judged is "
                "the equivalent one, and a sheared crack may turn as it grows", "", [at]))
        return sorted(found, key=lambda finding: finding["severity"] != "error")

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: FractureInputs, check_results: list[dict]) -> dict:
        base = StaticAnalysis.summary(self, result, inputs, check_results)
        checks = base.pop("checks")
        front_k = result.scalars["front_k"]
        index = result.scalars["K_index"]
        K = float(result.scalars["K_max"])
        toughness = result.scalars["toughness"]
        crack_echo = inputs.crack.as_dict()
        summary = {
            "crack": {**crack_echo, "words": crack_words(crack_echo)},
            "K_max_MPa_sqrt_m": round(K, 4),
            "K_I_MPa_sqrt_m": round(front_k.K_I[index], 4),
            "K_II_MPa_sqrt_m": round(front_k.K_II[index], 4),
            "K_III_MPa_sqrt_m": round(front_k.K_III[index], 4),
            "K_at_mm": [round(c, 3) for c in front_k.at_mm[index]],
            "K_point": result.scalars["K_point"],
            "toughness_MPa_sqrt_m": toughness,
            "fracture_factor": None if toughness is None or not K > 0 else _floored(toughness / K),
            "front": [
                {"front": front_k.front[i], "s_mm": round(front_k.s_mm[i], 4), "at_mm": [round(c, 3) for c in front_k.at_mm[i]],
                 "K_I": round(front_k.K_I[i], 4), "K_II": round(front_k.K_II[i], 4), "K_III": round(front_k.K_III[i], 4),
                 "J_N_per_mm": round(front_k.J_N_mm[i], 6)}
                for i in range(len(front_k.K_I))
            ],
            "front_size_mm": round(result.scalars["front_mm"], 4),
            "domain_radius_mm": round(result.scalars["radius_mm"], 4),
            "domain_change_percent": round(100.0 * front_k.spread, 2),
            "growth": None,
            **{key: base[key] for key in ("max_von_mises_MPa", "max_von_mises_at_mm", "max_displacement_mm",
                                          "max_displacement_at_mm", "applied_force_N", "reaction_force_N", "deformation_scale")},
        }
        growth = result.scalars.get("growth")
        if growth is not None:
            summary["growth"] = {
                "load_ratio": growth["load_ratio"], "paris_C": growth["paris_C"], "paris_m": growth["paris_m"],
                "cycles": float(f"{growth['cycles']:.4g}") if math.isfinite(growth["cycles"]) else None,
                "from_mm": inputs.crack.size_mm,
                "critical_mm": round(growth["critical_mm"], 4) if math.isfinite(growth["critical_mm"]) else None,
                "to_mm": round(growth["final_mm"], 4) if math.isfinite(growth["final_mm"]) else None,
                "start_rate_mm_per_cycle": float(f"{growth['rate_mm_per_cycle']:.4g}"),
            }
        summary["checks"] = checks
        return summary

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        """Static's, the stress colours capped below the front's singular peak (its 99th percentile)."""
        import numpy as np

        stress = np.asarray(result.fields["von_mises"], dtype=float)
        cap = float(np.quantile(stress, COLOUR_QUANTILE)) if len(stress) else 0.0
        top = min(summary["max_von_mises_MPa"], round(cap, 4)) if cap > 0 else summary["max_von_mises_MPa"]
        return {"von_mises": (0.0, top), "displacement": (0.0, summary["max_displacement_mm"])}

    def extras_name(self, stem: str) -> str:
        return f"{stem} crack"

    def extras_head(self, summary: dict) -> dict:
        """What the viewer reads of the crack: its words, the largest K and where, and the front's stations (for its markers)."""
        return {"crack": {
            "kind": summary["crack"]["kind"], "words": summary["crack"]["words"], "face": summary["crack"]["face"],
            "size_mm": summary["crack"]["size_mm"], "K_max_MPa_sqrt_m": summary["K_max_MPa_sqrt_m"], "K_point": summary["K_point"],
            "toughness_MPa_sqrt_m": summary["toughness_MPa_sqrt_m"],
            "front_mm": [station["at_mm"] for station in summary["front"]],
            "K_front": [station["K_I"] for station in summary["front"]],
        }}

    def extras_assembly(self, summary: dict) -> dict:
        return {}

    def study_echo(self, inputs: FractureInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = StaticAnalysis.study_echo(self, inputs, bare)
        crack = inputs.crack.as_dict()
        if inputs.crack.face is not None:
            crack["face"] = bare((inputs.crack.face,))[0]
        crack["words"] = crack_words(crack)
        echo["crack"] = crack
        if inputs.growth is not None:
            echo["growth"] = inputs.growth.as_dict()
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        K = summary["K_max_MPa_sqrt_m"]
        toughness = summary["toughness_MPa_sqrt_m"]
        lines = [
            f"crack: {summary['crack']['words']}; front meshed at {summary['front_size_mm']:g} mm, "
            f"J domain {summary['domain_radius_mm']:g} mm",
            f"K {K:.4g} MPa√m at {summary['K_point']} (K_I {summary['K_I_MPa_sqrt_m']:.4g}, K_II {summary['K_II_MPa_sqrt_m']:.3g}, "
            f"K_III {summary['K_III_MPa_sqrt_m']:.3g})"
            + (f", toughness {toughness:g} MPa√m: fracture factor {summary['fracture_factor']}" if toughness else ""),
            f"K changed {summary['domain_change_percent']:g}% between the two J domains",
        ]
        growth = summary.get("growth")
        if growth:
            to = growth["to_mm"]
            lines.append(
                f"crack growth (Paris C {growth['paris_C']:.3g} m/cycle, m {growth['paris_m']:g}, R {growth['load_ratio']:g}): "
                f"{growth['from_mm']:g} mm to {to if to is not None else '?'} mm in "
                f"{_cycles(growth['cycles']) if growth['cycles'] is not None else 'no end of'} cycles")
        lines.append(f"max displacement {summary['max_displacement_mm']} mm")
        return lines


def _front_length(prepared) -> float:
    """The front's length before meshing: the analytic front(s) clipped to the part's box."""
    from cadgen._internal.fea import crack

    total = 0.0
    for points in crack.front_polylines(prepared.crack, prepared.shape):
        total += _polyline_length(points)
    return total


def _polyline_length(points) -> float:
    import numpy as np

    points = np.asarray(points)
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()) if len(points) > 1 else 0.0


def _inside_crack(geometry, points):
    """Whether points of the crack's plane lie in the crack: its rectangle (edge, through) or ellipse."""
    import numpy as np

    rel = points - geometry.at
    u = rel @ geometry.d
    v = rel @ geometry.t
    if geometry.kind in ("edge", "through"):
        return np.abs(u) <= geometry.a * (1 + 1e-9)
    return (u / geometry.a) ** 2 + (v / geometry.c) ** 2 <= 1.0 + 1e-9


def _finding(severity: str, kind: str, summary: str, description: str, items: list[dict]) -> dict:
    return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description, "items": items}
