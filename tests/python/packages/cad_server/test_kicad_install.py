"""``cad_server.kicad``: the server runs KiCad's command line alone, never KiCad.

Where ``kicad-cli`` is looked for and what is refused: only a file named exactly ``kicad-cli``
(``kicad-cli.exe``) is ever returned -- never ``kicad``, a ``kicad-cli-nightly`` wrapper or a
launcher. Every run is headless (no ``DISPLAY``, no ``WAYLAND_DISPLAY``) with every KiCad home
(settings, documents, cache, data, temp, ``HOME``) in a private folder that is removed after the run.
No KiCad: the candidates are small scripts on a fake PATH.
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

from cad.kicad import _program as install
from cad_server.kicad import cli

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
    # What each OS reads KiCad's settings, data, cache and temp files from: all must end up in the private folder.
    HOMES = {
        "linux": ("HOME", "TMPDIR", "KICAD_CONFIG_HOME", "KICAD_DOCUMENTS_HOME", "KICAD_CACHE_HOME",
                  "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"),
        "darwin": ("HOME", "TMPDIR", "KICAD_CONFIG_HOME", "KICAD_DOCUMENTS_HOME", "KICAD_CACHE_HOME"),
        "win32": ("HOME", "TMPDIR", "KICAD_CONFIG_HOME", "KICAD_DOCUMENTS_HOME", "KICAD_CACHE_HOME",
                  "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"),
    }

    def test_a_run_has_no_display_and_homes_of_its_own(self) -> None:
        person = {name: str(Path("someone") / name) for names in self.HOMES.values() for name in names}
        person.update(DISPLAY=":0", WAYLAND_DISPLAY="wayland-0", KICAD_STOCK_DATA_HOME="stock")
        for platform, names in self.HOMES.items():
            with self.subTest(platform=platform), tempfile.TemporaryDirectory(prefix="tmp-kicad-env-") as folder, \
                    mock.patch.object(install.sys, "platform", platform), \
                    mock.patch.dict(os.environ, person):
                root = Path(folder)
                env = install.headless_env(root)
                self.assertNotIn("DISPLAY", env)
                self.assertNotIn("WAYLAND_DISPLAY", env)
                for name in names:
                    path = Path(env[name])
                    self.assertTrue(path.is_relative_to(root), f"{name}={path} is outside {root}")
                    self.assertTrue(path.is_dir(), f"{name}={path} was not made")
                self.assertEqual(Path(env["KICAD_CONFIG_HOME"]), root / "settings")
                # A user's KiCad finds its stock data by this; only a packaged kicad-cli needs it set.
                self.assertEqual(env["KICAD_STOCK_DATA_HOME"], "stock")
                # Everything else is this process's own, untouched.
                for name in env.keys() - set(names):
                    self.assertEqual(env[name], os.environ[name], name)

    def test_a_private_run_removes_what_kicad_left_in_its_homes(self) -> None:
        with install.private_run("tmp-kicad-run-") as (scratch, env):
            lock = Path(env["TMPDIR"]) / "org.kicad.kicad"
            lock.write_text("", encoding="utf-8")
            (Path(env["KICAD_CACHE_HOME"]) / "kicad").mkdir()
            self.assertTrue(scratch.name.startswith("tmp-kicad-run-"))
        self.assertFalse(scratch.exists())

    def test_drc_runs_kicad_cli_headless_in_private_homes(self) -> None:
        seen = {}
        fake_cli = Path("/opt/kicad/bin/kicad-cli")

        def run(command, *, env, **_options):
            seen.update(command=command, env=env, scratch=Path(env["HOME"]).parent)
            Path(command[command.index("-o") + 1]).write_text(json.dumps({"violations": []}), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}), \
                mock.patch.object(cli.subprocess, "run", run):
            self.assertEqual(cli.run_drc(fake_cli, Path("/boards/a.kicad_pcb")), [])
        # The command carries str(Path): backslashes on Windows, so compare against the Path, not a literal.
        self.assertEqual(seen["command"][:3], [str(fake_cli), "kicad_pcb", "check"])
        self.assertNotIn("DISPLAY", seen["env"])
        self.assertNotIn("WAYLAND_DISPLAY", seen["env"])
        settings = Path(seen["env"]["KICAD_CONFIG_HOME"])
        self.assertTrue(settings.name == "settings" and settings.parent.name.startswith("cad-drc-"), settings)
        self.assertFalse(settings.exists(), "the private settings folder is removed after the run")
        self.assertEqual(seen["scratch"], settings.parent)
        self.assertFalse(seen["scratch"].exists(), "every private home is removed after the run")


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
