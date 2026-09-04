"""Where a build's position comes from — ours in memory, a peer's from disk.

TWO PRODUCERS, TWO CHANNELS
---------------------------
OUR OWN build reports IN PROCESS. The compile worker installs a progress sink
and every ``ProgressEvent`` arrives here as a frame, so the bar the client draws
is the build narrating itself rather than a file being scraped. Nothing is read
from disk for a build this server started.

A PEER's build — ``python model.py`` in a terminal, a ``cadgen step compile``,
another viewer — has no in-process channel, so those stay file-based: every
producer publishes an advisory record at ``progress_path(build_scope(model))``
(``cadgen.coordination.paths``), keyed by the MODEL path, which is the one
identity a reader holds before the build has produced anything.

DELIBERATELY SCHEMA-BLIND AND RUN-ATTRIBUTION-FREE
--------------------------------------------------
``schemaVersion`` is not checked and ``runId`` is only passed through (the
client resets its bar when it changes). Nothing proves a peer is alive: the
record is written data, so staleness is gated on ``outcome`` plus a freshness
window, and a killed peer's badge ages out rather than pinning an entry to a
loading overlay forever.

No kernel import: this is a viewing-path read. ``cadgen.coordination.paths`` is
stdlib-only by contract.
"""

from __future__ import annotations

import json
import threading
import time

from cadgen.coordination.paths import progress_path

from .store_paths import build_scope

__all__ = [
    "PROGRESS_FRESHNESS_MS",
    "ProgressRegistry",
    "build_progress_snapshot",
    "status_record_path",
]

# A peer record older than this is treated as absent. It is the ONLY thing that
# retires a record left behind by a killed producer: records are never unlinked
# (a reader mid-read would see the file vanish), so a crashed peer's last
# non-terminal write would otherwise say "generating" forever.
PROGRESS_FRESHNESS_MS = 20_000


def status_record_path(scope: str) -> str:
    """The advisory progress record for a build scope, as a string."""
    return str(progress_path(scope))


def _read_fresh_record(record_path: str, now_ms: float):
    """A live, non-terminal record, or ``None``.

    Returns ``(updated_at, record)`` so a caller can compare candidates without
    re-parsing.

    ``errors="replace"``: the record is written by a peer build WHILE IT RUNS,
    so a read can legitimately land on a partial write; strict decoding turned
    a torn multi-byte character into ``UnicodeDecodeError``, which is a
    ``ValueError`` and was swallowed as "no build in flight" — the client stopped
    showing the peer's progress and reported the model ready mid-build.
    """
    try:
        with open(record_path, "r", encoding="utf-8", errors="replace") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    # A record with an outcome describes a FINISHED run: done, failed or
    # skipped. Rendering one as in-flight is how a completed build kept a
    # spinner on screen.
    if record.get("outcome") is not None:
        return None
    try:
        updated_at = float(record.get("updatedAt") or 0)
    except (TypeError, ValueError):
        return None
    if updated_at != updated_at or updated_at in (float("inf"), float("-inf")):  # NaN/inf
        return None
    if now_ms - updated_at > PROGRESS_FRESHNESS_MS:
        return None
    return updated_at, record


def _snapshot_from_record(record: dict) -> dict:
    """The record IS the progress payload.

    Its phase fields are flattened at the top level in exactly the shape the
    client's ``normalizeArtifactProgress`` reads, so one reader serves every
    producer and the extra identity keys ride along harmlessly.
    """
    run_id = record.get("runId")
    return {
        "writing": True,
        "busy": False,
        "runId": run_id if isinstance(run_id, str) else None,
        "progress": record,
    }


class ProgressRegistry:
    """The in-process channel: what OUR builds are reporting, right now.

    Keyed by build scope, the same key the in-flight map uses, so a status poll
    and the build it is asking about agree on identity.

    The writer is the compile client's frame-reader thread and the readers are
    request threads, so every access is guarded — Node got this serialised for
    free from its event loop.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._entries: dict[str, dict] = {}

    def publish(self, scope: str, run_id: str, payload: dict) -> None:
        """Record one progress frame.

        ``run_id`` must be STABLE for the whole run: the client resets its bar
        to null when it changes, because a ratio is monotonic only within a run.
        """
        record = dict(payload)
        record["runId"] = run_id
        record["updatedAt"] = round(time.time() * 1000.0)
        with self._guard:
            self._entries[scope] = record

    def clear(self, scope: str) -> None:
        with self._guard:
            self._entries.pop(scope, None)

    def snapshot(self, scope: str) -> dict | None:
        """The live snapshot for a build we are running, or ``None``.

        No freshness window applies: the entry exists only while the client owns
        a running worker for it, and is cleared in a ``finally``. The window is
        for records whose producer we cannot observe.
        """
        with self._guard:
            record = self._entries.get(scope)
        return _snapshot_from_record(record) if record is not None else None


def build_progress_snapshot(entry_path, *, registry: ProgressRegistry | None = None) -> dict | None:
    """The build view for one model: ours if we are building it, else a peer's."""
    scope = build_scope(entry_path)
    if registry is not None:
        live = registry.snapshot(scope)
        if live is not None:
            return live
    found = _read_fresh_record(status_record_path(scope), time.time() * 1000.0)
    return _snapshot_from_record(found[1]) if found is not None else None
