"""Cooled by flow (`"analysis": "conjugate_heat"`): the study it reads, Graetz's Nusselt number, energy balances and the ladder.

- The pipe: a tube 32 mm long, bore radius 2 mm, wall 1 mm, along x, its outer
  face held at 80 °C, its wall a near-perfect conductor (so the bore is at the
  wall temperature). An oil-like fluid (ρ 900 kg/m³, μ 0.05 Pa·s, k 0.15 W/(m K),
  c_p 2000 J/(kg K): Pr 667) comes in at 20 °C with the fully developed profile, at
  a Péclet number of 40 (Re 0.06). Laminar, thermally developed flow with a
  constant wall temperature has Nu = h D / k = 3.66, and its bulk temperature
  approaches the wall's as θ_b ∝ exp(−4 Nu x / (Pe D)), so between two sections
  in the developed part Nu = Pe D / (4 Δx) ln(θ1 / θ2); the bulk temperatures are
  the mixing-cup integrals over each section (the fluid's own temperature and
  velocity, sampled). Every watt the held face sends into the tube leaves as
  m c_p ΔT.
- The cold plate: an aluminium block 24 x 10 x 8 mm with a 4 mm bore along x,
  1 W into its top face, everything else insulated, water at 20 °C through the
  bore at 0.01 m/s: the outlet's mixed temperature is T_in + Q / (m c_p).
- The ladder: the cold plate against a 1 s target coarsens the flow's core and the
  part away from its peak, says so everywhere, and still balances.
- Turbulent: the cold plate at 1 m/s (Re 4000) solved with the k-omega SST flow and
  the thermal law of the wall still closes its books; its mean Nusselt number is
  printed beside Dittus-Boelter's.

Every STEP is a build123d solid in a temporary directory.
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

R, WALL, LENGTH = 2.0, 1.0, 32.0
OIL = {"name": "oil", "density_kg_m3": 900.0, "viscosity_Pa_s": 0.05, "conductivity_W_mK": 0.15, "specific_heat_J_kgK": 2000.0}
PECLET = 40.0
WATER_RHO, WATER_CP = 998.2, 4181.0
LIMIT_TEXT = "Steady; the flow carries the heat but is not changed by it (no buoyancy, constant properties)."
COLD_PLATE = {
    "analysis": "conjugate_heat", "material": "aluminum-6061-t6", "mesh": {"size_mm": 0.75},
    "flow": {"kind": "internal", "fluid": "water",
             "inlets": [{"opening": "x_min", "velocity_m_s": 0.01, "temperature_C": 20}],
             "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
    "view": {"checks": [{"kind": "temperature", "max_C": 60}, {"kind": "pressure_drop", "limit_Pa": 100}]},
}


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def solve(step: Path, out: Path, study: dict):
    """Run the study; hand back the result and the analysis's own (the fluid's temperatures and space)."""
    from cadgen import fea
    from cadgen._internal.fea.analyses.conjugate_heat import ConjugateHeatAnalysis

    captured = {}
    original = ConjugateHeatAnalysis.solve

    def keep(self, ctx, inputs):
        captured["result"] = original(self, ctx, inputs)
        return captured["result"]

    with redirect_stderr(io.StringIO()), mock.patch.object(ConjugateHeatAnalysis, "solve", keep):
        result = fea.solve(step, out, study=study)
    return result, captured.get("result")


class StudyFile(unittest.TestCase):
    def parse(self, **changes):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**COLD_PLATE, **changes})

    def flow(self, **changes):
        return {**COLD_PLATE["flow"], **changes}

    def test_it_is_registered_built_tier_three(self):
        from cadgen._internal.fea.analyses import REGISTRY, get_analysis

        entry = REGISTRY["conjugate_heat"]
        self.assertEqual((entry.tier, entry.word, entry.planned), (3, "Cooled by flow", False))
        analysis = get_analysis("conjugate_heat")
        self.assertEqual(analysis.limits, (LIMIT_TEXT,))
        self.assertEqual(analysis.ladder, ("iterative", "fluid_coarsen", "continuation", "local_refine"))
        self.assertEqual([spec.kind for spec in analysis.checks], ["temperature", "pressure_drop", "velocity"])
        self.assertEqual([spec.name for spec in analysis.fields],
                         ["temperature", "fluid_temperature", "wall_heat_flux", "heat_transfer_coefficient", "pressure"])

    def test_it_reads_the_flow_the_inlet_temperatures_and_the_parts_heat(self):
        study = self.parse(heat=[{"faces": ["#o1.f3"], "W": 2}], convection=[{"faces": ["#o1.f4"], "h_W_m2K": 10, "ambient_C": 25}])
        inputs = study.inputs
        self.assertEqual(study.analysis, "conjugate_heat")
        self.assertEqual(inputs.inlet_C, (20.0,))
        self.assertEqual((inputs.fluid_conductivity, inputs.fluid_specific_heat), (0.606, 4181.0))  # water's
        self.assertEqual(inputs.regime, "auto")
        self.assertEqual(inputs.flow.inlets[0].velocity_m_s, 0.01)
        self.assertEqual(inputs.reference_C, 20.0)  # the coolest the study sets: the inlet
        self.assertFalse(inputs.requires_anchor)  # the fluid carries the heat away
        self.assertEqual(inputs.thermal.heat[0].watts, 2.0)
        custom = self.parse(flow=self.flow(fluid=OIL, regime="laminar"))
        self.assertEqual((custom.inputs.fluid_conductivity, custom.inputs.fluid_specific_heat, custom.inputs.regime), (0.15, 2000.0, "laminar"))
        outside = self.parse(flow={"kind": "external", "fluid": "air", "velocity_m_s": [2, 0, 0], "temperature_C": 15})
        self.assertEqual(outside.inputs.inlet_C, (15.0,))

    def test_the_errors_name_the_field(self):
        no_k = {key: value for key, value in OIL.items() if key != "conductivity_W_mK"}
        cases = [
            ({"flow": self.flow(inlets=[{"opening": "x_min", "velocity_m_s": 0.01}])}, "flow.inlets[0].temperature_C"),
            ({"flow": {"kind": "external", "fluid": "air", "velocity_m_s": [2, 0, 0]}}, "flow.temperature_C"),
            ({"flow": self.flow(fluid=no_k)}, "flow.fluid.conductivity_W_mK"),
            ({"flow": self.flow(regime="creeping")}, "flow.regime"),
            ({"flow": self.flow(regime="laminar", inlets=[{"opening": "x_min", "velocity_m_s": 0.01, "temperature_C": 20,
                                                            "turbulence_intensity": 0.05}])}, "a laminar flow has no turbulence"),
            ({"flow": self.flow(inlets=[{"opening": "x_min", "velocity_m_s": 0.01, "temperature_C": 20, "swirl": 1}])},
             "an inlet takes opening, velocity_m_s, temperature_C, profile and turbulence_intensity"),
            ({"flow": self.flow(inlets=[{"opening": "x_min", "velocity_m_s": 0.01, "temperature_C": -300}])}, "below absolute zero"),
            ({"view": {"checks": [{"kind": "temperature", "max_C": 15}]}}, "15 °C is not above 20 °C"),
            ({"view": {"checks": [{"kind": "stress"}]}}, "is not a check this cadgen makes"),
            ({"radiation": []}, "unknown keys ['radiation']"),
        ]
        for changes, words in cases:
            with self.subTest(words=words), self.assertRaises(ValueError) as caught:
                self.parse(**changes)
            self.assertIn(words, str(caught.exception))

    def test_a_material_is_needed_for_the_parts_conduction(self):
        from cadgen._internal.fea.study import parse_study

        with self.assertRaises(ValueError) as caught:
            parse_study({key: value for key, value in COLD_PLATE.items() if key != "material"})
        self.assertIn("'material' is required", str(caught.exception))


def tube_step(directory: Path) -> tuple[Path, str]:
    from build123d import Align, Cylinder, Rotation, export_step

    from cadgen import fea

    step = directory / "tube.step"
    along = (Align.CENTER, Align.CENTER, Align.MIN)
    export_step(Rotation(0, 90, 0) * (Cylinder(R + WALL, LENGTH, align=along) - Cylinder(R, LENGTH, align=along)), str(step))
    outer = max((face for face in fea.faces(step).faces if face.surface == "cylinder"), key=lambda face: face.area_mm2).ref
    return step, outer


def cold_plate_step(directory: Path) -> tuple[Path, str]:
    from build123d import Align, Box, Cylinder, Rotation, export_step

    from cadgen import fea

    step = directory / "cold_plate.step"
    block = Box(24, 10, 8, align=(Align.MIN, Align.CENTER, Align.CENTER))
    bore = Rotation(0, 90, 0) * Cylinder(R, 24, align=(Align.CENTER, Align.CENTER, Align.MIN))
    export_step(block - bore, str(step))
    top = max((face for face in fea.faces(step).faces if face.normal and face.normal[2] > 0.9), key=lambda face: face.center_mm[2]).ref
    return step, top


def section_bulk(analysis_result, x: float) -> float:
    """The mixing-cup temperature of the pipe's section at ``x``: ∫ u T dA / ∫ u dA, sampled on a polar grid."""
    import numpy as np
    from skfem import Basis, ElementTetP1, MeshTet

    space = analysis_result.scalars["fluid_space"]
    T = analysis_result.scalars["fluid_temperatures"]
    velocity = space.nodal(analysis_result.scalars["flow"].u)[:space.vertices, 0]
    # Sampled on the straight-sided mesh of the same corners (the field is linear on each element).
    straight = Basis(MeshTet(space.mesh.p, space.mesh.t[:4]), ElementTetP1())
    nodes, weights = np.polynomial.legendre.leggauss(10)
    radii, radial = 0.5 * (nodes + 1) * R * 0.999, 0.5 * weights * R * 0.999
    angles = np.linspace(0.0, 2 * math.pi, 48, endpoint=False)
    points = np.array([[x, r * math.cos(a), r * math.sin(a)] for r in radii for a in angles]).T
    w = np.repeat(radial * radii, len(angles))
    probe = straight.probes(points)
    u, t = probe @ velocity, probe @ T
    return float((w * u * t).sum() / (w * u).sum())


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Pipe(unittest.TestCase):
    """Graetz: laminar flow through a pipe whose wall is held at one temperature."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        directory = Path(cls.tmp.name)
        step, outer = tube_step(directory)
        cls.U = PECLET * OIL["conductivity_W_mK"] / (OIL["density_kg_m3"] * OIL["specific_heat_J_kgK"] * 2 * R / 1000)
        cls.out = directory / "tube.glb"
        cls.result, cls.own = solve(step, cls.out, {
            "analysis": "conjugate_heat", "material": {"name": "aluminum-6061-t6", "conductivity_W_mK": 20000.0},
            "mesh": {"size_mm": 0.5},
            "flow": {"kind": "internal", "regime": "laminar", "fluid": OIL,
                     "inlets": [{"opening": "x_min", "velocity_m_s": cls.U, "temperature_C": 20}],
                     "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
            "temperatures": [{"faces": [outer], "C": 80}],
        })

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_developed_nusselt_number_is_graetzs(self):
        x1, x2 = 8.0, 28.0   # 2 and 7 diameters in: past the thermal entry (x / (D Pe) > 0.05)
        theta1, theta2 = (80.0 - section_bulk(self.own, x) for x in (x1, x2))
        nusselt = PECLET * (2 * R) / (4 * (x2 - x1)) * math.log(theta1 / theta2)
        self.assertLess(abs(nusselt - 3.66) / 3.66, 0.05, nusselt)
        print(f"\n  Graetz, constant wall temperature: Nu {nusselt:.4f} against 3.66 ({100 * (nusselt - 3.66) / 3.66:+.2f}%), Pe {PECLET:g}")

    def test_every_watt_into_the_tube_leaves_as_m_cp_delta_t(self):
        summary = self.result.summary
        held = summary["part_heat_in_W"]     # what the held outer face sends in
        self.assertLess(abs(summary["heat_to_fluid_W"] - held) / held, 1e-6)
        self.assertLess(abs(summary["heat_carried_W"] - held) / held, 0.01)
        # m c_p ΔT from the inlet's own flow (ρ U π R²) and the outlet's mixed temperature.
        mass = OIL["density_kg_m3"] * self.U * math.pi * (R / 1000) ** 2
        carried = mass * OIL["specific_heat_J_kgK"] * (summary["outlet_temperature_C"] - 20.0)
        self.assertLess(abs(carried - held) / held, 0.01, (carried, held))
        self.assertLess(summary["fluid_balance"], 1e-6)
        self.assertEqual(summary["regime"], "laminar")
        print(f"\n  pipe energy balance: m c_p ΔT {carried:.5f} W against {held:.5f} W in ({100 * (carried - held) / held:+.3f}%)")

    def test_it_writes_the_parts_and_the_fluids_temperature_and_the_wall_heat(self):
        extras, attributes = glb_extras(self.out)
        for attribute in ("_TEMPERATURE", "_FLUID_TEMPERATURE", "_WALL_HEAT_FLUX", "_HEAT_TRANSFER_COEFFICIENT", "_PRESSURE"):
            self.assertIn(attribute, attributes)
        self.assertEqual([field["field"] for field in extras["fields"]],
                         ["temperature", "fluid_temperature", "wall_heat_flux", "heat_transfer_coefficient", "pressure"])
        self.assertEqual(extras["analysis"]["type"], "conjugate_heat")
        self.assertEqual(extras["analysis"]["regime"], "laminar")
        self.assertEqual(extras["analysis"]["limits"], [LIMIT_TEXT])
        self.assertEqual(extras["study"]["flow"]["inlets"][0]["temperature_C"], 20)
        self.assertEqual(extras["study"]["flow"]["fluid"]["conductivity_W_mK"], 0.15)
        # The fluid next to the wall warms from the inlet towards the wall's 80 °C.
        fluid = self.result.summary["wall_fluid_temperature_C"]
        self.assertGreater(fluid[1], 60.0)
        self.assertGreaterEqual(fluid[0], 20.0 - 1e-6)
        self.assertGreater(self.result.summary["mean_heat_transfer_coefficient_W_m2K"], 0)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ColdPlate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_outlet_is_as_hot_as_the_energy_balance_says(self):
        step, top = cold_plate_step(self.dir)
        result, _ = solve(step, self.dir / "plate.glb", {**COLD_PLATE, "heat": [{"faces": [top], "W": 1.0}]})
        summary = result.summary
        self.assertEqual(summary["regime"], "laminar")    # auto, at Re 40
        expected = 20.0 + 1.0 / (summary["mass_flow_kg_s"] * WATER_CP)
        self.assertLess(abs(summary["outlet_temperature_C"] - expected) / (expected - 20.0), 0.01, (summary["outlet_temperature_C"], expected))
        # And by the flow the inlet asked for (ρ U π R²): the solved flow is within 1 % of it.
        asked = WATER_RHO * 0.01 * math.pi * (R / 1000) ** 2
        self.assertLess(abs(summary["mass_flow_kg_s"] - asked) / asked, 0.01)
        by_asked = 20.0 + 1.0 / (asked * WATER_CP)
        self.assertAlmostEqual(summary["heat_to_fluid_W"], 1.0, places=6)
        self.assertAlmostEqual(summary["heat_carried_W"], 1.0, places=6)
        self.assertEqual([check["status"] for check in summary["checks"]], ["passes", "passes"])
        self.assertGreater(summary["max_temperature_C"], summary["outlet_temperature_C"])
        lines = result.human_lines()
        self.assertTrue(any(line.startswith("fluid in at 20 °C, out at") for line in lines))
        print(f"\n  cold plate outlet: {summary['outlet_temperature_C']:.6f} °C against {expected:.6f} °C by the balance on the solved "
              f"flow, {by_asked:.6f} °C on the asked flow ({100 * (summary['outlet_temperature_C'] - by_asked) / (by_asked - 20):+.2f}% of the rise)")

    def test_the_ladder_coarsens_the_flows_core_and_the_part_and_still_balances(self):
        step, top = cold_plate_step(self.dir)
        out = self.dir / "ladder.glb"
        result, _ = solve(step, out, {**COLD_PLATE, "heat": [{"faces": [top], "W": 1.0}], "fit": {"seconds": 1}})
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("fluid_coarsen", rungs)
        self.assertIn("local_refine", rungs)
        extras, _ = glb_extras(out)
        sidecar = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        coarsen = next(step for step in extras["fit"] if step["rung"] == "fluid_coarsen")
        self.assertIn("the heat it takes from the walls", coarsen["accuracy"])
        self.assertEqual([s["rung"] for s in sidecar["fit"]], rungs)
        self.assertTrue(any(line.startswith("adapted: Coarsened the flow mesh away from the walls") for line in result.human_lines()))
        self.assertTrue(any(f["type"] == "fit_fluid_coarsen" for f in result.findings))
        summary = result.summary
        expected = 20.0 + 1.0 / (summary["mass_flow_kg_s"] * WATER_CP)
        # Widened to 2 % for the ladder; the books close exactly all the same.
        self.assertLess(abs(summary["outlet_temperature_C"] - expected) / (expected - 20.0), 0.02)
        self.assertLess(summary["fluid_balance"], 1e-6)
        print(f"\n  cold plate, adapted ({', '.join(rungs)}): outlet {summary['outlet_temperature_C']:.6f} °C against {expected:.6f} °C")

    def test_a_turbulent_flow_closes_its_books_too(self):
        step, top = cold_plate_step(self.dir)
        flow = {**COLD_PLATE["flow"], "regime": "turbulent",
                "inlets": [{"opening": "x_min", "velocity_m_s": 1.0, "temperature_C": 20}]}
        result, _ = solve(step, self.dir / "turbulent.glb", {**COLD_PLATE, "flow": flow, "heat": [{"faces": [top], "W": 1.0}]})
        summary = result.summary
        self.assertEqual(summary["regime"], "turbulent")
        self.assertAlmostEqual(summary["heat_to_fluid_W"], 1.0, places=6)
        self.assertLess(summary["fluid_balance"], 0.01)
        reynolds, prandtl = summary["reynolds"]["value"], summary["prandtl"]
        dittus_boelter = 0.023 * reynolds ** 0.8 * prandtl ** 0.4
        self.assertLess(abs(summary["nusselt"] - dittus_boelter) / dittus_boelter, 0.5)
        print(f"\n  cold plate, turbulent at Re {reynolds:.0f}: mean Nu {summary['nusselt']:.2f} (a 6-diameter plate, entry included), "
              f"Dittus-Boelter {dittus_boelter:.2f} for developed flow")


if __name__ == "__main__":
    unittest.main()
