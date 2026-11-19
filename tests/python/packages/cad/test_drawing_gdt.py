"""A feature control frame's own rules, checked when it is made: no part, no
sheet and no kernel are needed to say that a frame cannot be read."""

from __future__ import annotations

import unittest


class FrameRuleTests(unittest.TestCase):
    def test_a_characteristic_measured_from_a_datum_names_one(self) -> None:
        from cad.eng_drawing import Frame

        for characteristic in ("angularity", "perpendicularity", "parallelism", "concentricity", "symmetry",
                               "circular_runout", "total_runout"):
            with self.subTest(characteristic=characteristic):
                with self.assertRaisesRegex(ValueError, "measured from a datum"):
                    Frame(characteristic, 0.05)
                self.assertEqual(Frame(characteristic, 0.05, ("A",)).datums, ("A",))
        # A profile with no datum controls form; a position with none holds a pattern to itself.
        for characteristic in ("line_profile", "surface_profile", "position"):
            self.assertEqual(Frame(characteristic, 0.1).datums, ())
        with self.assertRaisesRegex(ValueError, "names no datum"):
            Frame("flatness", 0.05, ("A",))

    def test_a_datum_is_one_letter_a_datum_can_carry(self) -> None:
        from cad.eng_drawing import Frame

        self.assertEqual(Frame("position", 0.1, ("a", "B")).datums, ("A", "B"))
        for datums in (("AB",), ("",), ("A", ""), ("I",), ("A", 1), ("A-B",), ("A", "A"), ("A", "B", "C", "D")):
            with self.subTest(datums=datums), self.assertRaisesRegex(ValueError, "letters"):
                Frame("position", 0.1, datums)
        with self.assertRaises(TypeError):
            Frame("position", 0.1, "A")
        with self.assertRaises(TypeError):
            Frame("position", 0.1, 5)

    def test_a_material_condition_goes_where_a_feature_of_size_is(self) -> None:
        from cad.eng_drawing import Frame

        for characteristic in ("position", "perpendicularity", "concentricity", "symmetry"):
            self.assertEqual(Frame(characteristic, 0.1, ("A",), modifier="M").modifier, "M")
        self.assertEqual(Frame("straightness", 0.1, diameter=True, modifier="M").modifier, "M")
        for characteristic, datums in (("flatness", ()), ("surface_profile", ("A",)), ("total_runout", ("A",))):
            with self.subTest(characteristic=characteristic), self.assertRaisesRegex(ValueError, "material condition"):
                Frame(characteristic, 0.1, datums, modifier="M")


if __name__ == "__main__":
    unittest.main()
