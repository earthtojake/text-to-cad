"""Drop (estimate): G from the height and how it stops, and a solve that is exactly a static study.

A part dropped h that stops over d decelerates at G = h / d; one that stops in
τ along a half-sine peaks at π v / (2 τ), v = √(2 g h). The solve holds the
landing faces and loads the part with G g toward them, so it must equal, to the
last bit, a static study with those faces fixed and an ``acceleration`` of G g
away from the floor. The block is a build123d box written to a temporary STEP.
"""

from __future__ import annotations

import io
import json
import math
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

G0 = 9806.65
LINE = ("Estimate: 1 m drop stopping in 2 mm, 500 g equivalent static load; "
        "not an impact simulation (analysis impact simulates the impact)")


def _study(**drop) -> dict:
    return {"analysis": "drop", "material": "abs", "drop": {"height_mm": 1000, "onto": ["#o1.f5"], **drop}}


class Parse(unittest.TestCase):
    def parse(self, document):
        from cadgen._internal.fea.study import parse_study

        return parse_study(document)

    def error(self, document) -> str:
        with self.assertRaises(ValueError) as caught:
            self.parse(document)
        return str(caught.exception)

    def test_g_is_height_over_stopping_distance_exactly(self):
        study = self.parse(_study(stop_mm=2))
        self.assertEqual(study.inputs.G, 500.0)
        self.assertEqual(study.fixtures[0].faces, ("#o1.f5",))
        self.assertEqual(study.inputs.anchor_refs, ("#o1.f5",))
        self.assertEqual(study.checks, ({"kind": "stress", "label": "Drop"},))

    def test_a_half_sine_stop_peaks_at_pi_v_over_two_tau(self):
        study = self.parse(_study(impact_ms=1.5))
        speed = math.sqrt(2 * G0 * 1000.0)
        self.assertAlmostEqual(study.inputs.G, math.pi * speed / (2 * 1.5e-3) / G0, places=9)
        from cadgen._internal.fea.analyses.drop import estimate_line

        self.assertEqual(estimate_line(1000.0, study.inputs.G, impact_ms=1.5),
                         "Estimate: 1 m drop stopping in 1.5 ms (half-sine), 473 g peak equivalent static load; "
                         "not an impact simulation (analysis impact simulates the impact)")

    def test_the_estimate_line_says_what_was_assumed(self):
        from cadgen._internal.fea.analyses.drop import estimate_line

        self.assertEqual(estimate_line(1000.0, 500.0, stop_mm=2.0), LINE)
        self.assertTrue(estimate_line(500.0, 250.0, stop_mm=2.0).startswith("Estimate: 500 mm drop stopping in 2 mm, 250 g"))

    def test_a_given_direction_is_the_way_it_falls(self):
        study = self.parse(_study(stop_mm=4, direction=[0, 0, -2]))
        self.assertEqual(study.inputs.direction, (0.0, 0.0, -1.0))
        self.assertEqual(study.loads[0].vector_g, (0.0, 0.0, 250.0))

    def test_plain_errors_name_what_to_add(self):
        for document, fragment in (
            (_study(), "exactly one of stop_mm"),
            (_study(stop_mm=2, impact_ms=1), "exactly one of stop_mm"),
            ({"analysis": "drop", "material": "abs", "drop": {"onto": ["#o1.f5"], "stop_mm": 2}}, "drop.height_mm"),
            ({"analysis": "drop", "material": "abs", "drop": {"height_mm": 10, "stop_mm": 2}}, "drop.onto"),
            (_study(stop_mm=0), "drop.stop_mm: must be > 0"),
            (_study(stop_mm=2, direction=[0, 0, 0]), "the direction is zero"),
            (_study(stop_mm=2, floor="rigid"), "unknown keys ['floor']"),
            (_study(stop_mm=2, dynamic="yes"), "drop.dynamic: true or false"),
            ({"analysis": "drop", "material": "abs", "drop": {"height_mm": 10, "onto": ["#o1.f5"], "stop_mm": 2},
              "fixtures": []}, "drop studies take"),
            ({"analysis": "drop", "material": {"E_MPa": 2000, "nu": 0.3, "yield_MPa": 40}, "drop": {"height_mm": 10,
              "onto": ["#o1.f5"], "stop_mm": 2}}, "need the density"),
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.error(document))
        # dynamic false is the estimate itself; true adds the transient check.
        self.assertEqual(self.parse(_study(stop_mm=2, dynamic=False)).inputs.G, 500.0)
        self.assertTrue(self.parse(_study(stop_mm=2, dynamic=True)).inputs.dynamic)

    def test_the_dynamic_pulse_has_the_estimate_s_peak_and_the_impact_s_speed_change(self):
        from cadgen._internal.fea.analyses.drop import pulse_s

        # A half-sine of peak G g changes the speed by (2/π) G g τ: the impact speed √(2 g h) sets τ.
        for study in (_study(impact_ms=1.5), _study(stop_mm=2)):
            G = self.parse(study).inputs.G
            tau = pulse_s(1000.0, G)
            self.assertAlmostEqual(2 / math.pi * G * G0 * tau, math.sqrt(2 * G0 * 1000.0), places=6)
        self.assertAlmostEqual(pulse_s(1000.0, self.parse(_study(impact_ms=1.5)).inputs.G), 1.5e-3, places=12)


