"""What the engine keeps of a model whose store is its ``.xbf``: its place in the library until a person removes it
on the home, the person's files untouched; every document out of memory and out of its worker read again from
its file, nothing written in the cache folder; and an ``.xbf`` of an older format, or of one no release reads, as it
is across restarts. Through a class engine
of the file's own (``store_fixtures.StoreCase``), with an engine, a state and a cache folder of its own
(``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon, store_fixtures
from tests.python.support.store_fixtures import await_

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

    def test_remove_on_the_home_forgets_a_document_and_leaves_its_file(self) -> None:
        cube = self.write("cube")
        self.run_script("cube")
        self.assertEqual(self.entry(cube)["path"], str(self.xbf("cube")), "its run added its .xbf to the library")
        (self.cache / "documents" / cube / "checks").mkdir(parents=True, exist_ok=True)
        status, body = self.home("remove", cube)
        self.assertEqual(status, 200, body)
        self.assertNotIn(cube, [row["id"] for row in body["documents"]])
        self.assertIsNone(self.entry(cube))
        self.assertNotIn(cube, [row["id"] for row in self.ask({"op": "status"})["models"]], "what the engine held of it")
        self.assertFalse((self.cache / "documents" / cube).exists(), "and what its cache derived of it")
        self.assertTrue((self.project / "cube.py").is_file() and self.xbf("cube").is_file(), "never a file of the person's")
        # Nothing deletes a document: it is its file. The next run lists it again.
        self.assertEqual(self.home("delete", cube)[0], 400)
        self.assertEqual(self.ask({"op": "delete", "ids": [cube]}), {"failed": "unknown request 'delete'"})
        self.run_script("cube")
        self.assertEqual(self.entry(cube)["path"], str(self.xbf("cube")))

    def legacy_xbf(self, data: bytes) -> str:
        """Historical bytes as a model's .xbf the library knows, with its source gone: its id."""
        ident = self.write("cube")
        self.run_script("cube")
        self.assertEqual(self.cli("stop").returncode, 0)
        self.xbf("cube").write_bytes(data)
        (self.project / "cube.py").unlink()
        (self.project / "cube.ran").unlink()
        self.start()  # the next engine
        return ident

    def test_a_legacy_xbf_opens_after_restart_without_source_or_rewriting_it(self) -> None:
        from cad.engine import document, document_migrations, previous

        fixture = FIXTURES / "xbf8_materials.xbf"
        original = fixture.read_bytes()
        ident = self.legacy_xbf(original)
        original_closure = previous.read_record(document.read_bytes(original))[1]
        partial = self.folder / "must-not-write.step"
        refused = self.cli("export", ident, str(partial), str(self.xbf("cube")))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertFalse(partial.exists())
        self.assertEqual(self.xbf("cube").read_bytes(), original)
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
        ident = self.legacy_xbf(original)
        out = self.folder / "unsupported.step"
        for _ in range(2):
            self.start()  # the engine each time afresh
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 2, exported.stderr)
            self.assertIn("unsupported document format xbf/99", exported.stderr)
            self.assertFalse(out.exists())
            self.assertEqual(self.xbf("cube").read_bytes(), original)
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


if __name__ == "__main__":
    unittest.main()
