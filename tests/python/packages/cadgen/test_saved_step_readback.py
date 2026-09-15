"""Saved readback may reuse only a verified canonical tree of the exact bytes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class SavedStepReadbackTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="saved-step-readback-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        environment.start()
        self.addCleanup(environment.stop)
        workers = mock.patch("cadgen._internal.component_package._component_build_worker_count", return_value=1)
        workers.start()
        self.addCleanup(workers.stop)

    def shape(self, size=2):
        from build123d import Solid

        shape = Solid.make_box(size, 3, 4)
        shape.label = "part"
        shape.color = (.8, .7, .6, 1)
        shape.cad_face_ordinal_colors = {1: (1., 0., 0., 1.), 3: (0., 0., 1., 1.)}
        return shape

    def build(self, shape=None, *, force=False, materials=None):
        from cadgen.store.build import build_tree_through_step

        return build_tree_through_step(
            self.shape() if shape is None else shape, self.root / "part.step",
            root_name="root", force=force, materials=materials,
        )

    def seed(self, shape=None, *, materials=None):
        from cadgen.store.records import note_document_tree

        result = self.build(shape, materials=materials)
        note_document_tree(result[3], result[2]["documentTree"])
        return result

    def assert_same_document(self, expected, actual):
        self.assertEqual(expected[3], actual[3])
        for key in ("documentTree", "documentOccurrenceMap", "documentNodeMap", "documentAppearance"):
            self.assertEqual(expected[2][key], actual[2][key], key)

    def test_exact_digest_hit_matches_forced_raw_readback_and_has_private_geometry(self):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package

        expected = self.seed()
        cached = scene_from_render_package(self.root / "part.step", step_hash=expected[3])
        vertex = TopoDS.Vertex_s(TopExp_Explorer(next(iter(cached.prototype_shapes.values())), TopAbs_VERTEX).Current())
        BRep_Builder().UpdateVertex(vertex, gp_Pnt(50, 60, 70), 1e-7)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")):
            warm = self.build()
        self.assert_same_document(expected, warm)
        self.assertEqual(expected[:2], warm[:2])
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            forced = self.build(force=True)
        raw.assert_called_once()
        self.assert_same_document(expected, forced)

    def test_new_geometry_digest_is_a_raw_miss_even_with_an_existing_path_record(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.records import note_output, write_record

        old = self.seed()
        source = self.root / "removed-source.py"
        write_record(source, {"tree": old[0], "outputs": {str(self.root / "part.step"): {"sha256": old[3]}}})
        note_output(self.root / "part.step", source)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            changed = self.build(self.shape(5))
        raw.assert_called_once()
        self.assertNotEqual(old[3], changed[3])
        self.assertNotEqual(old[2]["documentTree"], changed[2]["documentTree"])

    def test_repeated_assembly_readback_retains_exact_canonical_objects_without_reencoding(self):
        from build123d import Compound, Location, Solid
        from cadgen._internal.step_scene_package import load_step_scene_exact
        from cadgen.store.build import build_document_tree
        from cadgen.store.objects import read_verified_object
        from cadgen.store.trees import tree_objects

        shapes = []
        for index in range(24):
            part = Solid.make_cylinder(1 + index % 6, 3)
            part.label = f"cylinder-{index}"
            part.color = (index % 2, (index + 1) % 2, .5, 1)
            shapes.append(part.moved(Location((index * 15, index % 3, 0), (17, 31, 43))))
        shape = Compound(children=shapes, label="root")
        expected = self.seed(shape)
        digest = expected[2]["documentTree"]
        original = {key: read_verified_object(key) for key in tree_objects(digest)}
        with mock.patch("cadgen.store.build._publish_document_scene",
                        side_effect=AssertionError("verified canonical inputs were re-encoded")), \
                mock.patch("cadgen._internal.step_scene_loader.load_step_scene",
                           side_effect=AssertionError("exact saved bytes were reparsed")):
            for _ in range(3):
                self.assert_same_document(expected, self.build(shape))
                self.assertEqual({key: read_verified_object(key) for key in tree_objects(digest)}, original)
        self.assert_same_document(expected, self.build(shape, force=True))
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "cold-store")}):
            cold_hash, _, _ = build_document_tree(load_step_scene_exact(self.root / "part.step"))
            self.assertEqual(cold_hash, digest)

    def test_generic_publication_derives_mutated_scene_despite_matching_document_digest(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import tree_for_document_hash

        expected = self.seed()
        scene = scene_from_render_package(self.root / "part.step", step_hash=expected[3])
        original = (self.root / "part.step").read_bytes()
        key = next(iter(scene.prototype_shapes))
        scene.prototype_shapes[key] = self.shape(9).wrapped
        scene.prototype_face_colors.clear()
        scene.roots[0].name = "changed public scene"
        # Public hashes and invented attestation attributes cannot grant reuse.
        scene.document_tree = expected[2]["documentTree"]
        changed_hash, changed_tree, _ = build_document_tree(scene)
        self.assertNotEqual(changed_hash, expected[2]["documentTree"])
        self.assertEqual(changed_tree["label"], "changed public scene")
        self.assertEqual(scene.step_hash, expected[3])
        self.assertEqual(tree_for_document_hash(expected[3]), expected[2]["documentTree"])
        self.assertEqual((self.root / "part.step").read_bytes(), original)

    def test_current_pbr_is_rebound_without_reading_source_records_or_staged_sidecars(self):
        from cadgen._internal.source_sidecar import SOURCE_MATERIAL_DEFAULTS

        shape = self.shape()
        first_finish = {"name": "First", "roughness": .2, "metalness": .6}
        second_finish = {"name": "Second", "roughness": .8, "metalness": .1}
        declaration = lambda finish: {
            "definitions": {"finish": finish},
            "assignments": [{"targets": ["#part"], "material": "finish"}],
        }
        expected = self.seed(shape, materials=declaration(first_finish))
        (self.root / "part.step.json").write_text("not a sidecar", encoding="utf-8")
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")), \
                mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("read source record")):
            changed = self.build(shape, materials=declaration(second_finish))
        self.assertEqual(expected[3], changed[3])
        self.assertEqual(expected[2]["documentTree"], changed[2]["documentTree"])
        self.assertNotEqual(expected[2]["documentAppearance"], changed[2]["documentAppearance"])
        expected_effective = {
            **SOURCE_MATERIAL_DEFAULTS,
            "roughness": second_finish["roughness"],
            "metalness": second_finish["metalness"],
        }
        self.assertTrue(all(
            value == expected_effective
            for value in changed[2]["documentAppearance"].values()
        ))
        self.assertEqual(changed[1]["appearance"]["materials"]["finish"], second_finish)

    def test_nested_located_root_and_repeated_prototypes_keep_names_placements_and_colors(self):
        from build123d import Compound, Location

        first = self.shape().moved(Location((2, 0, 0)))
        first.label, first.color = "first", (1, 0, 0, 1)
        second = self.shape().moved(Location((8, 0, 0)))
        second.label, second.color = "second", (0, 1, 0, 1)
        group = Compound(children=[first, second], label="pair").moved(Location((20, 5, 0), (0, 0, 30)))
        shape = Compound(children=[group], label="root").moved(Location((3, 4, 5), (10, 0, 0)))
        materials = {
            "definitions": {"finish": {"name": "Finish", "roughness": .7}},
            "assignments": [{"targets": ["#second"], "material": "finish"}],
        }
        expected = self.seed(shape, materials=materials)
        with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("cache hit parsed STEP")):
            warm = self.build(shape, materials=materials)
        self.assert_same_document(expected, warm)
        self.assert_same_document(expected, self.build(shape, force=True, materials=materials))

    def test_indexed_missing_or_digest_mismatched_objects_reparse_and_repair(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.objects import object_hash, object_path
        from cadgen.store.trees import get_tree, tree_objects

        expected = self.seed()
        tree_hash = expected[2]["documentTree"]
        tree = get_tree(tree_hash)
        component = next(iter(tree["components"].values()))
        original = {digest: object_path(digest).read_bytes() for digest in tree_objects(tree_hash)}
        for kind, digest in (("tree", tree_hash), ("brep", component["brep"])):
            for damage in ("missing", "mismatched"):
                with self.subTest(kind=kind, damage=damage):
                    path = object_path(digest)
                    if damage == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(b"damaged object")
                    self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[3]))
                    with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
                        repaired = self.build()
                    raw.assert_called_once()
                    self.assert_same_document(expected, repaired)
                    for object_digest, payload in original.items():
                        self.assertEqual(object_path(object_digest).read_bytes(), payload)
                        self.assertEqual(object_hash(payload), object_digest)

    def test_missing_or_unreadable_surface_never_blocks_native_face_colors(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store import surfaces
        from cadgen.store.index import write_entry
        from cadgen.store.objects import object_path, put_object
        from cadgen.store.trees import get_tree

        expected = self.seed()
        tree = expected[2]["documentTree"]
        expected_colors = sorted(tuple(color) for entry in get_tree(tree)["components"].values()
                                 for color in entry["faceColors"].values())
        record = next(iter(surfaces.derive(tree).values()))
        payload = object_path(record["object"]).read_bytes()
        for damage in ("missing", "digest-mismatched", "hash-valid-unreadable"):
            with self.subTest(damage=damage):
                put_object(payload, repair=True)
                write_entry("surface", record["surfaceInput"], record)
                if damage == "missing":
                    object_path(record["object"]).unlink()
                elif damage == "digest-mismatched":
                    object_path(record["object"]).write_bytes(b"corrupt surface")
                else:
                    write_entry("surface", record["surfaceInput"], {
                        **record, "object": put_object(b"hash-valid unreadable SURF"),
                    })
                with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("native hit parsed STEP")), \
                        mock.patch("cadgen._internal.surface_extract.extract_surface_component", side_effect=AssertionError("native read extracted SURF")):
                    scene = scene_from_render_package(self.root / "part.step", step_hash=expected[3])
                    self.assertIsNotNone(scene)
                    actual_colors = sorted(color for recipe in scene.prototype_face_colors.values()
                                           for color in recipe.values())
                    self.assertEqual(actual_colors, expected_colors)
                    self.assert_same_document(expected, self.build())

    def test_absent_document_index_does_not_reuse_damaged_component_objects(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.index import remove_entry
        from cadgen.store.objects import object_path
        from cadgen.store.trees import get_tree

        expected = self.seed()
        component = next(iter(get_tree(expected[2]["documentTree"])["components"].values()))
        for force in (False, True):
            with self.subTest(force=force):
                remove_entry("document", expected[3])
                path = object_path(component["brep"])
                original = path.read_bytes()
                path.write_bytes(b"corrupt component, no document index")
                with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
                    repaired = self.build(force=force)
                raw.assert_called_once()
                self.assert_same_document(expected, repaired)
                self.assertEqual(path.read_bytes(), original)

    def test_cache_snapshot_repairs_entire_closure_deleted_or_damaged_after_lookup(self):
        from cadgen._internal import step_scene_package
        from cadgen.store.objects import object_path, read_verified_object
        from cadgen.store.trees import tree_objects

        expected = self.seed()
        captured = {digest: read_verified_object(digest) for digest in tree_objects(expected[2]["documentTree"])}
        original = step_scene_package._lookup_document_readback

        for damage in ("missing", "mismatched"):
            with self.subTest(damage=damage):
                def damage_after_lookup(*args, **kwargs):
                    result = original(*args, **kwargs)
                    self.assertIsNotNone(result[0])
                    for digest in captured:
                        if damage == "missing":
                            object_path(digest).unlink()
                        else:
                            object_path(digest).write_bytes(b"damage after verified capture")
                    return result

                with mock.patch.object(step_scene_package, "_lookup_document_readback", side_effect=damage_after_lookup), \
                        mock.patch("cadgen.store.build._publish_document_scene", side_effect=AssertionError("lost original canonical identity")), \
                        mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("verified snapshot was lost")):
                    repaired = self.build()
                self.assert_same_document(expected, repaired)
                self.assertEqual({digest: read_verified_object(digest) for digest in captured}, captured)

    def test_linked_tree_is_rejected_before_flattening(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.objects import put_object
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree

        expected = self.seed()
        bad_tree = get_tree(expected[2]["documentTree"])
        bad_tree["links"] = [{"id": "o1.1", "tree": expected[0]}]
        # Deliberately malformed input bypasses the strict tree writer.
        note_document_tree(expected[3], put_object(json.dumps(bad_tree).encode()))
        with mock.patch("cadgen.store.trees.flatten_tree", side_effect=AssertionError("linked document flattened")):
            self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[3]))

    def test_honestly_hashed_invalid_native_recipe_and_eager_inputs_cannot_reuse_identity(self):
        from cadgen._internal import component_package as cp, step_scene_package
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store import surfaces
        from cadgen.store.build import _publish_document_scene
        from cadgen.store.objects import put_object, read_verified_object
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import get_tree

        expected = self.seed()
        tree_hash = expected[2]["documentTree"]
        surface = next(iter(surfaces.derive(tree_hash).values()))["object"]
        for mode in ("unreadable-native", "absent-face", "eager-only", "singular-placement"):
            with self.subTest(mode=mode):
                tree = get_tree(tree_hash)
                cid, entry = next(iter(tree["components"].items()))
                payload = read_verified_object(entry["brep"])
                if mode == "unreadable-native":
                    payload = cp._BREP_HEADERS[entry["codec"]] + b"honestly hashed invalid native input"
                    entry["brep"] = put_object(payload)
                elif mode == "absent-face":
                    entry["faceColors"]["999"] = [1., 0., 0., 1.]
                elif mode == "eager-only":
                    entry.update(kind="eager-only", eagerSurface=surface)
                else:
                    tree["occurrences"][0]["transform"][:12] = [0.] * 12
                entry["contentHash"] = cp.geometry_component_hash(
                    entry["codec"], payload, entry["faceColors"], kind=entry["kind"],
                    eager_surface=entry.get("eagerSurface"),
                )
                new_cid = entry["contentHash"][:16]
                tree["components"] = {new_cid: entry}
                for row in tree["occurrences"]:
                    if row["component"] == cid:
                        row["component"] = new_cid
                bad_hash = put_object(cp.canonical_json_bytes(tree))
                note_document_tree(expected[3], bad_hash)
                with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw, \
                        mock.patch.object(step_scene_package, "_scene_from_selected_bytes",
                                          wraps=step_scene_package._scene_from_selected_bytes) as exact_raw, \
                        mock.patch("cadgen.store.build._publish_document_scene", wraps=_publish_document_scene) as derived:
                    actual = self.build()
                self.assertEqual(raw.call_count + exact_raw.call_count, 1)
                derived.assert_called_once()
                self.assert_same_document(expected, actual)
                self.assertNotEqual(actual[2]["documentTree"], bad_hash)
                note_document_tree(expected[3], tree_hash)

    def test_deleted_asset_between_tree_and_component_reads_reparses(self):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store import objects, trees

        expected = self.seed()
        tree_hash = expected[2]["documentTree"]
        brep = next(iter(trees.get_tree(tree_hash)["components"].values()))["brep"]
        original = trees.read_verified_object
        deleted = False

        def delete_after_tree(digest):
            nonlocal deleted
            data = original(digest)
            if digest == tree_hash and not deleted:
                objects.object_path(brep).unlink(missing_ok=True)
                deleted = True
            return data

        with mock.patch.object(trees, "read_verified_object", side_effect=delete_after_tree), \
                mock.patch("cadgen._internal.step_scene_loader.load_step_scene", wraps=load_step_scene) as raw:
            repaired = self.build()
        self.assertTrue(deleted)
        raw.assert_called_once()
        self.assert_same_document(expected, repaired)

    def test_cached_placement_and_face_color_correspondence_checks_still_run(self):
        from build123d import Compound
        from cadgen._internal import step_scene_package

        shape = Compound(children=[self.shape()], label="root")
        self.seed(shape)
        original = step_scene_package._lookup_document_readback

        def changed_placement(*args, **kwargs):
            readback, repair = original(*args, **kwargs)
            scene = readback.scene
            leaf = scene.roots[0]
            while leaf.children:
                leaf = leaf.children[0]
            transform = list(leaf.transform)
            transform[3] += 1
            leaf.transform = tuple(transform)
            return readback, repair

        with mock.patch.object(step_scene_package, "_lookup_document_readback", side_effect=changed_placement):
            with self.assertRaisesRegex(RuntimeError, "placement"):
                self.build(shape)

        def missing_colors(*args, **kwargs):
            readback, repair = original(*args, **kwargs)
            scene = readback.scene
            scene.prototype_face_colors.clear()
            return readback, repair

        with mock.patch.object(step_scene_package, "_lookup_document_readback", side_effect=missing_colors):
            with self.assertRaisesRegex(RuntimeError, "per-face colours"):
                self.build(shape)

        def wrong_product_name(*args, **kwargs):
            readback, repair = original(*args, **kwargs)
            readback.scene.roots[0].name = "wrong hierarchy"
            return readback, repair

        with mock.patch.object(step_scene_package, "_lookup_document_readback", side_effect=wrong_product_name), \
                mock.patch.object(step_scene_package._DocumentReadback, "restore",
                                  side_effect=AssertionError("published before correspondence")):
            with self.assertRaisesRegex(RuntimeError, "STEP correspondence.*name changed"):
                self.build(shape)

    def test_saved_reader_repairs_corrupt_objects_without_code_index_reads(self):
        import cadgen

        expected = self.seed()
        guard_root = self.root / "reader-guard"
        guard_root.mkdir()
        # The real transient compile process inherits this guard. Historical
        # compile bookkeeping may be written, but no reader can consult it.
        (guard_root / "sitecustomize.py").write_text(textwrap.dedent("""\
            import os
            import sys
            root = os.path.abspath(os.environ["CADGEN_CACHE_DIR"])
            forbidden = tuple(os.path.join(root, "index", kind) for kind in ("model", "output"))
            def guard(event, args):
                if event not in {"open", "os.listdir", "os.scandir"} or not args:
                    return
                if not isinstance(args[0], (str, bytes)):
                    return
                path = os.path.abspath(os.fsdecode(args[0]))
                write_only = (event == "open" and len(args) > 2 and isinstance(args[2], int)
                              and args[2] & (os.O_WRONLY | os.O_RDWR) == os.O_WRONLY)
                if not write_only and any(path == prefix or path.startswith(prefix + os.sep) for prefix in forbidden):
                    raise AssertionError("saved reader read code index: " + path)
            sys.addaudithook(guard)
            sys._cadgen_saved_reader_guard = True
            """), encoding="utf-8")
        script = textwrap.dedent("""\
            import hashlib
            import json
            import sys
            from pathlib import Path
            from unittest import mock
            from cadgen._internal.component_package import _BREP_HEADERS, geometry_component_hash
            from cadgen._internal.step_scene_package import load_step_scene_cached
            from cadgen.daemon import executors
            from cadgen.step import compile
            from cadgen.store.index import write_entry
            from cadgen.store.objects import object_path, put_object, read_verified_object
            from cadgen.store.records import note_document_tree, tree_for_document_hash
            from cadgen.store.trees import get_tree, tree_objects

            assert sys._cadgen_saved_reader_guard
            step = Path(sys.argv[1])
            step_hash, tree_hash = sys.argv[2:4]
            saved_bytes = step.read_bytes()
            original = {digest: read_verified_object(digest) for digest in tree_objects(tree_hash)}
            component = next(iter(get_tree(tree_hash)["components"].values()))
            cases = []
            for kind, digest in (("tree", tree_hash), ("brep", component["brep"])):
                object_path(digest).write_bytes(b"damaged derived object")
                with mock.patch.object(executors, "submit_compile", wraps=executors.submit_compile) as submitted:
                    scene = load_step_scene_cached(step)
                assert submitted.call_count == 1, (kind, submitted.call_count)
                assert scene.step_hash == step_hash
                assert tree_for_document_hash(step_hash) == tree_hash
                assert all(read_verified_object(key) == data for key, data in original.items())
                assert step.read_bytes() == saved_bytes
                cases.append(kind)
            # Byte integrity and a matching codec header cannot certify native
            # validity. Use an honestly hashed malformed BREP/tree to prove the
            # reader carries its failed native verdict into compilation.
            bad_tree = get_tree(tree_hash)
            old_cid = next(iter(bad_tree["components"]))
            bad_component = bad_tree["components"].pop(old_cid)
            malformed = _BREP_HEADERS[bad_component["codec"]] + b"not a native shape"
            bad_component["brep"] = put_object(malformed)
            bad_component["contentHash"] = geometry_component_hash(
                bad_component["codec"], malformed, bad_component["faceColors"])
            cid = bad_component["contentHash"][:16]
            bad_tree["components"][cid] = bad_component
            for occurrence in bad_tree["occurrences"]:
                if occurrence["component"] == old_cid:
                    occurrence["component"] = cid
            write_entry("component", cid, {"schemaVersion": 1, **bad_component})
            note_document_tree(step_hash, put_object(json.dumps(bad_tree).encode()))
            with mock.patch.object(executors, "submit_compile", wraps=executors.submit_compile) as submitted:
                assert load_step_scene_cached(step).step_hash == step_hash
            assert submitted.call_count == 1
            assert submitted.call_args.kwargs["force"] is True
            assert tree_for_document_hash(step_hash) == tree_hash
            assert all(read_verified_object(key) == data for key, data in original.items())
            cases.append("unreadable-brep")
            # Force also bypasses a present document index and repairs existing
            # corrupt component bytes instead of an idempotent write keeping them.
            object_path(component["brep"]).write_bytes(b"force must repair this")
            result = compile(step, force=True)
            assert result.ok and not result.skipped
            assert result.tree == tree_hash
            assert all(read_verified_object(key) == data for key, data in original.items())
            # A healthy saved read retains its no-compile path after repair.
            with mock.patch.object(executors, "submit_compile", side_effect=AssertionError("healthy read compiled")):
                assert load_step_scene_cached(step).step_hash == step_hash
            assert hashlib.sha256(step.read_bytes()).hexdigest() == step_hash
            print(json.dumps({"repaired": cases, "forced": True, "codeIndexReadsForbidden": True}))
            """)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("CADGEN_")}
        environment.update({
            "CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0",
            "CADGEN_JOBS": "1", "CADGEN_COMPONENT_WORKERS": "1",
            "PYTHONPATH": os.pathsep.join([str(guard_root), str(Path(cadgen.__file__).resolve().parent.parent)]),
        })
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.root / "part.step"), expected[3], expected[2]["documentTree"]],
            cwd=self.root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1]), {
            "repaired": ["tree", "brep", "unreadable-brep"],
            "forced": True, "codeIndexReadsForbidden": True,
        })


class NativePlacementValidationTest(unittest.TestCase):
    def setUp(self):
        # Finish provider imports before replacing gp_Trsf, so a lazy import
        # cannot retain the test's fake constructor after the patch ends.
        __import__("build123d")

    def test_construction_error_without_standard_failure_parent_repairs_saved_readback(self):
        from OCP import Standard, gp
        from cadgen._internal import step_scene_package
        from cadgen.store.materialize import _location_from_matrix

        # Some OCP wheels register this directly under Exception rather than
        # Standard_Failure. The actual zero-determinant fixture above must get
        # the same saved-byte repair path with either binding hierarchy.
        class ConstructionError(Exception):
            pass

        failure = ConstructionError("gp_Trsf::SetValues, null determinant")
        transform = mock.Mock()
        transform.SetValues.side_effect = failure
        matrix = [0.] * 12 + [0., 0., 0., 1.]
        with mock.patch.object(Standard, "Standard_ConstructionError", ConstructionError), \
                mock.patch.object(gp, "gp_Trsf", return_value=transform):
            with self.assertRaisesRegex(ValueError, "invalid geometry transform") as raised:
                _location_from_matrix(matrix)
            self.assertIs(raised.exception.__cause__, failure)
            with mock.patch("cadgen.store.records.tree_for_document_hash", return_value="a" * 64), \
                    mock.patch.object(step_scene_package, "_readback_from_document_tree",
                                      side_effect=lambda *args, **kwargs: _location_from_matrix(matrix)):
                self.assertEqual(
                    step_scene_package._lookup_document_readback(Path("unused.step"), step_hash="b" * 64),
                    (None, True),
                )

    def test_unrelated_native_conversion_failures_propagate(self):
        from OCP import gp
        from cadgen.store.materialize import _location_from_matrix

        for failure in (MemoryError("allocation"), SystemExit(17), KeyboardInterrupt(), RuntimeError("unexpected")):
            with self.subTest(error=type(failure).__name__):
                transform = mock.Mock()
                transform.SetValues.side_effect = failure
                with mock.patch.object(gp, "gp_Trsf", return_value=transform), \
                        self.assertRaises(type(failure)) as raised:
                    _location_from_matrix([0.] * 12)
                self.assertIs(raised.exception, failure)


class ObjectRepairTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="object-repair-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        environment.start()
        self.addCleanup(environment.stop)

    def test_opt_in_repair_keeps_valid_objects_untouched_and_repairs_known_bytes(self):
        from cadgen.store import objects

        payload = b"known exact object bytes"
        digest = objects.put_object(payload)
        path = objects.object_path(digest)
        source = self.root / "source.bin"
        source.write_bytes(payload)
        original_stat = path.stat()
        with mock.patch.object(objects, "replace_atomic", side_effect=AssertionError("rewrote valid object")):
            self.assertEqual(objects.put_object(payload, repair=True), digest)
            self.assertEqual(objects.put_object_from_file(source, repair=True), digest)
        self.assertEqual(path.stat().st_mtime_ns, original_stat.st_mtime_ns)
        for writer in (lambda: objects.put_object(payload, repair=True),
                       lambda: objects.put_object_from_file(source, repair=True)):
            path.write_bytes(b"corrupt bytes")
            # Normal idempotent writes remain unchanged; recovery is explicit.
            self.assertEqual(objects.put_object(payload), digest)
            self.assertEqual(path.read_bytes(), b"corrupt bytes")
            self.assertEqual(writer(), digest)
            self.assertEqual(path.read_bytes(), payload)

    def test_two_repair_writers_never_remove_each_others_valid_object(self):
        from concurrent.futures import ThreadPoolExecutor
        from cadgen.store import objects

        payload = b"same expected bytes in both repairing writers"
        digest = objects.put_object(payload)
        path = objects.object_path(digest)
        path.write_bytes(b"corrupt bytes")
        barrier = threading.Barrier(2)
        original = objects._object_matches
        original_replace = objects.replace_atomic
        original_unlink = Path.unlink
        observation_lock = threading.Lock()
        publication_lock = threading.Lock()
        observations = 0
        published = False

        def both_observe_damage(target, expected):
            nonlocal observations
            matches = original(target, expected)
            if target == path:
                with observation_lock:
                    observations += 1
                    initial = observations <= 2
                if initial:
                    barrier.wait(timeout=5)
            return matches

        def deny_the_losing_writer(temp, target):
            nonlocal published
            with publication_lock:
                if not published:
                    original_replace(temp, target)
                    published = True
                    return
            raise PermissionError(5, "destination was just replaced", str(target))

        def keep_the_canonical_object(candidate, *args, **kwargs):
            if candidate == path:
                raise AssertionError("repair unlinked the canonical object")
            return original_unlink(candidate, *args, **kwargs)

        with mock.patch.object(objects, "_object_matches", side_effect=both_observe_damage), \
                mock.patch.object(objects, "replace_atomic", side_effect=deny_the_losing_writer), \
                mock.patch.object(Path, "unlink", autospec=True, side_effect=keep_the_canonical_object), \
                ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(objects.put_object, payload, repair=True) for _ in range(2)]
            self.assertEqual([future.result(timeout=5) for future in futures], [digest, digest])
        self.assertEqual(path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
