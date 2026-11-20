"""The install script: scripts/install/install.py, and the two thin scripts that run it.

Each test runs install.py in a fresh temporary home with stand-in programs on PATH (``tests/python/support/agent_apps.py``:
uv, pipx, curl, a ``cad``), which record how they were called and change nothing else. No real app, network, uv or cad
runs: every proxy is a closed port, and a failure's report goes to a stand-in receiver on loopback (``Receiver``).
What the plugin's step does in each agent app, and the terminal's logo and live line, are tested where cad's own table
of apps is (``tests/python/packages/cad_server/plugin``): here that step is the stand-in ``cad``.

``run_install`` runs the checkout's own file, which reports nothing (a development run); ``run_hosted`` a copy alone
in a folder, as the hosted one is run.
"""

from __future__ import annotations

import contextlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
import uuid
import zipfile

from tests.python.support.agent_apps import LATEST, STAND_IN, AgentApps
from tests.python.support.paths import REPO_ROOT

INSTALL = REPO_ROOT / "scripts" / "install"
spec = importlib.util.spec_from_file_location("text_to_cad_install", INSTALL / "install.py")
install = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = install
spec.loader.exec_module(install)

# The newest release's `cad plugin install`, run outside any installed tool: the words after `uv`.
NEWEST = ["tool", "run", "--no-config", "--managed-python", "--python", "3.14", "cad@latest", "plugin", "install"]
HANDED = ["plugin", "install"]
# Asked first, its answer captured, whether the installed cad has that command: it runs nothing.
ASKED = ["plugin", "install", "--help"]
# The switch, turned on last by the installed cad's own command wherever a cad is installed.
AUTO_ON = ["plugin", "update", "auto", "on"]
# What a failure's report names this machine: as cad's own counts do.
PLATFORM = sys.platform if sys.platform in ("darwin", "win32") else "linux" if sys.platform.startswith("linux") else "other"
ARCH = re.sub(r"[^A-Za-z0-9_.+:-]+", "-", platform.machine().lower())[:16]
FIELDS = ["schema", "run", "at", "stage", "outcome", "code", "platform", "arch", "by", "uv"]


# A cad of 0.11.13, as far as this command reaches it (v0.11.13's `cad_server/cli/plugin.py`): no `cad plugin install`
# (argparse's usage error, exit 2, nothing run); `cad plugin update`, which downloads and runs the hosted install command
# -- here this checkout's, once, with what 0.11.13 sets, so a loop would show as a second run of it --; and `cad plugin
# update auto on`, the switch, which keeps a setting and runs nothing. Each call is noted in the stand-ins' log, with the
# variables it was given that the run's edges turn on.
OLD_CAD = """#!{python}
import json, os, subprocess, sys
WATCHED = ("CAD_INSTALL_ATTEMPT", "CAD_PLUGIN_SERVER_RUN", "CAD_INSTALL_FAILED", "CAD_INSTALL_BY_CAD", "CAD_PLUGIN_BY",
           "OLD_CAD_DEPTH")
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({{"name": "cad", "argv": sys.argv[1:], "path": sys.argv[0],
                           "env": {{name: os.environ.get(name) for name in WATCHED}}}}) + "\\n")
argv = sys.argv[1:]
if argv == ["--version"]:
    print("cad 0.11.13")
elif argv == ["update"]:
    print("cad 0.11.13 is the newest release of its major version")
elif argv == ["plugin", "update", "auto", "on"]:
    print("plugin update auto: on")
elif argv == ["plugin", "update"]:
    if os.environ.get("OLD_CAD_DEPTH"):
        sys.exit(99)  # never reached but by a loop
    sys.exit(subprocess.call([sys.executable, {script!r}], stdin=subprocess.DEVNULL,
                             env={{**os.environ, "OLD_CAD_DEPTH": "1", "CAD_INSTALL_BY_CAD": "1"}}))
else:
    print("usage: cad plugin [-h] {{update}} ...", file=sys.stderr)
    print("cad plugin: error: argument command: invalid choice: " + repr(argv[1] if len(argv) > 1 else "")
          + " (choose from 'update')", file=sys.stderr)
    sys.exit(2)
"""


