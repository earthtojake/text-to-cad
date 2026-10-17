"""A document reads as the tree its bytes map to, and a file reads as the result it was
written from.

A document's entry may name a tree that links its children's (a model's result): every
reader flattens it, the hierarchy its file was written with. A file written from a result
names every node as the result does, so a compile of its bytes in a store that never saw
the result -- a reader with nothing but the file -- mints the result's tokens: a part placed
away from the identity, which STEP can only write inside an unnamed product of one, is that
part, and a label the reader respells is spelled as it reads.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.tree_ids import leaf_id

add_repo_path("packages/cadgen/src")


def _flat_leaves(tree: str) -> list[tuple[str, str]]:
    """The leaves of the flattened ``tree``, in tree order, by token and name."""
    from cadgen.store.trees import flatten
    from tests.python.support.tree_ids import nodes

    flat = flatten(tree)
    names = {row["id"]: row["name"] for row in flat["occurrences"]}
    return [(node["id"], names[node["id"]]) for node in nodes(flat) if node["id"] in names]


def _compiled(path: Path) -> str:
    """The tree a compile of the file at ``path`` publishes, in the store in use."""
    from cadgen._internal.step_scene_loader import load_step_scene
    from cadgen.store.build import build_document_tree

    return build_document_tree(load_step_scene(path))[0]


class LinkedDocumentTest(unittest.TestCase):
    """An entry naming a tree that links a child's reads as the flattened tree."""

    def setUp(self) -> None:
        from build123d import Compound, Location, Solid

        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree

        self.roots = IsolatedCadRoots(self, prefix="linked-document-")
        first = Solid.make_box(2, 3, 4)
        first.label = "first"
        second = Solid.make_box(1, 1, 1).moved(Location((7, 0, 0)))
        second.label = "second"
        child, _, _ = build_tree_from_compound(Compound(children=[first, second], label="kid"), root_name="kid")
        placed = materialize(child).moved(Location((0, 30, 0)))
        placed.label = "kid"
        own = Solid.make_box(5, 5, 5)
        own.label = "own"
        self.tree, _, _ = build_tree_from_compound(Compound(children=[placed, own], label="rig"), root_name="rig")
        self.assertTrue(get_tree(self.tree)["links"], "the fixture's tree links its child's")
        self.path = self.roots.cad_root / "rig.step"
        self.digest = export_build123d_step_file(materialize(self.tree), self.path)
        note_document_tree(self.digest, self.tree)

    def test_a_linked_tree_reads_as_its_flattened_document(self) -> None:
        from cadgen._internal.step_scene_mesh import scene_leaf_occurrences
        from cadgen._internal.step_scene_package import scene_from_render_package

        scene = scene_from_render_package(self.path, step_hash=self.digest)
        self.assertIsNotNone(scene)
        self.assertEqual(_flat_leaves(self.tree), [(node.id, node.name) for node in scene_leaf_occurrences(scene)])

    def test_read_scene_and_a_listing_name_the_flattened_tree_by_its_tokens(self) -> None:
        import cadgen.step as step_door
        from cadgen import snapshot_core
        from cadgen.step_scene import read_scene
        from cadgen.store.trees import flatten

        leaves = _flat_leaves(self.tree)
        scene = read_scene(self.path)
        self.assertEqual([f"#{token}" for token, _name in leaves], [leaf.ref for leaf in scene.leaves()])
        self.assertEqual(f"#{leaf_id(flatten(self.tree), 'second')}", scene.resolve("#second").ref)
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start",
                               side_effect=AssertionError("a browser was started")):
            listing = step_door.snapshot(self.path, mode="list")
        self.assertEqual(sorted((f"#{token}", name) for token, name in leaves),
                         sorted((row["ref"], row["name"]) for row in listing.parts))


class WrittenNamesTest(unittest.TestCase):
    """A compile of a file in a store that never held its result names it as the result."""

    def setUp(self) -> None:
        self.roots = IsolatedCadRoots(self, prefix="written-names-")

    def written(self, shape, *, root_name: str) -> tuple[list[tuple[str, str]], Path]:
        """The leaves of the result tree of ``shape`` and the file written from it."""
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize

        tree, _, _ = build_tree_from_compound(shape, root_name=root_name)
        path = self.roots.cad_root / f"{root_name}.step"
        export_build123d_step_file(materialize(tree), path)
        return _flat_leaves(tree), path

    def compiled(self, path: Path) -> tuple[list[tuple[str, str]], dict]:
        """The leaves and the root of the tree a compile of ``path`` publishes in a store
        that never held its result: a reader with nothing but the file."""
        import os

        from cadgen.store.trees import get_tree

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.roots.root / f"fresh-{path.stem}")}):
            tree = _compiled(path)
            return _flat_leaves(tree), get_tree(tree)["assembly"]["root"]

    def test_a_part_placed_away_from_the_identity_reads_as_that_part(self) -> None:
        from build123d import Box, Pos

        for label in ("cap", None):
            with self.subTest(label=label):
                part = Pos(10, 0, 0) * Box(4, 4, 2)
                if label is not None:
                    part.label = label
                expected, path = self.written(part, root_name=label or "plain")
                leaves, root = self.compiled(path)
                self.assertEqual(expected, leaves)
                self.assertFalse(root["children"], "one part, no group")

    def test_a_label_the_reader_respells_is_spelled_as_it_reads(self) -> None:
        from build123d import Box, Compound, Pos

        spaced, kind, digits = Box(1, 1, 1), Pos(3, 0, 0) * Box(1, 1, 1), Pos(6, 0, 0) * Box(1, 1, 1)
        spaced.label, kind.label, digits.label = "left  hand ", "Solid", "42"
        expected, path = self.written(Compound(children=[spaced, kind, digits], label="rig"), root_name="rig")
        self.assertEqual(["left hand", "part", "part"], [name for _token, name in expected])
        self.assertEqual(expected, self.compiled(path)[0])


if __name__ == "__main__":
    unittest.main()
