"""Magnetic / electric (`"analysis": "electromagnetic"`): the study it reads, and textbook answers per mode.

- Steady current: a 40 x 4 x 4 mm aluminium bar held at 1 mV on one end and 0 V on the other has
  R = rho L / A, and the Joule heat it makes is I² R; with the heat handed to a thermal solve its ends,
  cooled by air, warm by P / (h A).
- Electrostatics: a PETG slab between two painted electrodes (its insulated sides keep the field
  straight) holds C = eps0 eps_r A / d; two aluminium plates in air, the upper one's centre electrode
  shielded by a guard cup at its own voltage, hold C = eps0 pi (r + g/2)² / d (Maxwell's guard-ring
  capacitor: the fringe goes to the guard).
- Magnetostatics: a ring coil (inner radius a1, outer a2, height 2b, uniform current density J) has
  B = mu0 J b ln((a2 + sqrt(a2² + b²)) / (a1 + sqrt(a1² + b²))) at its centre; two coaxial coils
  pull on each other with the force a Biot-Savart sum over their filaments gives.

Each STEP is a build123d solid or compound in a temporary directory; meshes are coarse.
"""

from __future__ import annotations

import io
import json
import math
import re
import struct
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.materials import MATERIALS, NONE_REASONS, lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

REFERENCE = Path(__file__).resolve().parents[4] / "skills" / "fea" / "references" / "materials.md"
EPS0_F_M = 8.8541878188e-12
MU0_H_M = 1.25663706127e-6


def parse(document: dict):
    from cadgen._internal.fea.study import parse_study

    return parse_study({"analysis": "electromagnetic", "material": "aluminum-6061-t6", **document})


def glb(path: Path, names: tuple[str, ...]) -> tuple[dict, dict]:
    """A result GLB's extras and the named vertex attributes as lists of rows."""
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
    return gltf["meshes"][0]["extras"], out


def planes_along(step: Path, axis: int, occurrence: str | None = None) -> dict[float, str]:
    """Plane faces whose normal is along ``axis``, by their position on it."""
    from cadgen import fea

    return {round(face.center_mm[axis], 6): face.ref for face in fea.faces(step, occurrence=occurrence).faces
            if face.surface == "plane" and face.normal and abs(abs(face.normal[axis]) - 1) < 1e-6}


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


