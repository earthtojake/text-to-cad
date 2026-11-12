#!/usr/bin/env python3

"""Injection molding's verdicts on tiny parts built here: the pulls a part is offered and the one that does
better, a part of several solids and an assembly judged part by part, a verdict that holds however the part
is placed, and the type side's rules (``cad._internal.dfm.molding``: their sources, floors and the clamp's
press). The check's measurements are ``test_dfm_molding_walls``, ``test_dfm_molding_undercuts`` and
``test_dfm_molding_features``; the planted-defect corpus is ``test_dfm_molding_corpus``."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

import build123d as bd
import numpy as np

import cad
from cad._internal.dfm import molding as type_side
from cad._internal.dfm.rules import RuleSet
from cad.build123d import _dfm_brep
from tests.python.support.dfm_molding import A, BOTTOM, _check, _tray


class CandidatesAndPartsTest(unittest.TestCase):
    def test_a_blind_side_hole_ranks_its_own_axis_first(self) -> None:
        part = bd.Box(30, 20, 20) - bd.Pos(10, 0, 0) * bd.Rotation(0, 90, 0) * bd.Cylinder(3, 20)
        rows = {row["pull"]: row for row in _check(part, candidates=True).measurements["pulls"]["candidates"]}
        self.assertEqual((rows["x"]["undercut_count"], rows["x"]["undercut_candidate_area_mm2"]), (0, 0.0))
        self.assertEqual((rows["z"]["undercut_count"], rows["z"]["side_action_count"]), (1, 1))

    def test_pulls_tie_on_area_and_part_on_draft(self) -> None:
        rows = [{"pull": "x", "axis": [1, 0, 0], "undercut_candidate_area_mm2": 0.0, "zero_draft_wall_area_mm2": 0.4,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 1.66},
                {"pull": "z", "axis": [0, 0, 1], "undercut_candidate_area_mm2": 0.0, "zero_draft_wall_area_mm2": 11.4,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 7.46},
                {"pull": "y", "axis": [0, 1, 0], "undercut_candidate_area_mm2": 900.0, "zero_draft_wall_area_mm2": 0.0,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 9.0}]
        self.assertEqual([row["pull"] for row in type_side.ranked(rows)], ["z", "x", "y"])

    def test_a_cup_modelled_along_x_is_told_x_does_better(self) -> None:
        cup = bd.Rot(0, 90, 0) * (bd.Cone(20, 18, 20, align=BOTTOM) - bd.Pos(0, 0, 3) * bd.Cone(18, 16, 17, align=BOTTOM))
        result = _check(cup, pull="z")
        (said,) = [f for f in result.findings if f.code == "pull_better"]
        self.assertEqual(said.severity, "warning")
        self.assertIn("along x (1,0,0)", said.message)
        self.assertIn("--pull 1,0,0", said.hint)
        self.assertNotIn("the default", said.message)   # z was given
        self.assertEqual(result.measurements["pull_check"]["better"], "x")
        self.assertTrue(said.refs)   # the faces this pull falls by
        # The pulls offered are the part's own, not the world's: turned 37 deg about (1, 2, 3), the cup offers
        # the same directions turned with it, its axis first and toward its mouth -- where the world's x, y and z
        # are no directions of it.
        from cad.build123d import _dfm_molding

        def offered(shape: Any) -> list[tuple[str, np.ndarray]]:
            return _dfm_molding._own_pulls(_dfm_molding._Geometry(_dfm_brep.parts_of(shape).parts[0]))

        turn = bd.Axis((0, 0, 0), (1, 2, 3))
        straight, turned = offered(cup), offered(cup.rotate(turn, 37))
        self.assertEqual((straight[0][0], [round(float(value), 9) + 0.0 for value in straight[0][1]]), ("x", [1.0, 0.0, 0.0]))
        self.assertEqual(turned[0][0], "face0")
        self.assertEqual(len(straight), len(turned))
        for (_name, axis), (_other, moved) in zip(straight, turned):
            there = bd.Vector(*axis).rotate(turn, 37)
            self.assertGreater(float(moved @ np.array([there.X, there.Y, there.Z])), 0.99999)

    def test_a_part_tilted_off_the_default_pull_is_told_its_own_axis(self) -> None:
        # A clean tray turned 37 deg off the axes and checked with no --pull: along z a fifth of its surface is
        # trapped and no wall reads zero draft -- under both of the triggers that once asked whether the pull was
        # right. Every check asks now, and names the pull that does better: the tray's own axis.
        turn = bd.Rotation(20, 30, 0)
        result = _check(turn * _tray())
        (said,) = [f for f in result.findings if f.code == "pull_better"]
        self.assertIn("the default, z: none was given", said.message)
        self.assertIn("(the default pull)", result.summary)
        check = result.measurements["pull_check"]
        better = next(row for row in check["candidates"] if row["pull"] == check["better"])
        own = (turn * bd.Pos(0, 0, 1)).position
        self.assertAlmostEqual(abs(float(np.array(better["axis"]) @ np.array([own.X, own.Y, own.Z]))), 1.0, places=3)
        self.assertEqual((better["undercut_candidate_area_mm2"], better["zero_draft_wall_area_mm2"]), (0.0, 0.0))
        # along its own axis, given: nothing is trapped and no wall is without draft, so no other pull is read
        given = _check(turn * _tray(), pull=",".join(f"{value:.12g}" for value in (own.X, own.Y, own.Z)))
        self.assertNotIn("pull_better", {f.code for f in given.findings})
        self.assertEqual(given.measurements["pull_check"]["candidates"], [])
        self.assertNotIn("the default pull", given.summary)

    def test_a_pull_does_better_only_where_it_is_no_worse_anywhere(self) -> None:
        chosen = {"wall_area_mm2": 5000.0, "undercut_candidate_area_mm2": 400.0, "side_action_count": 1,
                  "zero_draft_wall_area_mm2": 0.0, "flat_parting": True}
        clean = {**chosen, "undercut_candidate_area_mm2": 0.0, "side_action_count": 0, "measured": "full"}
        self.assertTrue(type_side.dominates(clean, chosen))
        self.assertFalse(type_side.dominates(chosen, clean))
        # less trapped, but a wall without draft the measured pull has not: no better, and a tie is none
        self.assertFalse(type_side.dominates({**clean, "zero_draft_wall_area_mm2": 900.0}, chosen))
        self.assertFalse(type_side.dominates({**clean, "flat_parting": False}, chosen))
        self.assertFalse(type_side.dominates({**chosen, "undercut_candidate_area_mm2": 420.0}, chosen))
        # a feature nothing releases decides, whatever else: the pull that leaves none does better, though it
        # takes a lifter more (a tray lying 37 deg off the default pull, an off-centre boss in it)
        stuck = {**chosen, "unreleasable_count": 1}
        self.assertTrue(type_side.dominates({**chosen, "lifter_count": 1}, stuck))
        self.assertFalse(type_side.dominates(stuck, {**chosen, "lifter_count": 1}))
        # a pull only screened (its figures not all read) is never the one named
        self.assertIsNone(type_side.better_pull(chosen, [{**clean, "measured": "trapped"}]))
        self.assertEqual(type_side.better_pull(chosen, [clean | {"pull": "x"}])["pull"], "x")

    def test_two_solids_touching_are_said_to_be_fused_and_their_contact_is_no_undercut(self) -> None:
        pair = bd.Compound([bd.Box(10, 10, 10), bd.Pos(10, 0, 0) * bd.Box(10, 10, 10)])
        pair.label = "pair"
        result = _check(pair)
        # one thing said once: the part's several solids are every process's warning, which says of molding that
        # their contacts are left out; each pair is a fact of the report
        (said,) = [f for f in result.findings if f.code in ("several_solids", "solids_touching")]
        self.assertEqual(said.code, "several_solids")
        self.assertIn("where two touch without being fused", said.message)
        self.assertIn("fuse", said.hint)
        (touching,) = result.measurements["touching"]["items"]
        self.assertEqual(touching["solids"], [1, 2])
        self.assertAlmostEqual(touching["contact_area_mm2"], 100.0, delta=1.0)
        self.assertEqual(result.measurements["undercuts"]["candidate_area_mm2"], 0.0)
        self.assertNotIn("several_bodies", {f.code for f in result.findings})
        # the contact faces are no walls: six sides of the pair, not eight
        self.assertEqual(len(result.measurements["draft"]["items"]), 6)

    def test_several_solids_in_one_part_are_said(self) -> None:
        pair = bd.Box(10, 10, 10) + bd.Pos(30, 0, 0) * bd.Box(10, 10, 10)
        self.assertEqual(len(pair.solids()), 2)
        found = _check(pair).findings
        (said,) = [f for f in found if f.code == "several_solids"]   # every process's warning, once
        self.assertIn("2 solids in one part", said.message)
        self.assertIn("shadow each other", said.message)
        self.assertNotIn("several_bodies", {f.code for f in found})

    def test_an_assembly_is_measured_part_by_part_at_its_parts_refs(self) -> None:
        plain = bd.Box(20, 20, 10)
        plain.label = "plain"
        drafted = bd.Pos(40, 0, 0) * bd.extrude(bd.Rectangle(20, 20), 10, taper=3)
        drafted.label = "drafted"
        result = _check(bd.Compound(label="pair", children=[plain, drafted]))
        failed = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.draft_min")
        self.assertEqual({failure["location"].split("/face")[0] for failure in failed["failures"]}, {"plain"})
        self.assertEqual(len(result.measurements["projection"]["items"]), 2)
        (said,) = [f for f in result.findings if f.code == "several_bodies"]
        self.assertEqual(sorted(said.refs), ["drafted", "plain"])   # its parts, as `cad step inspect` takes them
        self.assertNotIn("pull_check", result.measurements)   # each part opens its own way: no one pull to compare
        self.assertEqual([part["own"] for part in result.measurements["pulls"]], [False, False])

    def test_a_part_that_occurs_twice_is_judged_each_way_it_stands_and_counted_every_time(self) -> None:
        # A STEP holds a part's geometry once. Its occurrences turned alike are measured once and counted twice
        # in the totals; one turned on its side is a part of its own, judged along its own pull: an assembly's
        # parts lie as they are assembled, not as each is molded, and none fails it for that.
        def pair(turn: Any) -> Any:
            clip = bd.extrude(bd.Rectangle(20, 20), 3, taper=3)
            clip.label = "clip"
            other = bd.Pos(40, 0, 0) * turn * clip
            other.label = "clip"
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "pair.step"
                bd.export_step(bd.Compound(label="pair", children=[clip, other]), str(path))
                return cad.step.dfm(path, process="molding", material="abs")

        alike = pair(bd.Rot(0, 0, 0))
        (body,) = alike.measurements["bodies"]
        self.assertEqual(body["occurrences"], 2)
        (one,) = alike.measurements["projection"]["items"]
        self.assertEqual(one["occurrences"], 2)
        self.assertAlmostEqual(alike.measurements["projection"]["projected_area_mm2"], 2 * one["projected_area_mm2"],
                               delta=0.1)
        self.assertAlmostEqual(alike.measurements["projection"]["volume_mm3"], 2 * one["volume_mm3"], delta=0.1)
        self.assertAlmostEqual(alike.measurements["clamp"]["tons"], 2 * alike.measurements["clamp"]["items"][0]["tons"],
                               delta=0.011)
        self.assertEqual(alike.measurements["rules"]["failed"], [])
        turned = pair(bd.Rot(90, 0, 0))
        self.assertEqual([body["occurrences"] for body in turned.measurements["bodies"]], [1, 1])
        flat, side = turned.measurements["pulls"]
        self.assertEqual((flat["own"], side["own"]), (False, True))
        self.assertAlmostEqual(abs(side["axis"][1]), 1.0, places=6)   # its own axis, the world's y
        (said,) = [f for f in turned.findings if f.code == "part_pull"]
        self.assertEqual((said.severity, said.refs), ("warning", [side["part"]]))
        flat, side = turned.measurements["projection"]["items"]
        self.assertAlmostEqual(side["projected_area_mm2"], flat["projected_area_mm2"], delta=1.0)
        self.assertEqual((turned.ok, turned.measurements["rules"]["failed"]), (True, []))
        self.assertNotIn("occurrences_measured_once", {f.code for f in turned.findings + alike.findings})

    def test_a_step_reads_as_its_live_shape(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tray.step"
            bd.export_step(_tray(), str(path))
            from_file = cad.step.dfm(path, process="molding", material="abs").measurements
        live = _check(_tray()).measurements
        for family in ("draft", "undercuts", "parting"):
            self.assertEqual(len(from_file[family]["items"]), len(live[family]["items"]), family)
        self.assertEqual(from_file["thickness"]["nominal_mm"], live["thickness"]["nominal_mm"])


class OrientationTest(unittest.TestCase):
    def test_the_verdict_and_the_figures_do_not_turn_with_the_part_s_placement(self) -> None:
        # A box with square walls 18 mm deep inside (an error), a pad and a side window, off-centre. Turned about
        # the pull, moved, turned any way or tilted a third of a degree off the axes with its pull, it is the same
        # part: its verdict, its findings and its figures hold.
        part = bd.Box(60, 40, 20, align=BOTTOM) - bd.Pos(0, 0, 2) * bd.Box(56, 36, 20, align=BOTTOM) + \
            bd.Pos(-10, 5, 2) * bd.Box(12, 8, 3, align=BOTTOM) - bd.Pos(0, 20, 10) * bd.Box(10, 6, 4)

        def read(shape: Any, pull: str | None = None) -> tuple:
            result = _check(shape, pull=pull)
            m = result.measurements
            codes = sorted((f.severity, f.code) for f in result.findings if f.severity != "info")
            (window,) = m["undercuts"]["items"]
            return (result.ok, codes, m["thickness"]["nominal_mm"], m["thickness"]["max_mm"],
                    m["undercuts"]["candidate_area_mm2"], m["draft"]["wall_area_mm2"], window)

        ok, codes, nominal, thick, trapped, walls, window = read(part)
        self.assertFalse(ok)
        self.assertIn(("error", "molding.draft_zero"), codes)
        self.assertEqual((window["release"], window["side_actions"]), ("side_action", ["+y"]))
        placements = [(bd.Rot(0, 0, 30.0), None), (bd.Pos(250, -40, 1000), None),
                      (bd.Rot(0.3, 0, 0), "tilted"), (bd.Rot(23, -37, 61), "turned")]
        def turned(place: Any, x: float, y: float, z: float) -> np.ndarray:
            moved = (place * bd.Pos(x, y, z)).position - place.position
            return np.array([moved.X, moved.Y, moved.Z])

        def way_of(name: str) -> np.ndarray:
            if "," in name:
                found = np.array([float(value) for value in name.split(",")])   # as said, to three places
                return found / np.linalg.norm(found)
            return np.eye(3)["xyz".index(name[1])] * (1.0 if name[0] == "+" else -1.0)

        for place, pulled in placements:
            pull = ",".join(f"{value:.15g}" for value in turned(place, 0, 0, 1)) if pulled else None
            got = read(place * part, pull)
            self.assertEqual((ok, codes), got[:2], place)
            for want, have in zip((nominal, thick, walls), (got[2], got[3], got[5])):
                self.assertAlmostEqual(want, have, delta=1e-3 * max(1.0, abs(want)), msg=place)
            # the trapped area is sampled: a rectangle's mesh takes either diagonal, and its samples follow it
            self.assertAlmostEqual(trapped, got[4], delta=0.05 * trapped, msg=place)
            # the window's place and its slide, in the world the part stands in
            there = (place * bd.Pos(*window["xyz"])).position
            self.assertLess(float(np.linalg.norm(np.asarray(got[6]["xyz"]) - np.array([there.X, there.Y, there.Z]))),
                            0.5, place)
            (slide,) = got[6]["side_actions"]
            self.assertGreater(float(way_of(slide) @ turned(place, 0, 1, 0)), 0.9999, place)


class RulesTest(unittest.TestCase):
    def test_the_rules_cite_their_numbers_and_name_molding(self) -> None:
        self.assertIsInstance(type_side.RULES, RuleSet)
        for rule in type_side.RULES.rules:
            self.assertTrue(rule.id.startswith("molding."), rule.id)
            self.assertTrue(type_side.RULES.source(rule.source).url.startswith("https://"))
        # the wall table, in inches on its page, is millimetres here.
        self.assertAlmostEqual(type_side.WALL_RANGES["abs"][0], 1.143, places=3)
        self.assertAlmostEqual(type_side.WALL_RANGES["pc"][1], 3.81, places=3)

    def test_a_part_past_a_large_press_is_warned_and_one_past_any_press_built_fails(self) -> None:
        # The clamp force is an estimate of the part's projected area; the press that gives it is a shop's. Two
        # floors of text-to-cad's own stand on it all the same: a 12 m x 3 m panel takes 56 000 tons at a ton per
        # square inch, half the lowest factor published and five times what any press built gives -- it does not
        # read OK; a 2 m2 one is molded, on a press few shops run.
        def clamp(shape: Any) -> tuple[bool, dict[str, str], float]:
            result = _check(shape)
            press = {f.code: f.severity for f in result.findings if f.code.startswith("molding.clamp")}
            self.assertTrue(all(f.source.startswith("text-to-cad, ") for f in result.findings if f.code in press))
            return result.ok, press, result.measurements["clamp"]["tons"]

        ok, press, tons = clamp(bd.extrude(bd.Rectangle(12000, 3000), 30, taper=3))
        self.assertEqual((ok, press), (False, {"molding.clamp_beyond_press": "error"}))
        self.assertGreater(tons, 20 * type_side.CLAMP_LARGEST_TONS)
        # a 2 m2 panel is estimated past the largest press and takes a third of it at the least factor: warned
        ok, press, tons = clamp(bd.extrude(bd.Rectangle(2000, 1000), 4, taper=3))
        self.assertEqual((ok, press), (True, {"molding.clamp_large_press": "warning"}))
        self.assertGreater(tons, type_side.CLAMP_LARGEST_TONS)

    def test_the_rules_recommend_two_degrees_and_a_block_s_zero_draft_is_no_wrong_pull(self) -> None:
        (draft,) = [rule for rule in type_side.RULES.rules if rule.id == "molding.draft"]
        self.assertEqual(draft.limit, 2.0)
        self.assertIn("Most situations: 2", draft.note)
        for taper, warned in ((-1, True), (-2, False)):
            flared = bd.extrude(bd.Rectangle(40, 30), 20, taper=taper)
            self.assertEqual("molding.draft" in {f.code for f in _check(flared).findings}, warned)
        # a square block along its shortest side: every wall reads zero draft, and no other pull does better
        box = _check(bd.Box(40, 30, 20))
        (zero,) = [f for f in box.findings if f.code == "zero_draft_walls"]
        # a sum of what molding.draft_min and molding.draft_zero judge face by face: a fact
        self.assertEqual(zero.severity, "info")
        self.assertNotIn("pull_better", {f.code for f in box.findings})
        self.assertIsNone(box.measurements["pull_check"]["better"])
        # a cube's principal axes are any three: the kernel's pick (its diagonals) is no pull to offer
        cube = _check(bd.Box(40, 40, 40)).measurements["pull_check"]
        self.assertEqual(([row["pull"] for row in cube["candidates"]], cube["better"]), (["x", "y"], None))

    def test_a_limit_is_compared_unrounded(self) -> None:
        (thick,) = [rule for rule in type_side.RULES.rules if rule.id == "molding.thick_section"]
        self.assertEqual(thick.limit, 1 / 0.6)
        report = {"thickness": {"nominal_mm": 18.0, "items": [
            {"location": "p/face 1", "ratio_to_nominal": 30 / 18, "feature": "wall"},
            {"location": "p/face 2", "ratio_to_nominal": 30.001 / 18, "feature": "wall"}]}}
        from cad._internal.dfm import rules

        found, _record = rules.evaluate(report, type_side.RULES, type_side.context(report, {"material": "abs"}))
        self.assertEqual([f.location for f in found if f.code == "molding.thick_section"], ["p/face 2"])

    def test_one_cause_one_finding_and_hints_in_millimetres(self) -> None:
        # A rib's sides are judged by rib_draft alone, a window's walls (formed by its slide) by the undercut rule
        # alone; the sums of the faces and features are facts (info), the rules' findings what to act on.
        plate = bd.Box(60, 40, 2, align=BOTTOM) + bd.Pos(0, 0, 2) * bd.Box(40, 1.2, 8, align=BOTTOM)
        result = _check(plate)
        ribs = result.measurements["ribs"]["items"]
        sides = set(ribs[0]["faces"][:2])
        drafted = {f.location for f in result.findings if f.code in ("molding.draft_min", "molding.draft")}
        self.assertFalse(sides & drafted)
        self.assertIn("molding.rib_draft", {f.code for f in result.findings})
        cup = _tray() - bd.Pos(0, 20, 10) * bd.Box(10, 6, 4)
        cupped = _check(cup)
        window = {face for item in cupped.measurements["undercuts"]["items"] for face in item["trapped_faces"]}
        self.assertTrue(window)
        self.assertFalse(window & {f.location for f in cupped.findings if f.code.startswith("molding.draft")})
        corner = next(f for f in cupped.findings if f.code == "molding.inside_corner_radius")
        self.assertRegex(corner.hint, r"round this internal corner to [0-9.]+ mm or more")

    def test_a_metal_is_refused(self) -> None:
        from cad._internal import manufacturing
        from cad._internal.refused import ArgumentRefused
        with self.assertRaisesRegex(ArgumentRefused, "is a resin: steel is a metal"):
            manufacturing.options("step", "molding", {"material": "steel"})

    def test_a_thin_wall_for_the_resin(self) -> None:
        thin = bd.extrude(bd.Rectangle(40, 30), 0.8, taper=3)
        warned = _check(thin, material="abs")
        self.assertIn(("warning", "molding.wall_min"), {(f.severity, f.code) for f in warned.findings})
        self.assertTrue(warned.ok)   # under ABS's recommended 1.14 mm, over half of it: made, at a cost
        self.assertNotIn("molding.wall_min", {f.code for f in _check(thin, material="nylon").findings})

    def test_a_broad_wall_far_under_the_resin_s_range_fails_and_a_thick_one_is_warned(self) -> None:
        def plate(thickness: float) -> Any:
            return bd.extrude(bd.Rectangle(40, 30), thickness, taper=3)

        checked: dict[tuple, Any] = {}

        def codes(thickness: float, material: str | None, severity: str = "error") -> set[str]:
            if (thickness, material) not in checked:
                checked[thickness, material] = _check(plate(thickness), material=material)
            return {f.code for f in checked[thickness, material].findings
                    if f.severity == severity and f.code.startswith("molding.wall")}

        # 0.4 mm: under half of ABS's 1.14 mm minimum; within PPS's range down to 0.51 less than half short; and
        # under every resin's minimum, which is all that can be said with no resin named
        self.assertEqual(codes(0.4, "abs"), {"molding.wall_too_thin"})
        self.assertEqual(codes(0.4, "pps"), set())
        self.assertEqual(codes(0.4, None), {"molding.wall_too_thin"})
        # 8 mm: over twice ABS's 3.56 mm maximum -- it sinks, voids and cools slowly, and is molded all the same
        # (a cutting board): a warning, louder than the recommendation's; inside acrylic's range
        self.assertEqual(codes(8.0, "abs"), set())
        self.assertEqual(codes(8.0, "abs", "warning"), {"molding.wall_too_thick"})
        self.assertEqual(codes(8.0, "pmma", "warning"), set())
        self.assertEqual(codes(30.0, None, "warning"), {"molding.wall_too_thick"})   # over every resin's 25.4 mm
        thin = checked[0.4, "abs"]
        floor = next(f for f in thin.findings if f.code == "molding.wall_too_thin")
        self.assertTrue(floor.source.startswith("text-to-cad, "))   # ours: half of Protolabs' recommendation, said as that
        self.assertIn("0.5 of Protolabs' recommended minimum for abs", floor.message)
        # the recommendation is left to the record beside the floor: one finding a face
        self.assertFalse({f.location for f in thin.findings if f.code == "molding.wall_min"}
                         & {f.location for f in thin.findings if f.code == "molding.wall_too_thin"})

    def test_a_feature_s_width_is_no_wall_s_thickness(self) -> None:
        # What the floor judges is a broad wall: the face and the face across it each at least ten of the wall
        # wide. Two 2 mm plates joined by a web 0.4 mm thick and 1.5 mm long (a living hinge), a ridge down one
        # whose crest is 0.3 mm wide, and a 0.3 mm deep logo cut in the other: features a molder fills from the
        # wall beside them. Each reads thin where it is thin -- the recommendation's warning -- and none fails.
        plates = bd.Pos(-20.75, 0, 0) * bd.Box(40, 40, 2, align=BOTTOM) + bd.Pos(20.75, 0, 0) * bd.Box(40, 40, 2, align=BOTTOM)
        hinge = bd.Pos(0, 0, 1.6) * bd.Box(1.5, 40, 0.4, align=BOTTOM)
        ridge = bd.Pos(20, 0, 2) * bd.Rot(90, 0, 0) * bd.extrude(bd.Trapezoid(1.2, 1.5, 73.3, align=(A.CENTER, A.MIN)), 8, both=True)
        logo = bd.Pos(-20, 0, 1.7) * bd.Box(0.5, 10, 0.3, align=BOTTOM) + bd.Pos(-19.2, 0, 1.7) * bd.Box(0.5, 10, 0.3, align=BOTTOM)
        result = _check(plates + hinge + ridge - logo, material="pp")
        items = result.measurements["thickness"]["items"]
        floor = 0.5 * type_side.WALL_RANGES["pp"][0]
        thin = [item for item in items if item["thickness_mm"] < floor]
        self.assertGreaterEqual(len(thin), 3)   # the web, the crest and the strip between the logo's strokes
        self.assertFalse([item for item in items if item["broad"] and item["broad_wall_mm"] < floor])
        self.assertTrue(result.ok, result.summary)
        self.assertNotIn("molding.wall_too_thin", {f.code for f in result.findings})
        self.assertIn(("warning", "molding.wall_min"), {(f.severity, f.code) for f in result.findings})
        # the plates themselves are broad walls, read as their own 2 mm
        self.assertEqual({item["broad_wall_mm"] for item in items if item["broad"]}, {2.0})


if __name__ == "__main__":
    unittest.main()
