"""Link-defined groups include each link's parent planning joint, as MoveIt does."""
from pathlib import Path
import tempfile
import unittest

from cadgen import srdf

URDF = '''<robot name="arm">
<link name="base"/><link name="upper"/><link name="tip"/><link name="fixed_tip"/>
<joint name="shoulder" type="revolute"><parent link="base"/><child link="upper"/>
<axis xyz="0 0 1"/><limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
<joint name="slide" type="prismatic"><parent link="upper"/><child link="tip"/>
<axis xyz="1 0 0"/><limit lower="0" upper="0.2" effort="1" velocity="1"/></joint>
<joint name="mount" type="fixed"><parent link="tip"/><child link="fixed_tip"/></joint>
</robot>'''


class SrdfLinkGroupTests(unittest.TestCase):
    def validate(self, group, state, *, extra=""):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "arm.urdf").write_text(URDF, encoding="utf-8")
            target = root / "arm.srdf"
            target.write_text(f'<robot name="arm">{group}{extra}'
                              f'<group_state name="home" group="arm">{state}</group_state></robot>',
                              encoding="utf-8")
            return srdf.validate(target)

    def test_link_group_accepts_its_parent_joint(self):
        result = self.validate('<group name="arm"><link name="upper"/></group>',
                               '<joint name="shoulder" value="0.5"/>')
        self.assertTrue(result.ok, result)

    def test_link_group_still_checks_joint_limits(self):
        result = self.validate('<group name="arm"><link name="upper"/></group>',
                               '<joint name="shoulder" value="2"/>')
        self.assertIn("group_state_above_limit", {item.code for item in result.issues})
        self.assertNotIn("group_state_joint_not_in_group", {item.code for item in result.issues})

    def test_subgroup_inherits_link_parent_joints(self):
        result = self.validate('<group name="arm"><group name="part"/></group>',
                               '<joint name="slide" value="0.1"/>',
                               extra='<group name="part"><link name="tip"/></group>')
        self.assertTrue(result.ok, result)

    def test_link_group_reports_omitted_joint(self):
        result = self.validate('<group name="arm"><link name="upper"/><link name="tip"/></group>',
                               '<joint name="shoulder" value="0"/>')
        self.assertIn("incomplete_group_state", {item.code for item in result.issues})

    def test_link_does_not_include_all_ancestor_joints(self):
        result = self.validate('<group name="arm"><link name="tip"/></group>',
                               '<joint name="shoulder" value="0"/>')
        self.assertIn("group_state_joint_not_in_group", {item.code for item in result.issues})

    def test_fixed_link_parent_is_not_a_planning_variable(self):
        result = self.validate('<group name="arm"><link name="upper"/><link name="fixed_tip"/></group>',
                               '<joint name="shoulder" value="0"/>')
        self.assertTrue(result.ok, result)
        self.assertNotIn("incomplete_group_state", {item.code for item in result.issues})


if __name__ == "__main__":
    unittest.main()
