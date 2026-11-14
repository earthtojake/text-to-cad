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
# `cad viewer`, pinned to the skill's release as every command a skill runs is.
VIEWER = re.compile(r"`?cad \+\S+ viewer")


class ShowTheModelTest(unittest.TestCase):
    def test_the_cad_app_first_then_the_app_s_own_browser_pane_then_the_link(self) -> None:
        # The skills are every host's: Codex and Cursor have the CAD app, Claude does not. The section shows with
        # `cad_show` where the agent's tools include it; else the agent OPENS the page in the app's own browser pane
        # where it has a tool for that (the Claude desktop app); only with neither does it give the link alone. An
        # agent told only to "give the link, to open in the browser pane" gave the link and opened nothing.
        text = section(SKILLS[0])
        self.assertIn("1. `cad_show` among your tools", text)
        self.assertIn("2. A tool that opens a page in the app's own browser pane", text)
        self.assertIn("open the page there yourself", text)
        self.assertIn("3. Neither: give the person the link", text)
        self.assertIn("The page follows every run", text)
        self.assertRegex(text, r"`cad \+\S+ viewer")
        # Of the app's tools, only `cad_show` is named, and outside the section only beside `cad viewer` or as a
        # thing that already prints or refuses (never told to call alone).
        for path in sorted((REPO / "skills").rglob("*.md")):
            for paragraph in path.read_text(encoding="utf-8").split("\n\n"):
                if not APP_TOOLS.search(paragraph) or "Show the model" in paragraph:
                    continue
                with self.subTest(path=str(path.relative_to(REPO)), paragraph=paragraph[:80]):
                    self.assertNotRegex(paragraph, r"`cad_(?:view|screenshot)`")
                    self.assertTrue(VIEWER.search(paragraph) or "`cad_show` among your tools" in paragraph
                                    or re.search(r"`cad_show`\s+(?:print|alike|do not open)", paragraph), paragraph)

    def test_every_skill_that_shows_models_says_how_in_the_same_words(self) -> None:
        first = section(SKILLS[0])
        for name in SKILLS[1:]:
            self.assertEqual(section(name), first, f"skills/{name}: Show the model differs from skills/{SKILLS[0]}")


if __name__ == "__main__":
    unittest.main()
