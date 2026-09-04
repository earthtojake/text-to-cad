"""The Python and JS selector grammars are two implementations of one language.

`cadgen.cad_ref_syntax` and `cadgen-js/lib/cadRefs.js` parse the same refs, and before this fixture
existed nothing checked that they agreed -- the grammar was copy-pasted into four places. Both
suites read `packages/cadgen-js/src/lib/cadRefs.parity.json`, so a form added to one language and
forgotten in the other fails here rather than in a user's pasted ref.
"""

from __future__ import annotations

import json
import unittest

from tests.python.support.paths import repo_path

from cadgen.label_refs import build_label_aliases
from cadgen.cad_ref_syntax import (
    build_cad_token,
    ensure_ref_file_matches,
    normalize_selector_list,
    parse_cad_tokens,
    parse_selector,
    path_has_suffix,
)


FIXTURE_PATH = repo_path("packages", "cadgen-js", "src", "lib", "cadRefs.parity.json")


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ParityFixtureIsUsableTest(unittest.TestCase):
    def test_the_fixture_exists_and_has_all_three_case_kinds(self) -> None:
        data = _fixture()
        for key in ("selectorCases", "inheritanceCases", "aliasCases"):
            self.assertTrue(data.get(key), f"{key} must be present and non-empty")


class SelectorParityTest(unittest.TestCase):
    def test_every_selector_case_parses_as_the_fixture_says(self) -> None:
        for case in _fixture()["selectorCases"]:
            with self.subTest(selector=case["selector"], why=case.get("why", "")):
                parsed = parse_selector(case["selector"])
                self.assertIsNotNone(parsed)
                self.assertEqual(case["selectorType"], parsed.selector_type)
                self.assertEqual(case["occurrenceId"], parsed.occurrence_id)
                self.assertEqual(case["ordinal"], parsed.ordinal)
                self.assertEqual(case["canonical"], parsed.canonical)
                self.assertEqual(case.get("label", ""), parsed.label)


class AliasParityTest(unittest.TestCase):
    """The fixture carries aliasCases for both languages, but only the JS suite ran them.

    Nothing here read them, so `buildLabelAliasMap` and `build_label_aliases` could drift
    with the fixture still green -- which is how the `occurrenceId` row spelling ended up
    accepted by one side and dropped by the other.
    """

    def test_every_alias_case_builds_as_the_fixture_says(self) -> None:
        for case in _fixture()["aliasCases"]:
            with self.subTest(why=case.get("why", "")):
                built = build_label_aliases(case["rows"])
                self.assertEqual(case["aliases"], built["aliases"])
                self.assertEqual(case.get("ambiguous", {}), built["ambiguous"])


class InheritanceParityTest(unittest.TestCase):
    def test_comma_lists_inherit_as_the_fixture_says(self) -> None:
        for case in _fixture()["inheritanceCases"]:
            with self.subTest(input=case["input"], why=case.get("why", "")):
                self.assertEqual(case["expected"], normalize_selector_list(case["input"]))


class BackwardsCompatibilityTest(unittest.TestCase):
    """Adding label forms must not move a single existing ref.

    This is the guarantee that matters most: every numeric selector anyone has already pasted
    into an issue, a sidecar, or a script keeps parsing to exactly what it parsed to before.
    """

    NUMERIC_FORMS = (
        "o1",
        "o1.2",
        "o1.2.3.4.5.6",
        "o12.f19",
        "o1.2.s3",
        "o1.2.e3",
        "o1.2.v3",
        "f45",
        "s2",
        "e9",
        "v4",
        "#o2.f1",
        "m1",
        "m17",
    )

    def test_numeric_selectors_never_take_the_label_branch(self) -> None:
        for selector in self.NUMERIC_FORMS:
            with self.subTest(selector=selector):
                parsed = parse_selector(selector)
                self.assertIsNotNone(parsed)
                self.assertEqual(
                    "",
                    parsed.label,
                    f"{selector} must not be read as a label",
                )

    def test_mates_stay_opaque(self) -> None:
        # "m1" matches the label pattern; it must still be opaque so mate handling in the
        # consumers keeps working.
        for selector in ("m1", "m2", "M3"):
            with self.subTest(selector=selector):
                self.assertEqual("opaque", parse_selector(selector).selector_type)

    def test_entity_and_occurrence_forms_win_over_the_label_form(self) -> None:
        self.assertEqual("face", parse_selector("f45").selector_type)
        self.assertEqual("occurrence", parse_selector("o1.2").selector_type)
        self.assertEqual("shape", parse_selector("s7").selector_type)


