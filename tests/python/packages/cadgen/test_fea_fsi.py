"""Flow and bending (`"analysis": "fsi"`, lite): the study it reads, two benchmarks, not settling, and the ladder.

The flap: a round bore 12 mm long, radius 2.5 mm, through a block, with a flap 0.4 mm thick and 2 mm
wide standing up from the bore's floor 4 mm downstream of the inlet; a syrup (1 Pa s) comes in at
0.05 m/s (Re 0.25). The flap is soft (E 5 MPa), so it leans downstream by about a fifth of its
height. Two-way, the leaning flap blocks less of the bore and is pushed less, so it must lean less
than the one-way answer (the flow at rest pushing the flap once) by a few percent, and the coupling
must settle to its tolerance. An independent iteration (a fixed relaxation of 0.7, no Aitken, to ten
times tighter tolerance) must land on the same deflection.

The tube: a soft tube (E 1 MPa, nu 0.3), bore radius 2 mm, wall 0.2 mm, 16 mm long, held at both
ends, a syrup (10 Pa s) through it at 0.01 m/s. Away from its ends its bore swells by the thin-wall
pressure-vessel formula, delta = p R_m^2 (1 - nu^2) / (E t) (its ends held, so the wall does not
stretch along it), with p the flow's own wall pressure there, within 10 %. The flow's pressure drop
two-way is the one where Poiseuille's law and that swelling agree: dp/dx = -8 mu Q / (pi a^4) with
a = R + c p, which integrates to a_in^5 = R^5 + 5 c (8 mu Q / pi) L. Every STEP is a build123d solid
in a temporary directory.
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
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

LIMIT_TEXT = ("Steady flow two-way coupled to a linear elastic part: no flutter, vortex shedding or other unsteady "
              "motion; small-to-moderate deflection, the flow mesh following the part (ALE mesh motion).")
# The flap in a bore.
BORE_L, BORE_R, FLAP_T, FLAP_W, FLAP_TOP, FLAP_X = 12.0, 2.5, 0.4, 2.0, 0.5, 4.0
SYRUP = {"name": "syrup", "density_kg_m3": 1000, "viscosity_Pa_s": 1.0}
# The soft tube.
TUBE_R, TUBE_T, TUBE_L, TUBE_E, TUBE_NU, TUBE_MU, TUBE_U = 2.0, 0.2, 16.0, 1.0, 0.3, 10.0, 0.01


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def flap_step(directory: Path) -> Path:
    from build123d import Box, Cylinder, Pos, Rotation, export_step

    step = directory / "flap.step"
    block = Pos(BORE_L / 2, 0, 0) * Box(BORE_L, 2 * BORE_R + 2, 2 * BORE_R + 2)
    bore = Pos(BORE_L / 2, 0, 0) * Rotation(0, 90, 0) * Cylinder(BORE_R, BORE_L)
    height = FLAP_TOP + BORE_R + 0.5      # from inside the floor up to its top, 0.5 mm above the bore's axis
    flap = Pos(FLAP_X + FLAP_T / 2, 0, FLAP_TOP - height / 2) * Box(FLAP_T, FLAP_W, height)
    export_step((block - bore) + flap, str(step))
    return step


def tube_step(directory: Path) -> Path:
    from build123d import Align, Cylinder, Rotation, export_step

    step = directory / "tube.step"
    along = (Align.CENTER, Align.CENTER, Align.MIN)
    export_step(Rotation(0, 90, 0) * (Cylinder(TUBE_R + TUBE_T, TUBE_L, align=along) - Cylinder(TUBE_R, TUBE_L, align=along)),
                str(step))
    return step


def plane_face(step: Path, axis: int, value: float) -> str:
    from cadgen import fea

    return next(face.ref for face in fea.faces(step).faces
                if face.surface == "plane" and abs(face.center_mm[axis] - value) < 1e-6)


def flap_study(step: Path, **changes) -> dict:
    return {"analysis": "fsi", "material": {"name": "soft", "E_MPa": 5.0, "nu": 0.3, "yield_MPa": 1.0},
            "fixtures": [{"faces": [plane_face(step, 2, -BORE_R - 1)]}], "mesh": {"size_mm": 0.8},
            "flow": {"kind": "internal", "fluid": SYRUP, "inlets": [{"opening": "x_min", "velocity_m_s": 0.05}],
                     "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}, **changes}


def tube_study(step: Path, **changes) -> dict:
    return {"analysis": "fsi", "material": {"name": "soft", "E_MPa": TUBE_E, "nu": TUBE_NU, "yield_MPa": 1.0},
            "fixtures": [{"faces": [plane_face(step, 0, 0.0)]}, {"faces": [plane_face(step, 0, TUBE_L)]}],
            "mesh": {"size_mm": 0.8},
            "flow": {"kind": "internal", "fluid": {"name": "syrup", "density_kg_m3": 1000, "viscosity_Pa_s": TUBE_MU},
                     "inlets": [{"opening": "x_min", "velocity_m_s": TUBE_U}], "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
            **changes}


def solve(step: Path, out: Path, study: dict):
    """Run the study, and hand back the analysis's own result too (the fields on the part's nodes)."""
    from cadgen import fea
    from cadgen._internal.fea.analyses.fsi import FsiAnalysis

    captured = {}
    original = FsiAnalysis.solve

    def keep(self, ctx, inputs):
        captured["result"] = original(self, ctx, inputs)
        return captured["result"]

    with redirect_stderr(io.StringIO()), mock.patch.object(FsiAnalysis, "solve", keep):
        result = fea.solve(step, out, study=study)
    return result, captured["result"]


_SHARED: dict = {}


def shared(name: str):
    """The flap's and the tube's plain runs, solved once for every class that compares against them."""
    if name not in _SHARED:
        if "tmp" not in _SHARED:
            _SHARED["tmp"] = tempfile.TemporaryDirectory()
        directory = Path(_SHARED["tmp"].name)
        if name == "flap":
            step = flap_step(directory)
            study = flap_study(step, view={"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 1.0},
                                                      {"kind": "pressure_drop", "limit_Pa": 5000}]})
            _SHARED[name] = (step, *solve(step, directory / "flap.glb", study))
        else:
            step = tube_step(directory)
            _SHARED[name] = (step, *solve(step, directory / "tube.glb", tube_study(step)))
    return _SHARED[name]


def tearDownModule():
    if "tmp" in _SHARED:
        _SHARED.pop("tmp").cleanup()
    _SHARED.clear()


def tip_deflection(own) -> float:
    import numpy as np

    return float(np.linalg.norm(own.fields["displacement"], axis=1).max())


def bore_swelling(own, x0: float) -> tuple[float, float]:
    """The bore's mean radial displacement (mm) and its mean wall pressure (MPa) within 0.4 mm of x0."""
    import numpy as np

    where, moved = own.dof_locations, own.fields["displacement"]
    radius = np.hypot(where[:, 1], where[:, 2])
    on = (np.abs(where[:, 0] - x0) < 0.4) & (np.abs(radius - TUBE_R) < 1e-3)
    radial = (moved[on, 1] * where[on, 1] + moved[on, 2] * where[on, 2]) / radius[on]
    return float(radial.mean()), float(own.fields["pressure"][on].mean()) / 1e6


