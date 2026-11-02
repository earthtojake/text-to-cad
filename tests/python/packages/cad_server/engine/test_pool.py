"""The daemon's workers, by the supervisor's rules: at most a cap of them alive, requests past it
waiting first come first served, the least recently used idle worker retired to make room, workers
retired for memory and never on a timer, no process standing by, and a retired script's next build a
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
from cad_server.engine.daemon import Daemon  # noqa: E402
from cad_server.engine.services import WORKER  # noqa: E402
from cad_server.engine.supervisor import Supervisor  # noqa: E402

_PIDS = itertools.count(1)


def _address(name: str) -> str:
    """A script model's address, as the server keys it (the script needs not exist)."""
    from cad.engine.addresses import key

    return str(key(f"{name}.py::{name}"))


class Fake:
    """A worker as the supervisor sees one (its ``launch``): of 100 MB."""

    def __init__(self, service, key: str, label: str, environment: dict, cwd: str | None,
                 rss: float | None = None) -> None:
        self.service, self.key, self.label, self.environment, self.cwd = service, key, label, environment, cwd
        self.pid, self.requests, self.started = next(_PIDS), 0, time.time()
        self.rss = 100.0 if rss is None else rss
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
    def pool(self, cap: int, memory: float | None = None) -> Supervisor:
        self.started: list[str] = []

        def launch(service, key: str, label: str, environment: dict, cwd: str | None) -> Fake:
            self.started.append(label)
            return Fake(service, key, label, environment, cwd)

        return Supervisor(cap, (WORKER,), launch=launch, memory=lambda: memory)

    def lease_in_turn(self, pool: Supervisor, script: str, got: list) -> threading.Thread:
        """A request for ``script`` from a thread of its own, once every earlier one is waiting."""
        waiting = pool.waiting("worker")
        thread = threading.Thread(target=lambda: got.append((script, pool.lease("worker", script, {}))), daemon=True)
        thread.start()
        await_(lambda: pool.waiting("worker") == waiting + 1, f"{script} to wait")
        return thread

    def test_requests_past_the_cap_wait_their_turn_first_come_first_served(self) -> None:
        pool = self.pool(1)
        first = pool.lease("worker", "a.py", {})
        got: list = []
        later = [self.lease_in_turn(pool, name, got) for name in ("b.py", "c.py")]
        self.assertEqual((pool.waiting("worker"), [w.label for w in pool.processes("worker")]), (2, ["a.py"]),
                         "one alive, two waiting")
        pool.release(first)
        await_(lambda: len(got) == 1, "the first waiting request")
        self.assertEqual(got[0][0], "b.py", "the first to come is the first served")
        self.assertTrue(first.stopped, "the idle worker made room: retired, at the cap")
        self.assertEqual(pool.waiting("worker"), 1)
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
        a, b = pool.lease("worker", "a.py", {}), pool.lease("worker", "b.py", {})
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
        a = pool.lease("worker", "a.py", {})
        pool.release(a)
        b = pool.lease("worker", "b.py", {})
        pool.release(b)
        c = pool.lease("worker", "c.py", {})
        self.assertTrue(a.stopped and not b.stopped, "a was used least recently")
        pool.release(c)
        again = pool.lease("worker", "a.py", {})
        self.assertIsNot(again, a, "a retired script's next build is a fresh worker's")
        self.assertTrue(b.stopped and not c.stopped)
        self.assertEqual(sorted(w.label for w in pool.processes("worker")), ["a.py", "c.py"])
        self.assertEqual([row["reason"] for row in pool.retired], ["LRU", "LRU"])

    def test_over_the_memory_cap_the_least_recently_used_idle_worker_goes_and_a_busy_one_never(self) -> None:
        pool = self.pool(4, memory=250.0)
        old, recent, busy = (pool.lease("worker", "a.py", {}), pool.lease("worker", "b.py", {}),
                             pool.lease("worker", "c.py", {}))
        pool.release(old)  # 300 MB in all: over the cap, so the least recently used goes
        self.assertTrue(old.stopped)
        pool.release(recent)
        self.assertEqual([w.label for w in pool.processes("worker")], ["b.py", "c.py"],
                         "200 MB: under the cap, both stay")
        busy.rss = 400.0  # alone over the cap while it builds: the idle one goes, and it stays busy
        self.assertEqual(pool.shed(), [recent])
        self.assertFalse(busy.stopped)
        self.assertEqual([(row["script"], row["reason"]) for row in pool.retired], [("b.py", "RSS"), ("a.py", "RSS")])
        self.assertIsNot(pool.lease("worker", "a.py", {}), old, "a retired script's next build is a fresh worker's")

    def test_only_what_shapes_the_import_system_replaces_a_worker_and_the_rest_is_adopted(self) -> None:
        pool = self.pool(1)
        worker = pool.lease("worker", "a.py", {"PATH": "/one", "VIRTUAL_ENV": "/venv", "TURN": "1"})
        pool.release(worker)
        for name in ("PATH", "VIRTUAL_ENV", "TURN", "HOME"):
            again = pool.lease("worker", "a.py", {"PATH": "/one", "VIRTUAL_ENV": "/venv", "TURN": "1", name: "/other"})
            pool.release(again)
            self.assertIs(again, worker, f"another {name} is the run's to adopt: the warm worker serves it")
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE",
                     "PYTHONPLATLIBDIR"):
            new = pool.lease("worker", "a.py", {name: "1"})
            pool.release(new)
            self.assertTrue(worker.stopped and not new.stopped, f"another {name} is another interpreter")
            self.assertEqual(pool.retired[0]["reason"], "environment")
            worker = new
        self.assertEqual(len(self.started), 7)

    def test_a_gone_or_capped_worker_leaves_the_pool_when_let_go(self) -> None:
        pool = self.pool(2)
        crashed, capped = pool.lease("worker", "a.py", {}), pool.lease("worker", "b.py", {})
        crashed.stopped = True  # it died during its build
        capped.retired = True  # over its memory cap after its build
        pool.release(crashed), pool.release(capped)
        self.assertEqual(pool.processes("worker"), [])
        self.assertEqual(sorted(row["reason"] for row in pool.retired), ["RSS", "exited"])

    def test_a_worker_that_fails_to_start_gives_its_slot_back(self) -> None:
        def launch(service, key: str, label: str, environment: dict, cwd: str | None) -> Fake:
            if label == "bad.py":
                raise RuntimeError("no")
            return Fake(service, key, label, environment, cwd)

        pool = Supervisor(1, (WORKER,), launch=launch)
        with self.assertRaises(RuntimeError):
            pool.lease("worker", "bad.py", {})
        self.assertEqual(pool.lease("worker", "good.py", {}).label, "good.py")


