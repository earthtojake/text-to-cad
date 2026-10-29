"""Whether a newer text-to-cad is out, and what to tell the person.

At most once an hour, cadgen reads the version feed (``GET /versions``, ``cadgen/_internal/api.py``)::

    {"latest": "0.9.0"}

It is one anonymous request: no id, no path, nothing about the person or their machine beyond what
any web request carries. ``CADGEN_UPDATE_CHECK=0`` turns it off, and with it the self-update, and
neither runs in CI (``CI`` set) (``switched_on``). The feed as last read is kept in the state
directory (``versions.json``), where every process of the person's reads it. A copy that is not
told reads it only for the self-update.

Only a copy nothing else updates is told (``told``: ``cadgen/_internal/channel.py``): a plugin the
person installed and updates by hand, and a process no plugin started, such as the CAD Viewer of a
skills-only install. A plugin that something else keeps up to date -- a store, once a release
passes its review, or the app that installed it -- says so in its startup config
(``CADGEN_AUTO_UPDATED=1``) and is never told; nor is a development install.

The update is the install command run again (``INSTALL``, ``INSTALL_WINDOWS``): it updates cadgen
and text-to-cad in every agent app on the computer. Where the install command set the computer up,
the engine runs it itself, within the hour of a release (``cadgen._internal.auto_update``); anywhere
else the person, or their agent, does. The notice is the same wherever it shows: ``A new version
v0.9.0 of text-to-cad is available (currently on v0.8.1)``, the command for this computer
(``command``), and a prompt that has the person's agent run it, ``Run `curl -fsSL
https://texttocad.dev/install.sh | sh` to update text-to-cad to 0.9.0 (on Windows: `irm
https://www.texttocad.dev/install.ps1 | iex`)``. Where the engine updates the computer itself, the
notice says where that stands instead (``auto``: pending, updating -- downloading or installing --,
or failed, ``_AUTO``), and the card can start it at once, as its Try again does after a failure
(``POST /__cad/update``, ``auto_update.run_now``). Once it is installed there is no notice at all:
the next session an agent app starts runs it, and the engine steps aside for it by itself
(``cadgen._internal.installations``, ``cadgen.engine.daemon``'s ``supersede``); ``cadgen doctor``
says it is installed.
The CAD app's blue update button, first in its navbar and on its home, opens a card that shows
the command to copy and sends the prompt to the chat where the host takes messages; the CAD Viewer's
copies the command. The card also links to the install instructions (``INSTRUCTIONS``, the docs
site's ``/install``), which lead to installing by hand. The button stays while the install is behind:
nothing the person does with it is kept. A text-only app gets the same as one line (``line``) with its
first ``cad_show`` result; an update pending or installing itself is no agent's business, and says
nothing there. A skill's ``cadgen`` command says nothing: it cannot tell which plugin, if
any, it came with.

None of it ever gets in the way, online or off: nothing here raises, and the feed is read only in
the background (``refresh``), so no start, request or tool call waits on it -- what is told comes
from the feed as last read. Each hour's attempt is spent before it is made, so a feed that cannot be
reached is tried once an hour.
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

INSTALL = "curl -fsSL https://texttocad.dev/install.sh | sh"  # installs or updates text-to-cad: macOS and Linux
INSTALL_WINDOWS = "irm https://www.texttocad.dev/install.ps1 | iex"  # the same, in Windows PowerShell
INSTRUCTIONS = "https://www.texttocad.dev/install"  # the install instructions: the install box on the docs site's homepage
FILE = "versions.json"  # the feed as last read, in the state directory
CHECK_SECONDS = 60 * 60  # how old the feed may get before it is read again
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


def switched_on() -> bool:
    """The one switch, for the check and the self-update alike: not turned off
    (``CADGEN_UPDATE_CHECK=0``), and not in CI."""
    if str(os.environ.get("CADGEN_UPDATE_CHECK") or "").strip().lower() in _OFF:
        return False
    return str(os.environ.get("CI") or "").strip().lower() in ("", *_OFF)


def checking() -> bool:
    """Whether to check for the notice: switched on (``switched_on``), and a copy that is told -- not
    one something else keeps up to date, nor a development install."""
    return switched_on() and told()


def _cache() -> Path:
    from cadgen.viewer.recents import state_dir  # noqa: PLC0415 -- the state directory's one definition

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


def _due(kept: dict[str, Any], key: str, now: float, fresh: float = CHECK_SECONDS) -> bool:
    """Whether ``fresh`` seconds (an hour) have passed since ``key`` (a clock set back counts as that)."""
    then = kept.get(key)
    return not isinstance(then, (int, float)) or not 0 <= now - then < fresh


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


def feed(*, fetch: bool = True, now: float | None = None, path: Path | None = None,
         get: Callable[[str], Any] | None = None, updating: bool = False,
         fresh: float = CHECK_SECONDS) -> dict[str, Any] | None:
    """The feed as last read, read again first (``fetch``) when that was ``fresh`` seconds ago or more
    (an hour; the update a person starts asks for a minute): for a copy that is told, or for the
    self-update (``updating``), which reads it whether or not this process is told, since it keeps the
    install command's copies current, never the one that started it."""
    path = path or _cache()
    kept = _load(path)
    known = parse_feed(kept.get("feed"))
    now = time.time() if now is None else now
    if fetch and (switched_on() if updating else checking()) and _due(kept, "checked", now, fresh):
        # The hour's attempt is spent before it is made: a process that exits mid-request, or a feed
        # that never answers, costs one wait an hour.
        _save(path, now, known)
        fresh = parse_feed((get or _get)(f"{api_url()}/versions"))
        if fresh is not None:
            known = fresh
            _save(path, now, fresh)
    return known


