"""The install command catching up with cad: where ``plugin.auto_update`` is on (``auto_update.plugin_switch``) and
this cad is newer than the release of cad the install command is up to date for, the server runs ``cad plugin update``
once.

cad knows no app, plugin or skill. What it knows here is the hosted install command, which ``cad plugin update`` runs
(``install_script.run``), and the release it is up to date for. The rule holds on every route by which cad gets newer
-- its own automatic update, a typed ``cad update``, ``uv tool upgrade cad`` or ``pipx upgrade cad`` by hand --
because it is the server of the newer cad that asks, whatever brought it.

**The record** (``RECORD``, in the state folder beside ``auto-update.json``): ``for``, the release of cad the install
command is up to date for -- written by ``cad plugin update`` as it ends with exit status 0 (``ended``), and as the
switch is turned on (``noted``, from ``auto_update.change_plugin``): the install command turns it on as its last step
wherever cad is there, right after it put the plugin in place, and tells cad how its run is ending in the environment
of that call (``FAILED_ENV``): ending well, the switch is turned on and ``for`` written; ending badly, the switch is
turned on and nothing written, so a computer whose runs keep failing still has the plugin kept: where an earlier run
ended well (``for`` older than this cad), the server runs the command again for this release; where none ever did (no
``for``), the rule below takes this release as up to date, and the command runs once cad is newer. A person who turns
it on by hand, with no such variable, means "from this release on". A run that fails writes nothing of ``for``. Then
the last run the server began
(``begin``): ``release``, ``at``, ``tries`` (of that release), ``outcome`` (``underway``, then ``ok`` or ``failed``),
``code`` (its exit status, null where it could not start) and ``ended``. It is a state record, not a choice, so it
lives in the state folder, as the update's own record does, and not in the person's settings. ``cad doctor`` shows it.

**The rule** (``due``), asked by the server at its start and as it tends itself, only once nothing is in flight: the
switch on; the update check not turned off for this process (``updates.checking``: ``CAD_UPDATE_CHECK=0``, CI, a
development build); an install command to run (``install_script.installer``: ``CAD_ENGINE_UPDATE_INSTALLER``, a test's
stand-in, or none where it is empty); this cad a global install (``tool``: an installer of ``auto_update.INSTALLERS``
made its environment) of a plain release;
install mode not owed (BRIDGE-ONLY: a computer the bridge still carries gets that run, ``install_script``, and no
other); and this cad newer than ``for``. Where the record names no ``for`` (none yet, or unreadable), it is written
for this release and nothing runs: a fresh install's command writes it itself, and a computer whose switch was on
before is taken as up to date. Bounded: a run underway, of any release, begun less than ``RETRY_SECONDS`` ago, is
waited for; one of this release that failed (or never said how it ended) is tried again not sooner than
``RETRY_SECONDS`` after it began, and at a later start or tending: at most ``TRIES`` runs for one release, each an hour
or more after the one before. Never in a loop. ``begin`` asks the record's half of it again under the state folder's
lock, as it keeps its run (``_wanted``), so two servers on one state folder never both begin one.

**A run** (``begin``): the record says ``underway`` first; then this cad's own ``cad`` command
(``auto_update.tool_command``) runs ``cad plugin update``, detached, with no window, in an environment that points at
nothing of this one (``auto_update._UNSET``) and names the run (``ATTEMPT_ENV``: its ``at``), its output in
``install-command.log`` (``auto_update.INSTALL_LOG``). Named so, that command stops the install command, with every
process it started, after ``INSTALL_SECONDS`` and exits non-zero (``install_script.run``, ``deadline``), so no run
outlives its deadline whichever server began it; a person's own run has none. That command keeps how it ended
(``ended``); where it exited without saying so, the server that started it keeps it as failed, with its exit status
(``Catcher``). ``cad update`` never runs it.

Imports the standard library alone; what it asks of cad it imports as it asks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

RECORD = "install-command.json"
# The run ``cad plugin update`` is, where the server began it: the ``at`` of the record's run.
ATTEMPT_ENV = "CAD_INSTALL_ATTEMPT"
# Set to ``1`` by the install command (``scripts/install/install.py``) for its own ``cad plugin update auto on`` where
# its run is ending badly: the switch turned on, and nothing taken as up to date (see the module). Empty or absent:
# the run is ending well, or a person typed it.
FAILED_ENV = "CAD_INSTALL_FAILED"


def failing() -> bool:
    """Whether this command was run by an install command whose run is ending badly (``FAILED_ENV``)."""
    return os.environ.get(FAILED_ENV, "").strip() == "1"
TRIES = 3  # how many runs one release gets: once, and twice more, each an hour or more after the one before
RETRY_SECONDS = 60 * 60.0
UNDERWAY, OK, FAILED = "underway", "ok", "failed"


def deadline() -> float | None:
    """How long ``cad plugin update`` lets the install command run: where a server began this run (``ATTEMPT_ENV``),
    ``INSTALL_SECONDS``, the bound cad's update helper puts on an install; a person's own run, none."""
    if not os.environ.get(ATTEMPT_ENV):
        return None
    from cad_server._internal.auto_update_helper import INSTALL_SECONDS

    return float(INSTALL_SECONDS)


def _folder() -> Path:
    from cad.engine.places import state_dir

    return state_dir()


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
    on. ``OSError`` where it cannot be written."""
    named = release if _numbers(release) is not None else _version()
    _change(lambda found: {**found, "for": named})


