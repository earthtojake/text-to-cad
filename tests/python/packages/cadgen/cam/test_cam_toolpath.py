"""FreeCAD's path commands read as moves: lines, arcs within the chord, drilling cycles, and a word cadgen cannot
read refused rather than skipped."""

from __future__ import annotations

import math
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.cam import toolpath  # noqa: E402

START = (0.0, 0.0, 10.0)


class Read(unittest.TestCase):
    def test_rapids_and_feeds_are_timed_at_their_rates(self):
        moves = toolpath.read([(0, [["G0", {"X": 30.0}], ["G1", {"Z": 0.0, "F": 2.0}], ["(a comment)", {}]])],
                              START, rapid_mm_min=1800.0)
        self.assertEqual([[0, 0, 10], [30, 0, 10], [30, 0, 0]], moves.points.tolist())
        self.assertEqual([True, True, False], moves.rapid.tolist())
        self.assertAlmostEqual(1.0 + 5.0, moves.t[-1])          # 30 mm at 30 mm/s, 10 mm at 2 mm/s (FreeCAD's mm/s)

    def test_an_arc_is_sampled_on_its_circle_within_the_chord(self):
        moves = toolpath.read([(3, [["G0", {"X": 10.0, "Y": 0.0, "Z": 0.0}],
                                    ["G3", {"X": -10.0, "Y": 0.0, "I": -10.0, "J": 0.0, "F": 5.0}]])], START, 3000.0)
        arc = moves.points[2:]
        radii = [math.hypot(x, y) for x, y, _ in arc]
        self.assertTrue(all(abs(r - 10.0) < 1e-9 for r in radii))
        self.assertTrue(all(y >= -1e-9 for _, y, _ in arc))    # counter-clockwise from +X: over the top
        gaps = [math.dist(a, b) for a, b in zip(arc, arc[1:])]
        sagitta = 10.0 - math.sqrt(100.0 - (max(gaps) / 2) ** 2)
        self.assertLessEqual(sagitta, toolpath.CHORD_MM + 1e-9)
        self.assertEqual({3}, set(moves.op.tolist()))

    def test_a_clockwise_arc_goes_under(self):
        moves = toolpath.read([(0, [["G0", {"X": 10.0}], ["G2", {"X": -10.0, "I": -10.0, "F": 5.0}]])], START, 3000.0)
        self.assertTrue(all(y <= 1e-9 for _, y, _ in moves.points[2:]))

    def test_a_drilling_cycle_goes_to_r_feeds_to_z_and_returns(self):
        moves = toolpath.read([(1, [["G98", {}], ["G81", {"X": 5.0, "Y": 5.0, "Z": -4.0, "R": 2.0, "F": 1.0}],
                                    ["G81", {"X": 9.0, "Y": 5.0, "Z": -4.0, "R": 2.0, "F": 1.0}], ["G80", {}]])],
                              START, 3000.0)
        self.assertEqual([[0, 0, 10], [5, 5, 10], [5, 5, 2], [5, 5, -4], [5, 5, 10],
                          [9, 5, 10], [9, 5, 2], [9, 5, -4], [9, 5, 10]], moves.points.tolist())
        self.assertEqual([True, True, True, False, True, True, True, False, True], moves.rapid.tolist())
        g99 = toolpath.read([(1, [["G99", {}], ["G81", {"X": 5.0, "Z": -4.0, "R": 2.0, "F": 1.0}]])], START, 3000.0)
        self.assertEqual([5, 0, 2], g99.points[-1].tolist())    # G99: back to R

    def test_a_word_cadgen_cannot_check_is_refused(self):
        for name, words in (("G91", {}), ("G18", {}), ("G1", {"X": 5.0})):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    toolpath.read([(0, [[name, words]])], START, 3000.0)


if __name__ == "__main__":
    unittest.main()
