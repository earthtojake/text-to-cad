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
``an_hour_passes``), in ``self-stopped-midway`` the last beat of a worker it stopped (twenty minutes), and in
``self-ready-busy`` the end of the attempt that got a release ready (a day). No route waits for a server to be idle:
cad's own update never does. No real agent app is on any PATH.

Every computer has a folder of releases of its own, holding only those that are out (``Box.out``): the install command
installs PyPI's newest, and cad's own update the newest of a major, or the release the feed or PyPI names (``uv pip
install --target``, which reads that folder as ``uv tool install`` does), so a release not out yet must not be there.
What is out, the feed names (``latest``, and each major's newest as ``lines``) and the stand-in PyPI lists (each
release, its file not yanked). Releases of a higher major (``above``) have a minor and a patch of 9000 and more, past
anything PyPI holds of that major.

The install command counts the runs cad starts of it on every computer (``Box.runs``): the bridge's (install mode,
a shipped release's own setup, a server's one run on a computer our setup reached), and the one the ``cad plugin
update`` of 0.11.12 and 0.11.13 makes. ``cad plugin install``, which this
build's server runs once where cad got newer, installs the plugin with cad's own code and runs no install command: on a
route of cad updating itself the count stays 0, and the run is read from cad's record of it (``caught_up``). The feed
keeps which address each cad read it at (``addresses``): this build's the new one, ``/v1/releases``, a shipped
release's the old, ``/v1/versions``; a route where one read the other's fails, ``self-update`` checks this build read
the new one and ``updater`` the shipped release the old.

**cad updating itself** (a computer the install command set up: cad a uv tool, its automatic updates on). cad's update
never changes the installed cad: it installs the newer release whole in a folder of the store, in the state folder
(``<state>/store/<release>-<what it is built for>``, whose marker ``cad-store.json`` names the release), runs it once,
and then writes the environment's pointer (``<state>/store/pointer-<8 hex>.json``), which every process of the
environment reads as its Python starts. So an
update ends, wherever it is checked (``through_store``), with ``cad --version`` and the server saying the new release;
a process of the environment running the stored release, whole, which the pointer names; and what uv made exactly as uv
made it: ``uv tool list`` and the tool's own ``cad-<release>.dist-info`` naming the release uv installed, uv's receipt
byte for byte, and every file of the environment by size and time (Python's bytecode caches aside, which Python writes
itself). An update that fails before the switch changes nothing that runs; one whose new server does not start goes
back by itself.

The server's own update only gets the release **ready** (``made_ready``): its record ``ready`` (``"switch": false``,
not typed, at its first try, not counted), the release whole in the store and nothing pointing at it, the release
before still running -- the same server process, ``cad --version`` -- and the viewer's button saying ``ready``. The
restart onto it comes later, by one of the ways a route takes: the server's next start, which becomes the switch
(``restarted_at_start``: ``cad server start`` says the release that was ready is running, and no server of the release
before answers the door in between, as a client looking every 50 ms sees it), the button (``restarted_by_button``:
``POST /api/v1/local/update`` ``{}``), a typed ``cad update`` (``typed_restart``: the restart alone said), with PyPI
reachable or not; never by itself at a tending, however busy the server and however long the release has been ready
(``self-ready-busy``).

- ``self-update``: with ``cad plugin update auto on``, the feed names the next release and an hour passes; the running
  server gets it ready at its next tending, at its first try; then a person clicks the viewer's button (202, the button ``working``
  at its ``switching`` step: nothing is left to install), and the next release's server answers, through the store as
  above, its record ``installed`` and a person's; that server serves the viewer it carries (``viewer``: ``GET /`` the
  page of the wheel the route built, its module script, and a process of the environment finding the viewer inside the
  stored release, where this run's wheels carry the built viewer; ``GET /api/v1/server`` alone where they carry none);
  then that server, newer than the release the plugin is up to date for, runs its own ``cad plugin install`` once:
  exit 0, kept in its record (``install-command.json``: up to date for the next release, at its first try), its output
  in ``install-command.log``; the helper ran none, and no install command ran.
- ``self-typed``: with ``cad update auto off`` and the plugin's switch on, ``cad update`` is typed with nothing newer on
  PyPI: it says so and nothing restarts; then PyPI names the next release and ``cad update`` is typed again: the
  server asks PyPI at once and updates cad to it; the command, a running ``cad`` of the tool, waits, says each step once
  on stderr (the release installed beside this one, then the server restarted on it, where the command saw that
  begin: a restart can be over in a moment) and ``cad <new> updated to <next>``; cad is the next release through the store, its server answers, and the plugin catches up: that server runs
  ``cad plugin install`` once, as after an automatic update.
- ``self-typed-stopped``: the same with no server running: ``cad update`` with nothing newer says so and starts no
  server; with the next release out it says ``cad <new> updated to <next>`` (exit 0, its steps on stderr: the second,
  ``cad: switching to it``, only where the command saw it begin, a switch with no server being over in a moment), the
  record says no server is started (``"start": false``, no ``started``),
  ``cad --version`` says the next release through the store, no server and no process of the computer runs
  afterwards, automatic updates stay off, and no ``cad plugin install`` runs (no server runs to catch the plugin up).
- ``self-at-start``: the plugin's switch off, the server stopped, the feed's file already naming the next release, then
  ``cad server start``: the server starts at once as the release installed, and the start says so; then it
  gets the next release ready in the background at its first try; then the server is stopped and started again, and
  that start is the switch: the next release's server answers, the update automatic; no ``cad plugin install`` runs.
- ``self-off``: with ``cad update auto off``, the server reads the feed naming the next release, and a start of the
  server starts the same cad: nothing updates.
- ``self-rollback``: ``cad update`` to a release whose server cannot start (its engine module,
  ``cad_server/_internal/engine_daemon.py``, raises): cad goes back by itself. The command exits non-zero with one line
  that names both releases and says the release before runs again; the record is ``failed``, cause ``start_failed``,
  ``restored``; the release before serves the pages' port again with their token, the environment runs its own cad, and
  no pointer is left; the failure is counted. It is not tried again by itself: an hour passes with the feed naming it,
  and two tendings later no attempt has begun. Then the feed names the release after it, an hour passes, the
  automatic update gets that one ready at its first try, and the server's next start is the switch to it.
- ``self-broken``: the release whose server cannot start installed by uv as the tool itself: its ``cad server start``
  fails, begins the update itself (``cad: updating cad to <after>``), and the next release's server answers, through
  the store.
- ``self-unbuildable``: ``cad update`` to a release uv cannot install (it requires a package no index has): it fails
  with a cause read from uv's words (``no_release``, or ``config_index`` where an index setting of uv's is there, as the
  computer's folder of releases is), its log naming the package, and nothing that runs was touched: the same server
  process answers before and after, never restarted; the record ``failed``; the environment runs its own cad, as uv
  made it; no pointer; the store holds no release and no ``.building-`` folder.
- ``self-unrunnable``: the same for a release that installs but does not pass its own check (its
  ``cad_server/_internal/selftest.py`` raises): cause ``broken``.
- ``self-major``: the rule that a new major never installs itself, and that nothing crosses one. With the next release
  and a release a major up out, the server gets the next release ready, never the higher major, and a typed ``cad
  update`` restarts on it (naming the higher major and the migration guides in one line); then, automatic updates
  off, a typed ``cad update`` says the next release is the newest of its major and names the higher one, beginning
  nothing; ``cad update --major`` is refused as an unknown option (exit 2), beginning nothing; then, automatic updates
  on, with the release after out, the server gets that one ready, never the higher major, and a typed ``cad update``
  with PyPI out of reach (the stand-in answering 503) restarts on it all the same. Each through the store: uv's
  receipt stays byte for byte as the install wrote it, and cad writes no range there.
