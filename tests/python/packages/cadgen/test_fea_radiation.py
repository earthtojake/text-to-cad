"""Thermal radiation in `thermal` and `thermal_transient`: the study it reads, view factors, and three textbook answers.

- A plate radiating to its surroundings: a 100 x 100 x 2 mm aluminium plate takes
  100 W on its underside and radiates from its top (emissivity 0.9) to 25 °C, its
  other faces insulated; it settles where ε σ A (T⁴ − T∞⁴) = Q.
- Two parallel plates: two 50 x 50 x 2 mm black plates face each other 50 mm
  apart, one held at 500 °C behind, the other at 25 °C behind, their facing faces
  exchanging heat with each other (``surface_to_surface``) and with surroundings at
  25 °C. The view factor of two directly opposed squares of side a at distance c is
  F = 2/(π X Y) [ln √((1+X²)(1+Y²)/(1+X²+Y²)) + X √(1+Y²) atan(X/√(1+Y²))
  + Y √(1+X²) atan(Y/√(1+X²)) − X atan X − Y atan Y], X = Y = a/c; with black faces
  and the surroundings at the cold plate's temperature, the cold plate takes in
  exactly A F σ (T_h⁴ − T_c⁴).
- Radiative cooling of a small aluminium cube (10 mm, every face ε 0.9, 500 °C to
  25 °C surroundings): lumped, ρ c V dT/dt = −ε σ A (T⁴ − T∞⁴), whose integral is
  t = (ρ c V / ε σ A) [G(T0) − G(T)], G(T) = (ln((T − a)/(T + a)) − 2 atan(T/a)) / (4 a³), a = T∞.

The view factor routine is also checked alone on two triangulated squares, with and
without a plate between them. Each STEP is a build123d solid in a temporary directory.
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

SIGMA = 5.670374419e-8
KELVIN = 273.15
BASE = {"analysis": "thermal", "material": "aluminum-6061-t6"}


def opposed_squares(a: float, c: float) -> float:
    """The view factor between two directly opposed squares of side ``a`` at distance ``c``."""
    X = Y = a / c
    return 2 / (math.pi * X * Y) * (
        math.log(math.sqrt((1 + X * X) * (1 + Y * Y) / (1 + X * X + Y * Y)))
        + X * math.sqrt(1 + Y * Y) * math.atan(X / math.sqrt(1 + Y * Y))
        + Y * math.sqrt(1 + X * X) * math.atan(Y / math.sqrt(1 + X * X))
        - X * math.atan(X) - Y * math.atan(Y)
    )


def glb_extras(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])["meshes"][0]["extras"]


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**BASE, **changes})

    def test_it_reads_radiation_to_the_surroundings_and_between_faces(self):
        study = self.parse(radiation=[{"faces": ["#o1.f6"], "emissivity": 0.9, "ambient_C": 25},
                                      {"faces": ["#o1.f1", "#o1.f2"], "emissivity": 0.8, "ambient_C": 15, "surface_to_surface": True}])
        inputs = study.inputs
        self.assertEqual([(r.faces, r.emissivity, r.ambient, r.surface_to_surface) for r in inputs.radiation],
                         [(("#o1.f6",), 0.9, 25.0, False), (("#o1.f1", "#o1.f2"), 0.8, 15.0, True)])
        # Radiation alone gives the heat somewhere to go: it anchors a steady study, and sets the reference.
        self.assertEqual(inputs.anchor_refs, ("#o1.f6", "#o1.f1", "#o1.f2"))
        self.assertEqual(inputs.reference_C, 15.0)

    def test_a_study_without_radiation_reads_as_before(self):
        study = self.parse(temperatures=[{"faces": ["#o1.f1"], "C": 25}])
        self.assertEqual(study.inputs.radiation, ())
        from cadgen._internal.fea.analyses.thermal import heat_echo

        self.assertNotIn("radiation", heat_echo(study.inputs, list))

    def test_the_errors_name_the_field(self):
        cases = [
            ([{"faces": ["#o1.f6"], "ambient_C": 25}], "radiation[0].emissivity: how well the faces radiate"),
            ([{"faces": ["#o1.f6"], "emissivity": 1.2, "ambient_C": 25}], "a share from 0 to 1"),
            ([{"faces": ["#o1.f6"], "emissivity": 0.9}], "radiation[0].ambient_C"),
            ([{"faces": ["#o1.f6"], "emissivity": 0.9, "ambient_C": 25, "view": 1}], "radiation takes faces, emissivity, ambient_C"),
            ([{"faces": ["#o1.f6"], "emissivity": 0.9, "ambient_C": 25, "surface_to_surface": "yes"}], "surface_to_surface: true"),
            ([{"faces": ["#o1.f6"], "emissivity": 0.9, "ambient_C": 25}, {"faces": ["#o1.f6"], "emissivity": 0.5, "ambient_C": 25}],
             "already radiates in radiation[0]"),
        ]
        for radiation, words in cases:
            with self.subTest(words=words), self.assertRaises(ValueError) as caught:
                self.parse(radiation=radiation)
            self.assertIn(words, str(caught.exception))

    def test_nothing_to_take_the_heat_still_names_radiation(self):
        with self.assertRaises(ValueError) as caught:
            self.parse(heat=[{"faces": ["#o1.f1"], "W": 5}])
        self.assertIn("nowhere for the heat to go, has no steady temperature", str(caught.exception))
        self.assertIn("'radiation' entry", str(caught.exception))

    def test_a_transient_study_takes_radiation_and_nothing_else_needed(self):
        from cadgen._internal.fea.study import parse_study

        study = parse_study({"analysis": "thermal_transient", "material": "aluminum-6061-t6", "initial_C": 500, "end_s": 60,
                             "radiation": [{"faces": ["#o1.f1"], "emissivity": 0.9, "ambient_C": 25}]})
        self.assertEqual(study.inputs.radiation[0].ambient, 25.0)
        self.assertEqual(study.inputs.reference_C, 25.0)

    def test_heat_stress_takes_radiation_through_its_thermal_solve(self):
        from cadgen._internal.fea.study import parse_study

        study = parse_study({"analysis": "thermal_stress", "material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}],
                             "radiation": [{"faces": ["#o1.f2"], "emissivity": 0.9, "ambient_C": 25}]})
        self.assertEqual([(entry.faces, entry.emissivity) for entry in study.inputs.thermal.radiation], [(("#o1.f2",), 0.9)])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ViewFactors(unittest.TestCase):
    """The view factor routine alone, on two triangulated squares facing each other (no mesher)."""

    @staticmethod
    def square(z: float, size: float, cells: int, up: bool):
        import numpy as np

        corners, normals = [], []
        step = size / cells
        for i in range(cells):
            for j in range(cells):
                x0, y0 = -size / 2 + i * step, -size / 2 + j * step
                a, b, c, d = (x0, y0, z), (x0 + step, y0, z), (x0 + step, y0 + step, z), (x0, y0 + step, z)
                corners += [(a, b, c), (a, c, d)]
                normals += [(0, 0, 1 if up else -1)] * 2
        corners = np.array(corners, dtype=float)
        area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        return corners, area, np.array(normals, dtype=float), corners.mean(axis=1)

    def test_two_opposed_squares_match_the_analytic_factor_and_a_plate_between_blocks_them(self):
        import numpy as np

        from cadgen._internal.fea import radiation

        lower = self.square(0.0, 50.0, 10, up=True)
        upper = self.square(50.0, 50.0, 10, up=False)
        corners, area, normal, centroid = (np.concatenate([a, b]) for a, b in zip(lower, upper))
        patch = np.concatenate([np.zeros(len(lower[1]), dtype=np.int64), np.ones(len(upper[1]), dtype=np.int64)])
        F, notes = radiation.view_factors(corners, area, normal, centroid, patch, corners)
        expected = opposed_squares(50.0, 50.0)
        self.assertLess(abs(F[0, 1] - expected) / expected, 0.03, (F[0, 1], expected))
        self.assertAlmostEqual(F[0, 1], F[1, 0], places=12)  # equal areas: reciprocity makes them equal
        self.assertEqual(F[0, 0], 0.0)
        self.assertEqual(notes["method"], "contour integral from each triangle's centroid")
        # A wider plate half-way between: nothing gets through.
        shield = self.square(25.0, 80.0, 4, up=True)[0]
        F_blocked, _ = radiation.view_factors(corners, area, normal, centroid, patch, np.concatenate([corners, shield]))
        self.assertLess(F_blocked[0, 1], 1e-9)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Benchmarks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def plate(self):
        from build123d import Align, Box, export_step

        from cadgen import fea

        step = self.dir / "plate.step"
        export_step(Box(100, 100, 2, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(step))
        faces = fea.faces(step).faces
        top = next(f.ref for f in faces if f.normal and f.normal[2] > 0.9)
        bottom = next(f.ref for f in faces if f.normal and f.normal[2] < -0.9)
        return step, top, bottom

    def test_a_plate_radiating_to_its_surroundings_settles_where_the_closed_form_says(self):
        step, top, bottom = self.plate()
        out = self.dir / "plate.glb"
        result = solve(step, out, {**BASE, "mesh": {"size_mm": 10}, "heat": [{"faces": [bottom], "W": 100}],
                                   "radiation": [{"faces": [top], "emissivity": 0.9, "ambient_C": 25}]})
        self.assertTrue(result.ok)
        expected = (100 / (0.9 * SIGMA * 0.01) + (25 + KELVIN) ** 4) ** 0.25 - KELVIN
        summary = result.summary
        # The radiating face is the plate's coolest; its rise over the surroundings within 1 % of the closed form.
        radiating = summary["min_temperature_C"]
        self.assertLess(abs(radiating - expected) / (expected - 25), 0.01, (radiating, expected))
        self.assertLess(abs(radiating + KELVIN - (expected + KELVIN)) / (expected + KELVIN), 0.01)
        self.assertAlmostEqual(summary["radiation"]["entries"][0]["net_W"], 100.0, places=3)
        self.assertLess(summary["heat_balance"], 1e-6)
        self.assertIn("Newton", result.mesh["solver"])
        extras = glb_extras(out)
        self.assertEqual(extras["study"]["radiation"], [{"faces": [top], "emissivity": 0.9, "ambient_C": 25.0}])
        self.assertTrue(any(line.startswith("radiated 100 W from") for line in result.human_lines()))
        print(f"\n  plate to its surroundings: {radiating:.4f} °C against {expected:.4f} °C closed form "
              f"({100 * (radiating - expected) / (expected - 25):+.3f}% of the rise)")

    def test_two_parallel_plates_see_each_other_by_the_analytic_factor_and_exchange_by_it(self):
        from build123d import Align, Box, Compound, Pos, export_step

        from cadgen import fea

        a, gap, t = 50.0, 50.0, 2.0
        step = self.dir / "plates.step"
        lower = Box(a, a, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        upper = Pos(0, 0, t + gap) * Box(a, a, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        export_step(Compound([lower, upper]), str(step))
        faces = fea.faces(step).faces

        def at(z, sign):
            return next(f.ref for f in faces if f.normal and f.normal[2] * sign > 0.9 and abs(f.center_mm[2] - z) < 1e-6)

        hot_back, hot_face, cold_face, cold_back = at(0, -1), at(t, 1), at(t + gap, -1), at(2 * t + gap, 1)
        hot, cold = 500.0, 25.0
        result = solve(step, self.dir / "plates.glb", {
            **BASE, "mesh": {"size_mm": 5},
            "temperatures": [{"faces": [hot_back], "C": hot}, {"faces": [cold_back], "C": cold}],
            "radiation": [{"faces": [hot_face], "emissivity": 1, "ambient_C": cold, "surface_to_surface": True},
                          {"faces": [cold_face], "emissivity": 1, "ambient_C": cold, "surface_to_surface": True}],
        })
        self.assertTrue(result.ok)
        radiation = result.summary["radiation"]
        F = radiation["view_factors"][0][1]
        expected_F = opposed_squares(a, gap)
        self.assertLess(abs(F - expected_F) / expected_F, 0.03, (F, expected_F))
        self.assertEqual(radiation["view_factors"][0][0], 0.0)
        # The cold plate's face takes in exactly the exchange (its surroundings are at its own temperature).
        exchange = -radiation["entries"][1]["net_W"]
        expected_Q = (a / 1000) ** 2 * expected_F * SIGMA * ((hot + KELVIN) ** 4 - (cold + KELVIN) ** 4)
        self.assertLess(abs(exchange - expected_Q) / expected_Q, 0.05, (exchange, expected_Q))
        self.assertGreater(radiation["rays"], 0)
        print(f"\n  parallel plates: view factor {F:.5f} against {expected_F:.5f} ({100 * (F - expected_F) / expected_F:+.2f}%), "
              f"exchange {exchange:.4f} W against {expected_Q:.4f} W ({100 * (exchange - expected_Q) / expected_Q:+.2f}%)")

    def cube_cooling(self, study_changes: dict):
        from build123d import Box, export_step

        from cadgen import fea

        step = self.dir / "cube.step"
        export_step(Box(10, 10, 10), str(step))
        faces = [face.ref for face in fea.faces(step).faces]
        study = {"analysis": "thermal_transient", "material": "aluminum-6061-t6", "mesh": {"size_mm": 5},
                 "initial_C": 500, "end_s": 300, "step_s": 1.0,
                 "radiation": [{"faces": faces, "emissivity": 0.9, "ambient_C": 25}], **study_changes}
        out = self.dir / "cube.glb"
        result = solve(step, out, study)
        return result, json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))

    @staticmethod
    def lumped(t: float) -> float:
        """The lumped cube's temperature (°C) at ``t`` s, from the analytic integral."""
        material = lookup_material("aluminum-6061-t6")
        rho, c = material.density * 1e12, material.specific_heat
        V, A = 1e-6, 6e-4
        a = 25 + KELVIN
        T0 = 500 + KELVIN

        def G(T):
            return (math.log((T - a) / (T + a)) - 2 * math.atan(T / a)) / (4 * a ** 3)

        k = 0.9 * SIGMA * A / (rho * c * V)
        low, high = a + 1e-9, T0
        for _ in range(200):  # bisection on t(T) = (G(T0) - G(T)) / k, falling in T
            middle = 0.5 * (low + high)
            if (G(T0) - G(middle)) / k > t:
                low = middle
            else:
                high = middle
        return 0.5 * (low + high) - KELVIN

    def test_a_small_cube_cools_by_radiation_as_the_lumped_integral(self):
        result, sidecar = self.cube_cooling({})
        self.assertTrue(result.ok)
        curve = sidecar["curves"]["max_temperature_C"]
        worst = 0.0
        for t, T in zip(curve["x"], curve["y"]):
            if t > 0:
                expected = self.lumped(t)
                worst = max(worst, abs(T - expected) / (expected - 25))
        self.assertLess(worst, 0.03)
        end = self.lumped(300)
        self.assertLess(abs(result.summary["final_max_temperature_C"] - end) / (end - 25), 0.03)
        self.assertIn("radiation_at_end", result.summary)
        print(f"\n  radiative cooling: {result.summary['final_max_temperature_C']:.3f} °C at 300 s against {end:.3f} °C "
              f"(worst {100 * worst:.2f}% of the rise over the run)")

    def test_the_ladder_lets_the_step_grow_and_the_cube_still_follows_the_integral(self):
        result, sidecar = self.cube_cooling({"fit": {"seconds": 0.001, "allow": ["adaptive_steps"]}, "step_s": 0.5})
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in sidecar["fit"]]
        self.assertIn("adaptive_steps", rungs)
        self.assertTrue(any(line.startswith("adapted: Let the time step grow") for line in result.human_lines()))
        self.assertTrue(any(f["type"] == "fit_adaptive_steps" for f in result.findings))
        end = self.lumped(300)
        self.assertLess(abs(result.summary["final_max_temperature_C"] - end) / (end - 25), 0.03)
        self.assertTrue(result.summary["adaptive"])
        print(f"\n  radiative cooling, adaptive steps: {result.summary['final_max_temperature_C']:.3f} °C against {end:.3f} °C "
              f"in {result.summary['steps']} steps")


if __name__ == "__main__":
    unittest.main()
