"""Where WireViz is: the ``wireviz`` command, and the Graphviz ``dot`` it draws with.

WireViz is a separate program (GPL-3.0): cadgen never imports it and never
installs it; it finds one and runs it. In this order:

1. ``CADGEN_WIREVIZ``, the full path of a ``wireviz`` to use;
2. ``wireviz`` on ``PATH``;
3. where ``uv tool install`` and ``pipx install`` put commands:
   ``~/.local/bin`` (``%USERPROFILE%\\.local\\bin`` on Windows).

WireViz draws with Graphviz's ``dot``, which it expects on ``PATH``; cadgen
also looks where Graphviz's installers put it (Homebrew's ``bin`` folders on
macOS, ``Program Files\\Graphviz\\bin`` on Windows, ``/usr/bin`` on Linux) and
hands that folder to WireViz. Only a drawing needs ``dot``: listing a
harness's bill of materials does not.

A WireViz older than :data:`WIREVIZ_MINIMUM` is refused: cadgen writes that
release's connection syntax. Nothing here runs at import; the probes run once
per process for a given executable.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "WIREVIZ_MINIMUM",
    "WirevizInstall",
    "WirevizMissingError",
    "find_wireviz",
    "install_hint",
]

#: The WireViz release whose document syntax cadgen writes.
WIREVIZ_MINIMUM = (0, 4)


class WirevizMissingError(RuntimeError):
    """No usable WireViz or Graphviz: none found, or too old. The message says what to do."""


@dataclass(frozen=True)
class WirevizInstall:
    cli: Path
    version: str
    #: Graphviz's ``dot``, when it was asked for (a drawing needs it, a BOM does not).
    dot: Path | None = None
    graphviz_version: str | None = None

    def env(self) -> dict[str, str]:
        """The environment a ``wireviz`` run gets: ``dot``'s folder first on ``PATH``."""
        env = dict(os.environ)
        if self.dot is not None:
            env["PATH"] = os.pathsep.join([str(self.dot.parent), env.get("PATH", "")])
        return env


def install_hint() -> str:
    """How to get WireViz and Graphviz on this platform, as one sentence a person can act on."""
    wireviz = "WireViz in its own tool environment (`uv tool install wireviz`, or `pipx install wireviz`)"
    if sys.platform == "darwin":
        return f"install Graphviz (`brew install graphviz`) and {wireviz}, or set CADGEN_WIREVIZ to its wireviz"
    if sys.platform.startswith("win"):
        return (
            "install Graphviz from https://graphviz.org/download/ (let its installer add it to PATH) and "
            f"{wireviz}, or set CADGEN_WIREVIZ to its wireviz.exe"
        )
    return (
        "install Graphviz (Ubuntu and Debian: `sudo apt install graphviz`; others: https://graphviz.org/download/) "
        f"and {wireviz}, or set CADGEN_WIREVIZ to its wireviz"
    )


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def _executable(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def _wireviz_candidates() -> list[Path]:
    explicit = os.environ.get("CADGEN_WIREVIZ", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    found: list[Path] = []
    on_path = shutil.which("wireviz")
    if on_path:
        found.append(Path(on_path))
    found.append(Path.home() / ".local" / "bin" / _executable("wireviz"))
    return found


def _dot_candidates() -> list[Path]:
    found: list[Path] = []
    on_path = shutil.which("dot")
    if on_path:
        found.append(Path(on_path))
    if sys.platform == "darwin":
        found += [Path("/opt/homebrew/bin/dot"), Path("/usr/local/bin/dot"), Path("/opt/local/bin/dot")]
    elif sys.platform.startswith("win"):
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                found += sorted(Path(root).glob("Graphviz*/bin/dot.exe"), reverse=True)
    else:
        found += [Path("/usr/bin/dot"), Path("/usr/local/bin/dot")]
    return found


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=8)
def _probe(command: str, flag: str, pattern: str, stamp: tuple[int, int]) -> str | None:
    del stamp  # part of the cache key: a reinstalled program is probed again
    try:
        completed = subprocess.run([command, flag], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    match = re.search(pattern, (completed.stdout or "") + "\n" + (completed.stderr or ""))
    return match.group(1) if match else None


def _find_dot() -> tuple[Path, str]:
    for candidate in _dot_candidates():
        stamp = _stamp(candidate)
        if stamp is None:
            continue
        version = _probe(str(candidate), "-V", r"graphviz version (\S+)", stamp)
        if version is not None:
            return candidate, version
    raise WirevizMissingError(f"Graphviz's dot, which WireViz draws with, was not found: {install_hint()}")


def find_wireviz(*, dot: bool = True) -> WirevizInstall:
    """The WireViz this process uses (and, with ``dot``, the Graphviz it draws with)."""
    too_old: list[str] = []
    for candidate in _wireviz_candidates():
        stamp = _stamp(candidate)
        if stamp is None:
            continue
        version = _probe(str(candidate), "--version", r"WireViz (\d+(?:\.\d+)*)", stamp)
        if version is None:
            continue
        if _version_tuple(version) < WIREVIZ_MINIMUM:
            too_old.append(f"{candidate} is WireViz {version}")
            continue
        if not dot:
            return WirevizInstall(cli=candidate, version=version)
        dot_path, graphviz_version = _find_dot()
        return WirevizInstall(cli=candidate, version=version, dot=dot_path, graphviz_version=graphviz_version)
    minimum = ".".join(str(part) for part in WIREVIZ_MINIMUM)
    if too_old:
        raise WirevizMissingError(f"cadgen writes WireViz {minimum} documents, but {'; '.join(too_old)}: {install_hint()}")
    raise WirevizMissingError(f"WireViz's command line, wireviz, was not found: {install_hint()}")
