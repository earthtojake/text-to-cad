"""The cam skill says what a CAM job reads: every operation, post and finding in its tables, each operation's own keys
as the job parser takes them, and an example job that parses."""

from __future__ import annotations

import json
import re
import unittest

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cad/src")

from cad._internal.cam.checks import CHECKS  # noqa: E402
from cad._internal.cam.job import OP_COMMON_KEYS, OPERATIONS, POSTS, parse_job  # noqa: E402

SKILL = REPO_ROOT / "skills" / "cam"


def _table(text: str, heading: str) -> dict[str, list[str]]:
    """A section's table by its first column's code word: the row's cells."""
    section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    rows = {}
    for line in lines[2:]:                                  # past the header and its rule
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        named = re.fullmatch(r"`([a-z_0-9]+)`", cells[0])
        if named:
            rows[named.group(1)] = cells
    return rows


class Skill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def test_every_operation_with_exactly_its_own_keys(self):
        rows = _table(self.text, "## The operations")
        self.assertEqual(set(OPERATIONS), set(rows))
        for op, spec in OPERATIONS.items():
            with self.subTest(op=op):
                named = set(re.findall(r"`([a-z_]+_mm|[a-z_]+over|side)`", rows[op][-1]))
                self.assertEqual(set(spec["keys"]) - set(OP_COMMON_KEYS), named)

    def test_every_post_and_every_finding_a_plan_raises(self):
        self.assertEqual(set(POSTS), set(_table(self.text, "## The posts and the files")))
        raised = {kind for check, kinds in CHECKS.items() if check != "job" for kind in kinds}
        self.assertEqual(raised, set(_table(self.text, "## The checks")))

    def test_the_setup_block_is_the_shared_one_and_says_freecad_is_the_persons(self):
        from cad.registry import INTEGRATIONS

        probe = INTEGRATIONS["freecad"].probe
        shared = (REPO_ROOT / "skills" / "engineering-drawing" / "SKILL.md").read_text(encoding="utf-8")
        block = shared.split("## Setup\n\n", 1)[1].split("\n## ", 1)[0].rstrip()
        self.assertIn(block, self.text)
        setup = " ".join(self.text.split("### Install FreeCAD", 1)[1].split("\n## ", 1)[0].split())
        self.assertIn(f"`{probe.override}`", setup)
        self.assertIn(f"FreeCAD {probe.minimum} or newer", setup)
        self.assertIn("the person's to install", setup)

    def test_every_command_is_a_types_cam_operation(self):
        from cad.registry import DOCUMENT_TYPES

        planned = {entry.id for entry in DOCUMENT_TYPES.values() if "cam" in entry.operation_names}
        for path in (SKILL / "SKILL.md", SKILL / "references" / "job-file.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                self.assertNotRegex(text, r"`cad cam\b", "a job is an operation of its document's type")
                for document_type in re.findall(r"`cad (\w+) cam\b", text):
                    self.assertIn(document_type, planned)

    def test_the_example_job_parses(self):
        blocks = re.findall(r"```json\n(.*?)```", self.text, re.S)
        jobs = [block for block in blocks if '"setups"' in block]
        self.assertTrue(jobs)
        for block in jobs:
            with self.subTest(block=block[:40]):
                parse_job(json.loads(re.sub(r"^ {3}", "", block, flags=re.M)))


if __name__ == "__main__":
    unittest.main()
