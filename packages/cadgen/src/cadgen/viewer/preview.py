"""What a build of a STEP file is doing, for the viewer's status: never geometry.

The viewer always shows the saved file (STORE.md 9b). This read-only adapter matches the
daemon's jobs to the file's output path and store and reports the newest: whether it is queued
or running, how far it has got, whether it failed and why -- and, once it has finished, whether
the file moved past it (``superseded``), when its failure is no longer the news. A daemon
restart expires this channel; the catalog keeps serving the bytes on disk.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from cadgen.store.paths import store_root

from .backend import absolute_path
from .build_progress import _daemon_jobs
from .scanner import to_posix_path

LOG = logging.getLogger("cadgen.viewer.preview")


def _preview_target(file_ref: str) -> str:
    target = absolute_path(file_ref)
    if Path(target).suffix.lower() not in {".step", ".stp"}:
        raise ValueError("A build status requires a STEP output path")
    return target


def preview_update(file_ref: str, *, after: str | None = None,
                   on_saved: Callable[[dict[str, str], str], None] | None = None) -> dict:
    """Wake for ledger changes, then answer as :func:`preview_status`."""
    target = _preview_target(file_ref)  # refuse invalid paths before waiting
    from cadgen.daemon.client import watch_jobs

    update = watch_jobs(after, output=os.path.realpath(target), store_root=os.path.realpath(store_root()))
    if update is None:
        return preview_status(file_ref, on_saved=on_saved)
    result = preview_status(file_ref, jobs=update["jobs"], on_saved=on_saved)
    result["feedCursor"] = update["jobsCursor"]
    if update.get("jobsWatchLimited"):
        result["feedLimited"] = True
    return result


def preview_status(file_ref: str, *, jobs: list[dict] | None = None,
                   on_saved: Callable[[dict[str, str], str], None] | None = None) -> dict:
    """The newest build of the file. ``on_saved`` hears what the file's builds have saved
    ({path: saved tree}, newest build last) and the file asked about, spelled as it was asked,
    before anything here reads the file: the viewer starts on its catalog row (``warm.py``).
    That is best effort: whatever it raises is logged, and the feed answers all the same."""
    file_path = _preview_target(file_ref)
    # ``file`` is the catalog's spelling of the file (``scanner``); ``output`` is the real path
    # the ledger's outputs are matched by.
    display_file = to_posix_path(file_path)
    target = os.path.realpath(file_path)
    active_store = os.path.realpath(store_root())
    listed = jobs if jobs is not None else _daemon_jobs(time.time(), max_age=0.08)
    matching = [
        job for job in listed
        if job.get("tool") == "run"
        and job.get("editingProducer", True)
        and job.get("storeRoot") and os.path.realpath(job["storeRoot"]) == active_store
        and target in {os.path.realpath(p) for p in job.get("outputs", [])}
    ]
    if on_saved is not None:
        saved = {
            path: str(entry.get("tree") or "")
            for job in sorted(matching, key=lambda job: int(job.get("sequence") or 0))
            for path, entry in (job.get("savedResults") or {}).items()
            if isinstance(entry, dict)
        }
        if saved:
            try:
                on_saved(saved, file_path)
            except Exception as error:  # noqa: BLE001 - a warm only saves a read time; the feed must answer
                LOG.warning("catalog warm hand-off failed: %r", error)
    if not matching:
        return {"output": target, "file": display_file, "state": "disconnected", "revision": None}
    latest = max(matching, key=lambda job: int(job.get("sequence") or 0))
    result = {
        "output": target,
        "file": display_file,
        "epoch": latest.get("epoch"),
        "revision": int(latest.get("sequence") or 0),
        "request": latest.get("id"),
        "state": latest.get("state"),
        "phase": latest.get("phase"),
        "detail": latest.get("detail"),
        "updatedAt": round(float(latest.get("updatedAt") or 0.0) * 1000.0),
        "error": latest.get("error"),
    }
    if _superseded(latest, target):
        # The file moved on after this build finished: built by another installation, or once
        # its daemon has gone; a checkout; a STEP written by hand. Its failure is no longer the news.
        result["superseded"] = True
        result["error"] = None
    return result


def _superseded(job: dict, target: str) -> bool:
    """Whether the file changed after ``job`` finished. A build that saved is judged by bytes: the
    file is no longer the one it wrote. One that saved nothing (it failed, or it changed nothing)
    by time: the file was written after the build ended. A file that is not there was not -- a
    failed first build never wrote one -- and that build's failure is still the news."""
    finished = job.get("finishedAt")
    if job.get("state") not in ("done", "failed") or finished is None:
        return False
    saved = (job.get("savedResults") or {}).get(target)
    if isinstance(saved, dict) and saved.get("documentHash"):
        from cadgen.catalog import artifact_file_hash

        return artifact_file_hash(Path(target)) != saved["documentHash"]
    try:
        return os.stat(target).st_mtime > float(finished)
    except (OSError, TypeError, ValueError):
        return False
