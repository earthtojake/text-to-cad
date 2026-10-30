#!/usr/bin/env python3
"""Install this checkout into an agent app, to test the plugin locally.

Each host gets the development plugin, text-to-cad@earthtojake-dev: this checkout's skills, and
CAD's server run by this checkout's .venv (`cadgen mcp`), serving a copy of this checkout's
apps/mcp build. That .venv is registered as this install's version (<version>-dev.<time>), the
skills run `cadgen +<version>-dev.<time>` and the `cadgen` command is written (~/.local/bin/cadgen), so
the server and the agent's scripts share this checkout's installation and warm daemon -- and every
worktree has its own. With --wheel, the checkout's wheel is built as the release builds it, the
server runs it through uvx and that installation is the one registered: the shape users get. Claude Desktop's chat takes servers, not plugins, so it
gets that server alone. Run it again after a change; --uninstall takes the install out. For an agent without plugins,
install the skills alone from the checkout with the Skills CLI: `npx skills add . -g -a <agent>`.

One copy per app: a host that already loads another copy (the published plugin, this one through
another host, or this repository's skills installed loose) is refused, because two copies means
every skill twice. Cursor and Grok Build both load the plugins Claude Code installed, so `claude`
covers all three. How each app is read -- its commands, its config files, every copy of the plugin
it loads -- is cadgen's own (cadgen/_internal/providers.py, loaded by its path), which `cadgen
setup` reads the apps with too.

    scripts/install/dev_install.py claude              # Claude Code (and so Cursor and Grok Build)
    scripts/install/dev_install.py codex [--restart]   # the Codex app, CLI and IDE extension
    scripts/install/dev_install.py cursor              # Cursor, without Claude Code
    scripts/install/dev_install.py grok                # Grok Build, without Claude Code
    scripts/install/dev_install.py gemini              # Gemini CLI
    scripts/install/dev_install.py claude-desktop      # Claude Desktop's chat: the server alone
    scripts/install/dev_install.py <host> --wheel        # this checkout's wheel, run through uvx
    scripts/install/dev_install.py <host> --uninstall

The page is a copy taken at install, as an installed wheel serves its own: a page that changed
under a running app would change its URI, and hosts drop the frames already showing it. So
install again to see a page edit, and restart the app after a Python change -- a running server
keeps the code it started with.

Environment:
    CADGEN_PYTHON           the interpreter that runs the server (default: the checkout's .venv)
    CODEX_CLI               the codex CLI (default: the newer of `codex` on PATH and the Codex app's)
    GEMINI_CLI              the gemini CLI (default: `gemini` on PATH)
    CLAUDE_DESKTOP_CONFIG   Claude Desktop's config file (default: its own, per platform)
    CADGEN_LAUNCHER_DIR     where the `cadgen` command goes (default: ~/.local/bin)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]


def _shared_providers():
    """cadgen's agent-app providers (``cadgen._internal.providers``), loaded by its path: this script
    runs on any Python 3 and must not import cadgen, whose floor is newer, and that module imports
    nothing of cadgen, so both installers read the apps one way."""
    path = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "_internal" / "providers.py"
    spec = importlib.util.spec_from_file_location("text_to_cad_providers", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


providers = _shared_providers()
# cadgen._internal.launch.LAUNCHER, repeated because this script runs on any Python 3 and must
# not import cadgen, whose floor is newer; test_dev_install holds the two equal.
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.13", "--from")
# cadgen.updates.INSTALL and INSTALL_WINDOWS, the install command, repeated for the same reason: a
# development install's skills never send an agent to the release's installer, which would put the
# published release over this checkout's engine.
INSTALL_COMMANDS = ("curl -fsSL https://texttocad.dev/install.sh | sh", "irm https://www.texttocad.dev/install.ps1 | iex")
MARKETPLACE = providers.DEV_MARKETPLACE
PLUGIN_HOSTS = ("claude", "codex", "cursor", "grok", "gemini")
HOSTS = (*PLUGIN_HOSTS, "claude-desktop")
DESKTOP_SERVER = "cad-dev"
CURSOR_PLUGINS = providers.cursor_plugins()
# Written into the Cursor plugin folder, so --uninstall and a reinstall only ever touch our own.
OWNER_MARK = providers.DEV_MARK
# Every SKILL.md of this repository's says where it is maintained; a loose skill saying so is ours.
PROVENANCE = providers.PROVENANCE
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
# A Codex thread waits this long for the server's first start, which may build the page's data.
CODEX_STARTUP_SECONDS = 30
PAGE_COPY_DAYS = 1


class Refused(Exception):
    """The install would leave the app in a state we never want; the message says why."""


def plugin_name(root: Path = REPO_ROOT) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]


def dev_root(host: str, root: Path = REPO_ROOT) -> Path:
    return root / "tmp" / f"{host}-dev"


# A development install's channel, in its server's environment (cadgen's _internal/channel.py): its
# analytics are told apart, and it is never offered an update.
CHANNEL = {"CADGEN_INSTALL_CHANNEL": "dev"}


def server_entry(host: str, python: str, page_dir: Path, version: str | None = None) -> dict:
    """CAD's server for a development install: this checkout's interpreter, this install's page, and
    the version it registers as at each start, `version` (cadgen's _internal/installations.py; a
    source tree registers none unless named)."""
    entry = {"command": python, "args": ["-m", "cadgen.cli", "mcp"], "env": {**CHANNEL, "CADGEN_MCP_APP_DIR": str(page_dir)}}
    if version:
        entry["env"][VERSION_ENV] = version
    if host == "codex":
        entry["startup_timeout_sec"] = CODEX_STARTUP_SECONDS
    return entry


# The variable that names the version a development install registers as (cadgen's
# _internal/installations.py NAME_ENV).
VERSION_ENV = "CADGEN_INSTALLATION_VERSION"


def launch(tool: str, version: str) -> str:
    """The uvx command for ``tool`` (``cadgen`` or ``python``), as the release stamps it in the skills."""
    return " ".join((*LAUNCHER, f"cadgen=={version}", tool))


def launcher_dir() -> str:
    """The `cadgen` command's folder as a skill names it: ``~/.local/bin`` unless CADGEN_LAUNCHER_DIR moves it."""
    return os.environ.get("CADGEN_LAUNCHER_DIR") or "~/.local/bin"


