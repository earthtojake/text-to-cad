"""Where a model build's time went: the model's own code, or cadgen.

A build is two programs taking turns: the model's body (the decorated function and
everything it calls) and cadgen (loading the script, storing parts, writing the
document and its meshes). An agent that watches a build slow from two minutes to
fifteen cannot tell which of them grew unless the build says so, and it keeps
editing the wrong one. So every build that runs measures the split, and the root of
the build prints it once per model built (``cadgen.cli_tree``).

How the split is measured, on the thread that runs the build:

* ``model code`` is the wall time of the decorated function's call, minus the
  windows inside it where cadgen worked for it: waiting for a child model's build
  (``waiting_for_children``) and loading a finished child's geometry from the
  store (``cadgen_work``). Module import is not in it: loading the script is
  cadgen's, and on a cold run it is mostly the CAD kernel's own import.
* ``waiting on children`` is every wait for a child's build, in the body or after
  it (a parent owes its children's outputs before it is done). Each child prints
  its own line.
* ``queued`` is the wait for a build slot before the body could start.
* ``cadgen`` is the rest of the build's wall time.

``--profile`` runs cProfile over exactly the model-code windows and reports the
functions the time went to. Stdlib only: the root process imports this to print,
and the root must stay light.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

#: A slowdown is worth a warning when the model code took more than this many times
#: its last build's AND at least ``SLOWDOWN_MIN_SECONDS`` more: the ratio alone fires
#: on a 0.1 s model that took 0.3 s, the difference alone on noise in a long one.
SLOWDOWN_RATIO = 2.0
SLOWDOWN_MIN_SECONDS = 30.0

_PROJECT_ROWS = 12
_OVERALL_ROWS = 8
_LOCAL = threading.local()


def format_duration(seconds: float) -> str:
    """``820ms``, ``14.2s``, ``9m42s``, ``1h05m``: short enough for one line."""
    seconds = max(0.0, float(seconds))
    if round(seconds * 1000) < 1000:
        return f"{round(seconds * 1000)}ms"
    if round(seconds, 1) < 60:
        return f"{seconds:.1f}s"
    whole = int(round(seconds))
    if whole < 3600:
        return f"{whole // 60}m{whole % 60:02d}s"
    return f"{whole // 3600}h{(whole % 3600) // 60:02d}m"


@dataclass(frozen=True)
class BuildTimings:
    """What one build's wall time was spent on, in seconds."""

    seconds: float
    model: float
    children: float
    queued: float

    @property
    def cadgen(self) -> float:
        return max(0.0, self.seconds - self.model - self.children - self.queued)

    def payload(self) -> dict[str, float]:
        """The ``timings`` object a ``--json`` result and the build tree's ``done``
        line carry."""
        return {
            "seconds": round(self.seconds, 3),
            "modelSeconds": round(self.model, 3),
            "cadgenSeconds": round(self.cadgen, 3),
            "childrenSeconds": round(self.children, 3),
            "queuedSeconds": round(self.queued, 3),
        }


def time_line(document: str, timings: dict[str, Any]) -> str:
    """``built STEP/robot.step in 9m42s: model code 8m20s, cadgen 1m22s``."""
    parts = [
        f"model code {format_duration(timings.get('modelSeconds') or 0.0)}",
        f"cadgen {format_duration(timings.get('cadgenSeconds') or 0.0)}",
    ]
    children = float(timings.get("childrenSeconds") or 0.0)
    if children >= 0.05:
        parts.append(f"waiting on children {format_duration(children)}")
    queued = float(timings.get("queuedSeconds") or 0.0)
    if queued >= 0.05:
        parts.append(f"queued for a build slot {format_duration(queued)}")
    return f"built {document} in {format_duration(timings.get('seconds') or 0.0)}: {', '.join(parts)}"


