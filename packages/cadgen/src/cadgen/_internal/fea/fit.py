"""The fit-the-budget ladder: every analysis adapts to the machine instead of refusing a model.

A :class:`Budget` is a target, never a threshold. :func:`fit_budget` asks the
analysis what its current :class:`FitPlan` will cost (``analysis.estimate``)
and, while that misses the memory or the time target, takes the analysis's
next rung (``analysis.apply``), each a plain-worded :class:`Step` with its
accuracy cost where it can be estimated. A rung that does not apply (no thin
wall, no symmetry) is skipped without a word. When every rung is taken and the
estimate still misses, the run goes ahead anyway and the last step says how
long and how much memory to expect. Nothing is refused for size or time.

The rungs every solid analysis shares live here (:func:`apply_generic`):
``iterative`` (an AMG-preconditioned or a matrix-free solver), ``local_refine``
(a coarse pass, then a pass fine only where the coarse one peaked),
``defeature`` (:mod:`.defeature`), ``linear_elements`` (4-node tets),
``idealise`` (:data:`IDEALISERS`, filled by the shell and beam modules) and
``symmetry`` (:mod:`.symmetry`). An analysis plugs in by declaring ``ladder``
and implementing ``estimate`` (often :func:`solid_estimate`) and ``apply``
(often :func:`apply_generic`).

The cost models are per method, from mesh counts: a netgen mesh holds about
4.5 V/h^3 + 2 A/h^2 tetrahedra, plus a band at each curved or narrow face the
mesher refines below h; a quadratic vector space costs about 80 kB per element
to build and assemble; the stiffness has about 77 entries per row (quadratic)
or 40 (linear); AMG keeps about three times the matrix; SuperLU's factor
grows as n^1.5. The constants were measured on this engine's own meshes and
solves; they aim to be right within a factor of three, which is what choosing
a rung needs.

Stdlib at import; numeric work inside the functions.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cadgen._internal.fea.analyses.base import Analysis, Inputs, Rung, SolveContext

__all__ = [
    "Budget", "Estimate", "FaceInfo", "FitPlan", "Geometry", "IDEALISERS", "Step", "TAIL", "apply_generic",
    "default_budget", "fit_budget", "governing", "human_bytes", "human_seconds", "solid_estimate", "solve_idealised",
    "tets_estimate",
]

GIB = 2 ** 30
#: The closing step's ``rung``: the run went ahead past the budget, and says what to expect.
TAIL = "budget"
#: The time target a study gets when it names none, seconds.
DEFAULT_SECONDS = 600.0
#: The local_refine rung's governing region: the top share of the coarse pass's governing field.
PEAK_SHARE = 0.02
#: At most this many points of that region become local sizes (an even subsample beyond it).
MAX_POINTS = 64
#: The coarse pass of local_refine: at most this many times the requested size, and a part's diagonal over this.
MAX_COARSENING, MIN_ELEMENTS_ACROSS = 4.0, 8.0
#: Defeaturing: a feature under this many coarse elements is small; it must lie this many element sizes from named faces.
SMALL_FEATURE_ELEMENTS, FAR_ELEMENTS = 2.0, 3.0
#: Linear tetrahedra's accuracy when it cannot be measured (the stated table).
LINEAR_TABLE_NOTE = "linear tets read bending stress about 10-30% low at 3 elements through the thickness"

#: Idealisers by name ("shell", "beam"): each ``(analysis, ctx, inputs) -> Step | None`` changes
#: ``ctx.plan.idealisation`` when its detection is unambiguous, and carries ``estimate(ctx)`` and
#: ``solve(analysis, ctx, inputs)`` for the plan it made. The shell and beam modules register on import.
IDEALISERS: dict[str, Callable[..., "Step | None"]] = {}
#: The rungs that only shrink the solid solve, which an idealised model replaces (and its idealiser undoes).
SUPERSEDED_BY_IDEALISE = ("iterative", "local_refine", "linear_elements")


def _idealisers() -> dict:
    from cadgen._internal.fea import beam, shell  # noqa: F401  (they register in IDEALISERS)

    return IDEALISERS


def solve_idealised(analysis, ctx, inputs):
    """The idealised model's solve when the ladder chose one (``ctx.plan.idealisation``), else ``None``."""
    plan = getattr(ctx, "plan", None)
    if plan is None or plan.idealisation == "solid":
        return None
    return _idealisers()[plan.idealisation].solve(analysis, ctx, inputs)


