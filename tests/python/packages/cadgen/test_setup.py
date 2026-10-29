"""``cadgen setup`` and ``cadgen update`` (``cadgen.cli.setup``), ``cadgen uninstall``
(``cadgen.cli.uninstall``), and the one-line installer's scripts that run them
(``scripts/install/install.sh``, ``install.ps1``).

The verb runs against a temporary home: its state, cache and ``cadgen`` command folders inside it,
fake app commands on a PATH of their own, Claude Desktop's config file named by
``CLAUDE_DESKTOP_CONFIG``. The engine is never asked: what serves the port, the older engine's
retirement and ``cadgen stop`` are stood in for, as are the doctor's report and the telemetry
choice, so nothing here reaches the network or the developer's own engine and settings. Every run
is at a terminal that would answer no, and asks it nothing.
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

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen import analytics  # noqa: E402
from cadgen import cli, updates  # noqa: E402
from cadgen._internal import diagnostics, installations, providers  # noqa: E402
from cadgen._internal.launch import LAUNCHER  # noqa: E402
from cadgen.cli import setup, stop, telemetry, uninstall  # noqa: E402
from cadgen.engine import client  # noqa: E402

RELEASE = cadgen.__version__
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


# The Skills CLI, for Windsurf: `add` copies every skill into its folder and prints the CLI's JSON,
# `remove` takes the named ones out.
NPX = f"SKILLS = {providers.SKILLS!r}\n" + """
import os, shutil
from pathlib import Path
folder = Path(os.environ["HOME"]) / ".codeium" / "windsurf" / "skills"
assert args[:2] == ["-y", "skills@latest"] and args[args.index("-a") + 1] == "windsurf", args
if args[2] == "add":
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
        environ = {key: value for key, value in os.environ.items()
                   if not key.endswith("_CLI") and key not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "APPDATA",
                                                               "UV_INSTALL_DIR", "XDG_BIN_HOME", "XDG_CONFIG_HOME",
                                                               "HERMES_HOME", "FLATPAK_XDG_CONFIG_HOME")}
        environ.update({"PATH": str(self.bin), "HOME": str(self.home), "USERPROFILE": str(self.home),
                        "CLAUDE_DESKTOP_CONFIG": str(self.desktop)})
        self.machine = providers.Machine(self.home, environ, bundled={})
        for patch in (mock.patch.object(providers.Machine, "here", return_value=self.machine),
                      mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.state),
                                                   "CADGEN_CACHE_DIR": str(self.cache),
                                                   "CADGEN_LAUNCHER_DIR": str(self.launchers)}),
                      mock.patch.object(diagnostics, "engine", side_effect=self.engine),
                      mock.patch.object(diagnostics, "report", side_effect=self.report),
                      mock.patch.object(analytics, "notify", return_value=False),
                      mock.patch.object(telemetry, "describe", return_value="off: your choice"),
                      mock.patch.object(stop, "main", return_value=0)):
            self.addCleanup(patch.stop)
            patch.start()
        self.serving: dict = {"status": "missing"}

    def engine(self, port: int) -> dict:
        return {"port": port, **self.serving}

    def report(self, python, skill, **_options) -> dict:
        """The doctor's report: what Claude Desktop's config now runs, read from the file."""
        sources = []
        if self.desktop.is_file():
            entry = json.loads(self.desktop.read_text(encoding="utf-8")).get("mcpServers", {}).get("cad")
            if entry:
                sources.append({"provider": "claude-desktop", "kind": "config", "status": "ok", "port": PORT,
                                "release": providers.server_pin(entry)})
        return {"status": "ok", "hosts": {"sources": sources}, "engines": [{"port": PORT, "selected": True,
                                                                            "status": "missing"}]}

    def run_setup(self, *argv: str) -> tuple[int, str, str]:
        return self._run(setup.main, argv)

    def run_uninstall(self, *argv: str) -> tuple[int, str, str]:
        return self._run(uninstall.main, argv)

    def _run(self, main, argv: tuple[str, ...]) -> tuple[int, str, str]:
        out, err, terminal = io.StringIO(), io.StringIO(), Terminal("n\n" * 8)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", terminal):
            try:
                code = main([*argv, *(() if "--port" in argv else ("--port", str(PORT)))])
            except SystemExit as exit_:
                code = exit_.code
        self.assertEqual(terminal.tell(), 0, "cadgen read its terminal: it asks nothing")
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

    def entry(self) -> dict:
        return {"command": os.path.abspath(self.machine.which("uvx")),
                "args": [*LAUNCHER[1:], f"cadgen=={RELEASE}", "cadgen", "mcp"],
                "env": {"CADGEN_INSTALL_CHANNEL": "claude-desktop"}}


