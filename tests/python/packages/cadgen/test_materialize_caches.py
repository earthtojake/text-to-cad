"""Materialization memo hits preserve immutable bytes and private appearance."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class MaterializeCacheTest(unittest.TestCase):
    def setUp(self):
        self.scratch = generated_cad_directory(prefix="materialize-recipes-")
        self.addCleanup(self.scratch.cleanup)
        patcher = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(self.scratch.name) / "store")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.materialize = importlib.import_module("cadgen.store.materialize")
        self.materialize.reset_memo()
        self.addCleanup(self.materialize.reset_memo)

    def test_immutable_brep_cache_is_bounded_and_released(self):
        from cadgen.store.objects import put_object
        digests = [put_object(bytes([n]) * 8) for n in range(3)]
        with mock.patch.object(self.materialize, "_BREP_BYTES_MEMO_CAPACITY", 16):
            first = self.materialize._bytes_for_object(digests[0])
            self.materialize._bytes_for_object(digests[1])
            self.materialize._bytes_for_object(digests[0])
            self.materialize._bytes_for_object(digests[2])
            self.assertEqual(list(self.materialize._BREP_BYTES_MEMO), [digests[0], digests[2]])
            self.assertEqual(self.materialize._BREP_BYTES_MEMO_SIZE, 16)
        self.materialize.reset_memo()
        self.assertFalse(self.materialize._BREP_BYTES_MEMO)
        self.assertEqual(first, bytes([0]) * 8)

    def test_intrinsic_recipes_are_private_and_require_no_surface_cache(self):
        from build123d import Solid
        from cadgen.store.build import build_tree_from_compound
        from cadgen._internal import surface_extract
        shape = Solid.make_box(2, 3, 4)
        shape.cad_face_ordinal_colors = {1: (.2, .3, .4, 1.)}
        tree = build_tree_from_compound(shape, root_name="box")[0]
        with mock.patch.object(surface_extract, "read_surf", side_effect=AssertionError("surface read")):
            first = self.materialize.materialize(tree)
            first.cad_face_ordinal_colors[1] = (1., 0., 0., 1.)
            self.materialize.reset_memo()
            second = self.materialize.materialize(tree)
        self.assertEqual(second.cad_face_ordinal_colors, {1: (.2, .3, .4, 1.)})

    def test_corrupt_brep_miss_cannot_poison_materialization_after_atomic_repair(self):
        from build123d import Solid
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.objects import object_path, put_object
        from cadgen.store.trees import flatten

        tree, _, _ = build_tree_from_compound(Solid.make_box(8, 6, 4), root_name="box")
        brep = next(iter(flatten(tree)["components"].values()))["brep"]
        target = object_path(brep)
        original = target.read_bytes()
        # Both an unreadable payload and a readable but different native shape
        # must be rejected before memo admission, not just on failed decoding.
        cases = ((False, b"not a BREP"), (True, _shape_brep_bytes(Solid.make_box(1, 2, 3))))
        for readable, corrupt in cases:
            with self.subTest(readable=readable):
                self.materialize.reset_memo()
                target.write_bytes(corrupt)
                with self.assertRaises(ValueError):
                    self.materialize.materialize(tree)
                self.assertNotIn(brep, self.materialize._BREP_BYTES_MEMO)
                self.assertEqual(put_object(original, repair=True), brep)
                recovered = self.materialize.materialize(tree)
                self.assertAlmostEqual(recovered.volume, 8 * 6 * 4)
                self.assertEqual(self.materialize._bytes_for_object(brep), original)


if __name__ == "__main__":
    unittest.main()
