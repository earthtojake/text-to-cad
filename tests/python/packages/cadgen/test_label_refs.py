"""Label refs resolve to exactly one occurrence, or they raise.

The alias numbering is user-facing -- people paste `#cast_rim:5spoke_2` -- so its order is a
contract, not an implementation detail. The ambiguity rule is the load-bearing one: a bare
label shared by two parts must refuse to resolve rather than silently pick the first, because
picking the first renders the wrong wheel and looks like success.
"""

from __future__ import annotations

import json
import unittest

from tests.python.support.paths import repo_path

from cadgen.label_refs import (
    LabelResolutionError,
    build_label_aliases,
    label_ref_for_occurrence,
    resolve_label_selectors,
    selectors_contain_label,
)


FIXTURE_PATH = repo_path("packages", "cadjs", "src", "lib", "cadRefs.parity.json")


def _alias_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["aliasCases"]


class AliasFixtureParityTest(unittest.TestCase):
    """The same alias cases the JS suite asserts, so both languages number identically."""

    def test_every_alias_case_matches(self) -> None:
        for case in _alias_cases():
            with self.subTest(why=case.get("why", "")):
                built = build_label_aliases(case["rows"])
                self.assertEqual(case["aliases"], built["aliases"])
                self.assertEqual(
                    {k: list(v) for k, v in case["ambiguous"].items()},
                    {k: list(v) for k, v in built["ambiguous"].items()},
                )


class AliasOrderingTest(unittest.TestCase):
    def test_duplicates_are_numbered_in_occurrence_tree_order(self) -> None:
        rows = [
            {"id": "o1.10", "name": "bolt"},
            {"id": "o1.2", "name": "bolt"},
            {"id": "o1.9", "name": "bolt"},
        ]
        built = build_label_aliases(rows)
        self.assertEqual(
            {"bolt_1": "o1.2", "bolt_2": "o1.9", "bolt_3": "o1.10"},
            built["aliases"],
        )

    def test_deep_paths_sort_segment_by_segment(self) -> None:
        rows = [
            {"id": "o1.2.11", "name": "pin"},
            {"id": "o1.2.3", "name": "pin"},
        ]
        self.assertEqual(
            {"pin_1": "o1.2.3", "pin_2": "o1.2.11"},
            build_label_aliases(rows)["aliases"],
        )

    def test_a_numbered_alias_never_steals_an_authored_name(self) -> None:
        rows = [
            {"id": "o1.1", "name": "servo_end_mount"},
            {"id": "o1.2", "name": "servo_end_mount"},
            {"id": "o1.3", "name": "servo_end_mount_1"},
        ]
        built = build_label_aliases(rows)
        self.assertEqual("o1.3", built["aliases"]["servo_end_mount_1"])
        self.assertEqual("o1.1", built["aliases"]["servo_end_mount_2"])
        self.assertEqual("o1.2", built["aliases"]["servo_end_mount_3"])


class UnaliasableRowsTest(unittest.TestCase):
    def test_names_that_collide_with_the_numeric_grammar_get_no_alias(self) -> None:
        rows = [
            {"id": "o1.1", "name": "o1.4"},
            {"id": "o1.2", "name": "f12"},
            {"id": "o1.3", "name": "m2"},
            {"id": "o1.4", "name": "5spoke"},
            {"id": "o1.5", "name": "has space"},
            {"id": "o1.6", "name": "has.dot"},
            {"id": "o1.7", "name": ""},
        ]
        built = build_label_aliases(rows)
        self.assertEqual({}, built["aliases"], "none of these may claim an alias")

    def test_rows_without_an_id_are_ignored(self) -> None:
        self.assertEqual({}, build_label_aliases([{"name": "orphan"}])["aliases"])


class ResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.alias_map = build_label_aliases(
            [
                {"id": "o1.1.2", "name": "eye_shank"},
                {"id": "o1.3", "name": "cast_rim:5spoke"},
                {"id": "o1.7", "name": "cast_rim:5spoke"},
            ]
        )

    def test_a_unique_label_resolves_bare(self) -> None:
        self.assertEqual(["o1.1.2"], resolve_label_selectors(["eye_shank"], self.alias_map))

    def test_a_unique_label_resolves_with_an_entity(self) -> None:
        self.assertEqual(
            ["o1.1.2.f45"], resolve_label_selectors(["eye_shank.f45"], self.alias_map)
        )
        self.assertEqual(
            ["o1.1.2.e3"], resolve_label_selectors(["eye_shank.e3"], self.alias_map)
        )

    def test_a_leading_hash_is_preserved(self) -> None:
        self.assertEqual(["#o1.1.2.f45"], resolve_label_selectors(["#eye_shank.f45"], self.alias_map))

    def test_a_numbered_duplicate_resolves(self) -> None:
        self.assertEqual(["o1.3"], resolve_label_selectors(["cast_rim:5spoke_1"], self.alias_map))
        self.assertEqual(["o1.7"], resolve_label_selectors(["cast_rim:5spoke_2"], self.alias_map))

    def test_a_bare_duplicate_raises_and_names_the_candidates(self) -> None:
        with self.assertRaises(LabelResolutionError) as raised:
            resolve_label_selectors(["cast_rim:5spoke"], self.alias_map)
        message = str(raised.exception)
        self.assertIn("matches 2 occurrences", message)
        self.assertIn("cast_rim:5spoke_1", message)
        self.assertIn("cast_rim:5spoke_2", message)
        self.assertIn("o1.3", message, "the message must show which part each alias is")

    def test_an_unknown_label_raises_with_a_next_step(self) -> None:
        with self.assertRaises(LabelResolutionError) as raised:
            resolve_label_selectors(["no_such_part"], self.alias_map)
        self.assertIn("no_such_part", str(raised.exception))
        self.assertIn("--mode list", str(raised.exception))

    def test_a_label_with_no_alias_map_at_all_raises(self) -> None:
        with self.assertRaises(LabelResolutionError):
            resolve_label_selectors(["eye_shank"], None)


