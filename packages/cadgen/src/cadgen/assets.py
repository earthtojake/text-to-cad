"""Where cadgen's non-Python runtime assets live.

cadgen executes two kinds of JavaScript it does not write in Python: a headless browser
bundle (the snapshot CLI drives it in a page) and the CAD Viewer's built client
(``cadgen viewer`` serves it). Both ship inside the distribution under ``cadgen/_runtime``,
and both can be pointed elsewhere for development. The native file tracer every build
loads ships there too (``_runtime/native``, one library per platform, found by
cadgen._internal.filetrace) and has no override. Nothing cadgen runs needs Node.

**Every resolver here is CALL-TIME.** Nothing at import time touches the filesystem:
``pip install cadgen`` must succeed on a machine with no browser, and the CAD Viewer's
long-lived server must import light. A format that needs an asset asks for it at the
moment it needs it, and gets an actionable error if it is absent.

In a source checkout the Viewer resolves to ``apps/web/dist``. An installed wheel has
no source tree and falls through to its bundled ``_runtime`` copy.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "AssetMissing",
    "browser_runtime_dir",
    "require_browser_runtime",
    "runtime_build_hint",
    "runtime_root",
    "viewer_dist_dir",
]

# Data-only; deliberately no __init__.py, so this is a path lookup rather than an import.
_RUNTIME = Path(__file__).resolve().parent / "_runtime"


class AssetMissing(RuntimeError):
    """A runtime asset cadgen needs is not present in this installation."""


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
            "cadgen is running from a source checkout, where the packaged runtime is BUILT "
            "and never committed: run scripts/bundle/bundle.sh to produce it. "
            f"Expected it at {path}."
        )
    return (
        f"This cadgen installation is incomplete: {path} should ship inside the "
        "distribution. Reinstall cadgen"
        + (", or point the matching CADGEN_*_DIR environment variable at a directory "
           "that holds it." if overridable else ".")
    )


def _in_source_checkout() -> bool:
    """True when this cadgen is being imported out of the repository that builds it:
    a ``packages`` ancestor with ``core`` beside us. A wheel matches nothing here.
    """
    for parent in Path(__file__).resolve().parents:
        if parent.name == "packages" and (parent / "core" / "package.json").is_file():
            return True
    return False


def require_browser_runtime(directory: Path | str) -> Path:
    """The snapshot browser runtime, or :class:`AssetMissing` naming how to get it.

    It has no live source to fall back on: ``render.html`` is written by the bundler and
    ``snapshot-render.js`` is an esbuild of @text-to-cad/core, so a checkout that has never
    bundled cannot render at all. Without this the failure was a 404 inside a headless
    browser page.
    """
    path = Path(directory)
    missing = [name for name in ("render.html", "snapshot-render.js") if not (path / name).is_file()]
    if missing:
        raise AssetMissing(
            "cadgen's snapshot browser runtime is missing "
            f"{', '.join(missing)}. " + runtime_build_hint(path)
        )
    return path


def runtime_root() -> Path:
    """The packaged ``_runtime`` directory. May not exist in a source checkout."""
    return _RUNTIME


def _env_dir(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    return Path(value).expanduser().resolve() if value else None


def _dev_viewer_dist_dir() -> Path | None:
    """A built ``apps/web/dist`` when imported from this repository checkout."""
    for parent in Path(__file__).resolve().parents:
        app = parent / "apps" / "web"
        if (app / "package.json").is_file():
            dist = app / "dist"
            return dist if (dist / "index.html").is_file() else None
    return None


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
    Otherwise a checkout's built ``apps/web/dist`` wins over the packaged copy.
    """
    override = _env_dir("CADGEN_VIEWER_DIST")
    if override:
        return override
    dev = _dev_viewer_dist_dir()
    if dev:
        return dev
    return _RUNTIME / "viewer"
