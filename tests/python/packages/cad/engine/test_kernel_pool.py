"""The engine's kernel processes on a Python that starts no thread and joins no spawn pool (the WebAssembly kernel's):
the pools are ``kernel_pool.KernelPool``, kernel processes started as programs and spoken to on their streams, and a
worker reads each request when its loop comes for it. Both are held here on this Python itself -- the pool with this
interpreter as its kernel's, the worker with ``places.THREADS`` false -- so what they do is checked wherever the suite
runs; that a WebAssembly kernel runs them is its host's to show."""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine import kernel_pool, serve  # noqa: E402
from cad.engine.kernel_pool import KernelPool  # noqa: E402


def _echo(value):
    return value


def _pid() -> int:
    return os.getpid()


def _fails(text: str):
    raise ValueError(text)


def _dies() -> None:
    os._exit(3)


def _slow(seconds: float) -> int:
    time.sleep(seconds)
    return os.getpid()


def _warm() -> None:
    os.environ["CAD_TEST_POOL_WARMED"] = "1"


def _warmed() -> str | None:
    return os.environ.get("CAD_TEST_POOL_WARMED")


class KernelPoolTest(unittest.TestCase):
    """The part of a process pool the engine uses, over kernel processes that are programs."""

    def pool(self, workers: int = 2, **options) -> KernelPool:
        # The jobs here are this module's functions: its folder's root on the processes' path, as the engine's is.
        top = str(Path(__file__).resolve().parents[5])
        found = KernelPool(workers, sys.executable, [top, *SRC], **options)
        self.addCleanup(found.terminate_workers)
        return found

    def test_a_job_runs_in_a_kernel_process_and_answers_its_value_or_its_error(self) -> None:
        pool = self.pool()
        self.assertEqual(pool.submit(_echo, {"bytes": b"\x00\xff", "n": 2.5}).result(60), {"bytes": b"\x00\xff", "n": 2.5})
        self.assertNotEqual(pool.submit(_pid).result(60), os.getpid())
        with self.assertRaisesRegex(ValueError, "no such part"):
            pool.submit(_fails, "no such part").result(60)
        # The process that answered an error is the one that answers the next job.
        first = pool.submit(_pid).result(60)
        self.assertEqual(pool.submit(_pid).result(60), first)

    def test_a_pool_holds_at_most_its_processes_and_starts_one_only_for_a_job_none_is_free_for(self) -> None:
        pool = self.pool(8)
        self.assertEqual(pool.workers, kernel_pool.PROCESSES, "a kernel here is a whole host: the pool is capped")
        one = pool.submit(_pid).result(60)
        self.assertEqual({pool.submit(_pid).result(60) for _ in range(3)}, {one}, "an idle process takes the next job")
        together = [pool.submit(_slow, 0.5) for _ in range(kernel_pool.PROCESSES)]
        self.assertEqual(len({job.result(60) for job in together}), kernel_pool.PROCESSES, "jobs asked at once run at once")

    def test_a_process_that_dies_fails_its_job_alone_and_the_next_job_starts_another(self) -> None:
        pool = self.pool(1)
        before = pool.submit(_pid).result(60)
        with self.assertRaises(BrokenProcessPool):
            pool.submit(_dies).result(60)
        after = pool.submit(_pid).result(60)
        self.assertNotEqual(after, before)
        self.assertFalse(pool._broken, "the pool mends itself: its owner makes no new one")

    def test_its_initializer_is_each_process_s_first_act_but_the_spawn_pools_watch(self) -> None:
        self.assertEqual(self.pool(1, initializer=_warm).submit(_warmed).result(60), "1")
        # ``exit_with_parent`` watches a spawned process's parent from a thread; here the closed pipe says it.
        watched = self.pool(1, initializer=serve.exit_with_parent)
        self.assertIsNone(watched.initializer)
        self.assertIsNone(watched.submit(_warmed).result(60))

    def test_shut_down_it_cancels_what_waits_and_its_processes_leave_when_their_input_closes(self) -> None:
        pool = self.pool(1)
        running = pool.submit(_slow, 0.5)
        deadline = time.monotonic() + 60
        while not running.running() and time.monotonic() < deadline:
            time.sleep(0.01)
        waiting = pool.submit(_pid)
        pool.shutdown(wait=False, cancel_futures=True)
        self.assertTrue(waiting.cancelled())
        pid = running.result(60)
        with self.assertRaises(RuntimeError):
            pool.submit(_pid)
        pool.shutdown(wait=True)  # its threads gone: each has closed its process's input and waited for it
        self.assertEqual(pool._children, {})
        if os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_the_engine_s_pool_is_this_one_where_the_kernel_environment_is_webassembly(self) -> None:
        found = {"python": sys.executable, "prefix": sys.prefix, "path": None, "own": False, "wasm": True}
        with mock.patch("cad.engine.places.kernel", return_value=found):
            pool = serve._process_pool(4, initializer=serve.exit_with_parent, max_tasks_per_child=1)
        self.addCleanup(pool.terminate_workers)
        self.assertIsInstance(pool, KernelPool)
        self.assertIs(pool.submit(serve._ready).result(120), True)
        serve._end(pool)  # ended as any pool is


