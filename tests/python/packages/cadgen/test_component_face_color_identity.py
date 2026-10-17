"""A part's identity includes face colors; immutable BREP identity remains shared."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.documents import assert_same_document, save_step
from tests.python.support.tmp_root import generated_cad_directory


RED = (1.0, 0.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)


class ComponentFaceColorIdentityTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="component-face-color-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        workers = mock.patch("cadgen._internal.component_package._component_build_worker_count", return_value=1)
        workers.start()
        self.addCleanup(workers.stop)

    def box(self, colors=None):
        from build123d import Solid

        shape = Solid.make_box(2, 3, 4)
        shape.label = "box"
        if colors is not None:
            shape.cad_face_ordinal_colors = colors
        return shape

    def faces(self, component):
        return {int(ordinal): tuple(color) for ordinal, color in component["faceColors"].items()}

    def test_normalized_input_rekeys_legacy_colorless_components_but_keeps_brep_bytes(self):
        from build123d import Location
        from cadgen._internal.component_package import _content_hash_and_bytes, _content_hash_shape

        shape = self.box()
        plain_hash, brep = _content_hash_and_bytes(shape)
        # The retired pre-v3 key: a global cache-schema number (last value 20)
        # salting the bare BREP bytes. Spelled literally so the retired scheme
        # cannot come back through an import.
        legacy_hash = hashlib.sha256(b"20" + b"\0" + brep).hexdigest()
        self.assertNotEqual(plain_hash, legacy_hash, "a polluted legacy colorless index must not be reused")
        shape.cad_face_ordinal_colors = {1: RED}
        red_hash, red_brep = _content_hash_and_bytes(shape)
        blue_hash, blue_brep = _content_hash_and_bytes(shape.wrapped, face_colors={1: BLUE})
        self.assertEqual(red_brep, brep)
        self.assertEqual(blue_brep, brep)
        self.assertEqual(len({plain_hash, red_hash, blue_hash}), 3)
        self.assertEqual(_content_hash_shape(shape), red_hash)
        self.assertEqual(_content_hash_and_bytes(shape.wrapped, face_colors={"1": [1, 0, 0, 1]})[0], red_hash)
        self.assertEqual(_content_hash_and_bytes(shape.moved(Location((8, 0, 0))))[0], red_hash)
        self.assertEqual(_content_hash_and_bytes(shape.wrapped, face_colors={1: RED, "1": RED})[0], red_hash)
        with self.assertRaisesRegex(ValueError, "conflicting colors"):
            _content_hash_and_bytes(shape.wrapped, face_colors={1: RED, "1": BLUE})

    def test_differently_colored_occurrences_sharing_one_tshape_do_not_merge(self):
        from build123d import Compound, Location, Solid
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_document_tree, build_tree_from_compound
        from cadgen.store.records import document_entry_for_hash

        prototype = self.box()
        red, blue = Solid(prototype.wrapped), Solid(prototype.wrapped)
        blue.location = Location((8, 0, 0))
        red.label, blue.label = "red", "blue"
        red.cad_face_ordinal_colors, blue.cad_face_ordinal_colors = {1: RED}, {1: BLUE}
        self.assertTrue(red.wrapped.IsPartner(blue.wrapped))
        shape = Compound(children=[red, blue], label="two-colors")
        before, tree, _ = build_tree_from_compound(shape, root_name="two-colors")
        self.assertEqual(len(tree["components"]), 2)
        self.assertEqual(len({entry["brep"] for entry in tree["components"].values()}), 1)
        self.assertEqual([self.faces(tree["components"][occ["component"]]) for occ in tree["occurrences"]],
                         [{1: RED}, {1: BLUE}])
        self.assertEqual(build_tree_from_compound(shape, root_name="two-colors")[0], before)

        output = self.root / "two-colors.step"
        result, _, stats, digest = save_step(shape, output, root_name="two-colors")
        first_bytes = output.read_bytes()
        # The file holds the result, whose two components share one body.
        self.assertEqual((result, {"ok": True}), (before, stats["verify"]))
        self.assertEqual(document_entry_for_hash(digest)["tree"], result)
        _, cold, _ = build_document_tree(load_step_scene(output))
        self.assertEqual([self.faces(cold["components"][occ["component"]]) for occ in cold["occurrences"]],
                         [{1: RED}, {1: BLUE}])
        repeated, _, _, repeated_digest = save_step(shape, output, root_name="two-colors")
        self.assertEqual((repeated, repeated_digest), (result, digest))
        self.assertEqual(output.read_bytes(), first_bytes)

    def test_red_blue_and_colorless_documents_match_empty_store_compilation(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import get_tree

        documents = []
        step_hashes = []
        for name, colors in (("red", {1: RED}), ("blue", {1: BLUE}), ("plain", {})):
            with self.subTest(name=name):
                output = self.root / "box.step"
                _, _, stats, digest = save_step(self.box(colors), output, root_name="box")
                self.assertEqual({"ok": True}, stats["verify"])
                document = get_tree(document_entry_for_hash(digest)["tree"])
                component = next(iter(document["components"].values()))
                self.assertEqual(self.faces(component), colors)
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"cold-{name}")}):
                    cold_hash, _, _ = build_document_tree(load_step_scene(output))
                    cold = get_tree(cold_hash)
                assert_same_document(self, document, cold)
                documents.append(document)
                step_hashes.append(digest)
        self.assertEqual(len(set(step_hashes)), 3)
        self.assertEqual(len({cid for document in documents for cid in document["components"]}), 3)
        self.assertEqual(len({component["brep"] for document in documents
                              for component in document["components"].values()}), 1)
        # Subsequent writes leave the earlier immutable colored parts intact.
        self.assertEqual(self.faces(next(iter(documents[0]["components"].values()))), {1: RED})
        self.assertEqual(self.faces(next(iter(documents[1]["components"].values()))), {1: BLUE})

    def test_materialized_occurrences_own_face_colors_while_sharing_one_brep_decode(self):
        from importlib import import_module

        from build123d import Compound, Location
        from cadgen._internal import topology_extract
        from cadgen.store.build import build_tree_from_compound

        materialization = import_module("cadgen.store.materialize")
        red, blue = self.box({1: RED}), self.box({1: BLUE}).moved(Location((8, 0, 0)))
        repeated = red.moved(Location((16, 0, 0)))
        tree, _, _ = build_tree_from_compound(Compound(children=[red, blue, repeated]), root_name="colors")
        from cadgen._internal import component_package
        with mock.patch.object(component_package, "decode_geometry_component", wraps=component_package.decode_geometry_component) as decoded:
            with mock.patch.object(topology_extract, "extract_topology_facts", wraps=topology_extract.extract_topology_facts) as extracted:
                first = materialization.materialize(tree)
        self.assertEqual(decoded.call_count, 1)
        self.assertEqual(extracted.call_count, 0)
        self.assertEqual([child.cad_face_ordinal_colors for child in first.children], [{1: RED}, {1: BLUE}, {1: RED}])
        second = materialization.materialize(tree)
        first.children[0].cad_face_ordinal_colors[1] = BLUE
        self.assertEqual(first.children[2].cad_face_ordinal_colors, {1: RED})
        self.assertEqual([child.cad_face_ordinal_colors for child in second.children], [{1: RED}, {1: BLUE}, {1: RED}])

    def test_pinned_colored_children_save_identically_warm_and_after_store_deletion(self):
        import shutil

        from build123d import Compound, Location
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.build import build_document_tree, build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import flatten, get_tree

        red_tree, _, _ = build_tree_from_compound(self.box({1: RED}), root_name="red-child")
        blue_tree, _, _ = build_tree_from_compound(self.box({1: BLUE}), root_name="blue-child")

        def parent():
            red = materialize(red_tree).moved(Location((2, 3, 0)))
            blue = materialize(blue_tree).moved(Location((10, 3, 0)))
            return Compound(children=[red, blue], label="colored-parent")

        output = self.root / "parent.step"
        result, result_tree, stats, step_hash = save_step(parent(), output, root_name="colored-parent")
        first_bytes = output.read_bytes()
        self.assertEqual([link["tree"] for link in result_tree["links"]], [red_tree, blue_tree])
        # The saved document is the linked result: a reader takes it flattened.
        self.assertEqual(({"ok": True}, result), (stats["verify"], document_entry_for_hash(step_hash)["tree"]))
        document = flatten(result)
        self.assertEqual([self.faces(document["components"][occ["component"]]) for occ in document["occurrences"]],
                         [{1: RED}, {1: BLUE}])
        self.assertEqual(len({entry["brep"] for entry in document["components"].values()}), 1)
        repeated, _, _, repeated_sha = save_step(parent(), output, root_name="colored-parent")
        self.assertEqual((repeated, repeated_sha), (result, step_hash))
        self.assertEqual(output.read_bytes(), first_bytes)
        warm_scene = scene_from_render_package(output, step_hash=step_hash)
        self.assertIsNotNone(warm_scene)
        assert_same_document(self, document, build_document_tree(warm_scene)[1])

        # No source or model record is needed to recover the saved appearance: a cold
        # compile reads the same document, every component from the file.
        shutil.rmtree(self.root / "store")
        with self.assertRaises(FileNotFoundError):
            materialize(red_tree)
        cold_hash, _, _ = build_document_tree(load_step_scene(output))
        assert_same_document(self, document, get_tree(cold_hash))

    def test_a_face_override_on_a_decoded_child_moves_without_reusing_the_original_child_finish(self):
        from build123d import Compound, Location
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.trees import flatten

        red_tree, _, _ = build_tree_from_compound(self.box({1: RED}), root_name="child")
        original = materialize(red_tree, label="child")
        original.cad_face_ordinal_colors = {1: BLUE}
        moved = original.moved(Location((8, 0, 0)))
        moved.cad_face_ordinal_colors[1] = RED
        self.assertEqual(original.cad_face_ordinal_colors, {1: BLUE})
        shape = Compound(children=[original, moved], label="overrides")
        result_hash, result, stats, _ = save_step(shape, self.root / "override.step", root_name="overrides")
        self.assertEqual([link["tree"] for link in result["links"]], [red_tree])
        self.assertEqual({"ok": True}, stats["verify"])
        document = flatten(result_hash)
        self.assertEqual([self.faces(document["components"][occ["component"]]) for occ in document["occurrences"]],
                         [{1: BLUE}, {1: RED}])
        self.assertEqual(materialize(red_tree).cad_face_ordinal_colors, {1: RED})

if __name__ == "__main__":
    unittest.main()
