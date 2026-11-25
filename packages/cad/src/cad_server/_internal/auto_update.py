"""cad's own update: what a global install is, the switches, the check, and its trigger.

**The rule.** cad installs by itself any newer release with the same major version number as its own; a release of a
higher major never arrives by itself: a person asks for it (``cad update --major``). Every update is forward only. The
bound is worked out from the release that runs each time (``bound``: ``cad>=<this release>,<<its major + 1>``), never a
fixed number, so it holds on a computer that has not updated for months.

**How a release arrives.** No file of an installed cad is ever changed. The update builds the newer release whole in a
folder of its own, in the state folder (the store, ``store``), with the uv cad carries (``carried_uv``), runs it once
there, and then switches to it by writing one small file whole, the pointer, which every process of the environment
reads as its interpreter starts (``_cad_release``). A process keeps the release it started with until it ends, so a
``cad`` that runs while the update does is never left half replaced. That work is the worker's
(``auto_update_helper``); this module decides when it runs and keeps its record.

**A global install** (``global_install``) is a cad whose environment uv's ``uv tool install cad`` made (uv's receipt
there names ``cad``) or pipx's ``pipx install cad`` (pipx's ``venvs/cad``, its metadata naming ``cad``). Only a global
install updates itself, and the same way whoever made it: the installer is named for telemetry, ``cad doctor`` and
the command that installs cad again (``reinstall``) alone, and its receipt is never rewritten. ``installed_tool`` finds the global install from anywhere (a cad run from
uv's cache): uv's tool first, then pipx's.

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
already runs ``wanted`` or newer while this older server runs (``stale``): ``cad server start`` replaces the server.
Nor where ``wanted`` is the release that is ready already (``ready``): only its switch is left. Where an update is due
and none can begin (``blocked``: no uv, or an environment that does not read the pointer), the check counts it once
for that release (``BLOCKED``). The check is asked as the server tends itself (``tend``, with nothing in flight and
no command run for ``IDLE_SECONDS``) and by ``cad server start`` when the start failed (``after_failed_start``): a
release whose server cannot start still updates.

**Ready, then the switch.** The server's own update only gets the release ready (``"switch": false`` in its record):
built and run once in the store, it ends ``ready`` with nothing pointing at it, so no server restarts under a viewer
page someone is looking at (a page's requests are no commands). The viewer's button then offers the restart
(``button``), which is ``cad update``'s; else the switch begins by itself where automatic updates are on, the check is
on and the feed as last read calls for that release still (``restart``): as the server starts (the start becomes the
switch: ``cad_server.engine.daemon.main``, never for ``--foreground`` or ``--port``), once nothing at all has been asked
of the server for ``ALONE_SECONDS``, or, once the release has been ready a ``DAY``, at the first ``IDLE_SECONDS`` with
no command. That sitting resumes the attempt (``_claim``): no try spent, held by no schedule. The release that is ready
is the one ``ready`` names, and the store's tidying keeps it (``kept``).

**The trigger** (``trigger``) begins the update in one step across processes (``_claim``, under the state folder's
lock): where an attempt is underway none begins (an automatic update) or it is joined (``cad update``, which makes
one that only got its release ready a whole update); where a release is ready and asked for, it is resumed at its
switch; else the attempt before counted where it was not, and this one kept as underway, its ``phase``
``building``. Then the worker starts, detached, by this environment's own interpreter (``helper_command``), told the
release the record names. The attempt is kept in the state folder (``RECORD``: ``release``, ``wanted``, ``from``,
``at``, ``tries``, ``installer``, ``asked`` -- a person's own update --, ``major``, ``switch`` -- false where it gets
its release ready alone --, ``phase``, ``beat``, then the worker's ``ended``, ``outcome`` (``ready`` too),
``detail``, ``restored``, ``started`` and, where it did not install what it was for, ``cause``: one word of
``auto_update_helper.CAUSES``, said in plain words by ``SAID``, and what to do about it by ``advice``, the one line
``cad doctor``, ``cad update`` and ``notice`` give; ``dismissed`` once the person put its failure away), which ``cad
doctor`` and the viewer's update button (``button``) show, with the worker's log (``LOG``; the attempt before's
``LOG_BEFORE``; never sent). Every change of it that another process may make at the same moment holds the state
folder's lock: the claim, the worker's beat and its decision to end ``ready``, ``dismiss``, ``report``. While the
worker switches releases (``switching``) a ``cad`` command that finds no server waits for the next
(``cad.engine.client.SWITCHING``), and a server of the release being left starts none in its place (``leaving``). A
worker silent for ``LOST_SECONDS`` is taken for lost; should it wake, it writes no outcome over another attempt's
record.

**Counted** (``report``), once per attempt that ended, by the server that runs after it (and by a trigger, before a new
attempt takes the record's place; a ``ready`` record is no end, and its switch is the sitting counted): one ``update``
event (``analytics.update``): the release before, how it ended (``installed``, ``current``, ``failed``, ``restored``
where the release before runs again, or ``lost``), which step failed (``upgrade``: the release could not be built,
did not run, or its server did not start; ``older``: it built a release it may not end on; ``put_back``: and the
release before could not be put back either), why (``cause``; ``already`` where the environment ran the release
already), the tries, the installer, whether it was typed, and for a newer cad how the install command's run for it
went (``plugin_catch_up.last``).

**Asked for** (``cad update``, and the viewer's update button: the server judges it, ``asked``, and begins it at once,
``begin``; with no server running, ``cad update`` itself, whose worker then starts none): PyPI asked now
(``updates.pypi``) for the newest release of this cad's major, chosen as the feed's answer is; where a release of a
higher major is out, the answer names it (``higher``, ``MAJOR_LINE``). ``cad update --major``: PyPI's newest of all.
Neither the switch nor the schedule applies, and no automatic try is spent; where PyPI cannot be reached, the build
runs all the same, bounded -- or, where a release is ready, its switch. A person's update never ends ``ready``.

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
IDLE_SECONDS = 60.0
HOUR, DAY = 3600.0, 86400.0
# How long nothing at all may be asked of the server -- no command, no agent's tool call, no request of a viewer page --
# before it restarts by itself onto a release that is ready (``restart``).
ALONE_SECONDS = HOUR
WAIT_HOURS = 24  # the longest wait between two automatic tries of one release: 1, 2, 4, 8, 16, then 24 hours
DAILY = 4  # the most attempts begun in a day, of every release, that an automatic one may begin beside
KEPT = 8  # how many releases' tries are kept: the newest tried
LOST_SECONDS = 20 * 60.0  # an attempt whose worker has not beaten for this long is lost (``believed``)
LONGEST_SECONDS = 6 * HOUR  # nor is one believed underway this long after it began, whatever its beat says
RETRY_SECONDS = HOUR  # how long an attempt a release before the beat kept is believed underway
# What the record names as the release of a typed update begun with no answer from PyPI: whatever the build gets.
LATEST = "latest"
# The steps of an attempt underway, as its record's ``phase`` names them: the release built beside the one that runs,
# then the switch to it (the server drained, the pointer written, the next server started). A switch that fails ends
# in a third, ``restoring``, which no reader shows: the way back, while the release before starts again.
PHASES = ("building", "switching")
# Who makes a global install of cad (``global_install``), named in the record and its count.
INSTALLERS = ("uv", "pipx")
# The worker, run as a module by this environment's interpreter (``helper_command``).
HELPER = "cad_server._internal.auto_update_helper"
# One update begun at a time in a process: the check and the trigger together (``_begin_due``, ``restart``, ``begin``).
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
MAJOR_LINE = ("cad {release}, a new major version, is out and does not install itself: `cad update --major` installs it "
              f"(what changes: {MIGRATIONS})")


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


# What a person is told where uv's own record keeps this install below the release it runs (``outgrown``).
OUTGROWN = ("uv's own record keeps this install below cad {major}, so a `uv tool upgrade` would put an older cad over cad "
            "{release}: `uv tool install --force cad` installs cad afresh and clears that")


def kept_below(prefix: str | None = None) -> int | None:
    """The major version uv's own record of this install keeps cad below: the ``<N`` of the requirement its receipt
    holds (``cad>=X,<N``, which the update of 0.11.12 to 0.11.17 wrote there as it ran uv's upgrade; a person's own
    ``uv tool install "cad<N"`` writes one too). None where it holds no such bound, or uv did not make this install.
    cad's update never rewrites the receipt (``outgrown``)."""
    import tomllib

    try:
        receipt = tomllib.loads((Path(prefix or sys.prefix) / "uv-receipt.toml").read_text(encoding="utf-8"))
        first = receipt["tool"]["requirements"][0]
        said = str(first.get("specifier") or "") if isinstance(first, dict) else str(first)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    bound = re.search(r"(?<![<>=!~])<\s*(\d+)(?:\.0)*\s*(?:,|;|$)", said)
    return int(bound[1]) if bound else None