- ``self-pipx``: cad installed by ``pipx install cad`` (pipx itself a uv tool of the computer's, on pip's backend, its
  folders in the home, pip offered this tree's releases by ``PIP_FIND_LINKS``): the install command, a person's run,
  finds nothing newer for pipx's cad (its own ``cad update``), installs no uv tool, hands over to that cad's ``cad
  plugin install`` and turns the plugin's switch on by that cad (``cad plugin update auto on``); the next release
  and a release a major up out and an hour passed, the server gets the next release ready, never the higher
  major, and its next start is the switch, through the store as uv's cad updates, and the new cad's server runs ``cad
  plugin install`` once; then, automatic updates off, a typed ``cad update`` with nothing newer in its major says so
  and names the higher major, and with the release after out updates pipx's cad to it, whose server runs ``cad plugin
  install`` once more. No ``pipx upgrade`` runs: pipx's own record of its environment (``pipx_metadata.json``)
  stays byte for byte and ``pipx list`` names the first release throughout, while pipx's ``cad`` says each new one; an
  open page's port and token reach the last.
- ``self-called``: the acceptance test of the switch. While the update runs (from its record underway, through the
  release ready, to the end of the switch), three callers each run the bin folder's ``cad`` every 50 ms, rotating ``cad
  --version``, ``cad server status`` and ``cad server start``, as agent apps call it. The release gets ready by itself,
  the server untouched; then a person clicks the button, the update installs at its first try, and the next release's
  server answers and serves the viewer. No call fails but with cad's own one line that it updated itself while the
  command ran, and those
  only from 10 s before the switch (the pointer's ``at``) to 1 s after it; the run says how many calls ran, how many
  failed, and with what. On the shipped mechanism, which upgraded uv's tool in place, this destroyed the install on
  Windows.
- ``self-held``: ``cad update`` twice, the second while a file of the installed cad (its ``cad_server/__init__.py``)
  and the same file of the release that runs (the stored one) are held open by another process, as long as the update
  takes (on Windows a held file cannot be deleted or replaced): it installs all the same.
- ``self-reinstall``: after an update through the store, a person's ``uv tool install --reinstall cad`` (with this
  computer's releases) runs what uv installed, at once, from the environment's own packages: the pointer of the
  install before means nothing; the next ``cad update`` points cad at the newest again. On a second computer, after an
  update through the store, ``uv tool upgrade cad`` by hand puts the newest release in the tool, and cad runs it.
- ``self-stopped-midway``: the update's worker (its command line names ``-m cad_server._internal.auto_update_helper``)
  and its uv are stopped, by force, while uv builds the next release in a ``.building-`` folder of the store: the
  server never stopped (the same process answers), cad is still the release installed and runs, and no pointer was
  written; twenty minutes pass with no beat from the worker and the attempt is counted as lost; then a typed ``cad
  update`` installs the release, and the release's tries keep the one before as lost.
- ``self-hop``: the shipped ``SHIPPED`` (0.11.17), the newest release whose update upgrades uv's tool in place,
  installed from PyPI as a uv tool, its server running: its own ``cad update``, typed, updates it the old way into
  this tree (its helper runs uv's upgrade of the tool: uv lists this tree's release, which runs from the environment's
  own packages, no pointer), and from there this tree's ``cad update`` updates through the store (uv's tool stays,
  the pointer appears). Every computer of a shipped release arrives this way. The shipped release reads this tree's
  release from the stand-ins as it reads PyPI's: the feed's ``/v1/releases`` and ``CAD_PYPI_URL``.
- ``self-ready-busy``: a server never left alone: from before the feed names the next release to the end of the route,
  a page asks ``GET /api/v1/server`` every 2 s and a command (``cad server status``) runs every 3 s. The release gets
  ready all the same, at once (begun within a few tendings of the server reading the feed; the route says how many
  commands the server answered before it began), and nothing restarts by itself: ten tendings, then the record's
  ``ended`` set back a day (and a minute) and ten tendings more, the same server process, the record still ``ready``
  and uncounted, the button ``ready``. Then the server's next start is the switch, the page and the commands going on.
- ``self-ready-waits``: the next release ready by itself, and never switched to by itself where it must not be: with
  automatic updates off, ``cad server start`` starts the release before (the button still offers the restart); with
  them on again but the feed as last read naming it no more (taken back from the feed and PyPI), the same, and the
  button offers nothing; with the feed naming it again, an hour passes, and that start, going by the feed as last read,
  still starts the release before; once the server has read the feed, its next start is the switch.
- ``self-ready-rollback``: a release whose server cannot start, ready by itself (its build runs: only its server fails),
  then the server's next start is the switch to it: cad goes back by itself, the record ``failed``, cause
  ``start_failed``, ``restored``, counted; the ``cad server start`` that began it ends with a server of the release
  before running, which serves the pages' port with their token; no pointer. It is held back: an hour passes with the
  feed naming it, two tendings and another start, and no attempt began.
- ``self-ready-damaged``: the next release ready, then a module its own check imports gone from its folder in the
  store: the server's next start resumes the attempt, the worker finds the stored release no longer runs, builds it
  again (its log names the ``.building-`` folder) and switches to it, at the same try; the file is there again.

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

``all`` (the default) is every route; ``self`` the twenty of cad updating itself; ``bridge`` the ten from a shipped
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
# one uv cannot install (it requires a package no index has), and one that does not pass its own check.
NEW, NEXT, BROKEN, NOSTART, AFTER, UNBUILDABLE, UNRUNNABLE = (rc.stamp(_BASE + step) for step in range(7))
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
# What the release that does not pass its own check (``UNRUNNABLE``) has for that check, and what the release uv
# cannot install (``UNBUILDABLE``) requires.
BROKEN_CHECK = b"raise SystemExit('cad: this build does not pass its own check (a rehearsal of one that does not)')\n"
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

    def taken(self, env: Path) -> dict | None:
        """What a process of the environment ``env`` runs, as its interpreter says (``TAKEN``); None where it cannot."""
        done = self.run([rc.interpreter(env), "-c", TAKEN], check=False, timeout=60)
        try:
            found = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        return found if isinstance(found, dict) else None

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
        lock is free: it writes nothing after), the feed's stamp set back, and started again: it reads the feed at its
        first tending. Where cad's own update has a release ready, that start may be the switch to it
        (``restarted_at_start``), and says the release that was ready is running."""
        was = self.version().removeprefix("cad ")
        held = self.read("auto-update.json")
        self.run([self.cad(), "server", "stop"])
        self.an_hour_passes()
        started = self.run([self.cad(), "server", "start"]).stdout.strip()
        switched = held.get("outcome") == "ready" and started == UPDATED.format(release=held.get("release"), was=was)
        if "started" not in started and not switched:
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

# What a process of an environment runs, asked of the module every interpreter of it imports as it starts
# (``_cad_release``, by the wheel's ``cad.pth``): where the environment's pointer is, the stored release the process
# took (None: the environment's own packages), and where that release finds the viewer it serves.
TAKEN = ("import json, _cad_release as taken\nfrom cad_server import assets\n"
         "print(json.dumps({'pointer': taken.pointer(), 'stored': taken.STORED, "
         "'viewer': str(assets.viewer_dist_dir())}))")
# What the server's environment holds of the update's book, asked of the release that runs: why the last attempt did
# not install what it was for (``auto_update.cause``: ``lost`` once its worker has been silent too long).
CAUSE = "from cad_server._internal import auto_update as a\nprint(a.cause(a.last() or {}) or '')"
# How long an attempt's worker may be silent before the attempt is taken for lost (``auto_update.LOST_SECONDS``),
# and a minute more: how far ``self-stopped-midway`` sets the last beat of a worker it stopped back.
LOST_SECONDS = 21 * 60.0
# The words a ``cad`` command says where the server it reached is the next release's, which cad's own update started
# while the command ran (``cli_errors.classify``).
UPDATED_LINE = "cad updated itself to {release} while this command ran: run it again"


def updated(box: Box, target: str, outcome: str = "installed", *, after: dict | None = None) -> dict:
    """cad's own update to ``target`` ended (its record, ``auto-update.json``) with ``outcome``: the record. ``after``:
    the record of the attempt that got ``target`` ready, which the sitting that switches to it takes the place of (a
    resume has an ``at`` of its own), so only that sitting's end is awaited."""
    record = box.until(lambda: (lambda found: found if found.get("release") == target and "ended" in found and (
        after is None or found.get("at") != after.get("at")) else None)(box.read("auto-update.json")),
        f"cad's own update to {target} ended")
    if record.get("outcome") != outcome:
        raise Failed(f"{box.label}: cad's own update to {target}: {record}\n{box.said()}")
    return record


# What ``cad server start`` says (``cad.engine.client.start``): where it started a server of the release it is, and
# where it stood by while cad's own update switched releases and the server that answered is the next release's -- a
# start that became the switch to a release the update had ready (``restarted_at_start``).
STARTED = "started the cad server (cad {release})"
UPDATED = "started the cad server (cad {release}): cad updated itself from {was} as the server started"


def made_ready(box: Box, env: Path, was: str, target: str, first: dict) -> dict:
    """cad's own update got ``target`` ready by itself beside ``was``, and nothing restarted (see the module): its record
    ``ready``, an automatic attempt that switches nothing (``"switch": false``, not typed, at its first try), not
    counted (``reported``: its switch is the sitting counted); the release whole in the store (``<state>/store``, its
    marker naming it), and no pointer naming it; the release before still the one that runs -- the same server process
    as ``first`` (its status) answering as ``was``, ``cad --version`` saying ``was`` --; and the viewer's update button
    offering the restart (``GET /api/v1/server``: ``cadUpdate``'s ``state`` ``ready``, ``ready`` the release). The
    record."""
    record = updated(box, target, "ready")
    store = box.state / "store"
    held = [path.name for path in (store.glob(f"{target}-*") if store.is_dir() else [])
            if read_json(path / "cad-store.json").get("release") == target]
    taken = box.taken(env) or {}
    now = box.ask(rc.interpreter(env), "status") or {}
    status, answer = box.http("GET", "/api/v1/server")
    button = answer.get("cadUpdate") or {}
    problems = []
    if (record.get("switch"), record.get("asked"), record.get("tries"), record.get("from")) != (False, False, 1, was) \
            or "reported" in record:
        problems.append(f"the record {record}")
    if not held or read_json(Path(taken.get("pointer") or "/nowhere")).get("release") == target:
        problems.append(f"the store holds {sorted(os.listdir(store)) if store.is_dir() else []}, a process of the "
                        f"environment runs {taken}")
    if (now.get("pid"), now.get("version")) != (first.get("pid"), was) or not first.get("pid") \
            or box.version() != f"cad {was}":
        problems.append(f"the server was {first}, is {now}; cad --version says {box.version()!r}")
    if (status, answer.get("release"), button.get("state"), button.get("ready"), button.get("version")) != (
            200, was, "ready", target, was):
        problems.append(f"GET /api/v1/server answered {status}: {answer}")
    if problems:
        raise Failed(f"{box.label}: {target} ready beside {was}, nothing restarted:\n  " + "\n  ".join(problems)
                     + f"\n{box.said()}")
    return record


# Which server answers the computer's door, asked every 50 ms by a client of the release that runs until the input
# ends (``Watch``): a first line once it looks, then a line for each look, ``[release, process]`` or null.
WATCH = """import json, os, sys, threading, time
from cad.engine import client
def end():
    sys.stdin.read()
    os._exit(0)
threading.Thread(target=end, daemon=True).start()
print("watching", flush=True)
while True:
    try:
        found = client.request({"op": "status", "internal": True}, start=False)
    except Exception:
        found = None
    print(json.dumps([found.get("version"), found.get("pid")] if isinstance(found, dict) else None), flush=True)
    time.sleep(0.05)
"""


