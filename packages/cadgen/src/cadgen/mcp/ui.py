"""The CAD app a host renders: one self-contained HTML file, addressed by its build.

Every CAD surface loads this same page; what it shows comes from the launch the
opening tool returns. The URI carries a hash of the page, so a host that caches
resources by URI can never pair a new server with an old page. Any build's URI
reads as the current page: a tab the host restores after an update gets the
current app, which checks the protocol of the launch it was restored with.

The page must not change while the host runs. Each thread's server reports the
URI, and a host that sees it change drops the frames showing the old one. An
installed wheel's page never changes; a build directory's changes with every
rebuild, so serve a copy of it (``CADGEN_MCP_APP_DIR``) to a running host.
"""

from __future__ import annotations

import hashlib
import html
import os
import threading
from pathlib import Path

from cadgen.assets import runtime_build_hint, runtime_root

MIME = "text/html;profile=mcp-app"
_PREFIX, _SUFFIX = "ui://cad/", "/app.html"

# What the page needs from its sandbox: blob workers and modules (the bundle
# inlines its workers) and data URIs (its fonts and images). No network origin.
RESOURCE_META = {
    "ui": {
        "prefersBorder": False,
        "csp": {"connectDomains": ["data:", "blob:"], "resourceDomains": ["data:", "blob:"]},
        "permissions": {"clipboardWrite": {}},
    },
}


def app_dir() -> Path:
    """Where the built page lives: ``CADGEN_MCP_APP_DIR``, a checkout's build, or the wheel's."""
    override = str(os.environ.get("CADGEN_MCP_APP_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        app = parent / "apps" / "mcp"
        if (app / "package.json").is_file():
            if (app / "dist" / "index.html").is_file():
                return app / "dist"
            break
    return runtime_root() / "mcp"


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
                path = (self._directory or app_dir()) / "index.html"
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
        return f"{_PREFIX}{self.build}{_SUFFIX}"

    def owns(self, uri: object) -> bool:
        return isinstance(uri, str) and uri.startswith(_PREFIX) and uri.endswith(_SUFFIX)

    def html(self) -> str:
        return self._load()[1]
