"""Shaking (``harmonic``): the study it takes, modal superposition itself, and a shaken cantilever against theory.

The beam is a build123d box written to a temporary STEP: 100 mm long, 6 x 6 mm
steel, clamped at x = 0 and shaken along Z at 1 g. Shaken at its first natural
frequency f1 with damping ratio ζ, its tip moves relative to the clamp by about
1.566·a/ω1² · 1/(2ζ): 1.566 is the cantilever's first-mode participation at
the tip, 1/(2ζ) the resonance's amplification. Far below f1 it follows the
shake and bends as under a steady 1 g: tip w = qL⁴/(8EI), q = ρgA (spec
section 13, 10 %).

Parse and superposition tests need no mesh; the beam needs the fea extra.
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
from types import SimpleNamespace

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.analyses import get_analysis  # noqa: E402
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
G0 = 9806.65
ZETA = 0.02
FIXED = "#o1.f1"


def _study(**more) -> dict:
    return {"analysis": "harmonic", "material": "steel", "fixtures": [{"faces": [FIXED]}],
            "excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": 1}, "sweep_Hz": [10, 600], **more}


class StudyFile(unittest.TestCase):
    def test_a_base_shake_reads_its_direction_amplitude_sweep_and_damping(self):
        parsed = parse_study(_study(excitation={"type": "base", "direction": [0, 0, 2], "amplitude_g": 3}))
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.excitation, inputs.direction, inputs.amplitude_g), ("harmonic", "base", (0.0, 0.0, 1.0), 3.0))
        self.assertEqual((inputs.sweep_Hz, inputs.damping_ratio, inputs.top_Hz), ((10.0, 600.0), 0.02, 900.0))
        self.assertEqual((inputs.anchor_refs, inputs.requires_anchor, inputs.loads), ((FIXED,), True, ()))
        # With no view, the shake is judged on strength.
        self.assertEqual(parsed.checks, ({"kind": "stress"},))

    def test_a_force_shake_swings_its_loads(self):
        study = _study(excitation={"type": "force"}, loads=[{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 10]}])
        inputs = parse_study(study).inputs
        self.assertEqual((inputs.excitation, inputs.direction, inputs.face_refs), ("force", None, (FIXED, "#o1.f2")))
        self.assertEqual(inputs.loads[0].vector, (0.0, 0.0, 10.0))

    def test_what_is_wrong_is_said_in_plain_words(self):
        loads = [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, 1]}]
        for bad, words in (
            ({"excitation": None}, "what shakes it"),
            ({"excitation": {"type": "random"}}, "is not one of"),
            ({"excitation": {"type": "base", "amplitude_g": 1}}, "direction it is shaken along"),
            ({"excitation": {"type": "base", "direction": [0, 0, 0]}}, "direction is zero"),
            ({"excitation": {"type": "base", "direction": [0, 0, 1], "amplitude_g": -1}}, "must be > 0"),
            ({"excitation": {"type": "base", "direction": [0, 0, 1], "psd": 1}}, "unknown keys"),
            ({"loads": loads}, "a base shake moves the fixtures, so it takes no loads"),
            ({"excitation": {"type": "force"}}, "needs the forces it swings with"),
            ({"sweep_Hz": [600, 10]}, "must be below high"),
            ({"sweep_Hz": 100}, r"\[low, high\]"),
            ({"damping_ratio": 1.5}, "must be under 1"),
            ({"fixtures": []}, "at least one"),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                parse_study({**_study(), **bad})
        with self.assertRaisesRegex(ValueError, "not one of"):
            parse_study(_study(excitation={"type": "force"}, loads=[{"type": "gravity", "vector_g": [0, 0, -1]}]))

    def test_it_takes_the_three_shaking_checks_and_a_frequency_scrubber(self):
        parsed = parse_study(_study(view={"checks": [
            {"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5}, {"kind": "acceleration", "limit_g": 10, "faces": ["#o1.f2"]}],
            "presets": [{"label": "At resonance", "frame": 490, "deformation": 50}]}))
        self.assertEqual([check["kind"] for check in parsed.checks], ["stress", "displacement", "acceleration"])
        self.assertEqual(parsed.check_faces, ("#o1.f2",))
        with self.assertRaisesRegex(ValueError, "not a check this cadgen makes"):
            parse_study(_study(view={"checks": [{"kind": "frequency", "min_Hz": 60}]}))
        with self.assertRaisesRegex(ValueError, "limit_g"):
            parse_study(_study(view={"checks": [{"kind": "acceleration"}]}))


class Ladder(unittest.TestCase):
    def test_it_declares_the_spec_ladder(self):
        self.assertEqual(get_analysis("harmonic").ladder,
                         ("reduce_modes", "iterative", "local_refine", "defeature", "linear_elements", "symmetry"))

    def test_reduce_modes_keeps_fewer_modes_once(self):
        from cadgen._internal.fea.fit import FitPlan

        analysis = get_analysis("harmonic")
        inputs = parse_study(_study()).inputs
        ctx = SimpleNamespace(plan=FitPlan(), budget=None)
        step = analysis.apply("reduce_modes", ctx, inputs)
        self.assertEqual((step.rung, ctx.plan.modes), ("reduce_modes", 6))
        self.assertIn("90% of the mass moving along Z", step.words)
        self.assertIsNone(analysis.apply("reduce_modes", ctx, inputs))
        for rung in ("idealise", "symmetry"):
            self.assertIsNone(analysis.apply(rung, ctx, inputs))


class Superposition(unittest.TestCase):
    """The shared module on a chain of three masses and springs, held at one end: against a direct solve."""

    def setUp(self):
        import numpy as np
        import scipy.sparse as sparse

        k, m = 1.0e6, 1.0e-3
        stiffness = np.zeros((4, 4))
        for a in range(3):
            stiffness[np.ix_([a, a + 1], [a, a + 1])] += k * np.array([[1, -1], [-1, 1]])
        self.K = sparse.csr_matrix(stiffness)
        self.M = sparse.csr_matrix(np.diag([m, m, m, m / 2]))
        self.fixed = np.array([0])

    def test_modes_are_the_eigenpairs_mass_normalised_and_held(self):
        import numpy as np
        import scipy.linalg

        from cadgen._internal.fea import superposition as sp

        modes = sp.find_modes(self.K, self.M, self.fixed, top_Hz=1e6)
        values = scipy.linalg.eigh(self.K.toarray()[1:, 1:], self.M.toarray()[1:, 1:], eigvals_only=True)
        np.testing.assert_allclose(modes.omega ** 2, values, rtol=1e-9)
        np.testing.assert_allclose(modes.vectors.T @ self.M @ modes.vectors, np.eye(3), atol=1e-9)
        self.assertTrue(np.all(modes.vectors[0] == 0))
        self.assertTrue(modes.complete)
        # Only the modes up to the top are kept, at least one.
        self.assertEqual(len(sp.find_modes(self.K, self.M, self.fixed, top_Hz=1.0)), 1)

    def test_a_base_shake_superposed_is_the_direct_damped_solve(self):
        import numpy as np

        from cadgen._internal.fea import superposition as sp

        modes = sp.find_modes(self.K, self.M, self.fixed, top_Hz=1e6)
        r = np.ones(4)
        gamma = sp.participation(modes, self.M, r)
        masses, total = sp.effective_mass(modes, self.M, r)
        self.assertAlmostEqual(total, 3.5e-3)
        # All the modes of the free DOF together hold the mass that moves (the held end's own does not).
        self.assertAlmostEqual(masses.sum(), 3.0e-3 / 2 + 1.0e-3, delta=1e-12)
        omega = np.array([300.0, float(modes.omega[0]), 5000.0])
        q = sp.base_coordinates(modes.omega, gamma, omega, ZETA, G0)
        # Direct: (K - ω²M + iωC) u = -M r a on the free DOF, C the same modal damping.
        free = np.arange(1, 4)
        phi = modes.vectors[free]
        Mf = self.M.toarray()[np.ix_(free, free)]
        C = Mf @ phi @ np.diag(2 * ZETA * modes.omega) @ phi.T @ Mf
        for i, w in enumerate(omega):
            A = self.K.toarray()[np.ix_(free, free)] - w ** 2 * Mf + 1j * w * C
            direct = np.linalg.solve(A, -(self.M.toarray() @ r)[free] * G0)
            np.testing.assert_allclose(phi @ q[i], direct, rtol=1e-9)
        # At its own frequency a mode answers 1/(2ζ) times its static share, a quarter turn behind.
        static = -gamma[0] * G0 / modes.omega[0] ** 2
        self.assertAlmostEqual(abs(q[1, 0]) / abs(static), 1 / (2 * ZETA), delta=1e-9)
        self.assertAlmostEqual(q[1, 0].real, 0.0, delta=1e-12 * abs(q[1, 0]))
        p = sp.modal_loads(modes, np.array([0.0, 0.0, 0.0, 1.0]))
        np.testing.assert_allclose(sp.force_coordinates(modes.omega, p, omega, ZETA)[0],
                                   p / (modes.omega ** 2 - 300.0 ** 2 + 2j * ZETA * modes.omega * 300.0))

    def test_peaks_over_a_cycle(self):
        import numpy as np

        from cadgen._internal.fea import superposition as sp

        rng = np.random.default_rng(1)
        Z = rng.standard_normal((5, 3)) + 1j * rng.standard_normal((5, 3))
        theta = np.linspace(0, 2 * math.pi, 20001)
        sampled = np.abs(np.linalg.norm(Z.real[None] * np.cos(theta)[:, None, None] - Z.imag[None] * np.sin(theta)[:, None, None], axis=2)).max(axis=0)
        np.testing.assert_allclose(sp.vector_peak(Z), sampled, rtol=1e-6)
        # A stress in phase everywhere peaks at its own von Mises; sampled at 12 phases, never above the true peak.
        s = rng.standard_normal((6, 4))
        np.testing.assert_allclose(sp.von_mises_peak(s * (1 + 1j) / math.sqrt(2)), sp.von_mises_of(s), rtol=1e-12)
        S = rng.standard_normal((6, 4)) + 1j * rng.standard_normal((6, 4))
        fine = np.max([sp.von_mises_of(S.real * math.cos(t) - S.imag * math.sin(t)) for t in theta[:10001]], axis=0)
        coarse = sp.von_mises_peak(S)
        self.assertTrue(np.all(coarse <= fine + 1e-12))
        self.assertTrue(np.all(coarse >= math.cos(math.pi / 24) * fine))
        self.assertEqual(len(sp.phase_angles()), sp.PHASES)

    def test_the_fewest_modes_holding_a_share(self):
        import numpy as np

        from cadgen._internal.fea import superposition as sp

        chosen, share = sp.fewest_modes(np.array([0.1, 0.6, 0.0, 0.25, 0.05]), 1.0)
        self.assertEqual((chosen.tolist(), round(share, 6)), ([0, 1, 3], 0.95))
        # Short of the share: every mode that moves at all.
        chosen, share = sp.fewest_modes(np.array([0.61, 0.0]), 1.0)
        self.assertEqual((chosen.tolist(), round(share, 6)), ([0], 0.61))

    def test_lobpcg_finds_the_modes_a_factorisation_does(self):
        import numpy as np
        import scipy.sparse as sparse

        from cadgen._internal.fea import superposition as sp

        n = 800
        K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 2.0), np.full(n - 1, -1.0)], [-1, 0, 1], format="csr") * 1e6
        M = sparse.identity(n, format="csr") * 1e-3
        top = float(np.sqrt(4e9) * np.sin(4 * math.pi / (2 * (n + 1))) / (2 * math.pi)) * 1.01
        direct = sp.find_modes(K, M, np.array([0]), top)
        iterative = sp.find_modes(K, M, np.array([0]), top, method="lobpcg")
        self.assertEqual(len(direct), len(iterative))
        np.testing.assert_allclose(iterative.omega, direct.omega, rtol=1e-5)


class Frames(unittest.TestCase):
    def test_the_grid_meets_every_mode_and_the_frames_keep_the_peaks(self):
        import numpy as np

        from cadgen._internal.fea.analyses.harmonic import choose_frames, sweep_grid

        grid = sweep_grid(10, 1000, [123.4, 5000.0], ZETA)
        self.assertTrue(np.isclose(grid, 123.4).any())
        self.assertTrue(np.all(np.diff(grid) > 0) and grid[0] == 10 and grid[-1] == 1000)
        curve = 1 / np.abs(123.4 ** 2 - grid ** 2 + 2j * ZETA * 123.4 * grid)
        frames, peaks = choose_frames(grid, curve, 24, ZETA)
        self.assertLessEqual(len(frames), 24)
        self.assertEqual([round(float(grid[i]), 1) for i in peaks], [123.4])
        self.assertIn(peaks[0], frames)
        self.assertEqual((frames[0], frames[-1]), (0, len(grid) - 1))
        self.assertEqual(choose_frames(grid, curve, 1, ZETA)[0], peaks)


def _glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length]), raw[20 + length + 8:]


def _ends(listing) -> tuple[str, str]:
    by_x = {face.center_mm[0]: face.ref for face in listing.faces
            if face.surface == "plane" and face.normal is not None and abs(abs(face.normal[0]) - 1) < 1e-6}
    return by_x[min(by_x)], by_x[max(by_x)]


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class ShakenCantilever(unittest.TestCase):
    """The clamped beam shaken at 1 g along Z from 10 to 600 Hz, through its first mode (490 Hz)."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, export_step

        from cadgen import fea

        cls._tmp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        cls.step = cls.directory / "beam.step"
        export_step(Box(LENGTH, SIDE, SIDE, align=(Align.MIN, Align.CENTER, Align.CENTER)), str(cls.step))
        cls.fixed, cls.tip = _ends(fea.faces(cls.step))
        cls.study = _study(fixtures=[{"faces": [cls.fixed]}], mesh={"size_mm": 2.0}, damping_ratio=ZETA, view={"checks": [
            {"kind": "stress"}, {"kind": "acceleration", "limit_g": 10, "faces": [cls.tip], "label": "Tip"},
            {"kind": "displacement", "limit_mm": 1.0}]})
        with redirect_stderr(io.StringIO()):
            cls.result = fea.solve(cls.step, cls.directory / "beam.fea.glb", study=cls.study)
        cls.summary = cls.result.summary
        cls.f1 = cls.summary["modes"][0]["frequency_Hz"]
        cls.sidecar = json.loads(cls.result.sidecar.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _theory_at_f1(self) -> float:
        omega1 = 2 * math.pi * self.f1
        return 1.566 * G0 / omega1 ** 2 / (2 * ZETA)

    def test_at_its_first_mode_the_tip_moves_as_the_resonance_amplifies(self):
        self.assertAlmostEqual(self.summary["peak_Hz"] / self.f1, 1.0, delta=0.005)
        # The tip moves most; relative to the clamp, 1.566·a/ω1² amplified by 1/(2ζ).
        self.assertAlmostEqual(self.summary["max_displacement_at_mm"][0], LENGTH, delta=1e-6)
        self.assertAlmostEqual(self.summary["max_displacement_mm"] / self._theory_at_f1(), 1.0, delta=0.10)

    def test_far_below_it_follows_the_shake_and_bends_as_under_a_steady_g(self):
        curve = self.sidecar["curves"]["max_displacement_mm"]
        self.assertEqual((curve["x"][0], curve["x_unit"], curve["y_unit"]), (10.0, "Hz", "mm"))
        q = STEEL.density * SIDE * SIDE * G0
        static = q * LENGTH ** 4 / (8 * STEEL.E * SIDE ** 4 / 12)
        self.assertAlmostEqual(curve["y"][0] / static, 1.0, delta=0.10)
        # Absolute acceleration: the base's own 1 g, far below resonance.
        self.assertAlmostEqual(self.sidecar["curves"]["max_acceleration_g"]["y"][0], 1.0, delta=0.01)

    def test_the_checks_say_where_and_at_which_frequency(self):
        stress, tip, moved = self.summary["checks"]
        series = self.sidecar["series"]
        self.assertEqual((stress["status"], stress["at"]["frame"]), ("passes", series["default"]))
        self.assertAlmostEqual(stress["value"], self.summary["max_von_mises_MPa"])
        self.assertEqual((tip["kind"], tip["unit"], tip["status"], tip["label"], tip["faces"]), ("acceleration", "g", "fails", "Tip", [self.tip]))
        omega1 = 2 * math.pi * self.f1
        self.assertAlmostEqual(tip["value"] / (omega1 ** 2 * self._theory_at_f1() / G0), 1.0, delta=0.10)
        self.assertEqual(tip["at"]["frame"], series["default"])
        self.assertEqual((moved["status"], moved["unit"]), ("passes", "mm"))
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["acceleration_over_limit"]["severity"], "error")
        self.assertIn(f"The checked faces shake at {tip['value']:.3g} g at 490 Hz, more than the 10 g allowed (Tip)",
                      found["acceleration_over_limit"]["summary"])
        self.assertTrue(found["resonance"]["summary"].startswith("Resonates at 490 Hz (mode 1)"))

    def test_modes_holding_too_little_mass_are_said(self):
        # Up to 900 Hz only the first bending mode moves along Z: about 61 % of the mass.
        self.assertAlmostEqual(self.summary["effective_mass_fraction"], 0.613, delta=0.03)
        self.assertEqual((self.summary["effective_mass_axis"], self.summary["modes_up_to_Hz"]), ("Z", 900.0))
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertEqual(found["modes_missing_mass"]["severity"], "warning")
        self.assertIn("The modes up to 900 Hz move only 61% of the mass along Z", found["modes_missing_mass"]["summary"])

    def test_the_glb_carries_a_frequency_series_with_both_parts_of_the_motion(self):
        gltf, _ = _glb(self.result.glb)
        extras = gltf["meshes"][0]["extras"]
        attributes = gltf["meshes"][0]["primitives"][0]["attributes"]
        self.assertEqual(extras["analysis"]["type"], "harmonic")
        self.assertEqual([field["field"] for field in extras["fields"]], ["von_mises", "displacement"])
        self.assertTrue(all(field["per_frame"] for field in extras["fields"]))
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"]), ("frequency", "Hz"))
        values = [frame["value"] for frame in series["frames"]]
        self.assertTrue(len(values) <= 24 and values == sorted(values) and values[0] == 10.0 and values[-1] == 600.0)
        self.assertEqual(series["frames"][series["default"]]["label"], "490 Hz")
        self.assertEqual(series["frames"][0]["attributes"],
                         {"von_mises": "_VON_MISES", "displacement": "_DISPLACEMENT", "displacement_im": "_DISPLACEMENT_IM_F0"})
        for index, frame in enumerate(series["frames"]):
            self.assertEqual(frame["attributes"]["displacement_im"], f"_DISPLACEMENT_IM_F{index}")
            self.assertEqual(gltf["accessors"][attributes[frame["attributes"]["displacement_im"]]]["type"], "VEC3")
            if index:
                self.assertEqual(gltf["accessors"][attributes[frame["attributes"]["von_mises"]]]["type"], "SCALAR")
        self.assertEqual(extras["study"]["excitation"], {"type": "base", "direction": [0.0, 0.0, 1.0], "amplitude_g": 1.0})
        self.assertEqual((extras["study"]["sweep_Hz"], extras["study"]["damping_ratio"]), ([10.0, 600.0], ZETA))

    def test_the_sidecar_and_the_cli_lines(self):
        self.assertEqual((self.sidecar["analysis"], sorted(self.sidecar["curves"])), ("harmonic", ["max_acceleration_g", "max_displacement_mm"]))
        lines = self.result.human_lines()
        self.assertIn("(harmonic)", lines[0])
        self.assertEqual(lines[1], "shaken 1 g along Z from 10 to 600 Hz, 2% damping; strongest at 490 Hz")
        self.assertTrue(lines[3].startswith("2 modes up to 900 Hz, holding 61% of the mass along Z"))

    def test_an_oversized_model_completes_by_keeping_the_modes_that_move_with_the_shake(self):
        from cadgen import fea

        study = {**self.study, "fit": {"memory_GB": 0.01, "allow": ["reduce_modes"]}}
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "tight.fea.glb", study=study)
        self.assertTrue(result.ok)
        self.assertEqual([step["rung"] for step in result.fit][0], "reduce_modes")
        words = "Kept 1 of the 2 modes up to 900 Hz, the ones holding 61% of the mass moving along Z, to fit"
        self.assertEqual(result.fit[0]["words"], words)
        self.assertEqual(result.fit[0]["detail"]["kept_modes"], 1)
        self.assertEqual((result.summary["modes_used"], result.summary["kept_share"]), (1, round(result.fit[0]["detail"]["kept_share"], 4)))
        gltf, _ = _glb(result.glb)
        self.assertIn(words, [step["words"] for step in gltf["meshes"][0]["extras"]["fit"]])
        self.assertIn(words, [step["words"] for step in json.loads(result.sidecar.read_text(encoding="utf-8"))["fit"]])
        self.assertIn(f"adapted: {words}", result.human_lines())
        self.assertIn("fit_reduce_modes", [finding["type"] for finding in result.findings])
        # The mode that carries the shake is kept: the benchmark still holds.
        self.assertAlmostEqual(result.summary["max_displacement_mm"] / self._theory_at_f1(), 1.0, delta=0.10)

    def test_a_force_shake_resonates_at_the_same_mode(self):
        from cadgen import fea

        study = _study(fixtures=[{"faces": [self.fixed]}], mesh={"size_mm": 2.0}, excitation={"type": "force"},
                       loads=[{"faces": [self.tip], "type": "force", "vector_N": [0, 0, 1]}], sweep_Hz=[10, 600])
        with redirect_stderr(io.StringIO()):
            result = fea.solve(self.step, self.directory / "force.fea.glb", study=study)
        # A 1 N tip force: static PL³/(3EI), amplified by about 1/(2ζ) at f1 (mode 1 holds ~97 % of the tip's static compliance).
        static = LENGTH ** 3 / (3 * STEEL.E * SIDE ** 4 / 12)
        self.assertAlmostEqual(result.summary["peak_Hz"] / self.f1, 1.0, delta=0.005)
        self.assertAlmostEqual(result.summary["max_displacement_mm"] / (0.97 * static / (2 * ZETA)), 1.0, delta=0.10)
        self.assertEqual(result.summary["excitation"], {"type": "force", "applied_N": [0.0, 0.0, 1.0]})


if __name__ == "__main__":
    unittest.main()
