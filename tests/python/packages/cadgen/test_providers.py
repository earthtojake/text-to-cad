"""The agent apps ``cadgen install`` reads and changes (``cadgen._internal.providers``).

Every test builds a temporary home, and puts on a temporary PATH fake ``claude``, ``codex``,
``gemini``, ``grok``, ``git`` and ``npx`` commands: one small emulator (``EMULATOR``) that records each call
and keeps each app's state the way the app does -- Claude Code's and Grok Build's behind their
``--json`` listings, Codex's in ``config.toml`` and its cache, Gemini CLI's and Cursor's in their
folders -- so a plan is applied, read back and taken out again. Nothing here runs a real app or
touches the developer's home.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal import providers  # noqa: E402

RELEASE = "1.2.3"

# One program behind every fake command: `python EMULATOR <tool> ARGS...`. Its world is a JSON file
# (FAKE_WORLD): the release the `latest` branch holds, the commands told to fail, and the state the
# apps keep behind their commands; every call is logged beside it, one JSON line each.
EMULATOR = r'''
import json, os, shutil, sys
from pathlib import Path

tool, args = sys.argv[1], sys.argv[2:]
world_file = Path(os.environ["FAKE_WORLD"])
world = json.loads(world_file.read_text(encoding="utf-8"))
home = Path(os.environ["FAKE_HOME"])
with open(world_file.with_name("calls.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps([tool, *args]) + "\n")
said = " ".join([tool, *args])
for prefix, code in world.get("fail", {}).items():
    if said.startswith(prefix):
        print(tool + ": failed, as the test asked", file=sys.stderr)
        sys.exit(code)
release = world["release"]


def done():
    world_file.write_text(json.dumps(world), encoding="utf-8")
    sys.exit(0)


def refuse(why):
    print(tool + ": " + why, file=sys.stderr)
    sys.exit(1)


def toml(state):
    lines = []
    for table in ("marketplaces", "plugins", "mcp_servers"):
        for name, entry in state.get(table, {}).items():
            lines.append("[%s.%s]" % (table, json.dumps(name)))
            lines += ["%s = %s" % (key, json.dumps(value)) for key, value in entry.items()]
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plugin_folder(path, version, branch):
    (path / ".cursor-plugin").mkdir(parents=True, exist_ok=True)
    (path / ".cursor-plugin" / "plugin.json").write_text(json.dumps({"name": "text-to-cad", "version": version}),
                                                         encoding="utf-8")
    (path / ".git").mkdir(exist_ok=True)
    (path / ".git" / "HEAD").write_text("ref: refs/heads/%s\n" % branch, encoding="utf-8")
    (path / ".git" / "config").write_text('[remote "origin"]\n\turl = https://github.com/earthtojake/text-to-cad\n',
                                          encoding="utf-8")


if tool == "claude":
    state = world.setdefault("claude", {"plugins": [], "marketplaces": []})
    plugins, markets = state["plugins"], state["marketplaces"]
    if args == ["plugin", "list", "--json"]:
        print(json.dumps(plugins))
        sys.exit(0)
    if args == ["plugin", "marketplace", "list", "--json"]:
        print(json.dumps(markets))
        sys.exit(0)
    if args[:3] == ["plugin", "marketplace", "add"]:
        repo, _, ref = args[3].partition("#")
        if any(market["name"] == "earthtojake" for market in markets):
            refuse("its source doesn't match its extraKnownMarketplaces entry")
        markets.append({"name": "earthtojake", "source": "github", "repo": repo, **({"ref": ref} if ref else {})})
        done()
    if args[:3] == ["plugin", "marketplace", "remove"]:
        state["marketplaces"] = [market for market in markets if market["name"] != args[3]]
        state["plugins"] = [plugin for plugin in plugins if not plugin["id"].endswith("@" + args[3])]
        done()
    if args[:3] == ["plugin", "marketplace", "update"]:
        done()
    if args[:2] == ["plugin", "install"]:
        if not any(args[2].endswith("@" + market["name"]) for market in markets):
            refuse("no such marketplace")
        plugins.append({"id": args[2], "version": release, "scope": "user", "enabled": True})
        done()
    if args[:2] == ["plugin", "update"]:
        for plugin in plugins:
            if plugin["id"] == args[2]:
                plugin["version"] = release
        done()
    if args[:2] == ["plugin", "uninstall"]:
        if not any(plugin["id"] == args[2] for plugin in plugins):
            refuse("not installed")
        state["plugins"] = [plugin for plugin in plugins if plugin["id"] != args[2]]
        done()
    if args[:4] == ["mcp", "remove", "--scope", "user"]:
        config = home / ".claude.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data["mcpServers"].pop(args[4])
        config.write_text(json.dumps(data), encoding="utf-8")
        done()
elif tool == "codex":
    state = world.setdefault("codex", {})
    if args == ["--version"]:
        print("codex-cli " + world.get("codex_version", "0.153.4"))
        sys.exit(0)
    markets, plugins = state.setdefault("marketplaces", {}), state.setdefault("plugins", {})
    cache = home / ".codex" / "plugins" / "cache"
    if args[:3] == ["plugin", "marketplace", "add"]:
        if "earthtojake" in markets:
            refuse("a marketplace named earthtojake exists")
        markets["earthtojake"] = {"source_type": "git", "source": "https://github.com/%s.git" % args[3]}
        if "--ref" in args:
            markets["earthtojake"]["ref"] = args[args.index("--ref") + 1]
    elif args[:3] == ["plugin", "marketplace", "upgrade"]:
        pass
    elif args[:3] == ["plugin", "marketplace", "remove"]:
        markets.pop(args[3], None)
    elif args[:2] == ["plugin", "add"]:
        plugins[args[2]] = {"enabled": True}
        folder = cache / args[2].split("@")[1] / "text-to-cad"
        shutil.rmtree(folder, ignore_errors=True)
        (folder / release).mkdir(parents=True)
    elif args[:2] == ["plugin", "remove"]:
        plugins.pop(args[2], None)
        shutil.rmtree(cache / args[2].split("@")[1], ignore_errors=True)
    elif args[:2] == ["mcp", "remove"]:
        state.get("mcp_servers", {}).pop(args[2], None)
    else:
        refuse("unknown command " + said)
    toml(state)
    done()
elif tool == "gemini":
    folder = home / ".gemini" / "extensions" / "text-to-cad"
    if args[:2] == ["extensions", "install"]:
        if folder.exists():
            refuse("already installed")
        folder.mkdir(parents=True)
        (folder / "gemini-extension.json").write_text(json.dumps({"name": "text-to-cad", "version": release}),
                                                      encoding="utf-8")
        (folder / ".gemini-extension-install.json").write_text(json.dumps(
            {"source": args[2], "type": "git", "ref": args[args.index("--ref") + 1], "autoUpdate": True}),
            encoding="utf-8")
        done()
    if args == ["extensions", "update", "text-to-cad"]:
        manifest = json.loads((folder / "gemini-extension.json").read_text(encoding="utf-8"))
        manifest["version"] = release
        (folder / "gemini-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
        done()
    if args == ["extensions", "uninstall", "text-to-cad"]:
        shutil.rmtree(folder)
        done()
elif tool == "grok":
    state = world.setdefault("grok", {"plugins": []})
    registry = home / ".grok" / "installed-plugins" / "registry.json"
    if args == ["plugin", "list", "--json"]:
        print(json.dumps(state["plugins"]))
        sys.exit(0)
    if args[:2] == ["plugin", "install"]:
        repo, _, ref = args[2].partition("@")
        path = str(home / ".grok" / "installed-plugins" / "text-to-cad-1")
        state["plugins"].append({"status": "installed", "name": "text-to-cad", "version": release, "path": path,
                                 "source": "https://github.com/" + repo, "marketplace": None})
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"version": 1, "repos": {"text-to-cad-1": {
            "kind": {"type": "Git", "url": "https://github.com/" + repo, "git_ref": ref}, "path": path}}}),
            encoding="utf-8")
        done()
    if args[:2] in (["plugin", "enable"], ["plugin", "update"]):
        for plugin in state["plugins"]:
            plugin["version"] = release
        done()
    if args[:2] == ["plugin", "uninstall"]:
        state["plugins"] = [plugin for plugin in state["plugins"] if plugin["name"] != args[2]]
        done()
elif tool == "git":
    if args[0] == "clone":
        plugin_folder(Path(args[-1]), release, args[args.index("--branch") + 1])
        done()
    if args[0] == "-C" and args[2:3] == ["pull"]:
        plugin_folder(Path(args[1]), release, "latest")
        done()
elif tool == "npx" and args[:2] == ["-y", "skills@latest"]:
    # The Skills CLI: `add` copies every skill into each named agent's folder, `remove` takes them out.
    agents = [args[index + 1] for index, word in enumerate(args) if word == "-a"]
    folders = world["skills_folders"]
    if args[2] == "add":
        for agent in agents:
            for name in world["skills"]:
                skill = Path(folders[agent]) / name
                skill.mkdir(parents=True, exist_ok=True)
                (skill / "SKILL.md").write_text("---\nname: %s\n---\nMaintained at earthtojake/text-to-cad.\n" % name,
                                                encoding="utf-8")
        print(json.dumps([{"name": name, "status": "installed", "agents": agents} for name in world["skills"]]))
        done()
    if args[2] == "remove":
        for agent in agents:
            for name in args[args.index("-s") + 1:args.index("-y")]:
                shutil.rmtree(Path(folders[agent]) / name, ignore_errors=True)
        done()
refuse("unknown command " + said)
'''


class Home:
    """A temporary home, its fake commands on a PATH of their own, and the world they share."""

    def __init__(self, root: Path, tools: tuple[str, ...] = (), release: str = RELEASE) -> None:
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.bin = root / "bin"
        self.bin.mkdir()
        self.world = root / "world.json"
        self.calls_file = root / "calls.jsonl"
        self.write_world({"release": release})
        (self.bin / "emulator.py").write_text(EMULATOR, encoding="utf-8")
        for tool in tools:
            self.tool(tool)
        environ = {key: value for key, value in os.environ.items()
                   if not key.endswith("_CLI") and key not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLAUDE_DESKTOP_CONFIG",
                                                               "APPDATA", "UV_INSTALL_DIR", "XDG_BIN_HOME", "XDG_CONFIG_HOME",
                                                               "HERMES_HOME", "FLATPAK_XDG_CONFIG_HOME")}
        environ.update({"PATH": str(self.bin), "HOME": str(self.home), "USERPROFILE": str(self.home),
                        "FAKE_WORLD": str(self.world), "FAKE_HOME": str(self.home),
                        "CLAUDE_DESKTOP_CONFIG": str(self.desktop)})
        self.machine = providers.Machine(self.home, environ, bundled={})
        self.set(skills=list(providers.SKILLS), skills_folders={
            agent: str(providers.skills_folder(agent, self.machine)) for agent in providers.SKILLS_AGENTS})

    @property
    def desktop(self) -> Path:
        return self.home / "desktop" / "claude_desktop_config.json"

    def tool(self, name: str, folder: Path | None = None) -> Path:
        """A command ``name`` that runs the emulator."""
        folder = folder or self.bin
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            launcher = folder / f"{name}.cmd"
            launcher.write_text(f'@"{sys.executable}" "{self.bin / "emulator.py"}" {name} %*\r\n', encoding="utf-8")
        else:
            launcher = folder / name
            launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.bin / "emulator.py"}" {name} "$@"\n',
                                encoding="utf-8")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        return launcher

    def read_world(self) -> dict:
        return json.loads(self.world.read_text(encoding="utf-8"))

    def write_world(self, world: dict) -> None:
        self.world.write_text(json.dumps(world), encoding="utf-8")

    def set(self, **changes) -> None:
        self.write_world({**self.read_world(), **changes})

    def calls(self) -> list[list[str]]:
        if not self.calls_file.is_file():
            return []
        return [json.loads(line) for line in self.calls_file.read_text(encoding="utf-8").splitlines()]

    def changing_calls(self) -> list[list[str]]:
        """Every call but a listing or a version question."""
        return [call for call in self.calls() if call[1:] not in (["plugin", "list", "--json"], ["--version"],
                                                                  ["plugin", "marketplace", "list", "--json"])]

    def detect(self) -> dict:
        return providers.detect(self.machine)

    def plan(self, **options) -> list:
        return providers.plan(self.detect(), release=options.pop("release", RELEASE), machine=self.machine,
                              desktop_entry=options.pop("desktop_entry", ENTRY), **options)

    def apply(self, steps: list, **options) -> list:
        records = []
        for step in steps:
            if step.changes:
                ok, done = providers.apply(step, self.machine, aside=self.root / "aside", **options)
                self.assertion(ok, step, done)
                records += done
        return records

    def assertion(self, ok: bool, step, done: list) -> None:
        if not ok:
            raise AssertionError(f"{step.label} {step.action} failed: {done}")

    def skill(self, folder: Path, name: str = "cad", ours: bool = True) -> Path:
        skill = folder / name
        skill.mkdir(parents=True)
        provenance = providers.PROVENANCE if ours else "someone/else"
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\nMaintained at {provenance}.\n", encoding="utf-8")
        return skill


ENTRY = {"command": "/bin/uvx", "args": ["--no-config", "--managed-python", "--python", "3.13", "--from",
                                          f"cadgen=={RELEASE}", "cadgen", "mcp"],
         "env": {"CADGEN_INSTALL_CHANNEL": "claude-desktop"}}


def actions(steps: list) -> list[tuple[str, str]]:
    return [(step.app, step.action) for step in steps]


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = temporary_directory(prefix="providers-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()

    def make(self, tools: tuple[str, ...] = (), **options) -> Home:
        return Home(self.root, tools, **options)


class DetectionAndPlan(Fixture):
    def test_a_home_with_no_app_has_nothing_to_do(self) -> None:
        home = self.make()
        apps = home.detect()
        self.assertEqual([name for name, app in apps.items() if app.present], [])
        self.assertEqual(home.plan(), [])

    def test_every_app_found_gets_its_own_command_and_claude_desktop_its_server(self) -> None:
        home = self.make(("claude", "codex", "gemini", "grok", "git"))
        home.desktop.parent.mkdir(parents=True)
        (home.home / ".cursor").mkdir()
        steps = home.plan(only=["claude-desktop", "codex", "cursor", "grok", "gemini"])
        self.assertEqual(actions(steps), [("claude-desktop", "install"), ("codex", "install"), ("cursor", "install"),
                                          ("grok", "install"), ("gemini", "install")])
        commands = {step.app: [argv[1:] for argv in step.commands] for step in steps}
        self.assertEqual(commands["codex"], [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                             ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(commands["gemini"], [["extensions", "install", "https://github.com/earthtojake/text-to-cad", "--ref",
                                               "latest", "--consent", "--auto-update"]])
        self.assertEqual(commands["grok"], [["plugin", "install", "earthtojake/text-to-cad@latest", "--trust"],
                                            ["plugin", "enable", "text-to-cad"]])
        self.assertEqual(commands["cursor"][0][:5], ["clone", "--depth", "1", "--branch", "latest"])
        self.assertEqual(steps[0].edit, {"op": "servers", "path": str(home.desktop), "set": {"cad": ENTRY}, "remove": []})
        # Claude Code's plugin feeds Cursor and Grok Build: with it in the plan, theirs are not added.
        steps = home.plan()
        self.assertEqual(actions(steps)[:2], [("claude", "install"), ("claude-desktop", "install")])
        self.assertEqual([argv[1:] for argv in steps[0].commands],
                         [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                          ["plugin", "install", "text-to-cad@earthtojake"]])
        served = [step.subject for step in steps if step.app in ("cursor", "grok")]
        self.assertEqual(served, ["served by the Claude Code plugin"] * 2)

    def test_second_copies_are_found_and_removed_and_store_copies_left(self) -> None:
        home = self.make(("claude", "codex", "grok"))
        home.set(claude={"plugins": [{"id": "text-to-cad@earthtojake-dev", "version": "1.2.3-dev.1", "scope": "user"},
                                     {"id": "text-to-cad@earthtojake", "version": "1.2.2", "scope": "project"}],
                         "marketplaces": []},
                 grok={"plugins": [{"name": "text-to-cad", "version": RELEASE, "path": "/x", "source": "/checkout"}]})
        # Codex: the app directory's copy, and a server someone added by hand.
        (home.home / ".codex").mkdir()
        (home.home / ".codex" / "config.toml").write_text(
            '[plugins."text-to-cad@openai-curated"]\nenabled = true\n'
            '[mcp_servers.cad]\ncommand = "uvx"\nargs = ["--from", "cadgen==1.0.0", "cadgen", "mcp"]\n', encoding="utf-8")
        cursor_dev = home.home / ".cursor" / "plugins" / "local" / "text-to-cad-dev"
        (cursor_dev / ".cursor-plugin").mkdir(parents=True)
        (cursor_dev / ".cursor-plugin" / "plugin.json").write_text('{"name": "text-to-cad"}', encoding="utf-8")
        (cursor_dev / providers.DEV_MARK).write_text("checkout\n", encoding="utf-8")
        store = home.home / ".cursor" / "plugins" / "cache" / "earthtojake" / "text-to-cad"
        store.mkdir(parents=True)
        loose = home.skill(home.home / ".claude" / "skills")
        home.skill(home.home / ".claude" / "skills", "theirs", ours=False)
        apps = home.detect()
        self.assertEqual([(copy.name, copy.ours, copy.store, copy.removable) for copy in apps["codex"].copies],
                         [("text-to-cad@openai-curated", False, True, True), ("cad", False, False, True)])
        steps = home.plan()
        by_app = {}
        for step in steps:
            by_app.setdefault(step.app, []).append((step.action, step.subject))
        self.assertIn(("remove duplicate", "text-to-cad@earthtojake-dev 1.2.3-dev.1 (a development install)"),
                      by_app["claude"])
        self.assertIn(("remove duplicate", f"loose skill {providers.shown(loose, home.machine)} (installed loose)"),
                      by_app["claude"])
        self.assertTrue(any(action == "leave" and "another scope's" in subject for action, subject in by_app["claude"]))
        # A store's copy is reported, never removed, and nothing of ours is added beside it.
        self.assertEqual([action for action, _subject in by_app["codex"]], ["leave", "remove duplicate"])
        self.assertIn("a store's copy", by_app["codex"][0][1])
        # Cursor and Grok Build are served by Claude Code's plugin: their own copies go, the store's stays.
        self.assertEqual([action for action, _subject in by_app["cursor"]],
                         ["leave", "remove duplicate", "leave"])
        self.assertIn("remove one of them in Cursor", by_app["cursor"][2][1])
        self.assertEqual(by_app["grok"], [("leave", "served by the Claude Code plugin"),
                                          ("remove duplicate", "text-to-cad 1.2.3 (from /checkout)")])

    def test_a_catalog_on_another_branch_is_pointed_at_latest(self) -> None:
        home = self.make(("claude", "codex"))
        home.set(claude={"plugins": [{"id": "text-to-cad@earthtojake", "version": "1.2.2", "scope": "user"}],
                         "marketplaces": [{"name": "earthtojake", "source": "github", "repo": "earthtojake/text-to-cad"}]})
        steps = home.plan(only=["claude"])
        self.assertEqual(actions(steps), [("claude", "update")])
        self.assertEqual([argv[1:] for argv in steps[0].commands],
                         [["plugin", "marketplace", "remove", "earthtojake"],
                          ["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                          ["plugin", "install", "text-to-cad@earthtojake"]])
        # On latest, an older copy is updated in place, and the release's own is left.
        home.set(claude={"plugins": [{"id": "text-to-cad@earthtojake", "version": "1.2.2", "scope": "user"}],
                         "marketplaces": [{"name": "earthtojake", "repo": "earthtojake/text-to-cad", "ref": "latest"}]})
        self.assertEqual([argv[1:] for argv in home.plan(only=["claude"])[0].commands],
                         [["plugin", "marketplace", "update", "earthtojake"], ["plugin", "update", "text-to-cad@earthtojake"]])
        self.assertEqual(actions(home.plan(only=["claude"], release="1.2.2")), [("claude", "leave")])

    def test_the_newer_of_the_codex_on_path_and_the_app_s_own_installs(self) -> None:
        # Both write the one ~/.codex the app reads, so the newer command does: here the app's.
        home = self.make(("codex",))
        app = self.root / "app"
        app.mkdir()
        bundled = app / ("codex.cmd" if os.name == "nt" else "codex")
        bundled.write_text("@echo codex-cli 0.200.0\r\n" if os.name == "nt" else "#!/bin/sh\necho codex-cli 0.200.0\n",
                           encoding="utf-8")
        bundled.chmod(bundled.stat().st_mode | stat.S_IXUSR)
        home.machine.bundled = {"codex": [str(bundled)]}
        self.assertEqual(providers.codex_cli(home.machine), str(bundled))
        home.set(codex_version="0.300.0")
        self.assertEqual(providers.codex_cli(home.machine), home.machine.which("codex"))
        self.assertEqual(home.detect()["codex"].command, home.machine.which("codex"))


class ApplyReadBackAndTakeBack(Fixture):
    def test_an_install_applied_is_up_to_date_on_the_next_run_and_its_receipt_takes_it_back(self) -> None:
        home = self.make(("claude", "codex", "gemini", "git"))
        original = {"mcpServers": {"cad-dev": {"command": "/venv/bin/python", "args": ["-m", "cadgen.cli", "mcp"]},
                                   "other": {"command": "node", "args": ["server.js"]}}, "preferences": {"x": 1}}
        home.desktop.parent.mkdir(parents=True)
        home.desktop.write_text(json.dumps(original, indent=1) + "\n", encoding="utf-8")
        before = home.desktop.read_bytes()
        (home.home / ".cursor").mkdir()
        steps = home.plan(only=["claude", "claude-desktop", "codex", "gemini"])
        self.assertEqual(actions(steps), [("claude", "install"), ("claude-desktop", "remove duplicate"),
                                          ("claude-desktop", "install"), ("codex", "install"), ("gemini", "install")])
        records = home.apply(steps, backed_up=set())
        # Claude Desktop: one write, ours set and the development server taken out, the rest as it was.
        config = json.loads(home.desktop.read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"], {"other": original["mcpServers"]["other"], "cad": ENTRY})
        self.assertEqual(config["preferences"], {"x": 1})
        self.assertEqual(home.desktop.with_name(home.desktop.name + ".bak").read_bytes(), before)
        # The next run finds every copy current and changes nothing.
        calls = len(home.calls())
        self.assertEqual({step.action for step in home.plan(only=["claude", "claude-desktop", "codex", "gemini"])},
                         {"leave"})
        self.assertEqual([call for call in home.calls()[calls:] if call in home.changing_calls()], [])
        # The receipt's replay takes back what was done, newest first: Claude Desktop's file restored
        # whole from its .bak, each plugin and the catalogs it added removed.
        undo = providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine)
        self.assertEqual(actions(undo), [("gemini", "remove"), ("codex", "remove"), ("claude-desktop", "remove"),
                                         ("claude", "remove")])
        home.apply(undo)
        self.assertEqual(home.desktop.read_bytes(), before)
        apps = home.detect()
        self.assertEqual([copy.name for name in ("claude", "codex", "gemini") for copy in apps[name].copies], [])
        self.assertEqual(apps["claude"].marketplaces, {})
        self.assertNotIn("earthtojake", apps["codex"].marketplaces)

    def test_a_config_changed_since_loses_only_our_server(self) -> None:
        home = self.make()
        home.desktop.parent.mkdir(parents=True)
        home.desktop.write_text('{"mcpServers": {}}', encoding="utf-8")
        (step,) = home.plan()
        records = home.apply([step], backed_up=set())
        config = json.loads(home.desktop.read_text(encoding="utf-8"))
        config["mcpServers"]["mine"] = {"command": "node"}
        home.desktop.write_text(json.dumps(config), encoding="utf-8")
        home.apply(providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine))
        self.assertEqual(json.loads(home.desktop.read_text(encoding="utf-8")), {"mcpServers": {"mine": {"command": "node"}}})
        # A file the installer made goes whole.
        home.desktop.unlink()
        records = home.apply(home.plan(), backed_up=set())
        self.assertTrue(records[0]["created"])
        home.apply(providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine))
        self.assertFalse(home.desktop.exists())

    def test_a_config_that_is_not_plain_json_is_never_rewritten(self) -> None:
        home = self.make()
        home.desktop.parent.mkdir(parents=True)
        home.desktop.write_text('{\n  // a comment\n  "mcpServers": {}\n}\n', encoding="utf-8")
        before = home.desktop.read_bytes()
        (step,) = home.plan()
        self.assertEqual(step.action, "leave")
        self.assertIn("not plain JSON", step.subject)
        with self.assertRaises(ValueError):
            providers.edit_servers(home.desktop, set_entries={"cad": ENTRY})
        self.assertEqual(home.desktop.read_bytes(), before)

    def test_without_claude_code_cursor_and_grok_get_their_own_and_their_updates(self) -> None:
        home = self.make(("grok", "git"))
        (home.home / ".cursor").mkdir()
        steps = home.plan()
        self.assertEqual(actions(steps), [("cursor", "install"), ("grok", "install")])
        records = home.apply(steps)
        self.assertEqual({step.action for step in home.plan()}, {"leave"})
        home.set(release="1.2.4")
        steps = home.plan(release="1.2.4")
        self.assertEqual([(step.app, step.action, [argv[1:] for argv in step.commands]) for step in steps],
                         [("cursor", "update", [["-C", str(home.home / ".cursor" / "plugins" / "local" / "text-to-cad"),
                                                 "pull", "--ff-only"]]),
                          ("grok", "update", [["plugin", "update", "text-to-cad"]])])
        home.apply(steps)
        undo = providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine)
        self.assertEqual(actions(undo), [("grok", "remove"), ("cursor", "remove")])
        home.apply(undo)
        self.assertEqual(home.detect()["cursor"].copies, [])

    def test_a_failed_command_stops_its_step_and_says_why(self) -> None:
        home = self.make(("claude",))
        home.set(fail={"claude plugin install": 3})
        (step,) = home.plan(only=["claude"])
        said = []
        ok, records = providers.apply(step, home.machine, say=said.append)
        self.assertFalse(ok)
        self.assertEqual([(record["command"][1:3], record["code"], record["ok"]) for record in records],
                         [(["plugin", "marketplace"], 0, True), (["plugin", "install"], 3, False)])
        self.assertIn("failed, as the test asked", records[-1]["output"])
        self.assertEqual(said[-1], "failed: exit status 3")

    def test_loose_skills_are_moved_aside_and_an_uninstall_with_no_receipt_removes_what_it_finds(self) -> None:
        home = self.make(("gemini",))
        skill = home.skill(home.home / ".gemini" / "skills")
        (step,) = [step for step in home.plan() if step.action == "remove duplicate"]
        ok, (record,) = providers.apply(step, home.machine, aside=self.root / "aside")
        self.assertTrue(ok)
        self.assertFalse(skill.exists())
        self.assertTrue((Path(record["to"]) / "SKILL.md").is_file())
        home.apply(home.plan())
        undo = providers.uninstall_plan(home.detect(), None, machine=home.machine)
        self.assertEqual([(step.app, step.action) for step in undo], [("gemini", "remove")])


class SkillsForAgentsWithoutAPlugin(Fixture):
    """The agents the Skills CLI knows and no plugin reaches: the skills, by one ``npx skills add``."""

    def agents(self, home: Home, *names: str) -> None:
        marks = {"windsurf": ".codeium/windsurf", "goose": ".config/goose", "cline": ".cline"}
        for name in names:
            (home.home / marks[name]).mkdir(parents=True)

    def test_the_skills_are_this_repository_s(self) -> None:
        self.assertEqual(list(providers.SKILLS),
                         sorted(path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")))

    def test_installed_agents_get_the_skills_in_one_command_and_the_plugin_apps_never(self) -> None:
        home = self.make(("claude", "codex", "npx"))
        self.agents(home, "windsurf", "goose")
        (home.home / ".gemini").mkdir()
        self.assertEqual(providers.skills_agents(home.machine),
                         {"windsurf": home.home / ".codeium" / "windsurf" / "skills",
                          "goose": home.home / ".config" / "goose" / "skills"})
        skills = [step for step in home.plan() if step.app in providers.SKILLS_AGENTS]
        windsurf, goose = (providers.shown(folder, home.machine) for folder in providers.skills_agents(home.machine).values())
        self.assertEqual([(step.label, step.action, step.subject, step.note) for step in skills],
                         [("Windsurf", "install", f"the skills, copied into {windsurf} by the Skills CLI", ""),
                          ("Goose", "install", f"the skills, copied into {goose} by the Skills CLI", "in the command above")])
        self.assertEqual(skills[0].commands, [[home.machine.which("npx"), "-y", "skills@latest", "add",
                                               "earthtojake/text-to-cad#latest", "-g", "-a", "windsurf", "-a", "goose",
                                               "-s", "*", "-y", "--copy", "--json"]])
        self.assertEqual(skills[0].agents, ["windsurf", "goose"])

    def test_without_npx_each_agent_is_left_with_why(self) -> None:
        home = self.make()
        self.agents(home, "windsurf", "goose")
        self.assertEqual([(step.app, step.action, step.subject) for step in home.plan()],
                         [("windsurf", "leave", providers.NEED_NODE), ("goose", "leave", providers.NEED_NODE)])

    def test_a_loose_copy_of_ours_in_a_plugin_app_s_folder_goes_and_a_skill_only_named_like_ours_stays(self) -> None:
        home = self.make(("claude",))
        home.set(claude={"plugins": [{"id": "text-to-cad@earthtojake", "version": RELEASE, "scope": "user"}],
                         "marketplaces": [{"name": "earthtojake", "repo": "earthtojake/text-to-cad", "ref": "latest"}]})
        loose = home.skill(home.home / ".claude" / "skills")
        home.skill(home.home / ".claude" / "skills", "dxf", ours=False)
        home.skill(home.home / ".claude" / "skills", "mine")  # says our repository, but no skill of ours
        steps = home.plan()
        self.assertEqual([(step.action, step.edit) for step in steps if step.changes],
                         [("remove duplicate", {"op": "move", "path": str(loose)})])

    def test_the_shared_folder_is_a_skills_agent_s_and_codex_says_it_lists_them_too(self) -> None:
        home = self.make(("codex", "npx"))
        self.agents(home, "cline")
        home.skill(home.home / ".agents" / "skills")
        steps = home.plan()
        self.assertEqual([(step.app, step.action) for step in steps],
                         [("codex", "install"), ("cline", "update"), ("codex", "leave")])
        shared = providers.shown(providers.shared_skills(home.machine), home.machine)
        self.assertEqual(steps[-1].subject, f"the skills in {shared}, Cline's folder: Codex lists them beside its plugin's")

    def test_up_to_date_is_the_release_and_the_skills_the_cli_installed_and_the_replay_removes_them(self) -> None:
        home = self.make(("npx",))
        self.agents(home, "windsurf")
        # The CLI skips a skill (one its YAML parser refused): what it says it installed is recorded.
        skipped = [name for name in providers.SKILLS if name != "step-parts"]
        home.set(skills=skipped)
        (added,) = home.apply(home.plan())
        self.assertEqual(added["skills"], skipped)
        folder = home.home / ".codeium" / "windsurf" / "skills"
        where = providers.shown(folder, home.machine)
        record = {"windsurf": {"release": RELEASE, "skills": added["skills"]}}
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record)],
                         [("leave", f"the skills in {where}, from cadgen {RELEASE}: up to date")])
        # A recorded skill gone, or another release: added again, said why.
        providers.remove_path(folder / "dxf")
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record)],
                         [("update", f"the skills in {where}: dxf missing")])
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record, release="1.2.4")],
                         [("update", f"the skills in {where}, from cadgen {RELEASE} -> 1.2.4")])
        (step,) = providers.uninstall_plan(home.detect(), {"actions": [], "skills": record}, machine=home.machine)
        self.assertEqual(step.commands, [[home.machine.which("npx"), "-y", "skills@latest", "remove", "-g", "-a", "windsurf",
                                          "-s", *sorted(name for name in skipped if name != "dxf"), "-y"]])
        home.apply([step])
        self.assertEqual(providers.ours_in(folder), [])


if __name__ == "__main__":
    unittest.main()
