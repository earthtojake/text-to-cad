"""Which installed version each delivery channel of text-to-cad is on: the pointers.

A channel is whoever delivers and updates a copy of the plugin. The **default** channel has no name: the
install command's copies and anything installed by hand. Any other channel is a free-form name of safe
characters (``CHANNEL``, ``channel_name``); this code holds no list of names and no rule for any one of them.
Each channel's pointer names the one version (``versions/<version>`` in the state folder,
``cad_server._internal.versions``) that channel runs:

- ``<state>/default``: the default channel's version, one line.
- ``<state>/channels/<name>``: a named channel's, one line, a file per channel.

A pointer is written whole (``registry.Folder``: beside it, then renamed over), so a reader meets the one
before or the one after (``write``); moving a channel to another version is ``versions.move``, which is the
one writer of a pointer outside a test. ``listing`` says every pointer, ``named`` the versions they name.

**The default channel's version** (``default``): its pointer; with none, the version the layout of 0.11.10 and earlier
names current (``installations/current``) where the install command has run here (its receipt,
``install-receipt.json``); else the newest version present. With no pointer that is a resolution, not a
pointer: what ``versions.move`` leaves for the default channel is ``leaving``'s, the pointer or the layout of 0.11.10
and earlier.

**The mirror for 0.11.10 and earlier.** Every client of 0.11.10 and earlier finds the device's server through
``installations/current`` and the record it names (``cad_server._internal.installations``). So writing the
default pointer writes them too (``mirror``): ``current`` names the default's version and its record the
version's server environment, as its code marker says it (``places.version_record``). Only clients of 0.11.10 and
earlier
read them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cad.engine import places

__all__ = ["CHANNEL", "CHANNELS", "DEFAULT", "Default", "FORGOTTEN_DAYS", "Pointer", "channel_name", "default", "forget",
           "last_used", "leaving", "listing", "mirror", "named", "read", "unused", "used", "write"]

# A named channel: a lower-case letter or digit first, then up to 31 of those, ``.``, ``_`` or ``-``. Safe as a
# file's name on every system, and in a pin (``cad +<version>@<channel>``): the library's one rule
# (``places.CHANNEL``), which the ``cad`` command's own text repeats (``installations``).
CHANNEL = places.CHANNEL
DEFAULT = places.DEFAULT_CHANNEL
CHANNELS = "channels"
# The install command's record of what it changed, whose presence says the install command ran here.
RECEIPT = "install-receipt.json"


def channel_name(text: object) -> str | None:
    """``text`` as a channel's name, or ``ValueError`` saying the rule: an empty one, as in ``@`` with
    nothing after it, among them. ``default`` is the default channel itself, None: never a named channel of
    that name, so ``channels/default`` is never made and ``default`` means one thing everywhere."""
    if text == DEFAULT:
        return None
    if isinstance(text, str) and CHANNEL.fullmatch(text):
        return text
    raise ValueError(f"not a channel: {text!r} (a channel is a lower-case letter or digit, then up to 31 "
                     "lower-case letters, digits, '.', '_' or '-')")


def _folder(state: Path | None = None):
    from cad_server.engine.registry import Folder

    return Folder(state or places.state_dir())


def _inside(channel: str | None) -> str:
    """The pointer's file in the state folder: ``default`` for the default channel (None, or ``default``),
    else ``channels/<name>``."""
    name = None if channel is None else channel_name(channel)
    return DEFAULT if name is None else f"{CHANNELS}/{name}"


def read(channel: str | None = None, state: Path | None = None) -> str | None:
    """The version channel ``channel``'s pointer names (None: the default channel's), present or not; None
    with no pointer, or one that names no version."""
    data = _folder(state).read(_inside(channel))
    text = data.decode("utf-8", "replace").strip() if data is not None else ""
    return text if places.VERSION.fullmatch(text) else None


def write(channel: str | None, version: str, state: Path | None = None, *, mirrored: bool = True) -> Path:
    """Channel ``channel``'s pointer (None: the default's) set to ``version``, landed whole: its file. Writing
    the default's writes the mirror for 0.11.10 and earlier too (``mirror``), after it, unless ``mirrored`` is
    false (``versions.move`` writes it itself, after the pointer, so it tells a failure of the one from the
    other): a mirror that cannot be written is ``OSError``, with the pointer moved. ``ValueError`` for a name
    that is no channel or no version."""
    if not places.VERSION.fullmatch(version or ""):
        raise ValueError(f"not a version: {version!r}")
    path = _folder(state).write(_inside(channel), f"{version}\n".encode("utf-8"))
    if _inside(channel) == DEFAULT and mirrored:
        mirror(version, state)
    return path


def forget(channel: str, state: Path | None = None) -> None:
    """Named channel ``channel``'s pointer removed (``cad doctor --prune``'s, for a channel no longer used).
    The default's is never forgotten: a device's default moves, and is gone only with the device's install
    (``ValueError``)."""
    if channel_name(channel) is None:
        raise ValueError("the default channel's pointer is never forgotten")
    _folder(state).remove(_inside(channel))


# When this process last marked each channel used (``used``), so a server busy with requests marks it once a
# minute at most.
USED_SECONDS = 60.0
_used: dict[str, float] = {}


def used(channel: object, state: Path | None = None) -> bool:
    """Channel ``channel`` (a request's ``channel``: absent, None or ``default`` is the default channel) marked
    used now: its pointer's file's time set to now, where it has one -- the time ``cad doctor`` shows as the
    channel's last use. Made by a server as it takes a request, outside any sandbox; never a pointer made, nor
    one written. At most once a ``USED_SECONDS`` per channel in a process; quiet. Whether it was marked."""
    import time

    try:
        name = None if channel is None else channel_name(channel)
    except ValueError:
        return False
    key = name or DEFAULT
    now = time.monotonic()
    if now - _used.get(key, -USED_SECONDS) < USED_SECONDS:
        return False
    _used[key] = now
    try:
        os.utime(_folder(state).path(_inside(name)))
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class Pointer:
    """A channel's pointer: its channel (None: the default), the version it names, and its file (whose time
    is when the channel was last used, ``used``, or moved)."""

    channel: str | None
    version: str
    path: Path


# How long a named channel goes unused before ``cad doctor --prune`` forgets it (``unused``): a store's copy that is
# gone from every app leaves its pointer, and nothing else ever moves or removes it. Never the default channel.
FORGOTTEN_DAYS = 30


def last_used(pointer: Pointer) -> float | None:
    """When ``pointer``'s channel was last used (``used``): its file's modified time; None where it cannot be read."""
    try:
        return os.stat(pointer.path).st_mtime
    except OSError:
        return None


def unused(now: float | None = None, state: Path | None = None) -> list[Pointer]:
    """The named channels unused for ``FORGOTTEN_DAYS`` (``last_used``), which ``cad doctor --prune`` forgets: a
    person's command, never automatic. Never the default channel."""
    import time

    now = time.time() if now is None else now
    found = []
    for pointer in listing(state):
        when = last_used(pointer)
        if pointer.channel is not None and when is not None and now - when >= FORGOTTEN_DAYS * 86400:
            found.append(pointer)
    return found


