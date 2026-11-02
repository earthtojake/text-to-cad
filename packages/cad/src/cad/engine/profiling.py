"""Bounded, in-memory function timings of actual build execution, including cache hits."""

from __future__ import annotations

import contextlib
import cProfile
import os
import pstats
import threading
import time
from pathlib import Path
from typing import Any

LIMIT = 20

# cProfile records every thread's calls on one stack (Python 3.12+ profiles through sys.monitoring,
# which is the interpreter's, not a thread's): a call another thread makes while a build is profiled is
# booked against the build's frames, and a function then shows more self time than cumulative time --
# 0.0 cumulative beside 0.12 s self, once. So while a profile records, the worker's own other threads
# (its progress throttle, its request reader) wait at ``quiet`` before they run any Python, and the
# kernel's load notice (``worker.kernel``) is joined before a build starts.
_RECORDING = threading.RLock()  # a profiled build inside a profiled build (one thread) records on


@contextlib.contextmanager
def quiet():
    """Around Python work a thread other than the build's does: held off while a profile records.
    Taken before any other lock the work takes, so it never waits holding one the build needs."""
    with _RECORDING:
        yield


class Profile:
    """A class context manager: enabling in a generator introduces an unmatched return.

    builtins=False also matters: pybind11 returns can otherwise pop Python frames
    cProfile never pushed (Python 3.12+). Native time belongs to its Python caller. It records
    with the worker's other threads held at ``quiet``; a caller's own threads in an in-process
    build are the caller's to keep still.
    """

    def __init__(self, *, project: Path) -> None:
        self.project = project.resolve()
        self.profiler = cProfile.Profile(builtins=False)
        self.started = 0.0
        self.seconds = 0.0

    def __enter__(self) -> Profile:
        _RECORDING.acquire()
        self.started = time.perf_counter()
        self.profiler.enable()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.profiler.disable()
        self.seconds = time.perf_counter() - self.started
        _RECORDING.release()

    def report(self) -> dict[str, Any]:
        rows = []
        project_rows = []
        for (filename, line, function), (primitive, calls, own, cumulative, _callers) in pstats.Stats(self.profiler).stats.items():
            if filename == __file__:
                continue
            row = {"file": filename, "line": line, "function": function, "calls": calls,
                   "primitive_calls": primitive, "self_seconds": own, "cumulative_seconds": cumulative}
            rows.append(row)
            path = Path(filename)
            if path.is_relative_to(self.project) and not {"site-packages", "dist-packages"}.intersection(path.parts):
                project_rows.append(row)
        # Tie-break by location so equal timings have a deterministic presentation.
        def ranked(items: list, key: str) -> list:
            return sorted(items, key=lambda row: (-row[key], row["file"], row["line"], row["function"]))[:LIMIT]

        return {"scope": "build_request", "mode": "actual_execution", "process": os.getpid(),
                "builtins": False, "seconds": self.seconds,
                "self_seconds": sum(row["self_seconds"] for row in rows), "function_count": len(rows),
                "limit": LIMIT, "project_cumulative": ranked(project_rows, "cumulative_seconds"),
                "top_self": ranked(rows, "self_seconds")}


def describe(profile: dict[str, Any]) -> str:
    """Human mirror of the report's two bounded tables, with scope and cache semantics."""
    lines = [f"  profile: actual build request, {profile['seconds']:.3f}s; cache hits preserved",
             "    cProfile adds overhead; native time is included in the calling Python function."]
    lines.append("    Replayed bodies and memo hits contain no timings for the work they skipped.")
    for title, field, seconds in (("project functions by cumulative time", "project_cumulative", "cumulative_seconds"),
                                  ("all functions by self time", "top_self", "self_seconds")):
        lines.append(f"    {title} (up to {profile['limit']}):")
        for row in profile[field]:
            lines.append(f"      {row[seconds]:9.4f}s  {row['calls']:8} calls  "
                         f"{row['file']}:{row['line']} {row['function']}")
        if not profile[field]:
            lines.append("      (none executed)")
    return "\n".join(lines)
