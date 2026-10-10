"""Shaking: the part's steady response to a sine sweep, shaken at its fixtures or pushed by swinging forces.

The study (spec 5.8) holds the part at its ``fixtures`` and shakes it one of two
ways (``excitation``):

- ``base``: the fixtures move together along ``direction`` with an
  acceleration of ``amplitude_g`` (a shaker table, a vehicle's mount);
- ``force``: the ``loads`` (forces and pressures on faces) swing at the
  sweep's frequency with the size written (a motor's out-of-balance).

The sweep (``sweep_Hz``) runs from low to high with modal damping
``damping_ratio`` (default 0.02). The answer is built by modal superposition
(:mod:`cadgen._internal.fea.superposition`) from every mode up to 1.5 × the
sweep's top. What it writes:

- a series of frequency frames: the response peaks (up to 6) plus evenly spaced
  log frequencies, at most ``Budget.max_frames``; each frame carries the
  displacement relative to the base (its real and imaginary parts, so a viewer
  can turn it through a cycle) and von Mises at its peak over the cycle;
- curves of the largest displacement and the largest (absolute) acceleration
  against frequency;
- checks ``stress`` (the peak over the sweep against yield), ``displacement``
  and ``acceleration`` (``limit_g``, optional ``faces``), each saying the
  frequency where it peaks;
- a finding when the modes found hold under 80 % of the mass along the shake.

The ladder's own rung is ``reduce_modes``: only the fewest modes holding 90 %
of the mass moving along the shake are kept, and its words say the share. The
mesh rungs are the shared ones. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.modal import (
    align_degenerate, apply_eigen_rung, eigen_estimate, fixed_dofs, hz_text, materials_of, max_frames, solver_method,
)
from cadgen._internal.fea.study import Fixture, Load, parse_fixtures, parse_loads

if TYPE_CHECKING:
    import numpy as np

__all__ = ["HarmonicAnalysis", "HarmonicInputs", "choose_frames", "sweep_grid"]

G0_MM_S2 = 9806.65
#: Modes are found up to this multiple of the sweep's top (spec 5.8).
TOP_FACTOR = 1.5
#: reduce_modes keeps the fewest modes holding this share of the mass moving along the shake.
KEEP_SHARE = 0.9
#: Under this share of the mass along the shake, the modes found may miss part of the response: a finding.
MASS_WARNING = 0.8
#: The response peaks a series keeps as frames (spec 5.8).
PEAK_FRAMES = 6
#: Log-spaced points the curves run over, before the points added around each mode.
GRID_POINTS = 160
#: The number of modes the ladder assumes before the solve has found them, and after reduce_modes.
GUESS_MODES = 20
REDUCED_GUESS = 6
#: Acceleration and stress checks are close at 90 % of their limit.
_CLOSE_AT = 0.9
_TWO_PI = 2.0 * math.pi
_AXES = "XYZ"


@dataclass(frozen=True)
class HarmonicInputs(Inputs):
    fixtures: tuple[Fixture, ...] = ()
    #: ``force`` excitation: the loads, as amplitudes.
    loads: tuple[Load, ...] = ()
    #: "base" (the fixtures shaken) or "force" (the loads swinging).
    excitation: str = "base"
    #: The shake's direction, a unit vector (base only).
    direction: tuple[float, float, float] | None = (0.0, 0.0, 1.0)
    amplitude_g: float = 1.0
    sweep_Hz: tuple[float, float] = (10.0, 2000.0)
    damping_ratio: float = 0.02

    @property
    def top_Hz(self) -> float:
        """The highest mode the response is built from: 1.5 × the sweep's top."""
        return TOP_FACTOR * self.sweep_Hz[1]


def _unit(vector, where: str) -> tuple[float, float, float]:
    if not isinstance(vector, list) or len(vector) != 3:
        raise ValueError(f"{where}: the direction it is shaken along as [x, y, z], like [0, 0, 1] for Z")
    values = [kinds.number(v, where=where) for v in vector]
    size = math.sqrt(sum(v * v for v in values))
    if size == 0:
        raise ValueError(f"{where}: the direction is zero; give the axis it is shaken along, like [0, 0, 1]")
    return tuple(v / size for v in values)  # type: ignore[return-value]


def axis_words(direction) -> str:
    """"Z", "-X" or "(0.71, 0, 0.71)": the line a shake moves along."""
    for c, name in enumerate(_AXES):
        if abs(abs(direction[c]) - 1) < 1e-9:
            return name
    return "(" + ", ".join(f"{v:.2g}" for v in direction) + ")"