@dataclass(frozen=True)
class Budget:
    """Targets, never thresholds: they choose ladder steps and nothing is refused for them."""

    memory_bytes: int            # default: half of physical RAM (os.sysconf), at least 2 GiB
    seconds: float               # wall-clock target, default 600
    max_frames: int = 24         # series frames written to the GLB


@dataclass(frozen=True)
class Estimate:
    dofs: int
    memory_bytes: int            # predicted peak: matrix nnz, factor fill or AMG hierarchy, frames, state
    seconds: float               # predicted from dofs, nnz, modes, steps, iterations (calibrated per method)

    def fits(self, budget: Budget) -> bool:
        return self.memory_bytes <= budget.memory_bytes and self.seconds <= budget.seconds


@dataclass(frozen=True)
class Step:
    """One ladder step taken, said in plain words."""

    rung: "Rung | str"
    words: str                   # "Coarsened the mesh away from the hole to fit: the peak is still meshed at 0.8 mm"
    accuracy: str | None         # "peak stress moved 2.1% between the coarse and the refined pass" or None (exact)
    accuracy_pct: float | None   # the number behind `accuracy`, when there is one
    faces: tuple[str, ...] = ()  # faces the step concerns (kept fine, left out), for the viewer's tint
    detail: dict = field(default_factory=dict)   # numbers: {"from_size_mm": 2, "to_size_mm": 4, "kept_mm": 0.8}

    def as_dict(self) -> dict:
        """The step as ``extras.fit`` and the sidecar's ``fit`` carry it."""
        return {
            "rung": self.rung, "words": self.words, "accuracy": self.accuracy,
            "accuracy_pct": None if self.accuracy_pct is None else round(self.accuracy_pct, 2),
            "faces": list(self.faces), "detail": dict(self.detail),
        }

    def finding(self) -> dict:
        """The step as an info finding of kind ``fit_<rung>``, for the agent."""
        return {
            "check": "fea", "severity": "info", "type": f"fit_{self.rung}",
            "summary": self.words + (f" ({self.accuracy})" if self.accuracy else ""),
            "description": "cadgen adapted the model to fit the memory and time it had; the run still completed",
            "items": [],
        }


@dataclass
class FitPlan:
    solver: Literal["direct", "iterative", "matrix_free"] = "direct"
    size_mm: float | None = None                 # global element size
    size_field: dict | None = None               # local sizes: {"faces": {...}, "points": [...], "radius_mm": ...}
    defeatured: tuple[str, ...] = ()             # face refs removed for meshing
    order: int = 2
    idealisation: Literal["solid", "shell", "beam"] = "solid"
    modes: int | None = None                     # modes kept (dynamics)
    symmetry: tuple[str, ...] = ()               # planes used: ("x", "y")
    mass_scale_dt: float | None = None           # explicit target step
    subcycle: int = 1
    window_s: float | None = None
    adaptive_steps: bool = False
    fluid_far_size_mm: float | None = None
    re_schedule: tuple[float, ...] = ()          # Reynolds continuation
    # Additive to the spec's fields: what the ladder itself keeps.
    #: The rungs the study allows (``fit.allow``); ``None`` for every rung of the analysis's ladder.
    allow: tuple[str, ...] | None = None
    #: The rungs already offered to the analysis, taken or not: a second fit_budget pass resumes after them.
    tried: list[str] = field(default_factory=list)
    #: The rungs taken, over every fit_budget pass.
    taken: list[str] = field(default_factory=list)
    #: local_refine: the size the governing region keeps (the requested size); set means two passes.
    refine_to_mm: float | None = None
    #: The element size the study asked for (or the default), before any rung.
    requested_mm: float | None = None
    #: The last estimate fit_budget made, for the closing words and the finer re-solve's choice.
    estimate: Estimate | None = None
    #: What the rungs that change the geometry made (:mod:`.defeature`, :mod:`.symmetry`): the shape to mesh.
    prepared: Any = None

    @property
    def two_pass(self) -> bool:
        return self.refine_to_mm is not None

    @property
    def changes_mesh(self) -> bool:
        return bool(self.two_pass or self.defeatured or self.order != 2 or self.symmetry or self.idealisation != "solid")


@dataclass(frozen=True)
class FaceInfo:
    """One face of the geometry, as the cost model and the defeaturing rung read it."""

    ordinal: int
    ref: str
    kind: str                     # "plane", "cylinder", "torus", "sphere", "cone", "other"
    size_mm: float                # radius of a curved face; a planar face's width (2 area / perimeter)
    area_mm2: float
    center: tuple[float, float, float]


