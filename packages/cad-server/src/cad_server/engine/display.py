"""The engine's X display: where the processes it starts draw their stills on Linux when the request they
draw for names no ``DISPLAY`` of its own (``render.context.display``).

OCP's Linux wheels draw through GLX alone (``render/context.py``), so a still needs an X server, and an
agent's shell often has none to name: a server over SSH, a container, a sandbox, or an agent app that
does not pass its ``DISPLAY`` on. A process a declaration says draws (``Service.draws``: a document's
render process, started for its first picture) is started with ``places.DISPLAY`` (``CAD_ENGINE_DISPLAY``)
naming the engine's own display, and ``places.XAUTHORITY`` (``CAD_ENGINE_XAUTHORITY``) the file that
admits a client to it, where it takes one (``environment``); a model's worker, started for a build, is told
them with each export that draws (``worker.told_display``). So the display is found, or started, with the
first picture, never for a build. It is, first of:

1. the daemon's own ``DISPLAY`` (and ``XAUTHORITY``), where it has one: started from a desktop session,
   or by an app that has one;
2. an Xvfb the daemon starts itself, once, where ``Xvfb`` is on ``PATH``: the first display number free
   (``-displayfd``), a 24-bit screen and GLX, no TCP, and a cookie of its own that only this user can read
   (``-auth``), so no other user's program draws on it or reads it. It lives as long as the daemon: it is
   started under a shell that reads the daemon's pipe and stops it when the pipe closes (the daemon stopped,
   or killed), and ``stop`` stops it with the daemon;
3. none: a still is refused, naming what to install (``render.context.INSTALL``).

macOS and Windows draw on a window of their own and are given nothing here, and a Linux daemon with a
``DISPLAY`` starts nothing. An Xvfb that did not start is said in the daemon's log once and not started
again by this daemon; one that is not on ``PATH`` is looked for again at the next picture, so one
installed meanwhile is found.
"""

from __future__ import annotations

import logging
import os
import secrets
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO, Any

from cad.engine.places import DISPLAY, XAUTHORITY

__all__ = ["READY_SECONDS", "environment", "name", "stop"]

LOG = logging.getLogger("cad_server.engine.display")
# How long an Xvfb has to say it is ready (its display number on ``-displayfd``).
READY_SECONDS = 10.0
SCREEN = "1280x1024x24"
# The shell an Xvfb runs under. Xvfb (``"$@"``) writes its display number to the shell's standard output,
# the daemon's pipe for it; the shell lets go of that pipe, and stops Xvfb when its own standard input --
# the daemon's other pipe -- closes, or exits as Xvfb does. A command run in the background reads
# ``/dev/null`` unless told otherwise, so the reader is handed that pipe as descriptor 3. One-digit
# descriptors alone: dash, Debian's ``sh``, takes no other.
_WATCH = ('"$@" -displayfd 1 </dev/null & x=$!; exec 1>/dev/null 3<&0; '
          '{ read -r _ <&3; kill "$x" 2>/dev/null; } & exec 3<&-; wait "$x"')

_LOCK = threading.Lock()
_XVFB: "_Xvfb | None" = None
_FAILED: str | None = None  # why this daemon's Xvfb did not start, said once


class _Xvfb:
    """An Xvfb the daemon started: the shell it runs under, its display (``:N``), the cookie that admits a
    client to it, and its log."""

    def __init__(self, process: subprocess.Popen, display: str, authority: Path, log: IO[bytes]) -> None:
        self.process, self.display, self.authority, self.log = process, display, authority, log

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
        shutil.rmtree(self.authority.parent, ignore_errors=True)
        if not keep_log:
            self.log.close()


def _linux() -> bool:
    """Whether a still here draws on an X display: what ``render.context.platform`` calls linux."""
    return sys.platform != "darwin" and os.name != "nt"


def environment() -> dict[str, str]:
    """What a process that draws is started with (``Service.draws``): ``places.DISPLAY`` naming the engine's
    display (``name``) and ``places.XAUTHORITY`` the file that admits a client to it where it takes one;
    nothing where it has none or needs none."""
    found = name()
    if not found:
        return {}
    if _XVFB is not None and found == _XVFB.display:
        authority: str | None = str(_XVFB.authority)
    else:
        authority = os.environ.get("XAUTHORITY")
    return {DISPLAY: found, **({XAUTHORITY: authority} if authority else {})}


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


def _cookie() -> Path:
    """An X authority file of one MIT-MAGIC-COOKIE-1 for any display on this machine (family ``FamilyWild``,
    no address, no display number: ``libXau`` takes it for every one), in a folder only this user may enter."""
    folder = Path(tempfile.mkdtemp(prefix="cad-xauth-"))
    path = folder / "Xauthority"

    def field(data: bytes) -> bytes:
        return struct.pack(">H", len(data)) + data

    entry = struct.pack(">H", 0xFFFF) + field(b"") + field(b"") + field(b"MIT-MAGIC-COOKIE-1") + field(secrets.token_bytes(16))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(entry)
    return path


def _start(program: str) -> _Xvfb:
    """An Xvfb started, once it has said its display; ``RuntimeError`` saying why when it does not within
    ``READY_SECONDS``."""
    authority = _cookie()
    read, write = os.pipe()
    log = tempfile.TemporaryFile(prefix="cad-xvfb-")
    try:
        process = subprocess.Popen(["/bin/sh", "-c", _WATCH, "sh", program, "-screen", "0", SCREEN, "-nolisten", "tcp",
                                    "-auth", str(authority), "+extension", "GLX"],
                                   stdin=subprocess.PIPE, stdout=write, stderr=log, start_new_session=True)
    except OSError as error:
        os.close(read)
        os.close(write)
        log.close()
        shutil.rmtree(authority.parent, ignore_errors=True)
        raise RuntimeError(f"{program}: {error}") from None
    os.close(write)
    try:
        number = _said(read, process)
    finally:
        os.close(read)
    if number is None:
        _Xvfb(process, "", authority, log).stop(keep_log=True)
        log.seek(0)
        tail = log.read()[-600:].decode("utf-8", "replace").strip()
        log.close()
        raise RuntimeError(f"no display within {READY_SECONDS:g} s" + (f": {tail}" if tail else ""))
    return _Xvfb(process, f":{number}", authority, log)


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
