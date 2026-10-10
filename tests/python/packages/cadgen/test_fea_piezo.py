"""Piezo (`"analysis": "piezo"`): the study it reads, its ceramics' constants, and textbook answers per solve.

Hand checks, each from the material's own constants (piezo_ops.one_d_constants: s^E = c^E⁻¹, d = e s^E,
eps^T = eps^S + d eᵀ, c33^D = c33^E + e33² / eps33^S, k_t² = e33² / (c33^D eps33^S)):

- A free PZT-5A plate (A = 4 x 4 mm, t = 1 mm) held only by rollers that let it grow every way: its
  capacitance is eps33^T A / t, its thickness changes by d33 V, and held between two rollers (thickness
  blocked, sides free) it pushes with F = d33 V A / (s33^E t) (the 1D reduced constants d33 and s33^E: T1 = T2 = 0,
  S3 = 0). Compressed by F with the top electrode open, it reads V = g33 F t / A (g33 = d33 / eps33^T).
- A laterally clamped column (S1 = S2 = 0, the 1D thickness mode): anti-resonance fa = sqrt(c33^D / rho) / 2t,
  resonance fr from k_t² = (π/2)(fr/fa) tan((π/2)(fa − fr)/fa) (IEEE Std 176), k_t from the pair, and its blocked
  capacitance eps33^S A / t.
- A series bimorph cantilever (two equal layers poled opposite ways, L = 20 mm, each h = 0.25 mm thick):
  the uniform-field closed form δ = 3 d31 V L² / (2 t²) (t = 2h). With the coupling made weak (eps^S x 100,
  d31 unchanged) the uniform-field assumption holds and the solve must meet it within 10 %. With PZT-5A's own
  coupling the bending strain makes a field of its own inside each layer, stiffening its own bending to the
  open-circuit biaxial compliance (s11 + s12)(1 − kp²): the curvature becomes
  κ = ε0 / (h (1/2 + r/6)), r = 1 / (1 − kp²), ε0 = d31 V / t: the closed form times (2/3) / (1/2 + r/6). The
  solve must meet that within 5 % (and is about 11 % under the uniform-field formula, which ignores it).
- A driven sweep at low frequency draws the static capacitance's current: |Y| = ω C.

Each STEP is a build123d solid in a temporary directory; meshes are coarse.
"""

from __future__ import annotations

import io
import json
import math
import re
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.materials import PIEZO_MATERIALS, material_from_spec  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

REFERENCE = Path(__file__).resolve().parents[4] / "skills" / "fea" / "references" / "materials.md"
EPS0_F_M = 8.8541878128e-12
#: TP-226 section III's own derived values, which the stiffness, coupling and permittivity it lists must reproduce:
#: d33, d31 (1e-12 m/V), k_t, k33, eps33^T / eps0.
TP226 = {"pzt-4": (289, -123, 0.513, 0.70, 1300), "pzt-5a": (374, -171, 0.486, 0.705, 1700),
         "pzt-5h": (593, -274, 0.505, 0.752, 3400)}


def parse(document: dict):
    from cadgen._internal.fea.study import parse_study

    return parse_study({"analysis": "piezo", "material": "pzt-5a", **document})


ELECTRODES = [{"faces": ["#o1.f6"], "V": 100, "name": "top"}, {"faces": ["#o1.f5"], "V": 0, "name": "bottom"}]


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


def plane(step: Path, axis: int, at: float, occurrence: str | None = None) -> str:
    """The plane face square to ``axis`` at ``at``."""
    from cadgen import fea

    return next(face.ref for face in fea.faces(step, occurrence=occurrence).faces
                if face.surface == "plane" and face.normal and abs(abs(face.normal[axis]) - 1) < 1e-6
                and abs(face.center_mm[axis] - at) < 1e-6)


def constants(name: str) -> dict:
    from cadgen._internal.fea import piezo_ops

    return piezo_ops.one_d_constants(PIEZO_MATERIALS[name].piezo)


