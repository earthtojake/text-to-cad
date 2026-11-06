"""FreeCAD, the program every plan is made by: found as the person installed it or refused in a sentence, and its
failures said. The planning itself is tested end to end by ``test_cam_plan``, on a real FreeCAD; these need none."""

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

from cad.freecad import _program as freecad  # noqa: E402

POSIX_ONLY = unittest.skipIf(sys.platform == "win32", "a shell script stands in for freecadcmd")


def _program(folder: Path, body: str) -> str:
    path = folder / "freecadcmd"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def _nowhere():
    """No FreeCAD on PATH or in an installer's place."""
    return mock.patch.multiple(freecad, _in_installers=lambda: [], executables=mock.Mock(find=lambda name: None))


class FindFreecad(unittest.TestCase):
    def test_a_setting_naming_no_program_says_so_and_how_to_install(self):
        with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: "/no/such/freecadcmd"}), _nowhere():
            with self.assertRaises(freecad.FreecadMissingError) as caught:
                freecad.find_freecad()
        said = str(caught.exception)
        self.assertIn(f"CAD_FREECAD names {Path('/no/such/freecadcmd')}, which is not a file", said)
        self.assertIn("install FreeCAD 1.1 or newer", said)

    def test_a_setting_naming_the_desktop_app_or_a_wrapper_is_refused_and_never_run(self):
        with tempfile.TemporaryDirectory() as name:
            for wrapper in ("FreeCAD", "freecad.cmd", "freecad-launcher"):
                path = Path(name) / wrapper
                path.write_text("", encoding="utf-8")
                with self.subTest(wrapper=wrapper), mock.patch.dict(os.environ, {freecad.FREECAD_ENV: str(path)}):
                    with self.assertRaisesRegex(freecad.FreecadMissingError, "which is not freecadcmd"):
                        freecad.find_freecad()

    def test_none_anywhere_is_refused_with_the_install_hint(self):
        with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: ""}), _nowhere():
            with self.assertRaises(freecad.FreecadMissingError) as caught:
                freecad.find_freecad()
        self.assertIn("freecadcmd was not found", str(caught.exception))
        self.assertIn("FreeCAD 1.1 or newer", str(caught.exception))

    @POSIX_ONLY
    def test_a_version_older_than_the_minimum_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "echo 'FreeCAD 0.21.2 Revision: 33771'")
            with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: program}):
                with self.assertRaisesRegex(freecad.FreecadMissingError, r"reports 0\.21\.2; cad needs FreeCAD 1\.1 or newer"):
                    freecad.find_freecad()

    @POSIX_ONLY
    def test_a_program_that_reports_no_version_is_no_freecad(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "echo hello")
            with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: program}):
                with self.assertRaisesRegex(freecad.FreecadMissingError, "reports no version"):
                    freecad.find_freecad()

    @POSIX_ONLY
    def test_a_supported_version_is_found_and_labels_the_plan(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "echo 'FreeCAD 1.1.4 Revision: 20260928 (Git shallow)'")
            with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: program}):
                found = freecad.find_freecad()
        self.assertEqual((found.path, found.version, found.label), (program, "1.1.4", "freecad 1.1.4"))

    @POSIX_ONLY
    def test_path_is_searched_as_the_engine_searches_it_never_the_working_folder(self):
        # A freecadcmd in the working folder, or in a relative PATH entry, is never the one run.
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            program = _program(folder, "echo 'FreeCAD 1.1.4'")
            cwd = os.getcwd()
            try:
                os.chdir(folder)
                with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: "", "PATH": "."}), \
                        mock.patch.object(freecad, "_in_installers", lambda: []):
                    with self.assertRaisesRegex(freecad.FreecadMissingError, "freecadcmd was not found"):
                        freecad.find_freecad()
                with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: "", "PATH": str(folder)}), \
                        mock.patch.object(freecad, "_in_installers", lambda: []):
                    self.assertEqual(program, freecad.find_freecad().path)
            finally:
                os.chdir(cwd)

    @POSIX_ONLY
    def test_an_installers_place_is_looked_in_after_path(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "echo 'FreeCAD 1.2.0'")
            with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: ""}), _nowhere(), \
                    mock.patch.object(freecad, "_in_installers", lambda: ["/not/here", program]):
                self.assertEqual(program, freecad.find_freecad().path)


class Run(unittest.TestCase):
    @POSIX_ONLY
    def test_a_run_that_writes_no_result_says_what_freecad_printed(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), "echo 'Exception while processing file: boom'; exit 3")
            with self.assertRaisesRegex(RuntimeError, r"FreeCAD failed \(exit 3\): Exception while processing file"):
                freecad.run(freecad.FreeCAD(program, "1.1.4"), {}, lambda path: path.write_text("", encoding="utf-8"))

    @POSIX_ONLY
    def test_an_error_the_job_script_reports_is_said(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), 'echo \'{"error": "KeyError: Face99"}\' > "$CAD_CAM_FOLDER/result.json"')
            with self.assertRaisesRegex(RuntimeError, "FreeCAD failed: KeyError: Face99"):
                freecad.run(freecad.FreeCAD(program, "1.1.4"), {}, lambda path: path.write_text("", encoding="utf-8"))

    @POSIX_ONLY
    def test_freecads_own_settings_stay_in_the_runs_folder(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), 'printf \'{"operations": [], "posts": ["a.nc"], "home": "%s"}\' '
                                           '"$FREECAD_USER_HOME" > "$CAD_CAM_FOLDER/result.json"; '
                                           'echo G0 > "$CAD_CAM_FOLDER/a.nc"')
            report, posted = freecad.run(freecad.FreeCAD(program, "1.1.4"), {"x": 1},
                                         lambda path: path.write_text("", encoding="utf-8"))
        self.assertTrue(report["home"].endswith("/freecad") and "cad-freecad-" in report["home"])
        self.assertEqual({"a.nc": "G0\n"}, posted)

    @POSIX_ONLY
    def test_a_run_reaches_no_display_and_keeps_to_private_homes(self):
        with tempfile.TemporaryDirectory() as name:
            program = _program(Path(name), 'printf \'{"operations": [], "posts": [], "home": "%s", "display": "%s%s"}\' '
                                           '"$HOME" "$DISPLAY" "$WAYLAND_DISPLAY" > "$CAD_CAM_FOLDER/result.json"')
            with mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}):
                report, _posted = freecad.run(freecad.FreeCAD(program, "1.1.4"), {},
                                              lambda path: path.write_text("", encoding="utf-8"))
        self.assertEqual("", report["display"])
        self.assertIn("cad-freecad-", report["home"])


if __name__ == "__main__":
    unittest.main()