class Watch:
    """The servers that answer the computer's door while a step runs, as a client of the environment ``env`` sees them
    every 50 ms (``WATCH``): ``stop`` ends the look and says each ``(release, process)`` that answered, in order."""

    def __init__(self, box: Box, env: Path) -> None:
        self.seen: list[tuple[str, int]] = []
        self.looks = 0
        self.process = subprocess.Popen([rc.interpreter(env), "-c", WATCH], env=box.env, cwd=box.work,
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
            if found and (not self.seen or self.seen[-1] != tuple(found)):
                self.seen.append(tuple(found))

    def saw(self, release: str) -> bool:
        return any(found == release for found, _pid in list(self.seen))

    def stop(self) -> list[tuple[str, int]]:
        self.process.stdin.close()
        self.process.wait(60)
        self.reading.join(60)
        return list(self.seen)


def restarted_at_start(box: Box, env: Path, was: str, target: str, ready: dict) -> tuple[dict, str]:
    """The server's next start, with ``target`` ready beside ``was`` (``ready``: its record): stopped by its own
    command, then ``cad server start``, which becomes the switch -- the server of ``was`` it starts begins the switch
    and serves nothing, the update's worker starts ``target``'s, and the command returns once that one answers, saying
    it runs (``UPDATED``), exit 0. No server of ``was`` answered the door from the stop until ``target``'s did, as a
    client looking every 50 ms sees it (``Watch``). The switch is the automatic one's: its record ``installed``, not
    typed, at the try that got it ready. The record, and the route's line."""
    box.run([box.cad(), "server", "stop"])
    watch = Watch(box, env)
    try:
        began = time.monotonic()
        done = box.run([box.cad(), "server", "start"], check=False)
        took = time.monotonic() - began
        record = updated(box, target, after=ready)
        # Until the watch itself has seen the server that answered the start: what it saw before is what came between.
        box.until(lambda: watch.saw(target), f"the watch on the door seeing {target}'s server", seconds=60)
    finally:
        seen = watch.stop()
    said = UPDATED.format(release=target, was=was)
    if (done.returncode, done.stdout.strip()) != (0, said) or [release for release, _pid in seen] != [target]:
        raise Failed(f"{box.label}: cad server start with {target} ready exited {done.returncode} in {took:.1f} s:\n"
                     f"{done.stdout}\n{done.stderr}\nthe door answered as {seen} ({watch.looks} looks)\n{box.said()}")
    if (record.get("asked"), record.get("from"), record.get("tries")) != (False, was, 1) or "restored" in record:
        raise Failed(f"{box.label}: the switch a start began: {record}\n{box.said()}")
    return record, (f"`cad server start` with {target} ready: {said!r} in {took:.1f} s (exit 0); no server of {was} "
                    f"answered the door from the stop until {target}'s did, {watch.looks} looks")


def restarted_by_button(box: Box, was: str, target: str, ready: dict) -> dict:
    """The viewer's update button clicked with ``target`` ready beside ``was`` (``ready``: its record): ``POST
    /api/v1/local/update`` ``{}``, as a page posts it, answered 202 with the button's ``working`` at its ``switching``
    step (nothing left to install: the page shows the restart, no progress); the update a person's (``asked``), at the
    try that got the release ready. The record."""
    status, answer = box.http("POST", "/api/v1/local/update", body=b"{}",
                              headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
    button = answer.get("cadUpdate") or {}
    if (status, button.get("state"), button.get("phase")) != (202, "working", "switching"):
        raise Failed(f"{box.label}: the update button with {target} ready answered {status}: {answer}\n{box.said()}")
    record = updated(box, target, after=ready)
    if (record.get("asked"), record.get("from"), record.get("tries")) != (True, was, 1) or "restored" in record:
        raise Failed(f"{box.label}: the switch the button began: {record}\n{box.said()}")
    return record


def typed_restart(box: Box, was: str, target: str, ready: dict, *, also: tuple[str, ...] = ()) -> dict:
    """``cad update`` typed with ``target`` ready beside ``was`` (``ready``: its record): only the restart is left, so
    it says that one step on stderr, naming the release, and ``cad <was> updated to <target>`` (then ``also``, a line
    naming a higher major, say) on stdout, exit 0; the update a person's, at the try that got the release ready. The
    record."""
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    step = f"cad: restarting the cad server on cad {target}, installed beside cad {was}"
    if (done.returncode, done.stdout.strip().splitlines(), done.stderr.strip().splitlines()) != (
            0, [f"cad {was} updated to {target}", *also], [step]):
        raise Failed(f"{box.label}: cad update with {target} ready exited {done.returncode}:\n{done.stdout}\n"
                     f"{done.stderr}\n{box.said()}")
    record = updated(box, target, after=ready)
    if (record.get("asked"), record.get("from"), record.get("tries")) != (True, was, 1):
        raise Failed(f"{box.label}: the switch a typed update began: {record}\n{box.said()}")
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


class Installed:
    """What an installer made of cad's environment ``env`` (its ``release``), as it was when taken: what the installer
    lists (``listing``, run in the computer: ``uv tool list --show-paths``, ``pipx list --short``), its own record of
    the environment, byte for byte (``record``: uv's receipt, pipx's metadata), and every file there by size and time
    (``files``). An update through the store changes none of it (``changed``)."""

    def __init__(self, box: Box, env: Path, release: str, listing: list[str], record: str) -> None:
        self.box, self.env, self.release, self.listing, self.record = box, Path(env), release, listing, record
        self.listed = self.lists()
        self.recorded = (self.env / record).read_bytes()
        self.files = files(self.env)

    def lists(self) -> str:
        done = self.box.run(self.listing, check=False, timeout=60)
        return done.stdout.strip() or f"(exit {done.returncode}: {done.stderr.strip()})"

    def changed(self) -> list[str]:
        """What changed since it was taken: a file of the environment (changed, added or gone), the installer's
        record, or what the installer lists."""
        now = files(self.env)
        found = [f"{path}: {self.files[path]} -> {now.get(path)}" for path in self.files
                 if now.get(path) != self.files[path]]
        found += [f"{path}: added" for path in now if path not in self.files]
        if (self.env / self.record).read_bytes() != self.recorded:
            found.append(f"{self.record}: written again")
        listed = self.lists()
        if listed != self.listed:
            found.append(f"`{' '.join(self.listing)}` said {self.listed!r}, now {listed!r}")
        return found


def uv_installed(box: Box) -> Installed:
    """uv's tool ``cad`` as uv installed it (``Installed``)."""
    tool = box.tool()
    if tool is None:
        raise Failed(f"{box.label}: uv lists no cad tool\n{box.said()}")
    return Installed(box, Path(tool["env"]), tool["version"], ["uv", "tool", "list", "--show-paths"], "uv-receipt.toml")


def serves(box: Box, env: Path, version: str) -> dict:
    """The server answering as ``version``, run from the environment ``env`` (its ``prefix``), whatever its installer
    lists there: its status."""
    def found():
        status = box.ask(rc.interpreter(env), "status")
        return status if status and status.get("version") == version and rc._within(
            Path(status.get("prefix") or "/nowhere"), env) else None
    return box.until(found, f"the server of {env} answering as {version}")


def through_store(box: Box, before: Installed, release: str, *, server: bool = True) -> Path:
    """cad updated to ``release`` through the store, as the update leaves it (see the module): ``cad --version`` says
    ``release``; a process of the environment takes a stored release, a folder of ``<state>/store`` whose marker
    (``cad-store.json``) names ``release``, by the environment's pointer, which names it; the cad installed there is
    still the installer's release (its one ``cad-<release>.dist-info``), and nothing ``before`` took of the environment
    changed; with ``server``, the server answers as ``release`` from the environment. The stored release."""
    taken = box.taken(before.env) or {}
    stored = Path(taken.get("stored") or "/nowhere")
    marker = read_json(stored / "cad-store.json")
    pointer = read_json(Path(taken.get("pointer") or "/nowhere"))
    infos = dist_infos(before.env)
    problems = []
    if box.version() != f"cad {release}":
        problems.append(f"cad --version says {box.version()!r}")
    if os.path.realpath(stored.parent) != os.path.realpath(box.state / "store") or marker.get("release") != release:
        problems.append(f"a process of the environment runs {taken} (its marker {marker})")
    if (pointer.get("release"), pointer.get("path")) != (release, str(stored)):
        problems.append(f"the pointer {taken.get('pointer')} holds {pointer}")
    if infos != [f"cad-{before.release}.dist-info"]:
        problems.append(f"the environment's own cad is {infos}, not the installer's {before.release}")
    problems += before.changed()
    if problems:
        raise Failed(f"{box.label}: cad updated to {release} through the store:\n  " + "\n  ".join(problems)
                     + f"\n{box.said()}")
    if server:
        serves(box, before.env, release)
    return stored


def runs_its_own(box: Box, env: Path, release: str) -> None:
    """The environment ``env`` runs its own packages, ``release``, as its installer installed them: a process there
    takes no stored release, its one ``cad-<release>.dist-info``, and ``cad --version`` says ``release``."""
    taken = box.taken(env) or {}
    if taken.get("stored") is not None or dist_infos(env) != [f"cad-{release}.dist-info"] \
            or box.version() != f"cad {release}":
        raise Failed(f"{box.label}: not {release} as installed: a process there runs {taken}, the environment holds "
                     f"{dist_infos(env)}, cad --version says {box.version()!r}\n{box.said()}")


def dist_infos(env: Path) -> list[str]:
    """The ``cad-<release>.dist-info`` folders of the environment ``env``."""
    return sorted(path.name for pattern in ("lib/python*/site-packages/cad-*.dist-info",
                                            "Lib/site-packages/cad-*.dist-info") for path in env.glob(pattern))


def read_json(path: Path) -> dict:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def no_pointer(box: Box, env: Path) -> None:
    """No pointer for the environment ``env``, and a process there takes no stored release."""
    taken = box.taken(env) or {}
    if taken.get("stored") is not None or not taken.get("pointer") or Path(taken["pointer"]).exists():
        raise Failed(f"{box.label}: a pointer was written: {taken}, {read_json(Path(taken.get('pointer') or '.'))}\n"
                     f"{box.said()}")


def viewer(box: Box, release: str, env: Path, stored: Path) -> str:
    """The viewer served by the server of ``release``, which runs the stored release ``stored`` in the environment
    ``env``: ``GET /api/v1/server`` names ``release``; and where this run's wheels carry the built viewer (cad's wheel
    of ``release`` holds ``cad_server/_runtime/viewer/index.html``), a process of the environment finds it inside
    ``stored`` and nowhere else, ``GET /`` answers 200 with that page (it names the page's module script) and that
    script answers 200: a stored release finds the files it ships beside its own code. The route's line."""
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
    found = Path((box.taken(env) or {}).get("viewer") or "/nowhere")
    status, body = box.fetch("/")
    asset, _ = box.fetch(f"/{script[1]}")
    if not rc._within(found, stored) or status != 200 or script[1] not in body.decode("utf-8", "replace") \
            or asset != 200:
        raise Failed(f"{box.label}: the viewer of {release}: found at {found} (not in {stored}), GET / answered "
                     f"{status} {body[:200]!r}, GET /{script[1]} {asset}\n{box.said()}")
    return f"GET / served {release}'s viewer ({script[1]}, 200), found in the stored release"


def typed_update(box: Box, was: str, target: str, *, server: bool = True) -> dict:
    """``cad update`` typed, PyPI naming ``target``: it says each step once on stderr as it sees it begin -- the
    release installed beside the one that runs, then the switch, with the server restarted where one runs
    (``server``) -- and ``cad <was> updated to <target>`` on stdout, exit 0. The command looks at the record every
    moment, so a switch over before it looks again (with no server, or a server that stopped and started in a moment)
    is not said. The record, ``installed`` and typed."""
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    steps = [f"cad: installing cad {target} beside cad {was}",
             "cad: restarting the cad server on it" if server else "cad: switching to it"]
    said = done.stderr.strip().splitlines()
    if (done.returncode, done.stdout.strip()) != (0, f"cad {was} updated to {target}") \
            or said not in (steps, steps[:1]):
        raise Failed(f"{box.label}: cad update exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n{box.said()}")
    record = updated(box, target)
    if (record.get("asked"), record.get("from")) != (True, was):
        raise Failed(f"{box.label}: the record of a typed update: {record}")
    return record


def self_update(box: Box) -> None:
    box.set_up("on")
    before = uv_installed(box)
    box.out(NEXT)
    box.hour_later()
    ready = made_ready(box, before.env, NEW, NEXT, box.ask(rc.interpreter(before.env), "status") or {})
    read_feed(box, "releases", "cad")
    say(f"        {NEXT} ready by itself, at its first try, beside {NEW}, whose server runs on; the button says "
        "ready")
    # Then a person clicks the viewer's button, which restarts the server on it.
    record = restarted_by_button(box, NEW, NEXT, ready)
    stored = through_store(box, before, NEXT)
    if record.get("installer") != "uv":
        raise Failed(f"{box.label}: the record of the update: {record}")
    # Then `cad plugin install`, once, by the new cad's server: kept in its record, its output in the log.
    caught_up(box, NEXT)
    if (box.state / "versions.json").exists():
        raise Failed(f"{box.label}: this build wrote versions.json, the feed's file of 0.10.0 to 0.11.11")
    say(f"        the button's `POST /api/v1/local/update` {{}}: 202, restarting; {NEW} -> {NEXT}: cad --version and the "
        f"server {NEXT}, run from {stored.name} by the pointer; uv still lists {NEW}, its receipt and the "
        "environment's files as they were; then the new server ran `cad plugin install`, once, exit 0; no "
        "versions.json written")
    say(f"        {viewer(box, NEXT, before.env, stored)}")
    pages(box, NEXT)


def self_major(box: Box) -> None:
    """cad installs by itself any newer release of its major, never a higher major, and no command crosses one: the
    automatic update gets the newer release of this major ready with a higher major out, and a typed ``cad update``
    restarts on it, naming the higher major; a typed ``cad update`` with nothing newer in this major says so, names
    the higher major and begins nothing; ``cad update --major`` is refused as an unknown option; then the automatic
    update gets the next release of this major ready, never the higher major, and a typed ``cad update`` with PyPI out
    of reach restarts on it all the same. uv's receipt stays as uv wrote it throughout."""
    box.set_up("off")
    before = uv_installed(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    box.out(HIGH)  # both out: the feed's `lines` name each, its `latest` the higher major's
    box.hour_later()
    ready = made_ready(box, before.env, NEW, NEXT, box.ask(python, "status") or {})
    read_feed(box, "releases", "cad")
    if ready.get("wanted") != NEXT or "major" in ready:
        raise Failed(f"{box.label}: the automatic update: {ready}\n{box.said()}")
    # A typed `cad update` restarts on it, and names the higher major.
    typed_restart(box, NEW, NEXT, ready, also=(MAJOR_LINE.format(release=HIGH),))
    through_store(box, before, NEXT)
    say(f"        {HIGH} and {NEXT} out: {NEXT} ready by itself, never {HIGH}; a typed `cad update` restarted on it, "
        f"naming {HIGH}; uv's receipt as uv wrote it")
    # Typed: nothing newer in this major; the higher major named in one line, nothing begun.
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    begun = box.read("auto-update.json")
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    said = [f"cad {NEXT} is the newest {MAJOR}.x release", MAJOR_LINE.format(release=HIGH)]
    if (done.returncode, done.stdout.strip().splitlines(), done.stderr.strip()) != (0, said, "") \
            or box.read("auto-update.json").get("at") != begun.get("at") or box.version() != f"cad {NEXT}":
        raise Failed(f"{box.label}: cad update with a higher major out exited {done.returncode}: {done.stdout}"
                     f"{done.stderr}, {box.read('auto-update.json')}\n{box.said()}")
    say(f"        `cad update`: {' / '.join(said)!r}; nothing begun")
    # `cad update --major` is no option: refused as any unknown option is, nothing begun.
    done = box.run([box.cad(), "update", "--major"], check=False, timeout=SECONDS + 60)
    if done.returncode != 2 or "unrecognized arguments: --major" not in done.stderr \
            or box.read("auto-update.json").get("at") != begun.get("at") or box.version() != f"cad {NEXT}":
        raise Failed(f"{box.label}: cad update --major exited {done.returncode}: {done.stdout}{done.stderr}, "
                     f"{box.read('auto-update.json')}\n{box.said()}")
    say("        `cad update --major`: refused as an unknown option (exit 2); nothing begun")
    # Automatic updates on again: the release after, of this major, ready by itself, never the higher major.
    switched = box.run([box.cad(), "update", "auto", "on"]).stdout.strip()
    if switched != "update auto: on":
        raise Failed(f"{box.label}: cad update auto on said {switched!r}")
    box.out(AFTER)
    box.hour_later()
    ready = made_ready(box, before.env, NEXT, AFTER, box.ask(python, "status") or {})
    if ready.get("wanted") != AFTER:
        raise Failed(f"{box.label}: the automatic update with {AFTER} and {HIGH} out: {ready}\n{box.said()}")
    # A typed `cad update` with PyPI out of reach: the release that is ready needs no answer from it.
    box.pypi.down = True
    try:
        typed_restart(box, NEXT, AFTER, ready)
    finally:
        box.pypi.down = False
    through_store(box, before, AFTER)
    say(f"        {AFTER} and {HIGH} out: {AFTER} ready by itself, never {HIGH}; then, PyPI out of reach, a typed "
        f"`cad update` restarted on it: {NEXT} -> {AFTER}; uv's receipt as uv wrote it, uv still lists {NEW}")
    pages(box, AFTER)


def pages(box: Box, version: str) -> None:
    """A page that was open before the update still reaches a server: the pages' port, with their token, answered by
    ``version``'s, nothing asked of it in between (the last check of a route: what came before is said already)."""
    box.until(lambda: box.serving(version), f"{version}'s server answering the pages' port {box.port} with their "
              "token, as before the update", seconds=90)
    say(f"        an open page's port and token reach {version}'s server")


def self_typed(box: Box) -> None:
    # Automatic updates off, the plugin's switch on: a typed update needs neither; the plugin catches up all the same.
    box.set_up("on")
    before = uv_installed(box)
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    # Nothing newer on PyPI: said, and nothing restarts.
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip()) != (0, f"cad {NEW} is the newest release") or box.read("auto-update.json"):
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: {done.stdout}{done.stderr}, "
                     f"{box.read('auto-update.json')}")
    box.out(NEXT)  # out on PyPI; the feed's hour has not passed for the server
    record = typed_update(box, NEW, NEXT)
    if record.get("installer") != "uv":
        raise Failed(f"{box.label}: the record of a typed update: {record}")
    through_store(box, before, NEXT)
    if (box.read("settings.json").get("auto_update") or {}).get("on") is not False:
        raise Failed(f"{box.label}: after cad update: switches {box.read('settings.json').get('auto_update')}")
    caught_up(box, NEXT)
    say(f"        `cad update` with nothing newer: 'cad {NEW} is the newest release', nothing restarted; then {NEW} -> "
        f"{NEXT} with automatic updates off, each step said once on stderr, through the store; then the new server "
        "ran `cad plugin install`, once, exit 0")
    pages(box, NEXT)
    tendings(box, before.env, 2)
    caught_up(box, NEXT)  # and only once: still its first try


def self_typed_stopped(box: Box) -> None:
    """``cad update`` typed with no server running: cad updates in the command's own process, the helper starts no
    server, and ``cad plugin install`` never runs."""
    box.set_up("on")  # the plugin's switch on: a typed update still never runs `cad plugin install`
    before = uv_installed(box)
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    python = rc.interpreter(before.env)
    box.run([box.cad(), "server", "stop"])
    box.until(lambda: box.ask(python, "status") is None, "no server running")
    # Nothing newer on PyPI: said, nothing begun, no server started.
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    if (done.returncode, done.stdout.strip()) != (0, f"cad {NEW} is the newest release") \
            or box.read("auto-update.json") or box.ask(python, "status") is not None:
        raise Failed(f"{box.label}: cad update with nothing newer exited {done.returncode}: "
                     f"{done.stdout}{done.stderr}, {box.read('auto-update.json')}\n{box.said()}")
    box.out(NEXT)  # out on PyPI
    began = time.monotonic()
    record = typed_update(box, NEW, NEXT, server=False)
    took = time.monotonic() - began
    if record.get("start") is not False or "started" in record:
        raise Failed(f"{box.label}: the helper was to start no server: {record}")
    through_store(box, before, NEXT, server=False)
    # No server afterwards: none answers, and nothing of the computer runs once the helper has exited.
    box.until(lambda: not box.computer.processes(), "nothing of the computer running", seconds=60)
    if box.ask(python, "status") is not None or box.computer.processes():
        raise Failed(f"{box.label}: a server runs after the update:\n{box.said()}")
    if (box.read("settings.json").get("auto_update") or {}).get("on") is not False:
        raise Failed(f"{box.label}: switches {box.read('settings.json').get('auto_update')}")
    never_installed(box, record, "a typed cad update")
    say(f"        no server ran: {NEW} -> {NEXT} by a typed `cad update` in {took:.0f} s, through the store, cad "
        f"--version {NEXT}; no server after it, no `cad plugin install`, processes {box.computer.processes()} "
        f"(looked: {box.computer.looked})")


def feed_read(box: Box, latest: str) -> None:
    """The feed as the server last read it naming ``latest`` as the newest of its major, read now (within the hour:
    nothing reads it again soon), in the file the server keeps it in; only while no server runs, which writes that
    file itself."""
    (box.state / "releases.json").write_text(json.dumps({"checked": time.time(), "feed": {
        "latest": latest, "lines": {latest.split(".", 1)[0]: latest}}}), encoding="utf-8")


def self_at_start(box: Box) -> None:
    box.set_up("off")
    before = uv_installed(box)
    box.run([box.cad(), "server", "stop"])
    # The feed as the server last read it, naming the next release, read within the hour: due at the next start.
    box.out(NEXT)
    feed_read(box, NEXT)
    began = time.monotonic()
    done = box.run([box.cad(), "server", "start"], check=False)
    took = time.monotonic() - began
    # It started at once, as the release installed, and said so: the update comes after, in the background.
    if done.returncode != 0 or done.stdout.strip() != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start exited {done.returncode}: {done.stdout}{done.stderr}\n"
                     f"{box.said()}")
    ready = made_ready(box, before.env, NEW, NEXT, box.ask(rc.interpreter(before.env), "status") or {})
    say(f"        `cad server start` answered at once as {NEW} ({took:.1f} s: {done.stdout.strip()!r}); then "
        f"{NEXT} ready in the background at its first try, the {NEW} server running on")
    # The server's next start is the switch.
    record, line = restarted_at_start(box, before.env, NEW, NEXT, ready)
    through_store(box, before, NEXT)
    never_installed(box, record, "the plugin's switch off")
    say(f"        {line}; {NEW} -> {NEXT}, whose server answers; the plugin's switch off: no `cad plugin install`")


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


