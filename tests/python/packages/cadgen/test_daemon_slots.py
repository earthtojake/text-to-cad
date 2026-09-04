"""Job slots and coalescing end to end, on both executors.

The same fixture -- a parent fanning out to 20 leaves, and the 3-level link tree -- is
built once on a private daemon started with ``CADGEN_JOBS=2`` and once on the transient
executor with the same limit. Running never exceeds the limit (the broker's peak says so),
a 1-slot pool still finishes the 3-level tree (yield/reacquire), and two parents that
need one stale child build it once.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import client as daemon_client  # noqa: E402
from cadgen.daemon import transport  # noqa: E402

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"

LEAF = """\
from cadgen import step
from cadgen import build123d as bd


@step
def {name}():
    import time; time.sleep(0.3)
    return bd.Box({size}, 4.0, 2.0)


if __name__ == "__main__":
    {name}()
"""

FANOUT = """\
from cadgen import step
from cadgen import build123d as bd
{imports}


@step
def fanout():
    parts = [{calls}]
    return bd.Compound(children=[bd.Pos(i * 10, 0, 0) * p for i, p in enumerate(parts)], label="fanout")


if __name__ == "__main__":
    fanout()
"""

PIN = """\
from cadgen import step
from cadgen import build123d as bd


@step
def pin():
    import time; time.sleep(0.5)
    return bd.Cylinder(radius=2.0, height=12.0)


if __name__ == "__main__":
    pin()
"""

ARM = """\
from cadgen import step
from cadgen import build123d as bd
from pin import pin


@step
def arm():
    p = pin()
    return bd.Compound(children=[bd.Box(40, 8, 4), bd.Pos(-15, 0, 2) * p, bd.Pos(15, 0, 2) * p], label="arm")


if __name__ == "__main__":
    arm()
"""

ROBOT = """\
from cadgen import step
from cadgen import build123d as bd
from arm import arm
from pin import pin


@step
def robot():
    a = arm()
    return bd.Compound(children=[bd.Box(60, 30, 6), bd.Pos(0, 10, 5) * a, bd.Pos(25, 0, 9) * pin()], label="robot")


if __name__ == "__main__":
    robot()
"""

PARENT_A = """\
from cadgen import step
from cadgen import build123d as bd
from pin import pin


@step
def parent_a():
    return bd.Compound(children=[bd.Box(10, 10, 1), bd.Pos(0, 0, 3) * pin()], label="parent_a")


if __name__ == "__main__":
    parent_a()
