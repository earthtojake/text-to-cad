#!/usr/bin/env python3

"""The CNC check's holes with quiddity's reading of what closes them (``cad.build123d._dfm_cnc_recognised``), on
tiny parts built here, so each expected figure is the construction's. A hole whose record is taken carries the
detector's figures; a blind bore and a shallow recess whose floors are no face of the hole's own are blind, where
the detector's ray read them through, and nothing else of them changes. A record the kernel contradicts changes
nothing: a hole crossed by another stays two holes, a narrower bore is never a counterbore, and a record that
says closed where a ray leaves the part, through where the ray meets the hole's own floor, a point where there is
no cone, is declined -- each with the detector's report exactly as it was and the disagreement said. What
quiddity does not claim is the detector's still; a part quiddity is not available for keeps the detector's
holes, the report as it was but for the note that says so, repeatable only where the reason is the part's own;
and one recogniser is asked once for a document's every part.
"""

from __future__ import annotations

import copy
import importlib.util
import math
import tomllib
import unittest
from typing import Any
from unittest import mock

import build123d as bd

from cad import quiddity
from cad._internal import manufacturing
from cad._internal.dfm import kept
from cad.build123d import _dfm_brep as brep
from cad.build123d import _dfm_cnc, _dfm_cnc_recognised, cnc
from cad.quiddity import _features, _process
from cad.quiddity._features import unavailable
from tests.python.support.dfm_cnc import A, _check, _part
from tests.python.support.paths import repo_path

QUIDDITY = importlib.util.find_spec("quiddity") is not None
NEEDS = "quiddity is the quiddity extra's: uv sync installs it"
DOWN = (A.CENTER, A.CENTER, A.MAX)


def _measure(shape: Any, recognise: bool = True) -> dict[str, Any]:
    """The cnc report of a shape, measured here: with quiddity asked, or by the detector alone."""
    options = kept.Measuring("cnc", manufacturing.options("step", "cnc", {}))
    return _dfm_cnc.measure(brep.parts_of(shape), options, False, recognise=recognise)


def _holes(report: dict[str, Any]) -> dict[float, dict[str, Any]]:
    return {hole["diameter_mm"]: hole for hole in report["holes"]["items"]}


def _as_it_was(report: dict[str, Any]) -> dict[str, Any]:
    """A report as the detector alone gives it: no ``recognition``, every hole its own."""
    report = copy.deepcopy(report)
    report["holes"].pop("recognition", None)
    for hole in report["holes"]["items"]:
        hole["recognised_by"] = "cad"
    return report


def _block() -> Any:
    return bd.Box(60, 40, 40)  # its top at z = 20


def _plate() -> Any:
    """A 100 x 30 x 40 block, its top at z = 20, drilled from the top: 6.8 mm, 15 deep to a 118 degree point, at
    x = -35; 6.6 mm through under an 11 mm counterbore 6 deep, at -20; 4.5 mm through under a 90 degree
    countersink 9 mm across, at -5; and 4 mm through, its mouth broken 0.5 x 45 degrees, at 10."""
    tip = 3.4 / math.tan(math.radians(59.0))
    part = bd.Box(100, 30, 40)
    part -= bd.Pos(-35, 0, 21) * bd.Cylinder(3.4, 16, align=DOWN) + bd.Pos(-35, 0, 5) * bd.Cone(0.0, 3.4, tip, align=DOWN)
    part -= bd.Pos(-20, 0, 0) * bd.Cylinder(3.3, 60) + bd.Pos(-20, 0, 20.5) * bd.Cylinder(5.5, 6.5, align=DOWN)
    part -= bd.Pos(-5, 0, 0) * bd.Cylinder(2.25, 60) + bd.Pos(-5, 0, 20.25) * bd.Cone(2.25, 4.75, 2.5, align=DOWN)
    part -= bd.Pos(10, 0, 0) * bd.Cylinder(2.0, 60) + bd.Pos(10, 0, 20.25) * bd.Cone(2.0, 2.75, 0.75, align=DOWN)
    return _part(part, "plate")


