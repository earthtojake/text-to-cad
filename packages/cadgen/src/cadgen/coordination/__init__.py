"""Cross-process coordination for file-artifact generation.

ONE implementation, imported by both sides. The producer (cadgen, from a CLI or the CAD
Viewer's warm worker) holds a lock while it mutates an artifact's output directory and
publishes its progress; the reader (the viewer's server) takes a non-blocking snapshot of
that state. Before this package the reader half was a hand-written COPY of the producer
half in ``viewer/server_py/artifact.py``, kept in sync only by a test that compared path
strings -- and the two had drifted into implementing different protocols from one
primitive: the producer took a blocking exclusive lock to DO something, the reader took a
momentary exclusive lock to ASK something.

**stdlib only.** The viewer's long-lived server process imports this module, and it must
never drag OCP/build123d/ezdxf into that process. ``cadgen/__init__.py`` defers all of its
own imports, so ``import cadgen.coordination`` costs milliseconds and pulls in no CAD
runtime. That invariant is pinned by
``tests/python/packages/cadgen/test_coordination_is_stdlib_only.py``; do not add a
non-stdlib import here or to any module in this package.

Producer::

    with artifact_build(STEP_PACKAGE, package_dir,
                        is_current=lambda: package_is_current(spec),
                        force=force) as run:
        if run.skipped:                 # is_current() re-evaluated UNDER the lock
            return existing_payload()
        run.phase(PHASE_COMPONENTS, total=len(work))  # a phase that can count
        run.advance(detail=name)
        run.phase(PHASE_GENERATE)                     # a phase that cannot
        run.detail("airframe")

Reader::

    snap = snapshot(package_dir)
    snap.state       # "idle" | "writing" | "busy"
    snap.progress    # dict | None -- only when the record belongs to the live run
    snap.degraded    # locking unavailable here; coordination is not in effect
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from cadgen.coordination import record as _record
from cadgen.coordination.kinds import (
    DRAWING_PACKAGE,
    IMPLICIT_PACKAGE,
    PHASE_BROWSER,
    PHASE_RENDER,
    SNAPSHOT,
    STEP_PACKAGE,
    ArtifactKind,
)
from cadgen.coordination.lock import (
    Contended,
    exclusive,
    locking_available,
    new_run_id,
    probe,
    read_run_id,
)
from cadgen.coordination.paths import (
    generator_lock_path,
    generator_status_path,
    status_path,
    write_lock_path,
)
from cadgen.coordination.phases import (
    NULL_PROGRESS,
    PHASE_COMPONENTS,
    PHASE_DONE,
    PHASE_FINALIZE,
    PHASE_GENERATE,
    PHASE_LABELS,
    PHASE_ORDER,
    PHASE_PACKAGE,
    ProgressEvent,
    ProgressReporter,
    render_progress_bar,
    resolve,
)

__all__ = [
    "ArtifactKind",
    "BuildRun",
    "Contended",
    "DRAWING_PACKAGE",
    "IMPLICIT_PACKAGE",
    "PHASE_BROWSER",
    "PHASE_RENDER",
    "SNAPSHOT",
    "NULL_PROGRESS",
    "PHASE_COMPONENTS",
    "PHASE_DONE",
    "PHASE_FINALIZE",
    "PHASE_GENERATE",
    "PHASE_LABELS",
    "PHASE_ORDER",
    "PHASE_PACKAGE",
    "ProgressEvent",
    "ProgressReporter",
    "STEP_PACKAGE",
    "Snapshot",
    "STATE_BUSY",
    "STATE_IDLE",
    "STATE_WRITING",
    "artifact_build",
    "current_build",
    "generator_busy",
    "generator_lock_path",
    "generator_status_path",
    "render_progress_bar",
    "reporting_as",
    "require_write_lock",
    "resolve",
    "snapshot",
    "status_path",
    "write_lock_path",
]

STATE_IDLE = "idle"
STATE_WRITING = "writing"
STATE_BUSY = "busy"


# --- reader ------------------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    """A non-blocking observation of an artifact's coordination state.

    ``state`` comes from the KERNEL (which sentinel is held), never from the record --
    that is what makes a crashed or killed run read as idle with no stale window, and it
    is the one property of the old heartbeat design that had to be replaced.
    """

    state: str
    run_id: str | None = None
    progress: dict[str, Any] | None = None
    degraded: bool = False

    @property
    def writing(self) -> bool:
        return self.state == STATE_WRITING

    @property
    def busy(self) -> bool:
        return self.state == STATE_BUSY


def snapshot(output_dir: Path | str) -> Snapshot:
    """What is happening to ``output_dir`` right now. Never blocks, never creates files.

    A writer hides the artifact (it is being rewritten); a busy generator does not (the
    artifact on disk is still whatever it was). Progress is attached only when the record
    on disk belongs to the run that currently holds the writer lock -- otherwise a corpse
    left by a SIGKILLed build would be rendered as the live run's position.
    """
    if not str(output_dir or "").strip():
        return Snapshot(state=STATE_IDLE)

    write_probe = probe(write_lock_path(output_dir))
    if write_probe.held:
        run_id = read_run_id(write_lock_path(output_dir))
        return Snapshot(
            state=STATE_WRITING,
            run_id=run_id,
            progress=_record.progress_for_run(status_path(output_dir), run_id),
            degraded=False,
        )

    generator_probe = probe(generator_lock_path(output_dir))
    if generator_probe.held:
        # A busy generator reports its phases too (an export runs the same gen_step a build
        # does). Its record is a DIFFERENT file from the writer's, and attribution works the
        # same way: only the run holding this sentinel may be rendered.
        run_id = read_run_id(generator_lock_path(output_dir))
        return Snapshot(
            state=STATE_BUSY,
            run_id=run_id,
            progress=_record.progress_for_run(generator_status_path(output_dir), run_id),
        )

    return Snapshot(
        state=STATE_IDLE,
        degraded=write_probe.degraded or generator_probe.degraded,
    )


# --- producer ----------------------------------------------------------------------


class BuildRun:
    """The producer's handle inside :func:`artifact_build`.

    Forwards the :class:`ProgressReporter` API, so build code reports through the same
    object that owns the lock and there is no way to report progress for a run that is not
    holding one -- which is how a stale record used to be rendered as live.
    """

    __slots__ = ("_reporter", "contended", "degraded", "run_id", "skipped")

    def __init__(self, reporter: Any, run_id: str | None, *, degraded: bool = False) -> None:
        self._reporter = reporter
        self.run_id = run_id
        # Two ways to have no work to do, and a producer must handle both. ``skipped``: we
        # HELD the lock and found the artifact already current. ``contended``: we never got
        # the lock, because a peer holds it and the caller set a deadline. Neither is an
        # error; both mean "do not write the package".
        self.skipped = False
        self.contended = False
        # We are writing WITHOUT mutual exclusion, because locking was unavailable here (a
        # filesystem that refuses advisory locks, an unwritable __cadgen__). The build goes
        # ahead -- a missing lock must never be the reason a user's build fails -- and
        # ``run_id`` is still minted so progress has something to attribute itself to.
        #
        # A producer that hands work to a Node child MUST pass this on: the child proves it
        # was started by the lock holder by matching its run id against the sentinel, and a
        # degraded run never stamped one. This flag is the only way the child can tell "no
        # lock was taken here" from "you are not the holder", which are the same empty
        # sentinel from where it stands. See implicitjs/glb/assertWriteLock.js.
        self.degraded = degraded

    def phase(self, name: str, *, total: int | None = None, detail: str = "") -> None:
        self._reporter.phase(name, total=total, detail=detail)

    def set_total(self, total: int | None) -> None:
        self._reporter.set_total(total)

    def advance(self, count: int = 1, *, detail: str | None = None) -> None:
        self._reporter.advance(count, detail=detail)

    def detail(self, text: str) -> None:
        self._reporter.detail(text)

    def stage_ms_snapshot(self) -> dict[str, float]:
        return self._reporter.stage_ms_snapshot()


# The run whose lock is held on this thread, for code that is too far from `artifact_build`
# to be handed it. `run_node_builder` solves the same problem across a PIPE -- the Node
# child describes its work and the holder publishes it -- and this is the in-process twin:
# a generator's `gen_step()` is called with no arguments and cannot be given the BuildRun,
# so it looks the run up instead. A ContextVar rather than a global because the viewer's
# warm worker is long-lived and must never leak one build's reporter into another's.
_CURRENT_BUILD: contextvars.ContextVar[BuildRun | None] = contextvars.ContextVar(
    "cadgen_current_build", default=None
)


def current_build() -> BuildRun | None:
    """The :class:`BuildRun` reporting for the work on this thread, or None outside a build.

    Callers report through it and must never assume it exists: the same generator runs under
    the CLI, the viewer's worker, a test harness, and a plain `python model.step.py`.
    """
    return _CURRENT_BUILD.get()


@contextlib.contextmanager
def reporting_as(run: BuildRun | None) -> Iterator[None]:
    """Make ``run`` the :func:`current_build` for the duration of the block.

    Nested binds are IGNORED: a model that composes child generators would otherwise have
    the child's loop retarget the parent's phase, and the outermost loop is the one whose
    count means anything to a reader.
    """
    if run is None or _CURRENT_BUILD.get() is not None:
        yield
        return
    token = _CURRENT_BUILD.set(run)
    try:
        yield
    finally:
        _CURRENT_BUILD.reset(token)


@contextlib.contextmanager
def artifact_build(
    kind: ArtifactKind,
    output_dir: Path | str | None,
    *,
    is_current: Callable[[], bool] | None = None,
    force: bool = False,
    deadline_ms: float | None = None,
    on_wait: Callable[[float], None] | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> Iterator[BuildRun]:
    """Own the write lock, the status record, and the post-lock freshness re-check.

    Order of operations, and every part of it matters:

    1. Acquire the write lock (blocking, or bounded by ``deadline_ms`` -- in which case a
       peer holding it yields a run with ``contended`` set and nothing else happens).
    2. Mint a run id, stamp it into the sentinel, and publish a ``starting`` record --
       synchronously, BEFORE any work and before yielding. This is what closes the window
       in which a reader could attribute a previous run's record to this one.
    3. Re-evaluate ``is_current()`` UNDER the lock and set ``run.skipped``. The caller's
       own pre-lock fast path cannot cover the concurrent case: it ran before the peer
       existed, so a process that queued behind one would wake up and redo the full
       generator+mesh the holder had just finished.
    4. Yield.
    5. Publish the terminal record -- ``done`` WITH the run's stage times, or ``failed``
       WITHOUT them, so a failed run cannot teach the next build's bar.

    ``force=True`` skips only the ``is_current()`` call, never the lock.
    ``output_dir`` of None (a producer with no coordinated output) yields an inert run.
    ``on_wait`` reports a contended acquire while it is still waiting -- see
    :func:`cadgen.coordination.lock.exclusive`.
    """
    if output_dir is None:
        # Uncoordinated (a producer with no output dir of its own). There is no lock and no
        # record, but is_current is still a FRESHNESS question, not a locking one, and must
        # be answered the same way -- otherwise "do I have work to do?" would depend on
        # whether coordination happened to be available.
        run = BuildRun(NULL_PROGRESS, None)
        if not force and is_current is not None:
            with contextlib.suppress(Exception):
                run.skipped = bool(is_current())
        yield run
        return

    started_at_ms = time.time() * 1000.0
    target = status_path(output_dir)

    # The acquire is entered separately from the body so a deadline that expires can be
    # reported as an OUTCOME (run.contended) rather than thrown through the caller. A peer
    # holding the lock is an ordinary answer to "should I build this?", the same shape as
    # run.skipped -- and a caller that ignores it and writes anyway is caught at the
    # mutation boundary by require_write_lock().
    stack = contextlib.ExitStack()
    try:
        run_id = stack.enter_context(
            exclusive(write_lock_path(output_dir), deadline_ms=deadline_ms, on_wait=on_wait)
        )
    except Contended:
        contended_run = BuildRun(NULL_PROGRESS, None)
        contended_run.contended = True
        yield contended_run
        return

    with stack:
        # Degraded (no fcntl, unwritable dir, or a filesystem without advisory locks). Still
        # report progress -- a bar with no mutual exclusion is better than no bar, and the
        # reader surfaces `degraded` separately. The run carries the fact, because the minted
        # id below is NOT in the sentinel and anything that checks it must know that.
        degraded = run_id is None
        if run_id is None:
            run_id = new_run_id()

        def _publish(outcome: str | None, event: ProgressEvent | None = None) -> None:
            _record.write_record(
                target,
                _record.build_record(
                    run_id=run_id,
                    kind=kind.name,
                    intent=_record.INTENT_WRITE,
                    started_at_ms=started_at_ms,
                    outcome=outcome,
                    progress=event.progress_payload() if event is not None else None,
                    stage_ms=(
                        event.stage_ms
                        if (event is not None and outcome == _record.OUTCOME_DONE)
                        else None
                    ),
                ),
            )

        _publish(_record.OUTCOME_RUNNING)

        reporter = ProgressReporter(
            sinks=[s for s in (lambda e: _publish(None, e), sink) if s is not None],
            phases=kind.phases,
            labels=kind.labels,
        )
        run = BuildRun(reporter, run_id, degraded=degraded)

        if not force and is_current is not None:
            with contextlib.suppress(Exception):
                run.skipped = bool(is_current())
        if run.skipped:
            _publish(_record.OUTCOME_SKIPPED)
            yield run
            return

        try:
            yield run
        except BaseException:  # include KeyboardInterrupt/SystemExit: a cancelled run is a failed run
            _publish(_record.OUTCOME_FAILED)
            raise
        reporter.finish()
        _publish(_record.OUTCOME_DONE, _terminal_event(reporter))


def _terminal_event(reporter: ProgressReporter) -> ProgressEvent:
    """A synthetic terminal event carrying the run's measured stage times."""
    return ProgressEvent(
        phase=PHASE_DONE,
        label=PHASE_LABELS[PHASE_DONE],
        index=0,
        count=0,
        done=0,
        total=None,
        determinate=False,
        phase_started_at_ms=time.time() * 1000.0,
        elapsed_ms=0.0,
        stage_ms=reporter.stage_ms_snapshot(),
    )


