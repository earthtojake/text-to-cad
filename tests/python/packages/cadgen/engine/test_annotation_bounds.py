"""A still's annotation must not size the renderer's rasters without bound. parse_annotation
refuses pathological mark fields; the OCCT text path caps its canvas; the DXF ink path clips
each mark's mask to the frame. Covers snapshot.parse_annotation, render.text.text_canvas and
render.drawing.paint_ink."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import snapshot  # noqa: E402
from cadgen.engine.render import drawing, text  # noqa: E402

TEXT_POINTS = [0, 0, 0, 1, 0, 0, 1, -1, 0, 0, -1, 0]


def annotation(mark):
    return json.dumps({"marks": [{"kind": "text", "points": TEXT_POINTS, "color": "#ff0000", **mark}]})


class ParseAnnotationBoundsTest(unittest.TestCase):
    def test_a_sane_text_mark_is_accepted(self):
        found = snapshot.parse_annotation(annotation({"text": "hello", "fontPx": 14}))
        self.assertEqual(len(found["marks"]), 1)

    def test_an_enormous_font_is_refused(self):
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(annotation({"text": "MMMM", "fontPx": 3000}))

    def test_a_non_finite_font_is_refused(self):
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(annotation({"text": "x", "fontPx": float("inf")}))

    def test_too_many_lines_are_refused(self):
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(annotation({"text": "\n" * 200000 + "x", "fontPx": 14}))

    def test_an_enormous_stroke_width_is_refused(self):
        payload = json.dumps({"marks": [{"kind": "stroke", "points": [0, 0, 0, 1, 1, 0],
                                         "color": "#00ff00", "width": 1e9}]})
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(payload)

    def test_too_many_marks_are_refused(self):
        many = {"marks": [{"kind": "stroke", "points": [0, 0, 0, 1, 1, 0], "color": "#00ff00"}
                          for _ in range(snapshot.MARK_MAX + 1)]}
        with self.assertRaises(snapshot.SnapshotRefused):
            snapshot.parse_annotation(json.dumps(many))


class TextCanvasBoundTest(unittest.TestCase):
    def test_a_sane_label_rasterises(self):
        out = text.text_canvas("hello", 14.0, "#ff0000")
        self.assertEqual(out.ndim, 3)

    def test_an_oversized_canvas_is_refused_before_allocation(self):
        # The parse gate already rejects fontPx 3000, but text_canvas is the renderer's own backstop.
        with self.assertRaises(ValueError):
            text.text_canvas("M" * 20, 3000.0, "#ff0000")


class InkMaskClipTest(unittest.TestCase):
    def test_a_far_reaching_stroke_allocates_no_mask_larger_than_the_frame(self):
        from PIL import Image

        real_new = Image.new
        seen = []

        def recording_new(mode, size, *args, **kwargs):
            seen.append(size)
            # refuse to actually allocate anything huge, so a regression fails loudly not slowly
            if size[0] * size[1] > 64_000_000:
                raise AssertionError(f"mask {size} is far larger than the 64x64 frame")
            return real_new(mode, size, *args, **kwargs)

        Image.new = recording_new
        try:
            frame = np.zeros((64, 64, 3), np.uint8)
            mark = {"kind": "stroke", "points": [0, 0, 0, 1e6, 1e6, 0], "color": "#00ff00", "width": 2}
            drawing.paint_ink(frame, [mark], lambda p: (float(p[0]), float(p[1])), 1.0)
        finally:
            Image.new = real_new
        self.assertTrue(seen)
        for w, h in seen:
            self.assertLessEqual(w, (64 + 8) * drawing.INK_SUPERSAMPLE)
            self.assertLessEqual(h, (64 + 8) * drawing.INK_SUPERSAMPLE)


if __name__ == "__main__":
    unittest.main()
