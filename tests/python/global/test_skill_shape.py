"""Every skill keeps the shape the guide gives it (docs/contributing/writing-a-skill.md): a task table, a check
loop where it makes something, references one level deep and all linked from SKILL.md, and links that land.

It holds the structure, not the size. Whether a line earns its place is a judgement the guide's questions ask
of each change ("Before you add a line"), and no number here stands in for it.

Standard library alone.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = sorted(path for path in (REPO / "skills").iterdir() if path.is_dir())
#: The skill format's own limit on a description: a longer one is cut off or refused where it is listed.
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

    def test_every_description_fits_the_format(self) -> None:
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
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
