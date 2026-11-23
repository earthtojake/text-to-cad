"""The plugin catching up with cad: where ``plugin.auto_update`` is on (``auto_update.plugin_switch``) and this cad is
newer than the release of cad the plugin in the agent apps is up to date for, the server runs ``cad plugin install``
once.

What cad knows of agent apps, plugins and skills lives in one place, ``cad_server.plugin``, reached only by the ``cad
plugin`` command (``cad_server.cli.plugin``). This module names none of them: it knows that command, when the server
runs it, the release it is up to date for, and the lock one run of it holds. The rule holds on every route by which cad
gets newer -- its own automatic update, a typed ``cad update``, ``uv tool upgrade cad`` or ``pipx upgrade cad`` by hand
-- because it is the server of the newer cad that asks, whatever brought it.

**The record** (``RECORD``, in the state folder beside ``auto-update.json``): ``for``, the release of cad the plugin is
up to date for -- written by ``cad plugin install`` as it ends with every app it found gone well (``ended``: exit status
0 and no app ``failed``; a run that found no app counts), and as the switch is turned on (``noted``, from
``auto_update.change_plugin``), and only ever by this computer's global install of cad (``tool``): a cad run from
anywhere else (the newest release from uv's cache, which the hosted install command runs for an installed cad with no
``cad plugin install``) is not the cad whose server asks the rule below, and its release, which may be of a higher major
than that cad ever reaches, is never kept. ``cad plugin install`` installs and leaves the switch as it is; the switch is
the person's, turned on by the hosted install command they ran, as its last step (``cad plugin update auto on``), which
says how its run is ending in the environment of that call (``FAILED_ENV``): every app gone well, the switch is turned
on and ``for`` written; otherwise (the plugin's step ended non-zero, or an app failed), the switch is turned on and
nothing written, so a computer whose runs keep failing still has the plugin kept: where an earlier run went well
(``for`` older than this cad), the server runs the command again for this release; where none ever did (no ``for``), the
run's own mark (``owed``, below) has it run again all the same. 0.11.12 and 0.11.13 read that variable the same way, so
the call means one thing to every cad it reaches. A person who turns it on by hand, with no such variable, means "from
this release on". A run that fails, or where any app failed, writes nothing of ``for``: the plugin is up to date for a
release only where every app found went well. ``owed``: the release of the global install's last run that did not go
well (an app failed, or the run did), dropped by one that went well and by the switch turned on (``noted``): the rule
reads it as a run owed to that release and any later one, so a computer where the plugin was never up to date for any
release (no ``for``: a fresh install whose first run had an app fail) is tried again too. BRIDGE-ONLY: the bridge's run
of the hosted install command, done once cad is installed whatever the apps did (``install_script``), marks it too
where its report says the plugin's step failed and no run is owed already (``owe``): the release that run was owed
for, so the plugin is this rule's to try again even where no global install's run marked it (the step ran a cad from
uv's cache, or could not run at all). 0.11.12 and 0.11.13 read only
``for`` of the record, and keep any other field as they find it. Then the last run the server began (``begin``):
``release``, ``at``, ``tries`` (of that release), ``outcome`` (``underway``, then ``ok`` or ``failed``), ``code`` (its
exit status, null where it could not start) and ``ended``. It is a state record, not a choice, so it lives in the state
folder, as the update's own record does, and not in the person's settings. ``cad doctor`` shows it.

**The rule** (``due``), asked by the server as it tends itself, only once nothing is in flight, never in its first
``START_SECONDS`` (by its monotonic clock) and never while a run holds the lock (``Catcher``): the switch on; the update
check not turned off for this process (``updates.checking``: ``CAD_UPDATE_CHECK=0``, CI, a development build); no test
saying to run nothing (``silenced``: ``CAD_ENGINE_UPDATE_INSTALLER`` set and empty, the variable that names the bridge's
stand-in for the hosted install command -- ``cad plugin install`` itself runs no install command and reads no such
variable); this cad a global install (``tool``: an installer of ``auto_update.INSTALLERS`` made its environment) of a
plain release; install mode not owed (BRIDGE-ONLY: a computer the bridge still carries gets that run,
``install_script``, and no other, until that run is done, which it is once cad is installed: an app that failed there
is this rule's from then on); and this cad newer than ``for``, or owed a run (``owed``, of this release or an
earlier one). Where the record names no ``for`` (none yet, or unreadable) and owes no run, it is written for this
release and nothing runs: the switch was turned on by hand, or no run was ever made, and a computer whose switch was on
before is taken as up to date. Bounded: a run underway, of any release, begun less than ``RETRY_SECONDS`` ago, is waited
for; one of this release that failed (or never said how it ended) is tried again not sooner than ``RETRY_SECONDS`` after
it began, and at a later tending: at most ``TRIES`` runs for one release, each an hour or more after the one before.
Never in a loop. A run where any app failed is a failed run, though the others went well and it exited 0 (``ended``), so
an app that is broken for good costs at most ``TRIES`` runs in the background for each release, an hour or more apart,
and then nothing until cad is newer. ``begin`` asks the record's half of it again under the state folder's lock, as it
keeps its run (``_wanted``), so two servers on one state folder never both begin one.

**A run** (``begin``): the record says ``underway`` first; then this cad's own ``cad`` command
(``auto_update.tool_command``) runs ``cad plugin install``, detached, with no window, in an environment that points at
nothing of this one (``auto_update._UNSET``) and names the run (``SERVER_ENV``: its ``at``), its output in
``install-command.log`` (``auto_update.INSTALL_LOG``). Named so, and only so, that command is a server's run: it has
``INSTALL_SECONDS`` (``deadline``), its hard stop, a server's place at the lock, and it closes the record's run as it
ends (``ended``: ``ok`` only where every app it found went well, else ``failed``). No released cad sets
``SERVER_ENV``. The name 0.11.12 and 0.11.13 give their server's run,
``ATTEMPT_ENV``, is no such mark: their run is their own ``cad plugin update``, which runs the hosted install
command, and everything that command starts inherits the name -- a ``cad plugin install`` it reached that took it for
its own would close another release's run, under a deadline and a lock role that are not its own. So nothing here
reads it, and the hosted install command takes it out of every cad command it starts. That command has its deadline:
each command it runs is given what is left of them and stopped with every process it started, none is started past
them, and it exits non-zero. That much is the run's own doing, asked between its steps, and a step that never comes
back (a folder on a disk that stopped answering, a lock, a call of ours with no time of its own) would hold the run's
lock, and with it cad's own update and every run that waits, for as long as the process lived. So the command also
carries a hard stop (``HardStop``), a thread of its own that asks nothing of the run: ``GRACE_SECONDS`` past the
deadline, where the command has still not ended, the run's record is closed as a stopped run's (``ended`` with
``STOPPED``), it is counted as stopped, and the process exits with ``STOPPED`` there and then, waiting on nothing --
which frees the lock. No run a server began outlives its deadline by more than that grace and the moment its last
words take (``CLOSE_SECONDS``), whichever server began it and whether or not that server still runs -- but for a
process no thread of which runs at all (one a signal stopped, or one held inside a call that lets no other thread
run, which no wait of the standard library's is), which no thread of its own can end. Any other run (a person's,
the hosted install command's) has no deadline and no stop.
That command keeps how it ended (``ended``); where it exited without saying so, the server that started it keeps it as
failed, with its exit status (``Catcher``). ``cad update`` never runs it, and it runs neither ``cad update`` nor any
install command.

**One run at a time** (``run_lock``, ``running``): a run of ``cad plugin install`` holds ``LOCK``, a file of its own in
the state folder, from its start to its end, so it never holds the state folder's one lock while it works. A second
run waits for it -- but one a server began (``SERVER_ENV``), which ends with exit status ``BUSY`` and runs nothing.
The server begins none while the lock is held, and none in its first ``START_SECONDS``: a person's install command
that updated cad restarted the server, and goes on to the plugin a moment later; it takes the lock and does the work,
and keeps this release, so the server, asking after it, finds the plugin up to date and runs nothing. Where nobody ran
that command (cad's own update, one by hand), the run begins that much later. cad's own update begins none while the
lock is held (``auto_update.due``, ``auto_update.asked``): it would replace this environment's files under the
run. Whether it is held can only be asked by trying for it (``running``: neither ``flock`` nor Windows' ``locking``
says who holds a lock without taking it), so a server that asks holds it for an instant. A run therefore tries for
``SETTLE_SECONDS`` before it takes the lock as another run's (``run_lock``): only then does a server's run answer
``BUSY``, and a person's say that it waits.

Imports the standard library alone; what it asks of cad it imports as it asks.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

RECORD = "install-command.json"
# The run ``cad plugin install`` is, where this release's server began it: the ``at`` of the record's run. No released
# cad sets it (see the module).
SERVER_ENV = "CAD_PLUGIN_SERVER_RUN"
# The name 0.11.12 and 0.11.13 give the run their server began, which everything it starts inherits: never read here,
# never passed on by a run this server begins, and taken out of every cad command the hosted install command starts
# (see the module).
ATTEMPT_ENV = "CAD_INSTALL_ATTEMPT"
# Set to ``1`` by the hosted install command for its own ``cad plugin update auto on`` where its plugin step ended
# non-zero or named an app as failed: the switch turned on, and nothing taken as up to date (see the module). Empty or
# absent: every app went well, or a person typed it. 0.11.12 and 0.11.13 read it the same way.
FAILED_ENV = "CAD_INSTALL_FAILED"
# The command the server runs, as a line of its log names it.
SAID = "`cad plugin install`"
# The lock one run of ``cad plugin install`` holds, in the state folder (``run_lock``).
LOCK = "install-command.lock"
# The exit status of a run a server began that found another run holding the lock: nothing ran, and it is tried again
# later (``EX_TEMPFAIL``).
BUSY = 75
# The exit status of a run a server began that was ended at its deadline, as ``timeout(1)`` says one: the run's own,
# where it stopped itself, and the hard stop's (``HardStop``).
STOPPED = 124
# How long past its deadline a run a server began may take to end by itself before it is ended (``HardStop``): what
# stopping its last command can take at most (the command and what it started ended, then waited on: 40 seconds on
# Windows), and its last lines.
GRACE_SECONDS = 60.0
# How long the hard stop gives the run's last words (its record closed, its line, its count) before the process exits
# without them: they wait on the state folder's lock, which whatever hangs may hold.
CLOSE_SECONDS = 5.0
# How long a run tries for the lock, every ``SETTLE_STEP``, before it takes it as held by another run: whoever asks
# whether a run is going (``running``) holds it for an instant, which is no run.
SETTLE_SECONDS = 2.0
SETTLE_STEP = 0.25
# How long a server waits after its start before it first asks the rule (``Catcher``), by its own monotonic clock: two
# of its tendings (``daemon.TEND_SECONDS``; on a test's computer, two of its own, ``daemon.catch_up_seconds``). A
# person's install command that just updated cad, and with it restarted the server, goes on to the plugin within it.
START_SECONDS = 60.0
TRIES = 3  # how many runs one release gets: once, and twice more, each an hour or more after the one before
RETRY_SECONDS = 60 * 60.0
UNDERWAY, OK, FAILED = "underway", "ok", "failed"


def failing() -> bool:
    """Whether this command was run by a hosted install command whose plugin step did not go well for every app
    (``FAILED_ENV``)."""
    return os.environ.get(FAILED_ENV, "").strip() == "1"


def server_run() -> str | None:
    """The ``at`` of the record's run where this release's server began this one (``SERVER_ENV``), else None."""
    return os.environ.get(SERVER_ENV) or None


def deadline() -> float | None:
    """How long ``cad plugin install`` may take: where this release's server began this run (``server_run``),
    ``INSTALL_SECONDS``, the bound cad's update helper puts on an install; any other run, none."""
    if server_run() is None:
        return None
    from cad_server._internal.auto_update_helper import INSTALL_SECONDS

    return float(INSTALL_SECONDS)


