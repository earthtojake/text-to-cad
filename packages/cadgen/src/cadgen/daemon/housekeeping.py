"""Store housekeeping the daemon does while idle (STORE.md §8).

For each store a finished request named, once no request has been in flight
for ``QUIET_SECONDS``, one look -- a stat walk that keeps nothing per file:

1. **Over the cap**: when the store has outgrown ``max(cap, after + band)``,
   ``after`` being where that store's last pass ended under the same cap, a
   full pass with the cap (retire, evict, sweep). ``band`` is the fifth of the
   cap between the cap and its low watermark.
2. **Otherwise, a retired index kind** (``index/op``): a pass that retires it
   and sweeps only the objects its entries named.

A pass that finds a newer cadgen writing to the store removes nothing and says
so; the next one is as far off as after any other pass.

``after`` is noted beside the daemon's socket, per store, so a store whose
records and documents alone hold more than the cap costs one pass per fifth of
the cap it grows -- never one per idle moment, nor one per daemon start.
Losing that note costs one pass.

A pass runs as ``python -m cadgen.store.gc``, a process of its own, so its
memory (a record per object and entry) leaves with it instead of staying in
the daemon. Closing its stdin stops it at its next step, which happens the
moment a request arrives or the daemon winds down; stopping anywhere leaves a
consistent store. Stdlib and the store modules only; never the CAD kernel.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

QUIET_SECONDS = 30.0
# How long a pass told to stop may take to reach its next step before it is killed.
STOP_GRACE_SECONDS = 10.0


class Housekeeper:
    def __init__(
        self,
        *,
        active: Callable[[], bool],
        log: Callable[[str], None] = lambda message: None,
        clock: Callable[[], float] = time.monotonic,
        quiet_seconds: float = QUIET_SECONDS,
        state_dir: Callable[[], Path] | None = None,
    ) -> None:
        self.active = active
        self._log = log
        self._clock = clock
        self._quiet = float(quiet_seconds)
        self._state_dir = state_dir or _default_state_dir
        self._guard = threading.Lock()
        self._due: dict[str, int | None] = {}
        self._retired_at: dict[str, float] = {}
        self._last_activity = clock()
        self._stopping = False
        self._worker: threading.Thread | None = None

    # --- what the server tells it --------------------------------------------

    def note(self, store_root: object, env: object = None) -> None:
        """A request against ``store_root`` finished: look at that store when idle,
        under the cap the requesting client had in force."""
        from cadgen.store.gc import configured_cap

        root = str(store_root or "").strip()
        with self._guard:
            self._last_activity = self._clock()
        if not root:
            return
        try:
            cap = configured_cap(env if isinstance(env, dict) else {})
        except ValueError as error:
            self._log(f"store {root}: {error}; it is not evicted")
            cap = None
        with self._guard:
            self._due[root] = cap

    def busy(self) -> bool:
        worker = self._worker
        return worker is not None and worker.is_alive()

    def stop(self, timeout: float = 2.0) -> None:
        """The daemon is exiting: end a pass at its next step."""
        self._stopping = True
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    # --- the idle watcher's call ----------------------------------------------

    def tick(self) -> str | None:
        """Start at most one look, in its own thread, at the first due store.
        Returns that store's root, or None."""
        if self.active():
            with self._guard:
                self._last_activity = self._clock()
            return None
        with self._guard:
            if self._stopping or self.busy() or not self._due:
                return None
            if self._clock() - self._last_activity < self._quiet:
                return None
            root = next(iter(self._due))
            cap = self._due.pop(root)
            self._worker = threading.Thread(target=self._look, args=(root, cap),
                                            name="cadgen-store-housekeeping", daemon=True)
            self._worker.start()
        return root

    # --- one look -------------------------------------------------------------

    def _should_stop(self) -> bool:
        return self._stopping or bool(self.active())

    def _look(self, root: str, cap: int | None) -> None:
        try:
            line = self.look(root, cap)
        except Exception as error:  # noqa: BLE001 - housekeeping never takes the daemon down
            line = f"housekeeping failed: {type(error).__name__}: {error}"
        if line:
            self._log(f"store {root}: {line}")

    def look(self, root: str, cap: int | None) -> str | None:
        """What this store needs now, done; a log line, or None for nothing."""
        from cadgen.store.gc import DEFAULT_GRACE_SECONDS, scan

        resolved = Path(root).expanduser().resolve()
        found = scan(resolved, keep=False)
        if cap is not None and found.total > self.threshold(root, cap):
            report = self._pass(resolved, ["--max-bytes", str(cap)])
            if report is None:
                return self._resume(root, cap)
            self._remember(root, cap, report["bytes_after"])
            return _summary(report)
        if found.retired and self._clock() - self._retired_at.get(root, float("-inf")) >= DEFAULT_GRACE_SECONDS:
            report = self._pass(resolved, ["--retired-only"])
            if report is None:
                return self._resume(root, cap)
            self._retired_at[root] = self._clock()
            return _summary(report)
        return None

    def _resume(self, root: str, cap: int | None) -> str:
        """A pass stopped for a request: this store is due again, whatever store
        that request was for."""
        with self._guard:
            self._due.setdefault(root, cap)
        return "a pass stopped for a request; the next idle look resumes it"

    def _pass(self, root: Path, args: list[str]) -> dict | None:
        """One pass, in a process of its own; its report, or None when it stopped."""
        from cadgen.daemon.executors import worker_env

        env = worker_env()
        env["CADGEN_CACHE_DIR"] = str(root)
        output: list[str] = []
        released = None
        with subprocess.Popen(
            # -P: cadgen's own modules, never the working folder's (STORE.md §9).
            [sys.executable, "-P", "-m", "cadgen.store.gc", *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=tempfile.gettempdir(), env=env, text=True, encoding="utf-8", errors="replace",
        ) as proc:
            reader = threading.Thread(target=lambda: output.extend(proc.stdout), daemon=True)
            reader.start()
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if released is None and self._should_stop():
                    released = time.monotonic()
                    with contextlib.suppress(OSError):
                        proc.stdin.close()
                elif released is not None and time.monotonic() - released > STOP_GRACE_SECONDS:
                    proc.kill()
            reader.join(STOP_GRACE_SECONDS)
        report = None
        for line in reversed(output):
            if line.startswith("{"):
                with contextlib.suppress(ValueError):
                    report = json.loads(line)
                break
        if report is None:
            if released is None:
                tail = "".join(output[-5:]).strip()
                raise RuntimeError(f"the pass exited {proc.returncode} without a report: {tail}")
            return None
        return None if report.get("stopped") else report

    # --- where the last pass ended --------------------------------------------

    def threshold(self, root: str, cap: int) -> int:
        """The size above which this store gets a pass: the cap, or a fifth of
        the cap past where its last pass under this cap ended."""
        from cadgen.store.gc import LOW_WATERMARK

        band = cap - int(cap * LOW_WATERMARK)
        note = self._read_note(root)
        if not note or note.get("cap") != cap or not isinstance(note.get("after"), int):
            return cap
        return max(cap, note["after"] + band)

    def _note_path(self, root: str) -> Path:
        key = hashlib.sha256(str(Path(root).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]
        return self._state_dir() / f"store-{key}.json"

    def _read_note(self, root: str) -> dict | None:
        try:
            note = json.loads(self._note_path(root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return note if isinstance(note, dict) else None

    def _remember(self, root: str, cap: int, after: int) -> None:
        from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

        path = self._note_path(root)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}{temp_suffix()}")
            tmp.write_text(json.dumps({"root": root, "cap": cap, "after": int(after), "at": time.time()}), encoding="utf-8")
            replace_atomic(tmp, path)
        except OSError as error:
            self._log(f"store {root}: cannot note where the pass ended ({error}); the next look may pass again")


def _default_state_dir() -> Path:
    from cadgen.coordination.paths import state_dir

    return state_dir()


def _summary(report: dict) -> str:
    deferred = report.get("deferred")
    if deferred:
        return "left alone: a newer cadgen writes to this store (" + "; ".join(deferred["evidence"]) + ")"
    parts = []
    if report.get("retired"):
        parts.append("retired " + ", ".join(f"index/{kind} ({count} entries)" for kind, count in sorted(report["retired"].items())))
    if report.get("evicted"):
        parts.append("evicted " + ", ".join(f"{count} {kind}" for kind, count in sorted(report["evicted"].items())))
    parts.append(f"removed {report['removed']} objects ({report['removed_bytes']} bytes)")
    size = f"{report['bytes_before']} -> {report['bytes_after']} bytes"
    if report.get("cap") is not None:
        size += f" (cap {report['cap']})"
    return "; ".join(parts) + f"; {size}"
