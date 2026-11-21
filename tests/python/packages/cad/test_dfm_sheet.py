#!/usr/bin/env python3

"""Sheet metal's measurements of exact geometry (``cad.build123d._dfm_sheet``) and its type side
(``cad._internal.dfm.sheet``): the thickness and where a part is not sheet, bends, flanges in each
convention, the unfold against hand-computed flat lengths, holes and their distances (to an edge, to each
other, to a bend in four conventions), reliefs, hems, curls, notches, tabs and countersinks.

Every part is built here with build123d, so each expected figure is the construction's: an L-bracket's
flat length is its flanges plus ``angle * (r + K t)``, a hole's distance to the bend's tangent line is where
it was cut less its radius.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import build123d as bd

from cad._internal import manufacturing
from cad._internal import sheet_plane as plane
from cad._internal.dfm import sheet as sheet_rules
from cad.build123d import _dfm_brep as brep
from cad.build123d import _dfm_sheet as sheet

# --- parts, built here -----------------------------------------------------------------------------------


def profile(steps: list[tuple], t: float) -> bd.Face:
    """A sheet's cross-section in a sketch's XY: a turtle path along one face of the sheet with the material
    on its left. ``("line", length)``; ``("bend", angle_deg, inside_radius)``: a positive angle turns left,
    toward the material (the path then runs on the bend's outside), a negative one right."""
    x, y, heading = 0.0, 0.0, 0.0
    faces = []
    for step in steps:
        dx, dy = math.cos(heading), math.sin(heading)
        nx, ny = -dy, dx
        if step[0] == "line":
            length = step[1]
            points = [(x, y), (x + length * dx, y + length * dy), (x + length * dx + t * nx, y + length * dy + t * ny),
                      (x + t * nx, y + t * ny)]
            faces.append(bd.make_face(bd.Polyline(*points, close=True)))
            x, y = x + length * dx, y + length * dy
            continue
        _, angle, inside = step
        turn = math.radians(angle)
        path = inside + t if turn > 0 else inside
        cx, cy = (x + path * nx, y + path * ny) if turn > 0 else (x - path * nx, y - path * ny)
        start = math.atan2(y - cy, x - cx)
        first, sweep = (start, turn) if turn > 0 else (start + turn, -turn)
        outer = bd.CenterArc((cx, cy), inside + t, math.degrees(first), math.degrees(sweep))
        inner = bd.CenterArc((cx, cy), inside, math.degrees(first), math.degrees(sweep))
        wire = bd.Wire([outer, bd.Line(outer @ 1, inner @ 1), inner.reversed(), bd.Line(inner @ 0, outer @ 0)])
        faces.append(bd.make_face(wire))
        x, y = cx + path * math.cos(start + turn), cy + path * math.sin(start + turn)
        heading += turn
    return faces[0].fuse(*faces[1:]).clean() if len(faces) > 1 else faces[0]


def bent(steps: list[tuple], t: float, width: float, label: str = "part") -> bd.Part:
    """The profile in XZ extruded ``width`` along +Y: the first flange lies on z = 0 from x = 0."""
    part = bd.extrude(bd.Plane.XZ * profile(steps, t), amount=-width)
    part.label = label
    return part


def centre(steps: list[tuple], t: float) -> bd.Wire:
    """``profile``'s path a t/2 into the sheet (its bends turning left only), in XZ as ``bent`` places it."""
    x, y, heading, edges = 0.0, 0.0, 0.0, []
    for step in steps:
        dx, dy = math.cos(heading), math.sin(heading)
        if step[0] == "line":
            start = (x - t / 2 * dy, y + t / 2 * dx)
            edges.append(bd.Line(start, (start[0] + step[1] * dx, start[1] + step[1] * dy)))
            x, y = x + step[1] * dx, y + step[1] * dy
            continue
        _, angle, inside = step
        cx, cy = x - (inside + t) * dy, y + (inside + t) * dx
        first = math.atan2(y - cy, x - cx)
        edges.append(bd.CenterArc((cx, cy), inside + t / 2, math.degrees(first), angle))
        x, y = cx + (inside + t) * math.cos(first + math.radians(angle)), \
            cy + (inside + t) * math.sin(first + math.radians(angle))
        heading += math.radians(angle)
    return bd.Plane.XZ * bd.Wire(edges)


def tube(path: bd.Wire, t: float) -> bd.Part:
    """A round bar ``t`` across along ``path``: what rounds a ``t`` sheet's edge whole."""
    edge = path.edges()[0]
    ring = bd.Face(bd.Wire(bd.Edge.make_circle(t / 2, bd.Plane(edge @ 0, z_dir=edge % 0))))
    return bd.sweep(ring, path=path, transition=bd.Transition.ROUND)


def rounded(steps: list[tuple], t: float, width: float, sides: int) -> bd.Part:
    """The bracket ``width`` wide, ``sides`` of its sides rounded whole, or (3) its whole outline."""
    if sides < 3:
        part = bd.Pos(0, t / 2 * (sides - 1), 0) * bent(steps, t, width - t / 2 * sides)
        for y in (width - t / 2, t / 2)[:sides]:
            part = part + tube(bd.Pos(0, y, 0) * centre(steps, t), t)
        return part
    inner = [("line", steps[0][1] - t / 2), *steps[1:-1], ("line", steps[-1][1] - t / 2)]
    near, far = (bd.Pos(t / 2, y, 0) * centre(inner, t) for y in (t / 2, width - t / 2))
    path = bd.Wire([*near.edges(), bd.Line(near @ 1, far @ 1), *reversed(far.edges()),
                    bd.Line(far @ 0, near @ 0)])
    return bd.Pos(t / 2, t / 2, 0) * bent(inner, t, width - t) + tube(path, t)


def _wall(t: float, r: float, length: float, height: float) -> bd.Part:
    """A bend and a wall rising from a plate's edge at x = 0 (plate below z = t), ``length`` along y."""
    centre = t + r
    ring = bd.Pos(0, 0, centre) * (bd.Rot(90, 0, 0) * (bd.Cylinder(r + t, length) - bd.Cylinder(r, length)))
    quarter = ring & (bd.Pos((r + t) / 2, 0, centre - (r + t) / 2) * bd.Box(r + t, length, r + t))
    return quarter + bd.Pos(r + t / 2, 0, centre + height / 2) * bd.Box(t, length, height)


def tabbed(t: float = 2.0, r: float = 2.0, base: tuple[float, float] = (60.0, 60.0), width: float = 30.0,
           height: float = 20.0, relief: tuple[float, float] | None = None, label: str = "tabbed") -> bd.Part:
    """A plate (x from -L to 0) with one wall narrower than its edge bent up at x = 0; ``relief`` (width,
    depth from the tangent line) cut into the plate at each end of the bend."""
    length, across = base
    part = bd.Pos(-length / 2, 0, t / 2) * bd.Box(length, across, t) + _wall(t, r, width, height)
    if relief:
        cut, depth = relief
        for sign in (1, -1):
            part -= bd.Pos(-depth / 2, sign * (width / 2 + cut / 2), t / 2) * bd.Box(depth, cut, 3 * t)
    part = part.clean()
    part.label = label
    return part


def tray(size: float = 60.0, t: float = 1.5, r: float = 1.5, height: float = 20.0, corner: float | None = None,
         label: str = "tray") -> bd.Part:
    """A square plate centred at the origin with a wall bent up along each edge, as long as the edge; the
    corners open, ``corner`` a square corner relief that size cut at each corner, through the plate and the
    bends' ends and 1 mm on into the walls (past both tangent lines)."""
    part = bd.Pos(0, 0, t / 2) * bd.Box(size, size, t)
    for angle in (0, 90, 180, 270):
        part = part + bd.Rot(0, 0, angle) * (bd.Pos(size / 2, 0, 0) * _wall(t, r, size, height))
    if corner:
        for sx in (1, -1):
            for sy in (1, -1):
                part -= bd.Pos(sx * size / 2, sy * size / 2, 0) * bd.Box(2 * corner, 2 * corner, 2 * (t + r + 1))
    part = part.clean()
    part.label = label
    return part


OPTIONS = {"thickness": None, "k_factor": 0.4, "material": None}


def measured(shape: bd.Shape, **options) -> dict:
    return sheet.measure(brep.parts_of(shape), {**OPTIONS, **options}, False)


def items(report: dict, family: str) -> list[dict]:
    return report[family]["items"]


class ThicknessTest(unittest.TestCase):
    def test_a_bracket_is_one_sheet_of_its_thickness(self) -> None:
        report = measured(bent([("line", 40), ("bend", 90, 1.0), ("line", 30)], 2.0, 50, "L"))
        part = items(report, "parts")[0]
        self.assertAlmostEqual(part["thickness_mm"], 2.0, places=6)
        self.assertTrue(part["is_sheet"])
        self.assertEqual(part["sheet_area_fraction"], 1.0)
        self.assertEqual(items(report, "not_sheet"), [])

    def test_a_boss_and_a_pocket_are_not_sheet_at_their_faces(self) -> None:
        plate = bd.Pos(0, 0, 1.5) * bd.Box(60, 40, 3)
        boss = plate + bd.Pos(15, 0, 3) * bd.Cylinder(4, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        pocket = plate - bd.Pos(-15, 0, 2.5) * bd.Box(10, 10, 2)
        for shape, centre, kinds in ((boss, (15, 0), {"thicker", "unpaired"}), (pocket, (-15, 0), {"thinner", "unpaired"})):
            shape.label = "plate"
            report = measured(shape)
            part = items(report, "parts")[0]
            self.assertAlmostEqual(part["thickness_mm"], 3.0, places=6)
            found = items(report, "not_sheet")
            self.assertTrue(found)
            self.assertTrue({item["kind"] for item in found} <= kinds | {"thicker", "thinner"})
            for item in found:
                self.assertLess(math.dist(item["xyz"][:2], centre), 6.0, item)  # every place is the feature's
                self.assertGreater(item["deviation_mm"], 0.0)
        top = next(i for i in items(measured(boss), "not_sheet") if i["surface"] == "plane" and i["xyz"][2] > 7)
        self.assertAlmostEqual(top["deviation_mm"], 5.0, places=6)  # a 5 mm boss on 3 mm sheet: 8 mm across

    def test_a_filleted_machined_block_is_not_sheet(self) -> None:
        block = bd.fillet(bd.Box(60, 40, 20).edges(), 3)
        block.label = "block"
        part = items(measured(block), "parts")[0]
        self.assertFalse(part["is_sheet"])
        self.assertIn("sheet", part["why"])

    def test_a_washer_ring_is_a_cut_outline_not_a_bend(self) -> None:
        washer = bd.Cylinder(12, 2) - bd.Cylinder(10, 2)
        washer.label = "washer"
        report = measured(washer)
        self.assertEqual(items(report, "bends"), [])
        self.assertTrue(items(report, "parts")[0]["is_sheet"])


class BendTest(unittest.TestCase):
    def test_an_l_brackets_bend(self) -> None:
        report = measured(bent([("line", 40), ("bend", 90, 1.0), ("line", 30)], 2.0, 50, "L"))
        (bend,) = items(report, "bends")
        self.assertEqual(bend["kind"], "bend")
        self.assertAlmostEqual(bend["inside_radius_mm"], 1.0, places=6)
        self.assertAlmostEqual(bend["outside_radius_mm"], 3.0, places=6)
        self.assertAlmostEqual(bend["angle_deg"], 90.0, places=4)
        self.assertAlmostEqual(bend["flanges_angle_deg"], 90.0, places=4)
        self.assertAlmostEqual(bend["length_mm"], 50.0, places=6)
        self.assertAlmostEqual(abs(bend["axis"][1]), 1.0, places=6)
        self.assertAlmostEqual(bend["bend_allowance_mm"], math.pi / 2 * (1.0 + 0.4 * 2.0), places=4)
        # the inside tangent lines: on the bottom flange's top face at x = 40, on the wall's inside at z = 3
        tangents = {(round(line[0][0], 4), round(line[0][2], 4)) for line in bend["tangent_lines"]}
        self.assertTrue({(40.0, 2.0), (40.0, 0.0), (41.0, 3.0), (43.0, 3.0)} <= tangents)
        self.assertTrue(bend["location"].endswith(tuple(f"face {n}" for n in range(1, 20))))

    def test_angles_hems_and_curls(self) -> None:
        for angle, kind in ((45, "bend"), (135, "bend"), (180, "hem"), (270, "curl")):
            steps = [("line", 30), ("bend", angle, 2.0)] + ([("line", 10)] if angle < 270 else [])
            report = measured(bent(steps, 1.0, 20, "bent"))
            (bend,) = items(report, "bends")
            self.assertEqual(bend["kind"], kind, angle)
            self.assertAlmostEqual(bend["angle_deg"], angle, places=3)
            self.assertAlmostEqual(bend["included_angle_deg"], 180 - angle, places=3)
            if kind == "hem":
                (hem,) = items(report, "hems")
                self.assertAlmostEqual(hem["inside_diameter_mm"], 4.0, places=6)
                self.assertAlmostEqual(hem["return_length_mm"], 10.0, places=4)
            if kind == "curl":
                self.assertEqual(len(items(report, "curls")), 1)
        # a hem's mold lines meet nowhere: no bend deduction (tan 89 degrees made it 338 mm)
        (hem,) = items(measured(bent([("line", 30), ("bend", 178, 1.0), ("line", 10)], 2.0, 20, "hem")), "bends")
        self.assertEqual((hem["kind"], hem["bend_deduction_mm"]), ("hem", None))


class TurnedTest(unittest.TestCase):
    def test_a_part_turned_in_its_model_reads_the_same(self) -> None:
        part = bent([("line", 40), ("bend", 90, 1.0), ("line", 30)], 2.0, 50, "L")
        part = part - bd.Pos(20, -25, 0) * bd.Cylinder(3, 10)

        def read(shape: bd.Shape) -> tuple:
            result = checked(shape)
            (body,) = result.measurements["parts"]["items"]
            (bend,) = result.measurements["bends"]["items"]
            return (result.ok, sorted({f.code for f in result.findings if f.severity != "info"}),
                    body["thickness_mm"], body["flat_length_mm"], body["flat_width_mm"], bend["angle_deg"],
                    bend["inside_radius_mm"], len(result.measurements["holes"]["items"]))

        drawn = read(part)
        for turn in (bd.Rot(0, 0, 30), bd.Rot(17, 23, 41)):
            turned = read(turn * part)
            self.assertEqual(turned[:2] + turned[-1:], drawn[:2] + drawn[-1:])
            for a, b in zip(turned[2:-1], drawn[2:-1]):
                self.assertAlmostEqual(a, b, delta=1e-3 * max(1.0, abs(b)))

    def test_a_plate_is_the_same_sheet_however_it_stands(self) -> None:
        # a scalloped strip 9 mm wide and 2 thick, its faces' widths read in their own frames, never a world box's;
        # and a plate whose top face lies exactly half over a step: a skin wherever it stands, its share of rays
        # across counted (a sum of its samples' equal areas read 0.4999999 placed the last way: one skin, 18% sheet)
        strip = bd.Pos(0, 0, 1) * bd.Box(40, 9, 2)
        for x in (-10, 0, 10):
            strip -= bd.Pos(x, 4.5, 0) * bd.Cylinder(1.5, 6)
        stepped = bd.Pos(0, 0, 1) * bd.Box(40, 10, 2) + bd.Pos(-10, 0, -1) * bd.Box(20, 10, 2)
        for shape in (strip.clean(), stepped.clean()):
            for turn in (bd.Rot(0, 0, 0), bd.Rot(0, 0, 45), bd.Rot(45, 0, 0), bd.Pos(7, -3, 11) * bd.Rot(23, -37, 61)):
                (part,) = items(measured(turn * shape), "parts")
                self.assertTrue(part["is_sheet"], (turn, part.get("why")))
                self.assertEqual((part["skin_faces"], part["thickness_mm"]), (2, 2.0), turn)


class UnfoldTest(unittest.TestCase):
    """The flat pattern against lengths computed by hand: flanges from their tangent lines plus each bend's
    allowance, BA = angle * (r + K t)."""

    def test_an_l_bracket_with_known_k(self) -> None:
        t, r, k = 2.0, 1.0, 0.33
        part = bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 50, "L")
        # the flat flanges from the tangent lines: the base 40 and the wall 30 (the profile's own lengths)
        expected = 40 + 30 + math.pi / 2 * (r + k * t)
        report = measured(part, k_factor=k)
        flat = items(report, "parts")[0]
        self.assertAlmostEqual(flat["flat_length_mm"], expected, places=4)
        self.assertAlmostEqual(flat["flat_width_mm"], 50.0, places=4)
        face = sheet.unfold(part, k_factor=k)
        self.assertAlmostEqual(face.area, expected * 50, places=2)
        box = face.bounding_box()
        self.assertAlmostEqual(box.size.Z, 0.0, places=6)
        self.assertAlmostEqual(max(box.size.X, box.size.Y), expected, places=4)

    def test_a_u_channel_with_known_k_and_its_hand_lengths(self) -> None:
        t, r, k = 1.5, 2.0, 0.42
        part = bent([("line", 25), ("bend", 90, r), ("line", 60), ("bend", 90, r), ("line", 25)], t, 80, "U")
        report = measured(part, k_factor=k)
        allowance = math.pi / 2 * (r + k * t)
        self.assertAlmostEqual(items(report, "parts")[0]["flat_length_mm"], 25 + 60 + 25 + 2 * allowance, places=4)
        flanges = sorted(round(item["length_tangent_mm"], 4) for item in items(report, "flanges"))
        self.assertEqual(flanges, [25.0, 25.0, 60.0, 60.0])  # the base measured from each of its bends
        base = next(item for item in items(report, "flanges") if round(item["length_tangent_mm"]) == 60)
        self.assertAlmostEqual(base["length_inside_mm"], 60 + r, places=4)
        self.assertAlmostEqual(base["length_outside_mm"], 60 + r + t, places=4)
        (channel,) = items(report, "channels")
        self.assertAlmostEqual(channel["base_length_mm"], 60 + 2 * (r + t), places=4)
        self.assertAlmostEqual(channel["base_to_flange_ratio"], (60 + 2 * (r + t)) / (25 + r + t), places=4)

    def test_k_half_unfolds_onto_the_volume_and_holes_survive(self) -> None:
        part = bent([("line", 30), ("bend", 90, 3.0), ("line", 20), ("bend", -90, 3.0), ("line", 30)], 2.0, 40, "Z")
        part = part - bd.Pos(10, 20, 0) * bd.Cylinder(3, 10) - bd.Pos(50, 20, 29) * bd.Box(8, 4, 10)
        part.label = "Z"
        report = measured(part, k_factor=0.5)
        flat = items(report, "parts")[0]
        self.assertAlmostEqual(flat["neutral_area_ratio"], 1.0, places=6)  # at K = 0.5 the flat is volume / t
        cut = sheet.unfold(part, k_factor=0.5, bend_lines=True)
        self.assertEqual([child.label for child in cut.children], ["CUT", "BEND"])
        outline, lines = cut.children
        self.assertEqual(len(outline.faces()[0].inner_wires()), 2)
        self.assertEqual(len(lines.edges()), 2)
        # The lines are one shape, not an assembly of them: a child would be a part of its own, which a DXF writes
        # on a layer of its own name and the cut-file check then reads as an open cut.
        self.assertEqual(len(lines.children), 0)
        round_holes = [i for i in items(report, "holes") if i["kind"] == "round"]
        self.assertEqual([i["diameter_mm"] for i in round_holes], [6.0])
        # a flat plate has no bend line, and unfolds to the same two layers, one of them empty
        cut = sheet.unfold(bd.Box(100, 60, 2), bend_lines=True)
        self.assertEqual([child.label for child in cut.children], ["CUT", "BEND"])
        outline, lines = cut.children
        self.assertAlmostEqual(outline.area, 6000.0, places=6)
        self.assertEqual(len(lines.edges()), 0)

    def test_the_flat_overlaps_where_flanges_collide_in_it_and_not_where_a_fuse_loses_area(self) -> None:
        t, r = 2.0, 2.0

        def eared(side: float) -> bd.Part:
            """A wall bent up at the plate's edge x = 0, an ear on its side reaching 20 mm past the plate's corner."""
            return _wall(t, r, 60, 20) + bd.Pos(r + t / 2, side * 40, t + r + 10) * bd.Box(t, 20, 20)

        # one wall bent up at x = 0 and one down at y = 30, each with an ear past their shared corner: clear of
        # each other as bent, and on one another in the flat over the square the two ears share
        down = bd.mirror(bd.Pos(-30, 30, 0) * bd.Rot(0, 0, 90) * eared(-1.0), bd.Plane.XY.offset(t / 2))
        part = (bd.Pos(-30, 0, t / 2) * bd.Box(60, 60, t) + eared(1.0) + down).clean()
        part.label = "eared"
        allowance = math.pi / 2 * (r + 0.4 * t)
        flat = items(measured(part), "parts")[0]
        self.assertAlmostEqual(flat["flat_overlap_mm2"], (20 - allowance) ** 2, places=2)
        self.assertIn("sheet.flat_overlap", [f.code for f in checked(part).findings if f.severity == "error"])
        # a bracket with a hole in its wall, its planes and cylinders written as NURBS (as some CAD writes a STEP):
        # the fused flat's area is a square millimetre short of its pieces', and nothing lies on anything
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

        bracket = bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 50)
        bracket = bracket - bd.Pos(43, 12, 20) * bd.Rot(0, 90, 0) * bd.Cylinder(2.75, 20)
        nurbs = bd.Part(BRepBuilderAPI_NurbsConvert(bracket.wrapped, True).Shape())
        nurbs.label = "bracket"
        self.assertIsNone(items(measured(nurbs), "parts")[0]["flat_overlap_mm2"])
        self.assertEqual(verdicts(checked(nurbs)), [])

    def test_not_sheet_refuses_to_unfold(self) -> None:
        with self.assertRaisesRegex(ValueError, "not sheet metal"):
            sheet.unfold(bd.Sphere(10))