def _extras(glb: Path) -> tuple[dict, bytes]:
    raw = glb.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])["meshes"][0]["extras"], raw[20 + length:]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Solve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "block.step"
        export_step(Box(30, 20, 10), str(step))
        planes = {face.center_mm[2]: face.ref for face in fea.faces(step).faces if face.surface == "plane"}
        cls.bottom = planes[min(planes)]
        cls.volume = 30 * 20 * 10
        with redirect_stderr(io.StringIO()):
            cls.drop = fea.solve(step, directory / "drop.glb", study={
                "analysis": "drop", "material": "abs", "mesh": {"size_mm": 5},
                "drop": {"height_mm": 1000, "onto": [cls.bottom], "stop_mm": 2},
            })
            cls.static = fea.solve(step, directory / "static.glb", study={
                "material": "abs", "mesh": {"size_mm": 5}, "fixtures": [{"faces": [cls.bottom]}],
                "loads": [{"type": "acceleration", "vector_g": [0, 0, 500]}],
            })
            # A budget far under the model: it completes by static's ladder, here its local refinement.
            cls.fitted = fea.solve(step, directory / "fitted.glb", study={
                "analysis": "drop", "material": "abs", "mesh": {"size_mm": 1.5},
                "fit": {"memory_GB": 0.05, "seconds": 0.5, "allow": ["local_refine"]},
                "drop": {"height_mm": 1000, "onto": [cls.bottom], "stop_mm": 2},
            })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_is_exactly_the_static_study_with_that_acceleration(self):
        for key, value in self.static.summary.items():
            if key != "checks":
                self.assertEqual(self.drop.summary[key], value, key)
        drop_extras, drop_bin = _extras(self.drop.glb)
        static_extras, static_bin = _extras(self.static.glb)
        # Every attribute, to the bit: positions, stress, displacement, faces.
        self.assertEqual(drop_bin, static_bin)
        # The same fields and ranges; a non-static result also names each field's view.
        self.assertEqual([{k: v for k, v in entry.items() if k != "field"} for entry in drop_extras["fields"]], static_extras["fields"])
        weight = 1.04e-9 * self.volume * G0 * 500
        self.assertAlmostEqual(-self.drop.summary["applied_force_N"][2] / weight, 1.0, delta=1e-3)

    def test_it_falls_along_the_landing_faces_outward_normal(self):
        self.assertEqual(self.drop.summary["drop"]["direction"], [0.0, 0.0, -1.0])
        self.assertEqual(self.drop.summary["drop"]["acceleration_g"], [0.0, 0.0, 500.0])
        self.assertAlmostEqual(self.drop.summary["drop"]["impact_speed_m_s"], math.sqrt(2 * 9.80665), places=3)

    def test_it_says_estimate_everywhere(self):
        self.assertTrue(self.drop.summary["estimate"])
        self.assertEqual(self.drop.summary["estimate_line"], LINE)
        self.assertIn(LINE, self.drop.human_lines())
        extras, _ = _extras(self.drop.glb)
        self.assertEqual({k: extras["analysis"][k] for k in ("type", "tier", "estimate", "noun")},
                         {"type": "drop", "tier": 2, "estimate": True, "noun": "this drop"})
        self.assertTrue(any("not an impact simulation" in line for line in extras["analysis"]["limits"]))
        sidecar = json.loads(self.drop.sidecar.read_text(encoding="utf-8"))
        self.assertTrue(sidecar["estimate"])
        self.assertEqual(sidecar["analysis"], "drop")
        estimate = [finding for finding in self.drop.findings if finding["type"] == "drop_estimate"]
        self.assertEqual(len(estimate), 1)
        self.assertIn("not an impact simulation", estimate[0]["summary"])
        self.assertEqual(estimate[0]["description"], LINE)

    def test_an_oversized_drop_completes_through_static_s_ladder(self):
        self.assertTrue(self.fitted.ok)
        rungs = [step["rung"] for step in self.fitted.fit]
        self.assertIn("local_refine", rungs)
        refined = self.fitted.fit[rungs.index("local_refine")]
        self.assertTrue(refined["accuracy"])
        lines = self.fitted.human_lines()
        self.assertIn(LINE, lines)
        self.assertIn(f"adapted: {refined['words']} ({refined['accuracy']})", lines)
        self.assertEqual([step["rung"] for step in json.loads(self.fitted.sidecar.read_text(encoding="utf-8"))["fit"]], rungs)

    def test_the_check_is_labelled_drop_and_the_study_echoes_the_drop(self):
        extras, _ = _extras(self.drop.glb)
        self.assertEqual([(check["kind"], check["label"]) for check in extras["checks"]], [("stress", "Drop")])
        self.assertEqual(extras["study"]["drop"], {"height_mm": 1000.0, "onto": [self.bottom], "stop_mm": 2.0,
                                                   "direction": [0.0, 0.0, -1.0], "G": 500.0})
        self.assertEqual(extras["study"]["fixtures"], [{"type": "fixed", "faces": [self.bottom]}])
        self.assertEqual(extras["study"]["loads"], [{"type": "acceleration", "vector_g": [0.0, 0.0, 500.0]}])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Dynamic(unittest.TestCase):
    """``"dynamic": true``: the transient check with a half-sine pulse, and the larger response reported.

    A squat block rings far faster than a 1.5 ms pulse, so it answers the pulse as the steady load: the estimate
    governs. A 100 mm steel arm held at its root and landing sideways rings at 490 Hz, close to a 1.6 ms pulse
    (f τ = 0.78), where a half-sine overshoots: about 1.77× for a single undamped mode, a little less with 2 %
    damping and the higher modes answering steadily. The transient governs, reported as the equivalent steady load.
    """

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        block = directory / "block.step"
        export_step(Box(30, 20, 10), str(block))
        planes = {face.center_mm[2]: face.ref for face in fea.faces(block).faces if face.surface == "plane"}
        arm = directory / "arm.step"
        export_step(Box(100, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(arm))
        ends = {face.center_mm[0]: face.ref for face in fea.faces(arm).faces
                if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
        cls.root = ends[min(ends)]
        drop = {"height_mm": 20, "onto": [cls.root], "impact_ms": 1.6, "direction": [0, 0, -1]}
        with redirect_stderr(io.StringIO()):
            cls.block = fea.solve(block, directory / "block.glb", study={
                "analysis": "drop", "material": "abs", "mesh": {"size_mm": 5},
                "drop": {"height_mm": 1000, "onto": [planes[min(planes)]], "impact_ms": 1.5, "dynamic": True},
            })
            cls.estimate = fea.solve(arm, directory / "estimate.glb", study={
                "analysis": "drop", "material": "steel", "mesh": {"size_mm": 3}, "drop": drop})
            cls.arm = fea.solve(arm, directory / "arm.glb", study={
                "analysis": "drop", "material": "steel", "mesh": {"size_mm": 3}, "drop": {**drop, "dynamic": True}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_part_stiffer_than_the_pulse_answers_it_as_the_steady_load(self):
        dynamic = self.block.summary["dynamic"]
        self.assertEqual((dynamic["pulse_ms"], dynamic["governs"]), (1.5, False))
        self.assertGreater(dynamic["first_mode_Hz"], 10 * 1000 / dynamic["pulse_ms"])
        self.assertAlmostEqual(dynamic["factor"], 1.0, delta=0.05)
        self.assertEqual(dynamic["G_reported"], self.block.summary["drop"]["G"])
        self.assertIn("drop_dynamic", [finding["type"] for finding in self.block.findings])
        self.assertTrue(self.block.human_lines()[2].startswith("Dynamic check: a 1.5 ms half-sine pulse"))

    def test_a_part_ringing_near_the_pulse_reports_the_larger_transient_peak(self):
        dynamic = self.arm.summary["dynamic"]
        self.assertTrue(dynamic["governs"])
        self.assertAlmostEqual(dynamic["first_mode_Hz"], 490, delta=15)
        self.assertTrue(1.4 < dynamic["factor"] < 1.8, dynamic["factor"])
        # Reported as the static solve at the equivalent load: the estimate's numbers times the factor.
        G = self.arm.summary["drop"]["G"]
        self.assertAlmostEqual(dynamic["G_reported"], G * dynamic["factor"], delta=1e-3 * G)
        self.assertEqual(self.arm.summary["drop"]["acceleration_g"], [0.0, 0.0, round(dynamic["G_reported"], 4)])
        ratio = self.arm.summary["max_von_mises_MPa"] / self.estimate.summary["max_von_mises_MPa"]
        self.assertAlmostEqual(ratio, dynamic["factor"], delta=1e-3)
        self.assertAlmostEqual(self.arm.summary["max_von_mises_MPa"] / dynamic["max_von_mises_MPa"], 1.0, delta=0.05)
        extras, _ = _extras(self.arm.glb)
        self.assertTrue(extras["study"]["drop"]["dynamic"])
        self.assertIn("the transient governs, reported as an equivalent", self.arm.human_lines()[2])


if __name__ == "__main__":
    unittest.main()
