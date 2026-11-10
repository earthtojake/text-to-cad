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

from cad.engine import build as engine_build
from cad.engine import document, export, paint, reader
from cad.engine.colors import linear

FULL = FinishedMaterial(metals.aluminum().material, pbr=PbrProperties.create(
    "Full", color="#80a0c0", opacity=0.8, metalness=0.3, roughness=0.6, ior=1.45,
    anisotropy=0.4, anisotropy_rotation=0.7, transmission=0.5,
    attenuation_color=(0.9, 0.8, 0.7), attenuation_distance=0.02,
    clearcoat=0.6, clearcoat_roughness=0.15, emissive=(0.1, 0.2, 0.3), emissive_intensity=2.5))

SOURCE = '''
import build123d as bd
from bd_materials import metals
from cad import xbf, glb, step
from cad.build123d import memo, paint

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

    def test_a_step_declaring_kilograms_per_cubic_metre_reads_its_densities_as_it_says_them(self):
        """OCCT's STEP reader converts a density's length unit and drops its mass unit's prefix: a file
        in kg/m^3, what most CAD tools write, arrived 1000 times too light. A STEP the engine writes says
        grams and reads back as it was; one rewritten to say kg/m^3 reads the same density, by both the
        document loader and the reader process's parse."""
        import re

        shape = bd.Box(10, 10, 10)
        shape.material = metals.aluminum()  # 2700 kg/m^3
        self.roundtrip(shape)
        written = self.folder / "grams.step"
        export.translate(export.Source.read(self.folder / "test.xbf"), "step", written)
        density = lambda path: [prototype["material"]["material"]["density"]  # noqa: E731
                                for prototype in export.Source.read(path).structure["prototypes"]]
        self.assertEqual(density(written), [2700.0])
        text = written.read_text(encoding="latin-1")
        item = re.search(r"MEASURE_REPRESENTATION_ITEM\('density',[^,]*,#\d+\)", text)
        self.assertIsNotNone(item, "the engine's STEP names a density")
        # As Fusion 360 writes it: the value in kg/m^3, a derived unit of kilogram over metre cubed.
        kilograms = (item.group(0).replace("'density',", "'density measure',POSITIVE_RATIO_MEASURE(")
                     .split(",POSITIVE_RATIO_MEASURE(")[0]
                     + ",POSITIVE_RATIO_MEASURE(2700.),#9001)")
        units = ("#9001=DERIVED_UNIT((#9002,#9003));\n#9002=DERIVED_UNIT_ELEMENT(#9004,1.);\n"
                 "#9003=DERIVED_UNIT_ELEMENT(#9005,-3.);\n#9004=(MASS_UNIT()NAMED_UNIT(*)SI_UNIT(.KILO.,.GRAM.));\n"
                 "#9005=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.));\n")
        rewritten = self.folder / "kilograms.step"
        rewritten.write_text(re.sub(r"ENDSEC;\s*END-ISO", lambda end: units + end.group(0),
                                    text.replace(item.group(0), kilograms), count=1), encoding="latin-1")
        self.assertEqual(density(rewritten), [2700.0])
        header, _packed = reader._parse(str(rewritten))
        self.assertEqual([product["material"]["material"]["density"] for product in header["products"]
                          if product.get("material")], [2700.0])

    def test_every_density_with_a_unit_of_its_own_is_read_as_it_says_it_however_its_units_are_written(self):
        """Each of a STEP's densities in kg/m^3 is read as it says it when each names units of its own, written
        as CAD tools write them: a measure and entities across lines, complex entities spaced or not, a derived
        unit's elements in either order, a number that another begins (``#90004`` and ``#900041``, the second
        first); a STEP declaring no density reads none."""
        import re

        parts = []
        for at, material in enumerate((metals.aluminum(), metals.mild_steel(), metals.copper())):
            part = bd.Box(10, 10, 10).moved(bd.Location((20 * at, 0, 0)))
            part.label, part.material = f"part{at}", material
            parts.append(part)
        self.roundtrip(bd.Compound(children=parts, label="parts"))
        written = self.folder / "grams.step"
        export.translate(export.Source.read(self.folder / "test.xbf"), "step", written)
        density = lambda path: sorted(prototype["material"]["material"]["density"]  # noqa: E731
                                      for prototype in export.Source.read(path).structure["prototypes"])
        declared = density(written)
        self.assertEqual(len(declared), 3)
        text = written.read_text(encoding="latin-1")
        items = re.findall(r"MEASURE_REPRESENTATION_ITEM\('density',([-+0-9.Ee]+),#\d+\)", text)
        self.assertEqual(len(items), 3, "the engine's STEP names three densities")
        rewritten, units = text, []
        for index, value in enumerate(items):
            at = 9000 + 100 * index  # a unit set of its own, each written differently
            kilograms = round(float(value) * 1000.0, 6)  # g/cm^3 as kg/m^3
            mass = (f"#{at}4 = (\nMASS_UNIT ( )\nNAMED_UNIT ( * )\nSI_UNIT ( .KILO. , .GRAM. )\n) ;" if index == 0
                    else f"#{at}4=(MASS_UNIT()NAMED_UNIT(*)SI_UNIT(.KILO.,.GRAM.));")
            length = f"#{at}5=( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );"
            elements = f"(#{at}3,#{at}2)" if index == 1 else f"(#{at}2,#{at}3)"
            units += [f"#{at}41=(MASS_UNIT()NAMED_UNIT(*)SI_UNIT($,.GRAM.));",  # begins as #{at}4 does, and comes first
                      f"#{at}1=DERIVED_UNIT(\n  {elements}\n);" if index == 2 else f"#{at}1=DERIVED_UNIT({elements});",
                      f"#{at}2=DERIVED_UNIT_ELEMENT(#{at}4,1.);", f"#{at}3=DERIVED_UNIT_ELEMENT(#{at}5,-3.);",
                      mass, length]
            rewritten = re.sub(rf"MEASURE_REPRESENTATION_ITEM\('density',{re.escape(value)},#\d+\)",
                               f"MEASURE_REPRESENTATION_ITEM('density measure',\nPOSITIVE_RATIO_MEASURE({kilograms!r}),"
                               f"#{at}1)", rewritten, count=1)
        rewritten = re.sub(r"ENDSEC;\s*END-ISO", lambda end: "\n".join(units) + "\n" + end.group(0), rewritten, count=1)
        path = self.folder / "kilograms.step"
        path.write_text(rewritten, encoding="latin-1")
        self.assertEqual(density(path), declared)
        header, _packed = reader._parse(str(path))
        self.assertEqual(sorted(product["material"]["material"]["density"] for product in header["products"]
                                if product.get("material")), declared)
        plain = self.folder / "plain.step"
        bd.export_step(bd.Box(10, 10, 10), str(plain))
        self.assertEqual([prototype.get("material") for prototype in export.Source.read(plain).structure["prototypes"]],
                         [None])

    def test_a_step_s_user_defined_attributes_are_no_materials(self):
        """A CAD tool writes a part's parameters as user-defined attributes, which OCCT's reader takes for materials
        named for the parameter: no material is read of one, by the document loader or the reader process's parse;
        one naming a material is read as the material it names."""
        import re

        def written(attributes: tuple[tuple[str, str], ...]) -> Path:
            path = self.folder / f"{attributes[-1][0].lower()}.step"
            box = bd.Box(10, 10, 10)
            box.label = "block"
            bd.export_step(box, str(path))
            text = path.read_text(encoding="latin-1")
            definition = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(", text).group(1)
            context = re.search(r"#(\d+)\s*=\s*\(\s*GEOMETRIC_REPRESENTATION_CONTEXT", text).group(1)
            at, rows = 9000, []
            for name, value in attributes:  # as a CAD tool writes a parameter
                rows += [f"#{at}=PROPERTY_DEFINITION('{name}','user defined attribute',#{definition});",
                         f"#{at + 1}=GENERAL_PROPERTY('','{name}','user defined attribute');",
                         f"#{at + 2}=GENERAL_PROPERTY_ASSOCIATION('user defined attribute','',#{at + 1},#{at});",
                         f"#{at + 3}=DESCRIPTIVE_REPRESENTATION_ITEM('{name}','{value}');",
                         f"#{at + 4}=REPRESENTATION('',(#{at + 3}),#{context});",
                         f"#{at + 5}=PROPERTY_DEFINITION_REPRESENTATION(#{at},#{at + 4});"]
                at += 10
            path.write_text(re.sub(r"ENDSEC;\s*END-ISO", lambda end: "\n".join(rows) + "\n" + end.group(0), text,
                                   count=1), encoding="latin-1")
            return path

        def materials(path: Path) -> tuple[list, list]:
            loaded = [(prototype.get("material") or {}).get("material")
                      for prototype in export.Source.read(path).structure["prototypes"]]
            header, _packed = reader._parse(str(path))
            parsed = [(product.get("material") or {}).get("material") for product in header["products"]]
            return [found and found["name"] for found in loaded], [found and found["name"] for found in parsed]

        self.assertEqual(materials(written((("QTY", ""), ("PTC_COMMON_NAME", "block.prt")))), ([None], [None]))
        self.assertEqual(materials(written((("PTC_MATERIAL_NAME", "STEEL"),))), (["STEEL"], ["STEEL"]))

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
        from cad.engine.render.finish import finish

        with self.assertRaisesRegex(ValueError, "texture maps require UV mapping"):
            finish(document.material_color(material), encoded)
        with self.assertRaisesRegex(ValueError, "texture maps requires UV mapping"):
            export.translate(export.Source.read(self.folder / "test.xbf"), "glb", self.folder / "test.glb")
        self.assertFalse((self.folder / "test.glb").exists())

    def test_future_material_document_format_is_refused_and_current_format_reloads(self):
        from OCP.Standard import Standard_GUID
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDataStd import TDataStd_AsciiString
        from cad.engine import previous

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