WORKER = textwrap.dedent("""
    import sys
    from cad.engine import places
    places.THREADS = False  # as on the WebAssembly kernel: nothing reads ahead of the loop
    from cad.engine import worker
    sys.exit(worker.main())
""")


class ThreadlessWorkerTest(unittest.TestCase):
    """A worker on a Python that starts no thread: the same protocol, each request read when the loop comes for
    it."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="threadless-worker-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(SRC), "CAD_ENGINE_DIR": str(self.folder / "engine"),
               "CAD_STATE_DIR": str(self.folder / "state"), "CAD_CACHE_DIR": str(self.folder / "cache")}
        self.worker = subprocess.Popen([sys.executable, "-P", "-c", WORKER], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=self.folder)
        self.addCleanup(self._end)

    def _end(self) -> None:
        if self.worker.poll() is None:
            self.worker.kill()
        self.worker.wait(30)
        for stream in (self.worker.stdin, self.worker.stdout):
            try:
                stream.close()
            except OSError:
                pass

    def frame(self) -> dict:
        line = self.worker.stdout.readline()
        self.assertTrue(line, "the worker closed its answers")
        message = json.loads(line)
        if message.get("bytes"):
            message["payload"] = self.worker.stdout.read(message["bytes"])
        return message

    def ask(self, request: dict) -> None:
        self.worker.stdin.write((json.dumps(request) + "\n").encode())
        self.worker.stdin.flush()

    def answer(self, ident: int) -> dict:
        while True:
            message = self.frame()
            if message.get("id") == ident and ("done" in message or "failed" in message or "where" in message):
                return message

    def test_it_says_it_is_ready_answers_each_request_in_turn_and_leaves_when_its_input_closes(self) -> None:
        self.assertEqual(self.frame()["ready"], self.worker.pid)
        # A question about an element is answered by the loop, between requests, not by a thread during one.
        self.ask({"id": 1, "op": "where", "doc": "none", "key": "k", "kind": "face", "ordinal": 1})
        self.assertEqual(self.answer(1), {"id": 1, "where": None})
        self.ask({"id": 2, "op": "nonsense"})
        self.assertIn("unknown request", self.answer(2)["failed"])
        # A build of a script that is not there fails as on any worker, and the worker collects at once after it
        # (it cannot wait for idleness) and says so before it reads the next request.
        self.ask({"id": 3, "op": "build", "script": str(self.folder / "absent.py"), "functions": None,
                  "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("failed", self.answer(3))
        self.assertIn("collected", self.frame())
        self.ask({"id": 4, "op": "nonsense"})
        self.assertIn("unknown request", self.answer(4)["failed"])
        self.worker.stdin.close()
        self.assertEqual(self.worker.wait(60), 0)


class ThreadlessJobsTest(unittest.TestCase):
    """What starts a thread or a process inside a build or a check, on a Python that starts neither: done in the
    one thread, at once."""

    def test_a_mesher_s_job_runs_where_it_is_asked_and_starts_no_thread_and_no_pool(self) -> None:
        from cad.engine import places

        with mock.patch.object(places, "THREADS", False), \
                mock.patch.object(serve, "_process_pool", side_effect=AssertionError("a pool started")), \
                mock.patch.object(serve, "_timed", side_effect=lambda data, parallel: (data[::-1], parallel)):
            mesher = serve.Mesher("processes")
            self.assertEqual(mesher.submit(b"abc").result(0), (b"cba", True))
            self.assertEqual(mesher.run(_echo, 7).result(0), 7)
            failed = mesher.run(_fails, "no such part")
            self.assertIsInstance(failed.exception(0), ValueError)
            self.assertIsNone(mesher._dispatcher)
            self.assertEqual(mesher._inline._threads, set(), "the inline thread was never started")

    def test_a_check_a_caller_measures_itself_is_measured_in_its_own_process(self) -> None:
        import subprocess

        from cad._internal import manufacturing
        from cad.engine import places

        request = {"type": "step", "source": "part.step"}
        with mock.patch.object(places, "THREADS", False), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("a process started")), \
                mock.patch.object(manufacturing, "_measured_here", side_effect=lambda asked: {"measured": asked}):
            self.assertEqual(manufacturing._watched(request), {"measured": request})


class ThreadlessProgressTest(unittest.TestCase):
    def test_no_frame_is_held_where_no_thread_could_send_it_when_its_interval_is_up(self) -> None:
        # A build that says a body's name and then spends a minute in it: the page shows that name, not the one before.
        from cad.engine import progress

        sent: list[dict] = []
        with mock.patch.object(progress, "THREADS", False), mock.patch.object(progress, "INTERVAL", 60.0):
            said = progress.Progress(sent.append, script=Path("model.py"))
            said.load()
            first = len(sent)
            for _ in range(3):
                with said.lock:
                    said._emit()  # well within the interval of the frame before
            self.assertEqual((len(sent), said.held, said.timer), (first + 3, False, None))


if __name__ == "__main__":
    unittest.main()
