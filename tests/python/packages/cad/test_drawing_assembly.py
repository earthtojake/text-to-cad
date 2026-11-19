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


if __name__ == "__main__":
    unittest.main()
