"""A manufacturing check's life in the engine (``Runner``): asked, answered from what was kept or measured in a
checks process, and stopped when it must be.

Every check is measured in a checks process (``checks.Pool``), from a file's path or from the bytes of the
document the engine holds -- never in a model's warm worker, so a check holds up no build, inspection or
view of its document, and a build never has a check to cancel. Each asked check has one ``State``, changed
under the runner's one lock:

- ``ASKED``: what was kept of it is looked for, and its document read.
- ``WAITING``: for a slot of the pool; it holds no process.
- ``STARTING``: a slot is its own, and the slot's checks process is leased, started where none lives.
- ``MEASURING``: that process is its own (``Asked.process``), its request sent.
- ``ANSWERED``: its process answered, or was lost.
- stopped by the engine, each the reason its callers are told (``FAILURES``): ``CANCELLED`` (every caller of
  it gone, its process given to a check someone waits for), ``STOPPED`` (the engine stops), ``OVER_TIME`` and
  ``OVER_MEMORY`` (past a check's own limits, ``Limits``), ``SUPERSEDED`` (its model was built again under it,
  ``Runner.built``).

A check is stopped only before it has ended (``_stop``): one waiting leaves the pool's queue, one
measuring has its process killed -- the process its own lease holds, signalled under the lock, which the
lease's end takes too before it lets the process go, so no stop ever reaches a process another check has
(a checks process holds nothing of anyone's: what it read for checks goes with it, and the next check
starts a fresh one).

A check that does not complete answers ``{"failed": words, "reason": ...}`` (``api.EngineError.reason``),
never a result: ``cancelled``, ``stopped``, ``over_time``, ``over_memory``, ``process_lost`` (its checks
process exited under it), ``no_kernel`` (none could be started) and ``superseded`` (its document was built
again, or its file rewritten, while it was measured: the result is of a version that is gone, so it is neither
kept nor answered).

**A document that moves on under its check.** A model built to a new generation while a check of it is asked
is told by the daemon as the build registers (``Runner.built``): the check stops at once, its process killed,
so it holds neither its slot nor its callers for a result no one can use. While a caller of it is still there
the check is then asked again, of the document as it is now (``READS`` times at most: a document built again
under each answers ``superseded``); with none it ends there. A build that changes nothing keeps its generation,
and one of another model is another document: neither stops a check.
"""

from __future__ import annotations

import enum
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cad.engine.client import WORKER_STDERR
from cad.engine.frames import failed_type

from cad_server.engine.checks import Checks, Pool, Withdrawn, digest
from cad_server.engine.supervisor import Gone

__all__ = ["FAILURES", "SECONDS", "STOPPED", "SUPERSEDED", "Asked", "Limits", "Runner", "State", "file_key",
           "resident_of"]

# A check measured this long is stopped (``Limits``): ``CAD_ENGINE_CHECK_SECONDS``, by default half an hour.
SECONDS = 1800.0
# How often the watchdog looks at the checks measuring (``Runner._watch``).
WATCH_SECONDS = 1.0
# How many times a check is asked of its document as it is now because a build replaced it, or its file was
# rewritten, before or while it was measured: past them it answers ``superseded``.
READS = 3


class State(enum.Enum):
    ASKED = "asked"
    WAITING = "waiting"
    STARTING = "starting"
    MEASURING = "measuring"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    STOPPED = "stopped"
    OVER_TIME = "over_time"
    OVER_MEMORY = "over_memory"
    SUPERSEDED = "superseded"


# The states a check can be stopped in: once it is in any other, it has ended.
LIVE = (State.ASKED, State.WAITING, State.STARTING, State.MEASURING)
STOPPED = ("the CAD server stopped while it measured the manufacturing check (an update or `cad stop` stops it): "
           "run the check again")
SUPERSEDED = ("the document changed while its manufacturing check ran, so nothing of that check is kept or "
              "answered: run the check again")