class StudyFile(unittest.TestCase):
    def test_it_is_built_and_registered_no_longer_planned(self):
        from cadgen._internal.fea.analyses import REGISTRY, get_analysis

        self.assertFalse(REGISTRY["electromagnetic"].planned)
        self.assertEqual(get_analysis("electromagnetic").word, "Magnetic / electric")

    def test_each_mode_reads_its_own_keys_and_writes_its_own_fields(self):
        electro = parse({"mode": "electrostatic", "material": "petg", "air": {"around_mm": 5},
                         "voltages": [{"faces": ["#o1.f1"], "V": 1000, "name": "top"}, {"faces": ["#o1.f2"], "V": 0}],
                         "probes": [{"at_mm": [0, 0, 1], "label": "gap"}],
                         "view": {"checks": [{"kind": "electric_field", "limit_kV_mm": 3}]}})
        inputs = electro.inputs
        self.assertEqual((inputs.mode, inputs.air_mm, inputs.between), ("electrostatic", 5.0, ("top", "0 V")))
        self.assertEqual(electro.checks[0], {"kind": "electric_field", "limit_kV_mm": 3.0})
        from cadgen._internal.fea.analyses import get_analysis

        analysis = get_analysis("electromagnetic")
        self.assertEqual([f.name for f in analysis.fields], ["potential", "electric_field"])
        current = parse({"mode": "current", "voltages": [{"faces": ["#o1.f2"], "V": 0}], "currents": [{"faces": ["#o1.f1"], "A": 2}],
                         "electro_thermal": {"convection": [{"faces": ["#o1.f3"], "h_W_m2K": 10, "ambient_C": 20}]}})
        self.assertEqual(current.inputs.material_needs, frozenset({"resistivity", "conductivity"}))
        self.assertEqual([f.name for f in analysis.fields], ["potential", "current_density", "temperature"])
        self.assertIsNone(current.inputs.air_mm)
        magnetic = parse({"mode": "magnetostatic", "coils": [{"turns": 100, "A": 2, "axis": {"direction": [0, 0, 1]}}],
                          "map_to_structure": {"fixtures": [{"faces": ["#o1.f1"]}]}})
        self.assertEqual(magnetic.inputs.air_mm, 0.0)  # magnetostatics always solves in air
        self.assertEqual([f.name for f in analysis.fields], ["magnetic_field", "von_mises", "displacement"])

    def test_the_errors_name_the_field_in_plain_words(self):
        cases = [
            ({"mode": "plasma"}, "mode: \"plasma\" is not one of"),
            ({"mode": "electrostatic"}, "needs faces held at a voltage"),
            ({"mode": "current", "currents": [{"faces": ["#o1.f1"], "A": 2}]}, "a current needs somewhere to leave"),
            ({"mode": "current", "voltages": [{"faces": ["#o1.f1"], "V": 0}], "air": True}, "air is not for a current study"),
            ({"mode": "magnetostatic"}, "needs a source: a coil"),
            ({"mode": "magnetostatic", "coils": [{"turns": 10, "A": 1}]}, "coils[0].axis"),
            ({"mode": "magnetostatic", "coils": [{"turns": 10, "A": 1, "axis": {"direction": [0, 0, 0]}}]}, "the direction is zero"),
            ({"mode": "electrostatic", "voltages": [{"faces": ["#o1.f1"], "V": 1}], "capacitance": {"between": ["a", "b"]}},
             "names no electrode"),
            ({"mode": "electrostatic", "voltages": [{"faces": ["#o1.f1"], "V": 1}],
              "view": {"checks": [{"kind": "electric_field"}]}}, "limit_kV_mm"),
            ({"mode": "current", "voltages": [{"faces": ["#o1.f1"], "V": 1}],
              "view": {"checks": [{"kind": "electric_field", "limit_kV_mm": 3}]}}, "not for a current study"),
            ({"mode": "current", "voltages": [{"faces": ["#o1.f1"], "V": 1}],
              "view": {"checks": [{"kind": "temperature", "max_C": 80}]}}, "add electro_thermal"),
            ({"mode": "magnetostatic", "material": "steel", "coils": [{"turns": 10, "A": 1, "axis": {"direction": [0, 0, 1]}}]},
             "relative_permeability"),
        ]
        for changes, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse(changes)
            self.assertIn(fragment, str(caught.exception))