def outgrown(prefix: str | None = None) -> str | None:
    """The one line (``OUTGROWN``) for an install that runs a release uv's own record does not allow: ``cad update
    --major`` took cad to a major the receipt keeps it below (``kept_below``), and uv's own ``uv tool upgrade``, which
    goes by the receipt, would install the newest release below that major over it -- and a cad installed again runs
    what was installed. None where the release that runs (``store.active``) is inside the bound, or there is none.
    Never raises."""
    try:
        from cad_server._internal import store

        bound, running = kept_below(prefix), release(store.active(prefix))
        if bound is None or running is None or running[0] < bound:
            return None
        return OUTGROWN.format(major=bound, release=".".join(map(str, running)))
    except Exception:  # noqa: BLE001 - a line of advice, never a reason for what says it to fail
        return None


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
    """Whether ``found`` is a file, and not inside this cad's environment (``prefix``): the uv inside it is the one cad
    carries (``carried_uv``), asked for apart."""
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
    install command looks). Never the one inside this cad's environment (``prefix``: ``_outside``)."""
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


def carried_uv() -> str | None:
    """The uv cad's own ``uv`` dependency carries, of the release this process runs: beside the ``uv`` package it
    imports (a stored release's ``bin``, where ``uv pip install --target`` puts scripts on every platform), else where
    ``uv.find_uv_bin`` looks (the environment's own, which may be a release older). None where neither is."""
    try:
        import uv

        beside = Path(uv.__file__).resolve().parent.parent / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        found = str(beside) if beside.is_file() else uv.find_uv_bin()
    except (ImportError, FileNotFoundError, OSError, TypeError):
        return None
    return found if found and os.path.isfile(found) else None


