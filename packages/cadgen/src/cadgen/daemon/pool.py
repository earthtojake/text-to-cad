"""A pool of warm OCP worker processes, owned by the daemon supervisor.

A worker belongs to ONE PROJECT — the directory holding the model script it was spawned
for — for its whole life. That is the load-bearing rule: cad-projects all share the same
top-level module names (``lib``, sibling models), so a worker that served project A and is
then handed project B can build B against A's helpers, and the pre-run module evictions
that guard against it are a scrub rather than a guarantee. Keying the worker by project
means a worker never sees a second project's code at all. See Pool.acquire.

The dispatch rule, which is the rest of the design:

1. This project's worker is free — use it. Warm, the common case.
2. This project's worker is busy — wait for IT, so two builds of one project serialize
   instead of duplicating each other's work.
3. No worker for this project and the pool is below its cap — spawn one and wait for it.
   That caller pays roughly one OCP import, the same as running cold, but the worker
   PERSISTS, so a burst converges to warm instead of paying the import every time.
4. At the cap — evict the least-recently-used project's idle worker and spawn under the
   new key. The cap is an admission budget over projects, not a reuse pool.
5. At the cap with everything busy — wait a short while, then run cold if nothing frees.

Rule 3 used to give up immediately, on the grounds that a queue is what made the old
single-process daemon worse than useless. That lesson was real but it was about a cap of
ONE: with a pool, refusing to wait at all means the cap bounds nothing. Overflow still
runs, so N callers produce N OCP processes no matter what the cap says, and the machine
can be driven into swap by a burst the pool was supposed to govern. A bounded wait puts
the ceiling back without reintroducing the serialisation: nobody blocks indefinitely, and
the cold path is still there the moment waiting stops paying.

The wait is bounded by roughly what running cold would have cost, so waiting is never the
slower choice by much. Jobs are usually short relative to an OCP import, so nearly every
wait ends in a warm worker rather than at the deadline.

Sizing follows the machine rather than a constant. See max_workers().
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import subprocess
import sys
import threading
import time


DEFAULT_RECYCLE_AFTER = 200
DEFAULT_WORKER_IDLE_SECONDS = 300.0
_SPAWN_TIMEOUT_SECONDS = 120.0

# Recency ORDER comes from this counter, not from the clock. time.monotonic()'s
# resolution is ~16 ms on Windows, so a burst of acquire/release cycles -- which
# is what a pool at its cap sees -- stamped several workers with the same
# instant, and min() then broke the tie by list position: the freshly refreshed
# worker was evicted and the actually-least-recent one kept. A strictly
# increasing sequence has no ties on any platform. ``last_used`` stays a clock
# because reap_idle needs an ELAPSED time, which a counter cannot give.
_USE_SEQUENCE = itertools.count()

# A warm worker measures ~281 MB resident on macOS/arm64 once it has served a job (the OCP
# import is lazy, so a freshly spawned one is ~25 MB until then). Adding a SECOND worker
# costs the system only ~50 MB, because OCP's mapped libraries are shared -- so summing RSS
# overstates the real cost by roughly 5x.
#
# The conservative figure is used anyway, deliberately. It only binds on small or
# containerised machines, which is exactly where over-spawning hurts and where the shared
# pages are least likely to save you; on anything roomy the CPU bound below decides first,
# so the pessimism costs nothing there.
WORKER_MEMORY_BYTES = 300 * 1024 * 1024
# Half the box. The rest is for the OS, the caller, the browser the Viewer runs in, and the
# geometry a build allocates on top of a worker's resting footprint.
MEMORY_FRACTION = 0.5
# Past this, more warm processes stop being the bottleneck and start being a liability to
# supervise. Nothing subtle -- just a refusal to let a huge machine spawn absurdly.
MAX_WORKERS_CEILING = 32
# Kept for machines where neither memory nor CPU can be read.
FALLBACK_MAX_WORKERS = 4

# How long a caller waits at the cap before running cold. A first job's OCP import measured
# 0.54 s with a warm page cache, so this is a few times the cost of the thing the caller
# would do instead -- long enough that a short job ahead of it frees a worker, short enough
# that waiting never becomes the expensive option. Cold-cache imports are slower, which is
# an argument for the headroom rather than against the bound.
DEFAULT_WAIT_SECONDS = 2.0


def _env_int(name: str) -> int | None:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return None
    return value if value > 0 else None


def _container_memory_limit() -> int | None:
    """A cgroup memory cap, which is the real limit inside a container.

    Physical RAM is the HOST's there. A 2 GB container on a 128 GB host that sizes itself
    against 128 GB gets OOM-killed, which is the shape of bug the JVM shipped for years
    before UseContainerSupport.
    """
    for path, unlimited in (
        ("/sys/fs/cgroup/memory.max", {"max"}),                  # cgroup v2
        ("/sys/fs/cgroup/memory/memory.limit_in_bytes", set()),  # cgroup v1
    ):
        try:
            with open(path, encoding="utf-8") as handle:
                raw = handle.read().strip()
        except OSError:
            continue
        if raw in unlimited:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        # v1 spells "unlimited" as a huge sentinel rather than a word.
        if 0 < value < (1 << 62):
            return value
    return None


def _physical_memory() -> int | None:
    """Total RAM, or None where it cannot be read.

    TOTAL, never "available": available moves with the page cache and whatever else is
    running, so sizing on it would give the same command a different cap from one run to
    the next and make a report irreproducible. The fraction above is what leaves headroom.
    """
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        pass
    if sys.platform == "win32":  # pragma: no cover - not exercised by the POSIX runners
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    return None


def memory_budget() -> int | None:
    """Bytes this pool may hold in warm workers, or None if RAM cannot be read."""
    physical = _physical_memory()
    limit = _container_memory_limit()
    if limit is not None:
        physical = limit if physical is None else min(physical, limit)
    return None if physical is None else int(physical * MEMORY_FRACTION)


def max_workers() -> int:
    """How many warm workers this machine should hold.

    Memory says what can be held, CPUs say what can usefully run at once, and the smaller
    wins. The flat default this replaced scaled DOWN on small machines but never up, so a
    64 GB workstation and an 8 GB laptop were both given four -- half the cores idle on one,
    and no way to tell without reading the source.
    """
    configured = _env_int("CADGEN_DAEMON_MAX_WORKERS")
    if configured is not None:
        return configured
    by_cpu = (os.cpu_count() or FALLBACK_MAX_WORKERS) - 2
    budget = memory_budget()
    if budget is None:
        return max(1, min(FALLBACK_MAX_WORKERS, by_cpu))
    by_memory = budget // WORKER_MEMORY_BYTES
    return max(1, min(by_memory, by_cpu, MAX_WORKERS_CEILING))


def wait_seconds() -> float:
    """Seconds to wait at the worker cap before telling the caller to run cold."""
    return DEFAULT_WAIT_SECONDS


def _recycle_after() -> int:
    try:
        return max(0, int(os.environ.get("CADGEN_DAEMON_RECYCLE", "")))
    except ValueError:
        return DEFAULT_RECYCLE_AFTER


class WorkerGone(RuntimeError):
    """The worker died or stopped speaking. Its job is lost; the pool replaces it.

    ``exit_status`` is the process's wait status when it had already exited (a
    negative number is the signal that killed it -- -9 is the OOM killer's SIGKILL
    on Linux and macOS alike); None when the pipe closed but the process was still
    running at the moment we looked."""

    def __init__(self, message: str, *, exit_status: int | None = None) -> None:
        super().__init__(message)
        self.exit_status = exit_status


# Windows reports a violent death as the process's exit code -- an NTSTATUS with the
# error severity bits set. These are from Microsoft's ntstatus.h / [MS-ERREF]; verify
# any addition against it, and never gloss a code with a CAUSE the number cannot prove.
_NTSTATUS_NAMES = {
    0xC0000005: "STATUS_ACCESS_VIOLATION",      # the Windows SIGSEGV -- a kernel crash
    0xC0000017: "STATUS_NO_MEMORY",             # confirms the out-of-memory suspicion
    0xC00000FD: "STATUS_STACK_OVERFLOW",        # runaway recursion, not memory pressure
    0xC000013A: "STATUS_CONTROL_C_EXIT",        # the user interrupted it; NOT a crash
    0xC0000374: "STATUS_HEAP_CORRUPTION",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",  # __fastfail / abort-class native fatal
}


def describe_exit(status: int | None) -> str:
    """``exited with code 1`` / ``was killed by SIGKILL (signal 9)`` / ``exited with
    0xC0000005 (STATUS_ACCESS_VIOLATION)`` / ``closed its output while still running``
    -- the evidence a dead worker leaves.

    Windows has no signals for a crash: the kernel kills the process and the
    NTSTATUS becomes its exit code, which rendered as decimal 3221225477 matched
    nothing a user could search. As 0xC0000005 it matches Event Viewer, WER and
    every search result, and the name says whether to suspect memory, recursion
    or their own Ctrl+C."""
    if status is None:
        return "closed its output while still running"
    if status < 0:
        import signal

        try:
            # Windows' Signals enum has no member 9, so the fallback is the
            # ordinary wording there -- it must not stutter `signal 9 (signal 9)`.
            return f"was killed by {signal.Signals(-status).name} (signal {-status})"
        except ValueError:
            return f"was killed by signal {-status}"
    if 0xC0000000 <= status <= 0xFFFFFFFF:
        # A DWORD in the NTSTATUS error range. No os.name test is needed: POSIX
        # cannot produce one (exit codes truncate to 0-255 and signals come back
        # negative), and the upper bound keeps subprocess's sys.maxsize sentinel
        # out of this arm. An unnamed code gets the hex and nothing else -- an
        # invented gloss would be worse than none.
        named = _NTSTATUS_NAMES.get(status)
        return f"exited with 0x{status:08X}" + (f" ({named})" if named else "")
    return f"exited with code {status}"


class Worker:
    """One warm subprocess. Owned by the pool; never shared between concurrent jobs."""

    def __init__(self) -> None:
        env = dict(os.environ)
        # Guards against a worker's own CLI call routing back into the daemon.
        env["CADGEN_DAEMON_CHILD"] = "1"
        # A worker used to be spawned with PYTHONHASHSEED pinned, because ezdxf's
        # emitted order followed string hashing and a warm drawing build had to
        # agree with a cold one. The DXF emitter engineers that agreement now
        # (cadgen._internal.dxf_emit), and a worker whose seed differed from every
        # other process was a divergence waiting to hide the next ordering bug
        # rather than reveal it.
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cadgen.daemon.worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            # utf-8 EXPLICITLY, not the locale's guess: this pipe carries the
            # worker's JSON frames, and on Windows `text=True` alone decodes the
            # ANSI code page. The worker encodes utf-8 (see worker.serve), so a
            # message with a character outside that page arrived as mojibake --
            # cold and warm builds then reported one failure two different ways,
            # which the warm-equivalence test is there to forbid.
            env=env, text=True, encoding="utf-8", errors="backslashreplace", bufsize=1,
        )
        self.jobs_served = 0
        self.busy = False
        self.last_used = time.monotonic()
        self.use_seq = next(_USE_SEQUENCE)
        # The PROJECT this worker belongs to: the directory holding the model
        # script of the first job it served. Set once and never changed --
        # a worker executes exactly one project's code for its whole life.
        # See Pool.acquire for why rebinding is not an option.
        self.project = ""
        ready = self._read_frame(timeout=_SPAWN_TIMEOUT_SECONDS)
        if not ready or "ready" not in ready:
            self.kill()
            raise WorkerGone("worker did not announce itself")
        self.pid = int(ready["ready"])

    def _read_frame(self, timeout: float | None = None) -> dict | None:
        """Frames are newline-delimited JSON; a closed pipe means the worker is gone."""
        line = self.proc.stdout.readline() if self.proc.stdout else ""
        if line == "":
            return None
        try:
            return json.loads(line)
        except ValueError:
            return {"stream": "stderr", "data": line}

    def send(self, request: dict) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise WorkerGone("worker is not running")
        try:
            self.proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise WorkerGone(f"worker stdin closed: {exc}") from exc

    def frames(self):
        """Yield frames until the terminating one, which is yielded last."""
        while True:
            frame = self._read_frame()
            if frame is None:
                status = self._exit_status()
                raise WorkerGone(
                    f"worker {getattr(self, 'pid', self.proc.pid)} {describe_exit(status)}",
                    exit_status=status,
                )
            yield frame
            if "exit" in frame or "result" in frame or "pong" in frame:
                return

    def _exit_status(self) -> int | None:
        """The wait status once the pipe has closed. A dying process closes its
        pipe a moment before the kernel reaps it, so give it that moment."""
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
                # Closing stdin is the polite exit; the worker's read loop ends on EOF.
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
        except OSError:
            pass
        finally:
            # Close the pipes explicitly; a supervisor that churns workers over a long
            # session would otherwise leak a file descriptor pair per worker.
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()


class Pool:
    """Owns every worker. Thread-safe; one lock, held only around bookkeeping."""

    def __init__(self) -> None:
        # A Condition, not a Lock: a caller at the cap sleeps here until release() or a
        # reaper frees a slot, instead of being turned away the moment the pool is full.
        self._cv = threading.Condition()
        self._workers: list[Worker] = []
        # Spawns in flight. Counted against the cap so two callers arriving together
        # cannot both see room for the last worker and both take it -- without this the
        # pool can exceed its own ceiling, which is the one thing it is for.
        self._pending = 0
        # Projects with a spawn in flight. A second request for the same project
        # must wait for that spawn rather than start a second worker for it --
        # otherwise "one project, one worker" holds only when requests are spaced
        # out, which is the opposite of when it matters.
        self._pending_projects: list[str] = []
        self.cold_overflows = 0
        self.crashes = 0
        self.recycles = 0
        self.waits = 0
        self.evictions = 0

    # --- acquisition -------------------------------------------------------------
    def acquire(self, project: str = "") -> Worker | None:
        """A worker to run one job on, or None meaning "run this cold".

        ``project`` is the directory holding the request's model script, and it
        BINDS FOR LIFE: a project's requests are served by its own worker, and a
        request that finds that worker busy WAITS for it rather than fanning out
        — per-project serialization is what stops two builds of one project
        duplicating each other's work, and it keeps that worker's in-memory
        op-memo cache warm for the model.

        The binding is permanent because a worker is a Python process and every
        cad-project shares the same top-level module names (``lib``, sibling
        models). A worker that served project A and is then handed project B has
        A's ``lib`` in ``sys.modules`` and A's directory in the import caches;
        the pre-run evictions scrub that, but they are a scrub, and a scrub that
        misses builds B against A's helpers and reports success. Keying the
        worker by project removes the question instead of answering it: a worker
        never sees a second project's code, so there is nothing to scrub between
        them.

        The cap is therefore an ADMISSION budget over projects, not a reuse pool.
        At the cap a new project EVICTS the least-recently-used project's idle
        worker and spawns a fresh one under its own key. Evicting costs one OCP
        import and loses nothing durable (every session cache writes through to
        the shared store); rebinding would cost nothing and lose correctness.

        A request with no project — ``inspect``/``snapshot`` verbs that name no
        model script — runs no model code, so it takes any free worker and binds
        nothing.
        """
        deadline: float | None = None
        with self._cv:
            while True:
                self._reap_dead_locked()
                bound = self._project_worker_locked(project)
                if bound is not None and not bound.busy:
                    bound.busy = True
                    return bound
                if bound is not None or self._project_is_spawning_locked(project):
                    # The project's worker is busy, or its spawn is still in flight.
                    # Wait for IT rather than starting a second worker on this project.
                    deadline = self._wait_for_project_locked(deadline)
                    if deadline is None:
                        return None
                    continue
                chosen = self._reusable_worker_locked(project)
                if chosen is not None:
                    chosen.busy = True
                    if project:
                        chosen.project = project
                    return chosen
                if len(self._workers) + self._pending < max_workers():
                    self._reserve_spawn_locked(project)
                    break
                if project:
                    # At the cap with no worker for this project. Evict the
                    # least-recently-used project's idle worker and spawn under
                    # the new key; a worker is never handed to a second project.
                    victim = self._lru_idle_worker_locked()
                    if victim is not None:
                        self.evictions += 1
                        self._drop_locked(victim)
                        self._reserve_spawn_locked(project)
                        break
                # At the cap and everything is busy. Wait for someone to finish rather
                # than adding an OCP process to a machine already running as many as
                # it should.
                if deadline is None:
                    budget = wait_seconds()
                    if budget <= 0:
                        self.cold_overflows += 1
                        return None
                    deadline = time.monotonic() + budget
                    self.waits += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.cold_overflows += 1
                    return None
                self._cv.wait(remaining)
        # Spawn outside the lock: it costs an OCP import and must not block acquire().
        try:
            worker = Worker()
        except (OSError, WorkerGone):
            with self._cv:
                self._release_spawn_locked(project)
                self.crashes += 1
                self._cv.notify_all()  # the slot this spawn reserved is free again
            return None
        with self._cv:
            self._release_spawn_locked(project)
            worker.busy = True
            worker.project = project
            self._workers.append(worker)
            # Anyone waiting on this project's spawn can stop waiting -- they will
            # find the worker busy and queue behind it, which is the intended order.
            self._cv.notify_all()
            return worker

    # --- dispatch helpers (all called with the lock held) -------------------------
    def _project_worker_locked(self, project: str) -> Worker | None:
        if not project:
            return None
        return next((w for w in self._workers if w.project == project), None)

    def _project_is_spawning_locked(self, project: str) -> bool:
        return project in self._pending_projects

    def _reusable_worker_locked(self, project: str) -> Worker | None:
        """A free worker this request may run on WITHOUT rebinding it.

        For a project request that means an unbound worker only. For a
        project-less request it means any free worker: such a request executes
        no model code, so whose worker it borrows cannot matter.
        """
        best: Worker | None = None
        for worker in self._workers:
            if worker.busy:
                continue
            if not worker.project:
                return worker
            if project:
                continue  # bound elsewhere, and rebinding is what this class refuses
            if best is None or worker.use_seq < best.use_seq:
                best = worker
        return best

    def _lru_idle_worker_locked(self) -> Worker | None:
        idle = [worker for worker in self._workers if not worker.busy]
        return min(idle, key=lambda worker: worker.use_seq) if idle else None

    def _reserve_spawn_locked(self, project: str) -> None:
        self._pending += 1
        if project:
            self._pending_projects.append(project)

    def _release_spawn_locked(self, project: str) -> None:
        self._pending -= 1
        if project and project in self._pending_projects:
            self._pending_projects.remove(project)

    def _wait_for_project_locked(self, deadline: float | None) -> float | None:
        """Wait for this project's worker; None means "give up and run cold".

        The budget is longer than the at-capacity one: the caller is queueing
        behind ANOTHER BUILD of the same project, which is work it would
        otherwise duplicate, so waiting pays off over a longer horizon.
        """
        if deadline is None:
            budget = wait_seconds() * 4
            if budget <= 0:
                self.cold_overflows += 1
                return None
            deadline = time.monotonic() + budget
            self.waits += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self.cold_overflows += 1
            return None
        self._cv.wait(remaining)
        return deadline

    def release(self, worker: Worker, *, healthy: bool = True) -> None:
        with self._cv:
            worker.busy = False
            worker.last_used = time.monotonic()
            worker.use_seq = next(_USE_SEQUENCE)
            worker.jobs_served += 1
            recycle_after = _recycle_after()
            if not healthy or not worker.alive():
                self.crashes += 0 if healthy else 1
                self._drop_locked(worker)
            elif recycle_after and worker.jobs_served >= recycle_after:
                # Bound OCP's memory growth over a long-lived session.
                self.recycles += 1
                self._drop_locked(worker)
            # A worker went idle, or dropping one freed a slot to spawn into. Either way
            # somebody waiting at the cap can stop waiting; without this they sleep to
            # their deadline and run cold with an idle worker sitting right there.
            # notify_all, not notify: waiters are keyed to DIFFERENT projects now, so
            # waking one arbitrary sleeper can wake the one this release does not help
            # while the one it does help sleeps to its deadline.
            self._cv.notify_all()

    # --- maintenance -------------------------------------------------------------
    def _drop_locked(self, worker: Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        worker.kill()

    def _reap_dead_locked(self) -> None:
        for worker in list(self._workers):
            if not worker.alive():
                self._workers.remove(worker)

    def reap_idle(self) -> None:
        """Drop idle workers down to one, so a finished burst returns the memory."""
        with self._cv:
            self._reap_dead_locked()
            now = time.monotonic()
            idle = [w for w in self._workers if not w.busy and now - w.last_used > DEFAULT_WORKER_IDLE_SECONDS]
            for worker in idle:
                if len(self._workers) <= 1:
                    break
                self._drop_locked(worker)
            self._cv.notify_all()

    def shutdown(self) -> None:
        with self._cv:
            for worker in list(self._workers):
                self._drop_locked(worker)
            # Nobody should still be waiting for a pool that is going away.
            self._cv.notify_all()

    # --- introspection -----------------------------------------------------------
    def snapshot(self) -> dict:
        with self._cv:
            return {
                "maxWorkers": max_workers(),
                "workers": [
                    {
                        "pid": w.pid,
                        "busy": w.busy,
                        "jobsServed": w.jobs_served,
                        "project": w.project,
                    }
                    for w in self._workers
                ],
                "coldOverflows": self.cold_overflows,
                "waits": self.waits,
                "waitSeconds": wait_seconds(),
                "recycles": self.recycles,
                "evictions": self.evictions,
                "crashes": self.crashes,
            }
