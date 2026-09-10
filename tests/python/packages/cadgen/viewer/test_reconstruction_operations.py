"""Independent kernel shapes exercise loft and fillet replay, including failures."""

import copy
import unittest
from cadgen._internal.step_reconstruction import replay, compare, items, mass
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS


def circle(z, radius):
    return {
        "kind": "boundary",
        "edges": [
            {
                "reversed": False,
                "curve": {
                    "kind": "circle",
                    "origin": [0, 0, z],
                    "xdir": [1, 0, 0],
                    "ydir": [0, 1, 0],
                    "radius": radius,
                    "range": [0, 6.283185307179586],
                },
            }
        ],
    }


def loft_recipe():
    return {
        "schema": 1,
        "units": "mm",
        "output": "loft",
        "steps": [
            {
                "id": "a",
                "kind": "sketch",
                "label": "Bottom",
                "dependsOn": [],
                "profile": circle(0, 10),
            },
            {
                "id": "b",
                "kind": "sketch",
                "label": "Top",
                "dependsOn": [],
                "profile": circle(5, 6),
            },
            {
                "id": "loft",
                "kind": "loft",
                "label": "Loft",
                "dependsOn": ["a", "b"],
                "sketches": ["a", "b"],
            },
        ],
    }


def fillet_recipe():
    return {
        "schema": 1,
        "units": "mm",
        "output": "fillet",
        "steps": [
            {
                "id": "profile",
                "kind": "sketch",
                "label": "Rectangle",
                "dependsOn": [],
                "profile": {
                    "kind": "polygon",
                    "points": [[0, 0, 0], [8, 0, 0], [8, 5, 0], [0, 5, 0]],
                },
            },
            {
                "id": "base",
                "kind": "extrude",
                "label": "Extrude",
                "dependsOn": ["profile"],
                "sketch": "profile",
                "direction": [0, 0, 4],
            },
            {
                "id": "fillet",
                "kind": "fillet",
                "label": "Fillet",
                "dependsOn": ["base"],
                "input": "base",
                "radius": 1.3,
                "edges": "all",
            },
        ],
    }


class ReconstructionOperationTests(unittest.TestCase):
    def test_loft_matches_an_independent_cone_and_changed_section_fails(self):
        target = BRepPrimAPI_MakeCone(10, 6, 5).Shape()
        recipe = loft_recipe()
        result, states = replay(recipe)
        self.assertTrue(compare(target, result)["passed"])
        self.assertEqual(len(states), 3)
        self.assertTrue(all(s["shape"] is None for s in states[:2]))
        recipe["steps"][1]["profile"] = circle(5, 6.1)
        changed, _ = replay(recipe)
        self.assertFalse(compare(target, changed)["passed"])

    def test_fillet_preserves_unrounded_stock_and_matches_independent_box(self):
        box = BRepPrimAPI_MakeBox(8, 5, 4).Shape()
        operation = BRepFilletAPI_MakeFillet(box)
        for edge in items(box, TopAbs_EDGE):
            operation.Add(1.3, TopoDS.Edge_s(edge))
        operation.Build()
        result, states = replay(fillet_recipe())
        self.assertTrue(compare(operation.Shape(), result)["passed"])
        self.assertAlmostEqual(mass(states[1]["shape"]), 160)
        self.assertLess(mass(result), 160)
        changed = fillet_recipe()
        changed["steps"][-1]["radius"] = 1.2
        wrong, _ = replay(changed)
        self.assertFalse(compare(operation.Shape(), wrong)["passed"])

    def test_capped_fillet_selection_and_indexed_mesh_stay_bounded(self):
        from cadgen._internal.step_reconstruction import mesh

        recipe = fillet_recipe()
        recipe["steps"][-1].update(
            radius=0.4,
            edges={"axis": 2, "position": 4, "bounds": [0, 0, 4, 8, 5, 4], "count": 4},
        )
        result, _ = replay(recipe)
        self.assertLess(mass(result), 160)
        data = mesh(result)
        self.assertEqual(len(data["vertices"]), len(data["normals"]))
        self.assertEqual(len(data["indices"]) % 3, 0)
        self.assertLess(max(data["indices"]), len(data["vertices"]) // 3)
        self.assertLess(len(data["vertices"]), len(data["indices"]) * 3)
        recipe["steps"][-1]["edges"]["count"] = 8
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            replay(recipe)

    def test_cut_and_add_consume_solid_tools_with_actual_dependencies(self):
        from cadgen._internal.step_reconstruction import cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        recipe = fillet_recipe()
        recipe["steps"] = recipe["steps"][:2]
        recipe["steps"].extend(
            [
                {
                    "id": "circle",
                    "kind": "sketch",
                    "label": "Tool sketch",
                    "dependsOn": [],
                    "profile": circle(-1, 2),
                },
                {
                    "id": "tool",
                    "kind": "extrude",
                    "label": "Tool",
                    "dependsOn": ["circle"],
                    "sketch": "circle",
                    "direction": [0, 0, 6],
                },
                {
                    "id": "cut",
                    "kind": "cut",
                    "label": "Cut",
                    "dependsOn": ["base", "tool"],
                    "input": "base",
                    "tool": "tool",
                },
            ]
        )
        recipe["output"] = "cut"
        expected = cut(
            BRepPrimAPI_MakeBox(8, 5, 4).Shape(), BRepPrimAPI_MakeCylinder(2, 6).Shape()
        )
        result, _ = replay(recipe)
        self.assertTrue(compare(expected, result)["passed"])
        recipe["steps"][-1].update(kind="add")
        enlarged, _ = replay(recipe)
        self.assertGreater(mass(enlarged), 160)
        recipe["steps"][-1].update(tool="circle", dependsOn=["base", "circle"])
        with self.assertRaisesRegex(ValueError, "solid tool"):
            replay(recipe)

    def test_new_operations_require_real_dependencies_and_supported_selection(self):
        bad = []
        r = loft_recipe()
        r["steps"][-1]["dependsOn"] = ["a"]
        bad.append(r)
        r = loft_recipe()
        r["steps"][-1]["sketches"] = ["a"]
        r["steps"][-1]["dependsOn"] = ["a"]
        bad.append(r)
        r = fillet_recipe()
        r["steps"][-1]["input"] = "profile"
        r["steps"][-1]["dependsOn"] = ["profile"]
        bad.append(r)
        r = fillet_recipe()
        r["steps"][-1]["radius"] = -1
        bad.append(r)
        r = fillet_recipe()
        r["steps"][-1]["edges"] = [1]
        bad.append(r)
        for recipe in bad:
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                replay(copy.deepcopy(recipe))


if __name__ == "__main__":
    unittest.main()
