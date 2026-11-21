#!/usr/bin/env python3

"""The CNC check's holes as quiddity recognises them (``cad.build123d._dfm_cnc_recognised``), on tiny parts built
here, so each expected figure is the construction's: a hole quiddity reads carries the figures this library
measures, in their documented meanings; a blind bore and a shallow recess whose floors are no face of the hole's
own are blind, where the detector's ray took them for through; what quiddity does not claim is still the
detector's -- a drafted wall, a sealed bore, a channel it calls a hole and is none; two stretches of one drilled
hole are one hole, and no face is two holes'; a part quiddity is not available for keeps the detector's holes, the
report as it was but for the note that says so; and one recogniser is asked once for a document's every part.
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


@unittest.skipUnless(QUIDDITY, NEEDS)
class RecognisedHolesTest(unittest.TestCase):
    def test_a_hole_quiddity_reads_carries_the_figures_this_library_measures(self) -> None:
        # through the engine's checks process, as a check of a file runs
        report = _check(_plate(), material="aluminum").measurements
        measured, holes = report["holes"], _holes(report)
        self.assertEqual({hole["recognised_by"] for hole in holes.values()}, {"quiddity"})
        self.assertEqual(measured["recognition"], {
            "library": "quiddity", "version": _dfm_cnc_recognised.QUIDDITY, "holes": {"quiddity": 4, "cad": 0},
            "parts": {"quiddity": 1, "cad": 0}, "fallbacks": [], "declined": [], "disagreements": [],
            "repeatable": True})
        drilled, bored, sunk, broken = holes[6.8], holes[6.6], holes[4.5], holes[4.0]
        # the drilled hole: its point's angle is its cone's, its opening the end quiddity's axis comes in from
        self.assertEqual((drilled["depth_mm"], drilled["through"], drilled["bottom"], drilled["opening"]),
                         (15.0, False, "drill_point", [0.0, 0.0, 1.0]))
        self.assertAlmostEqual(drilled["point_angle_deg"], 118.0, places=6)
        self.assertEqual((drilled["standard_drill"], drilled["tap_candidate"], drilled["drilled"], drilled["floor_tool"]),
                         ("6.8 mm", "M8x1.25", True, None))
        self.assertEqual((drilled["aligned"], drilled["reachable"], drilled["inclination_deg"]), (True, True, 0.0))
        self.assertRegex(drilled["location"], r"^plate/face \d+$")
        self.assertEqual(len(drilled["faces"]), 2, "its wall and its point")
        # a depth is the drilled length below a counterbore or a seat: the bore's own, as quiddity's is
        self.assertEqual((bored["through"], bored["depth_mm"], bored["overall_depth_mm"]), (True, 34.0, 40.0))
        self.assertEqual(bored["counterbores"], [{"diameter_mm": 11.0, "depth_mm": 6.0,
                                                  "depth_to_diameter": round(6.0 / 11.0, 9)}])
        self.assertEqual((sunk["depth_mm"], [(s["diameter_mm"], s["angle_deg"]) for s in sunk["countersinks"]]),
                         (37.75, [(9.0, 90.0)]))
        # a mouth's small chamfer, which quiddity keeps apart from a seat, is a countersink here: its cone's
        # largest diameter and included angle
        self.assertEqual((broken["depth_mm"], [(s["diameter_mm"], s["angle_deg"]) for s in broken["countersinks"]]),
                         (39.5, [(5.0, 90.0)]))
        self.assertEqual(len(broken["faces"]), 2, "its wall and its chamfer")

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
        # each said, with both readings
        self.assertEqual(read["holes"]["recognition"]["disagreements"], [
            {"location": holes[diameter]["location"], "field": "through", "quiddity": False, "cad": True}
            for diameter in (16.0, 40.0)])
        # a ball nose closes its hole and is no flat floor: quiddity's word for it is flat, a plane's here
        nosed = bd.Box(60, 40, 20) - (bd.Pos(0, 0, 11) * bd.Cylinder(4, 9, align=DOWN) + bd.Pos(0, 0, 2) * bd.Sphere(4))
        (hole,) = _measure(_part(nosed))["holes"]["items"]
        self.assertEqual((hole["through"], hole["bottom"], hole["floor_tool"]), (False, "other", None))

    def test_what_quiddity_does_not_claim_is_still_the_detector_s(self) -> None:
        block = bd.Box(60, 40, 20)
        # an 8 mm land 5 long under a wall drafted 2 degrees: quiddity's record is the land alone
        drafted = block - (bd.Pos(0, 0, -10) * bd.Cylinder(4, 5, align=(A.CENTER, A.CENTER, A.MIN))
                           + bd.Pos(0, 0, -5) * bd.Cone(4, 4 + 15 * math.tan(math.radians(2)), 15,
                                                       align=(A.CENTER, A.CENTER, A.MIN)))
        read = _measure(_part(drafted))
        (hole,), (alone,) = read["holes"]["items"], _measure(_part(drafted), recognise=False)["holes"]["items"]
        self.assertEqual((hole["recognised_by"], hole["diameter_mm"], hole["depth_mm"], len(hole["faces"])),
                         ("quiddity", 8.0, 5.0, 2))
        self.assertEqual([round(sink["angle_deg"], 6) for sink in hole["countersinks"]], [4.0], "the drafted wall")
        self.assertEqual({key: value for key, value in hole.items() if key != "recognised_by"},
                         {key: value for key, value in alone.items() if key != "recognised_by"})
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": hole["location"], "field": "countersinks", "quiddity": 0, "cad": 1}])
        # a bore sealed inside the block is an interior void to quiddity, which has no hole there
        read = _measure(_part(block - bd.Cylinder(4, 10)))
        (hole,) = read["holes"]["items"]
        self.assertEqual((hole["recognised_by"], hole["bottom"], hole["depth_mm"]), ("cad", "closed", 10.0))
        self.assertEqual(read["holes"]["recognition"]["holes"], {"quiddity": 0, "cad": 1})
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": hole["location"], "field": "hole", "quiddity": False, "cad": True}])
        # a 2.6 mm channel along the top, its axis 0.6 mm under it, is open along its side: a hole to quiddity,
        # none here (it sweeps 235 degrees), so its record is declined and no family reads it as one
        channel = block - bd.Pos(0, 0, 9.4) * bd.Rot(0, 90, 0) * bd.Cylinder(1.3, 80)
        read, alone = _measure(_part(channel)), _measure(_part(channel), recognise=False)
        self.assertEqual(read["holes"]["items"], [])
        (declined,) = read["holes"]["recognition"]["declined"]
        self.assertEqual((declined["reason"], declined["record"]), ("open", "holes/0"))
        self.assertRegex(declined["location"], r"^part/face \d+$")
        read["holes"].pop("recognition")
        self.assertEqual(read, alone)

    def test_two_stretches_of_one_drilled_hole_are_one_hole_and_no_face_is_two_holes(self) -> None:
        # 6 mm drilled across a 60 mm block, through an 8 mm hole down its middle
        crossed = bd.Box(60, 40, 20) - bd.Cylinder(4, 40) - bd.Rot(0, 90, 0) * bd.Cylinder(3, 80)
        read, alone = _measure(_part(crossed)), _measure(_part(crossed), recognise=False)
        self.assertEqual(sorted(hole["diameter_mm"] for hole in alone["holes"]["items"]), [6.0, 6.0, 8.0])
        holes = _holes(read)
        self.assertEqual((read["holes"]["count"], sorted(holes)), (2, [6.0, 8.0]))
        self.assertEqual((holes[6.0]["depth_mm"], holes[6.0]["through"], len(holes[6.0]["faces"])), (60.0, True, 2))
        faces = [face for hole in read["holes"]["items"] for face in hole["faces"]]
        self.assertEqual(len(faces), len(set(faces)))
        self.assertEqual(sorted(faces), sorted(face for hole in alone["holes"]["items"] for face in hole["faces"]))
        self.assertEqual(read["holes"]["recognition"]["disagreements"],
                         [{"location": holes[6.0]["location"], "field": "holes", "quiddity": 1, "cad": 2}])
        # the families that read a hole's faces read the same faces
        for family in ("access", "walls", "gaps", "pockets", "sharp_edges", "setups"):
            self.assertEqual(read[family], alone[family], family)

    def test_two_records_on_one_of_the_detector_s_holes_are_two_holes_and_its_other_faces_the_first_s(self) -> None:
        """The counterbored hole's record handed over as two, its bore and its counterbore each a hole: what
        the detector makes one hole of is two, the step's plane, which neither record names, the first's."""
        real = quiddity.features_of

        def split(parts: Any, **_given: Any) -> Any:
            (found,) = real(parts)
            (whole,) = [hole for hole in found["holes"] if hole["counterbore"]]
            step = whole["counterbore"]
            bore = {**whole, "counterbore": None, "faces": [face for face in whole["faces"] if face not in step["faces"]]}
            wide = {**whole, "id": "holes/9", "counterbore": None, "diameter_mm": step["diameter_mm"],
                    "faces": list(step["faces"])}
            found["holes"] = [bore if hole is whole else hole for hole in found["holes"]] + [wide]
            return [found]

        with mock.patch.object(quiddity, "features_of", split):
            read = _measure(_plate())
        alone = _holes(_measure(_plate(), recognise=False))
        holes = _holes(read)
        self.assertEqual((read["holes"]["count"], sorted(holes)), (5, [4.0, 4.5, 6.6, 6.8, 11.0]))
        self.assertEqual((len(holes[6.6]["faces"]), len(holes[11.0]["faces"])), (2, 1), "the step's plane is the bore's")
        faces = [face for hole in read["holes"]["items"] for face in hole["faces"]]
        self.assertEqual(len(faces), len(set(faces)))
        self.assertEqual(set(holes[6.6]["faces"]) | set(holes[11.0]["faces"]), set(alone[6.6]["faces"]))
        self.assertEqual([entry for entry in read["holes"]["recognition"]["disagreements"]], [
            {"location": holes[6.6]["location"], "field": "holes", "quiddity": 2, "cad": 1},
            {"location": holes[11.0]["location"], "field": "holes", "quiddity": 2, "cad": 1}])

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


class FallbackTest(unittest.TestCase):
    """A part quiddity is not available for: its holes are the detector's, the report as it was."""

    def setUp(self) -> None:
        self.shape = _capped()
        self.alone = _measure(_capped(), recognise=False)

    def _with(self, features_of: Any) -> dict[str, Any]:
        with mock.patch.object(quiddity, "features_of", features_of):
            return _measure(self.shape)

    def test_the_holes_are_the_detector_s_and_the_report_says_why(self) -> None:
        self.assertNotIn("recognition", self.alone["holes"])
        self.assertEqual({hole["recognised_by"] for hole in self.alone["holes"]["items"]}, {"cad"})
        for reason, repeatable in (("no_wheel", True), ("unverified", True), ("refused", True),
                                   ("not_installed", False), ("timed_out", False), ("stopped", False)):
            with self.subTest(reason=reason):
                read = self._with(lambda parts, **_given: [unavailable(reason, "why, in a line") for _part in parts])
                self.assertEqual(read["holes"].pop("recognition"), {
                    "library": "quiddity", "version": None, "holes": {"quiddity": 0, "cad": 3},
                    "parts": {"quiddity": 0, "cad": 1},
                    "fallbacks": [{"part": "capped", "reason": reason, "detail": "why, in a line"}],
                    "declined": [], "disagreements": [], "repeatable": repeatable})
                self.assertEqual(read, self.alone)

    def test_a_recogniser_that_raises_or_another_release_s_answer_costs_no_hole(self) -> None:
        def raises(parts: Any, **_given: Any) -> Any:
            raise RuntimeError("no recogniser here")

        said = self._with(raises)["holes"]["recognition"]
        self.assertEqual((said["fallbacks"], said["repeatable"]),
                         ([{"part": "capped", "reason": "failed",
                            "detail": "quiddity could not be asked: RuntimeError: no recogniser here"}], True))
        # records are read as one release's, the one the extra pins: the code that measures names it
        extras = tomllib.loads(repo_path("packages", "cad", "pyproject.toml").read_text(encoding="utf-8"))
        (requirement,) = extras["project"]["optional-dependencies"]["quiddity"]
        self.assertEqual(requirement.partition(";")[0].strip(), f"quiddity=={_dfm_cnc_recognised.QUIDDITY}")
        other = {"available": True, "quiddity": "0.0.1", "holes": [], "records": []}
        read = self._with(lambda parts, **_given: [copy.deepcopy(other) for _part in parts])
        said = read["holes"].pop("recognition")
        self.assertEqual((said["version"], said["fallbacks"], said["repeatable"]),
                         ("0.0.1", [{"part": "capped", "reason": "other_release",
                                     "detail": "quiddity 0.0.1 answered, and its records are read as quiddity "
                                               f"{_dfm_cnc_recognised.QUIDDITY}'s"}], False))
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
