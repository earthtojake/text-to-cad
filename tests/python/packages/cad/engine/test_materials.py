"""Native materials through build123d, the engine, XBF, STEP, GLB, paints and warm edits."""
from __future__ import annotations

import base64
import copy
import io
import json
import re
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

import build123d as bd
from bd_materials import FinishedMaterial, glass, metals, plastics
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

    def test_texture_maps_kept_in_the_xbf_are_drawn_as_the_scalar_look_and_named(self):
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
        board = bd.Box(1, 2, 3)
        board.material = material
        board.label = "board"
        plain = bd.Box(1, 2, 3).moved(bd.Location((5, 0, 0)))
        plain.material = metals.copper()
        plain.label = "plain"
        loaded = self.roundtrip(bd.Compound(children=[board, plain], label="pair"))
        self.assertEqual(loaded.prototypes[0].material.pbr.to_dict(), material.pbr.to_dict(), "the xbf keeps them whole")
        # Not drawn yet (a mesh has no UVs): every renderer draws the scalar look, and the structure
        # names what each leaves out, once, from the materials.
        prototypes = {p["name"]: p for p in loaded.structure()["prototypes"]}
        name = material.material.name
        self.assertEqual(prototypes["board"]["untextured"], {name: ["color"]})
        self.assertNotIn("untextured", prototypes["plain"])
        from cad.engine.render.finish import finish

        drawn = finish(document.material_color(material), encoded)
        self.assertEqual((drawn["metallic"], drawn["ior"]), (0.3, 1.45), "the still: its scalar look")
        told: list[str] = []
        export.translate(export.Source.read(self.folder / "test.xbf"), "glb", self.folder / "test.glb", told=told.append)
        self.assertEqual(told, [f"test.glb: board: {name}'s color map not written: textures are not drawn yet, "
                                "so the part wears its material's scalar look"])
        data = (self.folder / "test.glb").read_bytes()
        gltf = json.loads(data[20:20 + int.from_bytes(data[12:16], "little")])
        self.assertFalse({"images", "textures", "samplers"} & set(gltf), "no image in the file")
        written = {m["name"]: m for m in gltf["materials"]}
        self.assertNotIn("baseColorTexture", written[name]["pbrMetallicRoughness"])
        self.assertEqual([written[name]["pbrMetallicRoughness"][key] for key in ("metallicFactor", "roughnessFactor")],
                         [0.3, 0.6], "the GLB: its scalar factors")
        self.assertIn(metals.copper().material.name, written)

    def test_a_glb_writes_a_transmissive_look_opaque_unless_its_opacity_fades_it(self):
        from cad.engine.export.glb import _material

        def written(rgba, material):
            entry = _material(rgba, document.material_json(material), 2.0)
            return entry["alphaMode"], entry["pbrMetallicRoughness"]["baseColorFactor"][3]

        clear = glass.borosilicate()
        self.assertEqual(written((0.9, 0.9, 0.9, 0.3), clear), ("OPAQUE", 1.0), "the alpha build123d's setter inferred")
        faded = plastics.pmma()
        faded.pbr = faded.pbr.override(opacity=0.5)
        self.assertEqual(written((1.0, 1.0, 1.0, 0.3), faded), ("BLEND", 0.5), "the author's fade, whatever the colour says")
        self.assertEqual(written((0.5, 0.5, 0.5, 0.4), metals.brass()), ("BLEND", 0.4), "no transmission: the colour's own")

    def test_a_transmissive_material_at_alpha_1_previews_as_build123d_infers_and_a_lower_alpha_is_its_own(self):
        from cad.engine.formats.gltf import preview_alpha

        self.assertEqual([preview_alpha(1.0, 0.6), preview_alpha(1.0, 1.0), preview_alpha(0.5, 0.6), preview_alpha(1.0, 0.0)],
                         [0.58, 0.3, 0.5, 1.0])
        for opacity in (0.0, 0.4, 0.75):
            look = plastics.pmma(opacity=opacity).pbr
            self.assertEqual(preview_alpha(1.0, look.values.transmission), look.interpolate_color()[3], "the setter's own")

    def test_the_viewer_previews_a_transmissive_look_as_the_engine_does_case_for_case(self):
        """``@cad/core``'s ``previewOpacity.js`` is the viewer's copy of the one fade; its
        ``previewOpacity.parity.json`` is asserted there and here, so the two cannot drift."""
        from cad.engine.export.glb import _alpha
        from cad.engine.formats.gltf import preview_alpha
        from cad.engine.render.finish import finish
        from tests.python.support.paths import repo_path

        cases = json.loads(repo_path("packages", "core", "src", "lib", "render", "previewOpacity.parity.json")
                           .read_text(encoding="utf-8"))
        self.assertTrue(cases["previewCases"] and cases["lookCases"])
        for case in cases["previewCases"]:
            with self.subTest(why=case["why"]):
                self.assertEqual(preview_alpha(case["alpha"], case["transmission"]), case["preview"])
        for case in cases["lookCases"]:
            with self.subTest(why=case["why"]):
                fade = {} if case["opacity"] is None else {"opacity": case["opacity"]}
                look = FinishedMaterial(plastics.pmma().material, pbr=PbrProperties.create(
                    "case", color="#ffffff", transmission=case["transmission"], **fade))
                self.assertEqual(look.pbr.interpolate_color()[3], case["preview"], "build123d's setter infers it")
                for alpha in (1.0, case["preview"], 0.3):  # whatever the colour's alpha
                    self.assertEqual(_alpha((1.0, 1.0, 1.0, alpha), look.pbr.values), case["transmitted"], "a GLB")
                    self.assertAlmostEqual(finish((1.0, 1.0, 1.0, alpha), document.material_json(look))["alpha"],
                                           case["preview"], places=9, msg="a still")
                self.assertEqual(preview_alpha(case["transmitted"], case["transmission"]), case["preview"],
                                 "what reads the GLB and draws no transmission")

    def test_a_still_draws_a_clear_lens_at_its_preview_and_a_faded_one_at_its_own_fade(self):
        from cad.build123d import materials
        from cad.engine.render.finish import finish

        def still(look, rgba=None):
            return finish(rgba if rgba is not None else document.material_color(look),
                          document.material_json(look))["alpha"]

        lens = materials.led_lens()
        self.assertEqual(lens.pbr.values.transmission, 1.0)
        self.assertAlmostEqual(still(lens), 0.3, places=6, msg="a clear lens is drawn, not gone")
        self.assertAlmostEqual(still(lens, (1.0, 1.0, 1.0, 1.0)), 0.3, places=6, msg="whatever its colour's alpha")
        self.assertAlmostEqual(still(lens, (1.0, 1.0, 1.0, 0.3)), 0.3, places=6, msg="the setter's preview, not twice")
        faded = plastics.pmma()
        faded.pbr = faded.pbr.override(opacity=0.5)
        self.assertAlmostEqual(still(faded), 0.5, places=6, msg="the author's fade, as a GLB writes it")
        self.assertAlmostEqual(still(metals.brass(), (0.5, 0.5, 0.5, 0.4)), 0.4, places=6, msg="no transmission")

    def test_a_glb_s_transmissive_part_reads_as_the_xbf_s_in_a_still_and_a_3mf(self):
        from cad.engine import formats
        from cad.engine.render.finish import finish

        script = self.folder / "pane.py"
        script.write_text(textwrap.dedent('''
            import build123d as bd
            from bd_materials import plastics
            from cad import glb, xbf

            @xbf("pane.xbf")
            @glb("pane.glb")
            def pane():
                part = bd.Box(20, 10, 2)
                part.material = plastics.pmma(opacity=0.4)
                return part
        '''), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["pane"], cwd=self.folder)[0]["ok"])
        (prototype,) = formats.read(self.folder / "pane.glb").structure["prototypes"]
        material = prototype["material"] or next(iter(prototype["faceMaterials"].values()))
        self.assertEqual(material["pbr"]["values"]["transmission"], 0.6, "matched by name and factors at alpha 1")
        rgba = prototype["color"] or next(iter(prototype["faceColors"].values()))
        # A still draws no transmission: the preview alpha, once, not faded again by the transmission.
        self.assertAlmostEqual(finish(rgba, material)["alpha"], 0.58, places=5)
        (own,) = document.Loaded(self.folder / "pane.xbf").structure()["prototypes"]
        self.assertAlmostEqual(finish(own["color"], own["material"])["alpha"], 0.58, places=5, msg="the xbf's still")
        direct, converted = self.folder / "direct.3mf", self.folder / "converted.3mf"
        export.translate(self.folder / "pane.xbf", None, direct)
        export.translate(self.folder / "pane.glb", None, converted)
        colours = [re.findall(r'displaycolor="([^"]+)"', zipfile.ZipFile(path).read("3D/3dmodel.model").decode())
                   for path in (direct, converted)]
        self.assertEqual(colours[0], colours[1])
        self.assertEqual(colours[0][0][-2:], "94", "alpha 0.58")

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
