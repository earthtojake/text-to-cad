"""Roller supports: a face that slides in its own plane but never moves along its normal.

Benchmarks:
- a block on rollers on three faces that meet at a corner, pulled on the
  opposite face, is in the free uniaxial stress state exactly: von Mises F/A at
  every node, the stretch ε = F/(AE) along the pull and the lateral contraction
  ν ε across it, at every node;
- the same block turned 30° about Z (its rollers on sloped faces, held in their
  nodes' own axes) gives the same state in its own axes;
- a quarter cylinder on rollers on its two cut planes, its base and its curved
  side (normal per facet), pressed on its top, is confined: σ_r = σ_θ =
  ν/(1-ν) σ_z, so von Mises p (1-2ν)/(1-ν), within 3 %;
- rollers on one face alone leave the part free to slide: a plain error;
- ``mesh.refine`` (the Hertz benchmark's finer ball) parses and places its points.
The STEPs are build123d solids written to temporary directories.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import glb_array, glb_extras, needs_fea, reported, solve, value_error
from tests.python.support.fea_fixtures import STEEL_NUMBERS  # noqa: E402

from cadgen._internal.fea.study import parse_study  # noqa: E402

FORCE = 2000.0
SIZE = (10.0, 20.0, 30.0)
E, NU = 200_000.0, 0.30  # the table's steel


def _glb(path: Path):
    """Undeformed CAD-mm positions, CAD-mm displacement, the von Mises field and the extras."""
    import numpy as np

    extras = glb_extras(path)
    moved = glb_array(path, "_DISPLACEMENT", 3)
    at = glb_array(path, "POSITION", 3) - extras["deformation_scale"] * moved
    to_cad = lambda v: np.c_[v[:, 0], -v[:, 2], v[:, 1]] * 1000.0  # noqa: E731  glTF (x, z, -y) metres -> CAD mm
    return to_cad(at), to_cad(moved), glb_array(path, "_VON_MISES")[:, 0], extras


def _block(directory: Path, angle: float):
    """The block turned ``angle`` degrees about Z, its faces by outward normal in its own axes (-x, -y, -z, +z)."""
    from build123d import Align, Box, Rotation, export_step

    from cadgen import fea

    step = directory / f"block{angle:g}.step"
    export_step(Rotation(0, 0, angle) * Box(*SIZE, align=Align.MIN), str(step))
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    wanted = {"-x": (-c, -s, 0.0), "-y": (s, -c, 0.0), "-z": (0.0, 0.0, -1.0), "+z": (0.0, 0.0, 1.0)}
    faces = {}
    for face in fea.faces(step).faces:
        for name, normal in wanted.items():
            if face.normal and all(abs(a - b) < 1e-6 for a, b in zip(face.normal, normal)):
                faces[name] = face.ref
    return step, faces


def _pull(faces) -> dict:
    return {"faces": [faces["+z"]], "type": "force", "vector_N": [0, 0, FORCE]}


def _uniaxial(directory: Path, angle: float, **more):
    step, faces = _block(directory, angle)
    study = {"material": STEEL_NUMBERS, "mesh": {"size_mm": 6.0},
             "fixtures": [{"faces": [faces["-x"], faces["-y"], faces["-z"]], "type": "roller"}],
             "loads": [_pull(faces)], **more}
    return solve(step, directory / f"block{angle:g}.fea.glb", study)


class StudyFile(unittest.TestCase):
    def test_a_fixture_is_fixed_by_default_or_a_roller(self):
        base = {"material": STEEL_NUMBERS, "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [0, 0, 1]}]}
        parsed = parse_study({**base, "fixtures": [{"faces": ["face 1"]}, {"faces": ["face 3"], "type": "roller"}]})
        self.assertEqual([fixture.type for fixture in parsed.fixtures], ["fixed", "roller"])
        with self.assertRaisesRegex(ValueError, r"fixtures\[0\]\.type: 'pinned' is not one of \('fixed', 'roller'\)"):
            parse_study({**base, "fixtures": [{"faces": ["face 1"], "type": "pinned"}]})

    def test_mesh_refine_names_balls_meshed_finer(self):
        from cadgen._internal.fea.study import refine_points

        base = {"material": STEEL_NUMBERS, "fixtures": [{"faces": ["face 1"]}],
                "loads": [{"faces": ["face 2"], "type": "force", "vector_N": [0, 0, 1]}]}
        ball = {"center_mm": [1, 2, 3], "radius_mm": 1.0, "size_mm": 0.5}
        parsed = parse_study({**base, "mesh": {"size_mm": 3, "refine": [ball]}})
        self.assertEqual(parsed.mesh_refine, (((1.0, 2.0, 3.0), 1.0, 0.5),))
        points = refine_points(parsed.mesh_refine)
        self.assertIn([1.0, 2.0, 3.0, 0.5], points)
        self.assertTrue(all((x - 1) ** 2 + (y - 2) ** 2 + (z - 3) ** 2 <= 1.0 + 1e-9 for x, y, z, _ in points))
        self.assertEqual(parse_study(base).mesh_refine, ())
        for bad, words in (([], "a list of balls"), ([{"center_mm": [0, 0, 0], "radius_mm": 1}], "give center_mm, radius_mm"),
                           ([{**ball, "size_mm": 0}], r"mesh.refine\[0\].size_mm"),
                           ([{**ball, "radius_mm": 100, "size_mm": 0.1}], "too many local sizes")):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                parse_study({**base, "mesh": {"refine": bad}})


@needs_fea
class UniaxialBlock(unittest.TestCase):
    """10 x 20 x 30 mm steel on rollers on its x, y and z = 0 faces, pulled by 2000 N on its top: σ = 10 MPa."""

    def test_rollers_give_the_free_uniaxial_state_square_or_turned_on_sloped_rollers(self):
        import numpy as np

        stress = FORCE / (SIZE[0] * SIZE[1])
        strain = stress / E
        for angle in (0.0, 30.0):
            with self.subTest(angle=angle), tempfile.TemporaryDirectory() as name:
                result = _uniaxial(Path(name), angle)
                at, moved, von_mises, extras = _glb(result.glb)
                # Every node: von Mises F/A, in the free uniaxial state (no clamp spoils it).
                self.assertLess(float(np.abs(von_mises - stress).max()), 1e-4 * stress)
                self.assertAlmostEqual(result.summary["max_von_mises_MPa"], stress, delta=1e-4 * stress)
                # In the block's own axes: stretched ε along the pull, narrowed ν ε across it, from the rollers' corner.
                c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                own = np.c_[at[:, 0] * c + at[:, 1] * s, -at[:, 0] * s + at[:, 1] * c, at[:, 2]]
                own_moved = np.c_[moved[:, 0] * c + moved[:, 1] * s, -moved[:, 0] * s + moved[:, 1] * c, moved[:, 2]]
                expected = np.c_[-NU * strain * own[:, 0], -NU * strain * own[:, 1], strain * own[:, 2]]
                self.assertLess(float(np.abs(own_moved - expected).max()), 1e-4 * strain * SIZE[2])
                self.assertAlmostEqual(result.summary["reaction_force_N"][2], -FORCE, delta=1e-6 * FORCE)
                self.assertEqual([fixture["type"] for fixture in extras["study"]["fixtures"]], ["roller"])

    def test_rollers_on_one_face_leave_the_part_free_and_say_so(self):
        with tempfile.TemporaryDirectory() as name:
            step, faces = _block(Path(name), 0.0)
            message = value_error(self, solve, step, Path(name) / "loose.fea.glb", {
                "material": STEEL_NUMBERS, "mesh": {"size_mm": 8.0}, "fixtures": [{"faces": [faces["-z"]], "type": "roller"}],
                "loads": [_pull(faces)]})
        self.assertIn("the fixtures leave the part free to slide or turn (3 of its 6 rigid motions)", message)

    def test_rollers_in_separate_fixtures_count_their_shared_edges_once(self):
        """Three roller fixtures meet at edges: each edge DOF's reaction is counted once, so the fixtures'
        reactions sum to the pull and no "do not balance" warning appears."""
        with tempfile.TemporaryDirectory() as name:
            step, faces = _block(Path(name), 0.0)
            written = reported(solve(step, Path(name) / "three.fea.glb", {
                "material": STEEL_NUMBERS, "mesh": {"size_mm": 6.0},
                "fixtures": [{"faces": [faces[side]], "type": "roller"} for side in ("-x", "-y", "-z")],
                "loads": [_pull(faces)]}))
        self.assertFalse([w for w in written["warnings"] if "do not balance" in w], written["warnings"])
        reactions = [fixture["reaction_N"] for fixture in written["fixtures"]]
        self.assertEqual(len(reactions), 3)
        for c in range(3):
            self.assertAlmostEqual(sum(r[c] for r in reactions), -FORCE if c == 2 else 0.0, delta=1e-6 * FORCE)
        # The floor (-z) carries the pull; the two side rollers carry nothing along it.
        self.assertAlmostEqual(reactions[2][2], -FORCE, delta=1e-6 * FORCE)
        self.assertAlmostEqual(reactions[0][2], 0.0, delta=1e-6 * FORCE)


@needs_fea
class ConfinedCylinder(unittest.TestCase):
    """A quarter cylinder (R 10, H 10) on rollers on every face but its top, pressed by 10 MPa: confined compression."""

    def test_a_roller_on_a_curved_face_holds_it_along_its_normal(self):
        import numpy as np
        from build123d import Align, Box, Cylinder, export_step

        from cadgen import fea

        pressure, radius, height = 10.0, 10.0, 10.0
        with tempfile.TemporaryDirectory() as name:
            step = Path(name) / "quarter.step"
            export_step(Cylinder(radius, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
                        & Box(radius, radius, height, align=Align.MIN), str(step))
            listed = fea.faces(step).faces
            top = next(f.ref for f in listed if f.normal and f.normal[2] > 0.999)
            result = solve(step, Path(name) / "quarter.fea.glb", {
                "material": STEEL_NUMBERS, "mesh": {"size_mm": 2.5},
                "fixtures": [{"faces": [f.ref for f in listed if f.ref != top], "type": "roller"}],
                "loads": [{"faces": [top], "type": "pressure", "pressure_MPa": pressure}]})
            at, moved, von_mises, _ = _glb(result.glb)
        expected = pressure * (1 - 2 * NU) / (1 - NU)
        self.assertAlmostEqual(float(np.median(von_mises)) / expected, 1.0, delta=0.03)
        # It only shortens: the curved roller keeps it from bulging out.
        squeeze = pressure * (1 + NU) * (1 - 2 * NU) / ((1 - NU) * E) * height
        top_nodes = np.abs(at[:, 2] - height) < 1e-6
        self.assertAlmostEqual(float(-moved[top_nodes, 2].mean()) / squeeze, 1.0, delta=0.03)
        self.assertLess(float(np.abs(moved[:, :2]).max()), 0.05 * squeeze)


if __name__ == "__main__":
    unittest.main()
