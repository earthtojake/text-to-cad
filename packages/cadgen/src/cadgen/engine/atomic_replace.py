"""The one rename every engine writer moves a finished file into place with.

Every file the engine writes is written beside its target first and renamed over it, so a reader
never sees half of one. It is written in a folder made beside the target for that one writer
(``staging``): a name no one can know first, closed to everyone else, so nothing another user put
in the target's folder is written through or moved into place. On Windows that rename can be refused by a handle that is about to
close: ``WinError 32`` (a sharing violation; on an SMB share the redirector still holds the
handle Python just closed) and ``WinError 5`` when another process has the DESTINATION open --
two builds of one model, each reading back the document the other is replacing. Both wait out
a short bounded ladder; then the file is copied sideways under a name the server has never
seen, whose handle nothing holds, and the ladder runs once more on the copy. Any other error,
and a ``5`` with no file at the target, surfaces at once. Off Windows this is ``os.replace``.

It is cadgen's own policy (``cadgen._internal.atomic_replace``, whose docstring has the
measurements) kept in the engine because the engine imports nothing of cadgen outside itself.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Iterator

WINDOWS_SHARING_VIOLATION = 32
WINDOWS_ACCESS_DENIED = 5
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


def _held(error: OSError, target: Path | str) -> bool:
    """Whether a refused rename is a handle someone will let go of."""
    code = getattr(error, "winerror", None)
    if code == WINDOWS_SHARING_VIOLATION:
        return True
    return code == WINDOWS_ACCESS_DENIED and os.path.isfile(target)


def _ladder(source: Path | str, target: Path | str) -> OSError | None:
    """The bounded retry; the held-handle refusal it could not beat, or None."""
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            os.replace(source, target)
            return None
        except OSError as error:
            if not _held(error, target):
                raise
            if delay is None:
                return error
            time.sleep(delay)
    return None


@contextlib.contextmanager
def staging(target: Path | str) -> Iterator[Path]:
    """Where to write ``target`` before it is moved over it (``replace_atomic``): a path of the same
    name in a folder made beside it for this writer alone (``tempfile.mkdtemp``: a fresh random
    name, mode 0700, ``*.tmp`` so a checkout ignores it). Whatever is left in it goes with the
    folder when the block ends."""
    target = Path(target)
    folder = Path(tempfile.mkdtemp(prefix=f".{target.stem}.", suffix=".tmp", dir=target.parent))
    try:
        yield folder / target.name
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def replace_atomic(source: Path | str, target: Path | str) -> None:
    """``os.replace`` with a bounded retry, then one retry from a copy the server has not seen."""
    blocked = _ladder(source, target)
    if blocked is None:
        return
    source = Path(source)
    fresh = source.with_name(f"{source.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        shutil.copyfile(source, fresh)
    except OSError:
        raise blocked from None
    with contextlib.suppress(OSError):  # the handle that blocked the rename usually blocks this too
        source.unlink(missing_ok=True)
    try:
        if _ladder(fresh, target) is not None:
            raise blocked
    finally:
        with contextlib.suppress(OSError):
            fresh.unlink(missing_ok=True)