class NumericPassThroughTest(unittest.TestCase):
    """Backwards compatibility: resolution must not touch anything numeric."""

    UNTOUCHED = ["o1", "o1.2", "o12.f19", "o1.2.3.4.5.6.e7", "f45", "s2", "e9", "v4", "m1", "#o2.f1"]

    def test_numeric_and_opaque_selectors_pass_through_byte_for_byte(self) -> None:
        alias_map = build_label_aliases([{"id": "o1.1", "name": "eye_shank"}])
        self.assertEqual(self.UNTOUCHED, resolve_label_selectors(self.UNTOUCHED, alias_map))

    def test_numeric_selectors_resolve_without_an_alias_map(self) -> None:
        # A model with no labels at all must keep working exactly as before.
        self.assertEqual(self.UNTOUCHED, resolve_label_selectors(self.UNTOUCHED, None))

    def test_selectors_contain_label_only_flags_labels(self) -> None:
        self.assertFalse(selectors_contain_label(self.UNTOUCHED))
        self.assertTrue(selectors_contain_label(["o1.2", "eye_shank"]))


class LabelRefLookupTest(unittest.TestCase):
    def test_the_paste_spelling_is_reported_for_an_occurrence(self) -> None:
        alias_map = build_label_aliases(
            [{"id": "o1.1", "name": "eye_shank"}, {"id": "o1.2", "name": "tube"}]
        )
        self.assertEqual("#eye_shank", label_ref_for_occurrence(alias_map, "o1.1"))
        self.assertEqual("", label_ref_for_occurrence(alias_map, "o9.9"))


if __name__ == "__main__":
    unittest.main()


class SceneSelectionResolvesLabelsTest(unittest.TestCase):
    """`validate` and `interfere` select against the build123d scene, not the selector index.

    They were missed by the first pass and failed in the worst way available: a label matched
    no occurrence, so both reported a clean run over zero parts and exited 0. A validation tool
    that silently validates nothing is more dangerous than one that errors.
    """

    class _Occ:
        def __init__(self, ref, name):
            self.ref = ref
            self.name = name

    def _selected(self, refs, rows=None):
        from cadgen.interference import _selected

        occurrences = [self._Occ("o1.1", "eye_shank"), self._Occ("o1.2", "pressure_tube")]
        return [o.ref for o in _selected(occurrences, refs, label_rows=rows)]

    def test_a_leaf_label_selects_the_same_occurrence_as_its_numeric_ref(self) -> None:
        self.assertEqual(["o1.1"], self._selected(["eye_shank"]))
        self.assertEqual(["o1.1"], self._selected(["o1.1"]))
        self.assertEqual(["o1.1"], self._selected(["#eye_shank"]))

    def test_numeric_refs_are_unchanged(self) -> None:
        self.assertEqual(["o1.1", "o1.2"], self._selected(["o1.1", "o1.2"]))
        self.assertEqual(["o1.1", "o1.2"], self._selected([]), "no refs still means everything")

    def test_an_unknown_label_raises_rather_than_selecting_nothing(self) -> None:
        with self.assertRaises(LabelResolutionError):
            self._selected(["no_such_part"])

    def test_a_subassembly_label_selects_its_whole_subtree(self) -> None:
        # Group rows come from scene_label_rows, which walks every node; the prefix match then
        # pulls in the leaves. Without the group row this label would look unknown here while
        # resolving fine through snapshot and inspect refs -- the same ref working on four CLIs
        # and failing on two.
        rows = [
            {"id": "o1", "name": "damper_body"},
            {"id": "o1.1", "name": "eye_shank"},
            {"id": "o1.2", "name": "pressure_tube"},
        ]
        self.assertEqual(["o1.1", "o1.2"], self._selected(["damper_body"], rows))
        self.assertEqual(["o1.1", "o1.2"], self._selected(["o1"], rows))
