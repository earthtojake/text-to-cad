"""cad's own update: what a global install is, the switches, the check, and its trigger.

**The rule.** cad installs by itself any newer release with the same major version number as its own; a release of a
higher major never arrives by itself: a person asks for it (``cad update --major``). Every update is forward only. The
bound lives in the command each update runs, worked out from the release that runs each time (``bound``: ``cad>=<this
release>,<<its major + 1>``), never a fixed number, so it holds on a computer that has not updated for months.

**A global install** (``global_install``) is a cad whose environment one of the installers in ``INSTALLERS`` made: uv's
``uv tool install cad`` (uv's receipt in the environment names ``cad``), or pipx's ``pipx install cad`` (pipx's
metadata in the environment names ``cad``, and the environment is pipx's ``venvs/cad``). Only a global install updates
itself, and each installer says how: the command that upgrades cad to the newest release of its major (uv: ``uv tool
install --upgrade "cad>=X,<N"``, measured: it moves up, never past the bound and, with the floor, never down, is safe
to repeat, and uv keeps the range in its receipt, so a person's own ``uv tool upgrade cad`` stays inside the major too;
no Python flags, so the environment keeps its interpreter. pipx: ``pipx upgrade cad --pip-args=cad>=X,<N``, measured on
pipx 1.0, 1.4, 1.8 and 1.18: pip takes both requirements and the upgrade stays inside the bound, and pipx's own
handling of a pinned version a release put back is kept; pipx 1.18 keeps the ``--pip-args`` for a person's own ``pipx
upgrade cad``, which then stays inside the major too, where earlier pipx keeps none and takes the newest of all), the
command that crosses to the newest release of all, for ``cad update --major``, never below the release that runs: the
floor alone (uv: ``uv tool install --upgrade "cad>=X"``, measured on uv 0.11.25: it crosses to a higher major, keeps
``>=X`` in place of the range, which the next bounded upgrade writes again, ends 0 with nothing changed where nothing
newer is out, and where X is yanked and only older releases are not, keeps X; pipx: ``pipx upgrade cad
--pip-args=cad>=X``, which replaces the range pipx 1.18 kept: a plain ``pipx upgrade cad`` there would stay inside
it; a known gap: cad's ``--pip-args`` take the place of a person's own, an index of their ``pipx install cad
--pip-args=...`` among them), the command that puts a given release back (``cad==<release>``; pipx: ``pipx install --force cad==<release>``), the command that prints the folder
its launchers are in, the variables its commands need to act on this environment (pipx: ``PIPX_HOME``, the folder that
holds ``venvs/cad``, where the server's environment may not name it), and the environment's own ``cad`` command.
Another installer is one more entry of ``INSTALLERS``; nothing that asks changes. Where both made one on a computer,
uv's is the one ``installed_tool`` finds.

**The switches** are the person's, in cad's settings (``settings.json`` in the state folder): ``auto_update.on``,
whether cad updates itself, ON where nothing is kept -- but OFF where 0.10.0 to 0.11.11 kept the person's own off
(``updates.automatic: false``, the same file: every release reads the one state folder) and ``auto_update.on`` was
never chosen, so a choice made before the update to this cad stands; ``cad update auto on`` then writes ``true``, which
wins, and the earlier key is only read --; and ``plugin.auto_update``, whether the server runs the install
command (``cad plugin update``) once where cad is newer than the release that command is up to date for
(``plugin_catch_up``), OFF where nothing is kept. ``cad update auto`` and ``cad plugin update auto`` change them.

**The check** (``due``): switch on, the check not turned off for this process (``updates.checking``:
``CAD_UPDATE_CHECK=0``, CI), this cad a global install whose installer is found, no attempt underway, of whatever
release (``underway``: begun less than ``RETRY_SECONDS`` ago and not ended), and an update the version feed calls for
(``choose``): the newest release of this cad's major its ``lines`` names, where it is newer than this cad; where the
feed names none of this major, its ``latest`` where that is of this major and newer, or, where ``latest`` is of a
higher major, the bounded upgrade all the same with no release named (whatever it gets of this major), so a feed
without ``lines`` never strands a computer. No answer from the feed, no update; never a higher major, never an older
release. The release it is for (``wanted``: the release named, or the feed's ``latest`` where none is) not tried
``TRIES`` times already, nor in the last ``RETRY_SECONDS``: one that fails, or finds nothing newer, is tried once more
at a check an hour later, never in a loop. It is asked first thing as the server starts (``at_start``, from the feed
as last read), as the server tends itself (``tend``, the feed read again in the background once an hour), and by ``cad
server start`` when the start failed (``after_failed_start``, the feed read when due): a release whose server cannot
start still updates. These three are the automatic updates.

**The trigger** (``trigger``), once nothing is in flight -- at a start, at once; otherwise once nothing has run for
``IDLE_SECONDS``, or nothing has run since the server started: the update begun in one step across processes
(``_claim``, under the state folder's lock, ``file_lock.state``): where an attempt is underway, of whatever release,
none begins (an automatic update) or it is joined (``cad update``); for an automatic update, ``wanted`` asked again
(``_tried``); then the attempt before counted where it was not, and this one kept as underway, before the lock is let
go. So two servers that start at once, each asking ``at_start`` before either holds the daemon's lock, begin one update
between them. Within a process ``_BEGIN`` keeps the check and the trigger together. Then a detached helper, never the
``cad`` executable and never run from cad's environment (``auto_update_helper``, run by the Python that environment
was made from), stops the server, runs the installer's upgrade command, and starts the server with whatever cad is
there. On Windows it renames each ``cad.exe`` of the tool aside before the installer runs and puts a copy back,
because an installer cannot remove one that is running (a ``cad update`` that waits, a ``cad server start``); that works
because cad takes its launcher off ``sys.path`` as it starts (``cad_server/__init__.py``). The helper runs no install
command: the server of the newer cad does, by ``plugin_catch_up``'s rule, whatever brought cad there. The attempt is
kept in the state folder (``RECORD``: ``release``, ``wanted``, ``from``, ``at``, ``tries``, ``installer``, ``asked`` -- a
typed update --, ``major`` -- ``cad update --major`` --, then the helper's ``ended``, ``outcome``, ``detail``,
``restored``, ``started``), which ``cad doctor`` shows.

Left as they are, on purpose: a ``cad server start`` that arrives while the helper upgrades starts whatever cad is
there at that moment (the helper's own start at the end then meets it as any start meets a running server: a newer one
is joined, an older one replaced); and uv run beside the helper by the install command or by an app's server line
(``tool_install``), which uv's own lock on its tool folder puts one after the other, the last to run deciding what is
installed. A known gap: the helper's tries (``auto_update_helper.WAITS``, each up to ``INSTALL_SECONDS``) can last
longer than ``RETRY_SECONDS``, after which the attempt is no longer ``underway`` and a second can begin beside it.

**Counted** (``report``), once per attempt that ended, by the server that runs after it, at its start and as it tends
itself, once nothing is in flight (and by a trigger, before a new attempt takes the record's place): one ``update``
event (``analytics.update``) -- the release before, how it ended (``installed``, ``current``, ``failed``, or
``restored`` where the helper put the release before back), which step failed (``upgrade``: the installer's upgrade
never ended well, or, for ``--major``, ended well without crossing to the higher major asked for; ``older``: it ended
well on a release it may not end on, older than the one that ran or, but for ``--major``, of another major -- a
``--major`` that crossed is ``installed``, whatever release of the higher major it got; ``put_back``: the release
before could
not be put back either), the tries, the installer, whether it was typed, and, for a newer cad installed, how the
install command's run for it ended, a run begun since the attempt began (``plugin_catch_up.last``: ``none``, ``ok``,
``failed``; the event waits while that run is underway, but where a new attempt begins first, it is counted as it
stands, ``underway``). The record is marked ``reported`` as it is counted. A failed update leaves the old cad, and is
counted by the next server of it that runs; one that installed a newer cad, by the new cad's server; either, where a new
attempt begins before such a server ran, by whatever begins that attempt (a server, or a typed ``cad update`` with no
server running, in its own process). The helper counts nothing.

**Asked for** (``cad update``, which the server it asks judges, ``asked``, and begins, ``begin``; with no server
running, the command itself, whose helper then starts none): PyPI asked now (``updates.pypi``) for the newest release of
this cad's major that is not yanked, chosen as the feed's answer is (``choose``), and updated to by the same bounded
upgrade; where a release of a higher major is out, the answer names it (``higher``), which the command says in one
line (``MAJOR_LINE``). ``cad update --major`` (``major``): PyPI's newest release of all, by the installer's crossing
command. The switch, ``TRIES`` and ``RETRY_SECONDS`` do not apply (a typed update always updates); where PyPI cannot be
reached, the upgrade runs all the same, and says what it got; the update begun as soon as nothing is in flight, not
after the idle minute, or joined where one is underway. Counted in the record as any attempt is, so the automatic tries
stay bounded. It never runs the install command itself, and says nothing of it.

Imports the standard library alone; what it asks of cad it imports as it asks: ``cad.engine.places`` (the folders),
``cad_server.updates`` (the feed, PyPI), ``cad._internal.atomic_replace`` (the attempt kept),
``cad_server._internal.file_lock`` (the state folder's lock), ``cad_server.analytics`` (the attempt counted) and, to
change a switch, ``cad_server.settings``.
"""

