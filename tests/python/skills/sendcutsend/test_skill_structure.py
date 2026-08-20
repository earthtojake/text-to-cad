from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import repo_path


class SendCutSendSkillStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "sendcutsend")

    def test_skill_md_exists_with_required_frontmatter(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        head = source.split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: sendcutsend", head[1])
        self.assertRegex(head[1], r"description:\s*\S", "description frontmatter must be non-empty")

    def test_agents_openai_yaml_exists(self) -> None:
        agent_file = self.skill_root / "agents" / "openai.yaml"
        self.assertTrue(agent_file.is_file(), "agents/openai.yaml must exist")
        self.assertGreater(agent_file.read_text(encoding="utf-8").strip(), "")

    def test_references_exist(self) -> None:
        for rel in ("official-sources.md", "report-template.md"):
            ref = self.skill_root / "references" / rel
            with self.subTest(reference=rel):
                self.assertTrue(ref.is_file(), f"references/{rel} must exist")
                self.assertGreater(ref.read_text(encoding="utf-8").strip(), "")
