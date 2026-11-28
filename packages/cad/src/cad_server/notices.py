"""The project's notices: a line of words, and a link where there is one, that the project posts for every cad older
than a release (``/v1/notices``, read beside PyPI; checked again by ``updates.parse_notices``; posted without a
release, apps/api's README, "Posting a notice"), for
the computers a release cannot bring along. Read from what was last read (``updates.feed``, never fetched here), each
checked again, and only where this cad reads them at all (``updates.checking``: never with ``CAD_UPDATE_CHECK=0``,
in CI or for a development build, whose kept feed would never hear a notice taken down). Shown whatever automatic
updates are set to: a notice is the project's word to everyone it is for.

Three places say them, and with none posted, none says anything: a ``cad`` command, after its own output, one line on
stderr per notice at most once a day (``lines``, ``cad_server.cli``); ``cad doctor``, a line of its report each
(``applying``); and the viewer, a card each until the person dismisses it (``GET /api/v1/server``'s ``cadNotices``,
``for_viewer``). A notice is only ever shown as text: nothing in it is run.

Nothing here raises.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

LOG = logging.getLogger("cad_server.notices")

# In the state folder: when a command last said each notice, by its id. A file of its own, which no release before
# notices reads.
FILE = "notices.json"
DAY = 86400.0  # how long after a command said a notice the next one may say it again


def applying() -> list[dict[str, str]]:
    """The notices for this cad, as the feed as last read carries them (``updates.notices_for``): ``{"id", "below",
    "text", "url"?}`` each, in the feed's order. None where this cad reads no feed (``updates.checking``), or where
    anything fails."""
    try:
        from cad_server import __version__, updates

        if not updates.checking():
            return []
        return updates.notices_for(__version__, updates.feed(fetch=False))
    except Exception:  # noqa: BLE001 - a notice never fails what it rides on
        LOG.debug("could not read the notices", exc_info=True)
        return []


def said(notice: dict[str, str]) -> str:
    """A notice in words: its text, and its link in brackets where it has one."""
    return notice["text"] + (f" ({notice['url']})" if notice.get("url") else "")


def for_viewer() -> list[dict[str, str]]:
    """The notices for this cad as the viewer shows them (``GET /api/v1/server``'s ``cadNotices``): ``{"id", "text",
    "url"?}`` each; ``[]`` where there is none."""
    return [{key: notice[key] for key in ("id", "text", "url") if key in notice} for notice in applying()]


def lines(now: float | None = None, path: Path | None = None) -> list[str]:
    """The lines a ``cad`` command says on stderr after its own output: ``cad: <text>``, and `` (<url>)`` where there is
    one, for each notice that applies (``applying``) and that no command said within a ``DAY`` (a clock set back counts
    as long ago). Noted as said in ``FILE`` before they are said, the file written whole, keeping only the notices
    that still apply: a file that cannot be written says nothing, so a notice can never be said on every command.
    Never raises."""
    try:
        found = applying()
        if not found:
            return []
        now = time.time() if now is None else now
        if path is None:
            from cad.engine.places import state_dir

            path = state_dir() / FILE
        try:
            kept = json.loads(path.read_text(encoding="utf-8")).get("said")
        except (OSError, ValueError, AttributeError):
            kept = None
        kept = kept if isinstance(kept, dict) else {}
        last = {notice["id"]: kept.get(notice["id"]) for notice in found}
        due = [notice for notice in found if not (_time(last[notice["id"]]) and 0 <= now - last[notice["id"]] < DAY)]
        if not due:
            return []
        record = {key: value for key, value in last.items() if _time(value)}
        record.update((notice["id"], now) for notice in due)
        from cad._internal.atomic_replace import write_bytes_atomic

        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, json.dumps({"said": record}, sort_keys=True).encode("utf-8"))
        return [f"cad: {said(notice)}" for notice in due]
    except Exception:  # noqa: BLE001 - a line never fails the command it follows, and one not kept is not said
        LOG.debug("could not say the notices", exc_info=True)
        return []


def _time(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
