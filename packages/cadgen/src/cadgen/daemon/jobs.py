"""The daemon's job ledger: every job it runs, whoever asked for it.

One entry per request the supervisor relays — a ``python model.py`` from a
terminal, a parent's child build, a door's or the viewer's compile — with the
job's DECLARED OUTPUT PATHS as metadata (the ``out=`` document and the declared
meshes for a model script, parsed statically; the document itself for a
compile). Readers match jobs to files by those paths and never by source state:
the CAD Viewer shows ``compiling · <phase> n/total`` for any job whose outputs
include the document it displays, ``failed`` with the failure's own reason for a
failed one, and nothing else
(``cadgen.viewer.build_progress``). Finished jobs stay listed for
:data:`RETAIN_SECONDS` so a failure is still visible after the job is gone.

State comes from the ``{"event": …}`` frames the worker streams (the build
tree's own transitions: submitted → queued → building [phase, done/total] →
done | failed) and from the request's exit code. Stdlib only; nothing here
imports the kernel — a job's outputs come from ``cadgen.metadata``'s AST parse.
"""

from __future__ import annotations

import itertools
import copy
import hashlib
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

__all__ = ["JobLedger", "RETAIN_SECONDS", "declared_outputs", "failure_message"]

RETAIN_SECONDS = 120.0
_RUNNING = ("submitted", "queued", "building")

# The two shapes a failed job's stderr ends in: the CLI's own failure line
# (``[cadgen step compile] FAILED: RuntimeError: ...``) or, under --verbose, a raw
# traceback whose last line is ``RuntimeError: ...``.
_CLI_FAILED = re.compile(r"^\[[^\]]+\]\s+FAILED:\s+(?:[\w.]+\.)?(?P<type>\w+)\s*:\s*(?P<message>.+)$")
_EXCEPTION_LINE = re.compile(r"^(?:[\w.]+\.)?(?P<type>\w+(?:Error|Exception))\s*:\s*(?P<message>.+)$")
_CLI_NOISE = re.compile(r"^\[[^\]]+\]\s+(?:re-run with --verbose|\s)")


