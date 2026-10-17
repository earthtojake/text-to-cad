"""A format's byte changes invalidate exactly that format's final export reuse."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.mesh_export import (  # noqa: E402
    SERIALIZATION_VERSIONS,
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


def _legacy_variant(fmt: str, animation_key: str | None = None, serializer: int | None = None) -> str:
    """A variant key as an earlier writer ledgered it: STL/3MF with no revision at all."""
    fields = [fmt, "default", "default"]
    if serializer is not None:
        fields.append(f"serializer:{serializer}")
    fields.append(f"appearance:{appearance_digest(None)}")
    if animation_key is not None:
        fields.append(f"anim:{animation_key}")
    return "|".join(fields)


class SerializerFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="serializer-freshness-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self.env = mock.patch.dict("os.environ", {"CADGEN_CACHE_DIR": str(self.store)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_every_format_carries_its_revision_and_an_older_ledger_entry_misses(self) -> None:
        # The JavaScript writers ledgered STL and 3MF with no revision and GLB at 3;
        # none of their files may be reported current for what the store's meshes write.
        self.assertEqual(set(SERIALIZATION_VERSIONS), {"stl", "3mf", "glb"})
        document_hash = "a" * 64
        note_document_tree(document_hash, "tree")
        cases = [("stl", None, None), ("3mf", None, None), ("glb", None, 3), ("glb", "clip-and-keyframes", 3)]
        for fmt, animation_key, old_serializer in cases:
            with self.subTest(fmt=fmt, animation_key=animation_key):
                output = self.root / f"part-{fmt}-{animation_key}.{fmt}"
                output.write_bytes(f"final {fmt} bytes".encode())
                digest = hashlib.sha256(output.read_bytes()).hexdigest()
                new_key = mesh_variant_key(fmt, None, None, animation_key=animation_key)
                self.assertIn(f"|serializer:{SERIALIZATION_VERSIONS[fmt]}|", new_key)
                old_key = _legacy_variant(fmt, animation_key, old_serializer)
                self.assertNotEqual(old_key, new_key)

                variant = dict(document_hash=document_hash, fmt=fmt, mesh_tolerance=None,
                               mesh_angular_tolerance=None, animation_key=animation_key)
                note_document_mesh(document_hash, old_key, digest)
                self.assertFalse(document_mesh_current(output, **variant))
                record_document_mesh(output, **variant)
                self.assertTrue(document_mesh_current(output, **variant))

    def test_a_model_output_written_before_the_revision_is_stale_until_rewritten(self) -> None:
        model = self.root / "model.step"
        model.write_bytes(b"document")
        document_hash = hashlib.sha256(model.read_bytes()).hexdigest()

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

        outputs = {fmt: self.root / f"model.{fmt}" for fmt in ("stl", "3mf", "glb")}
        for fmt, path in outputs.items():
            path.write_bytes(f"old {fmt}".encode())
        write_record(model, {"tree": "tree", "outputs": {str(path.resolve()): entry(fmt, path)
                                                        for fmt, path in outputs.items()}})
        current = dict(model=model, document_hash=document_hash, mesh_tolerance=None, mesh_angular_tolerance=None)
        for fmt, path in outputs.items():
            with self.subTest(fmt=fmt):
                self.assertFalse(mesh_export_current(path, **current))
                record_mesh_export(path, fmt=fmt, **current)
                self.assertTrue(mesh_export_current(path, **current))
                self.assertEqual(
                    SERIALIZATION_VERSIONS[fmt],
                    read_record(model)["outputs"][str(path.resolve())]["serializer"],
                )


if __name__ == "__main__":
    unittest.main()
