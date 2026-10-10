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

    def test_every_need_is_a_known_property(self):
        with self.assertRaises(KeyError):
            requires(lookup_material("steel"), ("colour",), "static")
        self.assertLessEqual(set(TABLE_PROPERTIES), set(MATERIAL_PROPERTIES))


if __name__ == "__main__":
    unittest.main()
