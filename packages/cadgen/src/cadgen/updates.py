"""Whether a newer text-to-cad is out, and what to tell the person.

At most once a day, cadgen reads the version feed (``GET /versions``, ``cadgen/_internal/api.py``)::

    {"latest": "0.9.0"}

It is one anonymous request: no id, no path, nothing about the person or their machine beyond what
any web request carries. ``CADGEN_UPDATE_CHECK=0`` turns it off, and it never runs in CI (``CI``
set) or for a copy that is not told. The feed as last read is kept in the state directory
(``versions.json``), where every process of the person's reads it.

Only a copy nothing else updates is told (``told``: ``cadgen/_internal/channel.py``): a plugin the
person installed and updates by hand, and a process no plugin started, such as the CAD Viewer of a
skills-only install. A plugin that something else keeps up to date -- a store, once a release
passes its review, or the app that installed it -- says so in its startup command
(``--auto-updated``) and is never told; nor is a development install.

The notice is the same wherever it shows: ``A new version v0.9.0 of text-to-cad is available
(currently on v0.8.1)``, and a prompt for the person's agent worded like the install message,
``Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad``: the agent takes
the steps for its own app from there. The agent does the update; nothing here does. The CAD app's
blue update button, first in its navbar and on its home, opens a card that sends that prompt to the
chat where the host takes messages, and copies it elsewhere; the CAD Viewer's copies it. The card also
links to manual installation (``INSTRUCTIONS``, the docs site's ``/install``), should the agent not
manage. The button stays while the install is behind: nothing the person does with it is kept. A
text-only app gets the same as one line (``line``) with its first ``cad_show`` result. A skill's
``cadgen`` command says nothing: it cannot tell which plugin, if any, it came with.

None of it ever gets in the way: nothing here raises, a request waits at most
``TIMEOUT_SECONDS``, and each day's attempt is spent before it is made, so a feed that cannot be
reached costs one wait a day.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cadgen._internal.api import api_url
from cadgen._internal.atomic_replace import write_bytes_atomic
from cadgen._internal.channel import told

LOG = logging.getLogger("cadgen.updates")

REPOSITORY = "https://github.com/earthtojake/text-to-cad"  # where the install message sends the agent too
INSTRUCTIONS = "https://www.texttocad.dev/install"  # the full install instructions: the docs site's Install section
FILE = "versions.json"  # the feed as last read, in the state directory
CHECK_SECONDS = 24 * 60 * 60  # how old the feed may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")


def _release(value: Any) -> tuple[int, ...] | None:
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as cadgen reads it: a release as ``latest`` (``None`` when there is none). Anything
    else in it is left out, so the feed can grow without a release of cadgen."""
    if not isinstance(data, dict) or _release(data.get("latest")) is None:
        return None
    return {"latest": data["latest"]}


def checking() -> bool:
    """Whether to check at all: not turned off (``CADGEN_UPDATE_CHECK=0``), not in CI, and a copy
    that is told -- not one something else keeps up to date, nor a development install."""
    if str(os.environ.get("CADGEN_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    return told()


def _cache() -> Path:
    from cadgen.viewer.recents import state_dir  # noqa: PLC0415 -- the state directory's one definition

    return state_dir() / FILE


def _load(path: Path) -> dict[str, Any]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _save(path: Path, kept: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, json.dumps(kept, sort_keys=True).encode("utf-8"))
    except OSError:
        LOG.debug("could not keep the version feed in %s", path, exc_info=True)


def _due(kept: dict[str, Any], key: str, now: float) -> bool:
    """Whether a day has passed since ``key`` (a clock set back counts as a day)."""
    then = kept.get(key)
    return not isinstance(then, (int, float)) or not 0 <= now - then < CHECK_SECONDS


def _get(url: str) -> Any:
    """The feed's JSON, or ``None`` when it could not be read: offline, slow, refused, or not JSON."""
    try:
        import urllib.request

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cadgen"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`api_url`)
            return json.loads(response.read(MAX_BYTES))
    except Exception:  # noqa: BLE001 - a check that fails is tried again tomorrow
        LOG.debug("could not read the version feed at %s", url, exc_info=True)
        return None


def feed(*, fetch: bool = True, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None) -> dict[str, Any] | None:
    """The feed as last read, read again first (``fetch``) when that was a day ago or more."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and checking() and _due(kept, "checked", now):
        # The day's attempt is spent before it is made: a process that exits mid-request, or a feed
        # that never answers, costs one wait a day.
        _save(path, {**kept, "checked": now})
        fresh = parse_feed((get or _get)(f"{api_url()}/versions"))
        if fresh is not None:
            known = fresh
            _save(path, {**_load(path), "checked": now, "feed": fresh})
    return known


def offer(found: dict[str, Any] | None, version: str, told: bool) -> str | None:
    """The release to offer an install of ``version`` that is ``told`` or not, if any (see the module docstring)."""
    if found is None or not told:
        return None
    current, latest = _release(version), _release(found["latest"])
    if current is None or latest is None or current >= latest:
        return None
    return found["latest"]


def notice(*, fetch: bool = True, now: float | None = None, path: Path | None = None,
           get: Callable[[str], Any] | None = None) -> dict[str, str] | None:
    """``{latest, version, text, prompt, instructions}``: what to tell the person, or ``None`` when
    there is nothing to say, or no checking."""
    try:
        if not checking():
            return None
        from cadgen import __version__

        latest = offer(feed(fetch=fetch, now=now, path=path, get=get), __version__, told())
        if latest is None:
            return None
        return {"latest": latest, "version": __version__,
                "text": f"A new version v{latest} of text-to-cad is available (currently on v{__version__})",
                "prompt": f"Update text-to-cad to {latest} from {REPOSITORY}", "instructions": INSTRUCTIONS}
    except Exception:  # noqa: BLE001 - a notice never fails what shows it
        LOG.debug("the version check failed", exc_info=True)
        return None


def line(found: dict[str, str]) -> str:
    """The notice as one line of text, for an agent to pass on: the card's words, its prompt and its
    link in place of its buttons."""
    return (f'{found["text"]}. Ask your agent to update to the latest version ("{found["prompt"]}"), '
            f'or install manually ({found["instructions"]}).')


def _quietly() -> None:
    try:
        feed()
    except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
        LOG.debug("the version check failed", exc_info=True)


def refresh() -> None:
    """A server's start: read the feed in the background when it is due, so what it tells is current."""
    if checking():
        threading.Thread(target=_quietly, name="cadgen-update-check", daemon=True).start()