def slowdown_warning(name: str, model_seconds: float, last_seconds: float | None) -> str | None:
    """The warning for a model whose own code got much slower than its last build's,
    or None. No previous time (a first build, a record from before cadgen kept one)
    is never a slowdown."""
    if last_seconds is None or last_seconds <= 0:
        return None
    if model_seconds <= SLOWDOWN_RATIO * last_seconds or model_seconds - last_seconds < SLOWDOWN_MIN_SECONDS:
        return None
    return (
        f"warning: {name}'s model code took {format_duration(model_seconds)}, "
        f"{model_seconds / last_seconds:.1f}x its last build ({format_duration(last_seconds)}); "
        "the time is in the model script, not cadgen. Rerun with --profile to see where."
    )


# --- measuring ---------------------------------------------------------------------------


class BuildClock:
    """One build's measurements, owned by the thread that runs it."""

    def __init__(self, *, model_ref: str | None, last_model_seconds: float | None, profile: bool) -> None:
        self.started = time.perf_counter()
        self.model_ref = model_ref
        self.last_model_seconds = last_model_seconds
        self.profile = bool(profile)
        self.body_seconds = 0.0
        self.body_measured = False
        self.excluded = 0.0
        self.children = 0.0
        self.queued = 0.0
        self.profile_report: str | None = None
        self._in_body = 0
        self._paused = 0

    @property
    def model_seconds(self) -> float:
        return max(0.0, self.body_seconds - self.excluded)

    def timings(self) -> BuildTimings:
        return BuildTimings(
            seconds=time.perf_counter() - self.started,
            model=self.model_seconds,
            children=self.children,
            queued=self.queued,
        )


def current() -> BuildClock | None:
    stack = getattr(_LOCAL, "clocks", None)
    return stack[-1] if stack else None


def record_fields() -> dict[str, float]:
    """What a model's record remembers of this build: its model-code time, which the
    next build compares itself against (``slowdown_warning``). Empty when the body
    was not measured on this thread. A profiled build keeps the last unprofiled
    time: cProfile's overhead is not the model's."""
    clock = current()
    if clock is None or not clock.body_measured:
        return {}
    if clock.profile:
        # A profiled body ran slower than the model does: keep the last real time.
        return {"modelSeconds": clock.last_model_seconds} if clock.last_model_seconds else {}
    return {"modelSeconds": round(clock.model_seconds, 3)}


@contextlib.contextmanager
def measuring(*, model_ref: str | None, last_model_seconds: float | None, profile: bool = False) -> Iterator[BuildClock]:
    """Measure the build that runs in the block, on this thread."""
    stack = getattr(_LOCAL, "clocks", None)
    if stack is None:
        stack = _LOCAL.clocks = []
    clock = BuildClock(model_ref=model_ref, last_model_seconds=last_model_seconds, profile=profile)
    stack.append(clock)
    try:
        yield clock
    finally:
        stack.pop()


class model_body:
    """The decorated function's call. Times it and, under ``--profile``, profiles it.

    A class, not a generator: cProfile pairs every return with the newest call it
    saw, and a generator's yield right after ``enable()`` would be a return it never
    saw the call of."""

    def __init__(self, project: Path | None) -> None:
        self._project = project
        self._clock: BuildClock | None = None
        self._profiler: Any = None
        self._started = 0.0

    def __enter__(self) -> None:
        clock = current()
        if clock is None or clock._in_body:
            return
        self._clock = clock
        clock._in_body += 1
        if clock.profile:
            import cProfile

            # builtins=False: C functions are not entries of their own, so the time a
            # model spends in OCCT counts in the Python function that called it (the
            # build123d method, or the model's own). It is also what keeps the profile
            # true: since Python 3.12 cProfile pairs a pybind11 method's return with a
            # call it never pushed, popping the model's own frames off its stack.
            profiler = cProfile.Profile(builtins=False)
            try:
                profiler.enable()
                self._profiler = profiler
            except ValueError as exc:
                # One profiler per process (Python 3.12+ profiles through
                # sys.monitoring): a coverage run or another profiled build holds it.
                clock.profile_report = f"profile unavailable: {exc}"
        self._started = time.perf_counter()

    def __exit__(self, *exc_info: object) -> None:
        clock = self._clock
        if clock is None:
            return
        elapsed = time.perf_counter() - self._started
        if self._profiler is not None:
            self._profiler.disable()
        clock.body_seconds += elapsed
        clock.body_measured = True
        clock._in_body -= 1
        if self._profiler is not None:
            clock.profile_report = profile_report(
                self._profiler, project=self._project, body_seconds=elapsed,
                model_seconds=clock.model_seconds,
            )