@dataclass(frozen=True)
class Global:
    """A global install of cad: its environment, who made it (``INSTALLERS``), and the uv the update builds with, the
    one cad carries else the person's (``find_uv``; None where neither is: then it cannot update)."""

    installer: str
    prefix: Path
    uv: str | None

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
    return Global(installer, folder, carried_uv() or find_uv(prefix=str(folder)))


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


def ready() -> dict[str, Any] | None:
    """The release that is ready, as the last attempt's record keeps it: the record, where its outcome is ``ready``
    (an attempt that only got its release ready: built and run once in the store, nothing pointing at it), it began
    from the release this process runs (its ``from``: another release's is not this one's to switch from), and the
    release it names is still a stored release (``store.marker``: a folder gone, or no longer whole, is ready no
    more); else None. Never raises."""
    try:
        found = last()
        if found is None or found.get("outcome") != "ready" or found.get("from") != _version() \
                or release(found.get("release")) is None:
            return None
        from cad_server._internal import store

        return found if store.marker(store.folder(found["release"])) is not None else None
    except Exception:  # noqa: BLE001 - what cannot be told is no release ready
        return None


def kept() -> list[Path]:
    """What a tidying of the store keeps whatever points at it (``store.clean``'s ``keep``): the folder of the release
    that is ready (``ready``), or none."""
    found = ready()
    if found is None:
        return []
    from cad_server._internal import store

    return [store.folder(found["release"])]


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
    once for its release (``_blocked``). None too where the release it would choose is the one that is ready already
    (``ready``, by ``wanted``): what is left of that one is its switch (``restart``); a newer one is due as any.
    ``fetch``: the feed read first where an hour has passed (``updates.feed``; never for an update that cannot begin);
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
        held = ready()
        if held is not None and _wanted(held) == chosen.wanted:
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
    """Whether this server is older than what its own environment runs now (``store.active``), which is ``wanted`` or
    newer: another update, or one by hand, got there after it started. No update is due for it and no try is spent:
    the server wants restarting, which ``cad server start`` does, as ``cad doctor`` says."""
    from cad_server._internal import store

    held, mine, want = release(store.active()), release(_version()), release(wanted)
    return held is not None and mine is not None and held > mine and (want is None or held >= want)


def blocked(found: Global) -> str | None:
    """Why no update can begin for the global install ``found``, as a cause (``SAID``): ``no_switch``, its
    environment does not read cad's pointer as Python starts, or its own install of cad is damaged
    (``store.switches``); ``no_installer``, no uv is found. None where one can."""
    from cad_server._internal import store

    if not store.switches():
        return "no_switch"
    return "no_installer" if found.uv is None else None


def requirement(target: str | None, version: str, *, major: bool = False) -> str:
    """What the worker builds from release ``version``: ``cad==<target>``; with no target the newest of this major
    (``bound``), or, for ``major``, of all, never below ``version``."""
    if target is not None:
        return f"cad=={target}"
    return f"cad>={version}" if major else bound(version)


