"""Joints connect distinct endpoint frames; valid closed loops remain supported."""
from pathlib import Path
import tempfile
import unittest

from cadgen import sdf


def joint(name, parent, child):
    return f'<joint name="{name}" type="fixed"><parent>{parent}</parent><child>{child}</child></joint>'


class SdfJointEndpointTests(unittest.TestCase):
    def validate(self, body):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "arm.sdf"
            target.write_text('<sdf version="1.12"><model name="arm"><link name="base"/>'
                              f'<link name="tip"/>{body}</model></sdf>', encoding="utf-8")
            return sdf.validate(target, gz_check="never")

    def test_identical_endpoint_frames_fail(self):
        for endpoint in ("base", " arm::base ", "world"):
            with self.subTest(endpoint=endpoint):
                result = self.validate(joint("invalid", endpoint, endpoint))
                self.assertFalse(result.ok, result)
                self.assertIn("joint_parent_same_as_child", {issue.code for issue in result.issues})

    def test_distinct_links_remain_valid(self):
        self.assertTrue(self.validate(joint("mount", "base", "tip")).ok)

    def test_world_parent_remains_valid(self):
        self.assertTrue(self.validate(joint("anchor", "world", "base")).ok)

    def test_world_child_still_fails(self):
        result = self.validate(joint("invalid", "base", "world"))
        self.assertFalse(result.ok)
        self.assertIn("invalid_joint_child", {issue.code for issue in result.issues})

    def test_closed_loop_is_not_mistaken_for_a_self_joint(self):
        result = self.validate(joint("outbound", "base", "tip") + joint("return", "tip", "base"))
        self.assertTrue(result.ok, result)

    def test_missing_endpoint_keeps_its_existing_diagnostic(self):
        result = self.validate('<joint name="invalid" type="fixed"><child>base</child></joint>')
        self.assertFalse(result.ok)
        self.assertNotIn("joint_parent_same_as_child", {issue.code for issue in result.issues})


if __name__ == "__main__":
    unittest.main()
