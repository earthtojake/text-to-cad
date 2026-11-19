"""What a drawing's report says of the features a callout cannot state whole.

Each part is built here with build123d, small, and drawn through
``_render_sheet`` with a record of what the sheet states, as ``@eng_drawing``
does; ``_unstated`` then reads the part against that record.
"""

from __future__ import annotations

import unittest


def _report(sheet) -> list[str]:
    from cad._internal.drawing_render import _render_sheet
    from cad._internal.drawing_report import _Facts, _unstated

    facts = _Facts()
    _render_sheet(sheet, index=1, count=1, label="report", warnings=[], facts=facts)
    return _unstated(facts)


def _ball_and_fillet():
    """A block with a ⌀8 hole 6 deep ended in a ball, and a ⌀10 hole 10 deep to a
    floor filleted R2."""
    from build123d import Align, Axis, Box, Cylinder, Pos, Sphere, fillet

    down = (Align.CENTER, Align.CENTER, Align.MAX)
    block = Box(60, 40, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    block -= Pos(-15, 0, 20) * (Cylinder(4, 6, align=down) + Pos(0, 0, -6) * Sphere(4))
    filleted = Cylinder(5, 10, align=down)
    return block - Pos(15, 0, 20) * fillet(filleted.edges().group_by(Axis.Z)[0], 2)


class BlindEndReportTests(unittest.TestCase):
    """A callout's depth is where the full diameter ends; an end it has no symbol
    for is reported until a note states it."""

    def _sheet(self, note: str | None = None):
        from cad.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, _front, _right = sheet.three_views(_ball_and_fillet())
        top.holes()
        if note:
            top.note(note, (-15, 0, 20))
        return sheet

    def test_a_ball_end_is_reported_and_a_filleted_floor_is_the_depth(self) -> None:
        lines = _report(self._sheet())
        ball = [line for line in lines if "ends in a ball" in line]
        self.assertEqual(len(ball), 1, lines)
        self.assertIn("⌀8 ↧6 ends in a ball R4, 4 past the depth", ball[0])
        self.assertIn("SPHERICAL R4", ball[0], "the line names the note that states it")
        self.assertFalse([line for line in lines if "not called out" in line], lines)
        self.assertFalse([line for line in lines if "⌀10 ↧8" in line], "the fillet does not shorten the depth")
        self.assertTrue(any("fillet R2" in line for line in lines), "and the fillet is asked for as a radius")

    def test_a_note_naming_the_ball_states_it(self) -> None:
        lines = _report(self._sheet("SPHERICAL R4"))
        self.assertFalse([line for line in lines if "ends in a ball" in line], lines)

    def test_a_hole_ending_inside_a_bore_across_it_is_reported(self) -> None:
        from build123d import Align, Box, Cylinder, Pos, Rot
        from cad.eng_drawing import Sheet

        corner = (Align.MIN, Align.MIN, Align.MIN)
        block = Box(60, 40, 30, align=corner) - Pos(30, 20, 15) * Rot(0, 90, 0) * Cylinder(5, 60)
        block -= Pos(30, 0, 15) * Rot(-90, 0, 0) * Cylinder(3, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))

        def lines(note: str | None) -> list[str]:
            sheet = Sheet("A3", 1.0)
            _top, front, right = sheet.three_views(block)
            front.holes()
            right.holes()
            if note:
                front.note(note, (30, 0, 15))
            return [line for line in _report(sheet) if "drilled across it" in line]

        said = lines(None)
        self.assertEqual(len(said), 1, said)
        self.assertIn("⌀6 ↧15 ends inside a bore drilled across it", said[0])
        self.assertNotIn("THRU ends", said[0])
        self.assertEqual(lines("⌀6 THRU TO ⌀10 BORE"), [], "a note naming the hole states it")


def _round_cuts():
    """A 100 x 60 x 12 plate with three round cuts no hole callout reads: a bore
    tapering from ⌀10 at the top to ⌀6 at (-30, 0), a ⌀8 hole breaking out of the
    +X edge, and a ring groove 3 deep at (10, 0), ⌀30 outside round a ⌀20 island."""
    from build123d import Align, Box, Cone, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    plate = Box(100, 60, 12, align=align)
    plate -= Pos(-30, 0, 0) * Cone(3, 5, 12, align=align)
    plate -= Pos(48, 0, 0) * Cylinder(4, 12, align=align)
    return plate - Pos(10, 0, 9) * (Cylinder(15, 3, align=align) - Cylinder(10, 3, align=align))