def failure_message(output: str) -> tuple[str, str | None]:
    """The one line a person reads about a failed job, and the exception class.

    Reads a job's stderr from the end: the CLI's ``[tool] FAILED: Type: message``
    line first, then a traceback's final ``Type: message``, then the last line
    that is not the CLI's own hint or frame listing. Returns ``("", None)`` for
    silence. Pure text; nothing here knows what ran.
    """
    lines = [line.rstrip() for line in str(output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        match = _CLI_FAILED.match(line.strip())
        if match:
            return match.group("message").strip(), match.group("type")
    for line in reversed(lines):
        match = _EXCEPTION_LINE.match(line.strip())
        if match:
            return match.group("message").strip(), match.group("type")
    for line in reversed(lines):
        if not _CLI_NOISE.match(line):
            return line.strip(), None
    return "", None


def _real(path: str | os.PathLike[str]) -> str:
    try:
        return os.path.realpath(str(path))
    except (OSError, ValueError):
        return str(path)


def declared_outputs(subject: str, tool: str) -> list[str]:
    """The output paths a job will write, from its declarations alone.

    A compile (``step-compile``) writes the tree for the document it names — the
    document IS its output. A model script's outputs are its ``out=`` document
    (else the sibling ``<stem>.step`` / ``.dxf``) and every declared mesh export,
    resolved exactly as the build resolves them. Never raises: a script that
    cannot be parsed simply declares nothing.
    """
    if not subject:
        return []
    script_ref, _, function = subject.partition("::")
    if not script_ref.endswith(".py"):
        return [_real(subject)]
    try:
        from cadgen.metadata import declared_output_paths

        paths = declared_output_paths(Path(script_ref), function=function or None)
        return list(dict.fromkeys(_real(path) for path in paths))
    except Exception:  # noqa: BLE001 - metadata is best-effort; a job still runs
        return []


class JobLedger:
    """Thread-safe: the relay threads write, status requests read."""

    def __init__(self, *, retain_seconds: float = RETAIN_SECONDS, clock=time.time) -> None:
        self._guard = threading.Lock()
        self._changed = threading.Condition(self._guard)
        self._revision = 0
        self._jobs: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._retain = float(retain_seconds)
        self._clock = clock
        self.epoch = uuid.uuid4().hex

    # --- lifecycle -------------------------------------------------------------

    def start(self, *, tool: str, subject: str, argv: list[str] | None = None, store_root: str = "",
              editing_producer: bool = True, adopt_announced: bool = False) -> dict[str, Any]:
        if tool == "artifact":
            subject, editing_producer = "", False
        subject = _real(subject) if subject else ""
        now = self._clock()
        sequence = next(self._ids)
        job: dict[str, Any] = {
            "id": f"{self.epoch}:job-{sequence}",
            "epoch": self.epoch,
            "sequence": sequence,
            "storeRoot": _real(store_root) if store_root else "",
            "tool": str(tool),
            "editingProducer": bool(editing_producer),
            "subject": subject,
            "outputs": [] if tool == "artifact" else declared_outputs(subject, str(tool)),
            "argv": [str(a) for a in (argv or [])],
            "state": "submitted",
            "phase": None,
            "detail": "",
            "done": None,
            "total": None,
            "startedAt": now,
            "updatedAt": now,
            "finishedAt": None,
            "exit": None,
            "error": None,
        }
        with self._guard:
            if adopt_announced and subject:
                # A concurrent real request for the same model must not hide
                # the child's earlier announcement.  If it does, that
                # announcement is never adopted or finished and remains a
                # permanently submitted Viewer progress row.
                existing = self._announced_for(subject)
                if existing is not None:
                    existing["tool"] = str(tool)
                    existing["argv"] = [str(a) for a in (argv or [])]
                    existing["storeRoot"] = job["storeRoot"]
                    existing["editingProducer"] = bool(editing_producer)
                    # Announcements are hints that a request is coming, not
                    # accepted editing revisions.  Order the adopted row by
                    # this request's actual acceptance.
                    existing["sequence"] = sequence
                    existing["startedAt"] = now
                    existing["updatedAt"] = now
                    existing.pop("announced", None)
                    self._notify(existing)
                    return existing
            self._jobs[job["id"]] = job
            self._notify(job)
        return job

    def start_artifact(self, request: dict, *, store_root: str, root_id=None, dependency=False) -> dict[str, Any]:
        job = self.start(tool="artifact", subject="", store_root=store_root, editing_producer=False)
        with self._guard:
            job["artifact"] = copy.deepcopy(request)
            job["rootId"] = root_id
            job["dependency"] = bool(dependency)
            self._notify(job)
        return job

    def record_artifact_result(self, job: dict[str, Any], result: dict) -> None:
        with self._guard:
            if job["tool"] == "artifact" and job.get("artifactResult") is None:
                job["artifactResult"] = copy.deepcopy(result)
                job["updatedAt"] = self._clock()
                self._notify(job)

    def accept_editing_producer(self, job: dict[str, Any]) -> None:
        """Only a coalescing request that owns the work advances edit ordering."""
        with self._guard:
            job["editingProducer"] = True
            self._notify(job)

    def observe(self, frame: dict[str, Any]) -> None:
        """Fold one relayed frame into the ledger (only ``event`` frames matter)."""
        event = frame.get("event") if isinstance(frame, dict) else None
        if not isinstance(event, dict):
            return
        model = _real(str(event.get("model") or ""))
        state = str(event.get("state") or "")
        if not model or not state:
            return
        now = self._clock()
        producer = str(event.get("job") or "")
        with self._guard:
            job = self._jobs.get(producer) if producer else self._running_for(model)
            if producer:
                if job is None or _real(model.split("::", 1)[0]) != _real(job["subject"].split("::", 1)[0]):
                    # Parent-announced child transitions are not the parent's
                    # own work. The child's accepted request has its own row.
                    return
                ordinal = int(event.get("sequence") or 0)
                if job.get("finishedAt") is not None or (ordinal and ordinal <= job.get("eventSequence", 0)):
                    return
                if ordinal:
                    job["eventSequence"] = ordinal
            if job is None:
                if state in ("done", "failed", "current"):
                    return  # a transition for a job this ledger never saw start
                # A child a parent has submitted: its own request has not
                # arrived yet, so it is listed from the parent's announcement.
                sequence = next(self._ids)
                job = {
                    "id": f"{self.epoch}:job-{sequence}", "epoch": self.epoch,
                    "sequence": sequence, "storeRoot": "", "announced": True,
                    "tool": "run", "subject": model,
                    "outputs": declared_outputs(model, "run"), "argv": [], "state": "submitted",
                    "phase": None, "detail": "", "done": None, "total": None, "startedAt": now,
                    "updatedAt": now, "finishedAt": None, "exit": None, "error": None,
                }
                self._jobs[job["id"]] = job
            if state in ("submitted", "queued"):
                if job["state"] == "submitted" or state == "queued":
                    job["state"] = state
            elif state == "building":
                job["state"] = "building"
                job["phase"] = event.get("phase") or job["phase"]
                if event.get("detail") is not None:
                    job["detail"] = str(event.get("detail") or "")
                job["done"] = event.get("done")
                job["total"] = event.get("total")
            elif state in ("done", "current"):
                # A real request may run several decorated models; only its
                # process completion closes the request, not one model event.
                if not producer:
                    job["state"] = "done"
                    job["finishedAt"] = now
            elif state == "failed":
                job["state"] = "failed"
                job["exit"] = event.get("exit", job["exit"])
                if event.get("error"):
                    job["error"] = str(event["error"])
                job["finishedAt"] = now
            result = event.get("sourceResult")
            if isinstance(result, dict) and result.get("model") and result.get("tree"):
                job.setdefault("sourceResults", {}).setdefault(str(result["model"]), copy.deepcopy(result))
            for field in ("preview", "saved"):
                payload = event.get(field)
                if not isinstance(payload, dict) or not payload.get("output") or not payload.get("tree"):
                    continue
                output = _real(str(payload["output"]))
                updates = job.setdefault("previews" if field == "preview" else "savedResults", {})
                ordinal = int(event.get("sequence") or 0)
                previous = updates.get(output)
                if previous is None or ordinal > int(previous.get("sequence") or 0):
                    updates[output] = {**copy.deepcopy(payload), "output": output, "sequence": ordinal}
                if output not in job["outputs"]:
                    job["outputs"].append(output)
            job["updatedAt"] = now
            self._notify(job)

    def finish(self, job: dict[str, Any], exit_code: int, *, error: str | None = None) -> None:
        """Close the job. ``error`` is the failure's one-line reason (see
        :func:`failure_message`), kept so a reader can say WHY, not just that."""
        now = self._clock()
        with self._guard:
            if job["state"] in _RUNNING:
                job["state"] = "done" if exit_code == 0 else "failed"
            job["exit"] = int(exit_code)
            if exit_code != 0 and error:
                job["error"] = str(error)
            job["finishedAt"] = job["finishedAt"] or now
            job["updatedAt"] = now
            self._sweep(now)
            self._notify(job)

    # --- reading -----------------------------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        """Every running job and every job finished within the retention window."""
        with self._guard:
            self._sweep(self._clock())
            return copy.deepcopy(list(self._jobs.values()))

    def watch(self, after: str | None = None, *, timeout: float = 1.0,
              output: str | None = None, store_root: str | None = None) -> dict:
        """Wait for a ledger change without occupying a kernel worker.

        Cursor and snapshot are captured under the same lock. The epoch makes
        an old daemon's cursor immediately expire after restart. A bounded
        heartbeat also exposes retained-job expiry and lets document readers
        revalidate saved bytes and missing objects without a new build event.
        """
        deadline = time.monotonic() + max(0.0, min(float(timeout), 1.0))
        normalized_output = _real(output) if output and store_root else ""
        normalized_store = _real(store_root) if output and store_root else ""

        def selected() -> list[dict[str, Any]]:
            if not normalized_output or not normalized_store:
                return list(self._jobs.values())
            return [
                job for job in self._jobs.values()
                if job.get("tool") == "run"
                and job.get("editingProducer", True)
                and job.get("storeRoot") and _real(job["storeRoot"]) == normalized_store
                and normalized_output in {_real(path) for path in job.get("outputs", [])}
            ]

        def cursor(jobs: list[dict[str, Any]]) -> str:
            if not normalized_output or not normalized_store:
                return f"{self.epoch}:{self._revision}"
            digest = hashlib.sha256()
            for value in (self.epoch, normalized_output, normalized_store):
                digest.update(value.encode("utf-8", errors="surrogatepass"))
                digest.update(b"\0")
            for job in jobs:
                digest.update(str(job.get("id") or "").encode("utf-8", errors="surrogatepass"))
                digest.update(b"\0")
                digest.update(str(int(job.get("ledgerRevision") or 0)).encode("ascii"))
                digest.update(b"\0")
            return f"{self.epoch}:scope:{digest.hexdigest()}"

        with self._changed:
            self._sweep(self._clock())
            jobs = selected()
            jobs_cursor = cursor(jobs)
            while after == jobs_cursor:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._changed.wait(remaining)
                self._sweep(self._clock())
                jobs = selected()
                jobs_cursor = cursor(jobs)
            return {"jobsCursor": jobs_cursor, "jobs": copy.deepcopy(jobs)}

    def _notify(self, job: dict[str, Any] | None = None) -> None:
        """Called with the ledger lock held; no event history is retained."""
        self._revision += 1
        if job is not None:
            job["ledgerRevision"] = self._revision
        self._changed.notify_all()

    def _running_for(self, subject: str, *, exclude: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for job in reversed(list(self._jobs.values())):
            if job is not exclude and job["subject"] == subject and job["state"] in _RUNNING:
                return job
        return None

    def _announced_for(self, subject: str) -> dict[str, Any] | None:
        for job in reversed(list(self._jobs.values())):
            if job["subject"] == subject and job["state"] in _RUNNING and job.get("announced"):
                return job
        return None

    def _sweep(self, now: float) -> None:
        for key, job in list(self._jobs.items()):
            finished = job.get("finishedAt")
            if finished is not None and now - finished > self._retain:
                self._jobs.pop(key, None)
                self._notify()