class DaemonSwitchesTest(unittest.TestCase):
    """The daemon's own switches and its status, with fake workers."""

    def test_the_pressure_switch_answers_for_the_host_and_anything_else_is_refused(self) -> None:
        # CAD_ENGINE_PRESSURE is Pressure.simulate for a daemon in another process.
        from cad_server.engine import daemon as engine

        for value, simulated in (("0", False), ("1", True), ("", None), (None, None)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"CAD_ENGINE_PRESSURE": value or ""}):
                if value is None:
                    os.environ.pop("CAD_ENGINE_PRESSURE")
                made = Daemon(cap=1)
                self.addCleanup(made.shutdown)
                self.assertEqual(made.pressure.simulated, simulated, "unset: the system's signal, measured")
                if simulated is not None:
                    self.assertEqual(made.pressure.under(), simulated)
        folder = Path(tempfile.mkdtemp(prefix="eng-"))
        self.addCleanup(shutil.rmtree, folder, True)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_PRESSURE": "yes", "CAD_ENGINE_DIR": str(folder)}):
            with self.assertRaisesRegex(ValueError, "CAD_ENGINE_PRESSURE is 'yes': 0 .*, 1 .*, or unset"):
                Daemon(cap=1)
            with mock.patch("sys.stderr"):
                self.assertEqual(engine.main([]), 1, "refused at the start")
            self.assertIn("CAD_ENGINE_PRESSURE is 'yes'", json.loads(engine.failure_path().read_text(encoding="utf-8"))["reason"])

    def test_status_counts_the_workers_against_the_cap_and_no_process_stands_by(self) -> None:
        from cad_server.engine.cli import status_text

        daemon = Daemon(cap=4)
        daemon.supervisor.launch = Fake
        self.addCleanup(daemon.shutdown)
        worker = daemon.supervisor.lease("worker", "/w/tube.py", {"PYTHONPATH": "/other"})
        daemon.supervisor.release(worker)
        answer = daemon.status()
        self.assertEqual([Path(w["script"]).name for w in answer["workers"]], ["tube.py"])
        self.assertEqual(answer["rssMb"], 100)
        self.assertNotIn("standby", answer)
        lines = status_text(answer).splitlines()
        self.assertIn("workers 1/4 · ", lines[0])
        self.assertNotIn("standby", status_text(answer))


