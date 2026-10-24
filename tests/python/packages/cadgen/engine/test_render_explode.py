"""Explode in the stills is the viewer's: `engine/render/explode.py` ports the layout and the xbf
scene's records, and is held to the fixture the viewer's own scene made
(`packages/core/src/lib/xbf/__fixtures__/explode.json`, which `xbfExplode.test.js` holds the viewer
to), for the material fixture and the motorbike and for the layout's nested branch, to 1e-6. No node
runs. A part's box is every node, edge point and vertex of its mesh, and the records go in the
tree's order, numbers compared as numbers."""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import numpy as np

from cadgen.engine.mesh import Mesh
from cadgen.engine.render import explode

GOLDEN = Path(__file__).resolve().parents[5] / "packages" / "core" / "src" / "lib" / "xbf" / "__fixtures__" / "explode.json"
TOLERANCE = 1e-6


def _amount(key: str) -> float:
    return float(key)


class ExplodeParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    def assert_near(self, found: list[float], expected: list[float], label: str) -> None:
        self.assertEqual(len(found), len(expected), label)
        for at, (value, want) in enumerate(zip(found, expected)):
            self.assertLessEqual(abs(value - want), TOLERANCE, f"{label}[{at}]: {value} is not {want}")

    def test_a_document_explodes_where_the_viewer_explodes_it(self) -> None:
        self.assertEqual(sorted(self.golden["scenes"]), ["bench", "motorbike"])
        for name, scene in self.golden["scenes"].items():
            structure = {"tree": scene["tree"], "instances": scene["instances"]}
            matrices = [np.array(instance["matrix"], float).reshape(4, 4).T for instance in scene["instances"]]
            boxes = [None if box is None else (np.array(box[0]), np.array(box[1])) for box in scene["boxes"]]
            records, rest = explode.instance_records(structure, boxes, matrices)
            found = explode.layout(records, rest)
            self.assertEqual(found.levels, 1, f"{name}: an xbf scene hands no hierarchy, so every instance is a sibling")
            for key, expected in scene["offsets"].items():
                moved = explode.moved(found, _amount(key))
                for index, offset in enumerate(expected):
                    self.assert_near(list(moved.get(index, (0.0, 0.0, 0.0))), offset, f"{name} at {key}, instance {index}")
            self.assertEqual(len(explode.moved(found, 1.0)), len(scene["instances"]), name)

    def test_the_nested_branch_of_the_layout_is_the_viewer_s_too(self) -> None:
        nested = self.golden["nested"]
        records = [explode.Record(row["partId"], (tuple(row["min"]), tuple(row["max"])), row["partId"])
                   for row in nested["records"]]
        found = explode.layout(records, None, {row["partId"]: row["path"] for row in nested["records"]})
        self.assertEqual(found.levels, 3)
        for key, expected in nested["offsets"].items():
            moved = explode.moved(found, _amount(key))
            for part, offset in expected.items():
                self.assert_near(list(moved.get(part, (0.0, 0.0, 0.0))), offset, f"nested at {key}, {part}")

    def test_offsets_of_a_document_from_its_meshes(self) -> None:
        """What the scene asks of explode: a document's structure, each prototype's mesh and each
        instance's matrix, and the offsets by instance index (none at no amount)."""
        scene = self.golden["scenes"]["bench"]

        def corners(box: list[list[float]]) -> Mesh:
            positions = np.array(box, np.float32)
            empty = np.zeros((0, 3), np.float32)
            return Mesh(positions, positions.copy(), np.zeros(0, np.uint32), np.zeros((0, 3), np.uint32),
                        np.zeros((0, 4), np.uint32), empty, np.zeros((0, 4), np.float32))

        structure = {"tree": scene["tree"], "instances": scene["instances"]}
        matrices = [np.array(instance["matrix"], float).reshape(4, 4).T for instance in scene["instances"]]
        found = explode.offsets(structure, [corners(box) for box in scene["boxes"]], matrices, 1.0)
        self.assertEqual(sorted(found), list(range(len(scene["instances"]))))
        for index, offset in found.items():
            self.assert_near(offset.tolist(), scene["offsets"]["1"][index], f"instance {index}")
        self.assertEqual(explode.offsets(structure, [corners(box) for box in scene["boxes"]], matrices, 0.0), {})


class RecordsTest(unittest.TestCase):
    def test_a_part_s_box_is_every_node_edge_point_and_vertex(self) -> None:
        mesh = Mesh(np.array([[0, 0, 0], [1, 1, 1]], np.float32), np.zeros((2, 3), np.float32),
                    np.zeros(0, np.uint32), np.zeros((0, 3), np.uint32), np.zeros((0, 4), np.uint32),
                    np.array([[-2, 0.5, 0.5]], np.float32), np.array([[1, 0.5, 0.5, 3]], np.float32))
        low, high = explode.part_box(mesh)
        self.assertEqual((low.tolist(), high.tolist()), ([-2.0, 0.0, 0.0], [1.0, 1.0, 3.0]))
        empty = Mesh(*(np.zeros((0, width), dtype) for width, dtype in ((3, np.float32), (3, np.float32))),
                     np.zeros(0, np.uint32), np.zeros((0, 3), np.uint32), np.zeros((0, 4), np.uint32),
                     np.zeros((0, 3), np.float32), np.zeros((0, 4), np.float32))
        self.assertIsNone(explode.part_box(empty))

    def test_records_follow_the_tree_numbers_as_numbers_and_a_part_that_draws_nothing_stays(self) -> None:
        tree = {"children": [{"instance": index} for index in range(11)]}
        structure = {"tree": tree, "instances": [{"prototype": 0 if index != 3 else 1} for index in range(11)]}
        matrices = [np.eye(4) for _ in range(11)]
        for index, matrix in enumerate(matrices):
            matrix[0, 3] = 10.0 * index
        box = (np.zeros(3), np.ones(3))
        records, rest = explode.instance_records(structure, [box, None], matrices)
        self.assertEqual([record.part_id for record in records],
                         ["o1.1", "o1.2", "o1.3", "o1.5", "o1.6", "o1.7", "o1.8", "o1.9", "o1.10", "o1.11"])
        self.assertEqual([record.key for record in records], [0, 1, 2, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(rest, ((0.0, 0.0, 0.0), (101.0, 1.0, 1.0)))
        self.assertNotIn(3, explode.moved(explode.layout(records, rest), 1.0))

    def test_hypot_is_v8_s(self) -> None:
        # Node's Math.hypot of a vector where Python's own rounds one place apart (a third of
        # random vectors do): the layout's distances are V8's to the last bit.
        vector = (-70.2226554836252, -32.17071328878902, -93.17824467698962)
        self.assertEqual(explode.js_hypot(*vector), 121.03041525900144)
        self.assertNotEqual(math.hypot(*vector), 121.03041525900144)
        self.assertEqual(explode.js_hypot(0.0, 0.0, 0.0), 0.0)
        self.assertEqual(explode.js_hypot(3.0, -4.0), 5.0)
        self.assertTrue(math.isinf(explode.js_hypot(math.inf, math.nan)))


if __name__ == "__main__":
    unittest.main()
