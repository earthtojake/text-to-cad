"""Where this install of text-to-cad came from: its channel, and whether something keeps it up to date.

Each plugin says both where it starts the CAD server: ``cadgen mcp --channel <id>``, plus
``--auto-updated`` when something other than the person keeps that copy up to date (the store
that reviewed it, or the app that installed it). The build that makes the plugin writes them into
its startup command; nothing works them out from folders, ids or a host's internals. The server
hands both to the processes it starts (the CAD Viewer, the build daemon and its workers) as
``CADGEN_INSTALL_CHANNEL`` and ``CADGEN_AUTO_UPDATED``, so they know them too.

cadgen reads a channel as a token and nothing more: analytics report it, and nothing decides by
its name but ``dev``, a development install (and an editable install of a source tree). A process
no plugin's server started -- a skill's ``cadgen`` command, the CAD Viewer a skill opens -- is
``unknown``: a skills-only install, or cadgen run by hand. Which app runs a server is not a
channel either: the MCP handshake says that (``clientInfo``), so a plugin several apps read names
one channel.

Whether a copy hears of a new release (``cadgen/updates.py``) is ``told``: not when something
keeps it up to date, nor for a development install. So a plugin that ships somewhere new needs no
release of cadgen: its startup command says it all.
"""

from __future__ import annotations

import functools
import os
import re

ENV = "CADGEN_INSTALL_CHANNEL"
AUTO_UPDATED_ENV = "CADGEN_AUTO_UPDATED"
DEV = "dev"
UNKNOWN = "unknown"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def is_channel(value: object) -> bool:
    """Whether ``value`` is a channel a plugin can name: a short lowercase token."""
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value)) and value != UNKNOWN


@functools.cache
def _source_tree() -> bool:
    from cadgen._internal.editable import editable_source

    return editable_source() is not None


def channel() -> str:
    """This install's channel: what its plugin named, else ``dev`` for a source tree, else ``unknown``."""
    named = str(os.environ.get(ENV) or "").strip()
    if is_channel(named):
        return named
    return DEV if _source_tree() else UNKNOWN


def auto_updated() -> bool:
    """Whether this install's plugin said something other than the person keeps it up to date."""
    return str(os.environ.get(AUTO_UPDATED_ENV) or "").strip() == "1"


def told() -> bool:
    """Whether this install hears of a new release: a copy nothing else updates, and not a development install."""
    return not auto_updated() and channel() != DEV
