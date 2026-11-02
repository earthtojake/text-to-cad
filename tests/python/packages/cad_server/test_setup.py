"""``cad setup`` (``cad_server.cli.setup``), ``cad update`` (``cad_server.cli.update``), ``cad
uninstall`` (``cad_server.cli.uninstall``), and the one-line installer's scripts that run them
(``scripts/install/install.sh``, ``install.ps1``).

The verb runs against a temporary home: its state, cache and ``cad`` command folders inside it,
fake app commands on a PATH of their own, Claude Desktop's config file named by
``CLAUDE_DESKTOP_CONFIG``, and a plugin of the test's own that the plugin folder is written from
(``cad_server._internal.plugin``). The engine is never asked: what serves the port, 0.8's ``cadgen stop``,
this release's ``cad stop``, the switch and the plugin folder following it are stood in for, as is the
telemetry choice, so nothing here reaches the network or the developer's own engine, settings and
apps. Every run is at a terminal that would answer no, and asks it nothing.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cad/src")

import cad_server  # noqa: E402
from cad_server import analytics  # noqa: E402
from cad_server import cli, updates  # noqa: E402
from cad_server._internal import installations, plugin, providers, releases, switch  # noqa: E402
from cad_server._internal.launch import LAUNCHER  # noqa: E402
from cad_server.cli import setup, stop, telemetry, uninstall  # noqa: E402

RELEASE = cad_server.__version__
PORT = 3245
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
INSTALL_SH = REPO_ROOT / "scripts" / "install" / "install.sh"
INSTALL_PS1 = REPO_ROOT / "scripts" / "install" / "install.ps1"
POSIX = unittest.skipIf(os.name == "nt", "the shell installer is for macOS and Linux")


def command(folder: Path, name: str, body: str) -> Path:
    """A command ``name`` in ``folder`` that runs ``body`` (Python, with ``args``) by this interpreter
    and logs each call to ``calls.jsonl`` beside it."""
    program = folder / f"{name}.py"
    program.write_text("import json, sys\nargs = sys.argv[1:]\n"
                       f"with open({str(folder / 'calls.jsonl')!r}, 'a', encoding='utf-8') as log:\n"
                       f"    log.write(json.dumps([{name!r}, *args]) + '\\n')\n" + body, encoding="utf-8")
    if os.name == "nt":
        launcher = folder / f"{name}.cmd"
        launcher.write_text(f'@"{sys.executable}" "{program}" %*\r\n', encoding="utf-8")
    else:
        launcher = folder / name
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{program}" "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


# Claude Code with a development install of the plugin, and nothing else, for a plan to show.
CLAUDE = """
if args == ["plugin", "list", "--json"]:
    print(json.dumps([{"id": "text-to-cad@earthtojake-dev", "version": "0.0.1-dev.1", "scope": "user"}]))
elif args == ["plugin", "marketplace", "list", "--json"]:
    print("[]")
else:
    sys.exit(9)
"""

# Claude Code with nothing installed, whose every other command succeeds: the plugin folder it is
# pointed at must be there by then, written.
CLAUDE_EMPTY = """
import os
if args in (["plugin", "list", "--json"], ["plugin", "marketplace", "list", "--json"]):
    print("[]")
elif args[:3] == ["plugin", "marketplace", "add"]:
    sys.exit(0 if os.path.isfile(os.path.join(args[3], ".claude-plugin", "marketplace.json")) else 7)
"""


def plugin_source(root: Path) -> Path:
    """A plugin of the test's own, laid out as the server's wheel carries it: every file the folder is
    written from, and a skill."""
    server = {"mcpServers": {"cad": {"command": "uvx", "args": [*LAUNCHER[1:], "cad-mcp==0.0.1", "cad-mcp"],
                                     "env": {"CAD_INSTALL_CHANNEL": "x"}}}}
    files = {name: b"bytes" for name in plugin.FILES}
    files.update({name: json.dumps({"name": "text-to-cad", "version": "0.0.1"}).encode() for name in plugin.MANIFESTS})
    files.update({name: json.dumps(server).encode() for name in ("claude.mcp.json", "codex.mcp.json", "cursor.mcp.json",
                                                                 "mcp.json")})
    files["gemini-extension.json"] = json.dumps({"name": "text-to-cad", "version": "0.0.1", **server}).encode()
    files[plugin.CATALOG] = json.dumps({"name": "earthtojake", "plugins": [{"name": "text-to-cad", "source": "./"}]}).encode()
    files["skills/cad/SKILL.md"] = b"---\nname: cad\n---\nMaintained at earthtojake/text-to-cad.\n"
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return root


# The Skills CLI, for Windsurf: `add` copies every skill into its folder and prints the CLI's JSON,
# `remove` takes the named ones out.
NPX = f"SKILLS = {providers.SKILLS!r}\n" + """
import os, shutil
from pathlib import Path
folder = Path(os.environ["HOME"]) / ".codeium" / "windsurf" / "skills"
assert args[:3] == ["--prefer-offline", "-y", "skills@latest"] and args[args.index("-a") + 1] == "windsurf", args
args = args[1:]
if args[2] == "add":
    assert os.path.isfile(os.path.join(args[3], "cad", "SKILL.md")), "the skills come from the plugin folder"
    for name in SKILLS:
        (folder / name).mkdir(parents=True, exist_ok=True)
        (folder / name / "SKILL.md").write_text(f"---\\nname: {name}\\n---\\nMaintained at earthtojake/text-to-cad.\\n")
    print(json.dumps([{"name": name, "status": "installed"} for name in SKILLS]))
elif args[2] == "remove":
    for name in args[args.index("-s") + 1:args.index("-y")]:
        shutil.rmtree(folder / name)
