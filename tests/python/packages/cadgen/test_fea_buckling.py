"""Buckling: the study it takes, the Euler column, its check, findings, GLB and ladder.

The column is a build123d box written to a temporary STEP: 200 mm long,
6 x 6 mm steel, clamped at x = 0 and pushed along its axis at the free end. A
fixed-free Euler column buckles at P = π²EI/(4L²) (1332 N here), so 100 N
buckles it at 13.3 times the load; its square section buckles at that load in
Y and in Z alike, and its next shape needs nine times the load (spec section 13).

Parse tests are stdlib only; the solves need the fea extra.
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

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
from cadgen._internal.fea.analyses.buckling import NO_BUCKLING_FACTOR, _buckling_check  # noqa: E402
from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

LENGTH, SIDE, PUSH = 200.0, 6.0, 100.0
STEEL = lookup_material("steel")
EULER_N = math.pi ** 2 * STEEL.E * SIDE ** 4 / 12.0 / (4.0 * LENGTH ** 2)


def _study(**more) -> dict:
    return {"analysis": "buckling", "material": "steel", "fixtures": [{"faces": ["#o1.f1"]}],
            "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [-PUSH, 0, 0]}], **more}


class StudyFile(unittest.TestCase):
    def test_it_takes_static_fixtures_and_loads_and_three_modes(self):
        parsed = parse_study(_study())
        self.assertEqual((parsed.analysis, parsed.inputs.modes, parsed.inputs.requires_anchor), ("buckling", 3, True))
        self.assertEqual(parsed.inputs.face_refs, ("#o1.f1", "#o1.f2"))
        self.assertEqual(parsed.checks, ({"kind": "buckling", "margin": 3.0},))
        self.assertEqual(parse_study(_study(modes=5)).inputs.modes, 5)

    def test_fixtures_and_loads_are_required(self):
        with self.assertRaisesRegex(ValueError, "fixtures"):
            parse_study({"analysis": "buckling", "material": "steel", "loads": _study()["loads"]})
        with self.assertRaisesRegex(ValueError, "loads"):
            parse_study({"analysis": "buckling", "material": "steel", "fixtures": _study()["fixtures"]})

    def test_its_check_and_keys(self):
        parsed = parse_study(_study(view={"checks": [{"kind": "buckling", "margin": 5, "label": "Column"}]}))
        self.assertEqual(parsed.inputs.checks, ({"kind": "buckling", "margin": 5.0, "label": "Column"},))
        with self.assertRaisesRegex(ValueError, "below 1 means it buckles"):
            parse_study(_study(view={"checks": [{"kind": "buckling", "margin": 0.5}]}))
        with self.assertRaisesRegex(ValueError, "only one buckling check"):
            parse_study(_study(view={"checks": [{"kind": "buckling"}, {"kind": "buckling"}]}))
        with self.assertRaisesRegex(ValueError, r"unknown keys \['range_Hz'\]; buckling studies take"):
            parse_study(_study(range_Hz=[0, 10]))
        with self.assertRaisesRegex(ValueError, "from 1 to 30"):
            parse_study(_study(modes=0))

    def test_a_body_load_needs_a_density_as_in_static(self):
        parsed = parse_study(_study(loads=[{"type": "gravity", "vector_g": [-1, 0, 0]}]))
        self.assertEqual(parsed.inputs.material_needs, frozenset({"density"}))


class Check(unittest.TestCase):
    def test_the_first_load_factor_against_its_margin(self):
        passes = _buckling_check({"kind": "buckling", "margin": 3.0}, [13.3, 13.4])
        self.assertEqual((passes["status"], passes["value"], passes["limit"], passes["unit"], passes["label"]),
                         ("passes", 13.3, 3.0, "×", "Buckling"))
        self.assertAlmostEqual(passes["ratio"], 1 / 13.3, places=6)
        self.assertEqual((passes["close_at"], passes["at"]), (round(1 / 3, 6), {"frame": 0, "value": 13.3, "unit": "×"}))
        self.assertEqual(_buckling_check({"kind": "buckling", "margin": 3.0}, [2.0])["status"], "close")
        self.assertEqual(_buckling_check({"kind": "buckling"}, [0.8])["status"], "fails")

    def test_a_load_that_does_not_compress_passes(self):
        none = _buckling_check({"kind": "buckling"}, [])
        self.assertEqual((none["status"], none["value"]), ("passes", NO_BUCKLING_FACTOR))
        self.assertNotIn("at", none)

    def test_it_declares_the_spec_ladder(self):
        self.assertEqual(get_analysis("buckling").ladder, (
            "iterative", "local_refine", "defeature", "linear_elements", "idealise", "symmetry", "reduce_modes"))


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class EulerColumn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "column.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(cls.step))
        cls.fixed, cls.top = _ends(fea.faces(cls.step))
        cls.study = {"analysis": "buckling", "material": "steel", "mesh": {"size_mm": 2.0}, "fixtures": [{"faces": [cls.fixed]}],
                     "loads": [{"faces": [cls.top], "type": "force", "vector_N": [-PUSH, 0, 0]}], "modes": 3}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "column.fea.glb", study=cls.study)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_it_buckles_at_eulers_load(self):
        factors = self.result.summary["load_factors"]
        self.assertAlmostEqual(factors[0] / (EULER_N / PUSH), 1.0, delta=0.05)
        self.assertAlmostEqual(self.result.summary["critical_load_N"] / EULER_N, 1.0, delta=0.05)
        # The square section buckles alike either way; its next shape needs (3π/2)² / (π/2)² = 9 times the load.
        self.assertAlmostEqual(factors[1] / factors[0], 1.0, delta=0.01)
        self.assertAlmostEqual(factors[2] / factors[0] / 9.0, 1.0, delta=0.05)

    def test_the_prestress_is_the_static_solve_and_balances(self):
        summary = self.result.summary
        self.assertAlmostEqual(summary["applied_force_N"][0], -PUSH, delta=1e-6)
        self.assertAlmostEqual(summary["reaction_force_N"][0], PUSH, delta=1e-3)
        # P/A along the column; the clamp, holding the ends' Poisson swell, adds a little at its corners.
        self.assertTrue(0.99 <= summary["max_von_mises_MPa"] / (PUSH / SIDE ** 2) < 1.5)
        self.assertGreater(summary["yield_factor"], summary["load_factors"][0])  # it buckles long before it yields

    def test_its_check_passes_and_the_findings_say_why(self):
        check, = self.result.summary["checks"]
        self.assertEqual((check["kind"], check["status"], check["limit"], check["at"]["frame"]), ("buckling", "passes", 3.0, 0))
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["first_buckling_mode"]["summary"], f"First buckling at 13.3× this load ({self.result.summary['critical_load_N']:.4g} N in all)")
        self.assertNotIn("yields_before_buckling", found)
        self.assertEqual(self.result.human_lines()[1][:31], "buckles first at 13.3× this loa")

    def test_the_glb_carries_the_shapes_and_the_prestress(self):
        extras = _glb(self.result.glb)["meshes"][0]["extras"]
        self.assertEqual(extras["analysis"]["type"], "buckling")
        self.assertEqual([(f["attribute"], f["field"]) for f in extras["fields"]], [("_DISPLACEMENT", "mode_shape"), ("_VON_MISES", "von_mises")])
        self.assertTrue(extras["fields"][0]["per_frame"])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], len(series["frames"])), ("mode", "×", 3))
        self.assertEqual(series["frames"][0]["label"], "Mode 1 · 13.3×")
        self.assertEqual(series["frames"][1]["attributes"], {"mode_shape": "_MODE_SHAPE_F1"})
        self.assertEqual(extras["study"]["loads"][0]["vector_N"], [-PUSH, 0.0, 0.0])
        self.assertEqual(extras["study"]["modes_requested"], 3)

    def test_on_the_engine_lobpcg_tension_and_a_close_margin(self):
        from cadgen._internal.fea.analyses.base import SolveContext
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.fit import FitPlan
        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen.step_scene import read_scene

        volume = mesh_occurrence(next(iter(read_scene(self.step).leaves())), max_h=2.0)
        space = FemSpace.build(volume)
        ordinal_of = {ref: int(ref.rsplit("f", 1)[1]) for ref in (self.fixed, self.top)}
        analysis = get_analysis("buckling")

        def solve(study, solver="direct"):
            parsed = parse_study(study)
            ctx = SolveContext(volume=volume, materials=(parsed.material,), ordinal_of=ordinal_of, space=space, log=None,
                               automatic=False, upstream={}, budget=None, plan=FitPlan(solver=solver), study=parsed, part_name="column")
            return ctx, parsed, analysis.solve(ctx, parsed.inputs)

        _, _, iterative = solve({**self.study, "modes": 1}, "iterative")
        self.assertIn("lobpcg + amg", iterative.solver)
        self.assertAlmostEqual(iterative.scalars["load_factors"][0] / (EULER_N / PUSH), 1.0, delta=0.05)

        pulled = {**self.study, "loads": [{"faces": [self.top], "type": "force", "vector_N": [PUSH, 0, 0]}]}
        ctx, parsed, result = solve(pulled)
        self.assertEqual(result.scalars["load_factors"], [])
        self.assertIn("does not compress the part enough to buckle it", result.warnings[-1])
        found = analysis.findings(ctx, result, parsed.inputs, [], assembly=False)
        self.assertIn("no_buckling", [finding["type"] for finding in found])

        close = {**self.study, "view": {"checks": [{"kind": "buckling", "margin": 20, "label": "Column"}]}}
        ctx, parsed, result = solve(close)
        judged = analysis.judge(parsed.checks[0], 0, ctx, result, parsed.inputs)
        self.assertEqual((judged["status"], judged["label"]), ("close", "Column"))
        self.assertTrue(analysis.needs_finer(result, parsed.inputs, []))
        found = {finding["type"]: finding for finding in analysis.findings(ctx, result, parsed.inputs, [], assembly=False)}
        self.assertEqual(found["close_to_buckling"]["severity"], "warning")
        self.assertIn("under the 20× margin it should keep", found["close_to_buckling"]["summary"])


if __name__ == "__main__":
    unittest.main()
