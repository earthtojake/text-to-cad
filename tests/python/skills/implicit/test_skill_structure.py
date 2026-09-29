from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import repo_path


class ImplicitSkillStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "implicit")

    def test_skill_md_exists_with_required_frontmatter(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        head = source.split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: implicit", head[1])
        self.assertRegex(head[1], r"description:\s*\S", "description frontmatter must be non-empty")
        self.assertIn("signed distance", head[1], "the description says what kind of SDF this is (not SDFormat)")

    def test_agents_openai_yaml_exists(self) -> None:
        agent_file = self.skill_root / "agents" / "openai.yaml"
        self.assertTrue(agent_file.is_file(), "agents/openai.yaml must exist")
        self.assertIn("$implicit", agent_file.read_text(encoding="utf-8"))

    def test_references_exist(self) -> None:
        for rel in ("modeling.md", "questions.md", "meshing.md"):
            ref = self.skill_root / "references" / rel
            with self.subTest(reference=rel):
                self.assertTrue(ref.is_file(), f"references/{rel} must exist")
                self.assertGreater(len(ref.read_text(encoding="utf-8").strip()), 0)

    def test_requirements_pin_cadgen(self) -> None:
        text = (self.skill_root / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(text, r"^cadgen(\[[a-z,]+\])?==\d", "requirements.txt pins cadgen")


if __name__ == "__main__":
    unittest.main()
