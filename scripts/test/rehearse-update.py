#!/usr/bin/env python3
"""The updates a real device makes into this build, and out of it, rehearsed on private devices.

0.11.10 is frozen on every device: its updater makes a flat ``releases/<release>`` for the release it moves to,
runs that folder's ``cad setup --engine-update`` (first with ``CAD_UPDATE_PREPARE=1`` for an automatic update), and
then drains its server and has its helper start the new release's through ``installations/current`` and the flat
door. This script installs a release from PyPI into a device of its own -- its own home, state, engine, cache and
``cad`` command folders (``CAD_STATE_DIR``, ``CAD_ENGINE_DIR``, ``CAD_CACHE_DIR``, ``CAD_LAUNCHER_DIR``), never this
machine's --, publishes this checkout as later releases (its wheels in a folder uv reads beside the index,
``CAD_UPDATE_FIND_LINKS`` and ``UV_FIND_LINKS``; the version feed a local stand-in, ``CAD_API_URL``), built from a
copy of the tree in which the quiet period an automatic update waits for (``auto_updates.IDLE_SECONDS``) is
``QUIET`` seconds rather than an hour, and drives each path:

- ``automatic``: 0.11.10's own background update (its feed read, its minute of quiet, its prepare step);
- ``button``: the update button's request, ``POST /api/v1/local/update``, to 0.11.10's server;
- ``command``: 0.11.10's ``cad update``, through the ``cad`` command 0.11.10 wrote;
- ``reinstall``: the install command run again (``uvx ... --from cad-server==<release> cad setup``, what
  ``install.sh`` runs), which drains 0.11.10's server and takes its port;
- ``interrupted``: this build's setup killed (``os._exit``: nothing after it runs) before the import is marked,
  before the pointer is written, and after it, each followed by 0.11.10's update button, which completes it; and the
  second update killed during the removal of the version it leaves, followed by the same setup again;
- ``own-automatic``: this build updating itself to a later build of itself by its own automatic path: the release
  installed in the background, the server tending (and sweeping: an earlier removal's leftover is planted for it)
  all through the quiet period, a person's ``cad status`` every few seconds putting the update off, then the setup
  once it is quiet; the installed release never removed while it waited;
- ``in-flight``: work going on while 0.11.10, and then this build, is updated: a build held open across the update
  (it must run to its end in the server it started on), and a document opened in Recents by the old server after
  the new version imported its data (it must be in the new version, and the old version or layout removed only
  after it was carried over). This build's own update with a build in flight ends as ``moved``: the new server takes
  the next port, which the page goes to, and the old server, as it stops once its build ends, hands the pages' port
  to the new one, which then answers there with the same token;
- ``early-server``: new skill text before the new software (the design's H4): on a device on 0.11.10 with its server
  serving pages, ``cad setup --add`` and a pinned command of this build (which moves the default channel and leaves
  0.11.10's server running), this build's server up on the next port with a page and a build held open, then
  0.11.10's own update button: this build's server is never stopped, its build runs to its end, and it ends up
  serving the port pages were on as well;
- ``app-behind``: an app an update could not reach: Codex (a stand-in of its command, ``CODEX``) set up from a
  person's terminal, which has its command, and the update run by a server an app started, whose environment lacks
  it: the receipt records Codex behind, ``cad doctor`` names it, and ``cad update`` from the terminal repairs it;
- ``from-0.10``: 0.10.4, the newest 0.10 release, by its update button, its ``cad update`` and the install command
  run again (0.10 has no automatic update, and a minor release is never taken by one).

After each it checks: the default pointer; the mirror (``installations/current`` and its record); the port pages were
on and the page token (``GET /api/v1/server`` answers the old token with the new release); Recents (a file the old
release recorded) and that document opening (``GET /api/v1/documents/<id>``); the layout of 0.11.10 removed and the
files kept for its clients present; the flat door answering a client of the old release; and the ``cad`` command with
no pin. Most paths add a second update on top, by the new server's own button.

Ports: no process is given a port by name (``CAD_ENGINE_PORT`` is refused, never rolled, when it is held). Each
device's servers take the default port and roll from it as on a person's computer: the true default, 3245, where it
is free on this machine (CI), else a free port of the device's own as its default (``CAD_ENGINE_DEFAULT_PORT``, the
seam every release since 0.10 reads), so a server this script did not start is never asked anything.

Usage: scripts/test/rehearse-update.py [SCENARIO ...] [--old RELEASE] (default: all, from 0.11.10; ``--old``
rehearses another release before this build that updates itself, as 0.11.0, for the paths that start on 0.11.10).
It needs uv, the network (PyPI, for the old releases and the packages every release depends on; uv's cache holds
them after the first run) and loopback ports. It never sets ``CAD_UPDATE_CHECK=0``: the update is what it rehearses,
against the local feed. The release tier of ``.github/workflows/test.yml`` runs it on Linux, macOS and Windows
(``update-rehearsal``). Exit 0 when every path held; 1, with what the device holds, when one did not.
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

from tests.python.packages.cad_server import test_update_end_to_end as published  # noqa: E402
from tests.python.packages.cad_server.test_update_end_to_end import Feed, forget, free_port, release  # noqa: E402

from cad_server._internal import base  # noqa: E402
from cad_server._internal.launch import LAUNCHER  # noqa: E402

OLD = "0.11.10"
# The newest 0.10 release: what a device that never took 0.11 runs (0.10 has no automatic update).
OLD_10 = "0.10.4"
WINDOWS = os.name == "nt"
# This checkout, as three releases a release before it takes by itself (a patch) and no index will ever hold.
_RUN = os.getpid() % 900
NEW, NEWER, THIRD = f"0.11.{9000 + 3 * _RUN}", f"0.11.{9001 + 3 * _RUN}", f"0.11.{9002 + 3 * _RUN}"
# How long each wait may take: an install from uv's cache, 0.11.10's 30-second tend and minute of quiet.
SECONDS = 600.0
# The quiet period an automatic update of this build waits for, in the releases built here (an hour in a release).
QUIET = 40.0
# The default port, and how the script finds it free: bound for a moment on loopback and on every interface, nothing
# connected to (a server there is never asked anything).
DEFAULT_PORT = 3245
POINTS = ("before-the-import-is-marked", "before-the-pointer", "after-the-pointer")
# A document's file, a binary-free STL a page opens.
STL = ("solid p\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\n"
       "endsolid p\n")

# This build's setup run by a version's own Python, killed at one point (``os._exit``).
KILL = """
import os, shutil, sys
point = sys.argv[1]
from cad._internal import atomic_replace
from cad_server._internal import imports, pointers, versions
if point == "before-the-import-is-marked":
    original = atomic_replace.write_bytes_atomic
    def marked(path, data, *args, **kwargs):
        if str(path).endswith(imports.MARKER):
            os._exit(9)
        return original(path, data, *args, **kwargs)
    atomic_replace.write_bytes_atomic = marked
