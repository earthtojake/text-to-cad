"""``@drawing``: a sheet derived from a part.

The part is built with build123d so every expected number is known from the
construction: a 40 x 30 x 10 box with one 6 mm hole dimensioned overall reads
40 and 30 because it was built that way, and its hole gets a centre mark
because the projected outline contains a full circle.
"""

from __future__ import annotations

import io
import unittest
from pathlib import Path

from tests.python.support.tmp_root import temporary_directory


def _part():
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    return Box(40, 30, 10, align=align) - Pos(10, 5, 0) * Cylinder(3, 10, align=align)


def _sheet(part):
    from cadgen.drawing import Sheet

    sheet = Sheet("A4", title="TEST BLOCK", part_number="T-1", revision="B", notes=["ONE", "TWO"])
    top = sheet.view(part, "top", at=(100, 120))
    front = sheet.view(part, "front", at=(100, 50))
    top.overall()
    top.diameter((10, 5, 10), 3, text="%%c6 THRU")
    front.dim((20, -15, 0), (20, -15, 10), offset=12)
    return sheet


class DrawingSheetTests(unittest.TestCase):
    def test_a_sheet_writes_views_dimensions_marks_frame_and_title(self) -> None:
        import ezdxf
        from cadgen.drawing import _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=2, label="t")
        msp = doc.modelspace()
        kinds = {}
        for entity in msp:
            kinds[entity.dxftype()] = kinds.get(entity.dxftype(), 0) + 1
        self.assertEqual(kinds.get("DIMENSION"), 3, "overall width + height, the front height")
        self.assertEqual(kinds.get("LEADER"), 1, "the hole callout is a leader to text outside the view")
        self.assertGreaterEqual(kinds.get("TEXT", 0), 6, "title block, notes and two view labels")
        layers = {layer.dxf.name: layer for layer in doc.layers}
        self.assertEqual(layers["HIDDEN"].dxf.linetype, "HIDDEN")
        self.assertEqual(layers["CENTER"].dxf.linetype, "CENTER")
        by_layer = {}
        for entity in msp:
            by_layer.setdefault(entity.dxf.layer, 0)
            by_layer[entity.dxf.layer] += 1
        self.assertGreater(by_layer.get("VISIBLE", 0), 0)
        self.assertGreater(by_layer.get("HIDDEN", 0), 0, "the hole is hidden in the front view")
        self.assertEqual(by_layer.get("CENTER", 0), 2, "one centre mark: two lines")
        # Measured, not typed: the overall dimensions read the box.
        texts = []
        for dim in msp.query("DIMENSION"):
            block = doc.blocks.get(dim.dxf.geometry)
            texts.extend(e.text for e in block if e.dxftype() == "MTEXT")
        self.assertIn("40", texts)
        self.assertIn("30", texts)
        self.assertIn("10", texts)
        callouts = [e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == "DIM"]
        self.assertEqual(callouts, ["%%c6 THRU"])
        # The callout text sits outside the view's extent, not across the part.
        callout = next(e for e in msp.query("TEXT") if e.dxf.layer == "DIM")
        outline_x = [p[0] for e in msp.query("LWPOLYLINE LINE") if e.dxf.layer == "VISIBLE" for p in _points(e)]
        self.assertTrue(callout.dxf.insert.x > max(outline_x) or callout.dxf.insert.x < min(outline_x))
        # A4 landscape frame at the margin.
        frame = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "SHEET"]
        self.assertEqual(len(frame), 1)
        xs = [p[0] for p in frame[0].get_points("xy")]
        self.assertAlmostEqual(max(xs) - min(xs), 297 - 20, places=6)
        title_text = [e.dxf.text for e in msp.query("TEXT")]
        self.assertIn("TEST BLOCK", title_text)
        self.assertTrue(any("SHEET 1 OF 2" in t and "REV B" in t for t in title_text))

    def test_dimension_points_land_on_the_projected_geometry(self) -> None:
        """A dimension between the box's top corners spans exactly the drawn outline."""
        from cadgen.drawing import _render_sheet, Sheet

        part = _part()
        sheet = Sheet("A4")
        top = sheet.view(part, "top", at=(100, 100))
        top.dim((-20, 15, 10), (20, 15, 10), offset=10)
        doc = _render_sheet(sheet, index=1, count=1, label="t")
        msp = doc.modelspace()
        dim = list(msp.query("DIMENSION"))[0]
        p1, p2 = dim.dxf.defpoint2, dim.dxf.defpoint3
        self.assertAlmostEqual(abs(p2.x - p1.x), 40.0, places=5)
        xs = [p[0] for e in msp.query("LWPOLYLINE LINE") if e.dxf.layer == "VISIBLE" for p in _points(e)]
        self.assertAlmostEqual(min(p1.x, p2.x), min(xs), places=4)
        self.assertAlmostEqual(max(p1.x, p2.x), max(xs), places=4)

    def test_running_the_decorated_function_writes_deterministic_dxf(self) -> None:
        from cadgen.drawing import drawing

        with temporary_directory(prefix="tmp-cad-drawing-") as td:
            root = Path(td)
            (root / "src").mkdir()
            out = root / "DXF" / "block.dxf"

            @drawing(out=str(out), pdf=False)
            def block_drawing():
                return _sheet(_part())

            first = block_drawing()
            self.assertEqual(first, [out])
            payload = out.read_bytes()
            block_drawing()
            self.assertEqual(out.read_bytes(), payload, "an unchanged drawing rebuilds to identical bytes")
            self.assertNotIn(b"@ 20", payload[:4000], "no live timestamp marker survives")

    def test_two_sheets_write_two_files_and_number_themselves(self) -> None:
        from cadgen.drawing import drawing, Sheet

        with temporary_directory(prefix="tmp-cad-drawing-") as td:
            out = Path(td) / "DXF" / "pair.dxf"
            part = _part()

            @drawing(out=str(out), pdf=False)
            def pair():
                a = Sheet("A4", title="ONE"); a.view(part, "top", at=(100, 100))
                b = Sheet("A4", title="TWO"); b.view(part, "front", at=(100, 100))
                return [a, b]

            written = pair()
            self.assertEqual([p.name for p in written], ["pair.dxf", "pair-sheet2.dxf"])
            import ezdxf
            second = ezdxf.readfile(written[1])
            self.assertTrue(any("SHEET 2 OF 2" in e.dxf.text for e in second.modelspace().query("TEXT")))

    def test_pdf_pages_follow_the_sheets_when_matplotlib_is_present(self) -> None:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not installed")
        from cadgen.drawing import drawing, Sheet

        with temporary_directory(prefix="tmp-cad-drawing-") as td:
            out = Path(td) / "DXF" / "pdf.dxf"
            part = _part()

            @drawing(out=str(out))
            def two():
                a = Sheet("A4"); a.view(part, "top", at=(100, 100))
                b = Sheet("A3"); b.view(part, "iso", at=(200, 150))
                return [a, b]

            written = two()
            pdf = [p for p in written if p.suffix == ".pdf"]
            self.assertEqual(len(pdf), 1)
            self.assertEqual(pdf[0].parent.name, "PDF")
            # matplotlib writes the page tree uncompressed: the tree's /Count is the page count.
            self.assertIn(b"/Count 2", pdf[0].read_bytes())

    def test_views_are_tagged_and_shop_annotations_are_written(self) -> None:
        import ezdxf
        from cadgen.drawing import Sheet, _render_sheet, hole_callout_text

        part = _part()
        sheet = Sheet("A4", title="TAGGED", general_tolerance="ISO 2768-m",
                      revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ("B", "2026-09-17", "HOLE MOVED")])
        top = sheet.view(part, "top", at=(100, 120))
        front = sheet.view(part, "front", at=(100, 50))
        front.dim((20, -15, 0), (20, -15, 10), offset=12, tol=0.1)
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12, tol=(0.05, 0.02), fit="h6")
        top.hole((10, 5, 10), 6, thru=True, count=1)
        top.hole((10, 5, 10), 6.6, depth=12, cbore=(11, 6.5), thread="M6x1 - 6H")
        doc = _render_sheet(sheet, index=1, count=1, label="tagged")
        msp = doc.modelspace()

        # Every view entity names its view; every dimension names its authoring index.
        tags = {}
        for entity in msp:
            xdata = entity.get_xdata("CADGEN") if entity.has_xdata("CADGEN") else []
            values = [str(tag.value) for tag in xdata]
            view = next((v[5:] for v in values if v.startswith("view=")), None)
            if view:
                tags.setdefault(view, set()).update(v for v in values if v.startswith("dim="))
        self.assertEqual(set(tags), {"top", "front"})
        self.assertEqual(tags["front"], {"dim=0", "dim=1"})
        self.assertEqual(tags["top"], {"dim=0", "dim=1"})
        tagged_lines = [e for e in msp.query("LINE LWPOLYLINE") if e.has_xdata("CADGEN")]
        self.assertGreater(len(tagged_lines), 4, "the projected edges carry their view")
        # The view label carries the placement and the model->sheet map, and the map
        # sends the dimension's model points where the dimension landed.
        label = next(e for e in msp.query("TEXT[layer=='NOTES']") if e.dxf.text == "FRONT")
        values = {str(t.value).split("=")[0]: str(t.value).split("=", 1)[1] for t in label.get_xdata("CADGEN") if "=" in str(t.value)}
        self.assertEqual(values["at"], "100,50")
        m = [float(v) for v in values["map"].split(",")]
        self.assertEqual(len(m), 8)
        def to_sheet(p):
            return (m[0] + m[2] * p[0] + m[4] * p[1] + m[6] * p[2], m[1] + m[3] * p[0] + m[5] * p[1] + m[7] * p[2])
        front_dim = next(d for d in msp.query("DIMENSION") if "dim=0" in [str(t.value) for t in d.get_xdata("CADGEN")] and "view=front" in [str(t.value) for t in d.get_xdata("CADGEN")])
        expected = to_sheet((20, -15, 0))
        self.assertAlmostEqual(front_dim.dxf.defpoint2.x, expected[0], places=3)
        self.assertAlmostEqual(front_dim.dxf.defpoint2.y, expected[1], places=3)

        def dim_texts():
            out = []
            for d in msp.query("DIMENSION"):
                out += [e.text for e in doc.blocks.get(d.dxf.geometry) if e.dxftype() == "MTEXT"]
            return out

        texts = dim_texts()
        self.assertTrue(any("±0.10" in t for t in texts), texts)
        self.assertTrue(any("+0.05" in t and "0.02" in t and "h6" in t for t in texts), texts)
        notes = [e.dxf.text for e in msp.query("TEXT[layer=='NOTES']")]
        self.assertTrue(any("ISO 2768-m" in n for n in notes), notes)
        title_texts = [e.dxf.text for e in msp.query("TEXT[layer=='TITLE']")]
        self.assertIn("DESCRIPTION", title_texts)
        self.assertIn("HOLE MOVED", title_texts)
        callouts = [e.dxf.text for e in msp.query("TEXT[layer=='DIM']")]
        self.assertIn("1× %%c6 THRU", callouts)
        self.assertEqual(hole_callout_text({"diameter": 6.6, "depth": 12, "thru": False, "cbore": (11, 6.5), "csk": None,
                                            "thread": "M6x1 - 6H", "count": None}), "M6x1 - 6H \u21a712   \u2334 %%c11 \u21a76.5")

    def test_unknown_view_and_sheet_are_refused(self) -> None:
        from cadgen.drawing import Sheet

        with self.assertRaises(ValueError):
            Sheet("Letter")
        with self.assertRaises(ValueError):
            Sheet("A4").view(_part(), "diagonal", at=(0, 0))


def _points(entity):
    if entity.dxftype() == "LINE":
        return [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
    return list(entity.get_points("xy"))


if __name__ == "__main__":
    unittest.main()
