"""Over time: a held part's response to loads that change in time, a hammer blow or a sudden push. Tier 1.

The study (spec 5.11) holds the part at its ``fixtures`` and loads it with
``loads`` (forces and pressures on faces), each with a ``history``: how its
size changes over time, as a table ``[[t_s, factor], ...]`` (straight lines
between the points, the ends held) or a shape ``{"shape": "step" | "ramp" |
"half_sine", "duration_s": ...}``. It may also, or instead, be shaken at its
fixtures (``excitation``: a base acceleration along ``direction`` of
``amplitude_g``, with its own ``history``). The response is followed from rest
for ``end_s``, at ``step_s`` (or ``"auto"``), with damping ratio
``damping_ratio`` (default 0.02), by one of two methods:

- ``modal`` (the default): the part's modes up to 3 × the highest frequency in
  the loads (:func:`History.content_Hz`), each integrated exactly for a load
  that is linear between the time points (:func:`timestep.modal_march`), plus
  the steady share of every mode left out (the static correction: each load's
  static answer less what the kept modes carry of it), so a slow load is exact
  and a fast one misses only the ringing of modes far above its frequencies;
- ``direct``: the whole model stepped through time by Newmark's average
  acceleration (:func:`timestep.newmark`), with Rayleigh damping fitted to the
  damping ratio at modes 1 and 2.

A step under the auto rule keeps at least 40 steps per period of mode 1 and 20
per period of the fastest load. What it writes: a series of time frames (up to
``Budget.max_frames``, evenly spaced from 0 to the end plus the moments of the
peak stress and the peak displacement), each with the displacement (relative to
the fixtures when shaken) and von Mises; the envelopes of both over all time
(``von_mises_peak``, ``displacement_peak``); a curve of the largest
displacement against time; and the ``stress`` and ``displacement`` checks
judged on the peaks, each saying when (``at``). The summary also gives the
steady (static) displacement under the loads at their peak and the ratio of the
peak to it: a suddenly applied load on an undamped part moves twice as far.

The ladder: ``reduce_modes`` switches ``direct`` to ``modal`` (and says so), or
keeps the fewest modes holding 90 % of the response; ``adaptive_steps`` lets
Newmark's step grow while its local error stays small; the mesh rungs are the
shared ones. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Inputs, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.modal import (
    align_degenerate, eigen_estimate, fixed_dofs, hz_text, materials_of, max_frames, solver_method,
)
from cadgen._internal.fea.analyses.thermal_transient import time_label
from cadgen._internal.fea.study import Fixture, Load, parse_fixtures, parse_loads

if TYPE_CHECKING:
    import numpy as np

__all__ = ["Excitation", "History", "TransientAnalysis", "TransientInputs", "parse_time_history", "time_grid"]

G0_MM_S2 = 9806.65
SHAPES = ("step", "ramp", "half_sine")
METHODS = ("modal", "direct")
#: Modes are found up to this multiple of the loads' highest frequency (spec 5.11).
TOP_FACTOR = 3.0
#: ``step_s: "auto"``: at most this share of the run per step ...
AUTO_STEPS = 400
#: ... at least this many steps per period of the fastest load ...
STEPS_PER_LOAD_PERIOD = 20
#: ... and per period of mode 1.
STEPS_PER_PERIOD = 40
#: The auto rule never takes more steps than this.
MAX_AUTO_STEPS = 20_000
#: A load that jumps has every frequency: the modes followed are those of 1 / (this × the step).
JUMP_STEPS = 20
#: reduce_modes keeps the fewest modes holding this share of the response.
KEEP_SHARE = 0.9
#: The modes the ladder assumes before the solve has found them, and after reduce_modes.
GUESS_MODES = 20
REDUCED_GUESS = 6
#: Stress is evaluated at every step while that costs under this many multiply-adds, else at a stride.
STRESS_WORK = 2e10
#: A check is close at 90 % of its limit.
_CLOSE_AT = 0.9
_TWO_PI = 2.0 * math.pi
_AXES = "XYZ"


# -- histories ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class History:
    """How a load's size changes over time: a factor on it, against time in seconds."""

    #: "table", "step", "ramp" or "half_sine".
    shape: str
    #: A ramp's rise or a half-sine's length, s.
    duration_s: float | None = None
    #: A table's points (t_s, factor), times rising; straight lines between them, the ends held.
    points: tuple[tuple[float, float], ...] = ()

    def values(self, t) -> "np.ndarray":
        """The factor at each time of ``t`` (an array, or one time)."""
        import numpy as np

        t = np.asarray(t, dtype=float)
        if self.shape == "step":
            return np.where(t >= 0, 1.0, 0.0)
        if self.shape == "ramp":
            return np.clip(t / self.duration_s, 0.0, 1.0)
        if self.shape == "half_sine":
            return np.where((t >= 0) & (t <= self.duration_s), np.sin(math.pi * np.clip(t, 0, self.duration_s) / self.duration_s), 0.0)
        times = [p[0] for p in self.points]
        factors = [p[1] for p in self.points]
        return np.interp(t, times, factors)

    def value(self, t: float) -> float:
        return float(self.values(t))

    @property
    def corners(self) -> tuple[float, ...]:
        """Times where the factor turns a corner: a step lands on each, so a table or a ramp is followed exactly."""
        if self.shape in ("ramp", "half_sine"):
            return (float(self.duration_s),)
        if self.shape == "table":
            return tuple(p[0] for p in self.points)
        return ()

    @property
    def peak(self) -> float:
        """The largest size of the factor over all time."""
        if self.shape == "table":
            return max(abs(p[1]) for p in self.points)
        return 1.0

    def content_Hz(self, jump_Hz: float) -> float:
        """The highest frequency the load carries: 1 / the rise of a ramp, the length of a half-sine or a table's
        quickest change; a jump (a step) carries every frequency and is followed up to ``jump_Hz``."""
        if self.shape == "step":
            return jump_Hz
        if self.shape in ("ramp", "half_sine"):
            return min(1.0 / self.duration_s, jump_Hz)
        fastest = 0.0
        for (t0, f0), (t1, f1) in zip(self.points, self.points[1:]):
            if f1 != f0:
                fastest = max(fastest, 1.0 / (t1 - t0))
        # A table that starts at a non-zero factor after rest is a jump at t = 0.
        if self.points[0][1] != 0.0:
            fastest = jump_Hz
        return min(fastest, jump_Hz)

    def echo(self):
        if self.shape == "table":
            return [[t, f] for t, f in self.points]
        return {"shape": self.shape, **({} if self.duration_s is None else {"duration_s": self.duration_s})}

    def words(self) -> str:
        """"step", "ramp over 2 ms", "half-sine, 2 ms", "table of 4 points to 10 ms"."""
        if self.shape == "step":
            return "step"
        if self.shape == "ramp":
            return f"ramp over {time_label(self.duration_s)}"
        if self.shape == "half_sine":
            return f"half-sine, {time_label(self.duration_s)}"
        return f"table of {len(self.points)} point{'s' if len(self.points) != 1 else ''} to {time_label(self.points[-1][0])}"


