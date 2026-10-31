"""What a drawing reads off a part's faces: holes, turned axes, turned diameters.

Every part is built here with build123d, so each expected number is the one it
was built with: a counterbored hole made ⌀6.6 through under a ⌀11 × 6.5 bore
reads exactly that, and a boss or a slot end -- convex, or half a cylinder --
reads as no hole at all.
"""

from __future__ import annotations

import math
import unittest


def _block():
    from build123d import Align, Box, BuildPart, CounterBoreHole, CounterSinkHole, Hole, Locations, Pos

    with BuildPart() as part:
        Box(80, 50, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Pos(-25, 10, 12), Pos(-25, -10, 12)):
            CounterBoreHole(radius=3.3, counter_bore_radius=5.5, counter_bore_depth=6.5)
        with Locations(Pos(0, 0, 12)):
            CounterSinkHole(radius=3, counter_sink_radius=6, counter_sink_angle=90)
        with Locations(Pos(25, 10, 12), Pos(25, -10, 12)):
            Hole(radius=2, depth=5)
    return part.part


class HoleTests(unittest.TestCase):
    def test_every_hole_reads_as_its_callout_would(self) -> None:
        from cadgen._internal.drawing_features import holes

        found = holes(_block())
        by_kind: dict[tuple, list] = {}
        for hole in found:
            by_kind.setdefault(hole.signature(), []).append(hole)
        self.assertEqual(len(found), 5)
        self.assertEqual(len(by_kind), 3, "two counterbored, one countersunk, two blind")

        cbore = next(h for h in found if h.cbore)
        self.assertAlmostEqual(cbore.diameter, 6.6, places=6)
        self.assertTrue(cbore.thru)
        self.assertEqual(tuple(round(v, 6) for v in cbore.cbore), (11.0, 6.5))
        self.assertEqual(cbore.axis, (0.0, 0.0, -1.0), "into the material from the counterbored face")
        self.assertAlmostEqual(cbore.mouth[2], 12.0, places=6)

        csk = next(h for h in found if h.csk)
        self.assertAlmostEqual(csk.diameter, 6.0, places=6)
        self.assertEqual((round(csk.csk[0], 6), csk.csk[1]), (12.0, 90.0))

        blind = [h for h in found if not h.thru]
        self.assertEqual(len(blind), 2)
        for hole in blind:
            self.assertAlmostEqual(hole.diameter, 4.0, places=6)
            self.assertAlmostEqual(hole.depth, 5.0, places=6)
            self.assertAlmostEqual(hole.mouth[2], 12.0, places=6, msg="a blind hole opens where it is open")

    def test_a_boss_and_a_slot_are_not_holes(self) -> None:
        """A boss is a convex cylinder; a slot's ends are half cylinders."""
        from build123d import Align, Box, Cylinder, Pos, SlotCenterToCenter, extrude
        from cadgen._internal.drawing_features import holes

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        boss = Box(60, 40, 5, align=align) + Pos(0, 0, 5) * Cylinder(6, 10, align=align)
        self.assertEqual(holes(boss), [])
        slot = Box(60, 40, 5, align=align) - extrude(SlotCenterToCenter(20, 8), 5)
        self.assertEqual(holes(slot), [])

    def test_a_hole_broken_by_air_is_still_one_hole(self) -> None:
        """A clevis pin hole crosses the gap between the arms; a blind bore can break
        through a cross hole. Judged piece by piece, each read as two holes."""
        from build123d import Align, Box, Cylinder, Pos, Rot
        from cadgen._internal.drawing_features import holes

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        clevis = (Box(30, 30, 6, align=align) + Pos(0, 0, 26) * Box(30, 30, 6, align=align)
                  + Pos(-12, 0, 0) * Box(6, 30, 32, align=align)) - Cylinder(5, 40, align=align)
        found = holes(clevis)
        self.assertEqual(len(found), 1, "one pin hole through both arms")
        self.assertTrue(found[0].thru)

        crossed = (Box(40, 40, 30, align=align) - Pos(0, 0, 5) * Cylinder(3, 25, align=align)
                   - Pos(0, 0, 12) * Rot(0, 90, 0) * Cylinder(5, 60))
        blind = [h for h in holes(crossed) if round(h.diameter, 3) == 6]
        self.assertEqual(len(blind), 1, "the bore below the cross hole is the same bore")
        self.assertFalse(blind[0].thru)
        self.assertAlmostEqual(blind[0].depth, 25.0, places=6)

    def test_a_groove_inside_a_blind_bore_does_not_end_it(self) -> None:
        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_features import holes

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(40, 40, 30, align=align) - Pos(0, 0, 10) * Cylinder(5, 20, align=align) \
            - Pos(0, 0, 18) * Cylinder(6, 3, align=align)
        (hole,) = holes(part)
        self.assertAlmostEqual(hole.diameter, 10.0, places=6)
        self.assertAlmostEqual(hole.depth, 20.0, places=6)

    def test_a_ring_groove_or_a_pocket_round_a_standoff_is_not_a_hole(self) -> None:
        """Concave and full circle, but with material inside: nothing a drill makes."""
        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_features import holes

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(80, 80, 10, align=align)
        groove = plate - Pos(0, 0, 7) * (Cylinder(20, 3, align=align) - Cylinder(15, 3, align=align))
        self.assertEqual(holes(groove), [])
        standoff = plate - Pos(0, 0, 5) * Cylinder(15, 5, align=align) + Pos(0, 0, 5) * Cylinder(5, 5, align=align)
        self.assertEqual(holes(standoff), [])

    def test_a_bore_opened_out_at_both_ends_says_so(self) -> None:
        from build123d import Align, Box, Cone, Cylinder, Pos
        from cadgen._internal.drawing_features import holes

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = (Box(40, 40, 12, align=align) - Cylinder(5, 12, align=align)
                - Pos(0, 0, 11) * Cone(5, 6, 1, align=align) - Cone(6, 5, 1, align=align))
        (hole,) = holes(part)
        self.assertTrue(hole.thru)
        self.assertEqual((round(hole.csk[0], 6), hole.csk[1]), (12.0, 90.0))
        self.assertEqual(hole.far_csk, hole.csk, "the same chamfer at the other end")

    def test_a_bore_split_into_several_faces_is_one_bore(self) -> None:
        """A STEP from some kernels splits a full cylinder into faces."""
        from build123d import Box, Compound, Cylinder, GeomType, Keep, Plane
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

        from cadgen._internal.drawing_features import holes

        plate = Box(40, 40, 10) - Cylinder(3, 10)
        left, right = plate.split(Plane.YZ, keep=Keep.BOTTOM), plate.split(Plane.YZ, keep=Keep.TOP)
        # Fused without unifying faces, as build123d's own fuse would.
        joined = Compound(BRepAlgoAPI_Fuse(left.wrapped, right.wrapped).Shape()).solids()[0]
        self.assertGreater(len([f for f in joined.faces() if f.geom_type == GeomType.CYLINDER]), 1)
        self.assertEqual([(h.diameter, h.thru) for h in holes(joined)], [(6.0, True)])
        self.assertEqual(holes(left), [], "half a bore, a notch in an edge, is not a hole")


