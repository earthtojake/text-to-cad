"""The hand-over a version owes the computer a shipped updater brought it to: the hosted install script, run by the
version's own server until it has worked.

The updaters of 0.10.0 to 0.11.10 bring a computer cad alone (``cad setup --engine-update``, ``cad_server.cli.setup``);
the rest of what the install command does on a computer comes only with the hosted install script. So
``--engine-update`` owes that run: it writes the record ``handover.json`` in the version's data folder (``owe``) and
starts nothing. The version's own server carries it out, from its tending (``Carrier``, ``cad_server.engine.daemon``):

- **When** (``plan``): only while ``installations/current`` names the version. The shipped updater's switch points it
  there once the version's server answers on the pages' port, and back at the release before when it does not, so a
  version whose server cannot start, or that its updater went back from, never runs the script. One attempt at a time
  on the computer: ``handover.lock`` in the state folder, held by the attempt as long as it runs. The first once the
  server has run ``FIRST_SECONDS`` (five minutes): longer than any shipped switch can still be deciding whether this
  server took over -- its check of the new server can end, and go back, after the server's first tending --; after one
  that failed, at the server's next start but not sooner
  than ``RETRY_SECONDS`` (an hour) after it began, then once every ``DAY_SECONDS`` while the server runs, by the wall
  clock or by the server's own monotonic one (a clock set back stalls nothing); at most ``ATTEMPTS`` (30) attempts,
  and none once ``GIVE_UP_SECONDS`` (30 days) have passed since the first: then it gives up for good (``gave up``).
  A newer version that ``current`` names has taken over: the hand-over is over (``superseded``).
- **An attempt** (``main``): a program of the version's Python, started detached, its output nowhere, never waited
  on. It waits until the site's ``install.py`` -- what the hosted ``install.sh`` and ``install.ps1`` download and run
  -- names this release or a later one as its fallback (``wait``: about an hour; the site is deployed after the
  version feed names a release), then runs the hosted install script (``installer``: ``curl -fsSL
  https://texttocad.dev/install.sh | sh``, on Windows PowerShell ``irm https://www.texttocad.dev/install.ps1 | iex``)
  with ``CAD_INSTALL_REPORT`` naming ``install-report.json`` in the version's data folder, in the server's own
  environment and ``PATH``.
- **Its outcome** (``judge``): ``done`` when the script wrote that report during the attempt, its ``cad setup``
  exited 0 and no step it reports failed. Anything else is a failed attempt, by why: ``no_report`` (the script never
  ran, could not be fetched, was stopped -- after ``RUN_SECONDS`` at most --, or writes no report), ``setup`` (its
  ``cad setup`` failed), ``app`` (a step it reports failed) or ``other`` (the site never named the release within the
  wait, or ``current`` moved on before the script ran). Nothing else of the report is read.

The record: ``schema``, ``version``, ``state`` (``owed``, ``done``, ``superseded``, ``gave up``), ``owed`` (when),
``attempts``, ``first`` and ``last`` (when the first and the last attempt began), ``outcome`` (the last attempt's:
``running`` while it runs, then as above), ``told`` (the attempts whose end the server has told) and ``ended``;
times are the wall clock's, in seconds. The server tells each attempt's end once, and the end of the hand-over
(``ended``: counted, and one line in the server's log).

``CAD_ENGINE_UPDATE_INSTALLER`` names a command to run instead of the hosted script (a test's stand-in), and empty,
none: nothing is attempted. ``CAD_ENGINE_UPDATE_FIRST_SECONDS`` sets how long a server runs before its first attempt
(a test's computers). ``CAD_ENGINE_UPDATE_INSTALL_PY`` names the ``install.py`` an attempt waits for (a test's
own server), and empty, none, as a command ``CAD_ENGINE_UPDATE_INSTALLER`` names waits for none unless it is set.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

# The program the hosted install script downloads and runs, whose fallback release says which release it installs.
URL = "https://www.texttocad.dev/install.py"
# The delays between asks of the site, in seconds: growing, about an hour in all, then the attempt gives up.
DELAYS = (15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 600.0, 600.0, 600.0, 600.0)
ASK_SECONDS = 20.0
MOST_BYTES = 1 << 20
FALLBACK = re.compile(r'^FALLBACK = "([0-9][0-9A-Za-z.+_-]*)"[ \t]*$', re.M)
# What an attempt runs: a command line, split as a shell splits it; empty runs nothing.
INSTALLER_ENV = "CAD_ENGINE_UPDATE_INSTALLER"
INSTALLER = ("sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh")
INSTALLER_WINDOWS = ("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                     "irm https://www.texttocad.dev/install.ps1 | iex")
# The ``install.py`` an attempt waits for, once it names this release: its address.
INSTALL_PY_ENV = "CAD_ENGINE_UPDATE_INSTALL_PY"
# Where the hosted install script writes what it did: a report, of what it installed, ``cad setup``'s exit status and
# each step's status (``judge`` reads the setup's status and whether any step failed).
REPORT_ENV = "CAD_INSTALL_REPORT"

RECORD = "handover.json"
REPORT = "install-report.json"
LOCK = "handover.lock"
SCHEMA = "cad hand-over/1"
OWED, DONE, SUPERSEDED, GAVE_UP = "owed", "done", "superseded", "gave up"
# An attempt's outcome: running, done, or why it failed.
RUNNING = "running"
FAILURES = ("no_report", "setup", "app", "other")
# ``plan``'s answer for an attempt now.
ATTEMPT = "attempt"
# How long a server runs before its first attempt: a shipped updater's switch (0.10.0 to 0.11.10, ``switch._started``)
# starts the new server waiting up to ``START_SECONDS`` (60) for its door, then asks its ``status`` and to serve pages
# on the old port, and goes back where either fails -- seconds after the door answers, with no bound of its own on
# those two asks --; the server first tends ``TEND_SECONDS`` (30) after it starts. Five minutes is that wait, those
# asks on a slow or busy computer, and a margin. ``CAD_ENGINE_UPDATE_FIRST_SECONDS`` sets it for a test's computers.
FIRST_SECONDS = 5 * 60.0
FIRST_ENV = "CAD_ENGINE_UPDATE_FIRST_SECONDS"
ATTEMPTS = 30
GIVE_UP_SECONDS = 30 * 24 * 60 * 60.0
RETRY_SECONDS = 60 * 60.0
DAY_SECONDS = 24 * 60 * 60.0
# How long the install script may run before it is stopped, with what it started: it takes a minute or two, a few
# more on a slow line; one that hangs (a prompt it should not show) would hold the lock and stop every later attempt.
RUN_SECONDS = 2 * 60 * 60.0
# How often an attempt waiting for the site looks whether ``installations/current`` still names its version.
LOOK_SECONDS = 1.0


# --- the record ---------------------------------------------------------------------------------------------------


def _path(name: str) -> Path:
    from cad.engine import places

    return places.data_dir(name) / RECORD


def read(name: str) -> dict[str, Any] | None:
    """Version ``name``'s hand-over record, or None where there is none of this schema."""
    try:
        found = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("schema") == SCHEMA else None


