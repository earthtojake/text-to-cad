"""Every relative link in the repository's own documents lands on a file and, with a fragment, on a heading.

AGENTS.md sends a reader to one document for each kind of change, and each document sends them on to the next:
a link that lands nowhere strands them at the moment they are following instructions. Documents are split, moved
and renamed (the release runbook out of CONTRIBUTING.md, the engine's README into a page per mechanism), and
nothing else notices a link that pointed at the old place.

The skills' links are held by ``test_skill_shape.py``, which also keeps each inside its skill, and the
documentation site's pages (``apps/docs/content``) by the site's own build, which resolves their routes
(``/docs/cad#...``) and their ``repo:`` paths. This holds every other tracked Markdown file. Standard library
alone.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCED = re.compile(r"^ *```.*?^ *```", re.S | re.M)
INLINE = re.compile(r"`[^`\n]*`")
#: Not documents of ours: a task's or a test's sample text, whose links are part of the sample.
SAMPLES = ("__fixtures__/", "/fixtures/", "scripts/bench/skill_ab/tasks/")
#: Held elsewhere: the skills, and the site's pages, whose links are the site's routes.
ELSEWHERE = ("skills/", "apps/docs/content/")


def _documents() -> list[Path]:
    """The tracked Markdown files but those held elsewhere and the samples'."""
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.md"], capture_output=True, text=True, check=True)
    return [REPO / name for name in listed.stdout.splitlines()
            if not name.startswith(ELSEWHERE) and not any(sample in name for sample in SAMPLES)]


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


class DocumentLinks(unittest.TestCase):
    def test_every_relative_link_lands_on_a_file_and_its_heading(self) -> None:
        anchors: dict[Path, set[str]] = {}
        documents = _documents()
        self.assertGreater(len(documents), 60, "the sweep read almost no document")
        checked = 0
        for document in documents:
            text = INLINE.sub("", FENCED.sub("", document.read_text(encoding="utf-8")))
            for target in LINK.findall(text):
                if re.match(r"[a-z][a-z0-9+.-]*:", target):
                    continue  # another site's
                checked += 1
                name, _, fragment = target.partition("#")
                landed = (document.parent / name).resolve() if name else document.resolve()
                with self.subTest(document=str(document.relative_to(REPO)), link=target):
                    self.assertTrue(landed.exists(), "links to a file or folder that is not there")
                    if fragment and landed.suffix == ".md" and landed.is_file():
                        if landed not in anchors:
                            anchors[landed] = _anchors(landed)
                        self.assertIn(fragment, anchors[landed], "links to a heading that file does not have")
        self.assertGreater(checked, 300, "the sweep matched almost no link")


if __name__ == "__main__":
    unittest.main()