class SecondReviewHoleTests(unittest.TestCase):
    """What the second review of the hole reader found reading wrong at exit 0."""

    @staticmethod
    def _counterbored():
        from build123d import Align, Box, Cylinder, Pos

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        return Box(40, 40, 12, align=up) - Cylinder(3.3, 12, align=up) - Pos(0, 0, 5.5) * Cylinder(5.5, 6.5, align=up)

    def test_a_filleted_counterbore_floor_is_one_counterbored_hole(self) -> None:
        from build123d import Axis, GeomType, SortBy
        from cadgen._internal.drawing_features import holes

        part = self._counterbored()
        floor = part.edges().filter_by(GeomType.CIRCLE).filter_by_position(Axis.Z, 5.4, 5.6).sort_by(SortBy.RADIUS)[-1]
        [hole] = holes(part.fillet(0.5, [floor]))
        self.assertEqual((round(hole.diameter, 6), hole.thru, hole.problem), (6.6, True, None))
        self.assertEqual(tuple(round(v, 6) for v in hole.cbore), (11.0, 6.5), "deep to its floor, fillet and all")

    def test_an_end_opened_out_in_steps_is_no_one_callout(self) -> None:
        from build123d import Align, Axis, Box, Cylinder, GeomType, Pos, SortBy
        from cadgen._internal.drawing_features import holes

        part = self._counterbored()
        mouth = part.edges().filter_by(GeomType.CIRCLE).filter_by_position(Axis.Z, 11.9, 12.1).sort_by(SortBy.RADIUS)
        [chamfered] = holes(part.chamfer(0.5, None, mouth[-1:]))
        self.assertEqual((chamfered.csk, chamfered.cbore), (None, None), "no countersink made up of its chamfer")
        self.assertIn("its mouth opens out in 2 steps", chamfered.problem)
        up = (Align.CENTER, Align.CENTER, Align.MIN)
        three = (Box(40, 40, 12, align=up) - Cylinder(3, 12, align=up) - Pos(0, 0, 7) * Cylinder(5, 5, align=up)
                 - Pos(0, 0, 10) * Cylinder(7, 2, align=up))
        [stepped] = holes(three)
        self.assertEqual(stepped.cbore, None, "the middle step is not dropped")
        self.assertIn("a bore ⌀14 for 2, then a bore ⌀10 for 3", stepped.problem)

    def test_a_blind_slot_with_a_hole_in_its_floor_is_blind(self) -> None:
        from build123d import Align, Box, Cylinder, Pos, SlotCenterToCenter, extrude
        from cadgen._internal.drawing_features import holes, slots

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(60, 40, 10, align=up) - Pos(0, 0, 5) * extrude(SlotCenterToCenter(20, 8), 5) - Cylinder(2, 10)
        [slot] = slots(part)
        self.assertEqual((slot.thru, slot.depth), (False, 5.0))
        self.assertEqual([(h.diameter, h.thru) for h in holes(part)], [(4.0, True)], "the hole is its own")

    def test_blind_holes_facing_each_other_across_a_gap_are_two(self) -> None:
        from build123d import Align, Box, Cylinder, Pos, Rot
        from cadgen._internal.drawing_features import holes

        up, centred = (Align.CENTER, Align.CENTER, Align.MIN), (Align.CENTER,) * 3
        channel = Box(10, 30, 30, align=up) + Pos(30, 0, 0) * Box(10, 30, 30, align=up) \
            + Pos(15, 0, 0) * Box(40, 30, 5, align=up)
        channel -= Pos(5, 0, 20) * Rot(0, 90, 0) * Cylinder(3, 10, align=centred)
        channel -= Pos(25, 0, 20) * Rot(0, 90, 0) * Cylinder(3, 10, align=centred)
        found = sorted(((h.mouth, h.axis, h.thru, h.depth) for h in holes(channel)))
        self.assertEqual(found, [((5.0, 0.0, 20.0), (-1.0, 0.0, 0.0), False, 5.0),
                                 ((25.0, 0.0, 20.0), (1.0, 0.0, 0.0), False, 5.0)])


