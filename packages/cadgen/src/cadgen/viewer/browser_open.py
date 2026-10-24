"""Open a viewer page in the person's browser without its token on any command line.

The page's URL carries the engine's token, and a browser (or the launcher that starts it) is given
its URL as an argument, which other local users may read in the process list. So the browser is
given a file instead: a page of one redirect to the URL, written owner-only (0600) in the engine's
own folder, which is this user's alone (``daemon.folder_refusal``). It is removed after
``KEEP_SECONDS`` by a thread of the process that wrote it, and any one older than that by the
next open, should that process have exited first."""
from __future__ import annotations

import html
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable

KEEP_SECONDS = 10.0
PREFIX = 'open-'


class CannotOpen(Exception):
    """No browser could be opened here, said in words (no display, no opener, a refused folder)."""


def redirect_page(url: str) -> bytes:
    """A page that only navigates to ``url``, sending no referrer."""
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            f'<meta http-equiv="refresh" content="0;url={html.escape(url, quote=True)}"><title>CAD</title></head>'
            f'<body><script>location.replace({json.dumps(url)})</script></body></html>\n').encode('utf-8')


def _sweep(folder: Path) -> None:
    """Remove the redirect files an earlier open left past their time."""
    stale = time.time() - KEEP_SECONDS
    for found in folder.glob(f'{PREFIX}*.html'):
        try:
            if found.lstat().st_mtime < stale:
                found.unlink()
        except OSError:
            pass


def _remove_later(path: Path) -> None:
    def remove() -> None:
        time.sleep(KEEP_SECONDS)
        try:
            path.unlink()
        except OSError:
            pass

    threading.Thread(target=remove, name='cadgen-browser-open', daemon=True).start()


def display_refusal(environ=None) -> str | None:
    """Why no browser can be shown to the person from this process, or None: a remote shell with no
    forwarded display, or a POSIX desktop-less session (no X11 or Wayland display), where Python's
    ``webbrowser`` would fall back to a console browser nobody sees."""
    environ = os.environ if environ is None else environ
    if os.name == 'nt':
        return None
    shown = environ.get('DISPLAY') or environ.get('WAYLAND_DISPLAY')
    if (environ.get('SSH_CONNECTION') or environ.get('SSH_TTY')) and not shown:
        return 'this is a remote session with no display to open a browser on'
    if sys.platform != 'darwin' and not shown:
        return 'there is no display to open a browser on'
    return None


def open_page(url: str, *, opener: Callable[[str], bool] = webbrowser.open) -> Path:
    """Open ``url`` in the browser through an owner-only redirect file; the file's path, or
    ``CannotOpen`` when no browser can be opened here (the file is removed at once when one did
    not)."""
    from cadgen.engine import daemon

    refusal = display_refusal()
    if refusal is not None:
        raise CannotOpen(refusal)

    folder = daemon.state_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as error:
        raise CannotOpen(f"the engine's folder {folder} cannot be made: {error.strerror or error}") from error
    refusal = daemon.folder_refusal(folder)
    if refusal is not None:
        raise CannotOpen(refusal)
    _sweep(folder)
    path = folder / f'{PREFIX}{secrets.token_hex(8)}.html'
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(redirect_page(url))
    try:
        opened = opener(path.as_uri())
    except Exception as error:  # noqa: BLE001 - any opener's failure is "no browser here"
        opened, reason = False, str(error)
    else:
        reason = 'no browser could be started here (no display, or no browser to open)'
    if not opened:
        path.unlink(missing_ok=True)
        raise CannotOpen(reason)
    _remove_later(path)
    return path