def parse_time_history(raw: Any, where: str) -> History:
    """A ``history``: ``[[t_s, factor], ...]`` (times rising from 0 or later) or ``{"shape", "duration_s"}``."""
    words = ('how the load changes over time, as [[t_s, factor], ...] like [[0, 0], [0.001, 1], [0.002, 0]], '
             'or {"shape": "step" | "ramp" | "half_sine", "duration_s": 0.002}')
    if raw is None:
        raise ValueError(f"{where}: {words}")
    if isinstance(raw, dict):
        unknown = set(raw) - {"shape", "duration_s"}
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a shaped history takes shape and duration_s")
        shape = raw.get("shape")
        if shape not in SHAPES:
            raise ValueError(f"{where}.shape: {kinds.json_text(shape)} is not one of \"step\" (on at once and held), "
                             "\"ramp\" (rising to full over duration_s, then held) or \"half_sine\" (a pulse duration_s long)")
        if shape == "step":
            if "duration_s" in raw:
                raise ValueError(f"{where}.duration_s: a step is on at once and stays on; it takes no duration")
            return History("step")
        if "duration_s" not in raw:
            raise ValueError(f"{where}.duration_s: how long the {'rise' if shape == 'ramp' else 'pulse'} lasts, in seconds, "
                             "like 0.002 for 2 ms")
        return History(shape, kinds.number(raw["duration_s"], where=f"{where}.duration_s", positive=True))
    if not isinstance(raw, list) or not raw or not all(isinstance(point, list) and len(point) == 2 for point in raw):
        raise ValueError(f"{where}: {words}")
    points: list[tuple[float, float]] = []
    for index, (t, factor) in enumerate(raw):
        t = kinds.number(t, where=f"{where}[{index}][0]")
        factor = kinds.number(factor, where=f"{where}[{index}][1]")
        if t < 0:
            raise ValueError(f"{where}[{index}]: times start at 0 s, got {t:g}")
        if points and not t > points[-1][0]:
            raise ValueError(f"{where}[{index}]: times must rise; {t:g} s is not after {points[-1][0]:g} s")
        points.append((t, factor))
    if not any(f for _, f in points):
        raise ValueError(f"{where}: every factor is zero, so the load never acts")
    return History("table", None, tuple(points))


def time_grid(end_s: float, step_s: float, corners: Sequence[float]) -> "np.ndarray":
    """The times the response is computed at: every ``step_s`` from 0 to ``end_s``, plus each load's corners."""
    import numpy as np

    count = max(1, int(math.ceil(end_s / step_s - 1e-9)))
    times = np.concatenate([np.linspace(0.0, step_s * count, count + 1), [c for c in corners if 0 < c < end_s]])
    times = np.unique(np.clip(times, 0.0, end_s))
    keep = np.concatenate([[True], np.diff(times) > 1e-9 * step_s])
    return times[keep]


# -- the study ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Excitation:
    """The fixtures shaken together along ``direction`` (a unit vector) at ``amplitude_g`` times ``history``."""

    direction: tuple[float, float, float]
    amplitude_g: float
    history: History


@dataclass(frozen=True)
class TransientInputs(Inputs):
    fixtures: tuple[Fixture, ...] = ()
    loads: tuple[Load, ...] = ()
    #: One per load, in order.
    histories: tuple[History, ...] = ()
    excitation: Excitation | None = None
    end_s: float = 0.0
    #: The step in s; ``None`` for "auto".
    step_s: float | None = None
    damping_ratio: float = 0.02
    method: str = "modal"
    #: Internal (drop's dynamic check): run at least this many periods of mode 1 past the last load corner.
    settle_periods: float = 0.0

    @property
    def histories_all(self) -> tuple[History, ...]:
        return self.histories + ((self.excitation.history,) if self.excitation is not None else ())

    def first_step(self) -> float:
        """The step before the modes are known: the study's, or a 400th of the run and a 20th of the fastest load's period."""
        if self.step_s is not None:
            return self.step_s
        step = self.end_s / AUTO_STEPS
        finite = [h.content_Hz(math.inf) for h in self.histories_all if h.shape != "step"]
        finite = [f for f in finite if 0 < f < math.inf]
        if finite:
            step = min(step, 1.0 / (STEPS_PER_LOAD_PERIOD * max(finite)))
        return max(step, self.end_s / MAX_AUTO_STEPS)

    def content_Hz(self) -> float:
        """The highest frequency in the loads (a jump counts as 1 / (20 × the first step))."""
        jump = 1.0 / (JUMP_STEPS * self.first_step())
        return max(h.content_Hz(jump) for h in self.histories_all)

    @property
    def top_Hz(self) -> float:
        return TOP_FACTOR * self.content_Hz()


def _unit(vector, where: str) -> tuple[float, float, float]:
    if not isinstance(vector, list) or len(vector) != 3:
        raise ValueError(f"{where}: the direction it is shaken along as [x, y, z], like [0, 0, 1] for Z")
    values = [kinds.number(v, where=where) for v in vector]
    size = math.sqrt(sum(v * v for v in values))
    if size == 0:
        raise ValueError(f"{where}: the direction is zero; give the axis it is shaken along, like [0, 0, 1]")
    return tuple(v / size for v in values)  # type: ignore[return-value]


def axis_words(direction) -> str:
    for c, name in enumerate(_AXES):
        if abs(abs(direction[c]) - 1) < 1e-9:
            return name
    return "(" + ", ".join(f"{v:.2g}" for v in direction) + ")"


def _figure(value: float) -> str:
    return f"{value:.3g}" if abs(value) < 1000 else f"{value:.0f}"


def load_words(load: Load, history: History) -> str:
    """"50 N half-sine, 2 ms", "2 MPa pressure step"."""
    if load.type == "force":
        size = f"{_figure(math.sqrt(sum(c * c for c in load.vector)))} N"
    else:
        size = f"{_figure(load.pressure)} MPa pressure"
    return f"{size} {history.words()}"