class StudyFile(unittest.TestCase):
    STUDY = {"analysis": "fsi", "material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}],
             "flow": {"kind": "internal", "fluid": "water", "inlets": [{"opening": "x_min", "velocity_m_s": 0.5}],
                      "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}}

    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**self.STUDY, **changes})

    def test_it_reads_the_flow_the_material_the_fixtures_and_the_coupling(self):
        parsed = self.parse(coupling={"method": "fixed_point", "relaxation": 0.5, "tolerance": 1e-4, "max_iterations": 40},
                            view={"checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.1},
                                             {"kind": "pressure_drop", "limit_Pa": 500}]})
        inputs = parsed.inputs
        self.assertEqual(parsed.material.name, "Aluminum 6061-T6")
        self.assertEqual((inputs.flow.kind, inputs.flow.fluid.name, inputs.regime), ("internal", "water", "auto"))
        self.assertFalse(inputs.flow.mapped)
        self.assertEqual([(i.opening, i.velocity_m_s) for i in inputs.flow.inlets], [("x_min", 0.5)])
        self.assertEqual((parsed.face_refs, inputs.anchor_refs), (("#o1.f1",), ("#o1.f1",)))
        self.assertEqual((inputs.method, inputs.relaxation, inputs.tolerance, inputs.max_iterations), ("fixed_point", 0.5, 1e-4, 40))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "displacement", "pressure_drop"])
        defaults = self.parse().inputs
        self.assertEqual((defaults.method, defaults.relaxation, defaults.tolerance, defaults.max_iterations), ("aitken", 1.0, 1e-3, 25))
        self.assertEqual(self.parse(flow={**self.STUDY["flow"], "regime": "turbulent"}).inputs.regime, "turbulent")

    def test_the_errors_name_the_field_in_plain_words(self):
        flow = self.STUDY["flow"]
        for changes, fragment in (
            ({"flow": None}, "study.flow"),
            ({"flow": {**flow, "regime": "creeping"}}, "flow.regime"),
            ({"flow": {**flow, "regime": "laminar", "inlets": [{"opening": "x_min", "velocity_m_s": 1, "turbulence_intensity": 0.05}]}},
             "a laminar flow has no turbulence"),
            ({"fixtures": []}, "'fixtures' must list at least one"),
            ({"coupling": {"method": "newton"}}, "coupling.method"),
            ({"coupling": {"steps": 3}}, "coupling: unknown keys ['steps']"),
            ({"coupling": {"max_iterations": 0}}, "coupling.max_iterations"),
            ({"coupling": {"tolerance": 0.9}}, "coupling.tolerance"),
            ({"map_to_structure": {}}, "fsi studies take"),
            ({"view": {"checks": [{"kind": "velocity", "limit_m_s": 1}]}}, "velocity"),
        ):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(fragment, str(caught.exception))

    def test_it_is_registered_built_and_stdlib_only_at_import(self):
        import subprocess
        import sys

        from cadgen._internal.fea.analyses import get_analysis

        fsi = get_analysis("fsi")
        self.assertEqual((fsi.tier, fsi.word, fsi.limits), (3, "Flow and bending", (LIMIT_TEXT,)))
        self.assertEqual(fsi.ladder, ("continuation", "iterative", "fluid_coarsen", "local_refine"))
        self.assertEqual([spec.name for spec in fsi.fields], ["von_mises", "pressure", "wall_shear", "displacement"])
        code = (
            "import sys; sys.path.insert(0, 'packages/cadgen/src');"
            "import cadgen._internal.fea.analyses.fsi;"
            "print(','.join(m for m in ('numpy', 'scipy', 'skfem', 'netgen', 'OCP') if m in sys.modules))"
        )
        root = Path(__file__).resolve().parents[4]
        out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "")


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class FlexibleFlap(unittest.TestCase):
    """A soft flap in a slow syrup: two-way it leans less than one-way, and an independent iteration agrees."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step, cls.result, cls.own = shared("flap")
        cls.extras, cls.attributes = glb_extras(cls.result.glb)
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))
        # The independent iteration: a fixed relaxation of 0.7, no Aitken, to ten times tighter tolerance.
        fixed = flap_study(cls.step, coupling={"method": "fixed_point", "relaxation": 0.7, "tolerance": 1e-4, "max_iterations": 40})
        cls.fixed, cls.fixed_own = solve(cls.step, directory / "fixed.glb", fixed)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_coupling_settles_to_its_tolerance_and_says_how(self):
        coupling = self.result.summary["coupling"]
        self.assertTrue(coupling["converged"])
        self.assertLess(coupling["residual"], 1e-3)
        self.assertLess(coupling["load_change"], 1e-3)
        self.assertGreaterEqual(coupling["iterations"], 2)
        self.assertEqual(coupling["method"], "aitken")
        self.assertEqual(len(coupling["history"]), coupling["iterations"])
        self.assertEqual(self.extras["analysis"]["coupling"]["iterations"], coupling["iterations"])
        self.assertTrue(self.extras["analysis"]["coupling"]["converged"])
        self.assertEqual(self.extras["analysis"]["regime"], "laminar")
        self.assertEqual(self.extras["analysis"]["limits"], [LIMIT_TEXT])
        self.assertEqual(self.extras["analysis"]["warnings"], [])

    def test_two_way_leans_less_than_one_way(self):
        two = tip_deflection(self.own)
        one = self.result.summary["one_way"]["max_displacement_mm"]
        self.assertAlmostEqual(self.result.summary["max_displacement_mm"], two, places=5)
        # Bent downstream, the flap blocks less of the bore and is pushed less.
        self.assertLess(two, 0.98 * one, (two, one))
        self.assertGreater(two, 0.8 * one, (two, one))
        self.assertLess(self.result.summary["two_way_vs_one_way"]["displacement_change_pct"], -2.0)
        # It leans downstream, its top moving along +x.
        top = self.result.summary["max_displacement_at_mm"]
        self.assertGreater(top[2], 0.0)
        self.assertGreater(self.result.summary["force_N"][0], 0.0)

    def test_an_independent_fixed_point_iteration_lands_on_the_same_deflection(self):
        coupling = self.fixed.summary["coupling"]
        self.assertTrue(coupling["converged"])
        self.assertEqual(coupling["method"], "fixed_point")
        self.assertTrue(all(w == 0.7 for w in coupling["relaxation"]))
        self.assertLess(coupling["residual"], 1e-4)
        self.assertGreater(coupling["iterations"], self.result.summary["coupling"]["iterations"])
        aitken, fixed = tip_deflection(self.own), tip_deflection(self.fixed_own)
        self.assertLess(abs(aitken - fixed) / fixed, 2e-3, (aitken, fixed))
        self.assertEqual(self.fixed.summary["one_way"]["max_displacement_mm"], self.result.summary["one_way"]["max_displacement_mm"])

    def test_the_glb_carries_stress_pressure_shear_and_the_deformed_shape(self):
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertEqual(set(fields), {"von_mises", "pressure", "wall_shear", "displacement"})
        self.assertTrue(fields["pressure"]["signed"])
        for attribute in ("_VON_MISES", "_PRESSURE", "_WALL_SHEAR", "_DISPLACEMENT"):
            self.assertIn(attribute, self.attributes)
        self.assertIsNotNone(self.extras["deformation_scale"])
        self.assertGreater(fields["pressure"]["max"], 0.0)
        study = self.extras["study"]
        self.assertEqual(study["flow"]["inlets"], [{"opening": "x_min", "velocity_m_s": 0.05, "profile": "developed"}])
        self.assertEqual(study["flow"]["regime"], "auto")
        self.assertEqual(len(study["fixtures"]), 1)
        self.assertEqual(study["coupling"]["method"], "aitken")
        self.assertEqual(self.sidecar["analysis"], "fsi")

    def test_the_checks_and_the_cli(self):
        checks = {check["kind"]: check for check in self.result.summary["checks"]}
        self.assertEqual(list(checks), ["stress", "displacement", "pressure_drop"])
        self.assertEqual(checks["displacement"]["value"], round(self.result.summary["max_displacement_mm"], 6))
        self.assertEqual(checks["pressure_drop"]["unit"], "Pa")
        self.assertTrue(all(check["status"] == "passes" for check in checks.values()))
        lines = "\n".join(self.result.human_lines())
        self.assertIn("(fsi)", lines)
        self.assertIn("coupled two ways", lines)
        self.assertIn("coupling: ", lines)
        self.assertIn("(one-way ", lines)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class CompliantTube(unittest.TestCase):
    """A soft tube swells under its own flow: the thin-wall formula with the flow's pressure, and the drop where
    Poiseuille's law and the swelling agree."""

    @classmethod
    def setUpClass(cls):
        cls.step, cls.result, cls.own = shared("tube")

    def test_the_bore_swells_by_the_thin_wall_formula_with_the_flows_pressure(self):
        self.assertTrue(self.result.summary["coupling"]["converged"])
        mean_radius = TUBE_R + TUBE_T / 2
        for x0 in (4.0, 6.0, 8.0, 10.0):
            swelling, pressure = bore_swelling(self.own, x0)
            thin_wall = pressure * mean_radius ** 2 * (1 - TUBE_NU ** 2) / (TUBE_E * TUBE_T)
            with self.subTest(x_mm=x0):
                self.assertGreater(pressure, 0.0)
                self.assertLess(abs(swelling - thin_wall) / thin_wall, 0.10, (x0, swelling, thin_wall))

    def test_the_drop_is_where_poiseuille_and_the_swelling_agree(self):
        summary = self.result.summary
        mu = TUBE_MU * 1e-6                                       # MPa s
        flow = summary["flow_rate_m3_s"] * 1e9                    # mm^3/s
        k = 8 * mu * flow / math.pi
        rigid = k * TUBE_L / TUBE_R ** 4 * 1e6                    # Pa
        c = (TUBE_R + TUBE_T / 2) ** 2 * (1 - TUBE_NU ** 2) / (TUBE_E * TUBE_T)   # mm of swelling per MPa
        swollen = ((TUBE_R ** 5 + 5 * c * k * TUBE_L) ** 0.2 - TUBE_R) / c * 1e6
        one, two = summary["one_way"]["pressure_drop_Pa"], summary["pressure_drop_Pa"]
        self.assertLess(abs(one - rigid) / rigid, 0.03, (one, rigid))
        self.assertLess(abs(two - swollen) / swollen, 0.03, (two, swollen))
        # Swollen, the tube passes the same flow for less: two-way below one-way.
        self.assertLess(two, one)
        self.assertLess(summary["two_way_vs_one_way"]["pressure_drop_change_pct"], -2.0)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class NotSettled(unittest.TestCase):
    """Two iterations are not enough for the soft tube: it still answers, with the last state, said plainly."""

    def test_the_last_state_is_reported_as_not_converged(self):
        with tempfile.TemporaryDirectory() as tmp:
            step = tube_step(Path(tmp))
            result, _ = solve(step, Path(tmp) / "short.glb", tube_study(step, coupling={"max_iterations": 2}))
            extras, _ = glb_extras(result.glb)
        self.assertTrue(result.ok)
        coupling = result.summary["coupling"]
        self.assertEqual((coupling["converged"], coupling["iterations"]), (False, 2))
        self.assertGreater(coupling["residual"], 1e-3)
        sentence = extras["analysis"]["warnings"][0]
        self.assertIn("did not settle in 2 coupling iterations", sentence)
        self.assertIn("this is the last state, not a converged answer", sentence)
        self.assertFalse(extras["analysis"]["coupling"]["converged"])
        self.assertIn("coupling_not_converged", [finding["type"] for finding in result.findings])
        self.assertIn("NOT converged", "\n".join(result.human_lines()))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    """A tiny time target: the flap coarsens its flow's core (its walls kept at the size asked for) and still
    leans within 5 % of the full answer; the tube, its continuation threshold lowered, ramps its inflow up in
    steps and lands on the unramped answer."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        flap = flap_step(directory)
        cls.flap, cls.flap_own = solve(flap, directory / "flap.glb",
                                       flap_study(flap, fit={"seconds": 1, "allow": ["fluid_coarsen", "local_refine"]}))
        _, cls.flap_full, cls.flap_full_own = shared("flap")
        cls.flap_extras, _ = glb_extras(cls.flap.glb)
        tube = tube_step(directory)
        with mock.patch("cadgen._internal.fea.analyses.cfd.CONTINUE_FROM", 0.0):
            cls.tube, cls.tube_own = solve(tube, directory / "ramp.glb",
                                           tube_study(tube, fit={"seconds": 0.5, "allow": ["continuation"]}))
        _, cls.tube_full, cls.tube_full_own = shared("tube")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_fluid_coarsen_keeps_the_walls_fine_and_the_deflection_within_5_percent(self):
        step = next(step for step in self.flap.fit if step["rung"] == "fluid_coarsen")
        self.assertIn("walls and openings are still meshed at 0.8 mm", step["words"])
        self.assertTrue(step["accuracy"])
        self.assertEqual(self.flap.summary["fluid_mesh"]["wall_size_mm"], 0.8)
        self.assertGreater(self.flap.summary["fluid_mesh"]["far_size_mm"], 0.8)
        # The part's own solve is a small share of the cost: local_refine is not worth two coupled passes.
        self.assertNotIn("local_refine", [s["rung"] for s in self.flap.fit])
        self.assertIn(step["words"], [s["words"] for s in self.flap_extras["fit"]])
        self.assertIn("fit_fluid_coarsen", [finding["type"] for finding in self.flap.findings])
        self.assertTrue(any(line.startswith(f"adapted: {step['words']}") for line in self.flap.human_lines()))
        self.assertTrue(self.flap.summary["coupling"]["converged"])
        adapted, full = tip_deflection(self.flap_own), tip_deflection(self.flap_full_own)
        self.assertLess(abs(adapted - full) / full, 0.05, (adapted, full))

    def test_continuation_ramps_the_inflow_and_lands_on_the_same_answer(self):
        step = next(step for step in self.tube.fit if step["rung"] == "continuation")
        self.assertIn("Ramped the inflow up in steps (25%, 50%, 100% of 0.01 m/s)", step["words"])
        self.assertEqual(step["detail"]["ramp"], [0.25, 0.5, 1.0])
        coupling = self.tube.summary["coupling"]
        self.assertTrue(coupling["ramped"])
        self.assertTrue(coupling["converged"])
        self.assertIn("fit_continuation", [finding["type"] for finding in self.tube.findings])
        ramped, full = bore_swelling(self.tube_own, 8.0)[0], bore_swelling(self.tube_full_own, 8.0)[0]
        self.assertLess(abs(ramped - full) / full, 0.01, (ramped, full))
        self.assertLess(abs(self.tube.summary["pressure_drop_Pa"] - self.tube_full.summary["pressure_drop_Pa"])
                        / self.tube_full.summary["pressure_drop_Pa"], 0.01)


def box_duct_step(directory: Path, side: float, length: float, wall: float = 1.0) -> Path:
    """A square passage through a block along x: sharp corners where the inlet meets the walls."""
    from build123d import Align, Box, export_step

    step = directory / "duct.step"
    along = (Align.MIN, Align.CENTER, Align.CENTER)
    export_step(Box(length, side + 2 * wall, side + 2 * wall, align=along) - Box(length, side, side, align=along), str(step))
    return step


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class BoxDuct(unittest.TestCase):
    """A soft square duct (sharp corners at its inlet) bends under its flow: the laminar flow under it solves."""

    def test_a_square_duct_solves(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            step = box_duct_step(directory, 3.0, 12.0, wall=0.5)
            study = {"analysis": "fsi", "material": {"name": "soft", "E_MPa": 5.0, "nu": 0.3, "yield_MPa": 1.0},
                     "fixtures": [{"faces": [plane_face(step, 0, 0.0)]}, {"faces": [plane_face(step, 0, 12.0)]}],
                     "mesh": {"size_mm": 1.0},
                     "flow": {"kind": "internal", "fluid": SYRUP, "inlets": [{"opening": "x_min", "velocity_m_s": 0.01}],
                              "outlets": [{"opening": "x_max", "pressure_Pa": 0}]}}
            result, _ = solve(step, directory / "duct.glb", study)
        self.assertTrue(result.ok)
        self.assertGreater(result.summary["pressure_drop_Pa"], 0)


if __name__ == "__main__":
    unittest.main()
