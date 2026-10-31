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

A declared or exported file is written through ``put``: moved into place only when the file there
does not hold its bytes already, so writing the same translation twice writes it once and an
unchanged file keeps its bytes and its time. Inside ``together`` every ``put`` lands with the others or
not at all: a model's declared files, one of which its check refuses, leave every earlier file as it was.
"""

from __future__ import annotations

import contextlib
import contextvars
import errno
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterator

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


# The files each ``put`` inside ``together`` made, waiting to land: (staged file, target, its staging folder).
_PENDING: contextvars.ContextVar[list[tuple[Path, Path, Path]] | None] = contextvars.ContextVar("pending", default=None)


@contextlib.contextmanager
def together() -> Iterator[None]:
    """Every ``put`` in the block lands with the others or none does (law 17): each is written and
    checked in its staging folder and held there; once the block ends whole they are moved into
    place in order, the file each replaces linked aside in its staging folder until every one has
    landed. A block that raises lands nothing; a move that fails puts each earlier file back byte
    for byte and takes away each new one that had no file before it."""
    pending: list[tuple[Path, Path, Path]] = []
    token = _PENDING.set(pending)
    try:
        try:
            yield
        finally:
            _PENDING.reset(token)
        _land(pending)
    finally:
        for _temporary, _target, stage in pending:
            shutil.rmtree(stage, ignore_errors=True)


def _land(pending: list[tuple[Path, Path, Path]]) -> None:
    """``together``'s moves, each undone when a later one fails."""
    landed: list[tuple[Path, Path | None]] = []
    try:
        for temporary, target, stage in pending:
            earlier: Path | None = stage / f".earlier.{target.name}"
            try:
                os.link(target, earlier)  # the earlier file itself, its bytes and its time, kept aside
            except FileNotFoundError:
                earlier = None
            except OSError:  # a folder that takes no hard link: a copy of it
                shutil.copy2(target, earlier)
            landed.append((target, earlier))
            replace_atomic(temporary, target)
    except BaseException:
        for target, earlier in reversed(landed):
            with contextlib.suppress(OSError):
                if earlier is not None:
                    replace_atomic(earlier, target)
                else:
                    target.unlink(missing_ok=True)
        raise


# The refusals that say the target's folder takes no new file from this user.
_REFUSED = (errno.EACCES, errno.EPERM, errno.EROFS)


def put(target: Path | str, write: Callable[[Path], None], *, compare: bool = True,
        staged: str | None = None) -> tuple[bool, int]:
    """Write ``target`` with ``write(path)`` -- the new file made at ``path``, named ``staged`` (else
    the target's name) -- staged beside it and moved over it (``staging``, ``replace_atomic``). With
    ``compare``, a target that holds the new bytes already is left as it is, written to nothing.
    A folder that refuses the staging folder (read-only) is written to only when the bytes differ:
    they are made aside and compared, and a changed or missing target fails in one line naming the
    folder and its mode. Returns whether the target was written, and its size."""
    target = Path(target)
    name = staged or target.name
    try:
        stage: Path | None = Path(tempfile.mkdtemp(prefix=f".{target.stem}.", suffix=".tmp", dir=target.parent))
    except OSError as error:
        if error.errno not in _REFUSED:
            raise
        stage = None
    try:
        with contextlib.ExitStack() as aside:
            folder = stage or Path(aside.enter_context(tempfile.TemporaryDirectory(prefix="cadgen-")))
            temporary = folder / name
            write(temporary)
            size = temporary.stat().st_size
            if (compare or stage is None) and same_bytes(target, temporary):
                return False, size
            if stage is None:
                raise PermissionError(refused_folder(target))
            pending = _PENDING.get()
            if pending is not None:
                # Landed with the rest of its set (``together``), which removes the folder.
                pending.append((temporary, target, stage))
                stage = None
                return True, size
            replace_atomic(temporary, target)
            return True, size
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def refused_folder(target: Path) -> str:
    """The one line a changed file in a folder that takes no new file says."""
    try:
        mode = f"mode {stat.S_IMODE(os.stat(target.parent).st_mode):04o}"
    except OSError:
        mode = "its mode unreadable"
    change = "changed" if target.exists() else "is new"
    return f"{target.name} {change} and cannot be written: its folder {target.parent} is read-only ({mode})"


def same_bytes(first: Path, second: Path) -> bool:
    """Whether the file ``first`` exists and holds the bytes of ``second``."""
    try:
        if os.stat(first).st_size != os.stat(second).st_size:
            return False
        with open(first, "rb") as one, open(second, "rb") as two:
            while True:
                a, b = one.read(1 << 22), two.read(1 << 22)
                if a != b:
                    return False
                if not a:
                    return True
    except OSError:
        return False


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
