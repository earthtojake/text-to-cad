"""Where a document's build position comes from: the daemon's job ledger.

ONE PRODUCER, ONE CHANNEL. Every job the daemon runs — ``python model.py`` in a
terminal, a parent's child build, a door's compile, this viewer's own compile —
is one entry in the daemon's ledger (``cadgen.daemon.jobs``), carrying the
job's DECLARED OUTPUT PATHS and its state as the build tree narrates it:
submitted → queued → building [phase, done/total] → done | failed. The viewer
asks the daemon (``cadgen.daemon.client.status``), matches jobs to the document
it displays by output path, and shows ``compiling · <phase> n/total`` for any
of them alike; ``failed`` when the latest job for the document failed.

Artifact-side only: no record, no script, no closure is read here, and nothing
on disk is scraped — there is no advisory progress record any more. With no
daemon (``CADGEN_DAEMON=0``, or none running) there is no feed: a document then
reads from its tree alone, and the viewer's own compile is reported by the
compile client's in-flight marker (``cadgen_ops``).

No kernel import: this is a viewing-path read.
"""

from __future__ import annotations

import os
import threading
import time

__all__ = ["FEED_CACHE_SECONDS", "build_progress_snapshot", "jobs_for_document"]

# One status poll per open document every ~400 ms; one socket round-trip per
# window serves them all.
FEED_CACHE_SECONDS = 0.25
_RUNNING = ("submitted", "queued", "building")

_guard = threading.Lock()
_cache: tuple[float, list[dict]] = (0.0, [])


def _daemon_jobs(now: float) -> list[dict]:
    global _cache
    with _guard:
        stamp, jobs = _cache
        if now - stamp < FEED_CACHE_SECONDS:
            return jobs
    from cadgen.daemon import client

    try:
        status = client.status()
    except Exception:  # noqa: BLE001 - a status read never fails a poll
        status = None
    jobs = [job for job in ((status or {}).get("jobs") or []) if isinstance(job, dict)]
    with _guard:
        _cache = (now, jobs)
    return jobs


def _real(path) -> str:
    try:
        return os.path.realpath(str(path))
    except (OSError, ValueError):
        return str(path)


def jobs_for_document(entry_path, *, jobs: list[dict] | None = None) -> list[dict]:
    """Every listed job whose declared outputs include ``entry_path``, oldest first."""
    target = _real(entry_path)
    listed = jobs if jobs is not None else _daemon_jobs(time.time())
    matching = [job for job in listed if target in {_real(p) for p in (job.get("outputs") or [])}]
    return sorted(matching, key=lambda job: float(job.get("startedAt") or 0.0))


def _progress_payload(job: dict) -> dict:
    """The phase block in the shape the client's ``normalizeArtifactProgress`` reads."""
    total = job.get("total")
    done = job.get("done")
    phase = job.get("phase") or job.get("state") or "building"
    return {
        "phase": phase,
        "label": phase,
        "done": done if isinstance(done, int) else 0,
        "total": total if isinstance(total, int) else None,
        "determinate": isinstance(total, int) and total > 0,
        "detail": "",
        "updatedAt": round(float(job.get("updatedAt") or 0.0) * 1000.0),
    }


def build_progress_snapshot(entry_path, *, jobs: list[dict] | None = None) -> dict | None:
    """The build view for one document, from the daemon's ledger.

    ``{"writing": True, "runId", "progress"}`` while a job with this output is
    running; ``{"writing": False, "failed": {...}}`` when the latest such job
    failed; ``None`` when nothing is (or was recently) building it. ``busy`` is
    always False: no producer here can say it.
    """
    matching = jobs_for_document(entry_path, jobs=jobs)
    running = [job for job in matching if job.get("state") in _RUNNING]
    if running:
        job = running[-1]
        return {"writing": True, "busy": False, "runId": job.get("id"), "progress": _progress_payload(job)}
    if matching and matching[-1].get("state") == "failed":
        job = matching[-1]
        return {
            "writing": False,
            "busy": False,
            "failed": {"runId": job.get("id"), "exit": job.get("exit"), "tool": job.get("tool")},
        }
    return None
