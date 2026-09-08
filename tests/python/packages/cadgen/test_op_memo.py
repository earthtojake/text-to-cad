"""Op-memoization invariants (design/incremental-generation.md, Phase 1).

The contract under test: memoized kernel ops return canonically reconstructed
shapes whose bytes are independent of cache state (cold or warm, first run or
tenth), never mutate or consume caller arguments, and fall through untouched
for anything they cannot key or store.
"""

from __future__ import annotations

import hashlib
import io
import os
import unittest

from cadgen._internal import op_memo


def _digest(shape) -> str:
    from OCP.BinTools import BinTools, BinTools_FormatVersion

    stream = io.BytesIO()
    BinTools.Write_s(shape.wrapped, stream, False, False,
                     BinTools_FormatVersion.BinTools_FormatVersion_CURRENT)
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _build_part():
    from build123d.topology import Solid

    box = Solid.make_box(20, 20, 8)
    return box.cut(Solid.make_cylinder(3, 12))


class OpMemoTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        op_memo.install()
        op_memo.clear()
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["CADGEN_OP_MEMO"] = "1"
        self._prev_store = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = self._tmp.name

    def tearDown(self):
        op_memo.clear()
        os.environ.pop("CADGEN_OP_MEMO", None)
        if self._prev_store is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._prev_store
        self._tmp.cleanup()

    def test_install_is_idempotent(self):
        from build123d.topology import Face

        self.assertFalse(op_memo.install())  # second call is a no-op
        self.assertTrue(getattr(Face.make_surface.__func__, "__op_memo__", False))

    def test_cache_state_independence(self):
        first = _build_part()
        stats_before = op_memo.stats()
        second = _build_part()
        stats_after = op_memo.stats()
        self.assertGreater(stats_after["hits"], stats_before["hits"])
        self.assertEqual(_digest(first), _digest(second))

    def test_hit_returns_independent_tshape(self):
        first = _build_part()
        second = _build_part()
        self.assertIsNot(first.wrapped.TShape(), second.wrapped.TShape())

    def test_boolean_results_match_the_unmemoized_kernel(self):
        """Input protection must not change what the boolean PRODUCES.

        ``SetNonDestructive(True)`` did: a ring with two bosses fused on
        tangentially (chained ``+``), bored, then halved is a valid solid when
        OCCT runs destructively and an invalid, self-intersecting one in
        non-destructive mode -- the w16 engine's rod caps, all sixteen, failed
        ``inspect validate`` this way while every in-process check passed.
        Operands are copied instead, so the kernel runs the algorithm it was
        validated with and the inputs still come back untouched."""
        from OCP.BRepCheck import BRepCheck_Analyzer
        from build123d import Align, Axis, Box, Cylinder, Location

        def cap():
            width = 19.0
            ring = Cylinder(41.0, width, align=(Align.CENTER,) * 3).rotate(Axis.Y, 90)
            bosses = [Cylinder(7.5, 46.0).moved(Location((0, sy * 34.0, -3.0))) for sy in (-1, 1)]
            body = ring + bosses[0] + bosses[1]
            body = body - Cylinder(30.0, width + 2, align=(Align.CENTER,) * 3).rotate(Axis.Y, 90)
            return body - Box(100, 200, 100, align=(Align.CENTER, Align.CENTER, Align.MIN))

        memoized = cap()
        self.assertTrue(BRepCheck_Analyzer(memoized.wrapped, True).IsValid(), "memoized boolean chain produced an invalid solid")
        os.environ["CADGEN_OP_MEMO"] = "0"
        try:
            bare = cap()
        finally:
            os.environ["CADGEN_OP_MEMO"] = "1"
        self.assertTrue(BRepCheck_Analyzer(bare.wrapped, True).IsValid())
        self.assertEqual(len(bare.solids()), len(memoized.solids()))

    def test_boolean_inputs_come_back_untouched(self):
        """The guarantee the flag used to provide, now by copying: a tool that
        is ALSO emitted as its own part serializes identically before and after
        it is used, so package bytes do not depend on cache state."""
        from build123d import Align, Axis, Cylinder

        tool = Cylinder(30.0, 21.0, align=(Align.CENTER,) * 3).rotate(Axis.Y, 90)
        before = _digest(tool)
        body = Cylinder(41.0, 19.0, align=(Align.CENTER,) * 3).rotate(Axis.Y, 90) - tool
        self.assertGreater(body.volume, 0)
        self.assertEqual(before, _digest(tool))

    def test_mutating_a_result_does_not_poison_the_cache(self):
        from OCP.BRepMesh import BRepMesh_IncrementalMesh

        first = _build_part()
        reference = _digest(first)
        # Mutate the first result the way the pipeline does (meshing).
        BRepMesh_IncrementalMesh(first.wrapped, 0.1, False, 0.5, True)
        BRepMesh_IncrementalMesh(first.wrapped, 0.5, False, 0.8, True)
        second = _build_part()
        self.assertEqual(_digest(second), reference)

    def test_orientation_is_part_of_the_key(self):
        from build123d.topology import Solid

        solid = Solid.make_box(5, 5, 5)
        forward = solid.wrapped
        key_fwd = op_memo._shape_key(solid)
        solid.wrapped = forward.Reversed()
        key_rev = op_memo._shape_key(solid)
        self.assertNotEqual(key_fwd, key_rev)

    def test_generator_arguments_pass_through_uncached(self):
        from build123d.topology import Solid

        box = Solid.make_box(20, 20, 8)
        edges = (e for e in box.edges()[:2])
        before = op_memo.stats()["unkeyable"]
        result = box.fillet(1.0, edges)
        self.assertEqual(op_memo.stats()["unkeyable"], before + 1)
        self.assertLess(result.volume, box.volume)

    def test_kill_switch(self):
        os.environ["CADGEN_OP_MEMO"] = "0"
        before = dict(op_memo.stats())
        part = _build_part()
        after = op_memo.stats()
        self.assertEqual(after["hits"], before["hits"])
        self.assertEqual(after["misses"], before["misses"])
        self.assertGreater(part.volume, 0)

    def test_disabled_and_enabled_geometry_match(self):
        os.environ["CADGEN_OP_MEMO"] = "0"
        plain = _build_part()
        os.environ["CADGEN_OP_MEMO"] = "1"
        memoized = _build_part()
        self.assertAlmostEqual(plain.volume, memoized.volume, places=9)

    def test_vector_and_axis_arguments_are_keyable(self):
        # Vector/Axis carry a `wrapped` (gp_Vec/gp_Ax1); they must normalize as
        # value types, not fall into the shape branch and become unkeyable —
        # builder-heavy models pass them to Solid.extrude/revolve constantly.
        from build123d import Axis, Location, Vector
        from build123d.topology import Face, Solid, Wire

        face = Face.make_surface(Wire.make_circle(6.0))
        before = op_memo.stats()["unkeyable"]
        first = Solid.extrude(face, Vector(0, 0, 4))
        off_axis = Face.make_surface(Wire.make_circle(2.0)).moved(Location((0, 10, 0)))
        Solid.revolve(off_axis, 180.0, Axis.X)
        self.assertEqual(op_memo.stats()["unkeyable"], before)
        hits_before = op_memo.stats()["hits"]
        second = Solid.extrude(face, Vector(0, 0, 4))
        self.assertGreater(op_memo.stats()["hits"], hits_before)
        self.assertEqual(_digest(first), _digest(second))

    def test_disk_tier_survives_memory_clear(self):
        first = _build_part()
        reference = _digest(first)
        op_memo.clear()  # simulate a fresh process: memory gone, disk kept
        before = op_memo.stats()["disk_hits"]
        second = _build_part()
        after = op_memo.stats()
        self.assertGreater(after["disk_hits"], before)
        self.assertEqual(_digest(second), reference)

    def test_disk_tier_kill_switch(self):
        os.environ["CADGEN_OP_MEMO_DISK"] = "0"
        try:
            _build_part()
            op_memo.clear()
            before = op_memo.stats()["disk_hits"]
            _build_part()
            self.assertEqual(op_memo.stats()["disk_hits"], before)
        finally:
            os.environ.pop("CADGEN_OP_MEMO_DISK", None)


