"""``cadgen._internal.fea.materials``: the table, the material object, and what an analysis may ask of it.

Stdlib only: no FEA stack. The table and the skill's materials reference must
agree number for number, and every value the table leaves out must say why.
"""

from __future__ import annotations

import dataclasses
import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.materials import (  # noqa: E402
    MATERIAL_PROPERTIES,
    MATERIALS,
    NONE_REASONS,
    TABLE_PROPERTIES,
    Material,
    lookup_material,
    material_from_spec,
    requires,
)

REFERENCE = Path(__file__).resolve().parents[4] / "skills" / "fea" / "references" / "materials.md"
# The columns of materials.md's "Strength, fatigue and heat" table after the name, as the table stores them.
COLUMNS = ("uts", "endurance", "endurance_cycles", "conductivity", "expansion", "specific_heat")
# The doc writes expansion in 1e-6/K, the table in 1/K.
DOC_FACTOR = {"expansion": 1e-6}


def _reference_rows() -> dict[str, list[str]]:
    """materials.md's property table: table key -> its cells after the name."""
    text = REFERENCE.read_text(encoding="utf-8")
    section = text[text.index("## Strength, fatigue and heat"):]
    rows = {}
    for line in section.splitlines():
        match = re.match(r"\|\s*`([a-z0-9-]+)`", line)
        if match:
            rows[match.group(1)] = [cell.strip() for cell in line.strip().strip("|").split("|")][1:]
    return rows


def _number(cell: str) -> float | None:
    if cell.lower().startswith("none"):
        return None
    cell = cell.split("(")[0]  # "60 (unverified)": the number, its status beside it
    return float(cell.replace(" ", "").replace(" ", ""))


class Table(unittest.TestCase):
    def test_every_material_has_every_property_or_a_reason(self):
        for key, material in MATERIALS.items():
            for attribute in TABLE_PROPERTIES:
                with self.subTest(material=key, property=attribute):
                    value = getattr(material, attribute)
                    if value is None:
                        self.assertIn((key, attribute), NONE_REASONS)
                    else:
                        self.assertGreater(value, 0)
                        self.assertNotIn((key, attribute), NONE_REASONS)

    def test_the_reference_gives_the_tables_numbers_and_every_reason(self):
        rows = _reference_rows()
        text = " ".join(REFERENCE.read_text(encoding="utf-8").split())
        self.assertEqual(set(rows), set(MATERIALS))
        for key, material in MATERIALS.items():
            for column, attribute in enumerate(COLUMNS):
                with self.subTest(material=key, property=attribute):
                    written = _number(rows[key][column])
                    value = getattr(material, attribute)
                    if value is None:
                        self.assertIsNone(written)
                    else:
                        self.assertIsNotNone(written)
                        self.assertAlmostEqual(written * DOC_FACTOR.get(attribute, 1.0) / value, 1.0, places=9)
        for reason in set(NONE_REASONS.values()):
            self.assertIn(reason, text)

    def test_every_material_names_its_sources(self):
        rows = _reference_rows()
        for key in MATERIALS:
            with self.subTest(material=key):
                self.assertTrue(rows[key][len(COLUMNS)].strip(), "the sources column is empty")

    def test_the_first_five_fields_keep_their_order(self):
        names = [f.name for f in dataclasses.fields(Material)][:5]
        self.assertEqual(names, ["name", "E", "nu", "yield_strength", "density"])
        self.assertEqual(Material("x", 1.0, 0.3, 1.0, 0.0).uts, None)


