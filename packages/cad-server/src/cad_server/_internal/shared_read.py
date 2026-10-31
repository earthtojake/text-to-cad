"""Open a file for reading without standing in the way of its deletion.

POSIX never lets a reader's handle stop an unlink or a rename. Windows does:
``open()`` asks ``CreateFile`` for ``FILE_SHARE_READ | FILE_SHARE_WRITE`` and
leaves out ``FILE_SHARE_DELETE``, so while ANY handle opened that way is alive,
deleting the file, renaming it or replacing it fails with ``WinError 32``
(ERROR_SHARING_VIOLATION) for everyone else.

A reader that merely looks — the CAD Viewer hashing a model for its catalog row
on a background thread, a status poll hashing a STEP to find its tree — must
not turn the user's ``rm part.stl`` into that error. So those readers open
through here, which on Windows asks for all three share modes. The read itself
is unchanged; a file deleted while it is open simply finishes reading the bytes
it had, and the next scan no longer lists it.

It is not a cure for renaming ONTO an open file: NTFS refuses that without
POSIX rename semantics whatever the share mode (``WinError 5``), which is why
``atomic_replace`` retries it.

Off Windows this is exactly ``open(path, "rb")``.
"""

from __future__ import annotations

import os
import sys
from typing import BinaryIO

__all__ = ["open_shared_for_read"]

_GENERIC_READ = 0x80000000
_FILE_SHARE_READ_WRITE_DELETE = 0x1 | 0x2 | 0x4
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80


def open_shared_for_read(path) -> BinaryIO:
    """A binary read handle that never blocks another process deleting the file.

    Raises the same ``OSError`` subclasses ``open`` does (``FileNotFoundError``
    for a file that is already gone), so callers keep their existing handling.
    """
    if sys.platform != "win32":
        return open(path, "rb")
    import _winapi
    import msvcrt

    handle = _winapi.CreateFile(
        os.fspath(path),
        _GENERIC_READ,
        _FILE_SHARE_READ_WRITE_DELETE,
        _winapi.NULL,
        _OPEN_EXISTING,
        _FILE_ATTRIBUTE_NORMAL,
        _winapi.NULL,
    )
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        _winapi.CloseHandle(handle)
        raise
    return os.fdopen(descriptor, "rb")