def _memo_outcome(fn):
    """What a caller observes: the result's volume, or the exception class."""
    try:
        return ("ok", round(fn().volume, 6))
    except Exception as exc:  # noqa: BLE001 - the exception IS the observation
        return ("raised", type(exc).__name__)


class OpMemoAttributeParityTest(unittest.TestCase):
    """A memo hit must hand back the wrapper build123d would have built, not a
    bare one. build123d derives a result's Python-level attributes from the
    call (``_bool_op`` copies ``self``'s ``topo_parent``/label/color onto its
    result and builds anytree children for a multi-solid compound) and
    downstream code steers on them: ``bd.chamfer(edges, …)`` chamfers
    ``edges[0].topo_parent``. The juno shin was chamfered on a disk hit and not
    on a cold run because the disk tier reconstructed ``cls(topods)`` with
    ``topo_parent=None`` while a miss preserved the live attributes — the
    package hash changed with every run against a warm disk tier."""

    def setUp(self):
        import tempfile

        op_memo.install()
        op_memo.clear()
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["CADGEN_OP_MEMO"] = "1"
        self._prev_store = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = self._tmp.name

    def tearDown(self):
        op_memo.clear()
        os.environ.pop("CADGEN_OP_MEMO", None)
        if self._prev_store is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._prev_store
        self._tmp.cleanup()

    @staticmethod
    def _bored_plate():
        """A bool op whose result inherits topo_parent/label/color from self."""
        from build123d.topology import Part, Solid

        root = Part(children=[Solid.make_box(20, 20, 8)])
        plate = root.solids()[0]  # topo_parent is root (get_shape_list)
        plate.label = "plate"
        plate.color = (0.2, 0.4, 0.6, 1.0)
        return root, plate, plate.cut(Solid.make_cylinder(3, 12))

    def test_a_disk_hit_replays_attributes_against_the_current_call(self):
        first_root, first_plate, first = self._bored_plate()
        self.assertIs(first.topo_parent, first_root)
        op_memo.clear()  # a fresh process: memory gone, disk kept
        disk_hits = op_memo.stats()["disk_hits"]
        second_root, second_plate, second = self._bored_plate()
        self.assertGreater(op_memo.stats()["disk_hits"], disk_hits)
        self.assertIs(second.topo_parent, second_root, "topo_parent must be THIS call's root")
        self.assertEqual(second.label, "plate")
        self.assertEqual(tuple(second.color), tuple(first.color))
        self.assertIs(second._color, second_plate._color, "copied by reference, as copy_attributes_to does")

    def test_a_warm_hit_does_not_leak_the_recording_call_objects(self):
        first_root, _plate, first = self._bored_plate()
        hits = op_memo.stats()["hits"]
        second_root, _plate2, second = self._bored_plate()
        self.assertGreater(op_memo.stats()["hits"], hits)
        self.assertIs(second.topo_parent, second_root)
        self.assertIsNot(second.topo_parent, first_root, "a hit used to clone the recording result's dict")

    def test_children_are_rebuilt_onto_the_reconstruction(self):
        """No memoized op in build123d 0.11 returns a compound WITH anytree
        children (a split bool result has solids but no children), so this
        exercises the recipe directly: children map positionally onto the
        reconstruction's top-level sub-shapes, carry their attributes, and
        parent onto the reconstruction — never onto the recording result."""
        from build123d.geometry import Location
        from build123d.topology import Part, Solid
        from build123d.topology.shape_core import get_top_level_topods_shapes

        base = Solid.make_box(20, 20, 8)
        base.label = "base"
        left, right = Solid.make_box(5, 5, 5), Solid.make_box(5, 5, 5).moved(Location((10, 0, 0)))
        left.label, right.label = "left", "right"
        left.topo_parent = right.topo_parent = base  # as copy_attributes_to would leave them
        result = Part(children=[left, right])
        result.label = "pair"

        stored = op_memo._freeze_result(result, [base])
        thawed = op_memo._thaw_result(stored, [base])
        self.assertEqual(thawed.label, "pair")
        self.assertEqual([c.label for c in thawed.children], ["left", "right"])
        for child, top in zip(thawed.children, get_top_level_topods_shapes(thawed.wrapped)):
            self.assertTrue(child.wrapped.IsSame(top), "children wrap the reconstruction's own sub-shapes")
            self.assertIs(child.parent, thawed)
            self.assertIs(child.topo_parent, base)
        self.assertIsNot(thawed.children[0], left)
        self.assertEqual(_digest(thawed), _digest(result))

    def test_chamfer_steered_by_topo_parent_is_cache_state_independent(self):
        """The juno pattern: chamfer edges taken from a solid whose topo_parent
        is an unrelated root. Whatever build123d does with it un-memoized is
        what a cold miss AND a disk hit must do."""
        from build123d import chamfer
        from build123d.topology import Part, Solid

        def build():
            root = Part(children=[Solid.make_box(20, 20, 8)])
            core = root.solids()[0]
            core = core.cut(Solid.make_cylinder(3, 12)).solids()[0]
            edges = core.edges().filter_by(lambda e: e.length > 15)
            return chamfer(list(edges), 0.5)

        os.environ["CADGEN_OP_MEMO"] = "0"
        truth = _memo_outcome(build)
        os.environ["CADGEN_OP_MEMO"] = "1"
        self.assertEqual(_memo_outcome(build), truth, "cold miss differs from un-memoized")
        op_memo.clear()
        self.assertEqual(_memo_outcome(build), truth, "disk hit differs from un-memoized")
        self.assertEqual(_memo_outcome(build), truth, "warm hit differs from un-memoized")

    def test_a_result_with_inexpressible_attributes_is_not_cached(self):
        """An attribute reachable from no argument of the call cannot be replayed
        on a hit, so the result must not be stored (the op simply runs uncached)."""
        from build123d.topology import Solid

        result = Solid.make_box(20, 20, 8)
        result.topo_parent = Solid.make_box(1, 1, 1)
        with self.assertRaises(op_memo._Unkeyable):
            op_memo._freeze_result(result, [])
        # Reachable through an argument: stored, and replayed against THAT argument.
        holder = Solid.make_box(2, 2, 2)
        holder.topo_parent = result.topo_parent
        stored = op_memo._freeze_result(result, [holder])
        other = Solid.make_box(2, 2, 2)
        other.topo_parent = Solid.make_box(3, 3, 3)
        self.assertIs(op_memo._thaw_result(stored, [other]).topo_parent, other.topo_parent)



