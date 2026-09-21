"""The warm worker pool: a worker per model, an extra when it is busy, spares in reserve.

One rule decides routing here: **nothing waits on another build.** A request
for a model whose worker is idle takes that worker. A request for a model whose
worker is busy gets an *extra* — a spare bound to the same model for the length
of one job — and runs now. A request for a model with no worker binds a spare. A
request with no spare left spawns if its memory reservation fits. Admission
counts resident worker trees (including extraction children), keeps headroom
for dependencies, and reclaims idle workers first. That reservation is not
configured: it starts at the seed and is recalibrated on every accounting pass
from the RSS of workers that are idle and have run nothing, which is what a
worker costs before geometry (``memory.worker_baseline``). The dependency
headroom follows from the same number. Exhaustion waits for the
builds in flight to finish (a parent fanning out its children submits them all
at once, and only a core's worth can run) and fails explicitly only when nothing
is running that could release memory. These are soft RSS and
reservation bounds, not a hard limit on a native operation's allocations.
Publication ordering remains the publish rule's concern.

Spares: ``CADGEN_DAEMON_SPARES`` (default 2) workers that have finished importing
build123d and are bound to nothing. Binding one starts a replacement in the
background when memory permits, so a new model's first build pays no import.
A subject-less job borrows one without replacing it. Surplus workers from a
burst remain reusable for two idle seconds, then the periodic sweep restores K.
An extra returns to the spare set when its job ends; a primary stays bound
until idle timeout, memory pressure or recycling reclaims it.

Recycle: a worker is dropped after ``CADGEN_DAEMON_RECYCLE`` jobs (default 1000)
as a leak hedge; its model binds a fresh worker on the next request.

Workers read frames on a thread so every read honours a timeout: a worker that
hangs before announcing itself, or mid-job, is reported instead of blocking its
caller forever.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

from cadgen.daemon.memory import MemoryPolicy, MIB, process_tree_bytes, worker_baseline

DEFAULT_SPARES = 2
DEFAULT_RECYCLE_AFTER = 1000
DEFAULT_IDLE_UNBIND_SECONDS = 600.0
BORROWED_SURPLUS_IDLE_SECONDS = 2.0
SPAWN_TIMEOUT_SECONDS = 120.0
_USE_SEQUENCE = itertools.count()


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def spare_count() -> int:
    value = _env_int("CADGEN_DAEMON_SPARES")
    return max(0, value) if value is not None else DEFAULT_SPARES


def recycle_after() -> int:
    value = _env_int("CADGEN_DAEMON_RECYCLE")
    return max(1, value) if value is not None else DEFAULT_RECYCLE_AFTER


def idle_unbind_seconds() -> float:
    raw = os.environ.get("CADGEN_DAEMON_IDLE_UNBIND", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_IDLE_UNBIND_SECONDS


class WorkerGone(RuntimeError):
    """The worker process ended, or its pipe closed, before the job produced its
    terminal frame. Carries the wait status when the process has been reaped."""

    def __init__(self, message: str, *, exit_status: int | None = None) -> None:
        super().__init__(message)
        self.exit_status = exit_status


class MemoryAdmissionError(RuntimeError):
    """A worker reservation could not fit after idle resources were reclaimed."""


_NTSTATUS_NAMES = {
    0xC0000005: "STATUS_ACCESS_VIOLATION",
    0xC00000FD: "STATUS_STACK_OVERFLOW",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
    0xC0000374: "STATUS_HEAP_CORRUPTION",
    0xC000013A: "STATUS_CONTROL_C_EXIT",
}


def describe_exit(status: int | None) -> str:
    """A worker's death in words: the signal that killed it, or its exit code."""
    if status is None:
        return "closed its output while still running"
    if status < 0:
        import signal

        number = -status
        try:
            name = signal.Signals(number).name
        except ValueError:
            return f"was killed by signal {number}"
        return f"was killed by {name} (signal {number})"
    if os.name == "nt" or status > 255:
        unsigned = status & 0xFFFFFFFF
        name = _NTSTATUS_NAMES.get(unsigned)
        if name:
            return f"exited with 0x{unsigned:08X} ({name})"
        return f"exited with code {status}"
    return f"exited with code {status}"


