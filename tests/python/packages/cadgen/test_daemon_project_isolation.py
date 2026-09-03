"""A warm worker never executes two projects' code. End to end, real processes.

The defect this pins: routing keyed on the request's cwd, and `cadgen step build
models/juno/src/head.py` and `cadgen step build models/moonwatch/src/movement_base.py`
run from a repo root report the SAME cwd. So one worker served every project on the
machine -- and every cad-project keeps its shared code in `src/lib/`, so the second
project's `import lib` lands on a name the first project already bound. The loader
evicts foreign modules before each run, but that is a scrub over a shared process;
when it misses, the build succeeds against the WRONG project's helpers.

The projects below are the juno/moonwatch repro in miniature: two trees, each with its
own `lib.geometry`, each exporting a symbol the other does not have, so a leak fails
the build loudly instead of silently changing a dimension. The assertion is on ROUTING
rather than on the leak, because routing is what was fixed: a leak is a race, and a
test that has to lose a race to fail is a test that passes when the bug is back.

Pool-level dispatch (eviction, the cap, per-project serialization) is covered against
stub workers in test_daemon_pool; this is the one check that the supervisor derives the
project key from the real request and that real worker processes come out separated.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

from cadgen.daemon import client as daemon_client
from cadgen.daemon import transport

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"
SPAWN_WAIT_SECONDS = 90.0  # daemon startup pays the full OCP import once

# `lib` is a NAMESPACE package (no __init__.py), which is the cad-project layout and the
# harder case: a namespace package has no __file__, so the module-to-source-file scan
# cannot see it and it used to survive every eviction.
LIB_SOURCE = """\
WIDTH = {width}
ONLY_IN_{tag} = "{tag}"


def width():
    return WIDTH
"""

MODEL_SOURCE = """\
from build123d import Box

from cadgen import step
from lib.geometry import ONLY_IN_{tag}, width


@step
def model():
    # A leak from the other project shows up as an ImportError on this name, so a
    # crossed worker fails the build rather than quietly changing the box.
    assert ONLY_IN_{tag} == "{tag}"
    return Box(width(), 8.0, 4.0)


if __name__ == "__main__":
    model()
