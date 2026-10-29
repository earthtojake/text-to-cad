"""text-to-cad keeping itself up to date: the engine runs the newest release's ``cadgen setup`` itself.

The install command set this computer up (``cadgen setup``, ``cadgen.cli.setup``) and left a
receipt in the state folder (``install-receipt.json``) that says which release it installed, for
which engine port, for which apps (``only``, when the person named some) and with which PATH it
found their commands (``path``). Where there is one, the engine keeps what it records current: a
thread the daemon starts (``start``, ``cadgen-auto-update``) waits a short grace after the start,
so a start is never slowed, then once an hour reads the version feed (``cadgen.updates.feed``) and,
when the feed names a release past the receipt's, installs it (``run_once``):

1. **Staged.** The release is downloaded whole before anything changes: ``uvx ... --refresh-package
   cadgen --from cadgen==<release> cadgen --version`` (``cadgen._internal.launch.LAUNCHER``), which
   reads cadgen's index afresh -- uv's cache of it lasts ten minutes, which would call a release
   minutes old unsatisfiable -- and installs the release and its CAD kernel, hundreds of megabytes,
   minutes on a slow connection. It is staged when that exits 0 and says the release.
2. **Applied.** The staged release's own ``cadgen setup`` runs detached, for the receipt's apps,
   with the receipt's PATH before this process's: an engine Claude Desktop started from the Dock has
   launchd's PATH, which finds none of the apps' commands. That setup does what the install command
   does: it refreshes the skills through each app's own plugin command, registers the release and
   makes it the one the device runs (``<state>/current``, ``cadgen._internal.installations``), and
   the receipt it writes says how it went. No app's server line is rewritten: each is a floor, and
   the next session an app starts meets the new release's engine (``cadgen.engine.client.CURRENT``).

One attempt per release a day (``RETRY_SECONDS``): a release that fails is tried again the next
day, and the install command still works by hand. The person can start one at once from the update
card (``run_now``, the viewer's ``POST /__cad/update``): it reads the feed afresh unless it was read
in the last minute, and tries a failed release again whenever asked; one attempt runs at a time,
and never where the engine does not update the computer. What happened is kept in the state folder (``auto-update.json``:
``release``, ``started``, ``at``, ``stage`` -- ``staging``, ``applying``, ``done`` or ``failed`` --
and a failure's ``error``), what the commands printed beside it (``auto-update.log``, its last few
hundred kilobytes), and both are read by the update notice (``status``, for ``cadgen.updates.notice``: an attempt
under way says ``downloading`` while it stages, ``installing`` while it applies) and by ``cadgen
doctor`` (``describe``). While a command runs, ``at`` is renewed every minute
(``HEARTBEAT_SECONDS``, ``_wait``), so a stage that has said nothing for an hour (``STALE_SECONDS``)
while the receipt is still behind stopped before it finished: a failure.

Which engine does it (``wanted``): the one switch is on (``CADGEN_UPDATE_CHECK=0`` turns the check
and the update off, and neither runs in CI); not a development install; a receipt exists, so the
install command made this install; and its port is this engine's, so a test's engine, or a second
engine on another port, never updates anything. Not whether this process is told
(``cadgen._internal.channel``): an engine a store's plugin started still keeps the receipt's copies
current, and the setup never touches a store's copy.

Once a release is installed, nothing is restarted and nothing asked of anyone. The engine of the
release before is superseded (the daemon's ``SUPERSEDED``): once nothing holds or uses it, it steps
aside by itself, starting its successor first when pages watch it (``successor``, the daemon's
``SUCCESSOR``) -- the current release's ``cadgen server`` on its port, from its registered
installation, else through uvx -- which retires it at its start and serves the pages as they reload.

Nothing here raises into the daemon or waits on a request path: the thread logs every failure
(``cadgen.auto_update``) and goes on, an update started on demand runs in a thread of its own, and
the notice and the doctor only read files.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

LOG = logging.getLogger("cadgen.auto_update")

FILE = "auto-update.json"  # what the last attempt did, in the state directory
LOG_FILE = "auto-update.log"  # what its commands printed, beside it
LOG_BYTES = 512 * 1024  # past this the log is cut to its last ``LOG_KEPT`` bytes
LOG_KEPT = 256 * 1024
GRACE_SECONDS = 90.0  # after the daemon starts, before the first check
RETRY_SECONDS = 24 * 60 * 60  # a release attempted is attempted again a day later at the earliest
FRESH_SECONDS = 60.0  # an update started on demand reads a feed older than this afresh
SLICE_SECONDS = 60.0  # the longest the thread sleeps at once
STAGE_SECONDS = 30 * 60  # the download of a release, its kernel with it
APPLY_SECONDS = 3 * 60 * 60  # the setup, which allows each app's command 900 s
HEARTBEAT_SECONDS = 60.0  # while a command runs, how often the attempt says it is still under way (``at``)
STALE_SECONDS = 60 * 60  # a stage that has said nothing for this long stopped
STAGES = ("staging", "applying")  # an attempt under way
STAGE_WORDS = {"staging": "downloading", "applying": "installing"}  # what the notice and the doctor call each
UNDER_WAY = "an update is already under way"
STOPPED = "it stopped before it finished"
# The line ``cadgen setup`` ends its report with (``said``), which is never a failure's words.
SAID = "text-to-cad now updates itself"
# The variables of this process that would make the staged release's Python import another cadgen
# (the engine's own is on its PYTHONPATH) or name another installation: never handed on.
UNHANDED = ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE", "PYTHONPLATLIBDIR",
            "PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE", "PYTHONEXECUTABLE", "VIRTUAL_ENV",
            "CADGEN_INSTALLATION_VERSION")


# --- the gate ----------------------------------------------------------------------------------


def _state() -> Path:
    from cadgen.viewer.recents import state_dir  # noqa: PLC0415 -- the state directory's one definition

    return Path(state_dir())


def _json(path: Path) -> dict[str, Any]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def receipt() -> dict[str, Any] | None:
    """The install command's receipt (``cadgen.cli.setup``), or ``None`` when there is none to read."""
    from cadgen.cli.setup import RECEIPT, SCHEMA

    kept = _json(_state() / RECEIPT)
    return kept if kept.get("schema") == SCHEMA else None


