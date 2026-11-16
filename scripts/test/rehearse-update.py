#!/usr/bin/env python3
"""A computer on a shipped release arriving at this build, rehearsed with the real release from PyPI on a private
computer: its own home, state, engine, cache and ``cad`` command folders, never this machine's.

Two ways reach this build, and each is rehearsed from the releases that take it:

- the shipped release's own updater (0.11.10; ``--old`` names another of 0.10.0 to 0.11.10): it installs this build in a
  flat ``releases/<release>`` folder and runs its hidden ``cad setup --engine-update``, which sets the version up,
  writes the record the updater's switch starts its server by and owes the computer the install script's run; the
  switch then points ``installations/current`` at this build and starts its server on the port pages were on, and goes
  back to the release before where that server does not answer. This build's server, once it serves, runs the install
  script (``CAD_ENGINE_UPDATE_INSTALLER``: here a stand-in that writes the report the real script writes, or the real
  ``scripts/install/install.sh``) until it has worked. Routes:
  - ``updater``: by the update button (``POST /api/v1/local/update``). From 0.10.0 on Windows (``--old 0.10.0``), which
    keeps its state in the local application data, where its switch reads the records it starts a server by, apart
    from this build's: its computer names no state folder, and this build's setup stops 0.10.0's server by its own
    stop command and takes the computer over itself, 0.10.0's own records then naming this build; then this build's
    real plain `cad setup`, as the hand-over's install script runs it, must leave the server that took over serving
    its pages (the same process, the same port and token) and run no stop;
  - ``automatic``: by the automatic update, nothing pressed (an hour passes for the version feed: its ``checked``
    stamp set back), as most computers take it;
  - ``handover`` (POSIX: its stand-ins are scripts run by their ``#!`` line): by the button on a computer with
    stand-ins of two agent apps, Claude Code's and Codex's commands, to which 0.11.10's setup gave its plugin from its
    local catalog (``<state>/plugin``); the hand-over runs the real ``install.sh`` and ``install.py`` through their
    test hooks, and one stand-in fails its first command: the first attempt fails, the next server start (an hour
    later: the record's stamps set back) tries again, and every stand-in ends with the new plugin from GitHub and
    without the old one;
  - ``rollback``: by the automatic update, to a variant of this build whose server cannot start (its daemon module
    exits at once; published as a release of its own): the switch goes back, so the old release serves again on the
    pages' port with their token, ``current`` names it, the ``cad`` command runs it, and the install script never
    runs; and its automatic retry a day later (its stamps set back, its server restarted) leaves all of that so.
- ``install-script`` (0.11.10, or ``--old``): ``scripts/install/install.py`` run as the hosted script runs it, which
  runs this build's ``cad setup`` through uvx; the shipped release's server is asked to stop once idle and the next
  command starts this build's;
- ``from-0.8``: 0.8.4, which has no updater, installed by its own ``cadgen setup`` with telemetry turned off, its
  server serving a page and a file in Recents; then ``install.py``. Its state folder is the platform's, in the private
  home (no ``CAD_STATE_DIR``): what 0.8 kept there is taken in only where no state folder is named.

After each arrival it checks: this build's server answering on the port pages were on (with the page token they hold,
from 0.10 and 0.11); the file recorded before in Recents and opening (``GET /api/v1/documents/<id>``), the telemetry
answer and What's new decided as an updated computer's; the ``cad`` command with no pin and ``cad +<this build>``
running this build; through an updater, the install script run once, by this build's server and only once it served,
and the hand-over recorded done; one server: the old release's gone, no process left running from its folders, and
the layout of 0.11.10 and earlier (or what 0.8 left there) removed by this build's cleanup once that is safe.

This tree is published as one later release (``0.11.<9000+n>``, n from this process: no index ever holds it), and its
variant whose server cannot start as another (``0.11.<9900+n>``), their wheels in a folder uv reads beside the index
(``CAD_UPDATE_FIND_LINKS``, ``UV_FIND_LINKS``), and the version feed is a stand-in served here (``CAD_API_URL``,
``CAD_INSTALL_FEED``). No process is given a port by name: each computer's servers take the default port, 3245 where
it is free on this machine (CI), else a free port of the computer's own as its default (``CAD_ENGINE_DEFAULT_PORT``,
``CADGEN_ENGINE_DEFAULT_PORT``), so a server this script did not start is never asked anything. No real agent app
runs: PATH holds the system's folders and the computer's own, ``CODEX_CLI`` names the computer's (a stand-in, or a
path where there is none: old releases otherwise run the Codex app's bundled command), and ``install.py`` looks on PATH
alone (``CAD_INSTALL_PATH_ONLY``). uv's own cache is this machine's (``uv cache dir``): it is read, and this run's
wheels are taken out of it again (``forget``). Every computer is a folder of the system's temporary folder, removed
with every process of it as its route ends.

Usage: scripts/test/rehearse-update.py [ROUTE ...] [--old RELEASE] (default: all; every route but ``from-0.8`` starts
on 0.11.10, or on ``--old``). It needs uv, the network (PyPI, for the old releases and what every release depends on;
uv's cache holds them after the first run) and loopback ports. The release tier of ``.github/workflows/test.yml`` runs
it on Linux, macOS and Windows (``update-rehearsal``). Exit 0 when every route held; 1, with what the computer holds,
when one did not.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.python.support.machine import Feed, forget, free_port, release  # noqa: E402

from cad_server._internal import base  # noqa: E402
from cad_server._internal.launch import LAUNCHER  # noqa: E402

OLD = "0.11.10"
EIGHT = "0.8.4"
# The release whose updater cannot switch to this build on Windows (``Computer.alone``).
ALONE_OLD = "0.10.0"
WINDOWS = os.name == "nt"
# This checkout as a release a release before it takes (a patch), and no index will ever hold; and its variant whose
# server cannot start.
NEW = f"0.11.{9000 + os.getpid() % 900}"
BROKEN = f"0.11.{9900 + os.getpid() % 90}"
BROKEN_DAEMON = b"raise SystemExit('cad: this build cannot start its server (a rehearsal of a release that cannot)')\n"
# How long each wait may take: an install from uv's cache, a switch, a cleanup's next try (a minute).
SECONDS = 600.0
DEFAULT_PORT = 3245
# A file a page opens, binary-free.
STL = ("solid p\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\n"
       "endsolid p\n")
# The stand-in of the install script an updater's hand-over runs: a line in the file it names, each run (when, and the
# version installations/current named in the state folder it names), and the report the real script writes where
# CAD_INSTALL_REPORT names it.
INSTALLER = ("import json, os, sys, time\n"
             "state = sys.argv[2]\n"
             "current = open(os.path.join(state, 'installations', 'current'), encoding='utf-8').read().strip()\n"
             "with open(sys.argv[1], 'a', encoding='utf-8') as out:\n"
             "    out.write(f'{time.time()} {current}\\n')\n"
             "with open(os.environ['CAD_INSTALL_REPORT'], 'w', encoding='utf-8') as out:\n"
             "    json.dump({'schema': 'text-to-cad install report/1', 'release': current, 'setup': 0, 'apps': {}}, out)\n")
# A server started as a page link starts it, by a Python of the release (its own client), and what it says: its
# token and port.
START = "import json\nfrom {package}.engine import client\nprint(json.dumps(client.request({{'op': 'http'}})))"
# Stand-ins of Claude Code's and Codex's commands, and of git, for the ``handover`` route: each records its call, and
# keeps what the real one keeps in its own files, as 0.11.10's setup and install.py read them back (Claude Code's
# ~/.claude/plugins/installed_plugins.json and known_marketplaces.json, Codex's ~/.codex/config.toml); git's clone is a
# copy of this checkout's plugin. Claude Code's first add of the GitHub catalog fails (``FAILED_ONCE``). Nothing of the
# network, nothing outside the home.
APPS = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
name, args, home = Path(sys.argv[0]).name, sys.argv[1:], Path(os.environ["HOME"])
with open({calls!r}, "a", encoding="utf-8") as log:
    log.write(json.dumps({{"name": name, "argv": args}}) + "\n")
def done(code=0, out=""):
    if out:
        print(out)
    sys.exit(code)
def catalog(source):
    for relative in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        try:
            return json.loads((Path(source or {repo!r}) / relative).read_text())["name"]
        except (OSError, ValueError, KeyError):
            pass
    return json.loads((Path({repo!r}) / ".claude-plugin/marketplace.json").read_text())["name"]
if args[:1] == ["--version"]:
    done(0, {{"claude": "2.1.325 (Claude Code)", "codex": "codex-cli 0.169.0", "git": "git version 2.50.1"}}[name])
words = [word for index, word in enumerate(args) if not word.startswith("--") and (index == 0 or args[index - 1]
         not in ("--scope", "--ref"))]
if name == "claude":
    folder = home / ".claude" / "plugins"
    folder.mkdir(parents=True, exist_ok=True)
    plugins_file, markets_file = folder / "installed_plugins.json", folder / "known_marketplaces.json"
    plugins = json.loads(plugins_file.read_text()) if plugins_file.exists() else {{"version": 2, "plugins": {{}}}}
    markets = json.loads(markets_file.read_text()) if markets_file.exists() else {{}}
    def save():
        plugins_file.write_text(json.dumps(plugins)); markets_file.write_text(json.dumps(markets))
    if words[:3] == ["plugin", "marketplace", "add"]:
        source = words[3]
        if Path(source).is_dir():
            key = catalog(source)
            markets[key] = {{"source": {{"source": "directory", "path": source}}, "installLocation": source}}
        else:
            failed = Path({failed_once!r})
            if not failed.exists():
                failed.write_text("")
                done(1, "Failed to add marketplace: a network error (a stand-in's)")
            repo, _, ref = source.partition("#")
            key = catalog(None)
            markets[key] = {{"source": {{"source": "github", "repo": repo, **({{"ref": ref}} if ref else {{}})}},
                            "installLocation": str(folder / "marketplaces" / key)}}
        save(); done(0, f"Successfully added marketplace: {{key}}")
    if words[:3] == ["plugin", "marketplace", "remove"]:
        if words[3] not in markets:
            done(1, f"Marketplace '{{words[3]}}' not found")
        del markets[words[3]]
        for key in [key for key in plugins["plugins"] if key.endswith("@" + words[3])]:
            del plugins["plugins"][key]
        save(); done(0)
    if words[:3] == ["plugin", "marketplace", "update"]:
        done(0 if words[3] in markets else 1)
    if words[:3] == ["plugin", "marketplace", "list"]:
        done(0, json.dumps([{{"name": key, "source": value["source"]["source"], "repo": value["source"].get("repo"),
                             "ref": value["source"].get("ref"), "path": value["source"].get("path"),
                             "installLocation": value.get("installLocation")}} for key, value in markets.items()]))
    if words[:2] == ["plugin", "install"]:
        market = words[2].partition("@")[2]
        if market not in markets:
            done(1, f"Plugin {{words[2]}} not found")
        plugins["plugins"][words[2]] = [{{"scope": "user", "installPath": markets[market]["installLocation"],
                                          "version": "stand-in"}}]
        save(); done(0, f"Installed {{words[2]}}")
    if words[:2] == ["plugin", "uninstall"]:
        if words[2] not in plugins["plugins"]:
            done(1, f"Plugin {{words[2]}} is not installed")
        del plugins["plugins"][words[2]]; save(); done(0)
    if words[:2] == ["plugin", "update"]:
        done(0 if words[2] in plugins["plugins"] else 1)
    if words[:2] == ["plugin", "list"]:
        done(0, json.dumps([{{"id": key, **entries[0]}} for key, entries in plugins["plugins"].items()]))
    done(0)
if name == "codex":
    folder = home / ".codex"
    folder.mkdir(parents=True, exist_ok=True)
    kept = folder / ".stand-in.json"
    state = json.loads(kept.read_text()) if kept.exists() else {{"marketplaces": {{}}, "plugins": []}}
    def save():
        kept.write_text(json.dumps(state))
        lines = []
        for key, market in state["marketplaces"].items():
            lines += [f"[marketplaces.{{key}}]", f'source_type = "{{market["type"]}}"', f'source = "{{market["source"]}}"']
            lines += [f'ref = "{{market["ref"]}}"'] if market.get("ref") else []
            lines.append("")
        for plugin in state["plugins"]:
            lines += [f'[plugins."{{plugin}}"]', "enabled = true", ""]
        (folder / "config.toml").write_text("\n".join(lines))
    ref = args[args.index("--ref") + 1] if "--ref" in args else ""
    if words[:3] == ["plugin", "marketplace", "add"]:
        source = words[3]
        local = Path(source).is_dir()
        key = catalog(source if local else None)
        state["marketplaces"][key] = {{"type": "local" if local else "git", "ref": ref,
                                      "source": source if local else f"https://github.com/{{source}}.git"}}
        save(); done(0, f"Added marketplace {{key}}")
    if words[:3] == ["plugin", "marketplace", "remove"]:
        if words[3] not in state["marketplaces"]:
            done(1, "no such marketplace")
        del state["marketplaces"][words[3]]; save(); done(0)
    if words[:3] == ["plugin", "marketplace", "upgrade"]:
        done(0 if words[3] in state["marketplaces"] else 1)
    if words[:2] == ["plugin", "add"]:
        market = words[2].partition("@")[2]
        if market not in state["marketplaces"]:
            done(1, f"marketplace {{market}} not found")
        state["plugins"] = [plugin for plugin in state["plugins"] if plugin != words[2]] + [words[2]]
        (folder / "plugins" / "cache" / market / "text-to-cad" / "stand-in").mkdir(parents=True, exist_ok=True)
        save(); done(0, f"Added {{words[2]}}")
    if words[:2] == ["plugin", "remove"]:
        if words[2] not in state["plugins"]:
            done(1, "not installed")
        state["plugins"].remove(words[2]); save(); done(0)
    done(0)
if name == "git":
    if "ls-remote" in args:
        done(0, "a" * 40 + "\trefs/heads/latest")
    if "status" in args:
        done(0, "## latest...origin/latest")
    if "clone" in args:
        target = Path(args[-1])
        (target / ".git").mkdir(parents=True)
        (target / ".git" / "config").write_text('[remote "origin"]\n\turl = ' + args[-2] + "\n")
        for part in ("skills", ".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            if (Path({repo!r}) / part).is_dir():
                shutil.copytree(Path({repo!r}) / part, target / part)
    done(0)
done(0)
'''


class Failed(Exception):
    pass


def default_free() -> bool:
    """Whether the true default port is free here: bound for a moment on loopback and on every interface (a listener
    on either takes a loopback client's traffic), nothing connected to."""
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket() as probe:
            try:
                probe.bind((host, DEFAULT_PORT))
            except OSError:
                return False
    return True


def platform_state(home: Path, name: str) -> Path:
    """The platform's state folder ``name`` in ``home``, as ``cad.engine.places`` and 0.8 find it with no folder
    named: ``~/Library/Application Support`` on macOS, ``%LOCALAPPDATA%`` for 0.8 on Windows, else
    ``~/.local/state``."""
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / name
    if WINDOWS and name.startswith("cadgen"):
        return home / "AppData" / "Local" / "cadgen-state"
    return home / ".local" / "state" / name


class Computer:
    """A computer of its own (see the module): a home, its folders, the feed and the folder of wheels."""

    def __init__(self, label: str, old: str, wheels: Path, feed: Feed, uv_cache: str, seam: int | None, *,
                 named_state: bool = True, new: str = NEW) -> None:
        self.label, self.old, self.feed, self.wheels, self.new = label, old, feed, wheels, new
        # 0.10.0 on Windows keeps its state in the local application data, where its switch reads the records it
        # starts a server by: apart from this build's, so this build's setup takes the computer over itself. Its
        # computer names no state folder, so each release keeps its own where it would.
        self.alone = WINDOWS and old == ALONE_OLD
        named_state = named_state and not self.alone
        # Short, under /tmp: a server's door is a Unix socket in its folder, whose path caps near 104 bytes.
        self.work = Path(tempfile.mkdtemp(prefix=f"cr{label[:2]}.", dir=None if WINDOWS else "/tmp")).resolve()
        self.home = self.work / "home"
        self.state = self.work / "state" if named_state else platform_state(self.home, "cad")
        # Where the old release keeps its state: this computer's, or 0.10.0's own on Windows.
        self.old_state = self.home / "AppData" / "Local" / "cad-state" if self.alone else self.state
        self.port = seam or DEFAULT_PORT  # the port pages are on: the default, until a server says otherwise
        self.installed = self.work / "installer-ran"
        self.tools = self.home / ".local" / "bin"
        self.tools.mkdir(parents=True)
        uv = Path(base.find_uv())
        for name in ("uv", "uvx"):
            found = shutil.which(name) or str(uv.with_name(name + uv.suffix))
            try:
                (os.link if WINDOWS else os.symlink)(found, self.tools / Path(found).name)
            except OSError:
                shutil.copy2(found, self.tools / Path(found).name)
        stand_in = self.work / "installer.py"
        stand_in.write_text(INSTALLER, encoding="utf-8")
        dropped = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "CI", "CODEX_HOME",
                   "CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                   "XDG_BIN_HOME", "UV_INSTALL_DIR", "GITHUB_ACTIONS", "CODEX_CLI", "HERMES_HOME", "NPM_CONFIG_PREFIX",
                   "npm_config_prefix")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("CAD_", "CADGEN_")) and key not in dropped}
        system = os.environ.get("SystemRoot", r"C:\Windows")
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        feed_url = f"http://127.0.0.1:{feed.server_port}/v1"
        env.update({
            "HOME": str(self.home),
            "PATH": os.pathsep.join([str(self.tools), *([rf"{system}\System32", system] if WINDOWS
                                                        else ["/usr/bin", "/bin"])]),
            "UV_CACHE_DIR": uv_cache, "NO_PROXY": bypass, "no_proxy": bypass, "DO_NOT_TRACK": "1", "BROWSER": "true",
            "CAD_CACHE_DIR": str(self.work / "cache"), "CAD_ENGINE_DIR": str(self.work / "engine"),
            "CAD_LAUNCHER_DIR": str(self.work / "bin"), "CAD_API_URL": feed_url,
            "CAD_INSTALL_FEED": f"{feed_url}/versions", "CAD_UPDATE_FIND_LINKS": str(wheels), "UV_FIND_LINKS": str(wheels),
            "CAD_ENGINE_UPDATE_INSTALLER": f'"{sys.executable}" "{stand_in}" "{self.installed}" "{self.state}"'
            if WINDOWS else f"'{sys.executable}' '{stand_in}' '{self.installed}' '{self.state}'",
            "CADGEN_ENGINE_DIR": str(self.work / "engine-0.8"), "CADGEN_CACHE_DIR": str(self.work / "cache-0.8"),
            # No real agent app: the Codex app's bundled command, which old releases look for outside PATH, is never
            # theirs to find (a path where there is none), and install.py looks on PATH alone.
            "CODEX_CLI": str(self.work / "no-codex" / "codex"), "CAD_INSTALL_PATH_ONLY": "1",
            # The new server's first hand-over attempt at its first tending: a shipped switch here decides in seconds,
            # and a route waits no five minutes for the margin a person's computer is given.
            "CAD_ENGINE_UPDATE_FIRST_SECONDS": "0",
        })
        if named_state:
            env["CAD_STATE_DIR"] = str(self.state)
        if seam is not None:
            env["CAD_ENGINE_DEFAULT_PORT"] = env["CADGEN_ENGINE_DEFAULT_PORT"] = str(seam)
        if WINDOWS:
            env.update({"USERPROFILE": str(self.home), "APPDATA": str(self.home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(self.home / "AppData" / "Local")})
        self.env = env
        self.token = ""
        self.documents: list[str] = []
        self.pythons: list[Path] = []  # the old release's Python, which stops its server at the end

    # --- running things here ----------------------------------------------------------------------------------

    def run(self, argv: list, *, timeout: float = SECONDS, check: bool = True) -> subprocess.CompletedProcess:
        done = subprocess.run([str(part) for part in argv], env=self.env, cwd=self.work, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        if check and done.returncode != 0:
            raise Failed(f"{' '.join(map(str, argv[:6]))} ... exited {done.returncode}:\n{done.stdout}\n{done.stderr}")
        return done

    def until(self, condition, what: str, seconds: float = SECONDS):
        deadline = time.monotonic() + seconds
        while True:
            found = condition()
            if found:
                return found
            if time.monotonic() > deadline:
                raise Failed(f"{self.label}: {what}, not within {seconds:.0f} s\n{self.said()}")
            time.sleep(0.25)

    def http(self, method: str, path: str, *, body: bytes | None = None, headers: dict | None = None
             ) -> tuple[int | None, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers={"Authorization": f"Bearer {self.token}",
                                                                 **(headers or {})})
            response = connection.getresponse()
            data = response.read()
        except (OSError, http.client.HTTPException):
            return None, {}
        finally:
            connection.close()
        try:
            return response.status, json.loads(data or b"{}")
        except ValueError:
            return response.status, {"body": data[:200].decode("utf-8", "replace")}

    def said(self) -> str:
        """What the computer holds, for a failure."""
        listing = lambda path: sorted(os.listdir(path)) if path.is_dir() else []  # noqa: E731
        current = self.state / "installations" / "current"
        log = self.old_state / "update.log"
        handover = self.handover()
        return (f"computer {self.work}\n  state {self.state}: {listing(self.state)}\n"
                f"  versions {listing(self.state / 'versions')}, releases {listing(self.state / 'releases')}, "
                f"current {current.read_text(encoding='utf-8') if current.exists() else '(none)'}\n"
                f"  hand-over {handover}\n"
                + (f"  {self.old}'s update log:\n{log.read_text(encoding='utf-8', errors='replace')[-3000:]}"
                   if log.exists() else "")
                + "\n" + self.running())

    def running(self) -> str:
        """The processes running from the computer's folder, one a line."""
        if WINDOWS:
            listing = ["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"]
        else:
            listing = ["ps", "-axo", "pid=,command="]
        listed = subprocess.run(listing, capture_output=True, text=True, timeout=60).stdout
        mark = str(self.work)
        return "\n".join(line.strip() for line in listed.splitlines() if mark in line and str(os.getpid()) not in
                         line.split()[:1])

    def python(self, version: str) -> Path:
        """Version ``version``'s own Python (its server environment's)."""
        return base.interpreter(self.state / "versions" / version / "code" / "server")

    def proxy(self) -> Path:
        """The ``cad`` command: on Windows ``cad.exe``, or, where there is none, the batch file a release before 0.11
        wrote (``cad.cmd``), which an updater's run leaves in place until the hand-over's own setup writes the
        command (a stand-in here); both run the installation ``installations/current`` names."""
        folder = self.work / "bin"
        if WINDOWS and not (folder / "cad.exe").exists() and (folder / "cad.cmd").exists():
            return folder / "cad.cmd"
        return folder / ("cad.exe" if WINDOWS else "cad")

    def current(self) -> str:
        path = self.state / "installations" / "current"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def handover(self, version: str | None = None) -> dict:
        """The hand-over this build (or ``version``) owes, as its record says it; empty with none."""
        path = self.state / "versions" / (version or self.new) / "data" / "handover.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def record(self, python: Path, package: str) -> str:
        """A file opened in Recents by the release whose Python is ``python`` (``RecentStore.opened``): its id."""
        part = self.work / f"part-{len(self.documents)}.stl"
        part.write_text(STL, encoding="ascii")
        done = self.run([python, "-c", f"import sys\nfrom {package}.viewer.recents import RecentStore\n"
                         "print(RecentStore().opened(sys.argv[1])['id'])", part])
        ident = done.stdout.strip().splitlines()[-1]
        self.documents.append(ident)
        return ident

    def start(self, python: Path, package: str) -> dict:
        """The server of the release whose Python is ``python`` started as a page link starts it: its answer."""
        done = self.run([python, "-c", START.format(package=package)])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def stop_server(self, python: Path, package: str = "cad") -> None:
        """The server the client of the release whose Python is ``python`` reaches, stopped, and waited for."""
        self.run([python, "-c", f"from {package}.engine import client\nclient.request({{'op': 'stop'}}, start=False)\n"
                  "client.wait_gone(timeout=60)"], check=False, timeout=120)

    # --- the old release ----------------------------------------------------------------------------------------

    def install_old(self) -> None:
        """The old release as the install command set it up: its own ``cad setup`` through uvx, its server serving
        pages on the computer's default port, and a file in Recents."""
        self.feed.latest = self.old
        self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={self.old}", "cad", "setup"], timeout=1200)
        python = base.interpreter(self.old_state / "releases" / self.old)
        if not python.exists():
            raise Failed(f"{self.old}'s setup made no release folder\n{self.said()}")
        self.pythons.append(python)
        answer = self.start(python, "cad")
        self.token = answer["token"]
        if int(answer["port"]) != self.port:
            raise Failed(f"{self.old}'s server took port {answer['port']}, not the computer's default {self.port}")
        self.old_serves()
        self.record(python, "cad_server")

    def old_serves(self) -> dict:
        """The old release's server on the port pages are on, answering the page token they hold."""
        def found():
            status, said = self.http("GET", "/api/v1/server")
            return said if status == 200 and said.get("release") == self.old else None
        return self.until(found, f"{self.old}'s server on port {self.port} with the page token")

    def install_eight(self) -> Path:
        """0.8.4 as its install command set it up (``cadgen setup``, telemetry turned off), its server serving pages
        on the computer's default port, a file in Recents. Its Python."""
        self.run(["uvx", "--no-config", "--from", f"cadgen=={EIGHT}", "cadgen", "setup", "--no-telemetry"],
                 timeout=1200)
        eight = platform_state(self.home, "cadgen")
        record = json.loads((eight / "installations" / f"{EIGHT}.json").read_text(encoding="utf-8"))
        python = Path(record["python"])
        self.pythons.append(python)
        settings = json.loads((eight / "settings.json").read_text(encoding="utf-8"))
        if (settings.get("telemetry") or {}).get("choice") != "off":
            raise Failed(f"0.8's setup did not keep telemetry off: {settings}")
        answer = self.start(python, "cadgen")
        if int(answer["port"]) != self.port:
            raise Failed(f"0.8's server took port {answer['port']}, not the computer's default {self.port}")
        self.record(python, "cadgen")
        return python

    def eight_runs(self, python: Path) -> bool:
        """Whether 0.8's server answers at its own door, nothing started."""
        done = self.run([python, "-c", "import json\nfrom cadgen.engine import client\n"
                         "print(json.dumps(client.request({'op': 'status'}, start=False)))"], check=False, timeout=60)
        return '"ok": true' in done.stdout

    # --- arriving -----------------------------------------------------------------------------------------------

    def install_script(self) -> None:
        """``scripts/install/install.py`` as the hosted script runs it: the newest release the feed names, its
        ``cad setup`` through uvx, then the apps (none in this home)."""
        self.feed.latest = self.new
        done = self.run([sys.executable, "-I", REPO_ROOT / "scripts" / "install" / "install.py"], check=False,
                        timeout=1200)
        if done.returncode != 0:
            raise Failed(f"install.py exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n{self.said()}")

    def button(self) -> None:
        """The old release's update button, on the port pages are on."""
        self.feed.latest = self.new
        status, answer = self.http("POST", "/api/v1/local/update", body=b"{}",
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202 or (answer.get("update") or {}).get("target") != self.new:
            raise Failed(f"{self.label}: the update button answered {status}: {answer}")

    def an_hour_passes(self) -> None:
        """The old release's version feed due again, as an hour passing makes it: its ``checked`` stamp
        (``versions.json``) set back 61 minutes. A server's start does not make it due."""
        path = self.state / "versions.json"
        kept = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        kept["checked"] = time.time() - 61 * 60
        path.write_text(json.dumps(kept), encoding="utf-8")

    def automatically(self) -> None:
        """The old release's automatic update, nothing pressed: the feed names the new release and an hour passes."""
        self.feed.latest = self.new
        self.an_hour_passes()

    # --- after ------------------------------------------------------------------------------------------------

    def served(self) -> dict:
        """This build's server on the port pages are on, answering the page token they hold."""
        def found():
            status, answer = self.http("GET", "/api/v1/server")
            update = answer.get("update") or {}
            if update.get("state") == "failed":
                raise Failed(f"{self.label}: the update failed: {update.get('error')}\n{self.said()}")
            return answer if status == 200 and answer.get("release") == self.new else None
        return self.until(found, f"{self.new}'s server on port {self.port} with the page token")

    def check(self, *, gone: list[Path]) -> None:
        """What every arrival leaves (see the module); ``gone``: what the old release kept that must go."""
        self.served()
        imported = json.loads((self.state / "versions" / NEW / "data" / "format.json").read_text(encoding="utf-8"))
        if (imported.get("imported") or {}).get("kind") != "legacy":
            raise Failed(f"{self.label}: {NEW} did not take the old release's data: {imported}")
        status, listing = self.http("GET", "/api/v1/documents")
        held = {row.get("id") for row in listing.get("documents", [])}
        for document in self.documents:
            if status != 200 or document not in held:
                raise Failed(f"{self.label}: Recents lacks {document}: {status} {listing}\n{self.said()}")
            opened, envelope = self.http("GET", f"/api/v1/documents/{document}")
            if opened != 200:
                raise Failed(f"{self.label}: the document {document} does not open: {opened} {envelope}")
        settings = json.loads((self.state / "versions" / NEW / "data" / "settings.json").read_text(encoding="utf-8"))
        seen = (settings.get("whats_new") or {}).get("seen")
        if not isinstance(seen, list) or "0.11" in seen and not self.old.startswith("0.11."):
            raise Failed(f"{self.label}: What's new not decided as an updated computer's: {settings.get('whats_new')}")
        for argv in ([self.proxy(), "--version"], [self.proxy(), f"+{NEW}", "--version"]):
            said = self.run(argv, check=False)
            if said.stdout.splitlines()[:1] != [f"cad {NEW}"]:
                raise Failed(f"{self.label}: {' '.join(map(str, argv[1:]))} says {said.stdout!r} {said.stderr!r}")
        # One server: the flat door, where there is one, answered by this build's, the old one's processes gone, and
        # the old layout removed by this build's cleanup once that was safe.
        door = self.run([self.python(NEW), "-c", "import json\nfrom cad_server._internal import versions\n"
                         "print(json.dumps(versions.ask_flat({'op': 'status'})))"], check=False).stdout
        inside = str(self.state / "versions" / NEW)
        if self.old != EIGHT and inside not in door.replace("\\\\", "\\"):
            raise Failed(f"{self.label}: the flat door is not answered by {NEW}'s server: {door}\n{self.said()}")
        self.until(lambda: not [path for path in gone if path.exists()],
                   f"what {self.old} kept removed: {[str(path) for path in gone if path.exists()]}")
        left = [line for line in self.running().splitlines() if str(self.state / "releases") in line]
        if left:
            raise Failed(f"{self.label}: {self.old}'s processes still run:\n" + "\n".join(left))

    def switched(self) -> None:
        """The shipped updater's switch, as its record (``update.json``) says it: from the old release, which it would
        have gone back to, to this build, held."""
        def found() -> dict | None:
            try:
                said = json.loads((self.state / "update.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            return said if said.get("to") == self.new and "ok" in said else None
        said = self.until(found, "the switch's record")
        if (said.get("from"), said.get("ok")) != (self.old, True):
            raise Failed(f"{self.label}: the switch's record: {said}")

    def taken_over(self) -> None:
        """0.10.0 on Windows, taken over by this build's setup: its server not running beside this build's, and the
        records its own clients start a server by naming this build."""
        ten = str(self.old_state / "releases" / self.old)
        left = [line for line in self.running().splitlines() if ten in line]
        if left:
            raise Failed(f"{self.label}: {self.old}'s processes still run:\n" + "\n".join(left))
        current = (self.old_state / "installations" / "current").read_text(encoding="utf-8").strip()
        if current != self.new:
            raise Failed(f"{self.label}: {self.old}'s own records name {current!r}, not {self.new}")

    def set_up_again(self) -> None:
        """After 0.10.0's take-over, this build's real plain ``cad setup``, through the ``cad`` command, as the hand-over's
        install script runs it: the server that took over still serving its pages -- the same process, on the same
        port with the page token --, and no earlier release's stop run (the record the take-over wrote in 0.10.0's
        folder is none of 0.10.0's installations)."""
        serving = self.served()["pid"]
        done = self.run([self.proxy(), "setup"], check=False)
        if done.returncode != 0 or "`cad stop`" in done.stderr:
            raise Failed(f"{self.label}: `cad setup` after the take-over, exit {done.returncode}:\n{done.stdout}"
                         f"{done.stderr}")
        if self.served()["pid"] != serving:
            raise Failed(f"{self.label}: `cad setup` after the take-over restarted {self.new}'s server\n{self.said()}")

    def handed_over(self, attempts: int = 1) -> None:
        """The install script run by this build's server once it served -- each run's line naming this build current
        -- the hand-over recorded done after ``attempts`` attempts, and no attempt left running."""
        record = self.until(lambda: (lambda found: found if found.get("state") == "done" else None)(self.handover()),
                            "the hand-over done")
        if record.get("attempts") != attempts:
            raise Failed(f"{self.label}: the hand-over took {record.get('attempts')} attempts, not {attempts}")
        if self.installed.exists():
            runs = self.installed.read_text(encoding="utf-8").splitlines()
            if len(runs) != attempts or {line.split()[-1] for line in runs} != {NEW}:
                raise Failed(f"{self.label}: the install script ran {runs}, not once with {NEW} current")
        self.until(lambda: "install_script" not in self.running(), "the hand-over's program ended")

    def stop(self) -> None:
        """Every server of the computer stopped, and anything still running from its folder ended."""
        versions = self.state / "versions"
        for version in (sorted(os.listdir(versions)) if versions.is_dir() else []):
            if self.python(version).exists():
                self.run([self.python(version), "-c", f"from cad_server._internal import versions\n"
                          f"versions.ask({version!r}, {{'op': 'stop'}})"], check=False, timeout=60)
        for python in self.pythons:
            if python.exists():
                package = "cadgen" if "cadgen" in str(python) else "cad"
                self.run([python, "-c", f"from {package}.engine import client\n"
                          "client.request({'op': 'stop'}, start=False)"], check=False, timeout=60)
        if not WINDOWS:
            for line in self.running().splitlines():
                pid = line.split(None, 1)[0]
                if pid.isdigit() and int(pid) != os.getpid():
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except OSError:
                        pass
        # A worker of 0.8's server that was still loading its kernel as the server stopped writes its bytecode into
        # 0.8's cache as it finishes, then exits (its command line names no folder of this computer's, so nothing above
        # ends it): the folder is removed again until it stays gone.
        deadline = time.monotonic() + 180
        while True:
            shutil.rmtree(self.work, ignore_errors=True)
            time.sleep(3)
            if not self.work.exists() or time.monotonic() > deadline:
                break


def legacy_layout(computer: Computer) -> list[Path]:
    """What the layout of 0.11.10 and earlier keeps that this build's cleanup removes once it is safe."""
    state, cache = computer.state, computer.work / "cache"
    return [state / "releases", state / "documents", state / "recents",
            *(cache / name for name in ("base", "documents", "pycache"))]


# --- the routes -----------------------------------------------------------------------------------------------------


def updater(computer: Computer) -> None:
    """The shipped release's own updater, by its button (see the module); for 0.10.0 on Windows, this build's setup
    taking the computer over (``alone``)."""
    computer.install_old()
    computer.button()
    computer.check(gone=legacy_layout(computer))
    if computer.alone:
        computer.taken_over()
    else:
        computer.switched()
    computer.handed_over()
    if computer.alone:
        computer.set_up_again()


def automatic(computer: Computer) -> None:
    """The shipped release's own updater, by itself (see the module)."""
    computer.install_old()
    computer.automatically()
    computer.check(gone=legacy_layout(computer))
    computer.switched()
    computer.handed_over()


def apps(computer: Computer) -> dict:
    """What the stand-ins of Claude Code and Codex hold of ours: each one's plugins, and its catalogs."""
    claude, codex = computer.home / ".claude" / "plugins", computer.home / ".codex" / ".stand-in.json"
    read = lambda path: json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}  # noqa: E731
    held = read(codex)
    return {"claude": (sorted((read(claude / "installed_plugins.json").get("plugins") or {})),
                       sorted(read(claude / "known_marketplaces.json"))),
            "codex": (sorted(held.get("plugins") or []), sorted(held.get("marketplaces") or {}))}


def handover(computer: Computer) -> None:
    """The real install script in the hand-over, failing once, then again at the next server start (see the module)."""
    calls = computer.work / "app-calls.jsonl"
    for name in ("claude", "codex", "git"):
        path = computer.tools / name
        path.write_text(APPS.format(python=sys.executable, calls=str(calls), repo=str(REPO_ROOT),
                                    failed_once=str(computer.work / "claude-failed-once")), encoding="utf-8")
        path.chmod(0o755)
    computer.env.update({"CODEX_CLI": str(computer.tools / "codex"),
                         "CAD_ENGINE_UPDATE_INSTALLER": f"sh '{REPO_ROOT / 'scripts' / 'install' / 'install.sh'}'",
                         "CAD_INSTALL_PY": str(REPO_ROOT / "scripts" / "install" / "install.py")})
    computer.install_old()
    old = {"claude": (["text-to-cad@text-to-cad"], ["text-to-cad"]), "codex": (["text-to-cad@text-to-cad"],
                                                                             ["text-to-cad"])}
    if apps(computer) != old:
        raise Failed(f"{computer.label}: {computer.old}'s setup left the apps holding {apps(computer)}, not {old}")
    computer.button()
    computer.served()
    computer.switched()
    # The first attempt: Claude Code's add of the GitHub catalog fails, so the attempt does, and the old copy stays.
    record = computer.until(lambda: (lambda found: found if found.get("outcome") == "app" else None)(computer.handover()),
                            "the first attempt failed by an app's step")
    if (record["state"], record["attempts"]) != ("owed", 1) or apps(computer)["claude"] != old["claude"]:
        raise Failed(f"{computer.label}: after the failed attempt: {record}, Claude Code holds {apps(computer)['claude']}")
    computer.until(lambda: "install_script" not in computer.running(), "the first attempt's program ended")
    # An hour later, the server starts again (the computer restarted): the next attempt, which holds.
    computer.stop_server(computer.python(NEW))
    path = computer.state / "versions" / NEW / "data" / "handover.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**record, "last": record["last"] - 3700, "first": record["first"] - 3700}),
                    encoding="utf-8")
    computer.start(computer.python(NEW), "cad")
    computer.handed_over(attempts=2)
    new = {"claude": (["text-to-cad@earthtojake"], ["earthtojake"]), "codex": (["text-to-cad@earthtojake"],
                                                                              ["earthtojake"])}
    if apps(computer) != new:
        raise Failed(f"{computer.label}: after the hand-over the apps hold {apps(computer)}, not {new}")
    report = json.loads((path.parent / "install-report.json").read_text(encoding="utf-8"))
    if (report["release"], report["setup"]) != (NEW, 0) or "failed" in report["apps"].values() \
            or {report["apps"].get("claude"), report["apps"].get("codex")} - {"installed", "updated"}:
        raise Failed(f"{computer.label}: the install script's report: {report}")
    computer.check(gone=legacy_layout(computer))


def rollback(computer: Computer) -> None:
    """The automatic update to a build whose server cannot start, gone back from; and its retry a day later (see the
    module)."""
    computer.install_old()
    computer.automatically()

    def gone_back() -> dict | None:
        try:
            found = json.loads((computer.state / "update.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return found if found.get("to") == BROKEN and "restored" in found else None
    result = computer.until(gone_back, f"the switch to {BROKEN} gone back from")
    if (result.get("ok"), result.get("restored"), result.get("from")) != (False, True, computer.old):
        raise Failed(f"{computer.label}: the switch did not go back to {computer.old}: {result}")
    stays(computer, "after the switch went back")
    # A day later: the automatic attempt due again, the failure no longer news to a server starting, the feed due, and
    # the old server started again (the computer restarted). 0.11.10's own tending removes the flat folder of a
    # release its last switch failed to move to (``releases.discard``), the one this attempt makes again, while the
    # attempt waits for its server to be idle: the attempt then fails before any switch. Either way the computer stays
    # as it was.
    began = time.time()
    path = computer.state / "update-automatic.json"
    kept = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**kept, "at": kept["at"] - 86_500}), encoding="utf-8")
    os.utime(computer.state / "update.json", (began - 3_600, began - 3_600))
    computer.stop_server(computer.pythons[0])
    computer.an_hour_passes()
    computer.start(computer.pythons[0], "cad")

    def tried_again() -> dict | None:
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return found if found.get("release") == BROKEN and found.get("at", 0) >= began and found.get("error") else None
    computer.until(tried_again, f"the automatic attempt of {BROKEN} a day later, ended")
    switch = json.loads((computer.state / "update.json").read_text(encoding="utf-8"))
    if switch.get("ok") is not False or (switch != result and not switch.get("restored")):
        raise Failed(f"{computer.label}: a day later, the switch's record: {switch}")
    stays(computer, "a day later")


def stays(computer: Computer, when: str) -> None:
    """The computer as the old release left it, ``when``: its server on the pages' port with their token,
    ``installations/current`` and the ``cad`` command its own, the install script never run, and nothing of the build
    that could not serve running."""
    computer.old_serves()
    if computer.current() != computer.old:
        raise Failed(f"{computer.label}: {when}: current names {computer.current()!r}, not {computer.old}")
    said = computer.run([computer.proxy(), "--version"], check=False)
    if said.stdout.splitlines()[:1] != [f"cad {computer.old}"]:
        raise Failed(f"{computer.label}: {when}: the cad command says {said.stdout!r} {said.stderr!r}")
    owed = computer.handover(BROKEN)
    if (owed.get("state"), owed.get("attempts")) != ("owed", 0) or computer.installed.exists():
        raise Failed(f"{computer.label}: {when}: the install script ran for a build that never served: {owed}")
    left = [line for line in computer.running().splitlines()
            if str(computer.state / "versions" / BROKEN) in line or "install_script" in line]
    if left:
        raise Failed(f"{computer.label}: {when}: processes of {BROKEN} still run:\n" + "\n".join(left))


def install_script(computer: Computer) -> None:
    """``install.py`` on a computer of the shipped release, its server serving pages (see the module)."""
    computer.install_old()
    computer.install_script()
    if computer.current() != NEW:
        raise Failed(f"{computer.label}: the records {computer.old}'s clients read name {computer.current()!r}, not {NEW}")
    # The old server, asked to stop once idle, goes; the next command starts this build's, on the port it served
    # pages on (free now), with the page token this build imported.
    computer.until(lambda: computer.http("GET", "/api/v1/server")[0] is None, f"{computer.old}'s server stopped")
    answer = computer.start(computer.python(NEW), "cad")
    if (int(answer["port"]), answer["token"]) != (computer.port, computer.token):
        raise Failed(f"{computer.label}: {NEW}'s server serves on {answer['port']} "
                     f"{'with' if answer['token'] == computer.token else 'without'} the page token")
    computer.check(gone=legacy_layout(computer))
    if computer.installed.exists() or computer.handover():
        raise Failed(f"{computer.label}: cad setup owed or started the install script")


def from_eight(computer: Computer) -> None:
    """0.8.4, then ``install.py`` (see the module)."""
    eight = computer.install_eight()
    computer.install_script()
    if computer.eight_runs(eight):
        raise Failed(f"{computer.label}: 0.8's server still runs after this build's setup\n{computer.said()}")
    answer = computer.start(computer.python(NEW), "cad")
    computer.token = answer["token"]
    if int(answer["port"]) != computer.port:
        raise Failed(f"{computer.label}: {NEW}'s server took port {answer['port']}, not {computer.port}, "
                     "which 0.8's served")
    computer.check(gone=[computer.state / "documents", computer.state / "recents"])
    settings = json.loads((computer.state / "versions" / NEW / "data" / "settings.json").read_text(encoding="utf-8"))
    if ((settings.get("telemetry") or {}).get("choice"), settings.get("whats_new")) != ("off", {"seen": []}):
        raise Failed(f"{computer.label}: 0.8's telemetry no or an updated computer's What's new was lost: {settings}")


def main(argv: list[str] | None = None) -> int:
    routes = {"updater": updater, "automatic": automatic, "handover": handover, "rollback": rollback,
              "install-script": install_script, "from-0.8": from_eight}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("routes", nargs="*", default=["all"], choices=("all", *routes), metavar="ROUTE",
                        help=f"one or more of: all, {', '.join(routes)}")
    parser.add_argument("--old", default=OLD, help="the shipped release every route but from-0.8 starts on")
    args = parser.parse_args(argv)
    # A failed route prints what its programs said: a character this output's encoding has not (Windows' code page)
    # is printed escaped, never raised in place of the failure.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if shutil.which("uv") is None and shutil.which("uvx") is None:
        print("rehearse-update: uv is not installed", file=sys.stderr)
        return 1
    uv_cache = os.environ.get("UV_CACHE_DIR") or subprocess.run(
        [base.find_uv(), "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
    chosen = list(routes) if "all" in args.routes else list(dict.fromkeys(args.routes))
    seam = None if default_free() else free_port()
    print(f"rehearse-update: {', '.join(chosen)}, into {NEW}; the default port is "
          + (f"{DEFAULT_PORT}" if seam is None else f"{seam} ({DEFAULT_PORT} is in use here)"), flush=True)
    wheels = Path(tempfile.mkdtemp(prefix="crw.")).resolve()
    release(NEW, wheels)
    if "rollback" in chosen:
        release(BROKEN, wheels, replace={"cad_server/_internal/engine_daemon.py": BROKEN_DAEMON})
    feed = Feed()
    threading.Thread(target=feed.serve_forever, daemon=True).start()
    failed = 0
    try:
        for name in chosen:
            if name == "handover" and WINDOWS:  # its stand-ins of the apps are scripts run by their #! line
                print("skipped handover: a POSIX route", flush=True)
                continue
            old = EIGHT if name == "from-0.8" else args.old
            computer = Computer(name, old, wheels, feed, uv_cache, seam, named_state=name != "from-0.8",
                                new=BROKEN if name == "rollback" else NEW)
            began = time.monotonic()
            try:
                routes[name](computer)
                print(f"ok      {name}, from {old} ({time.monotonic() - began:.0f} s)", flush=True)
            except (Failed, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as failure:
                failed += 1
                print(f"FAILED  {name}, from {old} ({time.monotonic() - began:.0f} s): {failure}", flush=True)
            finally:
                computer.stop()
    finally:
        feed.shutdown()
        feed.server_close()
        forget(Path(uv_cache), (NEW, BROKEN))
        shutil.rmtree(wheels, ignore_errors=True)
    ran = len(chosen) - (WINDOWS and "handover" in chosen)
    print(f"rehearse-update: {ran - failed} held, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
