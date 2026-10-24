"""The daemon's pool of workers: at most a cap of them alive, requests past it waiting first come
first served, the least recently used idle worker retired to make room, an idle one retired after
the idle time, and a retired script's next build a fresh worker's."""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine.addresses import document_id  # noqa: E402
from cadgen.engine.daemon import Daemon, Pool  # noqa: E402
from cadgen.engine.ids import file_id  # noqa: E402

_PIDS = itertools.count(1)


def _address(name: str) -> str:
    """A script model's address, as the server keys it (the script needs not exist)."""
    from cadgen.engine.addresses import key

    return str(key(f"{name}.py::{name}"))


class Fake:
    """A worker as the pool sees one."""

    def __init__(self, script: str, environment: dict, cwd: str | None) -> None:
        self.script, self.environment, self.cwd = script, environment, cwd
        self.key = os.path.normcase(script)
        self.pid, self.builds = next(_PIDS), 0
        self.leased, self.since, self.used, self.retired, self.stopped = False, 0.0, time.monotonic(), False, False

    def alive(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True


def await_(condition, what: str, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.01)


class PoolTest(unittest.TestCase):
    def pool(self, cap: int, idle: float = 3600.0) -> Pool:
        self.started: list[str] = []

        def start(script: str, environment: dict, cwd: str | None) -> Fake:
            self.started.append(script)
            return Fake(script, environment, cwd)

        return Pool(cap, idle, start)

    def lease_in_turn(self, pool: Pool, script: str, got: list) -> threading.Thread:
        """A request for ``script`` from a thread of its own, once every earlier one is waiting."""
        waiting = pool.waiting()
        thread = threading.Thread(target=lambda: got.append((script, pool.lease(script, {}))), daemon=True)
        thread.start()
        await_(lambda: pool.waiting() == waiting + 1, f"{script} to wait")
        return thread

    def test_requests_past_the_cap_wait_their_turn_first_come_first_served(self) -> None:
        pool = self.pool(1)
        first = pool.lease("a.py", {})
        got: list = []
        later = [self.lease_in_turn(pool, name, got) for name in ("b.py", "c.py")]
        self.assertEqual((pool.waiting(), [w.script for w in pool.workers()]), (2, ["a.py"]), "one alive, two waiting")
        pool.release(first)
        await_(lambda: len(got) == 1, "the first waiting request")
        self.assertEqual(got[0][0], "b.py", "the first to come is the first served")
        self.assertTrue(first.stopped, "the idle worker made room: retired, at the cap")
        self.assertEqual(pool.waiting(), 1)
        pool.release(got[0][1])
        await_(lambda: len(got) == 2, "the second waiting request")
        self.assertEqual(got[1][0], "c.py")
        for thread in later:
            thread.join(5)
        self.assertEqual(self.started, ["a.py", "b.py", "c.py"])
        self.assertEqual([(Path(row["script"]).name, row["reason"]) for row in pool.retired],
                         [("b.py", "LRU"), ("a.py", "LRU")], "the latest retirement first")

    def test_a_busy_script_s_next_build_waits_for_its_worker_and_takes_no_slot(self) -> None:
        pool = self.pool(2)
        a, b = pool.lease("a.py", {}), pool.lease("b.py", {})
        got: list = []
        again = self.lease_in_turn(pool, "a.py", got)  # waits for a's own worker
        other = self.lease_in_turn(pool, "c.py", got)  # waits for a slot: both workers are busy
        pool.release(b)
        await_(lambda: len(got) == 1, "the slot b's worker left")
        self.assertEqual(got[0][0], "c.py")
        self.assertTrue(b.stopped)
        pool.release(a)
        await_(lambda: len(got) == 2, "a's worker, free")
        self.assertIs(got[1][1], a, "a's next build is its warm worker's")
        again.join(5), other.join(5)

    def test_at_the_cap_the_least_recently_used_idle_worker_is_retired(self) -> None:
        pool = self.pool(2)
        a = pool.lease("a.py", {})
        pool.release(a)
        b = pool.lease("b.py", {})
        pool.release(b)
        c = pool.lease("c.py", {})
        self.assertTrue(a.stopped and not b.stopped, "a was used least recently")
        pool.release(c)
        again = pool.lease("a.py", {})
        self.assertIsNot(again, a, "a retired script's next build is a fresh worker's")
        self.assertTrue(b.stopped and not c.stopped)
        self.assertEqual(sorted(w.script for w in pool.workers()), ["a.py", "c.py"])
        self.assertEqual([row["reason"] for row in pool.retired], ["LRU", "LRU"])

    def test_a_worker_idle_past_the_idle_time_is_retired_and_a_busy_one_never(self) -> None:
        pool = self.pool(4, idle=60.0)
        idle, busy = pool.lease("a.py", {}), pool.lease("b.py", {})
        pool.release(idle)
        self.assertEqual(pool.retire_idle(time.monotonic() + 30), [], "not idle long enough")
        self.assertEqual(pool.retire_idle(time.monotonic() + 61), [idle])
        self.assertTrue(idle.stopped and not busy.stopped)
        self.assertEqual([(row["script"], row["reason"]) for row in pool.retired], [("a.py", "idle")])
        self.assertIsNot(pool.lease("a.py", {}), idle)

    def test_only_what_shapes_the_import_system_replaces_a_worker_and_the_rest_is_adopted(self) -> None:
        pool = self.pool(1)
        worker = pool.lease("a.py", {"PATH": "/one", "VIRTUAL_ENV": "/venv", "TURN": "1"})
        pool.release(worker)
        for name in ("PATH", "VIRTUAL_ENV", "TURN", "HOME"):
            again = pool.lease("a.py", {"PATH": "/one", "VIRTUAL_ENV": "/venv", "TURN": "1", name: "/other"})
            pool.release(again)
            self.assertIs(again, worker, f"another {name} is the run's to adopt: the warm worker serves it")
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE",
                     "PYTHONPLATLIBDIR"):
            new = pool.lease("a.py", {name: "1"})
            pool.release(new)
            self.assertTrue(worker.stopped and not new.stopped, f"another {name} is another interpreter")
            self.assertEqual(pool.retired[0]["reason"], "environment")
            worker = new
        self.assertEqual(len(self.started), 7)

    def test_a_gone_or_capped_worker_leaves_the_pool_when_let_go(self) -> None:
        pool = self.pool(2)
        crashed, capped = pool.lease("a.py", {}), pool.lease("b.py", {})
        crashed.stopped = True  # it died during its build
        capped.retired = True  # over its memory cap after its build
        pool.release(crashed), pool.release(capped)
        self.assertEqual(pool.workers(), [])
        self.assertEqual(sorted(row["reason"] for row in pool.retired), ["RSS", "exited"])

    def test_a_worker_that_fails_to_start_gives_its_slot_back(self) -> None:
        def start(script: str, environment: dict, cwd: str | None) -> Fake:
            if script == "bad.py":
                raise RuntimeError("no")
            return Fake(script, environment, cwd)

        pool = Pool(1, 3600.0, start)
        with self.assertRaises(RuntimeError):
            pool.lease("bad.py", {})
        self.assertEqual(pool.lease("good.py", {}).script, "good.py")


