"""``cad.mujoco._compile``'s model-health checks: one tiny MJCF per check that trips it, a clean model that
trips none but the notes; and ``cad.mujoco.check`` (``cad mujoco check``): ``strict``, what a model collides as and
its contact excludes as data, and what is no MuJoCo model or one MuJoCo refuses. Each in a fresh temporary folder."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

#: The library's source tree, for a child Python that runs it (``cad._internal.operation``).
SOURCES = os.pathsep.join(path for path in sys.path if path)

import cad.mujoco  # noqa: E402
from cad.mujoco import _compile, _health  # noqa: E402

#: The notes a model may carry and still be clean.
NOTES = {"compiled", "home_key", "mass_summary", "defaults_not_recommended"}

# Tuned as the guide recommends, its visuals out of collision and of the mass, a home key in range.
CLEAN = """<mujoco model="clean">
  <option integrator="implicitfast" cone="elliptic" impratio="10" timestep="0.002"/>
  <default>
    <geom solref="0.005 1"/>
    <default class="visual"><geom group="2" contype="0" conaffinity="0" density="0"/></default>
    <default class="collision"><geom group="3"/></default>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="1 1 0.1"/>
    <body name="link" pos="0 0 0.5">
      <joint name="hinge" range="-90 90"/>
      <geom name="link_visual" class="visual" type="box" size="0.05 0.05 0.1"/>
      <geom name="link_collision" class="collision" type="box" size="0.05 0.05 0.1"/>
    </body>
  </worldbody>
  <keyframe><key name="home" qpos="0.2"/></keyframe>
</mujoco>
"""

INTERSECTING = """<mujoco model="overlap">
  <worldbody>
    <body name="left"><joint name="a" type="slide"/><geom name="left_box" type="box" size="0.1 0.1 0.1"/></body>
    <body name="right" pos="0.15 0 0"><joint name="b" type="slide"/>
      <geom name="right_box" type="box" size="0.1 0.1 0.1"/></body>
  </worldbody>
</mujoco>
"""

# A free box sunk 0.5 mm into the floor rests there; sunk 20 mm it intersects.
RESTING = """<mujoco model="rest"><worldbody><geom name="floor" type="plane" size="1 1 0.1"/>
  <body name="cube" pos="0 0 {z}"><freejoint/><geom name="cube_geom" type="box" size="0.05 0.05 0.05"/></body>
</worldbody></mujoco>
"""

VISUAL_COLLIDES = """<mujoco model="vis"><worldbody>
  <body name="link"><joint name="j"/>
    <geom name="shell_visual" type="sphere" size="0.1" group="2" density="0"/>
    <geom name="shell_collision" type="sphere" size="0.1" group="3"/>
  </body>
</worldbody></mujoco>
"""

DOUBLED = """<mujoco model="doubled"><worldbody>
  <body name="heavy"><joint name="j"/>
    <geom name="heavy_visual" type="sphere" size="0.1" group="2" contype="0" conaffinity="0"/>
    <geom name="heavy_collision" type="sphere" size="0.1" group="3"/>
  </body>
  <body name="declared" pos="1 0 0"><joint name="k"/>
    <inertial pos="0 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>
    <geom name="declared_visual" type="sphere" size="0.1" group="2" contype="0" conaffinity="0"/>
    <geom name="declared_collision" type="sphere" size="0.1" group="3"/>
  </body>
</worldbody></mujoco>
"""

MILLIMETRES = """<mujoco model="mm"><asset>
  <mesh name="bracket" vertex="0 0 0 250 0 0 0 250 0 0 0 250"/>
</asset><worldbody>
  <body name="arm"><joint name="j"/><geom name="arm_geom" type="box" size="400 20 20"/></body>
  <body name="part" pos="2000 0 0"><joint name="k"/><geom type="mesh" mesh="bracket"/></body>
</worldbody></mujoco>
"""

# The Panda's joint4: its range excludes 0, so qpos0 sits outside it; the home key does not.
PAST_LIMIT = """<mujoco model="panda_like"><worldbody>
  <body name="link4"><joint name="joint4" range="-3.0718 -0.0698" limited="true"/>
    <geom type="capsule" size="0.05" fromto="0 0 0 0 0 0.2"/></body>
