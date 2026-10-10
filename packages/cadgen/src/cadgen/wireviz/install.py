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

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from cadgen._internal import tool_probe

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


def _wireviz_candidates() -> list[Path]:
    return tool_probe.candidates("CADGEN_WIREVIZ", ["wireviz", Path.home() / ".local" / "bin" / tool_probe.executable("wireviz")])


def _dot_candidates() -> list[Path]:
    places: list[Path] = []
    if sys.platform == "darwin":
        places = [Path("/opt/homebrew/bin/dot"), Path("/usr/local/bin/dot"), Path("/opt/local/bin/dot")]
    elif sys.platform.startswith("win"):
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                places += sorted(Path(root).glob("Graphviz*/bin/dot.exe"), reverse=True)
    else:
        places = [Path("/usr/bin/dot"), Path("/usr/local/bin/dot")]
    return tool_probe.candidates(None, ["dot", *places])


def _find_dot() -> tuple[Path, str]:
    for candidate in _dot_candidates():
        version = tool_probe.version(candidate, "-V", r"graphviz version (\S+)")
        if version is not None:
            return candidate, version
    raise WirevizMissingError(f"Graphviz's dot, which WireViz draws with, was not found: {install_hint()}")


def find_wireviz(*, dot: bool = True) -> WirevizInstall:
    """The WireViz this process uses (and, with ``dot``, the Graphviz it draws with)."""
    too_old: list[str] = []
    for candidate in _wireviz_candidates():
        version = tool_probe.version(candidate, "--version", r"WireViz (\d+(?:\.\d+)*)")
        if version is None:
            continue
        if tool_probe.version_tuple(version) < WIREVIZ_MINIMUM:
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
