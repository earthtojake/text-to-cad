#!/usr/bin/env python3

"""The manufacturing checks' shared layers: the rules and their verdicts (``cad._internal.dfm.rules``),
the options every process resolves (``cad._internal.manufacturing.options``), and exact geometry
(``cad.build123d._dfm_brep``): a document's parts and their refs, surfaces, edges, rays and samples.

Every part is built here with build123d, so the right answer is the construction's: a pocket's floor
edges are concave because the pocket was cut, a ref resolves to the face it was written for because the
engine's own resolver says so.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import build123d as bd
import numpy as np

from cad._internal import manufacturing
from cad._internal.dfm.rules import Rule, RuleSet, Source, evaluate
from cad.build123d import _dfm_brep as brep

SOURCE = Source("s", "Publisher", "Guide", "https://example.invalid/guide", "2026-11-03")


def _set(*rules: Rule) -> RuleSet:
    return RuleSet("cnc", "Test", "1", rules, (SOURCE,))


class RulesTest(unittest.TestCase):
    def test_a_min_rule_fails_the_items_under_it_and_names_its_place_and_source(self) -> None:
        rule = Rule("cnc.corner", "pockets", "radius_mm", "min", 1.0, "mm", "internal corner radius", "s",
                    fix="radius it to at least {limit:g} mm")
        report = {"pockets": {"items": [{"radius_mm": 0.5, "location": "plate/face 7"},
                                        {"radius_mm": 2.0, "location": "plate/face 9"},
                                        {"radius_mm": None, "location": "plate/face 11"}]}}
        found, record = evaluate(report, _set(rule), {})
        self.assertEqual([(f.code, f.location, f.severity) for f in found], [("cnc.corner", "plate/face 7", "error")])
        self.assertIn("0.5 mm is under the 1 mm minimum (general practice; source: Publisher, Guide)", found[0].message)
        self.assertEqual(found[0].hint, "radius it to at least 1 mm")
        outcome = record["outcomes"][0]
        self.assertEqual((outcome["status"], outcome["evaluated"], outcome["unmeasured"]), ("failed", 2, 1))
        self.assertEqual(record["failed"], ["cnc.corner"])

    def test_an_angle_is_at_its_limit_to_a_millionth_of_a_degree(self) -> None:
        # a 2 deg wall against a pull typed to nine digits reads 1.99999999
        rule = Rule("draft", "draft", "draft_deg", "min", 2.0, "deg", "wall draft", "s")
        items = [{"draft_deg": 2.0 - 1e-8, "location": "a"}, {"draft_deg": 1.99999, "location": "b"}]
        found, _record = evaluate({"draft": {"items": items}}, _set(rule), {})
        self.assertEqual([f.location for f in found], ["b"])

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
        items = [{"v": float(i + 2), "location": f"p/face {i}"} for i in range(20)]
        found, record = evaluate({"f": {"items": items}}, _set(rule), {})
        self.assertEqual(len(found), 9)  # SHOWN_PER_RULE refs, then one counting the rest
        self.assertEqual(found[0].message.split(" is ")[0], "v 21 mm")  # the worst first
        self.assertEqual(len(record["outcomes"][0]["failures"]), 20)

    def test_failures_at_one_ref_are_one_finding_and_an_implied_warning_is_left_to_the_record(self) -> None:
        error = Rule("e", "f", "v", "min", 1.0, "mm", "v", "s")
        warning = Rule("w", "f", "v", "min", 2.0, "mm", "v", "s", severity="warning")
        report = {"f": {"items": [{"v": 0.5, "location": "p/face 1"}, {"v": 0.2, "location": "p/face 1"},
                                  {"v": 1.5, "location": "p/face 2"}]}}
        found, record = evaluate(report, _set(warning, error), {})
        # the two failures of the error at face 1 are one finding, the worst first, counting the other
        errors = [f for f in found if f.code == "e"]
        self.assertEqual([(f.location, f.message.split(" is ")[0]) for f in errors], [("p/face 1", "v 0.2 mm")])
        self.assertIn("(and 1 more at this ref)", errors[0].message)
        # the warning on face 1 is implied by the error there; face 2 fails the warning alone
        self.assertEqual([f.location for f in found if f.code == "w"], ["p/face 2"])
        # the record keeps every failure of both
        by_rule = {o["rule"]: o for o in record["outcomes"]}
        self.assertEqual(len(by_rule["e"]["failures"]), 2)
        self.assertEqual(len(by_rule["w"]["failures"]), 3)

    def test_of_two_recommendations_one_figure_fails_the_one_further_off_is_said(self) -> None:
        # a 0 deg wall fails draft_min's 0.5 and draft's 2: one cause, one finding; the record keeps both
        low = Rule("low", "f", "v", "min", 0.5, "deg", "v", "s", severity="warning")
        high = Rule("high", "f", "v", "min", 2.0, "deg", "v", "s", severity="warning")
        report = {"f": {"items": [{"v": 0.0, "location": "p/face 1"}, {"v": 1.0, "location": "p/face 2"}]}}
        found, record = evaluate(report, _set(high, low), {})
        self.assertEqual(sorted((f.code, f.location) for f in found), [("high", "p/face 2"), ("low", "p/face 1")])
        self.assertEqual(len(next(o for o in record["outcomes"] if o["rule"] == "high")["failures"]), 2)

    def test_a_figure_is_judged_unrounded(self) -> None:
        # exactly at the limit passes, a ten-thousandth past it fails: nothing is rounded before the test
        rule = Rule("r", "f", "v", "max", 1 / 0.6, "ratio", "v", "s", severity="warning")
        found, _ = evaluate({"f": {"items": [{"v": 30 / 18, "location": "a"}]}}, _set(rule), {})
        self.assertEqual(found, [])
        found, _ = evaluate({"f": {"items": [{"v": 30 / 18 + 1e-4, "location": "a"}]}}, _set(rule), {})
        self.assertEqual([f.code for f in found], ["r"])

    def test_nothing_to_judge_passes_and_figures_a_source_lacks_are_not_applicable(self) -> None:
        holes = Rule("hole", "holes", "d", "min", 1.0, "mm", "hole", "s")
        supported = Rule("wall", "walls", "t", "min", 1.0, "mm", "supported wall", "s", item_when={"supported": True})
        unknown = Rule("mesh_wall", "walls", "t", "min", 1.0, "mm", "wall", "s", item_when={"supported": None})
        report = {"holes": {"items": [], "count": 0}, "walls": {"items": [{"t": 0.5, "supported": None}]}}
        found, record = evaluate(report, _set(holes, supported, unknown), {})
        status = {o["rule"]: (o["status"], o.get("reason", "")) for o in record["outcomes"]}
        self.assertEqual(status["hole"], ("passed", "none found: no feature it applies to"))  # measured: no hole
        self.assertEqual(status["wall"][0], "not_applicable")  # a mesh's walls do not say they are supported
        self.assertEqual(status["mesh_wall"][0], "failed")    # the rule for walls of unknown support reads them
        self.assertEqual(record["none_found"], ["hole"])
        self.assertEqual([f.code for f in found], ["mesh_wall"])

    def test_a_warning_says_its_limit_is_recommended(self) -> None:
        """A recommendation's message never reads as a feasibility limit."""
        rule = Rule("r", "f", "v", "min", 1.0, "deg", "wall draft", "s", severity="warning")
        found, _ = evaluate({"f": {"items": [{"v": 0.5, "location": "a"}]}}, _set(rule), {})
        self.assertIn("wall draft 0.5 deg is under the 1 deg recommended minimum", found[0].message)

    def test_a_rule_citing_a_source_its_set_does_not_list_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _set(Rule("r", "f", "v", "max", 1.0, "mm", "v", "elsewhere"))

    def test_the_edges_of_a_verdict(self) -> None:
        rule = Rule("r", "f", "v", "min", 1.0, "mm", "v", "s", fix="raise it to {limit:g}")
        # a value just under the limit prints the digits that tell them apart
        found, _ = evaluate({"f": {"items": [{"v": 0.999999, "location": "a"}]}}, _set(rule), {})
        self.assertIn("v 0.999999 mm is under the 1 mm minimum", found[0].message)
        # a pass over some items is not a pass over the rest
        _, record = evaluate({"f": {"items": [{"v": 2.0, "location": "a"}, {"v": None, "location": "b"}]}},
                             _set(rule), {})
        self.assertEqual((record["outcomes"][0]["status"], record["outcomes"][0]["reason"]),
                         ("passed", "1 item(s) not measured"))
        # a bool is no scale
        scaled = Rule("r", "f", "v", "min", 1.0, "mm", "v", "s", scale_by="t")
        self.assertIsNone(scaled.limit_for({"t": True}))
        # the failures past those shown: counted where the record lists them, with the fix
        items = [{"v": 0.1, "location": f"p/face {i}"} for i in range(12)]
        found, _ = evaluate({"f": {"items": items}}, _set(rule), {})
        self.assertEqual((found[-1].location, found[-1].hint), ("measurements.rules", "raise it to 1"))
        # a warning is implied by an error on the same item, not on another that shares its place
        error, warning = Rule("e", "f", "v", "min", 1.0, "mm", "v", "s"), \
            Rule("w", "f", "v", "min", 2.0, "mm", "v", "s", severity="warning")
        found, _ = evaluate({"f": {"items": [{"v": 0.5}, {"v": 1.5}]}}, _set(error, warning), {})
        self.assertEqual(sorted(f.code for f in found), ["e", "w"])

    def test_every_rule_id_has_one_outcome_in_every_context(self) -> None:
        """Variants of one rule id (a tool given or not, acute or square, a minimum and a maximum, a technology)
        answer once: judged where any judged, else not evaluated or not applicable -- never twice, never gone."""
        from cad._internal import dfm

        for process in dfm.PROCESSES:
            rule_set = dfm.module(process).RULES
            ids = {rule.id for rule in rule_set.rules}
            for context, report in _exercises(rule_set):
                with self.subTest(process=process, context=context, measured=bool(report)):
                    _, record = evaluate(report, rule_set, context)
                    said = [outcome["rule"] for outcome in record["outcomes"]]
                    self.assertEqual(sorted(said), sorted(ids))

    def test_variants_that_judge_are_one_outcome_with_every_failure(self) -> None:
        low = Rule("r", "f", "v", "min", 1.0, "mm", "v", "s")
        high = Rule("r", "f", "v", "max", 5.0, "mm", "v", "s")
        gated = Rule("r", "f", "v", "min", 3.0, "mm", "v", "s", when={"tool": True})
        report = {"f": {"items": [{"v": 0.5, "location": "a"}, {"v": 9.0, "location": "b"}, {"v": 2.0, "location": "c"}]}}
        _, record = evaluate(report, _set(low, high, gated), {"tool": False})
        (outcome,) = record["outcomes"]
        self.assertEqual((outcome["status"], outcome["evaluated"]), ("failed", 3))
        self.assertEqual(sorted((f["op"], f["value"]) for f in outcome["failures"]), [("max", 9.0), ("min", 0.5)])
        self.assertEqual([variant["op"] for variant in outcome["variants"]], ["min", "max"])
        # none applies: one not_applicable, its conditions said
        _, record = evaluate({}, _set(Rule("g", "f", "v", "min", 1.0, "mm", "v", "s", when={"tool": True})), {})
        self.assertEqual([o["status"] for o in record["outcomes"]], ["not_applicable"])

    def test_every_template_names_fields_its_process_writes(self) -> None:
        """A rule's ``fix`` and ``detail`` name only the failure's own figures and what its process writes -- a
        context key, an item's field -- as a key or a keyword in the process's modules: a name that is neither
        would print as a raw brace (the text as written), silently."""
        import re
        import string

        import cad
        from cad._internal import dfm

        root = Path(cad.__file__).parent
        for process in dfm.PROCESSES:
            sources = [root / "_internal" / "dfm" / f"{process}.py", root / "build123d" / "_dfm_brep.py",
                       *(root / "build123d").glob(f"_dfm_{process}*.py"), *(root / "trimesh").glob(f"_{process}.py"),
                       *(root / "_internal").glob("meshops_*.py"),
                       *([root / "build123d" / "_dfm_dxf.py"] if process == "sheet" else [])]
            text = "".join(path.read_text(encoding="utf-8") for path in sources)
            for rule in dfm.module(process).RULES.rules:
                for template in (rule.fix, rule.detail):
                    names = {field.split(".")[0].split("[")[0]
                             for _, field, _, _ in string.Formatter().parse(template) if field}
                    unknown = {name for name in names - {"value", "limit", "unit", "xyz"}
                               if f'"{name}"' not in text and not re.search(rf"\b{name}=", text)}
                    with self.subTest(rule=rule.id, template=template):
                        self.assertEqual(unknown, set())


