"""First-party namespace cleanup remains usable after parent eviction."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import source_hash  # noqa: E402


class NamespaceEvictionTests(unittest.TestCase):
    def test_owned_child_is_removed_after_foreign_namespace_parent(self) -> None:
        parent_name = "cadgen_test_split_namespace"
        child_name = f"{parent_name}.owned"
        with tempfile.TemporaryDirectory(prefix="cadgen-namespace-eviction-") as raw:
            root = Path(raw)
            owned = root / "owned"
            foreign = root / "foreign"
            (owned / parent_name / "owned").mkdir(parents=True)
            (foreign / parent_name).mkdir(parents=True)
            sys.path[:0] = [str(owned), str(foreign)]
            self.addCleanup(lambda: sys.path.remove(str(owned)) if str(owned) in sys.path else None)
            self.addCleanup(lambda: sys.path.remove(str(foreign)) if str(foreign) in sys.path else None)
            self.addCleanup(sys.modules.pop, child_name, None)
            self.addCleanup(sys.modules.pop, parent_name, None)

            importlib.invalidate_caches()
            importlib.import_module(child_name)

            # The parent spans this model and another import root, while the
            # child is wholly owned. The foreign pass therefore removes only
            # the parent and leaves a temporarily orphaned child behind.
            with mock.patch.object(
                source_hash, "_first_party_namespace_packages", return_value={parent_name, child_name}
            ), mock.patch.object(
                source_hash, "repo_local_loaded_modules", return_value={}
            ), mock.patch.object(
                source_hash, "_packages_owning_loaded_extensions", return_value=frozenset()
            ):
                evicted = source_hash.evict_foreign_first_party_modules([owned])

            self.assertIn(parent_name, evicted)
            self.assertNotIn(parent_name, sys.modules)
            self.assertIn(child_name, sys.modules)

            # Recalculation now asks for the absent parent. The hygiene scan
            # must classify the child from its last exact path, then the next
            # blanket pass can remove it rather than crashing with KeyError.
            importlib.invalidate_caches()
            self.assertIn(child_name, source_hash._first_party_namespace_packages())
            with mock.patch.object(
                source_hash, "_first_party_namespace_packages", return_value={child_name}
            ), mock.patch.object(
                source_hash, "repo_local_loaded_modules", return_value={}
            ), mock.patch.object(
                source_hash, "_packages_owning_loaded_extensions", return_value=frozenset()
            ):
                evicted = source_hash.evict_first_party_modules()

            self.assertIn(child_name, evicted)
            self.assertNotIn(child_name, sys.modules)


if __name__ == "__main__":
    unittest.main()
