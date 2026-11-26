"""The library file (the project folders, the files a person opened, pinned, built, shared or forked) and the note
the cache keeps of a file: one entry of one file, written whole under one lock, readable by this user alone; a shared
file's entry kept while a share of it is live, its expired shares going as the library is written; a note that holds
for one version of its file; and what 0.11.17 kept, a record per document, carried once and removed."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

from cad.engine.ids import derived_id, file_id  # noqa: E402
from cad_server.engine import library as library_module  # noqa: E402
from cad_server.engine.library import Library, Notes  # noqa: E402
from cad_server.engine.state import file_version  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class LibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="library-")))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state, self.cache, self.work = self.tmp / "state", self.tmp / "cache", self.tmp / "work"
        self.work.mkdir()
        self.now = [1_764_000_000.0]
        self.library = Library(self.state, self.cache, clock=lambda: self.now[0])

    def file(self, name: str, data: bytes = b"solid t\nendsolid t\n") -> Path:
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def on_disk(self) -> dict:
        return json.loads((self.state / "library.json").read_text(encoding="utf-8"))

    def test_a_file_opened_pinned_and_forgotten_is_one_entry_of_one_file(self) -> None:
        arm, tag = self.file("arm.xbf"), self.file("tag.stl")
        self.assertTrue(self.library.know(arm), "a run's first build of it")
        self.assertFalse(self.library.know(arm))
        self.assertEqual(self.on_disk(), {"schema": 1, "projects": {}, "files": {
            file_id(arm): {"path": str(arm), "created": 1_764_000_000.0}}})
        written = (self.state / "library.json").stat().st_mtime_ns
        self.library.know(arm)
        self.assertEqual((self.state / "library.json").stat().st_mtime_ns, written, "nothing changed: nothing written")
        # Opened by a path through a link: one entry, its canonical path's, which keeps how it was reached.
        try:
            os.symlink(self.work, self.tmp / "linked", target_is_directory=True)
            reached = self.tmp / "linked" / "arm.xbf"
        except (OSError, NotImplementedError):
            reached = None
        self.now[0] += 100
        self.library.opened(reached or arm)
        self.library.pin(tag, True)
        expected = {"path": str(arm), "created": 1_764_000_000.0, "opened": 1_764_000_100.0}
        if reached is not None:
            expected["reached"] = str(reached)
        self.assertEqual(self.on_disk()["files"], {file_id(arm): expected, file_id(tag): {
            "path": str(tag), "created": 1_764_000_100.0, "pinned": True}}, "a pin makes the entry it has none of")
        self.assertEqual(self.library.path_of(file_id(arm)), str(arm))
        self.assertEqual((self.state / "library.json").read_text(encoding="utf-8"),
                         json.dumps(self.on_disk(), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        self.library.pin(tag, False)
        self.assertNotIn("pinned", self.on_disk()["files"][file_id(tag)])
        # A file that is gone goes with the next write, unless it is pinned: that one comes back with its file.
        gone, kept = self.file("gone.stl"), self.file("kept.stl")
        self.library.opened(gone)
        self.library.pin(kept, True)
        gone.unlink()
        kept.unlink()
        self.library.forget(file_id(tag))
        self.assertEqual(sorted(self.on_disk()["files"]), sorted([file_id(arm), file_id(kept)]))
        self.assertIsNone(self.library.path_of(file_id(gone)))

    def test_a_shared_files_entry_stays_while_a_share_is_live_and_is_this_users_alone(self) -> None:
        live = {"link": "https://cad.fun/" + "a" * 22, "write": "w" * 43, "delete": "d" * 43,
                "expires": "2999-01-01T00:00:00Z", "root": str(self.work), "entry": None}
        spent = {**live, "link": "http://127.0.0.1:1/" + "b" * 22, "expires": "2020-01-01T00:00:00Z"}
        shared, forked = self.file("shared.stl"), self.file("copy/arm.xbf")

        def keep(data: dict) -> None:
            data["files"][file_id(shared)] = {"path": str(shared), "created": 1.0,
                                              "shares": {"https://cad.fun": live, "http://127.0.0.1:1": spent}}
            data["files"][file_id(forked)] = {"path": str(forked), "created": 1.0, "imported": live["link"]}

        self.library.change(keep)
        # The share past its expiry goes as the library is written; the live one, and the link a fork came from, stay.
        self.assertEqual(self.on_disk()["files"][file_id(shared)]["shares"], {"https://cad.fun": live})
        self.assertEqual(self.on_disk()["files"][file_id(forked)]["imported"], live["link"])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.state / "library.json").stat().st_mode), 0o600,
                             "it holds the shares' keys")
        # Its file gone, a shared file's entry stays while its share is live, and goes with it; a forked one goes.
        shared.unlink()
        forked.unlink()
        self.library.opened(self.file("other.stl"))
        self.assertEqual(sorted(self.on_disk()["files"]), sorted([file_id(shared), file_id(self.work / "other.stl")]))
        self.library.change(lambda data: data["files"][file_id(shared)]["shares"]["https://cad.fun"].update(
            expires="2020-01-02T00:00:00Z"))
        self.assertEqual(list(self.on_disk()["files"]), [file_id(self.work / "other.stl")])

    def test_writers_at_once_lose_no_entry(self) -> None:
        files = [self.file(f"part_{index}.stl") for index in range(40)]
        start = threading.Barrier(8)

        def write(mine: list[Path]) -> None:
            start.wait(10)
            for path in mine:
                Library(self.state, self.cache).opened(path)  # each its own object, as each caller in the engine has

        writers = [threading.Thread(target=write, args=(files[index::8],)) for index in range(8)]
        for writer in writers:
            writer.start()
        for writer in writers:
            writer.join(30)
        self.assertEqual(sorted(self.on_disk()["files"]), sorted(file_id(path) for path in files))

    def test_a_library_that_does_not_read_is_set_aside_and_started_again(self) -> None:
        self.state.mkdir()
        (self.state / "library.json").write_text("{ not json", encoding="utf-8")
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self.assertEqual(self.library.read(), {"schema": 1, "projects": {}, "files": {}})
        self.assertIn("library.json.unreadable", said.getvalue())
        self.assertEqual((self.state / "library.json.unreadable").read_text(encoding="utf-8"), "{ not json")
        self.library.opened(self.file("tag.stl"))
        self.assertEqual(list(self.on_disk()["files"]), [file_id(self.work / "tag.stl")])

    def test_a_note_holds_for_one_version_of_its_file(self) -> None:
        notes = Notes(self.cache)
        arm = self.file("arm.xbf", b"one")
        ident, first = file_id(arm), file_version(arm)
        self.assertEqual(notes.read(ident, first), {}, "nothing seen of it yet")
        notes.count(arm, 3)
        notes.picture(arm, PNG)
        note = notes.read(ident, first)
        self.assertEqual((note["parts"], note["version"], notes.png(ident, first)), (3, first, PNG))
        folder = self.cache / "documents" / ident
        self.assertEqual(sorted(os.listdir(folder)), ["note.json", "picture.png"])
        self.assertEqual(set(json.loads((folder / "note.json").read_text(encoding="utf-8"))),
                         {"schema", "version", "parts", "pictured"})
        # The file written again: the note says nothing of it, and the next fill replaces it whole.
        arm.write_bytes(b"another, longer")
        second = file_version(arm)
        self.assertEqual((notes.read(ident, second), notes.png(ident, second)), ({}, None))
        notes.count(arm, 5)
        self.assertEqual(json.loads((folder / "note.json").read_text(encoding="utf-8")),
                         {"schema": 1, "version": second, "parts": 5})
        self.assertFalse((folder / "picture.png").exists(), "the picture of the version before went with its note")

    def test_the_records_of_0_11_17_are_carried_once_and_removed(self) -> None:
        """A state and a cache folder as 0.11.17 wrote them (``Registry.put``'s ``document.json``, one per
        document; Recents' pictures; the cache's copy of a model's document)."""
        opened, gone, script = self.file("bracket.step"), self.file("gone.stl"), self.file("parts.py", b"")
        gone.unlink()
        model = derived_id(script, "arm")  # 0.11.17's id of a model: its script and its function

        def record(ident: str, **fields) -> None:
            folder = self.state / "documents" / ident
            folder.mkdir(parents=True)
            (folder / "document.json").write_text(
                json.dumps({**fields, "id": ident, "schema": 1}, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")

        def a_file(path: Path, **fields) -> None:
            record(file_id(path), kind="file", root=str(path.parent), home=path.name, namespace=str(path.parent),
                   name=path.name, **fields)

        a_file(opened, created=1_700_000_000.0, opened=1_700_000_500.0, pinned=True,
               preview={"thumbnail": "0" * 32 + ".png", "pictured": 1_700_000_501.0})
        a_file(gone, created=1_700_000_000.0, opened=1_700_000_100.0)
        record(model, kind="model", root=str(self.work), home="parts.py", entry="arm", namespace=str(self.work),
               name="arm", revision="ab" * 32, fingerprint="cd" * 32, module="parts", built=1_700_000_200.0,
               created=1_700_000_200.0, facts={"parts": 1}, opened=1_700_000_300.0, pinned=True,
               cache={"file": "document.xbf", "format": 4})
        (self.state / "documents" / "not-a-record").mkdir()
        thumbnails = self.state / "recents" / "thumbnails"
        thumbnails.mkdir(parents=True)
        (thumbnails / ("0" * 32 + ".png")).write_bytes(PNG)
        kept = self.cache / "documents" / model
        (kept / "checks").mkdir(parents=True)
        (kept / "document.xbf").write_bytes(b"the cache's copy")
        (kept / "checks" / "result.json").write_text("{}", encoding="utf-8")

        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            found = self.library.read()
        self.assertEqual(found, {"schema": 1, "projects": {}, "files": {file_id(opened): {
            "path": str(opened), "created": 1_700_000_000.0, "opened": 1_700_000_500.0, "pinned": True}}})
        self.assertEqual(self.on_disk(), found)
        self.assertEqual((self.library.carried["files"], self.library.carried["projects"],
                          sorted(self.library.carried["skipped"])),
                         (1, 0, sorted([file_id(gone), model, "not-a-record"])),
                         "a file that is gone, and a model, whose record names no file, are not carried")
        self.assertIn("library: carried 1 files and 0 projects from the records of an earlier release; 3 not carried",
                      said.getvalue())
        self.assertEqual(sorted(os.listdir(self.state)), ["library.json"], "the records and the pictures are removed")
        self.assertEqual(sorted(os.listdir(kept)), ["checks"], "the cache's copy is removed, its kept checks stay")
        # A second read, as another process's first, finds the library and writes nothing.
        written = (self.state / "library.json").stat().st_mtime_ns
        again = Library(self.state, self.cache)
        with mock.patch.object(library_module, "_LOOKED", set()), mock.patch.object(library_module, "_READ", {}):
            self.assertEqual((again.read(), again.carried), (found, None))
        self.assertEqual((self.state / "library.json").stat().st_mtime_ns, written)


if __name__ == "__main__":
    unittest.main()
