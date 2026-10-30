"""``cadgen._internal.fea.materials``: a study's own material object, and the model's material read off its document.

No FEA stack: the document's material is bd_materials' own, built here as a model sets it.
"""

from __future__ import annotations

import unittest

from tests.python.support.fea_fixtures import value_error

from cadgen._internal.fea.materials import material_from_document, material_from_spec  # noqa: E402

OWN = {"E_MPa": 1000, "nu": 0.3, "yield_MPa": 10}


class MaterialObject(unittest.TestCase):
    def test_the_errors_name_the_field(self):
        cases = [
            ({**OWN, "uts_MPa": 400}, "material: unknown keys ['uts_MPa']; a material object takes name, E_MPa, nu"),
            ({**OWN, "nu": 0.5}, "material.nu: Poisson's ratio must be in [0, 0.5)"),
            ({**OWN, "yield_MPa": 0}, "material.yield_MPa: must be > 0"),
            ({**OWN, "density_t_per_mm3": -1}, "material.density_t_per_mm3: must be zero or more"),
            ({"E_MPa": 1}, "an object needs E_MPa, nu and yield_MPa (density_t_per_mm3 optional); it has no nu, yield_MPa"),
            ({**OWN, "name": ""}, "material.name: a material's name is text"),
            # A name alone is no material: no table reads an alloy off it.
            ("6061", "give an object with E_MPa, nu and yield_MPa"),
            ({"name": "steel", "yield_MPa": 355}, "it has no E_MPa, nu"),
        ]
        for spec, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, value_error(self, material_from_spec, spec))

    def test_as_dict_names_the_numbers_and_where_they_are_from(self):
        custom = material_from_spec(OWN)
        self.assertEqual(custom.as_dict(), {"name": "Custom", "E_MPa": 1000.0, "nu": 0.3, "yield_MPa": 10.0,
                                            "density_t_per_mm3": 0.0, "source": "study"})


class ModelMaterial(unittest.TestCase):
    """The material a model sets (``part.material = bd_materials.metals.aluminum()``), as its document holds it."""

    def test_yield_is_the_low_end_and_stiffness_the_middle(self):
        import bd_materials

        aluminium = material_from_document(bd_materials.metals.aluminum(), "'plate'")
        physics = bd_materials.metals.aluminum().material
        self.assertEqual(aluminium.yield_strength, physics.yield_strength.min)         # 240 of 240-280 MPa
        self.assertAlmostEqual(aluminium.E, (physics.modulus_of_elasticity.min + physics.modulus_of_elasticity.max) / 2 * 1000)
        self.assertAlmostEqual(aluminium.nu, (physics.poisson_ratio.min + physics.poisson_ratio.max) / 2)
        self.assertAlmostEqual(aluminium.density, physics.density * 1e-12)              # kg/m^3 -> t/mm^3
        said = aluminium.as_dict()
        self.assertEqual(said["source"], "document")
        self.assertEqual(said["ranges"]["yield_MPa"], [physics.yield_strength.min, physics.yield_strength.max])

    def test_a_part_with_no_material_or_no_mechanics_is_refused(self):
        from bd_materials.core import RangeMaterial
        from bd_materials import FinishedMaterial

        with self.assertRaisesRegex(ValueError, r"'post' has no material: set part.material in its model"):
            material_from_document(None, "'post'")
        # A STEP keeps a material's name and density, and none of its mechanics.
        named = FinishedMaterial(RangeMaterial(name="Alu_G6061_T6", density=2700.0))
        with self.assertRaisesRegex(ValueError, r"'post''s material Alu_G6061_T6 gives no modulus_of_elasticity, "
                                                r"poisson_ratio, yield_strength: .*solve the model's \.xbf"):
            material_from_document(named, "'post'")


if __name__ == "__main__":
    unittest.main()
