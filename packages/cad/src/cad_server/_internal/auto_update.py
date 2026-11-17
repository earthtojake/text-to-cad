"""cad's own update: the two switches, the check, and its trigger.

**The switches** are the person's, in cad's settings (``settings.json`` in the state folder, section ``auto_update``),
both off by default: ``on``, whether cad updates itself, and ``installer``, whether the install command runs again after
it (``installer_ran_for``: the release it last ran for; another part of cad reads it). ``cad auto-update`` changes
them; ``on`` only for a cad that is a uv tool.

**The check** (``due``): switch 1 on, the check not turned off for this process (``updates.checking``:
``CAD_UPDATE_CHECK=0``, CI), this cad the uv tool ``cad`` (``uv_tool``: uv's receipt in its environment), uv found
(``find_uv``: never the one in cad's own environment), and the version feed's ``latest`` newer than this cad (forward
only; no answer from the feed, no update), and that release not tried ``TRIES`` times already, nor in the last
``RETRY_SECONDS``: a release that fails is tried once more at a check an hour later, never in a loop. It is asked first
thing as the server starts (``at_start``, from the feed as last read), as the server tends itself (``tend``, the feed
read again in the background once an hour), and by ``cad server start`` when the start failed (``after_failed_start``,
the feed read when due): a release whose server cannot start still updates.

**The trigger** (``trigger``), once nothing is in flight -- at a start, at once; otherwise once nothing has run for
``IDLE_SECONDS``, or nothing has run since the server started (one update begun at a time, ``_BEGIN``): a detached
helper, never the ``cad`` executable and
never run from cad's environment (``auto_update_helper``, run by the Python that environment was made from), stops the
server, installs ``cad==<latest>`` with uv, and starts the server with whatever cad is there. On Windows it renames
each ``cad.exe`` of the tool aside before uv runs and puts a copy back, because uv cannot remove one that is running (a
``cad update`` that waits, a ``cad server start``); that works because cad takes its launcher off ``sys.path`` as it
starts (``cad_server/__init__.py``). The attempt is kept in the state folder (``RECORD``), which ``cad doctor`` shows.

**Asked for** (``cad update``, which the server it asks judges, ``asked``, and begins, ``begin``): the feed read now,
whatever its hour; switch 1, ``TRIES`` and ``RETRY_SECONDS`` do not apply (a typed update always updates); the update
begun as soon as nothing is in flight, not after the idle minute, or joined where one is underway. Counted in the
record as any attempt is, so the automatic tries stay bounded.

Imports the standard library alone; what it asks of cad it imports as it asks: ``cad.engine.places`` (the folders),
``cad_server.updates`` (the feed), ``cad._internal.atomic_replace`` (the attempt kept) and, to change a switch,
``cad_server.settings``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

SECTION = "auto_update"
RECORD = "auto-update.json"  # the last attempt, in the state folder
IDLE_SECONDS = 60.0
TRIES = 2  # how many times one release is tried: once, and once more at a later check
RETRY_SECONDS = 60 * 60.0  # how long after an attempt (underway, or ended) its release may be tried again
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


def _data() -> Path:
    from cad.engine.places import state_dir

    return state_dir()


def _version() -> str:
    from cad_server import __version__

    return __version__


# --- the switches -----------------------------------------------------------------------------------------------------


def switches(path: Path | None = None) -> dict[str, Any]:
    """``{"on", "installer", "installer_ran_for"}`` as kept; both off where nothing is kept or it cannot be read."""
    try:
        kept = json.loads((path or _data() / "settings.json").read_text(encoding="utf-8")).get(SECTION)
    except (OSError, ValueError, AttributeError):
        kept = None
    kept = kept if isinstance(kept, dict) else {}
    ran_for = kept.get("installer_ran_for")
    return {"on": kept.get("on") is True, "installer": kept.get("installer") is True,
            "installer_ran_for": ran_for if isinstance(ran_for, str) else None}


def change(on: bool, installer: bool | None = None, ran_for: str | None = None) -> dict[str, Any]:
    """The switches changed under the state folder's lock (``settings.update_section``): ``on``; ``installer`` where
    given; ``ran_for`` kept as the release the installer last ran for. ``OSError`` where they cannot be written."""
    from cad_server.settings import update_section

    def changed(kept: dict[str, Any]) -> dict[str, Any]:
        kept["on"] = on
        if installer is not None:
            kept["installer"] = installer
        if ran_for is not None:
            kept["installer_ran_for"] = ran_for
        return kept

    update_section(SECTION, changed)
    return switches()


# --- what this cad is -------------------------------------------------------------------------------------------------


def uv_tool(prefix: str | None = None) -> Path | None:
    """The environment of the uv tool ``cad`` this process runs from: ``prefix`` (``sys.prefix``) where uv's receipt
    there names ``cad`` first; else None (a cad installed any other way, which never updates itself)."""
    import tomllib

    folder = Path(prefix or sys.prefix)
    try:
        requirements = tomllib.loads((folder / "uv-receipt.toml").read_text(encoding="utf-8"))["tool"]["requirements"]
        first = requirements[0]
        name = first.get("name") if isinstance(first, dict) else re.split(r"[\s\[<>=!~;@]", str(first))[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return folder if str(name).lower() == "cad" else None


def installed_tool(uv: str | None = None, *, timeout: float = 30.0) -> Path | None:
    """The environment of the uv tool ``cad`` installed on this computer, wherever this process runs from (uvx's cache,
    say): where uv says its tools are (``uv tool dir``, which reads ``UV_TOOL_DIR`` as every uv command does), uv
    found as the update finds it (``find_uv``) else the one cad's own ``uv`` dependency carries, and uv's receipt there
    names ``cad`` (``uv_tool``) and its own ``cad`` command is there (``tool_command``). None where uv names none, or
    cannot be asked. Never raises."""
    try:
        if uv is None:
            uv = find_uv()
        if uv is None:
            from cad_server._internal.base import find_uv as carried

            uv = carried()
        done = subprocess.run([uv, "tool", "dir"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              env={name: value for name, value in os.environ.items() if name not in _UNSET},
                              creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
        lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
        if done.returncode != 0 or not lines:
            return None
        tool = Path(lines[-1]) / "cad"
        return tool if uv_tool(str(tool)) is not None and tool_command(tool).is_file() else None
    except Exception:  # noqa: BLE001 - no uv, or one that cannot answer: no tool found
        return None


def tool_command(tool: Path, windows: bool = os.name == "nt") -> Path:
    """The ``cad`` command of the uv tool environment ``tool``, its own (``Scripts/cad.exe``, ``bin/cad``): the one cad's
    update helper runs (``helper_command``)."""
    return tool / ("Scripts/cad.exe" if windows else "bin/cad")


def find_uv(environ: dict[str, str] | None = None, prefix: str | None = None,
            windows: bool = os.name == "nt") -> str | None:
    """uv: on ``PATH``, else where uv's own installer puts it (``UV_INSTALL_DIR`` and its ``bin``, ``XDG_BIN_HOME``,
    ``~/.local/bin``, ``~/.cargo/bin``, as the install command looks). Never one inside this cad's environment
    (``prefix``), which the update replaces."""
    environ = os.environ if environ is None else environ
    name = "uv.exe" if windows else "uv"
    home = Path(environ.get("USERPROFILE" if windows else "HOME") or Path.home())
    install = environ.get("UV_INSTALL_DIR")
    folders = [install, install and str(Path(install) / "bin"), environ.get("XDG_BIN_HOME"),
               str(home / ".local" / "bin"), str(home / ".cargo" / "bin")]
    inside = os.path.normcase(os.path.realpath(prefix or sys.prefix)).rstrip(os.sep) + os.sep
    for found in (shutil.which("uv", path=environ.get("PATH")),
                  *(str(Path(folder) / name) for folder in folders if folder)):
        if found and os.path.isfile(found) and not os.path.normcase(os.path.realpath(found)).startswith(inside):
            return found
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


def _tries(target: str) -> int:
    """How many times ``target`` has been tried (the last attempt's, where it is of ``target``)."""
    found = last()
    return int(found.get("tries", 1)) if found is not None and found["release"] == target else 0


def _tried(target: str, now: float) -> bool:
    """Whether ``target`` is not to be tried now: ``TRIES`` times already, or begun less than ``RETRY_SECONDS`` ago,
    underway or ended (a clock set back counts as long ago): the server a failed update starts never tries again."""
    found = last()
    if found is None or found["release"] != target:
        return False
    return 0 <= now - float(found["at"]) < RETRY_SECONDS or _tries(target) >= TRIES


# --- the check and its trigger ----------------------------------------------------------------------------------------


def due(*, fetch: bool = False, now: float | None = None) -> str | None:
    """The release to update to now, or None (see the module). ``fetch``: the feed read first where an hour has
    passed (``updates.feed``); else the feed as last read. Never raises."""
    try:
        if not switches()["on"] or uv_tool() is None or find_uv() is None:
            return None
        from cad_server import updates

        if not updates.checking():
            return None
        known = updates.feed(fetch=fetch)
        target = known["latest"] if known else None
        if not newer(target, _version()) or _tried(target, time.time() if now is None else now):
            return None
        return target
    except Exception:  # noqa: BLE001 - a check that cannot be made is no update
        return None


def helper_command(target: str, *, now: float, version: str, prefix: str | None = None, uv: str = "uv",
                   base: str | None = None, record: str = RECORD, tries: int = 1,
                   windows: bool = os.name == "nt") -> list[str]:
    """The helper's command line: the Python this environment was made from (``base``: ``sys._base_executable``,
    never this environment's), isolated, running the helper's source, and its one argument."""
    prefix = prefix or sys.prefix
    cad = str(tool_command(Path(prefix), windows))
    told = {"uv": uv, "cad": cad, "target": target, "prefix": prefix, "record": record, "from": version, "at": now,
            "tries": tries}
    python = base or getattr(sys, "_base_executable", None) or sys.executable
    return [python, "-I", "-S", "-c", HELPER.read_text(encoding="utf-8"), json.dumps(told)]


def trigger(target: str) -> bool:
    """The update to ``target`` begun: its attempt kept (``RECORD``, outcome ``underway``), and the helper started,
    detached, with no window, in an environment that points at nothing of this one (``_UNSET``). Whether it started;
    never raises."""
    try:
        from cad.engine.places import detached

        now, version, record, tries = time.time(), _version(), _data() / RECORD, _tries(target) + 1
        command = helper_command(target, now=now, version=version, uv=find_uv() or "uv", record=str(record),
                                 tries=tries)
        inside = os.path.normcase(os.path.realpath(sys.prefix)).rstrip(os.sep) + os.sep
        if os.path.normcase(os.path.realpath(command[0])).startswith(inside):
            return False  # no Python outside this environment to run it with
        _keep(record, {"release": target, "from": version, "at": now, "tries": tries, "outcome": "underway"})
        env = {name: value for name, value in os.environ.items() if name not in _UNSET}
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=env, cwd=str(record.parent), **detached())
        return True
    except Exception:  # noqa: BLE001 - an update that cannot begin leaves cad as it is
        return False


