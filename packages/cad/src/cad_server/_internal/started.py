"""The releases this computer's server started as: ``started.json`` in the state folder, the release it last
started as (``release``) and the release before that one (``before``), written by the server as it starts (``note``)
and read by what needs the release the computer had before (``read``), the command that goes back to it."""

from __future__ import annotations

import json
from typing import Any

FILE = "started.json"


def read() -> dict[str, Any]:
    """The record, ``{"release", "before"}``; ``{}`` where there is none."""
    from cad.engine.places import state_dir

    try:
        found = json.loads((state_dir() / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def note(release: str) -> None:
    """``release`` written as the one the server last started as, where the record names another, which it keeps
    as ``before``. Never a reason a server does not start: a state folder it cannot write is left as it is."""
    from cad._internal.atomic_replace import write_bytes_atomic
    from cad.engine.places import state_dir

    found = read().get("release")
    if found == release:
        return
    try:
        path = state_dir() / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, (json.dumps({"release": release, "before": found}) + "\n").encode("utf-8"))
    except OSError:
        pass
