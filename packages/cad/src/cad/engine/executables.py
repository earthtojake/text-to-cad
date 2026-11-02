"""An operating-system helper (a file manager, a clipboard tool, a file chooser, fontconfig) found
by name for a process that runs for others: the engine daemon and its children, which stand in a
folder the person never chose and keep the PATH of whichever client started them.

``find`` looks only in PATH's absolute folders and answers an absolute path, so a helper is never
an empty, ``.`` or relative PATH entry resolved against the working folder (where another user may
have put a file of that name), nor, on Windows, the working folder searched before PATH."""

from __future__ import annotations

import os
import sys

__all__ = ["find"]


def find(name: str) -> str | None:
    """The executable ``name`` (a bare name, as ``shutil.which`` takes) in one of PATH's absolute
    folders, as an absolute path; None when none of them holds it."""
    if os.path.basename(name) != name or not name:
        raise ValueError(f"{name!r} is not a bare executable name")
    suffixes = [""]
    if sys.platform == "win32":
        extensions = [ext for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if ext]
        if not any(name.lower().endswith(ext.lower()) for ext in extensions):
            suffixes = extensions
    for folder in os.environ.get("PATH", os.defpath).split(os.pathsep):
        folder = folder.strip().strip('"')
        if not folder or not os.path.isabs(folder):
            continue
        for suffix in suffixes:
            candidate = os.path.join(folder, name + suffix)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None
