"""The hand-written skill catalogs must list exactly the shipped skills.

`skills/` is the product, and two documents re-list it by hand: the QwenPaw
plugin README's "What it provides" table and the docs landing page's skill
groups. A new skill reaches every installer for free through `skills/`, so it
silently disappears from those lists and the copy understates what installs.
Neither list has any other coupling to the tree, which is why they are checked
here rather than left to review. The plugin's fabrication opt-in tuple is bound
to the same tree: a gated name that no longer exists stops applying in silence.

`skills/` itself is the source of truth; the structural rule that every skill
directory carries a `SKILL.md` lives in `test_plugin_manifests.py`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = REPO_ROOT / "skills"
PLUGIN_README_PATH = REPO_ROOT / ".qwenpaw-plugin" / "README.md"
DOCS_PAGE_PATH = REPO_ROOT / "apps" / "docs" / "src" / "app" / "page.tsx"
PLUGIN_ENTRY_PATH = REPO_ROOT / ".qwenpaw-plugin" / "plugin.py"

# A catalog row's first cell: "| `skill-name` | ...".
README_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|")
# A docs-site group entry: { name: "...", path: "skills/skill-name", ... }.
DOCS_SKILL_PATH = re.compile(r'path:\s*"skills/([^"]+)"')


def shipped_skills() -> list[str]:
    return sorted(
        path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()
    )


def load_plugin_entry():
    spec = importlib.util.spec_from_file_location(
        "_test_skill_catalog_plugin_entry", PLUGIN_ENTRY_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_test_skill_catalog_plugin_entry", None)
    return module


class SkillCatalogSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.skills = shipped_skills()
        self.assertTrue(self.skills, "skills/ found no skill directories")

    def test_qwenpaw_readme_table_lists_every_skill(self) -> None:
        listed = [
            match.group(1)
            for line in PLUGIN_README_PATH.read_text(
                encoding="utf-8"
            ).splitlines()
            if (match := README_ROW.match(line))
        ]
        self.assertEqual(
            self.skills,
            sorted(set(listed)),
            f"{PLUGIN_README_PATH.relative_to(REPO_ROOT)} 'What it provides' "
            "table diverged from skills/",
        )

    def test_docs_page_skill_groups_list_every_skill(self) -> None:
        text = DOCS_PAGE_PATH.read_text(encoding="utf-8")
        listed = DOCS_SKILL_PATH.findall(text)
        self.assertEqual(
            self.skills,
            sorted(set(listed)),
            f"{DOCS_PAGE_PATH.relative_to(REPO_ROOT)} skillGroups diverged "
            "from skills/",
        )

    def test_fabrication_gate_names_shipped_skills(self) -> None:
        gated = set(load_plugin_entry().FABRICATION_SKILLS)
        self.assertTrue(gated, "FABRICATION_SKILLS is empty")
        self.assertLessEqual(
            gated,
            set(self.skills),
            ".qwenpaw-plugin/plugin.py gates skills that no longer exist; the "
            "fabrication opt-in would silently stop applying",
        )


if __name__ == "__main__":
    unittest.main()
