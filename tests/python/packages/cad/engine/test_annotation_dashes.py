"""A stroke's line style in a snapshot: ``dash`` is checked where a still reads it, and a dashed or dotted stroke
is painted in runs of ink along its line (``render/dashes.py``), as the viewer draws it; a mark without one is
solid, as every mark written before there were line styles."""

from __future__ import annotations

import json
import unittest

import numpy as np

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine import snapshot  # noqa: E402
from cad.engine.render import drawing  # noqa: E402
from cad.engine.render.dashes import dash_pattern, dash_runs  # noqa: E402

LINE = [4, 8, 0, 60, 8, 0]


def painted(dash=None):
    frame = np.zeros((16, 64, 3), np.uint8)
    mark = {"kind": "stroke", "points": LINE, "color": "#ffffff", "width": 2, **({"dash": dash} if dash else {})}
    drawing.paint_ink(frame, [mark], lambda p: (float(p[0]), float(p[1])), 1.0)
    return frame[8, 4:61, 0] > 128


class AnnotationDashesTest(unittest.TestCase):
    def test_a_line_style_is_checked_and_an_old_mark_reads_as_solid(self):
        for dash in ("solid", "dashed", "dotted"):
            found = snapshot.parse_annotation(json.dumps({"marks": [{"kind": "stroke", "points": LINE, "color": "#ff0000", "width": 2, "dash": dash}]}))
            self.assertEqual(found["marks"][0]["dash"], dash)
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(json.dumps({"marks": [{"kind": "stroke", "points": LINE, "color": "#ff0000", "width": 2, "dash": "wavy"}]}))
        self.assertTrue(painted().all(), "no dash: one unbroken line")

    def test_dashed_and_dotted_strokes_are_runs_of_ink_along_the_line(self):
        solid, dashed, dotted = painted(), painted("dashed"), painted("dotted")
        # Dashes of 8px with 6px between; dots 4px apart: gaps a solid line has none of.
        self.assertGreater(solid.sum(), dashed.sum())
        self.assertGreater(dashed.sum(), dotted.sum())
        self.assertGreater(np.count_nonzero(np.diff(dashed.astype(int))), 6)
        self.assertGreater(np.count_nonzero(np.diff(dotted.astype(int))), 12)

    def test_the_pattern_runs_on_unbroken_from_segment_to_segment(self):
        points = np.array([[0, 0], [5, 0], [20, 0]], float)
        runs = dash_runs(points, [5, 15], dash_pattern("dashed", 2))
        self.assertEqual([(run[0][0], run[-1][0]) for run, _ in runs], [(0.0, 8.0), (14.0, 20.0)])


if __name__ == "__main__":
    unittest.main()
