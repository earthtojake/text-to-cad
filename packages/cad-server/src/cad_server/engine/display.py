"""The engine's X display: where the processes it starts draw their stills on Linux when the request they
draw for names no ``DISPLAY`` of its own (``render.context.display``).

OCP's Linux wheels draw through GLX alone (``render/context.py``), so a still needs an X server, and an
agent's shell often has none to name: a server over SSH, a container, a sandbox, or an agent app that
does not pass its ``DISPLAY`` on. Every process a declaration says draws (``Service.draws``: a model's
worker, a document's render process) is started with ``places.DISPLAY`` (``CAD_ENGINE_DISPLAY``) naming
the engine's own display (``environment``), first of:

1. the daemon's own ``DISPLAY``, where it has one (started from a desktop session, or by an app that
   has one);
2. an Xvfb the daemon starts itself, once, where ``Xvfb`` is on ``PATH``: the first display number free
   (``-displayfd``), a 24-bit screen and GLX, no TCP. It lives as long as the daemon: it is started
   under a shell that reads the daemon's pipe and stops it when the pipe closes (the daemon stopped,
   or killed), and ``stop`` stops it with the daemon;
3. none: a still is refused, naming what to install (``render.context.INSTALL``).

macOS and Windows draw on a window of their own and are given nothing here, and a Linux daemon with a
``DISPLAY`` starts nothing. An Xvfb that did not start is said in the daemon's log once and not started
again by this daemon; one that is not on ``PATH`` is looked for again at the next process, so one
installed meanwhile is found.
"""

from __future__ import annotations

import logging
import os
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import IO, Any

from cad.engine.places import DISPLAY

__all__ = ["READY_SECONDS", "environment", "name", "stop"]

LOG = logging.getLogger("cad_server.engine.display")
# How long an Xvfb has to say it is ready (its display number on ``-displayfd``).
READY_SECONDS = 10.0
SCREEN = "1280x1024x24"
# The shell an Xvfb runs under: it starts Xvfb (``"$@"``, its display number written to the pipe whose
# number is ``$1``), lets go of that pipe, and stops Xvfb when its own standard input -- the daemon's pipe
# -- closes, or exits as Xvfb does. A command run in the background reads ``/dev/null`` unless told
# otherwise, so the reader is handed the pipe as descriptor 3.
_WATCH = ('fd=$1; shift; "$@" -displayfd "$fd" </dev/null & x=$!; eval "exec $fd>&-"; exec 3<&0; '
          '{ read -r _ <&3; kill "$x" 2>/dev/null; } & exec 3<&-; wait "$x"')

_LOCK = threading.Lock()
_XVFB: "_Xvfb | None" = None
_FAILED: str | None = None  # why this daemon's Xvfb did not start, said once


class _Xvfb:
    """An Xvfb the daemon started: the shell it runs under, its display (``:N``), and its log."""

    def __init__(self, process: subprocess.Popen, display: str, log: IO[bytes]) -> None:
        self.process, self.display, self.log = process, display, log

    def alive(self) -> bool:
        return self.process.poll() is None

    def stop(self, *, keep_log: bool = False) -> None:
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()  # the shell's reader stops Xvfb
            except OSError:
                pass
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if not keep_log:
            self.log.close()


def _linux() -> bool:
    """Whether a still here draws on an X display: what ``render.context.platform`` calls linux."""
    return sys.platform != "darwin" and os.name != "nt"


def environment() -> dict[str, str]:
    """What a process that draws is started with (``Service.draws``): ``places.DISPLAY`` naming the engine's
    display (``name``), or nothing where it has none or needs none."""
    found = name()
    return {DISPLAY: found} if found else {}


def name() -> str | None:
    """The engine's X display: the daemon's own ``DISPLAY``, else its Xvfb's (started now, once), else None;
    None on macOS and Windows. Never raises."""
    if not _linux():
        return None
    own = os.environ.get("DISPLAY")
    if own:
        return own
    try:
        return _xvfb()
    except Exception:  # noqa: BLE001 - a display the engine could not start is a still refused by name, later
        LOG.warning("could not start Xvfb", exc_info=True)
        return None


def _xvfb() -> str | None:
    global _XVFB, _FAILED
    with _LOCK:
        if _XVFB is not None and _XVFB.alive():
            return _XVFB.display
        if _FAILED is not None:
            return None
        program = shutil.which("Xvfb")
        if program is None:
            return None
        started = time.monotonic()
        try:
            _XVFB = _start(program)
        except RuntimeError as error:
            _FAILED = str(error)
            LOG.warning("Xvfb did not start, so stills have no X display: %s", error)
            return None
        LOG.info("started Xvfb on %s for the engine's stills (%.2f s)", _XVFB.display, time.monotonic() - started)
        return _XVFB.display


def _start(program: str) -> _Xvfb:
    """An Xvfb started, once it has said its display; ``RuntimeError`` saying why when it does not within
    ``READY_SECONDS``."""
    read, write = os.pipe()
    log = tempfile.TemporaryFile(prefix="cad-xvfb-")
    try:
        process = subprocess.Popen(["/bin/sh", "-c", _WATCH, "sh", str(write), program, "-screen", "0", SCREEN,
                                    "-nolisten", "tcp", "+extension", "GLX"],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, pass_fds=(write,),
                                   start_new_session=True)
    except OSError as error:
        os.close(read)
        os.close(write)
        log.close()
        raise RuntimeError(f"{program}: {error}") from None
    os.close(write)
    try:
        number = _said(read, process)
    finally:
        os.close(read)
    if number is None:
        _Xvfb(process, "", log).stop(keep_log=True)
        log.seek(0)
        tail = log.read()[-600:].decode("utf-8", "replace").strip()
        log.close()
        raise RuntimeError(f"no display within {READY_SECONDS:g} s" + (f": {tail}" if tail else ""))
    return _Xvfb(process, f":{number}", log)


def _said(read: int, process: Any) -> str | None:
    """The display number Xvfb wrote to the pipe ``read`` (one line), or None when it closed, exited or took
    longer than ``READY_SECONDS``."""
    deadline = time.monotonic() + READY_SECONDS
    found = b""
    while b"\n" not in found:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        ready, _, _ = select.select([read], [], [], min(left, 0.25))
        if not ready:
            if process.poll() is not None:
                return None
            continue
        chunk = os.read(read, 64)
        if not chunk:
            return None
        found += chunk
    number = found.split(b"\n", 1)[0].strip()
    return number.decode("ascii") if number.isdigit() else None


def stop() -> None:
    """The daemon's Xvfb stopped, if it started one; the next process that draws starts another."""
    global _XVFB, _FAILED
    with _LOCK:
        started, _XVFB, _FAILED = _XVFB, None, None
    if started is not None:
        started.stop()
