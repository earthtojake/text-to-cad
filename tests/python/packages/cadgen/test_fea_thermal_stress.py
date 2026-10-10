"""Heat stress (`"analysis": "thermal_stress"`): the study it reads, and a bar heated free and heated clamped.

The bar is a 100 x 5 x 5 mm steel box (a build123d STEP in a temporary
directory) held at 120 °C on one face, so the thermal solve that runs first
leaves it uniformly at 120 °C, 100 °C above its stress-free 20 °C. Held at one
end it grows ΔL = α L ΔT and its middle carries no stress. Clamped at both ends
it cannot grow, and its middle carries σ = -E α ΔT, pushing on both walls.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
add_repo_path(".")

from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from tests.python.packages.cadgen.test_fea_thermal import box_step, glb_extras_and_attributes, side_faces, x_faces  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

STEEL = lookup_material("steel")
LENGTH, SIDE, HOT, REFERENCE = 100.0, 5.0, 120.0, 20.0
RISE = HOT - REFERENCE
BASE = {"analysis": "thermal_stress", "material": "steel", "fixtures": [{"faces": ["#o1.f1"]}],
        "temperatures": [{"faces": ["#o1.f2"], "C": HOT}]}


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**BASE, **changes})

    def test_it_reads_the_heat_the_fixtures_and_the_stress_free_temperature(self):
        study = self.parse(reference_C=25, loads=[{"faces": ["#o1.f3"], "type": "force", "vector_N": [0, 0, -10]}],
                           convection=[{"faces": ["#o1.f4"], "h_W_m2K": 10, "ambient_C": 20}])
        inputs = study.inputs
        self.assertEqual(inputs.reference_C, 25.0)
        self.assertEqual([fixture.faces for fixture in study.fixtures], [("#o1.f1",)])
        self.assertEqual(len(study.loads), 1)
        self.assertEqual(inputs.thermal.temperatures[0].celsius, HOT)
        self.assertEqual(inputs.anchor_refs, ("#o1.f1",))
        self.assertEqual(set(study.face_refs), {"#o1.f1", "#o1.f2", "#o1.f3", "#o1.f4"})
        self.assertEqual(study.checks, ({"kind": "stress"},))
        default = self.parse()
        self.assertEqual((default.inputs.reference_C, default.loads), (20.0, ()))

    def test_it_needs_a_fixture_a_way_for_the_heat_out_and_an_expansion(self):
        cases = [
            ({"fixtures": []}, "'fixtures' must list at least one"),
            ({"temperatures": []}, "has no steady temperature"),
            ({"reference_C": "room"}, "reference_C: expected a number"),
            ({"view": {"checks": [{"kind": "temperature", "max_C": 200}]}}, "is not a check this cadgen makes"),
            ({"material": {"name": "x", "E_MPa": 1e3, "nu": 0.3, "yield_MPa": 10, "conductivity_W_mK": 1}}, "expansion_per_K"),
            ({"loads": [{"type": "gravity", "vector_g": [0, 0, -1]}], "material": {"name": "x", "E_MPa": 1e3, "nu": 0.3,
              "yield_MPa": 10, "density_t_per_mm3": 0, "conductivity_W_mK": 1, "expansion_per_K": 1e-5}}, "density"),
        ]
        for changes, fragment in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(fragment, str(caught.exception))

    def test_its_view_offers_stress_displacement_temperature_and_the_load_control(self):
        study = self.parse(view={"controls": [{"drives": "field"}, {"drives": "load_scale", "max": 2}]})
        self.assertEqual(study.view["controls"][0]["options"], ["von_mises", "displacement", "temperature"])


def _middle_peak(extras: dict, attributes: dict) -> float:
    """The highest von Mises within 10 mm of the bar's middle, in the undeformed part."""
    scale = extras["deformation_scale"]
    peak = 0.0
    for (x, _, _), (dx, _, _), (stress,) in zip(attributes["POSITION"], attributes["_DISPLACEMENT"], attributes["_VON_MISES"]):
        if abs((x - scale * dx) * 1000.0 - LENGTH / 2) < 10.0:
            peak = max(peak, stress)
    return peak


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class HeatedBar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = box_step(directory, "bar", (LENGTH, SIDE, SIDE))
        near, far = x_faces(step)
        heat = {"analysis": "thermal_stress", "material": "steel", "mesh": {"size_mm": 2.5},
                "temperatures": [{"faces": [far], "C": HOT}]}
        names = ("POSITION", "_DISPLACEMENT", "_VON_MISES", "_TEMPERATURE")
        with redirect_stderr(io.StringIO()):
            cls.free = fea.solve(step, directory / "free.glb", study={**heat, "fixtures": [{"faces": [near]}]})
            cls.clamped = fea.solve(step, directory / "clamped.glb", study={**heat, "fixtures": [{"faces": [near]}, {"faces": [far]}]})
        cls.free_extras, cls.free_attributes = glb_extras_and_attributes(cls.free.glb, names)
        cls.clamped_extras, cls.clamped_attributes = glb_extras_and_attributes(cls.clamped.glb, names)
        cls.clamped_sidecar = json.loads(cls.clamped.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_held_at_one_end_it_grows_alpha_l_dt(self):
        growth = STEEL.expansion * LENGTH * RISE
        summary = self.free.summary
        self.assertAlmostEqual(summary["max_displacement_mm"] / growth, 1.0, delta=0.02)
        self.assertAlmostEqual(summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)
        self.assertEqual((summary["max_temperature_C"], summary["min_temperature_C"]), (HOT, HOT))

    def test_held_at_one_end_its_middle_carries_no_stress(self):
        self.assertLess(_middle_peak(self.free_extras, self.free_attributes), 0.01 * STEEL.E * STEEL.expansion * RISE)

    def test_clamped_at_both_ends_its_middle_is_pressed_by_e_alpha_dt(self):
        sigma = STEEL.E * STEEL.expansion * RISE
        self.assertAlmostEqual(_middle_peak(self.clamped_extras, self.clamped_attributes) / sigma, 1.0, delta=0.05)
        # Compressed: each wall pushes the bar back toward its middle, +x at the near end, -x at the far one.
        near, far = (fixture["reaction_N"][0] for fixture in self.clamped_sidecar["fixtures"])
        self.assertAlmostEqual(near / (sigma * SIDE * SIDE), 1.0, delta=0.05)
        self.assertAlmostEqual(far / -(sigma * SIDE * SIDE), 1.0, delta=0.05)
        self.assertEqual(self.clamped.warnings, ())

    def test_the_glb_carries_the_temperature_and_the_heat_for_the_viewer(self):
        extras = self.clamped_extras
        self.assertEqual(extras["analysis"]["type"], "thermal_stress")
        self.assertEqual(extras["analysis"]["noun"], "this heat")
        self.assertEqual(extras["analysis"]["reference_C"], REFERENCE)
        fields = {entry["field"]: entry for entry in extras["fields"]}
        self.assertEqual(list(fields), ["von_mises", "displacement", "temperature"])
        self.assertEqual((fields["temperature"]["min"], fields["temperature"]["max"]), (HOT, HOT))
        self.assertTrue(all(value == (HOT,) for value in self.clamped_attributes["_TEMPERATURE"]))
        self.assertEqual(extras["study"]["temperatures"][0]["C"], HOT)
        self.assertEqual(extras["study"]["reference_C"], REFERENCE)
        self.assertEqual(len(extras["study"]["fixtures"]), 2)
        self.assertIsNotNone(extras["safety_factor"])
        self.assertIn("max_temperature_C", self.clamped_sidecar["upstream"]["thermal"])

    def test_the_findings_and_the_cli_say_it_was_heated(self):
        heated = [finding for finding in self.clamped.findings if finding["type"] == "heated"]
        self.assertEqual(len(heated), 1)
        self.assertIn("Heated to 120 °C at most", heated[0]["summary"])
        lines = self.clamped.human_lines()
        self.assertIn("(thermal_stress)", lines[0])
        self.assertTrue(lines[1].startswith("max von Mises"))
        self.assertIn("temperatures 120 to 120 °C, stress-free at 20 °C", lines)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class RadiatingBar(unittest.TestCase):
    """The bar takes 1 W on one long side and radiates it from every face (emissivity 0.9, into 20 °C), clamped at
    both ends: it settles at its radiative equilibrium T = (Q / (ε σ A) + T∞⁴)^¼, nearly uniform along it, and is
    pressed by E α (T - 20 °C)."""

    POWER, EMISSIVITY = 1.0, 0.9

    def test_its_stress_follows_its_radiative_equilibrium_temperature(self):
        from cadgen import fea

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            step = box_step(directory, "bar", (LENGTH, SIDE, SIDE))
            near, far = x_faces(step)
            every = [near, far, *side_faces(step)]
            study = {"analysis": "thermal_stress", "material": "steel", "mesh": {"size_mm": 2.5},
                     "fixtures": [{"faces": [near]}, {"faces": [far]}],
                     "heat": [{"faces": [side_faces(step)[0]], "W": self.POWER}],
                     "radiation": [{"faces": every, "emissivity": self.EMISSIVITY, "ambient_C": REFERENCE}]}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, directory / "radiating.glb", study=study)
            extras, attributes = glb_extras_and_attributes(result.glb, ("POSITION", "_DISPLACEMENT", "_VON_MISES", "_TEMPERATURE"))
        area = (4 * LENGTH * SIDE + 2 * SIDE * SIDE) * 1e-6
        ambient = REFERENCE + 273.15
        settled = (self.POWER / (self.EMISSIVITY * 5.670374419e-8 * area) + ambient ** 4) ** 0.25 - 273.15
        summary = result.summary
        mean = 0.5 * (summary["max_temperature_C"] + summary["min_temperature_C"])
        self.assertAlmostEqual(mean / settled, 1.0, delta=0.01, msg=(summary["min_temperature_C"], summary["max_temperature_C"], settled))
        sigma = STEEL.E * STEEL.expansion * (mean - REFERENCE)
        self.assertAlmostEqual(_middle_peak(extras, attributes) / sigma, 1.0, delta=0.05)
        self.assertIn("radiation", extras["study"])


if __name__ == "__main__":
    unittest.main()