def _exercises(rule_set: RuleSet) -> list[tuple[dict, dict]]:
    """Contexts that satisfy each rule's ``when`` in turn (and none), each against no report and against one
    with an item for every rule's ``item_when``: where the variants of a rule id judge, split and vanish."""
    base: dict = {}
    for rule in rule_set.rules:
        if rule.scale_by:
            base[rule.scale_by] = 1.0
        if rule.by and isinstance(rule.limit, dict):
            base.setdefault(rule.by, next(iter(rule.limit)))
    contexts = [{}, dict(base)]
    for rule in rule_set.rules:
        wanted = {key: value[0] if isinstance(value, (tuple, list)) else value for key, value in rule.when.items()}
        contexts.append({**base, **wanted})
    if rule_set.selector:
        contexts.append({**base, rule_set.selector: "a value no rule names"})
    items: dict[str, list] = {}
    for index, rule in enumerate(rule_set.rules):
        fields = {other.field: 1.0 for other in rule_set.rules if other.family == rule.family}
        when = {key: value[0] if isinstance(value, (tuple, list)) else value for key, value in rule.item_when.items()}
        items.setdefault(rule.family, []).append({**fields, **when, "location": f"p/face {index}"})
    report = {family: {"items": found} for family, found in items.items()}
    unique = list({repr(sorted(context.items(), key=str)): context for context in contexts}.values())
    return [(context, measured) for context in unique for measured in ({}, report)]