def ended(code: int | None) -> None:
    """``cad plugin update`` ended with exit status ``code``: ``for`` this cad where it is 0 (a run that failed writes
    none: the install command turns the switch on as it ends badly too, but then tells cad so, ``FAILED_ENV``, and
    nothing is written), and, where the server began this run (``ATTEMPT_ENV``), the run's outcome. Never raises."""
    try:
        attempt = os.environ.get(ATTEMPT_ENV)

        def change(found: dict[str, Any]) -> dict[str, Any]:
            if code == 0:
                found["for"] = _version()
            if attempt and str(found.get("at")) == attempt and found.get("outcome") == UNDERWAY:
                found.update(outcome=OK if code == 0 else FAILED, code=code, ended=time.time())
            return found

        _change(change)
    except Exception:  # noqa: BLE001 - the command's own exit status is what it says
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
    """Whether the server runs ``cad plugin update`` now (see the module); a record with no ``for`` is written for
    this release first, and nothing runs. Never raises."""
    try:
        from cad_server import updates
        from cad_server._internal import auto_update, install_script

        now = time.time() if now is None else now
        version = _version()
        if not auto_update.plugin_switch() or not updates.checking() or not install_script.installer():
            return False
        if auto_update.release(version) is None or tool() is None:
            return False
        owed = install_script.read()
        if owed is not None and owed.get("state") == install_script.OWED:
            return False  # BRIDGE-ONLY: the bridge's run, never a second
        found = read()
        if _numbers(found.get("for")) is None:
            noted(version)
            return False
        return _wanted(found, version, now)
    except Exception:  # noqa: BLE001 - a rule that cannot be asked runs nothing
        return False


def _wanted(found: dict[str, Any], version: str, now: float) -> bool:
    """The record's half of the rule (see the module), for this cad, ``version``: newer than ``for``; no run underway,
    of any release, begun less than ``RETRY_SECONDS`` ago; and, for this release, fewer than ``TRIES`` runs, the last
    begun ``RETRY_SECONDS`` ago or more."""
    mine, last_for = _numbers(version), _numbers(found.get("for"))
    if mine is None or last_for is None or mine <= last_for:
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
    (``_wanted``) and the run kept as ``underway`` in the same step, then ``cad plugin update`` started. Its process, or
    None where the record no longer wants one (another server began one, or a run ended with exit status 0 since
    ``due`` was asked) or it could not start (kept as failed). Never raises."""
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
        told(f"the install command could not begin: {type(error).__name__}: {error}")
        return None, None
    at = began[-1]
    folder = _folder()
    env = {**{name: value for name, value in os.environ.items() if name not in auto_update._UNSET},
           ATTEMPT_ENV: str(at)}
    try:
        with open(folder / auto_update.INSTALL_LOG, "w", encoding="utf-8") as out:
            process = subprocess.Popen([str(auto_update.tool_command(prefix)), "plugin", "update"],
                                       stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT, env=env, cwd=str(folder), **detached())
    except (OSError, ValueError) as error:
        told(f"the install command could not start: {error}")
        try:
            _change(lambda kept: {**kept, "outcome": FAILED, "code": None, "ended": time.time()}
                    if kept.get("at") == at else kept)
        except OSError:
            pass
        return None, None
    told(f"cad {version} is newer than the one the install command is up to date for: it runs once now, in the "
         "background")
    return process, at


class Catcher:
    """The server's side (``daemon.Daemon``): the run it began last, held while it runs, so it begins no second, and
    kept as failed, with its exit status, where it exited without saying how it ended."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.at: float | None = None

    def tend(self, told) -> bool:
        """The rule asked (``due``) and a run begun where it says so (``begin``, which asks the record again under the
        lock); never while this server's last run still runs. Whether one began."""
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