class MaterialObject(unittest.TestCase):
    def test_a_name_reads_the_table(self):
        self.assertIs(material_from_spec("6061"), lookup_material("aluminum-6061-t6"))

    def test_an_object_extends_a_table_entry_and_keeps_the_rest(self):
        steel = material_from_spec({"name": "steel", "yield_MPa": 355, "uts_MPa": 470, "conductivity_W_mK": 45})
        self.assertEqual((steel.yield_strength, steel.uts, steel.conductivity), (355.0, 470.0, 45.0))
        self.assertEqual(steel.specific_heat, MATERIALS["steel"].specific_heat)

    def test_a_polymer_gains_fatigue_data_under_either_name(self):
        for keys in (("endurance_MPa", "endurance_cycles"), ("fatigue_strength_MPa", "fatigue_cycles")):
            with self.subTest(keys=keys):
                pla = material_from_spec({"name": "pla", keys[0]: 18, keys[1]: 1e6})
                self.assertEqual((pla.endurance, pla.endurance_cycles), (18.0, 1e6))

    def test_plasticity_and_hyperelastic_objects(self):
        steel = material_from_spec({"name": "steel", "plasticity": {"tangent_MPa": 2000}})
        self.assertEqual(steel.tangent, 2000.0)
        rubber = material_from_spec({"name": "rubber", "E_MPa": 1.8, "nu": 0.49, "yield_MPa": 10,
                                     "hyperelastic": {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}})
        self.assertEqual(rubber.hyperelastic, {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300.0})

    def test_the_errors_name_the_field(self):
        cases = [
            ({"name": "steel", "uts_MPa": -1}, "material.uts_MPa"),
            ({"name": "steel", "conductivity_W_mK": "high"}, "material.conductivity_W_mK"),
            ({"name": "steel", "plasticity": {"tangent_MPa": 300_000}}, "below E"),
            ({"name": "steel", "plasticity": 5}, "material.plasticity"),
            ({"name": "steel", "hyperelastic": {"model": "mooney"}}, "material.hyperelastic.model"),
            ({"name": "steel", "hyperelastic": {"mu_MPa": 1}}, "bulk_MPa"),
            ({"E_MPa": 1}, "an object needs E_MPa, nu and yield_MPa"),
            (3, "give a name from the table"),
        ]
        for spec, fragment in cases:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError) as caught:
                material_from_spec(spec)
            self.assertIn(fragment, str(caught.exception))

    def test_as_dict_adds_only_the_keys_that_are_set(self):
        custom = material_from_spec({"E_MPa": 1000, "nu": 0.3, "yield_MPa": 10})
        self.assertEqual(set(custom.as_dict()), {"name", "E_MPa", "nu", "yield_MPa", "density_t_per_mm3"})
        steel = lookup_material("steel").as_dict()
        self.assertEqual(steel["uts_MPa"], MATERIALS["steel"].uts)
        self.assertNotIn("tangent_MPa", steel)
        self.assertNotIn("endurance_MPa", lookup_material("abs").as_dict())


