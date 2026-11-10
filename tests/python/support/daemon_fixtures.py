"""Shared fixtures for the daemon suite (``tests/python/packages/cad_server/engine/test_daemon_*.py``): the
models its tests build, a page's reads, and ``DaemonCase``, the class engine each file's builds go through.

Importing this puts the packages' sources on ``sys.path``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad.engine import xbf

SIZE = {size}


@xbf("XBF/block.xbf")
def block():
    return bd.fillet(bd.Box(SIZE, 4, 2).edges().filter_by(bd.Axis.Z), 0.5)

if __name__ == "__main__":
    block()
"""


# A bare model: no file, its document the worker's memory alone.
BARE = """
import build123d as bd
from cad.engine import model


@model
def bracket():
    return bd.Box({size}, 2, 3)

if __name__ == "__main__":
    bracket()
"""


def get(url: str, token: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer "+token}), timeout=120) as response:
        return response.read()


def get_json(url: str, token: str) -> dict:
    return json.loads(get(url, token))


class DaemonCase(unittest.TestCase):
    """Through the daemon. The class shares one engine, so a test's first build takes the standby the
    one before left, with the kernel loaded; each test builds scripts of a folder of its own, and
    reads the workers of its own scripts (``mine``). A test whose subject is the engine's start, its
    environment or all it holds starts an engine of its own (``own``)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = cls.engine(cls.addClassCleanup)

    @classmethod
    def engine(cls, cleanup, **extra: str) -> tuple[Path, dict]:
        """An engine folder and its environment, the engine stopped and the folder removed at ``cleanup``."""
        state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cleanup(shutil.rmtree, state, True)
        env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(state),
                                     "CAD_ENGINE_MESH": "inline", **extra}, cleanup)
        cleanup(cls.stopped, state, env)
        return state, env

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-daemon-")).resolve()
        # These are independent fixtures, not moved scripts: keep each original present while
        # the class's shared registry can match another fixture to it.
        self.addClassCleanup(shutil.rmtree, self.folder, True)
        self.state, self.env = self.shared
        self.script = self.folder / "block.py"

    def own(self, **extra: str) -> None:
        """An engine of the test's own from now on, started with ``extra`` in its environment."""
        self.state, self.env = self.engine(self.addCleanup, **extra)

    def mine(self, rows: list[dict]) -> list[dict]:
        """The rows of ``status``'s ``workers`` or ``retired`` that are this test's scripts' (a render
        process's retirement names a document)."""
        return [row for row in rows if "script" in row and Path(row["script"]).parent == self.folder]

    @staticmethod
    def stopped(state: Path, env: dict) -> None:
        engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=env)
        deadline = time.monotonic() + 20
        while any(state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)

    def _stop_daemon(self) -> None:
        self.stopped(self.state, self.env)

    def cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=self.folder, env=env or self.env)

    def run_script(self, name: str, env: dict | None = None) -> subprocess.CompletedProcess:
        """``python NAME``: the script asks the daemon to build its models."""
        return engine_daemon.run([sys.executable, name], cwd=self.folder, env=env or self.env)

    def built(self, name: str, env: dict | None = None) -> dict:
        """Model ``name`` of ``name.py`` built through the daemon by ``Model.build()``: its report."""
        probe = f"import json, {name}; print(json.dumps({name}.{name}.build().models[0]))"
        done = engine_daemon.run([sys.executable, "-B", "-c", probe], cwd=self.folder, env=env or self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def build(self, size: int) -> dict:
        self.script.write_text(textwrap.dedent(MODEL.format(size=size)), encoding="utf-8")
        return self.built("block")

    def _bare(self) -> str:
        """``bracket.py``: one bare ``@model``, a document of memory alone, and its id."""
        from cad.engine.ids import model_id

        script = self.folder / "bracket.py"
        script.write_text(textwrap.dedent(BARE.format(size=1)), encoding="utf-8")
        return model_id(script, "bracket")
