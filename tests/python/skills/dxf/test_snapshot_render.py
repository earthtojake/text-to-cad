"""`cadgen dxf snapshot` draws the picture the CAD Viewer draws.

The only test in this repo that renders a real DXF through the real headless
runtime and reads the PIXELS back. That is the point: every other assertion
about this door is about the request, and a render that is accepted, runs, and
writes a blank image passes all of them.

What it pins is the shared contract, not the implementation:

* the drawing is FITTED and centred, with the viewer's own gutter;
* the default pen (`color: null`) is the appearance's foreground on the
  appearance's background, so light and dark flip the ink;
* a pen of its own survives (the red circle is red in both);
* an even-odd fill really has a hole in it (the hatch island is background);
* the PNG is exactly the size that was asked for.

The last case is the PARITY case, and it uses the SAME fixture the viewer's
browser test serves (`packages/ui/src/renderers/dxf/__fixtures__/sample.dxf`):
one drawing, two renderers, key pixels at positions computed from
`@hardcore/core/lib/drawing2d`'s fit maths, restated here. If the CLI and the
pane ever disagree about the frame, one of the two suites says so.

One browser, one packet: a `--job` file renders every case in a single run.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path, repo_path
from tests.python.support.png import PngImage, read_png

add_repo_path("packages/cadgen/src")

# What the browser test serves, and what `make_fixture.py` wrote it from:
# default-pen line work on a 100 x 60 mm sheet, a RED circle at (22, 40) r 12,
# a blue hatch (58, 28)-(92, 52) with an island (68, 34)-(82, 46), text, and a
# bulged polyline. A committed fixture, not a corpus model.
FIXTURE_DXF = repo_path("packages/ui/src/renderers/dxf/__fixtures__/sample.dxf")
FIXTURE_BOUNDS = (0.0, 0.0, 100.0, 60.0)

# packages/core/src/lib/drawing2d/transform.js: DRAWING_FIT_MARGIN.
FIT_MARGIN = 16
# The two colours a drawing is painted with, from
# packages/core/src/lib/appTheme.js: APP_THEME_COLORS.
LIGHT = {"background": (255, 255, 255), "foreground": (23, 23, 23)}
DARK = {"background": (41, 41, 41), "foreground": (250, 250, 250)}


def fit_transform(bounds, width, height):
    """`fitTransform(bounds, width, height)`, restated in Python.

    The parity this file exists for is about WHERE things land, so the maths is
    written out rather than approximated: a test that only checked "something
    was drawn" would pass through any reframing.
    """
    min_x, min_y, max_x, max_y = bounds
    span_x, span_y = abs(max_x - min_x), abs(max_y - min_y)
    usable_width = max(width - 2 * FIT_MARGIN, width * 0.5)
    usable_height = max(height - 2 * FIT_MARGIN, height * 0.5)
    scale_x = usable_width / span_x if span_x > 0 else float("inf")
    scale_y = usable_height / span_y if span_y > 0 else float("inf")
    scale = min(scale_x, scale_y)
    centre_x, centre_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    return scale, width / 2 - centre_x * scale, height / 2 + centre_y * scale


def model_to_screen(transform, x, y):
    scale, offset_x, offset_y = transform
    return x * scale + offset_x, -y * scale + offset_y


def window(image: PngImage, point, radius=3):
    """Every pixel within `radius` of a model point's screen position.

    A hairline is 1.25 CSS pixels wide and lands wherever sub-pixel rounding
    puts it, so an assertion reads a small neighbourhood rather than one pixel
    and would still be exact about a stroke drawn somewhere else entirely.
    """
    x, y = int(round(point[0])), int(round(point[1]))
    return [
        image.pixel(column, row)
        for row in range(max(0, y - radius), min(image.height, y + radius + 1))
        for column in range(max(0, x - radius), min(image.width, x + radius + 1))
    ]


def luminance(pixel):
    return pixel[0] + pixel[1] + pixel[2]


def near(pixel, expected, tolerance=12):
    return sum(abs(a - b) for a, b in zip(pixel, expected)) <= tolerance


def ink_box(image: PngImage):
    """The box around everything that is not the image's own background."""
    backdrop = image.pixel(0, 0)
    min_x, min_y, max_x, max_y, painted = image.width, image.height, -1, -1, 0
    for row in range(image.height):
        for column in range(image.width):
            if near(image.pixel(column, row), backdrop):
                continue
            painted += 1
            min_x, max_x = min(min_x, column), max(max_x, column)
            min_y, max_y = min(min_y, row), max(max_y, row)
    return {
        "minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y, "painted": painted,
        "centreX": (min_x + max_x) / 2, "centreY": (min_y + max_y) / 2,
        "width": max_x - min_x, "height": max_y - min_y, "backdrop": backdrop,
    }


