"""The Python and JS board-reference grammars are two implementations of one language.

`cadgen.kicad.refs` and `@text-to-cad/core/lib/boardRefs.js` parse the references a person
copies from a KiCad board or schematic in the viewer and an agent resolves against the board.
Both suites read `packages/core/src/lib/boardRefs.parity.json`, as the STEP grammars share
`cadRefs.parity.json`, so a form one side learns and the other forgets fails here rather than
in a pasted reference.
"""

from __future__ import annotations

import json
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad.refs import (  # noqa: E402
    board_ref_document,
    format_board_selector,
    parse_board_selector,
    parse_board_token,
)

FIXTURE_PATH = repo_path("packages", "core", "src", "lib", "boardRefs.parity.json")


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class BoardSelectorParityTest(unittest.TestCase):
    def test_the_fixture_has_every_case_kind(self) -> None:
        data = _fixture()
        for key in ("selectorCases", "invalidSelectors", "formatCases", "tokenCases", "invalidTokens"):
            self.assertTrue(data.get(key), f"{key} must be present and non-empty")

    def test_every_selector_case_parses_as_the_fixture_says(self) -> None:
        for case in _fixture()["selectorCases"]:
            with self.subTest(selector=case["selector"], why=case.get("why", "")):
                parsed = parse_board_selector(case["selector"])
                self.assertIsNotNone(parsed)
                self.assertEqual(case["kind"], parsed.kind)
                self.assertEqual(case["canonical"], parsed.canonical)
                for field in ("ref", "pad", "net"):
                    self.assertEqual(case.get(field), getattr(parsed, field), field)
                self.assertEqual(case.get("at"), list(parsed.at) if parsed.at is not None else None)
                # The canonical form is a fixed point.
                self.assertEqual(case["canonical"], parse_board_selector(parsed.canonical).canonical)

    def test_every_invalid_selector_is_refused(self) -> None:
        for selector in _fixture()["invalidSelectors"]:
            with self.subTest(selector=selector):
                self.assertIsNone(parse_board_selector(selector))

    def test_every_format_case_formats_as_the_fixture_says(self) -> None:
        for case in _fixture()["formatCases"]:
            fields = {key: case[key] for key in ("ref", "pad", "net", "at") if key in case}
            with self.subTest(selector=case["selector"]):
                self.assertEqual(case["selector"], format_board_selector(case["kind"], **fields))
                self.assertEqual(case["kind"], parse_board_selector(case["selector"]).kind)

    def test_every_token_case_splits_as_the_fixture_says(self) -> None:
        for case in _fixture()["tokenCases"]:
            with self.subTest(token=case["token"], why=case.get("why", "")):
                token = parse_board_token(case["token"])
                self.assertIsNotNone(token)
                self.assertEqual(case["path"], token.path)
                self.assertEqual(case["selectors"], [selector.canonical for selector in token.selectors])


    def test_whitespace_outside_a_quoted_name_is_no_token(self) -> None:
        for token in _fixture()["invalidTokens"]:
            with self.subTest(token=token):
                self.assertIsNone(parse_board_token(token))


class BoardSelectorEdgesTest(unittest.TestCase):
    """What the fixture does not spell out, pinned on this side."""

    def test_points_round_as_javascripts_to_fixed(self) -> None:
        # The binary number's exact value, ties away from zero: 0.0625 is a tie, 1.0005 is not one.
        self.assertEqual("#@x0.063y-0.063", format_board_selector("point", at=(0.0625, -0.0625)))
        self.assertEqual("#@x1y0", format_board_selector("point", at=(1.0005, -0.0004)))
        with self.assertRaises(ValueError):
            format_board_selector("point", at=(float("nan"), 0))

    def test_what_the_language_cannot_say_is_refused(self) -> None:
        for kind, fields in (
            ("part", {"ref": "3U"}),
            ("pad", {"ref": "U3", "pad": ""}),
            ("pad", {"ref": "U3", "pad": "1.1"}),
            ("net", {"net": ""}),
            ("copper", {"net": "VIN"}),
            ("hole", {}),
        ):
            with self.subTest(kind=kind, fields=fields), self.assertRaises(ValueError):
                format_board_selector(kind, **fields)

    def test_a_point_keeps_what_was_written_and_its_canonical_text_rounds(self) -> None:
        parsed = parse_board_selector("#@x0.12345y-1")
        self.assertEqual(((0.12345, -1.0), "#@x0.123y-1"), (parsed.at, parsed.canonical))

    def test_whitespace_around_a_selector_makes_it_none(self) -> None:
        for text in (" #U3", "#U3 ", "# U3", "U3\t"):
            with self.subTest(text=text):
                self.assertIsNone(parse_board_selector(text))

    def test_a_token_is_one_word_whose_selectors_all_parse(self) -> None:
        self.assertEqual(("", ['#net:"a#b"']), self._split('#net:"a#b"'))
        self.assertEqual(("PCB/b.kicad_pcb", ['#net:"a#b"', "#U3"]), self._split('PCB/b.kicad_pcb#net:"a#b",U3'))
        self.assertEqual(("my board #2.kicad_pcb", ["#U3"]), self._split('"my board #2.kicad_pcb"#U3'))
        for text in (
            "U3",  # no '#': a selector, not a token
            "PCB/b.kicad_pcb#",  # a file and nothing in it
            "PCB/b.kicad_pcb#U3,",  # an empty place in the list
            "PCB/b.kicad_pcb#U3,3U",
            '#net:"open',
            '"unclosed#U3',
            '"\\q"#U3',
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_board_token(text))
        self.assertEqual("a b", parse_board_selector('#net:"a b"').net)
        # A quoted name keeps its whitespace in a token too, as the viewer copies it.
        self.assertEqual(("PCB/b.kicad_sch", ['#net:"/Power Stage/VLOC"']), self._split('PCB/b.kicad_sch#net:"/Power Stage/VLOC"'))

    def _split(self, text: str):
        token = parse_board_token(text)
        return token.path, [selector.canonical for selector in token.selectors]

    def test_the_suffix_chooses_the_language(self) -> None:
        self.assertEqual("board", board_ref_document("PCB/x.kicad_pcb"))
        self.assertEqual("schematic", board_ref_document("x.KICAD_SCH"))
        self.assertIsNone(board_ref_document("x.step"))


if __name__ == "__main__":
    unittest.main()
