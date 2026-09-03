"""Owns the compile workers: spawning, framing, crash recovery, and de-duplication.

This is the server's side of the private worker protocol. It hands out results
and progress as VALUES — the caller never sees a pipe, an exit code, or a line
of scraped text.

WHAT REPLACED WHAT
------------------
The Node backend spawned ``cadgen step compile`` per import and reconstructed an
answer from its leavings: stdout reverse-scanned for a line starting with ``{``,
stderr truncated to its last 500 characters when that failed, and a watchdog
polling two raw pipes for silence. All of that is gone. A compile now returns a
payload dict or raises, and both cross the wire as one JSON frame.

THE POOL, AND WHY IT IS NOT ONE WORKER
--------------------------------------
Workers are serial — one document at a time each — because that is what a warm
kernel process can safely be. But a SINGLE worker shared by every document
creates a livelock the client cannot escape: a POST for document B while A is
building would answer ``contended``, the client attaches and polls, the status
route reports ``needs-build`` for B (no build of B is in flight anywhere), the
client re-POSTs, and around again every few seconds for the length of A's build,
with a bar that never advances. The Node design had no such state because it
spawned per import and two documents genuinely compiled in parallel.

So the pool holds up to ``max_workers`` (2 by default). Different documents
compile concurrently; ``contended`` goes back to meaning what it says — a peer
holds the package lock. A request that still cannot get a slot within
``ACQUIRE_TIMEOUT_SECONDS`` answers contended, which the client already handles.

CRASH ISOLATION
---------------
A kernel segfault closes the frame socket without a terminal frame. That EOF is
the signal: the worker is reaped, the exit code read (negative means a signal),
and the waiting request answered with the ordinary failure shape. The write lock
is ``fcntl.flock``, so a killed worker releases it AUTOMATICALLY at process
death — there is no stale lock to clean up. A replacement is spawned LAZILY on
the next request, never eagerly, so a crash loop cannot spin the machine, and a
circuit breaker stops respawning after two consecutive crashes on the same
package: a poison document costs two worker lives, not an infinite supply.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid

from .store_paths import coordination_scope

__all__ = [
    "ACQUIRE_TIMEOUT_SECONDS",
    "CompileClient",
]

# Same bound as the kernel lock timeout the worker passes, and the same client
# behaviour on the far side: attach and poll.
ACQUIRE_TIMEOUT_SECONDS = 5.0

# Kill a worker that has gone SILENT for this long. Idleness, not wall clock: a
# real STEP compile legitimately runs for minutes, so a wall-clock cap would
# abort healthy builds, while total silence on the frame channel is the signal
# that a child is wedged rather than working. `<= 0` disables it.
_IDLE_TIMEOUT_ENV = "VIEWER_CADGEN_IDLE_TIMEOUT"
_DEFAULT_IDLE_TIMEOUT_SECONDS = 300.0

# Consecutive crashes on ONE package before we stop feeding it workers.
_CRASH_BREAKER_LIMIT = 2


def _idle_timeout_seconds() -> float:
    """Read per call, so a test can shorten it after the server is running."""
    try:
        return float(os.environ.get(_IDLE_TIMEOUT_ENV, _DEFAULT_IDLE_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return _DEFAULT_IDLE_TIMEOUT_SECONDS


class _Import:
    """One in-flight compile that other requests may attach to."""

    __slots__ = ("done", "result")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: dict | None = None


class _Worker:
    """One live child process and its frame socket."""

    __slots__ = ("process", "conn", "reader", "last_used")

    def __init__(self, process, conn) -> None:
        self.process = process
        self.conn = conn
        self.reader = conn.makefile("rb")
        self.last_used = time.monotonic()

    def alive(self) -> bool:
        return self.process.poll() is None

    def kill(self) -> None:
        # stdin first: closing it is what lets a healthy worker notice EOF and
        # leave on its own, and leaving it open leaks a pipe fd per worker over
        # the life of a long-running server.
        closers = [self.reader.close, self.conn.close]
        if self.process.stdin is not None:
            closers.insert(0, self.process.stdin.close)
        for close in closers:
            try:
                close()
            except (OSError, ValueError):
                pass
        if self.process.poll() is None:
            try:
                self.process.kill()
            except OSError:
                pass
        try:
            self.process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass


class CompileClient:
    """Compiles documents in private worker processes.

    ``compile()`` blocks the calling request thread — which is correct and
    cheap: the thread holds no lock and no GIL while the child works, so the
    400ms status polls the client needs to draw a bar keep being served. That is
    the property a threading server exists for here.
    """

    def __init__(self, *, registry=None, max_workers: int = 2, worker_command=None) -> None:
        self._registry = registry
        self._max_workers = max(1, int(max_workers))
        # A test may substitute a worker that faults on purpose.
        self._worker_command = worker_command
        self._lock = threading.Lock()
        self._in_flight: dict[str, _Import] = {}
        self._idle: list[_Worker] = []
        self._slots = threading.Semaphore(self._max_workers)
        self._crashes: dict[str, int] = {}

    # --- worker lifecycle -------------------------------------------------

    def _worker_argv(self, port: int, token: str) -> list[str]:
        if self._worker_command is not None:
            return [*self._worker_command, "--frame-port", str(port), "--token", token]
        # `-m`, not the file path: the worker is a module of the same installed
        # cadgen this server runs from, and the module spelling is what makes it
        # resolve the same package -- a path would work from a checkout and from
        # a wheel alike, but only the module form says which one it means.
        return [sys.executable, "-m", "cadgen.viewer.compile_worker", "--frame-port", str(port), "--token", token]

    def _spawn(self) -> _Worker:
        """Start a worker and wait for it to connect back.

        The frame channel is a loopback socket rather than the child's stdout,
        because OCCT writes to fd 1 from C++ and would interleave with anything
        framed there. A one-shot listener plus a random token means we accept
        our own child and nothing else.
        """
        token = uuid.uuid4().hex
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(30)
            port = listener.getsockname()[1]
            process = subprocess.Popen(  # noqa: S603 - argv is ours, never a shell
                self._worker_argv(port, token),
                stdin=subprocess.PIPE,
                # stdout is discarded and stderr INHERITED. The worker points
                # its fd 1 at fd 2 as soon as it starts, so everything OCCT
                # prints from C++ lands in the server's own log stream, where a
                # kernel warning is readable instead of being either lost or
                # mixed into a channel something parses.
                stdout=subprocess.DEVNULL,
                stderr=None,
            )
            try:
                while True:
                    conn, _ = listener.accept()
                    reader = conn.makefile("rb")
                    hello = reader.readline()
                    try:
                        greeting = json.loads(hello.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        greeting = {}
                    reader.close()
                    if greeting.get("hello") == token:
                        conn.settimeout(None)
                        return _Worker(process, conn)
                    conn.close()
            except BaseException:
                # A child that never called back would otherwise be orphaned
                # holding a kernel import, invisible to the pool and to us.
                process.kill()
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    process.wait(timeout=5)
                raise
        finally:
            listener.close()

    def _acquire(self, timeout: float) -> _Worker | None:
        """A warm worker, or a fresh one, or ``None`` when every slot stayed busy.

        Reaping happens HERE rather than on a sweep thread: the only moment a
        stale worker costs anything is the moment we are about to reuse it, and
        a timer thread would have to take the same lock to do the same work.
        """
        if not self._slots.acquire(timeout=timeout):
            return None
        budget = _idle_timeout_seconds()
        stale: list[_Worker] = []
        worker = None
        with self._lock:
            while self._idle:
                candidate = self._idle.pop()
                if not candidate.alive():
                    continue
                if budget > 0 and time.monotonic() - candidate.last_used > budget:
                    # Idle long enough that its ~280MB of warm kernel is no
                    # longer worth holding. Dropped for a fresh spawn, which
                    # costs one import on the next build.
                    stale.append(candidate)
                    continue
                worker = candidate
                break
        for dead in stale:
            dead.kill()
        if worker is not None:
            return worker
        try:
            return self._spawn()
        except Exception:
            self._slots.release()
            raise

    def _release(self, worker: _Worker | None) -> None:
        with self._lock:
            if worker is not None and worker.alive():
                worker.last_used = time.monotonic()
                self._idle.append(worker)
        self._slots.release()

    def _discard(self, worker: _Worker) -> None:
        worker.kill()
        self._slots.release()

    def shutdown(self) -> None:
        with self._lock:
            workers, self._idle = self._idle, []
        for worker in workers:
            worker.kill()

    # --- the compile ------------------------------------------------------

    def compile(self, candidate: str, *, force: bool = False) -> dict:
        """Compile one document, attaching to an in-flight run for the same one.

        Returns the CompileResult shape on success, or ``{"ok": False, "error":
        ...}``. Never raises for a build failure: a failure is a value.
        """
        build_key = coordination_scope(candidate)

        # Get-or-create in ONE critical section. Node got this atomicity free
        # from its event loop; a check, then a create, then a store under
        # separate acquisitions lets two threads each start a compile of one
        # document — minutes of duplicated kernel work racing on the store.
        with self._lock:
            existing = self._in_flight.get(build_key)
            if existing is None:
                entry = _Import()
                self._in_flight[build_key] = entry
                owner = True
            else:
                entry, owner = existing, False

        if not owner:
            entry.done.wait()
            return entry.result or {"ok": False, "error": "compile did not report a result"}

        result: dict | None = None
        try:
            result = self._run(candidate, package_dir, force=force)
        except BaseException as error:  # noqa: BLE001 - a supervisor fault is still an answer
            # Attached waiters are owed an answer even when this thread is being
            # torn down, so the result is set before the exception continues.
            # Same split as the worker's error frame: `error` is the bare
            # message the UI will read, `errorType` is the diagnostic label.
            result = {
                "ok": False,
                "error": str(error).strip() or type(error).__name__,
                "errorType": type(error).__name__,
            }
            raise
        finally:
            with self._lock:
                self._in_flight.pop(package_dir, None)
            if self._registry is not None:
                self._registry.clear(package_dir)
            entry.result = result
            entry.done.set()
        return result

    def in_flight(self, package_dir: str) -> bool:
        with self._lock:
            return package_dir in self._in_flight

    def _clear_crashes(self, package_dir: str) -> None:
        with self._lock:
            self._crashes.pop(package_dir, None)

    def _count_crash(self, package_dir: str) -> None:
        with self._lock:
            self._crashes[package_dir] = self._crashes.get(package_dir, 0) + 1

    def _crash_count(self, package_dir: str) -> int:
        with self._lock:
            return self._crashes.get(package_dir, 0)

    def _run(self, candidate: str, package_dir: str, *, force: bool) -> dict:
        if self._crash_count(package_dir) >= _CRASH_BREAKER_LIMIT:
            # A document that has killed two workers gets no more. Answering
            # directly keeps a poison file from consuming the pool forever.
            return {
                "ok": False,
                "error": (
                    f"the CAD kernel crashed repeatedly compiling {os.path.basename(candidate)}; "
                    "not retrying"
                ),
            }

        worker = self._acquire(ACQUIRE_TIMEOUT_SECONDS)
        if worker is None:
            # Every worker is busy with another document. Reuse the payload the
            # client already understands: attach and poll rather than block a
            # request thread for the length of someone else's build.
            return {"ok": True, "contended": True, "skipped": True}

        request_id = uuid.uuid4().hex
        try:
            worker.process.stdin.write(
                (
                    json.dumps(
                        {"id": request_id, "candidate": candidate, "force": bool(force)},
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
            worker.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            self._discard(worker)
            return {"ok": False, "error": "cadgen worker was not accepting work"}

        # _read_frames reports whether it already destroyed the worker, rather
        # than this deciding from liveness: a worker that exits cleanly the
        # instant after a good result would otherwise look "already discarded"
        # and leak both a pool slot and the live count, shrinking the pool by
        # one on every such race until nothing could compile at all.
        discarded = False
        try:
            result, discarded = self._read_frames(worker, candidate, package_dir, request_id)
            return result
        finally:
            if not discarded:
                self._release(worker)

    def _read_frames(
        self, worker: _Worker, candidate: str, package_dir: str, request_id
    ) -> tuple[dict, bool]:
        """Consume frames until a terminal one, EOF, or silence past the budget.

        Reading in the CALLING thread rather than a dedicated reader keeps the
        state machine on one stack: this thread is already blocked waiting for
        the answer, and the worker is serial, so there is nothing a separate
        thread would be doing except handing values back across a queue.
        """
        idle_budget = _idle_timeout_seconds()
        worker.conn.settimeout(idle_budget if idle_budget > 0 else None)
        while True:
            try:
                line = worker.reader.readline()
            except socket.timeout:
                self._discard(worker)
                return (
                    {
                        "ok": False,
                        "error": (
                            f"the CAD kernel went silent for {idle_budget:.1f}s compiling "
                            f"{os.path.basename(candidate)} (no progress and no result); killed"
                        ),
                    },
                    True,
                )
            except OSError:
                line = b""

            if not line:
                # EOF with no terminal frame: the child died mid-compile. The
                # flock it held is released by the kernel at process death, so
                # there is no lock to clean up — only a worker to replace.
                return self._crashed(worker, candidate, package_dir), True

            try:
                frame = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if frame.get("id") != request_id:
                continue

            if "progress" in frame:
                if self._registry is not None:
                    self._registry.publish(
                        package_dir, str(frame.get("runId") or ""), frame["progress"]
                    )
                continue
            if "result" in frame:
                self._clear_crashes(package_dir)
                return frame["result"], False
            if "error" in frame:
                # A raised exception, already structured. No exit codes, no
                # stderr archaeology. The worker is healthy — it caught this and
                # said so — so it goes back in the pool.
                #
                # `error` is the BARE message: the caller splices it into "STEP
                # import failed: {error}" and a person reads the result. The
                # exception class rides alongside as `errorType`, available for
                # a log or a diagnostic panel but never part of the sentence.
                self._clear_crashes(package_dir)
                failure = {"ok": False, "error": str(frame.get("error") or "compile failed")}
                if frame.get("errorType"):
                    failure["errorType"] = str(frame["errorType"])
                return failure, False

    def _crashed(self, worker: _Worker, candidate: str, package_dir: str) -> dict:
        try:
            code = worker.process.wait(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            code = None
        self._discard(worker)
        self._count_crash(package_dir)
        if code is not None and code < 0:
            how = f"signal {-code}"
        elif code is not None:
            how = f"exit code {code}"
        else:
            how = "unknown cause"
        return {
            "ok": False,
            "error": (
                f"the CAD kernel crashed ({how}) while compiling "
                f"{os.path.basename(candidate)}"
            ),
        }
