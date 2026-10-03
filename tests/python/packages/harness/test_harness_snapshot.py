"""`cadgen harness snapshot` draws the picture the CAD Viewer's plot pane draws, through a real WireViz.

A harness document, written as a person would write WireViz YAML, is
snapshotted light and dark in one job packet, one browser. What is pinned is the
shared contract, read back as PIXELS:

* the diagram is FITTED and centred with the viewer's own gutter: on a dark
  surround, everything that is not the surround is exactly WireViz's page,
  fitted (drawing2d's fit, restated here) to the size the plot payload gives it;
* the page keeps WireViz's colour and the surround is the appearance's, so a
  light snapshot shows the diagram's own ink on white;
* nothing is left to warn about: a harness has no ratsnest.

Needs WireViz and Graphviz (scripts/test/test-harness.sh).
"""

from __future__ import annotations

import json
import os
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

# Not written by cadgen: WireViz's own syntax, a serial lead with a shield.
DOCUMENT = textwrap.dedent(
    """
    connectors:
      X1:
        type: D-Sub
        subtype: female
        pinlabels: [DCD, RX, TX, DTR, GND]
      X2:
        type: Molex KK 254
        pinlabels: [GND, RX, TX]
    cables:
      W1:
        gauge: 0.25 mm2
        length: 0.2
        color_code: DIN
        wirecount: 3
        shield: true
    connections:
      -
        - X1: [5, 2, 3]
        - W1: [1, 2, 3]
        - X2: [1, 3, 2]
    """
)

# packages/core/src/lib/drawing2d/transform.js: DRAWING_FIT_MARGIN.
FIT_MARGIN = 16
SIZE = (480, 360)
# packages/core/src/lib/appTheme.js.
LIGHT, DARK = (255, 255, 255), (41, 41, 41)


def near(pixel, expected, tolerance=12):
    return sum(abs(a - b) for a, b in zip(pixel, expected)) <= tolerance


def fitted_rect(width_mm, height_mm, width, height):
    """`fitTransform` over the page box, restated: where the sheet lands, in pixels."""
    scale = min(max(width - 2 * FIT_MARGIN, width * 0.5) / width_mm, max(height - 2 * FIT_MARGIN, height * 0.5) / height_mm)
    left, top = width / 2 - width_mm * scale / 2, height / 2 - height_mm * scale / 2
    return left, top, left + width_mm * scale, top + height_mm * scale


class HarnessSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = generated_cad_directory(prefix="harness-snapshot-")
        cls.folder = Path(cls._tmp.name)
        (cls.folder / "serial.harness.yml").write_text(DOCUMENT, encoding="utf-8")
        sized = {"width": SIZE[0], "height": SIZE[1]}
        packet = {"jobs": [
            {"input": "serial.harness.yml", "outputs": [{"path": "light.png", **sized}]},
            {"input": "serial.harness.yml", "display": {"appearance": "dark"}, "outputs": [{"path": "dark.png", **sized}]},
        ]}
        (cls.folder / "render.json").write_text(json.dumps(packet), encoding="utf-8")
        from cadgen import harness
        from cadgen.wireviz.plot import plot_payload_bytes

        previous = Path.cwd()
        os.chdir(cls.folder)
        try:
            cls.result = harness.snapshot(job=cls.folder / "render.json")
        finally:
            os.chdir(previous)
        # The payload the snapshot drew, from the store: the page's size in millimetres.
        [cls.sheet] = json.loads(plot_payload_bytes(cls.folder / "serial.harness.yml"))["sheets"]
        cls.images = {name: read_png((cls.folder / name).read_bytes()) for name in ("light.png", "dark.png")}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_output_is_written_at_the_size_asked_for_with_nothing_to_warn_about(self) -> None:
        self.assertTrue(self.result.ok)
        self.assertEqual([], list(self.result.warnings))
        for name, image in self.images.items():
            with self.subTest(output=name):
                self.assertEqual(SIZE, (image.width, image.height))

    def test_the_page_is_fitted_on_the_appearances_surround(self) -> None:
        image = self.images["dark.png"]
        self.assertTrue(near(image.pixel(0, 0), DARK), image.pixel(0, 0))
        left, top, right, bottom = fitted_rect(self.sheet["width"], self.sheet["height"], *SIZE)
        painted = [(x, y) for y in range(image.height) for x in range(image.width) if not near(image.pixel(x, y), DARK)]
        xs, ys = [x for x, _ in painted], [y for _, y in painted]
        for found, expected in ((min(xs), left), (max(xs), right - 1), (min(ys), top), (max(ys), bottom - 1)):
            self.assertLessEqual(abs(found - expected), 2, f"the page's box is {(min(xs), min(ys), max(xs), max(ys))}, not {(left, top, right, bottom)}")
        page = tuple(int(self.sheet["background"][index:index + 2], 16) for index in (1, 3, 5))
        self.assertTrue(near(image.pixel(round(left) + 2, round(top) + 2), page), image.pixel(round(left) + 2, round(top) + 2))

    def test_a_light_snapshot_shows_the_diagrams_own_ink_on_white(self) -> None:
        image = self.images["light.png"]
        self.assertTrue(near(image.pixel(0, 0), LIGHT), image.pixel(0, 0))
        left, top, right, bottom = (round(value) for value in fitted_rect(self.sheet["width"], self.sheet["height"], *SIZE))
        inked = sum(not near(image.pixel(x, y), LIGHT) for y in range(top, bottom) for x in range(left, right))
        self.assertGreater(inked, 500, "WireViz's connectors and wires are drawn")


if __name__ == "__main__":
    unittest.main()
