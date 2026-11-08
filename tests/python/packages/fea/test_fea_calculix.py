"""CalculiX, the program a study is solved by: the cad-ccx package's, or the one CAD_CCX names, or refused in a sentence; its
input's elements in C3D10's order, kept where a study asks; its printed output read, its errors said. The solve itself is tested end to end by the
static tests, on a real ``ccx``; these need none.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.calculix import _files, _program as calculix  # noqa: E402
from cad.netgen._mesher import NETGEN_EDGES  # noqa: E402


def _program(folder: Path, said: str) -> str:
    """A program that prints ``said`` and exits 0."""
    path = folder / "ccx"
    path.write_text(f"#!/bin/sh\necho '{said}'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class FindCcx(unittest.TestCase):
    def test_a_setting_naming_no_file_says_so_and_how_to_install(self):
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: "/no/such/ccx"}):
            with self.assertRaises(calculix.CalculixMissingError) as caught:
                calculix.find_ccx()
        said = str(caught.exception)
        self.assertIn(f"CAD_CCX names {Path('/no/such/ccx')}, which is not a file", said)  # Windows prints its own slashes
        self.assertIn("cad[calculix]", said)

    def test_a_setting_naming_anything_but_ccx_is_refused_and_never_run(self):
        with tempfile.TemporaryDirectory() as name:
            program = Path(name) / "FreeCAD"
            program.write_text("#!/bin/sh\ntouch ran\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: str(program)}):
                with self.assertRaisesRegex(calculix.CalculixMissingError, "which is not ccx"):
                    calculix.find_ccx()

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_the_cad_ccx_package_is_the_one_run_and_never_one_on_path(self):
        with tempfile.TemporaryDirectory() as name:
            packaged = _program(Path(name), "This is Version 2.23")
            on_path = Path(name) / "path"
            on_path.mkdir()
            _program(on_path, "This is Version 2.22")
            ccx = mock.Mock(executable=mock.Mock(return_value=Path(packaged)))
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: "", "PATH": str(on_path)}), \
                    mock.patch.dict(sys.modules, {"cad_ccx": ccx}):
                found = calculix.find_ccx()
        self.assertEqual((found.path, found.version), (packaged, "2.23"))

    def test_without_the_cad_ccx_package_it_is_refused_with_the_extra(self):
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: ""}), mock.patch.dict(sys.modules, {"cad_ccx": None}):
            self.assertFalse(calculix.carried())
            with self.assertRaises(calculix.CalculixMissingError) as caught:
                calculix.find_ccx()
        self.assertIn("ccx was not found", str(caught.exception))
        self.assertIn("cad[calculix]", str(caught.exception))
        self.assertIn("CAD_CCX", str(caught.exception))

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_newer_build_can_be_named_and_a_relative_path_is_kept_absolute(self):
        # Relative, it would be read in the folder a solve runs in.
        with tempfile.TemporaryDirectory() as name:
            program = Path(_program(Path(name), "This is Version 2.24"))
            program = program.rename(program.with_name("ccx_2.24_MT"))
            relative = os.path.relpath(program)
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: relative}):
                self.assertTrue(calculix.carried())
                found = calculix.find_ccx()
        self.assertTrue(os.path.isabs(found.path))
        self.assertEqual(found.version, "2.24")

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_version_older_than_the_minimum_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "This is Version 2.17")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                with self.assertRaisesRegex(calculix.CalculixMissingError, r"reports 2\.17; cad needs CalculiX 2\.20 or newer"):
                    calculix.find_ccx()

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_program_that_reports_no_version_is_no_calculix(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "hello")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                with self.assertRaisesRegex(calculix.CalculixMissingError, "reports no version"):
                    calculix.find_ccx()

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_supported_version_is_found_and_labels_the_result(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "This is Version 2.23")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                found = calculix.find_ccx()
        self.assertEqual((found.path, found.version, found.label), (program, "2.23", "calculix 2.23 (C3D10)"))


@unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
class Deck(unittest.TestCase):
    """``keeping_deck``: the input of each run that succeeds is kept where a study's ``deck`` names it."""

    def _solver(self, folder: Path, fails: bool = False) -> calculix.Ccx:
        path = folder / "ccx"
        body = "echo ' *ERROR in a card'\n" if fails else "echo out > \"$2.dat\"\n"
        path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return calculix.Ccx(path=str(path), version="2.23")

    def test_the_last_run_that_succeeds_is_kept_and_nothing_without_it(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            solver = self._solver(folder)
            deck = folder / "kept" / "study.inp"
            calculix.run(solver, lambda path: path.write_text("*HEADING\nfirst\n", encoding="utf-8"))
            self.assertFalse(deck.exists())
            with calculix.keeping_deck(deck):
                calculix.run(solver, lambda path: path.write_text("*HEADING\nfirst\n", encoding="utf-8"))
                calculix.run(solver, lambda path: path.write_text("*HEADING\nsecond\n", encoding="utf-8"))
                with self.assertRaises(RuntimeError):
                    calculix.run(self._solver(folder / "kept", fails=True), lambda path: path.write_text("*HEADING\nthird\n", encoding="utf-8"))
            self.assertEqual(deck.read_text(encoding="utf-8"), "*HEADING\nsecond\n")
            deck.unlink()
            calculix.run(solver, lambda path: path.write_text("*HEADING\nafter\n", encoding="utf-8"))
            self.assertFalse(deck.exists())


class Elements(unittest.TestCase):
    def test_every_element_has_a_positive_volume_and_each_mid_node_on_its_own_edge(self):
        import numpy as np

        corners = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
        mids = [(corners[i] + corners[j]) / 2 for i, j in NETGEN_EDGES]
        nodes = np.vstack([corners, mids])
        # The same tetrahedron both ways round: netgen's orientation, and the other.
        tets = np.array([list(range(10)), [0, 2, 1, 3, 5, 4, 6, 7, 9, 8]])
        elements = _files.c3d10_elements(nodes, tets)
        for row in elements:
            a, b, c, d = nodes[row[:4]]
            self.assertGreater(np.dot(np.cross(b - a, c - a), d - a), 0.0)
            for slot, (i, j) in enumerate(_files.C3D10_EDGES, start=4):
                np.testing.assert_allclose(nodes[row[slot]], (nodes[row[i]] + nodes[row[j]]) / 2)

    def test_linear_elements_are_refused(self):
        import numpy as np

        with self.assertRaisesRegex(ValueError, "C3D10 needs quadratic"):
            _files.c3d10_elements(np.zeros((4, 3)), np.array([[0, 1, 2, 3]]))


class ReadDat(unittest.TestCase):
    def test_each_block_reads_as_rows_and_a_three_digit_exponent_reads_too(self):
        text = "\n".join([
            "",
            " displacements (vx,vy,vz) for set NALL and time  0.1000000E+01",
            "",
            "         1  1.000000E-03  0.000000E+00 -2.000000E-03",
            "         2  0.000000E+00  1.234567-100  0.000000E+00",
            "",
            " forces (fx,fy,fz) for set NHELD and time  0.1000000E+01",
            "",
            "         1 -1.000000E+01  0.000000E+00  5.000000E+00",
            "",
            " stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set PART0 and time  0.1000000E+01",
            "",
            "         1   1  1.0E+00  2.0E+00  3.0E+00  4.0E+00  5.0E+00  6.0E+00",
            "",
        ])
        printed = _files.read_dat(text)
        self.assertEqual(printed["U"].shape, (2, 4))
        self.assertAlmostEqual(printed["U"][1, 2] * 1e100, 1.234567)
        self.assertEqual(printed["RF"].tolist(), [[1.0, -10.0, 0.0, 5.0]])
        self.assertEqual(printed["S"].tolist(), [[1.0, 1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]])


class Run(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_an_error_calculix_prints_is_said(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "ccx"
            path.write_text("#!/bin/sh\necho ' *ERROR in calinput: the node set NHELD is not defined'\n", encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
            with self.assertRaisesRegex(RuntimeError, "CalculiX failed .*NHELD is not defined"):
                calculix.run(calculix.Ccx(str(path), "2.23"), lambda inp: inp.write_text("*NODE\n", encoding="utf-8"))

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_run_has_no_display_a_home_of_its_own_and_one_thread(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "ccx"
            path.write_text('#!/bin/sh\necho "$HOME|${DISPLAY:-none}|$OMP_NUM_THREADS|$PWD" > study.dat\n', encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {"DISPLAY": ":0", "HOME": name, "OMP_NUM_THREADS": "8"}):
                dat = calculix.run(calculix.Ccx(str(path), "2.23"), lambda inp: inp.write_text("", encoding="utf-8"))
        home, display, threads, folder = dat.strip().split("|")
        self.assertEqual((display, threads), ("none", "1"))
        self.assertEqual(Path(home).resolve(), (Path(folder) / "home").resolve())
        self.assertFalse(Path(folder).exists())


if __name__ == "__main__":
    unittest.main()
