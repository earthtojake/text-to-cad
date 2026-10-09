"""``cadgen._internal.fea.checks``: a solved study as findings in plain words. Pure: no FEA stack."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.checks import Solved, findings, needs_finer  # noqa: E402


def solved(**changes):
    base = dict(
        material_name="6061-T6",
        yield_MPa=276.0,
        peak_MPa=47.3,
        peak_gauss_MPa=59.7,
        peak_at=(10.0, 40.0, 5.0),
        peak_face="#o1.f12",
        fixed_faces=("#o1.f3",),
        max_displacement_mm=0.029,
        displacement_at=(10.0, 60.0, 5.0),
        bbox_diagonal_mm=90.0,
        margin=2.0,
        coarser_peak_MPa=None,
        part="bracket",
    )
    base.update(changes)
    return Solved(**base)


class ChecksTest(unittest.TestCase):
    def test_a_safe_part_has_nothing_to_say(self):
        self.assertEqual(findings(solved()), [])

    def test_yields(self):
        (f,) = findings(solved(peak_MPa=310.0, peak_gauss_MPa=320.0))
        self.assertEqual((f["severity"], f["type"]), ("error", "yields"))
        self.assertEqual(f["summary"], "The bracket yields: peak stress 310 MPa is above 6061-T6's 276 MPa yield strength")
        self.assertEqual(f["items"][0]["ref"], "#o1.f12")

    def test_low_margin(self):
        (f,) = findings(solved(peak_MPa=197.0, peak_gauss_MPa=200.0))  # SF 1.40
        self.assertEqual((f["severity"], f["type"]), ("warning", "low_margin"))
        self.assertEqual(f["summary"], "It holds, but only 1.4× the load: under the 2× margin")

    def test_margin_is_the_studys(self):
        self.assertEqual(findings(solved(peak_MPa=197.0, peak_gauss_MPa=200.0, margin=1.25)), [])

    def test_yields_is_qualified_when_the_peak_is_at_the_fixture(self):
        (f, g) = findings(solved(peak_MPa=310.0, peak_gauss_MPa=320.0, peak_face="#o1.f3"))
        self.assertEqual((f["type"], g["type"]), ("yields", "peak_at_fixture"))
        self.assertEqual(f["summary"], "The bracket yields: peak stress 310 MPa is above 6061-T6's 276 MPa yield strength (the peak sits at the fixed face, see below)")

    def test_peak_on_a_fixed_face(self):
        (low, f) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3"))
        self.assertEqual((low["type"], f["type"]), ("low_margin", "peak_at_fixture"))
        self.assertTrue(low["summary"].endswith("(the peak sits at the fixed face, see below)"))
        self.assertEqual(f["summary"], "The peak sits where the part is held, where the model can exaggerate it: check the stress a little away from the fixed face before redesigning")

    def test_peak_findings_wait_until_the_margin_is_missed(self):
        self.assertEqual(findings(solved(peak_face="#o1.f3", peak_gauss_MPa=200.0)), [])

    def test_gauss_spike(self):
        (low, f) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=230.0))  # > 1.5 x 150
        self.assertEqual((low["type"], f["type"]), ("low_margin", "peak_concentration"))
        self.assertTrue(low["summary"].endswith("(the peak is a local spike, see below)"))
        self.assertEqual(f["summary"], "The peak is a sharp local spike the mesh can't resolve (a sharp corner or a concentrated load): a fillet or a finer mesh there would show the real value")

    def test_exactly_the_gauss_ratio_is_not_a_spike(self):
        (low,) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=225.0))
        self.assertEqual(low["type"], "low_margin")

    def test_fixture_wins_over_spike(self):
        types = [f["type"] for f in findings(solved(peak_MPa=150.0, peak_gauss_MPa=300.0, peak_face="#o1.f3"))]
        self.assertEqual(types, ["low_margin", "peak_at_fixture"])

    def test_not_converged_rising(self):
        (f,) = findings(solved(peak_MPa=56.0, coarser_peak_MPa=47.3))
        self.assertEqual(f["type"], "mesh_not_converged")
        self.assertEqual(f["summary"], "The peak kept rising on a finer mesh (47.3 to 56 MPa), which usually means a sharp corner or the fixed edge: fillet it or judge the stress a little away from it")
        self.assertEqual(findings(solved(peak_MPa=50.0, coarser_peak_MPa=47.3)), [])  # 5.7% < 10%

    def test_not_converged_falling(self):
        (f,) = findings(solved(peak_MPa=39.0, coarser_peak_MPa=47.3))
        self.assertEqual(f["summary"], "The peak changed 18% on a finer mesh (47.3 to 39 MPa): use a smaller mesh size (mesh.size_mm) before trusting the safety factor")

    def test_the_safety_factor_uses_the_higher_peak(self):
        (f, _) = findings(solved(coarser_peak_MPa=300.0))
        self.assertEqual(f["type"], "yields")
        self.assertIn("peak stress 300 MPa", f["summary"])

    def test_large_displacement(self):
        (f,) = findings(solved(max_displacement_mm=1.6))  # 1.8% of 90
        self.assertEqual(f["type"], "large_displacement")
        self.assertEqual(f["summary"], "It moves 1.6 mm, about 2% of its size: check the fit if it mates with another part")

    def test_no_load_reaches_it(self):
        (f,) = findings(solved(peak_MPa=0.0, peak_gauss_MPa=0.0))
        self.assertEqual((f["severity"], f["type"]), ("warning", "no_load"))
        self.assertEqual(f["summary"], "No load reaches the part: check the loads are on faces connected to the fixed ones")

    def test_a_factor_just_under_the_margin_never_reads_as_the_margin(self):
        (f,) = findings(solved(peak_MPa=276.0 / 1.96, peak_gauss_MPa=100.0))
        self.assertEqual(f["summary"], "It holds, but only 1.9× the load: under the 2× margin")

    def test_a_factor_of_exactly_one_holds(self):
        (f,) = findings(solved(peak_MPa=276.0, peak_gauss_MPa=276.0))
        self.assertEqual((f["severity"], f["type"]), ("warning", "low_margin"))
        self.assertEqual(f["summary"], "It holds, but only 1.0× the load: under the 2× margin")

    def test_yields_prints_more_decimals_when_the_numbers_would_tie(self):
        (f,) = findings(solved(peak_MPa=276.4, peak_gauss_MPa=276.4))
        self.assertEqual(f["summary"], "The bracket yields: peak stress 276.4 MPa is above 6061-T6's 276.0 MPa yield strength")

    def test_finer_only_when_close(self):
        self.assertTrue(needs_finer(2.99))
        self.assertFalse(needs_finer(3.0))
        self.assertFalse(needs_finer(None))

    def test_errors_first(self):
        types = [f["type"] for f in findings(solved(peak_MPa=310.0, peak_gauss_MPa=600.0, max_displacement_mm=2.0))]
        self.assertEqual(types[0], "yields")


if __name__ == "__main__":
    unittest.main()
