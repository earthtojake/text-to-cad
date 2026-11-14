#!/usr/bin/env python3
"""Install this checkout into an agent app, to test the plugin locally.

Each host gets the development plugin, text-to-cad@earthtojake-dev: this checkout's skills, and
CAD's server run by this checkout's .venv (`cad-mcp`), serving a copy of this checkout's
apps/mcp build. That .venv is installed as a version of its own, named <VERSION>-dev.<time>
(versions/<name>, whose code marker names the .venv: nothing is copied), the device's default
channel is moved to it (`versions.move`: its data imported from the version it replaces, the
pointer, the mirror for 0.11.10 and earlier), and the `cad` command is written (~/.local/bin/cad).
Every command in the copied skills pins that name (`cad +<name>`), so the skills, the server and
the agent's scripts run this checkout's version and share its warm server. Name every host you
test in one run (`dev_install.py claude codex`): each run is a new version, and moving the
default channel to it leaves the skills of a host installed by an earlier run pinned to a version
the channel has left (they say so; install that host again). With --wheel, the checkout's wheels
are built as the release builds them, the server runs them through uvx and that installation is
the version: the shape users get. Claude gets no CAD server, as from the release: Claude Code's
plugin is the skills alone (Cursor and Grok Build, which load it, read their own manifests, which
name the server), and `claude-desktop` only takes out the server an earlier development install
wrote into Claude Desktop's config. Run it again after a change.

Going back to the published release is the install command (`curl -fsSL
https://texttocad.dev/install.sh | sh`): it installs the release, moves the default channel to it
from the development version (a person's install goes back from a development version, which no
pinned command does), gives every app its plugin and takes the development plugin out of each as a
second copy. The development version's folder stays, with its data: a release never imports from a
newer version, and the move to the development version carried the device's Recents and settings
into it, so the release shows none of them until the next development install carries them on.
--uninstall takes a host's install out alone. For an agent without plugins, install the skills alone from the
checkout with the Skills CLI: `npx skills add . -g -a <agent>`.

One copy per app: a host that already loads another copy (the published plugin, this one through
another host, or this repository's skills installed loose) is refused, because two copies means
every skill twice. Cursor and Grok Build both load the plugins Claude Code installed, so `claude`
covers all three. How each app is read -- its commands, its config files, every copy of the plugin
it loads -- is the server's own (cad_server/_internal/providers.py, loaded by its path), which `cad
setup` reads the apps with too.

    scripts/install/dev_install.py claude              # Claude Code (and so Cursor and Grok Build)
    scripts/install/dev_install.py claude codex        # several hosts, one version
    scripts/install/dev_install.py codex [--restart]   # the Codex app, CLI and IDE extension
    scripts/install/dev_install.py cursor              # Cursor, without Claude Code
    scripts/install/dev_install.py grok                # Grok Build, without Claude Code
    scripts/install/dev_install.py gemini              # Gemini CLI
    scripts/install/dev_install.py claude-desktop      # Claude Desktop: an earlier install's server taken out
    scripts/install/dev_install.py <host> --wheel        # this checkout's wheels, run through uvx
    scripts/install/dev_install.py <host> --uninstall

The page is a copy taken at install, as an installed wheel serves its own: a page that changed
under a running app would change its URI, and hosts drop the frames already showing it. So
install again to see a page edit, and run `cad stop` after a Python change -- a running server
keeps the code it started with, and outlives the app.

Environment:
    CAD_PYTHON           the interpreter that runs the server (default: the checkout's .venv)
    CODEX_CLI               the codex CLI (default: the newer of `codex` on PATH and the Codex app's)
    GEMINI_CLI              the gemini CLI (default: `gemini` on PATH)
    CLAUDE_DESKTOP_CONFIG   Claude Desktop's config file (default: its own, per platform)
    CAD_LAUNCHER_DIR     where the `cad` command goes (default: ~/.local/bin)
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
    """The server's agent-app providers (``cad_server._internal.providers``), loaded by its path: this script
    runs on any Python 3 and must not import the packages, whose floor is newer, and that module imports
    nothing of them, so both installers read the apps one way."""
    path = REPO_ROOT / "packages" / "cad-server" / "src" / "cad_server" / "_internal" / "providers.py"
    spec = importlib.util.spec_from_file_location("text_to_cad_providers", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


providers = _shared_providers()
# cad_server._internal.launch.LAUNCHER, repeated because this script runs on any Python 3 and must
# not import the packages, whose floor is newer; test_dev_install holds the two equal.
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.14", "--from")
# cad_server.updates.INSTALL and INSTALL_WINDOWS, the install command, repeated for the same reason: a
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
# Every SKILL.md of this repository's names it; a loose skill naming it is ours.
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


def server_entry(host: str, python: str, page_dir: Path, version: str | None = None) -> dict:
    """CAD's server for a development install: this checkout's interpreter, this install's page, and
    the version it registers as at each start, `version` (cadgen's _internal/installations.py; a
    source tree registers none unless named). Its name, `<VERSION>-dev.<time>`, is what makes it a development
    build to the server (the server's _internal/channel.py): it sends no telemetry by default and hears of no
    release. Nothing names a channel: the default channel is moved to it."""
    entry = {"command": python, "args": ["-m", "cad_mcp"], "env": {"CAD_MCP_APP_DIR": str(page_dir)}}
    if version:
        entry["env"][VERSION_ENV] = version
    if host == "codex":
        entry["startup_timeout_sec"] = CODEX_STARTUP_SECONDS
    return entry


# The variable that names the version a development install registers as (cadgen's
# _internal/installations.py NAME_ENV).
VERSION_ENV = "CAD_INSTALLATION_VERSION"


def launcher_dir() -> str:
    """The `cad` command's folder as a skill names it: ``~/.local/bin`` unless CAD_LAUNCHER_DIR moves it."""
    return os.environ.get("CAD_LAUNCHER_DIR") or "~/.local/bin"


# Installs this install as a version of its own, named by the first argument, and moves the device's default
# channel to it -- the version every client and the `cad` command run with no pin, so the apps run this checkout --,
# and writes the `cad` command, through its own cadgen (this script cannot import it), printing what it did as JSON:
# the version and the one the default channel was on before. The code marker names the environment that runs this
# (the .venv, or the wheel's uvx environment): nothing is copied. A checkout older than the release the default
# channel is on moves it all the same: a development install goes over it.
INSTALL_VERSION = ("import json, sys\n"
                   "from pathlib import Path\n"
                   "from cad_server._internal import installations, pointers, releases, versions\n"
                   "name = sys.argv[1]\n"
                   "before = pointers.read(None)\n"
                   "said = lambda line: print(line, file=sys.stderr)\n"
                   "versions.development(name, sys.executable, str(releases.console(Path(sys.prefix))), sys.prefix)\n"
                   "moved = versions.move(None, name, told=said)\n"
                   "if moved.kind == 'stale':\n"
                   "    versions.first_start(name, told=said)\n"
                   "    pointers.write(None, name)\n"
                   "    versions.sweep(told=said)\n"
                   "elif not moved.ok:\n"
                   "    sys.exit(moved.error)\n"
                   "_path, _status, unwritten = installations.write_proxy()\n"
                   "print(json.dumps({'version': name, 'before': before}))\n"
                   "sys.exit(unwritten or 0)\n")

def register(python: list[str], version: str) -> dict:
    """Install this install as `version` by `python` (its interpreter, or the uvx command that runs the wheel's)
    and move the default channel to it (``INSTALL_VERSION``), writing the `cad` command: what it said, the version
    and the one the default channel was on before."""
    return json.loads(run(*python, "-c", INSTALL_VERSION, version, capture=True).strip().splitlines()[-1])


def skill_rewrites(version: str) -> dict:
    """What a development install changes in its skills' text, ``{release's: this install's}``: every
    command's pin, ``cad +<VERSION>``, names this install's `version` (the name it registers as), so
    the skills run this checkout, and each SKILL.md header's `metadata.version` names it too; the setup
    block's install commands, which would install the release (``--add <VERSION>``), become a note
    that this is a development install; and the `cad` command's folder is CAD_LAUNCHER_DIR's."""
    release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    note = f"This is a development install of {REPO_ROOT}; do not run the install command here"
    install, install_windows = INSTALL_COMMANDS
    windows_script = install_windows.removeprefix("irm ").removesuffix(" | iex")
    rewrites = {
        # The macOS and Linux command stands alone in a shell block: there the note is a comment.
        f"{install} -s -- --add {release}": f"# {note}",
        f"& ([scriptblock]::Create((irm {windows_script}))) --add {release}": note,
        f"cad +{release}": f"cad +{version}",
        # The header's `metadata.version` names the build the copy is, as the pins do.
        f'\nmetadata:\n  repository: earthtojake/text-to-cad\n  version: "{release}"\n':
            f'\nmetadata:\n  repository: earthtojake/text-to-cad\n  version: "{version}"\n',
    }
    if launcher_dir() != "~/.local/bin":
        rewrites["~/.local/bin"] = launcher_dir()
    return rewrites


def assemble(host: str, plugin_dir: Path, version: str, server: dict, root: Path = REPO_ROOT,
             rewrites: dict | None = None) -> dict:
    """Write the plugin `host` loads into `plugin_dir` and return its manifest.

    The skills are copied with ``rewrites`` applied to each Markdown file (:func:`skill_rewrites`), the
    host's manifest takes `version` (each install its own, so a host that caches by
    version takes this build) and names `server` alone: in a server config beside it, or, for
    Gemini, which keeps servers in the manifest itself, inline. Claude Code's names none, as the
    release's: Cursor's and Grok Build's manifests beside it name the server for the apps that load it.
    """
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    shutil.copytree(root / "skills", plugin_dir / "skills", ignore=IGNORED)
    for skill in plugin_dir.glob("skills/**/*.md"):
        text = skill.read_text(encoding="utf-8")
        for released, ours in (rewrites or {}).items():
            text = text.replace(released, ours)
        skill.write_text(text, encoding="utf-8")
    if host == "gemini":
        manifest = json.loads((root / "gemini-extension.json").read_text(encoding="utf-8"))
        manifest["version"] = version
        manifest["mcpServers"] = {"cad": server}
        write_json(plugin_dir / "gemini-extension.json", manifest)
        return manifest
    if host == "claude":
        # Claude Code gets the skills alone; Cursor and Grok Build load its plugins and read their own
        # manifests first, which keep the server.
        for fed, servers_file in ((".cursor-plugin", "cursor.mcp.json"), (".grok-plugin", "claude.mcp.json")):
            _manifest(root, plugin_dir, fed, version, servers_file)
            write_json(plugin_dir / servers_file, {"mcpServers": {"cad": server}})
        return _manifest(root, plugin_dir, ".claude-plugin", version)
    manifest_dir = {"codex": ".codex-plugin", "cursor": ".cursor-plugin"}.get(host, ".claude-plugin")
    servers_file = "codex.mcp.json" if host == "codex" else "claude.mcp.json"
    write_json(plugin_dir / servers_file, {"mcpServers": {"cad": server}})
    return _manifest(root, plugin_dir, manifest_dir, version, servers_file)


def _manifest(root: Path, plugin_dir: Path, manifest_dir: str, version: str, servers_file: str | None = None) -> dict:
    """One host's manifest written into `plugin_dir` with `version`, naming `servers_file` (none: no server),
    with its own files beside it."""
    manifest = json.loads((root / manifest_dir / "plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest.pop("mcpServers", None)
    if servers_file:
        manifest["mcpServers"] = f"./{servers_file}"
    (plugin_dir / manifest_dir).mkdir(parents=True, exist_ok=True)
    # The manifest's own files (icons), beside it; never a marketplace catalog.
    for path in (root / manifest_dir).iterdir():
        if path.is_file() and path.name not in ("plugin.json", "marketplace.json"):
            shutil.copy2(path, plugin_dir / manifest_dir / path.name)
    if manifest_dir == ".cursor-plugin" and manifest.get("logo"):
        # Cursor's logo is a path inside the plugin; ours is the Claude icon.
        logo = plugin_dir / manifest["logo"]
        logo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / manifest["logo"], logo)
    write_json(plugin_dir / manifest_dir / "plugin.json", manifest)
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
    python = os.environ.get("CAD_PYTHON") or str(default)
    check = ("import pathlib, sys\n"
             "import cad_server.mcp.server  # the server must import\n"
             "import cad, cad_mcp\n"
             "root = pathlib.Path(sys.argv[1]).resolve()\n"
             "for package in (cad, cad_server, cad_mcp):\n"
             "    if root not in pathlib.Path(package.__file__).resolve().parents:\n"
             "        sys.exit(f'{sys.executable} imports {package.__name__} from {package.__file__}, not from {root}')\n")
    if subprocess.run([python, "-c", check, str(REPO_ROOT)]).returncode != 0:
        raise Refused(f"{python} cannot run this checkout's server; install requirements-dev.txt into .venv "
                      "or set CAD_PYTHON.")
    return python


def copy_page(host: str, build: bool, version: str, prune: bool = True) -> Path:
    """This install's copy of the built page. Servers still running an earlier install read their own."""
    if build:
        subprocess.run(["npm", "run", "build:mcp"], cwd=REPO_ROOT, check=True)
    built = [REPO_ROOT / "apps" / "mcp" / "dist" / name for name in ("shell.html", "app.js")]
    if not all(page.is_file() for page in built):
        raise Refused("apps/mcp is not built; run without --no-build.")
    pages = dev_root(host) / "app"
    page_dir = pages / version
    page_dir.mkdir(parents=True, exist_ok=True)
    for page in built:  # the shell a host keeps, and the app it loads (cadgen's mcp/ui.py)
        shutil.copy2(page, page_dir / page.name)
    if prune:
        stale = time.time() - PAGE_COPY_DAYS * 86400
        for old in pages.iterdir():
            if old != page_dir and old.stat().st_mtime < stale:
                shutil.rmtree(old, ignore_errors=True)
    return page_dir


def uvx_from(wheel: Path) -> list[str]:
    """``uvx ... --from`` the server's ``wheel``, with the library's wheel built beside it: the uvx
    command an install by wheel runs, up to the command it runs."""
    library = sorted(wheel.parent.glob("cad-[0-9]*.whl"))
    return [*LAUNCHER[:-1], *(["--with", str(library[0])] if library else []), LAUNCHER[-1], str(wheel)]


def build_wheel(host: str, bundle: bool) -> Path:
    """This checkout's wheels -- the library's, the server's and the shim's -- built as the release
    builds them, at a path of their own per build: the server's.

    uv keeps one installation per requirement, so a wheel at a new path is a new installation --
    and a warm daemon of its own -- never the previous build's, nor another worktree's.
    """
    uv = cli("uv", "; install uv: https://docs.astral.sh/uv/")
    if bundle:
        subprocess.run([str(REPO_ROOT / "scripts" / "bundle" / "bundle.sh")], cwd=REPO_ROOT, check=True)
    wheels = dev_root(host) / "wheels"
    out = wheels / time.strftime("%Y%m%d%H%M%S")
    for project in ("cad", "cad-server", "cad-mcp"):
        run(uv, "build", "--wheel", "--out-dir", str(out), str(REPO_ROOT / "packages" / project))
    built = sorted(out.glob("cad_server-*.whl"))
    if not built or not list(out.glob("cad-[0-9]*.whl")):
        raise Refused(f"uv build wrote no server or library wheel to {out}.")
    # A server already running keeps the installation it started from; only new starts read the
    # wheel, and they read this one.
    for old in wheels.iterdir():
        if old != out:
            shutil.rmtree(old, ignore_errors=True)
    return built[0]


def runtime(host: str, args: argparse.Namespace, version: str) -> tuple[dict, dict, Path | None]:
    """``(server, skill rewrites, page copy)`` for this install: the .venv, or with --wheel the wheel.

    Either way the installation is registered as `version` and the `cad` command written before
    the app restarts, by that installation's own interpreter; its server registers it again at each
    start.
    """
    if args.wheel:
        # One build a run, for every host it installs: one version, one environment.
        wheel = getattr(args, "built", None) or build_wheel(host, args.build)
        args.built = wheel
        shim = sorted(wheel.parent.glob("cad_mcp-*.whl"))
        if not shim:
            raise Refused(f"no shim wheel beside {wheel}.")
        server = {"command": LAUNCHER[0], "args": [*LAUNCHER[1:], str(shim[0]), "cad-mcp"]}
        if host == "codex":
            server["startup_timeout_sec"] = CODEX_STARTUP_SECONDS
        if host not in PLUGIN_HOSTS:  # Claude Desktop's chat runs no skills
            return server, {}, None
        # Its name makes it a development build to the server (the server's _internal/channel.py).
        server["env"] = {VERSION_ENV: version}
        register([*uvx_from(wheel), "python"], version)
        return server, skill_rewrites(version), None
    python = interpreter()
    # Codex keeps an earlier install's server running until it restarts, so its page stays too.
    page_dir = copy_page(host, args.build, version, prune=host != "codex")
    if host not in PLUGIN_HOSTS:  # Claude Desktop's chat runs no skills
        return server_entry(host, python, page_dir), {}, page_dir
    register([python], version)
    return server_entry(host, python, page_dir, version), skill_rewrites(version), page_dir


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
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {dev_id}."
    others = [plugin_id for plugin_id in installed() if plugin_id != dev_id]
    if others:
        raise Refused(f"Another CAD plugin is installed: {', '.join(others)}\n"
                      "Remove it first (codex plugin remove <id>); two copies means every skill twice.")
    refuse_other_copies("codex")
    version = args.version
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
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {dev_id}."
    refuse_other_copies("claude")
    version = args.version
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
        shutil.rmtree(dev_root("cursor"), ignore_errors=True)
        return f"Removed {target}."
    refuse_other_copies("cursor")
    version = args.version
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
        shutil.rmtree(root, ignore_errors=True)
        return f"Removed {name} from Grok Build."
    refuse_other_copies("grok")
    version = args.version
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
        shutil.rmtree(dev_root("gemini"), ignore_errors=True)
        return f"Removed {name} from Gemini CLI."
    others = [source for source in gemini_installed(gemini) if source != str(plugin_dir)]
    if others:
        raise Refused(f"Gemini CLI already has {name} from {', '.join(others)}; uninstall it first "
                      f"(gemini extensions uninstall {name}): two copies means every skill twice.")
    refuse_other_copies("gemini")
    version = args.version
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
    """Claude gets no CAD server, as from the release (``providers._plan_desktop``): installing and uninstalling
    alike take out the `cad-dev` server an earlier development install wrote, the rest of the config kept, its
    .bak beside it, and add nothing. A config that is not plain JSON is left alone."""
    path = desktop_config()
    shutil.rmtree(dev_root("claude-desktop"), ignore_errors=True)
    try:
        text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        servers = (json.loads(text) if text else {}).get("mcpServers")
    except (OSError, ValueError, AttributeError) as error:
        raise Refused(f"{path} cannot be read ({error}); left alone") from error
    if not isinstance(servers, dict) or DESKTOP_SERVER not in servers:
        return "Claude Desktop gets no CAD server: Claude gets the skills alone, through Claude Code's plugin."
    providers.edit_servers(path, remove=[DESKTOP_SERVER])
    return (f"Removed {DESKTOP_SERVER} from {path} (its .bak beside it): Claude gets the skills alone, through "
            "Claude Code's plugin. Claude Desktop drops the server when it next starts.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 1)[1])
    parser.add_argument("host", nargs="+", choices=HOSTS, help="the hosts to install in, one version for all")
    parser.add_argument("--uninstall", action="store_true", help="take these hosts' installs out")
    parser.add_argument("--no-build", dest="build", action="store_false", help="serve the page already built")
    parser.add_argument("--restart", action="store_true", help="codex: quit and reopen the app")
    parser.add_argument("--wheel", action="store_true", help="build this checkout's wheel and run it through uvx")
    args = parser.parse_args(argv)
    hosts = list(dict.fromkeys(args.host))
    if args.restart and "codex" not in hosts:
        parser.error("--restart is for codex")
    args.version = dev_version()
    install = {"claude": install_claude, "codex": install_codex, "cursor": install_cursor, "grok": install_grok,
               "gemini": install_gemini, "claude-desktop": install_claude_desktop}
    code = 0
    for host in hosts:
        try:
            print(install[host](args))
        except Refused as refusal:
            print(f"error: {host}: {refusal}", file=sys.stderr)
            code = 1
        except subprocess.CalledProcessError as error:
            print(f"error: {host}: {' '.join(map(str, error.cmd))} exited {error.returncode}", file=sys.stderr)
            code = 1
    if args.uninstall:
        install, install_windows = INSTALL_COMMANDS
        print(f"To go back to the published release, run the install command: {install} (on Windows: "
              f"{install_windows})")
    return code


if __name__ == "__main__":
    sys.exit(main())
