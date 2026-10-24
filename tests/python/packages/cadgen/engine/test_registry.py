"""The registry: a record per document the engine built (or a page opened), in the user's state
folder, pointing and never caching; read again after a restart, so an id is known with the command
that builds it again and nothing is run; a moved script's record detached, listed, and removable; a
``memory`` document with none; a shape handed over recorded with no command, never detached. And
the declarations: a function in a saved file points; one in no file is refused, with the words
that hand its shape over instead; ``@model`` stacked with a file decorator is refused, saying which
to drop; a ``key=`` another declaration's record holds is refused, naming it."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import registry  # noqa: E402
from cadgen.engine.ids import model_id  # noqa: E402
from cadgen.engine.model import Model  # noqa: E402
from cadgen.engine.registry import Registry  # noqa: E402


def _record(ident: str, root: Path, **extra) -> dict:
    return {"id": ident, "kind": "model", "store": "pointer", "root": str(root), "home": "parts.py", "entry": "cube",
            "label": "cube", "run": ["python", "caller.py"], **extra}


class RegistryTest(unittest.TestCase):
    """The filesystem registry: records in, records out."""

    def setUp(self) -> None:
        self.state = Path(os.path.realpath(tempfile.mkdtemp(prefix="registry-")))
        self.addCleanup(shutil.rmtree, self.state, True)
        self.registry = Registry(self.state)
        self.ident = model_id(self.state / "parts.py", "cube")

    def test_a_record_is_written_once_until_it_changes_and_its_observers_hear_each_write(self) -> None:
        heard: list[dict] = []
        self.enterContext(mock.patch.object(registry, "OBSERVERS", [heard.append]))
        self.assertTrue(self.registry.put(_record(self.ident, self.state, revision="a")))
        written = self.state / "documents" / self.ident / "document.json"
        stamp = written.stat().st_mtime_ns
        self.assertFalse(self.registry.put(_record(self.ident, self.state, revision="a")), "unchanged: nothing written")
        self.assertEqual(written.stat().st_mtime_ns, stamp)
        self.assertTrue(self.registry.put(_record(self.ident, self.state, revision="b")))
        self.assertEqual([record["revision"] for record in heard], ["a", "b"])
        self.assertEqual([record["id"] for record in self.registry.list()], [self.ident])
        self.assertEqual(registry.command(self.registry, self.registry.get(self.ident)),
                         f"python {self.state / 'caller.py'}")
        self.assertTrue(self.registry.delete(self.ident))
        self.assertEqual((self.registry.get(self.ident), self.registry.list()), (None, []))

    def test_a_record_is_relocated_by_its_root_alone_and_a_shape_s_is_never_detached(self) -> None:
        moved = self.state / "elsewhere"
        self.registry.put(_record(self.ident, moved))
        record = self.registry.get(self.ident)
        self.assertEqual(registry.home(self.registry, record), moved / "parts.py")
        self.assertTrue(registry.detached(self.registry, record), "its script is not there")
        self.registry.put({**_record(self.ident, moved), "store": "shape", "run": []})
        record = self.registry.get(self.ident)
        self.assertFalse(registry.detached(self.registry, record), "a shape points at nothing that builds it")
        self.assertIsNone(registry.command(self.registry, record))


class StoreTest(unittest.TestCase):
    """What a declaration makes of a function: a document from its file, through one declaration."""

    def define(self, source: str, filename: str) -> Model:
        namespace: dict = {"__name__": "__main__"}
        exec(compile(source, filename, "exec"), namespace)  # noqa: S102
        return namespace["cell"]

    def test_a_saved_file_points_and_a_function_in_no_file_is_refused_with_the_shape_form(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="store-")))
        self.addCleanup(shutil.rmtree, folder, True)
        source = "from cadgen.engine import model\n\n@model\ndef cell():\n    return None\n"
        saved = folder / "cell.py"
        saved.write_text(source, encoding="utf-8")
        self.assertEqual(self.define(source, str(saved)).store, "pointer")
        self.assertEqual(self.define(source.replace("@model", "@model(store='memory')"), str(saved)).store, "memory")
        for nowhere in ("<stdin>", str(folder / "ipykernel_1" / "2.py")):  # a REPL's, a notebook cell's
            with self.subTest(file=nowhere), self.assertRaisesRegex(ValueError, r"model\(shape, name='cell'\)"):
                self.define(source, nowhere)
        with self.assertRaisesRegex(ValueError, "store is one of 'pointer', 'memory', not 'copy'"):
            self.define(source.replace("@model", "@model(store='copy')"), str(saved))
        with self.assertRaisesRegex(TypeError, "no name="):
            self.define(source.replace("@model", "@model(name='other')"), str(saved))

    def test_model_stacked_with_a_file_decorator_is_refused_saying_which_to_drop(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="store-")))
        self.addCleanup(shutil.rmtree, folder, True)
        saved = folder / "cell.py"
        saved.write_text("", encoding="utf-8")
        for stack in ("@model\n@xbf('XBF/cell.xbf')", "@step('cell.step')\n@model", "@glb('a.glb')\n@model\n@stl('a.stl')"):
            with self.subTest(stack=stack), self.assertRaisesRegex(
                    TypeError, "model 'cell' is declared by @model and @[a-z]+: .* never both; drop @model"):
                self.define(f"from cadgen.engine import model, xbf, step, glb, stl\n\n{stack}\ndef cell():\n"
                            "    return None\n", str(saved))
        both = self.define("from cadgen.engine import xbf, step\n\n@xbf('XBF/cell.xbf')\n@step('cell.step')\n"
                           "def cell():\n    return None\n", str(saved))
        self.assertEqual([kind for kind, _path in both.targets()], ["xbf", "step"], "file decorators stack")


PARTS = """
import build123d as bd
from cadgen import model