def require_write_lock(output_dir: Path | str) -> bool:
    """Assert that the caller holds ``output_dir``'s write lock. Returns True when it does.

    The lock used to be taken at CALL SITES, so whether a package write was coordinated
    depended on which of four producers you came through -- and one of them took no lock at
    all, which is how a cold `cad inspect` build became invisible to the viewer and raced a
    viewer-started build into the same directory. This puts the check at the MUTATION
    boundary instead, where it cannot be forgotten by a future producer.

    Raises under ``CADGEN_STRICT_LOCKS=1`` (tests and CI); otherwise warns and continues,
    because a missing lock must never be the reason a user's build fails.
    """
    from cadgen.coordination.lock import locking_available

    if not locking_available():
        return True  # degraded everywhere; nothing to assert
    # We hold it iff acquiring is re-entrant for this thread+path -- the thread-local set
    # in lock.py is the only honest record of "this thread already has it".
    from cadgen.coordination.lock import _HELD  # noqa: PLC2701 - same package

    held = getattr(_HELD, "paths", None) or set()
    if str(write_lock_path(output_dir)) in held:
        return True
    message = (
        f"render package written without holding its generation lock: {output_dir}. "
        "Wrap the write in cadgen.coordination.artifact_build()."
    )
    if os.environ.get("CADGEN_STRICT_LOCKS") == "1":
        raise RuntimeError(message)
    warnings.warn(message, RuntimeWarning, stacklevel=3)
    return False


