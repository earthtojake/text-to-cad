"""Open in MuJoCo Studio: an MJCF in Studio's web viewer, the one app of Open in the installation runs itself.

Studio is no desktop app found by its bundle or its command on PATH: it is ``mujoco-studio``, the command
the mujoco integration's extra puts in an environment (``cad.registry``'s ``commands``), run as ``cad run
mujoco-studio --model FILE`` runs it (``cad.mujoco._command``: Studio's web viewer, the model reloaded as
it changes). So Open in offers it (``apps.APPS``' ``mujoco-studio``, for the ``mjcf`` kind) where that
command is here to run without anything fetched: in this process's own environment (an installation that
carries the integration, a checkout's development environment) or in the environment of ``cad[mujoco]``
the engine has made (``integration_env.found``), its ``mujoco-studio`` there (``find``). It is looked for
with the desktop apps, in the background, never on a request (``apps.DETECTED``).

Opening one (``start``) starts ``cad run mujoco-studio --model FILE`` with this process's Python, detached
and never waited on, never through a shell, its output written to a file of its own; a thread reads that
file for the URL Studio's banner prints (``url_of``: ``http://localhost:PORT/``) and opens it in the
person's browser once it appears, where a browser can be shown from here (``_open``: not on a Linux with no
display). Its page holds no credential, so the URL is opened as it is.

Studio's web viewer listens on every network interface with no authentication (``cad.mujoco._command``:
MuJoCo binds ``::`` and offers no way to pin it to loopback), so the server says so on its stderr, its log,
as it starts one (``EXPOSED``), and keeps track of every Studio it starts. Each is recorded from its spawn,
under the lock, by the file it shows (``_RUNNING``): Open in on that file while it starts or runs opens its
page -- once the URL appears, for one still starting -- rather than starting another; one that exited is
forgotten and the next Open in starts afresh; one whose URL does not appear within ``URL_SECONDS`` is
stopped and forgotten, never left listening where nothing offers its page. Studio outlives the request,
never the server: every Studio this process started is stopped as it exits (``stop``, registered with
``atexit`` at the first start: on POSIX its process group, which it leads, on Windows its process tree).
A server killed outright runs no exit handler, so its Studios stay until stopped by hand. The log is
removed once the URL is read on POSIX and, on Windows, where an open file cannot be, once its Studio is
stopped or found gone.
"""
from __future__ import annotations

import atexit
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

__all__ = ["COMMAND", "STOP_SECONDS", "URL_SECONDS", "Studio", "command", "find", "start", "stop", "url_of"]

COMMAND = "mujoco-studio"
# How long the URL is waited for: Studio loads the model and binds its port in a few seconds.
URL_SECONDS = 60.0
# How long a Studio being stopped has to go after it is asked to, before it is killed.
STOP_SECONDS = 5.0
_POLL_SECONDS = 0.25
# The Studios this process started, by the file each shows, from their spawn until they are found gone or
# stopped (``_Run``).
_RUNNING: dict[str, "_Run"] = {}
_LOCK = threading.Lock()
_REGISTERED = False  # ``stop`` registered with ``atexit``
# The page's address as Studio's banner prints it, the terminal's hyperlink escapes around it or not.
_URL = re.compile(r"http://localhost:(\d+)/")
# Windows' process creation flags (``subprocess``'s own, which it defines on Windows alone).
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


class Studio(NamedTuple):
    """MuJoCo Studio, found: the ``mujoco-studio`` that ``cad run mujoco-studio`` runs."""

    program: str


def _script(python: Path) -> Path | None:
    folder = python.parent
    return next((folder / name for name in (COMMAND, f"{COMMAND}.exe") if (folder / name).is_file()), None)


