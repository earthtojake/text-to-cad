"""How a version arrived on this computer: kept by ``cad setup`` for the version's server, and counted.

``cad setup`` and its hidden ``--engine-update`` (``cad_server.cli.setup``) keep, in the version's data folder, the
record ``arrival.json`` -- written once, where none is there yet, so a later setup of the same version (the install
script run again, a hand-over's own setup) keeps the first --: ``schema``, ``version``, ``route`` (``updater`` for
``--engine-update``, the shipped updaters' route; ``setup`` for a plain setup), ``from`` (the version it arrived from,
``came_from``, or None), ``at`` (when, the wall clock's seconds) and ``served`` (None until the version's server has
served once, then when). The version's server, as it tends itself (``cad_server.engine.daemon``), says the first time
it serves (``first_serve``), once: its mark is ``served``.

Each step is counted (``cad_server.analytics.arrival``, under the rules every count goes by, beside the settings of the
process that counts it) by one small function: ``setup_ended``, called once as a run of ``cad setup`` or
``--engine-update`` ends, and ``first_served``, called by ``first_serve``; the hand-over's own is
``install_script.ended``.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["RECORD", "SCHEMA", "came_from", "first_serve", "first_served", "keep", "read", "setup_ended"]

RECORD = "arrival.json"
SCHEMA = "cad arrival/1"
# How a version arrived: by a shipped updater (``--engine-update``), or by a plain ``cad setup``.
UPDATER, SETUP = "updater", "setup"
# What a run of setup ended in, and why one failed: its making could not run from this shell (``versions.CANNOT``:
# ``uv``, ``network``, ``denied``), else ``other``.
OK, FAILED = "ok", "failed"
# A setup's ``ok`` counted by the version's own Python, for a setup that runs in another (uvx's): its argv after
# ``-c``, the route and the version it came from (empty: none).
COUNT = ("import sys\nfrom cad_server import analytics\n"
         "analytics.arrival('setup', route=sys.argv[1], earlier=sys.argv[2] or None, outcome='ok')\n")
COUNT_SECONDS = 60.0


def _path(name: str) -> Path:
    from cad.engine import places

    return places.data_dir(name) / RECORD


def read(name: str) -> dict[str, Any] | None:
    """Version ``name``'s arrival record, or None where there is none of this schema."""
    try:
        found = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("schema") == SCHEMA else None


def _write(name: str, record: dict[str, Any]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def came_from(name: str) -> str | None:
    """The version a setup of version ``name`` arrives from, read before it changes anything: the release
    ``installations/current`` names where that is none of the versions installed (the layout of 0.11.10 and earlier,
    whose updater or install a setup follows), else the newest installed version older than ``name``, else the release
    0.10.0's own records name on Windows (``places.appdata_state_dir``: its ``installations/current``), else None (a
    computer with nothing older)."""
    from cad.engine import places
    from cad_server._internal import installations, versions

    try:
        current = installations.current_version()
        present = versions.present()
    except (OSError, ValueError):
        return None
    if current is not None and current != name and current not in present:
        return current
    older = [version for version in present if versions.older(version, name)]
    if older:
        return older[-1]  # ``present`` is oldest first
    appdata = places.appdata_state_dir()
    if appdata is None:
        return None
    try:
        named = (appdata / installations.CURRENT).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return named if places.VERSION.fullmatch(named) and named != name else None


def keep(name: str, route: str, came: str | None, *, now: float | None = None) -> bool:
    """Version ``name``'s arrival record written, where none is there yet (see the module): whether it was written now,
    by the first setup of the version on this computer. ``OSError`` when it cannot be."""
    if read(name) is not None:
        return False
    _write(name, {"schema": SCHEMA, "version": name, "route": route, "from": came,
                  "at": time.time() if now is None else now, "served": None})
    return True


def setup_ended(name: str, route: str, came: str | None, outcome: str, reason: str | None = None, *,
                first: bool = False) -> None:
    """A run of ``cad setup`` (``route`` ``setup``) or of ``--engine-update`` (``updater``) of version ``name`` ended:
    in ``outcome`` ``ok`` -- the whole run done --, or ``failed`` in whichever run it failed, the prepare run included,
    and then why (``reason``: ``uv``, ``network``, ``denied`` or ``other``); ``came`` is the version it arrived from
    (``came_from``). Called once per run, as it ends (``cad_server.cli.setup``). Counted (``analytics.arrival``): a
    failure here, by the process it failed in; an ``ok`` once for the version on this computer -- by the run that kept
    its arrival record (``first``) -- and in the version's own process, whose settings hold the person's answer once
    its import is done: this one where it is the version's, else the version's own Python, run for it (``COUNT``),
    as a plain ``cad setup`` runs in uvx's. It says nothing: setup's own lines say the outcome, and a line after a
    failure would take the place of its reason where a shipped updater shows the last line it read."""
    from cad.engine import places
    from cad_server import analytics

    if outcome != OK:
        analytics.arrival("setup", route=route, earlier=came, outcome=FAILED, reason=reason)
        return
    if not first:
        return
    if places.versioned() == name:
        analytics.arrival("setup", route=route, earlier=came, outcome=OK)
        return
    record = places.version_record(name)
    if record is None:
        return
    from cad_server.cli.setup import _environment

    try:
        subprocess.run([record["python"], "-P", "-c", COUNT, route, came or ""], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**_environment(), places.INSTALLATION_ENV: name}, timeout=COUNT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def first_served(name: str, route: str, came: str | None, told: Callable[[str], None]) -> None:
    """Version ``name``'s server serves for the first time since the version was set up, by ``route`` from ``came``
    (``first_serve``): counted (``analytics.arrival``, in the server's own process), and one line to ``told`` (the
    server's log)."""
    from cad_server import analytics

    analytics.arrival("serving", route=route, earlier=came, outcome=OK)
    told(f"cad {name} serves for the first time on this computer, set up by {route}"
         + (f" from {came}" if came else ""))


def first_serve(name: str, told: Callable[[str], None], *, now: float | None = None) -> bool:
    """Version ``name``'s server, as it tends itself: the first time it serves since the version was set up -- its
    arrival record there and not yet marked ``served`` --, ``first_served`` called and the record marked, so it is
    called once. Whether it was. ``OSError`` when the mark cannot be written (it is tried again at the next tending)."""
    record = read(name)
    if record is None or record.get("served") is not None:
        return False
    record["served"] = time.time() if now is None else now
    _write(name, record)
    route = record.get("route")
    came = record.get("from")
    first_served(name, route if isinstance(route, str) else SETUP, came if isinstance(came, str) else None, told)
    return True