class RevolvedTests(unittest.TestCase):
    """A part turned whole about one principal axis, and parts that are not."""

    def test_a_grooved_ring_is_turned_whole_and_its_largest_diameter_found(self) -> None:
        from build123d import Axis, Cylinder, fillet

        from cadgen._internal.drawing_features import revolved

        ring = Cylinder(28.5, 24) - Cylinder(20, 24)
        ring = fillet(ring.edges().filter_by(Axis.Z, reverse=True).group_by(Axis.Z)[-1], 2)  # tori, with seams
        found = revolved(ring)
        self.assertIsNotNone(found)
        self.assertEqual((found.axis, found.diameter), (2, 57.0))

    def test_a_cross_hole_or_a_flat_is_not_turned_whole(self) -> None:
        from build123d import Box, Cylinder, Pos, Rot

        from cadgen._internal.drawing_features import revolved

        self.assertIsNone(revolved(Cylinder(10, 40) - Rot(90, 0, 0) * Cylinder(2, 30)))
        self.assertIsNone(revolved(Cylinder(10, 40) - Pos(9, 0, 0) * Box(4, 30, 50)))
        self.assertIsNone(revolved(Box(10, 10, 10)))

class PatternTests(unittest.TestCase):
    """Slots and bolt circles: what a callout states as one feature."""

    def test_an_obround_slot_reads_as_its_callout_would(self) -> None:
        from build123d import Align, Box, Pos, SlotCenterToCenter, extrude
        from cadgen._internal.drawing_features import slots

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(80, 40, 6, align=align) - Pos(10, 0, 0) * extrude(SlotCenterToCenter(22, 8), 6)
        (slot,) = slots(plate)
        self.assertAlmostEqual(slot.width, 8.0, places=6)
        self.assertAlmostEqual(slot.length, 30.0, places=6, msg="end to end")
        self.assertTrue(slot.thru)
        self.assertEqual(slot.direction, (1.0, 0.0, 0.0))
        self.assertEqual(sorted(round(e[0], 6) for e in slot.ends), [-1.0, 21.0])
        blind = Box(80, 40, 6, align=align) - Pos(0, 0, 2) * extrude(SlotCenterToCenter(22, 8), 4)
        (pocket,) = slots(blind)
        self.assertFalse(pocket.thru)
        self.assertAlmostEqual(pocket.depth, 4.0, places=6)

    def test_a_blind_slot_with_a_rounded_floor_is_not_thru(self) -> None:
        """Air just past the straight wall is the floor fillet, not the far side."""
        from build123d import Align, Axis, Box, Pos, SlotCenterToCenter, extrude, fillet
        from cadgen._internal.drawing_features import slots

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        pocket = Box(80, 40, 10, align=align) - Pos(0, 0, 4) * extrude(SlotCenterToCenter(20, 8), 6)
        floor = pocket.edges().filter_by_position(Axis.Z, 3.9, 4.1)
        (slot,) = slots(fillet(floor, 1))
        self.assertFalse(slot.thru)
        self.assertAlmostEqual(slot.depth, 6.0, places=4, msg="to the floor, past the fillet")

    def test_a_counterbored_slot_and_three_in_a_row(self) -> None:
        from build123d import Align, Box, Compound, Pos, SlotCenterToCenter, extrude
        from cadgen._internal.drawing_features import slots

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        sunk = (Box(80, 40, 10, align=align) - extrude(SlotCenterToCenter(20, 6), 10)
                - Pos(0, 0, 6) * extrude(SlotCenterToCenter(20, 11), 4))
        (slot,) = slots(sunk)
        self.assertTrue(slot.thru)
        self.assertAlmostEqual(slot.width, 6.0, places=6)
        self.assertEqual(tuple(round(v, 6) for v in slot.cbore), (11.0, 31.0, 4.0))
        row = Box(120, 60, 6, align=align) - Compound(
            [Pos(x, 0, 0) * extrude(SlotCenterToCenter(16, 8), 6) for x in (40, -40, 0)])
        self.assertEqual(sorted(round(sl.length, 6) for sl in slots(row)), [24.0, 24.0, 24.0],
                         "nearest ends pair; three slots in a row stay three")

    def test_a_half_round_notch_is_not_a_slot(self) -> None:
        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_features import slots

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        notched = Box(80, 40, 6, align=align) - Pos(40, 0, 0) * Cylinder(5, 6, align=align)
        self.assertEqual(slots(notched), [])

    def test_a_bolt_circle_needs_equal_spacing_round_a_turned_axis(self) -> None:
        import math

        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_features import bolt_circles

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        flange = Cylinder(40, 10, align=align) - Cylinder(15, 10, align=align)
        for k in range(6):
            a = 2 * math.pi * k / 6
            flange -= Pos(30 * math.cos(a), 30 * math.sin(a), 0) * Cylinder(3, 10, align=align)
        (circle,) = bolt_circles(flange)
        self.assertAlmostEqual(circle.diameter, 60.0, places=6)
        self.assertEqual(len(circle.mouths), 6)

        square = Box(80, 80, 8, align=align)
        for x in (-30, 30):
            for y in (-30, 30):
                square -= Pos(x, y, 0) * Cylinder(3, 8, align=align)
        self.assertEqual(bolt_circles(square), [], "corner holes on a plate are pitches, not a PCD")
        uneven = Cylinder(40, 10, align=align) - Cylinder(15, 10, align=align)
        for degrees in (0, 90, 135):
            a = math.radians(degrees)
            uneven -= Pos(30 * math.cos(a), 30 * math.sin(a), 0) * Cylinder(3, 10, align=align)
        self.assertEqual(bolt_circles(uneven), [], "not equally spaced")
        motor = Box(60, 60, 6, align=align) - Cylinder(11, 6, align=align)
        for x in (-15.5, 15.5):
            for y in (-15.5, 15.5):
                motor -= Pos(x, y, 0) * Cylinder(1.5, 6, align=align)
        self.assertEqual(bolt_circles(motor), [], "a square round a bore on a square plate is pitches")


