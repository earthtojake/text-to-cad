"""Where this install of text-to-cad came from: its channel.

Each package of the CAD plugin names its own channel in its MCP server's environment,
``CADGEN_INSTALL_CHANNEL``, written by the build that makes that package -- never worked out from
folders, ids or a host's internals. The server's children (the CAD Viewer, the build daemon and
its workers) inherit it, so every process of an install knows it.

cadgen knows two channels by name: ``github``, installed from the repository by hand (a
marketplace added from it, a clone, an extension, a Claude Desktop config), and ``dev``, a
development install. Every other channel a package names is a store's copy, named by that store's
package (a plugin directory, a marketplace): cadgen reads it as a token and nothing more, so a new
store needs no release of cadgen. A process nothing named a channel for -- a skill's ``cadgen``
command, a Skills CLI install -- is ``unknown``, and an editable install of a source tree is
``dev``. Which app runs it is not a channel: the MCP handshake says that (``clientInfo``), so one
package read by several apps names one channel.

Analytics report it (``channel``), and the version check decides by it (``cadgen/updates.py``):
a store's copy is left to its store, which updates it.
"""

from __future__ import annotations

import functools
import os
import re

ENV = "CADGEN_INSTALL_CHANNEL"
GITHUB = "github"
DEV = "dev"
UNKNOWN = "unknown"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def is_channel(value: object) -> bool:
    """Whether ``value`` is a channel a package can name: a short lowercase token."""
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value)) and value != UNKNOWN


@functools.cache
def _source_tree() -> bool:
    from cadgen._internal.editable import editable_source

    return editable_source() is not None


def channel() -> str:
    """This install's channel: what its package named, else ``dev`` for a source tree, else ``unknown``."""
    named = str(os.environ.get(ENV) or "").strip()
    if is_channel(named):
        return named
    return DEV if _source_tree() else UNKNOWN


def is_store(where: str) -> bool:
    """Whether ``where`` is a store's copy: any channel a package named but ``github`` and ``dev``."""
    return where not in (GITHUB, DEV, UNKNOWN)

