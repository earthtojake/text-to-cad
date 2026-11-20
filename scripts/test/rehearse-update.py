#!/usr/bin/env python3
"""cad's updates rehearsed end to end on private computers (``scripts/test/real_computer.py``: a home, cad's state,
engine and cache folders, uv's tools and their commands of its own, never this machine's), with real uv, real servers,
the real install command (``scripts/install/install.sh``, this tree's ``install.py``) and, for the bridge, the REAL
shipped releases from PyPI.

This tree is published as releases no index holds (``<major>.<minor>.<9000+n>`` of ``VERSION`` and the next few, n
from this process: ``real_computer.stamp``, newer than every release PyPI holds), written into a folder uv reads beside
the index (``UV_FIND_LINKS``, ``CAD_UPDATE_FIND_LINKS``), and the version feed is a stand-in on loopback
(``CAD_API_URL``), as is PyPI's JSON API that ``cad update`` asks
(``CAD_PYPI_URL``), which names what the feed names. Every computer's server takes a port of its own
(``CAD_ENGINE_DEFAULT_PORT``: the true default, 3245, on CI alone). This build's servers tend themselves every two
seconds, not every half minute (``CAD_ENGINE_TEND_SECONDS``), and so wait two of those tendings, not a minute, after
they start before the plugin first catches up; nothing else of their timing changes, so a step that waits for a minute
with nothing run still waits that minute. No real agent app is on any PATH.

Every computer has a folder of releases of its own, holding only those that are out (``Box.out``): the install command
installs PyPI's newest, and an upgrade the newest of a major (``uv tool install --upgrade "cad>=X,<N"``; ``cad update
--major``'s ``uv tool install --upgrade "cad>=X"`` the newest of all), so a release not out yet must not be there. What is out,
the feed names (``latest``, and each major's newest as ``lines``) and the stand-in PyPI lists (each release, its file not
yanked). Releases of a higher major (``above``) have a minor and a patch of 9000 and more, past anything PyPI holds of
that major.

The install command counts the runs cad starts of it on every computer (``Box.runs``): the bridge's (install mode,
a shipped release's own setup, a server's one run on a computer our setup reached), and the one the ``cad plugin
update`` of 0.11.12 and 0.11.13 makes. ``cad plugin install``, which this
build's server runs once where cad got newer, installs the plugin with cad's own code and runs no install command: on a
route of cad updating itself the count stays 0, and the run is read from cad's record of it (``caught_up``). The feed
keeps which address each cad read it at (``addresses``): this build's the new one, ``/v1/releases``, a shipped
release's the old, ``/v1/versions``; a route where one read the other's fails, ``self-update`` checks this build read
the new one and ``updater`` the shipped release the old.

**cad updating itself** (a computer the install command set up: cad a uv tool, its automatic updates on).

- ``self-update``: with ``cad plugin update auto on``, the feed names the next release and an hour passes; the running
  server, idle, stops, uv installs the next release, and its server answers; then that server, newer than the release
  the plugin is up to date for, runs its own ``cad plugin install`` once: exit 0, kept in its record
  (``install-command.json``: up to date for the next release, at its first try), its output in
  ``install-command.log``; the helper ran none, and no install command ran.
- ``self-typed``: with ``cad update auto off`` and the plugin's switch on, ``cad update`` is typed with nothing newer on
  PyPI: it says so and nothing restarts; then PyPI names the next release and ``cad update`` is typed again: the
  server asks PyPI at once and updates cad to it; the command, a running ``cad`` of the tool, waits and says so; the uv
  tool is the next release, its server answers, and the plugin catches up: that server runs ``cad plugin install``
  once, as after an automatic update.
- ``self-typed-stopped``: the same with no server running: ``cad update`` with nothing newer says so and starts no
  server; with the next release out it says ``cad <new> updated to <next>`` (exit 0, nothing on stderr), the record
  says no server is started (``"start": false``, no ``started``), the uv tool is the next release, no server and no
  process of the computer runs afterwards, automatic updates stay off, and no ``cad plugin install`` runs (no server
  runs to catch the plugin up).
- ``self-at-start``: the plugin's switch off, the server stopped, the feed's file already naming the next release, then
  ``cad server start``: the server it spawns hands its start to the update, and the starter, a running ``cad`` of the
  tool, waits for the update's server. It exits 0, the uv tool is the next release and serves, the attempt installed
  at its first try (on Windows this failed every time until cad's update set the running ``cad.exe`` aside), and no
  ``cad plugin install`` runs.
- ``self-off``: with ``cad update auto off``, the server reads the feed naming the next release, and a start of the
  server starts the same cad: nothing updates.
- ``self-broken``: an update to a release whose server cannot start (its daemon module raises): cad is that release, its
  server down; the feed then names the next, and ``cad server start``, failing, updates cad to it, whose server answers.
- ``self-uninstallable``: an update to a release uv cannot install as a tool (no command: "No executables are
  provided"): uv takes the tool away with the failed attempt, the helper puts the release before back, and its server
  answers, and counts the failure once; the plugin's switch on, no ``cad plugin install`` runs after the failed update
  (cad is no newer).
- ``self-major``: the rule that a new major never installs itself. With the next release and a release a major up out,
  the server, idle, updates to the next release (``uv tool install --upgrade "cad>=<new>,<N>"``), never the higher
  major, and uv keeps that range; then, automatic updates off, a typed ``cad update`` says the next release is the
  newest of its major and names the higher one in one line, beginning nothing; ``cad update --major`` installs the
  higher major (``uv tool install --upgrade "cad>=<next>"``: uv keeps the floor alone); then, automatic updates on,
  with a newer release of that major and one two majors up out, the server updates inside the new major alone, and uv
  keeps the new range.
- ``self-pipx``: cad installed by ``pipx install cad`` (pipx itself a uv tool of the computer's, on pip's backend, its
  folders in the home, pip offered this tree's releases by ``PIP_FIND_LINKS``): the install command, a person's run,
  finds nothing newer for pipx's cad (its own ``cad update``), installs no uv tool, hands over to that cad's ``cad
  plugin install`` and turns the plugin's switch on by that cad (``cad plugin update auto on``); the next release
  and a release a major up out and an hour passed, the server, idle, updates it to the next release by ``pipx
  upgrade cad --pip-args=cad>=<new>,<N>``, never the higher major, and the new cad's server runs ``cad plugin install`` once; then, automatic updates off, a typed ``cad
  update`` with nothing newer in its major says so and names the higher major, and with the release after out updates
  pipx's cad to it, whose server runs ``cad plugin install`` once more; ``cad update --major`` installs the higher major
  (``pipx upgrade cad --pip-args=cad>=<installed>``: pipx 1.18 keeps the range of an upgrade for the next), and,
  automatic updates on, the server then updates inside the new major alone, never two
  majors up. Each time pipx's cad serves the new release, and the new cad's server runs ``cad plugin install`` once; an
  open page's port and token reach the last.

**The bridge** from a shipped release (``--old``, 0.11.11 by default; 0.11.0 to 0.11.11 and 0.10.0 to 0.10.4 have the
updater), installed by its own ``cad setup`` through uvx, its server serving pages on the computer's port:

- ``updater``: its update button: its updater installs this build in ``releases/<new>`` and runs its hidden ``cad setup
  --engine-update``; its switch starts this build's server; that server runs the install command in install mode
  (cad a uv tool, both switches on) and hands over to the uv tool's server. The end: uv's ``cad`` in the bin folder in
  place of the shipped release's launcher, ``cad --version`` this build, the tool's server answering on the pages'
  port with their token, ``installations/current`` and its record naming the tool's environment, the hand-over
  recorded done, both switches on, and the old release folders still there (nothing of a past release is deleted).
  The install command ran once, and two tendings of the tool's server later still once.
- ``automatic`` (0.11.x): the same, by the shipped release's automatic update (an hour passes for its feed).
- ``updater-fallback``: ``updater`` where the install command fails and writes no report: install mode's attempt
  fails, this build's server installs cad as a uv tool itself and hands over; install mode stays owed (one attempt),
  for the tool's server to run later, and the tool's server serves the pages.
- ``store-only``: a computer that never ran our install command (no receipt of it, no plugin folder): the updater
  brings this build, whose server installs cad as a uv tool itself (the shipped launcher set aside, then deleted) and
  hands over to the tool's server, as ``updater`` ends; but the install command never runs: nothing owed, no plugin
  folder, no plugin switch.
- ``rollback``: the updater to a build whose server cannot start: the shipped switch goes back, so the old release
  serves on the pages' port with their token, ``current`` and the ``cad`` command are its own, and the install command
  never runs.
- ``install-command``: the install command run by a person on a computer of the shipped release whose server serves
  pages: cad a uv tool, the old launcher gone, both switches on; ``cad server start`` then replaces the old server.
- ``typed``: the shipped release's own ``cad update`` typed (what today's skill text has an agent type where cad is
  older): it brings this build, whose plain ``cad setup`` runs the install command: the end of ``install-command``.
  From 0.11.x, automatic updates were turned off first with the shipped release's own ``cad update auto off``: this
  build's ``cad update auto`` then says off, and the next release, out and the feed read, does not install itself.
  On Windows the typed command is the shipped release's ``cad.exe``, running all along, which Windows lets no one
  replace or delete: the install command renames it aside and installs uv's cad all the same, and the command exits 0.
  What it set aside, which ran until the command exited, goes at the install command's next run, a person's, which
  finds nothing newer for cad (the next release is not out yet).
- ``store-typed``: the same on a store-only computer: cad alone moves, as in ``store-only``; ``cad server start`` then
  replaces the old server with this build's, which ends as ``store-only`` does.
- ``uv-line``: the uv line typed (a skill's Setup block): ``uv tool install cad`` refused by the shipped launcher,
  then with ``--force`` (on Windows 0.10's ``cad.cmd`` is not in its way); ``cad server start`` replaces the old
  server; the tool's server turns the plugin's switch on and runs the install command once; stopped and started
  again, two tendings later still once.
- ``store-uv-line``: the same on a store-only computer: two tendings after the start the install command never ran,
  and there is no plugin switch.

**A release whose own ``cad plugin update`` runs the install command** (0.11.12 and 0.11.13: global installs
already, with no ``cad plugin install``; ``RUNS_IT``, the newer of the two), installed from PyPI as a uv tool:

- ``plugin-update``: its ``cad plugin update`` typed, with this tree out as the newest release. That command runs the
  install command, marked as a run of cad's own (``CAD_INSTALL_BY_CAD``): cad, a uv tool that starts, is left as it
  is; asked first, quietly, whether it has ``cad plugin install`` (``--help``), it refuses (exit status 2: it has no
  such command, asked of it first on its own too), so the newest release's runs instead, outside the tool (``uv tool
  run ... cad@latest plugin install``: this tree's, from the computer's folder of releases), and nothing of that
  refusal reaches the output; then the install command turns the plugin's switch on by the shipped release's own
  ``cad plugin update auto on``. The end: exit
  0; the install command ran once, and never again from inside itself; uv's cad is still the shipped release, which
  says the switch is on and keeps itself as the release the plugin is up to date for; no server was started, and
  nothing of the computer runs.

Usage::

    scripts/test/rehearse-update.py [ROUTE ...] [--old RELEASE] [--wheels DIR] [--uv-cache DIR]

``all`` (the default) is every route; ``self`` the nine of cad updating itself; ``bridge`` the ten from a shipped
release; ``plugin-update`` is of neither group, and runs with ``all`` or by its name. ``--wheels``: this tree's wheels as ``scripts/release/check-wheel-contents.sh`` keeps them; without it they
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
import shlex
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
OLD = "0.11.11"
# The newer of the two releases whose own `cad plugin update` runs the install command (0.11.12, 0.11.13): what
# ``plugin-update`` starts on.
RUNS_IT = "0.11.13"
_BASE = 9000 + os.getpid() % 800
# This tree as releases no index holds: the one installed first, the next, one whose server cannot start, the one after
# it, and one uv cannot install as a tool.
NEW, NEXT, BROKEN, AFTER, NOCMD = (rc.stamp(_BASE + step) for step in range(5))
MAJOR = int(NEW.split(".", 1)[0])


def above(majors: int, step: int) -> str:
    """This tree as a release ``majors`` major versions above its own: a minor and a patch far from any real one
    (9000 and up), so it is newer than any release PyPI holds of that major (the yanked 1.x of the name's earlier
    owner among them)."""
    return rc.stamp(_BASE + step, version=f"{MAJOR + majors}.9000.0")


# This tree as releases of higher majors: one a major up, the next of that major, and one two majors up.
HIGH, HIGH2, HIGHER = above(1, 5), above(1, 6), above(2, 7)
# What `cad update` and `cad doctor` say where a release of a higher major is out (``auto_update.MAJOR_LINE``).
MAJOR_LINE = ("cad {release}, a new major version, is out and does not install itself: `cad update --major` installs it "
              "(what changes: https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations)")
BROKEN_DAEMON = b"raise SystemExit('cad: this build cannot start its server (a rehearsal of a release that cannot)')\n"
# How long each wait may take: an install from uv's cache, a switch, a tending or two of a server.
SECONDS = 600.0
# How often this build's servers tend themselves on these computers (``CAD_ENGINE_TEND_SECONDS``; a person's every
# 30 s): each step the bridge takes waits for a tending.
TEND_SECONDS = 2.0
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


# What the install command's runs printed, every stream, and how each ended, in a computer's folder (``WRAPPER``).
OUTPUT = "install-command-output.log"
# The install command cad runs on a computer: a wrapper, run by this run's own Python (``-I``), that adds a line to the
# file that counts the runs, runs this tree's install command, and passes on everything it prints (as one stream)
# while it copies it, and its exit status, to ``OUTPUT``. Its exit status is the command's. The server throws an
# install mode run's output away; the failure dump shows this file. Its first line names the run's values: the run a
# server began, where one did (``CAD_INSTALL_ATTEMPT``, which the ``cad plugin update`` of 0.11.12 and 0.11.13, the
# releases that run the install command for it, sets).
WRAPPER = """import os, subprocess, sys
if counted:
    with open(counted, "a", encoding="utf-8") as runs:
        runs.write("ran\\n")
