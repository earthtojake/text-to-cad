"""The explorer's reads: one folder at a time, and a bounded search under a folder."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.viewer import folders
from cadgen.viewer.folders import list_folder, search_folder


def slashed(path: Path) -> str:
    return str(path).replace(os.sep, "/")


class FoldersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for name in ("arm/link2.step", "arm/link10.step", "arm/notes.txt", "arm/.cache/x.step", "arm/node_modules/y.step",
                     "base.stl", "Parts/deep/er/bolt.step", ".hidden.step"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(b"x")

    def test_a_folder_lists_its_subfolders_then_its_cad_files_in_natural_order(self) -> None:
        listed = list_folder(str(self.root))
        self.assertEqual(listed["path"], slashed(self.root))
        self.assertEqual(listed["entries"], [{"name": "arm", "kind": "directory"}, {"name": "Parts", "kind": "directory"},
                                             {"name": "base.stl", "kind": "file"}])
        # Hidden and build folders, and files CAD does not open, are not listed.
        self.assertEqual([entry["name"] for entry in list_folder(str(self.root / "arm"))["entries"]], ["link2.step", "link10.step"])
        self.assertFalse(listed["truncated"])
        with mock.patch.object(folders, "LIST_LIMIT", 1):
            self.assertEqual(list_folder(str(self.root)), {"path": slashed(self.root), "entries": [{"name": "arm", "kind": "directory"}],
                                                          "truncated": True})

    def test_only_an_existing_absolute_folder_is_read(self) -> None:
        with self.assertRaises(ValueError):
            list_folder("arm")
        with self.assertRaises(FileNotFoundError):
            list_folder(str(self.root / "missing"))
        with self.assertRaises(FileNotFoundError):
            search_folder(str(self.root / "base.stl"), "x")

    def test_a_search_finds_nested_files_by_their_path_below_the_folder_shallowest_first(self) -> None:
        found = search_folder(str(self.root), "")
        self.assertEqual(found["results"], [slashed(self.root / name) for name in
                                            ("base.stl", "arm/link2.step", "arm/link10.step", "Parts/deep/er/bolt.step")])
        self.assertFalse(found["truncated"])
        # A folder's name finds what is under it; case does not matter.
        self.assertEqual(search_folder(str(self.root), "DEEP")["results"], [slashed(self.root / "Parts/deep/er/bolt.step")])
        self.assertEqual(search_folder(str(self.root / "arm"), "link1")["results"], [slashed(self.root / "arm/link10.step")])

    def test_a_search_stops_early_at_its_limits_and_says_so(self) -> None:
        self.assertEqual(search_folder(str(self.root), "", limit=2), {"path": slashed(self.root), "results": [
            slashed(self.root / "base.stl"), slashed(self.root / "arm/link2.step")], "truncated": True})
        self.assertEqual(search_folder(str(self.root), "bolt", depth=1), {"path": slashed(self.root), "results": [], "truncated": True})
        ticks = iter(range(100))
        stopped = search_folder(str(self.root), "", seconds=1.5, clock=lambda: next(ticks))
        self.assertTrue(stopped["truncated"])
        self.assertLess(len(stopped["results"]), 4)

    @unittest.skipIf(os.name == "nt", "a symlink to a folder needs privileges on Windows")
    def test_a_link_back_into_a_walked_folder_is_not_walked_again(self) -> None:
        (self.root / "arm" / "loop").symlink_to(self.root, target_is_directory=True)
        found = search_folder(str(self.root), "link2")
        self.assertEqual(found["results"], [slashed(self.root / "arm/link2.step")])
        self.assertFalse(found["truncated"])


if __name__ == "__main__":
    unittest.main()
