"""A build's import path is exactly ``python script.py``'s: the script's folder, then
the caller's ``PYTHONPATH``. cadgen infers no root from directory names, and the daemon
carries the client's ``PYTHONPATH`` into each job and out again."""

from __future__ import annotations

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

from cadgen._internal.import_roots import import_roots, pythonpath_entries  # noqa: E402
from cadgen.daemon import client as daemon_client  # noqa: E402
from cadgen.daemon import transport  # noqa: E402

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"

PLATE = """\
from cadgen import step
from cadgen import build123d as bd
from lib.dims import W


@step
def plate():
    return bd.Box(W, 4.0, 2.0)


if __name__ == "__main__":
    plate()
"""


def _write_project(root: Path, width: float) -> Path:
    src = root / "src"
    (src / "lib").mkdir(parents=True)
    (src / "parts").mkdir()
    (src / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (src / "lib" / "dims.py").write_text(f"W = {width}\n", encoding="utf-8")
    script = src / "parts" / "plate.py"
    script.write_text(PLATE, encoding="utf-8")
    return script


def _base_env(work: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "CADGEN_CACHE_DIR": str(work / "store"),
        "CADGEN_DAEMON_STATE_DIR": str(work / "state"),
    })
    for key in ("CADGEN_DAEMON_CHILD", "CADGEN_ROOT_ID", "CADGEN_BROKER", "CADGEN_BROKER_KEY", "CADGEN_EVENTS"):
        env.pop(key, None)
    return env


def _cadgen_src() -> str:
    return str(REPO_ROOT / "packages" / "cadgen" / "src")


def _run(script: Path, env: dict[str, str], *extra: str) -> subprocess.CompletedProcess:
    # From a cwd that is NOT the project, so nothing resolves by accident.
    return subprocess.run(
        [sys.executable, str(script), "--json", *extra], cwd=str(script.parents[2]), env=env,
        capture_output=True, text=True, timeout=600,
    )


class ImportRootsHelper(unittest.TestCase):
    def test_the_roots_are_the_folder_then_pythonpath_and_nothing_inferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "STEP").mkdir()
            (root / "STEP" / "__init__.py").write_text("", encoding="utf-8")
            (root / "robot_common").mkdir()
            (root / "robot_common" / "__init__.py").write_text("", encoding="utf-8")
            script = root / "src" / "parts" / "plate.py"
            script.parent.mkdir(parents=True)
            script.write_text("", encoding="utf-8")
            extra = root / "src"
            previous = os.environ.get("PYTHONPATH")
            os.environ["PYTHONPATH"] = os.pathsep.join([str(extra), str(root / "missing"), ""])
            try:
                roots = import_roots(script)
                entries = pythonpath_entries()
            finally:
                if previous is None:
                    os.environ.pop("PYTHONPATH", None)
                else:
                    os.environ["PYTHONPATH"] = previous
            self.assertEqual(roots[0], str(script.parent.resolve()))
            self.assertIn(str(extra.resolve()), roots)
            self.assertNotIn(str(root.resolve()), roots, "an ancestor holding STEP/ or robot_common/ is not a root")
            self.assertEqual(entries, [str(extra.resolve())], "missing and empty PYTHONPATH entries are dropped")


class TransientExecutor(unittest.TestCase):
    def test_pythonpath_is_the_only_way_to_a_shared_root(self) -> None:
        with temporary_directory(prefix="cadgen-roots-transient-") as tmp:
            work = Path(tmp)
            script = _write_project(work / "proj", 10.0)
            env = _base_env(work)
            env["CADGEN_DAEMON"] = "0"
            env["PYTHONPATH"] = _cadgen_src()
            failed = _run(script, env)
            self.assertNotEqual(failed.returncode, 0, failed.stdout)
            self.assertIn("ModuleNotFoundError", failed.stderr)
            self.assertIn("No module named 'lib'", failed.stderr)
            self.assertNotIn("sys.path", failed.stderr, "the plain Python error, no teaching")
            env["PYTHONPATH"] = os.pathsep.join([_cadgen_src(), str(work / "proj" / "src")])
            built = _run(script, env)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertIn('"outcome":"built"', built.stdout)
            self.assertTrue((work / "proj" / "src" / "parts" / "plate.step").is_file())


class DaemonExecutor(unittest.TestCase):
    """The client's PYTHONPATH travels with the job and leaves with it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.work_tmp = temporary_directory(prefix="cadgen-roots-daemon-")
        cls.work = Path(cls.work_tmp.name)
        cls.socket_dir = tempfile.TemporaryDirectory(prefix="cadgen-roots-sock-")
        # Windows has no filesystem sockets: the daemon listens on a named pipe there.
        cls.address = rf"\\.\pipe\cadgen-roots-{os.getpid()}" if os.name == "nt" else os.path.join(cls.socket_dir.name, "d.sock")
        cls.env = _base_env(cls.work)
        cls.env["CADGEN_DAEMON_SOCKET"] = cls.address
        cls.env["PYTHONPATH"] = _cadgen_src()
        cls.env["CADGEN_JOBS"] = "2"
        os.environ["CADGEN_DAEMON_SOCKET"] = cls.address
        os.environ["CADGEN_DAEMON_STATE_DIR"] = cls.env["CADGEN_DAEMON_STATE_DIR"]
        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
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
                key = transport.read_authkey(daemon_client.daemon_identity())
                if key:
                    transport.connect(cls.address, key).close()
                    break
            except (OSError, RuntimeError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("daemon never came up")

    @classmethod
    def tearDownClass(cls) -> None:
        status = daemon_client.status() or {}
        if cls.server.poll() is None:
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

    def test_a_job_sees_its_own_pythonpath_and_the_next_one_does_not(self) -> None:
        script = _write_project(self.work / "proj", 12.0)
        with_root = dict(self.env)
        with_root["PYTHONPATH"] = os.pathsep.join([_cadgen_src(), str(self.work / "proj" / "src")])
        built = _run(script, with_root)
        self.assertEqual(built.returncode, 0, built.stderr + self.log_path.read_text(encoding="utf-8"))
        self.assertIn('"outcome":"built"', built.stdout)
        # The same model again — served by the worker now bound to it — without the
        # project's root: the previous job's path must not linger.
        without_root = dict(self.env)
        failed = _run(script, without_root, "--force")
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertIn("No module named 'lib'", failed.stderr)
        self.assertNotIn("sys.path", failed.stderr)
        # And with the root again, on the same bound worker, it builds.
        again = _run(script, with_root, "--force")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('"outcome":"built"', again.stdout)


if __name__ == "__main__":
    unittest.main()