@dataclass
class Geometry:
    """What the ladder knows of the part before it is meshed: enough to estimate and to simplify it."""

    volume_mm3: float
    area_mm2: float
    bbox_diagonal_mm: float
    faces: tuple[FaceInfo, ...] = ()
    #: The occurrence's OCP shape (one part); ``None`` for an assembly, which defeature and symmetry skip.
    shape: Any = None
    occurrence_ref: str = ""
    parts: int = 1


def default_budget(override: dict | None = None) -> Budget:
    """Half the machine's physical memory (at least 2 GiB) and ten minutes; a study's ``fit`` overrides either."""
    override = override or {}
    try:
        physical = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        physical = 8 * GIB
    memory = max(physical // 2, 2 * GIB)
    if override.get("memory_GB") is not None:
        memory = int(float(override["memory_GB"]) * GIB)
    seconds = float(override["seconds"]) if override.get("seconds") is not None else DEFAULT_SECONDS
    return Budget(memory_bytes=max(memory, 1), seconds=seconds)


# -- words -------------------------------------------------------------------------------------------


def human_seconds(seconds: float) -> str:
    """"40 seconds", "25 minutes", "3 hours": what a person reads the expected time as."""
    if seconds < 90:
        return f"{max(1, round(seconds))} seconds"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)} minutes"
    if seconds < 48 * 3600:
        hours = seconds / 3600
        return f"{hours:.1f} hours" if hours < 10 else f"{round(hours)} hours"
    return f"{round(seconds / 86400)} days"


def human_bytes(count: float) -> str:
    """"600 MB", "9 GB": memory as a person reads it."""
    if count >= GIB:
        gb = count / GIB
        return f"{gb:.1f} GB" if gb < 10 else f"{round(gb)} GB"
    return f"{max(1, round(count / 2 ** 20))} MB"


def _size(mm: float) -> str:
    return f"{mm:.3g} mm"


def _tail(estimate: Estimate, budget: Budget, taken: list[str], allowed_none: bool) -> Step:
    expect = f"expect about {human_seconds(estimate.seconds)} and {human_bytes(estimate.memory_bytes)}"
    if allowed_none:
        words = f"Solved the full model because the study allows no simplification; {expect}"
    elif taken:
        words = f"Every way to shrink this was used; {expect}"
    else:
        words = f"Nothing could shrink this model; {expect}"
    return Step(TAIL, words, None, None, detail={
        "expected_s": round(estimate.seconds, 1), "expected_bytes": int(estimate.memory_bytes), "dofs": int(estimate.dofs),
        "budget_s": budget.seconds, "budget_bytes": int(budget.memory_bytes),
    })


# -- the ladder --------------------------------------------------------------------------------------


def fit_budget(analysis: "Analysis", ctx: "SolveContext", inputs: "Inputs", *, tail: bool = True) -> list[Step]:
    """Try the analysis's rungs in order, each changing ctx.plan, until analysis.estimate() fits
    ctx.budget. Never raises for size or time. When every applicable rung is taken and the estimate
    still misses, the run goes ahead, and the last Step says how long and how much memory to expect
    ("Every way to shrink this was used; expect about 25 minutes and 9 GB").

    ``tail=False`` leaves the closing step out (a first pass before meshing, resumed after it):
    rungs already offered (``ctx.plan.tried``) are not offered again.
    """
    plan, budget = ctx.plan, ctx.budget
    steps: list[Step] = []
    estimate = analysis.estimate(ctx, inputs)
    for rung in getattr(analysis, "ladder", ()):
        if estimate.fits(budget):
            break
        if rung in plan.tried:
            continue
        plan.tried.append(rung)
        if plan.allow is not None and rung not in plan.allow:
            continue
        step = analysis.apply(rung, ctx, inputs)
        if step is None:
            continue
        if rung == "idealise" and plan.idealisation != "solid":
            # The shell or beam replaces the solid solve those rungs shrank (the idealiser undid them): unsaid.
            steps = [s for s in steps if s.rung not in SUPERSEDED_BY_IDEALISE]
            plan.taken = [r for r in plan.taken if r not in SUPERSEDED_BY_IDEALISE]
        steps.append(step)
        plan.taken.append(rung)
        estimate = analysis.estimate(ctx, inputs)
    plan.estimate = estimate
    if tail and not estimate.fits(budget):
        steps.append(_tail(estimate, budget, plan.taken, plan.allow is not None and not plan.allow))
    return steps


