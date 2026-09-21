"""The STEP document carries the colour the tree renders.

``srgb("#808080")`` is a Color whose CHANNELS are linear 0.216. The render
package stores those channels; the STEP writer used to store the
Quantity_Color's internal value instead (0.038 -- build123d linearizes its
constructor arguments a second time), so the file said sRGB 0.216 and every
reader of it showed the part two and a half stops darker than the tree.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from cadgen.color import linear_to_srgb, srgb
from tests.python.support.tmp_root import generated_cad_directory


class StepColorRoundTripTest(unittest.TestCase):
    def test_written_colour_is_the_intended_srgb_and_reads_back_as_the_channel(self) -> None:
        import build123d as bd
        from cadgen._internal.component_package import _occurrence_color
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file

        colour = srgb("#808080")
        box = bd.Box(10, 10, 10)
        box.color = colour
        box.label = "grey"
        root = bd.Compound(children=[box], label="grey_root")
        with tempfile.TemporaryDirectory(prefix="step-colour-") as tmp:
            out = Path(tmp) / "grey.step"
            export_build123d_step_file(root, out)
            match = re.search(r"COLOUR_RGB\('',([\d.E+-]+),([\d.E+-]+),([\d.E+-]+)\)", out.read_text(encoding="utf-8"))
            self.assertIsNotNone(match, "no COLOUR_RGB written")
            file_srgb = [float(v) for v in match.groups()]
            # What any CAD tool displays: the hex the author picked.
            self.assertEqual([round(v * 255) for v in file_srgb], [128, 128, 128])
            scene = load_step_scene(out)
            loaded = list(scene.prototype_colors.values())
            self.assertEqual(1, len(loaded))
        package_channel = _occurrence_color(box)
        for read_back, channel in zip(loaded[0][:3], package_channel[:3]):
            # Reader (linear) == package channel (linear): one model, one colour.
            self.assertAlmostEqual(read_back, channel, places=3)
            self.assertEqual(round(linear_to_srgb(read_back) * 255), 128)

    def test_repeated_geometry_keeps_occurrence_colors_and_one_component_payload(self) -> None:
        import build123d as bd
        from OCP.TopLoc import TopLoc_Location

        from cadgen._internal.component_package import _occurrence_color
        from cadgen.store.build import build_tree_through_step
        from cadgen.store.trees import get_tree

        scratch = generated_cad_directory(prefix="step-occurrence-colour-")
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        prototype = bd.Sphere(3)
        children = []
        for index, rgb in enumerate(((0.8, 0.1, 0.1), (0.1, 0.7, 0.2), (0.8, 0.1, 0.1))):
            child = prototype.moved(bd.Location((index * 10, 0, 0)))
            child.label = f"sphere-{index}"
            child.color = bd.Color(*rgb)
            children.append(child)
        native_shapes = [child.wrapped.Located(TopLoc_Location()) for child in children]
        self.assertTrue(all(native_shapes[0].IsSame(shape) for shape in native_shapes[1:]))

        expected = [_occurrence_color(child) for child in children]
        output = root / "repeated.step"
        with mock.patch.dict("os.environ", {"CADGEN_CACHE_DIR": str(root / "store")}):
            _, _, stats, _ = build_tree_through_step(
                bd.Compound(children=children, label="repeated"),
                output,
                root_name="repeated",
            )
            document = get_tree(stats["documentTree"])

        occurrences = document["occurrences"]
        self.assertEqual(3, len(occurrences))
        for occurrence, color in zip(occurrences, expected):
            for actual_channel, expected_channel in zip(occurrence["color"], color):
                self.assertAlmostEqual(actual_channel, expected_channel, places=3)
        self.assertEqual(
            1,
            len({occurrence["component"] for occurrence in occurrences}),
            "instance colors must not split identical geometry into component payloads",
        )
        self.assertEqual(1, len(document["components"]))
        self.assertEqual({}, next(iter(document["components"].values()))["faceColors"])


if __name__ == "__main__":
    unittest.main()
