"""Every skill keeps the shape the guide gives it: a SKILL.md inside its budget, a task table, a check loop
where it makes something, references one level deep and all linked, and links that land.

A SKILL.md is read whole by every agent that loads the skill, on every task, so its size is a cost every task
pays. The cad skill's had grown to 570 lines one reasonable paragraph at a time, with a section on joint stops,
which only a model with a mechanism needs, at its top level. Nothing held the guide's own limit, so this does:
the budget below is a ceiling a change may not pass without moving something to a reference first
(docs/contributing/writing-a-skill.md, "The budget"). Raising a number here is a decision, said in the pull
request that does it.

Standard library alone.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = sorted(path for path in (REPO / "skills").iterdir() if path.is_dir())
#: The ceiling of a SKILL.md: lines, and bytes (a few very long lines must not hide in the line count).
MAX_LINES = 260
MAX_BYTES = 17_500
#: The format's own limit on a description.
MAX_DESCRIPTION = 1024
#: The skills that make something a person keeps, which say how to check each change. The other two review a
#: file someone else made: their whole text is the check.
MAKES = {"cad", "engineering-drawing", "pcb", "print3d", "render", "robot-simulation"}
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCED = re.compile(r"^ *```.*?^ *```", re.S | re.M)


def _anchor(heading: str) -> str:
    """GitHub's anchor of a heading: lowercase, punctuation dropped but hyphens and underscores, spaces hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower().replace("`", "")).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6} (.+?)\s*$", FENCED.sub("", path.read_text(encoding="utf-8")), re.M):
        anchor = _anchor(heading)
        found.add(anchor if anchor not in seen else f"{anchor}-{seen[anchor]}")
        seen[anchor] = seen.get(anchor, 0) + 1
    return found


class SkillShape(unittest.TestCase):
    def test_the_skills_were_found(self) -> None:
        self.assertGreaterEqual(len(SKILLS), 8)
        self.assertLessEqual(MAKES, {skill.name for skill in SKILLS})

    def test_every_skill_md_is_inside_its_budget(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertLessEqual(len(text.splitlines()), MAX_LINES,
                                     "move what only some tasks need to a reference before adding to SKILL.md")
                self.assertLessEqual(len(text.encode("utf-8")), MAX_BYTES,
                                     "move what only some tasks need to a reference before adding to SKILL.md")
                description = re.search(r"^description: (.*)$", text, re.M)
                self.assertIsNotNone(description)
                self.assertLessEqual(len(description[1]), MAX_DESCRIPTION)

    def test_every_skill_opens_on_its_tasks_and_a_maker_says_how_to_check(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertRegex(text, r"(?m)^## Start with the task$")
                if skill.name in MAKES:
                    self.assertRegex(text, r"(?m)^## Check each change$")

    def test_references_are_one_level_deep_and_skill_md_links_every_one(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            pages = sorted(skill.rglob("*.md"))
            with self.subTest(skill=skill.name):
                self.assertEqual([page for page in pages
                                  if page.name != "SKILL.md" and page.parent != skill / "references"], [],
                                 "a skill's pages are SKILL.md and references/*.md")
                for page in (skill / "references").glob("*.md"):
                    self.assertIn(f"references/{page.name}", text,
                                  f"SKILL.md never names references/{page.name}: an agent reaches a reference "
                                  "from SKILL.md, not through another reference")

    def test_every_relative_link_lands_on_a_file_and_its_heading(self) -> None:
        anchors: dict[Path, set[str]] = {}
        checked = 0
        for skill in SKILLS:
            for page in sorted(skill.rglob("*.md")):
                for target in LINK.findall(FENCED.sub("", page.read_text(encoding="utf-8"))):
                    if re.match(r"[a-z][a-z0-9+.-]*:", target):
                        continue
                    checked += 1
                    name, _, fragment = target.partition("#")
                    landed = (page.parent / name).resolve() if name else page.resolve()
                    with self.subTest(page=str(page.relative_to(REPO)), link=target):
                        self.assertTrue(landed.is_file(), "links to a file the skill does not ship")
                        self.assertTrue(landed.is_relative_to(skill.resolve()), "a skill links only into itself")
                        if fragment and landed.suffix == ".md":
                            if landed not in anchors:
                                anchors[landed] = _anchors(landed)
                            self.assertIn(fragment, anchors[landed])
        self.assertGreater(checked, 200, "the sweep matched almost nothing")


if __name__ == "__main__":
    unittest.main()