def apply_generic(rung: str, analysis: "Analysis", ctx: "SolveContext", inputs: "Inputs") -> Step | None:
    """The shared solid rungs, for any analysis whose ``estimate`` reads the plan's solver, size, order,
    defeaturing and symmetry (:func:`solid_estimate` does). ``None`` when the rung does not apply."""
    def estimate() -> Estimate:
        return analysis.estimate(ctx, inputs)

    if rung == "iterative":
        return _apply_iterative(ctx, estimate)
    if rung == "local_refine":
        return _apply_local_refine(ctx, estimate)
    if rung == "defeature":
        return _apply_defeature(ctx, inputs)
    if rung == "linear_elements":
        return _apply_linear(analysis, ctx)
    if rung == "idealise":
        for idealiser in _idealisers().values():
            step = idealiser(analysis, ctx, inputs)
            if step is not None:
                return step
        return None
    if rung == "symmetry":
        return _apply_symmetry(analysis, ctx, inputs)
    return None


def _apply_iterative(ctx, estimate: Callable[[], Estimate]) -> Step | None:
    """An iterative solver: AMG + CG on the assembled matrix, or, where memory is what misses and storing
    no matrix saves the most, matrix-free CG. Taken only when it saves materially (5 %) what misses."""
    plan, budget = ctx.plan, ctx.budget
    if plan.solver != "direct":
        return None
    before = estimate()
    options = {}
    for solver in ("iterative", "matrix_free"):
        plan.solver = solver
        options[solver] = estimate()
    plan.solver = "direct"
    if before.memory_bytes > budget.memory_bytes:
        solver = min(options, key=lambda name: (options[name].memory_bytes > budget.memory_bytes, options[name].memory_bytes))
        if options[solver].memory_bytes - BASE_BYTES > 0.95 * (before.memory_bytes - BASE_BYTES):
            return None
        why = "fit in memory"
    else:
        solver = "iterative"
        if options[solver].seconds > 0.95 * before.seconds:
            return None
        why = "finish sooner"
    plan.solver = solver
    detail = {"solver": solver, "from_bytes": int(before.memory_bytes), "to_bytes": int(options[solver].memory_bytes)}
    if solver == "matrix_free":
        return Step("iterative", f"Used a matrix-free iterative solver to {why}: no stiffness matrix is stored", None, None, detail=detail)
    return Step("iterative", f"Used an iterative solver to {why}", None, None, detail=detail)


def _apply_local_refine(ctx, estimate: Callable[[], Estimate]) -> Step | None:
    """Coarse everywhere at the size that fits, then (in run.py) fine where the coarse pass peaked."""
    plan, budget, geometry = ctx.plan, ctx.budget, ctx.geometry
    if plan.two_pass or plan.requested_mm is None:
        return None
    fine = plan.requested_mm
    diagonal = geometry.bbox_diagonal_mm if geometry is not None else (ctx.volume.bbox_diagonal if ctx.volume is not None else 0.0)
    ceiling = min(MAX_COARSENING * fine, diagonal / MIN_ELEMENTS_ACROSS) if diagonal else MAX_COARSENING * fine
    if ceiling < 1.25 * fine:
        return None
    original = plan.size_mm
    plan.refine_to_mm = fine
    # The coarsest size that fits, found from the finest end: the coarse pass is as fine as the budget allows.
    chosen = ceiling
    for k in range(1, 13):
        size = fine * (ceiling / fine) ** (k / 12)
        plan.size_mm = size
        if estimate().fits(budget):
            chosen = size
            break
    if chosen < 1.25 * fine:
        chosen = 1.25 * fine
    plan.size_mm = chosen
    return Step(
        "local_refine",
        f"Coarsened the mesh away from the peak to fit: the peak is still meshed at {_size(fine)}",
        None, None, detail={"from_size_mm": round(original or fine, 4), "to_size_mm": round(chosen, 4), "kept_mm": round(fine, 4)},
    )


def _apply_defeature(ctx, inputs) -> Step | None:
    from cadgen._internal.fea import defeature

    plan, geometry = ctx.plan, ctx.geometry
    if geometry is None or geometry.shape is None or plan.defeatured or plan.symmetry:
        return None
    size = plan.size_mm or plan.requested_mm
    named = _named_ordinals(ctx, inputs)
    found = defeature.small_features(geometry, size, named)
    if not found:
        return None
    prepared = defeature.defeature(geometry, found)
    if prepared is None:
        return None
    removed = tuple(face.ref for feature in found for face in feature.faces)
    plan.defeatured = removed
    plan.prepared = prepared
    words = f"Left out {defeature.describe(found)} far from the loads and fixtures to mesh it"
    return Step("defeature", words, None, None, faces=removed,
                detail={"features": len(found), "faces": len(removed), "largest_mm": round(max(f.size_mm for f in found), 4)})


