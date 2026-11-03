"""Find ``kicad-cli``, KiCad's command line, and ask it its version. Viewing boards requires no KiCad.

The ``kicad`` integration's probe (``cad.registry.INTEGRATIONS["kicad"]``), run by the library's one
helper for the external programs our code runs (``cad._internal.programs``), the standard library
alone, so the library's ``@kicad_pcb``, ``cad.kicad_pcb.drc`` and ``export`` and the server's commands
find and run it the same way. The ``kicad-cli`` run is the integration's own: kicode's
(``kicode.executable()``, the ``cad[kicad]`` extra's), or the file ``CAD_KICAD_CLI`` names, refused unless
it is a ``kicad-cli`` (``kicad-cli.exe`` on Windows). A person's own KiCad is never run -- not on PATH,
not in ``/Applications`` or Program Files: it registers a Dock app and reads their settings -- and never
``kicad``, a wrapper (``kicad-cli-nightly``) or a desktop launcher. Every run of it is headless and reads,
writes or locks nothing of the person's: it gets homes of its own (``headless_env``), kicode's
(``kicode.environment``) for kicode's kicad-cli.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cad.registry import INTEGRATIONS

from cad._internal import programs
from cad._internal.programs import version_tuple  # noqa: F401 - the tests' and callers' comparison

__all__ = ["API_SERVER_HINT", "CLI_NAMES", "KICAD", "KICAD_MINIMUM", "KicadMissingError", "KicadRunError",
           "carried", "check_api_server", "check_version", "find_kicad_cli", "headless_env", "install_hint",
           "kicad_version", "packaged", "private_run", "project_as_found", "quiet", "ready"]

# What kicad-cli says on stderr that says nothing about the board.
_NOISE = ("Fontconfig error",)


class KicadRunError(RuntimeError):
    """``kicad-cli`` failed; the message carries what it said."""


# macOS's file-attribute lookup of an output that is not there yet, logged by kicad-cli's process.
_LOGGED = ("Error retrieving source file attributes",)


def quiet(text: str) -> str:
    """What kicad-cli said, without its noise."""
    return "\n".join(line for line in (text or "").splitlines()
                     if line.strip() and not line.startswith(_NOISE) and not any(said in line for said in _LOGGED))

_PROBE = INTEGRATIONS["kicad"].probe
assert _PROBE is not None
# The one program the server runs of KiCad's, by its file name on each platform.
CLI_NAMES = ("kicad-cli", "kicad-cli.exe")
# KiCad's own homes for a kicad-cli ``CAD_KICAD_CLI`` names, beside the ones every program run gets
# (``programs.headless_env``); kicode's own kicad-cli gets kicode's (``kicode.environment``), which sets the
# same three and, on Linux, where the packaged build finds its stock data and plugins.
_HOMES = {"KICAD_CONFIG_HOME": "settings", "KICAD_DOCUMENTS_HOME": "documents", "KICAD_CACHE_HOME": "cache"}


class KicadMissingError(programs.ProgramMissing):
    """No usable KiCad command line."""


def install_hint() -> str:
    return _PROBE.install_hint


def _kicode() -> Any:
    """kicode (the ``cad[kicad]`` extra), or None where this environment lacks it."""
    try:
        import kicode  # pyrefly: ignore[missing-import] - the kicad extra
    except ImportError:
        return None
    return kicode


def packaged() -> Path | None:
    """kicode's kicad-cli, where this environment holds kicode; else None."""
    kicode = _kicode()
    if kicode is None:
        return None
    try:
        return Path(kicode.executable())
    except (AttributeError, OSError):  # a wheel not for this platform says FileNotFoundError
        return None


def carried() -> bool:
    """Whether this process runs KiCad itself: ``CAD_KICAD_CLI`` names one, or it holds kicode."""
    return bool(os.environ.get(_PROBE.override, "").strip()) or packaged() is not None


def _is_packaged(cli: Path) -> bool:
    found = packaged()
    try:
        return found is not None and Path(cli).resolve() == found.resolve()
    except OSError:
        return False


