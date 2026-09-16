"""LazyCompound: what defers, what forces, and what a failed child says.

The five deferrals (``Pos/Rot/Location * child``, ``.moved()``, ``.label =``, ``.color =``)
must not touch geometry; EVERY other read forces -- including the ones a Compound
answers from its node state rather than from its shape (``.children`` and the anytree
views over it), which once answered "empty" on a pending child. The job and the
materialize are stubbed -- these are the promise's rules, not the store's -- except for
the one cold end-to-end build at the bottom, which is the reported bug verbatim.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

import build123d as bd  # noqa: E402

from cadgen.store import lazy as lazy_mod  # noqa: E402
from cadgen.store.lazy import ChildBuildError, LazyCompound  # noqa: E402


class _Job:
    def __init__(self, code: int = 0, text: str = "") -> None:
        self.code, self.text, self.waited = code, text, 0
        self.result_ready = self.done = True
        self.tree = "t-child"

    def wait_result(self, timeout=None):
        self.waited += 1
        if self.code or not self.tree:
            raise RuntimeError(self.text or "no source result")
        return self.tree

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


def _pair(label="child"):
    """A child model's result with two parts and a color of its own."""
    left, right = bd.Box(4.0, 3.0, 2.0), bd.Pos(10, 0, 0) * bd.Box(1.0, 1.0, 1.0)
    compound = bd.Compound(children=[left, right], label=label)
    compound.color = bd.Color("blue")
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
        record = mock.patch("cadgen.store.trees.tree_complete", return_value=True)
        record.start()
        self.addCleanup(record.stop)

    def lazy(self, job=None, label="child") -> LazyCompound:
        return LazyCompound(self.model, job, frame=self.frame, label=label, tree="t-child" if job is None else None)


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
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("latest record read")):
            second = self.lazy(None)
            self.assertEqual(second.tree_hash(), "t-child", "the pin did not isolate the build")

    def test_a_current_child_is_pinned_at_the_call_not_at_the_force(self):
        # The wrapper reads a current child's record when it is CALLED and hands the tree
        # in. The child is then rebuilt (a newer record appears) before the parent forces
        # it: the parent still composes the tree it pinned at the call.
        child = LazyCompound(self.model, None, frame=self.frame, label="child", tree="t-at-call")
        self.assertEqual(self.frame.pins[str(self.model)], "t-at-call")
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("latest record read")):
            child.solids()  # forces
        self.assertEqual(self.materialized, [("t-at-call", "child")])
        self.assertEqual(child.tree_hash(), "t-at-call")

    def test_copy_forces(self):
        import copy

        job = _Job()
        child = self.lazy(job)
        copy.copy(child)
        self.assertEqual(job.waited, 1)

    def test_deleting_owned_face_metadata_forces_then_marks_the_pinned_child_changed(self):
        def materialize(tree, label):
            compound = _box(label)
            compound.cad_face_ordinal_colors = {1: (1.0, 0.0, 0.0, 1.0)}
            return compound

        with mock.patch.object(lazy_mod, "_materialize_tree", materialize):
            from cadgen.store.materialize import PARTNER_TAG

            face_child = self.lazy()
            del face_child.cad_face_ordinal_colors
            self.assertTrue(face_child._forced)
            self.assertNotIn("cad_face_ordinal_colors", face_child.__dict__)
            self.assertFalse(getattr(face_child, PARTNER_TAG).intact(face_child))

            with self.assertRaises(AttributeError):
                del face_child.cad_face_ordinal_colors


