"""Whether a newer text-to-cad is out: the version check.

At most once an hour, a server reads the version feed (``GET /v1/versions``, ``cad_server/_internal/api.py``)::

    {"latest": "0.10.0"}

in the background (``refresh``), never waited on. It is one anonymous request: no id, no path, nothing about the
person or their machine beyond what any web request carries. ``CAD_UPDATE_CHECK=0`` turns it off, and it never runs
in CI (``CI`` set) or for a copy that is not told (``cad_server/_internal/channel.py``). The feed as last read is
kept in the data folder (``versions.json``), where every process of the person's reads it: ``latest`` says the
newest release the last check saw, and ``notice`` whether it is newer than this one. Nothing here updates anything:
text-to-cad is updated by its install command (``INSTALL``, ``INSTALL_WINDOWS``; ``command`` picks this computer's).

A release is also known with no network at all: an MCP client running a newer release's server says its release as
it connects (``see``), and that proves the release exists.

Nothing here ever raises or waits: what is told comes from the feed as last read. Each hour's attempt is spent
before it is made, so a feed that cannot be reached is tried once an hour.
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
from cad_server._internal.channel import told

LOG = logging.getLogger("cad_server.updates")

INSTALL = "curl -fsSL https://texttocad.dev/install.sh | sh"  # installs or updates text-to-cad: macOS and Linux
INSTALL_WINDOWS = "irm https://www.texttocad.dev/install.ps1 | iex"  # the same, in Windows PowerShell
FILE = "versions.json"  # the feed as last read, in the data folder
CHECK_SECONDS = 60 * 60  # how old the feed may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")
# The releases connecting MCP clients' servers said they run as they connected to this process's engine (``see``).
_seen: set[str] = set()
_seen_lock = threading.Lock()


def parse_release(value: Any) -> tuple[int, int, int] | None:
    """A release, a plain ``X.Y.Z``, as its three numbers; None for anything else (a development or
    pre-release version)."""
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as the server reads it: a release as ``latest`` (``None`` when there is none). Anything
    else in it is left out, so the feed can grow without a release of text-to-cad."""
    if not isinstance(data, dict) or parse_release(data.get("latest")) is None:
        return None
    return {"latest": data["latest"]}


def checking() -> bool:
    """Whether to read the feed at all: not turned off (``CAD_UPDATE_CHECK=0``), not in CI, and a copy that is
    told -- not one something else keeps up to date, nor a development install."""
    if str(os.environ.get("CAD_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    return told()


def _cache() -> Path:
    """The feed's cache, in this process's data folder (``places.data_dir``)."""
    from cad.engine.places import data_dir

    return data_dir() / FILE


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

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cadgen"})
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


def see(release: Any) -> None:
    """A release a connecting MCP client's server runs, as it said when it connected: one newer than this
    install proves a release exists, with no network."""
    if parse_release(release) is not None:
        with _seen_lock:
            _seen.add(release)


def _newest(candidates: list[Any], version: str) -> str | None:
    """The newest of ``candidates`` that is newer than ``version``, or None."""
    current = parse_release(version)
    found = [(parse_release(value), value) for value in candidates if parse_release(value) is not None]
    newer = [(parsed, value) for parsed, value in found if current is not None and parsed > current]
    return max(newer)[1] if newer else None


def command(system: str | None = None) -> str:
    """The install command for this computer (or for ``system``, an ``os.name``), which installs or updates
    text-to-cad."""
    return INSTALL_WINDOWS if (system or os.name) == "nt" else INSTALL


def notice(*, path: Path | None = None) -> dict[str, str] | None:
    """``{latest, version}``: a release newer than this one, from the feed as last read (never read here:
    ``refresh``) and the releases connecting servers run (``see``), where this process is told (``told``); or
    ``None`` when there is none, or it is not told."""
    try:
        from cad_server import __version__

        if not told():
            return None
        with _seen_lock:
            candidates: list[Any] = [*_seen]
        if checking():
            known = feed(fetch=False, path=path)
            if known is not None:
                candidates.append(known["latest"])
        latest = _newest(candidates, __version__)
        if latest is None:
            return None
        return {"latest": latest, "version": __version__}
    except Exception:  # noqa: BLE001 - a notice never fails what shows it
        LOG.debug("the version check failed", exc_info=True)
        return None


def latest(*, path: Path | None = None) -> str | None:
    """The latest release the last check saw (the feed as last read, never read here), or None: none read yet, the
    check turned off, or a feed that named none."""
    try:
        if not checking():
            return None
        known = feed(fetch=False, path=path)
        return known["latest"] if known is not None else None
    except Exception:  # noqa: BLE001 - a fact for a notice, never a failure
        LOG.debug("the version check failed", exc_info=True)
        return None


def line(found: dict[str, str], system: str | None = None) -> str:
    """The notice as text: the two lines a newer release is said in, with the install command that updates to
    it."""
    return (f"A new release of text-to-cad is available: {found['version']} -> {found['latest']}\n"
            f"To update, run: {command(system)}")


def _quietly() -> None:
    try:
        feed()
    except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
        LOG.debug("the version check failed", exc_info=True)


def refresh() -> threading.Thread | None:
    """Read the feed in the background when it is due, so what is told stays current: as a server
    starts, and as a page asks (a server can run for days). The thread reading it, if one started."""
    try:
        if not (checking() and _due(_load(_cache()), "checked", time.time())):
            return None
        thread = threading.Thread(target=_quietly, name="cad-update-check", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - a check that cannot start is tried at the next one
        LOG.debug("the version check could not start", exc_info=True)
        return None
