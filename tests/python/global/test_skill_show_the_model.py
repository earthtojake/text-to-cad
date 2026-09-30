"""The skills that show models say how in one section, word for word the same.

Each skill installs on its own, so each carries the section; this keeps the copies from drifting.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = ("cad", "dxf", "urdf", "sdf", "srdf")
END = "If it fails to launch, say so.\n"


def section(name: str) -> str:
    text = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    heading = re.search(r"^#{2,3} Show the model\n", text, re.M)
    if heading is None:
        raise AssertionError(f"skills/{name}/SKILL.md has no Show the model section")
    return text[heading.end(): text.index(END, heading.end()) + len(END)]


class ShowTheModelTest(unittest.TestCase):
    def test_every_skill_that_shows_models_says_how_in_the_same_words(self) -> None:
        first = section(SKILLS[0])
        for name in SKILLS[1:]:
            self.assertEqual(section(name), first, f"skills/{name}: Show the model differs from skills/{SKILLS[0]}")


if __name__ == "__main__":
    unittest.main()
