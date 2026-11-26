"""cad's own update: what a global install is, the switches, the check, and its trigger.

**The rule.** cad installs by itself any newer release with the same major version number as its own, and its own update
never crosses a major: a release of a higher major is only named where it is out (``MAJOR_LINE``). Every update is
forward only. The
bound is worked out from the release that runs each time (``bound``: ``cad>=<this release>,<<its major + 1>``), never a
fixed number, so it holds on a computer that has not updated for months.

**How a release arrives.** The installer that made cad updates it where it is, with the person's own settings: uv
(``base.find_uv``) runs ``uv tool upgrade "cad==<release>"`` on its tool, its receipt keeping its own requirements;
pipx (``find_pipx``) runs ``pipx runpip cad install "cad==<release>"``, pip inside its environment, the person's pin
there as it was (pipx 1.19 notes the requirement as the one it was installed by, which ``pipx upgrade`` moves on
from). What cad adds is what makes that safe where processes run cad, which on Windows hold its files (the installer
downloads and prepares the release before it changes the environment, so a download that fails leaves cad as it was):
the server stopped, on Windows every other process of the environment stopped and its ``cad`` command moved aside,
the upgrade, a check that the release runs, a repair in place where it does not, and, where that leaves no cad that
runs, cad installed again whole. That work is the worker's (``auto_update_helper``), run from the release it updates to
in uv's cache, never from the environment it replaces (``from_cache``): the newest release's code does the update.
This module decides when it runs and keeps its record.

**A global install** (``global_install``) is a cad whose environment uv's ``uv tool install cad`` made (uv's receipt
there names ``cad``) or pipx's ``pipx install cad`` (pipx's ``venvs/cad``, its metadata naming ``cad``): either updates
itself, by its installer. ``installed_tool`` finds the global install from anywhere (a cad run from uv's cache): uv's
tool first, then pipx's.

**The switches** are the person's, in cad's settings (``settings.json`` in the state folder): ``auto_update.on``,
whether cad updates itself, ON where nothing is kept -- but OFF where 0.10.0 to 0.11.11 kept the person's own off
(``updates.automatic: false``) and ``auto_update.on`` was never chosen; ``cad update auto on`` then writes ``true``,
which wins --; and ``plugin.auto_update``, whether the server runs ``cad plugin install`` once where cad is newer than
the release the plugin is up to date for (``plugin_catch_up``), OFF where nothing is kept.

**The check** (``due``): switch on, the check not turned off for this process (``updates.checking``), this cad a
global install, no attempt underway, of whatever release (``underway``, ``believed``), and an update the version feed
calls for (``choose``): the newest release of this cad's major its ``lines`` names, where it is newer; where it names
none of this major, its ``latest`` where that is of this major and newer, or, where ``latest`` is of a higher major,
the bounded build with no release named, so a feed without ``lines`` never strands a computer. That release
(``wanted``) is due by the schedule (``next_try``): after its ``n``-th automatic try it waits ``min(2 ** (n - 1),
WAIT_HOURS)`` hours, and no automatic attempt begins where ``DAILY`` began in the last day, of any release. The tries
are kept by release (``tries``, ``TRIED``), so a newer release starts afresh and a server of another release never
sets them back. One exception: a release an attempt at which ended ``start_failed`` (its server did not start, and
the release before runs again), automatic or a person's own, is not tried again by itself (``given_up``): a server
restarting for nothing once a day is worse than waiting for the next release; ``cad update`` still tries it. Not due either where the environment
already holds ``wanted`` or newer while this older server runs (``stale``): ``cad server start`` replaces the server.
Where an update is due and none can begin (``blocked``: no uv), the check counts it once for that release
(``BLOCKED``).

**When.** cad updates itself at two moments alone, never by how busy or idle the server is, so nothing that keeps
talking to it can put an update off for ever, and no update runs in the background: a person's ask (``cad update``,
and the viewer's button, ``button``, which is ``cad update``'s), and the server's start, where the check finds an
update due by the feed as last read, never a network wait (``restart``: the start becomes the update,
``cad_server.engine.daemon.main``, never for ``--foreground`` or ``--port``), and ``cad server start`` where the start
failed, the feed read first where an hour has passed (``after_failed_start``): a release whose server cannot start
still updates. The server's tending only reads the feed (``updates.refresh``). A server never restarted, whose person
never asks, stays on the release it runs, the button showing the update and ``notice`` and ``cad doctor`` saying so.
Nothing waits for what is in flight: the update stops the server at once, as ``cad server stop`` does, and a command
it cuts short says cad updated itself while it ran.

**The trigger** (``trigger``) begins the update in one step across processes (``_claim``, under the state folder's
lock): where an attempt is underway none begins (an automatic update) or it is joined (``cad update``); else the
attempt before counted where it was not, and this one kept as underway, its ``phase`` ``switching``. Then uv builds
the environment of the release the record names in its cache (``build``: where it cannot, the attempt ends ``failed``
with uv's cause, nothing touched), and the worker starts from it, detached (``from_cache``, ``helper_command``). The
attempt is kept in the state folder (``RECORD``: ``release``, ``wanted``, ``from``,
``at``, ``tries``, ``installer``, ``asked`` -- a person's own update --, ``phase``, ``beat``, then the worker's
``ended``, ``outcome``,
``detail``, ``restored``, ``started``, ``worker`` (its own release) and, where it did not install what it was for,
``cause``: one word of
``auto_update_helper.CAUSES``, said in plain words by ``SAID``, and what to do about it by ``advice``, the one line
``cad doctor``, ``cad update`` and ``notice`` give; ``dismissed`` once the person put its failure away), which ``cad
doctor`` and the viewer's update button (``button``) show, with the worker's log (``LOG``; the attempt before's
``LOG_BEFORE``; never sent). Every change of it that another process may make at the same moment holds the state
folder's lock: the claim, the worker's beat, ``dismiss``, ``report``. While the
worker switches releases (``switching``) a ``cad`` command that finds no server waits for the next
(``cad.engine.client.SWITCHING``), and a server of the release being left starts none in its place (``leaving``). A
worker silent for ``LOST_SECONDS`` is taken for lost; should it wake, it writes no outcome over another attempt's
record.

**Counted** (``report``), once per attempt that ended, by the server that runs after it (and by a trigger, before a new
attempt takes the record's place): one ``update``
event (``analytics.update``): the release before, how it ended (``installed``, ``current``, ``failed``, ``restored``
where the release before runs again, or ``lost``), which step failed (``upgrade``: the release could not be
installed, did not run, or its server did not start; ``older``: it installed a release it may not end on; ``put_back``: and the
release before could not be put back either), why (``cause``; ``already`` where the environment ran the release
already), the tries, the installer, whether it was typed, and for a newer cad how the install command's run for it
went (``plugin_catch_up.last``).

**Asked for** (``cad update``, and the viewer's update button: the server judges it, ``asked``, and begins it at once,
``begin``; with no server running, ``cad update`` itself, whose worker then starts none): PyPI asked now
(``updates.pypi``) for the newest release of this cad's major, chosen as the feed's answer is; where a release of a
higher major is out, the answer names it (``higher``, ``MAJOR_LINE``), and nothing crosses to it. Neither the switch
nor the schedule applies, and no automatic try is spent; where PyPI cannot be reached, the build
runs all the same, bounded.

**A cad that has stayed behind** (``notice``): where automatic updates are on and a global install has been behind a
release of its own major for ``BEHIND_SECONDS``, a ``cad`` command says so in one line on stderr after its own output,
at most once a day (``cad_server.cli``): the command line's counterpart of the viewer's update button.

Imports the standard library alone; what it asks of cad it imports as it asks.
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
INSTALL_LOG = "install-command.log"  # the output of the last `cad plugin install` the server ran (``plugin_catch_up``)
LOG, LOG_BEFORE = "auto-update.log", "auto-update.1.log"  # the worker's log of the last attempt and the one before
BLOCKED = "auto-update-blocked.json"  # the last release no update could begin for, counted once (``_blocked``)
# Each release's automatic tries, and the attempts of the last day (``tries``): the name every release from 0.11.12
# keeps them under.
TRIED = "tried"
HOUR, DAY = 3600.0, 86400.0
WAIT_HOURS = 24  # the longest wait between two automatic tries of one release: 1, 2, 4, 8, 16, then 24 hours
DAILY = 4  # the most attempts begun in a day, of every release, that an automatic one may begin beside
KEPT = 8  # how many releases' tries are kept: the newest tried
LOST_SECONDS = 20 * 60.0  # an attempt whose worker has not beaten for this long is lost (``believed``)
LONGEST_SECONDS = 6 * HOUR  # nor is one believed underway this long after it began, whatever its beat says
RETRY_SECONDS = HOUR  # how long an attempt a release before the beat kept is believed underway
# What the record names as the release of a typed update begun with no answer from PyPI: whatever the build gets.
LATEST = "latest"
# How long uv may take to upgrade cad (``auto_update_helper``).
UPGRADE_SECONDS = 900.0
# Who makes a global install of cad (``global_install``), named in the record and its count.
INSTALLERS = ("uv", "pipx")
# The worker's entry: ``python -P -m <HELPER> <told>``, run by uv from the release it updates to (``from_cache``). A
# contract every later release keeps, with ``told`` (``helper_command``): an older release starts a newer one's worker
# by it.
HELPER = "cad_server._internal.auto_update_helper"
# One update begun at a time in a process: the check and the trigger together (``restart``, ``begin``).
_BEGIN = threading.Lock()
# What the worker's environment leaves out: anything that would point its Python, or what it runs, elsewhere.
_UNSET = ("PYTHONPATH", "PYTHONHOME", "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__", "VIRTUAL_ENV")


def release(text: Any) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text) if isinstance(text, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def newer(theirs: Any, mine: Any) -> bool:
    """Whether release ``theirs`` is later than ``mine``; False where either is no plain ``X.Y.Z``."""
    a, b = release(theirs), release(mine)
    return a is not None and b is not None and a > b


def bound(version: str) -> str:
    """The requirement that keeps an update inside release ``version``'s major and never below it: ``cad>=<version>,<
    <its major + 1>``, worked out from the release each time (see the module). ``ValueError`` for no plain ``X.Y.Z``."""
    numbers = release(version)
    if numbers is None:
        raise ValueError(f"not a release: {version!r}")
    return f"cad>={version},<{numbers[0] + 1}"


# The migration guides, which say what a new major version asks of a person.
MIGRATIONS = "https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations"
# The one line that says a release of a higher major is out (``cad update``, ``cad doctor``, ``cad update auto``).
MAJOR_LINE = f"cad {{release}}, a new major version, is out: the migration guides say what changes ({MIGRATIONS})"


@dataclass(frozen=True)
class Due:
    """An update to make: ``target``, the release it moves to (None: the newest release of this major the build
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
    return Due(None, latest)  # no release of this major named: the bounded build, counted by ``latest``


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
    """Whether the server runs ``cad plugin install`` once where cad is newer than the release it is up to date for
    (``plugin_catch_up``): off unless ``true`` is kept."""
    return _section(PLUGIN_SECTION, path).get("auto_update") is True


def change_plugin(on: bool, release: str | None = None, *, note: bool = True) -> bool:
    """``plugin.auto_update`` changed under the state folder's lock; turned on, the plugin is taken as up to date for
    ``release``, the cad that turned it on (this one's by default: ``plugin_catch_up.noted``) -- unless ``note`` is
    false: turned on by the hosted install command whose plugin step did not go well for every app it found (it ended
    non-zero, or an app failed: ``plugin_catch_up.FAILED_ENV``), or by a cad that is no global install, which takes
    nothing as up to date. ``OSError`` where it cannot be written."""
    from cad_server.settings import update_section

    update_section(PLUGIN_SECTION, lambda kept: {**kept, "auto_update": on})
    if on and note:
        from cad_server._internal import plugin_catch_up

        plugin_catch_up.noted(release)
    return plugin_switch()


# --- what this cad is: a global install, and by which installer -------------------------------------------------------


def tool_command(tool: Path, windows: bool = os.name == "nt") -> Path:
    """The ``cad`` command of the environment ``tool``, its own (``Scripts/cad.exe``, ``bin/cad``): the one cad's
    update worker runs (``helper_command``)."""
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


def _outside(found: str | None, prefix: str | None) -> bool:
    """Whether ``found`` is a file, and not inside this cad's environment (``prefix``)."""
    inside = os.path.normcase(os.path.realpath(prefix or sys.prefix)).rstrip(os.sep) + os.sep
    return bool(found) and os.path.isfile(found) and not os.path.normcase(os.path.realpath(found)).startswith(inside)


def _on_path(name: str, environ: dict[str, str], windows: bool) -> str | None:
    """Program ``name`` on ``PATH``; on Windows only a real ``<name>.exe``. Windows runs a batch file (a ``.cmd`` or
    ``.bat`` shim, pyenv-win's ``pipx.bat``) through cmd.exe, which reads the ``<`` and ``>`` of a requirement such
    as ``cad>=X,<N`` as redirections, so cad never hands one a command: one found only as a batch file is not found."""
    found = shutil.which(f"{name}.exe" if windows else name, path=environ.get("PATH"))
    return None if found is None or (windows and not found.lower().endswith(".exe")) else found


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


@dataclass(frozen=True)
class Global:
    """A global install of cad: its environment, who made it (``INSTALLERS``), the person's uv (``base.find_uv``,
    which a pipx install needs too, for the kernel's environments), and for a pipx install pipx (``find_pipx``); None
    where there is none: then it cannot update."""

    installer: str
    prefix: Path
    uv: str | None
    pipx: list[str] | None = None

    @property
    def launcher(self) -> Path:
        """The environment's own ``cad`` command."""
        return tool_command(self.prefix)


def global_install(prefix: str | None = None) -> Global | None:
    """This process's cad (``prefix``: ``sys.prefix``) as a global install, or None where neither uv nor pipx made its
    environment (pip into a project's Python, a ``uvx`` run from uv's cache, a development checkout)."""
    folder = Path(prefix or sys.prefix)
    installer = "uv" if uv_tool(str(folder)) is not None else "pipx" if pipx_tool(str(folder)) is not None else None
    if installer is None:
        return None
    return Global(installer, folder, find_uv(), find_pipx(prefix=str(folder)) if installer == "pipx" else None)


def find_uv() -> str | None:
    """The person's uv (``base.find_uv``), or None where there is none."""
    from cad_server._internal.base import Refused, find_uv as found

    try:
        return found()
    except Refused:
        return None


def site_packages(prefix: str | os.PathLike[str] | None = None) -> list[Path]:
    """The packages folders of the environment at ``prefix`` (``sys.prefix``): ``Lib/site-packages`` on Windows,
    ``lib/python*/site-packages`` elsewhere."""
    folder = Path(prefix or sys.prefix)
    return [found for pattern in ("Lib/site-packages", "lib/python*/site-packages") for found in sorted(folder.glob(pattern))]


def holds(folder: str | os.PathLike[str], *, whole: bool = True) -> str | None:
    """The newest release of cad the packages folder ``folder`` holds whole: a ``cad-<release>.dist-info`` with its
    ``RECORD`` and ``METADATA`` (an install stopped midway leaves one with neither; ``whole`` false: any, by its name
    alone); None where it holds none."""
    found = []
    for path in Path(folder).glob("cad-*.dist-info"):
        numbers = release(path.name[len("cad-"):-len(".dist-info")])
        if numbers is not None and (not whole or (path / "RECORD").is_file() and (path / "METADATA").is_file()):
            found.append(numbers)
    return ".".join(map(str, max(found))) if found else None


def installed(prefix: str | os.PathLike[str] | None = None, *, whole: bool = True) -> str | None:
    """The release of cad the environment at ``prefix`` (``sys.prefix``) holds now, as its packages folder says
    (``holds``; ``whole`` false: one an install left half made too), whatever release this process runs: a process
    started before an update runs the release before it. None where it holds none."""
    found = [held for folder in site_packages(prefix) if (held := holds(folder, whole=whole)) is not None]
    return max(found, key=release) if found else None


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
    does), the person's uv (``find_uv``), and uv's receipt there names ``cad`` (``uv_tool``). Else pipx's: where pipx says its environment of cad is (``_pipx_venv``,
    which reads ``PIPX_HOME`` as every pipx command does), pipx found as the update finds it (``find_pipx``), and
    pipx's metadata there names ``cad`` (``pipx_tool``). Either only where its own ``cad``
    command is there (``tool_command``). None where neither names one, or neither can be asked. Never raises."""
    try:
        uv = uv or find_uv()
        if uv is None:
            raise FileNotFoundError("uv")
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


def tool_bin(install: Global | None = None, timeout: float = 30.0) -> Path | None:
    """The bin folder of the global install ``install`` (this cad's by default), where its installer puts cad's command:
    uv's (``uv tool dir --bin``, which reads ``UV_TOOL_BIN_DIR`` as every uv command does), pipx's (``pipx environment
    --value PIPX_BIN_DIR``, which reads ``PIPX_BIN_DIR``); None where it cannot say. Never raises."""
    try:
        install = install or global_install()
        asked = None if install is None else [*install.pipx, "environment", "--value", "PIPX_BIN_DIR"] \
            if install.installer == "pipx" and install.pipx else [install.uv, "tool", "dir", "--bin"] if install.uv \
            else None
        said = _said(asked, timeout) if asked else None
    except Exception:  # noqa: BLE001 - an installer that cannot answer names no folder
        return None
    return Path(said) if said else None


def tidy(windows: bool = os.name == "nt") -> list[str]:
    """On Windows, for a global install: each ``cad.exe`` cad's update moved aside (``auto_update_helper.ASIDE``) and
    could not remove then, as a process still ran it, removed where none does now. The paths removed. Elsewhere
    nothing. Never raises."""
    if not windows or uv_tool() is None and pipx_tool() is None:
        return []
    from cad_server._internal.auto_update_helper import ASIDE

    folder, removed = tool_bin(), []
    for path in sorted(folder.glob(ASIDE.format(pid="*"))) if folder is not None else ():
        try:
            path.unlink()
            removed.append(str(path))
        except OSError:
            continue  # still running: the next tidying
    return removed


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


def _time(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _count(value: Any) -> int:
    """A count of tries as kept: a whole number from 0; anything else (null, a string, a float, a bool) 0, never
    raising, so a record no release wrote never stops an update."""
    return value if type(value) is int and value >= 0 else 0


def tries(now: float | None = None) -> dict[str, Any]:
    """The tries (``TRIED``): ``tried``, each release's automatic tries by the release they were for (``{release:
    {"tries", "first", "at", "cause"}}``: how many, when the first and the last began, why the last did not install
    it), the ``KEPT`` newest; ``recent``, when each attempt of the last ``DAY`` began, of every release, typed ones too;
    and ``seen``, the last attempt they count. The last attempt (``RECORD``) is counted in where they do not count it
    yet: one a release before them began, which keeps none of them, by the tries its record names (``_counted``). Kept
    by release and apart from the record, which every release writes whole: a server of another release, an earlier
    one too, never sets a release's count back. Never raises."""
    now = time.time() if now is None else now
    try:
        kept = json.loads((_data() / TRIED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    kept = kept if isinstance(kept, dict) else {}
    tried = kept.get("tried") if isinstance(kept.get("tried"), dict) else {}
    found = {"tried": {name: {"tries": _count(entry.get("tries")),
                              **{key: entry[key] for key in ("first", "at") if _time(entry.get(key))},
                              **({"cause": entry["cause"]} if isinstance(entry.get("cause"), str) else {})}
                       for name, entry in tried.items() if isinstance(name, str) and isinstance(entry, dict)},
             "recent": [at for at in kept.get("recent") or () if _time(at)] if isinstance(kept.get("recent"), list)
             else [], "seen": kept.get("seen") if _time(kept.get("seen")) else None}
    return _counted(found, last(), now)


def _counted(book: dict[str, Any], found: dict[str, Any] | None, now: float) -> dict[str, Any]:
    """``book`` (``tries``) with the attempt ``found`` (the record) counted in where it is not yet (its ``at`` is not
    ``seen``): its begin among the ``recent``, and, where it was automatic, its release's tries -- one more than kept,
    or the record's own count where that is more (a release before kept them there alone) --; the record's cause the
    last try's where it is that try, and ``start_failed`` that release's whoever asked (a person's own update that
    ended so holds the release back from the automatic one as an automatic try does: ``given_up``); then the
    ``recent`` of the last ``DAY`` alone (a clock set back counts as long ago)."""
    wanted = _wanted(found) if found is not None else None
    if found is not None and isinstance(wanted, str):
        at, entry = found["at"], book["tried"].get(wanted)
        if at != book["seen"]:
            book["recent"].append(at)
            if found.get("asked") is not True:
                before = entry or {}
                entry = book["tried"][wanted] = {
                    "tries": max(before.get("tries", 0) + 1, _count(found.get("tries", 1))),
                    "first": before.get("first", at), "at": at}
            book["seen"] = at
        if entry is not None and entry.get("at") == at:
            word = cause(found, now)
            if word is not None:
                entry["cause"] = word
        elif found.get("cause") == "start_failed":
            # A person's own update, which spends no try, showed it too: the release's server does not start here.
            book["tried"][wanted] = {**(entry or {"tries": 0, "first": at, "at": at}), "cause": "start_failed"}
    book["recent"] = sorted(at for at in book["recent"] if 0 <= now - at < DAY)
    return book


def next_try(wanted: str, book: dict[str, Any], now: float) -> float | None:
    """When an automatic try of ``wanted`` may begin by the schedule (``book``: ``tries``), or None: now. After its
    ``n``-th try a release waits ``min(2 ** (n - 1), WAIT_HOURS)`` hours from that try's begin -- 1, 2, 4, 8, 16, then
    24 --, and is never given up on; and no automatic attempt begins where ``DAILY`` began in the last ``DAY``, of
    whatever release, typed or not. A clock set back counts as long ago."""
    later = []
    entry = book["tried"].get(wanted) or {}
    if entry.get("tries", 0) >= 1 and _time(entry.get("at")):
        wait = min(2 ** min(entry["tries"] - 1, 5), WAIT_HOURS) * HOUR
        if 0 <= now - entry["at"] < wait:
            later.append(entry["at"] + wait)
    if len(book["recent"]) >= DAILY:
        later.append(book["recent"][-DAILY] + DAY)
    return max(later) if later else None


def _kept(book: dict[str, Any]) -> dict[str, Any]:
    """``book`` as it is written: the ``KEPT`` releases tried last."""
    newest = sorted(book["tried"].items(), key=lambda item: item[1].get("at", 0.0), reverse=True)[:KEPT]
    return {**book, "tried": dict(newest)}


# --- the check and its trigger ----------------------------------------------------------------------------------------


def due(*, fetch: bool = False, now: float | None = None) -> Due | None:
    """The update to make now (``Due``), or None (see the module); one due that cannot begin (``blocked``) counted
    once for its release (``_blocked``). ``fetch``: the feed read first where an hour has passed (``updates.feed``; never for an update that cannot begin);
    else the feed as last read. Never raises."""
    try:
        found = global_install()
        if not switches()["on"] or found is None:
            return None
        from cad_server import updates

        if not updates.checking():
            return None
        stuck = blocked(found)
        chosen = choose(updates.feed(fetch=fetch and stuck is None), _version())
        now = time.time() if now is None else now
        if chosen is None or underway(now) is not None or stale(chosen.wanted):
            return None
        book = tries(now)
        if next_try(chosen.wanted, book, now) is not None or given_up(chosen.wanted, book):
            return None
        if stuck is not None:
            _blocked(found, chosen.wanted, stuck, now)
            return None
        return chosen
    except Exception:  # noqa: BLE001 - a check that cannot be made is no update
        return None


def given_up(wanted: str, book: dict[str, Any]) -> bool:
    """Whether an attempt at ``wanted`` (``book``: ``tries``), its last automatic try or a person's own update since,
    ended with its server not starting (``start_failed``): it is not tried again by itself, only by ``cad update``
    (see the module)."""
    return (book["tried"].get(wanted) or {}).get("cause") == "start_failed"


def _blocked(found: Global, wanted: str, word: str, now: float) -> None:
    """An update to ``wanted`` due, that cannot begin for the global install ``found`` (``word``: ``blocked``'s cause),
    counted once for that release and the one that runs (``BLOCKED`` names the last such pair, kept under the state
    folder's lock before it is counted): the ``update`` event ``blocked``, no try made."""
    from cad_server._internal.file_lock import state

    folder, version = _data(), _version()
    path = folder / BLOCKED
    said = {"from": version, "wanted": wanted}

    def counted() -> bool:
        try:
            kept = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(kept, dict) and {name: kept.get(name) for name in said} == said

    if counted():
        return
    folder.mkdir(parents=True, exist_ok=True)
    with state(folder):
        if counted():
            return
        _keep(path, {**said, "cause": word, "at": now})
    from cad_server import analytics

    analytics.update(earlier=version, outcome="blocked", tries=0, installer=found.installer, asked=False,
                     cause=word)


def stale(wanted: str) -> bool:
    """Whether this server is older than what its own environment holds now (``installed``), which is ``wanted`` or
    newer: another update, or one by hand, got there after it started. No update is due for it and no try is spent:
    the server wants restarting, which ``cad server start`` does, as ``cad doctor`` says."""
    held, mine, want = release(installed()), release(_version()), release(wanted)
    return held is not None and mine is not None and held > mine and (want is None or held >= want)


def blocked(found: Global) -> str | None:
    """Why no update can begin for the global install ``found``, as a cause (``SAID``): ``pinned``, the person pinned
    cad to its release (``pinned``); ``no_installer``, no uv is found, or for a pipx install no pipx. None where one
    can."""
    if pinned(found.prefix):
        return "pinned"
    return "no_installer" if found.uv is None or found.installer == "pipx" and not found.pipx else None


def pinned(prefix: str | os.PathLike[str] | None = None) -> bool:
    """Whether the person pinned the global install at ``prefix`` (``sys.prefix``) to its release, so its installer
    keeps it there: uv's receipt's requirement an exact one (``==``, ``===``), as a person's own ``uv tool install
    cad==X`` writes it (cad's installers write none, ``<N`` or ``>=X,<N``, and an update leaves the receipt as it is),
    which every upgrade to another release fails on; pipx's metadata ``pinned`` (``pipx pin cad``), which ``pipx
    upgrade`` keeps to (a ``pipx install cad==X`` pins nothing: ``pipx upgrade`` moves it on). Never raises."""
    import tomllib

    folder = Path(prefix or sys.prefix)
    try:
        package = json.loads((folder / "pipx_metadata.json").read_text(encoding="utf-8"))["main_package"]
        return package.get("pinned") is True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    try:
        first = tomllib.loads((folder / "uv-receipt.toml").read_text(encoding="utf-8"))["tool"]["requirements"][0]
        specifier = first.get("specifier", "") if isinstance(first, dict) else str(first)[3:]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return False
    return "==" in str(specifier)


def requirement(target: str | None, version: str) -> str:
    """What the worker installs from release ``version``: ``cad==<target>``; with no target the newest of this major,
    never below ``version`` (``bound``)."""
    return f"cad=={target}" if target is not None else bound(version)


def helper_command(target: str | None, *, now: float, version: str, record: str, install: Global, tries: int = 1,
                   asked: bool = False, start: bool = True, wanted: str | None = None,
                   log: str | None = None, python: str = "python",
                   spare: list[int] | None = None) -> list[str]:
    """The worker's entry (``HELPER``): ``python`` (the one of the environment uv runs it from: ``from_cache``; the
    bridge's, the installed environment's own, ``cli.setup.move``), the worker as a module, and its one argument,
    ``told``: ``target``, the release asked for (None: whatever uv gets), what to install (``requirement``), the global
    install ``install``'s environment and its ``cad`` command, who made it, its uv and pipx; ``wanted``, the release
    the attempt is for (``target`` or ``LATEST`` by default), ``tries``, ``asked`` (a typed update), ``start`` (whether
    a server is wanted at the end though none runs now), ``spare`` (on Windows, the processes the switch leaves
    running: ``spared``), ``record`` and ``log``, the files it keeps the attempt and each command in."""
    told = {"record": record, "log": log, "from": version, "at": now, "tries": tries,
            "wanted": wanted or target or LATEST, "asked": asked, "start": start, "target": target,
            "requirement": requirement(target, version), "prefix": str(install.prefix),
            "cad": str(tool_command(install.prefix)), "uv": install.uv, "pipx": install.pipx,
            "installer": install.installer, "spare": spare or []}
    return [python, "-P", "-m", HELPER, json.dumps(told)]


def from_cache(uv: str, wanted: str, *command: str) -> list[str]:
    """``command`` run by uv from an environment of ``wanted`` (a requirement) in its cache, isolated from the uv tool
    ``cad`` installed (which uv would reuse where it holds the release asked for), on the Python of cad's own uv calls
    (``launch.PYTHON``), with the person's own uv settings, as the update installs by them."""
    from cad_server._internal.launch import PYTHON

    return [uv, "tool", "run", "--isolated", "--managed-python", "--python", PYTHON, "--from", wanted, *command]


def build(uv: str, wanted: str, timeout: float = UPGRADE_SECONDS) -> tuple[str | None, int | None, str]:
    """uv's environment of ``wanted`` built in its cache, as the worker runs from it (``from_cache``), and asked its
    release (``cad --version``, which every release answers): ``(that release or None, uv's exit status, all it
    printed)``, the status None where uv could not run or did not end within ``timeout``. Run with no window, in the
    worker's environment (``environ``)."""
    command = from_cache(uv, wanted, "cad", "--version")
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout, env=environ(),
                              creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
    except (OSError, subprocess.SubprocessError) as error:
        return None, None, f"{type(error).__name__}: {error}"
    lines = [line.strip() for line in (done.stdout or "").splitlines() if line.strip()]
    found = re.fullmatch(r"cad (\d+\.\d+\.\d+)", lines[-1]) if done.returncode == 0 and lines else None
    return (found[1] if found else None), done.returncode, done.stdout or ""


def _unbuilt(kept: dict[str, Any], line: list[str], uv: str, wanted: str,
             found: tuple[str | None, int | None, str], seconds: float) -> dict[str, Any]:
    """The attempt ``kept`` ended where uv could not build the worker's environment of ``wanted`` (``build``'s
    ``found``, in ``seconds``): ``failed``, with uv's cause (``auto_update_helper.cause_of``), its first error
    (``auto_update_helper.why``), and
    ``restored``: nothing was touched, and the release before runs on. Written to the record and the log."""
    from cad_server._internal import auto_update_helper as helper

    _named, code, said = found
    log = helper.Log(str(_data() / LOG))
    log.begin(json.loads(line[-1]))
    log.ran(from_cache(uv, wanted, "cad", "--version"), code, seconds, said)
    ended = {**{name: value for name, value in kept.items() if name not in ("phase", "beat")}, "outcome": "failed",
             "ended": time.time(), "restored": True,
             "cause": helper.cause_of(1 if code == 0 else code, said, log),  # 0: uv named no release
             "detail": f"uv could not build {wanted} to update cad, and nothing was changed: "
                       f"{helper.why(said) or 'uv said nothing'}"}
    log.end(ended)
    _keep(_data() / RECORD, ended)
    return ended


def spared(waiting: int | None = None) -> list[int]:
    """On Windows, the processes the switch must leave running though they run from the environment: this one, which
    starts the worker, and ``waiting``, the ``cad update`` that waits on it, each with the processes that started it
    (a ``cad.exe`` and the environment's ``python.exe`` launch the Python under them, and ending either ends it), as
    they are now: the worker cannot ask after this process ends (``auto_update_helper.lineage``). They leave the
    environment before it is installed again whole (``auto_update_helper.reinstall``). Elsewhere none. Never
    raises."""
    if os.name != "nt":
        return []
    try:
        from cad_server._internal import auto_update_helper as helper

        table = helper.Windows().processes()
        return sorted(set().union(*(helper.lineage(pid, table) for pid in (os.getpid(), waiting) if pid)))
    except Exception:  # noqa: BLE001 - the rest is stopped
        return [os.getpid(), *([waiting] if waiting else [])]


def environ() -> dict[str, str]:
    """The worker's environment: this process's, less what would point its Python elsewhere (``_UNSET``). The state
    folder's variables stay: what the worker runs must find the same one."""
    return {name: value for name, value in os.environ.items() if name not in _UNSET}


BEGUN, UNDERWAY, NOT_YET = "begun", "underway", "not yet"  # what starting an update found (``_claim``)


def _claim(*, release: str, wanted: str, version: str, installer: str, automatic: bool) -> tuple[str, dict[str, Any]]:
    """Starting an update, one step across processes, under the state folder's lock (see the module's trigger), in
    this order. Where an attempt is underway, of whatever release (``underway``), ``(UNDERWAY, that attempt)``. Else,
    for an automatic update whose ``wanted`` is not to be tried now (``next_try``, ``given_up``: another process began
    one since the check), ``(NOT_YET, {})``; else the attempt before counted where it was not, as it stands (``event``,
    ``wait`` false: this one takes its place in the record), and this one kept as underway, in its ``switching`` phase,
    its worker's first beat its begin: ``(BEGUN, this attempt)``, and in the tries (``TRIED``) among the day's attempts
    and, automatic, as one more try of ``wanted`` (a typed one spends none: its record's ``tries`` is the try it would
    be). The record is written first: where the tries are not, they count it from the record (``tries``). The time is
    read once the lock is held: read before, a process that waited for the lock would find the attempt the other began
    later than its own now, which ``underway`` takes for a clock set back, and begin a second. The count is sent once
    the lock is let go. ``OSError`` where the record cannot be written."""
    from cad_server._internal.file_lock import state

    folder = _data()
    folder.mkdir(parents=True, exist_ok=True)
    counted: Any = None
    with state(folder):
        now = time.time()
        found = underway(now)
        if found is not None:
            return UNDERWAY, found
        book = tries(now)
        if automatic and (next_try(wanted, book, now) is not None or given_up(wanted, book)):
            return NOT_YET, {}
        before = last()
        if before is not None and not before.get("reported"):
            counted = event(before, wait=False)
        entry = book["tried"].get(wanted) or {}
        count = entry.get("tries", 0) + 1
        kept = {"release": release, "wanted": wanted, "from": version, "at": now, "tries": count, "beat": now,
                "outcome": "underway", "phase": "switching", "installer": installer, "asked": not automatic}
        _keep(folder / RECORD, kept)
        if automatic:
            book["tried"][wanted] = {"tries": count, "first": entry.get("first", now), "at": now}
        book["recent"].append(now)
        try:
            _keep(folder / TRIED, _kept({**book, "seen": now}))
        except OSError:
            pass  # counted from the record by the next that reads them
    if isinstance(counted, dict):
        try:
            from cad_server import analytics

            analytics.update(**counted)
        except Exception:  # noqa: BLE001 - a count never fails the update
            pass
    return BEGUN, kept


def _start(target: str | None, *, automatic: bool, start: bool, wanted: str | None,
           waiting: int | None = None) -> tuple[str, dict[str, Any]]:
    """The update to ``target`` begun (``trigger``'s work), or the attempt underway found: ``(BEGUN, the attempt)``,
    ``(UNDERWAY, the attempt underway)``, or ``("", {})`` where none could begin (``NOT_YET`` too). Once claimed
    (``_claim``), uv builds the environment of the release the record names (``build``): where it cannot, the attempt
    has ended (``_unbuilt``: ``(BEGUN, that record)``); else the worker starts from it, of the very release uv built
    (``from_cache``), told what the record names (``helper_command``), outside any Windows app package
    (``places.outside_package``). ``waiting``: the process that waits on the attempt (``spared``)."""
    from cad.engine.places import detached, outside_package

    found = global_install()
    if found is None or blocked(found) is not None:
        return "", {}
    version = _version()
    bound(version)  # a release cad can bound a build by, or none begins (``ValueError``)
    named = target or LATEST
    said, kept = _claim(release=named, wanted=wanted or named, version=version, installer=found.installer,
                        automatic=automatic)
    if said != BEGUN:
        return (said if said == UNDERWAY else ""), kept
    record = _data() / RECORD
    try:
        line = helper_command(None if kept["release"] == LATEST else kept["release"], now=kept["at"],
                              version=version, record=str(record), install=found, tries=kept["tries"],
                              asked=kept["asked"], start=start, wanted=kept["wanted"],
                              log=str(record.with_name(LOG)), spare=spared(waiting))
        wanted_ = json.loads(line[-1])["requirement"]
        began = time.monotonic()
        built = build(found.uv, wanted_)
        if built[0] is None:
            return BEGUN, _unbuilt(kept, line, found.uv, wanted_, built, time.monotonic() - began)
        outside_package(from_cache(found.uv, f"cad=={built[0]}", *line), stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environ(), cwd=str(record.parent),
                        **detached(breakaway=True))
    except Exception as error:
        # Kept as underway, an attempt whose worker never started would hold every update for the hour: it failed.
        _keep(record, {**kept, "outcome": "failed", "ended": time.time(), "cause": "helper_start",
                       "detail": f"the update's worker could not start: {type(error).__name__}: {error}"})
        raise
    return BEGUN, kept


def trigger(target: str | None, *, automatic: bool = True, start: bool = True, wanted: str | None = None,
            waiting: int | None = None) -> dict[str, Any] | None:
    """The update to ``target`` (None: whatever uv gets) begun, for ``wanted`` (``target`` by default): in one step
    across processes (``_claim``) the attempt before counted where it was not and this one kept (``RECORD``, outcome
    ``underway``), unless one is underway (or, ``automatic``, ``wanted`` was tried since the check); then the worker
    started from the release in uv's cache (``_start``), detached, with no window, in ``environ``; ``automatic``: the
    server's own update, else a typed one (``asked`` in the record); ``start``: a server wanted at the end though none
    runs now; ``waiting``: the process that waits on it (``spared``). The attempt this call began and its worker
    carries out (its record), or None; never raises."""
    try:
        said, kept = _start(target, automatic=automatic, start=start, wanted=wanted, waiting=waiting)
    except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
        return None
    return kept if said == BEGUN and kept.get("outcome") == "underway" else None


def _keep(path: Path, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, json.dumps(record, sort_keys=True).encode("utf-8"))


def restart(*, fetch: bool = False) -> dict[str, Any] | None:
    """As the server starts (the start becomes the update, ``cad_server.engine.daemon.main``; ``after_failed_start``):
    the automatic update begun where it is due (``due``: by the feed as last read, ``fetch`` read first where an hour
    has passed), under ``_BEGIN``. The attempt begun (its record), or None. Never raises."""
    try:
        with _BEGIN:
            found = due(fetch=fetch)
            return trigger(found.target, wanted=found.wanted) if found is not None else None
    except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
        return None


def after_failed_start() -> str | None:
    """``cad server start`` failed: the update begun where it is due, the feed read first where an hour has passed
    (``restart``). What it updates to, in words (the release, or the newest release of this major), or None."""
    found = restart(fetch=True)
    if found is None:
        return None
    numbers = release(_version())
    return found["release"] if found["release"] != LATEST else (
        f"the newest {numbers[0]}.x release" if numbers else "the newest release")


# --- an update asked for: ``cad update`` ------------------------------------------------------------------------------

NOT_THE_TOOL = ("the cad server running is not a global install of cad: run `cad server stop`, then `cad server "
                "start`, then `cad update` again")
CHECK_OFF = ("this cad server does not look for updates (CAD_UPDATE_CHECK=0, CI, or a development build), so it does "
             "not update cad")


def asked(*, pypi: Callable[[], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """``cad update`` judged by the server it asks (``{"op": "update"}``), for the cad this process is: ``{"failed"}``
    in one line where it cannot update cad -- not a global install, the check turned off for this process
    (``updates.checking``), none can begin (``blocked``: why, then what to do, ``advice``), no release cad can bound a
    build by --; ``{"ok": true, "newest"}``, this release, where PyPI names none newer that
    this update takes (of this cad's major, ``choose``); or ``{"ok": true, "updating", "from"}``, the update to
    ``begin``: ``updating`` the release PyPI names, or None where PyPI could not be asked, or named no release of this
    major (the build then runs all the same). Either with ``higher``, the newest release of a higher major, where PyPI
    names one: named, never installed. PyPI is asked now (``updates.pypi``, or ``pypi``). Never raises."""
    try:
        version = _version()
        found = global_install()
        if found is None:
            return {"failed": NOT_THE_TOOL}
        from cad_server import updates

        if not updates.checking():
            return {"failed": CHECK_OFF}
        stuck = blocked(found)
        if stuck is not None:
            return {"failed": f"{in_words(stuck, found.installer)}: {advice(stuck, found.installer)}"}
        if release(version) is None:
            return {"failed": f"cad {version} is no release, so it does not update itself"}
        known = (pypi or updates.pypi)()
        out = {"higher": higher(known, version)} if higher(known, version) else {}
        chosen = choose(known, version)
        if chosen is None and known is not None:
            return {"ok": True, "newest": version, **out}
        return {"ok": True, "updating": chosen.target if chosen else None, "from": version, **out}
    except Exception as error:  # noqa: BLE001 - said in its one line, never a crash of the server's
        return {"failed": f"could not look for an update: {type(error).__name__}: {error}"}


def underway(now: float | None = None) -> dict[str, Any] | None:
    """The attempt underway now, of any release: the last one, not ended and still believed (``believed``: a worker
    that died ends nothing, and stops beating). None where none is."""
    found = last()
    if found is None or found.get("outcome") != "underway":
        return None
    return found if believed(found, time.time() if now is None else now) else None


def believed(found: dict[str, Any], now: float) -> bool:
    """Whether the attempt ``found``, kept as underway, is underway still: its worker beat (``beat``, which it writes
    every minute as it runs, ``auto_update_helper.Beat``) less than ``LOST_SECONDS`` ago, and it began less than
    ``LONGEST_SECONDS`` ago; one a release before the beat kept (no ``beat``), begun less than ``RETRY_SECONDS`` ago.
    Past that it is ``lost``. A clock set back counts as long ago."""
    at, beat = found.get("at"), found.get("beat")
    if not _time(at):
        return False
    if not _time(beat):
        return 0 <= now - at < RETRY_SECONDS
    return 0 <= now - beat < LOST_SECONDS and 0 <= now - at < LONGEST_SECONDS


def switching(now: float | None = None) -> bool:
    """Whether an update is between two servers now: the attempt underway (``underway``) has stopped the server, or
    is about to, and is upgrading cad and starting the next, or repairing it (its ``phase``, ``switching``). A ``cad``
    command that finds no server then waits for the one the update starts (``cad.engine.client.SWITCHING``). Never
    raises."""
    try:
        found = underway(now)
    except Exception:  # noqa: BLE001 - a record that cannot be read is no switch
        return False
    return found is not None and found.get("phase") == "switching"


# How fresh the worker's beat must be for a server's start to stand aside for its switch (``leaving``). It beats every
# minute and as it begins the switch (``auto_update_helper.Beat``), so a worker that died holds a start back no longer.
LEAVING_SECONDS = 150.0
# What the worker sets for every command it runs (``auto_update_helper.main``): the ``at`` of its attempt, so its own
# check of a release, the release being left included where its repair goes back to it, is never held by ``leaving``.
WORKER_ENV = "CAD_UPDATE_WORKER"


def leaving(now: float | None = None) -> bool:
    """Whether cad's own update is switching away from the release this process runs, right now: the attempt underway
    is in its ``switching`` phase, it began from this release (its ``from``), and its worker beat in the last
    ``LEAVING_SECONDS``. The server the update stopped is gone or going, and the next to start is the next release's:
    a server of this release started in between (a ``cad server start`` at that moment) would run from files uv is
    replacing, and hold them on Windows. So it starts none (``cad_server.engine.daemon.main``), and its starter
    launches none meanwhile and waits for the server that answers (``cad.engine.client.LEAVING``): the worker starts
    the next release's, or, where that does not run, the one of whatever release its repair leaves. Never for the
    worker's own commands (``WORKER_ENV``): it checks the release before by starting its server where its repair goes
    back to it. Never raises."""
    try:
        now = time.time() if now is None else now
        found = underway(now)
        if found is None or found.get("phase") != "switching" or found.get("from") != _version():
            return False
        if os.environ.get(WORKER_ENV) == json.dumps(found.get("at")):
            return False
        beat = found.get("beat")
        return _time(beat) and 0 <= now - beat < LEAVING_SECONDS
    except Exception:  # noqa: BLE001 - what cannot be told is no reason for a server not to start
        return False


# Each cause an attempt's record keeps (``auto_update_helper.CAUSES``), or a reader tells (``lost``, ``blocked``), in
# plain words: what ``cad doctor`` and the viewer say.
SAID = {
    "timeout": "uv did not end within 15 minutes",
    "no_program": "uv could not be run",
    "in_use": "a file of cad's was in use by another program",
    "denied": "uv was refused access to a file",
    "disk_full": "the disk is full",
    "network": "uv could not reach the package index",
    "offline": "uv is set to work offline",
    "no_release": "the package index has no release the update may take",
    "python": "the release asks for a newer Python than cad's environment has",
    "platform": "the release has no build for this computer",
    "config_exclude": "a setting of uv's hides newer releases (exclude-newer)",
    "config_index": "a package index named in uv's settings did not give the release",
    "config_tls": "a TLS setting of uv's failed the connection to the package index",
    "cad_running": ("a program run from cad's environment could not be stopped, and a file it holds could not be "
                    "replaced"),
    "broken": "the update left cad unable to run",
    "start_failed": "the new release did not start, so the release before runs again",
    "helper_start": "the update's worker could not start",
    "helper_crash": "the update's worker stopped with an error",
    "lost": "the update's worker ended without saying how",
    "no_installer": "uv cannot be found, so no update can begin",
    "pinned": "cad is pinned to its release in uv's tool receipt (a `uv tool install cad==X`), so it does not update",
    # Said of records an earlier release kept: no update says it now.
    "no_switch": "this cad's own install is damaged, so an update would change nothing",
    "packaged": ("cad's update ran inside a Windows app's package, where it would hide cad's new files from every "
                 "other program"),
    "unknown": "uv's output names no cause cad knows",
}
# The command that installs cad again, by who made the global install (``Global.installer``): what a reinstall line
# names (``advice``), never another.
REINSTALL = {"uv": "uv tool install --force cad", "pipx": "pipx install --force cad"}
UV_DOCS = "https://docs.astral.sh/uv/"
# What to do about each cause (``advice``), by kind: the update tries again by itself; it follows a setting of uv's,
# which the person changes; nothing is to be done; uv is to be installed; cad is to be installed again.
RETRIES = "cad tries again by itself; `cad update` tries now"
_SETTING = "the update follows your uv settings: change {setting}, then `cad update`"
ADVICE = {
    **dict.fromkeys(("network", "timeout", "no_release", "in_use", "unknown", "helper_start", "helper_crash", "lost"),
                    RETRIES),
    "cad_running": "close the programs that run cad (an agent app, a terminal), then `cad update`",
    "denied": "give your user write access to cad's state folder ({state}), uv's tools and uv's cache, then " + RETRIES,
    "disk_full": "free room on the disk, then " + RETRIES,
    "offline": _SETTING.format(setting="uv's offline setting"),
    "config_exclude": _SETTING.format(setting="uv's exclude-newer setting"),
    "config_index": _SETTING.format(setting="the package index named in uv's settings"),
    "config_tls": _SETTING.format(setting="uv's TLS settings"),
    "python": "the release asks for a newer Python than this cad was installed on: install cad again: `{reinstall}`",
    "platform": "nothing to do: this computer cannot take the release, and cad tries each newer one by itself",
    "broken": "install cad again: `{reinstall}`",
    "start_failed": ("nothing to do: cad went back to the release before and takes the next release when it is out; "
                     "`cad update` tries this one again"),
    "no_switch": "install cad again: `{reinstall}`",
    "packaged": "run `cad update` in a terminal (PowerShell opened from the Start menu)",
    **dict.fromkeys(("no_installer", "no_program"), f"install uv ({UV_DOCS}), then `cad update`"),
    "pinned": "to have cad update itself again, install it unpinned: `uv tool install --force cad`",
}
# Where pipx made the global install, what is said in other words than uv's (``in_words``, ``advice``).
PIPX_SAID = {
    "timeout": "pipx did not end within 15 minutes",
    "no_program": "pipx could not be run",
    "denied": "pipx was refused access to a file",
    "network": "pipx could not reach the package index",
    "no_installer": "pipx or uv cannot be found, so no update can begin",
    "pinned": "cad is pinned to its release in pipx (a `pipx pin cad`), so it does not update",
    "unknown": "pipx's output names no cause cad knows",
}
PIPX_ADVICE = {
    "denied": "give your user write access to cad's state folder ({state}) and pipx's environments, then " + RETRIES,
    **dict.fromkeys(("no_installer", "no_program"), f"install pipx and uv ({UV_DOCS}), then `cad update`"),
    "pinned": "to have cad update itself again, unpin it: `pipx unpin cad`",
}


def cause(found: dict[str, Any], now: float | None = None) -> str | None:
    """Why the attempt ``found`` (a record) did not install what it was for: its ``cause``, where it is one of
    ``SAID``; ``lost`` where it is still kept as underway and no longer ``believed``, with none (its worker died
    without a word); else None (it installed, or it is underway)."""
    kept, at = found.get("cause"), found.get("at")
    if kept in SAID:
        return kept
    now = time.time() if now is None else now
    if found.get("outcome") == "underway" and _time(at) and not believed(found, now):
        return "lost"
    return None


def in_words(word: str, installer: str | None = None) -> str:
    """A cause in plain words (``SAID``; ``PIPX_SAID`` where pipx made the global install, ``installer``)."""
    return (PIPX_SAID if installer == "pipx" else {}).get(word) or SAID[word]


def reinstall(installer: str | None = None) -> str:
    """The command that installs cad again for a global install made by ``installer`` (``REINSTALL``; uv's where it
    names neither)."""
    return REINSTALL.get(installer or "uv", REINSTALL["uv"])


def advice(word: str, installer: str | None = None) -> str:
    """What to do about a cause (``ADVICE``), in one line that names one command where there is one to run: the one
    ``cad doctor``, ``cad update``'s failure and the line a cad behind says (``notice``) give. A reinstall names the
    command of who made the global install (``installer``: ``reinstall``; pipx's own words, ``PIPX_ADVICE``).
    ``KeyError`` for a word that is no cause."""
    said = (PIPX_ADVICE if installer == "pipx" else {}).get(word) or ADVICE[word]
    return said.format(reinstall=reinstall(installer), state=_data())


def waiting(known: Any = None, version: str | None = None,
            now: float | None = None) -> tuple[str, dict[str, Any], float | None] | None:
    """The release the version feed as last read (``known``) calls for from release ``version`` (this one's), where it
    has been tried by itself: ``(that release, its tries, when the next may begin by the schedule or None: at the next
    check)``; else None. A release held back (``given_up``: its tries' ``cause`` is ``start_failed``) has no next try
    by itself, whatever the schedule says: its reader says it is held back. ``cad update`` tries it now whatever the
    schedule says."""
    from cad_server import updates

    now = time.time() if now is None else now
    chosen = choose(updates.feed(fetch=False) if known is None else known, version or _version())
    book = tries(now)
    entry = book["tried"].get(chosen.wanted) if chosen is not None else None
    if chosen is None or not entry or entry.get("tries", 0) < 1:
        return None
    return chosen.wanted, entry, next_try(chosen.wanted, book, now)


def begin(target: str | None, *, start: bool = True, waiting: int | None = None) -> dict[str, Any] | None:
    """The update to ``target`` (None: whatever uv gets) that ``cad update`` asked for, begun now, in the one step
    across processes (``_claim``): the attempt underway joined, whatever its release, another process's too; else a
    new attempt. Never a second at once, never the install command after it. ``start``: a server wanted after it
    though none runs (false where ``cad update`` found none running); ``waiting``: the ``cad update`` that waits on
    it, which the switch leaves running (``spared``; this process where it is that one). The attempt's record
    (``release``, ``at``; ended already where uv could not build the release, ``_unbuilt``), or None where it could
    not begin."""
    with _BEGIN:
        try:
            said, found = _start(target, automatic=False, start=start, wanted=None, waiting=waiting)
        except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
            return None
        return found if said in (BEGUN, UNDERWAY) else None


# --- the viewer's update button --------------------------------------------------------------------------------------


def button(*, now: float | None = None) -> dict[str, Any] | None:
    """What the viewer's update button shows (``GET /api/v1/server``'s ``cadUpdate``), from the feed as last read and the
    attempt's record, never asked of the network here: None where cad cannot update itself -- no global install, the
    check turned off for this process (``updates.checking``: ``CAD_UPDATE_CHECK=0``, CI), no release that runs --,
    whatever the switch says (a person can always click); else ``{"version", "latest", "state"}``: ``latest`` the
    newest release of this cad's major the feed names, where it is newer (``choose``; never a higher major's), else
    None; ``state`` ``working`` (an attempt of this release underway and still believed, automatic or asked, with the
    attempt's ``at`` and ``asked``), ``failed`` (the last attempt of this
    release did not install what it was for -- ``lost`` too --, and this cad is still behind), with ``at`` the
    attempt's start, ``cause`` its word, ``said`` it in plain words (``in_words``), the ``installer`` that made the
    global install, ``log`` the worker's log of it (``LOG``, where there is one) and ``dismissed`` where the person put
    it away (``dismiss``), else ``idle``. An attempt underway from another release is the one that installed this one:
    ``idle``; and so is a server older than its own environment (``stale``): the release is there already, and the
    click's update only restarts the server on it. A click updates whenever ``latest`` is named. Never raises."""
    try:
        version = _version()
        install = global_install()
        if install is None or release(version) is None:
            return None
        from cad_server import updates

        if not updates.checking():
            return None
        chosen = choose(updates.feed(fetch=False), version)
        latest = chosen.target if chosen is not None else None
        out: dict[str, Any] = {"version": version, "latest": latest, "state": "idle"}
        now = time.time() if now is None else now
        found = last()
        mine = found is not None and found.get("from") == version
        word = cause(found, now) if mine else None
        attempt = {"at": found["at"], "asked": found.get("asked") is True} if mine else {}
        if mine and word is None and underway(now) is not None:
            return {**out, **attempt, "state": "working"}
        if word is not None and latest is not None and not stale(chosen.wanted):
            log = _data() / LOG
            return {**out, **attempt, "state": "failed", "cause": word, "said": in_words(word, found.get("installer")),
                    **({"installer": found["installer"]} if found.get("installer") in INSTALLERS else {}),
                    **({"log": str(log)} if log.is_file() else {}),
                    **({"dismissed": True} if found.get("dismissed") is True else {})}
        return out
    except Exception:  # noqa: BLE001 - a button that cannot say shows nothing
        return None


def dismiss(at: float) -> bool:
    """The failure of the attempt begun at ``at`` put away by the person (the viewer's alert of it closed): marked
    ``dismissed`` in the record, under the state folder's lock, where the record is still that attempt's and it has
    ended; every page, here or after a reload, keeps it put away (``button``'s ``dismissed``) until another attempt
    takes the record's place. Whether it was. Never raises."""
    try:
        from cad_server._internal.file_lock import state

        folder = _data()
        if not (folder / RECORD).is_file():
            return False
        with state(folder):
            found = last()
            if found is None or found.get("at") != at or (found.get("outcome") == "underway" and cause(found) is None):
                return False
            _keep(folder / RECORD, {**found, "dismissed": True})
        return True
    except Exception:  # noqa: BLE001 - a failure not put away is shown again
        return False


# --- a cad that has stayed behind: one line on stderr ----------------------------------------------------------------

NOTICE = "auto-update-notice.json"  # in the state folder: the release this cad is behind, since when, when it was said
BEHIND_SECONDS = 3 * DAY  # how long a cad is behind before a command says so


def notice(now: float | None = None) -> str | None:
    """The one line a ``cad`` command says on stderr, after its own output, where this cad has stayed behind: the
    command line's counterpart of the viewer's update button, for computers that never open the viewer. Only for a
    global install with automatic updates on (a person who turned them off chose the release they have, and an agent
    that read "run `cad update`" might run it against that choice) and the check not turned off for this process
    (``updates.checking``); never where this cad is current by the version feed as last read (``choose``, never the
    network), where an update is underway (``underway``) or the environment runs a newer release already (``stale``).
    Kept in ``NOTICE`` (written whole): ``from``, this release, ``behind``, the release of its major it is behind,
    ``since``, when a cad of this release was first seen behind, whatever newer release came out since, and ``said``.
    The first time only the time is noted; from ``BEHIND_SECONDS`` after it, and not within a ``DAY`` of the last time
    (a clock set back counts as long ago), the line, noted as said first: a file it cannot write says nothing, so it
    can never be said on every command. The line names both releases, why in plain words (``in_words``), and what
    to do (``advice``, the line ``cad doctor`` and ``cad update`` give for that cause): where none can begin
    (``blocked``), and where this release's last attempt did not install (``cause``); else, no attempt on record,
    ``cad update``. None otherwise. Never raises."""
    try:
        now = time.time() if now is None else now
        lag = _lag(now)
        if lag is None:
            return None
        version, target, kept = lag
        path = _data() / NOTICE
        if target is None:
            if kept:
                path.unlink()  # current: a release behind a later one starts afresh
            return None
        since = kept.get("since")
        if kept.get("from") != version or not _time(since) or since > now:
            _keep(path, {"from": version, "behind": target, "since": now})
            return None
        said = kept.get("said")
        if now - since < BEHIND_SECONDS or (_time(said) and 0 <= now - said < DAY):
            return None
        line = behind_line(version, target, now)
        _keep(path, {**kept, "behind": target, "said": now})
        return line
    except Exception:  # noqa: BLE001 - the line never fails the command it follows, and one not kept is not said
        return None


def stayed_behind(now: float | None = None) -> str | None:
    """The release this cad has been behind for ``BEHIND_SECONDS`` by ``notice``'s rule and record, read and never
    written (``cad doctor``); else None. Never raises."""
    try:
        now = time.time() if now is None else now
        lag = _lag(now)
        if lag is None or lag[1] is None:
            return None
        version, target, kept = lag
        since = kept.get("since")
        return target if kept.get("from") == version and _time(since) and BEHIND_SECONDS <= now - since else None
    except Exception:  # noqa: BLE001 - a report line, never a reason for it to fail
        return None


def _lag(now: float) -> tuple[str, str | None, dict[str, Any]] | None:
    """What ``notice`` judges by: ``(this release, the release of its major the feed as last read calls for or None
    where it is current, what ``NOTICE`` keeps)``; None where nothing is said (see ``notice``)."""
    if uv_tool() is None and pipx_tool() is None or not switches()["on"]:
        return None
    from cad_server import updates

    if not updates.checking():
        return None
    version = _version()
    chosen = choose(updates.feed(fetch=False), version)
    if chosen is not None and chosen.target is not None and (underway(now) is not None or stale(chosen.wanted)):
        return None
    try:
        kept = json.loads((_data() / NOTICE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    return version, chosen.target if chosen is not None else None, kept if isinstance(kept, dict) else {}


def behind_line(version: str, target: str, now: float) -> str:
    """``notice``'s line for this cad, release ``version``, behind ``target``."""
    found = global_install()
    installer = found.installer if found is not None else None
    stuck = blocked(found) if found is not None else None
    if stuck is not None:
        return (f"cad: this cad is {version} and cannot update itself to {target} ({in_words(stuck, installer)}): "
                f"{advice(stuck, installer)}")
    record = last()
    word = cause(record, now) if record is not None and record.get("from") == version else None
    if word is not None:
        return (f"cad: this cad is {version} and has not been able to update itself to {target} "
                f"({in_words(word, installer)}): "
                f"{advice(word, installer)}")
    return f"cad: cad {target} is out and this is {version}: `cad update` updates it"



# --- an attempt counted -----------------------------------------------------------------------------------------------

# The worker's outcomes that end an attempt (an earlier release's ``ready`` is none).
ENDED = frozenset({"installed", "current", "failed"})
ALREADY = re.compile(r"cad \S+ is installed")  # the worker's detail where the environment ran the release already
WAIT = object()  # ``event``: not yet, the install command's run for the new cad still underway


def event(found: dict[str, Any], *, wait: bool = True) -> dict[str, Any] | object | None:
    """The ``update`` event an ended attempt (``found``, the record) is counted as (``analytics.update``'s arguments),
    ``WAIT`` while the install command's run for the cad it installed is underway (``wait`` false: the event as it
    stands, that run ``underway``), or None for a record that is none of an ended attempt. That
    run is one begun since the attempt began (``plugin_catch_up.last``, ``since``): a run begun before it is another's.
    An attempt kept as
    underway and no longer ``believed`` never ends: it is counted ``lost``. Every outcome but ``installed`` says why
    (``cause``, ``_sent``)."""
    outcome = found.get("outcome")
    if outcome == "underway":
        if not _time(found.get("at")) or believed(found, time.time()):
            return None  # still underway (``underway``)
        outcome = "lost"
    elif outcome not in ENDED:
        return None
    reason = None
    if outcome == "failed":
        detail = found.get("detail")
        # ``older``: a release it may not end on (the worker's "which it may not end on"); any other failure is the
        # build's, the release's run or its server's start.
        reason = "older" if isinstance(detail, str) and detail.endswith("which it may not end on") else "upgrade"
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
    if installer not in INSTALLERS:  # a record kept before it named one: this cad's
        here = global_install()
        installer = here.installer if here is not None else None
    tries = found.get("tries", 1)
    return {"earlier": found.get("from"), "outcome": outcome, "reason": reason,
            "tries": tries if type(tries) is int else 1, "installer": installer, "asked": found.get("asked") is True,
            "plugin": plugin, "cause": None if outcome == "installed" else _sent(found, outcome)}


def _sent(found: dict[str, Any], outcome: str) -> str:
    """Why the attempt ``found``, counted as ``outcome``, did not install a newer cad, as its event says it
    (``analytics.UPDATE_CAUSES``): a ``lost`` one's worker stopped with an error (``helper_crash``) or without a word
    (``lost``); else the record's cause (``cause``), ``already`` for a ``current`` one whose environment held the
    release already (its worker's detail), and ``none`` where the record names none."""
    if outcome == "lost":
        return "helper_crash" if found.get("cause") == "helper_crash" else "lost"
    word, detail = cause(found), found.get("detail")
    if word is None and outcome == "current" and isinstance(detail, str) and ALREADY.fullmatch(detail):
        return "already"
    return word or "none"


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
