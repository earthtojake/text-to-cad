"""Recents: the library's files that are there now, each a row read from its entry, one ``stat`` and the cache's
note of the file as it is."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from cad.engine.ids import file_id
from cad_server.engine.library import Library, Notes
from cad_server.viewer.projects import Projects
from cad_server.viewer.recents import listing

STL = b"solid t\nendsolid t\n"


class RecentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.library = Library(self.tmp / "state", self.tmp / "cache")
        self.notes = Notes(self.tmp / "cache")
        self.projects = Projects(self.library)

    def file(self, name: str, data: bytes = STL) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def rows(self) -> dict[str, dict]:
        return {row["name"]: row for row in listing(self.library, self.notes, self.projects)}

    def test_pins_lead_then_the_latest_activity_and_a_file_that_is_gone_is_not_listed(self) -> None:
        old, new, pinned, gone = (self.file(name) for name in ("old.stl", "new.stl", "pinned.stl", "gone.stl"))
        for path in (old, new, pinned, gone):
            self.library.opened(path)
        self.library.pin(pinned, True)
        gone.unlink()
        # Opened in that order, but old.stl written since: its last activity is the latest.
        future = time.time() + 3600
        os.utime(old, (future, future))
        self.assertEqual(list(self.rows()), ["pinned.stl", "old.stl", "new.stl"])
        self.file("gone.stl")
        self.assertIn("gone.stl", self.rows(), "back with its file")

    def test_a_row_is_its_file_as_it_is_on_disk_with_its_entry(self) -> None:
        part = self.file("part.stl")
        os.utime(part, (1_700_000_000, 1_700_000_000))
        self.library.opened(part)
        arm = self.file("arm.xbf", b"not read here")
        self.library.know(arm)  # a run wrote it: listed, never opened
        self.library.opened(self.file("notes.xyz"))  # a file no page reads is listed nowhere
        rows = self.rows()
        self.assertEqual(set(rows), {"part.stl", "arm.xbf"})
        row = rows["part.stl"]
        self.assertEqual(set(row), {"id", "kind", "record", "api", "path", "name", "folder", "namespace", "opened",
                                    "updated", "created", "pinned", "missing", "thumbnail", "pictured", "size", "parts",
                                    "project"})
        self.assertEqual((row["id"], row["kind"], row["record"], row["path"], row["folder"], row["namespace"]),
                         (file_id(part), "stl", "file", str(part), str(self.tmp), str(self.tmp)))
        self.assertEqual((row["updated"], row["size"], row["missing"], row["pinned"], row["project"]),
                         (1_700_000_000, len(STL), False, False, None))
        self.assertEqual(row["created"], row["opened"], "made as a page first opened it")
        model = rows["arm.xbf"]
        self.assertEqual((model["kind"], model["record"], model["api"], model["opened"]),
                         ("model", "file", f"/api/v1/documents/model/{file_id(arm)}", None))
        part.write_bytes(STL + b"\n")  # written again: the next read has its new size
        self.assertEqual(self.rows()["part.stl"]["size"], len(STL) + 1)

    def test_a_row_says_its_parts_and_its_picture_while_the_note_is_of_the_file_as_it_is(self) -> None:
        kit = self.file("kit.xbf", b"not read here")
        self.library.opened(kit)
        self.assertEqual([self.rows()["kit.xbf"][key] for key in ("parts", "thumbnail", "pictured")], [None, None, None])
        self.notes.count(kit, 3)
        self.notes.picture(kit, b"\x89PNG kit")
        row = self.rows()["kit.xbf"]
        self.assertEqual((row["parts"], row["thumbnail"]), (3, str(round(row["pictured"] * 1000))))
        later = time.time_ns() + 5_000_000_000
        os.utime(kit, ns=(later, later))
        self.assertEqual([self.rows()["kit.xbf"][key] for key in ("parts", "thumbnail", "pictured")], [None, None, None],
                         "written since: the note is of another version")


if __name__ == "__main__":
    unittest.main()
