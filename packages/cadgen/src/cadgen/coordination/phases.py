"""Phase model and progress accounting for one artifact build.

A build has stages that cost real time, and only one of them has a denominator known before
the work starts:

* ``generate`` -- running the model's ``gen_step()`` (or parsing an imported STEP).
  Arbitrary user code; there is no unit of work to count.
* ``package`` -- walking the composed compound, serializing each leaf's BREP and
  content-hashing it. Countable only as it goes: the leaf count is not known until the
  walk ends.
* ``components`` -- meshing + selector-extracting every component GLB not already in the
  package's content-addressed cache. The work list is built in full before the first mesh
  runs, so ``done``/``total`` here is MEASURED, not estimated -- and this is where most of
  a slow build's time goes.
* ``finalize`` -- descriptor write + orphan prune. Fast.

So the honest report is an exact count during ``components`` and a phase label for the
opaque stages. Every event also carries ``ratioFloor``/``ratioCeiling`` and the phase's
expected duration, so a reader that polls -- the CAD Viewer -- can interpolate an
indeterminate stage against the wall clock without the build having to say anything while
it is busy.

**Events are emitted at work boundaries, never from a timer.** A heartbeat thread is
precisely what the generation lock had to stop relying on: OCP meshing holds the GIL inside
C for long stretches, so a heartbeat starves during exactly the work it is meant to be
reporting. Readers interpolate instead.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

PHASE_GENERATE = "generate"
PHASE_PACKAGE = "package"
PHASE_COMPONENTS = "components"
PHASE_FINALIZE = "finalize"
# Terminal marker. Not a phase with a weight -- it means "this record describes a finished
# run", and a reader must never render it as an in-flight build.
PHASE_DONE = "done"

PHASE_ORDER = (PHASE_GENERATE, PHASE_PACKAGE, PHASE_COMPONENTS, PHASE_FINALIZE)

PHASE_LABELS = {
    PHASE_GENERATE: "Building geometry",
    PHASE_PACKAGE: "Collecting parts",
    PHASE_COMPONENTS: "Meshing components",
    PHASE_FINALIZE: "Writing package",
    PHASE_DONE: "Done",
}

# Fallback split, used only for an artifact that has never recorded a build. Rough by
# definition; the first completed build replaces it with this artifact's real times.
DEFAULT_PHASE_WEIGHTS = {
    PHASE_GENERATE: 0.34,
    PHASE_PACKAGE: 0.12,
    PHASE_COMPONENTS: 0.50,
    PHASE_FINALIZE: 0.04,
}
# Floor on any learned weight: a stage that was instant last time (every component cached,
# say) must still leave the bar somewhere to go if it is slow this time.
MIN_PHASE_WEIGHT = 0.02
# An indeterminate phase never fills its whole band -- reaching 100% of a stage whose end we
# cannot see would be a lie, and leaves nothing for the handoff.
INDETERMINATE_PHASE_CEILING = 0.95
# Floor between record writes / status repaints for INDETERMINATE ticks, so the per-leaf
# walk of a large assembly cannot spend the build's time on reporting. Determinate ticks
# (see ProgressReporter.advance) bypass it.
MIN_EMIT_INTERVAL_MS = 100.0


def phase_weights_from_stage_ms(
    stage_ms: object, *, phases: Sequence[str] = PHASE_ORDER
) -> dict[str, float] | None:
    """Phase weights proportional to a previous build's measured stage times.

    An artifact whose generator dominates and one whose meshing dominates need very
    different splits before one overall bar moves evenly, and the last build of THIS
    artifact is the best available predictor of the next one. Returns None when there is
    nothing usable to learn from, leaving :data:`DEFAULT_PHASE_WEIGHTS` in place."""
    if not isinstance(stage_ms, Mapping):
        return None
    values: dict[str, float] = {}
    for phase in phases:
        try:
            value = float(stage_ms.get(phase))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0.0:
            values[phase] = value
    total = sum(values.values())
    if len(values) < 2 or total <= 0.0:
        return None
    floored = {phase: max(value / total, MIN_PHASE_WEIGHT) for phase, value in values.items()}
    scale = sum(floored.values())
    return {phase: weight / scale for phase, weight in floored.items()}


def _even_weights(phases: Sequence[str]) -> dict[str, float]:
    """Fallback split for a kind that has never recorded a build.

    DEFAULT_PHASE_WEIGHTS is the measured-ish split for the STEP phase set; any other
    phase set gets an even split until its first completed build replaces it with real
    times."""
    if tuple(phases) == PHASE_ORDER:
        return dict(DEFAULT_PHASE_WEIGHTS)
    share = 1.0 / max(1, len(phases))
    return {phase: share for phase in phases}


def render_progress_bar(ratio: float, width: int = 18) -> str:
    """A fixed-width unicode bar. Shared by the CLI sink and its tests so the two cannot
    disagree about what a given ratio looks like."""
    width = max(1, int(width))
    clamped = min(1.0, max(0.0, float(ratio)))
    filled = int(round(clamped * width))
    return f"▕{'█' * filled}{'░' * (width - filled)}▏"


@dataclass(frozen=True)
class ProgressEvent:
    """One observation of a build's position. ``total`` is None for a phase with no knowable
    denominator; ``determinate`` says whether ``done``/``total`` is a real count or the
    phase is being estimated against the clock."""

    phase: str
    label: str
    done: int
    total: int | None
    determinate: bool
    ratio: float
    ratio_floor: float
    ratio_ceiling: float
    phase_started_at_ms: float
    phase_expected_ms: float | None
    elapsed_ms: float
    detail: str = ""
    stage_ms: Mapping[str, float] | None = None

    @property
    def finished(self) -> bool:
        return self.phase == PHASE_DONE

    def progress_payload(self) -> dict[str, object]:
        """The phase/ratio block of a status record (camelCase -- it is read by the viewer).

        Identity, outcome and stage times are the RECORD's business, not the event's; see
        :func:`cadgen.coordination.record.build_record`."""
        return {
            "phase": self.phase,
            "label": self.label,
            "detail": self.detail,
            "done": self.done,
            "total": self.total,
            "determinate": self.determinate,
            "ratio": round(self.ratio, 4),
            "ratioFloor": round(self.ratio_floor, 4),
            "ratioCeiling": round(self.ratio_ceiling, 4),
            "phaseStartedAt": round(self.phase_started_at_ms),
            "phaseExpectedMs": (round(self.phase_expected_ms) if self.phase_expected_ms else None),
            "elapsedMs": round(self.elapsed_ms),
        }


class ProgressReporter:
    """Tracks the current phase and pushes :class:`ProgressEvent`s to its sinks.

    ``stage_ms`` is the previous build's measured per-phase durations: it both weights the
    overall bar and supplies the expected duration an indeterminate phase is interpolated
    against. A reporter with no sinks is inert bookkeeping, which is what makes the
    no-progress call paths free of branching."""

    def __init__(
        self,
        *,
        sinks: Sequence[Callable[[ProgressEvent], None]] = (),
        stage_ms: Mapping[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        phases: Sequence[str] = PHASE_ORDER,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self._sinks = [sink for sink in sinks if sink is not None]
        self._clock = clock
        self._expected = dict(stage_ms or {})
        # An artifact kind declares the phases it actually has. A DXF drawing has no
        # meshing stage, so weighting its bar over the STEP phase set left half the bar
        # reserved for work that never happens and the drawing appeared to stall at ~46%.
        self._phases = tuple(phases) or PHASE_ORDER
        # Shared vocabulary, overridden by whatever this kind introduces.
        self._labels = {**PHASE_LABELS, **(labels or {})}
        self._weights = phase_weights_from_stage_ms(stage_ms, phases=self._phases) or _even_weights(
            self._phases
        )
        self._started = clock()
        self._phase = ""
        self._phase_started = self._started
        self._phase_started_wall_ms = time.time() * 1000.0
        self._done = 0
        self._total: int | None = None
        self._detail = ""
        self._ratio = 0.0
        self._stage_ms: dict[str, float] = {}
        self._last_emit = 0.0
        self._finished = False

    # --- driving the run ---

    def phase(self, name: str, *, total: int | None = None, detail: str = "") -> None:
        """Enter ``name``. ``total`` makes the phase determinate (a real count)."""
        if self._finished:
            return
        self._close_phase()
        self._phase = name
        self._phase_started = self._clock()
        self._phase_started_wall_ms = time.time() * 1000.0
        self._done = 0
        self._total = total if (total is None or total > 0) else 0
        self._detail = detail
        self._emit(force=True)

    def set_total(self, total: int | None) -> None:
        """Supply a denominator discovered mid-phase (a walk that has just ended)."""
        if self._finished:
            return
        self._total = total
        self._emit(force=True)

    def advance(self, count: int = 1, *, detail: str | None = None) -> None:
        """Record ``count`` more units of the current phase."""
        if self._finished:
            return
        self._done += count
        if detail is not None:
            self._detail = detail
        # Every tick of a DETERMINATE phase reports, unthrottled. Those ticks are the
        # measured ones and they are coarse -- one per component GLB, often seconds apart --
        # so dropping one to a rate limit would pin a visible count at a stale value for
        # however long the next component takes. Only the indeterminate walk, which ticks
        # once per assembly leaf, is throttled.
        self._emit(force=self._determinate())

    def finish(self) -> None:
        """Terminal event: ratio 1.0, ``phase: done``, and the run's measured stage times so
        the next build of this artifact can weight its bar from them."""
        if self._finished:
            return
        self._close_phase()
        self._finished = True
        self._phase = PHASE_DONE
        self._ratio = 1.0
        self._done = 0
        self._total = None
        self._detail = ""
        self._emit(force=True)

    def stage_ms_snapshot(self) -> dict[str, float]:
        """Stage durations recorded so far, including the phase still running."""
        snapshot = dict(self._stage_ms)
        if self._phase in self._phases:
            elapsed = (self._clock() - self._phase_started) * 1000.0
            snapshot[self._phase] = snapshot.get(self._phase, 0.0) + elapsed
        return snapshot

    # --- internals ---

    def _close_phase(self) -> None:
        if self._phase not in self._phases:
            return
        elapsed_ms = (self._clock() - self._phase_started) * 1000.0
        self._stage_ms[self._phase] = self._stage_ms.get(self._phase, 0.0) + elapsed_ms

    def _determinate(self) -> bool:
        return self._total is not None and self._total > 0

    def _bounds(self) -> tuple[float, float]:
        """The (floor, ceiling) of the current phase's band in the overall bar."""
        if self._phase not in self._phases:
            return (self._ratio, self._ratio)
        index = self._phases.index(self._phase)
        floor = sum(self._weights.get(phase, 0.0) for phase in self._phases[:index])
        span = self._weights.get(self._phase, 0.0)
        ceiling = floor + span * (1.0 if self._determinate() else INDETERMINATE_PHASE_CEILING)
        return (floor, ceiling)

    def _compute_ratio(self, floor: float, ceiling: float) -> float:
        if self._finished:
            return 1.0
        if self._determinate():
            within = min(1.0, self._done / float(self._total))  # type: ignore[arg-type]
        else:
            expected = self._expected.get(self._phase)
            if expected and expected > 0:
                elapsed_ms = (self._clock() - self._phase_started) * 1000.0
                within = min(1.0, elapsed_ms / float(expected))
            else:
                within = 0.0
        # The bar must never go backwards WITHIN a run: a learned weight can be wrong, and a
        # phase transition that lowered the number would read as a build losing ground.
        # Across runs the reader resets on a new runId instead.
        return max(self._ratio, min(1.0, floor + (ceiling - floor) * within))

    def _emit(self, *, force: bool = False) -> None:
        if not self._sinks:
            return
        now_ms = self._clock() * 1000.0
        if not force and (now_ms - self._last_emit) < MIN_EMIT_INTERVAL_MS:
            return
        self._last_emit = now_ms
        floor, ceiling = self._bounds()
        self._ratio = self._compute_ratio(floor, ceiling)
        event = ProgressEvent(
            phase=self._phase,
            label=self._labels.get(self._phase, self._phase or ""),
            done=self._done,
            total=self._total,
            determinate=self._determinate(),
            ratio=self._ratio,
            ratio_floor=floor,
            ratio_ceiling=ceiling,
            phase_started_at_ms=self._phase_started_wall_ms,
            phase_expected_ms=self._expected.get(self._phase),
            elapsed_ms=(self._clock() - self._started) * 1000.0,
            detail=self._detail,
            stage_ms=(self.stage_ms_snapshot() if self._finished else None),
        )
        for sink in self._sinks:
            try:
                sink(event)
            except Exception:  # noqa: BLE001 - reporting must never fail a build
                continue


class _NullProgressReporter:
    """Accepts every call and does nothing, so build code can report unconditionally."""

    def phase(self, *args: object, **kwargs: object) -> None:
        return None

    def set_total(self, *args: object, **kwargs: object) -> None:
        return None

    def advance(self, *args: object, **kwargs: object) -> None:
        return None

    def finish(self) -> None:
        return None

    def stage_ms_snapshot(self) -> dict[str, float]:
        return {}


NULL_PROGRESS = _NullProgressReporter()


def resolve(progress: object | None) -> object:
    """``progress or NULL_PROGRESS`` -- keeps ``if progress is not None`` out of the build
    path, where the reporting is incidental to what the code is saying."""
    return NULL_PROGRESS if progress is None else progress
