"""Adversarial edge-case coverage for the SRDF validator.

Each case is a deliberately broken (or deliberately suspicious) URDF+SRDF pair
pinned to the finding code the validator must emit. This file is the coverage
contract for the validator: new checks land with a case here.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("skills/srdf/scripts")

from srdf import cli

URDF = """\
<robot name="edge">
  <link name="base"/>
  <link name="upper"/>
  <link name="lower"/>
  <link name="tool"/>
  <link name="island"/>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="upper"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/>
  </joint>
  <joint name="elbow" type="prismatic">
    <parent link="upper"/><child link="lower"/>
    <limit lower="0" upper="0.2" effort="1" velocity="1"/>
  </joint>
  <joint name="wrist_fix" type="fixed">
    <parent link="lower"/><child link="tool"/>
  </joint>
  <joint name="island_mount" type="fixed">
    <parent link="base"/><child link="island"/>
  </joint>
</robot>
"""

SRDF_HEADER = '<robot name="edge">\n'
ARM_GROUP = '  <group name="arm"><chain base_link="base" tip_link="lower"/></group>\n'


def _srdf(body: str, *, header: str = SRDF_HEADER, groups: str = ARM_GROUP) -> str:
    return f"{header}{groups}{body}</robot>\n"


# (case name, srdf text, expected code, expected severity)
CASES = [
    # --- structural parsing ---
    ("invalid_xml", "<robot name='edge'><group></robot>", "invalid_xml", "error"),
    ("invalid_root", "<semantic/>", "invalid_root", "error"),
    ("missing_robot_name", _srdf("", header="<robot>\n"), "missing_robot_name", "error"),
    ("missing_group_name", _srdf('  <group><joint name="shoulder"/></group>\n'), "missing_group_name", "error"),
    ("duplicate_group", _srdf('  <group name="arm"><joint name="shoulder"/></group>\n'), "duplicate_name", "error"),
    ("unknown_robot_child", _srdf("  <group_states/>\n"), "unknown_element", "warning"),
    ("unknown_group_child", _srdf('  <group name="g2"><joint name="shoulder"/><chian base_link="base" tip_link="lower"/></group>\n'), "unknown_element", "warning"),
    ("missing_virtual_joint_name", _srdf('  <virtual_joint type="fixed" parent_frame="world" child_link="base"/>\n'), "missing_virtual_joint_name", "error"),
    ("invalid_virtual_joint_type", _srdf('  <virtual_joint name="vj" type="rotary" parent_frame="world" child_link="base"/>\n'), "invalid_virtual_joint_type", "error"),
    ("missing_parent_frame", _srdf('  <virtual_joint name="vj" type="fixed" child_link="base"/>\n'), "missing_parent_frame", "error"),
    ("virtual_joint_missing_child_link_attr", _srdf('  <virtual_joint name="vj" type="fixed" parent_frame="world"/>\n'), "missing_child_link", "error"),
    ("missing_passive_joint_name", _srdf("  <passive_joint/>\n"), "missing_passive_joint_name", "error"),
    ("missing_group_state_identity", _srdf('  <group_state name="pose"><joint name="shoulder" value="0"/></group_state>\n'), "missing_group_state_identity", "error"),
    ("nonnumeric_group_state_value", _srdf('  <group_state name="pose" group="arm"><joint name="shoulder" value="x"/></group_state>\n'), "invalid_group_state_value", "error"),
    ("infinite_group_state_value", _srdf('  <group_state name="pose" group="arm"><joint name="shoulder" value="inf"/></group_state>\n'), "nonfinite_group_state_value", "error"),
    ("missing_pair_links", _srdf('  <disable_collisions link1="base" reason="Adjacent"/>\n'), "missing_collision_pair_links", "error"),
    ("self_pair", _srdf('  <disable_collisions link1="base" link2="base" reason="Adjacent"/>\n'), "self_collision_pair", "error"),
    ("missing_pair_reason", _srdf('  <disable_collisions link1="base" link2="upper"/>\n'), "missing_collision_pair_reason", "error"),
    ("duplicate_pair", _srdf(
        '  <disable_collisions link1="base" link2="upper" reason="Adjacent"/>\n'
        '  <disable_collisions link1="upper" link2="base" reason="Adjacent"/>\n'
    ), "duplicate_name", "error"),
    # --- urdf pairing (same folder, matching robot name) ---
    ("no_paired_urdf", _srdf("", header='<robot name="other">\n'), "no_paired_urdf", "error"),
    (
        "deprecated_urdf_link",
        _srdf("", header='<robot name="edge" xmlns:tcad="https://text-to-cad.dev/srdf">\n  <tcad:urdf path="robot.urdf"/>\n'),
        "deprecated_urdf_link",
        "warning",
    ),
    # --- cross-validation against the URDF ---
    ("no_planning_groups", _srdf("", groups=""), "no_planning_groups", "error"),
    ("empty_group", _srdf('  <group name="empty"/>\n'), "empty_group", "error"),
    ("unknown_group_joint", _srdf('  <group name="g2"><joint name="wrist_roll"/></group>\n'), "missing_name_reference", "error"),
    ("unknown_group_link", _srdf('  <group name="g2"><link name="phantom"/></group>\n'), "missing_name_reference", "error"),
    ("unknown_subgroup", _srdf('  <group name="g2"><group name="ghost_group"/></group>\n'), "missing_name_reference", "error"),
    ("missing_chain_base", _srdf('  <group name="g2"><chain base_link="ghost" tip_link="lower"/></group>\n'), "missing_chain_link", "error"),
    ("missing_chain_tip", _srdf('  <group name="g2"><chain base_link="base" tip_link="ghost"/></group>\n'), "missing_chain_link", "error"),
    ("reversed_chain", _srdf('  <group name="g2"><chain base_link="lower" tip_link="base"/></group>\n'), "chain_not_a_path", "error"),
    ("sibling_chain", _srdf('  <group name="g2"><chain base_link="island" tip_link="lower"/></group>\n'), "chain_not_a_path", "error"),
    (
        "subgroup_cycle",
        _srdf(
            '  <group name="g_a"><group name="g_b"/></group>\n'
            '  <group name="g_b"><group name="g_a"/></group>\n'
        ),
        "subgroup_cycle",
        "error",
    ),
    ("virtual_joint_missing_child", _srdf('  <virtual_joint name="vj" type="fixed" parent_frame="world" child_link="phantom"/>\n'), "missing_virtual_joint_child", "error"),
    ("virtual_joint_name_collision", _srdf('  <virtual_joint name="shoulder" type="fixed" parent_frame="world" child_link="base"/>\n'), "virtual_joint_name_collision", "warning"),
    ("missing_passive_joint", _srdf('  <passive_joint name="caster"/>\n'), "missing_passive_joint", "error"),
    (
        "group_state_sets_passive_joint",
        _srdf(
            '  <passive_joint name="elbow"/>\n'
            '  <group_state name="pose" group="arm"><joint name="shoulder" value="0"/><joint name="elbow" value="0"/></group_state>\n'
        ),
        "group_state_sets_passive_joint",
        "error",
    ),
    ("missing_ee_parent_link", _srdf('  <end_effector name="ee" parent_link="phantom" group="arm"/>\n'), "missing_end_effector_parent_link", "error"),
    ("missing_ee_group", _srdf('  <end_effector name="ee" parent_link="lower" group="hand"/>\n'), "missing_end_effector_group", "error"),
    ("missing_ee_parent_group", _srdf('  <end_effector name="ee" parent_link="lower" group="arm" parent_group="torso"/>\n'), "missing_end_effector_parent_group", "error"),
    (
        "ee_group_overlaps_parent_group",
        _srdf(
            '  <group name="hand"><link name="lower"/></group>\n'
            '  <end_effector name="ee" parent_link="lower" group="hand" parent_group="arm"/>\n'
        ),
        "end_effector_group_overlap",
        "error",
    ),
    (
        "ee_parent_link_outside_parent_group",
        _srdf(
            '  <group name="hand"><link name="tool"/></group>\n'
            '  <end_effector name="ee" parent_link="island" group="hand" parent_group="arm"/>\n'
        ),
        "end_effector_parent_link_outside_parent_group",
        "error",
    ),
    (
        "ee_parent_link_not_adjacent",
        _srdf(
            '  <group name="hand"><link name="tool"/></group>\n'
            '  <end_effector name="ee" parent_link="island" group="hand"/>\n'
        ),
        "end_effector_parent_link_not_adjacent",
        "error",
    ),
    ("missing_group_state_group", _srdf('  <group_state name="pose" group="torso"><joint name="shoulder" value="0"/></group_state>\n'), "missing_group_state_group", "error"),
    ("missing_group_state_joint", _srdf('  <group_state name="pose" group="arm"><joint name="phantom" value="0"/></group_state>\n'), "missing_group_state_joint", "error"),
    (
        "group_state_joint_not_in_group",
        _srdf(
            '  <group name="solo"><joint name="shoulder"/></group>\n'
            '  <group_state name="pose" group="solo"><joint name="elbow" value="0"/></group_state>\n'
        ),
        "group_state_joint_not_in_group",
        "error",
    ),
    (
        "group_state_sets_fixed_joint",
        _srdf(
            '  <group name="fixed_g"><joint name="wrist_fix"/><joint name="shoulder"/></group>\n'
            '  <group_state name="pose" group="fixed_g"><joint name="wrist_fix" value="0"/></group_state>\n'
        ),
        "group_state_sets_fixed_joint",
        "error",
    ),
    ("group_state_below_limit", _srdf('  <group_state name="pose" group="arm"><joint name="shoulder" value="-2"/><joint name="elbow" value="0"/></group_state>\n'), "group_state_below_limit", "error"),
    ("group_state_above_limit", _srdf('  <group_state name="pose" group="arm"><joint name="elbow" value="0.5"/><joint name="shoulder" value="0"/></group_state>\n'), "group_state_above_limit", "error"),
    ("incomplete_group_state", _srdf('  <group_state name="pose" group="arm"><joint name="shoulder" value="0"/></group_state>\n'), "incomplete_group_state", "warning"),
    ("adjacent_reason_mismatch", _srdf('  <disable_collisions link1="base" link2="lower" reason="Adjacent"/>\n'), "adjacent_reason_mismatch", "warning"),
    ("unknown_pair_link", _srdf('  <disable_collisions link1="base" link2="phantom" reason="Never"/>\n'), "missing_name_reference", "error"),
]


class SrdfFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-srdf-findings-")
        self.temp_root = Path(self._tempdir.name)
        (self.temp_root / "robot.urdf").write_text(URDF, encoding="utf-8")

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _report(self, srdf_text: str) -> dict[str, object]:
        srdf_path = self.temp_root / "robot.srdf"
        srdf_path.write_text(srdf_text, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = cli._validate_target(srdf_path, strict=False, output_format="json")
        return report

    def _codes(self, srdf_text: str) -> tuple[set[str], set[str]]:
        findings = self._report(srdf_text)["findings"]
        return (
            {f["code"] for f in findings if f["severity"] == "error"},
            {f["code"] for f in findings if f["severity"] == "warning"},
        )

    def test_cases_emit_expected_codes(self) -> None:
        for name, srdf_text, expected_code, severity in CASES:
            with self.subTest(case=name):
                error_codes, warning_codes = self._codes(srdf_text)
                if severity == "error":
                    self.assertIn(expected_code, error_codes, f"{name}: errors were {error_codes}")
                else:
                    self.assertIn(expected_code, warning_codes, f"{name}: warnings were {warning_codes}")
                    self.assertFalse(error_codes, f"{name}: unexpected errors {error_codes}")

    def test_clean_pair_has_no_findings(self) -> None:
        srdf_text = _srdf(
            '  <virtual_joint name="world_mount" type="fixed" parent_frame="world" child_link="base"/>\n'
            '  <group name="hand"><link name="tool"/></group>\n'
            '  <group_state name="home" group="arm"><joint name="shoulder" value="0"/><joint name="elbow" value="0.1"/></group_state>\n'
            '  <end_effector name="ee" parent_link="lower" group="hand" parent_group="arm"/>\n'
            '  <disable_collisions link1="base" link2="upper" reason="Adjacent"/>\n'
            '  <disable_collisions link1="base" link2="island" reason="Adjacent"/>\n'
        )
        report = self._report(srdf_text)
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual([], report["findings"])

    def test_legacy_explorer_namespace_is_clean(self) -> None:
        header = '<robot name="edge" xmlns:explorer="https://text-to-cad.dev/explorer">\n  <explorer:urdf path="robot.urdf"/>\n'
        report = self._report(_srdf("", header=header))
        self.assertTrue(report["ok"], report["findings"])

    def test_many_manual_pairs_warns(self) -> None:
        # 25+ pairs with free-text reasons classify as "manual" provenance.
        links = "".join(f'  <link name="extra{i}"/>\n  ' for i in range(30))
        joints = "".join(
            f'<joint name="je{i}" type="fixed"><parent link="base"/><child link="extra{i}"/></joint>\n  '
            for i in range(30)
        )
        urdf_text = URDF.replace("</robot>", f"{links}{joints}</robot>")
        (self.temp_root / "robot.urdf").write_text(urdf_text, encoding="utf-8")
        pairs = "".join(
            f'  <disable_collisions link1="upper" link2="extra{i}" reason="reviewed by hand"/>\n'
            for i in range(25)
        )
        _, warning_codes = self._codes(_srdf(pairs))
        self.assertIn("many_manual_disabled_pairs", warning_codes)

    def test_broken_paired_urdf_reports_invalid_paired_urdf(self) -> None:
        # The root tag parses (so pairing resolves by name) but the body is broken XML.
        (self.temp_root / "robot.urdf").write_text("<robot name='edge'><link></robot>", encoding="utf-8")
        error_codes, _ = self._codes(_srdf(""))
        self.assertIn("invalid_paired_urdf", error_codes)

    def test_ambiguous_paired_urdf_fails(self) -> None:
        (self.temp_root / "robot_b.urdf").write_text(URDF, encoding="utf-8")
        error_codes, _ = self._codes(_srdf(""))
        self.assertIn("ambiguous_paired_urdf", error_codes)

    def test_multi_root_paired_urdf_warns_not_a_tree(self) -> None:
        urdf_text = URDF.replace("</robot>", '<link name="orphan"/></robot>')
        (self.temp_root / "robot.urdf").write_text(urdf_text, encoding="utf-8")
        _, warning_codes = self._codes(_srdf(""))
        self.assertIn("paired_urdf_not_a_tree", warning_codes)

    def test_multiple_errors_collected_in_one_pass(self) -> None:
        srdf_text = _srdf(
            '  <group name="g2"><joint name="phantom_joint"/></group>\n'
            '  <group_state name="pose" group="torso"><joint name="shoulder" value="0"/></group_state>\n'
            '  <disable_collisions link1="base" link2="phantom" reason="Never"/>\n'
        )
        error_codes, _ = self._codes(srdf_text)
        self.assertLessEqual(
            {"missing_name_reference", "missing_group_state_group"},
            error_codes,
        )

    def test_strict_promotes_warnings(self) -> None:
        srdf_path = self.temp_root / "robot.srdf"
        srdf_path.write_text(
            _srdf('  <group_state name="pose" group="arm"><joint name="shoulder" value="0"/></group_state>\n'),
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            default_report = cli._validate_target(srdf_path, strict=False, output_format="json")
            strict_report = cli._validate_target(srdf_path, strict=True, output_format="json")
        self.assertTrue(default_report["ok"])
        self.assertFalse(strict_report["ok"])


if __name__ == "__main__":
    unittest.main()