class ConnectedPoolTest(unittest.TestCase):
    """The real version-wait lifecycle holds the builder, not unrelated workers."""

    def test_version_wait_and_recent_sync_keep_the_builder_warm(self) -> None:
        from cadgen.engine.serve import LIVE, Server

        with tempfile.TemporaryDirectory() as folder:
            daemon = Daemon(3600, cap=2, retire_after=1)
            daemon.pool.start = Fake
            server = daemon.server = Server(mesh_mode="inline")
            self.addCleanup(daemon.shutdown)
            path = Path(folder).resolve() / "part.xbf"
            ident = server.put(path, {"version": "one", "prototypes": []}, {})
            builder, other = daemon.pool.lease("a.py", {}), daemon.pool.lease("b.py", {})
            daemon.builders[file_id(path)] = builder
            daemon.pool.release(builder)
            daemon.pool.release(other)
            waiting = threading.Event()
            original = server.changed.wait_for

            def wait_for(*args, **kwargs):
                waiting.set()
                return original(*args, **kwargs)

            with mock.patch.object(server.changed, "wait_for", side_effect=wait_for):
                thread = threading.Thread(target=server.wait, args=(ident, "one", 60), daemon=True)
                thread.start()
                try:
                    self.assertTrue(waiting.wait(5), "the page is waiting on the version")
                    # Advance past both clocks: an outstanding wait still wins over LIVE.
                    with mock.patch("time.monotonic", return_value=builder.used + LIVE + 10):
                        self.assertEqual(daemon.pool.retire_idle(), [other])
                        self.assertFalse(builder.stopped)
                finally:
                    server.put(path, {"version": "two", "prototypes": []}, {})
                    thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertFalse(server.watchers, "the completed wait releases its watcher")
            synced = server.synced[ident]
            with mock.patch("time.monotonic", return_value=synced + LIVE - 1):
                self.assertEqual(daemon.pool.retire_idle(), [], "recent sync keeps the worker warm")
            with mock.patch("time.monotonic", return_value=synced + LIVE + 1):
                self.assertEqual(daemon.pool.retire_idle(), [builder], "no watcher: idle retirement")

    def test_the_worker_count_cap_retires_an_unwatched_worker_before_a_watched_one(self) -> None:
        from cadgen.engine.serve import Server

        daemon = Daemon(3600, cap=2)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        watched = daemon.pool.lease("watched.py", {})
        daemon.pool.release(watched)  # used least recently
        unwatched = daemon.pool.lease("unwatched.py", {})
        daemon.pool.release(unwatched)
        server.put(_address("watched"), {"version": "one", "prototypes": []}, {})
        daemon.builders[document_id(_address("watched"))] = watched
        server.sync(_address("watched"))
        third = daemon.pool.lease("third.py", {})
        self.assertTrue(unwatched.stopped, "the unwatched worker made room")
        self.assertFalse(watched.stopped, "a watched worker is not the count cap's victim")
        self.assertEqual([row["reason"] for row in daemon.pool.retired], ["LRU"])

    def test_at_the_cap_with_every_idle_worker_watched_a_new_build_starts_past_the_cap(self) -> None:
        from cadgen.engine.serve import Server

        daemon = Daemon(3600, cap=2)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        watched = []
        for name in ("one", "two"):
            worker = daemon.pool.lease(f"{name}.py", {})
            daemon.pool.release(worker)
            server.put(_address(name), {"version": "one", "prototypes": []}, {})
            daemon.builders[document_id(_address(name))] = worker
            server.sync(_address(name))
            watched.append(worker)
        third = daemon.pool.lease("third.py", {})
        self.assertEqual(len(daemon.pool.workers()), 3, "the cap is exceeded, not met by an eviction")
        self.assertFalse(any(worker.stopped for worker in watched), "the watched workers live")
        self.assertEqual(list(daemon.pool.retired), [])
        # Past the cap, an unwatched idle worker is the next build's victim, the watched ones never.
        daemon.pool.release(third)
        daemon.pool.lease("fourth.py", {})
        self.assertTrue(third.stopped)
        self.assertFalse(any(worker.stopped for worker in watched))
        self.assertEqual([row["reason"] for row in daemon.pool.retired], ["LRU"])

    def test_memory_model_sync_keeps_its_worker_warm(self) -> None:
        from cadgen.engine.serve import LIVE, Server

        daemon = Daemon(3600, cap=1, retire_after=1)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        address = _address("part")
        server.put(address, {"version": "one", "prototypes": []}, {})
        worker = daemon.pool.lease("part.py", {})
        daemon.builders[document_id(address)] = worker
        daemon.pool.release(worker)
        synced = worker.used + 10
        with mock.patch("time.monotonic", return_value=synced):
            server.sync(address)
            self.assertEqual(daemon.pool.retire_idle(), [])
        with mock.patch("time.monotonic", return_value=synced + LIVE + 1):
            self.assertEqual(daemon.pool.retire_idle(), [worker])

    def test_failed_wait_releases_watcher_and_memory_cap_still_retires(self) -> None:
        from cadgen.engine.serve import Server

        daemon = Daemon(3600, cap=1)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "part.xbf"
            ident = server.put(path, {"version": "one", "prototypes": []}, {})
            worker = daemon.pool.lease("a.py", {})
            daemon.builders[file_id(path)] = worker
            with mock.patch.object(server, "document", side_effect=ValueError("unreadable")):
                with self.assertRaisesRegex(ValueError, "unreadable"):
                    server.wait(ident, "one", 60)
            self.assertFalse(server.watchers)
            self.assertTrue(daemon.connected(worker))
            worker.retired = True
            daemon.pool.release(worker)
            self.assertTrue(worker.stopped)
            self.assertEqual(daemon.pool.retired[0]["reason"], "RSS")


