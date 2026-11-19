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


if __name__ == "__main__":
    unittest.main()