# What the callers of a check the engine stopped are told, by the state it was stopped in.
FAILURES = {
    State.CANCELLED: "the manufacturing check was stopped and its checks process given to another check: every "
                     "caller of it had gone; run the check again",
    State.STOPPED: STOPPED,
    State.OVER_TIME: "the manufacturing check was stopped after {seconds:.0f} s, over a check's time limit of "
                     "{limit:g} s: nothing was measured. Check a smaller part or fewer samples, or raise the limit "
                     "(CAD_ENGINE_CHECK_SECONDS, in the environment the CAD server starts in; 0 for none)",
    State.OVER_MEMORY: "the manufacturing check was stopped with its process at {resident:.0f} MB, over a check's "
                       "memory limit of {limit:.0f} MB: nothing was measured. The part may be too large to check "
                       "on this machine; check a smaller part, or raise the limit (CAD_ENGINE_CHECK_RSS_MB, in the "
                       "environment the CAD server starts in; 0 for none)",
    State.SUPERSEDED: SUPERSEDED,
}


def resident_of(pid: int | None) -> float | None:
    """The resident memory of process ``pid`` now, in MiB, read from outside it (``/proc`` on Linux, the
    system's own count on Windows, ``ps`` elsewhere); None where the system does not say, which holds a check to
    no memory limit there."""
    if not pid:
        return None
    try:
        if sys.platform.startswith("linux"):
            with open(f"/proc/{pid}/statm", encoding="ascii") as handle:
                return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS, as ``worker.resident_mb`` reads its own
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return None
            try:
                counters = Counters()
                counters.cb = ctypes.sizeof(Counters)
                if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return None
                return counters.WorkingSetSize / 2**20
            finally:
                kernel32.CloseHandle(handle)
        said = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
                              check=False).stdout.split()
        return int(said[0]) / 1024 if said else None
    except Exception:  # noqa: BLE001 - a system that will not say holds a check to no memory limit
        return None


class Limits:
    """What one check may take before the engine stops it: ``seconds`` measuring (None: no limit) and
    ``memory()``, its process's resident memory in MiB (None: no limit). ``notes``: what was said of a setting
    that is no number."""

    def __init__(self, seconds: float | None = SECONDS, memory: Callable[[], float | None] = lambda: None,
                 notes: tuple[str, ...] = ()) -> None:
        self.seconds, self.memory, self.notes = seconds, memory, notes

    @classmethod
    def of_environment(cls, cap: Callable[[], float | None]) -> "Limits":
        """The daemon's: ``CAD_ENGINE_CHECK_SECONDS`` (by default ``SECONDS``) and ``CAD_ENGINE_CHECK_RSS_MB``
        (by default ``cap()``, the memory the engine holds all its processes to together,
        ``CAD_ENGINE_WORKER_RSS_MB``: one check alone never takes it all); ``0`` for no limit."""
        notes: list[str] = []

        def number(name: str) -> float | None:
            given = os.environ.get(name, "").strip()
            if not given:
                return None
            try:
                value = float(given)
            except ValueError:
                value = -1.0
            if value < 0:
                notes.append(f"{name}={given!r} is no number of zero or more: the default holds")
                return None
            return value

        seconds, memory = number("CAD_ENGINE_CHECK_SECONDS"), number("CAD_ENGINE_CHECK_RSS_MB")
        return cls(SECONDS if seconds is None else (seconds or None),
                   cap if memory is None else (lambda: memory or None), tuple(notes))

    def status(self) -> dict[str, Any]:
        return {"seconds": self.seconds, "rssMb": self.memory(), **({"notes": list(self.notes)} if self.notes else {})}


class Asked:
    """A check asked of the engine and not yet ended: its ``state``; what it is (``what``: its type, process and
    document or file); its callers (each one's ``gone``, set at its end of file: its own, then every one attached
    to it; None for one asked from within the engine, which never goes); its place in ``Runner.running``
    (``same``; None for a check kept under no version); the slot of the pool it holds and the checks process
    leased for it, while it has them; when it was asked and since when it measures; its answer, once it has
    one; and ``finished``, set when it has ended."""

    def __init__(self, token: str, what: dict[str, Any], gone: threading.Event | None,
                 same: tuple[str, str, str] | None) -> None:
        self.token, self.what, self.same = token, dict(what), same
        self.state = State.ASKED
        self.callers: list[threading.Event | None] = [gone]
        self.slot: str | None = None
        self.process: Any = None
        self.began = time.time()
        self.since: float | None = None
        self.why: dict[str, float] = {}  # what a stop's words say: the seconds, the memory, the limit
        self.answer: dict[str, Any] | None = None
        self.finished = threading.Event()

    def abandoned(self) -> bool:
        """Whether every caller of it, and every caller attached to it since, has gone."""
        return bool(self.callers) and all(gone is not None and gone.is_set() for gone in self.callers)

    def there(self) -> int:
        """How many of its callers are still there."""
        return sum(1 for gone in self.callers if gone is None or not gone.is_set())

    def failure(self) -> dict[str, Any]:
        """What its callers are told of the stop it is in (``FAILURES``)."""
        return {"failed": FAILURES[self.state].format(**self.why), "reason": self.state.value,
                **({"stopped": True} if self.state is State.STOPPED else {})}


