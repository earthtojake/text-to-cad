"""cad's list of the plugin's skills is the skills this repository ships.

``cad plugin install`` copies the skills into the folder of each agent app that has no plugin command, and decides by
name which copies there are ours to replace or remove (``cad_server/plugin/source.py``: ``SKILLS``, and
``RETIRED_SKILLS`` for those an earlier release shipped). A skill under ``skills/`` that the list lacks is copied once
and then left alone as someone else's, so it is never updated again; a name the list keeps for a skill that is gone is
never cleaned up as retired. Nothing else holds the two together: the list is in cad's wheel, the skills in the plugin.
The lists are read from their source with ``ast``, nothing imported.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "packages/cad/src/cad_server/plugin/source.py"
SKILLS = REPO_ROOT / "skills"


def _lists() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in ("SKILLS", "RETIRED_SKILLS"):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found


def _shipped() -> set[str]:
    return {folder.name for folder in SKILLS.iterdir() if (folder / "SKILL.md").is_file()}


class PluginKnowsTheSkillsShippedTest(unittest.TestCase):
    def test_the_lists_and_the_skills_are_read(self) -> None:
        self.assertEqual(sorted(_lists()), ["RETIRED_SKILLS", "SKILLS"])
        self.assertTrue(_shipped(), "no skill found under skills/: this looks in the wrong place")

    def test_the_list_is_exactly_the_skills_under_skills(self) -> None:
        listed, shipped = _lists()["SKILLS"], _shipped()
        self.assertEqual(len(listed), len(set(listed)), "a skill is listed twice")
        self.assertEqual(
            set(listed), shipped,
            "`SKILLS` in packages/cad/src/cad_server/plugin/source.py is not the folders under skills/ that hold a "
            f"SKILL.md (listed only: {sorted(set(listed) - shipped)}; under skills/ only: "
            f"{sorted(shipped - set(listed))}). Update the list in the same change that adds or removes a skill: a "
            "skill it lacks is copied once and never updated, and one that is gone belongs in `RETIRED_SKILLS`.")

    def test_no_skill_shipped_is_listed_as_retired(self) -> None:
        self.assertEqual(sorted(set(_lists()["RETIRED_SKILLS"]) & _shipped()), [],
                         "a skill under skills/ is in `RETIRED_SKILLS`: its copies would be removed as old ones")


if __name__ == "__main__":
    unittest.main()