def self_rollback(box: Box) -> None:
    box.set_up("off")
    env = Path(box.tool()["env"])
    box.out(NOSTART)  # out on PyPI
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    record = updated(box, NOSTART, "failed")
    line = done.stderr.strip().splitlines()[-1:]
    # One line: what failed, that the release before runs again, what to do and where the log is.
    said = f"cad update: could not update cad {NEW} to {NOSTART}, as "
    if done.returncode == 0 or not line or not line[0].startswith(said) \
            or f"so the release before runs again (cad {NEW})" not in line[0]:
        raise Failed(f"{box.label}: cad update to a release whose server cannot start exited {done.returncode}:\n"
                     f"{done.stdout}\n{done.stderr}\n{box.said()}")
    if (record.get("cause"), record.get("restored")) != ("start_failed", True) \
            or str(record.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the way back: {record}\n{box.said()}")
    # The release before serves again, on the pages' port with their token, and the environment runs its own cad.
    box.until(lambda: box.serving(NEW), f"{NEW} serving again on the pages' port with their token")
    serves(box, env, NEW)
    runs_its_own(box, env, NEW)
    no_pointer(box, env)
    box.until(lambda: box.read("auto-update.json").get("reported") is True,
              "the failed update counted by the old server")
    say(f"        `cad update` to {NOSTART}, whose server cannot start: {line[0]!r} (exit {done.returncode}); cause "
        f"start_failed, restored; {NEW} serves the pages' port again, no pointer; the failure counted")
    # Not tried again by itself: an hour passes with the feed naming it, and two tendings later no attempt began.
    typed = box.read("auto-update.json")
    box.hour_later()
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == NOSTART and
              time.time() - box.read("releases.json").get("checked", 0) < 600, "the server reading the feed")
    tendings(box, env, 2)
    if box.read("auto-update.json").get("at") != typed.get("at"):
        raise Failed(f"{box.label}: {NOSTART}, whose server did not start, was tried again by itself: "
                     f"{box.read('auto-update.json')}\n{box.said()}")
    say(f"        an hour later, the feed naming {NOSTART}: not tried again by itself")
    # The next good release, by itself: the one the feed names, not the one that failed.
    before = uv_installed(box)
    box.out(AFTER)
    box.hour_later()
    ready = made_ready(box, env, NEW, AFTER, box.ask(rc.interpreter(env), "status") or {})
    if ready.get("wanted") != AFTER:
        raise Failed(f"{box.label}: the automatic update after the way back: {ready}\n{box.said()}")
    _record, line = restarted_at_start(box, env, NEW, AFTER, ready)
    through_store(box, before, AFTER)
    say(f"        then {AFTER} out: ready by itself at its first try; {line}; {NEW} -> {AFTER} through the store")
    pages(box, AFTER)