#: ``kicad-cli`` as the helper runs it: the override, then kicode's, never PATH or an installation's.
KICAD = programs.Program.from_probe(_PROBE, names=CLI_NAMES, installed=lambda: [p for p in (packaged(),) if p],
                                     homes=_HOMES, title="KiCad 9", search_path=False)
#: What a board script needs beyond a check's or an export's kicad-cli: its headless api-server.
API_SERVER_HINT = ("a @kicad_pcb board script runs kicad-cli's headless api-server, which kicode's kicad-cli (cad[kicad]) "
                   "and a KiCad nightly's (10.99) have; a check or an export needs only KiCad 9 or newer. Unset "
                   "CAD_KICAD_CLI to run kicode's, or set it to a nightly's kicad-cli")
KICAD_MINIMUM = KICAD.minimum


def _missing(error: programs.ProgramMissing) -> KicadMissingError:
    return KicadMissingError(str(error))


def find_kicad_cli() -> Path:
    """The ``kicad-cli`` to run: ``CAD_KICAD_CLI`` when it is set (a ``kicad-cli`` that is a file, else
    refused), else kicode's (``kicode.executable()``), else ``KicadMissingError`` saying to install
    ``cad[kicad]``. Never one on PATH or in KiCad's installation folders."""
    try:
        return programs.find(KICAD)
    except KicadMissingError:
        raise
    except programs.ProgramMissing as error:
        raise _missing(error) from None


def headless_env(root: str | os.PathLike, cli: Path | None = None) -> dict[str, str]:
    """The environment a ``kicad-cli`` run gets (``programs.headless_env``: no display, every home inside
    ``root``), with KiCad's own homes inside ``root`` too: kicode's variables (``kicode.environment``) for
    kicode's kicad-cli -- ``cli``, or none named where this environment holds kicode -- else
    ``KICAD_CONFIG_HOME`` (``root/settings``), ``KICAD_DOCUMENTS_HOME`` and ``KICAD_CACHE_HOME``."""
    kicode = _kicode()
    if kicode is not None and (cli is None or _is_packaged(cli)):
        env = programs.headless_env(root)
        env.update(kicode.environment(root))
        return env
    return programs.headless_env(root, _HOMES)


@contextmanager
def private_run(prefix: str = "cad-kicad-", cli: Path | None = None) -> Iterator[tuple[Path, dict[str, str]]]:
    """A private folder and the headless environment inside it (``headless_env``), for one ``kicad-cli``
    run; the folder (with whatever KiCad left in it) is removed afterwards. Yields ``(folder, env)``."""
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as scratch:
        yield Path(scratch), headless_env(scratch, cli)


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
    """What ``cli`` is (``10.99.0``): kicode's version for kicode's kicad-cli, else what ``kicad-cli
    version`` says, run headless; None when it does not run."""
    kicode = _kicode()
    if kicode is not None and _is_packaged(cli):
        return str(kicode.KICAD_VERSION)
    with private_run("cad-kicad-version-", cli) as (_folder, env):
        try:
            done = subprocess.run([str(cli), "version"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
    if done.returncode != 0:
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", f"{done.stdout}\n{done.stderr}")
    return match.group(1) if match else None


def check_api_server(cli: Path) -> Path:
    """``cli`` when it has the headless ``api-server`` a board script runs: kicode's always has; another's
    (``CAD_KICAD_CLI``) is asked, ``kicad-cli api-server --help`` run headless listing its ``--socket``.
    Else ``KicadMissingError``, before any server is started: a stable KiCad's kicad-cli has no such command."""
    if _is_packaged(cli):
        return cli
    with private_run("cad-kicad-probe-", cli) as (_folder, env):
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


def ready() -> Path:
    """The ``kicad-cli`` to run, found and its version checked: ``find_kicad_cli`` then ``check_version``."""
    cli = find_kicad_cli()
    check_version(cli, kicad_version(cli))
    return cli
