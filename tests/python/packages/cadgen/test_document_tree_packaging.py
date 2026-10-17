"""Canonical STEP packaging is independent of authored trees and filenames, and a saved
file is the result it was written from where it holds it."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.documents import assert_same_document, save_step
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.tree_ids import node_ids, root_id


class DocumentTreePackagingTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="document-tree-packaging-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        workers = mock.patch("cadgen._internal.component_package._component_build_worker_count", return_value=1)
        workers.start()
        self.addCleanup(workers.stop)

    def box(self, name="box"):
        from build123d import Solid

        shape = Solid.make_box(2, 3, 4)
        shape.label = name
        shape.color = (.8, .7, .6, 1)
        return shape

    def assert_warm_and_cold_repackage(self, output, result):
        """The saved document is the build's ``result``: a scene read from it packages it
        again, and a parse of its bytes, here or as a copy under another name in an empty
        store, packages the same document, every component read from the file."""
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import flatten

        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        self.assertEqual(document_entry_for_hash(digest)["tree"], result)
        document = flatten(result)
        warm_scene = scene_from_render_package(output, step_hash=digest)
        self.assertIsNotNone(warm_scene)
        assert_same_document(self, document, build_document_tree(warm_scene)[1])
        raw_hash, raw_tree, _ = build_document_tree(load_step_scene(output))
        assert_same_document(self, document, raw_tree)
        copied = self.root / "different-filename.step"
        copied.write_bytes(output.read_bytes())
        # Force extraction in an empty store, not merely a hit of the generated
        # component index. The STEP bytes and intrinsic names are the inputs.
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "empty-store")}):
            cold_hash, cold_tree, _ = build_document_tree(load_step_scene(copied))
        self.assertEqual((cold_hash, cold_tree), (raw_hash, raw_tree))
        return raw_tree

    def test_single_part_root_wrapper_is_canonical_across_warm_cold_and_file_copies(self):
        shape = self.box("authored-part-name")
        finish = {"name": "Machined", "roughness": .2, "metalness": .7}
        materials = {
            "definitions": {"finish": finish},
            "assignments": [{"targets": ["#authored-part-name"], "material": "finish"}],
        }
        output = self.root / "original.step"
        # One part is its document, named by its label (generation._document_root_name).
        result, tree, stats, _ = save_step(shape, output, root_name="authored-part-name", materials=materials)
        self.assertEqual({"ok": True}, stats["verify"])
        self.assertEqual(tree["occurrences"][0]["name"], "authored-part-name")
        self.assertEqual(tree["appearance"]["materials"]["finish"], finish)
        self.assertEqual(tree["appearance"]["assignments"], {root_id(tree): "finish"})
        compiled = self.assert_warm_and_cold_repackage(output, result)
        # A finish travels in the sidecar, never in the file: a compile of the bytes has none.
        self.assertNotIn("appearance", compiled)
        self.assertTrue(all("material" not in occurrence for occurrence in compiled["occurrences"]))

    def test_nested_repeated_products_preserve_names_colors_and_world_placements_when_warm(self):
        from build123d import Compound, Location

        prototype = self.box()
        first = prototype.moved(Location((2, 0, 0)))
        first.label, first.color = "red", (1, 0, 0, 1)
        second = prototype.moved(Location((8, 0, 0)))
        second.label, second.color = "green", (0, 1, 0, 1)
        group = Compound(children=[first, second], label="pair").moved(Location((20, 5, 0), (0, 0, 30)))
        shape = Compound(children=[group], label="assembly-root")
        output = self.root / "nested.step"
        result, _, stats, _ = save_step(shape, output, root_name="assembly-root")
        self.assertEqual({"ok": True}, stats["verify"])
        compiled = self.assert_warm_and_cold_repackage(output, result)
        self.assertEqual([occurrence["name"] for occurrence in compiled["occurrences"]], ["red", "green"])

    def test_non_ascii_product_names_verify(self):
        from build123d import Compound

        shape = Compound(children=[self.box("圆角2_1_2")], label="主装配")
        output = self.root / "unicode-label.step"
        result, _, stats, _ = save_step(shape, output, root_name="主装配")
        self.assertEqual({"ok": True}, stats["verify"])
        compiled = self.assert_warm_and_cold_repackage(output, result)
        self.assertEqual(compiled["assembly"]["root"]["name"], "主装配")
        self.assertEqual(compiled["occurrences"][0]["name"], "圆角2_1_2")

    def test_a_fused_native_compound_with_no_wrapper_children_is_one_part(self):
        from build123d import Location, Solid

        # A fuse whose pieces do not all touch yields a Compound of solids with no
        # wrapper children: one part, the way build123d handed it back.
        fused = Solid.make_box(2, 3, 4).fuse(Solid.make_box(2, 3, 4).moved(Location((10, 0, 0))))
        fused.label = "frame:underbone"
        _, tree, stats, _ = save_step(fused, self.root / "fused.step", root_name="frame:underbone")
        self.assertEqual({"ok": True}, stats["verify"])
        self.assertEqual(tree["entryKind"], "part")
        self.assertEqual(tree["assembly"]["root"]["nodeType"], "part")
        self.assertEqual(len(tree["occurrences"]), 1)
        self.assertEqual(tree["occurrences"][0]["name"], "frame:underbone")

    def test_a_native_compound_product_keeps_its_product_boundary(self):
        from build123d import Compound, Location
        from cadgen._internal import component_package
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store.build import build_document_tree
        from cadgen.store.trees import IDENTITY_16

        shape = Compound(children=[self.box("one"), self.box("two").moved(Location((8, 0, 0)))])
        scene = LoadedStepScene(
            step_path=self.root / "unrelated-filename.step",
            roots=[OccurrenceNode(path=(1,), name="native-product", source_name="native-product",
                                  transform=tuple(IDENTITY_16), prototype_key=1)],
            prototype_shapes={1: shape.wrapped},
        )
        with mock.patch.object(component_package, "_bbox_from_shape",
                               wraps=component_package._bbox_from_shape) as fallback:
            _, tree, _ = build_document_tree(scene)
        fallback.assert_called_once()
        self.assertEqual(tree["label"], "native-product")
        self.assertEqual(len(tree["occurrences"]), 1)
        self.assertEqual(tree["assembly"]["root"]["children"], [])
        self.assertIn("bbox", tree)

    def test_canonical_bounds_reuse_exact_native_rotation_without_shape_key_serialization(self):
        from build123d import Compound, Location
        from cadgen._internal import component_package
        from cadgen._internal.step_scene_loader import _location_transform_matrix
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store import bounds
        from cadgen.store.build import build_document_tree

        # One STEP product whose nested native shape has two leaves, repeated
        # at two exact rotations and different translations. The optimized
        # path must match the old composed-shape bbox bit for bit while
        # measuring each native leaf only once for each component/rotation.
        def scene():
            prototype = Compound(children=[
                Compound(children=[
                    self.box("one"),
                    self.box("two").moved(Location((8, 2, 1), (0, 25, 0))),
                ]),
            ])
            locations = [
                Location((3, 4, 5), (17, 31, 43)).wrapped,
                Location((20, -7, 11), (17, 31, 43)).wrapped,
                Location((-8, 13, 2), (71, 5, 29)).wrapped,
                Location((14, 9, -6), (71, 5, 29)).wrapped,
            ]
            return LoadedStepScene(
                step_path=self.root / "native-repeat.step",
                roots=[
                    OccurrenceNode(
                        path=(index,), name=f"repeat-{index}", source_name=f"repeat-{index}",
                        transform=_location_transform_matrix(location), prototype_key=1,
                        location=location,
                    )
                    for index, location in enumerate(locations, start=1)
                ],
                prototype_shapes={1: prototype.wrapped},
            )

        bounds.clear()
        expected_hash, expected, _ = build_document_tree(scene(), force=True)
        real_optimal_box = component_package.optimal_box
        # The composed-shape path keys each leaf by its serialized BREP; the
        # prepared path keys it by the component's BREP hash and serializes none.
        with mock.patch.object(component_package, "_bbox_from_shape",
                               wraps=component_package._bbox_from_shape) as composed, \
                mock.patch.object(component_package, "optimal_box", wraps=real_optimal_box) as measured:
            actual_hash, actual, _ = build_document_tree(scene())
            self.assertEqual((actual_hash, actual), (expected_hash, expected))
            self.assertEqual(measured.call_count, 4)

            # A fresh process-cache state resolves the persisted scalar entry;
            # it still performs no native key serialization or measurement.
            bounds.clear()
            warm_hash, warm, _ = build_document_tree(scene())
            self.assertEqual((warm_hash, warm), (expected_hash, expected))
            self.assertEqual(measured.call_count, 4)
        self.assertEqual(composed.call_count, 0)

    def test_malformed_prepared_bounds_fall_back_to_exact_composed_shape(self):
        from build123d import Location
        from cadgen._internal import component_package
        from cadgen._internal.step_scene_loader import _location_transform_matrix
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store import bounds, build

        location = Location((3, 4, 5), (17, 31, 43)).wrapped
        scene = LoadedStepScene(
            step_path=self.root / "malformed-bounds.step",
            roots=[OccurrenceNode(
                path=(1,), name="part", source_name="part",
                transform=_location_transform_matrix(location), prototype_key=1,
                location=location,
            )],
            prototype_shapes={1: self.box().wrapped},
        )
        real_cached_box = bounds.cached_box

        def malformed_prepared_only(algorithm, parts, measure):
            if algorithm == bounds.PREPARED_OCCURRENCE_BOUNDS_ALGORITHM:
                return [0, 0, 0, 1, 1, float("nan")]
            return real_cached_box(algorithm, parts, measure)

        with mock.patch.object(bounds, "cached_box", side_effect=malformed_prepared_only), \
                mock.patch.object(component_package, "_bbox_from_shape",
                                  wraps=component_package._bbox_from_shape) as fallback:
            _, tree, _ = build.build_document_tree(scene)
        fallback.assert_called_once()
        self.assertIn("bbox", tree)

    def test_one_child_groups_keep_exact_document_nodes_even_with_identical_leaf_sets(self):
        from build123d import Compound

        inner = Compound(children=[self.box("leaf")], label="inner")
        outer = Compound(children=[inner], label="outer")
        shape = Compound(children=[outer], label="root")
        output = self.root / "one-child.step"
        result, tree, stats, _ = save_step(shape, output, root_name="root")
        self.assertEqual({"ok": True}, stats["verify"])
        compiled = self.assert_warm_and_cold_repackage(output, result)
        # Every group of one is a node of the file, the token the result gives it.
        written = compiled["assembly"]["root"]
        leaf = node_ids(tree, "leaf")
        for authored_id, name in zip(node_ids(tree, "root", "outer", "inner", "leaf"), ("root", "outer", "inner", "leaf")):
            self.assertEqual((written["id"], written["name"], written["leafPartIds"]), (authored_id, name, leaf))
            if written["children"]:
                written = written["children"][0]

    def test_multiple_free_roots_keep_a_stable_synthetic_group_when_repackaged(self):
        from cadgen._internal.step_scene_loader import _location_from_transform_matrix
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import IDENTITY_16

        moved = list(IDENTITY_16)
        moved[3] = 8
        scene = LoadedStepScene(
            step_path=self.root / "arbitrary-name.step",
            roots=[OccurrenceNode(path=(index,), name=name, source_name=name,
                                  transform=tuple(transform), prototype_key=1,
                                  location=_location_from_transform_matrix(tuple(transform)))
                   for index, name, transform in ((1, "first", IDENTITY_16), (2, "second", moved))],
            prototype_shapes={1: self.box().wrapped},
        )
        digest, tree, _ = build_document_tree(scene)
        from cadgen._internal.tree_tokens import is_occurrence_token

        self.assertEqual(tree["label"], "model")
        self.assertEqual([occ["name"] for occ in tree["occurrences"]], ["first", "second"])
        ids = [occ["id"] for occ in tree["occurrences"]]
        self.assertTrue(all(is_occurrence_token(occurrence_id) for occurrence_id in ids), ids)
        self.assertEqual(len(set(ids)), 2)
        note_document_tree("1" * 64, digest)
        warm = scene_from_render_package(self.root / "renamed.step", step_hash="1" * 64)
        warm_digest, warm_tree, _ = build_document_tree(warm)
        self.assertEqual((warm_digest, warm_tree), (digest, tree))

    def test_unnamed_step_fallback_uses_intrinsic_geometry_location_and_a_fixed_name(self):
        from types import SimpleNamespace

        from build123d import Location
        from cadgen._internal import step_scene_loader as loader

        shape = self.box().moved(Location((8, 2, 0)))
        reader = SimpleNamespace(ReadFile=lambda _: loader.IFSelect_RetDone,
                                 TransferRoots=lambda: None, OneShape=lambda: shape.wrapped)
        with mock.patch.object(loader, "STEPControl_Reader", return_value=reader):
            first = loader._load_fallback_occurrence_tree(self.root / "first.step")
            copied = loader._load_fallback_occurrence_tree(self.root / "copied.step")
        self.assertEqual(first[0][0].name, "model")
        self.assertEqual(first[0][0].name, copied[0][0].name)
        self.assertEqual(first[0][0].transform, copied[0][0].transform)
        self.assertEqual(first[0][0].transform[3], 8)
        self.assertEqual(first[0][0].transform[7], 2)
        self.assertTrue(next(iter(first[1].values())).Location().IsIdentity())

    def test_a_file_read_with_a_moved_repeat_shows_its_own_content(self):
        from build123d import Compound, Location
        from cadgen._internal import step_scene_package
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.records import document_entry_for_hash

        child_tree, _, _ = build_tree_from_compound(self.box("child"), root_name="child")
        first = materialize(child_tree)
        second = materialize(child_tree).moved(Location((8, 0, 0)))
        second.label = "repeat"
        shape = Compound(children=[first, second], label="parent")
        parse = step_scene_package._scene_from_selected_bytes

        def moved(*args, **kwargs):
            scene = parse(*args, **kwargs)
            repeated = scene.roots[0].children[1]
            transform = list(repeated.transform)
            transform[3] += 1
            repeated.transform = tuple(transform)
            return scene

        with mock.patch.object(step_scene_package, "_scene_from_selected_bytes", side_effect=moved):
            result, _, stats, digest = save_step(shape, self.root / "changed.step", root_name="parent")
        self.assertFalse(stats["verify"]["ok"])
        self.assertTrue(any(line.startswith("repeat (#") for line in stats["verify"]["differ"]), stats["verify"])
        entry = document_entry_for_hash(digest)
        self.assertNotEqual(entry["tree"], result)
        self.assertEqual(entry["differ"], stats["verify"]["differ"])
        self.assertNotIn("verified", entry)

    def test_products_read_in_another_order_keep_their_own_finishes(self):
        from build123d import Compound, Location
        from cadgen._internal import step_scene_package
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import document_entry_for_hash

        first, second = self.box("first"), self.box("second").moved(Location((8, 0, 0)))
        shape = Compound(children=[first, second], label="parent")
        materials = {
            "definitions": {
                "matte": {"name": "Matte", "roughness": .1},
                "polished": {"name": "Polished", "roughness": .9},
            },
            "assignments": [
                {"targets": ["#first"], "material": "matte"},
                {"targets": ["#second"], "material": "polished"},
            ],
        }
        parse = step_scene_package._scene_from_selected_bytes

        def reordered(*args, **kwargs):
            scene = parse(*args, **kwargs)
            scene.roots[0].children.reverse()
            return scene

        output = self.root / "reordered.step"
        with mock.patch.object(step_scene_package, "_scene_from_selected_bytes", side_effect=reordered):
            result, tree, stats, digest = save_step(shape, output, root_name="parent", materials=materials)
            reread = build_document_tree(step_scene_package._scene_from_selected_bytes(output.resolve(),
                                                                                       output.read_bytes()))[1]
        # A finish names its part by token, which its name and placement make, never its
        # place among its siblings: read in another order, each part is still its own.
        self.assertEqual(({"ok": True}, result), (stats["verify"], document_entry_for_hash(digest)["tree"]))
        by_name = {occurrence["name"]: occurrence["id"] for occurrence in tree["occurrences"]}
        self.assertEqual(tree["appearance"]["assignments"], {by_name["first"]: "matte", by_name["second"]: "polished"})
        self.assertEqual({occurrence["name"]: occurrence["id"] for occurrence in reread["occurrences"]}, by_name)
        self.assertEqual([occurrence["name"] for occurrence in reread["occurrences"]], ["second", "first"])

if __name__ == "__main__":
    unittest.main()
