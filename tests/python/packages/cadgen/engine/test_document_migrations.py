"""Read real published xbf/8 bytes without source, preserving their saved meaning."""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build123d as bd
from bd_materials import FinishedMaterial
from bd_materials.core import Range
from OCP.Standard import Standard_GUID
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_AsciiString, TDataStd_NamedData, TDataStd_TreeNode
from OCP.TDF import TDF_ChildIterator
from OCP.XCAFDoc import XCAFDoc, XCAFDoc_DocumentTool, XCAFDoc_Material
from OCP.collections import Sequence_TDF_Label

from cadgen.engine import build, document, document_migrations, export, mesh, previous
from cadgen.engine.colors import srgb_to_linear

FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "xbf8_materials.xbf"
EXPECTED = json.loads((FIXTURES / "xbf8_materials.json").read_text(encoding="utf-8"))


def physical_labels(doc):
    labels = Sequence_TDF_Label()
    XCAFDoc_DocumentTool.MaterialTool_s(doc.Main()).GetMaterialLabels(labels)
    return [labels.Value(i) for i in range(1, labels.Length() + 1)]


def links(doc, guid):
    found = {}
    iterator = TDF_ChildIterator(doc.Main(), True)
    while iterator.More():
        label = iterator.Value()
        node = TDataStd_TreeNode()
        if document._find(label, node, guid) and node.HasFather():
            found[document._entry(label)] = document._entry(node.Father().Label())
        iterator.Next()
    return found


def legacy_metadata(label):
    data = TDataStd_NamedData()
    if not document._find(label, data, TDataStd_NamedData.GetID_s()):
        return {}
    found = {}
    for name in ("family", "standard", "source", "vendor_batch", "bd_materials"):
        key = TCollection_ExtendedString(name)
        if data.HasString(key):
            found[name] = data.GetString(key).ToExtString()
    for name in ("young_modulus", "poisson_ratio", "yield_strength", "ultimate_strength",
                 "thermal_expansion", "thermal_conductivity", "specific_heat", "anisotropy",
                 "anisotropy_rotation", "transmission", "transmission_depth", "coat",
                 "coat_roughness", "emissive_strength", "vendor_scale"):
        key = TCollection_ExtendedString(name)
        if data.HasReal(key):
            found[name] = data.GetReal(key)
    for name in ("isotropic", "custom_revision"):
        key = TCollection_ExtendedString(name)
        if data.HasInteger(key):
            found[name] = data.GetInteger(key)
    key = TCollection_ExtendedString("transmission_color")
    if data.HasArrayOfReals(key):
        values = data.GetArrayOfReals(key)
        found["transmission_color"] = [values.Value(i) for i in range(values.Lower(), values.Upper() + 1)]
    return found


def document_state(doc):
    """Observable persistent metadata, including refs and the complete native payload."""
    cards = []
    for label in physical_labels(doc):
        physical = XCAFDoc_Material()
        document._find(label, physical, XCAFDoc_Material.GetID_s())
        cards.append([document._entry(label), physical.GetName().ToCString(),
                      physical.GetDescription().ToCString(), physical.GetDensity(),
                      physical.GetDensName().ToCString(), physical.GetDensValType().ToCString(),
                      legacy_metadata(label)])
    return json.dumps({
        "writer": document._label_text(doc.Main(), document.WRITER_GUID),
        "closure": document._label_text(doc.Main(), document.CLOSURE_GUID),
        "migration": document._label_text(doc.Main(), document_migrations.MIGRATION_GUID),
        "physical_refs": links(doc, XCAFDoc.MaterialRefGUID_s()),
        "visual_refs": links(doc, XCAFDoc.VisMaterialRefGUID_s()), "cards": cards,
    }, sort_keys=True)


class DocumentMigrationsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="document-migration-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "saved" / FIXTURE.name
        self.path.parent.mkdir()
        shutil.copy2(FIXTURE, self.path)
        self.original = self.path.read_bytes()
        self.original_stat = self.path.stat()

    def assert_original_untouched(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.path.stat().st_mtime_ns, self.original_stat.st_mtime_ns)

    def assert_structure(self, loaded):
        current = json.loads(json.dumps(loaded.structure()))
        for key in ("name", "units", "tree", "instances"):
            self.assertEqual(current[key], EXPECTED["structure"][key], key)
        self.assertEqual(len(current["prototypes"]), 3)
        for old, new in zip(EXPECTED["structure"]["prototypes"], current["prototypes"]):
            for key in ("name", "key", "color", "faceNames", "edgeNames", "vertexNames", "faceColors"):
                self.assertEqual(new[key], old[key], (new["name"], key))

    def assert_appearance(self, material, old):
        self.assertIsInstance(material, FinishedMaterial)
        values = material.pbr.to_dict()["values"]
        for old_name, new_name in (
            ("metallic", "metalness"), ("roughness", "roughness"), ("ior", "ior"),
            ("anisotropy", "anisotropy"), ("anisotropyRotation", "anisotropyRotation"),
            ("transmission", "transmission"), ("transmissionDepth", "attenuationDistance"),
            ("coat", "clearcoat"), ("coatRoughness", "clearcoatRoughness"),
            ("emissiveStrength", "emissiveIntensity"),
        ):
            self.assertAlmostEqual(values[new_name], old[old_name], delta=1e-6, msg=new_name)
        for actual, expected in zip(values["color"], old["color"][:3]):
            self.assertAlmostEqual(srgb_to_linear(actual), expected, delta=1e-6)
        self.assertAlmostEqual(values["opacity"], old["color"][3], delta=1e-6)
        for old_name, new_name in (("transmissionColor", "attenuationColor"), ("emissive", "emissive")):
            for actual, expected in zip(values[new_name], old[old_name]):
                self.assertAlmostEqual(actual, expected, delta=1e-6)

    def test_real_old_binary_opens_without_source_and_preserves_geometry_names_and_placements(self):
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), EXPECTED["sha256"])
        self.assertEqual(EXPECTED["versions"]["cadgen"], "0.8.0")
        self.assertEqual(EXPECTED["versions"]["cadquery-ocp-novtk"], "7.9.3.1.1")
        self.assertIn(b"cadgen.engine xbf/8 ", self.original)
        missing_source = self.path.parent / EXPECTED["closure"]["source"]["path"]
        self.assertFalse(missing_source.exists())
        with mock.patch.object(build, "build", side_effect=AssertionError("saved source must not run")):
            loaded = document.Loaded(self.path)
            self.assert_structure(loaded)
            self.assertEqual(loaded.closure, EXPECTED["closure"])
            self.assertEqual(loaded.migration["from"], "xbf/8")
            self.assertEqual(loaded.migration["writer"], EXPECTED["writer"])
            self.assertEqual(document.written_format(loaded.writer), previous.FORMAT)
            self.assertAlmostEqual(sum(bd.Compound(p.shape).volume for p in loaded.prototypes),
                                   EXPECTED["total_volume"], places=7)
            for prototype in loaded.prototypes:
                triangulated = mesh.mesh_shape(prototype.shape)
                self.assertGreater(len(triangulated.indices), 0)
                self.assertEqual(triangulated.unmeshed, {})
        self.assert_original_untouched()

    def test_saved_native_material_format_nine_opens_without_rekeying_its_original_closure(self):
        raw = document.read_bytes(self.original)
        with mock.patch.object(previous, "FORMAT", "xbf/9"), mock.patch.object(
                document, "_writer", return_value="cadgen.engine xbf/9 (cadgen 0.8.1)"):
            document_migrations.upgrade(raw)
        saved = document.to_bytes(raw)
        path = self.folder / "native-nine.xbf"
        path.write_bytes(saved)
        loaded = document.Loaded(path)
        self.assertEqual(document.written_format(loaded.writer), "xbf/10")
        self.assertEqual(loaded.migration["from"], "xbf/9")
        self.assertEqual(loaded.migration["materials"], 0)
        self.assertEqual(loaded.migration["previous"]["from"], "xbf/8")
        self.assertEqual(loaded.closure, EXPECTED["closure"])
        self.assert_structure(loaded)
        self.assertEqual(path.read_bytes(), saved, "opening does not rewrite the saved format-nine bytes")

    def test_old_physical_values_convert_units_without_catalogue_substitution_and_keep_metadata(self):
        raw = document.read_bytes(self.original)
        original = physical_labels(raw)[0]
        legacy = legacy_metadata(original)
        self.assertEqual(len(physical_labels(raw)), 1)
        loaded = document.Loaded(self.path, raw)
        physics = loaded.prototypes[0].material.material
        self.assertEqual(physics.name, "Legacy test alloy")
        self.assertEqual(physics.density, 7850)
        for name, expected in (("modulus_of_elasticity", 210), ("yield_strength", 355),
                               ("tensile_strength", 610), ("poisson_ratio", .29),
                               ("thermal_expansion", 12.3e-6), ("thermal_conductivity", 42.5),
                               ("specific_heat_capacity", 470)):
            value = getattr(physics, name)
            self.assertIsInstance(value, Range, name)
            self.assertEqual((value.min, value.max), (expected, expected), name)
        self.assertIsNone(physics.melting_temperature, "a missing property stays unknown")
        self.assertEqual(loaded.migration["materials"], 4)
        for label in physical_labels(raw):
            metadata = legacy_metadata(label)
            self.assertIn("bd_materials", metadata)
            metadata.pop("bd_materials")
            self.assertEqual(metadata, legacy)
            physical = XCAFDoc_Material()
            document._find(label, physical, XCAFDoc_Material.GetID_s())
            self.assertEqual(physical.GetDescription().ToCString(), EXPECTED["physical"]["description"])
            self.assertEqual(physical.GetDensName().ToCString(), "density")
            self.assertEqual(physical.GetDensValType().ToCString(), "MASS_DENSITY_MEASURE")
        self.assert_original_untouched()

    def test_shared_physics_keeps_distinct_visuals_face_paints_and_instance_colours_in_glb(self):
        raw = document.read_bytes(self.original)
        visual_refs = links(raw, XCAFDoc.VisMaterialRefGUID_s())
        loaded = document.Loaded(self.path, raw)
        self.assertEqual(links(raw, XCAFDoc.VisMaterialRefGUID_s()), visual_refs)
        for old, part in zip(EXPECTED["structure"]["prototypes"], loaded.prototypes):
            self.assert_appearance(part.material, old["material"])
            for ordinal, material in part.face_materials.items():
                self.assert_appearance(material, old["faceMaterials"][str(ordinal)])
        pin = next(p for p in loaded.prototypes if p.name == "pin")
        self.assertAlmostEqual(pin.material.pbr.values.roughness, .12, delta=1e-6)
        self.assertEqual(loaded.instances[-1].prototype, pin.index)
        self.assertAlmostEqual(loaded.instances[-1].color[-1], 119 / 255, delta=1e-6)
        target = self.folder / "saved.glb"
        export.translate(export.Source.read(self.path), "glb", target)
        data = target.read_bytes()
        length = struct.unpack_from("<I", data, 12)[0]
        gltf = json.loads(data[20:20 + length])
        looks = gltf["materials"]
        for alpha in (.8, .4, .6, .2, 119 / 255):
            self.assertTrue(any(abs(m["pbrMetallicRoughness"]["baseColorFactor"][3] - alpha) < .0011
                                for m in looks), alpha)
        for look in looks:
            extensions = look["extensions"]
            self.assertAlmostEqual(extensions["KHR_materials_transmission"]["transmissionFactor"], .5)
            self.assertAlmostEqual(extensions["KHR_materials_anisotropy"]["anisotropyStrength"], .4)
            self.assertAlmostEqual(extensions["KHR_materials_clearcoat"]["clearcoatFactor"], .6)
            self.assertAlmostEqual(extensions["KHR_materials_emissive_strength"]["emissiveStrength"], 2.5)
        self.assert_original_untouched()

    def test_explicit_migrated_save_is_idempotent_and_preserves_closure_and_legacy_attributes(self):
        source = export.Source.read(self.path)
        first = document_state(source.xcaf)
        self.assertIsNone(document_migrations.upgrade(source.xcaf))
        self.assertEqual(document_state(source.xcaf), first)
        target = self.folder / "migrated.xbf"
        export.translate(source, "xbf", target)
        reloaded = document.Loaded(target)
        self.assertIsNone(reloaded.migration)
        self.assertEqual(reloaded.closure, EXPECTED["closure"])
        self.assert_structure(reloaded)
        self.assertEqual(document_state(reloaded.doc), document_state(source.xcaf))
        self.assertEqual(document_migrations.provenance(reloaded.doc)["origin"], {
            "kind": "file", "path": str(self.path.resolve()), "closure_base": str(self.path.parent.resolve()),
        })
        with self.assertRaisesRegex(export.ExportRefused, "different XBF path"):
            export.translate(source, "xbf", self.path)
        with self.assertRaisesRegex(export.ExportRefused, "already is one"):
            export.translate(export.Source.read(target), "xbf", self.folder / "unnecessary.xbf")
        self.assert_original_untouched()

    def test_unsupported_version_and_invalid_old_data_leave_document_and_file_unchanged(self):
        for failure in ("future", "nonfinite"):
            with self.subTest(failure=failure):
                raw = document.read_bytes(self.original)
                if failure == "future":
                    TDataStd_AsciiString.Set_s(raw.Main(), Standard_GUID(document.WRITER_GUID),
                                             TCollection_AsciiString("cadgen.engine xbf/99 (cadgen 9.9.9)"))
                    expected = "unsupported document format xbf/99"
                else:
                    data = TDataStd_NamedData.Set_s(physical_labels(raw)[0])
                    data.SetReal(TCollection_ExtendedString("young_modulus"), float("nan"))
                    expected = "young_modulus is not finite"
                before = document_state(raw)
                with self.assertRaisesRegex(document_migrations.DocumentCompatibilityError, expected):
                    document_migrations.upgrade(raw)
                self.assertEqual(document_state(raw), before)
                self.assertFalse(raw.HasOpenCommand())
                self.assert_original_untouched()

    def test_write_failure_rolls_back_native_payload_refs_writer_and_provenance(self):
        raw = document.read_bytes(self.original)
        before, undo_limit = document_state(raw), raw.GetUndoLimit()
        write = document._write_extra
        calls = []
        def fail_after_partial_write(label, material):
            write(label, material)
            calls.append(label)
            if len(calls) == 2:
                raise OSError("injected native payload failure")
        with mock.patch.object(document, "_write_extra", side_effect=fail_after_partial_write):
            with self.assertRaisesRegex(document_migrations.DocumentCompatibilityError, "injected native payload"):
                document_migrations.upgrade(raw)
        self.assertEqual(len(calls), 2, "the conversion reached real document writes")
        self.assertEqual(document_state(raw), before)
        self.assertEqual(raw.GetUndoLimit(), undo_limit)
        self.assertFalse(raw.HasOpenCommand())
        self.assert_original_untouched()

    def test_old_binary_reader_failure_is_not_an_evictable_held_source(self):
        with mock.patch.dict(build._HELD, clear=True):
            with mock.patch.object(document, "read_bytes", side_effect=ValueError("old binary reader failed")):
                with self.assertRaisesRegex(document_migrations.DocumentCompatibilityError, "xbf/8"):
                    build.held_source(self.original, "legacy-fixture")
            self.assertEqual(build._HELD, {})
        self.assert_original_untouched()

    def test_failed_atomic_migrated_save_preserves_existing_target_and_source(self):
        from OCP.PCDM import PCDM_StoreStatus

        source = export.Source.read(self.path)
        target = self.folder / "migrated.xbf"
        target.write_bytes(b"previous target stays recoverable")
        before = target.read_bytes()
        def fail_save(_doc, staged):
            Path(staged.ToExtString()).write_bytes(b"incomplete native document")
            return PCDM_StoreStatus.PCDM_SS_Failure
        with mock.patch.object(document, "_application") as app:
            app.return_value.SaveAs.side_effect = fail_save
            with self.assertRaises(OSError):
                export.translate(source, "xbf", target)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.folder.glob(".*.tmp")))
        self.assert_original_untouched()


if __name__ == "__main__":
    unittest.main()
