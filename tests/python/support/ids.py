"""A model's document id as a test expects it: its ``.xbf``'s (``Model.id``, ``ids.file_id``), worked out from its
script and its name as the library works it out, without importing the script."""

from __future__ import annotations

import os
from pathlib import Path

from tests.python.support.paths import add_sources

add_sources()

from cad.engine.ids import canonical, file_id  # noqa: E402


def model_id(script: str | os.PathLike, function: str, name: str | None = None,
             xbf: str | os.PathLike | None = None) -> str:
    """The id of model ``function`` of ``script``: its ``.xbf``'s -- at ``xbf`` (relative to the script) where its
    ``@model`` gives a path, else ``<name>.xbf`` beside the script, ``name`` its ``name=`` or its function's."""
    path = Path(xbf) if xbf is not None else Path(f"{name or function}.xbf")
    if not path.is_absolute():
        path = Path(canonical(script)).parent / path
    return file_id(os.path.normpath(os.path.abspath(path)))