_TIMED_OUT = object()  # _read_frame: the wait elapsed; distinct from None (pipe closed)


class Worker:
    """One warm subprocess. Owned by the pool; never shared between concurrent jobs."""

    def __init__(self) -> None:
        from cadgen.daemon.client import daemon_address
        from cadgen.daemon.executors import worker_env

        env = worker_env()
        # The broker a worker's jobs take slots from is the daemon itself; name the
        # address explicitly so a worker never guesses it from its identity.
        env["CADGEN_DAEMON_SOCKET"] = daemon_address()
        # A daemon's worker submits its children to the daemon, whatever the process
        # that started the daemon had in its environment.
        env.pop("CADGEN_DAEMON", None)
        # Guards against a worker's own top-level call routing back into the daemon
        # as a fresh request; nested SUBMITS ignore this on purpose (client.run_nested).
        env["CADGEN_DAEMON_CHILD"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cadgen.daemon.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            # Spares can remain idle before their first request.  Start them in the
            # same stable directory worker._park uses between jobs so they never pin
            # the daemon launcher's project cwd on Windows.
            cwd=tempfile.gettempdir(),
            # utf-8 EXPLICITLY: this pipe carries JSON frames and the worker encodes
            # utf-8 (worker.serve), so neither end infers the platform code page.
            env=env, text=True, encoding="utf-8", errors="backslashreplace", bufsize=1,
        )
        self.jobs_served = 0
        self.busy = False
        self.extra = False
        self.last_used = time.monotonic()
        self.use_seq = next(_USE_SEQUENCE)
        # The MODEL this worker is bound to (its script path), "" while a spare.
        self.model = ""
        self._frames: queue.Queue = queue.Queue()
        self._reader = threading.Thread(target=self._pump, name="cadgen-worker-frames", daemon=True)
        self._reader.start()
        ready = self._read_frame(timeout=SPAWN_TIMEOUT_SECONDS)
        if ready is _TIMED_OUT:
            ready = None
        if not ready or "ready" not in ready:
            self.kill()
            raise WorkerGone(
                "worker did not announce itself" + ("" if ready else f" within {SPAWN_TIMEOUT_SECONDS:.0f}s")
            )
        self.pid = int(ready["ready"])

    def _pump(self) -> None:
        stream = self.proc.stdout
        if stream is None:
            self._frames.put(None)
            return
        try:
            for line in stream:
                try:
                    self._frames.put(json.loads(line))
                except ValueError:
                    self._frames.put({"stream": "stderr", "data": line})
        finally:
            # This thread owns stdout's buffered reader.  Closing it from a
            # retirement thread while this loop is blocked in readline waits
            # forever on TextIOWrapper's internal lock when a descendant still
            # holds the pipe open.
            with contextlib.suppress(OSError, ValueError):
                stream.close()
            self._frames.put(None)

    def _read_frame(self, timeout: float | None = None) -> dict | None | object:
        """The next frame; None when the pipe closed; ``_TIMED_OUT`` when ``timeout`` elapsed.

        The two are told apart on purpose: a worker that died is reported by its
        exit status, a worker that is merely quiet by the silence timeout. Folding
        them into one None let a SIGKILLed worker read as "went silent" whenever
        its pipe's EOF arrived a beat before the kernel let it be reaped.
        """
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return _TIMED_OUT

    def send(self, request: dict) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise WorkerGone("worker is not running")
        try:
            self.proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise WorkerGone(f"worker stdin closed: {exc}") from exc

    def frames(self, *, silence_timeout: float | None = None):
        """Yield frames until the terminating one, which is yielded last.

        ``silence_timeout`` bounds the wait for ANY frame; a worker silent that
        long is reported as gone (its process is killed) rather than waited for.
        """
        while True:
            frame = self._read_frame(timeout=silence_timeout)
            if frame is _TIMED_OUT:
                self.kill()
                raise WorkerGone(
                    f"worker {getattr(self, 'pid', self.proc.pid)} went silent for "
                    f"{silence_timeout:.0f}s and was killed"
                )
            if frame is None:
                status = self._exit_status()
                raise WorkerGone(
                    f"worker {getattr(self, 'pid', self.proc.pid)} {describe_exit(status)}",
                    exit_status=status,
                )
            yield frame
            if "exit" in frame or "pong" in frame:
                return

    def _exit_status(self) -> int | None:
        try:
            return self.proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            return None

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        proc = self.proc
        try:
            if proc.poll() is None:
                if proc.stdin is not None:
                    with contextlib.suppress(OSError):
                        proc.stdin.close()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        with contextlib.suppress(subprocess.TimeoutExpired):
                            proc.wait(timeout=2)
        except OSError:
            pass
        finally:
            # stdin has no independent reader.  stdout belongs exclusively to
            # _pump, which closes it after EOF; cross-thread close can deadlock
            # inside the buffered IO lock.
            if proc.stdin is not None:
                with contextlib.suppress(OSError, ValueError):
                    proc.stdin.close()