def _percent(share: float) -> str:
    return f"{share * 100:.0f}%"


def sweep_grid(low: float, high: float, modes_Hz, zeta: float, points: int = GRID_POINTS) -> "np.ndarray":
    """The frequencies (Hz) the response is evaluated at: log-spaced over the sweep, plus each mode's own
    frequency and points every ζ/2 around it (±3ζ), so no resonance falls between two points."""
    import numpy as np

    grid = [np.geomspace(low, high, points)]
    for f in modes_Hz:
        grid.append(f * (1.0 + 0.5 * zeta * np.arange(-6, 7)))
    out = np.unique(np.concatenate(grid))
    return out[(out >= low) & (out <= high)]


def choose_frames(grid: "np.ndarray", curve: "np.ndarray", frames: int, zeta: float,
                  peaks: int = PEAK_FRAMES) -> tuple[list[int], list[int]]:
    """(frame indices into ``grid`` ascending, the peaks among them): the curve's local maxima (the highest
    ``peaks``), then log-spaced frequencies over the sweep, at most ``frames`` in all. A log frame within
    3ζ of a peak is left out: it would show the same resonance."""
    import numpy as np

    frames = max(1, int(frames))
    n = len(grid)
    if n == 1:
        return [0], []
    local = [i for i in range(1, n - 1) if curve[i] >= curve[i - 1] and curve[i] > curve[i + 1]]
    local.sort(key=lambda i: -curve[i])
    chosen = local[:min(peaks, frames)]
    rest = frames - len(chosen)
    if rest > 0:
        targets = [grid[0]] if rest == 1 else np.geomspace(grid[0], grid[-1], rest)
        logs = np.log(grid)
        for target in targets:
            index = int(np.argmin(np.abs(logs - math.log(target))))
            if index in chosen or any(abs(grid[index] / grid[p] - 1) < 3 * zeta for p in local[:len(chosen)]):
                continue
            chosen.append(index)
    return sorted(set(chosen)), sorted(local[:min(peaks, frames)])


