"""Direct STEP export preserves placed assembly roots and nested frames."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import build123d as bd

from cadgen._internal.component_package import _occurrence_color
from cadgen._internal.step_scene_loader import load_step_scene
from cadgen._internal.step_scene_mesh import scene_occurrence_shape
from cadgen.step_export import export_build123d_step_file


class StepExportPlacementTests(unittest.TestCase):
    def test_placed_root_roundtrips_hierarchy_appearance_and_geometry_without_mutation(self):
        for root_frame in (bd.Pos(40, 50, 60), bd.Pos(40, 50, 60) * bd.Rot(17, 29, 83)):
            with self.subTest(root_frame=root_frame), tempfile.TemporaryDirectory(prefix="step-placement-") as tmp:
                leaf = bd.Solid.make_box(2, 3, 4)
                leaf.label, leaf.color = "leaf", bd.Color("red")
                sibling = bd.Pos(0, 8, 0) * leaf
                sibling.label, sibling.color = "sibling", bd.Color("blue")
                group_frame = bd.Pos(7, 11, 13) * bd.Rot(0, 90, 0)
                group = group_frame * bd.Compound(children=[leaf, sibling], label="nested")
                root = root_frame * bd.Compound(children=[group], label="root")
                nodes = [root, root.children[0], *root.children[0].children]
                original = [(node.location, node.label, node.color, node.wrapped) for node in nodes]
                expected = {
                    "leaf": root_frame * group_frame * leaf,
                    "sibling": root_frame * group_frame * sibling,
                }

                path = Path(tmp) / "root.step"
                export_build123d_step_file(root, path)
                first_bytes = path.read_bytes()
                scene = load_step_scene(path, record_read=False)
                self.assertEqual(len(scene.roots), 1)
                loaded_root = scene.roots[0]
                self.assertEqual((loaded_root.path, loaded_root.name), ((1,), "root"))
                self.assertEqual(len(loaded_root.children), 1)
                loaded_group = loaded_root.children[0]
                self.assertEqual((loaded_group.path, loaded_group.name), ((1, 1), "nested"))
                self.assertEqual([node.path for node in loaded_group.children], [(1, 1, 1), (1, 1, 2)])
                self.assertEqual([node.name for node in loaded_group.children], ["leaf", "sibling"])
                for node in loaded_group.children:
                    actual = bd.Compound.cast(scene_occurrence_shape(scene, node))
                    authored = expected[node.name]
                    self.assertLess((actual.center(bd.CenterOf.MASS) - authored.center(bd.CenterOf.MASS)).length, 1e-7)
                    self.assertAlmostEqual(actual.volume, authored.volume)
                    actual_vertices = sorted(tuple(v.center()) for v in actual.vertices())
                    authored_vertices = sorted(tuple(v.center()) for v in authored.vertices())
                    self.assertEqual(len(actual_vertices), len(authored_vertices))
                    for actual_point, authored_point in zip(actual_vertices, authored_vertices):
                        for actual_coordinate, authored_coordinate in zip(actual_point, authored_point):
                            self.assertAlmostEqual(actual_coordinate, authored_coordinate, places=7)
                    for actual_channel, expected_channel in zip(node.color, _occurrence_color(authored)):
                        self.assertAlmostEqual(actual_channel, expected_channel, places=3)
                export_build123d_step_file(root, path)
                self.assertEqual(path.read_bytes(), first_bytes)
                for node, (location, label, color, wrapped) in zip(nodes, original):
                    self.assertEqual(node.location, location)
                    self.assertEqual(node.label, label)
                    self.assertEqual(node.color, color)
                    self.assertTrue(node.wrapped.IsSame(wrapped))


if __name__ == "__main__":
    unittest.main()
