"""The robot validators walk a description as deep as a file can write without recursing: the
SDF frame graph, nested SDF models, the URDF joint tree and SRDF subgroups each take a stack of
their own, so a 5,000-deep chain is checked (and a cycle at its end found) instead of crashing
the validating process with a RecursionError."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from cadgen.findings import FindingsReport
from cadgen.sdf_validation import validate_sdf_xml
from cadgen.srdf_source import SrdfPlanningGroup
from cadgen.srdf_validation import _check_subgroup_cycles
from cadgen.urdf_source import validate_urdf_file

DEPTH = 5000
LINK = '<link name="base"><inertial><mass>1</mass><inertia><ixx>1</ixx><iyy>1</iyy><izz>1</izz></inertia></inertial></link>'


def codes(report: FindingsReport) -> list[str]:
    return [finding.code for finding in (*report.errors, *report.warnings, *report.infos)]


class DeepRobotDescriptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertLess(sys.getrecursionlimit(), DEPTH, "the chains must be deeper than a recursion could go")

    def test_a_deep_sdf_frame_chain_is_walked_and_a_cycle_at_its_end_is_found(self) -> None:
        frames = "".join(f'<frame name="f{at}" attached_to="f{at + 1}"/>' for at in range(DEPTH))
        last = f'<frame name="f{DEPTH}" attached_to="base"/>'
        document = f'<?xml version="1.0"?><sdf version="1.9"><model name="m">{LINK}{frames}{last}</model></sdf>'
        self.assertNotIn("frame_cycle", codes(validate_sdf_xml(document, source_path=Path("deep.sdf"))))
        looped = document.replace(last, f'<frame name="f{DEPTH}" attached_to="f0"/>')
        self.assertEqual(codes(validate_sdf_xml(looped, source_path=Path("loop.sdf"))).count("frame_cycle"), 1)

    def test_deeply_nested_sdf_models_are_each_checked(self) -> None:
        inner = f'<model name="m{DEPTH}">{LINK}</model>'
        document = inner
        for at in range(DEPTH - 1, -1, -1):
            document = f'<model name="m{at}">{document}</model>'
        report = validate_sdf_xml(f'<?xml version="1.0"?><sdf version="1.9">{document}</sdf>', source_path=Path("nested.sdf"))
        self.assertNotIn("empty_model", codes(report))
        broken = document.replace(f'<model name="m{DEPTH}">{LINK}</model>', f'<model name="m{DEPTH}"/>')
        report = validate_sdf_xml(f'<?xml version="1.0"?><sdf version="1.9">{broken}</sdf>', source_path=Path("nested.sdf"))
        self.assertEqual(codes(report).count("empty_model"), 1, "the deepest model is reached")

    def test_a_deep_urdf_joint_chain_is_one_rooted_tree(self) -> None:
        links = "".join(f'<link name="l{at}"/>' for at in range(DEPTH + 1))
        joints = "".join(f'<joint name="j{at}" type="fixed"><parent link="l{at}"/><child link="l{at + 1}"/></joint>'
                         for at in range(DEPTH))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deep.urdf"
            path.write_text(f'<robot name="deep">{links}{joints}</robot>', encoding="utf-8")
            _source, report = validate_urdf_file(path)
        self.assertFalse({"not_a_tree", "joint_graph_cycle", "disconnected_links"} & set(codes(report)), codes(report))

    def test_a_deep_srdf_subgroup_chain_is_walked_and_a_cycle_at_its_end_is_found(self) -> None:
        def groups(back_to_start: bool) -> dict[str, SrdfPlanningGroup]:
            found = {}
            for at in range(DEPTH + 1):
                below = (f"g{at + 1}",) if at < DEPTH else (("g0",) if back_to_start else ())
                found[f"g{at}"] = SrdfPlanningGroup(f"g{at}", (), ("l",) if not below else (), (), below)
            return found

        report = FindingsReport()
        _check_subgroup_cycles(groups(False), report)
        self.assertEqual(codes(report), [])
        _check_subgroup_cycles(groups(True), report)
        self.assertEqual(codes(report), ["subgroup_cycle"])
        self.assertTrue(report.errors[0].message.startswith("planning subgroups form a cycle: g0 -> g1 -> "))


if __name__ == "__main__":
    unittest.main()
