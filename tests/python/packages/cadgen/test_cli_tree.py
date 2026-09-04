"""The build tree renders model transitions; it never invents any.

Driven with synthetic events so the assertions are about the rendering rules: one
JSON line per transition off a TTY, current children counted on the parent's line, a
finished subtree folded to one line, a finished model that never regresses, and a
stranger's root id ignored.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.cli_tree import BuildTree, build_tree  # noqa: E402
from cadgen.daemon import executors  # noqa: E402

ROBOT, ARM, GRIPPER, FINGER = "/m/robot.py", "/m/arm.py", "/m/gripper.py", "/m/finger.py"


def _tree(**kwargs) -> tuple[BuildTree, io.StringIO]:
    out = io.StringIO()
    return BuildTree(root_id="r", stream=out, **kwargs), out


def _lines(out: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


class JsonLines(unittest.TestCase):
    def test_one_line_per_transition_with_parent_phase_progress_and_elapsed(self):
        tree, out = _tree()
        tree.handle({"model": ROBOT, "state": "building", "phase": "generate"})
        tree.handle({"model": ARM, "state": "submitted", "parent": ROBOT})
        tree.handle({"model": ARM, "state": "building", "phase": "Meshing", "done": 3, "total": 7})
        tree.handle({"model": ARM, "state": "building", "phase": "Meshing", "done": 3, "total": 7})  # no change
        tree.handle({"model": ARM, "state": "done", "elapsed": 1.5})
        tree.handle({"model": ROBOT, "state": "done", "elapsed": 4.0, "stale": "arm changed"})
        tree.close()
        lines = _lines(out)
        self.assertEqual([l["state"] for l in lines], ["building", "submitted", "building", "done", "done"])
        self.assertEqual(lines[1]["parent"], ROBOT)
        self.assertEqual(lines[2]["progress"], [3, 7])
        self.assertEqual(lines[2]["phase"], "Meshing")
        self.assertEqual(lines[3]["elapsed"], 1.5)
        self.assertEqual(lines[4]["stale"], "arm changed")
        self.assertIsNone(lines[1]["elapsed"], "a submitted model has no elapsed time yet")

    def test_a_current_child_is_one_line(self):
        tree, out = _tree()
        tree.handle({"model": ROBOT, "state": "building"})
        tree.handle({"model": ARM, "state": "current", "parent": ROBOT})
        tree.close()
        line = _lines(out)[1]
        self.assertEqual((line["model"], line["parent"], line["state"]), (ARM, ROBOT, "current"))
        self.assertIsNone(line["phase"])
        self.assertIsNone(line["progress"])

    def test_a_finished_model_never_regresses(self):
        tree, out = _tree()
        tree.handle({"model": ARM, "state": "done", "elapsed": 1.0})
        tree.handle({"model": ARM, "state": "current"})  # a diamond's second build found it current
        tree.handle({"model": ARM, "state": "building", "phase": "late"})
        tree.handle({"model": ARM, "state": "submitted"})
        tree.close()
        self.assertEqual([l["state"] for l in _lines(out)], ["done"])

    def test_queued_sits_between_submitted_and_building(self):
        tree, out = _tree()
        tree.handle({"model": ARM, "state": "submitted", "parent": ROBOT})
        tree.handle({"model": ARM, "state": "queued"})
        self.assertIn("queued", tree._render()[1])
        tree.handle({"model": ARM, "state": "building", "phase": "generate"})
        tree.handle({"model": ARM, "state": "done", "elapsed": 0.2})
        tree.handle({"model": ARM, "state": "queued"})  # late; a finished model never regresses
        tree.close()
        self.assertEqual([l["state"] for l in _lines(out)], ["submitted", "queued", "building", "done"])

    def test_a_failure_carries_the_exit_code(self):
        tree, out = _tree()
        tree.handle({"model": ARM, "state": "building"})
        tree.handle({"model": ARM, "state": "failed", "exit": 3})
        tree.close()
        self.assertEqual(_lines(out)[-1]["state"], "failed")
        self.assertEqual(_lines(out)[-1]["exit"], 3)

    def test_events_from_another_root_are_ignored(self):
        tree, out = _tree()
        tree.handle({"model": ARM, "state": "building", "root": "someone-else"})
        tree.handle({"model": ARM, "state": "building", "root": "r"})
        tree.close()
        self.assertEqual(len(_lines(out)), 1)

    def test_malformed_events_are_dropped(self):
        tree, out = _tree()
        tree.handle({"state": "building"})
        tree.handle({"model": ARM})
        tree.handle("nonsense")  # type: ignore[arg-type]
        tree.close()
        self.assertEqual(_lines(out), [])


class TreeRendering(unittest.TestCase):
    def _populated(self) -> BuildTree:
        tree, _ = _tree()
        for event in (
            {"model": ROBOT, "state": "building", "phase": "components", "done": 41, "total": 57},
            {"model": ARM, "state": "current", "parent": ROBOT},
            {"model": GRIPPER, "state": "submitted", "parent": ROBOT},
            {"model": GRIPPER, "state": "building", "phase": "generate"},
            {"model": FINGER, "state": "submitted", "parent": GRIPPER},
        ):
            tree.handle(event)
        return tree

    def test_work_is_drawn_and_current_children_are_counted_on_the_parent(self):
        lines = self._populated()._render()
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("robot", lines[0])
        self.assertIn("building · components 41/57", lines[0])
        self.assertIn("(1 current)", lines[0])
        self.assertNotIn("arm", "\n".join(lines), "a current leaf got its own line")
        self.assertIn("gripper", lines[1])
        self.assertIn("building · generate", lines[1])
        self.assertIn("finger", lines[2])
        self.assertIn("submitted", lines[2])

    def test_a_finished_subtree_folds_to_one_line(self):
        tree = self._populated()
        tree.handle({"model": FINGER, "state": "done", "elapsed": 0.5})
        tree.handle({"model": GRIPPER, "state": "done", "elapsed": 1.8})
        lines = tree._render()
        self.assertEqual(len(lines), 2, lines)
        self.assertIn("✓ 1.8s (1 built)", lines[1])
        tree.handle({"model": ROBOT, "state": "done", "elapsed": 4.1})
        lines = tree._render()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("✓ 4.1s (2 built, 1 current)", lines[0])

    def test_the_already_stale_notice_rides_on_the_done_line(self):
        tree, _ = _tree()
        tree.handle({"model": ROBOT, "state": "done", "elapsed": 4.1, "stale": "finger changed"})
        self.assertIn("✓ 4.1s — already stale: finger changed; rerun", tree._render()[0])

    def test_a_child_reported_before_its_parent_is_hung_under_it_once_known(self):
        tree, _ = _tree()
        tree.handle({"model": FINGER, "state": "building"})
        tree.handle({"model": FINGER, "state": "submitted", "parent": GRIPPER})
        lines = tree._render()
        self.assertIn("gripper", lines[0])
        self.assertIn("finger", lines[1])


class ProcessWiring(unittest.TestCase):
    def setUp(self):
        self.addCleanup(executors.set_event_sink, None)
        self.addCleanup(os.environ.pop, "CADGEN_ROOT_ID", None)

    def test_the_root_mints_an_id_installs_the_sink_and_clears_both(self):
        os.environ.pop("CADGEN_ROOT_ID", None)
        out = io.StringIO()
        with build_tree(json_lines=True, stream=out) as tree:
            self.assertIsNotNone(tree)
            self.assertTrue(executors.sink_installed())
            root = os.environ["CADGEN_ROOT_ID"]
            executors.emit_event(executors.model_event("/m/a.py", "building"))
        self.assertFalse(executors.sink_installed())
        self.assertNotIn("CADGEN_ROOT_ID", os.environ)
        line = _lines(out)[0]
        self.assertEqual(line["model"], "/m/a.py")
        self.assertEqual(tree._root_id, root)

    def test_a_worker_with_a_sink_already_installed_gets_no_tree(self):
        executors.set_event_sink(lambda event: None)
        with build_tree(json_lines=True) as tree:
            self.assertIsNone(tree)
        self.assertTrue(executors.sink_installed(), "the worker's sink was replaced")

    def test_a_transient_worker_gets_no_tree(self):
        with mock.patch.dict(os.environ, {"CADGEN_EVENTS": "1"}):
            with build_tree(json_lines=True) as tree:
                self.assertIsNone(tree)

    def test_emit_event_tags_the_root_id(self):
        seen = []
        executors.set_event_sink(seen.append)
        with mock.patch.dict(os.environ, {"CADGEN_ROOT_ID": "abc"}):
            executors.emit_event({"model": "/m/a.py", "state": "building"})
        self.assertEqual(seen, [{"model": "/m/a.py", "state": "building", "root": "abc"}])


if __name__ == "__main__":
    unittest.main()