def helper_command(target: str | None, *, now: float, version: str, record: str, install: Global, tries: int = 1,
                   asked: bool = False, start: bool = True, major: bool = False, wanted: str | None = None,
                   log: str | None = None, python: str | None = None) -> list[str]:
    """The worker's command line: this environment's interpreter (``python``: ``sys.executable``, so it runs the
    release that is current, by the pointer, as every process of the environment does), the worker as a module, and its
    one argument: ``target``, the release asked for (None: whatever the build gets), what to build (``requirement``),
    the global install ``install``'s ``cad`` command, the uv it builds with and who made it; ``wanted``, the release
    the attempt is for (``target`` or ``LATEST`` by default), ``tries``, ``asked`` (a typed update), ``major``
    (``cad update --major``), ``start`` (whether a server is wanted at the end though none runs now), ``record`` and
    ``log``, the files it keeps the attempt and each command in."""
    told = {"record": record, "log": log, "from": version, "at": now, "tries": tries,
            "wanted": wanted or target or LATEST, "asked": asked, "major": major, "start": start, "target": target,
            "requirement": requirement(target, version, major=major), "cad": str(tool_command(install.prefix)),
            "uv": install.uv, "installer": install.installer}
    return [python or sys.executable, "-P", "-m", HELPER, json.dumps(told)]


def environ() -> dict[str, str]:
    """The worker's environment: this process's, less what would point its Python elsewhere (``_UNSET``). The state
    folder's variables stay: the pointer is kept there, and what the worker runs must read the same one."""
    return {name: value for name, value in os.environ.items() if name not in _UNSET}


BEGUN, UNDERWAY, NOT_YET = "begun", "underway", "not yet"  # what starting an update found (``_claim``)


def _claim(*, release: str, wanted: str, version: str, installer: str, automatic: bool, major: bool,
           switch: bool = True) -> tuple[str, dict[str, Any]]:
    """Starting an update, one step across processes, under the state folder's lock (see the module's trigger), in
    this order. Where an attempt is underway, of whatever release (``underway``), ``(UNDERWAY, that attempt)`` -- and
    where the caller is a person (not ``automatic``) and that attempt only gets its release ready (``"switch":
    false``), the record made a whole update of theirs first, ``"switch": true, "asked": true``, and that attempt
    returned so: a person who asks during the silent build gets the restart too. Where a release is ready (``ready``)
    and it is the one asked for, or none was named (``LATEST``: PyPI could not be asked), that attempt resumed:
    ``(BEGUN, a new record)`` for the same release and ``wanted``, underway in its ``switching`` phase, its ``at``
    and first beat now, its ``tries`` the ready record's (no try spent: it did not fail), held by neither the
    schedule nor ``given_up``, among none of the day's attempts, counted as no event (a ready record is none); in the
    tries ``seen`` is its ``at``, and, automatic, its release's last try is this one (``at``, the count unchanged), so
    a switch that fails is that try's cause. A caller that only gets a release ready (``switch`` false) resumes
    nothing: for the release that is ready already, ``(NOT_YET, {})``. Else, for an automatic update whose ``wanted``
    is not to be tried now (``next_try``, ``given_up``: another process began one since the check), ``(NOT_YET,
    {})``; else the attempt before counted where it was not, as it stands (``event``, ``wait`` false: this one takes
    its place in the record), and this one kept as underway, in its ``building`` phase, its worker's first beat its
    begin, ``"switch": false`` where ``switch`` is: ``(BEGUN, this attempt)``, and in the tries (``TRIED``) among the
    day's attempts and, automatic, as one more try of ``wanted`` (a typed one spends none: its record's ``tries`` is
    the try it would be). The record is written first: where the tries are not, they count it from the record
    (``tries``). The time is read once the lock is held: read before, a process that waited for the lock would find
    the attempt the other began later than its own now, which ``underway`` takes for a clock set back, and begin a
    second. The count is sent once the lock is let go. ``OSError`` where the record cannot be written."""
    from cad_server._internal.file_lock import state

    folder = _data()
    folder.mkdir(parents=True, exist_ok=True)
    counted: Any = None
    with state(folder):
        now = time.time()
        found = underway(now)
        if found is not None:
            if not automatic and found.get("switch") is False:
                found = {**found, "switch": True, "asked": True}
                _keep(folder / RECORD, found)
            return UNDERWAY, found
        book = tries(now)
        held = ready()
        if held is not None and not switch and _wanted(held) == wanted:
            return NOT_YET, {}
        if held is not None and switch and release in (LATEST, held["release"]):
            kept = {"release": held["release"], "wanted": _wanted(held), "from": version, "at": now,
                    "tries": _count(held.get("tries")) or 1, "beat": now, "outcome": "underway", "phase": "switching",
                    "installer": installer, "asked": not automatic, "major": major}
            _keep(folder / RECORD, kept)
            entry = book["tried"].get(kept["wanted"])
            if automatic and entry is not None:
                book["tried"][kept["wanted"]] = {**entry, "at": now}
            try:
                _keep(folder / TRIED, _kept({**book, "seen": now}))
            except OSError:
                pass  # read from the record by the next that reads them
            return BEGUN, kept
        if automatic and (next_try(wanted, book, now) is not None or given_up(wanted, book)):
            return NOT_YET, {}
        before = last()
        if before is not None and not before.get("reported"):
            counted = event(before, wait=False)
        entry = book["tried"].get(wanted) or {}
        count = entry.get("tries", 0) + 1
        kept = {"release": release, "wanted": wanted, "from": version, "at": now, "tries": count, "beat": now,
                "outcome": "underway", "phase": "building", "installer": installer, "asked": not automatic,
                "major": major, **({} if switch else {"switch": False})}
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


