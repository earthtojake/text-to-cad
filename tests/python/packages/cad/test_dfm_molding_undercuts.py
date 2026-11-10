#!/usr/bin/env python3

"""Injection molding's undercuts on exact geometry, on tiny parts built here: what the pull traps, the slide,
lifter or collapsing core that releases each feature (a side hole is one slide along its axis, a sealed void
is released by nothing), and a face or a family the kernel fails on counted, never passed. The check's other
families are ``test_dfm_molding_walls``, ``test_dfm_molding_features`` and ``test_dfm_molding_verdicts``; the
planted-defect corpus is ``test_dfm_molding_corpus``."""

from __future__ import annotations

import math
import unittest
from typing import Any

import build123d as bd
import numpy as np

from cad._internal.dfm import molding as type_side
from cad.build123d import _dfm_brep
from tests.python.support.dfm_molding import BOTTOM, _check, _face, _tray


class UndercutTest(unittest.TestCase):
    def test_a_side_hole_needs_one_slide_along_its_axis(self) -> None:
        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"], item["side_actions"]), ("external", "side_action", ["+x"]))
        self.assertEqual(_dfm_brep.surface(_face(result, part, item["location"])).kind, "cylinder")
        # the pin travels the whole wall (2 mm at 3 deg: 2.003 across, and the bore's own lean), not as far as the
        # deepest sampled point happens to lie
        self.assertGreaterEqual(item["stroke_mm"], 2.0)
        self.assertLess(item["stroke_mm"], 2.5)
        self.assertAlmostEqual(item["height_mm"], 4.0, delta=0.3)
        (said,) = [f for f in result.findings if f.code == "molding.undercut"]
        self.assertIn("released by a side action along +x", said.message)
        self.assertNotIn("deep against the pull", said.message)   # a bump-off's figure, no hole's

    def test_holes_through_both_walls_are_two_slides_and_three_slots_in_one_wall_are_one(self) -> None:
        # A ray along +x from the -x wall's hole leaves through the hole opposite: the slide is the one whose way
        # out is the shorter. And a part's side actions are its distinct slide directions, not its features.
        through = _check(_tray() - bd.Pos(0, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 200)).measurements["undercuts"]
        self.assertEqual(sorted(tuple(item["side_actions"]) for item in through["items"]), [("+x",), ("-x",)])
        self.assertEqual((through["side_action_count"], sorted(through["side_action_directions"])), (2, ["+x", "-x"]))
        slotted = _tray()
        for x in (-15, 0, 15):
            slotted -= bd.Pos(x, 20, 10) * bd.Box(4, 8, 4)
        result = _check(slotted)
        slots = result.measurements["undercuts"]
        self.assertEqual([item["side_actions"] for item in slots["items"]], [["+y"]] * 3)
        self.assertEqual((slots["undercut_count"], slots["side_action_count"], slots["side_action_directions"]),
                         (3, 1, ["+y"]))
        (summed,) = [f for f in result.findings if f.code == "undercut_candidates"]
        self.assertIn("3 feature(s): 1 side action(s) (+y)", summed.message)

    def test_a_slot_takes_one_slide_along_its_own_run(self) -> None:
        # One slot off-centre in a long box: its own run (square to its faces' normals) is tried first, exactly,
        # so one slide along +y frees it, whatever the eight directions round the parting plane lean against.
        box = bd.extrude(bd.Rectangle(120, 80), 30, taper=-2) - \
            bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(116, 76), 28, taper=-2)
        result = _check(box - bd.Pos(-50, 40, 18) * bd.Box(1.5, 10, 8))
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["side_actions"], item["angled"]), ("side_action", ["+y"], False))
        self.assertGreaterEqual(item["stroke_mm"], 2.07)   # the wall, across
        self.assertLess(item["stroke_mm"], 2.5)

    def test_a_hole_off_the_grid_takes_a_slide_along_its_own_axis(self) -> None:
        # 20 deg off x in the parting plane: a plain slide along the bore. 25 deg out of the plane: an angled one.
        for turn, angled in ((bd.Rot(0, 0, 20), False), (bd.Rot(0, 25, 0), True)):
            part = _tray() - bd.Pos(30, 0, 10) * turn * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 14)
            result = _check(part)
            (item,) = result.measurements["undercuts"]["items"]
            self.assertEqual((item["release"], item["kind"], item["angled"]), ("side_action", "external", angled), turn)
            (way,) = item["side_actions"]
            axis = (turn * bd.Pos(1, 0, 0)).position
            self.assertAlmostEqual(float(np.array([float(v) for v in way.split(",")]) @ np.array([axis.X, axis.Y, axis.Z])),
                                   1.0, places=3)
            self.assertTrue(result.ok)

    def test_a_cavity_wider_below_its_mouth_is_an_inside_undercut_and_the_pull_check_agrees(self) -> None:
        # A box tapered the wrong way: its inside walls are trapped behind its mouth. No slide reaches them from
        # beside the part (the rays that leave it tilt out through the mouth: no side action's), and the report's
        # two readings of the pull are one.
        part = bd.extrude(bd.Rectangle(60, 40), 30, taper=2) - bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(56, 36), 28, taper=2)
        result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"], item["side_actions"]), ("internal", "collapsible_core", []))
        chosen = result.measurements["pull_check"]["chosen"]
        self.assertEqual((chosen["undercut_count"], chosen["side_action_count"], chosen["lifter_count"],
                          chosen["unreleasable_count"]), (1, 0, 1, 0))
        self.assertEqual(chosen["undercut_candidate_area_mm2"], result.measurements["undercuts"]["candidate_area_mm2"])

    def test_a_rib_s_end_a_hair_off_a_drafted_wall_is_a_crevice_not_an_undercut(self) -> None:
        # A square-ended rib run 0.1 mm into walls drafted 2 deg: buried at the floor, a hair off the wall above
        # it, the gap opening along the pull. A sample on the rib's end, stepped off it to cast its rays, landed in
        # the wall's material, read trapped both ways and freed by nothing: the part failed on two samples.
        box = bd.extrude(bd.Rectangle(60, 40), 30, taper=-2) - bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(56, 36), 28, taper=-2)
        result = _check(box + bd.Pos(0, 0, 5) * bd.Box(1.2, 36.2, 6))
        undercuts = result.measurements["undercuts"]
        self.assertEqual((undercuts["undercut_count"], undercuts["candidate_area_mm2"]), (0, 0.0))
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(undercuts["crevice_count"], 2)   # the rib's two ends
        # no undercut, but steel between two faces a hair apart is a knife edge: a warning, at their refs
        (said,) = [f for f in result.findings if f.code == "crevices"]
        self.assertEqual(said.severity, "warning")
        self.assertEqual(len(undercuts["crevices"][0]["faces"]), 2)
        self.assertEqual(set(said.refs), {face for crevice in undercuts["crevices"] for face in crevice["faces"]})

    def test_a_feature_nothing_releases_is_read_again_on_denser_points_before_it_fails_the_part(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        void = bd.Box(20, 20, 20) - bd.Sphere(5)
        # every feature made to rest on "few" points: the void is sampled again, and still nothing releases it
        with mock.patch.object(_dfm_molding, "_CONFIRM_UNDER", 10 ** 6):
            read = _check(void).measurements["undercuts"]
            self.assertEqual((read["unreleasable_count"], read["unconfirmed_count"]), (1, 0))
            self.assertGreaterEqual(read["items"][0]["confirmed_points"], _dfm_molding._CONFIRM_POINTS)
            # ... and where the denser points are not trapped it was a sample's reading: no feature, no error
            empty = (np.zeros((0, 3)), np.zeros((0, 3)))
            with mock.patch.object(_dfm_molding, "_denser", return_value=empty):
                result = _check(void)
        read = result.measurements["undercuts"]
        self.assertEqual((read["undercut_count"], read["unconfirmed_count"], read["candidate_area_mm2"]), (0, 1, 0.0))
        self.assertNotIn("molding.undercut_unreleasable", {f.code for f in result.findings})
        # ... dropped, but never silently: counted, and said
        (said,) = [f for f in result.findings if f.code == "undercuts_unconfirmed"]
        self.assertEqual(said.severity, "info")
        self.assertIn("1 place(s)", said.message)

    def test_an_external_groove_needs_two_slides(self) -> None:
        part = bd.Cylinder(15, 20) - (bd.Cylinder(16, 4) - bd.Cylinder(12, 4))
        (item,) = _check(part).measurements["undercuts"]["items"]
        # A round groove: any two opposite slides in the parting plane release it, +-x or +-y alike.
        self.assertEqual(item["release"], "side_action")
        self.assertIn(sorted(item["side_actions"]), (["+x", "-x"], ["+y", "-y"]))
        self.assertLess(item["stroke_mm"], 10.0, "each half travels its own half, not the whole diameter")

    def test_a_groove_s_depth_is_said_and_a_shallow_re_entrant_lip_is_bumped_off(self) -> None:
        # a 3 mm round groove in a rim, its centre inset: 0.5 mm in, its opening is 0.042 mm narrower each side
        # than the groove (3 - sqrt(9 - 0.25)), a lip the slides scrape over (a bump-off, a warning); 1 mm in,
        # 0.17 mm -- over BUMP_OFF_MM, nothing frees it (an error). Each says how deep it is against the pull.
        disc = bd.Cylinder(35, 16, align=BOTTOM) - bd.Cylinder(5, 40)
        turned = bd.Rot(0, 90, 0) * bd.Pos(2, -1, 0)
        for turn, pull, inset in ((bd.Rot(0, 0, 0), "z", 1.0), (turned, "x", 0.5)):
            result = _check(turn * (disc - bd.Pos(0, 0, 8) * bd.Torus(35 - inset, 3)), pull=pull)
            (item,) = result.measurements["undercuts"]["items"]
            self.assertAlmostEqual(item["depth_mm"], 3.0 + inset, delta=0.15, msg=(pull, inset))
            codes = {(f.severity, f.code) for f in result.findings if f.code.startswith("molding.undercut")}
            finding = next(f for f in result.findings if f.code.startswith("molding.undercut"))
            self.assertIn("mm deep against the pull", finding.message)
            # every ref it names is a whole one (`cad step inspect` resolves it): its faces', never a bare word
            self.assertTrue(set(item["trapped_faces"]) <= set(finding.refs))
            self.assertEqual(set(finding.refs), {*item["faces"], *item["trapped_faces"], *item["blocked_by"]})
            if inset == 0.5:
                self.assertEqual(codes, {("warning", "molding.undercut_bump_off")}, pull)
                # external by its geometry: slides reach the groove from beside the part
                self.assertEqual((item["release"], item["kind"]), ("bump_off", "external"))
                self.assertLessEqual(item["interference_mm"], type_side.BUMP_OFF_MM)
                self.assertIn("resin's flexibility", finding.message)
            else:
                self.assertEqual(codes, {("error", "molding.undercut_unreleasable")}, pull)
                self.assertGreater(item["slide_depth_mm"], type_side.BUMP_OFF_MM)
                self.assertLess(item["slide_depth_mm"], 0.18)

    def test_inside_undercuts_take_a_lifter_or_a_collapsing_core(self) -> None:
        inner = 20.0 + 15.0 * math.tan(math.radians(3.0)) - 2.0 / math.cos(math.radians(3.0))
        snap = _tray() + bd.Pos(0, inner - 0.6, 15) * bd.Box(10, 2, 1.5)
        (item,) = _check(snap).measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"]), ("internal", "lifter"))
        self.assertAlmostEqual(item["stroke_mm"], 1.5, delta=0.2, msg="the lip's reach into the cavity")
        groove = bd.Cylinder(15, 20) - bd.Cylinder(6, 20) - bd.Cylinder(8, 3)
        (item,) = _check(groove).measurements["undercuts"]["items"]
        self.assertEqual(item["release"], "collapsible_core")

    def test_an_undercut_whose_release_was_not_searched_is_counted_never_passed(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        with mock.patch.object(_dfm_molding, "_RELEASE_SECONDS", 0.0):   # the release search's time, spent
            result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["unreleasable_area_mm2"]), ("unknown", None))
        outcome = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.undercut_unreleasable")
        self.assertEqual((outcome["status"], outcome["unmeasured"]), ("not_evaluated", 1))
        self.assertIn(("warning", "undercuts_unsearched"), {(f.severity, f.code) for f in result.findings})
        # nothing trustworthy was judged of what is trapped: the check is not checked, never OK
        self.assertEqual((result.status, result.reason), ("not_checked", "rule_partly_judged"))
        # A window beside the hole, and rays that run out after the larger of the two: the search judged most
        # of what is trapped, so the verdict is of that. The hole is warned as the undercut it is and counted --
        # not passed, and not the whole check's undoing -- and the window keeps its slide, less the stroke the
        # budget ran out before.
        with mock.patch.object(_dfm_molding, "_RELEASE_RAYS", 1):
            result = _check(part - bd.Pos(0, 20, 10) * bd.Box(16, 12, 8))
        window, hole = result.measurements["undercuts"]["items"]
        self.assertEqual((window["release"], window["side_actions"], window["stroke_mm"], window["figures_measured"]),
                         ("side_action", ["+y"], None, False))
        self.assertEqual((hole["release"], hole["not_applicable"]), ("unknown", ["unreleasable_area_mm2"]))
        self.assertEqual(result.status, "ok")
        (said,) = [f for f in result.findings if f.code == "undercuts_unsearched"]
        self.assertIn("1 feature(s) not searched", said.message)
        self.assertEqual((said.severity, said.refs), ("warning", [hole["location"]]))
        self.assertIn("--pull", said.hint)
        self.assertEqual(sum(f.code == "molding.undercut" for f in result.findings), 2)   # each warned as an undercut
        outcome = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.undercut_unreleasable")
        self.assertEqual((outcome["status"], outcome["unmeasured"]), ("passed", 0))

    def test_a_sealed_void_is_released_by_nothing(self) -> None:
        result = _check(bd.Box(20, 20, 20) - bd.Sphere(5))
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["kind"]), ("none", "internal"))
        self.assertIn(("error", "molding.undercut_unreleasable"), {(f.severity, f.code) for f in result.findings})

    def test_a_ray_the_kernel_cannot_intersect_is_counted_not_fatal(self) -> None:
        """OCCT's exact intersector raised ``Standard_Failure`` on one face of a real part (a degenerate patch),
        which lost the whole undercuts family and then the summary (a ``KeyError``): the crossing is now not
        found, counted and said, and every family measured."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        made: list[Any] = []

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.fails = Real(face, tolerance), not made
                made.append(self)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.fails:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing):
            result = _check(part)
        self.assertEqual(result.measurements["partial_sections"], [])
        (said,) = [f for f in result.findings if f.code == "rays_unintersected"]
        self.assertRegex(said.location, r"face \d+$")  # at the face, not at a family
        self.assertIn("undercut candidates", result.summary)

    def test_a_face_the_kernel_cannot_intersect_is_not_measured_in_every_family_its_rays_cross(self) -> None:
        """Thickness, ribs and corners cast rays too: a face the kernel fails on is named in each family whose
        rays it cost, and the family's rules say it was not measured there -- never a plain pass."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        part = _tray()
        part.label = "tray"
        floor = min(part.faces(), key=lambda face: face.center().Z)  # the tray's underside, under every wall ray

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.fails = Real(face, tolerance), face.IsPartner(floor.wrapped)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.fails:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing):
            result = _check(part)
        ref = next(f.location for f in result.findings if f.code == "rays_unintersected")
        self.assertIn(ref, result.measurements["thickness"]["unmeasured_faces"])
        outcomes = {o["rule"]: o for o in result.measurements["rules"]["outcomes"]}
        self.assertIn(ref, outcomes["molding.wall_min"]["unmeasured_faces"])
        self.assertIn("not measured at 1 face(s)", outcomes["molding.wall_min"]["reason"])
        self.assertGreaterEqual(outcomes["molding.wall_min"]["unmeasured"], 1)

    def test_a_face_lost_only_while_the_pulls_are_ranked_is_said_once_for_the_part(self) -> None:
        """A bar drafted along x, molded along z, has a doubtful pull, so the part's own pulls are ranked
        (``pull_check``, which reads what x traps): a face the kernel fails on there alone is the part's one
        ``rays_unintersected``, naming it, and the pulls' too."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        from cad.build123d import _dfm_molding

        bar = bd.extrude(bd.Plane.YZ * bd.Rectangle(40, 20), amount=60, taper=5)
        bar.label = "bar"
        side = max(bar.faces(), key=lambda face: face.center().Y)
        ranking = {"now": False}

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.side = Real(face, tolerance), face.IsPartner(side.wrapped)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.side and ranking["now"]:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        check = _dfm_molding._pull_check

        def ranked(*args: Any, **kwargs: Any) -> Any:
            ranking["now"] = True
            try:
                return check(*args, **kwargs)
            finally:
                ranking["now"] = False

        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing), \
                mock.patch.object(_dfm_molding, "_pull_check", ranked):
            result = _check(bar)
        said = [f for f in result.findings if f.code == "rays_unintersected"]
        self.assertEqual(len(said), 1, [f.message for f in said])
        self.assertIn(" face(s) of bar (", said[0].message)
        self.assertEqual(result.measurements["pull_check"]["unmeasured_faces"], [said[0].location])

    def test_an_assembly_part_s_face_lost_while_its_pull_is_chosen_is_named_by_its_undercuts(self) -> None:
        """An assembly's part reads what its pull traps once, while its pull is chosen (``_own_pull``), and its
        report keeps that reading: a face the kernel fails on there is named by the undercuts family
        (``unmeasured_faces``), as one part's is, not by the part's ``rays_unintersected`` alone."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        from cad.build123d import _dfm_molding

        tray = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        tray.label = "tray"
        plate = bd.Pos(80, 0, 0) * bd.extrude(bd.Rectangle(20, 20), 3, taper=3)
        plate.label = "plate"
        searching = {"now": False}

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner = Real(face, tolerance)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if searching["now"]:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        search = _dfm_molding._undercut_part

        def failing(*args: Any, **kwargs: Any) -> Any:
            searching["now"] = True
            try:
                return search(*args, **kwargs)
            finally:
                searching["now"] = False

        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing), \
                mock.patch.object(_dfm_molding, "_undercut_part", failing):
            result = _check(bd.Compound(label="pair", children=[tray, plate]))
        self.assertEqual([part["own"] for part in result.measurements["pulls"]], [False, False])
        said = [ref for f in result.findings if f.code == "rays_unintersected" for ref in f.refs or [f.location]]
        self.assertTrue(said)
        self.assertTrue(set(said) <= set(result.measurements["undercuts"].get("unmeasured_faces") or ()),
                        (said, result.measurements["undercuts"].get("unmeasured_faces")))

    def test_a_family_not_measured_fails_the_check_and_never_raises(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        with mock.patch.object(_dfm_molding, "_undercut_part", side_effect=RuntimeError("no rays")):
            result = _check(_tray())
        self.assertFalse(result.ok)
        failed = [f for f in result.findings if f.code == "measurement_failed"]
        self.assertEqual([f.location for f in failed], ["undercuts"])
        self.assertIn("undercut candidates - mm2", result.summary)

    def test_a_drafted_tray_pulls_clean(self) -> None:
        result = _check(_tray())
        undercuts = result.measurements["undercuts"]
        self.assertEqual((undercuts["candidate_area_mm2"], undercuts["undercut_count"]), (0.0, 0))
        self.assertTrue(result.ok, [f for f in result.findings if f.severity == "error"])


if __name__ == "__main__":
    unittest.main()