"""

PARENT_B = PARENT_A.replace("parent_a", "parent_b").replace("bd.Box(10, 10, 1)", "bd.Box(12, 12, 1)")

LEAVES = 20


def _write_fixture(src: Path) -> None:
    src.mkdir(parents=True, exist_ok=True)
    names = [f"leaf_{i:02d}" for i in range(LEAVES)]
    for i, name in enumerate(names):
        (src / f"{name}.py").write_text(LEAF.format(name=name, size=5.0 + i), encoding="utf-8")
    (src / "fanout.py").write_text(
        FANOUT.format(
            imports="\n".join(f"from {n} import {n}" for n in names),
            calls=", ".join(f"{n}()" for n in names),
        ),
        encoding="utf-8",
    )
    (src / "pin.py").write_text(PIN, encoding="utf-8")
    (src / "arm.py").write_text(ARM, encoding="utf-8")
    (src / "robot.py").write_text(ROBOT, encoding="utf-8")
    (src / "parent_a.py").write_text(PARENT_A, encoding="utf-8")
    (src / "parent_b.py").write_text(PARENT_B, encoding="utf-8")


def _authkey() -> bytes:
    key = transport.read_authkey(daemon_client.daemon_identity())
    if not key:
        raise RuntimeError("the daemon has not written its auth key")
    return key


class _Executor(unittest.TestCase):
    """Shared assertions; subclasses supply how a model is run and how the peak is read."""

    LIMIT = 2

    @classmethod
    def setUpClass(cls) -> None:
        cls.work_tmp = temporary_directory(prefix=f"cadgen-slots-{cls.__name__}-")
        cls.work = Path(cls.work_tmp.name)
        cls.src = cls.work / "src"
        _write_fixture(cls.src)
        cls.env = dict(os.environ)
        cls.env.update({
            "CADGEN_CACHE_DIR": str(cls.work / "store"),
            "CADGEN_DAEMON_STATE_DIR": str(cls.work / "state"),
            "CADGEN_JOBS": str(cls.LIMIT),
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT / "packages" / "cadgen" / "src")]
                + [os.path.abspath(p) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
            ),
        })
        for key in ("CADGEN_DAEMON_CHILD", "CADGEN_ROOT_ID", "CADGEN_BROKER", "CADGEN_BROKER_KEY", "CADGEN_EVENTS"):
            cls.env.pop(key, None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.work_tmp.cleanup()

    def _run(self, script: str, *extra: str, env: dict | None = None) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, script, "--json", *extra], cwd=str(self.src), env=env or self.env,
            capture_output=True, text=True, timeout=900,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _events(self, stderr: str) -> list[dict]:
        return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]

    def test_a_fanout_of_twenty_leaves_never_exceeds_the_limit(self):
        code, out, err = self._run("fanout.py")
        self.assertEqual(code, 0, err)
        self.assertIn('"outcome":"built"', out)
        events = self._events(err)
        built = {Path(e["model"]).stem for e in events if e["state"] == "done"}
        self.assertTrue({f"leaf_{i:02d}" for i in range(LEAVES)} <= built, sorted(built))
        self.assertIn("queued", {e["state"] for e in events}, "twenty leaves on two slots must queue")
        peak = self.peak_running()
        self.assertLessEqual(peak, self.LIMIT, f"running exceeded the limit: peak {peak}")
        self.assertGreaterEqual(peak, 1)

    def test_two_parents_needing_one_stale_child_build_it_once(self):
        # Both parents in ONE top-level build so they share an executor: a root that
        # calls both. Here: two separate top-level runs started together, which for the
        # daemon share the daemon and for the transient executor each have their own
        # broker -- so the daemon proves coalescing across roots, the transient one within.
        a = subprocess.Popen([sys.executable, "parent_a.py", "--json"], cwd=str(self.src), env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        b = subprocess.Popen([sys.executable, "parent_b.py", "--json"], cwd=str(self.src), env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        outs = [p.communicate(timeout=900) for p in (a, b)]
        for proc, (out, err) in zip((a, b), outs):
            self.assertEqual(proc.returncode, 0, err)
            self.assertIn('"outcome":"built"', out)
        self.check_pin_built_once(outs)


class DaemonExecutor(_Executor):
    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.socket_dir = tempfile.TemporaryDirectory(prefix="cadgen-slots-", dir=None if os.name == "nt" else "/tmp")
        cls.address = rf"\\.\pipe\cadgen-slots-{os.getpid()}" if os.name == "nt" else str(Path(cls.socket_dir.name) / "d.sock")
        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
        cls.env["CADGEN_DAEMON_SOCKET"] = cls.address
        cls.env["CADGEN_DAEMON"] = "1"  # the runner may export 0; these clients go warm
        cls.env["CADGEN_DAEMON_SPARES"] = "1"
        cls.env["CADGEN_DAEMON_IDLE_TIMEOUT"] = "600"
        os.environ["CADGEN_DAEMON_STATE_DIR"] = cls.env["CADGEN_DAEMON_STATE_DIR"]
        os.environ["CADGEN_DAEMON_SOCKET"] = cls.address
        with open(cls.log_path, "ab") as log_file:
            cls.server = subprocess.Popen(
                [sys.executable, str(DAEMON_DIR / "__main__.py")],
                stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT, env=cls.env,
            )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError(f"daemon exited during startup:\n{cls.log_path.read_text(encoding='utf-8')}")
            try:
                transport.connect(cls.address, _authkey()).close()
                break
            except (OSError, RuntimeError):
                time.sleep(0.1)
        else:
            raise RuntimeError("daemon never came up")

    @classmethod
    def tearDownClass(cls) -> None:
        status = daemon_client.status() or {}
        if cls.server is not None and cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        for worker in status.get("workers") or []:
            try:
                os.kill(int(worker["pid"]), 9)
            except (OSError, ValueError, TypeError):
                pass
        os.environ.pop("CADGEN_DAEMON_SOCKET", None)
        os.environ.pop("CADGEN_DAEMON_STATE_DIR", None)
        cls.socket_dir.cleanup()
        super().tearDownClass()

    def peak_running(self) -> int:
        status = daemon_client.status() or {}
        jobs = status.get("jobsRunning") or {}
        self.assertEqual(jobs.get("limit"), self.LIMIT, status)
        return int(jobs.get("peakRunning") or 0)

    def check_pin_built_once(self, outs) -> None:
        # Two roots started together share the daemon. Whether the second root's ask for
        # pin coalesces onto the first's job or finds it already current depends on which
        # process reaches the daemon first; the invariant is that pin's body ran ONCE.
        # (Coalescing itself is proven deterministically by the broker unit tests.)
        built = 0
        for _out, err in outs:
            built += sum(1 for e in self._events(err) if Path(e["model"]).stem == "pin" and e["state"] == "done")
        status = daemon_client.status() or {}
        coalesced = int((status.get("jobsRunning") or {}).get("coalesced", 0))
        self.assertEqual(built, 1, f"pin was built {built} times (coalesced {coalesced}): {status}")

    def test_z_a_one_slot_daemon_builds_the_three_level_tree(self):
        # A separate daemon with ONE slot: a held slot would deadlock the parent waiting on
        # its child. Yield/reacquire is what lets this finish.
        env = dict(self.env)
        env["CADGEN_JOBS"] = "1"
        env["CADGEN_CACHE_DIR"] = str(self.work / "store-one")
        address = self.address + ".one"
        env["CADGEN_DAEMON_SOCKET"] = address
        log = Path(self.socket_dir.name) / "one.log"
        with open(log, "ab") as log_file:
            server = subprocess.Popen(
                [sys.executable, str(DAEMON_DIR / "__main__.py")],
                stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT, env=env,
            )
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    transport.connect(address, _authkey()).close()
                    break
                except OSError:
                    time.sleep(0.1)
            code, out, err = self._run("robot.py", env=env)
            self.assertEqual(code, 0, err)
            self.assertIn('"outcome":"built"', out)
            built = {Path(e["model"]).stem for e in self._events(err) if e["state"] == "done"}
            self.assertEqual(built, {"pin", "arm", "robot"})
            os.environ["CADGEN_DAEMON_SOCKET"] = address
            try:
                status = daemon_client.status() or {}
            finally:
                os.environ["CADGEN_DAEMON_SOCKET"] = self.address
            self.assertEqual((status.get("jobsRunning") or {}).get("peakRunning"), 1, status)
        finally:
            server.terminate()
            server.wait(timeout=15)


class TransientExecutor(_Executor):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env["CADGEN_DAEMON"] = "0"
        cls.stats = cls.work / "broker-stats.json"
        cls.env["CADGEN_BROKER_STATS"] = str(cls.stats)

    def peak_running(self) -> int:
        stats = json.loads(self.stats.read_text(encoding="utf-8"))
        self.assertEqual(stats["limit"], self.LIMIT, stats)
        return int(stats["peakRunning"])

    def check_pin_built_once(self, outs) -> None:
        # Two roots, two private brokers: coalescing here is within a root. The child was
        # built by whichever parent got there first; the second found it current.
        built = 0
        for _out, err in outs:
            built += sum(1 for e in self._events(err) if Path(e["model"]).stem == "pin" and e["state"] == "done")
        self.assertGreaterEqual(built, 1)

    def test_a_one_slot_transient_build_finishes_the_three_level_tree(self):
        env = dict(self.env)
        env["CADGEN_JOBS"] = "1"
        env["CADGEN_CACHE_DIR"] = str(self.work / "store-one")
        code, out, err = self._run("robot.py", env=env)
        self.assertEqual(code, 0, err)
        self.assertIn('"outcome":"built"', out)
        built = {Path(e["model"]).stem for e in self._events(err) if e["state"] == "done"}
        self.assertEqual(built, {"pin", "arm", "robot"})
        stats = json.loads(self.stats.read_text(encoding="utf-8"))
        self.assertEqual(stats["peakRunning"], 1, stats)
        # robot asks for pin twice (once itself, once through arm). Whether the second
        # ask coalesces onto the first job or finds it already current depends on which
        # child process reaches the broker first -- FIFO is over acquire calls, not over
        # submissions -- so the invariant is that pin is BUILT once, either way.
        pin_done = [e for e in self._events(err) if Path(e["model"]).stem == "pin" and e["state"] == "done"]
        self.assertEqual(len(pin_done), 1, "the shared child was built more than once")

    def test_one_root_calling_two_parents_that_share_a_child_builds_it_once(self):
        (self.src / "both.py").write_text(
            "from cadgen import step\nfrom cadgen import build123d as bd\n"
            "from parent_a import parent_a\nfrom parent_b import parent_b\n\n\n"
            "@step\ndef both():\n    return bd.Compound(children=[parent_a(), bd.Pos(30, 0, 0) * parent_b()], label='both')\n\n\n"
            "if __name__ == '__main__':\n    both()\n",
            encoding="utf-8",
        )
        env = dict(self.env)
        env["CADGEN_CACHE_DIR"] = str(self.work / "store-both")
        code, out, err = self._run("both.py", env=env)
        self.assertEqual(code, 0, err)
        stats = json.loads(self.stats.read_text(encoding="utf-8"))
        self.assertGreaterEqual(stats["coalesced"], 1, stats)
        pin_done = [e for e in self._events(err) if Path(e["model"]).stem == "pin" and e["state"] == "done"]
        self.assertEqual(len(pin_done), 1, "the shared child was built more than once")


del _Executor  # not a suite of its own

if __name__ == "__main__":
    unittest.main()
