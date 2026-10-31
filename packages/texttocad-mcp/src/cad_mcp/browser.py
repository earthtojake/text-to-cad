"""The one act of its own a text host's ``cad_show`` asks of this process: opening the person's browser.

The server runs in the environment of whatever started it (another agent's shell, another ``BROWSER``, no
display), so it never opens a browser itself: this process, which the host started in the person's own
environment, does. It says at initialize that it opens one for its host, and whether it can
(``transport_browser``); the server's answer then carries the page to open in its result's ``_meta``
(``OPEN``), which this process opens and strips before the host sees the result (``deliver``), and before
that it tells the server on its session whether the page opened (``OPENED``): the server counts a page as
open in the person's browser only once told it opened, so after a failed open the next ``cad_show`` opens
it again.

The page's URL carries a link, a credential for a day, and a browser (or the launcher that starts it) is
given its URL as an argument, which other local users may read in the process list. So the browser is
given a file instead: a page of one redirect to the URL, written owner-only (0600) in the engine folder,
which is this user's alone (``engine.folder_refusal``), and removed after ``KEEP_SECONDS``.
"""
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
from typing import Any, Callable

from cad_mcp import engine

# A text host's cad_show result: ``{"url", "said", "failed"}``, the page this process opens, the sentence
# of the result that says it opened, and the one it says in its place where the open fails (``{reason}``
# the failure). Only a transport that declared ``transport_browser`` is sent it.
OPEN = "dev.texttocad/open"
# This process's word on that page, the notification it sends on its session once its open returned and
# before its host has the answer: ``{"url", "opened"}``.
OPENED = "notifications/dev.texttocad/opened"
KEEP_SECONDS = 10.0
PREFIX = "open-"


class CannotOpen(Exception):
    """No browser could be opened here, said in words (no display, no opener, a refused folder)."""


def display_refusal(environ: Any = None) -> str | None:
    """Why no browser can be shown to the person from this process, or None: a remote shell with no
    forwarded display, or a POSIX desktop-less session (no X11 or Wayland display)."""
    environ = os.environ if environ is None else environ
    if os.name == "nt":
        return None
    shown = environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY")
    if (environ.get("SSH_CONNECTION") or environ.get("SSH_TTY")) and not shown:
        return "this is a remote session with no display to open a browser on"
    if sys.platform != "darwin" and not shown:
        return "there is no display to open a browser on"
    return None


def transport_browser() -> dict[str, Any]:
    """What this process says of its browser at initialize: that it opens one for its host, and
    ``refusal``, why none can be opened from its environment, or None."""
    return {"refusal": display_refusal()}


def redirect_page(url: str) -> bytes:
    """A page that only navigates to ``url``, sending no referrer."""
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            f'<meta http-equiv="refresh" content="0;url={html.escape(url, quote=True)}"><title>CAD</title></head>'
            f'<body><script>location.replace({json.dumps(url)})</script></body></html>\n').encode("utf-8")


def _sweep(folder: Path) -> None:
    stale = time.time() - KEEP_SECONDS
    for found in folder.glob(f"{PREFIX}*.html"):
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

    threading.Thread(target=remove, name="cad-mcp-browser-open", daemon=True).start()


def open_page(url: str, *, opener: Callable[[str], bool] = webbrowser.open) -> Path:
    """Open ``url`` in the browser through an owner-only redirect file; the file's path, or ``CannotOpen``
    when no browser can be opened here."""
    refusal = display_refusal()
    if refusal is not None:
        raise CannotOpen(refusal)
    folder = engine.engine_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as error:
        raise CannotOpen(f"the engine's folder {folder} cannot be made: {error.strerror or error}") from error
    refusal = engine.folder_refusal(folder)
    if refusal is not None:
        raise CannotOpen(refusal)
    _sweep(folder)
    path = folder / f"{PREFIX}{secrets.token_hex(8)}.html"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(redirect_page(url))
    try:
        opened = opener(path.as_uri())
    except Exception as error:  # noqa: BLE001 - any opener's failure is "no browser here"
        opened, reason = False, str(error)
    else:
        reason = "no browser could be started here (no display, or no browser to open)"
    if not opened:
        path.unlink(missing_ok=True)
        raise CannotOpen(reason)
    _remove_later(path)
    return path


def deliver(result: Any, opener: Callable[[str], bool] | None = None,
            tell: Callable[[str, bool], None] = lambda url, opened: None) -> Any:
    """``result`` as the host is given it: a page the server asked this process to open (``OPEN``) opened
    here (``open_page``) by ``opener`` (``webbrowser.open``, which reads this process's ``BROWSER``), and the
    request removed; where no browser opens, the sentence that said it did replaced by the one that says why
    not. Whether it opened is told, ``tell(url, opened)`` (the server, ``OPENED``), before the result is
    returned."""
    meta = result.get("_meta") if isinstance(result, dict) else None
    if not isinstance(meta, dict) or OPEN not in meta:
        return result
    asked = meta.pop(OPEN)
    if not meta:
        del result["_meta"]
    if not isinstance(asked, dict):
        return result
    url, said, failed = asked.get("url"), asked.get("said"), asked.get("failed")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return result  # only a page the server serves is opened, never a file or a program
    try:
        open_page(url, opener=opener or webbrowser.open)
    except CannotOpen as failure:
        tell(url, False)
        if isinstance(said, str) and isinstance(failed, str):
            instead = failed.replace("{reason}", str(failure))
            for item in result.get("content") or []:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    item["text"] = item["text"].replace(said, instead, 1)
    else:
        tell(url, True)
    return result
