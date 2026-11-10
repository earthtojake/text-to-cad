"""The library's named looks (``cad.build123d.materials``): native bd_materials objects any release reads,
scalar looks every renderer draws, kept whole through an xbf and written into a GLB."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from bd_materials import FinishedMaterial

from cad.build123d import materials
from cad.engine import build as engine_build
from cad.engine import document

# Every factory at its defaults, and the parameters each takes.
VARIANTS = {name: f"materials.{name}()" for name in materials.__all__} | {
    "soldermask_blue_matte": "materials.soldermask('blue', finish='matte')",
    "soldermask_hex": "materials.soldermask('#204060')",
    "silkscreen_black": "materials.silkscreen('black')",
    "copper_oxidized": "materials.bare_copper(oxidized=True)",
    "hasl_leaded": "materials.hasl(lead_free=False)",
    "ceramic_tan": "materials.ceramic('tan')",
    "led_lens_red_diffused": "materials.led_lens('red', diffused=True)",
    "connector_housing_white": "materials.connector_housing('white')",
    "anodized_red_7075": "materials.anodized('red', substrate=metals.aluminum(metals.Alu.G7075_T6))",
    "powder_coat_ral_gloss": "materials.powder_coat('RAL7016', finish='gloss', substrate=metals.aluminum())",
    "powder_coat_matte_tuple": "materials.powder_coat((0.9, 0.2, 0.1), finish='matte')",
    "brushed_aluminum": "materials.brushed(substrate=metals.aluminum())",
    "zinc_plated_yellow": "materials.zinc_plated('yellow')",
    "black_oxide_dry": "materials.black_oxide(oiled=False)",
}

SCRIPT = '''
import build123d as bd
from bd_materials import metals
from cad import glb, xbf
from cad.build123d import materials

VARIANTS = {variants!r}

@xbf("looks.xbf")
@glb("looks.glb")
def looks():
    parts = []
    for at, (label, look) in enumerate(VARIANTS.items()):
        # A height each: a preset and its factory's default are one look, which equal parts would share.
        part = bd.Box(4, 4, 1 + at / 8).moved(bd.Location((at * 6, 0, 0)))
        part.material = eval(look)
        part.label = label
        parts.append(part)
    return bd.Compound(children=parts, label="looks")
'''


def made(expression: str) -> FinishedMaterial:
    from bd_materials import metals

    return eval(expression, {"materials": materials, "metals": metals})


class NamedLooksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="named-looks-")
        cls.folder = Path(cls.temp.name)
        script = cls.folder / "looks.py"
        script.write_text(textwrap.dedent(SCRIPT.format(variants=VARIANTS)), encoding="utf-8")
        report = engine_build.build(script, ["looks"], cwd=cls.folder)[0]
        assert report["ok"], report.get("error")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_look_is_a_native_material_of_a_class_every_release_reads_with_no_texture_map(self):
        for label, expression in VARIANTS.items():
            with self.subTest(label=label):
                look = made(expression)
                self.assertIsInstance(look, FinishedMaterial)
                self.assertTrue(type(look.material).__module__.startswith("bd_materials."), "no class of our own")
                encoded = document.material_json(look)
                restored = document.material_from_json(json.loads(json.dumps(encoded)))
                self.assertIs(type(restored.material), type(look.material), "one of the classes an xbf reads")
                self.assertFalse([key for key in document.TEXTURE_FIELDS if encoded["pbr"].get(key)],
                                 "a scalar look: a mesh has no UVs")
                self.assertIsNot(made(expression), look, "a fresh material per call")

    def test_each_look_builds_and_its_xbf_serves_what_was_written(self):
        prototypes = {p["name"]: p for p in document.Loaded(self.folder / "looks.xbf").structure()["prototypes"]}
        self.assertEqual(sorted(prototypes), sorted(VARIANTS))
        for label, expression in VARIANTS.items():
            with self.subTest(label=label):
                self.assertEqual(prototypes[label]["material"], document.material_json(made(expression)))
                self.assertNotIn("untextured", prototypes[label])

    def test_a_glb_writes_a_transmissive_and_a_metallic_look_s_factors(self):
        data = (self.folder / "looks.glb").read_bytes()
        gltf = json.loads(data[20:20 + int.from_bytes(data[12:16], "little")])
        written = {m["name"]: m for m in gltf["materials"]}
        lens = written["led_lens_clear"]
        self.assertEqual(lens["extensions"]["KHR_materials_transmission"]["transmissionFactor"], 1.0)
        self.assertEqual(lens["extensions"]["KHR_materials_ior"]["ior"], 1.5)
        self.assertEqual((lens["alphaMode"], lens["pbrMetallicRoughness"]["baseColorFactor"][3]), ("OPAQUE", 1.0))
        copper = written["copper_bare"]["pbrMetallicRoughness"]
        self.assertEqual((copper["metallicFactor"], copper["roughnessFactor"]), (1.0, 0.25))
        self.assertEqual(written["brushed_stainless"]["extensions"]["KHR_materials_anisotropy"]["anisotropyStrength"],
                         0.8)
        self.assertEqual(written["soldermask_green"]["extensions"]["KHR_materials_clearcoat"]["clearcoatFactor"], 0.6)

    def test_importing_the_module_loads_no_material_library_and_a_bad_choice_is_refused_by_name(self):
        code = ("import sys, cad.build123d.materials;"
                "print([m for m in ('bd_materials', 'threejs_materials', 'OCP') if m in sys.modules])")
        found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(found.stdout.strip(), "[]")
        import cad.build123d

        self.assertIs(cad.build123d.materials, materials)
        self.assertIn("materials", cad.build123d.__all__, "offered as the package's other members are")
        self.assertIn("materials", dir(cad.build123d))
        with self.assertRaisesRegex(ValueError, "soldermask's finish is one of 'glossy', 'matte', not 'satin'"):
            materials.soldermask(finish="satin")
        # A passivation is a chemistry, not a colour: one of four, spelled in any case.
        with self.assertRaisesRegex(ValueError, "zinc_plated's passivation is one of 'clear', 'blue', 'yellow', 'black', "
                                                "not '#cfb766'"):
            materials.zinc_plated("#cfb766")
        self.assertEqual(document.material_json(materials.zinc_plated(" Yellow ")),
                         document.material_json(materials.zinc_plated("yellow")))
        with self.assertRaisesRegex(TypeError, "substrate is a bd_materials FinishedMaterial"):
            materials.anodized(substrate="6061")
        for bad in ("", "light blue", (1, 2, 3), (0.1, 0.2)):
            with self.subTest(colour=bad), self.assertRaisesRegex(ValueError, "anodized: a colour is one of clear, "):
                materials.anodized(bad)

    def test_one_finish_is_one_material_whichever_spelling_asked_for_it(self):
        def same(*looks):
            first = document.material_json(looks[0])
            for look in looks[1:]:
                self.assertEqual(document.material_json(look), first)
            return looks[0].material.name

        black = (0x1e / 255, 0x1f / 255, 0x22 / 255)
        self.assertEqual(same(materials.anodized(), materials.anodized("silver"), materials.anodized("Clear ")),
                         "anodized_clear")
        self.assertEqual(same(materials.anodized("grey"), materials.anodized("gray")), "anodized_grey")
        self.assertEqual(same(materials.anodized_black(), materials.anodized("#1E1F22"), materials.anodized(black)),
                         "anodized_black", "a preset's own colour is the preset, its metalness included")
        self.assertEqual(same(materials.powder_coat("grey"), materials.powder_coat("gray"), materials.powder_coat("ral7016")),
                         "powder_coat_RAL7016_satin")
        self.assertEqual(same(materials.powder_coat("white"), materials.powder_coat("RAL9016")), "powder_coat_RAL9016_satin")
        self.assertEqual(same(materials.ceramic("beige"), materials.ceramic("tan")), "ceramic_tan")
        self.assertEqual(same(materials.led_lens("white"), materials.led_lens(), materials.led_lens("#ffffff")),
                         "led_lens_clear")
        self.assertEqual(same(materials.connector_housing("beige"), materials.connector_housing("natural")),
                         "connector_housing_natural")
        self.assertEqual(same(materials.anodized("navy"), materials.anodized("#000080")), "anodized_000080",
                         "any other colour is named by its sRGB hex")
        self.assertNotEqual(materials.powder_coat("black").material.name, materials.powder_coat("RAL9005").material.name,
                            "two shades are two materials")

    def test_a_finish_on_a_substrate_wears_its_own_look_not_the_substrate_s(self):
        from bd_materials import metals

        bare = materials.bead_blasted()
        on_anodize = materials.bead_blasted(substrate=materials.anodized_black())
        self.assertEqual(on_anodize.material.name, "bead_blasted_aluminum")
        self.assertEqual(on_anodize.pbr.values.color, bare.pbr.values.color, "the bare metal's colour, not the dye's")
        self.assertEqual(materials.brushed(substrate=materials.powder_coat("RAL3020", substrate=metals.stainless()))
                         .pbr.values.color, materials.brushed().pbr.values.color)
        self.assertEqual(materials.brushed(substrate=materials.solder()).pbr.values.color, materials.solder().pbr.values.color,
                         "a metal bd_materials has no family look for keeps its own")

    def test_a_coloured_lens_is_tinted_once(self):
        """three.js tints the light a transmissive look passes by its base colour, and again by its attenuation
        colour over the part's depth: a lens is tinted by its colour alone, so it is its colour, however thick."""
        for colour in ("red", "green", "blue", "amber", "yellow"):
            with self.subTest(colour=colour):
                lens = materials.led_lens(colour).pbr.values
                self.assertEqual((lens.transmission, lens.attenuation_distance), (1.0, None))
                self.assertIn(lens.attenuation_color, (None, [1.0, 1.0, 1.0], (1.0, 1.0, 1.0)))
                self.assertEqual("#" + "".join(f"{round(c * 255):02x}" for c in lens.color), materials.LED[colour])


if __name__ == "__main__":
    unittest.main()