from __future__ import annotations

import functools
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECTION = "auto_update"
PLUGIN_SECTION = "plugin"
RECORD = "auto-update.json"  # the last attempt, in the state folder
INSTALL_LOG = "install-command.log"  # the output of the last `cad plugin update` the server ran (``plugin_catch_up``)
IDLE_SECONDS = 60.0
TRIES = 2  # how many times one release is tried: once, and once more at a later check
RETRY_SECONDS = 60 * 60.0  # how long after an attempt (underway, or ended) its release may be tried again
# What the record names as the release of a typed update begun with no answer from PyPI: whatever the upgrade gets.
LATEST = "latest"
# The exit status of a server that handed its start to an update (``at_start``): its starter waits for the next one
# (``cad.engine.client.UPDATING``).
UPDATING = 75
HELPER = Path(__file__).with_name("auto_update_helper.py")
# One update begun at a time in a process: the check and the trigger together (``_begin_due``, ``begin``).
_BEGIN = threading.Lock()
# What the helper's environment leaves out: anything that would point its Python, uv or cad at this environment.
_UNSET = ("PYTHONPATH", "PYTHONHOME", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__", "VIRTUAL_ENV")


def release(text: Any) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text) if isinstance(text, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def newer(theirs: Any, mine: Any) -> bool:
    """Whether release ``theirs`` is later than ``mine``; False where either is no plain ``X.Y.Z``."""
    a, b = release(theirs), release(mine)
    return a is not None and b is not None and a > b


def bound(version: str) -> str:
    """The requirement that keeps an upgrade inside release ``version``'s major and never below it: ``cad>=<version>,<
    <its major + 1>``, worked out from the release each time (see the module). ``ValueError`` for no plain ``X.Y.Z``."""
    numbers = release(version)
    if numbers is None:
        raise ValueError(f"not a release: {version!r}")
    return f"cad>={version},<{numbers[0] + 1}"


# The migration guides, which say what a new major version asks of a person.
MIGRATIONS = "https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations"
# The one line that says a release of a higher major is out (``cad update``, ``cad doctor``, ``cad update auto``).
MAJOR_LINE = ("cad {release}, a new major version, is out and does not install itself: `cad update --major` installs it "
              f"(what changes: {MIGRATIONS})")


@dataclass(frozen=True)
class Due:
    """An update to make: ``target``, the release it moves to (None: the newest release of this major the upgrade
    gets), and ``wanted``, the release it is for, by which its tries are counted (``target``, or the feed's ``latest``
    where it names none of this major)."""

    target: str | None
    wanted: str


def choose(known: Any, version: str) -> Due | None:
    """The update an answer in the feed's shape (``known``: ``{"latest", "lines"}``, the feed's or PyPI's) calls for,
    from release ``version`` (see the module's check), or None. Never a higher major, never an older release."""
    from cad_server import updates

    mine = release(version)
    if mine is None or not isinstance(known, dict):
        return None
    named = updates.newest_of_major(mine[0], known)
    if named is not None:
        return Due(named, named) if newer(named, version) else None
    latest = known.get("latest")
    top = release(latest)
    if top is None or top[0] < mine[0]:
        return None
    if top[0] == mine[0]:
        return Due(latest, latest) if newer(latest, version) else None
    return Due(None, latest)  # no release of this major named: the bounded upgrade, counted by ``latest``


def higher(known: Any, version: str) -> str | None:
    """The newest release of a higher major than release ``version``'s that ``known`` (the feed's shape) names, or
    None."""
    mine, latest = release(version), known.get("latest") if isinstance(known, dict) else None
    top = release(latest)
    return latest if mine is not None and top is not None and top[0] > mine[0] else None


def _data() -> Path:
    from cad.engine.places import state_dir

    return state_dir()


def _version() -> str:
    from cad_server import __version__

    return __version__


# --- the switches -----------------------------------------------------------------------------------------------------


def _section(name: str, path: Path | None) -> dict[str, Any]:
    try:
        kept = json.loads((path or _data() / "settings.json").read_text(encoding="utf-8")).get(name)
    except (OSError, ValueError, AttributeError):
        kept = None
    return kept if isinstance(kept, dict) else {}


# Where 0.10.0 to 0.11.11 kept the person's choice of automatic updates: ``{"updates": {"automatic": false}}`` once they
# turned them off. Read, never written or removed.
EARLIER_SECTION, EARLIER_KEY = "updates", "automatic"


def switches(path: Path | None = None) -> dict[str, Any]:
    """``{"on"}``, whether cad updates itself: what ``auto_update.on`` keeps, where it keeps true or false; where it
    keeps neither, off where the choice of 0.10.0 to 0.11.11 (``updates.automatic``) is false -- then ``"earlier":
    true`` too --, else on (absent, or unreadable: on)."""
    kept = _section(SECTION, path).get("on")
    if isinstance(kept, bool):
        return {"on": kept}
    if _section(EARLIER_SECTION, path).get(EARLIER_KEY) is False:
        return {"on": False, "earlier": True}
    return {"on": True}


def change(on: bool) -> dict[str, Any]:
    """The switch changed under the state folder's lock (``settings.update_section``). ``OSError`` where it cannot be
    written."""
    from cad_server.settings import update_section

    update_section(SECTION, lambda kept: {**kept, "on": on})
    return switches()


def plugin_switch(path: Path | None = None) -> bool:
    """Whether the server runs ``cad plugin update`` once where cad is newer than the release it is up to date for
    (``plugin_catch_up``): off unless ``true`` is kept."""
    return _section(PLUGIN_SECTION, path).get("auto_update") is True


def change_plugin(on: bool, release: str | None = None, *, note: bool = True) -> bool:
    """``plugin.auto_update`` changed under the state folder's lock; turned on, the install command is taken as up to
    date for ``release``, the cad that turned it on (this one's by default: ``plugin_catch_up.noted``) -- unless
    ``note`` is false: turned on by the install command's run that is ending badly (``plugin_catch_up.FAILED_ENV``),
    which takes nothing as up to date. ``OSError`` where it cannot be written."""
    from cad_server.settings import update_section

    update_section(PLUGIN_SECTION, lambda kept: {**kept, "auto_update": on})
    if on and note:
        from cad_server._internal import plugin_catch_up

        plugin_catch_up.noted(release)
    return plugin_switch()


# --- what this cad is: a global install, and by which installer -------------------------------------------------------


def tool_command(tool: Path, windows: bool = os.name == "nt") -> Path:
    """The ``cad`` command of the environment ``tool``, its own (``Scripts/cad.exe``, ``bin/cad``): the one cad's
    update helper runs (``helper_command``)."""
    return tool / ("Scripts/cad.exe" if windows else "bin/cad")


def uv_tool(prefix: str | None = None) -> Path | None:
    """The environment of the uv tool ``cad`` this process runs from: ``prefix`` (``sys.prefix``) where uv's receipt
    there names ``cad`` first; else None."""
    import tomllib

    folder = Path(prefix or sys.prefix)
    try:
        requirements = tomllib.loads((folder / "uv-receipt.toml").read_text(encoding="utf-8"))["tool"]["requirements"]
        first = requirements[0]
        name = first.get("name") if isinstance(first, dict) else re.split(r"[\s\[<>=!~;@]", str(first))[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return folder if str(name).lower() == "cad" else None


def pipx_tool(prefix: str | None = None) -> Path | None:
    """The environment of the pipx tool ``cad`` this process runs from: ``prefix`` (``sys.prefix``) where it is pipx's
    ``venvs/cad`` (pipx names each environment after its package, and a ``--suffix`` install, ``cad<suffix>``, is not
    the one ``pipx upgrade cad`` upgrades) and pipx's metadata there (``pipx_metadata.json``) names ``cad`` as its
    package; else None."""
    folder = Path(prefix or sys.prefix)
    if folder.name.lower() != "cad" or folder.parent.name != "venvs":
        return None
    try:
        package = json.loads((folder / "pipx_metadata.json").read_text(encoding="utf-8"))["main_package"]["package"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return folder if str(package).lower() == "cad" else None


@dataclass(frozen=True)
class Installer:
    """One installer that makes a global install of cad, and how cad's update uses it. Each command is a function of
    the installer's program as found (``find``): a command line, ``["/path/pipx"]`` or ``[python, "-P", "-m", "pipx"]``."""

    name: str
    owns: Callable[[Path], bool]  # whether it made the environment at this prefix
    find: Callable[[], list[str] | None]  # its program, never one inside cad's environment
    # cad upgraded to the newest release of the major of the release that runs, never below it (``bound``)
    upgrade: Callable[[list[str], str], list[str]]
    # cad upgraded to the newest release of all, never below the release that runs (the floor alone, ``cad>=X``):
    # ``cad update --major``
    cross: Callable[[list[str], str], list[str]]
    put_back: Callable[[list[str], str], list[str]]  # cad installed at a release, after a failed upgrade took it away
    launchers: Callable[[list[str]], list[str]]  # prints the folder its launchers (``cad``, ``cad.exe``) are in
    # The variables its commands need to act on the environment at this prefix, beside the server's own.
    environ: Callable[[Path], dict[str, str]] = lambda _prefix: {}


def _outside(found: str | None, prefix: str | None) -> bool:
    """Whether ``found`` is a file, and not inside this cad's environment (``prefix``), which the update replaces."""
    inside = os.path.normcase(os.path.realpath(prefix or sys.prefix)).rstrip(os.sep) + os.sep
    return bool(found) and os.path.isfile(found) and not os.path.normcase(os.path.realpath(found)).startswith(inside)


def _on_path(name: str, environ: dict[str, str], windows: bool) -> str | None:
    """Program ``name`` on ``PATH``; on Windows only a real ``<name>.exe``. Windows runs a batch file (a ``.cmd`` or
    ``.bat`` shim, pyenv-win's ``pipx.bat``) through cmd.exe, which reads the ``<`` and ``>`` of a requirement such
    as ``cad>=X,<N`` as redirections, so cad never hands one a command: one found only as a batch file is not found."""
    found = shutil.which(f"{name}.exe" if windows else name, path=environ.get("PATH"))
    return None if found is None or (windows and not found.lower().endswith(".exe")) else found


def find_uv(environ: dict[str, str] | None = None, prefix: str | None = None,
            windows: bool = os.name == "nt") -> str | None:
    """uv: on ``PATH`` (on Windows its ``uv.exe`` alone, never a batch file: ``_on_path``), else where uv's own
    installer puts it (``UV_INSTALL_DIR`` and its ``bin``, ``XDG_BIN_HOME``, ``~/.local/bin``, ``~/.cargo/bin``, as the
    install command looks). Never one inside this cad's environment (``prefix``), which the update replaces."""
    environ = os.environ if environ is None else environ
    name = "uv.exe" if windows else "uv"
    home = Path(environ.get("USERPROFILE" if windows else "HOME") or Path.home())
    install = environ.get("UV_INSTALL_DIR")
    folders = [install, install and str(Path(install) / "bin"), environ.get("XDG_BIN_HOME"),
               str(home / ".local" / "bin"), str(home / ".cargo" / "bin")]
    for found in (_on_path("uv", environ, windows),
                  *(str(Path(folder) / name) for folder in folders if folder)):
        if _outside(found, prefix):
            return found
    return None


# Where a system's package manager puts pipx: Homebrew's folders (Apple silicon, Intel macOS, Linux) and the system's.
PIPX_SYSTEM = ("/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin", "/usr/bin")


def find_pipx(environ: dict[str, str] | None = None, prefix: str | None = None, windows: bool = os.name == "nt",
              python: str | None = None) -> list[str] | None:
    """pipx, as the person's ``pipx install cad`` found it: on ``PATH`` (on Windows its ``pipx.exe`` alone, never a
    batch file such as pyenv-win's ``pipx.bat``: ``_on_path``); else where pipx is usually installed --
    ``PIPX_BIN_DIR`` and ``~/.local/bin`` (pipx itself, ``uv tool install pipx``, ``pip install --user pipx`` on
    Linux), Homebrew's folders and ``/usr/bin`` (a system package), ``~/Library/Python/3.*/bin`` (``pip install --user``
    on macOS); on Windows ``%APPDATA%\\Python\\Python3*\\Scripts`` and ``%LOCALAPPDATA%\\Programs\\Python\\Python3*\\Scripts``
    (pip, per user) and Scoop's shims --; else ``python -m pipx`` by the Python this environment was made from
    (``python``: ``sys._base_executable``), which is pipx's own Python where pipx made it from there (``pip install
    --user pipx``, then ``python -m pipx install cad``). Never one inside this cad's environment (``prefix``)."""
    environ = os.environ if environ is None else environ
    name = "pipx.exe" if windows else "pipx"
    home = Path(environ.get("USERPROFILE" if windows else "HOME") or Path.home())
    if windows:
        appdata, local = environ.get("APPDATA"), environ.get("LOCALAPPDATA")
        patterns = [*([str(Path(appdata) / "Python" / "Python3*" / "Scripts")] if appdata else []),
                    *([str(Path(local) / "Programs" / "Python" / "Python3*" / "Scripts")] if local else [])]
        folders = [environ.get("PIPX_BIN_DIR"), str(home / ".local" / "bin"), str(home / "scoop" / "shims")]
    else:
        patterns = [str(home / "Library" / "Python" / "3.*" / "bin")]
        folders = [environ.get("PIPX_BIN_DIR"), str(home / ".local" / "bin"), *PIPX_SYSTEM]
    for pattern in patterns:  # the newest Python's first
        folders += sorted(glob.glob(pattern), key=lambda folder: [int(part) for part in re.findall(r"\d+", folder)],
                          reverse=True)
    for found in (_on_path("pipx", environ, windows),
                  *(str(Path(folder) / name) for folder in folders if folder)):
        if _outside(found, prefix):
            return [found]
    python = python or getattr(sys, "_base_executable", None)
    if python and _outside(python, prefix) and _has_pipx(python):
        return [python, "-P", "-m", "pipx"]
    return None


@functools.lru_cache(maxsize=None)
def _has_pipx(python: str) -> bool:
    """Whether ``python`` can import pipx (its user site included), asked once in a process."""
    try:
        return subprocess.run([python, "-P", "-c", "import importlib.util, sys; "
                               "sys.exit(importlib.util.find_spec('pipx') is None)"],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                              env={name: value for name, value in os.environ.items() if name not in _UNSET},
                              creationflags=0x08000000 if os.name == "nt" else 0).returncode == 0  # CREATE_NO_WINDOW
    except (OSError, subprocess.SubprocessError):
        return False


def pipx_home(prefix: Path) -> dict[str, str]:
    """``PIPX_HOME``, the folder that holds pipx's ``venvs/cad`` at ``prefix``: so pipx upgrades this cad where the
    server's environment names no ``PIPX_HOME`` (a person's shell set one, an agent app started the server)."""
    return {"PIPX_HOME": str(prefix.parent.parent)} if prefix.parent.name == "venvs" else {}


def carried_uv() -> str | None:
    """The uv cad's own ``uv`` dependency carries (``uv.find_uv_bin``), or None. It lives inside cad's environment,
    which the update replaces, so the update runs a copy of it outside (``outside_copy``)."""
    try:
        from uv import find_uv_bin

        found = find_uv_bin()
    except (ImportError, FileNotFoundError, OSError):
        return None
    return found if found and os.path.isfile(found) else None


def update_uv() -> list[str] | None:
    """The uv cad's update of a uv install runs: the person's (``find_uv``), else the one cad carries (``carried_uv``),
    so a uv off the server's PATH still updates cad."""
    found = find_uv() or carried_uv()
    return [found] if found else None


UPDATE_UV = "update-uv"  # the folder in the state folder that holds the copy of the carried uv an update runs


def outside_copy(program: list[str], prefix: str | None = None) -> list[str]:
    """``program`` where its first word lives outside cad's environment (``prefix``); else that file copied to the
    state folder (``UPDATE_UV``) and named there: the update replaces the environment, and a uv inside it would be
    removed under its own run (on Windows it cannot be: the install fails). The copy is made again only where it
    differs in size or is missing; written beside and renamed into place. ``OSError`` where it cannot be made."""
    if not program or _outside(program[0], prefix):
        return program
    source = Path(program[0])
    target = _data() / UPDATE_UV / source.name
    if not (target.is_file() and target.stat().st_size == source.stat().st_size):
        target.parent.mkdir(parents=True, exist_ok=True)
        from cad._internal.atomic_replace import replace_atomic, temp_suffix

        staged = target.with_name(f".{source.name}{temp_suffix()}")
        shutil.copy2(source, staged)
        replace_atomic(staged, target)
    return [str(target), *program[1:]]


# The installers cad's update knows, in the order they are asked (see the module for what each command was measured
# to do). Python flags go only where an install starts afresh (a release put back): an upgrade keeps the environment's
# interpreter. pipx's put-back carries none: pipx makes the environment with its own default Python, as the person's
# ``pipx install cad`` did. pipx's bound is one argument (``--pip-args=...``) with no space or quote in it, so pipx's own
# split of it (``shlex``, non-POSIX on Windows) leaves it one requirement everywhere.
UV = Installer(
    name="uv", owns=lambda prefix: uv_tool(str(prefix)) is not None, find=update_uv,
    upgrade=lambda uv, version: [*uv, "tool", "install", "--upgrade", bound(version)],
    cross=lambda uv, version: [*uv, "tool", "install", "--upgrade", f"cad>={version}"],
    put_back=lambda uv, version: [*uv, "tool", "install", "--managed-python", "--python", "3.14", f"cad=={version}"],
    launchers=lambda uv: [*uv, "tool", "dir", "--bin"])
PIPX = Installer(
    name="pipx", owns=lambda prefix: pipx_tool(str(prefix)) is not None, find=lambda: find_pipx(),
    upgrade=lambda pipx, version: [*pipx, "upgrade", "cad", f"--pip-args={bound(version)}"],
    cross=lambda pipx, version: [*pipx, "upgrade", "cad", f"--pip-args=cad>={version}"],
    put_back=lambda pipx, version: [*pipx, "install", "--force", f"cad=={version}"],
    launchers=lambda pipx: [*pipx, "environment", "--value", "PIPX_BIN_DIR"],
    environ=pipx_home)
INSTALLERS: tuple[Installer, ...] = (UV, PIPX)


@dataclass(frozen=True)
class Global:
    """A global install of cad: its environment, the installer that made it, and that installer's program as found, a
    command line (None where it is not found: then it cannot update)."""

    installer: Installer
    prefix: Path
    program: list[str] | None

    @property
    def launcher(self) -> Path:
        """The environment's own ``cad`` command."""
        return tool_command(self.prefix)


def global_install(prefix: str | None = None) -> Global | None:
    """This process's cad (``prefix``: ``sys.prefix``) as a global install, or None where no installer of
    ``INSTALLERS`` made it (pip into a project's Python, a ``uvx`` run from uv's cache, a development checkout)."""
    folder = Path(prefix or sys.prefix)
    for installer in INSTALLERS:
        if installer.owns(folder):
            return Global(installer, folder, installer.find())
    return None


def _said(command: list[str], timeout: float, *, whole: bool = False) -> str | None:
    """The last line ``command`` printed (``whole``: all it printed) where it ended 0, run with no window in an
    environment that points at nothing of this one; else None."""
    done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          env={name: value for name, value in os.environ.items() if name not in _UNSET},
                          creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return (done.stdout if whole else lines[-1]) if done.returncode == 0 and lines else None


def _pipx_venv(pipx: list[str], timeout: float) -> Path | None:
    """Where pipx keeps its environment of cad: ``<PIPX_LOCAL_VENVS>/cad`` (``pipx environment``, pipx 1.1 and
    later); else, pipx 1.0 (Ubuntu 22.04's) having no ``environment``, the environment its list names cad's command
    in (``pipx list --json``: ``<venv>/bin/cad``, ``<venv>\\Scripts\\cad.exe``). None where pipx names none."""
    folder = _said([*pipx, "environment", "--value", "PIPX_LOCAL_VENVS"], timeout)
    if folder:
        return Path(folder) / "cad"
    listed = _said([*pipx, "list", "--json"], timeout, whole=True)
    paths = json.loads(listed)["venvs"]["cad"]["metadata"]["main_package"]["app_paths"] if listed else []
    return next((Path(path["__Path__"]).parent.parent for path in paths if isinstance(path, dict)), None)


def installed_tool(uv: str | None = None, *, timeout: float = 30.0, pipx: list[str] | None = None) -> Path | None:
    """The environment of the global ``cad`` installed on this computer, wherever this process runs from (uvx's cache,
    say). uv's tool first: where uv says its tools are (``uv tool dir``, which reads ``UV_TOOL_DIR`` as every uv command
    does), uv found as the update finds it (``find_uv``) else the one cad's own ``uv`` dependency carries, and uv's
    receipt there names ``cad`` (``uv_tool``). Else pipx's: where pipx says its environment of cad is (``_pipx_venv``,
    which reads ``PIPX_HOME`` as every pipx command does), pipx found as the update finds it (``find_pipx``), and
    pipx's metadata there names ``cad`` (``pipx_tool``). Either only where its own ``cad``
    command is there (``tool_command``). None where neither names one, or neither can be asked. Never raises."""
    try:
        if uv is None:
            uv = find_uv()
        if uv is None:
            from cad_server._internal.base import find_uv as carried

            uv = carried()
        folder = _said([uv, "tool", "dir"], timeout)
        tool = Path(folder) / "cad" if folder else None
        if tool is not None and uv_tool(str(tool)) is not None and tool_command(tool).is_file():
            return tool
    except Exception:  # noqa: BLE001 - no uv, or one that cannot answer: no uv tool found
        pass
    try:
        pipx = pipx or find_pipx()
        tool = _pipx_venv(pipx, timeout) if pipx else None
        return tool if tool is not None and pipx_tool(str(tool)) is not None and tool_command(tool).is_file() else None
    except Exception:  # noqa: BLE001 - no pipx, or one that cannot answer: no tool found
        return None


# --- the last attempt -------------------------------------------------------------------------------------------------


def last(path: Path | None = None) -> dict[str, Any] | None:
    """The last attempt (``{"release", "from", "at", "outcome", ...}``), or None."""
    try:
        found = json.loads((path or _data() / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(found, dict) and isinstance(found.get("release"), str) and isinstance(found.get("at"), (int, float))
    return found if ok else None


def _wanted(found: dict[str, Any]) -> Any:
    """The release an attempt was for (``wanted``; a record kept before it named one: its ``release``)."""
    return found.get("wanted", found.get("release"))


def _tries(wanted: str) -> int:
    """How many times ``wanted`` has been tried (the last attempt's, where it was for ``wanted``; a record with no
    ``tries``, 1). A ``tries`` that is no integer (null, a string, a float, a bool) counts as 0,
    never raising: the next attempt writes an integer, so the tries stay bounded."""
    found = last()
    if found is None or _wanted(found) != wanted:
        return 0
    tries = found.get("tries", 1)
    return tries if type(tries) is int else 0


def _tried(wanted: str, now: float) -> bool:
    """Whether ``wanted`` is not to be tried now: ``TRIES`` times already, or begun less than ``RETRY_SECONDS`` ago,
    underway or ended (a clock set back counts as long ago): the server a failed update starts never tries again."""
    found = last()
    if found is None or _wanted(found) != wanted:
        return False
    return 0 <= now - float(found["at"]) < RETRY_SECONDS or _tries(wanted) >= TRIES


# --- the check and its trigger ----------------------------------------------------------------------------------------


def due(*, fetch: bool = False, now: float | None = None) -> Due | None:
    """The update to make now (``Due``), or None (see the module). ``fetch``: the feed read first where an hour has
    passed (``updates.feed``); else the feed as last read. Never raises."""
    try:
        found = global_install()
        if not switches()["on"] or found is None or found.program is None:
            return None
        from cad_server import updates

        if not updates.checking():
            return None
        chosen = choose(updates.feed(fetch=fetch), _version())
        now = time.time() if now is None else now
        if chosen is None or underway(now) is not None or _tried(chosen.wanted, now):
            return None
        return chosen
    except Exception:  # noqa: BLE001 - a check that cannot be made is no update
        return None


def helper_command(target: str | None, *, now: float, version: str, prefix: str | None = None, uv: str = "uv",
                   base: str | None = None, record: str = RECORD, tries: int = 1, asked: bool = False,
                   windows: bool = os.name == "nt", install: Global | None = None, start: bool = True,
                   major: bool = False, wanted: str | None = None) -> list[str]:
    """The helper's command line: the Python this environment was made from (``base``: ``sys._base_executable``,
    never this environment's), isolated, running the helper's source, and its one argument: the commands of
    ``install``'s installer (by default uv's, its program ``uv``, for the environment ``prefix``), whose variables
    (``Installer.environ``) the trigger sets in the helper's environment, and its name (``installer``); ``target``, the
    release asked for (None: whatever the upgrade gets); ``wanted``, the release the attempt is for (``target`` or
    ``LATEST`` by default); ``asked``, a typed update; ``major``, ``cad update --major``: the installer's crossing
    command for its upgrade, and a release of a higher major accepted; else its upgrade inside this release's major
    (``bound``), and only a release of this major accepted (``auto_update_helper``); ``start``, whether it starts the
    server after the update. The installer's name, ``wanted``, ``asked`` and ``major`` the helper keeps in the
    attempt's record."""
    prefix = str(install.prefix) if install is not None else prefix or sys.prefix
    installer, program = (install.installer, install.program or [uv]) if install is not None else (UV, [uv])
    told = {"cad": str(tool_command(Path(prefix), windows)), "target": target, "prefix": prefix, "record": record,
            "from": version, "at": now, "tries": tries,
            "upgrade": installer.cross(program, version) if major else installer.upgrade(program, version),
            "put_back": installer.put_back(program, version), "launchers": installer.launchers(program),
            "installer": installer.name, "wanted": wanted or target or LATEST, "asked": asked, "major": major,
            "start": start}
    python = base or getattr(sys, "_base_executable", None) or sys.executable
    return [python, "-I", "-S", "-c", HELPER.read_text(encoding="utf-8"), json.dumps(told)]


BEGUN, UNDERWAY, TRIED = "begun", "underway", "tried"  # what starting an update found (``_claim``)


def _claim(*, release: str, wanted: str, version: str, installer: str, automatic: bool,
           major: bool) -> tuple[str, dict[str, Any]]:
    """Starting an update, one step across processes, under the state folder's lock (see the module's trigger): where
    an attempt is underway, of whatever release (``underway``), ``(UNDERWAY, that attempt)``; for an automatic update
    whose ``wanted`` is not to be tried now (``_tried``: another process's attempt ended since the check), ``(TRIED,
    {})``; else the attempt before counted where it was not, as it stands (``event``, ``wait`` false: this one takes
    its place in the record), and this one kept as underway: ``(BEGUN, this attempt)``. The time is read once the
    lock is held: read before, a process that waited for the lock would find the attempt the other began later than
    its own now, which ``underway`` takes for a clock set back, and begin a second. The count is sent once the lock is
    let go. ``OSError`` where the record cannot be written."""
    from cad_server._internal.file_lock import state

    folder = _data()
    folder.mkdir(parents=True, exist_ok=True)
    counted: Any = None
    with state(folder):
        now = time.time()
        found = underway(now)
        if found is not None:
            return UNDERWAY, found
        if automatic and _tried(wanted, now):
            return TRIED, {}
        before = last()
        if before is not None and not before.get("reported"):
            counted = event(before, wait=False)
        kept = {"release": release, "wanted": wanted, "from": version, "at": now, "tries": _tries(wanted) + 1,
                "outcome": "underway", "installer": installer, "asked": not automatic, "major": major}
        _keep(folder / RECORD, kept)
    if isinstance(counted, dict):
        try:
            from cad_server import analytics

            analytics.update(**counted)
        except Exception:  # noqa: BLE001 - a count never fails the update
            pass
    return BEGUN, kept


def _start(target: str | None, *, automatic: bool, start: bool, major: bool,
           wanted: str | None) -> tuple[str, dict[str, Any]]:
    """The update to ``target`` begun (``trigger``'s work), or the attempt underway found: ``(BEGUN, the attempt)``,
    ``(UNDERWAY, the attempt underway)``, or ``("", {})`` where none could begin (``TRIED`` too)."""
    from cad.engine.places import detached

    found = global_install()
    if found is None or found.program is None:
        return "", {}
    version = _version()
    bound(version)  # a release cad can bound an upgrade by, or none begins (``ValueError``)
    named = target or LATEST
    found = Global(found.installer, found.prefix, outside_copy(found.program, str(found.prefix)))
    python = getattr(sys, "_base_executable", None) or sys.executable
    inside = os.path.normcase(os.path.realpath(sys.prefix)).rstrip(os.sep) + os.sep
    if os.path.normcase(os.path.realpath(python)).startswith(inside):
        return "", {}  # no Python outside this environment to run it with
    said, kept = _claim(release=named, wanted=wanted or named, version=version, installer=found.installer.name,
                        automatic=automatic, major=major)
    if said != BEGUN:
        return (said if said == UNDERWAY else ""), kept
    record = _data() / RECORD
    try:
        command = helper_command(target, now=kept["at"], version=version, record=str(record), tries=kept["tries"],
                                 asked=not automatic, install=found, start=start, major=major, wanted=kept["wanted"])
        env = {**{name: value for name, value in os.environ.items() if name not in _UNSET},
               **found.installer.environ(found.prefix)}
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=env, cwd=str(record.parent), **detached())
    except Exception as error:
        # Kept as underway, an attempt whose helper never started would hold every update for the hour: it failed.
        _keep(record, {**kept, "outcome": "failed", "ended": time.time(),
                       "detail": f"the update's helper could not start: {type(error).__name__}: {error}"})
        raise
    return BEGUN, kept


def trigger(target: str | None, *, automatic: bool = True, start: bool = True, major: bool = False,
            wanted: str | None = None) -> bool:
    """The update to ``target`` (None: whatever the upgrade gets) begun, for ``wanted`` (``target`` by default): in one
    step across processes (``_claim``) the attempt before counted where it was not and this one kept (``RECORD``,
    outcome ``underway``), unless one is underway (or, ``automatic``, ``wanted`` was tried since the check); then the
    helper started, detached, with no window, in an environment that points at nothing of this one (``_UNSET``) and
    holds the installer's variables (``Installer.environ``); ``automatic``: the server's own update, else a typed one
    (``asked`` in the record); ``major``: ``cad update --major``; ``start``, the helper starts the server after it
    (false: none ran when it began). Whether this call started one; never raises."""
    try:
        return _start(target, automatic=automatic, start=start, major=major, wanted=wanted)[0] == BEGUN
    except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
        return False


def _keep(path: Path, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, json.dumps(record, sort_keys=True).encode("utf-8"))


def _begin_due(*, fetch: bool = False) -> Due | None:
    """The automatic update begun where it is due (``due``, ``trigger``), under ``_BEGIN``: what it updates to, or
    None."""
    with _BEGIN:
        found = due(fetch=fetch)
        return found if found is not None and trigger(found.target, wanted=found.wanted) else None


def at_start() -> bool:
    """First thing as the server starts, before it opens its door (nothing has run): the update begun where it is due
    by the feed as last read. True when it was: the server then exits ``UPDATING``, and the helper starts the next."""
    return _begin_due() is not None


def tend(*, working: bool, ran: bool, quiet_for: float) -> bool:
    """As the server tends itself: the update begun where it is due and nothing is in flight (``working``) -- nothing
    has run since the server started (``ran``), or nothing for ``IDLE_SECONDS`` (``quiet_for``). True when it was."""
    if working or (ran and quiet_for < IDLE_SECONDS):
        return False
    return _begin_due() is not None


def after_failed_start() -> str | None:
    """``cad server start`` failed: the update begun where it is due, the feed read first where an hour has passed.
    What it updates to, in words (the release, or the newest release of this major), or None."""
    found = _begin_due(fetch=True)
    if found is None:
        return None
    numbers = release(_version())
    return found.target or (f"the newest {numbers[0]}.x release" if numbers else "the newest release")


# --- an update asked for: ``cad update`` ------------------------------------------------------------------------------

NOT_THE_TOOL = ("the cad server running is not a global install of cad: run `cad server stop`, then `cad server "
                "start`, then `cad update` again")
CHECK_OFF = ("this cad server does not look for updates (CAD_UPDATE_CHECK=0, CI, or a development build), so it does "
             "not update cad")


def no_installer(name: str) -> str:
    return f"cad was installed with {name}, and the cad server cannot find {name}, so it cannot update cad"


def asked(*, major: bool = False, pypi: Callable[[], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """``cad update`` judged by the server it asks (``{"op": "update"}``, ``"major": true`` for ``--major``), for the
    cad this process is: ``{"failed"}`` in one line where it cannot update cad -- not a global install, the check
    turned off for this process (``updates.checking``), its installer not found, no release cad can bound an upgrade by
    --; ``{"ok": true, "newest"}``, this release, where PyPI names none newer that this update takes (of this cad's
    major, ``choose``; of all, ``major``); or ``{"ok": true, "updating", "from"}``, the update to ``begin``:
    ``updating`` the release PyPI names, or None where PyPI could not be asked, or named no release of this major (the
    upgrade then runs all the same); ``"major": true`` with ``major``. Without ``major``, ``higher``: the newest release
    of a higher major, where PyPI names one. PyPI is asked now (``updates.pypi``, or ``pypi``). Never raises."""
    try:
        version = _version()
        found = global_install()
        if found is None:
            return {"failed": NOT_THE_TOOL}
        from cad_server import updates

        if not updates.checking():
            return {"failed": CHECK_OFF}
        if found.program is None:
            return {"failed": no_installer(found.installer.name)}
        if release(version) is None:
            return {"failed": f"cad {version} is no release, so it does not update itself"}
        known = (pypi or updates.pypi)()
        if major:
            target = known.get("latest") if known else None
            if target is not None and not newer(target, version):
                return {"ok": True, "newest": version}
            return {"ok": True, "updating": target, "from": version, "major": True}
        out = {"higher": higher(known, version)} if higher(known, version) else {}
        chosen = choose(known, version)
        if chosen is None and known is not None:
            return {"ok": True, "newest": version, **out}
        return {"ok": True, "updating": chosen.target if chosen else None, "from": version, **out}
    except Exception as error:  # noqa: BLE001 - said in its one line, never a crash of the server's
        return {"failed": f"could not look for an update: {type(error).__name__}: {error}"}


def underway(now: float | None = None) -> dict[str, Any] | None:
    """The attempt underway now, of any release: the last one, begun less than ``RETRY_SECONDS`` ago and not ended (a
    helper that died ends nothing, so past that none is). None where none is."""
    found = last()
    if found is None or found.get("outcome") != "underway":
        return None
    return found if 0 <= (time.time() if now is None else now) - float(found["at"]) < RETRY_SECONDS else None


def begin(target: str | None, *, start: bool = True, major: bool = False) -> dict[str, Any] | None:
    """The update to ``target`` (None: whatever the upgrade gets) that ``cad update`` asked for (``major``: ``cad update
    --major``), begun now -- or the attempt underway joined, whatever its release, another process's too (``underway``,
    asked again in the step that begins one, ``_claim``): never a second at once. Never the install command after it.
    ``start``: the helper starts the server after it (false where ``cad update`` found none running). The attempt's
    record (``release``, ``at``), or None where it could not begin."""
    with _BEGIN:
        found = underway()
        if found is not None:
            return found
        try:
            said, found = _start(target, automatic=False, start=start, major=major, wanted=None)
        except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
            return None
        return found if said in (BEGUN, UNDERWAY) else None


# --- an attempt counted -----------------------------------------------------------------------------------------------

ENDED = frozenset({"installed", "current", "failed"})  # the helper's outcomes: the attempt ended
WAIT = object()  # ``event``: not yet, the install command's run for the new cad still underway


def event(found: dict[str, Any], *, wait: bool = True) -> dict[str, Any] | object | None:
    """The ``update`` event an ended attempt (``found``, the record) is counted as (``analytics.update``'s arguments),
    ``WAIT`` while the install command's run for the cad it installed is underway (``wait`` false: the event as it
    stands, that run ``underway``), or None for a record that is none of an ended attempt. That run is one begun since
    the attempt began (``plugin_catch_up.last``, ``since``): a run begun before it is another's."""
    outcome = found.get("outcome")
    if outcome not in ENDED:
        return None
    reason = None
    if outcome == "failed":
        detail = found.get("detail")
        # ``older``: a release it may not end on (the helper's "which it may not end on"); a newer one that is not
        # what was asked (``--major`` that did not cross: "it installed X, not Y") is the upgrade's failure.
        reason = "older" if isinstance(detail, str) and detail.startswith("it installed ") \
            and detail.endswith("which it may not end on") else "upgrade"
        if found.get("restored") is True:
            outcome = "restored"
        elif found.get("restored") is False:
            reason = "put_back"
    plugin = "none"
    if outcome == "installed":
        from cad_server._internal import plugin_catch_up

        at = found.get("at")
        ran = plugin_catch_up.last(str(found.get("release")), since=float(at) if isinstance(at, (int, float)) else 0.0)
        if ran == plugin_catch_up.UNDERWAY and wait:
            return WAIT
        plugin = ran or "none"
    installer = found.get("installer")
    if installer not in {each.name for each in INSTALLERS}:  # a record kept before it named one: this cad's
        installer = next((each.name for each in INSTALLERS if each.owns(Path(sys.prefix))), None)
    tries = found.get("tries", 1)
    return {"earlier": found.get("from"), "outcome": outcome, "reason": reason,
            "tries": tries if type(tries) is int else 1, "installer": installer, "asked": found.get("asked") is True,
            "plugin": plugin}


def report() -> bool:
    """The last attempt counted (see the module), once: where it ended and is not ``reported`` yet, and nothing it
    waits for is underway (``event``; a new attempt about to take its place in the record counts it as it stands,
    ``_claim``), the record marked ``reported`` under the state folder's lock, then the event kept for the sender
    (``analytics.update``, under the rules every count goes by). Whether it was counted now; never raises."""
    try:
        from cad_server._internal.file_lock import state

        folder = _data()
        if not (folder / RECORD).is_file():
            return False
        with state(folder):
            found = last()
            if found is None or found.get("reported"):
                return False
            counted = event(found)
            if not isinstance(counted, dict):
                return False
            _keep(folder / RECORD, {**found, "reported": True})
        from cad_server import analytics

        analytics.update(**counted)
        return True
    except Exception:  # noqa: BLE001 - a count never fails the server, nor the update
        return False