GATED = """
import pathlib, time
import build123d as bd
from cadgen.engine import xbf

GATE = pathlib.Path(__file__).with_suffix(".go")


@xbf("XBF/{name}.xbf")
def {name}():
    while {gated} and not GATE.exists():
        time.sleep(0.01)
    return bd.Box({size}, 2, 2)

if __name__ == "__main__":
    {name}()
"""


class DaemonPoolTest(unittest.TestCase):
    """The pool's rules through the daemon, its workers real processes."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-pool-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_IDLE": "120", "CADGEN_ENGINE_MESH": "inline",
                                          "CADGEN_ENGINE_WORKERS": "1"}, self.addCleanup)
        # This process asks the test's daemon what it holds (``status``), never starting one.
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}))
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.cli("stop")
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.folder, env=env or self.env)

    def status(self) -> dict:
        from cadgen.engine.client import request

        return request({"op": "status"}, start=False) or {}

    def script(self, name: str, gated: bool = False, size: int = 2) -> None:
        (self.folder / f"{name}.py").write_text(textwrap.dedent(GATED.format(name=name, gated=gated, size=size)),
                                                encoding="utf-8")

    def launch(self, name: str, env: dict | None = None) -> subprocess.Popen:
        """``python NAME.py``: the daemon builds it."""
        return subprocess.Popen([sys.executable, f"{name}.py"], cwd=self.folder, env=env or self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def build(self, name: str, env: dict | None = None) -> str:
        running = self.launch(name, env)
        out, err = engine_daemon.communicate(running, self.env)
        self.assertEqual(running.returncode, 0, err)
        return out

    def test_builds_past_the_cap_queue_in_order_and_a_retired_script_restarts(self) -> None:
        self.script("a", gated=True)
        self.script("b")
        self.script("c")
        builds = {"a": self.launch("a")}
        await_(lambda: [w["busy"] for w in self.status().get("workers", [])] == [True], "a's build", 120)
        for name, waiting in (("b", 1), ("c", 2)):
            builds[name] = self.launch(name)
            await_(lambda: self.status().get("waiting") == waiting, f"{name} to wait its turn", 120)
        self.assertIn("waiting  2 builds", self.cli("status").stdout)
        (self.folder / "a.go").touch()
        for name, process in builds.items():
            out, err = engine_daemon.communicate(process, self.env)
            self.assertEqual(process.returncode, 0, err)
            self.assertIn(" cold ", out, f"{name}: a worker of its own, started in its turn")
        status = self.status()
        self.assertEqual([Path(w["script"]).name for w in status["workers"]], ["c.py"], "one alive: the cap")
        self.assertEqual([(Path(row["script"]).name, row["reason"]) for row in status["retired"]],
                         [("b.py", "LRU"), ("a.py", "LRU")], "b was served before c")
        # A retired script's next build is a fresh worker's: a restart, which takes its xbf whole.
        self.assertTrue(self.build("a").startswith("took a.py::a cold"))

    def test_a_worker_idle_past_the_idle_time_is_retired(self) -> None:
        env = {**self.env, "CADGEN_ENGINE_WORKERS": "", "CADGEN_ENGINE_WORKER_IDLE": "1"}
        self.script("a")
        self.assertIn(" cold ", self.build("a", env))
        await_(lambda: (self.status().get("retired") or [{}])[0].get("reason") == "idle", "the idle retirement", 60)
        status = self.status()
        self.assertEqual(status["workers"], [])
        self.assertEqual(status["cap"], os.cpu_count(), "the cap is the machine's cores by default")
        self.assertIn(" cold ", self.build("a", env), "its next build is a fresh worker's")


if __name__ == "__main__":
    unittest.main()
