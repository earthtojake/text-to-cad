"""Find a user-installed ``kicad-cli``, KiCad's command line, and ask it its version. Viewing boards
requires no KiCad installation.

The ``kicad`` integration's probe (``cad.registry.INTEGRATIONS["kicad"]``), run by the server's one
helper for the external programs our code runs (``cad._internal.programs``), the standard library
alone, so the library's ``@kicad_pcb`` and the server's commands find and run it the same way. The server never
starts KiCad itself: what this finds is always an executable named exactly ``kicad-cli``
(``kicad-cli.exe`` on Windows) -- ``CAD_KICAD_CLI``, refused unless it names one, then ``kicad-cli`` on
PATH, then the command line inside the usual macOS or Windows installation -- never ``kicad``, a
wrapper (``kicad-cli-nightly``) or a desktop launcher. Every run of it is headless and reads, writes or
locks nothing of the person's: it gets homes of its own (``headless_env``).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cad.registry import INTEGRATIONS

from cad._internal import programs
from cad._internal.programs import version_tuple

__all__ = ["CLI_NAMES", "KICAD", "KICAD_MINIMUM", "KicadMissingError", "KicadRunError", "check_version",
           "find_kicad_cli", "headless_env", "install_hint", "kicad_version", "private_run", "quiet"]

# What kicad-cli says on stderr that says nothing about the board.
_NOISE = ("Fontconfig error",)


class KicadRunError(RuntimeError):
    """``kicad-cli`` failed; the message carries what it said."""


def quiet(text: str) -> str:
    """What kicad-cli said, without its noise."""
    return "\n".join(line for line in (text or "").splitlines() if line.strip() and not line.startswith(_NOISE))

_PROBE = INTEGRATIONS["kicad"].probe
assert _PROBE is not None
# The one program the server runs of KiCad's, by its file name on each platform.
CLI_NAMES = ("kicad-cli", "kicad-cli.exe")
# KiCad's own homes, beside the ones every program run gets (``programs.headless_env``). Without the
# documents and cache ones KiCad 10 still writes ``~/.local/share/kicad/<ver>`` and ``~/.cache/kicad/<ver>``.
# ``KICAD_STOCK_DATA_HOME`` is left alone: a user's KiCad finds its stock libraries and schemas by it,
# and only a packaged kicad-cli would need it set.
_HOMES = {"KICAD_CONFIG_HOME": "settings", "KICAD_DOCUMENTS_HOME": "documents", "KICAD_CACHE_HOME": "cache"}


class KicadMissingError(programs.ProgramMissing):
    """No usable KiCad command line."""


def install_hint() -> str:
    return _PROBE.install_hint


def _installed() -> list[Path]:
    """The command line inside the usual installation folders, newest version first: the binary in
    the macOS bundle (never the app, never ``open``), and ``bin/kicad-cli.exe`` under Program Files."""
    if sys.platform == "darwin":
        return [Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")]
    if sys.platform.startswith("win"):
        folder = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "KiCad"
        if folder.is_dir():
            versions = sorted(folder.iterdir(), key=lambda path: version_tuple(path.name), reverse=True)
            return [version / "bin" / "kicad-cli.exe" for version in versions]
    return []


#: ``kicad-cli`` as the helper runs it.
KICAD = programs.Program.from_probe(_PROBE, names=CLI_NAMES, installed=lambda: _installed(), homes=_HOMES,
                                     title="KiCad 9")
KICAD_MINIMUM = KICAD.minimum


def _missing(error: programs.ProgramMissing) -> KicadMissingError:
    return KicadMissingError(str(error))


def find_kicad_cli() -> Path:
    """The ``kicad-cli`` to run: ``CAD_KICAD_CLI`` when it is set (a ``kicad-cli`` that is a file,
    else refused), else ``kicad-cli`` on PATH, else the one inside the platform's usual installation."""
    try:
        return programs.find(KICAD)
    except KicadMissingError:
        raise
    except programs.ProgramMissing as error:
        raise _missing(error) from None


def headless_env(root: str | os.PathLike) -> dict[str, str]:
    """The environment every ``kicad-cli`` run gets (``programs.headless_env``), with KiCad's own homes,
    ``KICAD_CONFIG_HOME`` (``root/settings``), ``KICAD_DOCUMENTS_HOME`` and ``KICAD_CACHE_HOME``, inside
    ``root`` too."""
    return programs.headless_env(root, _HOMES)


@contextmanager
def private_run(prefix: str = "cad-kicad-") -> Iterator[tuple[Path, dict[str, str]]]:
    """A private folder and the headless environment inside it, for one ``kicad-cli`` run; the folder
    (with whatever KiCad left in it) is removed afterwards. Yields ``(folder, env)``."""
    with programs.private_run(prefix, _HOMES) as run:
        yield run


def kicad_version(cli: Path) -> str | None:
    """What ``kicad-cli version`` says it is (``9.0.1``), run headless; None when it does not run."""
    return programs.version(KICAD, cli)


def check_version(cli: Path, version: str | None) -> str:
    try:
        return programs.check_version(KICAD, cli, version)
    except programs.ProgramMissing as error:
        raise _missing(error) from None
