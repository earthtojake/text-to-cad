"""The fea skill's pages against the code they document: the study's keys and check kinds, the solver's setup, the
links between the pages. Stdlib only."""

from __future__ import annotations

import re
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cad/src")

SKILL = repo_path("skills", "fea")


def _pages() -> list:
    return [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]


class SkillDocs(unittest.TestCase):
    def test_the_study_keys_and_the_check_kinds_are_the_parsers(self):
        from cad._internal.fea.study import CHECK_KEYS, STUDY_KEYS

        text = (SKILL / "references" / "study-file.md").read_text(encoding="utf-8")
        keys = text.split("## Keys", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(sorted(set(re.findall(r"^\| `([a-z_]+)`", keys, re.M)) | {"connections", "contact_tolerance_mm"}),
                         sorted(STUDY_KEYS))
        checks = text.split("## `checks`", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(re.findall(r"^\| `([a-z_]+)` \|", checks, re.M)[1:], list(CHECK_KEYS))  # past the header

    def test_the_setup_names_the_mesher_and_the_solver_the_cad_command_installs(self):
        from cad.calculix._program import CCX, CCX_ENV, install_hint

        text = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        setup = text.split("## Setup", 1)[1].split("## Workflow", 1)[0]
        self.assertIn(f"`{CCX_ENV}`", setup)
        self.assertIn(f"{CCX.minimum[0]}.{CCX.minimum[1]} or newer", setup)
        self.assertIn("cad[calculix]", install_hint())
        # Both are integrations the cad command installs on first need; nothing is the person's to install.
        self.assertIn("`netgen` integration (`cad[netgen]`", setup)
        self.assertIn("`calculix` integration (`cad[calculix]`", setup)
        self.assertNotIn("conda install", setup)

    def test_every_command_is_a_types_operation(self):
        from cad.registry import DOCUMENT_TYPES

        studied = {entry.id for entry in DOCUMENT_TYPES.values() if "solve" in entry.operation_names}
        for path in _pages():
            text = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                for document_type in re.findall(r"`cad (\w+) solve\b", text):
                    self.assertIn(document_type, studied)
                self.assertNotRegex(text, r"`cad (?:step|xbf|model) fea\b", "the study is solve")
                self.assertNotRegex(text, r"`cad fea\b|\.fea\b", "a solve writes a folder of standard files")

    def test_the_folder_the_skill_describes_is_the_one_a_solve_writes(self):
        from cad._internal.fea import run

        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for name in (run.RESULT_JSON, run.RESULT_GLB, run.RESULT_VTU, run.STRESS_PNG, run.DISPLACEMENT_PNG, run.DECK):
            self.assertIn(f"`{name}`", text)

    def test_the_nodal_peak_is_the_one_documented_as_usually_higher(self):
        for path in (SKILL / "SKILL.md", SKILL / "references" / "linear-static.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            with self.subTest(page=path.name):
                self.assertIn("usually the higher of the two", text)

    def test_the_description_is_short_and_every_reference_page_is_linked(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"^description: (.*)$", text, re.M).group(1)
        self.assertLess(len(description), 1024)
        self.assertNotIn("—", description)
        for page in (SKILL / "references").glob("*.md"):
            self.assertIn(f"references/{page.name}", text)

    def test_every_relative_link_lands_on_a_page_and_its_heading(self):
        def anchor(heading: str) -> str:
            slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
            return slug.replace(" ", "-")

        anchors = {}
        for path in _pages():
            headings = re.findall(r"^#{1,6} (.+)$", path.read_text(encoding="utf-8"), re.M)
            anchors[path.resolve()] = {anchor(heading) for heading in headings}
        for path in _pages():
            for target in re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target):
                    continue
                page, _, fragment = target.partition("#")
                resolved = (path.parent / page).resolve() if page else path.resolve()
                with self.subTest(page=path.name, link=target):
                    self.assertIn(resolved, anchors, "links to a page the skill does not ship")
                    if fragment:
                        self.assertIn(fragment, anchors[resolved])


if __name__ == "__main__":
    unittest.main()
