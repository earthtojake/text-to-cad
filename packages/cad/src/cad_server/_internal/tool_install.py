"""cad installed globally, as the uv tool ``cad``, by a cad that runs from uv's cache: ``cad mcp`` started by an app's
server line (``uvx ... cad@<release> mcp``) on a computer with no global cad (``cad_mcp.shim.start_server``). uvx only
runs a release from uv's cache: it installs no ``cad`` command for the agent's shell, and a server started from there
never updates itself. So that cad installs the global one, and its server is the one that runs.

**From uv's cache** (``from_uv_cache``): this process's environment (``sys.prefix``) lies in the folder uv names as its
cache, ``uv cache dir``, asked both with ``--no-config`` (as a server line runs uvx) and without it (as a person may): a
``cache-dir`` in uv's settings is the one thing that tells the two apart. Asked of uv, never read from the shape of the
folder, which is uv's own and changes with it. A project's Python, a development checkout and a global install are not
in it, and nothing is installed from them.

**The install** (``install``): ``uv tool install --managed-python --python 3.14 "cad<N>"`` (``command``), the newest
release of the major of the cad doing the installing (``N`` its major + 1, worked out from its release: a plugin copy
pinned to this release may run long after a higher major is out, and a new major version is a person's to ask for, as
cad's own update keeps it, ``auto_update``); uv keeps the range, so the cad installed stays in that major by itself
too. With the Python flags of cad's own uv calls (``launch.PYTHON``: they change with any release). Never
``--force``: where uv refuses -- a ``cad`` executable uv did not install is in the way, there is no network -- nothing
is forced, and ``Failed`` carries uv's last line. Bounded: a uv that hangs is stopped (``timeout``). Several at once
make one install: uv locks its tool folder, the others wait, then find cad installed and say so (exit status 0).

**Never down** (``_refuse_higher``): ``cad<N`` moves a tool of a higher major down to this major, with exit status 0,
so the install never runs where uv's tool ``cad`` already holds a release of a higher major -- read from the
``cad-<release>.dist-info`` folder in its environment (``auto_update_helper.installed``), so it is seen where its
launcher is missing and ``auto_update.installed_tool`` finds none -- nor where uv cannot say where its tools are
(``uv tool dir``): ``Failed``, and nothing moved or run. A tool folder with no release to read (half made) is no reason
to refuse: uv repairs it.

BRIDGE-ONLY, the one exception: the ``cad`` command 0.10.0 to 0.11.11 wrote in uv's bin folder (``old_launcher``),
which uv would refuse to replace. Where uv's bin folder holds it (``uv tool dir --bin``; on Windows its ``cad.exe``),
it is renamed beside itself first, under the name cad's own update gives a ``cad.exe`` it sets aside
(``auto_update_helper.ASIDE``). It is deleted once uv ends 0 (one that still runs on Windows stays, harmless, for cad's
next update or the install command to delete), and put back where uv did not, unless uv left a ``cad`` there. Nothing
else is moved: another program's ``cad`` still makes uv refuse. This is how a computer of those releases gets cad
installed globally, by this bridge (``cli.setup``) or by an app's server line.

uv is found as cad's own update finds it (``auto_update.find_uv``: on Windows never a batch file, which would read the
``<`` of ``cad<N`` as a redirection), else the one cad's own ``uv`` dependency carries (``auto_update.carried_uv``).
Imports the standard library alone at module scope.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

__all__ = ["ASK_SECONDS", "Failed", "command", "find", "from_uv_cache", "install", "old_launcher"]

# How long one ``uv`` question (``uv cache dir``) may take.
ASK_SECONDS = 15.0
# BRIDGE-ONLY: the mark in the first lines of the ``cad`` command 0.10.0 to 0.11.11 wrote, with its revision: ``# `` in
# the sh script and in the ``__main__.py`` of the zip behind 0.11's cad.exe (Windows), ``rem `` in 0.10's cad.cmd.
OLD_LAUNCHER = re.compile(r"(#|rem) cad proxy: \d+")


class Failed(Exception):
    """The install did not happen: uv not found, refused, failed, or past its time. Its one line says why."""


def find() -> str | None:
    """uv, as cad's own update finds it (never a batch file on Windows: ``auto_update.find_uv``), else the one cad's
    ``uv`` dependency carries (``auto_update.carried_uv``); None where neither is."""
    from cad_server._internal.auto_update import carried_uv, find_uv

    try:
        return find_uv() or carried_uv()
    except Exception:  # noqa: BLE001 - no uv at all
        return None


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """``command`` run with no input and no window, its output kept, in an environment that points at nothing of this
    one's Python (``auto_update._UNSET``)."""
    from cad_server._internal.auto_update import _UNSET

    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          env={name: value for name, value in os.environ.items() if name not in _UNSET},
                          creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW


def _inside(path: str, folder: str) -> bool:
    folder = os.path.normcase(os.path.realpath(folder)).rstrip(os.sep) + os.sep
    return os.path.normcase(os.path.realpath(path)).rstrip(os.sep).startswith(folder)


def from_uv_cache(prefix: str | None = None, uv: str | None = None) -> bool:
    """Whether the environment at ``prefix`` (``sys.prefix``) lies in uv's cache (see the module). False where uv is
    not found or does not answer. Never raises."""
    try:
        uv = uv or find()
        if uv is None:
            return False
        for asked in ([uv, "cache", "dir", "--no-config"], [uv, "cache", "dir"]):
            done = _run(asked, ASK_SECONDS)
            lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
            if done.returncode == 0 and lines and _inside(prefix or sys.prefix, lines[-1]):
                return True
    except Exception:  # noqa: BLE001 - a uv that cannot be asked: not known to be its cache
        return False
    return False


