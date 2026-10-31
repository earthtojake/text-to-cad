"""The daemon's pool of workers: at most a cap of them alive, requests past it waiting first come
first served, the least recently used idle worker retired to make room, workers retired for memory
and never on a timer, the standby a new script's build takes, and a retired script's next build a
fresh worker's."""

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
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.addresses import document_id  # noqa: E402
from cad_server.engine.daemon import Daemon, Pool  # noqa: E402

_PIDS = itertools.count(1)


def _address(name: str) -> str:
    """A script model's address, as the server keys it (the script needs not exist)."""
    from cad.engine.addresses import key

    return str(key(f"{name}.py::{name}"))


class Fake:
    """A worker as the pool sees one."""

    def __init__(self, script: str, environment: dict, cwd: str | None, rss: float | None = 100.0) -> None:
        self.script, self.environment, self.cwd = script, environment, cwd
        self.key = os.path.normcase(script)
        self.pid, self.builds, self.rss, self.started = next(_PIDS), 0, rss, time.time()
        self.leased, self.since, self.used, self.retired, self.stopped = False, 0.0, time.monotonic(), False, False

    def alive(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True

    def adopt(self, script: str, environment: dict, cwd: str | None) -> None:
        self.script, self.environment, self.cwd, self.key = script, environment, cwd, os.path.normcase(script)


def await_(condition, what: str, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.01)


class PoolTest(unittest.TestCase):
    def pool(self, cap: int, memory: float | None = None) -> Pool:
        self.started: list[str] = []

        def start(script: str, environment: dict, cwd: str | None) -> Fake:
            self.started.append(script)
            return Fake(script, environment, cwd)

        return Pool(cap, start, memory=lambda: memory)

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
        self.assertIsNone(pool.free_for(a), "busy, and a request waits for it")
        pool.release(a)
        await_(lambda: len(got) == 2, "a's worker, free")
        self.assertIs(got[1][1], a, "a's next build is its warm worker's")
        self.assertIsNone(pool.free_for(a), "taken by the request that waited")
        pool.release(a)
        self.assertGreaterEqual(pool.free_for(a), 0.0, "free, and nothing waits for it: how long")
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

    def test_over_the_memory_cap_the_least_recently_used_idle_worker_goes_and_a_busy_one_never(self) -> None:
        pool = self.pool(4, memory=250.0)
        old, recent, busy = pool.lease("a.py", {}), pool.lease("b.py", {}), pool.lease("c.py", {})
        pool.release(old)  # 300 MB in all: over the cap, so the least recently used goes
        self.assertTrue(old.stopped)
        pool.release(recent)
        self.assertEqual([w.script for w in pool.workers()], ["b.py", "c.py"], "200 MB: under the cap, both stay")
        busy.rss = 400.0  # alone over the cap while it builds: the idle one goes, and it stays busy
        self.assertEqual(pool.shed(), [recent])
        self.assertFalse(busy.stopped)
        self.assertEqual([(row["script"], row["reason"]) for row in pool.retired], [("b.py", "RSS"), ("a.py", "RSS")])
        self.assertIsNot(pool.lease("a.py", {}), old, "a retired script's next build is a fresh worker's")

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

        pool = Pool(1, start)
        with self.assertRaises(RuntimeError):
            pool.lease("bad.py", {})
        self.assertEqual(pool.lease("good.py", {}).script, "good.py")


class StandbyTest(unittest.TestCase):
    """The pool's standby: a worker with the kernel loaded that a new script's build takes."""

    def pool(self, cap: int = 4, memory: float | None = None, gate: threading.Event | None = None) -> Pool:
        self.started: list[str] = []

        def start(script: str, environment: dict, cwd: str | None) -> Fake:
            self.started.append(script)
            return Fake(script, environment, cwd)

        def spare(environment: dict) -> Fake:
            if gate is not None:
                gate.wait(30)
            return Fake("standby", environment, None, rss=440.0)

        pool = Pool(cap, start, memory=lambda: memory)
        pool.spare = spare
        self.addCleanup(pool.stop)
        return pool

    def standing(self, pool: Pool, besides: Fake | None = None) -> Fake:
        await_(lambda: pool.standby is not None and pool.standby is not besides, "the standby")
        return pool.standby

    def test_a_new_script_takes_the_standby_of_its_interpreter_and_another_stands_by(self) -> None:
        pool = self.pool()
        pool.stand({"PATH": "/one"})
        spare = self.standing(pool)
        worker = pool.lease("/w/a.py", {"PATH": "/two", "TURN": "1"}, "/w")
        self.assertIs(worker, spare, "the standby is a.py's worker")
        self.assertEqual((worker.key, worker.environment, worker.cwd),
                         (os.path.normcase("/w/a.py"), {"PATH": "/two", "TURN": "1"}, "/w"), "as a fresh one of it")
        self.assertEqual(self.started, [], "no worker started for it")
        again = self.standing(pool, spare)
        self.assertEqual(again.environment, {"PATH": "/two", "TURN": "1"}, "the next in the taker's environment")
        pool.release(worker)
        self.assertIs(pool.lease("/w/a.py", {}), worker, "from then on a.py's warm worker")

    def test_another_interpreter_starts_a_fresh_worker_and_the_standby_follows_it(self) -> None:
        pool = self.pool()
        pool.stand({})
        spare = self.standing(pool)
        worker = pool.lease("b.py", {"PYTHONPATH": "/other"})
        self.assertEqual(self.started, ["b.py"])
        self.assertIsNot(worker, spare)
        self.assertTrue(spare.stopped, "a standby of another interpreter goes")
        self.assertEqual(self.standing(pool, spare).environment, {"PYTHONPATH": "/other"})
        self.assertEqual(list(pool.retired), [], "the standby is never a script's retirement")

    def test_a_build_arriving_while_the_standby_starts_waits_for_it_and_a_long_wait_is_said(self) -> None:
        gate = threading.Event()
        pool = self.pool(gate=gate)
        pool.stand({})
        got: list = []
        said: list = []
        with mock.patch("cad.engine.worker.KERNEL_PATIENCE", 0.01):
            thread = threading.Thread(target=lambda: got.append(pool.lease("a.py", {}, None, said.append)), daemon=True)
            thread.start()
            await_(lambda: said, "the wait for the standby's kernel to be said")
        self.assertEqual(said, ["loading the CAD kernel for the first time in this environment, up to a minute"])
        self.assertEqual(self.started, [], "no second kernel load beside the standby's")
        gate.set()
        thread.join(5)
        self.assertEqual((got[0].script, self.started, len(said)), ("a.py", [], 1))
        pool.release(got[0])
        pool.lease("a.py", {}, None, said.append)  # its warm worker: nothing waits, nothing is said
        self.assertEqual(len(said), 1)

    def test_the_standby_holds_a_slot_and_is_the_first_to_make_room(self) -> None:
        pool = self.pool(cap=2)
        pool.stand({})
        a = pool.lease("a.py", {})  # the standby, taken
        pool.release(a)
        spare = self.standing(pool, a)
        b = pool.lease("b.py", {"PYTHONPATH": "/other"})  # the cap is a and the standby: one goes
        self.assertTrue(spare.stopped and not a.stopped, "the standby made room, not a's idle worker")
        self.assertEqual([w.script for w in pool.workers()], ["a.py", "b.py"])
        self.assertIsNone(pool.standby, "no room for another")
        self.assertEqual(b.environment, {"PYTHONPATH": "/other"})

    def test_memory_retires_the_standby_before_any_script_s_worker(self) -> None:
        pool = self.pool(memory=1000.0)
        pool.stand({})
        worker = pool.lease("a.py", {})
        worker.rss = 600.0
        spare = self.standing(pool, worker)
        pool.release(worker)  # 1040 MB: over the cap, and the standby goes first
        self.assertTrue(spare.stopped and not worker.stopped)
        self.assertEqual([(row["script"], row["reason"]) for row in pool.retired], [("standby", "RSS")])
        worker.rss = 400.0
        pool.stand({})
        spare = self.standing(pool)
        self.assertEqual(pool.shed(pressure=True), [spare], "under pressure the standby goes at once; 400 MB "
                                                            "is under half the cap, so a's worker stays")
        self.assertFalse(worker.stopped)
        self.assertEqual(pool.retired[0]["reason"], "pressure")


    def test_under_memory_pressure_no_standby_starts_to_be_retired_again(self) -> None:
        pool = self.pool()
        under = [True]
        pool.pressed = lambda: under[0]
        pool.stand({})
        worker = pool.lease("a.py", {})  # a build under pressure: its own worker, and no standby after it
        pool.release(worker)
        self.assertEqual(self.started, ["a.py"])
        self.assertIsNone(pool.readying, "no kernel loaded for the pressure poller to retire")
        self.assertIsNone(pool.standby)
        under[0] = False
        pool.release(pool.lease("b.py", {}))
        self.standing(pool)

    def test_the_pressure_switch_answers_for_the_host_and_anything_else_is_refused(self) -> None:
        # CADGEN_ENGINE_PRESSURE is Pressure.simulate for a daemon in another process.
        from cad_server.engine import daemon as engine

        for value, simulated in (("0", False), ("1", True), ("", None), (None, None)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"CADGEN_ENGINE_PRESSURE": value or ""}):
                if value is None:
                    os.environ.pop("CADGEN_ENGINE_PRESSURE")
                made = Daemon(cap=1)
                self.addCleanup(made.shutdown)
                self.assertEqual(made.pressure.simulated, simulated, "unset: the system's signal, measured")
                if simulated is not None:
                    self.assertEqual((made.pressure.under(), made.pool.pressed()), (simulated, simulated))
        folder = Path(tempfile.mkdtemp(prefix="eng-"))
        self.addCleanup(shutil.rmtree, folder, True)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_PRESSURE": "yes", "CADGEN_ENGINE_DIR": str(folder)}):
            with self.assertRaisesRegex(ValueError, "CADGEN_ENGINE_PRESSURE is 'yes': 0 .*, 1 .*, or unset"):
                Daemon(cap=1)
            with mock.patch("sys.stderr"):
                self.assertEqual(engine.main([]), 1, "refused at the start")
            self.assertIn("CADGEN_ENGINE_PRESSURE is 'yes'", json.loads(engine.failure_path().read_text(encoding="utf-8"))["reason"])

    def test_status_shows_the_standby_with_its_memory_and_never_as_a_script_s_worker(self) -> None:
        from cad_server.engine.cli import status_text

        daemon = Daemon(cap=4)
        daemon.pressure.simulate(False)  # this machine's memory pressure would keep any standby from starting
        daemon.pool.start = Fake
        self.addCleanup(daemon.shutdown)
        daemon.pool.spare = lambda environment: Fake("standby", environment, None, rss=440.0)
        daemon.pool.stand({})
        self.standing(daemon.pool)
        worker = daemon.pool.lease("/w/tube.py", {"PYTHONPATH": "/other"})  # a fresh worker; the standby follows
        daemon.pool.release(worker)
        spare = self.standing(daemon.pool)
        answer = daemon.status()
        self.assertEqual([Path(w["script"]).name for w in answer["workers"]], ["tube.py"])
        self.assertEqual((answer["standby"]["pid"], answer["standby"]["rssMb"], answer["rssMb"]), (spare.pid, 440, 540))
        self.assertNotIn("workerIdle", answer, "no idle time to report")
        lines = status_text(answer).splitlines()
        self.assertIn("workers 2/4 with the standby", lines[0])
        self.assertIn("RSS 0.5 GB of", lines[0])
        self.assertRegex(lines[2], rf"^  standby +{spare.pid}  +0\.4 GB  kernel loaded · \d+s$")