class HoleTest(unittest.TestCase):
    def test_hole_sizes_and_distances_in_each_convention(self) -> None:
        t, r, k = 2.0, 2.0, 0.4
        part = bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 50, "holes")
        # in the base (z 0..2, bend tangent at x = 40): a 4 mm hole 3 mm from the tangent line, a 2 mm hole
        # 4 mm from the far edge, and a slot 3 wide
        part = part - bd.Pos(35, 25, 1) * bd.Cylinder(2, 10) - bd.Pos(5, 10, 1) * bd.Cylinder(1, 10)
        part = part - bd.Pos(10, 40, -5) * bd.extrude(bd.SlotCenterToCenter(8, 3), 10)
        part.label = "holes"
        report = measured(part, k_factor=k)
        holes = {round(item["size_mm"], 4): item for item in items(report, "holes")}
        self.assertEqual(sorted(holes), [2.0, 3.0, 4.0])
        self.assertEqual(holes[3.0]["kind"], "slot")
        self.assertAlmostEqual(holes[3.0]["length_mm"], 11.0, places=3)
        self.assertAlmostEqual(holes[2.0]["edge_distance_mm"], 4.0, places=4)  # x = 5, r = 1
        near = next(item for item in items(report, "hole_to_bend") if item["location"] == holes[4.0]["location"])
        half = math.pi / 2 * (r + k * t) / 2
        self.assertAlmostEqual(near["distance_tangent_mm"], 3.0, places=4)
        self.assertAlmostEqual(near["distance_centerline_mm"], 3.0 + half, places=4)
        self.assertAlmostEqual(near["distance_inside_mm"], 3.0 + r, places=4)
        self.assertAlmostEqual(near["distance_outside_mm"], 3.0 + r + t, places=4)
        spacing = items(report, "hole_spacing")
        self.assertTrue(all(item["distance_mm"] > 0 for item in spacing))
        # each ref names the hole's own wall
        part_doc = brep.parts_of(part).parts[0]
        wall = part_doc.faces()[int(holes[4.0]["location"].split()[-1]) - 1]
        self.assertAlmostEqual(brep.surface(wall).radius, 2.0, places=6)

    def test_a_countersink(self) -> None:
        with bd.BuildPart() as built:
            bd.Box(80, 50, 3)
            with bd.Locations((0, 0, 1.5)):
                bd.CounterSinkHole(radius=1.6, counter_sink_radius=3.2)
        report = measured(built.part)
        (hole,) = items(report, "holes")
        self.assertEqual((hole["size_mm"], hole["countersunk"], hole["countersink_diameter_mm"]), (3.2, True, 6.4))
        self.assertEqual(items(report, "not_sheet"), [])


    def test_close_holes_in_a_flat_plate_are_a_recommendation(self) -> None:
        # 2 mm apart edge to edge in a 2 mm plate, under Hubs's 2 t: a best practice for laser cutting whose
        # risk is the forming's -- a warning, never an error, however the plate is turned
        plate = bd.Box(60, 40, 2) - bd.Pos(-3, 0, 0) * bd.Cylinder(1.5, 4) - bd.Pos(2, 0, 0) * bd.Cylinder(1.5, 4)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(30, 0, 45) * bd.Pos(5, 1, 2)):
            result = checked(turn * plate, material="aluminum")
            self.assertEqual({f.severity for f in result.findings if f.code == "sheet.hole_spacing"}, {"warning"})
            self.assertAlmostEqual(failed(result, "sheet.hole_spacing")[0]["value"], 2.0, places=3)


class GrilleTest(unittest.TestCase):
    def test_a_grilles_bars_are_webs_judged_once(self) -> None:
        t = 3.0

        def grille(pitch: float) -> bd.Part:
            plate = bd.Pos(0, 0, t / 2) * bd.Box(140, 120, t)
            for i in range(17):  # slots 4 mm wide: 16 bars between them, pitch - 4 mm each
                plate -= bd.Pos(-8 * pitch + i * pitch, 0, t / 2) * bd.Box(4, 100, 3 * t)
            plate.label = "grille"
            return plate

        # bars half the thickness wide: one feature, one finding -- not one for each pair of slots
        thin = checked(grille(5.5))
        self.assertEqual(verdicts(thin), [("warning", "sheet.web_width")])
        (finding,) = [f for f in thin.findings if f.code == "sheet.web_width"]
        self.assertIn("1.5 mm is under the 3 mm recommended minimum (between 17 cutouts)", finding.message)
        (web,) = [item for item in items(thin.measurements, "webs") if "cutouts" in item]
        self.assertEqual((web["width_mm"], web["cutouts"]), (1.5, 17))
        self.assertEqual(items(thin.measurements, "hole_spacing"), [])
        # bars over the thickness and under the two a pair of round holes is asked: a grille as grilles are made
        self.assertEqual(verdicts(checked(grille(8.0))), [])