class StudyFile(unittest.TestCase):
    def test_it_is_built_and_registered(self):
        from cadgen._internal.fea.analyses import REGISTRY, get_analysis

        self.assertEqual((REGISTRY["piezo"].tier, REGISTRY["piezo"].word, REGISTRY["piezo"].planned), (3, "Piezo", False))
        self.assertEqual(get_analysis("piezo").word, "Piezo")

    def test_each_solve_reads_its_own_keys_and_writes_its_own_fields(self):
        from cadgen._internal.fea.analyses import get_analysis

        analysis = get_analysis("piezo")
        static = parse({"electrodes": ELECTRODES, "fixtures": [{"faces": ["#o1.f5"]}],
                        "view": {"checks": [{"kind": "displacement", "limit_mm": 0.01}]}})
        self.assertEqual((static.inputs.solve, [e.volts for e in static.inputs.electrodes]), ("static", [100.0, 0.0]))
        self.assertEqual([f.name for f in analysis.fields], ["von_mises", "potential", "electric_field", "displacement"])
        resonance = parse({"solve": "resonance", "modes": 4, "electrodes": ELECTRODES})
        self.assertEqual((resonance.inputs.modes, resonance.inputs.fixtures, resonance.inputs.requires_anchor), (4, (), False))
        self.assertEqual([f.name for f in analysis.fields], ["mode_shape", "von_mises", "potential"])
        sensing = parse({"solve": "harmonic", "sweep_Hz": [100, 10000], "damping_ratio": 0.02, "fixtures": [{"faces": ["#o1.f5"]}],
                         "electrodes": [{"faces": ["#o1.f6"], "open": True, "name": "out"}, {"faces": ["#o1.f5"], "V": 1}],
                         "view": {"checks": [{"kind": "voltage", "min_V": 0.5}]}})
        self.assertEqual(sensing.checks[0], {"kind": "voltage", "min_V": 0.5})
        self.assertEqual((sensing.inputs.open[0].name, sensing.inputs.sweep_Hz, sensing.inputs.material_needs),
                         ("out", (100.0, 10000.0), frozenset({"density"})))

    def test_the_errors_name_the_field_in_plain_words(self):
        held = {"fixtures": [{"faces": ["#o1.f5"]}]}
        cases = [
            ({"solve": "quasi"}, 'solve: "quasi" is not one of'),
            ({**held}, "electrodes: a piezo study needs its electrodes"),
            ({**held, "electrodes": [{"faces": ["#o1.f6"]}]}, "give V (the voltage it is held at"),
            ({**held, "electrodes": [{"faces": ["#o1.f6"], "open": True}]}, "hold at least one electrode at a voltage"),
            ({"electrodes": ELECTRODES}, "fixtures"),
            ({"solve": "resonance", "electrodes": [{"faces": ["#o1.f6"], "V": 1}]}, "needs a ground"),
            ({"solve": "resonance", "electrodes": [{"faces": ["#o1.f6"], "V": 0}]}, "nothing opens at anti-resonance"),
            ({"solve": "resonance", "loads": [], "electrodes": ELECTRODES}, "loads is not for a resonance piezo study"),
            ({**held, "solve": "harmonic", "electrodes": ELECTRODES}, "sweep_Hz: the band"),
            ({**held, "electrodes": ELECTRODES, "view": {"checks": [{"kind": "voltage", "min_V": 1}]}}, "reads an open electrode"),
            ({**held, "electrodes": ELECTRODES, "view": {"checks": [{"kind": "frequency", "min_Hz": 1}]}},
             "a frequency check is not for a static piezo study"),
            ({**held, "electrodes": ELECTRODES, "material": "steel"}, "needs a piezo ceramic in at least one part"),
            ({**held, "electrodes": ELECTRODES, "view": {"checks": [{"kind": "stress"}]}}, "add yield_MPa"),
        ]
        for changes, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse(changes)
            self.assertIn(fragment, str(caught.exception))