def _apply_linear(analysis, ctx) -> Step | None:
    plan = ctx.plan
    if plan.order != 2:
        return None
    plan.order = 1
    return Step("linear_elements", "Used linear elements to fit: stresses may read low", LINEAR_TABLE_NOTE, None,
                detail={"order": 1, "measured": False})


def _apply_symmetry(analysis, ctx, inputs) -> Step | None:
    from cadgen._internal.fea import symmetry

    plan, geometry = ctx.plan, ctx.geometry
    if geometry is None or geometry.shape is None or plan.symmetry or plan.idealisation != "solid":
        return None
    check = getattr(analysis, "symmetric_about", None)
    if check is None:
        return None
    planes = symmetry.planes_of(geometry, plan.prepared)
    usable = [plane for plane in planes if check(plane, inputs, ctx)]
    if not usable:
        return None
    usable = usable[:2]
    prepared = symmetry.cut(geometry, plan.prepared, usable)
    if prepared is None:
        return None
    plan.prepared = prepared
    plan.symmetry = tuple(plane.axis for plane in usable)
    part = "half" if len(usable) == 1 else "quarter"
    across = " and ".join(f"the {plane.axis.upper()} = {plane.offset:.4g} mm plane" for plane in usable)
    return Step("symmetry", f"Solved one {part} of the part, which is symmetric about {across}, and mirrored the result",
                None, None, detail={"planes": [plane.as_dict() for plane in usable]})


def _named_ordinals(ctx, inputs) -> set[int]:
    refs = set(getattr(inputs, "face_refs", ())) | set(getattr(ctx.study, "check_faces", ()) if ctx.study is not None else ())
    return {ctx.ordinal_of[ref] for ref in refs if ref in ctx.ordinal_of}


# -- the second pass of local_refine ----------------------------------------------------------------


def governing(analysis, result) -> tuple[Any, float]:
    """The field a pass's local sizes follow and the value two passes compare: the analysis's own
    (``governing_field``/``governing_value``), else its first scalar field and that field's maximum."""
    import numpy as np

    if hasattr(analysis, "governing"):
        return analysis.governing(result)
    spec = next(spec for spec in analysis.fields if spec.components == 1 and spec.name in result.fields)
    values = np.asarray(result.fields[spec.name], dtype=float)
    return values, float(values.max())


def refine_field(analysis, ctx, inputs, result, budget: Budget, estimate: Callable[[dict], Estimate]) -> dict:
    """The second pass's local sizes: the requested size within two elements of the coarse pass's
    governing region (its top 2 %), and on the named faces when they still fit."""
    import numpy as np

    plan = ctx.plan
    fine = plan.refine_to_mm
    values, _ = governing(analysis, result)
    locations = np.asarray(result.dof_locations)[: len(values)]
    cut = np.quantile(values, 1.0 - PEAK_SHARE)
    hot = np.flatnonzero(values >= cut)
    if len(hot) > MAX_POINTS:
        hot = hot[np.argsort(values[hot])[::-1][:MAX_POINTS]]
    points = [[*map(float, locations[i]), float(fine)] for i in hot]
    field: dict = {"points": points, "radius_mm": 2.0 * fine}
    # An assembly's mesher keys local sizes by face ref, not ordinal: its second pass refines at the peak only.
    named = sorted(_named_ordinals(ctx, inputs)) if ctx.assembly is None else []
    if named:
        with_faces = {**field, "faces": {ordinal: float(fine) for ordinal in named}}
        if estimate(with_faces).fits(budget) or estimate(with_faces).memory_bytes <= 1.5 * estimate(field).memory_bytes:
            field = with_faces
    return field


def pass_step(step: Step, first: float, second: float, word: str) -> Step:
    """The local_refine step with its accuracy: how far the governing value moved between the passes."""
    pct = 100.0 * abs(second - first) / abs(second) if second else 0.0
    return replace(step, accuracy=f"{word} moved {pct:.1f}% between the coarse and the refined pass", accuracy_pct=pct,
                   detail={**step.detail, "coarse_value": round(first, 6), "refined_value": round(second, 6)})


