"""Flow (`"analysis": "cfd"`, lite): the study it reads, Poiseuille, the Reynolds warning and the ladder.

The pipe is a tube 16 mm long, bore radius 2 mm, wall 1 mm, along x: water
enters at x_min with the fully developed profile at a mean speed U and leaves
at x_max at 0 Pa. Laminar pipe flow (Hagen-Poiseuille) loses
Δp = 8 μ L Q / (π R⁴) and has the parabola u = 2 U (1 - r²/R²) across it, and
its wall shear is 4 μ U / R. Past Re 2000 it still solves and warns. The ladder
cases pass a tiny time target: the pipe at Re 600 takes continuation, and a
cube in a free stream takes fluid_coarsen. Every STEP is a build123d solid in a
temporary directory.
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
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

R, WALL, LENGTH = 2.0, 1.0, 16.0
WATER_MU = 1.002e-3
LIMIT_TEXT = "Laminar, steady, incompressible; no turbulence model."
PIPE = {"analysis": "cfd", "mesh": {"size_mm": 1.0},
        "flow": {"kind": "internal", "fluid": "water", "inlets": [{"opening": "x_min", "velocity_m_s": 0.01}],
                 "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}}


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def tube_step(directory: Path) -> Path:
    from build123d import Align, Cylinder, Rotation, export_step

    step = directory / "tube.step"
    along = (Align.CENTER, Align.CENTER, Align.MIN)
    export_step(Rotation(0, 90, 0) * (Cylinder(R + WALL, LENGTH, align=along) - Cylinder(R, LENGTH, align=along)), str(step))
    return step


def poiseuille_Pa(flow_m3_s: float, mu: float = WATER_MU) -> float:
    return 8.0 * mu * (LENGTH / 1000) * flow_m3_s / (math.pi * (R / 1000) ** 4)


def solve(step: Path, out: Path, study: dict, capture: bool = False):
    """Run the study; with ``capture`` also hand back the analysis's own result (the volume's velocity)."""
    from cadgen import fea
    from cadgen._internal.fea.analyses.cfd import CfdAnalysis

    captured = {}
    original = CfdAnalysis.solve

    def keep(self, ctx, inputs):
        captured["result"] = original(self, ctx, inputs)
        return captured["result"]

    with redirect_stderr(io.StringIO()), mock.patch.object(CfdAnalysis, "solve", keep):
        result = fea.solve(step, out, study=study)
    return result, captured.get("result")


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**PIPE, **changes})

    def test_it_reads_the_flow_without_a_material(self):
        parsed = self.parse()
        inputs = parsed.inputs
        self.assertIsNone(parsed.material)
        self.assertEqual((inputs.kind, inputs.fluid.name, inputs.fluid.density_kg_m3), ("internal", "water", 998.2))
        self.assertEqual([(i.opening, i.velocity_m_s, i.profile) for i in inputs.inlets], [("x_min", 0.01, "developed")])
        self.assertEqual([(o.opening, o.pressure_Pa) for o in inputs.outlets], [("x_max", 0.0)])
        self.assertFalse(inputs.mapped)
        self.assertEqual(parsed.face_refs, ())

    def test_map_to_structure_brings_its_material_fixtures_and_the_static_checks(self):
        parsed = self.parse(map_to_structure={"material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}]},
                            view={"checks": [{"kind": "pressure_drop", "limit_Pa": 1000}, {"kind": "stress"}]})
        self.assertTrue(parsed.inputs.mapped)
        self.assertEqual(parsed.inputs.structure_material.name, "Aluminum 6061-T6")
        self.assertEqual((parsed.face_refs, parsed.inputs.anchor_refs), (("#o1.f1",), ("#o1.f1",)))
        self.assertEqual([check["kind"] for check in parsed.checks], ["pressure_drop", "stress"])

    def test_external_flow_takes_a_free_stream(self):
        parsed = self.parse(flow={"kind": "external", "fluid": {"density_kg_m3": 1.2, "viscosity_Pa_s": 1.8e-5},
                                  "velocity_m_s": [5, 0, 0]})
        self.assertEqual((parsed.inputs.kind, parsed.inputs.velocity_m_s, parsed.inputs.fluid.name), ("external", (5.0, 0.0, 0.0), "fluid"))

    def test_the_errors_name_the_field_in_plain_words(self):
        flow = PIPE["flow"]
        for changes, fragment in (
            ({"flow": {**flow, "fluid": None}}, "flow.fluid: name the fluid"),
            ({"flow": {**flow, "fluid": "oil"}}, "is not a fluid cadgen knows"),
            ({"flow": {**flow, "inlets": [{"opening": "left", "velocity_m_s": 1}]}}, "flow.inlets[0].opening"),
            ({"flow": {**flow, "outlets": [{"opening": "x_min"}]}}, "x_min is named twice"),
            ({"flow": {**flow, "inlets": [{"opening": "x_min", "velocity_m_s": 1, "profile": "plug"}]}}, "profile"),
            ({"flow": {"kind": "external", "fluid": "air"}}, "flow.velocity_m_s"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "add map_to_structure"),
            ({"map_to_structure": {"fixtures": [{"faces": ["#o1.f1"]}]}}, "map_to_structure.material"),
            ({"flow": None}, "study.flow"),
        ):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(fragment, str(caught.exception))

    def test_it_is_registered_built_and_stdlib_only_at_import(self):
        import subprocess
        import sys

        from cadgen._internal.fea.analyses import get_analysis

        cfd = get_analysis("cfd")
        self.assertEqual((cfd.tier, cfd.word, cfd.limits), (3, "Flow", (LIMIT_TEXT,)))
        self.assertEqual(cfd.ladder, ("iterative", "fluid_coarsen", "continuation"))
        code = (
            "import sys; sys.path.insert(0, 'packages/cadgen/src');"
            "import cadgen._internal.fea.analyses.cfd;"
            "print(','.join(m for m in ('numpy', 'scipy', 'skfem', 'netgen', 'OCP') if m in sys.modules))"
        )
        root = Path(__file__).resolve().parents[4]
        self.assertEqual(subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True).stdout.strip(), "")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Openings(unittest.TestCase):
    def test_an_opening_the_part_does_not_have_names_the_sides_it_does(self):
        from cadgen import fea

        with tempfile.TemporaryDirectory() as tmp:
            step = tube_step(Path(tmp))
            study = {**PIPE, "flow": {**PIPE["flow"], "inlets": [{"opening": "y_min", "velocity_m_s": 0.01}]}}
            with redirect_stderr(io.StringIO()), self.assertRaises(ValueError) as caught:
                fea.solve(step, Path(tmp) / "tube.glb", study=study)
        self.assertIn("no opening on the low Y side (y_min)", str(caught.exception))
        self.assertIn("its openings are on x_min, x_max", str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Poiseuille(unittest.TestCase):
    """Re 40 water through the tube: Hagen-Poiseuille's pressure drop, parabola and wall shear."""

    U = 0.01

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step = tube_step(directory)
        study = {**PIPE, "view": {"checks": [{"kind": "pressure_drop", "limit_Pa": 0.34}, {"kind": "velocity", "limit_m_s": 0.1}]}}
        cls.result, cls.own = solve(cls.step, directory / "tube.glb", study, capture=True)
        cls.extras, cls.attributes = glb_extras(cls.result.glb)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))
        cls.summary = cls.result.summary

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_pressure_drop_is_hagen_poiseuilles(self):
        flow = self.summary["flow_rate_m3_s"]
        self.assertAlmostEqual(flow, self.U * math.pi * (R / 1000) ** 2, delta=1e-3 * flow)
        self.assertLess(self.summary["flow_balance"], 1e-3)
        expected = poiseuille_Pa(flow)
        self.assertLess(abs(self.summary["pressure_drop_Pa"] - expected) / expected, 0.03, (self.summary["pressure_drop_Pa"], expected))

    def test_the_profile_is_the_parabola(self):
        import numpy as np

        post = self.own.scalars["post"]
        where, velocity = post["velocity_locations"], post["nodal_velocity"] / 1000.0
        middle = np.abs(where[:, 0] - LENGTH / 2) < 1.0
        r = np.hypot(where[middle, 1], where[middle, 2])
        parabola = 2 * self.U * (1 - (r / R) ** 2)
        self.assertLess(float(np.abs(velocity[middle, 0] - parabola).max()), 0.03 * 2 * self.U)
        self.assertLess(float(np.abs(velocity[middle, 1:]).max()), 0.01 * 2 * self.U)

    def test_the_wall_shear_on_the_bore_is_4_mu_u_over_r(self):
        expected = 4 * WATER_MU * self.U / (R / 1000)
        self.assertLess(abs(self.summary["max_wall_shear_Pa"] - expected) / expected, 0.1)

    def test_it_is_laminar_and_says_its_limits_everywhere(self):
        reynolds = self.summary["reynolds"]
        self.assertEqual((reynolds["kind"], reynolds["limit"], reynolds["laminar"]), ("internal", 2000, True))
        self.assertAlmostEqual(reynolds["value"], 998.2 * self.U * 2 * R / 1000 / WATER_MU, delta=0.5)
        self.assertEqual(self.extras["analysis"]["limits"], [LIMIT_TEXT])
        self.assertEqual(self.sidecar["limits"], [LIMIT_TEXT])
        self.assertEqual(self.extras["analysis"]["warnings"], [])
        self.assertTrue(self.summary["solve"]["converged"])
        self.assertLess(self.summary["solve"]["residual"], 1e-8)

    def test_the_glb_carries_wall_pressure_and_shear_on_the_part(self):
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertEqual(set(fields), {"pressure", "wall_shear"})
        self.assertTrue(fields["pressure"]["signed"])
        self.assertEqual((fields["pressure"]["units"], fields["wall_shear"]["units"]), ("Pa", "Pa"))
        self.assertIn("_PRESSURE", self.attributes)
        self.assertIn("_WALL_SHEAR", self.attributes)
        self.assertNotIn("_VON_MISES", self.attributes)
        self.assertEqual(self.extras["study"]["flow"]["inlets"], [{"opening": "x_min", "velocity_m_s": self.U, "profile": "developed"}])
        # The inlet end of the bore is at the drop's pressure, the outlet end near 0.
        self.assertAlmostEqual(fields["pressure"]["max"], self.summary["pressure_drop_Pa"], delta=0.1 * self.summary["pressure_drop_Pa"])

    def test_the_checks_and_the_cli(self):
        checks = {check["kind"]: check for check in self.summary["checks"]}
        self.assertEqual(checks["pressure_drop"]["unit"], "Pa")
        self.assertEqual(checks["pressure_drop"]["status"], "close")
        self.assertEqual(checks["velocity"]["status"], "passes")
        lines = "\n".join(self.result.human_lines())
        self.assertIn("internal flow of water: Re", lines)
        self.assertIn("pressure drop", lines)
        self.assertIn("(cfd)", lines)