elif point == "before-the-pointer":
    pointers.write = lambda *args, **kwargs: os._exit(9)
elif point == "after-the-pointer":
    pointers.mirror = lambda *args, **kwargs: os._exit(9)
elif point == "during-removal":
    remove = shutil.rmtree
    def removing(path, *args, **kwargs):
        if versions.TRASH in str(path):
            os._exit(9)
        return remove(path, *args, **kwargs)
    shutil.rmtree = removing
from cad_server.cli import setup
sys.exit(setup.main(["--engine-update"]))
"""

# A question asked of a version's server through its own door by that version's Python, marked internal (no
# command of the person's: ``versions.ask``).
ASK = ("import json, sys\nfrom cad_server._internal import versions\n"
       "print(json.dumps(versions.ask(sys.argv[1], json.loads(sys.argv[2]), seconds=float(sys.argv[3]))))")

# A model whose build is held open until the script says: it marks its start, waits for ``release``, marks its end,
# and makes a box. Its worker is this script's own Python (``contract.interpreter``: a release's server builds in the
# Python an order names, under an equal worker contract), which has the CAD kernel.
HELD = """
import time
from pathlib import Path

from cad import model


@model
def held():
    here = Path(__file__).parent
    (here / "started").write_text("", encoding="utf-8")
    while not (here / "release").exists():
        time.sleep(0.05)
    import build123d as bd

    (here / "ended").write_text("", encoding="utf-8")
    return bd.Box(1, 1, 1)
"""
# That build asked of one server through its door -- a version's own (``argv[2]``), or the flat one of 0.11.10 and
# earlier (``flat``) --, nothing started, its answer printed.
BUILD = """
import json, os, sys
from cad.engine import client, contract, places
project, name = sys.argv[1], sys.argv[2]
folder = places.engines_dir() if name == "flat" else places.engine_dir(name)
door = folder / f"{places.NAME}.{'port' if places.WINDOWS else 'door'}"
order = {"op": "build", "script": os.path.join(project, "model.py"), "functions": ["held"], "cwd": project,
         "env": dict(os.environ), "interpreter": contract.interpreter()}
