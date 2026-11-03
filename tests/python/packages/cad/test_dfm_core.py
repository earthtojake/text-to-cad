#!/usr/bin/env python3

"""The manufacturing checks' shared layers: rule sets and their verdicts (``cad._internal.dfm.rules``),
the options every process resolves (``cad._internal.manufacturing.options``), and exact geometry
(``cad.build123d._dfm_brep``): a document's parts and their refs, surfaces, edges, rays and samples.

Every part is built here with build123d, so the right answer is the construction's: a pocket's floor
edges are concave because the pocket was cut, a ref resolves to the face it was written for because the
engine's own resolver says so.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import build123d as bd
import numpy as np

from cad._internal import manufacturing
from cad._internal.dfm.rules import Rule, RuleSet, Source, evaluate
from cad.build123d import _dfm_brep as brep

SOURCE = Source("s", "Publisher", "Guide", "https://example.invalid/guide", "2026-11-03")


def _set(*rules: Rule, generic: bool = False) -> RuleSet:
    return RuleSet("test", "cnc", "Test", "1", rules, (SOURCE,), generic=generic)


class RulesTest(unittest.TestCase):
    def test_a_min_rule_fails_the_items_under_it_and_names_its_place_and_source(self) -> None:
        rule = Rule("cnc.corner", "pockets", "radius_mm", "min", 1.0, "mm", "internal corner radius", "s",
                    fix="radius it to at least {limit:g} mm")
        report = {"pockets": {"items": [{"radius_mm": 0.5, "location": "plate/face 7"},
                                        {"radius_mm": 2.0, "location": "plate/face 9"},
                                        {"radius_mm": None, "location": "plate/face 11"}]}}
        found, record = evaluate(report, _set(rule), {})
        self.assertEqual([(f.code, f.location, f.severity) for f in found], [("cnc.corner", "plate/face 7", "error")])
        self.assertIn("0.5 mm is under the 1 mm minimum (Publisher, Guide)", found[0].message)
        self.assertEqual(found[0].hint, "radius it to at least 1 mm")
        outcome = record["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["evaluated"], outcome["unmeasured"]), ("failed", 2, 1))
        self.assertEqual(record["failed"], ["cnc.corner"])

    def test_limits_by_context_scaled_and_conditioned(self) -> None:
        by_class = Rule("wall", "walls", "t", "min", {"metal": 0.8, "plastic": 1.5}, "mm", "wall", "s",
                        by="material_class")
        scaled = Rule("hole", "holes", "d", "min", 1.0, "mm", "hole", "s", scale_by="thickness")
        only_turning = Rule("turn", "turned", "d", "min", 5.0, "mm", "diameter", "s", when={"turning": True})
        only_blind = Rule("blind", "holes", "d", "max", 1.0, "mm", "blind hole", "s", severity="warning",
                          item_when={"kind": "blind"})
        report = {"walls": {"items": [{"t": 1.0}]}, "holes": {"items": [{"d": 1.5, "kind": "blind"}]},
                  "turned": {"items": [{"d": 1.0}]}}
        rules = _set(by_class, scaled, only_turning, only_blind)
        found, record = evaluate(report, rules, {"material_class": "plastic", "thickness": 2.0, "turning": False})
        self.assertEqual(sorted(f.code for f in found), ["blind", "hole", "wall"])
        # A rule that does not apply here is recorded as such, never dropped: no silent pass.
        turn = next(o for o in record["outcomes"] if o["rule"] == "turn")
        self.assertEqual((turn["status"], turn["reason"]), ("not_applicable", "applies only where turning is True"))
        self.assertEqual(next(f for f in found if f.code == "blind").severity, "warning")
        found, record = evaluate(report, rules, {"material_class": "metal", "thickness": 1.0, "turning": True})
        self.assertEqual(sorted(f.code for f in found), ["blind", "turn"])
        # No material: a rule by material gives no limit, and says so rather than passing.
        _, record = evaluate(report, rules, {"thickness": 1.0})
        wall = next(o for o in record["outcomes"] if o["rule"] == "wall")
        self.assertEqual(wall["status"], "not_evaluated")

    def test_a_family_not_measured_is_no_pass_and_many_failures_are_counted(self) -> None:
        rule = Rule("r", "f", "v", "max", 1.0, "mm", "v", "s")
        _, record = evaluate({"f": {"error": "boom"}}, _set(rule), {})
        self.assertEqual(record["outcomes"][0]["status"], "not_evaluated")
        found, record = evaluate({"f": {"items": [{"v": float(i + 2)} for i in range(20)]}}, _set(rule), {})
        self.assertEqual(len(found), 9)  # SHOWN_PER_RULE, then one counting the rest
        self.assertEqual(found[0].message.split(" is ")[0], "v 21 mm")  # the worst first
        self.assertEqual(len(record["outcomes"][0]["failures"]), 20)

    def test_a_rule_citing_a_source_its_set_does_not_list_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _set(Rule("r", "f", "v", "max", 1.0, "mm", "v", "elsewhere"))


class OptionsTest(unittest.TestCase):
    def test_each_option_belongs_to_its_process(self) -> None:
        resolved = manufacturing.options("step", "cnc", {"axes": 5, "tools": "6,3"})
        self.assertEqual((resolved["axes"], resolved["rules"], resolved["turning"]), (5, "generic", False))
        for process, given, said in (
                ("cnc", {"pull": "z"}, "--pull is not cnc's"),
                ("molding", {"turning": True}, "--turning is not molding's"),
                ("cnc", {"axes": 7}, "--axes is 3, 4 or 5"),
                ("cnc", {"rules": "acme"}, "--rules for cnc is one of"),
                ("sheet", {"k_factor": 0.9}, "--k-factor"),
                ("printing", {"technology": "inkjet"}, "--technology is one of"),
                ("printing", {"material": "cheese"}, "--material is one of")):
            with self.subTest(process=process, given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("step", process, given)

    def test_exact_processes_refuse_a_mesh_and_a_dxf_is_a_cut_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "check the part's STEP or xbf"):
            manufacturing.options("stl", "sheet", {})
        with self.assertRaisesRegex(ValueError, "--process sheet"):
            manufacturing.options("dxf", "cnc", {})
        with self.assertRaisesRegex(ValueError, "ranks molding's pulls"):
            manufacturing.options("step", "cnc", {}, candidates=True)
        self.assertEqual(manufacturing.options("dxf", "sheet", {"kerf": 0.2})["kerf"], 0.2)


def _pocketed() -> bd.Part:
    block = bd.Box(60, 40, 20)
    pocket = bd.fillet((bd.Pos(0, 0, 6) * bd.Box(30, 20, 8.0)).edges().filter_by(bd.Axis.Z), 2)
    part = block - pocket - bd.Pos(22, 12, 0) * bd.Cylinder(3, 40)
    part.label = "block"
    return part


class GeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory()
        path = Path(cls.folder.name) / "block.step"
        bd.export_step(_pocketed(), str(path))
        cls.document = brep.read("step", path)
        cls.part = cls.document.parts[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.folder.cleanup()

    def test_surfaces_say_which_way_the_material_lies(self) -> None:
        kinds = [brep.surface(face) for face in self.part.faces()]
        holes = [s for s in kinds if s.kind == "cylinder" and math.isclose(s.radius, 3.0)]
        corners = [s for s in kinds if s.kind == "cylinder" and math.isclose(s.radius, 2.0)]
        self.assertEqual((len(holes), len(corners)), (1, 4))
        self.assertTrue(all(s.concave for s in holes + corners))
        np.testing.assert_allclose(np.abs(holes[0].axis), [0, 0, 1], atol=1e-9)
        tops = [s for s in kinds if s.kind == "plane" and s.normal[2] > 0.99]
        self.assertEqual(len(tops), 2)  # the block's top and the pocket's floor

    def test_a_pockets_floor_edges_are_concave_and_its_fillet_joins_smooth(self) -> None:
        found = brep.edges(self.part)
        concave = [e for e in found if e.concave]
        self.assertEqual(len(concave), 8)  # four walls and four corner fillets meeting the floor
        self.assertTrue(all(math.isclose(e.angle_deg, 270.0, abs_tol=1e-6) for e in concave))
        self.assertTrue(all(math.isclose(e.midpoint[2], 2.0, abs_tol=1e-6) for e in concave))
        self.assertEqual(sum(1 for e in found if e.smooth), 8)
        convex = [e for e in found if not e.concave and not e.smooth]
        self.assertTrue(all(math.isclose(e.angle_deg, 90.0, abs_tol=1e-6) for e in convex))

    def test_rays_measure_walls_and_cross_the_material(self) -> None:
        rays = brep.Rays(self.part.shape)
        self.assertAlmostEqual(rays.thickness((25, 0, 10), (0, 0, 1)), 20.0, places=6)
        self.assertAlmostEqual(rays.thickness((0, 0, 2), (0, 0, 1)), 12.0, places=6)
        spans = rays.intervals((0, 0, -50), (0, 0, 1))
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0][1] - spans[0][0], 12.0, places=6)
        self.assertEqual(brep.inside(self.part.shape, [(0, 0, 0), (0, 0, 5), (22, 12, 0)]), [True, False, False])

    def test_samples_cover_each_face_on_its_surface(self) -> None:
        for face in self.part.faces():
            found = brep.samples(face, 64)
            self.assertGreaterEqual(len(found), 32)
            self.assertAlmostEqual(sum(s.area for s in found) / face.area, 1.0, delta=0.01)
            self.assertTrue(all(face.distance_to(bd.Vector(*s.point)) < 1e-6 for s in found[:5]))

    def test_a_triangulation_names_every_face(self) -> None:
        vertices, triangles, owners = brep.triangles(self.part.shape, 0.05)
        self.assertEqual(set(owners.tolist()), set(range(1, len(self.part.faces()) + 1)))
        self.assertEqual(vertices.shape[1], 3)


class RefsTest(unittest.TestCase):
    """Every ref a finding gives resolves, by the engine's own resolver, to the face it was written of."""

    def _assembly(self) -> bd.Compound:
        plate = bd.Box(40, 30, 5)
        plate.label = "plate"
        pins = []
        for index in range(3):
            pin = bd.Pos(-12 + 12 * index, 0, 10) * bd.Cylinder(2, 10)
            pin.label = "pin"
            pins.append(pin)
        nub = bd.Pos(0, 20, 0) * bd.Box(4, 4, 4)
        nub.label = "nub"
        group = bd.Compound(children=[nub])
        group.label = "group"
        kit = bd.Compound(children=[plate, *pins, bd.Pos(5, 0, 0) * group])
        kit.label = "kit"
        return kit

    def test_refs_resolve_to_their_faces(self) -> None:
        from cad.engine import refs
        from cad.engine.document import Loaded

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "kit.step"
            bd.export_step(self._assembly(), str(path))
            document = brep.read("step", path)
            structure = Loaded(path).structure()
            self.assertEqual(sorted(part.owner for part in document.parts),
                             ["kit/pin.1", "kit/pin.2", "kit/pin.3", "nub", "plate"])
            for part in document.parts:
                for ordinal, face in enumerate(part.faces(), start=1):
                    ref = part.ref("face", ordinal)
                    hits = refs.resolve_structure(structure, ref, path)
                    self.assertEqual(len(hits), 1, ref)
                    self.assertEqual((hits[0].kind, hits[0].ordinal), ("face", ordinal), ref)
            nub = next(part for part in document.parts if part.name == "nub")
            self.assertAlmostEqual(nub.shape.center().X, 5.0, places=6)  # placed where it stands
            self.assertAlmostEqual(nub.shape.center().Y, 20.0, places=6)

    def test_a_live_shape_reads_as_its_document_would(self) -> None:
        document = brep.parts_of(self._assembly())
        self.assertEqual(sorted(part.owner for part in document.parts),
                         ["kit/pin.1", "kit/pin.2", "kit/pin.3", "nub", "plate"])
        nub = next(part for part in document.parts if part.name == "nub")
        self.assertAlmostEqual(nub.shape.center().X, 5.0, places=6)


if __name__ == "__main__":
    unittest.main()
