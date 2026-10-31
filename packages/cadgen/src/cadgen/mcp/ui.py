"""The CAD app a host renders: a small page, the shell, addressed by the release and its build,
which loads the CAD app the engine serves.

Every CAD surface loads this same page; what it shows comes from the launch the
opening tool returns. The resource is the shell (``shell.html``), which greets the
host, waits for the launch, and imports the app (``app.js``, one module of the whole
app) from the engine (``GET /__cad/mcp-app``, ``app_code``), through the call the host
carries back or from the engine directly: so a page a host keeps -- by its URI, or
open across an update -- runs the engine's release, and loads the next one in place
after an update. The URI carries the engine's release and a hash of the page,
so a host that caches resources by URI can never pair a new server with an old
page. Any build's URI reads as the current page: a tab the host restores after an
update gets the current app, which checks the protocol of the launch it was
restored with.

The page must not change while the host runs. Each MCP session reports the
URI, and a host that sees it change drops the frames showing the old one. An
installed wheel's page never changes; a build directory's changes with every
rebuild, so serve a copy of it (``CADGEN_MCP_APP_DIR``) to a running host.
"""

from __future__ import annotations

import hashlib
import html
import threading
from pathlib import Path

from cadgen.assets import CAD_APP_MODULE as APP
from cadgen.assets import CAD_APP_SHELL as SHELL
from cadgen.assets import cad_app_code as app_code
from cadgen.assets import cad_app_dir as app_dir
from cadgen.assets import runtime_build_hint

from .host import MIME  # the page's type, which a host that renders MCP Apps lists

_PREFIX, _SUFFIX = "ui://cad/", "/app.html"
__all__ = ["APP", "MIME", "RESOURCE_META", "SHELL", "AppPage", "app_code", "app_dir"]

# What the page needs from its sandbox: blob workers and modules (the bundle
# inlines its workers) and data URIs (its fonts and images). No network origin.
RESOURCE_META = {
    "ui": {
        "prefersBorder": False,
        "csp": {"connectDomains": ["data:", "blob:"], "resourceDomains": ["data:", "blob:"]},
        "permissions": {"clipboardWrite": {}},
    },
}


def _told(data: bytes, presentation: str) -> bytes:
    """The page with its presentation stated first thing in its head (or after its doctype)."""
    meta = f'<meta name="cad-presentation" content="{html.escape(presentation)}">'.encode("utf-8")
    lowered = data.lower()
    for opening in (b"<head", b"<!doctype"):
        start = lowered.find(opening)
        if start >= 0:
            end = data.find(b">", start) + 1
            return data[:end] + meta + data[end:]
    return meta + data


def _missing_page(reason: str) -> str:
    return (
        "<!doctype html><meta charset=utf-8><title>CAD</title>"
        "<body style=\"font:14px system-ui;margin:24px;color:#888\">"
        f"<p><b>CAD's app is missing from this install.</b></p><p>{html.escape(reason)}</p>"
    )


class AppPage:
    """The page, read and hashed once, on first use -- never at import or initialize.

    A host that mounts views inline gets the same app with ``<meta name="cad-presentation"
    content="inline">`` in its head: the page reads it before it greets the host, to offer the
    display modes that host has. A host that shows tabs gets the file's bytes, untouched.
    """

    def __init__(self, directory: Path | None = None, *, presentation: str | None = None) -> None:
        self._directory = directory
        self._presentation = presentation
        self._lock = threading.Lock()
        self._loaded: tuple[str, str] | None = None

    def presenting(self, presentation: str) -> "AppPage":
        """This page as served to a host that presents it ``presentation`` (``"inline"``)."""
        return AppPage(self._directory, presentation=presentation)

    def _load(self) -> tuple[str, str]:
        with self._lock:
            if self._loaded is None:
                path = (self._directory or app_dir()) / SHELL
                try:
                    data = path.read_bytes()
                except OSError:
                    self._loaded = ("missing", _missing_page(runtime_build_hint(path)))
                else:
                    if self._presentation:
                        data = _told(data, self._presentation)
                    self._loaded = (hashlib.sha256(data).hexdigest()[:16], data.decode("utf-8"))
            return self._loaded

    @property
    def build(self) -> str:
        return self._load()[0]

    @property
    def uri(self) -> str:
        """``ui://cad/<release>/<build>/app.html``: the release the engine runs and a hash of the page, so a
        host that keys what it caches by the URI (OpenAI's, by its own guidance) never pairs a page with
        an engine of another release."""
        from cadgen import __version__

        return f"{_PREFIX}{__version__}/{self.build}{_SUFFIX}"

    def owns(self, uri: object) -> bool:
        return isinstance(uri, str) and uri.startswith(_PREFIX) and uri.endswith(_SUFFIX)

    def html(self) -> str:
        return self._load()[1]
