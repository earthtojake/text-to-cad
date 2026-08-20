"""The status record: what a run publishes about itself, and how a reader consumes it.

ADVISORY DECORATION ONLY. The ready/generating/error state machine is driven by the lock
and nothing here. That separation is deliberate: a status file is written data with no
liveness guarantee, and inferring "a build is running" from one reintroduces exactly the
stale-heartbeat failure the flock replaced.

The record is never unlinked. Unlinking would race: a reader mid-read would see the file
vanish. Its terminal payload carries ``stageMs``, the run's measured per-phase durations --
kept as a record of what the run cost (the CLI prints it), NOT as an input to anything.
Nothing predicts the next build from the last one any more; each phase reports itself.

**Run attribution.** A record carries the id of the run that wrote it, because a record left
behind by a SIGKILLed run is otherwise indistinguishable from the live one: any later lock
holder that never reported progress (an export, say) made the viewer render the corpse's
position -- "Meshing components 31/50" for a run that had meshed nothing. A reader accepts a
record only when its ``runId`` matches the run id stamped in the sentinel by the current
holder.

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


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result else 0.0  # NaN -> 0


def progress_for_run(path: Path | str, run_id: str | None) -> dict[str, Any] | None:
    """The in-flight run's position, or None when there is nothing to show.

    None for: no record, an unreadable/partial one, a schema this reader does not
    understand, a record describing a FINISHED run, or a record belonging to some OTHER
    run than the one holding the lock.

    That last case is the whole point of the run id. A record is written data with no
    liveness guarantee: a SIGKILLed build leaves a non-terminal one on disk forever. Only
    the kernel knows a run is alive, so a record is rendered ONLY when it can be attributed
    to the run that currently holds the sentinel. ``run_id`` of None means the caller could
    not read one, so nothing can be attributed and nothing is shown.
    """
    payload = read_record(path)
    if payload is None or run_id is None:
        return None
    if _as_int(payload.get("schemaVersion")) != SCHEMA_VERSION:
        # A record this reader does not understand. Report no progress; the caller still
        # reports `generating` from the lock, the same safe degradation as an unreadable
        # file.
        return None
    if payload.get("outcome") is not None:
        return None
    if str(payload.get("runId") or "").strip() != run_id:
        return None

    phase = str(payload.get("phase") or "").strip()
    if not phase or phase == "done":
        return None

    total = payload.get("total")
    return {
        "phase": phase,
        "label": str(payload.get("label") or ""),
        "detail": str(payload.get("detail") or ""),
        "index": _as_int(payload.get("index")),
        "count": _as_int(payload.get("count")),
        "done": _as_int(payload.get("done")),
        "total": _as_int(total) if total is not None else None,
        "determinate": bool(payload.get("determinate")),
        "phaseStartedAt": _as_float(payload.get("phaseStartedAt")),
        "updatedAt": _as_float(payload.get("updatedAt")),
        "runId": str(payload.get("runId") or "") or None,
    }
