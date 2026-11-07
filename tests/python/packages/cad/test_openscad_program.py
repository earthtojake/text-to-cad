"""``cad.openscad``: OpenSCAD found, checked and run headless, and what a render reads of a program.

Where ``openscad`` is looked for and what is refused: ``CAD_OPENSCAD`` first, refused unless it names a file
called ``openscad`` (``openscad.exe``, the macOS bundle's ``OpenSCAD``) -- never a wrapper or a launcher --
then ``PATH``, then where its installer puts it. Its version is read as OpenSCAD writes it (``2021.01``, a
snapshot's ``2025.03.07``) and checked against the oldest our code supports. Every run is headless: no
``DISPLAY``, OpenSCAD's homes in a private folder, and the person's OpenSCAD libraries kept reachable
(``OPENSCADPATH``, their real home's library folder), since an include of one is an input of the program.
A render writes the STL atomically and fails in OpenSCAD's words, leaving an earlier file as it was; the
dependency file OpenSCAD writes names the files the key reads. No OpenSCAD: the candidates are small
scripts, and the stand-in (``tests/python/support/openscad_stub``) renders where a run is needed.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import openscad_stub

from cad._internal import programs
from cad.openscad import _program as install
from cad.openscad import _render

EXE = ".exe" if sys.platform.startswith("win") else ""


def _executable(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}{EXE}"
    path.write_text("", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-openscad-find-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.on_path = _executable(self.root / "bin", "openscad")
        self.nightly = _executable(self.root / "nightly", "openscad-nightly")
        self.empty = self.root / "empty"
        self.empty.mkdir()

    def _find(self, *folders: Path, installed=(), **env: str) -> Path:
        variables = {"PATH": os.pathsep.join(str(folder) for folder in folders), **env}
        with mock.patch.dict(os.environ, variables, clear=False), \
                mock.patch.object(install, "installed", lambda: list(installed)):
            if "CAD_OPENSCAD" not in env:
                os.environ.pop("CAD_OPENSCAD", None)
            return install.find()

    def test_the_environment_variable_wins_and_names_openscad_itself(self) -> None:
        other = _executable(self.root / "other", "openscad")
        self.assertEqual(self._find(self.on_path.parent, CAD_OPENSCAD=str(other)), other)
        for named in (self.nightly, self.root / "open"):
            with self.subTest(named=named.name), \
                    self.assertRaisesRegex(install.OpenscadMissing, "CAD_OPENSCAD names .*which is not openscad"):
                self._find(self.on_path.parent, CAD_OPENSCAD=str(named))
        with self.assertRaisesRegex(install.OpenscadMissing, "CAD_OPENSCAD names .*not a file"):
            self._find(self.on_path.parent, CAD_OPENSCAD=str(self.empty / f"openscad{EXE}"))

    def test_path_then_the_installers_places_never_a_wrapper(self) -> None:
        self.assertEqual(self._find(self.on_path.parent), self.on_path)
        placed = _executable(self.root / "Applications", "OpenSCAD" if sys.platform == "darwin" else "openscad")
        self.assertEqual(self._find(self.nightly.parent, installed=[placed]), placed)
        with self.assertRaisesRegex(install.OpenscadMissing, r"openscad was not found: install OpenSCAD 2021\.01 or "
                                                             r"newer .*CAD_OPENSCAD"):
            self._find(self.nightly.parent, self.empty)

    def test_the_installers_places_are_each_platforms(self) -> None:
        with mock.patch.object(install.sys, "platform", "darwin"):
            self.assertTrue(all(path.name == "OpenSCAD" and "OpenSCAD.app" in path.parts for path in install.installed()))
        with mock.patch.object(install.sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"ProgramFiles": r"C:\PF", "ProgramFiles(x86)": r"C:\PF86"}):
            self.assertEqual([str(path) for path in install.installed()],
                             [str(Path(r"C:\PF") / "OpenSCAD" / "openscad.exe"), str(Path(r"C:\PF86") / "OpenSCAD" / "openscad.exe")])
        with mock.patch.object(install.sys, "platform", "linux"):
            self.assertEqual([str(path) for path in install.installed()], ["/usr/bin/openscad", "/usr/local/bin/openscad"])


class Version(unittest.TestCase):
    def test_a_release_and_a_snapshot_are_read_and_checked(self) -> None:
        self.assertEqual(programs.version_tuple("2021.01"), (2021, 1))
        self.assertEqual(install.OPENSCAD.minimum, (2021, 1))
        for said, expected in (("OpenSCAD version 2021.01", "2021.01"),
                               ("OpenSCAD version 2025.03.07 (git 1a2b3c)", "2025.03.07"),
                               ("WARNING: no display\nOpenSCAD version 2024.12.29\n", "2024.12.29")):
            self.assertEqual(install._VERSION.search(said).group(1), expected)
        self.assertEqual(install.check_version(Path("x"), "2025.03.07"), "2025.03.07")
        self.assertEqual(install.check_version(Path("x"), "2021.01"), "2021.01")
        with self.assertRaisesRegex(install.OpenscadMissing, r"x reports 2019\.05; cad needs OpenSCAD 2021\.01 or newer"):
            install.check_version(Path("x"), "2019.05")
        with self.assertRaisesRegex(install.OpenscadMissing, "reports no version"):
            install.check_version(Path("x"), None)

    @unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
    def test_the_stub_answers_its_version_once_per_program(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-openscad-stub-") as folder:
            stub = openscad_stub.write_stub(folder)
            self.assertEqual(install.version(stub), "2021.01")
            self.assertFalse(install.has_backend(stub), "2021.01 takes no --backend")
            with mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(stub)}):
                self.assertEqual(install.ready(), (stub, "2021.01"))
                with mock.patch.object(install, "version", side_effect=AssertionError("asked again")):
                    self.assertEqual(install.ready(), (stub, "2021.01"))


class Headless(unittest.TestCase):
    HOMES = {"linux": ("HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"),
             "darwin": ("HOME", "TMPDIR"),
             "win32": ("HOME", "TMPDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP")}

    def test_a_run_has_no_display_private_homes_and_the_persons_libraries(self) -> None:
        for platform, names in self.HOMES.items():
            with self.subTest(platform=platform), tempfile.TemporaryDirectory(prefix="tmp-openscad-env-") as folder:
                root = Path(folder)
                home = root / "someone"
                library = (home / "Documents" / "OpenSCAD" / "libraries" if platform != "linux"
                           else home / ".local" / "share" / "OpenSCAD" / "libraries")
                library.mkdir(parents=True)
                own = root / "own-libs"
                own.mkdir()
                person = {"HOME": str(home), "USERPROFILE": str(home), "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
                          "OPENSCADPATH": str(own)}
                with mock.patch.object(install.sys, "platform", platform), \
                        mock.patch.object(programs.sys, "platform", platform), \
                        mock.patch.dict(os.environ, person), \
                        mock.patch.object(os.path, "expanduser", lambda path, h=str(home): path.replace("~", h, 1)):
                    os.environ.pop("XDG_DATA_HOME", None)
                    env = install.headless_env(root / "run")
                self.assertNotIn("DISPLAY", env)
                self.assertNotIn("WAYLAND_DISPLAY", env)
                for name in names:
                    self.assertTrue(Path(env[name]).is_relative_to(root / "run"), f"{name}={env[name]} is outside the run")
                # The caller's entries first, then the real home's user library folder, which the private HOME hides.
                self.assertEqual(env["OPENSCADPATH"], os.pathsep.join([str(own), str(library)]))

    def test_a_person_with_no_library_folder_gets_no_openscadpath_of_ours(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-openscad-env-") as folder:
            root = Path(folder)
            with mock.patch.dict(os.environ, {"HOME": str(root / "nobody"), "USERPROFILE": str(root / "nobody")}), \
                    mock.patch.object(os.path, "expanduser", lambda path, h=str(root / "nobody"): path.replace("~", h, 1)):
                os.environ.pop("OPENSCADPATH", None)
                os.environ.pop("XDG_DATA_HOME", None)
                self.assertEqual(install.libraries(), [])
                self.assertNotIn("OPENSCADPATH", install.headless_env(root / "run"))

    def test_the_noise_is_dropped_and_the_words_kept(self) -> None:
        said = "Fontconfig error: no fonts\nqt.qpa.xcb: could not connect\nECHO: version = [2021, 1, 0]\n\n" \
               "Current top level object is not a 3D object."
        self.assertEqual(install.quiet(said), "ECHO: version = [2021, 1, 0]\nCurrent top level object is not a 3D object.")


class Dependencies(unittest.TestCase):
    def test_the_dependency_file_names_the_files_read_spaces_escaped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-openscad-deps-") as folder:
            root = Path(folder).resolve()
            (root / "lib dir").mkdir()
            program, helper, lib = root / "part.scad", root / "helper.scad", root / "lib dir" / "lib.scad"
            for path in (program, helper, lib):
                path.write_text("// scad\n", encoding="utf-8")
            text = (f"out.stl: \\\n\t{helper} \\\n\t{str(lib).replace(' ', chr(92) + ' ')} \\\n\tpart.scad\n")
            self.assertEqual(_render.dependencies(text, source=program, folder=root), (helper, lib), "sorted, each once")
            # A file that is gone names nothing, and a relative path is the program's folder's.
            self.assertEqual(_render.dependencies("x.stl: gone.scad helper.scad\n", source=program, folder=root), (helper,))

    def test_the_key_reads_the_program_its_includes_and_the_version(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-openscad-key-") as folder:
            root = Path(folder)
            program, lib = root / "part.scad", root / "lib.scad"
            program.write_text("include <lib.scad>\ncube(1);\n", encoding="utf-8")
            lib.write_text("a = 1;\n", encoding="utf-8")
            first = _render.key(program, [lib], "2021.01")
            self.assertEqual(first, _render.key(program, [lib], "2021.01"))
            self.assertNotEqual(first, _render.key(program, [], "2021.01"), "the includes are in it")
            self.assertNotEqual(first, _render.key(program, [lib], "2025.03.07"), "OpenSCAD's version is in it")
            lib.write_text("a = 2;\n", encoding="utf-8")
            self.assertNotEqual(first, _render.key(program, [lib], "2021.01"), "a library's edit is a new key")


@unittest.skipUnless(openscad_stub.RUNS, "the stand-in OpenSCAD is a shebang script, which Windows does not run")
class Render(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-openscad-render-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name).resolve()
        self.stub = openscad_stub.write_stub(self.root / "bin")
        patched = mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(self.stub)})
        patched.start()
        self.addCleanup(patched.stop)
        (self.root / "lib dir").mkdir()
        (self.root / "lib dir" / "lib.scad").write_text("module post() {}\n", encoding="utf-8")
        self.program = self.root / "part.scad"
        self.program.write_text('include <lib dir/lib.scad>\necho("hello");\ncube([20, 10, 5]);\n', encoding="utf-8")

    def test_a_render_writes_the_stl_and_names_what_it_read(self) -> None:
        out = self.root / "out" / "part.stl"
        found = _render.render(self.program, out)
        self.assertEqual((found.source, found.mesh, found.version), (self.program, out, "2021.01"))
        self.assertEqual(found.includes, (self.root / "lib dir" / "lib.scad",))
        self.assertIn("ECHO: \"hello\"", found.said)
        data = out.read_bytes()
        self.assertEqual((data[:14], int.from_bytes(data[80:84], "little"), len(data)), (b"OpenSCAD Model", 12, 84 + 12 * 50))
        self.assertEqual(sorted(path.name for path in out.parent.iterdir()), ["part.stl"], "no temp file left")

    def test_a_failure_is_openscads_words_and_leaves_the_file_as_it_was(self) -> None:
        out = self.root / "part.stl"
        out.write_bytes(b"earlier")
        self.program.write_text("syntax error here\n", encoding="utf-8")
        with self.assertRaisesRegex(_render.RenderError, r"OpenSCAD could not render part\.scad \(exit 1\): ERROR: Parser error"):
            _render.render(self.program, out)
        self.assertEqual(out.read_bytes(), b"earlier")
        self.program.write_text("square(10);\n", encoding="utf-8")
        with self.assertRaisesRegex(_render.TwoDimensional, r"part\.scad is a 2D program: OpenSCAD renders its object to a DXF"):
            _render.render(self.program, out)
        with self.assertRaisesRegex(FileNotFoundError, "no such file"):
            _render.render(self.root / "gone.scad", out)
        with mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(self.root / "nowhere" / "openscad")}), \
                self.assertRaisesRegex(install.OpenscadMissing, "CAD_OPENSCAD names .*not a file: install OpenSCAD"):
            _render.render(self.program, out)
        with mock.patch.dict(os.environ, {"CAD_OPENSCAD": str(self.root / "nothing")}), \
                self.assertRaisesRegex(install.OpenscadMissing, "which is not openscad: name the program itself"):
            _render.render(self.program, out)


if __name__ == "__main__":
    unittest.main()