def self_broken(box: Box) -> None:
    # A release whose server cannot start, installed by uv as the tool: its own `cad server start` begins the update.
    box.out(NOSTART)
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", "cad"], timeout=SECONDS)
    before = uv_installed(box)
    if before.release != NOSTART or box.version() != f"cad {NOSTART}":
        raise Failed(f"{box.label}: uv's cad is {before.release}, cad --version says {box.version()!r}")
    box.out(AFTER)
    done = box.run([box.cad(), "server", "start"], check=False)
    if done.returncode == 0 or f"cad: updating cad to {AFTER}" not in done.stderr:
        raise Failed(f"{box.label}: cad server start on {NOSTART} exited {done.returncode}: {done.stdout}{done.stderr}")
    record = updated(box, AFTER)
    if (record.get("asked"), record.get("from")) != (False, NOSTART):
        raise Failed(f"{box.label}: the update a failed start began: {record}")
    through_store(box, before, AFTER)
    say(f"        {NOSTART} installed by uv, its server down: `cad server start` failed and began the update, and "
        f"{AFTER}'s server answers, through the store")


def unswitched(box: Box, release: str, causes: tuple[str, ...]) -> dict:
    """A typed ``cad update`` to ``release``, which fails before anything switches, with a cause of ``causes``:
    nothing that runs was touched. The command exits non-zero and says so in one line; the same server process
    answers before and after, never restarted; the environment runs its own cad, unchanged, no pointer written, and
    the store holds no release and nothing half built. The record."""
    box.set_up("off")
    before = uv_installed(box)
    python = rc.interpreter(before.env)
    first = box.ask(python, "status") or {}
    box.out(release)  # out on PyPI
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 60)
    record = updated(box, release, "failed")
    after = box.ask(python, "status") or {}
    line = done.stderr.strip().splitlines()[-1:]
    store = box.state / "store"
    held = sorted(os.listdir(store)) if store.is_dir() else []
    if done.returncode == 0 or not line \
            or not line[0].startswith(f"cad update: could not update cad {NEW} to {release}, as "):
        raise Failed(f"{box.label}: cad update to {release} exited {done.returncode}:\n{done.stdout}\n{done.stderr}")
    if record.get("cause") not in causes or "restored" in record:
        raise Failed(f"{box.label}: the record of the update to {release}: {record}\n{box.said()}")
    if (first.get("pid"), first.get("version")) != (after.get("pid"), NEW) or not first.get("pid") \
            or after.get("up", 0) <= first.get("up", 0):
        raise Failed(f"{box.label}: the server before the update {first}, after {after}\n{box.said()}")
    if held or before.changed():
        raise Failed(f"{box.label}: after a failed update the store holds {held}; the environment: {before.changed()}")
    runs_its_own(box, before.env, NEW)
    no_pointer(box, before.env)
    return record


def self_unbuildable(box: Box) -> None:
    # uv's words name the cause: a requirement the index does not have (where an index setting of uv's is there, as
    # the computer's folder of releases is, its name).
    record = unswitched(box, UNBUILDABLE, ("no_release", "config_index"))
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")
    if MISSING.split("==")[0] not in log:
        raise Failed(f"{box.label}: the update's log names nothing of what uv could not find:\n{log[-3000:]}")
    say(f"        {UNBUILDABLE}, which requires {MISSING}: not built (cause {record['cause']}: {record['detail']!r}); "
        f"the same {NEW} server process answered throughout, no pointer, nothing in the store")


