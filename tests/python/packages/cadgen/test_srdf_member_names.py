"""Malformed members must not silently become a smaller planning group."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cadgen.srdf_source import parse_srdf_text


class SrdfMemberNameTests(unittest.TestCase):
    def test_all_named_member_kinds_require_a_nonempty_name(self):
        for kind in ("joint", "link", "group"):
            for attr in ("", ' name=""', ' name="   "'):
                with self.subTest(kind=kind, attr=attr):
                    source, report = parse_srdf_text(
                        f'<robot name="arm"><group name="arm">'
                        f'<joint name="shoulder"/><{kind}{attr}/></group></robot>',
                        source_path=Path("arm.srdf"))
                    self.assertIsNone(source)
                    self.assertIn("missing_group_member_name", {finding.code for finding in report.errors})
                    self.assertTrue(any(finding.path.endswith(f"/{kind}") for finding in report.errors))

    def test_collects_multiple_bad_members_in_one_pass(self):
        source, report = parse_srdf_text(
            '<robot name="arm"><group name="arm"><joint/><link/><group/></group></robot>',
            source_path=Path("arm.srdf"))
        self.assertIsNone(source)
        self.assertEqual(3, sum(item.code == "missing_group_member_name" for item in report.errors))

    def test_valid_members_and_namespaced_extensions_are_preserved(self):
        source, report = parse_srdf_text(
            '<robot name="arm" xmlns:x="urn:test"><group name="arm">'
            '<joint name="shoulder"/><link name="upper"/><group name="gripper"/>'
            '<x:joint/></group></robot>', source_path=Path("arm.srdf"))
        self.assertFalse(report.errors)
        self.assertEqual(source.planning_groups[0].joint_names, ("shoulder",))
        self.assertEqual(source.planning_groups[0].link_names, ("upper",))
        self.assertEqual(source.planning_groups[0].subgroups, ("gripper",))

    def test_cli_bad_member_fails_before_pairing_with_structured_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "arm.urdf").write_text('<robot name="arm"><link name="base"/></robot>', encoding="utf-8")
            path = root / "arm.srdf"
            path.write_text('<robot name="arm"><group name="arm"><link name="base"/><link/></group></robot>',
                            encoding="utf-8")
            process = subprocess.run([sys.executable, "-S", "-m", "cadgen.cli", "srdf", "validate",
                                      str(path), "--json"], capture_output=True, text=True, check=False)
            self.assertEqual(1, process.returncode, process.stderr)
            result = json.loads(process.stdout)
            self.assertIn("missing_group_member_name", {issue["code"] for issue in result["issues"]})


if __name__ == "__main__":
    unittest.main()
