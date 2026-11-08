"""A value of another kernel's build handed over: described portably in the caller, made a document by the engine.

``model(value, name=...)`` with a CadQuery value (its producer portable: ``cad.registry``) sends the engine a
description and a BinTools dump instead of a document's bytes (``api.hand_over``); the daemon has its
documents worker make the document of it (``cad.engine.portable``) and holds, caches, serves and exports it
as any shape handed over. Here the values are stand-ins with CadQuery's class names on build123d's shapes
(``tests/python/support/cadquery_like.py``, copied beside the program), so the whole path runs through a real
daemon in private engine, state and cache folders with no CadQuery installed; the real CadQuery is the
``cadquery`` job's (``tests/python/packages/cadquery``).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
import urllib.request
from pathlib import Path

from tests.python.support import cadquery_like, engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine.ids import derived_id  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402

HANDED = """
import json
import sys

import cq_like
from cad import model

handle = model(cq_like.bracket_assembly(), name="bracket")
plate = model(cq_like.plate(), name="plate")
print("RESULT " + json.dumps({"id": handle.id, "url": handle.url, "plate": plate.id,
                              "shape": type(handle.shape).__name__, "integration": handle.report["integration"]}))
"""

EMPTY = """
import cq_like
from cad import model

model(cq_like.Workplane(cq_like.Vector()), name="points")
"""


def _served(url: str, ident: str) -> dict:
    page, _, query = url.partition("?")
    base = page.rsplit("/", 1)[0]
    token = dict(part.split("=", 1) for part in query.split("&") if "=" in part).get("token", "")

    def read(path: str) -> dict:
        request = urllib.request.Request(f"{base}{path}", headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - the engine's own server
            return json.loads(response.read())

    return read(read(f"/api/v1/documents/{ident}")["api"] + "/structure")


class PortableHandOverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="portable-")))
        cls.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.state, cls.cache = cls.folder / "state", cls.folder / "cache"
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.addClassCleanup(shutil.rmtree, cls.engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(cls.engine),
                                         "CAD_STATE_DIR": str(cls.state), "CAD_CACHE_DIR": str(cls.cache),
                                         "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")
        cls.project = cls.folder / "project"
        cls.project.mkdir()
        shutil.copy(cadquery_like.__file__, cls.project / "cq_like.py")
        for name, text in (("hand.py", HANDED), ("empty.py", EMPTY)):
            (cls.project / name).write_text(textwrap.dedent(text), encoding="utf-8")

    @classmethod
    def cli(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=cls.folder, env=cls.env)

    def test_a_portable_value_is_a_document_held_served_exported_and_kept_in_the_cache(self) -> None:
        done = engine_daemon.run([sys.executable, "hand.py"], cwd=self.project, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout.rsplit("RESULT ", 1)[1])
        ident = derived_id(self.project / "hand.py", "bracket")
        self.assertEqual((found["id"], found["plate"], found["shape"], found["integration"]),
                         (ident, derived_id(self.project / "hand.py", "plate"), "Assembly", "cadquery"))
        self.assertIn("bracket: handed over (", done.stdout)
        structure = _served(found["url"], ident)
        self.assertEqual(structure["name"], "bracket_assembly", "its page serves it, the root named as the assembly is")
        names = {prototype["name"] for prototype in structure["prototypes"]}
        self.assertTrue({"plate", "peg"} <= names, names)
        record = Registry(self.state).get(ident)
        self.assertEqual((record["kind"], record["entry"], record["program"]), ("shape", "bracket", "hand.py"))
        # Exported by its id, as any document the engine holds: the STEP names the assembly's parts.
        out = self.project / "bracket.step"
        exported = self.cli("export", ident, str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        text = out.read_text(encoding="utf-8", errors="replace")
        for name in ("plate", "peg", "bracket_assembly"):
            self.assertIn(f"'{name}'", text)
        # After a restart, from the cache: the bytes the worker made are an ordinary document.
        self.assertEqual(self.cli("stop").returncode, 0)
        again = self.cli("export", ident, str(self.project / "restarted.glb"))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue((self.project / "restarted.glb").is_file())

    def test_a_value_with_no_shape_is_refused_in_the_caller_before_the_engine_is_asked(self) -> None:
        done = engine_daemon.run([sys.executable, "empty.py"], cwd=self.project, env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("the Workplane's stack holds Vector, and no shape", done.stderr)


if __name__ == "__main__":
    unittest.main()