def listing(state: Path | None = None) -> list[Pointer]:
    """Every pointer on this device, the default's first, then the named channels' by name. A file that names
    no version, or a name that is no channel, is none."""
    folder = _folder(state)
    found = []
    version = read(None, state)
    if version is not None:
        found.append(Pointer(None, version, folder.path(DEFAULT)))
    for name in folder.names(CHANNELS):
        if CHANNEL.fullmatch(name) and name != DEFAULT:
            version = read(name, state)
            if version is not None:
                found.append(Pointer(name, version, folder.path(f"{CHANNELS}/{name}")))
    return found


def named(state: Path | None = None) -> set[str]:
    """The versions some pointer names."""
    return {pointer.version for pointer in listing(state)}


@dataclass(frozen=True)
class Default:
    """The default channel's version and where it was found (``source``): ``pointer``; ``current``, the
    version ``installations/current`` names where the install command has run here and no pointer is
    (``legacy``: one of the layout of 0.11.10 and earlier, not the mirror of a version); ``newest``, the newest version
    present. ``version`` None with none of them."""

    version: str | None
    source: str | None
    legacy: bool = False


def default(state: Path | None = None) -> Default:
    """The default channel's version, for a command with no pin: its pointer; with none, the version the
    layout of 0.11.10 and earlier names current where the install command has run here (its receipt); else the newest
    version present (``versions.present``); else none."""
    found = read(None, state)
    if found is not None:
        return Default(found, "pointer")
    current = _current(state)
    if current is not None:
        return Default(current[0], "current", current[1])
    from cad_server._internal import versions

    present = versions.present(state)
    return Default(present[-1], "newest") if present else Default(None, None)


def leaving(state: Path | None = None) -> Default:
    """What the default channel leaves at its next move (``versions.move``): its pointer's version; with no
    pointer, the layout of 0.11.10 and earlier where the install command has run here and its ``current`` is not a
    version's mirror (``legacy``); else nothing -- the channel's first use."""
    found = read(None, state)
    if found is not None:
        return Default(found, "pointer")
    current = _current(state)
    if current is not None and current[1]:
        return Default(current[0], "current", True)
    return Default(None, None)


def _current(state: Path | None) -> tuple[str, bool] | None:
    """The version ``installations/current`` names, and whether it is one of the layout of 0.11.10 and earlier (its
    record's environment outside ``versions/``), where the install command's receipt is here; else None."""
    from cad_server._internal import installations

    folder = _folder(state)
    if folder.read(RECEIPT) is None:
        return None
    version = installations.current_version(folder)
    if version is None:
        return None
    record = places.installation_record(folder.read(f"{installations.FOLDER}/{version}.json"))
    return version, not (record is not None and _in_versions(record["prefix"], Path(folder.root)))


def _in_versions(prefix: str, state: Path) -> bool:
    inside = os.path.normcase(os.path.realpath(state / places.VERSIONS)).rstrip(os.sep) + os.sep
    return os.path.normcase(os.path.realpath(prefix)).startswith(inside)


def mirror(version: str, state: Path | None = None) -> bool:
    """``installations/current`` and the record it names written for present version ``version`` (its code
    marker's interpreter, console script and environment), so a client of 0.11.10 or earlier finds the default's
    server: whether it was written (False: ``version`` is not present). ``OSError`` when it cannot be."""
    from cad_server._internal import installations

    record = places.version_record(version, (state or places.state_dir()) / places.VERSIONS)
    if record is None:
        return False
    folder = _folder(state)
    installations.register(version, (record["cad"], record["python"], record["prefix"]), folder)
    installations.point(version, folder)
    return True
