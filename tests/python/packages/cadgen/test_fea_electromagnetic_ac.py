"""AC magnetic fields (`"analysis": "electromagnetic", "mode": "ac_magnetic"`): eddy currents, skin effect, induction heating.

- Skin effect: a round aluminium wire (radius a) fed an AC current through its ends at the frequency
  where its skin depth is a / 2.5 has R_ac / R_dc = Re[(ka / 2) J0(ka) / J1(ka)], k = (1 - j) / delta
  (Bessel's closed form for a long round conductor); at 1 Hz the same wire is R_dc = rho L / A.
- Eddy loss: a thin aluminium plate (t much under the skin depth) in a uniform AC field along it loses
  P = pi² B² f² t² sigma V / 6 (the low-frequency lamination formula); handed to a thermal solve, every
  watt of it leaves through the cooled faces, so the plate warms by P / (h A).
- The low-frequency limit: a coil at 1 Hz has the magnetostatic field and inductance.
- The ladder: on a tiny budget the air coarsens and the skin is meshed coarser than it asks, and the
  result says so plainly (and still reads the AC resistance within a widened tolerance).

Each STEP is a build123d solid in a temporary directory; meshes are coarse.
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

MU0_H_M = 1.25663706127e-6
ALUMINIUM = "aluminum-6061-t6"


def parse(document: dict):
    from cadgen._internal.fea.study import parse_study

    return parse_study({"analysis": "electromagnetic", "material": ALUMINIUM, "mode": "ac_magnetic", **document})


def glb_extras(path: Path) -> tuple[dict, set[str]]:
    """A result GLB's extras and the names of its vertex attributes."""
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    mesh = gltf["meshes"][0]
    return mesh["extras"], set(mesh["primitives"][0]["attributes"])


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


def ends(step: Path) -> dict[float, str]:
    """A z-axis cylinder's flat ends, by their z."""
    from cadgen import fea

    return {round(face.center_mm[2], 6): face.ref for face in fea.faces(step).faces if face.surface == "plane"}


def bessel_ratio(radius_m: float, depth_m: float) -> float:
    """R_ac / R_dc of a long round conductor: Re[(ka / 2) J0(ka) / J1(ka)], k = (1 - j) / delta."""
    from scipy.special import jv

    ka = (1 - 1j) / depth_m * radius_m
    return float((ka / 2 * jv(0, ka) / jv(1, ka)).real)


