"""build123d de-duplicates shapes through ``set()``, which orders by heap address.

``Shape.__hash__`` is ``hash(self.wrapped)`` and OCCT hashes a ``TopoDS_Shape``
from its ``TShape`` pointer, so every ``set()`` of shapes iterates in allocation
order. Where that order reaches geometry — ``Edge.make_line(*two_vertices)``
picks a direction from a two-element set, an intersection chain re-seeds from a
deduplicated list — identical source produces byte-different BREP, and cadgen's
component ids ARE hashes of that BREP. The component cache then misses on every
build for reasons that have nothing to do with the model.

``cadgen._internal.determinism`` keeps the de-duplication and drops only the
address-derived order. These tests pin both halves of it.
"""

from __future__ import annotations

import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")


class OrderedShapeSetTest(unittest.TestCase):
    """The stand-in must dedup like a set and order like a list."""

    def setUp(self) -> None:
        from cadgen._internal.determinism import OrderedShapeSet

        self.cls = OrderedShapeSet

    def test_keeps_first_occurrence_order(self) -> None:
        items = ["a", "b", "a", "c", "b"]
        self.assertEqual(list(self.cls(items)), ["a", "b", "c"])

    def test_membership_and_length_match_a_set(self) -> None:
        ordered = self.cls([1, 2, 2, 3])
        self.assertEqual(len(ordered), 3)
        self.assertIn(2, ordered)
        self.assertNotIn(9, ordered)
        self.assertTrue(bool(ordered))
        self.assertFalse(bool(self.cls([])))

    def test_operators_preserve_left_operand_order(self) -> None:
        left = self.cls(["c", "a", "b"])
        right = self.cls(["b", "c"])
        self.assertEqual(list(left & right), ["c", "b"])
        self.assertEqual(list(left - right), ["a"])
        self.assertEqual(list(left | self.cls(["d"])), ["c", "a", "b", "d"])

    def test_equality_is_set_equality(self) -> None:
        self.assertEqual(self.cls(["a", "b"]), self.cls(["b", "a"]))
        self.assertEqual(self.cls(["a", "b"]), {"a", "b"})
        self.assertNotEqual(self.cls(["a"]), self.cls(["a", "b"]))


class ShapeDedupOrderTest(unittest.TestCase):
    """With the shim installed, ``set(ShapeList)`` stops reordering."""

    @classmethod
    def setUpClass(cls) -> None:
        from cadgen._internal import determinism

        cls.installed = determinism.install()

    def test_install_is_idempotent(self) -> None:
        from cadgen._internal import determinism

        self.assertTrue(self.installed)
        self.assertTrue(determinism.install())

    def test_shapelist_dedup_keeps_source_order(self) -> None:
        from build123d.topology import Solid
        from build123d.topology.shape_core import ShapeList

        boxes = [Solid.make_box(1 + i, 1, 1) for i in range(24)]
        # The same shapes, duplicated, in a known order.
        source = ShapeList(boxes + boxes)
        from build123d.topology import shape_core

        deduped = list(shape_core.set(source))
        self.assertEqual(len(deduped), len(boxes))
        for expected, actual in zip(boxes, deduped):
            self.assertTrue(expected.is_same(actual))

    def test_a_real_set_would_have_reordered_them(self) -> None:
        """The control for the test above, so it cannot pass vacuously.

        A builtin set of 24 address-hashed shapes returning them in input order
        is a 1-in-24! event; observed across processes it returns a DIFFERENT
        order every time. If this assertion ever fails, ``Shape.__hash__`` has
        become content-derived upstream and the shim is obsolete — which is a
        thing to notice, not to skip past."""
        import builtins

        from build123d.topology import Solid
        from build123d.topology.shape_core import ShapeList

        boxes = [Solid.make_box(1 + i, 1, 1) for i in range(24)]
        naive = list(builtins.set(ShapeList(boxes)))
        self.assertNotEqual(
            [id(shape.wrapped) for shape in naive],
            [id(shape.wrapped) for shape in boxes],
            "a builtin set preserved input order — the fixture no longer "
            "exercises address-ordered de-duplication",
        )

    def test_non_shapelist_arguments_still_get_a_real_set(self) -> None:
        """The shadowed name must be inert for everything it was not written
        for — otherwise shadowing a builtin in someone else's module is a
        licence to break unrelated code."""
        from build123d.topology import shape_core

        self.assertIsInstance(shape_core.set(), set)
        self.assertIsInstance(shape_core.set([1, 2, 2]), set)
        self.assertEqual(shape_core.set([1, 2, 2]), {1, 2})
        self.assertIsInstance(shape_core.set({"a": 1}.keys()), set)

    def test_vertex_hash_is_coordinate_derived(self) -> None:
        """Equal vertices must hash equal (the set contract), and the hash must
        not vary between two separately-constructed but identical vertices —
        that is precisely what the address hash failed to give."""
        from build123d.topology.zero_d import Vertex

        first = Vertex(1.0, 2.0, 3.0)
        second = Vertex(1.0, 2.0, 3.0)
        self.assertEqual(hash(first), hash(second))
        self.assertNotEqual(hash(first), hash(Vertex(1.0, 2.0, 4.0)))

    def test_vertex_set_order_follows_coordinates_not_addresses(self) -> None:
        """The mechanism that covers the sites the ``set`` shadow cannot reach.

        ``build_common.py`` does ``ShapeList(set(vertex_list))`` but also
        ``isinstance(item, (list, tuple, filter, set))``, so shadowing ``set``
        there would break it. A coordinate-derived ``Vertex.__hash__`` makes
        those sets order by content instead — the same vertices, constructed
        again, iterate the same way. Measured across processes: 4 distinct
        orders before the shim, 1 after."""
        from build123d.topology.zero_d import Vertex

        def order(scale: float) -> list:
            verts = [Vertex(i * 1.5, i * -0.25, i % 7) for i in range(24)]
            # Touch unrelated allocations between runs so the two batches
            # cannot share an allocation pattern by accident.
            _ballast = [Vertex(scale * j, j, j) for j in range(50)]
            return [(round(v.X, 6), round(v.Y, 6), round(v.Z, 6)) for v in set(verts)]

        self.assertEqual(order(1.0), order(2.0))