def _capped() -> Any:
    """A 120 x 60 x 20 block, its top at z = 10: a 16 mm bore 12 deep whose floor's edge is rounded 1 mm, at
    x = -35; and a 40 mm recess 3 deep at x = 25, with a 5 mm hole through its floor 12 mm off its axis."""
    part = bd.Box(120, 60, 20) - bd.Pos(-35, 0, 10) * bd.Cylinder(8, 12, align=DOWN)
    part = bd.fillet([edge for edge in part.edges() if edge.geom_type == bd.GeomType.CIRCLE
                      and abs(edge.center().Z + 2) < 1e-6], 1.0)
    part -= bd.Pos(25, 0, 10) * bd.Cylinder(20, 3, align=DOWN)
    part -= bd.Pos(25, 12, 0) * bd.Cylinder(2.5, 40)
    return _part(part, "capped")


def _saying(change: Any) -> Any:
    """quiddity's own answer with each hole's record changed by ``change(record)`` (which may answer several
    records, or none, in its place): a record it could give, and the kernel does not bear out."""
    real = quiddity.features_of

    def features_of(parts: Any, **given: Any) -> Any:
        found = real(parts, **given)
        for result in found:
            holes = []
            for record in result["holes"]:
                said = change(copy.deepcopy(record))
                holes.extend(said if isinstance(said, list) else [said])
            result["holes"] = holes
        return found

    return mock.patch.object(quiddity, "features_of", features_of)


