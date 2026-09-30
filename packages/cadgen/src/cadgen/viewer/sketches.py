"""Pictures a prompt names by path: a Quick Edit's sketch.

A copied Quick Edit is text, and text cannot carry a picture. So the view with a
person's sketch drawn over it is saved here and the copied text names the file:
anything that can read a file can look at it. It is scratch, not state: the
system's temporary directory holds it, named as the view names it
(``bracket-sketch.png``) and for its own bytes (the same picture saved twice is
one file), and only the newest ``KEEP`` are kept.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from cadgen._internal.atomic_replace import write_bytes_atomic

MAX_PNG_BYTES = 20 * 1024 * 1024
KEEP = 64
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sketches_dir() -> Path:
    """Where sketches are saved: the system's temporary directory, which the system clears."""
    return Path(tempfile.gettempdir()) / "cadgen-sketches"


def _stem(name: str) -> str:
    stem = os.path.splitext(os.path.basename(str(name or "").replace("\\", "/")))[0]
    return _UNSAFE.sub("-", stem).strip("-.")[:48] or "sketch"


def _prune(directory: Path, keep: int) -> None:
    sketches = []
    for entry in os.scandir(directory):
        if entry.name.endswith(".png") and entry.is_file(follow_symlinks=False):
            try:
                sketches.append((entry.stat().st_mtime_ns, entry.path))
            except OSError:
                continue
    for _, path in sorted(sketches, reverse=True)[keep:]:
        try:
            os.unlink(path)
        except OSError:
            pass


def save_sketch(png: bytes, name: str = "") -> str:
    """Save ``png`` (the view with its sketch) under the name the view gives it; its absolute path."""
    if len(png) > MAX_PNG_BYTES or not png.startswith(_PNG_SIGNATURE):
        raise ValueError("A sketch is a PNG image of at most 20 MiB")
    directory = sketches_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_stem(name)}-{hashlib.sha256(png).hexdigest()[:12]}.png"
    if path.is_file():
        # Saved before: it is the newest again, so pruning keeps it.
        os.utime(path)
    else:
        write_bytes_atomic(path, png)
    _prune(directory, KEEP)
    return str(path)
