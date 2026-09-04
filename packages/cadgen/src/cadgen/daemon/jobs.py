"""The daemon's job ledger: every job it runs, whoever asked for it.

One entry per request the supervisor relays — a ``python model.py`` from a
terminal, a parent's child build, a door's or the viewer's compile — with the
job's DECLARED OUTPUT PATHS as metadata (the ``out=`` document and the declared
meshes for a model script, parsed statically; the document itself for a
compile). Readers match jobs to files by those paths and never by source state:
the CAD Viewer shows ``compiling · <phase> n/total`` for any job whose outputs
include the document it displays, ``failed`` for a failed one, and nothing else
(``cadgen.viewer.build_progress``). Finished jobs stay listed for
:data:`RETAIN_SECONDS` so a failure is still visible after the job is gone.

State comes from the ``{"event": …}`` frames the worker streams (the build
tree's own transitions: submitted → queued → building [phase, done/total] →
done | failed) and from the request's exit code. Stdlib only; nothing here
imports the kernel — a job's outputs come from ``cadgen.metadata``'s AST parse.
"""

from __future__ import annotations

import itertools
import os
import threading
import time
from pathlib import Path
from typing import Any

__all__ = ["JobLedger", "RETAIN_SECONDS", "declared_outputs"]

RETAIN_SECONDS = 120.0
_RUNNING = ("submitted", "queued", "building")


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
    if not subject.endswith(".py"):
        return [_real(subject)]
    try:
        from cadgen.metadata import parse_generator_metadata, resolve_model_output_path

        script = Path(subject)
        metadata = parse_generator_metadata(script)
        if metadata is None:
            return []
        fmt = "dxf" if str(getattr(metadata, "format", "step") or "step") == "dxf" else "step"
        primary = resolve_model_output_path(script, fmt=fmt, explicit_out=metadata.out_target)
        outputs: list[str] = []
        if fmt == "dxf" or getattr(metadata, "step_output", True):
            outputs.append(_real(primary))
        suffixes = {"stl": ".stl", "3mf": ".3mf", "glb": ".glb"}
        for decl in getattr(metadata, "mesh_exports", ()) or ():
            if decl.out is not None:
                path = resolve_model_output_path(script, fmt=decl.fmt, explicit_out=decl.out)
            else:
                path = primary.with_suffix(suffixes.get(decl.fmt, f".{decl.fmt}"))
            outputs.append(_real(path))
        return outputs
    except Exception:  # noqa: BLE001 - metadata is best-effort; a job still runs
        return []


class JobLedger:
    """Thread-safe: the relay threads write, status requests read."""

    def __init__(self, *, retain_seconds: float = RETAIN_SECONDS, clock=time.time) -> None:
        self._guard = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._retain = float(retain_seconds)
        self._clock = clock

    # --- lifecycle -------------------------------------------------------------

    def start(self, *, tool: str, subject: str, argv: list[str] | None = None) -> dict[str, Any]:
        subject = _real(subject) if subject else ""
        now = self._clock()
        job: dict[str, Any] = {
            "id": f"job-{next(self._ids)}",
            "tool": str(tool),
            "subject": subject,
            "outputs": declared_outputs(subject, str(tool)),
            "argv": [str(a) for a in (argv or [])],
            "state": "submitted",
            "phase": None,
            "done": None,
            "total": None,
            "startedAt": now,
            "updatedAt": now,
            "finishedAt": None,
            "exit": None,
        }
        with self._guard:
            self._jobs[job["id"]] = job
        return job

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
        with self._guard:
            job = self._running_for(model)
            if job is None:
                if state in ("done", "failed", "current"):
                    return  # a transition for a job this ledger never saw start
                # A child a parent has submitted: its own request has not
                # arrived yet, so it is listed from the parent's announcement.
                job = {
                    "id": f"job-{next(self._ids)}", "tool": "run", "subject": model,
                    "outputs": declared_outputs(model, "run"), "argv": [], "state": "submitted",
                    "phase": None, "done": None, "total": None, "startedAt": now,
                    "updatedAt": now, "finishedAt": None, "exit": None,
                }
                self._jobs[job["id"]] = job
            if state in ("submitted", "queued"):
                if job["state"] == "submitted" or state == "queued":
                    job["state"] = state
            elif state == "building":
                job["state"] = "building"
                job["phase"] = event.get("phase") or job["phase"]
                job["done"] = event.get("done")
                job["total"] = event.get("total")
            elif state in ("done", "current"):
                job["state"] = "done"
                job["finishedAt"] = now
            elif state == "failed":
                job["state"] = "failed"
                job["exit"] = event.get("exit", job["exit"])
                job["finishedAt"] = now
            job["updatedAt"] = now

    def adopt(self, job: dict[str, Any], *, subject: str, tool: str, argv: list[str]) -> dict[str, Any]:
        """A request arrives for a subject the ledger already lists from a parent's
        announcement: that entry IS this job (no duplicate row)."""
        with self._guard:
            existing = self._running_for(_real(subject), exclude=job) if subject else None
            if existing is not None:
                self._jobs.pop(job["id"], None)
                existing["tool"], existing["argv"] = str(tool), [str(a) for a in argv]
                return existing
        return job

    def finish(self, job: dict[str, Any], exit_code: int) -> None:
        now = self._clock()
        with self._guard:
            if job["state"] in _RUNNING:
                job["state"] = "done" if exit_code == 0 else "failed"
            job["exit"] = int(exit_code)
            job["finishedAt"] = job["finishedAt"] or now
            job["updatedAt"] = now
            self._sweep(now)

    # --- reading -----------------------------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        """Every running job and every job finished within the retention window."""
        with self._guard:
            self._sweep(self._clock())
            return [dict(job, outputs=list(job["outputs"]), argv=list(job["argv"])) for job in self._jobs.values()]

    def _running_for(self, subject: str, *, exclude: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for job in reversed(list(self._jobs.values())):
            if job is not exclude and job["subject"] == subject and job["state"] in _RUNNING:
                return job
        return None

    def _sweep(self, now: float) -> None:
        for key, job in list(self._jobs.items()):
            finished = job.get("finishedAt")
            if finished is not None and now - finished > self._retain:
                self._jobs.pop(key, None)
