from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import step_artifact_cli  # noqa: E402
from cadgen._internal.step_scene import LoadedStepScene, OccurrenceNode  # noqa: E402

_IDENTITY = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def _node(path: tuple[int, ...], children: list[OccurrenceNode] | None = None) -> OccurrenceNode:
    return OccurrenceNode(
        path=path,
        name=None,
        source_name=None,
        transform=_IDENTITY,
        prototype_key=None,
        children=children or [],
    )


def _scene(*roots: OccurrenceNode) -> LoadedStepScene:
    return LoadedStepScene(
        step_path=Path("synthetic.step"),
        roots=list(roots),
        prototype_shapes={},
    )


class SceneHasAssemblyStructureTests(unittest.TestCase):
    """`_scene_has_assembly_structure` classifies by the shape of the scene tree.

    The check is deliberately shallow: an assembly is a STEP whose product
    hierarchy has child relationships, and any deeper descendant implies a
    child of the root.
    """

    def test_empty_scene_is_a_part(self) -> None:
        self.assertFalse(step_artifact_cli._scene_has_assembly_structure(_scene()))

    def test_single_childless_root_is_a_part(self) -> None:
        self.assertFalse(step_artifact_cli._scene_has_assembly_structure(_scene(_node((1,)))))

    def test_root_with_children_is_an_assembly(self) -> None:
        leaf = _node((1, 1))
        root = _node((1,), children=[leaf])
        self.assertTrue(step_artifact_cli._scene_has_assembly_structure(_scene(root)))

    def test_root_with_grandchildren_is_an_assembly(self) -> None:
        grandchild = _node((1, 1, 1))
        child = _node((1, 1), children=[grandchild])
        root = _node((1,), children=[child])
        self.assertTrue(step_artifact_cli._scene_has_assembly_structure(_scene(root)))

    def test_multiple_roots_is_an_assembly(self) -> None:
        self.assertTrue(
            step_artifact_cli._scene_has_assembly_structure(_scene(_node((1,)), _node((2,))))
        )


if __name__ == "__main__":
    unittest.main()