def _port(port: int | None) -> int | None:
    if port is not None:
        return port
    from cadgen.engine.daemon import selected_port

    try:
        return selected_port()
    except ValueError:
        return None


def off(port: int | None = None) -> str | None:
    """Why the engine on ``port`` (by default the selected one) does not keep this computer up to
    date, in the doctor's words, or ``None`` when it does: switched on, not a development install,
    and the install command's receipt names that port."""
    from cadgen._internal.channel import DEV, channel
    from cadgen.updates import command, switched_on

    if not switched_on():
        return f"off (CADGEN_UPDATE_CHECK=0, or CI): update with `{command()}`"
    if channel() == DEV:
        return "off: a development install"
    found, port = receipt(), _port(port)
    if found is None:
        return f"off: the install command did not set this computer up; update with `{command()}`"
    if port is None or found.get("port") != port:
        return f"off on port {port}: the install command set up the engine on port {found.get('port')}"
    return None


def wanted(port: int | None = None) -> bool:
    """Whether the engine on ``port`` (by default the selected one) keeps this computer up to date
    (``off`` says why not)."""
    return off(port) is None


# --- what happened -----------------------------------------------------------------------------


def attempt() -> dict[str, Any]:
    """The last attempt as ``auto-update.json`` keeps it (written whole, by a replace), or ``{}``."""
    return _json(_state() / FILE)


def _keep(kept: dict[str, Any]) -> None:
    from cadgen._internal.atomic_replace import write_bytes_atomic

    folder = _state()
    folder.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(folder / FILE, (json.dumps(kept, sort_keys=True) + "\n").encode("utf-8"))


def _update(**fields: Any) -> dict[str, Any]:
    """The attempt with ``fields`` changed, under the state folder's lock."""
    from cadgen._internal.file_lock import state

    folder = _state()
    folder.mkdir(parents=True, exist_ok=True)
    with state(folder):
        kept = {**attempt(), **fields}
        _keep(kept)
    return kept