class ConnectedPoolTest(unittest.TestCase):
    """The real version-wait lifecycle holds the builder, not unrelated workers."""

    def test_version_wait_and_recent_sync_keep_the_builder_warm(self) -> None:
        from cad.engine.serve import LIVE, Server

        daemon = Daemon(cap=2)
        daemon.supervisor.launch = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        path = _address("a")  # the model document a's worker built
        ident = server.put(path, {"version": "one", "prototypes": []}, {})
        builder, other = daemon.supervisor.lease("worker", "a.py", {}), daemon.supervisor.lease("worker", "b.py", {})
        daemon.builders[ident] = builder
        daemon.supervisor.release(builder)  # the least recently used, and under the cap alone
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
                daemon.supervisor.memory = lambda: 150.0  # two workers of 100 MB: one is over
                with mock.patch("time.monotonic", return_value=builder.used + 24 * 3600):
                    daemon.supervisor.release(other)
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
        self.assertEqual(daemon.supervisor.shed(), [builder], "alone over the cap, a watched one goes too")

    def test_a_day_idle_under_the_memory_cap_keeps_every_worker(self) -> None:
        daemon = Daemon(cap=2)
        daemon.supervisor.launch = Fake
        daemon.supervisor.memory = lambda: 1000.0
        self.addCleanup(daemon.shutdown)
        worker = daemon.supervisor.lease("worker", "a.py", {})
        daemon.supervisor.release(worker)
        with mock.patch("time.monotonic", return_value=worker.used + 24 * 3600):
            daemon.tend()
        self.assertEqual((daemon.supervisor.processes("worker"), worker.stopped), ([worker], False),
                         "no timer retires a worker")

    def test_the_worker_count_cap_retires_an_unwatched_worker_before_a_watched_one(self) -> None:
        from cad.engine.serve import Server

        daemon = Daemon(cap=2)
        daemon.supervisor.launch = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        watched = daemon.supervisor.lease("worker", "watched.py", {})
        daemon.supervisor.release(watched)  # used least recently
        unwatched = daemon.supervisor.lease("worker", "unwatched.py", {})
        daemon.supervisor.release(unwatched)
        server.put(_address("watched"), {"version": "one", "prototypes": []}, {})
        daemon.builders[document_id(_address("watched"))] = watched
        server.sync(_address("watched"))
        third = daemon.supervisor.lease("worker", "third.py", {})
        self.assertTrue(unwatched.stopped, "the unwatched worker made room")
        self.assertFalse(watched.stopped, "a watched worker is not the count cap's victim")
        self.assertEqual([row["reason"] for row in daemon.supervisor.retired], ["LRU"])

    def test_at_the_cap_with_every_idle_worker_watched_a_new_build_starts_past_the_cap(self) -> None:
        from cad.engine.serve import Server

        daemon = Daemon(cap=2)
        daemon.supervisor.launch = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        watched = []
        for name in ("one", "two"):
            worker = daemon.supervisor.lease("worker", f"{name}.py", {})
            daemon.supervisor.release(worker)
            server.put(_address(name), {"version": "one", "prototypes": []}, {})
            daemon.builders[document_id(_address(name))] = worker
            server.sync(_address(name))
            watched.append(worker)
        third = daemon.supervisor.lease("worker", "third.py", {})
        self.assertEqual(len(daemon.supervisor.processes("worker")), 3, "the cap is exceeded, not met by an eviction")
        self.assertFalse(any(worker.stopped for worker in watched), "the watched workers live")
        self.assertEqual(list(daemon.supervisor.retired), [])
        # Past the cap, an unwatched idle worker is the next build's victim, the watched ones never.
        daemon.supervisor.release(third)
        daemon.supervisor.lease("worker", "fourth.py", {})
        self.assertTrue(third.stopped)
        self.assertFalse(any(worker.stopped for worker in watched))
        self.assertEqual([row["reason"] for row in daemon.supervisor.retired], ["LRU"])

    def test_failed_wait_releases_watcher_and_memory_cap_still_retires(self) -> None:
        from cad.engine.serve import Server

        daemon = Daemon(cap=1)
        daemon.supervisor.launch = Fake
        server = daemon.server = Server(mesh_mode="inline")
        self.addCleanup(daemon.shutdown)
        ident = server.put(_address("a"), {"version": "one", "prototypes": []}, {})
        worker = daemon.supervisor.lease("worker", "a.py", {})
        daemon.builders[ident] = worker
        with mock.patch.object(server, "document", side_effect=ValueError("unreadable")):
            with self.assertRaisesRegex(ValueError, "unreadable"):
                server.wait(ident, "one", 60)
        self.assertFalse(server.watchers)
        self.assertTrue(daemon.connected(worker))
        worker.retired = True
        daemon.supervisor.release(worker)
        self.assertTrue(worker.stopped)
        self.assertEqual(daemon.supervisor.retired[0]["reason"], "RSS")


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
        private = {"CAD_ENGINE_DIR": str(self.state), "CAD_STATE_DIR": str(own / "state"),
                   "CAD_CACHE_DIR": str(own / "cache")}
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), **private,
                                          "CAD_ENGINE_MESH": "inline",
                                          "CAD_ENGINE_WORKERS": "1"}, self.addCleanup)
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
        version = f"{url.scheme}://{url.netloc}/api/v1/documents/{url.path.strip('/')}/version?wait=0"
        token = parse_qs(url.query)["token"][0]
        with urllib.request.urlopen(urllib.request.Request(version, headers={"Authorization": "Bearer " + token}),
                                    timeout=60) as response:  # a page's sync: the file is watched now
            self.assertIn("version", json.loads(response.read()))
        self.build("b")
        status = self.status()
        self.assertEqual([Path(w["script"]).name for w in status["workers"]], ["b.py"], "the cap holds")
        self.assertEqual([(Path(row["script"]).name, row["reason"]) for row in status["retired"]], [("a.py", "LRU")])


if __name__ == "__main__":
    unittest.main()