# -- cost models -------------------------------------------------------------------------------------

#: Tetrahedra per mm^3 at size h: VOLUME_TETS / h^3, plus SURFACE_TETS / h^2 per mm^2 of surface.
VOLUME_TETS, SURFACE_TETS = 4.5, 2.0
#: netgen's curvature safety (mesh._MESHING): a curved face of radius r gets elements of about r / this.
CURVATURE_SAFETY = 1.5
#: Scalar nodes per tetrahedron: quadratic (corners and mid-edges) and linear (corners).
NODES_PER_TET = {2: 1.7, 1: 0.25}
#: Stiffness entries per vector DOF row.
NNZ_PER_ROW = {2: 77.0, 1: 40.0}
#: Bytes per element to build the space, the element matrices and recover stress (measured: 79 kB quadratic).
BYTES_PER_ELEMENT = {2: 80_000.0, 1: 12_000.0}
#: Of those, the matrix-free product keeps the space's basis only.
BASIS_BYTES_PER_ELEMENT = {2: 72_000.0, 1: 10_000.0}
#: Seconds per element: meshing, assembly and recovery (measured ~0.2 ms quadratic).
SECONDS_PER_ELEMENT = {2: 2.5e-4, 1: 4e-5}
#: AMG + CG: seconds per DOF, and the hierarchy's size as a multiple of the matrix.
AMG_SECONDS_PER_DOF, AMG_COPIES = 6e-5, 4.0
#: SuperLU: factor entries ~ FILL * n^1.5, time ~ DIRECT_SECONDS * n^2.
FILL, DIRECT_SECONDS = 1.2, 2.5e-9
#: The solve that chooses its own method goes direct below this many DOF (operators.DIRECT_SOLVE_BELOW).
DIRECT_BELOW = 20_000
#: Matrix-free CG: iterations ~ MF_ITERATIONS * n^(1/3) (690 at 2.5k DOF), each product this many seconds per element.
MF_ITERATIONS, MF_SECONDS_PER_ELEMENT = 50.0, {2: 6.5e-5, 1: 1e-5}
#: Python and the CAD kernel, before any mesh.
BASE_BYTES = 300 * 2 ** 20


def _face_band(face: FaceInfo, h: float) -> float:
    """Extra tetrahedra where the mesher refines a curved or narrow face below h."""
    if face.kind in ("cylinder", "torus", "sphere", "cone"):
        local = face.size_mm / CURVATURE_SAFETY
    else:
        local = face.size_mm
    if not local > 0 or local >= h:
        return 0.0
    return (VOLUME_TETS + SURFACE_TETS) * face.area_mm2 * (1.0 / local ** 2 - 1.0 / h ** 2)


def tets_estimate(geometry: Geometry, size_mm: float, *, removed: tuple[str, ...] = (), size_field: dict | None = None,
                  share: float = 1.0) -> float:
    """Tetrahedra netgen makes of ``geometry`` at ``size_mm``; ``removed`` faces are left out, ``share`` the
    part kept (a symmetric half is 0.5), ``size_field`` adds its fine regions."""
    h = float(size_mm)
    gone = set(removed)
    tets = VOLUME_TETS * geometry.volume_mm3 / h ** 3 + SURFACE_TETS * geometry.area_mm2 / h ** 2
    tets += sum(_face_band(face, h) for face in geometry.faces if face.ref not in gone)
    tets *= share
    if size_field:
        by_ordinal = {face.ordinal: face for face in geometry.faces}
        for ordinal, fine in (size_field.get("faces") or {}).items():
            face = by_ordinal.get(ordinal)
            if face is not None and fine < h:
                tets += share * (VOLUME_TETS * 2.0 + SURFACE_TETS) * face.area_mm2 * (1.0 / fine ** 2 - 1.0 / h ** 2)
        radius = float(size_field.get("radius_mm") or 0.0)
        points = size_field.get("points") or ()
        if points:
            fine = min(float(p[3]) for p in points)
            ball = (4.0 / 3.0) * math.pi * (radius + 2 * fine) ** 3
            # Points closer than a ball apart share their region: count the union at most as the part's volume.
            region = min(len(points) * ball, geometry.volume_mm3 * share)
            if fine < h:
                tets += VOLUME_TETS * region * (1.0 / fine ** 3 - 1.0 / h ** 3)
    return max(tets, 1.0)


