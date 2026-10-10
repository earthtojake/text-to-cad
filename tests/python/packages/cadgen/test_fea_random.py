"""Random vibration (``random_vibration``): the study it takes, the PSD arithmetic, and a cantilever against Miles.

The beam is a build123d box written to a temporary STEP: 100 mm long, 6 x 6 mm
steel, clamped at x = 0 and shaken along Z by a flat PSD of P g²/Hz from 20 to
1000 Hz. Its first mode f1 (about 490 Hz) answers like one mass on a spring,
so Miles' equation gives the tip's RMS motion relative to the clamp:
x_rms ≈ 1.566 · g0 · sqrt(π/2 · f1 · Q · P) / ω1², Q = 1/(2ζ), 1.566 the
cantilever's first-mode participation at the tip (spec section 13, 15 %). The
input's g rms is the PSD's area, exact.

Parse and PSD tests need no mesh; the beam needs the fea extra.
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
from types import SimpleNamespace

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

LENGTH, SIDE = 100.0, 6.0
G0 = 9806.65
ZETA = 0.02
P = 0.04
FIXED = "#o1.f1"
SPEC_TABLE = [[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]


def _study(**more) -> dict:
    return {"analysis": "random_vibration", "material": "steel", "fixtures": [{"faces": [FIXED]}],
            "psd": {"direction": [0, 0, 1], "table": [[20, P], [1000, P]]}, "damping_ratio": ZETA, **more}


class StudyFile(unittest.TestCase):
    def test_it_reads_the_psd_damping_and_sigma(self):
        parsed = parse_study(_study(psd={"direction": [0, 0, 2], "table": SPEC_TABLE}, sigma=1))
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.direction, inputs.sigma, inputs.damping_ratio), ("random_vibration", (0.0, 0.0, 1.0), 1, ZETA))
        self.assertEqual((inputs.table[1], inputs.band_Hz, inputs.top_Hz), ((80.0, 0.04), (20.0, 2000.0), 3000.0))
        self.assertEqual((inputs.anchor_refs, inputs.requires_anchor), ((FIXED,), True))
        # Judged at 3σ on strength unless the study says otherwise.
        defaults = parse_study(_study())
        self.assertEqual((defaults.inputs.sigma, defaults.checks), (3, ({"kind": "stress"},)))

    def test_what_is_wrong_is_said_in_plain_words(self):
        for bad, words in (
            ({"psd": None}, "the random shake"),
            ({"psd": {"direction": [0, 0, 1]}}, "at least two rows"),
            ({"psd": {"table": SPEC_TABLE}}, "direction it is shaken along"),
            ({"psd": {"direction": [0, 0, 0], "table": SPEC_TABLE}}, "direction is zero"),
            ({"psd": {"direction": [0, 0, 1], "table": SPEC_TABLE, "grms": 6}}, "unknown keys"),
            ({"psd": {"direction": [0, 0, 1], "table": [[20, 0.01], [10, 0.01]]}}, "must rise"),
            ({"psd": {"direction": [0, 0, 1], "table": [[20, 0.01], [100, 0]]}}, "must be > 0"),
            ({"psd": {"direction": [0, 0, 1], "table": [[20, 0.01], 100]}}, r"\[Hz, g²/Hz\]"),
            ({"sigma": 2}, "1 or 3"),
            ({"sigma": True}, "1 or 3"),
            ({"damping_ratio": 1.5}, "must be under 1"),
            ({"fixtures": []}, "at least one"),
            ({"loads": []}, "unknown keys"),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study({**_study(), **bad})

    def test_it_takes_stress_and_displacement_checks_and_a_sigma_control(self):
        parsed = parse_study(_study(view={
            "checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}],
            "presets": [{"label": "Typical", "sigma": 1}]}))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "displacement"])
        self.assertEqual(parsed.view["presets"], [{"label": "Typical", "sigma": 1}])
        with self.assertRaisesRegex(ValueError, "not a check this cadgen makes"):
            parse_study(_study(view={"checks": [{"kind": "acceleration", "limit_g": 10}]}))
        with self.assertRaisesRegex(ValueError, "not one of"):
            parse_study(_study(view={"controls": [{"drives": "frame", "type": "number"}]}))


class Psd(unittest.TestCase):
    def test_the_input_g_rms_is_the_area_under_the_log_log_table(self):
        from cadgen._internal.fea.analyses.random_vibration import grms, psd_at

        self.assertAlmostEqual(grms([(20, P), (1000, P)]), math.sqrt(P * 980), places=12)
        # Any other slope: S0 f0 ((f1/f0)^(s+1) - 1)/(s + 1), here -6 dB/oct (s = -2).
        self.assertAlmostEqual(grms([(100, 0.04), (200, 0.01)]) ** 2, 0.04 * 100 / -1 * ((200 / 100) ** -1 - 1), places=12)
        # The spec's profile by hand: +3 dB/oct (slope 1, S0 f0 ((f1/f0)² - 1)/2), flat, then slope -1 (S0 f0 ln(f1/f0)).
        rising = 0.01 * 20 / 2 * ((80 / 20) ** 2 - 1)
        flat = 0.04 * (350 - 80)
        falling = 0.04 * 350 * math.log(2000 / 350)
        self.assertAlmostEqual(grms(SPEC_TABLE), math.sqrt(rising + flat + falling), places=9)
        self.assertAlmostEqual(grms(SPEC_TABLE), 6.058, delta=5e-4)
        # Straight lines on log-log axes between rows, nothing outside the table.
        values = psd_at(SPEC_TABLE, [10, 20, 40, 80, 200, 2000, 2500])
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 0.0)
        for got, want in zip(values[1:6], (0.01, 0.02, 0.04, 0.04, 0.007)):
            self.assertAlmostEqual(got, want, delta=1e-12)

    def test_one_mode_answers_as_miles_says(self):
        import numpy as np

        from cadgen._internal.fea.analyses.random_vibration import modal_covariance, psd_at, response_grid

        fn = 300.0
        table = [(10, P), (5000, P)]
        grid = response_grid(table, ZETA)
        # 40 points across a half-power bandwidth: a log step of 2ζ/40.
        self.assertAlmostEqual(math.log(grid[1] / grid[0]), 2 * ZETA / 40, delta=1e-6)
        C0, C2 = modal_covariance(np.array([2 * math.pi * fn]), np.array([1.0]), grid, psd_at(table, grid) * G0 ** 2, ZETA)
        miles = G0 * math.sqrt(math.pi / 2 * fn / (2 * ZETA) * P) / (2 * math.pi * fn) ** 2
        self.assertAlmostEqual(math.sqrt(C0[0, 0]) / miles, 1.0, delta=0.005)
        # A lightly damped mode swings through zero at its own frequency.
        self.assertAlmostEqual(math.sqrt(C2[0, 0] / C0[0, 0]) / fn, 1.0, delta=0.01)

    def test_von_mises_rms_is_segalmans_quadratic_form(self):
        import numpy as np

        from cadgen._internal.fea.analyses.random_vibration import rms_displacement, rms_von_mises

        rng = np.random.default_rng(7)
        L = rng.standard_normal((3, 3))
        C = L @ L.T                                   # a modal covariance
        stresses = rng.standard_normal((3, 6, 5))     # three modes' stress at five nodes
        shapes = rng.standard_normal((3, 5, 3))
        # Against sampling: Gaussian modal coordinates with covariance C, von Mises squared averaged.
        q = rng.multivariate_normal(np.zeros(3), C, size=200_000)
        s = np.einsum("ti,ikn->tkn", q, stresses)
        xx, yy, zz, xy, yz, xz = (s[:, k] for k in range(6))
        vm2 = 0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy ** 2 + yz ** 2 + xz ** 2)
        np.testing.assert_allclose(rms_von_mises(stresses, C), np.sqrt(vm2.mean(axis=0)), rtol=0.01)
        u = np.einsum("ti,inc->tnc", q, shapes)
        np.testing.assert_allclose(rms_displacement(shapes, C), np.sqrt((u ** 2).sum(axis=2).mean(axis=0)), rtol=0.01)
        # One mode in uniaxial tension: its RMS is the stress per unit coordinate times the coordinate's RMS.
        tension = np.zeros((1, 6, 1))
        tension[0, 0, 0] = 5.0
        self.assertAlmostEqual(float(rms_von_mises(tension, np.array([[4.0]]))[0]), 10.0, places=12)


class Ladder(unittest.TestCase):
    def test_it_declares_its_ladder(self):
        self.assertEqual(get_analysis("random_vibration").ladder,
                         ("reduce_modes", "adaptive_steps", "iterative", "local_refine", "defeature", "linear_elements", "symmetry"))

    def test_each_own_rung_is_taken_once(self):
        from cadgen._internal.fea.fit import FitPlan

        analysis = get_analysis("random_vibration")
        inputs = parse_study(_study()).inputs
        ctx = SimpleNamespace(plan=FitPlan(), budget=None)
        step = analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual((step.rung, ctx.plan.modes), ("reduce_modes", 6))
        self.assertIn("90% of the mass moving along Z", step.words)
        self.assertIsNone(analysis.apply("reduce_modes", ctx, inputs))
        grid = analysis.apply("adaptive_steps", ctx, inputs)
        self.assertTrue(ctx.plan.adaptive_steps)
        self.assertIn("coarser frequency grid, 10 points across each resonance instead of 40", grid.words)
        self.assertIn("on the coarser grid", grid.accuracy)
        self.assertLess(grid.accuracy_pct, 1.0)
        self.assertIsNone(analysis.apply("adaptive_steps", ctx, inputs))
        for rung in ("idealise", "symmetry"):
            self.assertIsNone(analysis.apply(rung, ctx, inputs))


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ShakenAtRandom(unittest.TestCase):
    """The clamped beam under a flat 0.04 g²/Hz from 20 to 1000 Hz along Z, judged at 3σ."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(cls.step))
        cls.fixed, cls.tip = _ends(fea.faces(cls.step))
        cls.study = _study(fixtures=[{"faces": [cls.fixed]}], mesh={"size_mm": 2.0}, view={"checks": [
            {"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.05, "faces": [cls.tip], "label": "Tip"}]})
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "beam.fea.glb", study=cls.study)
        cls.summary = cls.result.summary
        cls.f1 = cls.summary["modes"][0]["frequency_Hz"]
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _miles(self) -> float:
        omega1 = 2 * math.pi * self.f1
        return 1.566 * G0 * math.sqrt(math.pi / 2 * self.f1 / (2 * ZETA) * P) / omega1 ** 2

    def test_the_tip_moves_as_miles_says_and_the_input_is_exact(self):
        self.assertAlmostEqual(self.summary["grms_input"], round(math.sqrt(P * 980), 6), places=9)
        self.assertAlmostEqual(self.summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)
        self.assertAlmostEqual(self.summary["max_displacement_rms_mm"] / self._miles(), 1.0, delta=0.15)
        self.assertAlmostEqual(self.summary["max_displacement_mm"], 3 * self.summary["max_displacement_rms_mm"], delta=1e-6)
        # One mode carries it: the stress swings through zero near f1, and mode 1 holds the stress.
        self.assertAlmostEqual(self.summary["zero_crossing_Hz"] / self.f1, 1.0, delta=0.05)
        self.assertGreater(self.summary["modes"][0]["stress_share"] + self.summary["modes"][1]["stress_share"], 0.95)

    def test_the_checks_judge_three_sigma(self):
        stress, tip = self.summary["checks"]
        self.assertEqual((stress["label"], stress["status"]), ("Random vibration", "passes"))
        self.assertAlmostEqual(stress["value"], 3 * self.summary["max_von_mises_rms_MPa"], delta=1e-3)
        self.assertAlmostEqual(stress["value"], self.summary["max_von_mises_MPa"], delta=1e-3)
        self.assertEqual((tip["kind"], tip["label"], tip["faces"], tip["unit"]), ("displacement", "Tip", [self.tip], "mm"))
        self.assertAlmostEqual(tip["value"], self.summary["max_displacement_mm"], delta=1e-5)
        self.assertEqual(tip["status"], "fails" if tip["value"] > 0.05 else "close" if tip["value"] > 0.045 else "passes")
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertTrue(found["random_response"]["summary"].startswith("Shaken at random at 6.26 g rms along Z, its stress is"))
        self.assertIn("mode 1 at 490 Hz carries", found["random_response"]["summary"])

    def test_the_glb_carries_the_rms_fields_and_the_psd(self):
        gltf, _ = _glb(self.result.glb)
        extras = gltf["meshes"][0]["extras"]
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(extras["analysis"]["type"], "random_vibration")
        self.assertEqual([(f["field"], f["attribute"]) for f in extras["fields"]],
                         [("von_mises_rms", "_VON_MISES_RMS"), ("displacement_rms", "_DISPLACEMENT_RMS")])
        for field in extras["fields"]:
            self.assertEqual(gltf["accessors"][attributes[field["attribute"]]]["type"], "SCALAR")
        self.assertNotIn("series", extras)
        self.assertEqual(extras["study"]["psd"], {"direction": [0.0, 0.0, 1.0], "table": [[20.0, P], [1000.0, P]],
                                                  "grms": round(math.sqrt(P * 980), 6)})
        self.assertEqual((extras["study"]["sigma"], extras["study"]["damping_ratio"]), (3, ZETA))
        self.assertEqual(extras["grms_input"], self.summary["grms_input"])

    def test_the_sidecar_and_the_cli_lines(self):
        self.assertEqual((self.sidecar["analysis"], sorted(self.sidecar["curves"])),
                         ("random_vibration", ["displacement_psd_mm2_Hz", "input_psd_g2_Hz", "stress_psd_MPa2_Hz"]))
        curve = self.sidecar["curves"]["input_psd_g2_Hz"]
        self.assertEqual((curve["x"][0], curve["x"][-1], curve["y"][0], curve["y_unit"]), (20.0, 1000.0, P, "g²/Hz"))
        lines = self.result.human_lines()
        self.assertIn("(random_vibration)", lines[0])
        self.assertEqual(lines[1], "shaken at random, 6.26 g rms along Z from 20 to 1000 Hz, 2% damping; judged at 3σ")
        self.assertTrue(lines[3].startswith("2 modes up to 1500 Hz, holding"))

    def test_an_oversized_model_completes_with_fewer_modes_and_a_coarser_grid(self):
        from cadgen import fea

        study = {**self.study, "fit": {"memory_GB": 0.01, "allow": ["reduce_modes", "adaptive_steps"]}}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "tight.fea.glb", study=study)
        self.assertTrue(result.ok)
        self.assertEqual([step["rung"] for step in result.fit][:2], ["reduce_modes", "adaptive_steps"])
        words = "Kept 1 of the 2 modes up to 1500 Hz, the ones holding 61% of the mass moving along Z, to fit"
        self.assertEqual(result.fit[0]["words"], words)
        self.assertIsNotNone(result.fit[1]["accuracy"])
        self.assertEqual((result.summary["modes_used"], result.summary["points_per_bandwidth"]), (1, 10))
        gltf, _ = _glb(result.glb)
        self.assertIn(words, [step["words"] for step in gltf["meshes"][0]["extras"]["fit"]])
        self.assertIn(words, [step["words"] for step in json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"]])
        self.assertIn(f"adapted: {words}", result.human_lines())
        self.assertTrue({"fit_reduce_modes", "fit_adaptive_steps"} <= {finding["type"] for finding in result.findings})
        # The mode that carries the shake is kept, on a grid that still resolves it: Miles still holds.
        self.assertAlmostEqual(result.summary["max_displacement_rms_mm"] / self._miles(), 1.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()
