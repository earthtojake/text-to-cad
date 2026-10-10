"""Shock (``shock``): the study it takes, the spectrum and the combination rules, and a shocked cantilever against theory.

The beam is a build123d box written to a temporary STEP: 100 mm long, 6 x 6 mm
steel, clamped at x = 0 and shocked along Z by a spectrum that is 50 g above
100 Hz. Its first bending mode f1 (about 490 Hz) carries the shock: alone, its
tip moves relative to the clamp by 1.566·S_a(f1)/ω1², 1.566 being the
cantilever's first-mode participation at the tip (spec section 13, 10 %). The
second bending mode (about 3 kHz, 6.3 times higher) is well separated, so CQC
and SRSS agree within 1 %.

Parse, spectrum and combination tests need no mesh; the beam needs the fea extra.
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
FIXED = "#o1.f1"
TABLE = [[10, 5], [100, 50], [4000, 50]]


def _study(**more) -> dict:
    return {"analysis": "shock", "material": "steel", "fixtures": [{"faces": [FIXED]}],
            "srs": {"direction": [0, 0, 1], "table": TABLE, "damping_ratio": 0.05}, **more}


class StudyFile(unittest.TestCase):
    def test_it_reads_the_spectrum_its_damping_and_the_combination(self):
        parsed = parse_study(_study(srs={"direction": [0, 0, 2], "table": TABLE}))
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.direction, inputs.damping_ratio, inputs.combination),
                         ("shock", (0.0, 0.0, 1.0), 0.05, "srss"))
        self.assertEqual((inputs.table, inputs.top_Hz), (((10.0, 5.0), (100.0, 50.0), (4000.0, 50.0)), 4000.0))
        self.assertEqual((inputs.anchor_refs, inputs.requires_anchor), ((FIXED,), True))
        # With no view, the shock is judged on strength, labelled "Shock".
        self.assertEqual(parsed.checks, ({"kind": "stress", "label": "Shock"},))
        self.assertEqual(parse_study(_study(combination="cqc")).inputs.combination, "cqc")

    def test_what_is_wrong_is_said_in_plain_words(self):
        for bad, words in (
            ({"srs": None}, "response spectrum"),
            ({"srs": {"table": TABLE}}, "direction of the shock"),
            ({"srs": {"direction": [0, 0, 0], "table": TABLE}}, "direction is zero"),
            ({"srs": {"direction": [0, 0, 1], "table": [[10, 5]]}}, "at least two"),
            ({"srs": {"direction": [0, 0, 1], "table": [[100, 5], [10, 50]]}}, "must rise"),
            ({"srs": {"direction": [0, 0, 1], "table": [[10, 5], [100, -1]]}}, "must be > 0"),
            ({"srs": {"direction": [0, 0, 1], "table": [[10, 5, 1], [100, 5]]}}, r"\[frequency Hz, peak g\]"),
            ({"srs": {"direction": [0, 0, 1], "table": TABLE, "damping_ratio": 1.2}}, "must be under 1"),
            ({"srs": {"direction": [0, 0, 1], "table": TABLE, "q": 10}}, "unknown keys"),
            ({"combination": "abs"}, "is not one of"),
            ({"fixtures": []}, "at least one"),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study({**_study(), **bad})

    def test_it_takes_stress_and_displacement_checks_only(self):
        parsed = parse_study(_study(view={"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}]}))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "displacement"])
        with self.assertRaisesRegex(ValueError, "not a check this cadgen makes"):
            parse_study(_study(view={"checks": [{"kind": "acceleration", "limit_g": 10}]}))


class Ladder(unittest.TestCase):
    def test_it_declares_the_spec_ladder(self):
        self.assertEqual(get_analysis("shock").ladder,
                         ("reduce_modes", "iterative", "local_refine", "defeature", "linear_elements", "symmetry"))

    def test_reduce_modes_keeps_fewer_modes_once(self):
        from cadgen._internal.fea.fit import FitPlan

        analysis = get_analysis("shock")
        inputs = parse_study(_study()).inputs
        ctx = SimpleNamespace(plan=FitPlan(), budget=None)
        step = analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual((step.rung, ctx.plan.modes), ("reduce_modes", 6))
        self.assertIn("90% of the mass moving along Z", step.words)
        self.assertIsNone(analysis.apply("reduce_modes", ctx, inputs))
        for rung in ("idealise", "symmetry"):
            self.assertIsNone(analysis.apply(rung, ctx, inputs))


class Spectrum(unittest.TestCase):
    def test_it_is_read_log_log_and_held_at_its_ends(self):
        from cadgen._internal.fea.analyses.shock import spectrum_g

        table = ((10.0, 5.0), (100.0, 50.0), (4000.0, 50.0))
        # Halfway in log frequency between 5 g and 50 g is their geometric mean.
        self.assertAlmostEqual(spectrum_g(table, math.sqrt(10 * 100)), math.sqrt(5 * 50), places=9)
        self.assertAlmostEqual(spectrum_g(table, 490.0), 50.0, places=9)
        self.assertAlmostEqual(spectrum_g(table, 2.0), 5.0, places=9)
        self.assertAlmostEqual(spectrum_g(table, 9000.0), 50.0, places=9)
        self.assertEqual([round(g, 9) for g in spectrum_g(table, [10.0, 100.0])], [5.0, 50.0])

    def test_it_is_said_in_a_line(self):
        from cadgen._internal.fea.analyses.shock import spectrum_words

        self.assertEqual(spectrum_words(((10, 5), (100, 50), (2000, 50)), (0, 0, 1), 0.05), "50 g above 100 Hz along Z, 5% damping")
        self.assertEqual(spectrum_words(((10, 5), (400, 30), (2000, 10)), (1, 0, 0), 0.05), "up to 30 g at 400 Hz along X, 5% damping")
        self.assertEqual(spectrum_words(((10, 50), (2000, 50)), (0, 1, 0), 0.03), "50 g from 10 to 2000 Hz along Y, 3% damping")


class Combination(unittest.TestCase):
    def test_the_der_kiureghian_coefficients(self):
        import numpy as np

        from cadgen._internal.fea.analyses.shock import cqc_coefficients

        zeta = 0.05
        omega = 2 * math.pi * np.array([100.0, 105.0, 1000.0])
        rho = cqc_coefficients(omega, zeta)
        np.testing.assert_allclose(np.diag(rho), 1.0)
        np.testing.assert_allclose(rho, rho.T, rtol=1e-12)
        # Equal damping: ρ = 8ζ²(1 + r) r^{3/2} / ((1 − r²)² + 4ζ² r (1 + r)²).
        r = 1.05
        self.assertAlmostEqual(rho[0, 1], 8 * zeta ** 2 * (1 + r) * r ** 1.5 / ((1 - r ** 2) ** 2 + 4 * zeta ** 2 * r * (1 + r) ** 2), places=12)
        self.assertGreater(rho[0, 1], 0.75)
        self.assertLess(rho[0, 2], 1e-3)

    def test_cqc_equals_srss_for_well_separated_modes_and_not_for_close_ones(self):
        import numpy as np

        from cadgen._internal.fea.analyses.shock import combine_modal, cqc_coefficients

        rng = np.random.default_rng(3)
        per_mode = rng.standard_normal((3, 50, 6))
        srss = combine_modal(per_mode)
        np.testing.assert_allclose(srss, np.sqrt((per_mode ** 2).sum(axis=0)), rtol=1e-12)
        apart = cqc_coefficients(2 * math.pi * np.array([100.0, 630.0, 4000.0]), 0.05)
        np.testing.assert_allclose(combine_modal(per_mode, apart), srss, rtol=0.01)
        # Two modes at one frequency peak together: CQC adds them, SRSS does not.
        same = np.stack([per_mode[0], per_mode[0]])
        together = cqc_coefficients(2 * math.pi * np.array([200.0, 200.0]), 0.05)
        np.testing.assert_allclose(combine_modal(same, together), 2 * np.abs(per_mode[0]), rtol=1e-12)
        np.testing.assert_allclose(combine_modal(same), math.sqrt(2) * np.abs(per_mode[0]), rtol=1e-12)


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ShockedCantilever(unittest.TestCase):
    """The clamped beam shocked along Z, 50 g above 100 Hz, its modes up to 4 kHz combined by SRSS."""

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
            {"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.2, "faces": [cls.tip], "label": "Tip"}]})
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "beam.fea.glb", study=cls.study)
        cls.summary = cls.result.summary
        # The first bending mode along Z: the one moving the most mass along Z.
        cls.mode = max(cls.summary["modes"], key=lambda mode: mode["effective_mass_fraction"][2])
        cls.f1 = cls.mode["frequency_Hz"]
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _theory(self) -> float:
        return 1.566 * 50 * G0 / (2 * math.pi * self.f1) ** 2

    def test_one_dominant_mode_moves_the_tip_as_the_spectrum_says(self):
        self.assertAlmostEqual(self.f1, 490, delta=20)
        self.assertEqual((self.mode["srs_g"], self.mode["used"]), (50.0, True))
        self.assertAlmostEqual(self.summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)
        self.assertAlmostEqual(self.summary["max_displacement_mm"] / self._theory(), 1.0, delta=0.10)
        # The first mode alone carries nearly all of it.
        self.assertAlmostEqual(self.mode["peak_mm"] / self.summary["max_displacement_mm"], 1.0, delta=0.02)

    def test_cqc_equals_srss_for_these_well_separated_modes(self):
        from cadgen import fea

        with redirect_stderr(io.StringIO()):
            cqc = fea.solve(self.step, self.directory / "cqc.fea.glb", study={**self.study, "combination": "cqc"})
        self.assertGreaterEqual(sum(mode["used"] and mode["effective_mass_fraction"][2] > 0.05 for mode in cqc.summary["modes"]), 2)
        for key in ("max_von_mises_MPa", "max_displacement_mm"):
            with self.subTest(key=key):
                self.assertAlmostEqual(cqc.summary[key] / self.summary[key], 1.0, delta=0.01)
        self.assertEqual(cqc.summary["combination"], "cqc")

    def test_the_checks_are_shock_and_the_tip(self):
        stress, tip = self.summary["checks"]
        self.assertEqual((stress["kind"], stress["label"], stress["status"]), ("stress", "Shock", "passes"))
        self.assertAlmostEqual(stress["value"], self.summary["max_von_mises_MPa"])
        self.assertEqual((tip["kind"], tip["label"], tip["faces"], tip["status"]), ("displacement", "Tip", [self.tip], "passes"))
        self.assertAlmostEqual(tip["value"], self.summary["max_displacement_mm"], places=6)

    def test_the_findings_say_which_mode_carries_it_and_the_mass_left_out(self):
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertTrue(found["shock_response"]["summary"].startswith(f"Mode {self.mode['mode']} (490 Hz) carries most of the shock"))
        # Up to 4 kHz the first two bending modes move about 61 % + 19 % of the mass along Z.
        self.assertAlmostEqual(self.summary["effective_mass_fraction"], 0.80, delta=0.04)
        self.assertEqual(found["modes_missing_mass"]["severity"], "warning")
        self.assertIn("The modes used move only 8", found["modes_missing_mass"]["summary"])

    def test_the_glb_carries_the_envelopes_and_the_spectrum(self):
        gltf, _ = _glb(self.result.glb)
        extras = gltf["meshes"][0]["extras"]
        self.assertEqual((extras["analysis"]["type"], extras["analysis"]["noun"]), ("shock", "this shock"))
        self.assertEqual([field["field"] for field in extras["fields"]], ["von_mises", "displacement"])
        self.assertNotIn("series", extras)
        self.assertEqual(extras["study"]["srs"], {"direction": [0.0, 0.0, 1.0], "table": [[10.0, 5.0], [100.0, 50.0], [4000.0, 50.0]],
                                                  "damping_ratio": 0.05})
        self.assertEqual(extras["study"]["combination"], "srss")
        self.assertEqual(self.sidecar["analysis"], "shock")

    def test_the_cli_lines(self):
        lines = self.result.human_lines()
        self.assertIn("(shock)", lines[0])
        self.assertEqual(lines[1], "shock of 50 g above 100 Hz along Z, 5% damping; modes combined by SRSS")
        self.assertTrue(any(line.startswith("4 modes up to 4000 Hz, holding 8") for line in lines), lines)

    def test_an_oversized_model_completes_by_keeping_the_modes_that_move_with_the_shock(self):
        from cadgen import fea

        study = {**self.study, "fit": {"memory_GB": 0.01, "allow": ["reduce_modes"]}}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "tight.fea.glb", study=study)
        self.assertTrue(result.ok)
        step = result.fit[0]
        self.assertEqual(step["rung"], "reduce_modes")
        self.assertRegex(step["words"], r"^Kept 2 of the 4 modes up to 4000 Hz, the ones holding 8\d% of the mass moving along Z, to fit$")
        self.assertRegex(step["accuracy"], r"^the other \d+% of the mass along Z, the missing mass, is left out, so the peak may read a little low$")
        self.assertEqual((result.summary["modes_used"], step["detail"]["kept_modes"]), (2, 2))
        self.assertIn(f"adapted: {step['words']} ({step['accuracy']})", result.human_lines())
        self.assertIn("fit_reduce_modes", [finding["type"] for finding in result.findings])
        # The modes that carry the shock are kept: the benchmark still holds.
        self.assertAlmostEqual(result.summary["max_displacement_mm"] / self._theory(), 1.0, delta=0.10)


if __name__ == "__main__":
    unittest.main()
