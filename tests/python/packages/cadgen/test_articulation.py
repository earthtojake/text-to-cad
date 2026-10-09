"""The articulation: what cadgen resolves a STEP's kinematics into, for a page to play.

Every fact a player could otherwise have decided is minted here -- the control ids and their
limits, the joint rows a coupling adds a term to, which occurrences a joint carries (a nested
end goes to the deepest joint), what a drag writes, the named poses and the opening -- and the
reference evaluator at the bottom of the module says where a pose puts a joint, in closed form.
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from cadgen.articulation import (
    ARTICULATION_SCHEMA_VERSION,
    articulation_control_values,
    joint_matrices,
    joint_values,
    row_value,
    step_articulation,
)

REPO = Path(__file__).resolve().parents[4]
BROWSER_FIXTURE = REPO / "packages/ui/src/renderers/step/__fixtures__/step"


def mate(name, kind, parent, child, *, origin=(0, 0, 0), direction=(0, 0, 1), limits=None, parent_id=None, child_id=None):
    entry = {"name": name, "kind": kind, "parent": f"#{parent}", "child": f"#{child}",
             "parentId": parent_id or parent, "childId": child_id or child}
    if kind != "fastened":
        entry["axis"] = {"origin": list(origin), "dir": list(direction)}
        entry["limits"] = limits if isinstance(limits, dict) else {"value": list(limits or (0, 90))}
    return entry


def leaf(node_id, name=None):
    return {"id": node_id, "name": name or node_id, "children": []}


def group(node_id, *children, name=None):
    return {"id": node_id, "name": name or node_id, "children": list(children)}


def descriptor(root, *leaves):
    """A flattened tree: the leaves (with the names the tree gives them) and the instance tree."""
    names = {}

    def visit(node):
        if not node["children"]:
            names[node["id"]] = node["name"]
        for child in node["children"]:
            visit(child)

    visit(root)
    return {"occurrences": [{"id": item, "name": names.get(item, item), "component": "c"} for item in leaves],
            "assembly": {"root": root}}


ARM = descriptor(group("o1", leaf("o1.1", "base"), leaf("o1.2", "upper"), leaf("o1.3", "forearm"), leaf("o1.4", "carriage"),
                       leaf("o1.5", "pin")),
                 "o1.1", "o1.2", "o1.3", "o1.4", "o1.5")


def point_through(matrix, point):
    x, y, z = point
    return [round(sum(matrix[i][j] * v for j, v in enumerate((x, y, z, 1.0))), 6) + 0.0 for i in range(3)]


class StepArticulation(unittest.TestCase):
    def test_controls_are_the_dof_ids_with_their_declared_limits_and_rest_values(self):
        block = {"mates": [
            mate("elbow", "revolute", "o1.1", "o1.2", limits=(0, 150)),
            mate("extend", "slider", "o1.2", "o1.3", direction=(1, 0, 0), limits=(0, 80)),
            mate("lead", "cylindrical", "o1.1", "o1.4", limits={"turn": [0, 3600], "travel": [0, 40]}),
            mate("pin", "fastened", "o1.2", "o1.5"),
        ], "couplings": [{"name": "curl", "gears": {"elbow": 90, "extend": 10}, "limits": [0, 1]}]}
        articulation = step_articulation(ARM, block)
        self.assertEqual(articulation["schemaVersion"], ARTICULATION_SCHEMA_VERSION)
        self.assertEqual(articulation["controls"], [
            {"id": "elbow", "label": "elbow", "unit": "deg", "min": 0.0, "max": 150.0, "default": 0.0},
            {"id": "extend", "label": "extend", "unit": "mm", "min": 0.0, "max": 80.0, "default": 0.0},
            {"id": "lead.turn", "label": "lead.turn", "unit": "deg", "min": 0.0, "max": 3600.0, "default": 0.0},
            {"id": "lead.travel", "label": "lead.travel", "unit": "mm", "min": 0.0, "max": 40.0, "default": 0.0},
            {"id": "curl", "label": "curl", "unit": "", "min": 0.0, "max": 1.0, "default": 0.0},
        ])
        self.assertEqual(articulation["opening"], {"elbow": 0.0, "extend": 0.0, "lead.turn": 0.0, "lead.travel": 0.0, "curl": 0.0})
        # Joints parents first, each row over its own control plus the coupling's term.
        joints = {joint["id"]: joint for joint in articulation["joints"]}
        self.assertEqual([joint["id"] for joint in articulation["joints"]], ["elbow", "extend", "lead", "pin"])
        self.assertEqual(joints["elbow"]["turn"], {"bias": 0.0, "terms": [["elbow", 1.0], ["curl", 90.0]]})
        self.assertNotIn("travel", joints["elbow"])
        self.assertEqual(joints["extend"], {"id": "extend", "parent": "elbow", "kind": "slider", "origin": [0.0, 0.0, 0.0],
                                            "axis": [1.0, 0.0, 0.0], "travel": {"bias": 0.0, "terms": [["extend", 1.0], ["curl", 10.0]]}})
        self.assertEqual(joints["lead"]["turn"], {"bias": 0.0, "terms": [["lead.turn", 1.0]]})
        self.assertEqual(joints["lead"]["travel"], {"bias": 0.0, "terms": [["lead.travel", 1.0]]})
        self.assertEqual(joints["pin"], {"id": "pin", "parent": "elbow", "kind": "fixed"})
        # A handle per movable row: a member exactly one coupling gears writes through it.
        self.assertEqual([(h["id"], h["control"], h["weight"], h["unit"]) for h in articulation["handles"]], [
            ("elbow", "curl", 90.0, "deg"), ("extend", "curl", 10.0, "mm"),
            ("lead.turn", "lead.turn", 1.0, "deg"), ("lead.travel", "lead.travel", 1.0, "mm")])

    def test_a_member_two_couplings_gear_keeps_its_own_handle(self):
        block = {"mates": [mate("elbow", "revolute", "o1.1", "o1.2", limits=(0, 150))],
                 "couplings": [{"name": "curl", "gears": {"elbow": 90}, "limits": [0, 1]},
                               {"name": "fold", "gears": {"elbow": 45}, "limits": [0, 1]}]}
        (handle,) = step_articulation(ARM, block)["handles"]
        self.assertEqual((handle["control"], handle["weight"]), ("elbow", 1.0))

    def test_carries_are_the_leaves_of_each_end_and_a_nested_end_goes_to_the_deepest_joint(self):
        # A servo GROUP fastened to the frame, whose horn (inside the group) is fastened to the jaw
        # beside it: the horn rides the jaw once, never the group's motion on top.
        gripper = descriptor(
            group("o1", leaf("o1.0", "base"), leaf("o1.1", "frame"), group("o1.2", leaf("o1.2.1"), leaf("o1.2.2"), name="servo"),
                  leaf("o1.3", "jaw")),
            "o1.0", "o1.1", "o1.2.1", "o1.2.2", "o1.3")
        block = {"mates": [
            mate("wrist", "revolute", "o1.0", "o1.1", limits=(-90, 90)),
            mate("frame__servo", "fastened", "o1.1", "o1.2"),
            mate("jaw", "revolute", "o1.1", "o1.3", origin=(10, 0, 0), direction=(0, 1, 0), limits=(0, 90)),
            mate("jaw__horn", "fastened", "o1.3", "o1.2.2"),
        ]}
        self.assertEqual(step_articulation(gripper, block)["carries"], {
            "wrist": ["o1.1"], "frame__servo": ["o1.2.1"], "jaw": ["o1.3"], "jaw__horn": ["o1.2.2"]})

    def test_an_end_named_by_label_alone_resolves_to_the_occurrences_of_that_name(self):
        block = {"mates": [{"name": "swing", "kind": "revolute", "parent": "#base", "child": "#forearm",
                            "axis": {"origin": [0, 0, 0], "dir": [0, 0, 1]}, "limits": {"value": [0, 90]}}]}
        self.assertEqual(step_articulation(ARM, block)["carries"], {"swing": ["o1.3"]})

    def test_no_mates_is_nothing_to_pose_and_an_unreadable_block_is_refused(self):
        self.assertIsNone(step_articulation(ARM, None))
        self.assertIsNone(step_articulation(ARM, {}))
        self.assertIsNone(step_articulation(ARM, {"mates": []}))
        with self.assertRaisesRegex(ValueError, "unknown kind"):
            step_articulation(ARM, {"mates": [mate("x", "twist", "o1.1", "o1.2")]})
        with self.assertRaisesRegex(ValueError, "not resolved to numbers"):
            step_articulation(ARM, {"mates": [{"name": "x", "kind": "revolute", "parent": "#a", "child": "#b",
                                               "axis": {"ref": "#b.f1"}, "limits": {"value": [0, 1]}}]})

    def test_poses_and_a_request_resolve_to_a_full_control_vector(self):
        block = {"mates": [mate("elbow", "revolute", "o1.1", "o1.2", limits=(0, 150)),
                           mate("extend", "slider", "o1.2", "o1.3", limits=(0, 80))],
                 "poses": {"open": {"elbow": 40}}}
        articulation = step_articulation(ARM, block)
        self.assertEqual(articulation["poses"], {"open": {"elbow": 40.0}})
        self.assertEqual(articulation_control_values(articulation, None), {"elbow": 0.0, "extend": 0.0})
        self.assertEqual(articulation_control_values(articulation, "open"), {"elbow": 40.0, "extend": 0.0})
        self.assertEqual(articulation_control_values(articulation, {"extend": 5}), {"elbow": 0.0, "extend": 5.0})
        with self.assertRaises(KeyError):
            articulation_control_values(articulation, "shut")
        with self.assertRaises(KeyError):
            articulation_control_values(articulation, {"stray": 1})


class ReferenceEvaluator(unittest.TestCase):
    def test_a_revolute_at_90_degrees_turns_its_child_about_its_own_axis(self):
        block = {"mates": [mate("elbow", "revolute", "o1.1", "o1.2", origin=(10, 0, 0), limits=(0, 150))]}
        articulation = step_articulation(ARM, block)
        delta = joint_matrices(articulation, {"elbow": 90})["elbow"]
        self.assertEqual(point_through(delta, (10, 0, 0)), [10.0, 0.0, 0.0])
        self.assertEqual(point_through(delta, (11, 0, 0)), [10.0, 1.0, 0.0])

    def test_a_slider_travels_along_its_axis_and_a_cylindrical_joint_does_both(self):
        block = {"mates": [mate("extend", "slider", "o1.1", "o1.2", direction=(1, 0, 0), limits=(0, 80)),
                           mate("lead", "cylindrical", "o1.1", "o1.3", limits={"turn": [0, 360], "travel": [0, 40]})]}
        articulation = step_articulation(ARM, block)
        matrices = joint_matrices(articulation, {"extend": 5, "lead.turn": 90, "lead.travel": 3})
        self.assertEqual(point_through(matrices["extend"], (0, 0, 0)), [5.0, 0.0, 0.0])
        self.assertEqual(point_through(matrices["lead"], (1, 0, 0)), [0.0, 1.0, 3.0])

    def test_a_coupling_is_a_term_of_every_row_it_gears_and_a_chain_composes_through_its_parent(self):
        block = {"mates": [mate("elbow", "revolute", "o1.1", "o1.2", origin=(10, 0, 0), limits=(0, 150)),
                           mate("extend", "slider", "o1.2", "o1.3", direction=(1, 0, 0), limits=(0, 80)),
                           mate("pin", "fastened", "o1.2", "o1.5")],
                 "couplings": [{"name": "curl", "gears": {"elbow": 90, "extend": 10}, "limits": [0, 1]}]}
        articulation = step_articulation(ARM, block)
        self.assertEqual(articulation["carries"], {"elbow": ["o1.2"], "extend": ["o1.3"], "pin": ["o1.5"]})
        rows = joint_values(articulation, {"curl": 0.5, "elbow": 10})
        self.assertEqual(rows["elbow"], {"turn": 55.0, "travel": 0.0})
        self.assertEqual(rows["extend"], {"turn": 0.0, "travel": 5.0})
        matrices = joint_matrices(articulation, {"elbow": 90, "extend": 5})
        # The slider's +x travel, carried by the elbow's quarter turn, moves the carriage +y.
        self.assertEqual(point_through(matrices["extend"], (10, 0, 0)), [10.0, 5.0, 0.0])
        self.assertEqual(matrices["pin"], matrices["elbow"])


class CurveRows(unittest.TestCase):
    """A row's ``curve`` (a four-bar's crank, ``cadgen.robot_payload``), played as the page plays it:
    linearly between its keys, held beyond them, folded into its period, nested through its driver.
    The numbers are the JS player's (`packages/core/src/common/articulation.test.js`)."""

    CRANK = {"bias": 0.0, "terms": [], "curve": {"driver": {"bias": 0.0, "terms": [["rocker", 1.0]]},
                                                 "input": [-30, -10, 0, 10, 30], "output": [-40, -12, 0, 8, 20]}}

    def test_between_held_added_folded_and_nested(self):
        self.assertEqual(row_value(self.CRANK, {"rocker": 20}), 14.0, "halfway between the keys at 10 and 30")
        self.assertEqual(row_value(self.CRANK, {"rocker": 5}), 4.0)
        self.assertEqual(row_value(self.CRANK, {"rocker": 0}), 0.0, "a key is hit exactly")
        self.assertEqual([row_value(self.CRANK, {"rocker": -50}), row_value(self.CRANK, {"rocker": 50})], [-40.0, 20.0], "held at the ends")
        self.assertEqual(row_value({**self.CRANK, "bias": 1.5, "terms": [["trim", 2.0]]}, {"rocker": 20, "trim": 1}), 17.5, "added to the affine part")
        wiper = {"bias": 0.0, "terms": [], "curve": {"driver": {"bias": 0.0, "terms": [["spin", 1.0]]}, "input": [-180, 0, 180], "output": [0, 10, 0], "period": 360}}
        self.assertEqual([row_value(wiper, {"spin": value}) for value in (-90, 360, 540, -270)], [5.0, 10.0, 0.0, 5.0])
        second = {"bias": 0.0, "terms": [], "curve": {"driver": self.CRANK, "input": [-40, 0, 20], "output": [-4, 0, 2]}}
        self.assertAlmostEqual(row_value(second, {"rocker": 20}), 1.4, places=12, msg="the crank at 14 reads 1.4 on the next linkage")
        linkage = {"joints": [{"id": "rocker", "kind": "revolute", "turn": {"bias": 0.0, "terms": [["rocker", 1.0]]}},
                              {"id": "crank", "kind": "revolute", "turn": self.CRANK}]}
        self.assertEqual(joint_values(linkage, {"rocker": 20})["crank"], {"turn": 14.0, "travel": 0.0})
        self.assertEqual(row_value({"bias": 0.0, "terms": [], "curve": {"driver": {}, "input": [], "output": []}}, {}), 0.0, "no keys, no term")


class BrowserFixture(unittest.TestCase):
    """The browser suite serves the hinge fixture's articulation as the scanner would publish it:
    the committed file is what cadgen writes for the fixture's tree and sidecar today."""

    def test_the_committed_articulation_is_current(self):
        view = json.loads((BROWSER_FIXTURE / "assembly.json").read_text(encoding="utf-8"))
        sidecar = json.loads((BROWSER_FIXTURE / "hinge_block.step.json").read_text(encoding="utf-8"))
        committed = json.loads((BROWSER_FIXTURE / "hinge_block.articulation.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, step_articulation(view, sidecar["kinematics"]),
                         "regenerate hinge_block.articulation.json from cadgen.articulation.step_articulation")
        self.assertTrue(math.isclose(joint_matrices(committed, {"hinge": 90})["hinge"][0][1], -1.0))


if __name__ == "__main__":
    unittest.main()
