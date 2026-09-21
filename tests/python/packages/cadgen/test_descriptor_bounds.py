"""Exact descriptor bounds, native ownership and source-publication ordering."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import struct
import unittest
from unittest import mock
import weakref

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.store import build
from cadgen.store import _descriptor_bounds as bounds
from cadgen._internal import component_package as cp, op_memo
from cadgen.store.objects import object_path
from cadgen.store.trees import get_tree

mat = importlib.import_module("cadgen.store.materialize")


def ordinary_build(*args, **kwargs):
    """The complete-document path without either optional optimization."""
    with mock.patch.object(bounds, "try_bounds", return_value=None):
        return build.build_tree_through_step(*args, **kwargs)


class DescriptorFixture:
    def setUp(self):
        self.temp = generated_cad_directory(prefix="descriptor-bounds-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_COMPONENT_WORKERS": "1", "CADGEN_DAEMON": "0",
            "CADGEN_OP_MEMO": "1",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        op_memo.install()
        op_memo.clear()
        mat.reset_memo()
        self.addCleanup(op_memo.clear)
        self.addCleanup(mat.reset_memo)

    def child_tree(self, kind="box"):
        import build123d as bd
        if kind == "nurbs":
            from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
            shape = bd.Solid(BRepBuilderAPI_NurbsConvert(bd.Cylinder(3, 7).wrapped, True).Shape())
        elif kind == "hole":
            shape = bd.Box(12, 8, 3) - bd.Cylinder(2, 10)
        else:
            shape = bd.Box(3, 5, 7)
        shape.label = kind
        shape.color = (.6, .7, .8, 1.)
        shape.cad_face_ordinal_colors = {1: (1., .2, .1, 1.)}
        return build.build_tree_from_compound(shape, root_name=kind)[0]

    def parent(self, kind="box"):
        import build123d as bd
        if kind == "nested":
            inner = self.parent("hole")
            tree = build.build_tree_from_compound(inner, root_name="nested")[0]
            children = [mat.materialize(tree).moved(bd.Location((9, 3, 1), (0, 27, 13))),
                        mat.materialize(self.child_tree("nurbs")).moved(bd.Location((-4, 5, 2), (17, 0, 7)))]
            return bd.Compound(children=children, label="root")
        digest = self.child_tree(kind)
        children = []
        for xyz, angles, label in [((1, 2, 3), (17, 23, 31), "first"), ((15, 4, 2), (0, 0, 0), "same prototype")]:
            child = mat.materialize(digest).moved(bd.Location(xyz, angles)); child.label = label
            children.append(child)
        return bd.Compound(children=children, label="root").move(bd.Location((7, -9, 4), (11, 7, 3)))

    def result(self, function, shape, *, force=False, callback=None, name="same"):
        path = self.root / f"{name}.step"
        value = function(shape, path, root_name="root", force=force, on_preview=callback)
        return {"sourceHash": value[0], "sourceTree": value[1], "stepHash": value[3],
                "stepBytesHash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "documentTree": value[2]["documentTree"],
                "documentAppearance": value[2]["documentAppearance"],
                "documentOccurrenceMap": value[2]["documentOccurrenceMap"],
                "documentNodeMap": value[2]["documentNodeMap"]}

    def snapshot(self, shape):
        from cadgen.coordination import resolve
        walk = build._walk_compound(shape, root_name="root", progress=resolve(None))
        return bounds.capture_links(walk.draft_tree(root_name="root"))



class ProviderTests(DescriptorFixture, unittest.TestCase):
    def test_full_tree_step_parity_across_geometry_and_cache_states(self):
        for kind in ("box", "hole", "nurbs", "nested"):
            with self.subTest(kind=kind):
                shape = self.parent(kind)
                expected = self.result(ordinary_build, shape)
                for state in ("cold-key", "ram", "disk", "disabled", "force"):
                    if state == "disk": op_memo.clear(); mat.reset_memo()
                    with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0" if state == "disabled" else "1"}):
                        actual = self.result(build.build_tree_through_step, shape, force=state == "force")
                    self.assertEqual(expected, actual)

    def test_provider_is_used_only_for_complete_links_and_not_force(self):
        shape = self.parent()
        snapshot = self.snapshot(shape)
        with mock.patch.object(bounds, "try_bounds", wraps=bounds.try_bounds) as measured:
            self.result(build.build_tree_through_step, shape)
        self.assertEqual(measured.call_count, 1)
        self.assertIsNotNone(measured.call_args.args[0]["links"])
        with mock.patch.object(bounds, "try_bounds", side_effect=AssertionError("forced provider")):
            self.result(build.build_tree_through_step, shape, force=True)
        self.assertEqual(snapshot.bounds(), cp._bbox_from_shape(mat.materialize_descriptor(snapshot.descriptor())))

    def test_new_own_shape_keeps_whole_document_path(self):
        import build123d as bd
        shape = bd.Box(3, 5, 7)
        expected = self.result(ordinary_build, shape)
        with mock.patch.object(bounds, "capture_links", wraps=bounds.capture_links) as captured:
            actual = self.result(build.build_tree_through_step, shape)
        self.assertEqual(expected, actual)
        self.assertTrue(captured.called)

    def test_preparation_and_callback_order_are_unchanged(self):
        shape = self.parent()
        for function in (ordinary_build, build.build_tree_through_step):
            events = []
            original = mat.materialize_descriptor
            def materialize(*args, **kwargs):
                result = original(*args, **kwargs); events.append("prepared"); return result
            with mock.patch.object(mat, "materialize_descriptor", side_effect=materialize):
                self.result(function, shape, callback=lambda *_: events.append("preview"))
            self.assertLess(events.index("prepared"), events.index("preview"))

    def test_callback_failure_prevents_step_and_does_not_get_swallowed(self):
        shape = self.parent()
        for index, function in enumerate((ordinary_build, build.build_tree_through_step)):
            path = self.root / f"failure-{index}.step"
            def fail(*_): raise RuntimeError("child output failed")
            with self.assertRaisesRegex(RuntimeError, "child output failed"):
                function(shape, path, root_name="root", on_preview=fail)
            self.assertFalse(path.exists())

    def test_missing_corrupt_inputs_and_bad_value_miss_to_original(self):
        shape = self.parent()
        snapshot = self.snapshot(shape)
        expected = self.result(ordinary_build, shape)
        self.result(build.build_tree_through_step, shape)
        desc = snapshot.descriptor(); entry = next(iter(desc["components"].values()))
        path = object_path(entry["brep"]); data = path.read_bytes()
        try:
            path.write_bytes(b"wrong bytes")
            self.assertIsNone(bounds.try_bounds(build._walk_compound(shape, root_name="root", progress=build.resolve_progress(None)).draft_tree(root_name="root")))
            # Existing consumers still own valid native geometry, but a new
            # publication must not certify a hash-corrupt required closure.
            for function in (ordinary_build, build.build_tree_through_step):
                with self.assertRaisesRegex(RuntimeError, "disappeared before publication"):
                    self.result(function, shape)
        finally: path.write_bytes(data)
        for digest, payload in snapshot.objects:
            path = object_path(digest)
            try:
                path.unlink()
                with self.assertRaises(OSError): snapshot.verify()
            finally: path.write_bytes(payload)
        with mock.patch.object(bounds.Snapshot, "bounds", side_effect=bounds.Ineligible("bad value")):
            self.assertEqual(expected, self.result(build.build_tree_through_step, shape))

    def test_exact_key_preserves_sub_rounding_placements_and_no_mutable_result_alias(self):
        shape = self.parent(); snapshot = self.snapshot(shape)
        first = snapshot.bounds(); first["min"][0] = 999
        self.assertNotEqual(first, snapshot.bounds())
        desc = snapshot.descriptor(); desc["occurrences"][0]["transform"][3] += 1e-10
        self.assertNotEqual(desc, snapshot.descriptor())
        recorded = []
        def capture(op, args, compute): recorded.append(args); return compute()
        with mock.patch.object(op_memo, "memoized_value", side_effect=capture): snapshot.bounds()
        self.assertTrue(any(type(args[1]) is bytes and len(args[1]) == 128 for args in recorded))

    def test_size_thresholds_reject_synthetic_objects_without_native_work(self):
        data = b"0123456789"; digest = hashlib.sha256(data).hexdigest(); path = object_path(digest)
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.assertEqual(bounds._read(digest, 10), data)
        with self.assertRaises(bounds.Ineligible): bounds._read(digest, 9)
        with self.assertRaises(bounds.Ineligible): bounds._json_bytes({"name": "x" * 65537})
        with self.assertRaises(bounds.Ineligible): bounds._json_bytes({"items": [0] * 1025})
        snapshot = self.snapshot(self.parent())
        desc = snapshot.descriptor()
        desc["occurrences"] *= 33
        with self.assertRaises(bounds.Ineligible): bounds._ordered(desc)
        desc = snapshot.descriptor(); desc["components"].update({f"fake-{i}": {} for i in range(17)})
        with self.assertRaises(bounds.Ineligible): bounds._ordered(desc)
        draft = build._walk_compound(self.parent(), root_name="root", progress=build.resolve_progress(None)).draft_tree(root_name="root")
        for limit in ("MAX_TREE_BYTES", "MAX_BREP_BYTES"):
            with mock.patch.object(bounds, limit, 1), mock.patch.object(bounds.Snapshot, "bounds", side_effect=AssertionError("native work after admission denial")):
                self.assertIsNone(bounds.try_bounds(draft))

    def test_actual_overflowing_numeric_op_entry_falls_back(self):
        from cadgen.store.index import write_entry
        shape = self.parent(); snapshot = self.snapshot(shape)
        expected = self.result(ordinary_build, shape)
        cid, transform = snapshot.occurrences[0]
        args = (dict(snapshot.component_breps)[cid], struct.pack("<16d", *transform), bounds._native_identity())
        key = op_memo._op_index_key(op_memo._build_key(bounds.OP, args, {}))
        write_entry("op", key, {"value": [10 ** 400] * 6})
        op_memo.clear()
        self.assertEqual(expected, self.result(build.build_tree_through_step, shape))

    def test_native_binding_identity_changes_the_actual_measurement_key(self):
        snapshot = self.snapshot(self.parent())
        recorded = []
        original = op_memo.memoized_value
        def capture(op, args, compute):
            if op == bounds.OP: recorded.append(args)
            return original(op, args, compute)
        with mock.patch.object(op_memo, "memoized_value", side_effect=capture):
            with mock.patch.object(bounds, "_native_identity", return_value="native=A;binding=A"):
                first = snapshot.bounds()
            with mock.patch.object(bounds, "_native_identity", return_value="native=B;binding=B"):
                second = snapshot.bounds()
        self.assertEqual(first, second)
        self.assertEqual({args[-1] for args in recorded}, {"native=A;binding=A", "native=B;binding=B"})
        self.assertTrue(bounds._native_identity().startswith("native="))


class LifecycleTests(DescriptorFixture, unittest.TestCase):
    def deferred(self, *args, **kwargs):
        return build.build_tree_through_step(*args, _internal_source_publication=True, **kwargs)

    def test_internal_path_full_tree_step_parity(self):
        for kind in ("box", "hole", "nurbs", "nested"):
            shape = self.parent(kind)
            expected = self.result(ordinary_build, shape)
            for state in ("cold-key", "ram", "disk", "disabled", "force"):
                if state == "disk": op_memo.clear(); mat.reset_memo()
                with mock.patch.dict(os.environ, {"CADGEN_OP_MEMO": "0" if state == "disabled" else "1"}):
                    actual = self.result(self.deferred, shape, force=state == "force")
                self.assertEqual(expected, actual, (kind, state))

    def test_only_internal_eligible_path_publishes_before_document_preparation(self):
        import build123d as bd
        for internal, force, own in [(True, False, False), (False, False, False), (True, True, False), (True, False, True)]:
            shape = bd.Box(3, 5, 7) if own else self.parent()
            events = []
            original = mat.materialize_descriptor
            def materialize(*args, **kwargs):
                result = original(*args, **kwargs); events.append("prepared"); return result
            with mock.patch.object(mat, "materialize_descriptor", side_effect=materialize):
                self.result(self.deferred if internal else build.build_tree_through_step, shape, force=force,
                            callback=lambda *_: events.append("preview"))
            self.assertEqual(events.index("preview") < events.index("prepared"), internal and not force and not own)

    def test_all_geometry_and_appearance_are_owned_before_callback(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        expected = self.result(ordinary_build, self.parent("nurbs"))
        shape = self.parent("nurbs")
        def mutate(*_):
            for child in shape.children:
                child.label = "mutated"
                child.color = (.2, .1, .8, .5)
                child.cad_face_ordinal_colors = {1: (0., 1., 0., 1.)}
                vertex = TopoDS.Vertex_s(TopExp_Explorer(child.wrapped, TopAbs_VERTEX).Current())
                BRep_Builder().UpdateVertex(vertex, gp_Pnt(55., 66., 77.), 1e-7)
            shape.label = "changed root"
        actual = self.result(self.deferred, shape, callback=mutate)
        self.assertEqual(expected, actual)

    def test_shared_brep_face_color_variants_keep_private_topology(self):
        import build123d as bd
        children = []
        entries = []
        for index, color in enumerate(((1., 0., 0., 1.), (0., 1., 0., 1.))):
            shape = bd.Box(3, 5, 7)
            shape.cad_face_ordinal_colors = {1: color}
            tree = build.build_tree_from_compound(shape, root_name=f"variant-{index}")[0]
            entries.append(next(iter(get_tree(tree)["components"].values())))
            children.append(mat.materialize(tree).moved(bd.Location((10. * index, 0., 0.))))
        self.assertEqual(entries[0]["brep"], entries[1]["brep"])
        parent = bd.Compound(children=children, label="root")
        snapshot = self.snapshot(parent).capture_appearance()
        self.assertEqual(len(snapshot.component_breps), 2)
        prepared = snapshot.prepare_document()
        prototypes = list(prepared._shapes.values())
        self.assertFalse(prototypes[0].wrapped.IsPartner(prototypes[1].wrapped))
        self.assertNotEqual(prototypes[0].cad_face_ordinal_colors,
                            prototypes[1].cad_face_ordinal_colors)
        self.assertEqual(self.result(ordinary_build, parent),
                         self.result(self.deferred, parent))

    def test_owned_snapshot_materialization_does_not_read_store(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Pnt
        snapshot = self.snapshot(self.parent()).capture_appearance()
        original = snapshot.descriptor()
        first = snapshot.materialize("root")
        with mock.patch.object(mat, "_bytes_for_object", side_effect=AssertionError("object lookup")), \
             mock.patch("cadgen._internal.surface_extract.read_surf", side_effect=AssertionError("SURF lookup")), \
             mock.patch("cadgen.store.trees.get_tree", side_effect=AssertionError("tree lookup")):
            second = snapshot.materialize("root")
        self.assertEqual(cp._shape_brep_bytes(first), cp._shape_brep_bytes(second))
        second_bytes = cp._shape_brep_bytes(second)
        vertex = TopoDS.Vertex_s(TopExp_Explorer(first.children[0].wrapped, TopAbs_VERTEX).Current())
        BRep_Builder().UpdateVertex(vertex, gp_Pnt(90., 80., 70.), 1e-7)
        self.assertEqual(second_bytes, cp._shape_brep_bytes(second))
        first.children[0].cad_face_ordinal_colors[1] = (0., 0., 0., 1.)
        self.assertNotEqual(first.children[0].cad_face_ordinal_colors, second.children[0].cad_face_ordinal_colors)
        self.assertEqual(original, snapshot.descriptor())

    def test_callback_cache_deletion_and_corruption_match_already_owned_document(self):
        for damage in ("missing", "corrupt"):
            shape = self.parent()
            snapshot = self.snapshot(shape)
            outcomes = []
            for function in (ordinary_build, self.deferred):
                def damage_inputs(*_):
                    for digest, data in snapshot.objects:
                        path = object_path(digest)
                        if damage == "missing": path.unlink(missing_ok=True)
                        else: path.write_bytes(b"damaged after publication")
                try:
                    outcomes.append(self.result(function, shape, callback=damage_inputs))
                finally:
                    for digest, data in snapshot.objects:
                        path = object_path(digest); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                    mat.reset_memo()
            self.assertEqual(outcomes[0], outcomes[1], damage)

    def test_existing_wait_children_failure_is_unchanged(self):
        from cadgen.authoring import BuildFrame
        for function in (ordinary_build, self.deferred):
            shape = self.parent()
            frame = BuildFrame(None)
            child = mock.Mock()
            child.wait_outputs.side_effect = RuntimeError("discarded child output failed")
            frame.children = [("discarded", child)]
            path = self.root / "must-not-save.step"
            with self.assertRaisesRegex(RuntimeError, "discarded child output failed"):
                function(shape, path, root_name="root", on_preview=lambda *_: frame.wait_children())
            child.wait_outputs.assert_called_once()
            self.assertFalse(path.exists())

    def test_reentrant_build_keeps_parent_snapshot_and_pins(self):
        import build123d as bd
        shape = self.parent("hole")
        expected = self.result(ordinary_build, shape)
        nested = []
        def reenter(*_):
            nested.append(self.result(self.deferred, bd.Box(1, 2, 3), name="nested"))
        actual = self.result(self.deferred, shape, callback=reenter)
        self.assertEqual(expected, actual)
        self.assertEqual(len(nested), 1)

    def test_native_invalidity_fails_before_preview_even_with_real_warm_bounds(self):
        from cadgen.store.index import entry_path, write_entry
        from cadgen.store.objects import put_object
        from cadgen.store.trees import get_tree, put_tree
        for invalid in ("brep", "placement"):
            with self.subTest(invalid=invalid):
                shape = self.parent()
                walk = build._walk_compound(shape, root_name="root", progress=build.resolve_progress(None))
                for link in walk.links:
                    tree = copy.deepcopy(get_tree(link["tree"]))
                    if invalid == "brep":
                        payload = cp._BREP_HEADERS["bintools-v4"] + b"not a native BREP representation"
                        digest = put_object(payload)
                        remap, entries = {}, {}
                        for cid, entry in tree["components"].items():
                            entry["brep"] = digest
                            entry["contentHash"] = cp.geometry_component_hash(entry["codec"], payload, entry["faceColors"])
                            remap[cid] = entry["contentHash"][:16]
                            entries[remap[cid]] = entry
                        tree["components"] = entries
                        for occurrence in tree["occurrences"]:
                            occurrence["component"] = remap[occurrence["component"]]
                    else:
                        for occurrence in tree["occurrences"]:
                            occurrence["transform"] = [0.] * 15 + [1.]
                    link["tree"] = put_tree(tree)
                snapshot = bounds.capture_links(walk.draft_tree(root_name="root")).capture_appearance()
                keys = []
                for cid, transform in snapshot.occurrences:
                    args = (dict(snapshot.component_breps)[cid], struct.pack("<16d", *transform), bounds._native_identity())
                    keys.append(op_memo._op_index_key(op_memo._build_key(bounds.OP, args, {})))
                for state in ("cold", "warm"):
                    with self.subTest(state=state):
                        for key in keys:
                            if state == "cold":
                                entry_path("op", key).unlink(missing_ok=True)
                            else:
                                write_entry("op", key, {"value": [-1., -1., -1., 1., 1., 1.]})
                        op_memo.clear(); mat.reset_memo()
                        if state == "warm":
                            # Verify actual disk entries skip native work; this is
                            # precisely the scalar-hit state that must not certify
                            # native bytes or gp_Trsf validity for publication.
                            with mock.patch.object(cp, "decode_geometry_component", side_effect=AssertionError("warm bounds decoded")):
                                self.assertEqual(snapshot.bounds(), {"min": [-1.] * 3, "max": [1.] * 3})
                        failures = []
                        for module, function in ((build, ordinary_build), (build, self.deferred)):
                            callback = mock.Mock()
                            path = self.root / f"invalid-{invalid}-{state}-{module.__name__.split('.')[-1]}.step"
                            path.unlink(missing_ok=True)
                            with mock.patch.object(module, "_walk_compound", return_value=walk):
                                try:
                                    function(shape, path, root_name="root", on_preview=callback)
                                except Exception as error:
                                    failures.append((type(error), str(error)))
                                else:
                                    self.fail("invalid native representation was published")
                            callback.assert_not_called()
                            self.assertFalse(path.exists())
                        self.assertEqual(failures[0], failures[1])

    def test_failed_bounds_releases_prevalidated_prototypes_before_fallback(self):
        shape = self.parent()
        expected = self.result(ordinary_build, shape)
        prepared_refs = []
        original_prepare = bounds.Snapshot.prepare_document
        original_materialize = mat.materialize_descriptor
        def prepare(snapshot):
            prepared = original_prepare(snapshot)
            prepared_refs.append(weakref.ref(prepared))
            return prepared
        def materialize(*args, **kwargs):
            self.assertTrue(prepared_refs)
            self.assertTrue(all(ref() is None for ref in prepared_refs))
            return original_materialize(*args, **kwargs)
        with mock.patch.object(bounds.Snapshot, "prepare_document", prepare), \
             mock.patch.object(bounds.Snapshot, "bounds", side_effect=bounds.Ineligible("invalid scalar entry")), \
             mock.patch.object(mat, "materialize_descriptor", side_effect=materialize):
            actual = self.result(self.deferred, shape)
        self.assertEqual(expected, actual)

    def test_prevalidated_prototypes_supply_bounds_misses_without_second_decode(self):
        shape = self.parent()
        snapshot = self.snapshot(shape).capture_appearance()
        prepared = snapshot.prepare_document()
        from cadgen.store.index import entry_path
        for cid, transform in snapshot.occurrences:
            args = (dict(snapshot.component_breps)[cid], struct.pack("<16d", *transform), bounds._native_identity())
            entry_path("op", op_memo._op_index_key(op_memo._build_key(bounds.OP, args, {}))).unlink(missing_ok=True)
        op_memo.clear()
        with mock.patch.object(cp, "_build123d_shape_from_brep_bytes", side_effect=AssertionError("second decode")):
            actual = snapshot.bounds(shapes=prepared._shapes)
        self.assertEqual(actual, cp._bbox_from_shape(prepared.materialize("root")))

    def test_appearance_budget_falls_back_before_callback(self):
        shape = self.parent()
        expected = self.result(ordinary_build, shape)
        events = []
        original = mat.materialize_descriptor
        def materialize(*args, **kwargs):
            result = original(*args, **kwargs); events.append("prepared"); return result
        with mock.patch.object(bounds, "MAX_APPEARANCE_BYTES", 1), \
             mock.patch.object(mat, "materialize_descriptor", side_effect=materialize):
            actual = self.result(self.deferred, shape, callback=lambda *_: events.append("preview"))
        self.assertEqual(expected, actual)
        self.assertLess(events.index("prepared"), events.index("preview"))


if __name__ == "__main__":
    unittest.main()
