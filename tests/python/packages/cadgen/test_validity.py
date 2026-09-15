"""cadgen.validity: per-solid topology, closure, and orientation checking."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from build123d import Box, Compound, Location, Pos, Shell, Solid
from OCP.TopoDS import TopoDS

from cadgen.validity import (
    REASON_INVALID_TOPOLOGY,
    REASON_NON_POSITIVE_VOLUME,
    REASON_NO_SOLID,
    REASON_OPEN_SHELL,
    REASON_SELF_INTERSECTING,
    SELF_INTERSECTION_EVERY_PLACEMENT,
    SELF_INTERSECTION_FIRST_PLACEMENT,
    SELF_INTERSECTION_SKIPPED,
    _check_payload_worker,
    _group_findings,
    _placed_compound,
    _self_intersection_mode,
    check_occurrence_shape,
    check_placements,
    prototype_groups,
)


def reversed_box(size=10):
    """A solid with inverted orientation: valid topology, negative volume."""
    return Solid(TopoDS.Solid_s(Box(size, size, size).solids()[0].wrapped.Reversed()))


class CheckOccurrenceShapeTest(unittest.TestCase):
    def test_a_closed_positive_solid_passes(self):
        result = check_occurrence_shape(Box(40, 30, 20).wrapped)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["solidCount"], 1)
        self.assertAlmostEqual(result["volumes"][0], 24000.0, delta=1.0)

    def test_an_open_shell_is_reported_as_not_closed(self):
        # Five of six faces: watertight-looking to `refs --facts`, which reports
        # "ok": true and faceCount 5 for exactly this shape.
        result = check_occurrence_shape(Shell(Box(40, 30, 20).faces()[1:]).wrapped)
        self.assertIn(REASON_OPEN_SHELL, result["reasons"])

    def test_an_open_shell_passes_when_surfaces_are_intended(self):
        result = check_occurrence_shape(
            Shell(Box(40, 30, 20).faces()[1:]).wrapped, allow_open=True
        )
        self.assertEqual(result["reasons"], [])

    def test_a_negative_volume_solid_is_reported(self):
        # BRepCheck_Analyzer returns True here -- only the volume sign catches it.
        result = check_occurrence_shape(reversed_box().wrapped)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])
        self.assertLess(result["volumes"][0], 0.0)

    def test_an_inverted_member_inside_a_compound_is_not_masked_by_cancellation(self):
        # The regression pin for aggregate cancellation: +1000 and -1000 sum to
        # zero, so anything reading a compound's total volume sees nothing wrong.
        compound = Compound([Box(10, 10, 10), Pos(30, 0, 0) * reversed_box()])
        result = check_occurrence_shape(compound.wrapped)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])
        self.assertEqual(result["solidCount"], 2)

    def test_two_disjoint_sound_solids_do_not_false_positive(self):
        compound = Compound([Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)])
        result = check_occurrence_shape(compound.wrapped)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["solidCount"], 2)

    def test_a_shape_with_no_solid_is_reported(self):
        result = check_occurrence_shape(Shell(Box(40, 30, 20).faces()[1:]).wrapped)
        self.assertIn(REASON_NO_SOLID, result["reasons"])

    def test_min_volume_threshold_is_respected(self):
        result = check_occurrence_shape(Box(1, 1, 1).wrapped, min_volume=10.0)
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])

    def test_self_intersection_check_can_be_skipped(self):
        result = check_occurrence_shape(
            Box(40, 30, 20).wrapped, check_self_intersection=False
        )
        self.assertEqual(result["reasons"], [])


def _instanced_scene(prototypes):
    """A compound_from_instances scene: ``prototypes`` is a list of
    ``(build123d shape, label, placements)``; each placement is one occurrence."""
    from cadgen.instances import compound_from_instances
    from cadgen.step_export import build_build123d_step_scene

    instances = []
    for shape, label, placements in prototypes:
        shape.label = label
        for index, location in enumerate(placements):
            instances.append((shape, Location(location), f"{label}_{index + 1}"))
    compound = compound_from_instances("rig", instances)
    with tempfile.TemporaryDirectory(prefix="cadgen-validate-") as tempdir:
        return build_build123d_step_scene(compound, Path(tempdir) / "rig.step")


def _occurrences(scene):
    from cadgen.interference import occurrences_from_scene

    return occurrences_from_scene(scene)


class NonRigidPlacementTest(unittest.TestCase):
    """A location is not always rigid, and the placed copy then libels a sound
    body (PR #370 bug record 021). A scale factor leaves the geometry's tolerances behind,
    so ``BRepCheck_Analyzer`` calls the placed shape invalidTopology; a mirror
    has a negative determinant, so the signed volume comes back negative and a
    good solid reports nonPositiveVolume. The body is checked in its own frame.
    """

    @staticmethod
    def _placed(shape, trsf):
        from OCP.TopLoc import TopLoc_Location

        return shape.wrapped.Moved(TopLoc_Location(trsf))

    @staticmethod
    def _scale(factor):
        from OCP.gp import gp_Pnt, gp_Trsf

        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), factor)
        return trsf

    @staticmethod
    def _mirror():
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

        trsf = gp_Trsf()
        trsf.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)))
        return trsf

    def test_a_mirrored_placement_of_a_sound_solid_passes(self):
        result = check_occurrence_shape(self._placed(Box(40, 30, 20), self._mirror()))
        self.assertEqual(result["reasons"], [])
        self.assertAlmostEqual(result["volumes"][0], 24000.0, delta=1.0)

    def test_a_scaled_placement_of_a_sound_solid_passes(self):
        result = check_occurrence_shape(self._placed(Box(40, 30, 20), self._scale(2.0)))
        self.assertNotIn(REASON_INVALID_TOPOLOGY, result["reasons"])
        self.assertEqual(result["reasons"], [])

    def test_a_mirrored_placement_does_not_launder_an_inverted_solid(self):
        # The strip must not turn the sign check into a coin flip: the body is
        # inverted in its own frame, mirrored placement or not.
        result = check_occurrence_shape(self._placed(reversed_box(), self._mirror()))
        self.assertIn(REASON_NON_POSITIVE_VOLUME, result["reasons"])

    def test_a_scaled_placement_does_not_launder_broken_topology(self):
        broken = Compound([Box(10, 10, 10), Shell(Box(4, 4, 4).faces()[1:])])
        placed = check_occurrence_shape(
            self._placed(broken, self._scale(2.0)), check_self_intersection=False
        )
        unplaced = check_occurrence_shape(broken.wrapped, check_self_intersection=False)
        self.assertEqual(sorted(placed["reasons"]), sorted(unplaced["reasons"]))
        self.assertIn(REASON_OPEN_SHELL, placed["reasons"])


class PrototypeDedupTest(unittest.TestCase):
    """Occurrences that share a TShape are one prototype: checked once, reported
    against every placement. The 2,546-occurrence assembly that motivated this
    took 78 minutes checking each placement in turn."""

    def test_placements_of_one_shape_form_one_group_in_tree_order(self):
        scene = _instanced_scene([
            (Box(10, 10, 10), "cube", [(0, 0, 0), (30, 0, 0), (60, 0, 0)]),
            (Box(5, 5, 5), "small", [(0, 40, 0)]),
        ])
        groups = prototype_groups(_occurrences(scene))
        self.assertEqual([len(g.occurrences) for g in groups], [3, 1])
        self.assertEqual([o.ref for o in groups[0].occurrences], ["o1.1", "o1.2", "o1.3"])
        self.assertEqual(groups[0].first.name, "cube_1")

    def test_a_copied_shape_is_its_own_prototype(self):
        # Same geometry, different TShape: dedup is identity, never geometry.
        first, second = Box(10, 10, 10), Box(10, 10, 10)
        scene = _instanced_scene([(first, "a", [(0, 0, 0)]), (second, "b", [(30, 0, 0)])])
        self.assertEqual(len(prototype_groups(_occurrences(scene))), 2)

    def test_an_invariant_finding_names_every_placement(self):
        # The reversed box is checked ONCE and the finding lists all three refs.
        scene = _instanced_scene([
            (reversed_box(), "inverted", [(0, 0, 0), (30, 0, 0), (60, 0, 0)]),
        ])
        [group] = prototype_groups(_occurrences(scene))
        results = check_placements([group.first.shape])
        [finding] = _group_findings(group, results)
        self.assertEqual(finding["ref"], "o1.1")
        self.assertEqual(finding["name"], "inverted_1")
        self.assertIn(REASON_NON_POSITIVE_VOLUME, finding["reasons"])
        self.assertEqual(
            [o["ref"] for o in finding["occurrences"]], ["o1.1", "o1.2", "o1.3"]
        )

    def test_check_placements_repeats_the_invariant_verdict_per_copy(self):
        scene = _instanced_scene([(Box(10, 10, 10), "cube", [(0, 0, 0), (0, 0, 20)])])
        [group] = prototype_groups(_occurrences(scene))
        results = check_placements([o.shape for o in group.occurrences])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["volumes"], results[1]["volumes"])
        self.assertEqual(results[1]["reasons"], [])

    def test_every_placement_splits_findings_by_verdict(self):
        scene = _instanced_scene([(Box(10, 10, 10), "cube", [(0, 0, 0), (0, 0, 20), (0, 0, 40)])])
        [group] = prototype_groups(_occurrences(scene))
        # Pretend the numeric test failed on the middle copy only.
        results = [
            {"solidCount": 1, "volumes": [1000.0], "reasons": []},
            {"solidCount": 1, "volumes": [1000.0], "reasons": [REASON_SELF_INTERSECTING]},
            {"solidCount": 1, "volumes": [1000.0], "reasons": []},
        ]
        [finding] = _group_findings(group, results)
        self.assertEqual(finding["ref"], "o1.2")
        self.assertEqual([o["ref"] for o in finding["occurrences"]], ["o1.2"])

    def test_the_payload_round_trip_checks_every_placement_bit_exactly(self):
        from cadgen._internal.component_package import _shape_brep_bytes

        scene = _instanced_scene([
            (reversed_box(), "inverted", [(0, 0, 0), (30, 0, 0)]),
        ])
        [group] = prototype_groups(_occurrences(scene))
        payload = _shape_brep_bytes(_placed_compound([o.shape for o in group.occurrences]))
        index, results, error = _check_payload_worker((payload, 7, {}))
        self.assertIsNone(error)
        self.assertEqual(index, 7)
        self.assertEqual(len(results), 2)
        direct = check_placements([o.shape for o in group.occurrences])
        self.assertEqual(results, direct)

    def test_every_placement_and_skip_cannot_both_be_asked(self):
        self.assertEqual(_self_intersection_mode(True, False), SELF_INTERSECTION_FIRST_PLACEMENT)
        self.assertEqual(_self_intersection_mode(True, True), SELF_INTERSECTION_EVERY_PLACEMENT)
        self.assertEqual(_self_intersection_mode(False, False), SELF_INTERSECTION_SKIPPED)
        with self.assertRaises(ValueError):
            _self_intersection_mode(False, True)


class InspectValidityDocumentTest(unittest.TestCase):
    """The door end to end on a document with repeated parts: dedup, the report
    additions, the process pool, and the partial document under --out."""

    @classmethod
    def setUpClass(cls):
        from cadgen.step_export import export_build123d_step_file

        cls._tmp = tempfile.TemporaryDirectory(prefix="cadgen-validate-doc-")

        def placed(shape, label, index, location):
            # `.moved()` keeps the TShape, so the written STEP references ONE
            # product per shape and the loaded scene shares its prototype --
            # the layout an assembly of repeated parts has on disk.
            copy = shape.moved(Location(location))
            copy.label = f"{label}_{index + 1}"
            return copy

        good = Box(10, 10, 10)
        # An open shell, not a reversed solid: STEP write/read normalizes
        # orientation, so an inverted body does not survive the round trip a
        # document fixture has to make. Five faces stay five faces.
        bad = Shell(Box(10, 10, 10).faces()[1:])
        children = [placed(good, "cube", i, (i * 30, 0, 0)) for i in range(4)]
        children += [placed(bad, "open", i, (i * 30, 40, 0)) for i in range(3)]
        # Seven more distinct prototypes push the count past the pool threshold.
        children += [placed(Box(4 + i, 4, 4), f"extra{i}", 0, (i * 30, 80, 0)) for i in range(7)]
        cls.document = Path(cls._tmp.name) / "rig.step"
        export_build123d_step_file(Compound(children=children, label="rig"), cls.document)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **kwargs):
        from cadgen.validity import inspect_validity

        previous = os.getcwd()
        os.chdir(self._tmp.name)
        try:
            return inspect_validity(str(self.document), **kwargs)
        finally:
            os.chdir(previous)

    def _assert_report(self, report):
        self.assertFalse(report["ok"])
        self.assertEqual(
            list(report),
            ["ok", "entry", "occurrenceCount", "prototypeCount", "selfIntersectionCheck",
             "failureCount", "parts", "errors"],
        )
        self.assertEqual(report["occurrenceCount"], 14)
        self.assertEqual(report["prototypeCount"], 9)
        self.assertEqual(report["selfIntersectionCheck"], SELF_INTERSECTION_FIRST_PLACEMENT)
        # Three placements of one bad shape: three failing occurrences, ONE finding.
        self.assertEqual(report["failureCount"], 3)
        [finding] = report["parts"]
        self.assertEqual(finding["name"], "open_1")
        self.assertEqual(finding["ref"], "o1.5")
        self.assertEqual([o["ref"] for o in finding["occurrences"]], ["o1.5", "o1.6", "o1.7"])
        self.assertEqual(finding["reasons"], [REASON_OPEN_SHELL, REASON_NO_SOLID])
        self.assertEqual(report["errors"], [])

    def test_in_process_report(self):
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}):
            self._assert_report(self._run())

    def test_the_pool_reports_the_same_document(self):
        # The document carries nothing machine-dependent: pooled and serial
        # runs must write the same bytes.
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "2"}):
            report = self._run()
        self._assert_report(report)
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}):
            serial = self._run()
        self.assertEqual(report, serial)

    def test_out_receives_the_final_document_and_no_partial_marker(self):
        out = Path(self._tmp.name) / "out" / "validate.json"
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}):
            report = self._run(out=out)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written, report)
        self.assertNotIn("partial", written)

    def test_a_killed_run_leaves_a_readable_partial_document(self):
        from cadgen import validity

        out = Path(self._tmp.name) / "partial.json"
        real = validity.check_placements
        seen = {"count": 0}

        def die_on_the_third(shapes, **options):
            seen["count"] += 1
            if seen["count"] == 3:
                raise KeyboardInterrupt  # what a Ctrl-C or a lost worker looks like here
            return real(shapes, **options)

        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}), \
                mock.patch.object(validity, "check_placements", die_on_the_third):
            with self.assertRaises(KeyboardInterrupt):
                self._run(out=out)
        partial = json.loads(out.read_text(encoding="utf-8"))
        self.assertIs(partial["partial"], True)
        self.assertFalse(partial["ok"])
        self.assertEqual(partial["checkedPrototypeCount"], 2)
        self.assertEqual(partial["prototypeCount"], 9)
        self.assertEqual(list(partial)[:3], ["ok", "partial", "checkedPrototypeCount"])

    def test_every_placement_runs_the_numeric_test_per_copy(self):
        from cadgen import validity

        calls = []
        real = validity._is_self_intersecting

        def counting(shape):
            calls.append(shape)
            return real(shape)

        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}), \
                mock.patch.object(validity, "_is_self_intersecting", counting):
            report = self._run(every_placement=True)
        self.assertEqual(report["selfIntersectionCheck"], SELF_INTERSECTION_EVERY_PLACEMENT)
        self.assertEqual(len(calls), 14, "every placed copy gets the numeric test")
        self.assertEqual(report["failureCount"], 3)

    def test_refs_select_before_grouping(self):
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}):
            report = self._run(refs=["o1.5", "o1.6"])
        self.assertEqual(report["occurrenceCount"], 2)
        self.assertEqual(report["prototypeCount"], 1)
        self.assertEqual(report["failureCount"], 2)


if __name__ == "__main__":
    unittest.main()
