"""Recents: the registry's view, shared by concurrent processes, tolerant of records it cannot read."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from cadgen.engine.ids import model_id
from cadgen.engine.registry import Registry
from cadgen.viewer.recents import RecentStore


class RecentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
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
        # A picture says when it was taken: a file changed since has an old one.
        self.assertIsNotNone(entries[1].pictured)
        self.assertIsNone(entries[0].public()["pictured"])
        self.assertEqual(len(Registry(self.tmp).list()), 2, "one record per file; the removed one's folder went")

    def test_a_picture_no_record_shows_goes_once_no_writer_can_still_name_it(self) -> None:
        # Each rebuilt revision a view pictures adds a PNG; replaced ones must not pile up.
        store = RecentStore(self.tmp)
        store.opened("/a.step")
        first = store.thumbnail("/a.step", b"\x89PNG one")
        second = store.thumbnail("/a.step", b"\x89PNG two")
        # Replaced, but too fresh to tell from a picture whose record is still on its way.
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

    def test_a_built_model_is_listed_by_its_id_and_one_whose_script_went_is_missing_until_removed(self) -> None:
        script = self.tmp / "parts.py"
        script.write_text("", encoding="utf-8")
        ident = model_id(script, "plate")
        Registry(self.tmp).put({"id": ident, "kind": "model", "store": "pointer", "root": str(self.tmp),
                                "home": "parts.py", "entry": "plate", "label": "plate", "run": ["python", "caller.py"],
                                "built": time.time()})
        store = RecentStore(self.tmp)
        [entry] = [recent.public() for recent in store.list()]
        self.assertEqual((entry["path"], entry["id"], entry["kind"], entry["name"], entry["missing"]),
                         (ident, ident, "model", "plate", False))
        self.assertEqual(entry["rebuild"], f"python {self.tmp / 'caller.py'}")
        script.unlink()  # moved away: detached, still listed, and says so
        self.assertTrue(store.list()[0].public()["missing"])
        store.remove(ident)
        self.assertEqual((store.list(), Registry(self.tmp).get(ident)), ([], None))

    def test_a_shape_handed_over_from_a_folder_is_present_and_says_what_it_is(self) -> None:
        from cadgen.engine.ids import derived_id

        ident, built = derived_id(self.tmp, "plate"), time.time() - 60
        Registry(self.tmp).put({"id": ident, "kind": "model", "store": "shape", "root": str(self.tmp), "home": ".",
                                "entry": "plate", "label": "plate", "run": [], "built": built,
                                "shown": "a shape handed over from a Python session the engine did not run: no script "
                                         "to rerun, and no command builds it again"})
        [entry] = [recent.public() for recent in RecentStore(self.tmp).list()]
        self.assertEqual((entry["id"], entry["missing"], entry["rebuild"], entry["store"], entry["modified"]),
                         (ident, False, None, "shape", built), "a folder home is where it came from, not a lost file")
        self.assertIn("a shape handed over", entry["shown"])
        self.assertIn("no script to rerun", entry["shown"])

    def test_two_processes_write_at_once_and_a_record_it_cannot_read_is_skipped(self) -> None:
        code = "import sys\nfrom cadgen.viewer.recents import RecentStore\nstore = RecentStore(__import__('pathlib').Path(sys.argv[1]))\n" \
               "for index in range(120):\n    store.opened(f'/{sys.argv[2]}/{index}.stl')\n"
        writers = [subprocess.Popen([sys.executable, "-c", code, str(self.tmp), name], env={**os.environ}) for name in ("x", "y")]
        for writer in writers:
            self.assertEqual(writer.wait(120), 0)
        documents = self.tmp / "documents"
        # A record of another schema, a torn one, and a folder that is no id: none of them is read.
        for name, text in (("00000000-0000-4000-8000-000000000001", json.dumps({"schema": 99})),
                           ("00000000-0000-4000-8000-000000000002", '{"schema": 1, "id": "00000000'), ("notes", "{}")):
            (documents / name).mkdir()
            (documents / name / "document.json").write_text(text, encoding="utf-8")
        entries = RecentStore(self.tmp).list()
        self.assertEqual(len({entry.path for entry in entries}), 200, "the newest 200 of the 240")
        self.assertEqual({entry.thumbnail for entry in entries}, {None})


if __name__ == "__main__":
    unittest.main()
