"""Shared fixtures for the engine's store suite (``tests/python/packages/cad_server/engine/test_xbf_store.py``,
``test_store_keeping.py``): the models its tests build, and ``StoreCase``, the class engine each file's tests run
through, with a state and a cache folder of its own. A model's store is its ``.xbf``; the cache folder holds no copy
of it (``copies``).

Importing this puts the packages' sources on ``sys.path``."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from tests.python.support.ids import model_id  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402

SCRIPT = """
import pathlib
import build123d as bd
from cad.engine import model

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")
WIDTH = {width}


@model
def {name}():
    return bd.Box(WIDTH, 2, 1)


if __name__ == "__main__":
    {name}()
"""

# A model whose body says on stderr that it ran: the worker's output reaches the run's stderr.
SAID = """
import sys
import build123d as bd
from cad.engine import model

WIDTH = {width}


@model
def {name}():
{body}


if __name__ == "__main__":
    {name}()
"""
GOOD = '    print("the body ran", file=sys.stderr)\n    return bd.Box(WIDTH, 2, 1)'


def await_(condition, what: str, seconds: float = 60.0):
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


def get(url: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class StoreCase(unittest.TestCase):
    """Through a real daemon. The class shares one engine, with a state and a cache folder of its
    own (so its workers' bytecode is compiled once), and each test starts with nothing recorded in
    it; a test whose engine needs another environment, or folders of its own, starts that engine
    (``use``), which reads the class's bytecode."""

    @classmethod
    def setUpClass(cls) -> None:
        from cad.engine import places

        cls.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-store-")))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.shared = cls.root / "state", cls.root / "cache"
        cls.bytecode = str(cls.shared[1] / places.PYCACHE / places.bytecode_tag())  # the class engine's own
        cls.engine_env = cls.environment(*cls.shared, cls.addClassCleanup)

    @classmethod
    def environment(cls, state: Path, cache: Path, cleanup, **extra: str) -> dict:
        """An engine's environment: a folder of its own, ``state`` and ``cache``; stopped at ``cleanup``."""
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cleanup(shutil.rmtree, engine, True)
        # The class engine keeps its bytecode where the engine does (the first test reads it there),
        # whatever folder a test run shares.
        given = {name: value for name, value in os.environ.items() if name != "PYTHONPYCACHEPREFIX"}
        env = engine_daemon.watched({**given, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(engine),
                                     "CAD_STATE_DIR": str(state), "CAD_CACHE_DIR": str(cache),
                                     "CAD_ENGINE_MESH": "inline", **extra}, cleanup)
        cleanup(lambda: engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=dict(env)))
        return env

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="test-", dir=self.root))
        self.project = self.folder / "project"
        self.project.mkdir()
        (self.state, self.cache), self.env = self.shared, self.engine_env
        self.engine = Path(self.env["CAD_ENGINE_DIR"])
        self.start()  # the class's engine, which a test before may have left stopped
        self.reset()

    def reset(self) -> None:
        """Nothing recorded in the class's engine: every document an earlier test left, deleted."""
        from cad_server.engine import cli

        with mock.patch.dict(os.environ, {name: self.env[name] for name in
                                          ("CAD_ENGINE_DIR", "CAD_STATE_DIR", "CAD_CACHE_DIR")}):
            left = [row["id"] for row in Registry(self.state).list()]
            if left:
                cli.delete(left)

    def use(self, state: Path, cache: Path, **extra: str) -> None:
        """The engine the test talks to from now on: one of its own, on ``state`` and ``cache``."""
        self.state, self.cache = state, cache
        self.env = self.environment(state, cache, self.addCleanup, PYTHONPYCACHEPREFIX=self.bytecode, **extra)
        self.engine = Path(self.env["CAD_ENGINE_DIR"])

    def cli(self, *args: str, env: dict | None = None):
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=self.project, env=env or self.env)

    def start(self) -> None:
        """The test's engine started again after a stop: a restart, as ``cad server start`` starts one."""
        engine_daemon.start(self.env)

    def run_script(self, name: str):
        done = engine_daemon.run([sys.executable, f"{name}.py"], cwd=self.project, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def write(self, name: str, width: float = 3.0, text: str = SCRIPT) -> str:
        (self.project / f"{name}.py").write_text(textwrap.dedent(text.format(name=name, width=width)), encoding="utf-8")
        return model_id(self.project / f"{name}.py", name)

    def ask(self, message: dict) -> dict:
        from cad.engine.client import request

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def record(self, ident: str) -> dict:
        return Registry(self.state).get(ident) or {}

    def xbf(self, name: str) -> Path:
        """Model ``name``'s ``.xbf``, beside its script: its document, its store."""
        return self.project / f"{name}.xbf"

    def copies(self) -> list[Path]:
        """Every copy of a document in the cache folder (``documents/<id>/document.xbf``): none, ever."""
        return sorted((self.cache / "documents").glob("*/document.xbf"))

    def page(self, ident: str) -> tuple[int, dict]:
        serving = self.ask({"op": "status"})["serving"]
        return get(f"{serving['url']}/api/v1/documents/model/{ident}/structure", self.ask({"op": "http"}).get("token", ""))

    def ran(self, name: str) -> bool:
        return (self.project / f"{name}.ran").exists()

    def said(self, body: str = GOOD, width: float = 3.0) -> str:
        """``cube.py``, its model's body ``body``: the model's id."""
        (self.project / "cube.py").write_text(SAID.format(name="cube", width=width, body=body), encoding="utf-8")
        return model_id(self.project / "cube.py", "cube")
