"""``cad_server.kicad``: the server runs KiCad's command line alone, never KiCad.

Where ``kicad-cli`` is looked for and what is refused: only a file named exactly ``kicad-cli``
(``kicad-cli.exe``) is ever returned -- never ``kicad``, a ``kicad-cli-nightly`` wrapper or a
launcher. Every run is headless (no ``DISPLAY``, no ``WAYLAND_DISPLAY``) with KiCad's settings in a
private folder. No KiCad: the candidates are small scripts on a fake PATH.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad_server.kicad import cli, install

EXE = ".exe" if sys.platform.startswith("win") else ""


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-kicad-install-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.stable = self._executable(self.root / "stable", "kicad-cli")
        self.nightly = self._executable(self.root / "nightly", "kicad-cli-nightly")
        self.app = self._executable(self.root / "app", "kicad")
        self.empty = self.root / "empty"
        self.empty.mkdir()

    @staticmethod
    def _executable(folder: Path, name: str) -> Path:
        folder.mkdir()
        path = folder / f"{name}{EXE}"
        path.write_text("", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def _find(self, *folders: Path, **env: str) -> Path:
        variables = {"PATH": os.pathsep.join(str(folder) for folder in folders), **env}
        with mock.patch.dict(os.environ, variables, clear=False), \
                mock.patch.object(install, "_installed", lambda: []):
            if "CAD_KICAD_CLI" not in env:
                os.environ.pop("CAD_KICAD_CLI", None)
            return install.find_kicad_cli()

    def test_the_environment_variable_wins_over_everything_on_path(self) -> None:
        other = self._executable(self.root / "other", "kicad-cli")
        self.assertEqual(self._find(self.stable.parent, CAD_KICAD_CLI=str(other)), other)

    def test_the_environment_variable_naming_anything_but_kicad_cli_is_refused(self) -> None:
        for named in (self.app, self.nightly, self.root / "open"):
            with self.subTest(named=named.name), \
                    self.assertRaisesRegex(install.KicadMissingError, "CAD_KICAD_CLI names .*which is not kicad-cli"):
                self._find(self.stable.parent, CAD_KICAD_CLI=str(named))
        with self.assertRaisesRegex(install.KicadMissingError, "CAD_KICAD_CLI names .*not a file"):
            self._find(self.stable.parent, CAD_KICAD_CLI=str(self.empty / f"kicad-cli{EXE}"))

    def test_only_kicad_cli_on_path_is_found_never_a_wrapper_or_the_app(self) -> None:
        self.assertEqual(self._find(self.nightly.parent, self.app.parent, self.stable.parent), self.stable)
        with mock.patch.object(install.sys, "platform", "linux"):
            with self.assertRaisesRegex(install.KicadMissingError, "not found.*CAD_KICAD_CLI"):
                self._find(self.nightly.parent, self.app.parent)

    def test_the_installation_folders_name_the_command_line_itself(self) -> None:
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform), mock.patch.object(install.sys, "platform", platform), \
                    mock.patch.dict(os.environ, {"ProgramFiles": str(self.root)}):
                (self.root / "KiCad" / "9.0").mkdir(parents=True, exist_ok=True)
                for candidate in install._installed():
                    self.assertIn(candidate.name, install.CLI_NAMES)


class Headless(unittest.TestCase):
    def test_a_run_has_no_display_and_settings_of_its_own(self) -> None:
        with mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
                                          "KICAD_CONFIG_HOME": "/home/someone/.config/kicad"}):
            env = install.headless_env("/tmp/private")
        self.assertNotIn("DISPLAY", env)
        self.assertNotIn("WAYLAND_DISPLAY", env)
        self.assertEqual(env["KICAD_CONFIG_HOME"], "/tmp/private")

    def test_drc_runs_kicad_cli_headless_in_a_private_settings_folder(self) -> None:
        seen = {}

        def run(command, *, env, **_options):
            seen.update(command=command, env=env)
            Path(command[command.index("-o") + 1]).write_text(json.dumps({"violations": []}), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}), \
                mock.patch.object(cli.subprocess, "run", run):
            self.assertEqual(cli.run_drc(Path("/opt/kicad/bin/kicad-cli"), Path("/boards/a.kicad_pcb")), [])
        self.assertEqual(seen["command"][:3], ["/opt/kicad/bin/kicad-cli", "pcb", "drc"])
        self.assertNotIn("DISPLAY", seen["env"])
        self.assertNotIn("WAYLAND_DISPLAY", seen["env"])
        settings = Path(seen["env"]["KICAD_CONFIG_HOME"])
        self.assertTrue(settings.name == "settings" and settings.parent.name.startswith("cad-drc-"), settings)
        self.assertFalse(settings.exists(), "the private settings folder is removed after the run")


class Version(unittest.TestCase):
    def test_supported_file_commands_accept_stable_and_development_versions(self) -> None:
        cli_path = Path("/opt/kicad/bin/kicad-cli")
        for version in ("9.0.0", "10.0.7", "10.99.0"):
            self.assertEqual(install.check_version(cli_path, version), version)
        for version in ("8.0.0", None):
            with self.assertRaisesRegex(install.KicadMissingError, "needs KiCad 9 or newer"):
                install.check_version(cli_path, version)


if __name__ == "__main__":
    unittest.main()