def _write(name: str, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def owe(name: str, *, now: float | None = None) -> None:
    """The hand-over owed for version ``name`` (``--engine-update``): its record written, unless one is owed already
    (an updater's second run keeps the attempts counted). ``OSError`` when it cannot be."""
    found = read(name)
    if found is not None and found.get("state") == OWED:
        return
    _write(name, {"schema": SCHEMA, "version": name, "state": OWED, "owed": time.time() if now is None else now,
                  "attempts": 0, "first": None, "last": None, "outcome": None, "told": 0, "ended": None})


def _count(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _time(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# --- when ---------------------------------------------------------------------------------------------------------


def plan(record: dict[str, Any] | None, name: str, current: str | None, *, wall: float, mono: float, began: float,
         tried: float | None) -> str | None:
    """What version ``name``'s server does now with its hand-over ``record`` (see the module): ``ATTEMPT``,
    ``SUPERSEDED``, ``GAVE_UP``, or None (nothing). ``current``: the version ``installations/current`` names;
    ``wall`` and ``mono``: now, by the wall clock and the monotonic one; ``began``: when the server started, ``tried``:
    when it last started an attempt, or None (monotonic). The caller has made sure no attempt is in flight."""
    from cad_server._internal import versions

    if record is None or record.get("state") != OWED:
        return None
    if current is not None and current != name and versions.older(name, current):
        return SUPERSEDED
    if current != name:  # switched back to the release before, or not switched yet
        return None
    attempts, first, last = _count(record.get("attempts")), _time(record.get("first")), _time(record.get("last"))
    if attempts == 0 or last is None:
        return ATTEMPT if mono - began >= first_seconds() else None
    if attempts >= ATTEMPTS or (first is not None and wall - first >= GIVE_UP_SECONDS):
        return GAVE_UP
    gap, since = (RETRY_SECONDS, began) if tried is None else (DAY_SECONDS, tried)
    return ATTEMPT if wall - last >= gap or mono - since >= gap else None


def first_seconds() -> float:
    """How long a server runs before its first attempt: ``FIRST_SECONDS``, or what ``CAD_ENGINE_UPDATE_FIRST_SECONDS``
    names (a test's computers)."""
    try:
        return max(0.0, float(os.environ[FIRST_ENV]))
    except (KeyError, ValueError):
        return FIRST_SECONDS


def _lock() -> Path:
    from cad.engine import places

    folder = places.state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / LOCK


def in_flight() -> bool:
    """Whether an attempt holds the computer's hand-over lock now: looked at, never waited for."""
    from cad_server._internal.file_lock import attempt

    with attempt(_lock()) as free:
        return not free


def installer() -> list[str] | str:
    """What an attempt runs: ``CAD_ENGINE_UPDATE_INSTALLER``'s command where it is set (empty: none), else the hosted
    install script for this computer. On Windows the variable's command line is run as it is written, one string that
    Windows splits as its programs do: ``shlex`` there keeps a quoted word's quotes, naming a program that is not
    there."""
    if INSTALLER_ENV in os.environ:
        named = os.environ[INSTALLER_ENV].strip()
        return named if os.name == "nt" else shlex.split(named)
    return list(INSTALLER_WINDOWS if os.name == "nt" else INSTALLER)


def install_py() -> str | None:
    """The ``install.py`` whose fallback release an attempt waits for: ``CAD_ENGINE_UPDATE_INSTALL_PY``'s where it is
    set (empty: none), else none for a command ``CAD_ENGINE_UPDATE_INSTALLER`` names, else the site's."""
    if INSTALL_PY_ENV in os.environ:
        return os.environ[INSTALL_PY_ENV].strip() or None
    return None if INSTALLER_ENV in os.environ else URL


class Carrier:
    """A version's server's side of its hand-over, at each tending (``tend``): the attempt it started last (its
    process), when it started it and when the server started (monotonic)."""

    def __init__(self, began: float) -> None:
        self.began = began
        self.tried: float | None = None
        self.process: subprocess.Popen | None = None

    def tend(self, name: str, told: Callable[[str], None], *, mono: float | None = None,
             wall: float | None = None) -> str | None:
        """Version ``name``'s hand-over looked after: nothing while an attempt runs; an attempt's end told once
        (``ended``), one that was stopped before it said its outcome taken as ``no_report``; then what ``plan`` says,
        done -- an attempt started (``start``), or the hand-over ended as superseded or given up. What it did: ``plan``'s
        answer, or None."""
        if self.process is not None:
            if self.process.poll() is None:
                return None
            self.process = None
        record = read(name)
        if record is None or not installer():
            return None
        attempts = _count(record.get("attempts"))
        if (record.get("state") != OWED and attempts <= _count(record.get("told"))) or in_flight():
            return None
        mono = time.monotonic() if mono is None else mono
        wall = time.time() if wall is None else wall
        if attempts > _count(record.get("told")):
            if record.get("outcome") not in (DONE, *FAILURES):  # running, with no attempt holding the lock: stopped
                record["outcome"] = "no_report"
            record["told"] = attempts
            _write(name, record)
            outcome = record["outcome"]
            ended(name, DONE if outcome == DONE else "failed", attempts, told,
                  why=None if outcome == DONE else outcome)
        from cad_server._internal import installations

        step = plan(record, name, installations.current_version(), wall=wall, mono=mono, began=self.began,
                    tried=self.tried)
        if step in (SUPERSEDED, GAVE_UP):
            record.update(state=step, ended=wall)
            _write(name, record)
            ended(name, "superseded" if step == SUPERSEDED else "gave_up", attempts, told)
        elif step == ATTEMPT:
            self.tried = mono
            self.process = start(name, told)
        return step


def ended(name: str, outcome: str, attempts: int, told: Callable[[str], None], *, why: str | None = None) -> None:
    """Version ``name``'s hand-over: an attempt ended (``outcome`` ``done``, or ``failed`` and ``why``: ``no_report``,
    ``setup``, ``app`` or ``other``), or the hand-over did (``gave_up``, ``superseded``), after ``attempts`` attempts.
    Called once for each (``Carrier.tend``): counted (``analytics.arrival``, in the server's own process, by the route
    and the version it came from its arrival record keeps), and one line to ``told`` (the server's log), counts
    only."""
    from cad_server import analytics
    from cad_server._internal import arrival

    came = (arrival.read(name) or {}).get("from")
    analytics.arrival("handover", route=arrival.UPDATER, earlier=came if isinstance(came, str) else None,
                      outcome=outcome, reason=why, attempts=attempts)
    if outcome == DONE:
        line = f"the install script ran for cad {name}'s hand-over: done (attempt {attempts})"
    elif outcome == "failed":
        line = (f"the install script ran for cad {name}'s hand-over: attempt {attempts} of at most {ATTEMPTS} failed "
                f"({why}); it runs again later")
    elif outcome == "gave_up":
        line = f"cad {name}'s hand-over gave up after {attempts} attempts: the install script is not run again"
    else:
        line = f"a newer cad has taken over: cad {name}'s hand-over ends after {attempts} attempts"
    told(line)


def start(name: str, told: Callable[[str], None]) -> subprocess.Popen | None:
    """An attempt for version ``name`` started (``main``): a program of this Python, detached -- a session of its own,
    its output nowhere -- in the environment setup gives the programs it starts. Its process, or None where it could
    not start (said)."""
    from cad.engine.places import detached
    from cad_server.cli.setup import _environment

    try:
        return subprocess.Popen([sys.executable, "-P", "-m", "cad_server._internal.install_script", name],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=_environment(), close_fds=True, **detached())
    except OSError as error:
        told(f"cad {name}'s hand-over could not start the install script: {error}")
        return None


# --- an attempt ---------------------------------------------------------------------------------------------------


def release(version: str) -> tuple[int, ...] | None:
    """The release numbers ``version`` starts with (``0.11.11`` of ``0.11.11`` and of a development build of it,
    ``0.11.11-dev.<stamp>``), or None for a name that starts with none. A release is always ``X.Y.Z``."""
    found = re.match(r"[0-9]+(?:\.[0-9]+)*", version or "")
    return tuple(int(part) for part in found.group().split(".")) if found else None


def _padded(numbers: tuple[int, ...], size: int) -> tuple[int, ...]:
    return numbers + (0,) * (size - len(numbers))


def serves(url: str, version: str, *, seconds: float = ASK_SECONDS) -> bool:
    """Whether the ``install.py`` at ``url`` names ``version``'s release, or a later one, as its fallback. False for
    one that cannot be read, or names none."""
    wanted = release(version)
    if wanted is None:
        return False
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "cad-engine-update", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=seconds) as answer:
            text = answer.read(MOST_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:  # not found, or not yet: its body closed
        error.close()
        return False
    except (OSError, ValueError):
        return False
    found = FALLBACK.search(text)
    named = release(found.group(1)) if found else None
    if named is None:
        return False
    size = max(len(named), len(wanted))
    return _padded(named, size) >= _padded(wanted, size)


def wait(url: str, version: str, *, delays: Sequence[float] = DELAYS, sleep: Callable[[float], None] = time.sleep,
         still: Callable[[], bool] = lambda: True) -> bool:
    """Whether the site at ``url`` serves ``version``'s install script (``serves``): asked at once, then after each of
    ``delays``; False once they are spent, or as soon as ``still()`` is not true (looked at every ``LOOK_SECONDS``
    of a delay)."""
    if serves(url, version):
        return True
    for delay in delays:
        left = delay
        while left > 0:
            step = min(LOOK_SECONDS, left)
            sleep(step)
            left -= step
            if not still():
                return False
        if serves(url, version):
            return True
    return False


def run(command: list[str] | str, report: Path, *, seconds: float = RUN_SECONDS) -> int | None:
    """``command`` (``installer``'s: on Windows a command line a test names is one string, run as it is written) run
    once with ``CAD_INSTALL_REPORT`` naming ``report``, its output nowhere, and stopped with every process it started
    after ``seconds``: its exit status, or None where it could not start or was stopped. uv's own
    installer, which the hosted script runs where it finds no uv, is told to leave the person's shell profiles alone
    (``UV_NO_MODIFY_PATH``): no one is there to be asked."""
    environment = {**os.environ, REPORT_ENV: str(report), "UV_NO_MODIFY_PATH": "1"}
    group = ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)} if os.name == "nt"
             else {"start_new_session": True})
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=environment, **group)
    except (OSError, ValueError):
        return None
    try:
        return process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        process.wait()
        return None


