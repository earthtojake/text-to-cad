"""Heat over time (`"analysis": "thermal_transient"`): the study it reads, lumped cooling, step doubling and the frames.

The benchmark is a 10 mm aluminium cube at 100 °C cooled by air at 20 °C on
every face (Bi = h (V/A) / k ≈ 0.001, so it cools as one lump):
T(t) = T_inf + (T_0 - T_inf) e^(-h A t / (ρ c V)). The STEP is a build123d box
in a temporary directory. The time march's step doubling is checked on the
same cube built directly in scikit-fem, warming by a heater on one face:
every joule put in is stored, so its mean temperature rises as P t / (ρ c V).
"""

from __future__ import annotations

import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
add_repo_path(".")

from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from tests.python.packages.cadgen.test_fea_thermal import box_step, glb_extras_and_attributes  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

ALUMINIUM = lookup_material("aluminum-6061-t6")
SIDE, H, T0, AIR = 10.0, 100.0, 100.0, 20.0
# τ = ρ c V / (h A), in seconds: ρ c in J/(m³ K), V/A = side / 6 in m, h in W/(m² K).
TAU = ALUMINIUM.density * 1e12 * ALUMINIUM.specific_heat * (SIDE / 1000 / 6) / H
BASE = {"analysis": "thermal_transient", "material": "aluminum-6061-t6", "end_s": 600,
        "heat": [{"faces": ["#o1.f7"], "W": 15, "history": [[0, 1], [300, 1], [301, 0]]}],
        "convection": [{"faces": ["#o1.f3"], "h_W_m2K": 10, "ambient_C": 25}]}


