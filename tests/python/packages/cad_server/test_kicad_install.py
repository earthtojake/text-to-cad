"""``cad.kicad._program``: the kicad integration runs KiCad's command line alone -- kicode's, or the one
``CAD_KICAD_CLI`` names -- never a person's own KiCad.

Where ``kicad-cli`` is looked for and what is refused: only a file named exactly ``kicad-cli``
(``kicad-cli.exe``) is ever returned -- never ``kicad``, a ``kicad-cli-nightly`` wrapper or a
launcher, and never one on PATH or in KiCad's installation folders. Every run is headless (no
``DISPLAY``, no ``WAYLAND_DISPLAY``) with every KiCad home (settings, documents, cache, data, temp,
``HOME``) in a private folder that is removed after the run: kicode's (``kicode.environment``) for its
kicad-cli. No KiCad: the candidates are small scripts, and kicode a stand-in module.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from cad.engine.formats.kicad import models3d
from cad.kicad import _check as cli
from cad.kicad import _program as install

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

    def _find(self, *folders: Path, kicode=None, **env: str) -> Path:
        variables = {"PATH": os.pathsep.join(str(folder) for folder in folders), **env}
        with mock.patch.dict(os.environ, variables, clear=False), mock.patch.dict(sys.modules, {"kicode": kicode}):
            if "CAD_KICAD_CLI" not in env:
                os.environ.pop("CAD_KICAD_CLI", None)
            return install.find_kicad_cli()

    def _kicode(self, executable: Path) -> types.ModuleType:
        module = types.ModuleType("kicode")
        module.executable = lambda: executable
        module.environment = lambda root: {"KICAD_CONFIG_HOME": str(Path(root) / "settings"), "APPDIR": "kicode"}
        module.KICAD_VERSION = "10.99.0"
        return module

    def test_the_environment_variable_wins_over_kicode(self) -> None:
        other = self._executable(self.root / "other", "kicad-cli")
        packaged = self._executable(self.root / "kicode", "kicad-cli")
        self.assertEqual(self._find(kicode=self._kicode(packaged), CAD_KICAD_CLI=str(other)), other)

    def test_the_environment_variable_naming_anything_but_kicad_cli_is_refused(self) -> None:
        for named in (self.app, self.nightly, self.root / "open"):
            with self.subTest(named=named.name), \
                    self.assertRaisesRegex(install.KicadMissingError, "CAD_KICAD_CLI names .*which is not kicad-cli"):
                self._find(self.stable.parent, CAD_KICAD_CLI=str(named))
        with self.assertRaisesRegex(install.KicadMissingError, "CAD_KICAD_CLI names .*not a file"):
            self._find(self.stable.parent, CAD_KICAD_CLI=str(self.empty / f"kicad-cli{EXE}"))

    def test_kicodes_kicad_cli_is_found_and_never_one_on_path(self) -> None:
        packaged = self._executable(self.root / "kicode", "kicad-cli")
        self.assertEqual(self._find(self.stable.parent, kicode=self._kicode(packaged)), packaged)
        with self.assertRaisesRegex(install.KicadMissingError, "not found.*cad\\[kicad\\].*CAD_KICAD_CLI"):
            self._find(self.stable.parent, self.nightly.parent, self.app.parent)

    def test_cad_run_kicad_cli_runs_the_environment_s_then_kicode_s_never_path_s_or_the_variable_s(self) -> None:
        from cad.kicad import _command

        packaged = self._executable(self.root / "kicode", "kicad-cli")
        environment = self.root / "env" / "bin"
        environment.mkdir(parents=True)
        python = environment / f"python{EXE}"
        variables = {"PATH": str(self.stable.parent), "CAD_KICAD_CLI": str(self.stable)}
        with mock.patch.object(_command.sys, "executable", str(python)), mock.patch.dict(os.environ, variables), \
                mock.patch.dict(sys.modules, {"kicode": self._kicode(packaged)}):
            self.assertEqual(_command.program(), packaged, "a kicode with no console script: its executable")
            script = self._executable(environment / "scripts", "kicad-cli")
            script.replace(environment / script.name)
            self.assertEqual(_command.program(), environment / script.name, "kicode's console script comes first")
        with mock.patch.object(_command.sys, "executable", str(self.empty / "python")), \
                mock.patch.dict(os.environ, variables), mock.patch.dict(sys.modules, {"kicode": None}):
            self.assertIsNone(_command.program(), "never one on PATH or CAD_KICAD_CLI's")

    def test_kicodes_version_is_its_own_never_asked(self) -> None:
        packaged = self._executable(self.root / "kicode", "kicad-cli")
        with mock.patch.dict(sys.modules, {"kicode": self._kicode(packaged)}), \
                mock.patch.object(install.subprocess, "run", side_effect=AssertionError("kicad-cli is not run")):
            self.assertEqual("10.99.0", install.kicad_version(packaged))
            self.assertEqual(packaged, install.check_api_server(packaged))
            self.assertTrue(install.carried())
        with mock.patch.dict(sys.modules, {"kicode": None}), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_KICAD_CLI", None)
            self.assertFalse(install.carried(), "without kicode or CAD_KICAD_CLI the command runs KiCad elsewhere")


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
        # The person's own library variables, which their KiCad reads, and their own folders: never a run's.
        own = {"KICAD10_3RD_PARTY": "someone-packages", "KICAD_USER_TEMPLATE_DIR": "someone-templates"}
        person.update(DISPLAY=":0", WAYLAND_DISPLAY="wayland-0", KICAD_STOCK_DATA_HOME="stock",
                      KICAD9_3DMODEL_DIR="someone-library", KICAD10_SYMBOL_DIR="someone-symbols",
                      KISYSMOD="someone-footprints", KICAD9_DESIGN_BLOCK_DIR="someone-blocks", **own)
        stock = {name for names in install.STOCK_VARIABLES.values() for name in names}
        for platform, names in self.HOMES.items():
            # KiCad's installation is the test's own (no KiCad of this computer's): its 3D, footprint, symbol,
            # template and design-block libraries side by side, CAD_KICAD_3DMODELS naming the first.
            with self.subTest(platform=platform), tempfile.TemporaryDirectory(prefix="tmp-kicad-env-") as folder, \
                    mock.patch.object(install.programs.sys, "platform", platform), \
                    mock.patch.dict(sys.modules, {"kicode": None}), \
                    mock.patch.object(models3d, "installations", lambda *_args, **_options: []), \
                    mock.patch.dict(os.environ, {**person, "CAD_KICAD_3DMODELS": os.path.join(folder, "kicad", "3dmodels")}):
                root = Path(folder)
                kicad = os.path.realpath(root / "kicad")
                for kind in ("3dmodels", *install.STOCK_VARIABLES):
                    os.makedirs(os.path.join(kicad, kind))
                env = install.headless_env(root)
                self.assertNotIn("DISPLAY", env)
                self.assertNotIn("WAYLAND_DISPLAY", env)
                for name in names:
                    path = Path(env[name])
                    self.assertTrue(path.is_relative_to(root), f"{name}={path} is outside {root}")
                    self.assertTrue(path.is_dir(), f"{name}={path} was not made")
                self.assertEqual(Path(env["KICAD_CONFIG_HOME"]), root / "settings")
                # A kicad-cli CAD_KICAD_CLI names finds its stock data by this; only kicode's sets it.
                self.assertEqual(env["KICAD_STOCK_DATA_HOME"], "stock")
                # Every 3D library variable names the library the board view reads first, and every other library
                # variable the folder of its name beside it, the installation's; the person's own folders are
                # KiCad's defaults, in the run's homes.
                self.assertEqual({env[name] for name in install.LIBRARY_VARIABLES}, {os.path.join(kicad, "3dmodels")})
                for kind, variables in install.STOCK_VARIABLES.items():
                    self.assertEqual({env[name] for name in variables}, {os.path.join(kicad, kind)}, kind)
                for name in own:
                    self.assertNotIn(name, env)
                # Everything else is this process's own, untouched.
                for name in env.keys() - set(names) - set(install.LIBRARY_VARIABLES) - stock:
                    self.assertEqual(env[name], os.environ[name], name)

    def test_kicads_other_libraries_are_an_installations_the_one_named_first(self) -> None:
        """Each of KiCad's other libraries is the first folder of its name in an installation of KiCad: one whose
        ``3dmodels`` CAD_KICAD_3DMODELS names, then each installed KiCad. A folder of models by another name is
        no installation, whatever lies beside it; a library no installation has is unnamed, whatever the
        caller's own variable says."""
        with tempfile.TemporaryDirectory(prefix="tmp-kicad-libraries-") as folder:
            root = Path(os.path.realpath(folder))
            models, kicad, installed = root / "parts" / "models", root / "kicad", root / "installed"
            for made in (models, root / "parts" / "symbols", kicad / "3dmodels", kicad / "symbols",
                         installed / "footprints"):
                made.mkdir(parents=True)
            named = os.pathsep.join([str(models), str(kicad / "3dmodels")])
            with mock.patch.dict(sys.modules, {"kicode": None}), \
                    mock.patch.object(models3d, "installations", lambda *_args, **_options: [str(installed)]), \
                    mock.patch.dict(os.environ, {"CAD_KICAD_3DMODELS": named, "KICAD10_TEMPLATE_DIR": "someone"}):
                env = install.headless_env(root / "run")
        self.assertEqual(env["KICAD10_3DMODEL_DIR"], str(models))
        self.assertEqual(env["KICAD10_SYMBOL_DIR"], str(kicad / "symbols"))
        self.assertEqual(env["KICAD10_FOOTPRINT_DIR"], str(installed / "footprints"))
        self.assertNotIn("KICAD10_TEMPLATE_DIR", env)

    def test_kicodes_kicad_cli_gets_kicodes_variables(self) -> None:
        packaged = Path(tempfile.mkdtemp(prefix="tmp-kicode-")) / "kicad-cli"
        packaged.write_text("", encoding="utf-8")
        self.addCleanup(lambda: __import__("shutil").rmtree(packaged.parent, ignore_errors=True))
        kicode = types.ModuleType("kicode")
        kicode.executable = lambda: packaged
        kicode.environment = lambda root: {"KICAD_CONFIG_HOME": str(Path(root) / "kicode-settings"), "APPDIR": "app"}
        with tempfile.TemporaryDirectory(prefix="tmp-kicad-env-") as folder, \
                mock.patch.dict(sys.modules, {"kicode": kicode}), mock.patch.dict(os.environ, {"DISPLAY": ":0"}):
            env = install.headless_env(Path(folder), packaged)
            self.assertEqual(env["KICAD_CONFIG_HOME"], str(Path(folder) / "kicode-settings"))
            self.assertEqual(env["APPDIR"], "app")
            self.assertNotIn("DISPLAY", env)
            other = install.headless_env(Path(folder), Path("/opt/kicad/bin/kicad-cli"))
            self.assertEqual(other["KICAD_CONFIG_HOME"], str(Path(folder) / "settings"))
            self.assertNotEqual(other.get("APPDIR"), "app")

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
        self.assertEqual(seen["command"][:3], [str(fake_cli), "pcb", "drc"])
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