def _start(target: str | None, *, automatic: bool, start: bool, major: bool, wanted: str | None,
           switch: bool = True) -> tuple[str, dict[str, Any]]:
    """The update to ``target`` begun (``trigger``'s work), or the attempt underway found: ``(BEGUN, the attempt)``,
    ``(UNDERWAY, the attempt underway)``, or ``("", {})`` where none could begin (``NOT_YET`` too). The worker is
    told what the claimed record names (``_claim``), not what was asked: a resume asked for with no release named
    uses exactly the release that is ready."""
    from cad.engine.places import detached

    found = global_install()
    if found is None or blocked(found) is not None:
        return "", {}
    version = _version()
    bound(version)  # a release cad can bound a build by, or none begins (``ValueError``)
    named = target or LATEST
    said, kept = _claim(release=named, wanted=wanted or named, version=version, installer=found.installer,
                        automatic=automatic, major=major, switch=switch)
    if said != BEGUN:
        return (said if said == UNDERWAY else ""), kept
    record = _data() / RECORD
    try:
        command = helper_command(None if kept["release"] == LATEST else kept["release"], now=kept["at"],
                                 version=version, record=str(record), install=found, tries=kept["tries"],
                                 asked=kept["asked"], start=start, major=major, wanted=kept["wanted"],
                                 log=str(record.with_name(LOG)))
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=environ(), cwd=str(record.parent), **detached())
    except Exception as error:
        # Kept as underway, an attempt whose worker never started would hold every update for the hour: it failed.
        _keep(record, {**kept, "outcome": "failed", "ended": time.time(), "cause": "helper_start",
                       "detail": f"the update's worker could not start: {type(error).__name__}: {error}"})
        raise
    return BEGUN, kept


def trigger(target: str | None, *, automatic: bool = True, start: bool = True, major: bool = False,
            wanted: str | None = None, switch: bool = True) -> dict[str, Any] | None:
    """The update to ``target`` (None: whatever the build gets) begun, for ``wanted`` (``target`` by default): in one
    step across processes (``_claim``) the attempt before counted where it was not and this one kept (``RECORD``,
    outcome ``underway``), or the release that is ready resumed, unless one is underway (or, ``automatic``,
    ``wanted`` was tried since the check); then the worker started (``helper_command``), detached, with no window, in
    ``environ``; ``automatic``: the server's own update, else a typed one (``asked`` in the record); ``major``: ``cad
    update --major``; ``start``: a server wanted at the end though none runs now; ``switch`` false: the release got
    ready alone, nothing switched (``"switch": false`` in the record). The attempt this call began (its record), or
    None; never raises."""
    try:
        said, kept = _start(target, automatic=automatic, start=start, major=major, wanted=wanted, switch=switch)
    except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
        return None
    return kept if said == BEGUN else None


def _keep(path: Path, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, json.dumps(record, sort_keys=True).encode("utf-8"))


def _begin_due(*, fetch: bool = False, switch: bool = True) -> dict[str, Any] | None:
    """The automatic update begun where it is due (``due``, ``trigger``; ``switch`` false: its release got ready
    alone), under ``_BEGIN``: the attempt begun, or None."""
    with _BEGIN:
        found = due(fetch=fetch)
        return trigger(found.target, wanted=found.wanted, switch=switch) if found is not None else None


