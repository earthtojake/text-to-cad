"""Artifact and geometry/surface indexes retain independent GC closures."""
from __future__ import annotations
import os
from pathlib import Path
import unittest
from unittest import mock
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
add_repo_path("packages/cadgen/src")

class ComponentGcReachability(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="store-gc-component-")
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name) / "store"
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        patch.start(); self.addCleanup(patch.stop)

    def seed(self):
        from tests.python.support.store_fixtures import seed_result
        path = Path(self.tmp.name) / "part.step"
        path.write_bytes(b"fixture document")
        return seed_result(path)

    def test_geometry_index_and_surface_index_own_separate_objects(self):
        from cadgen.store.gc import collect
        from cadgen.store.index import write_entry, remove_entry
        from cadgen.store.objects import has_object, put_object
        from cadgen.store.trees import get_tree
        import hashlib
        tree = self.seed()
        entry = next(iter(get_tree(tree)["components"].values()))
        cid = entry["contentHash"][:16]
        write_entry("component", cid, {"schemaVersion": 1, **entry})
        remove_entry("document", hashlib.sha256(b"fixture document").hexdigest())
        remove_entry("model", next((self.store / "index/model").iterdir()).name)
        orphan = put_object(b"unreferenced")
        report = collect(grace_seconds=0)
        self.assertEqual(report.reachable, 2)
        self.assertTrue(has_object(entry["brep"]))
        self.assertFalse(has_object(tree))
        self.assertFalse(has_object(orphan))

    def test_document_only_root_retains_linked_geometry_not_external_mesh_hash(self):
        from cadgen.store.gc import collect
        from cadgen.store.index import iter_entries, remove_entry
        from cadgen.store.objects import has_object, put_object
        from cadgen.store.records import note_document_tree, note_document_mesh
        from cadgen.store.trees import put_tree, tree_complete, IDENTITY_16
        child = self.seed()
        parent = put_tree({"label":"parent","units":"mm","entryKind":"assembly","components":{},"occurrences":[],
            "links":[{"id":"o1.1","name":"child","tree":child,"transform":IDENTITY_16}],
            "assembly":{"root":{"id":"o1","nodeType":"assembly","children":[{"id":"o1.1","nodeType":"link","children":[]}]}}})
        for kind in ("document", "model", "surface"):
            for key, _ in list(iter_entries(kind)): remove_entry(kind, key)
        external = put_object(b"external exported mesh")
        note_document_tree("d" * 64, parent)
        note_document_mesh("d" * 64, "stl:variant", external)
        report = collect(grace_seconds=0)
        self.assertEqual(report.records, 0)
        self.assertEqual(report.reachable, 3)
        self.assertTrue(tree_complete(parent))
        self.assertFalse(has_object(external))
        remove_entry("document", "d" * 64)
        self.assertEqual(collect(grace_seconds=0).removed, 3)

    def test_obsolete_document_index_does_not_retain_tree(self):
        from cadgen.store.gc import collect
        from cadgen.store.index import iter_entries, remove_entry, write_entry
        from cadgen.store.objects import has_object
        from cadgen.store.records import DOCUMENT_SCHEMA_VERSION
        tree = self.seed()
        for kind in ("document", "model", "surface"):
            for key, _ in list(iter_entries(kind)): remove_entry(kind, key)
        write_entry("document", "a" * 64, {"schemaVersion": DOCUMENT_SCHEMA_VERSION - 1, "tree": tree})
        self.assertEqual(collect(grace_seconds=0).reachable, 0)
        self.assertFalse(has_object(tree))

if __name__ == "__main__": unittest.main()
