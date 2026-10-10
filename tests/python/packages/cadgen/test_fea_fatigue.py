"""Fatigue life from a static load case: Marin, Basquin and Goodman by hand, and on a cantilever's peak.

The S-N line runs from 0.9 Sut at 1e3 cycles to the corrected endurance
strength Se = ka · kf · Se' at N_e (Shigley, chapter 6; ka from table 6-2).
Aluminium has no endurance limit: its line ends at its 5e8-cycle strength. A
polymer carries no fatigue data, so a study on one asks for it. The solve is a
7075-T6 cantilever, a build123d box in a temporary STEP, loaded from zero: the
reported fatigue factor and life must match the hand calculation on the
solve's own peak stress within 1 %.
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

from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

FIXTURES = [{"faces": ["#o1.f1"]}]
LOADS = [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -100]}]


def _study(material="steel", **fatigue) -> dict:
    return {"analysis": "fatigue", "material": material, "fixtures": FIXTURES, "loads": LOADS, "fatigue": fatigue}


def _hand_line(uts: float, endurance: float, cycles: float, ka: float) -> tuple[float, float, float]:
    """Se, and the Basquin A and b through (1e3, 0.9 Sut) and (N_e, Se), worked longhand."""
    se = ka * endurance
    b = (math.log10(se) - math.log10(0.9 * uts)) / (math.log10(cycles) - 3.0)
    return se, 0.9 * uts / 1000.0 ** b, b


class Method(unittest.TestCase):
    def test_the_marin_surface_factor_is_shigleys_table(self):
        from cadgen._internal.fea.analyses.fatigue import marin_surface

        # Shigley example 6-3: Sut 520 MPa, machined: ka = 4.51 · 520^-0.265 = 0.860.
        self.assertAlmostEqual(marin_surface("machined", 520.0), 0.860, places=3)
        self.assertAlmostEqual(marin_surface("hot_rolled", 520.0), 57.7 * 520 ** -0.718, places=12)
        self.assertAlmostEqual(marin_surface("as_forged", 400.0), 272.0 * 400 ** -0.995, places=12)
        self.assertEqual(marin_surface("polished", 520.0), 1.0)
        # Never above 1: a soft polymer's formula value is clipped.
        self.assertEqual(marin_surface("machined", 40.0), 1.0)

    def test_the_basquin_line_runs_from_0_9_sut_at_1e3_to_se_at_n_e(self):
        from cadgen._internal.fea.analyses.fatigue import marin_surface, sn_curve

        steel = lookup_material("steel")
        curve = sn_curve(steel, surface="machined")
        se, A, b = _hand_line(400.0, 200.0, 1e6, marin_surface("machined", 400.0))
        self.assertAlmostEqual(curve.endurance / se, 1.0, delta=1e-12)
        self.assertAlmostEqual(curve.A / A, 1.0, delta=1e-9)
        self.assertAlmostEqual(curve.b / b, 1.0, delta=1e-9)
        self.assertAlmostEqual(float(curve.strength(1e3)), 360.0, places=9)
        self.assertAlmostEqual(float(curve.strength(1e6)), se, places=9)
        # Past N_e the strength holds at Se; a stress under it never fails (steel's endurance limit).
        self.assertAlmostEqual(float(curve.strength(1e9)), se, places=9)
        self.assertEqual(float(curve.life(0.99 * se)), 1e6)
        # On the line, the life of a stress is where the line reaches it.
        stress = 250.0
        self.assertAlmostEqual(float(curve.life(stress)) / (stress / A) ** (1 / b), 1.0, delta=1e-9)
        self.assertAlmostEqual(float(curve.strength(curve.life(stress))), stress, places=6)

    def test_aluminium_uses_its_5e8_strength(self):
        from cadgen._internal.fea.analyses.fatigue import sn_curve

        aluminium = lookup_material("aluminum-6061-t6")
        curve = sn_curve(aluminium, surface="polished")
        self.assertEqual((curve.endurance_cycles, curve.endurance), (5e8, 96.5))
        self.assertAlmostEqual(float(curve.strength(5e8)), 96.5, places=9)
        self.assertAlmostEqual(float(curve.strength(1e3)), 0.9 * 310.0, places=9)
        self.assertEqual(float(curve.life(90.0)), 5e8)

    def test_goodman_is_amplitude_over_strength_plus_mean_over_uts(self):
        from cadgen._internal.fea.analyses.fatigue import FACTOR_CAP, goodman_factor, stress_ratio

        self.assertAlmostEqual(float(goodman_factor(100.0, 0.0, 200.0, 400.0)), 2.0, places=12)
        self.assertAlmostEqual(float(goodman_factor(60.0, 60.0, 180.0, 400.0)), 1 / (60 / 180 + 60 / 400), places=12)
        self.assertEqual(float(goodman_factor(0.0, 0.0, 180.0, 400.0)), FACTOR_CAP)
        self.assertEqual((stress_ratio("fully_reversed"), stress_ratio("zero_based"), stress_ratio(0.1)), (-1.0, 0.0, 0.1))


class Parse(unittest.TestCase):
    def parse(self, document):
        from cadgen._internal.fea.study import parse_study

        return parse_study(document)

    def error(self, document) -> str:
        with self.assertRaises(ValueError) as caught:
            self.parse(document)
        return str(caught.exception)

    def test_a_static_source_with_its_defaults(self):
        study = self.parse(_study())
        inputs = study.inputs
        self.assertEqual((inputs.source, inputs.loading, inputs.ratio, inputs.cycles, inputs.surface, inputs.factor),
                         ("static", "fully_reversed", -1.0, 1e6, "machined", 1.0))
        self.assertEqual(study.fixtures[0].faces, ("#o1.f1",))
        self.assertEqual(study.checks, ({"kind": "fatigue", "margin": 1.5},))
        ratio = self.parse(_study(loading={"ratio": 0.1}, cycles=2e5, surface="ground", factor=0.8)).inputs
        self.assertEqual((ratio.loading, ratio.ratio, ratio.cycles, ratio.surface, ratio.factor), ("ratio", 0.1, 2e5, "ground", 0.8))
        self.assertEqual((ratio.amplitude_share, ratio.mean_share), (0.45, 0.55))

    def test_a_polymer_asks_for_its_fatigue_data(self):
        message = self.error(_study("abs"))
        self.assertIn("ABS has no fatigue data", message)
        self.assertIn('"fatigue_strength_MPa": ', message)
        self.assertIn('"fatigue_cycles": ', message)
        given = self.parse(_study({"name": "abs", "fatigue_strength_MPa": 12, "fatigue_cycles": 1e6}))
        self.assertEqual((given.material.endurance, given.material.endurance_cycles), (12.0, 1e6))

    def test_harmonic_and_random_sources_are_coming(self):
        for source in ("harmonic", "random_vibration"):
            with self.subTest(source=source):
                self.assertIn("is coming, not in this cadgen yet", self.error(_study(**{"from": source})))
        self.assertIn("goes with from harmonic", self.error(_study(dwell_s=10)))

    def test_plain_errors_name_the_field(self):
        for document, fragment in (
            ({**_study(), "fatigue": None}, "study.fatigue: expected an object"),
            (_study(loading="sometimes"), "fatigue.loading"),
            (_study(loading={"ratio": 1}), "a steady load does not fatigue"),
            (_study(surface="shiny"), "fatigue.surface"),
            (_study(factor=1.2), "fatigue.factor"),
            (_study(cycles=0), "fatigue.cycles"),
            (_study(spin=1), "unknown keys ['spin']"),
            ({**_study(), "drop": {}}, "fatigue studies take"),
            ({**_study(), "view": {"checks": [{"kind": "stress"}]}}, "not a check this cadgen makes; use one of ['fatigue']"),
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.error(document))


def _extras(glb: Path) -> dict:
    raw = glb.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])["meshes"][0]["extras"]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Cantilever(unittest.TestCase):
    """A 60 mm 6 x 6 7075-T6 cantilever, its tip loaded from zero to 150 N and back, a million times."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "beam.step"
        export_step(Box(60, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(step))
        planes = {face.center_mm[0]: face.ref for face in fea.faces(step).faces
                  if face.surface == "plane" and face.normal and abs(abs(face.normal[0]) - 1) < 1e-6}
        cls.study = {
            "analysis": "fatigue", "material": "aluminum-7075-t6", "mesh": {"size_mm": 3},
            "fixtures": [{"faces": [planes[min(planes)]]}],
            "loads": [{"faces": [planes[max(planes)]], "type": "force", "vector_N": [0, 0, -150]}],
            "fatigue": {"from": "static", "loading": "zero_based", "cycles": 1e6, "surface": "machined"},
            "view": {"checks": [{"kind": "fatigue", "margin": 1.5}, {"kind": "fatigue", "cycles": 1e9, "label": "Service life"}]},
        }
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "beam.glb", study=cls.study)
        cls.extras = _extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hand(self) -> dict:
        """Goodman and Basquin longhand on the solve's own peak von Mises stress."""
        uts, endurance, cycles = 572.0, 159.0, 5e8
        se, A, b = _hand_line(uts, endurance, cycles, 4.51 * uts ** -0.265)
        sigma = self.result.summary["max_von_mises_MPa"]
        amplitude = mean = sigma / 2
        strength = A * 1e6 ** b
        equivalent = amplitude / (1 - mean / uts)
        return {"factor": 1 / (amplitude / strength + mean / uts), "life": (equivalent / A) ** (1 / b),
                "factor_1e9": 1 / (amplitude / se + mean / uts), "se": se}

    def test_the_fatigue_factor_and_life_match_the_hand_calculation(self):
        hand, summary = self.hand(), self.result.summary
        self.assertGreater(hand["life"], 1e3)  # on the line: Basquin, not its ends
        self.assertLess(hand["life"], 5e8)
        self.assertAlmostEqual(summary["min_fatigue_factor"] / hand["factor"], 1.0, delta=0.01)
        self.assertAlmostEqual(summary["min_life_cycles"] / hand["life"], 1.0, delta=0.01)
        self.assertAlmostEqual(summary["sn"]["corrected_endurance_MPa"] / hand["se"], 1.0, delta=1e-4)
        self.assertEqual(summary["sn"]["endurance_cycles"], 5e8)
        self.assertAlmostEqual(summary["stress_amplitude_MPa"], summary["max_von_mises_MPa"] / 2, places=3)

    def test_the_check_says_life_need_ratio_and_close_at(self):
        hand = self.hand()
        first, service = self.result.summary["checks"]
        self.assertEqual({k: first[k] for k in ("kind", "label", "unit", "limit", "margin", "need", "close_at")},
                         {"kind": "fatigue", "label": "Fatigue life", "unit": "", "limit": 1.5, "margin": 1.5, "need": 1e6,
                          "close_at": round(1 / 1.5, 6)})
        self.assertAlmostEqual(first["value"] / hand["factor"], 1.0, delta=0.01)
        self.assertAlmostEqual(first["ratio"] * first["value"], 1.0, delta=0.01)
        self.assertAlmostEqual(first["life"] / hand["life"], 1.0, delta=0.01)
        self.assertEqual(first["status"], "fails" if hand["factor"] < 1 else "close" if hand["factor"] < 1.5 else "passes")
        # Past aluminium's data (5e8) a billion cycles is judged at its 5e8 strength, and a finding says it may overstate it.
        self.assertEqual((service["label"], service["need"]), ("Service life", 1e9))
        self.assertAlmostEqual(service["value"] / hand["factor_1e9"], 1.0, delta=0.01)
        past = [finding for finding in self.result.findings if finding["type"] == "past_fatigue_data"]
        self.assertEqual([finding["severity"] for finding in past], ["warning"])
        self.assertIn("no endurance limit", past[0]["summary"])

    def test_the_glb_carries_life_and_fatigue_factor(self):
        fields = {entry["attribute"]: entry for entry in self.extras["fields"]}
        self.assertEqual(list(fields), ["_LIFE", "_FATIGUE_FACTOR", "_DISPLACEMENT"])
        self.assertEqual((fields["_LIFE"]["field"], fields["_LIFE"]["units"]), ("life", "log10 cycles"))
        self.assertAlmostEqual(fields["_LIFE"]["min"], math.log10(self.result.summary["min_life_cycles"]), places=3)
        # The lightly loaded tip outlasts the data: the field stops at the line's end.
        self.assertAlmostEqual(fields["_LIFE"]["max"], math.log10(5e8), places=6)
        self.assertAlmostEqual(fields["_FATIGUE_FACTOR"]["min"], self.result.summary["min_fatigue_factor"], delta=1e-3)
        self.assertEqual({k: self.extras["analysis"][k] for k in ("type", "tier", "estimate")},
                         {"type": "fatigue", "tier": 1, "estimate": False})
        self.assertEqual(self.extras["study"]["fatigue"], {"from": "static", "loading": "zero_based", "stress_ratio": 0.0,
                                                         "cycles": 1e6, "surface": "machined", "factor": 1.0})
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["analysis"], "fatigue")
        self.assertIn("min_fatigue_factor", sidecar["summary"])

    def test_the_cli_says_the_method_in_words(self):
        lines = "\n".join(self.result.human_lines())
        self.assertIn("fatigue from static, zero based", lines)
        self.assertIn("S-N line: UTS 572 MPa; fatigue strength 159 MPa at 5e+08 cycles", lines)
        self.assertIn("(modified Goodman)", lines)
        self.assertIn("check 'Fatigue life'", lines)


if __name__ == "__main__":
    unittest.main()
