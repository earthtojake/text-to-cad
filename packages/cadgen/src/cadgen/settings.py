"""The person's settings: one file, ``settings.json``, in the state directory beside the model
library, so both CAD apps (``cadgen mcp`` and ``cadgen viewer``) and every version of cadgen read
the same answers -- nothing an install or an update replaces holds them. Deleting the state
directory forgets them.

The file is one JSON object with a section per feature, each owned by the module that uses it
(``telemetry``: whether usage stats and crash reports are sent, and the install's random id,
``cadgen/analytics.py``; ``features``: the CAD views' features a person turned off,
``cadgen/features.py``). A change reads,
changes and writes its own section under one lock (``update_section``), so two apps changing
settings at once never undo each other, whichever sections they touch.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cadgen._internal.atomic_replace import write_bytes_atomic
from cadgen._internal.file_lock import exclusive

FILE = "settings.json"
LOCK = "settings.lock"


def settings_path() -> Path:
    from cadgen.viewer.recents import state_dir  # noqa: PLC0415 -- the state directory's one definition

    return state_dir() / FILE


def _load(path: Path) -> dict[str, Any]:
    """The settings in ``path``: ``{}`` when there is no file yet, or a broken one (the next write
    mends it). Raises ``OSError`` when the file is there but cannot be read now: a caller must not
    take that for "no settings", or what it writes next would wipe the person's answers."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        settings = json.loads(text)
    except ValueError:
        return {}
    return settings if isinstance(settings, dict) else {}


def read_section(name: str, *, path: Path | None = None) -> dict[str, Any]:
    """One feature's settings (``{}`` when there are none). Raises ``OSError`` when the file is
    there but cannot be read."""
    section = _load(path or settings_path()).get(name)
    return dict(section) if isinstance(section, dict) else {}


def update_section(name: str, change: Callable[[dict[str, Any]], dict[str, Any] | None], *,
                   path: Path | None = None) -> dict[str, Any] | None:
    """Read one feature's settings, change them and write them back, all under the lock, so no
    other app's write lands in between. ``change`` gets a copy of the section (``{}`` when there
    is none) and returns the section to keep (``None`` removes it); nothing is written when that
    is what the file already holds. Returns what is kept. Raises ``OSError`` when the file cannot
    be read or written."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(path.with_name(LOCK)):
        settings = _load(path)
        current = settings.get(name)
        before = dict(current) if isinstance(current, dict) else None
        after = change(dict(before or {}))
        if after == before:
            return after
        if after is None:
            settings.pop(name, None)
        else:
            settings[name] = after
        write_bytes_atomic(path, (json.dumps(settings, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        return after


def write_section(name: str, section: dict[str, Any] | None, *, path: Path | None = None) -> None:
    """Replace one feature's settings (``None`` removes them), keeping every other section as the
    file has it now. Raises ``OSError`` when the file cannot be written."""
    update_section(name, lambda _: section, path=path)
