"""Shared fixtures for the engine's document cache suite (``tests/python/packages/cad_server/engine/
test_cache_*.py``): the models its tests build, and ``CacheCase``, the class engine each file's tests
run through, with a state and a cache folder of its own.

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

from cad.engine.ids import model_id  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402

IDLE = 0.3  # the cache's idle seam (``CAD_ENGINE_CACHE_IDLE``), in seconds

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


class CacheCase(unittest.TestCase):
    """Through a real daemon. The class shares one engine, with a state and a cache folder of its
    own (so its workers' bytecode is compiled once), and each test starts with nothing recorded in
    it; a test whose engine needs another environment, or folders of its own, starts that engine
    (``use``), which reads the class's bytecode."""

    @classmethod
    def setUpClass(cls) -> None:
        from cad.engine import places

        cls.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-cache-")))
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
                                     "CAD_ENGINE_MESH": "inline", "CAD_ENGINE_CACHE_IDLE": str(IDLE),
                                     **extra}, cleanup)
        cleanup(lambda: engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], env=dict(env)))
        return env

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="test-", dir=self.root))
        self.project = self.folder / "project"
        self.project.mkdir()
        (self.state, self.cache), self.env = self.shared, self.engine_env
        self.engine = Path(self.env["CAD_ENGINE_DIR"])
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

    def file(self, ident: str) -> Path:
        return self.cache / "documents" / ident / "document.xbf"

    def cached(self, ident: str, revision: str | None = None) -> dict:
        """The record's ``cache`` field, once its file is there (at ``revision``, when given)."""
        def found():
            meta = self.record(ident).get("cache")
            ok = meta and self.file(ident).is_file() and (revision is None or meta["revision"] == revision)
            return meta if ok else None

        return await_(found, f"{ident}'s cache file")

    def page(self, ident: str) -> tuple[int, dict]:
        serving = self.ask({"op": "status"})["serving"]
        return get(f"{serving['url']}/api/v1/documents/model/{ident}/structure", self.ask({"op": "http"}).get("token", ""))

    def ran(self, name: str) -> bool:
        return (self.project / f"{name}.ran").exists()

    def said(self, body: str = GOOD, width: float = 3.0) -> str:
        """``cube.py``, its model's body ``body``: the model's id."""
        (self.project / "cube.py").write_text(SAID.format(name="cube", width=width, body=body), encoding="utf-8")
        return model_id(self.project / "cube.py", "cube")
