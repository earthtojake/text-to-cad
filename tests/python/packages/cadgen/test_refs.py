"""Every ref resolves through one resolver (``cadgen.refs``), to exactly one node, and
one element of a leaf, or it raises.

The alias numbering is user-facing -- people paste `#cast_rim:5spoke_2` -- so its order is a
contract, not an implementation detail. The ambiguity rule is the load-bearing one: a bare
label shared by two parts must refuse to resolve rather than silently pick the first, because
picking the first renders the wrong wheel and looks like success.

Occurrence ids are tokens (``o:`` + 12 hex digits) minted from the tree, so a token carries
no position: duplicates are numbered in the order the rows come, which is tree order.
"""

from __future__ import annotations

import unittest

from cadgen.label_refs import LabelResolutionError, build_label_aliases
from cadgen.refs import Resolved, Space, UnknownNode, descriptor_space, resolve
from tests.python.support.tree_ids import node_id, tokenized


def tok(n: int) -> str:
    """A token-shaped occurrence id; the alias builder treats ids as opaque."""
    return f"o:{n:012x}"


O1, O2, O3, O4, O5, O6, O7 = (tok(n) for n in range(1, 8))
F45 = "f:" + "a" * 11 + "5"
E3 = "e:" + "b" * 11 + "3"


def space(names: dict[str, list[str]], *, leaves: tuple[str, ...] = (), **elements) -> Space:
    """A space whose nodes are leaves: every node ``names`` names, and ``leaves``."""
    members = {token: [token] for token in [*leaves, *(t for tokens in names.values() for t in tokens)]}
    return Space(members, names, **elements)


def faces_and_edges(faces: list[str], edges: list[str]):
    """An ``elements`` provider: every leaf's faces and edges are named so."""
    return lambda token, kind: {"face": faces, "edge": edges, "vertex": []}[kind]


ALIAS_CASES = [
    {
        "why": "unique labels get a bare alias and no number",
        "rows": [
            {"id": O1, "name": "eye_shank"},
            {"id": O2, "name": "pressure_tube"},
        ],
        "aliases": {"eye_shank": O1, "pressure_tube": O2},
        "ambiguous": {},
    },
    {
        "why": "duplicates get numbered aliases in row (tree) order; the bare name is ambiguous",
        "rows": [
            {"id": O3, "name": "cast_rim:5spoke"},
            {"id": O7, "name": "cast_rim:5spoke"},
        ],
        "aliases": {"cast_rim:5spoke_1": O3, "cast_rim:5spoke_2": O7},
        "ambiguous": {"cast_rim:5spoke": ["cast_rim:5spoke_1", "cast_rim:5spoke_2"]},
    },
    {
        "why": "numbering follows the rows, never the token's spelling",
        "rows": [
            {"id": tok(0xFFFF), "name": "bolt"},
            {"id": O2, "name": "bolt"},
        ],
        "aliases": {"bolt_1": tok(0xFFFF), "bolt_2": O2},
        "ambiguous": {"bolt": ["bolt_1", "bolt_2"]},
    },
    {
        "why": "a numbered alias never collides with a label an author actually wrote",
        "rows": [
            {"id": O1, "name": "servo_end_mount"},
            {"id": O2, "name": "servo_end_mount"},
            {"id": O3, "name": "servo_end_mount_1"},
        ],
        "aliases": {"servo_end_mount_2": O1, "servo_end_mount_3": O2, "servo_end_mount_1": O3},
        "ambiguous": {"servo_end_mount": ["servo_end_mount_2", "servo_end_mount_3"]},
    },
    {
        "why": "names that cannot be labels are reachable by token only",
        "rows": [
            {"id": O1, "name": tok(4)},
            {"id": O2, "name": "o:" + "c" * 12 + "/" + F45},
            {"id": O3, "name": "m2"},
            {"id": O4, "name": "5spoke"},
            {"id": O5, "name": "has space"},
            {"id": O6, "name": "has.dot"},
            {"id": O7, "name": ""},
        ],
        "aliases": {},
        "ambiguous": {},
    },
    {
        "why": "a name spelled like the retired numeric grammar is an ordinary label now",
        "rows": [
            {"id": O1, "name": "f12"},
            {"id": O2, "name": "o1"},
        ],
        "aliases": {"f12": O1, "o1": O2},
        "ambiguous": {},
    },
    {
        "why": "group (non-leaf) rows are addressable too",
        "rows": [
            {"id": O1, "name": "damper_body"},
            {"id": O2, "name": "pressure_tube"},
        ],
        "aliases": {"damper_body": O1, "pressure_tube": O2},
        "ambiguous": {},
    },
    {
        "why": "a row may carry the render package's `occurrenceId` spelling instead of `id`",
        "rows": [
            {"occurrenceId": O1, "name": "eye_shank"},
            {"id": O2, "name": "pressure_tube"},
        ],
        "aliases": {"eye_shank": O1, "pressure_tube": O2},
        "ambiguous": {},
    },
]


