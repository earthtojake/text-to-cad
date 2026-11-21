#!/usr/bin/env python3

"""A part's features (``cad.quiddity.features``): quiddity asked about one part alone, its faces tied to the part's.

Every part is built here with build123d, so the right answer is the construction's: a hole's faces are the
cylinders the kernel finds where the hole was cut, at the diameter it was cut with. What is held: a plate's
through, blind, counterbored and countersunk holes with their figures and their faces' refs; the same part's
result twice over; a part read where it stands; an assembly's parts each read alone; the gate refusing a part
whose faces are handed over in another order, a record that names a face the kernel reads otherwise, and a count
that differs; and the one explicit result where nothing was measured -- an import that fails, a part quiddity
never finishes, an answer of another schema -- with the next part still answered.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from typing import Any
from unittest import mock

import build123d as bd

from cad import quiddity
from cad.build123d import _dfm_brep as brep
from cad.engine.export.step import shape_bytes
from cad.quiddity import _features, _process

from tests.python.support.quiddity_stand_in import STAND_IN, UNIMPORTABLE, StandIn

QUIDDITY = importlib.util.find_spec("quiddity") is not None
NEEDS = "quiddity is the quiddity extra's: uv sync installs it"


def plate() -> Any:
    """An 80 x 60 x 12 mm plate, its top at z = 6, with four holes drilled from the top: through, 6 mm across,
    at (-25, 15); blind, 5 mm across and 8 mm deep, at (0, 15); through, 6.6 mm across under an 11 mm
    counterbore 6.4 mm deep, at (25, 15); through, 4.5 mm across under a 90 degree countersink 9 mm across, at
    (-25, -15)."""
    with bd.BuildPart() as made:
        bd.Box(80, 60, 12)
        with bd.Locations((-25, 15, 6)):
            bd.Hole(3)
        with bd.Locations((0, 15, 6)):
            bd.Hole(2.5, depth=8)
        with bd.Locations((25, 15, 6)):
            bd.CounterBoreHole(3.3, 5.5, 6.4)
        with bd.Locations((-25, -15, 6)):
            bd.CounterSinkHole(2.25, 4.5, counter_sink_angle=90)
    return made.part


def part_of(shape: Any, owner: str = "plate") -> brep.Part:
    return brep.Part(name=owner, owner=owner, shape=shape)


def faces_at(part: brep.Part, kind: str, x: float, y: float, radius: float | None = None) -> list[int]:
    """The ordinals of the part's faces the kernel reads as ``kind`` about the vertical line through
    ``(x, y)`` (a cylinder of ``radius``), found without quiddity."""
    found = []
    for ordinal, face in enumerate(part.faces(), start=1):
        surface = brep.surface(face)
        if surface.kind != kind or abs(surface.origin[0] - x) > 1e-6 or abs(surface.origin[1] - y) > 1e-6:
            continue
        if radius is None or abs(surface.radius - radius) < 1e-6:
            found.append(ordinal)
    return found


@unittest.skipUnless(QUIDDITY, NEEDS)
class PlateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.part = part_of(plate())
        cls.result = quiddity.features(cls.part)

    def hole(self, x: float, y: float) -> dict[str, Any]:
        (found,) = [hole for hole in self.result["holes"]
                    if abs(hole["point_mm"][0] - x) < 1e-6 and abs(hole["point_mm"][1] - y) < 1e-6]
        return found

    def test_the_result_says_what_it_is_and_accounts_for_every_face(self) -> None:
        result = self.result
        self.assertEqual((result["available"], result["version"], result["quiddity"], result["schema"]),
                         (True, 1, "0.5.5", "quiddity-rust/recognition/6"))
        self.assertEqual(result["face_count"], len(self.part.faces()))
        self.assertIsNone(result["bodies"], "one solid of one shell")
        self.assertEqual(result["unanchored_faces"], [], "every face placed by a point quiddity proves on it")
        self.assertEqual([entry["face"] for entry in result["accounting"]], list(range(1, result["face_count"] + 1)))
        self.assertLessEqual({entry["group"] for entry in result["accounting"]}, set(quiddity.GROUPS))
        # Each face a hole names is accounted to a feature, by that hole's record among them.
        by_face = {entry["face"]: entry for entry in result["accounting"]}
        for hole in result["holes"]:
            for face in hole["faces"]:
                self.assertEqual(by_face[face]["group"], "feature")
                self.assertIn(hole["id"], by_face[face]["record_ids"])
        # Every record is carried, a hole's among them with quiddity's own parameters untouched.
        records = {record["id"]: record for record in result["records"]}
        self.assertEqual({hole["id"] for hole in result["holes"]},
                         {name for name, record in records.items() if record["family"] == "holes"})
        self.assertEqual({"countersinks", "holes"} - {record["family"] for record in result["records"]}, set())
        self.assertEqual(json.loads(json.dumps(result)), result, "plain data, JSON-safe")

    def test_a_through_hole_is_its_cylinder_at_the_parts_own_ref(self) -> None:
        hole = self.hole(-25, 15)
        self.assertEqual((hole["diameter_mm"], hole["depth_mm"], hole["through"], hole["bottom"]),
                         (6.0, 12.0, True, "through"))
        self.assertEqual((hole["axis"], hole["point_mm"]), ([0.0, 0.0, -1.0], [-25.0, 15.0, 6.0]))
        self.assertEqual((hole["counterbore"], hole["spotface"], hole["outer_counterbores"], hole["countersink"],
                          hole["mouth_chamfers"]), (None, None, [], None, []))
        self.assertEqual(hole["evidence_status"], "verified")
        # Its face is the one the kernel finds there, and the caller's ref of it is the part's own.
        (wall,) = faces_at(self.part, "cylinder", -25, 15, 3.0)
        self.assertEqual(hole["faces"], [wall])
        self.assertEqual(self.part.ref("face", hole["faces"][0]), f"plate/face {wall}")

    def test_a_blind_hole_says_its_depth_and_claims_its_floor(self) -> None:
        hole = self.hole(0, 15)
        self.assertEqual((hole["diameter_mm"], hole["depth_mm"], hole["through"], hole["bottom"]),
                         (5.0, 8.0, False, "flat"))
        (wall,) = faces_at(self.part, "cylinder", 0, 15, 2.5)
        (floor,) = [ordinal for ordinal, face in enumerate(self.part.faces(), start=1)
                    if brep.surface(face).kind == "plane" and abs(face.center().Z - (6 - 8)) < 1e-6]
        self.assertEqual(hole["faces"], sorted([wall, floor]))

    def test_a_counterbored_hole_says_the_bore_and_the_counterbore_each_with_its_faces(self) -> None:
        hole = self.hole(25, 15)
        (bore,) = faces_at(self.part, "cylinder", 25, 15, 3.3)
        (counterbore,) = faces_at(self.part, "cylinder", 25, 15, 5.5)
        # The bore's depth is its own length, below the counterbore: 12 less 6.4.
        self.assertEqual((hole["diameter_mm"], hole["depth_mm"], hole["through"]), (6.6, 5.6, True))
        self.assertEqual(hole["counterbore"], {"diameter_mm": 11.0, "depth_mm": 6.4, "faces": [counterbore]})
        self.assertEqual(hole["faces"], sorted([bore, counterbore]))
        self.assertIsNone(hole["countersink"])

    def test_a_countersunk_hole_says_its_cone_which_is_no_face_of_the_bore(self) -> None:
        (bore,) = faces_at(self.part, "cylinder", -25, -15, 2.25)
        (cone,) = faces_at(self.part, "cone", -25, -15)
        (hole,) = [found for found in self.result["holes"] if found["faces"] == [bore]]
        self.assertEqual((hole["diameter_mm"], hole["through"]), (4.5, True))
        self.assertEqual(hole["countersink"], {"diameter_mm": 9.0, "angle_deg": 90.0, "depth_mm": 2.25, "faces": [cone]})
        # The bore begins under the cone, 2.25 mm down, and runs the rest of the plate.
        self.assertEqual((hole["point_mm"], hole["depth_mm"]), ([-25.0, -15.0, 3.75], 9.75))

    def test_the_same_part_is_the_same_result(self) -> None:
        again = quiddity.features(part_of(plate()))
        self.assertEqual(again, self.result)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.result, sort_keys=True))
        # The bytes handed over are a function of the shape too, whatever the process wrote before.
        self.assertEqual(shape_bytes(self.part.shape), shape_bytes(self.part.shape))

    def test_a_part_is_read_where_it_stands(self) -> None:
        moved = part_of(bd.Pos(100, 50, 20) * bd.Rot(0, 90, 0) * plate())
        result = quiddity.features(moved.shape)  # a shape alone is a part too
        self.assertTrue(result["available"], result)
        self.assertEqual([hole["faces"] for hole in result["holes"]], [hole["faces"] for hole in self.result["holes"]])
        through = next(hole for hole in result["holes"] if hole["diameter_mm"] == 6.0)
        # The plate's top, z = 6, stands at x = 106, and its hole at (-25, 15) at y = 65, z = 45, drilled along -x.
        for got, expected in zip(through["point_mm"] + through["axis"], [106.0, 65.0, 45.0, -1.0, 0.0, 0.0]):
            self.assertAlmostEqual(got, expected, places=9)


@unittest.skipUnless(QUIDDITY, NEEDS)
class TreatedHolesTest(unittest.TestCase):
    def test_a_floors_fillet_is_not_depth_and_a_mouths_chamfer_is_no_countersink(self) -> None:
        with bd.BuildPart() as made:
            bd.Box(60, 40, 20)
            with bd.Locations((-15, 0, 10)):
                bd.Hole(4, depth=12)
            floor = [edge for edge in made.edges().filter_by(bd.GeomType.CIRCLE) if abs(edge.center().Z + 2) < 1e-6]
            bd.fillet(floor, 1.5)
            with bd.Locations((15, 0, 10)):
                bd.Hole(3)
        # A 0.5 mm x 45 degree break of the through hole's mouth.
        shape = made.part - bd.Pos(15, 0, 9.75) * bd.Cone(3, 3.5, 0.5)
        part = part_of(shape)
        result = quiddity.features(part)
        self.assertTrue(result["available"], result)
        blind, through = sorted(result["holes"], key=lambda hole: hole["point_mm"][0])
        # The blind hole was cut 12 mm deep: its depth is its cylinder's, short of the 1.5 mm fillet, and the
        # fillet is another record's, so a reader that wants the floor's depth adds what it measures itself.
        self.assertEqual((blind["diameter_mm"], blind["depth_mm"], blind["through"], blind["bottom"]),
                         (8.0, 10.5, False, "flat"))
        self.assertEqual(blind["faces"], faces_at(part, "cylinder", -15, 0, 4.0))
        (cone,) = faces_at(part, "cone", 15, 0)
        self.assertEqual((through["diameter_mm"], through["through"], through["countersink"]), (6.0, True, None))
        self.assertEqual(through["mouth_chamfers"], [{"diameter_mm": 6.0, "size_mm": 0.5, "depth_mm": 0.5,
                                                      "angle_deg": 45.0, "faces": [cone]}])
        # The cone is the hole's in the accounting, and no face of its record.
        self.assertNotIn(cone, through["faces"])
        self.assertEqual(result["accounting"][cone - 1]["record_ids"], [through["id"]])


@unittest.skipUnless(QUIDDITY, NEEDS)
class AssemblyTest(unittest.TestCase):
    def test_each_part_of_an_assembly_is_recognised_alone(self) -> None:
        base = plate()
        base.label = "base"
        lid = bd.Pos(0, 0, 20) * (bd.Box(80, 60, 4) - bd.Pos(10, 0, 0) * bd.Cylinder(4, 4))
        lid.label = "lid"
        second = bd.Pos(0, 0, 40) * lid
        second.label = "lid2"
        document = brep.parts_of(bd.Compound(children=[base, lid, second], label="box"))
        # The two lids stand alike, so they are one part, counted twice.
        self.assertEqual([(part.owner, part.occurrences) for part in document.parts], [("base", 1), ("lid", 2)])
        results = quiddity.features_of(document.parts)
        self.assertEqual([result["available"] for result in results], [True, True])
        for part, result in zip(document.parts, results):
            # Its own faces alone, never the file's: an assembly as one file would count them all.
            self.assertEqual(result["face_count"], len(part.faces()))
            self.assertIsNone(result["bodies"])
        self.assertEqual(len(results[0]["holes"]), 4)
        (hole,) = results[1]["holes"]
        (wall,) = [ordinal for ordinal, face in enumerate(document.parts[1].faces(), start=1)
                   if brep.surface(face).kind == "cylinder"]
        self.assertEqual((hole["diameter_mm"], hole["through"], hole["faces"]), (8.0, True, [wall]))
        self.assertEqual(document.parts[1].ref("face", wall), f"lid/face {wall}")
        self.assertAlmostEqual(hole["point_mm"][0], 10.0)

    def test_a_part_of_two_solids_says_its_bodies_by_ordinal(self) -> None:
        two = part_of(bd.Compound([plate(), bd.Pos(200, 0, 0) * plate()]))
        result = quiddity.features(two)
        self.assertTrue(result["available"], result)
        each = len(two.faces()) // 2
        self.assertEqual(result["bodies"], {"solids": 2, "void_shells": 0,
                                            "solid_faces": [list(range(1, each + 1)), list(range(each + 1, 2 * each + 1))]})
        self.assertEqual(len(result["holes"]), 8)

    def test_a_part_with_no_face_has_no_features_and_says_so(self) -> None:
        result = quiddity.features(bd.Compound([]))
        self.assertEqual((result["available"], result["reason"]), (False, "no_faces"))
        with self.assertRaisesRegex(TypeError, "a part is a build123d shape, not str"):
            quiddity.features("plate.step")


@unittest.skipUnless(QUIDDITY, NEEDS)
class GateTest(unittest.TestCase):
    """What quiddity said of the plate, checked against faces that are not the plate's in that order."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.part = part_of(plate())
        with _process.Recogniser() as ask:
            cls.answer = ask(shape_bytes(cls.part.shape))

    def mapped(self, document: Any = None, anchors: Any = None, faces: Any = None) -> dict[str, Any]:
        return _features._mapped(self.answer["document"] if document is None else document,
                                 self.answer["anchors"] if anchors is None else anchors, "0.5.5",
                                 self.part.faces() if faces is None else faces, brep.surface)

    def test_the_parts_own_faces_pass(self) -> None:
        self.assertTrue(self.mapped()["available"])

    def test_faces_in_another_order_have_no_features_at_all(self) -> None:
        turned = part_of(plate())
        turned._maps()
        turned._faces = list(reversed(part_of(plate()).faces()))
        result = quiddity.features(turned)
        self.assertEqual((result["available"], result["reason"], result["quiddity"]), (False, "unverified", "0.5.5"))
        self.assertRegex(result["detail"], r"^the point quiddity proves on its face 0 lies \S+ mm off the kernel's "
                                           r"face 1: its faces are not the part's in this order$")
        self.assertEqual(set(result), {"available", "version", "quiddity", "reason", "detail"}, "never partial data")

    def test_a_count_that_differs_is_refused_before_anything_is_read(self) -> None:
        with self.assertRaisesRegex(_features._Unverified, r"^quiddity read 14 faces where the kernel holds 6$"):
            self.mapped(faces=part_of(bd.Box(1, 2, 3)).faces())

    def test_a_hole_whose_face_the_kernel_reads_otherwise_is_refused(self) -> None:
        # The points all lie on their faces, so only the kernel's reading of a hole's face can tell: the
        # through hole's record names a face of the stock, then the counterbore's cylinder.
        answer = self.answer
        through = next(index for index, record in enumerate(answer["document"]["records"])
                       if record["family"] == "holes" and record["parameters"]["diameter"] == 6.0)
        flat = next(index for index, entry in enumerate(answer["document"]["face_accounting"])
                    if entry["group"] == "body")
        step = next(record["parameters"]["cbore"]["faces"][0] for record in answer["document"]["records"]
                    if record["family"] == "holes" and record["parameters"]["cbore"])
        for face, said in ((flat, r"^holes/\d+: face \d+ is a plane the kernel finds not square to its axis$"),
                           (step, r"^holes/\d+: face \d+ is a cylinder \S+ mm off its axis to the kernel$")):
            with self.subTest(face=face):
                document = copy.deepcopy(answer["document"])
                document["records"][through]["faces"] = [face]
                with self.assertRaisesRegex(_features._Unverified, said):
                    self.mapped(document=document)
        # A diameter quiddity would report that the cylinder does not have.
        document = copy.deepcopy(answer["document"])
        document["records"][through]["parameters"]["diameter"] = 6.5
        with self.assertRaisesRegex(_features._Unverified, r"is a cylinder of diameter 6 mm to the kernel, none of its own$"):
            self.mapped(document=document)

    def test_an_answer_this_was_not_written_for_is_refused_by_name(self) -> None:
        document = {**self.answer["document"], "schema_version": "quiddity-rust/recognition/7"}
        with self.assertRaisesRegex(_features._UnknownSchema, r"answered 'quiddity-rust/recognition/7', and this reads"):
            self.mapped(document=document)
        document = copy.deepcopy(self.answer["document"])
        document["face_accounting"][0] = {"group": "guessed"}
        with self.assertRaisesRegex(_features._Unverified, r"^face 1 is accounted 'guessed', which is none of feature"):
            self.mapped(document=document)
        document = copy.deepcopy(self.answer["document"])
        document["records"][0]["faces"] = [14]
        with self.assertRaisesRegex(_features._Unverified, r"names quiddity's face 14, and it read faces 0 to 13$"):
            self.mapped(document=document)


