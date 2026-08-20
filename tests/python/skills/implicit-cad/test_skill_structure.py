from __future__ import annotations

import unittest

from tests.python.support.paths import repo_path

EXPECTED_SCRIPT_ENTRIES = ("gen", "export.mjs", "snapshot", "lib/implicit-cad.mjs")


class ImplicitCadSkillStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "implicit-cad")

    def test_skill_md_exists_with_required_frontmatter(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        head = source.split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: implicit-cad", head[1])
        self.assertRegex(head[1], r"description:\s*\S", "description frontmatter must be non-empty")

    def test_agents_openai_yaml_exists(self) -> None:
        agent_file = self.skill_root / "agents" / "openai.yaml"
        self.assertTrue(agent_file.is_file(), "agents/openai.yaml must exist")
        self.assertGreater(agent_file.read_text(encoding="utf-8").strip(), "")

    def test_expected_script_entry_points_exist(self) -> None:
        for rel in EXPECTED_SCRIPT_ENTRIES:
            with self.subTest(entry=rel):
                self.assertTrue(
                    (self.skill_root / "scripts" / rel).exists(),
                    f"scripts/{rel} must exist",
                )

    def test_gen_package_is_runnable_as_a_module(self) -> None:
        gen_dir = self.skill_root / "scripts" / "gen"
        self.assertTrue((gen_dir / "__main__.py").is_file())
        self.assertTrue((gen_dir / "cli.py").is_file())
