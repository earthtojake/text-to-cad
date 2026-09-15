"""The daemon end to end on a private socket: routing by model, extras, spares, the
store root as a request field, and the race fixes.

Real supervisor, real workers, real builds. One daemon serves the whole class; every
test leaves it serving. The assertions are on worker identity, store contents and status
counters -- never on timing.
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.daemon_cleanup import retire_owned_daemon
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import client as daemon_client  # noqa: E402
from cadgen.daemon import transport  # noqa: E402

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"
SPAWN_WAIT_SECONDS = 120.0

PART = """\
from cadgen import step
from cadgen import build123d as bd


@step
def {name}():
    return bd.Box({size}, 4.0, 2.0)


if __name__ == "__main__":
    {name}()
"""

BLOCKED_PART = """\
from cadgen import step
from cadgen import build123d as bd


@step
def blocked():
    import time
    from pathlib import Path

    ready = Path(__file__).with_suffix(".ready")
    release = Path(__file__).with_suffix(".release")
    ready.touch()
    deadline = time.monotonic() + 120
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not release.exists():
        raise TimeoutError("test did not release blocked model")
    return bd.Box(5.0, 4.0, 2.0)


if __name__ == "__main__":
    blocked()
"""

PARENT = """\
from cadgen import step
from cadgen import build123d as bd

from left import left
from right import right


@step
def pair():
    a = left()
    b = bd.Pos(20, 0, 0) * right()
    return bd.Compound(children=[a, b], label="pair")


if __name__ == "__main__":
    pair()
