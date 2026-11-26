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
they start before the plugin first catches up; nothing else of their timing changes. Where a route needs time to pass
beyond that, it sets back the stamp that time is read from, while nothing writes it: the feed's (an hour,
``an_hour_passes``), and in ``self-stopped-midway`` the last beat of a worker it stopped (twenty minutes). No route
waits for a server to be idle: cad's own update never does. No real agent app is on any PATH.

Every computer has a folder of releases of its own, holding only those that are out (``Box.out``): the install command
installs PyPI's newest, and cad's own update the newest of a major, or the release the feed or PyPI names (``uv tool
upgrade``, which reads that folder as ``uv tool install`` does), so a release not out yet must not be there.
What is out, the feed names (``latest``, and each major's newest as ``lines``) and the stand-in PyPI lists (each
release, its file not yanked). Releases of a higher major (``above``) have a minor and a patch of 9000 and more, past
anything PyPI holds of that major.

The install command counts the runs cad starts of it on every computer (``Box.runs``): the bridge's (install mode,
a shipped release's own setup, a server's one run on a computer our setup reached), and the one the ``cad plugin
update`` of 0.11.12 and 0.11.13 makes. ``cad plugin install``, which this
build's server runs once where cad got newer, installs the plugin with cad's own code and runs no install command: on a
route of cad updating itself the count stays 0, and the run is read from cad's record of it (``caught_up``). The feed
keeps which address each cad read it at (``addresses``): this build's the new one, ``/v1/releases``, a shipped
release's the old, ``/v1/versions``; a route where one read the other's fails, ``self-at-start`` checks this build read
the new one and ``updater`` the shipped release the old.

**cad updating itself** (a computer the install command set up, but where a route says otherwise: cad a uv tool, its
automatic updates on). uv installed cad, and cad's update has the computer's own uv upgrade it where it is (``uv tool
upgrade "cad==<release>"``, by the worker, ``auto_update_helper``), at two moments alone: a person's ask (the viewer's
button, ``POST /api/v1/local/update``; a typed ``cad update``) and the server's next start, where the feed as last read
names a newer release of its major (the start becomes the update). So an update ends, wherever it is checked
(``in_place``), with uv listing the new release as its tool in the same environment, that environment holding its one
``cad-<release>.dist-info``, whole, and nothing left without its ``RECORD``, uv's receipt requiring what it did (no
pin written), ``cad --version`` saying it and, where a server runs, the server answering as it from the environment.

- ``self-at-start``: the next release out and an hour passed: the start goes by the feed as last read (nothing newer)
  and starts the release installed; the server reads the feed and the button offers the next release, nothing begun;
  then the server's next start is the update (``start_updates``): ``cad server start`` says the next release runs (exit
  0), no server of the release before answered the door in between (a copy of its client looking every 50 ms), the
  update automatic; that server serves the viewer and, the plugin's switch on, runs ``cad plugin install`` once.
- ``self-button``: the viewer's button, PyPI out of reach (the stand-in answering 503): 202, the update a person's, the
  server restarted on the next release; then PyPI reachable, the button again, to the release after; an open page's
  port and token reach the last.
- ``self-typed``: automatic updates off, ``cad update`` with nothing newer says so and begins nothing; with the next
  release on PyPI it updates and restarts the server, saying its one step on stderr, and the new server runs ``cad
  plugin install`` once; then with no server running and PyPI out of reach, it updates to the newest of its major uv
  finds and starts no server: nothing of the computer runs after it.
- ``self-waits``: nothing updates in the background: a page asking every 2 s and a command every 3 s, the feed read
  naming the next release, ten tendings, and the same server process, nothing begun, the environment as it was, the
  button offering it; with automatic updates off a start starts the release installed; on again, the next start is the
  update, the page and the commands going on.
- ``self-rollback``: a release whose server cannot start (its ``cad_server/_internal/engine_daemon.py`` raises),
  named by the feed: the start that becomes the update goes back by itself (``failed``, ``start_failed``, ``restored``:
  uv's tool the release before again, serving the pages' port), counted; another start does not try it again; a
  typed ``cad update`` does, and says in one line that the release before runs again; then the release after it
  updates at the next start.
- ``self-uninstallable``: a release uv cannot install (it requires a package no index has): uv fails before it
  touches the environment, so every file there is as it was, cad runs and its server answers again; the cause read from
  uv's words (``no_release``, or ``config_index`` where an index setting of uv's is there, as the computer's folder of
  releases is), the log naming the package.
- ``self-held``: a source file of cad (``cad_server/__init__.py``) held open by another process, as a scanner holds
  one, until uv's first run ended (on Windows uv cannot delete it, and stops; the worker repairs): installed, healthy,
  the route says whether the repair ran; then cad's dist-info left without its ``RECORD``, as an upgrade stopped past
  it leaves it: uv's upgrade fails on it, the worker deletes it and runs ``uv tool upgrade --reinstall``: healthy.
