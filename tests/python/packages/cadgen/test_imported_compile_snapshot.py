"""Imported currency checks keep one verified, call-local document selection."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


class ImportedCompileSnapshot(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="imported-compile-snapshot-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
        }))

    def document(self, name="part", *, assembly=False, width=2):
        from build123d import Compound, Location, Solid
        from cadgen.step_export import export_build123d_step_file

        shape = Solid.make_box(width, 3, 4)
        shape.label = "box"
        if assembly:
            second = Solid.make_box(1, 2, 3).moved(Location((8, 0, 0)))
            second.label = "second"
            shape = Compound(children=[shape, second], label="two boxes")
        path = self.root / f"{name}.step"
        export_build123d_step_file(shape, path)
        return path

    def compile(self, document, **kwargs):
        from cadgen.step_artifact_cli import build_step_artifact

        return build_step_artifact(repo_root=self.root, step=document, **kwargs)

    def spec(self, document):
        from cadgen._internal.generation import EntrySpec

        return EntrySpec(source_ref=document.name, cad_ref=document.stem,
                         source_path=document, display_name=document.stem,
                         source="imported", step_path=document)

    def test_hit_captures_once_without_source_surface_or_native_work(self):
        from cadgen import catalog, step_artifact_cli as artifact
        from cadgen._internal import component_package, surface_extract
        from cadgen.store import trees

        document = self.document()
        first = self.compile(document)
        expected_kind = trees.tree_kind_for(first["tree"])
        expected_stats = trees.capture_tree(first["tree"], retain_payloads=False)[0]["stats"]
        forbidden = AssertionError("imported hit did extra work")
        with mock.patch.object(trees, "capture_tree", wraps=trees.capture_tree) as capture, \
             mock.patch.object(artifact, "iter_cad_sources", side_effect=forbidden), \
             mock.patch.object(artifact, "load_step_scene_exact", side_effect=forbidden), \
             mock.patch.object(component_package, "decode_geometry_component", side_effect=forbidden), \
             mock.patch.object(surface_extract, "extract_surface_component", side_effect=forbidden), \
             mock.patch.object(catalog, "result_tree_for", side_effect=forbidden), \
             mock.patch.object(trees, "tree_kind_for", side_effect=forbidden):
            current = self.compile(document)
        capture.assert_called_once_with(first["tree"], retain_payloads=False)
        self.assertTrue(current["skipped"])
        self.assertEqual(current["tree"], first["tree"])
        self.assertEqual(current["stats"], expected_stats)
        self.assertEqual(current["entryKind"], expected_kind)
        self.assertFalse((self.root / "store/index/surface").exists())

    def test_edge_policy_well_formedness_gate_remains(self):
        from cadgen import step_artifact_cli as artifact
        from cadgen.store import trees

        document = self.document()
        tree = self.compile(document)["tree"]
        metadata, _ = trees.capture_tree(tree, retain_payloads=False)
        metadata.pop("edgeRendering", None)
        with mock.patch.object(trees, "capture_tree", return_value=(metadata, {})):
            self.assertIsNone(artifact._current_artifact_for_spec(self.spec(document)))

    def test_each_call_rejects_missing_or_corrupt_transitive_geometry(self):
        from cadgen import catalog, step_artifact_cli as artifact
        from cadgen.store import trees
        from cadgen.store.objects import object_path

        document = self.document()
        child = self.compile(document)["tree"]
        child_tree = trees.get_tree(child)
        child_brep = next(iter(child_tree["components"].values()))["brep"]
        parent = trees.put_tree({
            "units": "mm", "entryKind": "assembly", "components": {}, "occurrences": [],
            "edgeRendering": child_tree["edgeRendering"],
            "links": [{"id": "o1.1", "name": "linked", "tree": child,
                       "transform": list(trees.IDENTITY_16)}],
            "assembly": {"root": {"id": "o1", "nodeType": "assembly", "children": [
                {"id": "o1.1", "nodeType": "link", "children": []}],
            }},
        })
        selected = (hashlib.sha256(document.read_bytes()).hexdigest(), parent)
        with mock.patch.object(catalog, "result_snapshot_for", return_value=selected):
            initial = artifact._current_artifact_for_spec(self.spec(document))
            self.assertEqual(initial.kind, "assembly")  # One linked part is still an assembly.
            for digest in (child, child_brep):
                path = object_path(digest)
                original = path.read_bytes()
                for damaged in (None, b"corrupt required geometry"):
                    with self.subTest(digest=digest, missing=damaged is None):
                        if damaged is None:
                            path.unlink()
                        else:
                            path.write_bytes(damaged)
                        try:
                            self.assertIsNone(artifact._current_artifact_for_spec(self.spec(document)))
                        finally:
                            path.write_bytes(original)
                        repaired = artifact._current_artifact_for_spec(self.spec(document))
                        self.assertEqual(repaired.tree, parent)

    def test_result_uses_selected_tree_and_owned_metadata_without_relookup(self):
        from cadgen import catalog, step_artifact_cli as artifact
        from cadgen._internal import source_sidecar
        from cadgen.store import trees

        document = self.document(assembly=True)
        first = self.compile(document)
        spec = self.spec(document)
        current = artifact._current_artifact_for_spec(spec)
        forbidden = AssertionError("result reselected the document or reopened geometry")
        with mock.patch.object(catalog, "result_snapshot_for", side_effect=forbidden), \
             mock.patch.object(catalog, "result_tree_for", side_effect=forbidden), \
             mock.patch.object(trees, "capture_tree", side_effect=forbidden), \
             mock.patch.object(trees, "tree_kind_for", side_effect=forbidden), \
             mock.patch.object(source_sidecar, "read_source_sidecar", wraps=source_sidecar.read_source_sidecar) as sidecar:
            payload = artifact._existing_result_payload(spec, current)
        sidecar.assert_called_once_with(document, document_hash=current.document_hash)
        self.assertEqual(payload["tree"], first["tree"])
        self.assertEqual(payload["entryKind"], "assembly")
        self.assertEqual(payload["stats"], current.manifest["stats"])

    def test_document_replacement_after_capture_falls_through_to_normal_compile(self):
        from cadgen import step_artifact_cli as artifact
        from cadgen.store import trees

        document = self.document("selected")
        first = self.compile(document)
        replacement = self.document("replacement", assembly=True, width=5).read_bytes()
        capture = trees.capture_tree
        replaced = False

        def capture_then_replace(*args, **kwargs):
            nonlocal replaced
            result = capture(*args, **kwargs)
            if not replaced:
                document.write_bytes(replacement)
                replaced = True
            return result

        with mock.patch.object(trees, "capture_tree", side_effect=capture_then_replace), \
             mock.patch.object(artifact, "load_step_scene_exact", wraps=artifact.load_step_scene_exact) as loaded:
            actual = self.compile(document)
        self.assertTrue(replaced)
        loaded.assert_called_once_with(document)
        self.assertNotEqual(actual["tree"], first["tree"])
        self.assertEqual(actual["entryKind"], "assembly")
        self.assertFalse(actual.get("skipped", False))
        self.assertEqual(document.read_bytes(), replacement)
        self.assertEqual(self.compile(document)["tree"], actual["tree"])

    def test_generated_currency_gates_and_artifact_type_are_unchanged(self):
        from cadgen import catalog, step_artifact_cli as artifact
        from cadgen.step_targets import StepTopologyArtifact
        from cadgen.store import trees

        document = self.document()
        tree = self.compile(document)["tree"]
        spec = replace(self.spec(document), source="generated")
        gates = ("_existing_topology_artifact_matches_spec_without_scene",
                 "_generated_assembly_glb_closure_current", "_assembly_glb_package_current")
        for failure in (*range(len(gates)), None):
            with self.subTest(failure=failure):
                import contextlib

                calls = []
                with contextlib.ExitStack() as stack:
                    for index, name in enumerate(gates):
                        def gate(value, *, index=index, name=name):
                            self.assertIs(value, spec)
                            calls.append(name)
                            return index != failure
                        stack.enter_context(mock.patch.object(artifact, name, side_effect=gate))
                    capture = stack.enter_context(mock.patch.object(trees, "capture_tree", wraps=trees.capture_tree))
                    result = artifact._current_artifact_for_spec(spec)
                self.assertEqual(calls, list(gates if failure is None else gates[:failure + 1]))
                if failure is None:
                    self.assertIs(type(result), StepTopologyArtifact)
                    capture.assert_called_once_with(tree)
                    with mock.patch.object(catalog, "result_tree_for", wraps=catalog.result_tree_for) as lookup:
                        payload = artifact._existing_result_payload(spec, result)
                    lookup.assert_called_once_with(spec.entry_path)
                    self.assertEqual(payload["tree"], tree)
                else:
                    self.assertIsNone(result)
                    capture.assert_not_called()

    def test_current_generated_compile_still_heals_declared_export(self):
        from cadgen.step_artifact_cli import build_step_artifact

        script = self.root / "declared.py"
        script.write_text(
            "from cadgen import step, stl\n"
            "from build123d import Solid\n"
            "@step\n@stl\n"
            "def declared():\n    return Solid.make_box(1, 2, 3)\n",
            encoding="utf-8",
        )
        document = script.with_suffix(".step")
        exported = script.with_suffix(".stl")
        first = build_step_artifact(repo_root=self.root, step=document, source_path=script)
        original = exported.read_bytes()
        exported.unlink()
        healed = build_step_artifact(repo_root=self.root, step=document, source_path=script)
        self.assertEqual(exported.read_bytes(), original)
        self.assertEqual(healed["tree"], first["tree"])


if __name__ == "__main__":
    unittest.main()
