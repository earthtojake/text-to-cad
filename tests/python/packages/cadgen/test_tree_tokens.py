"""Occurrence tokens (``cadgen._internal.tree_tokens``): a node's token is a function of its
place in its tree -- parent, name, rounded placement, rank among identical siblings --
so a sibling inserted, a rebuild and a reader of the saved document keep it."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.tree_tokens import (  # noqa: E402
    OCCURRENCE_TOKEN_RE,
    ROTATION_QUANTUM,
    TRANSLATION_QUANTUM,
    assign_tokens,
    child_token,
    is_occurrence_token,
    positional_paths,
    retoken,
    root_token,
    rounded_placement,
)

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _moved(x: float, y: float = 0.0, z: float = 0.0) -> list[float]:
    return [1.0, 0.0, 0.0, x, 0.0, 1.0, 0.0, y, 0.0, 0.0, 1.0, z, 0.0, 0.0, 0.0, 1.0]


def _leaf(node_id: str, name: str | None) -> dict:
    return {"id": node_id, "name": name, "nodeType": "part", "children": []}


def _tree(children: list[tuple[str, str | None, list[float]]], *, label: str = "model") -> dict:
    occurrences = [{"id": node_id, "name": name, "component": "c", "transform": transform}
                   for node_id, name, transform in children]
    root = {"id": "o1", "name": label, "nodeType": "assembly", "leafPartIds": [c[0] for c in children],
            "children": [_leaf(node_id, name) for node_id, name, _ in children]}
    return {"label": label, "occurrences": occurrences, "links": [], "assembly": {"root": root}}


def _tokens(tree: dict) -> dict[str, str]:
    return assign_tokens(tree["assembly"]["root"], tree["occurrences"], tree["links"], label=tree["label"])


class TokenTest(unittest.TestCase):
    def test_a_token_is_o_and_twelve_hex_from_parent_name_and_placement(self) -> None:
        root = root_token("model")
        self.assertRegex(root, OCCURRENCE_TOKEN_RE)
        self.assertTrue(is_occurrence_token(root))
        self.assertFalse(is_occurrence_token("o1.2"))
        self.assertFalse(is_occurrence_token("o:" + "g" * 12))
        leaf = child_token(root, "pin", _moved(1.0))
        self.assertRegex(leaf, OCCURRENCE_TOKEN_RE)
        self.assertEqual(leaf, child_token(root, "pin", _moved(1.0)))
        self.assertNotEqual(leaf, child_token(root, "pin", _moved(2.0)), "another placement")
        self.assertNotEqual(leaf, child_token(root, "peg", _moved(1.0)), "another name")
        self.assertNotEqual(leaf, child_token(root_token("other"), "pin", _moved(1.0)), "another parent")
        self.assertNotEqual(leaf, child_token(root, "pin", None), "a group has no placement")
        self.assertNotEqual(leaf, child_token(root, "pin", _moved(1.0), rank=1), "a ranked sibling")

    def test_placements_round_to_the_quanta(self) -> None:
        self.assertIsNone(rounded_placement(None))
        self.assertEqual(len(rounded_placement(IDENTITY)), 12)
        nudged = _moved(1.0 + TRANSLATION_QUANTUM / 10)
        self.assertEqual(rounded_placement(nudged), rounded_placement(_moved(1.0)))
        self.assertNotEqual(rounded_placement(_moved(1.0 + 2 * TRANSLATION_QUANTUM)), rounded_placement(_moved(1.0)))
        turned = list(IDENTITY)
        turned[0] = 1.0 - ROTATION_QUANTUM / 10
        self.assertEqual(rounded_placement(turned), rounded_placement(IDENTITY))
        with self.assertRaises(ValueError):
            rounded_placement([1.0, 2.0])

    def test_a_translation_rounds_as_a_step_file_states_it(self) -> None:
        """A STEP file states a real to twelve decimals, or thirteen significant digits from
        a thousand up, and a reader returns exactly the number stated (``step_reals``): a
        translation within a stated digit of a rounding boundary rounds as stated, so the
        token a reader mints from the file is the result's by construction."""
        from cadgen._internal.step_reals import stated_real

        candidates = (1234.0 + (n + 0.5) * TRANSLATION_QUANTUM - 3e-10 for n in range(1000))
        stated = next(value for value in candidates
                      if round(value / TRANSLATION_QUANTUM) != round(stated_real(value) / TRANSLATION_QUANTUM))
        self.assertEqual(rounded_placement(_moved(stated)), rounded_placement(_moved(stated_real(stated))))
        self.assertEqual(rounded_placement(_moved(1.0 + TRANSLATION_QUANTUM / 10)), rounded_placement(_moved(1.0)))

    def test_tokens_are_assigned_from_the_tree_and_a_sibling_inserted_moves_none(self) -> None:
        before = _tree([("o1.1", "base", IDENTITY), ("o1.2", "pin", _moved(5.0))])
        after = _tree([("o1.1", "base", IDENTITY), ("o1.2", "spacer", _moved(2.0)), ("o1.3", "pin", _moved(5.0))])
        first, second = _tokens(before), _tokens(after)
        self.assertEqual(first["o1"], second["o1"], "the root is named by the label")
        self.assertEqual(first["o1.1"], second["o1.1"])
        self.assertEqual(first["o1.2"], second["o1.3"], "the pin keeps its token behind the inserted spacer")
        self.assertEqual(len(set(second.values())), 4)
        self.assertNotEqual(_tokens(_tree([("o1.1", "base", IDENTITY)], label="other"))["o1.1"], first["o1.1"],
                            "the tree's label names the root, and the root its children")

    def test_identical_siblings_are_ranked_in_tree_order(self) -> None:
        tree = _tree([("o1.1", None, IDENTITY), ("o1.2", None, IDENTITY), ("o1.3", None, _moved(1.0))])
        tokens = _tokens(tree)
        self.assertEqual(len(set(tokens.values())), 4, "two unnamed parts at one placement are two tokens")
        self.assertEqual(tokens["o1.1"], child_token(tokens["o1"], None, IDENTITY))
        self.assertEqual(tokens["o1.2"], child_token(tokens["o1"], None, IDENTITY, rank=1))
        self.assertEqual(tokens["o1.3"], child_token(tokens["o1"], None, _moved(1.0)))

    def test_groups_and_links_hash_parent_and_name_alone_unless_a_link_is_a_leaf(self) -> None:
        group = {"id": "o1.1", "name": "arm", "nodeType": "assembly", "children": [_leaf("o1.1.1", "pin")]}
        link = {"id": "o1.2", "name": "wheel", "nodeType": "link", "tree": "t" * 64, "children": []}
        root = {"id": "o1", "name": "model", "nodeType": "assembly", "children": [group, link]}
        occurrences = [{"id": "o1.1.1", "name": "pin", "component": "c", "transform": _moved(3.0)}]
        links = [{"id": "o1.2", "name": "wheel", "tree": "t" * 64, "transform": _moved(9.0)}]
        tokens = assign_tokens(root, occurrences, links, label="model")
        self.assertEqual(tokens["o1.1"], child_token(tokens["o1"], "arm", None))
        self.assertEqual(tokens["o1.1.1"], child_token(tokens["o1.1"], "pin", _moved(3.0)))
        self.assertEqual(tokens["o1.2"], child_token(tokens["o1"], "wheel", None), "a link to an assembly is a group")
        as_leaf = assign_tokens(root, occurrences, links, label="model", link_leaf={"o1.2": _moved(9.0)})
        self.assertEqual(as_leaf["o1.2"], child_token(tokens["o1"], "wheel", _moved(9.0)),
                         "a link to a part is the leaf it flattens to")
        self.assertEqual(as_leaf["o1.1.1"], tokens["o1.1.1"])

    def test_retoken_rewrites_every_id_and_refuses_an_unknown_one(self) -> None:
        tree = _tree([("o1.1", "base", IDENTITY), ("o1.2", "pin", _moved(5.0))])
        tree["appearance"] = {"assignments": {"o1.2": {"material": "steel"}}}
        mapping = _tokens(tree)
        out = retoken(tree, mapping)
        self.assertEqual(out["assembly"]["root"]["id"], mapping["o1"])
        self.assertEqual([node["id"] for node in out["assembly"]["root"]["children"]], [mapping["o1.1"], mapping["o1.2"]])
        self.assertEqual(out["assembly"]["root"]["leafPartIds"], [mapping["o1.1"], mapping["o1.2"]])
        self.assertEqual([row["id"] for row in out["occurrences"]], [mapping["o1.1"], mapping["o1.2"]])
        self.assertEqual(out["appearance"]["assignments"], {mapping["o1.2"]: {"material": "steel"}})
        self.assertEqual(tree["assembly"]["root"]["id"], "o1", "the input is not rewritten in place")
        with self.assertRaises(KeyError):
            retoken({**tree, "occurrences": [*tree["occurrences"], {"id": "o1.9", "transform": IDENTITY}]}, mapping)

    def test_positional_paths_join_nodes_to_the_readers_product_paths(self) -> None:
        root = {"id": "r", "children": [{"id": "a", "children": [{"id": "a1"}, {"id": "a2"}]}, {"id": "b"}]}
        self.assertEqual(positional_paths(root), {"r": (1,), "a": (1, 1), "a1": (1, 1, 1), "a2": (1, 1, 2), "b": (1, 2)})


