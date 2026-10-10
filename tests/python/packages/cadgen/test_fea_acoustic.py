"""Sound (`"analysis": "acoustic"`, lite): the study it reads, its benchmarks against theory, and the ladder.

Benchmarks, each a build123d solid in a temporary directory, meshed coarse:

- a rigid-walled box of air 300 x 190 x 110 mm: its modes are c/2 √((l/Lx)² + (m/Ly)² + (n/Lz)²),
  within 1 %; the same air closed inside a hollow box (``"domain": "inside"``);
- a closed-closed duct 500 mm long: its first resonances n c / 2L within 1 %, and driven by a piston
  at one end its pressure at the other ρ c V / |sin kL| within 1 %;
- a pulsating sphere of radius 20 mm in open air (``"domain": "outside"``): the pressure at
  r = 30, 50 and 70 mm, and at 500 mm past the box, against the monopole
  ρ c k a² V / (r √(1 + (ka)²)) within 10 %, through the first-order absorbing boundary;
- the ladder under a tiny time target: the air coarsened under six elements per wavelength with its
  accuracy note, the response built from modes, the open air brought in, each said everywhere;
- vibro-acoustics: a plate shaken by a harmonic study radiating into the air around it.
"""

from __future__ import annotations

import io
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import REGISTRY, get_analysis  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

RHO, C = 1.204, 343.2
BOX = (300.0, 190.0, 110.0)
DUCT = 500.0


def glb_extras(path: Path) -> tuple[dict, list[str]]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    return gltf["meshes"][0]["extras"], list(gltf["meshes"][0]["primitives"][0]["attributes"])


def box_modes(lengths, count: int) -> list[float]:
    """The rigid box's first ``count`` modes past the uniform one, Hz."""
    every = sorted(C / 2 * math.sqrt(sum((n / (side / 1000)) ** 2 for n, side in zip(lmn, lengths)))
                   for lmn in ((l, m, n) for l in range(6) for m in range(6) for n in range(6)))
    return every[1:count + 1]


def solve(step: Path, out: Path, study: dict):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        return fea.solve(step, out, study=study)


def end_faces(step: Path) -> tuple[str, str]:
    """The duct's x_min and x_max faces."""
    from cadgen._internal.fea.run import list_faces

    faces = list_faces(step).faces
    low = next(face.ref for face in faces if face.normal and face.normal[0] < -0.9)
    high = next(face.ref for face in faces if face.normal and face.normal[0] > 0.9)
    return low, high