class Requires(unittest.TestCase):
    def test_a_missing_property_is_asked_for_by_its_key(self):
        with self.assertRaises(ValueError) as caught:
            requires(lookup_material("abs"), ("uts", "endurance"), "fatigue")
        message = str(caught.exception)
        self.assertIn("fatigue studies need the fatigue strength", message)
        self.assertIn("endurance_MPa", message)
        self.assertIn('"name": "ABS"', message)

    def test_zero_density_is_missing(self):
        custom = material_from_spec({"E_MPa": 1000, "nu": 0.3, "yield_MPa": 10})
        with self.assertRaises(ValueError) as caught:
            requires(custom, ("density",), "modal")
        self.assertIn("density_t_per_mm3", str(caught.exception))
        requires(lookup_material("steel"), ("density", "conductivity", "expansion", "specific_heat"), "thermal_stress")

    def test_a_stress_check_on_a_rubber_asks_for_its_yield_strength(self):
        from cadgen._internal.fea.study import parse_study

        rubber = {"name": "rubber", "hyperelastic": {"model": "neo_hookean", "mu_MPa": 0.6, "bulk_MPa": 300}}
        study = {"analysis": "static", "material": rubber, "fixtures": [{"faces": ["#o1.f1"]}],
                 "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -10]}]}
        # A static study judges stress by default: a plain error naming what to add, not a TypeError later.
        for document in (study, {**study, "view": {"checks": [{"kind": "stress"}]}}):
            with self.assertRaises(ValueError) as caught:
                parse_study(document)
            message = str(caught.exception)
            self.assertIn("static studies need the yield strength, and rubber has none", message)
            self.assertIn('add yield_MPa to the material object, like {"name": "rubber", "yield_MPa": 10}', message)
        # Judged by displacement alone it needs no yield strength; given one, the stress check is judged.
        moved = parse_study({**study, "view": {"checks": [{"kind": "displacement", "limit_mm": 1}]}})
        self.assertIsNone(moved.material.yield_strength)
        self.assertEqual(parse_study({**study, "material": {**rubber, "yield_MPa": 8}}).material.yield_strength, 8.0)

    def test_an_analysis_with_isotropic_solids_refuses_an_orthotropic_material_naming_those_that_take_one(self):
        from cadgen._internal.fea.analyses import get_analysis
        from cadgen._internal.fea.study import ORTHOTROPIC_ANALYSES, parse_study

        block = {"E1_MPa": 135000, "E2_MPa": 10000, "E3_MPa": 10000, "nu12": 0.3, "nu13": 0.3, "nu23": 0.45,
                 "G12_MPa": 5000, "G13_MPa": 5000, "G23_MPa": 3500}
        # Steel with an orthotropic block, and everything else each analysis asks of its material.
        ortho = {"name": "steel", "orthotropic": block, "plasticity": {"tangent_MPa": 0},
                 "creep": {"A": 1e-20, "n": 5, "m": 0, "units": "MPa, hours"}}
        held = {"fixtures": [{"faces": ["#o1.f1"]}], "loads": [{"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -10]}]}
        bolt = {"between": ["plate", "bracket"], "type": "bolt", "size": "M6", "preload_N": 5000, "holes": ["#o1.1.f3", "#o1.2.f3"]}
        studies = {
            "nonlinear": {"analysis": "nonlinear", **held},
            "creep": {"analysis": "creep", "duration_h": 1000, **held},
            "contact": {"analysis": "contact", **held, "rigid_planes": [{"point_mm": [0, 0, 0], "normal": [0, 0, 1]}]},
            "bolt": {"analysis": "bolt", "fixtures": [{"faces": ["#o1.2.f1"]}], "connections": [bolt]},
            "impact": {"analysis": "impact", "drop": {"height_mm": 500}},
        }
        for name, study in studies.items():
            self.assertTrue(get_analysis(name).isotropic_only)
            isotropic = {key: value for key, value in ortho.items() if key != "orthotropic"}
            parse_study({**study, "material": isotropic})  # the same steel, the same in every direction: fine
            with self.subTest(analysis=name), self.assertRaises(ValueError) as caught:
                parse_study({**study, "material": ortho})
            message = str(caught.exception)
            self.assertIn(f"material: {name} studies treat a material as the same in every direction, and steel is orthotropic", message)
            self.assertIn("static, modal, buckling, harmonic, random_vibration, shock, transient, fatigue, drop and thermal_stress "
                          "studies take an orthotropic material", message)
        # An assembly's part made of one is refused the same way.
        with self.assertRaisesRegex(ValueError, "nonlinear studies treat a material as the same in every direction"):
            parse_study({**studies["nonlinear"], "material": "steel", "parts": {"rib": {"material": ortho}}})
        # The analyses named really take one: none of them is isotropic only, and a static study parses.
        for name in ORTHOTROPIC_ANALYSES:
            self.assertFalse(getattr(get_analysis(name), "isotropic_only", False), name)
        self.assertIsNotNone(parse_study({"analysis": "static", "material": ortho, **held}).material.orthotropic)

    def test_every_need_is_a_known_property(self):
        with self.assertRaises(KeyError):
            requires(lookup_material("steel"), ("colour",), "static")
        self.assertLessEqual(set(TABLE_PROPERTIES), set(MATERIAL_PROPERTIES))


if __name__ == "__main__":
    unittest.main()
