"""An exclusive lock between processes, held on a file of its own beside what it guards."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def exclusive(lock_path: Path) -> Iterator[None]:
    """Hold ``lock_path`` exclusively, waiting for any other holder. The file stays: deleting it
    while another process waits on it would hand that process a lock nobody else can see."""
    with open(lock_path, "a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