def _folder() -> Path:
    from cad.engine.places import state_dir

    return state_dir()


@contextlib.contextmanager
def run_lock(*, wait: bool, waiting: Callable[[], None] | None = None) -> Iterator[bool]:
    """``LOCK`` held for one run (see the module), from here to the end of the ``with``: yields True. Where it is
    held, it is tried for again, for ``SETTLE_SECONDS``: one who only asked whether a run is going lets it go at once.
    Where it is held still, another run holds it: with ``wait``, ``waiting`` is called once and that run waited for,
    however long it takes; without, yields False, and the caller runs nothing. Where the lock's file cannot be made
    or opened (a state folder this process may not write), the run goes on without one: yields True."""
    from cad_server._internal import file_lock

    with contextlib.ExitStack() as held:
        mine = True
        try:
            folder = _folder()
            folder.mkdir(parents=True, exist_ok=True)
            mine = _settled(held, folder / LOCK)
            if not mine and wait:
                if waiting is not None:
                    waiting()
                held.enter_context(file_lock.exclusive(folder / LOCK))
                mine = True
        except OSError:
            mine = True
        yield mine


def _settled(held: contextlib.ExitStack, path: Path) -> bool:
    """``path`` locked and kept in ``held`` where it comes free within ``SETTLE_SECONDS``, tried at once and then
    every ``SETTLE_STEP``; whether it was."""
    from cad_server._internal import file_lock

    until = time.monotonic() + SETTLE_SECONDS
    while True:
        with contextlib.ExitStack() as trying:
            if trying.enter_context(file_lock.attempt(path)):
                held.push(trying.pop_all())
                return True
        if time.monotonic() >= until:
            return False
        time.sleep(SETTLE_STEP)


