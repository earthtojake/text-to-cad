"""GLB byte changes invalidate only final GLB export reuse."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.mesh_export import (  # noqa: E402
    GLB_SERIALIZATION_VERSION,
    document_mesh_current,
    mesh_export_current,
    mesh_variant_key,
    record_document_mesh,
    record_mesh_export,
)
from cadgen._internal.source_sidecar import appearance_digest  # noqa: E402
from cadgen.store.records import (  # noqa: E402
    note_document_mesh,
    note_document_tree,
    read_record,
    write_record,
)


def _legacy_variant(fmt: str, animation_key: str | None = None) -> str:
    fields = [fmt, "default", "default", f"appearance:{appearance_digest(None)}"]
    if animation_key is not None:
        fields.append(f"anim:{animation_key}")
    return "|".join(fields)


class GlbSerializerFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="glb-serializer-freshness-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self.env = mock.patch.dict("os.environ", {"CADGEN_CACHE_DIR": str(self.store)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_python_and_shared_writer_revisions_match(self) -> None:
        source = (
            REPO_ROOT / "packages/core/src/lib/glb/writeGlb.js"
        ).read_text(encoding="utf-8")
        match = re.search(r"export const GLB_SERIALIZATION_VERSION\s*=\s*(\d+)", source)
        self.assertIsNotNone(match, "writeGlb must export its final-byte serialization revision")
        self.assertEqual(GLB_SERIALIZATION_VERSION, int(match.group(1)))

    def test_only_glb_artifact_variants_move_and_old_static_and_animated_entries_miss(self) -> None:
        for fmt in ("stl", "3mf"):
            self.assertEqual(_legacy_variant(fmt), mesh_variant_key(fmt, None, None))

        document_hash = "a" * 64
        note_document_tree(document_hash, "tree")
        output = self.root / "part.glb"
        output.write_bytes(b"same final output bytes")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()

        for animation_key in (None, "clip-and-module-token"):
            with self.subTest(animation_key=animation_key):
                old_key = _legacy_variant("glb", animation_key)
                new_key = mesh_variant_key("glb", None, None, animation_key=animation_key)
                self.assertNotEqual(old_key, new_key)
                self.assertIn(f"|serializer:{GLB_SERIALIZATION_VERSION}|", new_key)

                note_document_mesh(document_hash, old_key, digest)
                self.assertFalse(
                    document_mesh_current(
                        output,
                        document_hash=document_hash,
                        fmt="glb",
                        mesh_tolerance=None,
                        mesh_angular_tolerance=None,
                        animation_key=animation_key,
                    )
                )
                record_document_mesh(
                    output,
                    document_hash=document_hash,
                    fmt="glb",
                    mesh_tolerance=None,
                    mesh_angular_tolerance=None,
                    animation_key=animation_key,
                )
                self.assertTrue(
                    document_mesh_current(
                        output,
                        document_hash=document_hash,
                        fmt="glb",
                        mesh_tolerance=None,
                        mesh_angular_tolerance=None,
                        animation_key=animation_key,
                    )
                )

    def test_model_output_rejects_old_glb_then_accepts_current_without_invalidating_stl(self) -> None:
        model = self.root / "model.step"
        model.write_bytes(b"document")
        document_hash = hashlib.sha256(model.read_bytes()).hexdigest()
        output = self.root / "model.glb"
        output.write_bytes(b"old glb")

        def entry(fmt: str, path: Path) -> dict:
            return {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "declared": fmt,
                "document": document_hash,
                "chord": "default",
                "angle": "default",
                "anim": None,
                "appearance": appearance_digest(None),
            }

        stl = self.root / "model.stl"
        stl.write_bytes(b"unchanged stl")
        write_record(model, {
            "tree": "tree",
            "outputs": {str(output.resolve()): entry("glb", output), str(stl.resolve()): entry("stl", stl)},
        })
        current = dict(
            model=model,
            document_hash=document_hash,
            mesh_tolerance=None,
            mesh_angular_tolerance=None,
        )
        self.assertFalse(mesh_export_current(output, **current))
        self.assertTrue(mesh_export_current(stl, **current))

        record_mesh_export(output, fmt="glb", **current)
        self.assertTrue(mesh_export_current(output, **current))
        self.assertEqual(
            GLB_SERIALIZATION_VERSION,
            read_record(model)["outputs"][str(output.resolve())]["serializer"],
        )
        self.assertNotIn("serializer", read_record(model)["outputs"][str(stl.resolve())])


if __name__ == "__main__":
    unittest.main()