def _behind(release: Any, than: Any) -> bool:
    """Whether ``than`` is a release past ``release`` (one that is no release is behind every one)."""
    from cadgen.updates import _release

    newer = _release(than)
    return newer is not None and (_release(release) or ()) < newer


def _recent(kept: dict[str, Any], now: float) -> bool:
    then = kept.get("at", kept.get("started"))
    return isinstance(then, (int, float)) and 0 <= now - then < STALE_SECONDS


def _under_way(kept: dict[str, Any], now: float) -> bool:
    """Whether the attempt ``kept`` is running: at a stage, and said so within ``STALE_SECONDS``."""
    return kept.get("stage") in STAGES and _recent(kept, now)


def status(port: int | None = None, *, latest: str | None = None, version: str | None = None,
           now: float | None = None) -> dict[str, str] | None:
    """Where the self-update stands for a process of ``version`` (by default this one's), with the
    feed's ``latest``: ``{"state", "release"}``, an update's ``stage`` (``downloading`` or
    ``installing``, ``STAGE_WORDS``) and a failure's ``error``, or ``None`` when this engine does not
    update the computer (``wanted``) or there is nothing to say. ``failed`` and ``updating`` are the
    attempt at ``latest``'s; ``updated``, the receipt's release past ``version``; ``pending``,
    ``latest`` past both with no attempt at it. Never raises."""
    try:
        if not wanted(port):
            return None
        if version is None:
            from cadgen import __version__ as version
        have = (receipt() or {}).get("release")
        now = time.time() if now is None else now
        ahead = latest is not None and _behind(have, latest) and _behind(version, latest)
        kept = attempt()
        if ahead and kept.get("release") == latest:
            if kept.get("stage") == "failed":
                return {"state": "failed", "release": latest, "error": str(kept.get("error") or "it failed")}
            if kept.get("stage") in STAGES:
                if _recent(kept, now):
                    return {"state": "updating", "release": latest, "stage": STAGE_WORDS[kept["stage"]]}
                return {"state": "failed", "release": latest, "error": STOPPED}
        if _behind(version, have):
            return {"state": "updated", "release": str(have)}
        if ahead:
            return {"state": "pending", "release": latest}
        return None
    except Exception:  # noqa: BLE001 - a notice never fails what shows it
        LOG.debug("could not read the self-update's state", exc_info=True)
        return None


def _when(then: Any) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(then)) if isinstance(then, (int, float)) else "never"


def describe(port: int | None = None) -> str:
    """``cadgen doctor``'s line: whether the engine keeps this computer up to date, and where that
    stands. Reads files only."""
    from cadgen.updates import FILE as FEED, command, parse_feed

    why = off(port)
    if why is not None:
        return why
    found = receipt() or {}
    kept_feed = _json(_state() / FEED)
    latest = (parse_feed(kept_feed.get("feed")) or {}).get("latest")
    checked = f"last checked {_when(kept_feed.get('checked'))}"
    have, kept = found.get("release"), attempt()
    now = time.time()
    if latest is not None and _behind(have, latest):
        if kept.get("release") == latest and _under_way(kept, now):
            return f"installing v{latest} ({STAGE_WORDS[kept['stage']]}, since {_when(kept.get('started'))})"
        if kept.get("release") == latest and kept.get("stage") in (*STAGES, "failed"):
            error = kept.get("error") if kept.get("stage") == "failed" else STOPPED
            return (f"v{latest} could not install itself ({error}; {_when(kept.get('finished', kept.get('at')))}); "
                    f"update with `{command()}`")
        return f"v{latest} is out and installs itself within the hour ({checked})"
    if kept.get("stage") == "done" and kept.get("release") == have:
        return f"installed v{have} by itself {_when(kept.get('finished'))}; new sessions run it; {checked}"
    from cadgen import __version__

    if _behind(__version__, have):
        return f"installed v{have}; new sessions run it; {checked}"
    return f"up to date (v{have}), {checked}"


# --- the update ----------------------------------------------------------------------------------