class AbsenceTest(StandIn):
    def test_a_part_has_one_explicit_result_where_quiddity_does_not_import(self) -> None:
        self.stand_in(UNIMPORTABLE)
        results = quiddity.features_of([plate(), bd.Box(1, 2, 3)])
        for result in results:
            self.assertEqual(set(result), {"available", "version", "quiddity", "reason", "detail"})
            self.assertEqual((result["available"], result["version"], result["quiddity"], result["reason"]),
                             (False, 1, None, "not_installed"))
            self.assertIn("ImportError: no wheel was built for this machine", result["detail"])

    def test_a_part_quiddity_never_finishes_is_timed_out_and_the_next_is_still_read(self) -> None:
        self.stand_in(STAND_IN.replace('bytes(step).split()[0]', 'b"hang" if b"CONICAL_SURFACE" in step else b"ok"'))
        results = quiddity.features_of([plate(), bd.Box(1, 2, 3)], timeout_s=0.5)
        self.assertEqual([(result["available"], result["reason"]) for result in results],
                         [(False, "timed_out"), (False, "unknown_schema")])
        self.assertEqual(results[1]["detail"], "quiddity 0.0.0 answered 'stand-in', and this reads "
                                               "'quiddity-rust/recognition/6'")


class WhereItRunsTest(unittest.TestCase):
    @unittest.skipUnless(QUIDDITY, NEEDS)
    def test_a_process_that_lacks_quiddity_runs_it_in_the_environment_it_is_given(self) -> None:
        asked: list[str] = []

        def provide(told: Any) -> str:
            asked.append("asked")
            return sys.executable

        real = importlib.util.find_spec
        with mock.patch("importlib.util.find_spec",
                        lambda name, *rest: None if name == "quiddity" else real(name, *rest)), \
                mock.patch.object(_process, "published", return_value=True), \
                mock.patch.object(_process, "PROVIDE", provide):
            results = quiddity.features_of([plate(), bd.Box(1, 2, 3)])
        self.assertEqual([result["available"] for result in results], [True, True])
        self.assertEqual(asked, ["asked"], "once for them all")

    def test_importing_the_namespace_loads_neither_quiddity_nor_the_kernel(self) -> None:
        code = ("import json, sys\nimport cad.quiddity\nfrom cad.quiddity import _features, _frames, _process\n"
                "print(json.dumps(sorted(name for name in sys.modules if name.partition('.')[0] in "
                "('quiddity', 'OCP', 'build123d', 'numpy'))))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1]), [])


if __name__ == "__main__":
    unittest.main()