</worldbody><compiler angle="radian"/>
<keyframe><key name="home" qpos="-2.3"/></keyframe></mujoco>
"""

EULER = """<mujoco model="old"><option timestep="0.01"/><worldbody><geom name="floor" type="plane" size="1 1 0.1"/>
  <body name="b" pos="0 0 1"><freejoint/><geom type="sphere" size="0.1"/></body></worldbody></mujoco>
"""


class Health(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def findings(self, text: str, name: str = "robot.xml") -> list:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return _compile.compile_findings(path).all_findings()

    def only(self, findings: list, code: str):
        found = [finding for finding in findings if finding.code == code]
        self.assertEqual(1, len(found), [f"{f.code}: {f.message}" for f in findings])
        return found[0]

    def test_a_clean_model_carries_notes_alone(self) -> None:
        findings = self.findings(CLEAN)
        codes = {finding.code for finding in findings}
        self.assertLessEqual(codes, NOTES - {"home_key", "defaults_not_recommended"},
                             [f"{f.code}: {f.message}" for f in findings])
        summary = self.only(findings, "mass_summary")
        self.assertIn("1 moving bodies", summary.message)
        self.assertIn("1 degrees of freedom (nv)", summary.message)
        self.assertIn("0 actuators (nu)", summary.message)

    def test_intersecting_geoms_are_named_with_their_depth(self) -> None:
        finding = self.only(self.findings(INTERSECTING), "contacts_at_rest")
        self.assertEqual("warning", finding.severity)
        self.assertIn("'left_box'", finding.message)
        self.assertIn("'right_box'", finding.message)
        self.assertIn("50 mm", finding.message)
        self.assertIn("at qpos0", finding.message)
        # Two boxes intersecting make several contacts: the pair is said once, with how many.
        self.assertTrue(finding.message.startswith("1 body pair(s) intersect at qpos0"), finding.message)
        self.assertEqual(1, finding.message.count("'left_box' and geom 'right_box'"), finding.message)
        self.assertRegex(finding.message, r"by 50 mm, \d+ contacts")

    def test_a_free_body_resting_on_the_floor_is_not_intersecting(self) -> None:
        resting = self.findings(RESTING.format(z=0.0495))
        self.assertNotIn("contacts_at_rest", {finding.code for finding in resting})
        sunk = self.only(self.findings(RESTING.format(z=0.03)), "contacts_at_rest")
        self.assertIn("'cube_geom'", sunk.message)

    def test_a_visual_geom_beside_collision_geoms_must_not_collide(self) -> None:
        finding = self.only(self.findings(VISUAL_COLLIDES), "visual_geoms_collide")
        self.assertIn("'shell_visual'", finding.message)
        self.assertNotIn("'shell_collision'", finding.message)

    def test_mass_from_visual_and_collision_geoms_is_counted_twice(self) -> None:
        finding = self.only(self.findings(DOUBLED), "inertia_from_visuals")
        self.assertIn("'heavy'", finding.message)
        self.assertNotIn("'declared'", finding.message)

    def test_millimetres_read_as_metres(self) -> None:
        finding = self.only(self.findings(MILLIMETRES), "scale_suspect")
        self.assertIn("more than 50 m", finding.message)
        self.assertIn("mesh 'bracket'", finding.message)
        self.assertIn("kg", finding.message)

    def test_a_joint_outside_its_range_at_rest(self) -> None:
        findings = self.findings(PAST_LIMIT)
        finding = self.only(findings, "joint_limits_at_rest")
        self.assertIn("'joint4'", finding.message)
        self.assertIn("at qpos0", finding.message)
        self.assertNotIn("home_key", {f.code for f in findings})

    def test_a_home_key_outside_a_range_says_so(self) -> None:
        findings = self.findings(PAST_LIMIT.replace('qpos="-2.3"', 'qpos="0.5"'))
        labels = [finding.message for finding in findings if finding.code == "joint_limits_at_rest"]
        self.assertEqual(2, len(labels))
        self.assertTrue(any("at key 'home'" in message for message in labels), labels)

    def test_unfortunate_defaults_and_a_missing_home_are_notes(self) -> None:
        findings = self.findings(EULER)
        defaults = self.only(findings, "defaults_not_recommended")
        self.assertEqual("info", defaults.severity)
        for said in ("Euler", "implicitfast", "pyramidal", "elliptic", "solref", "timestep 0.01"):
            self.assertIn(said, defaults.message)
        self.assertEqual("info", self.only(findings, "home_key").severity)

    def test_a_default_after_an_include_does_not_reach_the_included_model_and_says_so(self) -> None:
        # The robot's elements are in its class, as a generated robot's are.
        (self.folder / "arm.xml").write_text(
            '<mujoco model="arm"><default><default class="arm"><geom rgba="1 0 0 1"/></default></default>'
            '<worldbody><body name="link" pos="0 0 0.5" childclass="arm"><joint name="hinge" range="-90 90"/>'
            '<geom name="link_geom" type="box" size="0.05 0.05 0.1"/></body></worldbody></mujoco>', encoding="utf-8")
        default = ('<default><geom solref="0.005 1"/><joint armature="0.01"/>'
                   '<default class="servo"><position kp="10"/></default></default>')
        scene = ('<mujoco model="scene"><include file="arm.xml"/>{late}<worldbody>'
                 '<geom name="floor" type="plane" size="1 1 0.1"/></worldbody></mujoco>')
        finding = self.only(self.findings(scene.format(late=default), "scene.xml"), "defaults_after_include")
        self.assertEqual("warning", finding.severity)
        self.assertIn('after <include file="arm.xml"> sets geom, joint defaults', finding.message)
        # MuJoCo agrees: the robot's geom keeps the default solref and its joint no armature.
        import mujoco

        model = mujoco.MjModel.from_xml_path(str(self.folder / "scene.xml"))
        self.assertEqual((list(model.geom("link_geom").solref), float(model.dof_armature[0])), ([0.02, 1.0], 0.0))
        # Above the include, both apply and nothing is said; a late default of the scene's own classes alone is fine,
        # as is one after a file that defines no class (its elements take the top-level default as it ends).
        moved = scene.replace('<include file="arm.xml"/>{late}', default + '<include file="arm.xml"/>')
        self.assertNotIn("defaults_after_include", {f.code for f in self.findings(moved, "scene.xml")})
        model = mujoco.MjModel.from_xml_path(str(self.folder / "scene.xml"))
        self.assertEqual((list(model.geom("link_geom").solref), float(model.dof_armature[0])), ([0.005, 1.0], 0.01))
        classes = '<default><default class="servo"><position kp="10"/></default></default>'
        self.assertNotIn("defaults_after_include", {f.code for f in self.findings(scene.format(late=classes), "scene.xml")})

    def test_a_check_that_fails_inside_is_a_note(self) -> None:
        with mock.patch.object(_health, "_scale_suspect", side_effect=RuntimeError("boom")):
            findings = self.findings(CLEAN)
        finding = self.only(findings, "check_unavailable")
        self.assertEqual("info", finding.severity)
        self.assertIn("scale_suspect", finding.message)
        self.assertIn("mass_summary", {f.code for f in findings})


class Strict(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def validate(self, text: str):
        path = self.folder / "robot.xml"
        path.write_text(text, encoding="utf-8")
        return cad.mujoco.check(path, strict=True)

    def test_strict_fails_intersecting_geoms_and_passes_the_clean_model(self) -> None:
        failed = self.validate(INTERSECTING)
        self.assertFalse(failed.ok)
        self.assertIn("contacts_at_rest", {finding.code for finding in failed.findings})
        passed = self.validate(CLEAN)
        self.assertTrue(passed.ok, [f"{f.code}: {f.message}" for f in passed.findings])


# Three bodies in a row: a and b touch, c stands 50 mm off b, and d collides as nothing. Every pair is excluded.
EXCLUDED = """<mujoco model="row">
  <worldbody>
    <body name="a"><joint type="hinge"/><geom name="a_box" type="box" size="0.05 0.05 0.05"/></body>
    <body name="b" pos="0.1 0 0"><joint type="hinge"/><geom name="b_box" type="box" size="0.05 0.05 0.05"/>
      <geom name="b_ball" type="sphere" size="0.01" pos="0 0 0.2"/></body>
    <body name="c" pos="0.25 0 0"><joint type="hinge"/><geom name="c_box" type="box" size="0.05 0.05 0.05"/></body>
    <body name="d" pos="0 1 0"><joint type="hinge"/>
      <geom name="d_shown" type="box" size="0.05 0.05 0.05" contype="0" conaffinity="0"/></body>
  </worldbody>
  <contact>
    <exclude body1="a" body2="b"/>
    <exclude body1="b" body2="c"/>
    <exclude body1="c" body2="d"/>
  </contact>
