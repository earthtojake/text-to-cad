"""LazyCompound: what defers, what forces, and what a failed child says.

The five deferrals (``Pos/Rot/Location * child``, ``.moved()``, ``.label =``, ``.color =``)
must not touch geometry; every other build123d path reaches ``.wrapped`` and forces. The
job and the materialize are stubbed -- these are the promise's rules, not the store's.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import build123d as bd  # noqa: E402

from cadgen.store import lazy as lazy_mod  # noqa: E402
from cadgen.store.lazy import ChildBuildError, LazyCompound  # noqa: E402


class _Job:
    def __init__(self, code: int = 0, text: str = "") -> None:
        self.code, self.text, self.waited = code, text, 0

    def wait(self, timeout=None):
        self.waited += 1
        return self.code

    def output(self):
        return self.text


class _Frame:
    def __init__(self) -> None:
        self.pins: dict[Path, str] = {}

    def pin(self, child, tree):
        return self.pins.setdefault(child, tree)


def _box(label="child"):
    shape = bd.Box(4.0, 3.0, 2.0)
    compound = bd.Compound(children=[shape], label=label)
    return compound


class LazyFixture(unittest.TestCase):
    def setUp(self):
        self.model = Path("/models/child.py")
        self.frame = _Frame()
        self.materialized = []

        def materialize(tree, label):
            self.materialized.append((tree, label))
            return _box(label)

        patcher = mock.patch.object(lazy_mod, "_materialize_tree", materialize)
        patcher.start()
        self.addCleanup(patcher.stop)
        record = mock.patch.object(lazy_mod, "_read_record", lambda model: {"tree": "t-child"})
        record.start()
        self.addCleanup(record.stop)

    def lazy(self, job=None, label="child") -> LazyCompound:
        return LazyCompound(self.model, job, frame=self.frame, label=label)


class Deferral(LazyFixture):
    def test_the_five_deferrals_do_not_force(self):
        job = _Job()
        child = self.lazy(job)
        placed = bd.Pos(1, 2, 3) * child
        rotated = bd.Rot(0, 0, 90) * placed
        located = bd.Location((5, 0, 0)) * rotated
        moved = located.moved(bd.Location((0, 1, 0)))
        moved.label = "placed"
        moved.color = bd.Color("red")
        for promise in (child, placed, rotated, located, moved):
            self.assertIsInstance(promise, LazyCompound)
            self.assertTrue(promise.pending, "a deferred operation forced the child")
        self.assertEqual(job.waited, 0)
        self.assertEqual(self.materialized, [])

    def test_the_first_geometry_read_forces_once_and_applies_the_placement(self):
        job = _Job()
        moved = (bd.Pos(10, 0, 0) * self.lazy(job)).moved(bd.Location((0, 5, 0)))
        moved.label = "placed"
        centre = moved.bounding_box().center()
        self.assertFalse(moved.pending)
        self.assertEqual(job.waited, 1)
        self.assertEqual(self.materialized, [("t-child", "child")])
        self.assertAlmostEqual(centre.X, 10.0, places=6)
        self.assertAlmostEqual(centre.Y, 5.0, places=6)
        self.assertEqual(moved.label, "placed")
        moved.faces()  # a second read is a plain attribute
        self.assertEqual(job.waited, 1)
        self.assertEqual(len(self.materialized), 1)

    def test_compound_children_forces_at_the_end_and_keeps_the_link_tag(self):
        job = _Job()
        left = bd.Pos(-5, 0, 0) * self.lazy(job)
        right = bd.Pos(5, 0, 0) * self.lazy(job)
        assembly = bd.Compound(children=[left, right], label="pair")
        self.assertEqual(len(assembly.children), 2)
        self.assertFalse(left.pending)
        self.assertFalse(right.pending)
        from cadgen.store.materialize import TREE_TAG

        self.assertEqual(getattr(left, TREE_TAG, None), "t-child")
        self.assertEqual(getattr(right, TREE_TAG, None), "t-child")

    def test_a_current_child_has_no_job_and_forces_in_place(self):
        child = self.lazy(None)
        self.assertFalse(child.pending)
        self.assertEqual(child.tree_hash(), "t-child")
        child.solids()
        self.assertEqual(self.materialized, [("t-child", "child")])

    def test_the_first_tree_seen_is_pinned_for_the_build(self):
        first = self.lazy(None)
        self.assertEqual(first.tree_hash(), "t-child")
        with mock.patch.object(lazy_mod, "_read_record", lambda model: {"tree": "t-newer"}):
            second = self.lazy(None)
            self.assertEqual(second.tree_hash(), "t-child", "the pin did not isolate the build")

    def test_a_current_child_is_pinned_at_the_call_not_at_the_force(self):
        # The wrapper reads a current child's record when it is CALLED and hands the tree
        # in. The child is then rebuilt (a newer record appears) before the parent forces
        # it: the parent still composes the tree it pinned at the call.
        child = LazyCompound(self.model, None, frame=self.frame, label="child", tree="t-at-call")
        self.assertEqual(self.frame.pins[self.model], "t-at-call")
        with mock.patch.object(lazy_mod, "_read_record", lambda model: {"tree": "t-rebuilt"}):
            child.solids()  # forces
        self.assertEqual(self.materialized, [("t-at-call", "child")])
        self.assertEqual(child.tree_hash(), "t-at-call")

    def test_copy_forces(self):
        import copy

        job = _Job()
        child = self.lazy(job)
        copy.copy(child)
        self.assertEqual(job.waited, 1)


class Errors(LazyFixture):
    def test_a_failed_child_raises_at_the_forcing_site_with_call_site_and_output(self):
        job = _Job(code=1, text="Traceback (most recent call last):\n  boom\n")
        child = self.lazy(job)
        with self.assertRaises(ChildBuildError) as caught:
            child.faces()
        message = str(caught.exception)
        self.assertIn("child.py", message)
        self.assertIn("boom", message)
        self.assertIn(__file__.rsplit("/", 1)[-1], message, "the call site in the parent is missing")

    def test_a_child_with_no_record_after_a_successful_job_is_an_error(self):
        with mock.patch.object(lazy_mod, "_read_record", lambda model: None):
            with self.assertRaises(ChildBuildError):
                self.lazy(_Job()).tree_hash()


if __name__ == "__main__":
    unittest.main()
