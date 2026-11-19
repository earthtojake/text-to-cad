"""The install script: scripts/install/install.py, and the two thin scripts that run it.

Each test runs install.py in a fresh temporary home with stand-in programs on PATH (``tests/python/support/agent_apps.py``:
the agent apps' CLIs, uv, npx, git), which record how they were called and change nothing else. No real app, network,
uv or cad runs. What each app's row does, and the terminal's logo and live line, are tested where cad's own table of apps
is (``tests/python/packages/cad_server/plugin``).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import zipfile

from tests.python.support.agent_apps import LATEST, STAND_IN, AgentApps
from tests.python.support.paths import REPO_ROOT

INSTALL = REPO_ROOT / "scripts" / "install"
spec = importlib.util.spec_from_file_location("text_to_cad_install", INSTALL / "install.py")
install = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = install
spec.loader.exec_module(install)


def exe(path: Path, main: str) -> Path:
    """A cad.exe as 0.11 wrote it: distlib's launcher, a shebang naming the ``cad-launcher`` beside it, then a zip whose
    ``__main__.py`` is ``main`` (0.11's carries the mark)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", main)
    path.write_bytes(b"MZ launcher\n#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe -I\n" + path.read_bytes())
    return path


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallScriptTests(AgentApps):
    PROGRAMS = ("uv", "git")

    def run_install(self, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        self.forget_calls()
        return subprocess.run([sys.executable, str(INSTALL / "install.py"), *argv], env=self.environ(**extra),
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def switched(self) -> list:
        """What each ``cad plugin update auto on`` was told of how the run is ending (``CAD_INSTALL_FAILED``)."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [call["failed"] for call in map(json.loads, lines)
                if call["name"] == "cad" and call["argv"] == ["plugin", "update", "auto", "on"]]

    def tools(self, **versions: str) -> None:
        """uv's tools, as the stand-in uv keeps them, each with its command in ~/.local/bin."""
        (self.root / "uv.json").write_text(json.dumps(versions), encoding="utf-8")
        for name in versions:
            self.uv_bin.mkdir(parents=True, exist_ok=True)
            (self.uv_bin / "cad").write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
            (self.uv_bin / "cad").chmod(0o755)

    def no_tools(self) -> None:
        """uv with no tools, and no cad command in ~/.local/bin."""
        (self.root / "uv.json").unlink(missing_ok=True)
        (self.uv_bin / "cad").unlink(missing_ok=True)

    def installs(self) -> list:
        """The `uv tool install` calls, each without its first two words."""
        return [argv[2:] for argv in self.calls("uv") if argv[:2] == ["tool", "install"]]

    def test_a_fresh_computer_gets_cad_and_the_plugin_in_every_app_found(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "muse")
        (self.home / ".cursor").mkdir()
        (self.home / ".cline").mkdir()
        # Muse has no copy yet: its update fails, and it installs from the `latest` branch fetched once.
        done = self.run_install(FAKE_FAIL="muse:update")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        # cad: PyPI's newest, as a uv tool; then the plugin's automatic updates turned on, by that cad.
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertIn("Installing cad with uv.", done.stdout)
        self.assertEqual(self.calls("cad"), [["plugin", "update", "auto", "on"]])
        self.assertEqual(self.switched(), [""], "told the run is ending well: cad keeps this release")
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        # Cursor and Grok Build load Claude Code's plugin: none of their own.
        self.assertEqual(self.calls("grok"), [])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # An agent with no plugin command gets the skills in its own folder, from `latest`.
        self.assertIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls("git")[0][:6], ["clone", "--quiet", "--depth", "1", "--branch", "latest"])
        self.assertEqual(len(self.calls("git")), 1)
        fetched = self.calls("git")[0][-1]
        self.assertEqual(self.calls("muse"), [["plugins", "update", "text-to-cad"], ["plugins", "install", fetched],
                                              ["plugins", "approve", "text-to-cad"]])
        for line in ("Claude Code: installed", "Codex: installed", "Gemini CLI: installed",
                     "Grok Build: skipped: it loads Claude Code's plugin", "Cursor: skipped: it loads Claude Code's plugin",
                     "Cline: installed: 2 skills in ~/.cline/skills", "Muse: installed",
                     "other supported apps were not found here.", "Start a new session in each app to use it."):
            self.assertIn(line, done.stdout)
        self.assertNotIn("removed", done.stdout)

    def test_with_no_cad_the_newest_is_installed_and_a_cad_there_is_left_alone_whatever_its_release(self) -> None:
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": "0.13.0"})
        # Nothing found, nothing installed: no word of a new session.
        self.assertNotIn("Start a new session", done.stdout)
        # A cad tool here that starts, older or newer than PyPI's newest: left as it is (cad updates itself), and its
        # plugin switch turned on all the same.
        for there in ("0.13.0", "0.1.0", "99.0.0"):
            self.tools(cad=there)
            done = self.run_install(FAKE_PYPI="5.0.0")
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertEqual(self.installs(), [], there)
            self.assertIn(f"cad {there} is installed already: it is left as it is, and updates itself.", done.stdout)
            self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
            self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": there})

    def test_a_cad_that_does_not_start_is_installed_again(self) -> None:
        # Windows can leave a tool half-replaced: running the install command again is how it is repaired.
        self.tools(cad="1.0.0")
        report = self.root / "report.json"
        done = self.run_install(FAKE_PYPI="5.0.0", FAKE_FAIL="cad:--version", CAD_INSTALL_REPORT=str(report))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 1.0.0 is installed but does not start: installing it again with uv.", done.stdout)
        self.assertNotIn("Installing cad with uv.", done.stdout)
        self.assertEqual(self.installs(), [["--reinstall", *install.UV_TOOL_ARGS, "cad"]])
        self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": "5.0.0"})
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["release"], found["setup"]), ("5.0.0", 0))
        # The reinstall fails too: the run fails, and says which cad the computer still has.
        self.tools(cad="1.0.0")
        done = self.run_install(FAKE_FAIL="cad:--version,uv:install", CAD_INSTALL_REPORT=str(report))
        self.assertEqual(1, done.returncode)
        self.assertIn("cad: failed (uv tool install exit status 1; what uv said is above).", done.stdout)
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["release"], found["setup"]), ("1.0.0", 1))

    def pipx_cad(self, version: str = "0.13.0", link: bool = True) -> dict:
        """cad as ``pipx install cad`` leaves it: pipx's environment of cad (its metadata, its own ``cad``, a stand-in)
        and, with ``link``, its command in ~/.local/bin, a link to that (pipx's bin folder by default, and uv's). What
        the stand-in pipx says."""
        venvs = self.home / ".local" / "share" / "pipx" / "venvs"
        own = venvs / "cad" / "bin" / "cad"
        own.parent.mkdir(parents=True)
        (venvs / "cad" / "pipx_metadata.json").write_text(json.dumps(
            {"main_package": {"package": "cad", "package_or_url": "cad", "package_version": version}}), encoding="utf-8")
        own.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
        own.chmod(0o755)
        if link:
            self.uv_bin.mkdir(parents=True, exist_ok=True)
            (self.uv_bin / "cad").symlink_to(own)
        return {"FAKE_PIPX_VENVS": str(venvs), "FAKE_PIPX_BIN": str(self.uv_bin)}

    def test_a_cad_pipx_installed_is_left_alone_as_uv_s_is_and_uv_installs_no_second(self) -> None:
        said = self.pipx_cad()
        self.programs("pipx")
        report = self.root / "report.json"
        done = self.run_install(CAD_INSTALL_REPORT=str(report), **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [])
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertNotIn("another program's", done.stdout)
        self.assertEqual(self.calls("pipx"), [["environment", "--value", "PIPX_LOCAL_VENVS"],
                                              ["environment", "--value", "PIPX_BIN_DIR"]])
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.13.0", "setup": 0})
        # pipx 1.0, which has no `pipx environment`, and no link in ~/.local/bin: its list says where its cad is.
        (self.uv_bin / "cad").unlink()
        done = self.run_install(FAKE_PIPX_1_0="1", **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")[-1]), ([], ["list", "--json"]))
        # pipx not found: its link in ~/.local/bin says whose cad it is.
        (self.uv_bin / "cad").symlink_to(self.home / ".local" / "share" / "pipx" / "venvs" / "cad" / "bin" / "cad")
        (self.bin / "pipx").unlink()
        done = self.run_install(**said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))
        self.assertIn("cad 0.13.0 is installed already: it is left as it is, and updates itself.", done.stdout)
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        # uv's cad is there too: uv's is the one, and pipx is not asked.
        self.programs("pipx")
        (self.root / "uv.json").write_text(json.dumps({"cad": "0.12.0"}), encoding="utf-8")
        done = self.run_install(**said)
        self.assertIn("cad 0.12.0 is installed already", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))

    def test_a_cad_pipx_installed_that_does_not_start_is_installed_again_by_pipx_never_by_uv(self) -> None:
        said = self.pipx_cad("0.12.0")
        self.programs("pipx")
        (self.home / ".cline").mkdir()
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="cad:--version", FAKE_PYPI="0.14.0", CAD_INSTALL_REPORT=str(report), **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.12.0 is installed with pipx but does not start: installing it again with pipx.",
                      done.stdout)
        self.assertEqual(self.installs(), [], "never with uv")
        self.assertEqual(self.calls("pipx")[-1], ["install", "--force", "cad"])
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.14.0", "setup": 0})
        # pipx's install fails, or pipx is not found: said in one line, and the apps are done all the same.
        for fail, line in (("cad:--version,pipx:install", "cad: failed (pipx install exit status 1; what pipx said is "
                                                          "above), so cad 0.14.0 could not be installed again."),
                           ("cad:--version", "cad 0.14.0, installed with pipx, does not start, and pipx was not found "
                                             "here, so it could not be installed again.")):
            with self.subTest(fail=fail):
                if "pipx" not in fail:
                    (self.bin / "pipx").unlink()
                done = self.run_install(FAKE_FAIL=fail, CAD_INSTALL_REPORT=str(report), **said)
                self.assertEqual(1, done.returncode)
                self.assertIn(line, done.stdout)
                self.assertNotIn("run `pipx", done.stdout)
                self.assertEqual(self.installs(), [])
                self.assertIn("Cline: updated", done.stdout)
                self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["setup"], 1)

    def test_pipx_without_a_cad_or_a_link_into_another_of_its_environments_is_no_cad(self) -> None:
        said = self.pipx_cad(link=False)
        (self.home / ".local" / "share" / "pipx" / "venvs" / "cad" / "pipx_metadata.json").write_text(json.dumps(
            {"main_package": {"package": "other", "package_version": "1.0"}}), encoding="utf-8")
        self.programs("pipx")
        done = self.run_install(**said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]], "uv's cad, as on any")
        self.no_tools()
        other = self.home / ".local" / "share" / "pipx" / "venvs" / "other" / "bin" / "cad"
        other.parent.mkdir(parents=True)
        other.write_text("#!/bin/sh\n", encoding="utf-8")
        (self.uv_bin / "cad").symlink_to(other)
        done = self.run_install(**said)
        self.assertEqual(1, done.returncode)
        self.assertIn("is another program's cad command", done.stdout)

    def test_the_old_cad_command_goes_and_another_program_s_stops_the_cad_step(self) -> None:
        # 0.10.0-0.11.11 wrote ~/.local/bin/cad, an sh script with our mark: set aside before uv puts its own there,
        # and put back where uv fails, so the computer keeps a cad command.
        text = "#!/bin/sh\n# cad proxy: 9\n# The cad command: runs ...\nexit 1\n"
        old = self.write(".local/bin/cad", text)
        done = self.run_install(FAKE_FAIL="uv:install")
        self.assertEqual(1, done.returncode)
        self.assertEqual(old.read_text(encoding="utf-8"), text)
        self.assertNotIn("Removed the cad command", done.stdout)
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("Removed the cad command of an earlier release (~/.local/bin/cad).", done.stdout)
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertNotIn("cad proxy", old.read_text(encoding="utf-8"))  # uv's command in its place
        # Someone else's cad there: kept, and cad is not installed; the apps are done all the same.
        (self.root / "uv.json").unlink()
        mine = self.write(".local/bin/cad", "#!/bin/sh\necho my own cad\n")
        (self.home / ".cline").mkdir()
        done = self.run_install()
        self.assertEqual(1, done.returncode)
        self.assertEqual(mine.read_text(encoding="utf-8"), "#!/bin/sh\necho my own cad\n")
        self.assertEqual(self.installs(), [])
        self.assertIn("cad: not installed: ~/.local/bin/cad is another program's cad command, which uv will not "
                      "replace. Move it away, then run this again.", done.stdout)
        self.assertIn("Cline: installed", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertEqual(self.calls("cad"), [])

    def test_the_old_windows_commands_are_known_by_their_mark(self) -> None:
        # 0.11's cad.exe (``exe``); 0.10's cad.cmd. uv's own cad.exe is a launcher and a zip too, with no mark.
        bin_ = self.home / ".local/bin"
        bin_.mkdir(parents=True)
        old = exe(bin_ / "cad.exe", "# cad proxy: 11\n# The cad command on Windows (cad.exe)\nimport json\n")
        cmd = self.write(".local/bin/cad.cmd", "@echo off\r\nrem cad proxy: 9\r\nrem The cad command\r\n")
        uv_made = exe(self.root / "uv-cad.exe", "import sys\nfrom cad_server.cli import main\nsys.exit(main())\n")
        self.assertEqual([install.old_launcher(path) for path in (old, cmd, uv_made)], [True, True, False])
        # And the Python 0.11's cad.exe ran: cad-launcher beside it, a virtual environment its shebang names.
        self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\nuv = 0.9.5\n")
        self.write(".local/bin/cad-launcher/Scripts/python.exe", "MZ")
        here = install.Here(self.environ(), platform="win32")
        everything = [".cad.cmd.text-to-cad-old", ".cad.exe.text-to-cad-old", ".cad-launcher.text-to-cad-old"]
        problem, moved = install.make_room(here, bin_, {})
        self.assertIsNone(problem)
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), sorted(everything))
        install.settle(here, moved, False)  # uv's cad did not go in: all of it back as it was
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), ["cad-launcher", "cad.cmd", "cad.exe"])
        self.assertTrue((bin_ / "cad-launcher/Scripts/python.exe").is_file())
        problem, moved = install.make_room(here, bin_, {})
        install.settle(here, moved, True)
        self.assertEqual(sorted(path.name for path in bin_.iterdir()), [])
        # A cad-launcher that is no virtual environment, or beside a cad.exe of ours that does not name it, stays.
        for shebang, cfg in ((b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe", False),
                             (b"#!C:\\elsewhere\\python.exe", True)):
            (bin_ / "cad-launcher").mkdir()
            if cfg:
                self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\n")
            exe(bin_ / "cad.exe", "# cad proxy: 11\n").write_bytes(
                (bin_ / "cad.exe").read_bytes().replace(b"#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe", shebang))
            problem, moved = install.make_room(here, bin_, {})
            install.settle(here, moved, True)
            self.assertEqual(sorted(path.name for path in bin_.iterdir()), ["cad-launcher"], shebang)
            install.discard(bin_ / "cad-launcher")
        # Someone else's cad.exe stops it; one uv lists as its own does not.
        uv_made.rename(bin_ / "cad.exe")
        self.assertIn("is another program's cad command", install.make_room(here, bin_, {})[0])
        self.assertEqual(install.make_room(here, bin_, {"cad": install.Tool("1.0.0", {"cad": str(bin_ / "cad.exe")})}),
                         (None, []))

    def test_on_windows_a_cad_exe_in_uv_s_way_is_set_aside_and_uv_s_folder_goes_on_the_path(self) -> None:
        # uv cannot replace a cad.exe that runs (it fails halfway, measured), but one that runs can be renamed: uv's
        # cad.exe and the tool environment's own go aside, into uv's bin folder (never the environment, which uv
        # deletes), under cad's own update's name; back where uv fails, deleted where it is in.
        folder = self.uv_bin
        env = self.home / "AppData/Roaming/uv/tools/cad"
        mine = [self.write(".local/bin/cad.exe", "uv's"), self.write("AppData/Roaming/uv/tools/cad/Scripts/cad.exe", "env's")]
        tool = install.Tool("1.0.0", {"cad": str(mine[0])}, str(env))
        moved = install.set_aside(folder, tool)
        self.assertEqual([path for path, _aside in moved], mine)
        self.assertTrue(all(aside.parent == folder and aside.is_file() and not path.exists() for path, aside in moved))
        self.assertEqual(len(list(folder.glob(install.ASIDE.format(stamp="*", n="*")))), 2)
        install.put_back(moved, False)
        self.assertEqual([path.read_text(encoding="utf-8") for path in mine], ["uv's", "env's"])
        install.put_back(install.set_aside(folder, tool), True)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [])
        # Where uv has no cad tool, a cad.exe there is not its: never moved.
        theirs = self.write(".local/bin/cad.exe", "another program's")
        self.assertEqual(install.set_aside(folder, None), [])
        self.assertEqual(theirs.read_text(encoding="utf-8"), "another program's")

    def test_uv_s_folder_goes_on_the_path_by_uv_s_own_command_on_every_system(self) -> None:
        # A shell whose PATH lacks uv's bin folder (winget's or Homebrew's uv puts its own folder there): uv's own
        # `uv tool update-shell` puts it on the PATH for new terminals, as uv's and Codex's installers do; nothing of
        # ours edits a profile. UV_NO_MODIFY_PATH, uv's own switch, stops it; where it fails, a line says what to do.
        uv = str(self.bin / "uv")
        put = ("~/.local/bin is on your PATH now for new terminals (uv tool update-shell): apps and terminals opened "
               "before this one see it once restarted.\n")
        not_put = ("~/.local/bin is not on this shell's PATH: open a new terminal to use cad (where it is still not "
                   "found, run `uv tool update-shell`).\n")
        for platform, separator in (("darwin", ":"), ("linux", ":"), ("win32", ";")):
            for extra, called, line in (({}, True, put), ({"UV_NO_MODIFY_PATH": "1"}, False, not_put),
                                        ({"FAKE_FAIL": "uv:update-shell", "FAKE_EXIT": "2"}, True, not_put),
                                        ({"PATH": f"{self.bin}{separator}{self.uv_bin}"}, False, "")):
                if self.log.exists():
                    self.log.unlink()
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    install.on_path(install.Here(self.environ(**extra), platform=platform), uv, self.uv_bin)
                self.assertEqual(self.calls("uv"), [["tool", "update-shell"]] if called else [], (platform, extra))
                self.assertEqual(said.getvalue(), line, (platform, extra))
        self.assertFalse((self.home / ".zshenv").exists(), "the stand-in uv edits no profile; nor does install.py")

    def test_on_windows_a_running_cad_exe_never_stops_the_install_and_a_later_run_removes_what_it_left(self) -> None:
        # Measured on Windows 11 (0.11.0 and 0.11.10): a person's agent types the old `cad update`, whose cad.exe (0.11's
        # launcher) runs the install command. The launcher and its Python go aside, uv's cad goes in, and what was set
        # aside, still running, cannot be deleted (Windows refuses): it stays, and nothing is said of it. The next run
        # deletes it, quietly, and nothing else in uv's bin folder.
        here = install.Here(self.environ(UV=str(self.bin / "uv")), platform="win32")
        exe(self.uv_bin / "cad.exe", "# cad proxy: 11\n# The cad command on Windows (cad.exe)\n")
        self.write(".local/bin/cad-launcher/pyvenv.cfg", "home = C:\\Python314\n")
        discard = install.discard

        def running(path: Path) -> None:  # Windows deletes no file that runs, nor a folder holding one
            if path.name == ".cad.exe.text-to-cad-old":
                raise PermissionError(13, "Access is denied")
            discard(path)

        def busy(_path: Path) -> None:
            raise PermissionError(13, "The process cannot access the file")

        said = io.StringIO()
        with mock.patch.object(install, "discard", running), mock.patch.object(install, "_rmtree", busy), \
                contextlib.redirect_stdout(said):
            cad = install.install_cad(here)
        self.assertEqual((cad.code, cad.release), (0, "0.13.0"), said.getvalue())
        self.assertIn("Installing cad with uv.", said.getvalue())
        self.assertNotIn("not installed", said.getvalue())
        self.assertNotIn("Removed the cad command", said.getvalue())
        left = sorted(path.name for path in self.uv_bin.iterdir())
        self.assertEqual([name for name in left if not name.startswith(".text-to-cad-trash-")],
                         [".cad.exe.text-to-cad-old", "cad"])
        self.assertEqual(len(left), 3, left)
        # The next run: cad is here and starts; what was left goes, quietly. Someone else's files stay.
        self.write(".local/bin/notes.old", "mine")
        self.write(".local/bin/.cad.exe.backup", "mine")
        self.write(".local/bin/" + install.ASIDE.format(stamp="123-456", n=0), "cad's own update's")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            cad = install.install_cad(here)
        self.assertEqual(cad.code, 0)
        self.assertEqual(said.getvalue(), "cad 0.13.0 is installed already: it is left as it is, and updates itself.\n")
        self.assertEqual(sorted(path.name for path in self.uv_bin.iterdir()), [".cad.exe.backup", "cad", "notes.old"])
        # Where a cad command of 0.10.0-0.11.11 is still there (its install did not happen), nothing set aside goes.
        kept = self.write(".local/bin/.cad-launcher.text-to-cad-old/pyvenv.cfg", "home = C:\\Python314\n")
        exe(self.uv_bin / "cad.exe", "# cad proxy: 11\n")
        install.tidy(here, self.uv_bin)
        self.assertTrue(kept.is_file())

    def test_the_plugin_switch_is_tolerated_where_cad_does_not_know_it(self) -> None:
        # A cad with no `cad plugin update auto` (a usage error, exit 2): one line, and the install has not failed.
        self.tools(cad="0.11.10")
        done = self.run_install(FAKE_FAIL="cad:plugin", FAKE_EXIT="2")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("cad"), [["--version"], ["plugin", "update", "auto", "on"]])
        said = [line for line in done.stdout.splitlines() if "update auto" in line]
        self.assertEqual(said, ["cad 0.11.10 has no `cad plugin update auto`: the plugin will not follow cad's updates. "
                                "Run this command again to update the plugin."])
        # Any other failure: what cad said, in one line.
        done = self.run_install(FAKE_FAIL="cad:plugin")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("The plugin's automatic updates were not turned on (cad said: cad: something went wrong). Run "
                      "this command again to update the plugin.", done.stdout)

    def test_its_output_is_utf_8_on_windows_where_it_is_no_console(self) -> None:
        # As `cad setup`'s, which it runs on the same streams: a pipe or a file on Windows; never a console, never
        # another system.
        class Stream:
            def __init__(self, console: bool) -> None:
                self.console = console

            def isatty(self) -> bool:
                return self.console

        self.assertTrue(install.utf8(Stream(False), "nt"))
        self.assertEqual([install.utf8(Stream(True), "nt"), install.utf8(Stream(False), "posix"),
                          install.utf8(Stream(True), "posix"), install.utf8(None, "nt")], [False] * 4)

    def test_a_failed_cad_install_fails_the_run_and_the_apps_are_done_all_the_same(self) -> None:
        self.programs("codex", "gemini")
        done = self.run_install(FAKE_FAIL="uv:install")
        self.assertEqual(1, done.returncode)
        self.assertIn("cad: failed (uv tool install exit status 1; what uv said is above). Where this ran inside an "
                      "app or an agent's sandbox, run it again in a terminal of your own.", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertEqual(self.calls("cad"), [], "no cad to switch on")

    def test_a_run_in_which_every_app_found_failed_fails_and_tells_cad_so(self) -> None:
        # It turns the switch on all the same (cad is here), so the plugin is kept on a computer whose runs keep
        # failing, and tells cad the run is ending badly, so cad keeps no release for it and its server runs it again.
        self.programs("claude")
        self.tools(cad="0.13.0")
        done = self.run_install(FAKE_FAIL="claude")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("Claude Code: failed", done.stdout)
        self.assertIn("No app got the plugin", done.stdout)
        self.assertEqual(self.switched(), ["1"])
        self.assertNotIn("Start a new session", done.stdout)

    def test_the_report_cad_s_hand_over_reads_changes_nothing_the_run_says(self) -> None:
        # CAD_INSTALL_REPORT (set by cad's own hand-over, cad_server._internal.install_script): what the run did, each
        # app by its key, written whole; the run's output and exit status as without it, and a report that cannot be
        # written fails nothing.
        self.programs("codex", "gemini")
        self.tools(cad="0.13.0")
        plain = self.run_install(FAKE_FAIL="codex")
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(report))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (plain.returncode, plain.stdout, plain.stderr))
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual({key: found[key] for key in ("schema", "release", "setup")},
                         {"schema": "text-to-cad install report/1", "release": "0.13.0", "setup": 0})
        self.assertEqual(set(found["apps"]), {app.key for app in install.APPS})
        self.assertEqual((found["apps"]["codex"], found["apps"]["gemini"], found["apps"]["claude"]),
                         ("failed", "installed", "not found"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if "report" in path.name), ["report.json"])
        self.no_tools()
        done = self.run_install(FAKE_FAIL="uv:install", FAKE_EXIT="3", CAD_INSTALL_REPORT=str(report))
        self.assertEqual((json.loads(report.read_text(encoding="utf-8"))["setup"],
                          json.loads(report.read_text(encoding="utf-8"))["release"]), (3, None))
        self.tools(cad="0.13.0")
        nowhere = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(self.root / "no folder" / "report.json"))
        self.assertEqual((nowhere.returncode, nowhere.stdout, nowhere.stderr),
                         (plain.returncode, plain.stdout, plain.stderr))

    def test_it_takes_no_options_and_does_nothing_when_given_one(self) -> None:
        # Old releases' docs piped options to install.sh (`sh -s -- --dry-run`, `--uninstall`, `--add X`).
        done = self.run_install("--uninstall")
        self.assertEqual(2, done.returncode)
        self.assertIn("takes no options", done.stderr)
        script = subprocess.run(["/bin/sh", "-s", "--", "--add", "0.11.11"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"),
                                env=self.environ(PATH=f"{self.bin}:/usr/bin:/bin"), capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(2, script.returncode)
        self.assertIn("takes no options", script.stderr)
        self.assertEqual(self.calls(), [])

    def run_sh(self, **extra: str) -> subprocess.CompletedProcess:
        if self.log.exists():
            self.log.unlink()
        return subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True,
                              text=True, env=self.environ(CAD_INSTALL_PY=str(INSTALL / "install.py"),
                                                          PATH=f"{self.bin}:/usr/bin:/bin", **extra), timeout=60)

    def test_install_sh_runs_install_py_with_uv_s_python(self) -> None:
        self.programs("uv")
        script = self.run_sh()
        self.assertEqual(0, script.returncode, script.stderr)
        run = self.calls("uv")[-1]
        self.assertEqual(run[:-1], ["run", "--no-config", "--managed-python", "--python", "3.14", "--no-project"])
        self.assertEqual(Path(run[-1]).name, "install.py")

    def uvs(self) -> list:
        """Each uv call: the program that ran (its path) and its first word."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [(Path(call["path"]), call["argv"][0]) for call in map(json.loads, lines) if call["name"] == "uv"]

    def test_install_sh_installs_a_newer_uv_where_uv_is_too_old_for_python_3_14_and_runs_with_it(self) -> None:
        # A uv older than 0.9.0 that cannot update itself (Homebrew's, pip's: no receipt of uv's own installer): uv's
        # own installer runs, as where uv is missing, with nothing added, and the run goes on with the uv it put in
        # its folder (~/.local/bin here), never the old one first on PATH. The person is never asked to update uv.
        self.programs("uv", "curl")
        old, new = self.bin / "uv", self.uv_bin / "uv"
        installer = ('echo "$#" > "$HOME/installer-args"\nmkdir -p "$HOME/.local/bin"\n'
                     f'cp "{old}" "$HOME/.local/bin/uv"\necho "$NEW_UV" > "$HOME/.local/bin/uv-version"\n')
        refused = "uv 0.8.24 is older than 0.9.0, and uv's installer did not install a newer uv (what it said is above)."
        # Its installer could not be downloaded, or put in a uv still too old: one line says so, and nothing runs.
        for extra in ({"FAKE_FAIL": "curl"}, {"NEW_UV": "0.8.30"}):
            script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, **extra)
            self.assertEqual(1, script.returncode, extra)
            self.assertIn(refused, script.stderr)
            self.assertNotIn("brew", script.stderr)
            self.assertNotIn("run", [word for _path, word in self.uvs()], extra)
        script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, NEW_UV="0.13.9")
        self.assertEqual(0, script.returncode, script.stderr)
        self.assertIn("uv 0.8.24 is older than 0.9.0, the first that installs Python 3.14: installing a newer uv with "
                      "uv's own installer (https://docs.astral.sh/uv/).", script.stderr)
        self.assertEqual([argv[1] for argv in self.calls("curl")], ["https://astral.sh/uv/install.sh"])
        self.assertEqual((self.home / "installer-args").read_text(encoding="utf-8").strip(), "0")
        self.assertEqual(self.uvs(), [(old, "--version"), (new, "--version"), (new, "run")])
        # uv from its own installer (its receipt) updates itself first; where it is still too old, the installer runs.
        self.write(".config/uv/uv-receipt.json", "{}")
        script = self.run_sh(FAKE_UV_VERSION="0.8.24", FAKE_UV_INSTALLER=installer, NEW_UV="0.13.9")
        self.assertEqual(0, script.returncode, script.stderr)
        self.assertIn("updating it (uv self update)", script.stderr)
        self.assertEqual(self.uvs(), [(old, "--version"), (old, "self"), (old, "--version"), (new, "--version"),
                                      (new, "run")])

    def test_the_development_install_puts_the_checkout_in_place_of_the_published_copy(self) -> None:
        dev_spec = importlib.util.spec_from_file_location("text_to_cad_dev_install", INSTALL / "dev_install.py")
        dev_install = importlib.util.module_from_spec(dev_spec)
        dev_spec.loader.exec_module(dev_install)
        folder = self.root / "dev-plugin" / "text-to-cad"
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        dev_install.assemble(folder, f"{release}-dev.1")
        self.assertEqual(json.loads((folder / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["name"], "earthtojake-dev")
        self.assertEqual(json.loads((folder / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"],
                         f"{release}-dev.1")
        # Codex's server, the one there is, runs the editable tool's cad under a bare command (Codex has dropped,
        # with no error, a server whose command is a path), and keeps its start allowance.
        self.assertEqual(sorted(path.name for path in folder.glob("*mcp*.json")), ["codex.mcp.json"])
        server = json.loads((folder / "codex.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["cad"]
        self.assertEqual((server["command"], server["args"], server["startup_timeout_sec"]), ("cad", ["mcp"], 300))
        # The folder's catalog comes in; then the published copy goes.
        self.programs("claude")
        self.claude_records({"text-to-cad@earthtojake": 1},
                            {"earthtojake": {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}})
        plugin = dev_install.cad_plugin  # cad's own table of apps, loaded from this checkout's files
        source = plugin.source.Source(folder=folder, catalog=plugin.source.DEV_CATALOG, skills_dir=folder / "skills")
        claude = [app for app in plugin.apps.APPS if app.key == "claude"]
        lines = plugin.apps.install_apps(plugin.computer.Here(self.environ()), source, claude, say=lambda line: None)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", str(folder)],
                                                ["plugin", "install", "text-to-cad@earthtojake-dev"],
                                                ["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "--scope", "user", "earthtojake"]])
        self.assertIn("Claude Code: installed (removed old copies: text-to-cad@earthtojake)", lines)
        # cad: the checkout, an editable uv tool, its automatic updates off; --release puts the published one back.
        with mock.patch.dict(os.environ, self.environ(), clear=True):
            self.assertEqual(dev_install.install_checkout(str(self.bin / "uv")), 0)
            self.assertEqual(self.installs(), [[*install.UV_TOOL_ARGS, "--reinstall-package", "cad", "--editable",
                                                str(REPO_ROOT / "packages" / "cad")]])
            self.assertEqual(self.calls("cad"), [["update", "auto", "off"]])
            self.assertTrue(dev_install.editable(str(self.bin / "uv")))
            self.log.unlink()
            with mock.patch.object(sys, "stdout", new=open(os.devnull, "w", encoding="utf-8")) as quiet:
                self.addCleanup(quiet.close)
                self.assertEqual(dev_install.main(["--release"]), 0)
            self.assertEqual([argv for argv in self.calls("uv") if argv[1] in ("install", "uninstall")],
                             [["tool", "uninstall", "cad"], ["tool", "install", *install.UV_TOOL_ARGS, "cad"]])
            # The install command leaves cad's own automatic updates as they are: --release turns them on again.
            self.assertEqual(self.calls("cad"), [["plugin", "update", "auto", "on"], ["update", "auto", "on"]])
            self.assertFalse(dev_install.editable(str(self.bin / "uv")))

    def test_install_ps1_ends_a_failure_in_a_terminating_error(self) -> None:
        # Not runnable here: the Windows install jobs run it. `powershell -Command "irm ... | iex"` exits 1 only on a
        # terminating error; Write-Error left it at 0 (measured on Windows 11), and `exit` closes a person's window.
        text = (INSTALL / "install.ps1").read_text(encoding="utf-8")
        self.assertRegex(text, r'\nif \(\$LASTEXITCODE\) \{\n    throw "[^"]+"\n\}\n?$')
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("Write-Error", code)
        self.assertNotRegex(code, r"(?m)^\s*exit\b")
        # Where uv's Python could not be set up (inside an app's package, first time), the person is told what to do.
        self.assertIn("& $uv python find --no-config --system --managed-python 3.14", text)
        self.assertIn("open PowerShell from the Start menu, run the install command there once", text)
        # A uv too old for Python 3.14 that cannot update itself (winget's, pip's): uv's own installer, as install.sh
        # runs it, and the run goes on with the uv it put in its folder; the person is never asked to update uv.
        self.assertIn("$null = Install-Uv\n            $version = $null\n            $uv = Find-InstalledUv", text)
        self.assertNotIn("winget upgrade", text)

    def test_the_installer_names_no_release(self) -> None:
        # Nothing in the install command changes with a release: no fallback, no pin, nothing a release stamps.
        for name in ("install.sh", "install.ps1", "install.py"):
            text = (INSTALL / name).read_text(encoding="utf-8")
            self.assertNotIn("FALLBACK", text, name)
            self.assertNotRegex(text, r"(cad|cad-server|cad-mcp)==[0-9]", name)
            self.assertNotIn("api.texttocad.dev", text, f"{name} reads no version feed")
        for name in ("sync-version.mjs", "check-version.sh"):
            self.assertNotIn("install", (REPO_ROOT / "scripts/release" / name).read_text(encoding="utf-8").replace(
                "installers clone", ""), name)


if __name__ == "__main__":
    unittest.main()
