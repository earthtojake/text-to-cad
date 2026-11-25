"""Document ids: one formula for every document -- uuid5 of a file's canonical path, with no name: a file's, and so
a model's, whose document is its ``.xbf`` (at ``@model``'s path, else ``<name>.xbf`` beside its script), and a shape's
handed over -- the same in every process, and the one key the engine's server and the viewer agree on."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.addresses import document_id  # noqa: E402
from cad.engine import model as declaring  # noqa: E402
from cad.engine.ids import NAMESPACE, canonical, derived_id, file_id, is_id  # noqa: E402
from tests.python.support.ids import model_id  # noqa: E402

SCRIPT = """
from cad.engine import model

@model
def part():
    return None
"""


def _case_insensitive(folder: Path) -> bool:
    probe = folder / "Probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        return (folder / "probe.TXT").exists()
    finally:
        probe.unlink()


class IdsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-ids-"))  # as given: not canonical on macOS
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "parts.py"
        self.script.write_text(textwrap.dedent(SCRIPT), encoding="utf-8")

    def link(self, name: str, target: Path) -> Path:
        link = self.folder / name
        try:
            link.symlink_to(target)
        except OSError as error:  # Windows without the symlink privilege
            self.skipTest(f"no symlinks here: {error}")
        return link

    def test_a_model_s_id_is_the_same_in_another_process_and_asks_no_engine(self) -> None:
        probe = ("import json, sys; sys.path.insert(0, sys.argv[1]); import parts; "
                 "print(json.dumps(parts.part.id))")
        env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.folder / "no-engine")}
        done = subprocess.run([sys.executable, "-c", probe, str(self.folder)], capture_output=True, text=True,
                              env=env, cwd=self.folder, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1]), model_id(self.script, "part"))
        self.assertFalse((self.folder / "no-engine").exists(), "no engine was asked or started")

    def load(self, path: Path, function: str, decorator: str = "@model"):
        import importlib.util

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"from cad.engine import model, step\n{decorator}\ndef {function}():\n    return None\n",
                        encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"ids_{path.parent.name}_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, function)

    def test_a_model_s_id_is_its_xbf_s_file_id(self) -> None:
        def formula(path: Path) -> str:
            return str(uuid.uuid5(NAMESPACE, canonical(path) + "::"))

        cases = [("bare.py", "bare", "@model", "bare.xbf"),
                 ("named.py", "named", "@model(name='arm')", "arm.xbf"),
                 ("given.py", "given", "@model('XBF/given part.xbf')", "XBF/given part.xbf"),
                 ("out.py", "out", "@model(out='../up.xbf')", "../up.xbf"),
                 ("stepped.py", "stepped", "@step('stepped.step')", "stepped.xbf"),
                 ("deep/inner.py", "inner", "@model('inner.xbf')", "deep/inner.xbf")]
        for script, function, decorator, xbf in cases:
            with self.subTest(decorator=decorator):
                declared = self.load(self.folder / script, function, decorator)
                path = Path(os.path.normpath(self.folder / xbf))
                self.assertEqual(declared.xbf, Path(os.path.normpath(os.path.abspath(canonical(self.folder) + "/" + xbf))))
                self.assertEqual(declared.id, file_id(path))
                self.assertEqual(declared.id, formula(path), "the one formula: the file's path, no name")
                self.assertEqual(declared.id, document_id(str(path)), "its .xbf's path names the model")
        self.assertEqual(derived_id(self.folder, "plate"), str(uuid.uuid5(NAMESPACE, canonical(self.folder) + "::plate")))

    def test_models_that_write_one_xbf_share_its_id_and_nothing_is_refused(self) -> None:
        left = self.load(self.folder / "left.py", "left", "@model(name='arm')")
        right = self.load(self.folder / "right.py", "right", "@model('arm.xbf')")
        self.assertEqual(left.id, right.id, "one file, one id: the last build wins")
        self.assertEqual(self.load(self.folder / "a.py", "duplicate").id, self.load(self.folder / "b.py", "duplicate").id)
        self.assertNotEqual(self.load(self.folder / "other" / "left.py", "left", "@model(name='arm')").id, left.id)
        for bad in ("", " arm", "arm\n", 7, "x::y"):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                declaring.model(name=bad)
        for decorate in (declaring.model, lambda **kw: declaring.model("a.xbf", **kw)):
            with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'key'"):
                decorate(key="removed")

    def test_two_scripts_with_one_function_name_and_their_own_files_are_two_models(self) -> None:
        other = self.folder / "other.py"
        other.write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        self.assertNotEqual(model_id(self.script, "part"), model_id(other, "part", xbf="other.xbf"))
        self.assertNotEqual(model_id(self.script, "part"), model_id(self.script, "other"))
        self.assertNotEqual(model_id(self.script, "part"), file_id(self.script), "a model is not its script's file")

    def test_a_symlinked_or_differently_spelled_script_is_one_model(self) -> None:
        spellings = [self.link("alias.py", self.script), self.folder / "sub" / ".." / "parts.py"]
        if _case_insensitive(self.folder):
            spellings.append(self.folder / "PARTS.py")
        for spelling in spellings:
            with self.subTest(spelling=str(spelling)):
                self.assertEqual(model_id(spelling, "part"), model_id(self.script, "part"))
                # A script's name never names its model through the address: `parts.py::part` is a file name; its
                # .xbf's path does.
                self.assertNotEqual(document_id(f"{spelling}::part"), model_id(self.script, "part"))

    def test_a_symlinked_or_case_variant_file_is_one_file(self) -> None:
        target = self.folder / "Part.xbf"
        target.write_bytes(b"x")
        spellings = [self.link("alias.xbf", target)]
        if _case_insensitive(self.folder):
            spellings.append(self.folder / "PART.XBF")
        for spelling in spellings:
            with self.subTest(spelling=str(spelling)):
                self.assertEqual(canonical(spelling), canonical(target))
                self.assertEqual(file_id(spelling), file_id(target))
        self.assertEqual(Path(canonical(target)).name, "Part.xbf", "the name as the file system spells it")
        # A file not written yet keeps its name below the folder that exists, and keeps its id once written.
        later = self.folder / "later.xbf"
        before = file_id(later)
        later.write_bytes(b"x")
        self.assertEqual(file_id(later), before)

    def test_a_path_that_holds_a_hash_is_one_file_and_a_ref_follows_the_file(self) -> None:
        # ``FILE#REF``: a file's path may hold a '#' itself (a folder named project#1), and every command once cut
        # it there ("project#1/part.step is not a step file"). The file is the longest part that is one.
        from cad.engine.addresses import parts, split

        part = self.folder / "project#1" / "bracket#2.step"
        part.parent.mkdir()
        part.write_text("ISO-10303-21;", encoding="utf-8")
        ident = model_id(self.script, "part")
        self.assertEqual(parts(str(part)), (str(part), None))
        self.assertEqual(parts(f"{part}#arm/face 3"), (str(part), "arm/face 3"))
        self.assertEqual(split(f"{part}#arm")[1], "arm")
        self.assertEqual(parts(f"{ident}#bracket"), (ident, "bracket"))
        self.assertEqual(parts("#U3"), ("", "U3"))
        self.assertEqual(parts(str(self.folder / "gone.step#arm")), (str(self.folder / "gone.step"), "arm"))

    def test_derived_ids_are_version_5_uuids(self) -> None:
        for ident in (model_id(self.script, "part"), file_id(self.script)):
            self.assertTrue(is_id(ident))
            self.assertEqual(uuid.UUID(ident).version, 5)
            self.assertEqual(document_id(ident), ident, "an id names itself")
        self.assertFalse(is_id(str(uuid.uuid4()).upper()))
        self.assertFalse(is_id(str(self.script)))
        self.assertTrue(is_id(str(uuid.uuid4())), "the version is never a rule")


class ServedByIdTest(unittest.TestCase):
    def setUp(self) -> None:
        from cad.engine.serve import Server
        from tests.python.support.http_listener import listener

        self.folder = Path(tempfile.mkdtemp(prefix="engine-ids-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.server = Server(mesh_mode="inline", http_factory=listener)
        self.addCleanup(self.server.stop)

    def test_the_page_s_document_route_serves_by_id(self) -> None:
        path = self.folder / "part.xbf"
        ident = self.server.put(path, {"version": "one", "prototypes": [], "name": "part"}, {})
        self.assertEqual(ident, file_id(path))
        self.server.start()
        with urllib.request.urlopen(f"{self.server.url}/api/doc/{ident}", timeout=30) as response:  # noqa: S310
            self.assertEqual(json.loads(response.read())["version"], "one")
        self.assertEqual(self.server.listing(), [{"id": ident, "path": canonical(path)}])
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{self.server.url}/api/doc/{file_id(self.folder / 'other.xbf')}", timeout=30)  # noqa: S310
        self.assertEqual(refused.exception.code, 404)

    def test_a_symlinked_file_opened_two_ways_is_one_served_document(self) -> None:
        path = self.folder / "part.xbf"
        link = self.folder / "alias.xbf"
        try:
            link.symlink_to(path)
        except OSError as error:
            self.skipTest(f"no symlinks here: {error}")
        ident = self.server.put(path, {"version": "one", "prototypes": []}, {})
        self.assertEqual(self.server.put(link, {"version": "two", "prototypes": []}, {}), ident)
        self.assertEqual([row["id"] for row in self.server.listing()], [ident])
        self.assertEqual(canonical(canonical(link)), canonical(link), "a canonical path is its own spelling")
        self.assertEqual(self.server._ids([str(link)]), [ident], "a build writing the link names the one document")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
