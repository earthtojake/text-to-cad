"""The documentation site's pages name files the repository has.

The site (`apps/docs`, texttocad.dev/docs) sets the repository's guides as they are and its own pages
(`apps/docs/content`), and its build resolves every link: a page of its map with no file, a `/docs`
path that is no page, an anchor that is no heading. That build runs when the site or `docs/` changes.
What it reads from the rest of the tree is checked here, on every change: a page's link to a file
of the repository (`repo:<path>`), so a renamed skill or reference fails where it is renamed rather
than at the next build of the site; and the Skills pages, one a skill, named after it.
"""

from __future__ import annotations

import re
import unittest

from tests.python.support.paths import REPO_ROOT

DOCS_APP = REPO_ROOT / "apps" / "docs"
CONTENT = DOCS_APP / "content"
MAP = DOCS_APP / "src" / "lib" / "docs" / "nav.ts"

REPO_LINK = re.compile(r"\]\(repo:([^)#\s]+)(?:#[^)\s]*)?\)")


class TheDocsSiteNamesFilesThatExist(unittest.TestCase):
    def test_a_page_links_repository_files_that_exist(self) -> None:
        missing = []
        for page in sorted(CONTENT.rglob("*.md")):
            for path in REPO_LINK.findall(page.read_text(encoding="utf-8")):
                if not (REPO_ROOT / path).exists():
                    missing.append(f"{page.relative_to(REPO_ROOT).as_posix()} -> {path}")
        self.assertEqual(missing, [])

    def test_the_map_names_repository_files_that_exist(self) -> None:
        # A guide of the repository's that is a page of the site: `repo("<page>", "<file>")`.
        files = re.findall(r'\brepo\("[^"]*", "([^"]+)"', MAP.read_text(encoding="utf-8"))
        self.assertTrue(files, "no repository files found in the documentation's map")
        self.assertEqual([path for path in files if not (REPO_ROOT / path).is_file()], [])

    def test_every_skill_has_its_page(self) -> None:
        # The Skills section is a page a skill, `content/skills/<skill>.md` at /docs/<skill>.
        skills = sorted(path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md"))
        self.assertTrue(skills, "no skills found")
        written = sorted(path.stem for path in (CONTENT / "skills").glob("*.md"))
        self.assertEqual(written, skills, "a skill with no page, or a page with no skill")

    def test_every_feature_links_a_skills_page_that_exists(self) -> None:
        # The homepage's tiles link the documentation's Skills (`page` in the site's copy), at a
        # section of a page where the feature is one (manufacturing checks are the cad skill's).
        copy = (DOCS_APP / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        pages = re.findall(r'page: "/docs/([^"#]+)(?:#[^"]*)?"', copy)
        self.assertEqual(len(pages), len(re.findall(r'^    id: "', copy, re.M)), "a feature with no page")
        self.assertEqual([page for page in pages if not (CONTENT / "skills" / f"{page}.md").is_file()], [])

if __name__ == "__main__":
    unittest.main()