def tend(*, working: bool, ran: bool, quiet_for: float, idle_for: float) -> dict[str, Any] | None:
    """As the server tends itself, in order: nothing where anything is in flight (``working``); else, where an update
    is due and nothing has run since the server started (``ran``) or no command for ``IDLE_SECONDS`` (``quiet_for``),
    its release got ready, begun as an attempt that switches nothing (``"switch": false``: no server restarts under
    a page someone looks at); else, where a release is ready and the moment is right (``restart``, by ``quiet_for``
    and ``idle_for``, the seconds since anything at all was asked of the server), the switch to it begun. The attempt
    begun (its record: ``"switch": false`` for the first, phase ``switching`` for the second), or None."""
    if working:
        return None
    if not ran or quiet_for >= IDLE_SECONDS:
        found = _begin_due(switch=False)
        if found is not None:
            return found
    return restart(quiet_for=quiet_for, idle_for=idle_for)


def restart(*, quiet_for: float, idle_for: float, starting: bool = False,
            now: float | None = None) -> dict[str, Any] | None:
    """The switch to the release that is ready begun by itself, where the moment is right: the attempt resumed (its
    record, ``_claim``), or None. All of: a release is ready (``ready``); this cad is a global install; automatic
    updates are on (``switches``) and the check is not turned off for this process (``updates.checking``); the
    version feed as last read calls for exactly that release still (``choose``, by ``wanted``: one taken back from
    the feed since, or a feed that cannot be read, is never switched to by itself, nor with a newer one out, whose
    own attempt takes the record's place); and one of: the server is starting (``starting``: the start itself
    becomes the switch, ``cad_server.engine.daemon.main``), nothing at all has been asked of it for
    ``ALONE_SECONDS`` (``idle_for``: a visible viewer page asks something every few seconds, a hidden one nothing),
    or the release has been ready for a ``DAY`` (its ``ended``; a clock set back counts as not yet) and no command
    has run for ``IDLE_SECONDS`` (``quiet_for``), so a page always shown or a computer always busy is never left
    behind for good. With automatic updates off a ready release waits for a person (``cad update``, the viewer's
    button). Never raises."""
    try:
        with _BEGIN:
            held = ready()
            if held is None or global_install() is None or not switches()["on"] or not called_for(held):
                return None
            now = time.time() if now is None else now
            ended = held.get("ended")
            if not (starting or idle_for >= ALONE_SECONDS
                    or _time(ended) and now - ended >= DAY and quiet_for >= IDLE_SECONDS):
                return None
            return trigger(held["release"], wanted=_wanted(held))
    except Exception:  # noqa: BLE001 - a switch that cannot begin leaves cad as it is
        return None


def called_for(held: dict[str, Any]) -> bool:
    """Whether the version feed as last read still calls for the release that is ready (``held``, its record): the
    update it calls for (``choose``) is for that release (``wanted``), and the check is on (``updates.checking``). The
    one rule a ready release is judged by: whether cad restarts on it by itself (``restart``), whether the viewer's
    button offers the restart (``button``), and what ``cad doctor`` says of it. Never asks the network."""
    from cad_server import updates

    if not updates.checking():
        return False
    chosen = choose(updates.feed(fetch=False), _version())
    return chosen is not None and chosen.wanted == _wanted(held)


def after_failed_start() -> str | None:
    """``cad server start`` failed: the update begun where it is due, the feed read first where an hour has passed,
    else the switch to a release that is ready, as a start's (``restart``). What it updates to, in words (the release,
    or the newest release of this major), or None."""
    found = _begin_due(fetch=True) or restart(quiet_for=0.0, idle_for=0.0, starting=True)
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