class TurnedTests(unittest.TestCase):
    def _shaft(self):
        from build123d import Align, Cylinder, Pos, Rot

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        along_x = Rot(0, 90, 0)
        return (Pos(0, 0, 0) * along_x * Cylinder(10, 30, align=align)
                + Pos(30, 0, 0) * along_x * Cylinder(15, 40, align=align)
                + Pos(70, 0, 0) * along_x * Cylinder(10, 30, align=align))

    def test_a_stepped_shaft_has_one_axis_end_to_end(self) -> None:
        from cadgen._internal.drawing_features import axes

        found = axes(self._shaft())
        self.assertEqual(len(found), 1, "three steps on one line are one turned axis")
        xs = sorted((found[0].start[0], found[0].end[0]))
        self.assertAlmostEqual(xs[0], 0.0, places=6)
        self.assertAlmostEqual(xs[1], 100.0, places=6)
        self.assertAlmostEqual(found[0].radius, 15.0, places=6)

    def test_turned_diameters_are_the_outside_steps_not_the_bores(self) -> None:
        from build123d import Box, Cylinder
        from cadgen._internal.drawing_features import turned_diameters

        self.assertEqual(turned_diameters(self._shaft()), [20.0, 30.0])
        self.assertEqual(turned_diameters(Box(40, 40, 10) - Cylinder(5, 10)), [], "a bore is a hole, not a step")

    def test_a_bead_is_not_a_groove_and_a_groove_is_one(self) -> None:
        from build123d import Align, Cylinder, Pos, Torus
        from cadgen._internal.drawing_features import grooves

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        self.assertEqual(grooves(Cylinder(10, 40, align=up) + Pos(0, 0, 20) * Torus(10, 1.5)), [],
                         "material raised round it is a bead")
        found = grooves(Cylinder(10, 40, align=up) - Pos(0, 0, 20) * Torus(10, 1.5))
        self.assertEqual(len(found), 1, found)

    def test_a_fillet_round_a_shoulder_is_not_a_groove(self) -> None:
        from build123d import Axis, fillet
        from cadgen._internal.drawing_features import grooves

        shaft = self._shaft()
        # The two shoulders' inside corners: the ring edges at X = 30 and 70 of the ⌀20 steps.
        corners = [e for e in shaft.edges().filter_by(Axis.X, reverse=True)
                   if abs(e.radius - 10) < 1e-6 and abs(e.center().X - 30) < 1e-6]
        self.assertEqual(grooves(fillet(corners, 2)), [], "a torus rounding a corner is the fillet's note's")


