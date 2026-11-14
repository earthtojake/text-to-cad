"""The agent apps ``cad setup`` reads and changes (``cad_server._internal.providers``).

Every test builds a temporary home, a plugin folder in it (the one the server writes,
``cad_server._internal.plugin``: here its manifests and one skill), and puts on a temporary PATH fake
``claude``, ``codex``, ``gemini``, ``grok`` and ``npx`` commands: one small emulator (``EMULATOR``) that
records each call and keeps each app's state the way the app does -- Claude Code's in its records and behind its
``--json`` listing (a local catalog's folder read in place), Grok Build's in its registry, Codex's in
``config.toml`` and its cache (a copy of a local catalog's plugin), Gemini CLI's link and Cursor's copy
in their folders -- so a plan is applied, read back and taken out again. Codex's and Cursor's commands
are checked this way, in dry run; Claude Code and Gemini CLI themselves read a real folder in
``tests/python/global/test_plugin_folder.py``. Nothing here runs a real app or touches the developer's home.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cad/src")

from cad_server._internal import providers  # noqa: E402

RELEASE = "1.2.3"
ID = providers.PLUGIN_ID
NPX = ["--prefer-offline", "-y", "skills@latest"]

# What Claude Code and Grok Build keep on disk of the state the emulator holds for them, as each writes it:
# what `providers.detect` reads.
RECORDS = r'''
def write_records(world, home):
    claude = world.get("claude")
    if claude is not None:
        folder = home / ".claude" / "plugins"
        folder.mkdir(parents=True, exist_ok=True)
        table = {}
        for plugin in claude["plugins"]:
            table.setdefault(plugin["id"], []).append({key: value for key, value in plugin.items() if key != "id"})
        (folder / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": table}), encoding="utf-8")
        known = {}
        for market in claude["marketplaces"]:
            kind = market.get("source")
            known[market["name"]] = {"source": ({"source": "directory", "path": market.get("path")} if kind == "directory"
                                                else {"source": kind, "repo": market.get("repo"), "ref": market.get("ref")})}
        (folder / "known_marketplaces.json").write_text(json.dumps(known), encoding="utf-8")
    grok = world.get("grok")
    if grok is not None:
        repos = {}
        for plugin in grok["plugins"]:
            repos[plugin["name"]] = {"path": plugin["path"], "plugins": {plugin["name"]: {"version": plugin["version"]}},
                                     "kind": {"type": "Git", "url": plugin["source"], "git_ref": plugin.get("ref", "")}}
        registry = home / ".grok" / "installed-plugins" / "registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"version": 1, "repos": repos}), encoding="utf-8")
'''
exec(RECORDS)

# One program behind every fake command: `python EMULATOR <tool> ARGS...`. Its world is a JSON file
# (FAKE_WORLD): the release the `latest` branch holds, the commands told to fail, and the state the
# apps keep behind their commands; every call is logged beside it, one JSON line each.
EMULATOR = r'''
import json, os, shutil, sys
from pathlib import Path
''' + RECORDS + r'''
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
    write_records(world, home)
    sys.exit(0)


def refuse(why):
    print(tool + ": " + why, file=sys.stderr)
    sys.exit(1)


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def catalog(source):
    """A catalog to add: a local folder (its own catalog's name), or this repository on GitHub."""
    if os.path.isdir(source):
        name = read(Path(source) / ".claude-plugin" / "marketplace.json").get("name")
        if not name:
            refuse("no marketplace.json in " + source)
        return {"name": name, "source": "directory", "path": source}
    repo, _, ref = source.partition("#")
    return {"name": "earthtojake", "source": "github", "repo": repo, **({"ref": ref} if ref else {})}


def toml(state):
    lines = []
    for table in ("marketplaces", "plugins", "mcp_servers"):
        for name, entry in state.get(table, {}).items():
            lines.append("[%s.%s]" % (table, json.dumps(name)))
            lines += ["%s = %s" % (key, json.dumps(value)) for key, value in entry.items()]
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


if tool == "claude":
    state = world.setdefault("claude", {"plugins": [], "marketplaces": []})
    plugins, markets = state["plugins"], state["marketplaces"]
    known = {market["name"]: market for market in markets}
    if args == ["plugin", "list", "--json"]:
        for plugin in plugins:  # a local catalog's plugin is read in place: its folder's version, now
            market = known.get(plugin["id"].split("@")[1], {})
            if market.get("source") == "directory":
                plugin.update({"readFromFolder": market["path"],
                               "folderVersion": read(Path(market["path"]) / ".claude-plugin" / "plugin.json").get("version")})
        print(json.dumps(plugins))
        sys.exit(0)
    if args == ["plugin", "marketplace", "list", "--json"]:
        print(json.dumps(markets))
        sys.exit(0)
    if args[:3] == ["plugin", "marketplace", "add"]:
        market = catalog(args[3])
        if market["name"] in known and known[market["name"]] != market:
            refuse("its source doesn't match its extraKnownMarketplaces entry")
        if market["name"] not in known:
            markets.append(market)
        done()
    if args[:3] == ["plugin", "marketplace", "remove"]:
        state["marketplaces"] = [market for market in markets if market["name"] != args[3]]
        state["plugins"] = [plugin for plugin in plugins if not plugin["id"].endswith("@" + args[3])]
        done()
    if args[:2] in (["plugin", "install"], ["plugin", "update"]):
        market = known.get(args[2].split("@")[1])
        if market is None:
            refuse("no such marketplace")
        version = (read(Path(market["path"]) / ".claude-plugin" / "plugin.json").get("version")
                   if market["source"] == "directory" else release)
        state["plugins"] = [plugin for plugin in plugins if plugin["id"] != args[2]] + [
            {"id": args[2], "version": version, "scope": "user", "enabled": True}]
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
    if args[:4] == ["mcp", "remove", "--scope", "local"]:
        # A project's server, which Claude Code finds by the folder it runs in.
        config = home / ".claude.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        here = os.path.realpath(os.getcwd())
        project = next((key for key in data.get("projects", {}) if os.path.realpath(key) == here), None)
        if project is None or args[4] not in data["projects"][project].get("mcpServers", {}):
            refuse("No MCP server found with name: " + args[4])
        data["projects"][project]["mcpServers"].pop(args[4])
        config.write_text(json.dumps(data), encoding="utf-8")
        done()
elif tool == "codex":
    state = world.setdefault("codex", {})
    if args == ["plugin", "list", "--json"]:
        # Codex's own listing, as the test sets it: canned JSON, a failure, or no answer at all.
        listing = world.get("codex_list", {"installed": [], "available": []})
        if listing == "hang":
            import time
            time.sleep(20)
        if listing == "fail":
            refuse("Not signed in")
        print(json.dumps(listing))
        sys.exit(0)
    if args == ["--version"]:
        # As the real one does: into CODEX_HOME, which it creates, even to say its version.
        arg0 = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "tmp" / "arg0"
        arg0.mkdir(parents=True, exist_ok=True)
        print("codex-cli " + world.get("codex_version", "0.153.4"))
        sys.exit(0)
    markets, plugins = state.setdefault("marketplaces", {}), state.setdefault("plugins", {})
    cache = home / ".codex" / "plugins" / "cache"
    if args[:3] == ["plugin", "marketplace", "add"]:
        if os.path.isdir(args[3]):
            name = catalog(args[3])["name"]
            entry = {"source_type": "local", "source": args[3]}
        else:
            name, entry = "earthtojake", {"source_type": "git", "source": "https://github.com/%s.git" % args[3]}
            if "--ref" in args:
                entry["ref"] = args[args.index("--ref") + 1]
        if name in markets and markets[name] != entry:
            refuse("a marketplace named %s exists" % name)
        markets[name] = entry
    elif args[:3] == ["plugin", "marketplace", "upgrade"]:
        pass
    elif args[:3] == ["plugin", "marketplace", "remove"]:
        markets.pop(args[3], None)
    elif args[:2] == ["plugin", "add"]:
        market = markets.get(args[2].split("@")[1])
        if market is None:
            refuse("no such marketplace")
        version = (read(Path(market["source"]) / ".codex-plugin" / "plugin.json").get("version")
                   if market["source_type"] == "local" else release)
        plugins[args[2]] = {"enabled": True}
        folder = cache / args[2].split("@")[1] / "text-to-cad"
        shutil.rmtree(folder, ignore_errors=True)
        (folder / version).mkdir(parents=True)
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
    if args[:2] == ["extensions", "link"]:
        if folder.exists():
            refuse("already installed")
        folder.mkdir(parents=True)
        (folder / ".gemini-extension-install.json").write_text(json.dumps({"source": args[2], "type": "link"}),
                                                               encoding="utf-8")
        done()
    if args == ["extensions", "uninstall", "text-to-cad"]:
        shutil.rmtree(folder)
        done()
elif tool == "grok":
    state = world.setdefault("grok", {"plugins": []})
    if args[:2] == ["plugin", "install"]:
        repo, _, ref = args[2].partition("@")
        path = str(home / ".grok" / "installed-plugins" / "text-to-cad-1")
        state["plugins"].append({"name": "text-to-cad", "version": release, "path": path,
                                 "source": "https://github.com/" + repo, "ref": ref})
        done()
    if args[:2] in (["plugin", "enable"], ["plugin", "update"]):
        for plugin in state["plugins"]:
            plugin["version"] = release
        done()
    if args[:2] == ["plugin", "uninstall"]:
        state["plugins"] = [plugin for plugin in state["plugins"] if plugin["name"] != args[2]]
        done()
elif tool == "npx" and args[:3] == ["--prefer-offline", "-y", "skills@latest"]:
    # The Skills CLI: `add` copies every skill into each named agent's folder, `remove` takes them out.
    agents = [args[index + 1] for index, word in enumerate(args) if word == "-a"]
    folders = world["skills_folders"]
    if args[3] == "add":
        assert os.path.isdir(args[4]), "the skills are added from the plugin folder's skills/"
        for agent in agents:
            for name in world["skills"]:
                skill = Path(folders[agent]) / name
                skill.mkdir(parents=True, exist_ok=True)
                (skill / "SKILL.md").write_text("---\nname: %s\n---\nMaintained at earthtojake/text-to-cad.\n" % name,
                                                encoding="utf-8")
        print(json.dumps([{"name": name, "status": "installed", "agents": agents} for name in world["skills"]]))
        done()
    if args[3] == "remove":
        for agent in agents:
            for name in args[args.index("-s") + 1:args.index("-y")]:
                shutil.rmtree(Path(folders[agent]) / name, ignore_errors=True)
        done()
refuse("unknown command " + said)
'''


def make_plugin_folder(folder: Path, version: str) -> Path:
    """The plugin folder as the server writes it, as far as the apps read it: its catalog, each host's
    manifest at ``version``, and a skill."""
    for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json",
                     "gemini-extension.json"):
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(json.dumps({"name": "text-to-cad", "version": version}), encoding="utf-8")
    (folder / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": providers.MARKETPLACE, "plugins": [{"name": "text-to-cad", "source": "./", "version": version}]}),
        encoding="utf-8")
    (folder / "skills" / "cad").mkdir(parents=True, exist_ok=True)
    (folder / "skills" / "cad" / "SKILL.md").write_text("---\nname: cad\n---\nMaintained at earthtojake/text-to-cad.\n",
                                                        encoding="utf-8")
    return folder


class Home:
    """A temporary home, its plugin folder, its fake commands on a PATH of their own, and the world they share."""

    def __init__(self, root: Path, tools: tuple[str, ...] = (), release: str = RELEASE) -> None:
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.bin = root / "bin"
        self.bin.mkdir()
        self.folder = make_plugin_folder(root / "state" / "plugin", release)
        self.world = root / "world.json"
        self.calls_file = root / "calls.jsonl"
        self.write_world({"release": release})
        (self.bin / "emulator.py").write_text(EMULATOR, encoding="utf-8")
        for tool in tools:
            self.tool(tool)
        environ = {key: value for key, value in os.environ.items()
                   if not key.endswith("_CLI") and key not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLAUDE_DESKTOP_CONFIG",
                                                               "APPDATA", "UV_INSTALL_DIR", "XDG_BIN_HOME", "XDG_CONFIG_HOME",
                                                               "HERMES_HOME", "FLATPAK_XDG_CONFIG_HOME", "GEMINI_CLI_HOME")}
        environ.update({"PATH": str(self.bin), "HOME": str(self.home), "USERPROFILE": str(self.home),
                        "FAKE_WORLD": str(self.world), "FAKE_HOME": str(self.home),
                        "CLAUDE_DESKTOP_CONFIG": str(self.desktop)})
        self.machine = providers.Machine(self.home, environ, bundled={}, homebrew=())
        self.set(skills=list(providers.SKILLS), skills_folders={
            agent: str(providers.skills_folder(agent, self.machine)) for agent in providers.SKILLS_AGENTS})

    @property
    def desktop(self) -> Path:
        return self.home / "desktop" / "claude_desktop_config.json"

    @property
    def cursor(self) -> Path:
        return providers.cursor_plugins(self.machine) / "text-to-cad"

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
        world = {**self.read_world(), **changes}
        self.write_world(world)
        write_records(world, self.home)

    def release(self, version: str) -> None:
        """A new release: the `latest` branch's, and the plugin folder written again for it."""
        self.set(release=version)
        make_plugin_folder(self.folder, version)

    def calls(self) -> list[list[str]]:
        if not self.calls_file.is_file():
            return []
        return [json.loads(line) for line in self.calls_file.read_text(encoding="utf-8").splitlines()]

    def changing_calls(self) -> list[list[str]]:
        """Every call but a listing or a version question."""
        return [call for call in self.calls() if call[1:] not in (["plugin", "list", "--json"], ["--version"],
                                                                  ["plugin", "marketplace", "list", "--json"])]

    def detect(self) -> dict:
        return providers.detect(self.machine, folder=self.folder)

    def plan(self, **options) -> list:
        return providers.plan(self.detect(), release=options.pop("release", RELEASE), folder=self.folder,
                              machine=self.machine, **options)

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

    def clone(self, path: Path, version: str = RELEASE) -> Path:
        """An earlier release's Cursor install: a clone of the repository's `latest` branch."""
        (path / ".cursor-plugin").mkdir(parents=True)
        (path / ".cursor-plugin" / "plugin.json").write_text(json.dumps({"name": "text-to-cad", "version": version}),
                                                             encoding="utf-8")
        (path / ".git").mkdir()
        (path / ".git" / "HEAD").write_text("ref: refs/heads/latest\n", encoding="utf-8")
        (path / ".git" / "config").write_text('[remote "origin"]\n\turl = https://github.com/earthtojake/text-to-cad\n',
                                              encoding="utf-8")
        return path


# Claude Desktop's server as releases through 0.11.10 wrote it.
ENTRY = {"command": "/bin/uvx", "args": ["--no-config", "--managed-python", "--python", "3.14", "--from",
                                          f"cad-mcp=={RELEASE}", "cad-mcp"],
         "env": {"CAD_INSTALL_CHANNEL": "claude-desktop"}}


def actions(steps: list) -> list[tuple[str, str]]:
    return [(step.app, step.action) for step in steps]


def commands(steps: list) -> dict[str, list[list[str]]]:
    return {step.app: [argv[1:] for argv in step.commands] for step in steps if step.commands}


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

    def test_every_app_is_pointed_at_the_plugin_folder_its_own_way_and_claude_desktop_gets_nothing(self) -> None:
        home = self.make(("claude", "codex", "gemini", "grok"))
        home.desktop.parent.mkdir(parents=True)
        (home.home / ".cursor").mkdir()
        folder = str(home.folder)
        steps = home.plan(only=["claude-desktop", "codex", "cursor", "grok", "gemini"])
        self.assertEqual(actions(steps), [("codex", "install"), ("cursor", "install"), ("grok", "install"),
                                          ("gemini", "install")])
        found = commands(steps)
        # Codex copies a local catalog's plugin; Gemini CLI links the folder, which it reads in place.
        self.assertEqual(found["codex"], [["plugin", "marketplace", "add", folder], ["plugin", "add", ID]])
        self.assertEqual(found["gemini"], [["extensions", "link", folder, "--consent"]])
        self.assertEqual(found["grok"], [["plugin", "install", "earthtojake/text-to-cad@latest", "--trust"],
                                         ["plugin", "enable", "text-to-cad"]])
        # Cursor gets a copy, real files, in its local plugins folder.
        self.assertEqual(steps[1].edit, {"op": "copy", "from": folder, "path": str(home.cursor)})
        # Claude Code reads a local catalog in place; its plugin feeds Cursor and Grok Build, so theirs are not added.
        # Claude gets the skills alone: nothing is written into Claude Desktop's config.
        steps = home.plan()
        self.assertEqual(actions(steps)[:2], [("claude", "install"), ("codex", "install")])
        home.apply(steps)
        self.assertFalse(home.desktop.exists())
        self.assertEqual(commands(steps)["claude"], [["plugin", "marketplace", "add", folder], ["plugin", "install", ID]])
        served = [step.subject for step in steps if step.app in ("cursor", "grok")]
        self.assertEqual(served, ["served by the Claude Code plugin"] * 2)

    def test_second_copies_are_found_and_removed_and_a_store_s_kept(self) -> None:
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
        # The app directory's copy is Codex's to deliver and update: kept, said, and nothing of ours added beside
        # it; the server added by hand goes.
        self.assertEqual([action for action, _subject in by_app["codex"]], ["leave", "remove duplicate"])
        self.assertIn("text-to-cad@openai-curated (its app directory's): the directory's copy, which the directory "
                      "updates, so it stays, and ours is not added beside it", by_app["codex"][0][1])
        self.assertIn("remove it in Codex's own plugin manager and run the install command again", by_app["codex"][0][1])
        self.assertNotIn(["plugin", "remove", "text-to-cad@openai-curated"], commands(steps)["codex"])
        # Cursor and Grok Build are served by Claude Code's plugin: their own copies go; the one Cursor installed
        # from a marketplace added in Cursor, which no command uninstalls, is left for the person to uninstall there.
        self.assertEqual([action for action, _subject in by_app["cursor"]],
                         ["leave", "leave", "remove duplicate"])
        self.assertIn("(installed from a marketplace in Cursor), which text-to-cad does not update: Cursor has no "
                      "command to uninstall it, so it stays", by_app["cursor"][1][1])
        self.assertIn("uninstall this one in Cursor", by_app["cursor"][1][1])
        self.assertEqual(by_app["grok"], [("leave", "served by the Claude Code plugin"),
                                          ("remove duplicate", "text-to-cad 1.2.3 (from /checkout)")])

    def test_claude_code_loses_every_cad_server_it_starts_itself_and_keeps_the_rest(self) -> None:
        # Claude Code takes CAD from the plugin's skills alone: a CAD server someone added with `claude mcp add`,
        # for the user or for one project, goes, by Claude Code's own command (a project's run in that project);
        # another server stays, and Claude Desktop gets none.
        home = self.make(("claude",))
        project, gone = home.root / "project", home.root / "deleted"
        project.mkdir()
        cad = {"command": "uvx", "args": ["--from", "cad-mcp==1.2.2", "cad-mcp"]}
        other = {"command": "npx", "args": ["-y", "some-server"]}
        (home.home / ".claude.json").write_text(json.dumps({
            "mcpServers": {"cad": cad, "other": other},
            "projects": {str(project): {"mcpServers": {"text-to-cad": cad, "other": other}},
                         str(gone): {"mcpServers": {"cad": cad}}}}), encoding="utf-8")
        home.desktop.parent.mkdir(parents=True)
        steps = home.plan()
        removals = [step for step in steps if step.action == "remove server"]
        self.assertEqual([([argv[1:] for argv in step.commands], step.cwd) for step in removals],
                         [([["mcp", "remove", "--scope", "user", "cad"]], None),
                          ([["mcp", "remove", "--scope", "local", "text-to-cad"]], str(project))])
        self.assertTrue(all("Claude Code gets text-to-cad as the plugin's skills alone" in step.subject
                            for step in removals))
        self.assertIn(("claude", "leave"), actions(steps))  # the deleted project's: Claude Code never starts it
        self.assertNotIn("claude-desktop", [step.app for step in steps])
        home.apply(steps)
        left = json.loads((home.home / ".claude.json").read_text(encoding="utf-8"))
        self.assertEqual(left["mcpServers"], {"other": other})
        self.assertEqual(left["projects"][str(project)]["mcpServers"], {"other": other})
        self.assertFalse(home.desktop.exists())
        self.assertEqual([copy.name for copy in home.detect()["claude"].copies if copy.kind == "server"], ["cad"])

    def test_claude_code_s_directory_copy_is_kept_and_keeps_ours_out(self) -> None:
        home = self.make(("claude",))
        official = "text-to-cad@claude-plugins-official"

        def plan_for(scope: str, *, ours: bool = False) -> list:
            plugins = [{"id": official, "version": "1.2.2", "scope": scope}]
            markets = []
            if ours:
                plugins.append({"id": ID, "version": RELEASE, "scope": "user"})
                markets.append({"name": providers.MARKETPLACE, "source": "directory", "path": str(home.folder)})
            home.set(claude={"plugins": plugins, "marketplaces": markets})
            return providers.read_for(lambda apps: providers.plan(apps, release=RELEASE, folder=home.folder,
                                                                  machine=home.machine, only=["claude", "cursor"]),
                                      home.machine, folder=home.folder)[1]

        # Another scope's copy (a project's) loads in that project alone: left as any other is, and ours installed.
        steps = plan_for("project")
        self.assertEqual(actions(steps), [("claude", "leave"), ("claude", "install")])
        self.assertIn("another scope's", steps[0].subject)
        (home.home / ".cursor").mkdir()
        # One an administrator manages: reported, and nothing of ours added beside it (Claude Code loads both).
        steps = plan_for("managed")
        self.assertEqual(actions(steps), [("claude", "leave"), ("cursor", "leave")])
        self.assertIn(f"{official} 1.2.2 (managed scope): an administrator manages it, so it stays, and ours is not "
                      "added beside it", steps[0].subject)
        self.assertEqual(steps[1].subject, "served by the Claude Code plugin")
        # The user scope's, claude.ai's directory's, is the directory's to update: kept, nothing run, and the line
        # says how to get ours instead.
        steps = plan_for("user")
        self.assertEqual(actions(steps), [("claude", "leave"), ("cursor", "leave")])
        self.assertEqual(steps[0].subject, f"{official} 1.2.2 (claude.ai's directory's): the directory's copy, which "
                                           "the directory updates, so it stays, and ours is not added beside it (Claude "
                                           "Code would load both); for ours, remove it in Claude Code's own plugin "
                                           "manager and run the install command again")
        self.assertFalse(any(step.commands for step in steps))
        # Ours beside it, as main always had it beside a copy no command here removes, goes: the app would load both.
        steps = plan_for("user", ours=True)
        self.assertEqual(actions(steps), [("claude", "leave"), ("claude", "remove duplicate"), ("cursor", "leave")])
        self.assertEqual(commands(steps)["claude"], [["plugin", "uninstall", ID],
                                                     ["plugin", "marketplace", "remove", providers.MARKETPLACE]])

    def synced(self, home: Home) -> None:
        """A copy claude.ai syncs into Claude Code from the person's account: its manifest alone, no install record."""
        synced = home.home / ".claude" / "plugins" / "synced" / "bucket"
        synced.mkdir(parents=True)
        (synced / "manifest.json").write_text(json.dumps({
            "name": "text-to-cad", "version": "1.2.2", "marketplaceName": "claude-plugins-official",
            "installationPreference": "available", "marketplaceKind": "official"}), encoding="utf-8")

    def test_a_copy_claude_ai_syncs_is_kept_by_every_run_and_keeps_ours_out_of_claude_code(self) -> None:
        # Recorded nowhere but in its manifest and in no scope: the install and every update (a refresh after a
        # switch among them) keep it and add nothing of ours beside it in Claude Code.
        home = self.make(("claude",))
        self.synced(home)
        apps = home.detect()
        self.assertEqual([(copy.name, copy.version, copy.store) for copy in apps["claude"].copies],
                         [("text-to-cad@claude-plugins-official", "1.2.2", True)])
        steps = home.plan(only=["claude"])
        self.assertEqual(actions(steps), [("claude", "leave")])
        self.assertIn("claude.ai syncs it from your account", steps[0].subject + apps["claude"].copies[0].held_by)
        self.assertIn("remove it in your claude.ai account's plugins and run the install command again", steps[0].subject)
        self.assertEqual(providers.refresh_plan(apps, release=RELEASE, folder=home.folder, machine=home.machine), [])
        # Ours, installed beside it by an earlier run, goes: Claude Code would load both.
        home.set(claude={"plugins": [{"id": ID, "version": RELEASE, "scope": "user"}],
                         "marketplaces": [{"name": "text-to-cad", "source": "directory", "path": str(home.folder)}]})
        steps = home.plan(only=["claude"])
        self.assertEqual(actions(steps), [("claude", "leave"), ("claude", "remove duplicate")])
        self.assertEqual(commands(steps)["claude"][0], ["plugin", "uninstall", ID])

    def test_a_copy_claude_ai_syncs_feeds_neither_cursor_nor_grok_build(self) -> None:
        # Cursor reads Claude Code's installed_plugins.json alone, and Grok Build each installPath in it: a synced copy
        # is in neither, so Cursor gets its own copy, and keeps it, as on a device with no Claude Code.
        home = self.make(("claude",))
        self.synced(home)
        (home.home / ".cursor").mkdir()
        self.assertFalse(providers.feeds(home.detect(), providers.APPS))
        steps = home.plan()
        self.assertEqual(actions(steps), [("claude", "leave"), ("cursor", "install")])
        home.apply(steps)
        steps = home.plan()
        self.assertEqual(actions(steps), [("claude", "leave"), ("cursor", "leave")])
        self.assertIn(f"{RELEASE}, a copy of", steps[1].subject)

    def codex_plan(self, home: Home) -> list:
        return providers.read_for(lambda apps: providers.plan(apps, release=RELEASE, folder=home.folder,
                                                              machine=home.machine, only=["codex"]),
                                  home.machine, folder=home.folder)[1]

    def remote(self, home: Home, market: str = "openai-curated", marked: bool = True) -> None:
        """What a copy Codex installed from its maker's directory on the account leaves in its plugin cache."""
        folder = home.home / ".codex" / "plugins" / "cache" / market / "text-to-cad"
        (folder / "1.2.2").mkdir(parents=True)
        if marked:
            (folder / providers.CODEX_REMOTE_MARK).write_text(json.dumps(
                {"schema_version": 1, "remote_plugin_id": "plugin_123"}), encoding="utf-8")

    @staticmethod
    def listing(market: str = "openai-curated", **entry) -> dict:
        return {"installed": [{"pluginId": f"text-to-cad@{market}", "name": "text-to-cad", "marketplaceName": market,
                               "version": "1.2.2", "installed": True, "enabled": True,
                               "source": {"source": "remote", "id": "plugin_123"}, **entry}], "available": []}

    def test_codex_s_listing_is_the_strong_evidence_of_its_directory_s_copy_and_ours_goes(self) -> None:
        home = self.make(("codex",))
        home.apply(self.codex_plan(home))  # ours, installed
        self.remote(home)
        home.set(codex_list=self.listing())
        steps = self.codex_plan(home)
        self.assertEqual(actions(steps), [("codex", "leave"), ("codex", "remove duplicate")])
        self.assertIn("text-to-cad@openai-curated 1.2.2 (its app directory's, on your OpenAI account): the "
                      "directory's copy, which the directory updates, so it stays", steps[0].subject)
        self.assertEqual(commands(steps)["codex"][0], ["plugin", "remove", ID])
        self.assertIn(["codex", "plugin", "list", "--json"], home.calls())

    def test_codex_s_cache_alone_is_weak_evidence_that_never_removes_ours_and_never_keeps_it_out(self) -> None:
        home = self.make(("codex",))
        self.remote(home)
        line = ("Codex's cache also holds OpenAI's directory copy, which Codex loads only while you are signed in; if "
                "the skills show twice, remove one copy")
        # The listing fails (no sign-in), says nothing of it, names it disabled, or never answers: ours is installed,
        # and a line says so.
        for said in ("fail", {"installed": [], "available": []}, self.listing(enabled=False), "hang"):
            with self.subTest(listing=said), mock.patch.object(providers, "CODEX_LIST_SECONDS", 2):
                home.set(codex_list=said)
                steps = self.codex_plan(home)
                self.assertEqual(actions(steps), [("codex", "leave"), ("codex", "install")])
                self.assertIn(line, steps[0].subject)
        # With ours there, it is kept, and nothing is removed.
        home.apply(steps)
        home.set(codex_list="fail")
        steps = self.codex_plan(home)
        self.assertEqual(actions(steps), [("codex", "leave"), ("codex", "leave")])
        self.assertFalse(any(step.commands or step.edit for step in steps))

    def test_a_cache_folder_without_codex_s_mark_or_from_openai_s_own_catalogs_is_no_evidence(self) -> None:
        home = self.make(("codex",))
        self.remote(home, marked=False)
        for market in sorted(providers.CODEX_NOT_STORES):
            self.remote(home, market)
        home.set(codex_list={"installed": [self.listing(market)["installed"][0]
                                           for market in sorted(providers.CODEX_NOT_STORES)], "available": []})
        apps = home.detect()
        self.assertEqual((apps["codex"].copies, apps["codex"].cached), ([], []))
        steps = self.codex_plan(home)
        self.assertEqual(actions(steps), [("codex", "install")])
        self.assertNotIn(["codex", "plugin", "list", "--json"], home.calls(), "no weak evidence: Codex not asked")

    def test_a_receipt_that_says_an_earlier_release_replaced_a_directory_s_copy_still_reads(self) -> None:
        # Releases through 0.11.10 removed a directory's copy at the install command and recorded it (`store`): an
        # uninstall does not put it back, and says where it came from.
        home = self.make(("claude",))
        gone = "text-to-cad@claude-plugins-official 1.2.2 (claude.ai's directory's)"
        receipt = {"actions": [{"app": "claude", "action": "remove duplicate", "kind": "command", "ok": True,
                                "store": gone, "at": "2026-10-31T02:39:00Z"}]}
        self.assertEqual(providers.replaced(receipt), [{"app": "claude", "store": gone, "at": "2026-10-31T02:39:00Z"}])
        undo = providers.uninstall_plan(home.detect(), receipt, machine=home.machine, folder=home.folder)
        self.assertEqual(actions(undo), [("claude", "leave")])
        self.assertIn("is not put back; install it from claude.ai's plugin directory again", undo[0].subject)

    def test_without_claude_code_a_copy_from_a_marketplace_in_cursor_keeps_ours_out(self) -> None:
        # Cursor keeps what it installed from a marketplace added in Cursor in its own app data and has no command
        # to uninstall it. It keeps the repository it fetched in a folder per commit, whose VERSION says which
        # release it is: said, since text-to-cad never updates that copy and it can be far behind.
        home = self.make()
        taken = home.home / ".cursor" / "plugins" / "cache" / "earthtojake" / "text-to-cad" / "0123abc"
        taken.mkdir(parents=True)
        (taken / "VERSION").write_text("0.7.12\n", encoding="utf-8")
        (step,) = home.plan()
        self.assertEqual((step.app, step.action), ("cursor", "leave"))
        self.assertIn("(installed from a marketplace in Cursor, text-to-cad 0.7.12), which text-to-cad does not "
                      "update: Cursor has no command to uninstall it, so it stays, "
                      "and ours is not added beside it; for ours, uninstall it in Cursor, then run the install command "
                      "again", step.subject)

    def test_an_earlier_release_s_copies_from_github_give_way_to_the_folder_s(self) -> None:
        home = self.make(("claude", "codex", "gemini"))
        github = {"name": "earthtojake", "source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        home.set(claude={"plugins": [{"id": "text-to-cad@earthtojake", "version": "1.2.2", "scope": "user"}],
                         "marketplaces": [github]},
                 codex={"marketplaces": {"earthtojake": {"source_type": "git", "ref": "latest",
                                                         "source": "https://github.com/earthtojake/text-to-cad.git"}},
                        "plugins": {"text-to-cad@earthtojake": {"enabled": True}}})
        (home.home / ".codex").mkdir()
        (home.home / ".codex" / "config.toml").write_text(
            '[marketplaces.earthtojake]\nsource_type = "git"\nsource = "https://github.com/earthtojake/text-to-cad.git"\n'
            'ref = "latest"\n[plugins."text-to-cad@earthtojake"]\nenabled = true\n', encoding="utf-8")
        extension = home.home / ".gemini" / "extensions" / "text-to-cad"
        extension.mkdir(parents=True)
        (extension / "gemini-extension.json").write_text('{"name": "text-to-cad", "version": "1.2.2"}', encoding="utf-8")
        (extension / ".gemini-extension-install.json").write_text(json.dumps(
            {"source": "https://github.com/earthtojake/text-to-cad", "type": "git", "ref": "latest"}), encoding="utf-8")
        steps = home.plan(only=["claude", "codex", "gemini"])
        folder = str(home.folder)
        self.assertEqual(actions(steps), [("claude", "remove duplicate"), ("claude", "install"),
                                          ("codex", "remove duplicate"), ("codex", "install"),
                                          ("gemini", "remove duplicate"), ("gemini", "install")])
        # The GitHub catalog goes with its plugin (Codex would fetch it again at every start).
        self.assertEqual([argv[1:] for argv in steps[0].commands],
                         [["plugin", "uninstall", "text-to-cad@earthtojake"], ["plugin", "marketplace", "remove", "earthtojake"]])
        self.assertEqual([argv[1:] for argv in steps[2].commands],
                         [["plugin", "remove", "text-to-cad@earthtojake"], ["plugin", "marketplace", "remove", "earthtojake"]])
        self.assertEqual([argv[1:] for argv in steps[4].commands], [["extensions", "uninstall", "text-to-cad"]])
        self.assertEqual([argv[1:] for argv in steps[5].commands], [["extensions", "link", folder, "--consent"]])
        home.apply(steps)
        apps = home.detect()
        self.assertEqual({name: [(copy.name, copy.via) for copy in apps[name].copies] for name in ("claude", "codex", "gemini")},
                         {"claude": [(ID, "in place")], "codex": [(ID, "copied")], "gemini": [("text-to-cad", "linked")]})
        self.assertEqual(sorted(apps["claude"].marketplaces), [providers.MARKETPLACE])
        self.assertEqual(sorted(apps["codex"].marketplaces), [providers.MARKETPLACE])
        self.assertEqual({step.action for step in home.plan(only=["claude", "codex", "gemini"])}, {"leave"})

    def test_a_new_release_s_folder_is_copied_again_where_an_app_keeps_a_copy(self) -> None:
        # In dry run: the commands an update runs for Codex and Cursor, and Claude Code's cached copy.
        home = self.make(("claude", "codex"))
        home.apply(home.plan(only=["claude", "codex"]))
        home.release("1.2.4")
        steps = home.plan(release="1.2.4", only=["claude", "codex"])
        self.assertEqual([(step.app, step.action, [argv[1:] for argv in step.commands]) for step in steps],
                         [("claude", "update", [["plugin", "update", ID]]), ("codex", "update", [["plugin", "add", ID]])])
        # The switch's refresh: the same, and nothing installed where the app has no copy of ours.
        self.assertEqual(actions(providers.refresh_plan(home.detect(), release="1.2.4", folder=home.folder,
                                                        machine=home.machine)),
                         [("claude", "update"), ("codex", "update")])
        home.apply(steps)
        apps = home.detect()
        self.assertEqual((apps["claude"].ours().recorded, apps["codex"].ours().version), ("1.2.4", "1.2.4"))
        self.assertEqual(providers.refresh_plan(apps, release="1.2.4", folder=home.folder, machine=home.machine), [])

    def test_a_catalog_of_ours_pointing_elsewhere_is_pointed_at_the_folder(self) -> None:
        home = self.make(("claude", "codex"))
        elsewhere = make_plugin_folder(self.root / "elsewhere", "1.2.2")
        home.set(claude={"plugins": [{"id": ID, "version": "1.2.2", "scope": "user"}],
                         "marketplaces": [{"name": providers.MARKETPLACE, "source": "directory", "path": str(elsewhere)}]})
        steps = home.plan(only=["claude"])
        self.assertEqual([(step.action, [argv[1:] for argv in step.commands]) for step in steps],
                         [("update", [["plugin", "marketplace", "remove", providers.MARKETPLACE],
                                      ["plugin", "marketplace", "add", str(home.folder)], ["plugin", "install", ID]])])
        self.assertEqual(providers.refresh_plan(home.detect(), release=RELEASE, folder=home.folder, machine=home.machine),
                         [], "a refresh points nothing: setup does")

    def test_the_newer_of_the_codex_on_path_and_the_app_s_own_installs(self) -> None:
        # Both write the one ~/.codex the app reads, so the newer command does: here the app's.
        home = self.make(("codex",))
        app = self.root / "app"
        (app / "bin").mkdir(parents=True)
        bundled = app / "bin" / ("codex.cmd" if os.name == "nt" else "codex")
        bundled.write_text("@echo codex-cli 0.200.0\r\n" if os.name == "nt" else "#!/bin/sh\necho codex-cli 0.200.0\n",
                           encoding="utf-8")
        bundled.chmod(bundled.stat().st_mode | stat.S_IXUSR)
        home.machine.bundled = {"codex": [str(bundled)]}
        self.assertEqual(providers.codex_cli(home.machine), str(bundled))
        home.set(codex_version="0.300.0")
        self.assertEqual(providers.codex_cli(home.machine), home.machine.which("codex"))
        self.assertEqual(home.detect()["codex"].command, home.machine.which("codex"))
        # Asked in a folder thrown away: the command writes there as it starts, and no ~/.codex appears.
        self.assertEqual(home.calls(), [["codex", "--version"]] * 3)
        self.assertFalse((home.home / ".codex").exists())
        # What the package keeps beside the command says it, and nothing runs: the app's bundle, the npm package.
        (app / "codex-package.json").write_text(json.dumps({"variant": "codex", "version": "0.400.0"}), encoding="utf-8")
        self.assertEqual(providers.codex_cli(home.machine), str(bundled))
        calls = len(home.calls())
        # npm's command on macOS and Linux is a link into its package, whose package.json says it. Windows' npm
        # writes a codex.cmd shim instead, and Windows finds a command by a PATHEXT name (as `tool` writes the
        # fakes), never an extensionless link: there the app's bundle above is the whole case.
        if os.name != "nt":
            package = self.root / "npm" / "@openai" / "codex"
            (package / "bin").mkdir(parents=True)
            (package / "package.json").write_text(json.dumps({"name": "@openai/codex", "version": "0.500.0"}),
                                                  encoding="utf-8")
            script = package / "bin" / "codex.js"
            script.write_text("", encoding="utf-8")
            script.chmod(0o755)
            linked = self.root / "linked"
            linked.mkdir()
            (linked / "codex").symlink_to(script)
            home.machine.environ["PATH"] = str(linked)
            self.assertEqual(providers.codex_cli(home.machine), str(linked / "codex"))
            self.assertEqual(len(home.calls()), calls, "nothing run")
        # One command, with no other to compare it with, is taken as it is: the one PATH finds.
        home.machine.bundled = {}
        on_path = home.machine.which("codex")
        self.assertIsNotNone(on_path)
        self.assertEqual(providers.codex_cli(home.machine), on_path)
        self.assertEqual(len(home.calls()), calls, "nothing run")

    def test_what_an_app_has_is_read_from_its_files_with_no_command_run(self) -> None:
        """Each app's command writes its own files as it starts, so reading what it has, for a dry run or a plan
        that leaves it alone, runs none of them; a real run about to change Claude Code asks its listing too."""
        home = self.make(("claude", "codex", "gemini", "grok"))
        steps = home.plan()
        self.assertEqual(home.calls(), [], "planning an install runs nothing")
        self.assertFalse((home.home / ".codex").exists())
        home.apply(steps)
        self.assertNotEqual(home.calls(), [])
        made = len(home.calls())
        found = home.detect()
        self.assertEqual(found["claude"].ours().version, RELEASE)
        self.assertEqual((found["claude"].ours().recorded, found["claude"].ours().via), (RELEASE, "in place"))
        self.assertEqual(found["codex"].ours().version, RELEASE)
        self.assertEqual(found["gemini"].ours().via, "linked")
        self.assertEqual(len(home.calls()), made, "reading what they have now runs nothing either")
        # Nothing to do for any of them: a real run reads and leaves them, and runs none.
        apps, steps, listed = providers.read_for(lambda apps: providers.plan(apps, release=RELEASE, folder=home.folder,
                                                                             machine=home.machine),
                                                 home.machine, folder=home.folder)
        self.assertFalse(listed)
        self.assertEqual({step.action for step in steps}, {"leave"})
        self.assertEqual(len(home.calls()), made)
        # A new release, for an app that reads the folder in place too, is a command of Claude Code's: its listing is
        # asked first, and is what the plan is made from.
        home.release("1.2.4")
        apps, steps, listed = providers.read_for(lambda apps: providers.plan(apps, release="1.2.4", folder=home.folder,
                                                                             machine=home.machine),
                                                 home.machine, folder=home.folder)
        self.assertTrue(listed)
        self.assertEqual(home.calls()[made:], [["claude", "plugin", "list", "--json"],
                                               ["claude", "plugin", "marketplace", "list", "--json"]])

    def test_grok_build_s_copy_is_read_from_its_registry(self) -> None:
        home = self.make(("grok",))
        home.set(grok={"plugins": [{"name": "text-to-cad", "version": "1.2.2", "path": "/x", "ref": providers.BRANCH,
                                    "source": providers.REPOSITORY_URL},
                                   {"name": "another", "version": "9", "path": "/y", "source": "https://example.com/y"}]})
        grok = home.detect()["grok"]
        self.assertEqual([(copy.name, copy.version, copy.path, copy.ours) for copy in grok.copies],
                         [("text-to-cad", "1.2.2", "/x", True)])
        self.assertEqual(home.calls(), [])
        # An install from anywhere else is a second copy, and a registry that names no plugins says by its manifests.
        registry = home.home / ".grok" / "installed-plugins" / "registry.json"
        folder = self.root / "checkout"
        (folder / ".cursor-plugin").mkdir(parents=True)
        (folder / ".cursor-plugin" / "plugin.json").write_text(json.dumps({"name": "text-to-cad", "version": "1.0.0"}),
                                                               encoding="utf-8")
        registry.write_text(json.dumps({"repos": {"r": {"path": str(folder), "kind": {"type": "Local", "path": "/co"}}}}),
                            encoding="utf-8")
        grok = home.detect()["grok"]
        self.assertEqual([(copy.version, copy.ours, copy.detail) for copy in grok.copies], [("1.0.0", False, "from /co")])

    def test_the_person_s_uvx_is_found_never_one_that_goes_from_under_it(self) -> None:
        # The install command's `cad setup` runs with uvx's own environment first on PATH (uv's cache's,
        # which `uv cache clean` removes), a release folder holds a uvx (an update removes the folder), and so
        # may this process's own environment: the person's uvx is found past all three.
        home = self.make()
        cached = self.root / "uv" / "archive-v0" / "M-XQ" / "bin"
        release = self.root / "state" / "releases" / RELEASE
        (release / "bin").mkdir(parents=True)
        (release / providers.RELEASE_MARKER).write_text("{}", encoding="utf-8")
        own = self.root / "venv"
        person = self.root / "person-bin"
        for folder in (cached, release / "bin", own / "bin", person):
            home.tool("uvx", folder)
        home.machine.environ["PATH"] = os.pathsep.join(str(folder) for folder in (cached, release / "bin", own / "bin", person))
        with mock.patch.object(sys, "prefix", str(own)):
            self.assertEqual(providers.uvx(home.machine), os.path.abspath(shutil.which("uvx", path=str(person))))
            self.assertEqual(providers.lasting(home.machine.environ["PATH"]), str(person))
        # None on PATH but uv's cache's: the one where uv's installer puts it.
        home.machine.environ["PATH"] = str(cached)
        self.assertIsNone(providers.uvx(home.machine))
        installed = home.home / ".local" / "bin" / ("uvx.exe" if os.name == "nt" else "uvx")
        installed.parent.mkdir(parents=True)
        installed.write_text("", encoding="utf-8")
        installed.chmod(0o755)
        self.assertEqual(providers.uvx(home.machine), str(installed))

    def test_an_engine_a_gui_app_started_finds_uvx_where_uv_s_installer_or_homebrew_put_it(self) -> None:
        # An app opened from the Dock, and the engine it starts, have none of the person's PATH: a uvx that
        # stays is still found, in uv's installer's folders, else Homebrew's.
        home = self.make()
        home.machine.environ.pop("XDG_DATA_HOME", None)
        home.machine.environ["PATH"] = str(self.root / "usr-bin")
        name = "uvx.exe" if os.name == "nt" else "uvx"

        def put(folder: Path) -> Path:
            folder.mkdir(parents=True)
            (folder / name).write_text("", encoding="utf-8")
            (folder / name).chmod(0o755)
            return folder / name

        brew = self.root / "opt" / "homebrew" / "bin"
        home.machine.homebrew = (str(brew),)
        self.assertIsNone(providers.uvx(home.machine))
        if os.name != "nt":  # Homebrew is not Windows'
            found = put(brew)
            self.assertEqual(providers.uvx(home.machine), str(found))
        data = self.root / "xdg" / "share"
        home.machine.environ["XDG_DATA_HOME"] = str(data)
        installed = put(data.parent / "bin")
        self.assertEqual(providers.uvx(home.machine), str(installed), "uv's installer's folder before Homebrew's")


class ApplyReadBackAndTakeBack(Fixture):
    def test_an_install_applied_is_up_to_date_on_the_next_run_and_its_receipt_takes_it_back(self) -> None:
        home = self.make(("claude", "codex", "gemini"))
        (home.home / ".cursor").mkdir()
        steps = home.plan(only=["claude", "claude-desktop", "codex", "gemini"])
        self.assertEqual(actions(steps), [("claude", "install"), ("codex", "install"), ("gemini", "install")])
        records = home.apply(steps, backed_up=set())
        # The next run finds every copy current and changes nothing.
        calls = len(home.calls())
        self.assertEqual({step.action for step in home.plan(only=["claude", "claude-desktop", "codex", "gemini"])},
                         {"leave"})
        self.assertEqual([call for call in home.calls()[calls:] if call in home.changing_calls()], [])
        # The receipt's replay takes back what was done, newest first: each plugin and the folder's catalog it
        # added removed.
        undo = providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine, folder=home.folder)
        self.assertEqual(actions(undo), [("gemini", "remove"), ("codex", "remove"), ("claude", "remove")])
        self.assertEqual(commands(undo)["claude"], [["plugin", "uninstall", ID],
                                                    ["plugin", "marketplace", "remove", providers.MARKETPLACE]])
        home.apply(undo)
        apps = home.detect()
        self.assertEqual([copy.name for name in ("claude", "codex", "gemini") for copy in apps[name].copies], [])
        self.assertEqual(apps["claude"].marketplaces, {})
        self.assertNotIn(providers.MARKETPLACE, apps["codex"].marketplaces)


class ClaudeDesktop(Fixture):
    """Claude gets no CAD server: releases through 0.11.10 wrote one into Claude Desktop's config, which every run
    takes out, and an uninstall still takes back as its receipt says."""

    def earlier_install(self, home: Home, config: dict | None) -> dict:
        """Claude Desktop's config with the server an earlier release wrote, and the receipt record it wrote."""
        home.desktop.parent.mkdir(parents=True, exist_ok=True)
        if config is not None:
            home.desktop.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        done = providers.edit_servers(home.desktop, set_entries={"cad": ENTRY})
        return {"app": "claude-desktop", "action": "install", "kind": "edit", **done, "ok": True}

    def test_setup_takes_ours_out_and_leaves_the_rest_of_the_file_as_it_was(self) -> None:
        home = self.make()
        mine = {"command": "node", "args": ["server.js"], "env": {"TOKEN": "x"}}
        hand = {"command": "uvx", "args": ["--from", "cad-mcp==1.2.2", "cad-mcp"]}  # added by hand, under its own key
        earlier = self.earlier_install(home, {"mcpServers": {"mine": mine, "text-to-cad": hand},
                                              "preferences": {"x": 1, "list": [1, 2]}, "globalShortcut": "Cmd+K"})
        before = home.desktop.read_bytes()
        (step,) = home.plan()
        self.assertEqual((step.app, step.action), ("claude-desktop", "remove server"))
        self.assertEqual(step.subject, f"mcpServers.cad in {providers.shown(home.desktop, home.machine)} (text-to-cad "
                                       f"{RELEASE}): Claude gets text-to-cad as skills alone, through Claude Code's plugin")
        self.assertEqual(step.edit, {"op": "servers", "path": str(home.desktop), "remove": ["cad"]})
        self.assertFalse(providers.needs_restart(step))
        records = home.apply([step], backed_up=set())
        # Every other key and server as it was, byte for byte (Claude Desktop writes its config two-space indented),
        # the file as it was beside it.
        self.assertEqual(home.desktop.read_text(encoding="utf-8"), json.dumps(
            {"mcpServers": {"mine": mine, "text-to-cad": hand}, "preferences": {"x": 1, "list": [1, 2]},
             "globalShortcut": "Cmd+K"}, indent=2) + "\n")
        self.assertEqual(home.desktop.with_name(home.desktop.name + ".bak").read_bytes(), before)
        # Nothing to do the next time; and an uninstall has nothing of ours left to take back there.
        self.assertEqual(home.plan(), [])
        undo = providers.uninstall_plan(home.detect(), {"actions": [earlier, *records]}, machine=home.machine)
        self.assertEqual(actions(undo), [])

    def test_a_config_that_is_unreadable_or_whose_cad_is_another_server_s_is_left_alone(self) -> None:
        home = self.make()
        home.desktop.parent.mkdir(parents=True)
        for text in ('{\n  // a comment\n  "mcpServers": {"cad": {"command": "uvx", "args": ["cad-mcp"]}}\n}\n',
                     '{"mcpServers": {"cad": {"command": "node", "args": ["other.js"]}}}'):
            home.desktop.write_text(text, encoding="utf-8")
            steps = home.plan()
            self.assertFalse(any(step.changes for step in steps), steps)
            home.apply(steps)
            self.assertEqual(home.desktop.read_text(encoding="utf-8"), text)

    def test_an_uninstall_takes_back_the_server_an_earlier_release_wrote(self) -> None:
        home = self.make()
        # A config changed since loses only our server.
        record = self.earlier_install(home, {"mcpServers": {}})
        config = json.loads(home.desktop.read_text(encoding="utf-8"))
        config["mcpServers"]["mine"] = {"command": "node"}
        home.desktop.write_text(json.dumps(config), encoding="utf-8")
        undo = providers.uninstall_plan(home.detect(), {"actions": [record]}, machine=home.machine)
        self.assertEqual(actions(undo), [("claude-desktop", "remove")])
        home.apply(undo)
        self.assertEqual(json.loads(home.desktop.read_text(encoding="utf-8")), {"mcpServers": {"mine": {"command": "node"}}})
        # A file the installer made goes whole.
        home.desktop.unlink()
        record = self.earlier_install(home, None)
        self.assertTrue(record["created"])
        home.apply(providers.uninstall_plan(home.detect(), {"actions": [record]}, machine=home.machine))
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

    def test_without_claude_code_cursor_gets_a_copy_and_grok_build_its_own_and_their_updates(self) -> None:
        home = self.make(("grok",))
        (home.home / ".cursor").mkdir()
        # An earlier release's clone of `latest` in Cursor's place gives way to the copy.
        home.clone(home.cursor, "1.2.2")
        steps = home.plan()
        self.assertEqual(actions(steps), [("cursor", "remove duplicate"), ("cursor", "install"), ("grok", "install")])
        records = home.apply(steps)
        copied = sorted(path.relative_to(home.cursor).as_posix() for path in home.cursor.rglob("*") if path.is_file())
        self.assertEqual(copied, sorted([*(path.relative_to(home.folder).as_posix() for path in home.folder.rglob("*")
                                           if path.is_file()), providers.COPY_MARK]))
        self.assertFalse((home.cursor / ".git").exists())
        self.assertEqual(providers.copy_mark(home.cursor)["from"], str(home.folder))
        self.assertEqual({step.action for step in home.plan()}, {"leave"})
        home.release("1.2.4")
        (home.folder / "skills" / "dxf").mkdir()
        (home.folder / "skills" / "dxf" / "SKILL.md").write_text("---\nname: dxf\n---\n", encoding="utf-8")
        (home.folder / "skills" / "cad" / "SKILL.md").unlink()
        steps = home.plan(release="1.2.4")
        self.assertEqual([(step.app, step.action, [argv[1:] for argv in step.commands], step.edit) for step in steps],
                         [("cursor", "update", [], {"op": "copy", "from": str(home.folder), "path": str(home.cursor)}),
                          ("grok", "update", [["plugin", "update", "text-to-cad"]], None)])
        home.apply(steps)
        self.assertTrue((home.cursor / "skills" / "dxf" / "SKILL.md").is_file())
        self.assertFalse((home.cursor / "skills" / "cad" / "SKILL.md").exists(), "what the folder no longer has goes")
        self.assertEqual(home.detect()["cursor"].ours().version, "1.2.4")
        undo = providers.uninstall_plan(home.detect(), {"actions": records}, machine=home.machine, folder=home.folder)
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
        undo = providers.uninstall_plan(home.detect(), None, machine=home.machine, folder=home.folder)
        self.assertEqual([(step.app, step.action) for step in undo], [("gemini", "remove")])

    def test_a_retired_loose_skill_in_a_plugin_app_s_folder_is_deleted(self) -> None:
        home = self.make(("gemini",))
        retired = home.skill(home.home / ".gemini" / "skills", providers.RETIRED_SKILLS[0])
        (step,) = [step for step in home.plan() if step.action == "remove duplicate"]
        self.assertEqual(step.edit, {"op": "remove", "path": str(retired), "unlock": True})
        ok, (record,) = providers.apply(step, home.machine, aside=self.root / "aside")
        self.assertTrue(ok)
        self.assertFalse(retired.exists())
        self.assertFalse((self.root / "aside").exists(), "deleted, not moved aside")
        self.assertEqual(record["kind"], "remove")

    def test_a_loose_skill_moved_aside_leaves_the_skills_cli_s_record_too(self) -> None:
        # `npx skills update` installs again what its record names once the repository's skills change: a loose
        # copy from GitHub, moved aside, goes from it; one it installed from the plugin folder stays.
        home = self.make(("gemini",))
        home.machine.environ.pop("XDG_STATE_HOME", None)
        home.skill(home.home / ".gemini" / "skills")
        lock = providers.skills_lock(home.machine)
        self.assertEqual(lock, home.home / ".agents" / ".skill-lock.json")
        github = {"source": providers.REPOSITORY, "sourceType": "github", "sourceUrl": f"{providers.REPOSITORY_URL}.git",
                  "ref": "latest", "skillPath": "skills/cad/SKILL.md"}
        local = {"source": str(home.folder / "skills"), "sourceType": "local"}
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"version": 3, "skills": {"cad": github, "dxf": local}, "dismissed": {}}), encoding="utf-8")
        (step,) = [step for step in home.plan() if step.action == "remove duplicate"]
        ok, (record,) = providers.apply(step, home.machine, aside=self.root / "aside")
        self.assertTrue(ok)
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8")), {"version": 3, "skills": {"dxf": local}, "dismissed": {}})
        self.assertEqual(record["unlocked"], str(lock))


class SkillsForAgentsWithoutAPlugin(Fixture):
    """The agents the Skills CLI knows and no plugin reaches: the skills, by one ``npx skills add``."""

    def agents(self, home: Home, *names: str) -> None:
        marks = {"windsurf": ".codeium/windsurf", "goose": ".config/goose", "cline": ".cline", "github-copilot": ".copilot",
                 "droid": ".factory", "opencode": ".config/opencode"}
        for name in names:
            (home.home / marks[name]).mkdir(parents=True)

    def test_a_retired_skill_of_ours_is_deleted_and_an_uninstall_removes_one_a_later_install_left(self) -> None:
        # The Skills CLI adds skills and never removes one: what an earlier release shipped stays loaded. Nothing
        # ships it any more, so it is deleted, not moved aside, and its record from GitHub goes with it.
        home = self.make(("npx",))
        self.agents(home, "windsurf")
        home.machine.environ.pop("XDG_STATE_HOME", None)
        folder = home.home / ".codeium" / "windsurf" / "skills"
        retired = home.skill(folder, providers.RETIRED_SKILLS[0])
        lock = providers.skills_lock(home.machine)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"version": 3, "skills": {retired.name: {"source": providers.REPOSITORY,
                                                                            "sourceType": "github"}}}), encoding="utf-8")
        where = providers.shown(folder, home.machine)
        steps = home.plan()
        self.assertIn(("remove retired", f"{retired.name} in {where}: text-to-cad {RELEASE} no longer ships it"),
                      [(step.action, step.subject) for step in steps])
        (step,) = [step for step in steps if step.action == "remove retired"]
        self.assertEqual(step.edit, {"op": "remove", "path": str(retired), "unlock": True})
        ok, (record,) = providers.apply(step, home.machine, aside=self.root / "aside")
        self.assertTrue(ok)
        self.assertFalse(retired.exists())
        self.assertFalse((self.root / "aside").exists(), "deleted, not moved aside")
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["skills"], {})
        self.assertEqual((record["kind"], record["unlocked"]), ("remove", str(lock)))
        # Another's skill by that name is not ours to move.
        home.skill(folder, providers.RETIRED_SKILLS[0], ours=False)
        self.assertNotIn("remove retired", [step.action for step in home.plan()])
        providers.remove_path(folder / providers.RETIRED_SKILLS[0])
        # An uninstall takes one out directly; the Skills CLI's command names only the skills it ships.
        retired = home.skill(folder, providers.RETIRED_SKILLS[0])
        home.skill(folder, "cad")
        (step,) = providers.uninstall_plan(home.detect(), {"actions": [], "skills": {"windsurf": {}}}, machine=home.machine)
        self.assertEqual(step.commands[0][-3:], ["-s", "cad", "-y"])
        self.assertIn(str(retired), step.edit["paths"])

    def test_installed_agents_get_the_folder_s_skills_in_one_command_and_the_plugin_apps_never(self) -> None:
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
        # Each agent by name, never --all (every agent, the apps with a plugin among them).
        self.assertEqual(skills[0].commands, [[home.machine.which("npx"), *NPX, "add", str(home.folder / "skills"), "-g",
                                               "-a", "windsurf", "-a", "goose", "-s", "*", "-y", "--copy", "--json"]])
        self.assertEqual(skills[0].agents, ["windsurf", "goose"])

    def test_without_npx_each_agent_is_left_with_why(self) -> None:
        home = self.make()
        self.agents(home, "windsurf", "goose")
        self.assertEqual([(step.app, step.action, step.subject) for step in home.plan()],
                         [("windsurf", "leave", providers.NEED_NODE), ("goose", "leave", providers.NEED_NODE)])

    def test_a_loose_copy_of_ours_in_a_plugin_app_s_folder_goes_and_a_skill_only_named_like_ours_stays(self) -> None:
        home = self.make(("claude",))
        home.set(claude={"plugins": [{"id": ID, "version": RELEASE, "scope": "user"}],
                         "marketplaces": [{"name": providers.MARKETPLACE, "source": "directory", "path": str(home.folder)}]})
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

    def test_the_cli_s_universal_agents_keep_their_skills_in_the_shared_folder_and_codex_leaves_them(self) -> None:
        """GitHub Copilot, Droid and OpenCode keep `.agents/skills` in a project, so the Skills CLI copies their
        skills into `~/.agents/skills` (its `getAgentBaseDir`), never their own global folders: the folder is
        theirs, and Codex, which reads it too, never takes the skills there for its duplicates -- which moved
        them aside on every run, for the CLI to copy them back."""
        home = self.make(("codex", "npx"))
        self.agents(home, "github-copilot", "droid", "opencode")
        shared = providers.shared_skills(home.machine)
        self.assertEqual(providers.skills_agents(home.machine),
                         {"github-copilot": shared, "droid": shared, "opencode": shared})
        home.skill(shared)
        steps = home.plan()
        self.assertEqual([(step.app, step.action) for step in steps],
                         [("codex", "install"), ("github-copilot", "update"), ("droid", "update"), ("opencode", "update"),
                          ("codex", "leave")])
        self.assertEqual(steps[-1].subject, f"the skills in {providers.shown(shared, home.machine)}, GitHub Copilot, "
                                            "Droid and OpenCode's folder: Codex lists them beside its plugin's")

    def test_up_to_date_is_the_release_and_the_skills_the_cli_installed_and_the_replay_removes_them(self) -> None:
        home = self.make(("npx",))
        self.agents(home, "windsurf")
        # The CLI skips a skill (one its YAML parser refused): what it says it installed is recorded.
        skipped = [name for name in providers.SKILLS if name != "print3d"]
        home.set(skills=skipped)
        (added,) = home.apply(home.plan())
        self.assertEqual(added["skills"], skipped)
        folder = home.home / ".codeium" / "windsurf" / "skills"
        where = providers.shown(folder, home.machine)
        record = {"windsurf": {"release": RELEASE, "skills": added["skills"]}}
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record)],
                         [("leave", f"the skills in {where}, from text-to-cad {RELEASE}: up to date")])
        # A recorded skill gone, or another release: added again, said why.
        providers.remove_path(folder / "pcb")
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record)],
                         [("update", f"the skills in {where}: pcb missing")])
        self.assertEqual([(step.action, step.subject) for step in home.plan(skills=record, release="1.2.4")],
                         [("update", f"the skills in {where}, from text-to-cad {RELEASE} -> 1.2.4")])
        # The switch's refresh adds them again for a release, for the agents the receipt names alone.
        self.assertEqual(actions(providers.refresh_plan(home.detect(), release="1.2.4", folder=home.folder,
                                                        machine=home.machine, skills=record)), [("windsurf", "update")])
        (step,) = providers.uninstall_plan(home.detect(), {"actions": [], "skills": record}, machine=home.machine)
        self.assertEqual(step.commands, [[home.machine.which("npx"), *NPX, "remove", "-g", "-a", "windsurf",
                                          "-s", *sorted(name for name in skipped if name != "pcb"), "-y"]])
        home.apply([step])
        self.assertEqual(providers.ours_in(folder), [])


class TheCopy(unittest.TestCase):
    def test_a_copy_is_real_files_written_again_in_place_and_marked(self) -> None:
        with temporary_directory(prefix="providers-copy-") as scratch:
            root = Path(scratch)
            source = make_plugin_folder(root / "plugin", RELEASE)
            target = root / "copy"
            (target / "skills" / "old").mkdir(parents=True)
            (target / "skills" / "old" / "SKILL.md").write_text("an old skill", encoding="utf-8")
            if os.name != "nt":
                (target / "skills" / "cad").mkdir()
                (target / "skills" / "cad" / "SKILL.md").symlink_to(source / "skills" / "cad" / "SKILL.md")
            mark = providers.copy_plugin(source, target)
            self.assertEqual((mark["from"], mark["version"]), (str(source), RELEASE))
            files = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
            self.assertEqual(files, sorted([*(path.relative_to(source).as_posix() for path in source.rglob("*")
                                              if path.is_file()), providers.COPY_MARK]))
            self.assertFalse([path for path in target.rglob("*") if path.is_symlink()])
            self.assertEqual(providers.copy_mark(target)["from"], str(source))


class CursorStoreVersion(unittest.TestCase):
    def test_a_folder_that_cannot_be_listed_or_read_names_no_version_and_never_fails_detection(self) -> None:
        with temporary_directory(prefix="providers-cursor-") as scratch:
            store = Path(scratch) / "store"
            (store / "abc123" / ".cursor-plugin").mkdir(parents=True)
            (store / "abc123" / ".cursor-plugin" / "plugin.json").write_text('{"version": "0.11.11"}', encoding="utf-8")
            self.assertEqual(providers._cursor_store_version(store), "0.11.11")
            real = Path.stat

            def removed(path, *args, **kwargs):  # the commit's folder removed between its listing and its look
                if path.name == "abc123":
                    raise FileNotFoundError(2, "No such file or directory")
                return real(path, *args, **kwargs)

            for patched, replacement in (("iterdir", mock.Mock(side_effect=PermissionError(13, "Permission denied"))),
                                         ("stat", removed)):
                with self.subTest(patched=patched), mock.patch.object(Path, patched, replacement):
                    self.assertIsNone(providers._cursor_store_version(store))


if __name__ == "__main__":
    unittest.main()
