#!/usr/bin/env python3
"""Install this checkout into the agent apps, to test the plugin and cad locally; and go back.

    scripts/install/dev_install.py                 # this checkout, into every app found here
    scripts/install/dev_install.py claude codex    # into these apps alone (install.py's APPS keys)
    scripts/install/dev_install.py --release       # back to the published release, in every app

It does what the install script does (scripts/install/install.py, whose table of apps it uses), with this
checkout as the source instead of PyPI and GitHub:

1. installs the checkout's cad as the ``cad`` uv tool, editable (``uv tool install --managed-python --python 3.14
   --editable packages/cad``; the cad command of 0.10.0-0.11.11 removed first, as install.py removes it), and
   switches cad's automatic updates off: an update would put the release in its place;
2. writes the plugin from this checkout into ``tmp/dev-plugin/text-to-cad``: its manifests name the version
   ``<VERSION>-dev.<time>`` (so each app takes it as new), Codex's CAD server (the one app given one:
   ``codex.mcp.json``) runs ``cad mcp``, the editable tool's command, and its catalog is ``earthtojake-dev``;
3. installs that folder in each app with the app's own command (install.py's ``local`` commands; an app that cannot
   install from a folder is skipped and says so), and only then removes the published copy of ours there.

``--release`` uninstalls the editable tool (only where the ``cad`` tool is one), then runs install.py as it is: the
newest release of cad, every app moved back to the GitHub copy (the development copies, ``text-to-cad@earthtojake-dev``
and the rest, are among the old copies it removes); then turns cad's automatic updates on again (``cad update
auto on``), which install.py leaves as they are. Run it again after a change; restart an app's session to load it. Run
``scripts/bundle/bundle.sh`` once first: the CAD Viewer's page comes from the bundle.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
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


def uv_folder(uv: str, *bin_: str) -> Path:
    """``uv tool dir`` (``--bin``: the folder of the tools' commands)."""
    return Path(subprocess.run([uv, "tool", "dir", *bin_], capture_output=True, text=True, check=True).stdout.strip())


def install_checkout(uv: str) -> int:
    """This checkout's cad as the ``cad`` uv tool, editable, its automatic updates off: 0, else uv's exit status."""
    here = install.Here()
    folder = uv_folder(uv, "--bin")
    problem, moved = install.make_room(here, folder, install.uv_tools(here, uv))
    if problem:
        print(problem, file=sys.stderr)
        return 1
    code = subprocess.call([uv, "tool", "install", *install.UV_TOOL_ARGS, "--reinstall-package", "cad", "--editable",
                            str(REPO_ROOT / "packages" / "cad")])
    install.settle(here, moved, code == 0)
    if code == 0:
        cad = folder / ("cad.exe" if here.windows else "cad")
        if subprocess.run([str(cad), "update", "auto", "off"], capture_output=True).returncode == 0:
            print("Automatic updates are off: an update would replace this checkout's cad with the release.")
    return code


def editable(uv: str) -> bool:
    """Whether the ``cad`` uv tool is an editable install (its receipt names an ``editable`` requirement)."""
    try:
        return bool(re.search(r"\beditable\s*=", (uv_folder(uv) / "cad" / "uv-receipt.toml").read_text(encoding="utf-8")))
    except (OSError, subprocess.CalledProcessError):
        return False


def plugin_files(root: Path = REPO_ROOT) -> list:
    """The checkout's plugin, as the `latest` branch carries it: the skills, every app's manifest folder
    (``.<app>-plugin/``), the root's JSON manifests and Codex's server config, and the licence."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
    found = []
    for name in listed.decode("utf-8").split("\0"):
        first = name.split("/", 1)[0]
        if (first == "skills" or name == "LICENSE" or re.fullmatch(r"\.[a-z0-9]+-plugin", first)
                or ("/" not in name and name.endswith(".json") and name not in ("package.json", "package-lock.json"))):
            if (root / name).is_file():
                found.append(name)
    return found


def assemble(target: Path, version: str, root: Path = REPO_ROOT) -> None:
    """The development plugin written into ``target``: ``version`` in every manifest, the CAD server entry running
    the ``cad`` command's ``cad mcp``, and the catalog named ``earthtojake-dev``."""
    release = (root / "VERSION").read_text(encoding="utf-8").strip()
    if target.exists():
        shutil.rmtree(target)
    for name in plugin_files(root):
        source, path = root / name, target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".json"):
            path.write_text(json.dumps(_json(json.loads(source.read_text(encoding="utf-8")), name, release, version),
                                       indent=2) + "\n", encoding="utf-8")
        else:
            shutil.copy2(source, path)


def _json(data, name: str, release: str, version: str):
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
        # Codex's entry, the one there is: the editable tool's command, bare as the published entry's uvx (a server
        # config whose command is a path has been dropped by Codex with no error). Its other keys (its
        # startup_timeout_sec) are kept.
        entry = {key: value for key, value in servers["cad"].items() if key not in ("command", "args", "env")}
        servers["cad"] = {**entry, "command": "cad", "args": ["mcp"]}
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
    uv = shutil.which("uv")
    if not uv:
        print("error: uv is needed (https://docs.astral.sh/uv/)", file=sys.stderr)
        return 1
    if args.release:
        if args.apps:
            parser.error("--release takes no apps: it puts the published release into every app")
        if editable(uv) and subprocess.call([uv, "tool", "uninstall", "cad"]) != 0:
            return 1
        code = install.main([])
        cad = uv_folder(uv, "--bin") / ("cad.exe" if install.Here().windows else "cad")
        if cad.exists() and subprocess.run([str(cad), "update", "auto", "on"], capture_output=True).returncode == 0:
            print("Automatic updates are on again.")
        return code
    if install_checkout(uv) != 0:
        print("error: this checkout's cad was not installed (what went wrong is above)", file=sys.stderr)
        return 1
    version = f"{(REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()}-dev.{time.strftime('%Y%m%d%H%M%S')}"
    assemble(PLUGIN_DIR, version)
    source = install.Source(folder=PLUGIN_DIR, catalog=install.DEV_CATALOG, skills_dir=PLUGIN_DIR / "skills")
    apps = [app for app in install.APPS if not args.apps or app.key in args.apps]
    print(f"This checkout's plugin is text-to-cad {version}; `cad` runs this checkout.")
    report = install.install_apps(install.Here(), source, apps)  # each app's line printed as it finishes
    if report.changed:
        print("Start a new session in each app to use it.")
    print("To go back: scripts/install/dev_install.py --release")
    return 1 if report.all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
