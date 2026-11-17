"""Which release is newest: the version feed, as cad's own update reads it.

At most once an hour, a server reads the version feed (``GET /v1/versions``, ``cad_server/_internal/api.py``)::

    {"latest": "0.10.0"}

in the background (``refresh``), never waited on. It is one anonymous request: no id, no path, nothing about the
person or their machine beyond what any web request carries. ``CAD_UPDATE_CHECK=0`` turns it off, and it never runs
in CI (``CI`` set) or for a development build (``cad_server._internal.editable.development``). The feed as last read
is kept in the state folder (``versions.json``), where every process of the person's reads it: ``latest`` is the
release cad's own update moves to (``cad_server._internal.auto_update``). Nothing here updates anything, and nothing
here says anything to a person or an agent.

Nothing here ever raises or waits. Each hour's attempt is spent before it is made, so a feed that cannot be reached
is tried once an hour.
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

from cad_server._internal.api import api_url
from cad._internal.atomic_replace import write_bytes_atomic

LOG = logging.getLogger("cad_server.updates")

FILE = "versions.json"  # the feed as last read, in the state folder
CHECK_SECONDS = 60 * 60  # how old the feed may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")


def parse_release(value: Any) -> tuple[int, int, int] | None:
    """A release, a plain ``X.Y.Z``, as its three numbers; None for anything else (a development or
    pre-release version)."""
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as the server reads it: a release as ``latest`` (``None`` when there is none). Anything
    else in it is left out, so the feed can grow without a release of cad."""
    if not isinstance(data, dict) or parse_release(data.get("latest")) is None:
        return None
    return {"latest": data["latest"]}


def checking() -> bool:
    """Whether to read the feed at all: not turned off (``CAD_UPDATE_CHECK=0``), not in CI, and no development
    build."""
    if str(os.environ.get("CAD_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    from cad_server._internal.editable import development

    return not development()


def _cache() -> Path:
    """The feed's cache, in the state folder (``places.state_dir``)."""
    from cad.engine.places import state_dir

    return state_dir() / FILE


def _load(path: Path) -> dict[str, Any]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _save(path: Path, checked: float, feed: dict[str, Any] | None) -> None:
    """The file as it is read: when the feed was last asked for (``checked``) and the feed as last
    read (``feed``), and nothing else."""
    kept: dict[str, Any] = {"checked": checked, **({"feed": feed} if feed is not None else {})}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(path, json.dumps(kept, sort_keys=True).encode("utf-8"))
    except OSError:
        LOG.debug("could not keep the version feed in %s", path, exc_info=True)


def _due(kept: dict[str, Any], key: str, now: float) -> bool:
    """Whether an hour has passed since ``key`` (a clock set back counts as an hour)."""
    then = kept.get(key)
    return not isinstance(then, (int, float)) or not 0 <= now - then < CHECK_SECONDS


def _get(url: str) -> Any:
    """The feed's JSON, or ``None`` when it could not be read: offline, slow, refused, or not JSON."""
    try:
        import urllib.request

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cad"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`api_url`)
            return json.loads(response.read(MAX_BYTES))
    except Exception:  # noqa: BLE001 - a check that fails is tried again in an hour
        LOG.debug("could not read the version feed at %s", url, exc_info=True)
        return None


def feed(*, fetch: bool = True, force: bool = False, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None) -> dict[str, Any] | None:
    """The feed as last read, read again first (``fetch``) when that was an hour ago or more -- or now,
    ``force``."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and checking() and (force or _due(kept, "checked", now)):
        # The hour's attempt is spent before it is made: a process that exits mid-request, or a feed
        # that never answers, costs one wait an hour.
        _save(path, now, known)
        fresh = parse_feed((get or _get)(f"{api_url()}/versions"))
        if fresh is not None:
            known = fresh
            _save(path, now, fresh)
    return known


def _quietly() -> None:
    try:
        feed()
    except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
        LOG.debug("the version check failed", exc_info=True)


def refresh() -> threading.Thread | None:
    """Read the feed in the background when it is due, so what cad's own update reads stays current: as a server
    starts and as it tends (a server can run for days). The thread reading it, if one started."""
    try:
        if not (checking() and _due(_load(_cache()), "checked", time.time())):
            return None
        thread = threading.Thread(target=_quietly, name="cad-update-check", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - a check that cannot start is tried at the next one
        LOG.debug("the version check could not start", exc_info=True)
        return None