class HarmonicAnalysis:
    name: ClassVar[str] = "harmonic"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Shaking"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "excitation", "sweep_Hz", "damping_ratio"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    # Both per frame. The imaginary part of the displacement rides along as each frame's own attribute
    # (`_DISPLACEMENT_IM_F<i>`, frame field "displacement_im") for the viewer's Vibrate; it is no colour of its own.
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress (peak over the cycle)", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement (relative to the base)", "mm", 3, 1000.0, per_frame=True),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT, kinds.ACCELERATION)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress"},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "load_scale", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("reduce_modes", "iterative", "local_refine", "defeature", "linear_elements", "symmetry")
    noun: ClassVar[str] = "this shake"
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> HarmonicInputs:
        fixtures = parse_fixtures(document)
        raw = document.get("excitation")
        if not isinstance(raw, dict):
            raise ValueError('excitation: what shakes it, like {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1} '
                             '(shaken at its fixtures) or {"type": "force"} (its loads swinging)')
        kind = raw.get("type", "base")
        if kind not in ("base", "force"):
            raise ValueError(f"excitation.type: {kinds.json_text(kind)} is not one of \"base\" (shaken at its fixtures) "
                             "or \"force\" (its loads swinging)")
        loads: tuple[Load, ...] = ()
        direction: tuple[float, float, float] | None = None
        amplitude = 1.0
        if kind == "base":
            unknown = set(raw) - {"type", "direction", "amplitude_g"}
            if unknown:
                raise ValueError(f"excitation: unknown keys {sorted(unknown)}; a base shake takes type, direction and amplitude_g")
            if "direction" not in raw:
                raise ValueError("excitation.direction: the direction it is shaken along as [x, y, z], like [0, 0, 1] for Z")
            direction = _unit(raw["direction"], "excitation.direction")
            amplitude = kinds.number(raw.get("amplitude_g", 1.0), where="excitation.amplitude_g", positive=True)
            if "loads" in document:
                raise ValueError('loads: a base shake moves the fixtures, so it takes no loads; to shake it by its '
                                 'loads use "excitation": {"type": "force"}')
        else:
            unknown = set(raw) - {"type"}
            if unknown:
                raise ValueError(f"excitation: unknown keys {sorted(unknown)}; a force shake takes only type: "
                                 "the loads are its amplitudes")
            if "loads" not in document:
                raise ValueError('loads: a force shake needs the forces it swings with, as amplitudes, like '
                                 '[{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 10]}]')
            loads = parse_loads(document, body=False)
        sweep = document.get("sweep_Hz")
        if not isinstance(sweep, list) or len(sweep) != 2:
            raise ValueError("sweep_Hz: the frequencies to sweep as [low, high] in Hz, like [10, 2000]")
        low, high = (kinds.number(v, where="sweep_Hz", positive=True) for v in sweep)
        if not low < high:
            raise ValueError(f"sweep_Hz: low ({low:g}) must be below high ({high:g})")
        zeta = kinds.number(document.get("damping_ratio", 0.02), where="damping_ratio", positive=True)
        if zeta >= 1:
            raise ValueError(f"damping_ratio: a share of critical damping, like 0.02 for 2 %; must be under 1, got {zeta:g}")
        refs = tuple(dict.fromkeys(ref for group in (*fixtures, *loads) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        return HarmonicInputs(refs, anchors, True, fixtures=fixtures, loads=loads, excitation=kind, direction=direction,
                              amplitude_g=amplitude, sweep_Hz=(low, high), damping_ratio=zeta)

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: HarmonicInputs):
        """Finding the modes (:func:`modal.eigen_estimate`), then per kept mode its stress (six components per
        node) and shape, the frequency grid's combinations and the frames written."""
        from cadgen._internal.fea import fit

        plan = getattr(ctx, "plan", None)
        modes = int(getattr(plan, "modes", None) or GUESS_MODES)
        base = eigen_estimate(ctx, modes)
        nodes = base.dofs / 3.0
        frames = max_frames(ctx)
        grid = GRID_POINTS + 13 * modes
        memory = base.memory_bytes + 8.0 * 9 * nodes * modes + 4.0 * 7 * nodes * frames + 16.0 * 16 * 3 * nodes
        seconds = base.seconds + modes * fit.SECONDS_PER_ELEMENT.get(getattr(plan, "order", 2), 2.5e-4) * nodes / 1.7 \
            + 2e-9 * grid * modes * 3 * nodes + 2e-8 * frames * 6 * 12 * nodes
        return fit.Estimate(dofs=base.dofs, memory_bytes=int(memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: HarmonicInputs):
        """``reduce_modes``: keep only the fewest modes holding 90 % of the mass moving along the shake (its words
        give the share once the modes are found). ``iterative``: LOBPCG instead of factorising. The mesh rungs the
        shared way; ``symmetry`` and ``idealise`` are not taken for a modal response yet."""
        from cadgen._internal.fea import fit

        if rung == "reduce_modes":
            plan = ctx.plan
            if plan.modes is not None and plan.modes <= REDUCED_GUESS:
                return None
            plan.modes = REDUCED_GUESS
            along = f" along {axis_words(inputs.direction)}" if inputs.direction is not None else ""
            step = fit.Step("reduce_modes", f"Kept only the fewest modes holding {_percent(KEEP_SHARE)} of the mass moving"
                            f"{along}, to fit", None, None, detail={"keep_share": KEEP_SHARE})
            # The solve finds the modes, then says how many it kept and the share they hold (_settle_reduce_step).
            plan._harmonic_reduce_step = step
            return step
        return apply_eigen_rung(self, rung, ctx, inputs, words="Found the modes with an iterative solver (LOBPCG with "
                                "multigrid) instead of factorising the stiffness")

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """local_refine keeps the mesh fine where the sweep stresses the part most; two passes compare that peak."""
        envelope = result.scalars["stress_envelope"]
        return envelope, float(envelope.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: HarmonicInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea import superposition as sp

        space = ctx.space
        plan = getattr(ctx, "plan", None)
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        materials = materials_of(ctx)
        K = operators.stiffness(space, materials)
        M = operators.mass(space, materials)
        fixed = fixed_dofs(space, inputs.fixtures, ctx.ordinal_of)
        low, high = inputs.sweep_Hz
        zeta = inputs.damping_ratio
        base = inputs.excitation == "base"
        if base:
            accel = inputs.amplitude_g * G0_MM_S2
            direction = np.asarray(inputs.direction, dtype=float)
            force = None
        else:
            accel = 0.0
            force = sp.load_vector(space, inputs.loads, ctx.ordinal_of)
            resultant = np.array([force[space.component == c].sum() for c in range(3)])
            size = float(np.linalg.norm(resultant))
            scale = float(np.abs(force).sum())
            direction = resultant / size if size > 1e-9 * max(scale, 1e-300) else None
        r = None if direction is None else sp.rigid_translation(space.component, direction)
        Mr = None if r is None else M @ r
        total_along = 0.0 if r is None else float(r @ Mr)
        timings["assemble_s"] = time.perf_counter() - started

        reduce = "reduce_modes" in (getattr(plan, "taken", None) or ())
        enough = None
        if reduce and Mr is not None:
            def enough(omega2, vectors, free):
                share = float(((vectors.T @ Mr[free]) ** 2).sum()) / total_along
                return share >= KEEP_SHARE

        started = time.perf_counter()
        free_count = space.dofs - len(fixed)
        method = solver_method(ctx, free_count)
        found = sp.find_modes(K, M, fixed, inputs.top_Hz, method=method, locations=space.locations,
                              component=space.component, enough=enough)
        warnings.extend(found.warnings)
        frequencies = found.frequencies_Hz
        found.vectors = align_degenerate(found.vectors, M, frequencies, space.component)
        timings["eigen_s"] = time.perf_counter() - started
        if ctx.log:
            ctx.log(f"harmonic: {len(found)} modes up to {frequencies[-1]:.4g} Hz ({found.how})")

        fractions = sp.mass_fractions(found, M, space.component)
        if base:
            gamma = sp.participation(found, M, r)
            weights, total = gamma ** 2, total_along
        else:
            p = sp.modal_loads(found, force)
            # Each mode's share of the static response's work (p²/ω²): what keeps a force shake's answer.
            weights = p ** 2 / np.maximum(found.omega ** 2, 1e-300)
            total = float(weights.sum())
        along_share = None
        if r is not None:
            masses = (sp.participation(found, M, r) ** 2)
            along_share = float(masses.sum() / total_along) if total_along > 0 else None
        kept = np.arange(len(found))
        kept_share = None
        if reduce:
            if base or r is None:
                kept, kept_share = sp.fewest_modes(weights, total, KEEP_SHARE)
            else:
                kept, kept_share = sp.fewest_modes(sp.participation(found, M, r) ** 2, total_along, KEEP_SHARE)
            self._settle_reduce_step(plan, inputs, found, kept, kept_share, base or r is not None)
        used = found.take(kept)

        started = time.perf_counter()
        shapes = sp.nodal_shapes(space, used)
        stresses = sp.modal_stresses(space, materials, used)
        timings["stress_s"] = time.perf_counter() - started

        started = time.perf_counter()
        grid = sweep_grid(low, high, [f for f in used.frequencies_Hz if low <= f <= high], zeta)
        omega = _TWO_PI * grid
        if base:
            coordinates = (lambda w: sp.base_coordinates(used.omega, gamma[kept], w, zeta, accel))
            base_vector = accel * direction
        else:
            coordinates = (lambda w: sp.force_coordinates(used.omega, p[kept], w, zeta))
            base_vector = None
        Q = coordinates(omega)
        curve_disp, curve_acc = sp.response_maxima(shapes, Q, omega, base=base_vector)
        indices, peaks = choose_frames(grid, curve_disp, max_frames(ctx), zeta)
        frame_Hz = [float(grid[i]) for i in indices]
        re, im, vm, disp_peak, acc_peak = [], [], [], [], []
        for i in indices:
            q = Q[i]
            U = sp.combine(shapes, q)
            re.append(U.real.copy())
            im.append(U.imag.copy())
            disp_peak.append(sp.vector_peak(U))
            A = -(omega[i] ** 2) * U
            if base_vector is not None:
                A = A + base_vector[None, :]
            acc_peak.append(sp.vector_peak(A) / G0_MM_S2)
            vm.append(sp.von_mises_peak(sp.combine(stresses, q)))
        timings["sweep_s"] = time.perf_counter() - started
        stress_max = [float(v.max()) for v in vm]
        default = int(np.argmax(stress_max)) if any(stress_max) else int(np.argmax([float(d.max()) for d in disp_peak]))

        series = Series(kind="frequency", unit="Hz", default=default, frames=[
            SeriesFrame(value=round(f, 6), label=hz_text(f), attributes={
                "von_mises": "_VON_MISES" if n == 0 else f"_VON_MISES_F{n}",
                "displacement": "_DISPLACEMENT" if n == 0 else f"_DISPLACEMENT_F{n}",
                "displacement_im": f"_DISPLACEMENT_IM_F{n}",
            })
            for n, f in enumerate(frame_Hz)
        ])
        in_sweep = [i for i, f in enumerate(found.frequencies_Hz) if low <= f <= high]
        return AnalysisResult(
            dof_locations=space.dof_locations,
            vertices=space.vertices,
            tets=space.tets,
            boundary_quadratic=space.boundary_quadratic,
            element_dofs=space.element_dofs,
            # Frame 0 is the fields' own attribute (the sweep's bottom); the viewer opens on the series' default, the peak.
            fields={"von_mises": vm[0], "displacement": re[0]},
            deformation=re[0],
            series=series,
            frame_fields={"von_mises": vm, "displacement": re, "displacement_im": im},
            curves={
                "max_displacement_mm": {"x": [round(float(f), 6) for f in grid], "x_unit": "Hz",
                                        "y": [round(float(v), 9) for v in curve_disp], "y_unit": "mm"},
                "max_acceleration_g": {"x": [round(float(f), 6) for f in grid], "x_unit": "Hz",
                                       "y": [round(float(v) / G0_MM_S2, 6) for v in curve_acc], "y_unit": "g"},
            },
            scalars={
                "frequencies_Hz": [float(f) for f in found.frequencies_Hz],
                "effective_mass_fractions": fractions.tolist(),
                "used_modes": [int(i) for i in kept],
                "modes_in_sweep": in_sweep,
                "kept_share": kept_share,
                "along_share": along_share,
                "direction": None if direction is None else [float(c) for c in direction],
                "searched_Hz": found.searched_Hz,
                "complete": found.complete,
                "total_mass_kg": float(sum((M @ (space.component == 0).astype(float)))) * 1000.0,
                "frame_Hz": frame_Hz,
                "peak_frames": [indices.index(i) for i in peaks],
                "stress_frames": vm,
                "displacement_frames": disp_peak,
                "acceleration_frames": acc_peak,
                "stress_envelope": np.max(np.stack(vm), axis=0),
                "applied_N": None if force is None else [float(force[space.component == c].sum()) for c in range(3)],
                "analysis_warnings": [],
                "study_checks": tuple(getattr(ctx.study, "checks", ()) or ()),
                "margin": float(getattr(ctx.study, "margin", 2.0) or 2.0),
                "parts": None if ctx.assembly is None else [
                    {"ref": part.ref, "name": name, "material": material.name}
                    for part, name, material in zip(ctx.assembly.parts, ctx.assembly.names, ctx.assembly.materials)
                ],
                "yields": [m.yield_strength for m in ctx.materials],
                "node_domain": _node_domain(space),
            },
            dofs=int(space.dofs),
            solver=f"{found.how}; modal superposition of {len(used)} mode{'s' if len(used) != 1 else ''}",
            timings=timings,
            warnings=warnings,
        )

    @staticmethod
    def _settle_reduce_step(plan, inputs: HarmonicInputs, found, kept, share: float | None, by_mass: bool) -> None:
        """reduce_modes' step says the share it kept once the modes are found: its words are written now.

        The step is the one the ladder recorded (``FitPlan``'s steps are frozen dataclasses run.py writes as
        they are), so its words are set in place."""
        from cadgen._internal.fea import fit

        step = getattr(plan, "_harmonic_reduce_step", None)
        if step is None or not isinstance(step, fit.Step):
            return
        along = f" moving along {axis_words(inputs.direction)}" if inputs.direction is not None else " moving with the shake"
        what = f"of the mass{along}" if by_mass else "of the response to the forces"
        count = len(kept)
        words = (f"Kept {count} of the {len(found)} modes up to {hz_text(found.searched_Hz)}, the ones holding "
                 f"{_percent(share or 0.0)} {what}, to fit")
        object.__setattr__(step, "words", words)
        step.detail.update({"kept_modes": count, "found_modes": len(found), "kept_share": round(share or 0.0, 4)})

    # -- checks, findings ----------------------------------------------------------------------------

    def _stress_peak(self, result: AnalysisResult) -> tuple[int, int, float]:
        """(frame, node, MPa) of the highest von Mises over the sweep's frames."""
        frames = result.scalars["stress_frames"]
        frame = max(range(len(frames)), key=lambda i: float(frames[i].max()))
        node = int(frames[frame].argmax())
        return frame, node, float(frames[frame][node])

    def _yield_at(self, result: AnalysisResult, node: int) -> float:
        domains = result.scalars["node_domain"]
        yields = result.scalars["yields"]
        if domains is None or len(yields) == 1:
            return yields[0]
        return yields[int(domains[node])]

    def needs_finer(self, result: AnalysisResult, inputs: HarmonicInputs, check_results: list[dict]) -> bool:
        """Solve once more finer when the stress check is close: the peak between yield over the margin and yield."""
        if check_results:
            return any(check["status"] == "close" for check in check_results)
        if not any(check.get("kind") == "stress" for check in result.scalars["study_checks"]):
            return False
        _, node, peak = self._stress_peak(result)
        ratio = peak / self._yield_at(result, node)
        return 1.0 / result.scalars["margin"] < ratio <= 1.0

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_MPa": round(self._stress_peak(result)[2], 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_von_mises_MPa"] = round(self._stress_peak(finer)[2], 4)
        finer.scalars["coarser_peak_MPa"] = self._stress_peak(coarse)[2]
        return finer

    def _at(self, result: AnalysisResult, frame: int) -> dict:
        f = result.scalars["frame_Hz"][frame]
        return {"frame": frame, "value": round(f, 4), "unit": "Hz"}

    def _over_frames(self, ctx: SolveContext, result: AnalysisResult, frames, check: dict, index: int):
        """(frame, kinds.FieldMax) of the largest of a per-frame nodal field over the check's faces."""
        best = None
        for frame, values in enumerate(frames):
            peak = kinds.field_max_over(
                values, tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
                boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
                ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
            )
            if best is None or peak.value > best[1].value:
                best = (frame, peak)
        return best

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: HarmonicInputs) -> dict:
        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import _peak_face

        kind = check["kind"]
        if kind == "stress":
            frame, node, peak = self._stress_peak(result)
            fixed = {ctx.ordinal_of[ref] for fixture in inputs.fixtures for ref in fixture.faces}
            at = tuple(float(c) for c in result.dof_locations[node])
            solved = checks.Solved(
                material_name="", yield_MPa=self._yield_at(result, node), peak_MPa=peak, peak_gauss_MPa=peak, peak_at=at,
                peak_face=_peak_face(ctx.volume, result, node, fixed), fixed_faces=(), max_displacement_mm=0.0,
                displacement_at=at, bbox_diagonal_mm=0.0, margin=result.scalars["margin"], coarser_peak_MPa=None, part="",
            )
            return {**checks.stress_check(solved, label=check.get("label")), "at": self._at(result, frame)}
        if kind == "displacement":
            frame, peak = self._over_frames(ctx, result, result.scalars["displacement_frames"], check, index)
            judged = checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces,
                                               label=check.get("label"))
            return {**judged, "at": self._at(result, frame)}
        frame, peak = self._over_frames(ctx, result, result.scalars["acceleration_frames"], check, index)
        ratio = peak.value / check["limit_g"]
        judged = {
            "kind": "acceleration", "label": check.get("label") or kinds.ACCELERATION.default_label,
            "value": round(peak.value, 4), "limit": check["limit_g"], "unit": "g", "ratio": round(ratio, 6),
            "close_at": _CLOSE_AT, "status": checks.check_status(ratio, _CLOSE_AT),
            "where": {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]},
        }
        if peak.faces and check.get("faces"):
            judged["faces"] = list(peak.faces)
        judged["at"] = self._at(result, frame)
        return judged

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: HarmonicInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.modal import finding

        scalars = result.scalars
        whole = "The assembly" if assembly else "The part"
        found: list[dict] = []
        for check in check_results:
            status = check["status"]
            if status not in ("fails", "close"):
                continue
            hz = hz_text(check["at"]["value"])
            severity = "error" if status == "fails" else "warning"
            item = [{"text": check["label"], **check["where"]}]
            if check["kind"] == "stress":
                if status == "fails":
                    sentence = (f"Shaken at {hz}, {whole.lower()} reaches {check['value']:.3g} MPa, over its "
                                f"{check['limit']:g} MPa yield ({check['label']})")
                else:
                    sentence = (f"Shaken at {hz}, {whole.lower()} reaches {check['value']:.3g} MPa, inside the "
                                f"{check['margin']:g}× margin under its {check['limit']:g} MPa yield ({check['label']})")
                found.append(finding(severity, "shaking_yields" if status == "fails" else "shaking_close_to_yield", sentence,
                                     f"peak von Mises over the cycle {check['value']:.4g} MPa at {check['at']['value']:.4g} Hz",
                                     item))
            elif check["kind"] == "acceleration":
                where = "The checked faces shake" if check.get("faces") else f"{whole} shakes"
                if status == "fails":
                    sentence = f"{where} at {check['value']:.3g} g at {hz}, more than the {check['limit']:g} g allowed ({check['label']})"
                else:
                    sentence = f"{where} at {check['value']:.3g} g at {hz}, close to the {check['limit']:g} g allowed ({check['label']})"
                found.append(finding(severity, "acceleration_over_limit" if status == "fails" else "acceleration_close",
                                     sentence, f"peak acceleration {check['value']:.4g} g against a {check['limit']:g} g limit",
                                     item))
            elif check["kind"] == "displacement" and status == "close":
                found.append(finding("warning", "displacement_close",
                                     f"Shaken at {hz}, it moves {check['value']:.3g} mm, close to the {check['limit']:g} mm allowed "
                                     f"({check['label']})", "the displacement is relative to where it is held", item))
        frequencies = scalars["frequencies_Hz"]
        low, high = inputs.sweep_Hz
        in_sweep = scalars["modes_in_sweep"]
        if in_sweep:
            frame = result.series.default
            f = scalars["frame_Hz"][frame]
            mode = min(in_sweep, key=lambda i: abs(frequencies[i] - f)) + 1
            displacement = scalars["displacement_frames"][frame]
            node = int(displacement.argmax())
            g = float(scalars["acceleration_frames"][frame].max())
            found.append(finding(
                "info", "resonance",
                f"Resonates at {hz_text(f)} (mode {mode}): it moves up to {float(displacement.max()):.3g} mm there and "
                f"shakes at up to {g:.3g} g",
                "the frequency in the sweep where the response peaks; a shake there is the worst case",
                [{"text": "moves most here", "ref": None, "at": [round(float(c), 3) for c in result.dof_locations[node]]}],
            ))
        else:
            found.append(finding(
                "info", "no_resonance_in_sweep",
                f"No natural frequency lies between {low:g} and {high:g} Hz: {whole.lower()} follows the shake without resonating"
                + (f"; its first mode is {hz_text(frequencies[0])}" if frequencies else ""),
                "the response stays near its static value across the sweep", [],
            ))
        share = scalars["along_share"]
        if share is not None and share < MASS_WARNING:
            along = axis_words(scalars["direction"])
            found.append(finding(
                "warning", "modes_missing_mass",
                f"The modes up to {hz_text(scalars['searched_Hz'])} move only {_percent(share)} of the mass along {along}: "
                f"the rest answers above them, so the response may read a little low",
                f"effective mass of the modes found {share:.3f} of the total along {along}; "
                "a fixed face's own mass never moves, and modes above 1.5× the sweep's top are left out", [],
            ))
        coarser = scalars.get("coarser_peak_MPa")
        if coarser:
            _, _, peak = self._stress_peak(result)
            moved = abs(peak - coarser) / coarser if coarser > 0 else 0.0
            found.append(finding(
                "warning" if moved > 0.1 else "info", "mesh_not_converged" if moved > 0.1 else "mesh_converged",
                f"The peak stress moved {moved * 100:.1f} % on a finer mesh ({coarser:.3g} to {peak:.3g} MPa)",
                "a check was close, so the part was solved again finer; the finer answer is the one reported", [],
            ))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        from cadgen._internal.fea.outputs import auto_deformation_scale

        largest = max(float(d.max()) for d in result.scalars["displacement_frames"])
        return requested or auto_deformation_scale(largest, bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: HarmonicInputs, check_results: list[dict]) -> dict:
        scalars = result.scalars
        frame_Hz = scalars["frame_Hz"]
        s_frame, s_node, s_peak = self._stress_peak(result)
        disp = scalars["displacement_frames"]
        d_frame = max(range(len(disp)), key=lambda i: float(disp[i].max()))
        d_node = int(disp[d_frame].argmax())
        acc = scalars["acceleration_frames"]
        a_frame = max(range(len(acc)), key=lambda i: float(acc[i].max()))
        yield_MPa = self._yield_at(result, s_node)
        factor = yield_MPa / s_peak if s_peak > 0 else None
        used = set(scalars["used_modes"])
        direction = scalars["direction"]
        axis = None if direction is None else max(range(3), key=lambda c: abs(direction[c]))
        excitation: dict[str, Any] = {"type": inputs.excitation}
        if inputs.excitation == "base":
            excitation.update({"direction": list(inputs.direction), "amplitude_g": inputs.amplitude_g})
        else:
            excitation["applied_N"] = [round(x, 4) for x in scalars["applied_N"]]
        summary: dict[str, Any] = {
            "excitation": excitation,
            "sweep_Hz": list(inputs.sweep_Hz),
            "damping_ratio": inputs.damping_ratio,
            "peak_Hz": round(frame_Hz[result.series.default], 4),
            "max_von_mises_MPa": round(s_peak, 4),
            "max_von_mises_Hz": round(frame_Hz[s_frame], 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[s_node]],
            "yield_MPa": yield_MPa,
            "safety_factor": None if factor is None else math.floor(factor * 1000) / 1000,
            "max_displacement_mm": round(float(disp[d_frame].max()), 6),
            "max_displacement_Hz": round(frame_Hz[d_frame], 4),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[d_node]],
            "max_acceleration_g": round(float(acc[a_frame].max()), 4),
            "max_acceleration_Hz": round(frame_Hz[a_frame], 4),
            "modes": [
                {"mode": i + 1, "frequency_Hz": round(f, 4), "effective_mass_fraction": [round(x, 4) for x in share],
                 "used": i in used}
                for i, (f, share) in enumerate(zip(scalars["frequencies_Hz"], scalars["effective_mass_fractions"]))
            ],
            "modes_used": len(used),
            "modes_up_to_Hz": round(inputs.top_Hz, 4),
            "effective_mass_fraction": None if scalars["along_share"] is None else round(scalars["along_share"], 4),
            "effective_mass_axis": None if axis is None else _AXES[axis],
            "total_mass_kg": round(scalars["total_mass_kg"], 6),
            "frames": len(frame_Hz),
            "deformation_scale": scalars["deformation_scale"],
        }
        if scalars["kept_share"] is not None:
            summary["kept_share"] = round(scalars["kept_share"], 4)
        if scalars.get("parts"):
            summary["parts"] = scalars["parts"]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} shaking"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        # Per-frame fields: one range across every frame, so the colours compare along the sweep.
        return {"von_mises": (0.0, summary["max_von_mises_MPa"]), "displacement": (0.0, summary["max_displacement_mm"])}

    def extras_head(self, summary: dict) -> dict:
        return {"peak_Hz": summary["peak_Hz"], "safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: HarmonicInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        excitation: dict[str, Any] = {"type": inputs.excitation}
        if inputs.excitation == "base":
            excitation.update({"direction": list(inputs.direction), "amplitude_g": inputs.amplitude_g})
        return {
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "loads": [{"type": load.type, "faces": bare(load.faces),
                       **({"vector_N": [float(c) for c in load.vector]} if load.type == "force" else {"pressure_MPa": load.pressure})}
                      for load in inputs.loads],
            "excitation": excitation,
            "sweep_Hz": list(inputs.sweep_Hz),
            "damping_ratio": inputs.damping_ratio,
        }

    def human_lines(self, summary: dict) -> list[str]:
        excitation = summary["excitation"]
        low, high = summary["sweep_Hz"]
        if excitation["type"] == "base":
            shaken = f"shaken {excitation['amplitude_g']:g} g along {axis_words(excitation['direction'])}"
        else:
            shaken = "pushed by its loads"
        lines = [
            f"{shaken} from {low:g} to {high:g} Hz, {summary['damping_ratio'] * 100:g}% damping; "
            f"strongest at {hz_text(summary['peak_Hz'])}",
            f"peak stress {summary['max_von_mises_MPa']:.4g} MPa at {hz_text(summary['max_von_mises_Hz'])}; moves up to "
            f"{summary['max_displacement_mm']:.4g} mm and shakes up to {summary['max_acceleration_g']:.4g} g",
        ]
        modes = f"{summary['modes_used']} mode{'s' if summary['modes_used'] != 1 else ''} up to {hz_text(summary['modes_up_to_Hz'])}"
        if summary.get("effective_mass_fraction") is not None:
            modes += f", holding {summary['effective_mass_fraction'] * 100:.0f}% of the mass along {summary['effective_mass_axis']}"
        lines.append(modes)
        return lines


def _node_domain(space) -> "np.ndarray | None":
    """Each node's part (the domain of an element it belongs to), for an assembly; None for one part."""
    import numpy as np

    if space.domain is None:
        return None
    out = np.zeros(space.scalar_count, dtype=np.int64)
    out[space.scalar.element_dofs] = np.asarray(space.domain)[None, :]
    return out