class TransientAnalysis:
    name: ClassVar[str] = "transient"
    tier: ClassVar[int] = 1
    word: ClassVar[str] = "Over time"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = ()
    study_keys: ClassVar[frozenset[str]] = frozenset(
        {"fixtures", "loads", "excitation", "end_s", "step_s", "damping_ratio", "method"})
    material_needs: ClassVar[frozenset[str]] = frozenset({"density"})
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("von_mises_peak", "_VON_MISES_PEAK", "von Mises stress (peak over time)", "MPa"),
        FieldSpec("displacement_peak", "_DISPLACEMENT_PEAK", "displacement (largest over time)", "mm"),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress"},)
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "load_scale", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "von_mises_peak", "displacement_peak"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("reduce_modes", "iterative", "local_refine", "defeature", "linear_elements", "symmetry",
                                         "adaptive_steps")
    noun: ClassVar[str] = "this load"
    governing_word: ClassVar[str] = "peak stress"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> TransientInputs:
        fixtures = parse_fixtures(document)
        loads = parse_loads(document, required=False, body=False)
        histories = tuple(parse_time_history(entry.get("history"), f"loads[{index}].history")
                          for index, entry in enumerate(document.get("loads") or ()))
        excitation = None
        if "excitation" in document:
            raw = document["excitation"]
            if not isinstance(raw, dict):
                raise ValueError('excitation: a shake at the fixtures, like {"type": "base", "direction": [0, 0, 1], '
                                 '"amplitude_g": 10, "history": {"shape": "half_sine", "duration_s": 0.002}}')
            unknown = set(raw) - {"type", "direction", "amplitude_g", "history"}
            if unknown:
                raise ValueError(f"excitation: unknown keys {sorted(unknown)}; a base shake takes type, direction, "
                                 "amplitude_g and history")
            if raw.get("type", "base") != "base":
                raise ValueError(f"excitation.type: {kinds.json_text(raw.get('type'))} is not \"base\" (the fixtures shaken); "
                                 "forces over time go in loads, each with its history")
            if "direction" not in raw:
                raise ValueError("excitation.direction: the direction it is shaken along as [x, y, z], like [0, 0, 1] for Z")
            excitation = Excitation(
                _unit(raw["direction"], "excitation.direction"),
                kinds.number(raw.get("amplitude_g", 1.0), where="excitation.amplitude_g", positive=True),
                parse_time_history(raw.get("history"), "excitation.history"),
            )
        if not loads and excitation is None:
            raise ValueError("study: nothing pushes or shakes it; add 'loads' (forces or pressures on faces, each with a "
                             "history) or 'excitation' (the fixtures shaken, with a history)")
        if "end_s" not in document:
            raise ValueError("study.end_s: how long to follow the motion, in seconds, like 0.02 for 20 ms")
        end = kinds.number(document["end_s"], where="end_s", positive=True)
        raw_step = document.get("step_s", "auto")
        step = None
        if raw_step != "auto":
            step = kinds.number(raw_step, where="step_s", positive=True)
            if step > end:
                raise ValueError(f"step_s: the step ({step:g} s) is longer than the run ({end:g} s); use a shorter step or \"auto\"")
        zeta = kinds.number(document.get("damping_ratio", 0.02), where="damping_ratio")
        if not 0 <= zeta < 1:
            raise ValueError(f"damping_ratio: a share of critical damping, like 0.02 for 2 %, from 0 (none) to under 1; got {zeta:g}")
        method = document.get("method", "modal")
        if method not in METHODS:
            raise ValueError(f"method: {kinds.json_text(method)} is not one of \"modal\" (modes, each integrated exactly) "
                             "or \"direct\" (the whole model stepped through time)")
        refs = tuple(dict.fromkeys(ref for group in (*fixtures, *loads) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        return TransientInputs(refs, anchors, True, fixtures=fixtures, loads=loads, histories=histories, excitation=excitation,
                               end_s=end, step_s=step, damping_ratio=zeta, method=method)

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    @staticmethod
    def method_of(plan, inputs: TransientInputs) -> str:
        """The method the run uses: the study's, unless the ladder switched direct to modal."""
        return getattr(plan, "_transient_method", None) or inputs.method

    def estimate(self, ctx: SolveContext, inputs: TransientInputs):
        """Modal: finding the modes (:func:`modal.eigen_estimate`) and a static solve per load, each mode's shape and
        stress, then every step's combination. Direct: two modes (for the damping) and a static solve, a factor of
        the step's matrix, then a solve a step (multigrid CG on an iterative plan)."""
        from cadgen._internal.fea import fit

        plan = ctx.plan
        steps = max(1, round(inputs.end_s / inputs.first_step()))
        frames = max_frames(ctx)
        vectors = len(inputs.histories_all)
        if self.method_of(plan, inputs) == "modal":
            modes = int(getattr(plan, "modes", None) or GUESS_MODES)
            base = eigen_estimate(ctx, modes, static_solves=vectors)
            nodes = base.dofs / 3.0
            basis = modes + vectors
            memory = base.memory_bytes + 8.0 * 9 * nodes * basis + 4.0 * 7 * nodes * frames + 16.0 * steps * basis \
                + 8.0 * 64 * 9 * nodes
            seconds = base.seconds + basis * fit.SECONDS_PER_ELEMENT.get(plan.order, 2.5e-4) * nodes / 1.7 \
                + 2e-9 * steps * basis * 9 * nodes
            return fit.Estimate(dofs=base.dofs, memory_bytes=int(memory), seconds=float(seconds))
        base = eigen_estimate(ctx, 2, static_solves=1)
        n = max(int(base.dofs), 1)
        if plan.adaptive_steps:
            steps = max(1, steps // 2)
        if plan.solver == "direct":
            factor = 16.0 * fit.FILL * n ** 1.5
            per_step = 2.4e-9 * n ** 1.5 + 2e-8 * n
            setup = 2 * fit.DIRECT_SECONDS * n ** 2
        else:
            factor = 12.0 * fit.NNZ_PER_ROW.get(plan.order, 77.0) * n * fit.AMG_COPIES
            per_step = 0.25 * fit.AMG_SECONDS_PER_DOF * n + 2e-8 * n
            setup = fit.AMG_SECONDS_PER_DOF * n
        memory = base.memory_bytes + factor + 8.0 * n * (12 + frames)
        seconds = base.seconds + setup + steps * per_step + 2e-8 * frames * 6 * n
        return fit.Estimate(dofs=n, memory_bytes=int(memory), seconds=float(seconds))

    def apply(self, rung, ctx: SolveContext, inputs: TransientInputs):
        """``reduce_modes``: direct switches to modal (said in words), or modal keeps the fewest modes holding 90 % of
        the response (its words give the share once the modes are found). ``iterative``: LOBPCG for the modes, CG for
        Newmark's steps. ``adaptive_steps``: Newmark's error-controlled step (modal integrates exactly; it takes none).
        The mesh rungs the shared way; ``symmetry`` and ``idealise`` are not taken for a response in time yet."""
        from cadgen._internal.fea import fit

        plan = ctx.plan
        method = self.method_of(plan, inputs)
        if rung == "reduce_modes":
            if method == "direct":
                plan._transient_method = "modal"
                return fit.Step(
                    "reduce_modes",
                    "Solved by modal superposition (each mode followed exactly, the modes left out by their steady share) "
                    "instead of stepping the whole model through time (direct), to fit",
                    None, None, detail={"from_method": "direct", "to_method": "modal"},
                )
            if plan.modes is not None and plan.modes <= REDUCED_GUESS:
                return None
            plan.modes = REDUCED_GUESS
            step = fit.Step("reduce_modes", f"Kept only the fewest modes holding {KEEP_SHARE * 100:.0f}% of the response, "
                            "the rest by their steady share, to fit", None, None, detail={"keep_share": KEEP_SHARE})
            plan._transient_reduce_step = step
            return step
        if rung == "iterative":
            if plan.solver != "direct":
                return None
            before = self.estimate(ctx, inputs)
            plan.solver = "iterative"
            after = self.estimate(ctx, inputs)
            words = ("Found the modes with an iterative solver (LOBPCG with multigrid) instead of factorising the stiffness"
                     if method == "modal" else "Solved each time step with an iterative solver (multigrid CG) instead of a factor")
            if before.memory_bytes > ctx.budget.memory_bytes and after.memory_bytes < before.memory_bytes:
                return fit.Step("iterative", f"{words}, to fit in memory", None, None,
                                detail={"from_bytes": before.memory_bytes, "to_bytes": after.memory_bytes})
            if before.memory_bytes <= ctx.budget.memory_bytes and after.seconds < 0.95 * before.seconds:
                return fit.Step("iterative", f"{words}, to finish sooner", None, None,
                                detail={"from_seconds": round(before.seconds, 1), "to_seconds": round(after.seconds, 1)})
            plan.solver = "direct"
            return None
        if rung == "adaptive_steps":
            from cadgen._internal.fea.timestep import NEWMARK_TOLERANCE

            if plan.adaptive_steps or method == "modal":
                return None
            plan.adaptive_steps = True
            share = NEWMARK_TOLERANCE * 100
            return fit.Step(
                "adaptive_steps",
                "Let the time step grow while the motion changes smoothly, checking each step's error, to fit the time target",
                f"each step's error kept under {share:g}% of the largest motion", share,
                detail={"first_step_s": round(inputs.first_step(), 9), "tolerance": NEWMARK_TOLERANCE},
            )
        if rung in ("idealise", "symmetry"):
            return None
        return fit.apply_generic(rung, self, ctx, inputs)

    def governing(self, result: AnalysisResult) -> tuple["np.ndarray", float]:
        """local_refine keeps the mesh fine where the part is stressed most over all time."""
        envelope = result.fields["von_mises_peak"]
        return envelope, float(envelope.max())

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: TransientInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea import superposition as sp

        space = ctx.space
        plan = ctx.plan
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        materials = materials_of(ctx)
        K = operators.stiffness(space, materials)
        M = operators.mass(space, materials)
        fixed = fixed_dofs(space, inputs.fixtures, ctx.ordinal_of)
        free = np.setdiff1d(np.arange(space.dofs), fixed)
        # Each load vector with its history: the face loads, then the shake as the inertia it puts in, -M r a.
        vectors: list[np.ndarray] = [sp.load_vector(space, (load,), ctx.ordinal_of) for load in inputs.loads]
        if inputs.excitation is not None:
            r = sp.rigid_translation(space.component, inputs.excitation.direction)
            vectors.append(-(M @ r) * (inputs.excitation.amplitude_g * G0_MM_S2))
        histories = inputs.histories_all
        F = np.stack(vectors, axis=1)                                            # (dofs, J)
        timings["assemble_s"] = time.perf_counter() - started

        iterative = getattr(plan, "solver", "direct") != "direct"
        started = time.perf_counter()
        statics = np.zeros_like(F)
        for j in range(F.shape[1]):
            u_free, _ = operators.solve_spd(K, F[:, j], free, space.locations, space.component, warnings,
                                            method="iterative" if iterative else None)
            statics[free, j] = u_free
        peaks = np.array([h.peak for h in histories])
        steady_vector = statics @ peaks
        steady = space.nodal(steady_vector)
        static_max = float(np.linalg.norm(steady, axis=1).max())
        # Its stress, recovered as every frame's is, so the two compare like with like.
        static_vm = float(sp.von_mises_of(sp.modal_stresses(space, materials, sp.Modes(np.zeros(1), steady_vector[:, None]))[0]).max())
        timings["static_s"] = time.perf_counter() - started

        method = self.method_of(plan, inputs)
        corners = sorted({c for h in histories for c in h.corners})
        frames_wanted = max_frames(ctx)
        if method == "modal":
            march = self._modal(ctx, inputs, K, M, fixed, F, statics, histories, corners, frames_wanted, timings, warnings)
        else:
            march = self._direct(ctx, inputs, K, M, fixed, free, F, histories, corners, frames_wanted, timings, warnings)
        if ctx.log:
            ctx.log(f"transient: {march['steps']} steps to {inputs.end_s:g} s, {march['solver']}")

        frame_t = march["frame_t"]
        stress_max = [float(v.max()) for v in march["frame_vm"]]
        disp_max = [float(np.linalg.norm(d, axis=1).max()) for d in march["frame_u"]]
        if max(stress_max, default=0.0) > 0:
            default = int(np.argmax(stress_max))
        else:
            default = int(np.argmax(disp_max))
        series = Series(kind="time", unit="s", default=default, frames=[
            SeriesFrame(value=round(t, 9), label=time_label(t), attributes={
                "von_mises": "_VON_MISES" if n == 0 else f"_VON_MISES_F{n}",
                "displacement": "_DISPLACEMENT" if n == 0 else f"_DISPLACEMENT_F{n}",
            })
            for n, t in enumerate(frame_t)
        ])
        curve_t, curve_d = march["curve_t"], march["curve_d"]
        if len(curve_t) > 600:
            stride = math.ceil(len(curve_t) / 600)
            keep = sorted({0, len(curve_t) - 1, int(np.argmax(curve_d)), *range(0, len(curve_t), stride)})
            curve_t, curve_d = [curve_t[i] for i in keep], [curve_d[i] for i in keep]
        return AnalysisResult(
            dof_locations=space.dof_locations,
            vertices=space.vertices,
            tets=space.tets,
            boundary_quadratic=space.boundary_quadratic,
            element_dofs=space.element_dofs,
            # Frame 0 (t = 0) is the fields' own attribute; the viewer opens on the series' default, the peak.
            fields={"von_mises": march["frame_vm"][0], "displacement": march["frame_u"][0],
                    "von_mises_peak": march["vm_peak"], "displacement_peak": march["u_peak"]},
            deformation=march["frame_u"][0],
            series=series,
            frame_fields={"von_mises": march["frame_vm"], "displacement": march["frame_u"]},
            curves={"max_displacement_mm": {"x": [round(float(t), 9) for t in curve_t], "x_unit": "s",
                                            "y": [round(float(v), 9) for v in curve_d], "y_unit": "mm"}},
            scalars={
                **march["scalars"],
                "method": method,
                "frame_t": frame_t,
                "vm_peak_t": march["vm_peak_t"],
                "u_peak_t": march["u_peak_t"],
                "steps": march["steps"],
                "first_step_s": march["first_step_s"],
                "smallest_step_s": march["smallest"],
                "largest_step_s": march["largest"],
                "adaptive": march["adaptive"],
                "end_s": march["end_s"],
                "static_max_mm": static_max,
                "static_von_mises_MPa": static_vm,
                "applied": [[float(F[space.component == c, j].sum()) for c in range(3)] for j in range(F.shape[1])],
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
            solver=march["solver"],
            timings=timings,
            warnings=warnings,
        )

    def _end(self, inputs: TransientInputs, corners: list[float], f1: float) -> float:
        """The run's end: the study's, or (drop's dynamic check) long enough to see mode 1 ring after the last corner."""
        if inputs.settle_periods > 0 and f1 > 0:
            return max(inputs.end_s, max(corners, default=0.0) + inputs.settle_periods / f1)
        return inputs.end_s

    def _step(self, inputs: TransientInputs, end: float, f1: float) -> float:
        if inputs.step_s is not None:
            return min(inputs.step_s, end)
        step = inputs.first_step()
        if f1 > 0:
            step = min(step, 1.0 / (STEPS_PER_PERIOD * f1))
        return max(step, end / MAX_AUTO_STEPS)

    def _modal(self, ctx, inputs: TransientInputs, K, M, fixed, F, statics, histories, corners, frames_wanted, timings, warnings):
        import time

        import numpy as np

        from cadgen._internal.fea import superposition as sp
        from cadgen._internal.fea import timestep

        space, plan = ctx.space, ctx.plan
        reduce = getattr(plan, "_transient_reduce_step", None) is not None
        base = inputs.excitation is not None and not inputs.loads
        r = None if inputs.excitation is None else sp.rigid_translation(space.component, inputs.excitation.direction)
        Mr = None if r is None else M @ r
        total_along = 0.0 if r is None else float(r @ Mr)
        enough = None
        if reduce and base and total_along > 0:
            def enough(omega2, vectors, free):
                return float(((vectors.T @ Mr[free]) ** 2).sum()) / total_along >= KEEP_SHARE

        started = time.perf_counter()
        method = solver_method(ctx, space.dofs - len(fixed))
        found = sp.find_modes(K, M, fixed, inputs.top_Hz, method=method, locations=space.locations,
                              component=space.component, enough=enough)
        warnings.extend(found.warnings)
        found.vectors = align_degenerate(found.vectors, M, found.frequencies_Hz, space.component)
        timings["eigen_s"] = time.perf_counter() - started
        Pm = found.vectors.T @ F                                                  # (m, J) modal loads per unit history
        kept = np.arange(len(found))
        kept_share = None
        if reduce:
            # Each mode's share of the steady response's work under the loads at their peak.
            p = Pm @ np.array([h.peak for h in histories])
            weights = p ** 2 / np.maximum(found.omega ** 2, 1e-300)
            if base and total_along > 0:
                kept, kept_share = sp.fewest_modes(sp.participation(found, M, r) ** 2, total_along, KEEP_SHARE)
            else:
                kept, kept_share = sp.fewest_modes(weights, float(weights.sum()), KEEP_SHARE)
            self._settle_reduce_step(plan, found, kept, kept_share, base)
        used = found.take(kept)
        Pu = Pm[kept]
        # The static correction: each load's steady answer less what the kept modes carry of it.
        residual = statics - used.vectors @ (Pu / (used.omega ** 2)[:, None])
        basis = sp.Modes(np.concatenate([used.omega, np.zeros(F.shape[1])]), np.hstack([used.vectors, residual]))

        started = time.perf_counter()
        shapes = sp.nodal_shapes(space, basis)                                    # (B, nodes, 3)
        stresses = sp.modal_stresses(space, materials_of(ctx), basis)             # (B, 6, nodes)
        timings["stress_s"] = time.perf_counter() - started

        started = time.perf_counter()
        f1 = float(found.frequencies_Hz[0])
        end = self._end(inputs, corners, f1)
        dt = self._step(inputs, end, f1)
        times = time_grid(end, dt, corners)
        H = np.stack([h.values(times) for h in histories], axis=1)               # (T, J)
        Q, _ = timestep.modal_march(used.omega, inputs.damping_ratio, times, H @ Pu.T)
        Z = np.hstack([Q, H])                                                     # (T, B)
        count, nodes = len(times), shapes.shape[1]
        flat = shapes.reshape(len(basis), nodes * 3)
        curve = np.zeros(count)
        u_peak = np.zeros(nodes)
        u_peak_t = np.zeros(nodes)
        chunk = max(1, min(256, int(4e6 // max(nodes * 3, 1))))
        for start in range(0, count, chunk):
            stop = min(start + chunk, count)
            size = np.linalg.norm((Z[start:stop] @ flat).reshape(stop - start, nodes, 3), axis=2)
            curve[start:stop] = size.max(axis=1)
            at = size.argmax(axis=0)
            best = size[at, np.arange(nodes)]
            higher = best > u_peak
            u_peak[higher] = best[higher]
            u_peak_t[higher] = times[start + at[higher]]
        # Stress at every step while that is cheap; else at a stride, always at each displacement peak in time.
        stride = max(1, math.ceil(count * len(basis) * 6 * nodes / STRESS_WORK))
        sampled = set(range(0, count, stride)) | {count - 1}
        if stride > 1:
            sampled |= {i for i in range(1, count - 1) if curve[i] >= curve[i - 1] and curve[i] >= curve[i + 1]}
        sampled = np.array(sorted(sampled))
        flat_s = stresses.reshape(len(basis), 6 * nodes)
        vm_peak = np.zeros(nodes)
        vm_peak_t = np.zeros(nodes)
        vm_curve = np.zeros(len(sampled))
        chunk = max(1, min(256, int(4e6 // max(nodes * 6, 1))))
        for start in range(0, len(sampled), chunk):
            rows = sampled[start:start + chunk]
            S = (Z[rows] @ flat_s).reshape(len(rows), 6, nodes).transpose(1, 0, 2)
            vm = sp.von_mises_of(S)                                               # (rows, nodes)
            vm_curve[start:start + len(rows)] = vm.max(axis=1)
            at = vm.argmax(axis=0)
            best = vm[at, np.arange(nodes)]
            higher = best > vm_peak
            vm_peak[higher] = best[higher]
            vm_peak_t[higher] = times[rows[at[higher]]]
        specials = {int(np.argmax(curve))}
        if vm_curve.max() > 0:
            specials.add(int(sampled[int(np.argmax(vm_curve))]))
        chosen = _frame_steps(times, frames_wanted, specials)
        frame_u = [(Z[i] @ flat).reshape(nodes, 3) for i in chosen]
        frame_vm = [sp.von_mises_of((Z[i] @ flat_s).reshape(6, nodes)) for i in chosen]
        timings["march_s"] = time.perf_counter() - started
        participation = None
        if r is not None:
            along = float((sp.participation(found, M, r) ** 2).sum() / total_along) if total_along > 0 else None
            participation = along
        modes_words = f"{len(used)} mode{'s' if len(used) != 1 else ''}"
        return {
            "steps": count - 1, "first_step_s": dt, "smallest": float(np.diff(times).min()) if count > 1 else 0.0,
            "largest": float(np.diff(times).max()) if count > 1 else 0.0, "adaptive": False, "end_s": end,
            "curve_t": times.tolist(), "curve_d": curve.tolist(),
            "frame_t": [float(times[i]) for i in chosen], "frame_u": frame_u, "frame_vm": frame_vm,
            "vm_peak": vm_peak, "vm_peak_t": vm_peak_t, "u_peak": u_peak, "u_peak_t": u_peak_t,
            "solver": f"{found.how}; modal superposition of {modes_words}, each integrated exactly, with the static "
                      "correction for the modes left out",
            "scalars": {
                "frequencies_Hz": [float(f) for f in found.frequencies_Hz],
                "used_modes": [int(i) for i in kept],
                "kept_share": kept_share,
                "searched_Hz": found.searched_Hz,
                "top_Hz": inputs.top_Hz,
                "content_Hz": inputs.content_Hz(),
                "along_share": participation,
                "rayleigh": None,
            },
        }

    def _direct(self, ctx, inputs: TransientInputs, K, M, fixed, free, F, histories, corners, frames_wanted, timings, warnings):
        import time

        import numpy as np

        from cadgen._internal.fea import superposition as sp
        from cadgen._internal.fea import timestep
        from cadgen._internal.fea.operators import rigid_body_modes

        space, plan = ctx.space, ctx.plan
        started = time.perf_counter()
        method = solver_method(ctx, len(free))
        # The first two modes: Rayleigh damping is fitted to the damping ratio there, and mode 1 sets the auto step.
        two = sp.find_modes(K, M, fixed, 1e12, method=method, locations=space.locations, component=space.component,
                            start=2, cap=2)
        omega = [float(w) for w in two.omega]
        timings["eigen_s"] = time.perf_counter() - started
        alpha, beta = timestep.rayleigh(omega[0], omega[1] if len(omega) > 1 else None, inputs.damping_ratio)
        Kff = K[free][:, free].tocsr()
        Mff = M[free][:, free].tocsr()
        C = None if alpha == 0 and beta == 0 else (Mff * alpha + Kff * beta)
        Ff = F[free]
        f1 = omega[0] / _TWO_PI
        end = self._end(inputs, corners, f1)
        dt = self._step(inputs, end, f1)
        adaptive = bool(getattr(plan, "adaptive_steps", False))
        iterative = getattr(plan, "solver", "direct") != "direct"
        hist = histories

        def load(t: float):
            return Ff @ np.array([h.value(t) for h in hist])

        nodes = space.scalar_count
        full = np.zeros(space.dofs)
        state = {"best": -1.0, "best_t": 0.0, "best_u": None}
        curve_t: list[float] = []
        curve_d: list[float] = []
        u_peak = np.zeros(nodes)
        u_peak_t = np.zeros(nodes)
        targets = list(np.linspace(0.0, end, max(frames_wanted - 1, 2)))
        kept: list[tuple[float, np.ndarray]] = []

        def on_step(t, u, v, a):
            full[free] = u
            size = np.linalg.norm(space.nodal(full), axis=1)
            largest = float(size.max())
            curve_t.append(t)
            curve_d.append(largest)
            higher = size > u_peak
            u_peak[higher] = size[higher]
            u_peak_t[higher] = t
            if largest > state["best"]:
                state.update(best=largest, best_t=t, best_u=u.copy())
            while targets and t >= targets[0] * (1 - 1e-9) - 1e-15:
                if not kept or kept[-1][0] != t:
                    kept.append((t, u.copy()))
                targets.pop(0)

        started = time.perf_counter()
        near_null = rigid_body_modes(space.locations[free], space.component[free]) if iterative else None
        run = timestep.newmark(Mff, C, Kff, load, end, dt, adaptive=adaptive, largest_step=end / 20, stops=corners,
                               solver="iterative" if iterative else "direct", near_null=near_null,
                               error_modes=two.vectors[free], on_step=on_step,
                               log=ctx.log)
        warnings.extend(run.warnings)
        if all(t != state["best_t"] for t, _ in kept):
            kept.append((state["best_t"], state["best_u"]))
            kept.sort(key=lambda frame: frame[0])
        columns = np.zeros((space.dofs, len(kept)))
        for i, (_, u) in enumerate(kept):
            columns[free, i] = u
        frames = sp.Modes(np.zeros(len(kept)), columns)
        frame_u = list(sp.nodal_shapes(space, frames))
        frame_vm = [sp.von_mises_of(s) for s in sp.modal_stresses(space, materials_of(ctx), frames)]
        timings["march_s"] = time.perf_counter() - started
        # Stress is recovered at the frames (the displacement peak among them): its envelope is theirs.
        stacked = np.stack(frame_vm)
        at = stacked.argmax(axis=0)
        vm_peak = stacked.max(axis=0)
        frame_t = [t for t, _ in kept]
        vm_peak_t = np.array(frame_t)[at]
        damping = "undamped" if C is None else (f"Rayleigh damping {inputs.damping_ratio * 100:g}% at "
                                                f"{' and '.join(hz_text(w / _TWO_PI) for w in omega)}")
        return {
            "steps": run.steps, "first_step_s": dt, "smallest": run.smallest_step, "largest": run.largest_step,
            "adaptive": adaptive, "end_s": end, "curve_t": curve_t, "curve_d": curve_d,
            "frame_t": frame_t, "frame_u": frame_u, "frame_vm": frame_vm,
            "vm_peak": vm_peak, "vm_peak_t": vm_peak_t, "u_peak": u_peak, "u_peak_t": u_peak_t,
            "solver": f"{run.how}, {run.steps} {'adaptive ' if adaptive else ''}steps, {damping}",
            "scalars": {
                "frequencies_Hz": [w / _TWO_PI for w in omega],
                "rejected_steps": run.rejected,
                "rayleigh": {"alpha_per_s": alpha, "beta_s": beta, "modes_Hz": [w / _TWO_PI for w in omega]},
            },
        }

    @staticmethod
    def _settle_reduce_step(plan, found, kept, share: float | None, by_mass: bool) -> None:
        """reduce_modes' step says what it kept once the modes are found: its words are written now (in place,
        like harmonic's: the ladder recorded the step before the solve)."""
        from cadgen._internal.fea import fit

        step = getattr(plan, "_transient_reduce_step", None)
        if step is None or not isinstance(step, fit.Step):
            return
        what = "of the mass moving with the shake" if by_mass else "of the response to the loads"
        words = (f"Kept {len(kept)} of the {len(found)} modes up to {hz_text(found.searched_Hz)}, the ones holding "
                 f"{(share or 0.0) * 100:.0f}% {what}, the rest by their steady share, to fit")
        object.__setattr__(step, "words", words)
        step.detail.update({"kept_modes": len(kept), "found_modes": len(found), "kept_share": round(share or 0.0, 4)})

    # -- checks, findings ----------------------------------------------------------------------------

    def _frame_at(self, result: AnalysisResult, when: float) -> int:
        times = result.scalars["frame_t"]
        return min(range(len(times)), key=lambda i: (abs(times[i] - when), i))

    def _at(self, result: AnalysisResult, when: float) -> dict:
        return {"frame": self._frame_at(result, when), "value": round(when, 9), "unit": "s", "time_s": round(when, 9)}

    def _stress_peak(self, result: AnalysisResult) -> tuple[int, float, float]:
        """(node, MPa, s) of the highest von Mises over all time."""
        envelope = result.fields["von_mises_peak"]
        node = int(envelope.argmax())
        return node, float(envelope[node]), float(result.scalars["vm_peak_t"][node])

    def _yield_at(self, result: AnalysisResult, node: int) -> float:
        domains = result.scalars["node_domain"]
        yields = result.scalars["yields"]
        if domains is None or len(yields) == 1:
            return yields[0]
        return yields[int(domains[node])]

    def needs_finer(self, result: AnalysisResult, inputs: TransientInputs, check_results: list[dict]) -> bool:
        """Solve once more finer when a check is close, or the peak stress lies between yield over the margin and yield."""
        if check_results:
            return any(check["status"] == "close" for check in check_results)
        if not any(check.get("kind") == "stress" for check in result.scalars["study_checks"]):
            return False
        node, peak, _ = self._stress_peak(result)
        ratio = peak / self._yield_at(result, node)
        return 1.0 / result.scalars["margin"] < ratio <= 1.0

    def refined_record(self, result: AnalysisResult, size_mm: float, finer_mm: float, *, assembly: bool) -> dict:
        return {"from_size_mm": round(size_mm, 4), "from_max_von_mises_MPa": round(self._stress_peak(result)[1], 4),
                "size_mm": round(finer_mm, 4), "max_von_mises_MPa": None}

    def merge_finer(self, coarse: AnalysisResult, finer: AnalysisResult, refined: dict) -> AnalysisResult:
        refined["max_von_mises_MPa"] = round(self._stress_peak(finer)[1], 4)
        finer.scalars["coarser_peak_MPa"] = self._stress_peak(coarse)[1]
        return finer

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: TransientInputs) -> dict:
        from cadgen._internal.fea import checks
        from cadgen._internal.fea.analyses.static import _peak_face

        if check["kind"] == "stress":
            node, peak, when = self._stress_peak(result)
            fixed = {ctx.ordinal_of[ref] for fixture in inputs.fixtures for ref in fixture.faces}
            at = tuple(float(c) for c in result.dof_locations[node])
            solved = checks.Solved(
                material_name="", yield_MPa=self._yield_at(result, node), peak_MPa=peak, peak_gauss_MPa=peak, peak_at=at,
                peak_face=_peak_face(ctx.volume, result, node, fixed), fixed_faces=(), max_displacement_mm=0.0,
                displacement_at=at, bbox_diagonal_mm=0.0, margin=result.scalars["margin"], coarser_peak_MPa=None, part="",
            )
            return {**checks.stress_check(solved, label=check.get("label")), "at": self._at(result, when)}
        peak = kinds.field_max_over(
            result.fields["displacement_peak"], tuple(check.get("faces", ())), boundary=result.boundary_quadratic,
            boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations, face_ref=ctx.volume.faces,
            ordinal_of=ctx.ordinal_of, where=f"view.checks[{index}]",
        )
        judged = checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces,
                                           label=check.get("label"))
        return {**judged, "at": self._at(result, float(result.scalars["u_peak_t"][peak.node]))}

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: TransientInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea.analyses.modal import finding

        scalars = result.scalars
        whole = "the assembly" if assembly else "the part"
        found: list[dict] = []
        for check in check_results:
            status = check["status"]
            if status not in ("fails", "close"):
                continue
            when = time_label(check["at"]["value"])
            severity = "error" if status == "fails" else "warning"
            item = [{"text": check["label"], **check["where"]}]
            if check["kind"] == "stress":
                if status == "fails":
                    sentence = (f"At {when}, {whole} reaches {check['value']:.3g} MPa, over its {check['limit']:g} MPa yield "
                                f"({check['label']})")
                else:
                    sentence = (f"At {when}, {whole} reaches {check['value']:.3g} MPa, inside the {check['margin']:g}× margin "
                                f"under its {check['limit']:g} MPa yield ({check['label']})")
                found.append(finding(severity, "transient_yields" if status == "fails" else "transient_close_to_yield", sentence,
                                     f"peak von Mises over time {check['value']:.4g} MPa at {check['at']['value']:.4g} s", item))
            elif check["kind"] == "displacement" and status == "close":
                found.append(finding("warning", "displacement_close",
                                     f"At {when}, it moves {check['value']:.3g} mm, close to the {check['limit']:g} mm allowed "
                                     f"({check['label']})", "the largest displacement over time", item))
        envelope = result.fields["displacement_peak"]
        node = int(envelope.argmax())
        peak_mm = float(envelope[node])
        when = float(scalars["u_peak_t"][node])
        static = scalars["static_max_mm"]
        ratio = peak_mm / static if static > 0 else None
        relative = " relative to its fixtures" if inputs.excitation is not None else ""
        found.append(finding(
            "info", "transient_peak",
            f"Moves most at {time_label(when)}: {peak_mm:.3g} mm{relative}"
            + (f", {ratio:.2f}× its steady response to the same loads" if ratio is not None else ""),
            "a load applied quickly moves a part further than the same load held steady (up to 2× for a sudden step)",
            [{"text": "moves most here", "ref": None, "at": [round(float(c), 3) for c in result.dof_locations[node]]}],
        ))
        end = scalars["end_s"]
        curve = result.curves["max_displacement_mm"]
        if when >= end * (1 - 1e-9) and len(curve["y"]) > 1 and curve["y"][-1] > curve["y"][-2] and peak_mm > 0:
            found.append(finding(
                "info", "still_moving",
                f"Still moving further at the end ({time_label(end)}): run longer (end_s) to see the peak",
                "the largest displacement was still growing at the last step", [],
            ))
        coarser = scalars.get("coarser_peak_MPa")
        if coarser:
            _, peak, _ = self._stress_peak(result)
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

        return requested or auto_deformation_scale(float(result.fields["displacement_peak"].max()), bbox_diagonal)

    def summary(self, result: AnalysisResult, inputs: TransientInputs, check_results: list[dict]) -> dict:
        scalars = result.scalars
        s_node, s_peak, s_when = self._stress_peak(result)
        envelope = result.fields["displacement_peak"]
        d_node = int(envelope.argmax())
        d_peak = float(envelope[d_node])
        yield_MPa = self._yield_at(result, s_node)
        factor = yield_MPa / s_peak if s_peak > 0 else None
        static = scalars["static_max_mm"]
        loads = []
        for load, history, applied in zip(inputs.loads, inputs.histories, scalars["applied"]):
            entry: dict[str, Any] = {"type": load.type, "faces": list(load.faces)}
            if load.type == "force":
                entry["vector_N"] = [float(c) for c in load.vector]
            else:
                entry["pressure_MPa"] = load.pressure
                entry["applied_N"] = [round(x, 4) for x in applied]
            entry["history"] = history.words()
            entry["words"] = load_words(load, history)
            loads.append(entry)
        excitation = None
        if inputs.excitation is not None:
            ex = inputs.excitation
            excitation = {"type": "base", "direction": list(ex.direction), "amplitude_g": ex.amplitude_g,
                          "history": ex.history.words()}
        summary: dict[str, Any] = {
            "method": scalars["method"],
            "loads": loads,
            "excitation": excitation,
            "end_s": round(scalars["end_s"], 9),
            "step_s": round(scalars["first_step_s"], 9),
            "steps": scalars["steps"],
            "adaptive": scalars["adaptive"],
            "smallest_step_s": round(scalars["smallest_step_s"], 9),
            "largest_step_s": round(scalars["largest_step_s"], 9),
            "damping_ratio": inputs.damping_ratio,
            "peak_s": round(scalars["frame_t"][result.series.default], 9),
            "max_von_mises_MPa": round(s_peak, 4),
            "max_von_mises_at_s": round(s_when, 9),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[s_node]],
            "yield_MPa": yield_MPa,
            "safety_factor": None if factor is None else math.floor(factor * 1000) / 1000,
            "max_displacement_mm": round(d_peak, 6),
            "max_displacement_at_s": round(float(scalars["u_peak_t"][d_node]), 9),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[d_node]],
            "static_displacement_mm": round(static, 6),
            "static_von_mises_MPa": round(scalars["static_von_mises_MPa"], 4),
            "dynamic_amplification": None if not static > 0 else round(d_peak / static, 4),
            "frames": len(scalars["frame_t"]),
            "deformation_scale": scalars["deformation_scale"],
        }
        if scalars["method"] == "modal":
            used = set(scalars["used_modes"])
            summary["modes"] = [{"mode": i + 1, "frequency_Hz": round(f, 4), "used": i in used}
                                for i, f in enumerate(scalars["frequencies_Hz"])]
            summary["modes_used"] = len(used)
            summary["modes_up_to_Hz"] = round(scalars["top_Hz"], 4)
            summary["load_content_Hz"] = round(scalars["content_Hz"], 4)
            if scalars["kept_share"] is not None:
                summary["kept_share"] = round(scalars["kept_share"], 4)
            if scalars["along_share"] is not None:
                summary["effective_mass_fraction"] = round(scalars["along_share"], 4)
        else:
            rayleigh = scalars["rayleigh"]
            summary["first_modes_Hz"] = [round(f, 4) for f in scalars["frequencies_Hz"]]
            summary["rayleigh"] = {"alpha_per_s": float(f"{rayleigh['alpha_per_s']:.6g}"),
                                   "beta_s": float(f"{rayleigh['beta_s']:.6g}"),
                                   "modes_Hz": [round(f, 4) for f in rayleigh["modes_Hz"]]}
            summary["rejected_steps"] = scalars["rejected_steps"]
        if scalars.get("parts"):
            summary["parts"] = scalars["parts"]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} over time"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        # Per-frame fields: one range across every frame, so the colours compare along the run.
        vm = max(float(v.max()) for v in result.frame_fields["von_mises"])
        disp = max(float(np.linalg.norm(d, axis=1).max()) for d in result.frame_fields["displacement"])
        return {"von_mises": (0.0, round(vm, 4)), "displacement": (0.0, round(disp, 6)),
                "von_mises_peak": (0.0, summary["max_von_mises_MPa"]), "displacement_peak": (0.0, summary["max_displacement_mm"])}

    def extras_head(self, summary: dict) -> dict:
        return {"peak_s": summary["peak_s"], "safety_factor": summary["safety_factor"]}

    def extras_assembly(self, summary: dict) -> dict:
        return {"parts": summary.get("parts", [])}

    def study_echo(self, inputs: TransientInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        def load_echo(load: Load, history: History) -> dict:
            return {"type": load.type, "faces": bare(load.faces),
                    **({"vector_N": [float(c) for c in load.vector]} if load.type == "force" else {"pressure_MPa": load.pressure}),
                    "history": history.echo()}

        echo: dict[str, Any] = {
            "fixtures": [{"type": fixture.type, "faces": bare(fixture.faces)} for fixture in inputs.fixtures],
            "loads": [load_echo(load, history) for load, history in zip(inputs.loads, inputs.histories)],
        }
        if inputs.excitation is not None:
            ex = inputs.excitation
            echo["excitation"] = {"type": "base", "direction": list(ex.direction), "amplitude_g": ex.amplitude_g,
                                  "history": ex.history.echo()}
        echo.update({"end_s": inputs.end_s, "step_s": "auto" if inputs.step_s is None else inputs.step_s,
                     "damping_ratio": inputs.damping_ratio, "method": inputs.method})
        return echo

    def human_lines(self, summary: dict) -> list[str]:
        what = [load["words"] for load in summary["loads"]]
        if summary["excitation"] is not None:
            ex = summary["excitation"]
            what.append(f"shaken {ex['amplitude_g']:g} g along {axis_words(ex['direction'])}, {ex['history']}")
        if summary["method"] == "modal":
            how = (f"modal: {summary['modes_used']} mode{'s' if summary['modes_used'] != 1 else ''} up to "
                   f"{hz_text(summary['modes_up_to_Hz'])}, each followed exactly")
        else:
            how = "direct: Newmark average acceleration" + (", adaptive steps" if summary["adaptive"] else "")
        lines = [
            f"{'; '.join(what)}; followed for {time_label(summary['end_s'])} in {summary['steps']} steps "
            f"({how}, {summary['damping_ratio'] * 100:g}% damping)",
            f"peak stress {summary['max_von_mises_MPa']:.4g} MPa at {time_label(summary['max_von_mises_at_s'])}; moves up to "
            f"{summary['max_displacement_mm']:.4g} mm at {time_label(summary['max_displacement_at_s'])}"
            + (f", {summary['dynamic_amplification']:.2f}× its steady {summary['static_displacement_mm']:.4g} mm"
               if summary["dynamic_amplification"] is not None else ""),
        ]
        return lines


def _frame_steps(times: "np.ndarray", frames: int, specials: set[int]) -> list[int]:
    """The steps written as frames: evenly spaced in time from 0 to the end, plus ``specials`` (the peaks), at most
    ``frames`` in all (the peaks always kept)."""
    import numpy as np

    frames = max(int(frames), len(specials) + 2)
    even = frames - len(specials)
    chosen = set(specials)
    for target in np.linspace(times[0], times[-1], even):
        chosen.add(int(np.argmin(np.abs(times - target))))
    chosen = sorted(chosen)
    while len(chosen) > frames:
        # Drop an evenly spaced frame next to another, never a peak or the ends.
        for i in range(1, len(chosen) - 1):
            if chosen[i] not in specials:
                chosen.pop(i)
                break
        else:
            break
    return chosen


def _node_domain(space) -> "np.ndarray | None":
    import numpy as np

    if space.domain is None:
        return None
    out = np.zeros(space.scalar_count, dtype=np.int64)
    out[space.scalar.element_dofs] = np.asarray(space.domain)[None, :]
    return out
