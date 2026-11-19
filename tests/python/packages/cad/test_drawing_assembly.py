"""An assembly's parts list: one row per part, however each copy was built and
however it stands.

Every assembly is built here with build123d, small.
"""

from __future__ import annotations

import unittest


def _handed():
    """A block no turn lays on its mirror image: a blind hole off both centre
    lines, and a corner cut away."""
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    corner = (Align.MIN, Align.MIN, Align.MIN)
    return (Box(20, 12, 30, align=align) - Pos(4, 2, 22) * Cylinder(2, 8, align=align)
            - Pos(-10, -6, 0) * Box(5, 3, 10, align=corner))


def _stand(turns, mirrored: bool = False):
    """A round base with a leg at each of ``turns``: (about X, about Z) in degrees.
    Each leg is built where it stands and cut after it was turned, so no two share
    a shape, and none is a shifted copy of another."""
    from build123d import Align, Box, Compound, Cylinder, Plane, Pos, Rot, mirror

    base = Cylinder(60, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    base.label = "base"
    legs = []
    for k, (tilt, spin) in enumerate(turns):
        leg = Rot(tilt, 0, spin) * Pos(35, 0, 5) * _handed()
        if mirrored and k == len(turns) - 1:
            leg = mirror(leg, Plane.XZ)
        leg -= Pos(0, 0, 500) * Box(1, 1, 1)   # a cut that takes nothing: the leg is its own solid now
        leg.label = "leg"
        legs.append(leg)
    return Compound(children=[base, *legs])


class TurnedCopyTests(unittest.TestCase):
    """The same part at four angles is one row, four off; its mirror image is another part."""

    def test_copies_built_apart_and_turned_are_one_item(self) -> None:
        from cad.eng_drawing import parts_list

        parts = parts_list(_stand([(0, 0), (0, 90), (10, 143), (0, 251)]))
        self.assertEqual([(item.description, item.quantity) for item in parts], [("BASE", 1), ("LEG", 4)])
        self.assertEqual(len(parts["leg"].occurrences), 4)

    def test_a_mirror_image_is_another_part(self) -> None:
        from cad.eng_drawing import parts_list

        parts = parts_list(_stand([(0, 0), (0, 90), (0, 180)], mirrored=True))
        self.assertEqual([(item.description, item.quantity) for item in parts],
                         [("BASE", 1), ("LEG", 2), ("LEG", 1)], "two of one hand, one of the other")

    def test_a_turned_part_of_another_size_is_another_part(self) -> None:
        from build123d import Box, Compound, Pos, Rot
        from cad._internal.drawing_assembly import _same_part

        block = Box(10, 20, 30)
        self.assertTrue(_same_part(block, Pos(50, 0, 0) * Rot(90, 0, 0) * Box(10, 20, 30)))
        self.assertTrue(_same_part(block, Pos(50, 0, 0) * Box(10, 30, 20)), "the same block, built lying down")
        self.assertFalse(_same_part(block, Rot(0, 90, 0) * Box(10, 20, 31)))
        self.assertFalse(_same_part(block, Compound([Box(10, 20, 15), Pos(0, 0, 40) * Box(10, 20, 15)])))


def _layers():
    """A layered part as a small assembly: a 1.5 shell, a 0.1 film on it (too thin
    to hatch at 2:1, so it is filled and named by a callout) and a 0.8 lining."""
    from build123d import Align, Box, Compound, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    layers = []
    for name, low, thick in (("shell", 0.0, 1.5), ("film", 1.5, 0.1), ("lining", 1.6, 0.8)):
        layer = Pos(0, 0, low) * Box(60, 40, thick, align=align)
        layer.label = name
        layers.append(layer)
    return Compound(children=layers, label="case_back")


def _bolted():
    """A base with six ⌀5 holes 10 deep on ⌀60, a spacer ring on it, and a cover on
    the ring with six ⌀5.5 clearance holes over them: two parts carrying one
    pattern, 2 apart, so read off the assembly it is two bolt circles of one size
    on one centre."""
    import math

    from build123d import Align, Compound, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    spots = [(30 * math.cos(math.radians(a)), 30 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    base = Cylinder(40, 20, align=align) - [Pos(x, y, 10) * Cylinder(2.5, 10, align=align) for x, y in spots]
    ring = Pos(0, 0, 20) * (Cylinder(12, 2, align=align) - Cylinder(8, 2, align=align))
    cover = Pos(0, 0, 22) * Cylinder(40, 5, align=align) - [Pos(x, y, 22) * Cylinder(2.75, 5, align=align)
                                                           for x, y in spots]
    base.label, ring.label, cover.label = "base", "ring", "cover"
    return Compound(children=[base, ring, cover], label="lid")


class ReportedFaultTests(unittest.TestCase):
    """Two faults found drawing a large assembly, each of which refused a
    sheet that was sound."""

    def test_a_thin_layer_s_callout_keeps_off_the_material_key(self) -> None:
        """The key is placed before the views are annotated and drawn last: a
        callout that could not see it landed on a key row, and the sheet refused
        itself as crowded."""
        from cad._internal.drawing_render import _render_sheet
        from cad.eng_drawing import Sheet, parts_list

        parts = parts_list(_layers())
        parts.set("shell", material="PC/ABS", family="plastic")
        parts.set("film", material="FILM 0")
        sheet = Sheet("A4", 2.0, title="CASE BACK")
        sheet.view(parts.assembly, "front", at=(80, 150), hidden=False).section("A", parts=parts, materials=True)
        sheet.view(parts.assembly, "top", at=(80, 90), hidden=False)
        texts = [t.dxf.text for t in _render_sheet(sheet, index=1, count=1, label="key").modelspace().query("TEXT")]
        self.assertIn("MATERIAL KEY", texts)
        self.assertIn("FILM 0", texts, "the thin layer is named, clear of the key")

    def test_two_parts_carrying_one_hole_pattern_draw_one_pitch_circle(self) -> None:
        from cad._internal.drawing_render import _render_sheet
        from cad.engine.export.dxf import validate_drawing_document
        from cad.eng_drawing import Sheet, parts_list

        parts = parts_list(_bolted())
        sheet = Sheet("A3", 1.0, title="LID")
        sheet.parts_list(parts)
        sheet.view(parts.assembly, "top", at=(120, 190)).balloons(parts)
        doc = _render_sheet(sheet, index=1, count=1, label="lid")
        pitch = [c for c in doc.modelspace().query("CIRCLE[layer=='CENTER']") if abs(c.dxf.radius - 30) < 1e-6]
        self.assertEqual(len(pitch), 1, "one pitch circle, though two parts' holes are on it")
        codes = {finding.code for finding in validate_drawing_document(doc, drawing=True)}
        self.assertNotIn("duplicate_entity", codes, "which is what refused the sheet")


if __name__ == "__main__":
    unittest.main()
