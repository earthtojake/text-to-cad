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
        round_holes = [i for i in items(report, "holes") if i["kind"] == "round"]
        self.assertEqual([i["diameter_mm"] for i in round_holes], [6.0])

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
                               (bd.Box(100, 7, 2), "sheet 2 mm, 0 bend(s), flat 100 x 7 mm")):
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
        # past an inch it is plate, no sheet shop's work: text-to-cad's own floor, said as its own
        (plate,) = [f for f in checked(bd.Box(160, 120, 30)).findings if f.severity in ("error", "warning")]
        self.assertEqual((plate.severity, plate.code), ("error", "sheet.thickness_limit"))
        self.assertIn("source: text-to-cad, text-to-cad's own figure", plate.message)

    def test_a_tube_is_a_closed_section_and_a_slit_one_a_rolled_sheet_at_its_wall(self) -> None:
        tube = bd.Cylinder(20, 100) - bd.Cylinder(18, 100)
        slit = tube - bd.Pos(20, 0, 0) * bd.Box(10, 1, 120)
        for shape, said in ((tube, "a closed section, a tube of 2 mm wall and 18 mm inside radius"),
                            (slit, "a 2 mm sheet rolled to a 18 mm inside radius with no flat flange")):
            for placed in (shape, turned(shape)):
                result = checked(placed)
                (finding,) = [f for f in result.findings if f.severity == "error"]
                self.assertEqual(finding.code, "sheet.not_sheet")
                self.assertIn(said, finding.message)
                self.assertAlmostEqual(result.measurements["parts"]["items"][0]["thickness_mm"], 2.0, places=6)

    def test_a_grille_s_slot_walls_do_not_outvote_its_skins(self) -> None:
        t = 3.0  # webs half the sheet's thickness between long slots: the walls face each other 1.5 mm apart
        plate = bd.Pos(0, 0, t / 2) * bd.Box(140, 120, t)
        for i in range(30):
            plate -= bd.Pos(-58 + i * 3.5, 0, t / 2) * bd.Box(2, 110, 3 * t)
        part = items(measured(plate), "parts")[0]
        self.assertAlmostEqual(part["thickness_mm"], 3.0, places=6)
        self.assertTrue(part["is_sheet"])


class NotJudgedTest(unittest.TestCase):
    """What is measured with no guide's limit is said so, and text-to-cad's own lines are said as its own."""

    def test_a_radius_of_many_thicknesses_is_no_single_hit_of_a_brake(self) -> None:
        rolled = checked(bent([("line", 20), ("bend", 120, 50), ("line", 20)], 2.0, 60))  # r = 25 t
        (warned,) = [f for f in rolled.findings if f.severity in ("error", "warning")]
        self.assertEqual((warned.severity, warned.code), ("warning", "sheet.bend_radius_max"))
        self.assertIn("25 ratio is over the 10 ratio recommended maximum", warned.message)
        self.assertIn("text-to-cad's own figure", warned.message)

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
