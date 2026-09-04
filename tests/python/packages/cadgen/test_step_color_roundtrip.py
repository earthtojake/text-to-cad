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
from pathlib import Path

from cadgen.color import linear_to_srgb, srgb


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


if __name__ == "__main__":
    unittest.main()