with open(output, "ab") as kept:
    kept.write(f"--- the install command (attempt {os.environ.get('CAD_INSTALL_ATTEMPT', 'none')})\\n".encode())
    kept.flush()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in process.stdout:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
        kept.write(line)
        kept.flush()
    code = process.wait()
    kept.write(f"--- exit {code}\\n".encode())
sys.exit(code)
"""


def installer_command(work: Path, counted: Path | None = None) -> str:
    """The install command as cad runs it, but this tree's (``CAD_ENGINE_UPDATE_INSTALLER``), by ``WRAPPER``, written
    into ``work``; with ``counted``, each run first adds a line to that file."""
    command = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                f"Get-Content -Raw '{INSTALL_PS1}' | Invoke-Expression"] if WINDOWS else ["sh", str(INSTALL_SH)])
    wrapper = work / "install-command.py"
    wrapper.write_text(f"counted, output, command = {str(counted or '')!r}, {str(work / OUTPUT)!r}, {command!r}\n"
                       + WRAPPER, encoding="utf-8")
    argv = [sys.executable, "-I", str(wrapper)]
    return subprocess.list2cmdline(argv) if WINDOWS else shlex.join(argv)


class PyPI(rc.Loopback):
    """PyPI's JSON API for cad (``CAD_PYPI_URL``): ``info.version`` what the feed names as newest, and ``releases``, each
    release that is out (``released``, set by ``Box.out``) with a file that is not yanked, as PyPI lists them."""

    def __init__(self, feed: rc.Feed) -> None:
        self.feed = feed
        self.released: list[str] = []
        pypi = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                found = self.path.split("?", 1)[0].rstrip("/") == "/pypi/cad/json"
                releases = {version: [{"filename": f"cad-{version}-py3-none-any.whl", "packagetype": "bdist_wheel",
                                       "yanked": False, "yanked_reason": None}] for version in pypi.released}
                body = json.dumps({"info": {"version": pypi.feed.latest},
                                   "releases": releases}).encode() if found else b""
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
    """One private computer of a route (see the module). ``links``: where uv finds this tree's releases, a folder of
    its own holding only the releases that are out (``out``): an install or an upgrade installs the newest there. With
    ``counted``, the install command cad starts counts its runs (``runs``)."""

    def __init__(self, label: str, feed: rc.Feed, wheels: Path, shared: Path, *, named_state: bool = True,
                 pypi: PyPI | None = None, counted: bool = False) -> None:
        self.label, self.feed, self.wheels, self.pypi = label, feed, wheels, pypi
        self.released: list[str] = []  # the releases out on this computer's index, the feed and PyPI (``out``)
        # Short: Windows' paths stay well under its old limit.
        work = Path(tempfile.mkdtemp(prefix=f"cr{label[:3]}.")).resolve()
        self.links = work / "links"
        self.links.mkdir(exist_ok=True)
        self.computer = rc.Computer(work, {}, feed=feed, shared=shared, wheels=self.links, helpers=("uv", "uvx"))
        self.work, self.home, self.bin, self.port = work, self.computer.home, self.computer.bin, self.computer.port
        self.counted = work / "install-command-runs.txt" if counted else None
        env = self.computer.env
        env.update({
            # The install command cad runs: this tree's, through its test hooks; its first run in install mode at
            # the server's first tending (a shipped switch here decides in seconds).
            "CAD_ENGINE_UPDATE_INSTALLER": installer_command(work, self.counted), "CAD_INSTALL_PY": str(INSTALL_PY),
            "CAD_ENGINE_UPDATE_FIRST_SECONDS": "0",
            # This build's servers tend themselves every TEND_SECONDS, not every half minute (the shipped releases'
            # servers do not read it).
            "CAD_ENGINE_TEND_SECONDS": str(TEND_SECONDS),
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
        self.launchers: list[str] = []  # the names of the cad commands the shipped release wrote

    def out(self, version: str) -> None:
        """``version`` out: uv finds it in the computer's folder of releases (a shipped release, from PyPI, has none
        there), and the feed and PyPI name what is out: ``latest`` the newest of all, ``lines`` each major's newest,
        PyPI's ``releases`` each one."""
        for wheel in self.wheels.glob(f"*-{version}-*.whl"):
            shutil.copy2(wheel, self.links / wheel.name)
        self.released.append(version)
        numbers = lambda release: tuple(int(part) for part in release.split("."))  # noqa: E731
        lines: dict[str, str] = {}
        for release in sorted(self.released, key=numbers):
            lines[release.split(".", 1)[0]] = release
        self.feed.latest, self.feed.lines = max(self.released, key=numbers), lines
        if self.pypi is not None:
            self.pypi.released = list(self.released)

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
        """A JSON file of the state folder (the data folder of 0.11.11 and of a uv tool's cad alike), or {}."""
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
        for name in ("update.json", "handover.json", "handover-move.json", "auto-update.json", "install-command.json",
                     "install-report.json"):
            if (self.state / name).exists():
                parts.append(f"  {name}: {json.dumps(self.read(name))[:800]}")
        parts.append(f"  switches: {self.read('settings.json').get('auto_update')}, plugin "
                     f"{self.read('settings.json').get('plugin')}; the install command ran {self.runs()} times")
        if (self.state / "install-command.log").is_file():
            parts.append("  install-command.log:\n"
                         + (self.state / "install-command.log").read_text(encoding="utf-8", errors="replace")[-3000:])
        if (self.work / OUTPUT).is_file():  # every run of the install command cad started, its output and its end
            parts.append(f"  {OUTPUT}:\n"
                         + (self.work / OUTPUT).read_text(encoding="utf-8", errors="replace")[-4000:])
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
        """The computer's processes, one a line with its command line (on Windows, each one's program, then its command
        line where it can be read); said where it could not look."""
        found = self.computer.processes()
        if not self.computer.looked:
            return "(this system did not let the run list its processes)"
        return "\n".join(f"{pid} {command}" + (f"\n      {rc.windows_command_line(pid) or '(command line not read)'}"
                                               if WINDOWS else "") for pid, command in found)

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

    # The feed as last read, in the data folder: this build's (``cad_server.updates.FILE``) and 0.11.11's, each its own.
    FEED_FILES = ("releases.json", "versions.json")

    def an_hour_passes(self) -> None:
        """The feed due again, as an hour passing makes it: its ``checked`` stamp set back 61 minutes, in the file of
        each release that keeps one (``FEED_FILES``: this build's ``releases.json``, 0.11.11's ``versions.json``, in
        the data folder of 0.11.11 and of a uv tool's cad alike). Only while no server runs, which writes that file as
        it reads the feed (Windows refuses a write that meets its own): ``hour_later``. A file not there is due already."""
        for name in self.FEED_FILES:
            if not (self.state / name).is_file():
                continue
            kept = self.read(name)
            kept["checked"] = time.time() - 61 * 60
            (self.state / name).write_text(json.dumps(kept), encoding="utf-8")

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
        as the install command left them); ``cad plugin update auto`` then turned ``plugin`` (``on``, ``off``) by its
        own command; its server started."""
        self.out(NEW)
        self.install_command()
        self.is_tool(NEW)
        switches = self.read("settings.json").get("auto_update") or {}
        if switches.get("on") is False:
            raise Failed(f"{self.label}: the install command left cad's automatic updates off: {switches}")
        said = self.run([self.cad(), "plugin", "update", "auto", plugin]).stdout.strip()
        if said != f"plugin update auto: {plugin}":
            raise Failed(f"{self.label}: cad plugin update auto {plugin} said {said!r}")
        started = self.run([self.cad(), "server", "start"]).stdout
        if f"cad {NEW}" not in started:
            raise Failed(f"{self.label}: cad server start said {started!r}")
        self.token = (self.ask(rc.interpreter(Path(self.tool()["env"])), "http") or {}).get("token", "")

    def is_tool(self, version: str, *, kept: tuple[str, ...] = ()) -> dict:
        """uv's tool ``cad`` at ``version``, its command in uv's bin folder (never the shipped launcher, but one named
        in ``kept`` that may stay), and that command saying ``cad <version>``: the tool."""
        tool = self.tool()
        if tool is None or tool["version"] != version:
            raise Failed(f"{self.label}: uv's cad tool is {tool}, not {version}\n{self.said()}")
        if os.path.realpath(Path(tool["command"]).parent) != os.path.realpath(self.bin):
            raise Failed(f"{self.label}: the tool's cad command is not in uv's bin folder {self.bin}: {tool}")
        stale = [path for path in self.commands() if launcher(path) and path.name not in kept]
        if stale:
            raise Failed(f"{self.label}: a shipped release's launcher is still in uv's bin folder: {stale}")
        if self.version() != f"cad {version}":
            raise Failed(f"{self.label}: cad --version says {self.version()!r}, not cad {version}")
        return tool

    def flat(self) -> None:
        """The state folder flat, as 0.11.11 keeps it: never a ``versions/`` folder."""
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
        self.out(old)
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
        self.launchers = [path.name for path in self.commands() if launcher(path)]
        if not self.launchers:
            raise Failed(f"{self.label}: {old}'s setup wrote no cad command in {self.bin}: {self.commands()}")
        return python

    def button(self, target: str) -> None:
        """The shipped release's update button, on the port pages are on."""
        self.out(target)
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
    """Whether ``path`` is the ``cad`` command 0.10.0 to 0.11.11 wrote (its mark, ``cad proxy: <revision>``, in its first
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
    """No ``cad plugin install`` ran after the update, and cad began none (``why``: the route's reason): the helper's
    record names none and the plugin's record names no run; nor did an install command (the computer counted none)."""
    began = box.read("install-command.json").get("release")
    if record.get("then_install") or "install_command" in record or began or box.runs() != 0:
        raise Failed(f"{box.label}: `cad plugin install` ran after the update ({why}): {record}, began for {began}, "
                     f"the install command ran {box.runs()} times\n{box.said()}")


def caught_up(box: Box, release: str) -> dict:
    """The server of ``release``, newer than the release the plugin is up to date for, ran ``cad plugin install`` once
    (``install-command.json``: its run for ``release`` ended 0, at the first try, and the plugin now up to date for
    ``release``), its output in ``install-command.log``; that command installed the plugin with cad's own code, so no
    install command ran (the computer counted none), and the helper's record names none; the update counted once by
    that server (its record marked ``reported``). The record.

    The run was the server's own, so it ran under its deadline: only a ``cad plugin install`` that carries the name of
    the record's run (``CAD_PLUGIN_SERVER_RUN``: its ``at``) writes that run's outcome as ``ok``; a run that exited
    without saying so is kept as failed by the server that began it."""
    record = box.until(lambda: (lambda found: found if found.get("release") == release and found.get("outcome") in
                                ("ok", "failed") else None)(box.read("install-command.json")),
                       f"the run of `cad plugin install` for {release}")
    log = box.state / "install-command.log"
    helper = box.read("auto-update.json")
    if (record.get("outcome"), record.get("code"), record.get("for"), record.get("tries")) != ("ok", 0, release, 1) \
            or box.runs() != 0 or not log.is_file() or "then_install" in helper or "install_command" in helper:
        raise Failed(f"{box.label}: `cad plugin install` after cad got newer: {record}, the install command ran "
                     f"{box.runs()} times (not 0), log {log.is_file()}, the helper's record {helper}\n{box.said()}")
    # Then the update is counted, once: its record marked (the computer's telemetry is off, so nothing is sent).
    box.until(lambda: box.read("auto-update.json").get("reported") is True, "the update counted by the new server")
    return record


def read_feed(box: Box, address: str, agent: str) -> None:
    """The feed's ``address`` (``versions`` or ``releases``) read on this computer by ``agent`` (its ``User-Agent``)."""
    if (address, agent) not in box.feed.reads:
        raise Failed(f"{box.label}: {agent} never read /{address} (the feed's reads: {sorted(set(box.feed.reads))})")


def addresses(box: Box) -> str:
    """Which of the feed's addresses each cad read on this computer, never the other's: this build's
    (``User-Agent: cad``) the new one, ``releases``, a shipped release's (``cadgen``) the old one, ``versions``. The
    route's line."""
    reads = sorted(set(box.feed.reads))
    crossed = [read for read in reads if read in (("versions", "cad"), ("releases", "cadgen"))]
    if crossed:
        raise Failed(f"{box.label}: the feed read at the other's address: {crossed}")
    return ", ".join(f"{agent or 'no agent'} read /{address}" for address, agent in reads) or "nothing read the feed"


def self_update(box: Box) -> None:
    box.set_up("on")
    box.out(NEXT)
    box.hour_later()
    updated(box, NEXT)
    read_feed(box, "releases", "cad")
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    # Then `cad plugin install`, once, by the new cad's server: kept in its record, its output in the log.
    caught_up(box, NEXT)
    if (box.state / "versions.json").exists():
        raise Failed(f"{box.label}: this build wrote versions.json, the feed's file of 0.10.0 to 0.11.11")
    say(f"        {NEW} -> {NEXT} by itself, idle, as `uv tool install --upgrade \"{bounded(NEW)}\"` got it; then the "
        "new server ran `cad plugin install`, once, exit 0; no versions.json written")
    pages(box, NEXT)


def bounded(version: str) -> str:
    """The requirement cad's own update bounds an upgrade from ``version`` by: its major, never below it."""
    return f"cad>={version},<{int(version.split('.', 1)[0]) + 1}"


def recorded(box: Box) -> str:
    """The requirement uv keeps for the cad tool (its receipt's ``specifier``; '' for none: the newest of all)."""
    import tomllib

    receipt = Path(box.tool()["env"]) / "uv-receipt.toml"
    first = tomllib.loads(receipt.read_text(encoding="utf-8"))["tool"]["requirements"][0]
    return first.get("specifier", "") if isinstance(first, dict) else str(first)[len("cad"):]


def self_major(box: Box) -> None:
    """cad installs by itself any newer release of its major, never a higher major: the automatic update to the newer
    release of this major with a higher major out; a typed ``cad update`` that stays and names the higher major;
    ``cad update --major`` installs it; then the automatic update stays inside the new major."""
    box.set_up("off")
    box.out(NEXT)
    box.out(HIGH)  # both out: the feed's `lines` name each, its `latest` the higher major's
    box.hour_later()
    record = updated(box, NEXT)
    read_feed(box, "releases", "cad")
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    if (record.get("wanted"), record.get("major"), recorded(box).replace(" ", "")) != (NEXT, False,
                                                                                         bounded(NEW)[len("cad"):]):
        raise Failed(f"{box.label}: the automatic update: {record}, uv keeps {recorded(box)!r}\n{box.said()}")
    say(f"        {HIGH} and {NEXT} out: {NEW} -> {NEXT} by itself (`uv tool install --upgrade \"{bounded(NEW)}\"`), "
        f"never {HIGH}; uv keeps {recorded(box)!r}")
    # Typed: nothing newer in this major; the higher major named in one line, nothing begun.
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    before = box.read("auto-update.json")
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    said = [f"cad {NEXT} is the newest {MAJOR}.x release", MAJOR_LINE.format(release=HIGH)]
    if (done.returncode, done.stdout.strip().splitlines(), done.stderr.strip()) != (0, said, "") \
            or box.read("auto-update.json").get("at") != before.get("at") or box.version() != f"cad {NEXT}":
        raise Failed(f"{box.label}: cad update with a higher major out exited {done.returncode}: {done.stdout}"
                     f"{done.stderr}, {box.read('auto-update.json')}\n{box.said()}")
    say(f"        `cad update`: {' / '.join(said)!r}; nothing begun")
    # `cad update --major`: the higher major, and the range uv kept gone.
    done = box.run([box.cad(), "update", "--major"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip(), done.stderr.strip()) != (0, f"cad {NEXT} updated to {HIGH}", ""):
        raise Failed(f"{box.label}: cad update --major exited {done.returncode}: {done.stdout}{done.stderr}\n"
                     f"{box.said()}")
    record = updated(box, HIGH)
    box.tool_serves(HIGH)
    box.is_tool(HIGH)
    if (record.get("asked"), record.get("major"), recorded(box).replace(" ", "")) != (True, True, f">={NEXT}"):
        raise Failed(f"{box.label}: the update across majors: {record}, uv keeps {recorded(box)!r}\n{box.said()}")
    say(f"        `cad update --major`: {NEXT} -> {HIGH} (`uv tool install --upgrade \"cad>={NEXT}\"`); uv keeps "
        f"{recorded(box)!r}")
    # Afterwards the automatic update stays inside the new major.
    switched = box.run([box.cad(), "update", "auto", "on"]).stdout.strip()
    if switched != "update auto: on":
        raise Failed(f"{box.label}: cad update auto on said {switched!r}")
    box.out(HIGH2)
    box.out(HIGHER)
    box.hour_later()
    record = updated(box, HIGH2)
    box.tool_serves(HIGH2)
    box.is_tool(HIGH2)
    if record.get("wanted") != HIGH2 or recorded(box).replace(" ", "") != bounded(HIGH)[len("cad"):]:
        raise Failed(f"{box.label}: the automatic update in the new major: {record}, uv keeps {recorded(box)!r}\n"
                     f"{box.said()}")
    say(f"        {HIGH2} and {HIGHER} out: {HIGH} -> {HIGH2} by itself (`\"{bounded(HIGH)}\"`), never {HIGHER}; "
        f"uv keeps {recorded(box)!r}")
    pages(box, HIGH2)


def pages(box: Box, version: str) -> None:
    """A page that was open before the update still reaches a server: the pages' port, with their token, answered by
    ``version``'s, nothing asked of it in between (the last check of a route: what came before is said already)."""
    box.until(lambda: box.serving(version), f"{version}'s server answering the pages' port {box.port} with their "
              "token, as before the update", seconds=90)
    say(f"        an open page's port and token reach {version}'s server")


def self_typed(box: Box) -> None:
    # Automatic updates off, the plugin's switch on: a typed update needs neither; the plugin catches up all the same.
    box.set_up("on")
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
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
    if (record.get("asked"), record.get("installer")) != (True, "uv"):
        raise Failed(f"{box.label}: the record of a typed update: {record}")
    box.tool_serves(NEXT)
    box.is_tool(NEXT)
    if (box.read("settings.json").get("auto_update") or {}).get("on") is not False:
        raise Failed(f"{box.label}: after cad update: switches {box.read('settings.json').get('auto_update')}")
    caught_up(box, NEXT)
    say(f"        `cad update` with nothing newer: 'cad {NEW} is the newest release', nothing restarted; then {NEW} -> "
        f"{NEXT} with automatic updates off ({said!r}); then the new server ran `cad plugin install`, once, exit 0")
    pages(box, NEXT)
    tendings(box, Path(box.tool()["env"]), 2)
    caught_up(box, NEXT)  # and only once: still its first try


def self_typed_stopped(box: Box) -> None:
    """``cad update`` typed with no server running: cad updates in the command's own process, the helper starts no
    server, and ``cad plugin install`` never runs."""
    box.set_up("on")  # the plugin's switch on: a typed update still never runs `cad plugin install`
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    python = rc.interpreter(Path(box.tool()["env"]))
    box.run([box.cad(), "server", "stop"])
    box.until(lambda: box.ask(python, "status") is None, "no server running")
    # Nothing newer on PyPI: said, nothing begun, no server started.
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    say(f"        typed, nothing newer: exit {done.returncode}, stdout {done.stdout.strip()!r}, "
        f"stderr {done.stderr.strip()!r}")
    if (done.returncode, done.stdout.strip()) != (0, f"cad {NEW} is the newest release") \
            or box.read("auto-update.json") or box.ask(python, "status") is not None:
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: "
                     f"{done.stdout}{done.stderr}, {box.read('auto-update.json')}\n{box.said()}")
    box.out(NEXT)  # out on PyPI
    began = time.monotonic()
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    say(f"        typed, {NEXT} out: exit {done.returncode} after {time.monotonic() - began:.0f} s, "
        f"stdout {done.stdout.strip()!r}, stderr {done.stderr.strip()!r}")
    said = f"cad {NEW} updated to {NEXT}"
    if (done.returncode, done.stdout.strip(), done.stderr.strip()) != (0, said, ""):
        raise Failed(f"{box.label}: cad update exited {done.returncode}: {done.stdout}{done.stderr}\n{box.said()}")
    record = updated(box, NEXT)
    say(f"        the record: {record}")
    if record.get("start") is not False or "started" in record:
        raise Failed(f"{box.label}: the helper was to start no server: {record}")
    box.is_tool(NEXT)
    python = rc.interpreter(Path(box.tool()["env"]))
    # No server afterwards: none answers, and nothing of the computer runs once the helper has exited.
    box.until(lambda: not box.computer.processes(), "nothing of the computer running", seconds=60)
    if box.ask(python, "status") is not None or box.computer.processes():
        raise Failed(f"{box.label}: a server runs after the update:\n{box.said()}")
    if (box.read("settings.json").get("auto_update") or {}).get("on") is not False:
        raise Failed(f"{box.label}: switches {box.read('settings.json').get('auto_update')}")
    never_installed(box, record, "a typed cad update")
    say(f"        no server ran: {NEW} -> {NEXT} by a typed `cad update` ({said!r}); no server after it, no "
        f"`cad plugin install`, processes {box.computer.processes()} (looked: {box.computer.looked})")


def self_at_start(box: Box) -> None:
    box.set_up("off")
    box.run([box.cad(), "server", "stop"])
    # The feed as the server last read it, naming the next release, read within the hour: due at the next start.
    box.out(NEXT)
    (box.state / "releases.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": NEXT}}),
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
        "plugin's switch off: no `cad plugin install`")


