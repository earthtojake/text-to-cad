"""The registry: a record per document the engine built (or a page opened), in the user's state
folder, pointing and never caching; read again after a restart, so an id is known with the command
that builds it again and nothing is run; a moved script's record detached, listed, and removable; a
``memory`` document with none; a shape handed over recorded with no command, never detached. And
the declarations: a function in a saved file points; one in no file is refused, with the words
that hand its shape over instead; ``@model`` stacked with a file decorator is refused, saying which
to drop; a ``name=`` another declaration's record holds is refused, naming it."""

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
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine import records
from cad_server.engine import registry  # noqa: E402
from cad.engine.ids import model_id  # noqa: E402
from cad.engine.model import Model  # noqa: E402
from cad_server.engine.registry import Registry  # noqa: E402


def _record(ident: str, root: Path, **extra) -> dict:
    return {"id": ident, "kind": "model", "root": str(root), "home": "parts.py", "entry": "cube", **extra}


class RegistryTest(unittest.TestCase):
    """The filesystem registry: records in, records out."""

    def setUp(self) -> None:
        self.state = Path(os.path.realpath(tempfile.mkdtemp(prefix="registry-")))
        self.addCleanup(shutil.rmtree, self.state, True)
        self.registry = Registry(self.state)
        self.ident = model_id(self.state / "parts.py", "cube")

    def test_an_engine_record_reads_only_a_port_number(self) -> None:
        engines = self.state / registry.ENGINES
        engines.mkdir(parents=True, exist_ok=True)
        for port, read in ((3246, {"port": 3246}), (True, {}), ("3246", {}), (70000, {}), (3246.0, {})):
            (engines / "abc123.json").write_text(json.dumps({"schema": registry.ENGINE_SCHEMA, "port": port}),
                                                 encoding="utf-8")
            self.assertEqual(self.registry.engine("abc123"), read, port)

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
                         f"cad run {self.state / 'parts.py'}", "the script that defines it, not its caller")
        self.assertTrue(self.registry.delete(self.ident))
        self.assertEqual((self.registry.get(self.ident), self.registry.list()), (None, []))

    def test_the_rebuild_command_pastes_into_the_platform_s_shell(self) -> None:
        # Printed for a person to paste: quoted for a POSIX shell there; on Windows as cmd.exe and
        # PowerShell both read it, where a single quote would be part of the path.
        cases = ((False, "/m/caller.py", None, None, "cad run /m/caller.py"),
                 (False, "/my models/caller.py", None, None, "cad run '/my models/caller.py'"),
                 (True, "C:\\m\\caller.py", None, None, "cad run C:\\m\\caller.py"),
                 (True, "C:\\my models\\caller.py", None, None, 'cad run "C:\\my models\\caller.py"'),
                 # Built with packages ``cad run --with`` was given: ``cad run --with`` them again; on Windows
                 # a word cmd.exe would read an operator in (``>``: a redirection) in double quotes too.
                 (False, "/my models/caller.py", None, ["/w/my pkg", "pandas>=2"],
                  "cad run --with '/w/my pkg' --with 'pandas>=2' '/my models/caller.py'"),
                 (True, "C:\\my models\\caller.py", None, ["C:\\w\\my pkg", "pandas>=2", "scipy"],
                  'cad run --with "C:\\w\\my pkg" --with "pandas>=2" --with scipy "C:\\my models\\caller.py"'),
                 # Built by a Python of its own (a venv's): that Python runs it again, as its run did.
                 (False, "/my models/caller.py", "/w/.venv/bin/python", None,
                  "/w/.venv/bin/python '/my models/caller.py'"),
                 (True, "C:\\my models\\caller.py", "C:\\w\\.venv\\Scripts\\python.exe", None,
                  'C:\\w\\.venv\\Scripts\\python.exe "C:\\my models\\caller.py"'))
        for windows, program, python, given, pasted in cases:
            with self.subTest(program=program, python=python, given=given), \
                    mock.patch.object(records, "WINDOWS", windows):
                self.assertEqual(records.rerun(program, python, given), pasted)
        # The record names that Python (``python``: absent, the base's, which ``cad run`` reaches), or the
        # requirements ``cad run --with`` was given (``with``).
        self.registry.put({**_record(self.ident, self.state), "python": "/w/.venv/bin/python"})
        with mock.patch.object(records, "WINDOWS", False):
            self.assertEqual(registry.command(self.registry, self.registry.get(self.ident)),
                             f"/w/.venv/bin/python {self.state / 'parts.py'}")
        self.registry.put({**_record(self.ident, self.state), "with": ["/w/pkg", "pandas>=2"]})
        with mock.patch.object(records, "WINDOWS", False):
            self.assertEqual(registry.command(self.registry, self.registry.get(self.ident)),
                             f"cad run --with /w/pkg --with 'pandas>=2' {self.state / 'parts.py'}")

    def test_a_record_is_relocated_by_its_root_alone_and_a_shape_s_is_never_detached(self) -> None:
        moved = self.state / "elsewhere"
        self.registry.put(_record(self.ident, moved))
        record = self.registry.get(self.ident)
        self.assertEqual(registry.home(self.registry, record), moved / "parts.py")
        self.assertTrue(registry.detached(self.registry, record), "its script is not there")
        self.registry.put({**_record(self.ident, moved), "kind": "shape"})
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
        source = "from cad.engine import model\n\n@model\ndef cell():\n    return None\n"
        saved = folder / "cell.py"
        saved.write_text(source, encoding="utf-8")
        self.assertEqual(self.define(source, str(saved)).name, "cell")
        self.assertFalse(hasattr(self.define(source, str(saved)), "store"), "no store to choose")
        for nowhere in ("<stdin>", str(folder / "ipykernel_1" / "2.py")):  # a REPL's, a notebook cell's
            with self.subTest(file=nowhere), self.assertRaisesRegex(ValueError, r"model\(shape, name='cell'\)"):
                self.define(source, nowhere)
        # store= is gone: an unexpected keyword argument, as any name that never was (law 15).
        for given in ("@model(store='memory')", "@xbf('XBF/cell.xbf', store='memory')"):
            with self.subTest(given=given), self.assertRaisesRegex(
                    TypeError, r"^(model|xbf)\(\) got an unexpected keyword argument 'store'$"):
                self.define(source.replace("from cad.engine import model", "from cad.engine import model, xbf")
                            .replace("@model", given), str(saved))
        self.assertEqual(self.define(source.replace("@model", "@model(name='other')"), str(saved)).explicit_name, "other")

    def test_model_stacked_with_a_file_decorator_is_refused_saying_which_to_drop(self) -> None:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="store-")))
        self.addCleanup(shutil.rmtree, folder, True)
        saved = folder / "cell.py"
        saved.write_text("", encoding="utf-8")
        for stack in ("@model\n@xbf('XBF/cell.xbf')", "@step('cell.step')\n@model", "@glb('a.glb')\n@model\n@stl('a.stl')"):
            with self.subTest(stack=stack), self.assertRaisesRegex(
                    TypeError, "model 'cell' is declared by @model and @[a-z]+: .* never both; drop @model"):
                self.define(f"from cad.engine import model, xbf, step, glb, stl\n\n{stack}\ndef cell():\n"
                            "    return None\n", str(saved))
        both = self.define("from cad.engine import xbf, step\n\n@xbf('XBF/cell.xbf')\n@step('cell.step')\n"
                           "def cell():\n    return None\n", str(saved))
        self.assertEqual([kind for kind, _path in both.targets()], ["xbf", "step"], "file decorators stack")