def running() -> bool:
    """Whether a run holds ``LOCK`` now, asked without waiting and without making the file -- by trying for it, the
    one way there is, so it is held here for an instant, which a run that begins just then waits out (``run_lock``).
    Never raises: where it cannot be asked, none is taken to run."""
    try:
        from cad_server._internal import file_lock

        path = _folder() / LOCK
        if not path.is_file():
            return False
        with file_lock.attempt(path) as free:
            return not free
    except Exception:  # noqa: BLE001 - a lock that cannot be asked holds nothing back
        return False


def silenced() -> bool:
    """Whether a test said the server runs nothing by itself: ``CAD_ENGINE_UPDATE_INSTALLER`` set and empty
    (``install_script.INSTALLER_ENV``, which names the bridge's stand-in for the hosted install command)."""
    from cad_server._internal.install_script import INSTALLER_ENV

    return INSTALLER_ENV in os.environ and not os.environ[INSTALLER_ENV].strip()


def _version() -> str:
    from cad_server import __version__

    return __version__


def _numbers(text: Any) -> tuple[int, ...] | None:
    """A release's numbers (a development build ``X.Y.Z-dev.<stamp>`` is its release's), or None."""
    found = re.match(r"(\d+)\.(\d+)\.(\d+)", text) if isinstance(text, str) else None
    return tuple(int(part) for part in found.groups()) if found else None


