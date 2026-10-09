"""Where this install of text-to-cad came from: its channel, and whether something keeps it up to date.

Each plugin says both in its CAD server's startup config, as the server's environment:
``CADGEN_INSTALL_CHANNEL=<id>``, plus ``CADGEN_AUTO_UPDATED=1`` when something other than the person
keeps that copy up to date (the store that reviewed it, or the app that installed it). The build
that makes the plugin writes them; nothing works them out from folders, ids or a host's
internals. The CAD Viewer the server starts inherits them. They are environment, not flags,
because a plugin's config pins a release of cadgen that may predate a setting: a cadgen ignores an
environment variable it does not know, where a flag it does not know would stop the server.

Only the server hears it, though, and most of CAD's work is not the server's: a skill's ``cadgen``
command, a model script, the CAD Viewer a skill opens and the build daemon run with nothing a plugin
set. So the server writes its channel down for its installation (``remember``): uv keeps one
installation per requirement, and the plugin's server and its skills run the same requirement, so
the same installation -- the one the build daemon is named after. Any process of that installation
that was not told a channel itself reports the one written down (``recorded``), re-read with each
batch, as the build daemon outlives the server that wrote it. The build daemon serves every caller
of its installation, so it takes no channel from whichever process started it, only the one written
down (``cadgen.daemon.client``). Where two plugins pin the same release on one machine they share an
installation, and the server that started last is the one written down: the app most likely in use.
The CAD server itself never reads it: a server its plugin did not name is configured by hand, and says
so as ``unknown``.

cadgen reads a channel as a token and nothing more: telemetry reports it, and nothing decides by
its name but ``dev``, a development install (and a source tree, installed editable or imported from
a checkout by path), which hears of no release and sends no telemetry by default. A process of an
installation no plugin's server ever ran from -- a skills-only install, or cadgen run by hand -- is
``unknown``. Which app runs a server is not a channel either: the MCP handshake says that
(``clientInfo``), so a plugin several apps read names one channel.

Whether a copy hears of a new release (``cadgen/updates.py``) is ``told``: not when something
keeps it up to date, nor for a development install. So a plugin that ships somewhere new needs no
release of cadgen: its startup config says it all.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
from pathlib import Path

ENV = "CADGEN_INSTALL_CHANNEL"
AUTO_UPDATED_ENV = "CADGEN_AUTO_UPDATED"
DEV = "dev"
UNKNOWN = "unknown"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
# Where each installation's channel is written down, in the state directory, and how many installations
# it keeps: the most recently written, as uv makes a new one for each release a plugin pins.
RECORD = "install-channels.json"
KEPT_INSTALLATIONS = 16

LOG = logging.getLogger("cadgen.channel")


def is_channel(value: object) -> bool:
    """Whether ``value`` is a channel a plugin can name: a short lowercase token."""
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value)) and value != UNKNOWN


@functools.cache
def _source_tree() -> bool:
    """An editable install, or cadgen imported from a checkout by path -- as the build daemon and its
    workers are (``PYTHONPATH`` names the checkout's ``src`` first), where the first metadata found
    can be a build's leftover rather than the editable install's record."""
    from cadgen._internal.editable import editable_source

    if editable_source() is not None:
        return True
    package = Path(__file__).resolve().parents[1]  # cadgen/
    return package.parent.name == "src" and (package.parents[1] / "pyproject.toml").is_file()


def named() -> str | None:
    """The channel this process was told itself: what its plugin named, else ``dev`` for a source tree, else ``None``."""
    value = str(os.environ.get(ENV) or "").strip()
    if is_channel(value):
        return value
    return DEV if _source_tree() else None


def channel(*, recorded_too: bool = True) -> str:
    """This install's channel: what its plugin named, else ``dev`` for a source tree, else the one written down for
    this installation (``recorded``; not with ``recorded_too=False``, as the CAD server asks), else ``unknown``."""
    return named() or (recorded() if recorded_too else None) or UNKNOWN


def _record_path() -> Path:
    from cadgen.viewer.recents import state_dir  # noqa: PLC0415 -- the state directory's one definition

    return state_dir() / RECORD


@functools.cache
def installation() -> str:
    """This installation's short name: its cadgen folder's, as the build daemon's is (``cadgen.daemon.client``)."""
    package = str(Path(__file__).resolve().parents[1])
    return hashlib.sha256(package.encode("utf-8")).hexdigest()[:16]


def _load(path: Path) -> dict[str, str]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {key: value for key, value in kept.items() if is_channel(value)} if isinstance(kept, dict) else {}


def recorded(*, path: Path | None = None) -> str | None:
    """The channel a plugin's server last wrote down for this installation (``remember``), or ``None``. Never
    raises: a record that cannot be read is no record."""
    try:
        return _load(path or _record_path()).get(installation())
    except Exception:  # noqa: BLE001 - a channel is only reported: nothing may fail for want of one
        LOG.debug("could not read the install channel", exc_info=True)
        return None


def remember(*, path: Path | None = None) -> str | None:
    """Write down the channel this process's plugin named, for every process of its installation that was not told
    one (``recorded``): the CAD server does, as it starts. Nothing is written when there is nothing named, or when
    it is what the record holds already. What was written, or ``None``. Never raises."""
    value = str(os.environ.get(ENV) or "").strip()
    if not is_channel(value):
        return None
    try:
        from cadgen._internal.atomic_replace import write_bytes_atomic
        from cadgen._internal.file_lock import exclusive

        path = path or _record_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = installation()
        with exclusive(path.with_name(RECORD + ".lock")):
            kept = _load(path)
            if kept.get(key) == value:
                return value
            kept.pop(key, None)
            kept[key] = value  # the last written is the newest: the oldest go first past the cap
            kept = dict(list(kept.items())[-KEPT_INSTALLATIONS:])
            write_bytes_atomic(path, (json.dumps(kept, indent=2) + "\n").encode("utf-8"))
        return value
    except Exception:  # noqa: BLE001 - a channel is only reported: nothing may fail for want of one
        LOG.debug("could not write the install channel down", exc_info=True)
        return None


def auto_updated() -> bool:
    """Whether this install's plugin said something other than the person keeps it up to date."""
    return str(os.environ.get(AUTO_UPDATED_ENV) or "").strip() == "1"


def told() -> bool:
    """Whether this install hears of a new release: a copy nothing else updates, and not a development install."""
    return not auto_updated() and channel() != DEV  # a record says ``dev`` only for a development install's own
