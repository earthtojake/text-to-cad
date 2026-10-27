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

    def test_the_stable_cli_is_preferred_and_nightly_is_a_fallback(self) -> None:
        self.assertEqual(self._find(self.stable.parent, self.nightly.parent), self.stable)
        self.assertEqual(self._find(self.stable.parent), self.stable)

    def test_a_miss_says_how_to_install_the_cli(self) -> None:
        with mock.patch("cadgen.kicad.install.sys.platform", "linux"):
            with self.assertRaisesRegex(install.KicadMissingError, "not found.*CADGEN_KICAD_CLI"):
                self._find(self.empty)


class Version(unittest.TestCase):
    def test_supported_file_commands_accept_stable_and_development_versions(self) -> None:
        cli = Path("/opt/kicad/bin/kicad-cli")
        for version in ("9.0.0", "10.0.7", "10.99.0"):
            self.assertEqual(install.check_version(cli, version), version)
        for version in ("8.0.0", None):
            with self.assertRaisesRegex(install.KicadMissingError, "needs KiCad 9 or newer"):
                install.check_version(cli, version)
