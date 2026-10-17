"""Exact native selection agrees with saved geometry and canonical viewer IDs.

A ref names geometry: an occurrence by its token, an element by the occurrence's token and
the element's (``#o:…/f:…``), so the refs here are read off the scene, never written down."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from build123d import Compound, Pos, Rot, Solid, Vector
from cadgen import read_scene, read_step


class StepSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="python-inspection-")
        cls.root = Path(cls.temp.name)
        cls.env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(cls.root / "store"), "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
        })
        cls.env.start()
        cls.path = cls.root / "assembly.step"
        pin = Solid.make_cylinder(3, 10)
        pin.label = "pin"
        other_pin = Pos(0, 0, 20) * pin
        other_pin.label = "pin"
        group = Pos(100, 50, 7) * Rot(0, 90, 0) * Compound(children=[pin, other_pin], label="housing")
        block = Solid.make_box(5, 6, 7)
        block.label = "base"
        cls.model = Compound(children=[group, block], label="assembly")
        from cadgen.step_export import export_build123d_step_file
        from cadgen import step
        export_build123d_step_file(cls.model, cls.path)
        cls.tree = step.compile(cls.path).tree

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.temp.cleanup()

    def test_hierarchy_labels_and_strict_reference_resolution(self):
        scene = read_scene(self.path)
        self.assertEqual(len(scene.roots), 1)
        self.assertEqual(len(list(scene.leaves())), 3)
        group = scene.resolve("#housing")
        self.assertEqual(group.kind, "occurrence")
        self.assertIsNone(group.prototype_id)
        self.assertEqual(len(group.children), 2)
        self.assertEqual(scene.resolve(group.ref).ref, group.ref)
        self.assertEqual(scene.resolve(self.path.name + group.ref).ref, group.ref)
        with self.assertRaisesRegex(ValueError, "matches 2"):
            scene.resolve("#pin")
        self.assertNotEqual(scene.resolve("#pin_1").ref, scene.resolve("#pin_2").ref)
        self.assertEqual(scene.resolve("#pin_1").prototype_id, scene.resolve("#pin_2").prototype_id)
        face = next(scene.resolve("#pin_1").entities("face")).ref.split("/")[1]
        # `assembly#…`: a bare stem names no file; a prefix is the file's path, extension
        # included. A bare element token needs the one leaf an assembly has not; the retired
        # positional grammar (`#o1.2`, `#pin_1.f1`) names nothing.
        for ref in ("#no_such_part", f"#{face}", "#housing.f1", f"wrong.step#{group.ref[1:]}", f"assembly#{group.ref[1:]}",
                    "#o:" + "9" * 12, "#pin_1.f1", f"#pin_1/{face},{face}", "#pin_1/f:not0a0token"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                scene.resolve(ref)
        # A label stands in for the occurrence token in an element ref.
        self.assertEqual(scene.resolve(f"#pin_1/{face}").ref, f"{scene.resolve('#pin_1').ref}/{face}")

    def test_geometry_is_world_placed_including_nested_rotation(self):
        scene = read_scene(self.path)
        pin = scene.resolve("#pin_1")
        solid = pin.shape().solids()[0]
        self.assertLess((solid.center() - Vector(105, 50, 7)).length, 1e-6)
        self.assertLess((scene.resolve("#pin_2").shape().center() - Vector(125, 50, 7)).length, 1e-6)
        circle = next(e.shape() for e in pin.entities("edge") if e.shape().geom_type.name == "CIRCLE")
        self.assertAlmostEqual(circle.radius, 3)
        self.assertAlmostEqual(circle.arc_center.Y, 50)
        self.assertAlmostEqual(circle.arc_center.Z, 7)
        self.assertAlmostEqual(scene.resolve("#housing").shape().volume, 2 * solid.volume)
        self.assertAlmostEqual(read_step(self.path).volume, scene.roots[0].shape().volume)

    def test_enumeration_preserves_occurrences_and_parent_ordinals(self):
        scene = read_scene(self.path)
        group = scene.resolve("#housing")
        faces = list(group.entities("face"))
        self.assertEqual(len(faces), 6)
        self.assertEqual(len({f.ref for f in faces}), 6)
        for selection in faces:
            self.assertEqual(scene.resolve(selection.ref).ref, selection.ref)
            for edge in selection.entities("edge"):
                self.assertEqual(scene.resolve(edge.ref).ref, edge.ref)
                self.assertAlmostEqual(edge.shape().length, scene.resolve(edge.ref).shape().length)
        base = scene.resolve("#base")
        self.assertEqual(len(list(base.entities("vertex"))), 8)
        # A body has no ref of its own: the occurrence names it.
        for kind in ("shape", "planes"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                list(base.entities(kind))

    def test_native_copies_cannot_mutate_scene_or_other_occurrences(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_VERTEX
        scene = read_scene(self.path)
        a, b = scene.resolve("#pin_1"), scene.resolve("#pin_2")
        first, second = a.shape(), a.shape()
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))
        self.assertFalse(first.wrapped.IsPartner(b.shape().wrapped))
        vertex = TopoDS.Vertex_s(TopExp_Explorer(first.wrapped, TopAbs_VERTEX).Current())
        BRep_Builder().UpdateVertex(vertex, 10.0)
        first.move(Pos(900, 0, 0))
        self.assertLess((a.shape().center() - Vector(105, 50, 7)).length, 1e-6)
        self.assertLess((b.shape().center() - Vector(125, 50, 7)).length, 1e-6)
        from OCP.BRep import BRep_Tool
        untouched_vertex = TopoDS.Vertex_s(TopExp_Explorer(a.shape().wrapped, TopAbs_VERTEX).Current())
        self.assertLess(BRep_Tool.Tolerance_s(untouched_vertex), 1e-3)

    def test_read_and_occurrence_lookup_decode_no_geometry_or_display_data(self):
        from cadgen._internal import component_package
        with mock.patch.object(component_package, "decode_geometry_component", wraps=component_package.decode_geometry_component) as decoded, \
             mock.patch("cadgen.store.parts.derive", side_effect=AssertionError("inspection requested display data")), \
             mock.patch("cadgen.store.parts.request_display", side_effect=AssertionError("inspection requested display data")), \
             mock.patch("cadgen._internal.topology_extract.extract_topology_facts", side_effect=AssertionError("inspection extracted topology facts")):
            scene = read_scene(self.path)
            scene.resolve("#housing")
            list(scene.leaves())
            decoded.assert_not_called()
            scene.resolve("#pin_1").shape()
            self.assertEqual(decoded.call_count, 1)
            scene.resolve("#pin_2").shape()
            next(scene.resolve("#pin_1").entities("face")).shape()
            self.assertEqual(decoded.call_count, 1)

    def test_cached_inventory_does_not_import_build123d(self):
        code = textwrap.dedent("""
            import sys
            class NoBuild123d:
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] == 'build123d':
                        raise AssertionError('inventory imported build123d')
            sys.meta_path.insert(0, NoBuild123d())
            from cadgen import read_scene
            scene = read_scene(sys.argv[1])
            assert len(list(scene.leaves())) == 3
            assert len(scene.resolve('#housing').children) == 2
            assert scene.resolve('#pin_1').prototype_id == scene.resolve('#pin_2').prototype_id
        """)
        result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_coincident_occurrences_keep_distinct_entity_references(self):
        from cadgen.step_export import export_build123d_step_file
        path = self.root / "coincident.step"
        a, b = Solid.make_box(2, 3, 4), Solid.make_box(2, 3, 4)
        a.label, b.label = "a", "b"
        export_build123d_step_file(Compound(children=[a, b], label="both"), path)
        scene = read_scene(path)
        self.assertEqual(len(list(scene.leaves())), 2)
        faces = list(scene.roots[0].entities("face"))
        self.assertEqual(len({f.ref for f in faces}), 12)
        self.assertAlmostEqual(scene.resolve("#a").shape().volume, 24)
        self.assertAlmostEqual(scene.resolve("#b").shape().volume, 24)

    def test_scene_keeps_captured_revision_after_replacement_and_cache_deletion(self):
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.objects import object_path
        from cadgen.store.trees import capture_tree
        target = self.root / "replaced.step"
        target.write_bytes(self.path.read_bytes())
        old = read_scene(target)
        expected = hashlib.sha256(target.read_bytes()).hexdigest()
        replacement = Solid.make_box(2, 3, 4)
        replacement.label = "replacement"
        export_build123d_step_file(replacement, target)
        new = read_scene(target)
        self.assertEqual(old.document_hash, expected)
        self.assertNotEqual(new.document_hash, expected)
        self.assertEqual(len(list(old.leaves())), 3)
        # One leaf: a bare element token resolves, to the same face as the full ref.
        (leaf,) = new.leaves()
        face = next(leaf.entities("face"))
        token = face.ref.split("/")[1]
        self.assertEqual(new.resolve(f"#{token}").ref, face.ref)
        self.assertAlmostEqual(new.resolve(f"#{token}").shape().area, face.shape().area)
        self.assertAlmostEqual(new.roots[0].shape().volume, 24)
        # Holding a scene retains selected bytes, even before any geometry was decoded.
        descriptor, captured = capture_tree(self.tree)
        victim = next(iter(descriptor["components"].values()))["brep"]
        saved = captured[victim]
        object_path(victim).unlink()
        try:
            self.assertGreater(next(old.resolve("#pin_1").entities("face")).shape().area, 0)
        finally:
            from cadgen.store.objects import put_object
            put_object(saved, repair=True)

    def test_face_and_edge_names_match_display_extraction(self):
        from cadgen._internal.geometric_tokens import element_names
        from cadgen._internal.topology_extract import component_metrics, extract_topology_facts
        # Compare using the scene's canonical BREP, before its world placement: the
        # entities come in the table's ordinal order, each under its name -- for a file no
        # model run named, the token the body's geometry gives that ordinal.
        scene = read_scene(self.path)
        selection = scene.resolve("#pin_1")
        raw = scene._loaded.prototype_shapes[selection._node.prototype_key]
        facts = extract_topology_facts(raw)
        faces = component_metrics(raw)["faces"]
        tokens = element_names(None, raw)
        for kind, plural in (("face", "faces"), ("edge", "edges")):
            entities = list(selection.entities(kind))
            rows = facts[plural]
            self.assertEqual(len(entities), len(rows))
            for i, entity in enumerate(entities, 1):
                self.assertEqual(entity.ref, f"{selection.ref}/{tokens[plural][i - 1]}")
                self.assertEqual(entity.kind, kind)
                metric = {"face": "area", "edge": "length"}[kind]
                exact = (faces if kind == "face" else rows)[i - 1][metric]
                self.assertAlmostEqual(getattr(entity.shape(), metric), exact, places=6)
