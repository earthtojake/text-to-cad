"""Export ledgers retain the document selection that supplied their geometry."""

import hashlib
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class MeshDocumentSnapshotTests(unittest.TestCase):
    def test_animation_source_is_pinned_before_mesh_preparation_and_ledgers_those_bytes(self):
        from cadgen import step_export_target as door
        from cadgen._internal.mesh_animation import animation_variant_token, parse_animation_option
        from cadgen._internal.mesh_export import mesh_variant_key
        from cadgen.store.records import document_mesh_sha, note_document_tree

        with generated_cad_directory(prefix="animation-source-snapshot-") as directory:
            root = Path(directory)
            document = root / "arm.step"
            document.write_bytes(b"selected document")
            document_hash = hashlib.sha256(document.read_bytes()).hexdigest()
            from cadgen._internal.source_sidecar import source_sidecar_path, write_source_sidecar
            module = source_sidecar_path(document)
            def write_animation(source):
                write_source_sidecar(document, {"animation": {"language": "javascript", "source": source}})
            before = "export const clips = { show: {duration: 1, update(t,m) {}} };"
            after = before.replace("duration: 1", "duration: 2")
            write_animation(before)
            view = root / "view"
            view.mkdir()
            (view / "assembly.json").write_text(json.dumps({
                "documentHash": document_hash, "components": {}, "occurrences": [],
            }), encoding="utf-8")
            out = root / "arm.glb"
            spec = SimpleNamespace(step_path=document, entry_path=document, color=None, source="imported")
            captured_paths = []

            def prepare(*args, **kwargs):
                write_animation(after)
                return spec, view, None

            def node(argv, **kwargs):
                captured = Path(argv[argv.index("--animation-source") + 1])
                captured_paths.append(captured)
                self.assertEqual(captured.name, module.name)
                self.assertNotEqual(captured, module)
                self.assertEqual(json.loads(module.read_text(encoding="utf-8"))["animation"]["source"], after)
                source = captured.read_text(encoding="utf-8")
                self.assertEqual(source, before)
                # Stand in for the Node loader consuming this exact file.
                out.write_bytes(source.encode("utf-8"))
                return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "store")}), \
                    mock.patch.object(door, "_resolve_mesh_package", side_effect=prepare), \
                    mock.patch.object(door, "_effective_export_tolerances", return_value=(None, None)), \
                    mock.patch("subprocess.run", side_effect=node) as builder:
                note_document_tree(document_hash, "tree-a")
                door.export_cad_target(document, [("glb", out)], animation="show")
                request = parse_animation_option("show")
                key = mesh_variant_key("glb", None, None, animation_key=animation_variant_token(request, before))
                self.assertEqual(document_mesh_sha(document_hash, key), hashlib.sha256(before.encode()).hexdigest())
                self.assertFalse(captured_paths[0].exists(), "private source must be cleaned after Node finishes")
                # Restoring the selected source may reuse only its own output.
                write_animation(before)
                door.export_cad_target(document, [("glb", out)], animation="show")
                self.assertEqual(builder.call_count, 1)
                self.assertEqual(out.read_text(encoding="utf-8"), before)

    def test_snapshot_uses_one_digest_for_its_tree_lookup(self):
        from cadgen.catalog import result_snapshot_for

        with mock.patch("cadgen.catalog.artifact_file_hash", side_effect=["a" * 64, "b" * 64]) as hashed, \
                mock.patch("cadgen.store.records.tree_for_document_hash", return_value="tree-a") as lookup, \
                mock.patch("cadgen.store.objects.has_object", return_value=True):
            self.assertEqual(result_snapshot_for(Path("model.step")), ("a" * 64, "tree-a"))
        hashed.assert_called_once()
        lookup.assert_called_once_with("a" * 64)

    def test_replaced_input_cannot_rekey_an_already_selected_export_view(self):
        from cadgen._internal.mesh_export import MeshExportJob, mesh_variant_key
        from cadgen.cli_logging import CliLogger
        from cadgen.step_export_target import _export_mesh_jobs
        from cadgen.store.records import document_mesh_sha, note_document_tree

        with generated_cad_directory(prefix="mesh-document-snapshot-") as directory:
            root = Path(directory)
            document = root / "model.step"
            old_hash = hashlib.sha256(b"old document").hexdigest()
            document.write_bytes(b"replacement document")
            new_hash = hashlib.sha256(document.read_bytes()).hexdigest()
            view = root / "view"
            view.mkdir()
            (view / "assembly.json").write_text(json.dumps({
                "documentHash": old_hash, "tree": "tree-a", "components": {}, "occurrences": [],
            }), encoding="utf-8")
            out = root / "model.glb"
            spec = SimpleNamespace(step_path=document, entry_path=document, color=None, source="imported")
            job = MeshExportJob("glb", out)

            def write_export(*args, **kwargs):
                out.write_bytes(b"mesh of the selected old document")
                return {"ok": True}

            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "store")}), \
                    mock.patch("cadgen.catalog.artifact_file_hash", side_effect=AssertionError("export rehashed its selected input")), \
                    mock.patch("cadgen.step_export_target.run_mesh_exporter", side_effect=write_export):
                note_document_tree(old_hash, "tree-a")
                note_document_tree(new_hash, "tree-b")
                written, _ = _export_mesh_jobs(spec, view, None, [job], logger=CliLogger("test", verbose=False))
                self.assertEqual(written, {out})
                key = mesh_variant_key("glb", None, None)
                self.assertEqual(document_mesh_sha(old_hash, key), hashlib.sha256(out.read_bytes()).hexdigest())
                self.assertIsNone(document_mesh_sha(new_hash, key))


if __name__ == "__main__":
    unittest.main()