def _log() -> Path:
    """The log, cut to its last ``LOG_KEPT`` bytes once it passes ``LOG_BYTES``."""
    path = _state() / LOG_FILE
    try:
        if path.stat().st_size > LOG_BYTES:
            with path.open("rb") as log:
                log.seek(-LOG_KEPT, os.SEEK_END)
                kept = log.read()
            path.write_bytes(kept[kept.find(b"\n") + 1:])
    except OSError:
        pass
    return path


def _note(path: Path, line: str) -> None:
    with path.open("ab") as log:
        log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {line}\n".encode("utf-8"))


def _last(output: bytes) -> str:
    """The last line of ``output`` that says something, short enough for a card, or ``""``."""
    for raw in reversed(output.decode("utf-8", "replace").splitlines()):
        text = raw.strip().strip("│╰─▶×").strip()
        if text and not text.startswith(SAID):
            return text if len(text) <= 240 else text[:239] + "…"
    return ""


def _environment(recorded: Any) -> dict[str, str]:
    """This process's environment for the staged release, the receipt's PATH (``recorded``) before
    its own, each folder once; nothing that would bring another cadgen with it (``UNHANDED``)."""
    env = {name: value for name, value in os.environ.items() if name.upper() not in UNHANDED}
    folders: list[str] = []
    for folder in [*(recorded.split(os.pathsep) if isinstance(recorded, str) else ()),
                   *env.get("PATH", "").split(os.pathsep)]:
        if folder and folder not in folders:
            folders.append(folder)
    env["PATH"] = os.pathsep.join(folders)
    return env


def _launcher(uvx: str, release: str, *, refresh: bool) -> list[str]:
    """``uvx ... --from cadgen==<release>``, with ``--refresh-package cadgen`` before ``--from``."""
    from cadgen._internal.launch import LAUNCHER

    at = LAUNCHER.index("--from")
    return [uvx, *LAUNCHER[1:at], *(("--refresh-package", "cadgen") if refresh else ()), *LAUNCHER[at:],
            f"cadgen=={release}"]


