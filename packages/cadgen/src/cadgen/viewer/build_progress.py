"""Where a build's position comes from — ours in memory, a peer's from disk.

TWO PRODUCERS, TWO CHANNELS
---------------------------
OUR OWN build reports IN PROCESS. The compile worker installs a progress sink
and every ``ProgressEvent`` arrives here as a frame, so the bar the client draws
is the build narrating itself rather than a file being scraped. Nothing is read
from disk for a build this server started.

A PEER's build — ``python model.py`` in a terminal, a ``cadgen step compile``,
another viewer — has no in-process channel, so those stay file-based.

THE DEFECT THIS FIXES
---------------------
A peer publishes its record at ``status_path(output_dir)``, and the two
producers used to pass DIFFERENT output dirs:

* a model-script run passed ``coordination_scope(entry_path)``, the model-path
  keyed ``locks/`` tier;
* ``cadgen step compile`` — and the re-emit, and the on-demand topology
  rebuild — passed ``render_package_dir(entry_path)``, the CONTENT-keyed
  ``packages/`` tier.

The Node reader derived only the locks spelling. So a script run's progress
appeared and a COMPILE's never did — which is the viewer's own import, the case
where a bar matters most, and it is why an import only ever showed an
indeterminate badge. This reader derives BOTH and takes whichever is fresher.

cadgen has since closed the same gap from the PRODUCER side: all three of those
call sites now key by ``coordination_scope`` too, pinned by
``tests/python/packages/cadgen/test_build_progress_path.py``, which also asserts
a current build leaves NO record outside the locks tier. Both fixes are worth
having and neither subsumes the other — see below.

WHY THE PACKAGES TIER STAYS, NOW THAT OUR OWN BUILDS REPORT IN PROCESS
----------------------------------------------------------------------
Reading a second tier is a DECLARED departure from the Node backend on a route
the client polls every 400ms, so it owes an argument. The registry above covers
builds this server runs — which is most of them, and none of them need a file
read at all — but not the case the extra read exists for.

When our worker cannot take the model's write lock it answers ``contended``,
``build_artifact`` turns that into ``generating``, and the client stops POSTing
and ATTACHES: it polls this route for someone else's bar. That peer is by
construction a ``build_step_artifact`` caller — another viewer's worker, or a
``cadgen step compile`` in a terminal — and cadgen is a SEPARATELY INSTALLED
distribution, so the peer's version is not this tree's version. A peer on a
cadgen that predates the producer-side fix still publishes to the packages
tier, and reading only the locks tier would tell the client to attach to a bar
that can never appear. So the second read is what keeps ``contended`` meaningful
against any peer, and it costs one ``open()`` of a usually-absent file per poll,
paid only for ``.step`` entries and only while we are not building them
ourselves.

DELIBERATELY SCHEMA-BLIND AND RUN-ATTRIBUTION-FREE
--------------------------------------------------
``schemaVersion`` is not checked and ``runId`` is not matched against a live
sentinel. cadgen's own ``progress_for_run`` does both and is more correct — it
cannot render a SIGKILLed run's corpse — but the viewer cannot know a peer's run
id before reading the record, and probing the sentinel would make a *reading*
path take a lock. Staleness is gated on ``outcome`` plus the freshness window
instead, so a killed peer's badge ages out rather than pinning an entry to a
loading overlay forever.

No cadgen import: this is a viewing-path read, and the record paths are two
string derivations.
"""

from __future__ import annotations

import json
import os
import threading
import time

from .store_paths import coordination_scope, render_package_dir

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

# cadgen's coordination.paths.STATUS_SUFFIX. Mirrored rather than imported for
# the same reason store_paths.py is a local copy: reading a peer's progress must
# not make cadgen a hard dependency of viewing.
_STATUS_SUFFIX = ".generation.progress.json"


def status_record_path(output_dir: str) -> str:
    """``<dirname>/.<basename>.generation.progress.json``."""
    parent, name = os.path.split(os.path.normpath(str(output_dir)))
    return os.path.join(parent, f".{name}{_STATUS_SUFFIX}")


def _read_fresh_record(record_path: str, now_ms: float):
    """A live, non-terminal record, or ``None``.

    Returns ``(updated_at, record)`` so the caller can pick the fresher of two
    tiers without re-parsing.

    ``errors="replace"``, matching the ``fs.readFileSync(path, "utf8")`` this
    replaced. The record is written by a peer build WHILE IT RUNS, so a read can
    legitimately land on a partial write; strict decoding turned a torn
    multi-byte character into ``UnicodeDecodeError``, which is a ``ValueError``
    and was swallowed as "no build in flight" — the client stopped showing the
    peer's progress and reported the model ready mid-build. Replacing the byte
    reproduces Node: the JSON around it still parses, or it does not and the
    record is skipped for a reason that is actually about the JSON.
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

    Keyed by render-package directory, the same key the in-flight map uses, so
    a status poll and the build it is asking about agree on identity.

    The writer is the compile client's frame-reader thread and the readers are
    request threads, so every access is lock-guarded — Node got this serialised
    for free from its event loop.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}

    def publish(self, package_dir: str, run_id: str, payload: dict) -> None:
        """Record one progress frame.

        ``run_id`` must be STABLE for the whole run: the client resets its bar
        to null when it changes, because a ratio is monotonic only within a run.
        """
        record = dict(payload)
        record["runId"] = run_id
        record["updatedAt"] = round(time.time() * 1000.0)
        with self._lock:
            self._entries[package_dir] = record

    def clear(self, package_dir: str) -> None:
        with self._lock:
            self._entries.pop(package_dir, None)

    def snapshot(self, package_dir: str) -> dict | None:
        """The live snapshot for a build we are running, or ``None``.

        No freshness window applies: the entry exists only while the client owns
        a running worker for it, and is cleared in a ``finally``. The window is
        for records whose producer we cannot observe.
        """
        with self._lock:
            record = self._entries.get(package_dir)
        return _snapshot_from_record(record) if record is not None else None


def build_progress_snapshot(entry_path, *, registry: ProgressRegistry | None = None) -> dict | None:
    """The build view for one model: ours if we are building it, else a peer's."""
    package_dir = render_package_dir(entry_path)
    if registry is not None:
        live = registry.snapshot(package_dir)
        if live is not None:
            return live

    now_ms = time.time() * 1000.0
    best = None
    # BOTH tiers, because the two producers key their records differently. See
    # the module docstring: reading only the locks tier is the defect.
    for output_dir in (coordination_scope(entry_path), package_dir):
        found = _read_fresh_record(status_record_path(output_dir), now_ms)
        if found is not None and (best is None or found[0] > best[0]):
            best = found
    return _snapshot_from_record(best[1]) if best is not None else None
