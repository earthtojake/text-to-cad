"""The person's settings: one file, ``settings.json``, in the state directory beside the model
library, so both CAD apps (``cadgen mcp`` and ``cadgen viewer``) and every version of cadgen read
the same answers -- nothing an install or an update replaces holds them. Deleting the state
directory forgets them.

The file is one JSON object with a section per feature, each owned by the module that uses it
(``analytics``: the answer to the analytics question, ``cadgen/analytics.py``). A write replaces
only its own section, under a lock, so two apps changing different settings never undo each other.
"""

from __future__ import annotations

import json
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
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # missing or unreadable: no settings yet
        return {}
    return settings if isinstance(settings, dict) else {}


def read_section(name: str, *, path: Path | None = None) -> dict[str, Any]:
    """One feature's settings (``{}`` when there are none, or the file cannot be read)."""
    section = _load(path or settings_path()).get(name)
    return section if isinstance(section, dict) else {}


def write_section(name: str, section: dict[str, Any] | None, *, path: Path | None = None) -> None:
    """Replace one feature's settings (``None`` removes them), keeping every other section as the
    file has it now. Raises ``OSError`` when the file cannot be written."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(path.with_name(LOCK)):
        settings = _load(path)
        if section is None:
            settings.pop(name, None)
        else:
            settings[name] = section
        write_bytes_atomic(path, (json.dumps(settings, indent=2, sort_keys=True) + "\n").encode("utf-8"))
