"""Which installed version each delivery channel of text-to-cad is on: the pointers.

A channel is whoever delivers and updates a copy of the plugin. The **default** channel has no name: the
install command's copies and anything installed by hand. Any other channel is a free-form name of safe
characters (``CHANNEL``, ``channel_name``); this code holds no list of names and no rule for any one of them.
Each channel's pointer names the one version (``versions/<version>`` in the state folder,
``cad_server._internal.versions``) that channel runs:

- ``<state>/default``: the default channel's version, one line.
- ``<state>/channels/<name>``: a named channel's, one line, a file per channel.

A pointer is written whole and made durable (``write``: beside it under a name no channel has, flushed to the
disk, renamed over, and its folder flushed), so a reader meets the one before or the one after, and a crash never
leaves an empty one; moving a channel to another version is ``versions.move``, which is the one writer of a pointer
outside a test. ``listing`` says every pointer, ``named`` the versions they name.

**A pointer that cannot be read is not "no pointer".** Only a file that is not there is none (``read``: None).
One that is there and cannot be read now (a sharing violation on Windows, an antivirus scan, a permission, a link to
nothing), or does not hold one version name (``version_text``: emptied by a crash, or written in a form this release
does not know), a ``channels`` folder that cannot be listed, and an entry there whose name is no channel's (but a
write's own, a dot first), are ``Unreadable``. Nothing reads one as "nothing": a pinned command refuses to run
(``pins.apply``), as the ``cad`` command does (``installations``: the sh, the Windows main and this module read a
pointer by the one rule, held equal by a test); every removal removes nothing that pass (``versions._kept``); only
``cad setup``, the updater and ``cad doctor`` write one again (``versions.move``'s ``mend``, ``versions.mend``),
never naming a version older than the newest a channel has been on. ``cad doctor`` says which.

**When a channel was last used** (``used``, ``last_used``): a stamp of its own beside the pointers,
``used/default`` or ``used/<name>``, whose time a server sets as it takes the channel's requests; so a pointer
file is written by a move alone.

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
from cad.engine.atomic_replace import replace_atomic

__all__ = ["CHANNEL", "CHANNELS", "DEFAULT", "Default", "FORGOTTEN_DAYS", "Pointer", "USED", "Unreadable", "channel_name",
           "default", "forget", "last_used", "leaving", "listing", "mirror", "named", "read", "started", "survey", "unused",
           "used", "version_text", "write"]

# A named channel: a lower-case letter or digit first, then up to 31 of those, ``.``, ``_`` or ``-``. Safe as a
# file's name on every system, and in a pin (``cad +<version>@<channel>``): the library's one rule
# (``places.CHANNEL``), which the ``cad`` command's own text repeats (``installations``).
CHANNEL = places.CHANNEL
DEFAULT = places.DEFAULT_CHANNEL
CHANNELS = "channels"
# The channels' last-use stamps, a file each (``used``): ``used/default``, ``used/<name>``.
USED = "used"
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


class Unreadable(OSError):
    """A pointer that is there and cannot be read now, or names no version, or the channels' folder that cannot be
    listed: never "no pointer" (see the module). ``path`` is the file or folder; ``corrupt``, that it was read and
    names no version (a crash emptied it), which only a move writing it again mends."""

    def __init__(self, path: Path, why: str, *, corrupt: bool = False) -> None:
        super().__init__(f"the pointer {path} cannot be read: {why}" if not corrupt
                         else f"the pointer {path} names no version: {why}")
        self.path = path
        self.corrupt = corrupt


def read(channel: str | None = None, state: Path | None = None) -> str | None:
    """The version channel ``channel``'s pointer names (None: the default channel's), present or not; None when it
    has no pointer -- its file is not there. ``Unreadable`` for one that is there and cannot be read, or names no
    version."""
    path = _folder(state).path(_inside(channel))
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        if os.path.lexists(path):  # a link to nothing is there, and names nothing that can be read
            raise Unreadable(path, "it is a link to nothing") from None
        return None
    except OSError as error:
        raise Unreadable(path, error.strerror or str(error)) from None
    text = version_text(data)
    if text is not None:
        return text
    raise Unreadable(path, f"it holds {len(data)} bytes and no version", corrupt=True)


def version_text(data: bytes) -> str | None:
    """The version a pointer's bytes name, by the one rule the ``cad`` command reads one by too
    (``installations``): every carriage return taken out and the line ends after the text, what is left one version
    name (``places.VERSION``) and nothing else; else None."""
    try:
        text = data.replace(b"\r", b"").rstrip(b"\n").decode("ascii")
    except UnicodeDecodeError:
        return None
    return text if places.VERSION.fullmatch(text) else None


def write(channel: str | None, version: str, state: Path | None = None, *, mirrored: bool = True) -> Path:
    """Channel ``channel``'s pointer (None: the default's) set to ``version``, landed whole and made durable (see
    the module): its file. Writing the default's writes the mirror for 0.11.10 and earlier too (``mirror``), after it,
    unless ``mirrored`` is false (``versions.move`` writes it itself, after the pointer, so it tells a failure of the
    one from the other): a mirror that cannot be written is ``OSError``, with the pointer moved. ``ValueError`` for a
    name that is no channel or no version."""
    if not places.VERSION.fullmatch(version or ""):
        raise ValueError(f"not a version: {version!r}")
    path = _folder(state).path(_inside(channel))
    _land(path, f"{version}\n".encode("utf-8"))
    if _inside(channel) == DEFAULT and mirrored:
        mirror(version, state)
    return path


def _land(path: Path, data: bytes) -> None:
    """``data`` at ``path``, whole and on the disk: written beside it under a name no channel has (a dot first),
    flushed, renamed over it, and the folder flushed, so neither a reader nor a crash ever meets half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        replace_atomic(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    if os.name != "nt":  # a rename is durable once its folder is flushed; Windows' NTFS journals it
        try:
            folder = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(folder)
        except OSError:
            pass
        finally:
            os.close(folder)


def forget(channel: str, state: Path | None = None) -> None:
    """Named channel ``channel``'s pointer removed, and its last-use stamp (``cad doctor --prune``'s, for a channel no
    longer used). The default's is never forgotten: a device's default moves, and is gone only with the device's
    install (``ValueError``)."""
    if channel_name(channel) is None:
        raise ValueError("the default channel's pointer is never forgotten")
    _folder(state).remove(_inside(channel))
    _folder(state).remove(f"{USED}/{channel}")


# When this process last marked each channel used (``used``), so a server busy with requests marks it once a
# minute at most.
USED_SECONDS = 60.0
_used: dict[str, float] = {}


def _stamp(channel: str | None, state: Path | None = None) -> Path:
    """Channel ``channel``'s last-use stamp (None: the default's), there or not."""
    return _folder(state).path(f"{USED}/{channel or DEFAULT}")


# How often a pinned command marks its channel used (``pins.apply``): each is a process of its own.
USED_DAILY = 86400.0


def used(channel: object, state: Path | None = None, *, every: float | None = None) -> bool:
    """Channel ``channel`` (a request's ``channel``: absent, None or ``default`` is the default channel) marked
    used now: its stamp's time (``used/<channel>``, made where it is not) set to now, where the channel has a pointer
    -- the time ``cad doctor`` shows as the channel's last use. Marked by a server as it takes a request, and by every
    pinned command as its version reads the pin (``pins.apply``; ``every``: not where the stamp is newer than that
    many seconds, ``USED_DAILY``); never a pointer made, nor one written. At most once a ``USED_SECONDS`` per channel
    in a process; quiet, a failure (a sandbox's folder) never said. Whether it was marked."""
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
        if not _folder(state).path(_inside(name)).is_file():
            return False
        stamp = _stamp(name, state)
        if every is not None:
            try:
                if time.time() - os.stat(stamp).st_mtime < every:
                    return False
            except FileNotFoundError:
                pass
        stamp.parent.mkdir(parents=True, exist_ok=True)
        with open(stamp, "ab"):
            pass
        os.utime(stamp)
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class Pointer:
    """A channel's pointer: its channel (None: the default), the version it names, and its file (whose time is
    when the channel last moved)."""

    channel: str | None
    version: str
    path: Path


# How long a named channel goes unused before ``cad doctor --prune`` forgets it (``unused``): a store's copy that is
# gone from every app leaves its pointer, and nothing else ever moves or removes it. Never the default channel.
FORGOTTEN_DAYS = 30


def last_used(pointer: Pointer, state: Path | None = None) -> float | None:
    """When ``pointer``'s channel was last used: the later of its last-use stamp's time (``used``) and its pointer's
    (a move is a use); None where neither can be read."""
    found = []
    for path in (_stamp(pointer.channel, state), pointer.path):
        try:
            found.append(os.stat(path).st_mtime)
        except OSError:
            pass
    return max(found) if found else None


def unused(now: float | None = None, state: Path | None = None) -> list[Pointer]:
    """The named channels unused for ``FORGOTTEN_DAYS`` (``last_used``), which ``cad doctor --prune`` forgets: a
    person's command, never automatic. Never the default channel."""
    import time

    now = time.time() if now is None else now
    found = []
    for pointer in listing(state):
        when = last_used(pointer, state)
        if pointer.channel is not None and when is not None and now - when >= FORGOTTEN_DAYS * 86400:
            found.append(pointer)
    return found


def _entries(channels: Path) -> list[str]:
    """The names in the channels' folder but a write's own (a dot first), sorted: none where the folder is not there.
    ``Unreadable`` when it cannot be listed."""
    try:
        return sorted(name for name in os.listdir(channels) if not name.startswith("."))
    except FileNotFoundError:
        return []
    except OSError as error:
        raise Unreadable(channels, error.strerror or str(error)) from None


def _channel_file(name: str) -> bool:
    """Whether ``name``, in the channels' folder, is a named channel's pointer as this release names one."""
    return CHANNEL.fullmatch(name) is not None and name != DEFAULT


def listing(state: Path | None = None) -> list[Pointer]:
    """Every pointer on this device, the default's first, then the named channels' by name; a write's own file (a dot
    first) is none. ``Unreadable`` when a pointer there cannot be read, the channels' folder cannot be listed, or holds
    an entry whose name is no channel's (written by a release that names them otherwise, or by hand): what it would
    name is not known, so never a shorter list."""
    folder = _folder(state)
    found = []
    version = read(None, state)
    if version is not None:
        found.append(Pointer(None, version, folder.path(DEFAULT)))
    channels = folder.path(CHANNELS)
    for name in _entries(channels):
        if not _channel_file(name):
            raise Unreadable(channels / name, "its name is no channel's, so which version it keeps is not known")
        version = read(name, state)
        if version is not None:
            found.append(Pointer(name, version, folder.path(f"{CHANNELS}/{name}")))
    return found


def survey(state: Path | None = None) -> list[Pointer | Unreadable]:
    """Every pointer file on this device as ``listing`` reads it, one that cannot be read as its ``Unreadable`` in its
    place rather than the whole list refused: what ``cad doctor`` reports."""
    folder = _folder(state)
    found: list[Pointer | Unreadable] = []
    names: list[str | None] = [None]
    channels = folder.path(CHANNELS)
    try:
        for name in _entries(channels):
            if _channel_file(name):
                names.append(name)
            else:
                found.append(Unreadable(channels / name, "its name is no channel's, so which version it keeps is "
                                                         "not known"))
    except Unreadable as unreadable:
        found.append(unreadable)
    for name in names:
        try:
            version = read(name, state)
        except Unreadable as unreadable:
            found.append(unreadable)
            continue
        if version is not None:
            found.append(Pointer(name, version, folder.path(_inside(name))))
    return found


def named(state: Path | None = None) -> set[str]:
    """The versions some pointer names (``Unreadable`` as ``listing``)."""
    return {pointer.version for pointer in listing(state)}


@dataclass(frozen=True)
class Default:
    """The default channel's version and where it was found (``source``): ``pointer``; ``current``, the
    version ``installations/current`` names where the install command has run here and no pointer is
    (``legacy``: one of the layout of 0.11.10 and earlier, not the mirror of a version); ``newest``, the newest version
    present that has started (``started``), else the newest present. ``version`` None with none of them."""

    version: str | None
    source: str | None
    legacy: bool = False


def started(name: str, state: Path | None = None) -> bool:
    """Whether version ``name`` has started: its data's first-start marker is there (``imports.MARKER``), as the
    ``cad`` command reads it too (a file there or not)."""
    return ((state or places.state_dir()) / places.VERSIONS / name / places.DATA / "format.json").is_file()


def default(state: Path | None = None) -> Default:
    """The default channel's version, for a command with no pin: its pointer; with none, the version the
    layout of 0.11.10 and earlier names current where the install command has run here (its receipt); else the newest
    version present that has started (``started``: one that never has is not taken for one whose data is there), else
    the newest present -- which a command then runs only through the default channel's first use, its import and its
    pointer first (``pins.first_use``) --; else none. ``Unreadable`` for a pointer that cannot be read."""
    found = read(None, state)
    if found is not None:
        return Default(found, "pointer")
    current = _current(state)
    if current is not None:
        return Default(current[0], "current", current[1])
    from cad_server._internal import versions

    # A version ``cad uninstall`` took out whose code the system kept (``versions.UNINSTALLED``) is no default.
    present = [name for name in versions.present(state)
               if not os.path.lexists((state or places.state_dir()) / places.VERSIONS / name / versions.UNINSTALLED)]
    used = [name for name in present if started(name, state)]
    return Default((used or present)[-1], "newest") if present else Default(None, None)


def leaving(state: Path | None = None) -> Default:
    """What the default channel leaves at its next move (``versions.move``): its pointer's version; with no
    pointer, the layout of 0.11.10 and earlier where the install command has run here and its ``current`` is not a
    version's mirror (``legacy``); else nothing -- the channel's first use. ``Unreadable`` for a pointer that cannot
    be read."""
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