def self_unrunnable(box: Box) -> None:
    record = unswitched(box, UNRUNNABLE, ("broken",))
    say(f"        {UNRUNNABLE}, which fails its own check: built, never switched to (cause broken: "
        f"{record['detail']!r}); the same {NEW} server process answered throughout, no pointer, nothing in the store")


class Callers:
    """Agents and apps calling ``cad`` while an update runs (``self-called``): ``count`` threads, each running the bin
    folder's ``cad`` every ``every`` seconds once the attempt is underway (its record) and until the update has ended
    (an outcome past ``underway`` and ``ready``: the release got ready, then the switch to it), each rotating through
    ``CALLS`` from a place of its own. ``calls``: each call's begin and end (``time.time``), what it ran, its exit status
    (or what stopped it) and the last line it said on stderr."""

    CALLS = (["--version"], ["server", "status"], ["server", "start"])

    def __init__(self, box: Box, count: int = 3, every: float = 0.05) -> None:
        self.box, self.every, self.done, self.lock = box, every, threading.Event(), threading.Lock()
        self.calls: list[tuple[float, float, str, object, str]] = []
        self.threads = [threading.Thread(target=self.call, args=(first,), daemon=True) for first in range(count)]
        for thread in self.threads:
            thread.start()

    def outcome(self) -> object:
        return self.box.read("auto-update.json").get("outcome")

    def call(self, at: int) -> None:
        while not self.done.is_set() and self.outcome() != "underway":
            time.sleep(self.every)
        while not self.done.is_set() and self.outcome() in ("underway", "ready"):
            command = self.CALLS[at % len(self.CALLS)]
            at += 1
            began = time.time()
            try:
                done = subprocess.run([str(self.box.cad()), *command], env=self.box.env, cwd=self.box.work,
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=120)
                how, said = done.returncode, (done.stderr.strip().splitlines() or [""])[-1]
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


# How far from the switch (the pointer's ``at``) a command may meet the next release's server: one that began just
# before it, of the release before, and found the next release's server (``UPDATED_LINE``).
SWITCH_WINDOW = (-10.0, 1.0)


def self_called(box: Box) -> None:
    box.set_up("off")
    before = uv_installed(box)
    box.out(NEXT)
    callers = Callers(box)
    try:
        box.hour_later()
        # Ready by itself while they call, the server untouched; then a person clicks the viewer's button.
        ready = made_ready(box, before.env, NEW, NEXT, box.ask(rc.interpreter(before.env), "status") or {})
        status, answer = box.http("POST", "/api/v1/local/update", body=b"{}",
                                  headers={"x-cad-viewer": "1", "Content-Type": "application/json"})
        if status != 202:
            raise Failed(f"{box.label}: the update button with {NEXT} ready answered {status}: {answer}")
        record = box.until(lambda: (lambda found: found if found.get("release") == NEXT and "ended" in found
                                    and found.get("at") != ready.get("at") else None)(box.read("auto-update.json")),
                           f"the switch to {NEXT} ended")
    finally:
        calls = callers.stop()
    pointer = read_json(Path((box.taken(before.env) or {}).get("pointer") or "/nowhere"))
    switch = pointer.get("at") if isinstance(pointer.get("at"), (int, float)) else 0.0
    failed = [call for call in calls if call[3] != 0]
    met = UPDATED_LINE.format(release=NEXT)
    wrong = [call for call in failed if not call[4].endswith(met)
             or not SWITCH_WINDOW[0] <= call[0] - switch <= SWITCH_WINDOW[1]]
    said: dict[str, int] = {}
    for call in failed:
        key = f"{call[2]}: exit {call[3]}: {call[4]}"
        said[key] = said.get(key, 0) + 1
    tally = f"{len(calls)} calls, {len(failed)} failed" + "".join(f"\n          {count} x {key}"
                                                                   for key, count in sorted(said.items()))
    # The calls ran across the switch: one began before it, and one ended after it.
    across = bool(calls) and min(call[0] for call in calls) < switch < max(call[1] for call in calls)
    if record.get("outcome") != "installed" or record.get("tries") != 1 or "restored" in record or not across \
            or wrong:
        raise Failed(f"{box.label}: the update while cad was called: {record}; {tally}; out of place:\n"
                     + "\n".join(f"  {call[0] - switch:+.2f} s from the switch: {call[2]}: {call[3]}: {call[4]}"
                                 for call in wrong) + f"\n{box.said()}")
    stored = through_store(box, before, NEXT)
    say(f"        {NEXT} ready by itself, then the button: {NEW} -> {NEXT} at its first try with three callers of `cad` "
        "every 50 ms all along, from "
        f"{min(call[0] for call in calls) - switch:+.1f} s to {max(call[1] for call in calls) - switch:+.1f} s around "
        f"the switch: {tally}")
    if failed:
        say("        each failure within " + ", ".join(f"{call[0] - switch:+.2f} s" for call in failed)
            + " of the switch")
    say(f"        {viewer(box, NEXT, before.env, stored)}")


# A child Python that opens the files it is given and keeps them open until its input ends (``self-held``): on Windows
# a file a process holds open cannot be deleted or replaced.
HOLD = "import sys\nheld = [open(path, 'rb') for path in sys.argv[1:]]\nprint('held', flush=True)\nsys.stdin.read()\n"


