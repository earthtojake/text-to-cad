"""Job slots end to end: one daemon with ONE slot, and whole builds still finish.

A parent's children build in the slot the parent holds, and the build's own pool jobs --
display, export -- run in the slot it yields to wait for them, so a 1-slot daemon finishes
a three-level tree and never runs two things at once (the broker's peak says so). Each
rule is pinned in threads by test_broker.py; this is the one real run through them.
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
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import client as daemon_client  # noqa: E402
from cadgen.daemon import transport  # noqa: E402

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"

PIN = """\
from cadgen import step
from cadgen import build123d as bd


@step
def pin():
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

BOTH = """\
from cadgen import step
from cadgen import build123d as bd
from parent_a import parent_a
from parent_b import parent_b


@step
def both():
    return bd.Compound(children=[parent_a(), bd.Pos(30, 0, 0) * parent_b()], label="both")


if __name__ == "__main__":
    both()
"""


def _authkey(address: str) -> bytes:
    key = transport.read_authkey(str(address))
    if not key:
        raise OSError("the daemon has not written its auth key")
    return key


class OneSlotDaemon(unittest.TestCase):
    LIMIT = 1
    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.work_tmp = generated_cad_directory(prefix="cadgen-slots-")
        cls.work = Path(cls.work_tmp.name)
        cls.src = cls.work / "src"
        cls.src.mkdir(parents=True)
        for name, source in (("pin", PIN), ("arm", ARM), ("robot", ROBOT), ("parent_a", PARENT_A),
                             ("parent_b", PARENT_B), ("both", BOTH)):
            (cls.src / f"{name}.py").write_text(source, encoding="utf-8")
        cls.socket_dir = tempfile.TemporaryDirectory(prefix="cadgen-slots-", dir=None if os.name == "nt" else "/tmp")
        cls.address = rf"\\.\pipe\cadgen-slots-{os.getpid()}" if os.name == "nt" else str(Path(cls.socket_dir.name) / "d.sock")
        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
        cls.env = dict(os.environ)
        cls.env.update({
            "CADGEN_CACHE_DIR": str(cls.work / "store"),
            "CADGEN_DAEMON_STATE_DIR": str(cls.work / "state"),
            "CADGEN_DAEMON_SOCKET": cls.address,
            "CADGEN_DAEMON": "1",  # the runner may export 0; these clients go warm
            "CADGEN_DAEMON_SPARES": "1",
            "CADGEN_DAEMON_IDLE_TIMEOUT": "600",
            "CADGEN_JOBS": str(cls.LIMIT),
            # Slots are the subject; memory admission has its own suite. Give these tiny
            # solids a bounded budget instead of depending on host RAM.
            "CADGEN_MEMORY_MB": "8192",
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT / "packages" / "cadgen" / "src")]
                + [os.path.abspath(p) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
            ),
        })
        cls.env.pop("CADGEN_DAEMON_CHILD", None)
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
                transport.connect(cls.address, _authkey(cls.address)).close()
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
        # Windows refuses to delete a file another process still has open, and a
        # killed worker releases its handle on the daemon log a beat after the kill.
        deadline = time.monotonic() + 15
        while True:
            try:
                cls.socket_dir.cleanup()
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        cls.work_tmp.cleanup()

    def _run(self, script: str, *, store: str = "store") -> tuple[int, str, list[dict]]:
        env = {**self.env, "CADGEN_CACHE_DIR": str(self.work / store)}
        proc = subprocess.run(
            [sys.executable, script, "--json"], cwd=str(self.src), env=env,
            capture_output=True, text=True, timeout=900,
        )
        events = [json.loads(line) for line in proc.stderr.splitlines() if line.startswith("{")]
        return proc.returncode, proc.stdout + proc.stderr, events

    def _peak_running(self) -> int:
        status = daemon_client.status() or {}
        jobs = status.get("jobsRunning") or {}
        self.assertEqual(jobs.get("limit"), self.LIMIT, status)
        return int(jobs.get("peakRunning") or 0)

    def test_a_one_slot_daemon_finishes_the_three_level_tree(self):
        code, output, events = self._run("robot.py")
        self.assertEqual(code, 0, output)
        self.assertIn('"outcome":"built"', output)
        done = [Path(e["model"]).stem for e in events if e["state"] == "done"]
        self.assertEqual(sorted(done), ["arm", "pin", "robot"])
        # robot asks for pin twice, once itself and once through arm: built once per run.
        self.assertEqual(done.count("pin"), 1, "the shared child was built more than once")
        self.assertEqual(self._peak_running(), 1, "two things ran at once on a one-slot daemon")

    def test_two_parents_sharing_a_child_build_it_once_in_a_run(self):
        code, output, events = self._run("both.py", store="store-both")
        self.assertEqual(code, 0, output)
        done = [Path(e["model"]).stem for e in events if e["state"] == "done"]
        self.assertEqual(done.count("pin"), 1, "the shared child was built more than once")
        self.assertEqual(sorted(done), ["both", "parent_a", "parent_b", "pin"])
        self.assertEqual(self._peak_running(), 1)


if __name__ == "__main__":
    unittest.main()
