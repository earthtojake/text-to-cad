"""Contact: the study it takes, the benchmarks, the GLB and the ladder.

Benchmarks (spec section 13):
- two stacked blocks, frictionless, pressed by F: the contact pressure is F/A
  everywhere on the face, within 2 % (through ``cadgen.fea.solve``; a third
  block glued on top shows every other touching pair stays bonded);
- the same blocks pulled apart: no contact pressure, and the fixed block takes
  no load (a contact never pulls), the loose block said to come loose;
- a sphere on a flat (Hertz): a quarter of a steel hemisphere pressed on a
  steel block, symmetric about two planes, on the engine with a mesh refined
  where they touch: the contact radius a = (3FR/4E*)^(1/3) and the peak pressure
  p0 = 3F/(2πa²) within 15 %. The radius is read from the contact forces'
  second moment (a Hertz pressure has Σ p r² / Σ p = 2a²/5), so it does not
  hang on which point happens to be the last one touching;
- a block on a rigid plane with friction 0.4, pushed sideways at half and at
  twice what friction holds: it sticks, then slides with a friction force of
  μ N exactly;
- a tiny budget: the stacked blocks still complete, by growing their load steps,
  and say so everywhere.

Every geometry is a build123d box or sphere written to a temporary STEP. Parse
tests are stdlib only; the solves need the fea extra.
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
from cadgen._internal.fea.analyses.contact import contact_words  # noqa: E402
from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402
from cadgen._internal.fea.study import parse_study  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

FORCE = 1000.0
AREA = 100.0


def _study(**more) -> dict:
    return {"analysis": "contact", "material": "steel", "fixtures": [{"faces": ["#o1.1.f1"]}],
            "loads": [{"faces": ["#o1.2.f2"], "type": "force", "vector_N": [0, 0, -100]}],
            "connections": [{"between": ["pin", "plate"], "type": "contact", "friction": 0.2}], **more}


class StudyFile(unittest.TestCase):
    def test_it_takes_contact_pairs_rigid_planes_and_steps(self):
        parsed = parse_study(_study(rigid_planes=[{"point_mm": [0, 0, -5], "normal": [0, 0, 2], "parts": ["plate"]}]))
        inputs = parsed.inputs
        self.assertEqual((parsed.analysis, inputs.steps, inputs.requires_anchor), ("contact", 5, False))
        (pair,) = inputs.pairs
        self.assertEqual((pair.between, pair.friction), (("pin", "plate"), 0.2))
        (plane,) = inputs.planes
        self.assertEqual((plane.point, plane.normal, plane.parts, plane.friction), ((0, 0, -5), (0, 0, 1), ("plate",), 0.0))
        self.assertEqual([(c.between, c.type) for c in parsed.connections], [(("pin", "plate"), "contact")])
        self.assertEqual(parsed.checks, ({"kind": "stress"},))
        checks = parse_study(_study(steps=3, view={"checks": [{"kind": "contact_pressure", "limit_MPa": 400, "faces": ["#o1.1.f3"]}]}))
        self.assertEqual(checks.checks, ({"kind": "contact_pressure", "limit_MPa": 400.0, "faces": ["#o1.1.f3"]},))
        self.assertEqual(checks.inputs.steps, 3)
        # A rigid plane alone holds a part: no fixture needed, and no pair.
        alone = parse_study({"analysis": "contact", "material": "steel", "rigid_planes": [{"point_mm": [0, 0, 0], "normal": [0, 0, 1]}],
                             "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -1]}]})
        self.assertEqual((alone.inputs.fixtures, alone.inputs.pairs), ((), ()))

    def test_only_contact_accepts_contact_pairs_and_bonded_stays_the_default(self):
        self.assertEqual(get_analysis("contact").connection_types, ("bonded", "free", "contact"))
        for name in ("static", "nonlinear", "modal"):
            with self.subTest(analysis=name):
                self.assertNotIn("contact", get_analysis(name).connection_types)
        study = {key: value for key, value in _study().items() if key != "analysis"}
        with self.assertRaisesRegex(ValueError, r"connections\[0\]\.type: 'contact' connections are not yet supported"):
            parse_study({**study, "connections": [{"between": ["pin", "plate"], "type": "contact"}]})
        with self.assertRaisesRegex(ValueError, r"connections\[0\]\.type: 'contact' connections are not yet supported"):
            parse_study({**study, "analysis": "nonlinear", "material": {"name": "steel", "plasticity": {"tangent_MPa": 0}},
                         "connections": [{"between": ["pin", "plate"], "type": "contact"}]})

    def test_the_errors_say_what_to_add(self):
        no_contact = {key: value for key, value in _study().items() if key != "connections"}
        cases = [
            (no_contact, "needs a contact"),
            ({**_study(), "fixtures": []}, "nothing holds the parts still"),
            (_study(connections=[{"between": ["pin", "plate"], "type": "contact", "friction": 3}]), "from 0 \\(frictionless\\) to 2"),
            (_study(connections=[{"between": ["pin", "plate"], "type": "free", "friction": 0.2}]), "only a contact connection slides"),
            (_study(connections=[{"between": ["pin", "plate"], "type": "contact", "grip": 1}]), r"unknown keys \['grip'\]"),
            (_study(rigid_planes=[{"point_mm": [0, 0, 0], "normal": [0, 0, 0]}]), "the normal is zero"),
            (_study(rigid_planes=[{"point_mm": [0, 0], "normal": [0, 0, 1]}]), "point_mm: a point on the plane"),
            (_study(rigid_planes=[{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "size": 3}]), r"unknown keys \['size'\]"),
            (_study(steps=0), "from 1 to 200"),
            (_study(material={"name": "rubber", "hyperelastic": {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}}),
             "a material here has none"),
            (_study(view={"checks": [{"kind": "contact_pressure"}]}), "limit_MPa"),
        ]
        for study, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, fragment):
                parse_study(study)

    def test_its_ladder_controls_limits_and_words(self):
        analysis = get_analysis("contact")
        self.assertEqual(analysis.ladder, get_analysis("nonlinear").ladder)
        self.assertEqual((analysis.tier, analysis.word), (3, "Contact"))
        self.assertNotIn("load_scale", analysis.drives)
        self.assertEqual([spec.name for spec in analysis.fields], ["von_mises", "displacement", "contact_pressure"])
        self.assertTrue(any(limit.startswith("Small sliding") for limit in analysis.limits))
        self.assertTrue(any("Node-to-surface" in limit for limit in analysis.limits))
        self.assertEqual(contact_words(("pin", "plate"), 0.2), "pin presses on plate, friction 0.2")
        self.assertEqual(contact_words(("pin", "plate"), 0.0), "pin presses on plate, no friction")


def _glb(path: Path) -> dict:
    raw = path.read_bytes()
    length, _ = struct.unpack_from("<II", raw, 12)
    return json.loads(raw[20:20 + length])


def _stack(directory: Path, *, cap: bool = False) -> tuple[Path, dict[str, str], object]:
    """base 10 x 10 x 20 at the origin, top 10 x 10 x 10 on it, and (``cap``) a 10 x 10 x 5 cap on top."""
    from build123d import Align, Box, Compound, Pos, export_step

    from cadgen.step_scene import read_scene

    base = Box(10, 10, 20, align=Align.MIN)
    base.label = "base"
    top = Pos(0, 0, 20) * Box(10, 10, 10, align=Align.MIN)
    top.label = "top"
    children = [base, top]
    if cap:
        lid = Pos(0, 0, 30) * Box(10, 10, 5, align=Align.MIN)
        lid.label = "cap"
        children.append(lid)
    step = directory / ("capped.step" if cap else "stack.step")
    export_step(Compound(children=children), str(step))
    scene = read_scene(step)
    return step, {leaf.label: leaf.ref for leaf in scene.leaves()}, scene


def _face(scene, part_ref: str, axis: int, value: float) -> str:
    from cadgen._internal.fea.mesh import face_area_center

    for selection in scene.resolve(part_ref).entities("face"):
        _, centre = face_area_center(selection.shape())
        if abs(centre[axis] - value) < 1e-6:
            return selection.ref
    raise AssertionError(f"no face of {part_ref} at {'xyz'[axis]} = {value}")


def _solve(step: Path, study: dict, name: str):
    from cadgen import fea

    with redirect_stderr(io.StringIO()):
        result = fea.solve(step, step.with_name(f"{name}.fea.glb"), study=study)
    sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
    return result, _glb(result.glb)["meshes"][0]["extras"], sidecar


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class StackedBlocks(unittest.TestCase):
    """A capped top block pressed on a base by 1000 N, frictionless; the cap is glued to the top (bonded, the default)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        directory = Path(cls._tmp.name)
        cls.step, refs, scene = _stack(directory, cap=True)
        cls.refs = refs
        cls.contact_face = _face(scene, refs["base"], 2, 20.0)
        study = {
            "analysis": "contact", "material": "steel", "mesh": {"size_mm": 3.0}, "steps": 2,
            "parts": {name: {"material": "steel"} for name in ("base", "top", "cap")},
            "connections": [{"between": ["top", "base"], "type": "contact"}],
            "fixtures": [{"faces": [_face(scene, refs["base"], 2, 0.0)]}],
            "loads": [{"faces": [_face(scene, refs["cap"], 2, 35.0)], "type": "force", "vector_N": [0, 0, -FORCE]}],
            "view": {"checks": [{"kind": "stress"}, {"kind": "contact_pressure", "limit_MPa": 12.0, "faces": [cls.contact_face]}]},
        }
        cls.result, cls.extras, cls.sidecar = _solve(cls.step, study, "capped")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_contact_pressure_is_force_over_area_within_2_percent(self):
        summary = self.result.summary
        (contact,) = summary["contacts"]
        self.assertTrue(contact["touching"])
        self.assertAlmostEqual(contact["force_N"] / FORCE, 1.0, delta=1e-3)
        self.assertAlmostEqual(contact["area_mm2"] / AREA, 1.0, delta=1e-3)
        self.assertAlmostEqual(contact["peak_MPa"] / (FORCE / AREA), 1.0, delta=0.02)
        self.assertAlmostEqual(summary["max_contact_pressure_MPa"] / (FORCE / AREA), 1.0, delta=0.02)
        self.assertAlmostEqual(summary["reaction_force_N"][2], FORCE, delta=1e-3 * FORCE)
        check = summary["checks"][1]
        self.assertEqual((check["kind"], check["unit"], check["status"], check["faces"]),
                         ("contact_pressure", "MPa", "passes", [self.contact_face]))
        self.assertAlmostEqual(check["value"] / (FORCE / AREA), 1.0, delta=0.02)

    def test_only_the_named_pair_is_a_contact_the_other_touching_pair_stays_bonded(self):
        types = {tuple(sorted(c["between"])): c["type"] for c in self.sidecar["connections"]}
        self.assertEqual(types, {("base", "top"): "contact", ("cap", "top"): "bonded"})
        self.assertEqual({c["type"] for c in self.extras["connections"]}, {"contact", "bonded"})

    def test_the_glb_carries_the_load_steps_and_the_contact_pressure(self):
        extras = self.extras
        self.assertEqual((extras["analysis"]["type"], extras["analysis"]["tier"], extras["analysis"]["word"]), ("contact", 3, "Contact"))
        self.assertTrue(extras["analysis"]["limits"])
        self.assertEqual([(f["field"], f["attribute"], f.get("per_frame")) for f in extras["fields"]],
                         [("von_mises", "_VON_MISES", True), ("displacement", "_DISPLACEMENT", True),
                          ("contact_pressure", "_CONTACT_PRESSURE", True)])
        series = extras["series"]
        self.assertEqual((series["kind"], series["unit"], series["default"]), ("time", "%", len(series["frames"]) - 1))
        self.assertEqual([frame["label"] for frame in series["frames"]], ["50 % load", "100 % load"])
        self.assertEqual(series["frames"][1]["attributes"]["contact_pressure"], "_CONTACT_PRESSURE_F1")
        self.assertEqual(extras["study"]["contact_pairs"], [{"between": ["top", "base"], "friction": 0.0}])
        self.assertEqual(extras["study"]["rigid_planes"], [])
        self.assertEqual(extras["contacts"][0]["words"], "top presses on base, no friction")
        self.assertIn("contact_force_N", self.sidecar["curves"])
        found = {finding["type"]: finding for finding in self.result.findings}
        self.assertIn("top presses on base: 1000 N over 100 mm²", found["contact_presses"]["summary"])
        self.assertIn("peaks at", found["peak_contact_pressure"]["summary"])
        self.assertTrue(any(line.startswith("top on base: presses with") for line in self.result.human_lines()))


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class PulledApart(unittest.TestCase):
    def test_a_contact_never_pulls_the_fixed_block_takes_no_load_and_the_top_comes_loose(self):
        with tempfile.TemporaryDirectory() as name:
            step, refs, scene = _stack(Path(name))
            study = {"analysis": "contact", "material": "steel", "mesh": {"size_mm": 4.0}, "steps": 1,
                     "connections": [{"between": ["top", "base"], "type": "contact", "friction": 0.3}],
                     "fixtures": [{"faces": [_face(scene, refs["base"], 2, 0.0)]}],
                     "loads": [{"faces": [_face(scene, refs["top"], 2, 30.0)], "type": "force", "vector_N": [0, 0, FORCE]}]}
            result, extras, sidecar = _solve(step, study, "pulled")
        self.assertTrue(result.ok)
        self.assertEqual(result.summary["max_contact_pressure_MPa"], 0.0)
        self.assertFalse(result.summary["contacts"][0]["touching"])
        self.assertEqual(result.summary["contacts"][0]["force_N"], 0.0)
        self.assertEqual(sidecar["fixtures"][0]["reaction_N"], [0.0, 0.0, 0.0])  # no tension reaches the base
        self.assertEqual(extras["fields"][2]["max"], 0.0)
        found = {finding["type"]: finding for finding in result.findings}
        self.assertEqual(found["comes_loose"]["severity"], "error")
        self.assertTrue(found["comes_loose"]["summary"].startswith("'top' comes loose"))
        self.assertIn("they separate under this load", found["contact_separates"]["summary"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class RigidPlaneFriction(unittest.TestCase):
    """A 20 x 20 x 4 mm steel plate on a rigid floor with friction 0.4, pressed down by N = 1000 N and pushed sideways."""

    def _push(self, sideways: float):
        from build123d import Align, Box, export_step

        from cadgen import fea

        with tempfile.TemporaryDirectory() as name:
            step = Path(name) / "plate.step"
            export_step(Box(20, 20, 4, align=Align.MIN), str(step))
            top = next(face.ref for face in fea.faces(step).faces if face.normal and face.normal[2] > 0.999)
            study = {"analysis": "contact", "material": "steel", "mesh": {"size_mm": 5.0}, "steps": 2,
                     "rigid_planes": [{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "friction": 0.4}],
                     "loads": [{"faces": [top], "type": "force", "vector_N": [sideways, 0, -FORCE]}]}
            result, extras, _ = _solve(step, study, "plate")
        return result, extras

    def test_it_sticks_under_friction_times_the_load_and_slides_past_it(self):
        held, extras = self._push(0.2 * FORCE)
        (floor,) = held.summary["contacts"]
        self.assertEqual(floor["name"], "the rigid plane")
        # Some slip at the rim, where the floor holds back the plate's own sideways bulge, but it holds.
        self.assertLess(floor["slipping_share"], 1.0)
        self.assertAlmostEqual(floor["force_N"] / FORCE, 1.0, delta=1e-3)
        self.assertAlmostEqual(floor["friction_N"] / (0.2 * FORCE), 1.0, delta=1e-3)  # it holds the whole push
        self.assertFalse({"slides_away", "comes_loose"} & {finding["type"] for finding in held.findings})
        self.assertEqual(extras["study"]["rigid_planes"], [{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "parts": [], "friction": 0.4}])
        sliding, _ = self._push(0.8 * FORCE)
        (floor,) = sliding.summary["contacts"]
        self.assertEqual(floor["slipping_share"], 1.0)
        found = {finding["type"]: finding for finding in sliding.findings}
        self.assertIn("slides over 100 % of the contact (friction 0.4)", found["contact_slides"]["summary"])
        # Sliding, the floor holds it back by friction times the load, μ N = 400 N, and no more: the rest is unheld.
        self.assertAlmostEqual(floor["friction_N"] / (0.4 * FORCE), 1.0, delta=1e-3)
        self.assertEqual(found["slides_away"]["severity"], "error")
        self.assertIn("cannot hold 400 N of its load sideways", found["slides_away"]["summary"])


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Hertz(unittest.TestCase):
    """A quarter of a steel hemisphere (R = 10 mm) pressed on a steel block by 20 kN, symmetric about x = 0 and y = 0."""

    R, FORCE = 10.0, 20_000.0

    def test_the_contact_radius_and_peak_pressure_are_hertz_s(self):
        import numpy as np
        from build123d import Align, Box, Compound, Pos, Sphere, export_step
        from skfem import LinearForm, asm

        from cadgen._internal.fea import contact_ops, nonlinear_driver, operators
        from cadgen._internal.fea.femspace import FemSpace
        from cadgen._internal.fea.materials import lookup_material
        from cadgen._internal.fea.mesh import mesh_assembly
        from cadgen.step_scene import read_scene

        R, height, fine = self.R, 6.0, 0.3
        with tempfile.TemporaryDirectory() as name:
            ball = Pos(0, 0, R) * Sphere(R) & Box(R, R, R, align=Align.MIN)
            ball.label = "ball"
            block = Pos(0, 0, -height) * Box(8, 8, height, align=Align.MIN)
            block.label = "block"
            step = Path(name) / "hertz.step"
            export_step(Compound(children=[ball, block]), str(step))
            scene = read_scene(step)
            leaves = list(scene.leaves())
            grid = np.arange(0.0, 2.5 + 1e-9, fine)
            points = [[float(x), float(y), z, fine] for x in grid for y in grid for z in (-fine / 2, fine / 2) if math.hypot(x, y) <= 2.5]
            volume = mesh_assembly(scene, [leaf.ref for leaf in leaves], [], 0.1, 3.0, size_field={"points": points, "radius_mm": 0.0})
        space = FemSpace.build(volume, 2)
        steel = lookup_material("steel")
        names = [leaf.label for leaf in leaves]
        basis, where, component = space.basis, space.locations, space.component
        held = (np.isclose(where[:, 0], 0) & (component == 0)) | (np.isclose(where[:, 1], 0) & (component == 1)) | np.isclose(where[:, 2], -height)
        free = np.flatnonzero(~held)
        top = np.flatnonzero(np.isclose(space.dof_locations[space.boundary_quadratic[:, :3]][:, :, 2], R).all(axis=1))
        facets = basis.boundary(space.facets_of_rows(top))
        traction = self.FORCE / 4 / float(facets.dx.sum())

        @LinearForm
        def push(v, w):
            return -traction * v[2]

        external = asm(push, facets)
        K = operators.stiffness(space, [steel, steel]).tocsr()
        node_part, node_body = contact_ops.body_of_nodes(space)
        pair = contact_ops.PairSpec(names.index("ball"), names.index("block"), 0.0, 0)
        constraints = contact_ops.pair_constraints(space, pair, node_part, steel.E, search_mm=1.5, tolerance_mm=0.1)
        vdofs = contact_ops.vector_dofs(space)
        ball_body = int(node_body[space.boundary_quadratic[top[0], 0]])
        stabilise = contact_ops.stabilising_springs(K, basis.N, [vdofs[node_body == ball_body].ravel()])
        moved = contact_ops.close_gaps(constraints, node_body, vdofs, external, [ball_body])
        self.assertGreater(np.abs(moved).max(), 0.0)  # the ball first drops onto the block, rigidly
        problem = contact_ops.ContactProblem(space, K, free, external, constraints, stabilise)
        path = nonlinear_driver.solve_path(problem, steps=3, runaway=None)
        self.assertFalse(path.collapsed)

        p = problem.response(path.u).normal_force
        self.assertAlmostEqual(4 * p.sum() / self.FORCE, 1.0, delta=2e-3)
        r = np.hypot(constraints.position[:, 0], constraints.position[:, 1])
        radius = math.sqrt(2.5 * float((p * r ** 2).sum()) / float(p.sum()))
        pressure = contact_ops.pressure_field(space, constraints, p)
        peak = float(pressure[constraints.node].max())
        e_star = steel.E / (2 * (1 - steel.nu ** 2))
        a = (3 * self.FORCE * R / (4 * e_star)) ** (1 / 3)
        p0 = 3 * self.FORCE / (2 * math.pi * a ** 2)
        self.assertAlmostEqual(radius / a, 1.0, delta=0.15)
        self.assertAlmostEqual(peak / p0, 1.0, delta=0.15)


@unittest.skipUnless(HAVE_FEA, "the fea extra (netgen-mesher, scikit-fem, pyamg) is not installed")
class Ladder(unittest.TestCase):
    def test_stacked_blocks_over_a_tiny_budget_complete_by_adapting_and_say_so(self):
        with tempfile.TemporaryDirectory() as name:
            step, refs, scene = _stack(Path(name))
            study = {"analysis": "contact", "material": "steel", "mesh": {"size_mm": 3.0}, "steps": 4,
                     "connections": [{"between": ["top", "base"], "type": "contact"}],
                     "fixtures": [{"faces": [_face(scene, refs["base"], 2, 0.0)]}],
                     "loads": [{"faces": [_face(scene, refs["top"], 2, 30.0)], "type": "force", "vector_N": [0, 0, -FORCE]}],
                     "fit": {"seconds": 0.001, "allow": ["iterative", "adaptive_steps"]}}
            result, extras, sidecar = _solve(step, study, "budget")
        self.assertTrue(result.ok)
        rungs = [step["rung"] for step in result.fit]
        self.assertIn("adaptive_steps", rungs)
        self.assertEqual(rungs[-1], "budget")  # still over a 1 ms target: it ran anyway and says what to expect
        summary = result.summary
        self.assertEqual((summary["collapsed"], summary["adaptive"], summary["load_percent"]), (False, True, 100.0))
        self.assertLess(summary["steps"], 4)  # the steps grew
        self.assertAlmostEqual(summary["max_contact_pressure_MPa"] / (FORCE / AREA), 1.0, delta=0.03)
        words = next(step["words"] for step in result.fit if step["rung"] == "adaptive_steps")
        self.assertIn("contacts settle", words)
        self.assertIn(words, [step["words"] for step in extras["fit"]])
        self.assertIn(words, [step["words"] for step in sidecar["fit"]])
        self.assertTrue(any(line.startswith(f"adapted: {words}") for line in result.human_lines()))
        self.assertIn("fit_adaptive_steps", [finding["type"] for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
