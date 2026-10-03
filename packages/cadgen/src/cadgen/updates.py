"""Whether a newer text-to-cad is out, and what to tell the person.

At most once a day, cadgen reads the version feed (``GET /versions``, ``cadgen/_internal/api.py``)::

    {"latest": "0.9.0", "minimum": {"claude-directory": "0.8.2"}}

It is one anonymous request: no id, no path, nothing about the person or their machine beyond what
any web request carries. ``CADGEN_UPDATE_CHECK=0`` turns it off, and it never runs in CI (``CI``
set) or for a development install. The feed as last read is kept in the state directory
(``versions.json``), where every process of the person's reads it.

What it offers depends on where the install came from (its channel, ``cadgen/_internal/channel.py``):

- a development install: nothing, ever;
- a store's copy (any channel its package named but ``github``): nothing while it is at or above
  that store's ``minimum`` -- the store updates it once a release passes its review -- and
  ``latest`` once it falls below; a store the feed names no minimum for is never told;
- installed from GitHub, or a channel nothing named: ``latest``, whenever it is behind.

The notice is the same wherever it shows: ``text-to-cad 0.9.0 is available (you have 0.8.1)``, and
a prompt for the person's agent worded like the install message, ``Update text-to-cad to 0.9.0 from
https://github.com/earthtojake/text-to-cad``: the agent takes the steps for its own app from there. The agent does the update; nothing here does.
The CAD app's card sends that prompt to the chat where the host takes messages, and copies it
elsewhere; the CAD Viewer's card copies it. A text-only app gets the line with its first
``cad_show`` result, and a ``cadgen`` command prints it on stderr, at most once a day.

The person's answer to a card -- they sent, copied or closed it -- is kept as theirs (the
``updates`` section of ``settings.json``, ``cadgen/settings.py``): that release is not offered
again, anywhere. The next one is.

None of it ever gets in the way: nothing here raises, a request waits at most
``TIMEOUT_SECONDS``, and each day's attempt is spent before it is made, so a feed that cannot be
reached costs one wait a day, never one per command.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from cadgen._internal.api import api_url
from cadgen._internal.atomic_replace import write_bytes_atomic
from cadgen._internal.channel import DEV, channel, is_channel, is_store
from cadgen.settings import read_section, settings_path, update_section

LOG = logging.getLogger("cadgen.updates")

REPOSITORY = "https://github.com/earthtojake/text-to-cad"  # where the install message sends the agent too
FILE = "versions.json"  # the feed as last read, in the state directory
SECTION = "updates"  # the person's answers to the card, in settings.json
CHECK_SECONDS = 24 * 60 * 60  # how old the feed may get before it is read again; the CLI's line, how often
TIMEOUT_SECONDS = 5
WAIT_SECONDS = 2  # the most a command's end waits for a check it started
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")


def _release(value: Any) -> tuple[int, ...] | None:
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as cadgen reads it: a release as ``latest``, and a release per store channel as its
    ``minimum`` (``None`` when there is no ``latest``). Anything else in it is left out, so the
    feed can grow without a release of cadgen."""
    if not isinstance(data, dict) or _release(data.get("latest")) is None:
        return None
    minimum = data.get("minimum") if isinstance(data.get("minimum"), dict) else {}
    return {"latest": data["latest"],
            "minimum": {store: value for store, value in minimum.items()
                        if is_channel(store) and is_store(store) and _release(value)}}


def checking() -> bool:
    """Whether to check at all: not turned off (``CADGEN_UPDATE_CHECK=0``), not in CI, not a development install."""
    if str(os.environ.get("CADGEN_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    return channel() != DEV


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


def offer(found: dict[str, Any] | None, version: str, where: str) -> str | None:
    """The release to offer an install of ``version`` from channel ``where``, if any (see the module docstring)."""
    if found is None or where == DEV:
        return None
    current, latest = _release(version), _release(found["latest"])
    if current is None or latest is None or current >= latest:
        return None
    if is_store(where):
        floor = _release(found["minimum"].get(where))
        if floor is None or current >= floor:
            return None
    return found["latest"]


def notice(*, fetch: bool = True, now: float | None = None, path: Path | None = None,
           settings: Path | None = None, get: Callable[[str], Any] | None = None) -> dict[str, str] | None:
    """``{latest, version, text, prompt}``: what to tell the person, or ``None`` when there is
    nothing to say -- or no checking, or the person set that release aside."""
    try:
        if not checking():
            return None
        from cadgen import __version__

        where = channel()
        latest = offer(feed(fetch=fetch, now=now, path=path, get=get), __version__, where)
        if latest is None or _dismissed(settings) == latest:
            return None
        return {"latest": latest, "version": __version__,
                "text": f"text-to-cad {latest} is available (you have {__version__})",
                "prompt": f"Update text-to-cad to {latest} from {REPOSITORY}"}
    except Exception:  # noqa: BLE001 - a notice never fails what shows it
        LOG.debug("the version check failed", exc_info=True)
        return None


def line(found: dict[str, str]) -> str:
    """The notice as one line of text, for an agent to pass on."""
    return f'{found["text"]}. To update, ask your agent: "{found["prompt"]}"'


def dismiss(version: Any, *, settings: Path | None = None) -> bool:
    """The person sent, copied or closed the card for ``version``: it is not offered again. Whether that was kept."""
    if _release(version) is None:
        return False
    try:
        update_section(SECTION, lambda section: {**section, "dismissed": version}, path=settings or settings_path())
    except OSError:
        LOG.debug("could not keep the update card's answer", exc_info=True)
        return False
    return True


def _dismissed(settings: Path | None) -> Any:
    try:
        return read_section(SECTION, path=settings or settings_path()).get("dismissed")
    except OSError:
        return None


def _quietly() -> None:
    try:
        feed()
    except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
        LOG.debug("the version check failed", exc_info=True)


def refresh() -> None:
    """A server's start: read the feed in the background when it is due, so what it tells is current."""
    if checking():
        threading.Thread(target=_quietly, name="cadgen-update-check", daemon=True).start()


def begin() -> threading.Thread | None:
    """A ``cadgen`` command's start: when the feed is due, read it beside the command, not before it."""
    try:
        if not checking() or not _due(_load(_cache()), "checked", time.time()):
            return None
    except Exception:  # noqa: BLE001
        LOG.debug("the version check failed", exc_info=True)
        return None
    check = threading.Thread(target=_quietly, name="cadgen-update-check", daemon=True)
    check.start()
    return check


def end(check: threading.Thread | None, *, stream: TextIO | None = None, now: float | None = None) -> None:
    """A ``cadgen`` command's end: the notice on stderr, at most once a day. A check the command
    started gets ``WAIT_SECONDS`` more, and is left behind after that."""
    try:
        if check is not None:
            check.join(WAIT_SECONDS)
        found = notice(fetch=False)
        if found is None:
            return
        path, now = _cache(), time.time() if now is None else now
        kept = _load(path)
        if not _due(kept, "told", now):
            return
        _save(path, {**kept, "told": now})
        (stream or sys.stderr).write(line(found) + "\n")
    except Exception:  # noqa: BLE001 - the command's own outcome stands
        LOG.debug("could not tell the version check's notice", exc_info=True)
