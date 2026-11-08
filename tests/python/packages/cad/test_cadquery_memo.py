"""The CadQuery memo's keying and replay, on a stand-in of CadQuery's shapes module (``cad.cadquery._memo``).

The memo patches whatever module it is given, so a module with CadQuery's class and method names over
build123d's shapes (the kernel these tests run) exercises the layer with no CadQuery: a call is keyed by
its operation, its parameters and the keys of the shapes it was given; a second identical call hits and
hands back a fresh wrapper on the first run's ``TopoDS_Shape``; a parameter changed misses and so does what
reads it; a shape no operation made is unkeyable and runs plain; a sub-shape of a result is keyed as its
root's; a result moved in place after it returned is kept as it was returned; entries the last runs did not
use are swept. The real CadQuery runs in the ``cadquery`` job.
"""

from __future__ import annotations

import types
import unittest

from tests.python.support.paths import add_sources

add_sources()

from cad.cadquery import _memo  # noqa: E402

PACKAGE = "cqlike"


def _module() -> types.ModuleType:
    """A stand-in for ``cadquery.occ_impl.shapes``: ``Shape`` (``wrapped``, ``forConstruction``, ``label``),
    ``Solid`` with the makers and operations the memo patches, over build123d's kernel calls."""
    import build123d as bd
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_ShapeEnum

    module = types.ModuleType(PACKAGE)

    class Shape:
        __module__ = PACKAGE

        def __init__(self, obj):
            self.wrapped = obj
            self.forConstruction = False
            self.label = ""

        def _bd(self):
            return bd.Shape.cast(self.wrapped)

        def cut(self, *others):
            return Shape((self._bd() - [other._bd() for other in others]).wrapped)

        def fuse(self, *others):
            return Shape((self._bd() + [other._bd() for other in others]).wrapped)

        def moved(self, loc):
            return type(self)(self.wrapped.Moved(loc.wrapped))

        def located(self, loc):
            return type(self)(self.wrapped.Located(loc.wrapped))

        def Edges(self):
            return [Shape(edge.wrapped) for edge in self._bd().edges()]

    class Solid(Shape):
        __module__ = PACKAGE

        @classmethod
        def makeBox(cls, length, width, height, pnt=None):
            return cls(bd.Box(length, width, height).wrapped)

        @classmethod
        def makeCylinder(cls, radius, height):
            return cls(bd.Cylinder(radius, height).wrapped)

    class Mixin3D:
        __module__ = PACKAGE

        def fillet(self, radius, edges):
            return type(self)(self._bd().fillet(radius, [bd.Edge(edge.wrapped) for edge in edges]).wrapped)

    class Location:
        __module__ = PACKAGE

        def __init__(self, x, y, z):
            self.wrapped = bd.Location((x, y, z)).wrapped
            self.values = (x, y, z)

        def toTuple(self):
            return (self.values, (0.0, 0.0, 0.0))

    module.Shape, module.Solid, module.Mixin3D, module.Location = Shape, Solid, Mixin3D, Location
    module.fuse = lambda first, *rest: first.fuse(*rest)
    return module


class MemoOnAStandIn(unittest.TestCase):
    def setUp(self) -> None:
        _memo.uninstall()
        self.module = _module()
        self.patched = _memo.install(self.module)
        self.addCleanup(_memo.uninstall)

    def _build(self, width: float = 40.0):
        made = self.module
        body = made.Solid.makeBox(width, 20, 6)
        hole = made.Solid.makeCylinder(4, 6)
        plate = body.cut(hole)
        peg = made.Solid.makeCylinder(2, 10).moved(made.Location(10, 0, 8))
        return plate.fuse(peg)

    def test_a_second_identical_run_hits_on_every_call_and_hands_back_the_first_run_s_kernel_objects(self) -> None:
        self.assertGreaterEqual(self.patched, 6)
        with _memo.run() as cold:
            first = self._build()
        self.assertEqual((cold.tally["hits"], cold.tally["misses"], cold.tally["unkeyable"]), (0, 6, 0), cold.tally)
        with _memo.run() as warm:
            second = self._build()
        self.assertEqual((warm.tally["hits"], warm.tally["misses"]), (6, 0), warm.tally)
        self.assertIsNot(first, second, "a new wrapper, as CadQuery would return")
        self.assertIsNot(first.wrapped, second.wrapped, "on an object of its own")
        self.assertEqual(first.wrapped.TShape(), second.wrapped.TShape(), "over the same TShape")
        with _memo.run() as edited:
            self._build(width=50)
        self.assertEqual((edited.tally["hits"], edited.tally["misses"]), (3, 3),
                         "the hole, the peg and its placement are kept; the box, the cut and the fuse ran")

    def test_a_shape_no_operation_made_is_unkeyable_and_a_sub_shape_is_its_root_s(self) -> None:
        import build123d as bd

        foreign = self.module.Shape(bd.Box(1, 1, 1).wrapped)
        with _memo.run() as run:
            self.module.Solid.makeBox(2, 2, 2).cut(foreign)
        self.assertEqual((run.tally["misses"], run.tally["unkeyable"]), (1, 1), run.tally)
        self.assertRegex(run.unkeyable[0], r"Shape\.cut: a Shape no operation of this process made")
        with _memo.run() as first:
            box = self.module.Solid.makeBox(10, 10, 10)
            self.module.Mixin3D.fillet(box, 1, box.Edges()[:1])  # an edge cast out of the result: the root's sub-shape
        self.assertEqual((first.tally["misses"], first.tally["unkeyable"]), (2, 0), first.unkeyable)
        with _memo.run() as second:
            box = self.module.Solid.makeBox(10, 10, 10)
            self.module.Mixin3D.fillet(box, 1, box.Edges()[:1])
        self.assertEqual((second.tally["hits"], second.tally["misses"]), (2, 0))

    def test_a_result_moved_in_place_after_it_returned_is_kept_as_returned(self) -> None:
        import build123d as bd

        with _memo.run():
            box = self.module.Solid.makeBox(3, 3, 3)
            box.wrapped.Move(bd.Location((0, 0, 7)).wrapped)  # CadQuery's move: the program's object changes
        with _memo.run() as run:
            again = self.module.Solid.makeBox(3, 3, 3)
        self.assertEqual(run.tally["hits"], 1)
        self.assertTrue(again.wrapped.Location().IsIdentity(), "the hit is the result as the operation returned it")

    def test_entries_the_last_runs_did_not_use_are_swept_and_hits_are_off_when_the_memo_is(self) -> None:
        import os
        from unittest import mock

        with _memo.run():
            self.module.Solid.makeBox(1, 2, 3)
        self.assertEqual(_memo.stats()["entries"], 1)
        for _ in range(_memo.RUNS_KEPT + 1):
            with _memo.run():
                self.module.Solid.makeBox(9, 9, 9)
        self.assertEqual(_memo.stats()["entries"], 1, "the first box's entry is gone, the repeated one kept")
        with mock.patch.dict(os.environ, {"CAD_ENGINE_MEMO": "0"}), _memo.run() as run:
            self.module.Solid.makeBox(9, 9, 9)
        self.assertEqual((run.tally["hits"], run.tally["misses"]), (0, 1))

    def test_a_call_outside_a_run_is_not_seen(self) -> None:
        before = _memo.stats()
        self.module.Solid.makeBox(1, 1, 1)
        self.assertEqual(_memo.stats()["misses"], before["misses"])


if __name__ == "__main__":
    unittest.main()
