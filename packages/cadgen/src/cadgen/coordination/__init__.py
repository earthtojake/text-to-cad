"""Build progress: how a run narrates its phases, in process and on disk.

There is NO lock here. Two builds of one model may run at once; the store's publish
rule (``cadgen.store.publish``) decides which result the model's record points at,
and every write under the store is atomic, so concurrent builds produce two valid
results and one pointer — never a torn one (STORE.md §7). What this package owns is
narration: the phase a build is in, how far through it is, and the advisory record
of that on disk for readers in other processes (the CAD Viewer's progress badge).

**stdlib only.** The viewer's long-lived server process imports this module, and it must
never drag OCP/build123d/ezdxf into that process. ``cadgen/__init__.py`` defers all of its
own imports, so ``import cadgen.coordination`` costs milliseconds and pulls in no CAD
runtime. That invariant is pinned by
``tests/python/packages/cadgen/test_coordination_is_stdlib_only.py``; do not add a
non-stdlib import here or to any module in this package.

Producer::

    with artifact_build(STEP_PACKAGE, build_scope(model),
                        is_current=lambda: model_is_current(spec),
                        force=force) as run:
        if run.skipped:                 # is_current() answered yes
            return existing_payload()
        run.phase(PHASE_COMPONENTS, total=len(work))  # a phase that can count
        run.advance(detail=name)
        run.phase(PHASE_GENERATE)                     # a phase that cannot
        run.detail("airframe")

Reader (the viewer)::

    record = read_record(progress_path(scope))   # advisory; stale after a crash
"""

from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

from cadgen.coordination import record as _record
from cadgen.coordination.kinds import (
    DRAWING_PACKAGE,
    PHASE_BROWSER,
    PHASE_CHECK,
    PHASE_COLLECT,
    PHASE_RENDER,
    SNAPSHOT,
    STEP_PACKAGE,
    VALIDATION,
    ArtifactKind,
)
from cadgen.coordination.paths import generator_progress_path, progress_path
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
    "DRAWING_PACKAGE",
    "PHASE_BROWSER",
    "PHASE_CHECK",
    "PHASE_COLLECT",
    "PHASE_RENDER",
    "SNAPSHOT",
    "VALIDATION",
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
    "artifact_build",
    "current_build",
    "generator_busy",
    "generator_progress_path",
    "new_run_id",
    "progress_path",
    "render_progress_bar",
    "reporting_as",
    "resolve",
]


def new_run_id() -> str:
    """One id per run: the viewer resets its bar when it changes, because a ratio is
    monotonic only within a run."""
    return uuid.uuid4().hex


# --- producer ----------------------------------------------------------------------


class BuildRun:
    """The producer's handle inside :func:`artifact_build`.

    Forwards the :class:`ProgressReporter` API, so build code reports through the same
    object that owns the run's record.
    """

    __slots__ = ("_reporter", "run_id", "skipped")

    def __init__(self, reporter: Any, run_id: str | None) -> None:
        self._reporter = reporter
        self.run_id = run_id
        # ``skipped``: the artifact was already current when the run opened, so there is
        # nothing to write. Not an error.
        self.skipped = False

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


# The run reporting on this thread, for code that is too far from `artifact_build` to be
# handed it. `run_node_builder` solves the same problem across a PIPE -- the Node child
# describes its work and the parent publishes it -- and this is the in-process twin: a
# model's entry is called with no arguments and cannot be given the BuildRun, so it looks
# the run up instead. A ContextVar rather than a global because the viewer's warm worker
# is long-lived and must never leak one build's reporter into another's.
_CURRENT_BUILD: contextvars.ContextVar[BuildRun | None] = contextvars.ContextVar(
    "cadgen_current_build", default=None
)


def current_build() -> BuildRun | None:
    """The :class:`BuildRun` reporting for the work on this thread, or None outside a build.

    Callers report through it and must never assume it exists: the same generator runs under
    the CLI, the viewer's worker, a test harness, and a plain `python model.py`.
    """
    return _CURRENT_BUILD.get()


@contextlib.contextmanager
def reporting_as(run: BuildRun | None) -> Iterator[None]:
    """Make ``run`` the :func:`current_build` for the duration of the block.

    Nested binds are IGNORED: a model that composes children would otherwise have a
    child's loop retarget the parent's phase, and the outermost loop is the one whose
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
def _reported_run(
    kind: ArtifactKind,
    target: Path,
    intent: str,
    *,
    is_current: Callable[[], bool] | None,
    force: bool,
    sink: Callable[[ProgressEvent], None] | None,
) -> Iterator[BuildRun]:
    """One run's record lifecycle: ``starting`` before any work, phases as they happen,
    ``done`` WITH the run's stage times or ``failed`` WITHOUT them, so a failed run cannot
    teach the next build's bar."""
    started_at_ms = time.time() * 1000.0
    run_id = new_run_id()

    def _publish(outcome: str | None, event: ProgressEvent | None = None) -> None:
        _record.write_record(
            target,
            _record.build_record(
                run_id=run_id,
                kind=kind.name,
                intent=intent,
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
    run = BuildRun(reporter, run_id)

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


@contextlib.contextmanager
def artifact_build(
    kind: ArtifactKind,
    scope: str | None,
    *,
    is_current: Callable[[], bool] | None = None,
    force: bool = False,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> Iterator[BuildRun]:
    """Report a run that REWRITES a model's outputs.

    ``scope`` is the model's build scope (``cadgen.catalog.build_scope``: a name derived
    from the model path, known before any geometry is). None means a producer with no
    coordinated output: ``is_current`` is still answered -- freshness is not a reporting
    question -- but nothing is recorded.

    ``force=True`` skips only the ``is_current()`` call.
    """
    if scope is None:
        run = BuildRun(NULL_PROGRESS, None)
        if not force and is_current is not None:
            with contextlib.suppress(Exception):
                run.skipped = bool(is_current())
        yield run
        return
    with _reported_run(
        kind, progress_path(scope), _record.INTENT_WRITE,
        is_current=is_current, force=force, sink=sink,
    ) as run:
        yield run


@contextlib.contextmanager
def generator_busy(
    kind: ArtifactKind,
    scope: str | None,
    *,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> Iterator[BuildRun | None]:
    """Report a run that occupies a model's GENERATOR without rewriting its outputs.

    An export runs the model's ``@step`` entry for a minute and writes a file somewhere else
    entirely. Its record goes to :func:`generator_progress_path`, NOT to the writer's record:
    sharing one file let an export stomp a live build's progress, and its terminal record
    carries no ``stageMs`` that would erase the phase weighting the next build reads.

    Yields a :class:`BuildRun`, exactly as :func:`artifact_build` does, so the work under it
    reports through the same phases. None when there is no scope to report under.
    """
    if scope is None:
        yield None
        return
    with _reported_run(
        kind, generator_progress_path(scope), _record.INTENT_GENERATE,
        is_current=None, force=True, sink=sink,
    ) as run:
        yield run


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
