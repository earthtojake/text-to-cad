"""The skills that show models say how in one section, word for word the same.

Each skill installs on its own, so each carries the section; this keeps the copies from drifting.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = ("cad", "pcb", "robot-simulation")
END = "If it fails to launch, say so.\n"


def section(name: str) -> str:
    text = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    heading = re.search(r"^#{2,3} Show the model\n", text, re.M)
    if heading is None:
        raise AssertionError(f"skills/{name}/SKILL.md has no Show the model section")
    return text[heading.end(): text.index(END, heading.end()) + len(END)]


# The CAD app's tools: not every host has them (Claude gets none), so a skill names them only on condition.
APP_TOOLS = re.compile(r"`cad_(?:show|view|screenshot)`")


class ShowTheModelTest(unittest.TestCase):
    def test_the_cad_app_is_used_only_where_the_tools_include_it_and_the_browser_otherwise(self) -> None:
        # The skills are every host's: Codex and Cursor have the CAD app, Claude does not. The section shows with
        # `cad_show` where the agent's tools include it, and otherwise gives the page's link from `cad viewer`.
        text = section(SKILLS[0])
        self.assertIn("If your\ntools include `cad_show`", text)
        self.assertIn("Otherwise", text)
        self.assertIn("`cad viewer", text)
        # Of the app's tools, only `cad_show` is named, and outside the section only beside `cad viewer` or as a
        # thing that already prints or refuses (never told to call alone).
        for path in sorted((REPO / "skills").rglob("*.md")):
            for paragraph in path.read_text(encoding="utf-8").split("\n\n"):
                if not APP_TOOLS.search(paragraph) or "Show the model" in paragraph:
                    continue
                with self.subTest(path=str(path.relative_to(REPO)), paragraph=paragraph[:80]):
                    self.assertNotRegex(paragraph, r"`cad_(?:view|screenshot)`")
                    self.assertTrue("cad viewer" in paragraph or "If your\ntools include" in paragraph
                                    or re.search(r"`cad_show`\s+(?:print|alike|do not open)", paragraph), paragraph)

    def test_every_skill_that_shows_models_says_how_in_the_same_words(self) -> None:
        first = section(SKILLS[0])
        for name in SKILLS[1:]:
            self.assertEqual(section(name), first, f"skills/{name}: Show the model differs from skills/{SKILLS[0]}")


if __name__ == "__main__":
    unittest.main()
