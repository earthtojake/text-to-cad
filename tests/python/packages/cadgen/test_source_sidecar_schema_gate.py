"""The sidecar readers are gated on the schema they read.

A sidecar carries the model's DECLARATIONS — kinematics, animation, mesh
exports — none of which can be re-derived from the STEP bytes. Reading
sections out of a file written to a different shape is therefore how a model
silently loses them, so a present-but-wrong-schema sidecar is refused with the
CURRENT requirement and the fix, and never interpreted, converted, or
recognized as anything historical.

A MISSING sidecar stays the ordinary "declares nothing" case, and the
provenance record is the only home of source identity: no reader falls back to
the sidecar for it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cadgen._internal.source_sidecar import (
    SOURCE_SIDECAR_SCHEMA_VERSION,
    SidecarBindingError,
    SidecarSchemaError,
    read_source_provenance,
    read_source_sidecar,
    source_sidecar_matches_document,
    source_sidecar_path,
    write_source_sidecar,
)
from tests.python.support.tmp_root import generated_cad_directory

CURRENT_SIDECAR = {
    "kinematics": {
        "mates": [
            {
                "name": "swing",
                "kind": "revolute",
                "parent": "#base",
                "child": "#flap",
                "axis": {"origin": [0, 0, 0], "dir": [0, 0, 1]},
                "limits": {"value": [0, 120]},
            }
        ]
    },
}


class SidecarSchemaGate(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = generated_cad_directory(prefix="sidecar-gate-")
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.document = self.root / "hinge.step"
        self.document.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    def _write_at_schema(self, schema: object) -> Path:
        payload = dict(CURRENT_SIDECAR)
        if schema is not None:
            payload["schemaVersion"] = schema
        path = source_sidecar_path(self.document)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

    def _document_hash(self) -> str:
        import hashlib

        return hashlib.sha256(self.document.read_bytes()).hexdigest()

    def test_a_current_schema_sidecar_reads(self) -> None:
        write_source_sidecar(self.document, CURRENT_SIDECAR)

        payload = read_source_sidecar(self.document)
        self.assertIsNotNone(payload)
        self.assertEqual(SOURCE_SIDECAR_SCHEMA_VERSION, payload["schemaVersion"])
        self.assertEqual(self._document_hash(), payload["documentHash"])

    def test_a_missing_sidecar_is_not_an_error(self) -> None:
        self.assertIsNone(read_source_sidecar(self.document))

    def test_another_schema_is_refused_with_the_current_requirement(self) -> None:
        self._write_at_schema(SOURCE_SIDECAR_SCHEMA_VERSION - 1)

        with self.assertRaises(SidecarSchemaError) as caught:
            read_source_sidecar(self.document)
        message = str(caught.exception)
        self.assertIn(
            f"unsupported sidecar schema {SOURCE_SIDECAR_SCHEMA_VERSION - 1} (expected {SOURCE_SIDECAR_SCHEMA_VERSION})",
            message,
        )
        self.assertIn("python hinge.py", message)
        self.assertIn("cadgen step build", message)
        # The error states the requirement and the remedy, never the history.
        self.assertNotIn("renamed", message)
        self.assertNotIn("no longer", message)
        self.assertNotIn("was removed", message)

    def test_a_sidecar_declaring_no_schema_is_refused_the_same_way(self) -> None:
        self._write_at_schema(None)

        with self.assertRaisesRegex(SidecarSchemaError, "unsupported sidecar schema none"):
            read_source_sidecar(self.document)

    def test_classification_treats_another_schema_as_no_sidecar(self) -> None:
        """The generated-vs-imported fast yes never raises — a badge is not a
        render — so a sidecar this cadgen does not read is simply not a marker.
        Mirrors artifactStatus.mjs."""
        from cadgen._internal.source_sidecar import model_is_generated

        self.assertFalse(model_is_generated(self.document))
        self._write_at_schema(SOURCE_SIDECAR_SCHEMA_VERSION - 1)
        self.assertFalse(model_is_generated(self.document))
        write_source_sidecar(self.document, CURRENT_SIDECAR)
        self.assertTrue(model_is_generated(self.document))

    def test_a_sidecar_for_replaced_step_bytes_is_refused(self) -> None:
        write_source_sidecar(self.document, CURRENT_SIDECAR)
        self.document.write_text("replacement STEP bytes\n", encoding="utf-8")

        with self.assertRaisesRegex(SidecarBindingError, "does not match hinge.step sha256"):
            read_source_sidecar(self.document)
        self.assertFalse(source_sidecar_matches_document(self.document))

    def test_an_already_verified_digest_avoids_rereading_for_binding(self) -> None:
        digest = self._document_hash()
        write_source_sidecar(self.document, CURRENT_SIDECAR, document_hash=digest)

        self.assertEqual(
            digest,
            read_source_sidecar(self.document, document_hash=digest)["documentHash"],
        )

    def test_provenance_never_falls_back_to_the_sidecar(self) -> None:
        """Source identity lives in the records tier alone. A document with a
        sidecar but no record is an import (or an evicted record) — one rebuild
        re-records, which is the whole cost."""
        write_source_sidecar(self.document, CURRENT_SIDECAR)
        path = source_sidecar_path(self.document)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["sourceKind"] = "python"
        payload["sourcePath"] = "hinge.py"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

        self.assertIsNone(read_source_provenance(self.document))

    def test_a_rewrite_replaces_a_sidecar_at_another_schema(self) -> None:
        """The writer is not gated — it OWNS the file. A rebuild is the fix the
        error names, so it must actually work."""
        self._write_at_schema(SOURCE_SIDECAR_SCHEMA_VERSION - 1)

        write_source_sidecar(self.document, CURRENT_SIDECAR)

        payload = read_source_sidecar(self.document)
        self.assertEqual(SOURCE_SIDECAR_SCHEMA_VERSION, payload["schemaVersion"])


if __name__ == "__main__":
    unittest.main()
