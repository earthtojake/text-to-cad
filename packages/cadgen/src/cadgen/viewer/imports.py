"""Imported-document compiles for the CAD Viewer: jobs in cadgen's pool.

The viewer renders what exists. Its one build-shaped action is importing a raw
FOREIGN ``.step`` — making the document's tree current in the shared store — and
that is a compile JOB submitted to the pool (``cadgen.daemon.executors.
submit_compile``): the same job a door submits when handed an imported document
with no tree. It runs on a daemon spare (or a transient subprocess under
``CADGEN_DAEMON=0``), takes a job slot, coalesces with a door compiling the same
bytes and shows in the build tree. Nothing here loads the kernel; the server
never does.

Concurrent viewer requests for one document attach to the first: one job, one
answer for all of them. Progress reaches the status endpoint through the
advisory progress record the compile publishes (``build_progress``), not
through this module — the job is the producer, this is a waiter.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from .store_paths import build_scope

__all__ = ["ImportCompiler"]

# The last thing a failed compile says, when it is a Python exception line:
# "RuntimeError: failed to read STEP file: ..." -> the bare message plus its class.
_ERROR_LINE = re.compile(r"^(?:[\w.]+\.)?(?P<type>\w+(?:Error|Exception))\s*:\s*(?P<message>.+)$")


class _Import:
    """One in-flight compile that other requests may attach to."""

    __slots__ = ("done", "result")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: dict | None = None


def _failure(output: str, document: str) -> dict:
    """A failed job's answer: the BARE message a person reads, the exception class
    riding alongside as ``errorType`` for a diagnostic, never in the sentence."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        match = _ERROR_LINE.match(line)
        if match:
            return {"ok": False, "error": match.group("message"), "errorType": match.group("type")}
    return {
        "ok": False,
        "error": lines[-1] if lines else f"compiling {os.path.basename(document)} failed",
    }


def _submit(document: Path, *, force: bool):
    from cadgen.daemon.executors import submit_compile

    return submit_compile(document, force=force)


class ImportCompiler:
    """Compile imported documents through the pool; one job per document at a time."""

    def __init__(self, *, submit=None) -> None:
        # `submit(document, force=) -> Job` (wait() -> exit code, output() -> text).
        # Injected by tests; the real one is the pool's submit_compile.
        self._submit = submit or _submit
        self._lock = threading.Lock()
        self._in_flight: dict[str, _Import] = {}

    def shutdown(self) -> None:
        """Nothing to own: the jobs belong to the pool, which outlives the viewer."""

    def compile(self, candidate: str, *, force: bool = False) -> dict:
        """Compile one document, attaching to an in-flight compile for the same one.

        Returns ``{"ok": True, "document": ...}`` or ``{"ok": False, "error": ...}``.
        Never raises for a build failure: a failure is a value.
        """
        build_key = build_scope(candidate)
        # Get-or-create in ONE critical section: a check, then a create, under
        # separate acquisitions would let two request threads each start a job
        # for one document. (The pool would coalesce them, but the second would
        # still hash the file and cross to the daemon for nothing.)
        with self._lock:
            entry = self._in_flight.get(build_key)
            owner = entry is None
            if owner:
                entry = self._in_flight[build_key] = _Import()
        assert entry is not None

        if not owner:
            entry.done.wait()
            return entry.result or {"ok": False, "error": "compile did not report a result"}

        result: dict | None = None
        try:
            result = self._run(candidate, force=force)
        except BaseException as error:  # noqa: BLE001 - a fault is still an answer the waiters are owed
            result = {
                "ok": False,
                "error": str(error).strip() or type(error).__name__,
                "errorType": type(error).__name__,
            }
            raise
        finally:
            with self._lock:
                self._in_flight.pop(build_key, None)
            entry.result = result
            entry.done.set()
        return result

    def in_flight(self, build_key: str) -> bool:
        with self._lock:
            return build_key in self._in_flight

    def _run(self, candidate: str, *, force: bool) -> dict:
        document = Path(candidate).resolve()
        job = self._submit(document, force=force)
        if job.wait() != 0:
            return _failure(job.output(), candidate)
        return {"ok": True, "document": str(document)}
