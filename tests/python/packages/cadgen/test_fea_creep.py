"""Creep: the study it takes, the Norton law and its tangent, the benchmarks, the GLB and the ladder.

Benchmarks (plan Y3, the Norton creep bar against the closed form):
- a bar under a constant stress: a 20 x 4 x 4 mm bar held on three symmetry
  planes and pulled with 100 MPa for 1000 h creeps ε_c = A σ^n t (1 %), and
  with time hardening (m = -0.5) ε_c = A σ^n t^(m+1) / (m+1) (1 %);
- the same bar held at a fixed stretch relaxes as the closed form
  σ(t) = [σ0^(1-n) + (n-1) E A t]^(1/(1-n)) (3 %), here to about half its
  starting stress;
- a ladder run with a tiny budget completes by letting the time steps grow,
  and says so in the GLB, the sidecar, the CLI lines and the findings.

The bars run on the engine (a structured mesh built in the test); the ladder
run through ``cadgen.fea.solve`` on a build123d box written to a temporary
STEP. Parse tests are stdlib only; the solves need the fea extra.
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

from cadgen._internal.fea.analyses import REGISTRY, get_analysis  # noqa: E402
from cadgen._internal.fea.analyses.creep import DEFAULT_STEPS, hours_label  # noqa: E402
from cadgen._internal.fea.materials import material_from_spec  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

E, NU = 200_000.0, 0.3
# Illustrative Norton constants (not a grade's data): 100 MPa creeps 1.875e-6 per hour.
A, N = 1.875e-16, 5.0
CREEPING = {"name": "steel", "creep": {"A": A, "n": N, "m": 0, "units": "MPa, hours"}}


def _study(**more) -> dict:
    return {"analysis": "creep", "material": CREEPING, "duration_h": 1000, "fixtures": [{"faces": ["#o1.f1"]}],
            "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -100]}], **more}


class StudyFile(unittest.TestCase):
    def test_it_is_built_and_takes_static_fixtures_and_loads_a_duration_and_a_creep_check(self):
        self.assertFalse(REGISTRY["creep"].planned)
        parsed = parse_study(_study())
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.duration_h, inputs.steps, inputs.temperature_C), ("creep", 1000.0, DEFAULT_STEPS, None))
        self.assertEqual(inputs.face_refs, ("#o1.f1", "#o1.f2"))
        self.assertEqual(parsed.checks, ({"kind": "creep_strain", "limit_percent": 1.0},))
        self.assertEqual(parse_study(_study(steps=50, temperature_C=550)).inputs.temperature_C, 550.0)
        checks = parse_study(_study(view={"checks": [{"kind": "creep_strain", "limit_percent": 0.5}, {"kind": "stress"},
                                                     {"kind": "displacement", "limit_mm": 2}]})).checks
        self.assertEqual([check["kind"] for check in checks], ["creep_strain", "stress", "displacement"])

    def test_the_material_carries_its_creep_law(self):
        steel = material_from_spec(CREEPING)
        self.assertEqual(steel.creep, {"A": A, "n": N, "m": 0.0, "units": "MPa, hours"})
        self.assertEqual(steel.as_dict()["creep"], steel.creep)
        per_second = material_from_spec({"name": "steel", "creep": {"A": 1e-20, "n": 4, "units": "MPa, s", "temperature_C": 600,
                                                                    "source": "a datasheet"}}).creep
        self.assertEqual((per_second["units"], per_second["temperature_C"], per_second["m"]), ("MPa, seconds", 600.0, 0.0))
        from cadgen._internal.fea.creep_law import norton_rate_per_hour

        self.assertAlmostEqual(norton_rate_per_hour(per_second) / (1e-20 * 3600), 1.0, places=12)
        self.assertIsNone(material_from_spec("steel").creep)

    def test_the_errors_say_what_to_add(self):
        cases = [
            (_study(material="steel"), "a creep study needs the material's creep law"),
            (_study(material={"name": "steel", "creep": {"n": 5}}), r"material.creep.A: a Norton creep law needs A and n"),
            (_study(material={"name": "steel", "creep": {"A": 1e-20, "n": 0.5}}), "from 1 to 20"),
            (_study(material={"name": "steel", "creep": {"A": 1e-20, "n": 5, "m": 0.5}}), "at most 0"),
            (_study(material={"name": "steel", "creep": {"A": 1e-20, "n": 5, "units": "psi, years"}}), "MPa, hours"),
            (_study(material={"name": "steel", "creep": {"A": 1e-20, "n": 5, "Q": 3}}), r"unknown keys \['Q'\]"),
            ({k: v for k, v in _study().items() if k != "duration_h"}, "duration_h: how long the load is held"),
            (_study(duration_h=0), "must be > 0"),
            (_study(steps=0), "from 1 to 1000"),
            (_study(modes=3), r"unknown keys \['modes'\]; creep studies take"),
            (_study(view={"checks": [{"kind": "creep_strain"}]}), "limit_percent"),
            (_study(view={"checks": [{"kind": "plastic_strain", "limit_percent": 1}]}), "is not a check this cadgen makes"),
        ]
        for study, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, fragment):
                parse_study(study)

    def test_there_is_no_load_control_and_the_ladder_is_the_spec_s(self):
        analysis = get_analysis("creep")
        self.assertNotIn("load_scale", analysis.drives)
        self.assertIn("frame", analysis.drives)
        self.assertEqual(analysis.ladder, ("iterative", "adaptive_steps", "local_refine", "defeature", "symmetry"))
        self.assertEqual((analysis.tier, analysis.word), (3, "Creep"))
        self.assertTrue(any("no tertiary creep" in limit for limit in analysis.limits))
        self.assertTrue(any("Isotropic" in limit for limit in analysis.limits))

    def test_its_words(self):
        self.assertEqual([hours_label(t) for t in (0.0, 2.5, 250.0, 10_000.0)], ["0 h", "2.5 h", "250 h", "10,000 h"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class NortonLaw(unittest.TestCase):
    def test_the_tangent_is_the_derivative_of_the_stress(self):
        import numpy as np

        from cadgen._internal.fea.creep_law import CreepParams, CreepState, norton_update

        rng = np.random.default_rng(3)
        shape = (2, 3)
        params = CreepParams(E / (3 * (1 - 2 * NU)), E / (2 * (1 + NU)), np.full(shape, 1e-14), np.full(shape, 4.0), np.zeros(shape))
        state = CreepState(1e-4 * np.einsum("ij,...->ij...", np.diag([1.0, -0.5, -0.5]), np.ones(shape)), 1e-4 * np.ones(shape),
                           150.0 * np.ones(shape))
        strain = 0.001 * rng.standard_normal((3, 3, *shape))
        strain = 0.5 * (strain + strain.transpose(1, 0, 2, 3))
        update = norton_update(strain, state, params, 10.0, 60.0)
        self.assertTrue((update.increment > 0).all())
        # Backward Euler: the increment is the rate at the END of the step, over the step.
        q = update.state.von_mises
        np.testing.assert_allclose(update.increment, 50.0 * 1e-14 * q ** 4, rtol=1e-9)
        h = 1e-8
        for k in range(3):
            for m in range(3):
                d = np.zeros_like(strain)
                d[k, m] += h / 2
                d[m, k] += h / 2
                numeric = (norton_update(strain + d, state, params, 10.0, 60.0, tangent=False).stress
                           - norton_update(strain - d, state, params, 10.0, 60.0, tangent=False).stress) / (2 * h)
                analytic = 0.5 * (update.tangent[:, :, k, m] + update.tangent[:, :, m, k])
                np.testing.assert_allclose(numeric, analytic, atol=1e-6 * np.abs(update.tangent).max())

    def test_a_step_of_no_time_is_elastic(self):
        import numpy as np

        from cadgen._internal.fea.creep_law import CreepParams, CreepState, norton_update
        from cadgen._internal.fea.plasticity import elastic_tensor

        shape = (1, 1)
        K, G = E / (3 * (1 - 2 * NU)), E / (2 * (1 + NU))
        params = CreepParams(K, G, np.full(shape, A), np.full(shape, N), np.zeros(shape))
        strain = np.zeros((3, 3, *shape))
        strain[0, 0] = 1e-3
        update = norton_update(strain, CreepState.zeros(shape), params, 0.0, 0.0)
        self.assertEqual(float(update.increment.max()), 0.0)
        np.testing.assert_allclose(update.tangent, elastic_tensor(K, G, shape))


def _bar(length=20.0, side=4.0):
    """A structured quadratic-tet bar held on its three symmetry planes (x = 0, y = 0, z = 0): uniaxial along x."""
    import numpy as np
    from skfem import LinearForm, MeshTet, MeshTet2, asm

    from cadgen._internal.fea.femspace import FemSpace

    mesh = MeshTet2.from_mesh(MeshTet.init_tensor(np.linspace(0, length, 6), np.linspace(0, side, 2), np.linspace(0, side, 2)))
    space = FemSpace.from_mesh(mesh)
    basis = space.basis
    held = []
    for axis in range(3):
        dofs = basis.get_dofs(mesh.facets_satisfying(lambda x, axis=axis: np.isclose(x[axis], 0.0))).all()
        held.append(dofs[space.component[dofs] == axis])
    end_facets = mesh.facets_satisfying(lambda x: np.isclose(x[0], length))
    end_dofs = basis.get_dofs(end_facets).all()
    end_x = end_dofs[space.component[end_dofs] == 0]
    end = basis.boundary(end_facets)

    def pull(nominal_MPa):
        @LinearForm
        def form(v, w):
            return nominal_MPa * v[0]

        return asm(form, end)

    def stretch(u):
        return float(u[(space.component == 0) & np.isclose(space.locations[:, 0], length)].mean()) / length

    return space, np.concatenate(held), end_x, pull, stretch


def _march(space, held, external, material, duration, *, u0=None, steps=DEFAULT_STEPS, adaptive=False):
    import numpy as np

    from cadgen._internal.fea.analyses.creep import _CreepProblem, _march as march
    from cadgen._internal.fea.creep_law import creep_params

    free = np.setdiff1d(np.arange(space.basis.N), held)
    problem = _CreepProblem(space, free, external, creep_params(space, [material]))
    path, frames, curve = march(problem, duration, steps, solver="direct", adaptive=adaptive, keep=24, log=None, u0=u0)
    return problem, path, frames, curve


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Bars(unittest.TestCase):
    STRESS, HOURS = 100.0, 1000.0

    def test_a_bar_under_constant_stress_creeps_a_sigma_to_the_n_t(self):
        space, held, _, pull, stretch = _bar()
        for m in (0.0, -0.5):
            with self.subTest(m=m):
                material = material_from_spec({"name": "steel", "creep": {"A": A, "n": N, "m": m}})
                problem, path, frames, curve = _march(space, held, pull(self.STRESS), material, self.HOURS)
                exact = A * self.STRESS ** N * self.HOURS ** (m + 1) / (m + 1)
                creep = stretch(frames[-1][1]) - self.STRESS / E
                self.assertAlmostEqual(creep / exact, 1.0, delta=0.01)
                self.assertAlmostEqual(float(problem.state.equivalent.mean()) / exact, 1.0, delta=0.01)
                # Constant stress: it does not relax, the elastic stretch is there at 0 h and the steps never needed cutting.
                self.assertAlmostEqual(float(problem.state.von_mises.mean()) / self.STRESS, 1.0, delta=1e-6)
                self.assertAlmostEqual(stretch(frames[0][1]) / (self.STRESS / E), 1.0, delta=1e-6)
                self.assertEqual((path.rejected, path.stopped), (0, False))
                self.assertEqual(frames[-1][0], self.HOURS)
                self.__class__.benchmark = getattr(self.__class__, "benchmark", {})
                self.benchmark[f"constant stress m={m}"] = (creep, exact)

    def test_a_bar_held_at_a_fixed_stretch_relaxes_as_the_closed_form(self):
        import numpy as np

        space, held, end_x, _, stretch = _bar()
        strain0 = 0.0005  # 100 MPa at the instant it is stretched
        u0 = np.zeros(space.basis.N)
        u0[end_x] = strain0 * 20.0
        material = material_from_spec({"name": "steel", "creep": {"A": A, "n": N}})
        for adaptive in (False, True):
            with self.subTest(adaptive=adaptive):
                problem, path, frames, curve = _march(space, np.concatenate([held, end_x]), np.zeros(space.basis.N), material,
                                                      self.HOURS, u0=u0, adaptive=adaptive)
                start = E * strain0
                exact = (start ** (1 - N) + (N - 1) * E * A * self.HOURS) ** (1 / (1 - N))
                relaxed = float(problem.state.von_mises.mean())
                self.assertAlmostEqual(float(frames[0][2].mean()) / start, 1.0, delta=1e-6)
                self.assertAlmostEqual(relaxed / exact, 1.0, delta=0.03)
                self.assertLess(exact / start, 0.55)  # it really relaxes: to about half
                self.assertAlmostEqual(stretch(frames[-1][1]), strain0, delta=1e-12)  # the stretch is held
                # The stress falls frame by frame: relaxation shows in the series.
                peaks = [float(vm.max()) for _, _, vm, _ in frames]
                self.assertTrue(all(b <= a + 1e-9 for a, b in zip(peaks, peaks[1:])))
                self.__class__.benchmark = getattr(self.__class__, "benchmark", {})
                self.benchmark[f"relaxation adaptive={adaptive} ({path.steps} steps, {path.rejected} cut)"] = (relaxed, exact)

    @classmethod
    def tearDownClass(cls):
        for name, (got, exact) in getattr(cls, "benchmark", {}).items():
            print(f"creep benchmark {name}: {got:.6g} against {exact:.6g} ({(got / exact - 1) * 100:+.2f} %)")


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _box(directory: Path, name: str, size: tuple[float, float, float], axis: int) -> tuple[Path, str, str]:
    """A box written to a STEP, and its two end faces along ``axis`` (low, high)."""
    from build123d import Align, Box, export_step

    from cadgen import fea

    step = directory / f"{name}.step"
    export_step(Box(*size, align=(Align.MIN, Align.MIN, Align.MIN)), str(step))
    ends = {face.center_mm[axis]: face.ref for face in fea.faces(step).faces
            if face.normal is not None and abs(abs(face.normal[axis]) - 1) < 1e-6}
    return step, ends[min(ends)], ends[max(ends)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    def test_adaptive_steps_cut_the_estimate(self):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.base import SolveContext

        analysis = get_analysis("creep")
        inputs = analysis.parse(_study())
        big = fit.Geometry(volume_mm3=2e6, area_mm2=1e5, bbox_diagonal_mm=300.0)
        ctx = SolveContext(None, (), {}, None, None, False, {}, fit.Budget(memory_bytes=2 ** 40, seconds=1.0),
                           fit.FitPlan(size_mm=3.0, requested_mm=3.0), geometry=big)
        before = analysis.estimate(ctx, inputs)
        step = analysis.apply("adaptive_steps", ctx, inputs)
        self.assertTrue(ctx.plan.adaptive_steps)
        self.assertIn("time steps grow", step.words)
        self.assertIsNone(analysis.apply("adaptive_steps", ctx, inputs))
        self.assertLess(analysis.estimate(ctx, inputs).seconds, before.seconds)

    def test_a_clamped_bar_over_a_tiny_budget_completes_by_adapting_and_says_so(self):
        from cadgen import fea

        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            step, fixed, tip = _box(directory, "bar", (40.0, 6.0, 6.0), 0)
            study = {"analysis": "creep", "material": {**CREEPING, "creep": {**CREEPING["creep"], "temperature_C": 600}},
                     "mesh": {"size_mm": 3.0}, "duration_h": 10_000, "temperature_C": 650, "steps": 8,
                     "fixtures": [{"faces": [fixed]}], "loads": [{"faces": [tip], "type": "force", "vector_N": [0, 0, -60]}],
                     "fit": {"seconds": 0.001, "allow": ["iterative", "adaptive_steps"]},
                     "view": {"checks": [{"kind": "creep_strain", "limit_percent": 1}, {"kind": "stress"},
                                         {"kind": "displacement", "limit_mm": 5}]}}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, directory / "bar.fea.glb", study=study)
            extras = _glb(result.glb)["meshes"][0]["extras"]
            sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("adaptive_steps", rungs)
        self.assertEqual(rungs[-1], "budget")  # still over a 1 ms target: it ran anyway and says what to expect
        summary = result.summary
        self.assertEqual((summary["stopped"], summary["adaptive"], summary["reached_h"], summary["duration_h"]),
                         (False, True, 10_000.0, 10_000.0))
        self.assertEqual(summary["status"], "Held for 10,000 h")
        # A clamped cantilever creeps: it keeps sagging, and its root stress relaxes as the creep spreads it.
        self.assertGreater(summary["max_displacement_mm"], summary["initial_max_displacement_mm"])
        self.assertGreater(summary["max_creep_strain_percent"], 0.0)
        self.assertGreater(summary["relaxation_percent"], 0.0)
        self.assertLess(summary["max_von_mises_MPa"], summary["initial_max_von_mises_MPa"])
        creep, stress, moved = summary["checks"]
        self.assertEqual((creep["kind"], creep["unit"], creep["limit"], creep["duration_h"]), ("creep_strain", "%", 1.0, 10_000.0))
        frames = extras["series"]["frames"]
        self.assertEqual(creep["at"], {"frame": len(frames) - 1, "value": 10_000.0, "unit": "h"})
        self.assertEqual(stress["at"]["frame"], 0)  # the largest peak is the instant the load goes on
        self.assertEqual(moved["kind"], "displacement")
        self.assertEqual(extras["analysis"]["type"], "creep")
        self.assertTrue(extras["analysis"]["limits"])
        self.assertEqual([(f["attribute"], f["field"], f.get("per_frame")) for f in extras["fields"]],
                         [("_VON_MISES", "von_mises", True), ("_DISPLACEMENT", "displacement", True),
                          ("_CREEP_STRAIN", "creep_strain", True)])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], series["default"]), ("time", "h", len(frames) - 1))
        self.assertEqual((frames[0]["label"], frames[-1]["label"]), ("0 h", "10,000 h"))
        self.assertEqual(frames[1]["attributes"],
                         {"von_mises": "_VON_MISES_F1", "displacement": "_DISPLACEMENT_F1", "creep_strain": "_CREEP_STRAIN_F1"})
        self.assertEqual((extras["study"]["duration_h"], extras["study"]["temperature_C"]), (10_000, 650))
        self.assertIn("max_von_mises_MPa", sidecar["curves"])
        self.assertTrue(any("600 °C" in warning and "650 °C" in warning for warning in [*result.warnings, *sidecar.get("warnings", [])]))
        words = next(step["words"] for step in result.fit if step["rung"] == "adaptive_steps")
        self.assertIn(words, [step["words"] for step in extras["fit"]])
        self.assertIn(words, [step["words"] for step in sidecar["fit"]])
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in result.human_lines()))
        found = [finding["type"] for finding in result.findings]
        self.assertIn("fit_adaptive_steps", found)
        self.assertIn("stress_relaxes", found)


if __name__ == "__main__":
    unittest.main()