class Materials(unittest.TestCase):
    def test_every_material_has_its_electrical_values_or_a_reason(self):
        self.assertEqual(lookup_material("6061").resistivity, 3.99e-8)
        self.assertEqual(lookup_material("stainless").permeability, 1.008)
        self.assertEqual(lookup_material("petg").permittivity, 2.6)
        for key, material in MATERIALS.items():
            with self.subTest(material=key):
                self.assertGreater(material.resistivity, 0)
                if material.resistivity < 1.0:
                    self.assertIn((key, "permittivity"), NONE_REASONS)
                else:
                    self.assertGreater(material.permittivity, 1.0)
        self.assertIn(("steel", "permeability"), NONE_REASONS)

    def test_the_reference_gives_the_tables_electrical_numbers_and_sources(self):
        text = REFERENCE.read_text(encoding="utf-8")
        section = text[text.index("## Electrical and magnetic"):text.index("## Strength, fatigue and heat")]
        rows = {}
        for line in section.splitlines():
            if match := re.match(r"\|\s*`([a-z0-9-]+)`", line):
                rows[match.group(1)] = [cell.strip() for cell in line.strip().strip("|").split("|")][1:]
        self.assertEqual(set(rows), set(MATERIALS))

        def number(cell: str):
            return None if cell.lower().startswith("none") else float(cell.split("(")[0])

        for key, material in MATERIALS.items():
            for column, attribute in enumerate(("resistivity", "permittivity", "permeability")):
                with self.subTest(material=key, property=attribute):
                    written, value = number(rows[key][column]), getattr(material, attribute)
                    self.assertEqual(written is None, value is None)
                    if value is not None:
                        self.assertAlmostEqual(written / value, 1.0, places=9)
            self.assertTrue(rows[key][3].strip(), "the sources column is empty")


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class SteadyCurrent(unittest.TestCase):
    """The bar: R = rho L / A to 1 %, the Joule heat I² R exactly, and the heat handed on to a thermal solve."""

    LENGTH, SIDE = 40.0, 4.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "bar.step"
        export_step(Box(cls.LENGTH, cls.SIDE, cls.SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(step))
        ends = planes_along(step, 0)
        cls.left, cls.right = ends[0.0], ends[cls.LENGTH]
        cls.study = {"analysis": "electromagnetic", "mode": "current", "material": "aluminum-6061-t6", "mesh": {"size_mm": 4.0},
                     "voltages": [{"faces": [cls.left], "V": 0.001, "name": "in"}, {"faces": [cls.right], "V": 0, "name": "out"}],
                     "electro_thermal": {"convection": [{"faces": [cls.left, cls.right], "h_W_m2K": 10, "ambient_C": 20}]},
                     "view": {"checks": [{"kind": "temperature", "max_C": 60}]}}
        cls.result = solve(step, directory / "bar.glb", cls.study)
        cls.extras, cls.attributes = glb(cls.result.glb, ("_POTENTIAL", "_CURRENT_DENSITY", "_TEMPERATURE"))
        # The same bar fed a current through one end instead (the other held at ground).
        cls.fed = solve(step, directory / "fed.glb", {
            "analysis": "electromagnetic", "mode": "current", "material": "aluminum-6061-t6", "mesh": {"size_mm": 4.0},
            "currents": [{"faces": [cls.left], "A": 10, "name": "in"}], "voltages": [{"faces": [cls.right], "V": 0, "name": "out"}]})
        cls.directory, cls.step = directory, step

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def resistance(self) -> float:
        return lookup_material("aluminum-6061-t6").resistivity * (self.LENGTH / 1000) / (self.SIDE / 1000) ** 2

    def test_the_resistance_is_rho_l_over_a(self):
        summary = self.result.summary
        self.assertEqual(summary["resistance_between"], ["in", "out"])
        self.assertAlmostEqual(summary["resistance_ohm"] / self.resistance(), 1.0, delta=0.01)
        self.assertAlmostEqual(self.fed.summary["resistance_ohm"] / self.resistance(), 1.0, delta=0.01)
        # The current fed in reads back at the ground: what goes in comes out.
        out = next(e for e in self.fed.summary["electrodes"] if e["name"] == "out")
        self.assertAlmostEqual(out["current_A"], -10.0, delta=1e-6)

    def test_the_joule_heat_is_i_squared_r_exactly(self):
        summary = self.result.summary
        current, resistance = summary["current_A"], summary["resistance_ohm"]
        self.assertAlmostEqual(summary["joule_heat_W"] / (current ** 2 * resistance), 1.0, places=5)
        self.assertAlmostEqual(summary["power_W"] / summary["joule_heat_W"], 1.0, places=5)
        # Uniform current: J = I / A everywhere.
        self.assertAlmostEqual(summary["max_current_density_A_mm2"] / (current / self.SIDE ** 2), 1.0, delta=0.01)

    def test_the_heat_goes_to_a_thermal_solve_one_way(self):
        summary = self.result.summary
        # Every watt leaves through the two cooled ends: T = T_air + P / (h A), the bar near one temperature.
        rise = summary["joule_heat_W"] / (10.0 * 2 * (self.SIDE / 1000) ** 2)
        self.assertAlmostEqual((summary["max_temperature_C"] - 20.0) / rise, 1.0, delta=0.01)
        self.assertLess(summary["heat_balance"], 0.01)
        check = summary["checks"][0]
        self.assertEqual((check["kind"], check["unit"], check["reference"]), ("temperature", "°C", 20.0))

    def test_the_glb_carries_its_fields_and_says_what_it_is(self):
        fields = {entry["field"]: entry for entry in self.extras["fields"]}
        self.assertEqual(list(fields), ["potential", "current_density", "temperature"])
        self.assertTrue(fields["potential"]["signed"])
        self.assertEqual(fields["current_density"]["units"], "A/mm²")
        analysis = self.extras["analysis"]
        self.assertEqual((analysis["type"], analysis["tier"], analysis["mode"], analysis["noun"]),
                         ("electromagnetic", 3, "current", "this current"))
        self.assertIn("no eddy currents", analysis["limits"][0])
        volts = [row[0] for row in self.attributes["_POTENTIAL"]]
        self.assertAlmostEqual(max(volts), 0.001, places=9)
        self.assertAlmostEqual(min(volts), 0.0, places=9)
        self.assertEqual(self.extras["study"]["voltages"][0], {"faces": [self.left], "V": 0.001, "name": "in"})
        self.assertIn("electro_thermal", self.extras["study"])

    def test_the_ladder_halves_it_twice_and_the_answer_holds(self):
        study = {**self.study, "fit": {"memory_GB": 0.01, "seconds": 0.001, "allow": ["symmetry"]}}
        study.pop("electro_thermal")
        study.pop("view")
        result = solve(self.step, self.directory / "quarter.glb", study)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("symmetry", rungs)
        words = next(step["words"] for step in result.fit if step["rung"] == "symmetry")
        self.assertIn("Solved one quarter of the part", words)
        self.assertAlmostEqual(result.summary["resistance_ohm"] / self.resistance(), 1.0, delta=0.01)
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertIn(words, [step["words"] for step in sidecar["fit"]])
        self.assertIn("fit_symmetry", [finding["type"] for finding in result.findings])
        extras, _ = glb(result.glb, ())
        self.assertIn(words, [step["words"] for step in extras["fit"]])


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class Electrostatics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build123d import Box, Compound, Cylinder, Pos, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        # A PETG slab with electrodes painted on its two faces.
        slab = directory / "slab.step"
        export_step(Box(20.0, 20.0, 2.0), str(slab))
        zs = planes_along(slab, 2)
        cls.slab = solve(slab, directory / "slab.glb", {
            "analysis": "electromagnetic", "mode": "electrostatic", "material": "petg", "mesh": {"size_mm": 2.0},
            "voltages": [{"faces": [zs[1.0]], "V": 1000, "name": "top"}, {"faces": [zs[-1.0]], "V": 0, "name": "bottom"}],
            "view": {"checks": [{"kind": "electric_field", "limit_kV_mm": 3}, {"kind": "electric_field", "limit_kV_mm": 0.4}]}})
        # Two aluminium plates in air: the upper one a centre electrode inside a guard cup at its voltage.
        gap, radius, slot, outer, thick = 2.0, 10.0, 0.5, 16.0, 1.0
        cup = thick + slot + thick
        centre = Pos(0, 0, gap / 2 + thick / 2) * Cylinder(radius, thick)
        centre.label = "centre"
        guard = Pos(0, 0, gap / 2 + cup / 2) * (Cylinder(outer, cup) - Pos(0, 0, -cup / 2 + (thick + slot) / 2) * Cylinder(radius + slot, thick + slot))
        guard.label = "guard"
        bottom = Pos(0, 0, -gap / 2 - thick / 2) * Cylinder(outer, thick)
        bottom.label = "bottom"
        plates = directory / "plates.step"
        export_step(Compound(children=[centre, guard, bottom]), str(plates))
        under = {occurrence: planes_along(plates, 2, occurrence) for occurrence in ("#o1.1", "#o1.2", "#o1.3")}
        cls.reference_pF = EPS0_F_M * math.pi * ((radius + slot / 2) / 1000) ** 2 / (gap / 1000) * 1e12
        cls.plates = solve(plates, directory / "plates.glb", {
            "analysis": "electromagnetic", "mode": "electrostatic", "material": "aluminum-6061-t6", "mesh": {"size_mm": 1.5},
            "air": {"around_mm": 8},
            "voltages": [{"faces": [under["#o1.1"][gap / 2]], "V": 100, "name": "centre"},
                         {"faces": [under["#o1.2"][gap / 2]], "V": 100, "name": "guard"},
                         {"faces": [under["#o1.3"][-gap / 2]], "V": 0, "name": "bottom"}],
            "capacitance": {"between": ["centre", "bottom"]},
            "probes": [{"at_mm": [0, 0, 0], "label": "gap"}],
            # A small budget: the air is coarsened away from the plates to fit (the ladder's air rung).
            "fit": {"memory_GB": 0.01, "seconds": 0.001}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_slab_holds_eps_a_over_d(self):
        expected = EPS0_F_M * 2.6 * (0.02 ** 2) / 0.002 * 1e12
        summary = self.slab.summary
        self.assertAlmostEqual(summary["capacitance_pF"] / expected, 1.0, delta=0.001)
        self.assertAlmostEqual(summary["max_field_kV_mm"], 0.5, delta=0.005)   # 1000 V over 2 mm
        # The energy is C V² / 2, and the charges are equal and opposite.
        self.assertAlmostEqual(summary["energy_J"] / (0.5 * expected * 1e-12 * 1000 ** 2), 1.0, delta=0.001)
        top, bottom = summary["electrodes"]
        self.assertAlmostEqual(top["charge_nC"], -bottom["charge_nC"], delta=1e-6 * abs(top["charge_nC"]))

    def test_the_electric_field_check_says_whether_it_holds_the_voltage(self):
        holds, arcs = self.slab.summary["checks"]
        self.assertEqual((holds["kind"], holds["label"], holds["unit"], holds["status"]), ("electric_field", "Arcing", "kV/mm", "passes"))
        self.assertAlmostEqual(holds["ratio"], 0.5 / 3, delta=0.002)
        self.assertEqual(arcs["status"], "fails")
        finding = next(f for f in self.slab.findings if f["type"] == "electric_field_over_limit")
        self.assertIn("it would arc over", finding["summary"])

    def test_a_guard_ring_capacitor_in_air_holds_eps_a_over_d(self):
        summary = self.plates.summary
        self.assertAlmostEqual(summary["capacitance_pF"] / self.reference_pF, 1.0, delta=0.03)
        self.assertEqual(summary["capacitance_between"], ["centre", "bottom"])
        probe = summary["probes"][0]
        self.assertAlmostEqual(probe["V"], 50.0, delta=1.0)                     # half way across the gap
        self.assertAlmostEqual(probe["electric_field_kV_mm"], 0.05, delta=0.002)  # 100 V over 2 mm
        self.assertTrue(summary["air"])
        self.assertGreater(summary["region"]["elements"], 0)

    def test_the_air_is_coarsened_to_fit_and_says_so(self):
        step = next(step for step in self.plates.fit if step["rung"] == "fluid_coarsen")
        self.assertIn("Coarsened the air away from the parts to fit", step["words"])
        self.assertIn("still meshed at 1.5 mm", step["words"])
        self.assertIsNotNone(step["accuracy"])
        self.assertGreater(self.plates.summary["region"]["air_mm"], 4.5)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class Magnetostatics(unittest.TestCase):
    A1, A2, B = 8.0, 10.0, 2.0

    @classmethod
    def setUpClass(cls):
        from build123d import Compound, Cylinder, Pos, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        coil = directory / "coil.step"
        export_step(Cylinder(cls.A2, 2 * cls.B) - Cylinder(cls.A1, 2 * cls.B), str(coil))
        cls.coil = solve(coil, directory / "coil.glb", {
            "analysis": "electromagnetic", "mode": "magnetostatic", "material": "aluminum-6061-t6", "mesh": {"size_mm": 1.0},
            "coils": [{"turns": 100, "A": 2, "axis": {"direction": [0, 0, 1], "point_mm": [0, 0, 0]}}],
            "probes": [{"at_mm": [0, 0, 0], "label": "centre"}]})
        cls.extras, cls.attributes = glb(cls.coil.glb, ("_MAGNETIC_FIELD",))
        lower = Pos(0, 0, -3) * (Cylinder(cls.A2, 2) - Cylinder(cls.A1, 2))
        lower.label = "lower"
        upper = Pos(0, 0, 3) * (Cylinder(cls.A2, 2) - Cylinder(cls.A1, 2))
        upper.label = "upper"
        pair = directory / "pair.step"
        export_step(Compound(children=[lower, upper]), str(pair))
        top = planes_along(pair, 2, "#o1.2")[4.0]
        cls.pair = solve(pair, directory / "pair.glb", {
            "analysis": "electromagnetic", "mode": "magnetostatic", "material": "aluminum-6061-t6", "mesh": {"size_mm": 1.5},
            "coils": [{"part": "lower", "turns": 100, "A": 5, "axis": {"direction": [0, 0, 1]}},
                      {"part": "upper", "turns": 100, "A": 5, "axis": {"direction": [0, 0, 1]}}],
            "map_to_structure": {"part": "upper", "fixtures": [{"faces": [top]}]},
            "view": {"checks": [{"kind": "stress"}]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_field_at_a_coils_centre_is_biot_savarts(self):
        a1, a2, b = self.A1 / 1000, self.A2 / 1000, self.B / 1000
        J = 100 * 2 / ((a2 - a1) * 2 * b)
        expected_mT = MU0_H_M * J * b * math.log((a2 + math.hypot(a2, b)) / (a1 + math.hypot(a1, b))) * 1e3
        probe = self.coil.summary["probes"][0]
        self.assertAlmostEqual(probe["magnetic_field_mT"] / expected_mT, 1.0, delta=0.05)
        self.assertGreater(probe["B_mT"][2], 0)            # right-handed about +Z: the field points up the axis
        coil = self.coil.summary["coils"][0]
        self.assertAlmostEqual(coil["section_mm2"], 8.0, delta=0.08)   # (1/2 pi) ∫ dV / r over the ring
        self.assertEqual(coil["ampere_turns"], 200)

    def test_a_lone_coil_feels_no_net_force_and_stores_l_i_squared_over_two(self):
        summary = self.coil.summary
        force = summary["forces"][0]
        self.assertEqual(force["by"], "J x B")
        self.assertLess(math.hypot(*force["force_N"]), 1e-3)
        self.assertAlmostEqual(summary["inductance_uH"] * 1e-6 * 2 ** 2 / 2 / summary["energy_J"], 1.0, places=4)

    def test_the_glb_carries_the_magnetic_field_on_the_coil(self):
        fields = [entry["field"] for entry in self.extras["fields"]]
        self.assertEqual(fields, ["magnetic_field"])
        self.assertEqual(self.extras["fields"][0]["units"], "mT")
        self.assertGreater(max(row[0] for row in self.attributes["_MAGNETIC_FIELD"]), 0.0)
        self.assertEqual(self.extras["analysis"]["mode"], "magnetostatic")

    def test_two_coils_pull_together_by_the_biot_savart_force(self):
        import numpy as np

        # The Biot-Savart force of the lower coil on the upper, each a 6 x 6 grid of filaments of 500/36 ampere-turns.
        def filaments(z0):
            return [(r, z) for r in np.linspace(8 + 1 / 6, 10 - 1 / 6, 6) for z in np.linspace(z0 - 5 / 6, z0 + 5 / 6, 6)]

        theta = np.linspace(0, 2 * np.pi, 240, endpoint=False)
        step = theta[1] - theta[0]
        current = 500 / 36
        force = 0.0
        for r1, z1 in filaments(-3):
            points = np.stack([r1 * np.cos(theta), r1 * np.sin(theta), np.full_like(theta, z1)], 1) * 1e-3
            dl = np.stack([-np.sin(theta), np.cos(theta), 0 * theta], 1) * r1 * step * 1e-3
            for r2, z2 in filaments(3):
                gap = np.array([r2, 0, z2]) * 1e-3 - points
                field = (MU0_H_M * current / (4 * np.pi) * np.cross(dl, gap) / np.linalg.norm(gap, axis=1)[:, None] ** 3).sum(0)
                force += current * np.cross(np.array([0, 1, 0]) * 2 * np.pi * r2 * 1e-3, field)[2]
        forces = {f["part"]: f["force_N"] for f in self.pair.summary["forces"]}
        self.assertLess(force, 0)                                         # the upper coil is pulled down
        self.assertAlmostEqual(forces["upper"][2] / force, 1.0, delta=0.05)
        self.assertAlmostEqual(-forces["lower"][2] / force, 1.0, delta=0.05)

    def test_the_force_is_handed_to_a_static_solve(self):
        summary = self.pair.summary
        self.assertEqual(summary["structure"]["part"], "upper")
        check = summary["checks"][0]
        self.assertEqual((check["kind"], check["status"]), ("stress", "passes"))
        self.assertGreater(summary["structure"]["max_von_mises_MPa"], 0.0)
        extras, _ = glb(self.pair.glb, ())
        self.assertEqual([entry["field"] for entry in extras["fields"]], ["magnetic_field", "von_mises", "displacement"])


if __name__ == "__main__":
    unittest.main()
