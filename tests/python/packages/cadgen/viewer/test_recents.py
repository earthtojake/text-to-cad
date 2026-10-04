"""The recents store: shared by concurrent processes, tolerant of other versions' lines."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from cadgen.viewer.recents import RecentStore


class RecentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_pins_lead_then_the_most_recent_and_a_removal_forgets(self) -> None:
        store = RecentStore(self.tmp)
        for path in ("/a.step", "/b.step", "/c.step"):
            store.opened(path)
        store.pin("/a.step", True)
        store.remove("/b.step")
        store.thumbnail("/c.step", b"\x89PNG fake")
        entries = store.list()
        self.assertEqual([(entry.path, entry.pinned) for entry in entries], [("/a.step", True), ("/c.step", False)])
        self.assertEqual(store.read_thumbnail(entries[1].thumbnail), b"\x89PNG fake")
        self.assertIsNone(store.read_thumbnail("../escape.png"))
        # A picture says when it was taken, as compacting the log keeps it: a file changed since has an old one.
        pictured = entries[1].pictured
        self.assertIsNotNone(pictured)
        self.assertIsNone(entries[0].public()["pictured"])
        with unittest.mock.patch("cadgen.viewer.recents.COMPACT_AFTER", 0):
            store.opened("/d.step")
        self.assertEqual(next(entry for entry in store.list() if entry.path == "/c.step").pictured, pictured)

    def test_a_picture_no_listed_model_shows_goes_once_no_writer_can_still_name_it(self) -> None:
        # Each rebuilt revision a view pictures adds a PNG; replaced ones must not pile up.
        store = RecentStore(self.tmp)
        store.opened("/a.step")
        first = store.thumbnail("/a.step", b"\x89PNG one")
        second = store.thumbnail("/a.step", b"\x89PNG two")
        # Replaced, but too fresh to tell from a picture whose event is still on its way.
        self.assertTrue((store.thumbnails / first).exists())
        old = time.time() - 3600
        for name in (first, second):
            os.utime(store.thumbnails / name, (old, old))
        third = store.thumbnail("/a.step", b"\x89PNG three")
        self.assertEqual([path.name for path in store.thumbnails.iterdir()], [third])

    def test_a_model_says_when_its_file_last_changed_and_a_gone_one_says_nothing(self) -> None:
        store = RecentStore(self.tmp / "state")
        model = self.tmp / "part.stl"
        model.write_bytes(b"solid t\nendsolid t\n")
        os.utime(model, (1_700_000_000, 1_700_000_000))
        store.opened(str(model))
        store.opened(str(self.tmp / "gone.stl"))
        shown = {entry["name"]: entry for entry in (recent.public() for recent in store.list())}
        self.assertEqual((shown["part.stl"]["modified"], shown["part.stl"]["missing"]), (1_700_000_000, False))
        self.assertEqual((shown["gone.stl"]["modified"], shown["gone.stl"]["missing"]), (None, True))

    def test_two_processes_append_at_once_and_foreign_lines_are_skipped(self) -> None:
        code = "import sys\nfrom cadgen.viewer.recents import RecentStore\nstore = RecentStore(__import__('pathlib').Path(sys.argv[1]))\n" \
               "for index in range(200):\n    store.opened(f'/{sys.argv[2]}/{index}.stl')\n"
        writers = [subprocess.Popen([sys.executable, "-c", code, str(self.tmp), name], env={**os.environ}) for name in ("x", "y")]
        for writer in writers:
            self.assertEqual(writer.wait(120), 0)
        log = self.tmp / "recents" / "recents.jsonl"
        with open(log, "a", encoding="utf-8") as handle:
            # A version from the future, an op nobody knows, a torn line, and a screenshot of a view from before
            # a model's picture was its own (`thumb`): none of them is read.
            handle.write('{"v":99,"op":"open","path":"/future.stl"}\n{"v":1,"op":"rename","path":"/x/0.stl"}\nnot json\n'
                         '{"v":1,"op":"thumb","path":"/x/0.stl","thumbnail":"old.png"}\n')
        entries = RecentStore(self.tmp).list()
        paths = {entry.path for entry in entries}
        self.assertEqual(len(paths), 200)  # the store keeps the newest 200 of the 400
        self.assertNotIn("/future.stl", paths)
        self.assertEqual({entry.thumbnail for entry in entries}, {None})


if __name__ == "__main__":
    unittest.main()