def self_off(box: Box) -> None:
    box.set_up("off")
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.splitlines()
    if switched != ["update auto: off"]:
        raise Failed(f"{box.label}: cad update auto off said {switched}")
    box.out(NEXT)
    box.hour_later()
    # The server reads the feed at its first tending; then a start, which updates first where the switch is on.
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == NEXT and
              time.time() - box.read("releases.json").get("checked", 0) < 600, "the server reading the feed")
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
    # The failure is counted, once, by the server of the release put back.
    box.until(lambda: box.read("auto-update.json").get("reported") is True, "the failed update counted by the old server")
    say(f"        {NOCMD} could not be installed ({record.get('detail')!r}); {NEW} put back and serving, the failure "
        "counted")


# --- cad installed by pipx ----------------------------------------------------------------------------------------

# The variables of pip and pipx a computer with pipx holds besides its own (``with_pipx``).
PIPX_FOLDERS = ("PIPX_HOME", "PIPX_BIN_DIR", "PIPX_MAN_DIR", "PIP_CACHE_DIR")


def with_pipx(box: Box) -> Path:
    """pipx on the computer, as a person may have it: ``uv tool install pipx`` (the computer's own uv tools, its command
    in the home's ``.local/bin``, on PATH), on uv's Python 3.14, its folders in the home (``PIPX_HOME``; ``PIPX_BIN_DIR``
    the home's ``.local/bin``, pipx's default and uv's; ``PIPX_MAN_DIR``), pipx's classic backend, pip
    (``PIPX_DEFAULT_BACKEND``), whose cache is the run's (``PIP_CACHE_DIR``, beside uv's), which reads no configuration
    file of this machine's (``PIP_CONFIG_FILE``), and which is offered this tree's releases as uv is (``PIP_FIND_LINKS``:
    the computer's folder of releases). Each folder said, and ``Failed`` where one is not the computer's or the run's.
    pipx's environment of cad (``<PIPX_HOME>/venvs/cad``)."""
    pipx_home = box.home / ".local" / "share" / "pipx"
    box.env.update({"PIPX_HOME": str(pipx_home), "PIPX_BIN_DIR": str(box.bin),
                    "PIPX_MAN_DIR": str(box.home / ".local" / "share" / "man"), "PIPX_DEFAULT_BACKEND": "pip",
                    "PIP_CACHE_DIR": str(box.computer.uv / "pip"), "PIP_CONFIG_FILE": os.devnull,
                    "PIP_FIND_LINKS": str(box.links), "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1"})
    for name in PIPX_FOLDERS:
        say(f"  {name}={box.env[name]}")
        if not (rc._within(Path(box.env[name]), box.work) or rc._within(Path(box.env[name]), box.computer.uv)):
            raise Failed(f"the computer is not isolated: {name}")
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", "pipx"])
    if not shutil.which("pipx", path=box.env["PATH"]):
        raise Failed(f"{box.label}: uv's pipx is not on the computer's PATH")
    return pipx_home / "venvs" / "cad"