def duct_step(directory: Path, width: float, height: float, length: float = 16.0) -> Path:
    """A rectangular duct along x: a width x height passage through a block with 1 mm walls."""
    from build123d import Align, Box, export_step

    step = directory / f"duct_{width:g}x{height:g}.step"
    along = (Align.MIN, Align.CENTER, Align.CENTER)
    export_step(Box(length, width + 2, height + 2, align=along) - Box(length, width, height, align=along), str(step))
    return step


def rectangular_duct_Pa(flow_m3_s: float, width_mm: float, height_mm: float, length_mm: float = 16.0,
                        mu: float = WATER_MU) -> float:
    """Laminar developed flow through a W x H rectangle (Shah & London's series): Q = W H^3 dp / (12 mu L) times
    1 - (192 H / pi^5 W) sum over odd n of tanh(n pi W / 2H) / n^5, with H the shorter side (f Re = 56.91 square)."""
    w, h = max(width_mm, height_mm) / 1000, min(width_mm, height_mm) / 1000
    series = sum(math.tanh(n * math.pi * w / (2 * h)) / n ** 5 for n in range(1, 40, 2))
    shape = 1 - 192 * h / (math.pi ** 5 * w) * series
    return 12 * mu * (length_mm / 1000) * flow_m3_s / (w * h ** 3 * shape)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SharpCorneredDucts(unittest.TestCase):
    """Rectangular passages solve: the inlet's corners, where every velocity around a pressure node is held,
    used to make the flow's matrix exactly singular. A square and a 2:1 duct against Shah & London."""

    def check(self, width: float, height: float):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            result, _ = solve(duct_step(directory, width, height), directory / "duct.glb", PIPE)
        summary = result.summary
        self.assertTrue(summary["solve"]["converged"])
        flow = summary["flow_rate_m3_s"]
        self.assertAlmostEqual(flow, 0.01 * width * height * 1e-6, delta=1e-3 * flow)
        expected = rectangular_duct_Pa(flow, width, height)
        self.assertLess(abs(summary["pressure_drop_Pa"] - expected) / expected, 0.05, (summary["pressure_drop_Pa"], expected))

    def test_a_square_duct_loses_shah_and_londons_pressure(self):
        self.check(3.0, 3.0)

    def test_a_two_to_one_duct_loses_shah_and_londons_pressure(self):
        self.check(4.0, 2.0)

    def test_an_unreached_pressure_takes_its_neighbours_value(self):
        import numpy as np
        from scipy import sparse

        from cadgen._internal.fea.navier_stokes import fill_unreached_pressures, unreached_pressures

        # Pressure 0 touches only velocity 0 (held); pressures 1 and 2 touch the free velocity 1.
        B = sparse.csr_matrix(np.array([[1.0, 0.0], [0.5, 1.0], [0.0, 2.0]]))
        unreached = unreached_pressures(B, np.array([0]))
        self.assertEqual(unreached.tolist(), [0])
        filled = fill_unreached_pressures(np.array([0.0, 4.0, 6.0]), unreached, np.array([[0], [1], [2]]))
        self.assertEqual(filled.tolist(), [5.0, 4.0, 6.0])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class PastLaminar(unittest.TestCase):
    """Re 2400 in the same tube: it solves (never refuses) and warns, in words and as data."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = {**PIPE, "flow": {**PIPE["flow"], "inlets": [{"opening": "x_min", "velocity_m_s": 0.6}]}}
        cls.result, _ = solve(tube_step(directory), directory / "fast.glb", study)
        cls.extras, _ = glb_extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_solves_and_warns(self):
        self.assertTrue(self.result.ok)
        reynolds = self.result.summary["reynolds"]
        self.assertGreater(reynolds["value"], 2000)
        self.assertEqual((reynolds["limit"], reynolds["laminar"]), (2000, False))
        self.assertTrue(self.result.summary["solve"]["converged"])
        sentence = self.extras["analysis"]["warnings"][0]
        self.assertIn("is past the laminar range", sentence)
        self.assertIn("real flow is likely turbulent, so this pressure drop is a lower bound", sentence)
        self.assertIn("reynolds_past_laminar", [finding["type"] for finding in self.result.findings])
        self.assertIn("past the laminar range", "\n".join(self.result.human_lines()))
        # The structured number rides beside the sentence in extras.analysis, which the viewer reads first.
        carried = self.extras["analysis"]["reynolds"]
        self.assertEqual({k: carried[k] for k in ("value", "limit", "kind")}, {k: reynolds[k] for k in ("value", "limit", "kind")})


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    """A tiny time target: the pipe at Re 600 reaches its Re by continuation, and Poiseuille holds within 5 %;
    a cube in a free stream coarsens its far field, its part kept at the size asked for."""

    @classmethod
    def setUpClass(cls):
        from build123d import Box, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = {**PIPE, "flow": {**PIPE["flow"], "inlets": [{"opening": "x_min", "velocity_m_s": 0.15}]},
                 "fit": {"seconds": 0.5, "allow": ["fluid_coarsen", "continuation"]}}
        cls.pipe, _ = solve(tube_step(directory), directory / "pipe.glb", study)
        cls.pipe_extras, _ = glb_extras(cls.pipe.glb)
        cube = directory / "cube.step"
        export_step(Box(4, 4, 4), str(cube))
        study = {"analysis": "cfd", "mesh": {"size_mm": 2.0}, "flow": {"kind": "external", "fluid": "air", "velocity_m_s": [0.1, 0, 0]},
                 "fit": {"seconds": 0.5, "allow": ["fluid_coarsen"]}}
        cls.cube, _ = solve(cube, directory / "cube.glb", study)
        cls.cube_extras, _ = glb_extras(cls.cube.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_continuation_reaches_re_600_and_poiseuille_holds(self):
        rungs = [step["rung"] for step in self.pipe.fit]
        self.assertIn("continuation", rungs)
        step = next(step for step in self.pipe.fit if step["rung"] == "continuation")
        self.assertIn("Reached Re 598 in steps", step["words"])
        self.assertEqual(self.pipe_extras["fit"][rungs.index("continuation")]["words"], step["words"])
        self.assertIn("fit_continuation", [finding["type"] for finding in self.pipe.findings])
        self.assertIn(f"adapted: {step['words']}", self.pipe.human_lines())
        solve_info = self.pipe.summary["solve"]
        self.assertTrue(solve_info["continuation"])
        self.assertEqual(len(solve_info["stages_Re"]), 4)
        expected = poiseuille_Pa(self.pipe.summary["flow_rate_m3_s"])
        self.assertLess(abs(self.pipe.summary["pressure_drop_Pa"] - expected) / expected, 0.05)

    def test_fluid_coarsen_keeps_the_part_fine_and_says_what_it_gave_up(self):
        step = next(step for step in self.cube.fit if step["rung"] == "fluid_coarsen")
        self.assertIn("the part is still meshed at 2 mm, the free stream at 16 mm", step["words"])
        self.assertTrue(step["accuracy"])
        self.assertEqual(self.cube.summary["fluid_mesh"]["far_size_mm"], 16.0)
        self.assertIn("fit_fluid_coarsen", [finding["type"] for finding in self.cube.findings])

    def test_the_free_stream_pushes_the_cube_downstream(self):
        force = self.cube.summary["force_N"]
        self.assertGreater(force[0], 0)
        self.assertLess(max(abs(force[1]), abs(force[2])), 0.2 * force[0])
        self.assertEqual(self.cube.summary["reynolds"]["kind"], "external")
        self.assertEqual(self.cube_extras["study"]["flow"], {"kind": "external", "velocity_m_s": [0.1, 0.0, 0.0],
                                                             "fluid": {"name": "air", "density_kg_m3": 1.204, "viscosity_Pa_s": 1.81e-05}})


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class MappedToStructure(unittest.TestCase):
    """A thick fluid (10 Pa s) pushes on the bore at a few kPa; held at its outlet end, the tube is stressed by it."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = tube_step(directory)
        outlet_end = next(face.ref for face in fea.faces(step).faces
                          if face.surface == "plane" and abs(face.center_mm[0] - LENGTH) < 1e-6)
        study = {**PIPE, "flow": {**PIPE["flow"], "fluid": {"name": "syrup", "density_kg_m3": 1000, "viscosity_Pa_s": 10}},
                 "map_to_structure": {"material": "aluminum-6061-t6", "fixtures": [{"faces": [outlet_end]}]},
                 "view": {"checks": [{"kind": "pressure_drop", "limit_Pa": 1e5}, {"kind": "stress"}]}}
        cls.result, _ = solve(step, directory / "mapped.glb", study)
        cls.extras, cls.attributes = glb_extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_wall_pressure_stresses_the_part(self):
        summary = self.result.summary
        drop = summary["pressure_drop_Pa"]
        self.assertLess(abs(drop - poiseuille_Pa(summary["flow_rate_m3_s"], mu=10.0)) / drop, 0.03)
        # A thick-walled tube under its inlet pressure: the bore's hoop stress is p (Ro² + R²) / (Ro² - R²).
        hoop = drop / 1e6 * ((R + WALL) ** 2 + R ** 2) / ((R + WALL) ** 2 - R ** 2)
        self.assertGreater(summary["max_von_mises_MPa"], 0.5 * hoop)
        self.assertLess(summary["max_von_mises_MPa"], 3.0 * hoop)
        self.assertEqual(summary["yield_MPa"], 276.0)
        kinds = [check["kind"] for check in summary["checks"]]
        self.assertEqual(kinds, ["pressure_drop", "stress"])
        self.assertEqual(summary["checks"][1]["status"], "passes")
        self.assertEqual(self.extras["study"]["material"]["name"], "Aluminum 6061-T6")
        self.assertEqual(len(self.extras["study"]["fixtures"]), 1)
        self.assertIsNotNone(self.extras["deformation_scale"])
        self.assertFalse(any("do not balance" in warning for warning in self.result.warnings))

    def test_the_mapped_stress_is_in_the_file_it_lists(self):
        # extras.fields lists von Mises, so the GLB carries it, though the colours are the wall pressure.
        listed = {entry["attribute"] for entry in self.extras["fields"]}
        self.assertIn("_VON_MISES", listed)
        self.assertTrue(listed <= set(self.attributes))


if __name__ == "__main__":
    unittest.main()
