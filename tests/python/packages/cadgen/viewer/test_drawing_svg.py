"""``/__cad/drawing``: a dimensioned DXF rendered to SVG by ezdxf."""

from __future__ import annotations

import unittest
from pathlib import Path

import ezdxf

from cadgen.viewer.drawing_svg import render_drawing_svg
from tests.python.support.tmp_root import temporary_directory


def _drawing(path: Path) -> None:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("HIDDEN", color=8, linetype="HIDDEN")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=True)
    msp.add_line((10, 30), (90, 30), dxfattribs={"layer": "HIDDEN"})
    msp.add_linear_dim(base=(0, -12), p1=(0, 0), p2=(100, 0), dimstyle="Standard").render()
    msp.add_text("SECTION A-A", dxfattribs={"height": 5}).set_placement((0, 70))
    doc.saveas(path)


class DrawingSvgTests(unittest.TestCase):
    def test_renders_geometry_dimension_and_text(self) -> None:
        with temporary_directory(prefix="tmp-cad-drawing-svg-") as td:
            path = Path(td) / "sheet.dxf"
            _drawing(path)
            svg = render_drawing_svg(path)
        self.assertIn("<svg", svg)
        # Text (the label and the dimension's measured value) is rendered as glyph
        # outlines, filled paths, so the client needs no font: there must be filled
        # geometry as well as stroked geometry, and the hidden line's grey stroke.
        self.assertIn("fill: #000000", svg, "glyph outlines are filled")
        self.assertIn("stroke: #808080", svg, "the HIDDEN layer keeps its grey")
        self.assertGreaterEqual(svg.count("<path"), 6)
        self.assertIn('width="', svg)

    def test_hidden_layers_are_left_out(self) -> None:
        with temporary_directory(prefix="tmp-cad-drawing-svg-") as td:
            path = Path(td) / "sheet.dxf"
            _drawing(path)
            full = render_drawing_svg(path)
            without = render_drawing_svg(path, hidden_layers=("HIDDEN",))
        self.assertLess(len(without), len(full), "hiding a layer removes its strokes")


if __name__ == "__main__":
    unittest.main()
