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


OPTIONS = {"thickness": None, "k_factor": 0.4, "material": None, "rules": "generic"}


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
        self.assertEqual(sheet_rules.k_factor("aluminum", "generic", 0.5, 1.0)[0], 0.33)
        self.assertEqual(sheet_rules.k_factor("stainless", "generic", 2.0, 1.0)[0], 0.45)
        self.assertEqual(sheet_rules.k_factor(None, "generic", 4.0, 1.0)[0], 0.50)
        k, said = sheet_rules.k_factor("aluminum", "sendcutsend", 3.175, 0.125 * 25.4)
        self.assertEqual(k, 0.44)
        self.assertIn("SendCutSend", said)

    def test_context_picks_each_sources_table(self) -> None:
        report = {"parts": {"items": [{"thickness_mm": 2.0}]}, "bends": {"items": [{"inside_radius_mm": 2.0}]}}
        found = sheet_rules.context(report, {"material": "steel", "rules": "protolabs"})
        self.assertAlmostEqual(found["protolabs_flange_t"], 2.75 * 2.0)  # CRS, .060-.090 in
        self.assertEqual(found["protolabs_edge_band"], "thick")
        self.assertEqual(found["tab_min_mm"], 4.0)
        self.assertEqual((found["sheet_long_mm"], found["sheet_short_mm"]), (1193.8, 990.6))
        found = sheet_rules.context({"parts": {"items": [{"thickness_mm": 0.125 * 25.4}]}, "bends": {"items": [{}]}},
                                    {"material": "aluminum", "rules": "sendcutsend", "sheet_size": "500x300"})
        self.assertAlmostEqual(found["scs_half_die_mm"], 0.630 * 25.4 / 2)
        self.assertEqual((found["sheet_long_mm"], found["sheet_short_mm"]), (500.0, 300.0))

    def test_every_set_judges_or_names_every_rule_another_set_judges(self) -> None:
        ids = {name: {rule.id.removeprefix("sheet.") for rule in rule_set.rules}
               for name, rule_set in sheet_rules.RULE_SETS.items()}
        every = set().union(*ids.values())
        for name, rule_set in sheet_rules.RULE_SETS.items():
            gaps = sheet_rules.NOT_JUDGED[name]
            self.assertEqual(every - ids[name], set(gaps), name)  # no silent gap, no stale one
            for rule in gaps:
                self.assertIn(rule, rule_set.note, name)

    def test_sendcutsend_gauges_and_their_fallbacks(self) -> None:
        self.assertEqual(sheet_rules.scs_row("steel", 2.0)[0], 0.074)       # within 0.005 in
        self.assertIsNone(sheet_rules.scs_row("aluminum", 3.0))            # 0.125 in is 3.175 mm
        report = {"parts": {"items": [{"thickness_mm": 3.0}]}, "bends": {"items": [{"inside_radius_mm": 3.0}]}}
        resolved = {"material": "5052", "rules": "sendcutsend", "thickness": None}
        found = sheet_rules.context(report, resolved)
        self.assertFalse(found["scs_gauge"])
        self.assertNotIn("scs_min_flange_mm", found)
        codes = [(f.severity, f.code) for f in sheet_rules.findings(report, resolved, False)]
        self.assertIn(("error", "sheet.gauge_unmatched"), codes)
        _, record = __import__("cad._internal.dfm.rules", fromlist=["evaluate"]).evaluate(
            {**report, "flanges": {"items": [{"length_outside_half_mm": 50.0}]}},
            sheet_rules.RULE_SETS["sendcutsend"], found)
        flange = [o["status"] for o in record["outcomes"] if o["rule"] == "sheet.flange_length"]
        self.assertIn("passed", flange)  # the gauge-free minimum judged where the gauge's is not
        self.assertNotIn("failed", flange)

    def test_sendcutsends_relief_width_is_half_the_thickness(self) -> None:
        from cad._internal.dfm import rules

        report = {"parts": {"items": [{"thickness_mm": 2.0, "is_sheet": True}]}, "bends": {"items": [{}]},
                  "reliefs": {"items": [{"kind": "bend", "width_mm": width, "location": f"p/face {n}", "detail": "d"}
                                        for n, width in ((1, 0.9), (2, 1.1))]}}
        resolved = {"material": "steel", "rules": "sendcutsend"}
        _, record = rules.evaluate(report, sheet_rules.RULE_SETS["sendcutsend"], sheet_rules.context(report, resolved))
        (width,) = [o for o in record["outcomes"] if o["rule"] == "sheet.bend_relief_width"]
        self.assertEqual([(f["value"], f["location"]) for f in width["failures"]], [(0.9, "p/face 1")])

    def test_options_and_findings(self) -> None:
        with self.assertRaisesRegex(ValueError, "--sheet-size"):
            manufacturing.options("step", "sheet", {"sheet_size": "big"})
        report = {"parts": {"items": [{"thickness_mm": 2.0, "is_sheet": True, "location": "p/face 1"}]},
                  "bends": {"items": [{"inside_radius_mm": 2.0, "location": "p/face 4"}]},
                  "holes": {"items": [{"size_mm": 0.2, "location": "p/face 9"}]}}
        codes = {f.code for f in sheet_rules.findings(report, {"thickness": 1.5, "bend_radius": 1.0, "kerf": 0.3,
                                                                "rules": "generic"}, False)}
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