"""


class Terminal(io.StringIO):
    """A terminal whose every answer is no: the installer asks nothing, so it reads none of it."""

    def isatty(self) -> bool:
        return True


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = temporary_directory(prefix="install-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        for folder in (self.home, self.bin):
            folder.mkdir()
        self.state, self.cache = self.home / "state", self.home / "cache"
        self.launchers = self.home / "launchers"
        self.desktop = self.home / "Claude" / "claude_desktop_config.json"
        self.uvx = command(self.bin, "uvx", "")
        self.plugin_source = plugin_source(self.root / "plugin-source")
        environ = {key: value for key, value in os.environ.items()
                   if not key.endswith("_CLI") and key not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "APPDATA",
                                                               "UV_INSTALL_DIR", "XDG_BIN_HOME", "XDG_CONFIG_HOME",
                                                               "HERMES_HOME", "FLATPAK_XDG_CONFIG_HOME", "GEMINI_CLI_HOME")}
        environ.update({"PATH": str(self.bin), "HOME": str(self.home), "USERPROFILE": str(self.home),
                        "CLAUDE_DESKTOP_CONFIG": str(self.desktop)})
        self.machine = providers.Machine(self.home, environ, bundled={})
        # The port is the default one, never what the test runner names for its own engines.
        port = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_CACHE_DIR": str(self.cache),
                                            "CAD_LAUNCHER_DIR": str(self.launchers),
                                            "CAD_ENGINE_DEFAULT_PORT": str(PORT)})
        port.start()
        self.addCleanup(port.stop)
        os.environ.pop("CAD_ENGINE_PORT", None)
        for patch in (mock.patch.object(providers.Machine, "here", return_value=self.machine),
                      mock.patch.object(setup, "engine_on", side_effect=lambda port: self.serving),
                      mock.patch.object(setup, "port_held", side_effect=lambda port: self.held),
                      mock.patch.object(setup, "stop_earlier", return_value=(True, [], "")),
                      mock.patch.object(switch, "handover", return_value=None),
                      # The release now current's own `cad plugin --refresh`, a process of its own.
                      mock.patch.object(switch, "follow", return_value=True),
                      mock.patch.object(plugin, "source", return_value=self.plugin_source),
                      mock.patch.object(analytics, "notify", return_value=False),
                      mock.patch.object(telemetry, "describe", return_value="off: your choice"),
                      mock.patch.object(stop, "main", return_value=0)):
            self.addCleanup(patch.stop)
            patch.start()
        self.serving: dict | None = None
        self.held: str | None = None

    def run_setup(self, *argv: str) -> tuple[int, str, str]:
        return self._run(setup.main, argv)

    def run_uninstall(self, *argv: str) -> tuple[int, str, str]:
        return self._run(uninstall.main, argv)

    def _run(self, main, argv: tuple[str, ...]) -> tuple[int, str, str]:
        out, err, terminal = io.StringIO(), io.StringIO(), Terminal("n\n" * 8)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", terminal):
            try:
                code = main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        self.assertEqual(terminal.tell(), 0, "cad read its terminal: it asks nothing")
        return code, out.getvalue(), err.getvalue()

    def snapshot(self) -> dict:
        found = {}
        for path in sorted(self.home.rglob("*")):
            found[path.relative_to(self.home).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "folder", path.stat().st_mtime_ns)
        return found

    def receipt(self) -> dict:
        return json.loads((self.state / setup.RECEIPT).read_text(encoding="utf-8"))

    def desktop_with(self, servers: dict) -> bytes:
        self.desktop.parent.mkdir(parents=True, exist_ok=True)
        self.desktop.write_text(json.dumps({"mcpServers": servers, "preferences": {"keep": True}}, indent=2) + "\n",
                                encoding="utf-8")
        return self.desktop.read_bytes()

    def entry(self, release: str = RELEASE) -> dict:
        return {"command": os.path.abspath(self.machine.which("uvx")),
                "args": [*LAUNCHER[1:], f"cad-mcp=={release}", "cad-mcp"],
                "env": {"CAD_INSTALL_CHANNEL": "claude-desktop"}}

    def earlier_installation(self, version: str = "0.8.4") -> dict:
        """A 0.8 installation, its environment and its record as 0.8 wrote it, in 0.8's own state folder: the
        state folder this test names (``cad.engine.places.earlier_state_dir``)."""
        scripts = self.root / f"env-{version}" / "bin"
        scripts.mkdir(parents=True)
        for path in (scripts / "cadgen", scripts / "python"):
            path.write_text("", encoding="utf-8")
        record = {"version": version, "python": str(scripts / "python"), "cadgen": str(scripts / "cadgen"),
                  "prefix": str(scripts.parent), "registered": "2026-10-30T12:00:00+0000"}
        (self.state / "installations").mkdir(parents=True, exist_ok=True)
        (self.state / "installations" / f"{version}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        return record


class TheCommand(Fixture):
    def test_setup_update_and_uninstall_are_verbs_of_their_own(self) -> None:
        self.assertEqual(cli._COMMANDS["setup"][0], "cad_server.cli.setup")
        self.assertEqual(cli._COMMANDS["update"][0], "cad_server.cli.update")
        self.assertEqual(cli._COMMANDS["uninstall"][0], "cad_server.cli.uninstall")
        self.assertNotIn("install", cli._COMMANDS)
        self.assertLessEqual({"setup", "update", "uninstall"}, cli._UNTOLD)
        for verb in ("update", "uninstall"):
            out = io.StringIO()
            with self.subTest(verb=verb), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as done:
                cli.main([verb, "--help"])
            self.assertEqual(done.exception.code, 0)
            self.assertIn(f"usage: cad {verb}", out.getvalue())

    def test_bad_arguments_exit_2_and_change_nothing(self) -> None:
        for run, argv in ((self.run_setup, ["--purge"]), (self.run_setup, ["--uninstall"]),
                          (self.run_setup, ["--only", "claude,nowhere"]), (self.run_setup, ["--port", "3245"]),
                          (self.run_setup, ["--yes"]), (self.run_uninstall, ["--no-telemetry"]),
                          (self.run_uninstall, ["--only", "nowhere"])):
            with self.subTest(verb=run.__name__, argv=argv):
                code, _out, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("error:", err)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_PORT": "no-port"}):
            code, _out, err = self.run_setup("--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("CAD_ENGINE_PORT='no-port' is not a port", err)
        self.assertFalse(self.state.exists())

    def test_a_dry_run_prints_the_plan_and_writes_nothing(self) -> None:
        command(self.bin, "claude", CLAUDE)
        self.desktop_with({"other": {"command": "node", "args": ["server.js"]}})
        (self.home / ".cursor").mkdir()
        earlier = self.earlier_installation()
        before = self.snapshot()
        code, out, _err = self.run_setup("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), before)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"text-to-cad {RELEASE} for this machine (engine port {PORT}):")
        rows = [re.split(r"\s{2,}", line.strip()) for line in lines[1:] if line.startswith("  ") and not line.startswith("    ")]
        self.assertIn(["Claude Code", "remove duplicate", "text-to-cad@earthtojake-dev 0.0.1-dev.1 (a development install)"],
                      rows)
        folder = providers.shown(plugin.folder(), self.machine)
        self.assertIn(["Claude Code", "install", f"text-to-cad@text-to-cad, which reads {folder} in place"], rows)
        where = providers.shown(self.desktop, self.machine)
        self.assertIn(["Claude Desktop", "install", f"mcpServers.cad in {where}: text-to-cad {RELEASE}"], rows)
        self.assertIn(["Cursor", "leave", "served by the Claude Code plugin"], rows)
        self.assertIn(["plugin folder", "write", f"{folder}: text-to-cad {RELEASE}, which the apps read"], rows)
        self.assertIn(["0.8", "stop", f"text-to-cad 0.8.4's server, if it runs: "
                                      f"`{providers.shown(earlier['cadgen'], self.machine)} stop`"], rows)
        self.assertIn(["engine", "leave", f"port {PORT}: no engine running; the first CAD view or build starts one"], rows)
        self.assertIn("$ claude plugin install text-to-cad@text-to-cad", out)
        self.assertIn("not found here: Codex, Grok Build, Gemini CLI", out)
        self.assertEqual(lines[-1], "Dry run: nothing was changed.")
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls, [["claude", "plugin", "list", "--json"], ["claude", "plugin", "marketplace", "list", "--json"]])
        setup.stop_earlier.assert_not_called()

    def test_json_is_the_plan_and_what_was_done_and_progress_goes_to_stderr(self) -> None:
        self.desktop_with({})
        code, out, err = self.run_setup("--dry-run", "--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(set(document), {"schema", "plan", "actions", "stopped", "verified", "restart"})
        self.assertEqual((document["schema"], document["actions"], document["verified"]), (1, [], None))
        self.assertEqual([(row["app"], row["action"]) for row in document["plan"]],
                         [("claude-desktop", "install"), ("plugin", "write"), ("engine", "leave")])
        self.assertEqual(document["plan"][0]["edit"]["set"], {"cad": self.entry()})
        self.assertIn("Dry run", err)
        code, out, _err = self.run_setup("--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual([(action["app"], action["kind"], action["ok"]) for action in document["actions"]],
                         [("plugin", "plugin", True), ("claude-desktop", "edit", True)])
        self.assertEqual(document["verified"]["apps"]["claude-desktop"], {"verdict": "ok", "release": RELEASE})
        self.assertEqual(document["verified"]["telemetry"], "off: your choice")
        self.assertEqual(document["restart"], [providers.RESTART["claude-desktop"]])


class InstallUpdateAndUninstall(Fixture):
    def test_an_install_stops_0_8_s_server_by_its_own_stop_registers_keeps_a_receipt_and_the_next_run_changes_nothing(self) -> None:
        original = self.desktop_with({"other": {"command": "node"}})
        earlier = self.earlier_installation()
        self.held = "another cad-server (python3.14, pid 4242)"  # 0.8's server on the port, as the system names it
        stopped = ["/tmp/cadgen-engine/0123456789ab.door"]
        # Its own `cadgen stop` stops it: the port is free after.
        setup.stop_earlier.side_effect = lambda record: (setattr(self, "held", None), (True, stopped, ""))[1]
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        (call,) = setup.stop_earlier.call_args_list
        self.assertEqual(call.args[0]["cadgen"], earlier["cadgen"], "stopped by 0.8's own cadgen stop")
        console = re.escape(providers.shown(earlier["cadgen"], self.machine))
        self.assertRegex(out, rf"\n  0\.8 +stop +text-to-cad 0\.8\.4's server, if it runs: `{console} stop`\n")
        self.assertIn(f"port {PORT} is held by another cad-server (python3.14, pid 4242): if 0.8's stop above does "
                      "not free it, the engine serves on the next free port, and says so", out)
        self.assertIn("0.8      stopped text-to-cad 0.8.4's server (its own `cadgen stop`)", out)
        config = json.loads(self.desktop.read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"], {"other": {"command": "node"}, "cad": self.entry()})
        self.assertEqual(self.desktop.with_name(self.desktop.name + ".bak").read_bytes(), original)
        proxy = Path(installations.proxy_path())
        self.assertEqual(installations.proxy_status(str(proxy)), installations.OK)
        receipt = self.receipt()
        self.assertEqual((receipt["schema"], receipt["release"]), (1, RELEASE))
        self.assertEqual([(action["app"], action["action"], action["kind"]) for action in receipt["actions"]],
                         [("plugin", "write", "plugin"), ("claude-desktop", "install", "edit")])
        self.assertEqual([(found["release"], found["servers"]) for found in receipt["stopped"]], [("0.8.4", stopped)])
        self.assertEqual(receipt["launcher"]["path"], str(proxy))
        self.assertIn("verify   Claude Desktop: text-to-cad " + RELEASE, out)
        self.assertIn(f"verify   engine port {PORT}: not running; the next CAD session starts one", out)
        self.assertIn(providers.RESTART["claude-desktop"], out)
        # Run again: nothing to do and nothing written; 0.8's own stop runs again, and stops nothing.
        setup.stop_earlier.side_effect = None
        before = self.snapshot()
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn("0.8      text-to-cad 0.8.4's server was not running", out)
        self.assertIn(f"text-to-cad {RELEASE} is already up to date here.", out)
        self.assertIn(f"verify   engine port {PORT}: not running; the next CAD session starts one", out)
        self.assertNotIn("Restart", out)
        self.assertEqual(setup.stop_earlier.call_count, 2)
        self.assertEqual({path: found for path, found in self.snapshot().items() if not path.endswith(setup.LOCK)},
                         {path: found for path, found in before.items() if not path.endswith(setup.LOCK)})

    def test_claude_desktop_s_server_moves_to_this_release_and_a_newer_one_is_left_alone(self) -> None:
        older = {**self.entry("0.0.1"), "env": {"CAD_INSTALL_CHANNEL": "claude-desktop", "CAD_ENGINE_PORT": "4000"}}
        self.desktop_with({"cad": older})
        where = providers.shown(self.desktop, self.machine)
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, rf"Claude Desktop +update +mcpServers\.cad in {re.escape(where)}: text-to-cad 0\.0\.1 -> {RELEASE}")
        # The pin is what uvx runs: it moves to this release, and the environment someone added stays.
        cad = json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"]["cad"]
        self.assertEqual(cad, {**self.entry(), "env": older["env"]})
        self.assertIn(providers.RESTART["claude-desktop"], out)
        written = self.desktop_with({"cad": self.entry("99.0.0")})
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn(f"mcpServers.cad in {where}: text-to-cad 99.0.0, newer than {RELEASE}, left alone", out)
        self.assertEqual(self.desktop.read_bytes(), written)

    def test_a_0_8_stop_that_fails_is_said_and_the_apps_are_installed(self) -> None:
        self.desktop_with({})
        self.earlier_installation()
        gone = self.earlier_installation("0.8.3")
        os.remove(gone["cadgen"])  # uv's cache cleaned of it: nothing of 0.8.3 is left to run
        setup.stop_earlier.return_value = (False, None, "Traceback (most recent call last):\nOSError: no")
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertEqual([call.args[0]["version"] for call in setup.stop_earlier.call_args_list], ["0.8.4"])
        self.assertIn("0.8      text-to-cad 0.8.4's `cadgen stop` failed: OSError: no; its server may still run", out)
        self.assertNotIn("0.8.3", out)
        self.assertIn("cad", json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"])
        self.assertEqual(self.receipt()["stopped"], [])

    def test_another_program_on_the_port_is_said_with_what_the_engine_does(self) -> None:
        self.held = "node (pid 77)"
        code, out, _err = self.run_setup("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"port {PORT} is held by node (pid 77): the engine serves on the next free port, and says so", out)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_PORT": "3300"}):
            code, out, _err = self.run_setup("--dry-run")
        self.assertIn("port 3300 is held by node (pid 77): stop it, or set another CAD_ENGINE_PORT", out)
        setup.stop_earlier.assert_not_called()

    def test_the_device_s_engine_is_switched_whatever_its_release(self) -> None:
        """Nothing compares versions: the device's engine moves to this release at the switch, a later
        release's as an earlier one's."""
        for version, prefix in (("99.0.0", "/newer"), ("0.0.1", str(self.root / "older"))):
            self.serving = {"ok": True, "pid": 9, "version": version, "installation": version, "prefix": prefix,
                            "serving": {"port": PORT}}
            code, out, _err = self.run_setup("--dry-run")
            self.assertEqual(code, 0, out)
            self.assertRegex(out, rf"engine +switch +text-to-cad {re.escape(version)}'s engine \(pid 9\) on port {PORT}: "
                                  rf"drains, then text-to-cad {re.escape(RELEASE)}'s takes its place")
        setup.stop_earlier.assert_not_called()

    def test_the_switch_comes_last_and_says_what_it_did(self) -> None:
        self.desktop_with({})
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            switch.handover.return_value = {"from": "0.0.1", "to": RELEASE, "ok": True, "gapMs": 412}
            code, out, _err = self.run_setup()
            self.assertEqual(code, 0, out)
            switch.handover.assert_called_once_with(RELEASE, told=mock.ANY)
            self.assertIn(f"engine   text-to-cad {RELEASE} is the current installation (412 ms without an engine)", out)
            self.assertLess(out.index("Claude Desktop: install"), out.index("is the current installation"),
                            "the apps first, then the switch")
            switch.follow.assert_not_called()
            switch.handover.return_value = {"from": "0.0.1", "to": RELEASE, "ok": False, "error": "no hello",
                                            "restored": True}
            code, out, _err = self.run_setup()
        self.assertEqual(code, 1, out)
        self.assertIn(f"engine   the switch to text-to-cad {RELEASE} failed: no hello; the release before runs again", out)
        # The release before's plugin folder, and the apps' copies of it, come back with it.
        switch.follow.assert_called_once_with(told=mock.ANY)

    def test_a_release_sets_itself_up_from_its_own_folder(self) -> None:
        """Run from uvx's environment (the install command), a release makes its folder in the state
        folder and runs the same command from there, with the person's PATH: uvx's environment, which
        uvx puts first on PATH and uv's cache keeps (its uvx and its `cad`), is not theirs. A dry run only
        plans it."""
        made = {"cad": str(self.root / "release-bin" / "cad")}
        cached = self.root / "uv" / "archive-v0" / "M-XQ" / "bin"
        with mock.patch.object(installations, "editable", return_value=False), \
                mock.patch.dict(os.environ, {installations.NAME_ENV: "",
                                             "PATH": os.pathsep.join((str(cached), str(self.bin)))}), \
                mock.patch.object(releases, "make", return_value=made) as make, \
                mock.patch.object(setup.os, "execve", side_effect=SystemExit(0)) as execve, \
                mock.patch("subprocess.call", return_value=0) as call:
            code, out, _err = self.run_setup("--dry-run")
            self.assertEqual(code, 0, out)
            where = providers.shown(str(releases.where(RELEASE)), self.machine)
            self.assertRegex(out, rf"\n  release\s+make\s+text-to-cad {re.escape(RELEASE)} in {re.escape(where)}, once\n")
            make.assert_not_called()
            code, out, _err = self.run_setup("--only", "claude")
        self.assertEqual(code, 0, out)
        make.assert_called_once_with(RELEASE, source=mock.ANY, told=mock.ANY)
        run = [made["cad"], "setup", "--only", "claude"]
        if os.name == "nt":
            call.assert_called_once_with(run, env=mock.ANY)
            environment = call.call_args.kwargs["env"]
        else:
            execve.assert_called_once_with(made["cad"], run, mock.ANY)
            environment = execve.call_args.args[2]
        self.assertEqual(environment["PATH"], str(self.bin))
        self.assertEqual(environment["CAD_STATE_DIR"], str(self.state), "the rest of the environment goes along")

    def test_the_engine_s_own_run_says_its_stages_on_stdout_and_switches_nothing(self) -> None:
        command(self.bin, "gemini", "sys.exit(1 if args[:2] == ['extensions', 'link'] else 0)\n")
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, err = self.run_setup("--engine-update")
        self.assertEqual(code, 0, err + out)  # an app's failure is said, and the engine still moves on
        frames = [json.loads(line)["progress"] for line in out.splitlines()]
        self.assertEqual([(frame["kind"], frame["stage"]) for frame in frames], [("update", "apps")])
        self.assertIn("Gemini CLI: install the text-to-cad extension", err)
        switch.handover.assert_not_called()

    def test_the_cad_kernel_environment_is_planned_and_made_once(self) -> None:
        from cad_server._internal import base

        core = base.Installation(**{**base.dataclasses.asdict(base.Installation.here()), "kernel": False})
        made: dict = {}

        def ensure(installation=None, *, make=True, told=None):
            if make and "env" not in made:
                told("making the CAD kernel environment, once: cad[build123d] in the cache folder")
                made["env"] = base.Environment("/base/bin/python", "/base", False, ("/base",))
            return made.get("env")

        where = providers.shown(str(base.where(core)), self.machine)
        with mock.patch.object(base.Installation, "here", return_value=core), \
                mock.patch.object(base, "ensure", side_effect=ensure):
            planned = self.run_setup("--dry-run")
            first = self.run_setup()
            again = self.run_setup()
        self.assertEqual(planned[0], 0)
        self.assertRegex(planned[1], rf"\n  build123d\s+make\s+cad\[build123d\] {re.escape(core.release)} in "
                                     rf"{re.escape(where)}, once\n")
        self.assertNotIn("making", planned[1], "a dry run makes nothing")
        self.assertEqual(first[0], 0, first[1])
        self.assertIn("build123d making the CAD kernel environment, once: cad[build123d] in the cache folder\n", first[1])
        self.assertEqual(again[0], 0)
        self.assertNotIn("making", again[1])
        self.assertRegex(again[1], r"build123d\s+leave\s+cad\[build123d\] ")

    def test_a_failed_app_exits_1_and_the_other_apps_are_still_done(self) -> None:
        command(self.bin, "gemini", "sys.exit(1 if args[:2] == ['extensions', 'link'] else 0)\n")
        self.desktop_with({})
        code, out, _err = self.run_setup()
        self.assertEqual(code, 1, out)
        self.assertIn("Gemini CLI: install the text-to-cad extension", out)
        self.assertIn("  failed: exit status 1", out)
        self.assertIn(f"run the install command again: {updates.command()}", out)
        self.assertIn("cad", json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"])
        self.assertEqual([(action["app"], action["ok"]) for action in self.receipt()["actions"]],
                         [("plugin", True), ("claude-desktop", True), ("gemini", False)])

    def test_the_plugin_folder_is_written_before_an_app_is_pointed_at_it_and_goes_with_an_uninstall(self) -> None:
        command(self.bin, "claude", CLAUDE_EMPTY)
        folder = plugin.folder()
        code, out, _err = self.run_setup("--only", "claude")
        self.assertEqual(code, 0, out)
        self.assertLess(out.index(f"plugin   wrote {providers.shown(folder, self.machine)}: text-to-cad {RELEASE}"),
                        out.index("Claude Code: install"))
        manifest = json.loads((folder / plugin.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], RELEASE, "this release's, whatever the plugin it was written from says")
        self.assertEqual((folder / "skills" / "cad" / "SKILL.md").read_bytes(),
                         (self.plugin_source / "skills" / "cad" / "SKILL.md").read_bytes())
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn(["claude", "plugin", "marketplace", "add", str(folder)], calls)
        self.assertIn(["claude", "plugin", "install", "text-to-cad@text-to-cad"], calls)
        # Run again: the folder already this release's, nothing written.
        before = (folder / plugin.MANIFEST).stat().st_mtime_ns
        self.assertEqual(self.run_setup("--only", "claude")[0], 0)
        self.assertEqual((folder / plugin.MANIFEST).stat().st_mtime_ns, before)
        code, out, _err = self.run_uninstall()
        self.assertEqual(code, 0, out)
        self.assertIn(f"plugin   removed {providers.shown(folder, self.machine)}", out)
        self.assertFalse(folder.exists())

    def test_a_folder_that_cannot_be_written_points_no_app_at_it(self) -> None:
        command(self.bin, "claude", CLAUDE_EMPTY)
        self.desktop_with({})
        with mock.patch.object(plugin, "source", side_effect=plugin.Missing("no plugin in this installation")):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 1, out)
        self.assertIn("could not be written: no plugin in this installation", out)
        self.assertIn("Claude Code: install text-to-cad@text-to-cad", out)
        self.assertIn("not done, with no plugin folder", out)
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertFalse([call for call in calls if call[1:3] == ["plugin", "marketplace"] and call[3] == "add"])
        self.assertIn("cad", json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"], "Claude Desktop needs none")

    def test_uninstall_takes_back_what_the_receipt_says_and_purge_removes_the_folders(self) -> None:
        original = self.desktop_with({"other": {"command": "node"}})
        with mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            self.assertEqual(self.run_setup()[0], 0)
        proxy = Path(installations.proxy_path())
        self.assertTrue(proxy.is_file())
        code, out, _err = self.run_uninstall("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Claude Desktop  remove", out)
        self.assertTrue(proxy.is_file())
        code, out, _err = self.run_uninstall()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.desktop.read_bytes(), original)
        self.assertFalse(proxy.exists())
        self.assertFalse((self.state / setup.RECEIPT).exists())
        stop.main.assert_called_once_with([])
        self.cache.mkdir(parents=True, exist_ok=True)
        # The release folders go with an uninstall, with their records and the current one.
        folder = releases.where(RELEASE)
        (folder / "bin").mkdir(parents=True)
        for name in ("cad", "python"):
            (folder / "bin" / name).write_text("", encoding="utf-8")
        installations.register(RELEASE, (str(folder / "bin" / "cad"), str(folder / "bin" / "python"), str(folder)))
        installations.point(RELEASE)
        code, out, _err = self.run_uninstall()
        self.assertEqual(code, 0, out)
        self.assertFalse(releases.root().exists())
        self.assertIn("releases removed", out)
        self.assertEqual((installations.records(), installations.current_version()), ([], None))
        code, out, _err = self.run_uninstall("--purge")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.cache.exists())

    def test_purge_leaves_a_folder_of_the_same_name_that_another_program_keeps(self) -> None:
        for folder in (self.state, self.cache):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "theirs.db").write_text("theirs", encoding="utf-8")
        code, out, _err = self.run_uninstall("--purge")
        self.assertEqual(code, 0, out)
        for folder in (self.state, self.cache):
            self.assertEqual([entry.name for entry in folder.iterdir()], ["theirs.db"], folder)
        self.assertEqual(out.count("it holds nothing text-to-cad made"), 2, out)

    def test_an_agent_without_a_plugin_gets_the_skills_once_per_release_and_uninstall_takes_them_back(self) -> None:
        command(self.bin, "npx", NPX)
        folder = self.home / ".codeium" / "windsurf" / "skills"
        folder.parent.mkdir(parents=True)
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertEqual(providers.ours_in(folder), [folder / name for name in providers.SKILLS])
        got = self.receipt()["skills"]["windsurf"]
        self.assertEqual((got["release"], got["skills"]), (RELEASE, list(providers.SKILLS)))
        self.assertIn("Windsurf: start a new session for the skills", out)
        # The receipt's release is this one and every skill is there: nothing to do.
        calls = (self.bin / "calls.jsonl").read_text(encoding="utf-8")
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn(f"from text-to-cad {RELEASE}: up to date", out)
        self.assertIn(f"text-to-cad {RELEASE} is already up to date here.", out)
        self.assertEqual((self.bin / "calls.jsonl").read_text(encoding="utf-8"), calls)
        code, out, _err = self.run_uninstall()
        self.assertEqual(code, 0, out)
        last = json.loads((self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(last, ["npx", "--prefer-offline", "-y", "skills@latest", "remove", "-g", "-a", "windsurf", "-s",
                                *sorted(providers.SKILLS), "-y"])
        self.assertEqual(providers.ours_in(folder), [])

    def test_only_takes_a_skills_cli_agent(self) -> None:
        command(self.bin, "npx", NPX)
        for mark in (".codeium/windsurf", ".config/goose"):
            (self.home / mark).mkdir(parents=True)
        self.desktop_with({})
        code, out, _err = self.run_setup("--dry-run", "--only", "windsurf")
        self.assertEqual(code, 0, out)
        rows = [line.split()[0] for line in out.splitlines() if line.startswith("  ") and not line.startswith("    ")]
        self.assertEqual(rows, ["Windsurf", "plugin", "engine"])
        star = "*" if os.name == "nt" else "'*'"  # command_text spells it for cmd, else for the shell
        self.assertIn(f"-a windsurf -s {star} -y --copy --json", out)

    def test_no_telemetry_turns_it_off_as_cad_telemetry_off_does(self) -> None:
        with mock.patch.object(analytics, "choose", return_value={"saved": True, "sharing": False}) as chosen:
            code, out, _err = self.run_setup("--no-telemetry")
        self.assertEqual(code, 0, out)
        chosen.assert_called_once_with(False, by="cli", forget=analytics.request_deletion)
        self.assertIn("telemetry off: your choice", out)


class ThePluginCommand(Fixture):
    """``cad plugin``: the folder written from the current installation, its path printed; ``--refresh``,
    which a switch runs, brings the apps' copies of it along when that changed it."""

    def test_it_writes_the_folder_from_the_current_installation_and_prints_its_path(self) -> None:
        from cad_server.cli import plugin as plugin_cli

        folder = plugin.folder()
        code, out, err = self._run(plugin_cli.main, ())  # no installation current: this one writes it
        self.assertEqual((code, out), (0, f"{folder}\n"), err)
        self.assertEqual(json.loads((folder / plugin.MANIFEST).read_text(encoding="utf-8"))["version"], RELEASE)
        with mock.patch.object(installations, "current", return_value={"version": "9.9.9", "prefix": "/elsewhere"}), \
                mock.patch.object(installations, "mine", return_value=False), mock.patch.object(plugin, "write") as write:
            code, out, err = self._run(plugin_cli.main, ())
        self.assertEqual((code, out), (0, f"{folder}\n"))
        write.assert_not_called()
        self.assertIn("text-to-cad 9.9.9 is the current installation: its `cad plugin` writes the folder", err)

    def test_refresh_adds_codex_s_copy_again_only_when_the_folder_changed(self) -> None:
        from cad_server.cli import plugin as plugin_cli

        folder = plugin.folder()
        command(self.bin, "codex", "print('codex-cli 0.153.4') if args == ['--version'] else None\n")
        codex = self.home / ".codex"
        (codex / "plugins" / "cache" / "text-to-cad" / "text-to-cad" / "0.0.1").mkdir(parents=True)
        (codex / "config.toml").write_text(f'[marketplaces.text-to-cad]\nsource_type = "local"\nsource = {json.dumps(str(folder))}\n'
                                           '[plugins."text-to-cad@text-to-cad"]\nenabled = true\n', encoding="utf-8")
        code, out, err = self._run(plugin_cli.main, ("--refresh",))
        self.assertEqual(code, 0, err)
        self.assertIn("Codex: update text-to-cad@text-to-cad 0.0.1 -> " + RELEASE, err)
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn(["codex", "plugin", "add", "text-to-cad@text-to-cad"], calls)
        self.assertEqual([action["app"] for action in self.receipt()["actions"]], ["codex"])
        count = len(calls)
        code, out, err = self._run(plugin_cli.main, ("--refresh", "--json"))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["refreshed"], None, "the folder did not change: nothing to bring along")
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([call for call in calls[count:] if call != ["codex", "--version"]], [])

    def test_refresh_brings_claude_desktop_s_server_back_with_a_switch_that_went_back(self) -> None:
        # A newer release's setup moved the folder and Claude Desktop's server to it, and its engine never
        # started: the release left current writes the folder again, and the server goes back with it.
        from cad_server.cli import plugin as plugin_cli

        before = self.desktop_with({})
        self.assertEqual(self.run_setup()[0], 0)
        backup = self.desktop.with_name(self.desktop.name + ".bak")
        self.assertEqual(backup.read_bytes(), before)
        config = json.loads(self.desktop.read_text(encoding="utf-8"))
        config["mcpServers"]["cad"] = self.entry("99.0.0")
        self.desktop.write_text(json.dumps(config), encoding="utf-8")
        manifest = plugin.folder() / plugin.MANIFEST
        manifest.write_text(json.dumps({"name": "text-to-cad", "version": "99.0.0"}), encoding="utf-8")
        code, _out, err = self._run(plugin_cli.main, ("--refresh",))
        self.assertEqual(code, 0, err)
        self.assertIn(f"Claude Desktop: update mcpServers.cad in {providers.shown(self.desktop, self.machine)}: "
                      f"text-to-cad 99.0.0 -> {RELEASE}", err)
        self.assertEqual(json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"]["cad"], self.entry())
        self.assertEqual(backup.read_bytes(), before, "the first .bak, which an uninstall restores, is kept")
        self.assertEqual(self.receipt()["actions"][-1]["app"], "claude-desktop")


class ZeroEightsOwnStop(unittest.TestCase):
    def test_it_runs_0_8_s_cadgen_stop_in_0_8_s_own_environment_with_telemetry_off(self) -> None:
        record = {"version": "0.8.4", "cadgen": "/env/bin/cadgen", "python": "/env/bin/python", "prefix": "/env"}
        answer = json.dumps({"ok": True, "stopped": ["/t/cadgen-engine/0123456789ab.door"]}, indent=2) + "\n"
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, answer, "")) as ran, \
                mock.patch.dict(os.environ, {"PYTHONPATH": "/a/checkout/src", "CADGEN_TELEMETRY": "1"}):
            self.assertEqual(setup.stop_earlier(record), (True, ["/t/cadgen-engine/0123456789ab.door"], answer.strip()))
        (call,) = ran.call_args_list
        self.assertEqual(call.args[0], ["/env/bin/cadgen", "stop", "--json"])
        # It runs on the person's behalf, its words read by no one: it counts, sends and tells nothing, so it
        # never takes a notice nobody read for a yes; and it imports its own release, never this one.
        self.assertEqual(call.kwargs["env"]["CADGEN_TELEMETRY"], "0")
        self.assertNotIn("PYTHONPATH", call.kwargs["env"])
        for done, expected in ((subprocess.CompletedProcess([], 0, '{"ok": true, "stopped": []}\n', ""), (True, [])),
                               (subprocess.CompletedProcess([], 0, "no engine server is running\n", ""), (True, None)),
                               (subprocess.CompletedProcess([], 1, "", "boom\n"), (False, None))):
            with mock.patch.object(subprocess, "run", return_value=done):
                self.assertEqual(setup.stop_earlier(record)[:2], expected, done)
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError(2, "No such file or directory")):
            self.assertEqual(setup.stop_earlier(record)[:2], (False, None))