def command(system: str | None = None) -> str:
    """The install command for this computer (or for ``system``, an ``os.name``), which updates
    text-to-cad when run again."""
    return INSTALL_WINDOWS if (system or os.name) == "nt" else INSTALL


def offer(found: dict[str, Any] | None, version: str, told: bool) -> str | None:
    """The release to offer an install of ``version`` that is ``told`` or not, if any (see the module docstring)."""
    if found is None or not told:
        return None
    current, latest = _release(version), _release(found["latest"])
    if current is None or latest is None or current >= latest:
        return None
    return found["latest"]


# What the notice says where the engine updates the computer itself, by the state of that update
# (``cadgen._internal.auto_update.status``): the release concerned, this process's version and the
# failure's words. An installed one says nothing. A line (``line``) says the command after a failure's.
_AUTO = {
    "updating": "text-to-cad v{release} is installing itself.",
    "failed": "text-to-cad v{release} could not install itself ({error}).",
    "pending": "A new version v{release} of text-to-cad is available (currently on v{version}); it installs "
               "itself within the hour.",
}


def _said(release: str, version: str, text: str) -> dict[str, Any]:
    return {"latest": release, "version": version, "text": text, "command": command(),
            "prompt": f"Run `{INSTALL}` to update text-to-cad to {release} (on Windows: `{INSTALL_WINDOWS}`)",
            "instructions": INSTRUCTIONS}


def notice(*, path: Path | None = None) -> dict[str, Any] | None:
    """``{latest, version, text, command, prompt, instructions}``: what to tell the person, from the
    feed as last read (never read here: ``refresh``), or ``None`` when there is nothing to say, or no
    checking. Where the engine updates the computer itself (``cadgen._internal.auto_update.wanted``),
    ``auto`` is added, ``{state, release}`` with an update's ``stage`` (``downloading``,
    ``installing``) and a failure's ``error``, ``latest`` is the release concerned, and the text is
    that state's (``_AUTO``); an update installed says nothing (``None``): new sessions run it, and
    nobody needs to do anything. Anywhere else there is no ``auto``."""
    try:
        if not checking():
            return None
        from cadgen import __version__
        from cadgen._internal import auto_update

        found = feed(fetch=False, path=path)
        auto = auto_update.status(latest=found["latest"] if found else None, version=__version__)
        if auto is not None:
            if auto["state"] == "updated":
                return None
            text = _AUTO[auto["state"]].format(version=__version__, **auto)
            return {**_said(auto["release"], __version__, text), "auto": auto}
        latest = offer(found, __version__, told())
        if latest is None:
            return None
        return _said(latest, __version__, f"A new version v{latest} of text-to-cad is available (currently on v{__version__})")
    except Exception:  # noqa: BLE001 - a notice never fails what shows it
        LOG.debug("the version check failed", exc_info=True)
        return None


def line(found: dict[str, Any]) -> str | None:
    """The notice as one line of text, for an agent to pass on: the card's words, its command and its
    link in place of its buttons; nothing (``None``) for an update pending or installing itself,
    which asks nothing of anyone."""
    auto = found.get("auto") or {}
    if auto.get("state") in ("pending", "updating"):
        return None
    return (f'{found["text"].rstrip(".")}. Update with this command: `{found["command"]}`, '
            f'or install manually ({found["instructions"]}).')


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
        thread = threading.Thread(target=_quietly, name="cadgen-update-check", daemon=True)
        thread.start()
        return thread
    except Exception:  # noqa: BLE001 - a check that cannot start is tried at the next one
        LOG.debug("the version check could not start", exc_info=True)
        return None

