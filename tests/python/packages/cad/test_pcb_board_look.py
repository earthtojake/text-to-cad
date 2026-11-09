"""What a board is made in, and a custom pad's real shape: the board index and the plot payload of a
tiny board with a stack-up and a comb-shaped custom pad (`tests/python/support/kicad_look_board.py`).

A custom pad is its anchor and primitives united, as KiCad makes its copper: a comb is a comb in the
index (`kicad_pcb.read`), in the plot the viewer and `cad kicad_pcb snapshot` draw, and in its mask
opening, never the hull round it. The stack-up (its layers' colours, the copper finish) is carried as the
file names it, for a 3D view to draw the board in. The union under both is unit-tested on its own.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_look_board import LOOK_BOARD, write_look_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad.board_index import read_index  # noqa: E402
from cad.engine.formats.kicad.geometry import area, hull, inside, union  # noqa: E402
from cad.engine.formats.kicad.plot import build_plot  # noqa: E402

# On the board (KiCad's frame, which the plot's sheet shares here: the outline starts at (0, 0)).
BETWEEN_FINGERS = (10.5, 5.5)
INSIDE_THE_BOW = (12.5, 6.0)
ON_A_FINGER = (11.0, 5.9)
ON_THE_SPINE = (10.0, 3.8)
ON_THE_ARC = (12.5, 6.45)


def _covered(point, items) -> bool:
    """Whether a payload's polygons (each with its holes) cover ``point``."""
    return any(inside(point, item["pts"]) and not any(inside(point, hole) for hole in item.get("holes", ())) for item in items)


class UnionTest(unittest.TestCase):
    def test_overlapping_squares_are_one_outline(self) -> None:
        pieces = union([[(0, 0), (2, 0), (2, 2), (0, 2)], [(1, 1), (3, 1), (3, 3), (1, 3)]])
        self.assertEqual(len(pieces), 1)
        self.assertAlmostEqual(area(pieces[0][0]), 7.0)
        self.assertEqual(pieces[0][1], [])

    def test_a_shared_edge_drops_out(self) -> None:
        # The second runs clockwise: a polygon may run either way.
        pieces = union([[(0, 0), (1, 0), (1, 1), (0, 1)], [(1, 0), (1, 1), (2, 1), (2, 0)]])
        self.assertEqual(len(pieces), 1)
        self.assertEqual(sorted(pieces[0][0]), [(0.0, 0.0), (0.0, 1.0), (2.0, 0.0), (2.0, 1.0)])

    def test_pieces_apart_stay_apart_largest_first(self) -> None:
        pieces = union([[(0, 0), (1, 0), (1, 1), (0, 1)], [(5, 0), (7, 0), (7, 2), (5, 2)]])
        self.assertEqual([round(area(outer), 6) for outer, _holes in pieces], [4.0, 1.0])

    def test_a_ring_keeps_its_hole(self) -> None:
        frame = [[(0, 0), (3, 0), (3, 1), (0, 1)], [(0, 2), (3, 2), (3, 3), (0, 3)],
                 [(0, 0), (1, 0), (1, 3), (0, 3)], [(2, 0), (3, 0), (3, 3), (2, 3)]]
        [(outer, holes)] = union(frame)
        self.assertAlmostEqual(area(outer), 9.0)
        self.assertEqual(len(holes), 1)
        self.assertAlmostEqual(area(holes[0]), -1.0)


class CustomPadTest(unittest.TestCase):
    def test_the_index_holds_the_comb_not_its_hull(self) -> None:
        [pad] = read_index(LOOK_BOARD).pads
        polygon = pad.polygon
        for point in (ON_A_FINGER, ON_THE_SPINE, ON_THE_ARC, (10.0, 5.0)):
            self.assertTrue(inside(point, polygon), point)
        for point in (BETWEEN_FINGERS, INSIDE_THE_BOW):
            self.assertFalse(inside(point, polygon), point)
            self.assertTrue(inside(point, hull(polygon)), point)  # what the hull drew
        # The spine (1.6 mm2) and five 0.4 mm fingers 2 mm long with round ends, less their overlaps, and the arc.
        self.assertAlmostEqual(area(polygon), 5.94, delta=0.05)

    def test_the_plot_draws_the_comb_on_its_copper_and_its_mask(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            payload = build_plot(write_look_board(Path(folder)))
        layers = {layer["id"]: layer for layer in payload["sheets"][0]["layers"]}
        for layer in ("F.Cu", "F.Mask"):
            pads = [item for item in layers[layer]["items"] if item.get("ref") == "#S1.1" and item["t"] == "poly"]
            self.assertTrue(pads, layer)
            for point in (ON_A_FINGER, ON_THE_SPINE, ON_THE_ARC):
                self.assertTrue(_covered(point, pads), (layer, point))
            for point in (BETWEEN_FINGERS, INSIDE_THE_BOW):
                self.assertFalse(_covered(point, pads), (layer, point))
        # Its clearance outline (KiCad's hairline on the front copper) is the comb grown by 0.2 mm, given as rings: the
        # 0.6 mm gap between two fingers stays open, which growing the outline as a convex one would not.
        [copper] = [item for item in layers["F.Cu"]["items"] if item.get("ref") == "#S1.1" and item["t"] == "poly"]
        self.assertEqual(copper["clearance"], 0.2)
        [grown] = copper["grown"]
        self.assertFalse(inside(BETWEEN_FINGERS, grown))
        self.assertTrue(inside((10.5, 3.65), grown), "0.15 mm above the spine")
        [pad] = payload["board"]["pads"]
        self.assertFalse(inside(BETWEEN_FINGERS, pad["polygon"]))


class StackupTest(unittest.TestCase):
    def test_the_index_and_the_payload_carry_the_stackup_as_written(self) -> None:
        stackup = read_index(LOOK_BOARD).stackup
        self.assertEqual(stackup.finish, "ENIG")
        colours = {layer.name: layer.color for layer in stackup.layers}
        self.assertEqual(colours, {"F.SilkS": "White", "F.Mask": "Black", "F.Cu": None, "dielectric 1": None,
                                   "B.Cu": None, "B.Mask": "Black", "B.SilkS": "White"})
        with tempfile.TemporaryDirectory() as folder:
            board = build_plot(write_look_board(Path(folder)))["board"]
        self.assertEqual(board["stackup"]["finish"], "ENIG")
        self.assertEqual(board["stackup"]["layers"][1], {"name": "F.Mask", "type": "Top Solder Mask", "color": "Black", "thickness": 0.01})
        self.assertEqual(board["stackup"]["layers"][3]["material"], "FR4")

    def test_a_board_without_a_stackup_carries_none(self) -> None:
        start, end = LOOK_BOARD.index("    (stackup"), LOOK_BOARD.index("    (pad_to_mask_clearance")
        bare = LOOK_BOARD[:start] + LOOK_BOARD[end:]
        self.assertIsNone(read_index(bare).stackup)
        self.assertNotIn("stackup", read_index(bare).as_json())


if __name__ == "__main__":
    unittest.main()
