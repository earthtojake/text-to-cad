"""What the engine keeps of a model whose store is its ``.xbf``: every record until a person deletes it, from the
shell or the home, the person's files untouched; every document out of memory and out of its worker read again from
its file, nothing written in the cache folder; an ``.xbf`` of an older format, or of one no release reads, as it is
across restarts; and a shape whose ``.xbf`` is gone named by the program that handed it over. Through a class engine
of the file's own (``store_fixtures.StoreCase``), with an engine, a state and a cache folder of its own
(``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon, store_fixtures
from tests.python.support.store_fixtures import await_

from tests.python.support.ids import model_id
from cad_server.engine.registry import Registry

# The saved-format fixtures, the library's tests' (an old release's document).
FIXTURES = Path(__file__).resolve().parents[2] / "cad" / "engine" / "fixtures"


class StoreKeepingTest(store_fixtures.StoreCase):
    def home(self, action: str, path: str) -> tuple[int, dict]:
        """A change to the home's library, as the engine's page sends it (``PATCH /api/v1/documents``)."""
        serving = self.ask({"op": "status"})["serving"]
        request = urllib.request.Request(f"{serving['url']}/api/v1/documents", method="PATCH",
                                         data=json.dumps({"action": action, "path": path}).encode(),
                                         headers={"Authorization": "Bearer " + self.ask({"op": "http"})["token"],
                                                  "x-cad-viewer": "1", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_delete_is_one_function_from_the_shell_and_from_the_home(self) -> None:
        cube, other = self.write("cube"), self.write("other")
        for name in ("cube", "other"):
            self.run_script(name)
        # The shell refuses a document it cannot name, before anything is deleted.
        refused = self.cli("delete", cube, str(self.project / "nothing.py"), "--yes")
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn(f"no document is recorded for {self.project / 'nothing.py'}", refused.stderr)
        self.assertTrue(self.record(cube), "nothing was deleted")
        # It destroys, so it asks: --dry-run says what it would delete, and where no one can be asked nothing is
        # deleted without --yes.
        planned = self.cli("delete", cube, str(self.project / "other.py"), "--dry-run")
        self.assertEqual((planned.returncode, planned.stdout.splitlines()),
                         (0, ["would delete 2 documents: each one's record and what the engine holds of it (your own "
                              "files stay)", f"  cube {cube}", f"  other {other}"]))
        asked = self.cli("delete", cube, "--json")
        self.assertEqual((asked.returncode, json.loads(asked.stdout)["reason"]), (2, "confirmation_required"))
        self.assertTrue(self.record(cube), "nothing was deleted")
        # Several at once, an id and a model's script: a line each; the record and the engine's copy go; the
        # script and its .xbf stay.
        done = self.cli("delete", cube, str(self.project / "other.py"), "--yes")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, f"deleted cube {cube}\ndeleted other {other}\n", ""))
        for ident in (cube, other):
            self.assertEqual(self.record(ident), {})
        self.assertEqual([row["id"] for row in self.ask({"op": "status"})["models"]], [])
        self.assertTrue((self.project / "cube.py").is_file() and self.xbf("cube").is_file(), "never a file of the person's")
        # The next run registers it again; its .xbf by its path deletes it too.
        self.run_script("cube")
        self.assertTrue(self.record(cube))
        done = self.cli("delete", str(self.xbf("cube")), "--yes")
        self.assertEqual((done.returncode, done.stdout), (0, f"deleted cube {cube}\n"))
        self.run_script("cube")
        # The home's Delete is the same deletion; Remove is a file's alone.
        self.assertEqual(self.home("remove", cube)[0], 400, "a model's row is deleted, never removed")
        status, body = self.home("delete", cube)
        self.assertEqual(status, 200, body)
        self.assertNotIn(cube, [row.get("id") for row in body["documents"]])
        self.assertEqual(self.record(cube), {})
        # With no engine running, the shell deletes the record, and starts none.
        self.run_script("other")
        self.assertEqual(self.cli("stop").returncode, 0)
        done = self.cli("delete", other, "--json", "--yes")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads(done.stdout), {"ok": True, "deleted": [{"id": other, "name": "other", "kind": "model"}]})
        self.assertEqual(self.record(other), {})
        self.assertIn("the cad server is not running", self.cli("status").stdout)

    def legacy_xbf(self, data: bytes) -> tuple[str, dict]:
        """Historical bytes as a real registered model's .xbf, with its source gone."""
        ident = self.write("cube")
        self.run_script("cube")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.xbf("cube").write_bytes(data)
        (self.project / "cube.py").unlink()
        (self.project / "cube.ran").unlink()
        self.start()  # the next engine
        return ident, self.record(ident)

    def test_a_legacy_xbf_opens_after_restart_without_source_or_rewriting_it(self) -> None:
        from cad.engine import document, document_migrations, previous

        fixture = FIXTURES / "xbf8_materials.xbf"
        original = fixture.read_bytes()
        ident, record = self.legacy_xbf(original)
        original_closure = previous.read_record(document.read_bytes(original))[1]
        partial = self.folder / "must-not-write.step"
        refused = self.cli("export", ident, str(partial), str(self.xbf("cube")))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertFalse(partial.exists())
        self.assertEqual(self.xbf("cube").read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        for suffix in ("step", "glb", "xbf"):
            out = self.folder / f"migrated.{suffix}"
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertGreater(out.stat().st_size, 0)
        loaded = document.Loaded(self.folder / "migrated.xbf")
        self.assertEqual(document.written_format(loaded.writer), previous.FORMAT)
        self.assertEqual(previous.read_record(loaded.doc)[1], original_closure)
        self.assertEqual(document_migrations.provenance(loaded.doc)["origin"]["kind"], "file")
        launched = engine_daemon.run([sys.executable, "-m", "cad_server.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])
        status, shown = self.page(ident)
        self.assertEqual(status, 200, shown)
        self.assertEqual(self.cli("stop").returncode, 0)
        # The next daemon still opens the original file; nothing rewrites it.
        self.start()
        out = self.folder / "again.step"
        exported = self.cli("export", ident, str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(self.xbf("cube").read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        self.assertFalse(self.ran("cube"))

    def test_an_xbf_of_an_unsupported_format_is_preserved_across_restarts(self) -> None:
        from OCP.Standard import Standard_GUID
        from OCP.TDataStd import TDataStd_AsciiString
        from OCP.TCollection import TCollection_AsciiString
        from cad.engine import document

        fixture = FIXTURES / "xbf8_materials.xbf"
        doc = document.read_bytes(fixture.read_bytes())
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(document.WRITER_GUID),
                                 TCollection_AsciiString("cadgen.engine xbf/99 (cadgen 99.0.0)"))
        original = document.to_bytes(doc)
        ident, record = self.legacy_xbf(original)
        out = self.folder / "unsupported.step"
        for _ in range(2):
            self.start()  # the engine each time afresh
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 2, exported.stderr)
            self.assertIn("unsupported document format xbf/99", exported.stderr)
            self.assertFalse(out.exists())
            self.assertEqual(self.xbf("cube").read_bytes(), original)
            self.assertEqual(self.record(ident), record)
            self.assertEqual(self.cli("stop").returncode, 0)
        self.assertFalse(self.ran("cube"))

    def test_every_document_out_of_memory_is_read_again_from_its_xbf_and_the_cache_folder_is_not_touched(self) -> None:
        # Its workers go after each build, over a memory cap of 1 MB, and its memory budget is past at
        # once: every document leaves memory and its worker, and is read again from its .xbf.
        self.use(self.folder / "state", self.folder / "cache", CAD_ENGINE_WORKER_RSS_MB="1",
                 CAD_ENGINE_MEMORY_MB="0.001")
        foreign = self.cache / "objects" / "ab" / "0.7-object"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"a 0.7 store object")
        beside = self.cache / "index.db"
        beside.write_bytes(b"0.7")
        stamps = {path: path.stat().st_mtime_ns for path in (foreign, beside)}
        idents = [self.write(name) for name in ("first", "second", "third")]
        for name in ("first", "second", "third"):
            self.run_script(name)
        await_(lambda: self.ask({"op": "status"})["workers"] == [] and self.ask({"op": "status"})["models"] == [],
               "every worker retired: each document its .xbf")
        self.assertEqual([self.ask({"op": "state", "id": ident})["state"] for ident in idents], ["held"] * 3)
        for ident in idents:
            status, structure = self.page(ident)
            self.assertEqual(status, 200, structure)
        exported = self.cli("export", idents[0], str(self.folder / "first.step"))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(self.copies(), [])
        self.assertEqual({path: path.stat().st_mtime_ns for path in stamps}, stamps, "the rest of the folder is not ours")
        self.assertEqual(foreign.read_bytes(), b"a 0.7 store object")


class KeptTest(unittest.TestCase):
    """The book on its own: a shape whose ``.xbf`` is gone says to hand it over again, naming its program."""

    def test_a_shape_whose_xbf_is_gone_is_unsaved_and_names_the_program_that_handed_it_over(self) -> None:
        from cad_server.engine import registry as registering
        from cad_server.engine.models import Models as Book

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-shape-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")
        saved = folder / "crate.xbf"
        saved.write_bytes(b"x" * 10)
        from cad.engine.ids import file_id

        ident = file_id(saved)
        words = Book.shown(str(folder / "hand.py"))
        held.put({"id": ident, "kind": "shape", "root": str(folder), "home": "hand.py", "program": "hand.py",
                  "entry": "crate", "revision": "h1", "built": 1.0, "saved": "crate.xbf"})
        daemon = mock.Mock(server=None, builders={})
        with mock.patch.object(registering, "FACTORY", lambda: held):
            book = Book(daemon)
            self.assertEqual(book.state(ident), "held", "a restart: its .xbf is the document")
            saved.unlink()
            found = book.rebuild(ident)
        self.assertEqual((found["state"], found["rebuild"]), ("unsaved", None))
        self.assertIn(words, found["error"], "the words of the program its record names, not a Python session's")

if __name__ == "__main__":
    unittest.main()