def self_held(box: Box) -> None:
    box.set_up("off")
    before = uv_installed(box)
    box.out(NEXT)
    typed_update(box, NEW, NEXT)
    stored = through_store(box, before, NEXT)
    # A file of the installed cad, and one of the release that runs, held open by another process for the whole update.
    held = [next(path for pattern in ("lib/python*/site-packages/cad_server/__init__.py",
                                      "Lib/site-packages/cad_server/__init__.py") for path in before.env.glob(pattern)),
            stored / "cad_server" / "__init__.py"]
    holder = subprocess.Popen([sys.executable, "-I", "-c", HOLD, *map(str, held)], env=box.env, cwd=box.work,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        if holder.stdout.readline().strip() != "held":
            raise Failed(f"{box.label}: the files could not be held: exit {holder.poll()}")
        box.out(AFTER)
        typed_update(box, NEXT, AFTER)
        through_store(box, before, AFTER)
        if holder.poll() is not None:
            raise Failed(f"{box.label}: the process holding the files ended before the update did")
    finally:
        holder.stdin.close()
        holder.wait(60)
    say(f"        {NEW} -> {NEXT}, then {NEXT} -> {AFTER} while {held[0].relative_to(box.work)} and "
        f"{held[1].relative_to(box.work)} were held open: installed all the same")


def self_reinstall(box: Box) -> None:
    box.set_up("off")
    before = uv_installed(box)
    box.out(NEXT)
    typed_update(box, NEW, NEXT)
    through_store(box, before, NEXT)
    # A person's own reinstall: uv's command, with this computer's releases. What uv installed runs, at once.
    box.run(["uv", "tool", "install", "--reinstall", "cad"], timeout=SECONDS)
    again = uv_installed(box)
    runs_its_own(box, again.env, again.release)
    say(f"        {NEW} -> {NEXT} through the store; then `uv tool install --reinstall cad` installed {again.release}, "
        "which runs at once from the environment's own packages: the pointer means nothing any more")
    # The next update points cad at the newest again.
    box.out(AFTER)
    typed_update(box, again.release, AFTER)
    through_store(box, again, AFTER)
    say(f"        then {again.release} -> {AFTER} through the store again")
    # A second computer: `uv tool upgrade cad` by hand over an update through the store.
    other = Box(f"{box.label}-2", box.feed, box.wheels, box.computer.uv, pypi=box.pypi, counted=True)
    say(f"  a second computer in {other.work}")
    try:
        other.computer.isolation(say)
        other.set_up("off")
        first = uv_installed(other)
        other.out(NEXT)
        typed_update(other, NEW, NEXT)
        through_store(other, first, NEXT)
        other.out(AFTER)
        other.run(["uv", "tool", "upgrade", "cad"], timeout=SECONDS)
        upgraded = uv_installed(other)
        if upgraded.release != AFTER:
            raise Failed(f"{other.label}: `uv tool upgrade cad` left uv's cad at {upgraded.release}, not {AFTER}")
        runs_its_own(other, upgraded.env, AFTER)
        say(f"        on it, {NEW} -> {NEXT} through the store, then `uv tool upgrade cad` by hand: uv's cad {AFTER}, "
            "which runs")
    finally:
        left = other.stop()
        if left:
            say(f"note    {other.label}: ended what was still running:\n" + "\n".join(left))
        shutil.rmtree(other.work, ignore_errors=True)


def worker_and_uv(box: Box, building: str) -> list[int]:
    """The update's worker (its command line names ``-m cad_server._internal.auto_update_helper``) and the uv it runs,
    building into the store's folder ``building``: their process ids, the worker's first."""
    found = []
    for pid, command in box.computer.processes():
        line = (rc.windows_command_line(pid) or "") if WINDOWS else command
        if "-m cad_server._internal.auto_update_helper" in line:
            found.insert(0, pid)
        elif building in line and "pip" in line:
            found.append(pid)
    return found


def self_stopped_midway(box: Box) -> None:
    box.set_up("off")
    before = uv_installed(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    box.hour_later()
    first = box.ask(python, "status") or {}
    store = box.state / "store"
    # The worker and its uv, stopped once uv builds the release in a folder of the store (looked for at once, often:
    # a build from uv's cache takes seconds).
    deadline, ended = time.monotonic() + SECONDS, []
    while not ended:
        if time.monotonic() > deadline:
            raise Failed(f"{box.label}: uv never seen building the next release\n{box.said()}")
        building = next((path.name for path in (store.glob(".building-*") if store.is_dir() else [])), None)
        found = worker_and_uv(box, building) if building else []
        if len(found) >= 2:
            for pid in found:
                try:
                    if WINDOWS:
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
                    else:
                        os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            ended = found
        time.sleep(0.02)
    box.until(lambda: not worker_and_uv(box, building), "the update's worker and its uv gone", seconds=60)
    record = box.read("auto-update.json")
    if (record.get("outcome"), record.get("phase"), record.get("release")) != ("underway", "building", NEXT):
        raise Failed(f"{box.label}: the update was not stopped while uv built: {record}\n{box.said()}")
    # Nothing that runs was touched: the same server process answers, the release installed, no pointer.
    after = box.ask(python, "status") or {}
    if (after.get("pid"), after.get("version")) != (first.get("pid"), NEW) or not first.get("pid"):
        raise Failed(f"{box.label}: the server before the worker was stopped {first}, after {after}\n{box.said()}")
    runs_its_own(box, before.env, NEW)
    no_pointer(box, before.env)
    # Twenty minutes pass with no beat from the stopped worker: the attempt is lost (its last beat set back, as the
    # feed's stamp is set back for an hour).
    _keep(box.state / "auto-update.json", {**record, "beat": time.time() - LOST_SECONDS})
    cause = box.run([python, "-c", CAUSE], check=False, timeout=60).stdout.strip()
    if cause != "lost":
        raise Failed(f"{box.label}: the stopped attempt, silent past the wait, is taken as {cause!r}, not lost")
    # A typed `cad update` then installs the release, and counts the attempt before as lost.
    typed_update(box, NEW, NEXT)
    through_store(box, before, NEXT)
    tried = (box.read("tried").get("tried") or {}).get(NEXT) or {}
    if tried.get("cause") != "lost":
        raise Failed(f"{box.label}: the tries of {NEXT}: {tried}")
    say(f"        the worker and its uv stopped while uv built {NEXT} (processes {ended}): the {NEW} server "
        f"(pid {first.get('pid')}) never stopped, no pointer, cad {NEW} runs; silent past the wait, the attempt is "
        f"lost; then a typed `cad update` installed {NEXT}, the try before kept as lost")


def _keep(path: Path, record: dict) -> None:
    """``record`` written whole in place of ``path``, as cad writes its records."""
    staged = path.with_name(f".{path.name}.{os.getpid()}")
    staged.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(staged, path)


def self_hop(box: Box) -> None:
    """``SHIPPED``, installed from PyPI as uv's tool, updates itself the old way into this tree (its helper runs
    uv's upgrade of the tool), and from there this tree updates through the store."""
    box.out(SHIPPED)  # out on PyPI, whose own file it is
    box.run(["uv", "tool", "install", "--managed-python", "--python", "3.14", f"cad=={SHIPPED}"], timeout=1500)
    box.is_tool(SHIPPED)
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {SHIPPED}" not in started:
        raise Failed(f"{box.label}: {SHIPPED}'s cad server start said {started!r}")
    env = Path(box.tool()["env"])
    box.out(NEW)
    done = box.run([box.cad(), "update"], check=False, timeout=SECONDS + 300)
    if done.returncode != 0 or f"cad {SHIPPED} updated to {NEW}" not in done.stdout:
        raise Failed(f"{box.label}: {SHIPPED}'s cad update exited {done.returncode}:\n{done.stdout}\n{done.stderr}\n"
                     f"{box.said()}")
    # The old way: uv's tool itself is this tree's release now, and nothing points anywhere.
    box.is_tool(NEW)
    runs_its_own(box, env, NEW)
    no_pointer(box, env)
    serves(box, env, NEW)
    say(f"        {SHIPPED}'s own `cad update` upgraded uv's tool in place to {NEW}: uv lists {NEW}, no pointer, "
        f"its server answers")
    # From there, through the store.
    before = uv_installed(box)
    box.out(NEXT)
    typed_update(box, NEW, NEXT)
    stored = through_store(box, before, NEXT)
    say(f"        then {NEW} -> {NEXT} through the store ({stored.name}): uv still lists {NEW}")


# --- a release that is ready --------------------------------------------------------------------------------------

# How far ``self-ready-busy`` sets back the end of the attempt that got a release ready: a day and a minute, past any
# rule by how long a release has been ready.
DAY_SECONDS = 86400.0 + 60.0


class Page:
    """A viewer page open on the computer's port, and shown: it asks ``GET /api/v1/server`` every ``every`` seconds, as
    a visible page asks the server something every couple of seconds, and runs no command, until ``stop``. ``seen``:
    the release each question was answered by, None where none answered."""

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
    as one (it is no rehearsal's look, ``ASK``), whether a server answers or not, until ``stop``. ``ran``: when each
    one a server answered ended (``time.time``)."""

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


def still_ready(box: Box, env: Path, ready: dict, button: str) -> None:
    """The release ``ready`` names (its record) still ready and switched to by nothing: the record as it was, and the
    release it began from still the one that runs (its server and ``cad --version``); the viewer's button in state
    ``button`` (``ready``, where it offers the restart)."""
    was = ready["from"]
    now = box.ask(rc.interpreter(env), "status") or {}
    status, answer = box.http("GET", "/api/v1/server")
    if box.read("auto-update.json") != ready or now.get("version") != was or box.version() != f"cad {was}" \
            or (status, (answer.get("cadUpdate") or {}).get("state")) != (200, button):
        raise Failed(f"{box.label}: {ready['release']} ready, never switched to: the record {box.read('auto-update.json')}, "
                     f"the server {now}, cad --version {box.version()!r}, GET /api/v1/server {status} {answer}\n"
                     f"{box.said()}")


def self_ready_busy(box: Box) -> None:
    """A server never left alone, as an agent at work and an open page keep it: a page asking every 2 s and a command
    every 3 s throughout. The release still gets ready at once, nothing restarts by itself however long it has been
    ready, and the server's next start is the switch."""
    box.set_up("off")
    before = uv_installed(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    page, commands = Page(box), Commands(box)
    try:
        box.hour_later()
        first = box.ask(python, "status") or {}
        up = time.time() - (first.get("up") or 0)
        ready = made_ready(box, before.env, NEW, NEXT, first)
        checked = box.read("releases.json").get("checked") or 0
        if not 0 <= ready["at"] - checked <= 3 * TEND_SECONDS + 10:
            raise Failed(f"{box.label}: the feed read at {checked:.1f}, the attempt begun at {ready['at']:.1f}: not at "
                         f"once\n{box.said()}")
        earlier = sum(1 for at in list(commands.ran) if up <= at <= ready["at"])
        # Ready, the page and the commands going on: ten tendings, then the release ready a day (its record's `ended`
        # set back: the server writes no record of a release that is ready), and ten more: nothing restarts.
        def ten_tendings() -> None:
            since = (box.ask(python, "status") or {}).get("up") or 0
            box.until(lambda: ((box.ask(python, "status") or {}).get("up") or 0) > since + 10 * TEND_SECONDS + 1,
                      "ten tendings more")

        ten_tendings()
        still_ready(box, before.env, ready, "ready")
        _keep(box.state / "auto-update.json", {**ready, "ended": ready["ended"] - DAY_SECONDS})
        ready = box.read("auto-update.json")
        ten_tendings()
        still_ready(box, before.env, ready, "ready")
        now = box.ask(python, "status") or {}
        if now.get("pid") != first.get("pid"):
            raise Failed(f"{box.label}: the server restarted by itself: {first}, now {now}\n{box.said()}")
        asked, called = len(page.seen), len(commands.ran)
        say(f"        {NEXT} ready by itself beside {NEW} {ready['at'] - checked:.1f} s after the feed was read, "
            f"commands answered before it began: {earlier}; ready a day too, then twenty tendings with a page asking "
            f"every 2 s ({asked} times) and a command every 3 s ({called} answered): the same {NEW} server (pid "
            f"{first.get('pid')}), still ready, nothing counted")
        # The next start is the switch, the page and the commands going on.
        _record, line = restarted_at_start(box, before.env, NEW, NEXT, ready)
    finally:
        seen, ran = page.stop(), commands.stop()
    through_store(box, before, NEXT)
    say(f"        then {line}; {NEW} -> {NEXT} through the store (the page asked {len(seen)} times, {len(ran)} commands "
        "answered)")
    pages(box, NEXT)


def self_ready_waits(box: Box) -> None:
    """A release that is ready and never switched to by itself: with automatic updates off, at a start; with them on
    again, at a start where the feed as last read stopped calling for it, or still says so after the feed named it
    again; then, the feed read naming it, the next start is the switch."""
    box.set_up("off")
    before = uv_installed(box)
    python = rc.interpreter(before.env)
    box.out(NEXT)
    box.hour_later()
    ready = made_ready(box, before.env, NEW, NEXT, box.ask(python, "status") or {})
    # Automatic updates off: a start starts the release before; the button still offers the restart.
    switched = box.run([box.cad(), "update", "auto", "off"]).stdout.strip()
    if switched != "update auto: off":
        raise Failed(f"{box.label}: cad update auto off said {switched!r}")
    box.run([box.cad(), "server", "stop"])
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start with automatic updates off said {started!r}\n{box.said()}")
    still_ready(box, before.env, ready, "ready")
    say(f"        {NEXT} ready by itself; then automatic updates off: `cad server start` said {started!r}, still "
        "ready, and the button offers the restart")
    # On again, but the feed, as last read, no longer names it: a start starts the release before, and the button
    # offers nothing.
    switched = box.run([box.cad(), "update", "auto", "on"]).stdout.strip()
    if switched != "update auto: on":
        raise Failed(f"{box.label}: cad update auto on said {switched!r}")
    box.run([box.cad(), "server", "stop"])
    box.taken_back(NEXT)
    feed_read(box, NEW)
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: cad server start with {NEXT} taken back said {started!r}\n{box.said()}")
    still_ready(box, before.env, ready, "idle")
    say(f"        automatic updates on, the feed read naming {NEXT} no more: `cad server start` said {started!r}, "
        "still ready, the button idle")
    # The feed names it again, and an hour passes: that start still goes by the feed as last read, and starts the
    # release before; the server then reads the feed.
    box.out(NEXT)
    box.hour_later()
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == NEXT and
              time.time() - box.read("releases.json").get("checked", 0) < 600, "the server reading the feed")
    tendings(box, before.env, 2)
    still_ready(box, before.env, ready, "ready")
    # The next start is the switch.
    _record, line = restarted_at_start(box, before.env, NEW, NEXT, ready)
    through_store(box, before, NEXT)
    say(f"        the feed naming it again, read by the server: {line}; {NEW} -> {NEXT} through the store")


def self_ready_rollback(box: Box) -> None:
    """A release whose server cannot start, got ready by itself, then switched to at the server's next start: cad goes
    back by itself, and that release is held back."""
    box.set_up("off")
    env = Path(box.tool()["env"])
    python = rc.interpreter(env)
    box.out(NOSTART)
    box.hour_later()
    ready = made_ready(box, env, NEW, NOSTART, box.ask(python, "status") or {})
    box.run([box.cad(), "server", "stop"])
    began = time.monotonic()
    done = box.run([box.cad(), "server", "start"], check=False)
    took = time.monotonic() - began
    then = box.ask(python, "status") or {}
    record = updated(box, NOSTART, "failed", after=ready)
    said = (done.stdout.strip().splitlines() or [""])[-1] if done.returncode == 0 else \
        (done.stderr.strip().splitlines() or [""])[-1]
    if (record.get("cause"), record.get("restored"), record.get("asked"), record.get("tries")) != (
            "start_failed", True, False, 1) or str(record.get("started", "")).startswith("not started"):
        raise Failed(f"{box.label}: the way back: {record}\n{box.said()}")
    # The start ended with a server of the release before running; it serves the pages again, and the environment
    # runs its own cad.
    if then.get("version") != NEW:
        raise Failed(f"{box.label}: `cad server start` exited {done.returncode} in {took:.1f} s ({said!r}) with the "
                     f"server {then}, not {NEW}'s\n{box.said()}")
    box.until(lambda: box.serving(NEW), f"{NEW} serving again on the pages' port with their token")
    serves(box, env, NEW)
    runs_its_own(box, env, NEW)
    no_pointer(box, env)
    box.until(lambda: box.read("auto-update.json").get("reported") is True,
              "the failed update counted by the old server")
    say(f"        {NOSTART}, whose server cannot start, ready by itself; `cad server start` began the switch, exited "
        f"{done.returncode} in {took:.1f} s ({said!r}) with {NEW}'s server running; cause start_failed, restored; "
        f"{NEW} serves the pages' port again, no pointer; the failure counted")
    # Held back: an hour passes with the feed naming it, two tendings, and another start: no attempt began.
    failed = box.read("auto-update.json")
    box.hour_later()
    box.until(lambda: (box.read("releases.json").get("feed") or {}).get("latest") == NOSTART and
              time.time() - box.read("releases.json").get("checked", 0) < 600, "the server reading the feed")
    tendings(box, env, 2)
    box.run([box.cad(), "server", "stop"])
    started = box.run([box.cad(), "server", "start"]).stdout.strip()
    if box.read("auto-update.json").get("at") != failed.get("at") or started != STARTED.format(release=NEW):
        raise Failed(f"{box.label}: {NOSTART}, whose server did not start, was tried again by itself ({started!r}): "
                     f"{box.read('auto-update.json')}\n{box.said()}")
    say(f"        an hour later, the feed naming {NOSTART}, two tendings and a start: not tried again by itself")


def self_ready_damaged(box: Box) -> None:
    """A release that is ready, a file of it gone before the restart: the server's next start resumes the attempt, the
    worker finds the release no longer runs and builds it again, then switches to it."""
    box.set_up("off")
    before = uv_installed(box)
    box.out(NEXT)
    box.hour_later()
    ready = made_ready(box, before.env, NEW, NEXT, box.ask(rc.interpreter(before.env), "status") or {})
    stored = next((box.state / "store").glob(f"{NEXT}-*"))
    gone = stored / "cad_server" / "cli" / "update.py"  # a module its own check imports
    gone.unlink()
    box.run([box.cad(), "server", "stop"])
    began = time.monotonic()
    done = box.run([box.cad(), "server", "start"], check=False)
    took = time.monotonic() - began
    record = updated(box, NEXT, after=ready)
    log = (box.state / "auto-update.log").read_text(encoding="utf-8", errors="replace")
    said = done.stdout.strip()
    if done.returncode != 0 or said not in (UPDATED.format(release=NEXT, was=NEW), STARTED.format(release=NEW)):
        raise Failed(f"{box.label}: cad server start with {NEXT} ready but damaged exited {done.returncode}:\n"
                     f"{done.stdout}\n{done.stderr}\n{box.said()}")
    if (record.get("asked"), record.get("tries")) != (False, 1) or ".building-" not in log:
        raise Failed(f"{box.label}: the switch to {NEXT}, damaged: {record}; its log:\n{log[-3000:]}\n{box.said()}")
    through_store(box, before, NEXT)
    if not gone.is_file():
        raise Failed(f"{box.label}: {NEXT} switched to without {gone.relative_to(stored)}")
    say(f"        {NEXT} ready, then {gone.relative_to(stored).as_posix()} of it gone; `cad server start` said "
        f"{said!r} in {took:.1f} s; the worker built it again and switched to it: {NEW} -> {NEXT} through the store, "
        "at the same try")


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


def pipx_is(box: Box, env: Path, version: str) -> Installed:
    """pipx's cad at ``version``, as pipx installed it: its metadata says so, the ``cad`` command in the bin folder is
    pipx's (a link into its environment; on Windows pipx's copy), it says ``cad <version>``, and uv has no cad tool
    beside it. What pipx made (``Installed``)."""
    try:
        held = json.loads((env / "pipx_metadata.json").read_text(encoding="utf-8"))["main_package"]["package_version"]
    except (OSError, ValueError, KeyError) as error:
        raise Failed(f"{box.label}: pipx's cad has no metadata: {error}\n{pipx_said(box)}") from None
    command = box.cad()
    linked = WINDOWS or (command.is_symlink() and rc._within(Path(os.path.realpath(command)), env))
    if held != version or not command.exists() or not linked or box.version() != f"cad {version}" or box.tool():
        raise Failed(f"{box.label}: pipx's cad is {held}, its command {command} (linked {linked}), cad --version says "
                     f"{box.version()!r}, uv's cad tool {box.tool()}; not {version}\n{pipx_said(box)}")
    return Installed(box, env, version, ["pipx", "list", "--short"], "pipx_metadata.json")


def self_pipx(box: Box) -> None:
    """cad installed by ``pipx install cad``: the install command, a person's run, finds nothing newer for it,
    installs no second cad, and has it turn the plugin's switch on; it updates itself through the store inside its
    major, as uv's does, never by pipx -- the release ready by itself, then its next start the switch (then ``cad
    plugin install`` once) --, and a typed ``cad update`` the same way, never across a major."""
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
    before = pipx_is(box, env, NEW)
    switches = box.read("settings.json")
    if (switches.get("plugin") or {}).get("auto_update") is not True or (switches.get("auto_update") or {}).get("on") \
            is False:
        raise Failed(f"{box.label}: after the install command: {switches}")
    started = box.run([box.cad(), "server", "start"]).stdout
    if f"cad {NEW}" not in started:
        raise Failed(f"{box.label}: cad server start said {started!r}")
    box.token = (box.ask(rc.interpreter(env), "http") or {}).get("token", "")
    serves(box, env, NEW)
    say(f"        `pipx install cad` gave {NEW}; the install command found nothing newer for it (no uv tool), and it "
        "turned the plugin's switch on")
    # By itself: an hour passes with the next release out, and a release of a higher major.
    box.out(NEXT)
    box.out(HIGH)
    box.hour_later()
    ready = made_ready(box, env, NEW, NEXT, box.ask(rc.interpreter(env), "status") or {})
    record, line = restarted_at_start(box, env, NEW, NEXT, ready)
    through_store(box, before, NEXT)
    if record.get("installer") != "pipx" or box.tool():
        raise Failed(f"{box.label}: the update of pipx's cad: {record}, uv's cad tool {box.tool()}")
    caught_up(box, NEXT)
    say(f"        {HIGH} and {NEXT} out: {NEXT} ready by itself, never {HIGH}; {line}; {NEW} -> {NEXT} through "
        f"the store; pipx still lists {NEW}, its metadata and the environment as pipx left them; then the new server "
        "ran `cad plugin install`, once, exit 0")
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
    through_store(box, before, AFTER)
    caught_up(box, AFTER)
    say(f"        `cad update` with nothing newer: 'cad {NEXT} is the newest {MAJOR}.x release' and {HIGH} named; then "
        f"{typed!r}, automatic updates off; then the new server ran `cad plugin install`, once more, exit 0")
    pages(box, AFTER)


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
        "self-at-start": self_at_start, "self-off": self_off, "self-rollback": self_rollback,
        "self-broken": self_broken, "self-unbuildable": self_unbuildable, "self-unrunnable": self_unrunnable,
        "self-major": self_major, "self-pipx": self_pipx, "self-called": self_called, "self-held": self_held,
        "self-reinstall": self_reinstall, "self-stopped-midway": self_stopped_midway, "self-hop": self_hop,
        "self-ready-busy": self_ready_busy, "self-ready-waits": self_ready_waits,
        "self-ready-rollback": self_ready_rollback, "self-ready-damaged": self_ready_damaged}
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
    rc.publish(base, UNRUNNABLE, out, replace={"cad_server/_internal/selftest.py": BROKEN_CHECK})


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
        f"cannot start, {AFTER}, {UNBUILDABLE} uv cannot install, {UNRUNNABLE} failing its own check; {HIGH} a "
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
