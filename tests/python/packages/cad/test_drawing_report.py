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


if __name__ == "__main__":
    unittest.main()
