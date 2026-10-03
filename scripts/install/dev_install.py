#!/usr/bin/env python3
"""Install this checkout into an agent app, to test the skills and the plugin locally.

A plugin host gets the development plugin, text-to-cad@earthtojake-dev: this checkout's skills,
and CAD's server run by this checkout's .venv (`cadgen mcp`), serving a copy of this checkout's
apps/mcp build. Claude Desktop's chat takes servers, not plugins, so it gets that server alone.
Agents without plugins get live links to the skills. Run it again after a change; --uninstall
takes the install out.

One copy per app: a host that already loads another copy of the plugin (the published one, or
this one through another host) is refused, because two copies means every skill twice. Cursor
and Grok Build both load the plugins Claude Code installed, so `claude` covers all three.

    scripts/install/dev_install.py codex [--restart]   # the Codex app
    scripts/install/dev_install.py claude              # Claude Code (and so Cursor and Grok Build)
    scripts/install/dev_install.py cursor              # Cursor, without Claude Code
    scripts/install/dev_install.py grok                # Grok Build, without Claude Code
    scripts/install/dev_install.py claude-desktop      # Claude Desktop's chat: the server alone
    scripts/install/dev_install.py gemini|agents       # skill links, for agents without plugins
    scripts/install/dev_install.py <host> --uninstall

The page is a copy taken at install, as an installed wheel serves its own: a page that changed
under a running app would change its URI, and hosts drop the frames already showing it. So
install again to see a page edit, and restart the app after a Python change -- a running server
keeps the code it started with.

Environment:
    CADGEN_PYTHON           the interpreter that runs the server (default: the checkout's .venv)
    CODEX_CLI               the codex CLI (default: the newer of `codex` on PATH and the Codex app's)
    CLAUDE_DESKTOP_CONFIG   Claude Desktop's config file (default: its own, per platform)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = "earthtojake-dev"
PLUGIN_HOSTS = ("codex", "claude", "cursor", "grok")
SKILL_HOSTS = ("gemini", "agents")
HOSTS = (*PLUGIN_HOSTS, "claude-desktop", *SKILL_HOSTS)
DESKTOP_SERVER = "cad-dev"
CURSOR_PLUGINS = Path.home() / ".cursor" / "plugins" / "local"
# Written into the Cursor plugin folder, so --uninstall and a reinstall only ever touch our own.
OWNER_MARK = ".text-to-cad-dev"
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
# A Codex thread waits this long for the server's first start, which may build the page's data.
CODEX_STARTUP_SECONDS = 30
PAGE_COPY_DAYS = 1


class Refused(Exception):
    """The install would leave the app in a state we never want; the message says why."""


def plugin_name(root: Path = REPO_ROOT) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]


def skill_names(root: Path = REPO_ROOT) -> list[str]:
    return sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))


def dev_root(host: str, root: Path = REPO_ROOT) -> Path:
    return root / "tmp" / f"{host}-dev"


def server_entry(host: str, python: str, page_dir: Path) -> dict:
    """CAD's server for a development install: this checkout's interpreter, this install's page."""
    entry = {"command": python, "args": ["-m", "cadgen.cli", "mcp"], "env": {"CADGEN_MCP_APP_DIR": str(page_dir)}}
    if host == "codex":
        entry["startup_timeout_sec"] = CODEX_STARTUP_SECONDS
    return entry


def assemble(host: str, plugin_dir: Path, version: str, server: dict, root: Path = REPO_ROOT) -> dict:
    """Write the plugin `host` loads into `plugin_dir` and return its manifest.

    The skills are copied, the host's manifest takes `version` (each install its own, so a host
    that caches by version takes this build) and names a server config holding `server` alone.
    """
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    shutil.copytree(root / "skills", plugin_dir / "skills", ignore=IGNORED)
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


def link_skills(destination: Path, root: Path = REPO_ROOT) -> list[str]:
    """Link each of this checkout's skills into `destination`; drop links to retired ones.

    A path that is not a link into this checkout's skills is someone else's and left alone.
    Returns what it did, one line each.
    """
    skills_root = (root / "skills").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    done = []
    for path in sorted(destination.iterdir()):
        target = ours(path, skills_root)
        if target is not None and not (target / "SKILL.md").is_file():
            path.unlink()
            done.append(f"removed {path.name} (retired)")
    for name in skill_names(root):
        link = destination / name
        if link.is_symlink() or link.exists():
            if ours(link, skills_root) is None:
                done.append(f"skipped {name}: {link} is not this checkout's link")
            continue
        link.symlink_to(skills_root / name, target_is_directory=True)
        done.append(f"linked {name}")
    return done


def unlink_skills(destination: Path, root: Path = REPO_ROOT) -> list[str]:
    skills_root = (root / "skills").resolve()
    done = []
    if destination.is_dir():
        for path in sorted(destination.iterdir()):
            if ours(path, skills_root) is not None:
                path.unlink()
                done.append(f"removed {path.name}")
        if not any(destination.iterdir()):
            destination.rmdir()
    return done


def ours(path: Path, skills_root: Path) -> Path | None:
    """The skill folder `path` links to, when it is a link into `skills_root`."""
    if not path.is_symlink():
        return None
    target = Path(os.readlink(path))
    target = Path(os.path.normpath(target if target.is_absolute() else path.parent / target))
    return target if Path(os.path.realpath(target.parent)) == skills_root else None