def failed(result, rule: str) -> list[dict]:
    return [failure for outcome in result.measurements["rules"]["outcomes"] if outcome["rule"] == rule
            and outcome["status"] == "failed" for failure in outcome["failures"]]


def _boxes_bracket() -> bd.Part:
    """A 2 mm bracket of two boxes unioned: a sharp corner, no bend radius (base on z = 0, wall at x = 0)."""
    part = (bd.Pos(20, 15, 1) * bd.Box(40, 30, 2) + bd.Pos(1, 15, 15) * bd.Box(2, 30, 30)).clean()
    part.label = "boxes"
    return part


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
        alone = {f.code for f in sheet_rules.findings({"parts": {"items": [part]}}, {"rules": "generic"}, False)}
        self.assertIn("sheet.flat_incomplete", alone)
        sharp = {"parts": {"items": [part]}, "sharp_bends": {"items": [{"kind": "sharp", "location": "p/face 2",
                                                                         "thickness_mm": 2.0, "angle_deg": 90.0}]}}
        codes = {f.code for f in sheet_rules.findings(sharp, {"rules": "generic"}, False)}
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

    def test_a_hem_is_judged_by_its_own_rule(self) -> None:
        hem = bent([("line", 40), ("bend", 180, 0.5), ("line", 8)], 1.0, 30, "hem")  # inside diameter = t
        result = checked(hem, material="steel", thickness=1)
        self.assertEqual(failed(result, "sheet.bend_radius"), [])
        lid = bent([("line", 8), ("bend", 180, 0.5), ("line", 25), ("bend", 90, 1.0), ("line", 60)], 1.0, 50, "lid")
        self.assertNotIn("sheet.bend_radii_mixed", {f.code for f in checked(lid, thickness=1).findings})

    def test_sendcutsend_names_its_radius_and_does_not_contradict_it(self) -> None:
        # 5052 at the 0.080 in gauge, bent at the calculator's 0.038 in: nothing about the radius
        t, r = 0.080 * 25.4, 0.038 * 25.4
        good = checked(bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 50, "scs"), material="5052",
                       rules="sendcutsend")
        self.assertEqual(failed(good, "sheet.bend_radius") + failed(good, "sheet.bend_radius_shop"), [])
        # 2 mm steel (0.074 in) bent at r = t: it is bent at the tooling's radius, so its flanges move -- one
        # warning for the bend, naming the radius to model in mm and inches, no second finding beside it
        off = checked(bent([("line", 40), ("bend", 90, 2.0), ("line", 30)], 2.0, 50, "scs"), material="steel",
                      rules="sendcutsend")
        (shop,) = [f for f in off.findings if f.code == "sheet.bend_radius_shop"]
        self.assertEqual(shop.severity, "warning")
        self.assertIn("mild steel 0.074 in, 1.6 mm (0.063 in)", shop.hint)
        self.assertIn("SendCutSend bends mild steel 0.074 in at 1.6 mm (0.063 in)", shop.message)
        self.assertNotIn("sheet.bend_radius_differs", {f.code for f in off.findings})

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

    def test_a_cone_between_flanges_is_one_formed_surface(self) -> None:
        section = bd.Pos(10, 0, 0) * profile([("line", 20), ("bend", 30, 2.0), ("line", 25), ("bend", -30, 2.0),
                                              ("line", 20)], 2.0)
        cone = bd.revolve(bd.Plane.XZ * section, bd.Axis.Z, 360)
        cone.label = "cone"
        result = checked(cone)
        (formed,) = [f for f in result.findings if f.code == "sheet.formed_surface"]
        self.assertEqual(formed.severity, "error")
        self.assertIn("cone", formed.message)
        self.assertNotIn("sheet.uniform_thickness", {f.code for f in result.findings})  # not six 0.005 mm departures

    def test_sendcutsend_bends_5052_alone_among_aluminums(self) -> None:
        t, r = 0.080 * 25.4, 0.038 * 25.4
        bracket = bent([("line", 40), ("bend", 90, r), ("line", 30)], t, 50, "scs")
        alloy = checked(bracket, material="6061", rules="sendcutsend")
        (refused,) = [f for f in alloy.findings if f.code == "sheet.material_not_bent"]
        self.assertEqual(refused.severity, "error")
        self.assertIn("6061", refused.message)
        self.assertNotIn("sheet.material_not_bent", {f.code for f in checked(bracket, material="5052",
                                                                            rules="sendcutsend").findings})

    def test_thickness_departures_say_how_thick_against_the_sheet(self) -> None:
        plate = bd.Pos(0, 0, 1) * bd.Box(80, 50, 2) + bd.Pos(0, 0, 2.5) * bd.Box(20, 20, 1)  # a 3 mm patch
        plate.label = "patched"
        result = checked(plate)
        thicker = [f.message for f in result.findings if f.code == "sheet.uniform_thickness"]
        self.assertEqual(len(thicker), 5)  # its top and its four sides, each 1 mm above the sheet
        for message in thicker:
            self.assertIn("local thickness (the sheet's is the maximum) 3 mm is over the 2 mm maximum", message)
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
