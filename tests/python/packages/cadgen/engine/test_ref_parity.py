"""The CAD Viewer reads and writes an .xbf's refs as this engine does, case for case.

``@text-to-cad/core``'s ``cadRefs.js`` holds a second parser of the ref grammar (the viewer's, for
the refs it copies and the ones pasted back to it) and a second speller of canonical refs (what Copy
Prompt writes). The ``refCases`` and ``spellingCases`` of its ``cadRefs.parity.json`` are asserted
there against those, and here against ``refs.parse`` and ``refs.resolve_structure`` -- the
resolution ``cadgen inspect`` runs on the structure it serves -- so the two cannot drift.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from cadgen.engine.refs import RefError, Selector, parse, resolve_structure

# The viewer's fixture (read, never imported: the engine stands alone).
PARITY = Path(__file__).resolve().parents[5] / "packages/core/src/lib/cadRefs.parity.json"


def shape(selector: Selector) -> dict[str, Any]:
    """A selector as the fixture writes it: its owner's segments, a quoted one as {quoted, index}."""
    owner = None if selector.owner is None else [
        segment.text if not segment.quoted
        else {"quoted": segment.text} if segment.index is None else {"quoted": segment.text, "index": segment.index}
        for segment in selector.owner]
    element = selector.element
    return {"owner": owner, "element": element if element is None or isinstance(element, str) else f"{element[0]} {element[1]}"}


def entry_at(tree: dict[str, Any], at: list[int]) -> dict[str, Any]:
    for index in at:
        tree = tree["children"][index]
    return tree


class ViewerGrammarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = json.loads(PARITY.read_text(encoding="utf-8"))

    def test_every_ref_case_parses_as_the_viewer_parses_it(self) -> None:
        self.assertTrue(self.cases["refCases"])
        for case in self.cases["refCases"]:
            with self.subTest(ref=case["ref"], why=case["why"]):
                if case.get("refused"):
                    with self.assertRaises(RefError):
                        parse(case["ref"])
                    continue
                file, selectors = parse(case["ref"])
                self.assertEqual(file, case["file"])
                self.assertEqual([shape(selector) for selector in selectors], case["selectors"])
                self.assertEqual([str(selector) for selector in selectors], case["printed"])

    def test_every_spelling_is_the_canonical_ref_where_resolves(self) -> None:
        self.assertTrue(self.cases["spellingCases"])
        for case in self.cases["spellingCases"]:
            structure = case["structure"]
            for row in case["occurrences"]:
                with self.subTest(ref=row["ref"], why=case["why"]):
                    (hit,) = resolve_structure(structure, row["ref"])
                    self.assertIs(hit.node.payload, entry_at(structure["tree"], row["at"]))
                    self.assertEqual((hit.kind, hit.ref), (None, row["ref"]))
            for row in case["elements"]:
                with self.subTest(ref=row["ref"], why=case["why"]):
                    (hit,) = resolve_structure(structure, row["ref"])
                    self.assertIs(hit.node.payload, entry_at(structure["tree"], row["at"]))
                    self.assertEqual((hit.kind, hit.ordinal, hit.ref), (row["kind"], row["ordinal"], row["ref"]))


if __name__ == "__main__":
    unittest.main()