def find(found: Callable[[str], tuple[str, str, str]] | None = None, python: str | None = None) -> Studio | None:
    """Studio where ``cad run mujoco-studio`` runs it with nothing fetched -- this process's environment
    carries the mujoco integration, or its environment is made (``found``: ``integration_env.found``) -- and
    that environment holds its ``mujoco-studio``; None otherwise. Reads files, runs nothing."""
    from cad_server._internal import base

    if found is None:
        from cad_server._internal.integration_env import found
    try:
        state, folder, _release = found("mujoco")
    except Exception:  # noqa: BLE001 - an installation that cannot say where it is offers no Studio
        return None
    if state == "carried":
        environment = Path(python or sys.executable)
    elif state == "made":
        environment = base.interpreter(Path(folder))
    else:
        return None
    script = _script(environment)
    return Studio(str(script)) if script is not None else None


def command(path: str, python: str | None = None) -> list[str]:
    """``cad run mujoco-studio --model PATH``, with this process's Python: what Open in starts."""
    return [python or sys.executable, "-P", "-m", "cad_server.cli", "run", COMMAND, "--model", path]


def url_of(text: str) -> str | None:
    """The URL of Studio's page in what it printed, or None before its banner."""
    found = _URL.search(text)
    return f"http://localhost:{found.group(1)}/" if found else None


def _open(url: str) -> None:
    """Open ``url`` in a browser tab where one can be shown: not on a Linux with no display, where Python's
    ``webbrowser`` would start a console browser nobody sees (Studio's own opener's rule)."""
    import webbrowser

    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    webbrowser.open(url, new=2)


def _alive(child: object) -> bool:
    return getattr(child, "poll", lambda: 0)() is None


class _Run:
    """A Studio this process started on a file, from its spawn on: its process, its log, its page's URL once
    its banner printed it (None before), and ``ready``, set once the URL is known or never will be."""

    def __init__(self, child: object, log: Path) -> None:
        self.child = child
        self.log = log
        self.url: str | None = None
        self.ready = threading.Event()


def _forget(path: str, run: _Run) -> None:
    """``run`` no longer the Studio of ``path`` (under the lock), and its log removed."""
    with _LOCK:
        if _RUNNING.get(path) is run:
            del _RUNNING[path]
    _remove(run.log)


def _remove(log: Path) -> None:
    """The log removed where it can be: on Windows not while a process still holds it open."""
    try:
        log.unlink(missing_ok=True)
    except OSError:
        pass


