from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import repo_path


class StepPartsSkillStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "step-parts")

    def test_skill_md_exists_with_required_frontmatter(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        head = source.split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        self.assertIn("name: step-parts", head[1])
        self.assertRegex(head[1], r"description:\s*\S", "description frontmatter must be non-empty")

    def test_agents_openai_yaml_exists(self) -> None:
        agent_file = self.skill_root / "agents" / "openai.yaml"
        self.assertTrue(agent_file.is_file(), "agents/openai.yaml must exist")
        self.assertGreater(agent_file.read_text(encoding="utf-8").strip(), "")

    def test_reference_and_cli_script_exist(self) -> None:
        self.assertTrue((self.skill_root / "references" / "step-parts-api.md").is_file())
        script = self.skill_root / "scripts" / "download_step_part.py"
        self.assertTrue(script.is_file(), "scripts/download_step_part.py must exist")

    def test_cli_script_stays_stdlib_only(self) -> None:
        script = self.skill_root / "scripts" / "download_step_part.py"
        source = script.read_text(encoding="utf-8")
        imports = []
        for line in source.splitlines():
            line = line.strip()
            if line.startswith("import "):
                imports.append(line[len("import ") :].split(".")[0].split()[0])
            elif line.startswith("from "):
                imports.append(line[len("from ") :].split(".")[0].split()[0])
        self.assertEqual([], sorted(set(imports) - _STDLIB))
        self.assertTrue(source.lstrip().startswith("#!/usr/bin/env python3"))


_STDLIB = {
    "__future__",
    "argparse",
    "hashlib",
    "json",
    "pathlib",
    "sys",
    "tempfile",
    "typing",
    "urllib",
}