def pipx_said(box: Box) -> str:
    """What pipx says it holds, for a failure."""
    listed = box.run(["pipx", "list", "--short"], check=False, timeout=60)
    return f"  pipx's tools: {listed.stdout.strip() or listed.stderr.strip()}\n{box.said()}"


def pipx_is(box: Box, env: Path, version: str) -> None:
    """pipx's cad at ``version``: its metadata says so, the ``cad`` command in the bin folder is pipx's (a link into its
    environment; on Windows pipx's copy), it says ``cad <version>``, and uv has no cad tool beside it."""
    try:
        held = json.loads((env / "pipx_metadata.json").read_text(encoding="utf-8"))["main_package"]["package_version"]
    except (OSError, ValueError, KeyError) as error:
        raise Failed(f"{box.label}: pipx's cad has no metadata: {error}\n{pipx_said(box)}") from None
    command = box.cad()
    linked = WINDOWS or (command.is_symlink() and rc._within(Path(os.path.realpath(command)), env))
    if held != version or not command.exists() or not linked or box.version() != f"cad {version}" or box.tool():
        raise Failed(f"{box.label}: pipx's cad is {held}, its command {command} (linked {linked}), cad --version says "
                     f"{box.version()!r}, uv's cad tool {box.tool()}; not {version}\n{pipx_said(box)}")