def lumped(t: float) -> float:
    return AIR + (T0 - AIR) * math.exp(-t / TAU)


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**BASE, **changes})

    def test_it_reads_the_run_the_start_and_each_schedule(self):
        inputs = self.parse(initial_C=30, step_s=2).inputs
        self.assertEqual((inputs.initial_C, inputs.end_s, inputs.step_s, inputs.first_step), (30.0, 600.0, 2.0, 2.0))
        self.assertEqual(inputs.heat[0].history, ((0.0, 1.0), (300.0, 1.0), (301.0, 0.0)))
        self.assertFalse(inputs.requires_anchor)  # an insulated part warming up is well posed over time
        self.assertEqual(inputs.reference_C, 25.0)
        auto = self.parse().inputs
        self.assertEqual((auto.initial_C, auto.step_s, auto.first_step), (20.0, None, 3.0))
        self.assertEqual(auto.reference_C, 20.0)  # the start is cooler than the air

    def test_a_schedule_is_a_straight_line_between_its_points(self):
        from cadgen._internal.fea.thermal_ops import factor_at

        schedule = ((0.0, 1.0), (300.0, 1.0), (301.0, 0.0))
        self.assertEqual([factor_at(schedule, t) for t in (0, 150, 300, 300.5, 301, 900)], [1, 1, 1, 0.5, 0, 0])
        self.assertEqual(factor_at((), 12.0), 1.0)
        self.assertEqual(factor_at(((10.0, 2.0),), 0.0), 2.0)

    def test_the_errors_name_the_field(self):
        cases = [
            ({"end_s": None}, "end_s"),
            ({"end_s": -1}, "end_s: must be > 0"),
            ({"step_s": 900}, "longer than the run"),
            ({"step_s": "fast"}, "step_s: expected a number"),
            ({"heat": [], "convection": []}, "nothing changes the part's temperature"),
            ({"heat": [{"faces": ["#o1.f7"], "W": 1, "history": [[5, 1], [2, 0]]}]}, "times must rise"),
            ({"heat": [{"faces": ["#o1.f7"], "W": 1, "history": [[0, 1, 2]]}]}, "[[t_s, factor], ...]"),
            ({"material": "steel", "view": {"checks": [{"kind": "temperature", "max_C": 10}]}}, "is not above 20 °C"),
            ({"material": {"name": "x", "E_MPa": 1e3, "nu": 0.3, "yield_MPa": 10, "density_t_per_mm3": 1e-9, "conductivity_W_mK": 1}},
             "specific_heat_J_kgK"),
        ]
        for changes, fragment in cases:
            document = {**BASE, **changes}
            document = {key: value for key, value in document.items() if value is not None}
            with self.subTest(changes=changes), self.assertRaises(ValueError) as caught:
                from cadgen._internal.fea.study import parse_study

                parse_study(document)
            self.assertIn(fragment, str(caught.exception))

    def test_its_view_has_a_time_scrubber(self):
        study = self.parse(view={"controls": [{"drives": "frame", "label": "Time"}, {"drives": "field"}]})
        self.assertEqual([control["drives"] for control in study.view["controls"]], ["frame", "field"])

    def test_time_reads_as_people_say_it(self):
        from cadgen._internal.fea.analyses.thermal_transient import time_label

        self.assertEqual([time_label(t) for t in (0, 0.012, 1.5, 45, 300, 9000)], ["0 s", "12 ms", "1.5 s", "45 s", "5 min", "2.5 h"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class LumpedCooling(unittest.TestCase):
    END = 2 * TAU

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = box_step(directory, "cube", (SIDE, SIDE, SIDE))
        every = [face.ref for face in fea.faces(step).faces]
        cls.top = next(face.ref for face in fea.faces(step).faces if face.normal and face.normal[2] > 0.999)
        study = {"analysis": "thermal_transient", "material": "aluminum-6061-t6", "mesh": {"size_mm": 5.0},
                 "initial_C": T0, "end_s": cls.END,
                 "convection": [{"faces": every, "h_W_m2K": H, "ambient_C": AIR}],
                 "view": {"checks": [{"kind": "temperature", "max_C": 120, "faces": [cls.top], "label": "Lid"}]}}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "cube.glb", study=study)
        cls.extras, cls.attributes = glb_extras_and_attributes(
            cls.result.glb, ("_TEMPERATURE", "_TEMPERATURE_F1", "_HEAT_FLUX_F1"))
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_cools_as_one_lump(self):
        curve = self.sidecar["curves"]["max_temperature_C"]
        self.assertEqual((curve["x_unit"], curve["y_unit"]), ("s", "°C"))
        self.assertEqual(len(curve["x"]), 201)  # t = 0 and the 200 steps of "auto"
        for t, value in zip(curve["x"][::40], curve["y"][::40]):
            with self.subTest(t=t):
                self.assertAlmostEqual((value - AIR) / (lumped(t) - AIR), 1.0, delta=0.03)
        self.assertAlmostEqual((self.result.summary["final_max_temperature_C"] - AIR) / (lumped(self.END) - AIR), 1.0, delta=0.03)

    def test_it_keeps_24_frames_from_the_start_and_opens_on_the_hottest(self):
        series = self.extras["series"]
        self.assertEqual((series["kind"], series["unit"]), ("time", "s"))
        self.assertEqual(len(series["frames"]), 23)  # cooling: the hottest step is the start, already a frame
        self.assertEqual(series["default"], 0)
        self.assertEqual(series["frames"][0], {"value": 0.0, "label": "0 s",
                                               "attributes": {"temperature": "_TEMPERATURE", "heat_flux": "_HEAT_FLUX"}})
        self.assertEqual(series["frames"][1]["attributes"]["temperature"], "_TEMPERATURE_F1")
        self.assertAlmostEqual(series["frames"][-1]["value"], self.END, places=6)
        self.assertTrue(all(value == (T0,) for value in self.attributes["_TEMPERATURE"]))
        self.assertLess(max(v for (v,) in self.attributes["_TEMPERATURE_F1"]), T0)
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertTrue(fields["temperature"]["per_frame"] and fields["temperature"]["signed"])
        self.assertEqual(fields["temperature"]["max"], T0)
        self.assertAlmostEqual(fields["temperature"]["min"], self.result.summary["min_temperature_C"])

    def test_a_check_judges_the_hottest_over_all_time_and_says_when(self):
        check = self.result.summary["checks"][0]
        self.assertEqual((check["label"], check["status"], check["value"], check["reference"]), ("Lid", "passes", T0, AIR))
        self.assertEqual(check["at"], {"frame": 0, "value": 0.0, "unit": "s", "time_s": 0.0})

    def test_the_glb_and_the_cli_say_what_it_is(self):
        self.assertEqual(self.extras["analysis"]["type"], "thermal_transient")
        self.assertEqual(self.extras["study"]["initial_C"], T0)
        self.assertEqual(self.extras["study"]["step_s"], "auto")
        self.assertEqual(self.result.summary["steps"], 200)
        lines = self.result.human_lines()
        self.assertTrue(lines[1].startswith("hottest 100 °C at 0 s"))
        self.assertIn("in 200 steps", lines[2])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class StepDoubling(unittest.TestCase):
    """The march on a scikit-fem cube: adaptive steps keep the lumped answer with fewer steps, and store every joule."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        from skfem import MeshTet, MeshTet2

        from cadgen._internal.fea import operators
        from cadgen._internal.fea.femspace import FemSpace

        mesh = MeshTet2.from_mesh(MeshTet.init_tensor(*(np.linspace(0, SIDE, 4),) * 3))
        cls.space = FemSpace.from_mesh(mesh)
        cls.capacity = operators.capacity(cls.space, ALUMINIUM)
        cls.every = mesh.boundary_facets()
        cls.top = mesh.facets_satisfying(lambda x: np.isclose(x[2], SIDE), boundaries_only=True)

    def march(self, system, end, step, adaptive):
        from cadgen._internal.fea import thermal_ops

        return thermal_ops.march(system, self.capacity, T0 if system.films else 20.0, end, step, [], adaptive=adaptive)

    def test_cooling_with_adaptive_steps_holds_the_lumped_answer_in_fewer_steps(self):
        from cadgen._internal.fea import thermal_ops

        system = thermal_ops.assemble(self.space, ALUMINIUM, films=[(self.every, H, AIR, ())])
        end = 2 * TAU
        fixed = self.march(system, end, end / 200, adaptive=False)
        adaptive = self.march(system, end, end / 200, adaptive=True)
        self.assertLess(adaptive.steps, fixed.steps)
        self.assertGreater(adaptive.largest_step, end / 200)
        self.assertAlmostEqual((adaptive.final.max() - AIR) / (lumped(end) - AIR), 1.0, delta=0.03)

    def test_a_heated_insulated_cube_stores_every_joule_and_heats_to_the_end(self):
        from cadgen._internal.fea import thermal_ops

        watts, end = 5.0, 60.0
        system = thermal_ops.assemble(self.space, ALUMINIUM, heat=[(self.top, watts, None, ())])
        run = self.march(system, end, end / 50, adaptive=True)
        weights = self.capacity @ (run.final * 0 + 1)
        mean = float(weights @ run.final / weights.sum())
        rise = watts * end / (ALUMINIUM.density * 1e12 * ALUMINIUM.specific_heat * (SIDE / 1000) ** 3)
        self.assertAlmostEqual((mean - 20.0) / rise, 1.0, delta=1e-6)  # backward Euler stores exactly what goes in
        self.assertEqual(run.hottest_time, end)
        self.assertEqual(run.hottest_frame, len(run.frames) - 1)
        self.assertGreater(run.node_peak[0], 20.0)

    def test_a_switched_off_heater_cools_back_and_the_peak_is_its_own_frame(self):
        from cadgen._internal.fea import thermal_ops

        system = thermal_ops.assemble(self.space, ALUMINIUM, heat=[(self.top, 5.0, None, ((0.0, 1.0), (7.0, 1.0), (7.01, 0.0)))])
        run = self.march(system, 60.0, 0.3, adaptive=False)
        self.assertLessEqual(len(run.frames), 24)
        self.assertGreater(run.hottest, run.final.max())
        # Backward Euler takes each step's heat at its end: the last step wholly before the switch-off is the hottest.
        self.assertTrue(6.6 <= run.hottest_time <= 7.4)
        self.assertEqual(run.frames[run.hottest_frame][0], run.hottest_time)


class Ladder(unittest.TestCase):
    def test_its_rungs_are_the_spec_s(self):
        from cadgen._internal.fea.analyses import get_analysis

        self.assertEqual(get_analysis("thermal_transient").ladder,
                         ("iterative", "local_refine", "defeature", "linear_elements", "symmetry", "adaptive_steps"))
        self.assertEqual(get_analysis("thermal").ladder, ("iterative", "local_refine", "defeature", "linear_elements", "symmetry"))

    def test_adaptive_steps_is_a_step_said_in_words_that_cuts_the_estimate(self):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.analyses.base import SolveContext

        analysis = get_analysis("thermal_transient")
        inputs = analysis.parse(BASE)
        geometry = fit.Geometry(volume_mm3=1000.0, area_mm2=600.0, bbox_diagonal_mm=17.3)
        ctx = SolveContext(None, (), {}, None, None, False, {}, fit.default_budget(), fit.FitPlan(size_mm=2.0, requested_mm=2.0),
                           geometry=geometry)
        before = analysis.estimate(ctx, inputs)
        step = analysis.apply("adaptive_steps", ctx, inputs)
        self.assertEqual(step.rung, "adaptive_steps")
        self.assertIn("time step", step.words)
        self.assertEqual(step.accuracy_pct, 0.2)
        self.assertTrue(ctx.plan.adaptive_steps)
        self.assertLess(analysis.estimate(ctx, inputs).seconds, before.seconds)
        self.assertIsNone(analysis.apply("adaptive_steps", ctx, inputs))  # taken once
        # No matrix-free operator for temperatures: it never looks cheaper than multigrid.
        ctx.plan.solver = "matrix_free"
        free = analysis.estimate(ctx, inputs)
        ctx.plan.solver = "iterative"
        self.assertEqual(free, analysis.estimate(ctx, inputs))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class OverBudget(unittest.TestCase):
    """A run that misses a tiny time target completes by taking adaptive_steps, and says so everywhere."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = box_step(directory, "cube", (SIDE, SIDE, SIDE))
        every = [face.ref for face in fea.faces(step).faces]
        study = {"analysis": "thermal_transient", "material": "aluminum-6061-t6", "mesh": {"size_mm": 5.0},
                 "initial_C": T0, "end_s": 2 * TAU, "convection": [{"faces": every, "h_W_m2K": H, "ambient_C": AIR}],
                 "fit": {"seconds": 0.001, "allow": ["adaptive_steps"]}}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "cube.glb", study=study)
        cls.extras, _ = glb_extras_and_attributes(cls.result.glb, ())
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_completes_by_taking_adaptive_steps(self):
        self.assertTrue(self.result.ok)
        rungs = [step["rung"] for step in self.result.fit]
        self.assertEqual(rungs[0], "adaptive_steps")
        self.assertTrue(self.result.summary["adaptive"])
        self.assertLess(self.result.summary["steps"], 200)
        # The benchmark still holds (step doubling keeps each step within 0.2 % of the range).
        self.assertAlmostEqual((self.result.summary["final_max_temperature_C"] - AIR) / (lumped(2 * TAU) - AIR), 1.0, delta=0.03)

    def test_the_step_is_said_in_the_glb_the_sidecar_the_cli_and_a_finding(self):
        words = self.result.fit[0]["words"]
        self.assertIn("time step", words)
        self.assertEqual(self.extras["fit"][0]["words"], words)
        self.assertEqual(self.sidecar["fit"][0]["accuracy_pct"], 0.2)
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in self.result.human_lines()))
        self.assertIn("fit_adaptive_steps", [finding["type"] for finding in self.result.findings])


if __name__ == "__main__":
    unittest.main()
