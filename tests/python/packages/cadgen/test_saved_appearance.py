"""Saved appearance is strict, owned, and part of mesh freshness."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path
from unittest import mock

from cadgen._internal.mesh_export import (
    document_mesh_current,
    mesh_export_current,
    mesh_variant_key,
    record_document_mesh,
    record_mesh_export,
)
from cadgen._internal.source_sidecar import (
    SOURCE_SIDECAR_SCHEMA_VERSION,
    SidecarAppearanceError,
    appearance_digest,
    apply_appearance,
    normalize_appearance,
    read_source_sidecar,
    source_sidecar_path,
    write_source_sidecar,
)
from cadgen.store.index import model_key, read_entry, write_entry
from cadgen.store.records import (
    DOCUMENT_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    document_mesh_sha,
    note_document_mesh,
    note_document_tree,
    read_record,
    tree_for_document_hash,
    write_record,
)
from tests.python.support.tmp_root import generated_cad_directory


ROUGH = {
    "materials": {"rough": {"name": "Rough", "roughness": 0.8, "metalness": 0.1}},
    "assignments": {"o1": "rough"},
}
POLISHED = {
    "materials": {"polished": {"name": "Polished", "roughness": 0.1, "metalness": 0.8}},
    "assignments": {"o1": "polished"},
}


class SavedAppearanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="saved-appearance-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self._cache = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        self._cache.start()
        self.addCleanup(self._cache.stop)

    def test_normalization_is_canonical_owned_and_strict(self) -> None:
        source = {
            "materials": {
                "coat": {"name": "Coat", "opacity": 1, "clearcoatRoughness": 0.75},
                "metal": {"name": "Metal", "roughness": 0, "metalness": 0.25, "clearcoat": 0.5},
            },
            "assignments": {"o2": "coat", "o1": "metal"},
        }
        normalized = normalize_appearance(source)

        self.assertEqual(
            {
                "materials": {
                    "coat": {"name": "Coat", "clearcoatRoughness": 0.75, "opacity": 1.0},
                    "metal": {"name": "Metal", "clearcoat": 0.5, "metalness": 0.25, "roughness": 0.0},
                },
                "assignments": {"o1": "metal", "o2": "coat"},
            },
            normalized,
        )
        self.assertIsNot(source, normalized)
        self.assertIsNot(source["materials"]["metal"], normalized["materials"]["metal"])
        normalized["materials"]["metal"]["roughness"] = 0.9
        self.assertEqual(0, source["materials"]["metal"]["roughness"])

        invalid = (
            {},
            {"materials": {}, "assignments": {}, "extra": 1},
            {"materials": [], "assignments": {}},
            {"materials": {"m": {"name": "M"}}, "assignments": {"": "m"}},
            {"materials": {"m": {"name": "M"}}, "assignments": {"o1": "missing"}},
            {"materials": {"m": {"name": "M", "color": 0.5}}, "assignments": {"o1": "m"}},
            {"materials": {"m": {"name": "M", "roughness": True}}, "assignments": {"o1": "m"}},
            {"materials": {"m": {"name": "M", "roughness": float("nan")}}, "assignments": {"o1": "m"}},
            {"materials": {"m": {"name": "M", "roughness": 1.01}}, "assignments": {"o1": "m"}},
        )
        for block in invalid:
            with self.subTest(block=block), self.assertRaises(SidecarAppearanceError):
                normalize_appearance(block)

    def test_digest_is_canonical_and_includes_absence(self) -> None:
        reordered = {"assignments": {"o1": "rough"}, "materials": {"rough": {"metalness": 0.1, "roughness": 0.8, "name": "Rough"}}}

        self.assertEqual(appearance_digest(ROUGH), appearance_digest(reordered))
        self.assertNotEqual(appearance_digest(ROUGH), appearance_digest(POLISHED))
        self.assertEqual(appearance_digest(None), appearance_digest({"materials": {}, "assignments": {}}))
        self.assertNotEqual(appearance_digest(None), appearance_digest(ROUGH))

    def test_apply_appearance_returns_a_fresh_descriptor_and_rejects_missing_targets(self) -> None:
        descriptor = {
            "components": {"c1": {"surf": "a"}, "c2": {"surf": "b"}},
            "occurrences": [
                {"id": "o1", "component": "c1", "material": {"roughness": 0.4}},
                {"id": "o2", "component": "c2"},
            ],
            "assembly": {"root": {"children": [{"id": "o1"}]}},
        }
        block = {
            "materials": {
                "rough": {"name": "Rough", "baseColor": "#123456", "roughness": 0.8},
                "metal": {"name": "Metal", "metalness": 0.25},
            },
            "assignments": {"o1": "rough", "o2": "metal"},
        }

        applied = apply_appearance(descriptor, block)
        self.assertEqual(
            {"roughness": 0.8, "metalness": 0.03, "clearcoat": 0.0, "clearcoatRoughness": 0.26, "opacity": 1.0},
            applied["occurrences"][0]["material"],
        )
        self.assertEqual(
            {"roughness": 0.42, "metalness": 0.25, "clearcoat": 0.0, "clearcoatRoughness": 0.26, "opacity": 1.0},
            applied["occurrences"][1]["material"],
        )
        self.assertEqual("rough", applied["occurrences"][0]["materialId"])
        self.assertEqual("Rough", applied["occurrences"][0]["materialName"])
        self.assertEqual("#123456", applied["occurrences"][0]["baseColor"])
        self.assertEqual("metal", applied["occurrences"][1]["materialId"])
        self.assertEqual("Metal", applied["occurrences"][1]["materialName"])
        self.assertNotIn("baseColor", applied["occurrences"][1])
        self.assertEqual({"roughness": 0.4}, descriptor["occurrences"][0]["material"])
        self.assertNotIn("material", descriptor["occurrences"][1])
        second_consumer = apply_appearance(descriptor, block)
        self.assertIsNot(applied["occurrences"][0]["material"], block["materials"]["rough"])
        self.assertIsNot(
            applied["occurrences"][0]["material"],
            second_consumer["occurrences"][0]["material"],
        )
        applied["occurrences"][0]["material"]["roughness"] = 0.2
        self.assertEqual(0.8, second_consumer["occurrences"][0]["material"]["roughness"])
        self.assertEqual(0.8, block["materials"]["rough"]["roughness"])
        applied["components"]["c1"]["surf"] = "changed"
        applied["assembly"]["root"]["children"][0]["id"] = "changed"
        self.assertEqual("a", descriptor["components"]["c1"]["surf"])
        self.assertEqual("o1", descriptor["assembly"]["root"]["children"][0]["id"])

        absent = apply_appearance(descriptor, None)
        self.assertEqual(descriptor, absent)
        self.assertIsNot(descriptor, absent)
        self.assertIsNot(descriptor["occurrences"], absent["occurrences"])

        with self.assertRaisesRegex(SidecarAppearanceError, "missing document occurrence missing"):
            apply_appearance(descriptor, {"materials": {"m": {"name": "M", "opacity": 0.5}}, "assignments": {"missing": "m"}})
        with self.assertRaisesRegex(SidecarAppearanceError, "missing document occurrence group"):
            apply_appearance(
                {"occurrences": [{"id": "group", "children": []}]},
                {"materials": {"m": {"name": "M", "opacity": 0.5}}, "assignments": {"group": "m"}},
            )

    def test_schema_nine_sidecars_bind_appearance_to_actual_step_bytes(self) -> None:
        first = self.root / "first.step"
        second = self.root / "renamed.step"
        step_bytes = b"ISO-10303-21;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
        first.write_bytes(step_bytes)
        second.write_bytes(step_bytes)

        write_source_sidecar(first, {"appearance": ROUGH})
        write_source_sidecar(second, {"appearance": POLISHED})
        first_sidecar = read_source_sidecar(first)
        second_sidecar = read_source_sidecar(second)
        expected_hash = hashlib.sha256(step_bytes).hexdigest()

        self.assertEqual(SOURCE_SIDECAR_SCHEMA_VERSION, first_sidecar["schemaVersion"])
        self.assertEqual(9, first_sidecar["schemaVersion"])
        self.assertEqual(expected_hash, first_sidecar["documentHash"])
        self.assertEqual(expected_hash, second_sidecar["documentHash"])
        self.assertEqual(ROUGH, first_sidecar["appearance"])
        self.assertEqual(POLISHED, second_sidecar["appearance"])
        self.assertNotEqual(
            appearance_digest(first_sidecar["appearance"]),
            appearance_digest(second_sidecar["appearance"]),
        )

        invalid = self.root / "invalid.step"
        invalid.write_bytes(step_bytes)
        with self.assertRaises(SidecarAppearanceError):
            write_source_sidecar(invalid, {"appearance": {"materials": {"m": {"name": "M", "opacity": False}}, "assignments": {"o1": "m"}}})
        self.assertFalse(source_sidecar_path(invalid).exists())

    def test_model_records_cut_over_to_six_while_documents_remain_four(self) -> None:
        current_tree = "c" * 64
        model = self.root / "model.step"
        model.write_bytes(b"model")
        for schema in (4, 5, 6):
            with self.subTest(retired_schema=schema):
                write_entry(
                    "model",
                    model_key(model),
                    {"kind": "record", "schemaVersion": schema, "tree": "legacy-tree", "outputs": {}},
                )
                self.assertIsNone(read_record(model))

        write_record(model, {"tree": current_tree, "outputs": {}})
        current_record = read_record(model)
        self.assertEqual(RECORD_SCHEMA_VERSION, current_record["schemaVersion"])
        self.assertEqual(7, current_record["schemaVersion"])
        self.assertEqual(current_tree, current_record["tree"])

        document_hash = "d" * 64
        write_entry(
            "document",
            document_hash,
            {"schemaVersion": 3, "tree": "legacy-tree", "kind": "step", "meshes": {"old": "mesh"}},
        )
        self.assertIsNone(tree_for_document_hash(document_hash))
        self.assertIsNone(document_mesh_sha(document_hash, "old"))
        note_document_mesh(document_hash, "new", "ignored")
        self.assertEqual(3, read_entry("document", document_hash)["schemaVersion"])

        note_document_tree(document_hash, current_tree)
        current_document = read_entry("document", document_hash)
        self.assertEqual(DOCUMENT_SCHEMA_VERSION, current_document["schemaVersion"])
        self.assertEqual(4, current_document["schemaVersion"])
        self.assertEqual(current_tree, tree_for_document_hash(document_hash))
        self.assertNotIn("meshes", current_document)
        note_document_mesh(document_hash, "new", "current-mesh")
        self.assertEqual("current-mesh", document_mesh_sha(document_hash, "new"))

    def test_document_mesh_ledger_separates_finishes_and_no_appearance(self) -> None:
        document_hash = "a" * 64
        note_document_tree(document_hash, "tree")
        output = self.root / "part.glb"
        rough_key = appearance_digest(ROUGH)
        polished_key = appearance_digest(POLISHED)
        absent_key = appearance_digest(None)

        rough_variant = mesh_variant_key("glb", 0.1, 0.2, appearance_key=rough_key)
        polished_variant = mesh_variant_key("glb", 0.1, 0.2, appearance_key=polished_key)
        absent_variant = mesh_variant_key("glb", 0.1, 0.2)
        self.assertEqual(absent_variant, mesh_variant_key("glb", 0.1, 0.2, appearance_key=absent_key))
        self.assertEqual(3, len({rough_variant, polished_variant, absent_variant}))

        output.write_bytes(b"rough mesh")
        record_document_mesh(
            output,
            document_hash=document_hash,
            fmt="glb",
            mesh_tolerance=0.1,
            mesh_angular_tolerance=0.2,
            appearance_key=rough_key,
        )
        self.assertTrue(
            document_mesh_current(
                output,
                document_hash=document_hash,
                fmt="glb",
                mesh_tolerance=0.1,
                mesh_angular_tolerance=0.2,
                appearance_key=rough_key,
            )
        )
        for wrong_key in (polished_key, None):
            with self.subTest(wrong_key=wrong_key):
                self.assertFalse(
                    document_mesh_current(
                        output,
                        document_hash=document_hash,
                        fmt="glb",
                        mesh_tolerance=0.1,
                        mesh_angular_tolerance=0.2,
                        appearance_key=wrong_key,
                    )
                )

        output.write_bytes(b"polished mesh")
        record_document_mesh(
            output,
            document_hash=document_hash,
            fmt="glb",
            mesh_tolerance=0.1,
            mesh_angular_tolerance=0.2,
            appearance_key=polished_key,
        )
        self.assertTrue(
            document_mesh_current(
                output,
                document_hash=document_hash,
                fmt="glb",
                mesh_tolerance=0.1,
                mesh_angular_tolerance=0.2,
                appearance_key=polished_key,
            )
        )
        self.assertFalse(
            document_mesh_current(
                output,
                document_hash=document_hash,
                fmt="glb",
                mesh_tolerance=0.1,
                mesh_angular_tolerance=0.2,
                appearance_key=rough_key,
            )
        )

    def test_model_mesh_ledger_separates_appearance_without_changing_document_identity(self) -> None:
        model = self.root / "model.step"
        model.write_bytes(b"same document bytes")
        document_hash = hashlib.sha256(model.read_bytes()).hexdigest()
        note_document_tree(document_hash, "tree")
        write_record(model, {"tree": "tree", "outputs": {}})
        output = self.root / "model.glb"
        rough_key = appearance_digest(ROUGH)
        polished_key = appearance_digest(POLISHED)

        output.write_bytes(b"rough mesh")
        record_mesh_export(
            output,
            model=model,
            document_hash=document_hash,
            fmt="glb",
            mesh_tolerance=None,
            mesh_angular_tolerance=None,
            appearance_key=rough_key,
        )
        self.assertTrue(
            mesh_export_current(
                output,
                model=model,
                document_hash=document_hash,
                mesh_tolerance=None,
                mesh_angular_tolerance=None,
                appearance_key=rough_key,
            )
        )
        self.assertFalse(
            mesh_export_current(
                output,
                model=model,
                document_hash=document_hash,
                mesh_tolerance=None,
                mesh_angular_tolerance=None,
                appearance_key=polished_key,
            )
        )
        self.assertFalse(
            mesh_export_current(
                output,
                model=model,
                document_hash=document_hash,
                mesh_tolerance=None,
                mesh_angular_tolerance=None,
            )
        )
        recorded = read_record(model)["outputs"][str(output.resolve())]
        self.assertEqual(document_hash, recorded["document"])
        self.assertEqual(rough_key, recorded["appearance"])


if __name__ == "__main__":
    unittest.main()
