from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from srdf.source import SrdfSourceError, read_srdf_source


SAMPLE_SRDF = """\
<robot name="sample" xmlns:tcad="https://text-to-cad.dev/srdf">
  <tcad:urdf path="robot.urdf"/>
  <group name="arm">
    <joint name="shoulder"/>
    <joint name="elbow"/>
  </group>
  <group name="gripper">
    <link name="tool"/>
  </group>
  <end_effector name="tcp" parent_link="wrist" group="gripper" parent_group="arm"/>
  <group_state name="home" group="arm">
    <joint name="shoulder" value="0"/>
    <joint name="elbow" value="1.57"/>
  </group_state>
  <disable_collisions link1="base" link2="shoulder_link" reason="Adjacent"/>
</robot>
"""

LEGACY_SAMPLE_SRDF = SAMPLE_SRDF.replace(
    'xmlns:tcad="https://text-to-cad.dev/srdf"',
    'xmlns:explorer="https://text-to-cad.dev/explorer"',
).replace("tcad:urdf", "explorer:urdf")


class SrdfSourceTests(unittest.TestCase):
    def test_reads_moveit2_srdf_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text(SAMPLE_SRDF, encoding="utf-8")

            source = read_srdf_source(srdf_path)

            self.assertEqual(source.robot_name, "sample")
            self.assertEqual(source.urdf_ref, "robot.urdf")
            self.assertEqual(source.planning_groups[0].name, "arm")
            self.assertEqual(source.planning_groups[0].joint_names, ("shoulder", "elbow"))
            self.assertEqual(source.end_effectors[0].name, "tcp")
            self.assertEqual(source.group_states[0].joint_values_by_name_rad["elbow"], 1.57)
            self.assertEqual(source.disabled_collision_pairs[0].reason, "Adjacent")

    def test_reads_legacy_explorer_urdf_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text(LEGACY_SAMPLE_SRDF, encoding="utf-8")

            source = read_srdf_source(srdf_path)

            self.assertEqual(source.urdf_ref, "robot.urdf")

    def test_rejects_non_robot_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-srdf-source-") as tempdir:
            srdf_path = Path(tempdir) / "robot.srdf"
            srdf_path.write_text("<sdf/>", encoding="utf-8")

            with self.assertRaisesRegex(SrdfSourceError, "root element must be <robot>"):
                read_srdf_source(srdf_path)


if __name__ == "__main__":
    unittest.main()