class StudyFile(unittest.TestCase):
    def test_it_reads_its_own_keys_and_writes_eddy_current_and_magnetic_field(self):
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.analyses.electromagnetic import AC_LIMITS, LIMITS

        parsed = parse({"frequency_Hz": 50000, "coils": [{"turns": 10, "A": 2, "axis": {"direction": [0, 0, 1]}}],
                        "applied_field": {"mT": 10, "direction": [1, 0, 0]}, "probes": [{"at_mm": [0, 0, 0]}],
                        "electro_thermal": {"convection": [{"faces": ["#o1.f1"], "h_W_m2K": 10, "ambient_C": 20}]},
                        "view": {"checks": [{"kind": "temperature", "max_C": 80}]}})
        inputs = parsed.inputs
        self.assertEqual((inputs.mode, inputs.frequency_Hz, inputs.air_mm), ("ac_magnetic", 50000.0, 0.0))
        self.assertEqual((inputs.applied.mT, inputs.applied.direction), (10.0, (1.0, 0.0, 0.0)))
        self.assertEqual(inputs.material_needs, frozenset({"permeability", "resistivity", "conductivity"}))
        analysis = get_analysis("electromagnetic")
        self.assertEqual([f.name for f in analysis.fields], ["eddy_current", "magnetic_field", "temperature"])
        self.assertEqual(next(f for f in analysis.fields if f.name == "eddy_current").attribute, "_EDDY_CURRENT")
        # Its limits and its ladder follow the mode: time-harmonic, and the air before the skin.
        self.assertEqual(analysis.limits, AC_LIMITS)
        self.assertIn("Time-harmonic", analysis.limits[0])
        self.assertEqual(analysis.ladder, ("iterative", "far_field", "local_refine"))
        parse_dc = parse({"mode": "magnetostatic", "coils": [{"turns": 10, "A": 2, "axis": {"direction": [0, 0, 1]}}]})
        self.assertIsNone(parse_dc.inputs.frequency_Hz)
        self.assertEqual(analysis.limits, LIMITS)

    def test_the_errors_name_the_field_in_plain_words(self):
        coil = [{"turns": 10, "A": 1, "axis": {"direction": [0, 0, 1]}}]
        cases = [
            ({"coils": coil}, "frequency_Hz: an AC study needs its frequency"),
            ({"frequency_Hz": 0, "coils": coil}, "frequency_Hz"),
            ({"frequency_Hz": 50}, "an AC study needs a source"),
            ({"frequency_Hz": 50, "currents": [{"faces": ["#o1.f1"], "A": 5}]}, "needs its return"),
            ({"frequency_Hz": 50, "currents": [{"faces": ["#o1.f1"], "A": 5}], "voltages": [{"faces": ["#o1.f2"], "V": 1}]},
             "driven by its current"),
            ({"frequency_Hz": 50, "coils": coil, "voltages": [{"faces": ["#o1.f2"], "V": 0}]}, "only as the return"),
            ({"frequency_Hz": 50, "applied_field": {"mT": 10}}, "applied_field.direction"),
            ({"frequency_Hz": 50, "applied_field": {"mT": 10, "direction": [0, 0, 0]}}, "the direction is zero"),
            ({"frequency_Hz": 50, "coils": coil, "view": {"checks": [{"kind": "temperature", "max_C": 80}]}},
             "add electro_thermal"),
            ({"frequency_Hz": 50, "coils": coil, "map_to_structure": {"fixtures": []}}, "not for an ac_magnetic study"),
            ({"mode": "magnetostatic", "frequency_Hz": 50, "coils": coil}, "not for a magnetostatic study"),
        ]
        for changes, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse(changes)
            self.assertIn(fragment, str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class SkinEffect(unittest.TestCase):
    """A round wire, radius 2 mm, fed 10 A through its ends: its AC resistance against Bessel's closed form."""

    RADIUS, LENGTH = 2.0, 2.0

    @classmethod
    def setUpClass(cls):
        from build123d import Cylinder, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "wire.step"
        export_step(Cylinder(cls.RADIUS, cls.LENGTH), str(cls.step))
        z = ends(cls.step)
        cls.rho = lookup_material(ALUMINIUM).resistivity
        cls.depth = cls.RADIUS / 2.5
        cls.frequency = cls.rho / (math.pi * MU0_H_M * (cls.depth * 1e-3) ** 2)
        cls.study = {"analysis": "electromagnetic", "mode": "ac_magnetic", "material": ALUMINIUM, "mesh": {"size_mm": 1.0},
                     "frequency_Hz": cls.frequency, "air": {"around_mm": 6},
                     "currents": [{"faces": [z[1.0]], "A": 10, "name": "in"}],
                     "voltages": [{"faces": [z[-1.0]], "V": 0, "name": "out"}]}
        cls.result = solve(cls.step, cls.directory / "wire.glb", cls.study)
        cls.r_dc = cls.rho * (cls.LENGTH / 1000) / (math.pi * (cls.RADIUS / 1000) ** 2)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_ac_resistance_is_bessels(self):
        expected = bessel_ratio(self.RADIUS / 1000, self.depth / 1000)
        self.assertGreater(expected, 1.4)                             # the skin is a fraction of the radius
        impedance = self.result.summary["impedance"]
        self.assertEqual(impedance["of"], "in")
        # Measured 1.3 % high at half a skin depth on the surface.
        self.assertAlmostEqual(impedance["R_ohm"] / self.r_dc / expected, 1.0, delta=0.05)
        # Time-averaged: P = I² R / 2.
        self.assertAlmostEqual(self.result.summary["loss_W"] / (0.5 * 10 ** 2 * impedance["R_ohm"]), 1.0, places=4)

    def test_the_skin_is_resolved_and_the_field_at_the_surface_is_mu0_i_over_2_pi_a(self):
        skin = self.result.summary["skin"][0]
        self.assertAlmostEqual(skin["depth_mm"], self.depth, places=4)
        self.assertTrue(skin["resolved"])
        self.assertAlmostEqual(skin["surface_mm"], self.depth / 2, places=4)
        expected_mT = MU0_H_M * 10 / (2 * math.pi * self.RADIUS / 1000) * 1e3
        self.assertAlmostEqual(self.result.summary["max_field_mT"] / expected_mT, 1.0, delta=0.03)
        # The current crowds to the surface: the densest is at the wire's skin, over the mean I / A.
        self.assertGreater(self.result.summary["max_eddy_current_A_mm2"], 1.3 * 10 / (math.pi * self.RADIUS ** 2))
        self.assertAlmostEqual(math.hypot(*self.result.summary["max_at_mm"][:2]), self.RADIUS, delta=0.01)

    def test_at_one_hertz_it_is_the_dc_resistance(self):
        # Meshed as the AC run meshes the wire's surface (0.4 mm), so the faceted section is the same.
        result = solve(self.step, self.directory / "dc.glb", {**self.study, "frequency_Hz": 1.0, "mesh": {"size_mm": 0.4}})
        self.assertAlmostEqual(result.summary["impedance"]["R_ohm"] / self.r_dc, 1.0, delta=0.01)

    def test_the_glb_says_what_it_is(self):
        extras, attributes = glb_extras(self.result.glb)
        self.assertIn("_EDDY_CURRENT", attributes)
        self.assertEqual([entry["field"] for entry in extras["fields"]], ["eddy_current", "magnetic_field"])
        self.assertEqual(extras["fields"][0]["units"], "A/mm²")
        analysis = extras["analysis"]
        self.assertEqual((analysis["mode"], analysis["noun"]), ("ac_magnetic", "this current"))
        self.assertAlmostEqual(analysis["frequency_Hz"], self.frequency)
        self.assertIn("Time-harmonic", analysis["limits"][0])
        self.assertEqual(extras["study"]["frequency_Hz"], self.frequency)
        self.assertTrue(any(line.startswith("at 15.8 kHz: loss") for line in self.result.human_lines()))

    def test_a_current_must_go_in_through_a_flat_end(self):
        from cadgen import fea

        side = next(face.ref for face in fea.faces(self.step).faces if face.surface != "plane")
        study = {**self.study, "currents": [{"faces": [side], "A": 10, "name": "in"}]}
        with self.assertRaises(ValueError) as caught:
            solve(self.step, self.directory / "side.glb", study)
        self.assertIn("flat faces square to x, y or z at the ends of the parts", str(caught.exception))
        self.assertIn(side, str(caught.exception))

    def test_on_a_tiny_budget_it_coarsens_the_air_and_the_skin_and_says_so(self):
        result = solve(self.step, self.directory / "fit.glb", {**self.study, "fit": {"memory_GB": 0.01, "seconds": 0.001}})
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("far_field", rungs)
        step = next(step for step in result.fit if step["rung"] == "local_refine")
        self.assertIn("Meshed the conductors' surfaces at 1 mm to fit, coarser than the 0.4 mm", step["words"])
        self.assertIn("about 6% at one element per skin depth", step["accuracy"])
        skin = result.summary["skin"][0]
        self.assertFalse(skin["resolved"])
        extras, _ = glb_extras(result.glb)
        self.assertIn(step["words"], [s["words"] for s in extras["fit"]])
        self.assertTrue(any("the skin is not resolved there" in line for line in extras["analysis"]["warnings"]))
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertIn(step["words"], [s["words"] for s in sidecar["fit"]])
        self.assertIn("fit_local_refine", [finding["type"] for finding in result.findings])
        # Under-resolved, it still reads the AC resistance (measured 5.7 % high at 0.8 elements per skin depth).
        expected = bessel_ratio(self.RADIUS / 1000, self.depth / 1000)
        self.assertAlmostEqual(result.summary["impedance"]["R_ohm"] / self.r_dc / expected, 1.0, delta=0.1)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class PlateInUniformField(unittest.TestCase):
    """A 10 x 10 x 0.5 mm aluminium plate in 100 mT along it at 500 Hz (skin depth 4.5 mm), cooled by still air."""

    SIDE, THICK, B, F = 10.0, 0.5, 0.1, 500.0

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "plate.step"
        export_step(Box(cls.SIDE, cls.SIDE, cls.THICK), str(step))
        refs = [face.ref for face in fea.faces(step).faces]
        cls.result = solve(step, directory / "plate.glb", {
            "analysis": "electromagnetic", "mode": "ac_magnetic", "material": ALUMINIUM, "mesh": {"size_mm": 1.0},
            "frequency_Hz": cls.F, "air": {"around_mm": 5}, "applied_field": {"mT": cls.B * 1e3, "direction": [1, 0, 0]},
            "electro_thermal": {"convection": [{"faces": refs, "h_W_m2K": 10, "ambient_C": 20}]},
            "view": {"checks": [{"kind": "temperature", "max_C": 21}]}})
        cls.area_m2 = (2 * cls.SIDE ** 2 + 4 * cls.SIDE * cls.THICK) * 1e-6

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_eddy_loss_is_the_lamination_formula(self):
        sigma = 1 / lookup_material(ALUMINIUM).resistivity
        volume = self.SIDE ** 2 * self.THICK * 1e-9
        expected = math.pi ** 2 * self.B ** 2 * self.F ** 2 * (self.THICK / 1000) ** 2 * sigma * volume / 6
        summary = self.result.summary
        # Measured 2.1 % low: the currents turning at the plate's edges (about 0.63 t / w for a strip).
        self.assertAlmostEqual(summary["loss_W"] / expected, 1.0, delta=0.10)
        self.assertEqual(summary["losses"][0]["part"], "plate")
        self.assertNotIn("impedance", summary)                         # a field, not a circuit: no impedance
        self.assertAlmostEqual(summary["applied_field"]["mT"], 100.0)
        self.assertAlmostEqual(summary["max_field_mT"] / 100.0, 1.0, delta=0.01)

    def test_the_loss_heats_the_plate_through_the_thermal_handoff(self):
        summary = self.result.summary
        # Every watt of loss goes into the thermal solve and leaves through the cooled faces: T = T_air + P / (h A).
        self.assertAlmostEqual(summary["heat_in_W"] / summary["loss_W"], 1.0, delta=1e-3)
        self.assertLess(summary["heat_balance"], 0.01)
        rise = summary["loss_W"] / (10.0 * self.area_m2)
        self.assertAlmostEqual((summary["max_temperature_C"] - 20.0) / rise, 1.0, delta=0.02)
        check = summary["checks"][0]
        self.assertEqual((check["kind"], check["status"], check["reference"]), ("temperature", "passes", 20.0))
        extras, attributes = glb_extras(self.result.glb)
        self.assertEqual([entry["field"] for entry in extras["fields"]], ["eddy_current", "magnetic_field", "temperature"])
        self.assertIn("_TEMPERATURE", attributes)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class InductionHeatedPart(unittest.TestCase):
    """A coil (its own part, stranded) around an aluminium disc at 2 kHz, the disc cooled by still air.

    An assembly's face refs have no mesh ordinal until it is meshed, and the fit ladder sizes the skin before that:
    this study once failed there (KeyError on the disc's face ref). Solved, every watt the disc loses leaves through
    its cooled faces, T = T_air + P / (h A), and the coil, which no heat reaches and nothing cools, reads the ambient.
    """

    RADIUS, THICK, H, AIR_C = 8.0, 2.0, 10.0, 20.0

    @classmethod
    def setUpClass(cls):
        from build123d import Compound, Cylinder, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        coil = Cylinder(14, 6) - Cylinder(11, 6)
        coil.label = "coil"
        disc = Cylinder(cls.RADIUS, cls.THICK)
        disc.label = "disc"
        step = directory / "induction.step"
        export_step(Compound(children=[coil, disc]), str(step))
        disc_faces = [face.ref for face in fea.faces(step, occurrence="#o1.2").faces]
        cls.result = solve(step, directory / "induction.glb", {
            "analysis": "electromagnetic", "mode": "ac_magnetic", "frequency_Hz": 2000, "material": ALUMINIUM,
            "parts": {"coil": {"material": "brass"}, "disc": {"material": ALUMINIUM}},
            "mesh": {"size_mm": 1.5}, "air": {"around_mm": 8},
            "coils": [{"part": "coil", "turns": 50, "A": 10, "axis": {"direction": [0, 0, 1], "point_mm": [0, 0, 0]}}],
            "electro_thermal": {"convection": [{"faces": disc_faces, "h_W_m2K": cls.H, "ambient_C": cls.AIR_C}]},
            "view": {"checks": [{"kind": "temperature", "max_C": 1000}]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_loss_heats_the_workpiece_by_p_over_h_a(self):
        self.assertTrue(self.result.ok)
        summary = self.result.summary
        self.assertEqual([loss["part"] for loss in summary["losses"]], ["disc"])  # the coil's wire is stranded
        self.assertGreater(summary["loss_W"], 0.0)
        self.assertAlmostEqual(summary["heat_in_W"] / summary["loss_W"], 1.0, delta=1e-3)
        area_m2 = (2 * math.pi * self.RADIUS ** 2 + 2 * math.pi * self.RADIUS * self.THICK) * 1e-6
        rise = summary["loss_W"] / (self.H * area_m2)
        self.assertAlmostEqual((summary["max_temperature_C"] - self.AIR_C) / rise, 1.0, delta=0.02)

    def test_the_glb_names_each_part_and_its_own_material(self):
        # The viewer's "Made of" and a face's part ("coil · face 3") read these; electromagnetic writes no per-part
        # results of its own, so they come from the assembly's plan.
        extras, _ = glb_extras(self.result.glb)
        self.assertEqual([(part["ref"], part["name"], part["material"]) for part in extras["parts"]],
                         [("#o1.1", "coil", "Brass (C36000)"), ("#o1.2", "disc", "Aluminum 6061-T6")])

    def test_the_coil_no_heat_reaches_reads_the_ambient_not_zero(self):
        extras, _ = glb_extras(self.result.glb)
        temperature = next(entry for entry in extras["fields"] if entry["field"] == "temperature")
        self.assertAlmostEqual(temperature["min"], self.AIR_C, places=3)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class LowFrequencyLimit(unittest.TestCase):
    def test_a_coil_at_one_hertz_has_the_magnetostatic_field_and_inductance(self):
        from build123d import Cylinder, export_step

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            step = directory / "coil.step"
            export_step(Cylinder(10, 4) - Cylinder(8, 4), str(step))
            base = {"analysis": "electromagnetic", "material": ALUMINIUM, "mesh": {"size_mm": 1.5},
                    "coils": [{"turns": 100, "A": 2, "axis": {"direction": [0, 0, 1], "point_mm": [0, 0, 0]}}],
                    "probes": [{"at_mm": [0, 0, 0], "label": "centre"}]}
            static = solve(step, directory / "static.glb", {**base, "mode": "magnetostatic"}).summary
            ac = solve(step, directory / "ac.glb", {**base, "mode": "ac_magnetic", "frequency_Hz": 1.0}).summary
        self.assertAlmostEqual(ac["probes"][0]["magnetic_field_mT"] / static["probes"][0]["magnetic_field_mT"], 1.0, delta=0.02)
        self.assertAlmostEqual(ac["impedance"]["L_uH"] / static["inductance_uH"], 1.0, delta=0.02)
        # A stranded coil with no conductor near it loses nothing: R is 0.
        self.assertEqual(ac["impedance"]["R_ohm"], 0.0)
        self.assertEqual(ac["losses"], [])


if __name__ == "__main__":
    unittest.main()
