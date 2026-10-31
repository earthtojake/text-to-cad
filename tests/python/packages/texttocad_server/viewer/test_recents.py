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

from cad.engine.ids import model_id
from cad_server.engine.registry import Registry
from cad_server.viewer.recents import RecentStore


class RecentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_pins_lead_then_the_most_recent_and_a_removal_forgets(self) -> None:
        store = RecentStore(self.tmp)
        a, b, c = (str(self.tmp / name) for name in ("a.step", "b.step", "c.step"))  # absolute on every platform
        for path in (a, b, c):
            store.opened(path)
        store.pin(a, True)
        store.remove(b)
        store.thumbnail(c, b"\x89PNG fake")
        entries = store.list()
        self.assertEqual([(entry.path, entry.pinned) for entry in entries], [(a, True), (c, False)])
        self.assertEqual(store.read_thumbnail(entries[1].thumbnail), b"\x89PNG fake")
        self.assertIsNone(store.read_thumbnail("../escape.png"))
        # A picture says when it was taken: a file changed since has an old one.
        self.assertIsNotNone(entries[1].pictured)
        self.assertIsNone(entries[0].public()["pictured"])
        self.assertEqual(len(Registry(self.tmp).list()), 2, "one record per file; the removed one's folder went")
        self.assertEqual(set(Registry(self.tmp).list()[0]) - {"pinned", "preview"},
                         {"schema", "id", "kind", "root", "home", "opened", "created", "namespace", "name"}, "its path, and when it was opened, first and last")

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

    def test_a_file_is_updated_when_it_last_changed_on_disk_and_a_gone_one_says_nothing(self) -> None:
        store = RecentStore(self.tmp / "state")
        model = self.tmp / "part.stl"
        model.write_bytes(b"solid t\nendsolid t\n")
        os.utime(model, (1_700_000_000, 1_700_000_000))
        store.opened(str(model))
        store.opened(str(self.tmp / "gone.stl"))
        shown = {entry["name"]: entry for entry in (recent.public() for recent in store.list())}
        self.assertEqual((shown["part.stl"]["updated"], shown["part.stl"]["missing"]), (1_700_000_000, False))
        self.assertEqual((shown["gone.stl"]["updated"], shown["gone.stl"]["missing"]), (None, True))
        self.assertGreater(shown["part.stl"]["opened"], 1_700_000_000, "opened is the page's, now")
        self.assertNotIn("modified", shown["part.stl"])

    def test_a_model_is_updated_by_its_run_never_its_scripts_time_and_says_when_a_page_opened_it(self) -> None:
        from unittest import mock

        from cad_server.viewer import recents

        script = self.tmp / "parts.py"
        script.write_text("", encoding="utf-8")
        os.utime(script, (1_800_000_000, 1_800_000_000))  # edited after the run: no row says so
        ident, built = model_id(script, "plate"), 1_700_000_000.0
        Registry(self.tmp).put({"id": ident, "kind": "model", "root": str(self.tmp), "home": "parts.py",
                                "entry": "plate", "revision": "r1", "built": built})
        store = RecentStore(self.tmp)
        timed = []
        with mock.patch.object(recents, "_mtime", side_effect=lambda path: timed.append(path)):
            [entry] = [recent.public() for recent in store.list()]
        self.assertEqual(timed, [], "a model's script's time is never read")
        self.assertEqual((entry["updated"], entry["opened"], entry["missing"]), (built, None, False))
        self.assertIsNone(entry["created"], "a record from before the engine kept it says no creation time")
        store.opened(ident)  # a page opened it: its record says when, and its run's time stays
        [entry] = [recent.public() for recent in store.list()]
        self.assertEqual(entry["updated"], built)
        self.assertGreater(entry["opened"], built)
        self.assertEqual(Registry(self.tmp).get(ident)["built"], built)
        self.assertIsNone(entry["created"], "an opening makes no creation time up")

    def test_a_file_is_created_at_its_first_open_and_a_model_at_its_first_run(self) -> None:
        store = RecentStore(self.tmp)
        path = str(self.tmp / "part.step")
        store.opened(path)
        [first] = [recent.public() for recent in store.list()]
        self.assertEqual(first["created"], first["opened"], "a file's record is made as a page first opens it")
        time.sleep(0.01)
        store.opened(path)
        [again] = [recent.public() for recent in store.list()]
        self.assertEqual(again["created"], first["created"], "a second open keeps the first")
        self.assertGreater(again["opened"], first["opened"])
        # A model's run writes its record with the time it was first built (``Models.record``).
        ident = model_id(self.tmp / "parts.py", "plate")
        Registry(self.tmp).put({"id": ident, "kind": "model", "root": str(self.tmp), "home": "parts.py",
                                "entry": "plate", "revision": "r2", "built": 1_700_000_100.0, "created": 1_700_000_000.0})
        by_path = {recent.path: recent.public() for recent in store.list()}
        self.assertEqual((by_path[ident]["created"], by_path[ident]["updated"]), (1_700_000_000.0, 1_700_000_100.0))

    def test_rows_are_ordered_by_last_activity_after_the_pinned(self) -> None:
        store = RecentStore(self.tmp / "state")
        old, new, pinned = (self.tmp / name for name in ("old.stl", "new.stl", "pinned.stl"))
        for path in (old, new, pinned):
            path.write_bytes(b"solid t\nendsolid t\n")
            store.opened(str(path))
        store.pin(str(pinned), True)
        # Opened in that order, but old.stl written since: its last activity is the latest.
        future = time.time() + 3600
        os.utime(old, (future, future))
        self.assertEqual([os.path.basename(entry.path) for entry in store.list()], ["pinned.stl", "old.stl", "new.stl"])

    def test_a_built_model_is_listed_by_its_id_and_one_whose_script_went_is_missing_until_removed(self) -> None:
        script = self.tmp / "parts.py"
        script.write_text("", encoding="utf-8")
        ident = model_id(script, "plate")
        Registry(self.tmp).put({"id": ident, "kind": "model", "root": str(self.tmp),
                                "home": "parts.py", "entry": "plate", "revision": "r1",
                                "built": time.time()})
        store = RecentStore(self.tmp)
        [entry] = [recent.public() for recent in store.list()]
        self.assertEqual((entry["path"], entry["id"], entry["kind"], entry["name"], entry["missing"]),
                         (ident, ident, "model", "plate", False))
        self.assertEqual(entry["rebuild"], f"cadgen run {self.tmp / 'parts.py'}")
        script.unlink()  # moved away: detached, still listed, and says so
        self.assertTrue(store.list()[0].public()["missing"])
        store.remove(ident)
        self.assertEqual((store.list(), Registry(self.tmp).get(ident)), ([], None))

    def test_a_shape_handed_over_from_a_folder_is_present_and_says_what_it_is(self) -> None:
        from cad.engine.ids import derived_id

        ident, built = derived_id(self.tmp, "plate"), time.time() - 60
        Registry(self.tmp).put({"id": ident, "kind": "shape", "root": str(self.tmp), "home": ".",
                                "entry": "plate", "revision": "h1", "built": built})
        [entry] = [recent.public() for recent in RecentStore(self.tmp).list()]
        self.assertEqual((entry["id"], entry["missing"], entry["rebuild"], entry["kind"], entry["updated"], entry["folder"]),
                         (ident, False, None, "shape", built, str(self.tmp)), "a folder home is where it came from, not a lost file")
        self.assertIn("a shape handed over", entry["shown"])
        self.assertIn("no script to rerun", entry["shown"])

    def test_two_processes_write_at_once_and_a_record_it_cannot_read_is_skipped(self) -> None:
        code = "import sys\nfrom cad_server.viewer.recents import RecentStore\nstore = RecentStore(__import__('pathlib').Path(sys.argv[1]))\n" \
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