@model
def cube():
    return bd.Box(3, 2, 1)


@model(store="memory")
def scratch():
    return bd.Box(1, 1, 1)
"""

# Two scripts whose models claim one key.
KEYED = """
import build123d as bd
from cadgen import model


@model(key="arm")
def {name}():
    return bd.Box(1, 1, 1)


{name}()
"""


class RegistryDaemonTest(unittest.TestCase):
    """Through a real daemon in a private engine folder and state folder."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="registry-")))
        cls.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.state = cls.folder / "state"
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.addClassCleanup(shutil.rmtree, cls.engine, True)
        # The registry alone, with no cache (``CADGEN_ENGINE_CACHE_GB=0``): a restart knows an id by its
        # record and its command. What the cache adds is ``test_cache``'s.
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(cls.engine),
                                         "CADGEN_STATE_DIR": str(cls.state), "CADGEN_ENGINE_IDLE": "120",
                                         "CADGEN_ENGINE_MESH": "inline", "CADGEN_ENGINE_CACHE_GB": "0"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")

    @classmethod
    def cli(cls, *args: str, cwd: Path | None = None):
        return engine_daemon.run([sys.executable, "-m", "cadgen.engine", *args], cwd=cwd or cls.folder, env=cls.env)

    def run_python(self, *args: str, cwd: Path, input: str | None = None):
        return engine_daemon.run([sys.executable, *args], cwd=cwd, env=self.env, input=input)

    def project(self, name: str, files: dict[str, str]) -> Path:
        folder = self.folder / name
        folder.mkdir()
        for file, text in files.items():
            (folder / file).write_text(textwrap.dedent(text), encoding="utf-8")
        return folder

    def ask(self, message: dict) -> dict:
        from cadgen.engine.client import request

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def records(self) -> dict[str, dict]:
        return {record["id"]: record for record in Registry(self.state).list()}

    def test_a_build_writes_its_record_alone_and_a_restart_knows_it_by_its_command(self) -> None:
        project = self.project("pointer", {"parts.py": PARTS,
                                           "caller.py": "import parts\n\nparts.cube()\nparts.scratch()\n"})
        def listed() -> list[str]:  # the interpreter's own bytecode cache of parts.py is not cadgen's
            return sorted(name for name in os.listdir(project) if name != "__pycache__")

        before = listed()
        done = self.run_python("caller.py", cwd=project)
        self.assertEqual(done.returncode, 0, done.stderr)
        cube, scratch = model_id(project / "parts.py", "cube"), model_id(project / "parts.py", "scratch")
        record = self.records()[cube]
        self.assertEqual((record["store"], record["home"], record["run"], Path(record["root"])),
                         ("pointer", "parts.py", ["python", "caller.py"], project))
        self.assertEqual(sorted(os.listdir(self.state / "documents" / cube)), ["document.json"], "it points: no geometry")
        self.assertNotIn(scratch, self.records(), "a memory document has no record")
        self.assertEqual(listed(), before, "nothing beside the script")
        written = (self.state / "documents" / cube / "document.json").stat().st_mtime_ns
        again = self.run_python("caller.py", cwd=project)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual((self.state / "documents" / cube / "document.json").stat().st_mtime_ns, written,
                         "an unchanged build rewrites nothing")
        # A restart: the id is known, not held, with the command that builds it again; nothing runs it.
        self.assertEqual(self.cli("stop").returncode, 0)
        inspected = self.cli("inspect", cube)
        self.assertEqual(inspected.returncode, 2, inspected.stderr)
        self.assertIn(f"run `python {project / 'caller.py'}`", inspected.stderr)
        answer = self.ask({"op": "state", "id": cube})
        self.assertEqual((answer["state"], answer["rebuild"]), ("evicted", f"python {project / 'caller.py'}"))
        self.assertEqual(self.ask({"op": "state", "id": scratch})["state"], "evicted", "a memory id is unknown")
        from cadgen.viewer.recents import RecentStore

        listed = {entry.path: entry.public() for entry in RecentStore(self.state).list()}
        self.assertEqual((listed[cube]["name"], listed[cube]["missing"]), ("cube", False))
        self.assertNotIn(scratch, listed)
        # The script moved: detached, listed and saying so, until it is removed.
        (project / "parts.py").rename(project / "moved.py")
        self.assertEqual(self.ask({"op": "state", "id": cube})["state"], "detached")
        self.assertTrue({entry.path: entry.public() for entry in RecentStore(self.state).list()}[cube]["missing"])
        RecentStore(self.state).remove(cube)
        self.assertFalse((self.state / "documents" / cube).exists())

    def test_a_key_another_declaration_s_record_holds_is_refused_naming_it(self) -> None:
        project = self.project("keyed", {"left.py": KEYED.format(name="left"), "right.py": KEYED.format(name="right")})
        first = self.run_python("left.py", cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        from cadgen.engine.ids import key_id

        record = self.records()[key_id("arm")]
        self.assertEqual((record["key"], record["entry"]), ("arm", "left"))
        second = self.run_python("right.py", cwd=project)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn(f"key 'arm' is claimed by {project / 'left.py'}::left", second.stderr)
        self.assertEqual(self.records()[key_id("arm")]["entry"], "left", "the record stays the first's")
        again = self.run_python("left.py", cwd=project)
        self.assertEqual(again.returncode, 0, again.stderr)


if __name__ == "__main__":
    unittest.main()
