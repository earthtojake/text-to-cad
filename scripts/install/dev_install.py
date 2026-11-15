#!/usr/bin/env python3
"""Install this checkout into the agent apps, to test the plugin and the server locally; and go back.

    scripts/install/dev_install.py                 # this checkout, into every app found here
    scripts/install/dev_install.py claude codex    # into these apps alone (install.py's APPS keys)
    scripts/install/dev_install.py --release       # back to the published release, in every app

It does what the install script does (scripts/install/install.py, whose table of apps it uses), with this
checkout as the source instead of GitHub:

1. registers the checkout's .venv as a text-to-cad version of its own, ``<VERSION>-dev.<time>``, and writes the
   ``cad`` command (cad_server's own code, run by that interpreter);
2. writes the plugin from this checkout into ``tmp/dev-plugin/text-to-cad``: every command in its skills pins that
   version (``cad +<VERSION>-dev.<time>``), its CAD server runs the .venv (``uv run ... --python <.venv's python>
   --module cad_mcp``: the Agent Plugins standard's ``mcp.json``, which Codex reads first, refuses a command that is
   a path, and drops the server without a word), and its catalog is ``earthtojake-dev``;
3. removes the published copy of ours from each app and installs that folder instead, with the app's own command
   (install.py's ``local`` commands; an app that cannot install from a folder is skipped and says so).

``--release`` first removes every development version (its server stopped where nothing is in flight there): one
sorts after its release, so left installed it would stay the newest, the one a ``cad`` command with no pin runs and
whose server cleans. Then it runs install.py as it is: the newest release, every app moved back to the GitHub copy
(the development copies, ``text-to-cad@earthtojake-dev`` and the rest, are among the old copies it removes). Run it
again after a change; restart an app's session to load it.

Environment: ``CAD_PYTHON``, the interpreter that runs the server (default: the checkout's .venv).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "tmp" / "dev-plugin" / "text-to-cad"


def _install_module():
    """install.py, loaded by its path: it is the standard library alone, and this script runs where it does."""
    spec = importlib.util.spec_from_file_location("text_to_cad_install", Path(__file__).with_name("install.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


install = _install_module()

# Registers the interpreter running it as the development version named by the first argument and writes the
# `cad` command, through the checkout's own cad_server (this script cannot import it).
REGISTER = ("import sys\n"
            "from pathlib import Path\n"
            "from cad_server._internal import installations, releases, versions\n"
            "versions.development(sys.argv[1], sys.executable, str(releases.console(Path(sys.prefix))), sys.prefix)\n"
            "_path, _status, unwritten = installations.write_proxy()\n"
            "sys.exit(unwritten or 0)\n")
# Removes every development version installed (``versions.remove``: its server stopped first), each said.
REMOVE = ("from cad_server._internal import versions\n"
          "for name in versions.present():\n"
          "    if versions.DEVELOPMENT.fullmatch(name):\n"
          "        done = versions.remove(name, told=print)\n"
          "        if done not in ('removed', 'absent'):\n"
          "            print(f'text-to-cad {name} stays for now ({done}): run this again once nothing runs from it')\n")
# The variable naming the version the server registers as when an app starts it (cad_server's installations).
VERSION_ENV = "CAD_INSTALLATION_VERSION"


class Refused(Exception):
    """This checkout cannot be installed as it is; the message says why."""


def interpreter() -> str:
    python = os.environ.get("CAD_PYTHON") or str(REPO_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt"
                                                                      else "bin/python"))
    check = ("import pathlib, sys\nimport cad, cad_server, cad_mcp\nroot = pathlib.Path(sys.argv[1]).resolve()\n"
             "for package in (cad, cad_server, cad_mcp):\n"
             "    if root not in pathlib.Path(package.__file__).resolve().parents:\n"
             "        sys.exit(f'{sys.executable} imports {package.__name__} from {package.__file__}, not from {root}')\n")
    if subprocess.run([python, "-c", check, str(REPO_ROOT)]).returncode != 0:
        raise Refused(f"{python} cannot run this checkout's server: install requirements-dev.txt into .venv, "
                      "or set CAD_PYTHON")
    return python


def remove_development() -> None:
    """Every development version removed, by this checkout's own server code (``REMOVE``); where the checkout cannot
    run it, said, and nothing removed."""
    try:
        python = interpreter()
    except Refused as refusal:
        print(f"The development versions stay ({refusal}).", file=sys.stderr)
        return
    subprocess.run([python, "-c", REMOVE])


def plugin_files(root: Path = REPO_ROOT) -> list:
    """The checkout's plugin, as the `latest` branch carries it: the skills, every app's manifest folder
    (``.<app>-plugin/``), the root's JSON manifests and server configs, and the licence."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
    found = []
    for name in listed.decode("utf-8").split("\0"):
        first = name.split("/", 1)[0]
        if (first == "skills" or name == "LICENSE" or re.fullmatch(r"\.[a-z0-9]+-plugin", first)
                or ("/" not in name and name.endswith(".json") and name not in ("package.json", "package-lock.json"))):
            if (root / name).is_file():
                found.append(name)
    return found


