"""Colours: what an author gives (sRGB hex, 0-255 integers, a build123d Color), what the
document holds (linear), and the rule that makes both routes to a colour agree: a build123d
``Color`` set on a shape stores what ``paint`` stores for the same hex."""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from cadgen.engine import Material
from cadgen.engine import build as engine_build
from cadgen.engine import document
from cadgen.engine.colors import Linear, color, linear, linear_to_srgb, srgb_to_linear

# One step of an 8-bit sRGB channel: the tolerance the two routes are held to.
STEP = 1 / 255


def srgb_bytes(rgba) -> list[float]:
    """Linear channels as the 0-255 sRGB a person reads off them, unrounded."""
    return [linear_to_srgb(channel) * 255 for channel in rgba[:3]]


class LinearTest(unittest.TestCase):
    def test_hex_and_integers_are_srgb_stored_linear(self) -> None:
        grey = linear("#808080")
        self.assertAlmostEqual(grey[0], 0.2158605, places=6)
        self.assertEqual(grey[3], 1.0)
        self.assertEqual(linear((128, 128, 128)), grey)
        self.assertEqual(linear("#888"), linear("#888888"))
        self.assertAlmostEqual(linear("#e6801980")[3], 128 / 255, places=6)
        self.assertEqual(linear((230, 128, 25, 128)), linear("#e6801980"))
        self.assertEqual(linear("#000000")[:3], (0.0, 0.0, 0.0))

    def test_without_alpha_three_channels(self) -> None:
        self.assertEqual(len(linear("#e68019", alpha=False)), 3)
        with self.assertRaisesRegex(ValueError, "emissive is a hex string"):
            linear("#e6801980", "emissive", alpha=False)

    def test_anything_else_is_refused_by_what_it_takes(self) -> None:
        for bad in ((0.5, 0.5, 0.5), (1, 2), (256, 0, 0), (True, 0, 0), "e68019", "#12345", "red", 0xE68019, None,
                    b"#e68019"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "Material color is a hex string"):
                linear(bad, "Material color")

    def test_a_build123d_color_is_srgb_read_linear(self) -> None:
        import build123d as bd

        self.assertEqual(tuple(round(c, 6) for c in linear(bd.Color("#e68019"))),
                         tuple(round(c, 6) for c in linear("#e68019")))
        made = color(linear("#e68019"))
        self.assertEqual([round(c * 255) for c in tuple(made)[:3]], [0xE6, 0x80, 0x19], "the way back is the hex")

    def test_the_transfer_functions_are_inverses(self) -> None:
        for value in (0.0, 0.01, 0.04, 0.2, 0.5, 0.9, 1.0):
            self.assertAlmostEqual(linear_to_srgb(srgb_to_linear(value)), value, places=9)


class MaterialColorTest(unittest.TestCase):
    def test_a_material_takes_what_the_author_sees_and_holds_it_linear(self) -> None:
        made = Material("Paint", color="#808080", emissive=(255, 128, 0), transmission_color="#ffffff")
        self.assertAlmostEqual(made.color[0], 0.2158605, places=6)
        self.assertEqual(made.emissive[:2], (1.0, round(srgb_to_linear(128 / 255), 6)))
        self.assertIsInstance(made.color, Linear)
        self.assertEqual(made.but(roughness=0.1).color, made.color, "a copy keeps the colour")
        self.assertEqual(made.but(color="#ffffff").color, (1.0, 1.0, 1.0, 1.0))
        with self.assertRaisesRegex(ValueError, "Material color is a hex string"):
            Material("Paint", color=(0.5, 0.5, 0.5))
        with self.assertRaisesRegex(ValueError, "Material emissive is a hex string"):
            Material("Paint", emissive=(0.1, 0.2, 0.3))


TWO_ROUTES = """
import build123d as bd
from cadgen.engine import paint, xbf

ORANGE, BLUE = "#e68019", "#2469ac"


@xbf("XBF/by_color.xbf")
def by_color():
    cone = bd.Cone(10, 0, 20)                                    # two faces: the side and the base
    cone.color = bd.Color(ORANGE)
    base = cone.faces().sort_by(bd.Axis.Z)[0]
    paint(cone, base, bd.Color(BLUE))
    cone.label = "cone"
    return cone


@xbf("XBF/by_paint.xbf")
def by_paint():
    cone = bd.Cone(10, 0, 20)
    side, base = cone.faces().sort_by(bd.Axis.Z)[-1], cone.faces().sort_by(bd.Axis.Z)[0]
    paint(cone, side, ORANGE)
    paint(cone, base, BLUE)
    cone.label = "cone"
    return cone


@xbf("XBF/by_hex.xbf")
def by_hex():
    cone = bd.Cone(10, 0, 20)
    cone.color = ORANGE
    paint(cone, cone.faces().sort_by(bd.Axis.Z)[0], (0x24, 0x69, 0xAC))
    cone.label = "cone"
    return cone
"""


class TwoRoutesTest(unittest.TestCase):
    """A build123d ``Color`` set on a shape and the same colour given to ``paint`` as hex store
    the same document colour, within one sRGB step."""

    def test_a_shape_s_color_and_paint_store_the_same_colour(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="engine-colors-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "cone.py").write_text(textwrap.dedent(TWO_ROUTES), encoding="utf-8")
        here = Path.cwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, here)
        for report in engine_build.build(folder / "cone.py", ["by_color", "by_paint", "by_hex"], cwd=folder):
            self.assertTrue(report["ok"], report.get("error"))

        def faces(name: str) -> list[list[float]]:
            """Each face's stored colour, by its ordinal: its paint, else its part's colour."""
            (prototype,) = document.Loaded(folder / "XBF" / f"{name}.xbf").structure()["prototypes"]
            painted = prototype.get("faceColors") or {}
            return [painted.get(str(ordinal)) or prototype["color"] for ordinal in (1, 2)]

        orange, blue = (srgb_bytes(linear(given)) for given in ("#e68019", "#2469ac"))
        routes = {name: faces(name) for name in ("by_color", "by_paint", "by_hex")}
        for name, stored in routes.items():
            with self.subTest(route=name):
                self.assertEqual(len(stored), 2)
                for face in stored:
                    self.assertEqual(face[3], 1.0)
                shown = sorted((srgb_bytes(face) for face in stored), key=lambda rgb: rgb[2])
                for got, wanted in zip(shown, (orange, blue)):
                    for channel, expected in zip(got, wanted):
                        self.assertLessEqual(abs(channel - expected), STEP * 255, (name, got, wanted))
        for face in range(2):
            for channel in range(3):
                values = [routes[name][face][channel] for name in routes]
                self.assertLessEqual(max(map(linear_to_srgb, values)) - min(map(linear_to_srgb, values)), STEP,
                                     f"face {face + 1}, channel {channel}: {values}")


if __name__ == "__main__":
    unittest.main()