def pipx_serves(box: Box, env: Path, version: str) -> dict:
    """pipx's cad's server answering as ``version``, from pipx's environment of cad: its status."""
    def found():
        status = box.ask(rc.interpreter(env), "status")
        return status if status and status.get("version") == version and rc._within(
            Path(status.get("prefix") or "/nowhere"), env) else None
    return box.until(found, f"pipx's cad's server answering as {version}")


def self_pipx(box: Box) -> None:
    """cad installed by ``pipx install cad``: the install command, a person's run, finds nothing newer for it,
    installs no second cad, and has it turn the plugin's switch on; it updates itself by ``pipx upgrade cad`` inside its
    major (then ``cad plugin install`` once), and a typed ``cad update`` updates it the same way; ``cad update --major``
    takes it across."""
    env = with_pipx(box)
    box.out(NEW)
    box.run(["pipx", "install", "cad"])
    pipx_is(box, env, NEW)
    said = box.install_command().stdout
    # A person's run: pipx's own cad is asked for a newer one (`cad update`), and says there is none, in the install
    # command's one line.
    if f"Updating cad {NEW} to the newest release..." not in said or f"cad {NEW} is the newest " not in said \
            or "another program's" in said:
        raise Failed(f"{box.label}: the install command with pipx's cad said:\n{said}\n{pipx_said(box)}")
    pipx_is(box, env, NEW)
    switches = box.read("settings.json")
    if (switches.get("plugin") or {}).get("auto_update") is not True or (switches.get("auto_update") or {}).get("on") \
            is False:
        raise Failed(f"{box.label}: after the install command: {switches}")
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    box.token = (box.ask(rc.interpreter(env), "http") or {}).get("token", "")
    pipx_serves(box, env, NEW)
    say(f"        `pipx install cad` gave {NEW}; the install command found nothing newer for it (no uv tool), and it "
        "turned the plugin's switch on")
    # By itself: an hour passes with the next release out, and a release of a higher major.
    box.out(NEXT)
    box.out(HIGH)
    box.hour_later()
    updated(box, NEXT)
    pipx_serves(box, env, NEXT)
    pipx_is(box, env, NEXT)
    caught_up(box, NEXT)
    say(f"        {HIGH} and {NEXT} out: {NEW} -> {NEXT} by itself, idle, as `pipx upgrade cad --pip-args="
        f"{bounded(NEW)}` got it, never {HIGH}; then the new server ran `cad plugin install`, once, exit 0")
    pages(box, NEXT)
    # Typed, with automatic updates off: nothing newer in this major (the higher major named), then the release after.
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    higher = MAJOR_LINE.format(release=HIGH)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip().splitlines()) != (0, [f"cad {NEXT} is the newest {MAJOR}.x release",
                                                                   higher]):
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: {done.stdout}{done.stderr}")
    box.out(AFTER)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    typed = f"cad {NEXT} updated to {AFTER}"
    if (done.returncode, done.stdout.strip().splitlines()) != (0, [typed, higher]):
        raise Failed(f"{box.label}: cad update exited {done.returncode}: {done.stdout}{done.stderr}\n{pipx_said(box)}")
    updated(box, AFTER)
    pipx_serves(box, env, AFTER)
    pipx_is(box, env, AFTER)
    caught_up(box, AFTER)
    say(f"        `cad update` with nothing newer: 'cad {NEXT} is the newest {MAJOR}.x release' and {HIGH} named; then "
        f"{typed!r}, automatic updates off; then the new server ran `cad plugin install`, once more, exit 0")
    # `cad update --major`: `pipx upgrade cad --pip-args=cad>=<installed>`, the newest of all (the range pipx 1.18 kept
    # from the last upgrade replaced: a plain `pipx upgrade cad` would stay inside it).
    done = box.run([box.cad(), "update", "--major"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip()) != (0, f"cad {AFTER} updated to {HIGH}"):
        raise Failed(f"{box.label}: cad update --major exited {done.returncode}: {done.stdout}{done.stderr}\n"
                     f"{pipx_said(box)}")
    record = updated(box, HIGH)
    pipx_serves(box, env, HIGH)
    pipx_is(box, env, HIGH)
    caught_up(box, HIGH)
    if (record.get("major"), record.get("installer")) != (True, "pipx"):
        raise Failed(f"{box.label}: the update across majors: {record}")
    say(f"        `cad update --major`: {AFTER} -> {HIGH} (`pipx upgrade cad --pip-args=cad>={AFTER}`); the new server "
        "ran `cad plugin install`")
    # Afterwards, automatic updates on: inside the new major, never two majors up.
    switched = box.run([box.cad(), "update", "auto", "on"]).stdout.strip()
    if switched != "update auto: on":
        raise Failed(f"{box.label}: cad update auto on said {switched!r}")
    box.out(HIGH2)
    box.out(HIGHER)
    box.hour_later()
    updated(box, HIGH2)
    pipx_serves(box, env, HIGH2)
    pipx_is(box, env, HIGH2)
    caught_up(box, HIGH2)
    say(f"        {HIGH2} and {HIGHER} out: {HIGH} -> {HIGH2} by itself (`--pip-args={bounded(HIGH)}`), never {HIGHER}")
    pages(box, HIGH2)


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
    # The helper writes its record after the server it starts answers, so the tool's server serving is no sign
    # the record is there yet: awaited, as every end of the bridge awaits it.
    handed_over(box)
    switches = box.read("settings.json").get("auto_update") or {}
    if switches.get("on") is False:
        raise Failed(f"{box.label}: automatic updates off after the bridge: {switches}")
    kept = [old_state / "releases" / old, old_state / "releases" / NEW]
    if not all(path.is_dir() for path in kept):
        raise Failed(f"{box.label}: a release folder is gone: {[str(path) for path in kept if not path.is_dir()]}")
    left = box.from_folder(old_state / "releases")
    if left:
        raise Failed(f"{box.label}: processes still run from the release folders:\n" + "\n".join(left))
    # The install command ran once (install mode), and the tool's server runs it no more: its switch is on.
    tendings(box, Path(tool["env"]), 2)
    if box.runs() != 1 or (box.read("settings.json").get("plugin") or {}).get("auto_update") is not True:
        raise Failed(f"{box.label}: two tendings after the move the install command ran {box.runs()} times, plugin "
                     f"{box.read('settings.json').get('plugin')}\n{box.said()}")
    say(f"        {old} -> {NEW}: uv's cad in {box.bin}, its server ({status.get('prefix')}), current {current}, "
        f"hand-over done (attempt {record.get('attempts')}), automatic updates on, releases/{old} and releases/{NEW} "
        "kept; the install command ran once, and two tendings later still once")
    pages(box, NEW)


def tendings(box: Box, env: Path, count: int) -> None:
    """The server of the environment ``env`` up through ``count`` of its tendings, as its status says (``up``). A
    start stamps no work, so its first tending is a quiet one: what the bridge does there, it has done by then."""
    box.until(lambda: ((box.ask(rc.interpreter(env), "status") or {}).get("up") or 0) > count * TEND_SECONDS + 5,
              f"the server through {count} tendings")


def handed_over(box: Box) -> dict:
    """The move to the uv tool's server ended (``handover-move.json``), the helper's server started: its record."""
    move = box.until(lambda: (lambda found: found if "ended" in found else None)(box.read("handover-move.json")),
                     "the move to the uv tool's server")
    if move.get("outcome") not in ("current", "installed") or str(move.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the move to the uv tool's server: {move}\n{box.said()}")
    return move


def on_the_tool(box: Box, old: str) -> dict:
    """The end the bridge's own install reaches (``store-only``, ``updater-fallback``): uv's cad at this build, its
    server serving the pages' port with their token; ``current`` and its record naming the tool's environment; no
    shipped launcher, and nothing it set aside, in the bin folder; both release folders kept, nothing running from them.
    The tool."""
    handed_over(box)
    box.tool_serves(NEW)
    tool = box.is_tool(NEW, kept=kept_launchers(box))
    current = box.current()
    entry = json.loads((box.state / "installations" / f"{current}.json").read_text(encoding="utf-8")) if current else {}
    if current != NEW or not rc._within(Path(entry.get("prefix") or "/nowhere"), Path(tool["env"])):
        raise Failed(f"{box.label}: installations/current names {current!r}: {entry}")
    aside = leftovers(box)
    if aside:
        raise Failed(f"{box.label}: what the install set aside is still in {box.bin}: {aside}")
    kept = [box.old_state / "releases" / old, box.old_state / "releases" / NEW]
    if not all(path.is_dir() for path in kept):
        raise Failed(f"{box.label}: a release folder is gone: {[str(path) for path in kept if not path.is_dir()]}")
    left = box.from_folder(box.old_state / "releases")
    if left:
        raise Failed(f"{box.label}: processes still run from the release folders:\n" + "\n".join(left))
    return tool


def kept_launchers(box: Box) -> tuple[str, ...]:
    """The shipped launcher the bridge's own install leaves in uv's bin folder: 0.10's ``cad.cmd`` on Windows, which
    is in uv's way of nothing (Windows finds uv's ``cad.exe`` first) and which nothing renames (a ``cmd.exe`` running
    it would break). Nothing else: 0.11's ``cad.exe`` is set aside, and a leftover one fails the route."""
    return ("cad.cmd",) if WINDOWS and "cad.cmd" in box.launchers else ()


def stays(box: Box) -> str:
    """The route's line about ``kept_launchers``."""
    return "; 0.10's cad.cmd stays, as Windows finds uv's cad.exe first" if kept_launchers(box) else ""


def no_plugin(box: Box) -> dict:
    """A store-only computer's end: the install command never ran, nothing owed, no report, no plugin folder, no
    plugin switch. What it holds."""
    held = {"runs": box.runs(), "handover": box.read("handover.json"), "report": box.read("install-report.json"),
            "plugin folder": (box.state / "plugin").exists(), "plugin": box.read("settings.json").get("plugin")}
    if held != {"runs": 0, "handover": {}, "report": {}, "plugin folder": False, "plugin": None}:
        raise Failed(f"{box.label}: a store-only computer: {held}\n{box.said()}")
    return held


def updater(box: Box, old: str) -> None:
    box.install_old(old)
    box.button(NEW)
    read_feed(box, "versions", "cadgen")
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
    box.out(NEW)
    box.old_hour_later(python)
    box.switched(old, NEW)
    bridged(box, old)


def store_bought(box: Box) -> None:
    """What only our install command's setup leaves, gone: a computer that only ever had a store's copy."""
    (box.old_state / "install-receipt.json").unlink(missing_ok=True)
    shutil.rmtree(box.old_state / "plugin", ignore_errors=True)


def store_only(box: Box, old: str) -> None:
    box.install_old(old)
    store_bought(box)
    box.button(NEW)
    box.switched(old, NEW)
    tool = on_the_tool(box, old)
    no_plugin(box)
    say(f"        {old} -> {NEW}: this build's server installed uv's cad ({tool['env']}) and handed over; the install "
        f"command never ran: nothing owed, no plugin folder, no plugin switch{stays(box)}")
    pages(box, NEW)


def updater_fallback(box: Box, old: str) -> None:
    # An install command that fails and writes no report (one that could not be fetched, say), counted.
    box.env["CAD_ENGINE_UPDATE_INSTALLER"] = (
        f"powershell -NoProfile -Command \"Add-Content -LiteralPath '{box.counted}' -Value ran; exit 1\"" if WINDOWS
        else f"""sh -c 'echo ran >> "$0"; exit 1' '{box.counted}'""")
    box.install_old(old)
    box.button(NEW)
    box.switched(old, NEW)
    tool = on_the_tool(box, old)
    owed = box.read("handover.json")
    if (owed.get("state"), owed.get("attempts"), owed.get("outcome"), owed.get("installed"), box.runs()) != (
            "owed", 1, "no_report", False, 1):
        raise Failed(f"{box.label}: install mode after the bridge's own install: {owed}, ran {box.runs()} times\n"
                     f"{box.said()}")
    say(f"        {old} -> {NEW}: install mode failed (no_report), this build's server installed uv's cad "
        f"({tool['env']}) and handed over; install mode still owed after 1 attempt{stays(box)}")
    pages(box, NEW)


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
    box.out(NEW)
    by_hand(box, old, box.install_command().stdout, "by the install command")


# What the install command sets aside in uv's bin folder and may leave there while it runs (``install.py``:
# ``LEFTOVERS``): on Windows, the typed command's own launcher, which runs on from its new name until it exits.
LEFTOVERS = (".cad.exe.text-to-cad-old", ".cad.cmd.text-to-cad-old", ".cad-launcher.text-to-cad-old",
             ".text-to-cad-trash-*", ".cad.exe.*.*.old")


def leftovers(box: Box) -> list[str]:
    """What the install command set aside in uv's bin folder and is still there."""
    return sorted(path.name for pattern in LEFTOVERS for path in box.bin.glob(pattern))


def typed_on_windows(box: Box, old: str) -> None:
    """The end of ``typed`` on Windows (see the module): what the install command set aside while the typed command
    ran, and could not delete then, goes at its next run, once that command has exited. That run is a person's, so it
    asks cad for a newer one (``cad update``): with the next release not out yet there is none, and cad stays as it
    is."""
    left = leftovers(box)
    said = box.install_command().stdout
    if f"Updating cad {NEW} to the newest release..." not in said or leftovers(box):
        raise Failed(f"{box.label}: the install command run again said:\n{said}\nand left {leftovers(box)} in {box.bin}")
    box.is_tool(NEW)
    say(f"        the install command run again: cad {NEW} is here already and nothing is newer, and what the "
        f"typed update set aside ({', '.join(left) or 'nothing'}) gone")


def typed(box: Box, old: str) -> None:
    box.install_old(old)
    opted_out = old.startswith("0.11.")
    if opted_out:
        # The person turned automatic updates off on the shipped release, with its own command, before the update.
        said = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
        if (box.read_old("settings.json").get("updates") or {}).get("automatic") is not False:
            raise Failed(f"{box.label}: {old}'s `cad update auto off` said {said!r}, and its settings hold "
                         f"{box.read_old('settings.json')}")
    box.out(NEW)
    # On Windows the typed command is the shipped release's cad.exe, running all along: the install command renames it
    # aside, and uv's cad goes in all the same.
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
    if box.old_state != box.state:
        # 0.10.0 on Windows: the typed update's setup took 0.10.0's data over first, so its page token still works.
        missing = [name for name in ("install-receipt.json", "engines/token") if not (box.state / name).is_file()]
        if missing:
            raise Failed(f"{box.label}: not taken over from {box.old_state}: {missing}\n{box.said()}")
        pages(box, NEW)
    # Before the next release is out (``stays_off``): the install command a person runs brings cad up to date.
    if WINDOWS:
        typed_on_windows(box, old)
    if opted_out:
        stays_off(box, old)


def stays_off(box: Box, old: str) -> None:
    """Automatic updates turned off on the shipped release stay off on this build: ``cad update auto`` says so, and the
    next release, out and the feed read after an hour, does not install itself at the server's tending or start."""
    began = time.monotonic()
    said = box.run([box.cad(), "update", "auto"]).stdout.strip().splitlines()
    if said[:1] != ["update auto: off (turned off in an earlier release)"]:
        raise Failed(f"{box.label}: after the update from {old}, `cad update auto` said {said}\n{box.said()}")
    box.out(NEXT)
    box.hour_later()
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == NEXT and
              time.time() - box.read("releases.json").get("checked", 0) < 600, "the server reading the feed")
    tendings(box, Path(box.tool()["env"]), 2)
    box.run([box.cad(), "server", "stop"])
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started or box.version() != f"cad {NEW}" or box.read("auto-update.json"):
        raise Failed(f"{box.label}: {old}'s off after the update: {started!r}, {box.version()}, "
                     f"{box.read('auto-update.json')}\n{box.said()}")
    say(f"        {old}'s `cad update auto off` stands: {said[0]!r}; {NEXT} out and the feed read, the server tended "
        f"and started again as {NEW}, nothing attempted ({time.monotonic() - began:.0f} s)")


def store_typed(box: Box, old: str) -> None:
    box.install_old(old)
    store_bought(box)
    box.out(NEW)
    box.run([box.cad(), "update"], timeout=SECONDS + 300)
    if box.current() != NEW or box.read("handover.json"):
        raise Failed(f"{box.label}: after {old}'s cad update: current {box.current()!r}, "
                     f"{box.read('handover.json')}\n{box.said()}")
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    tool = on_the_tool(box, old)
    no_plugin(box)
    say(f"        {old} -> {NEW} by {old}'s `cad update`, cad alone; `cad server start` started {NEW}, whose server "
        f"installed uv's cad ({tool['env']}) and handed over; the install command never ran{stays(box)}")
    pages(box, NEW)


def by_uv_line(box: Box, old: str, *, ours: bool) -> None:
    """``uv-line`` (``ours``) and ``store-uv-line`` (see the module)."""
    box.install_old(old)
    if not ours:
        store_bought(box)
    box.out(NEW)
    # The shipped launcher is in uv's way, but for 0.10's cad.cmd on Windows, which uv's cad.exe goes in beside.
    collides = any(launcher(path) and path.name != "cad.cmd" for path in box.commands())
    first = box.run(["uv", "tool", "install", "cad"], check=False)
    if (first.returncode == 0) == collides or (collides and "already exists" not in first.stdout + first.stderr):
        raise Failed(f"{box.label}: `uv tool install cad` over {old}'s cad command exited {first.returncode}:\n"
                     f"{first.stdout}\n{first.stderr}")
    if collides:
        box.run(["uv", "tool", "install", "--force", "cad"])
    tool = box.tool()
    if tool is None or tool["version"] != NEW or launcher(box.cad()) or box.version() != f"cad {NEW}":
        raise Failed(f"{box.label}: after the uv line: uv's cad tool {tool}, {box.cad()} says {box.version()!r}")
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    box.tool_serves(NEW)
    box.until(lambda: box.current() == NEW, f"installations/current naming {NEW}")
    left = box.from_folder(box.old_state / "releases")
    if left:
        raise Failed(f"{box.label}: {old}'s server still runs:\n" + "\n".join(left))
    env = Path(tool["env"])
    if not ours:
        tendings(box, env, 2)
        no_plugin(box)
        say(f"        {old} -> {NEW} by the uv line; `cad server start` replaced {old}'s server; two tendings later "
            "the install command never ran, and no plugin switch")
        pages(box, NEW)
        return
    # The tool's server, at its first quiet tending: the switch on, then the install command once, run to the line its
    # last step prints (the tool's ``cad plugin update auto on``, which the install command runs last).
    log = box.state / "install-command.log"
    box.until(lambda: box.runs() == 1 and log.is_file() and "plugin update auto: on" in log.read_text(
        encoding="utf-8", errors="replace"), "the install command run once by the tool's server, to its last step")
    if (box.read("settings.json").get("plugin") or {}).get("auto_update") is not True:
        raise Failed(f"{box.label}: the plugin's switch after the install command: {box.read('settings.json')}")
    box.run([box.cad(), "server", "stop"])
    box.run([box.cad(), "server", "start"])
    tendings(box, env, 2)
    if box.runs() != 1:
        raise Failed(f"{box.label}: the install command ran {box.runs()} times\n{box.said()}")
    say(f"        {old} -> {NEW} by the uv line; `cad server start` replaced {old}'s server; the tool's server turned "
        "the plugin's switch on and ran the install command once; restarted, two tendings later still once")
    pages(box, NEW)


def uv_line(box: Box, old: str) -> None:
    by_uv_line(box, old, ours=True)


def store_uv_line(box: Box, old: str) -> None:
    by_uv_line(box, old, ours=False)


# --- a release that runs the install command for `cad plugin update` -------------------------------------------------


def plugin_update(box: Box) -> None:
    """``plugin-update`` (see the module): ``RUNS_IT``'s own ``cad plugin update``, typed, runs the install command,
    whose hand-over that cad refuses, so the newest release's ``cad plugin install`` does the work."""
    old = RUNS_IT
    box.out(old)
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", f"cad=={old}"], timeout=1500)
    box.is_tool(old)
    # What the route stands on: this release has no `cad plugin install`, and says so as a command line it cannot
    # read, having run nothing, asked for its help (as the install command asks it) or not.
    for asked in (["plugin", "install", "--help"], ["plugin", "install"]):
        refused = box.run([box.cad(), *asked], check=False, timeout=120)
        if refused.returncode != 2 or "invalid choice: 'install'" not in refused.stderr or box.runs() != 0:
            raise Failed(f"{box.label}: {old}'s `cad {' '.join(asked)}` exited {refused.returncode}, the install "
                         f"command ran {box.runs()} times:\n{refused.stdout}\n{refused.stderr}")
    box.out(NEW)  # this tree, the newest release out: what `cad@latest` names
    done = box.run([box.cad(), "plugin", "update"], check=False, timeout=SECONDS + 300)
    said = [f"cad {old} is installed already: it is left as it is, and updates itself.",
            f"cad {old} has no `cad plugin install`: the newest cad's runs instead (uv tool run cad@latest), which uv "
            "downloads once.",
            "Setting up the plugin in each agent app found here:", "plugin update auto: on"]
    lines = done.stdout.splitlines()
    # That cad's refusal was asked for quietly: none of it is shown, only the install command's own line.
    if (done.returncode != 0 or [line for line in said if line not in lines] or "Installing cad with uv" in done.stdout
            or "invalid choice" in done.stdout + done.stderr):
        raise Failed(f"{box.label}: {old}'s `cad plugin update` exited {done.returncode} (to say, each on a line of "
                     f"its own: {said}):\n{done.stdout}\n{done.stderr}\n{box.said()}")
    # cad itself is left as it is, and the install command ran once: nothing it ran came back to it.
    box.is_tool(old)
    switch = box.run([box.cad(), "plugin", "update", "auto"]).stdout.strip()
    held = {"runs": box.runs(), "plugin": (box.read("settings.json").get("plugin") or {}).get("auto_update"),
            "switch": switch, "for": box.read("install-command.json").get("for")}
    if held != {"runs": 1, "plugin": True, "switch": "plugin update auto: on", "for": old}:
        raise Failed(f"{box.label}: after {old}'s `cad plugin update`: {held}\n{box.said()}")
    # No server was started, and nothing of the run is left running.
    box.until(lambda: not box.computer.processes(), "nothing of the computer running", seconds=60)
    if box.ask(rc.interpreter(Path(box.tool()["env"])), "status") is not None:
        raise Failed(f"{box.label}: a server runs after {old}'s `cad plugin update`:\n{box.said()}")
    say(f"        {old}'s `cad plugin update` ran the install command once: cad left at {old}, its `cad plugin "
        f"install` refused (exit 2), so {NEW}'s ran by `uv tool run cad@latest`, then {old}'s own switch went on; "
        f"exit 0, the plugin up to date for {old}, no server started")


SELF = {"self-update": self_update, "self-typed": self_typed, "self-typed-stopped": self_typed_stopped,
        "self-at-start": self_at_start, "self-off": self_off, "self-broken": self_broken,
        "self-uninstallable": self_uninstallable, "self-major": self_major, "self-pipx": self_pipx}
BRIDGE = {"updater": updater, "automatic": automatic, "updater-fallback": updater_fallback, "store-only": store_only,
          "rollback": rollback, "install-command": install_command, "typed": typed, "store-typed": store_typed,
          "uv-line": uv_line, "store-uv-line": store_uv_line}
# Of neither group: the routes that start on ``RUNS_IT``, each on a computer alone as a route of ``SELF`` is.
RELEASED = {"plugin-update": plugin_update}


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
    for version in (NEW, NEXT, AFTER, HIGH, HIGH2, HIGHER):
        rc.publish(base, version, out)
    rc.publish(base, BROKEN, out, replace={"cad_server/engine/daemon.py": BROKEN_DAEMON})
    rc.publish(base, NOCMD, out, commands=False)


def main(argv: list[str] | None = None) -> int:
    routes = {**SELF, **BRIDGE, **RELEASED}
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
        f"{AFTER}, {NOCMD} with no command; {HIGH} and {HIGH2} a major up, {HIGHER} two); the bridge from {args.old}")
    failed = 0
    began_all = time.monotonic()
    try:
        for name in chosen:
            before = rc.Sentinels.here()
            alone = WINDOWS and args.old == "0.10.0" and name in BRIDGE
            feed.reads.clear()
            box = Box(name, feed, wheels, shared, named_state=not alone, pypi=pypi, counted=True)
            say(f"-- {name}: a computer in {box.work}")
            came = f", from {args.old}" if name in BRIDGE else f", from {RUNS_IT}" if name in RELEASED else ""
            began = time.monotonic()
            try:
                box.computer.isolation(say)
                say(f"  CAD_PYPI_URL={box.env['CAD_PYPI_URL']}")
                if not box.env["CAD_PYPI_URL"].startswith("http://127.0.0.1:"):
                    raise Failed("the computer is not isolated: CAD_PYPI_URL")
                if name in BRIDGE:
                    routes[name](box, args.old)
                else:
                    routes[name](box)
                say(f"        the feed: {addresses(box)}")
                say(f"ok      {name}{came} ({time.monotonic() - began:.0f} s)")
            except (rc.Failed, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as failure:
                failed += 1
                say(f"FAILED  {name}{came} ({time.monotonic() - began:.0f} s): {failure}")
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
