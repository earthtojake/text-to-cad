"""The one atomic rename every artifact writer uses.

Every cached artifact is written to a temp file and renamed into place, so a reader never sees
a half-written payload. On a Windows SMB share that rename is not reliably atomic-and-instant:
the redirector can still hold the handle Python just closed, and the rename loses with
``WinError 32`` (ERROR_SHARING_VIOLATION, "file is being used by another process"). Under a
parallel component build it happens reliably -- see issue #241, where 8 workers failed every
time on a NAS and ``CADGEN_COMPONENT_WORKERS=1`` succeeded.

The remedy is a short bounded retry, and the reason it lives here rather than at each writer is
that there are seven of these renames in a build's write path. Hardening one moves the failure
to the next: the reporter's traceback caught the GLB writer's inner rename, with the outer
component rename one frame away.

Deliberately narrow:

* only ``WinError 32`` retries. A denial (5) or a missing directory is a real error and must
  surface at once, not 350 ms later.
* the attribute does not exist off Windows, so this is exactly ``os.replace`` on POSIX.
* five attempts over 750 ms, then the original error propagates. A rename that cannot win in
  that window is not a deferred close, and a build that hangs retrying is worse than one that
  says what happened.

The window is sized for the TAIL, not the median, and that distinction is the whole of issue
#274. 350 ms looked generous per rename and was: measured on a Synology SMB share over two
84-component builds, 126 of 168 renames blocked at all, median 31 ms, p90 118 ms -- and max
389 ms, just past the old budget. But the budget is spent per rename while the BUILD only
succeeds if every rename wins, and a large assembly draws from that distribution a hundred-odd
times. At 168 renames even a 1% per-rename loss rate leaves roughly a 1-in-5 chance of a clean
build, which is what the reporter saw: 1 of 3 runs completing, each failure on a different
component. Widening costs the common case nothing, because a 31 ms median still wins on the
first or second retry.

The 750 ms window is not the end of it, and a bigger constant is not the answer. Remeasured on
0.4.13 across eight instrumented builds: 413 of 2067 renames blocked, median 31 ms, p90 78 ms,
p99 265 ms -- and max 797 ms. Exactly one rename in 2067 beat the window, and one is all it
takes. The tail is long and thin, so any finite window eventually loses to it and chasing it
trades a bounded wait for a slow creep.

So the ladder is not the last word: when it is exhausted, ``replace_atomic`` copies the temp file
sideways under a name the server has never seen and runs the ladder once more on the copy. The
violation belongs to the handle the server still holds on the ORIGINAL temp file; the deferred
close pins that handle, reads do not conflict with it, and the copy carries no handle of its own.
One extra copy in the rare tail case, still strictly bounded -- the same principle the window was
chosen under.

It lives here rather than in ``write_bytes_atomic`` because most of these renames have no payload
to rewrite. A measured gate run on the reporter's NAS put every remaining failure at the component
GLB rename, which streams its bytes to disk and hands this helper a finished file; five other call
sites do the same, and a branch in flight adds a seventh. Hardening the writer would have left all
of them out, which is the rule the docstring above already states.

What this cannot do: ``os.replace`` is also refused when something holds the DESTINATION open --
a reader with the artifact mapped, or a virus scanner sweeping it. No source-side trick reaches
that case, and the second ladder is simply a bounded futile wait when it happens. The reported and
measured failure is the source handle; this covers that one.
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
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


def temp_suffix() -> str:
    """A collision-free suffix for a sibling temp file, ending in ``.tmp``.

    ``os.urandom`` rather than a clock: two writes inside one clock tick would otherwise collide,
    and the rescue below depends on the new name being genuinely new rather than on the timer's
    resolution. The ``.tmp`` ending matters too -- ``.gitignore`` carries ``*.tmp``, so a temp
    file leaked in the deep tail stays invisible to ``git add -A``.
    """
    return f".{os.getpid()}.{os.urandom(4).hex()}.tmp"


def _run_ladder(temp_path: Path | str, target_path: Path | str) -> OSError | None:
    """Run the bounded retry, returning the sharing violation it could not beat.

    Any other error propagates at once: a denial (5) or a missing directory is a real error and
    must surface immediately, not 750 ms later.
    """
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            os.replace(temp_path, target_path)
            return None
        except OSError as error:
            if getattr(error, "winerror", None) != WINDOWS_SHARING_VIOLATION:
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