class AliasCasesTest(unittest.TestCase):
    def test_every_alias_case_matches(self) -> None:
        for case in ALIAS_CASES:
            with self.subTest(why=case.get("why", "")):
                built = build_label_aliases(case["rows"])
                self.assertEqual(case["aliases"], built["aliases"])
                self.assertEqual(
                    {k: list(v) for k, v in case["ambiguous"].items()},
                    {k: list(v) for k, v in built["ambiguous"].items()},
                )


class AliasOrderingTest(unittest.TestCase):
    def test_duplicates_are_numbered_in_row_order(self) -> None:
        rows = [
            {"id": O7, "name": "bolt"},
            {"id": O2, "name": "bolt"},
            {"id": O5, "name": "bolt"},
        ]
        built = build_label_aliases(rows)
        self.assertEqual(
            {"bolt_1": O7, "bolt_2": O2, "bolt_3": O5},
            built["aliases"],
        )

    def test_a_numbered_alias_never_steals_an_authored_name(self) -> None:
        rows = [
            {"id": O1, "name": "servo_end_mount"},
            {"id": O2, "name": "servo_end_mount"},
            {"id": O3, "name": "servo_end_mount_1"},
        ]
        built = build_label_aliases(rows)
        self.assertEqual(O3, built["aliases"]["servo_end_mount_1"])
        self.assertEqual(O1, built["aliases"]["servo_end_mount_2"])
        self.assertEqual(O2, built["aliases"]["servo_end_mount_3"])


class UnaliasableRowsTest(unittest.TestCase):
    def test_names_that_collide_with_the_token_or_mate_grammar_get_no_alias(self) -> None:
        rows = [
            {"id": O1, "name": tok(4)},
            {"id": O2, "name": F45},
            {"id": O3, "name": "m2"},
            {"id": O4, "name": "5spoke"},
            {"id": O5, "name": "has space"},
            {"id": O6, "name": "has.dot"},
            {"id": O7, "name": ""},
        ]
        built = build_label_aliases(rows)
        self.assertEqual({}, built["aliases"], "none of these may claim an alias")

    def test_rows_without_an_id_are_ignored(self) -> None:
        self.assertEqual({}, build_label_aliases([{"name": "orphan"}])["aliases"])


class ResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.space = space(
            {"eye_shank": [O1], "cast_rim:5spoke": [O3, O7]},
            elements=faces_and_edges([F45], [E3]),
        )

    def test_a_unique_label_resolves_bare(self) -> None:
        self.assertEqual(Resolved(O1), resolve("eye_shank", self.space))

    def test_a_unique_label_resolves_with_an_element(self) -> None:
        self.assertEqual(Resolved(O1, "face", 1, F45), resolve(f"eye_shank/{F45}", self.space))
        self.assertEqual(Resolved(O1, "edge", 1, E3), resolve(f"eye_shank/{E3}", self.space))

    def test_a_leading_hash_is_the_same_ref(self) -> None:
        self.assertEqual(resolve(f"eye_shank/{F45}", self.space), resolve(f"#eye_shank/{F45}", self.space))

    def test_a_numbered_duplicate_resolves(self) -> None:
        self.assertEqual(O3, resolve("cast_rim:5spoke_1", self.space).occurrence)
        self.assertEqual(O7, resolve("cast_rim:5spoke_2", self.space).occurrence)

    def test_a_bare_duplicate_raises_and_names_the_candidates(self) -> None:
        with self.assertRaises(LabelResolutionError) as raised:
            resolve("cast_rim:5spoke", self.space)
        message = str(raised.exception)
        self.assertIn("matches 2 occurrences", message)
        self.assertIn("cast_rim:5spoke_1", message)
        self.assertIn("cast_rim:5spoke_2", message)
        self.assertIn(O3, message, "the message must show which part each alias is")

    def test_an_unknown_label_raises_with_a_next_step(self) -> None:
        with self.assertRaises(UnknownNode) as raised:
            resolve("no_such_part", self.space)
        self.assertIn("no_such_part", str(raised.exception))
        self.assertIn("--mode list", str(raised.exception))

    def test_a_label_in_a_tree_with_no_names_at_all_raises(self) -> None:
        with self.assertRaises(UnknownNode):
            resolve("eye_shank", space({}, leaves=(O1,)))

    def test_an_element_no_leaf_has_is_refused_with_the_count(self) -> None:
        with self.assertRaises(ValueError) as raised:
            resolve(f"eye_shank/f:{'c' * 11}9", self.space)
        self.assertIn(f"1 faces in #{O1}", str(raised.exception))


