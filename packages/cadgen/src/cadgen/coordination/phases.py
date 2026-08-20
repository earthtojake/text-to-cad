"""Phase model for one artifact build.

A build runs an ordered set of phases and reports EACH ONE SEPARATELY. There is no global
percentage, because there is no honest way to compute one. Measured across this repo's own
models, ``generate`` is 11% of one build and 84% of another, so a single bar spanning every
phase is a guess wearing a measurement's clothes -- and on a FIRST build, where nothing
about the model has been measured yet, it is a guess with no inputs at all. That is what
pinned a ten-minute F-14 ``generate`` phase at exactly 0% and then jumped it straight to
46% the instant the phase ended.

What a phase can honestly say is one of two things:

* a real FRACTION -- ``done``/``total`` -- when the work list is known. Meshing components
  builds its work list in full before the first mesh runs, so it reports ``312/1127``.
* a LABEL -- the name of the sub-unit in flight ("airframe") -- when it is not. A generator
  walking an assembly's systems knows what it is working on even when it cannot say how
  much is left, and the leaf walk that packages a compound knows which leaf it is on.

Both are true statements about the present, and neither extrapolates. A reader renders them
differently: a fraction becomes a bar, a label becomes an indeterminate bar naming the
sub-unit.

**Events are emitted at work boundaries, never from a timer.** OCP meshing holds the GIL
inside C for long stretches, so a heartbeat thread starves during exactly the work it is
meant to be reporting. A phase that cannot count says what it is DOING instead -- which is
information no timer could have produced anyway.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

PHASE_GENERATE = "generate"
PHASE_PACKAGE = "package"
PHASE_COMPONENTS = "components"
PHASE_FINALIZE = "finalize"
# Terminal marker. Not a phase -- it means "this record describes a finished run", and a
# reader must never render it as an in-flight build.
PHASE_DONE = "done"

PHASE_ORDER = (PHASE_GENERATE, PHASE_PACKAGE, PHASE_COMPONENTS, PHASE_FINALIZE)

PHASE_LABELS = {
    PHASE_GENERATE: "Building geometry",
    PHASE_PACKAGE: "Collecting parts",
    PHASE_COMPONENTS: "Meshing components",
    PHASE_FINALIZE: "Writing package",
    PHASE_DONE: "Done",
}

# Floor between record writes / status repaints for ticks that carry no count, so the
# per-leaf walk of a large assembly cannot spend the build's time on reporting. Ticks that
# move a real fraction (see ProgressReporter.advance) bypass it: those are the measured
# ones and they are coarse -- often seconds apart -- so dropping one to a rate limit would
# pin a visible count at a stale value for however long the next unit takes.
MIN_EMIT_INTERVAL_MS = 100.0


def render_progress_bar(ratio: float, width: int = 18) -> str:
    """A fixed-width unicode bar. Shared by the CLI sink and its tests so the two cannot
    disagree about what a given fraction looks like."""
    width = max(1, int(width))
    clamped = min(1.0, max(0.0, float(ratio)))
    filled = int(round(clamped * width))
    return f"▕{'█' * filled}{'░' * (width - filled)}▏"


@dataclass(frozen=True)
class ProgressEvent:
    """One observation of a build's position.

    ``index``/``count`` place the phase in the run (phase 2 of 4). ``done``/``total`` is a
    real fraction when ``determinate``; otherwise ``detail`` names the sub-unit in flight
    and there is no fraction to show.
    """

    phase: str
    label: str
    index: int
    count: int
    done: int
    total: int | None
    determinate: bool
    phase_started_at_ms: float
    elapsed_ms: float
    detail: str = ""
    stage_ms: Mapping[str, float] | None = None

    @property
    def finished(self) -> bool:
        return self.phase == PHASE_DONE

    @property
    def fraction(self) -> float | None:
        """This phase's completed share, or None when it has no denominator."""
        if not self.determinate or not self.total:
            return None
        return min(1.0, max(0.0, self.done / float(self.total)))

    def progress_payload(self) -> dict[str, object]:
        """The phase block of a status record (camelCase -- it is read by the viewer).

        Identity, outcome and stage times are the RECORD's business, not the event's; see
        :func:`cadgen.coordination.record.build_record`."""
        return {
            "phase": self.phase,
            "label": self.label,
            "index": self.index,
            "count": self.count,
            "detail": self.detail,
            "done": self.done,
            "total": self.total,
            "determinate": self.determinate,
            "phaseStartedAt": round(self.phase_started_at_ms),
            "elapsedMs": round(self.elapsed_ms),
        }


class ProgressReporter:
    """Tracks the current phase and pushes :class:`ProgressEvent`s to its sinks.

    A reporter with no sinks is inert bookkeeping, which is what keeps the no-progress call
    paths free of branching.
    """

    def __init__(
        self,
        *,
        sinks: Sequence[Callable[[ProgressEvent], None]] = (),
        clock: Callable[[], float] = time.monotonic,
        phases: Sequence[str] = PHASE_ORDER,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self._sinks = [sink for sink in sinks if sink is not None]
        self._clock = clock
        # An artifact kind declares the phases it actually has, so "phase 2 of 4" counts
        # the phases this kind runs rather than some global set.
        self._phases = tuple(phases) or PHASE_ORDER
        # Shared vocabulary, overridden by whatever this kind introduces.
        self._labels = {**PHASE_LABELS, **(labels or {})}
        self._started = clock()
        self._phase = ""
        self._phase_started = self._started
        self._phase_started_wall_ms = time.time() * 1000.0
        self._done = 0
        self._total: int | None = None
        self._detail = ""
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
        """Supply a denominator discovered mid-phase (a work list just built)."""
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
        self._emit(force=self._determinate())

    def detail(self, text: str) -> None:
        """Name the sub-unit now in flight, without claiming any fraction.

        A CHANGED label is published immediately; only a repeat of the one already showing
        is throttled. Rate-limiting a change would defeat the point of the call: the first
        label of a phase lands microseconds after the ``phase``/``set_total`` that opened it,
        so a blanket throttle silently swallowed it and the phase then ran for minutes with
        an empty label -- exactly the silence this exists to end.
        """
        if self._finished:
            return
        text = str(text or "")
        changed = text != self._detail
        self._detail = text
        self._emit(force=changed)

    def finish(self) -> None:
        """Terminal event: ``phase: done``, plus the run's measured stage times."""
        if self._finished:
            return
        self._close_phase()
        self._finished = True
        self._phase = PHASE_DONE
        # Stamped now, so a reader can time the phase that just ended by the difference.
        self._phase_started_wall_ms = time.time() * 1000.0
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

    def _position(self) -> tuple[int, int]:
        """(index, count) of the current phase, 1-based. Index 0 for a phase this kind did
        not declare -- it still reports, it just has no place in the sequence."""
        if self._phase not in self._phases:
            return (0, len(self._phases))
        return (self._phases.index(self._phase) + 1, len(self._phases))

    def _emit(self, *, force: bool = False) -> None:
        if not self._sinks:
            return
        now_ms = self._clock() * 1000.0
        if not force and (now_ms - self._last_emit) < MIN_EMIT_INTERVAL_MS:
            return
        self._last_emit = now_ms
        index, count = self._position()
        event = ProgressEvent(
            phase=self._phase,
            label=self._labels.get(self._phase, self._phase or ""),
            index=index,
            count=count,
            done=self._done,
            total=self._total,
            determinate=self._determinate(),
            phase_started_at_ms=self._phase_started_wall_ms,
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

    def detail(self, *args: object, **kwargs: object) -> None:
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