</mujoco>"""


class Check(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def written(self, text: str, name: str = "robot.xml") -> Path:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_what_collides_and_each_exclude_s_two_bodies_at_rest_are_data_and_two_lines(self) -> None:
        found = cad.mujoco.check(self.written(EXCLUDED))
        self.assertTrue(found.ok, [f"{f.code}: {f.message}" for f in found.findings])
        self.assertIn("MuJoCo model 'row', 4 bodies, 4 joints, 0 actuators, 4 collision geoms, 0 meshes, 0 keys",
                      found.summary)
        collisions = found.measurements["collisions"]
        self.assertEqual((collisions["geoms"], collisions["by_kind"], collisions["silent"]),
                         (4, {"box": 3, "sphere": 1}, ["d"]))
        self.assertEqual([(row["body"], [(geom["name"], geom["kind"]) for geom in row["geoms"]])
                          for row in collisions["bodies"]],
                         [("a", [("a_box", "box")]), ("b", [("b_box", "box"), ("b_ball", "sphere")]),
                          ("c", [("c_box", "box")])])
        self.assertEqual(collisions["bodies"][0]["geoms"][0]["size"], [0.05, 0.05, 0.05])
        # An exclude is between two bodies whole: how their collision geoms stand at rest says whether it is one
        # of touching neighbours, of two apart (meant, or left from a collision since removed), or of nothing.
        excludes = {tuple(row["bodies"]): (row["state"], row["distance_mm"]) for row in found.measurements["excludes"]}
        self.assertEqual(excludes[("a", "b")][0], "touching")
        self.assertEqual(excludes[("b", "c")], ("apart", 50.0))
        self.assertEqual(excludes[("c", "d")], ("no_collision", None))
        said = {finding.code: finding.message for finding in found.findings if finding.severity == "info"}
        self.assertEqual(said["collisions"], "4 collision geoms (box 3, sphere 1) on 3 bodies: a 1 (box 1); "
                                             "b 2 (box 1, sphere 1); c 1 (box 1). Moving bodies that collide as "
                                             "nothing: d")
        self.assertEqual(said["excludes"], "3 contact excludes, each between two bodies whole: a and b touching at "
                                           "rest; b and c 50 mm apart at rest; c and d, where one has no collision "
                                           "geom")

    def test_the_runner_of_one_operation_runs_an_integration_s_as_it_runs_a_type_s(self) -> None:
        # What the cad command runs in cad[mujoco]'s environment where its own holds no mujoco.
        import json
        import subprocess
        import sys

        def asked(operation: str) -> dict:
            request = json.dumps({"type": "mujoco", "operation": operation, "args": [str(self.written(EXCLUDED))],
                                  "kwargs": {"strict": True}})
            done = subprocess.run([sys.executable, "-m", "cad._internal.operation"], input=request, text=True,
                                  capture_output=True, check=True, env={**os.environ, "PYTHONPATH": SOURCES})
            return json.loads(done.stdout.strip().splitlines()[-1])

        answer = asked("check")["result"]
        self.assertEqual((answer["ok"], answer["measurements"]["collisions"]["geoms"]), (True, 4))
        self.assertEqual(asked("validate"),
                         {"error": "no operation 'validate' of a document type or an integration 'mujoco'"})

    def test_what_is_no_mujoco_model_and_one_mujoco_refuses_fail_by_name(self) -> None:
        wrong = cad.mujoco.check(self.written("<robot/>", "robot.urdf"))
        self.assertEqual((wrong.ok, [f.code for f in wrong.findings], wrong.findings[0].message),
                         (False, ["invalid_target"], "target must be a .xml or .mjcf file"))
        missing = cad.mujoco.check(self.folder / "nowhere.xml")
        self.assertEqual((missing.ok, missing.findings[0].message), (False, "file not found"))
        refused = cad.mujoco.check(self.written(
            '<mujoco><worldbody><body><geom type="mesh" mesh="nope"/></body></worldbody></mujoco>'))
        self.assertFalse(refused.ok)
        self.assertEqual(["compile_failed"], [f.code for f in refused.findings])
        self.assertIn("MuJoCo refused the model: Error: mesh 'nope' not found", refused.findings[0].message)
        self.assertEqual({}, refused.measurements, "nothing is measured of a model that did not compile")


if __name__ == "__main__":
    unittest.main()
