"""Whether a newer text-to-cad is out, which the update button says, and which release an update moves to.

At most once an hour, the server reads the version feed (``GET /v1/versions``, ``cad_server/_internal/api.py``)::

    {"latest": "0.10.0"}

It is one anonymous request: no id, no path, nothing about the person or their machine beyond what
any web request carries. ``CAD_UPDATE_CHECK=0`` turns it off, and it never runs in CI (``CI``
set) or for a copy that is not told. The feed as last read is kept in the state directory
(``versions.json``), where every process of the person's reads it. It only says a release is out:
nothing is fetched and nothing switches until the person asks -- the update button in the CAD Viewer
and the CAD app (``cad_server._internal.update``), ``cad update``, or the install command run again.

A release is also known with no network at all: an agent app whose plugin moved ahead runs the newer
release's CAD server, which says its release as it connects (``see``), and that proves the release
exists. The newer of the two is offered.

Only a copy nothing else updates is told of the feed's release (``told``: ``cad_server/_internal/channel.py``):
a plugin the person installed and updates by hand, and a process no plugin started, such as the CAD
Viewer of a skills-only install. A plugin that something else keeps up to date -- a store, once a
release passes its review -- says so in its startup config (``CAD_AUTO_UPDATED=1``) and is never
told of it; nor is a development install. A newer server's release is offered to every copy but a
development install: the store moved the plugin, and the device's engine is still behind it. An
update a person asks for reads the feed whatever the copy (``checking(asked=True)``).

The notice is ``{latest, version}``: the CAD Viewer's and the CAD app's update button, an icon and
nothing else, while this install is behind; a click updates (``POST /api/v1/local/update``). A text-only app
gets one line (``line``) with its first ``cad_show`` result: the release, and the install command
(``INSTALL``, ``INSTALL_WINDOWS``; ``command`` picks this computer's), which updates text-to-cad in
every agent app on the computer (``cad setup``). A skill's ``cad`` command says nothing.

None of it ever gets in the way, online or off: nothing here raises, and the feed is read only in
the background (``refresh``) or for the update a person asked for (``newest``), so no start, request
or tool call waits on it -- what is told comes from the feed as last read. Each hour's attempt is
spent before it is made, so a feed that cannot be reached is tried once an hour.
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
FILE = "versions.json"  # the feed as last read, in the state directory
CHECK_SECONDS = 60 * 60  # how old the feed may get before it is read again
TIMEOUT_SECONDS = 5
MAX_BYTES = 64 * 1024  # a feed is a few dozen bytes
_RELEASE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_OFF = ("0", "off", "false", "no")
# The releases agent apps' CAD servers said they run as they connected to this process's engine (``see``).
_seen: set[str] = set()
_seen_lock = threading.Lock()


def _release(value: Any) -> tuple[int, ...] | None:
    match = _RELEASE.fullmatch(value) if isinstance(value, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def parse_feed(data: Any) -> dict[str, Any] | None:
    """The feed as the server reads it: a release as ``latest`` (``None`` when there is none). Anything
    else in it is left out, so the feed can grow without a release of text-to-cad."""
    if not isinstance(data, dict) or _release(data.get("latest")) is None:
        return None
    return {"latest": data["latest"]}


def checking(*, asked: bool = False) -> bool:
    """Whether to read the feed at all: not turned off (``CAD_UPDATE_CHECK=0``), not in CI, and a copy
    that is told -- not one something else keeps up to date, nor a development install -- unless a
    person ``asked`` for an update (the update button, ``cad update``), which reads it whatever the
    copy."""
    if str(os.environ.get("CAD_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    if str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF):
        return False
    return asked or told()


def _cache() -> Path:
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

        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cadgen"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`api_url`)
            return json.loads(response.read(MAX_BYTES))
    except Exception:  # noqa: BLE001 - a check that fails is tried again in an hour
        LOG.debug("could not read the version feed at %s", url, exc_info=True)
        return None


def feed(*, fetch: bool = True, force: bool = False, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None, asked: bool = False) -> dict[str, Any] | None:
    """The feed as last read, read again first (``fetch``) when that was an hour ago or more -- or now,
    ``force``: an update a person ``asked`` for."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and checking(asked=asked) and (force or _due(kept, "checked", now)):
        # The hour's attempt is spent before it is made: a process that exits mid-request, or a feed
        # that never answers, costs one wait an hour.
        _save(path, now, known)
        fresh = parse_feed((get or _get)(f"{api_url()}/versions"))
        if fresh is not None:
            known = fresh
            _save(path, now, fresh)
    return known


def see(release: Any) -> None:
    """A release an agent app's CAD server runs, as it said when it connected: one newer than this
    install proves a release exists, and the update button shows it, with no network."""
    if _release(release) is not None:
        with _seen_lock:
            _seen.add(release)


def _newest(candidates: list[Any], version: str) -> str | None:
    """The newest of ``candidates`` that is newer than ``version``, or None."""
    current = _release(version)
    found = [(_release(value), value) for value in candidates if _release(value) is not None]
    newer = [(parsed, value) for parsed, value in found if current is not None and parsed > current]
    return max(newer)[1] if newer else None


def newest(*, fetch: bool = True) -> str | None:
    """The release an update a person asked for moves to: the newest of the feed's -- read now
    (``fetch``) unless checking is off -- and those agent apps' servers run (``see``), when it is newer
    than this install's; else None."""
    from cad_server import __version__

    try:
        found = feed(fetch=fetch, force=True, asked=True)
    except Exception:  # noqa: BLE001 - an update that cannot read the feed goes by what it knows
        found = None
    with _seen_lock:
        candidates: list[Any] = [*_seen]
    if found is not None and checking(asked=True):
        candidates.append(found["latest"])
    return _newest(candidates, __version__)


def command(system: str | None = None) -> str:
    """The install command for this computer (or for ``system``, an ``os.name``), which updates
    text-to-cad when run again (``cad setup``, ``cad_server.cli.setup``)."""
    return INSTALL_WINDOWS if (system or os.name) == "nt" else INSTALL


def offer(found: dict[str, Any] | None, version: str, told: bool) -> str | None:
    """The release to offer an install of ``version`` that is ``told`` or not, if any (see the module)."""
    if found is None or not told:
        return None
    return _newest([found["latest"]], version)


def notice(*, path: Path | None = None) -> dict[str, str] | None:
    """``{latest, version}``: the newer release the update button offers, from the feed as last read
    (never read here: ``refresh``) where this copy is told, and the releases agent apps' servers run
    (``see``) for any copy but a development install; or ``None`` when there is none."""
    try:
        from cad_server import __version__
        from cad_server._internal.channel import DEV, channel

        if channel() == DEV:
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


def line(found: dict[str, str], system: str | None = None) -> str:
    """The notice as one line of text, for a text-only app's agent to pass on: the release, and the
    install command that updates to it."""
    return (f"text-to-cad {found['latest']} is out (this is {found['version']}); to update every agent app "
            f"here, run: {command(system)}")


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
