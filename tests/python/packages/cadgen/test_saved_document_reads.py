"""A saved document's readers take the tree its bytes map to, privately, and never one
that does not read: a damaged or invalid tree is compiled again from the file's own bytes,
and a build of the model writes its own objects again. A saved file holds its result
where its verify says so."""

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

from tests.python.support.documents import assert_same_document, save_step
from tests.python.support.tmp_root import generated_cad_directory


class SavedDocumentReadTest(unittest.TestCase):
    def setUp(self):
        scratch = generated_cad_directory(prefix="saved-document-reads-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"),
                                                   "CADGEN_DAEMON": "0"})
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
        """``(tree, digest)`` of the model's save, its file verified as its result. One part
        is its document, named by its label (``generation._document_root_name``)."""
        tree_hash, _tree, stats, digest = save_step(
            self.shape() if shape is None else shape, self.root / "part.step", root_name="part",
            force=force, materials=materials,
        )
        self.assertEqual({"ok": True}, stats["verify"])
        return tree_hash, digest

    def test_a_saved_read_has_private_geometry(self):
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from cadgen._internal.step_scene_package import scene_from_render_package

        expected = self.build()

        def first_vertex(scene):
            return TopoDS.Vertex_s(TopExp_Explorer(next(iter(scene.prototype_shapes.values())), TopAbs_VERTEX).Current())

        cached = scene_from_render_package(self.root / "part.step", step_hash=expected[1])
        BRep_Builder().UpdateVertex(first_vertex(cached), gp_Pnt(50, 60, 70), 1e-7)
        again = scene_from_render_package(self.root / "part.step", step_hash=expected[1])
        self.assertNotEqual(BRep_Tool.Pnt_s(first_vertex(again)).Coord(), (50.0, 60.0, 70.0))
        self.assertEqual(expected, self.build())
        self.assertEqual(expected, self.build(force=True))

    def test_saved_bytes_move_exactly_with_the_document(self):
        """A finish rides the sidecar, never the file, so it never moves the saved bytes;
        geometry, a member's name or a placement does."""
        from build123d import Compound, Location, Solid

        def assembly(size=2, name="b", offset=10):
            box = Solid.make_box(size, 3, 4)
            box.label, box.color = "a", (.8, .1, .1, 1)
            pin = Solid.make_cylinder(1, 5).moved(Location((offset, 0, 0)))
            pin.label = name
            return Compound(children=[box, pin], label="root")

        def finish(metalness):
            return {"definitions": {"steel": {"name": "Steel", "metalness": metalness, "roughness": .3}},
                    "assignments": [{"targets": ["#a"], "material": "steel"}]}

        def written(tag, shape, materials=None):
            return save_step(shape, self.root / tag / "part.step", root_name="root", materials=materials)[3]

        base = written("base", assembly(), finish(1))
        for case, other, same in (
            ("finish", written("finish", assembly(), finish(.5)), True),
            ("geometry", written("geometry", assembly(size=3), finish(1)), False),
            ("member name", written("name", assembly(name="c"), finish(1)), False),
            ("placement", written("placement", assembly(offset=11), finish(1)), False),
        ):
            with self.subTest(case):
                self.assertEqual(other == base, same)

    def test_a_sidecar_with_unchanged_bytes_keeps_its_file(self):
        # A viewer versions the sidecar by its file stamp, so rewriting the same bytes (a label
        # edit whose document is kept) would reload the model for nothing.
        from cadgen._internal.generation import _publish_sidecar

        staged, saved = self.root / "stage" / "part.step", self.root / "saved" / "part.step"
        staged_sidecar, saved_sidecar = (path.with_name("part.step.json") for path in (staged, saved))
        for sidecar in (staged_sidecar, saved_sidecar):
            sidecar.parent.mkdir()
            sidecar.write_bytes(b'{"documentHash": "same"}')
        before = os.stat(saved_sidecar)
        _publish_sidecar(staged, saved)
        after = os.stat(saved_sidecar)
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))
        staged_sidecar.write_bytes(b'{"documentHash": "new"}')
        _publish_sidecar(staged, saved)
        self.assertEqual(saved_sidecar.read_bytes(), b'{"documentHash": "new"}')
        self.assertFalse(staged_sidecar.exists(), "a changed sidecar is moved into place")
        _publish_sidecar(staged, saved)
        self.assertFalse(saved_sidecar.exists(), "a build that stages no sidecar removes the saved one")

    def test_bytes_no_entry_maps_read_as_their_own_even_beside_a_record(self):
        from cadgen._internal.step_scene_package import load_step_scene_cached
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.exports import export_step
        from cadgen.store.records import note_output, tree_for_document_hash, write_record

        old = self.build()
        source = self.root / "removed-source.py"
        write_record(source, {"tree": old[0], "outputs": {str(self.root / "part.step"): {"sha256": old[1]}}})
        note_output(self.root / "part.step", source)
        changed, _, _ = build_tree_from_compound(self.shape(5), root_name="part")
        written = export_step(changed, self.root / "part.step")["sha256"]
        self.assertIsNone(tree_for_document_hash(written))
        self.assertEqual(load_step_scene_cached(self.root / "part.step").step_hash, written)
        self.assertNotIn(tree_for_document_hash(written), (None, old[0], changed))

    def test_generic_publication_derives_mutated_scene_despite_matching_document_digest(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.build import build_document_tree
        from cadgen.store.records import tree_for_document_hash

        expected = self.build()
        scene = scene_from_render_package(self.root / "part.step", step_hash=expected[1])
        original = (self.root / "part.step").read_bytes()
        key = next(iter(scene.prototype_shapes))
        scene.prototype_shapes[key] = self.shape(9).wrapped
        scene.prototype_face_colors.clear()
        scene.roots[0].name = "changed public scene"
        # Public hashes and invented attestation attributes cannot grant reuse.
        scene.document_tree = expected[0]
        changed_hash, changed_tree, _ = build_document_tree(scene)
        self.assertNotEqual(changed_hash, expected[0])
        self.assertEqual(changed_tree["label"], "changed public scene")
        self.assertEqual(scene.step_hash, expected[1])
        self.assertEqual(tree_for_document_hash(expected[1]), expected[0])
        self.assertEqual((self.root / "part.step").read_bytes(), original)

    def test_nested_located_root_and_repeated_prototypes_keep_names_placements_and_colors(self):
        from build123d import Compound, Location
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.build import build_document_tree
        from cadgen.store.trees import flatten

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
        expected = self.build(shape, materials=materials)
        self.assertEqual(expected, self.build(shape, force=True, materials=materials))
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "cold-store")}):
            _, cold, _ = build_document_tree(load_step_scene(self.root / "part.step"))
        assert_same_document(self, flatten(expected[0]), cold)

    def test_missing_or_digest_mismatched_objects_are_written_again_by_the_next_build(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store.objects import object_hash, object_path
        from cadgen.store.trees import get_tree, tree_objects

        expected = self.build()
        component = next(iter(get_tree(expected[0])["components"].values()))
        original = {digest: object_path(digest).read_bytes() for digest in tree_objects(expected[0])}
        for kind, digest in (("tree", expected[0]), ("brep", component["brep"])):
            for damage in ("missing", "mismatched"):
                with self.subTest(kind=kind, damage=damage):
                    path = object_path(digest)
                    if damage == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(b"damaged object")
                    self.assertIsNone(scene_from_render_package(self.root / "part.step", step_hash=expected[1]))
                    # The build owns the exact bytes of everything it publishes.
                    self.assertEqual(expected, self.build())
                    for object_digest, payload in original.items():
                        self.assertEqual(object_path(object_digest).read_bytes(), payload)
                        self.assertEqual(object_hash(payload), object_digest)
                    self.assertIsNotNone(scene_from_render_package(self.root / "part.step", step_hash=expected[1]))

    def test_missing_or_unreadable_display_data_never_blocks_native_face_colors(self):
        from cadgen._internal.step_scene_package import scene_from_render_package
        from cadgen.store import parts
        from cadgen.store.index import write_entry
        from cadgen.store.objects import object_path, put_object
        from cadgen.store.trees import get_tree

        expected = self.build()
        tree = expected[0]
        components = get_tree(tree)["components"]
        expected_colors = sorted(tuple(color) for entry in components.values()
                                 for color in entry["faceColors"].values())
        cid, record = next(iter(parts.derive(tree).items()))
        key = parts.part_key(components[cid], parts.producer_identity())
        payloads = {role: object_path(record[role]["object"]).read_bytes() for role in ("glb", "selectors")}
        for damage in ("missing", "digest-mismatched", "hash-valid-unreadable"):
            with self.subTest(damage=damage):
                for payload in payloads.values():
                    put_object(payload, repair=True)
                write_entry("part", key, record)
                if damage == "missing":
                    object_path(record["glb"]["object"]).unlink()
                elif damage == "digest-mismatched":
                    object_path(record["selectors"]["object"]).write_bytes(b"corrupt selector table")
                else:
                    write_entry("part", key, {
                        **record, "glb": {**record["glb"], "object": put_object(b"hash-valid unreadable mesh")},
                    })
                with mock.patch("cadgen._internal.step_scene_loader.load_step_scene", side_effect=AssertionError("native hit parsed STEP")), \
                        mock.patch("cadgen._internal.topology_extract.extract_topology_facts", side_effect=AssertionError("native read extracted topology facts")):
                    scene = scene_from_render_package(self.root / "part.step", step_hash=expected[1])
                    self.assertIsNotNone(scene)
                    actual_colors = sorted(color for recipe in scene.prototype_face_colors.values()
                                           for color in recipe.values())
                    self.assertEqual(actual_colors, expected_colors)
                self.assertEqual(expected, self.build())

    def test_absent_document_index_does_not_reuse_damaged_component_objects(self):
        from cadgen.store.index import remove_entry
        from cadgen.store.objects import object_path
        from cadgen.store.records import document_key, tree_for_document_hash
        from cadgen.store.trees import get_tree

        expected = self.build()
        component = next(iter(get_tree(expected[0])["components"].values()))
        for force in (False, True):
            with self.subTest(force=force):
                remove_entry("document", document_key(expected[1]))
                path = object_path(component["brep"])
                original = path.read_bytes()
                path.write_bytes(b"corrupt component, no document index")
                self.assertEqual(expected, self.build(force=force))
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(tree_for_document_hash(expected[1]), expected[0])

    def test_an_invalid_tree_is_never_read_and_the_file_reads_as_its_own(self):
        from cadgen._internal import component_package as cp
        from cadgen._internal.step_scene_package import load_step_scene_cached, lookup_document_scene
        from cadgen.store import parts
        from cadgen.store.objects import put_object, read_verified_object
        from cadgen.store.records import note_document_tree, tree_for_document_hash
        from cadgen.store.trees import capture_tree, get_tree

        expected = self.build()
        native = next(iter(capture_tree(expected[0], retain_payloads=False)[0]["components"].values()))
        from cadgen._internal.topology_facts import topology_facts_bytes
        surface = put_object(topology_facts_bytes(parts._topology(native, parts._decoded(native)[0])))
        for mode in ("unreadable-native", "absent-face", "eager-only", "singular-placement"):
            with self.subTest(mode=mode):
                tree = get_tree(expected[0])
                cid, entry = next(iter(tree["components"].items()))
                payload = read_verified_object(entry["brep"])
                if mode == "unreadable-native":
                    payload = cp._BREP_HEADERS[entry["codec"]] + b"honestly hashed invalid native input"
                    entry["brep"] = put_object(payload)
                elif mode == "absent-face":
                    entry["faceColors"]["999"] = [1., 0., 0., 1.]
                elif mode == "eager-only":
                    entry.update(kind="eager-only", topology=surface)
                else:
                    tree["occurrences"][0]["transform"][:12] = [0.] * 12
                entry["contentHash"] = cp.geometry_component_hash(
                    entry["codec"], payload, entry["faceColors"], kind=entry["kind"],
                    topology=entry.get("topology"),
                )
                new_cid = entry["contentHash"][:16]
                tree["components"] = {new_cid: entry}
                for row in tree["occurrences"]:
                    if row["component"] == cid:
                        row["component"] = new_cid
                bad_hash = put_object(cp.canonical_json_bytes(tree))
                note_document_tree(expected[1], bad_hash)
                scene, damaged = lookup_document_scene(self.root / "part.step", step_hash=expected[1])
                if mode == "eager-only":
                    # A valid eager-only component promises display, not a native codec:
                    # the door reads the file's own bytes.
                    self.assertFalse(damaged)
                    self.assertEqual(scene.prototype_components, {})
                else:
                    self.assertEqual((scene, damaged), (None, True))
                    self.assertEqual(load_step_scene_cached(self.root / "part.step").step_hash, expected[1])
                    self.assertNotIn(tree_for_document_hash(expected[1]), (bad_hash, expected[0]))
                note_document_tree(expected[1], expected[0])

    def test_an_asset_deleted_between_reads_is_damage(self):
        from cadgen._internal.step_scene_package import lookup_document_scene
        from cadgen.store import objects, trees

        expected = self.build()
        brep = next(iter(trees.get_tree(expected[0])["components"].values()))["brep"]
        original = trees.read_verified_object
        deleted = False

        def delete_after_tree(digest):
            nonlocal deleted
            data = original(digest)
            if digest == expected[0] and not deleted:
                objects.object_path(brep).unlink(missing_ok=True)
                deleted = True
            return data

        with mock.patch.object(trees, "read_verified_object", side_effect=delete_after_tree):
            self.assertEqual(lookup_document_scene(self.root / "part.step", step_hash=expected[1]), (None, True))
        self.assertTrue(deleted)
        self.assertEqual(expected, self.build())

    def test_saved_reader_repairs_corrupt_objects_without_code_index_reads(self):
        import cadgen

        expected = self.build()
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
            cases = []
            # A damaged document is compiled again from its bytes, and a second damage, to what
            # that compile wrote, compiles it again, whole. A compile names a file's parts by
            # their geometry, whatever names the file carries, so what is compiled is the
            # file's own tree, not the build's: a ref by name resolves again once the model is
            # built (SavedFileVerifyTest, the names-in-store test).
            compiled, original = None, {}
            for kind in ("tree", "brep"):
                current = tree_for_document_hash(step_hash)
                digest = current if kind == "tree" else next(iter(get_tree(current)["components"].values()))["brep"]
                object_path(digest).write_bytes(b"damaged derived object")
                with mock.patch.object(executors, "submit_compile", wraps=executors.submit_compile) as submitted:
                    scene = load_step_scene_cached(step)
                assert submitted.call_count == 1, (kind, submitted.call_count)
                assert scene.step_hash == step_hash
                if compiled is None:
                    compiled = tree_for_document_hash(step_hash)
                    assert compiled != tree_hash
                    original = {key: read_verified_object(key) for key in tree_objects(compiled)}
                assert tree_for_document_hash(step_hash) == compiled
                assert all(read_verified_object(key) == data for key, data in original.items())
                assert step.read_bytes() == saved_bytes
                cases.append(kind)
            component = next(iter(get_tree(compiled)["components"].values()))
            # Byte integrity and a matching codec header cannot certify native
            # validity. Use an honestly hashed malformed BREP/tree to prove the
            # reader carries its failed native verdict into compilation.
            bad_tree = get_tree(compiled)
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
            assert tree_for_document_hash(step_hash) == compiled
            assert all(read_verified_object(key) == data for key, data in original.items())
            cases.append("unreadable-brep")
            # Force also bypasses a present document index and repairs existing
            # corrupt component bytes instead of an idempotent write keeping them.
            object_path(component["brep"]).write_bytes(b"force must repair this")
            result = compile(step, force=True)
            assert result.ok and not result.skipped
            assert result.tree == compiled
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
            [sys.executable, "-c", script, str(self.root / "part.step"), expected[1], expected[0]],
            cwd=self.root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1]), {
            "repaired": ["tree", "brep", "unreadable-brep"],
            "forced": True, "codeIndexReadsForbidden": True,
        })