def _major(version: str | None = None) -> int | None:
    """The major of release ``version`` (this cad's by default), or None where it has none to read."""
    from cad_server import __version__

    found = re.match(r"(\d+)\.\d+\.\d+", __version__ if version is None else version)
    return int(found[1]) if found else None


def command(uv: str, version: str | None = None) -> list[str]:
    """``uv tool install`` of the newest ``cad`` of the major of release ``version`` (this cad's by default:
    ``cad<N>``, ``N`` its major + 1), with the Python flags of cad's own uv calls. A version with no major to read
    (none here) installs the newest of all."""
    from cad_server._internal.launch import COMMAND, PYTHON

    major = _major(version)
    wanted = f"{COMMAND}<{major + 1}" if major is not None else COMMAND
    return [uv, "tool", "install", "--managed-python", "--python", PYTHON, wanted]


def _tools(uv: str) -> Path | None:
    """uv's tool folder, as uv names it (``uv tool dir``, which reads ``UV_TOOL_DIR`` as every uv command does), or
    None where uv cannot say."""
    try:
        done = _run([uv, "tool", "dir"], ASK_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return Path(lines[-1]) if done.returncode == 0 and lines else None


def _held(uv: str) -> tuple[int, ...] | None:
    """The release uv's tool ``cad`` holds, read from the ``cad-<release>.dist-info`` folder in its environment's
    site-packages (``auto_update_helper.installed``: found with no launcher, a receipt or a ``cad`` that runs), or None
    where it holds none (no tool, or one half made). ``Failed`` where uv cannot say where its tools are."""
    from cad_server._internal.auto_update_helper import installed

    folder = _tools(uv)
    if folder is None:
        raise Failed("uv could not say where its tools are, so cad was left as it is")
    return installed(folder / "cad")


def _refuse_higher(uv: str) -> None:
    """``Failed`` where uv's tool ``cad`` holds a release of a higher major than this cad installs, or uv cannot say
    where its tools are (``_held``): the bounded install would take it down."""
    found, mine = _held(uv), _major()
    if found is not None and mine is not None and found[0] > mine:
        raise Failed(f"uv's cad tool holds cad {'.'.join(map(str, found))}, of a newer major version than this cad "
                     "installs, so cad was left as it is")


def old_launcher(path: Path) -> bool:
    """BRIDGE-ONLY. Whether ``path`` is the ``cad`` command 0.10.0 to 0.11.11 wrote: ``OLD_LAUNCHER`` in its first
    lines (0.11's cad.exe: in the ``__main__.py`` of the zip behind its launcher). A link is never one."""
    import zipfile

    if path.is_symlink() or not path.is_file():
        return False
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                head = archive.read("__main__.py")[:512]
        else:
            with open(path, "rb") as handle:
                head = handle.read(4096)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return False
    return any(OLD_LAUNCHER.match(line.strip()) for line in head.decode("utf-8", "replace").splitlines()[:3])


def _bin(uv: str) -> Path | None:
    """uv's bin folder, as uv names it (``uv tool dir --bin``), or None."""
    try:
        done = _run([uv, "tool", "dir", "--bin"], ASK_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return Path(lines[-1]) if done.returncode == 0 and lines else None


def _set_aside(uv: str) -> tuple[Path, Path] | None:
    """BRIDGE-ONLY. The old ``cad`` command in uv's bin folder renamed beside itself (see the module): where it was
    and where it is now. None where there is none, or it could not be renamed."""
    folder = _bin(uv)
    if folder is None:
        return None
    path = folder / ("cad.exe" if os.name == "nt" else "cad")
    if not old_launcher(path):
        return None
    from cad_server._internal.auto_update_helper import ASIDE

    aside = path.with_name(ASIDE.format(stamp=f"{os.getpid()}-{time.time_ns()}", n=0))
    try:
        os.replace(path, aside)
    except OSError:
        return None
    return path, aside


def _settle(moved: tuple[Path, Path] | None, ok: bool) -> None:
    """BRIDGE-ONLY. What ``_set_aside`` renamed: deleted where uv ended 0 and put a ``cad`` in its place; put back
    where nothing is in its place; else left. Quiet: a file that still runs stays."""
    if moved is None:
        return
    path, aside = moved
    try:
        if not os.path.lexists(path):
            os.replace(aside, path)
        elif ok:
            aside.unlink()
    except OSError:
        pass


def install(uv: str | None = None, *, timeout: float) -> list[str]:
    """cad installed as the uv tool ``cad`` (``command``), ``timeout`` seconds at most: what uv said, line by line.
    ``Failed`` in one line where it was not: where uv's tool ``cad`` holds a higher major, or uv cannot say where its
    tools are, before anything is moved or run (``_refuse_higher``). The old ``cad`` command set aside first (see the
    module)."""
    uv = uv or find()
    if uv is None:
        raise Failed("uv is not found")
    _refuse_higher(uv)
    moved, ok = _set_aside(uv), False
    try:
        done = _run(command(uv), timeout)
        ok = done.returncode == 0
    except subprocess.TimeoutExpired:
        raise Failed(f"uv did not finish within {timeout:g} s, and was stopped") from None
    except OSError as error:
        raise Failed(f"uv could not run: {error}") from None
    finally:
        _settle(moved, ok)
    said = [line.strip() for line in (done.stderr + "\n" + done.stdout).splitlines() if line.strip()]
    if done.returncode != 0:
        errors = [line for line in said if line.lower().startswith("error")]
        raise Failed((errors or said or [f"uv exited with status {done.returncode}"])[-1])
    return said
