"""``python -P -m cadgen._internal.telemetry_send``: send what commands counted, and exit.

A command sends nothing itself: it keeps what it counted in the spool beside the settings
(``analytics.spool``), which the CAD app's and the viewer's background sends take every window
(``analytics.FLUSH_SECONDS``). With neither running, nothing would. So a command that finds the spool's
oldest line older than a window, and no sender started within one (``STARTED``, beside the settings),
starts this module detached (``start_if_due``): no window, a process group or session of its own, its
output nowhere, the telemetry switches of the command's environment not inherited
(``analytics.for_others``: it goes by the person's settings) -- and goes on without waiting for it.

It sends as the process ``cli`` (``send``): the spool, the batches exiting processes kept, a batch at a
time until nothing is left or the receiver takes no more; what it could not send is kept for the next
sender (``Recorder.close``), and it exits. Nothing waits on it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

# Beside the settings: when the last sender was started (its time is the file's). A sender a window old is done
# or stuck; either way the next is started.
STARTED = "telemetry-sender"
ROUNDS = 8  # the most batches one sender sends: a spool past ``analytics.MAX_EVENTS`` events takes several


def start_if_due(path: Path | None = None, *, now: float | None = None,
                 spawn: Callable[[Path], Any] | None = None) -> bool:
    """Start the sender when the spool has waited longer than a window and none was started within one; whether
    it was. Under the settings lock, so two commands at once start one. Never raises, never waits on it."""
    try:
        import time

        from cadgen.analytics import FLUSH_SECONDS, SPOOL
        from cadgen._internal.file_lock import exclusive
        from cadgen.settings import LOCK, settings_path

        settings = Path(path or settings_path())
        now = time.time() if now is None else now
        oldest = _oldest(settings.with_name(SPOOL))
        if oldest is None or now - oldest <= FLUSH_SECONDS:  # the common answer, read without the lock
            return False
        started = settings.with_name(STARTED)
        with exclusive(settings.with_name(LOCK)):
            try:
                if now - started.stat().st_mtime <= FLUSH_SECONDS:
                    return False
            except FileNotFoundError:
                pass
            started.touch()
            os.utime(started, (now, now))
        (spawn or _spawn)(settings)
        return True
    except Exception:  # noqa: BLE001 - a send never fails the command that asked for it
        import logging

        logging.getLogger("cadgen.analytics").debug("could not start the telemetry sender", exc_info=True)
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


def _spawn(settings: Path) -> None:
    from cadgen.analytics import for_others

    detached: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                                if os.name == "nt" else {"start_new_session": True})
    subprocess.Popen([sys.executable, "-P", "-m", "cadgen._internal.telemetry_send"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(settings.parent),
                     env=for_others(os.environ), close_fds=True, **detached)


def send(path: Path | None = None, *, send: Callable[[dict[str, Any]], Any] | None = None) -> int:
    """Send what is waiting as the process ``cli``: a batch at a time, at most ``ROUNDS``, until one is not
    taken or nothing is left; the rest kept for the next sender. How many batches the receiver took."""
    from cadgen.analytics import Recorder

    recorder = Recorder(process="cli", path=path, send=send)
    sent = 0
    while sent < ROUNDS and recorder.flush():
        sent += 1
    recorder.close()
    return sent


def main() -> int:
    try:
        send()
    except Exception:  # noqa: BLE001 - nobody reads this process's output: it ends quietly
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
