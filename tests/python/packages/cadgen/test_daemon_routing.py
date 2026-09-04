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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
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
    import time; time.sleep({sleep})
    return bd.Box({size}, 4.0, 2.0)


if __name__ == "__main__":
    {name}()
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


def _authkey() -> bytes:
    key = transport.read_authkey(daemon_client.daemon_identity())
    if not key:
        raise RuntimeError("the daemon has not written its auth key")
    return key


class DaemonRouting(unittest.TestCase):
    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.socket_dir = tempfile.TemporaryDirectory(
            prefix="cadgen-routing-", dir=None if os.name == "nt" else "/tmp", ignore_cleanup_errors=True
        )
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
            (cls.src / f"{name}.py").write_text(PART.format(name=name, sleep=0.0, size=size), encoding="utf-8")
        (cls.src / "pair.py").write_text(PARENT, encoding="utf-8")
        (cls.src / "slow.py").write_text(PART.format(name="slow", sleep=4.0, size=5.0), encoding="utf-8")
        # The daemon's key and progress records live in ITS state dir; this process must
        # read the same one to authenticate. Kept for the whole class.
        cls._state_patch = mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(cls.work / "state")})
        cls._state_patch.start()
        cls._start_server()

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
                probe = transport.connect(cls.address, _authkey())
            except (OSError, RuntimeError):
                time.sleep(0.1)
                continue
            probe.close()
            return
        raise RuntimeError(f"daemon address never appeared:\n{cls.log_path.read_text(encoding='utf-8')}")

    @classmethod
    def tearDownClass(cls) -> None:
        pids = {int(w["pid"]) for w in (cls._status() or {}).get("workers", []) if w.get("pid")}
        if cls.server is not None and cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        for pid in pids:
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        cls._state_patch.stop()
        cls.work_tmp.cleanup()
        cls.socket_dir.cleanup()

    # --- helpers ------------------------------------------------------------------

    @classmethod
    def _env(cls, store: str = "a") -> dict[str, str]:
        return {
            "CADGEN_DAEMON": "1",
            "CADGEN_DAEMON_SOCKET": cls.address,
            "CADGEN_CACHE_DIR": str(cls.stores[store]),
            "CADGEN_DAEMON_STATE_DIR": str(cls.work / "state"),
        }

    @classmethod
    def _status(cls) -> dict | None:
        with mock.patch.dict(os.environ, cls._env()):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            return daemon_client.status()

    def _build(self, script: str, *extra: str, store: str = "a") -> tuple[int | None, str, list[dict]]:
        out, err = io.StringIO(), io.StringIO()
        events: list[dict] = []
        from cadgen.daemon import executors

        with mock.patch.dict(os.environ, self._env(store)):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            os.environ.pop("CADGEN_ROOT_ID", None)
            executors.set_event_sink(events.append)
            try:
                with redirect_stdout(out), redirect_stderr(err):
                    code = daemon_client.run_via_daemon(
                        "run", [str(self.src / script), *extra], cwd=str(self.src), prog=f"python {script}"
                    )
            finally:
                executors.set_event_sink(None)
        return code, out.getvalue() + err.getvalue(), events

    def _workers_for(self, model: str) -> list[dict]:
        status = self._status() or {}
        return [w for w in status.get("workers", []) if w["model"].endswith(model)]

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
        before = (self._status() or {}).get("concurrent", 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self._build, "slow.py", "--force")
            time.sleep(1.0)
            second = executor.submit(self._build, "slow.py", "--force")
            started = time.monotonic()
            second_code, second_out, _ = second.result(timeout=300)
            second_elapsed = time.monotonic() - started
            first_code, first_out, _ = first.result(timeout=300)
        self.assertEqual(first_code, 0, first_out)
        self.assertEqual(second_code, 0, second_out)
        status = self._status() or {}
        self.assertGreater(status.get("concurrent", 0), before, "no extra was bound for the busy model")
        # The second finished on its own clock: had it queued behind the first (4 s body)
        # it would have taken both bodies.
        self.assertLess(second_elapsed, 7.5)

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
        channel = transport.connect(self.address, _authkey())
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

        def slow() -> None:
            results["slow"] = self._build("slow.py", "--force")

        thread = threading.Thread(target=slow)
        thread.start()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if any(w["busy"] for w in self._workers_for("slow.py")):
                break
            time.sleep(0.1)
        else:
            self.fail("the slow build never went busy")
        channel = transport.connect(self.address, _authkey())
        try:
            channel.send(json.dumps({"tool": "run", "argv": ["left.py"], "cwd": str(self.src), "token": "stale"}).encode("utf-8"))
            raw = channel.recv(30.0)
        finally:
            channel.close()
        self.assertEqual(json.loads(raw.decode("utf-8")), {"restart": True})
        thread.join(timeout=120)
        code, output, _ = results["slow"]
        self.assertEqual(code, 0, f"the job in flight was not drained:\n{output}")
        self.server.wait(timeout=60)
        log = self.log_path.read_text(encoding="utf-8")
        # The slow job plus its worker's slot lease are both request threads in flight.
        self.assertRegex(log, r"finishing \d+ job\(s\) in flight")


if __name__ == "__main__":
    unittest.main()
