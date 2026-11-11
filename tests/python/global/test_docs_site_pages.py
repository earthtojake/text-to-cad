"""The documentation site's pages name files the repository has.

The site (`apps/docs`, texttocad.dev/docs) sets the repository's guides as they are and its own pages
(`apps/docs/content`), and its build resolves every link: a page of its map with no file, a `/docs`
path that is no page, an anchor that is no heading. That build runs when the site or `docs/` changes.
What it reads from the rest of the tree is checked here, on every change: a page's link to a file
of the repository (`repo:<path>`), so a renamed skill or reference fails where it is renamed rather
than at the next build of the site; and the page each document type and integration needs.
"""

from __future__ import annotations

import json
import re
import unittest

from tests.python.support.paths import REPO_ROOT

DOCS_APP = REPO_ROOT / "apps" / "docs"
CONTENT = DOCS_APP / "content"
MAP = DOCS_APP / "src" / "lib" / "docs" / "nav.ts"
REGISTRY = DOCS_APP / "src" / "lib" / "docs" / "registry.generated.json"

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

    def test_every_document_type_and_integration_has_its_page(self) -> None:
        # The map takes both lists from the registry; each entry's page opens with text written for it.
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        wanted = [f"document-types/{entry['id']}.md" for entry in registry["documentTypes"]]
        wanted += [f"integrations/{entry['name']}.md" for entry in registry["integrations"]]
        self.assertEqual([path for path in wanted if not (CONTENT / path).is_file()], [])


if __name__ == "__main__":
    unittest.main()
