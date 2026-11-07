"""The controls a CAD view counts are one vocabulary in three languages.

The page names what a person used (`@cad/ui`'s `usage/controls.js`), cadgen notes only names it
knows (`cad_server/analytics.py`: `CONTROLS`), and the receiver refuses any other (`apps/api/src/events.mjs`:
`CONTROLS`). A name one of them lacks is a count lost without a word: the page's never noted, or a whole
batch refused. The kinds a file is counted as are its document type's (the library's registry,
`cad.registry`, kernel-free), as the schemas spell them. Read from source, so this needs nothing installed.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "packages/ui/src/usage/controls.js"
CADGEN = ROOT / "packages/cad-server/src/cad_server/analytics.py"
RECEIVER = ROOT / "apps/api/src/events.mjs"


def names(path: Path, start: str, end: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    body = text[text.index(start) + len(start):]
    body = body[:body.index(end)]
    body = re.sub(r"(?m)(?://|#).*$", "", body)  # comments name words that are no control
    return re.findall(r"""['"]([a-z0-9][a-z0-9_]*)['"]""", body)


class TheControlsAreOneVocabulary(unittest.TestCase):
    def test_the_page_cadgen_and_the_receiver_name_the_same_controls(self) -> None:
        page = names(PAGE, "export const CONTROLS = Object.freeze(", "]));")
        cadgen = names(CADGEN, "CONTROLS = frozenset({", "})")
        receiver = names(RECEIVER, "export const CONTROLS = new Set([", "]);")
        self.assertGreater(len(page), 100)
        self.assertEqual(len(page), len(set(page)), "each name once")
        self.assertEqual(page, receiver, "the receiver's list, in the page's order")
        self.assertEqual(sorted(page), sorted(cadgen))
        # A name says what was used, never a value: snake_case words of the page's choosing.
        for name in page:
            self.assertRegex(name, r"^[a-z]+(?:_[a-z]+)*$")


class TheKindsAreOneVocabulary(unittest.TestCase):
    def test_current_sender_kinds_match_its_receiver_schema(self) -> None:
        # File suffixes are local lookup keys; only their formats and the closed model word cross the wire:
        # each document type's wire spelling (the registry's), which the sender's FILE_KINDS is made of.
        import sys

        sys.path.insert(0, str(ROOT / "packages/cad/src"))
        from cad.registry import DOCUMENT_TYPES

        tree = ast.parse(CADGEN.read_text(encoding="utf-8"))
        assignments = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                       for target in node.targets if isinstance(target, ast.Name)}
        self.assertEqual("_file_kinds()", ast.unparse(assignments["FILE_KINDS"]))
        formats = {entry.wire for entry in DOCUMENT_TYPES.values()}
        extra = names(CADGEN, "KINDS = frozenset({", "})")
        receiver = set(names(RECEIVER, "const KINDS = new Set([", "]);")
                       + names(RECEIVER, "const KINDS_6 = new Set([", "]);")
                       + names(RECEIVER, "const KINDS_8 = new Set([", "]);")
                       + names(RECEIVER, "const KINDS_9 = new Set([", "]);"))
        self.assertEqual(formats | set(extra), receiver)
        self.assertIn("model", extra)
        self.assertIn("xbf", formats)
        self.assertIn("scad", formats)
        schema = ast.literal_eval(assignments["SCHEMA"])
        self.assertRegex(RECEIVER.read_text(encoding="utf-8"), rf"\[{schema}, \{{[^\n]*kinds: KINDS_9")


if __name__ == "__main__":
    unittest.main()
