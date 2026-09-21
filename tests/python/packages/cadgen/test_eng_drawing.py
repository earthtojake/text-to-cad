"""``@eng_drawing``: a PDF sheet derived from a part.

The part is built with build123d so every expected number is known from the
construction: a 40 x 30 x 10 box with one 6 mm hole dimensioned overall reads
40 and 30 because it was built that way, and its hole gets a centre mark
because the projected outline contains a full circle.

``_render_sheet`` returns the in-memory ezdxf document the PDF is rendered
from, so the sheet's content is asserted there; the decorator's own tests
cover the document that reaches disk.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tests.python.support.tmp_root import temporary_directory


def _part():
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    return Box(40, 30, 10, align=align) - Pos(10, 5, 0) * Cylinder(3, 10, align=align)


def _sheet(part):
    from cadgen.eng_drawing import Sheet

    sheet = Sheet("A4", title="TEST BLOCK", part_number="T-1", revision="B", notes=["ONE", "TWO"])
    top = sheet.view(part, "top", at=(100, 120))
    front = sheet.view(part, "front", at=(100, 50))
    top.overall()
    top.diameter((10, 5, 10), 3, text="%%c6 THRU")
    front.dim((20, -15, 0), (20, -15, 10), offset=12)
    return sheet


def _dim_texts(doc):
    texts = []
    for dim in doc.modelspace().query("DIMENSION"):
        block = doc.blocks.get(dim.dxf.geometry)
        texts.extend(e.text for e in block if e.dxftype() == "MTEXT")
    return texts


class DrawingSheetTests(unittest.TestCase):
    def test_a_sheet_writes_views_dimensions_marks_frame_and_title(self) -> None:
        from cadgen.eng_drawing import _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=2, label="t")
        msp = doc.modelspace()
        kinds = {}
        for entity in msp:
            kinds[entity.dxftype()] = kinds.get(entity.dxftype(), 0) + 1
        self.assertEqual(kinds.get("DIMENSION"), 3, "overall width + height, the front height")
        self.assertEqual(kinds.get("LEADER"), 1, "the hole callout is a leader to text outside the view")
        self.assertGreaterEqual(kinds.get("TEXT", 0), 6, "title block, notes and two view labels")
        by_layer = {}
        for entity in msp:
            by_layer.setdefault(entity.dxf.layer, 0)
            by_layer[entity.dxf.layer] += 1
        self.assertGreater(by_layer.get("VISIBLE", 0), 0)
        self.assertGreater(by_layer.get("HIDDEN", 0), 0, "the hole is hidden in the front view")
        self.assertEqual(by_layer.get("CENTER", 0), 2, "one centre mark: two lines")
        # Measured, not typed: the overall dimensions read the box.
        texts = _dim_texts(doc)
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

    def test_every_layer_linetype_exists_in_the_table(self) -> None:
        """A layer naming a linetype the document does not define draws continuous.

        ezdxf's `setup=True` table has DASHED and CENTER and no HIDDEN, and it
        substitutes silently (the audit reports "Replaced undefined linetype"),
        so hidden edges printed solid. Asserting the NAME on the layer cannot
        catch that; asserting the table can.
        """
        from cadgen.eng_drawing import _LAYERS, _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=1, label="t")
        defined = {lt.dxf.name.upper() for lt in doc.linetypes}
        for name, (_color, linetype, _weight) in _LAYERS.items():
            self.assertIn(linetype.upper(), defined, f"layer {name} names an undefined linetype")
        auditor = doc.audit()
        self.assertEqual(list(auditor.errors), [])
        self.assertEqual([str(fix) for fix in auditor.fixes], [])

    def test_the_hidden_line_pass_writes_each_edge_once(self) -> None:
        """The kernel returns a hidden edge once per face that hides it."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        sheet.view(part, "front", at=(150, 105))
        doc = _render_sheet(sheet, index=1, count=1, label="dupes")
        drawn: dict[str, list] = {}
        for entity in doc.modelspace().query("LINE LWPOLYLINE CIRCLE ARC"):
            if entity.dxf.layer not in ("VISIBLE", "HIDDEN"):
                continue
            key = (entity.dxftype(), tuple(sorted(tuple(round(v, 6) for v in p) for p in _points(entity))))
            drawn.setdefault(entity.dxf.layer, []).append(key)
        for layer, keys in drawn.items():
            self.assertEqual(len(keys), len(set(keys)), f"{layer} holds duplicate geometry")
        self.assertGreater(len(drawn.get("HIDDEN", [])), 0, "the bore is hidden in the front view")

    def test_dimension_points_land_on_the_projected_geometry(self) -> None:
        """A dimension between the box's top corners spans exactly the drawn outline."""
        from cadgen.eng_drawing import Sheet, _render_sheet

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

    def test_a_scaled_sheet_prints_true_size_values(self) -> None:
        """At 1:2 an 80 x 50 x 10 plate still reads 80, 50 and 10.

        The dimension measures SHEET millimetres, which are the model's only at
        1:1, so each view sets dimlfac to the inverse of its own scale.
        """
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(80, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        for scale in (1.0, 0.5, 0.25):
            with self.subTest(scale=scale):
                sheet = Sheet("A3", scale=scale, title="PLATE")
                top, front, _right = sheet.three_views(part)
                top.overall()
                front.dim((-40, -25, 0), (-40, -25, 10), offset=-14)
                doc = _render_sheet(sheet, index=1, count=1, label="s")
                texts = _dim_texts(doc)
                self.assertIn("80", texts)
                self.assertIn("50", texts)
                self.assertIn("10", texts)
        # A view drawn at its own scale reads true size too.
        sheet = Sheet("A3", scale=1.0)
        sheet.view(part, "top", at=(210, 150), scale=0.5).overall()
        self.assertEqual(sorted(_dim_texts(_render_sheet(sheet, index=1, count=1, label="s"))), ["50", "80"])

    def test_a_tolerance_prints_the_authors_deviation_at_any_scale(self) -> None:
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(80, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3", scale=0.5)
        front = sheet.view(part, "front", at=(210, 150))
        front.dim((-40, -25, 0), (40, -25, 0), offset=-14, tol=0.1)
        texts = _dim_texts(_render_sheet(sheet, index=1, count=1, label="tol"))
        self.assertTrue(any("80" in t and "±0.10" in t for t in texts), texts)

    def test_an_unplaced_dimension_takes_the_next_free_row(self) -> None:
        """`dim()` used to default to the row `overall()` writes into."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        top = sheet.view(part, "top", at=(150, 105))
        top.overall()
        top.dim((-20, 15, 10), (20, 15, 10))
        top.dim((-20, -15, 10), (20, -15, 10))
        doc = _render_sheet(sheet, index=1, count=1, label="rows")
        # The three horizontal dimensions: the overall width and the two unplaced ones.
        rows = sorted(round(d.dxf.defpoint.y, 3) for d in doc.modelspace().query("DIMENSION")
                      if abs(float(d.dxf.angle)) < 1e-9)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(set(rows)), 3, f"two dimensions share a row: {rows}")
        self.assertEqual([round(b - a, 3) for a, b in zip(rows, rows[1:])], [12.0, 12.0],
                         "one clear row apart")

    def test_views_that_run_off_the_frame_are_refused_with_a_scale_that_fits(self) -> None:
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(3000, 1200, 200, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3")
        sheet.three_views(part)
        with self.assertRaises(ValueError) as caught:
            _render_sheet(sheet, index=1, count=1, label="big")
        message = str(caught.exception)
        self.assertIn("off the frame", message)
        suggested = float(message.split("Sheet(scale=")[1].split(")")[0])
        self.assertLess(suggested, 1.0)
        # The suggestion has to be one that actually works.
        fits = Sheet("A3", scale=suggested)
        fits.three_views(part)
        _render_sheet(fits, index=1, count=1, label="big")

    def test_a_title_longer_than_its_cell_is_cut_not_overrun(self) -> None:
        from cadgen.eng_drawing import _MIN_TEXT_MM, Sheet, _render_sheet

        title = "ELECTRONICS ENCLOSURE BASE, LOWER HALF, REVISION C, MACHINED FROM 6061-T6 BILLET"
        sheet = Sheet("A4", title=title)
        sheet.view(_part(), "top", at=(150, 120))
        doc = _render_sheet(sheet, index=1, count=1, label="long")
        drawn = next(e for e in doc.modelspace().query("TEXT[layer=='TITLE']")
                     if e.dxf.text.startswith("ELECTRONICS"))
        self.assertGreaterEqual(drawn.dxf.height, _MIN_TEXT_MM)
        cell = min(180.0, 297 - 20) * 0.6 - 6
        self.assertLessEqual(len(drawn.dxf.text) * drawn.dxf.height * 0.72, cell + 1e-6)
        self.assertTrue(drawn.dxf.text.endswith("…"), drawn.dxf.text)

    def test_first_angle_lays_the_views_out_first_angle(self) -> None:
        """The label and the arrangement are the same decision."""
        from cadgen.eng_drawing import Sheet

        part = _part()
        third = Sheet("A3")
        t_top, t_front, t_right = third.three_views(part)
        self.assertGreater(t_top.at[1], t_front.at[1], "third angle: the plan sits above the front")
        self.assertGreater(t_right.at[0], t_front.at[0], "third angle: the view from the right sits right")
        first = Sheet("A3", projection="FIRST ANGLE")
        f_top, f_front, f_right = first.three_views(part)
        self.assertLess(f_top.at[1], f_front.at[1], "first angle: the plan sits below the front")
        self.assertLess(f_right.at[0], f_front.at[0], "first angle: the view from the right sits left")

    def test_the_bottom_view_lines_up_under_the_front_view(self) -> None:
        """Third angle draws the bottom view as the top view mirrored, not rotated."""
        from cadgen.eng_drawing import _Projection

        part = _part()
        top, bottom = _Projection(part, "top"), _Projection(part, "bottom")

        def axes(proj):
            origin = proj.point((0, 0, 0))
            return [tuple(round(a - b, 6) for a, b in zip(proj.point(p), origin))
                    for p in ((1, 0, 0), (0, 1, 0))]

        self.assertEqual(axes(top), [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(axes(bottom), [(1.0, 0.0), (0.0, -1.0)], "+X must stay right; +Y flips")

    def test_every_side_view_maps_up_to_up(self) -> None:
        """A model point higher in Z lands higher on the sheet in every view that
        looks along a horizontal direction; the right and left views once mirrored."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        for name in ("front", "back", "right", "left"):
            with self.subTest(view=name):
                sheet = Sheet("A3")
                view = sheet.view(part, name, at=(210, 150))
                view.dim((0, 0, 0), (0, 0, 10), offset=12)
                doc = _render_sheet(sheet, index=1, count=1, label="sides")
                dim = doc.modelspace().query("DIMENSION")[0]
                self.assertGreater(dim.dxf.defpoint3.y, dim.dxf.defpoint2.y, "z=10 should sit above z=0")
                self.assertGreater(dim.dxf.defpoint3.y, view.at[1], "the top of the part is above the centre")

    def test_view_label_sits_below_bottom_dimensions(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        front = sheet.view(part, "front", at=(100, 100))
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12)
        doc = _render_sheet(sheet, index=1, count=1, label="label")
        label = next(e for e in doc.modelspace().query("TEXT[layer=='NOTES']") if e.dxf.text == "FRONT")
        dim = doc.modelspace().query("DIMENSION")[0]
        self.assertLess(label.dxf.insert.y, dim.dxf.defpoint.y - 3, "the label hangs under the dimension line")

    def test_round_edges_are_written_as_circles_and_arcs(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A4")
        sheet.view(_part(), "top", at=(100, 120))
        doc = _render_sheet(sheet, index=1, count=1, label="round")
        circles = [c for c in doc.modelspace().query("CIRCLE") if c.dxf.layer == "VISIBLE"]
        self.assertEqual(len(circles), 1, "the hole seen from above is one CIRCLE")
        self.assertAlmostEqual(circles[0].dxf.radius, 3.0, places=3)

    def test_shop_annotations_are_written(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet, hole_callout_text

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
        texts = _dim_texts(doc)
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
                                            "thread": "M6x1 - 6H", "count": None}), "M6x1 - 6H ↧12   ⌴ %%c11 ↧6.5")

    def test_an_angular_dimension_is_written(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A4")
        front = sheet.view(_part(), "front", at=(100, 100))
        front.angle((-20, -15, 0), (20, -15, 0), (-20, -15, 10), offset=14)
        doc = _render_sheet(sheet, index=1, count=1, label="angle")
        dims = doc.modelspace().query("DIMENSION")
        self.assertTrue(any(d.dimtype == 5 for d in dims), "an angular dimension on the DIM layer")


class DrawingVocabularyTests(unittest.TestCase):
    """Every argument is checked where it is written, not at render time."""

    def setUp(self) -> None:
        from cadgen.eng_drawing import Sheet

        self.view = Sheet("A4").view(_part(), "top", at=(100, 100))

    def test_unknown_view_sheet_and_projection_are_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaises(ValueError):
            Sheet("Letter")
        with self.assertRaises(ValueError):
            Sheet("A4").view(_part(), "diagonal", at=(0, 0))
        with self.assertRaisesRegex(ValueError, "projection"):
            Sheet("A4", projection="THIRD-ANGLE")

    def test_an_unknown_orientation_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "orientation"):
            self.view.dim((0, 0, 0), (1, 0, 0), orientation="x")

    def test_a_hole_that_cannot_be_made_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "diameter"):
            self.view.hole((0, 0, 0), -5)
        with self.assertRaisesRegex(ValueError, "diameter"):
            self.view.hole((0, 0, 0), 0)
        with self.assertRaisesRegex((TypeError, ValueError), "cbore"):
            self.view.hole((0, 0, 0), 6, cbore=5)
        with self.assertRaisesRegex(ValueError, "cbore"):
            self.view.hole((0, 0, 0), 6, cbore=(11, -2))
        with self.assertRaisesRegex(ValueError, "THRU"):
            self.view.hole((0, 0, 0), 6, thru=True, depth=12)
        with self.assertRaisesRegex(ValueError, "radius"):
            self.view.diameter((0, 0, 0), 0)

    def test_a_tolerance_that_is_not_a_tolerance_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), tol="abc")
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), tol=(1, 2, 3))

    def test_an_offset_that_is_not_a_number_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), offset="far")


