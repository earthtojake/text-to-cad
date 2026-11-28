"""The engine's pool jobs on a kernel that starts no process pool: the WebAssembly kernel.

The meshing and reading pools (``serve``) are spawn pools: ``multiprocessing`` starts each process from the engine's
own, handing it pipes and semaphores by number, which a Python on WebAssembly cannot take (no ``_multiprocessing``,
no inherited descriptors). ``KernelPool`` is the part of ``concurrent.futures.ProcessPoolExecutor`` those pools use
-- ``submit``, ``shutdown``, ``terminate_workers`` -- over kernel processes started as programs, each this module
run by the kernel's Python (``python -P -m cad.engine.kernel_pool``) and spoken to on its standard streams:

    a job     8 bytes, the length (big-endian), then that many of ``pickle.dumps((fn, args))``
    its answer  the same frame of ``("done", value)`` or ``("failed", error)``

``fn`` is one of the engine's module-level functions (``serve._timed``, ``serve._read_document``...), pickled by its
name, so the process imports the engine's code from its own path as a spawned one does. A process runs one job at a
time and exits when its input closes: when the pool lets it go, or when the engine that started it is gone, however
it ended (what ``serve.exit_with_parent`` does for a spawned process).

A kernel here is a whole WebAssembly host holding its own copy of the kernel (over a gigabyte of the computer's
memory), so a pool holds at most ``PROCESSES`` of them whatever it was asked for, and keeps a process for its next
job where a spawn pool would replace it (``max_tasks_per_child``): starting one costs seconds, not the tenth of one
a native process does.
"""

from __future__ import annotations

import concurrent.futures
import os
import pickle
import struct
import subprocess
import sys
import threading
from collections import deque
from typing import Any, Callable

__all__ = ["PROCESSES", "KernelPool", "main"]

# The most processes one pool holds: each is a host with the whole kernel in it.
PROCESSES = 2
_LENGTH = struct.Struct(">Q")


def _write(stream: Any, value: Any) -> None:
    data = pickle.dumps(value, protocol=4)  # a protocol both the engine's Python and the kernel's read
    stream.write(_LENGTH.pack(len(data)))
    stream.write(data)
    stream.flush()


def _read(stream: Any) -> Any:
    head = stream.read(_LENGTH.size)
    if len(head) < _LENGTH.size:
        raise EOFError
    (length,) = _LENGTH.unpack(head)
    data = stream.read(length)
    if len(data) < length:
        raise EOFError
    return pickle.loads(data)


class _Job:
    def __init__(self, fn: Callable, args: tuple) -> None:
        self.fn, self.args = fn, args
        self.future: concurrent.futures.Future = concurrent.futures.Future()


