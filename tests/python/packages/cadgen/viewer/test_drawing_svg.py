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



class DrawingPreviewEditTests(unittest.TestCase):
    """The viewer's preview edits on a cadgen sheet: moves, draft dimensions, highlight, tolerance."""

    def _sheet(self, td: Path) -> Path:
        from build123d import Align, Box
        from cadgen.drawing import Sheet, _render_sheet

        part = Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A4", title="PREVIEW")
        front = sheet.view(part, "front", at=(100, 60))
        sheet.view(part, "top", at=(100, 140))
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12)
        doc = _render_sheet(sheet, index=1, count=1, label="preview")
        path = td / "preview.dxf"
        doc.saveas(path)
        return path

    def test_parsers_accept_the_query_shapes(self) -> None:
        from cadgen.viewer.drawing_svg import parse_tolerance_spec, parse_view_moves

        self.assertEqual(parse_view_moves("FRONT:10,-5;right:0,20;bad"), {"front": (10.0, -5.0), "right": (0.0, 20.0)})
        self.assertEqual(parse_tolerance_spec("±0.1")["dimtp"], 0.1)
        self.assertEqual(parse_tolerance_spec("0.05/0.02")["dimtm"], 0.02)
        self.assertEqual(parse_tolerance_spec("H7"), {"fit": "H7"})
        self.assertEqual(parse_tolerance_spec(""), {})
        from cadgen.viewer.drawing_svg import parse_draft_dimensions, parse_tolerances
        self.assertEqual(parse_draft_dimensions("1,2,3,4,5;6,7,8,9,10,v;bad"), [(1.0, 2.0, 3.0, 4.0, 5.0, None), (6.0, 7.0, 8.0, 9.0, 10.0, "v")])
        self.assertEqual(parse_tolerances("front:0=±0.1;top:1=H7;junk"), [("front:0", "±0.1"), ("top:1", "H7")])
        from cadgen.viewer.drawing_svg import parse_draft_diameters
        self.assertEqual(parse_draft_diameters("110,50,3;bad;1,2,0;5,6,2,120"), [(110.0, 50.0, 3.0, 45.0), (5.0, 6.0, 2.0, 120.0)])
        from cadgen.viewer.drawing_svg import parse_draft_angles
        self.assertEqual(parse_draft_angles("100,40,140,40,140,60,14;bad"), [(100.0, 40.0, 140.0, 40.0, 140.0, 60.0, 14.0)])

    def test_moving_a_view_shifts_only_that_view(self) -> None:
        from cadgen.viewer.drawing_svg import _entity_tags, preview_edits

        with temporary_directory(prefix="tmp-cad-drawing-preview-") as td:
            path = self._sheet(Path(td))
            doc = ezdxf.readfile(path)

            def centre(view):
                xs = []
                for e in doc.modelspace().query("LINE"):
                    if _entity_tags(e).get("view") == view:
                        xs += [e.dxf.start.x, e.dxf.end.x]
                return sum(xs) / len(xs)

            before_front, before_top = centre("front"), centre("top")
            preview_edits(doc, moves={"front": (25.0, 0.0)})
            self.assertAlmostEqual(centre("front"), before_front + 25.0, places=6)
            self.assertAlmostEqual(centre("top"), before_top, places=6)
            # The view's dimension moved with it.
            dim = next(d for d in doc.modelspace().query("DIMENSION") if _entity_tags(d).get("view") == "front")
            self.assertGreater(dim.dxf.defpoint2.x, 100)

    def test_a_removed_dimension_leaves_the_preview(self) -> None:
        from cadgen.viewer.drawing_svg import _entity_tags, parse_removals, preview_edits

        self.assertEqual(parse_removals("front:0;Top:overall-w;bad"), [("front", "0"), ("top", "overall-w")])
        with temporary_directory(prefix="tmp-cad-drawing-preview-") as td:
            doc = ezdxf.readfile(self._sheet(Path(td)))
            before = len(doc.modelspace().query("DIMENSION"))
            preview_edits(doc, removals=[("front", "0")])
            dims = doc.modelspace().query("DIMENSION")
            self.assertEqual(len(dims), before - 1)
            self.assertFalse(any(_entity_tags(d).get("view") == "front" and _entity_tags(d).get("dim") == "0" for d in dims))

    def test_draft_dimension_highlight_and_tolerance_render_in_red(self) -> None:
        from cadgen.viewer.drawing_svg import preview_edits, render_drawing_svg

        with temporary_directory(prefix="tmp-cad-drawing-preview-") as td:
            path = self._sheet(Path(td))
            doc = ezdxf.readfile(path)
            before = len(doc.modelspace().query("DIMENSION"))
            preview_edits(doc, draft_dimension=(80, 40, 120, 40, 15, None), highlight="front:0",
                          tolerance=("front:0", "±0.1"), draft_diameter=[(100, 60, 3, 135)], draft_radius=[(100, 60, 18)],
                          draft_angle=[(100, 40, 140, 40, 140, 60, 14)])
            dims = doc.modelspace().query("DIMENSION")
            self.assertEqual(len(dims), before + 4)
            self.assertTrue(any(d.dimtype == 3 for d in dims), "a diameter dimension was drafted")
            self.assertTrue(any(d.dimtype == 4 for d in dims), "a radius dimension was drafted")
            self.assertTrue(any(d.dimtype == 5 for d in dims), "an angular dimension was drafted")
            texts = [e.text for d in dims for e in doc.blocks.get(d.dxf.geometry) if e.dxftype() == "MTEXT"]
            self.assertTrue(any("±0.1" in t for t in texts), texts)
            self.assertTrue(any(d.dxf.color == 1 for d in dims))
            svg = render_drawing_svg(path, draft_dimension=(80, 40, 120, 40, 15, None), highlight="front:0")
            self.assertIn("#ff0000", svg.lower(), "red strokes reach the SVG")


if __name__ == "__main__":
    unittest.main()
