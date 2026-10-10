"""Fatigue life from a static load case, a harmonic dwell and a random shake: Marin, Basquin, Goodman and
Steinberg-Miner by hand, and on a cantilever's peak.

The S-N line runs from 0.9 Sut at 1e3 cycles to the corrected endurance
strength Se = ka · kf · Se' at N_e (Shigley, chapter 6; ka from table 6-2).
Aluminium has no endurance limit: its line ends at its 5e8-cycle strength. A
polymer carries no fatigue data, so a study on one asks for it. The solve is a
7075-T6 cantilever, a build123d box in a temporary STEP, loaded from zero: the
reported fatigue factor and life must match the hand calculation on the
solve's own peak stress within 1 %. The vibration sources shake a steel
cantilever: a harmonic dwell at the sweep's peak frequency (cycles = f ×
dwell_s, Goodman on the peak frame's stress, fully reversed), and a random
shake (Steinberg's three bands, Miner's rule over duration_s at the
zero-crossing rate random_vibration reports), each checked against the hand
calculation on the solve's own numbers.
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

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
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


def _vibration(source: str, **fatigue) -> dict:
    shake = ({"excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1}, "sweep_Hz": [10, 600]}
             if source == "harmonic" else {"psd": {"direction": [0, 0, 1], "table": [[20, 0.04], [1000, 0.04]]}})
    return {"analysis": "fatigue", "material": "steel", "fixtures": FIXTURES, "fatigue": {"from": source, **fatigue}, **shake}


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

    def test_steinberg_miner_by_hand(self):
        from cadgen._internal.fea.analyses.fatigue import (
            FACTOR_CAP, STEINBERG, miner_life, sn_curve, steinberg_damage, steinberg_factor,
        )

        self.assertEqual(STEINBERG, ((1.0, 0.683), (2.0, 0.271), (3.0, 0.0433)))
        # Aluminium 6061-T6, polished: no endurance limit, so every band is on the Basquin line.
        aluminium = sn_curve(lookup_material("aluminum-6061-t6"), surface="polished")
        _, A, b = _hand_line(310.0, 96.5, 5e8, 1.0)
        rms = 40.0
        lives = [(k * rms / A) ** (1 / b) for k in (1, 2, 3)]
        damage = 0.683 / lives[0] + 0.271 / lives[1] + 0.0433 / lives[2]
        self.assertAlmostEqual(float(miner_life(aluminium, 2 * rms)) / lives[1], 1.0, delta=1e-9)
        self.assertAlmostEqual(float(steinberg_damage(aluminium, rms)) / damage, 1.0, delta=1e-9)
        # Miner over a million cycles: D(n σ) = n^(-1/b) D(σ), so the stress may grow n = (cycles · D)^b times
        # before the damage reaches 1.
        cycles = 1e6
        hand = (cycles * damage) ** b
        self.assertGreater(hand, 1.0)
        self.assertAlmostEqual(float(steinberg_factor(aluminium, rms, cycles)) / hand, 1.0, delta=1e-6)
        self.assertAlmostEqual(cycles * float(steinberg_damage(aluminium, rms * steinberg_factor(aluminium, rms, cycles))), 1.0,
                               delta=1e-6)
        # Twice the stress over ten billion cycles fails: n under 1, still on the line.
        self.assertAlmostEqual(float(steinberg_factor(aluminium, 2 * rms, 1e10)) / (1e10 * float(steinberg_damage(aluminium, 2 * rms))) ** b,
                               1.0, delta=1e-6)
        self.assertLess(float(steinberg_factor(aluminium, 2 * rms, 1e10)), 1.0)
        # Steel has an endurance limit: a band at or under Se does no damage, and no stress at all is FACTOR_CAP.
        steel = sn_curve(lookup_material("steel"), surface="machined")
        self.assertEqual(float(miner_life(steel, 0.99 * steel.endurance)), math.inf)
        only_3sigma = steel.endurance / 2.5  # 1σ and 2σ under Se, 3σ over it
        self.assertAlmostEqual(float(steinberg_damage(steel, only_3sigma)),
                               0.0433 / float(miner_life(steel, 3 * only_3sigma)), places=15)
        self.assertEqual(float(steinberg_factor(steel, 0.0, 1e9)), FACTOR_CAP)
        # Past steel's endurance limit the damage is no power law; the factor still makes it exactly 1.
        quiet = steel.endurance / 6.0  # 3σ at half of Se: no damage until the stress more than doubles
        n = float(steinberg_factor(steel, quiet, 1e7))
        self.assertGreater(n, 2.0)
        self.assertAlmostEqual(1e7 * float(steinberg_damage(steel, n * quiet)), 1.0, delta=1e-6)

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

    def test_harmonic_and_random_sources_parse_their_own_study(self):
        from cadgen._internal.fea.analyses.harmonic import HarmonicInputs
        from cadgen._internal.fea.analyses.random_vibration import RandomVibrationInputs

        harmonic = self.parse(_vibration("harmonic", dwell_s=600)).inputs
        self.assertEqual((harmonic.source, harmonic.dwell_s, harmonic.cycles, harmonic.ratio, harmonic.loading),
                         ("harmonic", 600.0, None, -1.0, "fully_reversed"))
        self.assertIsInstance(harmonic.source_inputs, HarmonicInputs)
        self.assertEqual(harmonic.source_inputs.sweep_Hz, (10.0, 600.0))
        self.assertEqual(get_analysis("fatigue").upstream_for(harmonic), ("harmonic",))
        random = self.parse(_vibration("random_vibration", duration_s=3600, surface="ground")).inputs
        self.assertEqual((random.source, random.duration_s, random.surface), ("random_vibration", 3600.0, "ground"))
        self.assertIsInstance(random.source_inputs, RandomVibrationInputs)
        # A shake needs the material's density, besides its fatigue data.
        self.assertIn("density", random.material_needs)

    def test_each_source_says_what_it_needs(self):
        self.assertIn("goes with from harmonic", self.error(_study(dwell_s=10)))
        for document, fragment in (
            (_vibration("harmonic"), 'fatigue.dwell_s: how long it is shaken, in seconds, like {"from": "harmonic", "dwell_s": 3600}'),
            (_vibration("random_vibration"), "fatigue.duration_s: how long it is shaken"),
            (_vibration("harmonic", dwell_s=60, cycles=1e6), "counts its own cycles (the peak frequency × dwell_s)"),
            (_vibration("harmonic", dwell_s=60, loading="zero_based"), "swings about zero, so it is fully reversed"),
            (_vibration("random_vibration", duration_s=60, dwell_s=1), "fatigue.dwell_s: goes with from harmonic"),
            (_vibration("harmonic", dwell_s=-1), "fatigue.dwell_s"),
            ({**_vibration("harmonic", dwell_s=60), "psd": {}}, "['psd'] go with another fatigue source"),
            ({**_study(), "sweep_Hz": [10, 600]}, "['sweep_Hz'] go with another fatigue source; fatigue from static takes"),
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.error(document))

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



def _shaken_beam(directory: Path) -> tuple[Path, str]:
    """A 60 mm 6 x 6 cantilever in a temporary STEP, and its clamped end's face."""
    from build123d import Align, Box, export_step

    from cadgen import fea

    step = directory / "beam.step"
    export_step(Box(60, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(step))
    planes = {face.center_mm[0]: face.ref for face in fea.faces(step).faces
              if face.surface == "plane" and face.normal and abs(abs(face.normal[0]) - 1) < 1e-6}
    return step, planes[min(planes)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class HarmonicDwell(unittest.TestCase):
    """A steel cantilever shaken at 80 g from 10 to 2500 Hz, dwelling a minute at its peak (its first mode)."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step, fixed = _shaken_beam(directory)
        cls.study = {
            "analysis": "fatigue", "material": "steel", "mesh": {"size_mm": 3}, "fixtures": [{"faces": [fixed]}],
            "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 80}, "sweep_Hz": [10, 2500],
            "fatigue": {"from": "harmonic", "dwell_s": 60},
        }
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "beam.glb", study=cls.study)
        cls.extras = _extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_cycles_are_the_peak_frequency_times_the_dwell(self):
        summary = self.result.summary
        self.assertEqual((summary["source"], summary["method"], summary["loading"], summary["dwell_s"]),
                         ("harmonic", "goodman", "fully_reversed", 60.0))
        self.assertGreater(summary["peak_Hz"], 1000)  # its first mode, about 1.36 kHz
        self.assertAlmostEqual(summary["cycles"] / (summary["peak_Hz"] * 60), 1.0, delta=1e-5)
        self.assertEqual(summary["mean_stress_MPa"], 0.0)

    def test_goodman_and_basquin_match_the_hand_calculation(self):
        summary = self.result.summary
        se, A, b = _hand_line(400.0, 200.0, 1e6, 4.51 * 400.0 ** -0.265)
        sigma, cycles = summary["stress_amplitude_MPa"], summary["cycles"]
        self.assertGreater(sigma, se)  # on the line: it wears out
        self.assertAlmostEqual(summary["min_fatigue_factor"] / (A * cycles ** b / sigma), 1.0, delta=0.01)
        self.assertAlmostEqual(summary["min_life_cycles"] / (sigma / A) ** (1 / b), 1.0, delta=0.01)
        (check,) = summary["checks"]
        self.assertAlmostEqual(check["need"] / cycles, 1.0, delta=1e-5)
        self.assertEqual(check["status"], "fails" if check["value"] < 1 else "close" if check["value"] < 1.5 else "passes")

    def test_it_writes_the_shake_and_says_the_dwell(self):
        fields = [entry["attribute"] for entry in self.extras["fields"]]
        self.assertEqual(fields, ["_LIFE", "_FATIGUE_FACTOR", "_DISPLACEMENT"])
        self.assertGreater(self.result.summary["max_displacement_mm"], 0.0)  # its widest swing, not the resonance's real part
        self.assertEqual(self.extras["study"]["fatigue"], {"from": "harmonic", "loading": "fully_reversed", "stress_ratio": -1.0,
                                                          "dwell_s": 60.0, "surface": "machined", "factor": 1.0})
        self.assertEqual(self.extras["study"]["sweep_Hz"], [10.0, 2500.0])
        lines = "\n".join(self.result.human_lines())
        self.assertIn("fatigue from harmonic, a 60 s dwell at", lines)
        self.assertIn("(modified Goodman)", lines)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class RandomShake(unittest.TestCase):
    """A 6061-T6 cantilever under a flat 16 g²/Hz from 20 to 2500 Hz for an hour: Steinberg's bands, Miner's rule."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step, fixed = _shaken_beam(directory)
        cls.study = {
            "analysis": "fatigue", "material": "aluminum-6061-t6", "mesh": {"size_mm": 3}, "fixtures": [{"faces": [fixed]}],
            "psd": {"direction": [0, 0, 1], "table": [[20, 16], [2500, 16]]},
            "fatigue": {"from": "random_vibration", "duration_s": 3600},
            "view": {"checks": [{"kind": "fatigue"}, {"kind": "fatigue", "cycles": 1e8, "label": "Service"}]},
        }
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "beam.glb", study=cls.study)
        cls.extras = _extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hand(self, cycles: float) -> tuple[float, float]:
        """Steinberg longhand on the solve's own peak RMS stress: Miner's damage per cycle and the factor over ``cycles``."""
        _, A, b = _hand_line(310.0, 96.5, 5e8, 4.51 * 310.0 ** -0.265)
        sigma = self.result.summary["max_von_mises_rms_MPa"]
        damage = sum(share / (k * sigma / A) ** (1 / b) for k, share in ((1, 0.683), (2, 0.271), (3, 0.0433)))
        return damage, (cycles * damage) ** b

    def test_the_cycles_are_the_zero_crossing_rate_times_the_duration(self):
        summary = self.result.summary
        self.assertEqual((summary["source"], summary["method"], summary["duration_s"]), ("random_vibration", "steinberg_miner", 3600.0))
        self.assertEqual(summary["bands"], [{"sigma": 1.0, "share": 0.683}, {"sigma": 2.0, "share": 0.271}, {"sigma": 3.0, "share": 0.0433}])
        self.assertAlmostEqual(summary["cycles"] / (summary["zero_crossing_Hz"] * 3600), 1.0, delta=1e-5)
        self.assertAlmostEqual(summary["checks"][0]["need"] / summary["cycles"], 1.0, delta=1e-5)

    def test_steinberg_and_miner_match_the_hand_calculation(self):
        summary = self.result.summary
        damage, _ = self.hand(1.0)
        self.assertAlmostEqual(summary["min_life_cycles"] / (1 / damage), 1.0, delta=0.01)
        # A check that names its cycles counts them at every node alike: the peak RMS stress governs.
        service = summary["checks"][1]
        self.assertEqual((service["label"], service["need"]), ("Service", 1e8))
        self.assertAlmostEqual(service["value"] / self.hand(1e8)[1], 1.0, delta=0.01)
        # Over the hour each node counts its own crossings: no node does better than the peak at the peak's rate.
        self.assertLessEqual(summary["min_fatigue_factor"], self.hand(summary["cycles"])[1] * 1.01)
        self.assertGreater(summary["min_fatigue_factor"], 1.0)

    def test_it_writes_life_and_factor_but_no_shape(self):
        fields = [entry["attribute"] for entry in self.extras["fields"]]
        self.assertEqual(fields, ["_LIFE", "_FATIGUE_FACTOR"])
        self.assertEqual(self.extras["study"]["fatigue"], {"from": "random_vibration", "loading": "fully_reversed",
                                                          "stress_ratio": -1.0, "duration_s": 3600.0, "surface": "machined",
                                                          "factor": 1.0})
        self.assertIn("psd", self.extras["study"])
        lines = "\n".join(self.result.human_lines())
        self.assertIn("fatigue from random_vibration, 3600 s at", lines)
        self.assertIn("Steinberg bands 68.3% at 1σ, 27.1% at 2σ, 4.33% at 3σ", lines)


if __name__ == "__main__":
    unittest.main()