class KernelPool:
    """``workers`` kernel processes at most (``PROCESSES`` at most), each started for the first job no started
    one is free for. ``python``: the kernel's Python; ``path``: the import path its processes are given (the
    engine's own folder, as a kernel process the server starts is given it)."""

    def __init__(self, workers: int, python: str, path: list[str], *, initializer: Callable | None = None,
                 max_tasks_per_child: int | None = None) -> None:
        self.workers = max(1, min(int(workers), PROCESSES))
        self.python, self.path = python, list(path)
        # A spawn pool's initializer watches for its parent's end from a thread; here the closed pipe says it.
        # Any other (the readers' warm-up) is the process's first act.
        self.initializer = None if getattr(initializer, "__name__", "") == "exit_with_parent" else initializer
        self._waiting: deque[_Job] = deque()
        self._wake = threading.Condition()
        self._threads: list[threading.Thread] = []
        self._idle = 0
        self._children: dict[int, subprocess.Popen] = {}
        self._stopped = False
        self._broken = False  # read by the pools' owners: a broken spawn pool is made again; this one mends itself

    # --- the executor's part ----------------------------------------------------------------------------------

    def submit(self, fn: Callable, /, *args: Any) -> concurrent.futures.Future:
        job = _Job(fn, args)
        with self._wake:
            if self._stopped:
                raise RuntimeError("cannot schedule new futures after shutdown")
            self._waiting.append(job)
            if self._idle == 0 and len(self._threads) < self.workers:
                thread = threading.Thread(target=self._serve, name=f"cad-kernel-pool-{len(self._threads)}", daemon=True)
                self._threads.append(thread)
                thread.start()
            self._wake.notify()
        return job.future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self._wake:
            self._stopped = True
            if cancel_futures:
                while self._waiting:
                    self._waiting.popleft().future.cancel()
            self._wake.notify_all()
            threads = list(self._threads)
        if wait:
            for thread in threads:
                thread.join()

    def terminate_workers(self) -> None:
        """Every job cancelled and every process ended now, a busy one too (``serve._end``)."""
        self.shutdown(wait=False, cancel_futures=True)
        with self._wake:
            children = list(self._children.values())
        for child in children:
            try:
                child.kill()
            except OSError:
                pass

    # --- one process and the thread that speaks to it -----------------------------------------------------------

    def _start(self) -> subprocess.Popen:
        from cad.engine import places

        env = dict(os.environ)
        listed = [*self.path, *[item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]]
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(listed))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        child = subprocess.Popen([self.python, "-P", "-m", "cad.engine.kernel_pool"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, env=env, **places.windowless())
        if self.initializer is not None:
            _write(child.stdin, (self.initializer, ()))
            _read(child.stdout)  # its warm-up's answer, whatever it is: a job that fails says so itself
        return child

    def _serve(self) -> None:
        child: subprocess.Popen | None = None
        ident = threading.get_ident()
        try:
            while True:
                with self._wake:
                    self._idle += 1
                    while not self._waiting and not self._stopped:
                        self._wake.wait()
                    self._idle -= 1
                    if not self._waiting:
                        return  # stopped, and nothing left to run
                    job = self._waiting.popleft()
                if not job.future.set_running_or_notify_cancel():
                    continue
                try:
                    if child is None or child.poll() is not None:
                        child = self._start()
                        with self._wake:
                            self._children[ident] = child
                    _write(child.stdin, (job.fn, job.args))
                    kind, value = _read(child.stdout)
                except BaseException as error:  # noqa: BLE001 - a process that did not start, or died in the job
                    code = None if child is None else child.poll()
                    if child is not None and code is None:
                        child.kill()
                    child = None
                    from concurrent.futures.process import BrokenProcessPool

                    job.future.set_exception(BrokenProcessPool(
                        f"a kernel process of the pool ended during a job ({type(error).__name__}: {error}"
                        f"{'' if code is None else f'; exit {code}'})"))
                    continue
                if kind == "done":
                    job.future.set_result(value)
                else:
                    job.future.set_exception(value)
        finally:
            if child is not None:
                try:
                    child.stdin.close()  # its input closed: it exits
                except OSError:
                    pass
            with self._wake:
                self._children.pop(ident, None)


def main() -> int:
    """A pool's kernel process: each job as it comes, until the input closes. What a job prints goes to the
    process's error stream; the answers alone are written where the pool reads."""
    answers = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    asked = sys.stdin.buffer
    while True:
        try:
            fn, args = _read(asked)
        except EOFError:
            return 0
        try:
            answer = ("done", fn(*args))
        except BaseException as error:  # noqa: BLE001 - the job's failure is its answer
            answer = ("failed", error)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                _write(answers, ("failed", RuntimeError(f"{type(error).__name__}: {error}")))
                return 1
        try:
            _write(answers, answer)
        except (pickle.PicklingError, TypeError, AttributeError) as error:
            # A value or an error no pickle carries: said in words, as a spawn pool says it.
            _write(answers, ("failed", RuntimeError(f"{type(answer[1]).__name__}: {answer[1]} "
                                                    f"(not sent as it is: {error})")))


if __name__ == "__main__":
    sys.exit(main())
