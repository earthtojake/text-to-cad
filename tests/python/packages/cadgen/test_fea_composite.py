"""Composites: orthotropic solids and laminated plates, against the compliance matrix and classical laminate theory.

Benchmarks:
- an orthotropic block under uniaxial stress (rollers on three faces, a force on
  the fourth) gives the compliance matrix's strains within 1 %;
- a symmetric cross-ply [0/90]s laminate's A, B and D match a hand CLT
  calculation within 1e-6 relative, and the rotated ply stiffness matches the
  textbook Q̄ formulas;
- that laminate as a long strip clamped on its long sides under pressure
  deflects at its centre as CLT's cylindrical bending says, q a^4 / (384 D11),
  within 5 %;
- a ply's Tsai-Wu index under a known stress matches the hand formula, in the
  module and in a solved result's worst ply;
- a thick laminate under a tiny budget takes the iterative, local_refine and
  symmetry rungs, completes, and keeps its worst ply within 10 % of the
  unadapted run.
The STEPs are written by build123d into temporary directories.
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

#: T300/5208 carbon-epoxy, Tsai and Hahn's textbook lamina (MPa).
CFRP = {"E1_MPa": 181000, "E2_MPa": 10300, "nu12": 0.28, "G12_MPa": 7170, "Xt_MPa": 1500, "Xc_MPa": 1500,
        "Yt_MPa": 40, "Yc_MPa": 246, "S_MPa": 68}
#: Small enough that nothing fits: every rung the study allows is taken.
TINY = {"memory_GB": 1e-6, "seconds": 1e-3}


def _layup(angles, thickness):
    return [{"material": "cfrp", "angle_deg": angle, "thickness_mm": thickness} for angle in angles]


def _glb(path: Path):
    """The GLB's undeformed CAD-mm positions, its CAD-mm displacement and its extras."""
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
    return to_cad(at), to_cad(moved), extras, set(primitive["attributes"])


def _attribute(path: Path, name: str):
    """One scalar vertex attribute of a GLB."""
    import numpy as np

    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"][name]]
    view = gltf["bufferViews"][accessor["bufferView"]]
    return np.frombuffer(raw[20 + length + 8:], np.float32, accessor["count"], view["byteOffset"]).astype(float)


