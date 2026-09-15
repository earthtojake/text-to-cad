"""Document compilation consumes its requested bytes without discarded source work."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class ColdCompileCleanupTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="cold-compile-cleanup-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_COMPONENT_WORKERS": "1", "CADGEN_DAEMON": "0",
        })
        env.start()
        self.addCleanup(env.stop)

    def document(self, *, nested=False, repeated=False, multiple_roots=False):
        from build123d import Compound, Location, Solid
        from cadgen.step_export import export_build123d_step_file

        red = Solid.make_box(2, 3, 4)
        red.label, red.color = "red part", (1., .1, .2, 1.)
        red.cad_face_ordinal_colors = {1: (.2, .8, .3, 1.)}
        shape = red
        if nested:
            blue = Solid.make_cylinder(1.5, 5).moved(Location((5, 0, 0), (13, 21, 7)))
            blue.label, blue.color = "blue part", (.2, .3, 1., 1.)
            members = [red, blue]
            if repeated:
                again = red.moved(Location((8, 1, 2)))
                again.label = "red repeated"
                members.append(again)
            group = Compound(children=members, label="pair").moved(Location((2, 4, 1), (0, 0, 27)))
            shape = Compound(children=[group], label="assembly")
        path = self.root / ("multi.step" if multiple_roots else "nested.step" if nested else "part.step")
        if multiple_roots:
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
            writer = STEPControl_Writer()
            for member in (red, Solid.make_cylinder(1.5, 5).moved(Location((7, 2, 1)))):
                self.assertEqual(writer.Transfer(member.wrapped, STEPControl_AsIs), IFSelect_RetDone)
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
        else:
            export_build123d_step_file(shape, path)
        return path

    def snapshot(self, tree_hash):
        from cadgen.store.objects import read_verified_object
        from cadgen.store.trees import get_tree, tree_objects

        return {
            "treeHash": tree_hash,
            "tree": get_tree(tree_hash),
            "objects": {digest: read_verified_object(digest) for digest in tree_objects(tree_hash)},
        }

    def compile(self, document, **kwargs):
        from cadgen.step_artifact_cli import build_step_artifact

        return build_step_artifact(repo_root=self.root, step=document, **kwargs)

    def test_document_compile_never_discovers_unrelated_sources(self):
        from cadgen import step_artifact_cli as artifact

        document = self.document()
        unrelated = self.root / "unrelated-source"
        unrelated.mkdir()
        (unrelated / "model.py").write_text(
            "from cadgen import step\n@step\ndef body():\n    raise RuntimeError('unrelated')\n",
            encoding="utf-8",
        )
        forbidden = str(unrelated.resolve())
        attempts = []
        guard = {"enabled": True}

        def audit(event, args):
            if not guard["enabled"] or event not in {"open", "os.listdir", "os.scandir"} or not args:
                return
            if not isinstance(args[0], (str, bytes)):
                return
            path = os.path.abspath(os.fsdecode(args[0]))
            if path == forbidden or path.startswith(forbidden + os.sep):
                attempts.append((event, path))
                raise AssertionError("document compile accessed unrelated source")

        sys.addaudithook(audit)
        try:
            with mock.patch.object(artifact, "iter_cad_sources", wraps=artifact.iter_cad_sources) as discovered:
                result = self.compile(document)
            discovered.assert_not_called()
            self.assertEqual(attempts, [])  # An internal catch must not hide attempted reads.
            self.assertTrue(result["ok"])
        finally:
            guard["enabled"] = False

    def test_raw_compile_matches_direct_canonical_objects_cold_warm_and_force(self):
        from cadgen._internal.step_scene_package import load_step_scene_exact
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import tree_for_document_hash

        for nested in (False, True):
            with self.subTest(nested=nested):
                document = self.document(nested=nested)
                original_bytes = document.read_bytes()
                digest = hashlib.sha256(original_bytes).hexdigest()
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"expected-{nested}")}):
                    tree, _, _ = build_document_tree(load_step_scene_exact(document), force=True)
                    expected = self.snapshot(tree)
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"actual-{nested}")}):
                    for force in (False, False, True):
                        result = self.compile(document, force=force)
                        self.assertEqual(expected, self.snapshot(result["tree"]))
                        self.assertEqual(tree_for_document_hash(digest), tree)
                        self.assertEqual(document.read_bytes(), original_bytes)

    def test_cold_and_warm_native_compile_never_prepare_display_surfaces(self):
        from cadgen._internal import surface_extract, step_scene_package
        document = self.document(nested=True)
        with mock.patch.object(surface_extract, "extract_surface_component", side_effect=AssertionError("display work in native compile")), \
             mock.patch("cadgen.store.view.view_dir_for", side_effect=AssertionError("display view in native compile")):
            first = self.compile(document)
            with mock.patch.object(step_scene_package, "_load_step_scene_text", side_effect=AssertionError("warm compile reparsed STEP")):
                second = self.compile(document)
        self.assertEqual(second["tree"], first["tree"])
        self.assertTrue(second["skipped"])
        self.assertFalse((self.root / "store/index/surface").exists())

    def test_discarded_composition_preserves_prototype_bytes_and_canonical_result(self):
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen._internal.step_scene_mesh import scene_to_build123d_compound
        from cadgen._internal.step_scene_package import load_step_scene_exact
        from cadgen.store.build import build_document_tree

        for name, options in (("single", {}),
                              ("repeated", {"nested": True, "repeated": True}),
                              ("multiple", {"multiple_roots": True})):
            with self.subTest(case=name):
                document = self.document(**options)
                legacy_scene = load_step_scene_exact(document)
                if name == "multiple":
                    self.assertGreater(len(legacy_scene.roots), 1)
                before = {key: (_shape_brep_bytes(shape), shape.Free())
                          for key, shape in legacy_scene.prototype_shapes.items()}
                discarded = scene_to_build123d_compound(legacy_scene)
                after = {key: (_shape_brep_bytes(shape), shape.Free())
                         for key, shape in legacy_scene.prototype_shapes.items()}
                self.assertEqual(before, after, "legacy wrapper mutated canonical prototypes")
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"legacy-{name}")}):
                    legacy_hash, _, _ = build_document_tree(legacy_scene, force=True)
                    expected = self.snapshot(legacy_hash)
                with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / f"direct-{name}")}):
                    direct_hash, _, _ = build_document_tree(load_step_scene_exact(document), force=True)
                    self.assertEqual(expected, self.snapshot(direct_hash))
                self.assertIsNotNone(discarded.wrapped)  # Match the old wrapper's lifetime.

    def test_raw_compile_skips_discarded_native_and_adaptive_preparation(self):
        from cadgen._internal import generation, step_scene_mesh, generation_spec
        from cadgen._internal.step_scene_package import load_step_scene_exact
        from cadgen.store.build import build_document_tree

        document = self.document(nested=True)
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "expected")}):
            tree, _, _ = build_document_tree(load_step_scene_exact(document))
            expected = self.snapshot(tree)
        with mock.patch.object(step_scene_mesh, "scene_to_build123d_compound", side_effect=AssertionError("unused native compound")), \
             mock.patch.object(generation_spec, "adaptive_mesh_resolution_for_scene", side_effect=AssertionError("unused classification")), \
             mock.patch.object(generation, "_assembly_provenance_manifest", side_effect=AssertionError("unused provenance")):
            for force in (False, True):
                result = self.compile(document, force=force)
                self.assertEqual(expected, self.snapshot(result["tree"]))

    def test_generated_and_reemit_scenes_keep_existing_preparation(self):
        from cadgen import step_artifact_cli as artifact
        from cadgen._internal import generation, step_scene_mesh
        from cadgen._internal.step_scene_package import load_step_scene_exact
        from cadgen._internal.step_scene_types import SelectorOptions

        class Reached(Exception):
            pass

        document = self.document()
        for source, kind, reemit in (("generated", "python", None),
                                     ("generated", "step", "input-digest"),
                                     ("imported", "python", None),
                                     ("imported", "step", "input-digest")):
            with self.subTest(source=source, kind=kind, reemit=reemit):
                scene = load_step_scene_exact(document)
                scene.source_kind, scene.reemit_source_hash = kind, reemit
                spec = replace(artifact._build_entry_spec(self.root, document, scene), source=source)
                with mock.patch.object(generation, "_selector_options_for_part", side_effect=Reached) as classified:
                    with self.assertRaises(Reached):
                        generation._generate_part_outputs(spec, entries_by_step_path={}, preloaded_scene=scene, force=True)
                self.assertIs(classified.call_args.kwargs["scene"], scene)
                with mock.patch.object(generation, "_selector_options_for_part", return_value=SelectorOptions()), \
                     mock.patch.object(generation, "_assembly_provenance_manifest", return_value={}), \
                     mock.patch.object(step_scene_mesh, "scene_to_build123d_compound", side_effect=Reached) as composed:
                    with self.assertRaises(Reached):
                        generation._generate_part_outputs(spec, entries_by_step_path={}, preloaded_scene=scene, force=True)
                composed.assert_called_once_with(scene)

    def test_public_reader_still_constructs_private_return_geometry(self):
        from cadgen._internal import step_scene_mesh
        from cadgen._internal.step_scene_package import load_step_scene_cached
        from cadgen.step_scene import read_step

        document = self.document(nested=True)
        self.compile(document)
        original = step_scene_mesh.scene_to_build123d_compound
        with mock.patch.object(step_scene_mesh, "scene_to_build123d_compound", wraps=original) as composed:
            first = read_step(document)
            second = read_step(document)
        self.assertEqual(composed.call_count, 2)
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))
        first.children[0].label = "changed local wrapper"
        self.assertNotEqual(first.children[0].label, second.children[0].label)
        self.assertTrue(load_step_scene_cached(document).roots)

    def test_bound_sidecar_is_preserved_and_remains_an_export_overlay(self):
        from cadgen._internal.source_sidecar import (
            SOURCE_MATERIAL_DEFAULTS,
            apply_appearance,
            read_source_sidecar,
            source_sidecar_path,
            write_source_sidecar,
        )
        from cadgen.store.trees import flatten

        document = self.document(nested=True)
        source_bytes = document.read_bytes()
        digest = hashlib.sha256(source_bytes).hexdigest()
        payload = {"appearance": {
                       "materials": {"finish": {"name": "Finish", "roughness": .27, "metalness": .6}},
                       "assignments": {"o1.1.1": "finish"},
                   },
                   "kinematics": {"poses": {"rest": {}}}}
        write_source_sidecar(document, payload, document_hash=digest)
        sidecar = source_sidecar_path(document)
        sidecar_bytes = sidecar.read_bytes()
        first_tree = None
        for force in (False, False, True):
            result = self.compile(document, force=force)
            if first_tree is None:
                first_tree = result["tree"]
            self.assertEqual(result["tree"], first_tree)
            self.assertEqual(document.read_bytes(), source_bytes)
            self.assertEqual(sidecar.read_bytes(), sidecar_bytes)
            declarations = read_source_sidecar(document, document_hash=digest)
            self.assertEqual(declarations["kinematics"], payload["kinematics"])
            canonical = flatten(result["tree"])
            overlaid = apply_appearance(canonical, declarations["appearance"])
            occurrence = next(occ for occ in overlaid["occurrences"] if occ["id"] == "o1.1.1")
            self.assertEqual(
                occurrence["material"],
                {**SOURCE_MATERIAL_DEFAULTS, "roughness": .27, "metalness": .6},
            )
            self.assertEqual(occurrence["materialName"], "Finish")
            self.assertNotEqual(overlaid, canonical)

    def test_foreign_sidecar_is_not_repaired_or_silently_accepted_by_its_reader(self):
        from cadgen._internal.source_sidecar import (
            SidecarBindingError, read_source_sidecar, source_sidecar_path, write_source_sidecar,
        )

        document = self.document()
        digest = hashlib.sha256(document.read_bytes()).hexdigest()
        write_source_sidecar(document, {"kinematics": {"poses": {"rest": {}}}}, document_hash=digest)
        sidecar = source_sidecar_path(document)
        foreign = json.loads(sidecar.read_text(encoding="utf-8"))
        foreign["documentHash"] = "a" * 64
        sidecar.write_text(json.dumps(foreign), encoding="utf-8")
        before = document.read_bytes(), sidecar.read_bytes()
        # Cold and forced compile derive only geometry; a current-result payload
        # reads declarations and retains the existing loud binding failure.
        self.compile(document)
        with self.assertRaises(SidecarBindingError):
            self.compile(document)
        self.compile(document, force=True)
        with self.assertRaises(SidecarBindingError):
            read_source_sidecar(document, document_hash=digest)
        self.assertEqual(before, (document.read_bytes(), sidecar.read_bytes()))

    def test_damaged_component_is_repaired_by_real_forced_compile(self):
        from cadgen.store.objects import object_path
        from cadgen.store.trees import get_tree

        document = self.document()
        result = self.compile(document)
        expected = self.snapshot(result["tree"])
        component = next(iter(get_tree(result["tree"])["components"].values()))
        for key in ("brep",):
            object_path(component[key]).write_bytes(b"corrupt canonical object")
            repaired = self.compile(document, force=True)
            self.assertEqual(expected, self.snapshot(repaired["tree"]))


if __name__ == "__main__":
    unittest.main()
