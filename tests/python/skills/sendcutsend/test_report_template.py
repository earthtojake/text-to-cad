from __future__ import annotations

import unittest

from tests.python.support.paths import repo_path

REQUIRED_SECTIONS = (
    "Context",
    "Sources Checked",
    "Geometry Facts",
    "Findings",
    "Verdict",
)


class SendCutSendReportTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = (
            repo_path("skills", "sendcutsend", "references", "report-template.md")
            .read_text(encoding="utf-8")
            .splitlines()
        )

    def test_template_has_a_document_title(self) -> None:
        self.assertTrue(self.template[0].startswith("# "), "template must open with a title")

    def test_required_sections_appear_in_order(self) -> None:
        heading_lines = [line.strip() for line in self.template if line.strip().startswith("## ")]
        self.assertGreaterEqual(len(heading_lines), len(REQUIRED_SECTIONS))
        headings = [line[3:].strip() for line in heading_lines]
        position = 0
        for section in REQUIRED_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, headings[position:], f"section {section!r} missing or out of order")
                position = position + 1 + headings[position:].index(section)

    def test_findings_table_has_the_standard_columns(self) -> None:
        header = [line for line in self.template if line.strip().startswith("| Status | Check | Evidence |")]
        self.assertEqual(1, len(header), "findings table must carry the standard header row")
        self.assertIn("Rule source", header[0])
        self.assertIn("Recommendation", header[0])
