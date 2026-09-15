"""Flattening preserves exact linked geometry and root color inheritance."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


IDENTITY = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]


def _part(occurrence_id: str, name: str) -> dict:
    return {
        "id": occurrence_id,
        "name": name,
        "nodeType": "part",
        "leafPartIds": [occurrence_id],
        "children": [],
    }


class TreeLinkIntegrity(unittest.TestCase):
    def setUp(self) -> None:
        temporary = generated_cad_directory(prefix="tree-link-integrity-")
        self.addCleanup(temporary.cleanup)
        self.store = Path(temporary.name) / "store"
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_missing_linked_tree_fails_instead_of_returning_partial_geometry(self) -> None:
        from cadgen.store.trees import flatten, put_tree

        missing = "a" * 64
        parent = put_tree({
            "label": "parent",
            "units": "mm", "entryKind": "assembly",
            "components": {},
            "occurrences": [],
            "links": [{"id": "o1.1", "name": "missing", "tree": missing, "transform": IDENTITY}],
            "assembly": {
                "root": {
                    "id": "o1",
                    "name": "parent",
                    "nodeType": "assembly",
                    "leafPartIds": ["o1.1"],
                    "children": [
                        {"id": "o1.1", "name": "missing", "nodeType": "link", "tree": missing, "children": []}
                    ],
                }
            },
        })

        with self.assertRaisesRegex(FileNotFoundError, rf"linked tree object missing: {missing}"):
            flatten(parent)

    def test_link_color_applies_only_where_the_child_has_no_authored_color(self) -> None:
        from cadgen.store.trees import flatten, put_tree
        from tests.python.support.store_fixtures import seed_result

        red = [1.0, 0.0, 0.0, 1.0]
        green = [0.0, 1.0, 0.0, 1.0]
        blue = [0.0, 0.0, 1.0, 1.0]
        fixture = self.store.parent / "color-fixture.step"
        fixture.write_bytes(b"geometry fixture input")
        child = seed_result(fixture, {"label": "child", "components": {
                "plain": {},
                "component-colored": {"color": green},
                "occurrence-colored": {},
            },
            "occurrences": [
                {"id": "o1.1", "name": "plain", "component": "plain", "transform": IDENTITY},
                {
                    "id": "o1.2", "name": "component-colored", "component": "component-colored",
                    "transform": IDENTITY,
                },
                {
                    "id": "o1.3", "name": "occurrence-colored", "component": "occurrence-colored",
                    "transform": IDENTITY, "color": blue,
                },
            ],
            "assembly": {
                "root": {
                    "id": "o1", "name": "child", "nodeType": "assembly",
                    "leafPartIds": ["o1.1", "o1.2", "o1.3"],
                    "children": [
                        _part("o1.1", "plain"),
                        _part("o1.2", "component-colored"),
                        _part("o1.3", "occurrence-colored"),
                    ],
                }
            },
        })
        parent = put_tree({
            "label": "parent",
            "units": "mm", "entryKind": "assembly",
            "components": {},
            "occurrences": [],
            "links": [
                {"id": "o1.1", "name": "placed-child", "tree": child, "transform": IDENTITY, "color": red}
            ],
            "assembly": {
                "root": {
                    "id": "o1", "name": "parent", "nodeType": "assembly",
                    "leafPartIds": ["o1.1"],
                    "children": [
                        {"id": "o1.1", "name": "placed-child", "nodeType": "link", "tree": child, "children": []}
                    ],
                }
            },
        })

        descriptor = flatten(parent)
        by_name = {occurrence["name"]: occurrence for occurrence in descriptor["occurrences"]}
        self.assertEqual(by_name["plain"]["color"], red)
        self.assertNotIn("color", by_name["component-colored"])
        colored_cid = by_name["component-colored"]["component"]
        self.assertEqual(descriptor["components"][colored_cid]["color"], green)
        self.assertEqual(by_name["occurrence-colored"]["color"], blue)

    def test_recolored_part_link_overrides_its_old_color_through_materialize_and_step(self) -> None:
        from build123d import Color, Compound

        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.trees import flatten

        red = [1.0, 0.0, 0.0, 1.0]
        blue = [0.0, 0.0, 1.0, 1.0]
        from build123d import Box

        source = Box(1, 2, 3)
        source.label = "red-child"
        source.color = Color(1.0, 0.0, 0.0)
        child_tree, _child, _stats = build_tree_from_compound(
            source, root_name="red-child"
        )
        child = materialize(child_tree, label="recolored-child")
        child.color = Color(0.0, 0.0, 1.0)

        parent_tree, parent, _stats = build_tree_from_compound(
            Compound(children=[child], label="parent"), root_name="parent"
        )
        self.assertEqual(parent["links"][0]["tree"], child_tree)
        self.assertEqual(parent["links"][0]["color"], blue)
        occurrence = flatten(parent_tree)["occurrences"][0]
        self.assertEqual(occurrence["color"], blue)

        output = self.store.parent / "recolored-part.step"
        export_build123d_step_file(materialize(parent_tree), output)
        colors = list(load_step_scene(output, record_read=False).prototype_colors.values())
        self.assertEqual(len(colors), 1)
        for actual, expected in zip(colors[0], blue):
            self.assertAlmostEqual(actual, expected, places=6)


if __name__ == "__main__":
    unittest.main()