class ConnectedPoolTest(unittest.TestCase):
    """The real version-wait lifecycle holds the builder, not unrelated workers."""

    def test_version_wait_and_recent_sync_keep_the_builder_warm(self) -> None:
        from cad.engine.serve import LIVE, Server

        daemon = Daemon(cap=2)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        path = _address("a")  # the model document a's worker built
        ident = server.put(path, {"version": "one", "prototypes": []}, {})
        builder, other = daemon.pool.lease("a.py", {}), daemon.pool.lease("b.py", {})
        daemon.builders[ident] = builder
        daemon.pool.release(builder)  # the least recently used, and under the cap alone
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
                # Past LIVE and a day on: an outstanding wait still marks it watched.
                daemon.pool.memory = lambda: 150.0  # two workers of 100 MB: one is over
                with mock.patch("time.monotonic", return_value=builder.used + 24 * 3600):
                    daemon.pool.release(other)
                    self.assertTrue(other.stopped, "over the cap, the unwatched worker goes")
                    self.assertFalse(builder.stopped, "the watched one, least recently used, stays")
            finally:
                server.put(path, {"version": "two", "prototypes": []}, {})
                thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertFalse(server.watchers, "the completed wait releases its watcher")
        synced = server.synced[ident]
        with mock.patch("time.monotonic", return_value=synced + LIVE - 1):
            self.assertTrue(daemon.connected(builder), "a recent sync keeps it watched")
        with mock.patch("time.monotonic", return_value=synced + LIVE + 1):
            self.assertFalse(daemon.connected(builder))
        builder.rss = 200.0
        self.assertEqual(daemon.pool.shed(), [builder], "alone over the cap, a watched one goes too")

    def test_a_day_idle_under_the_memory_cap_keeps_every_worker(self) -> None:
        daemon = Daemon(cap=2)
        daemon.pool.start = Fake
        daemon.pool.memory = lambda: 1000.0
        self.addCleanup(daemon.shutdown)
        worker = daemon.pool.lease("a.py", {})
        daemon.pool.release(worker)
        with mock.patch("time.monotonic", return_value=worker.used + 24 * 3600):
            daemon.tend()
        self.assertEqual((daemon.pool.workers(), worker.stopped), ([worker], False), "no timer retires a worker")

    def test_the_worker_count_cap_retires_an_unwatched_worker_before_a_watched_one(self) -> None:
        from cad.engine.serve import Server

        daemon = Daemon(cap=2)
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
        from cad.engine.serve import Server

        daemon = Daemon(cap=2)
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

    def test_failed_wait_releases_watcher_and_memory_cap_still_retires(self) -> None:
        from cad.engine.serve import Server

        daemon = Daemon(cap=1)
        daemon.pool.start = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        ident = server.put(_address("a"), {"version": "one", "prototypes": []}, {})
        worker = daemon.pool.lease("a.py", {})
        daemon.builders[ident] = worker
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
from cad.engine import xbf

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
        # Its engine, its registry of documents and its cache are its own, never the developer's.
        own = Path(tempfile.mkdtemp(prefix="engine-own-"))  # beside the project: nothing lands in it
        self.addCleanup(shutil.rmtree, own, True)
        private = {"CADGEN_ENGINE_DIR": str(self.state), "CADGEN_STATE_DIR": str(own / "state"),
                   "CADGEN_CACHE_DIR": str(own / "cache")}
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), **private,
                                          "CADGEN_ENGINE_MESH": "inline",
                                          "CADGEN_ENGINE_WORKERS": "1"}, self.addCleanup)
        # This process asks the test's daemon what it holds (``status``), never starting one.
        self.enterContext(mock.patch.dict(os.environ, private))
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.cli("stop")
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=self.folder, env=env or self.env)

    def status(self) -> dict:
        from cad.engine.client import request

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

    def test_a_page_watching_a_model_s_declared_xbf_keeps_no_worker_of_the_model(self) -> None:
        """A declared xbf opened as a file is a file: a page watching it keeps no model's worker
        warm, so at the count cap (one, here) the next script's build retires the worker that wrote
        it, exactly as with no page open."""
        from urllib.parse import parse_qs, urlsplit
        import urllib.request

        self.script("a")
        self.script("b")
        self.build("a")
        served = self.cli("serve", "XBF/a.xbf")
        self.assertEqual(served.returncode, 0, served.stderr)
        url = urlsplit(served.stdout.strip())
        version = f"{url.scheme}://{url.netloc}/api/doc/{url.path.strip('/')}/version?wait=0"
        token = parse_qs(url.query)["token"][0]
        with urllib.request.urlopen(urllib.request.Request(version, headers={"Authorization": "Bearer " + token}),
                                    timeout=60) as response:  # a page's sync: the file is watched now
            self.assertIn("version", json.loads(response.read()))
        self.build("b")
        status = self.status()
        self.assertEqual([Path(w["script"]).name for w in status["workers"]], ["b.py"], "the cap holds")
        self.assertEqual([(Path(row["script"]).name, row["reason"]) for row in status["retired"]], [("a.py", "LRU")])

    def test_a_new_script_s_first_build_takes_the_standby_and_another_stands_by(self) -> None:
        # The runners' standby is off; and the host's memory pressure, which keeps a standby from
        # starting, is no part of this test (``CADGEN_ENGINE_PRESSURE``).
        env = {**self.env, "CADGEN_ENGINE_WORKERS": "", "CADGEN_ENGINE_STANDBY": "1", "CADGEN_ENGINE_PRESSURE": "0"}

        def standby(besides: int | None = None) -> dict:
            found: dict = {}

            def ready() -> bool:
                found.update(self.status().get("standby") or {})
                return bool(found.get("pid")) and found["pid"] != besides

            await_(ready, "a standby with the kernel loaded", 120)
            return found

        self.script("a")
        self.build("a", env)  # the standby stands by in a's environment from now on
        spare = standby()
        self.script("b")
        self.assertIn(" cold ", self.build("b", env))
        status = self.status()
        self.assertEqual({Path(w["script"]).name: w["pid"] for w in status["workers"]}["b.py"], spare["pid"],
                         "b's worker is the standby")
        self.assertGreater(spare["rssMb"], 0)
        again = standby(spare["pid"])
        self.assertNotIn("standby", [Path(w["script"]).name for w in status["workers"]])
        self.assertRegex(self.cli("status").stdout, rf"with the standby .*\n(.*\n)*  standby +{again['pid']} ")


if __name__ == "__main__":
    unittest.main()