def write_json(path: Path, value: dict) -> None:
    """Replace `path` whole, keeping its mode (a config may hold another server's secrets)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(value, out, indent=2)
        out.write("\n")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def run(*command: str, capture: bool = False) -> str:
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else ""


def cli(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise Refused(f"No `{name}` on PATH.")
    return found


def codex_cli() -> str:
    """CODEX_CLI, else the newer of `codex` on PATH and the one the Codex app bundles.

    Both write the same ~/.codex, which the app, the terminal CLI and the IDE extension share,
    so the install must come from a CLI at least as new as the app that reads it.
    """
    if os.environ.get("CODEX_CLI"):
        candidates = [os.environ["CODEX_CLI"]]
    else:
        candidates = [path for path in (shutil.which("codex"), "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")
                      if path and os.access(path, os.X_OK)]
    versions = {}
    for path in candidates:
        try:
            output = subprocess.run([path, "--version"], capture_output=True, text=True, check=True).stdout
            versions[path] = tuple(int(part) for part in output.split()[-1].split(".")[:3])
        except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
            continue
    if not versions:
        raise Refused("No working codex CLI; install Codex or set CODEX_CLI.")
    return max(versions, key=versions.get)


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


def dev_version() -> str:
    return f"{(REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()}-dev.{time.strftime('%Y%m%d%H%M%S')}"


def claude_installed() -> list[str]:
    """The plugin ids Claude Code has installed for this plugin, any marketplace."""
    if not shutil.which("claude"):
        return []
    plugins = json.loads(run("claude", "plugin", "list", "--json", capture=True) or "[]")
    return [plugin["id"] for plugin in plugins if plugin.get("id", "").split("@")[0] == plugin_name()]


def grok_installed() -> list[str]:
    """Where each of Grok Build's installs of this plugin came from."""
    if not shutil.which("grok"):
        return []
    plugins = json.loads(run("grok", "plugin", "list", "--json", capture=True) or "[]")
    return [plugin.get("source") or plugin.get("path", "") for plugin in plugins if plugin.get("name") == plugin_name()]


def cursor_installed() -> list[Path]:
    """Cursor's local plugin folders that hold this plugin."""
    found = []
    for folder in sorted(CURSOR_PLUGINS.glob("*")) if CURSOR_PLUGINS.is_dir() else []:
        for manifest in (folder / ".cursor-plugin" / "plugin.json", folder / "plugin.json"):
            try:
                if json.loads(manifest.read_text(encoding="utf-8")).get("name") == plugin_name():
                    found.append(folder)
                    break
            except (OSError, ValueError):
                continue
    return found


def refuse_other_copies(host: str) -> None:
    """Refuse when an app this host feeds already loads another copy of the plugin."""
    dev_id = f"{plugin_name()}@{MARKETPLACE}"
    others = []
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
                      + "\n  ".join(others) + "\nUninstall it first: two copies means every skill twice.")


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
    python = interpreter()
    version = dev_version()
    # Codex keeps an earlier install's server running until it restarts, so its page stays too.
    page_dir = copy_page("codex", args.build, version, prune=False)
    assemble("codex", root / "plugins" / name, version, server_entry("codex", python, page_dir))
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
        for old in (root / "app").iterdir():
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
    python = interpreter()
    version = dev_version()
    page_dir = copy_page("claude", args.build, version)
    assemble("claude", root / "plugins" / name, version, server_entry("claude", python, page_dir))
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
    python = interpreter()
    version = dev_version()
    page_dir = copy_page("cursor", args.build, version)
    # Cursor follows no symlink out of its plugins folder, so the plugin is a real copy there.
    staged = dev_root("cursor") / "plugins" / name
    assemble("cursor", staged, version, server_entry("cursor", python, page_dir))
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
    python = interpreter()
    version = dev_version()
    page_dir = copy_page("grok", args.build, version)
    assemble("grok", plugin_dir, version, server_entry("grok", python, page_dir))
    if str(plugin_dir) in grok_installed():
        run(grok, "plugin", "uninstall", name)
    run(grok, "plugin", "install", str(plugin_dir), "--trust")
    return f"Installed {name} {version} in Grok Build; start a new session to load it."


def desktop_config() -> Path:
    if os.environ.get("CLAUDE_DESKTOP_CONFIG"):
        return Path(os.environ["CLAUDE_DESKTOP_CONFIG"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


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
    python = interpreter()
    page_dir = copy_page("claude-desktop", args.build, time.strftime("%Y%m%d%H%M%S"))
    servers[DESKTOP_SERVER] = server_entry("claude-desktop", python, page_dir)
    write_json(path, config)
    return (f"Added {DESKTOP_SERVER} to {path}. Restart Claude Desktop (or Developer > Reload MCP "
            "Configuration) to load it.")


def skills_destination(host: str) -> Path:
    if host == "gemini":
        return Path.home() / ".gemini" / "skills"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "agents" / "skills"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n\n", 1)[1])
    parser.add_argument("host", choices=HOSTS)
    parser.add_argument("--uninstall", action="store_true", help="take this host's install out")
    parser.add_argument("--no-build", dest="build", action="store_false", help="serve the page already built")
    parser.add_argument("--restart", action="store_true", help="codex: quit and reopen the app")
    args = parser.parse_args(argv)
    if args.restart and args.host != "codex":
        parser.error("--restart is for codex")
    try:
        if args.host in SKILL_HOSTS:
            destination = skills_destination(args.host)
            for line in (unlink_skills if args.uninstall else link_skills)(destination):
                print(line)
            print(f"{'Unlinked' if args.uninstall else 'Linked'} this checkout's skills in {destination}; "
                  "restart the agent to rescan them.")
            return 0
        install = {"codex": install_codex, "claude": install_claude, "cursor": install_cursor,
                   "grok": install_grok, "claude-desktop": install_claude_desktop}[args.host]
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
