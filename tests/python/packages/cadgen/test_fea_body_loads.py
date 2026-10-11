"""Static body loads: a cantilever under its own weight against beam theory, and an accelerated part.

The beam is a build123d box written to a temporary STEP: 100 mm long, 6 x 6 mm
steel, clamped at x = 0. Its own weight is a uniform load q = ρ g A, so the
tip deflects w = q L^4 / (8 E I) (shear adds under half a percent at this
slenderness). Accelerating the part up at 1 g loads it exactly as gravity
down does, and the reactions carry the weight.
"""

from __future__ import annotations

import io
import json
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

LENGTH, SIDE = 100.0, 6.0
STEEL = lookup_material("steel")
G0 = 9806.65


def _tip_deflection() -> float:
    q = STEEL.density * G0 * SIDE * SIDE
    inertia = SIDE ** 4 / 12.0
    return q * LENGTH ** 4 / (8.0 * STEEL.E * inertia)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SelfWeight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(step))
        planes = {face.center_mm[0]: face.ref for face in fea.faces(step).faces
                  if face.surface == "plane" and face.normal and abs(abs(face.normal[0]) - 1) < 1e-6}
        cls.fixed = planes[min(planes)]
        base = {"material": "steel", "fixtures": [{"faces": [cls.fixed]}], "mesh": {"size_mm": 2.0}}
        with redirect_stderr(io.StringIO()):
            cls.gravity = fea.solve(step, directory / "gravity.glb",
                                    study={**base, "loads": [{"type": "gravity", "vector_g": [0, 0, -1]}]})
            cls.lifted = fea.solve(step, directory / "lifted.glb",
                                   study={**base, "loads": [{"type": "acceleration", "vector_g": [0, 0, 1]}]})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_tip_sags_as_beam_theory_says(self):
        summary = self.gravity.summary
        self.assertAlmostEqual(summary["max_displacement_mm"] / _tip_deflection(), 1.0, delta=0.03)
        self.assertAlmostEqual(summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)

    def test_the_weight_is_applied_and_the_clamp_carries_it(self):
        weight = STEEL.density * LENGTH * SIDE * SIDE * G0
        applied, reaction = self.gravity.summary["applied_force_N"], self.gravity.summary["reaction_force_N"]
        self.assertAlmostEqual(applied[2] / -weight, 1.0, delta=1e-3)
        self.assertAlmostEqual(reaction[2] / weight, 1.0, delta=1e-3)
        self.assertEqual(self.gravity.warnings, ())

    def test_accelerating_up_loads_it_as_gravity_down(self):
        self.assertEqual(self.lifted.summary["max_displacement_mm"], self.gravity.summary["max_displacement_mm"])
        self.assertEqual(self.lifted.summary["applied_force_N"], self.gravity.summary["applied_force_N"])

    def test_the_glb_echoes_the_body_load_without_faces(self):
        raw = self.gravity.glb.read_bytes()
        length, _ = struct.unpack_from("<II", raw, 12)
        extras = json.loads(raw[20:20 + length])["meshes"][0]["extras"]
        self.assertEqual(extras["study"]["loads"], [{"type": "gravity", "vector_g": [0.0, 0.0, -1.0]}])
        self.assertNotIn("analysis", extras)


if __name__ == "__main__":
    unittest.main()
