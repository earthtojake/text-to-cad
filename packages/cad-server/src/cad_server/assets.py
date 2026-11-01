"""Where cadgen's non-Python runtime assets live.

cadgen serves JavaScript it does not write in Python: the CAD Viewer's built client
(``cad viewer`` serves it) and the CAD app page (``cad-mcp`` serves it). They ship
inside the distribution under ``cad_server/_runtime``, and can be pointed elsewhere for
development. Nothing cadgen runs needs Node.

**Every resolver here is CALL-TIME.** Nothing at import time touches the filesystem: the
CAD Viewer's long-lived server must import light, and a page that needs an asset asks for
it at the moment it needs it, with an actionable message if it is absent.

In a source checkout the Viewer resolves to ``apps/web/dist``. An installed wheel has
no source tree and falls through to its bundled ``_runtime`` copy: a checkout is the exact
layout that builds cadgen (``checkout_root``), never a folder found above an installation.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

__all__ = [
    "CAD_APP_MODULE",
    "CAD_APP_SHELL",
    "cad_app_code",
    "cad_app_dir",
    "checkout_root",
    "runtime_build_hint",
    "runtime_root",
    "viewer_dist_dir",
]

# The CAD app's built page (``cad_server.mcp.ui``): the shell a host keeps as its resource, and the app,
# one module, which the shell loads from the engine (``GET /app``).
CAD_APP_SHELL, CAD_APP_MODULE = "shell.html", "app.js"

# Data-only; deliberately no __init__.py, so this is a path lookup rather than an import.
_RUNTIME = Path(__file__).resolve().parent / "_runtime"


def runtime_build_hint(path: Path | str, *, overridable: bool = True) -> str:
    """The sentence to append when a packaged ``_runtime`` asset is not there.

    Two very different situations wear the same symptom, and the fix differs, so the
    message has to say which one this is. In a SOURCE CHECKOUT ``_runtime`` is built
    rather than committed -- nothing in the repository carries it, and a clone that has
    never bundled simply has no directory -- so the fix is to run the bundler. In an
    INSTALLED cadgen the wheel carries it and its absence is a packaging regression, so
    the fix is to reinstall.
    """
    if _in_source_checkout():
        return (
            "The server is running from a source checkout, where the packaged runtime is BUILT "
            "and never committed: run scripts/bundle/bundle.sh to produce it. "
            f"Expected it at {path}."
        )
    return (
        f"This installation of the server is incomplete: {path} should ship inside the "
        "distribution. Reinstall text-to-cad"
        + (", or point the matching CAD_*_DIR environment variable at a directory "
           "that holds it." if overridable else ".")
    )


def checkout_root() -> Path | None:
    """The repository this cadgen is imported out of, or None: only the exact layout that
    builds it -- this file at ``<root>/packages/cad-server/src/cad_server/assets.py``, with
    ``<root>/packages/core`` beside it. An installed wheel, wherever it sits, matches nothing
    here: no folder above an installation is ever taken for a checkout."""
    here = Path(__file__).resolve()
    package, src, project, packages = here.parents[0], here.parents[1], here.parents[2], here.parents[3]
    if (package.name, src.name, project.name, packages.name) != ("cad_server", "src", "cad-server", "packages"):
        return None
    if not (packages / "core" / "package.json").is_file() or not (project / "pyproject.toml").is_file():
        return None
    return packages.parent


def _in_source_checkout() -> bool:
    """True when this cadgen is being imported out of the repository that builds it
    (``checkout_root``). A wheel matches nothing here.
    """
    return checkout_root() is not None


def runtime_root() -> Path:
    """The packaged ``_runtime`` directory. May not exist in a source checkout."""
    return _RUNTIME


def _env_dir(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    return Path(value).expanduser().resolve() if value else None


def _dev_viewer_dist_dir() -> Path | None:
    """A built ``apps/web/dist`` when imported from this repository checkout (``checkout_root``)."""
    root = checkout_root()
    if root is None:
        return None
    dist = root / "apps" / "web" / "dist"
    return dist if (dist / "index.html").is_file() else None


def viewer_dist_dir() -> Path:
    """Directory holding the CAD Viewer's built client (``index.html`` and its assets).

    ``CAD_VIEWER_DIST`` names it directly (``cad viewer --dist`` is its CLI twin).
    Otherwise a checkout's built ``apps/web/dist`` wins over the packaged copy.
    """
    override = _env_dir("CAD_VIEWER_DIST")
    if override:
        return override
    dev = _dev_viewer_dist_dir()
    if dev:
        return dev
    return _RUNTIME / "viewer"


def cad_app_dir() -> Path:
    """Where the CAD app's built page lives: ``CAD_MCP_APP_DIR``, a checkout's build, or the wheel's."""
    override = str(os.environ.get("CAD_MCP_APP_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    root = checkout_root()
    if root is not None and (root / "apps" / "mcp" / "dist" / CAD_APP_SHELL).is_file():
        return root / "apps" / "mcp" / "dist"
    return runtime_root() / "mcp"


_code: dict[str, tuple[int, bytes]] = {}
_code_lock = threading.Lock()


def cad_app_code(directory: Path | None = None) -> bytes | None:
    """The CAD app as one module (``app.js``), which the shell imports: read once per build, or None
    where the built page's folder has none."""
    path = (directory or cad_app_dir()) / CAD_APP_MODULE
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return None
    with _code_lock:
        kept = _code.get(str(path))
        if kept is not None and kept[0] == stamp:
            return kept[1]
    try:
        data = path.read_bytes()
    except OSError:
        return None
    with _code_lock:
        _code[str(path)] = (stamp, data)
    return data