class EdgeTests(unittest.TestCase):
    """Blends and chamfers: what a general note states."""

    def test_rounds_fillets_and_chamfers_are_told_apart(self) -> None:
        from build123d import Align, Axis, Box, Cylinder, Pos, SlotCenterToCenter, chamfer, extrude, fillet
        from cadgen._internal.drawing_features import blends, chamfers

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        block = fillet(Box(60, 40, 20, align=up).edges().filter_by(Axis.Z), 5)
        block = chamfer(block.edges().group_by(Axis.Z)[-1], 1)
        block -= extrude(SlotCenterToCenter(16, 6), 20)
        self.assertEqual(sorted((b.radius, b.concave) for b in blends(block)), [(5.0, False)] * 4,
                         "the corners are rounds; the slot's ends are the slot's")
        self.assertEqual(sorted(c.legs for c in chamfers(block)), [(1.0, 1.0)] * 8,
                         "four flat chamfers and four round the corner arcs")
        pocket = Box(80, 50, 15, align=up) - Pos(0, 0, 5) * Box(40, 20, 10, align=up)
        pocket = fillet(pocket.edges().filter_by(Axis.Z).group_by(lambda e: abs(e.center().X))[0], 3)
        self.assertEqual(sorted((b.radius, b.concave) for b in blends(pocket)), [(3.0, True)] * 4)
        self.assertEqual(blends(Cylinder(10, 40)) + blends(Box(40, 40, 10) - Cylinder(4, 10)), [])
        self.assertEqual(chamfers(Box(40, 40, 10) - Cylinder(4, 10)), [], "a hole is not a chamfer")

    def test_a_shaft_shoulder_fillet_and_its_end_chamfers(self) -> None:
        from build123d import Align, Axis, Cylinder, Pos, chamfer, fillet
        from cadgen._internal.drawing_features import blends, chamfers

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        shaft = Cylinder(10, 40, align=up) + Pos(0, 0, 40) * Cylinder(6, 30, align=up)
        shaft = fillet(shaft.edges().filter_by(lambda e: abs(e.center().Z - 40) < 1e-6 and e.radius < 7), 2)
        shaft = chamfer(shaft.edges().group_by(Axis.Z)[-1], 1)
        shaft = chamfer(shaft.edges().group_by(Axis.Z)[0], 1)
        self.assertEqual([(b.radius, b.concave) for b in blends(shaft)], [(2.0, True)])
        self.assertEqual(sorted(c.legs for c in chamfers(shaft)), [(1.0, 1.0), (1.0, 1.0)])

    def test_full_round_ends_and_points_are_neither_blends_nor_chamfers(self) -> None:
        from build123d import Align, Box, Cone, Cylinder, Pos
        from cadgen._internal.drawing_features import blends, chamfers

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        notch = Box(40, 20, 10, align=up) - Pos(20, 0, 0) * (Box(20, 10, 10, align=up)
                                                             + Pos(-10, 0, 0) * Cylinder(5, 10, align=up))
        link = Box(40, 20, 6, align=up) + Pos(20, 0, 0) * Cylinder(10, 6, align=up) \
            + Pos(-20, 0, 0) * Cylinder(10, 6, align=up)
        self.assertEqual(blends(notch) + blends(link), [], "the end of a notch or a link is its full round")
        pin = Cylinder(3, 20, align=up) + Pos(0, 0, 20) * Cone(3, 0, 3, align=up)
        self.assertEqual(chamfers(pin), [], "a cone that reaches its axis is a point")
        self.assertEqual(chamfers(Cone(36.5, 30, 6, align=up)), [], "a cone that is a part's whole side is its shape")

    def test_a_bevelled_inside_corner_is_no_chamfer_and_no_fillet(self) -> None:
        from build123d import Align, Axis, Box, Pos
        from cadgen._internal.drawing_features import chamfers, sharp_edges
        from cadgen._internal.drawing_report import geometry_notes

        low = (Align.MIN,) * 3
        corner = lambda p, x: p.edges().filter_by(Axis.Y).filter_by_position(Axis.X, x - 0.1, x + 0.1) \
            .filter_by_position(Axis.Z, 4.9, 5.1)
        channel = Box(40, 30, 5, align=low) + Box(5, 30, 30, align=low) + Pos(35, 0, 0) * Box(5, 30, 30, align=low)
        channel = channel.fillet(3, corner(channel, 5))
        channel = channel.chamfer(3, None, corner(channel, 35))
        self.assertEqual(chamfers(channel), [], "a bevel in an inside corner bevels no outside edge")
        self.assertGreater(sharp_edges(channel)[1], 0, "its two edges are inside corners left sharp")
        self.assertFalse([n for n in geometry_notes(channel) if "FILLETS" in n],
                         "so no fillet note claims the bevelled corner is R3")
