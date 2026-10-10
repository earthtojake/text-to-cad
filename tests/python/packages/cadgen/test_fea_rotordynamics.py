"""Spinning (``rotordynamics``): the study it takes, its checks, the rotor line against closed forms, end to end, the ladder.

Benchmarks (spec section 13's rule: analytic, stated tolerance):

- Jeffcott rotor: a massless shaft, a disc at mid-span, rigid bearings. Its
  critical speed is sqrt(k/m), k = 48EI/L³ (1 %).
- A uniform shaft on rigid bearings at its ends, cut from a CAD cylinder (600 mm
  long, 20 mm across, steel): its first forward critical against Euler-Bernoulli's
  first frequency π²·sqrt(EI/ρAL⁴) (3 %).
- An overhung disc on a massless clamped shaft: its forward and backward whirl at
  a speed against the classic frequency equation
  (k11 − mω²)(k22 − Id·ω² + Ip·Ω·ω) − k12² = 0, forward roots ω > 0, backward ω < 0 (5 %).
- The Jeffcott rotor on damped springy bearings: the unbalance orbit away from the
  critical against (U/m)·r²/sqrt((1 − r²)² + (2ζr)²) and its phase lag (5 %); with a
  cross-coupled spring q it goes unstable exactly past q = c·ωn (the log decrement's sign).
- A spinning thin disc with a bore: the hoop stress at the bore against
  ρΩ²(3 + ν)/4·(b² + (1 − ν)/(3 + ν)·a²) (5 %).
- The solid spinning about its own axis, held at its end faces: its bending modes at rest are
  the clamped-clamped beam's (3 %), and spinning they soften to ω² = ω0² − Ω² (1 %).
- The ladder: a time target that the rotor line misses takes ``reduce_modes`` and
  still finds the critical (3 %).

Parse and check tests are stdlib only; the rotor line needs numpy and scipy, and the
solves the fea extra. Every STEP is written into a temporary directory.
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

from cadgen._internal.fea.analyses import REGISTRY, get_analysis  # noqa: E402
from cadgen._internal.fea.analyses.rotordynamics import critical_check, orbit_text, rpm_text, stability_check  # noqa: E402
from cadgen._internal.fea.materials import lookup_material  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

STEEL = lookup_material("steel")
E, D_SHAFT, L_SHAFT = 210000.0, 20.0, 600.0
I_SHAFT = math.pi * D_SHAFT ** 4 / 64.0


def _study(**more) -> dict:
    return {"analysis": "rotordynamics", "material": "steel", "spin": {"axis": "Z", "rpm": [0, 8000]},
            "bearings": [{"faces": ["#o1.f2"], "rigid": True}, {"faces": ["#o1.f3"], "k": 20000, "c": 5}], **more}


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


class StudyFile(unittest.TestCase):
    def test_it_is_registered_as_spinning_tier_3_and_built(self):
        self.assertEqual((REGISTRY["rotordynamics"].tier, REGISTRY["rotordynamics"].word, REGISTRY["rotordynamics"].planned),
                         (3, "Spinning", False))
        analysis = get_analysis("rotordynamics")
        self.assertEqual(analysis.ladder, ("reduce_modes", "iterative", "local_refine"))
        self.assertEqual([spec.kind for spec in analysis.checks], ["critical_speed", "stability", "stress"])

    def test_the_spin_bearings_and_defaults(self):
        parsed = parse_study(_study())
        inputs = parsed.inputs
        self.assertEqual((inputs.axis, inputs.axis_name, inputs.rpm, inputs.modes, inputs.disc_model), ((0.0, 0.0, 1.0), "Z", (0.0, 8000.0), 4, "rigid"))
        self.assertEqual(inputs.face_refs, ("#o1.f2", "#o1.f3"))
        self.assertEqual(inputs.anchor_refs, ("#o1.f2", "#o1.f3"))
        self.assertFalse(inputs.requires_anchor)
        rigid, springy = inputs.bearings
        self.assertTrue(rigid.rigid)
        self.assertEqual(dict(springy.coefficients), {"kxx": 20000.0, "kyy": 20000.0, "cxx": 5.0, "cyy": 5.0})
        # The sweep reaches 1.5 x the top speed, and never short of what a critical_speed check's margin needs.
        self.assertEqual(inputs.sweep_top_rpm, 12000.0)
        self.assertEqual([check["kind"] for check in parsed.checks], ["critical_speed", "stability", "stress"])
        one = parse_study(_study(spin={"axis": [1, 0, 0], "rpm": 3000, "sweep_rpm": 3100}))
        self.assertEqual((one.inputs.axis_name, one.inputs.rpm), ("X", (3000.0, 3000.0)))
        self.assertAlmostEqual(one.inputs.sweep_top_rpm, 1.1 * 1.15 * 3000)
        table = parse_study(_study(bearings=[{"at_mm": 0, "kxx": [[0, 1e4], [6000, 2e4]], "kyy": 1e4, "kxy": 500}]))
        self.assertEqual(dict(table.inputs.bearings[0].coefficients)["kxx"], ((0.0, 1e4), (6000.0, 2e4)))

    def test_it_says_what_is_missing_or_wrong_in_plain_words(self):
        cases = [
            ({"spin": None}, "needs how it spins"),
            ({"spin": {"axis": "Z"}}, "spin.rpm: the operating speeds"),
            ({"spin": {"axis": "W", "rpm": 100}}, "spin.axis: \"X\", \"Y\", \"Z\""),
            ({"spin": {"rpm": [500, 100]}}, "must be 0 or more and no more than high"),
            ({"spin": {"rpm": [0, 1000], "sweep_rpm": 500}}, "must reach the top operating speed"),
            ({"bearings": []}, "a rotor needs the bearings it runs in"),
            ({"bearings": [{"faces": ["#o1.f2"]}]}, "a bearing needs its stiffness across the shaft"),
            ({"bearings": [{"faces": ["#o1.f2"], "rigid": True, "k": 5}]}, "takes no springs or dampers"),
            ({"bearings": [{"faces": ["#o1.f2"], "at_mm": 3, "rigid": True}]}, "one of them"),
            ({"bearings": [{"at_mm": 0, "k": 10, "kxx": 5}]}, "give it or them, not both"),
            ({"bearings": [{"at_mm": 0, "k": [[100, 1], [50, 2]]}]}, "the table's speeds must climb"),
            ({"bearings": [{"at_mm": 0, "k": 10, "c": -1}]}, "a damper takes energy out"),
            ({"discs": [{"at_mm": 10}]}, "an added disc needs its place"),
            ({"unbalance": [{"at_mm": 10}]}, r"unbalance\[0\]\.g_mm: the unbalance's size"),
            ({"modes": 0}, "how many whirl curves"),
            ({"disc_model": "soft"}, "disc_model"),
            ({"spin": {"rpm": 100, "solid_modes": 3}, "bearings": [{"at_mm": 0, "rigid": True}]}, "held at its bearing faces"),
            ({"fixtures": [{"faces": ["#o1.f1"]}]}, "rotordynamics studies take"),
        ]
        for change, words in cases:
            study = _study(**change)
            if change.get("spin", 0) is None:
                study.pop("spin")
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                parse_study(study)

    def test_its_check_kinds_parse_their_own_keys(self):
        parsed = parse_study(_study(view={"checks": [{"kind": "critical_speed", "margin_percent": 20, "orders": [1, 2]},
                                                     {"kind": "stability", "min_log_dec": 0.3}, {"kind": "stress", "margin": 3}]}))
        self.assertEqual(parsed.checks[0], {"kind": "critical_speed", "margin_percent": 20.0, "orders": [1.0, 2.0]})
        self.assertEqual(parsed.checks[1], {"kind": "stability", "min_log_dec": 0.3})
        self.assertEqual(parsed.inputs.orders, (1.0, 2.0))
        self.assertAlmostEqual(parsed.inputs.margin, 0.2)
        for entry, words in (({"kind": "critical_speed", "margin_percent": 120}, "0 up to 100"),
                             ({"kind": "critical_speed", "orders": []}, "the multiples of the spin"),
                             ({"kind": "critical_speed", "backward": "yes"}, "true to judge the backward"),
                             ({"kind": "stability", "min_log_dec": -1}, "must be > 0"),
                             ({"kind": "frequency", "min_Hz": 10}, "not a check this cadgen makes")):
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, words):
                parse_study(_study(view={"checks": [entry]}))

    def test_speeds_and_orbits_in_words(self):
        self.assertEqual([rpm_text(v) for v in (4.5, 850, 3050, 12437)], ["4.5 rpm", "850 rpm", "3,050 rpm", "12,400 rpm"])
        self.assertEqual([orbit_text(v) for v in (0.0042, 6.92)], ["4.2 µm", "6.92 mm"])


class Checks(unittest.TestCase):
    """The checks' status rules and the numbers the viewer's row line reads."""

    @staticmethod
    def _critical(rpm, forward=True, order=1.0, frame=0):
        return {"rpm": rpm, "forward": forward, "order": order, "mode": 1, "frame": frame}

    def test_a_critical_inside_the_range_fails_one_within_the_margin_is_close(self):
        check = {"kind": "critical_speed", "margin_percent": 15.0}
        inside = critical_check(check, [self._critical(9200)], (0.0, 10800.0), 16200.0)
        self.assertEqual((inside["status"], inside["value"], inside["limit"], inside["reference"]), ("fails", 9200, 10800.0, 0.0))
        self.assertGreater(inside["ratio"], 1)
        close = critical_check(check, [self._critical(12400), self._critical(30000)], (0.0, 10800.0), 40000.0)
        self.assertEqual((close["status"], close["limit"], close["at"]["frame"]), ("close", 10800.0, 0))
        self.assertAlmostEqual(close["separation_percent"], 100 * 1600 / 10800, places=2)
        self.assertGreater(close["ratio"], close["close_at"])
        clear = critical_check(check, [self._critical(14000)], (0.0, 10800.0), 16200.0)
        self.assertEqual(clear["status"], "passes")
        self.assertLess(clear["ratio"], clear["close_at"])
        below = critical_check(check, [self._critical(7000)], (8000.0, 10800.0), 16200.0)
        self.assertEqual((below["status"], below["limit"], below["reference"]), ("close", 8000.0, 10800.0))
        self.assertAlmostEqual(below["separation_percent"], 12.5)

    def test_backward_criticals_and_other_orders_count_only_when_asked(self):
        found = [self._critical(9000, forward=False), self._critical(5000, order=2.0)]
        self.assertEqual(critical_check({"kind": "critical_speed"}, found, (0.0, 10800.0), 16200.0)["status"], "passes")
        self.assertEqual(critical_check({"kind": "critical_speed", "backward": True}, found, (0.0, 10800.0), 16200.0)["status"], "fails")
        self.assertEqual(critical_check({"kind": "critical_speed", "orders": [2]}, found, (0.0, 10800.0), 16200.0)["value"], 5000)

    def test_no_critical_in_the_sweep_passes_naming_how_far_it_looked(self):
        none = critical_check({"kind": "critical_speed"}, [], (0.0, 10800.0), 16200.0)
        self.assertEqual((none["status"], none["value"], none["none_below_rpm"]), ("passes", 16200.0, 16200.0))
        self.assertNotIn("mode", none)

    def test_stability_by_the_log_decrement(self):
        def lowest(value):
            return {"value": value, "rpm": 9000.0, "forward": True, "mode": 1}

        check = {"kind": "stability", "min_log_dec": 0.1}
        self.assertEqual(stability_check(check, lowest(-0.02))["status"], "fails")
        self.assertEqual(stability_check(check, lowest(0.05))["status"], "close")
        self.assertEqual(stability_check(check, lowest(0.4))["status"], "passes")
        undamped = stability_check(check, lowest(1e-12), damped=False)
        self.assertEqual((undamped["status"], undamped["value"], undamped["undamped"]), ("passes", 0.0, True))
        self.assertNotIn("mode", undamped)


@unittest.skipUnless(HAVE_FEA, "the fea extra (numpy, scipy, scikit-fem) is not installed")
class RotorLine(unittest.TestCase):
    """The rotor line itself (cadgen._internal.fea.rotor) against closed forms."""

    def setUp(self):
        from cadgen._internal.fea import rotor

        self.rd = rotor

    def _massless(self, length, count):
        return tuple(self.rd.Element(length / count, E * I_SHAFT, math.inf, 0.0, 0.0, 0.0) for _ in range(count))

    def test_the_jeffcott_rotor_whirls_and_goes_critical_at_sqrt_k_over_m(self):
        import numpy as np

        rd = self.rd
        mass = 10e-3  # 10 kg, in t
        rotor = rd.Rotor(tuple(np.linspace(0, L_SHAFT, 9)), self._massless(L_SHAFT, 8), (rd.Disc(4, mass, 20.0, 40.0),),
                         (rd.Bearing(0, rigid=True), rd.Bearing(8, rigid=True)))
        system = rd.System.of(rotor)
        omega_n = math.sqrt(48 * E * I_SHAFT / L_SHAFT ** 3 / mass)
        chart = rd.campbell(system, np.linspace(0, 2 * omega_n, 21), 2)
        forward = [c for c in rd.critical_speeds(system, chart) if c.forward]
        self.assertEqual(len(forward), 1)
        self.assertAlmostEqual(forward[0].omega / omega_n, 1.0, delta=0.01)
        # A disc at mid-span does not tilt in its first mode: its forward and backward whirl stay one frequency.
        self.assertAlmostEqual(chart.forward[-1, 0] / chart.backward[-1, 0], 1.0, places=9)

    def test_an_overhung_disc_splits_forward_and_backward_as_the_frequency_equation_says(self):
        import numpy as np

        rd = self.rd
        length, mass, radius = 300.0, 5e-3, 70.0
        polar, diametral = mass * radius ** 2 / 2, mass * radius ** 2 / 4
        rotor = rd.Rotor(tuple(np.linspace(0, length, 7)), self._massless(length, 6), (rd.Disc(6, mass, diametral, polar),),
                         (rd.Bearing(0, clamped=True),))
        system = rd.System.of(rotor)
        flexibility = np.array([[length ** 3 / (3 * E * I_SHAFT), length ** 2 / (2 * E * I_SHAFT)],
                                [length ** 2 / (2 * E * I_SHAFT), length / (E * I_SHAFT)]])
        (k11, k12), (_, k22) = np.linalg.inv(flexibility)
        for spin in (0.5, 1.0, 2.0):
            omega = spin * math.sqrt(k11 / mass)
            roots = np.roots([mass * diametral, -mass * polar * omega, -(k11 * diametral + mass * k22), k11 * polar * omega,
                              k11 * k22 - k12 ** 2])
            forward = sorted(r.real for r in roots if r.real > 0)
            backward = sorted(-r.real for r in roots if r.real < 0)
            whirls = rd.whirl(system, omega)
            found_forward = [w.omega for w in whirls if w.forward]
            found_backward = [w.omega for w in whirls if not w.forward]
            with self.subTest(spin=spin):
                for got, want in ((found_forward[0], forward[0]), (found_backward[0], backward[0]),
                                  (found_forward[1], forward[1]), (found_backward[1], backward[1])):
                    self.assertAlmostEqual(got / want, 1.0, delta=0.05)
                # The gyroscopic stiffening: forward above the backward, and further apart the faster it spins.
                self.assertGreater(found_forward[0], found_backward[0])

    def _jeffcott_on_springs(self, cross=0.0):
        import numpy as np

        rd = self.rd
        k, c, mass = 1e4, 2.0, 10e-3
        stiff = tuple(rd.Element(100.0, 1e14, math.inf, 0.0, 0.0, 0.0) for _ in range(4))
        half = {"kxx": k / 2, "kyy": k / 2, "cxx": c / 2, "cyy": c / 2, "kxy": cross / 2, "kyx": -cross / 2}
        rotor = rd.Rotor(tuple(np.linspace(0, 400.0, 5)), stiff, (rd.Disc(2, mass, 1e-3, 2e-3),),
                         (rd.Bearing(0, **half), rd.Bearing(4, **half)))
        return rd.System.of(rotor), k, c, mass

    def test_the_unbalance_orbit_and_its_lag_are_jeffcotts_away_from_the_critical(self):
        rd = self.rd
        system, k, c, mass = self._jeffcott_on_springs()
        omega_n = math.sqrt(k / mass)
        zeta = c / (2 * math.sqrt(k * mass))
        unbalance = 100e-6  # 100 g mm in t mm
        for r in (0.5, 2.0):
            response = rd.unbalance_response(system, [(2, unbalance, 0.0)], [r * omega_n])
            want = unbalance / mass * r ** 2 / math.sqrt((1 - r * r) ** 2 + (2 * zeta * r) ** 2)
            lag = math.degrees(math.atan2(2 * zeta * r, 1 - r * r))
            with self.subTest(r=r):
                self.assertAlmostEqual(response.amplitude[0, 2] / want, 1.0, delta=0.05)
                self.assertAlmostEqual(response.phase[0, 2], lag, delta=0.05 * max(lag, 1.0))

    def test_a_cross_coupled_spring_past_c_omega_n_makes_the_whirl_grow(self):
        rd = self.rd
        _, k, c, mass = self._jeffcott_on_springs()
        omega_n = math.sqrt(k / mass)
        for share, grows in ((0.5, False), (1.5, True)):
            system, *_ = self._jeffcott_on_springs(cross=share * c * omega_n)
            lowest = min(w.log_decrement for w in rd.whirl(system, 0.5 * omega_n)[:2])
            with self.subTest(share=share):
                self.assertEqual(lowest < 0, grows)

    def test_a_bearing_table_is_read_linearly_and_held_past_its_ends(self):
        table = ((0.0, 1e4), (6000.0, 2e4))
        self.assertEqual([self.rd.coefficient_at(table, rpm) for rpm in (-5, 0, 3000, 6000, 9000)], [1e4, 1e4, 1.5e4, 2e4, 2e4])


def _shaft_ends(listing):
    planes = sorted((face for face in listing.faces if face.surface == "plane"), key=lambda face: face.center_mm[2])
    return planes[0].ref, planes[-1].ref


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class UniformShaft(unittest.TestCase):
    """A 600 mm steel shaft, 20 mm across, on rigid bearings at its ends, spinning up to 8,000 rpm about Z."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Cylinder, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "shaft.step"
        export_step(Cylinder(D_SHAFT / 2, L_SHAFT, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(cls.step))
        cls.low_end, cls.high_end = _shaft_ends(fea.faces(cls.step))
        cls.study = {"analysis": "rotordynamics", "material": "steel", "spin": {"axis": "Z", "rpm": [0, 8000]},
                     "bearings": [{"faces": [cls.low_end], "rigid": True}, {"faces": [cls.high_end], "rigid": True}],
                     "unbalance": [{"at_mm": 300, "g_mm": 20}], "mesh": {"size_mm": 6.0}}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "shaft.fea.glb", study=cls.study)
        area = math.pi * D_SHAFT ** 2 / 4
        cls.euler_rpm = math.pi ** 2 * math.sqrt(STEEL.E * I_SHAFT / (STEEL.density * area * L_SHAFT ** 4)) * 60 / (2 * math.pi)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_its_first_forward_critical_is_euler_bernoullis_first_frequency(self):
        first = self.result.summary["first_critical_rpm"]
        self.assertAlmostEqual(first / self.euler_rpm, 1.0, delta=0.03)
        forward = [c for c in self.result.summary["critical_speeds"] if c["whirl"] == "forward"]
        self.assertAlmostEqual(forward[0]["frequency_Hz"] * 60 / first, 1.0, delta=1e-6)  # on the 1x line

    def test_the_rotor_line_is_the_cads_shaft(self):
        rotor = self.result.summary["rotor"]
        self.assertAlmostEqual(rotor["length_mm"], L_SHAFT, delta=1e-6)
        self.assertAlmostEqual(rotor["mass_kg"], STEEL.density * math.pi * D_SHAFT ** 2 / 4 * L_SHAFT * 1000, delta=1e-6)
        self.assertEqual(self.result.summary["discs"], [])
        self.assertEqual([b["at_mm"] for b in self.result.summary["bearings"]], [0.0, 600.0])

    def test_the_critical_inside_the_operating_range_fails_and_says_so(self):
        checks = {check["kind"]: check for check in self.result.summary["checks"]}
        critical = checks["critical_speed"]
        self.assertEqual((critical["status"], critical["limit"], critical["whirl"], critical["at"]["frame"]), ("fails", 8000.0, "forward", 0))
        # Rigid bearings take no energy out: undamped, nothing to judge, and a finding asks for the dampers.
        self.assertEqual((checks["stability"]["status"], checks["stability"]["undamped"]), ("passes", True))
        self.assertEqual(checks["stress"]["status"], "passes")
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["critical_speed_inside"]["severity"], "error")
        self.assertIn("runs at a critical speed: forward whirl 1 meets the spin at 6,600 rpm", found["critical_speed_inside"]["summary"])
        self.assertIn("undamped_whirl", found)

    def test_the_glb_carries_each_criticals_whirl_and_the_spinning_stress(self):
        gltf, _ = _glb(self.result.glb)
        extras = gltf["meshes"][0]["extras"]
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual((extras["analysis"]["type"], extras["analysis"]["tier"], extras["analysis"]["word"]), ("rotordynamics", 3, "Spinning"))
        self.assertEqual([field["field"] for field in extras["fields"]], ["von_mises", "whirl"])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], series["default"]), ("mode", "rpm", 0))
        self.assertTrue(series["frames"][0]["label"].startswith("Critical · 6,600 rpm · forward"))
        self.assertEqual(series["frames"][0]["attributes"], {"whirl": "_DISPLACEMENT", "mode_shape": "_DISPLACEMENT",
                                                            "displacement_im": "_DISPLACEMENT_IM_F0"})
        for frame in series["frames"]:
            self.assertEqual(gltf["accessors"][attributes[frame["attributes"]["displacement_im"]]]["type"], "VEC3")
        self.assertEqual(extras["study"]["spin"], {"axis": "Z", "rpm": [0.0, 8000.0], "sweep_rpm": 12000.0})
        self.assertEqual(extras["study"]["bearings"][0], {"faces": [self.low_end], "rigid": True})
        self.assertEqual(extras["study"]["unbalance"], [{"at_mm": 300.0, "g_mm": 20.0, "phase_deg": 0.0}])

    def test_the_sidecar_carries_the_campbell_diagram_and_the_unbalance_response(self):
        sidecar = json.loads(self.result.sidecar.read_text(encoding="utf-8"))
        curves = sidecar["curves"]
        for name in ("forward_1_Hz", "backward_1_Hz", "forward_1_log_dec", "order_1x_Hz", "unbalance_amplitude_mm", "unbalance_phase_deg"):
            self.assertIn(name, curves)
        self.assertEqual((curves["forward_1_Hz"]["x_unit"], curves["forward_1_Hz"]["x"][-1]), ("rpm", 12000.0))
        amplitude = curves["unbalance_amplitude_mm"]
        peak = amplitude["x"][max(range(len(amplitude["y"])), key=lambda i: amplitude["y"][i])]
        self.assertAlmostEqual(peak / self.result.summary["first_critical_rpm"], 1.0, delta=0.01)  # the orbit peaks at the critical
        self.assertEqual(sidecar["limits"][0], "Linear bearings: each a spring and a damper (it may change with speed); no fluid-film nonlinearity")
        lines = self.result.human_lines()
        self.assertIn("(rotordynamics)", lines[0])
        self.assertIn("spins 0 to 8,000 rpm about Z", lines)
        self.assertIn("critical speeds 6,600 rpm", lines)

    def test_a_tight_time_target_projects_the_rotor_on_its_slowest_shapes(self):
        from cadgen import fea

        study = {**self.study, "fit": {"seconds": 4, "allow": ["reduce_modes"]}}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "tight.fea.glb", study=study)
        self.assertTrue(result.ok)
        steps = {step["rung"]: step for step in result.fit}
        self.assertIn("reduce_modes", steps)
        words = steps["reduce_modes"]["words"]
        self.assertTrue(words.startswith("Found the rotor's whirl from its 28 slowest bending shapes"))
        self.assertIn("against the full rotor at 8,000 rpm", steps["reduce_modes"]["accuracy"])
        self.assertAlmostEqual(result.summary["first_critical_rpm"] / self.euler_rpm, 1.0, delta=0.03)
        gltf, _ = _glb(result.glb)
        self.assertIn(words, [step["words"] for step in gltf["meshes"][0]["extras"]["fit"]])
        self.assertIn(words, [step["words"] for step in json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"]])
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in result.human_lines()))
        self.assertIn("fit_reduce_modes", [finding["type"] for finding in result.findings])

    def test_the_solid_spinning_about_its_own_axis_softens_its_bending_by_omega_squared(self):
        # Held at both end faces the solid is a clamped-clamped beam: f0 = (4.730²/2π)·sqrt(EI/ρAL⁴). In the rotating
        # frame a round shaft's bending modes soften to ω² = ω0² − Ω² (its centrifugal stiffening is tiny).
        from cadgen import fea

        study = {**self.study, "spin": {"axis": "Z", "rpm": [0, 8000], "solid_modes": 2},
                 "bearings": [{"faces": [self.low_end], "rigid": True}, {"faces": [self.high_end], "rigid": True}]}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "solid.fea.glb", study=study)
        clamped = (4.730041 / math.pi) ** 2 * self.euler_rpm / 60
        spin = 8000 * 2 * math.pi / 60
        for mode in result.summary["solid_modes"]:
            with self.subTest(mode=mode["mode"]):
                self.assertAlmostEqual(mode["at_rest_Hz"] / clamped, 1.0, delta=0.03)
                softened = math.sqrt((2 * math.pi * mode["at_rest_Hz"]) ** 2 - spin ** 2) / (2 * math.pi)
                self.assertAlmostEqual(mode["spinning_Hz"] / softened, 1.0, delta=0.01)
        self.assertIn("solid_mode_spinning", [finding["type"] for finding in result.findings])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ShaftAndDisc(unittest.TestCase):
    """A shaft with a disc at mid-span, one part: the disc is found in the CAD and lumped with its exact inertia."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Cylinder, Pos, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        step = directory / "rotor.step"
        disc = Pos(0, 0, 290) * Cylinder(60, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
        export_step(Cylinder(D_SHAFT / 2, L_SHAFT, align=(Align.CENTER, Align.CENTER, Align.MIN)) + disc, str(step))
        low, high = _shaft_ends(fea.faces(step))
        study = {"analysis": "rotordynamics", "material": "steel", "spin": {"axis": "Z", "rpm": [1000, 3000]},
                 "bearings": [{"faces": [low], "k": 5e4, "c": 20}, {"faces": [high], "k": 5e4, "c": 20}], "mesh": {"size_mm": 8.0}}
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(step, directory / "rotor.fea.glb", study=study)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_disc_is_found_and_lumped_with_its_mass_and_inertia(self):
        (disc,) = self.result.summary["discs"]
        mass = STEEL.density * math.pi * 60 ** 2 * 20 * 1000  # kg
        self.assertEqual((disc["source"], disc["lumped"], disc["at_mm"]), ("cad", True, 300.0))
        self.assertAlmostEqual(disc["mass_kg"] / mass, 1.0, delta=1e-6)
        self.assertAlmostEqual(disc["polar_kg_mm2"] / (mass * 60 ** 2 / 2), 1.0, delta=1e-6)
        self.assertAlmostEqual(disc["diametral_kg_mm2"] / (mass * (60 ** 2 / 4 + 20 ** 2 / 12)), 1.0, delta=1e-6)

    def test_damped_bearings_give_a_positive_log_decrement_and_a_default_unbalance(self):
        summary = self.result.summary
        self.assertGreater(summary["lowest_log_decrement"]["value"], 0)
        stability = next(check for check in summary["checks"] if check["kind"] == "stability")
        self.assertIn(stability["status"], ("passes", "close"))
        self.assertNotIn("undamped", stability)
        self.assertEqual(summary["default_unbalance"]["grade"], "G2.5")
        self.assertIn("default_unbalance", [finding["type"] for finding in self.result.findings])
        self.assertTrue(summary["critical_speeds"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class SpinningDisc(unittest.TestCase):
    """A thin steel disc, 200 mm across with a 40 mm bore, 4 mm thick, spinning at 10,000 rpm about Z."""

    def test_the_hoop_stress_at_the_bore_is_the_rotating_disc_formulas(self):
        from build123d import Align, Cylinder, export_step

        from cadgen import fea

        inner, outer, thick, rpm = 20.0, 100.0, 4.0, 10000.0
        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "disc.step"
            align = (Align.CENTER, Align.CENTER, Align.MIN)
            export_step(Cylinder(outer, thick, align=align) - Cylinder(inner, thick, align=align), str(step))
            bore = min((face for face in fea.faces(step).faces if face.surface == "cylinder"), key=lambda face: face.area_mm2)
            study = {"analysis": "rotordynamics", "material": "steel", "spin": {"axis": "Z", "rpm": [0, rpm]},
                     "bearings": [{"faces": [bore.ref], "clamped": True}], "mesh": {"size_mm": 4.0}}
            with redirect_stderr(io.StringIO()):
                result = fea.solve(step, Path(tmp) / "disc.fea.glb", study=study)
        omega, nu = rpm * 2 * math.pi / 60, STEEL.nu
        hoop = STEEL.density * omega ** 2 * (3 + nu) / 4 * (outer ** 2 + (1 - nu) / (3 + nu) * inner ** 2)
        summary = result.summary
        # At the bore the radial and axial stresses vanish, so von Mises is the hoop stress.
        self.assertAlmostEqual(summary["max_von_mises_MPa"] / hoop, 1.0, delta=0.05)
        at = summary["max_von_mises_at_mm"]
        self.assertAlmostEqual(math.hypot(at[0], at[1]), inner, delta=0.5)
        self.assertEqual(next(check for check in summary["checks"] if check["kind"] == "stress")["label"], "Spin stress")
        self.assertIn("rotor_held_still", [finding["type"] for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