def exe(path: Path, main: str) -> Path:
    """A cad.exe as 0.11 wrote it: distlib's launcher, a shebang naming the ``cad-launcher`` beside it, then a zip whose
    ``__main__.py`` is ``main`` (0.11's carries the mark)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", main)
    path.write_bytes(b"MZ launcher\n#!<launcher_dir>\\cad-launcher\\Scripts\\python.exe -I\n" + path.read_bytes())
    return path


class Receiver:
    """A stand-in for the service a failure's report goes to, on loopback: it keeps each POST (its path, its headers
    by lower-case name, its body) and answers 204, as the service does."""

    def __init__(self) -> None:
        posts = self.posts = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server's name
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                posts.append((self.path, {key.lower(): value for key, value in self.headers.items()}, body))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *_args) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # A short poll: `shutdown` waits one out, at the end of every test.
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    @property
    def url(self) -> str:
        """The service's base, as ``CAD_API_URL`` names one."""
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallScriptTests(AgentApps):
    PROGRAMS = ("uv",)

    def setUp(self) -> None:
        super().setUp()
        self.receiver = Receiver()
        self.addCleanup(self.receiver.close)

    # --- running it ---------------------------------------------------------------------------------------------

    def run_install(self, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        self.forget_calls()
        return subprocess.run([sys.executable, str(INSTALL / "install.py"), *argv], env=self.environ(**extra),
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def reporting(self, **extra: str) -> dict:
        """The computer's environment with the stand-in receiver in the service's place, reached past the closed
        proxies."""
        return self.environ(**{"CAD_API_URL": self.receiver.url, "no_proxy": "127.0.0.1", "NO_PROXY": "127.0.0.1",
                               **extra})

    def run_hosted(self, **extra: str) -> subprocess.CompletedProcess:
        """install.py as the hosted one is run: a copy alone in a folder, which may report a failure."""
        hosted = self.root / "hosted" / "install.py"
        hosted.parent.mkdir(exist_ok=True)
        shutil.copy(INSTALL / "install.py", hosted)
        self.forget_calls()
        del self.receiver.posts[:]
        return subprocess.run([sys.executable, str(hosted)], env=self.reporting(**extra), capture_output=True,
                              text=True, encoding="utf-8", timeout=120)

    def logged(self, name: str) -> list:
        """Each call of the stand-in ``name``, as it noted it."""
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return [call for call in map(json.loads, lines) if call["name"] == name]

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

    def newest(self) -> list:
        """The `uv tool run` calls: the newest release's commands."""
        return [argv for argv in self.calls("uv") if argv[:2] == ["tool", "run"]]

    def report(self, stage: str, code: int, by: str = "person", uv: str = "0.11.0", **crash) -> dict:
        """The one report the receiver took, checked whole: its address, its headers, and its body, which is exactly
        the fields the service reads. The body."""
        self.assertEqual(len(self.receiver.posts), 1, self.receiver.posts)
        path, headers, raw = self.receiver.posts[0]
        self.assertEqual((path, headers["content-type"]), ("/v1/install", "application/json"))
        self.assertNotIn("origin", headers)
        self.assertLess(len(raw), 4096)
        body = json.loads(raw)
        self.assertEqual(list(body), FIELDS + list(crash))
        self.assertEqual(str(uuid.UUID(body["run"])), body["run"])
        self.assertIs(type(body["at"]), int)
        self.assertLess(abs(time.time() - body["at"]), 600)
        self.assertEqual({key: value for key, value in body.items() if key not in ("run", "at")},
                         {"schema": 1, "stage": stage, "outcome": "crashed" if crash else "failed", "code": code,
                          "platform": PLATFORM, "arch": ARCH, "by": by, "uv": uv, **crash})
        return body

    # --- the cad step -------------------------------------------------------------------------------------------

    def test_a_fresh_computer_gets_cad_and_cad_is_handed_the_plugin(self) -> None:
        mark = self.root / "started"
        done = self.run_install(FAKE_LOG_ENV="CAD_PLUGIN_BY,CAD_PLUGIN_REPORT,CAD_INSTALL_MARK",
                                FAKE_PLUGIN_APPS=json.dumps({"claude": "installed"}), CAD_INSTALL_MARK=str(mark))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        # cad: PyPI's newest, as a uv tool; then that tool's own `cad plugin install` and its switch, and nothing else
        # of cad: a cad installed just now is not updated, and the script runs no setup.
        self.assertEqual(self.installs(), [["--managed-python", "--python", "3.14", "cad"]])
        self.assertIn("Installing cad with uv.", done.stdout)
        self.assertEqual(json.loads((self.root / "uv.json").read_text(encoding="utf-8")), {"cad": "0.13.0"})
        asked, handed, switched = self.logged("cad")
        # Asked first, quietly, whether it has `cad plugin install`; then that command, for real.
        self.assertEqual((asked["argv"], asked["path"]), (ASKED, str(self.uv_bin / "cad")))
        self.assertEqual((handed["argv"], handed["path"]), (HANDED, str(self.uv_bin / "cad")))
        self.assertNotIn("usage: cad plugin install", done.stdout + done.stderr)
        # Then, last, that tool's own `cad plugin update auto on`: the person ran this, and the plugin follows cad.
        self.assertEqual((switched["argv"], switched["path"]), (AUTO_ON, str(self.uv_bin / "cad")))
        self.assertEqual(self.newest(), [])
        # cad is told the script began the run, and where to say what it did: a scratch file, gone with the run.
        self.assertEqual(handed["env"]["CAD_PLUGIN_BY"], "script")
        self.assertFalse(Path(handed["env"]["CAD_PLUGIN_REPORT"]).parent.exists())
        # Its output is this run's own: what cad draws on a person's terminal reaches it.
        self.assertIn("cad (stand-in): the plugin, on stdout\n", done.stdout)
        self.assertIn("cad (stand-in): the plugin, on stderr\n", done.stderr)
        # The shell that ran it finds the file it left as it started; the variable goes no further.
        self.assertTrue(mark.is_file())
        self.assertIsNone(handed["env"]["CAD_INSTALL_MARK"])

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
        self.assertEqual(self.calls("cad"), [["--version"], ASKED, HANDED, AUTO_ON])
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["release"], found["setup"]), ("5.0.0", 0))
        # A person's run: installed again just now, so there is nothing to bring up to date.
        self.tools(cad="1.0.0")
        done = self.run_install(FAKE_PYPI="5.0.0", FAKE_FAIL="cad:--version")
        self.assertEqual(self.calls("cad"), [["--version"], ASKED, HANDED, AUTO_ON])
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

    def test_a_cad_pipx_installed_is_a_global_cad_as_uv_s_is_and_uv_installs_no_second(self) -> None:
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
        self.assertEqual(self.calls("cad"), [["--version"], ASKED, HANDED, AUTO_ON])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.13.0", "setup": 0})
        # A person's run brings it up to date by pipx's own cad, and reads pipx's record of it again.
        done = self.run_install(FAKE_CAD_UPDATES="0.14.0", FAKE_UPDATE_EXIT="1", **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("cad"), [["--version"], ["update"], ASKED, HANDED, AUTO_ON])
        self.assertNotIn("cad was not updated", done.stdout)
        self.assertEqual(self.installs(), [])
        # pipx 1.0, which has no `pipx environment`, and no link in ~/.local/bin: its list says where its cad is.
        (self.uv_bin / "cad").unlink()
        done = self.run_install(FAKE_PIPX_1_0="1", **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("Updating cad 0.14.0 to the newest release...\ncad 0.14.0 is the newest release\n", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")[-1]), ([], ["list", "--json"]))
        # pipx not found: its link in ~/.local/bin says whose cad it is.
        (self.uv_bin / "cad").symlink_to(self.home / ".local" / "share" / "pipx" / "venvs" / "cad" / "bin" / "cad")
        (self.bin / "pipx").unlink()
        done = self.run_install(**said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))
        self.assertIn("Updating cad 0.14.0 to the newest release...", done.stdout)
        self.assertEqual(self.calls("cad"), [["--version"], ["update"], ASKED, HANDED, AUTO_ON])
        # uv's cad is there too: uv's is the one, and pipx is not asked.
        self.programs("pipx")
        (self.root / "uv.json").write_text(json.dumps({"cad": "0.12.0"}), encoding="utf-8")
        done = self.run_install(**said)
        self.assertIn("Updating cad 0.12.0 to the newest release...", done.stdout)
        self.assertEqual((self.installs(), self.calls("pipx")), ([], []))

    def test_a_cad_pipx_installed_that_does_not_start_is_installed_again_by_pipx_never_by_uv(self) -> None:
        said = self.pipx_cad("0.12.0")
        self.programs("pipx")
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="cad:--version", FAKE_PYPI="0.14.0", CAD_INSTALL_REPORT=str(report), **said)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.12.0 is installed with pipx but does not start: installing it again with pipx.",
                      done.stdout)
        self.assertEqual(self.installs(), [], "never with uv")
        self.assertEqual(self.calls("pipx")[-1], ["install", "--force", "cad"])
        self.assertEqual(self.calls("cad"), [["--version"], ASKED, HANDED, AUTO_ON])
        self.assertEqual({key: json.loads(report.read_text(encoding="utf-8"))[key] for key in ("release", "setup")},
                         {"release": "0.14.0", "setup": 0})
        # pipx's install fails, or pipx is not found: said in one line, and the plugin's step runs all the same, by
        # the newest cad.
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
                self.assertEqual(self.newest(), [NEWEST])
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
        # Someone else's cad there: kept, and cad is not installed; it is never run, and the plugin's step is the
        # newest cad's.
        (self.root / "uv.json").unlink()
        mine = self.write(".local/bin/cad", "#!/bin/sh\necho my own cad\n")
        done = self.run_install()
        self.assertEqual(1, done.returncode)
        self.assertEqual(mine.read_text(encoding="utf-8"), "#!/bin/sh\necho my own cad\n")
        self.assertEqual(self.installs(), [])
        self.assertIn("cad: not installed: ~/.local/bin/cad is another program's cad command, which uv will not "
                      "replace. Move it away, then run this again.", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertNotIn("my own cad", done.stdout)
        self.assertEqual((self.calls("cad"), self.newest()), ([], [NEWEST]))

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
        for system, separator in (("darwin", ":"), ("linux", ":"), ("win32", ";")):
            for extra, called, line in (({}, True, put), ({"UV_NO_MODIFY_PATH": "1"}, False, not_put),
                                        ({"FAKE_FAIL": "uv:update-shell", "FAKE_EXIT": "2"}, True, not_put),
                                        ({"PATH": f"{self.bin}{separator}{self.uv_bin}"}, False, "")):
                if self.log.exists():
                    self.log.unlink()
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    install.on_path(install.Here(self.environ(**extra), platform=system), uv, self.uv_bin)
                self.assertEqual(self.calls("uv"), [["tool", "update-shell"]] if called else [], (system, extra))
                self.assertEqual(said.getvalue(), line, (system, extra))
        self.assertFalse((self.home / ".zshenv").exists(), "the stand-in uv edits no profile; nor does install.py")

    def test_on_windows_a_running_cad_exe_never_stops_the_install_and_a_later_run_removes_what_it_left(self) -> None:
        # Measured on Windows 11 (0.11.0 and 0.11.10): a person's agent types the old `cad update`, whose cad.exe (0.11's
        # launcher) runs the install command. The launcher and its Python go aside, uv's cad goes in, and what was set
        # aside, still running, cannot be deleted (Windows refuses): it stays, and nothing is said of it. The next run
        # deletes it, quietly, and nothing else in uv's bin folder.
        here = install.Here(self.environ(UV=str(self.bin / "uv"), CAD_INSTALL_BY_CAD="1"), platform="win32")
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
        self.assertEqual((cad.code, cad.release, cad.there), (0, "0.13.0", False), said.getvalue())
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
        self.assertEqual((cad.code, cad.there), (0, True))
        self.assertEqual(said.getvalue(), "cad 0.13.0 is installed already: it is left as it is, and updates itself.\n")
        self.assertEqual(sorted(path.name for path in self.uv_bin.iterdir()), [".cad.exe.backup", "cad", "notes.old"])
        # Where a cad command of 0.10.0-0.11.11 is still there (its install did not happen), nothing set aside goes.
        kept = self.write(".local/bin/.cad-launcher.text-to-cad-old/pyvenv.cfg", "home = C:\\Python314\n")
        exe(self.uv_bin / "cad.exe", "# cad proxy: 11\n")
        install.tidy(here, self.uv_bin)
        self.assertTrue(kept.is_file())

    def test_its_output_is_utf_8_on_windows_where_it_is_no_console(self) -> None:
        # As cad's and uv's, which it runs on the same streams: a pipe or a file on Windows; never a console, never
        # another system.
        class Stream:
            def __init__(self, console: bool) -> None:
                self.console = console

            def isatty(self) -> bool:
                return self.console

        self.assertTrue(install.utf8(Stream(False), "nt"))
        self.assertEqual([install.utf8(Stream(True), "nt"), install.utf8(Stream(False), "posix"),
                          install.utf8(Stream(True), "posix"), install.utf8(None, "nt")], [False] * 4)

    # --- a cad that is here: brought up to date for a person, never for cad ---------------------------------------

    def test_a_person_s_run_brings_a_cad_that_is_here_up_to_date_by_that_cad_s_own_update(self) -> None:
        # Older or newer than PyPI's newest, uv installs nothing: the tool's own `cad update` is what updates it, and
        # it stays inside its major (no --major). Never PATH's cad: a shell may find another one first.
        self.programs("cad")
        for there in ("0.13.0", "0.1.0", "99.0.0"):
            self.tools(cad=there)
            done = self.run_install(FAKE_PYPI="5.0.0")
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertEqual(self.installs(), [], there)
            self.assertEqual([(call["argv"], call["path"]) for call in self.logged("cad")],
                             [(argv, str(self.uv_bin / "cad")) for argv in (["--version"], ["update"], ASKED, HANDED,
                                                                                 AUTO_ON)])
            self.assertIn(f"cad {there} is the newest release\n", done.stdout)
        # Its exit status says little: 0 with nothing newer (above), non-zero with the update done all the same. What
        # uv holds afterwards is what counts.
        done = self.run_install(FAKE_CAD_UPDATES="99.1.0", FAKE_UPDATE_EXIT="1")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 99.0.0 updated to 99.1.0\n", done.stdout)
        self.assertEqual(self.calls("cad")[-2:], [HANDED, AUTO_ON])

    def test_before_cad_takes_over_a_person_s_run_says_one_line_of_its_own_and_one_of_the_update(self) -> None:
        """What a person sees before cad's ``cad plugin install`` takes over (and plays its logo): the line that a
        failure's report may be sent, then one line as the update begins and one of what came of it -- updated, the
        newest already, or not updated, with cad's own most telling line as the reason. Nothing ``cad update``
        printed, on either stream. On a pipe, as here, the second line follows the first."""
        self.tools(cad="0.11.13")
        for extra, result in (
                ({"FAKE_CAD_UPDATES": "0.11.14"}, "cad 0.11.13 updated to 0.11.14"),
                ({}, "cad 0.11.13 is the newest release"),
                # cad's own line where it said one: a release of a higher major is out, which it does not install.
                ({"FAKE_UPDATE_SAID": "cad 0.11.13 is the newest 0.x release|cad 1.0.0, a new major version, is out"},
                 "cad 0.11.13 is the newest 0.x release"),
                ({"FAKE_UPDATE_EXIT": "1", "FAKE_UPDATE_SAID": "cad update: asking the cad server|error: the cad server "
                  "did not answer in 600 seconds|Run `cad update` again later."},
                 "cad 0.11.13 was not updated now (error: the cad server did not answer in 600 seconds): it updates "
                 "itself.")):
            with self.subTest(result=result):
                self.tools(cad="0.11.13")
                done = self.run_hosted(**extra)
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                before = done.stdout.split("cad (stand-in): the plugin, on stdout\n")[0]
                self.assertEqual(before.splitlines(), [install.NOTICE, "Updating cad 0.11.13 to the newest release...",
                                                       result])
                self.assertEqual(done.stderr, "cad (stand-in): the plugin, on stderr\n")
                self.assertNotIn("stand-in): update", done.stdout + done.stderr)
                self.assertEqual(self.calls("cad"), [["--version"], ["update"], ASKED, HANDED, AUTO_ON])

    def test_in_a_terminal_the_update_s_result_takes_the_place_of_its_first_line(self) -> None:
        self.tools(cad="0.13.0")

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        first = "Updating cad 0.13.0 to the newest release..."
        for columns, said in (("80", f"{first}\r{'cad 0.13.0 updated to 0.13.1'.ljust(len(first))}\n"),
                              ("40", f"{first}\ncad 0.13.0 updated to 0.13.1\n")):  # too narrow: a line each
            self.tools(cad="0.13.0")
            shown = Terminal()
            here = install.Here(self.environ(FAKE_CAD_UPDATES="0.13.1"))
            with contextlib.redirect_stdout(shown), mock.patch.dict(os.environ, {"COLUMNS": columns}):
                install.update(here, install.Cad("0.13.0", 0, str(self.uv_bin / "cad"), there=True))
            self.assertEqual(shown.getvalue(), said, columns)

    def test_a_cad_that_was_not_updated_never_fails_the_run(self) -> None:
        self.tools(cad="0.13.0")
        # Refused, failed, or still queued behind a busy server (exit 1): one line, and the run goes on. Its reason is
        # cad's own line that says most, as cad chooses one for an app's failure: the first that reads as an error,
        # else the last.
        from cad_server.plugin import computer

        self.assertEqual(install.ERROR_SAID.pattern, computer.ERROR_SAID.pattern)
        self.assertEqual(install.ERROR_SAID.flags, computer.ERROR_SAID.flags)
        done = self.run_install(FAKE_UPDATE_EXIT="1")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("cad 0.13.0 was not updated now (cad (stand-in): update, on stderr): it updates itself.\n",
                      done.stdout)
        self.assertEqual(self.calls("cad"), [["--version"], ["update"], ASKED, HANDED, AUTO_ON])
        # No answer in the time it has: stopped, said, and the run goes on.
        here = install.Here(self.environ(FAKE_UPDATE_SLEEP="30"))
        said = io.StringIO()
        with mock.patch.object(install, "UPDATE_SECONDS", 0.5), contextlib.redirect_stdout(said):
            install.update(here, install.Cad("0.13.0", 0, str(self.uv_bin / "cad"), there=True))
        self.assertEqual(said.getvalue(), "Updating cad 0.13.0 to the newest release...\ncad 0.13.0 was not updated "
                                          "now (no answer in 0 minutes): it updates itself.\n")

    def test_cad_s_own_run_of_it_brings_no_cad_up_to_date(self) -> None:
        # What the releases that run this command set, each alone: the cad that runs it is left as it is.
        self.tools(cad="0.11.13")
        for name, value in (("CAD_INSTALL_BY_CAD", "1"), ("CAD_INSTALL_ATTEMPT", "1763500000.5"),
                            ("CAD_INSTALL_REPORT", str(self.root / "report.json"))):
            with self.subTest(name=name):
                done = self.run_install(**{name: value})
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                self.assertIn("cad 0.11.13 is installed already: it is left as it is, and updates itself.\n",
                              done.stdout)
                self.assertEqual(self.calls("cad"), [["--version"], ASKED, HANDED, AUTO_ON])

    # --- the plugin: cad's own step --------------------------------------------------------------------------------

    def test_a_cad_with_no_plugin_install_is_passed_over_for_the_newest_cad_s(self) -> None:
        # 0.11.12 and 0.11.13 run this command themselves, and have no `cad plugin install`: asked first, quietly
        # (`--help`: a usage error, exit 2, which the person never sees), the newest release's runs instead, outside
        # the installed tool, told what the tool's would have been. Never `cad plugin update`, which on those releases
        # runs this command, and never `cad setup`.
        self.tools(cad="0.11.13")
        report = self.root / "report.json"
        done = self.run_install(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_APPS=json.dumps({"codex": "updated"}),
                                FAKE_LOG_ENV="CAD_PLUGIN_BY,CAD_PLUGIN_REPORT", CAD_INSTALL_BY_CAD="1",
                                CAD_INSTALL_REPORT=str(report))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("cad"), [["--version"], ASKED, AUTO_ON])
        self.assertEqual(self.newest(), [NEWEST])
        self.assertIn("cad 0.11.13 has no `cad plugin install`: the newest cad's runs instead (uv tool run cad@latest), "
                      "which uv downloads once.\nuv (stand-in): the plugin, on stdout\n", done.stdout)
        self.assertNotIn("usage:", done.stdout + done.stderr)
        self.assertNotIn("invalid choice", done.stdout + done.stderr)
        newest, = [call for call in self.logged("uv") if call["argv"] == NEWEST]
        self.assertEqual(newest["env"]["CAD_PLUGIN_BY"], "script")
        self.assertEqual(Path(newest["env"]["CAD_PLUGIN_REPORT"]).name, "plugin-report.json")
        self.assertFalse(Path(newest["env"]["CAD_PLUGIN_REPORT"]).parent.exists())
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                         {"schema": "text-to-cad install report/1", "release": "0.11.13", "setup": 0,
                          "apps": {"codex": "updated"}})
        self.assertEqual(self.installs(), [])
        # Before the docs site serves this script, its deploy asks PyPI's newest cad for this command's help
        # (scripts/release/newest_cad.py, held by test_newest_cad.py): the words uv was given here, and no others.
        spec = importlib.util.spec_from_file_location("newest_cad", REPO_ROOT / "scripts/release/newest_cad.py")
        asked = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(asked)
        self.assertEqual(self.newest(), [list(asked.HAND_OVER)])
        self.assertEqual(asked.ASKED, (*asked.HAND_OVER, "--help"))
        # A cad that says it has the command, or gives any answer but argparse's usage error, has its command run for
        # real; where that ends 2 having written no report, it had none either: the newest cad's runs, once.
        for help_code in ("0", "1"):
            with self.subTest(help_code=help_code):
                done = self.run_install(FAKE_PLUGIN_HELP_CAD=help_code, FAKE_PLUGIN_EXIT_CAD="2",
                                        FAKE_PLUGIN_APPS=json.dumps({"codex": "updated"}), CAD_INSTALL_BY_CAD="1")
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                self.assertEqual((self.calls("cad"), self.newest()),
                                 ([["--version"], ASKED, HANDED, AUTO_ON], [NEWEST]))
                self.assertIn("cad (stand-in): the plugin, on stdout\ncad 0.11.13 has no `cad plugin install`: the "
                              "newest cad's runs instead (uv tool run cad@latest), which uv downloads once.\n",
                              done.stdout)

    def test_run_against_0_11_13_nothing_loops(self) -> None:
        """0.11.13's own ``cad plugin update`` runs this command (by its server too, which names its run
        ``CAD_INSTALL_ATTEMPT``); it has no ``cad plugin install``. Whoever began the run, this command asks that cad
        whether it has ``cad plugin install`` (``--help``: exit 2, its answer captured), runs the newest release's in
        its place, and last turns the switch on by the installed cad's own command, once, telling it the run ended badly
        exactly where the plugin's step did not end well: never ``cad plugin update`` alone, which would run this
        command again. Nothing it starts carries a cad server's name for its run, so the newest release's step never
        takes an older server's run for its own."""
        self.tools(cad="0.11.13")
        (self.uv_bin / "cad").write_text(OLD_CAD.format(python=sys.executable, script=str(INSTALL / "install.py")),
                                         encoding="utf-8")
        watched = "CAD_INSTALL_ATTEMPT,CAD_PLUGIN_SERVER_RUN,CAD_INSTALL_FAILED,CAD_INSTALL_BY_CAD,CAD_PLUGIN_BY"
        server = {"CAD_INSTALL_BY_CAD": "1", "CAD_INSTALL_ATTEMPT": "1763500000.5", "CAD_PLUGIN_SERVER_RUN": "7.0"}
        for began, extra, code, failed in (
                (server, {"FAKE_PLUGIN_APPS": json.dumps({"claude": "updated"})}, 0, None),
                (server, {"FAKE_PLUGIN_EXIT_UV": "1"}, 1, "1"),
                (server, {"FAKE_PLUGIN_EXIT_UV": "75"}, 75, "1"),
                ({"CAD_INSTALL_BY_CAD": "1"}, {"FAKE_PLUGIN_EXIT_UV": "1", "CAD_INSTALL_FAILED": "1"}, 1, "1"),
                ({}, {"CAD_INSTALL_FAILED": "1"}, 0, None)):
            with self.subTest(began=sorted(began), extra=extra):
                done = self.run_install(FAKE_LOG_ENV=watched, **began, **extra)
                self.assertEqual(code, done.returncode, done.stdout + done.stderr)
                steps = [(call["name"], call["argv"]) for call in map(json.loads, self.log.read_text(
                    encoding="utf-8").splitlines()) if call["name"] == "cad" or call["argv"][:2] == ["tool", "run"]]
                self.assertEqual(steps, [("cad", ["--version"]), *([] if began else [("cad", ["update"])]),
                                         ("cad", ASKED), ("uv", NEWEST), ("cad", AUTO_ON)])
                # Of `cad plugin`, that cad saw the question alone before the newest cad's step, and the person
                # none of its answer: one line of this command's own.
                self.assertNotIn("invalid choice", done.stdout + done.stderr)
                self.assertIn("cad 0.11.13 has no `cad plugin install`: the newest cad's runs instead", done.stdout)
                calls = self.logged("cad") + self.logged("uv")
                self.assertEqual([call for call in calls if call["argv"] == ["plugin", "update"]], [], "no loop")
                self.assertEqual({call["env"].get("OLD_CAD_DEPTH") for call in self.logged("cad")}, {None})
                for call in calls:
                    self.assertIsNone(call["env"]["CAD_INSTALL_ATTEMPT"], call["argv"])
                    self.assertIsNone(call["env"]["CAD_PLUGIN_SERVER_RUN"], call["argv"])
                newest, = [call for call in self.logged("uv") if call["argv"] == NEWEST]
                self.assertEqual(newest["env"]["CAD_PLUGIN_BY"], "script")
                switched, = [call for call in self.logged("cad") if call["argv"] == AUTO_ON]
                self.assertEqual(switched["env"]["CAD_INSTALL_FAILED"], failed)
        # No cad could be installed: the newest release's step all the same, and no switch to turn.
        self.no_tools()
        done = self.run_install(FAKE_FAIL="uv:cad", FAKE_LOG_ENV=watched, **server)
        self.assertEqual(1, done.returncode)
        self.assertEqual((self.calls("cad"), self.newest()), ([], [NEWEST]))

    def test_with_no_cad_at_all_the_newest_cad_s_step_is_tried_once_and_then_the_run_has_failed(self) -> None:
        report = self.root / "report.json"
        # (The stand-in uv fails the call that names `cad` alone, its install: the newest cad's is `cad@latest`.)
        done = self.run_install(FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_EXIT_UV="1",
                                CAD_INSTALL_REPORT=str(report))
        self.assertEqual(1, done.returncode)
        self.assertEqual((self.calls("cad"), self.newest()), ([], [NEWEST]))
        self.assertIn("cad: failed (uv tool install exit status 3; what uv said is above).", done.stdout)
        self.assertIn("Setting up the plugin with the newest cad all the same (uv tool run cad@latest), which uv "
                      "downloads once.\n", done.stdout)
        self.assertIn("The plugin was not set up in the agent apps (uv tool run exit status 1; what it said is "
                      "above): run this again.\n", done.stdout)
        self.assertIn("cad itself was not installed", done.stdout)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                         {"schema": "text-to-cad install report/1", "release": None, "setup": 3, "apps": {}})
        # Where the newest cad's step runs, the apps are done: the run has failed all the same, for cad is not here.
        done = self.run_install(FAKE_FAIL="uv:cad", FAKE_PLUGIN_APPS=json.dumps({"claude": "installed"}),
                                CAD_INSTALL_REPORT=str(report))
        self.assertEqual(1, done.returncode)
        self.assertEqual(self.newest(), [NEWEST])
        self.assertNotIn("The plugin was not set up", done.stdout)
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((found["setup"], found["apps"]), (1, {"claude": "installed"}))

    def test_the_run_ends_as_the_plugin_s_step_did_and_the_report_cad_reads_is_written_last(self) -> None:
        # CAD_INSTALL_REPORT (0.11.12's and 0.11.13's hand-over sets it, and judges the file the moment it is there):
        # `apps` always a dict, as cad's step said them, `setup` an integer, the file written whole, after
        # everything else. The run ends 0 only where that step did: 1 where every app it found failed, 75 where
        # another run was going (cad's own status for it), 1 for anything else. A step that ended non-zero and named
        # no app as failed is one failure more in `apps`, the one thing its readers take for a run to try again.
        self.tools(cad="0.13.0")
        report = self.root / "report.json"
        failed = {"claude": "failed", "codex": "not found"}
        unsaid = {"plugin": "failed"}
        for extra, code, apps, line in (
                ({"FAKE_PLUGIN_APPS": json.dumps({"claude": "updated", "gemini": "skipped"})}, 0,
                 {"claude": "updated", "gemini": "skipped"}, None),
                ({}, 0, {}, None),
                ({"FAKE_PLUGIN_EXIT_CAD": "1", "FAKE_PLUGIN_APPS": json.dumps(failed)}, 1, failed, None),
                ({"FAKE_PLUGIN_EXIT_CAD": "75"}, 75, unsaid, None),
                ({"FAKE_PLUGIN_EXIT_CAD": "124"}, 1, unsaid, "The plugin was not set up in the agent apps (cad plugin "
                                                             "install exit status 124; what it said is above): run this again.\n"),
                ({"FAKE_PLUGIN_EXIT_CAD": "2", "FAKE_PLUGIN_EXIT_UV": "75"}, 75, unsaid, None)):
            with self.subTest(extra=extra):
                report.unlink(missing_ok=True)
                plain = self.run_install(CAD_INSTALL_BY_CAD="1", **extra)
                done = self.run_install(CAD_INSTALL_BY_CAD="1", CAD_INSTALL_REPORT=str(report),
                                        FAKE_LOG_EXISTS=str(report), **extra)
                # The report changes nothing the run says or how it ends.
                self.assertEqual((done.returncode, done.stdout, done.stderr),
                                 (plain.returncode, plain.stdout, plain.stderr))
                self.assertEqual(code, done.returncode, done.stdout + done.stderr)
                self.assertEqual("The plugin was not set up" in done.stdout, line is not None)
                self.assertIn(line or "", done.stdout)
                found = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(found, {"schema": "text-to-cad install report/1", "release": "0.13.0", "setup": 0,
                                         "apps": apps})
                self.assertIs(type(found["setup"]), int)
                # Not there while anything the run starts still runs; nothing left beside it.
                self.assertEqual([call["exists"] for call in self.logged("cad") + self.logged("uv")],
                                 [False] * len(self.calls()))
                self.assertEqual(sorted(path.name for path in self.root.iterdir() if "report" in path.name),
                                 ["report.json"])
        # A report that cannot be written fails nothing.
        nowhere = self.run_install(CAD_INSTALL_BY_CAD="1", CAD_INSTALL_REPORT=str(self.root / "no folder" / "r.json"))
        self.assertEqual((nowhere.returncode, nowhere.stderr), (0, "cad (stand-in): the plugin, on stderr\n"))

    def test_a_plugin_s_step_where_an_app_failed_keeps_no_release_by_the_switch_and_ends_as_it_did(self) -> None:
        # The plugin is up to date for a release only where every app found went well: where the step's report names
        # an app as failed, even with exit status 0, the switch is turned on with CAD_INSTALL_FAILED=1, so the cad
        # takes nothing as up to date (released 0.11.12 and 0.11.13 read it the same way) and its server tries again.
        # The run's exit status is the step's, and the report cad reads carries each app as it said it.
        self.tools(cad="0.13.0")
        report = self.root / "report.json"
        for apps, code, failed in (({"claude": "failed", "codex": "updated"}, 0, "1"),
                                   ({"claude": "failed", "codex": "failed"}, 1, "1"),
                                   ({"claude": "updated", "codex": "not found"}, 0, None),
                                   ({}, 0, None)):
            with self.subTest(apps=apps):
                done = self.run_install(FAKE_PLUGIN_APPS=json.dumps(apps) if apps else "",
                                        FAKE_PLUGIN_EXIT_CAD=str(code), FAKE_LOG_ENV="CAD_INSTALL_FAILED",
                                        CAD_INSTALL_REPORT=str(report))
                self.assertEqual(code, done.returncode, done.stdout + done.stderr)
                switched, = [call for call in self.logged("cad") if call["argv"] == AUTO_ON]
                self.assertEqual(switched["env"]["CAD_INSTALL_FAILED"], failed)
                self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["apps"], apps)
                self.assertEqual(self.calls("cad")[-2:], [HANDED, AUTO_ON])
        # A person's own CAD_INSTALL_FAILED is never passed on: only this run's step says it.
        done = self.run_install(FAKE_PLUGIN_APPS=json.dumps({"codex": "updated"}), FAKE_LOG_ENV="CAD_INSTALL_FAILED",
                                CAD_INSTALL_FAILED="1")
        switched, = [call for call in self.logged("cad") if call["argv"] == AUTO_ON]
        self.assertEqual((done.returncode, switched["env"]["CAD_INSTALL_FAILED"]), (0, None))

    def test_a_plugin_s_step_that_ended_badly_and_named_no_failure_is_one_to_the_releases_that_read_the_report(
            self) -> None:
        # 0.11.12 and 0.11.13 never read the run's exit status: by the report alone they take the run as done, and
        # stop running it, or as failed, and run it again later. Their rule, which no release can change now
        # (v0.11.13, `cad_server._internal.install_script.judge`).
        def judged(found: dict) -> str:
            steps = found.get("apps") if isinstance(found, dict) else None
            if not isinstance(steps, dict):
                return "no_report"
            if found.get("setup") != 0 or isinstance(found.get("setup"), bool):
                return "setup"
            return "app" if any(status == "failed" for status in steps.values()) else "done"

        report = self.root / "report.json"

        def ends(**extra: str) -> tuple:
            report.unlink(missing_ok=True)
            done = self.run_install(CAD_INSTALL_BY_CAD="1", CAD_INSTALL_REPORT=str(report), **extra)
            found = json.loads(report.read_text(encoding="utf-8"))
            return done.returncode, found["setup"], found["apps"], judged(found)

        unsaid = {"plugin": "failed"}
        self.tools(cad="0.13.0")
        # It raised (Python's own exit status, 1), or was stopped: no report of its own, so one failure in ours.
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="1"), (1, 0, unsaid, "app"))
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="124"), (1, 0, unsaid, "app"))
        # Ended by a signal, with whatever it had started: the tool's cad answers `--version`, then kills itself.
        killed = "#!/bin/sh\n[ \"$1\" = --version ] && exit 0\nkill -KILL $$\n"
        (self.uv_bin / "cad").write_text(killed, encoding="utf-8")
        self.assertEqual(ends(), (1, 0, unsaid, "app"))
        # It could not be started at all: the tool's cad is gone once it has said its version.
        (self.uv_bin / "cad").write_text("#!/bin/sh\n/bin/rm -- \"$0\"\n", encoding="utf-8")
        self.assertEqual(ends(), (1, 0, unsaid, "app"))
        self.assertEqual(self.newest(), [], "a cad that has the command is never passed over for the newest")
        # A cad with no such command, and the newest cad's step raised, or uv could not run it: the same.
        self.tools(cad="0.11.13")
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_EXIT_UV="1"), (1, 0, unsaid, "app"))
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_FAIL="uv:run", FAKE_EXIT="2"), (1, 0, unsaid, "app"))
        # Nothing ran because another run was going: this run did none of the work either.
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_EXIT_UV="75"), (75, 0, unsaid, "app"))
        # It ended badly after the apps, having named none as failed (it raised as it turned the switch on, say):
        # what it said of them is kept, and the failure added.
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_EXIT_UV="1", FAKE_PLUGIN_APPS='{"codex": "updated"}'),
                         (1, 0, {"codex": "updated", "plugin": "failed"}, "app"))
        # A failure the step named itself is passed on as it said it, and a step that ended 0 is never a failure.
        said = {"claude": "failed", "codex": "updated"}
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_EXIT_UV="1", FAKE_PLUGIN_APPS=json.dumps(said)),
                         (1, 0, said, "app"))
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_APPS='{"codex": "updated"}'),
                         (0, 0, {"codex": "updated"}, "done"))
        self.assertEqual(ends(FAKE_PLUGIN_EXIT_CAD="2"), (0, 0, {}, "done"))
        # Where cad itself could not be installed, `setup` is what its readers go by: no failure is made up for
        # apps no cad reached, and what the newest cad's step said of them is passed on.
        self.no_tools()
        self.assertEqual(ends(FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_EXIT_UV="1"), (1, 3, {}, "setup"))
        self.assertEqual(ends(FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_APPS='{"claude": "installed"}'),
                         (1, 3, {"claude": "installed"}, "setup"))

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

    # --- one report of a failure ----------------------------------------------------------------------------------

    def test_a_run_that_fails_with_no_cad_to_count_it_sends_one_report_of_where(self) -> None:
        # cad could not be installed: said first, in one line, then reported, whatever the plugin's step does after.
        done = self.run_hosted(FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_EXIT_UV="1")
        self.assertEqual(1, done.returncode)
        self.assertEqual(done.stdout.splitlines()[0], install.NOTICE)
        self.assertEqual(done.stdout.count(install.NOTICE), 1)
        self.report("cad", 3)
        # No cad could run the plugin's step: the one this computer has has none, and the newest could not be run.
        self.tools(cad="0.11.13")
        done = self.run_hosted(FAKE_PLUGIN_EXIT_CAD="2", FAKE_PLUGIN_EXIT_UV="1", FAKE_UPDATE_EXIT="1")
        self.assertEqual(1, done.returncode)
        self.report("plugin", 1)
        # uv itself gone since the cad step (`uv` then names nothing a report can ask): the step cannot run at all.
        cad = install.Cad("0.11.13", 0, str(self.uv_bin / "cad"), there=True)
        gone = self.reporting(FAKE_PLUGIN_EXIT_CAD="2", PATH=str(self.root / "nowhere"))
        with mock.patch.object(install, "development", lambda here: False), contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.dict(os.environ, gone, clear=True):
            del self.receiver.posts[:]
            here = install.Here()
            self.assertEqual(install.hand_over(here, cad, install.Reports(here)).code, 127)
        self.report("plugin", 127, uv="none")

    def test_a_run_a_working_cad_counts_sends_nothing(self) -> None:
        # It ended well; every app cad found failed; another run was going; cad's own command failed: cad counts each.
        self.tools(cad="0.13.0")
        for extra, code in (({}, 0), ({"FAKE_PLUGIN_EXIT_CAD": "1", "FAKE_PLUGIN_APPS": '{"claude": "failed"}'}, 1),
                            ({"FAKE_PLUGIN_EXIT_CAD": "75"}, 75), ({"FAKE_PLUGIN_EXIT_CAD": "1"}, 1),
                            ({"FAKE_PLUGIN_EXIT_CAD": "2", "FAKE_PLUGIN_EXIT_UV": "75"}, 75)):
            with self.subTest(extra=extra):
                done = self.run_hosted(**extra)
                self.assertEqual(code, done.returncode, done.stdout + done.stderr)
                self.assertEqual(self.receiver.posts, [])
                self.assertEqual(done.stdout.count(install.NOTICE), 1)

    def test_a_run_cad_started_says_no_line_and_reports_only_where_cad_has_told_the_person(self) -> None:
        # cad runs this command with its output in a log, or thrown away (0.11.12's and 0.11.13's `cad plugin
        # update`, the server's run of it, the bridge's install mode): a line said there is read by nobody, and
        # nothing is sent before a person was told. What cad told them, it keeps in its settings.
        from cad_server import analytics

        self.assertEqual((install.TOLD, install.AGREED), (analytics.NOTICE, analytics.DISCLOSURE))
        self.tools(cad="0.11.13")
        failing = {"FAKE_PLUGIN_EXIT_CAD": "2", "FAKE_PLUGIN_EXIT_UV": "1"}
        started = ({"CAD_INSTALL_BY_CAD": "1"}, {"CAD_INSTALL_ATTEMPT": "1763500000.5"},
                   {"CAD_INSTALL_REPORT": str(self.root / "report.json")})
        settings = self.home / ".local" / "state" / "cad" / "settings.json"

        def keep(telemetry: dict) -> None:
            """cad's settings, as cad writes them, with ``telemetry`` what it keeps of the person's answer."""
            self.write(".local/state/cad/settings.json", json.dumps(
                {"plugin": {"auto_update": True}, "telemetry": telemetry}, indent=2, sort_keys=True))

        told = {"notifiedAt": 1763500000.5, "notice": analytics.NOTICE}
        # A computer nobody was told on (no settings; settings that say nothing of it): nothing said, nothing sent,
        # by each of the three variables cad's releases set. The same run, a person's, says its line and reports.
        for kept in (None, {}):
            for by in started:
                with self.subTest(kept=kept, by=by):
                    settings.unlink(missing_ok=True)
                    if kept is not None:
                        keep(kept)
                    done = self.run_hosted(**failing, **by)
                    self.assertEqual((1, [], False), (done.returncode, self.receiver.posts, install.NOTICE in done.stdout))
        done = self.run_hosted(**failing, FAKE_UPDATE_EXIT="1")
        self.assertEqual(done.stdout.count(install.NOTICE), 1)
        self.report("plugin", 1)
        # Told by cad, or having said yes to what is sent now: the report goes, as cad's own counts do, and still no
        # line is said where nobody reads it.
        for kept in (told, {"choice": "on", "disclosure": analytics.DISCLOSURE, "by": "cli", "decidedAt": 1.5, "id": "x"}):
            for by in started:
                with self.subTest(kept=kept, by=by):
                    keep(kept)
                    done = self.run_hosted(**failing, **by)
                    self.assertEqual((1, False), (done.returncode, install.NOTICE in done.stdout))
                    self.report("plugin", 1, by="cad")
        # A no cad keeps is a no, told or not; so is a telling of less than is sent now, a yes to less, and
        # settings that cannot be read.
        for kept in ({**told, "choice": "off", "by": "cli", "decidedAt": 1.5}, {"choice": "off"},
                     {"notifiedAt": 1763500000.5, "notice": analytics.NOTICE - 1}, {"notifiedAt": 1763500000.5},
                     {"choice": "on", "disclosure": analytics.DISCLOSURE - 1}, {"choice": "on"}):
            with self.subTest(kept=kept):
                keep(kept)
                done = self.run_hosted(**failing, CAD_INSTALL_BY_CAD="1")
                self.assertEqual((1, [], False), (done.returncode, self.receiver.posts, install.NOTICE in done.stdout))
        settings.unlink()
        settings.mkdir()
        done = self.run_hosted(**failing, CAD_INSTALL_BY_CAD="1")
        self.assertEqual((1, [], False), (done.returncode, self.receiver.posts, install.NOTICE in done.stdout))
        settings.rmdir()
        # Told in one of cad's state folders and refused in another: the no holds.
        keep(told)
        elsewhere = self.root / "state"
        elsewhere.mkdir()
        (elsewhere / "settings.json").write_text(json.dumps({"telemetry": {"choice": "off"}}), encoding="utf-8")
        done = self.run_hosted(**failing, CAD_INSTALL_BY_CAD="1", CAD_STATE_DIR=str(elsewhere))
        self.assertEqual((1, []), (done.returncode, self.receiver.posts))
        # A crash of the script on a run cad started goes by the same rule.
        (elsewhere / "settings.json").unlink()
        with mock.patch.object(install, "development", lambda here: False):
            for kept, sends in ((told, True), ({}, False)):
                keep(kept)
                here = install.Here(self.reporting(CAD_INSTALL_BY_CAD="1"))
                self.assertEqual(install.Reports(here).on, sends, kept)

    def test_no_report_is_sent_or_spoken_of_where_the_person_the_environment_or_the_place_says_no(self) -> None:
        failing = {"FAKE_FAIL": "uv:cad", "FAKE_PLUGIN_EXIT_UV": "1"}
        # cad's kept settings, as cad writes them: the person's no there is a no here, wherever cad's state folder is.
        settings = self.write(".local/state/cad/settings.json", json.dumps(
            {"plugin": {"auto_update": True}, "telemetry": {"by": "cli", "choice": "off", "decidedAt": 1.5}}, indent=2,
            sort_keys=True))
        elsewhere = self.root / "state" / "settings.json"
        elsewhere.parent.mkdir()
        shutil.copy(settings, elsewhere)
        named = {"CAD_STATE_DIR": str(elsewhere.parent), "XDG_STATE_HOME": str(self.root / "none")}
        # The environment, in cad's own spellings; CI; a checkout's run (the rehearsals' hook, and the checkout's own
        # file, which `run_install` runs).
        for off in ({}, named, {"XDG_STATE_HOME": str(self.root / "none"), "DO_NOT_TRACK": "1"},
                    {"XDG_STATE_HOME": str(self.root / "none"), "CAD_INSTALL_PY": str(INSTALL / "install.py")}):
            with self.subTest(off=off):
                done = self.run_hosted(**failing, **off)
                self.assertEqual((1, [], False), (done.returncode, self.receiver.posts, install.NOTICE in done.stdout))
        settings.unlink()
        done = subprocess.run([sys.executable, str(INSTALL / "install.py")], env=self.reporting(**failing),
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual((1, [], False), (done.returncode, self.receiver.posts, install.NOTICE in done.stdout))
        # Every spelling, asked of the rule itself (the hosted copy's: this file is a checkout's).
        def may(**environ: str) -> bool:
            with mock.patch.object(install, "development", lambda here: bool(here.environ.get("CAD_INSTALL_PY"))):
                return install.reporting(install.Here(self.environ(**environ)))

        self.assertTrue(may())
        self.assertFalse(install.reporting(install.Here(self.environ())), "a checkout's file")
        for off in ({"DO_NOT_TRACK": "1"}, {"DO_NOT_TRACK": " True "}, {"DO_NOT_TRACK": "yes"}, {"DO_NOT_TRACK": "on"},
                    {"CAD_TELEMETRY": "0"}, {"CAD_TELEMETRY": "OFF"}, {"CAD_TELEMETRY": "no"},
                    {"CAD_TELEMETRY": "false"}, {"CI": "true"}, {"CI": "1"}, {"CAD_INSTALL_PY": "x"}, named):
            self.assertFalse(may(**off), off)
        for on in ({"DO_NOT_TRACK": "0"}, {"DO_NOT_TRACK": ""}, {"CAD_TELEMETRY": "1"}, {"CI": "false"}, {"CI": ""}):
            self.assertTrue(may(**on), on)
        # A yes kept there, settings that say nothing of it, or a file that is no JSON, is no no; one that cannot be
        # read now is no yes.
        for text, sent in ((json.dumps({"telemetry": {"choice": "on", "id": "x"}, "other": {"choice": "off"}}), True),
                           (json.dumps({"plugin": {"auto_update": True}}), True), ("[]", True), ("{", True),
                           (json.dumps({"telemetry": {"choice": "off"}}), False)):
            settings.write_text(text, encoding="utf-8")
            self.assertEqual(may(), sent, text)
        settings.unlink()
        settings.mkdir()
        self.assertFalse(may())

    def test_a_report_never_changes_what_the_run_says_or_how_it_ends(self) -> None:
        failing = {"FAKE_FAIL": "uv:cad", "FAKE_PLUGIN_EXIT_UV": "1"}
        taken = self.run_hosted(**failing)
        self.report("cad", 1)
        # A service that cannot be reached; and the same run where none may be sent, but for its first line.
        for extra in ({"CAD_API_URL": "http://127.0.0.1:9/v1"}, {"CAD_API_URL": "http://127.0.0.1:9/v1", "no_proxy": ""}):
            lost = self.run_hosted(**failing, **extra)
            self.assertEqual((lost.returncode, lost.stdout, lost.stderr), (taken.returncode, taken.stdout, taken.stderr))
        quiet = self.run_hosted(**failing, DO_NOT_TRACK="1")
        self.assertEqual((quiet.returncode, install.NOTICE + "\n" + quiet.stdout, quiet.stderr),
                         (taken.returncode, taken.stdout, taken.stderr))

    def test_a_crash_of_the_script_is_reported_by_its_type_and_its_frames_and_python_ends_it_as_it_would(self) -> None:
        hosted = self.root / "hosted" / "install.py"
        hosted.parent.mkdir()
        shutil.copy(INSTALL / "install.py", hosted)
        # The hosted copy, with uv's answer about its tools raising inside the cad step.
        driver = ("import importlib.util, sys\n"
                  "spec = importlib.util.spec_from_file_location('hosted_install', sys.argv[1])\n"
                  "install = importlib.util.module_from_spec(spec)\n"
                  "sys.modules[spec.name] = install\n"
                  "spec.loader.exec_module(install)\n"
                  "def broken(here, uv):\n"
                  "    raise KeyError('/home/someone/secret.txt')\n"
                  "install.uv_tools = broken\n"
                  "sys.exit(install.main([]))\n")
        done = subprocess.run([sys.executable, "-c", driver, str(hosted)], env=self.reporting(), capture_output=True,
                              text=True, encoding="utf-8", timeout=120)
        # Python's own traceback and exit status, after the report.
        self.assertEqual(1, done.returncode)
        self.assertIn("Traceback (most recent call last):", done.stderr)
        self.assertEqual(done.stderr.strip().splitlines()[-1], "KeyError: '/home/someone/secret.txt'")
        frames = [{"function": name, "line": mock.ANY} for name in ("main", "run", "install_cad")]
        body = self.report("script", 1, type="KeyError", frames=frames)
        self.assertTrue(all(type(frame["line"]) is int and frame["line"] > 0 for frame in body["frames"]))
        # Never a file's name, a path or a message.
        raw = self.receiver.posts[0][2].decode("utf-8")
        for private in ("secret", "someone", "install.py", str(self.root)):
            self.assertNotIn(private, raw)
        # At most ten frames, the innermost; a name the service would not take is not sent.
        def deep(n: int) -> None:
            if n:
                deep(n - 1)
            raise type("Ünïcode", (Exception,), {})("x")

        with mock.patch.object(install, "development", lambda here: False), \
                mock.patch.dict(os.environ, self.reporting(), clear=True):
            del self.receiver.posts[:]
            try:
                deep(14)
            except Exception as error:  # noqa: BLE001 - the crash under test
                with mock.patch.object(install, "__file__", __file__):
                    install.Reports(install.Here()).crashed(error)
        body = self.report("script", 1, type="<?>", frames=[{"function": "deep", "line": mock.ANY}] * 10)

    # --- install.sh ---------------------------------------------------------------------------------------------

    def run_sh(self, **extra: str) -> subprocess.CompletedProcess:
        """install.sh piped to sh, with the checkout's install.py (``CAD_INSTALL_PY``: a development run)."""
        if self.log.exists():
            self.log.unlink()
        return subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True,
                              text=True, env=self.environ(CAD_INSTALL_PY=str(INSTALL / "install.py"),
                                                          PATH=f"{self.bin}:/usr/bin:/bin", **extra), timeout=60)

    def run_sh_hosted(self, path: str = "", **extra: str) -> subprocess.CompletedProcess:
        """install.sh piped to sh as a person runs the hosted one: install.py downloaded (the stand-in curl hands over
        the checkout's), and a failure reported to the stand-in receiver."""
        self.forget_calls()
        del self.receiver.posts[:]
        return subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True,
                              text=True, timeout=120, env=self.reporting(
                                  FAKE_INSTALL_PY=str(INSTALL / "install.py"), PATH=path or f"{self.bin}:/usr/bin:/bin",
                                  **extra))

    def test_install_sh_runs_install_py_with_uv_s_python(self) -> None:
        self.programs("uv")
        script = self.run_sh(FAKE_LOG_ENV="CAD_INSTALL_MARK")
        self.assertEqual(0, script.returncode, script.stderr)
        run = self.logged("uv")[-1]
        self.assertEqual(run["argv"][:-1], ["run", "--no-config", "--managed-python", "--python", "3.14", "--no-project"])
        self.assertEqual(Path(run["argv"][-1]).name, "install.py")
        # Beside it, in the scratch folder that goes with the run: where install.py says it started.
        self.assertEqual(Path(run["env"]["CAD_INSTALL_MARK"]), Path(run["argv"][-1]).with_name("started"))
        self.assertFalse(Path(run["argv"][-1]).parent.exists())
        # Its exit status is install.py's.
        script = self.run_sh(FAKE_FAIL="uv:run", FAKE_EXIT="75")
        self.assertEqual(75, script.returncode)

    def test_install_sh_cut_short_runs_nothing(self) -> None:
        # A download that ends early: everything is inside main, called on the last line.
        lines = (INSTALL / "install.sh").read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertEqual(lines[-1], 'main "$@"\n')
        for kept in (len(lines) - 1, len(lines) * 2 // 3, len(lines) // 3):
            script = subprocess.run(["/bin/sh"], input="".join(lines[:kept]), capture_output=True, text=True,
                                    env=self.reporting(PATH=f"{self.bin}:/usr/bin:/bin"), timeout=60)
            self.assertEqual((self.calls(), self.receiver.posts, script.stdout), ([], [], ""), kept)

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

    def test_install_sh_reports_what_fails_before_install_py_runs_and_nothing_install_py_reported(self) -> None:
        self.programs("uv", "curl")
        # uv: too old, and its installer could not be downloaded. Said first, once, on the stream its lines go to.
        script = self.run_sh_hosted(FAKE_UV_VERSION="0.8.24", FAKE_FAIL="curl:https://astral.sh/uv/install.sh")
        self.assertEqual(1, script.returncode)
        self.assertEqual((script.stderr.splitlines()[0], script.stderr.count(install.NOTICE)), (install.NOTICE, 1))
        self.report("uv", 1, uv="0.8.24")
        # fetch: install.py could not be downloaded.
        script = self.run_sh_hosted(FAKE_FAIL="curl:https://texttocad.dev/install.py")
        self.assertEqual(1, script.returncode)
        self.assertIn("error: could not download https://texttocad.dev/install.py", script.stderr)
        self.report("fetch", 1)
        # python: uv could not run install.py, which left no sign that it started. The run ends as uv did.
        script = self.run_sh_hosted(FAKE_FAIL="uv:run", FAKE_EXIT="2")
        self.assertEqual(2, script.returncode)
        self.report("python", 2)
        # install.py ran, and reported its own failure (cad could not be installed): the script sends no second, and
        # install.py does not say again what the script said.
        script = self.run_sh_hosted(FAKE_UV_RUNS="1", FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_EXIT_UV="1")
        self.assertEqual(1, script.returncode, script.stdout + script.stderr)
        self.assertIn("cad: failed (uv tool install exit status 3", script.stdout)
        self.assertEqual((script.stderr.count(install.NOTICE), script.stdout.count(install.NOTICE)), (1, 0))
        self.report("cad", 3)
        # install.py ran and failed where cad counts it (another run was going): nothing is sent.
        self.tools(cad="0.13.0")
        script = self.run_sh_hosted(FAKE_UV_RUNS="1", FAKE_PLUGIN_EXIT_CAD="75")
        self.assertEqual((75, []), (script.returncode, self.receiver.posts), script.stdout + script.stderr)

    def test_install_sh_sends_and_says_nothing_where_the_person_the_environment_or_the_place_says_no(self) -> None:
        self.programs("uv", "curl")
        failing = {"FAKE_FAIL": "curl:https://texttocad.dev/install.py"}
        settings = self.write(".local/state/cad/settings.json", json.dumps(
            {"plugin": {"auto_update": True}, "telemetry": {"by": "cli", "choice": "off", "decidedAt": 1.5}}, indent=2,
            sort_keys=True))
        elsewhere = self.root / "state" / "settings.json"
        elsewhere.parent.mkdir()
        shutil.copy(settings, elsewhere)
        for off in ({}, {"CAD_STATE_DIR": str(elsewhere.parent), "XDG_STATE_HOME": str(self.root / "none")}):
            with self.subTest(off=off):
                script = self.run_sh_hosted(**failing, **off)
                self.assertEqual((1, [], False),
                                 (script.returncode, self.receiver.posts, install.NOTICE in script.stderr))
        settings.write_text(json.dumps({"telemetry": {"choice": "on", "id": "x"}, "other": {"choice": "off"}}), encoding="utf-8")
        self.run_sh_hosted(**failing)
        self.report("fetch", 1)
        settings.unlink()
        for off in ({"DO_NOT_TRACK": "1"}, {"DO_NOT_TRACK": " True "}, {"DO_NOT_TRACK": "yes"}, {"CAD_TELEMETRY": "0"},
                    {"CAD_TELEMETRY": "OFF"}, {"CAD_TELEMETRY": "no"}, {"CI": "true"}, {"CI": "1"}):
            with self.subTest(off=off):
                script = self.run_sh_hosted(**failing, **off)
                self.assertEqual((1, [], False),
                                 (script.returncode, self.receiver.posts, install.NOTICE in script.stderr))
        # A checkout's run (the rehearsals' hook): uv could not run its install.py, and nothing is sent.
        script = self.run_sh_hosted(FAKE_FAIL="uv:run", CAD_INSTALL_PY=str(INSTALL / "install.py"))
        self.assertEqual((1, [], False), (script.returncode, self.receiver.posts, install.NOTICE in script.stderr))
        for on in ({"DO_NOT_TRACK": "0"}, {"CAD_TELEMETRY": "1"}, {"CI": "false"}, {"CI": ""}):
            with self.subTest(on=on):
                self.run_sh_hosted(**failing, **on)
                self.report("fetch", 1)

    def test_install_sh_says_and_sends_nothing_on_a_run_cad_started_and_leaves_its_report_to_install_py(self) -> None:
        # Its output is a log's or nobody's, and the script cannot tell whether cad told the person: so no line, and
        # no report of its own stages, whatever cad's settings keep. install.py, which reads them, reports from there.
        self.programs("uv", "curl")
        told = {"telemetry": {"notifiedAt": 1763500000.5, "notice": 1}}
        for kept in (None, told):
            if kept is not None:
                self.write(".local/state/cad/settings.json", json.dumps(kept, indent=2, sort_keys=True))
            for by in ({"CAD_INSTALL_BY_CAD": "1"}, {"CAD_INSTALL_ATTEMPT": "1763500000.5"},
                       {"CAD_INSTALL_REPORT": str(self.root / "report.json")}):
                for failing, code in (({"FAKE_UV_VERSION": "0.8.24", "FAKE_FAIL": "curl:https://astral.sh/uv/install.sh"}, 1),
                                      ({"FAKE_FAIL": "curl:https://texttocad.dev/install.py"}, 1),
                                      ({"FAKE_FAIL": "uv:run", "FAKE_EXIT": "2"}, 2)):
                    with self.subTest(kept=kept, by=by, failing=failing):
                        script = self.run_sh_hosted(**failing, **by)
                        self.assertEqual((code, [], False), (script.returncode, self.receiver.posts,
                                                             install.NOTICE in script.stdout + script.stderr))
        # install.py, run by it on a computer cad told: cad could not be installed, reported once, by cad, unsaid.
        script = self.run_sh_hosted(FAKE_UV_RUNS="1", FAKE_FAIL="uv:cad", FAKE_EXIT="3", FAKE_PLUGIN_EXIT_UV="1",
                                    CAD_INSTALL_BY_CAD="1")
        self.assertEqual((1, False), (script.returncode, install.NOTICE in script.stdout + script.stderr))
        self.report("cad", 3, by="cad")

    def test_install_sh_s_report_goes_by_the_real_curl_and_the_real_wget(self) -> None:
        # The command lines themselves, each by the program a person has: install.py cannot be downloaded (every
        # proxy is a closed port), and the report reaches the stand-in receiver, past the proxies, as written.
        needs = ("awk", "cut", "date", "grep", "mktemp", "od", "rm", "sed", "tr", "uname")
        for sender in ("curl", "wget"):
            tools = self.root / f"tools-{sender}"
            tools.mkdir()
            found = {name: shutil.which(name, path="/usr/bin:/bin") for name in (*needs, sender)}
            if not all(found.values()):
                continue  # this system has no such program: the other one is the test
            for name, path in found.items():
                (tools / name).symlink_to(path)
            with self.subTest(sender=sender):
                script = self.run_sh_hosted(path=f"{self.bin}:{tools}")
                self.assertEqual(1, script.returncode, script.stderr)
                self.assertIn("error: could not download https://texttocad.dev/install.py", script.stderr)
                self.report("fetch", 1)
        self.assertTrue(any((self.root / f"tools-{sender}" / sender).exists() for sender in ("curl", "wget")),
                        "neither curl nor wget is here: nothing was tested")

    # --- the checkout's own install, and the scripts' text -----------------------------------------------------------

    def test_the_development_install_puts_the_checkout_in_place_of_the_published_copy(self) -> None:
        self.programs("git")
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
            # install.py hands the apps to the published cad, and leaves cad's own automatic updates as they are:
            # --release turns them on again.
            self.assertEqual(self.calls("cad"), [ASKED, HANDED, AUTO_ON, ["update", "auto", "on"]])
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

    def test_the_three_scripts_say_one_line_and_report_to_one_address_each_its_own_stages(self) -> None:
        # install.ps1 is not runnable here (the Windows install jobs run it): what it shares with the other two is
        # held by its text. One line said first, word for word; the service's one address; a stage per failure.
        address = f"{install.API}/install"
        self.assertEqual(address, "https://api.texttocad.dev/v1/install")
        sh, ps1 = ((INSTALL / name).read_text(encoding="utf-8") for name in ("install.sh", "install.ps1"))
        self.assertIn(f'NOTICE="{install.NOTICE}"\n', sh)
        self.assertIn(f"$Notice = '{install.NOTICE}'\n", ps1)
        self.assertIn(f'REPORT_URL="{address}"\n', sh)
        self.assertIn(f"$ReportUrl = '{address}'\n", ps1)
        self.assertEqual(re.findall(r"Send-Report '(\w+)' (\S+)", ps1),
                         [("uv", "1"), ("uv", "1"), ("uv", "1"), ("fetch", "1"), ("python", "$code")])
        self.assertEqual(re.findall(r"(?m)^\s+(?:stage=(\w+)|report (python) )", sh),
                         [("uv", ""), ("fetch", ""), ("", "python")])
        for name in install.BY_CAD + (install.MARK_ENV, install.API_ENV, "DO_NOT_TRACK", "CAD_TELEMETRY", "CAD_INSTALL_PY"):
            self.assertIn(name, sh, name)
            self.assertIn(name, ps1, name)
        # A run cad started (any of its three variables) says and sends nothing from either shell: the rule that
        # decides both stops there, and what they send is a person's run always.
        self.assertIn('  [ -z "${CAD_INSTALL_BY_CAD:-}${CAD_INSTALL_ATTEMPT:-}${CAD_INSTALL_REPORT:-}" ] || return 1\n',
                      sh.split("may_report() {\n", 1)[1].split("\n}\n", 1)[0])
        self.assertIn("        if ($env:CAD_INSTALL_BY_CAD -or $env:CAD_INSTALL_ATTEMPT -or $env:CAD_INSTALL_REPORT) "
                      "{ return $false }\n", ps1.split("    function Test-Report {\n", 1)[1].split("\n    }\n", 1)[0])
        self.assertEqual((sh.count('"by":"person"'), sh.count('"by":"'), ps1.count("$by = 'person'\n"), ps1.count("$by = ")),
                         (1, 1, 1, 1))

    def test_the_installer_names_no_release_and_no_agent_app(self) -> None:
        # Nothing in the install command changes with a release: no fallback, no pin, nothing a release stamps.
        for name in ("install.sh", "install.ps1", "install.py"):
            text = (INSTALL / name).read_text(encoding="utf-8")
            self.assertNotIn("FALLBACK", text, name)
            self.assertNotRegex(text, r"(cad|cad-server|cad-mcp)==[0-9]", name)
            self.assertNotRegex(text, r"/(releases|versions)\b", f"{name} reads no version feed")
        for name in ("sync-version.mjs", "check-version.sh"):
            self.assertNotIn("install", (REPO_ROOT / "scripts/release" / name).read_text(encoding="utf-8").replace(
                "installers clone", ""), name)
        # cad carries the one table of agent apps, and what the terminal is shown (`cad plugin install`): install.py
        # has neither, names no plugin's source, and runs neither `cad setup` nor `cad plugin update` (but its switch,
        # `cad plugin update auto on`), which on 0.11.12 and 0.11.13 would run this command again.
        text = (INSTALL / "install.py").read_text(encoding="utf-8")
        self.assertEqual([name for name in ("APPS", "App", "install_apps", "Source", "remove_loose_skills", "Screen",
                                            "Logo", "Live", "play_logo") if hasattr(install, name)], [])
        self.assertNotRegex(text, r"(?i)earthtojake|marketplace|\\x1b")
        self.assertEqual(re.findall(r'\[[^\[\]]*"(?:setup|plugin)"[^\[\]]*\]', text),
                         ['[cad.command, "plugin", "install", "--help"]',
                          '[cad.command, "plugin", "install"]',
                          '[uv, "tool", "run", "--no-config", *UV_TOOL_ARGS, "cad@latest", "plugin", "install"]',
                          '[cad.command, "plugin", "update", "auto", "on"]'])


if __name__ == "__main__":
    unittest.main()