class Ceramics(unittest.TestCase):
    def test_the_tables_constants_reproduce_tp226s_own_derived_values(self):
        for name, (d33, d31, kt, k33, eps33T) in TP226.items():
            c = constants(name)
            with self.subTest(material=name):
                self.assertAlmostEqual(c["d33"] * 1e12 / d33, 1.0, delta=0.02)
                self.assertAlmostEqual(c["d31"] * 1e12 / d31, 1.0, delta=0.02)
                self.assertAlmostEqual(c["kt"] / kt, 1.0, delta=0.02)
                self.assertAlmostEqual(c["k33"] / k33, 1.0, delta=0.02)
                self.assertAlmostEqual(c["epsT"][2, 2] / EPS0_F_M / eps33T, 1.0, delta=0.02)

    def test_the_reference_lists_every_constant_with_its_source(self):
        text = REFERENCE.read_text(encoding="utf-8")
        section = text[text.index("## Piezoelectric ceramics"):]
        section = section[:section.index("\n## ", 4)]
        self.assertIn("TP-226", section)
        for key, material in PIEZO_MATERIALS.items():
            row = next(line for line in section.splitlines() if f"(`{key}`)" in line)
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")][1:]
            block = material.piezo
            c, e, eps = block["cE_GPa"], block["e_C_m2"], block["epsS_rel"]
            expected = [c[0][0], c[0][1], c[0][2], c[2][2], c[3][3], c[5][5], e[2][0], e[2][2], e[0][4], eps[0][0], eps[2][2],
                        block["density_kg_m3"]]
            with self.subTest(material=key):
                self.assertEqual([float(cell.replace("−", "-")) for cell in cells[:12]], expected)
                self.assertTrue(cells[12], "the sources column is empty")

    def test_a_ceramic_is_named_turned_over_or_given_in_full(self):
        upside = material_from_spec({"name": "pzt-4", "piezo": {"poling": [0, 0, -2]}})
        self.assertEqual(upside.piezo["poling"], [0.0, 0.0, -1.0])
        self.assertEqual(upside.piezo["cE_GPa"], PIEZO_MATERIALS["pzt-4"].piezo["cE_GPa"])
        self.assertIsNone(upside.yield_strength)
        own = material_from_spec({"name": "my ceramic", "piezo": {k: PIEZO_MATERIALS["pzt-5h"].piezo[k]
                                                                   for k in ("cE_GPa", "e_C_m2", "epsS_rel")},
                                  "density_t_per_mm3": 7.5e-9})
        self.assertAlmostEqual(own.E, PIEZO_MATERIALS["pzt-5h"].E)
        bad = [row[:] for row in PIEZO_MATERIALS["pzt-5a"].piezo["cE_GPa"]]
        bad[0][1] = 1.0
        cases = [({"name": "x", "piezo": {"poling": [0, 0, 1]}}, "a piezo material needs cE_GPa"),
                 ({"name": "pzt-5a", "piezo": {"cE_GPa": bad}}, "must be symmetric"),
                 ({"name": "pzt-5a", "piezo": {"epsS_rel": [[1, 0, 0], [0, -1, 0], [0, 0, 1]]}}, "positive definite"),
                 ({"name": "pzt-5a", "piezo": {"d33": 1}}, "unknown keys ['d33']")]
        for spec, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                material_from_spec(spec)
            self.assertIn(fragment, str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class CoupledSolver(unittest.TestCase):
    def test_minres_with_block_multigrid_agrees_with_the_direct_solve(self):
        import numpy as np
        from skfem import MeshTet

        from cadgen._internal.fea import piezo_ops
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.supports import Supports

        mesh = MeshTet.init_tensor(*(np.linspace(0.0, size, count + 1) for size, count in ((4.0, 6), (4.0, 6), (1.0, 3))))
        space = FemSpace.from_mesh(mesh, order=1)
        part = PIEZO_MATERIALS["pzt-5a"]
        c, e, eps = piezo_ops.global_constants(part.piezo)
        matrices = piezo_ops.assemble(space, [piezo_ops.PartConstants("piezo", c, part.density, e, eps)])
        z = space.dof_locations[:, 2]
        bottom_vector = np.flatnonzero(np.isclose(space.locations[:, 2], 0.0))
        supports = Supports(fixed=bottom_vector, per_fixture=[bottom_vector])
        electrodes = [piezo_ops.Electrode("top", np.flatnonzero(np.isclose(z, 1.0)), 50.0),
                      piezo_ops.Electrode("bottom", np.flatnonzero(np.isclose(z, 0.0)), 0.0)]
        system = piezo_ops.System(space, matrices, supports, electrodes)
        f = np.zeros(space.basis.N)
        direct, _ = system.solve_static(f)
        iterative, how = system.solve_static(f, iterative=True)
        self.assertIn("minres", how)
        self.assertLess(np.abs(iterative.u - direct.u).max(), 1e-6 * np.abs(direct.u).max())
        self.assertAlmostEqual(iterative.charges[0] / direct.charges[0], 1.0, delta=1e-6)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class Plate(unittest.TestCase):
    """A free PZT-5A plate: capacitance, free stroke, blocked force and the open-circuit voltage of a sensor."""

    A, T, V, F = 4.0, 1.0, 100.0, 10.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        step = cls.dir / "plate.step"
        export_step(Box(cls.A, cls.A, cls.T, align=(Align.MIN, Align.MIN, Align.MIN)), str(step))
        cls.step = step
        cls.x0, cls.y0, cls.z0, cls.z1 = plane(step, 0, 0), plane(step, 1, 0), plane(step, 2, 0), plane(step, 2, cls.T)
        cls.c = constants("pzt-5a")
        # +V on the bottom: the field along the poling (+Z), so the plate grows by d33 V.
        base = {"analysis": "piezo", "material": "pzt-5a", "mesh": {"size_mm": 0.5},
                "electrodes": [{"faces": [cls.z0], "V": cls.V, "name": "drive"}, {"faces": [cls.z1], "V": 0, "name": "ground"}]}
        free = [{"faces": [cls.z0, cls.x0, cls.y0], "type": "roller"}]
        cls.free = solve(step, cls.dir / "free.glb", {**base, "fixtures": free})
        cls.blocked = solve(step, cls.dir / "blocked.glb", {**base, "fixtures": [*free, {"faces": [cls.z1], "type": "roller"}]})
        cls.sensor = solve(step, cls.dir / "sensor.glb", {
            **base, "electrodes": [{"faces": [cls.z1], "open": True, "name": "out"}, {"faces": [cls.z0], "V": 0, "name": "ground"}],
            "fixtures": free, "loads": [{"faces": [cls.z1], "type": "force", "vector_N": [0, 0, -cls.F]}],
            "view": {"checks": [{"kind": "voltage", "min_V": 10, "label": "Sensor output"}]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_capacitance_is_eps33T_A_over_t(self):
        expected = self.c["epsT"][2, 2] * (self.A * 1e-3) ** 2 / (self.T * 1e-3)
        print(f"\npiezo plate capacitance {self.free.summary['capacitance_F']:.6g} F, eps33T A/t {expected:.6g} F")
        self.assertAlmostEqual(self.free.summary["capacitance_F"] / expected, 1.0, delta=0.02)
        drive, ground = self.free.summary["electrodes"]
        self.assertAlmostEqual(drive["charge_C"], -ground["charge_C"], delta=1e-6 * abs(drive["charge_C"]))

    def test_the_free_stroke_is_d33_V(self):
        stroke = self.free.summary["electrodes"][1]["mean_displacement_mm"][2]
        expected = self.c["d33"] * self.V * 1e3
        print(f"piezo free stroke {stroke:.6g} mm, d33 V {expected:.6g} mm")
        self.assertAlmostEqual(stroke / expected, 1.0, delta=0.02)

    def test_the_blocked_force_is_d33_V_A_over_s33E_t(self):
        force = self.blocked.summary["reaction_force_N"][1][2]
        expected = self.c["d33"] * self.V / (self.T * 1e-3) / self.c["s33E"] * (self.A * 1e-3) ** 2
        print(f"piezo blocked force {force:.6g} N, d33 V A / (s33E t) {expected:.6g} N")
        self.assertAlmostEqual(abs(force) / expected, 1.0, delta=0.02)

    def test_a_pressed_sensor_reads_g33_F_t_over_A_on_its_open_electrode(self):
        out = self.sensor.summary["electrodes"][0]
        expected = self.c["g33"] * self.F / (self.A * 1e-3) ** 2 * self.T * 1e-3
        print(f"piezo open-circuit voltage {out['V']:.6g} V, g33 F t / A {expected:.6g} V")
        self.assertTrue(out["open"])
        self.assertAlmostEqual(abs(out["V"]) / expected, 1.0, delta=0.02)
        self.assertLess(abs(out["charge_C"]), 1e-12)
        check = self.sensor.summary["checks"][0]
        self.assertEqual((check["kind"], check["label"], check["unit"], check["status"], check["electrode"]),
                         ("voltage", "Sensor output", "V", "passes", "out"))
        self.assertAlmostEqual(check["ratio"], 10 / check["value"], places=5)

    def test_the_glb_and_sidecar_say_piezo_with_voltage_and_stress(self):
        sidecar = json.loads(self.free.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["analysis"], "piezo")
        self.assertEqual([f["field"] for f in sidecar["fields"]], ["von_mises", "potential", "electric_field", "displacement"])
        potential = next(f for f in sidecar["fields"] if f["field"] == "potential")
        self.assertEqual((potential["signed"], potential["min"], potential["max"]), (True, 0.0, 100.0))
        self.assertEqual(sidecar["study"]["analysis"], "piezo")
        self.assertEqual(self.free.summary["poling"][0]["direction"], [0.0, 0.0, 1.0])
        self.assertTrue(any(line.startswith("capacitance") for line in self.free.human_lines()))


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class ThicknessMode(unittest.TestCase):
    """A laterally clamped PZT-5A column: the 1D thickness mode's fr, fa and k_t, and its blocked capacitance."""

    A, T = 0.4, 1.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "column.step"
        export_step(Box(cls.A, cls.A, cls.T, align=(Align.MIN, Align.MIN, Align.MIN)), str(step))
        sides = [plane(step, 0, 0), plane(step, 0, cls.A), plane(step, 1, 0), plane(step, 1, cls.A)]
        cls.top, cls.bottom = plane(step, 2, cls.T), plane(step, 2, 0)
        electrodes = [{"faces": [cls.top], "V": 1, "name": "top"}, {"faces": [cls.bottom], "V": 0, "name": "bottom"}]
        cls.study = {"analysis": "piezo", "solve": "resonance", "material": "pzt-5a", "mesh": {"size_mm": 0.2}, "modes": 3,
                     "electrodes": electrodes, "fixtures": [{"faces": sides, "type": "roller"}],
                     "view": {"checks": [{"kind": "frequency", "min_Hz": 1e6}]}}
        cls.step, cls.dir = step, directory
        cls.result = solve(step, directory / "column.glb", cls.study)
        # Driven over a band, with the bottom held too: at low frequency it draws the static capacitance's current.
        held = {"faces": [*sides, cls.bottom], "type": "roller"}
        sweep = {**{k: v for k, v in cls.study.items() if k not in ("modes", "view")}, "solve": "harmonic", "fixtures": [held],
                 "sweep_Hz": [10000, 2000000], "points": 10, "damping_ratio": 0.02}
        cls.static = solve(step, directory / "static.glb", {**{k: v for k, v in sweep.items() if k not in ("sweep_Hz", "points",
                                                                                                         "damping_ratio")},
                                                            "solve": "static"})
        cls.sweep = solve(step, directory / "sweep.glb", sweep)
        cls.by_modes = solve(step, directory / "modes.glb", {**sweep, "fit": {"memory_GB": 0.0001, "seconds": 0.001,
                                                                              "allow": ["reduce_modes"]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def theory(self):
        from scipy.optimize import brentq

        c = constants("pzt-5a")
        rho = PIEZO_MATERIALS["pzt-5a"].piezo["density_kg_m3"]
        fa = math.sqrt(c["c33D"] / rho) / (2 * self.T * 1e-3)
        fr = brentq(lambda f: 0.5 * math.pi * (f / fa) * math.tan(0.5 * math.pi * (fa - f) / fa) - c["kt"] ** 2,
                    0.3 * fa, fa * (1 - 1e-12))
        return fr, fa, c

    def test_resonance_and_anti_resonance_meet_the_1d_thickness_mode(self):
        fr, fa, c = self.theory()
        mode = self.result.summary["modes"][0]
        print(f"\npiezo thickness mode fr {mode['resonance_Hz']:.6g} Hz (1D {fr:.6g}), fa {mode['antiresonance_Hz']:.6g} Hz "
              f"(1D {fa:.6g}), k_eff {mode['k_eff']:.4f}")
        self.assertAlmostEqual(mode["resonance_Hz"] / fr, 1.0, delta=0.05)
        self.assertAlmostEqual(mode["antiresonance_Hz"] / fa, 1.0, delta=0.05)
        self.assertAlmostEqual(mode["k_eff2"], (mode["antiresonance_Hz"] ** 2 - mode["resonance_Hz"] ** 2)
                               / mode["antiresonance_Hz"] ** 2, delta=1e-5)
        self.assertEqual(self.result.summary["rigid_body_modes"], 1)   # it slides along its rollers
        self.assertEqual(self.result.summary["checks"][0]["status"], "passes")

    def test_k_t_from_the_pair_is_the_constants_k_t(self):
        from cadgen._internal.fea import piezo_ops

        _, _, c = self.theory()
        mode = self.result.summary["modes"][0]
        kt = piezo_ops.thickness_kt(mode["resonance_Hz"], mode["antiresonance_Hz"])
        print(f"piezo k_t from fr, fa {kt:.5f}, from the constants {c['kt']:.5f}")
        self.assertAlmostEqual(kt / c["kt"], 1.0, delta=0.05)

    def test_the_blocked_capacitance_is_eps33S_A_over_t(self):
        _, _, c = self.theory()
        expected = c["epsS"][2, 2] * (self.A * 1e-3) ** 2 / (self.T * 1e-3)
        self.assertAlmostEqual(self.result.summary["blocked_capacitance_F"] / expected, 1.0, delta=0.02)

    def test_the_glb_carries_each_modes_shape_voltage_and_stress(self):
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        frames = sidecar["series"]["frames"]
        self.assertEqual(sidecar["series"]["kind"], "mode")
        self.assertEqual(frames[1]["attributes"], {"mode_shape": "_MODE_SHAPE_F1", "von_mises": "_VON_MISES_F1",
                                                   "potential": "_POTENTIAL_F1"})
        self.assertTrue(frames[0]["label"].startswith("Mode 1 · 1.9"))

    def test_a_sweep_draws_omega_C_at_low_frequency_and_by_modes_agrees(self):
        capacitance = self.static.summary["capacitance_F"]
        curves = json.loads(self.sweep.sidecar.read_text(encoding="utf-8"))["curves"]
        first = curves["admittance_S"]["x"][0], curves["admittance_S"]["y"][0]
        print(f"piezo admittance at {first[0]:.4g} Hz {first[1]:.6g} S, omega C {2 * math.pi * first[0] * capacitance:.6g} S")
        self.assertAlmostEqual(first[1] / (2 * math.pi * first[0] * capacitance), 1.0, delta=0.02)
        self.assertEqual((self.sweep.summary["method"], self.by_modes.summary["method"]), ("direct", "modes"))
        self.assertIn("reduce_modes", [step["rung"] for step in self.by_modes.fit])
        self.assertAlmostEqual(self.by_modes.summary["peak_admittance_S"] / self.sweep.summary["peak_admittance_S"], 1.0,
                               delta=0.02)
        self.assertEqual(self.by_modes.summary["peak_admittance_Hz"], self.sweep.summary["peak_admittance_Hz"])


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class Bimorph(unittest.TestCase):
    """A series bimorph cantilever: two PZT-5A layers poled opposite ways, glued, held at one end."""

    L, W, H, V = 20.0, 2.0, 0.25, 10.0

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, Compound, Pos, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        upper = Pos(0, 0, cls.H) * Box(cls.L, cls.W, cls.H, align=(Align.MIN, Align.MIN, Align.MIN))
        upper.label = "upper"
        lower = Box(cls.L, cls.W, cls.H, align=(Align.MIN, Align.MIN, Align.MIN))
        lower.label = "lower"
        step = directory / "bimorph.step"
        export_step(Compound(children=[upper, lower]), str(step))
        tip = [plane(step, 0, cls.L, "#o1.1"), plane(step, 0, cls.L, "#o1.2")]
        cls.study = {"analysis": "piezo", "material": "pzt-5a", "mesh": {"size_mm": 0.5},
                     "electrodes": [{"faces": [plane(step, 2, 2 * cls.H, "#o1.1")], "V": cls.V, "name": "top"},
                                    {"faces": [plane(step, 2, 0, "#o1.2")], "V": 0, "name": "bottom"}],
                     "fixtures": [{"faces": [plane(step, 0, 0, "#o1.1"), plane(step, 0, 0, "#o1.2")]}],
                     "view": {"checks": [{"kind": "displacement", "limit_mm": 1, "faces": tip}]}}

        def parts(**block):
            return {"upper": {"material": {"name": "pzt-5a", "piezo": {"poling": [0, 0, 1], **block}}},
                    "lower": {"material": {"name": "pzt-5a", "piezo": {"poling": [0, 0, -1], **block}}}}

        cls.real = solve(step, directory / "real.glb", {**cls.study, "parts": parts()})
        cls.weak_eps = [[916e2, 0, 0], [0, 916e2, 0], [0, 0, 830e2]]
        cls.weak = solve(step, directory / "weak.glb", {**cls.study, "parts": parts(epsS_rel=cls.weak_eps)})
        cls._tmp_dir = directory

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def closed_form(self, d31: float) -> float:
        """δ = 3 d31 V L² / (2 t²), mm."""
        t = 2 * self.H * 1e-3
        return 3 * abs(d31) * self.V * (self.L * 1e-3) ** 2 / (2 * t ** 2) * 1e3

    def test_with_weak_coupling_the_tip_meets_the_closed_form(self):
        from cadgen._internal.fea import piezo_ops

        block = dict(PIEZO_MATERIALS["pzt-5a"].piezo, epsS_rel=self.weak_eps)
        expected = self.closed_form(piezo_ops.one_d_constants(block)["d31"])
        tip = self.weak.summary["checks"][0]["value"]
        print(f"\npiezo bimorph (weak coupling) tip {tip:.6g} mm, 3 d31 V L²/(2t²) {expected:.6g} mm")
        self.assertAlmostEqual(tip / expected, 1.0, delta=0.10)

    def test_with_pzt5as_coupling_the_tip_meets_the_coupled_closed_form(self):
        c = constants("pzt-5a")
        s = c["sE"]
        kp2 = 2 * c["d31"] ** 2 / ((s[0, 0] + s[0, 1]) * c["epsT"][2, 2])
        r = 1 / (1 - kp2)
        uniform = self.closed_form(c["d31"])
        coupled = uniform * (2 / 3) / (0.5 + r / 6)
        tip = self.real.summary["checks"][0]["value"]
        print(f"piezo bimorph (PZT-5A) tip {tip:.6g} mm, coupled closed form {coupled:.6g} mm, uniform-field "
              f"{uniform:.6g} mm ({100 * (tip / uniform - 1):+.1f} %)")
        self.assertAlmostEqual(tip / coupled, 1.0, delta=0.05)
        self.assertEqual(len(self.real.summary["poling"]), 2)


@unittest.skipUnless(HAVE_FEA, "needs the [fea] extra")
class Ladder(unittest.TestCase):
    """Never refused for size: a tiny budget takes the symmetric quarter and local refinement, and the answer holds."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "disc.step"
        export_step(Box(4.0, 4.0, 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(step))
        top, bottom = plane(step, 2, 1.0), plane(step, 2, 0.0)
        cls.study = {"analysis": "piezo", "material": "pzt-4", "mesh": {"size_mm": 0.5},
                     "electrodes": [{"faces": [bottom], "V": 50, "name": "drive"}, {"faces": [top], "V": 0, "name": "ground"}],
                     "fixtures": [{"faces": [bottom]}]}
        cls.full = solve(step, directory / "full.glb", cls.study)
        tiny = {"memory_GB": 0.0001, "seconds": 0.001}
        cls.half = solve(step, directory / "half.glb", {**cls.study, "fit": {**tiny, "allow": ["symmetry"]}})
        cls.refined = solve(step, directory / "refined.glb", {**cls.study, "mesh": {"size_mm": 0.35},
                                                              "fit": {**tiny, "allow": ["local_refine"]}})
        cls.modes = solve(step, directory / "modes.glb", {"analysis": "piezo", "solve": "resonance", "material": "pzt-4",
                                                          "mesh": {"size_mm": 1.0}, "modes": 6,
                                                          "electrodes": cls.study["electrodes"],
                                                          "fit": {**tiny, "allow": ["reduce_modes"]}})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_symmetric_quarter_is_the_whole(self):
        rungs = [step["rung"] for step in self.half.fit]
        self.assertIn("symmetry", rungs)
        self.assertEqual(rungs[-1], "budget")   # it still ran, and says what to expect
        self.assertIn("Solved one quarter", self.half.fit[0]["words"])
        full, half = self.full.summary, self.half.summary
        self.assertAlmostEqual(half["capacitance_F"] / full["capacitance_F"], 1.0, delta=0.01)
        # (The peak stress sits on the held face's edge, a singularity each mesh reads differently: not compared.)
        self.assertAlmostEqual(half["max_displacement_mm"] / full["max_displacement_mm"], 1.0, delta=0.01)
        self.assertAlmostEqual(half["reaction_force_N"][0][2], full["reaction_force_N"][0][2], delta=1e-3)
        extras = json.loads(self.half.sidecar.read_text(encoding="utf-8"))
        self.assertEqual(extras["fit"][0]["rung"], "symmetry")
        self.assertTrue(any(f["type"] == "fit_symmetry" for f in self.half.findings))

    def test_local_refinement_keeps_the_capacitance(self):
        self.assertIn("local_refine", [step["rung"] for step in self.refined.fit])
        self.assertAlmostEqual(self.refined.summary["capacitance_F"] / self.full.summary["capacitance_F"], 1.0, delta=0.01)

    def test_fewer_modes_are_found_to_fit(self):
        step = next(step for step in self.modes.fit if step["rung"] == "reduce_modes")
        self.assertEqual(step["detail"], {"from_modes": 6, "to_modes": 3})
        self.assertEqual(len(self.modes.summary["modes"]), 3)
        self.assertEqual(self.modes.summary["rigid_body_modes"], 6)   # held by nothing


if __name__ == "__main__":
    unittest.main()
