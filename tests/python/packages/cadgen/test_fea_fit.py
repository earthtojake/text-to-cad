"""The fit-the-budget ladder: a model too big for its budget is never refused; it adapts, says how, and completes.

Each "oversized" model here is a small part given a tiny budget in its study
(``fit``: a few kilobytes and a millisecond), so every rung the study allows
is needed and the run costs seconds. Each case asserts the run completed, the
step names its rung in the GLB's ``extras.fit``, the sidecar's ``fit``, the CLI
lines and an info finding, and the answer still holds within a stated,
widened tolerance. The STEPs are written by build123d into temporary
directories. The ladder's own logic runs on a fake analysis, stdlib only.
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

from cadgen._internal.fea import fit  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

#: Small enough that nothing fits: every rung the study allows is taken.
TINY = {"memory_GB": 1e-6, "seconds": 1e-3}


def quiet():
    return redirect_stderr(io.StringIO())


def _extras(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])["meshes"][0]["extras"]


def _sidecar(result) -> dict:
    return json.loads(result.sidecar.read_text(encoding="utf-8"))


def _end_faces(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


def _cantilever(directory: Path, length=40.0, side=4.0) -> Path:
    from build123d import Align, Box, export_step

    path = directory / "cantilever.step"
    export_step(Box(length, side, side, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(path))
    return path


# -- the ladder itself, on a fake analysis ----------------------------------------------------------


class _Fake:
    """An analysis whose cost halves with each rung it takes; ``skip`` rungs do not apply."""

    ladder = ("iterative", "local_refine", "defeature", "symmetry")

    def __init__(self, cost: float, skip=()):
        self.cost, self.skip, self.applied = cost, set(skip), []

    def estimate(self, ctx, inputs):
        return fit.Estimate(1000, int(self.cost), self.cost / 1e6)

    def apply(self, rung, ctx, inputs):
        if rung in self.skip:
            return None
        self.applied.append(rung)
        self.cost /= 2
        return fit.Step(rung, f"took {rung}", None, None)


class _Ctx:
    def __init__(self, budget, allow=None):
        self.budget, self.plan = budget, fit.FitPlan(allow=allow)


class Ladder(unittest.TestCase):
    def test_rungs_are_taken_in_order_until_it_fits(self):
        analysis = _Fake(4e9, skip={"local_refine"})
        steps = fit.fit_budget(analysis, _Ctx(fit.Budget(1.5e9, 1e6)), None)
        self.assertEqual([s.rung for s in steps], ["iterative", "defeature"])
        self.assertEqual(analysis.applied, ["iterative", "defeature"])

    def test_a_model_that_fits_takes_nothing(self):
        self.assertEqual(fit.fit_budget(_Fake(1e6), _Ctx(fit.Budget(2e9, 600)), None), [])

    def test_when_every_rung_is_taken_it_still_runs_and_says_what_to_expect(self):
        steps = fit.fit_budget(_Fake(1e12), _Ctx(fit.Budget(1e6, 1.0)), None)
        self.assertEqual([s.rung for s in steps][:-1], list(_Fake.ladder))
        last = steps[-1]
        self.assertEqual(last.rung, fit.TAIL)
        self.assertTrue(last.words.startswith("Every way to shrink this was used; expect about "), last.words)
        self.assertIn("GB", last.words)

    def test_a_study_that_allows_no_rung_runs_as_it_is_and_says_so(self):
        analysis = _Fake(1e12)
        steps = fit.fit_budget(analysis, _Ctx(fit.Budget(1e6, 1.0), allow=()), None)
        self.assertEqual(analysis.applied, [])
        (only,) = steps
        self.assertIn("the study allows no simplification; expect about", only.words)

    def test_a_second_pass_resumes_after_the_rungs_already_offered(self):
        analysis, ctx = _Fake(1e12), _Ctx(fit.Budget(1e6, 1.0), allow=("iterative", "symmetry"))
        first = fit.fit_budget(analysis, ctx, None, tail=False)
        second = fit.fit_budget(analysis, ctx, None)
        self.assertEqual([s.rung for s in first], ["iterative", "symmetry"])
        self.assertEqual([s.rung for s in second], [fit.TAIL])

    def test_the_default_budget_is_half_the_memory_and_ten_minutes_and_the_study_overrides_it(self):
        budget = fit.default_budget()
        self.assertGreaterEqual(budget.memory_bytes, 2 * fit.GIB)
        self.assertEqual((budget.seconds, budget.max_frames), (600.0, 24))
        self.assertEqual(fit.default_budget({"memory_GB": 4, "seconds": 30}), fit.Budget(4 * fit.GIB, 30.0))

    def test_words_for_time_and_memory(self):
        self.assertEqual(fit.human_seconds(40), "40 seconds")
        self.assertEqual(fit.human_seconds(25 * 60), "25 minutes")
        self.assertEqual(fit.human_bytes(9 * fit.GIB), "9.0 GB")
        self.assertEqual(fit.human_bytes(600 * 2 ** 20), "600 MB")

    def test_a_step_is_a_dict_and_an_info_finding(self):
        step = fit.Step("defeature", "Left out 2 small holes", None, None, faces=("#o1.f9",), detail={"faces": 1})
        self.assertEqual(step.as_dict(), {"rung": "defeature", "words": "Left out 2 small holes", "accuracy": None,
                                          "accuracy_pct": None, "faces": ["#o1.f9"], "detail": {"faces": 1}})
        finding = step.finding()
        self.assertEqual((finding["severity"], finding["type"]), ("info", "fit_defeature"))

    def test_plan_counts_is_public_and_keeps_its_old_name(self):
        from types import SimpleNamespace

        self.assertIs(fit._plan_counts, fit.plan_counts)
        geometry = fit.Geometry(volume_mm3=1e5, area_mm2=1.4e4, bbox_diagonal_mm=80.0)
        ctx = SimpleNamespace(plan=fit.FitPlan(size_mm=2.0), volume=None, geometry=geometry)
        elements, nodes, two = fit.plan_counts(ctx)
        self.assertAlmostEqual(elements, fit.tets_estimate(geometry, 2.0))
        self.assertAlmostEqual(nodes, elements * fit.NODES_PER_TET[2])
        self.assertFalse(two)
        # nonlinear's estimate reads it by its public name.
        source = (Path(fit.__file__).parent / "analyses" / "nonlinear.py").read_text(encoding="utf-8")
        self.assertIn("fit.plan_counts(ctx)", source)
        self.assertNotIn("fit._plan_counts", source)

    def test_a_step_is_settled_into_a_new_step_never_changed_in_place(self):
        taken = fit.Step("reduce_modes", "Kept only the fewest modes", None, None, detail={"keep_share": 0.9})
        other = fit.Step("reduce_modes", "Solved by modal superposition", None, None, detail={"to_method": "modal"})
        steps = [fit.Step("iterative", "took iterative", None, None), other, taken]
        settled = fit.settle_step(steps, "reduce_modes", {"words": "Kept 2 of the 5 modes", "accuracy": "a little low",
                                                         "accuracy_pct": 3.0, "detail": {"kept_modes": 2}},
                                  marker="keep_share")
        self.assertEqual([s.words for s in settled], ["took iterative", "Solved by modal superposition", "Kept 2 of the 5 modes"])
        self.assertEqual((settled[2].accuracy, settled[2].accuracy_pct), ("a little low", 3.0))
        self.assertEqual(settled[2].detail, {"keep_share": 0.9, "kept_modes": 2})
        # The ladder's own step is untouched, its detail too.
        self.assertEqual((taken.words, taken.detail), ("Kept only the fewest modes", {"keep_share": 0.9}))
        self.assertIs(settled[1], other)
        self.assertEqual(fit.settle_step(steps, "reduce_modes", None), steps)

    def test_the_dynamic_analyses_settle_their_steps_through_run_and_mutate_no_frozen_step(self):
        from types import SimpleNamespace

        from cadgen._internal.fea.analyses import get_analysis

        run_source = (Path(fit.__file__).parent / "run.py").read_text(encoding="utf-8")
        self.assertIn("analysis.settle_steps(result, steps)", run_source)
        step = fit.Step("reduce_modes", "Kept only the fewest modes", None, None, detail={"keep_share": 0.9})
        for name in ("harmonic", "shock", "random_vibration", "transient"):
            with self.subTest(analysis=name):
                analysis = get_analysis(name)
                source = (Path(fit.__file__).parent / "analyses" / f"{name}.py").read_text(encoding="utf-8")
                self.assertNotIn("__setattr__", source)
                result = SimpleNamespace(scalars={"reduce_step": {"words": f"{name} kept 3", "detail": {"kept_modes": 3}}})
                (settled,) = analysis.settle_steps(result, [step])
                self.assertEqual((settled.words, settled.detail["kept_modes"]), (f"{name} kept 3", 3))
                self.assertEqual(analysis.settle_steps(SimpleNamespace(scalars={}), [step]), [step])
        self.assertEqual(step.words, "Kept only the fewest modes")

    def test_idealise_is_not_taken_for_vibration_or_buckling_and_the_skill_says_so(self):
        from types import SimpleNamespace

        from cadgen._internal.fea.analyses import get_analysis

        skill = Path(__file__).resolve().parents[4] / "skills" / "fea" / "references"
        for name, page, words in (("modal", "modal.md", "not taken for a vibration study"),
                                  ("buckling", "buckling.md", "not taken for buckling yet")):
            with self.subTest(analysis=name):
                analysis = get_analysis(name)
                self.assertIn("idealise", analysis.ladder)
                ctx = SimpleNamespace(plan=fit.FitPlan(), budget=fit.Budget(1, 1.0))
                self.assertIsNone(analysis.apply("idealise", ctx, None))
                self.assertEqual(ctx.plan.idealisation, "solid")
                text = " ".join((skill / page).read_text(encoding="utf-8").split())
                self.assertIn(f"`idealise` and `symmetry` are declared but {words}", text)

    def test_the_cost_model_grows_with_the_mesh_and_shrinks_with_each_rung(self):
        geometry = fit.Geometry(volume_mm3=1e5, area_mm2=1.4e4, bbox_diagonal_mm=80.0)
        fine, coarse = fit.tets_estimate(geometry, 1.0), fit.tets_estimate(geometry, 2.0)
        self.assertGreater(fine, 6 * coarse)
        self.assertAlmostEqual(fit.tets_estimate(geometry, 1.0, share=0.5), fine / 2)
        quadratic = fit.solve_cost(fine, fine * 1.7, order=2)
        linear = fit.solve_cost(fine, fine * 0.25, order=1)
        self.assertLess(linear.memory_bytes, quadratic.memory_bytes / 4)
        self.assertGreater(fit.solve_cost(fine, fine * 1.7, solver="matrix_free").seconds, quadratic.seconds)


# -- static, end to end ----------------------------------------------------------------------------


def _assert_said(test, result, rung: str):
    """The step is in the result, the GLB, the sidecar, the CLI and the findings."""
    test.assertTrue(result.ok)
    rungs = [step["rung"] for step in result.fit]
    test.assertIn(rung, rungs)
    step = next(step for step in result.fit if step["rung"] == rung)
    test.assertEqual(_extras(result.glb)["fit"], list(result.fit))
    test.assertEqual(_sidecar(result)["fit"], list(result.fit))
    lines = result.human_lines()
    test.assertIn(f"adapted: {step['words']}" + (f" ({step['accuracy']})" if step["accuracy"] else ""), lines)
    test.assertIn(f"fit_{rung}", [f["type"] for f in result.findings if f["severity"] == "info"])
    return step


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Cantilever(unittest.TestCase):
    """One cantilever, solved as it is and then through single rungs: iterative, linear elements, symmetry, none."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = _cantilever(cls.directory)
        cls.fixed, cls.loaded = _end_faces(fea.faces(cls.step))
        cls.base = {"material": "steel", "fixtures": [{"faces": [cls.fixed]}], "mesh": {"size_mm": 1.0},
                    "loads": [{"faces": [cls.loaded], "type": "force", "vector_N": [0, 0, -20]}]}
        with quiet():
            cls.plain = fea.solve(cls.step, cls.directory / "plain.glb", study=cls.base)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def solve(self, name: str, allow: list[str], **study):
        from cadgen import fea

        with quiet():
            return fea.solve(self.step, self.directory / f"{name}.glb",
                             study={**self.base, **study, "fit": {**TINY, "allow": allow}})

    def test_a_study_that_fits_writes_no_fit(self):
        self.assertEqual(self.plain.fit, ())
        self.assertNotIn("fit", _extras(self.plain.glb))
        self.assertNotIn("fit", _sidecar(self.plain))
        self.assertFalse(any(line.startswith("adapted:") for line in self.plain.human_lines()))

    def test_iterative_matrix_free_gives_the_same_answer(self):
        result = self.solve("iterative", ["iterative"], mesh={"size_mm": 2.0})
        step = _assert_said(self, result, "iterative")
        self.assertIn("matrix-free", step["words"])
        self.assertIn("matrix-free cg", result.mesh["solver"])
        self.assertIsNone(step["accuracy"])
        with quiet():
            from cadgen import fea

            direct = fea.solve(self.step, self.directory / "direct.glb", study={**self.base, "mesh": {"size_mm": 2.0}})
        self.assertAlmostEqual(result.summary["max_displacement_mm"] / direct.summary["max_displacement_mm"], 1.0, delta=1e-4)
        # The closing step says what to expect, since even this misses a kilobyte budget.
        self.assertEqual(result.fit[-1]["rung"], fit.TAIL)
        self.assertIn("expect about", result.fit[-1]["words"])

    def test_linear_elements_carry_their_accuracy_note(self):
        result = self.solve("linear", ["linear_elements"])
        step = _assert_said(self, result, "linear_elements")
        self.assertEqual(result.mesh["order"], 1)
        self.assertEqual(_extras(result.glb)["study"]["mesh"]["order"], 1)
        self.assertEqual(step["accuracy"], fit.LINEAR_TABLE_NOTE)
        # Linear tets are stiff in bending: the tip moves less, within the note's 30 % (widened to 40 %).
        ratio = result.summary["max_displacement_mm"] / self.plain.summary["max_displacement_mm"]
        self.assertTrue(0.6 < ratio < 1.0, ratio)

    def test_linear_elements_measure_their_accuracy_where_a_quadratic_pass_fits(self):
        from types import SimpleNamespace

        from cadgen.step_scene import read_scene

        occurrence = next(iter(read_scene(self.step).leaves()))
        shape = occurrence.shape()
        geometry = fit.geometry_of(shape.wrapped, occurrence.ref)

        def memory(size):
            ctx = SimpleNamespace(plan=fit.FitPlan(size_mm=size, requested_mm=1.0), volume=None, geometry=geometry)
            return fit.solid_estimate(ctx).memory_bytes

        # Quadratic misses at the asked 1 mm and fits at the measurement's first coarser size, 1.41 mm.
        budget_gb = 0.5 * (memory(1.0) + memory(2 ** 0.5)) / fit.GIB
        from cadgen import fea

        with quiet():
            result = fea.solve(self.step, self.directory / "measured.glb",
                               study={**self.base, "fit": {"memory_GB": budget_gb, "seconds": 600, "allow": ["linear_elements"]}})
        step = _assert_said(self, result, "linear_elements")
        self.assertTrue(step["detail"]["measured"], step)
        self.assertIn("against quadratic ones on a 1.41 mm check pass", step["accuracy"])
        self.assertGreater(step["accuracy_pct"], 0.0)

    def test_symmetry_solves_half_and_matches_the_whole(self):
        result = self.solve("half", ["symmetry"])
        step = _assert_said(self, result, "symmetry")
        self.assertIn("one half", step["words"])
        self.assertEqual([plane["axis"] for plane in step["detail"]["planes"]], ["y"])
        self.assertIsNone(step["accuracy"])
        whole, half = self.plain.summary, result.summary
        self.assertAlmostEqual(half["max_displacement_mm"] / whole["max_displacement_mm"], 1.0, delta=0.01)
        self.assertAlmostEqual(half["applied_force_N"][2], -20.0, delta=1e-6)
        self.assertAlmostEqual(half["reaction_force_N"][2], 20.0, delta=1e-3)
        self.assertAlmostEqual(half["applied_force_N"][1], 0.0, delta=1e-9)
        # The written GLB is the whole part: every face of it, both halves of the surface.
        self.assertEqual(_extras(result.glb)["faces"], _extras(self.plain.glb)["faces"])
        self.assertEqual(result.warnings, ())

    def test_a_load_across_the_plane_is_not_mirrored(self):
        result = self.solve("sideways", ["symmetry"],
                            loads=[{"faces": [self.loaded], "type": "force", "vector_N": [0, 5, -20]}])
        self.assertNotIn("symmetry", [step["rung"] for step in result.fit])

    def test_every_rung_forbidden_still_runs_and_says_its_time_and_memory(self):
        result = self.solve("as-is", [])
        self.assertTrue(result.ok)
        (only,) = result.fit
        self.assertEqual(only["rung"], fit.TAIL)
        self.assertIn("the study allows no simplification; expect about", only["words"])
        self.assertIn("seconds", only["words"])
        self.assertEqual(result.summary["max_displacement_mm"], self.plain.summary["max_displacement_mm"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class PlateWithHole(unittest.TestCase):
    """A plate with a hole in tension: two passes keep the hole fine and read Peterson's Kt within 5 %."""

    LENGTH, WIDTH, THICK, HOLE = 80.0, 20.0, 2.0, 6.0
    FORCE, FINE = 1000.0, 0.8

    @classmethod
    def setUpClass(cls):
        from build123d import Box, Cylinder, Pos, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "plate.step"
        export_step(Pos(cls.LENGTH / 2, 0, 0) * Box(cls.LENGTH, cls.WIDTH, cls.THICK)
                    - Pos(cls.LENGTH / 2, 0, 0) * Cylinder(cls.HOLE / 2, cls.THICK), str(step))
        fixed, loaded = _end_faces(fea.faces(step))
        study = {"material": "steel", "fixtures": [{"faces": [fixed]}], "mesh": {"size_mm": cls.FINE},
                 "loads": [{"faces": [loaded], "type": "force", "vector_N": [cls.FORCE, 0, 0]}],
                 "fit": {**TINY, "allow": ["local_refine"]}}
        with quiet():
            cls.result = fea.solve(step, directory / "plate.glb", study=study)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_peak_holds_peterson_within_five_percent(self):
        ratio = self.HOLE / self.WIDTH
        kt = 3.0 - 3.14 * ratio + 3.667 * ratio ** 2 - 1.527 * ratio ** 3
        nominal = self.FORCE / ((self.WIDTH - self.HOLE) * self.THICK)
        self.assertAlmostEqual(self.result.summary["max_von_mises_MPa"] / (kt * nominal), 1.0, delta=0.05)

    def test_the_words_quote_the_kept_size_and_the_pass_to_pass_change(self):
        step = _assert_said(self, self.result, "local_refine")
        self.assertIn(f"the peak is still meshed at {self.FINE:g} mm", step["words"])
        self.assertIn("peak stress moved", step["accuracy"])
        self.assertIn("between the coarse and the refined pass", step["accuracy"])
        self.assertGreater(step["detail"]["to_size_mm"], self.FINE)
        refined = _sidecar(self.result)["refined"]
        self.assertEqual(refined["size_mm"], self.FINE)
        self.assertGreater(refined["from_size_mm"], self.FINE)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Defeature(unittest.TestCase):
    """A bar with two small rimmed holes mid-span and a loaded fillet at its tip: the holes go, the fillet stays."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Axis, Box, Cylinder, GeomType, Pos, export_step, fillet

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        bar = Box(80.0, 20.0, 10.0, align=(Align.MIN, Align.CENTER, Align.CENTER))
        tip = bar.edges().filter_by(Axis.Y).group_by(Axis.X)[-1].group_by(Axis.Z)[-1]
        bar = fillet(tip, radius=2.0)
        for x in (30.0, 50.0):
            bar = bar - Pos(x, 0, 0) * Cylinder(1.0, 10.0)
        rims = bar.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1]
        bar = fillet(rims, radius=0.5)
        step = directory / "bar.step"
        export_step(bar, str(step))
        listing = fea.faces(step)
        fixed, _ = _end_faces(listing)
        cls.loaded = max((face for face in listing.faces if face.surface == "cylinder"), key=lambda face: face.center_mm[0]).ref
        base = {"material": "steel", "fixtures": [{"faces": [fixed]}], "mesh": {"size_mm": 3.0},
                "loads": [{"faces": [cls.loaded], "type": "force", "vector_N": [0, 0, -200]}]}
        with quiet():
            cls.whole = fea.solve(step, directory / "whole.glb", study=base)
            cls.result = fea.solve(step, directory / "defeatured.glb", study={**base, "fit": {**TINY, "allow": ["defeature"]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_far_features_are_left_out_and_the_loaded_fillet_stays(self):
        step = _assert_said(self, self.result, "defeature")
        self.assertEqual(step["words"], "Left out 2 small fillets and 2 small holes far from the loads and fixtures to mesh it")
        self.assertEqual(len(step["faces"]), 4)
        self.assertNotIn(self.loaded, step["faces"])
        self.assertAlmostEqual(self.result.summary["applied_force_N"][2], -200.0, delta=1e-6)

    def test_the_answer_barely_moves(self):
        ratio = self.result.summary["max_displacement_mm"] / self.whole.summary["max_displacement_mm"]
        self.assertAlmostEqual(ratio, 1.0, delta=0.03)
        self.assertLess(self.result.mesh["elements"], self.whole.mesh["elements"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class NoRefusal(unittest.TestCase):
    def test_past_the_dof_limit_the_solve_goes_ahead(self):
        from unittest import mock

        from cadgen._internal.fea import solve
        from cadgen._internal.fea.materials import lookup_material
        from cadgen._internal.fea.study import Fixture, Load
        from tests.python.packages.cadgen.test_fea_protocol import box_volume

        volume = box_volume()
        with mock.patch.object(solve, "DOF_LIMIT", 10):
            outcome = solve.solve_linear_static(volume, lookup_material("steel"), (Fixture(("#o1.f1",)),),
                                                (Load(("#o1.f2",), "force", vector=(0.0, 0.0, -1.0)),), {"#o1.f1": 1, "#o1.f2": 2})
        self.assertGreater(outcome.dofs, 10)
        self.assertTrue(math.isfinite(float(outcome.displacement.max())))


if __name__ == "__main__":
    unittest.main()
