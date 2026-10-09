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
    def test_animation_keyframes_are_pinned_before_mesh_preparation_and_ledgers_those_bytes(self):
        from cadgen import step_export_target as door
        from cadgen._internal.mesh_animation import animation_variant_token, parse_animation_option
        from cadgen._internal.mesh_export import MeshSource, mesh_variant_key
        from cadgen.store.records import document_mesh_sha, note_document_tree

        with generated_cad_directory(prefix="animation-keyframes-snapshot-") as directory:
            root = Path(directory)
            document = root / "arm.step"
            document.write_bytes(b"selected document")
            document_hash = hashlib.sha256(document.read_bytes()).hexdigest()
            from cadgen._internal.source_sidecar import source_sidecar_path, write_source_sidecar
            sidecar = source_sidecar_path(document)

            def baked(duration):
                return {"clips": [{"id": "show", "label": "show", "duration": duration, "loop": True,
                                   "tracks": [{"targets": ["o1"], "times": [0], "visible": [True]}]}]}

            def write_animation(section):
                write_source_sidecar(document, {"animation": section})

            # What the sampler is handed: canonical JSON of the section, as captured.
            before = json.dumps(baked(1), sort_keys=True, separators=(",", ":"))
            write_animation(baked(1))
            out = root / "arm.glb"
            spec = SimpleNamespace(step_path=document, entry_path=document, color=None, source="imported")

            def prepare(*args, **kwargs):
                # The model rebakes while the export prepares its meshes.
                write_animation(baked(2))
                return spec, MeshSource("tree-a", document_hash)

            def engine(source, jobs, *, animation_source, **kwargs):
                self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8"))["animation"], baked(2))
                self.assertEqual(animation_source.data, before)
                # Stand in for the sampler consuming exactly the captured keyframes.
                out.write_bytes(animation_source.data.encode("utf-8"))
                return {"ok": True, "files": [{"path": str(out), "format": "glb"}]}

            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "store")}), \
                    mock.patch.object(door, "_mesh_package", side_effect=prepare), \
                    mock.patch.object(door, "run_mesh_exporter", side_effect=engine) as exporter:
                note_document_tree(document_hash, "tree-a")
                door.export_cad_target(document, [("glb", out)], animation="show")
                request = parse_animation_option("show")
                key = mesh_variant_key("glb", None, None, animation_key=animation_variant_token(request, before))
                self.assertEqual(document_mesh_sha(document_hash, key), hashlib.sha256(before.encode()).hexdigest())
                # Restoring the selected keyframes may reuse only their own output.
                write_animation(baked(1))
                door.export_cad_target(document, [("glb", out)], animation="show")
                self.assertEqual(exporter.call_count, 1)
                self.assertEqual(out.read_text(encoding="utf-8"), before)

    def test_snapshot_uses_one_digest_for_its_tree_lookup(self):
        from cadgen.catalog import result_snapshot_for

        with mock.patch("cadgen.catalog.artifact_file_hash", side_effect=["a" * 64, "b" * 64]) as hashed, \
                mock.patch("cadgen.store.records.tree_for_document_hash", return_value="tree-a") as lookup, \
                mock.patch("cadgen.store.objects.has_object", return_value=True):
            self.assertEqual(result_snapshot_for(Path("model.step")), ("a" * 64, "tree-a"))
        hashed.assert_called_once()
        lookup.assert_called_once_with("a" * 64)

    def test_replaced_input_cannot_rekey_an_already_selected_export(self):
        from cadgen._internal.mesh_export import MeshExportJob, MeshSource, mesh_variant_key
        from cadgen.cli_logging import CliLogger
        from cadgen.step_export_target import _export_mesh_jobs
        from cadgen.store.records import document_mesh_sha, note_document_tree

        with generated_cad_directory(prefix="mesh-document-snapshot-") as directory:
            root = Path(directory)
            document = root / "model.step"
            old_hash = hashlib.sha256(b"old document").hexdigest()
            document.write_bytes(b"replacement document")
            new_hash = hashlib.sha256(document.read_bytes()).hexdigest()
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
                written, _baked, _noted = _export_mesh_jobs(spec, MeshSource("tree-a", old_hash), [job],
                                                            logger=CliLogger("test", verbose=False))
                self.assertEqual(written, {out})
                key = mesh_variant_key("glb", None, None)
                self.assertEqual(document_mesh_sha(old_hash, key), hashlib.sha256(out.read_bytes()).hexdigest())
                self.assertIsNone(document_mesh_sha(new_hash, key))


if __name__ == "__main__":
    unittest.main()