def asked(*, major: bool = False, pypi: Callable[[], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """``cad update`` judged by the server it asks (``{"op": "update"}``, ``"major": true`` for ``--major``), for the
    cad this process is: ``{"failed"}`` in one line where it cannot update cad -- not a global install, the check
    turned off for this process (``updates.checking``), none can begin (``blocked``: why, then what to do, ``advice``),
    no release cad can bound a build by --; ``{"ok": true, "newest"}``, this release, where PyPI names none newer that
    this update takes (of this cad's major, ``choose``; of all, ``major``); or ``{"ok": true, "updating", "from"}``, the
    update to ``begin``: ``updating`` the release PyPI names, or None where PyPI could not be asked, or named no release of this major (the
    build then runs all the same); ``"major": true`` with ``major``. Without ``major``, ``higher``: the newest release
    of a higher major, where PyPI names one. PyPI is asked now (``updates.pypi``, or ``pypi``). Never raises."""
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
            return {"failed": f"{in_words(stuck)}: {advice(stuck, found.installer)}"}
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
    is about to, and is starting the next (its ``phase``, ``switching``), or is on its way back to the release before
    (``restoring``). A ``cad`` command that finds no server then waits for the one the update starts
    (``cad.engine.client.SWITCHING``). Never raises."""
    try:
        found = underway(now)
    except Exception:  # noqa: BLE001 - a record that cannot be read is no switch
        return False
    return found is not None and found.get("phase") in ("switching", "restoring")


# How fresh the worker's beat must be for a server's start to stand aside for its switch (``leaving``). It beats every
# minute and as it begins the switch (``auto_update_helper.Beat``), so a worker that died holds a start back no longer.
LEAVING_SECONDS = 150.0


def leaving(now: float | None = None) -> bool:
    """Whether cad's own update is switching away from the release this process runs, right now: the attempt underway
    is in its ``switching`` phase, it began from this release (its ``from``), and its worker beat in the last
    ``LEAVING_SECONDS``. The server the update drained is gone or going, and the next to start is the next release's:
    a server of this release started in between (a ``cad server start`` at that moment) would take that place, be
    taken by the update for the one it is waiting to see gone, and be stopped as the next one starts. So it starts
    none (``cad_server.engine.daemon.main``), and its starter launches none meanwhile and waits for the server that
    answers (``cad.engine.client.LEAVING``: a daemon launched then would run whichever release the pointer names at
    that instant). Not on the way back (the worker's phase is ``restoring`` then, kept once the pointer is back: the
    release before is the one to start). Never raises."""
    try:
        now = time.time() if now is None else now
        found = underway(now)
        if found is None or found.get("phase") != "switching" or found.get("from") != _version():
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
    "broken": "the new release did not run on this computer",
    "start_failed": "the new release's server did not start, so the release before runs again",
    "helper_start": "the update's worker could not start",
    "helper_crash": "the update's worker stopped with an error",
    "lost": "the update's worker ended without saying how",
    "no_installer": "uv cannot be found, so no update can begin",
    "no_switch": ("this cad's environment does not read cad's pointer as Python starts, or its own install of cad is "
                  "damaged, so an update would change nothing"),
    "packaged": "cad runs inside an app's private copy of AppData",
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
    "denied": "give your user write access to cad's state folder ({state}) and to uv's cache, then " + RETRIES,
    "disk_full": "free room on the disk, then " + RETRIES,
    "offline": _SETTING.format(setting="uv's offline setting"),
    "config_exclude": _SETTING.format(setting="uv's exclude-newer setting"),
    "config_index": _SETTING.format(setting="the package index named in uv's settings"),
    "config_tls": _SETTING.format(setting="uv's TLS settings"),
    "python": "the release asks for a newer Python than this cad was installed on: install cad again: `{reinstall}`",
    "platform": "nothing to do: this computer cannot take the release, and cad tries each newer one by itself",
    "broken": "nothing to do: cad kept the release it has and tries again by itself",
    "start_failed": ("nothing to do: cad went back to the release before and takes the next release when it is out; "
                     "`cad update` tries this one again"),
    "no_switch": "install cad again: `{reinstall}`",
    "packaged": "install cad again from PowerShell opened from the Start menu: `{reinstall}`",
    **dict.fromkeys(("no_installer", "no_program"), f"install uv ({UV_DOCS}), then `cad update`"),
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


def in_words(word: str) -> str:
    """A cause in plain words (``SAID``)."""
    return SAID[word]


def reinstall(installer: str | None = None) -> str:
    """The command that installs cad again for a global install made by ``installer`` (``REINSTALL``; uv's where it
    names neither)."""
    return REINSTALL.get(installer or "uv", REINSTALL["uv"])


def advice(word: str, installer: str | None = None) -> str:
    """What to do about a cause (``ADVICE``), in one line that names one command where there is one to run: the one
    ``cad doctor``, ``cad update``'s failure and the line a cad behind says (``notice``) give. A reinstall names the
    command of who made the global install (``installer``: ``reinstall``). ``KeyError`` for a word that is no cause."""
    return ADVICE[word].format(reinstall=reinstall(installer), state=_data())


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


def begin(target: str | None, *, start: bool = True, major: bool = False) -> dict[str, Any] | None:
    """The update to ``target`` (None: whatever the build gets) that ``cad update`` asked for (``major``: ``cad update
    --major``), begun now, in the one step across processes (``_claim``) whatever the case: the attempt underway
    joined, whatever its release, another process's too, and made a whole update where it only got its release ready;
    the release that is ready resumed, where it is ``target`` or PyPI named none (only its switch is left, which
    needs no network); else a new attempt. Never a second at once, never an attempt that ends ``ready``, never the
    install command after it. ``start``: a server wanted after it though none runs (false where ``cad update`` found
    none running). The attempt's record (``release``, ``at``), or None where it could not begin."""
    with _BEGIN:
        try:
            said, found = _start(target, automatic=False, start=start, major=major, wanted=None)
        except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
            return None
        return found if said in (BEGUN, UNDERWAY) else None



# --- the viewer's update button --------------------------------------------------------------------------------------


def button(*, now: float | None = None) -> dict[str, Any] | None:
    """What the viewer's update button shows (``GET /api/v1/server``'s ``cadUpdate``), from the feed as last read and the
    attempt's record, never asked of the network here: None where cad cannot update itself -- no global install, the
    check turned off for this process (``updates.checking``: ``CAD_UPDATE_CHECK=0``, CI), no release that runs --,
    whatever the switch says (a person can always click); else ``{"version", "latest", "state"}``: ``latest`` the
    newest release of this cad's major the feed names, where it is newer (``choose``; never a higher major's, which
    only ``cad update --major`` installs), else None; ``state`` ``ready`` (a release is ready, ``ready``, and the feed
    as last read calls for it still, as ``restart`` judges: ``ready`` that release, with the attempt's ``at`` and
    ``asked``; a click only restarts the server on it), ``working`` (an attempt of this release underway and still
    believed, that restarts the server -- one that only gets its release ready, ``"switch": false``, shows nothing
    until it is ready --, automatic or asked: ``underway``, whose ``asked`` says which, with the step it is at,
    ``phase``: one of ``PHASES``), ``failed`` (the last attempt of this
    release did not install what it was for -- ``lost`` too --, and this cad is still behind), with ``at`` the
    attempt's start, ``cause`` its word, ``said`` it in plain words (``in_words``), the ``installer`` that made the
    global install, ``log`` the worker's log of it (``LOG``, where there is one) and ``dismissed`` where the person put
    it away (``dismiss``), else ``idle``. An attempt underway from another release is the one that installed this one:
    ``idle``; and so is a server older than its own environment (``stale``): the release is there already, and the
    click's update only restarts the server on it. Never raises."""
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
        held = ready()
        if held is not None and called_for(held):
            return {**out, **attempt, "state": "ready", "ready": held["release"]}
        if mine and word is None and underway(now) is not None and found.get("switch") is not False:
            phase = found.get("phase")
            return {**out, **attempt, "state": "working", **({"phase": phase} if phase in PHASES else {})}
        if word is not None and latest is not None and not stale(chosen.wanted):
            log = _data() / LOG
            return {**out, **attempt, "state": "failed", "cause": word, "said": in_words(word),
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
        line = _behind(version, target, now)
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


def _behind(version: str, target: str, now: float) -> str:
    """``notice``'s line for this cad, release ``version``, behind ``target``."""
    found = global_install()
    installer = found.installer if found is not None else None
    stuck = blocked(found) if found is not None else None
    if stuck is not None:
        return (f"cad: this cad is {version} and cannot update itself to {target} ({in_words(stuck)}): "
                f"{advice(stuck, installer)}")
    record = last()
    word = cause(record, now) if record is not None and record.get("from") == version else None
    if word is not None:
        return (f"cad: this cad is {version} and has not been able to update itself to {target} ({in_words(word)}): "
                f"{advice(word, installer)}")
    return f"cad: cad {target} is out and this is {version}: `cad update` updates it"



# --- an attempt counted -----------------------------------------------------------------------------------------------

# The worker's outcomes that end an attempt. Its fourth, ``ready`` (the release ready, nothing switched), is none: the
# sitting that switches to it is the one counted, as ``installed`` or ``failed``.
ENDED = frozenset({"installed", "current", "failed"})
ALREADY = re.compile(r"cad \S+ is installed")  # the worker's detail where the environment ran the release already
WAIT = object()  # ``event``: not yet, the install command's run for the new cad still underway


def event(found: dict[str, Any], *, wait: bool = True) -> dict[str, Any] | object | None:
    """The ``update`` event an ended attempt (``found``, the record) is counted as (``analytics.update``'s arguments),
    ``WAIT`` while the install command's run for the cad it installed is underway (``wait`` false: the event as it
    stands, that run ``underway``), or None for a record that is none of an ended attempt (``ready`` neither). That
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