def read() -> dict[str, Any]:
    """The record, ``{}`` where there is none or it cannot be read."""
    try:
        found = json.loads((_folder() / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _change(change) -> dict[str, Any] | None:
    """The record read, changed (``change`` gets a copy) and written, under the state folder's one lock; where
    ``change`` gives None, nothing is written. What was written, or None. ``OSError`` where it cannot be written."""
    from cad._internal.atomic_replace import write_bytes_atomic
    from cad_server._internal.file_lock import state

    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    with state(folder):
        found = change(dict(read()))
        if found is not None:
            write_bytes_atomic(folder / RECORD, (json.dumps(found, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return found


def noted(release: str | None = None) -> None:
    """The switch turned on (``auto_update.change_plugin``): ``for`` is ``release`` (this cad's by default) from now
    on, and a run owed for it or an earlier release (``owed``) is owed no more. ``OSError`` where it cannot be
    written."""
    named = release if _numbers(release) is not None else _version()

    def change(found: dict[str, Any]) -> dict[str, Any]:
        owed = _numbers(found.get("owed"))
        kept = {key: value for key, value in found.items() if key != "owed" or owed is None
                or owed > _numbers(named)}
        return {**kept, "for": named}

    _change(change)


def owe(release: str) -> None:
    """BRIDGE-ONLY. The bridge's run of the hosted install command ended done with the plugin's step failed
    (``install_script``): a run owed for ``release`` (``owed``, see the module), unless one is owed already -- the mark
    ``cad plugin install`` leaves where the global install ran it (``ended``), kept as it is. ``OSError`` where it
    cannot be written."""
    _change(lambda found: None if _numbers(found.get("owed")) is not None else {**found, "owed": release})


def owing(found: dict[str, Any], version: str) -> bool:
    """Whether the record owes this cad, ``version``, a run: a run of the global install for it or an earlier release
    did not go well (``owed``, see the module)."""
    owed, mine = _numbers(found.get("owed")), _numbers(version)
    return owed is not None and mine is not None and owed <= mine


def ended(code: int | None, *, failed: bool = False) -> None:
    """``cad plugin install`` ended with exit status ``code``, ``failed`` where an app it found failed: it went well
    where it is 0 and no app failed (one that found none included). Then ``for`` is this cad where this cad is the
    computer's global install (``tool``; a run that did not go well writes none, nor does a cad run from anywhere
    else, see the module) and the run it was owed no longer owed; where it did not go well, this cad's release is
    owed a run (``owed``: the global install's alone, as ``for``); and, where this release's server began this run
    (``server_run``), the run's outcome: ``ok`` where it went well, else ``failed`` with its exit status, so the rule
    tries it again later; any other run leaves the record's run as it is. Never raises."""
    try:
        attempt = server_run()
        well = code == 0 and not failed
        mine = tool() is not None

        def change(found: dict[str, Any]) -> dict[str, Any]:
            if mine and well:
                found["for"] = _version()
                found.pop("owed", None)
            elif mine:
                found["owed"] = _version()
            if attempt and str(found.get("at")) == attempt and found.get("outcome") == UNDERWAY:
                found.update(outcome=OK if well else FAILED, code=code, ended=time.time())
            return found

        _change(change)
    except Exception:  # noqa: BLE001 - the command's own exit status is what it says
        pass


class HardStop:
    """What ends a run a server began for certain (see the module), armed as it is made: ``seconds`` -- the run's
    deadline -- and ``GRACE_SECONDS`` later, where the command has not ended, the run's record is closed as a stopped
    run's (``ended`` with ``STOPPED``), ``last`` is called (the command's: its line, its count) and the process exits
    with ``STOPPED``, by ``os._exit``: no thread joined, no lock waited on, nothing flushed but what ``last`` flushed.
    The record and ``last`` have ``CLOSE_SECONDS`` between them; where they take longer (the state folder's lock held
    by what hangs), the process exits without them, and the server that began the run keeps it as failed with that
    exit status (``Catcher``).

    ``over()``: the run ended by itself, so its count and its record are its own to keep; where the stop has begun, it
    does not return, and nothing is said twice. From then the stop says nothing and only ends a command that still
    has not exited when its time comes. ``cancel()``: the command is done, and exits by itself."""

    def __init__(self, seconds: float, last: Callable[[], None] | None = None) -> None:
        self.last = last
        self._turn = threading.Lock()
        self._over = self._done = False
        self._timer = threading.Timer(max(0.0, seconds) + GRACE_SECONDS, self._stop)
        self._timer.daemon = True  # never what keeps the process from exiting
        self._timer.start()

    def over(self) -> None:
        with self._turn:
            self._over = True

    def cancel(self) -> None:
        self._timer.cancel()
        with self._turn:
            self._done = True

    def _stop(self) -> None:
        with self._turn:  # held until the process is gone: a run ending by itself just now waits here
            if self._done:
                return
            try:
                if not self._over:
                    closing = threading.Thread(target=self._close, daemon=True)
                    closing.start()
                    closing.join(CLOSE_SECONDS)
            finally:
                os._exit(STOPPED)

    def _close(self) -> None:
        ended(STOPPED)
        try:
            if self.last is not None:
                self.last()
        except Exception:  # noqa: BLE001 - the process exits whatever its last words did
            pass


def tool() -> Path | None:
    """This cad's environment where it is a global install (an installer of ``auto_update.INSTALLERS`` made it), else
    None. Only whether it is one: the installer's program need not be found, as the update's must."""
    import sys

    from cad_server._internal import auto_update

    prefix = Path(sys.prefix)
    return prefix if any(installer.owns(prefix) for installer in auto_update.INSTALLERS) else None


def _stale(found: dict[str, Any], now: float) -> bool:
    """Whether the record's run began ``RETRY_SECONDS`` ago or more (a clock set back counts as long ago)."""
    at = found.get("at")
    return not isinstance(at, (int, float)) or not 0 <= now - float(at) < RETRY_SECONDS


def due(*, now: float | None = None) -> bool:
    """Whether the server runs ``cad plugin install`` now (see the module); a record with no ``for`` is written for
    this release first, and nothing runs. Never raises."""
    try:
        from cad_server import updates
        from cad_server._internal import auto_update, install_script

        now = time.time() if now is None else now
        version = _version()
        if not auto_update.plugin_switch() or not updates.checking() or silenced():
            return False
        if auto_update.release(version) is None or tool() is None:
            return False
        owed = install_script.read()
        if owed is not None and owed.get("state") == install_script.OWED:
            return False  # BRIDGE-ONLY: the bridge's run, never a second
        found = read()
        if _numbers(found.get("for")) is None and not owing(found, version):
            noted(version)  # the switch turned on by hand, or no run ever made: from this release on
            return False
        return _wanted(found, version, now)
    except Exception:  # noqa: BLE001 - a rule that cannot be asked runs nothing
        return False


def _wanted(found: dict[str, Any], version: str, now: float) -> bool:
    """The record's half of the rule (see the module), for this cad, ``version``: newer than ``for``, or owed a run
    (``owing``); no run underway, of any release, begun less than ``RETRY_SECONDS`` ago; and, for this release, fewer
    than ``TRIES`` runs, the last begun ``RETRY_SECONDS`` ago or more."""
    mine, last_for = _numbers(version), _numbers(found.get("for"))
    if mine is None:
        return False
    if not owing(found, version) and (last_for is None or mine <= last_for):
        return False
    if found.get("outcome") == UNDERWAY and not _stale(found, now):
        return False  # waited for, whichever release and whichever server began it
    if found.get("release") != version:
        return True
    tries = found.get("tries")
    if type(tries) is int and tries >= TRIES:
        return False
    return _stale(found, now)


def begin(told, *, now: float | None = None) -> subprocess.Popen | None:
    """A run begun (see the module): the record's half of the rule asked again under the state folder's lock
    (``_wanted``) and the run kept as ``underway`` in the same step, then ``cad plugin install`` started. Its process,
    or None where the record no longer wants one (another server began one, or a run went well since ``due`` was
    asked) or it could not start (kept as failed). Never raises."""
    return _begin(told, now=now)[0]


def _begin(told, *, now: float | None = None) -> tuple[subprocess.Popen | None, float | None]:
    """``begin``, and the ``at`` the run was kept with (None where none began). The time is read once the state
    folder's lock is held (``now``, a test's clock, in its place), as ``auto_update._claim`` reads it: read before, a
    server that waited for the lock would find the run another began later than its own now, which ``_stale`` takes
    for a clock set back, and begin a second."""
    from cad.engine.places import detached
    from cad_server._internal import auto_update

    version = _version()
    began: list[float] = []
    try:
        prefix = tool()
        if prefix is None:
            return None, None

        def start(kept: dict[str, Any]) -> dict[str, Any] | None:
            at = time.time() if now is None else now
            if not _wanted(kept, version, at):
                return None
            tries = kept.get("tries") if kept.get("release") == version else 0
            kept = {key: value for key, value in kept.items() if key not in ("code", "ended")}
            began.append(at)
            return {**kept, "release": version, "at": at, "tries": (tries if type(tries) is int else 0) + 1,
                    "outcome": UNDERWAY}

        if _change(start) is None:
            return None, None
    except Exception as error:  # noqa: BLE001 - never a failure of the server's tending
        told(f"{SAID} could not begin: {type(error).__name__}: {error}")
        return None, None
    at = began[-1]
    folder = _folder()
    env = {**{name: value for name, value in os.environ.items()
              if name not in (*auto_update._UNSET, ATTEMPT_ENV, FAILED_ENV)}, SERVER_ENV: str(at)}
    try:
        with open(folder / auto_update.INSTALL_LOG, "w", encoding="utf-8") as out:
            process = subprocess.Popen([str(auto_update.tool_command(prefix)), "plugin", "install"],
                                       stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT, env=env, cwd=str(folder), **detached())
    except (OSError, ValueError) as error:
        told(f"{SAID} could not start: {error}")
        try:
            _change(lambda kept: {**kept, "outcome": FAILED, "code": None, "ended": time.time()}
                    if kept.get("at") == at else kept)
        except OSError:
            pass
        return None, None
    told(f"cad {version} is newer than the one the plugin is up to date for: {SAID} runs once now, in the background")
    return process, at


class Catcher:
    """The server's side (``daemon.Daemon``): the run it began last, held while it runs, so it begins no second, and
    kept as failed, with its exit status, where it exited without saying how it ended. It only asks whether the run
    has exited: what ends a run past its deadline is the run's own command (``HardStop``), whichever server began it.

    ``started``: when the server started, by ``clock`` (monotonic; now by default); nothing is asked until ``wait``
    seconds past it (``START_SECONDS``)."""

    def __init__(self, started: float | None = None, *, wait: float = START_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.process: subprocess.Popen | None = None
        self.at: float | None = None
        self.clock = clock
        self.started = clock() if started is None else started
        self.wait = wait

    def tend(self, told) -> bool:
        """The rule asked (``due``) and a run begun where it says so (``begin``, which asks the record again under the
        lock); never while this server's last run still runs, within ``wait`` of the server's start, or while another
        run holds the lock (``running``): then nothing is begun or kept, no try is spent, and it is asked again at a
        later tending. Whether one began."""
        if self.process is not None:
            code = self.process.poll()
            if code is None:
                return False
            at, self.process = self.at, None
            try:
                _change(lambda found: {**found, "outcome": FAILED, "code": code, "ended": time.time()}
                        if found.get("at") == at and found.get("outcome") == UNDERWAY else found)
            except OSError:
                pass
        if self.clock() - self.started < self.wait:
            return False  # the install command that just updated cad goes on to the plugin now (see the module)
        if running():
            return False  # a person's run, or the hosted install command's: it does the work
        if not due():
            return False
        self.process, self.at = _begin(told)
        return self.process is not None


def last(release: str, *, since: float | None = None, now: float | None = None) -> str | None:
    """How the run for ``release`` went, for the update that installed it (``auto_update.report``): ``ok``, ``failed``
    (it failed, could not start, or never said how it ended within ``RETRY_SECONDS``), ``underway``, or None where
    the server began none for it -- with ``since`` (when that update began), none begun since: a run begun before it
    is another's."""
    found = read()
    if found.get("release") != release:
        return None
    at = found.get("at")
    if since is not None and not (isinstance(at, (int, float)) and not isinstance(at, bool) and at >= since):
        return None
    if found.get("outcome") == UNDERWAY:
        return FAILED if _stale(found, time.time() if now is None else now) else UNDERWAY
    return OK if found.get("outcome") == OK else FAILED
