"""cadgen.color: authoring colours in the space you actually see."""

import unittest

from cadgen.color import linear_to_srgb, srgb, srgb_to_linear


class SrgbColorTest(unittest.TestCase):
    def test_hex_round_trips_through_linear(self):
        red, green, blue, _alpha = tuple(srgb("#808080"))
        for channel in (red, green, blue):
            self.assertEqual(round(linear_to_srgb(channel) * 255), 128)

    def test_channels_are_stored_linear_not_srgb(self):
        # The whole reason this helper exists: the renderer reads Color channels as
        # linear RGB, so mid-grey is ~0.216, not 0.5. Authoring 0.5 by hand
        # displays as byte 188.
        red, _g, _b, _a = tuple(srgb("#808080"))
        self.assertAlmostEqual(red, 0.2158605, places=5)
        self.assertEqual(round(linear_to_srgb(0.5) * 255), 188)

    def test_alpha_is_preserved(self):
        self.assertAlmostEqual(tuple(srgb("#38414D", 0.42))[3], 0.42, places=6)

    def test_short_and_long_hex_agree(self):
        self.assertAlmostEqual(tuple(srgb("#abc"))[0], tuple(srgb("#aabbcc"))[0], places=12)

    def test_leading_hash_is_optional(self):
        self.assertEqual(tuple(srgb("2E3742")), tuple(srgb("#2E3742")))

    def test_black_and_white_are_exact(self):
        self.assertEqual(tuple(srgb("#000000"))[:3], (0.0, 0.0, 0.0))
        for channel in tuple(srgb("#ffffff"))[:3]:
            self.assertAlmostEqual(channel, 1.0, places=6)

    def test_transfer_functions_are_inverses(self):
        for value in (0.0, 0.01, 0.04, 0.2, 0.5, 0.9, 1.0):
            self.assertAlmostEqual(linear_to_srgb(srgb_to_linear(value)), value, places=9)

    def test_bad_input_raises(self):
        for bad in ("nope", "#12", "#1234567", ""):
            with self.assertRaises(ValueError):
                srgb(bad)


if __name__ == "__main__":
    unittest.main()
