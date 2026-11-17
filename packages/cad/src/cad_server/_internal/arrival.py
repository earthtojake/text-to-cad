"""BRIDGE-ONLY: how a release arrived on a computer by a shipped updater, kept by ``cad setup`` for its server, and
counted.

``cad setup --engine-update`` (``cad_server.cli.setup``) keeps, in the state folder, the record ``arrival.json`` --
written where none is there yet for the same release, so an updater's second run keeps the first --: ``schema``,
``version``, ``route`` (``updater``), ``from`` (the release it arrived from, ``came_from``, or None) and ``at`` (when,
the wall clock's seconds).

Each step is counted (``cad_server.analytics.arrival``, under the rules every count goes by, beside the settings of the
process that counts it): ``setup_ended``, called once as a run of ``cad setup`` or ``--engine-update`` ends, in the
release's own process; the install command's run the server owes after it, by ``install_script.ended``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

__all__ = ["RECORD", "SCHEMA", "came_from", "keep", "read", "setup_ended"]

RECORD = "arrival.json"
SCHEMA = "cad arrival/1"
# How a release arrived: by a shipped updater (``--engine-update``), or by a plain ``cad setup`` (``cad update`` typed).
UPDATER, SETUP = "updater", "setup"
OK, FAILED = "ok", "failed"


def _path() -> Path:
    from cad.engine import places

    return places.state_dir() / RECORD


def read(name: str) -> dict[str, Any] | None:
    """Release ``name``'s arrival record, or None where there is none of this schema for it."""
    try:
        found = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("schema") == SCHEMA and found.get("version") == name else None


def came_from(name: str) -> str | None:
    """The release a setup of release ``name`` arrives from, read before it changes anything: the one
    ``installations/current`` names where that is another, else the one 0.10.0's own records name on Windows
    (``places.appdata_state_dir``), else None."""
    from cad.engine import places
    from cad_server._internal import installations
    from cad_server.engine.registry import Folder

    try:
        current = installations.current_version()
        if current is not None and current != name:
            return current
        appdata = places.appdata_state_dir()
        named = installations.current_version(Folder(appdata)) if appdata is not None else None
    except (OSError, ValueError):
        return None
    return named if named != name else None


def keep(name: str, route: str, came: str | None, *, now: float | None = None) -> bool:
    """Release ``name``'s arrival record written, where none is there for it yet: whether it was written now.
    ``OSError`` when it cannot be."""
    from cad._internal.atomic_replace import write_bytes_atomic

    if read(name) is not None:
        return False
    record = {"schema": SCHEMA, "version": name, "route": route, "from": came, "at": time.time() if now is None else now}
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return True


def setup_ended(name: str, route: str, came: str | None, outcome: str, reason: str | None = None, *,
                first: bool = False) -> None:
    """A run of ``cad setup`` (``route`` ``setup``) or of ``--engine-update`` (``updater``) of release ``name`` ended,
    in ``outcome`` ``ok`` or ``failed`` (and why, ``reason``); ``came``: the release it arrived from. Counted
    (``analytics.arrival``): a failure each time, an ``ok`` once for the release on this computer -- by the run that
    kept its arrival record (``first``) -- and a plain setup's each time. It says nothing: a line after a failure would
    take the place of its reason where a shipped updater shows the last line it read."""
    from cad_server import analytics

    if outcome == OK and route == UPDATER and not first:
        return
    analytics.arrival("setup", route=route, earlier=came, outcome=outcome, reason=None if outcome == OK else reason)
