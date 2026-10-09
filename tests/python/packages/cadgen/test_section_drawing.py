"""A section's drawing is the exact cut, placed: ``cadgen.section_drawing``.

Kernel-free. The component cuts are written to a throwaway store as the build
pool would write them (``cadgen.store.sections``), so what is tested is the
placing, the projection, the framing and the payload -- each against numbers
worked out by hand.
"""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import section_drawing as drawing  # noqa: E402
from cadgen.store import sections  # noqa: E402

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
COMPONENT = {"kind": "native", "codec": "bintools-v4", "contentHash": "c" * 64, "faceColors": {}, "brepObject": "b" * 64}
# A disc of radius 10 about the local origin, in the local XY plane, and a 20 x 10 rectangle:
# each a solid's cut, so each bounds material.
DISC = {"loops": [{"closed": True, "filled": True, "edges": [{"arc": {
    "center": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0], "radius": 10.0, "start": [10.0, 0.0, 0.0],
    "sweep": 2 * math.pi}}]}]}
SQUARE = {"loops": [{"closed": True, "filled": True, "edges": [
    {"line": [[0.0, 0.0, 0.0], [20.0, 0.0, 0.0]]}, {"line": [[20.0, 0.0, 0.0], [20.0, 10.0, 0.0]]},
    {"line": [[20.0, 10.0, 0.0], [0.0, 10.0, 0.0]]}, {"line": [[0.0, 10.0, 0.0], [0.0, 0.0, 0.0]]}]}]}


def translated(x=0.0, y=0.0, z=0.0, *, mirror_x=False):
    matrix = list(IDENTITY)
    matrix[0] = -1.0 if mirror_x else 1.0
    matrix[3], matrix[7], matrix[11] = x, y, z
    return matrix


