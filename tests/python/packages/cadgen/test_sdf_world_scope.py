"""World-level models and frames share SDFormat's frame-reference namespace."""
from pathlib import Path
import tempfile
import unittest

from cadgen import sdf


class SdfWorldScopeTests(unittest.TestCase):
    def validate(self, content):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "world.sdf"
            target.write_text(f'<sdf version="1.12"><world name="test">{content}</world></sdf>',
                              encoding="utf-8")
            return sdf.validate(target, gz_check="never")

    def test_frame_attaches_to_sibling_model(self):
        result = self.validate('<model name="arm"><link name="base"/></model>'
                               '<frame name="tool" attached_to="arm"/>')
        self.assertTrue(result.ok, result)

    def test_frame_pose_relative_to_sibling_model(self):
        result = self.validate('<frame name="tool"><pose relative_to="arm">1 0 0 0 0 0</pose></frame>'
                               '<model name="arm"><link name="base"/></model>')
        self.assertTrue(result.ok, result)

    def test_sibling_model_pose_relative_to_another_model(self):
        result = self.validate('<model name="arm"><link name="base"/></model>'
                               '<model name="table"><pose relative_to="arm">1 0 0 0 0 0</pose>'
                               '<link name="surface"/></model>')
        self.assertTrue(result.ok, result)

    def test_world_light_pose_can_reference_model(self):
        result = self.validate('<light name="lamp" type="point"><pose relative_to="arm">1 0 0 0 0 0</pose></light>'
                               '<model name="arm"><link name="base"/></model>')
        self.assertTrue(result.ok, result)

    def test_model_frame_name_collision_is_rejected(self):
        result = self.validate('<model name="arm"><link name="base"/></model>'
                               '<frame name="arm" attached_to="world"/>')
        self.assertFalse(result.ok)
        self.assertIn("cross_type_name_collision", {issue.code for issue in result.issues})

    def test_missing_model_reference_still_fails(self):
        result = self.validate('<model name="arm"><link name="base"/></model>'
                               '<frame name="tool" attached_to="missing"/>')
        self.assertFalse(result.ok)
        self.assertIn("unresolved_reference", {issue.code for issue in result.issues})

    def test_world_frame_reference_remains_valid(self):
        self.assertTrue(self.validate('<frame name="table" attached_to="world"/>'
                                     '<frame name="tool" attached_to="table"/>').ok)


if __name__ == "__main__":
    unittest.main()
