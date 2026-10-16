"""``cadgen.kicad.install``: where ``kicad-cli`` is looked for, in what order, and what a
KiCad too old to serve the API is told. No KiCad: the candidates are empty files on a
fake PATH, and the installers' folders are kicad-python's, faked."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen._internal import tool_probe
from cadgen.kicad import install


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-kicad-install-")
        self.addCleanup(self._tempdir.cleanup)
        root = Path(self._tempdir.name)
        self.nightly = self._executable(root / "nightly", "kicad-cli-nightly")
        self.stable = self._executable(root / "stable", "kicad-cli")
        self.empty = root / "empty"
        self.empty.mkdir()

    @staticmethod
    def _executable(folder: Path, name: str) -> Path:
        folder.mkdir()
        path = folder / tool_probe.executable(name)
        path.write_text("", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def _find(self, *folders: Path, **env: str) -> Path:
        variables = {"PATH": os.pathsep.join(str(folder) for folder in folders), **env}
        with mock.patch.dict(os.environ, variables, clear=False):
            if "CADGEN_KICAD_CLI" not in env:
                os.environ.pop("CADGEN_KICAD_CLI", None)
            return install.find_kicad_cli()

    def test_the_environment_variable_wins_over_everything_on_path(self) -> None:
        found = self._find(self.stable.parent, self.nightly.parent, CADGEN_KICAD_CLI=str(self.stable))
        self.assertEqual(found, self.stable)

    def test_the_environment_variable_naming_nothing_is_refused(self) -> None:
        with self.assertRaisesRegex(install.KicadMissingError, "CADGEN_KICAD_CLI names .*not a file"):
            self._find(self.nightly.parent, CADGEN_KICAD_CLI=str(self.empty / "kicad-cli"))

    def test_the_nightly_on_path_beats_a_stable_kicad_cli_before_it(self) -> None:
        self.assertEqual(self._find(self.stable.parent, self.nightly.parent), self.nightly)
        self.assertEqual(self._find(self.stable.parent), self.stable)

    def test_the_installers_folders_come_last_and_a_miss_says_where_it_looked(self) -> None:
        with mock.patch("cadgen.kipy.server.find_kicad_cli", return_value=str(self.stable)):
            self.assertEqual(self._find(self.empty), self.stable)
        with mock.patch("cadgen.kipy.server.find_kicad_cli", side_effect=FileNotFoundError("none")):
            with self.assertRaisesRegex(install.KicadMissingError, "kicad-cli, was not found .*CADGEN_KICAD_CLI") as caught:
                self._find(self.empty)
        self.assertIn(install.install_hint(), str(caught.exception))


class Unwrap(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-kicad-unwrap-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name).resolve()
        self.binary = self.root / "lib" / "kicad-cli"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"\x7fELF not really")

    def _wrapper(self, text: str) -> Path:
        wrapper = self.root / "kicad-cli-nightly"
        wrapper.write_text(text, encoding="utf-8")
        return wrapper

    def test_ubuntus_nightly_wrapper_is_run_as_its_binary_in_its_environment(self) -> None:
        # The shape Ubuntu's package ships: an environment file sourced, the binary run on
        # the arguments, no exec -- so a signal to the wrapper would leave the server running.
        env = self.root / "kicad-nightly.env"
        env.write_text('export LD_LIBRARY_PATH=/usr/lib/kicad-nightly/lib/\nKICAD_PATH="/usr/share/kicad-nightly"\n# noise\n', encoding="utf-8")
        wrapper = self._wrapper(f"#!/bin/sh\n. {env}\n {self.binary} \"$@\"\n")
        self.assertEqual(
            (self.binary, {"LD_LIBRARY_PATH": "/usr/lib/kicad-nightly/lib/", "KICAD_PATH": "/usr/share/kicad-nightly"}),
            install.unwrap(wrapper),
        )

    def test_anything_but_that_shape_is_run_as_it_is(self) -> None:
        self.assertEqual((self.binary, {}), install.unwrap(self.binary), "a binary")
        other = self._wrapper(f"#!/bin/sh\nif [ -z \"$DISPLAY\" ]; then exit 1; fi\nexec {self.binary} \"$@\"\n")
        self.assertEqual((other, {}), install.unwrap(other), "a script with logic of its own")
        gone = self._wrapper(f"#!/bin/sh\n{self.root / 'nowhere' / 'kicad-cli'} \"$@\"\n")
        self.assertEqual((gone, {}), install.unwrap(gone), "a wrapper over a binary that is not there")
        self.assertEqual((self.root / "missing", {}), install.unwrap(self.root / "missing"), "no file at all")


class Version(unittest.TestCase):
    def test_the_nightly_passes_and_a_stable_kicad_is_named_as_too_old(self) -> None:
        cli = Path("/opt/kicad/bin/kicad-cli")
        self.assertEqual(install.check_version(cli, "10.99.0"), "10.99.0")
        self.assertEqual(install.check_version(cli, "11.0.1"), "11.0.1")
        with self.assertRaisesRegex(install.KicadMissingError, r"kicad-cli is KiCad 10\.0\.7; cadgen needs KiCad 10\.99") as caught:
            install.check_version(cli, "10.0.7")
        self.assertIn(install.install_hint(), str(caught.exception))
        with self.assertRaisesRegex(install.KicadMissingError, "did not answer"):
            install.check_version(cli, None)


if __name__ == "__main__":
    unittest.main()
