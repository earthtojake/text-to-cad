"""Permanent bend / Stretch: the study it takes, the material models, the driver, the benchmarks, GLB and ladder.

Benchmarks (spec section 13):
- a bilinear bar: a 20 x 4 x 4 mm steel bar held on three symmetry planes and
  pulled past yield; its strain is σ/E + (σ - σy)/H exactly (1 %), by Newton
  with SuperLU and by Newton-Krylov alike;
- a cantilever's plastic collapse: 80 mm long, 3 mm wide, 6 mm deep, perfectly
  plastic steel, clamped and pushed at its tip with 1.5 times
  P = σy b h² / (4L); it is reported as collapsing at about 70 % of the load,
  that load within 7 % of P;
- a Neo-Hookean bar stretched to λ ≈ 2: nominal stress μ (λ - λ⁻²) within 2 %.

The bar benchmarks run on the engine (a structured mesh built in the test);
the cantilever and the ladder through ``cadgen.fea.solve`` on a build123d box
written to a temporary STEP. Parse tests are stdlib only; the solves need the
fea extra.
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

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
from cadgen._internal.fea.analyses.nonlinear import collapse_words, load_label  # noqa: E402
from cadgen._internal.fea.materials import material_from_spec  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

STEEL_PLASTIC = {"name": "steel", "plasticity": {"tangent_MPa": 2000}}
RUBBER = {"name": "rubber", "hyperelastic": {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}}
E, YIELD = 200_000.0, 250.0


def _study(**more) -> dict:
    return {"analysis": "nonlinear", "material": STEEL_PLASTIC, "fixtures": [{"faces": ["#o1.f1"]}],
            "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -100]}], **more}


class StudyFile(unittest.TestCase):
    def test_it_takes_static_fixtures_and_loads_ten_steps_and_a_plastic_strain_check(self):
        parsed = parse_study(_study())
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.steps, inputs.model, inputs.requires_anchor), ("nonlinear", 10, "plasticity", True))
        self.assertEqual(inputs.face_refs, ("#o1.f1", "#o1.f2"))
        self.assertEqual(parsed.checks, ({"kind": "plastic_strain", "limit_percent": 0.2},))
        self.assertEqual(parse_study(_study(steps=40)).inputs.steps, 40)
        checks = parse_study(_study(view={"checks": [{"kind": "plastic_strain", "limit_percent": 0.5},
                                                     {"kind": "displacement", "limit_mm": 2}]})).checks
        self.assertEqual([check["kind"] for check in checks], ["plastic_strain", "displacement"])

    def test_a_rubber_needs_no_e_nu_or_yield(self):
        parsed = parse_study(_study(material=RUBBER))
        self.assertEqual(parsed.inputs.model, "hyperelastic")
        self.assertIsNone(parsed.material.yield_strength)
        self.assertAlmostEqual(parsed.material.E, 9 * 300 * 0.6 / (3 * 300 + 0.6))
        self.assertEqual(material_from_spec({"name": "steel", "plasticity": {"tangent_MPa": 0}}).tangent, 0.0)

    def test_the_errors_say_what_to_add(self):
        cases = [
            (_study(material="steel"), "past the linear range"),
            (_study(steps=0), "from 1 to 200"),
            (_study(steps=2.5), "whole number"),
            (_study(material=RUBBER, view={"checks": [{"kind": "stress"}]}), "the rubber has none"),
            (_study(modes=3), r"unknown keys \['modes'\]; nonlinear studies take"),
            (_study(view={"checks": [{"kind": "plastic_strain"}]}), "limit_percent"),
            (_study(material={"name": "steel", "plasticity": {"tangent_MPa": -5}}), "0 \\(perfectly plastic\\) or more"),
        ]
        for study, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, fragment):
                parse_study(study)

    def test_there_is_no_load_control_and_the_ladder_is_the_spec_s(self):
        analysis = get_analysis("nonlinear")
        self.assertNotIn("load_scale", analysis.drives)
        self.assertIn("frame", analysis.drives)
        self.assertEqual(analysis.ladder, ("iterative", "adaptive_steps", "local_refine", "defeature", "symmetry"))
        self.assertEqual((analysis.tier, analysis.word), (3, "Permanent bend / Stretch"))
        self.assertTrue(any("isotropic hardening only" in limit for limit in analysis.limits))
        self.assertTrue(any("No rate" in limit for limit in analysis.limits))

    def test_its_words(self):
        self.assertEqual(load_label(0.6), "60 % load")
        self.assertEqual(load_label(0.703125), "70.3 % load")
        self.assertEqual(collapse_words(0.6969), "Collapses at about 70 % of the load")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class MaterialModels(unittest.TestCase):
    def test_the_tangents_are_the_derivatives_of_the_stresses(self):
        import numpy as np

        from cadgen._internal.fea.hyperelastic import NeoHookean, neo_hookean
        from cadgen._internal.fea.plasticity import J2Params, J2State, radial_return

        rng = np.random.default_rng(1)
        h = 1e-6
        F = np.eye(3)[..., None, None] + 0.3 * rng.standard_normal((3, 3, 2, 3))
        params = NeoHookean(0.6, 300.0)
        _, A, ok = neo_hookean(F, params)
        self.assertTrue(ok)
        for k in range(3):
            for m in range(3):
                dF = np.zeros_like(F)
                dF[k, m] = h
                numeric = (neo_hookean(F + dF, params, tangent=False)[0] - neo_hookean(F - dF, params, tangent=False)[0]) / (2 * h)
                np.testing.assert_allclose(numeric, A[:, :, k, m], atol=1e-5 * np.abs(A).max())

        j2 = J2Params(E / (3 * 0.4), E / 2.6, YIELD, 1000.0)
        state = J2State(0.002 * np.einsum("ij,...->ij...", np.diag([1.0, -0.5, -0.5]), np.ones((2, 3))), 0.002 * np.ones((2, 3)))
        strain = 0.004 * rng.standard_normal((3, 3, 2, 3))
        strain = 0.5 * (strain + strain.transpose(1, 0, 2, 3))
        update = radial_return(strain, state, j2)
        self.assertTrue(update.yielding.all())
        for k in range(3):
            for m in range(3):
                d = np.zeros_like(strain)
                d[k, m] += h / 2
                d[m, k] += h / 2
                numeric = (radial_return(strain + d, state, j2, tangent=False).stress
                           - radial_return(strain - d, state, j2, tangent=False).stress) / (2 * h)
                analytic = 0.5 * (update.tangent[:, :, k, m] + update.tangent[:, :, m, k])
                np.testing.assert_allclose(numeric, analytic, atol=1e-7 * np.abs(update.tangent).max())

    def test_the_element_loop_assembles_what_the_bilinear_form_does(self):
        import numpy as np
        from skfem import MeshTet, MeshTet2, asm

        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.plasticity import ElementOps, elastic_tensor, tangent_form

        space = FemSpace.from_mesh(MeshTet2.from_mesh(MeshTet.init_tensor(*[np.linspace(0, 2, 3)] * 3)))
        rng = np.random.default_rng(2)
        A = elastic_tensor(1.0, 1.0, space.basis.dx.shape) + 0.1 * rng.standard_normal((3, 3, 3, 3, *space.basis.dx.shape))
        ops = ElementOps(space.basis, chunk=7)
        reference = asm(tangent_form(), space.basis, C=A)
        self.assertLess(abs(ops.matrix(A) - reference).max(), 1e-10 * abs(reference).max())


def _bar(length=20.0, side=4.0):
    """A structured quadratic-tet bar held on its three symmetry planes (x = 0, y = 0, z = 0): uniaxial under an end pull."""
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
    free = np.setdiff1d(np.arange(basis.N), np.concatenate(held))
    end = basis.boundary(mesh.facets_satisfying(lambda x: np.isclose(x[0], length)))

    def pull(nominal_MPa):
        @LinearForm
        def form(v, w):
            return nominal_MPa * v[0]

        return asm(form, end)

    def stretch(u):
        return float(u[(space.component == 0) & np.isclose(space.locations[:, 0], length)].mean()) / length

    return space, free, pull, stretch


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Bars(unittest.TestCase):
    def test_a_bilinear_bar_pulled_past_yield_strains_exactly_as_its_two_slopes_say(self):
        from cadgen._internal.fea import nonlinear_driver
        from cadgen._internal.fea.analyses.nonlinear import _J2Problem
        from cadgen._internal.fea.plasticity import hardening_modulus, j2_params

        space, free, pull, stretch = _bar()
        steel = material_from_spec(STEEL_PLASTIC)
        stress = 350.0
        exact = stress / E + (stress - YIELD) / hardening_modulus(E, 2000.0)
        for solver in ("direct", "iterative"):
            with self.subTest(solver=solver):
                problem = _J2Problem(space, free, pull(stress), j2_params(space, [steel]))
                path = nonlinear_driver.solve_path(problem, steps=5, solver=solver)
                self.assertFalse(path.collapsed)
                self.assertAlmostEqual(stretch(path.u) / exact, 1.0, delta=0.01)
                self.assertIn("gmres + amg" if solver == "iterative" else "superlu", path.how)
                # The permanent strain is the plastic part, 0.0505.
                self.assertAlmostEqual(float(problem.history[-1][1].max()) / (exact - stress / E), 1.0, delta=0.01)
        # Under yield it is elastic, in one Newton iteration a step.
        problem = _J2Problem(space, free, pull(200.0), j2_params(space, [steel]))
        path = nonlinear_driver.solve_path(problem, steps=2)
        self.assertAlmostEqual(stretch(path.u) / (200.0 / E), 1.0, delta=1e-6)
        self.assertEqual(float(problem.history[-1][1].max()), 0.0)

    def test_a_neo_hookean_bar_stretched_to_twice_its_length(self):
        from cadgen._internal.fea import nonlinear_driver
        from cadgen._internal.fea.analyses.nonlinear import _RubberProblem
        from cadgen._internal.fea.hyperelastic import neo_hookean_params

        space, free, pull, stretch = _bar()
        rubber = material_from_spec(RUBBER)
        nominal = 1.05  # μ (λ - λ⁻²) at λ = 2
        problem = _RubberProblem(space, free, pull(nominal), neo_hookean_params(space, [rubber]))
        path = nonlinear_driver.solve_path(problem, steps=5)
        stretched = 1.0 + stretch(path.u)
        self.assertAlmostEqual(stretched, 2.0, delta=0.05)
        self.assertAlmostEqual(0.6 * (stretched - stretched ** -2) / nominal, 1.0, delta=0.02)


    def test_a_path_stuck_cutting_its_steps_stops_at_its_deadline_and_says_so(self):
        """A step that never converges is cut six times, each cut a dozen re-solves on a real mesh; past the deadline
        the driver cuts no more: the path ends there, collapsed and out of time, with a warning that says so."""
        import numpy as np
        import scipy.sparse as sparse

        from cadgen._internal.fea import nonlinear_driver

        class Stuck:
            size, free, external = 1, np.array([0]), np.array([1.0])
            locations, component = None, None

            def evaluate(self, u, *, tangent):
                return np.array([np.nan]), (sparse.csr_matrix(np.eye(1)) if tangent else None)

            def commit(self, u, factor):
                pass

        patient = nonlinear_driver.solve_path(Stuck(), steps=2, runaway=None)
        self.assertEqual((patient.collapsed, patient.out_of_time, patient.cuts), (True, False, nonlinear_driver.MAX_HALVINGS))
        hurried = nonlinear_driver.solve_path(Stuck(), steps=2, runaway=None, deadline_s=0.0)
        self.assertEqual((hurried.collapsed, hurried.out_of_time, hurried.cuts), (True, True, 0))
        self.assertTrue(any(warning.startswith("stopped cutting the load steps after") for warning in hurried.warnings))

        class Unsettling(Stuck):
            """Converges, but its forces never settle: kept, marked, at the smallest step, step after step."""

            def evaluate(self, u, *, tangent):
                return u.copy(), (sparse.csr_matrix(np.eye(1)) if tangent else None)

            def settle(self, u, factor):
                return nonlinear_driver.Settled(u, False)

            def rollback(self):
                pass

        marching = nonlinear_driver.solve_path(Unsettling(), steps=1, runaway=None)
        self.assertEqual((marching.collapsed, len(marching.unsettled)), (False, 2 ** nonlinear_driver.MAX_HALVINGS))
        stopped = nonlinear_driver.solve_path(Unsettling(), steps=1, runaway=None, deadline_s=0.0)
        self.assertEqual((stopped.collapsed, stopped.out_of_time, stopped.records), (True, True, []))


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
class CantileverCollapse(unittest.TestCase):
    """80 x 3 x 6 mm, perfectly plastic steel, pushed with 1.5 times its plastic collapse load."""

    LENGTH, WIDTH, DEPTH = 80.0, 3.0, 6.0

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step, fixed, tip = _box(directory, "cantilever", (cls.LENGTH, cls.WIDTH, cls.DEPTH), 0)
        cls.collapse_N = YIELD * cls.WIDTH * cls.DEPTH ** 2 / (4 * cls.LENGTH)
        study = {"analysis": "nonlinear", "material": {"name": "steel", "plasticity": {"tangent_MPa": 0}},
                 "mesh": {"size_mm": 2.0}, "fixtures": [{"faces": [fixed]}], "steps": 10,
                 "loads": [{"faces": [tip], "type": "force", "vector_N": [0, 0, -1.5 * cls.collapse_N]}],
                 "view": {"checks": [{"kind": "plastic_strain", "limit_percent": 0.2}, {"kind": "displacement", "limit_mm": 50}]}}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "cantilever.fea.glb", study=study)
        cls.extras = _glb(cls.result.glb)["meshes"][0]["extras"]
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_collapses_at_the_plastic_hinge_load(self):
        summary = self.result.summary
        self.assertTrue(summary["collapsed"])
        carried = summary["load_percent"] / 100 * 1.5 * self.collapse_N
        self.assertAlmostEqual(carried / self.collapse_N, 1.0, delta=0.07)
        self.assertEqual(summary["status"], collapse_words(summary["load_percent"] / 100))
        self.assertTrue(summary["status"].startswith("Collapses at about "))
        self.assertAlmostEqual(-summary["applied_force_N"][2], carried, delta=1e-3 * carried)
        self.assertAlmostEqual(summary["reaction_force_N"][2], -summary["applied_force_N"][2], delta=1e-3 * carried)

    def test_a_collapse_is_a_result_whose_checks_fail_and_whose_finding_says_so(self):
        self.assertTrue(self.result.ok)
        plastic, moved = self.result.summary["checks"]
        self.assertEqual((plastic["kind"], plastic["status"], plastic["unit"]), ("plastic_strain", "fails", "%"))
        self.assertEqual(moved["status"], "fails")  # under its limit, but the part does not carry the load
        self.assertEqual(moved["collapsed_at_percent"], round(self.result.summary["load_percent"], 4))
        frames = len(self.extras["series"]["frames"])
        self.assertEqual(plastic["at"], {"frame": frames - 1, "value": self.extras["series"]["frames"][-1]["value"], "unit": "%"})
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["collapses"]["severity"], "error")
        self.assertIn("collapses at about", found["collapses"]["summary"])
        self.assertTrue(self.result.human_lines()[1].startswith("collapses at about"))

    def test_the_glb_carries_the_load_steps_as_frames(self):
        extras = self.extras
        self.assertEqual(extras["analysis"]["type"], "nonlinear")
        self.assertEqual(extras["analysis"]["tier"], 3)
        self.assertTrue(extras["analysis"]["limits"])
        self.assertEqual(extras["analysis"]["warnings"], [self.result.summary["status"]])
        self.assertEqual([(f["attribute"], f["field"], f.get("per_frame")) for f in extras["fields"]],
                         [("_VON_MISES", "von_mises", True), ("_DISPLACEMENT", "displacement", True),
                          ("_PLASTIC_STRAIN", "plastic_strain", True)])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], series["default"]), ("time", "%", len(series["frames"]) - 1))
        self.assertEqual(series["frames"][0]["label"], "10 % load")
        self.assertEqual(series["frames"][1]["attributes"],
                         {"von_mises": "_VON_MISES_F1", "displacement": "_DISPLACEMENT_F1", "plastic_strain": "_PLASTIC_STRAIN_F1"})
        values = [frame["value"] for frame in series["frames"]]
        self.assertEqual(values, sorted(values))
        self.assertLessEqual(extras["fields"][0]["max"], YIELD + 1e-6)  # perfectly plastic: never past yield
        self.assertEqual((extras["study"]["steps"], extras["study"]["material_model"]), (10, "plasticity"))
        self.assertIn("max_displacement_mm", self.sidecar["curves"])
        self.assertTrue(self.sidecar["limits"])

    def test_no_check_quotes_a_load_multiple(self):
        """Not linear in the load: every check says it holds at this load only (scaling none), in the summary and the
        GLB the viewer reads, so the verdict's takeaway is the worst check's own sentence, never "OK up to 18× this load"."""
        checks = self.result.summary["checks"]
        self.assertTrue(checks)
        self.assertEqual({check.get("scaling") for check in checks}, {"none"})
        self.assertEqual({check.get("scaling") for check in self.extras["checks"]}, {"none"})


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    def test_newton_krylov_is_taken_when_it_saves_and_adaptive_steps_cut_the_estimate(self):
        from cadgen._internal.fea import fit
        from cadgen._internal.fea.analyses.base import SolveContext

        analysis = get_analysis("nonlinear")
        inputs = analysis.parse(_study())
        big = fit.Geometry(volume_mm3=2e6, area_mm2=1e5, bbox_diagonal_mm=300.0)
        ctx = SolveContext(None, (), {}, None, None, False, {}, fit.Budget(memory_bytes=2 ** 40, seconds=1.0),
                           fit.FitPlan(size_mm=3.0, requested_mm=3.0), geometry=big)
        step = analysis.apply("iterative", ctx, inputs)
        self.assertEqual((step.rung, ctx.plan.solver), ("iterative", "iterative"))
        self.assertIn("Newton-Krylov", step.words)
        self.assertIsNone(analysis.apply("iterative", ctx, inputs))
        before = analysis.estimate(ctx, inputs)
        step = analysis.apply("adaptive_steps", ctx, inputs)
        self.assertTrue(ctx.plan.adaptive_steps)
        self.assertIn("load steps grow", step.words)
        self.assertIsNotNone(step.accuracy)  # plastic strain follows the path more coarsely
        self.assertLess(analysis.estimate(ctx, inputs).seconds, before.seconds)

    def test_a_rubber_block_over_a_tiny_budget_completes_by_adapting_and_says_so(self):
        from cadgen import fea

        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            step, bottom, top = _box(directory, "pad", (10.0, 10.0, 20.0), 2)
            study = {"analysis": "nonlinear", "material": RUBBER, "mesh": {"size_mm": 5.0}, "steps": 4,
                     "fixtures": [{"faces": [bottom]}], "loads": [{"faces": [top], "type": "force", "vector_N": [0, 0, 30]}],
                     "fit": {"seconds": 0.001, "allow": ["iterative", "adaptive_steps"]}}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, directory / "pad.fea.glb", study=study)
            extras = _glb(result.glb)["meshes"][0]["extras"]
            sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("adaptive_steps", rungs)
        self.assertEqual(rungs[-1], "budget")  # still over a 1 ms target: it ran anyway and says what to expect
        summary = result.summary
        self.assertEqual((summary["collapsed"], summary["material_model"], summary["adaptive"]), (False, "hyperelastic", True))
        self.assertEqual(summary["load_percent"], 100.0)
        self.assertGreater(summary["max_displacement_mm"], 1.0)  # 0.3 MPa on a 0.6 MPa rubber: a large stretch
        self.assertNotIn("max_plastic_strain_percent", summary)
        check, = summary["checks"]
        self.assertEqual((check["kind"], check["value"], check["status"]), ("plastic_strain", 0.0, "passes"))
        self.assertEqual([f["field"] for f in extras["fields"]], ["von_mises", "displacement"])
        words = next(step["words"] for step in result.fit if step["rung"] == "adaptive_steps")
        self.assertIn(words, [step["words"] for step in extras["fit"]])
        self.assertIn(words, [step["words"] for step in sidecar["fit"]])
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in result.human_lines()))
        self.assertIn("fit_adaptive_steps", [finding["type"] for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