class Parsing(unittest.TestCase):
    """Stdlib: the registry, the study and the orthotropic material object."""

    def test_composite_is_built_and_its_check_parses(self):
        from cadgen._internal.fea.analyses import REGISTRY, get_analysis
        from cadgen._internal.fea.analyses.kinds import CHECK_SPECS

        self.assertFalse(REGISTRY["composite"].planned)
        analysis = get_analysis("composite")
        self.assertEqual((analysis.name, analysis.tier, analysis.word), ("composite", 3, "Composite"))
        self.assertEqual(analysis.ladder, ("iterative", "local_refine", "symmetry"))
        self.assertEqual([spec.name for spec in analysis.fields], ["von_mises", "displacement", "failure_index"])
        spec = CHECK_SPECS["ply_failure"]
        self.assertEqual((spec.default_label, spec.scaling, spec.unique), ("Ply failure", "none", True))
        self.assertEqual(spec.parse({"kind": "ply_failure"}, "c"), {"kind": "ply_failure"})
        self.assertEqual(spec.parse({"kind": "ply_failure", "criterion": "tsai_wu", "label": "Skin"}, "c"),
                         {"kind": "ply_failure", "criterion": "tsai_wu", "label": "Skin"})
        with self.assertRaises(ValueError) as caught:
            spec.parse({"kind": "ply_failure", "criterion": "hashin"}, "c")
        self.assertIn("c.criterion", str(caught.exception))

    def test_a_study_parses_and_its_errors_say_what_to_add(self):
        from cadgen._internal.fea.study import parse_study

        base = {"analysis": "composite", "laminae": {"cfrp": CFRP}, "layup": _layup((0, 90, 90, 0), 0.25),
                "fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "pressure", "pressure_MPa": 0.01}]}
        parsed = parse_study(base)
        self.assertIsNone(parsed.material)
        self.assertEqual(len(parsed.inputs.laminate.plies), 4)
        self.assertEqual(parsed.checks, ({"kind": "ply_failure"},))
        lamina = parsed.inputs.laminate.plies[0].lamina
        self.assertEqual((lamina.G13, lamina.nu23), (7170.0, 0.28))
        self.assertAlmostEqual(lamina.G23, 10300 / (2 * 1.28))
        cases = [
            ({"material": "steel"}, "a composite study takes its materials from the plies"),
            ({"layup": []}, "study.layup: the plies from the bottom face up"),
            ({"layup": [{"material": "glass", "angle_deg": 0, "thickness_mm": 1}]}, "'glass' is not in study.laminae"),
            ({"layup": [{"material": "cfrp", "angle_deg": 0}]}, "layup[0].thickness_mm"),
            ({"laminae": {"cfrp": {k: v for k, v in CFRP.items() if k != "Yc_MPa"}}}, "a ply material needs Yc_MPa"),
            ({"layup_axis": [0, 0, 0]}, "study.layup_axis: the direction is zero"),
            ({"loads": [{"type": "gravity", "vector_g": [0, 0, -1]}]}, "needs every ply material's density_t_per_mm3"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({**base, **change})
            self.assertIn(fragment, str(caught.exception))

    def test_an_orthotropic_material_object(self):
        from cadgen._internal.fea.materials import material_from_spec, mirror_symmetric

        block = {"E1_MPa": 135000, "E2_MPa": 10000, "E3_MPa": 10000, "nu12": 0.3, "nu13": 0.3, "nu23": 0.45,
                 "G12_MPa": 5000, "G13_MPa": 5000, "G23_MPa": 3500}
        material = material_from_spec({"name": "ud", "orthotropic": block})
        self.assertEqual((material.E, material.nu, material.yield_strength), (135000.0, 0.3, None))
        self.assertEqual(material.orthotropic["axes"], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        self.assertIn("orthotropic", material.as_dict())
        turned = material_from_spec({"name": "ud", "orthotropic": {**block, "axes": [[1, 1, 0], [-1, 1, 0]]}})
        self.assertTrue(mirror_symmetric(material, 0))
        self.assertFalse(mirror_symmetric(turned, 0))
        self.assertTrue(mirror_symmetric(turned, 2))
        self.assertTrue(mirror_symmetric(material_from_spec("steel"), 1))
        cases = [
            ({**block, "G23_MPa": -1}, "material.orthotropic.G23_MPa: must be > 0"),
            ({k: v for k, v in block.items() if k != "nu23"}, "missing nu23"),
            ({**block, "axes": [[1, 0, 0], [1, 1, 0]]}, "must be perpendicular"),
            ({**block, "nu12": 5.0}, "nu12: 5 is not physically possible"),
            ({**block, "nu12": 0.9, "nu13": 0.9, "nu23": 0.9, "E2_MPa": 135000, "E3_MPa": 135000},
             "not physically possible (the material would gain energy"),
        ]
        for spec, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                material_from_spec({"name": "ud", "orthotropic": spec})
            self.assertIn(fragment, str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "numpy comes with the fea extra")
class LaminateTheory(unittest.TestCase):
    """CLT and the failure criteria by hand."""

    def setUp(self):
        from cadgen._internal.fea.laminate import lamina_from_spec

        self.lamina = lamina_from_spec(CFRP, "cfrp", "cfrp")
        E1, E2, n12, G12 = 181000.0, 10300.0, 0.28, 7170.0
        d = 1 - n12 * n12 * E2 / E1
        self.Q11, self.Q22, self.Q12, self.Q66 = E1 / d, E2 / d, n12 * E2 / d, G12

    def test_a_symmetric_cross_ply_abd_matches_the_hand_calculation(self):
        import numpy as np

        from cadgen._internal.fea.laminate import Laminate, Ply, notation

        t0 = 0.25
        h = 4 * t0
        laminate = Laminate(tuple(Ply(self.lamina, a, t0) for a in (0, 90, 90, 0)))
        A, B, D = laminate.abd()
        Q11, Q22, Q12, Q66 = self.Q11, self.Q22, self.Q12, self.Q66
        hand_A = np.array([[(Q11 + Q22) / 2 * h, Q12 * h, 0], [Q12 * h, (Q11 + Q22) / 2 * h, 0], [0, 0, Q66 * h]])
        c = h ** 3 / 12
        # The outer 0° plies hold 7/8 of the bending inertia, the inner 90° plies 1/8.
        hand_D = np.array([[c * (7 * Q11 + Q22) / 8, Q12 * c, 0], [Q12 * c, c * (Q11 + 7 * Q22) / 8, 0], [0, 0, Q66 * c]])
        for ours, hand in ((A, hand_A), (D, hand_D)):
            nonzero = hand != 0
            self.assertLess(np.max(np.abs(ours[nonzero] / hand[nonzero] - 1)), 1e-6)
            self.assertLess(np.max(np.abs(ours[~nonzero])), 1e-6 * np.abs(hand).max())
        self.assertLess(np.abs(B).max(), 1e-6 * np.abs(A).max())
        self.assertEqual(notation(laminate), "[0/90]s")
        self.assertEqual(notation(Laminate(tuple(Ply(self.lamina, a, t0) for a in (0, 45, -45, 90)))), "[0/45/-45/90]")

    def test_the_rotated_ply_stiffness_is_the_textbook_q_bar(self):
        from cadgen._internal.fea.laminate import q_bar

        Q11, Q22, Q12, Q66 = self.Q11, self.Q22, self.Q12, self.Q66
        for angle in (30.0, 45.0, -60.0):
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            Qb = q_bar(self.lamina, angle)
            with self.subTest(angle=angle):
                self.assertAlmostEqual(Qb[0, 0] / (Q11 * c ** 4 + 2 * (Q12 + 2 * Q66) * s * s * c * c + Q22 * s ** 4), 1, 12)
                self.assertAlmostEqual(Qb[1, 1] / (Q11 * s ** 4 + 2 * (Q12 + 2 * Q66) * s * s * c * c + Q22 * c ** 4), 1, 12)
                q16 = (Q11 - Q12 - 2 * Q66) * s * c ** 3 + (Q12 - Q22 + 2 * Q66) * s ** 3 * c
                self.assertAlmostEqual(Qb[0, 2] / q16, 1, 12)

    def test_tsai_wu_and_max_stress_of_one_ply_match_the_hand_formula(self):
        from cadgen._internal.fea.laminate import max_stress, tsai_wu

        s1, s2, t12 = 500.0, 20.0, 30.0
        F1, F2 = 1 / 1500 - 1 / 1500, 1 / 40 - 1 / 246
        F11, F22, F66 = 1 / (1500 * 1500), 1 / (40 * 246), 1 / 68 ** 2
        F12 = -0.5 * math.sqrt(F11 * F22)
        hand = F1 * s1 + F2 * s2 + F11 * s1 ** 2 + F22 * s2 ** 2 + F66 * t12 ** 2 + 2 * F12 * s1 * s2
        self.assertAlmostEqual(tsai_wu(self.lamina, s1, s2, t12), hand, places=12)
        self.assertAlmostEqual(hand, 0.6979, places=4)
        self.assertAlmostEqual(float(max_stress(self.lamina, s1, s2, t12)), 0.5, places=12)      # 20 / 40
        self.assertAlmostEqual(float(max_stress(self.lamina, -1200.0, -50.0, 0.0)), 0.8, places=12)  # 1200 / 1500

    def test_the_orthotropic_matrix_inverts_the_compliance_and_turns_with_its_axes(self):
        import numpy as np

        from cadgen._internal.fea.operators import isotropic_matrix, orthotropic_compliance, orthotropic_matrix

        block = self.lamina.block([1, 0, 0], [0, 1, 0])
        C = orthotropic_matrix(block)
        self.assertLess(np.abs(C @ orthotropic_compliance(block) - np.eye(6)).max(), 1e-9)
        # Fibres along global Y, direction 2 along -X: the global XX entry is E2's, YY is E1's.
        turned = orthotropic_matrix(self.lamina.block([0, 1, 0], [-1, 0, 0]))
        self.assertAlmostEqual(turned[1, 1] / C[0, 0], 1, 12)
        self.assertAlmostEqual(turned[0, 0] / C[1, 1], 1, 12)
        self.assertAlmostEqual(turned[5, 5] / C[5, 5], 1, 12)
        iso = {"E1_MPa": 2e5, "E2_MPa": 2e5, "E3_MPa": 2e5, "nu12": 0.3, "nu13": 0.3, "nu23": 0.3,
               "G12_MPa": 2e5 / 2.6, "G13_MPa": 2e5 / 2.6, "G23_MPa": 2e5 / 2.6, "axes": [[0.6, 0.8, 0], [-0.8, 0.6, 0]]}
        self.assertLess(np.abs(orthotropic_matrix(iso) - isotropic_matrix(2e5, 0.3)).max(), 1e-6)


def _block_volume(directory: Path, size=(10.0, 10.0, 20.0), h=4.0):
    from build123d import Align, Box, export_step

    from cadgen._internal.fea.mesh import mesh_occurrence
    from cadgen.step_scene import read_scene

    step = directory / "block.step"
    export_step(Box(*size, align=(Align.MIN, Align.MIN, Align.MIN)), str(step))
    volume = mesh_occurrence(next(iter(read_scene(step).leaves())), max_h=h)

    def face(axis: int, level: float) -> int:
        return next(o for o, fp in volume.faces.items() if abs(fp.center[axis] - level) < 1e-6
                    and all(abs(fp.center[i] - size[i] / 2) < 1e-6 for i in range(3) if i != axis))

    return volume, face


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class OrthotropicSolid(unittest.TestCase):
    """A 10 x 10 x 20 mm block on rollers (x = 0, y = 0, z = 0), pulled along Z with 1000 N: uniaxial stress."""

    BLOCK = {"E1_MPa": 135000, "E2_MPa": 9000, "E3_MPa": 11000, "nu12": 0.31, "nu13": 0.27, "nu23": 0.45,
             "G12_MPa": 5200, "G13_MPa": 4800, "G23_MPa": 3600}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.volume, face = _block_volume(Path(cls._tmp.name))
        cls.face = staticmethod(face)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _pull(self, material, solver=None):
        from cadgen._internal.fea import solve
        from cadgen._internal.fea.study import Load

        top = self.face(2, 20.0)
        rollers = [((self.face(0, 0.0),), 0), ((self.face(1, 0.0),), 1), ((self.face(2, 0.0),), 2)]
        ordinal_of = {f"#o1.f{top}": top}
        return solve.solve_linear_static(self.volume, material, (), (Load((f"#o1.f{top}",), "force", vector=(0.0, 0.0, 1000.0)),),
                                         ordinal_of, rollers=rollers, **({"solver": solver} if solver else {}))

    def _strains(self, outcome):
        import numpy as np

        at, u = outcome.dof_locations, outcome.displacement
        far = [np.abs(at[:, i] - (10.0, 10.0, 20.0)[i]) < 1e-6 for i in range(3)]
        return [float(u[far[i], i].mean()) / (10.0, 10.0, 20.0)[i] for i in range(3)]

    def test_uniaxial_stress_gives_the_compliance_matrix_strains_within_one_percent(self):
        from cadgen._internal.fea.materials import material_from_spec

        sigma = 1000.0 / 100.0
        # Direction 1 along global Z, direction 2 along global X (3 = 1 x 2 along global Y).
        material = material_from_spec({"name": "ud", "orthotropic": {**self.BLOCK, "axes": [[0, 0, 1], [1, 0, 0]]}})
        exx, eyy, ezz = self._strains(self._pull(material))
        b = self.BLOCK
        self.assertAlmostEqual(ezz / (sigma / b["E1_MPa"]), 1.0, delta=0.01)
        self.assertAlmostEqual(exx / (-b["nu12"] * sigma / b["E1_MPa"]), 1.0, delta=0.01)
        self.assertAlmostEqual(eyy / (-b["nu13"] * sigma / b["E1_MPa"]), 1.0, delta=0.01)
        # Matrix-free (the iterative rung's) takes the same tensor.
        exx_mf, _, ezz_mf = self._strains(self._pull(material, "matrix_free"))
        self.assertAlmostEqual(ezz_mf / ezz, 1.0, delta=1e-5)
        self.assertAlmostEqual(exx_mf / exx, 1.0, delta=1e-5)

    def test_an_isotropic_block_written_orthotropic_solves_as_the_isotropic_one(self):
        import numpy as np

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.materials import material_from_spec

        steel = material_from_spec("steel")
        G = 200000.0 / 2.6
        ortho = material_from_spec({"name": "steel as orthotropic", "orthotropic": {
            "E1_MPa": 200000, "E2_MPa": 200000, "E3_MPa": 200000, "nu12": 0.3, "nu13": 0.3, "nu23": 0.3,
            "G12_MPa": G, "G13_MPa": G, "G23_MPa": G, "axes": [[0.6, 0, 0.8], [0, 1, 0]]}})
        space = FemSpace.build(self.volume)
        K_iso, K_ortho = operators.stiffness(space, steel), operators.stiffness(space, ortho)
        self.assertLess(abs(K_iso - K_ortho).max() / abs(K_iso).max(), 1e-9)
        a, b = self._pull(steel), self._pull(ortho)
        self.assertLess(np.abs(a.displacement - b.displacement).max() / np.abs(a.displacement).max(), 1e-8)

    def test_modal_takes_the_orthotropic_stiffness(self):
        from build123d import Box, export_step

        from cadgen import fea

        directory = Path(self._tmp.name)
        step = directory / "bar.step"
        export_step(Box(60, 6, 6), str(step))
        end = min((f for f in fea.faces(step).faces if f.surface == "plane"), key=lambda f: f.center_mm[0])
        base = {"analysis": "modal", "fixtures": [{"faces": [end.ref]}], "modes": 2, "mesh": {"size_mm": 3}}
        block = {**self.BLOCK, "density_t_per_mm3": 1.6e-9}
        ortho = {k: v for k, v in block.items() if k != "density_t_per_mm3"}

        def first(axes):
            material = {"name": "ud", "density_t_per_mm3": 1.6e-9, "orthotropic": {**ortho, "axes": axes}}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, directory / "bar.glb", study={**base, "material": material})
            return result.summary["first_frequency_Hz"]

        along, across = first([[1, 0, 0], [0, 1, 0]]), first([[0, 1, 0], [0, 0, 1]])
        # Fibres along the cantilever: E1 bends it; across, the much softer E3 (11 GPa) of that frame does.
        self.assertGreater(along / across, 2.5)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class CrossPlyStrip(unittest.TestCase):
    """A 100 x 400 x 1 mm [0/90]s T300 strip clamped on its long sides under 0.001 MPa: cylindrical bending across X."""

    A, B, T, Q = 100.0, 400.0, 1.0, 0.001

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "strip.step"
        export_step(Box(cls.A, cls.B, cls.T), str(step))
        faces = fea.faces(step).faces
        cls.long_sides = [f.ref for f in faces if f.normal is not None and abs(abs(f.normal[0]) - 1) < 1e-6]
        top = next(f.ref for f in faces if f.normal is not None and f.normal[2] > 0.99)
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "strip.glb", study={
                "analysis": "composite", "laminae": {"cfrp": CFRP}, "layup": _layup((0, 90, 90, 0), 0.25),
                "fixtures": [{"faces": cls.long_sides}],
                "loads": [{"faces": [top], "type": "pressure", "pressure_MPa": cls.Q}],
            })
        cls.at, cls.moved, cls.extras, cls.attributes = _glb(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_is_a_laminated_shell_and_says_so(self):
        summary = self.result.summary
        self.assertTrue(self.result.ok)
        self.assertEqual(summary["method"], "shell")
        self.assertEqual(summary["layup"], {"plies": _layup((0.0, 90.0, 90.0, 0.0), 0.25), "notation": "[0/90]s",
                                            "thickness_mm": 1.0, "count": 4})
        self.assertEqual(self.extras["analysis"]["type"], "composite")
        self.assertEqual(self.extras["analysis"]["tier"], 3)
        self.assertTrue(any("no delamination" in line for line in self.extras["analysis"]["limits"]))
        self.assertEqual(self.extras["study"]["layup"]["notation"], "[0/90]s")
        self.assertEqual(self.extras["study"]["laminae"], {"cfrp": CFRP})  # the viewer's Study reads the ply materials
        self.assertIn("_FAILURE_INDEX", self.attributes)
        self.assertEqual([f["field"] for f in self.extras["fields"]], ["von_mises", "displacement", "failure_index"])
        self.assertIn("composite_method", [f["type"] for f in self.result.findings])
        self.assertNotIn("fit", self.extras)

    def test_its_abd_is_the_hand_clt_one(self):
        Q11 = 181000 / (1 - 0.28 * 0.28 * 10300 / 181000)
        Q22 = Q11 * 10300 / 181000
        D11 = (7 * Q11 + Q22) / 8 / 12
        self.assertAlmostEqual(self.result.summary["detail"]["D"][0][0] / D11, 1.0, delta=1e-6)

    def test_centre_deflection_is_clt_cylindrical_bending_within_five_percent(self):
        import numpy as np

        D11 = self.result.summary["detail"]["D"][0][0]
        clt = self.Q * self.A ** 4 / (384 * D11)
        centre = int(np.argmin(np.linalg.norm(self.at[:, :2], axis=1)))
        self.assertLess(np.linalg.norm(self.at[centre, :2]), 3.0)
        w = -self.moved[centre, 2]
        self.assertAlmostEqual(w / clt, 1.0, delta=0.05)
        self.assertAlmostEqual(self.result.summary["reaction_force_N"][2], self.Q * self.A * self.B, delta=1e-6)

    def test_the_worst_ply_and_its_tsai_wu_by_hand(self):
        summary, check = self.result.summary, self.result.summary["checks"][0]
        worst = summary["worst_ply"]
        s1, s2, t12 = (worst["stress_MPa"][key] for key in ("sigma1", "sigma2", "tau12"))
        F11, F22 = 1 / 1500 ** 2, 1 / (40 * 246)
        hand = ((1 / 40 - 1 / 246) * s2 + F11 * s1 ** 2 + F22 * s2 ** 2 + t12 ** 2 / 68 ** 2
                - math.sqrt(F11 * F22) * s1 * s2)
        self.assertAlmostEqual(worst["tsai_wu"], hand, delta=1e-5 + 1e-4 * abs(hand))
        self.assertEqual(check["kind"], "ply_failure")
        self.assertEqual((check["ply"], check["angle_deg"]), (worst["ply"], worst["angle_deg"]))
        self.assertEqual(check["value"], summary["max_failure_index"])
        self.assertEqual(check["status"], "passes")
        self.assertIn(f"Worst ply {worst['ply']} (+90°)" if worst["angle_deg"] == 90 else f"Worst ply {worst['ply']} (0°)",
                      "\n".join(self.result.human_lines()))

    def test_no_check_quotes_a_load_multiple(self):
        """Not linear in the load: every check says it holds at this load only (scaling none), in the summary and the
        GLB the viewer reads, so the verdict's takeaway is the worst check's own sentence, never "OK up to 18× this load"."""
        checks = self.result.summary["checks"]
        self.assertTrue(checks)
        self.assertEqual({check.get("scaling") for check in checks}, {"none"})
        self.assertEqual({check.get("scaling") for check in self.extras["checks"]}, {"none"})

    def test_the_failure_index_field_tops_out_at_the_checks_value(self):
        """The field was a smoothed fit of the elements' index (0.573 at the top of the bar against a check of 0.62):
        now both are the governing criterion's worst, the field drawn as its envelope."""
        (field,) = [f for f in self.extras["fields"] if f["field"] == "failure_index"]
        check = self.result.summary["checks"][0]
        self.assertEqual(field["max"], check["value"])
        self.assertAlmostEqual(float(_attribute(self.result.glb, "_FAILURE_INDEX").max()), check["value"], delta=1e-6)  # float32 against six decimals


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ThickLaminate(unittest.TestCase):
    """A 40 x 40 x 8 mm [0/90]s plate (2 mm plies) clamped on two sides under 5 MPa: a layered solid."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, Cylinder, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step = directory / "thick.step"
        export_step(Box(40, 40, 8), str(cls.step))
        faces = fea.faces(cls.step).faces
        sides = [f.ref for f in faces if f.normal is not None and abs(abs(f.normal[0]) - 1) < 1e-6]
        top = next(f.ref for f in faces if f.normal is not None and f.normal[2] > 0.99)
        cls.study = {"analysis": "composite", "laminae": {"cfrp": {**CFRP, "nu23": 0.4}}, "layup": _layup((0, 90, 90, 0), 2.0),
                     "fixtures": [{"faces": sides}], "loads": [{"faces": [top], "type": "pressure", "pressure_MPa": 5}],
                     "mesh": {"size_mm": 4}}
        with redirect_stderr(io.StringIO()):
            cls.full = fea.solve(cls.step, directory / "full.glb", study=cls.study)
            cls.adapted = fea.solve(cls.step, directory / "adapted.glb", study={
                **cls.study, "fit": {**TINY, "allow": ["iterative", "local_refine", "symmetry"]}})
        cls.rod = directory / "rod.step"
        export_step(Cylinder(5, 60), str(cls.rod))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_failure_index_field_tops_out_at_the_checks_value(self):
        extras = _glb(self.full.glb)[2]
        (field,) = [f for f in extras["fields"] if f["field"] == "failure_index"]
        self.assertEqual(field["max"], self.full.summary["max_failure_index"])
        self.assertEqual(self.full.summary["checks"][0]["value"], self.full.summary["max_failure_index"])

    def test_it_is_a_layered_solid(self):
        self.assertTrue(self.full.ok)
        self.assertEqual(self.full.summary["method"], "solid")
        self.assertEqual(self.full.fit, ())
        self.assertGreater(self.full.summary["max_failure_index"], 0)
        self.assertEqual(len(self.full.summary["plies"]), 4)

    def test_the_ladder_takes_iterative_local_refine_and_symmetry_and_completes(self):
        result = self.adapted
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        for rung in ("iterative", "local_refine", "symmetry"):
            self.assertIn(rung, rungs)
        extras = _glb(result.glb)[2]
        self.assertEqual(extras["fit"], list(result.fit))
        self.assertEqual(json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"], list(result.fit))
        self.assertIn("fit_symmetry", [f["type"] for f in result.findings if f["severity"] == "info"])
        refine = next(step for step in result.fit if step["rung"] == "local_refine")
        self.assertIn("peak failure index moved", refine["accuracy"])
        # The worst ply's index holds within a widened 10 % of the unadapted run.
        self.assertAlmostEqual(result.summary["max_failure_index"] / self.full.summary["max_failure_index"], 1.0, delta=0.10)

    def test_a_part_that_is_not_a_plate_or_a_layup_too_thin_is_a_plain_error(self):
        from cadgen import fea

        with self.assertRaises(ValueError) as caught, redirect_stderr(io.StringIO()):
            fea.solve(self.step, Path(self._tmp.name) / "thin.glb", study={**self.study, "layup": _layup((0, 90, 90, 0), 1.0)})
        self.assertIn("the plies add up to 4 mm, but the plate is 8 mm thick", str(caught.exception))
        faces = fea.faces(self.rod).faces
        ends = [f.ref for f in faces if f.surface == "plane"]
        with self.assertRaises(ValueError) as caught, redirect_stderr(io.StringIO()):
            fea.solve(self.rod, Path(self._tmp.name) / "rod.glb", study={
                **self.study, "fixtures": [{"faces": [ends[0]]}],
                "loads": [{"faces": [ends[1]], "type": "pressure", "pressure_MPa": 1}]})
        self.assertIn("a layup needs a flat plate of even thickness", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