"""


def _authkey(address: str) -> bytes:
    key = transport.read_authkey(str(address))
    if not key:
        raise RuntimeError("the daemon has not written its auth key")
    return key


class DaemonRouting(unittest.TestCase):
    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.socket_dir = tempfile.TemporaryDirectory(prefix="cadgen-routing-", dir=None if os.name == "nt" else "/tmp")
        if os.name == "nt":
            cls.address = rf"\\.\pipe\cadgen-routing-{os.getpid()}"
        else:
            cls.address = str(Path(cls.socket_dir.name) / "d.sock")
        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
        cls.work_tmp = temporary_directory(prefix="cadgen-routing-work-")
        cls.work = Path(cls.work_tmp.name)
        cls.src = cls.work / "src"
        cls.src.mkdir()
        cls.stores = {"a": cls.work / "store-a", "b": cls.work / "store-b"}
        for name, size in (("left", 6.0), ("right", 7.0)):
            (cls.src / f"{name}.py").write_text(PART.format(name=name, size=size), encoding="utf-8")
        (cls.src / "pair.py").write_text(PARENT, encoding="utf-8")
        (cls.src / "blocked.py").write_text(BLOCKED_PART, encoding="utf-8")
        # Concurrent clients must not patch process-global daemon routing independently:
        # one thread restoring the runner's endpoint can otherwise spawn an unowned
        # daemon. Keep this class's socket, state and default store invariant throughout.
        env = {
            key: value for key, value in os.environ.items()
            if key not in {"CADGEN_DAEMON_CHILD", "CADGEN_ROOT_ID", "CADGEN_BROKER", "CADGEN_BROKER_KEY", "CADGEN_BROKER_STATS"}
        }
        env.update({
            "CADGEN_DAEMON": "1",
            "CADGEN_DAEMON_SOCKET": cls.address,
            "CADGEN_CACHE_DIR": str(cls.stores["a"]),
            "CADGEN_DAEMON_STATE_DIR": str(cls.work / "state"),
            "CADGEN_JOBS": "2",
            # Routing concurrency is the subject here; memory admission has its own
            # suite. Give these tiny solids stable, bounded test reservations.
            "CADGEN_MEMORY_MB": "8192",
            "CADGEN_WORKER_MEMORY_MB": "512",
            "CADGEN_DEPENDENCY_MEMORY_MB": "512",
        })
        cls._env_patch = mock.patch.dict(os.environ, env, clear=True)
        cls._env_patch.start()
        cls._start_server()
        cls._spawn_patch = mock.patch.object(
            daemon_client, "_spawn_daemon",
            side_effect=AssertionError("routing fixture attempted to spawn a daemon outside its owned server"),
        )
        cls._spawn_patch.start()

    @classmethod
    def _start_server(cls) -> None:
        env = dict(os.environ)
        env["CADGEN_DAEMON_SOCKET"] = cls.address
        env["CADGEN_DAEMON_IDLE_TIMEOUT"] = "600"
        env["CADGEN_DAEMON_SPARES"] = "1"
        env["CADGEN_DAEMON_STATE_DIR"] = str(cls.work / "state")
        env.pop("CADGEN_DAEMON_CHILD", None)
        env.pop("CADGEN_ROOT_ID", None)
        with open(cls.log_path, "ab") as log_file:
            cls.server = subprocess.Popen(
                [sys.executable, str(DAEMON_DIR / "__main__.py")],
                stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT, env=env,
            )
        deadline = time.monotonic() + SPAWN_WAIT_SECONDS
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError(f"daemon exited during startup:\n{cls.log_path.read_text(encoding='utf-8')}")
            try:
                probe = transport.connect(cls.address, _authkey(cls.address))
            except (OSError, RuntimeError):
                time.sleep(0.1)
                continue
            probe.close()
            return
        raise RuntimeError(f"daemon address never appeared:\n{cls.log_path.read_text(encoding='utf-8')}")

    @classmethod
    def tearDownClass(cls) -> None:
        pids = {int(w["pid"]) for w in (cls._status() or {}).get("workers", []) if w.get("pid")}
        retirement_error = None
        forced = False
        try:
            try:
                retire_owned_daemon(cls.address)
            except Exception as error:  # still close every owned process before reporting it
                retirement_error = error
                if cls.server is not None and cls.server.poll() is None:
                    cls.server.terminate()
                forced = True
            if cls.server is not None:
                try:
                    cls.server.wait(timeout=60 if retirement_error is None else 15)
                except subprocess.TimeoutExpired:
                    cls.server.kill()
                    cls.server.wait(timeout=15)
                    forced = True
            if forced:
                for pid in pids:
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass
        finally:
            try:
                try:
                    cls.work_tmp.cleanup()
                finally:
                    cls.socket_dir.cleanup()
            finally:
                cls._spawn_patch.stop()
                cls._env_patch.stop()
        if retirement_error is not None:
            raise retirement_error

    # --- helpers ------------------------------------------------------------------

    @classmethod
    def _status(cls) -> dict | None:
        return daemon_client.status()

    def _run(self, script: str, *extra: str, store: str = "a") -> int | None:
        cache = nullcontext() if store == "a" else mock.patch.dict(
            os.environ, {"CADGEN_CACHE_DIR": str(self.stores[store])}
        )
        with cache:
            return daemon_client.run_via_daemon(
                "run", [str(self.src / script), *extra], cwd=str(self.src), prog=f"python {script}"
            )

    def _build(self, script: str, *extra: str, store: str = "a") -> tuple[int | None, str, list[dict]]:
        out, err = io.StringIO(), io.StringIO()
        events: list[dict] = []
        from cadgen.daemon import executors

        executors.set_event_sink(events.append)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = self._run(script, *extra, store=store)
        finally:
            executors.set_event_sink(None)
        return code, out.getvalue() + err.getvalue(), events

    def _workers_for(self, model: str) -> list[dict]:
        status = self._status() or {}
        return [w for w in status.get("workers", []) if w["model"].endswith(model)]

    def _reset_blocked_model(self) -> tuple[Path, Path]:
        ready = self.src / "blocked.ready"
        release = self.src / "blocked.release"
        ready.unlink(missing_ok=True)
        release.unlink(missing_ok=True)
        return ready, release

    # --- tests -----------------------------------------------------------------------

    def test_a_model_binds_one_worker_and_keeps_it_across_builds(self):
        for _ in range(3):
            code, output, _events = self._build("left.py", "--force")
            self.assertEqual(code, 0, output)
        bound = self._workers_for("left.py")
        self.assertEqual(len(bound), 1, bound)
        self.assertGreaterEqual(bound[0]["jobs"], 3)
        self.assertFalse(bound[0]["extra"])

    def test_two_models_get_two_workers(self):
        self.assertEqual(self._build("left.py")[0], 0)
        self.assertEqual(self._build("right.py")[0], 0)
        left, right = self._workers_for("left.py"), self._workers_for("right.py")
        self.assertEqual((len(left), len(right)), (1, 1))
        self.assertNotEqual(left[0]["pid"], right[0]["pid"])

    def test_a_busy_model_runs_a_second_request_on_an_extra_without_waiting(self):
        ready, release = self._reset_blocked_model()
        before = (self._status() or {}).get("concurrent", 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self._run, "blocked.py", "--force")
            try:
                deadline = time.monotonic() + 120
                while not ready.exists() and time.monotonic() < deadline:
                    self.assertFalse(first.done(), "the first build finished before reaching its barrier")
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "the first build never reached its barrier")
                second = executor.submit(self._run, "blocked.py", "--force")
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    status = self._status() or {}
                    if status.get("concurrent", 0) > before:
                        break
                    self.assertFalse(first.done(), "the held build finished before an extra was bound")
                    time.sleep(0.02)
                else:
                    self.fail("no extra was bound for the held model")
                self.assertFalse(first.done(), "the held build finished before its release")
            finally:
                release.touch()
            self.assertEqual(first.result(timeout=300), 0)
            self.assertEqual(second.result(timeout=300), 0)

    def test_a_parent_submits_children_which_land_on_their_own_workers(self):
        code, output, events = self._build("pair.py", "--force")
        self.assertEqual(code, 0, output)
        models = {Path(e["model"]).name for e in events}
        self.assertTrue({"left.py", "right.py"} <= models, events)
        parents = {e.get("parent") for e in events if Path(e["model"]).name in {"left.py", "right.py"}}
        self.assertEqual({str(self.src / "pair.py")}, {p for p in parents if p})
        roots = {e.get("root") for e in events}
        self.assertEqual(len(roots), 1, f"child events were not tagged with the root's id: {roots}")
        for name in ("left.py", "right.py", "pair.py"):
            self.assertEqual(len(self._workers_for(name)), 1, name)

    def test_the_store_root_is_a_request_field(self):
        self.assertEqual(self._build("right.py", "--force", store="b")[0], 0)
        from cadgen.store.records import read_record

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.stores["b"])}):
            self.assertIsNotNone(read_record(self.src / "right.py"), "store b has no record")
        self.assertTrue((self.stores["b"] / "index" / "model").is_dir())

    def test_status_does_not_trip_the_token_exit(self):
        channel = transport.connect(self.address, _authkey(self.address))
        try:
            channel.send(json.dumps({"kind": "status", "token": "not-this-daemon"}).encode("utf-8"))
            raw = channel.recv(30.0)
        finally:
            channel.close()
        self.assertTrue(raw)
        frame = json.loads(raw.decode("utf-8"))
        self.assertIn("status", frame, frame)
        self.assertIn("spares", frame["status"])
        self.assertIn("imports", frame["status"])
        time.sleep(0.5)
        self.assertIsNone(self.server.poll(), "a status request with a foreign token stopped the daemon")

    def test_a_second_daemon_on_the_same_address_stands_down(self):
        env = dict(os.environ)
        env["CADGEN_DAEMON_SOCKET"] = self.address
        env["CADGEN_DAEMON_STATE_DIR"] = str(self.work / "state")
        env.pop("CADGEN_DAEMON_CHILD", None)
        second = subprocess.run(
            [sys.executable, str(DAEMON_DIR / "__main__.py")],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=120,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("standing down", second.stderr)
        # The first daemon still owns the address: its socket was not unlinked.
        self.assertEqual(self._build("left.py")[0], 0)

    def test_z_token_mismatch_drains_the_job_in_flight_before_exiting(self):
        # Last on purpose: it stops the daemon.
        results: dict = {}
        ready, release = self._reset_blocked_model()

        def blocked() -> None:
            results["blocked"] = self._build("blocked.py", "--force")

        thread = threading.Thread(target=blocked)
        thread.start()
        try:
            deadline = time.monotonic() + 120
            while not ready.exists() and time.monotonic() < deadline:
                self.assertTrue(thread.is_alive(), "the build finished before reaching its barrier")
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "the build never reached its barrier")
            channel = transport.connect(self.address, _authkey(self.address))
            try:
                channel.send(json.dumps({"tool": "run", "argv": ["left.py"], "cwd": str(self.src), "token": "stale"}).encode("utf-8"))
                raw = channel.recv(30.0)
            finally:
                channel.close()
            self.assertEqual(json.loads(raw.decode("utf-8")), {"restart": True})

            # The held job may still need a child or artifact after the runtime edit.
            # Its dependency request carries the new token because the client computes
            # that token from the live source tree. The draining daemon must finish it
            # on the old pool instead of closing the listener under its own root job.
            dependency = transport.connect(self.address, _authkey(self.address))
            try:
                dependency.send(json.dumps({
                    "tool": "run",
                    "argv": [str(self.src / "left.py")],
                    "cwd": str(self.src),
                    "token": "stale",
                    "dependency": True,
                }).encode("utf-8"))
                frames = []
                while True:
                    frame = dependency.recv(30.0)
                    self.assertTrue(frame, frames)
                    message = json.loads(frame.decode("utf-8"))
                    frames.append(message)
                    if "exit" in message:
                        break
            finally:
                dependency.close()
            self.assertEqual(frames[-1], {"exit": 0}, frames)
        finally:
            release.touch()
        thread.join(timeout=120)
        self.assertFalse(thread.is_alive(), "the held build did not drain")
        code, output, _ = results["blocked"]
        self.assertEqual(code, 0, f"the job in flight was not drained:\n{output}")
        self.server.wait(timeout=60)
        log = self.log_path.read_text(encoding="utf-8")
        # The blocked job plus its worker's slot lease are both request threads in flight.
        self.assertRegex(log, r"finishing \d+ job\(s\) in flight")


if __name__ == "__main__":
    unittest.main()