- ``self-called``: the button's update while three callers run uv's bin ``cad`` every 50 ms, rotating ``cad
  --version``, ``cad server status`` and ``cad server start``, as agent apps call it: cad ends healthy. Every call that
  failed overlapped the update (its record's ``at`` to ``ended``); on Windows each also failed fast (``FAST_SECONDS``)
  and never met a cad half replaced (``HALF_REPLACED``); elsewhere they are said.
- ``self-pinned``: a person's own ``uv tool install cad==<release>``: the start, the feed naming the next release,
  starts the release installed and counts the update blocked once (``pinned``); ``cad update`` refuses in one line
  that says how to unpin; the button answers 409 ``pinned``; nothing begins, the receipt as the person wrote it.
- ``self-major``: never across a major: with only a release a major up newer, the start begins nothing and ``cad
  update`` says this is the newest of its major and names the higher one; ``cad update --major`` is refused (exit 2);
  with the next release of this major out too, ``cad update`` takes it, never the higher one, and names it.
- ``self-stopped-midway``: the worker of the update a start began stopped the moment it is seen, before it reaches
  uv: the record left underway, cad as it was; twenty minutes pass with no beat (its last beat set back) and the
  attempt is lost; the next start begins nothing (the schedule waits an hour after a try); a typed ``cad update``
  installs the release, the automatic try before kept as lost.
- ``self-hop``: the shipped ``SHIPPED`` (0.11.17) installed from PyPI as a uv tool, its server running: its own ``cad
  update`` upgrades uv's tool in place into this tree, and this tree's ``cad update`` takes it on, in place.
- ``install-repair``: the install command, the advised repair, over a cad that does not start, whose dist-info has no
  ``RECORD``, with a process running from its environment: it removes the dist-info, on Windows stops that process
  and waits for it, installs cad again with uv: healthy, uv's receipt as it was.

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

``all`` (the default) is every route; ``self`` the thirteen of cad updating itself and of its repair; ``bridge`` the ten from a shipped
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
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import real_computer as rc  # noqa: E402 - beside it

REPO_ROOT = rc.REPO_ROOT
WINDOWS = rc.WINDOWS
OLD = "0.11.11"
# The newer of the two releases whose own `cad plugin update` runs the install command (0.11.12, 0.11.13): what
# ``plugin-update`` starts on.
RUNS_IT = "0.11.13"
# The newest shipped release whose own update upgrades uv's tool in place: what ``self-hop`` starts on.
SHIPPED = "0.11.17"
_BASE = 9000 + os.getpid() % 800
# This tree as releases no index holds: the one installed first, the next, one whose server cannot start by the
# shipped switch (the bridge's ``rollback``), one whose server cannot start by its own command, the one after them,
# and one uv cannot install (it requires a package no index has).
NEW, NEXT, BROKEN, NOSTART, AFTER, UNBUILDABLE = (rc.stamp(_BASE + step) for step in range(6))
MAJOR = int(NEW.split(".", 1)[0])


def above(majors: int, step: int) -> str:
    """This tree as a release ``majors`` major versions above its own: a minor and a patch far from any real one
    (9000 and up), so it is newer than any release PyPI holds of that major (the yanked 1.x of the name's earlier
    owner among them)."""
    return rc.stamp(_BASE + step, version=f"{MAJOR + majors}.9000.0")


# This tree as a release a major up.
HIGH = above(1, 7)
# What `cad update` and `cad doctor` say where a release of a higher major is out (``auto_update.MAJOR_LINE``).
MAJOR_LINE = ("cad {release}, a new major version, is out: the migration guides say what changes "
              "(https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations)")
BROKEN_DAEMON = b"raise SystemExit('cad: this build cannot start its server (a rehearsal of a release that cannot)')\n"
# What the release uv cannot install (``UNBUILDABLE``) requires.
MISSING = "a-package-that-does-not-exist-anywhere==9.9.9"
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
# Asked as no command (``internal``): a rehearsal's look never counts as work, which would keep a server from the quiet
# moment the bridge's hand-over waits for.
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
    release that is out (``released``, set by ``Box.out``) with a file that is not yanked, as PyPI lists them. While
    ``down``, PyPI out of reach: every question answered 503, with nothing."""

    def __init__(self, feed: rc.Feed) -> None:
        self.feed = feed
        self.released: list[str] = []
        self.down = False
        pypi = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                found = self.path.split("?", 1)[0].rstrip("/") == "/pypi/cad/json" and not pypi.down
                releases = {version: [{"filename": f"cad-{version}-py3-none-any.whl", "packagetype": "bdist_wheel",
                                       "yanked": False, "yanked_reason": None}] for version in pypi.released}
                body = json.dumps({"info": {"version": pypi.feed.latest},
                                   "releases": releases}).encode() if found else b""
                self.send_response(200 if found else 503 if pypi.down else 404)
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
        self.named()

    def taken_back(self, version: str) -> None:
        """``version`` out no more: the feed and PyPI stop naming it (its wheels stay where uv finds them, as a release
        taken back stays downloadable)."""
        self.released.remove(version)
        self.named()

    def named(self) -> None:
        """What the feed and PyPI name: the releases out (``out``)."""
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

    def fetch(self, path: str, method: str = "GET", *, body: bytes | None = None, headers: dict | None = None
              ) -> tuple[int | None, bytes]:
        """``path`` asked of the computer's port with the page token: its status and body; None where none answers."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers={"Authorization": f"Bearer {self.token}",
                                                                 **(headers or {})})
            response = connection.getresponse()
            return response.status, response.read()
        except (OSError, http.client.HTTPException):
            return None, b""
        finally:
            connection.close()

    def http(self, method: str, path: str, *, body: bytes | None = None, headers: dict | None = None
             ) -> tuple[int | None, dict]:
        status, data = self.fetch(path, method, body=body, headers=headers)
        if status is None:
            return None, {}
        try:
            return status, json.loads(data or b"{}")
        except ValueError:
            return status, {"body": data[:200].decode("utf-8", "replace")}

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
        if (self.state / "auto-update.log").is_file():  # the worker's log of cad's own update: each command it ran
            parts.append("  auto-update.log:\n"
                         + (self.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")[-3000:])
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

    def hour_later(self) -> str:
        """The uv tool's server, as an hour passes while it runs: stopped by its own command (which returns once its
        lock is free: it writes nothing after), the feed's stamp set back, and started again: it reads the feed at its
        first tending. That start goes by the feed as last read, and is the update where that names a newer release.
        What the start said."""
        self.run([self.cad(), "server", "stop"])
        self.an_hour_passes()
        started = self.run([self.cad(), "server", "start"]).stdout.strip()
        if "started" not in started:
            raise Failed(f"{self.label}: cad server start said {started!r}")
        return started

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
        # The feed read at its first tending, naming nothing newer: a release the route puts out next is the
        # automatic update's only once an hour passes (``hour_later``).
        self.until(lambda: (self.read("releases.json").get("feed") or {}).get("latest") == NEW,
                   "the server reading the feed at its first tending")

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
        """The uv tool's server answering as ``version``, from the tool's environment, whatever uv lists there (after
        an update through the store, the release uv installed): its status."""
        tool = self.tool()
        if tool is None:
            raise Failed(f"{self.label}: uv lists no cad tool\n{self.said()}")
        status = serves(self, Path(tool["env"]), version)
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

# What the server's environment holds of the update's book, asked of the release that runs: why the last attempt did
# not install what it was for (``auto_update.cause``: ``lost`` once its worker has been silent too long).
CAUSE = "from cad_server._internal import auto_update as a\nprint(a.cause(a.last() or {}) or '')"
# How long an attempt's worker may be silent before the attempt is taken for lost (``auto_update.LOST_SECONDS``),
# and a minute more: how far ``self-stopped-midway`` sets the last beat of a worker it stopped back.
LOST_SECONDS = 21 * 60.0
# What ``cad server start`` says (``cad.engine.client.start``): where it started a server of the release it is, and
# where it stood by while cad's own update switched releases and the server that answered is the next release's -- a
# start that became the update.
STARTED = "started the cad server (cad {release})"
UPDATED = "started the cad server (cad {release}): cad updated itself from {was} as the server started"
# The words a command that failed must never say on Windows, where the switch stops what runs from the environment
# before uv touches it (``self-called``): a cad half replaced under a running command.
HALF_REPLACED = ("ModuleNotFoundError", "ImportError", "No module named", "Traceback")
# How long a call that failed in the switch may have taken on Windows (``self-called``): stopped, refused or told
# the server is the next release's at once, never left waiting.
FAST_SECONDS = 20.0


def updated(box: Box, target: str, outcome: str = "installed", *, after: float | None = None) -> dict:
    """cad's own update to ``target`` ended (its record, ``auto-update.json``) with ``outcome``: the record. ``after``:
    an attempt begun after that time (``at``) alone."""
    record = box.until(lambda: (lambda found: found if found.get("release") == target and "ended" in found and (
        after is None or found.get("at", 0) > after) else None)(box.read("auto-update.json")),
        f"cad's own update to {target} ended")
    if record.get("outcome") != outcome:
        raise Failed(f"{box.label}: cad's own update to {target}: {record}\n{box.said()}")
    return record


def never_installed(box: Box, record: dict, why: str) -> None:
    """No ``cad plugin install`` ran after the update, and cad began none (``why``: the route's reason): the worker's
    record names none and the plugin's record names no run; nor did an install command (the computer counted none)."""
    began = box.read("install-command.json").get("release")
    if record.get("then_install") or "install_command" in record or began or box.runs() != 0:
        raise Failed(f"{box.label}: `cad plugin install` ran after the update ({why}): {record}, began for {began}, "
                     f"the install command ran {box.runs()} times\n{box.said()}")


def caught_up(box: Box, release: str) -> dict:
    """The server of ``release``, newer than the release the plugin is up to date for, ran ``cad plugin install`` once
    (``install-command.json``: its run for ``release`` ended 0, at the first try, and the plugin now up to date for
    ``release``), its output in ``install-command.log``; that command installed the plugin with cad's own code, so no
    install command ran (the computer counted none), and the worker's record names none; the update counted once by
    that server (its record marked ``reported``). The record."""
    record = box.until(lambda: (lambda found: found if found.get("release") == release and found.get("outcome") in
                                ("ok", "failed") else None)(box.read("install-command.json")),
                       f"the run of `cad plugin install` for {release}")
    log = box.state / "install-command.log"
    helper = box.read("auto-update.json")
    if (record.get("outcome"), record.get("code"), record.get("for"), record.get("tries")) != ("ok", 0, release, 1) \
            or box.runs() != 0 or not log.is_file() or "then_install" in helper or "install_command" in helper:
        raise Failed(f"{box.label}: `cad plugin install` after cad got newer: {record}, the install command ran "
                     f"{box.runs()} times (not 0), log {log.is_file()}, the worker's record {helper}\n{box.said()}")
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


def files(env: Path) -> dict[str, tuple[int, int]]:
    """Every file and link of the environment ``env`` by its path there, with its size and modification time; never
    Python's bytecode caches (``__pycache__``), which Python writes itself as a module is first imported from there."""
    found: dict[str, tuple[int, int]] = {}
    for folder, folders, names in os.walk(env):
        folders[:] = [name for name in folders if name != "__pycache__"]
        for name in names:
            path = Path(folder) / name
            try:
                stat = path.lstat()
            except OSError:
                continue
            found[path.relative_to(env).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return found


class Tool:
    """uv's tool ``cad`` as it was when taken: its release, its environment, what uv's receipt there requires (an
    update in place leaves it as it is, never a pin: ``same_receipt``; uv itself adds the person's own settings to its
    options, here the folder of releases, ``UV_FIND_LINKS``) and every file of the environment by size and time (a
    failed update that never reached the environment changes none: ``changed``)."""

    def __init__(self, box: Box) -> None:
        tool = box.tool()
        if tool is None:
            raise Failed(f"{box.label}: uv lists no cad tool\n{box.said()}")
        self.box, self.release, self.env = box, tool["version"], Path(tool["env"])
        self.receipt = self.requires()
        self.files = files(self.env)

    def requires(self) -> object:
        try:
            return tomllib.loads((self.env / "uv-receipt.toml").read_text(encoding="utf-8"))["tool"]["requirements"]
        except (OSError, ValueError, KeyError) as error:
            return f"(no receipt read: {error})"

    def same_receipt(self) -> list[str]:
        now = self.requires()
        return [] if now == self.receipt else [f"uv's receipt requires {now}, not {self.receipt} as before"]

    def changed(self) -> list[str]:
        """What changed in the environment since it was taken: a file changed, added or gone."""
        now = files(self.env)
        found = [f"{path}: {self.files[path]} -> {now.get(path)}" for path in self.files
                 if now.get(path) != self.files[path]]
        return found + [f"{path}: added" for path in now if path not in self.files]


def serves(box: Box, env: Path, version: str) -> dict:
    """The server answering as ``version``, run from the environment ``env`` (its ``prefix``): its status."""
    def found():
        status = box.ask(rc.interpreter(env), "status")
        return status if status and status.get("version") == version and rc._within(
            Path(status.get("prefix") or "/nowhere"), env) else None
    return box.until(found, f"the server of {env} answering as {version}")


def dist_infos(env: Path) -> list[str]:
    """The ``cad-<release>.dist-info`` folders of the environment ``env``."""
    return sorted(path.name for pattern in ("lib/python*/site-packages/cad-*.dist-info",
                                            "Lib/site-packages/cad-*.dist-info") for path in env.glob(pattern))


def unrecorded(env: Path) -> list[str]:
    """The ``*.dist-info`` folders of ``env`` without their ``RECORD``: what an upgrade stopped midway leaves."""
    return sorted(path.name for pattern in ("lib/python*/site-packages/*.dist-info", "Lib/site-packages/*.dist-info")
                  for path in env.glob(pattern) if path.is_dir() and not (path / "RECORD").is_file())


def site_packages(env: Path) -> Path:
    return next(path for pattern in ("lib/python*/site-packages", "Lib/site-packages") for path in env.glob(pattern))


def read_json(path: Path) -> dict:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def in_place(box: Box, before: Tool, release: str, *, server: bool = True) -> None:
    """cad at ``release``, upgraded in place by uv, as the update leaves it: uv lists ``release`` as its tool, in the
    same environment; the environment holds that one ``cad-<release>.dist-info``, whole, and nothing without its
    ``RECORD``; uv's receipt as it was (no pin written); ``cad --version`` from uv's bin folder says ``release``; and,
    with ``server``, the server answers as ``release`` from the environment."""
    tool = box.tool() or {}
    problems = []
    if (tool.get("version"), os.path.realpath(tool.get("env") or "/nowhere")) != (release, os.path.realpath(before.env)):
        problems.append(f"uv's tool is {tool}")
    if dist_infos(before.env) != [f"cad-{release}.dist-info"] or unrecorded(before.env):
        problems.append(f"the environment holds {dist_infos(before.env)}, without their RECORD {unrecorded(before.env)}")
    if box.version() != f"cad {release}":
        problems.append(f"cad --version says {box.version()!r}")
    problems += before.same_receipt()
    if problems:
        raise Failed(f"{box.label}: cad upgraded in place to {release}:\n  " + "\n  ".join(problems) + f"\n{box.said()}")
    if server:
        serves(box, before.env, release)


def viewer(box: Box, release: str) -> str:
    """The viewer served by the server of ``release``: ``GET /api/v1/server`` names ``release``; and where this run's
    wheels carry the built viewer (cad's wheel of ``release`` holds ``cad_server/_runtime/viewer/index.html``), ``GET
    /`` answers 200 with that page and its module script 200. The route's line."""
    box.until(lambda: box.serving(release), f"{release}'s server answering GET /api/v1/server with the page token",
              seconds=90)
    wheel = next(box.wheels.glob(f"cad-{release}-*.whl"), None)
    try:
        with zipfile.ZipFile(wheel) as archive:
            page = archive.read("cad_server/_runtime/viewer/index.html").decode("utf-8")
    except (TypeError, OSError, KeyError, zipfile.BadZipFile):
        return (f"`GET /api/v1/server` answered by {release}; the page itself not asked: this run's wheels carry no "
                "built viewer (built from the source: pass --wheels)")
    script = re.search(r'<script type="module"[^>]*src="\.?/?([^"]+)"', page)
    if script is None:
        raise Failed(f"{box.label}: the built viewer in {wheel.name} names no module script")
    status, body = box.fetch("/")
    asset, _ = box.fetch(f"/{script[1]}")
    if status != 200 or script[1] not in body.decode("utf-8", "replace") or asset != 200:
        raise Failed(f"{box.label}: the viewer of {release}: GET / answered {status} {body[:200]!r}, "
                     f"GET /{script[1]} {asset}\n{box.said()}")
    return f"GET / served {release}'s viewer ({script[1]}, 200)"


def pages(box: Box, version: str) -> None:
    """A page that was open before the update still reaches a server: the pages' port, with their token, answered by
    ``version``'s (the last check of a route: what came before is said already)."""
    box.until(lambda: box.serving(version), f"{version}'s server answering the pages' port {box.port} with their "
              "token, as before the update", seconds=90)
    say(f"        an open page's port and token reach {version}'s server")


def typed_update(box: Box, was: str, target: str, *, server: bool | None = True, also: tuple[str, ...] = (),
                 named: str | None = None) -> dict:
    """``cad update`` typed, which updates ``was`` to ``target``: it says the one step on stderr as it sees it begin
    (``cad: updating cad <was> to <named>``, ``named`` ``cad <target>`` by default, ``the newest release`` where PyPI
    named none; with ``server``, a server running, ``, then restarting the cad server``; None: either), and ``cad <was>
    updated to <target>`` (then ``also``) on stdout, exit 0. The step may go unsaid where the update was over before
    the command looked. The record, ``installed`` and typed."""
    began = time.time()
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    step = f"cad: updating cad {was} to {named or f'cad {target}'}"
    steps = ([[f"{step}, then restarting the cad server"]] if server in (True, None) else []) \
        + ([[step]] if server in (False, None) else [])
    said = done.stderr.strip().splitlines()
    if (done.returncode, done.stdout.strip().splitlines()) != (0, [f"cad {was} updated to {target}", *also]) \
            or said not in (*steps, []):
        raise Failed(f"{box.label}: cad update exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n{box.said()}")
    record = updated(box, target, after=began - 1)
    if (record.get("asked"), record.get("from")) != (True, was):
        raise Failed(f"{box.label}: the record of a typed update: {record}")
    return record


def feed_read(box: Box, latest: str, lines: dict | None = None) -> None:
    """The feed as the server last read it naming ``latest`` (``lines``: each major's newest; by default ``latest``
    for its own), read now (within the hour: nothing reads it again soon), in the file the server keeps it in; only
    while no server runs, which writes that file itself."""
    (box.state / "releases.json").write_text(json.dumps({"checked": time.time(), "feed": {
        "latest": latest, "lines": lines or {latest.split(".", 1)[0]: latest}}}), encoding="utf-8")


def reads_the_feed(box: Box, latest: str) -> None:
    """The server running read the feed, naming ``latest``, within the last ten minutes."""
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == latest and
              time.time() - box.read("releases.json").get("checked", 0) < 600, f"the server reading the feed ({latest})")


def button(box: Box) -> tuple[int | None, dict]:
    """What the viewer's update button shows (``GET /api/v1/server``'s ``cadUpdate``), and the status."""
    status, answer = box.http("GET", "/api/v1/server")
    return status, answer.get("cadUpdate") or {}


def click(box: Box) -> tuple[int | None, dict]:
    """The viewer's update button clicked: ``POST /api/v1/local/update`` ``{}``, as a page posts it."""
    return box.http("POST", "/api/v1/local/update", body=b"{}",
                    headers={"x-cad-viewer": "1", "Content-Type": "application/json"})


def nothing_begun(box: Box, why: str, *, at: object = None) -> None:
    """No update began (``why``): the record is as it was (``at``: the attempt it named, None for none)."""
    found = box.read("auto-update.json")
    if found.get("at") != at:
        raise Failed(f"{box.label}: an update began ({why}): {found}\n{box.said()}")


# Which release's server answers the computer's door, asked every 50 ms by a copy of the client of the release that
# runs (outside its environment, which the switch may stop on Windows and uv replaces), until the input ends
# (``Watch``): a first line once it looks, then a line for each look, the release or null.
WATCH = """import json, os, sys, threading, time
sys.path.insert(0, sys.argv[1])
from cad.engine import client
def end():
    sys.stdin.read()
    os._exit(0)
threading.Thread(target=end, daemon=True).start()
print("watching", flush=True)
while True:
    try:
        found = client._connect()
    except Exception:
        found = None
    print(json.dumps(found.release if found is not None else None), flush=True)
    if found is not None:
        found.close()
    time.sleep(0.05)
"""


class Watch:
    """The servers that answer the computer's door while a step runs, as a copy of the client of the environment
    ``env`` sees them every 50 ms (``WATCH``): ``stop`` ends the look and says each release that answered, in order."""

    def __init__(self, box: Box, env: Path) -> None:
        self.seen: list[str] = []
        self.looks = 0
        copy = box.work / "watch"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(site_packages(env) / "cad", copy / "cad", ignore=shutil.ignore_patterns("__pycache__"))
        self.process = subprocess.Popen([sys.executable, "-I", "-c", WATCH, str(copy)], env=box.env, cwd=box.work,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        if self.process.stdout.readline().strip() != "watching":
            raise Failed(f"{box.label}: the watch on the door did not start: exit {self.process.poll()}")
        self.reading = threading.Thread(target=self.read, daemon=True)
        self.reading.start()

    def read(self) -> None:
        for line in self.process.stdout:
            self.looks += 1
            try:
                found = json.loads(line)
            except ValueError:
                continue
            if found and (not self.seen or self.seen[-1] != found):
                self.seen.append(found)

    def saw(self, release: str) -> bool:
        return release in list(self.seen)

    def stop(self) -> list[str]:
        self.process.stdin.close()
        self.process.wait(60)
        self.reading.join(60)
        return list(self.seen)


def start_updates(box: Box, before: Tool, was: str, target: str) -> tuple[dict, str]:
    """The server's next start, with the feed as last read naming ``target`` newer than ``was``: stopped by its own
    command, then ``cad server start``, which becomes the update -- the server of ``was`` it starts begins it and
    serves nothing, the worker upgrades cad in place and starts ``target``'s, and the command returns once that one
    answers, saying it runs (``UPDATED``), exit 0. No server of ``was`` answered the door from the stop until
    ``target``'s did, as a client looking every 50 ms sees it (``Watch``). The update is automatic (not typed). The
    record, and the route's line."""
    box.run([box.cad(), "server", "stop"])
    watch = Watch(box, before.env)
    try:
        began = time.time()
        done = box.run([box.cad(), "server", "start"], check=False)
        took = time.time() - began
        record = updated(box, target, after=began - 1)
        box.until(lambda: watch.saw(target), f"the watch on the door seeing {target}'s server", seconds=60)
    finally:
        seen = watch.stop()
    said = UPDATED.format(release=target, was=was)
    if (done.returncode, done.stdout.strip()) != (0, said) or seen != [target]:
        raise Failed(f"{box.label}: cad server start with {target} named exited {done.returncode} in {took:.1f} s:\n"
                     f"{done.stdout}\n{done.stderr}\nthe door answered as {seen} ({watch.looks} looks)\n{box.said()}")
    if (record.get("asked"), record.get("from")) != (False, was) or "restored" in record:
        raise Failed(f"{box.label}: the update a start began: {record}\n{box.said()}")
    in_place(box, before, target)
    return record, (f"`cad server start`: {said!r} in {took:.1f} s (exit 0); no server of {was} answered the door "
                    f"from the stop until {target}'s did, {watch.looks} looks")


def self_at_start(box: Box) -> None:
    """The server's next start is the update, where the feed as last read names a newer release; the new server
    serves the viewer and runs ``cad plugin install`` once."""
    box.set_up("on")
    before = Tool(box)
    box.out(NEXT)
    # An hour passes: the start goes by the feed as last read, naming nothing newer, and starts the release installed;
    # then the server reads the feed, and the button offers the next release. Nothing updates meanwhile.
    started = box.hour_later()
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start, the feed as last read naming nothing newer, said {started!r}")
    reads_the_feed(box, NEXT)
    read_feed(box, "releases", "cad")
    status, shown = button(box)
    if (status, shown.get("latest"), shown.get("state")) != (200, NEXT, "idle"):
        raise Failed(f"{box.label}: the update button with {NEXT} named: {status} {shown}")
    nothing_begun(box, "the server read the feed")
    say(f"        {NEXT} out, an hour passed: `cad server start` started {NEW} ({started!r}); the server read the feed, "
        f"the button offers {NEXT}, nothing begun")
    record, line = start_updates(box, before, NEW, NEXT)
    say(f"        then {line}; {NEW} -> {NEXT} in place: uv lists {NEXT}, its receipt as it was")
    caught_up(box, NEXT)
    say(f"        {viewer(box, NEXT)}; the new server ran `cad plugin install`, once, exit 0 (tries {record['tries']})")
    pages(box, NEXT)


def clicked(box: Box, was: str, target: str) -> dict:
    """The viewer's button clicked, updating ``was`` to ``target``: 202, the update a person's; the record."""
    began = time.time()
    status, answer = click(box)
    if status != 202:
        raise Failed(f"{box.label}: the update button answered {status}: {answer}\n{box.said()}")
    record = updated(box, target, after=began - 1)
    if (record.get("asked"), record.get("from")) != (True, was) or "restored" in record \
            or str(record.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the update the button began: {record}\n{box.said()}")
    return record


def self_button(box: Box) -> None:
    """The viewer's button updates cad and restarts its server, PyPI reachable or not."""
    box.set_up("off")
    before = Tool(box)
    first = box.ask(rc.interpreter(before.env), "status") or {}
    box.out(NEXT)
    # PyPI out of reach (the stand-in answering 503): the update takes the newest release of its major uv finds.
    box.pypi.down = True
    try:
        record = clicked(box, NEW, NEXT)
    finally:
        box.pypi.down = False
    in_place(box, before, NEXT)
    now = box.ask(rc.interpreter(before.env), "status") or {}
    if now.get("pid") == first.get("pid"):
        raise Failed(f"{box.label}: the server was not restarted: {first}, {now}")
    say(f"        PyPI out of reach: the button's `POST /api/v1/local/update` {{}}: 202; {NEW} -> {NEXT} in place "
        f"({record['detail']!r}), the server restarted on it")
    pages(box, NEXT)
    box.out(AFTER)
    clicked(box, NEXT, AFTER)
    in_place(box, before, AFTER)
    say(f"        PyPI reachable: the button again, {NEXT} -> {AFTER} in place")
    say(f"        {viewer(box, AFTER)}")
    pages(box, AFTER)


def self_typed(box: Box) -> None:
    """``cad update`` typed, with automatic updates off: with nothing newer it says so; with a server running it
    updates in place and restarts it, and the new server catches the plugin up; with none running, PyPI out of reach,
    it updates in place and starts none."""
    box.set_up("on")
    before = Tool(box)
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip()) != (0, f"cad {NEW} is the newest release") or box.read("auto-update.json"):
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: {done.stdout}{done.stderr}, "
                     f"{box.read('auto-update.json')}")
    box.out(NEXT)  # out on PyPI; the feed's hour has not passed for the server
    typed_update(box, NEW, NEXT)
    in_place(box, before, NEXT)
    caught_up(box, NEXT)
    say(f"        `cad update` with nothing newer: 'cad {NEW} is the newest release'; then {NEW} -> {NEXT} in place, "
        "automatic updates off, the step said once on stderr, the server restarted; the new server ran `cad plugin "
        "install`, once, exit 0")
    # No server running, PyPI out of reach: the command begins the update itself, and its worker starts no server.
    python = rc.interpreter(before.env)
    box.run([box.cad(), "server", "stop"])
    box.until(lambda: box.ask(python, "status") is None, "no server running")
    box.out(AFTER)
    box.pypi.down = True
    try:
        began = time.monotonic()
        record = typed_update(box, NEXT, AFTER, server=False, named="the newest release")
        took = time.monotonic() - began
    finally:
        box.pypi.down = False
    if record.get("start") is not False or "started" in record:
        raise Failed(f"{box.label}: the worker was to start no server: {record}")
    in_place(box, before, AFTER, server=False)
    box.until(lambda: not box.computer.processes(), "nothing of the computer running", seconds=60)
    if box.ask(python, "status") is not None or (box.read("settings.json").get("auto_update") or {}).get("on") \
            is not False:
        raise Failed(f"{box.label}: after a typed update with no server: {box.said()}")
    say(f"        no server, PyPI out of reach: {NEXT} -> {AFTER} by a typed `cad update` in {took:.0f} s, in place; "
        f"no server after it, nothing of the computer running (looked: {box.computer.looked}), automatic updates off")


class Page:
    """A viewer page open on the computer's port, and shown: it asks ``GET /api/v1/server`` every ``every`` seconds
    until ``stop``. ``seen``: the release each question was answered by, None where none answered."""

    def __init__(self, box: Box, every: float = 2.0) -> None:
        self.box, self.every, self.done = box, every, threading.Event()
        self.seen: list[str | None] = []
        self.thread = threading.Thread(target=self.look, daemon=True)
        self.thread.start()

    def look(self) -> None:
        while True:
            status, answer = self.box.http("GET", "/api/v1/server")
            self.seen.append(answer.get("release") if status == 200 else None)
            if self.done.wait(self.every):
                return

    def stop(self) -> list[str | None]:
        self.done.set()
        self.thread.join(60)
        return list(self.seen)


class Commands:
    """An agent at work on the computer: ``cad server status`` run every ``every`` seconds, a command the server counts
    as one (it is no rehearsal's look, ``ASK``), until ``stop``. ``ran``: when each one a server answered ended."""

    def __init__(self, box: Box, every: float = 3.0) -> None:
        self.box, self.every, self.done = box, every, threading.Event()
        self.ran: list[float] = []
        self.thread = threading.Thread(target=self.call, daemon=True)
        self.thread.start()

    def call(self) -> None:
        while True:
            done = self.box.run([self.box.cad(), "server", "status"], check=False, timeout=60)
            if done.returncode == 0:
                self.ran.append(time.time())
            if self.done.wait(self.every):
                return

    def stop(self) -> list[float]:
        self.done.set()
        self.thread.join(90)
        return list(self.ran)


def self_waits(box: Box) -> None:
    """Nothing updates in the background: a server kept busy by a page and an agent, the feed read naming a newer
    release, ten tendings, and nothing begun; with automatic updates off a start starts the release installed; with
    them on, the next start is the update, the page and the agent going on."""
    box.set_up("off")
    before = Tool(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    page, commands = Page(box), Commands(box)
    try:
        box.hour_later()
        reads_the_feed(box, NEXT)
        first = box.ask(python, "status") or {}
        since = first.get("up") or 0
        box.until(lambda: ((box.ask(python, "status") or {}).get("up") or 0) > since + 10 * TEND_SECONDS + 1,
                  "ten tendings more")
        now = box.ask(python, "status") or {}
        status, shown = button(box)
        if now.get("pid") != first.get("pid") or box.tool()["version"] != NEW or before.changed() \
                or (status, shown.get("latest"), shown.get("state")) != (200, NEXT, "idle"):
            raise Failed(f"{box.label}: a busy server with {NEXT} named: {first} -> {now}, uv's tool {box.tool()}, "
                         f"{before.changed()[:5]}, the button {status} {shown}\n{box.said()}")
        nothing_begun(box, "a busy server's tendings")
        say(f"        {NEXT} named by the feed the server read, ten tendings with a page asking every 2 s and a command "
            f"every 3 s ({len(commands.ran)} answered): the same {NEW} server (pid {first.get('pid')}), nothing begun, "
            "the environment as it was, the button offering it")
        # Automatic updates off: a start starts the release installed.
        switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
        if switched != "update auto: off":
            raise Failed(f"{box.label}: cad update auto off said {switched!r}")
        box.run([box.cad(), "server", "stop"])
        started = box.run([box.cad(), "server", "start"]).stdout.strip()
        if started != STARTED.format(release=NEW):
            raise Failed(f"{box.label}: cad server start with automatic updates off said {started!r}\n{box.said()}")
        nothing_begun(box, "automatic updates off")
        say(f"        automatic updates off: `cad server start` said {started!r}, nothing begun")
        # On again: the next start is the update.
        switched = box.run([box.cad(), "update", "auto", "on"]).stdout.strip()
        if switched != "update auto: on":
            raise Failed(f"{box.label}: cad update auto on said {switched!r}")
        _record, line = start_updates(box, before, NEW, NEXT)
    finally:
        seen, ran = page.stop(), commands.stop()
    say(f"        automatic updates on: {line}; the page asked {len(seen)} times, {len(ran)} commands answered")
    pages(box, NEXT)


def self_rollback(box: Box) -> None:
    """A release whose server cannot start: at the start that becomes the update, and typed, cad goes back to the
    release before by itself; it is not tried again by itself; the release after it updates as any does."""
    box.set_up("off")
    before = Tool(box)
    env = before.env
    box.out(NOSTART)
    box.run([box.cad(), "server", "stop"])
    feed_read(box, NOSTART)
    began = time.time()
    done = box.run([box.cad(), "server", "start"], check=False)
    record = updated(box, NOSTART, "failed", after=began - 1)
    if (record.get("cause"), record.get("restored"), record.get("asked")) != ("start_failed", True, False) \
            or str(record.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the way back from {NOSTART} at a start: {record}\n{box.said()}")
    in_place(box, before, NEW)
    box.until(lambda: box.serving(NEW), f"{NEW} serving again on the pages' port with their token")
    box.until(lambda: box.read("auto-update.json").get("reported") is True, "the failed update counted")
    said = (done.stdout.strip() or done.stderr.strip()).splitlines()[-1:]
    say(f"        {NOSTART}, whose server cannot start, named by the feed: `cad server start` (exit {done.returncode}: "
        f"{said}) became the update; cause start_failed, restored: uv lists {NEW} again and its server serves the "
        "pages' port; counted")
    # Not tried again by itself: another start, the feed still naming it.
    box.run([box.cad(), "server", "stop"])
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start after the way back said {started!r}\n{box.said()}")
    nothing_begun(box, f"{NOSTART} held back", at=record["at"])
    say(f"        another start, the feed still naming {NOSTART}: {started!r}, not tried again by itself")
    # Typed: tried again, and back again, said in one line.
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    typed = updated(box, NOSTART, "failed", after=record["at"])
    line = done.stderr.strip().splitlines()[-1:]
    if done.returncode == 0 or not line or not line[0].startswith(
            f"cad update: could not update cad {NEW} to {NOSTART}, as the new release did not start") \
            or f"so the release before runs again (cad {NEW})" not in line[0] \
            or (typed.get("cause"), typed.get("restored")) != ("start_failed", True):
        raise Failed(f"{box.label}: cad update to {NOSTART} exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n"
                     f"{typed}\n{box.said()}")
    in_place(box, before, NEW)
    serves(box, env, NEW)
    say(f"        `cad update` to it: {line[0]!r} (exit {done.returncode}); {NEW} runs again")
    # The release after it, at the next start.
    box.out(AFTER)
    box.run([box.cad(), "server", "stop"])
    feed_read(box, AFTER)
    _record, line = start_updates(box, before, NEW, AFTER)
    say(f"        then {AFTER} named: {line}")
    pages(box, AFTER)


def self_uninstallable(box: Box) -> None:
    """A release uv cannot install (it requires a package no index has): uv fails before it touches the environment,
    so cad is as it was and runs; the cause read from uv's words; the log names the package."""
    box.set_up("off")
    before = Tool(box)
    box.out(UNBUILDABLE)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    record = updated(box, UNBUILDABLE, "failed")
    line = done.stderr.strip().splitlines()[-1:]
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")
    if done.returncode == 0 or not line \
            or not line[0].startswith(f"cad update: could not update cad {NEW} to {UNBUILDABLE}, as "):
        raise Failed(f"{box.label}: cad update to {UNBUILDABLE} exited {done.returncode}:\n{done.stdout}\n{done.stderr}")
    if record.get("cause") not in ("no_release", "config_index") or record.get("restored") is not True \
            or MISSING.split("==")[0] not in log:
        raise Failed(f"{box.label}: the update to {UNBUILDABLE}: {record}; its log:\n{log[-3000:]}\n{box.said()}")
    changed = before.changed()
    if changed:
        raise Failed(f"{box.label}: a release uv could not install changed the environment:\n  "
                     + "\n  ".join(changed[:20]))
    in_place(box, before, NEW)
    say(f"        {UNBUILDABLE}, which requires {MISSING}: not installed (cause {record['cause']}: {line[0]!r}); "
        f"every file of the environment as it was, uv lists {NEW}, its server answers again")
    pages(box, NEW)


# A child Python that opens the files it is given and keeps them open (on Windows a file a process holds open cannot be
# deleted, as a scanner holds one) until the worker's log says its first uv run ended, or the attempt did
# (``self-held``); then it lets go.
HOLD = """import sys, time
log, paths = sys.argv[1], sys.argv[2:]
held = [open(path, 'rb') for path in paths]
print('held', flush=True)
def ended():
    try:
        lines = open(log, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return False
    ran = [index for index, line in enumerate(lines) if line.startswith('$ ') and ' tool upgrade ' in line]
    return any(line.startswith('ended ') for line in lines) or bool(ran) and any(
        line.startswith(('  exit', '  did not run')) for line in lines[ran[0] + 1:])
while not ended():
    time.sleep(0.01)
for handle in held:
    handle.close()
print('let go', flush=True)
sys.stdin.read()
"""


def self_held(box: Box) -> None:
    """A source file of cad held open by another process as uv upgrades it (Windows: uv cannot delete it, and stops),
    let go once uv's first run ended; then the repair of an environment an upgrade stopped midway left with a
    dist-info without its RECORD. cad ends healthy each time."""
    box.set_up("off")
    before = Tool(box)
    held = site_packages(before.env) / "cad_server" / "__init__.py"
    holder = subprocess.Popen([sys.executable, "-I", "-c", HOLD, str(box.state / "auto-update.log"), str(held)],
                              env=box.env, cwd=box.work, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        if holder.stdout.readline().strip() != "held":
            raise Failed(f"{box.label}: the file could not be held: exit {holder.poll()}")
        box.out(NEXT)
        typed_update(box, NEW, NEXT)
        if holder.stdout.readline().strip() != "let go":
            raise Failed(f"{box.label}: the holder ended before uv's first run did: exit {holder.poll()}")
    finally:
        holder.stdin.close()
        holder.wait(60)
    in_place(box, before, NEXT)
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")
    repaired = "--reinstall" in log
    say(f"        {NEW} -> {NEXT} with {held.relative_to(before.env).as_posix()} held open until uv's first run ended: "
        f"installed, healthy ({'repaired: `uv tool upgrade --reinstall` ran' if repaired else 'uv was not stopped by it'})")
    # The repair: cad's dist-info left without its RECORD, as an upgrade stopped past it leaves it. uv's upgrade then
    # fails on it (it cannot remove that release), and the worker deletes it and installs the release again.
    record_file = site_packages(before.env) / f"cad-{NEXT}.dist-info" / "RECORD"
    record_file.unlink()
    box.out(AFTER)
    record = typed_update(box, NEXT, AFTER)
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")
    if "without its RECORD" not in log or "--reinstall" not in log:
        raise Failed(f"{box.label}: no repair of the dist-info left without its RECORD: {record}\n{log[-3000:]}")
    in_place(box, before, AFTER)
    say(f"        then cad-{NEXT}.dist-info without its RECORD: uv's upgrade to {AFTER} failed on it, the worker removed "
        f"it and ran `uv tool upgrade --reinstall`: {record['detail']!r}; healthy")
    pages(box, AFTER)


class Callers:
    """Agents and apps calling ``cad`` while an update runs (``self-called``): ``count`` threads, each running the bin
    folder's ``cad`` every ``every`` seconds from before the update begins until after it has ended (``stop``), each
    rotating through ``CALLS`` from a place of its own. ``calls``: each call's begin and end (``time.time``), what it
    ran, its exit status (or what stopped it) and all it said on stderr."""

    CALLS = (["--version"], ["server", "status"], ["server", "start"])

    def __init__(self, box: Box, count: int = 3, every: float = 0.05) -> None:
        self.box, self.every, self.done, self.lock = box, every, threading.Event(), threading.Lock()
        self.calls: list[tuple[float, float, str, object, str]] = []
        self.threads = [threading.Thread(target=self.call, args=(first,), daemon=True) for first in range(count)]
        for thread in self.threads:
            thread.start()

    def call(self, at: int) -> None:
        while not self.done.is_set():
            command = self.CALLS[at % len(self.CALLS)]
            at += 1
            began = time.time()
            try:
                done = subprocess.run([str(self.box.cad()), *command], env=self.box.env, cwd=self.box.work,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=120)
                how, said = done.returncode, done.stderr.strip()
            except FileNotFoundError:
                how, said = "not found", ""
            except (OSError, subprocess.TimeoutExpired) as error:
                how, said = type(error).__name__, str(error)
            with self.lock:
                self.calls.append((began, time.time(), " ".join(command), how, said))
            time.sleep(self.every)

    def stop(self) -> list[tuple[float, float, str, object, str]]:
        self.done.set()
        for thread in self.threads:
            thread.join(150)
        return list(self.calls)


def self_called(box: Box) -> None:
    """The switch with three callers running ``cad`` every 50 ms throughout: cad ends healthy. On Windows every call
    that failed fell inside the switch, failed fast and never met a cad half replaced; elsewhere they are said."""
    box.set_up("off")
    before = Tool(box)
    box.out(NEXT)
    callers = Callers(box)
    try:
        box.until(lambda: len(callers.calls) >= 6, "the callers at work")
        record = clicked(box, NEW, NEXT)
        done = len(callers.calls)
        box.until(lambda: len(callers.calls) >= done + 6, "the callers at work after the update")
    finally:
        calls = callers.stop()
    in_place(box, before, NEXT)
    start, end = record["at"], record["ended"]
    failed = [call for call in calls if call[3] != 0]
    said: dict[str, int] = {}
    for call in failed:
        key = f"{call[2]}: exit {call[3]}: {(call[4].splitlines() or [''])[-1][:160]}"
        said[key] = said.get(key, 0) + 1
    tally = f"{len(calls)} calls, {len(failed)} failed" + "".join(f"\n          {count} x {key}"
                                                                   for key, count in sorted(said.items()))
    outside = [call for call in failed if call[1] < start or call[0] > end]
    wrong = outside + ([call for call in failed if call not in outside and (
        call[1] - call[0] > FAST_SECONDS or any(word in call[4] for word in HALF_REPLACED))] if WINDOWS else [])
    during = [call for call in calls if call[1] >= start and call[0] <= end]
    if not during or wrong:
        raise Failed(f"{box.label}: the update while cad was called ({end - start:.1f} s): {tally}; out of place:\n"
                     + "\n".join(f"  {call[0] - start:+.2f} s to {call[1] - start:+.2f} s from its begin: {call[2]}: "
                                 f"{call[3]}: {call[4][-400:]}" for call in wrong) + f"\n{box.said()}")
    say(f"        the button: {NEW} -> {NEXT} in place in {end - start:.1f} s, three callers of `cad` every 50 ms from "
        f"before it to after it: {tally}, {len(during)} of them during the update")
    if failed:
        say("        each failure from " + ", ".join(f"{call[0] - start:+.2f}..{call[1] - start:+.2f} s"
                                                     for call in failed) + " of the update's begin"
            + (" (Windows: within it, fast, no cad half replaced)" if WINDOWS else " (recorded)"))
    say(f"        {viewer(box, NEXT)}")


def self_pinned(box: Box) -> None:
    """A person's own pin (``uv tool install cad==X``): nothing updates it, by itself or asked, and it says why
    (``pinned``)."""
    box.out(NEW)
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", f"cad=={NEW}"], timeout=SECONDS)
    before = Tool(box)
    box.out(NEXT)
    box.run([box.cad(), "server", "stop"], check=False)
    feed_read(box, NEXT)
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    box.token = (box.ask(rc.interpreter(before.env), "http") or {}).get("token", "")
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start, pinned, said {started!r}\n{box.said()}")
    blocked = box.until(lambda: box.read("auto-update-blocked.json") or None, "the blocked update counted")
    if (blocked.get("cause"), blocked.get("wanted")) != ("pinned", NEXT):
        raise Failed(f"{box.label}: the blocked update: {blocked}")
    nothing_begun(box, "pinned, at a start")
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    line = done.stderr.strip().splitlines()[-1:]
    if done.returncode == 0 or not line or "pinned" not in line[0] or "uv tool install --force cad" not in line[0]:
        raise Failed(f"{box.label}: cad update, pinned, exited {done.returncode}:\n{done.stdout}\n{done.stderr}")
    status, answer = click(box)
    if (status, answer.get("cause")) != (409, "pinned"):
        raise Failed(f"{box.label}: the button, pinned, answered {status}: {answer}")
    nothing_begun(box, "pinned, asked")
    in_place(box, before, NEW)
    say(f"        `uv tool install cad=={NEW}`, {NEXT} named: the start started {NEW} (cause pinned, counted once); "
        f"`cad update`: {line[0]!r}; the button 409 pinned; nothing begun, the receipt as the person wrote it")


def self_major(box: Box) -> None:
    """Never across a major: with only a higher major newer, nothing updates, at a start or typed, and the higher one
    is named; with a newer release of this major out too, that one, never the higher; ``--major`` is no option."""
    box.set_up("off")
    before = Tool(box)
    box.out(HIGH)
    box.run([box.cad(), "server", "stop"])
    feed_read(box, HIGH, {str(MAJOR): NEW, str(MAJOR + 1): HIGH})
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start, {HIGH} out, said {started!r}\n{box.said()}")
    nothing_begun(box, "a higher major out, at a start")
    higher = MAJOR_LINE.format(release=HIGH)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip().splitlines()) != (0, [f"cad {NEW} is the newest {MAJOR}.x release", higher]):
        raise Failed(f"{box.label}: cad update, {HIGH} out, exited {done.returncode}: {done.stdout}{done.stderr}")
    nothing_begun(box, "a higher major out, typed")
    say(f"        {HIGH} out: the start started {NEW}; `cad update`: 'cad {NEW} is the newest {MAJOR}.x release' and "
        f"{HIGH} named; nothing begun")
    done = box.run([box.cad(), "update", "--major"], check=False, timeout=SECONDS + 60)
    if done.returncode != 2 or "unrecognized arguments: --major" not in done.stderr:
        raise Failed(f"{box.label}: cad update --major exited {done.returncode}: {done.stdout}{done.stderr}")
    nothing_begun(box, "--major")
    box.out(NEXT)
    typed_update(box, NEW, NEXT, also=(higher,))
    in_place(box, before, NEXT)
    say(f"        `cad update --major`: refused (exit 2); then {NEXT} out too: `cad update` took {NEXT}, never {HIGH}, "
        "and named it")


def self_stopped_midway(box: Box) -> None:
    """The worker of the update a start began, stopped before it reached uv: the record is left underway, cad as it
    was; once its worker has been silent past the wait it is lost, the next start begins nothing (the schedule waits
    after a try), and a typed ``cad update`` installs the release, the try before kept as lost."""
    box.set_up("off")
    before = Tool(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    box.run([box.cad(), "server", "stop"])
    feed_read(box, NEXT)
    start = subprocess.Popen([str(box.cad()), "server", "start"], env=box.env, cwd=box.work,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # The worker, stopped the moment it is seen: it starts as a Python that imports what it needs before it does
    # anything, so it is stopped before it runs uv (its log, which names each command, says so after).
    deadline, worker = time.monotonic() + 120, None
    try:
        while worker is None:
            if time.monotonic() > deadline:
                raise Failed(f"{box.label}: the update's worker never seen\n{box.said()}")
            for pid, command in box.computer.processes():
                line = (rc.windows_command_line(pid) or "") if WINDOWS else command
                if "-m cad_server._internal.auto_update_helper" in line:
                    end_process(pid)
                    worker = pid
                    break
    finally:
        end_process(start.pid, tree=True)
        start.wait(60)
    box.until(lambda: not any("auto_update_helper" in ((rc.windows_command_line(pid) or "") if WINDOWS else command)
                              for pid, command in box.computer.processes()), "the update's worker gone", seconds=60)
    record = box.read("auto-update.json")
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace") \
        if (box.state / "auto-update.log").is_file() else ""
    if (record.get("outcome"), record.get("release"), record.get("asked")) != ("underway", NEXT, False) \
            or " tool upgrade " in log or before.changed() or box.version() != f"cad {NEW}":
        raise Failed(f"{box.label}: the worker stopped before uv: {record}; its log:\n{log}\n{before.changed()[:5]}\n"
                     f"{box.said()}")
    say(f"        the worker of the update a start began, stopped at once (pid {worker}): the record left underway, "
        f"cad {NEW} as it was")
    # Twenty minutes pass with no beat from it: lost (its last beat set back, as the feed's stamp is for an hour).
    _keep(box.state / "auto-update.json", {**record, "beat": time.time() - LOST_SECONDS})
    cause = box.run([python, "-c", CAUSE], check=False, timeout=60).stdout.strip()
    if cause != "lost":
        raise Failed(f"{box.label}: the stopped attempt, silent past the wait, is taken as {cause!r}, not lost")
    box.run([box.cad(), "server", "stop"], check=False)
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if started != STARTED.format(release=NEW) or box.read("auto-update.json").get("at") != record["at"]:
        raise Failed(f"{box.label}: the start after the lost attempt said {started!r}: {box.read('auto-update.json')}")
    say(f"        silent past the wait: lost; the next start, its try an hour from due: {started!r}, nothing begun")
    typed_update(box, NEW, NEXT, server=None)
    in_place(box, before, NEXT)
    tried = (box.read("tried").get("tried") or {}).get(NEXT) or {}
    if tried.get("cause") != "lost":
        raise Failed(f"{box.label}: the tries of {NEXT}: {tried}")
    say(f"        then a typed `cad update`: {NEW} -> {NEXT} in place, the automatic try before kept as lost")


def end_process(pid: int, *, tree: bool = False) -> None:
    """``pid`` ended at once (on Windows with ``tree``, with what it started), whatever it is doing."""
    try:
        if WINDOWS and tree:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=60)
        else:
            os.kill(pid, signal.SIGTERM if WINDOWS else signal.SIGKILL)  # TerminateProcess on Windows
    except (OSError, subprocess.SubprocessError):
        pass


def _keep(path: Path, record: dict) -> None:
    """``record`` written whole in place of ``path``, as cad writes its records."""
    staged = path.with_name(f".{path.name}.{os.getpid()}")
    staged.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(staged, path)


def self_hop(box: Box) -> None:
    """``SHIPPED``, installed from PyPI as uv's tool, updates itself the way it does (its worker upgrades uv's tool in
    place) into this tree, and from there this tree's update takes over."""
    box.out(SHIPPED)  # out on PyPI, whose own file it is
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", f"cad=={SHIPPED}"], timeout=1500)
    box.is_tool(SHIPPED)
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {SHIPPED}" not in started:
        raise Failed(f"{box.label}: {SHIPPED}'s cad server start said {started!r}")
    box.out(NEW)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 300)
    if done.returncode != 0 or f"cad {SHIPPED} updated to {NEW}" not in done.stdout:
        raise Failed(f"{box.label}: {SHIPPED}'s cad update exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n"
                     f"{box.said()}")
    box.is_tool(NEW)
    before = Tool(box)
    serves(box, before.env, NEW)
    say(f"        {SHIPPED}'s own `cad update` upgraded uv's tool in place to {NEW}, whose server answers")
    box.out(NEXT)
    typed_update(box, NEW, NEXT)
    in_place(box, before, NEXT)
    say(f"        then this tree's `cad update`: {NEW} -> {NEXT} in place")


# A process of cad's environment that runs until its input ends (``install-repair``): an agent's ``cad`` command at
# work, as far as Windows is concerned.
RUNS = "import sys\nprint('running', flush=True)\nsys.stdin.read()\n"


def install_repair(box: Box) -> None:
    """The install command, the advised repair: cad that does not start, its dist-info left without its RECORD, and a
    process running from its environment. It removes the dist-info, (on Windows) stops that process and waits for it,
    and installs cad again with uv: cad healthy."""
    box.set_up("off")
    before = Tool(box)
    box.run([box.cad(), "server", "stop"])
    packages = site_packages(before.env)
    (packages / "cad_server" / "cli" / "__init__.py").unlink()  # `cad` no longer starts
    (packages / f"cad-{NEW}.dist-info" / "RECORD").unlink()
    if box.run([box.cad(), "--version"], check=False).returncode == 0:
        raise Failed(f"{box.label}: cad still starts")
    running = subprocess.Popen([rc.interpreter(before.env), "-c", RUNS], env=box.env, cwd=box.work,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        if running.stdout.readline().strip() != "running":
            raise Failed(f"{box.label}: the process of the environment did not start: exit {running.poll()}")
        said = box.install_command().stdout
        ended = running.poll()
    finally:
        if running.poll() is None:
            running.stdin.close()
        running.wait(60)
    lines = [f"Removed cad-{NEW}.dist-info from cad's environment", "does not start: installing it again with uv"]
    if WINDOWS:
        lines.append("Stopped what ran from cad's environment, so uv can install it again: ")
    missing = [line for line in lines if line not in said]
    if missing or (WINDOWS and ended is None):
        raise Failed(f"{box.label}: the install command over a broken cad (to say {missing}; the process of the "
                     f"environment {'ended' if ended is not None else 'still running'}):\n{said}\n{box.said()}")
    in_place(box, before, NEW, server=False)
    say(f"        cad not starting, cad-{NEW}.dist-info without its RECORD, a process running from its environment: the "
        f"install command removed the dist-info, {'stopped that process, ' if WINDOWS else ''}installed cad again: "
        f"healthy, uv's receipt as it was")


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


SELF = {"self-at-start": self_at_start, "self-button": self_button, "self-typed": self_typed, "self-waits": self_waits,
        "self-rollback": self_rollback, "self-uninstallable": self_uninstallable, "self-held": self_held,
        "self-called": self_called, "self-pinned": self_pinned, "self-major": self_major,
        "self-stopped-midway": self_stopped_midway, "self-hop": self_hop, "install-repair": install_repair}
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
    for version in (NEW, NEXT, AFTER, HIGH):
        rc.publish(base, version, out)
    rc.publish(base, BROKEN, out, replace={"cad_server/engine/daemon.py": BROKEN_DAEMON})
    rc.publish(base, NOSTART, out, replace={"cad_server/_internal/engine_daemon.py": BROKEN_DAEMON})
    rc.publish(base, UNBUILDABLE, out, requires=[MISSING])


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
    say(f"rehearse-update: {', '.join(chosen)}; this tree as {NEW} (and {NEXT}, {BROKEN} and {NOSTART} whose server "
        f"cannot start, {AFTER}, {UNBUILDABLE} uv cannot install; {HIGH} a "
        f"major up); the bridge from {args.old}")
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