class SavedFileVerifyTest(unittest.TestCase):
    """A saved file is its result only where a parse of it verifies as the result, face by
    face and edge by edge within the display tolerance, and drawn in the same colours; a
    file that does not is its own content, and says which occurrences differ."""

    def setUp(self):
        scratch = generated_cad_directory(prefix="saved-file-verify-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"),
                                                   "CADGEN_DAEMON": "0"})
        environment.start()
        self.addCleanup(environment.stop)

    def build(self, shape, name, *, namer=None):
        """The result, the tree its file's bytes map to once verified, and the verify's answer."""
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import get_tree

        tree_hash, tree, stats, digest = save_step(shape, self.root / f"{name}.step", root_name=name, namer=namer)
        entry = document_entry_for_hash(digest)
        return tree_hash, tree, get_tree(entry["tree"]), stats["verify"]

    def test_a_body_the_file_trims_otherwise_is_the_files_own(self):
        """An ellipsoid cap fused with two side boxes: OCCT reads the cap back as its
        complement, with as many faces and the body's box unchanged -- only the cap's
        own box tells (PR #370's lossy translations)."""
        from build123d import Box, Matrix, Pos, Rot, Sphere

        sphere = Rot(90, 0, 0) * Rot(0, 0, -90) * Sphere(1)
        ellipsoid = sphere.transform_geometry(Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0], [0, 0, 1.4, 0], [0, 0, 0, 1]]))
        cap = (Pos(0, 0, 5.4) * ellipsoid) - (Pos(0, 0, 4.15 - 10) * Box(30, 30, 20))
        body = cap + Pos(-5, 0, 5) * Box(1, 6, 10) + Pos(5, 0, 5) * Box(1, 6, 10)
        body.label = "capped"
        _tree_hash, tree, document, verify = self.build(body, "capped")
        [written] = document["occurrences"]
        self.assertNotIn(written["component"], tree["components"], "the file was taken for the result")
        self.assertNotIn("lineage", document["components"][written["component"]])
        self.assertFalse(verify["ok"])
        self.assertTrue(verify["differ"] and all(line.startswith("capped (#") for line in verify["differ"]), verify)

    def test_a_name_resolves_with_the_store_of_the_build_that_wrote_the_file(self):
        """A compile names a file's elements by their geometry, whatever names the file
        carries; a build's names resolve with the store of the build that wrote the file. A
        token copied from a read with another store finds its face by geometry where the
        names are, and a name read with another store says why it does not resolve."""
        import re

        from build123d import Solid

        from cadgen import read_scene
        from cadgen._internal import kernel_memo

        def block():
            return Solid.make_box(4, 3, 2).cut(Solid.make_cylinder(0.5, 9))

        self.addCleanup(kernel_memo.clear)
        with kernel_memo.run(Path(__file__)) as run:
            body = block()
        body.label = "block"
        self.assertEqual({"ok": True}, self.build(body, "block", namer=run)[3])
        named = read_scene(self.root / "block.step")
        [leaf] = named.leaves()
        refs = [face.ref for face in leaf.entities("face")]
        bore = next(ref for ref in refs if "/f:block.make_cylinder1." in ref)
        self.assertEqual(named.resolve(bore).ref, bore)
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "another-store")}):
            elsewhere = read_scene(self.root / "block.step")
            [other] = elsewhere.leaves()
            tokens = [face.ref for face in other.entities("face")]
            with self.assertRaisesRegex(ValueError, "named by their geometry here"):
                elsewhere.resolve(bore)
        self.assertTrue(all(re.fullmatch(r"#o:[0-9a-f]{12}/f:[0-9a-f]{12}", token) for token in tokens), tokens)
        self.assertEqual(sorted(named.resolve(token).ref for token in tokens), sorted(refs))

    def test_screws_made_alike_and_labelled_apart_are_one_product_in_the_file(self):
        """A part is the construction that made it: screws made alike one by one and
        labelled apart are one component placed three times, written as one product with
        an instance per screw, and the file holds that result."""
        import re

        from build123d import Compound, Pos, Solid

        from cadgen._internal import kernel_memo

        def screws():
            made = []
            for index in range(3):
                screw = Solid.make_cylinder(0.5, 2).fuse(Pos(0, 0, 2) * Solid.make_cylinder(1, 0.5))
                screw = Pos(4 * index, 0, 0) * screw
                screw.label = f"screw:{index}"
                made.append(screw)
            return Compound(children=made, label="screws")

        self.addCleanup(kernel_memo.clear)
        with kernel_memo.run(Path(__file__)) as run:
            assembly = screws()
        tree_hash, tree, document, verify = self.build(assembly, "screws", namer=run)
        self.assertEqual(sorted(occurrence["name"] for occurrence in tree["occurrences"]),
                         ["screw:0", "screw:1", "screw:2"])
        [(_cid, entry)] = tree["components"].items()
        self.assertIn("construction", entry)
        step = (self.root / "screws.step").read_text(encoding="utf-8", errors="replace")
        self.assertEqual(len(re.findall(r"= PRODUCT\(", step)), 2, "the assembly and one screw")
        self.assertEqual(({"ok": True}, tree), (verify, document))

    def test_a_placements_colour_read_on_its_faces_is_the_result(self):
        """A coloured compound's colour comes back on each of its faces: drawn alike, the
        file holds the result, coloured as the result's occurrence is."""
        from build123d import Box, Compound, Pos

        panel = Compound(obj=[Box(4, 4, 1), Pos(6, 0, 0) * Box(4, 4, 1)])
        panel.label = "panel"
        panel.color = (0.2, 0.3, 0.4, 1.0)
        _tree_hash, tree, document, verify = self.build(Compound(children=[panel, Pos(0, 9, 0) * Box(2, 2, 2)]),
                                                        "panels")
        self.assertEqual(({"ok": True}, tree), (verify, document))


class NativePlacementValidationTest(unittest.TestCase):
    def setUp(self):
        # Finish provider imports before replacing gp_Trsf, so a lazy import
        # cannot retain the test's fake constructor after the patch ends.
        __import__("build123d")

    def test_construction_error_without_standard_failure_parent_is_damage_a_compile_repairs(self):
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
                    mock.patch.object(step_scene_package, "_scene_from_document_tree",
                                      side_effect=lambda *args, **kwargs: _location_from_matrix(matrix)):
                self.assertEqual(
                    step_scene_package.lookup_document_scene(Path("unused.step"), step_hash="b" * 64),
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
        # Claimed in place for the sweeper's grace window (STORE.md §8), never rewritten.
        self.assertEqual(path.stat().st_ino, original_stat.st_ino)
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
