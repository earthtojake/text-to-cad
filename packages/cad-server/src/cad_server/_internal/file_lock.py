"""An exclusive lock between processes, held on a file of its own beside what it guards, and the
state folder's one lock (``state``), which every change of a small file there holds."""

from __future__ import annotations

import contextlib
import errno
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

# The state folder's one lock: every read-change-write of a small file there -- the settings, the
# install channels, the telemetry spool and the batches kept, the start of a telemetry sender --
# holds it (``state``), so none needs a lock file of its own. Named as cadgen 0.7 names the
# settings' lock, so a 0.7 still installed and this cadgen changing the settings exclude each other.
# Its time is when the last telemetry sender was started (``telemetry_send.start_if_due``): nothing
# else changes it, as taking a lock writes nothing.
STATE_LOCK = "settings.lock"

# What msvcrt.locking raises when LK_LOCK gives up: it tries ten times, a second apart.
_WINDOWS_GAVE_UP = {getattr(errno, "EDEADLOCK", errno.EDEADLK), errno.EDEADLK, errno.EACCES}


@contextlib.contextmanager
def exclusive(lock_path: Path, *, waiting: Callable[[], None] | None = None) -> Iterator[None]:
    """Hold ``lock_path`` exclusively, waiting for any other holder, however long it holds it.
    ``waiting`` is called once, before that wait, when another process holds the lock. The file
    stays: deleting it while another process waits on it would hand that process a lock nobody
    else can see."""
    with open(lock_path, "a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                if waiting is not None:
                    waiting()
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError as error:
                        # LK_LOCK gives up after ten seconds; flock below waits for good, so this does too.
                        if error.errno not in _WINDOWS_GAVE_UP:
                            raise
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if waiting is not None:
                    waiting()
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def state(folder: Path, *, waiting: Callable[[], None] | None = None) -> contextlib.AbstractContextManager[None]:
    """Hold the state folder's one lock (``STATE_LOCK`` in ``folder``), waiting for any other holder."""
    return exclusive(folder / STATE_LOCK, waiting=waiting)
