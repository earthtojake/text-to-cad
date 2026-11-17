"""cad installed globally, as the uv tool ``cad``, by a cad that runs from uv's cache: ``cad mcp`` started by an app's
server line (``uvx ... cad@<release> mcp``) on a computer with no global cad (``cad_mcp.shim.start_server``). uvx only
runs a release from uv's cache: it installs no ``cad`` command for the agent's shell, and a server started from there
never updates itself. So that cad installs the global one, and its server is the one that runs.

**From uv's cache** (``from_uv_cache``): this process's environment (``sys.prefix``) lies in the folder uv names as its
cache, ``uv cache dir``, asked both with ``--no-config`` (as a server line runs uvx) and without it (as a person may): a
``cache-dir`` in uv's settings is the one thing that tells the two apart. Asked of uv, never read from the shape of the
folder, which is uv's own and changes with it. A project's Python, a development checkout and a global install are not
in it, and nothing is installed from them.

**The install** (``install``): ``uv tool install --managed-python --python 3.14 cad`` (``command``), the newest
release, with the Python flags of cad's own uv calls (``launch.PYTHON``: they change with any release). Never
``--force``: where uv refuses -- a ``cad`` executable uv did not install is in the way, there is no network -- nothing
is forced, and ``Failed`` carries uv's last line. Bounded: a uv that hangs is stopped (``timeout``). Several at once
make one install: uv locks its tool folder, the others wait, then find cad installed and say so (exit status 0).

BRIDGE-ONLY, the one exception: the ``cad`` command 0.10.0 to 0.11.10 wrote in uv's bin folder (``old_launcher``),
which uv would refuse to replace. Where uv's bin folder holds it (``uv tool dir --bin``; on Windows its ``cad.exe``),
it is renamed beside itself first, under the name cad's own update gives a ``cad.exe`` it sets aside
(``auto_update_helper.ASIDE``). It is deleted once uv ends 0 (one that still runs on Windows stays, harmless, for cad's
next update or the install command to delete), and put back where uv did not, unless uv left a ``cad`` there. Nothing
else is moved: another program's ``cad`` still makes uv refuse. This is how a computer of those releases gets cad
installed globally, by this bridge (``cli.setup``) or by an app's server line.

uv is found as cad's own update finds it (``auto_update.find_uv``), else the one cad's own ``uv`` dependency carries.
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
# BRIDGE-ONLY: the mark in the first lines of the ``cad`` command 0.10.0 to 0.11.10 wrote, with its revision: ``# `` in
# the sh script and in the ``__main__.py`` of the zip behind 0.11's cad.exe (Windows), ``rem `` in 0.10's cad.cmd.
OLD_LAUNCHER = re.compile(r"(#|rem) cad proxy: \d+")


class Failed(Exception):
    """The install did not happen: uv not found, refused, failed, or past its time. Its one line says why."""


def find() -> str | None:
    """uv, as cad's own update finds it, else the one cad's ``uv`` dependency carries; None where neither is."""
    from cad_server._internal.auto_update import find_uv

    found = find_uv()
    if found is not None:
        return found
    try:
        from cad_server._internal.base import find_uv as carried

        return carried()
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


def command(uv: str) -> list[str]:
    """``uv tool install`` of the newest ``cad``, with the Python flags of cad's own uv calls."""
    from cad_server._internal.launch import COMMAND, PYTHON

    return [uv, "tool", "install", "--managed-python", "--python", PYTHON, COMMAND]


def old_launcher(path: Path) -> bool:
    """BRIDGE-ONLY. Whether ``path`` is the ``cad`` command 0.10.0 to 0.11.10 wrote: ``OLD_LAUNCHER`` in its first
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
    ``Failed`` in one line where it was not. The old ``cad`` command set aside first (see the module)."""
    uv = uv or find()
    if uv is None:
        raise Failed("uv is not found")
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
