"""What the engine's document cache keeps: every document until a person deletes it, from the shell
or the home, with no cap and nothing evicted, touching nothing in its folder but ``documents/``; a
cached document of an older format, or of one no release reads, as it is across restarts; and an
engine whose cache folder is read-only, or not writable at all, saves nothing and does everything else
as ever. Through a class engine of the file's own (``cache_fixtures.CacheCase``), with an engine, a state and a
cache folder of its own (``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``), and the cache on its own."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import cache_fixtures, engine_daemon
from tests.python.support.cache_fixtures import await_

from cad.engine.ids import model_id
from cad_server.engine.registry import Registry

# The saved-format fixtures, the library's tests' (an old release's document).
FIXTURES = Path(__file__).resolve().parents[2] / "cad" / "engine" / "fixtures"


class CacheKeepingTest(cache_fixtures.CacheCase):
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
        for name, ident in (("cube", cube), ("other", other)):
            self.run_script(name)
            self.cached(ident)
        # The shell refuses a document it cannot name, before anything is deleted.
        refused = self.cli("delete", cube, str(self.project / "nothing.py"), "--yes")
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn(f"no document is recorded for {self.project / 'nothing.py'}", refused.stderr)
        self.assertTrue(self.record(cube) and self.file(cube).is_file(), "nothing was deleted")
        # It destroys, so it asks: --dry-run says what it would delete, and where no one can be asked nothing is
        # deleted without --yes.
        planned = self.cli("delete", cube, str(self.project / "other.py"), "--dry-run")
        self.assertEqual((planned.returncode, planned.stdout.splitlines()),
                         (0, ["would delete 2 documents: each one's record, its document in the engine's cache and "
                              "what the engine holds of it (your own files stay)", f"  cube {cube}", f"  other {other}"]))
        asked = self.cli("delete", cube, "--json")
        self.assertEqual((asked.returncode, json.loads(asked.stdout)["reason"]), (2, "confirmation_required"))
        self.assertTrue(self.record(cube) and self.file(cube).is_file(), "nothing was deleted")
        # Several at once, an id and a model's script: a line each; the record, the cached document and
        # the engine's copy go; the script stays.
        done = self.cli("delete", cube, str(self.project / "other.py"), "--yes")
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, f"deleted cube {cube}\ndeleted other {other}\n", ""))
        for ident in (cube, other):
            self.assertEqual(self.record(ident), {})
            self.assertFalse(self.file(ident).parent.exists())
        self.assertEqual([row["id"] for row in self.ask({"op": "status"})["models"]], [])
        self.assertEqual(self.page(cube)[0], 404, "the engine holds it no more")
        self.assertTrue((self.project / "cube.py").is_file(), "never a file of the person's")
        # The next run registers it again, and the cache keeps it again.
        self.run_script("cube")
        self.cached(cube)
        # The home's Delete is the same deletion; Remove is a file's alone.
        self.assertEqual(self.home("remove", cube)[0], 400, "a model's row is deleted, never removed")
        status, body = self.home("delete", cube)
        self.assertEqual(status, 200, body)
        self.assertNotIn(cube, [row.get("id") for row in body["documents"]])
        self.assertEqual(self.record(cube), {})
        self.assertFalse(self.file(cube).parent.exists())
        self.assertEqual(self.page(cube)[0], 404)
        # With no engine running, the shell deletes the record and its file, and starts none.
        self.run_script("other")
        self.cached(other)
        self.assertEqual(self.cli("stop").returncode, 0)
        done = self.cli("delete", other, "--json", "--yes")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads(done.stdout), {"ok": True, "deleted": [{"id": other, "name": "other", "kind": "model"}]})
        self.assertEqual((self.record(other), self.file(other).parent.exists()), ({}, False))
        self.assertIn("no engine server is running", self.cli("status").stdout)

    def legacy_cache(self, data: bytes) -> tuple[str, dict]:
        """Install historical bytes in a real registered model's cache, with its source gone."""
        ident = self.write("cube")
        self.run_script("cube")
        self.cached(ident)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.file(ident).write_bytes(data)
        Registry(self.state).update(ident, lambda record: {
            **record, "cache": {**record["cache"], "bytes": len(data)},
        })
        (self.project / "cube.py").unlink()
        (self.project / "cube.ran").unlink()
        return ident, self.record(ident)

    def test_legacy_cached_snapshot_opens_after_restart_without_source_or_rewriting_cache(self) -> None:
        from cad.engine import document, document_migrations, previous

        fixture = FIXTURES / "xbf8_materials.xbf"
        original = fixture.read_bytes()
        ident, record = self.legacy_cache(original)
        original_closure = previous.read_record(document.read_bytes(original))[1]
        partial = self.folder / "must-not-write.step"
        refused = self.cli("export", ident, str(partial), str(self.file(ident)))
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn("cached document is preserved", refused.stderr)
        self.assertFalse(partial.exists())
        self.assertEqual(self.file(ident).read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        for suffix in ("step", "glb", "xbf"):
            out = self.folder / f"migrated.{suffix}"
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertGreater(out.stat().st_size, 0)
        loaded = document.Loaded(self.folder / "migrated.xbf")
        self.assertEqual(document.written_format(loaded.writer), previous.FORMAT)
        self.assertEqual(previous.read_record(loaded.doc)[1], original_closure)
        self.assertEqual(document_migrations.provenance(loaded.doc)["origin"], {
            "kind": "document", "id": ident, "script": str(self.project / "cube.py"), "closure_base": None,
        })
        launched = engine_daemon.run([sys.executable, "-m", "cad_server.viewer", "--json", "--api-only", ident],
                                     cwd=self.project, env=self.env)
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual([row["id"] for row in json.loads(launched.stdout)["documents"]], [ident])
        status, shown = self.page(ident)
        self.assertEqual(status, 200, shown)
        self.assertEqual(self.cli("stop").returncode, 0)
        # The next daemon still opens the original snapshot; no migration cache/revision churn.
        out = self.folder / "again.step"
        exported = self.cli("export", ident, str(out))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual(self.file(ident).read_bytes(), original)
        self.assertEqual(self.record(ident), record)
        self.assertFalse(self.ran("cube"))

    def test_unsupported_cached_format_is_preserved_across_restarts(self) -> None:
        from OCP.Standard import Standard_GUID
        from OCP.TDataStd import TDataStd_AsciiString
        from OCP.TCollection import TCollection_AsciiString
        from cad.engine import document

        fixture = FIXTURES / "xbf8_materials.xbf"
        doc = document.read_bytes(fixture.read_bytes())
        TDataStd_AsciiString.Set_s(doc.Main(), Standard_GUID(document.WRITER_GUID),
                                 TCollection_AsciiString("cadgen.engine xbf/99 (cadgen 99.0.0)"))
        original = document.to_bytes(doc)
        ident, record = self.legacy_cache(original)
        out = self.folder / "unsupported.step"
        for _ in range(2):
            exported = self.cli("export", ident, str(out))
            self.assertEqual(exported.returncode, 2, exported.stderr)
            self.assertIn("unsupported document format xbf/99", exported.stderr)
            self.assertFalse(out.exists())
            self.assertEqual(self.file(ident).read_bytes(), original)
            self.assertEqual(self.record(ident), record)
            self.assertEqual(self.cli("stop").returncode, 0)
        self.assertFalse(self.ran("cube"))

    def test_every_document_stays_until_deleted_and_nothing_else_in_the_folder_is_touched(self) -> None:
        # Its workers go after each build, over a memory cap of 1 MB, and its memory budget is past at
        # once: every document leaves memory, and the cache keeps them all.
        self.use(self.folder / "state", self.folder / "cache", CAD_ENGINE_WORKER_RSS_MB="1",
                 CAD_ENGINE_MEMORY_MB="0.001")
        foreign = self.cache / "objects" / "ab" / "0.7-object"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"a 0.7 store object")
        beside = self.cache / "index.db"
        beside.write_bytes(b"0.7")
        stamps = {path: path.stat().st_mtime_ns for path in (foreign, beside)}
        idents = [self.write(name) for name in ("first", "second", "third")]
        for name, ident in zip(("first", "second", "third"), idents):
            self.run_script(name)
            self.cached(ident)
        # Out of memory, each read again from the cache: its worker gone and the server's copy trimmed.
        held = lambda: [(row["state"], row.get("held")) for row in self.ask({"op": "status"})["models"]]  # noqa: E731
        await_(lambda: self.ask({"op": "status"})["workers"] == [] and held() == [("held", "disk")] * 3,
               "every document out of memory and held on disk alone")
        self.assertTrue(all(self.file(ident).is_file() for ident in idents), "nothing evicts a document")
        cache = self.ask({"op": "status"})["cache"]
        self.assertEqual(sorted(cache), ["bytes", "documents", "enabled", "failures", "idleSeconds", "root",
                                         "written"], "no cap, no evictions")
        self.assertEqual((cache["documents"], cache["root"]), (3, str(self.cache)))
        total = sum(self.file(ident).stat().st_size for ident in idents)
        from cad.engine.said import size

        self.assertIn(f"cache {self.cache}: 3 documents · {size(total)}, kept until deleted\n", self.cli("status").stdout)
        exported = self.cli("export", idents[0], str(self.folder / "first.step"))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual({path: path.stat().st_mtime_ns for path in stamps}, stamps, "the rest of the folder is not ours")
        self.assertEqual(foreign.read_bytes(), b"a 0.7 store object")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "a read-only folder is POSIX's, and refuses no one running as root")
    def test_with_its_cache_folder_read_only_the_engine_saves_nothing_and_does_everything_else(self) -> None:
        def scenario(tag: str, **extra: str) -> dict:
            if tag == "read-only":
                self.use(self.folder / f"state-{tag}", self.folder / f"cache-{tag}", **extra)
                self.cache.mkdir()
                self.cache.chmod(stat.S_IRUSR | stat.S_IXUSR)
                self.addCleanup(self.cache.chmod, stat.S_IRWXU)
            else:  # no folder can be made there at all: a file is in its place
                self.use(self.folder / f"state-{tag}", Path(engine_daemon.unwritable(self.folder / tag)), **extra)
            ident = self.write("cube")
            seen: dict = {"build": [line for line in self.run_script("cube").stdout.splitlines() if "id:" in line]}
            await_(lambda: self.ask({"op": "status"})["cache"]["failures"], "the idle save tried and failed")
            status, structure = self.page(ident)
            seen["page"] = (status, sorted(structure))
            seen["state"] = self.ask({"op": "state", "id": ident})
            out = self.folder / f"{tag}.xbf"
            seen["export"] = (self.cli("export", ident, str(out)).returncode, out.read_bytes())
            seen["inspect"] = self.cli("inspect", ident, "--query", "closure").stdout
            listed = self.ask({"op": "status"})
            seen["models"] = [(row["state"], row.get("held")) for row in listed["models"]]
            failures = listed["cache"]["failures"]
            self.assertEqual(self.cli("stop").returncode, 0)
            (self.project / "cube.ran").unlink()
            again = self.cli("inspect", ident)
            seen["restart"] = (again.returncode, again.stderr)
            seen["restart state"] = self.ask({"op": "state", "id": ident})
            seen["restart page"] = self.page(ident)
            seen["ran"] = self.ran("cube")
            self.assertEqual(self.cli("stop").returncode, 0)
            seen = json.loads(json.dumps(seen, default=lambda value: value.hex()).replace(str(self.state), "STATE"))
            return seen, failures, list(self.cache.iterdir()) if self.cache.is_dir() else []

        read_only, failures, left = scenario("read-only")
        self.assertTrue(failures, "the failed save is listed")
        self.assertEqual(left, [], "and nothing is cached")
        unwritable, failures, _left = scenario("unwritable")
        self.assertTrue(failures, "the failed save is listed there too")
        self.assertEqual(read_only, unwritable, "every verb, every state, every message alike: nothing saved")
        self.assertEqual(read_only["restart"][0], 2, "after a restart it is not held: its command is said")