class RoundCutTests(unittest.TestCase):
    """A tapered bore, a bore that is not a whole circle and a bore with material
    standing in it are each reported until the sheet states them."""

    def _sheet(self, stated: bool):
        from cad.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_round_cuts())
        top.overall()
        front.overall(width=False)
        if stated:
            front.dim((-33, 0, 0), (-27, 0, 0), text="%%c<>")       # the taper's small end
            front.dim((-35, 0, 12), (-25, 0, 12), text="%%c<>")     # and its large one
            top.radius((48, 0, 12), size=4)                         # the hole breaking out
            top.diameter((10, 0, 12), size=30)                      # the groove's outer wall
            top.diameter((10, 0, 12), size=20, angle=-45)           # and its island
        return sheet

    def test_each_is_reported_with_the_call_that_states_it(self) -> None:
        lines = _report(self._sheet(stated=False))
        taper = [line for line in lines if "tapered bore from ⌀10 to ⌀6" in line]
        self.assertEqual(len(taper), 1, lines)
        self.assertIn("leaves ⌀6, ⌀10 unstated", taper[0])
        broken = [line for line in lines if "R4 part-round bore" in line]
        self.assertEqual(len(broken), 1, lines)
        self.assertIn("top.radius(", broken[0])
        wall = [line for line in lines if "the bore ⌀30" in line and "material standing in it" in line]
        self.assertEqual(len(wall), 1, lines)
        self.assertIn("top.diameter(", wall[0])
        self.assertFalse([line for line in lines if "not called out" in line], "none of the three is a hole")

    def test_stated_they_are_not_reported(self) -> None:
        lines = _report(self._sheet(stated=True))
        self.assertFalse([line for line in lines if "tapered bore" in line or "part-round" in line
                          or "material standing" in line], lines)


def _grooved(ring: float):
    """A ⌀30 x 40 shaft along Z with an R2.5 groove round it at Z = 20, its section
    centred ``ring`` from the axis."""
    from build123d import Align, Cylinder, Pos, Torus

    return Cylinder(15, 40, align=(Align.CENTER, Align.CENTER, Align.MIN)) - Pos(0, 0, 20) * Torus(ring, 2.5)


class GrooveDepthTests(unittest.TestCase):
    """A groove's radius says how deep it is cut only when its section is centred
    on the surface it is cut in; one centred elsewhere needs a diameter."""

    def _lines(self, ring: float, across: bool = False) -> list[str]:
        from cad.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        _top, front = sheet.three_views(_grooved(ring), views=("top", "front"))
        front.overall()
        front.dim((15, 0, 5), (-15, 0, 5), text="%%c<>")
        front.dim((-15, 0, 0), (-15, 0, 20))
        front.radius((-ring, 0, 20))
        if across:
            front.dim((ring - 2.5, 0, 20), (2.5 - ring, 0, 20), text="%%c<>")
        return [line for line in _report(sheet) if "groove" in line]

    def test_a_groove_centred_off_its_surface_needs_its_diameter(self) -> None:
        self.assertEqual(self._lines(15.0), [], "centred on the ⌀30: R2.5 is its depth")
        lines = self._lines(16.0)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("its diameter ⌀27", lines[0])
        self.assertEqual(self._lines(16.0, across=True), [])


class OwnFrameTests(unittest.TestCase):
    """A first pass draws a plate turned to face the front; what its report says
    is where the author will find it: in the part's own frame."""

    def test_a_turned_part_s_report_is_in_the_part_s_own_frame(self) -> None:
        from build123d import Align, Box, Cone, Cylinder, Pos
        from cad.eng_drawing import part_sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        # Holes down Z, so the top is drawn as the front; a ⌀6 hole 7 deep from
        # below, which no view of a first pass looks into; and a tapered bore.
        plate = Box(80, 50, 12, align=align)
        plate -= [Pos(x, 15, 0) * Cylinder(2.5, 12, align=align) for x in (-30, 30)]
        plate -= Pos(-20, -10, 0) * Cylinder(3, 7, align=align)
        plate -= Pos(20, -10, 0) * Cone(3, 5, 12, align=align)
        sheet = part_sheet(plate, title="PLATE")
        self.assertIsNotNone(sheet.views[0]._turn, "the first pass turned it")
        lines = _report(sheet)
        floor = [line for line in lines if "the face at" in line]
        self.assertEqual(len(floor), 1, lines)
        self.assertIn("the face at Z = 7 (square to Z)", floor[0], "the blind hole's floor, 7 up the part's own Z")
        taper = [line for line in lines if "tapered bore" in line]
        self.assertEqual(len(taper), 1, lines)
        self.assertIn("along Z through (20, -10, 12)", taper[0])


class NoHexagonTests(unittest.TestCase):
    """A twelve-sided bar is not HEX 60 A/F: its first pass prints no HEX, and a
    sheet that leaves its flats unstated says so."""

    def _bar(self):
        from build123d import RegularPolygon, Rot, extrude

        return Rot(0, 0, 15) * extrude(RegularPolygon(30, 12, major_radius=False), amount=10)

    def test_a_first_pass_states_no_hex_and_a_bare_sheet_reports_the_flats(self) -> None:
        from cad._internal.drawing_render import _render_sheet
        from cad.eng_drawing import Sheet, part_sheet

        first = _render_sheet(part_sheet(self._bar(), title="BAR"), index=1, count=1, label="bar")
        said = [d.dxf.text for d in first.modelspace().query("DIMENSION")]
        self.assertFalse([text for text in said if "HEX" in text], said)
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(self._bar(), views=("top", "front"))
        top.overall()
        front.overall(width=False)
        lines = [line for line in _report(sheet) if "inclined face" in line]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("8 inclined faces have no angle", lines[0], "the four square to X and Y are overall sizes")


if __name__ == "__main__":
    unittest.main()
