"""Geometry routes resolve pinned BREP; disposable SURF needs a runtime view."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import unittest
from unittest import mock
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.store_fixtures import seed_result, FIXTURE_SURFACE_PRODUCER
add_repo_path("packages/cadgen/src")

class ComponentLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="store-view-component-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        patch.start(); self.addCleanup(patch.stop)
        path = self.root / "part.step"; path.write_bytes(b"fixture")
        self.tree = seed_result(path)
        from cadgen.store.trees import get_tree
        self.body = get_tree(self.tree)
        self.cid, self.entry = next(iter(self.body["components"].items()))

    def parent(self, children):
        from cadgen.store.trees import put_tree, IDENTITY_16
        links = [{"id": f"o1.{i}", "name": "child", "tree": child, "transform": IDENTITY_16}
                 for i, child in enumerate(children, 1)]
        return put_tree({"label":"parent","units":"mm","entryKind":"assembly","components":{},"occurrences":[],"links":links,
            "assembly":{"root":{"id":"o1","nodeType":"assembly","children":[
                {"id":link["id"],"nodeType":"link","children":[]} for link in links]}}})

    def test_root_lookup_does_not_resolve_surfaces_or_read_source_indexes(self):
        from cadgen.store import records, view
        with mock.patch.object(view, "descriptor_for_view", side_effect=AssertionError("flattened")), \
             mock.patch.object(records, "read_record", side_effect=AssertionError("record")), \
             mock.patch.object(records, "model_for_output", side_effect=AssertionError("output")):
            actual = view.component_object_for_tree(self.tree, self.cid + ".brep")
        self.assertEqual(actual, (self.entry["brep"], "brep"))
        self.assertIsNone(view.component_object_for_tree(self.tree, self.cid + ".surf"))

    def test_repeated_links_use_one_exact_brep(self):
        from cadgen.store import view
        with mock.patch.object(view, "descriptor_for_view", side_effect=AssertionError("composed")):
            self.assertEqual(view.component_object_for_tree(self.parent([self.tree, self.tree]), self.cid + ".brep"),
                             (self.entry["brep"], "brep"))

    def test_conflicting_duplicate_cid_is_rejected(self):
        from cadgen.store import view
        from cadgen.store.objects import put_object
        from cadgen.store.trees import put_tree
        corrupted = copy.deepcopy(self.body)
        corrupted["components"][self.cid]["brep"] = put_object(b"wrong")
        parent = self.parent([self.tree, put_tree(corrupted)])
        self.assertIsNone(view.component_object_for_tree(parent, self.cid + ".brep"))

    def test_full_hash_spelling_is_confined_to_named_tree(self):
        from cadgen.store import view
        from cadgen.store.objects import put_object
        digest = self.entry["brep"]
        self.assertEqual(view.component_object_for_tree(self.tree, digest + ".brep"), (digest, "brep"))
        self.assertIsNone(view.component_object_for_tree(self.tree, put_object(b"outside") + ".brep"))

    def test_missing_root_link_or_target_fails_lookup(self):
        from cadgen.store import view
        from cadgen.store.objects import object_path
        parent = self.parent([self.tree])
        payload = object_path(self.tree).read_bytes(); object_path(self.tree).unlink()
        self.assertIsNone(view.component_object_for_tree(parent, self.cid + ".brep"))
        object_path(self.tree).write_bytes(payload)
        object_path(self.entry["brep"]).unlink()
        self.assertIsNone(view.component_object_for_tree(parent, self.cid + ".brep"))

    def test_malformed_link_rejected(self):
        from cadgen.store import view
        from cadgen.store.objects import put_object
        broken = copy.deepcopy(self.body)
        broken["links"] = [{"tree": "not-an-object-hash"}]
        tree = put_object(json.dumps(broken).encode())
        self.assertIsNone(view.component_object_for_tree(tree, self.cid + ".brep"))

    def test_hash_corrupt_brep_is_never_returned(self):
        from cadgen.store import view
        from cadgen.store.objects import object_path
        digest = self.entry["brep"]
        object_path(digest).write_bytes(b"corrupt native payload")
        self.assertIsNone(view.component_object_for_tree(self.tree, self.cid + ".brep"))
        self.assertIsNone(view.component_object_for_tree(self.tree, digest + ".brep"))

    def test_lookup_uses_current_store_environment(self):
        from cadgen.store import view
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "other")
        self.assertIsNone(view.component_object_for_tree(self.tree, self.cid + ".brep"))

    def test_runtime_descriptor_carries_surface_input_without_resolving_surface(self):
        from cadgen.store import view, surfaces
        with mock.patch.object(surfaces, "producer_identity", side_effect=AssertionError("native import")):
            descriptor = view.descriptor_for_view(self.tree, producer=FIXTURE_SURFACE_PRODUCER)
        self.assertEqual(descriptor["kind"], "assembly-package")
        entry = descriptor["components"][self.cid]
        self.assertEqual(entry["brepObject"], self.entry["brep"])
        self.assertEqual(len(entry["surfaceInput"]), 64)
        self.assertNotIn("surfaceObject", entry)

if __name__ == "__main__": unittest.main()
