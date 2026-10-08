"""`cadgen step snapshot --mode section`, through the real door, the real store and the real page.

The cut is cadgen's: an OCCT section of each part's exact BREP (a build-pool job), drawn as a
2D payload the snapshot page paints and written as SVG by cadgen itself. These run the verb on
a tiny assembly built here -- a 20 x 10 x 5 plate at the origin and a radius-5 pin standing at
x = 30 -- and read back what was written:

* the PNG is the cut, framed as a section always was, with the pin a true circle;
* an SVG output is cadgen's, so a job with only SVG outputs never starts a browser;
* focus/hide pick what is cut, and a plane that misses says so.
"""

from __future__ import annotations

import json
import math
import re
import unittest
from unittest import mock

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png

add_repo_path("packages/cadgen/src")

SIZE = (400, 300)
PIN = (30.0, 0.0, 5.0)  # centre x, centre y, radius


def write_assembly(path) -> None:
    from build123d import Compound, Location, Solid
    from cadgen.step_export import export_build123d_step_file

    plate = Solid.make_box(20, 10, 5)
    plate.label = "plate"
    pin = Solid.make_cylinder(PIN[2], 20).moved(Location((PIN[0], PIN[1], 0)))
    pin.label = "pin"
    export_build123d_step_file(Compound(children=[plate, pin], label="asm"), path)


def browser_refused(*_args, **_kwargs):
    raise AssertionError("a browser was started")


class SnapshotSectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="snapshot-section-")
        cls.workspace = cls._roots.cad_root
        write_assembly(cls.workspace / "asm.step")
        import cadgen.step as step_door

        cls.step = step_door
        packet = {"jobs": [
            {"input": "asm.step", "mode": "section", "section": {"plane": "XY", "offset": 2},
             "outputs": [{"path": "cut.png", "width": SIZE[0], "height": SIZE[1]}, {"path": "cut.svg"}]},
            {"input": "asm.step", "mode": "section", "section": {"plane": "XY", "offset": 50},
             "outputs": [{"path": "miss.png", "width": SIZE[0], "height": SIZE[1]}]},
        ]}
        job = cls.workspace / "packet.json"
        job.write_text(json.dumps(packet), encoding="utf-8")
        cls.result = step_door.snapshot(job=job)
        cls.image = read_png((cls.workspace / "cut.png").read_bytes())
        cls.svg = (cls.workspace / "cut.svg").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def screen(self, x: float, y: float) -> tuple[int, int]:
        """Where the page puts model (x, y): the old framing, 12% of the short side clear."""
        min_x, min_y, max_x, max_y = 0.0, -5.0, 35.0, 10.0
        padding = max(20, min(SIZE) * 0.12)
        scale = min((SIZE[0] - 2 * padding) / (max_x - min_x), (SIZE[1] - 2 * padding) / (max_y - min_y))
        return (round(SIZE[0] / 2 + (x - (min_x + max_x) / 2) * scale),
                round(SIZE[1] / 2 - (y - (min_y + max_y) / 2) * scale))

    def test_every_output_was_written_and_the_miss_is_said(self) -> None:
        self.assertTrue(self.result.ok)
        self.assertEqual(["cut.png", "cut.svg", "miss.png"], sorted(file.path.name for file in self.result.files))
        self.assertEqual({"png", "svg"}, {file.kind for file in self.result.files})
        self.assertEqual(SIZE, (self.image.width, self.image.height))
        self.assertEqual(["SECTION XY @ Z=50.000 does not intersect the model; the section is empty"],
                         list(self.result.warnings))

    def test_the_png_is_the_exact_cut_where_the_old_framing_put_it(self) -> None:
        background = self.image.pixel(2, 2)
        self.assertEqual((255, 255, 255), background)
        # Inside the plate and the pin: the grey fill, not the background.
        for point in ((10.0, 5.0), (PIN[0] + 2.5, PIN[1] - 2.5)):
            x, y = self.screen(*point)
            self.assertLess(sum(self.image.pixel(x, y)), 3 * 245, f"{point} is not filled")
        # The pin's outline crosses its exact radius at every angle: a dark ring there. (Its
        # upper half: the cut locator sits over the bottom right corner of a small picture.)
        for angle in range(0, 180, 30):
            radians = math.radians(angle + 15)
            x, y = self.screen(PIN[0] + PIN[2] * math.cos(radians), PIN[1] + PIN[2] * math.sin(radians))
            darkest = min(sum(self.image.pixel(x + dx, y + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            self.assertLess(darkest, 3 * 120, f"no outline at {angle + 15} degrees")

    def test_the_svg_draws_the_pin_as_its_exact_circle(self) -> None:
        self.assertIn('transform="scale(1 -1)"', self.svg)
        outlines = re.findall(r'<path d="([^"]+)"[^>]*stroke-width="3"', self.svg)
        curves = [command for outline in outlines for command in re.findall(r"C ([^A-Z]+)", outline)]
        self.assertEqual(4, len(curves), outlines)
        for curve in curves:
            x, y = map(float, curve.split()[4:6])
            self.assertAlmostEqual(PIN[2], math.hypot(x - PIN[0], y - PIN[1]), places=3)

    def test_an_svg_only_job_is_cadgens_alone_and_focus_picks_what_is_cut(self) -> None:
        from cadgen import snapshot_core

        out = self.workspace / "plate-only.svg"
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start", browser_refused):
            result = self.step.snapshot(self.workspace / "asm.step", out, mode="section", section="XY:2",
                                        focus=("#o1.1",))
        self.assertTrue(result.ok)
        svg = out.read_text(encoding="utf-8")
        self.assertIn("M 0 0 L 20 0 L 20 10 L 0 10 L 0 0 Z", svg.replace("M 0 10 L 0 0 L 20 0 L 20 10 L 0 10 Z",
                                                                         "M 0 0 L 20 0 L 20 10 L 0 10 L 0 0 Z"))
        self.assertNotIn(" C ", svg, "the focused plate has no curve; the pin was cut too")


if __name__ == "__main__":
    unittest.main()
