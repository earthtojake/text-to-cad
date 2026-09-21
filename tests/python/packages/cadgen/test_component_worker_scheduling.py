"""Small component batches avoid spawn without changing geometry or overrides."""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class ComponentWorkerSizing(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.dict(os.environ, {"CADGEN_COMPONENT_WORKERS": ""}),
            mock.patch("os.cpu_count", return_value=10),
            mock.patch("cadgen.daemon.memory.component_worker_limit", side_effect=lambda count: min(4, count)),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_small_known_payload_avoids_spawn_but_unknown_and_large_keep_sizing(self):
        from cadgen._internal.component_package import _component_build_worker_count

        self.assertEqual(_component_build_worker_count(9, payload_bytes=768 * 1024), 1)
        self.assertEqual(_component_build_worker_count(1000, payload_bytes=768 * 1024), 1)
        self.assertEqual(_component_build_worker_count(9, payload_bytes=768 * 1024 + 1), 4)
        self.assertEqual(_component_build_worker_count(9), 4)
        self.assertEqual(_component_build_worker_count(5, payload_bytes=1024 * 1024), 1)

    def test_explicit_values_keep_their_existing_meaning_and_memory_cap(self):
        from cadgen._internal.component_package import _component_build_worker_count

        for value, expected in (("0", 1), ("1", 1), ("2", 2), ("8", 4),
                                (" 2 ", 2), ("invalid", 1), (" ", 1)):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"CADGEN_COMPONENT_WORKERS": value}):
                self.assertEqual(_component_build_worker_count(9, payload_bytes=1), expected)
        with mock.patch.dict(os.environ, {"CADGEN_COMPONENT_WORKERS": "8"}):
            self.assertEqual(_component_build_worker_count(2, payload_bytes=1), 2)

    def test_memory_admission_still_caps_large_defaults_and_explicit_small_batches(self):
        from cadgen._internal.component_package import _component_build_worker_count

        with mock.patch("cadgen.daemon.memory.component_worker_limit", return_value=1) as limit:
            self.assertEqual(_component_build_worker_count(9, payload_bytes=1024 * 1024), 1)
            limit.assert_called_once_with(8)
            limit.reset_mock()
            with mock.patch.dict(os.environ, {"CADGEN_COMPONENT_WORKERS": "8"}):
                self.assertEqual(_component_build_worker_count(9, payload_bytes=1), 1)
            limit.assert_called_once_with(8)


class ComponentSchedulingParity(unittest.TestCase):
    def test_default_inline_and_explicit_spawn_publish_identical_owned_geometry(self):
        from build123d import Compound, Solid
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.objects import read_object

        with generated_cad_directory(prefix="component-scheduling-") as temporary:
            root = Path(temporary)
            parts = [Solid.make_box(index + 1, 2, 3) for index in range(6)]
            for index, part in enumerate(parts):
                part.label = f"part-{index}"
                part.cad_face_ordinal_colors = {1: (index / 6, .25, .75, 1.0)}
            source = Compound(children=parts, label="six-parts")
            original = [_shape_brep_bytes(part) for part in parts]
            self.assertLessEqual(sum(map(len, original)), 512 * 1024)
            outputs = []
            for mode, workers in (("default", ""), ("explicit", "2")):
                env = {"CADGEN_CACHE_DIR": str(root / mode), "CADGEN_COMPONENT_WORKERS": workers}
                with mock.patch.dict(os.environ, env):
                    if mode == "default":
                        with mock.patch("concurrent.futures.ProcessPoolExecutor",
                                        side_effect=AssertionError("small default batch spawned")):
                            tree_hash, tree, stats = build_tree_from_compound(source, root_name="six-parts")
                    else:
                        # Memory admission remains active; this machine-independent
                        # allowance makes the explicit two-worker branch observable.
                        with mock.patch("cadgen.daemon.memory.component_worker_limit", side_effect=lambda count: count):
                            tree_hash, tree, stats = build_tree_from_compound(source, root_name="six-parts")
                    artifacts = {component[kind]: read_object(component[kind])
                                 for component in tree["components"].values() for kind in ("brep",)}
                    outputs.append((tree_hash, tree, artifacts))
                    self.assertEqual(stats["components_built"], 6)
                    self.assertFalse((root / mode / "index/surface").exists())
                self.assertEqual([_shape_brep_bytes(part) for part in parts], original)
            self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