class TokenRefsTest(unittest.TestCase):
    """A token names its node with no names at all -- a model with no labels resolves as
    one with them -- and anything that is no node's token or name is refused, never passed
    on: a mate ref, the retired ``o1.2.f7`` grammar, an unknown token."""

    def test_tokens_resolve_without_any_name(self) -> None:
        nameless = space({}, leaves=(O1, O2), elements=faces_and_edges([F45], [E3]))
        self.assertEqual(Resolved(O1), resolve(O1, nameless))
        self.assertEqual(Resolved(O2), resolve(f"#{O2}", nameless))
        self.assertEqual(Resolved(O2, "edge", 1, E3), resolve(f"#{O2}/{E3}", nameless))

    def test_what_names_no_node_is_refused(self) -> None:
        nameless = space({"eye_shank": [O1]})
        for ref in (O5, f"#{O5}/{F45}", "o1.2.f7", "m1", "", "#"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                resolve(ref, nameless)

    def test_a_bare_element_names_the_element_of_a_document_with_one_leaf(self) -> None:
        part = space({"eye_shank": [O1]}, elements=faces_and_edges([F45], [E3]))
        self.assertEqual(Resolved(O1, "face", 1, F45), resolve(F45, part))
        assembly = space({"eye_shank": [O1], "pressure_tube": [O2]}, elements=faces_and_edges([F45], [E3]))
        with self.assertRaises(ValueError) as raised:
            resolve(F45, assembly)
        self.assertIn("needs an occurrence token in an assembly", str(raised.exception))

    def test_a_group_has_no_elements(self) -> None:
        grouped = Space({O1: [O2, O3], O2: [O2], O3: [O3]}, {"arm": [O1]}, elements=faces_and_edges([F45], []))
        self.assertEqual(Resolved(O1), resolve("#arm", grouped))
        with self.assertRaises(ValueError) as raised:
            resolve(f"#arm/{F45}", grouped)
        self.assertIn("is a group", str(raised.exception))


class GeometricFallbackTest(unittest.TestCase):
    """A ref by geometric token copied before its element had a name still names it: the
    element of that leaf with that geometry, whatever names it now. The fallback is the
    resolver's, so every API that takes a ref takes it (decision 11)."""

    GEOMETRIC = "f:1daf4226a7a8"

    def test_a_geometric_token_finds_the_element_its_name_has_replaced(self) -> None:
        asked: list[tuple[str, str]] = []

        def tokens(token: str, kind: str) -> list[str]:
            asked.append((token, kind))
            return ["f:" + "0" * 12, self.GEOMETRIC]

        part = space({"arm": [O1]}, elements=faces_and_edges(["f:arm.box1.1", "f:arm.box1.2"], []), tokens=tokens)
        self.assertEqual(Resolved(O1), resolve("#arm", part))
        self.assertEqual([], asked, "a ref by name measures nothing")
        self.assertEqual(Resolved(O1, "face", 2, "f:arm.box1.2"), resolve(f"#arm/{self.GEOMETRIC}", part))
        self.assertEqual([(O1, "face")], asked)

    def test_a_geometric_token_no_element_has_is_refused(self) -> None:
        part = space({"arm": [O1]}, elements=faces_and_edges(["f:arm.box1.1"], []), tokens=lambda token, kind: [])
        with self.assertRaises(ValueError):
            resolve(f"#arm/{self.GEOMETRIC}", part)


class OneNameRuleTest(unittest.TestCase):
    """Every API that takes a ``#name`` reads it one way: ``read_scene`` and snapshots,
    clips (``m.get``), material assignments and mates. A name two nodes share is refused
    in each with the same numbered aliases, and an alias names the same node in each.
    Clips once moved every node of a shared name: a clip on a beam moved its whole arm."""

    # A root group `arm` holding a base and a beam also labelled `arm`.
    DESCRIPTOR, _ = tokenized({
        "occurrences": [{"id": "o1.1"}, {"id": "o1.2"}],
        "assembly": {"root": {"id": "o1", "name": "arm", "children": [
            {"id": "o1.1", "name": "base", "children": []},
            {"id": "o1.2", "name": "arm", "children": []},
        ]}},
    })

    def test_a_shared_name_is_refused_alike_and_its_aliases_name_one_node(self) -> None:
        from cadgen._internal.animation_bake import animation_targets
        from cadgen._internal.kinematics_resolve import _occurrence_id_for_ref
        from cadgen._internal.source_sidecar import resolve_materials

        root = self.DESCRIPTOR["assembly"]["root"]
        base, beam = (str(child["id"]) for child in root["children"])
        scene = descriptor_space(self.DESCRIPTOR)
        clips = animation_targets(self.DESCRIPTOR)

        def material(target: str) -> dict:
            declaration = {"definitions": {"x": {}}, "assignments": [{"targets": [target], "material": "x"}]}
            return resolve_materials(self.DESCRIPTOR, declaration)

        def mate(target: str) -> str:
            return _occurrence_id_for_ref(target, what="child", mate="lift", source_ref="arm", space=scene)

        for api, call in {
            "read_scene": lambda: resolve("#arm", scene),
            "clip": lambda: clips.resolve("#arm"),
            "material": lambda: material("#arm"),
            "mate": lambda: mate("#arm"),
        }.items():
            with self.subTest(api=api), self.assertRaises(ValueError) as caught:
                call()
            # Numbered root first, then the beam: tree order, the same in every API.
            self.assertIn(f"label 'arm' matches 2 occurrences; use one of: #arm_1 ({root['id']}), #arm_2 ({beam})",
                          str(caught.exception))

        self.assertEqual(beam, resolve("#arm_2", scene).occurrence)
        self.assertEqual((beam,), clips.resolve("#arm_2"))
        self.assertEqual([beam], list(material("#arm_2")["assignments"]))
        self.assertEqual(beam, mate("#arm_2"))
        self.assertEqual(base, mate("#base"))
        self.assertEqual(node_id(self.DESCRIPTOR, "base"), base)


if __name__ == "__main__":
    unittest.main()
