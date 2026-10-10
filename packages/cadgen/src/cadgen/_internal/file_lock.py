"""An exclusive lock between processes, held on a file of its own beside what it guards."""

from __future__ import annotations

import contextlib
import errno
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

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
