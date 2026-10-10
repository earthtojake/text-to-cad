"""Two fluids (multiphase): the study file, the benchmarks against theory and experiment, and the ladder.

Benchmarks, each on the same numerics (``multiphase_ops``) the analysis runs:

- a still two-fluid column stays still and its pressure is hydrostatic (rho g h at the floor within 1%), in 2D on a
  scrambled mesh and through the whole analysis on a tank meshed by netgen;
- the first sloshing mode of a rectangular tank against linear theory, omega^2 = g k tanh(k h), k = pi / L, within 5%:
  a standing wave in 2D, and a tank given a short shake through the whole analysis;
- a rising bubble against Hysing et al., "Quantitative benchmark computations of two-dimensional bubble dynamics",
  Int. J. Numer. Meth. Fluids 60 (2009) 1259-1288, test case 1 (rho 1000/100, mu 10/1, g 0.98, sigma 24.5; the
  reference codes agree on the largest rise velocity 0.2417 at t = 0.921 and the centroid's height 1.0813 at t = 3):
  within 15% and 2% on a coarse mesh;
- the liquid's volume held within 1% over every run;
- the ladder: a run past its budget completes and says, in the GLB, the sidecar, the CLI and a finding, what it did.

Self-contained: build123d writes each tank into a temporary directory. Parse tests run everywhere; solves need the
fea extra.
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

G0 = 9.80665
WATER, AIR = 998.2, 1.204
# The tank: a 60 x 10 x 50 mm inside, 2 mm walls, open on top.
INSIDE, WALL = (60.0, 10.0, 50.0), 2.0


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def tank_step(directory: Path) -> Path:
    from build123d import Align, Box, Pos, export_step

    low = (Align.MIN, Align.MIN, Align.MIN)
    x, y, z = INSIDE
    tank = Box(x + 2 * WALL, y + 2 * WALL, z + WALL, align=low) - Pos(WALL, WALL, WALL) * Box(x, y, z, align=low)
    step = directory / "tank.step"
    export_step(tank, str(step))
    return step


def solve(step: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, step.with_name("tank.fea.glb"), study=study)


def zero_crossings(t, y) -> list[float]:
    return [t[i] - y[i] * (t[i + 1] - t[i]) / (y[i + 1] - y[i]) for i in range(len(y) - 1) if y[i] * y[i + 1] < 0]


def theory_period(length_m: float, depth_m: float, g: float = G0) -> float:
    k = math.pi / length_m
    return 2.0 * math.pi / math.sqrt(g * k * math.tanh(k * depth_m))


class StudyFile(unittest.TestCase):
    def parse(self, **study):
        from cadgen._internal.fea.study import parse_study

        return parse_study({"analysis": "multiphase", **study})

    def test_water_and_air_half_full_by_default_and_no_material(self):
        parsed = self.parse()
        inputs = parsed.inputs
        self.assertIsNone(parsed.material)
        self.assertEqual((inputs.liquid.name, inputs.liquid.density_kg_m3, inputs.gas.name, inputs.gas.density_kg_m3),
                         ("water", WATER, "air", AIR))
        self.assertEqual((inputs.fill, inputs.surface_tension_N_m, inputs.walls, inputs.gravity_m_s2),
                         ({"fraction": 0.5}, 0.0, "slip", (0.0, 0.0, -G0)))
        self.assertFalse(inputs.mapped)
        self.assertEqual(parsed.face_refs, ())

    def test_it_reads_a_shake_a_fill_probes_openings_and_checks(self):
        parsed = self.parse(
            fluids={"liquid": {"name": "fuel", "density_kg_m3": 800, "viscosity_Pa_s": 6e-4}, "gas": "air", "surface_tension_N_m": 0.025},
            fill={"level_mm": 20}, end_s=1.5, step_s=0.01, walls="no_slip",
            acceleration={"direction": [2, 0, 0], "amplitude_g": 0.3, "history": {"shape": "sine", "frequency_Hz": 3}},
            probes=[{"label": "left", "at_mm": [5, 5, 0]}], inlets=[{"opening": "z_max", "velocity_m_s": 0.1}],
            outlets=[{"opening": "x_max"}],
            view={"checks": [{"kind": "fill_level", "limit_mm": 45, "probes": ["left"]}, {"kind": "wall_pressure", "limit_Pa": 2000}]})
        inputs = parsed.inputs
        self.assertEqual((inputs.liquid.name, inputs.surface_tension_N_m, inputs.fill, inputs.end_s, inputs.step_s, inputs.walls),
                         ("fuel", 0.025, {"level_mm": 20.0}, 1.5, 0.01, "no_slip"))
        direction, amplitude, history = inputs.acceleration
        self.assertEqual((direction, amplitude, history), ((1.0, 0.0, 0.0), 0.3, ("sine", 3.0)))
        self.assertEqual([(o.opening, o.kind, o.velocity_m_s, o.fluid) for o in inputs.openings],
                         [("z_max", "inlet", 0.1, "liquid"), ("x_max", "outlet", 0.0, "liquid")])
        self.assertEqual(parsed.checks, ({"kind": "fill_level", "limit_mm": 45.0, "probes": ["left"]},
                                         {"kind": "wall_pressure", "limit_Pa": 2000.0}))
        self.assertEqual(self.parse(fluids={"surface_tension_N_m": "auto"}).inputs.surface_tension_N_m, 0.0728)

    def test_the_errors_say_what_to_write(self):
        cases = [
            ({"fill": {"fraction": 1.5}}, "fill.fraction: the share of the inside the liquid fills, 0 to 1"),
            ({"fill": {"level_mm": 5, "fraction": 0.5}}, "fill: how the liquid starts, exactly one of"),
            ({"fluids": {"liquid": "mercury"}}, "fluids.liquid: \"mercury\" is not one cadgen knows"),
            ({"fluids": {"liquid": {"density_kg_m3": 1, "viscosity_Pa_s": 1}, "gas": "air"}}, "must be denser than the gas"),
            ({"acceleration": {"direction": [0, 0, 0], "amplitude_g": 1}}, "acceleration.direction: the direction is zero"),
            ({"inlets": [{"opening": "top", "velocity_m_s": 1}]}, "inlets[0].opening: \"top\" is not a side"),
            ({"walls": "sticky"}, "walls: \"sticky\" is not \"slip\""),
            ({"view": {"checks": [{"kind": "stress"}]}}, "a stress check needs the fluids' pressure on the part"),
            ({"view": {"checks": [{"kind": "wall_pressure"}]}}, "a wall_pressure check needs the most the fluid may press"),
            ({"flow": {}}, "multiphase studies take analysis"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                self.parse(**change)
            self.assertIn(fragment, str(caught.exception))

    def test_linear_theory_and_words(self):
        from cadgen._internal.fea.analyses.multiphase import fill_words, sloshing_frequency

        self.assertAlmostEqual(sloshing_frequency(0.06, 0.025, G0), 1.0 / theory_period(0.06, 0.025), places=12)
        self.assertEqual([fill_words(0.5, "water"), fill_words(0.26, "oil"), fill_words(0.4, "water")],
                         ["Half full of water", "A quarter full of oil", "40 % full of water"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class TwoDimensional(unittest.TestCase):
    """The numerics on triangles: the benchmarks that are two-dimensional by nature."""

    def test_a_still_column_stays_still_on_a_scrambled_mesh(self):
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import Phases, TwoPhaseProblem, TwoPhaseSolver

        width, height, depth, n = 0.1, 0.06, 0.03, 20
        mesh = MeshTri.init_tensor(np.linspace(0, width, n + 1), np.linspace(0, height, 13))
        points = mesh.p.copy()
        inner = ~np.isin(np.arange(points.shape[1]), mesh.boundary_nodes())
        points[:, inner] += np.random.default_rng(0).uniform(-0.3, 0.3, (2, int(inner.sum()))) * width / n
        mesh = MeshTri(points, mesh.t)
        solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(WATER, AIR, 1.002e-3, 1.81e-5), depth - mesh.p[1], [0, -G0]))
        speeds = []
        state = solver.run(0.3, dt_max=0.005, on_step=lambda s: speeds.append(s.max_speed))
        floor = state.p[np.isclose(mesh.p[1], 0)].mean() - state.p[np.isclose(mesh.p[1], height)].mean()
        exact = WATER * G0 * depth + AIR * G0 * (height - depth)
        self.assertLess(abs(floor - exact) / exact, 0.01)
        self.assertLess(max(speeds), 1e-6)                       # m/s: still to round-off
        self.assertLess(abs(state.volume - solver.volume0) / solver.volume0, 1e-9)

    def test_the_first_sloshing_mode_matches_linear_theory(self):
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import Phases, TwoPhaseProblem, TwoPhaseSolver

        length, height, depth, amplitude = 0.1, 0.08, 0.05, 0.005
        mesh = MeshTri.init_tensor(np.linspace(0, length, 21), np.linspace(0, height, 17))
        k = math.pi / length
        solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(WATER, AIR, 1.002e-3, 1.81e-5),
                                                depth + amplitude * np.cos(k * mesh.p[0]) - mesh.p[1], [0, -G0]))
        period = theory_period(length, depth)
        times, modes, volumes = [], [], []

        def mode(state):
            # The standing wave's amplitude: the surface's crossings fitted by a + b cos(k x).
            a, b = state.distance[mesh.facets[0]], state.distance[mesh.facets[1]]
            cut = a * b < 0
            s = a[cut] / (a[cut] - b[cut])
            x = mesh.p[:, mesh.facets[0, cut]] + s * (mesh.p[:, mesh.facets[1, cut]] - mesh.p[:, mesh.facets[0, cut]])
            fit = np.linalg.lstsq(np.stack([np.ones(x.shape[1]), np.cos(k * x[0])], 1), x[1], rcond=None)[0]
            times.append(state.t)
            modes.append(fit[1])
            volumes.append(state.volume)

        solver.run(3 * period, dt_max=period / 40, on_step=mode)
        crossings = zero_crossings(times, modes)
        measured = 2.0 * float(np.mean(np.diff(crossings)))
        self.assertGreaterEqual(len(crossings), 5)
        self.assertLess(abs(measured - period) / period, 0.05, f"period {measured:.4f} s against {period:.4f} s")
        self.assertLess(max(abs(v - volumes[0]) for v in volumes) / volumes[0], 0.01)

    def test_a_rising_bubble_matches_hysing_test_case_1(self):
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import Phases, TwoPhaseProblem, TwoPhaseSolver, heaviside

        n = 20
        mesh = MeshTri.init_tensor(np.linspace(0, 1, n + 1), np.linspace(0, 2, 2 * n + 1))
        ends = mesh.facets_satisfying(lambda x: np.isclose(x[1], 0) | np.isclose(x[1], 2), boundaries_only=True)
        bubble = np.hypot(mesh.p[0] - 0.5, mesh.p[1] - 0.5) - 0.25                 # the heavy fluid outside it
        solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(1000.0, 100.0, 10.0, 1.0, 24.5), bubble, [0, -0.98], noslip=ends))
        dx = np.asarray(solver.pbasis.dx)
        y = solver.pbasis.global_coordinates().value[1]
        rise, centre, volumes = [], [], []

        def measure(state):
            gas = 1.0 - heaviside(solver.pbasis.interpolate(state.distance).value, solver.epsilon)
            size = (gas * dx).sum()
            rise.append(((gas * solver.ubasis.interpolate(state.u).value[1] * dx).sum() / size, state.t))
            centre.append((gas * y * dx).sum() / size)
            volumes.append(state.volume)

        solver.run(3.0, dt_max=0.02, on_step=measure)
        fastest, when = max(rise)
        self.assertLess(abs(fastest - 0.2417) / 0.2417, 0.15, f"rise velocity {fastest:.4f} at {when:.3f} s")
        self.assertLess(abs(centre[-1] - 1.0813) / 1.0813, 0.02, f"centroid {centre[-1]:.4f} at 3 s")
        self.assertLess(abs(when - 0.9213), 0.15)
        self.assertLess(max(abs(v - volumes[0]) for v in volumes) / volumes[0], 0.01)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Tank(unittest.TestCase):
    """The whole analysis on a tank netgen meshes: a STEP in, a GLB and a sidecar out."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="cadgen-multiphase-"))
        self.step = tank_step(self.directory)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_still_tank_stays_still_with_hydrostatic_walls(self):
        result = solve(self.step, {"analysis": "multiphase", "fill": {"level_mm": 25}, "end_s": 0.05, "mesh": {"size_mm": 5},
                                   "view": {"checks": [{"kind": "fill_level"}, {"kind": "wall_pressure", "limit_Pa": 1000}]}})
        summary = result.summary
        floor = WATER * G0 * 0.025 + AIR * G0 * 0.025
        self.assertLess(abs(summary["max_wall_pressure_Pa"] - floor) / floor, 0.01)
        self.assertLess(summary["max_speed_m_s"], 1e-4)
        self.assertLess(abs(summary["volume"]["max_change_percent"]), 1e-3)
        self.assertEqual(summary["fill"]["words"], "Half full of water")
        self.assertAlmostEqual(summary["force_N"]["at_rest"][2], -0.015e-3 * WATER * G0, delta=0.01 * 0.015e-3 * WATER * G0)
        self.assertEqual([(c["kind"], c["status"]) for c in summary["checks"]], [("fill_level", "passes"), ("wall_pressure", "passes")])
        self.assertAlmostEqual(summary["checks"][0]["value"], 25.0, delta=0.5)
        self.assertEqual(summary["checks"][0]["limit"], INSIDE[2])

        extras, attributes = glb_extras(result.glb)
        self.assertEqual(extras["analysis"]["type"], "multiphase")
        self.assertEqual(extras["analysis"]["fill"]["fraction"], 0.5)
        self.assertEqual([f["field"] for f in extras["fields"]], ["water_fraction", "pressure"])
        self.assertTrue(all(f["per_frame"] for f in extras["fields"]))
        frames = extras["series"]["frames"]
        self.assertEqual(extras["series"]["kind"], "time")
        self.assertGreaterEqual(len(frames), 3)
        self.assertIn("_WATER_FRACTION_F1", attributes)
        self.assertIn("_PRESSURE_F1", attributes)
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["analysis"], "multiphase")
        self.assertIn("sloshing_force_x_N", sidecar["curves"])
        self.assertTrue(any("Half full of water" in line for line in result.human_lines()))

    def test_a_shaken_tank_sloshes_at_its_first_mode(self):
        import numpy as np

        result = solve(self.step, {"analysis": "multiphase", "fill": {"level_mm": 25}, "end_s": 0.9, "mesh": {"size_mm": 5},
                                   "acceleration": {"direction": [1, 0, 0], "amplitude_g": 0.1,
                                                    "history": {"shape": "half_sine", "duration_s": 0.05}}})
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        period = theory_period(INSIDE[0] / 1000, 0.025)
        self.assertAlmostEqual(1.0 / sidecar["summary"]["first_sloshing_Hz"], period, places=6)
        curve = sidecar["curves"]["sloshing_force_x_N"]
        t, force = np.array(curve["x"]), np.array(curve["y"])
        later = t > 0.1                                           # after the shake
        crossings = zero_crossings(t[later], force[later] - force[later].mean())
        measured = 2.0 * float(np.mean(np.diff(crossings)))
        self.assertLess(abs(measured - period) / period, 0.05, f"period {measured:.4f} s against {period:.4f} s")
        self.assertLess(abs(sidecar["summary"]["volume"]["max_change_percent"]), 1.0)
        # It sloshed: the liquid rose at the walls and the walls felt a sideways push.
        self.assertGreater(sidecar["summary"]["peak_fill_level_mm"], 25.5)
        self.assertGreater(sidecar["summary"]["force_N"]["sloshing_peak_N"], 1e-3)

    def test_a_run_past_its_budget_takes_the_ladder_and_says_so(self):
        result = solve(self.step, {"analysis": "multiphase", "fill": {"level_mm": 25}, "end_s": 0.6, "mesh": {"size_mm": 5},
                                   "acceleration": {"direction": [1, 0, 0], "amplitude_g": 0.05,
                                                    "history": {"shape": "half_sine", "duration_s": 0.05}},
                                   "fit": {"seconds": 3}})
        rungs = [step["rung"] for step in result.fit]
        self.assertEqual(rungs[:3], ["adaptive_steps", "local_refine", "fluid_coarsen"])
        extras, _ = glb_extras(result.glb)
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual([step["rung"] for step in extras["fit"]], rungs)
        self.assertEqual([step["rung"] for step in sidecar["fit"]], rungs)
        self.assertIn("only where its surface moves", extras["fit"][1]["words"])
        self.assertIsNotNone(extras["fit"][0]["accuracy"])
        self.assertTrue({f"fit_{rung}" for rung in rungs} <= {finding["type"] for finding in sidecar["findings"]})
        self.assertTrue(any(line.startswith("adapted: Let the time step grow") for line in result.human_lines()))
        self.assertEqual(sidecar["summary"]["march"]["cfl"], 1.0)
        self.assertLess(abs(sidecar["summary"]["volume"]["max_change_percent"]), 1.0)


def box_duct_step(directory: Path, side: float, length: float, wall: float = 1.0) -> Path:
    """A square passage through a block along x: sharp corners where the inlet meets the walls."""
    from build123d import Align, Box, export_step

    step = directory / "duct.step"
    along = (Align.MIN, Align.CENTER, Align.CENTER)
    export_step(Box(length, side + 2 * wall, side + 2 * wall, align=along) - Box(length, side, side, align=along), str(step))
    return step


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class BoxDuct(unittest.TestCase):
    """Liquid fed into a square duct (sharp corners at its inlet) through one end, out of the other: it runs."""

    def test_a_square_duct_solves(self):
        with tempfile.TemporaryDirectory() as tmp:
            step = box_duct_step(Path(tmp), 10.0, 30.0, wall=2.0)
            result = solve(step, {"analysis": "multiphase", "fill": {"fraction": 0.5}, "end_s": 0.02, "mesh": {"size_mm": 3},
                                  "inlets": [{"opening": "x_min", "velocity_m_s": 0.05}], "outlets": [{"opening": "x_max"}]})
        self.assertTrue(result.ok)
        self.assertGreater(result.summary["max_speed_m_s"], 0)


if __name__ == "__main__":
    unittest.main()