@contextlib.contextmanager
def _paused(kind: str) -> Iterator[None]:
    clock = current()
    if clock is None:
        yield
        return
    outermost = clock._paused == 0
    clock._paused += 1
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        clock._paused -= 1
        if kind == "children":
            clock.children += elapsed
        if outermost and clock._in_body:
            clock.excluded += elapsed


def waiting_for_children() -> contextlib.AbstractContextManager[None]:
    """A wait for a child model's build: neither model code nor cadgen's own work."""
    return _paused("children")


def cadgen_work() -> contextlib.AbstractContextManager[None]:
    """cadgen working inside the body on its behalf (loading a child's geometry)."""
    return _paused("cadgen")


# --- the profile report ----------------------------------------------------------------


def _within(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return not any(part in {"site-packages", "dist-packages"} for part in relative.parts)


def _where(filename: str, line: int, name: str, project: Path | None) -> str:
    if filename == "~" or not filename:
        return name  # a builtin: cProfile already names it ("<built-in method …>")
    path = Path(filename)
    if project is not None and _within(path, project):
        shown = path.relative_to(project).as_posix()
    elif "site-packages" in path.parts:
        shown = "/".join(path.parts[len(path.parts) - path.parts[::-1].index("site-packages"):])
    else:
        shown = path.name
    return f"{shown}:{line} {name}"


def _row(where: str, calls: int, seconds: float) -> str:
    return f"    {format_duration(seconds):>7}  {calls:>8} call{'s' if calls != 1 else ' '}  {where}"


def profile_report(profiler: Any, *, project: Path | None, body_seconds: float, model_seconds: float) -> str:
    """The compact report ``--profile`` prints: where the body's time went.

    The profile covers the whole call of the decorated function, so a body that
    waited for a child shows the wait where it happened (in cadgen's lazy child,
    named in the overall list); the header says how much of the call that was."""
    import pstats

    stats = pstats.Stats(profiler).stats  # {(file, line, name): (cc, nc, tt, ct, callers)}
    project = project.resolve() if project is not None else None
    here = str(Path(__file__).resolve())
    rows = [
        (filename, line, name, int(nc), float(tt), float(ct))
        for (filename, line, name), (_cc, nc, tt, ct, _callers) in stats.items()
        # The profiler's own switching, not the model's.
        if filename != here and not name.startswith("<method 'disable' of '_lsprof.Profiler'")
    ]
    own_total = sum(row[4] for row in rows)
    in_project = sorted(
        (row for row in rows if project is not None and row[0] not in ("~", "") and _within(Path(row[0]), project)),
        key=lambda row: row[5], reverse=True,
    )
    by_own = sorted(rows, key=lambda row: row[4], reverse=True)[:_OVERALL_ROWS]
    waited = body_seconds - model_seconds
    header = f"profile of the model code ({format_duration(body_seconds)}"
    if waited >= 0.05:
        header += f", of which {format_duration(waited)} waiting on or loading child models"
    lines = [
        header + "; cProfile slows Python-call-heavy code, so read shares, not absolute times):",
        "  in this project, by cumulative time:",
    ]
    if in_project:
        lines += [
            _row(_where(f, ln, n, project), calls, ct) for f, ln, n, calls, _tt, ct in in_project[:_PROJECT_ROWS]
        ]
    else:
        lines.append("    (no function in the model's folder ran)")
    lines.append("  everywhere, by own time:")
    lines += [_row(_where(f, ln, n, project), calls, tt) for f, ln, n, calls, tt, _ct in by_own]
    listed = sum(row[4] for row in by_own)
    share = (listed / own_total * 100.0) if own_total > 0 else 0.0
    lines.append(
        f"  those {len(by_own)} functions account for {share:.0f}% of the profiled time "
        f"({format_duration(listed)} of {format_duration(own_total)})"
    )
    return "\n".join(lines)
