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
- inlets: a liquid inlet bringing nothing leaves a still channel still, and a half-full square duct fed through one
  end keeps its volume to what came in and went out, with nothing faster than a free fall through its height;
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

    def test_a_liquid_inlet_bringing_nothing_leaves_a_still_channel_still(self):
        # Fixed bug: every inlet corner was pinned to "liquid", the half of the inlet in the air too, so a jump in the
        # level set stood at the inlet and liquid poured from nothing (air at 0.5 m/s in the first step, the volume
        # growing with nothing coming in). The inlet's fluid now enters upwind at its own speed: here, none.
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import Opening, Phases, TwoPhaseProblem, TwoPhaseSolver

        length, height, depth = 0.03, 0.01, 0.005
        mesh = MeshTri.init_tensor(np.linspace(0, length, 37), np.linspace(0, height, 13))
        inlet = mesh.facets_satisfying(lambda x: np.isclose(x[0], 0), boundaries_only=True)
        top = mesh.facets_satisfying(lambda x: np.isclose(x[1], height), boundaries_only=True)
        openings = [Opening(inlet, "inlet", velocity=np.zeros(2), phase=1.0), Opening(top, "outlet")]
        solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(WATER, AIR, 1.002e-3, 1.81e-5), depth - mesh.p[1], [0, -G0],
                                                openings=openings))
        speeds = []
        state = solver.run(0.02, dt_max=5e-4, on_step=lambda s: speeds.append(s.max_speed))
        self.assertLess(max(speeds), 1e-6)                       # m/s: still to round-off
        self.assertLess(abs(state.volume - length * depth) / (length * depth), 1e-9)

    def test_an_open_tank_lets_air_in_never_liquid(self):
        # Fixed bug: where the flow came back in through an open side the level set took no condition, so liquid that
        # had splashed near an open top stayed on it as a skin, and the air coming in through the skin was counted as
        # liquid coming in: the volume kept was raised step by step (+26% here, +14% to +73% on 3D tanks) and the fill
        # level stuck at the brim. Air now comes in as air. Still, the tank keeps its liquid; sloshed to just below
        # the brim, it keeps it within 1% (it may only lose what the smeared surface spills) and its surface settles.
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import Opening, Phases, TwoPhaseProblem, TwoPhaseSolver, interface_heights

        length, height, depth, shake = 0.06, 0.04, 0.016, 0.2
        mesh = MeshTri.init_tensor(np.linspace(0, length, 13), np.linspace(0, height, 9))
        top = mesh.facets_satisfying(lambda x: np.isclose(x[1], height), boundaries_only=True)
        start = length * depth
        for amplitude in (0.0, 0.35):
            def acceleration(t, g=amplitude * G0):
                return np.array([g * math.sin(math.pi * t / shake) if t < shake else 0.0, 0.0])

            solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(WATER, AIR, 1.002e-3, 1.81e-5), depth - mesh.p[1], [0, -G0],
                                                    acceleration=acceleration, openings=[Opening(top, "outlet")]))
            volumes, levels = [], []

            def record(state):
                volumes.append(state.volume / start)
                levels.append(float(np.max(interface_heights(mesh, state.distance, solver.up))))

            state = solver.run(1.5, dt_max=0.01, on_step=record)
            with self.subTest(amplitude_g=amplitude):
                self.assertLess(max(volumes), 1.0 + 1e-4)                    # never gains liquid through the open top
                self.assertGreater(min(volumes), 0.99)
                self.assertLess(abs(state.volume - solver.expected_volume) / start, 1e-9)
                self.assertLess(levels[-1], 0.03)                            # the surface came back down (brim 40 mm)
                if amplitude:
                    self.assertGreater(max(levels), 0.035)                   # it did slosh up near the brim

    def test_the_rebuild_sees_a_squeezed_level_function(self):
        # Fixed bug: the band the rebuild watches was picked by each element's farthest corner, so a level function
        # squeezed four times steeper than a distance (the case the hydrostatic split cannot stand) fell out of it
        # and read as a perfect distance.
        import numpy as np
        from skfem import MeshTri

        from cadgen._internal.fea.multiphase_ops import PROFILE_TOL, Phases, TwoPhaseProblem, TwoPhaseSolver

        mesh = MeshTri.init_tensor(np.linspace(0, 0.03, 13), np.linspace(0, 0.01, 5))
        solver = TwoPhaseSolver(TwoPhaseProblem(mesh, Phases(WATER, AIR, 1.002e-3, 1.81e-5), 0.005 - mesh.p[1], [0, -G0]))
        self.assertLess(solver.profile_error(0.005 - mesh.p[1]), 1e-9)
        self.assertGreater(solver.profile_error(4.0 * (0.005 - mesh.p[1])), PROFILE_TOL)


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
    """Water fed at 0.05 m/s into a half-full square duct (sharp corners at its inlet) through one end, out of the other.

    What moves, and how fast it may: the inlet switches on at once, and the cheapest way to make room for what it
    pushes in is to push the air out, so in the first step the air in the duct's top half carries nearly all of the
    inflow while the water barely starts (about 0.35 m/s at the top wall on this mesh: the air's half is a few
    elements of a smeared interface, and the speed goes as 1 / density across it). The open outlet spills water,
    which falls out of the end. Nothing here moves faster than the inlet's speed plus a free fall through the duct's
    whole height, 0.05 + sqrt(2 g 10 mm) = 0.49 m/s. Before the fix the inlet's level set was pinned to "liquid" over
    the whole inlet, the air half too: the jump it made fed the hydrostatic split a force of several g, and the air
    by the inlet's top corner ran away to 1.14 m/s (23 times the inflow) and was still accelerating.
    """

    def test_a_square_duct_fills_at_its_inflow_and_nothing_outruns_a_free_fall(self):
        inflow, side, length, end = 0.05, 10.0, 30.0, 0.02
        with tempfile.TemporaryDirectory() as tmp:
            step = box_duct_step(Path(tmp), side, length, wall=2.0)
            result = solve(step, {"analysis": "multiphase", "fill": {"fraction": 0.5}, "end_s": end, "mesh": {"size_mm": 3},
                                  "inlets": [{"opening": "x_min", "velocity_m_s": inflow}], "outlets": [{"opening": "x_max"}]})
        self.assertTrue(result.ok)
        summary = result.summary
        self.assertLess(summary["max_speed_m_s"], inflow + math.sqrt(2.0 * G0 * side * 1e-3))
        volume = summary["volume"]
        inside_L = side * side * length * 1e-6
        # Half full, as asked (the pinned inlet used to start it 7.6% fuller); the liquid's volume is what came in
        # less what spilled, to round-off; and no more came in than the inlet brings.
        self.assertAlmostEqual(volume["start_L"], 0.5 * inside_L, delta=1e-6 * inside_L)
        self.assertLess(abs(volume["error_percent"]), 1e-3)
        self.assertLessEqual(volume["net_inflow_L"], inflow * side * side * 1e-6 * end * 1e3)

    def test_a_completely_full_duct_is_single_fluid_flow_at_its_inflow(self):
        """Full (fill fraction 1) has no free surface: keeping the volume chased a share the smeared interface at the
        brim cannot reach and ran away (2.9e6 m/s, the volume 1900% off). Solved as the liquid's flow alone, the duct
        carries plug flow at the inlet's speed, and the result says it was solved so."""
        inflow, side, length = 0.05, 10.0, 30.0
        with tempfile.TemporaryDirectory() as tmp:
            step = box_duct_step(Path(tmp), side, length, wall=2.0)
            result = solve(step, {"analysis": "multiphase", "fill": {"fraction": 1.0}, "end_s": 0.02, "mesh": {"size_mm": 3},
                                  "inlets": [{"opening": "x_min", "velocity_m_s": inflow}], "outlets": [{"opening": "x_max"}]})
            extras, _ = glb_extras(result.glb)
        self.assertTrue(result.ok)
        summary = result.summary
        self.assertAlmostEqual(summary["max_speed_m_s"] / inflow, 1.0, delta=0.1)
        self.assertEqual(summary["single_fluid"], "Completely full: solved as single-fluid flow, no free surface")
        self.assertEqual(summary["volume"]["change_percent"], 0.0)
        self.assertIn("Completely full: solved as single-fluid flow, no free surface", result.human_lines())
        self.assertIn("single_fluid", [finding["type"] for finding in result.findings])
        self.assertIn("Completely full: solved as single-fluid flow, no free surface", extras["analysis"]["warnings"])


if __name__ == "__main__":
    unittest.main()
