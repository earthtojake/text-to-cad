"""Where cadgen's non-Python runtime assets live.

cadgen executes three kinds of thing it does not write in Python: Node builders (the DXF
tree is baked by a JS child), a headless browser bundle (the snapshot CLI
drives it in a page), and the CAD Viewer's built client (``cadgen viewer`` serves it).
All three ship inside the distribution under ``cadgen/_runtime``; all three can be
pointed elsewhere for development.

**Every resolver here is CALL-TIME.** Nothing at import time touches the filesystem or
looks for ``node``: ``pip install cadgen`` must succeed on a machine with no Node and no
browser, and the CAD Viewer's long-lived server must import light. A format that needs an
asset asks for it at the moment it needs it, and gets an actionable error if it is absent.

Development overrides are explicit. Repository launchers set the supported environment
variables; installed package code never searches upward for another application's source.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "AssetMissing",
    "browser_runtime_dir",
    "node_builders_dir",
    "runtime_root",
    "viewer_dist_dir",
]

# Data-only; deliberately no __init__.py, so this is a path lookup rather than an import.
_RUNTIME = Path(__file__).resolve().parent / "_runtime"


class AssetMissing(RuntimeError):
    """A runtime asset cadgen needs is not present in this installation."""


def runtime_root() -> Path:
    """The packaged ``_runtime`` directory. May not exist in a source checkout."""
    return _RUNTIME


def _env_dir(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    return Path(value).expanduser().resolve() if value else None


def node_builders_dir() -> Path:
    """Directory holding the esbuilt Node builders (``dxf-mesh.mjs`` and friends).

    ``CADGEN_NODE_BUILDERS_DIR`` names it directly. Otherwise use the packaged copy.
    """
    override = _env_dir("CADGEN_NODE_BUILDERS_DIR")
    if override:
        return override
    return _RUNTIME / "node"


def browser_runtime_dir(explicit: Path | str | None = None) -> Path:
    """Directory holding ``snapshot-render.js`` + ``render.html``.

    ``explicit`` is a caller-supplied directory (``run_snapshot(runtime_dir=...)``),
    which a skill used to have to pass because the runtime was vendored beside it. It
    still wins when given; otherwise the packaged copy is used.
    """
    override = _env_dir("CADGEN_BROWSER_RUNTIME_DIR")
    if override:
        return override
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _RUNTIME / "browser"


def viewer_dist_dir() -> Path:
    """Directory holding the CAD Viewer's built client (``index.html`` and its assets).

    ``CADGEN_VIEWER_DIST`` names it directly (``cadgen viewer --dist`` is its CLI twin).
    Otherwise use the client bundled in this distribution, regardless of the current
    working directory. Repository launchers can explicitly select a development build.
    """
    override = _env_dir("CADGEN_VIEWER_DIST")
    if override:
        return override
    return _RUNTIME / "viewer"
