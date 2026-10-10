"""Over time (``transient``): the study it takes, the time integrators, and a suddenly loaded cantilever against theory.

A load applied all at once to an undamped part makes it overshoot: a single
mass on a spring under a sudden constant force F swings to 2 F / k, twice its
steady (static) answer, and back. A cantilever does the same at its tip, mode by
mode, so its peak tip displacement is 2× the static one (spec section 13, 5 %),
by both methods: ``modal`` (modes integrated exactly, plus the static share of
the modes left out) and ``direct`` (Newmark's average acceleration, which adds
no numerical damping). The beam is a build123d box written to a temporary STEP:
100 mm long, 6 x 6 mm steel, clamped at x = 0, a 10 N tip force stepped on.
Shaken at its clamp by a 1 g step instead, it overshoots to twice its sag under
a steady 1 g, qL⁴/(8EI).

Parse and integrator tests need no mesh; the beam needs the fea extra.
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
from types import SimpleNamespace

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

LENGTH, SIDE, FORCE = 100.0, 6.0, 10.0
STEEL = lookup_material("steel")
G0 = 9806.65
TIP = "#o1.f2"
FIXED = "#o1.f1"


def _study(**more) -> dict:
    return {"analysis": "transient", "material": "steel", "fixtures": [{"faces": [FIXED]}],
            "loads": [{"faces": [TIP], "type": "force", "vector_N": [0, 0, -FORCE], "history": {"shape": "step"}}],
            "end_s": 0.006, **more}


class StudyFile(unittest.TestCase):
    def test_loads_carry_their_histories_and_the_run_its_defaults(self):
        parsed = parse_study(_study(loads=[
            {"faces": [TIP], "type": "force", "vector_N": [0, 0, -50], "history": {"shape": "half_sine", "duration_s": 0.002}},
            {"faces": ["#o1.f3"], "type": "pressure", "pressure_MPa": 1, "history": [[0, 0], [0.001, 1], [0.003, 0]]}]))
        inputs = parsed.inputs
        self.assertEqual(parsed.analysis, "transient")
        self.assertEqual([h.shape for h in inputs.histories], ["half_sine", "table"])
        self.assertEqual((inputs.end_s, inputs.step_s, inputs.damping_ratio, inputs.method), (0.006, None, 0.02, "modal"))
        self.assertEqual((inputs.face_refs, inputs.anchor_refs, inputs.excitation), ((FIXED, TIP, "#o1.f3"), (FIXED,), None))
        self.assertEqual(parsed.checks, ({"kind": "stress"},))
        # The fastest load sets the modes: a 2 ms half-sine carries up to 500 Hz, followed to 3×.
        self.assertAlmostEqual(inputs.content_Hz(), 1000.0)  # the table's 1 ms rise
        self.assertAlmostEqual(inputs.top_Hz, 3000.0)

    def test_a_base_shake_with_a_history_needs_no_loads(self):
        inputs = parse_study(_study(loads=None, excitation={"direction": [0, 0, 2], "amplitude_g": 5,
                                                            "history": {"shape": "ramp", "duration_s": 0.001}},
                                    method="direct", damping_ratio=0, step_s=1e-5)).inputs
        self.assertEqual((inputs.loads, inputs.excitation.direction, inputs.excitation.amplitude_g), ((), (0.0, 0.0, 1.0), 5.0))
        self.assertEqual((inputs.method, inputs.damping_ratio, inputs.first_step()), ("direct", 0.0, 1e-5))

    def test_what_is_wrong_is_said_in_plain_words(self):
        bare = {"faces": [TIP], "type": "force", "vector_N": [0, 0, -1]}
        for bad, words in (
            ({"loads": [bare]}, "how the load changes over time"),
            ({"loads": [{**bare, "history": {"shape": "square"}}]}, "is not one of \"step\""),
            ({"loads": [{**bare, "history": {"shape": "half_sine"}}]}, "how long the pulse lasts"),
            ({"loads": [{**bare, "history": {"shape": "step", "duration_s": 1}}]}, "takes no duration"),
            ({"loads": [{**bare, "history": [[0, 1], [0, 2]]}]}, "times must rise"),
            ({"loads": [{**bare, "history": [[0, 0], [1, 0]]}]}, "never acts"),
            ({"loads": [{"type": "gravity", "vector_g": [0, 0, -1], "history": {"shape": "step"}}]}, "is not one of"),
            ({"loads": None}, "nothing pushes or shakes it"),
            ({"excitation": {"direction": [0, 0, 1]}}, "excitation.history"),
            ({"excitation": {"type": "force", "history": {"shape": "step"}}}, "forces over time go in loads"),
            ({"end_s": None}, "how long to follow the motion"),
            ({"step_s": 1.0}, "longer than the run"),
            ({"damping_ratio": -0.1}, "from 0"),
            ({"method": "explicit"}, "is not one of \"modal\""),
            ({"sweep_Hz": [1, 2]}, "transient studies take"),
        ):
            study = {key: value for key, value in {**_study(), **bad}.items() if value is not None}
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study(study)

    def test_it_takes_stress_and_displacement_and_a_time_scrubber(self):
        parsed = parse_study(_study(view={"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 1}],
                                          "presets": [{"label": "At the peak", "frame": 0.001}]}))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "displacement"])
        with self.assertRaisesRegex(ValueError, "not a check this cadgen makes"):
            parse_study(_study(view={"checks": [{"kind": "frequency", "min_Hz": 60}]}))


class Histories(unittest.TestCase):
    def test_each_shape_its_factor_its_corners_and_its_words(self):
        import numpy as np

        from cadgen._internal.fea.analyses.transient import parse_time_history

        t = np.array([-1e-3, 0.0, 0.5e-3, 1e-3, 2e-3, 3e-3])
        step = parse_time_history({"shape": "step"}, "h")
        ramp = parse_time_history({"shape": "ramp", "duration_s": 2e-3}, "h")
        pulse = parse_time_history({"shape": "half_sine", "duration_s": 2e-3}, "h")
        table = parse_time_history([[0, 0], [1e-3, 1], [2e-3, 1]], "h")
        np.testing.assert_allclose(step.values(t), [0, 1, 1, 1, 1, 1])
        np.testing.assert_allclose(ramp.values(t), [0, 0, 0.25, 0.5, 1, 1])
        np.testing.assert_allclose(pulse.values(t), [0, 0, math.sin(math.pi / 4), 1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(table.values(t), [0, 0, 0.5, 1, 1, 1])
        self.assertEqual((ramp.corners, table.corners, step.corners), ((2e-3,), (0.0, 1e-3, 2e-3), ()))
        self.assertEqual([h.words() for h in (step, ramp, pulse, table)],
                         ["step", "ramp over 2 ms", "half-sine, 2 ms", "table of 3 points to 2 ms"])
        self.assertEqual((pulse.echo(), table.echo()), ({"shape": "half_sine", "duration_s": 2e-3}, [[0, 0], [1e-3, 1], [2e-3, 1]]))
        # A step jumps: it carries what the step resolves; the others their quickest change.
        self.assertEqual((step.content_Hz(4000.0), pulse.content_Hz(4000.0), table.content_Hz(4000.0)), (4000.0, 500.0, 1000.0))

    def test_the_time_grid_lands_on_every_corner(self):
        from cadgen._internal.fea.analyses.transient import time_grid

        times = time_grid(0.01, 0.003, [0.0045, 0.02])
        self.assertEqual([round(t, 9) for t in times], [0.0, 0.003, 0.0045, 0.006, 0.009, 0.01])


class Integrators(unittest.TestCase):
    """The shared time stepping (timestep.py) on single oscillators, against their closed forms."""

    def test_modal_march_is_exact_for_a_step_damped_or_not(self):
        import numpy as np

        from cadgen._internal.fea import timestep

        omega = 2 * math.pi * 10.0
        times = np.linspace(0, 0.2, 41)  # five steps a period: still exact, the load is linear between them
        for zeta in (0.0, 0.05):
            Q, _ = timestep.modal_march(np.array([omega]), zeta, times, np.ones((len(times), 1)))
            wd = omega * math.sqrt(1 - zeta ** 2)
            exact = (1 - np.exp(-zeta * omega * times) * (np.cos(wd * times) + zeta / math.sqrt(1 - zeta ** 2) * np.sin(wd * times))) / omega ** 2
            np.testing.assert_allclose(Q[:, 0], exact, atol=1e-12 / omega ** 2)
        # Undamped, it swings to twice its static answer 1/ω².
        Q, _ = timestep.modal_march(np.array([omega]), 0.0, times, np.ones((len(times), 1)))
        self.assertAlmostEqual(Q[:, 0].max() * omega ** 2, 2.0, places=9)

    def test_newmark_overshoots_twice_without_numerical_damping_and_adapts_its_step(self):
        import numpy as np
        import scipy.sparse as sparse

        from cadgen._internal.fea import timestep

        omega = 2 * math.pi * 10.0
        K, M = sparse.csr_matrix([[omega ** 2]]), sparse.csr_matrix([[1.0]])
        fixed, adaptive = [], []
        run = timestep.newmark(M, None, K, lambda t: np.array([1.0]), 1.0, 0.002, on_step=lambda t, u, v, a: fixed.append(u[0]))
        self.assertEqual(run.steps, 500)
        self.assertAlmostEqual(max(fixed) * omega ** 2, 2.0, delta=1e-4)
        # Ten periods later it still swings to 2: average acceleration keeps every cycle's size.
        self.assertAlmostEqual(max(fixed[-50:]) * omega ** 2, 2.0, delta=2e-3)
        run = timestep.newmark(M, None, K, lambda t: np.array([1.0]), 1.0, 0.002, adaptive=True,
                               on_step=lambda t, u, v, a: adaptive.append(u[0]))
        self.assertLess(run.steps, 500)
        self.assertGreater(run.largest_step, 0.002)
        self.assertAlmostEqual(max(adaptive) * omega ** 2, 2.0, delta=0.01)

    def test_rayleigh_damping_holds_the_ratio_at_both_modes(self):
        from cadgen._internal.fea import timestep

        alpha, beta = timestep.rayleigh(100.0, 600.0, 0.02)
        for omega in (100.0, 600.0):
            self.assertAlmostEqual(alpha / (2 * omega) + beta * omega / 2, 0.02, places=12)
        self.assertEqual(timestep.rayleigh(100.0, 600.0, 0.0), (0.0, 0.0))

    def test_theta_backward_euler_follows_a_first_order_decay(self):
        import numpy as np
        import scipy.sparse as sparse

        from cadgen._internal.fea import timestep

        one = sparse.csr_matrix([[1.0]])
        states = []
        run = timestep.theta(one, one, lambda t: np.array([1.0]), 5.0, 0.01, theta=0.5, on_step=lambda t, u: states.append(u[0]))
        self.assertAlmostEqual(states[-1], 1 - math.exp(-5.0), delta=1e-6)
        states.clear()
        run = timestep.theta(one, one, lambda t: np.array([1.0]), 5.0, 0.01, adaptive=True, on_step=lambda t, u: states.append(u[0]))
        self.assertLess(run.steps, 500)
        self.assertAlmostEqual(states[-1], 1 - math.exp(-5.0), delta=1e-3)


class Ladder(unittest.TestCase):
    def test_it_declares_the_spec_ladder(self):
        self.assertEqual(get_analysis("transient").ladder, ("reduce_modes", "iterative", "local_refine", "defeature",
                                                             "linear_elements", "symmetry", "adaptive_steps"))

    def test_reduce_modes_switches_direct_to_modal_in_words(self):
        from cadgen._internal.fea.fit import FitPlan

        analysis = get_analysis("transient")
        inputs = parse_study(_study(method="direct")).inputs
        ctx = SimpleNamespace(plan=FitPlan(), budget=None)
        step = analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual((step.rung, analysis.method_of(ctx.plan, inputs)), ("reduce_modes", "modal"))
        self.assertIn("instead of stepping the whole model through time (direct)", step.words)
        # Modal now: adaptive steps do not apply; a second reduce_modes keeps fewer modes.
        self.assertIsNone(analysis.apply("adaptive_steps", ctx, inputs))
        self.assertEqual(analysis.apply("reduce_modes", ctx, inputs).rung, "reduce_modes")
        self.assertEqual(ctx.plan.modes, 6)
        for rung in ("idealise", "symmetry"):
            self.assertIsNone(analysis.apply(rung, ctx, inputs))


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SuddenTipForce(unittest.TestCase):
    """The undamped cantilever with a 10 N tip force stepped on, followed for three periods of mode 1 (490 Hz)."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(cls.step))
        cls.fixed, cls.tip = _ends(fea.faces(cls.step))
        cls.study = _study(fixtures=[{"faces": [cls.fixed]}], loads=[
            {"faces": [cls.tip], "type": "force", "vector_N": [0, 0, -FORCE], "history": {"shape": "step"}}],
            mesh={"size_mm": 3.0}, damping_ratio=0, view={"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 1.0}]})
        cls.results = {}
        with redirect_stderr(io.StringIO()):
            for method in ("modal", "direct"):
                cls.results[method] = fea.solve(cls.step, cls.directory / f"{method}.fea.glb", study={**cls.study, "method": method})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _solve(self, name: str, **more):
        from cadgen import fea

        with redirect_stderr(io.StringIO()):
            return fea.solve(self.step, self.directory / f"{name}.fea.glb", study={**self.study, **more})

    def test_the_peak_is_twice_the_static_answer_by_both_methods(self):
        static_theory = FORCE * LENGTH ** 3 / (3 * STEEL.E * SIDE ** 4 / 12)
        for method, result in self.results.items():
            with self.subTest(method=method):
                summary = result.summary
                self.assertEqual(summary["method"], method)
                # The steady answer is the beam's PL³/3EI; the sudden load swings the tip to twice it.
                self.assertAlmostEqual(summary["static_displacement_mm"] / static_theory, 1.0, delta=0.05)
                self.assertAlmostEqual(summary["dynamic_amplification"] / 2.0, 1.0, delta=0.05)
                self.assertAlmostEqual(summary["max_displacement_mm"] / (2 * static_theory), 1.0, delta=0.05)
                self.assertAlmostEqual(summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)
                # The stress swings to about twice the steady one too; at the clamp's corners the higher modes ring
                # with it, a little out of step, so its peak (a von Mises, never negative) reads somewhat over 2×.
                self.assertTrue(1.8 < summary["max_von_mises_MPa"] / summary["static_von_mises_MPa"] < 2.5)
        modal = self.results["modal"].summary
        # Mode 1's half period: the first time the tip is furthest.
        f1 = modal["modes"][0]["frequency_Hz"]
        self.assertAlmostEqual(modal["max_von_mises_at_s"] * 2 * f1, 1.0, delta=0.05)
        self.assertAlmostEqual(modal["modes_up_to_Hz"], 3 * modal["load_content_Hz"], places=3)
        self.assertTrue(all(mode["used"] for mode in modal["modes"]))
        direct = self.results["direct"].summary
        self.assertAlmostEqual(direct["first_modes_Hz"][0] / f1, 1.0, delta=1e-3)
        self.assertEqual(direct["rayleigh"]["alpha_per_s"], 0.0)

    def test_the_checks_judge_the_peaks_and_say_when(self):
        result = self.results["modal"]
        stress, moved = result.summary["checks"]
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        frames = sidecar["series"]["frames"]
        self.assertEqual((stress["status"], stress["at"]["unit"]), ("passes", "s"))
        self.assertEqual(stress["at"]["frame"], sidecar["series"]["default"])
        self.assertAlmostEqual(frames[stress["at"]["frame"]]["value"], stress["at"]["time_s"], places=9)
        self.assertAlmostEqual(stress["value"], result.summary["max_von_mises_MPa"])
        self.assertEqual((moved["kind"], moved["status"]), ("displacement", "passes"))
        self.assertAlmostEqual(moved["value"], result.summary["max_displacement_mm"], places=5)
        found = {finding["type"]: finding for finding in result.findings}
        self.assertTrue(found["transient_peak"]["summary"].startswith("Moves most at "))
        self.assertIn("× its steady response to the same loads", found["transient_peak"]["summary"])

    def test_the_glb_carries_a_time_series_and_the_peak_envelopes(self):
        gltf = _glb(self.results["modal"].glb)
        extras = gltf["meshes"][0]["extras"]
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(extras["analysis"]["type"], "transient")
        self.assertEqual([field["field"] for field in extras["fields"]],
                         ["von_mises", "displacement", "von_mises_peak", "displacement_peak"])
        self.assertEqual([field.get("per_frame", False) for field in extras["fields"]], [True, True, False, False])
        self.assertIn("_VON_MISES_PEAK", attributes)
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"]), ("time", "s"))
        values = [frame["value"] for frame in series["frames"]]
        self.assertTrue(len(values) <= 24 and values == sorted(values) and values[0] == 0.0 and values[-1] == 0.006)
        self.assertEqual(series["frames"][1]["attributes"], {"von_mises": "_VON_MISES_F1", "displacement": "_DISPLACEMENT_F1"})
        self.assertTrue(series["frames"][series["default"]]["label"].endswith("ms"))
        self.assertEqual(extras["study"]["loads"][0]["history"], {"shape": "step"})
        self.assertEqual((extras["study"]["end_s"], extras["study"]["step_s"], extras["study"]["method"]), (0.006, "auto", "modal"))

    def test_the_sidecar_and_the_cli_lines(self):
        result = self.results["modal"]
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        curve = sidecar["curves"]["max_displacement_mm"]
        self.assertEqual((curve["x"][0], curve["x_unit"]), (0.0, "s"))
        # At rest at the start, but for the modes left out, whose steady share the static correction adds at once.
        self.assertLess(curve["y"][0], 0.002 * max(curve["y"]))
        self.assertAlmostEqual(max(curve["y"]), result.summary["max_displacement_mm"], places=6)
        lines = result.human_lines()
        self.assertIn("(transient)", lines[0])
        self.assertTrue(lines[1].startswith("10 N step; followed for 6 ms in "))
        self.assertIn("each followed exactly, 0% damping", lines[1])
        self.assertIn("× its steady", lines[2])

    def test_shaken_at_the_clamp_by_a_sudden_g_it_sags_twice_as_far(self):
        result = self._solve("base", loads=None, excitation={"direction": [0, 0, 1], "amplitude_g": 1, "history": {"shape": "step"}})
        q = STEEL.density * SIDE * SIDE * G0
        sag = q * LENGTH ** 4 / (8 * STEEL.E * SIDE ** 4 / 12)
        self.assertAlmostEqual(result.summary["static_displacement_mm"] / sag, 1.0, delta=0.05)
        self.assertAlmostEqual(result.summary["dynamic_amplification"] / 2.0, 1.0, delta=0.05)
        self.assertEqual(result.summary["excitation"]["history"], "step")
        self.assertIn("shaken 1 g along Z, step", result.human_lines()[1])

    def test_an_oversized_direct_run_switches_to_modal_and_says_so(self):
        result = self._solve("switched", method="direct", fit={"memory_GB": 0.01, "allow": ["reduce_modes"]})
        self.assertTrue(result.ok)
        step = result.fit[0]
        self.assertEqual(step["rung"], "reduce_modes")
        self.assertIn("Solved by modal superposition", step["words"])
        self.assertEqual(result.summary["method"], "modal")
        self.assertIn(f"adapted: {step['words']}", result.human_lines())
        self.assertIn("fit_reduce_modes", [finding["type"] for finding in result.findings])
        self.assertAlmostEqual(result.summary["dynamic_amplification"] / 2.0, 1.0, delta=0.05)

    def test_an_oversized_direct_run_completes_by_adaptive_steps(self):
        result = self._solve("adaptive", method="direct", fit={"seconds": 0.001, "allow": ["adaptive_steps"]})
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertEqual(rungs[0], "adaptive_steps")
        step = result.fit[0]
        self.assertTrue(step["accuracy"])
        self.assertIn(f"adapted: {step['words']} ({step['accuracy']})", result.human_lines())
        gltf = _glb(result.glb)
        self.assertIn(step["words"], [entry["words"] for entry in gltf["meshes"][0]["extras"]["fit"]])
        summary = result.summary
        # The step grew past the fixed run's, and the benchmark still holds within a widened 7 %.
        self.assertTrue(summary["adaptive"])
        self.assertLess(summary["steps"], self.results["direct"].summary["steps"])
        self.assertGreater(summary["largest_step_s"], summary["step_s"])
        self.assertAlmostEqual(summary["dynamic_amplification"] / 2.0, 1.0, delta=0.07)


if __name__ == "__main__":
    unittest.main()