connection = client._connect(door)
print(json.dumps(None if connection is None else client._exchange(connection, order, address=door)))
"""


# A stand-in for Codex's command (``codex``), as the apps step of a setup drives it: a local catalog added
# (``plugin marketplace add <folder>``) or removed, the plugin copied from it into Codex's plugin cache (``plugin add
# <plugin>@<catalog>``), each recorded where Codex keeps it (``config.toml``'s ``marketplaces`` and ``plugins``, and
# ``plugins/cache/<catalog>/<plugin>/<version>``), which is all a setup reads of Codex.
CODEX = """
import json, os, shutil, sys
from pathlib import Path
home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
home.mkdir(parents=True, exist_ok=True)
state = home / "stand-in.json"
kept = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {"marketplaces": {}, "plugins": []}
args = sys.argv[1:]
with open(home / "stand-in.log", "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if args[:3] == ["plugin", "marketplace", "add"]:
    kept["marketplaces"]["text-to-cad"] = os.path.abspath(args[3])
elif args[:3] == ["plugin", "marketplace", "remove"]:
    kept["marketplaces"].pop(args[3], None)
    kept["plugins"] = [plugin for plugin in kept["plugins"] if not plugin.endswith("@" + args[3])]
elif args[:2] == ["plugin", "add"]:
    plugin, market = args[2].split("@", 1)
    folder = Path(kept["marketplaces"][market])
    version = json.loads((folder / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    target = home / "plugins" / "cache" / market / plugin / version
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(folder, target)
    kept["plugins"] = [*[other for other in kept["plugins"] if other != args[2]], args[2]]
elif args[:2] == ["plugin", "list"]:
    print("[]")
    sys.exit(0)
else:
    print(f"stand-in codex: {args} is not something a setup asks", file=sys.stderr)
    sys.exit(2)
state.write_text(json.dumps(kept), encoding="utf-8")
lines = []
for name, folder in kept["marketplaces"].items():
    lines += [f"[marketplaces.{json.dumps(name)}]", 'source_type = "local"', f"source = {json.dumps(folder)}", ""]
for plugin in kept["plugins"]:
    lines += [f"[plugins.{json.dumps(plugin)}]", "enabled = true", ""]
(home / "config.toml").write_text("\\n".join(lines), encoding="utf-8")
"""


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


def publish(wheels: Path, versions: tuple[str, ...]) -> None:
    """``versions`` published to ``wheels``, built from a copy of this tree (``published.DISTRIBUTIONS`` pointed at
    it) in which an automatic update's quiet period is ``QUIET`` seconds: the one change, made where it is said
    (``auto_updates.IDLE_SECONDS``), and refused should that line not be there exactly once."""
    tree = wheels.parent / f"{wheels.name}-tree"
    copies = {}
    for distribution, (source, packages, roots) in published.DISTRIBUTIONS.items():
        target = tree / source.name
        (target / "src").mkdir(parents=True)
        for name in ("pyproject.toml", *roots):
            shutil.copy2(source / name, target / name)
        for top in packages:
            shutil.copytree(source / "src" / top, target / "src" / top,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_runtime"))
        copies[distribution] = (target, packages, roots)
    quiet = tree / "cad-server" / "src" / "cad_server" / "auto_updates.py"
    text = quiet.read_text(encoding="utf-8")
    line = "IDLE_SECONDS = 60 * 60.0"
    if text.count(line) != 1:
        raise SystemExit(f"rehearse-update: {quiet} no longer says {line!r} once: say how the quiet period is set")
    quiet.write_text(text.replace(line, f"IDLE_SECONDS = {QUIET!r}"), encoding="utf-8")
    kept = dict(published.DISTRIBUTIONS)
    published.DISTRIBUTIONS.update(copies)
    try:
        for version in versions:
            release(version, wheels)
    finally:
        published.DISTRIBUTIONS.update(kept)
        shutil.rmtree(tree, ignore_errors=True)


class Device:
    """A device of its own, with an old release installed by the install command's own step, its server serving
    pages on the device's default port."""

    def __init__(self, label: str, old: str, wheels: Path, feed: Feed, uv_cache: str, seam: int | None) -> None:
        self.label = label
        self.old = old
        # Short, under /tmp: a server's door is a Unix socket in its folder, whose path caps near 104 bytes.
        self.work = Path(tempfile.mkdtemp(prefix=f"cr{label[:2]}.", dir=None if WINDOWS else "/tmp")).resolve()
        self.state = self.work / "state"
        self.feed = feed
        self.default = seam or DEFAULT_PORT
        self.port = self.default  # the port pages are on: the default, until a server says otherwise
        self.wheels = wheels
        home = self.work / "home"
        tools = home / ".local" / "bin"
        tools.mkdir(parents=True)
        uv = Path(base.find_uv())
        for name in ("uv", "uvx"):
            found = shutil.which(name) or str(uv.with_name(name + uv.suffix))
            try:
                (os.link if WINDOWS else os.symlink)(found, tools / Path(found).name)
            except OSError:
                shutil.copy2(found, tools / Path(found).name)
        dropped = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "CI", "CODEX_HOME",
                   "CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                   "XDG_BIN_HOME", "UV_INSTALL_DIR", "GITHUB_ACTIONS")
        env = {key: value for key, value in os.environ.items() if not key.startswith("CAD_") and key not in dropped}
        system = os.environ.get("SystemRoot", r"C:\Windows")
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        env.update({
            "HOME": str(home),
            "PATH": os.pathsep.join([str(tools), *([rf"{system}\System32", system] if WINDOWS else ["/usr/bin", "/bin"])]),
            "UV_CACHE_DIR": uv_cache, "NO_PROXY": bypass, "no_proxy": bypass, "DO_NOT_TRACK": "1", "BROWSER": "true",
            "CODEX_CLI": str(self.work / "no-codex"), "CAD_STATE_DIR": str(self.state),
            "CAD_CACHE_DIR": str(self.work / "cache"), "CAD_ENGINE_DIR": str(self.work / "engine"),
            "CAD_LAUNCHER_DIR": str(self.work / "bin"),
            "CAD_API_URL": f"http://127.0.0.1:{feed.server_port}/v1", "CAD_UPDATE_FIND_LINKS": str(wheels),
            "UV_FIND_LINKS": str(wheels),
        })
        if seam is not None:
            env["CAD_ENGINE_DEFAULT_PORT"] = str(seam)
        if WINDOWS:
            env.update({"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(home / "AppData" / "Local")})
        self.env = env
        self.token = ""
        self.document = ""
        self.old_client: list[str] = []
        self.helds: list[Held] = []
        self.kept: list[str] = []

    # --- running things here ----------------------------------------------------------------------------------

    def run(self, argv: list, *, timeout: float = SECONDS, check: bool = True, env: dict | None = None
            ) -> subprocess.CompletedProcess:
        done = subprocess.run([str(part) for part in argv], env=env or self.env, cwd=self.work, stdin=subprocess.DEVNULL,
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
                raise Failed(f"{self.label}: {what}, not within {seconds:.0f} s\n{self.state_said()}")
            time.sleep(0.25)

    def server(self, token: str | None = None, port: int | None = None) -> tuple[int | None, dict]:
        """``GET /api/v1/server`` on the port pages are on, as a page asks it."""
        return self.http("GET", "/api/v1/server", token=token, port=port)

    def http(self, method: str, path: str, *, token: str | None = None, body: bytes | None = None,
             headers: dict | None = None, port: int | None = None) -> tuple[int | None, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers={"Authorization": f"Bearer {token or self.token}",
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

    def read(self, inside: str) -> str:
        path = self.state / inside
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def state_said(self) -> str:
        """What the device holds, for a failure: the pointer, the mirror, the folders, the old release's update log."""
        listing = lambda path: sorted(os.listdir(path)) if path.is_dir() else []  # noqa: E731
        log = self.state / "update.log"
        return (f"device {self.work}\n  default {self.read('default')!r}, current {self.read('installations/current')!r}\n"
                f"  versions {listing(self.state / 'versions')}, releases {listing(self.state / 'releases')}\n"
                f"  state {listing(self.state)}\n"
                + (f"  {self.old}'s update log:\n{log.read_text(encoding='utf-8', errors='replace')[-3000:]}"
                   if log.exists() else ""))

    def python(self, version: str) -> Path:
        """Version ``version``'s own Python (its server environment's)."""
        return base.interpreter(self.state / "versions" / version / "code" / "server")

    def ask(self, version: str, message: dict, seconds: float = 10.0) -> dict | None:
        """``message`` asked of version ``version``'s server through its own door by that version's Python, marked
        internal (``versions.ask``): its answer, or None."""
        if not self.python(version).exists():
            return None
        done = self.run([self.python(version), "-c", ASK, version, json.dumps(message), seconds], check=False,
                        timeout=seconds + 60)
        try:
            found = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return found if isinstance(found, dict) else None

    def pid(self, version: str) -> int | None:
        found = (self.ask(version, {"op": "pid"}) or {}).get("pid")
        return found if type(found) is int else None

    # --- the old release ----------------------------------------------------------------------------------------

    def install_old(self, shell: dict | None = None) -> None:
        """The old release as the install command sets it up: its own `cad setup` through uvx (in the environment
        ``shell``, a person's terminal's, where given), its server started as a client starts it, serving pages on the
        device's default port; a file it recorded in Recents."""
        self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={self.old}", "cad", "setup"], timeout=1200,
                 env=shell)
        python = base.interpreter(self.state / "releases" / self.old)
        if not python.exists():
            raise Failed(f"{self.old}'s setup made no release folder\n{self.state_said()}")
        started = self.run([python, "-c", "import json\nfrom cad.engine import client\n"
                            "print(json.dumps(client.request({'op': 'http'})))"])
        answer = json.loads(started.stdout.strip().splitlines()[-1])
        self.token, self.port = answer["token"], int(answer["port"])
        if self.port != self.default:
            raise Failed(f"{self.old}'s server took port {self.port}, not the device's default {self.default}")
        status, answer = self.server()
        if status != 200 or answer.get("release") != self.old:
            raise Failed(f"{self.old}'s server does not answer on {self.port}: {status} {answer}")
        part = self.work / "part.stl"
        part.write_text(STL, encoding="ascii")
        recorded = self.run([python, "-c", "import sys\nfrom cad_server.viewer.recents import RecentStore\n"
                             "print(RecentStore().opened(sys.argv[1])['id'])", part])
        self.document = recorded.stdout.strip().splitlines()[-1]
        self.kept = [name for name in ("settings.json", "engines/token") if (self.state / name).exists()]
        # A client of the old release of its own, outside the device's folders, as an app's launcher of it is.
        client = self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={self.old}", "python", "-c",
                           "import sys; print(sys.executable)"], timeout=1200)
        self.old_client = [client.stdout.strip().splitlines()[-1]]

    def codex_shell(self) -> dict:
        """A person's terminal on a device with Codex: the stand-in ``codex`` command (``CODEX``) found there
        (``CODEX_CLI``), as it is not in the environment of a server an app started. That environment."""
        folder = self.work / "apps"
        folder.mkdir(exist_ok=True)
        script = folder / "codex.py"
        script.write_text(CODEX, encoding="utf-8")
        if WINDOWS:
            command = folder / "codex.cmd"
            command.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        else:
            command = folder / "codex"
            command.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n", encoding="utf-8")
            command.chmod(0o755)
        return {**self.env, "CODEX_CLI": str(command)}

    def codex_copy(self) -> list[str]:
        """The versions of our plugin Codex's cache holds (``plugins/cache/text-to-cad/text-to-cad/<version>``)."""
        cache = Path(self.env["HOME"]) / ".codex" / "plugins" / "cache" / "text-to-cad" / "text-to-cad"
        return sorted(os.listdir(cache)) if cache.is_dir() else []

    def behind(self) -> dict:
        """The apps the receipt records behind."""
        try:
            return json.loads(self.read("install-receipt.json") or "{}").get("behind") or {}
        except ValueError:
            return {}

    def old_door(self) -> dict | None:
        """The flat door, as a client of the old release asks it: the status of the server there, nothing started."""
        done = self.run([*self.old_client, "-c", "import json\nfrom cad.engine import client\n"
                         "print(json.dumps(client.request({'op': 'status'}, start=False)))"], check=False, timeout=60)
        try:
            return json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None

    def proxy(self) -> Path:
        """The device's ``cad`` command. On Windows it is ``cad.exe``; a release of 0.10 wrote ``cad.cmd`` there, which
        is the command until an update writes ``cad.exe``."""
        folder = self.work / "bin"
        if WINDOWS and not (folder / "cad.exe").exists() and (folder / "cad.cmd").exists():
            return folder / "cad.cmd"
        return folder / ("cad.exe" if WINDOWS else "cad")

    def opened(self, name: str, port: int | None = None) -> str:
        """A page opening a new file in Recents (``PATCH /api/v1/documents``) on the server at ``port``: the server
        writes its record. The document's id."""
        part = self.work / f"{name}.stl"
        part.write_text(STL.replace("solid p", f"solid {name}"), encoding="ascii")
        status, answer = self.http("PATCH", "/api/v1/documents", port=port,
                                   body=json.dumps({"action": "open", "path": str(part)}).encode(),
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 200:
            raise Failed(f"{self.label}: opening {part} in Recents on port {port or self.port} answered {status}: {answer}")
        rows = [row for row in (answer.get("documents") or []) if str(row.get("path") or row.get("home") or "")
                .endswith(f"{name}.stl") or row.get("name") == f"{name}.stl"]
        found = rows[0].get("id") if rows else None
        if not found:
            status, listing = self.http("GET", "/api/v1/documents", port=port)
            rows = [row for row in listing.get("documents", []) if row.get("name") == f"{name}.stl"]
            found = rows[0].get("id") if rows else None
        if not found:
            raise Failed(f"{self.label}: {name}.stl is not in Recents after it was opened: {answer}")
        return found

    # --- after an update ------------------------------------------------------------------------------------------

    def served(self, version: str, port: int | None = None) -> dict:
        """The port pages are on answering the old page token with ``version``: a page open on it reloads into it."""
        def found():
            status, answer = self.server(port=port)
            if status not in (None, 200):
                raise Failed(f"{self.label}: the server answered {status}: {answer}")
            update = answer.get("update") or {}
            if update.get("state") == "failed":
                raise Failed(f"{self.label}: the update failed: {update.get('error')}\n{self.state_said()}")
            return answer if answer.get("release") == version else None
        return self.until(found, f"{version}'s server on port {port or self.port} with the old token")

    def check(self, version: str, *, legacy_gone: bool = True, documents: tuple[str, ...] = ()) -> None:
        """Everything an update into ``version`` leaves (see the module), and the documents ``documents`` in Recents
        too, each opening."""
        self.served(version)
        self.until(lambda: self.read("default") == version, f"the default pointer naming {version}")
        if self.read("installations/current") != version:
            raise Failed(f"{self.label}: the mirror names {self.read('installations/current')!r}\n{self.state_said()}")
        record = json.loads(self.read(f"installations/{version}.json"))
        server = self.state / "versions" / version / "code" / "server"
        if os.path.normcase(os.path.realpath(record["prefix"])) != os.path.normcase(os.path.realpath(server)):
            raise Failed(f"{self.label}: the mirror's record names {record['prefix']}, not {server}")
        if legacy_gone:  # what it held carried over first: then Recents is read
            gone = [self.state / "releases", self.state / "documents", self.state / "recents",
                    *(self.work / "cache" / name for name in ("base", "documents", "pycache"))]
            self.until(lambda: not [path for path in gone if path.exists()], f"the layout of {self.old} removed")
        status, listing = self.http("GET", "/api/v1/documents")
        held = {row.get("id") for row in listing.get("documents", [])}
        for document in (self.document, *documents):
            if status != 200 or document not in held:
                raise Failed(f"{self.label}: Recents lacks {document}: {status} {listing}\n{self.state_said()}")
            status, envelope = self.http("GET", f"/api/v1/documents/{document}")
            if status != 200:
                raise Failed(f"{self.label}: the document {document} does not open: {status} {envelope}")
        door = self.old_door()
        inside = os.path.normcase(os.path.realpath(self.state / "versions" / version)) + os.sep
        if not door or not os.path.normcase(os.path.realpath(str(door.get("prefix") or "-"))).startswith(inside):
            raise Failed(f"{self.label}: the flat door does not answer a {self.old} client with {version}'s server: "
                         f"{door}")
        version_out = self.run([self.proxy(), "--version"], check=False).stdout.strip()
        if version_out != f"cad {version}":
            raise Failed(f"{self.label}: the cad command with no pin says {version_out!r}")
        # What the old release had of the files kept for its clients (0.10 writes no settings.json until a setting is
        # chosen), and what every update leaves.
        for kept in (*self.kept, "installations/current", f"installations/{version}.json", "install-receipt.json",
                     "plugin"):
            if not (self.state / kept).exists():
                raise Failed(f"{self.label}: {kept} is gone\n{self.state_said()}")

    def button(self, version: str, port: int | None = None) -> dict:
        status, answer = self.http("POST", "/api/v1/local/update", body=b"{}", port=port,
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202 or (answer.get("update") or {}).get("target") != version:
            raise Failed(f"{self.label}: the update button answered {status}: {answer}")
        return answer

    def second(self) -> None:
        """A second update on top, by the new server's own button: NEWER, the same port and token, NEW removed."""
        self.feed.latest = NEWER
        self.button(NEWER)
        self.check(NEWER)
        self.until(lambda: not (self.state / "versions" / NEW).exists(), f"{NEW}'s folder removed")

    def stop(self) -> None:
        """Every server of the device stopped, and anything still running from its folder ended."""
        for held in self.helds:
            held.let_go()
        versions = self.state / "versions"
        for version in (sorted(os.listdir(versions)) if versions.is_dir() else []):
            if self.python(version).exists():
                self.run([self.python(version), "-c", f"from cad_server._internal import versions\n"
                          f"versions.ask({version!r}, {{'op': 'stop'}})"], check=False, timeout=60)
        if self.old_client:
            self.run([*self.old_client, "-c", "from cad.engine import client\n"
                      "client.request({'op': 'stop'}, start=False)"], check=False, timeout=60)
        if not WINDOWS:
            listed = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
            for line in listed.splitlines():
                pid, _, command_line = line.strip().partition(" ")
                if str(self.work) in command_line and pid.isdigit() and int(pid) != os.getpid():
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except OSError:
                        pass
        shutil.rmtree(self.work, ignore_errors=True)


class Held:
    """A build held open (``HELD``) on the server behind ``door`` -- a version's name, or ``flat`` for whichever
    server holds the flat door of 0.11.10 and earlier --: started, and later let go, when it must have run to its end
    there, answered."""

    def __init__(self, device: Device, door: str, label: str) -> None:
        self.device = device
        self.label = label
        self.project = device.work / f"held-{label}"
        self.project.mkdir()
        (self.project / "model.py").write_text(HELD, encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-c", BUILD, str(self.project), door], env=device.env,
                                        cwd=self.project, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        device.helds.append(self)
        device.until(lambda: (self.project / "started").exists() or self.process.poll() is not None,
                     f"the {label} build under way", 300)
        if not (self.project / "started").exists():
            out, err = self.process.communicate()
            raise Failed(f"{device.label}: the {label} build did not start: {out}{err}")

    def let_go(self) -> None:
        (self.project / "release").write_text("", encoding="utf-8")

    def ended(self) -> dict:
        """Let go, and its answer: it ran to its end, in a worker no update killed, and its server answered it."""
        self.let_go()
        try:
            out, err = self.process.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            self.process.kill()
            raise Failed(f"{self.device.label}: the {self.label} build never answered") from None
        lines = out.strip().splitlines()
        try:
            answer = json.loads(lines[-1]) if lines else None
        except ValueError:
            answer = None
        if not (self.project / "ended").exists():
            raise Failed(f"{self.device.label}: the {self.label} build did not run to its end: {out}{err}")
        if not isinstance(answer, dict) or "failed" in answer or not answer.get("ok", True):
            raise Failed(f"{self.device.label}: the {self.label} build's server did not answer it: {out}{err}")
        return answer


# --- the paths ------------------------------------------------------------------------------------------------------


def automatic(device: Device) -> None:
    device.feed.latest = NEW
    device.install_old()
    device.until(lambda: (device.state / "releases" / NEW).is_dir(), f"{device.old}'s automatic update starting")
    device.check(NEW)
    device.second()


def onto_new(device: Device) -> None:
    device.feed.latest = device.old
    device.install_old()
    device.feed.latest = NEW
    device.button(NEW)
    device.check(NEW)


def button(device: Device) -> None:
    onto_new(device)
    device.second()


def command_path(device: Device) -> None:
    device.feed.latest = device.old
    device.install_old()
    device.feed.latest = NEW
    device.run([device.proxy(), "update"], timeout=SECONDS)
    device.check(NEW)
    device.second()


def reinstall(device: Device) -> None:
    """The install command run again on a device of the old release (``install.sh`` runs the newest release's ``cad
    setup`` through uvx): it drains the old release's server and its own takes the port, with the same token."""
    device.feed.latest = device.old
    device.install_old()
    device.feed.latest = NEW
    device.run(["uvx", *LAUNCHER[1:-1], "--find-links", device.wheels, "--from", f"cad-server=={NEW}", "cad",
                "setup"], timeout=SECONDS)
    device.check(NEW)
    device.second()


def interrupted(device: Device, point: str) -> None:
    """This build's setup killed at ``point`` on a device of 0.11.10, then 0.11.10's update button."""
    device.feed.latest = device.old
    device.install_old()
    device.feed.latest = NEW
    device.run([base.find_uv(), "tool", "run", *LAUNCHER[1:-1], "--find-links", device.wheels, "--from",
                f"cad-server=={NEW}", "cad", "setup", "--add", "--quiet"])
    killed = device.run([device.python(NEW), "-c", KILL, point], check=False)
    if killed.returncode != 9:
        raise Failed(f"{device.label}: the setup was not killed at {point}: {killed.returncode}\n{killed.stderr}")
    working(device)
    device.button(NEW)
    device.check(NEW)


def interrupted_removal(device: Device) -> None:
    """The second update's setup killed while it removes the version it leaves, then that setup run again."""
    button(device)  # on NEWER now: a third release to leave it for
    device.run([base.find_uv(), "tool", "run", *LAUNCHER[1:-1], "--find-links", device.wheels,
                "--from", f"cad-server=={THIRD}", "cad", "setup", "--add", "--quiet"])
    killed = device.run([device.python(THIRD), "-c", KILL, "during-removal"], check=False)
    refused = WINDOWS and killed.returncode == 0 and (device.state / "versions" / NEWER).exists()
    if killed.returncode != 9 and not refused:  # on Windows a rename refused (a file in use) leaves nothing to cut
        raise Failed(f"{device.label}: the setup was not killed during the removal: {killed.returncode}\n{killed.stderr}")
    working(device)
    device.run([device.python(THIRD), "-m", "cad_server.cli", "setup", "--engine-update"])
    if device.read("default") != THIRD or (device.state / "versions" / NEWER).exists():
        raise Failed(f"{device.label}: the second run did not finish the removal\n{device.state_said()}")
    leftovers = [entry for entry in os.listdir(device.state / "versions") if entry.startswith(".trash-")]
    if leftovers:
        raise Failed(f"{device.label}: {leftovers} left in versions/")


def working(device: Device) -> None:
    """A working device: the cad command with no pin answers, and a 0.11.10 client finds a server (one started)."""
    said = device.run([device.proxy(), "--version"], check=False)
    if said.returncode != 0 or not said.stdout.startswith("cad "):
        raise Failed(f"{device.label}: the cad command with no pin does not run: {said.stdout}{said.stderr}\n"
                     f"{device.state_said()}")
    door = device.run([*device.old_client, "-c", "import json\nfrom cad.engine import client\n"
                       "print(json.dumps(client.request({'op': 'status'})))"], check=False, timeout=120)
    if door.returncode != 0 or '"ok": true' not in door.stdout:
        raise Failed(f"{device.label}: a 0.11.10 client finds no server: {door.stdout}{door.stderr}\n{device.state_said()}")


def own_automatic(device: Device) -> None:
    """This build updating itself by its own automatic path (see the module)."""
    onto_new(device)
    # An hour later, as the server sees it: the feed it read as it started is due again, and names NEWER.
    device.feed.latest = NEWER
    cache = device.state / "versions" / NEW / "data" / "versions.json"
    kept = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    cache.write_text(json.dumps({**kept, "checked": 0}), encoding="utf-8")
    marker = device.state / "versions" / NEWER / "code" / "cad-version.json"
    seen = {"present": False, "lost": False}
    watching = threading.Event()

    def watch() -> None:  # the installed release, once there, never gone before the default channel moves to it
        while not watching.is_set():
            if marker.exists():
                seen["present"] = True
            elif seen["present"] and device.read("default") != NEWER:
                seen["lost"] = True
            time.sleep(0.1)

    threading.Thread(target=watch, daemon=True).start()
    try:
        def waiting():
            automatic_update = ((device.ask(NEW, {"op": "status"}) or {}).get("update") or {}).get("automatic") or {}
            return automatic_update.get("release") == NEWER and automatic_update.get("state") == "waiting"
        device.until(waiting, f"{NEW}'s server installing {NEWER} by itself and waiting for quiet", 300)
        if not marker.exists():
            raise Failed(f"{device.label}: {NEWER} is waiting but not installed\n{device.state_said()}")
        # What an earlier removal cut short leaves: the next tend's sweep clears it, with NEWER waiting beside it.
        leftover = device.state / "versions" / ".trash-rehearsal"
        leftover.mkdir()
        # A person's command every few seconds, for longer than the quiet period: the update waits.
        began = time.monotonic()
        while time.monotonic() - began < 1.5 * QUIET:
            device.run([device.proxy(), "status"], check=False, timeout=120)
            if device.read("default") != NEW:
                raise Failed(f"{device.label}: the automatic update ran while commands were coming in "
                             f"({time.monotonic() - began:.0f} s into them)\n{device.state_said()}")
            time.sleep(QUIET / 5)
        device.until(lambda: not leftover.exists(), "a tend's sweep clearing an earlier removal's leftover", 120)
        if seen["lost"] or not marker.exists():
            raise Failed(f"{device.label}: {NEWER}, installed and waiting, was removed\n{device.state_said()}")
        # Quiet now: the update goes on by itself.
        device.until(lambda: device.read("default") == NEWER, f"{NEWER}'s setup once {NEW}'s server was quiet",
                     QUIET + 180)
    finally:
        watching.set()
    if seen["lost"]:
        raise Failed(f"{device.label}: {NEWER}'s folder went before its setup ran")
    device.check(NEWER)
    device.until(lambda: not (device.state / "versions" / NEW).exists(), f"{NEW}'s folder removed")


def in_flight(device: Device) -> None:
    """Work going on while 0.11.10 is updated into this build, and while this build is updated (see the module)."""
    device.feed.latest = device.old
    device.install_old()
    held = Held(device, "flat", device.old)
    device.feed.latest = NEW
    device.button(NEW)
    imported = device.state / "versions" / NEW / "data" / "format.json"
    device.until(lambda: imported.exists() and device.read("default") == NEW, f"{NEW} imported and the default")
    old = device.old_door() or {}
    if NEW in str(old.get("prefix")) or not old.get("ok"):
        raise Failed(f"{device.label}: {device.old}'s server is not the one running its build: {old}")
    late = device.opened("late")  # written by the old server, after the new version imported
    if (device.state / "versions" / NEW / "data" / "documents" / late).exists():
        raise Failed(f"{device.label}: {late} reached {NEW} before the old layout went: no carry-over to rehearse")
    if not (device.state / "documents" / late).exists():
        raise Failed(f"{device.label}: {device.old}'s server did not record {late} in its layout\n{device.state_said()}")
    held.ended()
    device.check(NEW, documents=(late,))

    # This build, updated by its button while a build runs on it.
    held = Held(device, NEW, NEW)
    pid = device.pid(NEW)
    device.feed.latest = NEWER
    device.button(NEWER)
    imported = device.state / "versions" / NEWER / "data" / "format.json"
    device.until(lambda: imported.exists() and device.read("default") == NEWER, f"{NEWER} imported and the default")
    moved = device.until(lambda: (lambda update: update if update.get("state") == "moved" else None)(
        device.server()[1].get("update") or {}), f"{NEW}'s server saying the update moved on, its build running")
    if device.pid(NEW) != pid:
        raise Failed(f"{device.label}: {NEW}'s server was replaced with its build in flight")
    later = device.opened("later")  # written by NEW's server, after NEWER imported
    if not (device.state / "versions" / NEW).exists():
        raise Failed(f"{device.label}: {NEW}'s folder went with its build in flight")
    held.ended()
    device.until(lambda: not (device.state / "versions" / NEW).exists(), f"{NEW}'s folder removed once idle")
    address = str(moved.get("address") or "")
    pages = device.port
    device.port = int(address.rsplit(":", 1)[-1].split("/")[0]) if address else device.port
    # NEWER took the next port while NEW held the pages' one; NEW, as it stopped, handed that port to NEWER's server
    # (``versions.hand_port``), so a page left open there reloads into NEWER, with the same token.
    def handed():
        status, said = device.server(port=pages)
        return status == 200 and said.get("release") == NEWER
    device.until(handed, f"port {pages} (the pages' before the update) served by {NEWER} once {NEW} stopped")
    device.check(NEWER, documents=(late, later))


def early_server(device: Device) -> None:
    """New skill text before the new software, on a device of 0.11.10 (see the module)."""
    device.feed.latest = device.old
    device.install_old()
    pages = device.port
    device.run([base.find_uv(), "tool", "run", *LAUNCHER[1:-1], "--find-links", device.wheels, "--from",
                f"cad-server=={NEW}", "cad", "setup", "--add", "--quiet"])
    pinned = device.run([device.proxy(), f"+{NEW}", "status"], check=False, timeout=SECONDS)
    if device.read("default") != NEW:
        raise Failed(f"{device.label}: the pinned command did not move the default channel: {pinned.stdout}"
                     f"{pinned.stderr}\n{device.state_said()}")
    old = device.old_door() or {}
    if not old.get("ok") or NEW in str(old.get("prefix")):
        raise Failed(f"{device.label}: {device.old}'s server did not stay: {old}")
    page = device.run([device.python(NEW), "-c", "import json\nfrom cad.engine import client\n"
                       "print(json.dumps(client.request({'op': 'http'})))"])
    answer = json.loads(page.stdout.strip().splitlines()[-1])
    early = int(answer["port"])
    if early == pages or answer.get("token") != device.token:
        raise Failed(f"{device.label}: {NEW}'s server took port {early} (pages on {pages}) with "
                     f"{'the same' if answer.get('token') == device.token else 'another'} token")
    status = device.ask(NEW, {"op": "status"}) or {}
    if (status.get("serving") or {}).get("portSource") != "rolled":
        raise Failed(f"{device.label}: {NEW}'s server did not roll from the default port: {status.get('serving')}")
    device.served(NEW, port=early)
    pid = device.pid(NEW)
    held = Held(device, NEW, NEW)
    device.feed.latest = NEW
    device.button(NEW)  # 0.11.10's own button, on the port pages are on
    device.until(lambda: device.server()[1].get("release") == NEW, f"{NEW}'s server serving port {pages} too")
    if device.pid(NEW) != pid:
        raise Failed(f"{device.label}: {NEW}'s server, running before {device.old} switched, was stopped")
    held.ended()
    device.served(NEW, port=early)
    device.check(NEW)
    if device.pid(NEW) != pid:
        raise Failed(f"{device.label}: {NEW}'s server was stopped")


def app_behind(device: Device) -> None:
    """An app an update could not reach (B3): Codex set up from a person's terminal, where its command is, and the
    update run by the server an app started, whose environment lacks it. The receipt records Codex behind, ``cad
    doctor`` names it, and ``cad update`` from the terminal gives it the new release's text."""
    shell = device.codex_shell()
    device.feed.latest = device.old
    device.install_old(shell)
    if device.codex_copy() != [device.old]:
        raise Failed(f"{device.label}: {device.old}'s setup did not give Codex its copy: {device.codex_copy()}")
    device.feed.latest = NEW
    device.button(NEW)
    device.check(NEW)
    behind = device.behind().get("codex") or {}
    if behind.get("release") != NEW:
        raise Failed(f"{device.label}: the receipt does not record Codex behind {NEW}: {device.behind()} "
                     f"(Codex holds {device.codex_copy()})")
    doctor = device.run([device.proxy(), "doctor"], check=False, env=shell, timeout=300)
    if not any("Codex" in line and "behind" in line for line in doctor.stdout.splitlines()):
        raise Failed(f"{device.label}: cad doctor does not name Codex behind:\n{doctor.stdout}{doctor.stderr}")
    device.run([device.proxy(), "update"], env=shell, timeout=SECONDS)
    if NEW not in device.codex_copy() or "codex" in device.behind():
        raise Failed(f"{device.label}: cad update did not give Codex {NEW}'s text: {device.codex_copy()}, "
                     f"behind {device.behind()}")
    device.check(NEW)


def main(argv: list[str] | None = None) -> int:
    global OLD
    runs = {"automatic": [("automatic", automatic)], "button": [("button", button)],
            "command": [("command", command_path)], "reinstall": [("reinstall", reinstall)],
            "interrupted": [*((f"killed {point}", lambda device, point=point: interrupted(device, point))
                              for point in POINTS), ("killed during-removal", interrupted_removal)],
            "own-automatic": [("own automatic", own_automatic)], "in-flight": [("in flight", in_flight)],
            "early-server": [("early server", early_server)], "app-behind": [("app behind", app_behind)],
            "from-0.10": [(f"{name} from {OLD_10}", path, OLD_10) for name, path in
                          (("button", button), ("command", command_path), ("reinstall", reinstall))]}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenarios", nargs="*", default=["all"], choices=("all", *runs), metavar="SCENARIO",
                        help=f"one or more of: all, {', '.join(runs)}")
    parser.add_argument("--old", default=OLD, help="the release before this build the 0.11.10 paths start on")
    args = parser.parse_args(argv)
    OLD = args.old
    if shutil.which("uv") is None and shutil.which("uvx") is None:
        print("rehearse-update: uv is not installed", file=sys.stderr)
        return 1
    uv_cache = os.environ.get("UV_CACHE_DIR") or subprocess.run(
        [base.find_uv(), "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
    names = list(runs) if "all" in args.scenarios else list(dict.fromkeys(args.scenarios))
    chosen = [(run[0], run[1], run[2] if len(run) > 2 else OLD) for name in names for run in runs[name]]
    seam = None if default_free() else free_port()
    print(f"rehearse-update: {len(chosen)} paths; the default port is "
          + (f"{DEFAULT_PORT}" if seam is None else f"{seam} (CAD_ENGINE_DEFAULT_PORT: {DEFAULT_PORT} is in use here)"),
          flush=True)
    wheels = Path(tempfile.mkdtemp(prefix="crw.")).resolve()
    publish(wheels, (NEW, NEWER, THIRD))
    feed = Feed()
    threading.Thread(target=feed.serve_forever, daemon=True).start()
    failed = 0
    try:
        for label, path, old in chosen:
            device = Device(label.replace(" ", "-"), old, wheels, feed, uv_cache, seam)
            began = time.monotonic()
            try:
                path(device)
                print(f"ok      {label}, from {old} ({time.monotonic() - began:.0f} s)", flush=True)
            except (Failed, subprocess.TimeoutExpired) as failure:
                failed += 1
                print(f"FAILED  {label}, from {old} ({time.monotonic() - began:.0f} s): {failure}", flush=True)
            finally:
                device.stop()
    finally:
        feed.shutdown()
        feed.server_close()
        forget(Path(uv_cache), (NEW, NEWER, THIRD))
        shutil.rmtree(wheels, ignore_errors=True)
    print(f"rehearse-update: {len(chosen) - failed} held, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