class ReliefTest(unittest.TestCase):
    def test_a_missing_relief_and_one_present(self) -> None:
        bare = measured(tabbed(label="bare"))
        reliefs = items(bare, "reliefs")
        self.assertEqual(len(reliefs), 2)
        self.assertTrue(all(item["needed"] and not item["present"] and item["width_mm"] == 0 for item in reliefs))
        cut = measured(tabbed(relief=(3.0, 6.0), label="cut"), k_factor=0.4)
        reliefs = items(cut, "reliefs")
        self.assertEqual(len(reliefs), 2)
        half = math.pi / 2 * (2.0 + 0.4 * 2.0) / 2
        for item in reliefs:
            self.assertTrue(item["present"])
            self.assertAlmostEqual(item["width_mm"], 3.0, places=3)
            self.assertAlmostEqual(item["depth_tangent_mm"], 6.0, places=4)
            self.assertAlmostEqual(item["depth_centerline_mm"], 6.0 + half, places=4)

    def test_a_full_width_bend_needs_none_and_a_trays_corners_are_corner_reliefs(self) -> None:
        self.assertEqual(items(measured(bent([("line", 40), ("bend", 90, 2.0), ("line", 20)], 2.0, 30)), "reliefs"), [])
        corners = items(measured(tray()), "reliefs")
        self.assertEqual(len(corners), 8)
        self.assertTrue(all(item["kind"] == "corner" and not item["present"] for item in corners))
        relieved = items(measured(tray(corner=2.0)), "reliefs")
        self.assertTrue(relieved and all(item["present"] for item in relieved))
        self.assertTrue(all(item["kind"] == "corner" for item in relieved))  # a corner, relieved or not


class OutlineTest(unittest.TestCase):
    def test_a_notch_and_a_tab_on_a_plate(self) -> None:
        plate = bd.Pos(0, 0, 1) * bd.Box(80, 40, 2)
        plate -= bd.Pos(0, 20 - 6, 1) * bd.Box(2, 12, 4)                 # a notch 2 wide, 12 deep
        plate += bd.Pos(40 + 7.5, 0, 1) * bd.Box(15, 5, 2)               # a tab 5 wide, 15 long
        plate = plate.clean()
        plate.label = "plate"
        report = measured(plate)
        notch = min(items(report, "notches"), key=lambda item: item["width_mm"])
        self.assertAlmostEqual(notch["width_mm"], 2.0, places=4)
        self.assertAlmostEqual(notch["length_mm"], 12.0, places=4)
        self.assertAlmostEqual(notch["length_to_width"], 6.0, places=4)
        tab = min(items(report, "tabs"), key=lambda item: item["width_mm"])
        self.assertAlmostEqual(tab["width_mm"], 5.0, places=4)
        self.assertAlmostEqual(tab["length_mm"], 15.0, places=4)
        self.assertGreater(tab["xyz"][0], 40.0)  # located at the tab

    def test_the_hull_keeps_the_corners_of_a_side_that_is_vertical_but_for_rounding(self) -> None:
        # a flat's outline as an unfold laid it: the points of its two vertical sides differ in x by rounding
        # (1e-15), so they come sorted by that and not by y. The hull dropped the corners (-50, -37) and
        # (0, 31.4), and the flat read 77.262 x 37.377 for 68.398 x 50
        low, top = 9.39822971502571, 31.39822971502571
        points = [(-6.0, -12.0), (-6.0, low), (9.369662123902149e-17, low), (5.523736751135049e-17, top),
                  (-50.00000000000001, top), (-50.0, low), (-44.0, 9.398229715025709), (-44.0, -12.0),
                  (-50.0, -12.0), (-50.0, -37.0), (2.613352407788645e-15, -37.0), (-5.492429656686475e-18, -12.0)]
        self.assertEqual(plane.hull(points).tolist(), [4, 9, 10, 3])
        long, short, _ = plane.min_rectangle(points)
        self.assertAlmostEqual(long, top + 37.0, places=9)
        self.assertAlmostEqual(short, 50.0, places=9)


class TypeSideTest(unittest.TestCase):
    def test_k_factor_defaults(self) -> None:
        self.assertEqual(sheet_rules.k_factor("aluminum", 0.5, 1.0)[0], 0.33)
        self.assertEqual(sheet_rules.k_factor("stainless", 2.0, 1.0)[0], 0.45)
        k, said = sheet_rules.k_factor(None, 4.0, 1.0)
        self.assertEqual(k, 0.50)
        self.assertIn("no material given: medium (steel)", said)

    def test_context_scales_tabs_and_takes_the_sheet_given(self) -> None:
        report = {"parts": {"items": [{"thickness_mm": 2.0}]}, "bends": {"items": [{"inside_radius_mm": 2.0}]},
                  "tabs": {"items": [{"width_mm": 5.0, "thickness_mm": 3.0}]}}
        found = sheet_rules.context(report, {"material": "steel"})
        self.assertEqual((found["tab_min_mm"], found["notch_min_mm"]), (4.0, 2.0))
        # an item scales by its own part's thickness, and by the stock's where --thickness names it
        self.assertEqual(report["tabs"]["items"][0]["tab_min_mm"], 6.0)
        sheet_rules.context(report, {"thickness": 1.0})
        self.assertEqual(report["tabs"]["items"][0]["tab_min_mm"], 3.2)
        self.assertEqual((found["sheet_long_mm"], found["sheet_short_mm"], found["sheet_given"]),
                         (*sheet_rules.DEFAULT_SHEET, False))
        found = sheet_rules.context(report, {"material": "aluminum", "sheet_size": "300x500"})
        self.assertEqual((found["sheet_long_mm"], found["sheet_short_mm"], found["sheet_given"]), (500.0, 300.0, True))

    def test_the_flat_on_a_sheet_given_is_an_error_on_the_standard_sheet_a_warning(self) -> None:
        from cad._internal.dfm import rules

        report = {"parts": {"items": [{"thickness_mm": 2.0, "is_sheet": True, "flat_length_mm": 600.0,
                                       "flat_width_mm": 100.0, "location": "p/face 1"}]}}
        # the sheet given is the user's own figure: a finding of fact that cites no guide, and no rule's verdict
        self.assertEqual(rules.evaluate(report, sheet_rules.RULES,
                                        sheet_rules.context(report, {"sheet_size": "500x300"}))[0], [])
        (given,) = sheet_rules.findings(report, {"sheet_size": "500x300"}, False)
        self.assertEqual((given.code, given.severity), ("sheet.flat_length", "error"))
        self.assertIn("600 mm is over the 500 mm of the 500 x 300 mm sheet given (--sheet-size)", given.message)
        self.assertNotIn("source", given.message)
        report["parts"]["items"][0]["flat_length_mm"] = 3100.0
        assumed, _ = rules.evaluate(report, sheet_rules.RULES, sheet_rules.context(report, {}))
        self.assertEqual([(f.code, f.severity) for f in assumed], [("sheet.flat_length", "warning")])
        self.assertIn("give --sheet-size", assumed[0].hint)

    def test_a_flat_no_plate_holds_is_an_error_of_text_to_cads_own(self) -> None:
        # longer than a 10 x 40 ft plate, the largest stocked: cut from no one plate, wherever it lies
        for placed in (bd.Box(20000, 3000, 2), turned(bd.Box(20000, 3000, 2))):
            result = checked(placed)
            (limit,) = [f for f in result.findings if f.severity == "error"]
            self.assertEqual((limit.code, limit.value, limit.limit), ("sheet.flat_length_limit", 20000.0, 12192.0))
            self.assertTrue(limit.source.startswith("cad, its own figure"), limit.source)
        # one such a plate holds is over the standard sheet assumed, a warning; and the shop's own sheet rules
        self.assertEqual({code for severity, code in verdicts(checked(bd.Box(12000, 3000, 2)))},
                         {"units_suspect", "sheet.flat_length", "sheet.flat_width"})
        self.assertEqual(verdicts(checked(bd.Box(20000, 3000, 2), sheet_size="20000x3000")),
                         [("warning", "units_suspect")])

    def test_a_bend_relief_is_as_wide_as_the_thickness(self) -> None:
        from cad._internal.dfm import rules

        report = {"parts": {"items": [{"thickness_mm": 2.0, "is_sheet": True}]}, "bends": {"items": [{}]},
                  "reliefs": {"items": [{"kind": "bend", "width_mm": width, "location": f"p/face {n}", "detail": "d"}
                                        for n, width in ((1, 1.9), (2, 2.1))]}}
        _, record = rules.evaluate(report, sheet_rules.RULES, sheet_rules.context(report, {"material": "steel"}))
        (width,) = [o for o in record["outcomes"] if o["rule"] == "sheet.bend_relief_width"]
        self.assertEqual([(f["value"], f["location"]) for f in width["failures"]], [(1.9, "p/face 1")])

    def test_options_and_findings(self) -> None:
        with self.assertRaisesRegex(ValueError, "--sheet-size"):
            manufacturing.options("step", "sheet", {"sheet_size": "big"})
        report = {"parts": {"items": [{"thickness_mm": 2.0, "is_sheet": True, "location": "p/face 1"}]},
                  "bends": {"items": [{"inside_radius_mm": 2.0, "location": "p/face 4"}]},
                  "holes": {"items": [{"size_mm": 0.2, "location": "p/face 9"}]}}
        codes = {f.code for f in sheet_rules.findings(report, {"thickness": 1.5, "bend_radius": 1.0, "kerf": 0.3},
                                                      False)}
        self.assertTrue({"sheet.thickness_mismatch", "sheet.bend_radius_differs", "sheet.under_kerf"} <= codes)

    def test_a_check_through_the_step_reads_refs_that_resolve(self) -> None:
        from cad import step
        from cad.engine import refs
        from cad.engine.document import Loaded

        part = bent([("line", 40), ("bend", 90, 0.5), ("line", 30)], 2.0, 50, "bracket")
        part = part - bd.Pos(38, 25, 1) * bd.Cylinder(0.6, 10)
        part.label = "bracket"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bracket.step"
            bd.export_step(part, str(path))
            result = step.dfm(path, process="sheet")
            codes = {f.code for f in result.findings}
            self.assertTrue({"sheet.bend_radius", "sheet.hole_to_bend", "sheet.hole_diameter"} <= codes, codes)
            structure = Loaded(path).structure()
            for finding in result.findings:
                if finding.location and "/face " in finding.location:
                    hits = refs.resolve_structure(structure, finding.location, path)
                    self.assertEqual(len(hits), 1, finding.location)
            # what no rule's verdict says names its faces as data too: a sharp corner's, a chamfered edge's, a
            # block's -- each ref one `cad step inspect` resolves, the finding's location the first
            sharp = _boxes_bracket()
            chamfered = bd.Pos(100, 0, 0) * bd.chamfer(bd.Box(80, 40, 3).edges(), 0.5)
            chamfered.label = "chamfered"
            block = bd.Pos(0, 100, 0) * bd.Box(50, 40, 30)
            block.label = "block"
            path = Path(folder) / "three.step"
            bd.export_step(bd.Compound(children=[sharp, chamfered, block]), str(path))
            result = step.dfm(path, process="sheet")
            structure = Loaded(path).structure()
            found = {f.code: f for f in result.findings}
            for code, count in (("sheet.sharp_bend", 4), ("sheet.edge_break", 16), ("sheet.not_sheet", 1)):
                finding = found[code]   # (the corner's two faces inside and two outside; the skins' chamfers)
                self.assertEqual(len(finding.refs), count, (code, finding.refs))
                self.assertEqual(finding.refs[0], finding.location)
                for ref in finding.refs:
                    self.assertEqual(len(refs.resolve_structure(structure, ref, path)), 1, ref)
            self.assertEqual((found["sheet.sharp_bend"].value, found["sheet.sharp_bend"].unit), (90.0, "deg"))
            self.assertEqual((found["sheet.edge_break"].value, found["sheet.edge_break"].unit), (0.5, "mm"))


def checked(shape: bd.Shape, **options):
    """The whole check of a live shape, as an agent's script runs it."""
    from cad import build123d as cb

    return cb.sheet_metal(shape, **options)


def verdicts(result) -> list[tuple[str, str]]:
    """The errors and warnings of a result: (severity, code), sorted."""
    return sorted((f.severity, f.code) for f in result.findings if f.severity in ("error", "warning"))


def turned(shape: bd.Shape, degrees: float = 37.0) -> bd.Shape:
    """``shape`` turned about a skew axis and moved: no face of it along a world axis."""
    return shape.rotate(bd.Axis((0, 0, 0), (1, 2, 3)), degrees).translate((13.3, -7.1, 4.4))


