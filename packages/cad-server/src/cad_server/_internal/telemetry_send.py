"""``python -P -m cad_server._internal.telemetry_send``: send what commands counted, and exit.

A command sends nothing itself: it keeps what it counted in the spool beside the settings
(``analytics.spool``), which the CAD app's and the viewer's background sends take every window
(``analytics.FLUSH_SECONDS``), each as a ``cli`` batch of its own (``Recorder._spooled``). With neither
running, nothing would. So a command that finds the spool's (or the arrivals')
oldest line older than a window, and no sender started within one, starts this module detached (``start_if_due``): no
window, a process group or session of its own, its output nowhere, the telemetry switches of the command's
environment not inherited (``analytics.for_others``: it goes by the person's settings) -- and goes on without waiting
for it.

When the last sender of a folder was started, or is set to start, is the time of a file of its own beside the settings
(``STARTED``), which only a sender's start writes: none there, none was started. The data folder's one lock
(``file_lock.STATE_LOCK``) is given the same time, as releases of 0.11.10 and earlier kept it, so their commands in
the state folder they share start none in a window this release started one in; its own time is not read, since
taking the lock makes the file, and a lock made a moment ago says nothing of a sender (a version's data folder, made
as its setup imports, would hold its first arrival back a window).

An arrival (``analytics.arrival``) does not wait for the spool to age: the step that counted it may be the last of
its version on the computer. It starts this module at once where no sender was started within a window, else one
that waits until that window is over (``--at``), the stamp's time set to when it will start, so at most one sender
starts each window and none is left waiting for a later command (``start_soon``). It runs on the Python that
counted the arrival -- the version's own, uvx's, an updater's folder of an earlier release's layout -- so a version
whose own environment could not be made is still heard from.

It sends as the process ``cli`` (``send``): the spool, the arrivals, the batches exiting processes kept, a batch at a
time until nothing is left or the receiver takes no more; what it could not send is kept for the next
sender (``Recorder.close``), and it exits. Nothing waits on it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROUNDS = 8  # the most batches one sender sends: a spool past ``analytics.MAX_EVENTS`` events takes several
AT = "--at"  # a sender that waits until then (seconds since 1970) before it sends (``start_soon``)
STARTED = "telemetry-started"  # beside the settings: its time is when the last sender started, or is set to start


def _last(settings: Path) -> float | None:
    """When the last sender of ``settings``' folder was started, or is set to start (``STARTED``'s time), or None
    where none was."""
    try:
        return settings.with_name(STARTED).stat().st_mtime
    except FileNotFoundError:
        return None


def _started(settings: Path, at: float) -> None:
    """A sender of ``settings``' folder started, or set to start, at ``at``: ``STARTED``'s time, and the lock's, which
    releases of 0.11.10 and earlier read. Under the data folder's one lock."""
    from cad_server._internal.file_lock import STATE_LOCK

    stamp = settings.with_name(STARTED)
    stamp.touch()
    os.utime(stamp, (at, at))
    os.utime(settings.with_name(STATE_LOCK), (at, at))


def start_if_due(path: Path | None = None, *, now: float | None = None,
                 spawn: Callable[[Path], Any] | None = None) -> bool:
    """Start the sender when the spool (or the arrivals) has waited longer than a window and none was started
    within one (``STARTED``); whether it was. Under the data folder's one lock: so two commands at once start one,
    and a sender a window old -- done or stuck -- is followed by the next. Never raises, never waits on it."""
    try:
        import time

        from cad_server.analytics import ARRIVALS, FLUSH_SECONDS, SPOOL
        from cad_server._internal.file_lock import state
        from cad_server.settings import settings_path

        settings = Path(path or settings_path())
        now = time.time() if now is None else now
        waiting = [at for at in (_oldest(settings.with_name(SPOOL)), _oldest(settings.with_name(ARRIVALS)))
                   if at is not None]
        if not waiting or now - min(waiting) <= FLUSH_SECONDS:  # the common answer, read without the lock
            return False
        with state(settings.parent):
            last = _last(settings)
            if last is not None and now - last <= FLUSH_SECONDS:
                return False
            _started(settings, now)
        (spawn or _spawn)(settings)
        return True
    except Exception:  # noqa: BLE001 - a send never fails the command that asked for it
        import logging

        logging.getLogger("cad_server.analytics").debug("could not start the telemetry sender", exc_info=True)
        return False


def start_soon(path: Path | None = None, *, now: float | None = None,
               spawn: Callable[..., Any] | None = None) -> bool:
    """Start the sender for an arrival kept now (``analytics.arrival``): at once where none was started within a
    window (``STARTED``: in a folder no sender was started in, at once), else one that waits until that window is
    over; none where one is already set to start later, which takes what was kept now. Started under the lock, and
    ``STARTED``'s time then set to when the sender starts: a sender that could not be started leaves it as it was, for
    the next to try. Whether one was started. Never raises, never waits on it."""
    try:
        import time

        from cad_server.analytics import FLUSH_SECONDS
        from cad_server._internal.file_lock import state
        from cad_server.settings import settings_path

        settings = Path(path or settings_path())
        now = time.time() if now is None else now
        with state(settings.parent):
            last = _last(settings)
            if last is not None and last > now:  # a sender set to start later
                return False
            at = now if last is None else max(now, last + FLUSH_SECONDS)
            (spawn or _spawn)(settings, at=at if at > now else None)
            _started(settings, at)
        return True
    except Exception:  # noqa: BLE001 - a send never fails the step that asked for it
        import logging

        logging.getLogger("cad_server.analytics").debug("could not start the telemetry sender", exc_info=True)
        return False


def _oldest(spool: Path) -> float | None:
    """When the spool's oldest line was kept (its ``at``; the file's time for a line an older cadgen kept with
    none), or ``None`` for no spool."""
    import json

    try:
        with open(spool, encoding="utf-8") as handle:
            first = handle.readline()
        at = json.loads(first).get("at") if first.strip() else None
        return float(at) if isinstance(at, (int, float)) else spool.stat().st_mtime
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError):
        return spool.stat().st_mtime if spool.exists() else None


def _spawn(settings: Path, *, at: float | None = None) -> None:
    from cad_server.analytics import for_others

    detached: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                                if os.name == "nt" else {"start_new_session": True})
    later = [AT, repr(at)] if at is not None else []
    subprocess.Popen([sys.executable, "-P", "-m", "cad_server._internal.telemetry_send", *later],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd=str(settings.parent), env=for_others(os.environ), close_fds=True, **detached)


def send(path: Path | None = None, *, send: Callable[[dict[str, Any]], Any] | None = None) -> int:
    """Send what is waiting as the process ``cli``: a batch at a time, at most ``ROUNDS``, until one is not
    taken or nothing is left; the rest kept for the next sender. How many batches the receiver took."""
    from cad_server.analytics import Recorder

    recorder = Recorder(process="cli", path=path, send=send)
    sent = 0
    while sent < ROUNDS and recorder.flush():
        sent += 1
    recorder.close()
    return sent


def main(argv: list[str] | None = None) -> int:
    try:
        import time

        from cad_server.analytics import FLUSH_SECONDS

        argv = sys.argv[1:] if argv is None else argv
        if argv[:1] == [AT] and len(argv) == 2:
            time.sleep(min(max(0.0, float(argv[1]) - time.time()), FLUSH_SECONDS))
        send()
    except Exception:  # noqa: BLE001 - nobody reads this process's output: it ends quietly
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
