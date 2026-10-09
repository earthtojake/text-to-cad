"""``cadgen._internal.fea.checks``: a solved study as findings in plain words. Pure: no FEA stack."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.checks import (  # noqa: E402
    Solved, assembly_findings, default_material, findings, gap_closed, needs_finer, safety_factor, safety_factor_text,
)


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
    if base["coarser_peak_MPa"] is not None:  # a re-solve is materially finer unless a test says otherwise
        base.setdefault("dofs", 200_000)
        base.setdefault("coarser_dofs", 100_000)
    return Solved(**base)


class ChecksTest(unittest.TestCase):
    def test_a_safe_part_has_nothing_to_say(self):
        self.assertEqual(findings(solved()), [])

    def test_yields(self):
        (f,) = findings(solved(peak_MPa=310.0, peak_gauss_MPa=320.0))
        self.assertEqual((f["severity"], f["type"]), ("error", "yields"))
        self.assertEqual(f["summary"], "The bracket yields: peak stress 310 MPa is above the 276 MPa yield strength of 6061-T6")
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
        self.assertEqual(f["summary"], "The bracket yields: peak stress 310 MPa is above the 276 MPa yield strength of 6061-T6 (the peak sits at the fixed face)")

    def test_peak_on_a_fixed_face(self):
        (low, f) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3"))
        self.assertEqual((low["type"], f["type"]), ("low_margin", "peak_at_fixture"))
        self.assertTrue(low["summary"].endswith("(the peak sits at the fixed face)"))
        self.assertEqual(f["summary"], "Check the stress a little away from the fixed face before redesigning: the model exaggerates peaks where a part is held")

    def test_peak_findings_wait_until_the_margin_is_missed(self):
        self.assertEqual(findings(solved(peak_face="#o1.f3", peak_gauss_MPa=200.0)), [])

    def test_gauss_spike(self):
        (low, f) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=230.0))  # > 1.5 x 150
        self.assertEqual((low["type"], f["type"]), ("low_margin", "peak_concentration"))
        self.assertTrue(low["summary"].endswith("(the peak is a local spike)"))
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

    def test_the_safety_factor_uses_the_written_peak_and_the_coarser_peak_only_checks_convergence(self):
        (f,) = findings(solved(coarser_peak_MPa=300.0))  # written peak 47.3: SF 5.8
        self.assertEqual(f["type"], "mesh_not_converged")
        self.assertEqual(safety_factor(solved(coarser_peak_MPa=300.0)), 276.0 / 47.3)
        (f, _) = findings(solved(peak_MPa=300.0, coarser_peak_MPa=40.0))
        self.assertEqual(f["type"], "yields")
        self.assertIn("peak stress 300 MPa", f["summary"])

    def test_a_resolved_peak_at_the_fixture_raises_no_peak_finding(self):
        # The mounting plate: 209 MPa then 208 on the finer mesh, peak on a clamped hole's rim.
        (low,) = findings(solved(yield_MPa=276.0, peak_MPa=208.0, peak_gauss_MPa=300.0, peak_face="#o1.f3", coarser_peak_MPa=209.0))
        self.assertEqual(low["type"], "low_margin")
        self.assertNotIn("peak sits", low["summary"])
        (low,) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=300.0, coarser_peak_MPa=149.0))
        self.assertEqual(low["type"], "low_margin")
        self.assertNotIn("local spike", low["summary"])

    def test_a_resolve_barely_bigger_than_the_first_does_not_resolve_the_peak(self):
        # The plate: 603k then 621k DOF (+3%), 209 then 208 MPa: weak evidence.
        types = [f["type"] for f in findings(solved(
            peak_MPa=208.0, peak_gauss_MPa=216.0, peak_face="#o1.f3", coarser_peak_MPa=209.0,
            dofs=620922, coarser_dofs=603483,
        ))]
        self.assertEqual(types, ["low_margin", "peak_at_fixture"])
        (low,) = findings(solved(
            peak_MPa=208.0, peak_gauss_MPa=216.0, peak_face="#o1.f3", coarser_peak_MPa=209.0,
            dofs=130_000, coarser_dofs=100_000,  # exactly 1.3x counts as finer
        ))
        self.assertEqual(low["type"], "low_margin")

    def test_a_rising_peak_at_a_smooth_spot_gets_no_likely_lower_clause(self):
        (low, moved) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f12", coarser_peak_MPa=100.0))
        self.assertEqual((low["type"], moved["type"]), ("low_margin", "mesh_not_converged"))
        self.assertEqual(low["summary"], "It holds, but only 1.8× the load: under the 2× margin")

    def test_a_rising_spike_gets_the_clause(self):
        (low, *_rest) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=300.0, peak_face="#o1.f12", coarser_peak_MPa=100.0))
        self.assertIn("kept rising on a finer mesh, so the real stress is likely lower", low["summary"])

    def test_an_unresolved_peak_at_the_fixture_still_raises_it(self):
        types = [f["type"] for f in findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3", coarser_peak_MPa=100.0))]
        self.assertEqual(types, ["low_margin", "peak_at_fixture", "mesh_not_converged"])

    def test_a_rising_peak_says_the_real_stress_is_likely_lower(self):
        # The stepped shaft: 175 then 337 MPa, peak at the fixed journal.
        (f, peak, moved) = findings(solved(
            material_name="steel", yield_MPa=250.0, part="shaft", peak_MPa=337.0, peak_gauss_MPa=467.0,
            peak_face="#o1.f3", coarser_peak_MPa=175.0,
        ))
        self.assertEqual((f["type"], peak["type"], moved["type"]), ("yields", "peak_at_fixture", "mesh_not_converged"))
        self.assertEqual(f["severity"], "error")
        self.assertEqual(
            f["summary"],
            "The shaft yields: peak stress 337 MPa is above the 250 MPa yield strength of steel, "
            "but this peak kept rising on a finer mesh, so the real stress is likely lower",
        )
        self.assertNotIn("fixed face)", f["summary"])

    def test_a_rising_low_margin_peak_carries_the_same_clause_once(self):
        (low, *_rest) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3", coarser_peak_MPa=100.0))
        self.assertEqual(low["summary"], "It holds, but only 1.8× the load: under the 2× margin, but this peak kept rising on a finer mesh, so the real stress is likely lower")

    def test_a_falling_peak_keeps_its_old_qualifier(self):
        (low, *_rest) = findings(solved(peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3", coarser_peak_MPa=200.0))
        self.assertTrue(low["summary"].endswith("(the peak sits at the fixed face)"))

    def test_one_rounding_for_every_factor_a_person_reads(self):
        self.assertEqual(safety_factor_text(1.684), "1.6")
        self.assertEqual(safety_factor_text(0.999), "0.9")
        self.assertEqual(safety_factor_text(9.99), "9.9")
        self.assertEqual(safety_factor_text(10.0), "10")
        self.assertEqual(safety_factor_text(12.9), "12")
        (f,) = findings(solved(peak_MPa=276.0 / 1.684, peak_gauss_MPa=100.0))
        self.assertEqual(f["summary"], "It holds, but only 1.6× the load: under the 2× margin")
        self.assertEqual(f["description"], "safety factor 1.6, margin 2")

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
        self.assertEqual(f["summary"], "The bracket yields: peak stress 276.4 MPa is above the 276.0 MPa yield strength of 6061-T6")

    def test_finer_only_when_close(self):
        self.assertTrue(needs_finer(2.99))
        self.assertFalse(needs_finer(3.0))
        self.assertFalse(needs_finer(None))

    def test_errors_first(self):
        types = [f["type"] for f in findings(solved(peak_MPa=310.0, peak_gauss_MPa=600.0, max_displacement_mm=2.0))]
        self.assertEqual(types[0], "yields")


class AssemblyChecksTest(unittest.TestCase):
    def test_default_material_asks_whether_the_default_is_right(self):
        f = default_material("post", "6061-T6")
        self.assertEqual((f["check"], f["severity"], f["type"]), ("fea", "warning", "default_material"))
        self.assertEqual(f["summary"], "'post' uses the default material (6061-T6): is that right?")

    def test_gap_closed_names_the_gap_and_the_parts(self):
        f = gap_closed("post", "base", 0.08)
        self.assertEqual((f["severity"], f["type"]), ("warning", "gap_closed"))
        self.assertEqual(f["summary"], "Closed a 0.08 mm gap between 'post' and 'base' to bond them")

    def test_yields_names_the_part_as_it_always_does(self):
        (f,) = findings(solved(part="post", assembly=True, peak_MPa=310.0, peak_gauss_MPa=320.0))
        self.assertEqual(f["summary"], "The post yields: peak stress 310 MPa is above the 276 MPa yield strength of 6061-T6")
        self.assertEqual(f["items"][0]["text"], "the peak stress in 'post'")

    def test_the_other_sentences_of_an_assembly_name_the_part(self):
        (f,) = findings(solved(part="post", assembly=True, peak_MPa=197.0, peak_gauss_MPa=200.0))
        self.assertEqual(f["summary"], "'post' holds, but only 1.4× the load: under the 2× margin")
        (low, g) = findings(solved(part="post", assembly=True, peak_MPa=150.0, peak_gauss_MPa=160.0, peak_face="#o1.f3"))
        self.assertTrue(g["summary"].startswith("In 'post': check the stress a little away from the fixed face"))
        (h,) = findings(solved(part="post", assembly=True, max_displacement_mm=2.0))
        self.assertTrue(h["summary"].startswith("'post' moves 2 mm, about 2% of its size"))

    def test_a_peak_on_the_edge_of_a_joint_is_said_once_the_margin_is_missed(self):
        (low, f) = findings(solved(part="post", assembly=True, peak_MPa=150.0, peak_gauss_MPa=160.0, joint_with="base"))
        self.assertEqual((low["type"], f["type"]), ("low_margin", "bonded_edge_peak"))
        self.assertEqual(f["severity"], "warning")
        self.assertTrue(f["summary"].startswith("In 'post': the peak sits on the edge of the bonded joint with 'base'"))
        self.assertEqual(findings(solved(part="post", assembly=True, joint_with="base")), [])

    def test_a_peak_that_a_finer_mesh_confirmed_is_not_blamed_on_the_joint(self):
        got = findings(solved(part="post", assembly=True, peak_MPa=150.0, peak_gauss_MPa=160.0, joint_with="base", coarser_peak_MPa=148.0))
        self.assertEqual([f["type"] for f in got], ["low_margin"])

    def test_one_part_without_a_load_is_nothing_to_report(self):
        loaded = solved(part="post", assembly=True)
        unloaded = solved(part="base", assembly=True, peak_MPa=0.0, peak_gauss_MPa=0.0)
        self.assertEqual(assembly_findings([loaded, unloaded]), [])
        (f,) = assembly_findings([unloaded, solved(part="post", assembly=True, peak_MPa=0.0, peak_gauss_MPa=0.0)])
        self.assertEqual(f["type"], "no_load")

    def test_errors_come_first_across_parts(self):
        found = assembly_findings([
            solved(part="base", assembly=True, peak_MPa=197.0, peak_gauss_MPa=200.0),
            solved(part="post", assembly=True, peak_MPa=310.0, peak_gauss_MPa=320.0),
        ])
        self.assertEqual([f["type"] for f in found], ["yields", "low_margin"])


if __name__ == "__main__":
    unittest.main()