def solve_cost(elements: float, nodes: float, *, components: int = 3, order: int = 2, solver: str = "direct",
               extra_bytes: float = 0.0) -> Estimate:
    """Memory and time of building, solving and recovering one linear system on a mesh."""
    n = max(int(nodes * components), 1)
    scale = components / 3.0
    nnz = NNZ_PER_ROW[order] * scale * n
    matrix = 12.0 * nnz
    build = BYTES_PER_ELEMENT[order] * scale * elements
    seconds = SECONDS_PER_ELEMENT[order] * scale * elements
    if solver == "matrix_free":
        memory = BASIS_BYTES_PER_ELEMENT[order] * scale * elements + 80.0 * n
        iterations = MF_ITERATIONS * n ** (1.0 / 3.0)
        seconds += iterations * MF_SECONDS_PER_ELEMENT[order] * scale * elements
    elif solver == "iterative" or n >= DIRECT_BELOW:
        memory = build + matrix * (1.0 + AMG_COPIES)
        seconds += AMG_SECONDS_PER_DOF * n
    else:
        memory = build + matrix * 2.0 + 16.0 * FILL * n ** 1.5
        seconds += DIRECT_SECONDS * n ** 2
    return Estimate(dofs=n, memory_bytes=int(BASE_BYTES + memory + extra_bytes), seconds=float(seconds))


def _plan_counts(ctx) -> tuple[float, float, bool]:
    """(elements, scalar nodes, two passes) of the mesh the plan will make: counted on ``ctx.volume`` when the
    plan meshes as it was meshed, else from the geometry."""
    plan = ctx.plan
    volume = ctx.volume
    if volume is not None and getattr(ctx, "meshed_plan", None) == _mesh_key(plan):
        elements = float(len(volume.tets))
        nodes = float(len(volume.nodes))
        if plan.order == 1 and volume.tets.shape[1] == 10:
            nodes = float(len(set(volume.tets[:, :4].ravel().tolist())))
        return elements, nodes, False
    geometry = ctx.geometry
    size = plan.size_mm or plan.requested_mm
    share = 0.5 ** len(plan.symmetry)
    if geometry is None:  # a meshed study with no geometry: scale the mesh it has
        elements = float(len(volume.tets)) * (volume.max_h / size) ** 3 * share
    else:
        elements = tets_estimate(geometry, size, removed=plan.defeatured, share=share)
    return elements, elements * NODES_PER_TET[plan.order], plan.two_pass


def _mesh_key(plan: FitPlan) -> tuple:
    return (plan.size_mm, plan.order, plan.defeatured, plan.symmetry, plan.idealisation)


def solid_estimate(ctx, *, components: int = 3, extra_bytes: float = 0.0, extra_seconds: float = 0.0,
                   passes: float = 1.0) -> Estimate:
    """What one linear solve on the plan's mesh costs (a vector field: ``components`` 3; a scalar one: 1).
    A two-pass plan pays for its coarse pass and its refined one. An idealised plan costs its idealiser's model."""
    plan = ctx.plan
    if plan.idealisation != "solid" and plan.idealisation in _idealisers():
        return IDEALISERS[plan.idealisation].estimate(ctx)
    elements, nodes, two = _plan_counts(ctx)
    cost = solve_cost(elements, nodes, components=components, order=plan.order, solver=plan.solver, extra_bytes=extra_bytes)
    seconds = cost.seconds * passes + extra_seconds
    if two and ctx.geometry is not None:
        share = 0.5 ** len(plan.symmetry)
        size = plan.size_mm
        field = plan.size_field or {"points": [[0.0, 0.0, 0.0, plan.refine_to_mm]] * 8, "radius_mm": 2 * plan.refine_to_mm}
        fine = tets_estimate(ctx.geometry, size, removed=plan.defeatured, share=share, size_field=field)
        second = solve_cost(fine, fine * NODES_PER_TET[plan.order], components=components, order=plan.order,
                            solver=plan.solver, extra_bytes=extra_bytes)
        return Estimate(second.dofs, max(cost.memory_bytes, second.memory_bytes), seconds + second.seconds * passes)
    return Estimate(cost.dofs, cost.memory_bytes, seconds)


# -- geometry ----------------------------------------------------------------------------------------


