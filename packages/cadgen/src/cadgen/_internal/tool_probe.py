"""Finding a program cadgen runs but never installs (KiCad, WireViz, Graphviz, Java): where to
look, and what version it says it is.

Each tool's own module keeps what is particular to it: its places, its minimum version, its
missing-tool error and the sentence that says how to install it. These are the steps they share.
A program is asked its version once per process for each (mtime, size) it has, so a program
reinstalled under a running daemon is asked again.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

__all__ = ["candidates", "executable", "output", "version", "version_tuple"]


def executable(name: str) -> str:
    """``name`` as an executable's file name on this platform (``name.exe`` on Windows)."""
    return f"{name}.exe" if sys.platform.startswith("win") else name


def candidates(variable: str | None, places: Iterable[Path | str | None]) -> list[Path]:
    """Where to look, best first: ``variable``'s path alone when that variable is set, else each
    of ``places`` once, in order (a ``str`` is a command looked up on ``PATH``; ``None`` is skipped).
    ``places`` is read only when the variable is not set, so a generator's costly lookups wait."""
    explicit = os.environ.get(variable, "").strip() if variable else ""
    if explicit:
        return [Path(explicit).expanduser()]
    found: list[Path] = []
    for place in places:
        if isinstance(place, str):
            on_path = shutil.which(place)
            place = Path(on_path) if on_path else None
        if place is not None and place not in found:
            found.append(place)
    return found


def _stamp(path: Path) -> tuple[int, int] | None:
    """``path``'s (mtime, size), or ``None`` when there is nothing there."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=32)
def _run(command: str, flag: str, stamp: tuple[int, int]) -> tuple[str, str] | None:
    del stamp  # part of the cache key: a reinstalled program is asked again
    try:
        completed = subprocess.run([command, flag], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (completed.stdout or "", completed.stderr or "") if completed.returncode == 0 else None


def output(path: Path, flag: str) -> tuple[str, str] | None:
    """What ``path flag`` prints, as (stdout, stderr), when it runs and succeeds; else ``None``."""
    found = _stamp(path)
    return None if found is None else _run(str(path), flag, found)


def version(path: Path, flag: str, pattern: str) -> str | None:
    """The first group of ``pattern`` in what ``path flag`` prints (stdout, then stderr)."""
    printed = output(path, flag)
    match = re.search(pattern, "\n".join(printed)) if printed is not None else None
    return match.group(1) if match else None


def version_tuple(version: str) -> tuple[int, ...]:
    """The first three numbers of ``version``, to compare with a minimum: ``(0, 4, 1)``."""
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])
