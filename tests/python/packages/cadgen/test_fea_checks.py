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
        finer_peak_MPa=None,
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

    def test_peak_on_a_fixed_face(self):
        (f,) = findings(solved(peak_face="#o1.f3"))
        self.assertEqual(f["type"], "peak_at_fixture")
        self.assertIn("likely exaggerated", f["summary"])

    def test_gauss_spike(self):
        (f,) = findings(solved(peak_gauss_MPa=80.0))  # > 1.5 x 47.3
        self.assertEqual(f["type"], "peak_at_fixture")

    def test_not_converged(self):
        (f,) = findings(solved(finer_peak_MPa=56.0))
        self.assertEqual(f["type"], "mesh_not_converged")
        self.assertEqual(f["summary"], "The peak moved 18% on a finer mesh (47.3 to 56 MPa): refine before trusting the safety factor")
        self.assertEqual(findings(solved(finer_peak_MPa=50.0)), [])  # 5.7% < 10%

    def test_large_bend(self):
        (f,) = findings(solved(max_displacement_mm=1.6))  # 1.8% of 90
        self.assertEqual(f["type"], "large_bend")
        self.assertEqual(f["summary"], "It bends 1.6 mm, about 2% of its size: check the fit if it mates with another part")

    def test_no_load_reaches_it(self):
        self.assertEqual(findings(solved(peak_MPa=0.0, peak_gauss_MPa=0.0)), [])

    def test_finer_only_when_close(self):
        self.assertTrue(needs_finer(2.99))
        self.assertFalse(needs_finer(3.0))
        self.assertFalse(needs_finer(None))

    def test_errors_first(self):
        types = [f["type"] for f in findings(solved(peak_MPa=310.0, peak_gauss_MPa=600.0, max_displacement_mm=2.0))]
        self.assertEqual(types[0], "yields")


if __name__ == "__main__":
    unittest.main()
