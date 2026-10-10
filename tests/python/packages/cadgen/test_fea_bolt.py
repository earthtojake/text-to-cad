"""Bolted joint: the study it takes, the hand calcs, the benchmarks, the GLB and the ladder.

Benchmarks (an M6 class 8.8 bolt, 5 kN preload, steel parts):

- two round plates as wide as the bolt head (OD = d_w = 8.88 mm, 6.6 mm hole, 6 mm thick
  each), the lower one held at its bottom face (where the nut bears), the upper one pulled
  off it by F_A on its top face (where the head bears, so the load comes in under the head:
  VDI 2230's n = 1):
  - at the preload, before any load, the clamped faces carry the preload within 2 %;
  - the bolt's share of the load matches the joint-stiffness hand calc
    Phi = k_b / (k_b + k_c) within 15 %, with k_b from VDI 2230 Part 1 (2015) section 5.1.1
    (hexagon head 0.5 d and nut 0.4 d on the nominal section, the engaged thread 0.5 d on the
    minor section, a plain shank through l_K = 12 mm) and k_c from section 5.1.2.2 for parts
    no wider than the head (D_A <= d_w): the sleeve, E pi (D_A^2 - d_h^2) / (4 l_K);
  - the faces open at F_A = F_V / (1 - Phi) within 15 %, after which the bolt carries the
    whole load;
- two 24 mm square plates, the upper one pushed sideways at its end, friction 0.2: the
  joint slips at mu * F_V * 1 interface within 5 %;
- a tiny budget: the round plates still complete, by growing their load steps, and say so.

Every geometry is a build123d solid written to a temporary STEP. Parse tests are stdlib
only; the solves need the fea extra.
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
from cadgen._internal.fea.analyses.bolt import bolt_words, force_words  # noqa: E402
from cadgen._internal.fea.bolt_ops import (  # noqa: E402
    SIZES, bolt_compliance, joint_compliance, load_factor, preload_from_torque, proof_load,
)
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

PRELOAD = 5000.0
E_STEEL = 200_000.0          # the material table's steel, for the parts and the bolt
D, P, D_W, D_H = 6.0, 1.0, 8.88, 6.6
THICK = 6.0
L_K = 2 * THICK


def hand_load_factor() -> tuple[float, float, float]:
    """(k_b, k_c, Phi) by VDI 2230 for the round plates (module docstring), written out here on their own."""
    a_n = math.pi * D ** 2 / 4
    d3 = D - 1.22687 * P
    a_d3 = math.pi * d3 ** 2 / 4
    k_b = 1.0 / ((0.5 * D / a_n + L_K / a_n + 0.5 * D / a_d3 + 0.4 * D / a_n) / E_STEEL)
    k_c = E_STEEL * math.pi * (D_W ** 2 - D_H ** 2) / 4 / L_K
    return k_b, k_c, k_b / (k_b + k_c)


def _bolt(**more) -> dict:
    return {"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": PRELOAD,
            "holes": ["#o1.1.f3", "#o1.2.f3"], **more}


def _study(**more) -> dict:
    return {"analysis": "bolt", "material": "steel", "fixtures": [{"faces": ["#o1.2.f1"]}], "connections": [_bolt()], **more}


class StudyFile(unittest.TestCase):
    def test_it_takes_bolts_with_a_preload_or_a_torque(self):
        parsed = parse_study(_study())
        (bolt,) = parsed.inputs.bolts
        self.assertEqual((parsed.analysis, bolt.between, bolt.size.name, bolt.preload_N, bolt.grade, bolt.friction),
                         ("bolt", ("plate", "bracket"), "M6", PRELOAD, "8.8", 0.2))
        self.assertEqual(parsed.inputs.face_refs, ("#o1.2.f1", "#o1.1.f3", "#o1.2.f3"))
        self.assertEqual((parsed.inputs.loads, parsed.inputs.requires_anchor, parsed.inputs.steps), ((), False, 5))
        self.assertEqual([check["kind"] for check in parsed.checks], ["bolt_load", "joint_separation", "joint_slip"])
        self.assertEqual([(c.between, c.type) for c in parsed.connections], [(("plate", "bracket"), "bolt")])
        # A torque: F = T / (K d), K 0.2 by default; a size by its diameter; a grade and friction of its own.
        by_torque = {key: value for key, value in _bolt().items() if key != "preload_N"}
        torqued = parse_study(_study(connections=[{**by_torque, "torque_Nm": 10, "size": {"diameter_mm": 8}, "grade": "10.9",
                                                   "friction": 0.15}]))
        (bolt,) = torqued.inputs.bolts
        self.assertAlmostEqual(bolt.preload_N, 10_000 / (0.2 * 8), places=9)
        self.assertEqual((bolt.size.name, bolt.grade, bolt.friction, bolt.nut_factor), ("M8", "10.9", 0.15, 0.2))
        self.assertAlmostEqual(bolt.proof_N, 830 * 36.6, places=6)
        self.assertEqual(bolt_words(parsed.inputs.bolts[0]), "M6 bolt, 5 kN preload, clamps plate and bracket")
        # Several bolts may clamp the same two parts.
        two = parse_study(_study(connections=[_bolt(), _bolt(holes=["#o1.1.f4", "#o1.2.f4"])]))
        self.assertEqual(len(two.inputs.bolts), 2)

    def test_only_the_bolt_analysis_accepts_bolts(self):
        self.assertEqual(get_analysis("bolt").connection_types, ("bonded", "free", "contact", "bolt"))
        for name in ("static", "contact", "nonlinear"):
            with self.subTest(analysis=name):
                self.assertNotIn("bolt", get_analysis(name).connection_types)
        with self.assertRaisesRegex(ValueError, r"connections\[0\]\.type: 'bolt' connections are not yet supported"):
            parse_study({**_study(), "analysis": "static", "loads": [{"faces": ["#o1.1.f2"], "type": "force", "vector_N": [0, 0, 1]}]})
        with self.assertRaisesRegex(ValueError, r"connections\[0\]: unknown keys \['holes', 'preload_N', 'size'\]"):
            parse_study({**_study(), "analysis": "contact", "loads": [{"faces": ["#o1.1.f2"], "type": "force", "vector_N": [0, 0, 1]}]})

    def test_the_errors_say_what_to_add(self):
        no_bolt = {key: value for key, value in _study().items() if key != "connections"}
        both = {k: v for k, v in _bolt().items()}
        cases = [
            (no_bolt, "a bolt study needs a bolt"),
            ({**_study(), "fixtures": []}, "nothing holds the parts still"),
            (_study(connections=[{**both, "size": "M7"}]), 'a metric size like "M6"'),
            (_study(connections=[{**both, "torque_Nm": 10}]), "exactly one"),
            (_study(connections=[{**both, "nut_factor": 0.2}]), "it goes with torque_Nm"),
            (_study(connections=[{**both, "grade": "7.7"}]), "the property class"),
            (_study(connections=[{**both, "friction": 3}]), "from 0 \\(frictionless\\) to 2"),
            (_study(connections=[{**both, "holes": []}]), "the hole walls"),
            (_study(connections=[{**both, "washer": True}]), r"unknown keys \['washer'\]"),
            (_study(connections=[both, {"between": ["plate", "bracket"], "type": "contact"}]), "leave out their contact connection"),
            (_study(connections=[both, {**both, "friction": 0.3}]), "different friction"),
            (_study(view={"checks": [{"kind": "joint_separation", "min_clamp_N": -1}]}), "zero or more"),
            (_study(view={"checks": [{"kind": "bolt_load", "limit_N": 0}]}), "must be > 0"),
        ]
        for study, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, fragment):
                parse_study(study)

    def test_its_ladder_checks_limits_and_words(self):
        analysis = get_analysis("bolt")
        self.assertEqual(analysis.ladder, get_analysis("contact").ladder)
        self.assertEqual((analysis.tier, analysis.word), (3, "Bolted joint"))
        self.assertNotIn("load_scale", analysis.drives)
        self.assertEqual([spec.name for spec in analysis.fields], ["von_mises", "displacement", "contact_pressure"])
        self.assertEqual([spec.kind for spec in analysis.checks][:3], ["bolt_load", "joint_separation", "joint_slip"])
        self.assertTrue(analysis.limits[0].startswith("Each bolt is a pretensioned spring"))
        self.assertTrue(any("No fatigue of the bolt yet" in limit for limit in analysis.limits))
        self.assertTrue(any(limit.startswith("Small sliding") for limit in analysis.limits))  # contact's, inherited
        parsed = parse_study(_study(view={"checks": [{"kind": "bolt_load", "limit_N": 9000}, {"kind": "joint_separation", "min_clamp_N": 500},
                                                     {"kind": "joint_slip", "label": "Shear"}]}))
        self.assertEqual(parsed.checks, ({"kind": "bolt_load", "limit_N": 9000.0}, {"kind": "joint_separation", "min_clamp_N": 500.0},
                                         {"kind": "joint_slip", "label": "Shear"}))
        self.assertEqual([force_words(800), force_words(5000), force_words(12500)], ["800 N", "5 kN", "12.5 kN"])


class HandCalcs(unittest.TestCase):
    def test_the_bolt_and_joint_stiffness_are_vdi_2230s(self):
        k_b, k_c, phi = hand_load_factor()
        bolt = bolt_compliance(SIZES["M6"], L_K, E_STEEL)
        sleeve = joint_compliance(D_W, D_H, L_K, D_W, E_STEEL)
        self.assertAlmostEqual(1 / bolt["total"] / k_b, 1.0, places=12)
        self.assertAlmostEqual(1 / sleeve["total"] / k_c, 1.0, places=12)
        self.assertEqual(sleeve["body"], "sleeve")
        self.assertAlmostEqual(load_factor(bolt["total"], sleeve["total"]), phi, places=12)
        self.assertAlmostEqual(phi, 0.356, delta=0.001)
        # Wider parts: the deformation cone, stiffer than the head-wide sleeve, and between the two a cone and sleeve.
        cone = joint_compliance(D_W, D_H, L_K, 40.0, E_STEEL)
        between = joint_compliance(D_W, D_H, L_K, 12.0, E_STEEL)
        self.assertEqual((cone["body"], between["body"]), ("cone", "cone and sleeve"))
        self.assertLess(cone["total"], between["total"])
        self.assertLess(between["total"], sleeve["total"])
        self.assertAlmostEqual(cone["tan_phi"], 0.362 + 0.032 * math.log(L_K / D_W / 2) + 0.153 * math.log(40 / D_W), places=12)

    def test_torque_to_preload_and_the_proof_load(self):
        self.assertAlmostEqual(preload_from_torque(10.0, 0.2, 6.0), 10_000 / 1.2)
        self.assertAlmostEqual(proof_load(SIZES["M6"], "8.8"), 580 * 20.1)
        self.assertAlmostEqual(proof_load(SIZES["M20"], "8.8"), 600 * 245)


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _joint(directory: Path, width: float | None):
    """Two plates with a 6.6 mm hole, 6 mm thick, stacked: round as wide as the head (``width`` None) or square."""
    from build123d import Align, Box, Compound, Cylinder, Pos, export_step

    from cadgen.step_scene import read_scene

    base = (Align.CENTER, Align.CENTER, Align.MIN)

    def plate(z: float):
        outer = Cylinder(D_W / 2, THICK, align=base) if width is None else Box(width, width, THICK, align=base)
        return Pos(0, 0, z) * (outer - Cylinder(D_H / 2, THICK, align=base))

    top, bottom = plate(THICK), plate(0.0)
    top.label, bottom.label = "plate", "bracket"
    step = directory / "joint.step"
    export_step(Compound(children=[top, bottom]), str(step))
    scene = read_scene(step)
    return step, {leaf.label: leaf.ref for leaf in scene.leaves()}, scene


def _face(scene, part_ref: str, axis: int, value: float, area: float | None = None) -> str:
    from cadgen._internal.fea.mesh import face_area_center

    for selection in scene.resolve(part_ref).entities("face"):
        found, centre = face_area_center(selection.shape())
        if abs(centre[axis] - value) < 1e-6 and (area is None or abs(found - area) < 1.0):
            return selection.ref
    raise AssertionError(f"no face of {part_ref} at {'xyz'[axis]} = {value}")


def _holes(scene, refs) -> list[str]:
    wall = math.pi * D_H * THICK
    return [_face(scene, refs["plate"], 2, 1.5 * THICK, wall), _face(scene, refs["bracket"], 2, 0.5 * THICK, wall)]


def _solve(step: Path, study: dict, name: str):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        result = fea.solve(step, step.with_name(f"{name}.fea.glb"), study=study)
    sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
    return result, _glb(result.glb)["meshes"][0]["extras"], sidecar


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class PulledApart(unittest.TestCase):
    """The round plates pulled apart by 10 kN in five steps: they open at about 7.8 kN, between the third and fourth."""

    LOAD = 10_000.0

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        step, refs, scene = _joint(Path(cls._tmp.name), None)
        study = {
            "analysis": "bolt", "material": "steel", "mesh": {"size_mm": 1.5}, "steps": 5,
            "parts": {name: {"material": "steel"} for name in ("plate", "bracket")},
            "connections": [{"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": PRELOAD,
                             "holes": _holes(scene, refs)}],
            "fixtures": [{"faces": [_face(scene, refs["bracket"], 2, 0.0)]}],
            "loads": [{"faces": [_face(scene, refs["plate"], 2, 2 * THICK)], "type": "force", "vector_N": [0, 0, cls.LOAD]}],
        }
        cls.result, cls.extras, cls.sidecar = _solve(step, study, "pulled")
        (cls.bolt,) = cls.result.summary["bolts"]
        (cls.joint,) = cls.result.summary["joints"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_at_the_preload_the_clamped_faces_carry_the_preload_within_2_percent(self):
        self.assertAlmostEqual(self.joint["preload_clamp_N"] / PRELOAD, 1.0, delta=0.02)
        self.assertAlmostEqual(self.sidecar["curves"]["bolt_force_N"]["y"][0], PRELOAD)
        self.assertAlmostEqual(self.bolt["clamp_length_mm"], L_K, delta=1e-6)
        self.assertAlmostEqual(self.bolt["head_bearing_mm2"] / (math.pi / 4 * (D_W ** 2 - D_H ** 2)), 1.0, delta=0.02)

    def test_the_bolts_share_of_the_load_is_the_joint_stiffness_hand_calcs_within_15_percent(self):
        _, _, phi = hand_load_factor()
        curve = self.sidecar["curves"]["bolt_force_N"]
        self.assertEqual(curve["x"][:2], [0.0, 20.0])
        share = (curve["y"][1] - PRELOAD) / (0.2 * self.LOAD)
        self.assertAlmostEqual(share / phi, 1.0, delta=0.15)
        self.assertAlmostEqual(self.bolt["hand"]["load_factor"], phi, delta=1e-4)  # the sidecar says the hand calc too
        self.assertEqual(self.bolt["hand"]["joint_body"], "sleeve")

    def test_the_faces_open_at_the_hand_calcs_load_within_15_percent_and_then_the_bolt_takes_it_all(self):
        _, _, phi = hand_load_factor()
        opens = self.joint["opens_at_percent"] / 100 * self.LOAD
        self.assertAlmostEqual(opens / (PRELOAD / (1 - phi)), 1.0, delta=0.15)
        self.assertTrue(self.joint["open"])
        self.assertAlmostEqual(self.bolt["force_N"] / self.LOAD, 1.0, delta=0.02)
        checks = {check["kind"]: check for check in self.result.summary["checks"]}
        self.assertEqual((checks["joint_separation"]["status"], checks["bolt_load"]["status"], checks["joint_slip"]["status"]),
                         ("fails", "passes", "passes"))
        self.assertAlmostEqual(checks["bolt_load"]["limit"], 580 * 20.1, places=3)
        self.assertEqual(self.result.summary["status"], "Joint opens")
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertTrue(found["joint_opens"]["summary"].startswith("The joint opens: plate and bracket separate at about"))

    def test_the_glb_carries_the_preload_then_the_load_steps(self):
        extras = self.extras
        self.assertEqual((extras["analysis"]["type"], extras["analysis"]["tier"], extras["analysis"]["word"]), ("bolt", 3, "Bolted joint"))
        series = extras["series"]
        self.assertEqual([frame["label"] for frame in series["frames"]][:2], ["Preload", "20 % load"])
        self.assertEqual((series["frames"][0]["value"], series["default"]), (0.0, len(series["frames"]) - 1))
        self.assertEqual([f["field"] for f in extras["fields"]], ["von_mises", "displacement", "contact_pressure"])
        (bolt,) = extras["study"]["bolts"]
        self.assertEqual((bolt["words"], bolt["size"], bolt["preload_N"]), ("M6 bolt, 5 kN preload, clamps plate and bracket", "M6", PRELOAD))
        self.assertEqual(extras["bolts"][0]["refs"], [c["refs"] for c in self.sidecar["connections"]][0])
        self.assertEqual({c["type"] for c in self.sidecar["connections"]}, {"contact"})
        self.assertTrue(any(line.startswith("bolt 1 (M6, 8.8): preload 5000 N") for line in self.result.human_lines()))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Slip(unittest.TestCase):
    def test_the_joint_slips_at_friction_times_the_preload(self):
        push = 1050.0
        with tempfile.TemporaryDirectory() as name:
            step, refs, scene = _joint(Path(name), 24.0)
            study = {
                "analysis": "bolt", "material": "steel", "mesh": {"size_mm": 4.0}, "steps": 5,
                "connections": [{"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": PRELOAD,
                                 "friction": 0.2, "holes": _holes(scene, refs)}],
                "fixtures": [{"faces": [_face(scene, refs["bracket"], 2, 0.0)]}],
                "loads": [{"faces": [_face(scene, refs["plate"], 0, 12.0)], "type": "force", "vector_N": [push, 0, 0]}],
            }
            result, _, _ = _solve(step, study, "slip")
        (joint,) = result.summary["joints"]
        self.assertAlmostEqual(joint["preload_clamp_N"] / PRELOAD, 1.0, delta=0.02)
        slips = joint["slips_at_percent"] / 100 * push
        self.assertAlmostEqual(slips / (0.2 * PRELOAD * 1), 1.0, delta=0.05)
        self.assertTrue(joint["slips"])
        check = next(check for check in result.summary["checks"] if check["kind"] == "joint_slip")
        self.assertEqual(check["status"], "fails")
        self.assertAlmostEqual(check["value"] / push, 1.0, delta=0.02)
        self.assertIn("joint_slips", [finding["type"] for finding in result.findings])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    def test_the_round_plates_over_a_tiny_budget_complete_by_adapting_and_say_so(self):
        load = 3000.0
        with tempfile.TemporaryDirectory() as name:
            step, refs, scene = _joint(Path(name), None)
            study = {
                "analysis": "bolt", "material": "steel", "mesh": {"size_mm": 1.5}, "steps": 4,
                "connections": [{"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": PRELOAD,
                                 "holes": _holes(scene, refs)}],
                "fixtures": [{"faces": [_face(scene, refs["bracket"], 2, 0.0)]}],
                "loads": [{"faces": [_face(scene, refs["plate"], 2, 2 * THICK)], "type": "force", "vector_N": [0, 0, load]}],
                "fit": {"seconds": 0.001, "allow": ["iterative", "adaptive_steps"]},
            }
            result, extras, sidecar = _solve(step, study, "budget")
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("adaptive_steps", rungs)
        self.assertEqual(rungs[-1], "budget")
        summary = result.summary
        self.assertEqual((summary["collapsed"], summary["adaptive"], summary["load_percent"]), (False, True, 100.0))
        self.assertLess(summary["steps"], 4)
        _, _, phi = hand_load_factor()
        self.assertAlmostEqual((summary["bolts"][0]["force_N"] - PRELOAD) / load / phi, 1.0, delta=0.15)
        words = next(step["words"] for step in result.fit if step["rung"] == "adaptive_steps")
        self.assertIn(words, [step["words"] for step in extras["fit"]])
        self.assertIn(words, [step["words"] for step in sidecar["fit"]])
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in result.human_lines()))
        self.assertIn("fit_adaptive_steps", [finding["type"] for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