class SectionDrawingTests(unittest.TestCase):
    def setUp(self) -> None:
        store = tempfile.TemporaryDirectory(prefix="section-drawing-store-")
        self.addCleanup(store.cleanup)
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": store.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.entry = sections.component_entry(dict(COMPONENT))

    def place(self, cut, matrix, *, plane="XY", offset=0.0):
        """Store ``cut`` as the component's section by the plane this placement sees."""
        normal = drawing.SECTION_FRAMES[plane][0]
        local_normal, local_offset = drawing.occurrence_plane(matrix, normal, offset)
        sections.write(sections.section_key(self.entry, local_normal, local_offset), {"schemaVersion": 1, **cut})
        return {"id": "o1", "name": "part", "component": "c0", "transform": matrix,
                "bbox": {"min": [-10.0, -10.0, -5.0], "max": [10.0, 10.0, 5.0]}}

    def draw(self, rows, **options):
        descriptor = {"units": "mm", "components": {"c0": COMPONENT}}
        options = {"plane": "XY", "offset": 0.0, "size": (800, 600), **options}
        with mock.patch("cadgen.daemon.artifacts.resolve_artifacts", side_effect=AssertionError("cut again")):
            return drawing.section_drawing(descriptor, rows, **options)

    def test_the_world_plane_seen_from_a_placed_part(self) -> None:
        # A part turned 90 degrees about Y and moved to x=40: world Z is its local -X.
        turned = [0.0, 0.0, 1.0, 40.0, 0.0, 1.0, 0.0, 5.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        normal, offset = drawing.occurrence_plane(turned, (0.0, 0.0, 1.0), 2.0)
        self.assertEqual((-1.0, 0.0, 0.0), tuple(value + 0.0 for value in normal))
        self.assertEqual(2.0, offset)
        # A plane reached through rotation noise is the same cut, and the same entry.
        noisy = list(turned)
        noisy[0] = noisy[10] = 2.22044604925e-16
        self.assertEqual(sections.section_key(self.entry, *drawing.occurrence_plane(turned, (0, 0, 1), 2.0)),
                         sections.section_key(self.entry, *drawing.occurrence_plane(noisy, (0, 0, 1), 2.0)))

    def test_a_circle_is_drawn_as_beziers_of_its_exact_centre_and_radius(self) -> None:
        section = self.draw([self.place(DISC, translated(30.0, 5.0))])
        [outline] = [p for p in section.payload["primitives"] if p["layer"] == "section-outline"]
        curves = [command for command in outline["geometry"] if command[0] == "C"]
        self.assertEqual(4, len(curves))
        for command in curves:
            end = command[5:7]
            self.assertAlmostEqual(10.0, math.hypot(end[0] - 30.0, end[1] - 5.0), places=4)
        self.assertEqual(["Z"], outline["geometry"][-1])
        self.assertEqual([], section.warnings)
        self.assertEqual("XY @ Z=0.000", section.label)

    def test_a_mirrored_placement_turns_its_arcs_the_other_way(self) -> None:
        half = {"loops": [{"closed": False, "edges": [{"arc": {
            "center": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0], "radius": 10.0, "start": [10.0, 0.0, 0.0],
            "sweep": math.pi / 2}}]}]}
        upright = self.draw([self.place(half, translated())])
        mirrored = self.draw([self.place(half, translated(mirror_x=True))])

        def end(section):
            [outline] = [p for p in section.payload["primitives"] if p["layer"] == "section-outline"]
            return outline["geometry"][-1][5:7]

        # +90 degrees from (10, 0) is (0, 10); mirrored in X, the start is (-10, 0) and the
        # quarter turn runs clockwise, to (0, 10) again -- never down to (0, -10).
        self.assertEqual([0, 10], end(upright))
        self.assertEqual([0, 10], end(mirrored))
        self.assertFalse([p for p in mirrored.payload["primitives"] if p["type"] == "filled-paths"],
                         "an open chain is outlined, never filled")

    def test_the_hatch_lies_inside_the_cut(self) -> None:
        section = self.draw([self.place(SQUARE, translated())])
        [hatch] = [p for p in section.payload["primitives"] if p["layer"] == "section-hatch"]
        self.assertGreater(len(hatch["geometry"]), 5)
        for x0, y0, x1, y1 in hatch["geometry"]:
            self.assertAlmostEqual(1.0, (y1 - y0) / (x1 - x0), places=3)  # 45 degrees
            for x, y in ((x0, y0), (x1, y1)):
                on_edge = min(abs(x), abs(x - 20), abs(y), abs(y - 10))
                self.assertLess(on_edge, 1e-3, f"({x}, {y}) is not on the square's boundary")

    def test_the_drawing_is_framed_as_the_cut_always_was(self) -> None:
        section = self.draw([self.place(SQUARE, translated())], size=(800, 600))
        # The old framing: 12% of the short side clear (72 px), the box fitted inside.
        scale = min((800 - 144) / 20, (600 - 144) / 10)
        min_x, min_y, max_x, max_y = section.payload["bounds"]
        # The page's own fit leaves 16 px; the padded bounds fill what it leaves at that scale.
        self.assertAlmostEqual((800 - 32) / scale, max_x - min_x, places=3)
        self.assertAlmostEqual((600 - 32) / scale, max_y - min_y, places=3)
        self.assertAlmostEqual(10.0, (min_x + max_x) / 2, places=3)
        self.assertAlmostEqual(5.0, (min_y + max_y) / 2, places=3)
        layers = [primitive["layer"] for primitive in section.payload["primitives"]]
        self.assertEqual(["section-fill", "section-hatch", "section-centerline", "section-outline"], layers)

    def test_a_closed_loop_that_bounds_no_material_is_outlined_never_filled(self) -> None:
        # A sheet's cut can close on itself (a capless tube cut across is a circle), and there
        # is nothing inside it to fill or hatch.
        ring = {"loops": [{**DISC["loops"][0], "filled": False}]}
        section = self.draw([self.place(ring, translated())])
        layers = [primitive["layer"] for primitive in section.payload["primitives"]]
        self.assertEqual(["section-centerline", "section-outline"], layers)
        [outline] = [p for p in section.payload["primitives"] if p["layer"] == "section-outline"]
        self.assertEqual(["Z"], outline["geometry"][-1])
        self.assertNotIn('fill-rule="evenodd"', section.svg)

    def test_a_plane_that_misses_is_said_and_draws_nothing(self) -> None:
        section = self.draw([self.place({"loops": []}, translated(), offset=50.0)], offset=50.0)
        self.assertIsNone(section.payload["bounds"])
        self.assertEqual([], section.payload["primitives"])
        self.assertEqual(["SECTION XY @ Z=50.000 cuts no material; the section is empty"],
                         section.warnings)

    def test_the_svg_is_the_payload_drawn_y_up(self) -> None:
        section = self.draw([self.place(SQUARE, translated())])
        self.assertIn('transform="scale(1 -1)"', section.svg)
        self.assertIn('fill-rule="evenodd"', section.svg)
        self.assertIn('vector-effect="non-scaling-stroke"', section.svg)
        self.assertIn("M 0 0 L 20 0 L 20 10 L 0 10 L 0 0 Z", section.svg)

    def test_the_locator_is_where_the_cut_sits_across_the_parts(self) -> None:
        rows = [{"bbox": {"min": [0, 0, -5], "max": [1, 1, 15]}}]
        self.assertEqual(0.25, drawing.locator_fraction(rows, "XY", 0.0))
        self.assertEqual(1.0, drawing.locator_fraction(rows, "XY", 99.0))


if __name__ == "__main__":
    unittest.main()