class Runner:
    """The engine's manufacturing checks (the module): ``check`` answers one, ``reap``, ``halt`` and the watchdog
    stop them, ``status`` lists them. Of the daemon it takes what it cannot know: ``store`` (the kept results) and
    ``pool`` (the checks processes' slots); ``lease(slot)`` and ``release(process)``, a slot's checks process for
    one request; ``version(ident)``, a model document's generation (None: no such document; ``ValueError``: a
    refusal); ``read(ident)``, the document as a checks process reads it -- ``({"path"}, b"")`` for a file's,
    ``({"document", "name"}, its xbf bytes)`` for a model's -- or ``ValueError``; ``durable(ident, version)``,
    the version of it that outlives the engine with its id, or None; ``stopping()``, whether the engine stops;
    ``limits``; and ``resident``, a process's memory read from outside it."""

    def __init__(self, store: Checks, pool: Pool, *, lease: Callable[[str], Any], release: Callable[[Any], None],
                 version: Callable[[str], str | None], read: Callable[[str], tuple[dict[str, Any], bytes]],
                 durable: Callable[[str, str | None], tuple[str, str] | None],
                 stopping: Callable[[], bool] = lambda: False, limits: Limits | None = None,
                 resident: Callable[[int | None], float | None] = resident_of) -> None:
        self.store, self.pool = store, pool
        self._lease, self._release, self._version, self._read, self._durable = lease, release, version, read, durable
        self.stopping, self.limits, self.resident = stopping, limits or Limits(), resident
        self.lock = threading.Lock()
        # The checks asked and not yet ended, by their token; and by what they check (document, version,
        # check), what the same check asked meanwhile attaches to.
        self.asked: dict[str, Asked] = {}
        self.running: dict[tuple[str, str, str], Asked] = {}
        self.watching = False

    # --- one check ----------------------------------------------------------------------------------

    def check(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None],
              gone: threading.Event | None = None) -> None:
        """A manufacturing check (an ``export`` request with ``check``, ``api.check``) of the document the
        request names, answered through ``send``; ``gone``: set once its caller has hung up.

        The same check of the same version is answered from what was kept (``reused``), in memory, else on
        disk, with no process asked and none of the document's bytes read; one asked while it runs waits for it
        and answers with its answer, saying so, so it is measured once. Else it is measured in a checks process
        of the server's own library, when that is the caller's (its release, ``caller``, and what measures in
        it, ``measures``: ``contract.measures_for``): another's is answered at once with no ``checked``, and
        its caller measures the document its own way. A version is a model's generation, read before its bytes
        and again after the check, or the digest of the bytes a file's check measured: a result is kept under
        the version it was measured at, or not at all, and a check whose document moved on under it is stopped
        (``built``) and asked again of the document as it is now while a caller of it is there, ``READS`` times
        at most, then answers ``superseded`` (the module). A check runs to its end whoever asked it: its caller going leaves it running and its
        result kept, unless a check whose caller is there needs its slot (``reap``)."""
        from cad.engine.contract import measures_for
        from cad.engine.ids import file_id
        from cad.engine.previous import version as release

        def told(message: dict[str, Any]) -> None:
            try:
                send(message)
            except OSError:
                pass  # its caller went: the check goes on, and its result is kept for the next to ask

        refusal = _refusal(request)
        if refusal is not None:
            told({"failed": refusal, "kind": "builtins:ValueError"})
            return
        spec, check = request["source"], request["check"]
        measures = request.get("measures")
        nobody = {"done": {"reports": [], "files": [], "release": release()}}
        if not isinstance(measures, dict) or request.get("caller") != release():
            told(nobody)  # another release's library, or one that does not say what measures in it
            return
        known = self.pool.known()
        if known is not None and not measures_for(measures, known):
            told(nobody)  # other code or libraries than the checks processes': never measured to be thrown away
            return
        key = Checks.key(check, release(), measures.get("code"))
        ident = str(spec["id"]) if "id" in spec else None
        what = {"type": check.get("type"), "process": check.get("process"),
                **({"document": ident} if ident is not None else {"file": str(spec["path"])})}

        def serves(by: Any) -> bool:
            return measures_for(measures, by)

        reads = 0
        while True:
            try:
                if ident is not None:
                    document, before = f"model:{ident}", self._version(ident)
                    durable = self._durable(ident, before)
                else:
                    path = str(spec["path"])
                    document, before = file_key(path), digest(Path(path))
                    durable = None if before is None else (file_id(os.path.normcase(os.path.realpath(path))), before)
            except ValueError as error:
                told(_refused(error))
                return
            since = self.store.epoch(durable[0] if durable is not None else ident)
            same = (document, before, key) if before is not None else None
            with self.lock:
                # Under one lock with a check's end (which keeps its result, then leaves ``running``) and with
                # a reaping (which takes its victim out of it): a check of this version is kept, or running, or
                # this one is the one to run.
                running = self.running.get(same) if same is not None else None
                if running is None:
                    asked = Asked(str(check.get("token") or secrets.token_hex(8)), what, gone, same)
                    while asked.token in self.asked:
                        asked.token = secrets.token_hex(8)
                    self.asked[asked.token] = asked
                    if same is not None:
                        self.running[same] = asked
                else:
                    running.callers.append(gone)  # a caller of it too: while one is there, it is not abandoned
            if running is not None:
                self.store.attached()
                told({"log": "waiting for the same manufacturing check, started "
                             f"{time.time() - running.began:.0f} s ago", "stream": "waiting"})
                running.finished.wait()  # it ends with its process, which the watchdog holds to its limits
                done = (running.answer or {}).get("done")
                checked = done.get("checked") if isinstance(done, dict) else None
                if running.answer is None or (isinstance(done, dict) and not (
                        isinstance(checked, dict) and serves(checked.get("measures")))):
                    continue  # it read its document again, or its measurer measures for another: this one's own
                told(_attached(running.answer))
                return
            try:
                kept = self.store.get(document, before, key, durable, serves) if before is not None else None
                if kept is not None:
                    asked.answer = {"done": {"reports": [], "files": [], "checked": kept, "reused": True}}
                    told(asked.answer)
                    return
                if self.stopping():
                    asked.answer = {"failed": STOPPED, "reason": State.STOPPED.value, "stopped": True}
                    told(asked.answer)
                    return
                try:
                    source, payload = self._read(ident) if ident is not None else ({"path": str(spec["path"])}, b"")
                    moved = ident is not None and self._version(ident) != before
                except ValueError as error:
                    asked.answer = _refused(error)
                    told(asked.answer)
                    return
                if moved:
                    # A build landed as its bytes were read: nothing is measured of a version gone.
                    reads += 1
                    if reads < READS:
                        continue
                    asked.answer = {"failed": SUPERSEDED, "reason": "superseded"}
                    told(asked.answer)
                    return
                if "document" in source:
                    source = {**source, "version": before}  # its bytes are this version's: read once there
                order = {"id": 1, "op": "export", "source": source, "destinations": [], "cwd": None,
                         "check": {**check, "token": asked.token, "measures": measures}}
                answer = self._measure(asked, document, order, payload, told)
                done = answer.get("done")
                measured = done.get("checked") if isinstance(done, dict) else None
                if isinstance(measured, dict):
                    if ident is not None:
                        current = self._version(ident) == before
                        moved = not current  # built again under the check: its result is of a version gone
                    else:
                        current = measured.get("digest") == before
                        moved = bool(measured.get("changed"))  # rewritten while it was read: of no version at all
                    if not measured.get("changed"):
                        self.store.counted(read=bool(measured.get("read")))
                    if moved:
                        answer = {"failed": SUPERSEDED, "reason": "superseded"}
                    by = measured.get("measures")
                    if "done" in answer and before is not None and current and _clean(measured) and serves(by):
                        self.store.keep(document, before, key, _result(measured), durable, since, by)
                if answer.get("reason") == State.SUPERSEDED.value:
                    reads += 1
                    if reads < READS and not asked.abandoned():
                        # Nothing of the version gone is answered: the document as it is now is checked, for
                        # its callers still there (those attached ask again as this one ends unanswered).
                        told({"log": "the document changed while its manufacturing check ran: checking it as "
                                     "it is now", "stream": "waiting"})
                        continue
                asked.answer = answer
                told(answer)
                return
            finally:
                with self.lock:
                    self.asked.pop(asked.token, None)
                    if same is not None and self.running.get(same) is asked:
                        self.running.pop(same)
                asked.finished.set()

    def _measure(self, asked: Asked, document: str, order: dict[str, Any], payload: bytes,
                 told: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """``order`` asked of a checks process for ``asked``: a slot of the pool taken (waiting for one, said
        once), its process leased, the request sent and its answer returned -- or the failure of the stop it
        was in, of its process lost, or of none that could be started."""
        with self.lock:
            if asked.state is not State.ASKED:
                return asked.failure()  # stopped as it read its document
            asked.state = State.WAITING
        try:
            slot = self.pool.take(document, lambda: asked.state is not State.WAITING,
                                  lambda said: told({"log": said, "stream": "waiting"}),
                                  lambda: self.reap(asked), lambda: self._defers(asked))
        except Withdrawn:
            return asked.failure()  # stopped while it waited for a slot
        process = None
        try:
            with self.lock:
                if asked.state is not State.WAITING:
                    return asked.failure()  # stopped as it took its slot
                asked.state, asked.slot = State.STARTING, slot
            process = self._lease(slot)
            with self.lock:
                if asked.state is not State.STARTING:
                    return asked.failure()  # stopped as its process started
                asked.state, asked.process, asked.since = State.MEASURING, process, time.time()
                watch = not self.watching
                self.watching = True
            if watch:
                threading.Thread(target=self._watch, name="cad-check-watchdog", daemon=True).start()
            answer = process.request(order, told, payload)
            with self.lock:
                if asked.state is not State.MEASURING:
                    return asked.failure()  # stopped as it answered: its process is killed, nothing of it kept
                asked.state = State.ANSWERED
            self.pool.learn(process, answer)
            if "failed" in answer and "kind" not in answer:
                answer = {**answer, "reason": "error"}  # the check itself failed there: its words, nothing measured
            return answer
        except Gone as error:
            with self.lock:
                if asked.state not in LIVE:
                    return asked.failure()  # its process killed by the stop it is in
                asked.state = State.ANSWERED
            if self.stopping():
                return {"failed": STOPPED, "reason": State.STOPPED.value, "stopped": True}
            if error.during:
                return {"failed": _lost(str(error), error.code), "reason": "process_lost"}
            return {"failed": str(error), "reason": "no_kernel", **failed_type(error)}  # it never started
        except RuntimeError as error:
            from cad.engine.serve import KernelProcessesUnavailable

            if not isinstance(error, KernelProcessesUnavailable):
                raise
            # No kernel environment to start a checks process in: its line, and its type.
            return {"failed": str(error), "reason": "no_kernel", **failed_type(error)}
        finally:
            with self.lock:
                asked.process = None  # before it is let go: no stop reaches a process it no longer has
            if process is not None:
                self._release(process)
            with self.lock:
                asked.slot = None
            self.pool.give(slot)

    # --- stopping -----------------------------------------------------------------------------------

    def _stop(self, asked: Asked, why: State, **said: float) -> bool:
        """``asked`` stopped for ``why`` (call with the lock held), unless it has ended: one waiting leaves the
        pool's queue as it next looks, one measuring has the process its lease holds killed, and its request
        answers that it is gone. Whether it was stopped: one that has ended is left alone."""
        if asked.state not in LIVE:
            return False
        asked.state, asked.why = why, dict(said)
        if asked.process is not None:
            try:
                asked.process.popen.kill()
            except Exception:  # noqa: BLE001 - gone already
                pass
        return True

    def _defers(self, waiter: Asked) -> bool:
        """Whether a check waiting for a slot leaves a free one to another: its callers have all gone, and a
        check someone waits for waits too."""
        if not waiter.abandoned():
            return False
        with self.lock:
            return any(asked.state is State.WAITING and not asked.abandoned() for asked in self.asked.values())

    def reap(self, waiter: Asked) -> None:
        """A check waiting for a slot (``waiter``), its caller there: one check measuring whose callers have
        all gone gives up its process -- killed at once, nothing of it kept, and the pool starts a fresh one for
        the waiter -- one for each such waiter, the oldest first, a cancelled one counted until its slot is free
        again. It leaves ``running`` as it is cancelled, so the same check asked meanwhile runs anew. A check
        someone waits for is never cut short this way."""
        if waiter.abandoned():
            return
        with self.lock:
            waiters = sum(1 for asked in self.asked.values()
                          if asked.state is State.WAITING and not asked.abandoned())
            freeing = sum(1 for asked in self.asked.values()
                          if asked.state is State.CANCELLED and asked.slot is not None)
            victims = [asked for asked in self.asked.values() if asked.state is State.MEASURING and asked.abandoned()]
            if freeing >= waiters or not victims:
                return
            victim = min(victims, key=lambda asked: asked.began)
            self._stop(victim, State.CANCELLED)
            if victim.same is not None and self.running.get(victim.same) is victim:
                self.running.pop(victim.same)

    def built(self, ident: str) -> None:
        """Model document ``ident`` was built, handed over or deleted, as the daemon registers it: each check
        of it asked at another generation than the one it has now is stopped -- one waiting leaves the queue,
        one measuring has its process killed -- and leaves ``running``, so the same check asked from now on is
        of the new generation (``check`` asks it again for the callers still there). A build that kept its
        generation stops nothing, nor does one of another document."""
        try:
            now = self._version(ident)
        except ValueError:
            now = None
        document = f"model:{ident}"
        with self.lock:
            for asked in self.asked.values():
                if asked.same is None or asked.same[0] != document or asked.same[1] == now:
                    continue
                if self._stop(asked, State.SUPERSEDED) and self.running.get(asked.same) is asked:
                    self.running.pop(asked.same)

    def halt(self) -> None:
        """Every check stopped as the engine stops (an update's drain, ``cad stop``): those waiting leave the
        queue, the checks processes measuring are killed, all at once -- they hold nothing of anyone's, so nothing
        is waited for -- and their callers are told to run the check again (``api.Stopped``)."""
        with self.lock:
            for asked in self.asked.values():
                self._stop(asked, State.STOPPED)

    def _watch(self) -> None:
        """The watchdog, alive while a check measures: each one past a check's time limit, or whose process
        holds more than a check's memory limit (read from outside the process, so one inside a kernel call that
        never returns is seen all the same), is stopped. What it read is the process's memory as the supervisor
        counts it (``Process.rss``) from then on, so the engine's memory rule and the pool's room go by what a
        measuring process holds now, not by what it said after its last check."""
        while True:
            now = time.time()
            with self.lock:
                measuring = [(asked, asked.process.pid, asked.since or now) for asked in self.asked.values()
                             if asked.state is State.MEASURING and asked.process is not None]
                if not measuring:
                    self.watching = False
                    return
            seconds, memory = self.limits.seconds, self.limits.memory()
            for asked, pid, since in measuring:
                resident = self.resident(pid) if memory is not None else None
                with self.lock:
                    if resident is not None and asked.state is State.MEASURING:
                        asked.process.rss = resident
                    if seconds is not None and now - since > seconds:
                        self._stop(asked, State.OVER_TIME, seconds=now - since, limit=seconds)
                    elif memory is not None and resident is not None and resident > memory:
                        self._stop(asked, State.OVER_MEMORY, resident=resident, limit=memory)
            time.sleep(WATCH_SECONDS)

    # --- what it holds ------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """What ``status`` says of the checks: the store's counts, how many are asked, the pool, a check's
        limits, and each check asked and not ended (``running``): what, of which document or file, where (its
        checks process; None while it waits for one), since when, whether a caller still waits for it and how
        many do (a caller gone never counted)."""
        now = time.time()
        with self.lock:
            rows = [{**asked.what, "state": asked.state.value,
                     "where": getattr(asked.process, "key", None), "since": asked.began,
                     "seconds": round(now - asked.began, 1), "attached": not asked.abandoned(),
                     "callers": asked.there(), "waiting": asked.process is None}
                    for asked in sorted(self.asked.values(), key=lambda asked: asked.began)]
        return {**self.store.status(), "asked": len(rows), "pool": self.pool.status(), "limits": self.limits.status(),
                "running": rows}


def _refusal(request: dict[str, Any]) -> str | None:
    """Why a check's request is none the engine measures, in one line, or None: it names a document the engine
    holds or a file, and a check of a B-rep type for a process it has, its options resolved."""
    from cad._internal.dfm import PROCESSES

    spec, check = request.get("source"), request.get("check")
    if not isinstance(spec, dict) or not ("id" in spec or "path" in spec):
        return "a check reads a document the engine holds, or a STEP's or an xbf's file"
    if not isinstance(check, dict) or check.get("type") not in ("model", "step", "xbf"):
        return "the engine measures a manufacturing check of a model, a STEP or an xbf"
    process = check.get("process")
    if process is None:
        return None if isinstance(check.get("given", {}), dict) else "a check's given options are a table"
    if process not in PROCESSES:
        return f"a check's process is {', '.join(PROCESSES[:-1])} or {PROCESSES[-1]}, not {process!r}"
    return None if isinstance(check.get("resolved"), dict) else "a check's resolved options are a table"


def _refused(error: Exception) -> dict[str, Any]:
    """A refusal as the daemon answers one (``daemon.refused``)."""
    from cad_server.engine.daemon import refused

    return refused(error)


def _lost(said: str, code: int | None) -> str:
    """A checks process that exited while it measured a check, said as such: what went with it, and, for one
    the system killed, why it usually does."""
    head, tail, detail = said.partition(WORKER_STDERR)
    killed = getattr(signal, "SIGKILL", None)
    why = (": killed by the system, usually for memory -- the part may be too large to check on this machine"
           if killed is not None and code == -int(killed) else "")
    return f"{head}{why}. The check is not run again; the next check starts a fresh process{tail}{detail}"


def file_key(path: str) -> str:
    """A file as the checks key it: by its device and inode where the system gives one, so every name of one
    file -- a hard link, another spelling of its case -- is one key; else by its real path, its case folded where
    its file system folds it (asked of the system, never assumed)."""
    real = os.path.normcase(os.path.realpath(path))
    try:
        found = os.stat(real)
    except OSError:
        return f"file:{real}"
    if found.st_ino:
        return f"file:{found.st_dev}:{found.st_ino}"
    folder, name = os.path.split(real)
    other = os.path.join(folder, name.swapcase())
    try:
        folds = other != real and os.path.samefile(real, other)
    except OSError:
        folds = False  # no file by the other spelling: a file system that tells case apart
    return f"file:{real.casefold() if folds else real}"


def _result(checked: dict[str, Any]) -> dict[str, Any]:
    """A check's answer as it is kept and as a caller that waited for it is answered: without what only its
    first caller is told -- whether it read the document, what measured it."""
    return {name: value for name, value in checked.items() if name not in ("read", "measures")}


def _attached(answer: dict[str, Any]) -> dict[str, Any]:
    """What a caller that waited for the same check is answered: that check's answer, its result as reused; its
    failure as it was."""
    done = answer.get("done")
    if not (isinstance(done, dict) and isinstance(done.get("checked"), dict)):
        return answer
    return {"done": {**done, "checked": _result(done["checked"]), "reused": True}}


def _clean(checked: dict[str, Any]) -> bool:
    """Whether a check's answer is a result to keep: one fully measured -- never a document that did not read,
    a refusal, or a family not measured, which the next check may measure."""
    report = (checked.get("measured") or {}).get("report")
    return isinstance(report, dict) and not report.get("partial") and not report.get("partial_sections")