class StudyFile(unittest.TestCase):
    def test_it_is_registered_built_sound_and_stdlib_only_at_import(self):
        entry = REGISTRY["acoustic"]
        self.assertEqual((entry.tier, entry.word, entry.planned), (3, "Sound", False))
        analysis = get_analysis("acoustic")
        self.assertEqual((analysis.name, analysis.word, analysis.tier), ("acoustic", "Sound", 3))
        code = ("import sys; sys.path.insert(0, 'packages/cadgen/src');"
                "import cadgen._internal.fea.analyses.acoustic;"
                "print(','.join(sorted(m for m in ('numpy', 'scipy', 'skfem', 'OCP', 'netgen') if m in sys.modules)))")
        root = Path(__file__).resolve().parents[4]
        heavy = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(heavy, "")

    def test_no_sources_finds_the_modes_and_sources_solve_a_response(self):
        modes = parse_study({"analysis": "acoustic", "modes": 4})
        self.assertEqual((modes.inputs.solve, modes.inputs.domain, modes.inputs.modes, modes.material), ("modes", "part", 4, None))
        self.assertEqual(modes.inputs.fluid.name, "air")
        self.assertEqual([spec.name for spec in get_analysis("acoustic").fields], ["sound_pressure"])
        response = parse_study({
            "analysis": "acoustic", "fluid": "water", "sweep_Hz": [100, 1000],
            "sources": [{"faces": ["#o1.f1"], "velocity_mm_s": 2}, {"point_mm": [1, 2, 3], "volume_velocity_m3_s": 1e-6}],
            "absorbers": [{"faces": ["#o1.f2"], "absorption": 0.3}], "open": [{"faces": ["#o1.f3"]}],
            "probes": [{"label": "ear", "at_mm": [0, 0, 10]}],
            "view": {"checks": [{"kind": "sound_level", "limit_dB": 80, "probes": ["ear"]}]},
        })
        inputs = response.inputs
        self.assertEqual((inputs.solve, inputs.fluid.name, inputs.loss_factor, inputs.sweep_Hz), ("response", "water", 0.01, (100.0, 1000.0)))
        self.assertEqual(inputs.face_refs, ("#o1.f1", "#o1.f2", "#o1.f3"))
        self.assertEqual([spec.name for spec in get_analysis("acoustic").fields], ["sound_level", "sound_pressure"])
        self.assertEqual(response.checks, ({"kind": "sound_level", "limit_dB": 80.0, "probes": ["ear"]},))

    def test_from_harmonic_reads_the_harmonic_keys_and_needs_the_material(self):
        study = parse_study({
            "analysis": "acoustic", "from": "harmonic", "material": "aluminum-6061-t6", "fixtures": [{"faces": ["#o1.f1"]}],
            "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1}, "sweep_Hz": [100, 800],
        })
        inputs = study.inputs
        self.assertEqual((inputs.domain, inputs.from_harmonic, inputs.requires_anchor, inputs.anchor_refs), ("outside", True, True, ("#o1.f1",)))
        self.assertEqual(get_analysis("acoustic").upstream_for(inputs), ("harmonic",))
        self.assertEqual(inputs.harmonic.sweep_Hz, (100.0, 800.0))

    def test_the_errors_name_the_field_in_plain_words(self):
        source = [{"faces": ["#o1.f1"], "velocity_mm_s": 1}]
        cases = [
            ({"sweep_Hz": [10, 100]}, "sources: a sweep needs something making the sound"),
            ({"sources": source}, "sweep_Hz: the frequencies to solve the sound at"),
            ({"domain": "outside"}, "domain: open air has no natural frequencies"),
            ({"domain": "room"}, "domain: \"room\" is not one of"),
            ({"absorbers": [{"faces": ["#o1.f2"], "absorption": 0.3}]}, "absorbers: absorbers damp a driven response"),
            ({"sources": source, "sweep_Hz": [10, 100], "absorbers": [{"faces": ["#o1.f2"], "absorption": 1.5}]},
             "absorbers[0].absorption: a share from 0 to 1"),
            ({"sources": [{"faces": ["#o1.f1"]}], "sweep_Hz": [10, 100]}, "sources[0].velocity_mm_s"),
            ({"fluid": "oil"}, "fluid: \"oil\" is not one of"),
            ({"from": "harmonic", "fixtures": [{"faces": ["#o1.f1"]}], "excitation": {"type": "base", "direction": [0, 0, 1]},
              "sweep_Hz": [10, 100]}, "material: the vibrating part's material"),
            ({"fixtures": [{"faces": ["#o1.f1"]}]}, "fixtures: that is a harmonic study's key"),
            ({"sources": source, "sweep_Hz": [10, 100], "view": {"checks": [{"kind": "sound_level", "limit_dB": 80, "probes": ["ear"]}]}},
             "view.checks[0].probes: no probe labelled 'ear'"),
            ({"view": {"checks": [{"kind": "sound_level", "limit_dB": 80}]}}, "view.checks[0]: a sound_level check judges a driven response"),
            ({"sources": source, "sweep_Hz": [10, 100], "view": {"checks": [{"kind": "frequency", "min_Hz": 80}]}},
             "view.checks[0]: a frequency check judges the air's natural frequencies"),
            ({"view": {"checks": [{"kind": "sound_level"}]}}, "limit_dB: a sound_level check needs the loudest level allowed"),
        ]
        for extra, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                parse_study({"analysis": "acoustic", **extra})
            self.assertIn(fragment, str(caught.exception))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Numerics(unittest.TestCase):
    def test_absorption_admittance_and_the_mesh_wave_speed_error(self):
        from cadgen._internal.fea.acoustic_ops import absorption_admittance, frequency_error, level_dB

        self.assertAlmostEqual(absorption_admittance(1.0), 1.0)          # ρc: soaks up everything
        beta = absorption_admittance(0.5)
        z = 1 / beta
        self.assertAlmostEqual(1 - ((z - 1) / (z + 1)) ** 2, 0.5)
        self.assertLess(abs(frequency_error(6)), 0.001)
        self.assertGreater(frequency_error(3), frequency_error(6))
        self.assertAlmostEqual(float(level_dB(20e-6 * math.sqrt(2) * 10 ** 4)), 80.0)

    def test_the_iterative_solvers_agree_with_the_direct_ones(self):
        import numpy as np

        from cadgen._internal.fea import acoustic_ops
        from cadgen._internal.fea.femspace import FemSpace
        from tests.python.packages.cadgen.test_fea_protocol import box_volume

        volume = box_volume((DUCT, 40.0, 40.0), (40, 3, 3))
        region = acoustic_ops.part_region(FemSpace.build(volume, 2), volume, (250.0, 20.0, 20.0))
        ops = acoustic_ops.assemble(region, sources=[(volume.boundary_ordinal == 1, 1e-3)],
                                    absorbers=[(volume.boundary_ordinal == 2, 0.4)])
        air = acoustic_ops.Fluid("air", RHO, C)
        for f in (200.0, 900.0):
            direct = acoustic_ops.solve_frequency(ops, air, f, 0.01)
            iterative = acoustic_ops.solve_frequency(ops, air, f, 0.01, iterative=True)
            self.assertLess(np.abs(iterative - direct).max() / np.abs(direct).max(), 1e-6)
        k2_direct = acoustic_ops.cavity_modes(ops, 5)[0]
        k2_iterative = acoustic_ops.cavity_modes(ops, 5, iterative=True)[0]
        np.testing.assert_allclose(np.sqrt(k2_iterative[1:]), np.sqrt(k2_direct[1:]), rtol=1e-5)
        self.assertLess(abs(C * math.sqrt(k2_direct[1]) / (2 * math.pi) / (C / (2 * DUCT / 1000)) - 1), 0.01)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Benchmarks(unittest.TestCase):
    """Theory against the solve, every number printed on failure."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, Sphere, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        corner = (Align.MIN,) * 3
        cls.box = cls.tmp / "box.step"
        export_step(Box(*BOX, align=corner), str(cls.box))
        cls.duct = cls.tmp / "duct.step"
        export_step(Box(DUCT, 40, 40, align=corner), str(cls.duct))
        cls.shell = cls.tmp / "shell.step"
        export_step(Box(BOX[0] + 10, BOX[1] + 10, BOX[2] + 10) - Box(*BOX), str(cls.shell))
        cls.sphere = cls.tmp / "sphere.step"
        export_step(Sphere(20.0), str(cls.sphere))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_rigid_box_of_air_rings_at_its_room_modes(self):
        result = solve(self.box, self.tmp / "box.fea.glb", {"analysis": "acoustic", "modes": 6, "mesh": {"size_mm": 40}})
        got = [mode["frequency_Hz"] for mode in result.summary["modes"]]
        expected = box_modes(BOX, 6)
        for f, e in zip(got, expected):
            self.assertLess(abs(f / e - 1), 0.01, (got, expected))
        self.assertTrue(result.summary["uniform_mode_left_out"])
        self.assertGreaterEqual(result.summary["air_mesh"]["elements_per_wavelength"], 5.99)
        extras, attributes = glb_extras(result.glb)
        self.assertEqual(extras["analysis"]["type"], "acoustic")
        self.assertEqual(extras["series"]["kind"], "mode")
        self.assertEqual(extras["series"]["frames"][1]["label"], f"Mode 2 · {expected[1]:.0f} Hz")
        self.assertEqual(extras["fields"][0], {"attribute": "_SOUND_PRESSURE", "name": "sound pressure (mode shape)", "units": "",
                                               "min": -1.0, "max": 1.0, "attribute_scale": 1.0, "field": "sound_pressure", "signed": True,
                                               "per_frame": True})
        self.assertIn("_SOUND_PRESSURE_F5", attributes)
        self.assertEqual(len(extras["analysis"]["limits"]), 2)
        print(f"\n  box modes {got} Hz against {[round(e, 2) for e in expected]} Hz", file=sys.stderr)

    def test_the_same_air_closed_inside_a_hollow_box(self):
        result = solve(self.shell, self.tmp / "shell.fea.glb", {
            "analysis": "acoustic", "domain": "inside", "modes": 3, "mesh": {"size_mm": 40},
            "view": {"checks": [{"kind": "frequency", "min_Hz": 600, "label": "Boom"}]},
        })
        got = [mode["frequency_Hz"] for mode in result.summary["modes"]]
        expected = box_modes(BOX, 3)
        for f, e in zip(got, expected):
            self.assertLess(abs(f / e - 1), 0.01, (got, expected))
        check = result.summary["checks"][0]
        self.assertEqual((check["kind"], check["label"], check["status"], check["mode"]), ("frequency", "Boom", "fails", 1))
        self.assertEqual(check["at"]["frame"], 0)
        self.assertIn("acoustic_resonance", [finding["type"] for finding in result.findings])
        print(f"\n  inside modes {got} Hz against {[round(e, 2) for e in expected]} Hz", file=sys.stderr)

    def test_a_closed_duct_resonates_at_n_c_over_2L_and_a_piston_drives_it_as_theory_says(self):
        result = solve(self.duct, self.tmp / "duct.fea.glb", {"analysis": "acoustic", "modes": 4, "mesh": {"size_mm": 40}})
        got = [mode["frequency_Hz"] for mode in result.summary["modes"]]
        expected = [n * C / (2 * DUCT / 1000) for n in (1, 2, 3, 4)]
        for f, e in zip(got, expected):
            self.assertLess(abs(f / e - 1), 0.01, (got, expected))
        piston, wall = end_faces(self.duct)
        driven = solve(self.duct, self.tmp / "duct-driven.fea.glb", {
            "analysis": "acoustic", "frequencies_Hz": [200, 500, 900], "loss_factor": 0, "mesh": {"size_mm": 40},
            "sources": [{"faces": [piston], "velocity_mm_s": 1}], "probes": [{"label": "end", "at_mm": [DUCT, 20, 20]}],
            "view": {"checks": [{"kind": "sound_level", "limit_dB": 80, "probes": ["end"]}]},
        })
        curve = json.loads(driven.sidecar.read_text(encoding="utf-8"))["curves"]["level_dB end"]
        for f, level in zip(curve["x"], curve["y"]):
            k = 2 * math.pi * f / C
            pressure = RHO * C * 1e-3 / abs(math.sin(k * DUCT / 1000))
            theory = 20 * math.log10(pressure / math.sqrt(2) / 20e-6)
            self.assertLess(abs(10 ** ((level - theory) / 20) - 1), 0.01, (f, level, theory))
        check = driven.summary["checks"][0]
        self.assertEqual((check["kind"], check["status"], check["probe"], check["unit"]), ("sound_level", "fails", "end", "dB"))
        self.assertEqual(check["at"]["value"], 900.0)
        self.assertIn("too_loud", [finding["type"] for finding in driven.findings])
        print(f"\n  duct modes {got} Hz against {[round(e, 2) for e in expected]} Hz; driven levels {curve['y']} dB",
              file=sys.stderr)

    def test_a_pulsating_sphere_radiates_as_a_monopole_through_the_absorbing_box(self):
        f, a, v = 1000.0, 0.02, 1e-3
        probes = [{"label": f"r{r}", "at_mm": [r, 0, 0]} for r in (30, 50, 70)] + [{"label": "far", "at_mm": [0, 0, 500]}]
        result = solve(self.sphere, self.tmp / "sphere.fea.glb", {
            "analysis": "acoustic", "domain": "outside", "frequencies_Hz": [f], "mesh": {"size_mm": 10},
            "sources": [{"faces": ["#o1.f1"], "velocity_mm_s": 1}], "probes": probes,
        })
        k = 2 * math.pi * f / C
        errors = {}
        for probe in result.summary["probes"]:
            r = math.dist(probe["at_mm"], (0, 0, 0)) / 1000
            monopole = RHO * C * k * a * a * v / (r * math.sqrt(1 + (k * a) ** 2))
            errors[probe["label"]] = probe["peak_pressure_Pa"] / monopole - 1
        self.assertLess(max(abs(e) for e in errors.values()), 0.10, errors)
        self.assertTrue(result.summary["probes"][-1]["extrapolated"])
        self.assertEqual(len(json.loads(result.sidecar.read_text(encoding="utf-8"))["limits"]), 3)
        self.assertIn("open_air_boundary", [finding["type"] for finding in result.findings])
        print(f"\n  pulsating sphere at {f:g} Hz: relative errors {({k_: round(e, 4) for k_, e in errors.items()})}", file=sys.stderr)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, Sphere, export_step

        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.duct = cls.tmp / "duct.step"
        export_step(Box(DUCT, 40, 40, align=(Align.MIN,) * 3), str(cls.duct))
        cls.sphere = cls.tmp / "sphere.step"
        export_step(Sphere(20.0), str(cls.sphere))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_a_tiny_budget_coarsens_the_air_builds_from_modes_and_says_so_everywhere(self):
        piston, wall = end_faces(self.duct)
        study = {"analysis": "acoustic", "sweep_Hz": [100, 1200], "points": 12, "mesh": {"size_mm": 40},
                 "sources": [{"faces": [piston], "velocity_mm_s": 1}], "absorbers": [{"faces": [wall], "absorption": 0.5}],
                 "probes": [{"label": "mid", "at_mm": [250, 20, 20]}]}
        full = solve(self.duct, self.tmp / "full.fea.glb", study)
        adapted = solve(self.duct, self.tmp / "adapted.fea.glb", {**study, "fit": {"seconds": 0.001}})
        self.assertTrue(adapted.ok)
        rungs = [step["rung"] for step in adapted.fit]
        self.assertIn("local_refine", rungs)
        self.assertIn("reduce_modes", rungs)
        coarse = next(step for step in adapted.fit if step["rung"] == "local_refine")
        self.assertIn("elements per wavelength at 1200 Hz", coarse["words"])
        self.assertIn("the mesh's wave-speed error", coarse["accuracy"])
        self.assertGreater(coarse["accuracy_pct"], 0)
        extras, _ = glb_extras(adapted.glb)
        sidecar = json.loads(adapted.sidecar.read_text(encoding="utf-8"))
        self.assertEqual([step["rung"] for step in extras["fit"]], rungs)
        self.assertEqual([step["rung"] for step in sidecar["fit"]], rungs)
        self.assertTrue(any(line.startswith("adapted: Meshed the air at") for line in adapted.human_lines()))
        self.assertIn("fit_local_refine", [finding["type"] for finding in adapted.findings])
        # The level at the probe stays within a stated 2 dB of the full solve, frequency by frequency.
        before = json.loads(full.sidecar.read_text(encoding="utf-8"))["curves"]["level_dB mid"]
        after = sidecar["curves"]["level_dB mid"]
        low = [abs(a - b) for x, a, b in zip(before["x"], before["y"], after["y"]) if x <= 600]
        self.assertLess(max(low), 2.0, (before, after))
        print(f"\n  ladder: {rungs}; probe level moved at most {max(low):.2f} dB up to 600 Hz", file=sys.stderr)

    def test_open_air_brings_its_absorbing_box_in_to_fit(self):
        adapted = solve(self.sphere, self.tmp / "sphere.fea.glb", {
            "analysis": "acoustic", "domain": "outside", "frequencies_Hz": [1000], "mesh": {"size_mm": 10},
            "sources": [{"faces": ["#o1.f1"], "velocity_mm_s": 1}], "probes": [{"label": "r50", "at_mm": [50, 0, 0]}],
            "fit": {"seconds": 0.001, "allow": ["far_field"]},
        })
        step = next(step for step in adapted.fit if step["rung"] == "far_field")
        self.assertIn("Brought the open air's absorbing box in", step["words"])
        self.assertIn("k·r is", step["accuracy"])
        k, a, r = 2 * math.pi * 1000 / C, 0.02, 0.05
        monopole = RHO * C * k * a * a * 1e-3 / (r * math.sqrt(1 + (k * a) ** 2))
        self.assertLess(abs(adapted.summary["probes"][0]["peak_pressure_Pa"] / monopole - 1), 0.15)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class VibroAcoustic(unittest.TestCase):
    def test_a_shaken_plate_radiates_into_the_air_around_it(self):
        from build123d import Align, Box, export_step

        from cadgen._internal.fea.run import list_faces

        with tempfile.TemporaryDirectory() as tmp:
            step = Path(tmp) / "plate.step"
            export_step(Box(60, 30, 3, align=(Align.MIN,) * 3), str(step))
            root = next(face.ref for face in list_faces(step).faces if face.normal and face.normal[0] < -0.9)
            result = solve(step, Path(tmp) / "plate.fea.glb", {
                "analysis": "acoustic", "from": "harmonic", "material": "aluminum-6061-t6", "fixtures": [{"faces": [root]}],
                "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1}, "sweep_Hz": [200, 1200],
                "mesh": {"size_mm": 6}, "air_mm": 30, "probes": [{"label": "mic", "at_mm": [30, 15, 300]}],
                "view": {"checks": [{"kind": "sound_level", "limit_dB": 120, "probes": ["mic"]}]},
            })
            self.assertTrue(result.ok)
            sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
            self.assertEqual(result.summary["from"], "harmonic")
            self.assertIsNotNone(sidecar["upstream"]["harmonic"])
            harmonic_frames = sidecar["series"]["frames"]
            self.assertGreater(len(harmonic_frames), 3)
            mic = result.summary["probes"][0]
            self.assertTrue(mic["extrapolated"])
            self.assertGreater(mic["peak_level_dB"], 20.0)
            self.assertEqual(result.summary["checks"][0]["status"], "passes")
            extras, _ = glb_extras(result.glb)
            self.assertEqual(extras["study"]["acoustic"]["from"], "harmonic")
            self.assertEqual(extras["study"]["excitation"]["type"], "base")
            print(f"\n  shaken plate: mic peak {mic['peak_level_dB']} dB at {mic['peak_Hz']} Hz", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