def assemble(target: Path, version: str, python: str, root: Path = REPO_ROOT) -> None:
    """The development plugin written into ``target``: ``version`` in every pin and manifest, every CAD server
    entry running ``cad_mcp`` on ``python`` as that version, and the catalog named ``earthtojake-dev``."""
    release = (root / "VERSION").read_text(encoding="utf-8").strip()
    if target.exists():
        shutil.rmtree(target)
    for name in plugin_files(root):
        source, path = root / name, target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".md"):
            text = source.read_text(encoding="utf-8").replace(f"cad +{release}", f"cad +{version}")
            text = text.replace(f"--from cad-server=={release} cad setup", f"--from cad-server=={release} cad setup  "
                                f"# not here: this is a development install of {root}")
            path.write_text(text, encoding="utf-8")
        elif name.endswith(".json"):
            path.write_text(json.dumps(_json(json.loads(source.read_text(encoding="utf-8")), name, release, version,
                                             python), indent=2) + "\n", encoding="utf-8")
        else:
            shutil.copy2(source, path)


def _json(data, name: str, release: str, version: str, python: str):
    if not isinstance(data, dict):
        return data
    if name.endswith("marketplace.json") and isinstance(data.get("name"), str):
        data["name"] = install.DEV_CATALOG
    if data.get("version") == release:
        data["version"] = version
    plugins = data.get("plugins") if isinstance(data.get("plugins"), list) else []
    for plugin in plugins:
        if isinstance(plugin, dict) and plugin.get("version") == release:
            plugin["version"] = version
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and isinstance(servers.get("cad"), dict):
        # A bare command in every entry: the Agent Plugins standard allows only a program's name or a `./` path
        # inside the plugin, and Codex, which reads the standard's mcp.json before its own manifest's file, drops
        # a server whose command is a path with no error. uv, which the published entries' uvx comes with, runs
        # the interpreter in place, and the shim takes it for a launcher when it looks for its host.
        entry = {key: value for key, value in servers["cad"].items() if key not in ("command", "args", "env")}
        servers["cad"] = {**entry, "command": "uv",
                          "args": ["run", "--no-config", "--no-project", "--python", python, "--module", "cad_mcp"],
                          "env": {VERSION_ENV: version}}
    return data


def main(argv=None) -> int:
    keys = [app.key for app in install.APPS]
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("apps", nargs="*", metavar="APP", help=f"one of: {', '.join(keys)}")
    parser.add_argument("--release", action="store_true", help="go back to the published release, in every app")
    args = parser.parse_args(argv)
    unknown = [name for name in args.apps if name not in keys]
    if unknown:
        parser.error(f"no app {', '.join(unknown)}: choose from {', '.join(keys)}")
    if args.release:
        if args.apps:
            parser.error("--release takes no apps: it puts the published release into every app")
        remove_development()
        return install.main([])
    version = f"{(REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()}-dev.{time.strftime('%Y%m%d%H%M%S')}"
    try:
        python = interpreter()
        if subprocess.run([python, "-c", REGISTER, version]).returncode != 0:
            raise Refused(f"could not register this checkout as {version}")
    except Refused as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 1
    assemble(PLUGIN_DIR, version, python)
    source = install.Source(folder=PLUGIN_DIR, catalog=install.DEV_CATALOG, skills_dir=PLUGIN_DIR / "skills")
    apps = [app for app in install.APPS if not args.apps or app.key in args.apps]
    print(f"This checkout is text-to-cad {version}.")
    for line in install.install_apps(install.Here(), source, apps):
        print(line)
    print("Start a new session in each app to use it. To go back: scripts/install/dev_install.py --release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