def _junction_fillets():
    """The sequential-fillet pattern that lost identity under the memo: hold
    the boss's junction edges, then re-find each one in the CURRENT solid
    before filleting it. Returns (fillets applied, result)."""
    from build123d import Box, Pos

    shape = Box(10, 10, 10).fuse(Pos(5, 0, 0) * Box(10, 6, 6))
    roots = [e for e in shape.edges() if 4 < e.length < 6.5]
    roots.sort(key=lambda e: tuple(round(v, 5) for v in e.center()))
    applied = 0
    for edge in roots:
        current = next((c for c in shape.edges() if edge.is_same(c)), None)
        if current is None:
            continue
        shape = shape.fillet(0.5, [current])
        applied += 1
    return applied, shape


class OpMemoSubShapeIdentityTest(unittest.TestCase):
    """Sub-shape identity survives an op under the memo (module docstring).

    Canonical reconstruction gives every untouched sub-shape a new TShape, so
    build123d's pointer identity (``is_same``/``==``/``__hash__``) found
    nothing after an op: of twelve junction edges the plain kernel filleted
    six and the memo one. Identity is geometric while the shims are
    installed, and off with the kill switch."""

    def setUp(self):
        import tempfile

        op_memo.install()
        op_memo.clear()
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["CADGEN_OP_MEMO"] = "1"
        os.environ["CADGEN_OP_MEMO_DISK"] = "0"
        self._prev_store = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = self._tmp.name

    def tearDown(self):
        op_memo.install()  # a test that uninstalled leaves the shims in place
        op_memo.clear()
        os.environ.pop("CADGEN_OP_MEMO", None)
        os.environ.pop("CADGEN_OP_MEMO_DISK", None)
        if self._prev_store is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._prev_store
        self._tmp.cleanup()

    @staticmethod
    def _bored():
        """A box with a bore, and one edge held from BEFORE the cut."""
        from build123d import Box, Cylinder, Pos

        box = Pos(3, 4, 5) * Box(20, 20, 8)
        held = box.edges().sort_by(lambda e: e.center().X)[0]
        return held, box.cut(Cylinder(3, 12))

    def test_sequential_fillets_match_the_unmemoized_kernel(self):
        os.environ["CADGEN_OP_MEMO"] = "0"
        plain_count, plain = _junction_fillets()
        os.environ["CADGEN_OP_MEMO"] = "1"
        cold_count, cold = _junction_fillets()
        warm_count, warm = _junction_fillets()
        self.assertEqual(plain_count, 6)
        self.assertEqual((cold_count, warm_count), (6, 6))
        self.assertEqual(len(cold.faces()), len(plain.faces()))
        self.assertAlmostEqual(cold.volume, plain.volume, places=9)
        # Cache purity: cold and warm are byte-identical. Memo-off bytes are
        # not compared: input protection re-expresses located sub-shapes, the
        # accepted versioned difference documented on _StoredShape.
        self.assertEqual(_digest(cold), _digest(warm))

    def test_identity_survives_an_op(self):
        held, bored = self._bored()
        matches = [e for e in bored.edges() if held.is_same(e)]
        self.assertEqual(len(matches), 1)
        self.assertIsNot(held.wrapped.TShape(), matches[0].wrapped.TShape())
        self.assertEqual(held, matches[0])
        self.assertIn(held, bored.edges())
        self.assertIn(held, set(bored.edges()))
        self.assertIs({matches[0]: "found"}[held], "found")
        self.assertIn(held.vertices()[0], set(bored.vertices()))

    def test_different_edges_stay_different(self):
        from build123d import Pos

        held, bored = self._bored()
        others = [e for e in bored.edges() if not held.is_same(e)]
        self.assertEqual(len(others), len(bored.edges()) - 1)
        self.assertNotEqual(held, others[0])
        self.assertFalse(held.is_same(others[0]))
        self.assertNotEqual(held, Pos(0, 0, 1) * held)  # same TShape, moved
        self.assertNotEqual(held, held.faces() or bored.faces()[0])  # other kind

    def test_kill_switch_restores_pointer_identity(self):
        os.environ["CADGEN_OP_MEMO"] = "0"
        held, bored = self._bored()
        # Without the memo the kernel keeps the untouched TShape, so pointer
        # identity holds on its own and the shims pass through to build123d.
        self.assertTrue(any(held.is_same(e) for e in bored.edges()))
        self.assertEqual(hash(held), hash(held.wrapped))

    def test_uninstall_restores_build123d(self):
        from build123d.topology import Mixin3D, Shape, Solid

        self.assertTrue(op_memo.uninstall())
        self.assertFalse(op_memo.uninstall())
        for attr in ("is_same", "__eq__", "__hash__"):
            self.assertFalse(getattr(getattr(Shape, attr), "__op_memo__", False), attr)
        self.assertFalse(getattr(Mixin3D.fillet, "__op_memo__", False))
        self.assertFalse(getattr(Solid.extrude.__func__, "__op_memo__", False))
        # Pointer identity again: a byte-identical twin on a new TShape is a
        # different edge to build123d, and the same one to the shims.
        from build123d.topology import Edge

        held, _bored = self._bored()
        twin = Edge(op_memo._downcast(op_memo._read_brep(op_memo._write_brep(held.wrapped))))
        self.assertFalse(held.is_same(twin))
        self.assertNotEqual(held, twin)
        self.assertTrue(op_memo.install())
        self.assertTrue(getattr(Shape.is_same, "__op_memo__", False))
        self.assertTrue(held.is_same(twin))
        self.assertEqual(held, twin)
        self.assertEqual(hash(held), hash(twin))