class RecognitionTest(unittest.TestCase):
    """What is sheet is read off the part's own faces, never its box in the world: the same wherever it stands."""

    def placements(self, shape: bd.Shape):
        return (shape, turned(shape), shape.rotate(bd.Axis.Y, 45), shape.rotate(bd.Axis((0, 0, 0), (1, 0.3, 0.2)), 0.4))

    def test_a_small_bracket_and_a_narrow_strip_are_sheet_in_every_placement(self) -> None:
        bracket = bent([("line", 4), ("bend", 90, 3), ("line", 4)], 3.0, 30)  # 10 mm legs: Hubs's 2 t + r is 9
        for shape, summary in ((bracket, "sheet 3 mm, 1 bend(s), flat 30 x 14.5031 mm"),
                               (bd.Box(100, 7, 2), "sheet 2 mm, 0 bend(s), flat 100 x 7 mm"),
                               # twice as wide as it is thick, with no wider face: a laser-cut strip, no bar
                               (bd.Box(100, 4, 2), "sheet 2 mm, 0 bend(s), flat 100 x 4 mm")):
            for placed in self.placements(shape):
                result = checked(placed)
                self.assertTrue(result.ok, result.summary)
                self.assertEqual(verdicts(result), [])
                self.assertIn(summary, result.summary)

    def test_bars_and_blocks_are_not_sheet_in_any_placement_and_a_thick_plate_is(self) -> None:
        for size, said in (((50, 40, 30), "40 mm wide and 30 mm across"), ((30, 30, 20), "30 mm wide and 20 mm across"),
                           ((100, 8, 6), "8 mm wide and 6 mm across"), ((100, 6, 6), "6 mm wide and 6 mm across")):
            for placed in self.placements(bd.Box(*size)):
                result = checked(placed)
                (finding,) = [f for f in result.findings if f.severity == "error"]
                self.assertEqual(finding.code, "sheet.not_sheet")
                self.assertIn(said, finding.message)  # the same words wherever it stands
        for placed in self.placements(bd.Box(100, 100, 12)):
            self.assertEqual(verdicts(checked(placed)), [("warning", "sheet.thickness_max")])
        # past an inch it is plate, no sheet shop's work: cad's own floor, said as its own -- and an
        # inch plate is within the inch its note says
        self.assertEqual(verdicts(checked(bd.Box(160, 120, 25.4))), [("warning", "sheet.thickness_max")])
        (plate,) = [f for f in checked(bd.Box(160, 120, 26)).findings if f.severity in ("error", "warning")]
        self.assertEqual((plate.severity, plate.code), ("error", "sheet.thickness_limit"))
        self.assertTrue(plate.source.startswith("cad, its own figure"), plate.source)

    def test_a_tube_is_a_closed_section_and_a_rolled_sheet_is_sheet_not_checked(self) -> None:
        tube = bd.Cylinder(20, 100) - bd.Cylinder(18, 100)
        for placed in (tube, turned(tube)):
            result = checked(placed)
            (finding,) = [f for f in result.findings if f.severity == "error"]
            self.assertEqual((result.status, finding.code), ("failed", "sheet.not_sheet"))
            self.assertIn("a closed section, a tube of 2 mm wall and 18 mm inside radius", finding.message)
        # a sheet rolled round with no flat flange is sheet -- no error says it is not -- and is not unrolled here:
        # what was not measured is said once, and the check is no pass
        slit = tube - bd.Pos(20, 0, 0) * bd.Box(10, 1, 120)
        guard = bent([("bend", 120, 100)], 2.0, 200, "guard")
        for shape, radius in ((slit, 18), (turned(slit), 18), (guard, 100), (turned(guard), 100)):
            result = checked(shape)
            self.assertEqual((result.status, result.reason), ("not_checked", "measurement_failed"))
            (finding,) = [f for f in result.findings if f.severity in ("error", "warning")]
            self.assertIn(f"a 2 mm sheet rolled to a {radius} mm inside radius with no flat flange is rolled on plate "
                          "rolls", finding.message)
            self.assertNotIn("not one sheet", finding.message)
            (part,) = result.measurements["parts"]["items"]
            self.assertEqual((part["is_sheet"], part["thickness_mm"]), (True, 2.0))
        with self.assertRaisesRegex(ValueError, "rolled on plate rolls"):
            sheet.unfold(guard)

    def test_a_grille_s_slot_walls_do_not_outvote_its_skins(self) -> None:
        t = 3.0  # webs half the sheet's thickness between long slots: the walls face each other 1.5 mm apart
        plate = bd.Pos(0, 0, t / 2) * bd.Box(140, 120, t)
        for i in range(30):
            plate -= bd.Pos(-58 + i * 3.5, 0, t / 2) * bd.Box(2, 110, 3 * t)
        part = items(measured(plate), "parts")[0]
        self.assertAlmostEqual(part["thickness_mm"], 3.0, places=6)
        self.assertTrue(part["is_sheet"])


class NotJudgedTest(unittest.TestCase):
    """What is measured with no guide's limit is said so, and cad's own lines are said as its own."""

    def test_a_radius_of_many_thicknesses_is_no_single_hit_of_a_brake(self) -> None:
        rolled = checked(bent([("line", 20), ("bend", 120, 50), ("line", 20)], 2.0, 60))  # r = 25 t
        (warned,) = [f for f in rolled.findings if f.severity in ("error", "warning")]
        self.assertEqual((warned.severity, warned.code), ("warning", "sheet.bend_radius_max"))
        self.assertIn("25 ratio is over the 10 ratio recommended maximum", warned.message)
        self.assertTrue(warned.source.startswith("cad, its own figure"), warned.source)

    def test_relief_depth_and_channel_proportions_are_said_measured_not_judged(self) -> None:
        shallow = checked(tabbed(relief=(3.0, 0.5)))  # wide enough, 0.5 mm past the tangent line
        self.assertEqual(verdicts(shallow), [])
        (note,) = [f for f in shallow.findings if f.code == "sheet.measured_not_judged"]
        self.assertEqual(note.severity, "info")
        self.assertIn("2 bend relief(s)' depth past the bend", note.message)
        self.assertEqual({item["depth_tangent_mm"] for item in shallow.measurements["reliefs"]["items"]}, {0.5})
        channel = checked(bent([("line", 30), ("bend", 90, 2), ("line", 6), ("bend", 90, 2), ("line", 30)], 2.0, 120))
        (note,) = [f for f in channel.findings if f.code == "sheet.measured_not_judged"]
        self.assertIn("1 channel(s)' width against their legs", note.message)
        self.assertNotIn("sheet.measured_not_judged", {f.code for f in checked(bd.Box(80, 50, 2)).findings})


class PerPartTest(unittest.TestCase):
    """Each part of a document is judged by its own thickness, whichever comes first."""

    def test_two_thicknesses_are_each_judged_by_their_own_in_either_order(self) -> None:
        thin = bent([("line", 40), ("bend", 90, 1), ("line", 30)], 1.0, 50, "thin")  # r = t: no warning
        # a 5 mm hole 3 mm from the bend's tangent line of a 3 mm part: under 2 t = 6 mm
        thick = bent([("line", 40), ("bend", 90, 3), ("line", 30)], 3.0, 50, "thick") - bd.Pos(34.5, 25, 0) * bd.Cylinder(2.5, 20)
        thick.label = "thick"
        for first, second in ((thin, thick), (thick, thin)):
            result = checked(bd.Compound(children=[first, bd.Pos(100, 0, 0) * second]))
            self.assertEqual(verdicts(result), [("error", "sheet.hole_to_bend")], result.summary)
            (failure,) = failed(result, "sheet.hole_to_bend")
            self.assertAlmostEqual(failure["value"], 3.0, places=6)
            self.assertIn("2 parts, 1 and 3 mm", result.summary)
            (hole,) = [f for f in result.findings if f.code == "sheet.hole_to_bend"]
            self.assertIn("3 mm is under the 6 mm minimum", hole.message)
            # each part's one radius is its own: two parts of two radii mix none
            self.assertNotIn("sheet.bend_radii_mixed", {f.code for f in result.findings})

    def test_a_flat_plate_beside_a_bent_bracket_keeps_the_flat_thickness_limit(self) -> None:
        plate = bd.Pos(0, 100, 4) * bd.Box(80, 60, 8)  # 8 mm, flat: within the 10 mm a laser cuts
        plate.label = "plate"
        bracket = bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "bracket")
        result = checked(bd.Compound(children=[bracket, plate]))
        self.assertEqual(verdicts(result), [], [f.message for f in result.findings])


def failed(result, rule: str) -> list[dict]:
    return [failure for outcome in result.measurements["rules"]["outcomes"] if outcome["rule"] == rule
            and outcome["status"] == "failed" for failure in outcome["failures"]]


def _boxes_bracket() -> bd.Part:
    """A 2 mm bracket of two boxes unioned: a sharp corner, no bend radius (base on z = 0, wall at x = 0)."""
    part = (bd.Pos(20, 15, 1) * bd.Box(40, 30, 2) + bd.Pos(1, 15, 15) * bd.Box(2, 30, 30)).clean()
    part.label = "boxes"
    return part


class FlangeTest(unittest.TestCase):
    def test_a_bend_running_past_its_flange_has_no_flange_there(self) -> None:
        t, r = 2.0, 2.0
        part = bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 60, "L")
        # the wall cut to 30 mm wide at its tangent line (z = r + t), the bend left 60 long: 15 mm each side of
        # it bends to nothing
        wall = part.bounding_box().max.X
        for y in (0.0, 45.0):
            part -= bd.Pos(wall - 5, y, r + t) * bd.Box(10, 15, 40, align=(bd.Align.MIN,) * 3)
        part.label = "L"
        result = checked(part, material="aluminum")
        [short] = failed(result, "sheet.flange_length")
        flange = next(item for item in items(result.measurements, "flanges") if item["stations_off_flange"])
        self.assertEqual(flange["length_tangent_mm"], 0.0)
        self.assertEqual(flange["location"], flange["bend"])  # at the bend's stretch past the flange
        self.assertEqual(short["location"], flange["location"])
        # the full-width wall reaches its tangent everywhere: no station off it, the rule passes
        whole = checked(bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 60, "L"), material="aluminum")
        self.assertEqual(failed(whole, "sheet.flange_length"), [])
        self.assertEqual({item["stations_off_flange"] for item in items(whole.measurements, "flanges")}, {0})


