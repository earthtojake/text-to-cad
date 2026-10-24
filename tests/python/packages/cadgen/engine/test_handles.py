"""A model call returns its document's handle -- never a bare shape, never a report -- and
``model(shape, name=...)`` makes a document of a shape a program holds.

A handle has the document's id and page; its ``shape`` is transferred into the caller, the kernel
loaded, on first access and never before; ``handle.export(...)`` is ``export(handle, ...)``. Inside a
body a child's call returns its handle too, whose ``shape`` is the result in the worker, which the
caller composes. A shape handed over is held, cached and served as a drained document is, its page
and its export work, its record says a program the engine did not run showed it (no command builds
it again), ``key=`` names it, and the animations passed with it are baked into its GLB. Through a
real daemon in private engine, state and cache folders."""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import tempfile
import textwrap
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine.ids import derived_id, key_id, model_id  # noqa: E402
from cadgen.engine.registry import Registry  # noqa: E402

PARTS = """
import build123d as bd
from cadgen import model, xbf


@model
def peg():
    return bd.Cylinder(2, 10)


@xbf("XBF/base.xbf")
def base():
    first, second = peg(), peg()
    # A child's call is its handle, inside the body too: its id, no page yet, its result here.
    assert type(first).__name__ == "Document" and first.id == peg.id and first.url is None, first
    return bd.Compound(children=[bd.Box(20, 20, 3), first.shape.moved(bd.Pos(5, 0, 6)),
                                 second.shape.moved(bd.Pos(-5, 0, 6))], label="base")
"""

CALLER = """
import json
import sys

import cadgen
import parts

handle = parts.base()
before = "OCP" in sys.modules
shape = handle.shape
handle.export("out/a.step")
cadgen.export(handle, "out/b.step")
print("RESULT " + json.dumps({
    "type": type(handle).__name__, "id": handle.id, "url": handle.url, "name": handle.name,
    "kernel_before": before, "kernel_after": "OCP" in sys.modules, "volume": shape.volume,
    "labels": sorted(child.label for child in shape.children), "again": handle.shape is shape}))
"""

HANDED = """
import json

import build123d as bd
from cadgen import model
from cadgen.gltf import animation

lid = bd.Box(10, 10, 2)
lid.label = "lid"
crate = bd.Compound(children=[bd.Box(10, 10, 10), lid.moved(bd.Pos(0, 0, 6))], label="crate")
lift = animation(crate, "lift", duration=2).translation("lid", by=(0, 0, 10), end=2)
handle = model(crate, name="crate", animations=[lift])
handle.export("crate.glb", "crate.step")
tag = model(bd.Box(1, 1, 1), name="tag", key="crate-tag")
print("RESULT " + json.dumps({"id": handle.id, "url": handle.url, "same": handle.shape is crate, "tag": tag.id}))
"""


def _served(url: str, ident: str) -> dict:
    """The document a page serves (``/api/doc/<id>``), with the token its URL carries."""
    page, _, query = url.partition("?")
    base = page.rsplit("/", 1)[0]
    token = dict(part.split("=", 1) for part in query.split("&") if "=" in part).get("token", "")
    request = urllib.request.Request(f"{base}/api/doc/{ident}", headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - the engine's own server
        return json.loads(response.read())


def _glb_json(path: Path) -> dict:
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length])


class HandleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="handles-")))
        cls.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.state, cls.cache = cls.folder / "state", cls.folder / "cache"
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.addClassCleanup(shutil.rmtree, cls.engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(cls.engine),
                                         "CADGEN_STATE_DIR": str(cls.state), "CADGEN_CACHE_DIR": str(cls.cache),
                                         "CADGEN_ENGINE_IDLE": "120", "CADGEN_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")

    @classmethod
    def cli(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=cls.folder, env=cls.env)

    def project(self, name: str, files: dict[str, str]) -> Path:
        folder = self.folder / name
        folder.mkdir()
        for file, text in files.items():
            (folder / file).write_text(textwrap.dedent(text), encoding="utf-8")
        return folder

    def run_python(self, *args: str, cwd: Path, input: str | None = None) -> dict:
        done = engine_daemon.run([sys.executable, *args], cwd=cwd, env=self.env, input=input)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.rsplit("RESULT ", 1)[1])

    def ask(self, message: dict) -> dict:
        from cadgen.engine.client import request

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def test_a_call_returns_a_handle_whose_shape_loads_on_first_access_and_a_child_s_composes(self) -> None:
        project = self.project("parts", {"parts.py": PARTS, "caller.py": CALLER})
        found = self.run_python("caller.py", cwd=project)
        ident = model_id(project / "parts.py", "base")
        self.assertEqual((found["type"], found["id"], found["name"]), ("Document", ident, "base"))
        self.assertTrue(found["url"].split("?")[0].endswith(f"/{ident}"), found["url"])
        self.assertEqual((found["kernel_before"], found["kernel_after"]), (False, True),
                         "the shape is transferred, and the kernel loaded, on its first access alone")
        self.assertAlmostEqual(found["volume"], 20 * 20 * 3 + 2 * 3.141592653589793 * 2 ** 2 * 10, places=3)
        self.assertEqual(found["labels"], ["part1", "peg", "peg"], "the built shape, the children's results placed")
        self.assertTrue(found["again"], "transferred once")
        self.assertEqual((project / "out/a.step").read_bytes(), (project / "out/b.step").read_bytes(),
                         "handle.export is export(handle)")
        self.assertEqual(_served(found["url"], ident)["name"], "base", "its page serves it")

    def test_a_shape_handed_over_is_a_document_held_served_exported_and_never_rebuilt(self) -> None:
        project = self.project("handed", {"hand.py": HANDED})
        found = self.run_python("hand.py", cwd=project)
        ident = derived_id(project / "hand.py", "crate")
        self.assertEqual((found["id"], found["tag"], found["same"]), (ident, key_id("crate-tag"), True))
        self.assertEqual(_served(found["url"], ident)["name"], "crate", "its page serves it")
        self.assertEqual([clip["name"] for clip in _glb_json(project / "crate.glb").get("animations") or []],
                         ["lift"], "the animations passed are baked into its GLB")
        self.assertTrue((project / "crate.step").is_file())
        record = Registry(self.state).get(ident)
        self.assertEqual((record["store"], record["run"], record["entry"]), ("shape", [], "crate"))
        self.assertIn("a program the engine did not run: no script to rerun", record["shown"])
        # From a REPL: the working folder is its scope.
        repl = self.run_python("-", cwd=project, input="import json, build123d as bd\nfrom cadgen import model\n"
                               "h = model(bd.Box(2, 2, 2), name='scratch')\nprint('RESULT ' + json.dumps(h.id))\n")
        self.assertEqual(repl, derived_id(project, "scratch"))
        # Exported by its id, as any document the engine holds; after a restart, from the cache.
        self.assertEqual(self.cli("export", ident, str(project / "again.stl")).returncode, 0)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.cli("export", ident, str(project / "restarted.stl")).returncode, 0)
        # With its cache file gone, nothing builds it again, and the words say so.
        self.assertEqual(self.cli("stop").returncode, 0)
        shutil.rmtree(self.cache / "documents" / ident)
        refused = self.cli("export", ident, str(project / "gone.stl"))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("a program the engine did not run: no script to rerun", refused.stderr)
        answer = self.ask({"op": "state", "id": ident})
        self.assertEqual((answer["state"], answer["rebuild"]), ("evicted", None))


if __name__ == "__main__":
    unittest.main()