class TheCommand(Fixture):
    def test_setup_and_update_are_one_command_and_uninstall_a_verb_of_its_own(self) -> None:
        self.assertEqual(cli._COMMANDS["setup"][0], "cadgen.cli.setup")
        self.assertEqual(cli._COMMANDS["update"][0], "cadgen.cli.setup")
        self.assertEqual(cli._COMMANDS["uninstall"][0], "cadgen.cli.uninstall")
        self.assertNotIn("install", cli._COMMANDS)
        self.assertLessEqual({"setup", "update", "uninstall"}, cli._UNTOLD)
        for verb in ("update", "uninstall"):
            out = io.StringIO()
            with self.subTest(verb=verb), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as done:
                cli.main([verb, "--help"])
            self.assertEqual(done.exception.code, 0)
            self.assertIn(f"usage: cadgen {verb}", out.getvalue())

    def test_bad_arguments_exit_2_and_change_nothing(self) -> None:
        for run, argv in ((self.run_setup, ["--purge"]), (self.run_setup, ["--uninstall"]),
                          (self.run_setup, ["--only", "claude,nowhere"]), (self.run_setup, ["--port", "0"]),
                          (self.run_setup, ["--yes"]), (self.run_uninstall, ["--no-telemetry"]),
                          (self.run_uninstall, ["--only", "nowhere"])):
            with self.subTest(verb=run.__name__, argv=argv):
                code, _out, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("error:", err)
        self.assertFalse(self.state.exists())

    def test_a_dry_run_prints_the_plan_and_writes_nothing(self) -> None:
        command(self.bin, "claude", CLAUDE)
        self.desktop_with({"other": {"command": "node", "args": ["server.js"]}})
        (self.home / ".cursor").mkdir()
        before = self.snapshot()
        code, out, _err = self.run_setup("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), before)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"text-to-cad {RELEASE} for this machine (engine port {PORT}):")
        rows = [re.split(r"\s{2,}", line.strip()) for line in lines[1:] if line.startswith("  ") and not line.startswith("    ")]
        self.assertIn(["Claude Code", "remove duplicate", "text-to-cad@earthtojake-dev 0.0.1-dev.1 (a development install)"],
                      rows)
        self.assertIn(["Claude Code", "install", "text-to-cad@earthtojake from earthtojake/text-to-cad at latest"], rows)
        where = providers.shown(self.desktop, self.machine)
        self.assertIn(["Claude Desktop", "install", f"mcpServers.cad in {where}: cadgen {RELEASE}"], rows)
        self.assertIn(["Cursor", "leave", "served by the Claude Code plugin"], rows)
        self.assertIn(["engine", "leave", f"port {PORT}: no engine running; the first CAD view or build starts one"], rows)
        self.assertIn("$ claude plugin install text-to-cad@earthtojake", out)
        self.assertIn("not found here: Codex, Grok Build, Gemini CLI", out)
        self.assertEqual(lines[-1], "Dry run: nothing was changed.")
        calls = [json.loads(line) for line in (self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls, [["claude", "plugin", "list", "--json"], ["claude", "plugin", "marketplace", "list", "--json"]])

    def test_json_is_the_plan_and_what_was_done_and_progress_goes_to_stderr(self) -> None:
        self.desktop_with({})
        code, out, err = self.run_setup("--dry-run", "--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(set(document), {"schema", "plan", "actions", "retired", "verified", "restart"})
        self.assertEqual((document["schema"], document["actions"], document["verified"]), (1, [], None))
        self.assertEqual([(row["app"], row["action"]) for row in document["plan"]],
                         [("claude-desktop", "install"), ("engine", "leave")])
        self.assertEqual(document["plan"][0]["edit"]["set"], {"cad": self.entry()})
        self.assertIn("Dry run", err)
        code, out, _err = self.run_setup("--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual([(action["app"], action["kind"], action["ok"]) for action in document["actions"]],
                         [("claude-desktop", "edit", True)])
        self.assertEqual(document["verified"]["apps"]["claude-desktop"], {"verdict": "ok", "releases": [RELEASE]})
        self.assertEqual(document["verified"]["telemetry"], "off: your choice")
        self.assertEqual(document["restart"], [providers.RESTART["claude-desktop"]])


class InstallUpdateAndUninstall(Fixture):
    def test_an_install_retires_the_older_engine_registers_and_keeps_a_receipt_and_the_next_run_changes_nothing(self) -> None:
        original = self.desktop_with({"other": {"command": "node"}})
        self.serving = {"status": "incompatible", "release": "0.0.1"}
        retire = mock.Mock(return_value={"release": "0.0.1", "pid": 4242, "port": PORT})
        with mock.patch.object(client, "retire_older", retire, create=True), \
                mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        retire.assert_called_once_with(PORT, wait=setup.RETIRE_SECONDS)
        self.assertIn("engine   retired cadgen 0.0.1's engine (pid 4242)", out)
        config = json.loads(self.desktop.read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"], {"other": {"command": "node"}, "cad": self.entry()})
        self.assertEqual(self.desktop.with_name(self.desktop.name + ".bak").read_bytes(), original)
        proxy = Path(installations.proxy_path())
        self.assertEqual(installations.proxy_status(str(proxy)), installations.OK)
        receipt = self.receipt()
        self.assertEqual((receipt["schema"], receipt["release"], receipt["port"]), (1, RELEASE, PORT))
        self.assertEqual([(action["app"], action["action"], action["kind"]) for action in receipt["actions"]],
                         [("claude-desktop", "install", "edit")])
        self.assertEqual([(found["release"], found["pid"]) for found in receipt["retired"]], [("0.0.1", 4242)])
        self.assertEqual(receipt["launcher"]["path"], str(proxy))
        self.assertIn("verify   Claude Desktop: cadgen " + RELEASE, out)
        self.assertIn(providers.RESTART["claude-desktop"], out)
        # Run again: nothing to do, nothing written, nothing asked of the engine.
        self.serving = {"status": "compatible", "release": RELEASE}
        before = self.snapshot()
        with mock.patch.object(client, "retire_older", retire, create=True), \
                mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn(f"text-to-cad {RELEASE} is already up to date here.", out)
        self.assertNotIn("Restart", out)
        self.assertEqual(retire.call_count, 1)
        self.assertEqual({path: found for path, found in self.snapshot().items() if not path.endswith(setup.LOCK)},
                         {path: found for path, found in before.items() if not path.endswith(setup.LOCK)})

    def test_claude_desktop_s_server_is_written_once_and_another_release_s_pin_is_left_alone(self) -> None:
        self.desktop_with({})
        self.assertEqual(self.run_setup()[0], 0)
        floor = {**self.entry(), "args": [*LAUNCHER[1:], "cadgen==0.0.1", "cadgen", "mcp"]}
        written = self.desktop_with({"cad": floor})  # installed by an earlier release: its floor
        code, out, _err = self.run_setup("--dry-run")
        self.assertEqual(code, 0, out)
        where = providers.shown(self.desktop, self.machine)
        self.assertIn(f"Claude Desktop  leave  mcpServers.cad in {where}: there, from cadgen 0.0.1; it runs the "
                      "release this device runs", out)
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.desktop.read_bytes(), written)
        self.assertIn(f"verify   Claude Desktop: cadgen {RELEASE} (its config names 0.0.1, a floor)", out)
        self.assertNotIn("Restart", out, "an update restarts nothing")

    def test_setup_makes_its_release_current_never_a_development_build_nor_an_older_one_unasked(self) -> None:
        pointer = self.state / installations.CURRENT

        def environment(name: str) -> tuple[str, str, str]:
            scripts = self.root / name / "bin"
            scripts.mkdir(parents=True)
            for path in (scripts / "cadgen", scripts / "python"):
                path.write_text("", encoding="utf-8")
            return str(scripts / "cadgen"), str(scripts / "python"), str(self.root / name)

        here = environment("this")
        with mock.patch.object(installations, "targets", return_value=here), \
                mock.patch.dict(os.environ, {installations.NAME_ENV: RELEASE}):
            with mock.patch.object(installations, "development", return_value=True):
                self.assertEqual(self.run_setup()[0], 0)
            self.assertFalse(pointer.exists(), "a development install never points")
            with mock.patch.object(installations, "development", return_value=False):
                code, out, _err = self.run_setup()
                self.assertEqual(code, 0, out)
                self.assertIn(f"current  cadgen {RELEASE}: what every app's next session runs", out)
                self.assertEqual(installations.current()["cadgen"], here[0])
                newer = environment("newer")
                installations.register("99.0.0", newer)
                installations.point("99.0.0", newer)
                code, out, _err = self.run_setup()
                self.assertEqual(code, 0, out)
                self.assertIn(f"current  cadgen 99.0.0, newer than {RELEASE}, left as it is", out)
                self.assertEqual(installations.current()["release"], "99.0.0")
                code, out, _err = self.run_setup("--version", RELEASE)  # the install command asked for it
                self.assertEqual(code, 0, out)
                self.assertEqual(installations.current()["release"], RELEASE)
                self.assertEqual(self.run_setup("--version", "99.0.0")[0], 2, "only this release can be asked for")

    def test_the_verify_line_names_the_engine_on_the_port_this_run_set_up(self) -> None:
        self.serving = {"status": "compatible", "release": RELEASE}
        code, out, _err = self.run_setup("--port", "3399")
        self.assertEqual(code, 0, out)
        self.assertIn(f"verify   engine port 3399: cadgen {RELEASE} running", out)
        self.assertNotIn(f"engine port {PORT}", out)

    def test_an_engine_in_use_is_said_and_the_apps_are_installed(self) -> None:
        self.desktop_with({})
        # An older release met by protocol answers its hello: still an older engine to retire.
        self.serving = {"status": "compatible", "release": "0.0.1"}
        busy = mock.Mock(side_effect=ConnectionError("cadgen 0.0.1's engine on port 3245 is in use by 2 app servers"))
        with mock.patch.object(client, "retire_older", busy, create=True):
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn("engine   cadgen 0.0.1's engine on port 3245 is in use by 2 app servers", out)
        self.assertIn("cad", json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"])
        self.assertNotIn("retired", [key for key, value in self.receipt().items() if value])

    def test_without_retire_older_an_older_protocol_s_engine_is_stopped_through_its_own_door(self) -> None:
        self.serving = {"status": "conflicting_listener"}
        older = {"kind": "engine", "port": PORT, "release": "0.0.1", "pid": 7, "address": "/door",
                 "said": "cadgen 0.0.1's engine (pid 7)"}
        with mock.patch.object(client, "retire_older", None, create=True), \
                mock.patch.object(client, "legacy", return_value=older), \
                mock.patch.object(client, "stop_legacy", return_value=True) as stopped:
            code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn("engine   retire", out)  # the plan said it
        stopped.assert_called_once_with(older, timeout=setup.RETIRE_SECONDS)
        self.assertIn("engine   retired cadgen 0.0.1's engine (pid 7)", out)
        self.assertEqual([found["pid"] for found in self.receipt()["retired"]], [7])

    def test_a_failed_app_exits_1_and_the_other_apps_are_still_done(self) -> None:
        command(self.bin, "gemini", "sys.exit(1 if args[:2] == ['extensions', 'install'] else 0)\n")
        self.desktop_with({})
        code, out, _err = self.run_setup()
        self.assertEqual(code, 1, out)
        self.assertIn("Gemini CLI: install the text-to-cad extension", out)
        self.assertIn("  failed: exit status 1", out)
        self.assertIn(f"run the install command again: {updates.command()}", out)
        self.assertIn("cad", json.loads(self.desktop.read_text(encoding="utf-8"))["mcpServers"])
        self.assertEqual([(action["app"], action["ok"]) for action in self.receipt()["actions"]],
                         [("claude-desktop", True), ("gemini", False)])

    def test_the_receipt_keeps_the_apps_and_the_path_the_self_update_runs_the_next_setup_with(self) -> None:
        # Every run records them, a run that changes nothing else too; the report ends saying so.
        from cadgen._internal import auto_update

        self.desktop_with({})
        code, out, _err = self.run_setup("--only", "claude-desktop")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.receipt()["only"], self.receipt()["path"]), (["claude-desktop"], str(self.bin)))
        self.assertEqual(out.splitlines()[-1], auto_update.said())
        code, out, _err = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertIn("already up to date", out)
        self.assertNotIn("only", self.receipt())
        self.assertEqual(self.receipt()["path"], str(self.bin))

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
        stop.main.assert_called_once_with(["--port", str(PORT)])
        self.cache.mkdir(parents=True, exist_ok=True)
        code, out, _err = self.run_uninstall("--purge")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.cache.exists())

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
        self.assertIn(f"from cadgen {RELEASE}: up to date", out)
        self.assertIn(f"text-to-cad {RELEASE} is already up to date here.", out)
        self.assertEqual((self.bin / "calls.jsonl").read_text(encoding="utf-8"), calls)
        code, out, _err = self.run_uninstall()
        self.assertEqual(code, 0, out)
        last = json.loads((self.bin / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(last, ["npx", "-y", "skills@latest", "remove", "-g", "-a", "windsurf", "-s",
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
        self.assertEqual(rows, ["Windsurf", "engine"])
        star = "*" if os.name == "nt" else "'*'"  # command_text spells it for cmd, else for the shell
        self.assertIn(f"-a windsurf -s {star} -y --copy --json", out)

    def test_no_telemetry_turns_it_off_as_cadgen_telemetry_off_does(self) -> None:
        with mock.patch.object(analytics, "choose", return_value={"saved": True, "sharing": False}) as chosen:
            code, out, _err = self.run_setup("--no-telemetry")
        self.assertEqual(code, 0, out)
        chosen.assert_called_once_with(False, by="cli", forget=analytics.request_deletion)
        self.assertIn("telemetry off: your choice", out)


class TheOneLineInstaller(unittest.TestCase):
    """The scripts texttocad.dev serves, read as text, and the shell one run with fake uvx and curl."""

    def test_install_sh_runs_nothing_before_its_last_line_and_runs_this_release_s_cadgen_setup(self) -> None:
        text = INSTALL_SH.read_text(encoding="utf-8").replace("\r\n", "\n")  # as a Windows checkout may hold it
        self.assertTrue(text.isascii())
        # The command each script says it is run by is the one cadgen tells people to run.
        self.assertIn(updates.INSTALL, text)
        self.assertIn(updates.INSTALL_WINDOWS, text)
        lines = text.splitlines()
        self.assertEqual(lines[-1], 'main "$@"')
        self.assertIn("set -eu", lines[:lines.index("main() {")])
        self.assertEqual(re.findall(r'^CADGEN_VERSION="([^"]*)"$', text, re.M), [VERSION])
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
        self.assertIn(f'exec "$uvx" {launch} $refresh --from "$requirement" cadgen "$verb" "$@"\n', text)
        self.assertIn('refresh="--refresh-package cadgen"', text)
        # One way in, the same at a terminal or not: cadgen asks nothing, so it reads none.
        self.assertEqual(text.count('cadgen "$verb" "$@"'), 1)
        self.assertNotIn("cadgen install", text)
        self.assertNotIn("/dev/tty", text)
        self.assertNotIn("--yes", text)
        sh = shutil.which("sh")
        if sh and os.name != "nt":
            self.assertEqual(subprocess.run([sh, "-n", str(INSTALL_SH)], capture_output=True).returncode, 0)

    def test_install_ps1_runs_nothing_but_its_function_and_runs_this_release_s_cadgen_setup(self) -> None:
        text = INSTALL_PS1.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertTrue(text.isascii())
        self.assertIn(updates.INSTALL_WINDOWS, text)
        self.assertIn(updates.INSTALL, text)
        lines = text.splitlines()
        self.assertEqual(lines[-1], "Install-TextToCad @args")
        body = lines[lines.index("function Install-TextToCad {"):lines.index("Install-TextToCad @args")]
        self.assertEqual(body[-2], "}")
        self.assertTrue(all(line.startswith("#") or not line for line in lines[:lines.index("function Install-TextToCad {")]))
        self.assertEqual(re.findall(r'^\s*\$CadgenVersion = "([^"]*)"$', text, re.M), [VERSION])
        words = ", ".join(f"'{word}'" for word in LAUNCHER[1:-1])
        self.assertIn(f"@({words}) + $refresh + @('--from', $requirement, 'cadgen', $verb) + $rest", text)
        self.assertIn("$verb = 'setup'", text)
        self.assertIn("if ($argument -eq '--uninstall') { $verb = 'uninstall'; continue }", text)
        self.assertNotIn("cadgen install", text)
        self.assertIn("$refresh = @('--refresh-package', 'cadgen')", text)
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
    def test_install_sh_picks_the_release_and_hands_every_other_argument_to_cadgen_setup_or_uninstall(self) -> None:
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

            head = [*LAUNCHER[1:-1], "--refresh-package", "cadgen", "--from"]
            done, given = run("--dry-run", "--only", "claude,codex")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(given, [*head, "cadgen==9.9.9", "cadgen", "setup", "--dry-run", "--only", "claude,codex"])
            self.assertIn("cadgen setup --dry-run --only claude,codex\n", done.stderr)  # the Running: line
            # A release asked for by name is told so: it becomes the one the device runs.
            done, given = run("--version", "1.2.3")
            self.assertEqual(given, [*head, "cadgen==1.2.3", "cadgen", "setup", "--version", "1.2.3"])
            done, given = run("--version", "0.0.1")  # older than the script's own: it knows no --version
            self.assertEqual(given, [*head, "cadgen==0.0.1", "cadgen", "setup"])
            # --uninstall picks the verb, wherever it is given; the rest goes to `cadgen uninstall`.
            done, given = run("--purge", "--uninstall", "--dry-run")
            self.assertEqual(given, [*head, "cadgen==9.9.9", "cadgen", "uninstall", "--purge", "--dry-run"])
            self.assertIn("cadgen uninstall --purge --dry-run\n", done.stderr)
            done, given = run("--version=1.2.4")
            self.assertEqual(given[len(head)], "cadgen==1.2.4")
            done, given = run(feed="")  # the version feed cannot be read: the release the script was published with
            self.assertEqual(given[len(head)], f"cadgen=={VERSION}")
            self.assertIn("the version feed could not be read", done.stderr)
            # The feed lags a release for up to an hour: never a release older than this script's own,
            # which has no `cadgen setup`; a newer one, and this very release, are taken as the feed says.
            done, given = run(feed='{"latest":"0.8.0"}')
            self.assertEqual(given[len(head)], f"cadgen=={VERSION}")
            self.assertIn("the version feed still names 0.8.0", done.stderr)
            done, given = run(feed=f'{{"latest":"{VERSION}"}}')
            self.assertEqual(given[len(head)], f"cadgen=={VERSION}")
            self.assertIn("the newest release", done.stderr)
            # A build named outright, for testing before its release: taken as it is, nothing refreshed.
            plain = [*LAUNCHER[1:-1], "--from"]
            done, given = run("--from", "/builds/cadgen-9.9.9-py3-none-any.whl", "--dry-run")
            self.assertEqual(given, [*plain, "/builds/cadgen-9.9.9-py3-none-any.whl", "cadgen", "setup", "--dry-run"])
            self.assertIn("as --from asked", done.stderr)
            done, given = run("--dry-run", CADGEN_INSTALL_FROM="/builds/cadgen")
            self.assertEqual(given[:len(plain) + 1], [*plain, "/builds/cadgen"])
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
