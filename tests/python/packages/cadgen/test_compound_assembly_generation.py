from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import generation_runner
from cadgen._internal.step_scene_loader import load_step_scene
from cadgen.step_export import _create_bin_xcaf_doc, export_build123d_step_file
from cadgen._internal.step_scene import _bbox_from_shape, scene_leaf_occurrences, scene_occurrence_shape


def _rounded_color(color: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(component, 3) for component in color)


def _srgb_to_linear(component: float) -> float:
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


class CompoundAssemblyGenerationTests(unittest.TestCase):
    def test_step_payload_rejects_non_shapes(self) -> None:
        for payload, named in ((None, "NoneType"), ({"shape": object()}, "dict")):
            with self.subTest(payload=named):
                with self.assertRaisesRegex(TypeError, rf"must return a build123d Shape, got {named}$"):
                    generation_runner._normalize_step_payload(payload, script_path=Path("part.py"))

    def test_a_compound_with_children_packages_as_occurrences(self) -> None:
        # Packaging follows the shape and nothing else: a Compound placing
        # children becomes occurrences, a single solid one component.
        import build123d
        from cadgen.store.build import compound_has_children

        left = build123d.Box(1, 1, 1)
        right = build123d.Box(1, 1, 1)
        shape = build123d.Compound(obj=[left, right], label="compound_arm")

        self.assertTrue(compound_has_children(shape))
        self.assertFalse(compound_has_children(build123d.Box(1, 1, 1)))

    def test_labeled_childless_compound_does_not_warn_without_color(self) -> None:
        import build123d

        left = build123d.Box(1, 1, 1)
        right = build123d.Box(1, 1, 1)
        shape = build123d.Compound(obj=[left, right], label="compound_arm")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _create_bin_xcaf_doc(shape)

        messages = [str(item.message) for item in caught]
        self.assertNotIn("Unknown Compound type, color not set", messages)

    def test_colored_bare_compound_leaf_keeps_color_and_does_not_warn(self) -> None:
        # A boolean/chamfer chain can return a bare `Compound` (not
        # Part/Sketch/Curve). Exported alone — the per-component doc path —
        # this used to warn "Unknown Compound type, color not set" and ship
        # the geometry uncolored. The solids inside must get the color.
        import build123d

        solid = build123d.Solid.make_box(1, 1, 1)
        shape = build123d.Compound(obj=[solid])
        self.assertNotIsInstance(shape, build123d.Part)
        shape.label = "bare_leaf"
        shape.color = build123d.Color(1, 0, 0)

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                export_build123d_step_file(shape, Path(tempdir) / "bare_leaf.step")
            scene = load_step_scene(Path(tempdir) / "bare_leaf.step")

        messages = [str(item.message) for item in caught]
        self.assertNotIn("Unknown Compound type, color not set", messages)

        colors = {
            tuple(round(component, 3) for component in color)
            for color in scene.prototype_colors.values()
        }

        def collect(node):
            if node.color is not None:
                colors.add(tuple(round(component, 3) for component in node.color))
            for child in node.children:
                collect(child)

        for root in scene.roots:
            collect(root)
        self.assertIn((1.0, 0.0, 0.0, 1.0), colors)

    def test_colored_child_shapes_survive_compound_assembly_export(self) -> None:
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            left = build123d.Box(1, 1, 1)
            left.label = "red_child"
            left.color = build123d.Color(1, 0, 0)
            right = build123d.Pos(2, 0, 0) * build123d.Box(1, 1, 1)
            right.label = "blue_child"
            right.color = build123d.Color(0, 0, 1)
            shape = build123d.Compound(children=[left, right], label="colored_assembly")

            export_build123d_step_file(shape, Path(tempdir) / "colored_assembly.step")
            scene = load_step_scene(Path(tempdir) / "colored_assembly.step")

        colors = {
            tuple(round(component, 3) for component in color)
            for color in scene.prototype_colors.values()
        }
        colors.update(
            tuple(round(component, 3) for component in node.color)
            for root in scene.roots
            for node in root.children
            if node.color is not None
        )

        self.assertEqual(1, len(scene.roots))
        self.assertEqual(2, len(scene.roots[0].children))
        self.assertIn((1.0, 0.0, 0.0, 1.0), colors)
        self.assertIn((0.0, 0.0, 1.0, 1.0), colors)

    def test_nested_colored_compound_keeps_parent_transform(self) -> None:
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            child = build123d.Box(1, 1, 1)
            child.label = "motor_body"
            child.color = build123d.Color(0.1, 0.2, 0.3)
            expected_color = _rounded_color(child.color)
            expected_linear_color = _rounded_color(
                (
                    *(_srgb_to_linear(component) for component in expected_color[:3]),
                    expected_color[3],
                )
            )
            nested = build123d.Compound(children=[child], label="imported_motor")
            placed = build123d.Pos(20, 0, 0) * nested
            placed.label = "placed_motor"
            root = build123d.Compound(children=[placed], label="arm")

            export_build123d_step_file(root, Path(tempdir) / "arm.step")
            scene = load_step_scene(Path(tempdir) / "arm.step")

        leaves = scene_leaf_occurrences(scene)
        self.assertEqual(1, len(leaves))
        bbox = _bbox_from_shape(scene_occurrence_shape(scene, leaves[0]))
        self.assertGreater(bbox["min"][0], 19.0)
        self.assertLess(bbox["max"][0], 21.0)
        self.assertIn(
            _rounded_color(leaves[0].color),
            {expected_color, expected_linear_color},
        )


if __name__ == "__main__":
    unittest.main()
