"""The ladder's idealise rung: a thin plate solved as a shell and a slender rod as a beam, each within 5 % of theory.

Both are reached through the ladder: a static study on a small part with a
tiny budget in its ``fit`` (a kilobyte and a millisecond), allowed only the
idealise rung, so the rung is needed and the run costs seconds. Each case
asserts the run completed, the step is in the GLB's ``extras.fit``, the
sidecar's ``fit``, the CLI lines and an info finding, it carries its model-error
note, and the answer holds against plate or beam theory. Detection is
unambiguous or nothing is taken: a stepped plate, a thick plate and a stubby
bar stay solid. The STEPs are written by build123d into temporary directories.
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

#: Small enough that nothing fits: the rung the study allows is taken.
TINY = {"memory_GB": 1e-6, "seconds": 1e-3}
#: Steel, as cadgen's table has it: MPa.
E, NU = 200_000.0, 0.3


def _extras(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])["meshes"][0]["extras"]


def _solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study={**study, "fit": {**TINY, "allow": ["idealise"]}})


def _assert_idealised(test, result, idealisation: str) -> dict:
    """The idealise step is in the result, the GLB, the sidecar, the CLI and the findings, with its model error."""
    test.assertTrue(result.ok)
    step = next(step for step in result.fit if step["rung"] == "idealise")
    test.assertEqual(step["detail"]["idealisation"], idealisation)
    test.assertEqual(_extras(result.glb)["fit"], list(result.fit))
    test.assertEqual(json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"], list(result.fit))
    test.assertIn(f"adapted: {step['words']} ({step['accuracy']})", result.human_lines())
    test.assertIn("fit_idealise", [f["type"] for f in result.findings if f["severity"] == "info"])
    test.assertIn("model error", step["accuracy"])
    test.assertAlmostEqual(step["accuracy_pct"], round(100 * step["detail"]["slenderness"] ** 2, 2), places=2)
    return step


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ThinPlate(unittest.TestCase):
    """A 100 x 100 x 1 mm steel plate clamped on its four sides under 0.01 MPa (Timoshenko's clamped square plate)."""

    A, T, Q = 100.0, 1.0, 0.01

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "plate.step"
        export_step(Box(cls.A, cls.A, cls.T), str(step))
        faces = fea.faces(step).faces
        sides = [f.ref for f in faces if f.normal is not None and abs(f.normal[2]) < 1e-6]
        top = next(f.ref for f in faces if f.normal is not None and f.normal[2] > 0.99)
        cls.result = _solve(step, directory / "plate.glb", {
            "material": "steel", "fixtures": [{"faces": sides}],
            "loads": [{"faces": [top], "type": "pressure", "pressure_MPa": cls.Q}],
        })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_is_solved_as_a_shell_and_says_so(self):
        step = _assert_idealised(self, self.result, "shell")
        self.assertIn("as its mid-surface (a shell)", step["words"])
        self.assertAlmostEqual(step["detail"]["thickness_mm"], self.T)
        # The GLB is the real part: its six faces, not a sheet.
        self.assertEqual(len(_extras(self.result.glb)["faces"]), 6)

    def test_centre_deflection_and_edge_stress_hold_plate_theory_within_five_percent(self):
        D = E * self.T ** 3 / (12 * (1 - NU ** 2))
        deflection = 0.00126 * self.Q * self.A ** 4 / D
        self.assertAlmostEqual(self.result.summary["max_displacement_mm"] / deflection, 1.0, delta=0.05)
        # The clamped edge's middle: sigma_x = 6 (0.0513 q a^2) / t^2 and sigma_y = nu sigma_x there.
        edge = 6 * 0.0513 * self.Q * self.A ** 2 / self.T ** 2 * math.sqrt(1 - NU + NU ** 2)
        self.assertAlmostEqual(self.result.summary["max_von_mises_MPa"] / edge, 1.0, delta=0.05)
        self.assertAlmostEqual(self.result.summary["reaction_force_N"][2], self.Q * self.A ** 2, delta=1e-6)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SlenderRod(unittest.TestCase):
    """A 200 mm long, 6 mm steel rod along X, fixed at one end with 5 N across the other: tip w = P L^3 / (3 E I)."""

    L, D, P = 200.0, 6.0, 5.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Cylinder, Rot, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "rod.step"
        export_step(Rot(0, 90, 0) * Cylinder(cls.D / 2, cls.L, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(step))
        ends = sorted((f for f in fea.faces(step).faces if f.surface == "plane"), key=lambda f: f.center_mm[0])
        cls.result = _solve(step, directory / "rod.glb", {
            "material": "steel", "fixtures": [{"faces": [ends[0].ref]}],
            "loads": [{"faces": [ends[-1].ref], "type": "force", "vector_N": [0, 0, -cls.P]}],
        })

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_is_solved_as_a_beam_and_says_so(self):
        step = _assert_idealised(self, self.result, "beam")
        self.assertIn("as a beam along its centreline", step["words"])
        self.assertAlmostEqual(step["detail"]["section_mm"], self.D, places=3)

    def test_tip_deflection_and_root_stress_hold_beam_theory_within_five_percent(self):
        I = math.pi * self.D ** 4 / 64
        self.assertAlmostEqual(self.result.summary["max_displacement_mm"] / (self.P * self.L ** 3 / (3 * E * I)), 1.0, delta=0.05)
        self.assertAlmostEqual(self.result.summary["max_von_mises_MPa"] / (self.P * self.L * self.D / 2 / I), 1.0, delta=0.05)


class Detection(unittest.TestCase):
    """The rung is taken only when the part is unambiguously a thin plate or a slender bar."""

    @staticmethod
    def _geometry(part):
        from cadgen._internal.fea import fit

        return fit.geometry_of(part.wrapped)

    def test_only_unambiguous_plates_and_bars_are_idealised(self):
        from build123d import Box, Cylinder, Pos

        from cadgen._internal.fea import beam, shell

        plate = self._geometry(Box(100, 80, 1) - Pos(20, 0, 0) * Cylinder(5, 2))
        self.assertIsNotNone(shell.detect(plate))
        self.assertIsNone(beam.detect(plate))
        rod = self._geometry(Box(200, 6, 6))
        self.assertIsNotNone(beam.detect(rod))
        self.assertIsNone(shell.detect(rod))
        for part in (
            Box(100, 100, 1) + Pos(0, 0, 1) * Box(10, 10, 1),   # a boss: two thicknesses
            Box(20, 20, 2),                                     # thick for its span
            Box(40, 4, 4),                                      # stubby
            Box(200, 6, 6) - Pos(50, 0, 0) * Cylinder(1, 10),   # a cross hole: not a prism
        ):
            geometry = self._geometry(part)
            self.assertIsNone(shell.detect(geometry))
            self.assertIsNone(beam.detect(geometry))


if __name__ == "__main__":
    unittest.main()
