from __future__ import annotations

import unittest

from tests.python.support.paths import repo_path


class StepDiffSkillStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "step-diff")

    def test_skill_md_exists_with_required_frontmatter(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        head = source.split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: step-diff", head[1])
        self.assertRegex(head[1], r"description:\s*\S", "description frontmatter must be non-empty")

    def test_agents_openai_yaml_exists(self) -> None:
        agent_file = self.skill_root / "agents" / "openai.yaml"
        self.assertTrue(agent_file.is_file(), "agents/openai.yaml must exist")
        self.assertGreater(agent_file.read_text(encoding="utf-8").strip(), "")

    def test_install_reference_checks_the_download(self) -> None:
        install = (self.skill_root / "references" / "install.md").read_text(encoding="utf-8")
        self.assertIn(".sha256", install)
        self.assertIn("shasum -a 256 -c", install)


if __name__ == "__main__":
    unittest.main()