def _keep(path: Path, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, json.dumps(record, sort_keys=True).encode("utf-8"))


def _begin_due(*, fetch: bool = False) -> str | None:
    """The update begun where it is due (``due``, ``trigger``), under ``_BEGIN``: the release it updates to, or None."""
    with _BEGIN:
        target = due(fetch=fetch)
        return target if target is not None and trigger(target) else None


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
    """``cad server start`` failed: the update begun where it is due, the feed read first where an hour has passed. The
    release it updates to, or None."""
    return _begin_due(fetch=True)


# --- an update asked for: ``cad update`` ------------------------------------------------------------------------------

NOT_THE_TOOL = ("the cad server running is not the uv tool's cad: run `cad server stop`, then `cad server start`, then "
                "`cad update` again")
CHECK_OFF = ("this cad server does not look for updates (CAD_UPDATE_CHECK=0, CI, or a development build), so it does "
             "not update cad")
NO_UV = "the cad server cannot find uv, which cad updates itself with: install uv, then run `cad update` again"


def asked(*, read: Callable[[], tuple[Any, Any]] | None = None) -> dict[str, Any]:
    """``cad update`` judged by the server it asks (``{"op": "update"}``), for the cad this process is: ``{"failed"}`` in
    one line where it cannot update cad -- not the uv tool's cad, the check turned off for this process
    (``updates.checking``), no uv, or the feed not read and nothing newer known --; ``{"ok": true, "newest"}``, this
    release, where the feed names none newer; or ``{"ok": true, "updating", "from"}``, the update to ``begin``. The
    feed is read now (``updates.read_now``, or ``read``), whatever its hour. Never raises."""
    try:
        version = _version()
        if uv_tool() is None:
            return {"failed": NOT_THE_TOOL}
        from cad_server import updates

        if not updates.checking():
            return {"failed": CHECK_OFF}
        if find_uv() is None:
            return {"failed": NO_UV}
        fresh, known = (read or updates.read_now)()
        target = (fresh or known or {}).get("latest")
        if newer(target, version):
            return {"ok": True, "updating": target, "from": version}
        if fresh is None:
            return {"failed": f"could not read which release is newest, so cad {version} stays as it is: try "
                              "`cad update` again later"}
        return {"ok": True, "newest": version}
    except Exception as error:  # noqa: BLE001 - said in its one line, never a crash of the server's
        return {"failed": f"could not look for an update: {type(error).__name__}: {error}"}


def underway(now: float | None = None) -> dict[str, Any] | None:
    """The attempt underway now, of any release: the last one, begun less than ``RETRY_SECONDS`` ago and not ended (a
    helper that died ends nothing, so past that none is). None where none is."""
    found = last()
    if found is None or found.get("outcome") != "underway":
        return None
    return found if 0 <= (time.time() if now is None else now) - float(found["at"]) < RETRY_SECONDS else None


def begin(target: str) -> dict[str, Any] | None:
    """The update to ``target`` that ``cad update`` asked for, begun now -- or the attempt underway joined, whatever
    its release (``underway``): never a second at once. The attempt's record (``release``, ``at``), or None where it
    could not begin."""
    with _BEGIN:
        found = underway()
        if found is not None:
            return found
        if not trigger(target):
            return None
        found = last()
        return found if found is not None and found["release"] == target else None
