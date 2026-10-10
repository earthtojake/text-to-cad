"""`cadgen pcb snapshot` draws the picture the CAD Viewer's plot pane draws, through a real KiCad 10.

One draft board (its LED left unrouted) is built with ``python blinky.py`` and
snapshotted with its schematic in one job packet, one browser. What is pinned is
the shared contract, read back as PIXELS:

* the board is FITTED and centred with the viewer's own gutter: everything that
  is not the surround is exactly the board's fitted rectangle (drawing2d's fit,
  restated here), so the CLI cannot frame a board differently from the pane;
* the board sits on KiCad's board background and the surround is the
  appearance's, which flips with ``--appearance`` while the board does not;
* a schematic sheet sits on KiCad's paper colour;
* a draft says so: the unrouted connection is reported beside the image.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.packages.kicad.test_pcb_models import board_source
from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")

# packages/core/src/lib/drawing2d/transform.js: DRAWING_FIT_MARGIN.
FIT_MARGIN = 16
# The board's outline in board_source(): 40 x 30 mm, which KiCad plots page-fitted.
BOARD_SIZE = (40.0, 30.0)
SIZE = (400, 300)
# packages/core/src/lib/appTheme.js and cadgen.kicad.plot.
LIGHT, DARK = (255, 255, 255), (41, 41, 41)
BOARD_BACKGROUND, PAPER = (0x00, 0x10, 0x23), (0xF5, 0xF4, 0xEF)


def near(pixel, expected, tolerance=12):
    return sum(abs(a - b) for a, b in zip(pixel, expected)) <= tolerance


def fitted_rect(width_mm, height_mm, width, height):
    """`fitTransform` over the page box, restated: where the sheet lands, in pixels."""
    scale = min(max(width - 2 * FIT_MARGIN, width * 0.5) / width_mm, max(height - 2 * FIT_MARGIN, height * 0.5) / height_mm)
    left, top = width / 2 - width_mm * scale / 2, height / 2 - height_mm * scale / 2
    return left, top, left + width_mm * scale, top + height_mm * scale


class PcbSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = generated_cad_directory(prefix="pcb-snapshot-")
        cls.folder = Path(cls._tmp.name)
        env = dict(os.environ, CADGEN_DAEMON="0", PYTHONPATH=str(CADGEN_SRC))
        (cls.folder / "blinky.py").write_text(board_source(route_led=False), encoding="utf-8")
        built = subprocess.run([sys.executable, "blinky.py"], cwd=cls.folder, env=env, capture_output=True, text=True, timeout=600)
        if built.returncode != 0:
            raise AssertionError(built.stderr)
        sized = {"width": SIZE[0], "height": SIZE[1]}
        packet = {"jobs": [
            {"input": "blinky.kicad_pcb", "outputs": [{"path": "board-light.png", **sized}]},
            {"input": "blinky.kicad_pcb", "display": {"appearance": "dark"}, "outputs": [{"path": "board-dark.png", **sized}]},
            {"input": "blinky.kicad_sch", "outputs": [{"path": "schematic.png", **sized}]},
        ]}
        (cls.folder / "render.json").write_text(json.dumps(packet), encoding="utf-8")
        from cadgen import pcb

        previous = Path.cwd()
        os.chdir(cls.folder)
        try:
            cls.result = pcb.snapshot(job=cls.folder / "render.json")
        finally:
            os.chdir(previous)
        cls.images = {name: read_png((cls.folder / name).read_bytes()) for name in ("board-light.png", "board-dark.png", "schematic.png")}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_output_is_written_at_the_size_asked_for(self) -> None:
        self.assertTrue(self.result.ok)
        for name, image in self.images.items():
            with self.subTest(output=name):
                self.assertEqual(SIZE, (image.width, image.height))

    def test_the_board_is_fitted_on_its_background_and_the_surround_is_the_appearances(self) -> None:
        left, top, right, bottom = fitted_rect(*BOARD_SIZE, *SIZE)
        for name, surround in (("board-light.png", LIGHT), ("board-dark.png", DARK)):
            with self.subTest(output=name):
                image = self.images[name]
                self.assertTrue(near(image.pixel(0, 0), surround), image.pixel(0, 0))
                painted = [(x, y) for y in range(image.height) for x in range(image.width) if not near(image.pixel(x, y), surround)]
                xs, ys = [x for x, _ in painted], [y for _, y in painted]
                for found, expected in ((min(xs), left), (max(xs), right - 1), (min(ys), top), (max(ys), bottom - 1)):
                    self.assertLessEqual(abs(found - expected), 2, f"the board's box is {(min(xs), min(ys), max(xs), max(ys))}, not {(left, top, right, bottom)}")
                # The rounded outline leaves KiCad's board background in the rectangle's corners.
                self.assertTrue(near(image.pixel(round(left) + 2, round(top) + 2), BOARD_BACKGROUND, 24), image.pixel(round(left) + 2, round(top) + 2))

    def test_a_schematic_sheet_is_on_kicads_paper(self) -> None:
        image = self.images["schematic.png"]
        paper = sum(near(image.pixel(x, y), PAPER) for y in range(0, image.height, 4) for x in range(0, image.width, 4))
        self.assertGreater(paper / ((image.width // 4) * (image.height // 4)), 0.4)

    def test_a_draft_says_it_is_one(self) -> None:
        self.assertTrue(any("1 connection is still unrouted" in warning for warning in self.result.warnings), self.result.warnings)


if __name__ == "__main__":
    unittest.main()
