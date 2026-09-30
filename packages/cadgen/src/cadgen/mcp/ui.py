"""The CAD app a host renders: one self-contained HTML file, addressed by its build.

Every CAD surface loads this same page; what it shows comes from the launch the
opening tool returns. The URI carries a hash of the page, so a host that caches
resources by URI can never pair a new server with an old page. Any build's URI
reads as the current page: a tab the host restores after an update gets the
current app, which checks the protocol of the launch it was restored with.
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
    """Where the built page lives: ``CADGEN_CODEX_APP_DIR``, a checkout's build, or the wheel's."""
    override = str(os.environ.get("CADGEN_CODEX_APP_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        app = parent / "apps" / "codex"
        if (app / "package.json").is_file():
            if (app / "dist" / "index.html").is_file():
                return app / "dist"
            break
    return runtime_root() / "codex"


def _missing_page(reason: str) -> str:
    return (
        "<!doctype html><meta charset=utf-8><title>CAD</title>"
        "<body style=\"font:14px system-ui;margin:24px;color:#888\">"
        f"<p><b>CAD's app is missing from this install.</b></p><p>{html.escape(reason)}</p>"
    )


class AppPage:
    """The page, read and hashed once, on first use -- never at import or initialize."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._lock = threading.Lock()
        self._loaded: tuple[str, str] | None = None

    def _load(self) -> tuple[str, str]:
        with self._lock:
            if self._loaded is None:
                path = (self._directory or app_dir()) / "index.html"
                try:
                    data = path.read_bytes()
                except OSError:
                    self._loaded = ("missing", _missing_page(runtime_build_hint(path)))
                else:
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
