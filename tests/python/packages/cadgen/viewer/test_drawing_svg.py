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

    def test_line_weight_scales_every_stroke(self) -> None:
        import re

        with temporary_directory(prefix="tmp-cad-drawing-svg-") as td:
            path = Path(td) / "sheet.dxf"
            _drawing(path)
            normal = render_drawing_svg(path)
            bold = render_drawing_svg(path, lineweight_scale=2.0)

        def widths(svg: str) -> list[float]:
            return sorted(float(w) for w in re.findall(r"stroke-width: ([0-9.]+)", svg))

        self.assertTrue(widths(normal))
        self.assertGreater(max(widths(bold)), max(widths(normal)), "Bold draws wider strokes")

    def test_dimensions_can_be_restated_in_precision_units_and_size(self) -> None:
        from cadgen.viewer.drawing_svg import restyle_dimensions

        def dimension_texts(document):
            texts = []
            for dimension in document.modelspace().query("DIMENSION"):
                block = document.blocks.get(dimension.dxf.geometry)
                texts += [e.text if e.dxftype() == "MTEXT" else e.dxf.text for e in block if e.dxftype() in ("TEXT", "MTEXT")]
            return texts

        with temporary_directory(prefix="tmp-cad-drawing-svg-") as td:
            path = Path(td) / "sheet.dxf"
            _drawing(path)
            untouched = ezdxf.readfile(path)
            self.assertEqual(restyle_dimensions(untouched), 0, "nothing asked, nothing re-rendered")
            self.assertEqual(dimension_texts(untouched), ["100"])

            precise = ezdxf.readfile(path)
            self.assertEqual(restyle_dimensions(precise, decimals=2), 1)
            self.assertEqual(dimension_texts(precise), ["100.00"])

            inches = ezdxf.readfile(path)
            restyle_dimensions(inches, units="in")
            self.assertEqual(dimension_texts(inches), ['3.937"'])

            larger = ezdxf.readfile(path)
            restyle_dimensions(larger, text_scale=2.0)
            heights = [e.dxf.char_height for d in larger.modelspace().query("DIMENSION")
                       for e in larger.blocks.get(d.dxf.geometry) if e.dxftype() == "MTEXT"]
            self.assertTrue(heights and all(h > 1.5 for h in heights), heights)

            with self.assertRaises(ValueError):
                restyle_dimensions(ezdxf.readfile(path), units="furlongs")

            svg = render_drawing_svg(path, dimension_units="in", dimension_decimals=1)
            self.assertIn("<svg", svg)


if __name__ == "__main__":
    unittest.main()
