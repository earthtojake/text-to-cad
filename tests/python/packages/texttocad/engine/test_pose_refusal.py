"""A pose by a name no mechanism state has is refused naming the document's states and its
configuration sequences apart, and showing the joint-value form with a joint of its own."""

from __future__ import annotations

import unittest

from cad.engine import mechanism

# A hub on a revolute joint and a sliding door, with one state and one configuration sequence
# (the shape the document's kinematics are served in; only what ``resolve`` reads).
KINEMATICS = {
    "pairs": [{"label": "hub_rotation", "type": "revolute", "links": ["tower", "hub"], "limits": [[0, 360]]},
              {"label": "slide", "type": "prismatic", "links": ["tower", "door"], "limits": [[0, 40]]}],
    "asBuilt": {"hub_rotation": 0, "slide": 0},
    "configurations": {"parked": {"hub_rotation": 0}},
    "couplings": {},
    "motions": {"spin": {"duration": 4, "ease": "linear", "keys": []}},
}


class PoseRefusalTest(unittest.TestCase):
    def refused(self, pose: str) -> str:
        with self.assertRaises(mechanism.KinematicsError) as caught:
            mechanism.resolve(KINEMATICS, pose)
        return str(caught.exception)

    def test_a_sequence_s_name_says_it_is_a_sequence_and_shows_the_joint_value_form(self) -> None:
        self.assertEqual(self.refused("spin"),
                         "the document has no mechanism state 'spin' ('spin' is a configuration sequence, which "
                         "plays over time: a pose is a state or joint values); its states: parked; its sequences: "
                         "spin; its joints: hub_rotation, slide: pose one by value, --pose '{\"hub_rotation\": 90}'")

    def test_a_joint_s_name_shows_that_joint_at_a_value_its_range_allows(self) -> None:
        self.assertEqual(self.refused("slide"),
                         "the document has no mechanism state 'slide'; its states: parked; its sequences: spin; "
                         "it is a joint: pose it by value, --pose '{\"slide\": 20}'")

    def test_a_coupled_joint_is_never_the_example_its_coupling_is(self) -> None:
        # ja and jb are a gear pair's: posed alone they are refused, so the example names the coupling.
        geared = {"pairs": [{"label": "ja", "type": "revolute", "links": ["frame", "a"], "limits": [[-360, 360]]},
                            {"label": "jb", "type": "revolute", "links": ["frame", "b"], "limits": [[-360, 360]]}],
                  "asBuilt": {"ja": 0, "jb": 0}, "configurations": {}, "motions": {},
                  "couplings": {"drive": {"range": [-180.0, 180.0], "terms": [["ja", 0, 1.0], ["jb", 0, -2.0]]}}}
        refused = []
        for pose in ("spin", "jb"):
            with self.assertRaises(mechanism.KinematicsError) as caught:
                mechanism.resolve(geared, pose)
            refused.append(str(caught.exception))
        self.assertEqual(refused, [
            "the document has no mechanism state 'spin'; its states: none; its sequences: none; its joints: ja, jb; "
            "ja, jb moved by their coupling 'drive': pose a coupling by value, --pose '{\"drive\": 90}'",
            "the document has no mechanism state 'jb'; its states: none; its sequences: none; it is a joint its "
            "coupling 'drive' moves: pose the coupling by value, --pose '{\"drive\": 90}'"])
        self.assertEqual(mechanism.resolve(geared, {"drive": 90})[0]["jb"], (-180.0,), "the example poses")

    def test_a_state_still_poses(self) -> None:
        self.assertEqual(mechanism.resolve(KINEMATICS, "parked")[1], "parked")


if __name__ == "__main__":
    unittest.main()
