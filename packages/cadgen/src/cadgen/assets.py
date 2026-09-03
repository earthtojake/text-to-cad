"""Where cadgen's non-Python runtime assets live.

cadgen executes three kinds of thing it does not write in Python: Node builders (the DXF
render package is baked by a JS child), a headless browser bundle (the snapshot CLI
drives it in a page), and the CAD Viewer's built client (``cadgen viewer`` serves it).
All three ship inside the distribution under ``cadgen/_runtime``; all three can be
pointed elsewhere for development.

**Every resolver here is CALL-TIME.** Nothing at import time touches the filesystem or
looks for ``node``: ``pip install cadgen`` must succeed on a machine with no Node and no
browser, and the CAD Viewer's long-lived server must import light. A format that needs an
asset asks for it at the moment it needs it, and gets an actionable error if it is absent.

**Development beats the package, on purpose.** In this repo the builders resolve to the
live ``packages/cadgen-js/bin`` sources rather than the committed bundles, so editing builder
JS takes effect without a rebundle, and the viewer client resolves to ``apps/viewer/dist``
so ``npm run build`` there is what ``cadgen viewer`` serves. An installed wheel has no such
sources and falls through to ``_runtime``.
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


def _dev_builders_dir() -> Path | None:
    """``packages/cadgen-js/bin`` when cadgen is imported from a source checkout.

    Walks up from this module looking for a sibling ``cadgen-js/bin`` under a ``packages``
    directory -- true for ``packages/cadgen/src/cadgen/assets.py`` in this repo, and for a
    skill runtime that still vendors ``packages/cadgen`` beside ``packages/cadgen-js``. An
    installed wheel matches nothing here and falls through to the packaged copy.
    """
    for parent in Path(__file__).resolve().parents:
        if parent.name != "packages":
            continue
        candidate = parent / "cadgen-js" / "bin"
        if candidate.is_dir():
            return candidate
    return None


def _dev_viewer_dist_dir() -> Path | None:
    """``apps/viewer/dist`` when cadgen is imported from a source checkout.

    Anchored on the repository root -- the first parent that holds
    ``apps/viewer/package.json`` -- rather than on a ``packages`` directory, because the
    client app is not a sibling package. The dist is what ``npm run build`` writes there;
    an unbuilt checkout returns ``None`` and the caller says so.
    """
    for parent in Path(__file__).resolve().parents:
        app = parent / "apps" / "viewer"
        if (app / "package.json").is_file():
            dist = app / "dist"
            return dist if (dist / "index.html").is_file() else None
    return None


def node_builders_dir() -> Path:
    """Directory holding the esbuilt Node builders (``dxf-mesh.mjs`` and friends).

    ``CADGEN_NODE_BUILDERS_DIR`` names it directly. Otherwise a checkout's live
    ``packages/cadgen-js/bin`` wins over the packaged copy, so builder JS stays editable.
    """
    override = _env_dir("CADGEN_NODE_BUILDERS_DIR")
    if override:
        return override
    dev = _dev_builders_dir()
    if dev:
        return dev
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

    ``CADGEN_VIEWER_DIST`` names it directly (``cadgen viewer --dist`` is the flag twin and
    is applied by the caller before asking here). Otherwise a checkout's ``apps/viewer/dist``
    wins over the packaged copy, so a local ``npm run build`` is what gets served. The
    returned directory may not exist -- an unbuilt checkout or a wheel built without the
    viewer stage -- and ``cadgen viewer`` refuses to start with a build hint when it does not.
    """
    override = _env_dir("CADGEN_VIEWER_DIST")
    if override:
        return override
    dev = _dev_viewer_dist_dir()
    if dev:
        return dev
    return _RUNTIME / "viewer"
