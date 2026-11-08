"""``cad.mujoco._compile``'s model-health checks: one tiny MJCF per check that trips it, a clean model that
trips none but the notes, and ``--strict`` through ``cad.mjcf.validate``, each in a fresh temporary folder."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

import cad.mjcf  # noqa: E402
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
        return cad.mjcf.validate(path, strict=True, compile="required")

    def test_strict_fails_intersecting_geoms_and_passes_the_clean_model(self) -> None:
        failed = self.validate(INTERSECTING)
        self.assertFalse(failed.ok)
        self.assertIn("contacts_at_rest", {finding.code for finding in failed.findings})
        passed = self.validate(CLEAN)
        self.assertTrue(passed.ok, [f"{f.code}: {f.message}" for f in passed.findings])


if __name__ == "__main__":
    unittest.main()
