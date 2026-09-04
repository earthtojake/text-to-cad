"""The status record: what a run publishes about itself, and how a reader consumes it.

ADVISORY ONLY. Freshness is the gate's (``cadgen.store.gate``) and never inferred from
here: a status file is written data with no liveness guarantee, so a reader ages a
non-terminal record out (``cadgen.viewer.build_progress``) rather than trusting it.

The record is never unlinked. Unlinking would race: a reader mid-read would see the file
vanish. Its terminal payload carries ``stageMs``, the run's measured per-phase durations --
kept as a record of what the run cost (the CLI prints it), NOT as an input to anything.
Nothing predicts the next build from the last one any more; each phase reports itself.

**Run id.** A record carries the id of the run that wrote it. The viewer resets its bar
when the id changes, because a ratio is monotonic only within one run.

**Schema v3 reports each phase on its own.** v2 carried a global ``ratio`` plus the band
(``ratioFloor``/``ratioCeiling``) and expectation (``phaseExpectedMs``) a reader needed to
interpolate one overall bar across every phase. Those are gone: a phase now reports its
position in the run (``index``/``count``) and either a real fraction (``done``/``total``) or
a ``detail`` label naming the sub-unit in flight. A reader that does not understand this
version renders no bar, which is the same safe degradation as an unreadable file.

``stageMs`` is written ONLY on ``outcome == "done"``: partial times from a killed run are
not durations anyone should print.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Mapping

# Stdlib-only, like everything this module touches: the viewer's server imports it.
from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

SCHEMA_VERSION = 3

OUTCOME_RUNNING = None
OUTCOME_DONE = "done"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"

INTENT_WRITE = "write"
INTENT_GENERATE = "generate"


def _host() -> str:
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover - hostname lookup effectively never fails
        return ""


def build_record(
    *,
    run_id: str,
    kind: str,
    intent: str,
    started_at_ms: float,
    outcome: str | None = None,
    progress: Mapping[str, Any] | None = None,
    stage_ms: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """One status payload. ``progress`` is the phase/ratio block, absent for a bare
    ``starting`` record; ``stage_ms`` is attached only by a successful terminal write."""
    record: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "pid": os.getpid(),
        "host": _host(),
        "kind": kind,
        "intent": intent,
        "startedAt": round(started_at_ms),
        "outcome": outcome,
        "updatedAt": round(time.time() * 1000.0),
    }
    if progress:
        record.update(progress)
    record["stageMs"] = (
        {str(k): round(float(v)) for k, v in stage_ms.items()} if stage_ms else None
    )
    return record


def write_record(path: Path | str, record: Mapping[str, Any]) -> bool:
    """Atomically publish ``record``. Returns False when the write was not possible.

    Temp file + ``os.replace`` so a poller never reads a half-written payload. The temp
    name carries the pid so two processes cannot clobber each other's temp file. Every
    failure is swallowed: an unwritable ``__cadgen__`` must degrade to "no status
    reported", never to a failed build.
    """
    target = Path(path)
    temp_path = target.with_name(f"{target.name}{temp_suffix()}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
        replace_atomic(temp_path, target)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
        return False


def read_record(path: Path | str) -> dict[str, Any] | None:
    """The raw record, or None when there is nothing readable there."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None
