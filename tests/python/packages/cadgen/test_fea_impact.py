"""Drop impact (``impact``): the study it takes, the explicit engine, and a bar dropped end-on against theory.

A bar dropped end-on onto a rigid floor at v = √(2 g h) sends a compression
wave up its length; the wave reflects from the free end as tension and, when it
is back at the floor, the bar leaves it: the contact lasts 2 L / c, c = √(E/ρ),
and the stress behind the wave is ρ c v, so the floor pushes with ρ c v A and
the bar's rigid-body deceleration is c v / L (spec section 13: 5 % and 10 %).
The bar is steel, 10 x 10 x 100 mm, written by build123d to a temporary STEP,
with Poisson's ratio set to 0 so the 3D bar is the 1D bar the theory describes
(with Poisson's ratio the bar's lateral inertia makes it ring above ρ c v, the
Pochhammer-Chree oscillations, real but not in the 1D theory).

The ladder test drops a bar with a small fillet round its top end, whose small
elements set a short stable step, with a tiny time target: the run completes by
stopping after the first impact (window), stepping the small elements more often
(subcycling) and adding mass to them (mass_scaling, at most 5 %), each said in
plain words, and the benchmark still holds within 15 %.

Parse tests need no mesh; the solves need the fea extra.
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
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

G0 = 9806.65
LENGTH, SIDE, HEIGHT = 100.0, 10.0, 1000.0
E, RHO = 200_000.0, 7.85e-9
BAR_C = math.sqrt(E / RHO)                       # mm/s
SPEED = math.sqrt(2 * G0 * HEIGHT)                # mm/s
CONTACT_S = 2 * LENGTH / BAR_C                    # 39.6 µs
STRESS_MPA = RHO * BAR_C * SPEED                  # 175 MPa
PEAK_G = BAR_C * SPEED / LENGTH / G0              # 22,800 g
STEEL_1D = {"name": "steel", "nu": 0.0}
LIMITS = "Rigid floor; linear tets; elastic unless plasticity is given."


def _study(**more) -> dict:
    return {"analysis": "impact", "material": "steel", "drop": {"height_mm": HEIGHT, "direction": [0, 0, -1], "floor": "rigid"},
            **more}


def _glb(path: Path, names: tuple[str, ...] = ()) -> tuple[dict, dict]:
    """A result GLB's mesh extras and the named float attributes, as lists of rows."""
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    binary = raw[20 + length + 8:]
    primitive = gltf["meshes"][0]["primitives"][0]
    out = {}
    for name in names:
        accessor = gltf["accessors"][primitive["attributes"][name]]
        view = gltf["bufferViews"][accessor["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3}[accessor["type"]]
        values = struct.unpack_from(f"<{accessor['count'] * width}f", binary, view["byteOffset"])
        out[name] = [values[i:i + width] for i in range(0, len(values), width)]
    out["_names"] = sorted(primitive["attributes"])
    return gltf["meshes"][0]["extras"], out


def _mid_peak(path: Path) -> float:
    """The peak von Mises over the run in the middle 60 % of the bar (glTF is y-up, in metres): away from the ends."""
    _, attributes = _glb(path, ("POSITION", "_VON_MISES_PEAK"))
    return max(value[0] for position, value in zip(attributes["POSITION"], attributes["_VON_MISES_PEAK"])
               if 0.02 < position[1] < 0.08)


def _bar(directory: Path, name: str, fillet_mm: float = 0.0) -> Path:
    from build123d import Align, Axis, Box, export_step, fillet

    shape = Box(SIDE, SIDE, LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    if fillet_mm:
        shape = fillet(shape.edges().group_by(Axis.Z)[-1], fillet_mm)
    step = directory / f"{name}.step"
    export_step(shape, str(step))
    return step


class StudyFile(unittest.TestCase):
    def test_a_drop_onto_a_rigid_floor_with_its_defaults(self):
        parsed = parse_study({"analysis": "impact", "material": "abs", "drop": {"height_mm": 500}})
        inputs = parsed.inputs
        self.assertEqual(parsed.analysis, "impact")
        self.assertEqual((inputs.height_mm, inputs.direction, inputs.friction, inputs.window_s, inputs.plastic),
                         (500.0, (0.0, 0.0, -1.0), 0.0, None, False))
        self.assertEqual((inputs.face_refs, inputs.anchor_refs, inputs.requires_anchor), ((), (), False))
        self.assertEqual(parsed.mesh_order, 1)
        self.assertEqual(parsed.checks, ({"kind": "stress"},))
        self.assertAlmostEqual(inputs.speed_mm_s, math.sqrt(2 * G0 * 500))

    def test_the_spec_example_reads_whole(self):
        parsed = parse_study({
            "analysis": "impact", "material": "abs",
            "drop": {"height_mm": 1000, "direction": [0, 0, -2], "floor": "rigid", "friction": 0.3},
            "window_ms": 0.5, "plasticity": {"tangent_MPa": 200}, "mesh": {"size_mm": 3, "order": 1},
            "view": {"checks": [{"kind": "stress"}, {"kind": "acceleration", "limit_g": 2000},
                                {"kind": "plastic_strain", "limit_percent": 1}]}})
        inputs = parsed.inputs
        self.assertEqual((inputs.direction, inputs.friction, inputs.window_s, inputs.tangent_MPa, inputs.plastic),
                         ((0.0, 0.0, -1.0), 0.3, 0.0005, 200.0, True))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "acceleration", "plastic_strain"])
        self.assertEqual(inputs.material_needs, frozenset({"yield_strength"}))

    def test_what_is_wrong_is_said_in_plain_words(self):
        for bad, words in (
            ({"drop": None}, "expected an object like"),
            ({"drop": {}}, "how far it falls"),
            ({"drop": {"height_mm": 1000, "onto": ["#o1.f1"]}}, "unknown keys \\['onto'\\]"),
            ({"drop": {"height_mm": 1000, "floor": "carpet"}}, "only a rigid floor is modelled"),
            ({"drop": {"height_mm": 1000, "friction": -1}}, "0 or more"),
            ({"drop": {"height_mm": 1000, "direction": [0, 0, 0]}}, "the direction is zero"),
            ({"window_ms": -1}, "must be > 0"),
            ({"plasticity": {"tangent": 1}}, "plasticity takes"),
            ({"mesh": {"order": 2}}, "impact studies take order 1"),
            ({"view": {"checks": [{"kind": "plastic_strain", "limit_percent": 1}]}}, "needs plasticity"),
            ({"view": {"checks": [{"kind": "frequency", "min_Hz": 60}]}}, "not a check this cadgen makes"),
            ({"fixtures": [{"faces": ["#o1.f1"]}]}, "impact studies take"),
        ):
            study = {key: value for key, value in {**_study(), **bad}.items() if value is not None}
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study(study)

    def test_the_contact_time_estimate_and_the_words(self):
        from cadgen._internal.fea.analyses.impact import contact_time_estimate, time_words

        self.assertAlmostEqual(contact_time_estimate(LENGTH, E, RHO), CONTACT_S)
        self.assertEqual([time_words(t) for t in (0, 3.96e-5, 1.2e-3, 1.5)], ["0 s", "39.6 µs", "1.2 ms", "1.5 s"])
        analysis = get_analysis("impact")
        self.assertEqual((analysis.tier, analysis.word, analysis.limits, analysis.mesh_orders), (3, "Drop impact", (LIMITS,), (1,)))
        self.assertEqual(analysis.ladder, ("iterative", "window", "subcycling", "mass_scaling", "local_refine", "defeature"))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Engine(unittest.TestCase):
    """The explicit engine's pieces on hand-built tets."""

    def _cube(self):
        import numpy as np

        from cadgen._internal.fea import explicit

        # A unit cube split into six tets around its diagonal, then scaled 10 mm.
        corners = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], dtype=float) * 10.0
        tets = np.array([[0, 1, 3, 7], [0, 1, 5, 7], [0, 2, 3, 7], [0, 2, 6, 7], [0, 4, 5, 7], [0, 4, 6, 7]])
        faces = [[0, 1, 3], [0, 3, 2], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                 [0, 2, 6], [0, 6, 4], [1, 3, 7], [1, 7, 5]]
        return explicit.build_model(corners, tets, np.array(faces), youngs=E, poisson=0.3, density=RHO)

    def test_lumped_mass_volumes_and_the_stable_step(self):
        import numpy as np

        model = self._cube()
        self.assertAlmostEqual(float(model.volume.sum()), 1000.0, places=9)
        self.assertAlmostEqual(float(model.node_mass().sum()), RHO * 1000.0, places=18)
        self.assertAlmostEqual(float(model.node_area.sum()), 600.0, places=9)
        # Each element's step is no longer than a wave crossing its shortest altitude, and of that order.
        c_d = math.sqrt(E * 0.7 / (1.3 * 0.4) / RHO)
        self.assertTrue(np.all(model.element_dt < 10.0 / c_d))
        self.assertTrue(np.all(model.element_dt > 0.1 * 10.0 / c_d))

    def test_mass_scaling_is_capped_and_subcycling_needs_a_saving(self):
        import numpy as np

        from cadgen._internal.fea import explicit

        model = self._cube()
        reached, share = explicit.max_mass_scaling(model, 0.05)
        self.assertLessEqual(share, 0.05 + 1e-12)
        self.assertGreater(reached, model.element_dt.min())
        added, again = explicit.mass_scaling(model, reached)
        self.assertAlmostEqual(again, share)
        self.assertTrue(np.all(added >= 0))
        # Six alike tets have no small region: nothing to subcycle.
        self.assertEqual(explicit.best_subcycle(model.element_dt, model.tets, model.count), (1, 1.0))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class BarDroppedEndOn(unittest.TestCase):
    """A 100 mm steel bar dropped 1 m end-on: contact 2 L / c, stress ρ c v, deceleration c v / L."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = _bar(cls.directory, "bar")
        study = _study(material=STEEL_1D, mesh={"size_mm": 3.0},
                       view={"checks": [{"kind": "stress"}, {"kind": "acceleration", "limit_g": 30000}]})
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "bar.fea.glb", study=study)
        cls.extras, cls.attributes = _glb(cls.result.glb)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_contact_time_peak_stress_and_g_match_the_wave_theory(self):
        summary = self.result.summary
        self.assertAlmostEqual(summary["contact_ms"] / (CONTACT_S * 1e3), 1.0, delta=0.05)
        self.assertAlmostEqual(summary["max_von_mises_MPa"] / STRESS_MPA, 1.0, delta=0.10)
        self.assertAlmostEqual(summary["peak_force_N"] / (STRESS_MPA * SIDE * SIDE), 1.0, delta=0.10)
        self.assertAlmostEqual(summary["peak_g"] / PEAK_G, 1.0, delta=0.10)
        # The window is three contact-time estimates, the estimate 2 L / c; the bar leaves the floor nearly as fast as it hit.
        self.assertAlmostEqual(summary["contact_time_estimate_ms"], CONTACT_S * 1e3, places=9)
        self.assertAlmostEqual(summary["window_ms"], 3 * CONTACT_S * 1e3, places=9)
        self.assertTrue(summary["window_auto"])
        self.assertGreater(summary["rebound_speed_m_s"], 0.8 * SPEED / 1000)
        self.assertEqual((summary["mass_added_percent"], summary["subcycle"]), (0.0, 1))

    def test_the_checks_judge_the_peaks_and_say_when(self):
        stress, g = self.result.summary["checks"]
        frames = self.sidecar["series"]["frames"]
        self.assertEqual((stress["kind"], stress["status"], stress["at"]["unit"]), ("stress", "close", "s"))
        self.assertAlmostEqual(stress["value"], self.result.summary["max_von_mises_MPa"])
        self.assertEqual((g["kind"], g["label"], g["unit"], g["status"]), ("acceleration", "Peak g", "g", "passes"))
        self.assertAlmostEqual(g["value"], self.result.summary["peak_g"], places=3)
        self.assertAlmostEqual(frames[g["at"]["frame"]]["value"], g["at"]["time_s"], delta=CONTACT_S / 4)

    def test_the_glb_carries_a_time_series_its_envelopes_and_its_limits(self):
        extras = self.extras
        self.assertEqual(extras["analysis"]["type"], "impact")
        self.assertEqual((extras["analysis"]["tier"], extras["analysis"]["limits"]), (3, [LIMITS]))
        self.assertEqual([field["field"] for field in extras["fields"]],
                         ["von_mises", "displacement", "von_mises_peak", "displacement_peak"])
        self.assertIn("_VON_MISES_PEAK", self.attributes["_names"])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"]), ("time", "s"))
        values = [frame["value"] for frame in series["frames"]]
        self.assertTrue(len(values) <= 24 and values == sorted(values) and values[0] == 0.0)
        # The peak stress frame is kept, and the viewer opens on it.
        stress = self.result.summary["checks"][0]
        self.assertEqual(series["default"], stress["at"]["frame"])
        self.assertTrue(series["frames"][1]["label"].endswith("µs"))
        drop = extras["study"]["drop"]
        self.assertEqual((drop["height_mm"], drop["floor"], drop["friction"], drop["direction"]), (HEIGHT, "rigid", 0.0, [0.0, 0.0, -1.0]))
        self.assertEqual(len(drop["onto"]), 1)  # the end face it landed on
        self.assertEqual(extras["study"]["window_ms"], "auto")
        self.assertEqual(extras["study"]["mesh"]["order"], 1)

    def test_the_sidecar_curves_the_cli_lines_and_the_findings_say_the_limits(self):
        curves = self.sidecar["curves"]
        force, g = curves["contact_force_N"], curves["rigid_body_g"]
        self.assertEqual((force["x_unit"], force["y_unit"], g["y_unit"]), ("s", "N", "g"))
        self.assertLessEqual(len(force["x"]), 600)
        self.assertAlmostEqual(max(g["y"]) / PEAK_G, 1.0, delta=0.10)
        self.assertEqual(self.sidecar["limits"], [LIMITS])
        self.assertEqual(self.sidecar["summary"]["limits"], LIMITS)
        lines = self.result.human_lines()
        self.assertIn(LIMITS, lines)
        self.assertTrue(any("onto a rigid floor" in line for line in lines))
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertTrue(found["impact_peak"]["summary"].startswith("The floor stops it with a peak of"))
        self.assertIn(LIMITS, found["impact_peak"]["description"])

    def test_plasticity_caps_the_stress_at_yield_and_leaves_it_bent(self):
        from cadgen import fea

        yield_MPa = 100.0
        study = _study(material={**STEEL_1D, "yield_MPa": yield_MPa}, mesh={"size_mm": 3.0}, window_ms=0.05,
                       plasticity={"tangent_MPa": 0},
                       view={"checks": [{"kind": "stress"}, {"kind": "plastic_strain", "limit_percent": 0.2}]})
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "plastic.fea.glb", study=study)
        summary = result.summary
        # Perfectly plastic: the stress stops at yield and the floor pushes with yield × area, not ρ c v A.
        self.assertLessEqual(summary["max_von_mises_MPa"], yield_MPa * 1.001)
        self.assertAlmostEqual(summary["peak_force_N"] / (yield_MPa * SIDE * SIDE), 1.0, delta=0.10)
        self.assertGreater(summary["max_plastic_strain_percent"], 0.2)
        plastic = summary["checks"][1]
        self.assertEqual((plastic["kind"], plastic["label"], plastic["unit"], plastic["status"]),
                         ("plastic_strain", "Permanent bend", "%", "fails"))
        self.assertIn("impact_bends_for_good", [finding["type"] for finding in result.findings])
        extras, attributes = _glb(result.glb)
        self.assertIn("_PLASTIC_STRAIN", attributes["_names"])
        self.assertEqual(extras["study"]["plasticity"], {"tangent_MPa": 0.0})
        self.assertLess(summary["rebound_speed_m_s"], 0.5 * SPEED / 1000)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class OverBudget(unittest.TestCase):
    """A bar with a small fillet at its top (small elements, a short step) and a tiny time target."""

    @classmethod
    def setUpClass(cls):
        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = _bar(cls.directory, "filleted", fillet_mm=1.0)
        base = _study(material=STEEL_1D, mesh={"size_mm": 5.0})
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "all.fea.glb", study={
                **base, "fit": {"seconds": 0.05, "allow": ["window", "subcycling", "mass_scaling"]}})
            cls.subcycled = fea.solve(cls.step, cls.directory / "sub.fea.glb", study={
                **base, "window_ms": 0.05, "fit": {"seconds": 0.05, "allow": ["subcycling"]}})
        cls.extras, _ = _glb(cls.result.glb)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _benchmark(self, result, tolerance: float) -> None:
        summary = result.summary
        self.assertAlmostEqual(summary["contact_ms"] / (CONTACT_S * 1e3), 1.0, delta=tolerance)
        self.assertAlmostEqual(summary["peak_g"] / PEAK_G, 1.0, delta=tolerance)
        self.assertAlmostEqual(_mid_peak(result.glb) / STRESS_MPA, 1.0, delta=tolerance)

    def test_it_completes_by_stopping_early_subcycling_and_scaling_mass(self):
        self.assertTrue(self.result.ok)
        rungs = [step["rung"] for step in self.result.fit]
        self.assertEqual(rungs[:3], ["window", "subcycling", "mass_scaling"])
        summary = self.result.summary
        self.assertTrue(summary["stopped_after_pulse"])
        self.assertLess(summary["end_ms"], summary["window_ms"])
        self.assertGreater(summary["mass_added_percent"], 0.0)
        self.assertLessEqual(summary["mass_added_percent"], 5.0 + 1e-9)
        # The benchmark still holds, within the widened 15 %.
        self._benchmark(self.result, 0.15)

    def test_each_step_is_said_with_its_accuracy_everywhere(self):
        steps = {step["rung"]: step for step in self.result.fit}
        mass = steps["mass_scaling"]
        self.assertIn(f"Added {self.result.summary['mass_added_percent']:.1f}% to the part's mass", mass["words"])
        self.assertLessEqual(mass["detail"]["added_share"], 0.05 + 1e-12)
        self.assertIn("peak g", mass["accuracy"])
        self.assertIsNotNone(mass["accuracy_pct"])
        self.assertIn("first impact", steps["window"]["words"])
        self.assertTrue(all(steps[rung]["accuracy"] for rung in ("window", "subcycling", "mass_scaling")))
        for rung in ("window", "subcycling", "mass_scaling"):
            words = steps[rung]["words"]
            with self.subTest(rung=rung):
                self.assertIn(words, [step["words"] for step in self.extras["fit"]])
                self.assertIn(words, [step["words"] for step in self.sidecar["fit"]])
                self.assertTrue(any(line.startswith(f"adapted: {words}") for line in self.result.human_lines()))
                self.assertIn(f"fit_{rung}", [finding["type"] for finding in self.result.findings])

    def test_subcycling_alone_steps_the_small_elements_more_often(self):
        summary = self.subcycled.summary
        self.assertEqual([step["rung"] for step in self.subcycled.fit][0], "subcycling")
        self.assertGreaterEqual(summary["subcycle"], 2)
        self.assertEqual(summary["mass_added_percent"], 0.0)
        self._benchmark(self.subcycled, 0.15)


if __name__ == "__main__":
    unittest.main()