def judge(report: Path) -> str:
    """An attempt's outcome by the report its script wrote at ``report`` (see the module): ``done``, ``no_report``,
    ``setup`` or ``app``. Of the report only its ``setup`` exit status and whether any step's status is ``failed`` are
    read."""
    try:
        found = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "no_report"
    steps = found.get("apps") if isinstance(found, dict) else None
    if not isinstance(steps, dict):
        return "no_report"
    if found.get("setup") != 0 or isinstance(found.get("setup"), bool):
        return "setup"
    return "app" if any(status == "failed" for status in steps.values()) else DONE


def attempt(name: str, *, sleep: Callable[[float], None] = time.sleep) -> str | None:
    """One attempt for version ``name`` (see the module), under the computer's hand-over lock, recorded as it begins
    and as it ends: its outcome, or None where none was made (another attempt holds the lock, nothing is owed,
    ``installations/current`` does not name ``name``, or there is no command to run)."""
    from cad.engine import places
    from cad_server._internal import installations
    from cad_server._internal.file_lock import attempt as hold

    command = installer()
    if not command:
        return None
    with hold(_lock()) as mine:
        record = read(name) if mine else None
        if record is None or record.get("state") != OWED or installations.current_version() != name:
            return None
        began = time.time()
        record.update(attempts=_count(record.get("attempts")) + 1, last=began,
                      first=_time(record.get("first")) or began, outcome=RUNNING)
        _write(name, record)
        report = places.data_dir(name) / REPORT
        still = lambda: installations.current_version() == name  # noqa: E731
        url = install_py()
        try:
            report.unlink(missing_ok=True)
        except OSError:
            outcome = "other"
        else:
            if (url and not wait(url, name, sleep=sleep, still=still)) or not still():
                outcome = "other"
            else:
                run(command, report)
                outcome = judge(report)
        record = read(name) or record
        record["outcome"] = outcome
        if outcome == DONE:
            record.update(state=DONE, ended=time.time())
        _write(name, record)
        return outcome


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m cad_server._internal.install_script VERSION``: one attempt of version ``VERSION``'s hand-over
    (``attempt``). Always 0: no one waits on this program."""
    words = list(sys.argv[1:] if argv is None else argv)
    if len(words) != 1:
        return 0
    try:
        attempt(words[0])
    except Exception:  # noqa: BLE001 - nothing reads this program's output; the server tells what the record says
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
