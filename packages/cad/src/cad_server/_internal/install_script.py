"""BRIDGE-ONLY: the hosted install command as cad runs it, once by the server for a computer a shipped updater
brought (install mode), and by ``cad setup`` (``cad_server.cli.setup``). ``cad plugin`` runs none of it.

This module names no app, plugin or skill. What it knows is one fixed public command, the hosted install command
(``curl -fsSL https://texttocad.dev/install.sh | sh``; on Windows PowerShell ``irm
https://www.texttocad.dev/install.ps1 | iex``), and the report that command writes where ``CAD_INSTALL_REPORT`` names
a file: whether its cad step ended 0 (``setup``) and whether any app's step failed (``apps``). Nothing else of the
report is read.

**Install mode** (BRIDGE-ONLY), owed by ``cad setup --engine-update`` (``owe``), which the updaters of 0.10.0 to 0.11.11
run: the command installs cad as a uv tool and our plugin in every agent app. Done, the server that runs from the
shipped updater's folder hands over to the uv tool's (``cad_server.cli.setup``).

**When** (``plan``): the first attempt once the server has run ``FIRST_SECONDS`` (five minutes) while
``installations/current`` names the release it is owed for -- longer than a shipped updater's switch can still be
deciding to go back from this server: its check can end, and go back, after the server's first tending; ``current``
naming a newer release first ends it (``superseded``). After an attempt that failed: at a server's start but not sooner
than ``RETRY_SECONDS`` (an hour) after the last began, then once every ``DAY_SECONDS`` while the server runs, by the wall
clock or the server's own monotonic one (a clock set back stalls nothing); at most ``ATTEMPTS`` (30) attempts, and none
once ``GIVE_UP_SECONDS`` (30 days) have passed since the first (``gave up``). Nothing of it blocks, delays or undoes
cad's own update, which the server asks for first.

**An attempt** (``Carrier.begin``): the command started by the server itself, detached (a session or process group of
its own, no window), its output nowhere, ``CAD_INSTALL_REPORT`` naming ``install-report.json`` in the state folder and
uv's own installer told to leave shell profiles alone (``UV_NO_MODIFY_PATH``). No process of cad's waits on it: a
server that stops leaves it running, and the next server judges its report. It is stopped, with what it started,
after ``RUN_SECONDS``; one the server that started it no longer watches is taken as failed then.

**Its outcome** (``judge``): ``done`` when the report says the cad step ended 0, whatever the apps' steps did; else
failed, by why: ``no_report`` (none written: the command could not be fetched, was stopped, or writes none), ``setup``
(its cad step failed) or ``other`` (the command could not start). The run is cad's: once cad is installed it is over.
Where the report also says the plugin's step failed (a value of its ``apps`` ``failed``: an app's, or the step's own,
``"plugin"``), that is left to cad's own retry of the plugin, as on any computer, and the computer is marked as owed a
run of it for the release this run was owed for (``plugin_catch_up.owe``), where ``cad plugin install`` did not mark it
itself; a run of that retry is never held back once this run is done (``plugin_catch_up.due``). 0.11.12 to 0.11.14 took
such a run for a failed one (``app``) and ran it again, hourly and then daily: a record of theirs that says so is
attempted again as any failed one, and that attempt is done once cad is there.

The record, ``handover.json`` in the state folder, one at a time: ``schema``, ``mode`` (``install``), ``version`` (the
release it is owed for), ``state`` (``owed``, ``done``, ``superseded``, ``gave up``), ``owed`` (when), ``attempts``,
``first`` and ``last`` (when the first and the last attempt began), ``outcome`` (the last attempt's: ``running`` while
it runs), ``installed`` (true once an attempt's report said cad was installed) and ``ended``; times are the wall
clock's, in seconds. Each attempt's end, and the end of the run, is one line in the server's log, and counted
(``analytics.arrival``, as the bridge's other steps are).

Every install command cad starts carries ``CAD_INSTALL_BY_CAD=1`` (``environment``), so a ``cad setup`` it reaches runs
nothing (``cad_server.cli.setup``): the hosted command of 0.10.0 to 0.11.11 runs one, and is served until the site is
redeployed.

``CAD_ENGINE_UPDATE_INSTALLER`` names a command to run instead of the hosted one (a test's stand-in), and empty, none:
nothing is attempted, and the server runs no ``cad plugin install`` by itself either (``plugin_catch_up.silenced``).
``CAD_ENGINE_UPDATE_FIRST_SECONDS`` sets install mode's wait (a test's computers).
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# What an attempt runs: a command line, split as a shell splits it; empty runs nothing.
INSTALLER_ENV = "CAD_ENGINE_UPDATE_INSTALLER"
INSTALLER = ("sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh")
INSTALLER_WINDOWS = ("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                     "irm https://www.texttocad.dev/install.ps1 | iex")
# What the command reads: where to write its report.
REPORT_ENV = "CAD_INSTALL_REPORT"
# The update mode of the install command of earlier builds, which no run of cad's asks for: never passed on to one.
UPDATE_ENV = "CAD_INSTALL_UPDATE"
# The mark of a command cad started (``environment``): a ``cad setup`` it reaches runs nothing (BRIDGE-ONLY).
BY_CAD_ENV = "CAD_INSTALL_BY_CAD"

RECORD = "handover.json"
REPORT = "install-report.json"
SCHEMA = "cad hand-over/2"
INSTALL = "install"
OWED, DONE, SUPERSEDED, GAVE_UP = "owed", "done", "superseded", "gave up"
RUNNING = "running"
# Why an attempt failed. ``app`` (an app's step failed, cad installed) is 0.11.12 to 0.11.14's, kept in their records:
# this release takes such an attempt as done (``judge``).
FAILURES = ("no_report", "setup", "app", "other")
ATTEMPT = "attempt"
# Install mode's wait before its first attempt: a shipped updater's switch (0.10.0 to 0.11.11, ``switch._started``)
# starts the new server waiting up to 60 seconds for its door, then asks its ``status`` and to serve pages on the old
# port, and goes back where either fails -- seconds after the door answers, with no bound of its own on those two
# asks --; the server first tends 30 seconds after it starts. Five minutes is that wait, those asks on a slow or busy
# computer, and a margin.
FIRST_SECONDS = 5 * 60.0
FIRST_ENV = "CAD_ENGINE_UPDATE_FIRST_SECONDS"
ATTEMPTS = 30
GIVE_UP_SECONDS = 30 * 24 * 60 * 60.0
RETRY_SECONDS = 60 * 60.0
DAY_SECONDS = 24 * 60 * 60.0
# How long the command may run before it is stopped, with what it started: a minute or two, a few more on a slow line;
# one that hangs (a prompt it should not show) would hold every later attempt.
RUN_SECONDS = 2 * 60 * 60.0


# --- the command --------------------------------------------------------------------------------------------------


def installer() -> list[str] | str:
    """What a run runs: ``CAD_ENGINE_UPDATE_INSTALLER``'s command where it is set (empty: none), else the hosted
    install command for this computer. On Windows the variable's command line is run as it is written, one string that
    Windows splits as its programs do: ``shlex`` there keeps a quoted word's quotes, naming a program that is not
    there."""
    if INSTALLER_ENV in os.environ:
        named = os.environ[INSTALLER_ENV].strip()
        return named if os.name == "nt" else shlex.split(named)
    return list(INSTALLER_WINDOWS if os.name == "nt" else INSTALLER)


def environment(*, report: Path | None) -> dict[str, str]:
    """The environment the command runs in: this process's, without its import path, the version it was told it runs
    as and a ``cad run``'s marks, with the person's own PATH (none of an environment that comes and goes,
    ``installations.lasting``), uv's installer told to leave shell profiles alone, cad's mark (``BY_CAD_ENV``), and the
    report's file named. The install command has no modes: an earlier build's update mode is never passed on."""
    from cad.engine.places import INSTALLATION_ENV, RUN_WITH
    from cad_server._internal.installations import lasting

    dropped = ("PYTHONPATH", "PYTHONHOME", INSTALLATION_ENV, RUN_WITH, "CAD_UPDATE_PREPARE", REPORT_ENV, UPDATE_ENV)
    found = {key: value for key, value in os.environ.items() if key not in dropped}
    found["PATH"] = lasting(os.environ.get("PATH", os.defpath))
    found["UV_NO_MODIFY_PATH"] = "1"
    found[BY_CAD_ENV] = "1"
    if report is not None:
        found[REPORT_ENV] = str(report)
    return found


# --- the record (BRIDGE-ONLY) ---------------------------------------------------------------------------------------


def _folder() -> Path:
    from cad.engine import places

    return places.state_dir()


def read() -> dict[str, Any] | None:
    """The record, or None where there is none of this schema."""
    try:
        found = json.loads((_folder() / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(found, dict) and found.get("schema") == SCHEMA and found.get("mode") == INSTALL
    return found if ok and isinstance(found.get("version"), str) else None


def _write(record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(folder / RECORD, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def _new(mode: str, version: str, now: float) -> dict[str, Any]:
    return {"schema": SCHEMA, "mode": mode, "version": version, "state": OWED, "owed": now, "attempts": 0,
            "first": None, "last": None, "outcome": None, "installed": False, "ended": None}


def owe(version: str, *, now: float | None = None) -> None:
    """BRIDGE-ONLY. Install mode owed for release ``version`` (``cad setup --engine-update``), unless it is owed for it
    already (an updater's second run keeps the attempts counted). ``OSError`` when it cannot be written."""
    found = read()
    if found is not None and (found["version"], found.get("state")) == (version, OWED):
        return
    _write(_new(INSTALL, version, time.time() if now is None else now))


def _count(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _time(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _later(one: str | None, other: str) -> bool:
    """Whether release ``one`` is later than ``other`` by its numbers (a development build ``X.Y.Z-dev.<stamp>`` is
    its release's)."""
    import re

    def numbers(text: str | None) -> tuple[int, ...]:
        found = re.match(r"[0-9]+(?:\.[0-9]+)*", text or "")
        return tuple(int(part) for part in found.group().split(".")) if found else ()

    a, b = numbers(one), numbers(other)
    size = max(len(a), len(b))
    return bool(a) and bool(b) and a + (0,) * (size - len(a)) > b + (0,) * (size - len(b))


# --- when ---------------------------------------------------------------------------------------------------------


def plan(record: dict[str, Any] | None, current: str | None, *, wall: float, mono: float, began: float,
         tried: float | None) -> str | None:
    """What the server does now with ``record`` (see the module): ``ATTEMPT``, ``SUPERSEDED``, ``GAVE_UP``, or None.
    ``current``: the release ``installations/current`` names; ``wall`` and ``mono``: now, by the wall clock and the
    monotonic one; ``began``: when the server started, ``tried``: when it last began an attempt, or None (monotonic).
    The caller has made sure no attempt is in flight."""
    if record is None or record.get("state") != OWED:
        return None
    attempts, first, last = _count(record.get("attempts")), _time(record.get("first")), _time(record.get("last"))
    if attempts == 0 or last is None:
        if current is not None and _later(current, record["version"]):
            return SUPERSEDED
        if current != record["version"]:  # switched back to the release before, or not switched yet
            return None
        return ATTEMPT if mono - began >= first_seconds() else None
    if attempts >= ATTEMPTS or (first is not None and wall - first >= GIVE_UP_SECONDS):
        return GAVE_UP
    gap, since = (RETRY_SECONDS, began) if tried is None else (DAY_SECONDS, tried)
    return ATTEMPT if wall - last >= gap or mono - since >= gap else None


def first_seconds() -> float:
    """Install mode's wait: ``FIRST_SECONDS``, or what ``CAD_ENGINE_UPDATE_FIRST_SECONDS`` names (a test's)."""
    try:
        return max(0.0, float(os.environ[FIRST_ENV]))
    except (KeyError, ValueError):
        return FIRST_SECONDS


def judge(report: Path) -> tuple[str, bool, bool]:
    """An attempt's outcome by the report at ``report`` (see the module) -- ``done``, ``no_report`` or ``setup`` --,
    whether it says cad was installed (its cad step ended 0), and whether, done, it says the plugin's step failed (a
    value of its ``apps`` ``failed``), which is cad's own retry's to run again."""
    try:
        found = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "no_report", False, False
    steps = found.get("apps") if isinstance(found, dict) else None
    if not isinstance(steps, dict):
        return "no_report", False, False
    if found.get("setup") != 0 or isinstance(found.get("setup"), bool):
        return "setup", False, False
    return DONE, True, any(status == "failed" for status in steps.values())


# How long ``_stop`` lets taskkill run, and then waits for the process itself to be gone.
STOP_SECONDS = 30.0


def _stop(process: subprocess.Popen, *, windows: bool = os.name == "nt", seconds: float = STOP_SECONDS) -> bool:
    """``process`` stopped with every process it started (its own session; on Windows its tree, ``taskkill /T``):
    True; or, where that could not be done (on Windows taskkill refused -- "Access denied" in a session with no
    interactive logon, SSH or a service --, failed or did not end within ``seconds``), the process itself alone
    (``kill``): False, and what it started may run on. Never waits for ever (each step bounded by ``seconds``), never
    raises."""
    whole = False
    try:
        if windows:
            done = subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=seconds, check=False)
            whole = done.returncode == 0
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # nothing left of its session
            whole = True
    except (OSError, subprocess.SubprocessError):
        whole = False
    try:
        if process.poll() is None and not whole:
            process.kill()
        process.wait(seconds)
    except (OSError, subprocess.SubprocessError):
        pass
    return whole


class Carrier:
    """BRIDGE-ONLY. The server's side, at each tending (``tend``): the attempt it began last (its process) and when
    (monotonic), and when the server started."""

    def __init__(self, began: float) -> None:
        self.began = began
        self.tried: float | None = None
        self.process: subprocess.Popen | None = None

    def tend(self, name: str, told: Callable[[str], None], *, mono: float | None = None,
             wall: float | None = None) -> str | None:
        """The run this server, release ``name``, owes looked after: its own attempt watched, and judged as it ends;
        one an earlier server began judged once its report is there, or ``RUN_SECONDS`` have passed; then what
        ``plan`` says done. What it did: ``plan``'s answer, or None."""
        mono = time.monotonic() if mono is None else mono
        wall = time.time() if wall is None else wall
        report = _folder() / REPORT
        if self.process is not None:
            if self.process.poll() is None:
                if self.tried is None or mono - self.tried < RUN_SECONDS:
                    return None
                _stop(self.process)
            self.process = None
            record = read()
            if record is not None and record.get("outcome") == RUNNING:
                self.judged(record, report, told, wall)
        record = read()
        if record is not None and record.get("outcome") == RUNNING:  # an earlier server's attempt
            if not report.exists() and wall - (_time(record.get("last")) or 0.0) < RUN_SECONDS:
                return None
            self.judged(record, report, told, wall)
            record = read()
        if record is None or not installer():
            return None
        if _later(record["version"], name):
            return None  # owed for a later release than this server's: that release's server carries it out
        from cad_server._internal import installations

        step = plan(record, installations.current_version(), wall=wall, mono=mono, began=self.began, tried=self.tried)
        if step in (SUPERSEDED, GAVE_UP):
            record.update(state=step, ended=wall)
            _write(record)
            ended(record, "superseded" if step == SUPERSEDED else "gave_up", told)
        elif step == ATTEMPT:
            self.begin(record, report, told, wall, mono)
        return step

    def begin(self, record: dict[str, Any], report: Path, told: Callable[[str], None], wall: float,
              mono: float) -> None:
        """An attempt begun (see the module): recorded, then the command started; one that cannot start is failed
        (``other``) at once."""
        from cad.engine.places import detached

        self.tried = mono
        record.update(attempts=_count(record.get("attempts")) + 1, last=wall,
                      first=_time(record.get("first")) or wall, outcome=RUNNING)
        try:
            report.unlink(missing_ok=True)
            _write(record)
            self.process = subprocess.Popen(installer(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, env=environment(report=report), **detached())
        except (OSError, ValueError) as error:
            told(f"the install command could not start: {error}")
            self.end(record, "other", False, told, wall)

    def judged(self, record: dict[str, Any], report: Path, told: Callable[[str], None], wall: float) -> None:
        """The attempt ended, judged by its report (``judge``): ended (``end``), and, done with the plugin's step
        failed, cad's own retry of the plugin owed a run (``plugin_catch_up.owe``, see the module)."""
        outcome, installed, left = judge(report)
        self.end(record, outcome, installed, told, wall)
        if outcome == DONE and left:
            from cad_server._internal import plugin_catch_up

            try:
                plugin_catch_up.owe(record["version"])
            except OSError as error:
                told(f"an agent app's step failed, and could not be marked to run again: {error}")
                return
            told("an agent app's step failed: cad runs that step again later, by itself")

    def end(self, record: dict[str, Any], outcome: str, installed: bool, told: Callable[[str], None],
            wall: float) -> None:
        """An attempt's ``outcome`` kept and told; done, the run is over."""
        record["outcome"] = outcome
        record["installed"] = bool(record.get("installed")) or installed
        if outcome == DONE:
            record.update(state=DONE, ended=wall)
        _write(record)
        ended(record, DONE if outcome == DONE else "failed", told, why=None if outcome == DONE else outcome)


def ended(record: dict[str, Any], outcome: str, told: Callable[[str], None], *, why: str | None = None) -> None:
    """An attempt ended (``outcome`` ``done``, or ``failed`` and ``why``), or the run did (``gave_up``,
    ``superseded``): one line to ``told`` (the server's log), and counted (``analytics.arrival``, by the version it
    came from its arrival record keeps)."""
    name, attempts = record["version"], _count(record.get("attempts"))
    what = f"the install command, owed for cad {name}"
    if outcome == DONE:
        told(f"{what}: done (attempt {attempts})")
    elif outcome == "failed":
        told(f"{what}: attempt {attempts} of at most {ATTEMPTS} failed ({why}); it runs again later")
    elif outcome == "gave_up":
        told(f"{what}: given up after {attempts} attempts")
    else:
        told(f"{what}: a later cad took over, after {attempts} attempts")
    from cad_server import analytics
    from cad_server._internal import arrival

    came = (arrival.read(name) or {}).get("from")
    analytics.arrival("handover", route=arrival.UPDATER, earlier=came if isinstance(came, str) else None,
                      outcome=outcome, reason=why, attempts=attempts)
