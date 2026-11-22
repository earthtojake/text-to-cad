"""A CNC report's walls and gaps refined as it lists them, with the parts' kept results (``cad._internal.dfm.parts``):
its first 200 of each refined on their parts' models, each once ever -- kept with its part's result, made on demand
on a model of a part found kept -- so a check refines no more than one with no store does, and its report is the
one every part measured afresh makes. Every part is built here, and the store is a folder of the test's own."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from tests.python.packages.cad.test_dfm_parts import _Checked, _document, _labelled


class RefinedTest(_Checked):
    process = "cnc"

    def setUp(self) -> None:
        from cad import quiddity
        from cad.quiddity._features import unavailable

        super().setUp()
        patched = mock.patch.object(quiddity, "features_of", lambda parts, **_given: [
            unavailable("no_wheel", "why, in a line") for _part in parts])
        patched.start()
        self.addCleanup(patched.stop)

    def test_the_report_s_walls_and_gaps_are_refined_once_each_and_never_more_than_it_lists(self) -> None:
        """A report refines its first 200 walls and gaps on their parts' models, each once ever: a cold check
        refines what a check with no store does, a warm one nothing, and a part found kept is refined where a
        document lists more of its walls than one before did."""
        import build123d as bd

        from cad.build123d import _dfm_cnc

        def grid(pitch: float, label: str, at: float, n: int = 8) -> object:
            """A plate drilled ``n`` by ``n``, its walls the webs between the holes."""
            plate = bd.Box(n * pitch + 8, n * pitch + 8, 10)
            for i in range(n):
                for j in range(n):
                    plate -= bd.Pos((i - (n - 1) / 2) * pitch, (j - (n - 1) / 2) * pitch, 0) * bd.Cylinder(2.5, 10)
            return _labelled(bd.Pos(0, at, 0) * plate, label)

        def refines(document: object, kept: object = None) -> tuple[int, str]:
            with mock.patch.object(_dfm_cnc, "_refine", side_effect=_dfm_cnc._refine) as refine:
                report = self.measure(document, kept)
            return refine.call_count, report

        # a plate of more walls than the report lists, beside one whose walls are all wider than those listed
        document = _document(self.root, [grid(5.9, "thin", 0, 13), grid(7.2, "wide", 200)])
        alone, fresh = refines(document)
        self.assertLessEqual(alone, 400, "the report's first 200 walls and 200 gaps at most")
        self.assertGreater(json.loads(fresh)["walls"]["count"], 200, "more walls than the report lists")
        self.assertEqual(refines(document, self.kept), (alone, fresh), "cold: what a check with no store refines")
        self.assertEqual(refines(document, self.kept), (0, fresh), "warm: none")
        # the wide plate alone, found kept: its own first 200 refined now, on a model made of the part
        lone = _document(self.root, [grid(7.2, "wide", 200)])
        made, report = refines(lone, self.kept)
        self.assertEqual(report, refines(lone)[1])
        self.assertGreater(made, 0)
        self.assertEqual(self.kept.counts["dfm-cnc"]["measured"], 2, "the wide plate found kept, not measured again")
        self.assertEqual(refines(lone, self.kept), (0, report))



if __name__ == "__main__":
    unittest.main()