class BuiltTreeTokensTest(unittest.TestCase):
    """The build mints tokens from the compound; the saved document reads them back."""

    def setUp(self) -> None:
        import os
        from pathlib import Path
        from unittest import mock

        from tests.python.support.tmp_root import generated_cad_directory

        self.tmp = generated_cad_directory(prefix="tree-tokens-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)

    def test_a_tree_minted_before_translations_rounded_as_stated_is_never_read(self) -> None:
        """Before a translation rounded as the STEP file states it, a leaf within a stated
        digit of a rounding boundary was minted another id than it is now; a tree of that
        format is another schema, which is never read, so no id it holds meets the one minted
        today."""
        import json

        from build123d import Box, Compound, Pos

        from cadgen._internal import tree_tokens
        from cadgen._internal.component_package import canonical_json_bytes
        from cadgen._internal.step_reals import stated_real
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.objects import put_object, read_verified_object
        from cadgen.store.trees import get_tree

        candidates = (1234.0 + (n + 0.5) * TRANSLATION_QUANTUM - 3e-10 for n in range(1000))
        stated = next(value for value in candidates
                      if round(value / TRANSLATION_QUANTUM) != round(stated_real(value) / TRANSLATION_QUANTUM))
        base, pin = Box(2, 2, 2), Pos(stated, 0, 0) * Box(1, 1, 1)
        base.label, pin.label = "base", "pin"
        tree_hash = build_tree_from_compound(Compound(children=[base, pin], label="fixture"), root_name="fixture")[0]
        tree = json.loads(read_verified_object(tree_hash))
        row = next(row for row in tree["occurrences"] if row["name"] == "pin")
        unstated = [round(value / (TRANSLATION_QUANTUM if index % 4 == 3 else ROTATION_QUANTUM))
                    for index, value in enumerate(row["transform"][:12])]
        then = tree_tokens._token([tree["assembly"]["root"]["id"], "pin", unstated])
        self.assertNotEqual(then, row["id"], "the premise: its translation rounded unstated, the pin had another id")
        older = json.loads(json.dumps(tree).replace(row["id"], then))
        older["schemaVersion"] = 5
        self.assertIsNone(get_tree(put_object(canonical_json_bytes(older))))
        self.assertIsNotNone(get_tree(tree_hash))

    def test_a_rebuild_with_a_sibling_inserted_keeps_every_other_token(self) -> None:
        from build123d import Box, Compound, Cylinder, Pos

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.trees import flatten

        def labelled(shape, label):
            shape.label = label
            return shape

        def model(spacer: bool):
            children = [labelled(Box(10, 10, 2), "base"), labelled(Pos(0, 0, 6) * Cylinder(2, 8), "pin")]
            if spacer:
                children.insert(1, labelled(Pos(20, 0, 0) * Box(4, 4, 4), "spacer"))
            return Compound(children=children, label="fixture")

        first = flatten(build_tree_from_compound(model(False), root_name="fixture")[0])
        second = flatten(build_tree_from_compound(model(True), root_name="fixture")[0])
        by_name = lambda descriptor: {row["name"]: row["id"] for row in descriptor["occurrences"]}  # noqa: E731
        a, b = by_name(first), by_name(second)
        self.assertEqual(a["base"], b["base"])
        self.assertEqual(a["pin"], b["pin"], "the pin's token survives the spacer inserted before it")
        self.assertEqual(first["assembly"]["root"]["id"], second["assembly"]["root"]["id"])
        for descriptor in (first, second):
            for row in descriptor["occurrences"]:
                self.assertTrue(is_occurrence_token(row["id"]), row["id"])
            self.assertEqual(descriptor["assembly"]["root"]["leafPartIds"], [row["id"] for row in descriptor["occurrences"]])

    def test_the_saved_document_mints_the_same_tokens(self) -> None:
        from build123d import Box, Compound, Cylinder, Pos, export_step, import_step

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.trees import flatten

        base, pin = Box(10, 10, 2), Pos(0, 0, 6) * Cylinder(2, 8)
        base.label, pin.label = "base", "pin"
        model = Compound(children=[base, pin], label="fixture")
        built = flatten(build_tree_from_compound(model, root_name="fixture")[0])
        step = self.root / "fixture.step"
        export_step(model, str(step))
        read = flatten(build_tree_from_compound(import_step(str(step)), root_name="fixture")[0])
        self.assertEqual({row["name"]: row["id"] for row in built["occurrences"]},
                         {row["name"]: row["id"] for row in read["occurrences"]})
        self.assertEqual(built["assembly"]["root"]["id"], read["assembly"]["root"]["id"])


if __name__ == "__main__":
    unittest.main()