class TheOneLineInstaller(unittest.TestCase):
    """The scripts texttocad.dev serves, read as text, and the shell one run with fake uvx and curl."""

    def test_install_sh_runs_nothing_before_its_last_line_and_runs_this_release_s_cad_setup(self) -> None:
        text = INSTALL_SH.read_text(encoding="utf-8").replace("\r\n", "\n")  # as a Windows checkout may hold it
        self.assertTrue(text.isascii())
        # The command each script says it is run by is the one the server tells people to run.
        self.assertIn(updates.INSTALL, text)
        self.assertIn(updates.INSTALL_WINDOWS, text)
        lines = text.splitlines()
        self.assertEqual(lines[-1], 'main "$@"')
        self.assertIn("set -eu", lines[:lines.index("main() {")])
        self.assertEqual(re.findall(r'^CAD_VERSION="([^"]*)"$', text, re.M), [VERSION])
        # Outside a function, only comments, settings and definitions: a download cut short runs nothing.
        heredoc, depth = None, 0
        for line in lines[:-1]:
            if heredoc:
                heredoc = None if line == heredoc else heredoc
                continue
            if depth == 0:
                self.assertRegex(line, r'^(#.*|set -eu|[A-Z_]+="[^"$`]*"|[a-z_]+\(\) \{|)$')
            depth += line.endswith("{") - (line.strip() == "}")
            opened = re.search(r"<<'?(\w+)'?$", line)
            heredoc = opened.group(1) if opened else None
        self.assertEqual(depth, 0)
        launch = " ".join(LAUNCHER[1:-1])
        self.assertIn(f'exec "$uvx" {launch} $refresh --from "$requirement" cad "$verb" "$@"\n', text)
        self.assertIn('requirement="cad-server==$version"', text)
        self.assertIn('refresh="--refresh-package cad-server --refresh-package cad"', text)
        # One way in, the same at a terminal or not: cad asks nothing, so it reads none.
        self.assertEqual(text.count('cad "$verb" "$@"'), 1)
        self.assertNotIn("cad install", text)
        self.assertNotIn("/dev/tty", text)
        self.assertNotIn("--yes", text)
        sh = shutil.which("sh")
        if sh and os.name != "nt":
            self.assertEqual(subprocess.run([sh, "-n", str(INSTALL_SH)], capture_output=True).returncode, 0)

    def test_install_ps1_runs_nothing_but_its_function_and_runs_this_release_s_cad_setup(self) -> None:
        text = INSTALL_PS1.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertTrue(text.isascii())
        self.assertIn(updates.INSTALL_WINDOWS, text)
        self.assertIn(updates.INSTALL, text)
        lines = text.splitlines()
        self.assertEqual(lines[-1], "Install-TextToCad @args")
        body = lines[lines.index("function Install-TextToCad {"):lines.index("Install-TextToCad @args")]
        self.assertEqual(body[-2], "}")
        self.assertTrue(all(line.startswith("#") or not line for line in lines[:lines.index("function Install-TextToCad {")]))
        self.assertEqual(re.findall(r'^\s*\$CadVersion = "([^"]*)"$', text, re.M), [VERSION])
        words = ", ".join(f"'{word}'" for word in LAUNCHER[1:-1])
        self.assertIn(f"@({words}) + $refresh + @('--from', $requirement, 'cad', $verb) + $rest", text)
        self.assertIn('$requirement = "cad-server==$version"', text)
        self.assertIn("$verb = 'setup'", text)
        self.assertIn("if ($argument -eq '--uninstall') { $verb = 'uninstall'; continue }", text)
        self.assertNotIn("cad install", text)
        self.assertIn("$refresh = @('--refresh-package', 'cad-server', '--refresh-package', 'cad')", text)
        self.assertNotIn("--yes", text)
        pwsh = shutil.which("pwsh")
        if pwsh:
            # Parsed, never run: the path is inside the command (after -Command, an argument is more command).
            path = str(INSTALL_PS1).replace("'", "''")
            parse = (f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, "
                     "[ref]$errors) | Out-Null; if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 }")
            done = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", parse],
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    @POSIX
    def test_install_sh_picks_the_release_and_hands_every_other_argument_to_cad_setup_or_uninstall(self) -> None:
        with temporary_directory(prefix="install-sh-") as scratch:
            root = Path(scratch)
            fakes = root / "bin"
            fakes.mkdir()
            (fakes / "uvx").write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$FAKE_ARGS"\n', encoding="utf-8")
            (fakes / "curl").write_text('#!/bin/sh\n[ -n "$FEED" ] || exit 7\nprintf \'%s\' "$FEED"\n', encoding="utf-8")
            for fake in fakes.iterdir():
                fake.chmod(0o755)
            arguments = root / "arguments"

            def run(*argv: str, feed: str = '{"latest":"9.9.9"}', **extra: str) -> tuple[subprocess.CompletedProcess, list[str]]:
                arguments.unlink(missing_ok=True)
                environment = {"PATH": f"{fakes}:/usr/bin:/bin", "HOME": str(root), "FAKE_ARGS": str(arguments),
                               "FEED": feed, **extra}
                done = subprocess.run(["/bin/sh", str(INSTALL_SH), *argv], env=environment, capture_output=True,
                                      text=True, stdin=subprocess.DEVNULL)
                given = arguments.read_text(encoding="utf-8").splitlines() if arguments.exists() else []
                return done, given

            head = [*LAUNCHER[1:-1], "--refresh-package", "cad-server", "--refresh-package", "cad", "--from"]
            done, given = run("--dry-run", "--only", "claude,codex")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(given, [*head, "cad-server==9.9.9", "cad", "setup", "--dry-run", "--only", "claude,codex"])
            self.assertIn("cad setup --dry-run --only claude,codex\n", done.stderr)  # the Running: line
            # A release asked for by name is the one installed; the device runs its newest release.
            done, given = run("--version", "1.2.3")
            self.assertEqual(given, [*head, "cad-server==1.2.3", "cad", "setup"])
            done, given = run("--version", "0.0.1")  # older than the script's own, taken as asked
            self.assertEqual(given, [*head, "cad-server==0.0.1", "cad", "setup"])
            # --uninstall picks the verb, wherever it is given; the rest goes to `cad uninstall`.
            done, given = run("--purge", "--uninstall", "--dry-run")
            self.assertEqual(given, [*head, "cad-server==9.9.9", "cad", "uninstall", "--purge", "--dry-run"])
            self.assertIn("cad uninstall --purge --dry-run\n", done.stderr)
            done, given = run("--version=1.2.4")
            self.assertEqual(given[len(head)], "cad-server==1.2.4")
            done, given = run(feed="")  # the version feed cannot be read: the release the script was published with
            self.assertEqual(given[len(head)], f"cad-server=={VERSION}")
            self.assertIn("the version feed could not be read", done.stderr)
            # The feed lags a release for up to an hour: never a release older than this script's own,
            # which has no `cad setup`; a newer one, and this very release, are taken as the feed says.
            done, given = run(feed='{"latest":"0.8.0"}')
            self.assertEqual(given[len(head)], f"cad-server=={VERSION}")
            self.assertIn("the version feed still names 0.8.0", done.stderr)
            done, given = run(feed=f'{{"latest":"{VERSION}"}}')
            self.assertEqual(given[len(head)], f"cad-server=={VERSION}")
            self.assertIn("the newest release", done.stderr)
            # A build named outright, for testing before its release: taken as it is, nothing refreshed.
            plain = [*LAUNCHER[1:-1], "--from"]
            done, given = run("--from", "/builds/cad_server-9.9.9-py3-none-any.whl", "--dry-run")
            self.assertEqual(given, [*plain, "/builds/cad_server-9.9.9-py3-none-any.whl", "cad", "setup", "--dry-run"])
            self.assertIn("as --from asked", done.stderr)
            done, given = run("--dry-run", CAD_INSTALL_FROM="/builds/cad-server")
            self.assertEqual(given[:len(plain) + 1], [*plain, "/builds/cad-server"])
            done, given = run("--from")
            self.assertEqual((done.returncode, given), (1, []))
            for argv in (("--version", "1.2.3;true"), ("--version",)):
                done, given = run(*argv)
                self.assertEqual((done.returncode, given), (1, []), argv)
            done, given = run("--help")
            self.assertEqual((done.returncode, given), (0, []))
            self.assertIn(f"releases/download/v{VERSION}/install.sh", done.stdout)


if __name__ == "__main__":
    unittest.main()