PLAIN_BOUNDS = (0.0, 0.0, 100.0, 50.0)
PLAIN_SIZE = (400, 200)
FIXTURE_SIZE = (480, 300)


def write_plain_drawing(path: Path) -> None:
    """A 100 x 50 rectangle on the default pen, with one RED rule across it.

    Written here rather than copied, so the pixel assertions below are about
    coordinates this file chose: the rectangle is exactly the drawing's bounds,
    and the rule is the one thing inside it.
    """
    import ezdxf

    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4  # millimetres
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    modelspace.add_line((10, 10), (90, 10), dxfattribs={"color": 1})  # ACI 1 = red
    document.saveas(path)


class DxfSnapshotRenderTests(unittest.TestCase):
    """One browser launch; every case is a job in the same packet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="dxf-snapshot-render-")
        cls.workspace = cls._roots.cad_root
        write_plain_drawing(cls.workspace / "plain.dxf")
        shutil.copyfile(FIXTURE_DXF, cls.workspace / "sample.dxf")

        packet = {
            "jobs": [
                {
                    "input": "plain.dxf",
                    "outputs": [{"path": "plain-light.png", "width": PLAIN_SIZE[0], "height": PLAIN_SIZE[1]}],
                },
                {
                    "input": "plain.dxf",
                    "display": {"appearance": "dark"},
                    "outputs": [{"path": "plain-dark.png", "width": PLAIN_SIZE[0], "height": PLAIN_SIZE[1]}],
                },
                {
                    "input": "sample.dxf",
                    "outputs": [{"path": "sample.png", "width": FIXTURE_SIZE[0], "height": FIXTURE_SIZE[1]}],
                },
            ]
        }
        job_path = cls.workspace / "render.json"
        job_path.write_text(json.dumps(packet), encoding="utf-8")

        import cadgen.dxf as dxf_door

        cls.result = dxf_door.snapshot(job=job_path)
        cls.images = {
            name: read_png((cls.workspace / name).read_bytes())
            for name in ("plain-light.png", "plain-dark.png", "sample.png")
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_every_declared_output_was_written(self) -> None:
        self.assertTrue(self.result.ok)
        self.assertEqual(
            ["plain-dark.png", "plain-light.png", "sample.png"],
            sorted(file.path.name for file in self.result.files),
        )

    def test_the_png_is_exactly_the_size_that_was_asked_for(self) -> None:
        for name, size in (
            ("plain-light.png", PLAIN_SIZE), ("plain-dark.png", PLAIN_SIZE), ("sample.png", FIXTURE_SIZE)
        ):
            with self.subTest(output=name):
                image = self.images[name]
                self.assertEqual(size, (image.width, image.height))

    def test_the_drawing_is_fitted_and_centred_in_the_image(self) -> None:
        image = self.images["plain-light.png"]
        box = ink_box(image)
        self.assertGreater(box["painted"], 0, "nothing was drawn")
        self.assertLessEqual(abs(box["centreX"] - image.width / 2), 2)
        self.assertLessEqual(abs(box["centreY"] - image.height / 2), 2)
        # The rectangle IS the bounds, so the ink box is the fitted box: the
        # gutter on the constraining axis, and the drawing's own aspect.
        transform = fit_transform(PLAIN_BOUNDS, *PLAIN_SIZE)
        left, bottom = model_to_screen(transform, PLAIN_BOUNDS[0], PLAIN_BOUNDS[1])
        right, top = model_to_screen(transform, PLAIN_BOUNDS[2], PLAIN_BOUNDS[3])
        self.assertLessEqual(abs(box["minX"] - left), 2, f"left edge at {box['minX']}, expected {left}")
        self.assertLessEqual(abs(box["maxX"] - right), 2, f"right edge at {box['maxX']}, expected {right}")
        self.assertLessEqual(abs(box["minY"] - top), 2, f"top edge at {box['minY']}, expected {top}")
        self.assertLessEqual(abs(box["maxY"] - bottom), 2, f"bottom edge at {box['maxY']}, expected {bottom}")

    def test_the_default_pen_flips_with_the_appearance_and_a_real_pen_does_not(self) -> None:
        transform = fit_transform(PLAIN_BOUNDS, *PLAIN_SIZE)
        top_edge = model_to_screen(transform, 50, 50)     # default pen (ACI 7)
        red_rule = model_to_screen(transform, 50, 10)     # ACI 1
        empty = model_to_screen(transform, 50, 30)        # nothing is drawn here

        for name, theme in (("plain-light.png", LIGHT), ("plain-dark.png", DARK)):
            image = self.images[name]
            with self.subTest(appearance=name):
                self.assertTrue(
                    near(image.pixel(2, 2), theme["background"]),
                    f"the margin is {image.pixel(2, 2)}, not the appearance's background",
                )
                self.assertTrue(
                    any(near(pixel, theme["background"]) for pixel in window(image, empty)),
                    "a part of the sheet with no geometry is not the background",
                )
                # The hairline's core: the pixel furthest from the background in
                # luminance — an antialiased skirt is not it. A 1.25 px stroke never
                # fully covers a device pixel, so the ink is a BLEND of the pen and
                # the background rather than the pen itself. What must hold is that
                # it is neutral grey (both colours are) and that it moved the right
                # WAY: darker than white, lighter than charcoal.
                pick = min if theme is LIGHT else max
                pen = pick(window(image, top_edge), key=luminance)
                self.assertLessEqual(max(pen) - min(pen), 4, f"the default pen drew {pen}, which is not neutral")
                towards = luminance(theme["foreground"]) - luminance(theme["background"])
                moved = luminance(pen) - luminance(theme["background"])
                self.assertGreater(
                    moved * towards, 0,
                    f"the default pen drew {pen}: it did not move towards {theme['foreground']} "
                    f"from {theme['background']}",
                )
                self.assertGreater(
                    abs(moved), 300,
                    f"the default pen drew {pen}, barely distinguishable from the background",
                )
                red = max(window(image, red_rule), key=lambda pixel: pixel[0] - (pixel[1] + pixel[2]) / 2)
                self.assertGreater(red[0], 180, f"the red rule drew {red}")
                self.assertLess(max(red[1], red[2]), 90, f"the red rule drew {red}")

    def test_the_committed_viewer_fixture_lands_where_the_pane_puts_it(self) -> None:
        image = self.images["sample.png"]
        transform = fit_transform(FIXTURE_BOUNDS, *FIXTURE_SIZE)

        self.assertTrue(near(image.pixel(2, 2), LIGHT["background"]))

        # The sheet outline: default pen, so the appearance's foreground.
        border = min(window(image, model_to_screen(transform, 50, 60)), key=luminance)
        self.assertLess(luminance(border), luminance(LIGHT["background"]) - 200, f"the sheet outline drew {border}")

        # The red circle at (22, 40) r 12 — read on its leftmost point.
        circle = max(
            window(image, model_to_screen(transform, 10, 40)),
            key=lambda pixel: pixel[0] - (pixel[1] + pixel[2]) / 2,
        )
        self.assertGreater(circle[0], 180, f"the circle drew {circle}")
        self.assertLess(max(circle[1], circle[2]), 90, f"the circle drew {circle}")

        # The hatch: solid inside its outer ring, and a REAL hole inside the
        # island. Even-odd filling is the whole reason the payload's
        # `filled-paths` are filled one at a time.
        solid = image.pixel(*(int(round(value)) for value in model_to_screen(transform, 62, 31)))
        self.assertGreater(solid[2], 150, f"the hatch drew {solid}")
        self.assertLess(max(solid[0], solid[1]), 90, f"the hatch drew {solid}")
        hole = window(image, model_to_screen(transform, 75, 40), radius=2)
        self.assertTrue(
            all(near(pixel, LIGHT["background"]) for pixel in hole),
            f"the hatch island is filled, not a hole: {sorted(set(hole))[:4]}",
        )


if __name__ == "__main__":
    unittest.main()