class ModellingMistakeTest(unittest.TestCase):
    """The mistakes an agent writing build123d makes: no wrong part or flat pattern reads as a pass."""

    def test_a_sharp_cornered_bracket_is_a_sharp_bend_and_its_flat_is_incomplete(self) -> None:
        result = checked(_boxes_bracket(), material="steel", thickness=2)
        self.assertFalse(result.ok)
        (corner,) = result.measurements["sharp_bends"]["items"]
        self.assertEqual((corner["kind"], corner["angle_deg"]), ("sharp", 90.0))
        by_code = {f.code: f for f in result.findings}
        self.assertIn("inside radius r >= t and an outside radius r + t at the corner", by_code["sheet.sharp_bend"].hint)
        part = result.measurements["parts"]["items"][0]
        self.assertAlmostEqual(part["flat_material_fraction"], 1200 / 2040, places=4)  # the wall is not in it
        self.assertNotIn("sheet.flat_incomplete", by_code)  # the sharp bend says why the flat is short
        with self.assertRaisesRegex(ValueError, "without a bend"):
            sheet.unfold(_boxes_bracket())

    def test_a_short_flat_is_an_error_where_nothing_else_says_why(self) -> None:
        part = {"thickness_mm": 2.0, "is_sheet": True, "location": "p/face 1", "flat_material_fraction": 0.8}
        alone = {f.code for f in sheet_rules.findings({"parts": {"items": [part]}}, {}, False)}
        self.assertIn("sheet.flat_incomplete", alone)
        # it names what did not unfold, at it, and never points at other findings that are not there
        (short,) = [f for f in sheet_rules.findings({"parts": {"items": [{**part, "not_in_flat": ["p/face 4"]}]}},
                                                    {}, False) if f.code == "sheet.flat_incomplete"]
        self.assertEqual(short.location, "p/face 4")
        self.assertIn("p/face 4 did not unfold", short.message)
        self.assertNotIn("other findings", short.hint)
        (whole,) = [f for f in sheet_rules.findings({"parts": {"items": [part]}}, {}, False)
                    if f.code == "sheet.flat_incomplete"]
        self.assertIn("every flange and bend unfolded", whole.message)
        sharp = {"parts": {"items": [part]}, "sharp_bends": {"items": [{"kind": "sharp", "location": "p/face 2",
                                                                         "thickness_mm": 2.0, "angle_deg": 90.0}]}}
        codes = {f.code for f in sheet_rules.findings(sharp, {}, False)}
        self.assertEqual(codes & {"sheet.flat_incomplete", "sheet.sharp_bend"}, {"sheet.sharp_bend"})

    def test_a_round_on_one_side_of_a_corner_says_which_radius_is_missing(self) -> None:
        part = _boxes_bracket()
        inner = [e for e in part.edges().filter_by(bd.Axis.Y) if abs(e.center().X - 2) < 1e-6 and abs(e.center().Z - 2) < 1e-6]
        result = checked(part.fillet(2, inner), material="steel", thickness=2)
        rounds = [item for item in result.measurements["sharp_bends"]["items"] if item["kind"] != "sharp"]
        self.assertEqual([(item["kind"], item["inside_radius_mm"]) for item in rounds], [("inside_only", 2.0)])
        messages = [f.message for f in result.findings if f.code == "sheet.sharp_bend"]
        self.assertTrue(any("no outside radius of 4 mm" in message for message in messages), messages)
        self.assertEqual(failed(result, "sheet.uniform_thickness"), [])  # the round is the sharp bend's, said once

    def test_a_well_made_bracket_is_whole(self) -> None:
        result = checked(bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "L"), material="steel",
                         thickness=2)
        self.assertTrue(result.ok, [f.message for f in result.findings])
        self.assertEqual(result.measurements["sharp_bends"]["items"], [])
        self.assertAlmostEqual(result.measurements["parts"]["items"][0]["flat_material_fraction"], 1.0, delta=0.002)
        self.assertNotIn("sheet sheet", result.summary)

    def test_a_hole_across_the_tangent_line_is_a_hole_in_the_bend(self) -> None:
        for x in (39.5, 40.5):  # the tangent line at x = 40: half in the flange, half in the bend, either way
            part = bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "L") - bd.Pos(x, 25, 0) * bd.Cylinder(1.5, 100)
            report = measured(part, material="steel")
            (hole,) = items(report, "holes")
            self.assertTrue(hole["in_bend"], hole)
            (near,) = items(report, "hole_to_bend")
            self.assertEqual(near["distance_tangent_mm"], 0.0)
            codes = {f.code for f in checked(part, material="steel").findings}
            self.assertTrue({"sheet.hole_to_bend", "sheet.hole_in_bend"} <= codes, codes)

    def test_a_slot_across_a_bend_leaves_one_bend_line_unfolded_whole(self) -> None:
        part = bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "L") - bd.Pos(40, 25, 4) * bd.Box(12, 3, 12)
        report = measured(part)
        p = items(report, "parts")[0]
        self.assertEqual(p["bend_count"], 2)
        self.assertIsNone(p["unfold_note"])  # no loop of flanges, no seam
        self.assertAlmostEqual(p["flat_material_fraction"], 1.0, delta=0.002)
        self.assertEqual(len(p["flat_bend_lines"]), 2)
        self.assertEqual(items(report, "notches"), [])  # the second strip is in the flat: no gap where it was
        # the window ends the bend either side: no hole beside it, its 3 mm a relief's width at each end
        self.assertEqual(items(report, "hole_to_bend"), [])
        self.assertEqual({item["width_mm"] for item in items(report, "reliefs")}, {3.0})
        self.assertEqual(verdicts(checked(part)), [])
        self.assertEqual(verdicts(checked(turned(part))), [])
        # a hole in the bend line that leaves the flanges whole is a hole in the bend, and no relief missing
        holed = bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "L") - (
            bd.Pos(42, 25, 2) * bd.Rot(0, 45, 0) * bd.Cylinder(1.5, 20))
        self.assertEqual(verdicts(checked(holed)), [("error", "sheet.hole_to_bend"), ("warning", "sheet.hole_in_bend")])

    def test_a_hem_is_judged_by_its_own_rule(self) -> None:
        hem = bent([("line", 40), ("bend", 180, 0.5), ("line", 8)], 1.0, 30, "hem")  # inside diameter = t
        result = checked(hem, material="steel", thickness=1)
        self.assertEqual(failed(result, "sheet.bend_radius"), [])
        lid = bent([("line", 8), ("bend", 180, 0.5), ("line", 25), ("bend", 90, 1.0), ("line", 60)], 1.0, 50, "lid")
        self.assertNotIn("sheet.bend_radii_mixed", {f.code for f in checked(lid, thickness=1).findings})

    def test_a_u_bend_round_a_wide_radius_is_no_hem(self) -> None:
        # a saddle clamp: a strap bent half round a 25 mm pipe, between two feet
        clamp = bent([("line", 15), ("bend", 90, 2), ("line", 5), ("bend", -180, 12.5), ("line", 5), ("bend", 90, 2),
                      ("line", 15)], 1.5, 20, "clamp")
        for placed in (clamp, turned(clamp)):
            result = checked(placed)
            self.assertEqual(verdicts(result), [])
            self.assertEqual(sorted(b["kind"] for b in result.measurements["bends"]["items"]), ["bend"] * 3)
            self.assertEqual(result.measurements["hems"]["items"], [])
        # a fold whose return lies four thicknesses off the panel is still a hem, and one wider is not
        for radius, kind in ((2.0, "hem"), (2.1, "bend")):
            fold = bent([("line", 80), ("bend", 180, radius), ("line", 4)], 1.0, 120, "fold")
            (bend,) = items(measured(fold), "bends")
            self.assertEqual(bend["kind"], kind)
            self.assertEqual(verdicts(checked(fold)), [("warning", "sheet.hem_return")] if kind == "hem" else [])

    def test_the_shops_radius_is_given_and_said_once_a_bend(self) -> None:
        # no radius is assumed for a shop: given (--bend-radius), each bend modelled otherwise is one warning
        bracket = bent([("line", 40), ("bend", 90, 2.0), ("line", 30)], 2.0, 50, "L")
        self.assertNotIn("sheet.bend_radius_differs", {f.code for f in checked(bracket, material="steel").findings})
        (shop,) = [f for f in checked(bracket, material="steel", bend_radius=1.6).findings
                   if f.code == "sheet.bend_radius_differs"]
        self.assertEqual(shop.severity, "warning")
        self.assertIn("the shop's 1.6 mm", shop.message)

    def test_a_chamfered_plate_is_cut_sheet_its_flat_the_cut_outline(self) -> None:
        plate = bd.chamfer(bd.Box(80, 40, 3).edges(), 0.5)
        plate.label = "chamfered"
        result = checked(plate)
        self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
        part = result.measurements["parts"]["items"][0]
        self.assertEqual((part["thickness_mm"], part["is_sheet"]), (3.0, True))
        self.assertAlmostEqual(part["flat_length_mm"], 80.0, places=4)  # the cut edges', not the skin's 79 x 39
        self.assertAlmostEqual(part["flat_width_mm"], 40.0, places=4)
        kinds = {item["kind"] for item in result.measurements["not_sheet"]["items"]}
        self.assertEqual(kinds, {"edge_break"})  # never a thicker stretch 80 mm across
        (broken,) = [f for f in result.findings if f.code == "sheet.edge_break"]
        self.assertEqual(broken.severity, "warning")
        self.assertEqual(failed(result, "sheet.uniform_thickness"), [])

    def test_broken_edges_that_meet_at_a_corner_of_the_outline_are_laid_into_the_flat(self) -> None:
        # where two broken edges meet at a corner of the outline a break ends in a curve, no line: an ellipse's
        # arc between two rounds, a conic between a chamfer along a line and one along an arc. Sampled, its
        # chords were shorter than the tolerance the breaks are fused onto the skin with, and the fuse dropped
        # the breaks with no error: the flat was the skin's, 79 x 39 for an 80 x 40 plate rounded 0.5 mm
        def broken(part: bd.Part, how, size: float) -> bd.Part:
            levels = part.edges().group_by(bd.Axis.Z)
            return how(levels[0] + levels[-1], size)

        outline = bd.Wire([bd.CenterArc((0, 0), 30, 90, 180), bd.Line((0, -30), (0, 30))])
        for name, part in (("plate", bd.Box(80, 40, 2)), ("half disc", bd.extrude(bd.Face(outline), 2))):
            square = checked(part).measurements["parts"]["items"][0]
            for how in (bd.fillet, bd.chamfer):
                for size in (0.2, 0.5):
                    with self.subTest(part=name, how=how.__name__, size=size):
                        result = checked(broken(part, how, size))
                        self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
                        found = result.measurements["parts"]["items"][0]
                        for key in ("flat_length_mm", "flat_width_mm"):
                            self.assertAlmostEqual(found[key], square[key], places=3)
                        self.assertAlmostEqual(found["flat_area_mm2"], square["flat_area_mm2"], delta=0.05)
                        self.assertIn("sheet.edge_break", {f.code for f in result.findings})

    def test_broken_edges_round_a_bend_are_unrolled_with_it(self) -> None:
        # a bracket's cut edges broken all round, its ends' too: round a bend the break is a cone or a torus
        # about its axis, which was read as a face off the sheet's thickness (sheet.uniform_thickness), the
        # bend's strip stopped short of the cut on both ends (49.4 mm of a 50 mm bend) and the flanges' material
        # ran on past it (sheet.bend_relief_width, a relief 0 mm wide): FAILED on a part that bends as drawn
        def broken(part: bd.Part, how, size: float) -> bd.Part:
            ends = part.faces().filter_by(bd.Axis.Y)
            return how([e for face in ends for e in face.edges() if abs(e.length - 2.0) > 1e-6], size)

        for name, steps in (("L", [("line", 30), ("bend", 90, 2), ("line", 40)]),
                            ("U", [("line", 30), ("bend", 90, 2), ("line", 40), ("bend", 90, 2), ("line", 30)]),
                            ("60 degrees", [("line", 30), ("bend", 60, 2), ("line", 40)])):
            part = bent(steps, 2.0, 50.0, name)
            square = checked(part, k_factor=0.4).measurements["parts"]["items"][0]
            for how in (bd.fillet, bd.chamfer):
                for size in (0.3, 0.8):
                    with self.subTest(part=name, how=how.__name__, size=size):
                        result = checked(broken(part, how, size), k_factor=0.4)
                        self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
                        found = result.measurements["parts"]["items"][0]
                        self.assertAlmostEqual(found["flat_area_mm2"], square["flat_area_mm2"], delta=0.05)
                        self.assertAlmostEqual(found["flat_material_fraction"], 1.0, places=2)
                        self.assertEqual([b["length_mm"] for b in result.measurements["bends"]["items"]],
                                         [50.0] * (len(steps) // 2))
                        self.assertIn("sheet.edge_break", {f.code for f in result.findings})
                        self.assertEqual(len(sheet.unfold(broken(part, how, size), k_factor=0.4).faces()), 1)

    def test_broken_edges_along_an_ellipse_or_a_spline_are_breaks_and_the_flat_is_the_outline(self) -> None:
        # a plate cut along an ellipse or a spline: a chamfer or a round of its edge is a B-spline face and its cut
        # a surface of extrusion, which were read as faces off the sheet's thickness (FAILED,
        # sheet.uniform_thickness), and its flat was measured off 48 points of each curve (a spline plate's
        # 0.19 mm short). A deep break on one skin failed round a disc too: the other skin's rays that reach it
        # are short by the break
        spline = bd.Edge.make_spline([bd.Vector(x, y) for x, y in ((40, 0), (25, 18), (-5, 20), (-38, 12),
                                                                  (-40, -6), (-15, -20), (20, -17))], periodic=True)
        outlines = {"ellipse": bd.Ellipse(40, 20).face(), "spline": bd.Face(bd.Wire(spline)),
                    "elliptical hole": (bd.Rectangle(80, 40) - bd.Ellipse(12, 6)).face(),
                    "disc": bd.Circle(30).face()}
        for name, outline in outlines.items():
            wire = outline.outer_wire()
            long, short, _ = plane.min_rectangle([(p.X, p.Y) for p in (wire @ (i / 4000) for i in range(4000))])
            # (a cylinder's skins sample beside its rim, where the other skin's break is)
            square = bd.Cylinder(30, 2) if name == "disc" else bd.extrude(outline, amount=2)
            report = checked(square).measurements
            found, holes = report["parts"]["items"][0], [hole["size_mm"] for hole in report["holes"]["items"]]
            with self.subTest(part=name, broken=None):
                # the outline's own size, within the chords' tolerance
                self.assertAlmostEqual(found["flat_length_mm"], long, delta=plane.CHORD_MM)
                self.assertAlmostEqual(found["flat_width_mm"], short, delta=plane.CHORD_MM)
                self.assertAlmostEqual(found["flat_area_mm2"], outline.area, delta=0.001 * outline.area)
            top, bottom = square.edges().group_by(bd.Axis.Z)[-1], square.edges().group_by(bd.Axis.Z)[0]
            for how, size, edges in ((bd.chamfer, 0.5, top + bottom), (bd.fillet, 0.5, top), (bd.chamfer, 0.9, top)):
                with self.subTest(part=name, broken=(how.__name__, size, "both" if len(edges) > len(top) else "top")):
                    part = how(edges, size)
                    result = checked(part)
                    self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
                    self.assertIn("sheet.edge_break", {f.code for f in result.findings})
                    measured = result.measurements["parts"]["items"][0]
                    for key in ("flat_length_mm", "flat_width_mm"):
                        self.assertAlmostEqual(measured[key], found[key], delta=plane.CHORD_MM)
                    self.assertAlmostEqual(measured["flat_area_mm2"], found["flat_area_mm2"], delta=0.05)
                    sizes = [hole["size_mm"] for hole in result.measurements["holes"]["items"]]
                    self.assertEqual(len(sizes), len(holes))
                    for size_mm, hole in zip(sizes, holes):
                        self.assertAlmostEqual(size_mm, hole, delta=plane.CHORD_MM)
                    if len(edges) > len(top):  # both skins broken: their breaks fused on, one piece
                        self.assertEqual(len(sheet.unfold(part).faces()), 1)

    def test_a_cut_edge_in_several_faces_across_the_thickness_is_one_cut(self) -> None:
        # a plate extruded both ways along an ellipse or a spline: the kernel merges the halves of a plane or a
        # cylinder and leaves such a cut two faces, split at mid-thickness. Neither touches both skins, so
        # neither was a cut edge (FAILED, sheet.uniform_thickness), and no break of its edges was one: the
        # flat stopped at the skins, 1 mm short across 0.5 mm chamfers, an elliptical hole 1 mm large. Layers
        # joined and never merged (planes, cylinders, a bracket's sides and ends) read the same
        def agrees(split: bd.Shape, whole: bd.Shape, **options) -> None:
            result, wanted = checked(split, **options), checked(whole, **options)
            self.assertTrue(wanted.ok, [f.message for f in wanted.findings if f.severity == "error"])
            self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
            self.assertEqual(verdicts(result), verdicts(wanted))
            found, expected = (r.measurements["parts"]["items"][0] for r in (result, wanted))
            for key in ("thickness_mm", "flat_length_mm", "flat_width_mm", "flat_area_mm2", "flat_material_fraction"):
                self.assertAlmostEqual(found[key], expected[key], places=3, msg=key)
            for family, keys in (("holes", ("size_mm", "countersunk", "countersink_diameter_mm")), ("bends", ("length_mm",))):
                self.assertEqual([[item[key] for key in keys] for item in result.measurements[family]["items"]],
                                 [[item[key] for key in keys] for item in wanted.measurements[family]["items"]], family)
            self.assertEqual(len(sheet.unfold(split, **options).faces()), 1)

        def rims(part: bd.Shape, both: bool) -> list[bd.Edge]:
            levels = part.edges().group_by(bd.Axis.Z)
            return [*levels[-1], *(levels[0] if both else [])]

        def joined(first: bd.Shape, *more: bd.Shape) -> bd.Solid:
            """The solids fused as the kernel fuses them: no face merged with the next (build123d's fuse merges)."""
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

            shape = first.wrapped
            for other in more:
                fuse = BRepAlgoAPI_Fuse(shape, other.wrapped)
                fuse.Build()
                shape = fuse.Shape()
            return bd.Compound(shape).solids()[0]

        def layered(outline: bd.Face, *levels: float) -> bd.Solid:
            return joined(*(bd.extrude(bd.Pos(0, 0, low) * outline, amount=high - low)
                            for low, high in zip(levels, levels[1:])))

        spline = bd.Edge.make_spline([bd.Vector(x, y) for x, y in ((40, 0), (25, 18), (-5, 20), (-38, 12),
                                                                  (-40, -6), (-15, -20), (20, -17))], periodic=True)
        chamfer, fillet = (bd.chamfer, 0.5, True), (bd.fillet, 0.5, False)
        for name, outline, breaks in (("ellipse", bd.Ellipse(40, 20).face(), (chamfer, fillet)),
                                      ("spline", bd.Face(bd.Wire(spline)), ()),
                                      ("elliptical hole", (bd.Rectangle(80, 40) - bd.Ellipse(12, 6)).face(), (chamfer,))):
            whole, split = bd.extrude(outline, amount=2), bd.extrude(outline, amount=1, both=True)
            with self.subTest(part=name, extruded="both ways"):
                agrees(split, whole)
            for how, size, both in breaks:
                with self.subTest(part=name, extruded="both ways", broken=(how.__name__, size, both)):
                    agrees(how(rims(split, both), size), how(rims(whole, both), size))

        plate = (bd.RectangleRounded(80, 40, 5) - bd.Pos(-15, 0) * bd.SlotOverall(30, 8) - bd.Pos(25, 8) * bd.Circle(4)).face()
        whole = bd.extrude(plate, amount=2)
        for levels in ((0, 1, 2), (0, 0.6, 1.3, 2)):
            with self.subTest(part="plate, a slot and a hole", layers=levels):
                split = layered(plate, *levels)
                self.assertGreater(len(split.faces()), len(whole.faces()))
                agrees(split, whole)
        with self.subTest(part="plate, a slot and a hole", layers=levels, broken="chamfer 0.4, both skins"):
            agrees(bd.chamfer(rims(split, True), 0.4), bd.chamfer(rims(whole, True), 0.4))

        # under a countersink the hole's wall reaches that skin through the cone: the wall in two faces
        sunk = self._sunk((80, 40, 3), top=[(-20, 0)], bottom=[(20, 0)], hole=5, rim=7)
        with self.subTest(part="countersunk holes", layers=2):
            split = joined(*sunk.split(bd.Plane.XY, keep=bd.Keep.BOTH))
            self.assertGreater(len(split.faces()), len(sunk.faces()))
            agrees(split, sunk)

        # an L bracket in two layers, one inside the other: its sides and ends each in two faces
        def steps(radius: float) -> list[tuple]:
            return [("line", 30), ("bend", 90, radius), ("line", 40)]

        outer = bd.extrude(bd.Plane.XZ * profile(steps(3.0), 1.0), amount=-50)
        inner = bd.extrude(bd.Plane.XZ * (bd.Pos(0, 1) * profile(steps(2.0), 1.0)), amount=-50)
        with self.subTest(part="L bracket", layers=2):
            split, whole = joined(outer, inner), bent(steps(2.0), 2.0, 50.0)
            self.assertGreater(len(split.faces()), len(whole.faces()))
            agrees(split, whole, k_factor=0.4)

        # and what is no cut edge stays none: a bead along the middle of a plate's edge, tangent to the square
        # faces above and below it (the faces followed are the square ones alone)
        bead = bd.Spline((40, -0.5), (40.3, 0), (40, 0.5), tangents=((0, 1), (0, 1)))
        section = bd.Wire([*bd.Polyline((40, 0.5), (40, 1), (-40, 1), (-40, -1), (40, -1), (40, -0.5)).edges(), bead])
        beaded = checked(bd.extrude(bd.Plane.XZ * bd.Face(section), amount=-40))
        self.assertIn(("error", "sheet.uniform_thickness"), verdicts(beaded))

    @staticmethod
    def _sunk(size: tuple[float, float, float], top: list[tuple[float, float]], bottom: list[tuple[float, float]],
              hole: float, rim: float, angle: float = 82.0, plate: bd.Part | None = None) -> bd.Part:
        """A plate (``plate``, or a box) with ``hole`` mm holes countersunk to ``rim`` mm at ``angle`` degrees
        from its top (at ``top``) and from below."""
        with bd.BuildPart() as built:
            bd.Box(*size) if plate is None else bd.add(plate)
            for side, places in ((1, top), (-1, bottom)):
                for x, y in places:
                    with bd.Locations(bd.Pos(x, y, side * size[2] / 2) * bd.Rot(0 if side > 0 else 180, 0, 0)):
                        bd.CounterSinkHole(radius=hole / 2, counter_sink_radius=rim / 2, depth=size[2],
                                           counter_sink_angle=angle)
        return built.part

    def test_a_countersink_in_the_unfolded_side_leaves_the_flat_its_through_hole(self) -> None:
        # the skin a countersink is sunk into has the countersink's rim for a hole, and where that skin was the
        # one unfolded the flat had it too, 10 mm for a 5 mm hole, with no finding. A plate sunk from both
        # sides has one such whichever side unfolds, and so has a hole chamfered at both rims
        for name, top, bottom, rim in (("sunk from both sides", [(-20, 0)], [(20, 0)], 10.0),
                                       ("chamfered at both rims", [(0, 0)], [(0, 0)], 6.0)):
            with self.subTest(part=name):
                result = checked(self._sunk((80, 40, 3), top, bottom, 5.0, rim))
                self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
                holes = result.measurements["holes"]["items"]
                self.assertEqual([(hole["size_mm"], hole["countersink_diameter_mm"]) for hole in holes],
                                 [(5.0, rim)] * len(holes))
                part = result.measurements["parts"]["items"][0]
                self.assertAlmostEqual(part["flat_area_mm2"], 3200 - len(holes) * math.pi * 2.5 ** 2, delta=0.1)
                self.assertAlmostEqual(part["flat_material_fraction"], 1.0, places=2)

    def test_a_countersink_through_the_sheet_or_with_a_cut_rim_leaves_the_flat_its_hole(self) -> None:
        # a countersink was a cone between a skin and a hole's wall, its rim a whole circle in that skin. Sunk
        # through the full thickness there is no wall: the cone was a cut edge, the flat's hole the rim where
        # that skin unfolded (11 mm for 5) and the cone's cut missing from the material. With its rim off the
        # outline, in a cutout or in another rim, the cone is no whole turn there: laid into the flat edge by
        # edge it left the hole out (47.7 mm2 of a plate, a false sheet.web_width; two rims that overlap,
        # sheet.flat_incomplete), and the wire its rim is part of was read as the hole
        slot = bd.Box(80, 40, 3) - bd.Box(30, 6, 10)
        under = [(-25, 10), (25, 10), (0, -12), (25, -10)]  # four rims below: the top is the larger skin
        for name, part, holes, cut in (
                ("to a knife edge", self._sunk((80, 40, 3), [(-20, 0)], [(20, 0)], 5.0, 11.0, 90.0), [(5.0, 11.0)] * 2, 0.0),
                ("past the far skin", self._sunk((80, 40, 3), [(-20, 0)], [(20, 0)], 5.0, 13.0, 90.0), [(7.0, 13.0)] * 2, 0.0),
                ("its rim off the outline", self._sunk((80, 40, 3), [(37, 0)], [(-37, 0)], 5.0, 10.0), [(5.0, 10.0)] * 2, 0.0),
                ("its rim off a corner", self._sunk((80, 40, 3), [(37, 17)], [(-37, -17)], 5.0, 10.0), [(5.0, 10.0)] * 2, 0.0),
                ("its rim in a slot", self._sunk((80, 40, 3), [(18.5, 0)], [(-18.5, 0)], 5.0, 10.0, plate=slot),
                 [(5.0, 10.0), (5.0, 10.0), (6.0, None)], 180.0),
                ("two rims that overlap", self._sunk((80, 40, 3), [(-4.5, 0), (4.5, 0)], under, 5.0, 10.0), [(5.0, 10.0)] * 6, 0.0),
                ("to a knife edge and off the outline", self._sunk((80, 40, 3), [(36.5, 0)], [(-36.5, 0)], 5.0, 11.0, 90.0),
                 [(5.0, 11.0)] * 2, 0.0)):
            with self.subTest(part=name):
                result = checked(part)
                self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
                self.assertFalse({code for _, code in verdicts(result)} - {"sheet.hole_to_edge", "sheet.hole_spacing"})
                found = sorted(((hole["size_mm"], hole["countersink_diameter_mm"]) for hole in
                                result.measurements["holes"]["items"]), key=lambda hole: (hole[0], hole[1] or 0.0))
                self.assertEqual(found, holes)
                area = 3200 - cut - sum(math.pi * (size / 2) ** 2 for size, rim in holes if rim)
                item = result.measurements["parts"]["items"][0]
                self.assertAlmostEqual(item["flat_area_mm2"], area, delta=0.05 * len(holes))  # each rim's chords
                self.assertAlmostEqual(item["flat_material_fraction"], 1.0, places=2)
                self.assertAlmostEqual(sheet.unfold(part).area, area, delta=0.02)
        # on a bracket's flange, from each of its skins
        bracket = bent([("line", 30), ("bend", 90, 2), ("line", 40)], 2.0, 60.0)
        with bd.BuildPart() as built:
            bd.add(bracket)
            for z, turn, y in ((2.0, 0, 15), (0.0, 180, 45)):
                with bd.Locations(bd.Pos(15, y, z) * bd.Rot(turn, 0, 0)):
                    bd.CounterSinkHole(radius=1.6, counter_sink_radius=3.6, depth=2.0, counter_sink_angle=90.0)
        result, plain = checked(built.part, k_factor=0.4), checked(bracket, k_factor=0.4)
        self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
        self.assertEqual([(hole["size_mm"], hole["countersink_diameter_mm"]) for hole in result.measurements["holes"]["items"]],
                         [(3.2, 7.2)] * 2)
        self.assertAlmostEqual(result.measurements["parts"]["items"][0]["flat_area_mm2"],
                               plain.measurements["parts"]["items"][0]["flat_area_mm2"] - 2 * math.pi * 1.6 ** 2, delta=0.1)

    def test_a_countersink_in_several_faces_reads_as_the_part_whole(self) -> None:
        # some systems write a closed face as two halves with no seam (OCCT's ShapeUpgrade_ShapeDivideClosed
        # leaves the same). A cone sunk to a knife edge in two halves has no whole circle, so it was a cut edge
        # (the flat's hole its rim, 11 mm for 5); a corner of the outline cuts a piece of a cone in three from
        # every skin, and that piece was no sheet at all; a cone laid into the flat in pieces left a round hole
        # of chords, read as a cutout. A plate cut through its holes and joined unmerged holds no wire of them:
        # its countersinks were not countersunk, and a skin in several faces counted each chamfer once a face
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Splitter
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.collections import List_TopoDS_Shape
        from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideClosed

        def divided(part: bd.Part, points: int) -> bd.Solid:
            """Each closed face of ``part`` in ``points + 1`` faces."""
            op = ShapeUpgrade_ShapeDivideClosed(part.wrapped)
            op.SetNbSplitPoints(points)
            op.Perform()
            return bd.Compound(op.Result()).solids()[0]

        def cut_through(part: bd.Part, xs: list[float]) -> bd.Solid:
            """``part`` cut across X at each of ``xs`` (by the kernel's splitter) and joined again as the kernel
            joins it, no face merged."""
            parts, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
            parts.Append(part.solids()[0].wrapped)
            for x in xs:
                tools.Append(bd.Face.make_rect(400, 400, bd.Plane(origin=(x, 0, 0), x_dir=(0, 0, 1), z_dir=(-1, 0, 0))).wrapped)
            op = BRepAlgoAPI_Splitter()
            op.SetArguments(parts)
            op.SetTools(tools)
            op.Build()
            pieces = sorted(bd.Compound(op.Shape()).solids(), key=lambda piece: piece.center().X)
            joined = pieces[0]
            for piece in pieces[1:]:
                op = BRepAlgoAPI_Fuse(joined.wrapped, piece.wrapped)
                op.Build()
                joined = bd.Compound(op.Shape()).solids()[0]
            return joined

        def drilled(plate: bd.Part, holes: list[tuple[float, float, int]], hole: float, rim: float) -> bd.Part:
            """``plate`` (3 mm) with ``hole`` mm holes sunk at 90 degrees to ``rim`` mm, from its top (side 1) or
            from below (-1): a drill and a cone, cut. (A ``CounterSinkHole``'s faces, divided, are no valid
            solid.)"""
            r, big = hole / 2, rim / 2
            for x, y, side in holes:
                tool = bd.Pos(0, 0, 1) * (bd.Cylinder(r, 5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
                                          + bd.Cone(r, big + 1, big - r + 1,
                                                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)))
                plate = plate - bd.Pos(x, y, side * 1.5) * bd.Rot(0 if side > 0 else 180, 0, 0) * tool
            return plate

        def read(part: bd.Shape) -> tuple[tuple, list[float]]:
            """What must be the same, and the flat's length, width, area and material fraction."""
            result = checked(part, k_factor=0.4)
            item = result.measurements["parts"]["items"][0]
            return ((result.status, verdicts(result), sorted(
                        (hole["size_mm"], hole["countersink_diameter_mm"], hole["edge_distance_mm"])
                        for hole in result.measurements["holes"]["items"])),
                    [item["flat_length_mm"], item["flat_width_mm"], item["flat_area_mm2"], item["flat_material_fraction"]])

        plate, slot = bd.Box(80, 40, 3), bd.Box(80, 40, 3) - bd.Box(30, 6, 10)
        disc = bd.Cylinder(20, 3)
        three = [(-20, 0, 1), (0, 8, 1), (20, 0, -1)]  # two from the top: the bottom is the larger skin
        for name, whole, made in (
                ("a knife edge, in halves", drilled(plate, three, 5.0, 11.0), lambda part: divided(part, 1)),
                ("past the far skin, in thirds", drilled(plate, three, 5.0, 13.0), lambda part: divided(part, 2)),
                ("its rim off a corner, in thirds", drilled(plate, [(37, 17, 1), (0, 0, 1), (-37, -17, -1)], 5.0, 10.0),
                 lambda part: divided(part, 2)),
                ("its rim off a corner from each skin, in thirds", drilled(plate, [(37.9, 17.9, 1), (-37.9, -17.9, -1)], 3.2, 6.4),
                 lambda part: divided(part, 2)),
                ("its rim off a corner, cut through its hole", drilled(plate, [(37, 17, 1)], 5.0, 10.0),
                 lambda part: cut_through(part, [37.0])),
                # three rims at one end: the bottom is the larger skin, but its middle piece is smaller than the top's
                ("the larger skin in pieces", drilled(plate, [(-20, 0, -1), (30, -12, 1), (30, 0, 1), (30, 12, 1)], 3.2, 6.4),
                 lambda part: cut_through(part, [-20.0, 20.0])),
                ("its rim in a slot's side, in thirds", drilled(slot, [(0, 7, 1), (0, -7, -1)], 5.0, 10.0),
                 lambda part: divided(part, 2)),
                ("cut through its holes", self._sunk((80, 40, 3), [(-20, 0), (0, 5)], [(20, 0)], 5.0, 10.0),
                 lambda part: cut_through(part, [-20.0, 0.0, 20.0])),
                ("a knife edge, cut through its holes", self._sunk((80, 40, 3), [(-20, 0), (0, 5)], [(20, 0)], 5.0, 11.0, 90.0),
                 lambda part: cut_through(part, [-20.0, 0.0, 20.0])),
                ("a disc chamfered on one edge, cut through its axis",
                 bd.chamfer(disc.edges().sort_by(bd.Axis.Z)[-1], 1.0), lambda part: cut_through(part, [0.0]))):
            with self.subTest(part=name):
                split = made(whole)
                self.assertGreater(len(split.faces()), len(whole.faces()))
                self.assertTrue(BRepCheck_Analyzer(split.wrapped).IsValid())
                (got, sizes), (want, wanted) = read(split), read(whole)
                self.assertEqual(got, want)
                for value, expected, delta in zip(sizes, wanted, (2e-3, 2e-3, 0.05, 5e-4)):
                    self.assertAlmostEqual(value, expected, delta=delta)  # the material: a cone's cut, triangulated
                self.assertAlmostEqual(sheet.unfold(split).area, sheet.unfold(whole).area, delta=0.05)

    def test_a_break_in_several_faces_reads_as_the_part_whole(self) -> None:
        # a part in layers, joined and never merged (a kernel fuse, an import), has every face a layer crosses
        # in several. A round of a cut edge in two was laid into the flat piece by piece: the piece beside the
        # cut projects a few microns wide, under the tolerance the flat is fused at, and was lost there, a
        # hole's rim with it (the hole filled, sheet.flat_incomplete). Round a bend's end the piece beside the
        # cut does not touch the bend's cylinder, so it was no break (sheet.uniform_thickness), and neither was
        # a corner of an outline rounded whole, nor a full round run on round a bend
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Splitter
        from OCP.collections import List_TopoDS_Shape

        def layered(part: bd.Shape, *tools: bd.Shape) -> bd.Solid:
            """``part`` cut along each of ``tools`` (by the kernel's splitter) and joined again as the kernel
            joins it: the same solid, no face merged."""
            parts, cutters = List_TopoDS_Shape(), List_TopoDS_Shape()
            parts.Append(part.solids()[0].wrapped)
            for tool in tools:
                cutters.Append(tool.wrapped)
            op = BRepAlgoAPI_Splitter()
            op.SetArguments(parts)
            op.SetTools(cutters)
            op.Build()
            joined, *rest = bd.Compound(op.Shape()).solids()
            while rest:  # the next piece that touches what is joined so far
                for piece in rest:
                    fuse = BRepAlgoAPI_Fuse(joined.wrapped, piece.wrapped)
                    fuse.Build()
                    solids = bd.Compound(fuse.Shape()).solids()
                    if len(solids) == 1:
                        joined = solids[0]
                        rest.remove(piece)
                        break
                else:
                    raise AssertionError("the pieces do not join")
            return joined

        def level(z: float) -> bd.Face:
            return bd.Face.make_rect(400, 400, bd.Plane.XY.offset(z))

        def within(steps: list[tuple], t: float, depth: float, width: float) -> bd.Shell:
            """The surface ``depth`` into ``bent(steps, t, width)`` from the face its path runs on, run on past
            the part's ends and sides."""
            longer = [("line", steps[0][1] + 10), *steps[1:-1], ("line", steps[-1][1] + 10)]
            path = centre([(how, size, *(inside + t - 2 * depth for inside in radius))
                           for how, size, *radius in longer], 2 * depth)
            return bd.Shell.extrude(bd.Pos(-10, -10, 0) * path, (0, width + 20, 0))

        def agrees(split: bd.Shape, whole: bd.Shape, **options) -> None:
            self.assertGreater(len(split.faces()), len(whole.faces()))
            result, wanted = checked(split, **options), checked(whole, **options)
            self.assertTrue(wanted.ok, [f.message for f in wanted.findings if f.severity == "error"])
            self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
            self.assertEqual(verdicts(result), verdicts(wanted))
            found, expected = (r.measurements["parts"]["items"][0] for r in (result, wanted))
            for key in ("thickness_mm", "flat_length_mm", "flat_width_mm", "flat_material_fraction"):
                self.assertAlmostEqual(found[key], expected[key], places=3, msg=key)
            self.assertAlmostEqual(found["flat_area_mm2"], expected["flat_area_mm2"], delta=0.05)
            for family, keys in (("holes", ("size_mm", "countersunk")), ("bends", ("length_mm",))):
                self.assertEqual([[item[key] for key in keys] for item in result.measurements[family]["items"]],
                                 [[item[key] for key in keys] for item in wanted.measurements[family]["items"]], family)
            # the breaks are said as deep as the whole part's, not as one piece of one
            deep = [next(f.value for f in r.findings if f.code == "sheet.edge_break") for r in (result, wanted)]
            self.assertAlmostEqual(deep[0], deep[1], places=3)
            self.assertEqual(len(sheet.unfold(split, **options).faces()), 1)

        def rims(part: bd.Shape, both: bool) -> list[bd.Edge]:
            levels = part.edges().group_by(bd.Axis.Z)
            return [*levels[-1], *(levels[0] if both else [])]

        # flat plates 2 thick (z = 0 to 2), their rims broken, cut level inside the breaks
        holed = (bd.RectangleRounded(80, 40, 5) - bd.Pos(-15, 0) * bd.SlotOverall(30, 8)
                 - bd.Pos(25, 8) * bd.Circle(4)).face()
        notched = (bd.Rectangle(80, 40) - bd.Pos(0, 20) * bd.Ellipse(12, 6)).face()
        for name, outline, how, size, both, cuts, turn in (
                ("round, cut near its foot", holed, bd.fillet, 0.9, False, (1.118,), False),
                ("chamfers, each cut in two", holed, bd.chamfer, 0.8, True, (0.72, 1.28), False),
                ("rounds that meet in mitres", bd.Rectangle(80, 40).face(), bd.fillet, 0.2, True, (1.89,), False),
                ("round along an ellipse, cut twice", notched, bd.fillet, 0.4, False, (1.64, 1.8), True),
                ("rounds along an ellipse, cut near their feet", notched, bd.fillet, 0.2, True, (0.18, 1.82), False)):
            with self.subTest(plate=name):
                whole = how(rims(bd.extrude(outline, amount=2), both), size)
                split = layered(whole, *(level(z) for z in cuts))
                agrees(*((turned(split), turned(whole)) if turn else (split, whole)))

        # a plate cut across, its round's faces end to end: the outline is chorded as the whole part's is
        whole = bd.fillet(rims(bd.extrude(bd.Ellipse(40, 20).face(), amount=2), False), 0.9)
        with self.subTest(plate="round along an ellipse, cut across"):
            agrees(layered(whole, bd.Face.make_rect(400, 400, bd.Plane.YZ.offset(7))), whole)

        # a plate's outline and holes rounded whole (r = t/2), cut off its mid-plane: one with round corners and
        # holes, one with square corners (a face of its own turns each)
        for name, outline in (("round corners, holes", holed), ("square corners", bd.Rectangle(80, 40).face())):
            whole = bd.extrude(bd.Pos(0, 0, -1) * outline, amount=2)
            for wire in outline.wires():
                whole = whole + tube(wire, 2.0)
            for off in (0.04, 0.4):
                with self.subTest(plate="rounded whole", corners=name, cut_off_the_middle=off):
                    agrees(layered(whole, level(off)), whole)

        # an L bracket, its sides' edges rounded along the flanges and round the bend (or round the bend alone),
        # cut along a surface inside the rounds: near the foot of the outside ones, then of the inside ones
        steps = [("line", 30), ("bend", 90, 2.0), ("line", 40)]
        square = bent(steps, 2.0, 50.0)
        sides = [edge for face in square.faces().filter_by(bd.Axis.Y) for edge in face.edges()
                 if abs(edge.length - 2.0) > 1e-6]
        for name, edges in (("all round", sides),
                            ("round the bend", [edge for edge in sides if edge.geom_type == bd.GeomType.CIRCLE])):
            whole = bd.fillet(edges, 0.6)
            for depth in (0.57, 1.46):
                with self.subTest(bracket=name, cut_at=depth):
                    agrees(layered(whole, within(steps, 2.0, depth, 50.0)), whole, k_factor=0.4)

        # and one whose sides are rounded whole, round the bend too
        whole = rounded(steps, 2.0, 50.0, 2)
        for depth in (1.04, 1.6):
            with self.subTest(bracket="sides rounded whole", cut_at=depth):
                agrees(layered(whole, within(steps, 2.0, depth, 50.0)), whole, k_factor=0.4)

    def test_a_round_whose_edges_meet_a_hair_apart_is_laid_whole(self) -> None:
        # a plate notched along half an ellipse, its rims rounded: the kernel may end the mitre where the round
        # along the ellipse meets the one along the plate's edge a fraction of a micron off the vertex it shares
        # with the edge along the skin (within that vertex's tolerance). The round's outline laid into the flat
        # did not close over that gap and was laid as its sampled points, the mitre's chords a hundredth of a
        # millimetre long, under the tolerance the breaks are fused with: the fuse lost material there (the
        # flat two faces, 5 mm2 short, 99.7% of the material)
        outline = (bd.Rectangle(80, 40) - bd.Pos(0, 20) * bd.Ellipse(12, 6)).face()
        plate = bd.extrude(outline, amount=2)
        levels = plate.edges().group_by(bd.Axis.Z)
        unbroken = checked(plate).measurements["parts"]["items"][0]["flat_area_mm2"]
        for name, edges, radius in (("one rim", levels[-1], 0.4), ("both rims", levels[0] + levels[-1], 0.2)):
            with self.subTest(rounded=name):
                part = bd.fillet(edges, radius)
                found = checked(part).measurements["parts"]["items"][0]
                self.assertAlmostEqual(found["flat_area_mm2"], unbroken, delta=0.05)
                self.assertAlmostEqual(found["flat_material_fraction"], 1.0, places=3)
                flat = sheet.unfold(part)
                self.assertEqual(len(flat.faces()), 1)
                # the outline's area, within its chords' sag along the notch
                self.assertAlmostEqual(flat.area, 80 * 40 - math.pi * 12 * 6 / 2, delta=0.3)

    def test_what_countersinks_and_edge_breaks_cut_is_not_missing_from_the_flat(self) -> None:
        # the flat's area was held against the part's volume, which countersinks and edge breaks cut after the
        # blank: 24 countersinks in a 2 mm plate, or a 1 mm chamfer round a small 3 mm one, read 107% and 111%
        # of the material, an error on a flat that was right (and ``unfold`` refused it)
        grid = [(x, y) for x in range(-35, 36, 10) for y in (-12, 0, 12)]
        sunk = self._sunk((80, 40, 2), grid, [], 3.2, 6.4)
        levels = bd.Box(20, 10, 3).edges().group_by(bd.Axis.Z)
        for name, part, area in (("countersinks", sunk, 3200 - len(grid) * math.pi * 1.6 ** 2),
                                 ("chamfers", bd.chamfer(levels[0] + levels[-1], 1.0), 200.0)):
            with self.subTest(part=name):
                result = checked(part)
                self.assertNotIn("sheet.flat_incomplete", {f.code for f in result.findings})
                found = result.measurements["parts"]["items"][0]
                self.assertAlmostEqual(found["flat_material_fraction"], 1.0, places=2)
                self.assertAlmostEqual(sheet.unfold(part).area, area, delta=0.01)

    def test_a_full_round_edge_is_laid_into_the_flat(self) -> None:
        # a cut edge rounded from skin to skin (r = t/2) leaves no face of the cut square to the skins: it was
        # read as the cut edge itself, so the flat stopped at the skins, t/2 short of the round at each such
        # edge and with no finding (an 80 x 40 plate with full-round ends: 78 x 40, ok), and a hole's round
        # left the hole a thickness too wide. A full round is a break of both skins, laid into the flat as one
        t, width = 2.0, 40.0

        def rounded_ends(part: bd.Part) -> bd.Part:
            """Each end of the sheet (its t-wide cut faces across ``width``) rounded whole, a t/2 further out."""
            ends = [face for face in part.faces().filter_by(bd.GeomType.PLANE)
                    if abs(face.area - t * width) < 1e-6 and abs(face.normal_at().Y) < 1e-6]
            for face in ends:
                part = part + bd.Pos(*face.center()) * bd.Rot(90, 0, 0) * bd.Cylinder(t / 2, width)
            return part

        def rounded_all(sketch: bd.Sketch) -> bd.Part:
            """The sketch cut from a t sheet, every outline and hole rounded whole: a t/2 tube along each wire."""
            (face,) = sketch.faces()
            part = bd.extrude(bd.Pos(0, 0, -t / 2) * face, amount=t)
            for wire in face.wires():
                edge = wire.edges()[0]
                ring = bd.Face(bd.Wire(bd.Edge.make_circle(t / 2, bd.Plane(edge @ 0, z_dir=edge % 0))))
                part = part + bd.sweep(ring, path=wire, transition=bd.Transition.ROUND)
            return part

        def square(sketch: bd.Sketch) -> bd.Part:
            """The same blank cut square: the outline a t/2 out, each hole a t/2 in."""
            (face,) = sketch.faces()
            blank = bd.offset(bd.Face(face.outer_wire()), t / 2, kind=bd.Kind.ARC)
            for wire in face.inner_wires():
                blank = blank - bd.offset(bd.Face(wire), -t / 2, kind=bd.Kind.ARC)
            return bd.extrude(bd.Pos(0, 0, -t / 2) * blank, amount=t)

        holed = bd.Sketch() + bd.RectangleRounded(76, 36, 4) - bd.Circle(5)
        sharp = bd.Sketch() + bd.Rectangle(76, 36)  # its corners turned by the tubes' rounds of revolution
        l_steps = [("line", 30), ("bend", 90, 2.0), ("line", 40)]
        u_steps = [("line", 30), ("bend", 90, 2.0), ("line", 40), ("bend", 90, 2.0), ("line", 30)]
        cases = (("plate, ends", rounded_ends(bd.Box(78, width, t)), bd.Box(80, width, t)),
                 ("L bracket, ends", rounded_ends(bent(l_steps, t, width)),
                  bent([("line", 31), *l_steps[1:2], ("line", 41)], t, width)),
                 ("U bracket, ends", rounded_ends(bent(u_steps, t, width)),
                  bent([("line", 31), *u_steps[1:4], ("line", 31)], t, width)),
                 ("plate with a hole, all round", rounded_all(holed), square(holed)),
                 ("plate with sharp corners, all round", rounded_all(sharp), square(sharp)))
        for name, part, blank in cases:
            with self.subTest(part=name):
                result, want = checked(part), checked(blank)
                self.assertTrue(result.ok, [f.message for f in result.findings if f.severity in ("error", "warning")
                                            and f.code != "sheet.edge_break"])
                found, square_part = result.measurements["parts"]["items"][0], want.measurements["parts"]["items"][0]
                for key in ("flat_length_mm", "flat_width_mm"):
                    self.assertAlmostEqual(found[key], square_part[key], places=3)
                self.assertAlmostEqual(found["flat_area_mm2"], square_part["flat_area_mm2"], delta=0.05)
                self.assertAlmostEqual(found["flat_material_fraction"], 1.0, places=2)
                self.assertEqual([hole["size_mm"] for hole in result.measurements["holes"]["items"]],
                                 [hole["size_mm"] for hole in want.measurements["holes"]["items"]])
                self.assertEqual([f.code for f in result.findings if f.severity == "warning"], ["sheet.edge_break"])
                self.assertEqual(len(sheet.unfold(part).faces()), 1)

    def test_a_full_round_run_on_round_a_bend_is_unrolled_with_it(self) -> None:
        # a bracket's side edges rounded whole along its flanges and round its bends: round a bend the round is
        # a torus from one of its cylinders to the other, which was read as the cut edge, so the bend's strip
        # stopped at the skins, a t/2 short of the round on each such side (48 mm of a 50 mm bend) and the
        # flanges' rounds ran on past it (sheet.bend_relief_width, a relief 0 mm wide): FAILED. Where the whole
        # outline is rounded, a corner's round touches the skin at a point, which the skin holds as a wire of
        # one degenerate edge, and the holes were not measured (measurement_failed)
        l_steps = [("line", 30), ("bend", 90, 2.0), ("line", 40)]
        u_steps = [("line", 30), ("bend", 90, 2.0), ("line", 40), ("bend", 90, 2.0), ("line", 30)]
        sixty = [("line", 30), ("bend", 60, 2.0), ("line", 40)]
        cases = (("L bracket, both sides", l_steps, 2.0, 2), ("U bracket, one side", u_steps, 2.0, 1),
                 ("60 degrees, both sides", sixty, 1.5, 2),
                 ("60 degrees, its whole outline", sixty, 2.0, 3))  # (its unfolded skin holds such a wire)
        for name, steps, t, sides in cases:
            with self.subTest(part=name):
                part, width = rounded(steps, t, 50.0, sides), 50.0
                result = checked(part, k_factor=0.4)
                want = checked(bent(steps, t, width), k_factor=0.4).measurements["parts"]["items"][0]
                self.assertTrue(result.ok, [f.message for f in result.findings if f.severity in ("error", "warning")
                                            and f.code != "sheet.edge_break"])
                found = result.measurements["parts"]["items"][0]
                for key in ("flat_length_mm", "flat_width_mm"):
                    self.assertAlmostEqual(found[key], want[key], places=3)
                # (the whole outline's corners are rounded a t/2 in the flat too)
                corners = (4 - math.pi) * (t / 2) ** 2 if sides == 3 else 0.0
                self.assertAlmostEqual(found["flat_area_mm2"], want["flat_area_mm2"] - corners, delta=0.05)
                self.assertAlmostEqual(found["flat_material_fraction"], 1.0, places=3)
                self.assertEqual([b["length_mm"] for b in result.measurements["bends"]["items"]],
                                 [width] * (len(steps) // 2))
                self.assertEqual([f.code for f in result.findings if f.severity == "warning"], ["sheet.edge_break"])
                self.assertEqual(len(sheet.unfold(part, k_factor=0.4).faces()), 1)

    def test_an_s_jog_of_two_tangent_bends_unrolls_whole(self) -> None:
        # two bends meeting with no flat between them: a joggle, unrolled one strip after the other
        jog = bent([("line", 40), ("bend", 90, 1.5), ("bend", -90, 1.5), ("line", 40)], 1.5, 40, "jog")
        allowance = math.pi / 2 * (1.5 + 0.4 * 1.5)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            result = checked(turn * jog, material="aluminum", k_factor=0.4)
            self.assertTrue(result.ok, [f.message for f in result.findings if f.severity == "error"])
            part = result.measurements["parts"]["items"][0]
            self.assertAlmostEqual(part["flat_material_fraction"], 1.0, places=4)
            self.assertAlmostEqual(part["flat_length_mm"], 80 + 2 * allowance, places=3)
            self.assertEqual((part["bend_count"], part["flange_count"], part["not_in_flat"]), (2, 2, []))
            codes = {f.code for f in result.findings}
            self.assertIn("sheet.joggle", codes)
            self.assertFalse(codes & {"sheet.flat_incomplete", "sheet.not_unfolded", "sheet.flange_length"})
            self.assertNotIn("-0.0", json.dumps(result.measurements))

    def test_a_joggle_is_two_opposed_bends_a_short_web_apart_and_a_compound_bend_is_none(self) -> None:
        def joggles(steps: list[tuple], turn: bd.Location) -> tuple[list, set[str]]:
            result = checked(turn * bent(steps, 1.5, 40, "jog"), material="aluminum", k_factor=0.4)
            self.assertAlmostEqual(result.measurements["parts"]["items"][0]["flat_material_fraction"], 1.0, places=4)
            return [f for f in result.findings if f.code == "sheet.joggle"], {f.code for f in result.findings}

        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            # opposed, no web and a 1 mm web (under the 3 mm minimum): one joggle warning, no flange_length
            for web in ([], [("line", 1.0)]):
                found, codes = joggles([("line", 40), ("bend", 90, 1.5), *web, ("bend", -90, 1.5), ("line", 40)],
                                       turn)
                self.assertEqual([f.severity for f in found], ["warning"], (web, turn))
                self.assertIn("needs an offset/joggle die; not measured", found[0].message)
                self.assertNotIn("sheet.flange_length", codes)
            # opposed with a web at a flange's length: two ordinary bends
            found, codes = joggles([("line", 40), ("bend", 90, 1.5), ("line", 6.0), ("bend", -90, 1.5),
                                    ("line", 40)], turn)
            self.assertEqual(found, [])
            # the same way round, tangent: a compound bend, unrolled, no joggle
            found, codes = joggles([("line", 40), ("bend", 45, 2.0), ("bend", 45, 6.0), ("line", 40)], turn)
            self.assertEqual(found, [])
            # a joggle's tight radii keep their own warning
            _, codes = joggles([("line", 40), ("bend", 90, 0.1), ("bend", -90, 0.1), ("line", 40)], turn)
            self.assertIn("sheet.bend_radius", codes)

    def test_a_part_s_formed_faces_and_broken_edges_are_one_finding_each_and_named_as_its_ref_names_it(self) -> None:
        # an unnamed part's refs are bare (face 7): its chamfers are one finding, not one a face
        plate = bd.chamfer(bd.Box(80, 40, 3).edges(), 0.5)
        broken = [f for f in checked(plate).findings if f.code == "sheet.edge_break"]
        self.assertEqual(len(broken), 1)
        # a part placed twice is measured at its first occurrence, its ref's name the message's
        part = {"name": "pin_right", "is_sheet": False, "why": "its 12 mm thickness is no sheet's",
                "location": "pin_left/face 2"}
        (said,) = [f for f in sheet_rules.findings({"parts": {"items": [part]}}, {}, False)
                   if f.code == "sheet.not_sheet"]
        self.assertTrue(said.message.startswith("pin_left is not one sheet"), said.message)

    def test_a_cone_between_flanges_is_one_formed_surface(self) -> None:
        section = bd.Pos(10, 0, 0) * profile([("line", 20), ("bend", 30, 2.0), ("line", 25), ("bend", -30, 2.0),
                                              ("line", 20)], 2.0)
        cone = bd.revolve(bd.Plane.XZ * section, bd.Axis.Z, 360)
        cone.label = "cone"
        result = checked(cone)
        (formed,) = [f for f in result.findings if f.code == "sheet.formed_surface"]
        # no guide gives a stamped or rolled form's feasibility limit: not measured, quoted as a formed feature
        self.assertEqual(formed.severity, "warning")
        self.assertIn("cone", formed.message)
        self.assertIn("not measured", formed.message)
        self.assertNotIn("sheet.uniform_thickness", {f.code for f in result.findings})  # not six 0.005 mm departures

    def test_thickness_departures_say_how_thick_against_the_sheet(self) -> None:
        plate = bd.Pos(0, 0, 1) * bd.Box(80, 50, 2) + bd.Pos(0, 0, 2.5) * bd.Box(20, 20, 1)  # a 3 mm patch
        plate.label = "patched"
        result = checked(plate)
        # one feature, one finding: its top and its four sides, each 1 mm above the sheet, at one ref
        (thicker,) = [f.message for f in result.findings if f.code == "sheet.uniform_thickness"]
        self.assertIn("local thickness (the sheet's is the maximum) 3 mm is over the 2 mm maximum", thicker)
        self.assertIn("and 4 more at this ref", thicker)
        self.assertEqual(len({item["face"] for item in result.measurements["not_sheet"]["items"]}), 5)
        # a wall 3 mm thick where the bracket is 2: its skins, not its end caps, whose rays run along it
        wall = bent([("line", 40), ("bend", 90, 2), ("line", 30)], 2.0, 50, "L") + bd.Pos(44.5, 25, 19) * bd.Box(1, 50, 30)
        found = items(measured(wall.clean()), "not_sheet")
        self.assertTrue([item for item in found if item["local_thickness_mm"] == 3.0])
        self.assertFalse([item for item in found if abs(item["xyz"][2] - 34) < 1e-6])  # the wall's top cap
        block = bd.fillet(bd.Box(60, 40, 20).edges(), 3)
        block.label = "block"
        machined = checked(block)
        self.assertTrue(machined.measurements["not_sheet"]["items"])  # the facts stay
        self.assertNotIn("sheet.uniform_thickness", {f.code for f in machined.findings})
        self.assertEqual(failed(machined, "sheet.uniform_thickness"), [])


if __name__ == "__main__":
    unittest.main()
