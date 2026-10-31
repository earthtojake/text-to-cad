"""Automatic updates: the person's setting, and the rules the engine keeps when it updates by itself.

With automatic updates on -- the default (``DEFAULT``) -- the device's engine reads the version feed
once an hour (``cad_server/updates.py``) and, when it names a release newer than this one, updates to
it with no click (``cad_server._internal.update.Update.automatic``): the release is installed and its
CAD kernel environment made at once, in the background, and the agent apps' plugins are moved to it
and the engine switched (``cad_server._internal.switch``) only once nothing has run for a minute
(``IDLE_SECONDS``): no build, draw, export or agent's call in flight, no switch or other update
underway. The update button, ``cad update`` and the install command work as ever and come first: a
click while an automatic update gets ready makes it the click's, done at once.

The setting is the person's, one for every CAD app and release: the ``updates`` section of their
settings (``cad_server/settings.py``: ``settings.json`` in the state folder), ``{"automatic": false}``
once they turn it off (``cad update auto off``, or the app menu's Automatic updates in the CAD Viewer
and the CAD app), ``{"automatic": true}`` once they turn it on; no section is the default. An
environment that turns the version check off (``CAD_UPDATE_CHECK=0``, CI) turns it off too, and no
click changes that (``reason``: ``environment``). A development install is never updated by itself,
as it is never told of a release.

An update that fails leaves the engine as it was, or brings the release before back (the switch's
way back), and is not tried again in a loop: the last automatic attempt is kept in the state folder
(``RECORD``: its release and when), and the same release is tried again only ``RETRY_SECONDS`` later;
a newer release the feed names is tried at the next check. Offline, or a feed that cannot be read:
nothing happens, and nothing waits on it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from cad_server.settings import read_section, update_section

LOG = logging.getLogger("cad_server.auto_updates")

SECTION = "updates"  # this module's part of the settings file
KEY = "automatic"
# Whether automatic updates are on for a person who never chose: the one place to flip it.
DEFAULT = True
# The last automatic attempt, in the state folder: its release, when it began, and why it failed.
RECORD = "update-automatic.json"
# How long nothing may have run before the engine switches by itself.
IDLE_SECONDS = 60.0
# How long before the same release is tried again by itself once an attempt of it did not hold.
RETRY_SECONDS = 24 * 60 * 60
_OFF = ("0", "off", "false", "no")


def _environment_off() -> bool:
    """Whether this process's environment turns the version check, and so automatic updates, off."""
    if str(os.environ.get("CAD_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return True
    return str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF)


def read(*, path: Path | None = None) -> dict[str, Any]:
    """``{"automatic": bool, "reason": "default" | "choice" | "environment"}``: whether the engine
    updates by itself, and why. Settings that cannot be read now read as the default."""
    if _environment_off():
        return {"automatic": False, "reason": "environment"}
    try:
        kept = read_section(SECTION, path=path).get(KEY)
    except OSError:
        LOG.debug("could not read the update setting", exc_info=True)
        kept = None
    if isinstance(kept, bool):
        return {"automatic": kept, "reason": "choice"}
    return {"automatic": DEFAULT, "reason": "default"}


def enabled(*, path: Path | None = None) -> bool:
    """Whether the engine updates by itself (``read``)."""
    return bool(read(path=path)["automatic"])


def change(choice: Any, *, path: Path | None = None) -> dict[str, Any]:
    """Keep the person's answer (``{"automatic": true | false}``) under the state folder's one lock,
    beside every other setting, and answer the setting as it now is (``read``). ``ValueError`` for
    anything else; ``OSError`` when the settings cannot be written."""
    if not isinstance(choice, dict) or set(choice) != {KEY} or not isinstance(choice[KEY], bool):
        raise ValueError('automatic updates are {"automatic": true} or {"automatic": false}')
    update_section(SECTION, lambda kept: {**kept, KEY: choice[KEY]}, path=path)
    return read(path=path)


# --- the last automatic attempt ---------------------------------------------------------------------


def _record_path() -> Path:
    from cad.engine.places import state_dir

    return Path(state_dir()) / RECORD


def attempted(*, path: Path | None = None) -> dict[str, Any] | None:
    """The last automatic attempt (``{"release", "at", "error"?}``), or None."""
    try:
        found = json.loads((path or _record_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or not isinstance(found.get("release"), str) \
            or not isinstance(found.get("at"), (int, float)):
        return None
    return found


def attempt(release: str, *, error: str | None = None, now: float | None = None,
            path: Path | None = None) -> None:
    """The automatic attempt of ``release`` kept, as it begins, and again with ``error`` should it
    fail in the engine (its time kept: a failure is no new attempt). Never raises."""
    from cad._internal.atomic_replace import write_bytes_atomic

    path = path or _record_path()
    kept = attempted(path=path)
    at = now if now is not None else time.time()
    if error is not None and kept is not None and kept["release"] == release:
        at = kept["at"]
    record: dict[str, Any] = {"release": release, "at": at, **({"error": error} if error else {})}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
    except OSError:
        LOG.debug("could not keep the automatic update's attempt in %s", path, exc_info=True)


def forget(*, path: Path | None = None) -> None:
    """The last automatic attempt forgotten: one given up because the person turned it off."""
    try:
        (path or _record_path()).unlink(missing_ok=True)
    except OSError:
        pass


def due(release: str, record: dict[str, Any] | None, now: float) -> bool:
    """Whether ``release`` may be tried by itself now: unless the last automatic attempt was of the
    same release less than ``RETRY_SECONDS`` ago (a clock set back counts as long ago)."""
    if record is None or record.get("release") != release:
        return True
    return not 0 <= now - float(record["at"]) < RETRY_SECONDS


def quiet(since: float, now: float) -> bool:
    """Whether nothing has run since ``since`` for ``IDLE_SECONDS`` (both monotonic)."""
    return now - since >= IDLE_SECONDS


def installing() -> bool:
    """Whether a ``cad setup`` -- the install command, ``cad update`` -- holds the install lock now:
    the person's own update, which an automatic one never runs beside. A lock that cannot be asked
    counts as held."""
    from cad.engine.places import state_dir
    from cad_server.cli.setup import LOCK

    lock = Path(state_dir()) / LOCK
    if not lock.exists():
        return False
    try:
        with open(lock, "a+b") as handle:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    return True
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return True
    return False


# --- what is said of it -----------------------------------------------------------------------------


def _when(stamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))


def describe(engine: dict[str, Any] | None = None, *, now: float | None = None) -> str:
    """One line for ``cad status``, ``cad doctor`` and ``cad update auto``: on or off and why, when the
    feed was last read and when it is next due, and -- from the engine's ``status`` (its ``update``) --
    a release it is getting ready to switch to; else the last automatic attempt that failed."""
    from cad_server import updates
    from cad_server._internal.channel import DEV, channel

    now = time.time() if now is None else now
    found = read()
    reason = {"default": "by default", "choice": "your choice",
              "environment": "CAD_UPDATE_CHECK or CI in this environment"}[found["reason"]]
    line = f"{'on' if found['automatic'] else 'off'} ({reason})"
    development = channel() == DEV
    if found["automatic"] and development:
        line += ", but a development install is never updated by itself"
    try:
        checked = updates._load(updates._cache()).get("checked")
    except Exception:  # noqa: BLE001 - a report line, never a reason for the report to fail
        checked = None
    if isinstance(checked, (int, float)) and checked > 0:
        line += f"; feed last read {_when(checked)}"
        if found["automatic"]:
            line += f", next due {_when(max(now, checked + updates.CHECK_SECONDS))}"
    elif found["automatic"] and not development:
        line += "; feed not read yet: the engine reads it within the hour"
    pending = ((engine or {}).get("automatic") if isinstance(engine, dict) else None) or None
    if isinstance(pending, dict) and pending.get("release"):
        line += (f"; text-to-cad {pending['release']} "
                 + ("installing" if pending.get("state") == "preparing" else "installed, switching once idle"))
    else:
        last = attempted()
        if last is not None and last.get("error"):
            line += f"; the update to {last['release']} on {_when(last['at'])} failed: {last['error']}"
    return line
