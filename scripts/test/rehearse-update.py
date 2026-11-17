#!/usr/bin/env python3
"""cad's updates rehearsed end to end on private computers (``scripts/test/real_computer.py``: a home, cad's state,
engine and cache folders, uv's tools and their commands of its own, never this machine's), with real uv, real servers,
the real install command (``scripts/install/install.sh``, this tree's ``install.py``) and, for the bridge, the REAL
shipped releases from PyPI.

This tree is published as releases no index holds (``0.11.<9000+n>`` and the next few, n from this process), written
into a folder uv reads beside the index (``UV_FIND_LINKS``, ``CAD_UPDATE_FIND_LINKS``), and the version feed is a
stand-in on loopback (``CAD_API_URL``, ``CAD_INSTALL_FEED``), as is PyPI's JSON API that ``cad update`` asks
(``CAD_PYPI_URL``), which names what the feed names. Every computer's server takes a port of its own
(``CAD_ENGINE_DEFAULT_PORT``: the true default, 3245, on CI alone). No real agent app is on any PATH.

**cad updating itself** (a computer the install command set up: cad a uv tool, its automatic updates on). Each such
computer has a folder of releases of its own, holding only those that are out (``Box.out``), since an upgrade is
``uv tool install cad@latest``; the install command cad runs counts its runs there (``Box.runs``).

- ``self-update``: with ``cad plugin auto-update on``, the feed names the next release and an hour passes; the running
  server, idle, stops, uv installs the next release, and its server answers; then the helper runs the new cad's ``cad
  plugin install`` once: exit 0, kept in the record, its output in ``install-command.log``.
- ``self-typed``: with ``cad auto-update off`` and the plugin's switch on, ``cad update`` is typed with nothing newer on
  PyPI: it says so and nothing restarts; then PyPI names the next release and ``cad update`` is typed again: the
  server asks PyPI at once and updates cad to it; the command, a running ``cad`` of the tool, waits and says so; the uv
  tool is the next release, its server answers, and no install command runs.
- ``self-at-start``: the plugin's switch off, the server stopped, the feed's file already naming the next release, then
  ``cad server start``: the server it spawns hands its start to the update, and the starter, a running ``cad`` of the
  tool, waits for the update's server. It exits 0, the uv tool is the next release and serves, the attempt installed
  at its first try (on Windows this failed every time until cad's update set the running ``cad.exe`` aside), and no
  install command runs.
- ``self-off``: with ``cad auto-update off``, the server reads the feed naming the next release, and a start of the
  server starts the same cad: nothing updates.
- ``self-broken``: an update to a release whose server cannot start (its daemon module raises): cad is that release, its
  server down; the feed then names the next, and ``cad server start``, failing, updates cad to it, whose server answers.
- ``self-uninstallable``: an update to a release uv cannot install as a tool (no command: "No executables are
  provided"): uv takes the tool away with the failed attempt, the helper puts the release before back, and its server
  answers; the plugin's switch on, no install command runs after the failed update.

**The bridge** from a shipped release (``--old``, 0.11.10 by default; 0.11.0 to 0.11.10 and 0.10.0 to 0.10.4 have the
updater), installed by its own ``cad setup`` through uvx, its server serving pages on the computer's port:

- ``updater``: its update button: its updater installs this build in ``releases/<new>`` and runs its hidden ``cad setup
  --engine-update``; its switch starts this build's server; that server runs the install command in install mode
  (cad a uv tool, both switches on) and hands over to the uv tool's server. The end: uv's ``cad`` in the bin folder in
  place of the shipped release's launcher, ``cad --version`` this build, the tool's server answering on the pages'
  port with their token, ``installations/current`` and its record naming the tool's environment, the hand-over
  recorded done, both switches on, and the old release folders still there (nothing of a past release is deleted).
- ``automatic`` (0.11.x): the same, by the shipped release's automatic update (an hour passes for its feed).
- ``store-only``: a computer that never ran our install command (no receipt of it, no plugin folder): the updater
  brings this build, and cad alone moves: no install command runs, nothing is owed, no uv tool, no plugin.
- ``rollback``: the updater to a build whose server cannot start: the shipped switch goes back, so the old release
  serves on the pages' port with their token, ``current`` and the ``cad`` command are its own, and the install command
  never runs.
- ``install-command``: the install command run by a person on a computer of the shipped release whose server serves
  pages: cad a uv tool, the old launcher gone, both switches on; ``cad server start`` then replaces the old server.
- ``typed``: the shipped release's own ``cad update`` typed (what today's skill text has an agent type where cad is
  older): it brings this build, whose plain ``cad setup`` runs the install command: the end of ``install-command``.
  On Windows that install cannot finish: the typed command is the shipped release's ``cad.exe``, still running, which
  Windows lets no one replace, so the install command refuses and says so. The command exits 1, and the computer is
  left as it was and working: the same release answers ``cad --version`` and serves the pages, ``current`` and the
  switches unchanged, no uv tool, nothing owed (no ``handover.json``) and no arrival kept. Then the way on every skill
  names, the install command run with no ``cad.exe`` running: the end of ``install-command``.
- ``store-typed``: the same on a store-only computer: cad alone moves, as in ``store-only``; ``cad server start`` then
  replaces the old server with this build's.

Usage::

    scripts/test/rehearse-update.py [ROUTE ...] [--old RELEASE] [--wheels DIR] [--uv-cache DIR]

``all`` (the default) is every route; ``self`` the six of cad updating itself; ``bridge`` the seven from a shipped
release. ``--wheels``: this tree's wheels as ``scripts/release/check-wheel-contents.sh`` keeps them; without it they
are built from the source (``tests/python/support/machine.py``, no packaged runtime: no route opens a page).
``--uv-cache``: one folder for uv's cache and Pythons, shared by every computer of the run (default: a new one of the
run's in the system's temporary folder, removed at its end; never one of the person's own folders of uv, cad or the
agent apps, ``real_computer.uv_refused``). A server's feed stamp is set back only while it is stopped (it writes that
file itself), and telemetry is off as each computer's kept choice too (``real_computer.quiet``). It needs uv and the network (PyPI: the shipped releases and what every release depends
on). Before and after every route it reads the modification times of the files a person's apps and cad keep on this
machine (``real_computer.Sentinels``), and fails where one moved. Exit 0 when every route held; 1, with what the
computer holds, when one did not. The release tier of ``.github/workflows/test.yml`` runs it on Linux, macOS and
Windows (``update-rehearsal``).
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import real_computer as rc  # noqa: E402 - beside it

REPO_ROOT = rc.REPO_ROOT
WINDOWS = rc.WINDOWS
OLD = "0.11.10"
_BASE = 9000 + os.getpid() % 800
# This tree as releases no index holds: the one installed first, the next, one whose server cannot start, the one after
# it, and one uv cannot install as a tool.
NEW, NEXT, BROKEN, AFTER, NOCMD = (f"0.11.{_BASE + step}" for step in range(5))
BROKEN_DAEMON = b"raise SystemExit('cad: this build cannot start its server (a rehearsal of a release that cannot)')\n"
# How long each wait may take: an install from uv's cache, a switch, a tending or two of a server (30 s each).
SECONDS = 600.0
INSTALL_SH = REPO_ROOT / "scripts" / "install" / "install.sh"
INSTALL_PS1 = REPO_ROOT / "scripts" / "install" / "install.ps1"
INSTALL_PY = REPO_ROOT / "scripts" / "install" / "install.py"
# A server started as a page link starts it, by a Python of the release (its own client), and what it says: its token
# and port.
START = "import json\nfrom cad.engine import client\nprint(json.dumps(client.request({'op': 'http'})))"
# Asked as no command (``internal``): a rehearsal's look never counts as work, which would keep a server from the idle
# its update and the bridge's hand-over wait for.
# Whether the shipped release's server answers its own client, asked by that client: "None" once it is gone.
OLD_STATUS = ("from cad.engine import client\ntry:\n    gone = client.request({'op': 'status'}, start=False) is None\n"
              "except ConnectionError:\n    gone = True\nprint(gone)")
ASK = ("import json, sys\nfrom cad.engine import client\n"
       "print(json.dumps(client.request({'op': sys.argv[1], 'internal': True}, start=False)))")


class Failed(rc.Failed):
    pass


def say(line: str = "") -> None:
    print(line, flush=True)


def installer_command(counted: Path | None = None) -> str:
    """The install command as cad runs it, but this tree's (``CAD_ENGINE_UPDATE_INSTALLER``); with ``counted``, each
    run first adds a line to that file."""
    if WINDOWS:
        count = f"Add-Content -LiteralPath '{counted}' -Value ran; " if counted else ""
        return (f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{count}Get-Content -Raw \'{INSTALL_PS1}\' | '
                'Invoke-Expression"')
    if counted:
        return f"""sh -c 'echo ran >> "$0"; exec sh "$1"' '{counted}' '{INSTALL_SH}'"""
    return f"sh '{INSTALL_SH}'"


class PyPI(http.server.ThreadingHTTPServer):
    """PyPI's JSON API for cad (``CAD_PYPI_URL``), naming as newest what the feed names: the release that is out."""

    def __init__(self, feed: rc.Feed) -> None:
        self.feed = feed
        pypi = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                found = self.path.split("?", 1)[0].rstrip("/") == "/pypi/cad/json"
                body = json.dumps({"info": {"version": pypi.feed.latest}}).encode() if found else b""
                self.send_response(200 if found else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        super().__init__(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/pypi"

    def close(self) -> None:
        self.shutdown()
        self.server_close()


class Box:
    """One private computer of a route (see the module). ``links``: where uv finds this tree's releases. A route of cad
    updating itself (``counted``) gets a folder of its own, holding only the releases that are out (``out``): an
    upgrade installs the newest there; its install command counts its runs (``runs``)."""

    def __init__(self, label: str, feed: rc.Feed, wheels: Path, shared: Path, *, named_state: bool = True,
                 pypi: PyPI | None = None, counted: bool = False) -> None:
        self.label, self.feed, self.wheels = label, feed, wheels
        # Short: Windows' paths stay well under its old limit.
        work = Path(tempfile.mkdtemp(prefix=f"cr{label[:3]}.")).resolve()
        self.links = work / "links" if counted else wheels
        self.links.mkdir(exist_ok=True)
        self.computer = rc.Computer(work, {}, feed=feed, shared=shared, wheels=self.links, helpers=("uv", "uvx"))
        self.work, self.home, self.bin, self.port = work, self.computer.home, self.computer.bin, self.computer.port
        self.counted = work / "install-command-runs.txt" if counted else None
        env = self.computer.env
        env.update({
            # The install command cad runs: this tree's, through its test hooks; its first run in install mode at
            # the server's first tending (a shipped switch here decides in seconds).
            "CAD_ENGINE_UPDATE_INSTALLER": installer_command(self.counted), "CAD_INSTALL_PY": str(INSTALL_PY),
            "CAD_ENGINE_UPDATE_FIRST_SECONDS": "0",
            # PyPI, as `cad update` asks it: a stand-in on loopback.
            **({"CAD_PYPI_URL": pypi.url} if pypi is not None else {}),
        })
        if not named_state:
            # 0.10.0 on Windows keeps its state in the local application data, apart from every later release's:
            # its computer names no state folder, so each release keeps its own where it would.
            env.pop("CAD_STATE_DIR")
            self.computer.state = self.home / ".local" / "state" / "cad"
            rc.quiet(self.computer.state)
        self.state = self.computer.state
        # Where the shipped release keeps its state: the computer's, or 0.10.0's own on Windows.
        self.old_state = self.state if named_state else self.home / "AppData" / "Local" / "cad-state"
        rc.quiet(self.old_state)
        self.env = env
        self.token = ""
        self.pythons: list[Path] = []  # the shipped release's Python, which stops its server at the end

    def out(self, version: str) -> None:
        """``version`` out: the feed and PyPI name it, and, on a computer of its own folder of releases, uv finds it."""
        if self.links != self.wheels:
            for wheel in self.wheels.glob(f"*-{version}-*.whl"):
                shutil.copy2(wheel, self.links / wheel.name)
        self.feed.latest = version

    def runs(self) -> int:
        """How many times cad ran the install command on this computer."""
        try:
            return len(self.counted.read_text(encoding="utf-8").split()) if self.counted else 0
        except OSError:
            return 0

    # --- running things here ----------------------------------------------------------------------------------

    def run(self, argv: list, *, timeout: float = SECONDS, check: bool = True,
            extra: dict | None = None) -> subprocess.CompletedProcess:
        argv = [str(part) for part in argv]
        if WINDOWS and not os.path.isabs(argv[0]):
            argv[0] = shutil.which(argv[0], path=self.env["PATH"]) or argv[0]
        done = subprocess.run(argv, env={**self.env, **(extra or {})}, cwd=self.work, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        if check and done.returncode != 0:
            raise Failed(f"{' '.join(argv[:6])} ... exited {done.returncode}:\n{done.stdout}\n{done.stderr}")
        return done

    def until(self, condition, what: str, seconds: float = SECONDS):
        deadline = time.monotonic() + seconds
        while True:
            found = condition()
            if found:
                return found
            if time.monotonic() > deadline:
                raise Failed(f"{self.label}: {what}, not within {seconds:.0f} s\n{self.said()}")
            time.sleep(0.5)

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

    def read(self, name: str) -> dict:
        """A JSON file of the state folder (the data folder of 0.11.10 and of a uv tool's cad alike), or {}."""
        try:
            found = json.loads((self.state / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    def read_old(self, name: str) -> dict:
        """A JSON file of the shipped release's state folder, or {}."""
        try:
            found = json.loads((self.old_state / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    def said(self) -> str:
        """What the computer holds, for a failure."""
        listing = lambda path: sorted(os.listdir(path)) if path.is_dir() else []  # noqa: E731
        parts = [f"computer {self.work}", f"  state: {listing(self.state)}",
                 f"  releases: {listing(self.old_state / 'releases')}, current: {self.current() or '(none)'}",
                 f"  bin: {listing(self.bin)}"]
        for name in ("update.json", "handover.json", "handover-move.json", "auto-update.json", "install-report.json"):
            if (self.state / name).exists():
                parts.append(f"  {name}: {json.dumps(self.read(name))[:800]}")
        parts.append(f"  switches: {self.read('settings.json').get('auto_update')}, plugin "
                     f"{self.read('settings.json').get('plugin')}; the install command ran {self.runs()} times")
        if (self.state / "install-command.log").is_file():
            parts.append("  install-command.log:\n"
                         + (self.state / "install-command.log").read_text(encoding="utf-8", errors="replace")[-3000:])
        # The engine folder, and why the last server started there could not take its lock or listen (the daemon's
        # failure note, ``places.failure_path``: ``engine.failed``), where it said.
        parts.append(f"  engine: {listing(self.work / 'engine')}")
        failed = self.work / "engine" / "engine.failed"
        if failed.is_file():
            parts.append(f"  engine.failed: {failed.read_text(encoding='utf-8', errors='replace')[:800]}")
        tools = self.run(["uv", "tool", "list", "--show-paths"], check=False, timeout=60)
        parts.append(f"  uv's tools: {tools.stdout.strip() or tools.stderr.strip()}")
        for log in (self.old_state / "update.log", *sorted((self.work / "engine").glob("*.log"))):
            if log.is_file():
                parts.append(f"  {log.name}:\n{log.read_text(encoding='utf-8', errors='replace')[-3000:]}")
        parts.append("  processes:\n" + self.running())
        return "\n".join(parts)

    def running(self) -> str:
        """The computer's processes, one a line (on Windows, each one's program); said where it could not look."""
        found = self.computer.processes()
        if not self.computer.looked:
            return "(this system did not let the run list its processes)"
        return "\n".join(f"{pid} {command}" for pid, command in found)

    def from_folder(self, folder: Path) -> list[str]:
        """The computer's processes that run from ``folder`` (by their command line; on Windows, their program)."""
        mark = os.path.normcase(str(folder))
        return [f"{pid} {command}" for pid, command in self.computer.processes() if mark in os.path.normcase(command)]

    def current(self) -> str:
        path = self.state / "installations" / "current"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def commands(self) -> list[Path]:
        """The ``cad`` commands in uv's bin folder that are there: on Windows cad.exe (uv's, or 0.11's launcher) and
        cad.cmd (0.10's launcher)."""
        return [path for path in rc.cad_commands(self.bin) if path.exists()]

    def cad(self) -> Path:
        """The ``cad`` command in uv's bin folder a shell runs, whatever wrote it."""
        return next(iter(self.commands()), rc.cad_commands(self.bin)[0])

    def version(self) -> str:
        said = self.run([self.cad(), "--version"], check=False, timeout=120)
        return said.stdout.strip().splitlines()[0] if said.returncode == 0 and said.stdout.strip() else \
            f"(exit {said.returncode}: {said.stderr.strip()[-300:]})"

    def tool(self) -> dict | None:
        """uv's tool ``cad``: its version, environment and command; None where uv lists none."""
        listed = self.run(["uv", "tool", "list", "--show-paths"], check=False, timeout=60).stdout.splitlines()
        for index, line in enumerate(listed):
            found = re.fullmatch(r"cad v(\S+) \((.+)\)", line.strip())
            if found:
                commands = [re.fullmatch(r"- cad(?:\.exe)? \((.+)\)", entry.strip()) for entry in listed[index + 1:]]
                return {"version": found[1], "env": found[2],
                        "command": next((match[1] for match in commands if match), "")}
        return None

    def ask(self, python: Path, op: str) -> dict | None:
        """The server's answer to ``op`` asked by the client of the release whose Python is ``python``, never
        starting one; None where none answers."""
        done = self.run([python, "-c", ASK, op], check=False, timeout=60)
        try:
            found = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return found if isinstance(found, dict) else None

    def serving(self, version: str) -> dict | None:
        """The server answering on the pages' port, with their token, as ``version``; its answer, else None."""
        status, answer = self.http("GET", "/api/v1/server")
        return answer if status == 200 and answer.get("release") == version else None

    def an_hour_passes(self) -> None:
        """The feed due again, as an hour passing makes it: its ``checked`` stamp (``versions.json``, in the data
        folder of 0.11.10 and of a uv tool's cad alike) set back 61 minutes. Only while no server runs, which writes
        that file as it reads the feed (Windows refuses a write that meets its own): ``hour_later``."""
        kept = self.read("versions.json")
        kept["checked"] = time.time() - 61 * 60
        (self.state / "versions.json").write_text(json.dumps(kept), encoding="utf-8")

    def hour_later(self) -> None:
        """The uv tool's server, as an hour passes while it runs: stopped by its own command (which returns once its
        lock is free: it writes nothing after), the feed's stamp set back, and started again, idle: it reads the
        feed at its first tending."""
        self.run([self.cad(), "server", "stop"])
        self.an_hour_passes()
        started = self.run([self.cad(), "server", "start"]).stdout
        if "started" not in started:
            raise Failed(f"{self.label}: cad server start said {started!r}")

    def old_hour_later(self, python: Path) -> None:
        """The shipped release's server, as an hour passes while it runs: stopped by its own client and awaited until
        its door is gone, the feed's stamp set back, and started again as a page link starts it (the same port and
        token, which it keeps)."""
        self.run([python, "-c", "from cad.engine import client\nclient.request({'op': 'stop'}, start=False)"],
                 check=False, timeout=60)
        self.until(lambda: self.run([python, "-c", OLD_STATUS], check=False, timeout=60).stdout.strip() == "True",
                   "the shipped release's server gone")
        self.an_hour_passes()
        answer = json.loads(self.run([python, "-c", START]).stdout.strip().splitlines()[-1])
        if int(answer["port"]) != self.port or answer["token"] != self.token:
            raise Failed(f"{self.label}: the shipped release's server came back on {answer['port']}, another token")

    def stop(self) -> list[str]:
        """Every server of the computer stopped, by its own client, and anything still running from its folder ended:
        what had to be ended (``looked``: whether it could see)."""
        if self.cad().exists():
            self.run([self.cad(), "server", "stop"], check=False, timeout=120)
        for python in self.pythons:
            if python.exists():
                self.run([python, "-c", "from cad.engine import client\nclient.request({'op': 'stop'}, start=False)"],
                         check=False, timeout=60)
        deadline = time.monotonic() + rc.GONE_SECONDS
        left = self.computer.processes()
        while left and time.monotonic() < deadline:
            time.sleep(0.5)
            left = self.computer.processes()
        for pid, _command in left:
            try:
                if WINDOWS:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return [f"{pid} {command}" for pid, command in left]

    # --- a computer the install command set up --------------------------------------------------------------

    def install_command(self, *, extra: dict | None = None) -> subprocess.CompletedProcess:
        """The install command as a person runs it (``install.sh`` piped to ``sh``; Windows: ``install.ps1`` to
        ``Invoke-Expression``), this tree's ``install.py``: its exit status 0."""
        if WINDOWS:
            argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    f"Get-Content -Raw '{INSTALL_PS1}' | Invoke-Expression"]
            done = subprocess.run(argv, env={**self.env, **(extra or {})}, cwd=self.work, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=SECONDS)
        else:
            done = subprocess.run(["sh"], input=INSTALL_SH.read_text(encoding="utf-8"), env={**self.env,
                                  **(extra or {})}, cwd=self.work, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=SECONDS)
        if done.returncode != 0:
            raise Failed(f"{self.label}: the install command exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n"
                         f"{self.said()}")
        return done

    def set_up(self, plugin: str) -> None:
        """This tree's ``NEW`` installed by the install command: a uv tool, its automatic updates on (by default, or
        as the install command left them); ``cad plugin auto-update`` then turned ``plugin`` (``on``, ``off``) by its
        own command; its server started."""
        self.out(NEW)
        self.install_command()
        self.is_tool(NEW)
        switches = self.read("settings.json").get("auto_update") or {}
        if switches.get("on") is False:
            raise Failed(f"{self.label}: the install command left cad's automatic updates off: {switches}")
        said = self.run([self.cad(), "plugin", "auto-update", plugin]).stdout.strip()
        if said != f"plugin auto-update: {plugin}":
            raise Failed(f"{self.label}: cad plugin auto-update {plugin} said {said!r}")
        started = self.run([self.cad(), "server", "start"]).stdout
        if f"cad {NEW}" not in started:
            raise Failed(f"{self.label}: cad server start said {started!r}")
        self.token = (self.ask(rc.interpreter(Path(self.tool()["env"])), "http") or {}).get("token", "")

    def is_tool(self, version: str) -> dict:
        """uv's tool ``cad`` at ``version``, its command in uv's bin folder (never the shipped launcher), and that
        command saying ``cad <version>``: the tool."""
        tool = self.tool()
        if tool is None or tool["version"] != version:
            raise Failed(f"{self.label}: uv's cad tool is {tool}, not {version}\n{self.said()}")
        if os.path.realpath(Path(tool["command"]).parent) != os.path.realpath(self.bin):
            raise Failed(f"{self.label}: the tool's cad command is not in uv's bin folder {self.bin}: {tool}")
        stale = [path for path in self.commands() if launcher(path)]
        if stale:
            raise Failed(f"{self.label}: a shipped release's launcher is still in uv's bin folder: {stale}")
        if self.version() != f"cad {version}":
            raise Failed(f"{self.label}: cad --version says {self.version()!r}, not cad {version}")
        return tool

    def flat(self) -> None:
        """The state folder flat, as 0.11.10 keeps it: never a ``versions/`` folder."""
        if (self.state / "versions").exists():
            raise Failed(f"{self.label}: the state folder holds versions/: {sorted(os.listdir(self.state / 'versions'))}")

    def tool_serves(self, version: str) -> dict:
        """The uv tool's server answering as ``version``, from the tool's environment: its status."""
        def found():
            tool = self.tool()
            if tool is None or tool["version"] != version:
                return None
            status = self.ask(rc.interpreter(Path(tool["env"])), "status")
            return status if status and status.get("version") == version and rc._within(
                Path(status.get("prefix") or "/nowhere"), Path(tool["env"])) else None
        status = self.until(found, f"the uv tool's server answering as {version}")
        self.flat()
        return status

    # --- a computer of a shipped release ---------------------------------------------------------------------

    def install_old(self, old: str) -> Path:
        """The shipped release as its install command set it up: its own ``cad setup`` through uvx, its server
        serving pages on the computer's port. Its Python."""
        self.feed.latest = old
        self.run(["uvx", "--no-config", "--managed-python", "--python", "3.14", "--from", f"cad-server=={old}", "cad",
                  "setup"], timeout=1500)
        python = rc.interpreter(self.old_state / "releases" / old)
        if not python.exists():
            raise Failed(f"{self.label}: {old}'s setup made no release folder\n{self.said()}")
        self.pythons.append(python)
        answer = json.loads(self.run([python, "-c", START]).stdout.strip().splitlines()[-1])
        self.token = answer["token"]
        if int(answer["port"]) != self.port:
            raise Failed(f"{self.label}: {old}'s server took port {answer['port']}, not the computer's {self.port}")
        self.until(lambda: self.serving(old), f"{old}'s server on port {self.port} with the page token")
        if not any(launcher(path) for path in self.commands()):
            raise Failed(f"{self.label}: {old}'s setup wrote no cad command in {self.bin}: {self.commands()}")
        return python

    def button(self, target: str) -> None:
        """The shipped release's update button, on the port pages are on."""
        self.feed.latest = target
        status, answer = self.http("POST", "/api/v1/local/update", body=b"{}",
                                   headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202 or (answer.get("update") or {}).get("target") != target:
            raise Failed(f"{self.label}: the update button answered {status}: {answer}")

    def switched(self, old: str, target: str) -> dict:
        """The shipped updater's switch, as its record (``update.json``) says it, from ``old`` to ``target``, ended."""
        said = self.until(lambda: (lambda found: found if found.get("to") == target and "ok" in found else None)(
            self.read_old("update.json")), f"{old}'s switch to {target}")
        if said.get("from") != old:
            raise Failed(f"{self.label}: the switch's record: {said}")
        return said


def launcher(path: Path) -> bool:
    """Whether ``path`` is the ``cad`` command 0.10.0 to 0.11.10 wrote (its mark, ``cad proxy: <revision>``, in its first
    lines, or in the ``__main__.py`` of the zip behind 0.11's cad.exe)."""
    import zipfile

    if not path.is_file() or path.is_symlink():
        return False
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                head = archive.read("__main__.py")[:512]
        else:
            head = path.read_bytes()[:4096]
    except (OSError, KeyError, zipfile.BadZipFile):
        return False
    return bool(re.search(rb"(#|rem) cad proxy: \d+", head))


# --- cad updating itself ----------------------------------------------------------------------------------------


def updated(box: Box, target: str, outcome: str = "installed") -> dict:
    """cad's own update to ``target`` ended (its record, ``auto-update.json``) with ``outcome``: the record."""
    record = box.until(lambda: (lambda found: found if found.get("release") == target and "ended" in found
                                else None)(box.read("auto-update.json")), f"cad's own update to {target} ended")
    if record.get("outcome") != outcome:
        raise Failed(f"{box.label}: cad's own update to {target}: {record}\n{box.said()}")
    return record


def never_installed(box: Box, record: dict, why: str) -> None:
    """The update's record says no install command runs after it, and cad ran none (``why``: the route's reason)."""
    if record.get("then_install") or "install_command" in record or box.runs() != 0:
        raise Failed(f"{box.label}: the install command ran after the update ({why}): {record}, runs {box.runs()}\n"
                     f"{box.said()}")


def self_update(box: Box) -> None:
    box.set_up("on")
    box.out(NEXT)
    box.hour_later()
    record = updated(box, NEXT)
    if not record.get("then_install"):
        raise Failed(f"{box.label}: the update says no install command runs after it: {record}")
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    # Then `cad plugin install`, once, by the new cad: its exit status kept, its output in the log.
    record = box.until(lambda: (lambda found: found if "install_command" in found else None)(
        box.read("auto-update.json")), "the install command after the update")
    log = box.state / "install-command.log"
    if record["install_command"] != 0 or box.runs() != 1 or not log.is_file():
        raise Failed(f"{box.label}: the install command after the update: {record}, ran {box.runs()} times, log "
                     f"{log.is_file()}\n{box.said()}")
    say(f"        {NEW} -> {NEXT} by itself, idle, as `uv tool install cad@latest` got it; then `cad plugin install`, "
        "once, exit 0")
    pages(box, NEXT)


def pages(box: Box, version: str) -> None:
    """A page that was open before the update still reaches a server: the pages' port, with their token, answered by
    ``version``'s, nothing asked of it in between (the last check of a route: what came before is said already)."""
    box.until(lambda: box.serving(version), f"{version}'s server answering the pages' port {box.port} with their "
              "token, as before the update", seconds=90)
    say(f"        an open page's port and token reach {version}'s server")


def self_typed(box: Box) -> None:
    # Automatic updates off, the plugin's switch on: a typed update needs neither, and never runs the install command.
    box.set_up("on")
    switched = box.run([box.cad(), "auto-update", "off"]).stdout.strip()
    if switched != "auto-update: off":
        raise Failed(f"{box.label}: cad auto-update off said {switched!r}")
    # Nothing newer on PyPI: said, and nothing restarts.
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip()) != (0, f"cad {NEW} is the newest release") or box.read("auto-update.json"):
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: {done.stdout}{done.stderr}, "
                     f"{box.read('auto-update.json')}")
    box.out(NEXT)  # out on PyPI; the feed's hour has not passed for the server
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    said = f"cad {NEW} updated to {NEXT}"
    if (done.returncode, done.stdout.strip()) != (0, said):
        raise Failed(f"{box.label}: cad update exited {done.returncode}: {done.stdout}{done.stderr}\n{box.said()}")
    record = updated(box, NEXT)
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    if (box.read("settings.json").get("auto_update") or {}).get("on") is not False:
        raise Failed(f"{box.label}: after cad update: switches {box.read('settings.json').get('auto_update')}")
    never_installed(box, record, "a typed cad update")
    say(f"        `cad update` with nothing newer: 'cad {NEW} is the newest release', nothing restarted; then {NEW} -> "
        f"{NEXT} with automatic updates off ({said!r}); no install command")
    pages(box, NEXT)
    never_installed(box, box.read("auto-update.json"), "a typed cad update")


def self_at_start(box: Box) -> None:
    box.set_up("off")
    box.run([box.cad(), "server", "stop"])
    # The feed as the server last read it, naming the next release, read within the hour: due at the next start.
    box.out(NEXT)
    (box.state / "versions.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": NEXT}}),
                                             encoding="utf-8")
    done = box.run([box.cad(), "server", "start"], check=False)
    if done.returncode != 0 or f"cad {NEXT}" not in done.stdout:
        raise Failed(f"{box.label}: cad server start exited {done.returncode}: {done.stdout}{done.stderr}\n"
                     f"{box.said()}")
    record = updated(box, NEXT)
    if record.get("tries") != 1 or "restored" in record:
        raise Failed(f"{box.label}: cad's own update at the start: {record}\n{box.said()}")
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    never_installed(box, record, "the plugin's switch off")
    say(f"        {NEW} -> {NEXT} as `cad server start` started, the starter waiting: {done.stdout.strip()!r}; the "
        "plugin's switch off: no install command")


def self_off(box: Box) -> None:
    box.set_up("off")
    switched = box.run([box.cad(), "auto-update", "off"]).stdout.splitlines()
    if switched != ["auto-update: off"]:
        raise Failed(f"{box.label}: cad auto-update off said {switched}")
    box.out(NEXT)
    box.hour_later()
    # The server reads the feed at its first tending; then a start, which updates first where the switch is on.
    box.until(lambda: (box.read("versions.json").get("feed") or {}).get("latest") == NEXT and
              time.time() - box.read("versions.json").get("checked", 0) < 600, "the server reading the feed")
    box.run([box.cad(), "server", "stop"])
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started or box.version() != f"cad {NEW}" or box.read("auto-update.json"):
        raise Failed(f"{box.label}: with the switch off: {started!r}, {box.version()}, {box.read('auto-update.json')}")
    box.tool_serves(NEW)
    say(f"        switched off: the feed named {NEXT}, the server started as {NEW}, nothing attempted")


def self_broken(box: Box) -> None:
    box.set_up("off")
    box.out(BROKEN)
    box.hour_later()
    record = updated(box, BROKEN)
    if not str(record.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: {BROKEN}'s server started: {record}")
    if box.version() != f"cad {BROKEN}":
        raise Failed(f"{box.label}: cad --version says {box.version()!r}, not cad {BROKEN}")
    # The next release: `cad server start`, failing, updates cad to it (no server runs to write the feed's file).
    box.out(AFTER)
    box.an_hour_passes()
    done = box.run([box.cad(), "server", "start"], check=False)
    if done.returncode == 0 or f"updating cad to {AFTER}" not in done.stderr:
        raise Failed(f"{box.label}: cad server start on {BROKEN} exited {done.returncode}: {done.stdout}{done.stderr}")
    updated(box, AFTER)
    box.tool_serves(AFTER)
    box.is_tool(AFTER)
    say(f"        {NEW} -> {BROKEN} (its server down) -> {AFTER} by a failed cad server start")


def self_uninstallable(box: Box) -> None:
    box.set_up("on")
    box.out(NOCMD)
    box.hour_later()
    record = updated(box, NOCMD, "failed")
    if record.get("restored") is not True:
        raise Failed(f"{box.label}: the release before was not put back: {record}\n{box.said()}")
    box.tool_serves(NEW)
    box.is_tool(NEW)
    never_installed(box, record, "a failed update, the plugin's switch on")
    say(f"        {NOCMD} could not be installed ({record.get('detail')!r}); {NEW} put back and serving")


# --- the bridge ---------------------------------------------------------------------------------------------------


def bridged(box: Box, old: str) -> None:
    """The end of the bridge (see the module)."""
    old_state = box.old_state
    record = box.until(lambda: (lambda found: found if found.get("state") in ("done", "gave up") else None)(
        box.read("handover.json")), "the install command in install mode, done")
    if (record.get("mode"), record.get("version"), record.get("state")) != ("install", NEW, "done"):
        raise Failed(f"{box.label}: the hand-over: {record}\n{box.said()}")
    status = box.tool_serves(NEW)
    tool = box.is_tool(NEW)
    current = box.current()
    entry = json.loads((box.state / "installations" / f"{current}.json").read_text(encoding="utf-8")) if current else {}
    if current != NEW or not rc._within(Path(entry.get("prefix") or "/nowhere"), Path(tool["env"])):
        raise Failed(f"{box.label}: installations/current names {current!r}: {entry}")
    move = box.read("handover-move.json")
    if move.get("outcome") not in ("current", "installed") or str(move.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the move to the uv tool's server: {move}")
    switches = box.read("settings.json").get("auto_update") or {}
    if switches.get("on") is False:
        raise Failed(f"{box.label}: automatic updates off after the bridge: {switches}")
    kept = [old_state / "releases" / old, old_state / "releases" / NEW]
    if not all(path.is_dir() for path in kept):
        raise Failed(f"{box.label}: a release folder is gone: {[str(path) for path in kept if not path.is_dir()]}")
    left = box.from_folder(old_state / "releases")
    if left:
        raise Failed(f"{box.label}: processes still run from the release folders:\n" + "\n".join(left))
    say(f"        {old} -> {NEW}: uv's cad in {box.bin}, its server ({status.get('prefix')}), current {current}, "
        f"hand-over done (attempt {record.get('attempts')}), automatic updates on, releases/{old} and releases/{NEW} kept")
    pages(box, NEW)


def updater(box: Box, old: str) -> None:
    box.install_old(old)
    box.button(NEW)
    if box.old_state == box.state:
        box.switched(old, NEW)
    else:
        # 0.10.0 on Windows: this build's setup takes the computer over (its switch could only go back): 0.10.0's own
        # records then name this build, and 0.10.0's server is not running beside it.
        box.until(lambda: (box.old_state / "installations" / "current").is_file() and (
            box.old_state / "installations" / "current").read_text(encoding="utf-8").strip() == NEW,
            f"{old}'s own records naming {NEW}")
    bridged(box, old)


def automatic(box: Box, old: str) -> None:
    if not old.startswith("0.11."):
        raise Failed(f"{box.label}: {old} has no automatic update (0.11.0 and later have)")
    python = box.install_old(old)
    box.feed.latest = NEW
    box.old_hour_later(python)
    box.switched(old, NEW)
    bridged(box, old)


def store_only(box: Box, old: str) -> None:
    box.install_old(old)
    # What only our install command's setup leaves: gone, as on a computer that only ever had a store's copy.
    (box.old_state / "install-receipt.json").unlink(missing_ok=True)
    shutil.rmtree(box.old_state / "plugin", ignore_errors=True)
    box.button(NEW)
    box.switched(old, NEW)
    box.until(lambda: box.serving(NEW), f"{NEW}'s server on the pages' port")
    status = box.ask(rc.interpreter(box.old_state / "releases" / NEW), "status") or {}
    held = {"current": box.current(), "handover": box.read("handover.json"), "tool": box.tool(),
            "plugin": (box.state / "plugin").exists(), "report": box.read("install-report.json"),
            "cad": box.version()}
    if (held["current"], held["handover"], held["tool"], held["plugin"], held["report"]) != (NEW, {}, None, False, {}) \
            or not rc._within(Path(status.get("prefix") or "/nowhere"), box.old_state / "releases" / NEW) \
            or held["cad"] != f"cad {NEW}":
        raise Failed(f"{box.label}: a store-only computer after the update: {held}, server {status.get('prefix')}\n"
                     f"{box.said()}")
    say(f"        {old} -> {NEW}, cad alone: no install command, nothing owed, no uv tool, no plugin folder; the "
        f"shipped cad command runs {NEW}")


def rollback(box: Box, old: str) -> None:
    box.install_old(old)
    box.button(BROKEN)
    said = box.until(lambda: (lambda found: found if found.get("to") == BROKEN and "restored" in found else None)(
        box.read_old("update.json")), f"the switch to {BROKEN} gone back from")
    if (said.get("ok"), said.get("restored")) != (False, True):
        raise Failed(f"{box.label}: the switch did not go back to {old}: {said}")
    box.until(lambda: box.serving(old), f"{old} serving again on the pages' port with their token")
    owed = box.read("handover.json")
    held = {"current": box.current(), "cad": box.version(), "tool": box.tool(), "report": box.read("install-report.json"),
            "owed": (owed.get("state"), owed.get("attempts"))}
    if (held["current"], held["cad"], held["tool"], held["report"]) != (old, f"cad {old}", None, {}) \
            or held["owed"] not in (("owed", 0), (None, None)):
        raise Failed(f"{box.label}: after going back: {held}\n{box.said()}")
    left = box.from_folder(box.old_state / "releases" / BROKEN)
    if left:
        raise Failed(f"{box.label}: processes of {BROKEN} still run:\n" + "\n".join(left))
    say(f"        {old} -> {BROKEN} gone back from: {old} serves the pages, current and the cad command its own, "
        "no install command, no uv tool")


def by_hand(box: Box, old: str, said: str, how: str) -> None:
    """The end of the install command a person ran on a computer of ``old`` (``said``: its output): uv's cad, the old
    launcher removed, and ``cad server start`` replacing the old server; ``how`` says how the computer got there."""
    box.is_tool(NEW)
    if "Removed the cad command of an earlier release" not in said:
        raise Failed(f"{box.label}: the install command did not say it removed {old}'s cad command:\n{said}")
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    box.tool_serves(NEW)
    box.until(lambda: box.current() == NEW, f"installations/current naming {NEW}")
    left = box.from_folder(box.old_state / "releases")
    if left:
        raise Failed(f"{box.label}: {old}'s server still runs:\n" + "\n".join(left))
    say(f"        {old} -> {NEW} {how}: uv's cad, both switches on, the old server replaced by `cad server start`, "
        f"current {NEW}")
    pages(box, NEW)


def install_command(box: Box, old: str) -> None:
    box.install_old(old)
    box.feed.latest = NEW
    by_hand(box, old, box.install_command().stdout, "by the install command")


# What the install command says where a cad.exe runs from cad's own folder (``install.py``: ``cad_running``), as the
# shipped release's typed ``cad update`` does on Windows while it runs this build's ``cad setup``.
CAD_EXE_RUNS = "cad.exe is running from cad's own folder, and Windows lets no one replace it while it does"
# The records a typed update that could not install leaves as they were (the state folder's).
RECORDS = ("handover.json", "arrival.json", "install-report.json", "auto-update.json", "update.json")


def held(box: Box) -> dict:
    """What a person on a computer of a shipped release relies on, and what would act on it later: for ``typed`` on Windows."""
    return {"cad": box.version(), "current": box.current(), "tool": box.tool(),
            "launcher": sorted(path.name for path in box.commands() if launcher(path)),
            "switches": box.read("settings.json").get("auto_update"),
            "records": {name: box.read(name) for name in RECORDS},
            "new release folder": (box.old_state / "releases" / NEW).is_dir()}


def typed_on_windows(box: Box, old: str) -> None:
    """``typed`` on Windows (see the module): the install refused while the typed ``cad.exe`` runs, the computer as it
    was, then the install command run by hand."""
    before = held(box)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 300)
    words = done.stdout + done.stderr
    if done.returncode != 1 or CAD_EXE_RUNS not in words or f"text-to-cad {NEW} is out (this is {old})" not in words:
        raise Failed(f"{box.label}: {old}'s cad update exited {done.returncode}, not 1 with the install command's "
                     f"refusal:\n{done.stdout}\n{done.stderr}\n{box.said()}")
    box.until(lambda: box.serving(old), f"{old}'s server still serving the pages' port {box.port} with their token")
    after = held(box)
    expected = {**before, "new release folder": True}  # the shipped update made it before it ran this build's setup
    if after != expected or (after["cad"], after["current"], after["tool"]) != (f"cad {old}", old, None) \
            or not after["launcher"] or after["records"]["handover.json"] or after["records"]["arrival.json"]:
        raise Failed(f"{box.label}: after {old}'s cad update was refused: {after}\nbefore it: {before}\n{box.said()}")
    left = box.from_folder(box.old_state / "releases" / NEW)
    if left:
        raise Failed(f"{box.label}: processes of {NEW} still run after {old}'s cad update:\n" + "\n".join(left))
    say(f"        {old}'s `cad update` exited 1, refused while its cad.exe runs; cad {old} answers and serves the "
        f"pages, current {old}, no uv tool, nothing owed, no arrival kept")
    by_hand(box, old, box.install_command().stdout, "then by the install command, with no cad.exe running")


def typed(box: Box, old: str) -> None:
    box.install_old(old)
    box.feed.latest = NEW
    if WINDOWS:
        typed_on_windows(box, old)
        return
    box.run([box.cad(), "update"], timeout=SECONDS + 300)
    box.is_tool(NEW)
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    box.tool_serves(NEW)
    box.until(lambda: box.current() == NEW, f"installations/current naming {NEW}")
    left = box.from_folder(box.old_state / "releases")
    if left:
        raise Failed(f"{box.label}: {old}'s server still runs:\n" + "\n".join(left))
    say(f"        {old} -> {NEW} by {old}'s `cad update`: uv's cad, both switches on, the old server replaced by "
        f"`cad server start`, current {NEW}")


def store_typed(box: Box, old: str) -> None:
    box.install_old(old)
    (box.old_state / "install-receipt.json").unlink(missing_ok=True)
    shutil.rmtree(box.old_state / "plugin", ignore_errors=True)
    box.feed.latest = NEW
    box.run([box.cad(), "update"], timeout=SECONDS + 300)
    started = box.run([box.cad(), "server", "start"]).stdout
    status = box.until(lambda: (lambda found: found if found and found.get("version") == NEW else None)(
        box.ask(rc.interpreter(box.old_state / "releases" / NEW), "status")), f"{NEW}'s server answering")
    held = {"current": box.current(), "handover": box.read("handover.json"), "tool": box.tool(),
            "plugin": (box.state / "plugin").exists(), "report": box.read("install-report.json"),
            "cad": box.version()}
    if (held["current"], held["handover"], held["tool"], held["plugin"], held["report"]) != (NEW, {}, None, False, {}) \
            or not rc._within(Path(status.get("prefix") or "/nowhere"), box.old_state / "releases" / NEW) \
            or held["cad"] != f"cad {NEW}":
        raise Failed(f"{box.label}: a store-only computer after {old}'s cad update: {held}, {started!r}, server "
                     f"{status.get('prefix')}\n{box.said()}")
    say(f"        {old} -> {NEW} by {old}'s `cad update`, cad alone: no install command, no uv tool, no plugin folder; "
        f"`cad server start` serves {NEW}")


SELF = {"self-update": self_update, "self-typed": self_typed, "self-at-start": self_at_start, "self-off": self_off,
        "self-broken": self_broken, "self-uninstallable": self_uninstallable}
BRIDGE = {"updater": updater, "automatic": automatic, "store-only": store_only, "rollback": rollback,
          "install-command": install_command, "typed": typed, "store-typed": store_typed}


def publish_all(source: Path | None, out: Path) -> None:
    """This tree as every release the routes name, into ``out`` (see the module)."""
    base = out.parent / "base"
    base.mkdir(parents=True, exist_ok=True)
    if source is None:
        sys.path.insert(0, str(REPO_ROOT))
        from tests.python.support.machine import release  # noqa: PLC0415 - the source tree's wheels

        release(NEW, base)
    else:
        for wheel in source.glob("*.whl"):
            shutil.copy2(wheel, base / wheel.name)
    for version in (NEW, NEXT, AFTER):
        rc.publish(base, version, out)
    rc.publish(base, BROKEN, out, replace={"cad_server/engine/daemon.py": BROKEN_DAEMON})
    rc.publish(base, NOCMD, out, commands=False)


def main(argv: list[str] | None = None) -> int:
    routes = {**SELF, **BRIDGE}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("routes", nargs="*", default=["all"], choices=("all", "self", "bridge", *routes),
                        metavar="ROUTE", help=f"one or more of: all, self, bridge, {', '.join(routes)}")
    parser.add_argument("--old", default=OLD, help="the shipped release the bridge's routes start on")
    parser.add_argument("--wheels", type=Path, help="this tree's wheels (default: built from the source)")
    parser.add_argument("--uv-cache", type=Path, help="uv's cache and Pythons, shared by the run's computers")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if shutil.which("uv") is None or shutil.which("uvx") is None:
        say("rehearse-update: uv is not installed")
        return 1
    chosen: list[str] = []
    for name in args.routes:
        chosen += list(routes) if name == "all" else list(SELF) if name == "self" else \
            list(BRIDGE) if name == "bridge" else [name]
    chosen = list(dict.fromkeys(chosen))
    run = Path(tempfile.mkdtemp(prefix="crr.")).resolve()
    shared = args.uv_cache.resolve() if args.uv_cache else run / "uv"
    wheels = run / "wheels"
    publish_all(args.wheels.resolve() if args.wheels else None, wheels)
    feed = rc.Feed(NEW)
    pypi = PyPI(feed)
    say(f"rehearse-update: {', '.join(chosen)}; this tree as {NEW} (and {NEXT}, {BROKEN} whose server cannot start, "
        f"{AFTER}, {NOCMD} with no command); the bridge from {args.old}")
    failed = 0
    began_all = time.monotonic()
    try:
        for name in chosen:
            before = rc.Sentinels.here()
            alone = WINDOWS and args.old == "0.10.0" and name in BRIDGE
            box = Box(name, feed, wheels, shared, named_state=not alone, pypi=pypi, counted=name in SELF)
            say(f"-- {name}: a computer in {box.work}")
            began = time.monotonic()
            try:
                box.computer.isolation(say)
                say(f"  CAD_PYPI_URL={box.env['CAD_PYPI_URL']}")
                if not box.env["CAD_PYPI_URL"].startswith("http://127.0.0.1:"):
                    raise Failed("the computer is not isolated: CAD_PYPI_URL")
                if name in SELF:
                    routes[name](box)
                else:
                    routes[name](box, args.old)
                say(f"ok      {name}{'' if name in SELF else f', from {args.old}'} ({time.monotonic() - began:.0f} s)")
            except (rc.Failed, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as failure:
                failed += 1
                say(f"FAILED  {name}{'' if name in SELF else f', from {args.old}'} ({time.monotonic() - began:.0f} s): "
                    f"{failure}")
            finally:
                left = box.stop()
                if left:
                    say(f"note    {name}: ended what was still running:\n" + "\n".join(left))
                elif not box.computer.looked:
                    say(f"note    {name}: this system did not let the run list its processes: whether anything was "
                        "left running is not known")
                moved = before.moved(rc.Sentinels.here())
                if moved:
                    failed += 1
                    say(f"FAILED  {name}: this machine's own files moved:\n" + "\n".join(moved))
                shutil.rmtree(box.work, ignore_errors=True)
    finally:
        feed.close()
        pypi.close()
        shutil.rmtree(run, ignore_errors=True)
    say(f"rehearse-update: {len(chosen) - failed} held, {failed} failed ({time.monotonic() - began_all:.0f} s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
