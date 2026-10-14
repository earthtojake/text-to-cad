"""The cam skill says what cadgen builds: every operation in its router table, each on a reference page that names
its keys, every post in posts.md, and a router description that stays a router."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from cadgen._internal.cam import operations, posts

SKILL = Path(__file__).resolve().parents[5] / "skills" / "cam"
GENERAL = {"job-file.md", "checks.md", "posts.md", "machining-practice.md"}


def _table(text: str, heading: str) -> list[list[str]]:
    section = text.split(heading, 1)[1]
    section = re.split(r"\n#{2,3} ", section, maxsplit=1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|") and "---" not in line]
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]


def _router_rows() -> dict[str, tuple[str, str, str]]:
    """op -> (plain word, status, reference page), the page carried down from the row that links it."""
    rows: dict[str, tuple[str, str, str]] = {}
    page = ""
    for cells in _table((SKILL / "SKILL.md").read_text(encoding="utf-8"), "## Choose the operation"):
        linked = re.search(r"\(references/([a-z0-9-]+\.md)", cells[4])
        page = linked.group(1) if linked else (cells[4] if cells[4].endswith(".md") else page)
        found = re.fullmatch(r"`([a-z_0-9]+)`", cells[1])
        if found:
            rows[found.group(1)] = (cells[2], cells[3], page)
    return rows


class RouterTable(unittest.TestCase):
    def test_every_built_operation_has_a_row_with_its_word_and_status(self):
        rows = _router_rows()
        for name in operations.built():
            entry = operations.REGISTRY[name]
            with self.subTest(op=name):
                self.assertIn(name, rows, f"{name} is built but has no row in SKILL.md's Choose the operation")
                word, status, _ = rows[name]
                self.assertEqual(word, entry.plain)
                self.assertTrue(status.startswith("**Runs today**"), status)
                self.assertEqual("(lite)" in status, entry.status == "lite", status)
        self.assertEqual(sorted(set(rows) - set(operations.REGISTRY)), [])
        for name in set(operations.REGISTRY) - set(operations.built()):
            self.assertNotIn("Runs today", rows.get(name, ("", "", ""))[1], name)

    def test_each_operation_page_is_linked_once_and_names_every_key_its_operations_take(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        section = re.split(r"\n#{2,3} ", text.split("## Choose the operation", 1)[1], maxsplit=1)[0]
        linked = re.findall(r"\]\(references/([a-z0-9-]+\.md)", section)
        pages = sorted(p.name for p in (SKILL / "references").glob("*.md") if p.name not in GENERAL)
        self.assertEqual(sorted(linked), pages, "each operation page is linked exactly once from the table")
        for page in GENERAL:
            self.assertIn(f"references/{page}", text)
        for name, (_, _, page) in _router_rows().items():
            if name not in operations.built():
                continue
            body = (SKILL / "references" / page).read_text(encoding="utf-8")
            for key in operations.get_operation(name).keys:
                with self.subTest(op=name, key=key):
                    self.assertIn(f"`{key}`", body, f"{page} does not document {name}'s key {key!r}")

    def test_the_description_is_a_router(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        description = re.search(r"^description: (.*)$", text, re.M).group(1)
        self.assertLess(len(description), 1024)
        self.assertNotIn("—", description)
        self.assertNotIn("`", description)


class Findings(unittest.TestCase):
    def test_checks_md_names_every_finding_check_and_type(self):
        from cadgen._internal.cam.checks.base import FINDING_TYPES

        body = (SKILL / "references" / "checks.md").read_text(encoding="utf-8")
        for check, kinds in FINDING_TYPES.items():
            for kind in (check, *kinds):
                with self.subTest(check=check, type=kind):
                    self.assertIn(f"`{kind}`", body, f"checks.md does not name the finding {check}/{kind}")


class Posts(unittest.TestCase):
    def test_posts_md_lists_every_post_with_its_extension(self):
        rows = {}
        for cells in _table((SKILL / "references" / "posts.md").read_text(encoding="utf-8"), "## The posts"):
            found = re.fullmatch(r"`([a-z_0-9]+)`", cells[0])
            if found:
                rows[found.group(1)] = " ".join(cells[1:])
        self.assertEqual(sorted(rows), sorted(posts.POST_NAMES))
        for name, entry in posts.REGISTRY.items():
            with self.subTest(post=name):
                self.assertIn(f"`{entry.extension}`", rows[name])


if __name__ == "__main__":
    unittest.main()
