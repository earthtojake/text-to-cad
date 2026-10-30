"""CalculiX, the program a study is solved by: found as the person installed it or refused in a sentence, its input's
elements in C3D10's order, its printed output read, its errors said. The solve itself is tested end to end by the
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

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea import calculix  # noqa: E402


def _program(folder: Path, said: str) -> str:
    """A program that prints ``said`` and exits 0."""
    path = folder / "ccx"
    path.write_text(f"#!/bin/sh\necho '{said}'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class FindCcx(unittest.TestCase):
    def test_a_setting_naming_no_program_says_so_and_how_to_install(self):
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: "/no/such/ccx"}):
            with self.assertRaisesRegex(calculix.CalculixMissingError, r"CADGEN_CCX names /no/such/ccx, which is not a program"):
                calculix.find_ccx()

    def test_none_on_path_or_in_freecad_is_refused_with_the_install_hint(self):
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: ""}), mock.patch("cadgen.engine.executables.find", return_value=None), \
                mock.patch.object(calculix, "_in_freecad", return_value=["/no/FreeCAD.app/Contents/Resources/bin/ccx"]):
            with self.assertRaises(calculix.CalculixMissingError) as caught:
                calculix.find_ccx()
        self.assertIn("CalculiX's ccx was not found", str(caught.exception))
        self.assertIn("conda install -c conda-forge calculix", str(caught.exception))
        self.assertIn("FreeCAD 1.0 or newer, which carries one", str(caught.exception))

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_with_none_on_path_the_ccx_a_freecad_install_carries_is_found(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "This is Version 2.23")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: ""}), mock.patch("cadgen.engine.executables.find", return_value=None), \
                    mock.patch.object(calculix, "_in_freecad", return_value=["/no/such/ccx", program]):
                found = calculix.find_ccx()
        self.assertEqual((found.path, found.version), (program, "2.23"))

    def test_freecad_installs_are_looked_for_where_each_installer_puts_them(self):
        with mock.patch.object(calculix.sys, "platform", "darwin"):
            self.assertIn(str(Path("/Applications/FreeCAD.app/Contents/Resources/bin/ccx")), calculix._in_freecad())
        with mock.patch.object(calculix.sys, "platform", "linux"):
            self.assertEqual(calculix._in_freecad(), [])
        # Windows: the installer's "FreeCAD 1.1" folders, newest by number (1.10 after 1.9, which spelling sorts
        # the other way round), and nothing else that starts with the name.
        with tempfile.TemporaryDirectory() as name:
            for folder in ("FreeCAD 1.9", "FreeCAD 1.10", "FreeCAD 1.1 dev", "FreeCAD-backup"):
                (Path(name) / folder).mkdir()
            with mock.patch.object(calculix.sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"ProgramFiles": name, "LOCALAPPDATA": ""}):
                self.assertEqual(calculix._in_freecad(), [str(Path(name) / "FreeCAD 1.10" / "bin" / "ccx.exe"),
                                                          str(Path(name) / "FreeCAD 1.9" / "bin" / "ccx.exe")])

    def test_a_setting_is_an_absolute_path_or_a_name_on_path(self):
        # A relative path would be read in whatever folder the solve runs in.
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: "bin/ccx"}):
            with self.assertRaisesRegex(calculix.CalculixMissingError, r"CADGEN_CCX names bin/ccx, which is not a "
                                                                       r"program \(give its absolute path"):
                calculix.find_ccx()
        with mock.patch.dict(os.environ, {calculix.CCX_ENV: "ccx"}), \
                mock.patch("cadgen.engine.executables.find", return_value=None) as find:
            with self.assertRaises(calculix.CalculixMissingError):
                calculix.find_ccx()
        find.assert_called_once_with("ccx")

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_version_older_than_the_minimum_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "This is Version 2.17")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                with self.assertRaisesRegex(calculix.CalculixMissingError, r"is CalculiX 2\.17; cadgen needs 2\.20 or newer"):
                    calculix.find_ccx()

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_program_that_reports_no_version_is_no_calculix(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "hello")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                with self.assertRaisesRegex(calculix.CalculixMissingError, "reports no CalculiX version"):
                    calculix.find_ccx()

    @unittest.skipIf(sys.platform == "win32", "a shell script stands in for ccx")
    def test_a_supported_version_is_found_and_labels_the_result(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "This is Version 2.23")
            with mock.patch.dict(os.environ, {calculix.CCX_ENV: program}):
                found = calculix.find_ccx()
        self.assertEqual((found.path, found.version, found.label), (program, "2.23", "calculix 2.23 (C3D10)"))


class Elements(unittest.TestCase):
    def test_every_element_has_a_positive_volume_and_each_mid_node_on_its_own_edge(self):
        import numpy as np

        corners = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
        mids = [(corners[i] + corners[j]) / 2 for i, j in calculix.NETGEN_EDGES]
        nodes = np.vstack([corners, mids])
        # The same tetrahedron both ways round: netgen's orientation, and the other.
        tets = np.array([list(range(10)), [0, 2, 1, 3, 5, 4, 6, 7, 9, 8]])
        elements = calculix.c3d10_elements(nodes, tets)
        for row in elements:
            a, b, c, d = nodes[row[:4]]
            self.assertGreater(np.dot(np.cross(b - a, c - a), d - a), 0.0)
            for slot, (i, j) in enumerate(calculix.C3D10_EDGES, start=4):
                np.testing.assert_allclose(nodes[row[slot]], (nodes[row[i]] + nodes[row[j]]) / 2)

    def test_linear_elements_are_refused(self):
        import numpy as np

        with self.assertRaisesRegex(ValueError, "C3D10 needs quadratic"):
            calculix.c3d10_elements(np.zeros((4, 3)), np.array([[0, 1, 2, 3]]))


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
        printed = calculix.read_dat(text)
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


if __name__ == "__main__":
    unittest.main()
