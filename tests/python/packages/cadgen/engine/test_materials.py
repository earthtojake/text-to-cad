"""Native materials through build123d, the engine, XBF, STEP, GLB, paints and warm edits."""
from __future__ import annotations

import base64
import copy
import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

import build123d as bd
from bd_materials import FinishedMaterial, metals
from bd_materials.core import Range
from threejs_materials import PbrProperties
from PIL import Image

from cadgen.engine import build as engine_build
from cadgen.engine import document, export, paint, reader
from cadgen.engine.colors import linear

FULL = FinishedMaterial(metals.aluminum().material, pbr=PbrProperties.create(
    "Full", color="#80a0c0", opacity=0.8, metalness=0.3, roughness=0.6, ior=1.45,
    anisotropy=0.4, anisotropy_rotation=0.7, transmission=0.5,
    attenuation_color=(0.9, 0.8, 0.7), attenuation_distance=0.02,
    clearcoat=0.6, clearcoat_roughness=0.15, emissive=(0.1, 0.2, 0.3), emissive_intensity=2.5))

SOURCE = '''
import build123d as bd
from bd_materials import metals
from cadgen import memo, paint, xbf, glb, step

FINISH = metals.aluminum()
FINISH.pbr = FINISH.pbr.override(roughness=ROUGHNESS, anisotropy=0.4,
    anisotropy_rotation=0.7, transmission=0.5, attenuation_color=(0.9, 0.8, 0.7),
    attenuation_distance=0.02, clearcoat=0.6, clearcoat_roughness=0.15,
    emissive=(0.1, 0.2, 0.3), emissive_intensity=2.5, ior=1.45)

@memo
def block():
    return bd.Box(20, 10, 4)

@xbf("assembly.xbf")
@glb("assembly.glb")
@step("assembly.step")
def assembly():
    left = block()
    left.label = "left"
    right = left.moved(bd.Location((30, 0, 0)))
    left.material = FINISH
    paint(left, left.faces().sort_by(bd.Axis.Z)[-1], metals.copper())
    right.label = "right"
    right.material = metals.mild_steel()
    return bd.Compound(children=[left, right], label="assembly")
'''


class MaterialsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-materials-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def roundtrip(self, shape):
        tree = document.collect(shape, "test")
        path = self.folder / "test.xbf"
        document.save(document.to_xcaf(tree), path, compare=False, tree=tree)
        return document.Loaded(path)

    def test_native_assignment_mass_copy_and_explicit_colour(self):
        shape = bd.Box(10, 10, 10)
        shape.material = metals.aluminum()
        self.assertIsInstance(shape.material, FinishedMaterial)
        self.assertAlmostEqual(shape.mass(), 2.7)
        moved = shape.moved(bd.Location((20, 0, 0)))
        self.assertEqual(document.material_key(moved.material), document.material_key(shape.material))
        shape.color = bd.Color("red")
        part = self.roundtrip(shape).prototypes[0]
        self.assertEqual(part.color, linear("#ff0000"))
        self.assertEqual(part.material.material, shape.material.material)
        self.assertAlmostEqual(part.material.material.mass(1000), 2.7)
        self.assertIsInstance(part.material.material.yield_strength, Range)

    def test_physics_and_every_existing_appearance_control_survive_xbf_and_reader(self):
        shape = bd.Box(10, 20, 3)
        shape.material = copy.deepcopy(FULL)
        paint(shape, shape.faces()[0], FULL)
        loaded = self.roundtrip(shape)
        part = loaded.prototypes[0]
        self.assertEqual(part.material.material, FULL.material)
        values = FULL.pbr.to_dict()["values"]
        for field, expected in values.items():
            if field == "color":
                continue  # XCAF's base colour is a rounded linear float.
            self.assertEqual(part.material.pbr.to_dict()["values"][field], expected, field)
        face = next(iter(part.face_materials.values()))
        self.assertEqual(face.material, FULL.material)
        self.assertEqual(face.pbr.values.clearcoat, 0.6)
        structure = loaded.structure()
        self.assertEqual(structure["prototypes"][0]["material"]["pbr"]["values"]["emissiveIntensity"], 2.5)
        restored = reader.read_xbf(self.folder / "test.xbf").children[0]
        self.assertIsInstance(restored.material, FinishedMaterial)
        self.assertAlmostEqual(restored.mass(), shape.mass())

    def test_inherited_material_and_equal_placements_share_a_prototype(self):
        left = bd.Box(2, 3, 4)
        right = left.moved(bd.Location((10, 0, 0)))
        root = bd.Compound(children=[left, right])
        root.material = metals.copper()
        tree = document.collect(root, "pair")
        self.assertEqual(len(tree.parts), 1)
        self.assertEqual(tree.parts[0].material.material.density, metals.copper().material.density)
        for actual, expected in zip(tree.parts[0].color, document.material_color(root.material)):
            self.assertAlmostEqual(actual, expected, delta=1e-4)
        root.color = bd.Color("red")
        coloured = self.roundtrip(root)
        self.assertEqual(coloured.prototypes[0].color, linear("#ff0000"))
        self.assertEqual(coloured.prototypes[0].material.material.density, metals.copper().material.density)

    def test_material_serialization_embeds_textures_and_keeps_transforms(self):
        material = copy.deepcopy(FULL)
        material.pbr.texture_repeat = (2, 3)
        material.pbr.texture_rotation = 27
        material.pbr.normalize_uvs = False
        image = io.BytesIO()
        Image.new("RGB", (1, 1), "red").save(image, format="PNG")
        material.pbr.maps.color = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
        encoded = document.material_json(material)
        restored = document.material_from_json(json.loads(json.dumps(encoded)))
        self.assertEqual(restored.pbr.to_dict(), material.pbr.to_dict())
        self.assertIs(type(restored.material), type(material.material))
        self.assertEqual(document.material_key(restored), document.material_key(material))
        shape = bd.Box(1, 2, 3)
        shape.material = material
        self.assertEqual(self.roundtrip(shape).prototypes[0].material.pbr.to_dict(), material.pbr.to_dict())
        from cadgen.engine.render.finish import finish

        with self.assertRaisesRegex(ValueError, "texture maps require UV mapping"):
            finish(document.material_color(material), encoded)
        with self.assertRaisesRegex(ValueError, "texture maps requires UV mapping"):
            export.translate(export.Source.read(self.folder / "test.xbf"), "glb", self.folder / "test.glb")
        self.assertFalse((self.folder / "test.glb").exists())

    def test_future_material_document_format_is_refused_and_current_format_reloads(self):
        from OCP.Standard import Standard_GUID
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDataStd import TDataStd_AsciiString
        from cadgen.engine import previous

        shape = bd.Box(1, 2, 3)
        shape.material = copy.deepcopy(FULL)
        current = self.roundtrip(shape)
        self.assertEqual(document.material_key(current.prototypes[0].material), document.material_key(shape.material))
        path = self.folder / "test.xbf"
        TDataStd_AsciiString.Set_s(current.doc.Main(), Standard_GUID(document.WRITER_GUID),
                                 TCollection_AsciiString("cadgen.engine xbf/99 (cadgen 9.9.9)"))
        document.save(current.doc, path, compare=False)
        original = path.read_bytes()
        for read in (document.Loaded, reader.read_xbf):
            with self.subTest(read=read.__name__), self.assertRaisesRegex(
                    ValueError, f"unsupported document format xbf/99.*expected {previous.FORMAT}"):
                read(path)
        self.assertEqual(path.read_bytes(), original)

    def test_warm_material_edit_updates_exports_without_geometry_work(self):
        script = self.folder / "model.py"
        def build(roughness):
            script.write_text(textwrap.dedent(SOURCE.replace("ROUGHNESS", str(roughness))), encoding="utf-8")
            report = engine_build.build(script, ["assembly"], cwd=self.folder)[0]
            self.assertTrue(report["ok"], report.get("error"))
            return report
        build(0.25)
        before = document.Loaded(self.folder / "assembly.xbf").structure()
        report = build(0.75)
        after = document.Loaded(self.folder / "assembly.xbf").structure()
        self.assertEqual([p["key"] for p in before["prototypes"]], [p["key"] for p in after["prototypes"]])
        left = next(p for p in after["prototypes"] if p["name"] == "left")
        self.assertEqual(left["material"]["pbr"]["values"]["roughness"], 0.75)
        self.assertEqual(report["memo"]["misses"], 0, report["memo"])
        data = (self.folder / "assembly.glb").read_bytes()
        length = int.from_bytes(data[12:16], "little")
        gltf = json.loads(data[20:20 + length])
        material = next(m for m in gltf["materials"] if m["name"] == metals.aluminum().name)
        self.assertEqual(material["pbrMetallicRoughness"]["roughnessFactor"], 0.75)
        extensions = material["extensions"]
        self.assertEqual(extensions["KHR_materials_clearcoat"]["clearcoatFactor"], 0.6)
        self.assertEqual(extensions["KHR_materials_anisotropy"]["anisotropyRotation"], 0.7)
        self.assertEqual(extensions["KHR_materials_emissive_strength"]["emissiveStrength"], 2.5)
        self.assertEqual(extensions["KHR_materials_volume"]["attenuationDistance"], 0.02)
        step = reader.read_step(self.folder / "assembly.step")
        densities = {child.material.material.density for child in step.children}
        self.assertIn(metals.aluminum().material.density, densities)
        self.assertIn(metals.mild_steel().material.density, densities)

    def test_mutation_changes_content_key_and_rejects_arbitrary_reconstruction_types(self):
        changed = copy.deepcopy(FULL)
        shape = bd.Box(1, 2, 3)
        shape.material = changed
        key = document.material_key(changed)
        changed.pbr.values.roughness = 0.12
        self.assertNotEqual(document.material_key(changed), key)
        changed.pbr = changed.pbr.override(clearcoat=0.9)
        part = self.roundtrip(shape).prototypes[0]
        self.assertEqual(part.material.pbr.values.roughness, 0.12)
        self.assertEqual(part.material.pbr.values.clearcoat, 0.9)
        payload = document.material_json(changed)
        payload["type"] = "os.system"
        with self.assertRaises(KeyError):
            document.material_from_json(payload)


if __name__ == "__main__":
    unittest.main()