# Registers this install and writes the `cadgen` command through its own cadgen (this script cannot
# import it), printing the record's file.
REGISTER = ("import sys\n"
            "from cadgen._internal import installations\n"
            "(record, _, failed), (_, _, unwritten) = installations.setup(sys.argv[1])\n"
            "print(record)\n"
            "sys.exit('; '.join(error for error in (failed, unwritten) if error) or 0)\n")


def register(host: str, python: list[str], version: str) -> None:
    """Register this install as `version` by `python` (its interpreter, or the uvx command that runs
    the wheel's), write the `cadgen` command, and take out the records of this host's installs
    before it that are over a day old: a Codex thread started earlier may still run its own."""
    record = dev_root(host) / "installations.json"
    try:
        earlier = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        earlier = {}
    stale = time.time() - PAGE_COPY_DAYS * 86400
    for old_version, path in list(earlier.items()):
        if old_version != version and _older(path, stale):
            Path(path).unlink(missing_ok=True)
            del earlier[old_version]
    written = run(*python, "-c", REGISTER, version, capture=True).strip().splitlines()[-1]
    write_json(record, {**earlier, version: written})


def _older(path: str, than: float) -> bool:
    try:
        return os.lstat(path).st_mtime < than
    except OSError:
        return True


def unregister(host: str) -> None:
    """Take out the record of every install of this host's (the `cadgen` command stays: it is every
    installation's)."""
    try:
        recorded = json.loads((dev_root(host) / "installations.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for path in recorded.values():
        Path(path).unlink(missing_ok=True)


def skill_rewrites(released: str, version: str, python: str | None = None, wheel: Path | None = None) -> dict:
    """What a development install changes in its skills' text, ``{release's: this install's}``: the
    version they run (``cadgen +<version>``, ``cadgen.cmd +<version>``) is this install's, the `cadgen`
    command's folder is CADGEN_LAUNCHER_DIR's, the install command becomes the checkout's interpreter
    (the .venv shape) or the wheel through uvx (--wheel), told that version so its `cadgen doctor`
    registers it (Windows shells take no such prefix), and the one-line installer
    (``INSTALL_COMMANDS``) becomes a note that this is a development install."""
    named = "" if os.name == "nt" else f"{VERSION_ENV}={version} "
    command = " ".join((*LAUNCHER, str(wheel), "cadgen")) if wheel is not None else f"{python} -m cadgen.cli"
    rewrites = {launch("cadgen", released): f"{named}{command}", f"cadgen +{released}": f"cadgen +{version}",
                f"cadgen.cmd +{released}": f"cadgen.cmd +{version}",
                f"it says {released} is not installed": f"it says {version} is not installed"}
    note = f"This is a development install of {REPO_ROOT}; do not run the install command here"
    # The macOS and Linux command stands alone in a shell block: there the note is a comment.
    rewrites.update({INSTALL_COMMANDS[0]: f"# {note}", INSTALL_COMMANDS[1]: note})
    if launcher_dir() != "~/.local/bin":
        rewrites["~/.local/bin"] = launcher_dir()
    return rewrites


def assemble(host: str, plugin_dir: Path, version: str, server: dict, root: Path = REPO_ROOT,
             rewrites: dict | None = None) -> dict:
    """Write the plugin `host` loads into `plugin_dir` and return its manifest.

    The skills are copied with ``rewrites`` applied (:func:`skill_rewrites`: the runtime the server
    uses), the host's manifest takes `version` (each install its own, so a host that caches by
    version takes this build) and names `server` alone: in a server config beside it, or, for
    Gemini, which keeps servers in the manifest itself, inline.
    """
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    shutil.copytree(root / "skills", plugin_dir / "skills", ignore=IGNORED)
    # A skill's main file and its setup guide carry the runtime; a migration reference may name an
    # old release on purpose, and is copied as it is.
    for skill in plugin_dir.glob("skills/*/SKILL.md"):
        for document in (skill, skill.parent / "references" / "setup.md"):
            if not document.is_file():
                continue
            text = document.read_text(encoding="utf-8")
            for released, ours in (rewrites or {}).items():
                text = text.replace(released, ours)
            document.write_text(text, encoding="utf-8")
    if host == "gemini":
        manifest = json.loads((root / "gemini-extension.json").read_text(encoding="utf-8"))
        manifest["version"] = version
        manifest["mcpServers"] = {"cad": server}
        write_json(plugin_dir / "gemini-extension.json", manifest)
        return manifest
    manifest_dir = {"codex": ".codex-plugin", "cursor": ".cursor-plugin"}.get(host, ".claude-plugin")
    servers_file = "codex.mcp.json" if host == "codex" else "claude.mcp.json"
    manifest = json.loads((root / manifest_dir / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["mcpServers"] = f"./{servers_file}"
    (plugin_dir / manifest_dir).mkdir(parents=True)
    # The manifest's own files (icons), beside it; never a marketplace catalog.
    for path in (root / manifest_dir).iterdir():
        if path.is_file() and path.name not in ("plugin.json", "marketplace.json"):
            shutil.copy2(path, plugin_dir / manifest_dir / path.name)
    if host == "cursor" and manifest.get("logo"):
        # Cursor's logo is a path inside the plugin; ours is the Claude icon.
        logo = plugin_dir / manifest["logo"]
        logo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / manifest["logo"], logo)
    write_json(plugin_dir / manifest_dir / "plugin.json", manifest)
    write_json(plugin_dir / servers_file, {"mcpServers": {"cad": server}})
    return manifest


# This repository's skills installed loose (by the Skills CLI, or linked by hand), the folders each
# host loads skills from, and the atomic JSON write: the providers'.
loose_skills = providers.loose_skills
write_json = providers.write_json


def skill_folders(host: str) -> list[Path]:
    """The user-level skill folders `host` loads skills from, as each app was seen to."""
    return providers.skill_folders(host)


def run(*command: str, capture: bool = False, answer: str | None = None) -> str:
    """Run a CLI; with `capture`, return what it printed and keep its chatter off the terminal."""
    pipe = subprocess.PIPE if capture else None
    result = subprocess.run(command, check=True, text=True, input=answer, stdout=pipe, stderr=pipe)
    return result.stdout if capture else ""


def cli(name: str, hint: str = "") -> str:
    found = providers.find_cli(name)
    if not found:
        raise Refused(f"No `{name}` on PATH{hint}.")
    return found


def codex_cli() -> str:
    """CODEX_CLI, else the newer of `codex` on PATH and the one the Codex app bundles
    (``providers.codex_cli``): the install must come from a CLI at least as new as the app."""
    found = providers.codex_cli()
    if not found:
        raise Refused("No working codex CLI; install Codex or set CODEX_CLI.")
    return found


def interpreter() -> str:
    default = REPO_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = os.environ.get("CADGEN_PYTHON") or str(default)
    check = ("import pathlib, sys\n"
             "import cadgen.mcp.server  # the server must import\n"
             "import cadgen\n"
             "root = pathlib.Path(sys.argv[1]).resolve()\n"
             "if root not in pathlib.Path(cadgen.__file__).resolve().parents:\n"
             "    sys.exit(f'{sys.executable} imports cadgen from {cadgen.__file__}, not from {root}')\n")
    if subprocess.run([python, "-c", check, str(REPO_ROOT)]).returncode != 0:
        raise Refused(f"{python} cannot run this checkout's server; install requirements-dev.txt into .venv "
                      "or set CADGEN_PYTHON.")
    return python


def copy_page(host: str, build: bool, version: str, prune: bool = True) -> Path:
    """This install's copy of the built page. Servers still running an earlier install read their own."""
    if build:
        subprocess.run(["npm", "run", "build:mcp"], cwd=REPO_ROOT, check=True)
    page = REPO_ROOT / "apps" / "mcp" / "dist" / "index.html"
    if not page.is_file():
        raise Refused("apps/mcp is not built; run without --no-build.")
    pages = dev_root(host) / "app"
    page_dir = pages / version
    page_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(page, page_dir / "index.html")
    if prune:
        stale = time.time() - PAGE_COPY_DAYS * 86400
        for old in pages.iterdir():
            if old != page_dir and old.stat().st_mtime < stale:
                shutil.rmtree(old, ignore_errors=True)
    return page_dir


def build_wheel(host: str, bundle: bool) -> Path:
    """This checkout's wheel, built as the release builds it, at a path of its own per build.

    uv keeps one installation per requirement, so a wheel at a new path is a new installation --
    and a warm daemon of its own -- never the previous build's, nor another worktree's.
    """
    uv = cli("uv", "; install uv: https://docs.astral.sh/uv/")
    if bundle:
        subprocess.run([str(REPO_ROOT / "scripts" / "bundle" / "bundle.sh")], cwd=REPO_ROOT, check=True)
    wheels = dev_root(host) / "wheels"
    out = wheels / time.strftime("%Y%m%d%H%M%S")
    run(uv, "build", "--wheel", "--out-dir", str(out), str(REPO_ROOT / "packages" / "cadgen"))
    built = sorted(out.glob("cadgen-*.whl"))
    if not built:
        raise Refused(f"uv build wrote no cadgen wheel to {out}.")
    # A server already running keeps the installation it started from; only new starts read the
    # wheel, and they read this one.
    for old in wheels.iterdir():
        if old != out:
            shutil.rmtree(old, ignore_errors=True)
    return built[0]


def runtime(host: str, args: argparse.Namespace, version: str) -> tuple[dict, dict, Path | None]:
    """``(server, skill rewrites, page copy)`` for this install: the .venv, or with --wheel the wheel.

    Either way the installation is registered as `version` and the `cadgen` command written before
    the app restarts, by that installation's own interpreter; its server registers it again at each
    start.
    """
    released = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if args.wheel:
        wheel = build_wheel(host, args.build)
        server = {"command": LAUNCHER[0], "args": [*LAUNCHER[1:], str(wheel), "cadgen", "mcp"], "env": dict(CHANNEL)}
        if host == "codex":
            server["startup_timeout_sec"] = CODEX_STARTUP_SECONDS
        if host not in PLUGIN_HOSTS:  # Claude Desktop's chat runs no skills
            return server, {}, None
        server["env"][VERSION_ENV] = version
        register(host, [*LAUNCHER, str(wheel), "python"], version)
        return server, skill_rewrites(released, version, wheel=wheel), None
    python = interpreter()
    # Codex keeps an earlier install's server running until it restarts, so its page stays too.
    page_dir = copy_page(host, args.build, version, prune=host != "codex")
    if host not in PLUGIN_HOSTS:  # Claude Desktop's chat runs no skills
        return server_entry(host, python, page_dir), {}, page_dir
    register(host, [python], version)
    return server_entry(host, python, page_dir, version), skill_rewrites(released, version, python=python), page_dir


def dev_version() -> str:
    return f"{(REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()}-dev.{time.strftime('%Y%m%d%H%M%S')}"


def claude_installed() -> list[str]:
    """The plugin ids Claude Code has installed for this plugin, any marketplace."""
    return providers.claude_installed(name=plugin_name())


def grok_installed() -> list[str]:
    """Where each of Grok Build's installs of this plugin came from."""
    return providers.grok_installed(name=plugin_name())


def gemini_installed(gemini: str) -> list[str]:
    """Where each of Gemini CLI's installs of this extension came from (`Source:` in its list)."""
    return providers.gemini_installed(gemini, name=plugin_name())


def cursor_installed() -> list[Path]:
    """Cursor's local plugin folders that hold this plugin."""
    return providers.cursor_installed(name=plugin_name())


def refuse_other_copies(host: str) -> None:
    """Refuse when an app this host feeds already loads another copy of the plugin or its skills."""
    dev_id = f"{plugin_name()}@{MARKETPLACE}"
    others = [f"loose skills: {path}" for path in loose_skills(skill_folders(host))]
    if host in ("claude", "cursor", "grok"):
        # Cursor and Grok Build load Claude Code's plugins as well as their own.
        others += [f"Claude Code: {plugin_id}" for plugin_id in claude_installed()
                   if not (host == "claude" and plugin_id == dev_id)]
    if host in ("claude", "cursor"):
        others += [f"Cursor: {folder}" for folder in cursor_installed()
                   if not (host == "cursor" and (folder / OWNER_MARK).is_file())]
    if host in ("claude", "grok"):
        others += [f"Grok Build: {source}" for source in grok_installed()
                   if not (host == "grok" and Path(source) == dev_root("grok") / "plugins" / plugin_name())]
    if others:
        raise Refused("Another copy of the plugin is installed where this one would load:\n  "
                      + "\n  ".join(others) + "\nUninstall it first: two copies means every skill twice "
                      "(`npx skills remove -g <skill>` for loose skills).")


def install_codex(args: argparse.Namespace) -> str:
    codex = codex_cli()
    name = plugin_name()
    dev_id = f"{name}@{MARKETPLACE}"
    root = dev_root("codex")

    def installed() -> list[str]:
        plugins = json.loads(run(codex, "plugin", "list", "--json", capture=True)).get("installed", [])
        return [plugin["pluginId"] for plugin in plugins if plugin.get("name") == name]

    def marketplace_known() -> bool:
        listing = run(codex, "plugin", "marketplace", "list", capture=True)
        return MARKETPLACE in (line.split()[0] for line in listing.splitlines() if line.split())

    if args.uninstall:
        if dev_id in installed():
            run(codex, "plugin", "remove", dev_id)
        if marketplace_known():
            run(codex, "plugin", "marketplace", "remove", MARKETPLACE)
        unregister("codex")
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {dev_id}."
    others = [plugin_id for plugin_id in installed() if plugin_id != dev_id]
    if others:
        raise Refused(f"Another CAD plugin is installed: {', '.join(others)}\n"
                      "Remove it first (codex plugin remove <id>); two copies means every skill twice.")
    refuse_other_copies("codex")
    version = dev_version()
    server, rewrites, page_dir = runtime("codex", args, version)
    assemble("codex", root / "plugins" / name, version, server, rewrites=rewrites)
    write_json(root / ".agents" / "plugins" / "marketplace.json", {
        "name": MARKETPLACE, "interface": {"displayName": "CAD (this checkout)"},
        "plugins": [{"name": name, "source": {"source": "local", "path": f"./plugins/{name}"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "Productivity"}]})
    if not marketplace_known():
        run(codex, "plugin", "marketplace", "add", str(root))
    run(codex, "plugin", "add", dev_id)
    if args.restart:
        subprocess.run(["osascript", "-e", 'quit app "ChatGPT"'], capture_output=True)
        for _ in range(50):
            if subprocess.run(["pgrep", "-xq", "ChatGPT"]).returncode != 0:
                break
            time.sleep(0.2)
        # No server of an earlier install survives the restart, so neither need its page.
        for old in (root / "app").iterdir() if (root / "app").is_dir() else ():
            if old != page_dir:
                shutil.rmtree(old, ignore_errors=True)
        subprocess.run(["open", "-a", "ChatGPT"], check=True)
    return f"Installed {dev_id} {version}. New threads run this build{'' if args.restart else ' after Codex restarts'}."


def install_claude(args: argparse.Namespace) -> str:
    claude = cli("claude")
    name = plugin_name()
    dev_id = f"{name}@{MARKETPLACE}"
    root = dev_root("claude")
    marketplaces = {entry["name"] for entry in json.loads(run(claude, "plugin", "marketplace", "list", "--json",
                                                                capture=True) or "[]")}
    if args.uninstall:
        if dev_id in claude_installed():
            run(claude, "plugin", "uninstall", dev_id)
        if MARKETPLACE in marketplaces:
            run(claude, "plugin", "marketplace", "remove", MARKETPLACE)
        unregister("claude")
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {dev_id}."
    refuse_other_copies("claude")
    version = dev_version()
    server, rewrites, _ = runtime("claude", args, version)
    assemble("claude", root / "plugins" / name, version, server, rewrites=rewrites)
    write_json(root / ".claude-plugin" / "marketplace.json", {
        "name": MARKETPLACE, "owner": {"name": "this checkout"},
        "description": f"{name} from {REPO_ROOT}, for development",
        "plugins": [{"name": name, "source": f"./plugins/{name}", "version": version}]})
    run(claude, "plugin", "marketplace", *(("update", MARKETPLACE) if MARKETPLACE in marketplaces
                                           else ("add", str(root))))
    # A new version each install, so `update` re-copies the plugin into Claude Code's cache.
    run(claude, "plugin", "update" if dev_id in claude_installed() else "install", dev_id)
    return (f"Installed {dev_id} {version}. Claude Code sessions, Cursor and Grok Build load it; "
            "restart one already running to pick up a new build.")


def install_cursor(args: argparse.Namespace) -> str:
    name = plugin_name()
    target = CURSOR_PLUGINS / f"{name}-dev"
    if target.exists() and not (target / OWNER_MARK).is_file():
        raise Refused(f"{target} exists and is not this script's install; move it away first.")
    if args.uninstall:
        shutil.rmtree(target, ignore_errors=True)
        unregister("cursor")
        shutil.rmtree(dev_root("cursor"), ignore_errors=True)
        return f"Removed {target}."
    refuse_other_copies("cursor")
    version = dev_version()
    server, rewrites, _ = runtime("cursor", args, version)
    # Cursor follows no symlink out of its plugins folder, so the plugin is a real copy there.
    staged = dev_root("cursor") / "plugins" / name
    assemble("cursor", staged, version, server, rewrites=rewrites)
    (staged / OWNER_MARK).write_text(f"{REPO_ROOT}\n", encoding="utf-8")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(staged, target)
    return f"Installed {name} {version} at {target}. Cursor reloads its plugins when that folder changes."


def install_grok(args: argparse.Namespace) -> str:
    grok = cli("grok")
    name = plugin_name()
    root = dev_root("grok")
    plugin_dir = root / "plugins" / name
    if args.uninstall:
        if str(plugin_dir) in grok_installed():
            run(grok, "plugin", "uninstall", name)
        unregister("grok")
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {name} from Grok Build."
    refuse_other_copies("grok")
    version = dev_version()
    server, rewrites, _ = runtime("grok", args, version)
    assemble("grok", plugin_dir, version, server, rewrites=rewrites)
    if str(plugin_dir) in grok_installed():
        run(grok, "plugin", "uninstall", name)
    run(grok, "plugin", "install", str(plugin_dir), "--trust")
    return f"Installed {name} {version} in Grok Build; start a new session to load it."


def install_gemini(args: argparse.Namespace) -> str:
    gemini = cli("gemini", "; install Gemini CLI (npm install -g @google/gemini-cli) or set GEMINI_CLI")
    name = plugin_name()
    # Gemini expects the extension's folder to bear its name.
    plugin_dir = dev_root("gemini") / "plugins" / name
    linked = str(plugin_dir) in gemini_installed(gemini)
    if args.uninstall:
        if linked:
            run(gemini, "extensions", "uninstall", name)
        unregister("gemini")
        shutil.rmtree(dev_root("gemini"), ignore_errors=True)
        return f"Removed {name} from Gemini CLI."
    others = [source for source in gemini_installed(gemini) if source != str(plugin_dir)]
    if others:
        raise Refused(f"Gemini CLI already has {name} from {', '.join(others)}; uninstall it first "
                      f"(gemini extensions uninstall {name}): two copies means every skill twice.")
    refuse_other_copies("gemini")
    version = dev_version()
    server, rewrites, _ = runtime("gemini", args, version)
    assemble("gemini", plugin_dir, version, server, rewrites=rewrites)
    if not linked:
        # A link reads the folder in place, so a later install only rewrites it. Gemini asks whether
        # to trust the folder even with --consent; this is the folder we just wrote.
        run(gemini, "extensions", "link", str(plugin_dir), "--consent", answer="y\n")
    return f"Installed {name} {version} in Gemini CLI; start a new session to load it."


def desktop_config() -> Path:
    """Claude Desktop's config file: CLAUDE_DESKTOP_CONFIG, else its own, per platform."""
    return providers.desktop_config()


def install_claude_desktop(args: argparse.Namespace) -> str:
    path = desktop_config()
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    config = json.loads(text) if text else {}
    servers = config.setdefault("mcpServers", {})
    if args.uninstall:
        servers.pop(DESKTOP_SERVER, None)
        write_json(path, config)
        shutil.rmtree(dev_root("claude-desktop"), ignore_errors=True)
        return f"Removed {DESKTOP_SERVER} from {path}. Restart Claude Desktop to drop it."
    others = [key for key, entry in servers.items()
              if key != DESKTOP_SERVER and "cadgen" in " ".join([entry.get("command", ""), *entry.get("args", [])])]
    if others:
        raise Refused(f"{path} already runs CAD's server as {', '.join(others)}; remove that entry first: "
                      "two servers means every tool twice.")
    servers[DESKTOP_SERVER] = runtime("claude-desktop", args, time.strftime("%Y%m%d%H%M%S"))[0]
    write_json(path, config)
    return (f"Added {DESKTOP_SERVER} to {path}. Restart Claude Desktop (or Developer > Reload MCP "
            "Configuration) to load it.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 1)[1])
    parser.add_argument("host", choices=HOSTS)
    parser.add_argument("--uninstall", action="store_true", help="take this host's install out")
    parser.add_argument("--no-build", dest="build", action="store_false", help="serve the page already built")
    parser.add_argument("--restart", action="store_true", help="codex: quit and reopen the app")
    parser.add_argument("--wheel", action="store_true", help="build this checkout's wheel and run it through uvx")
    args = parser.parse_args(argv)
    if args.restart and args.host != "codex":
        parser.error("--restart is for codex")
    install = {"claude": install_claude, "codex": install_codex, "cursor": install_cursor, "grok": install_grok,
               "gemini": install_gemini, "claude-desktop": install_claude_desktop}[args.host]
    try:
        print(install(args))
        return 0
    except Refused as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"error: {' '.join(map(str, error.cmd))} exited {error.returncode}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
