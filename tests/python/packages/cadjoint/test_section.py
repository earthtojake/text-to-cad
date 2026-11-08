"""``cad.cadjoint.section``: a plane through a cadjoint field, drawn as a PNG, and what it shows.

The section says what it drew, so its numbers are checked against the construction: the space-frame
node's wall is 2 mm (``fixtures/space_frame_node.py``), so the deepest point inside any plane through it
is 1 mm from the surface; a plane beside the clevis bracket (``fixtures/clevis_bracket.py``, 52 mm tall)
never crosses its surface.
"""

from __future__ import annotations

import os
import runpy
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cad.cadjoint import Section, section

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _scene(name: str):
    return runpy.run_path(str(FIXTURES / f"{name}.py"), run_name="__fixture__")["scene"]


class SectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="cadjoint-section-"))
        self.addCleanup(__import__("shutil").rmtree, self.folder, True)

    def test_the_node_wall_reads_one_millimetre_deep(self) -> None:
        out = self.folder / "node.png"
        drawn = section(_scene("space_frame_node"), out, axis="y", at=0.0, pixels=400)
        self.assertIsInstance(drawn, Section)
        png = out.read_bytes()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual(max(width, height), 400)
        self.assertEqual((drawn.path, drawn.plane, drawn.across, drawn.up), (out.resolve(), "y = 0", "x", "z"))
        self.assertTrue(drawn.crosses_surface)
        self.assertAlmostEqual(drawn.field_range[0], -1.0, delta=0.02)
        self.assertEqual(sorted(os.listdir(self.folder)), ["node.png"], "the picture alone, no partial file")

    def test_a_plane_beside_the_part_never_crosses_its_surface(self) -> None:
        drawn = section(_scene("clevis_bracket"), self.folder / "air.png", axis="z", at=80.0, pixels=128)
        self.assertFalse(drawn.crosses_surface)
        self.assertGreater(drawn.field_range[0], 0.0)

    def test_a_flat_field_on_a_contour_value_is_not_filled(self) -> None:
        """A plane along a wall's mid-plane can read one distance everywhere: no contour has a place."""
        from cad.cadjoint._section import colour

        rgb = colour(np.full((40, 40), -3.0), pixel=0.1, step=1.0)
        self.assertEqual(len(np.unique(rgb.reshape(-1, 3), axis=0)), 1)

    def test_bad_arguments_are_refused_before_anything_is_drawn(self) -> None:
        from cadjoint.construction import Solid

        ball = Solid.sphere(radius=10.0, name="ball")
        out = self.folder / "x.png"
        for options, said in (({"bounds": (10, 0, 0, 10)}, "U0 < U1 and V0 < V1"),
                              ({"axis": "w"}, "axis is one of x, y, z"),
                              ({"pixels": 32}, "pixels is a whole number from 64 to 4096"),
                              ({"step": 0}, "step is the contours' spacing"),
                              ({"bounds": (0, 0, 1)}, r"bounds is \(u0, v0, u1, v1\)")):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, said):
                section(ball, out, **options)
        with self.assertRaisesRegex(ValueError, "into a .png, not x.jpg"):
            section(ball, self.folder / "x.jpg")
        with self.assertRaisesRegex(TypeError, "takes a cadjoint field"):
            section("ball", out)
        self.assertEqual(os.listdir(self.folder), [])


if __name__ == "__main__":
    unittest.main()