def _wait(process: subprocess.Popen, limit: float) -> int | None:
    """``process`` waited for, up to ``limit`` seconds, the attempt's ``at`` renewed every
    ``HEARTBEAT_SECONDS`` so a long download or setup never reads as stopped (``STALE_SECONDS``): its
    exit code, or ``None`` once the limit has passed with it still running."""
    deadline = time.monotonic() + limit
    while True:
        try:
            return process.wait(timeout=max(0.0, min(HEARTBEAT_SECONDS, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                return None
            _update(at=time.time())


def _stage(uvx: str, release: str, env: dict[str, str]) -> str | None:
    """The release downloaded and installed by uv, not yet set up: ``None``, or why it was not. What
    uv prints goes to the log, which the words of a failure are read back from."""
    from cadgen.engine.daemon import windowless

    argv = [*_launcher(uvx, release, refresh=True), "cadgen", "--version"]
    log = _log()
    _note(log, "$ " + " ".join(argv))
    start = log.stat().st_size
    with log.open("ab") as kept:
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=kept, stderr=subprocess.STDOUT, env=env,
                                       **windowless())
        except OSError as error:
            return f"{type(error).__name__}: {error}"
    code = _wait(process, STAGE_SECONDS)
    if code is None:
        process.kill()  # a download that hangs: uv's cache is left whole, and tomorrow (or the person) tries again
        return f"its download did not finish within {STAGE_SECONDS // 60} minutes"
    with log.open("rb") as kept:
        kept.seek(start)
        output = kept.read()
    if code == 0 and f"cadgen {release}" in output.decode("utf-8", "replace").splitlines():
        return None
    return _last(output) or f"uvx exited {code}"


def _apply(uvx: str, release: str, only: Any, env: dict[str, str]) -> str:
    """The staged release's ``cadgen setup`` run, detached, and waited for: what it last said, or how
    it exited (whether it succeeded is the receipt's to say)."""
    from cadgen.engine.daemon import detached

    argv = [*_launcher(uvx, release, refresh=False), "cadgen", "setup"]
    if isinstance(only, list) and only:
        argv += ["--only", ",".join(str(name) for name in only)]
    log = _log()
    _note(log, "$ " + " ".join(argv))
    start = log.stat().st_size
    with log.open("ab") as kept:
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=kept, stderr=subprocess.STDOUT, env=env,
                                       **detached())
        except OSError as error:
            return f"{type(error).__name__}: {error}"
    code = _wait(process, APPLY_SECONDS)
    if code is None:  # left to finish on its own: a setup is never cut off mid-way through an app's config
        return f"cadgen setup did not finish within {APPLY_SECONDS // 3600} hours"
    with log.open("rb") as kept:
        kept.seek(start)
        said = _last(kept.read())
    return said or f"cadgen setup exited {code}"


def _failed(release: str, error: str) -> str:
    _update(stage="failed", error=error.replace("\n", " "), finished=time.time())
    LOG.info("text-to-cad %s could not install itself: %s", release, error)
    return "failed"


def run_once(port: int | None = None, *, get: Callable[[str], Any] | None = None, now: float | None = None,
             force: bool = False) -> str | None:
    """One check, and the update it calls for: ``None`` when there was nothing to do (not ``wanted``,
    the receipt at or past the feed's release, an attempt under way, or that release attempted in the
    last day, ``RETRY_SECONDS``), else ``"done"`` or ``"failed"``. ``get`` reads the feed
    (``cadgen.updates.feed``). ``force``, the person's (``run_now``): the feed read afresh unless it
    was in the last minute (``FRESH_SECONDS``), and a release attempted today attempted again."""
    from cadgen import updates
    from cadgen._internal import providers
    from cadgen._internal.file_lock import state

    if not wanted(port):
        return None
    have = receipt() or {}
    found = updates.feed(updating=True, get=get, now=now, fresh=FRESH_SECONDS if force else updates.CHECK_SECONDS)
    latest = found["latest"] if found else None
    now = time.time() if now is None else now
    folder = _state()
    folder.mkdir(parents=True, exist_ok=True)
    with state(folder):  # one check of the attempt and one write of it, whole
        kept = attempt()
        if latest is None or not _behind(have.get("release"), latest):
            # Caught up, by this engine's setup or a person's: an attempt left under way is done.
            if kept.get("stage") in STAGES and not _behind(have.get("release"), kept.get("release")):
                _keep({**kept, "stage": "done", "finished": now})
            return None
        if _under_way(kept, now):
            return None  # another thread's or process's: one attempt at a time
        started = kept.get("started")
        if (not force and kept.get("release") == latest and isinstance(started, (int, float))
                and 0 <= now - started < RETRY_SECONDS):
            return None
        _keep({"release": latest, "started": now, "at": now, "stage": "staging"})
    env = _environment(have.get("path"))
    uvx = providers.uvx(providers.Machine(Path.home(), env))
    if uvx is None:
        return _failed(latest, "uvx was not found")
    LOG.info("staging text-to-cad %s", latest)
    error = _stage(uvx, latest, env)
    if error is not None:
        return _failed(latest, error)
    _update(stage="applying", at=time.time())
    LOG.info("applying text-to-cad %s", latest)
    said = _apply(uvx, latest, have.get("only"), env)
    if (receipt() or {}).get("release") == latest:
        _update(stage="done", finished=time.time())
        return "done"
    return _failed(latest, said)


def said() -> str:
    """The line ``cadgen setup``'s report ends with: what keeps text-to-cad up to date from now on."""
    from cadgen.updates import switched_on

    if not switched_on():
        return ("text-to-cad does not update itself here: CADGEN_UPDATE_CHECK=0 (or CI) turns the check and the "
                "update off; run the install command again to update.")
    return (f"{SAID}: a newer release installs within the hour of its publication. CADGEN_UPDATE_CHECK=0 turns "
            "the check and the update off.")


# --- on demand ----------------------------------------------------------------------------------

_now: threading.Thread | None = None  # the update the person started (``run_now``), while it runs
_now_lock = threading.Lock()


def _forced(port: int | None) -> None:
    try:
        run_once(port, force=True)
    except Exception:  # noqa: BLE001 - what failed is the attempt's to say; the process goes on
        LOG.exception("the self-update the person started failed")


def run_now(port: int | None = None) -> dict[str, Any]:
    """The update the person starts from the card (the viewer's ``POST /__cad/update``): one run of
    ``run_once`` with ``force``, in a thread of its own. ``{"started": True}``, or ``{"started":
    False, "reason"}``: where the engine on ``port`` does not update the computer, the doctor's words
    (``off``); while an attempt runs, in this process or another, ``UNDER_WAY``. Never waits on it:
    where it stands is the notice's (``status``)."""
    global _now
    why = off(port)
    if why is not None:
        return {"started": False, "reason": why}
    with _now_lock:
        if (_now is not None and _now.is_alive()) or _under_way(attempt(), time.time()):
            return {"started": False, "reason": UNDER_WAY}
        _now = threading.Thread(target=_forced, args=(port,), name="cadgen-update-now", daemon=True)
        _now.start()
    return {"started": True}


def successor(port: int) -> str | None:
    """The engine of the release the device runs, started on ``port`` to take this superseded one's
    place while pages watch it (the daemon's ``SUCCESSOR``, for its ``supersede``): ``None`` once it is
    started, else why not in one line. Its ``cadgen server`` runs detached, from the current
    installation (``installations.newer``), else -- the pointer's installation gone -- through uvx at
    the receipt's release, past this process's, on the receipt's PATH; in this process's environment
    with the receipt's PATH first and no other cadgen (``_environment``), and what it prints goes to
    the log. It retires this engine as it
    starts (``cadgen.engine.client.converge``), and serves this one's pages as they reload."""
    from cadgen import __version__
    from cadgen._internal import installations, providers
    from cadgen.engine.daemon import detached

    found = receipt() or {}
    env = _environment(found.get("path"))
    current = installations.newer()
    if current is not None:
        release = current["release"]
        argv = [current["cadgen"], "server", "--port", str(port)]
    else:
        release = found.get("release")
        if not isinstance(release, str) or not _behind(__version__, release):
            return f"no release newer than v{__version__} is installed"
        uvx = providers.uvx(providers.Machine(Path.home(), env))
        if uvx is None:
            return f"no installation of {release} is registered: run the install command"
        argv = [*_launcher(uvx, release, refresh=False), "cadgen", "server", "--port", str(port)]
    log = _log()
    _note(log, "$ " + " ".join(argv))
    with log.open("ab") as written:
        try:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=written, stderr=subprocess.STDOUT, env=env,
                             **detached())
        except OSError as error:
            return f"{type(error).__name__}: {error}"
    LOG.info("handing the engine on port %s over to text-to-cad %s", port, release)
    return None


