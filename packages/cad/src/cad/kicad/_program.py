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
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cad.registry import INTEGRATIONS

from cad._internal import programs
from cad._internal.programs import version_tuple

__all__ = ["API_SERVER_HINT", "CLI_NAMES", "KICAD", "KICAD_MINIMUM", "KicadMissingError", "KicadRunError",
           "check_api_server", "check_version", "find_kicad_cli", "headless_env", "install_hint", "kicad_version",
           "private_run", "project_as_found", "quiet"]

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
#: What a board script needs beyond a check's or an export's kicad-cli: its headless api-server.
API_SERVER_HINT = ("a @kicad_pcb board script runs kicad-cli's headless api-server, which only a KiCad nightly "
                   "(10.99) has for now; a check or an export needs only KiCad 9 or newer. Install a nightly from "
                   "https://www.kicad.org/download/, or set CAD_KICAD_CLI to a nightly's kicad-cli")
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


# The project files kicad-cli makes beside a board it only reads, when they are missing: its local settings
# (.kicad_prl) on a check or an export, and a project (.kicad_pro) when the board has none.
_PROJECT_FILES = (".kicad_prl", ".kicad_pro")


@contextmanager
def project_as_found(board: Path) -> Iterator[None]:
    """A read of ``board`` by kicad-cli (a check, an export) leaves its folder as it found it: a project file
    kicad-cli makes beside it that was not there before is removed afterwards. One that was there is never
    touched."""
    made = [board.with_suffix(suffix) for suffix in _PROJECT_FILES if not board.with_suffix(suffix).exists()]
    try:
        yield
    finally:
        for path in made:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def kicad_version(cli: Path) -> str | None:
    """What ``kicad-cli version`` says it is (``9.0.1``), run headless; None when it does not run."""
    return programs.version(KICAD, cli)


def check_api_server(cli: Path) -> Path:
    """``cli`` when it has the headless ``api-server`` a board script runs: ``kicad-cli api-server --help``,
    run headless, lists its ``--socket``. Else ``KicadMissingError``, before any server is started: a stable
    KiCad's kicad-cli has no such command."""
    with private_run("cad-kicad-probe-") as (_folder, env):
        try:
            done = subprocess.run([str(cli), "api-server", "--help"], env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=60, check=False)
            said = f"{done.stdout}\n{done.stderr}"
        except (OSError, subprocess.SubprocessError):
            said = ""
    if "--socket" not in said:
        raise KicadMissingError(f"{cli} has no api-server: {API_SERVER_HINT}")
    return cli


def check_version(cli: Path, version: str | None) -> str:
    try:
        return programs.check_version(KICAD, cli, version)
    except programs.ProgramMissing as error:
        raise _missing(error) from None
