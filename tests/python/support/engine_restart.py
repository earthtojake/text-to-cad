"""An in-process build's restart as the engine has one: a fresh worker holds nothing, and takes a model from its
``.xbf`` while the key that file holds is the model's now (``build._previous``). A test that builds with
``daemon=False`` calls ``restart()`` where a worker would go, and builds through ``build(...)``, the engine's
build (``take=True``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def restart() -> None:
    """A worker gone and a fresh one in its place: nothing held."""
    from cad.engine import build
    from cad.engine.kernel import memo

    memo.clear()
    build._WRITTEN.clear()
    build._PARTS.clear()
    build._BUILT.clear()


def build(script: Path | str, functions: list[str] | None = None, **options: Any) -> list[dict]:
    """The engine's build of ``script`` in this process (``take=True``): what a fresh worker takes, it takes from a
    model's ``.xbf``."""
    from cad.engine import build as engine_build

    return engine_build.build(Path(script), functions, take=True, **options)