def geometry_of(shape, occurrence_ref: str = "", *, parts: int = 1, keep_shape: bool = True) -> Geometry:
    """Volume, area, diagonal and every face's kind and size of an OCP shape, in cadgen's face order."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.GProp import GProp_GProps

    from cadgen._internal.entity_ordinals import entity_map
    from cadgen._internal.fea.mesh import _bbox_diagonal

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume = float(props.Mass())
    faces = entity_map(shape, "face")
    infos = []
    total = 0.0
    for ordinal in range(1, faces.Extent() + 1):
        face = faces.FindKey(ordinal)
        surface = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, surface)
        area = float(surface.Mass())
        centre = surface.CentreOfMass()
        total += area
        adaptor = BRepAdaptor_Surface(_as_face(face))
        kind_id = adaptor.GetType()
        if kind_id == GeomAbs_Cylinder:
            kind, size = "cylinder", adaptor.Cylinder().Radius()
        elif kind_id == GeomAbs_Torus:
            kind, size = "torus", adaptor.Torus().MinorRadius()
        elif kind_id == GeomAbs_Sphere:
            kind, size = "sphere", adaptor.Sphere().Radius()
        elif kind_id == GeomAbs_Cone:
            kind, size = "cone", max(_perimeter_width(face, area), 1e-9)
        elif kind_id == GeomAbs_Plane:
            kind, size = "plane", _perimeter_width(face, area)
        else:
            kind, size = "other", _perimeter_width(face, area)
        prefix = occurrence_ref or ""
        infos.append(FaceInfo(ordinal, f"{prefix}.f{ordinal}" if prefix else f"f{ordinal}", kind, float(size), area,
                              (centre.X(), centre.Y(), centre.Z())))
    return Geometry(volume, total, _bbox_diagonal(shape), tuple(infos), shape if keep_shape else None, occurrence_ref, parts)


def _as_face(shape):
    from OCP.TopoDS import TopoDS

    return TopoDS.Face_s(shape)


def _perimeter_width(face, area: float) -> float:
    """A face's width as 2 area / perimeter: a long strip's width, half a square's side."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.LinearProperties_s(face, props)
    perimeter = float(props.Mass())
    return 2.0 * area / perimeter if perimeter > 0 else 0.0


def merge_geometry(parts: list[Geometry]) -> Geometry:
    """An assembly's geometry for the cost model: its parts' volumes, areas and faces together, no shape."""
    return Geometry(
        volume_mm3=sum(g.volume_mm3 for g in parts), area_mm2=sum(g.area_mm2 for g in parts),
        bbox_diagonal_mm=max((g.bbox_diagonal_mm for g in parts), default=0.0),
        faces=tuple(face for g in parts for face in g.faces), shape=None, parts=len(parts),
    )


# -- linear elements' accuracy, measured --------------------------------------------------------------


def measure_linear(analysis, step: Step, budget: Budget, geometry: Geometry | None, plan: FitPlan,
                   mesh: Callable, solve_on: Callable, context: Callable, inputs) -> Step:
    """The linear_elements step with a measured accuracy note: where a quadratic solve fits at some
    coarser size, both orders are solved there and the governing values compared. Else the stated table."""
    if geometry is None or plan.requested_mm is None:
        return step
    saved = (plan.size_mm, plan.order, plan.refine_to_mm, plan.size_field)
    ceiling = geometry.bbox_diagonal_mm / MIN_ELEMENTS_ACROSS
    try:
        plan.refine_to_mm, plan.size_field, plan.order = None, None, 2
        size = None
        for k in range(1, 9):
            candidate = plan.requested_mm * 2 ** (k / 2)
            if candidate > ceiling:
                break
            plan.size_mm = candidate
            quadratic = analysis.estimate(context(None), inputs)
            if quadratic.memory_bytes <= budget.memory_bytes and 2 * quadratic.seconds <= budget.seconds:
                size = candidate
                break
        if size is None:
            return step
        plan.size_mm, plan.order = size, 2
        _, _, quad = solve_on(mesh(size))
        plan.order = 1
        _, _, lin = solve_on(mesh(size))
        q, l = governing(analysis, quad)[1], governing(analysis, lin)[1]
    except Exception:  # noqa: BLE001 - the measurement is a note; the run stands without it
        return step
    finally:
        plan.size_mm, plan.order, plan.refine_to_mm, plan.size_field = saved
    if not q:
        return step
    pct = 100.0 * (l - q) / abs(q)
    note = f"linear elements read the peak {abs(pct):.1f}% {'low' if pct < 0 else 'high'} against quadratic ones on a {size:.3g} mm check pass"
    return replace(step, accuracy=note, accuracy_pct=abs(pct), detail={**step.detail, "measured": True, "check_size_mm": round(size, 4)})