if __name__ == "__main__":
    unittest.main()


class TokenParityTest(unittest.TestCase):
    """The token layer: `<file>#<selectors>`.

    The prefix half of the token was always in the grammar's shape -- ParsedToken has carried a
    `cad_path` field filled with "" since it was written -- and this is where it gets populated.
    It sits LEFT of the '#', which is why it cannot collide with the selector grammar: labels,
    their ':' qualifiers, and entity dots all live on the right.
    """

    def test_every_token_case_parses_as_the_fixture_says(self) -> None:
        for case in _fixture()["tokenCases"]:
            with self.subTest(text=case["text"], why=case.get("why", "")):
                tokens = parse_cad_tokens(case["text"])
                if case["selectors"] is None:
                    self.assertEqual([], tokens, "text without '#' is not a token")
                    continue
                self.assertEqual(1, len(tokens), f"expected one token from {case['text']!r}")
                self.assertEqual(case["cadPath"], tokens[0].cad_path)
                self.assertEqual(case["selectors"], list(tokens[0].selectors))

    def test_a_token_round_trips_through_build_cad_token(self) -> None:
        # build_cad_token took a cad_path and discarded it (`_ = cad_path`). It no longer does,
        # so what the viewer copies is what the grammar parses.
        self.assertEqual("plate.stl#o1.2", build_cad_token("plate.stl", "o1.2"))
        self.assertEqual("#o1.2", build_cad_token("", "o1.2"))
        self.assertEqual("plate.stl#", build_cad_token("plate.stl", ""))
        self.assertEqual("#", build_cad_token("", ""))


class TokenBackwardsCompatibilityTest(unittest.TestCase):
    def test_bare_tokens_are_untouched(self) -> None:
        for text in ("#o1", "#o1.2.f3", "#f45", "#m1", "#", "#o1.2,f3"):
            with self.subTest(text=text):
                tokens = parse_cad_tokens(text)
                self.assertEqual(1, len(tokens))
                self.assertEqual("", tokens[0].cad_path, f"{text} must carry no file prefix")


class RefFileGuardTest(unittest.TestCase):
    """A ref's file prefix must match the file the command is looking at, or be refused.

    CLIs never resolve a prefix to a path -- the agent does that and passes the file separately.
    What a CLI must do is refuse a prefix naming some OTHER file, because the alternative is
    inspecting the file it was pointed at and reporting a confident answer about geometry the
    user did not ask about.
    """

    TARGET = "models/assemblies/STEP/motorcycle_shock_absorber/motorcycle_shock_absorber"

    def test_matching_prefixes_pass_in_every_spelling(self) -> None:
        for prefix in (
            "motorcycle_shock_absorber",
            "motorcycle_shock_absorber.py",
            "motorcycle_shock_absorber.step",
            "STEP/motorcycle_shock_absorber",
            "models/assemblies/STEP/motorcycle_shock_absorber/motorcycle_shock_absorber",
        ):
            with self.subTest(prefix=prefix):
                ensure_ref_file_matches(prefix, self.TARGET)

    def test_an_empty_prefix_is_always_fine(self) -> None:
        ensure_ref_file_matches("", self.TARGET)

    def test_a_foreign_file_is_refused_and_the_message_names_both(self) -> None:
        with self.assertRaises(ValueError) as raised:
            ensure_ref_file_matches("other_part", self.TARGET)
        message = str(raised.exception)
        self.assertIn("other_part", message)
        self.assertIn("motorcycle_shock_absorber", message)

    def test_matching_is_segment_aligned_not_substring(self) -> None:
        # `absorber.py` is a substring of the target's filename but not a path segment;
        # accepting it would resolve a ref to a file the user never named.
        with self.assertRaises(ValueError):
            ensure_ref_file_matches("absorber", self.TARGET)
        with self.assertRaises(ValueError):
            ensure_ref_file_matches("other/motorcycle_shock_absorber", self.TARGET)

    def test_path_has_suffix_is_segment_aligned(self) -> None:
        self.assertTrue(path_has_suffix("a/b/plate.stl", "plate.stl"))
        self.assertTrue(path_has_suffix("a/b/plate.stl", "b/plate.stl"))
        self.assertFalse(path_has_suffix("a/b/plate.stl", "late.stl"))
        self.assertFalse(path_has_suffix("plate.stl", "a/plate.stl"))
        self.assertFalse(path_has_suffix("a/b/plate.stl", ""))
