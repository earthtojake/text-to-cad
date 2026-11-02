"""Find a user-installed ``kicad-cli``, KiCad's command line, and ask it its version. Viewing boards
requires no KiCad installation.

The server never starts KiCad itself: what this finds is always an executable named exactly
``kicad-cli`` (``kicad-cli.exe`` on Windows) -- ``CAD_KICAD_CLI``, refused unless it names one, then
``kicad-cli`` on PATH, then the command line inside the usual macOS or Windows installation -- never
``kicad``, a wrapper (``kicad-cli-nightly``) or a desktop launcher. Every run of it is headless and
reads, writes or locks nothing of the person's: it gets homes of its own (``headless_env``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = ["CLI_NAMES", "KICAD_MINIMUM", "KicadMissingError", "check_version", "find_kicad_cli", "headless_env",
           "install_hint", "kicad_version", "private_run"]

KICAD_MINIMUM = (9, 0)
# The one program the server runs of KiCad's, by its file name on each platform.
CLI_NAMES = ("kicad-cli", "kicad-cli.exe")
# What a child would need to reach a desktop: never handed to kicad-cli.
_DISPLAY = ("DISPLAY", "WAYLAND_DISPLAY")


class KicadMissingError(RuntimeError):
    """No usable KiCad command line."""


def install_hint() -> str:
    return ("install KiCad 9 or newer from https://www.kicad.org/download/, or set CAD_KICAD_CLI to its "
            "kicad-cli")


def _is_cli(path: Path) -> bool:
    return path.name.lower() in CLI_NAMES if sys.platform.startswith("win") else path.name in CLI_NAMES


def find_kicad_cli() -> Path:
    """The ``kicad-cli`` to run: ``CAD_KICAD_CLI`` when it is set (a ``kicad-cli`` that is a file,
    else refused), else ``kicad-cli`` on PATH, else the one inside the platform's usual installation."""
    explicit = os.environ.get("CAD_KICAD_CLI", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not _is_cli(path):
            raise KicadMissingError(f"CAD_KICAD_CLI names {path}, which is not kicad-cli: name KiCad's "
                                    f"command line itself, never kicad or a launcher; {install_hint()}")
        if path.is_file():
            return path
        raise KicadMissingError(f"CAD_KICAD_CLI names {path}, which is not a file: {install_hint()}")
    found = shutil.which("kicad-cli")
    if found and _is_cli(Path(found)):
        return Path(found)
    for candidate in _installed():
        if _is_cli(candidate) and candidate.is_file():
            return candidate
    raise KicadMissingError(f"KiCad's kicad-cli was not found: {install_hint()}")


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


def _windows() -> bool:
    return sys.platform.startswith("win")


def headless_env(root: str | os.PathLike) -> dict[str, str]:
    """The environment every ``kicad-cli`` run gets: this process's, with no display to reach
    (``DISPLAY``, ``WAYLAND_DISPLAY`` removed) and every home KiCad reads or writes inside ``root``,
    a private folder the caller removes afterwards, so a run neither opens a window nor touches the
    person's KiCad settings, data, cache, documents or instance lock. The folders are made here.

    - ``KICAD_CONFIG_HOME`` (``root/settings``), ``KICAD_DOCUMENTS_HOME`` and ``KICAD_CACHE_HOME``:
      KiCad's own overrides, on every OS. Without the last two KiCad 10 still writes
      ``~/.local/share/kicad/<ver>`` and ``~/.cache/kicad/<ver>``.
    - ``HOME``: never empty (kicad-cli exits 255 then), and where macOS keeps its ``~/Library``
      folders, so it covers them. ``TMPDIR`` holds KiCad's instance lock (``$TMPDIR/org.kicad.kicad``).
    - Linux and other POSIX: ``XDG_CONFIG_HOME``, ``XDG_DATA_HOME``, ``XDG_CACHE_HOME`` and
      ``XDG_STATE_HOME``, which wxWidgets reads before ``HOME``.
    - Windows: ``USERPROFILE``, ``APPDATA``, ``LOCALAPPDATA`` and ``TEMP`` / ``TMP``.

    ``KICAD_STOCK_DATA_HOME`` is left alone: a user's KiCad finds its stock libraries and schemas by
    it, and only a packaged kicad-cli would need it set."""
    root = Path(root)
    home = root / "home"
    tmp = root / "tmp"
    folders = [home, tmp, root / "settings", root / "documents", root / "cache"]
    env = {key: value for key, value in os.environ.items() if key not in _DISPLAY}
    env.update(HOME=os.fspath(home), TMPDIR=os.fspath(tmp), KICAD_CONFIG_HOME=os.fspath(root / "settings"),
               KICAD_DOCUMENTS_HOME=os.fspath(root / "documents"), KICAD_CACHE_HOME=os.fspath(root / "cache"))
    if _windows():
        roaming, local = home / "AppData" / "Roaming", home / "AppData" / "Local"
        folders += [roaming, local]
        env.update(USERPROFILE=os.fspath(home), APPDATA=os.fspath(roaming), LOCALAPPDATA=os.fspath(local),
                   TEMP=os.fspath(tmp), TMP=os.fspath(tmp))
    elif sys.platform != "darwin":
        xdg = {"XDG_CONFIG_HOME": home / ".config", "XDG_DATA_HOME": home / ".local" / "share",
               "XDG_CACHE_HOME": home / ".cache", "XDG_STATE_HOME": home / ".local" / "state"}
        folders += list(xdg.values())
        env.update({name: os.fspath(path) for name, path in xdg.items()})
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    return env


@contextmanager
def private_run(prefix: str = "cad-kicad-") -> Iterator[tuple[Path, dict[str, str]]]:
    """A private folder and the headless environment inside it, for one ``kicad-cli`` run; the folder
    (with whatever KiCad left in it) is removed afterwards. Yields ``(folder, env)``."""
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as scratch:
        yield Path(scratch), headless_env(scratch)


def version_tuple(version: str) -> tuple[int, ...]:
    """The first three numbers of ``version``, to compare with a minimum: ``(9, 0, 1)``."""
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def kicad_version(cli: Path) -> str | None:
    """What ``kicad-cli version`` says it is (``9.0.1``), run headless; None when it does not run."""
    with private_run() as (_scratch, env):
        try:
            done = subprocess.run([str(cli), "version"], env=env, capture_output=True, text=True, timeout=60,
                                  check=False)
        except (OSError, subprocess.SubprocessError):
            return None
    if done.returncode != 0:
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", f"{done.stdout}\n{done.stderr}")
    return match.group(1) if match else None


def check_version(cli: Path, version: str | None) -> str:
    if version is not None and version_tuple(version)[:2] >= KICAD_MINIMUM:
        return version
    raise KicadMissingError(f"{cli} reports {version or 'no version'}; cad needs KiCad 9 or newer: {install_hint()}")
