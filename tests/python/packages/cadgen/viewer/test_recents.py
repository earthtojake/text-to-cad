"""The recents store: shared by concurrent processes, tolerant of other versions' lines."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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

    def test_two_processes_append_at_once_and_foreign_lines_are_skipped(self) -> None:
        code = "import sys\nfrom cadgen.viewer.recents import RecentStore\nstore = RecentStore(__import__('pathlib').Path(sys.argv[1]))\n" \
               "for index in range(200):\n    store.opened(f'/{sys.argv[2]}/{index}.stl')\n"
        writers = [subprocess.Popen([sys.executable, "-c", code, str(self.tmp), name], env={**os.environ}) for name in ("x", "y")]
        for writer in writers:
            self.assertEqual(writer.wait(120), 0)
        log = self.tmp / "recents" / "recents.jsonl"
        with open(log, "a", encoding="utf-8") as handle:
            handle.write('{"v":99,"op":"open","path":"/future.stl"}\n{"v":1,"op":"rename","path":"/x/0.stl"}\nnot json\n')
        paths = {entry.path for entry in RecentStore(self.tmp).list()}
        self.assertEqual(len(paths), 200)  # the store keeps the newest 200 of the 400
        self.assertNotIn("/future.stl", paths)


if __name__ == "__main__":
    unittest.main()