class LiveVertexHashTest(unittest.TestCase):
    """Set membership follows live geometric equality, including native edits."""

    def setUp(self) -> None:
        import os

        from cadgen._internal import determinism, op_memo

        op_memo.install()
        determinism.install()
        self.env = mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def assert_same_bucket(self, first, second) -> None:
        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))
        self.assertEqual(len({first, second}), 1)
        self.assertEqual({first: "found"}[second], "found")

    def test_nearly_coincident_vertices_hash_at_equality_precision(self) -> None:
        from build123d import Vertex

        self.assert_same_bucket(Vertex(0.0000004, 0, 0), Vertex(0.00000045, 0, 0))
        self.assertNotEqual(Vertex(0.0000004, 0, 0), Vertex(0.0000006, 0, 0))

    def test_native_point_edit_ignores_stale_python_coordinates(self) -> None:
        from build123d import Vertex
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt

        vertex = Vertex(1, 2, 3)
        before = hash(vertex)
        BRep_Builder().UpdateVertex(vertex.wrapped, gp_Pnt(4, 2, 3), 1e-7)
        self.assertEqual(vertex.X, 1, "the fixture must retain stale Python coordinates")
        self.assertNotEqual(hash(vertex), before)
        self.assert_same_bucket(vertex, Vertex(4, 2, 3))

    def test_native_location_edit_uses_current_world_coordinates(self) -> None:
        from build123d import Location, Vertex

        vertex = Vertex(1, 2, 3)
        vertex.wrapped.Location(Location((3, 4, 5)).wrapped)
        self.assertEqual((vertex.X, vertex.Y, vertex.Z), (1, 2, 3))
        self.assert_same_bucket(vertex, Vertex(4, 6, 8))

    def test_vertex_and_generic_shape_wrappers_agree(self) -> None:
        from build123d import Shape, Vertex

        vertex = Vertex(1, 2, 3)
        self.assert_same_bucket(vertex, Shape(vertex.wrapped))
        self.assert_same_bucket(vertex, Shape(Vertex(1, 2, 3).wrapped))

    def test_disabled_memo_keeps_pointer_distinct_vertices_separate(self) -> None:
        import os

        from build123d import Vertex
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt

        with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0"}):
            first, second = Vertex(1, 2, 3), Vertex(1, 2, 3)
            self.assertNotEqual(first, second)
            self.assertEqual(hash(first), hash(second))
            self.assertEqual(len({first, second}), 2)
            alias = Vertex(first.wrapped)
            BRep_Builder().UpdateVertex(first.wrapped, gp_Pnt(4, 2, 3), 1e-7)
            self.assert_same_bucket(first, alias)

    def test_install_order_keeps_equal_vertices_in_one_bucket(self) -> None:
        from build123d import Shape, Vertex
        from cadgen._internal import determinism, op_memo

        original_vertex_hash = Vertex.__hash__
        try:
            for memo_first in (True, False):
                with self.subTest(memo_first=memo_first):
                    op_memo.uninstall()
                    Vertex.__hash__ = Shape.__hash__
                    with mock.patch.object(determinism, "_installed", False):
                        installers = (op_memo.install, determinism.install)
                        if not memo_first:
                            installers = installers[::-1]
                        for install in installers:
                            install()
                        self.assert_same_bucket(Vertex(0.0000004, 0, 0), Vertex(0.00000045, 0, 0))
        finally:
            op_memo.install()
            Vertex.__hash__ = original_vertex_hash


if __name__ == "__main__":
    unittest.main()
