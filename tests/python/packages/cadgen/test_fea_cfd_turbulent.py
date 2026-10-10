"""Turbulent flow (`"analysis": "cfd_turbulent"`, lite): the study it reads, the Moody chart and the ladder.

The pipe is a tube 15 mm long, bore 10 mm, wall 1 mm, along x: water enters at
x_min fully developed (the settled turbulent profile, k and omega of a long pipe
of that bore) and leaves at x_max at 0 Pa. A smooth pipe's fully developed
pressure drop is dp = f (L / D) rho U^2 / 2, with Darcy's f from Colebrook's
equation (the Moody chart), and its wall shear f rho U^2 / 8. The solver must
land within 10 % of it at Re 10,000 and Re 50,000. The ladder case passes a tiny
time target and still completes. Every STEP is a build123d solid in a temporary
directory.
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

R, WALL, LENGTH = 5.0, 1.0, 15.0
RHO, MU = 998.2, 1.002e-3
LIMIT_TEXT = "Steady RANS (k-omega SST), wall functions, incompressible"


def speed_for(reynolds: float) -> float:
    return reynolds * MU / (RHO * 2 * R / 1000)


def pipe(reynolds: float, **changes) -> dict:
    return {"analysis": "cfd_turbulent", "mesh": {"size_mm": 1.0},
            "flow": {"kind": "internal", "fluid": "water",
                     "inlets": [{"opening": "x_min", "velocity_m_s": speed_for(reynolds)}],
                     "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}, **changes}


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


def friction(summary: dict, reynolds: float) -> float:
    """Darcy's friction factor of the solved pressure drop."""
    return summary["pressure_drop_Pa"] * (2 * R / LENGTH) / (0.5 * RHO * speed_for(reynolds) ** 2)


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**pipe(20000), **changes})

    def test_it_reads_the_laminar_flows_study_and_the_turbulence_intensity(self):
        parsed = self.parse()
        inputs = parsed.inputs
        self.assertIsNone(parsed.material)
        self.assertEqual((inputs.kind, inputs.fluid.name), ("internal", "water"))
        self.assertEqual([(i.opening, i.profile) for i in inputs.inlets], [("x_min", "developed")])
        self.assertEqual(inputs.intensities, (0.05,))
        flow = {**pipe(20000)["flow"], "inlets": [{"opening": "x_min", "velocity_m_s": 2, "profile": "uniform",
                                                   "turbulence_intensity": 0.1}]}
        self.assertEqual(self.parse(flow=flow).inputs.intensities, (0.1,))
        external = self.parse(flow={"kind": "external", "fluid": "air", "velocity_m_s": [20, 0, 0],
                                    "turbulence_intensity": 0.02}).inputs
        self.assertEqual((external.kind, external.intensity), ("external", 0.02))
        mapped = self.parse(map_to_structure={"material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}]},
                            view={"checks": [{"kind": "pressure_drop", "limit_Pa": 1000}, {"kind": "stress"}]})
        self.assertTrue(mapped.inputs.mapped)
        self.assertEqual([check["kind"] for check in mapped.checks], ["pressure_drop", "stress"])

    def test_the_errors_name_the_field_in_plain_words(self):
        flow = pipe(20000)["flow"]
        for changes, fragment in (
            ({"flow": {**flow, "inlets": [{"opening": "x_min", "velocity_m_s": 2, "turbulence_intensity": 5}]}},
             "flow.inlets[0].turbulence_intensity: a share of the mean speed"),
            ({"flow": {**flow, "turbulence_intensity": 0.05}}, "an internal flow gives it per inlet"),
            ({"flow": {**flow, "inlets": [{"opening": "x_min", "velocity_m_s": 2, "swirl": 1}]}},
             "an inlet takes opening, velocity_m_s, profile and turbulence_intensity"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "add map_to_structure"),
            ({"flow": None}, "study.flow"),
        ):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(fragment, str(caught.exception))

    def test_it_is_registered_built_and_stdlib_only_at_import(self):
        import subprocess
        import sys

        from cadgen._internal.fea.analyses import REGISTRY, get_analysis

        turbulent = get_analysis("cfd_turbulent")
        self.assertFalse(REGISTRY["cfd_turbulent"].planned)
        self.assertEqual((turbulent.tier, turbulent.word, turbulent.limits), (3, "Turbulent flow", (LIMIT_TEXT,)))
        self.assertEqual(turbulent.ladder, ("fluid_coarsen", "continuation", "iterative"))
        code = (
            "import sys; sys.path.insert(0, 'packages/cadgen/src');"
            "import cadgen._internal.fea.analyses.cfd_turbulent;"
            "print(','.join(m for m in ('numpy', 'scipy', 'skfem', 'netgen', 'OCP') if m in sys.modules))"
        )
        root = Path(__file__).resolve().parents[4]
        self.assertEqual(subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True).stdout.strip(), "")

    def test_the_laminar_warning_points_here_and_colebrook_is_the_moody_chart(self):
        from cadgen._internal.fea.analyses.cfd import reynolds_sentence
        from cadgen._internal.fea.analyses.cfd_turbulent import laminar_sentence
        from cadgen._internal.fea.turbulence import colebrook

        self.assertIn("run the same study as cfd_turbulent", reynolds_sentence(4200, 2000))
        self.assertIn("the laminar cfd analysis fits it better", laminar_sentence(900, 2000))
        # Smooth pipe, Moody chart: f(1e4) = 0.0309, f(1e5) = 0.0180.
        self.assertAlmostEqual(colebrook(1e4), 0.0309, delta=0.0003)
        self.assertAlmostEqual(colebrook(1e5), 0.0180, delta=0.0002)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class MoodyChart(unittest.TestCase):
    """Fully developed water in the 10 mm pipe at Re 10,000 and Re 50,000: Colebrook's friction within 10 %."""

    LOW, HIGH = 10000.0, 50000.0

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = tube_step(directory)
        study = pipe(cls.LOW, view={"checks": [{"kind": "pressure_drop", "limit_Pa": 25}, {"kind": "velocity", "limit_m_s": 5}]})
        cls.low = solve(step, directory / "low.glb", study)
        cls.high = solve(step, directory / "high.glb", pipe(cls.HIGH))
        cls.extras, cls.attributes = glb_extras(cls.low.glb)
        cls.sidecar = json.loads(cls.low.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_pressure_drop_follows_colebrook(self):
        from cadgen._internal.fea.turbulence import colebrook

        for result, reynolds in ((self.low, self.LOW), (self.high, self.HIGH)):
            with self.subTest(reynolds=reynolds):
                summary = result.summary
                self.assertAlmostEqual(summary["reynolds"]["value"], reynolds, delta=0.01 * reynolds)
                expected = colebrook(reynolds)
                self.assertLess(abs(friction(summary, reynolds) - expected) / expected, 0.10,
                                (friction(summary, reynolds), expected))
                self.assertLess(summary["flow_balance"], 1e-3)
                self.assertTrue(summary["solve"]["converged"])
                # The wall function's shear on the bore: f rho U^2 / 8.
                tau = expected / 8 * RHO * speed_for(reynolds) ** 2
                self.assertLess(abs(summary["max_wall_shear_Pa"] - tau) / tau, 0.15, (summary["max_wall_shear_Pa"], tau))

    def test_it_is_turbulent_and_says_its_limits_everywhere(self):
        summary = self.low.summary
        self.assertEqual((summary["reynolds"]["limit"], summary["reynolds"]["turbulent"]), (2000, True))
        turbulence = summary["turbulence"]
        self.assertEqual(turbulence["model"], "k-omega SST")
        self.assertGreater(turbulence["viscosity_ratio_max"], 10.0)
        self.assertGreaterEqual(turbulence["wall_yplus"]["min"], 29.9)
        self.assertEqual(self.extras["analysis"]["type"], "cfd_turbulent")
        self.assertEqual(self.extras["analysis"]["limits"], [LIMIT_TEXT])
        self.assertEqual(self.sidecar["limits"], [LIMIT_TEXT])
        self.assertEqual(self.extras["analysis"]["warnings"], [])
        self.assertNotIn("reynolds", self.extras["analysis"])

    def test_the_glb_carries_wall_pressure_and_shear_and_the_study(self):
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertEqual(set(fields), {"pressure", "wall_shear"})
        self.assertIn("_PRESSURE", self.attributes)
        self.assertIn("_WALL_SHEAR", self.attributes)
        inlet = self.extras["study"]["flow"]["inlets"][0]
        self.assertEqual((inlet["profile"], inlet["turbulence_intensity"]), ("developed", 0.05))

    def test_the_checks_and_the_cli(self):
        checks = {check["kind"]: check for check in self.low.summary["checks"]}
        self.assertEqual(checks["pressure_drop"]["status"], "close")
        self.assertEqual(checks["velocity"]["status"], "passes")
        lines = "\n".join(self.low.human_lines())
        self.assertIn("internal turbulent flow of water: Re", lines)
        self.assertIn("k-omega SST with wall functions", lines)
        self.assertIn("(cfd_turbulent)", lines)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    """A tiny time target: the pipe at Re 20,000 on a coarser mesh still completes, with its steps said,
    and still lands within a widened 15 % of Colebrook."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        study = pipe(20000, mesh={"size_mm": 1.25}, fit={"seconds": 0.5})
        cls.result = solve(tube_step(directory), directory / "fit.glb", study)
        cls.extras, _ = glb_extras(cls.result.glb)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_completes_and_says_each_step(self):
        from cadgen._internal.fea.turbulence import colebrook

        self.assertTrue(self.result.ok)
        rungs = [step["rung"] for step in self.result.fit]
        self.assertIn("continuation", rungs)
        step = next(step for step in self.result.fit if step["rung"] == "continuation")
        self.assertIn("Marched to the steady turbulent flow in longer pseudo-time steps", step["words"])
        self.assertEqual([entry["rung"] for entry in self.extras["fit"]], rungs)
        self.assertIn("fit_continuation", [finding["type"] for finding in self.result.findings])
        self.assertIn(f"adapted: {step['words']}", self.result.human_lines())
        self.assertTrue(self.result.summary["solve"]["converged"])
        expected = colebrook(20000)
        self.assertLess(abs(friction(self.result.summary, 20000) - expected) / expected, 0.15)


if __name__ == "__main__":
    unittest.main()