class NodeStateReads(LazyFixture):
    """The reads a Compound answers from its NODE state, not its shape.

    ``.children`` and the anytree views over it (``.descendants``, ``.leaves``,
    ``.is_leaf``, ``.height``, ``.size``) are served out of the node's child list,
    which forcing fills in. A promise that forced only on the shape answered every
    one of them with an empty tree until something else happened to touch geometry
    first -- a two-part child read as zero parts, at exit 0.
    """

    def setUp(self):
        super().setUp()

        def materialize(tree, label):
            self.materialized.append((tree, label))
            return _pair(label or "child")

        patcher = mock.patch.object(lazy_mod, "_materialize_tree", materialize)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_node_views_are_correct_with_no_prior_geometry_read(self):
        for read, expected in (
            (lambda c: len(c.children), 2),
            (lambda c: len(c.descendants), 2),
            (lambda c: len(c.leaves), 2),
            (lambda c: c.is_leaf, False),
            (lambda c: c.height, 1),
            (lambda c: c.size, 3),
        ):
            with self.subTest(read=read):
                child = self.lazy(_Job())
                self.assertEqual(expected, read(child))
                self.assertFalse(child.pending)

    def test_the_first_read_of_children_forces_exactly_once(self):
        job = _Job()
        child = self.lazy(job)
        self.assertEqual(2, len(child.children))
        self.assertEqual(2, len(child.children))
        child.bounding_box()
        self.assertEqual(1, job.waited)
        self.assertEqual([("t-child", "child")], self.materialized)

    def test_a_placed_promise_reads_its_children_placed(self):
        placed = bd.Pos(0, 0, 50) * self.lazy(_Job())
        self.assertEqual(2, len(placed.children))
        self.assertAlmostEqual(50.0, placed.bounding_box().center().Z, places=6)

    def test_label_and_color_reads_stay_deferred(self):
        # Reading `.label`/`.color` does NOT force: reference composition
        # (cadgen.store._references) reads both on a pending child to decide what to
        # record without waiting for geometry. A pending child answers with what the
        # parent authored, and learns the child's own on force.
        job = _Job()
        child = LazyCompound(self.model, job, frame=self.frame, label="", tree=None)
        self.assertEqual("", child.label)
        self.assertIsNone(child.color)
        self.assertTrue(child.pending)
        self.assertEqual(0, job.waited)
        self.assertEqual(2, len(child.children))
        self.assertEqual("child", child.label)
        self.assertEqual(tuple(bd.Color("blue")), tuple(child.color))


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

    def test_a_child_with_no_source_result_after_a_successful_job_is_an_error(self):
        job = _Job()
        job.tree = None
        with self.assertRaises(ChildBuildError):
            self.lazy(job).tree_hash()


CHILD = """
    from cadgen import step
    from cadgen import build123d as bd


    @step
    def pair():
        return bd.Compound(children=[bd.Box(1, 1, 1), bd.Pos(2, 0, 0) * bd.Box(1, 1, 1)])


    if __name__ == "__main__":
        pair()
"""

PARENT = """
    from cadgen import step
    from cadgen import build123d as bd

    from pair import pair


    @step
    def holder():
        child = pair()
        # Read the node views BEFORE anything touches geometry: this is the
        # reported bug, which printed `before=0 after=2`.
        before = (len(child.children), len(child.leaves), child.is_leaf)
        child.bounding_box()
        after = (len(child.children), len(child.leaves), child.is_leaf)
        print(f"BEFORE {before} AFTER {after}")
        return bd.Compound(children=[child])


    if __name__ == "__main__":
        holder()
"""


class ColdBuild(unittest.TestCase):
    """The reported bug end to end: a real uncached build, a real store, no stubs."""

    def test_a_deferred_child_reads_its_children_before_any_geometry_read(self) -> None:
        with temporary_directory(prefix="lazy-child-reads-") as tmp:
            root, cache = Path(tmp) / "proj", Path(tmp) / "store"
            root.mkdir(parents=True)
            for name, text in (("pair.py", CHILD), ("holder.py", PARENT)):
                (root / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                p for p in [str(REPO_ROOT / "packages" / "cadgen" / "src"), env.get("PYTHONPATH", "")] if p
            )
            env["CADGEN_CACHE_DIR"] = str(cache)
            env["CADGEN_DAEMON"] = "0"
            env.pop("CADGEN_DAEMON_CHILD", None)
            result = subprocess.run(
                [sys.executable, "holder.py", "--force"],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            line = next(
                (ln for ln in (result.stdout + result.stderr).splitlines() if ln.startswith("BEFORE ")),
                "",
            )
            self.assertEqual("BEFORE (2, 2, False) AFTER (2, 2, False)", line, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