@contextlib.contextmanager
def generator_busy(
    kind: ArtifactKind,
    output_dir: Path | str | None,
    *,
    deadline_ms: float | None = None,
    on_wait: Callable[[float], None] | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> Iterator[BuildRun | None]:
    """Occupy an artifact's GENERATOR without claiming to rewrite its package.

    An export runs the model's ``gen_step()`` for a minute and writes a file somewhere else
    entirely. Taking the write lock for that made a fully-current model report `generating`
    with an empty bar; taking nothing would let a reader think the generator is free. This
    is the third option, and it is why there are two sentinels.

    Note what this does NOT do: the generator sentinel is a different file from the writer
    sentinel, so ``flock`` cannot make the two exclude each other. A build and an export of
    one model DO run its ``gen_step()`` concurrently, each in its own process. That is
    wasteful but not unsafe -- they share no in-process state and write different outputs.
    What it buys is a state a reader can distinguish: a busy generator does not hide the
    package on disk, and a writer does.

    Its record goes to :func:`generator_status_path`, NOT to the writer's record. Sharing one
    file let this run stomp a live build's progress -- and the two runs cannot exclude each
    other, so there was no lock that would have prevented it.

    Yields a :class:`BuildRun`, exactly as :func:`artifact_build` does, so the work under it
    reports through the same phases. This run does the SAME ``gen_step()`` a build does -- for
    a large assembly that is minutes -- and it used to report nothing at all to either
    surface, because it had no reporter to report through. The only thing that differs is
    where the record lands, and what a reader is entitled to conclude from it: an occupied
    generator does not hide the package on disk.
    """
    if output_dir is None:
        yield None
        return
    started_at_ms = time.time() * 1000.0
    target = generator_status_path(output_dir)
    with exclusive(
        generator_lock_path(output_dir), deadline_ms=deadline_ms, on_wait=on_wait
    ) as run_id:
        # Degraded locking. Still report: a bar with no mutual exclusion beats no bar, and
        # the reader surfaces `degraded` separately.
        degraded = run_id is None
        if run_id is None:
            run_id = new_run_id()

        def _publish(outcome: str | None, event: ProgressEvent | None = None) -> None:
            _record.write_record(
                target,
                _record.build_record(
                    run_id=run_id,
                    kind=kind.name,
                    intent=_record.INTENT_GENERATE,
                    started_at_ms=started_at_ms,
                    outcome=outcome,
                    progress=event.progress_payload() if event is not None else None,
                    stage_ms=(
                        event.stage_ms
                        if (event is not None and outcome == _record.OUTCOME_DONE)
                        else None
                    ),
                ),
            )

        _publish(_record.OUTCOME_RUNNING)
        reporter = ProgressReporter(
            sinks=[s for s in (lambda e: _publish(None, e), sink) if s is not None],
            phases=kind.phases,
            labels=kind.labels,
        )
        run = BuildRun(reporter, run_id, degraded=degraded)
        try:
            yield run
        except BaseException:  # include KeyboardInterrupt/SystemExit: a cancelled run is a failed run
            _publish(_record.OUTCOME_FAILED)
            raise
        reporter.finish()
        _publish(_record.OUTCOME_DONE, _terminal_event(reporter))
