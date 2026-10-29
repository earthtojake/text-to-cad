"""The state folder's existing lock, using the shared engine file-lock primitive."""
from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from cadgen.engine.file_lock import exclusive

# Retain the settings lock name used by older installations.
STATE_LOCK = "settings.lock"


def state(folder: Path, *, waiting: Callable[[], None] | None = None) -> contextlib.AbstractContextManager[None]:
    """Hold the state folder's one lock (``STATE_LOCK`` in ``folder``), waiting for any other holder."""
    return exclusive(folder / STATE_LOCK, waiting=waiting)