class KeptTest(unittest.TestCase):
    """The cache on its own: it has no cap, and keeps every file it writes, a shape handed over's as a
    model's; a document whose file is gone says to hand it over again."""

    def test_no_cap_every_file_written_stays(self) -> None:
        from cad_server.engine import cache as engine_cache

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-kept-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")

        class Models:
            def registry(self) -> Registry:
                return held

            def row(self, _ident: str) -> None:
                return None

        names = ["a_shape", "a_model", "b_shape", "b_model"]
        idents = {name: model_id(folder / f"{name}.py", name) for name in names}
        for name, ident in idents.items():
            held.put({"id": ident, "kind": "shape" if name.endswith("shape") else "model",
                      "root": str(folder), "home": f"{name}.py", "entry": name, "revision": "r1"})
        self.assertFalse(hasattr(engine_cache, "cap") or hasattr(engine_cache, "CACHE_GB"), "no cap to set")
        first, second = engine_cache.Cache(Models()), engine_cache.Cache(Models())
        for name in names[:3]:
            first._write(idents[name], "r1", b"x" * 1000)
        second._write(idents["b_model"], "r1", b"x" * 1000)  # an engine started after the first three
        kept = {name for name, ident in idents.items() if (folder / "cache" / "documents" / ident / "document.xbf").is_file()}
        self.assertEqual(kept, set(names), "every file stays")
        self.assertTrue(all(held.get(ident)["cache"]["bytes"] == 1000 for ident in idents.values()))
        status = second.status()
        self.assertEqual((status["documents"], status["bytes"]), (4, 4000))
        self.assertNotIn("capBytes", status)
        self.assertNotIn("evictions", status)

    def test_a_document_at_the_cache_s_revision_is_never_written_again(self) -> None:
        from cad_server.engine import cache as engine_cache

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-once-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")
        ident = model_id(folder / "cube.py", "cube")
        held.put({"id": ident, "kind": "model", "root": str(folder), "home": "cube.py", "entry": "cube", "revision": "r1"})

        class Models:
            def registry(self) -> Registry:
                return held

            def row(self, _ident: str) -> dict:
                return {"revision": "r1", "worker": None, "version": "g2"}

            def held_bytes(self, _ident: str, _version: str) -> bytes:
                raise AssertionError("an unchanged document's bytes are never taken")

        kept = engine_cache.Cache(Models())
        kept._write(ident, "r1", b"x" * 1000)
        path = folder / "cache" / "documents" / ident / "document.xbf"
        stamps = (path.stat().st_mtime_ns, held.get(ident))
        kept._due(ident)  # idle again, unchanged
        kept.keep(ident, "r1", b"y" * 10)  # the drain's bytes, unchanged
        self.assertEqual((list(kept.writes), kept.written), ([], 1))
        self.assertEqual((path.stat().st_mtime_ns, held.get(ident)), stamps, "the file and its record as they were")

    def test_a_shape_taken_up_after_a_restart_and_unsaved_names_the_program_that_handed_it_over(self) -> None:
        from cad_server.engine import registry as registering
        from cad_server.engine.models import Models as Book

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-shape-")))
        self.addCleanup(shutil.rmtree, folder, True)
        held = Registry(folder / "state", folder / "cache")
        ident = model_id(folder / "hand.py", "crate")
        words = Book.shown(str(folder / "hand.py"))
        held.put({"id": ident, "kind": "shape", "root": str(folder), "home": "hand.py", "program": "hand.py",
                  "entry": "crate", "revision": "h1", "built": 1.0})
        held.cache.write(f"documents/{ident}/document.xbf", b"x" * 10)
        held.update(ident, lambda found: {**found, "cache": {"revision": "h1", "bytes": 10}})
        daemon = mock.Mock(server=None)
        with mock.patch.object(registering, "FACTORY", lambda: held):
            book = Book(daemon)
            book.adopt(ident)  # a restart: taken up from its record, its cache file at its revision
            self.assertEqual(book.state(ident), "held")
            book.cache.remove(ident)  # its file gone (its bytes did not read)
            found = book.rebuild(ident)
        self.assertEqual((found["state"], found["rebuild"]), ("unsaved", None))
        self.assertIn(words, found["error"], "the words of the program its record names, not a Python session's")


if __name__ == "__main__":
    unittest.main()
