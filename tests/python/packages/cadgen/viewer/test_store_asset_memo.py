"""The component route resolves a tree's cid -> object map ONCE per tree.

A tree is a content-addressed, immutable object, and the viewer serves one
component request per component of an assembly: re-flattening a 600-occurrence
tree on each of 485 requests cost ~11 ms of CPU apiece (5.6 s per load of a
483-component model). The memo is keyed by store root too, because the root is
read from the environment per call and a suite may move it.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.store import view
from cadgen.viewer import store_paths

from tests.python.support.store_fixtures import seed_result


class ComponentResolutionIsMemoised(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previous = os.environ.get("CADGEN_CACHE_DIR")
        self.addCleanup(
            lambda: os.environ.__setitem__("CADGEN_CACHE_DIR", previous)
            if previous is not None
            else os.environ.pop("CADGEN_CACHE_DIR", None)
        )
        self.addCleanup(view._component_objects_memo.clear)
        view._component_objects_memo.clear()

    def _store(self, name: str) -> str:
        root = os.path.join(self.tmp.name, name)
        os.environ["CADGEN_CACHE_DIR"] = root
        return root

    def test_one_flatten_per_tree_and_store(self) -> None:
        self._store("cache-a")
        document = Path(self.tmp.name, "part.step")
        document.write_text("body\n", encoding="utf-8")
        tree = seed_result(document, components=("c0", "c1"))

        with mock.patch.object(view, "flatten", wraps=view.flatten) as flatten:
            first = store_paths.virtual_store_asset(f"{tree}/components/c0.surf")
            second = store_paths.virtual_store_asset(f"{tree}/components/c1.surf")
            third = store_paths.virtual_store_asset(f"/{tree}/components/c0.surf")
            self.assertEqual(flatten.call_count, 1, "every component request re-flattened the tree")
        self.assertIsInstance(first[0], Path)
        self.assertEqual(first, third)
        self.assertEqual(second[1], "application/octet-stream")
        # Unknown cid: resolved through the memo, still a miss.
        self.assertEqual(store_paths.virtual_store_asset(f"{tree}/components/nope.surf"), (None, ""))

    def test_a_missing_tree_is_not_remembered(self) -> None:
        self._store("cache-b")
        document = Path(self.tmp.name, "late.step")
        document.write_text("body\n", encoding="utf-8")
        absent = "0" * 64
        self.assertEqual(store_paths.virtual_store_asset(f"{absent}/components/c0.surf"), (None, ""))
        self.assertEqual(view._component_objects_memo, {})
        # The tree appears (a compile finished): the next request finds it.
        tree = seed_result(document)
        self.assertIsInstance(store_paths.virtual_store_asset(f"{tree}/components/c0.surf")[0], Path)

    def test_the_memo_is_per_store_root(self) -> None:
        self._store("cache-c")
        document = Path(self.tmp.name, "moved.step")
        document.write_text("body\n", encoding="utf-8")
        tree = seed_result(document)
        self.assertIsInstance(store_paths.virtual_store_asset(f"{tree}/components/c0.surf")[0], Path)
        # The same tree hash in a store that does not hold it: a miss, not the
        # other store's answer.
        self._store("cache-d")
        self.assertEqual(store_paths.virtual_store_asset(f"{tree}/components/c0.surf"), (None, ""))


if __name__ == "__main__":
    unittest.main()
