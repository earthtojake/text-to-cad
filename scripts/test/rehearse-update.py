#!/usr/bin/env python3
"""A computer on a shipped release arriving at this build, rehearsed with the real release from PyPI on a private
computer: its own home, state, engine, cache and ``cad`` command folders, never this machine's.

Two routes reach this build, and each is rehearsed from the releases that take it:

- ``updater`` (0.11.10; ``--old`` names another of 0.10.0 to 0.11.10): the shipped release's own updater, asked by its
  update button (``POST /api/v1/local/update``), installs this build in a flat ``releases/<release>`` folder and runs
  its hidden ``cad setup --engine-update``, which sets the version up, hands over from the shipped layout and starts
  the install script once (here a stand-in, ``CAD_ENGINE_UPDATE_INSTALLER``, that notes it ran); the shipped
  release's switch then starts this build's server on the port pages were on.
- ``install-script`` (0.11.10, or ``--old``): ``scripts/install/install.py`` run as the hosted script runs it, which
  runs this build's ``cad setup`` through uvx; the shipped release's server is asked to stop once idle and the next
  command starts this build's;
- ``from-0.8``: 0.8.4, which has no updater, installed by its own ``cadgen setup`` with telemetry turned off, its
  server serving a page and a file in Recents; then ``install.py``. Its state folder is the platform's, in the private
  home (no ``CAD_STATE_DIR``): what 0.8 kept there is taken in only where no state folder is named.

After each it checks: this build's server answering on the port pages were on (with the page token they hold, from
0.10 and 0.11); the file recorded before in Recents and opening (``GET /api/v1/documents/<id>``), the telemetry answer
and What's new decided as an updated computer's; the ``cad`` command with no pin and ``cad +<this build>`` running this
build; the install script started exactly once (``updater``); one server: the old release's gone, no process left
running from its folders, and the layout of 0.11.10 and earlier (or what 0.8 left there) removed by this build's
cleanup once that is safe.

This tree is published as one later release (``0.11.<9000+n>``, n from this process: no index ever holds it), its
wheels in a folder uv reads beside the index (``CAD_UPDATE_FIND_LINKS``, ``UV_FIND_LINKS``), and the version feed is
a stand-in served here (``CAD_API_URL``, ``CAD_INSTALL_FEED``). No process is given a port by name: each computer's
servers take the default port, 3245 where it is free on this machine (CI), else a free port of the computer's own as
its default (``CAD_ENGINE_DEFAULT_PORT``, ``CADGEN_ENGINE_DEFAULT_PORT``), so a server this script did not start is
never asked anything. uv's own cache is this machine's (``uv cache dir``): it is read, and this run's wheels are taken
out of it again (``forget``).

Usage: scripts/test/rehearse-update.py [ROUTE ...] [--old RELEASE] (default: all; ``updater`` and ``install-script``
start on 0.11.10, or on ``--old``). It needs uv, the network (PyPI, for the old releases and what every release
depends on; uv's cache holds them after the first run) and loopback ports. The release tier of
``.github/workflows/test.yml`` runs it on Linux, macOS and Windows (``update-rehearsal``). Exit 0 when every route
held; 1, with what the computer holds, when one did not.
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
WINDOWS = os.name == "nt"
# This checkout as a release a release before it takes (a patch), and no index will ever hold.
NEW = f"0.11.{9000 + os.getpid() % 900}"
# How long each wait may take: an install from uv's cache, a switch, a cleanup's next try (a minute).
SECONDS = 600.0
DEFAULT_PORT = 3245
# A file a page opens, binary-free.
STL = ("solid p\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\n"
       "endsolid p\n")
# The stand-in of the install script ``cad setup --engine-update`` starts: a line in the file it names, each run.
INSTALLER = "import sys, time\nwith open(sys.argv[1], 'a', encoding='utf-8') as out:\n    out.write(f'{time.time()}\\n')\n"
# A server started as a page link starts it, by a Python of the release (its own client), and what it says: its
# token and port.
START = "import json\nfrom {package}.engine import client\nprint(json.dumps(client.request({{'op': 'http'}})))"


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
                 named_state: bool = True) -> None:
        self.label, self.old, self.feed, self.wheels = label, old, feed, wheels
        # Short, under /tmp: a server's door is a Unix socket in its folder, whose path caps near 104 bytes.
        self.work = Path(tempfile.mkdtemp(prefix=f"cr{label[:2]}.", dir=None if WINDOWS else "/tmp")).resolve()
        self.home = self.work / "home"
        self.state = self.work / "state" if named_state else platform_state(self.home, "cad")
        self.port = seam or DEFAULT_PORT  # the port pages are on: the default, until a server says otherwise
        self.installed = self.work / "installer-ran"
        tools = self.home / ".local" / "bin"
        tools.mkdir(parents=True)
        uv = Path(base.find_uv())
        for name in ("uv", "uvx"):
            found = shutil.which(name) or str(uv.with_name(name + uv.suffix))
            try:
                (os.link if WINDOWS else os.symlink)(found, tools / Path(found).name)
            except OSError:
                shutil.copy2(found, tools / Path(found).name)
        stand_in = self.work / "installer.py"
        stand_in.write_text(INSTALLER, encoding="utf-8")
        dropped = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "CI", "CODEX_HOME",
                   "CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                   "XDG_BIN_HOME", "UV_INSTALL_DIR", "GITHUB_ACTIONS")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("CAD_", "CADGEN_")) and key not in dropped}
        system = os.environ.get("SystemRoot", r"C:\Windows")
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        feed_url = f"http://127.0.0.1:{feed.server_port}/v1"
        env.update({
            "HOME": str(self.home),
            "PATH": os.pathsep.join([str(tools), *([rf"{system}\System32", system] if WINDOWS else ["/usr/bin", "/bin"])]),
            "UV_CACHE_DIR": uv_cache, "NO_PROXY": bypass, "no_proxy": bypass, "DO_NOT_TRACK": "1", "BROWSER": "true",
            "CAD_CACHE_DIR": str(self.work / "cache"), "CAD_ENGINE_DIR": str(self.work / "engine"),
            "CAD_LAUNCHER_DIR": str(self.work / "bin"), "CAD_API_URL": feed_url,
            "CAD_INSTALL_FEED": f"{feed_url}/versions", "CAD_UPDATE_FIND_LINKS": str(wheels), "UV_FIND_LINKS": str(wheels),
            "CAD_ENGINE_UPDATE_INSTALLER": f'"{sys.executable}" "{stand_in}" "{self.installed}"' if WINDOWS
            else f"'{sys.executable}' '{stand_in}' '{self.installed}'",
            "CADGEN_ENGINE_DIR": str(self.work / "engine-0.8"), "CADGEN_CACHE_DIR": str(self.work / "cache-0.8"),
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
        log = self.state / "update.log"
        return (f"computer {self.work}\n  state {self.state}: {listing(self.state)}\n"
                f"  versions {listing(self.state / 'versions')}, releases {listing(self.state / 'releases')}, "
                f"current {current.read_text(encoding='utf-8') if current.exists() else '(none)'}\n"
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
        return self.work / "bin" / ("cad.exe" if WINDOWS else "cad")

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

    # --- the old release ----------------------------------------------------------------------------------------

    def install_old(self) -> None:
        """The old release as the install command set it up: its own ``cad setup`` through uvx, its server serving
        pages on the computer's default port, and a file in Recents."""
        self.feed.latest = self.old
        self.run(["uvx", *LAUNCHER[1:-1], "--from", f"cad-server=={self.old}", "cad", "setup"], timeout=1200)
        python = base.interpreter(self.state / "releases" / self.old)
        if not python.exists():
            raise Failed(f"{self.old}'s setup made no release folder\n{self.said()}")
        self.pythons.append(python)
        answer = self.start(python, "cad")
        self.token = answer["token"]
        if int(answer["port"]) != self.port:
            raise Failed(f"{self.old}'s server took port {answer['port']}, not the computer's default {self.port}")
        status, said = self.http("GET", "/api/v1/server")
        if status != 200 or said.get("release") != self.old:
            raise Failed(f"{self.old}'s server does not answer on {self.port}: {status} {said}")
        self.record(python, "cad_server")

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
        self.feed.latest = NEW
        done = self.run([sys.executable, "-I", REPO_ROOT / "scripts" / "install" / "install.py"], check=False,
                        timeout=1200)
        if done.returncode != 0:
            raise Failed(f"install.py exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n{self.said()}")

    def button(self) -> None:
        """The old release's update button, on the port pages are on."""
        self.feed.latest = NEW
        status, answer = self.http("POST", "/api/v1/local/update", body=b"{}",
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202 or (answer.get("update") or {}).get("target") != NEW:
            raise Failed(f"{self.label}: the update button answered {status}: {answer}")

    # --- after ------------------------------------------------------------------------------------------------

    def served(self) -> dict:
        """This build's server on the port pages are on, answering the page token they hold."""
        def found():
            status, answer = self.http("GET", "/api/v1/server")
            update = answer.get("update") or {}
            if update.get("state") == "failed":
                raise Failed(f"{self.label}: the update failed: {update.get('error')}\n{self.said()}")
            return answer if status == 200 and answer.get("release") == NEW else None
        return self.until(found, f"{NEW}'s server on port {self.port} with the page token")

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
    """The shipped release's own updater, by its button (see the module)."""
    computer.install_old()
    computer.button()
    computer.check(gone=legacy_layout(computer))
    computer.until(lambda: computer.installed.exists(), "the install script started")
    runs = computer.installed.read_text(encoding="utf-8").splitlines()
    if len(runs) != 1:
        raise Failed(f"{computer.label}: the install script was started {len(runs)} times")


def install_script(computer: Computer) -> None:
    """``install.py`` on a computer of the shipped release, its server serving pages (see the module)."""
    computer.install_old()
    computer.install_script()
    current = (computer.state / "installations" / "current").read_text(encoding="utf-8").strip()
    if current != NEW:
        raise Failed(f"{computer.label}: the records {computer.old}'s clients read name {current!r}, not {NEW}")
    # The old server, asked to stop once idle, goes; the next command starts this build's, on the port it served
    # pages on (free now), with the page token this build imported.
    computer.until(lambda: computer.http("GET", "/api/v1/server")[0] is None, f"{computer.old}'s server stopped")
    answer = computer.start(computer.python(NEW), "cad")
    if (int(answer["port"]), answer["token"]) != (computer.port, computer.token):
        raise Failed(f"{computer.label}: {NEW}'s server serves on {answer['port']} "
                     f"{'with' if answer['token'] == computer.token else 'without'} the page token")
    computer.check(gone=legacy_layout(computer))
    if computer.installed.exists():
        raise Failed(f"{computer.label}: cad setup started the install script")


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
    routes = {"updater": updater, "install-script": install_script, "from-0.8": from_eight}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("routes", nargs="*", default=["all"], choices=("all", *routes), metavar="ROUTE",
                        help=f"one or more of: all, {', '.join(routes)}")
    parser.add_argument("--old", default=OLD, help="the shipped release updater and install-script start on")
    args = parser.parse_args(argv)
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
    feed = Feed()
    threading.Thread(target=feed.serve_forever, daemon=True).start()
    failed = 0
    try:
        for name in chosen:
            old = EIGHT if name == "from-0.8" else args.old
            computer = Computer(name, old, wheels, feed, uv_cache, seam, named_state=name != "from-0.8")
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
        forget(Path(uv_cache), (NEW,))
        shutil.rmtree(wheels, ignore_errors=True)
    print(f"rehearse-update: {len(chosen) - failed} held, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