PARTS = """
import build123d as bd
from cad import model


@model
def cube():
    return bd.Box(3, 2, 1)
"""

# Two scripts whose models claim one explicit name.
NAMED = """
import build123d as bd
from cad import model


@model(name="arm")
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
        # The registry alone, with a cache folder nothing can write: a restart knows an id by its
        # record and its command. What the cache adds is ``test_cache``'s.
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(cls.engine),
                                         "CAD_STATE_DIR": str(cls.state),
                                         "CAD_CACHE_DIR": engine_daemon.unwritable(cls.folder),
                                         "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.cli, "stop")

    @classmethod
    def cli(cls, *args: str, cwd: Path | None = None):
        return engine_daemon.run([sys.executable, "-m", "cad_server.engine", *args], cwd=cwd or cls.folder, env=cls.env)

    def run_python(self, *args: str, cwd: Path, input: str | None = None):
        return engine_daemon.run([sys.executable, *args], cwd=cwd, env=self.env, input=input)

    def project(self, name: str, files: dict[str, str]) -> Path:
        folder = self.folder / name
        folder.mkdir()
        for file, text in files.items():
            (folder / file).write_text(textwrap.dedent(text), encoding="utf-8")
        return folder

    def ask(self, message: dict) -> dict:
        from cad.engine.client import request

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            return request(message, start=False) or {}

    def records(self) -> dict[str, dict]:
        return {record["id"]: record for record in Registry(self.state).list()}

    def test_a_build_writes_its_record_alone_and_a_restart_knows_it_by_its_command(self) -> None:
        project = self.project("pointer", {"parts.py": PARTS,
                                           "caller.py": "import parts\n\nparts.cube()\n"})
        def listed() -> list[str]:  # the interpreter's own bytecode cache of parts.py is not cadgen's
            return sorted(name for name in os.listdir(project) if name != "__pycache__")

        before = listed()
        done = self.run_python("caller.py", cwd=project)
        self.assertEqual(done.returncode, 0, done.stderr)
        cube = model_id(project / "parts.py", "cube")
        record = self.records()[cube]
        self.assertEqual((record["kind"], record["home"], Path(record["root"])), ("model", "parts.py", project))
        # What a restart needs and no more: no closure (the document's own), no versions, no stamps,
        # no command (always `cad run` of its home), no record of the files it declared.
        self.assertEqual(set(record), {"schema", "id", "kind", "root", "home", "entry", "revision", "built", "created", "facts", "namespace", "name", "fingerprint", "module", "declares"})
        self.assertEqual(record["declares"], [], "the explicit names its script declares: none")
        self.assertEqual((record["namespace"], record["name"]), (str(project), "cube"))
        self.assertEqual(record["created"], record["built"], "a first build is when the model was created")
        self.assertEqual(sorted(os.listdir(self.state / "documents" / cube)), ["document.json"], "it points: no geometry")
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
        self.assertIn(f"run `cad run {project / 'parts.py'}`", inspected.stderr)
        answer = self.ask({"op": "state", "id": cube})
        self.assertEqual((answer["state"], answer["rebuild"]), ("unsaved", f"cad run {project / 'parts.py'}"))
        from cad_server.viewer.recents import RecentStore

        listed = {entry.path: entry.public() for entry in RecentStore(self.state).list()}
        self.assertEqual((listed[cube]["name"], listed[cube]["missing"]), ("cube", False))
        # The script moved: detached, listed and saying so, until it is removed.
        (project / "parts.py").rename(project / "moved.py")
        self.assertEqual(self.ask({"op": "state", "id": cube})["state"], "detached")
        self.assertTrue({entry.path: entry.public() for entry in RecentStore(self.state).list()}[cube]["missing"])
        RecentStore(self.state).remove(cube)
        self.assertFalse((self.state / "documents" / cube).exists())

    def test_a_name_another_declaration_s_record_holds_is_refused_naming_it(self) -> None:
        project = self.project("keyed", {"left.py": NAMED.format(name="left"), "right.py": NAMED.format(name="right")})
        first = self.run_python("left.py", cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        from cad.engine.ids import derived_id

        record = self.records()[derived_id(project, "arm")]
        self.assertEqual((record["line"], record["entry"]), (6, "left"))
        self.assertEqual((record["namespace"], record["name"]), (str(project), "arm"))
        from cad_server.viewer.recents import RecentStore

        recent = next(row.public() for row in RecentStore(self.state).list() if row.path == record["id"])
        self.assertEqual((recent["namespace"], recent["name"]), (str(project), "arm"))
        second = self.run_python("right.py", cwd=project)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn(f"{project / 'left.py'}:6", second.stderr)
        self.assertEqual(self.records()[derived_id(project, "arm")]["entry"], "left", "the record stays the first's")
        again = self.run_python("left.py", cwd=project)
        self.assertEqual(again.returncode, 0, again.stderr)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