"""

PROJECTS = {
    # project directory -> (model script name, its distinguishing tag, box width)
    "alpha": ("head.py", "ALPHA", 10.0),
    "beta": ("movement_base.py", "BETA", 20.0),
}


def _authkey() -> bytes:
    key = transport.read_authkey(daemon_client.daemon_identity())
    if not key:
        raise RuntimeError("the daemon has not written its auth key")
    return key


class ProjectIsolation(unittest.TestCase):
    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        # AF_UNIX paths are length-limited (~104 bytes on macOS), so the socket gets a
        # short dir rather than the repo tmp root.
        cls.socket_dir = tempfile.TemporaryDirectory(
            prefix="cadgen-projects-",
            dir=None if os.name == "nt" else "/tmp",
            ignore_cleanup_errors=True,
        )
        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
        cls.workspace_tmp = temporary_directory(prefix="cadgen-projects-src-")
        cls.workspace = Path(cls.workspace_tmp.name)
        cls.scripts: dict[str, str] = {}
        for name, (script, tag, width) in PROJECTS.items():
            src = cls.workspace / name / "src"
            (src / "lib").mkdir(parents=True)
            (src / "lib" / "geometry.py").write_text(
                LIB_SOURCE.format(width=width, tag=tag), encoding="utf-8"
            )
            (src / script).write_text(MODEL_SOURCE.format(tag=tag), encoding="utf-8")
            # Relative to the WORKSPACE, so every request reports the same cwd -- the
            # shape that collapsed every project onto one worker.
            cls.scripts[name] = f"{name}/src/{script}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_server()
        cls.workspace_tmp.cleanup()
        cls.socket_dir.cleanup()

    @classmethod
    def _address(cls, suffix: str) -> str:
        if os.name == "nt":
            return rf"\\.\pipe\cadgen-projects-{os.getpid()}-{suffix}"
        return str(Path(cls.socket_dir.name) / f"{suffix}.sock")

    @classmethod
    def _stop_server(cls) -> None:
        if cls.server is not None and cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        cls.server = None

    @classmethod
    def _start_server(cls, address: str, *, max_workers: int | None = None) -> None:
        env = dict(os.environ)
        env["CADGEN_DAEMON_SOCKET"] = address
        env["CADGEN_DAEMON_IDLE_TIMEOUT"] = "300"  # orphan self-cleans if teardown is skipped
        if max_workers is not None:
            env["CADGEN_DAEMON_MAX_WORKERS"] = str(max_workers)
        with open(cls.log_path, "ab") as log_file:
            cls.server = subprocess.Popen(
                [sys.executable, str(DAEMON_DIR / "__main__.py")],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
        deadline = time.monotonic() + SPAWN_WAIT_SECONDS
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError(f"daemon exited during startup:\n{cls.log_path.read_text(encoding='utf-8')}")
            try:
                probe = transport.connect(address, _authkey())
            except (OSError, RuntimeError):
                time.sleep(0.1)
                continue
            probe.close()
            return
        raise RuntimeError(f"daemon address never appeared:\n{cls.log_path.read_text(encoding='utf-8')}")

    def _env(self, address: str) -> dict[str, str]:
        return {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": address}

    def _build(self, address: str, project: str) -> tuple[int | None, str]:
        """One warm --force build. --force matters: without it the no-op gate answers
        before the model is ever imported, and an import is what a leak needs."""
        out = io.StringIO()
        with mock.patch.dict(os.environ, self._env(address)):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            os.environ.pop("CADGEN_DAEMON_MAX_WORKERS", None)
            with redirect_stdout(out), redirect_stderr(out):
                code = daemon_client.run_via_daemon(
                    "run", [self.scripts[project], "--force"], cwd=str(self.workspace)
                )
        return code, out.getvalue()

    def _worker_projects(self, address: str) -> dict[int, str]:
        with mock.patch.dict(os.environ, self._env(address)):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            status = daemon_client.status()
        self.assertIsNotNone(status, "the daemon stopped answering")
        return {int(w["pid"]): str(w.get("project") or "") for w in status["workers"]}

    def test_interleaved_projects_land_on_separate_workers(self) -> None:
        address = self._address("pool")
        self._start_server(address)
        self.addCleanup(self._stop_server)

        pids_by_project: dict[str, set[int]] = {name: set() for name in PROJECTS}
        for round_index in range(3):
            for project in PROJECTS:
                code, output = self._build(address, project)
                self.assertEqual(
                    0, code, f"round {round_index} {project} failed:\n{output}"
                )
                for pid, owner in self._worker_projects(address).items():
                    if owner.endswith(f"{project}/src") or owner.endswith(
                        f"{project}{os.sep}src"
                    ):
                        pids_by_project[project].add(pid)

        alpha, beta = pids_by_project["alpha"], pids_by_project["beta"]
        self.assertEqual(len(alpha), 1, f"alpha did not converge on one worker: {alpha}")
        self.assertEqual(len(beta), 1, f"beta did not converge on one worker: {beta}")
        self.assertFalse(alpha & beta, "one worker served both projects")
        # And the supervisor really did key on the SCRIPT's directory, not on the shared
        # cwd every one of these requests reported.
        owners = set(self._worker_projects(address).values())
        self.assertEqual(len(owners), 2, f"expected one worker per project, got {owners}")
        self.assertNotIn(str(self.workspace), owners, "routing fell back to cwd")

    def test_a_single_worker_cap_respawns_per_project(self) -> None:
        # With room for one worker, alternating projects must EVICT and respawn. Reuse
        # is the bug, and a cap of one is where reuse is most tempting.
        self._stop_server()
        address = self._address("capped")
        self._start_server(address, max_workers=1)
        self.addCleanup(self._stop_server)

        pids_by_project: dict[str, set[int]] = {name: set() for name in PROJECTS}
        for round_index in range(2):
            for project in PROJECTS:
                code, output = self._build(address, project)
                self.assertEqual(
                    0, code, f"round {round_index} {project} failed:\n{output}"
                )
                resident = self._worker_projects(address)
                self.assertEqual(len(resident), 1, f"the cap of one was exceeded: {resident}")
                pid, owner = next(iter(resident.items()))
                self.assertTrue(
                    owner.endswith("src"), f"the resident worker is unbound: {owner!r}"
                )
                pids_by_project[project].add(pid)

        self.assertFalse(
            pids_by_project["alpha"] & pids_by_project["beta"],
            "a capped pool handed one process to both projects instead of respawning",
        )


if __name__ == "__main__":
    unittest.main()