class Pool:
    """See the module docstring."""

    def __init__(self, clock=time.monotonic, *, policy: MemoryPolicy | None = None, memory_reader=None,
                 in_flight=None) -> None:
        self._cv = threading.Condition()
        self._clock = clock
        self._workers: list[Worker] = []
        self._retiring: list[Worker] = []
        self._active_pending = 0
        self._spares_pending = 0
        self._policy = policy if policy is not None else MemoryPolicy.from_environment()
        # What one worker is estimated to cost. The seed until a never-used idle
        # worker has been measured; recalibrated by every _memory_locked.
        self._reservation = self._policy.seed_bytes
        self._memory_reader = memory_reader or process_tree_bytes
        # How many jobs hold a run slot right now. Each one hands its charge back when
        # it finishes, so admission waits on them instead of refusing.
        self._in_flight = in_flight or (lambda: 0)
        self._stats = {"jobsServed": 0, "imports": 0, "concurrent": 0, "crashes": 0, "recycles": 0, "unbinds": 0,
                       "memoryReclaims": 0, "memoryRefusals": 0}
        self._closed = False

    # --- spares -------------------------------------------------------------------

    def _spawn(self) -> Worker:
        worker = Worker()
        with self._cv:
            self._stats["imports"] += 1
        return worker

    def _spares_locked(self) -> list[Worker]:
        return [w for w in self._workers if not w.model and not w.busy]

    def ensure_spares(self) -> None:
        """Replenish spare capacity, including workers temporarily borrowed."""
        with self._cv:
            if self._closed:
                return
            # Subject-less borrowers return after one job. Replacing them while busy
            # discards each returning warm kernel in favour of a cold import,
            # turning a stream of surface requests into one import per job.
            borrowed = sum(worker.busy and not worker.model for worker in self._workers)
            want = spare_count() - len(self._spares_locked()) - borrowed - self._spares_pending
            if self._policy.limit_bytes:
                snapshot = self._memory_locked()
                available = (self._policy.limit_bytes - snapshot["dependencyReserveBytes"]
                             - snapshot["chargedBytes"])
                want = min(want, max(0, available // max(1, snapshot["workerReservationBytes"])))
            if want <= 0:
                return
            self._spares_pending += want

        def fill(count: int) -> None:
            for _ in range(count):
                try:
                    worker = self._spawn()
                except WorkerGone:
                    worker = None
                with self._cv:
                    self._spares_pending -= 1
                    if worker is not None:
                        if self._closed:
                            worker.kill()
                        else:
                            self._workers.append(worker)
                    self._cv.notify_all()

        threading.Thread(target=fill, args=(want,), name="cadgen-spares", daemon=True).start()

    def _take_spare_locked(self) -> Worker | None:
        spares = self._spares_locked()
        return spares[0] if spares else None

    # --- acquire / release -------------------------------------------------------

    def acquire(self, model: str = "", *, dependency: bool = False) -> Worker:
        """A worker for ``model``, or an explicit memory-admission failure.

        ``model`` is the script path (the routing key); "" means a request with
        no model subject, which borrows a spare without binding it.
        """
        with self._cv:
            if self._closed:
                raise WorkerGone("worker pool is closed")
            self._reap_dead_locked()
            bound = []
            worker = None
            if model:
                bound = [w for w in self._workers if w.model == model and not w.extra]
                idle = [w for w in bound if not w.busy]
                if idle:
                    worker = idle[0]
            if worker is None:
                worker = self._take_spare_locked()
            if worker is not None:
                worker.busy = True  # reserve before releasing the bookkeeping lock
            try:
                self._admit_locked(
                    spawning=worker is None,
                    dependency=dependency,
                    isolated_worker=worker,
                )
            except MemoryAdmissionError:
                if worker is not None:
                    worker.busy = False
                    # Its retained cache may itself be the pressure. This was
                    # idle before our reservation, so retry with a fresh worker.
                    self._stats["memoryReclaims"] += 1
                    self._drop_locked(worker)
                    worker = None
                    self._admit_locked(spawning=True, dependency=dependency)
                else:
                    raise
            if worker is None:
                self._active_pending += 1
        if worker is None:
            try:
                worker = self._spawn()
            except BaseException:
                with self._cv:
                    self._active_pending -= 1
                    self._cv.notify_all()
                raise
            with self._cv:
                self._active_pending -= 1
                if self._closed:
                    worker.kill()
                    raise WorkerGone("worker pool closed while starting a worker")
                worker.busy = True
                self._workers.append(worker)
        with self._cv:
            worker.busy = True
            if model:
                was_bound = worker in bound
                worker.model = model
                # An extra when a primary already exists; a primary otherwise.
                worker.extra = not was_bound and any(
                    w is not worker and w.model == model and not w.extra for w in self._workers
                )
                if worker.extra:
                    self._stats["concurrent"] += 1
            else:
                worker.extra = True  # borrowed; returns to the spare set on release
            self._used_locked(worker)
        self.ensure_spares()
        return worker

    def _memory_locked(self) -> dict:
        self._retiring[:] = [w for w in self._retiring if w.alive()]
        workers = [*self._workers, *self._retiring]
        measured = self._memory_reader([w.pid for w in workers]) if self._policy.limit_bytes else {}
        resident = sum(measured.values())
        # Recalibrate from the workers that have run nothing; the reader is already in hand.
        self._reservation = worker_baseline(
            (measured[w.pid] for w in self._workers
             if not w.busy and not w.jobs_served and w.pid in measured),
            seed=self._policy.seed_bytes,
            previous=self._reservation,
        )
        reservation = self._reservation
        charged = sum(
            max(measured.get(w.pid, reservation), reservation if w.busy else 0)
            for w in workers
        )
        pending = self._active_pending + self._spares_pending
        retiring_bytes = sum(measured.get(w.pid, reservation) for w in self._retiring)
        return {"limitBytes": self._policy.limit_bytes, "residentBytes": resident,
                "chargedBytes": charged + pending * reservation,
                "workerReservationBytes": reservation,
                "dependencyReserveBytes": self._policy.dependency_reserve(reservation),
                "measuredWorkers": len(measured), "unmeasuredWorkers": len(workers) - len(measured),
                "pendingWorkers": pending, "retiringWorkers": len(self._retiring),
                "retiringBytes": retiring_bytes}

    def _reclaim_pressure_locked(self) -> None:
        """Trim newly idle retained caches without waiting for active work."""
        if not self._policy.limit_bytes:
            return
        snapshot = self._memory_locked()
        # Already-retiring workers are charged for admission until they exit,
        # but must not cause us to schedule the same reclamation twice.
        planned = snapshot["chargedBytes"] - snapshot["retiringBytes"]
        ceiling = self._policy.limit_bytes - snapshot["dependencyReserveBytes"]
        idle = sorted((w for w in self._workers if not w.busy), key=lambda w: w.use_seq)
        measured = self._memory_reader([w.pid for w in idle])
        for worker in idle:
            if planned <= ceiling:
                break
            planned -= measured.get(worker.pid, snapshot["workerReservationBytes"])
            self._stats["memoryReclaims"] += 1
            self._drop_locked(worker)

    def _admit_locked(
        self,
        *,
        spawning: bool,
        dependency: bool,
        isolated_worker: Worker | None = None,
    ) -> None:
        if not self._policy.limit_bytes:
            return
        deadline = time.monotonic() + 5.0  # wait only for idle-process teardown
        stalled_since = None
        while True:
            # Each pass recalibrates, so a reservation and the headroom derived
            # from it track what the workers now resident actually cost.
            snapshot = self._memory_locked()
            usage = snapshot["chargedBytes"]
            additional = snapshot["workerReservationBytes"] if spawning else 0
            ceiling = self._policy.limit_bytes - (0 if dependency else snapshot["dependencyReserveBytes"])
            if usage + additional <= ceiling:
                return
            idle = sorted((w for w in self._workers if not w.busy), key=lambda w: w.use_seq)
            if idle:
                self._stats["memoryReclaims"] += 1
                self._drop_locked(idle[0])
                continue
            if self._retiring and time.monotonic() < deadline:
                self._cv.wait(timeout=0.05)
                continue
            # The measured retained cache of the selected worker can be larger
            # than the normal build allowance.
            # It may use the dependency reserve only when it is literally the
            # sole charge. If it later asks for a child, that admission fails
            # explicitly while the parent and its geometry remain alive.
            if not dependency:
                sole_charge = (
                    not self._retiring
                    and not self._active_pending
                    and not self._spares_pending
                    and (
                        self._workers == [isolated_worker]
                        if isolated_worker is not None
                        else not self._workers
                    )
                )
                if sole_charge and usage + additional <= self._policy.limit_bytes:
                    return
            # A build holding a run slot finishes and releases its worker; a spawn
            # still starting becomes such a build. Wait for them. Only when nothing
            # is in flight can no wait help: every busy worker is then a parent kept
            # alive by the geometry it retains for its children.
            if self._in_flight() or self._active_pending or self._spares_pending:
                stalled_since = None
                self._cv.wait(timeout=0.05)
                continue
            now = time.monotonic()
            stalled_since = stalled_since or now
            if now - stalled_since < 2.0:  # a freshly spawned worker takes a moment to claim its slot
                self._cv.wait(timeout=0.05)
                continue
            self._stats["memoryRefusals"] += 1
            raise MemoryAdmissionError(
                f"cadgen memory admission: {usage / MIB:.0f} MiB charged plus "
                f"{additional / MIB:.0f} MiB requested exceeds the "
                f"{ceiling / MIB:.0f} MiB {'dependency' if dependency else 'build'} allowance "
                f"({self._policy.limit_bytes / MIB:.0f} MiB total). "
                "Idle workers were reclaimed; active builds retain their geometry and nothing "
                "is running that could release memory. "
                "An oversized reservation may use the total allowance only while it is the sole charge. "
                "Increase CADGEN_MEMORY_MB or reduce the workload."
            )

    def _used_locked(self, worker: Worker) -> Worker:
        worker.last_used = self._clock()
        worker.use_seq = next(_USE_SEQUENCE)
        return worker

    def unbind_idle(self) -> None:
        """A bound worker idle for ``idle_unbind_seconds()`` returns to the spare set
        (spares beyond K exit). Its model's next build rebinds a spare -- no import
        repaid, a cold RAM op-memo tier. This only releases process state;
        persistent cache objects remain available to the replacement worker.

        Subject-less burst workers get a much shorter grace so the next browser
        poll can reuse their warm kernels. Once that grace expires, this same
        periodic sweep returns the idle spare set to K.
        """
        limit = idle_unbind_seconds()
        with self._cv:
            now = self._clock()
            for worker in list(self._workers):
                if not worker.model or worker.busy or worker.extra:
                    continue
                if now - worker.last_used < limit:
                    continue
                self._stats["unbinds"] += 1
                if len(self._spares_locked()) + self._spares_pending >= spare_count():
                    self._drop_locked(worker)
                else:
                    worker.model = ""
            # Keep the K most recently used spares. Any additional unbound
            # workers came from a subject-less burst: model-bound extras and
            # idle unbinding still enforce K at release/unbind time. A brief
            # grace bridges the viewer's asynchronous result poll without
            # increasing the daemon's settled worker count.
            spares = sorted(self._spares_locked(), key=lambda worker: worker.last_used, reverse=True)
            for worker in spares[spare_count():]:
                if now - worker.last_used >= BORROWED_SURPLUS_IDLE_SECONDS:
                    self._drop_locked(worker)

    def release(self, worker: Worker, *, healthy: bool = True) -> None:
        with self._cv:
            borrowed = worker.extra and not worker.model
            worker.busy = False
            worker.last_used = self._clock()
            worker.jobs_served += 1
            self._stats["jobsServed"] += 1
            if not healthy or not worker.alive():
                if not healthy:
                    self._stats["crashes"] += 1
                self._drop_locked(worker)
            elif worker.jobs_served >= recycle_after():
                self._stats["recycles"] += 1
                self._drop_locked(worker)
            elif worker.extra:
                # A subject-less compile still has model == "" after clearing
                # busy above. Let a burst retain already-admitted warm workers
                # briefly so asynchronous clients can submit their next wave
                # without repaying imports. Explicit K=0 still retires them
                # immediately. Model-bound extras keep the exact K-sized warm
                # reserve semantics below.
                other_spares = sum(spare is not worker for spare in self._spares_locked())
                if borrowed and spare_count() > 0:
                    worker.model = ""
                    worker.extra = False
                elif other_spares + self._spares_pending >= spare_count():
                    # The spare set is already full (a replacement was started when this
                    # one was taken); keeping it too would grow the set by one per extra.
                    self._drop_locked(worker)
                else:
                    # Back to the spare set: unbound, idle, warm.
                    worker.model = ""
                    worker.extra = False
            self._reclaim_pressure_locked()
            self._cv.notify_all()
        self.ensure_spares()

    def _drop_locked(self, worker: Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if worker not in self._retiring:
            self._retiring.append(worker)

        def retire():
            try:
                worker.kill()
            finally:
                with self._cv:
                    self._cv.notify_all()

        threading.Thread(target=retire, daemon=True).start()

    def _reap_dead_locked(self) -> None:
        for worker in list(self._workers):
            if not worker.alive() and not worker.busy:
                self._drop_locked(worker)

    def reap_dead(self) -> None:
        with self._cv:
            self._reap_dead_locked()

    def shutdown(self) -> None:
        with self._cv:
            self._closed = True
            workers, self._workers = [*self._workers, *self._retiring], []
            self._retiring = []
        for worker in workers:
            worker.kill()

    def snapshot(self) -> dict:
        with self._cv:
            workers = [
                {
                    "pid": getattr(w, "pid", None),
                    "model": w.model,
                    "busy": w.busy,
                    "extra": w.extra,
                    "jobs": w.jobs_served,
                }
                for w in self._workers
            ]
            return {
                "workers": workers,
                "spares": len(self._spares_locked()),
                "sparesPending": self._spares_pending,
                "sparesWanted": spare_count(),
                "memory": self._memory_locked(),
                **self._stats,
            }
