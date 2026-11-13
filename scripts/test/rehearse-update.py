#!/usr/bin/env python3
"""The update a real 0.11.10 makes into this build, rehearsed on a private device.

0.11.10 is frozen on every device: its updater makes a flat ``releases/<release>`` for the release it moves to,
runs that folder's ``cad setup --engine-update`` (first with ``CAD_UPDATE_PREPARE=1`` for an automatic update), and
then drains its server and has its helper start the new release's through ``installations/current`` and the flat
door. This script installs 0.11.10 from PyPI into a device of its own -- its own home, state, engine, cache and
``cad`` command folders (``CAD_STATE_DIR``, ``CAD_ENGINE_DIR``, ``CAD_CACHE_DIR``, ``CAD_LAUNCHER_DIR``), never this
machine's --, publishes this checkout as two later releases (its wheels in a folder uv reads beside the index,
``CAD_UPDATE_FIND_LINKS`` and ``UV_FIND_LINKS``; the version feed a local stand-in, ``CAD_API_URL``), and drives
each update path of 0.11.10 into this build:

- ``automatic``: 0.11.10's own background update (its feed read, its minute of quiet, its prepare step);
- ``button``: the update button's request, ``POST /api/v1/local/update``, to 0.11.10's server;
- ``command``: 0.11.10's ``cad update``, through the ``cad`` command 0.11.10 wrote.

After each it checks: the default pointer; the mirror (``installations/current`` and its record); the same port and
page token (``GET /api/v1/server`` answers the old token with the new release); Recents (a file 0.11.10 recorded) and
that document opening (``GET /api/v1/documents/<id>``); the layout of 0.11.10 removed and the files kept for its
clients present; the flat door answering a 0.11.10 client; and a second update on top, by the new server's own
button. And the interrupted updates (``interrupted``): this build's setup killed (``os._exit``: nothing after it
runs) before the import is marked, before the pointer is written, and after it, each followed by 0.11.10's update
button, which completes it; and the second update killed during the removal of the version it leaves, followed by
the same setup again. Throughout, a command with no pin and a 0.11.10 client both reach a working server.

Usage: scripts/test/rehearse-update.py [automatic|button|command|interrupted|all] [--old RELEASE] (default: all,
from 0.11.10; ``--old`` rehearses another release before this build that updates itself, as 0.11.0). It needs uv, the
network (PyPI, for 0.11.10 and the packages both releases depend on; uv's cache holds them after the first run) and
loopback ports. It never sets ``CAD_UPDATE_CHECK=0``: the update is what it rehearses, against the local feed. The
release tier of ``.github/workflows/test.yml`` runs it on Linux, macOS and Windows (``update-rehearsal``).
Exit 0 when every path held; 1, with what the device holds, when one did not.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.python.packages.cad_server.test_update_end_to_end import Feed, forget, free_port, release  # noqa: E402

from cad_server._internal import base  # noqa: E402
from cad_server._internal.launch import LAUNCHER  # noqa: E402

OLD = "0.11.10"
WINDOWS = os.name == "nt"
# This checkout, as two releases 0.11.10 takes by itself (a patch) and no index will ever hold.
_RUN = os.getpid() % 900
NEW, NEWER = f"0.11.{9000 + 2 * _RUN}", f"0.11.{9001 + 2 * _RUN}"
# How long each wait may take: an install from uv's cache, 0.11.10's 30-second tend and minute of quiet.
SECONDS = 600.0
POINTS = ("before-the-import-is-marked", "before-the-pointer", "after-the-pointer")

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


class Failed(Exception):
    pass


class Device:
    """A device of its own, with 0.11.10 installed by the install command's own step, its server serving pages."""

    def __init__(self, label: str, wheels: Path, feed: Feed, uv_cache: str) -> None:
        self.label = label
        # Short, under /tmp: a server's door is a Unix socket in its folder, whose path caps near 104 bytes.
        self.work = Path(tempfile.mkdtemp(prefix=f"cr{label[:2]}.", dir=None if WINDOWS else "/tmp")).resolve()
        self.state = self.work / "state"
        self.feed = feed
        self.port = free_port()
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
            "CAD_LAUNCHER_DIR": str(self.work / "bin"), "CAD_ENGINE_PORT": str(self.port),
            "CAD_API_URL": f"http://127.0.0.1:{feed.server_port}/v1", "CAD_UPDATE_FIND_LINKS": str(wheels),
            "UV_FIND_LINKS": str(wheels),
        })
        if WINDOWS:
            env.update({"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(home / "AppData" / "Local")})
        self.env = env
        self.token = ""
        self.document = ""
        self.old_client: list[str] = []

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

    def server(self, token: str | None = None) -> tuple[int | None, dict]:
        """``GET /api/v1/server`` on the device's port, as a page asks it."""
        return self.http("GET", "/api/v1/server", token=token)

    def http(self, method: str, path: str, *, token: str | None = None, body: bytes | None = None,
             headers: dict | None = None) -> tuple[int | None, dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
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
        """What the device holds, for a failure: the pointer, the mirror, the folders, 0.11.10's update log."""
        listing = lambda path: sorted(os.listdir(path)) if path.is_dir() else []  # noqa: E731
        log = self.state / "update.log"
        return (f"device {self.work}\n  default {self.read('default')!r}, current {self.read('installations/current')!r}\n"
                f"  versions {listing(self.state / 'versions')}, releases {listing(self.state / 'releases')}\n"
                f"  state {listing(self.state)}\n"
                + (f"  0.11.10's update log:\n{log.read_text(encoding='utf-8', errors='replace')[-3000:]}" if log.exists()
                   else ""))

    # --- 0.11.10 ------------------------------------------------------------------------------------------------

    def install_old(self) -> None:
        """0.11.10 as the install command sets it up: its own `cad setup` through uvx, its server started as a client
        starts it, serving pages; a file it recorded in Recents."""
        self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={OLD}", "cad", "setup"], timeout=1200)
        python = base.interpreter(self.state / "releases" / OLD)
        if not python.exists():
            raise Failed(f"0.11.10's setup made no release folder\n{self.state_said()}")
        started = self.run([python, "-c", "import json, sys\nfrom cad.engine import client\n"
                            "print(json.dumps(client.request({'op': 'http', 'port': int(sys.argv[1])})))", self.port])
        self.token = json.loads(started.stdout.strip().splitlines()[-1])["token"]
        status, answer = self.server()
        if status != 200 or answer.get("release") != OLD:
            raise Failed(f"0.11.10's server does not answer on {self.port}: {status} {answer}")
        part = self.work / "part.stl"
        part.write_text("solid p\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\n"
                        "endfacet\nendsolid p\n", encoding="ascii")
        recorded = self.run([python, "-c", "import sys\nfrom cad_server.viewer.recents import RecentStore\n"
                             "print(RecentStore().opened(sys.argv[1])['id'])", part])
        self.document = recorded.stdout.strip().splitlines()[-1]
        # A 0.11.10 client of its own, outside the device's folders, as an app's launcher of 0.11.10 is.
        client = self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={OLD}", "python", "-c",
                           "import sys; print(sys.executable)"], timeout=1200)
        self.old_client = [client.stdout.strip().splitlines()[-1]]

    def old_door(self) -> dict | None:
        """The flat door, as a client of 0.11.10 asks it: the status of the server there, nothing started."""
        done = self.run([*self.old_client, "-c", "import json\nfrom cad.engine import client\n"
                         "print(json.dumps(client.request({'op': 'status'}, start=False)))"], check=False, timeout=60)
        try:
            return json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None

    def proxy(self) -> Path:
        return self.work / "bin" / ("cad.exe" if WINDOWS else "cad")

    # --- after an update ------------------------------------------------------------------------------------------

    def served(self, version: str) -> dict:
        """The device's port answering the old page token with ``version``: a page open on it reloads into it."""
        def found():
            status, answer = self.server()
            if status not in (None, 200):
                raise Failed(f"{self.label}: the server answered {status}: {answer}")
            update = answer.get("update") or {}
            if update.get("state") == "failed":
                raise Failed(f"{self.label}: the update failed: {update.get('error')}\n{self.state_said()}")
            return answer if answer.get("release") == version else None
        return self.until(found, f"{version}'s server on port {self.port} with the old token")

    def check(self, version: str, *, legacy_gone: bool = True) -> None:
        """Everything an update into ``version`` leaves (see the module)."""
        self.served(version)
        self.until(lambda: self.read("default") == version, f"the default pointer naming {version}")
        if self.read("installations/current") != version:
            raise Failed(f"{self.label}: the mirror names {self.read('installations/current')!r}\n{self.state_said()}")
        record = json.loads(self.read(f"installations/{version}.json"))
        server = self.state / "versions" / version / "code" / "server"
        if os.path.normcase(os.path.realpath(record["prefix"])) != os.path.normcase(os.path.realpath(server)):
            raise Failed(f"{self.label}: the mirror's record names {record['prefix']}, not {server}")
        status, documents = self.http("GET", "/api/v1/documents")
        if status != 200 or self.document not in {row.get("id") for row in documents.get("documents", [])}:
            raise Failed(f"{self.label}: Recents lacks the file 0.11.10 recorded: {status} {documents}")
        status, envelope = self.http("GET", f"/api/v1/documents/{self.document}")
        if status != 200:
            raise Failed(f"{self.label}: the document does not open: {status} {envelope}")
        door = self.old_door()
        inside = os.path.normcase(os.path.realpath(self.state / "versions" / version)) + os.sep
        if not door or not os.path.normcase(os.path.realpath(str(door.get("prefix") or "-"))).startswith(inside):
            raise Failed(f"{self.label}: the flat door does not answer a 0.11.10 client with {version}'s server: {door}")
        version_out = self.run([self.proxy(), "--version"], check=False).stdout.strip()
        if version_out != f"cad {version}":
            raise Failed(f"{self.label}: the cad command with no pin says {version_out!r}")
        if legacy_gone:
            gone = [self.state / "releases", self.state / "documents", self.state / "recents",
                    *(self.work / "cache" / name for name in ("base", "documents", "pycache"))]
            self.until(lambda: not [path for path in gone if path.exists()], "the layout of 0.11.10 removed")
        for kept in ("settings.json", "engines/token", "installations/current", f"installations/{version}.json",
                     "install-receipt.json", "plugin"):
            if not (self.state / kept).exists():
                raise Failed(f"{self.label}: {kept} is gone\n{self.state_said()}")

    def button(self, version: str) -> None:
        status, answer = self.http("POST", "/api/v1/local/update", body=b"{}",
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202 or (answer.get("update") or {}).get("target") != version:
            raise Failed(f"{self.label}: the update button answered {status}: {answer}")

    def second(self) -> None:
        """A second update on top, by the new server's own button: NEWER, the same port and token, NEW removed."""
        self.feed.latest = NEWER
        self.button(NEWER)
        self.check(NEWER)
        self.until(lambda: not (self.state / "versions" / NEW).exists(), f"{NEW}'s folder removed")

    def stop(self) -> None:
        """Every server of the device stopped, and anything still running from its folder ended."""
        for version in (NEWER, NEW):
            python = base.interpreter(self.state / "versions" / version / "code" / "server")
            if python.exists():
                self.run([python, "-c", f"from cad_server._internal import versions\n"
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


# --- the paths ------------------------------------------------------------------------------------------------------


def automatic(device: Device) -> None:
    device.feed.latest = NEW
    device.install_old()
    device.until(lambda: (device.state / "releases" / NEW).is_dir(), "0.11.10's automatic update starting", SECONDS)
    device.check(NEW)
    device.second()


def button(device: Device) -> None:
    device.feed.latest = OLD
    device.install_old()
    device.feed.latest = NEW
    device.button(NEW)
    device.check(NEW)
    device.second()


def command_path(device: Device) -> None:
    device.feed.latest = OLD
    device.install_old()
    device.feed.latest = NEW
    device.run([device.proxy(), "update"], timeout=SECONDS)
    device.check(NEW)
    device.second()


def interrupted(device: Device, point: str) -> None:
    """This build's setup killed at ``point`` on a device of 0.11.10, then 0.11.10's update button."""
    device.feed.latest = OLD
    device.install_old()
    device.feed.latest = NEW
    links = device.env["CAD_UPDATE_FIND_LINKS"]
    device.run([base.find_uv(), "tool", "run", *LAUNCHER[1:-1], "--find-links", links, "--from", f"cad-server=={NEW}",
                "cad", "setup", "--add", "--quiet"])
    python = base.interpreter(device.state / "versions" / NEW / "code" / "server")
    killed = device.run([python, "-c", KILL, point], check=False)
    if killed.returncode != 9:
        raise Failed(f"{device.label}: the setup was not killed at {point}: {killed.returncode}\n{killed.stderr}")
    working(device)
    device.button(NEW)
    device.check(NEW)


def interrupted_removal(device: Device) -> None:
    """The second update's setup killed while it removes the version it leaves, then that setup run again."""
    button(device)  # on NEWER now: a third release to leave it for
    third = f"0.11.{9000 + 2 * _RUN + 2}"
    release(third, Path(device.env["CAD_UPDATE_FIND_LINKS"]))
    device.run([base.find_uv(), "tool", "run", *LAUNCHER[1:-1], "--find-links", device.env["CAD_UPDATE_FIND_LINKS"],
                "--from", f"cad-server=={third}", "cad", "setup", "--add", "--quiet"])
    python = base.interpreter(device.state / "versions" / third / "code" / "server")
    killed = device.run([python, "-c", KILL, "during-removal"], check=False)
    refused = WINDOWS and killed.returncode == 0 and (device.state / "versions" / NEWER).exists()
    if killed.returncode != 9 and not refused:  # on Windows a rename refused (a file in use) leaves nothing to cut
        raise Failed(f"{device.label}: the setup was not killed during the removal: {killed.returncode}\n{killed.stderr}")
    working(device)
    device.run([python, "-m", "cad_server.cli", "setup", "--engine-update"])
    if device.read("default") != third or (device.state / "versions" / NEWER).exists():
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


def main(argv: list[str] | None = None) -> int:
    global OLD
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", nargs="?", default="all",
                        choices=("automatic", "button", "command", "interrupted", "all"))
    parser.add_argument("--old", default=OLD, help="the release before this build that the device starts on")
    args = parser.parse_args(argv)
    OLD = args.old
    if shutil.which("uv") is None and shutil.which("uvx") is None:
        print("rehearse-update: uv is not installed", file=sys.stderr)
        return 1
    uv_cache = os.environ.get("UV_CACHE_DIR") or subprocess.run(
        [base.find_uv(), "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
    third = f"0.11.{9000 + 2 * _RUN + 2}"
    wheels = Path(tempfile.mkdtemp(prefix="crw.")).resolve()
    for version in (NEW, NEWER):
        release(version, wheels)
    feed = Feed()
    threading.Thread(target=feed.serve_forever, daemon=True).start()
    runs = {"automatic": [("automatic", automatic)], "button": [("button", button)],
            "command": [("command", command_path)],
            "interrupted": [*((f"killed {point}", lambda device, point=point: interrupted(device, point))
                              for point in POINTS), ("killed during-removal", interrupted_removal)]}
    chosen = [run for name in (runs if args.path == "all" else [args.path]) for run in runs[name]]
    failed = 0
    try:
        for label, path in chosen:
            device = Device(label.replace(" ", "-"), wheels, feed, uv_cache)
            began = time.monotonic()
            try:
                path(device)
                print(f"ok      {label}, from {OLD} ({time.monotonic() - began:.0f} s)", flush=True)
            except (Failed, subprocess.TimeoutExpired) as failure:
                failed += 1
                print(f"FAILED  {label}: {failure}", flush=True)
            finally:
                device.stop()
    finally:
        feed.shutdown()
        feed.server_close()
        forget(Path(uv_cache), (NEW, NEWER, third))
        shutil.rmtree(wheels, ignore_errors=True)
    print(f"rehearse-update: {len(chosen) - failed} held, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
