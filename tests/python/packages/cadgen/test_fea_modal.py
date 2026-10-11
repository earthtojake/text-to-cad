"""Vibration (``modal``): the study it takes, the frequencies against beam theory, its checks, GLB and ladder.

The beam is a build123d box written to a temporary STEP: 100 mm long, 6 x 6 mm
steel. Clamped at x = 0 it is a cantilever, whose first bending frequency is
f1 = (1.875²/2π)·sqrt(EI/ρAL⁴); a square section bends at that frequency in Y
and in Z alike, and its second bending mode sits 6.27 times higher. Held by
nothing it is free in space: six rigid-body modes come out at 0 Hz and are
dropped, and it first bends at (4.730²/2π)·sqrt(EI/ρAL⁴). Shear and rotary
inertia (a 3D solid, L/h = 17) put the solid a little under Euler-Bernoulli,
well inside the tolerances (spec section 13).

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
from cadgen._internal.fea.analyses.modal import _frequency_check  # noqa: E402
from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

LENGTH, SIDE = 100.0, 6.0
STEEL = lookup_material("steel")


def _beam_hz(root: float) -> float:
    inertia, area = SIDE ** 4 / 12.0, SIDE * SIDE
    return root ** 2 / (2 * math.pi) * math.sqrt(STEEL.E * inertia / (STEEL.density * area * LENGTH ** 4))


CANTILEVER_F1 = _beam_hz(1.875104)
FREE_FREE_F1 = _beam_hz(4.730041)
SECOND_OVER_FIRST = (4.694091 / 1.875104) ** 2  # 6.267


def _study(**more) -> dict:
    return {"analysis": "modal", "material": "steel", **more}


class StudyFile(unittest.TestCase):
    def test_fixtures_are_optional_and_modes_default_to_six(self):
        parsed = parse_study(_study())
        self.assertEqual(parsed.analysis, "modal")
        self.assertEqual((parsed.inputs.fixtures, parsed.inputs.modes, parsed.inputs.range_Hz), ((), 6, None))
        self.assertFalse(parsed.inputs.requires_anchor)
        self.assertEqual(parsed.checks, ())
        held = parse_study(_study(fixtures=[{"faces": ["#o1.f1"]}], modes=3, range_Hz=[100, 2000]))
        self.assertEqual((held.inputs.anchor_refs, held.inputs.modes, held.inputs.range_Hz), (("#o1.f1",), 3, (100.0, 2000.0)))

    def test_modes_and_range_are_checked_in_plain_words(self):
        for bad, words in (({"modes": 0}, "from 1 to 30"), ({"modes": 31}, "from 1 to 30"), ({"modes": 2.5}, "whole number"),
                           ({"range_Hz": [200, 100]}, "below high"), ({"range_Hz": [-1, 100]}, "0 or more"),
                           ({"range_Hz": 100}, "[low, high]")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study(_study(**bad))

    def test_it_takes_its_own_keys_and_checks_only(self):
        with self.assertRaisesRegex(ValueError, r"unknown keys \['loads'\]; modal studies take"):
            parse_study(_study(loads=[{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -1]}]))
        with self.assertRaisesRegex(ValueError, "not a check this cadgen makes"):
            parse_study(_study(view={"checks": [{"kind": "stress"}]}))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            parse_study(_study(view={"checks": [{"kind": "frequency", "min_Hz": 60, "avoid_Hz": [1, 2]}]}))
        with self.assertRaisesRegex(ValueError, "at most mode 30"):
            parse_study(_study(view={"checks": [{"kind": "frequency", "min_Hz": 60, "mode": 31}]}))

    def test_a_check_on_a_higher_mode_is_found_whatever_modes_says(self):
        parsed = parse_study(_study(modes=2, view={"checks": [{"kind": "frequency", "min_Hz": 60, "mode": 4},
                                                            {"kind": "frequency", "avoid_Hz": [110, 130]}]}))
        self.assertEqual((parsed.inputs.check_modes, parsed.inputs.band_top_Hz), (4, 130.0))

    def test_it_needs_a_density(self):
        with self.assertRaisesRegex(ValueError, "density_t_per_mm3"):
            parse_study(_study(material={"name": "mystery", "E_MPa": 1000, "nu": 0.3, "yield_MPa": 10, "density_t_per_mm3": 0}))

    def test_its_mode_picker_and_deformation_are_what_a_preset_may_set(self):
        parsed = parse_study(_study(view={"presets": [{"label": "Second", "mode": 2, "deformation": 40}]}))
        self.assertEqual(parsed.view["presets"], [{"label": "Second", "mode": 2, "deformation": 40.0}])
        with self.assertRaisesRegex(ValueError, "load_scale"):
            parse_study(_study(view={"controls": [{"drives": "load_scale", "max": 2}]}))


class FrequencyChecks(unittest.TestCase):
    """A frequency check judged on the modes' frequencies: the spec's status rules, and the words the viewer reads."""

    def test_a_mode_must_stay_above_its_minimum(self):
        passes = _frequency_check({"kind": "frequency", "min_Hz": 60}, [85.0, 118.0])
        self.assertEqual((passes["status"], passes["value"], passes["limit"], passes["mode"]), ("passes", 85.0, 60, 1))
        self.assertAlmostEqual(passes["ratio"], 60 / 85, places=6)
        self.assertEqual(passes["at"], {"frame": 0, "value": 85.0, "unit": "Hz"})
        self.assertEqual(_frequency_check({"kind": "frequency", "min_Hz": 80}, [85.0])["status"], "close")
        second = _frequency_check({"kind": "frequency", "min_Hz": 120, "mode": 2, "label": "Second"}, [85.0, 118.0])
        self.assertEqual((second["status"], second["label"], second["at"]["frame"]), ("fails", "Second", 1))

    def test_no_mode_may_sit_in_a_band(self):
        inside = _frequency_check({"kind": "frequency", "avoid_Hz": [110, 130]}, [85.0, 118.0, 300.0])
        self.assertEqual((inside["status"], inside["mode"], inside["value"], inside["limit"]), ("fails", 2, 118.0, 110))
        self.assertGreater(inside["ratio"], 1)
        self.assertEqual(inside["avoid_Hz"], [110, 130])
        near = _frequency_check({"kind": "frequency", "avoid_Hz": [110, 130]}, [85.0, 135.0])
        self.assertEqual((near["status"], near["mode"], near["limit"]), ("close", 2, 130))
        below = _frequency_check({"kind": "frequency", "avoid_Hz": [110, 130]}, [50.0, 400.0])
        self.assertEqual((below["status"], below["mode"], below["limit"]), ("passes", 1, 110))
        self.assertAlmostEqual(below["ratio"], 1 - 60 / 110, places=6)
        clear = _frequency_check({"kind": "frequency", "avoid_Hz": [110, 130]}, [400.0, 900.0])
        self.assertEqual((clear["status"], clear["ratio"]), ("passes", 0.0))
        self.assertEqual(clear["label"], "Vibration")


class Ladder(unittest.TestCase):
    def test_it_declares_the_spec_ladder(self):
        self.assertEqual(get_analysis("modal").ladder, (
            "iterative", "local_refine", "defeature", "linear_elements", "idealise", "symmetry", "reduce_modes"))

    def test_reduce_modes_halves_but_keeps_the_modes_checks_name(self):
        from types import SimpleNamespace

        from cadgen._internal.fea.fit import FitPlan

        analysis = get_analysis("modal")
        inputs = parse_study(_study(modes=8, view={"checks": [{"kind": "frequency", "min_Hz": 60, "mode": 3}]})).inputs
        ctx = SimpleNamespace(plan=FitPlan(), budget=None)
        step = analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual((ctx.plan.modes, step.rung, step.detail), (4, "reduce_modes", {"from_modes": 8, "to_modes": 4}))
        self.assertIn("every mode a check names is kept", step.words)
        analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual(ctx.plan.modes, 3)
        self.assertIsNone(analysis.apply("reduce_modes", ctx, inputs))
        for rung in ("idealise", "symmetry"):
            self.assertIsNone(analysis.apply(rung, ctx, inputs))


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Cantilever(unittest.TestCase):
    """The clamped beam solved end to end: frequencies, effective mass, checks, the GLB and the sidecar."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(cls.step))
        cls.fixed, cls.tip = _ends(fea.faces(cls.step))
        study = _study(fixtures=[{"faces": [cls.fixed]}], mesh={"size_mm": 2.0}, view={"checks": [
            {"kind": "frequency", "min_Hz": 600, "label": "First mode"},
            {"kind": "frequency", "avoid_Hz": [2900, 3100], "label": "Motor speed"}]})
        cls.study = study
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "beam.fea.glb", study=study)
        cls.frequencies = [mode["frequency_Hz"] for mode in cls.result.summary["modes"]]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_first_mode_is_beam_theorys(self):
        self.assertAlmostEqual(self.frequencies[0] / CANTILEVER_F1, 1.0, delta=0.03)

    def test_a_square_section_bends_alike_in_y_and_z(self):
        self.assertAlmostEqual(self.frequencies[1] / self.frequencies[0], 1.0, delta=0.01)
        # Lined up with the axes: each of the pair moves its share of the mass along one axis only.
        shares = [mode["effective_mass_fraction"] for mode in self.result.summary["modes"][:2]]
        self.assertEqual(sorted(max(range(3), key=lambda c: share[c]) for share in shares), [1, 2])
        for share in shares:
            self.assertAlmostEqual(max(share), 0.613, delta=0.03)  # a cantilever's first mode carries 61 %

    def test_a_second_run_writes_the_same_file(self):
        # The square section's two equal modes could turn between runs if the eigen solve started at random.
        from cadgen import fea

        again = self.directory / "again.fea.glb"
        with redirect_stderr(io.StringIO()):
            fea.solve(self.step, again, study=self.study)
        self.assertEqual(again.read_bytes(), (self.directory / "beam.fea.glb").read_bytes())

    def test_the_second_bending_mode_is_six_point_two_seven_times_the_first(self):
        self.assertAlmostEqual((self.frequencies[2] / self.frequencies[0]) / SECOND_OVER_FIRST, 1.0, delta=0.03)

    def test_the_summary_says_the_modes_and_the_mass(self):
        summary = self.result.summary
        self.assertEqual((len(summary["modes"]), summary["modes_requested"], summary["rigid_body_modes"]), (6, 6, 0))
        self.assertAlmostEqual(summary["total_mass_kg"], STEEL.density * LENGTH * SIDE * SIDE * 1000.0, delta=1e-6)
        self.assertEqual(summary["first_frequency_Hz"], self.frequencies[0])

    def test_the_checks_say_in_plain_words_which_mode_and_why(self):
        first, band = self.result.summary["checks"]
        self.assertEqual((first["status"], first["mode"], first["label"], first["at"]["frame"]), ("fails", 1, "First mode", 0))
        self.assertEqual((band["status"], band["mode"], band["avoid_Hz"], band["at"]["frame"]), ("fails", 3, [2900, 3100], 2))
        self.assertIsNotNone(band["where"]["ref"])
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["frequency_too_low"]["severity"], "error")
        self.assertIn("first mode is 490 Hz, under the 600 Hz it must stay above (First mode)", found["frequency_too_low"]["summary"])
        self.assertIn("Mode 3 rings at 3018 Hz, inside the 2900–3100 Hz band", found["resonates_in_band"]["summary"])
        self.assertEqual(found["first_mode"]["severity"], "info")

    def test_the_glb_carries_every_mode_shape_as_a_series(self):
        gltf, _ = _glb(self.result.glb)
        extras = gltf["meshes"][0]["extras"]
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(extras["analysis"]["type"], "modal")
        self.assertEqual(extras["fields"], [{"attribute": "_DISPLACEMENT", "name": "mode shape", "units": "mm", "min": 0.0, "max": 1.0,
                                             "attribute_scale": 1000.0, "field": "mode_shape", "per_frame": True}])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], series["default"], len(series["frames"])), ("mode", "Hz", 0, 6))
        self.assertEqual(series["frames"][0], {"value": 1.0, "label": "Mode 1 · 490 Hz", "attributes": {"mode_shape": "_DISPLACEMENT"}})
        self.assertEqual(series["frames"][2]["attributes"], {"mode_shape": "_MODE_SHAPE_F2"})
        for frame in series["frames"][1:]:
            self.assertEqual(gltf["accessors"][attributes[frame["attributes"]["mode_shape"]]]["type"], "VEC3")
        self.assertEqual(extras["study"]["modes_requested"], 6)
        self.assertEqual(extras["study"]["fixtures"][0]["type"], "fixed")

    def test_the_sidecar_and_the_cli_lines(self):
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual((sidecar["analysis"], sidecar["series"]["kind"]), ("modal", "mode"))
        lines = self.result.human_lines()
        self.assertIn("(modal)", lines[0])
        self.assertTrue(lines[1].startswith("first mode 490 Hz; modes 490 Hz, 490 Hz, 3018 Hz"))

    def test_an_oversized_model_completes_by_finding_fewer_modes(self):
        from cadgen import fea

        study = _study(fixtures=[{"faces": [self.fixed]}], mesh={"size_mm": 2.0},
                       fit={"memory_GB": 0.01, "allow": ["iterative", "reduce_modes"]})
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "tight.fea.glb", study=study)
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("reduce_modes", rungs)
        self.assertEqual((len(result.summary["modes"]), result.summary["modes_requested"]), (3, 6))
        self.assertAlmostEqual(result.summary["modes"][0]["frequency_Hz"] / CANTILEVER_F1, 1.0, delta=0.03)
        words = "Found the first 3 of the 6 modes asked for, to fit"
        gltf, _ = _glb(result.glb)
        self.assertIn(words, [step["words"] for step in gltf["meshes"][0]["extras"]["fit"]])
        self.assertIn(words, [step["words"] for step in json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"]])
        self.assertIn(f"adapted: {words}", result.human_lines())
        self.assertIn("fit_reduce_modes", [finding["type"] for finding in result.findings])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class OnTheEngine(unittest.TestCase):
    """The beam meshed once and solved through the analysis itself: free in space, LOBPCG, a window.

    These build the analysis's context as run.py does, to reach the engine's own paths
    directly (a free-free study also solves end to end through ``fea.solve``: test_fea_protocol).
    """

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.mesh import mesh_occurrence
        from cadgen.step_scene import read_scene

        cls._tmp = tempfile.TemporaryDirectory()
        step = Path(cls._tmp.name) / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(step))
        cls.fixed, _ = _ends(fea.faces(step))
        cls.volume = mesh_occurrence(next(iter(read_scene(step).leaves())), max_h=2.0)
        cls.space = FemSpace.build(cls.volume)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _solve(self, study: dict, solver: str = "direct", modes: int | None = None):
        from cadgen._internal.fea.analyses.base import SolveContext
        from cadgen._internal.fea.fit import FitPlan

        parsed = parse_study(study)
        ctx = SolveContext(
            volume=self.volume, materials=(parsed.material,), ordinal_of={self.fixed: int(self.fixed.rsplit("f", 1)[1])},
            space=self.space, log=None, automatic=False, upstream={}, budget=None, plan=FitPlan(solver=solver, modes=modes),
            study=parsed,
        )
        return get_analysis("modal").solve(ctx, parsed.inputs)

    def test_free_in_space_six_rigid_body_modes_are_dropped(self):
        for solver in ("direct", "iterative"):
            with self.subTest(solver=solver):
                result = self._solve(_study(modes=4), solver)
                frequencies = result.scalars["frequencies_Hz"]
                self.assertEqual(result.scalars["rigid_body_modes"], 6)
                self.assertEqual(len(frequencies), 4)
                self.assertAlmostEqual(frequencies[0] / FREE_FREE_F1, 1.0, delta=0.03)
                self.assertAlmostEqual(frequencies[1] / frequencies[0], 1.0, delta=0.01)
                # Nothing holds it, so no elastic mode moves its mass as a whole.
                self.assertLess(max(max(share) for share in result.scalars["effective_mass_fractions"]), 1e-3)
                self.assertEqual(result.solver.split()[0], "lobpcg" if solver == "iterative" else "arpack")

    def test_lobpcg_finds_the_cantilevers_first_mode(self):
        result = self._solve(_study(fixtures=[{"faces": [self.fixed]}], modes=3), "iterative")
        self.assertTrue(result.solver.startswith("lobpcg + amg"))
        self.assertAlmostEqual(result.scalars["frequencies_Hz"][0] / CANTILEVER_F1, 1.0, delta=0.03)
        self.assertEqual(result.warnings, [])

    def test_a_window_finds_the_modes_inside_it(self):
        result = self._solve(_study(fixtures=[{"faces": [self.fixed]}], modes=2, range_Hz=[1000, 5000]))
        frequencies = result.scalars["frequencies_Hz"]
        self.assertEqual(len(frequencies), 2)
        self.assertTrue(all(1000 <= f <= 5000 for f in frequencies))
        self.assertAlmostEqual(frequencies[0] / (CANTILEVER_F1 * SECOND_OVER_FIRST), 1.0, delta=0.03)
        self.assertEqual(result.series.frames[0].label, f"Mode 1 · {frequencies[0]:.0f} Hz")


if __name__ == "__main__":
    unittest.main()