@unittest.skipUnless(QUIDDITY, NEEDS)
class RecognisedHolesTest(unittest.TestCase):
    def test_a_hole_whose_record_is_taken_carries_the_figures_the_detector_measures(self) -> None:
        # through the engine's checks process, as a check of a file runs
        report = _check(_plate(), material="aluminum").measurements
        measured, holes = report["holes"], _holes(report)
        self.assertEqual({hole["recognised_by"] for hole in holes.values()}, {"quiddity"})
        self.assertEqual(measured["recognition"], {
            "library": "quiddity", "version": _dfm_cnc_recognised.QUIDDITY, "holes": {"quiddity": 4, "cad": 0},
            "parts": {"quiddity": 1, "cad": 0}, "fallbacks": [], "declined": [], "disagreements": [],
            "repeatable": True})
        drilled, bored, sunk, broken = holes[6.8], holes[6.6], holes[4.5], holes[4.0]
        self.assertEqual((drilled["depth_mm"], drilled["through"], drilled["bottom"], drilled["opening"]),
                         (15.0, False, "drill_point", [0.0, 0.0, 1.0]))
        self.assertAlmostEqual(drilled["point_angle_deg"], 118.0, places=6)
        self.assertEqual((drilled["standard_drill"], drilled["tap_candidate"], drilled["drilled"], drilled["floor_tool"]),
                         ("6.8 mm", "M8x1.25", True, None))
        self.assertEqual((drilled["aligned"], drilled["reachable"], drilled["inclination_deg"]), (True, True, 0.0))
        self.assertEqual((bored["through"], bored["depth_mm"], bored["overall_depth_mm"]), (True, 34.0, 40.0))
        self.assertEqual(bored["counterbores"], [{"diameter_mm": 11.0, "depth_mm": 6.0,
                                                  "depth_to_diameter": round(6.0 / 11.0, 9)}])
        self.assertEqual((sunk["depth_mm"], [(s["diameter_mm"], s["angle_deg"]) for s in sunk["countersinks"]]),
                         (37.75, [(9.0, 90.0)]))
        # a mouth's small chamfer, which quiddity keeps apart from a seat, is a countersink here, as it was
        self.assertEqual((broken["depth_mm"], [(s["diameter_mm"], s["angle_deg"]) for s in broken["countersinks"]]),
                         (39.5, [(5.0, 90.0)]))
        # every item is the detector's own, to the last field
        self.assertEqual(_as_it_was(_measure(_plate())), _measure(_plate(), recognise=False))

    def test_a_blind_bore_and_a_shallow_recess_are_blind_where_the_detector_s_ray_read_through(self) -> None:
        shape = _capped()
        alone, read = _holes(_measure(shape, recognise=False)), _measure(shape)
        holes = _holes(read)
        for diameter, depth in ((16.0, 11.0), (40.0, 3.0)):  # the bore's wall ends where its floor's round begins
            with self.subTest(diameter=diameter):
                self.assertEqual((alone[diameter]["through"], alone[diameter]["bottom"], alone[diameter]["opening"]),
                                 (True, "through", None), "a floor that is no face of the hole's own")
                hole = holes[diameter]
                self.assertEqual((hole["through"], hole["bottom"], hole["opening"], hole["depth_mm"]),
                                 (False, "flat", [0.0, 0.0, 1.0], depth))
                self.assertEqual((hole["drilled"], hole["floor_tool"]), (False, "end mill or flat-bottom drill"))
                changed = {key for key in hole if hole[key] != alone[diameter].get(key)}
                self.assertEqual(changed, {"through", "bottom", "opening", "drilled", "floor_tool", "recognised_by"})
        self.assertEqual({key: holes[5.0][key] for key in holes[5.0] if key != "recognised_by"},
                         {key: alone[5.0][key] for key in alone[5.0] if key != "recognised_by"})
        # each said, with both readings, and no other family reads the part otherwise
        self.assertEqual(read["holes"]["recognition"]["disagreements"], [
            {"location": holes[diameter]["location"], "field": "through", "quiddity": False, "cad": True}
            for diameter in (16.0, 40.0)])
        was = _measure(shape, recognise=False)
        self.assertEqual({name: read[name] for name in read if name != "holes"},
                         {name: was[name] for name in was if name != "holes"})
        # a ball nose closes its hole and is no flat floor: quiddity's word for it is flat, a plane's here
        nosed = _block() - (bd.Pos(0, 0, 21) * bd.Cylinder(4, 9, align=DOWN) + bd.Pos(0, 0, 12) * bd.Sphere(4))
        (hole,) = _measure(_part(nosed))["holes"]["items"]
        self.assertEqual((hole["through"], hole["bottom"], hole["floor_tool"], hole["recognised_by"]),
                         (False, "other", None, "quiddity"))

    def test_what_quiddity_does_not_claim_is_still_the_detector_s(self) -> None:
        block = bd.Box(60, 40, 20)
        # an 8 mm land 5 long under a wall drafted 2 degrees: quiddity's record is the land alone
        drafted = block - (bd.Pos(0, 0, -10) * bd.Cylinder(4, 5, align=(A.CENTER, A.CENTER, A.MIN))
                           + bd.Pos(0, 0, -5) * bd.Cone(4, 4 + 15 * math.tan(math.radians(2)), 15,
                                                       align=(A.CENTER, A.CENTER, A.MIN)))
        read, alone = _measure(_part(drafted)), _measure(_part(drafted), recognise=False)
        (hole,) = read["holes"]["items"]
        self.assertEqual((hole["recognised_by"], hole["diameter_mm"], hole["depth_mm"], len(hole["faces"])),
                         ("quiddity", 8.0, 5.0, 2))
        self.assertEqual([round(sink["angle_deg"], 6) for sink in hole["countersinks"]], [4.0], "the drafted wall")
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": hole["location"], "field": "countersinks", "quiddity": 0, "cad": 1}])
        self.assertEqual(_as_it_was(read), alone)
        # a bore sealed inside the block is an interior void to quiddity, which has no hole there
        read, alone = _measure(_part(block - bd.Cylinder(4, 10))), _measure(_part(block - bd.Cylinder(4, 10)), False)
        (hole,) = read["holes"]["items"]
        self.assertEqual((hole["recognised_by"], hole["bottom"], hole["depth_mm"]), ("cad", "closed", 10.0))
        self.assertEqual(read["holes"]["recognition"]["holes"], {"quiddity": 0, "cad": 1})
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": hole["location"], "field": "hole", "quiddity": False, "cad": True}])
        self.assertEqual(_as_it_was(read), alone)
        # a 2.6 mm channel along the top, its axis 0.6 mm under it, is open along its side: a hole to quiddity,
        # none here (it sweeps 235 degrees), so its record is declined and no family reads it as one
        channel = block - bd.Pos(0, 0, 9.4) * bd.Rot(0, 90, 0) * bd.Cylinder(1.3, 80)
        read, alone = _measure(_part(channel)), _measure(_part(channel), recognise=False)
        self.assertEqual(read["holes"]["items"], [])
        (declined,) = read["holes"]["recognition"]["declined"]
        self.assertEqual((declined["reason"], declined["record"]), ("open", "holes/0"))
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": declined["location"], "field": "hole", "quiddity": True, "cad": False}])
        self.assertEqual(_as_it_was(read), alone)

    def test_a_hole_another_hole_crosses_stays_two_holes_each_as_deep_as_a_drill_goes(self) -> None:
        """6 mm along a 260 mm block, crossed in the middle by 10 mm: the detector reads the two stretches, 125.5
        mm each (21 diameters, which a drill reaches); quiddity's one record is both, 260 mm (43, which none
        does). A check that passed fails for no change to the part unless the record is declined."""
        crossed = _part(bd.Box(260, 40, 20) - bd.Cylinder(5, 40) - bd.Rot(0, 90, 0) * bd.Cylinder(3, 300), "crossed")
        read, alone = _measure(crossed), _measure(crossed, recognise=False)
        self.assertEqual(sorted((hole["diameter_mm"], hole["depth_mm"]) for hole in alone["holes"]["items"])[:2],
                         [(6.0, 125.5), (6.0, 125.5)])
        self.assertEqual(_as_it_was(read), alone)
        said = read["holes"]["recognition"]
        first = alone["holes"]["items"][0]["location"]
        (declined,) = said["declined"]
        self.assertEqual((declined["reason"], said["holes"]), ("spans", {"quiddity": 1, "cad": 2}))
        self.assertEqual([entry for entry in said["disagreements"] if entry["field"] == "holes"],
                         [{"location": declined["location"], "field": "holes", "quiddity": 1, "cad": 2}])
        self.assertIn(first, {hole["location"] for hole in read["holes"]["items"]})
        result = cnc(crossed, material="aluminum")
        self.assertEqual((result.status, [f.code for f in result.findings if f.code == "cnc.hole_depth_limit"]),
                         ("ok", []))

    def test_a_narrower_bore_is_never_a_counterbore_and_a_hole_is_a_record_s_whole_or_not_at_all(self) -> None:
        """A stepped blind bore, 10 mm for 15 mm then 6 mm for 10 mm: one hole here, 6 mm under a 10 mm
        counterbore. A record that takes the 10 mm step for the bore, with or without another for the 6 mm, is
        declined, and the hole is the detector's: its 6 mm bore's diameter, depth and drill are still judged."""
        stepped = _part(_block() - bd.Pos(0, 0, 20) * bd.Cylinder(5, 15, align=DOWN)
                        - bd.Pos(0, 0, 5) * bd.Cylinder(3, 10, align=DOWN))
        alone = _measure(stepped, recognise=False)
        (hole,) = alone["holes"]["items"]
        self.assertEqual((hole["diameter_mm"], [bore["diameter_mm"] for bore in hole["counterbores"]]), (6.0, [10.0]))

        def wide(record: dict[str, Any]) -> dict[str, Any]:
            step = record["counterbore"]
            return {**record, "counterbore": None, "diameter_mm": step["diameter_mm"], "faces": list(step["faces"])}

        def both(record: dict[str, Any]) -> list[dict[str, Any]]:
            step = record["counterbore"]
            narrow = {**record, "id": "holes/9", "counterbore": None, "evidence_status": "unproved",
                      "faces": [face for face in record["faces"] if face not in step["faces"]]}
            return [wide(record), narrow]

        for change, reasons, differs in ((wide, ["other_bore"], ("diameter_mm", 10.0, 6.0)),
                                         (both, ["shared", "unproved"], ("holes", 2, 1))):
            with self.subTest(change=change.__name__), _saying(change):
                read = _measure(stepped)
                self.assertEqual(_as_it_was(read), alone)
                said = read["holes"]["recognition"]
                self.assertEqual(([entry["reason"] for entry in said["declined"]], said["holes"]),
                                 (reasons, {"quiddity": 0, "cad": 1}))
                self.assertEqual(said["disagreements"], [{"location": hole["location"], "field": differs[0],
                                                          "quiddity": differs[1], "cad": differs[2]}])

    def test_what_a_record_says_closes_a_hole_is_taken_only_where_the_rays_do_not_contradict_it(self) -> None:
        tip = 3.0 / math.tan(math.radians(59.0))
        through = _part(_block() - bd.Cylinder(3, 60))
        blind = _part(_block() - bd.Pos(0, 0, 20) * bd.Cylinder(4, 10, align=DOWN))
        drilled = _part(_block() - (bd.Pos(0, 0, 21) * bd.Cylinder(3, 13, align=DOWN)
                                    + bd.Pos(0, 0, 8) * bd.Cone(0.0, 3, tip, align=DOWN)))
        # 4 mm, 10 deep, into a slot 20 high across the block: open, the slot's far wall 20 mm past its end
        slotted = _part(_block() - bd.Pos(0, 0, 20) * bd.Cylinder(2, 10, align=DOWN) - bd.Box(60, 20, 20))
        capped = _capped()

        def says(**fields: Any) -> Any:
            return lambda record: {**record, **fields} if record["diameter_mm"] != 5.0 else record

        cases = [
            # a ray into the hole leaves the part: that end is open, whatever the record says
            ("through, said flat", through, says(bottom="flat"), ("through", False, True)),
            ("through, said a point", through, says(bottom="drill_point"), ("through", False, True)),
            # what the ray meets is no floor of this hole's: the far wall of what it opens into
            ("open into a slot, said flat", slotted, says(bottom="flat"), ("through", False, True)),
            # the ray meets the hole's own floor
            ("blind, said through", blind, says(bottom="through"), ("through", True, False)),
            ("blind, said closed from the other end", blind, says(axis=[0.0, 0.0, 1.0]),
             ("opening", [0.0, 0.0, -1.0], [0.0, 0.0, 1.0])),
            # the floor is of another kind than the record says
            ("flat floor, said a point", blind, says(bottom="drill_point"), ("bottom", "drill_point", "flat")),
            ("a drill's point, said flat", drilled, says(bottom="flat"), ("bottom", "flat", "drill_point")),
            ("a floor that is not the hole's own, said a point", capped, says(bottom="drill_point"),
             ("bottom", "drill_point", "through")),
            ("the same, said closed from the end it opens at", capped, says(axis=[0.0, 0.0, 1.0]),
             ("through", False, True)),
        ]
        for name, shape, change, (field, theirs, ours) in cases:
            with self.subTest(name), _saying(change):
                read, alone = _measure(shape), _measure(shape, recognise=False)
                self.assertEqual(_as_it_was(read), alone, "the detector's reading stands, exactly")
                said = read["holes"]["recognition"]
                self.assertEqual({entry["reason"] for entry in said["declined"]}, {"contradicted"})
                self.assertTrue(said["disagreements"])
                for entry in said["disagreements"]:
                    self.assertEqual((entry["field"], entry["quiddity"], entry["cad"]), (field, theirs, ours))
                self.assertEqual({hole["recognised_by"] for hole in read["holes"]["items"]
                                  if hole["diameter_mm"] != 5.0}, {"cad"})
        # ``unknown`` is no reading: the record is taken, and the detector's reading stands
        with _saying(says(bottom="unknown")):
            read = _measure(capped)
        self.assertEqual({hole["recognised_by"] for hole in read["holes"]["items"]}, {"quiddity"})
        self.assertEqual((read["holes"]["recognition"]["declined"], read["holes"]["recognition"]["disagreements"]),
                         ([], []))
        self.assertEqual(_as_it_was(read), _measure(capped, recognise=False))

    def test_one_recogniser_is_asked_once_for_every_part_a_document_holds(self) -> None:
        drilled = bd.Box(40, 30, 12) - bd.Pos(12, 0, 0) * bd.Cylinder(2, 12)
        parts = [_part(bd.Pos(0, 0, 0) * drilled, "a"), _part(bd.Pos(60, 0, 0) * bd.Rot(90, 0, 0) * drilled, "b"),
                 _part(bd.Pos(120, 0, 0) * (bd.Box(30, 30, 10) - bd.Cylinder(3, 10)), "c")]
        with mock.patch.object(quiddity, "features_of", side_effect=quiddity.features_of) as asked:
            read = _measure(bd.Compound(children=parts, label="kit"))
        (call,) = asked.call_args_list
        self.assertEqual([part.name for part in call.args[0]], ["a", "c"], "b is a's geometry, turned")
        said = read["holes"]["recognition"]
        self.assertEqual((said["holes"], said["parts"]), ({"quiddity": 3, "cad": 0}, {"quiddity": 3, "cad": 0}))
        self.assertEqual(sorted(hole["location"].split("/")[0] for hole in read["holes"]["items"]), ["a", "b", "c"])

    def test_a_part_of_more_faces_than_are_handed_over_is_the_detector_s_on_every_computer(self) -> None:
        started: list[Any] = []
        child = _process._Child

        def counted(*given: Any) -> Any:
            started.append(given)
            return child(*given)

        with mock.patch.object(_features, "FACES", 11), mock.patch.object(_process, "_Child", counted):
            read = _measure(_capped())
        self.assertEqual(started, [], "no recogniser's process is started for it")
        self.assertEqual(_as_it_was(read), _measure(_capped(), recognise=False))
        said = read["holes"]["recognition"]
        self.assertEqual((said["fallbacks"], said["repeatable"], said["version"]),
                         ([{"part": "capped", "reason": "too_many_faces",
                            "detail": "the part holds 12 faces, over the 11 of a part handed to quiddity"}], True, None))