# --- the thread ----------------------------------------------------------------------------------


def due_in(began: float, last: float | None, now: float) -> float:
    """Seconds until the next check, by the wall clock (a laptop's sleep counts): ``GRACE_SECONDS``
    after the thread ``began``, then an hour (``cadgen.updates.CHECK_SECONDS``) after the ``last``; a
    clock set back makes it due."""
    from cadgen.updates import CHECK_SECONDS

    if last is None:
        return max(0.0, began + GRACE_SECONDS - now) if now >= began else 0.0
    since = now - last
    return 0.0 if not 0 <= since < CHECK_SECONDS else CHECK_SECONDS - since


def _tick(port: int, clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> None:
    began, last = clock(), None
    while True:
        wait = due_in(began, last, clock())
        if wait > 0:
            sleep(min(wait, SLICE_SECONDS))
            continue
        last = clock()
        try:
            run_once(port)
        except Exception:  # noqa: BLE001 - the daemon goes on; the next hour is another check
            LOG.exception("the self-update failed")


def start(port: int) -> threading.Thread | None:
    """The thread that keeps the computer up to date from the engine on ``port`` (the daemon starts
    it), or ``None`` where nothing ever will: switched off, or a development install. Whether a
    receipt names the port is asked at each check: the install command may make one later."""
    try:
        from cadgen._internal.channel import DEV, channel
        from cadgen.updates import switched_on

        if not switched_on() or channel() == DEV:
            return None
        thread = threading.Thread(target=_tick, args=(port,), name="cadgen-auto-update", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - never a failure of the daemon's start
        LOG.exception("the self-update could not start")
        return None
