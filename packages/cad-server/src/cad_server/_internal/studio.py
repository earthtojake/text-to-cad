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
display). Studio outlives the request and the server, until its process is stopped; while the one this
process started on a file runs, Open in on that file opens its page again rather than starting another
(``_RUNNING``). Its page holds no credential, so the URL is opened as it is.
"""
from __future__ import annotations

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

__all__ = ["COMMAND", "URL_SECONDS", "Studio", "command", "find", "start", "url_of"]

COMMAND = "mujoco-studio"
# How long the URL is waited for: Studio loads the model and binds its port in a few seconds.
URL_SECONDS = 60.0
_POLL_SECONDS = 0.25
# The Studios this process started whose page is up, by the file each shows: its process and its URL.
_RUNNING: dict[str, tuple[object, str]] = {}
_LOCK = threading.Lock()
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


def _watch(path: str, log: Path, child: object, opener: Callable[[str], None], seconds: float,
           clock: Callable[[], float], sleep: Callable[[float], None]) -> str | None:
    """Wait for Studio's URL in ``log``, keep it as the page of ``path`` and open it; the URL, or None when
    Studio exited or ``seconds`` passed first. The log is removed once read where an open file may be (not
    Windows)."""
    deadline = clock() + seconds
    url = None
    try:
        while url is None and clock() < deadline:
            try:
                url = url_of(log.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                break
            if url is None:
                if not _alive(child):
                    break
                sleep(_POLL_SECONDS)
    finally:
        if os.name != "nt":
            log.unlink(missing_ok=True)
    if url is not None:
        with _LOCK:
            _RUNNING[path] = (child, url)
        try:
            opener(url)
        except Exception:  # noqa: BLE001 - Studio runs; the person can still open its page from the log
            pass
    return url


def start(path: str, *, spawn: Callable[..., object] = subprocess.Popen,
          opener: Callable[[str], None] = _open, platform: str = sys.platform, seconds: float = URL_SECONDS,
          clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
          wait: bool = False) -> threading.Thread:
    """Start Studio on the MJCF at ``path`` (``command``), detached, its output to a file of its own, and
    open its page in the browser once its URL appears (a thread, returned; joined first with ``wait``); the
    page of the one already running on ``path`` instead, where this process started one. Raises ``OSError``
    where the process cannot be started."""
    with _LOCK:
        running = _RUNNING.get(path)
        if running is not None and not _alive(running[0]):
            del _RUNNING[path]
            running = None
    if running is not None:
        thread = threading.Thread(target=opener, args=(running[1],), name="cad-mujoco-studio", daemon=True)
        thread.start()
        if wait:
            thread.join()
        return thread
    handle, name = tempfile.mkstemp(prefix="cad-mujoco-studio-", suffix=".log")
    log = Path(name)
    detached = ({"creationflags": _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP} if platform == "win32"
                else {"start_new_session": True})
    try:
        with os.fdopen(handle, "wb") as out:
            child = spawn(command(path), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                          close_fds=True, **detached)
    except OSError:
        log.unlink(missing_ok=True)
        raise
    thread = threading.Thread(target=_watch, args=(path, log, child, opener, seconds, clock, sleep),
                              name="cad-mujoco-studio", daemon=True)
    thread.start()
    if wait:
        thread.join()
    return thread