class FallbackTest(unittest.TestCase):
    """A part quiddity is not available for: its holes are the detector's, the report as it was."""

    def setUp(self) -> None:
        self.shape = _capped()
        self.alone = _measure(_capped(), recognise=False)

    def _with(self, features_of: Any) -> dict[str, Any]:
        with mock.patch.object(quiddity, "features_of", features_of):
            return _measure(self.shape)

    def test_the_holes_are_the_detector_s_and_the_report_says_why_and_whether_it_would_say_so_again(self) -> None:
        self.assertNotIn("recognition", self.alone["holes"])
        self.assertEqual({hole["recognised_by"] for hole in self.alone["holes"]["items"]}, {"cad"})
        own = ("no_wheel", "no_faces", "too_many_faces", "unwritten", "refused", "failed", "unknown_schema", "unverified")
        self.assertEqual(set(_dfm_cnc_recognised.REPEATABLE), set(own))
        self.assertLess(set(own), set(_features.REASONS))
        for reason in _features.REASONS:
            with self.subTest(reason=reason):
                read = self._with(lambda parts, **_given: [unavailable(reason, "why, in a line") for _part in parts])
                self.assertEqual(read["holes"].pop("recognition"), {
                    "library": "quiddity", "version": None, "holes": {"quiddity": 0, "cad": 3},
                    "parts": {"quiddity": 0, "cad": 1},
                    "fallbacks": [{"part": "capped", "reason": reason, "detail": "why, in a line"}],
                    "declined": [], "disagreements": [], "repeatable": reason in own})
                self.assertEqual(read, self.alone)

    def test_what_the_machinery_or_another_release_answers_costs_no_hole_and_is_not_said_repeatable(self) -> None:
        def raises(parts: Any, **_given: Any) -> Any:
            raise RuntimeError("can't start new thread")

        said = self._with(raises)["holes"]["recognition"]
        self.assertEqual((said["fallbacks"], said["repeatable"]),
                         ([{"part": "capped", "reason": "unanswered",
                            "detail": "quiddity could not be asked: RuntimeError: can't start new thread"}], False))
        # records are read as one release's, the one the extra pins: the code that measures names it
        extras = tomllib.loads(repo_path("packages", "cad", "pyproject.toml").read_text(encoding="utf-8"))
        (requirement,) = extras["project"]["optional-dependencies"]["quiddity"]
        self.assertEqual(requirement.partition(";")[0].strip(), f"quiddity=={_dfm_cnc_recognised.QUIDDITY}")
        # whatever another release answers -- features, or why it has none -- is that environment's
        answers = ({"available": True, "quiddity": "0.0.1", "holes": [], "records": []},
                   unavailable("unverified", "its faces are not the part's", "0.0.1"),
                   unavailable("failed", "a panic", "0.0.1"))
        for answer in answers:
            with self.subTest(answer=answer.get("reason")):
                read = self._with(lambda parts, **_given: [copy.deepcopy(answer) for _part in parts])
                said = read["holes"].pop("recognition")
                self.assertEqual((said["version"], [entry["reason"] for entry in said["fallbacks"]], said["repeatable"]),
                                 ("0.0.1", ["other_release"], False))
                self.assertRegex(said["fallbacks"][0]["detail"], r"^quiddity 0\.0\.1 answered.*, and its records are "
                                                                 r"read as quiddity 0\.5\.5's$")
                self.assertEqual(read, self.alone)
        # records that do not read against the part: every hole the detector's, and not said repeatable
        broken = {"available": True, "quiddity": _dfm_cnc_recognised.QUIDDITY, "records": [], "holes": [{"id": "holes/0"}]}
        read = self._with(lambda parts, **_given: [copy.deepcopy(broken) for _part in parts])
        said = read["holes"].pop("recognition")
        self.assertEqual(([entry["reason"] for entry in said["fallbacks"]], said["repeatable"], said["parts"]),
                         (["misread"], False, {"quiddity": 0, "cad": 1}))
        self.assertEqual(read, self.alone)

    def test_a_check_passes_as_it_did(self) -> None:
        with mock.patch.object(quiddity, "features_of",
                               lambda parts, **_given: [unavailable("not_installed", "no environment") for _part in parts]):
            result = cnc(_plate(), material="aluminum")
        self.assertEqual((result.status, result.ok), ("ok", True))
        self.assertEqual(result.measurements["holes"]["recognition"]["parts"], {"quiddity": 0, "cad": 1})

    @unittest.skipUnless(QUIDDITY, NEEDS)
    def test_one_part_s_fallback_leaves_the_others_read(self) -> None:
        parts = [_part(bd.Box(40, 30, 12) - bd.Cylinder(2, 12), "a"),
                 _part(bd.Pos(60, 0, 0) * (bd.Box(30, 30, 10) - bd.Cylinder(3, 10)), "b")]
        real = quiddity.features_of

        def second_stopped(given: Any, **_given: Any) -> Any:
            first, _second = list(given)
            return [*real([first]), unavailable("stopped", "its process ended", "0.5.5")]

        with mock.patch.object(quiddity, "features_of", second_stopped):
            read = _measure(bd.Compound(children=parts, label="kit"))
        self.assertEqual({hole["location"].split("/")[0]: hole["recognised_by"] for hole in read["holes"]["items"]},
                         {"a": "quiddity", "b": "cad"})
        said = read["holes"]["recognition"]
        self.assertEqual((said["holes"], said["parts"], said["repeatable"]),
                         ({"quiddity": 1, "cad": 1}, {"quiddity": 1, "cad": 1}, False))
        self.assertEqual(said["fallbacks"], [{"part": "b", "reason": "stopped", "detail": "its process ended"}])


if __name__ == "__main__":
    unittest.main()
