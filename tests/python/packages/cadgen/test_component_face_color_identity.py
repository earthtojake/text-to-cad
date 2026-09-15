"""SURF identity includes face colors; immutable BREP identity remains shared."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

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
        from cadgen._internal.cache_schema import CACHE_SCHEMA_VERSION
        from cadgen._internal.component_package import _content_hash_and_bytes, _content_hash_shape

        shape = self.box()
        plain_hash, brep = _content_hash_and_bytes(shape)
        legacy_hash = hashlib.sha256(str(CACHE_SCHEMA_VERSION).encode() + b"\0" + brep).hexdigest()
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
        from cadgen.store.build import build_tree_from_compound, build_tree_through_step
        from cadgen.store.trees import get_tree

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
        result, _, stats, digest = build_tree_through_step(shape, output, root_name="two-colors")
        first_bytes = output.read_bytes()
        document = get_tree(stats["documentTree"])
        self.assertEqual(len(document["components"]), 2)
        self.assertEqual(len({entry["brep"] for entry in document["components"].values()}), 1)
        self.assertEqual([self.faces(document["components"][occ["component"]]) for occ in document["occurrences"]],
                         [{1: RED}, {1: BLUE}])
        repeated, _, repeated_stats, repeated_digest = build_tree_through_step(shape, output, root_name="two-colors")
        self.assertEqual((repeated, repeated_stats["documentTree"], repeated_digest),
                         (result, stats["documentTree"], digest))
        self.assertEqual(output.read_bytes(), first_bytes)

    def test_red_blue_and_colorless_documents_match_empty_store_compilation(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_document_tree, build_tree_through_step
        from cadgen.store.trees import get_tree

        documents = []
        step_hashes = []
        for name, colors in (("red", {1: RED}), ("blue", {1: BLUE}), ("plain", {})):
            with self.subTest(name=name):
                output = self.root / "box.step"
                _, _, stats, digest = build_tree_through_step(self.box(colors), output, root_name="box")
                document = get_tree(stats["documentTree"])
                component = next(iter(document["components"].values()))
                self.assertEqual(self.faces(component), colors)
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"cold-{name}")}):
                    cold_hash, _, _ = build_document_tree(load_step_scene(output, record_read=False))
                self.assertEqual(cold_hash, stats["documentTree"])
                documents.append(document)
                step_hashes.append(digest)
        self.assertEqual(len(set(step_hashes)), 3)
        self.assertEqual(len({cid for document in documents for cid in document["components"]}), 3)
        self.assertEqual(len({component["brep"] for document in documents
                              for component in document["components"].values()}), 1)
        # Subsequent writes leave the earlier immutable colored SURFs intact.
        self.assertEqual(self.faces(next(iter(documents[0]["components"].values()))), {1: RED})
        self.assertEqual(self.faces(next(iter(documents[1]["components"].values()))), {1: BLUE})

    def test_materialized_occurrences_own_face_colors_while_sharing_one_brep_decode(self):
        from importlib import import_module

        from build123d import Compound, Location
        from cadgen._internal import surface_extract
        from cadgen.store.build import build_tree_from_compound

        materialization = import_module("cadgen.store.materialize")
        red, blue = self.box({1: RED}), self.box({1: BLUE}).moved(Location((8, 0, 0)))
        repeated = red.moved(Location((16, 0, 0)))
        tree, _, _ = build_tree_from_compound(Compound(children=[red, blue, repeated]), root_name="colors")
        from cadgen._internal import component_package
        with mock.patch.object(component_package, "decode_geometry_component", wraps=component_package.decode_geometry_component) as decoded:
            with mock.patch.object(surface_extract, "read_surf", wraps=surface_extract.read_surf) as surfaces:
                first = materialization.materialize(tree)
        self.assertEqual(decoded.call_count, 1)
        self.assertEqual(surfaces.call_count, 0)
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
        from cadgen.store.build import build_document_tree, build_tree_from_compound, build_tree_through_step
        from cadgen.store.materialize import materialize
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree

        red_tree, _, _ = build_tree_from_compound(self.box({1: RED}), root_name="red-child")
        blue_tree, _, _ = build_tree_from_compound(self.box({1: BLUE}), root_name="blue-child")

        def parent():
            red = materialize(red_tree).moved(Location((2, 3, 0)))
            blue = materialize(blue_tree).moved(Location((10, 3, 0)))
            return Compound(children=[red, blue], label="colored-parent")

        output = self.root / "parent.step"
        result, result_tree, stats, step_hash = build_tree_through_step(parent(), output, root_name="colored-parent")
        first_bytes = output.read_bytes()
        self.assertEqual([link["tree"] for link in result_tree["links"]], [red_tree, blue_tree])
        document = get_tree(stats["documentTree"])
        self.assertEqual([self.faces(document["components"][occ["component"]]) for occ in document["occurrences"]],
                         [{1: RED}, {1: BLUE}])
        self.assertEqual(len({entry["brep"] for entry in document["components"].values()}), 1)
        repeated, _, repeated_stats, repeated_sha = build_tree_through_step(parent(), output, root_name="colored-parent")
        self.assertEqual((repeated, repeated_stats["documentTree"], repeated_sha),
                         (result, stats["documentTree"], step_hash))
        self.assertEqual(output.read_bytes(), first_bytes)
        note_document_tree(step_hash, stats["documentTree"])
        warm_scene = scene_from_render_package(output, step_hash=step_hash)
        self.assertIsNotNone(warm_scene)
        self.assertEqual(build_document_tree(warm_scene)[0], stats["documentTree"])

        # No source or model record is needed to recover the saved appearance.
        shutil.rmtree(self.root / "store")
        with self.assertRaises(FileNotFoundError):
            materialize(red_tree)
        cold_hash, _, _ = build_document_tree(load_step_scene(output, record_read=False))
        self.assertEqual((cold_hash, get_tree(cold_hash)), (stats["documentTree"], document))

    def test_pre_force_face_override_moves_without_reusing_the_original_child_finish(self):
        from build123d import Compound, Location
        from cadgen.store.build import build_tree_from_compound, build_tree_through_step
        from cadgen.store.lazy import LazyCompound
        from cadgen.store.materialize import materialize
        from cadgen.store.trees import get_tree

        red_tree, _, _ = build_tree_from_compound(self.box({1: RED}), root_name="child")
        original = LazyCompound("absent.py::child", None, frame=None, label="child", tree=red_tree)
        original.cad_face_ordinal_colors = {1: BLUE}
        moved = original.moved(Location((8, 0, 0)))
        moved.cad_face_ordinal_colors[1] = RED
        self.assertEqual(original.cad_face_ordinal_colors, {1: BLUE})
        shape = Compound(children=[original, moved], label="overrides")
        _, result, stats, _ = build_tree_through_step(shape, self.root / "override.step", root_name="overrides")
        self.assertEqual([link["tree"] for link in result["links"]], [red_tree])
        document = get_tree(stats["documentTree"])
        self.assertEqual([self.faces(document["components"][occ["component"]]) for occ in document["occurrences"]],
                         [{1: BLUE}, {1: RED}])
        self.assertEqual(materialize(red_tree).cad_face_ordinal_colors, {1: RED})


if __name__ == "__main__":
    unittest.main()
