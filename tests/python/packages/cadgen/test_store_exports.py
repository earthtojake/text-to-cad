"""A model's STEP is an export of its stored result, verified by a parse (``store.exports``).

The export writes the stored tree with the names writer, or plain; the verify compares a
parse of the written bytes with the tree and makes the document's entry say what the file
shows: the tree, once it verifies, or the file's own content and what differs.
"""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        from build123d import Compound, Location, Solid

        from cadgen.store.build import build_tree_from_compound

        scratch = generated_cad_directory(prefix="store-exports-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        environment.start()
        self.addCleanup(environment.stop)
        plate = Solid.make_box(20, 10, 4) - Solid.make_cylinder(2, 4).moved(Location((5, 5, 0)))
        plate.label, plate.color = "plate", (0.2, 0.4, 0.6, 1)
        pin = Solid.make_cylinder(2, 12).moved(Location((15, 5, 0)))
        pin.label = "pin"
        self.tree, self.result, _ = build_tree_from_compound(Compound(children=[plate, pin], label="rig"),
                                                             root_name="rig")

    def export(self, name: str, *, names: bool = True) -> tuple[Path, dict]:
        from cadgen.store.exports import export_step

        path = self.root / name
        return path, export_step(self.tree, path, names=names)

    def pending(self, result: dict, *, tree: str | None = None, plain: bool = False) -> None:
        """The entry an export's publication writes: the bytes mapped to the tree, not yet verified."""
        from cadgen.store.parts import producer_identity
        from cadgen.store.records import note_document_tree

        note_document_tree(result["sha256"], tree or self.tree, producer=producer_identity(), verified=False,
                           plain=plain)

    def test_an_export_is_the_writer_given_the_stored_tree(self) -> None:
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.materialize import materialize

        path, result = self.export("plain.step", names=False)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["sha256"])
        self.assertEqual(export_build123d_step_file(materialize(self.tree), self.root / "writer.step"), result["sha256"])
        self.assertIsNone(result["producer"], "a plain file is written under no producer's keys")
        spans = [label for label, _seconds in result["spans"]]
        self.assertIn("materialize", spans)
        self.assertIn("write STEP file plain.step", spans)
        self.assertTrue(all(not names.part and not names.faces
                            for names in load_step_scene(path).prototype_step_names.values()),
                        "a plain file claims no part and no element")

    def test_an_export_captures_no_evidence_for_model_code(self) -> None:
        """What an export materializes is written, never handed to model code: it is not
        tagged as a materialized tree, whose evidence (every shape's geometry digest) only
        tells an edit by model code apart -- 3 s of the moonwatch's export."""
        from cadgen.store import materialize

        with mock.patch.object(materialize, "_capture_materialized_state",
                               wraps=materialize._capture_materialized_state) as capture:
            path, result = self.export("untagged.step")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["sha256"])
        self.assertEqual(0, capture.call_count)

    def test_a_named_export_verifies_and_its_entry_is_confirmed(self) -> None:
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.store.exports import verify_document
        from cadgen.store.records import document_entry_for_hash

        path, result = self.export("named.step")
        self.assertTrue(all(names.part for names in load_step_scene(path).prototype_step_names.values()))
        self.pending(result)
        self.assertEqual({"ok": True}, verify_document(self.tree, path, result["sha256"], producer=result["producer"]))
        entry = document_entry_for_hash(result["sha256"])
        self.assertEqual(self.tree, entry["tree"])
        self.assertNotIn("verified", entry)
        self.assertNotIn("differ", entry)

    def test_a_plain_export_verifies_by_its_occurrences(self) -> None:
        from cadgen.store.exports import verify_document

        path, result = self.export("plain.step", names=False)
        self.pending(result, plain=True)
        self.assertEqual({"ok": True}, verify_document(self.tree, path, result["sha256"], producer=None))

    def test_a_file_that_does_not_hold_the_tree_is_its_own_content(self) -> None:
        from build123d import Compound, Location, Solid

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.exports import verify_document
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import flatten

        path, result = self.export("named.step")
        # The bytes mapped to a result with a thicker pin: the file does not hold it.
        plate = Solid.make_box(20, 10, 4) - Solid.make_cylinder(2, 4).moved(Location((5, 5, 0)))
        plate.label, plate.color = "plate", (0.2, 0.4, 0.6, 1)
        pin = Solid.make_cylinder(3, 12).moved(Location((15, 5, 0)))
        pin.label = "pin"
        other, _, _ = build_tree_from_compound(Compound(children=[plate, pin], label="rig"), root_name="rig")
        self.pending(result, tree=other)
        answer = verify_document(other, path, result["sha256"], producer=result["producer"])
        self.assertFalse(answer["ok"])
        self.assertTrue(any("pin" in line for line in answer["differ"]), answer["differ"])
        entry = document_entry_for_hash(result["sha256"])
        self.assertNotIn(entry["tree"], (other, self.tree), "the file's own content: a compile of its bytes")
        self.assertEqual(answer["differ"], entry["differ"])
        self.assertNotIn("verified", entry)
        self.assertEqual(["pin", "plate"], sorted(row["name"] for row in flatten(entry["tree"])["occurrences"]))

    def test_a_file_whose_bytes_moved_on_is_not_answered_for(self) -> None:
        from cadgen.store.exports import verify_document
        from cadgen.store.records import document_entry_for_hash

        path, result = self.export("named.step")
        self.pending(result)
        path.write_bytes(path.read_bytes() + b"\n")
        self.assertEqual({"ok": None}, verify_document(self.tree, path, result["sha256"], producer=result["producer"]))
        self.assertIs(False, document_entry_for_hash(result["sha256"])["verified"])


class ArtifactVocabularyTest(unittest.TestCase):
    """An export names a stored tree and a staged STEP; a verify, the tree, a document and its
    bytes -- one job per bytes and tree, wherever the document is."""

    TREE, DIGEST = "a" * 64, "b" * 64

    def test_exports_and_verifies_are_closed_requests(self) -> None:
        from cadgen.daemon.artifacts import normalize_request

        out = str(Path("/work/stage/part.step").resolve())
        self.assertEqual({"kind": "export", "tree": self.TREE, "out": out, "names": True},
                         normalize_request({"kind": "export", "tree": self.TREE, "out": out, "names": True}))
        for bad in ({"kind": "export", "tree": self.TREE, "out": "part.step", "names": True},
                    {"kind": "export", "tree": self.TREE, "out": str(Path("/work/model.py").resolve()), "names": True},
                    {"kind": "export", "tree": self.TREE, "out": out, "names": "yes"},
                    {"kind": "verify", "tree": self.TREE, "document": out, "sha256": "x", "producer": None}):
            with self.subTest(request=bad), self.assertRaises(ValueError):
                normalize_request(bad)

    def test_a_verify_is_keyed_by_the_bytes_and_the_tree(self) -> None:
        from cadgen.daemon.artifacts import request_key

        def verify(document: str, tree: str) -> dict:
            return {"kind": "verify", "tree": tree, "document": str(Path(document).resolve()),
                    "sha256": self.DIGEST, "producer": None}

        self.assertEqual(request_key(verify("/a/part.step", self.TREE)), request_key(verify("/b/copy.step", self.TREE)))
        self.assertNotEqual(request_key(verify("/a/part.step", self.TREE)), request_key(verify("/a/part.step", "c" * 64)))


if __name__ == "__main__":
    unittest.main()
