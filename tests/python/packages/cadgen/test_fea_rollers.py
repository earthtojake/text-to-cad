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
- ``mesh.refine`` (the Hertz benchmark's finer ball) parses and places its points;
- a modal, a harmonic and a nonlinear study on rollers give the same answer
  with the block square to the axes and turned (the turned frame through the
  eigen solves and the nonlinear driver).
The STEPs are build123d solids written to temporary directories.
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
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

FORCE = 2000.0
SIZE = (10.0, 20.0, 30.0)
E, NU = 200_000.0, 0.30  # the table's steel


def _glb(path: Path):
    """Undeformed CAD-mm positions, CAD-mm displacement, the von Mises field and the extras."""
    import numpy as np

    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    binary = raw[20 + length + 8:]
    primitive = gltf["meshes"][0]["primitives"][0]

    def read(name: str, width: int):
        accessor = gltf["accessors"][primitive["attributes"][name]]
        view = gltf["bufferViews"][accessor["bufferView"]]
        return np.frombuffer(binary, np.float32, accessor["count"] * width, view["byteOffset"]).reshape(-1, width).astype(float)

    extras = gltf["meshes"][0]["extras"]
    moved = read("_DISPLACEMENT", 3)
    at = read("POSITION", 3) - extras["deformation_scale"] * moved
    to_cad = lambda v: np.c_[v[:, 0], -v[:, 2], v[:, 1]] * 1000.0  # noqa: E731  glTF (x, z, -y) metres -> CAD mm
    return to_cad(at), to_cad(moved), read("_VON_MISES", 1)[:, 0], extras


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
    return step, faces, (c, s)


def _uniaxial(directory: Path, angle: float, **more):
    from cadgen import fea

    step, faces, _ = _block(directory, angle)
    study = {"material": "steel", "mesh": {"size_mm": 6.0},
             "fixtures": [{"faces": [faces["-x"], faces["-y"], faces["-z"]], "type": "roller"}],
             "loads": [{"faces": [faces["+z"]], "type": "force", "vector_N": [0, 0, FORCE]}], **more}
    if study.get("analysis") == "modal":
        study.pop("loads")
    with redirect_stderr(io.StringIO()):
        return fea.solve(step, directory / f"block{angle:g}.fea.glb", study=study), faces


class StudyFile(unittest.TestCase):
    def test_a_fixture_is_fixed_by_default_or_a_roller(self):
        base = {"material": "steel", "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 1]}]}
        parsed = parse_study({**base, "fixtures": [{"faces": ["#o1.f1"]}, {"faces": ["#o1.f3"], "type": "roller"}]})
        self.assertEqual([fixture.type for fixture in parsed.fixtures], ["fixed", "roller"])
        with self.assertRaisesRegex(ValueError, r"fixtures\[0\]\.type: 'pinned' is not one of \('fixed', 'roller'\)"):
            parse_study({**base, "fixtures": [{"faces": ["#o1.f1"], "type": "pinned"}]})

    def test_mesh_refine_names_balls_meshed_finer(self):
        from cadgen._internal.fea.study import refine_points

        base = {"material": "steel", "fixtures": [{"faces": ["#o1.f1"]}],
                "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 1]}]}
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


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class UniaxialBlock(unittest.TestCase):
    """10 x 20 x 30 mm steel on rollers on its x, y and z = 0 faces, pulled by 2000 N on its top: σ = 10 MPa."""

    def _check(self, result, rotation):
        import numpy as np

        at, moved, von_mises, extras = _glb(result.glb)
        stress = FORCE / (SIZE[0] * SIZE[1])
        strain = stress / E
        # Every node: von Mises F/A, in the free uniaxial state (no clamp spoils it).
        self.assertLess(float(np.abs(von_mises - stress).max()), 1e-4 * stress)
        self.assertAlmostEqual(result.summary["max_von_mises_MPa"], stress, delta=1e-4 * stress)
        # In the block's own axes: stretched ε along the pull, narrowed ν ε across it, from the rollers' corner.
        c, s = rotation
        own = np.c_[at[:, 0] * c + at[:, 1] * s, -at[:, 0] * s + at[:, 1] * c, at[:, 2]]
        own_moved = np.c_[moved[:, 0] * c + moved[:, 1] * s, -moved[:, 0] * s + moved[:, 1] * c, moved[:, 2]]
        expected = np.c_[-NU * strain * own[:, 0], -NU * strain * own[:, 1], strain * own[:, 2]]
        self.assertLess(float(np.abs(own_moved - expected).max()), 1e-4 * strain * SIZE[2])
        self.assertAlmostEqual(result.summary["reaction_force_N"][2], -FORCE, delta=1e-6 * FORCE)
        self.assertEqual([fixture["type"] for fixture in extras["study"]["fixtures"]], ["roller"])

    def test_rollers_on_three_faces_give_the_free_uniaxial_state(self):
        with tempfile.TemporaryDirectory() as name:
            result, _ = _uniaxial(Path(name), 0.0)
            self._check(result, (1.0, 0.0))

    def test_the_block_turned_on_sloped_rollers_gives_the_same_state_in_its_own_axes(self):
        with tempfile.TemporaryDirectory() as name:
            result, _ = _uniaxial(Path(name), 30.0)
            self._check(result, (math.cos(math.radians(30.0)), math.sin(math.radians(30.0))))

    def test_rollers_on_one_face_leave_the_part_free_and_say_so(self):
        with tempfile.TemporaryDirectory() as name, self.assertRaises(ValueError) as caught:
            from cadgen import fea

            step, faces, _ = _block(Path(name), 0.0)
            with redirect_stderr(io.StringIO()):
                fea.solve(step, Path(name) / "loose.fea.glb", study={
                    "material": "steel", "mesh": {"size_mm": 8.0}, "fixtures": [{"faces": [faces["-z"]], "type": "roller"}],
                    "loads": [{"faces": [faces["+z"]], "type": "force", "vector_N": [0, 0, FORCE]}]})
        self.assertIn("the fixtures leave the part free to slide or turn (3 of its 6 rigid motions)", str(caught.exception))


    def test_rollers_in_separate_fixtures_count_their_shared_edges_once(self):
        """The three rollers as three fixtures meet at edges: each edge DOF's reaction is counted once, so the
        fixtures' reactions sum to the pull and no "do not balance" warning appears."""
        from cadgen import fea

        with tempfile.TemporaryDirectory() as name:
            step, faces, _ = _block(Path(name), 0.0)
            study = {"material": "steel", "mesh": {"size_mm": 6.0},
                     "fixtures": [{"faces": [faces[side]], "type": "roller"} for side in ("-x", "-y", "-z")],
                     "loads": [{"faces": [faces["+z"]], "type": "force", "vector_N": [0, 0, FORCE]}]}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, Path(name) / "three.fea.glb", study=study)
            sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertFalse([w for w in sidecar["warnings"] if "do not balance" in w], sidecar["warnings"])
        reactions = [fixture["reaction_N"] for fixture in sidecar["fixtures"]]
        self.assertEqual(len(reactions), 3)
        for c in range(3):
            self.assertAlmostEqual(sum(r[c] for r in reactions), -FORCE if c == 2 else 0.0, delta=1e-6 * FORCE)
        # The floor (-z) carries the pull; the two side rollers carry nothing along it.
        self.assertAlmostEqual(reactions[2][2], -FORCE, delta=1e-6 * FORCE)
        self.assertAlmostEqual(reactions[0][2], 0.0, delta=1e-6 * FORCE)

@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
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
            rest = [f.ref for f in listed if f.ref != top]
            study = {"material": "steel", "mesh": {"size_mm": 2.5},
                     "fixtures": [{"faces": rest, "type": "roller"}],
                     "loads": [{"faces": [top], "type": "pressure", "pressure_MPa": pressure}]}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, Path(name) / "quarter.fea.glb", study=study)
            at, moved, von_mises, _ = _glb(result.glb)
        expected = pressure * (1 - 2 * NU) / (1 - NU)
        self.assertAlmostEqual(float(np.median(von_mises)) / expected, 1.0, delta=0.03)
        # It only shortens: the curved roller keeps it from bulging out.
        squeeze = pressure * (1 + NU) * (1 - 2 * NU) / ((1 - NU) * E) * height
        top_nodes = np.abs(at[:, 2] - height) < 1e-6
        self.assertAlmostEqual(float(-moved[top_nodes, 2].mean()) / squeeze, 1.0, delta=0.03)
        self.assertLess(float(np.abs(moved[:, :2]).max()), 0.05 * squeeze)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class TurnedFrames(unittest.TestCase):
    """Square to the axes or turned 30°, the same block on the same rollers answers the same."""

    def _both(self, **more):
        with tempfile.TemporaryDirectory() as name:
            square, _ = _uniaxial(Path(name), 0.0, **more)
            turned, _ = _uniaxial(Path(name), 30.0, **more)
        return square, turned

    def test_its_modes(self):
        square, turned = self._both(analysis="modal", modes=3)
        first, second = ([mode["frequency_Hz"] for mode in r.summary["modes"]] for r in (square, turned))
        self.assertEqual((square.summary["rigid_body_modes"], turned.summary["rigid_body_modes"]), (0, 0))
        self.assertEqual(len(first), 3)
        for a, b in zip(first, second):
            self.assertAlmostEqual(b / a, 1.0, delta=0.02)  # each its own mesh

    def test_a_harmonic_sweep_through_the_modes(self):
        # The pull swept in frequency: the same response square or turned (the modes found in the rollers' own axes
        # and turned back).
        square, turned = self._both(analysis="harmonic", excitation={"type": "force"}, sweep_Hz=[10, 100])
        for key in ("max_von_mises_MPa", "max_displacement_mm"):
            self.assertAlmostEqual(turned.summary[key] / square.summary[key], 1.0, delta=0.03, msg=key)

    def test_a_nonlinear_pull_past_yield(self):
        material = {"name": "steel", "plasticity": {"tangent_MPa": 0}}
        loads = [{"faces": None, "type": "pressure", "pressure_MPa": -300}]
        with tempfile.TemporaryDirectory() as name:
            results = []
            for angle in (0.0, 30.0):
                from cadgen import fea

                step, faces, _ = _block(Path(name), angle)
                study = {"analysis": "nonlinear", "material": material, "steps": 4, "mesh": {"size_mm": 8.0},
                         "fixtures": [{"faces": [faces["-x"], faces["-y"], faces["-z"]], "type": "roller"}],
                         "loads": [{**loads[0], "faces": [faces["+z"]]}]}
                with redirect_stderr(io.StringIO()):
                    results.append(fea.solve(step, Path(name) / f"pull{angle:g}.fea.glb", study=study))
        square, turned = (r.summary for r in results)
        # 300 MPa pulls the 250 MPa steel past yield, perfectly plastic: it collapses at yield over load, 250/300.
        self.assertTrue(square["collapsed"])
        self.assertAlmostEqual(square["load_percent"] / (100 * 250 / 300), 1.0, delta=0.02)
        self.assertAlmostEqual(turned["load_percent"] / square["load_percent"], 1.0, delta=0.02)


if __name__ == "__main__":
    unittest.main()
