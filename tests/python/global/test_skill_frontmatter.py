"""Every skill's front matter is YAML an installer can read.

The Skills CLI and the agent apps parse SKILL.md's front matter as YAML. A plain (unquoted) value
holding ": " is a mapping inside a mapping, so the whole file is refused: `npx skills` stopped
updating step-parts over one colon in its description. Python ships no YAML parser, so this checks
the two plain-scalar rules a one-line value breaks, which is how every skill writes its keys.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def front_matter(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path.relative_to(REPO)} does not open with front matter")
    return lines[1:lines.index("---", 1)]


class SkillFrontMatterTest(unittest.TestCase):
    def test_no_plain_value_holds_a_colon_space_or_a_comment(self) -> None:
        skills = sorted((REPO / "skills").glob("*/SKILL.md"))
        self.assertTrue(skills)
        for path in skills:
            for line in front_matter(path):
                key, separator, value = line.partition(": ")
                if not separator or line[:1].isspace():
                    continue
                with self.subTest(skill=path.parent.name, key=key):
                    if value[:1] in {'"', "'", ">", "|"}:
                        continue  # quoted or a block scalar: the colon is text
                    self.assertNotIn(": ", value, "quote it or write it as a `>-` block")
                    self.assertNotIn(" #", value, "quote it or write it as a `>-` block")


if __name__ == "__main__":
    unittest.main()