class DrawingDocumentTests(unittest.TestCase):
    """What reaches disk: one PDF, at the path the caller named, byte-stable."""

    def test_running_the_decorated_function_writes_one_deterministic_pdf(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "PDF" / "block.pdf"

            @eng_drawing(out=str(out))
            def block_drawing():
                return _sheet(_part())

            written = block_drawing()
            self.assertEqual(written, [out])
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["block.pdf"],
                             "no DXF, and no half-written file left behind")
            payload = out.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF"))
            self.assertNotIn(b"CreationDate", payload, "a clock stamp would make the bytes differ per run")
            block_drawing()
            self.assertEqual(out.read_bytes(), payload, "an unchanged drawing rebuilds to identical bytes")

    def test_a_sheet_per_page(self) -> None:
        from cadgen.eng_drawing import Sheet, eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "pair.pdf"
            part = _part()

            @eng_drawing(out=str(out))
            def pair():
                a = Sheet("A4", title="ONE"); a.view(part, "top", at=(150, 105))
                b = Sheet("A4", title="TWO"); b.view(part, "front", at=(150, 105))
                return [a, b]

            self.assertEqual(pair(), [out])
            # matplotlib writes the page tree uncompressed: the tree's /Count is the page count.
            self.assertIn(b"/Count 2", out.read_bytes())

    def test_the_output_path_is_required_and_names_a_pdf(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with self.assertRaisesRegex(ValueError, "out="):
            @eng_drawing
            def no_path():
                return _sheet(_part())

        with self.assertRaisesRegex(ValueError, r"\.pdf"):
            @eng_drawing(out="../DXF/wrong.dxf")
            def wrong_suffix():
                return _sheet(_part())

    def test_a_missing_renderer_fails_loudly_and_writes_nothing(self) -> None:
        """The PDF is the drawing: no renderer is a failure, not a skipped half."""
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "PDF" / "block.pdf"

            @eng_drawing(out=str(out))
            def block_drawing():
                return _sheet(_part())

            # Only this key is swapped and restored: `patch.dict` on sys.modules
            # rebuilds the whole mapping on exit and would drop every submodule
            # imported inside the block, the CAD kernel's included.
            missing = object()
            previous = sys.modules.get("matplotlib", missing)
            sys.modules["matplotlib"] = None  # `import matplotlib` now raises ImportError
            try:
                with self.assertRaisesRegex(RuntimeError, "PDF"):
                    block_drawing()
            finally:
                if previous is missing:
                    sys.modules.pop("matplotlib", None)
                else:
                    sys.modules["matplotlib"] = previous
            self.assertFalse(out.exists())

    def test_a_function_that_returns_no_sheet_is_refused(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            @eng_drawing(out=str(Path(td) / "x.pdf"))
            def not_a_sheet():
                return 42

            with self.assertRaises(TypeError):
                not_a_sheet()


def _points(entity):
    kind = entity.dxftype()
    if kind == "LINE":
        return [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
    if kind == "CIRCLE":
        return [(entity.dxf.center.x, entity.dxf.center.y), (entity.dxf.radius, entity.dxf.radius)]
    if kind == "ARC":
        return [(entity.dxf.center.x, entity.dxf.center.y), (entity.dxf.radius, entity.dxf.radius),
                (entity.dxf.start_angle, entity.dxf.end_angle)]
    return list(entity.get_points("xy"))


if __name__ == "__main__":
    unittest.main()
