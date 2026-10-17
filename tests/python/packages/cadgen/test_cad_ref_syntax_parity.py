"""The Python and JS selector grammars are two implementations of one language.

`cadgen.cad_ref_syntax` and `@text-to-cad/core/lib/cadRefs.js` parse the same selectors, and before
this fixture existed nothing checked that they agreed -- the grammar was copy-pasted into four
places. Both suites read the `selectorCases` of `packages/core/src/lib/cadRefs.parity.json`, so a
form added to one language and forgotten in the other fails here rather than in a user's pasted
ref. Its `inheritanceCases` and `tokenCases` are the JS parser's alone: Python takes one ref at a
time, its file prefix split off (`split_cad_ref`) and its selector parsed (`parse_selector`).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import repo_path

from cadgen.cad_ref_syntax import (
    parse_selector,
    path_has_suffix,
    split_cad_ref,
)
from cadgen.refs import Space, locate

OCCURRENCE = "o:" + "1" * 12


def ensure_ref_file_matches(prefix: str, document: str) -> None:
    """Resolve a ref carrying ``prefix`` against ``document``: the one resolver's file
    guard (``cadgen.refs.locate``), which raises ``ValueError`` for a foreign file."""
    locate(f"{prefix}#{OCCURRENCE}", Space({OCCURRENCE: [OCCURRENCE]}, {}, document=document))


FIXTURE_PATH = repo_path("packages", "core", "src", "lib", "cadRefs.parity.json")


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ParityFixtureIsUsableTest(unittest.TestCase):
    def test_the_fixture_exists_and_has_selector_cases(self) -> None:
        self.assertTrue(_fixture().get("selectorCases"), "selectorCases must be present and non-empty")


class SelectorParityTest(unittest.TestCase):
    def test_every_selector_case_parses_as_the_fixture_says(self) -> None:
        for case in _fixture()["selectorCases"]:
            with self.subTest(selector=case["selector"], why=case.get("why", "")):
                parsed = parse_selector(case["selector"])
                self.assertIsNotNone(parsed)
                self.assertEqual(case["selectorType"], parsed.selector_type)
                self.assertEqual(case["occurrenceId"], parsed.occurrence_id)
                self.assertEqual(case["element"], parsed.element)
                self.assertEqual(case["canonical"], parsed.canonical)
                self.assertEqual(case.get("label", ""), parsed.label)


O1, O2 = "o:4b1f9e2a7c03", "o:0a9e8d7c6b5f"
F, E, V = "f:9d2e8c1b5a70", "e:12ab34cd56ef", "v:fedcba987654"
# Names by lineage: the feature that made the element, its number there, and a split piece's.
NAMED = ("f:dial.extrude1.3", "e:dial.extrude1.3.2", "v:lid.2")


class TokenPrecedenceTest(unittest.TestCase):
    """Token and name forms are tried before the label form, so neither is read as a label,
    and the retired positional grammar (``o1.2.f7``, ``f7``) is no ref at all."""

    TOKEN_FORMS = (O1, f"{O1}/{F}", f"{O1}/{E}", f"{O1}/{V}", F, E, V, f"#{O2}/{F}", *NAMED,
                   *(f"{O2}/{name}" for name in NAMED), "m1", "m17")

    def test_token_selectors_never_take_the_label_branch(self) -> None:
        for selector in self.TOKEN_FORMS:
            with self.subTest(selector=selector):
                parsed = parse_selector(selector)
                self.assertIsNotNone(parsed)
                self.assertEqual("", parsed.label, f"{selector} must not be read as a label")

    def test_the_retired_grammar_is_no_ref(self) -> None:
        from cadgen.cad_ref_syntax import element_kind, element_ref, is_native_selector

        for selector in ("o1", "o1.2", "o1.2.f7", "o12.f19", "s2", f"{O1}/s:9d2e8c1b5a70", f"{O1}.{F}"):
            with self.subTest(selector=selector):
                self.assertNotEqual("occurrence", parse_selector(selector).selector_type)
                self.assertNotIn(parse_selector(selector).selector_type, {"face", "edge", "vertex"})
                self.assertFalse(is_native_selector(selector))
        self.assertEqual("label", parse_selector("f45").selector_type, "a bare ordinal is a label spelling")
        self.assertEqual(f"{O1}/{F}", element_ref(O1, F))
        self.assertEqual(("face", "edge", "vertex"), (element_kind(F), element_kind(E), element_kind(V)))
        self.assertEqual(("face", "edge", "vertex"), tuple(element_kind(name) for name in NAMED))

    def test_an_element_name_names_its_feature(self) -> None:
        from cadgen.cad_ref_syntax import element_feature, is_element_name, is_feature_name

        self.assertEqual(["dial.extrude1", "dial.extrude1", "lid"], [element_feature(name) for name in NAMED])
        self.assertIsNone(element_feature(F), "a geometric token names no feature")
        self.assertTrue(all(is_element_name(name) for name in (F, E, V, *NAMED)))
        self.assertTrue(is_element_name(NAMED[0], "face") and not is_element_name(NAMED[0], "edge"))
        for value in (O1, "f7", "f:dial.extrude1", "f:9d2e8c1b5a70.3", "x:dial.extrude1.3", None):
            self.assertFalse(is_element_name(value), value)
        self.assertTrue(is_feature_name("dial.extrude1") and is_feature_name("lid"))
        self.assertFalse(is_feature_name("dial.extrude1.3") or is_feature_name("3d") or is_feature_name(""))

    def test_mates_stay_opaque(self) -> None:
        # "m1" matches the label pattern; it must still be opaque so mate handling in the
        # consumers keeps working.
        for selector in ("m1", "m2", "M3"):
            with self.subTest(selector=selector):
                self.assertEqual("opaque", parse_selector(selector).selector_type)

    def test_element_and_occurrence_forms_win_over_the_label_form(self) -> None:
        self.assertEqual("face", parse_selector(F).selector_type)
        self.assertEqual("occurrence", parse_selector(O1).selector_type)
        self.assertEqual("vertex", parse_selector(f"{O2}/{V}").selector_type)
        self.assertEqual("edge", parse_selector(f"bracket/{E}").selector_type)
        self.assertEqual("bracket", parse_selector(f"bracket/{E}").label)


class TokenBackwardsCompatibilityTest(unittest.TestCase):
    def test_bare_tokens_carry_no_file_prefix(self) -> None:
        for text in (f"#{O1}", f"#{O1}/{F}", f"#{F}", "#m1", "#", f"#{O1},{F}"):
            with self.subTest(text=text):
                self.assertEqual(("", text[1:]), split_cad_ref(text), f"{text} must carry no file prefix")


class RefFileGuardTest(unittest.TestCase):
    """A ref's file prefix must match the file the command is looking at, or be refused.

    CLIs never resolve a prefix to a path -- the agent does that and passes the file separately.
    What a CLI must do is refuse a prefix naming some OTHER file, because the alternative is
    inspecting the file it was pointed at and reporting a confident answer about geometry the
    user did not ask about.
    """

    DOCUMENT = "/work/projects/STEP/shock_absorber.step"

    def test_a_root_relative_or_absolute_prefix_names_the_document(self) -> None:
        # The viewer names a file by its path under whichever root it serves, or absolutely when
        # it has none: each is a segment-aligned suffix of the document's own path.
        for prefix in (
            "shock_absorber.step",
            "STEP/shock_absorber.step",
            "projects/STEP/shock_absorber.step",
            "/work/projects/STEP/shock_absorber.step",
        ):
            with self.subTest(prefix=prefix):
                ensure_ref_file_matches(prefix, self.DOCUMENT)

    def test_an_empty_prefix_is_always_fine(self) -> None:
        ensure_ref_file_matches("", self.DOCUMENT)

    def test_a_foreign_file_is_refused_and_the_message_names_both(self) -> None:
        with self.assertRaises(ValueError) as raised:
            ensure_ref_file_matches("STEP/other_part.step", self.DOCUMENT)
        message = str(raised.exception)
        self.assertIn("other_part", message)
        self.assertIn("shock_absorber", message)

    def test_only_the_file_itself_names_it(self) -> None:
        # A bare stem, a script, a substring of the name or another folder's file of the same
        # name would each resolve a ref to a file the user never named.
        for prefix in (
            "shock_absorber",
            "shock_absorber.py",
            "absorber.step",
            "other/STEP/shock_absorber.step",
            "/elsewhere/projects/STEP/shock_absorber.step",
            # An absolute path is a path, not the end of one: this names /projects/..., not the document.
            "/projects/STEP/shock_absorber.step",
        ):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                ensure_ref_file_matches(prefix, self.DOCUMENT)

    def test_a_prefix_is_read_as_a_path(self) -> None:
        # Real files: links resolve, `~` expands, and a relative prefix is read from the working directory.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        document = tmp / "real" / "STEP" / "part.step"
        document.parent.mkdir(parents=True)
        document.write_text("ISO-10303-21;", encoding="utf-8")
        (tmp / "link").symlink_to(tmp / "real", target_is_directory=True)
        ensure_ref_file_matches(str(tmp / "link" / "STEP" / "part.step"), str(document))
        with mock.patch.dict(os.environ, {"HOME": str(tmp), "USERPROFILE": str(tmp)}):
            ensure_ref_file_matches("~/link/STEP/part.step", str(document))
        with contextlib.chdir(tmp / "real"):
            ensure_ref_file_matches("STEP/part.step", str(document))
        # From a folder with its own STEP/part.step, the same relative prefix names that other file.
        other = tmp / "other" / "STEP" / "part.step"
        other.parent.mkdir(parents=True)
        other.write_text("ISO-10303-21;", encoding="utf-8")
        with contextlib.chdir(tmp / "other"), self.assertRaises(ValueError):
            ensure_ref_file_matches("STEP/part.step", str(document))

    def test_a_quoted_prefix_is_decoded_rather_than_cut_at_a_hash(self) -> None:
        # The viewer JSON-quotes a prefix holding a space, a quote, a '#' or a backslash.
        for path in (
            "/work/CAD models/part #2.step",
            "C:\\work\\part.step",
            "models/Hex Drive Screw (2).STEP",
            'models/café #1 "screw".STEP',
        ):
            with self.subTest(path=path):
                token = json.dumps(path, ensure_ascii=False) + f"#{O1}/{F},{E}"
                self.assertEqual((path, f"{O1}/{F},{E}"), split_cad_ref(token))
        self.assertEqual(("STEP/part.step", f"{O1}/{F}"), split_cad_ref(f"STEP/part.step#{O1}/{F}"))
        self.assertEqual(("", f"{O1}/{F}"), split_cad_ref(f"#{O1}/{F}"))
        self.assertEqual(("", f"{O1}/{F}"), split_cad_ref(f"{O1}/{F}"))

    def test_path_has_suffix_is_segment_aligned(self) -> None:
        self.assertTrue(path_has_suffix("a/b/plate.stl", "plate.stl"))
        self.assertTrue(path_has_suffix("a/b/plate.stl", "b/plate.stl"))
        self.assertFalse(path_has_suffix("a/b/plate.stl", "late.stl"))
        self.assertFalse(path_has_suffix("plate.stl", "a/plate.stl"))
        self.assertFalse(path_has_suffix("a/b/plate.stl", ""))


if __name__ == "__main__":
    unittest.main()
