"""Where an event comes from, and whether this process has an updater: the delivery channel and the app.

**The channel** is a pin's (``cad +<version>@<channel> <verb>``) or a launcher's (``cad-mcp --channel NAME``):
who delivered the copy of the plugin whose text ran the command, as that copy says it. A store's copy carries
its channel in every pin (its builder stamps it); our own text -- the install command's plugin folder, the
``latest`` branch, a copy installed from GitHub by hand -- carries none, and runs on the default channel. Nothing
here keeps a list of channels or decides anything by a channel's name: a request carries its channel
(``places.channel``, ``client.with_channel``), a session its launcher's (``mcp.http.Session.channel``), and
telemetry reports it beside the app (``describe``), ``default`` for none. A server's environment says no
channel: ``CAD_INSTALL_CHANNEL`` and ``CAD_AUTO_UPDATED``, which plugin configs of 0.11.10 and earlier set, are
read for nothing.

**The app** an event comes from is detected, never told: the MCP handshake's client name where there is one,
else the markers an agent app sets in the shells it runs (``engine_host.app``), else ``unknown``.

**A development build** (``development``) is a version named ``<release>-dev.<time>`` (``dev_install``), or a
source tree -- installed editable, or imported from a checkout by path -- that was not told which version it runs
as (``places.INSTALLATION_ENV``). It hears of no release and sends no telemetry by default; what it sends with
telemetry turned on says the channel ``dev``.

**The updater** (``told``): only the default channel has one (a named channel's copy is updated by whoever
delivers it), only where the install command has run (its receipt), and never for a development build. A
process with no version (a person's own environment) is the default's, on a device the install command set up.
"""

from __future__ import annotations

import functools
import logging
import os
import re
from pathlib import Path

DEV = "dev"
UNKNOWN = "unknown"

LOG = logging.getLogger("cad_server.channel")


@functools.cache
def _source_tree() -> bool:
    """An editable install, or the server imported from a checkout by path -- as the engine daemon and its
    workers are (``PYTHONPATH`` names the checkout's ``src`` first), where the first metadata found can be a
    build's leftover rather than the editable install's record. Told by where the server is imported from before
    any metadata is read: the scan costs every command that counts something tens of milliseconds, and a server
    imported from a folder of installed packages is no source tree (an editable install imports from its
    source)."""
    package = Path(__file__).resolve().parents[1]  # cad_server/
    if package.parent.name == "src" and (package.parents[1] / "pyproject.toml").is_file():
        return True
    if package.parent.name in ("site-packages", "dist-packages"):
        return False
    from cad_server._internal.editable import editable_source

    return editable_source() is not None


# A development build's name, ``<release>-dev.<YYYYmmddHHMMSS>``: ``versions.DEVELOPMENT``, copied so that asking
# imports nothing of the engine's (a command that needs none of it, ``cad orcaslicer``, reads it), held equal by a test.
_DEVELOPMENT = re.compile(r"(?P<release>.+)-dev\.(?P<stamp>[0-9]+)")


def development() -> bool:
    """Whether this process is a development build (see the module): the version it was told it runs as
    (``CAD_INSTALLATION_VERSION``, which the ``cad`` command and a server tell a development build's processes) is a
    development build's name; told none, a source tree is one, and an installed server is one where the version it
    runs as (``places.installation``: its version folder's) is. Never raises: what cannot be read is no development
    build."""
    try:
        told = os.environ.get("CAD_INSTALLATION_VERSION", "").strip()
        if told:
            return _DEVELOPMENT.fullmatch(told) is not None
        if _source_tree():
            return True
        from cad.engine.places import installation

        return _DEVELOPMENT.fullmatch(installation() or "") is not None
    except Exception:  # noqa: BLE001 - a fact for a report and a default, never a reason to fail
        LOG.debug("could not tell whether this is a development build", exc_info=True)
        return False


def told() -> bool:
    """Whether this process hears of a new release, and shows an update notice, an update button and the
    automatic-updates switch: the default channel's version alone, the one channel with an updater (a named
    channel's copy is updated by whoever delivers it), on a device where the install command has run (its receipt:
    where it has not, there is no install to update), and never a development build. A process with no version is
    the default's."""
    return not development() and default_version()


def default_version() -> bool:
    """Whether this process's version (``places.versioned``) is the default channel's as a command with no pin
    resolves it (``pointers.default``) on a device the install command set up (its receipt); a process with no
    version is the default's, but only on such a device too (a person's own ``pip install cad-server`` or ``uvx``
    run on a device the install command never set up has no install to update). Never raises."""
    from cad.engine.places import state_dir, versioned

    name = versioned()
    try:
        from cad_server._internal import pointers

        receipt = (state_dir() / pointers.RECEIPT).is_file()
        if name is None:
            return receipt
        return pointers.default().version == name and receipt
    except Exception:  # noqa: BLE001 - a state folder it cannot read: told, as before
        return True


# How long a process keeps what ``own`` read of the pointers before reading them again.
OWN_SECONDS = 60.0
_OWN: list = [float("-inf"), None]  # when ``own`` last read the pointers (monotonic), and what it found


def own() -> str | None:
    """The delivery channel a version's own use counts under where nothing names one -- the browser viewer's page,
    which no pin or launcher carries (``analytics.Recorder``'s process-level counts): the one named channel that is
    on this process's version, when the default channel's pointer does not name it (a version only a store's copy is
    on: claude.ai's directory copy, which is skills alone, has the browser as its one interface); else None, the
    default. A process with no version, the default's version, a version two named channels share, or pointers that
    cannot be read: None. Read at most once every ``OWN_SECONDS``. Never raises."""
    import time

    now = time.monotonic()
    if now - _OWN[0] < OWN_SECONDS:
        return _OWN[1]
    found = None
    try:
        from cad.engine.places import versioned

        name = versioned()
        if name is not None:
            from cad_server._internal import pointers

            if pointers.read(None) != name:  # the default channel's pointer: none names nothing
                on = {pointer.channel for pointer in pointers.listing() if pointer.channel and pointer.version == name}
                found = next(iter(on)) if len(on) == 1 else None
    except Exception:  # noqa: BLE001 - pointers that cannot be read now: the default, as before
        LOG.debug("could not read which channel is on this version", exc_info=True)
        found = None
    _OWN[0], _OWN[1] = now, found
    return found


def describe(channel: str | None = None, client: str | None = None, environ=None) -> dict[str, str]:
    """Where an event comes from, as telemetry says it (two fields, ``cad_server.analytics``): ``channel``, the
    delivery channel of the request or session it counts (a request's ``channel``, a launcher's ``--channel``; none
    is ``default``; ``dev`` from a development build), and ``app``, the agent app running it -- detected, never
    told: from the MCP handshake's client name where there is one (``client``), else from the markers an app sets
    in its shell (read from ``environ``: a command's own environment, or a build request's ``env``), else
    ``unknown`` (``engine_host.app``, the host adapter's)."""
    from cad.engine.places import CHANNEL, DEFAULT_CHANNEL
    from cad_server._internal.engine_host import app

    if development():
        named = DEV
    else:
        named = channel if isinstance(channel, str) and CHANNEL.fullmatch(channel) else DEFAULT_CHANNEL
    return {"channel": named, "app": app(client, environ) or UNKNOWN}