def _end(child: object, *, platform: str = sys.platform, seconds: float = STOP_SECONDS,
         killpg: Callable[[int, int], None] | None = None,
         taskkill: Callable[..., object] = subprocess.run) -> None:
    """``child``, a Studio this process started, stopped with every process under it -- ``cad run``'s
    Python, MuJoCo's command and Studio itself: on POSIX its process group (it leads one,
    ``start_new_session``) terminated and, still there after ``seconds``, killed; on Windows its process tree
    (``taskkill /T /F``), else the process alone. On POSIX the group is signalled even where its leader
    exited, so a Studio left under it goes too. Best effort: one already gone is no error."""
    pid = getattr(child, "pid", None)
    if not isinstance(pid, int):
        return
    if platform == "win32":
        if not _alive(child):
            return
        try:
            taskkill(["taskkill", "/T", "/F", "/PID", str(pid)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            pass
        try:
            if _alive(child):
                child.terminate()  # type: ignore[attr-defined]
            child.wait(timeout=seconds)  # type: ignore[attr-defined]
        except (OSError, subprocess.TimeoutExpired):
            pass
        return
    import signal

    kill = killpg or os.killpg
    try:
        kill(pid, signal.SIGTERM)
    except OSError:
        return  # the group is gone
    try:
        child.wait(timeout=seconds)  # type: ignore[attr-defined]
    except subprocess.TimeoutExpired:
        try:
            kill(pid, signal.SIGKILL)
        except OSError:
            pass


def stop(*, end: Callable[[object], None] | None = None) -> None:
    """Every Studio this process started stopped (``_end``) and forgotten, its log removed: what the server
    does as it exits (``atexit``), so no Studio's listener outlives the server that started it."""
    with _LOCK:
        runs = list(_RUNNING.items())
        _RUNNING.clear()
    for _path, run in runs:
        try:
            (end or _end)(run.child)
        except Exception:  # noqa: BLE001 - the next is stopped all the same
            pass
        run.ready.set()
        _remove(run.log)


def _watch(path: str, run: _Run, opener: Callable[[str], None], seconds: float, clock: Callable[[], float],
           sleep: Callable[[float], None], end: Callable[[object], None]) -> str | None:
    """Wait for Studio's URL in its log, keep it as the page of ``path`` and open it; the URL, or None when
    Studio exited or ``seconds`` passed first. A Studio that exited is forgotten; one still running with no
    URL in time is stopped and forgotten, never left listening untracked (its page cannot be offered, and the
    next Open in starts afresh). The log is removed once read where an open file may be (not Windows; there,
    once the Studio is stopped or found gone)."""
    deadline = clock() + seconds
    url = None
    try:
        while url is None and clock() < deadline:
            try:
                url = url_of(run.log.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                break
            if url is None:
                if not _alive(run.child):
                    break
                sleep(_POLL_SECONDS)
    finally:
        if os.name != "nt":
            _remove(run.log)
    if url is None:
        try:
            if _alive(run.child):
                end(run.child)
        finally:
            _forget(path, run)
            run.ready.set()
        return None
    run.url = url
    run.ready.set()
    try:
        opener(url)
    except Exception:  # noqa: BLE001 - Studio runs; Open in on the file again opens its page
        pass
    return url


def _again(run: _Run, opener: Callable[[str], None], seconds: float) -> None:
    """The page of a Studio already started on the file opened: at once where its URL is known, else once it
    appears (``seconds`` at most); nothing where it never does."""
    if run.ready.wait(seconds) and run.url is not None:
        opener(run.url)


def _say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def start(path: str, *, spawn: Callable[..., object] = subprocess.Popen,
          opener: Callable[[str], None] = _open, platform: str = sys.platform, seconds: float = URL_SECONDS,
          clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
          wait: bool = False, say: Callable[[str], None] = _say,
          end: Callable[[object], None] | None = None) -> threading.Thread:
    """Start Studio on the MJCF at ``path`` (``command``), detached, its output to a file of its own, and
    open its page in the browser once its URL appears (a thread, returned; joined first with ``wait``); the
    page of the one this process already started on ``path`` instead, running or still starting (``_RUNNING``,
    recorded at its spawn, under the lock, so two requests never start two). Says on this process's stderr,
    the server's log, that Studio's web viewer now listens on every network interface with no authentication
    (``cad.mujoco._command.EXPOSED``). Raises ``OSError`` where the process cannot be started."""
    with _LOCK:
        run = _RUNNING.get(path)
        if run is not None and not _alive(run.child):
            del _RUNNING[path]
            _remove(run.log)
            run = None
        if run is None:
            fresh = True
            handle, name = tempfile.mkstemp(prefix="cad-mujoco-studio-", suffix=".log")
            log = Path(name)
            detached = ({"creationflags": _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP} if platform == "win32"
                        else {"start_new_session": True})
            try:
                with os.fdopen(handle, "wb") as out:
                    child = spawn(command(path), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                  close_fds=True, **detached)
            except OSError:
                _remove(log)
                raise
            run = _RUNNING[path] = _Run(child, log)
            _stopped_at_exit()
        else:
            fresh = False
    if fresh:
        from cad.mujoco._command import EXPOSED

        say(f"cad: Open in started MuJoCo Studio on {path}, until it exits or this server stops: "
            f"{EXPOSED.partition(': ')[2]}")
        ender = end or (lambda child: _end(child, platform=platform))
        thread = threading.Thread(target=_watch, args=(path, run, opener, seconds, clock, sleep, ender),
                                  name="cad-mujoco-studio", daemon=True)
    else:
        thread = threading.Thread(target=_again, args=(run, opener, seconds), name="cad-mujoco-studio", daemon=True)
    thread.start()
    if wait:
        thread.join()
    return thread


def _stopped_at_exit() -> None:
    """``stop`` registered to run as this process exits, once (under the lock)."""
    global _REGISTERED
    if not _REGISTERED:
        atexit.register(stop)
        _REGISTERED = True