class OptionsTest(unittest.TestCase):
    def test_each_option_belongs_to_its_process(self) -> None:
        resolved = manufacturing.options("step", "cnc", {"axes": 5, "tools": "6,3"})
        self.assertEqual((resolved["axes"], resolved["turning"]), (5, False))
        self.assertNotIn("rules", resolved, "the rules are the process's own: no option picks them")
        for process, given, said in (
                ("cnc", {"pull": "z"}, "--pull is not cnc's"),
                ("molding", {"turning": True}, "--turning is not molding's"),
                ("cnc", {"axes": 7}, "--axes is 3, 4 or 5"),
                ("cnc", {"rules": "generic"}, "--rules is not cnc's"),
                ("sheet", {"k_factor": 0.9}, "--k-factor"),
                ("printing", {"technology": "inkjet"}, "--technology is one of"),
                ("printing", {"material": "cheese"}, "--material is one of")):
            with self.subTest(process=process, given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("step", process, given)

    def test_exact_processes_refuse_a_mesh_and_a_dxf_is_a_cut_file(self) -> None:
        from cad._internal.refused import ArgumentRefused

        with self.assertRaisesRegex(ValueError, "check the part's STEP or model instead"):
            manufacturing.options("stl", "sheet", {})
        for document_type in ("stl", "threemf", "glb"):  # molding is judged on exact geometry alone
            with self.subTest(document_type=document_type), self.assertRaisesRegex(
                    ArgumentRefused, r"a molding check is judged on exact geometry .*: check the part's STEP or model "
                                     r"instead \(cad step dfm part.step --process molding"):
                manufacturing.options(document_type, "molding", {"pull": "z"})
        with self.assertRaisesRegex(ValueError, "--process sheet"):
            manufacturing.options("dxf", "cnc", {})
        with self.assertRaisesRegex(ValueError, "ranks molding's pulls"):
            manufacturing.options("step", "cnc", {}, candidates=True)
        self.assertEqual(manufacturing.options("dxf", "sheet", {"kerf": 0.2})["kerf"], 0.2)
        self.assertEqual(manufacturing.options("dxf", None, {"kerf": 0.2})["kerf"], 0.2, "a DXF's one process")

    def test_a_value_of_another_kind_is_refused_never_coerced(self) -> None:
        for process, given, said in (
                ("cnc", {"axes": 3.7}, "--axes is a whole number, not 3.7"),
                ("cnc", {"axes": True}, "--axes is a whole number"),
                ("cnc", {"turning": "no"}, "--turning is true or false, not 'no'"),
                ("molding", {"cavities": 1.5}, "--cavities is a whole number"),
                ("printing", {"samples": 2.5}, "--samples is a whole number"),
                ("sheet", {"kerf": float("inf")}, "--kerf is a finite number, not inf"),
                ("sheet", {"thickness": float("nan")}, "--thickness is a finite number"),
                ("cnc", {"tools": 6}, "--tools is text")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("step", process, given)
        with self.assertRaisesRegex(ValueError, "--candidates is true or false"):
            manufacturing.options("stl", "printing", {}, candidates=1)
        with self.assertRaisesRegex(ValueError, "--axes is a whole number"):  # before the process is read
            manufacturing.options("model", None, {"axes": 3.5})

    def test_each_type_takes_its_processes_and_their_options_alone(self) -> None:
        import inspect

        import cad

        for document_type, processes, has, lacks in (
                ("step", ("cnc", "sheet", "molding", "printing"), {"axes", "kerf", "pull", "nozzle"}, set()),
                ("stl", ("printing",), {"nozzle", "candidates", "units"}, {"axes", "kerf", "pull"}),
                ("dxf", ("sheet",), {"kerf", "thickness", "k_factor"}, {"axes", "pull", "candidates"})):
            with self.subTest(document_type=document_type):
                function = getattr(cad, document_type).dfm
                parameters = inspect.signature(function).parameters
                self.assertEqual(manufacturing.processes_for(document_type), processes)
                self.assertTrue(has <= set(parameters) and not lacks & set(parameters), sorted(parameters))
                with self.assertRaises(TypeError):
                    function("part", axes=3) if "axes" in lacks else function("part", nonsense=1)
        self.assertEqual(inspect.signature(cad.dxf.dfm).parameters["process"].default, "sheet")
        self.assertIn("source: the .dxf cut file to check.", cad.dxf.dfm.__doc__)
        self.assertEqual(manufacturing.options("glb", None, {})["technology"], "fdm", "a mesh's one process: printing")
        with self.assertRaisesRegex(ValueError, "a STEP keeps no process: give --process cnc"):
            manufacturing.options("step", None, {})


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

    def test_a_part_with_no_face_is_said_and_skipped(self) -> None:
        from cad.build123d import printing

        box = bd.Box(10, 10, 10)
        box.label = "box"
        hollow = bd.Compound([])
        hollow.label = "nothing"
        kit = bd.Compound(children=[box, hollow])
        kit.label = "kit"
        document = brep.parts_of(kit)
        self.assertEqual(([part.name for part in document.parts], document.empty), (["box"], ["nothing"]))
        result = printing(kit)
        self.assertEqual([f.location for f in result.findings if f.code == "empty_parts"], ["nothing"])
        self.assertFalse(result.measurements["partial"])


class IntegrityTest(unittest.TestCase):
    def test_no_closed_solid_is_refused_in_every_process_and_says_what_to_fix(self) -> None:
        from cad.build123d import cnc, molding, printing, sheet_metal

        shell = bd.Shell(bd.Box(10, 10, 10).faces()[:5])
        face = bd.Rectangle(10, 10).face()
        for shape in (shell, face):
            for check in (cnc, sheet_metal, molding, printing):
                result = check(shape)
                self.assertFalse(result.ok)
                self.assertEqual([f.code for f in result.findings], ["not_solid"], check.__name__)
                self.assertIn("Close the shell into a solid", result.findings[0].message)

    def test_faces_beside_a_solid_are_an_error_said_first(self) -> None:
        from cad.build123d import cnc, molding

        part = bd.Compound([bd.Box(10, 10, 10), bd.Pos(30, 0, 0) * bd.Rectangle(5, 5).face()])
        for check in (cnc, molding):
            result = check(part)
            self.assertFalse(result.ok)
            self.assertEqual((result.findings[0].severity, result.findings[0].code), ("error", "not_watertight"))

    def test_a_part_drawn_in_metres_is_said_first(self) -> None:
        from cad.build123d import cnc, sheet_metal

        plate = bd.Box(0.1, 0.05, 0.002)  # a 100 x 50 x 2 mm plate drawn in metres
        for check in (cnc, sheet_metal):
            first = check(plate).findings[0]
            self.assertEqual((first.severity, first.code), ("warning", "units_suspect"))
            self.assertIn("metres (111.8 mm if so)", first.message)
        self.assertFalse(any(f.code == "units_suspect" for f in cnc(bd.Box(100, 50, 2)).findings))

    def test_one_units_test_in_every_process_and_on_both_paths(self) -> None:
        """Under 1 mm or over 10 m across is suspect wherever it is read (each process on exact geometry, printing
        on a mesh), the note offering only the readings that make it a plausible size; a full 3048 x 1524 sheet
        is not."""
        import cad
        from cad._internal.dfm._common import units_doubt
        from cad.build123d import cnc, molding, printing, sheet_metal

        self.assertFalse(units_doubt(float(np.hypot(3048, 1524)), "it reads")["units_suspect"])
        note = units_doubt(12_000.0, "it reads")["note"]
        self.assertIn("micrometres, or millimetres read as metres (12 mm if so)", note)
        self.assertNotIn("metres (1.2e+07", note)
        self.assertNotIn("inches (", units_doubt(0.002, "it reads")["note"], "0.05 mm read as inches: no fit")
        for size, label in ((0.0005, "small"), (12_000.0, "large")):
            box = bd.Box(size, size / 2, size / 50)
            for check in (cnc, sheet_metal, molding, printing):
                first = check(box).findings[0]
                self.assertEqual((first.code, first.severity), ("units_suspect", "warning"), (label, check))
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "box.stl"
                bd.export_stl(box, str(path))
                codes = {f.code for f in cad.stl.dfm(path, process="printing").findings}
                self.assertIn("units_suspect", codes, label)

    def test_a_faces_sampling_tolerance_turns_with_it(self) -> None:
        face = bd.Box(36, 20, 5).faces().sort_by(bd.Axis.Z)[-1]
        turned = (bd.Rot(17, 23, 41) * bd.Box(36, 20, 5)).faces().sort_by(bd.Axis.Z)[-1]
        self.assertAlmostEqual(brep.deflection_for(face), 0.72, places=6)
        for other in (bd.Rot(0, 0, 30) * face, bd.Rot(17, 23, 41) * face):
            self.assertAlmostEqual(brep.deflection_for(other), brep.deflection_for(face), places=6)
        self.assertGreater(brep.deflection_for(turned), 0.0)


class DeclaredMaterialTest(unittest.TestCase):
    """A check given no material judges by the one the parts declare, when they agree."""

    def test_the_declared_material_is_read_and_said(self) -> None:
        from bd_materials import metals
        from cad.build123d import cnc

        plate = bd.Box(40, 20, 6) - bd.Cylinder(4, 10)
        plate.label, plate.material = "plate", metals.aluminum()
        result = cnc(plate)
        codes = {finding.code for finding in result.findings}
        self.assertIn("material_declared", codes)
        self.assertNotIn("cnc.material_assumed", codes)
        self.assertEqual(result.measurements["rules"]["context"]["material"], "aluminum")
        self.assertEqual(result.measurements["bodies"][0]["material"], "Alu_G6061_T6")
        # a material given wins, and the declared one it overrides is said
        given = cnc(plate, material="steel")
        self.assertEqual(given.measurements["rules"]["context"]["material"], "steel")
        said = [finding.message for finding in given.findings if finding.code == "material_declared"]
        self.assertEqual(said, ["material steel as given, not the aluminum the parts declare: judged as steel"])

    def test_parts_that_disagree_are_judged_as_with_none(self) -> None:
        from bd_materials import metals, plastics
        from cad.build123d import cnc, molding

        plate = bd.Box(40, 20, 6)
        plate.label, plate.material = "plate", metals.aluminum()
        clip = bd.Pos(0, 40, 0) * bd.Box(10, 10, 10)
        clip.label, clip.material = "clip", plastics.abs_()
        result = cnc(bd.Compound(children=[plate, clip]))
        codes = {finding.code for finding in result.findings}
        self.assertIn("material_mixed", codes)
        self.assertIn("cnc.material_assumed", codes)
        self.assertIsNone(result.measurements["rules"]["context"]["material"])
        # a resin declared is the molding check's resin
        molded = molding(clip, pull="z")
        self.assertEqual(molded.measurements["rules"]["context"].get("resin"), "abs")
        self.assertNotIn("resin_unknown", {finding.code for finding in molded.findings})


class DeclaredProcessTest(unittest.TestCase):
    """A check given no process takes the one the parts declare (``bd_materials``' ``process=``), says so, and
    lets a technology or layer height given win over the declared one."""

    @staticmethod
    def _part(material: object, label: str = "plate", x: float = 0.0) -> bd.Part:
        part = bd.Pos(x, 0, 0) * (bd.Box(40, 20, 6) - bd.Cylinder(4, 10))
        part.label, part.material = label, material
        return part

    @staticmethod
    def _checked(shape: object, **given: object):
        from cad.build123d._dfm_check import checked

        return checked(shape, None, dict(given))

    def _context(self, result) -> dict:
        self.assertIn("process_declared", {finding.code for finding in result.findings})
        return result.measurements["rules"]["context"]

    def test_each_declared_route_is_its_process(self) -> None:
        from bd_materials import metals, plastics
        from bd_materials.processes import fdm, machined, molded, slm, vat

        machined_ = self._checked(self._part(metals.aluminum(process=machined())))
        self.assertEqual((machined_.measurements["process"], machined_.measurements["bodies"][0]["process"]),
                         ("cnc", "machined"))
        said = next(f.message for f in machined_.findings if f.code == "process_declared")
        self.assertEqual(said, "process cnc, read from the part's declared material (Alu_G6061_T6, machined): "
                               "give --process to check another")
        self.assertIn("holes", machined_.measurements, "the cnc check ran")
        self._context(machined_)
        self.assertEqual(self._checked(self._part(plastics.abs_(process=molded()))).measurements["process"], "molding")
        printed = self._checked(self._part(plastics.pla(process=fdm(layer_height_mm=0.2))))
        self.assertEqual(printed.measurements["process"], "printing")
        self.assertEqual({key: self._context(printed)[key] for key in ("technology", "layer_height")},
                         {"technology": "fdm", "layer_height": 0.2})
        # the other prints resolve as fdm's does (measured above): their technology, no layer height
        for applied, technology in ((slm(), "pbf"), (vat(), "sla")):
            with self.subTest(technology=technology):
                parts = [("plate", metals.titanium(process=applied))]
                process, resolved, said = manufacturing.declared("step", parts, {})
                self.assertEqual((process, resolved["technology"], resolved["layer_height"], said["code"]),
                                 ("printing", technology, None, "process_declared"))

    def test_a_technology_given_wins_over_the_declared_one(self) -> None:
        from bd_materials import plastics
        from bd_materials.processes import fdm

        part = self._part(plastics.pla(process=fdm(layer_height_mm=0.3)))
        context = self._context(self._checked(part, technology="sla"))
        self.assertEqual(context["technology"], "sla")
        self.assertNotEqual(context["layer_height"], 0.3, "fdm's layer height is not sla's")
        _, resolved, _ = manufacturing.declared("step", [("plate", part.material)], {"layer_height": 0.1})
        self.assertEqual((resolved["technology"], resolved["layer_height"]), ("fdm", 0.1))

    def test_parts_that_disagree_or_declare_nothing_checkable_name_the_fix(self) -> None:
        from bd_materials import metals, plastics
        from bd_materials.processes import cast, fdm, machined, molded

        from cad._internal.refused import ArgumentRefused

        # each is the caller's to fix with --process: refused by name (the command's exit 2), never a result
        with self.assertRaisesRegex(ArgumentRefused, r"machined \(a\), molded \(b\).*give --process"):
            self._checked(bd.Compound(children=[self._part(metals.aluminum(process=machined()), "a"),
                                                self._part(plastics.abs_(process=molded()), "b", 60)]))
        for material, said in ((metals.aluminum(process=cast()), r"\(Alu_G6061_T6, cast\) is made by a process no "),
                               (metals.aluminum(), "no part declares one"), (None, "no part declares one")):
            with self.subTest(said=said), self.assertRaisesRegex(ArgumentRefused, said + ".*give --process cnc, sheet"):
                self._checked(self._part(material))
        # an option of another process is refused once the declared one is read
        with self.assertRaisesRegex(ArgumentRefused, "--pull is not cnc's.*the parts declare machined"):
            self._checked(self._part(metals.aluminum(process=machined())), pull="z")
        # FDM parts whose layer heights differ: the technology's own, and said
        parts = [("a", plastics.pla(process=fdm(layer_height_mm=0.2))), ("b", plastics.pla(process=fdm(layer_height_mm=0.3)))]
        _, resolved, said = manufacturing.declared("step", parts, {})
        self.assertIsNone(resolved["layer_height"])
        self.assertIn("the technology's layer height: the parts declare 0.2, 0.3 mm", said["message"])

    def test_the_type_side_defers_the_process_to_a_brep_types_read(self) -> None:
        from types import SimpleNamespace

        from cad._internal.dfm import processes

        self.assertIsNone(manufacturing.options("model", None, {"material": "aluminum"}))
        with self.assertRaisesRegex(ValueError, "give --process"):  # a STEP keeps none
            manufacturing.options("step", None, {})
        for given, said in (({"units": "cm"}, "an xbf is in millimetres"),
                            ({"material": "cheese"}, "--material is one of")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("xbf", None, given)
        # duck typed: a route's value, an FDM skin's pitch is its line width, not a layer height
        route = SimpleNamespace(value="fdm")
        self.assertEqual(processes.declared(SimpleNamespace(process=route, pitch_mm=0.12)), ("printing", "fdm", 0.12))
        self.assertEqual(processes.declared(SimpleNamespace(process=route, pitch_mm=0.4, skin=True)),
                         ("printing", "fdm", None))
        self.assertIsNone(processes.declared(SimpleNamespace(process=SimpleNamespace(value="wrought"))))


class DetailTest(unittest.TestCase):
    def test_a_rule_formats_the_item_and_the_context_into_its_detail_and_hint(self) -> None:
        rule = Rule("c.edge", "edges", "makeable", "min", 1, "ways", "ways", "s",
                    fix="round edge {edge} ({void_angle_deg:.0f} deg) to {limit:g} {unit}; shop radius {shop_r:g}",
                    detail="edge {edge}, {void_angle_deg:.1f} deg at {xyz}")
        report = {"edges": {"items": [{"makeable": 0, "location": "p/face 3", "edge": "p/edge 12",
                                       "void_angle_deg": 176.04, "xyz": [1.0, 2.5, 0.0]}]}}
        found, _ = evaluate(report, _set(rule), {"shop_r": 1.5})
        self.assertEqual(found[0].message.split(" (")[-1].rstrip(")"), "edge p/edge 12, 176.0 deg at 1, 2.5, 0")
        self.assertEqual(found[0].hint, "round edge p/edge 12 (176 deg) to 1 ways; shop radius 1.5")
        # a name the item lacks leaves the text as written
        bare = Rule("c.bare", "edges", "makeable", "min", 1, "ways", "ways", "s", fix="see {nothing}")
        found, _ = evaluate(report, _set(bare), {})
        self.assertEqual(found[0].hint, "see {nothing}")


class SelectorTest(unittest.TestCase):
    def test_a_rule_with_no_variant_for_the_selected_value_is_not_evaluated_and_a_silent_set_is_said(self) -> None:
        sla = Rule("p.hole", "holes", "d", "min", 0.8, "mm", "hole", "s", when={"technology": ("sla",)})
        sls = Rule("p.hole", "holes", "d", "min", 1.5, "mm", "hole", "s", when={"technology": ("sls",)})
        other = Rule("p.turn", "turning", "d", "max", 1.0, "mm", "turned", "s", when={"turning": True})
        rules = RuleSet("printing", "Test", "1", (sla, sls, other), (SOURCE,), selector="technology")
        report = {"holes": {"items": [{"d": 0.5, "location": "p/face 1"}]}}
        found, record = evaluate(report, rules, {"technology": "fdm", "turning": False})
        self.assertEqual(found, [])
        hole = [o for o in record["outcomes"] if o["rule"] == "p.hole"]
        self.assertEqual([(o["status"], o["reason"]) for o in hole],
                         [("not_evaluated", "the rules give no limit for technology fdm")])
        # a rule for another context stays not_applicable: it is not a missing figure
        turn = next(o for o in record["outcomes"] if o["rule"] == "p.turn")
        self.assertEqual(turn["status"], "not_applicable")
        self.assertEqual(record["evaluated"], 0)
        # with a technology the rules know, the rule judges
        found, record = evaluate(report, rules, {"technology": "sla", "turning": False})
        self.assertEqual([f.code for f in found], ["p.hole"])
        self.assertEqual(record["evaluated"], 1)


class SummaryTest(unittest.TestCase):
    def test_a_failed_check_digests_what_failed_in_one_line(self) -> None:
        from cad.build123d import cnc

        # four 0.04 mm holes, under the 0.05 mm the smallest tool makes (an error: draft_min, a molding
        # recommendation, no longer fails a check; a hole under 1 mm is a warning)
        box = bd.Box(30, 20, 10) - bd.Pos(0, 0, 0) * bd.Compound([bd.Pos(x, y, 0) * bd.Cylinder(0.02, 10)
                                                                     for x in (-8, 8) for y in (-5, 5)])
        box.label = "box"
        result = cnc(box, material="aluminum")
        self.assertFalse(result.ok)
        self.assertIn("failed: cnc.hole_diameter x4", result.summary)  # every failure, not the findings shown
        self.assertTrue(result.human_lines()[-1].startswith("FAILED box: "))
        self.assertIn("cnc.hole_diameter x4", result.human_lines()[-1])
        # errors come first, then warnings, then the facts
        order = [{"error": 0, "warning": 1, "info": 2}[f.severity] for f in result.findings]
        self.assertEqual(order, sorted(order))

    def test_the_digest_counts_a_process_error_and_an_ok_line_its_warnings(self) -> None:
        from cad.build123d import cnc, printing, sheet_metal

        block = bd.Box(40, 30, 15); block.label = "block"
        self.assertTrue(cnc(block, turning=True).summary.endswith("failed: cnc.no_turning_axis x1"))
        self.assertIn("failed: sheet.not_sheet x1", sheet_metal(block).summary)
        warned = printing(block, technology="pbf")
        self.assertTrue(warned.ok)
        self.assertRegex(warned.human_lines()[-1], r"^OK block: printing pbf: .* \(1 warning\(s\)\)$")


class CheckpointTest(unittest.TestCase):
    """A check asked to stop stops between its faces, in every process: its measurement reaches a checkpoint
    (``cad._internal.dfm.checkpoint``) at least once a face, in each module that does the work, and the stop
    goes through every family's ``except Exception``. Counted, never timed."""

    # A thin drilled plate, a sheet: every process measures it whole.
    SITES = {"cnc": {"_dfm_cnc.py:run", "_dfm_cnc_model.py:_cast", "_dfm_cnc_model.py:_sample"},
             "sheet": {"_dfm_sheet.py:_part", "_dfm_sheet.py:_samples", "meshops_sheet.py:inside",
                       "_dfm_brep.py:_crossings"},
             "molding": {"_dfm_molding.py:_safe", "_dfm_molding.py:cast_faces", "meshops_molding.py:ball_thickness"},
             "printing": {"_dfm_printing.py:_safe", "_dfm_printing.py:_first_hits", "_dfm_brep.py:samples"}}

    class Recorder:
        """Stands for the flag ``checkpoint`` reads: each read recorded, and set from the ``stop_at``-th on."""

        def __init__(self, stop_at: int | None = None) -> None:
            self.count, self.stop_at, self.sites = 0, stop_at, set()

        def is_set(self) -> bool:
            frame = sys._getframe(2)
            self.count += 1
            self.sites.add(f"{Path(frame.f_code.co_filename).name}:{frame.f_code.co_name}")
            return self.stop_at is not None and self.count >= self.stop_at

    def test_every_process_reaches_a_checkpoint_at_every_face_and_stops_there(self) -> None:
        from unittest import mock

        from cad._internal import dfm
        from cad.build123d import _dfm_check

        holes = bd.Compound(children=[bd.Pos(i * 8 - 16, j * 8 - 16, 0) * bd.Cylinder(1.5, 4)
                                      for i in range(5) for j in range(5)])
        part = bd.Box(60, 60, 2) - holes
        faces = len(part.faces())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plate.step"
            bd.export_step(part, str(path))
            for process, sites in self.SITES.items():
                with self.subTest(process=process):
                    resolved = manufacturing.options("step", process, {})
                    recorder = self.Recorder()
                    with mock.patch.object(dfm, "_STOPPING", recorder):
                        _dfm_check.measure("step", path, process, resolved, False)
                    self.assertGreaterEqual(recorder.count, faces, sorted(recorder.sites))
                    self.assertLessEqual(sites, recorder.sites, sorted(recorder.sites))
                    with mock.patch.object(dfm, "_STOPPING", self.Recorder(stop_at=recorder.count // 2)), \
                            self.assertRaises(dfm.Cancelled):
                        _dfm_check.measure("step", path, process, resolved, False)


def _lofted() -> bd.Shape:
    """A free-form part: a loft through three sections (two B-spline faces), a slot cut across it."""
    a = bd.Sketch() + bd.Ellipse(20, 12)
    b = bd.Pos(3, 2, 25) * (bd.Sketch() + bd.Ellipse(12, 16))
    c = bd.Pos(-2, 0, 50) * (bd.Sketch() + bd.Circle(9))
    return bd.loft([a.faces()[0], b.faces()[0], c.faces()[0]]) - bd.Pos(0, 0, 25) * bd.Box(8, 60, 6)


class ExactRaysTest(unittest.TestCase):
    """Exact rays cost what they must (``brep.Screen``, ``brep.Intersector``) and find every crossing on a face the
    kernel's own intersector finds: the screen leaves out only faces a ray cannot cross, and the full intersector
    adds its crossings to the fast one's where the line passes a boundary it could accept one at."""

    def test_rays_answer_as_the_kernel_s_intersector_and_skip_faces_they_cannot_cross(self) -> None:
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector

        shape = _lofted()
        part = brep.Part("p", "p", shape)
        samples = [sample for face in part.faces() for sample in brep.samples(face, 24)]
        rng = np.random.default_rng(7)
        rays = []
        for sample in samples:
            turned = rng.normal(size=3)
            rays += [(sample.point, -sample.normal), (sample.point, sample.normal),
                     (sample.point, turned / np.linalg.norm(turned))]
        # every free-form face heavy (``brep.HEAVY_EDGES``): the screen and the fast intersector on both B-splines
        heavy = mock.patch.object(brep, "HEAVY_EDGES", 1)
        heavy.start()
        self.addCleanup(heavy.stop)
        fast, plain = brep.Rays(shape), brep.Rays(shape)
        plain.screen.order = lambda o, d, c, e, s, en: (c, e)  # type: ignore[method-assign]
        performed = {"fast": 0, "plain": 0}

        def kernel(index: int) -> object:
            found = plain._intersectors.get(index)
            if found is None:
                found = plain._intersectors[index] = IntCurvesFace_Intersector(plain.faces[index], 1e-7)
            performed["plain"] += 1
            return found

        plain._intersector = kernel  # type: ignore[method-assign]
        counting = fast._intersector

        def counted(index: int) -> object:
            performed["fast"] += 1
            return counting(index)

        fast._intersector = counted  # type: ignore[method-assign]
        for origin, direction in rays:
            a, b = fast.first(origin, direction, skip=1e-6), plain.first(origin, direction, skip=1e-6)
            self.assertEqual(a is None, b is None)
            if a is not None and b is not None:
                # the same crossing; near a boundary found on the stretch there, to the root's last digits
                self.assertAlmostEqual(a[0], b[0], delta=1e-12 * max(1.0, b[0]))
                self.assertTrue(a[1].IsSame(b[1]))
        for origin, direction in rays[:200]:
            mine, kernel = fast.intervals(origin, direction), plain.intervals(origin, direction)
            self.assertEqual(len(mine), len(kernel))
            for (p, q), (r, t) in zip(mine, kernel):
                self.assertAlmostEqual(p, r, delta=1e-12 * max(1.0, abs(r)))
                self.assertAlmostEqual(q, t, delta=1e-12 * max(1.0, abs(t)))
        self.assertTrue(fast.screen.heavy.any())
        self.assertLess(performed["fast"], performed["plain"])

    def test_a_ray_grazing_near_an_edge_keeps_every_crossing_on_the_face(self) -> None:
        # The full intersector answers differently on a stretch of a ray than on the whole of it: a crossing on
        # the face that the fast intersector finds is never dropped for the stretch's answer.
        from unittest import mock

        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.BRepLProp import BRepLProp_SLProps
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        from OCP.IntCurvesFace import IntCurvesFace_Intersector
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        heavy = mock.patch.object(brep, "HEAVY_EDGES", 1)
        heavy.start()
        self.addCleanup(heavy.stop)
        rays = brep.Rays(_lofted())
        rng = np.random.default_rng(3)
        lost = checked = 0
        for index, face in enumerate(rays.faces):
            if not rays.screen.heavy[index]:
                continue
            surface = BRepAdaptor_Surface(face)
            explorer = TopExp_Explorer(face, TopAbs_EDGE)
            while explorer.More():
                edge = TopoDS.Edge(explorer.Current())
                explorer.Next()
                if BRep_Tool.Degenerated_s(edge):
                    continue
                curve = BRepAdaptor_Curve(edge)
                for t in np.linspace(curve.FirstParameter(), curve.LastParameter(), 4):
                    at = curve.Value(float(t))
                    projected = GeomAPI_ProjectPointOnSurf(at, BRep_Tool.Surface_s(face))
                    if not projected.NbPoints():
                        continue
                    props = BRepLProp_SLProps(surface, *projected.LowerDistanceParameters(), 1, 1e-9)
                    if not props.IsNormalDefined():
                        continue
                    normal = np.array([props.Normal().X(), props.Normal().Y(), props.Normal().Z()])
                    for off in (0.0, 1e-4, 1e-2, 5e-2):
                        for angle in (30.0, 5.0, 1.0, 0.2):
                            jitter, along = rng.normal(size=3), rng.normal(size=3)
                            jitter -= normal * (jitter @ normal)
                            along -= normal * (along @ normal)
                            target = np.array([at.X(), at.Y(), at.Z()]) + off * jitter / np.linalg.norm(jitter)
                            d = -math.sin(math.radians(angle)) * normal \
                                + math.cos(math.radians(angle)) * along / np.linalg.norm(along)
                            d /= np.linalg.norm(d)
                            line = gp_Lin(gp_Pnt(*(target - 30.0 * d)), gp_Dir(*d))
                            kernel = IntCurvesFace_Intersector(face, 1e-7)
                            kernel.Perform(line, 0.0, 1e9)
                            mine = rays._intersector(index)
                            mine.Perform(line, 0.0, 1e9)
                            found = [mine.WParameter(k) for k in range(1, mine.NbPnt() + 1)]
                            for k in range(1, kernel.NbPnt() + 1):
                                w = kernel.WParameter(k)
                                point = kernel.Pnt(k)
                                on = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(point).Vertex(), face)
                                if not on.IsDone() or on.Value() > 1e-9:
                                    continue  # in the boundary's tolerance band, beyond the trim
                                checked += 1
                                lost += not any(abs(w - x) <= 1e-7 for x in found)
        self.assertGreater(checked, 500)
        self.assertEqual(lost, 0)

    def test_a_stretch_the_kernel_fails_on_loses_its_own_crossings_alone(self) -> None:
        from unittest import mock

        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        from OCP.Standard import Standard_Failure

        heavy = mock.patch.object(brep, "HEAVY_EDGES", 1)
        heavy.start()
        self.addCleanup(heavy.stop)
        rays = brep.Rays(_lofted())
        index = int(np.flatnonzero(rays.screen.heavy)[0])
        sample = brep.samples(brep.Part("p", "p", _lofted()).faces()[index], 4)[0]
        line = gp_Lin(gp_Pnt(*(sample.point + 5.0 * sample.normal)), gp_Dir(*(-sample.normal)))
        intersector = rays._intersector(index)
        intersector.Perform(line, 0.0, 1e9)
        crossings = [intersector.WParameter(k) for k in range(1, intersector.NbPnt() + 1)]
        self.assertTrue(crossings)

        class Broken:
            def Perform(self, *args: object) -> None:  # noqa: N802 - the kernel's name
                raise Standard_Failure("the kernel failed")

        intersector._full = Broken()
        with mock.patch.object(brep.Intersector, "_near_boundary", lambda self, line, a, b: [(0.0, 1e-3)]):
            intersector.Perform(line, 0.0, 1e9)
        self.assertTrue(intersector.IsDone())
        self.assertEqual([intersector.WParameter(k) for k in range(1, intersector.NbPnt() + 1)], crossings)
        self.assertEqual(rays.screen.failed, {index: 1})

    def test_a_heavy_face_whose_triangulation_cannot_be_read_is_read_once(self) -> None:
        from unittest import mock

        heavy = mock.patch.object(brep, "HEAVY_EDGES", 1)
        heavy.start()
        self.addCleanup(heavy.stop)
        rays = brep.Rays(_lofted())
        with mock.patch.object(brep.Screen, "_chunks", return_value=None) as read:
            for x in np.linspace(-15, 15, 20):
                rays.hits((x, -50.0, 12.0), (0.0, 1.0, 0.0))
        self.assertEqual(read.call_count, int(rays.screen.heavy.sum()))

    def test_a_copy_names_its_own_faces_the_kernel_failed_on_and_its_rules_say_they_were_not_measured(self) -> None:
        from unittest import mock

        from OCP.Standard import Standard_Failure

        import cad.build123d as cb

        parts = []
        for index in range(2):
            placed = bd.Pos(60 * index, 0, 0) * (bd.Box(30, 20, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 6))
            placed.label = f"t{index}"
            parts.append(placed)
        original = brep.Intersector.Perform

        class Broken:
            def Perform(self, *args: object) -> None:  # noqa: N802 - the kernel's name
                raise Standard_Failure("the kernel failed")

        def one_face_fails(self: brep.Intersector, line: object, start: float, end: float) -> None:
            if self._index == 0:
                self._full, self._fast = Broken(), None
            original(self, line, start, end)

        with mock.patch.object(brep.Intersector, "Perform", one_face_fails):
            result = cb.cnc(bd.Compound(children=parts, label="kit"), material="aluminum")
        said = sorted(f.location for f in result.findings if f.code == "rays_unintersected")
        self.assertEqual(said, ["t0/face 1", "t1/face 1"])
        lost = {name: family["unmeasured_faces"] for name, family in result.measurements.items()
                if isinstance(family, dict) and family.get("unmeasured_faces")}
        self.assertTrue(lost)
        self.assertTrue(all(faces == ["t0/face 1", "t1/face 1"] for faces in lost.values()), lost)
        outcomes = [o for o in result.measurements["rules"]["outcomes"] if o.get("unmeasured_faces")]
        self.assertTrue(outcomes)
        for outcome in outcomes:
            self.assertGreaterEqual(outcome["unmeasured"], 2)
            self.assertIn("t1/face 1", outcome["reason"])

    def test_a_face_the_kernel_cannot_intersect_is_said_and_the_family_completes(self) -> None:
        from unittest import mock

        from OCP.Standard import Standard_Failure

        import cad.build123d as cb

        shape = bd.Box(30, 20, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 6)
        shape.label = "tray"
        original = brep.Intersector.Perform

        class Broken:
            """The kernel's intersector failing on every line, as OCCT does on a degenerate surface patch."""

            def Perform(self, *args: object) -> None:  # noqa: N802 - the kernel's name
                raise Standard_Failure("the kernel failed")

        def one_face_fails(self: brep.Intersector, line: object, start: float, end: float) -> None:
            if self._index == 0:
                self._full, self._fast = Broken(), None
            original(self, line, start, end)

        for process, check in (("cnc", lambda: cb.cnc(shape, material="aluminum")),
                               ("sheet", lambda: cb.sheet_metal(shape, material="aluminum")),
                               ("printing", lambda: cb.printing(shape, technology="fdm"))):
            with self.subTest(process=process), mock.patch.object(brep.Intersector, "Perform", one_face_fails):
                result = check()
                self.assertFalse(result.measurements.get("partial_sections"), result.measurements.get("partial_sections"))
                said = [finding for finding in result.findings if finding.code == "rays_unintersected"]
                self.assertEqual(len(said), 1, [finding.code for finding in result.findings])
                self.assertIn("tray/face 1", said[0].message)


def _bracket() -> bd.Shape:
    """A plate with a pocket and a hole: a part with something in every cnc family."""
    plate = bd.Box(40, 24, 8) - bd.Pos(-7.5, 0, 2) * bd.Box(14, 12, 4) - bd.Pos(12, 0, 0) * bd.Cylinder(3, 8)
    return plate.fillet(1.0, plate.edges().group_by(bd.Axis.Z)[-1])


class CopiesTest(unittest.TestCase):
    """An assembly's parts that are one geometry moved (``brep.copies``) are measured once, and every copy's
    items are said at its own refs and places: a row of copies costs one part's measurement, and reads as the
    same parts each measured alone."""

    # turned by less than 45 degrees: each copy's own machine frame is its first's turned with it
    PLACES = ((0, 0, 0, 0), (70, 0, 0, 0), (0, 60, 0, 30), (-70, -10, 15, -20))

    def _kit(self, shape: bd.Shape) -> bd.Compound:
        parts = []
        for index, (x, y, z, turn) in enumerate(self.PLACES):
            placed = bd.Pos(x, y, z) * bd.Rot(0, 0, turn) * shape
            placed.label = f"b{index}"
            parts.append(placed)
        kit = bd.Compound(children=parts)
        kit.label = "kit"
        return kit

    def test_copies_are_found_with_their_motion(self) -> None:
        kit = self._kit(_bracket())
        other = bd.Pos(0, -60, 0) * bd.Box(40, 24, 8)
        other.label = "other"
        document = brep.parts_of(bd.Compound(children=[*kit.children, other]), "kit")
        found = brep.copies(document.parts)
        self.assertEqual(sorted(found), [1, 2, 3])
        self.assertTrue(all(found[k].of == 0 and found[k].proper for k in found))
        corner = np.array([20.0, 12.0, 4.0])
        for index in (2, 3):
            x, y, z, turn = self.PLACES[index]
            c, s_ = math.cos(math.radians(turn)), math.sin(math.radians(turn))
            np.testing.assert_allclose(found[index].point(corner),
                                       [c * 20.0 - s_ * 12.0 + x, s_ * 20.0 + c * 12.0 + y, 4.0 + z], atol=1e-9)

    def test_a_different_part_that_shares_its_ends_and_middles_is_no_copy(self) -> None:
        # two plates whose curved edge is a Bezier with the same ends and middle, its other poles apart
        def plate(poles: list[tuple[float, float]]) -> bd.Shape:
            spline = bd.Edge.make_bezier(*[bd.Vector(x, y, 0) for x, y in poles])
            wire = bd.Wire([spline, bd.Edge.make_line((40, 0), (40, 40)), bd.Edge.make_line((40, 40), (0, 40)),
                            bd.Edge.make_line((0, 40), (0, 0))])
            return bd.extrude(bd.Face(wire), 5)

        a = plate([(0, 0), (10, 5), (20, 10), (30, 5), (40, 0)])
        b = bd.Pos(0, 60, 0) * plate([(0, 0), (10, 12.5), (20, 0), (30, 12.5), (40, 0)])
        a.label, b.label = "a", "b"
        self.assertEqual(brep.copies(brep.parts_of(bd.Compound(children=[a, b]), "kit").parts), {})

    def test_a_copy_reports_its_own_machine_frame_and_one_square_to_it_is_measured_anew(self) -> None:
        from unittest import mock

        import cad.build123d as cb
        from cad.build123d import _dfm_cnc

        def frames(*turns: float) -> tuple[list[dict], int]:
            parts = []
            for index, turn in enumerate(turns):
                placed = bd.Pos(80 * index, 0, 0) * bd.Rot(0, 0, turn) * _bracket()
                placed.label = f"b{index}"
                parts.append(placed)
            with mock.patch.object(_dfm_cnc, "_measure_part", side_effect=_dfm_cnc._measure_part) as measured:
                result = cb.cnc(bd.Compound(children=parts, label="kit"), material="aluminum")
            return result.measurements["machine"]["frames"], measured.call_count

        together, count = frames(0, 30)
        self.assertEqual(count, 1)
        alone, _ = frames(30)
        self.assertEqual(together[1]["copy_of"], "b0")
        self.assertEqual((together[1]["axes"], together[1]["turned"]), (alone[0]["axes"], alone[0]["turned"]))
        self.assertTrue(together[1]["turned"])
        # turned a right angle, it reads square to the world again: a frame of its own, so measured anew
        _, count = frames(0, 90)
        self.assertEqual(count, 2)

    def test_a_row_of_copies_costs_one_part_and_reads_as_its_first_moved(self) -> None:
        from unittest import mock

        import cad.build123d as cb
        from cad.build123d import _dfm_cnc, _dfm_sheet

        kit = self._kit(_bracket())
        for process, module, name, check in (
                ("cnc", _dfm_cnc, "_measure_part", lambda shape: cb.cnc(shape, material="aluminum")),
                ("sheet", _dfm_sheet, "_part", lambda shape: cb.sheet_metal(shape, material="aluminum"))):
            with self.subTest(process=process):
                real = getattr(module, name)
                with mock.patch.object(module, name, side_effect=real) as measured:
                    together = check(kit)
                self.assertEqual(measured.call_count, 1)
                self.assertEqual(together.measurements.get("partial_sections"), [])
                alone = check(bd.Compound(children=[self._kit(_bracket()).children[0]], label="kit"))
                for family, value in alone.measurements.items():
                    if not isinstance(value, dict) or not value.get("items"):
                        continue
                    first = [item for item in value["items"] if str(item.get("location", "")).startswith("b0/")]
                    for index, (x, y, z, turn) in enumerate(self.PLACES):
                        theirs = [item for item in together.measurements[family]["items"]
                                  if str(item.get("location", "")).startswith(f"b{index}/")]
                        self.assertEqual(sorted(item["location"].split("/", 1)[1] for item in theirs),
                                         sorted(item["location"].split("/", 1)[1] for item in first), family)
                        c, s_ = math.cos(math.radians(turn)), math.sin(math.radians(turn))
                        turn_xy = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
                        for a in theirs:
                            # its first's item at the same face, of the same figures, moved onto it
                            alike = [item for item in first if item["location"].split("/", 1)[1]
                                     == a["location"].split("/", 1)[1] and all(
                                         item.get(k) == a.get(k) for k in a if type(a[k]) in (int, float)
                                         or k in ("kind", "reason"))]
                            self.assertTrue(alike, (family, a))
                            if a.get("xyz") is not None:
                                gaps = [float(np.linalg.norm(np.array(a["xyz"]) - (turn_xy @ np.array(b["xyz"])
                                                                                    + np.array([x, y, z]))))
                                        for b in alike]
                                self.assertLess(min(gaps), 2e-4, (family, a))


if __name__ == "__main__":
    unittest.main()
