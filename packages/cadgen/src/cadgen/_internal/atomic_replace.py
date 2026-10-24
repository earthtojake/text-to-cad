"""The one atomic rename every file cadgen writes outside the engine goes through.

The settings, the model library, the channel record, the telemetry spool and batches, a Quick
Edit packet: each is written to a temp file and renamed into place, so a reader never sees a
half-written payload. (The engine keeps its own copy of this rule, ``cadgen.engine.atomic_replace``:
it imports nothing of cadgen.) On a Windows SMB share that rename is not reliably atomic-and-instant:
the redirector can still hold the handle Python just closed, and the rename loses with
``WinError 32`` (ERROR_SHARING_VIOLATION, "file is being used by another process") -- issue #241,
where 8 workers failed every time on a NAS and one worker succeeded.

Deliberately narrow:

* only ``WinError 32``, and ``WinError 5`` onto an existing FILE, retry (see below for the
  second). A denial with no file in the way -- a read-only folder, a directory at the target --
  or a missing directory is a real error and must surface at once, not 350 ms later.
* the attribute does not exist off Windows, so this is exactly ``os.replace`` on POSIX.
* five attempts over 750 ms, then the original error propagates.

The window is sized for the TAIL, not the median (issue #274): measured on a Synology SMB share,
the median blocked rename waited 31 ms, p99 265 ms, max 797 ms. The tail is long and thin, so any
finite window eventually loses to it, and a bigger constant is not the answer: when the ladder is
exhausted, ``replace_atomic`` copies the temp file sideways under a name the server has never seen
and runs the ladder once more on the copy. The violation belongs to the handle the server still
holds on the ORIGINAL temp file; the copy carries no handle of its own.

The DESTINATION has its own failure, and it answers with a different code. NTFS refuses to
rename over a file that any process holds open -- ``MoveFileEx`` without POSIX semantics, which is
what ``os.replace`` is -- and says ``WinError 5`` (ERROR_ACCESS_DENIED), not 32: two processes
writing one settings file each read what they just wrote. The hold is a read that ends in
milliseconds, so the same ladder waits it out; the retry is keyed on a FILE at the target, because
that is the only case where a ``5`` can be somebody else's handle.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import time
from pathlib import Path

# ERROR_SHARING_VIOLATION: the file is open in another process -- or, on SMB, was open a moment
# ago and the server has not caught up.
WINDOWS_SHARING_VIOLATION = 32
# ERROR_ACCESS_DENIED: what a rename answers when another process holds the DESTINATION open
# (or is renaming onto it). Retried only when a file is there -- see the module docstring.
WINDOWS_ACCESS_DENIED = 5
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


def temp_suffix() -> str:
    """A collision-free suffix for a sibling temp file, ending in ``.tmp``.

    ``os.urandom`` rather than a clock: two writes inside one clock tick would otherwise collide,
    and the rescue below depends on the new name being genuinely new rather than on the timer's
    resolution. The ``.tmp`` ending matters too -- ``.gitignore`` carries ``*.tmp``, so a temp
    file leaked in the deep tail stays invisible to ``git add -A``.
    """
    return f".{os.getpid()}.{os.urandom(4).hex()}.tmp"


def _held(error: OSError, target_path: Path | str) -> bool:
    """Whether a refused rename is a handle someone will let go of.

    A sharing violation always is. A denial is only when a FILE is at the target: that is the
    code NTFS gives a rename over a file another process has open. With nothing there, or a
    directory in the way, a denial is a real one.
    """
    code = getattr(error, "winerror", None)
    if code == WINDOWS_SHARING_VIOLATION:
        return True
    return code == WINDOWS_ACCESS_DENIED and os.path.isfile(target_path)


def _run_ladder(temp_path: Path | str, target_path: Path | str) -> OSError | None:
    """Run the bounded retry, returning the held-handle refusal it could not beat.

    Any other error propagates at once: a real denial or a missing directory must surface
    immediately, not 750 ms later.
    """
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            os.replace(temp_path, target_path)
            return None
        except OSError as error:
            if not _held(error, target_path):
                raise
            if delay is None:
                return error
            time.sleep(delay)
    return None


def replace_atomic(temp_path: Path | str, target_path: Path | str) -> None:
    """``os.replace`` with a bounded retry, then one retry from a copy the server has not seen."""
    blocked = _run_ladder(temp_path, target_path)
    if blocked is None:
        return

    source = Path(temp_path)
    fresh = source.with_name(f"{source.name}{temp_suffix()}")
    try:
        shutil.copyfile(source, fresh)
    except OSError:
        # The source is pinned for reading too, so there is nothing left to try. Report the
        # rename failure, which is the one the caller was waiting on.
        raise blocked from None

    # Best effort: the handle that blocked the rename usually blocks this as well.
    with contextlib.suppress(OSError):
        source.unlink(missing_ok=True)

    try:
        if _run_ladder(fresh, target_path) is not None:
            raise blocked
    finally:
        with contextlib.suppress(OSError):
            fresh.unlink(missing_ok=True)


def write_bytes_atomic(target_path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``target_path`` through a temp file in the same directory.

    Same directory on purpose: a rename across filesystems is not atomic, and a temp dir on
    another volume would silently turn this into a copy.
    """
    resolved = Path(target_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temp_path = resolved.with_name(f"{resolved.name}{temp_suffix()}")
    try:
        temp_path.write_bytes(payload)
        replace_atomic(temp_path, resolved)
    finally:
        # Suppressed: on Windows the handle that blocks a rename blocks the delete too, and
        # letting that escape here would mask the rename failure the caller needs to see.
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
