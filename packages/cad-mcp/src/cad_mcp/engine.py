"""The CAD server of this transport's own version, as the stdio transport reaches it: with the standard library
alone.

The server's own clients find it by one rule (the library's ``cad.engine.places`` and
``cad.engine.client``, which this package does not import: an agent app installs it alone), and this
reads it the same way:

- **Its version and channel** (``Pin``, ``configure``): the version is this package's own release (a development
  install names its build in ``CAD_INSTALLATION_VERSION``); the channel is the ``--channel`` its app's server
  config gives it (none: the default channel). A source tree has no version (a checkout's tests, a development
  checkout), and reaches the server as every client of 0.11.10 and earlier does (below).
- **Its version made ready** (``prepare``, at start, in the background, outside any sandbox): its channel's
  pointer (``pointer``) read first, and where that names a newer version (``older``) the transport is stale at
  once and installs nothing; else its version installed where it is not (``uvx --from cad-server==<version> cad
  setup --add``, the ``cad`` command's own way); then, where the pointer does not name it, that version's own
  ``cad`` run pinned to it (``cad +<version>[@<channel>] setup --add --quiet``), which moves the channel to it or
  says it is stale -- the one rule every pinned command keeps, run by the version's own code, never this copy of
  it. Until it is done the transport is not ready (``unavailable``: being installed, ``installing_line``).
- **The engine folder** (``engine_dir``): the server's door (a named pipe; on Windows a port file) and
  lock, named ``engine``, in a folder only this user can write (``folder_refusal``): a version's is
  ``<engines>/<version>`` (``engine_dir(version)``), its data ``versions/<version>`` in the state folder
  (``version_dir``), its installed marker ``versions/<version>/code/cad-version.json`` (``version_record``); the
  flat one directly in the engines' folder (``engines_dir``) is what every server of 0.11.10 and earlier holds,
  and the default channel's version's server holds too, for their clients -- the library's rules
  (``cad.engine.places``), copied and held equal by a test. A transport with a version reaches its own version's
  door and no other. A request is one JSON line through the door, answered by JSON lines (``request``); the door
  is the one way to the server's HTTP endpoint and its token (``op: http``), which a loopback port alone could not
  vouch for.
- **Starting it** (``_start``): with a version, that version's server, from its own Python; with none, the
  current installation's (``<state>/installations/current`` and its record), whatever release this transport is,
  and on a device with none, one registered first (``register``: the server this transport's environment
  carries, else its own release's, installed by uvx).
- **Stale** (``stale``): once its channel's pointer names a NEWER version than its own (``older``: an update moved
  the channel on while the app's thread stayed open; an app still holding an older copy), this transport's version
  is not its channel's any more: it installs nothing, starts no server and connects to none (``connect``), and
  every request is answered here with one line that says so (``stale_line``: the ``cad`` command's words for
  which version this is and which its channel is on, then a thread's repair; ``shim``). A pointer naming an older version is no such thing: it is the channel this transport is moving.
- **Every wait bounded**: a request waits for the version a few seconds at most (``unavailable``), a server's
  answer through the door ``DOOR_SECONDS`` a line (``_line``), its start 60 seconds, its HTTP answer 10 minutes;
  ``prepare``'s runs are bounded by ``PREPARE_SECONDS`` each, which bounds every wait for it (``READY_LIMIT``).
- **The hold** (``hold``): a connection the server keeps while it is open, under a name the transport's
  MCP sessions are opened by, which end when it drops.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import re
import secrets
import selectors
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable
from urllib.parse import urlsplit

WINDOWS = os.name == "nt"
NAME = "engine"
# The server's distribution, whose release is this transport's own, its import name, the module it
# registers an installation by and the one it runs its engine as.
SERVER = "cad-server"
SERVER_PACKAGE = "cad_server"
REGISTER = "cad_server._internal.installations"
DAEMON_MODULE = "cad_server._internal.engine_daemon"
# How the server of this release is installed when the device has none: uv's tool run, as the agent app
# started this transport, with the Python line the server runs on.
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.14", "--from")
INSTALLATIONS = "installations"
CURRENT = f"{INSTALLATIONS}/current"
# The installed versions' folder in the state folder, and a version's name: a digit first.
VERSIONS = "versions"
VERSION = r"[0-9][0-9A-Za-z.+_-]*"
# Switches that govern only the process they are set in: the server serves every later client, so it
# goes by the person's saved choice, never by the switch of whichever client happened to start it.
PER_PROCESS = ("DO_NOT_TRACK", "CAD_TELEMETRY")
# The sandboxes known to refuse the loopback port the server's HTTP listener needs, each by a variable and
# the value it sets in the shells it runs: Codex's Seatbelt, in its default workspace-write mode.
SANDBOXES: tuple[tuple[str, str], ...] = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)
SANDBOXED = ("no engine server is running, and this shell's sandbox cannot start one: open a CAD card "
             "(the CAD plugin's server starts the engine) or run `cad server` outside the sandbox")
# How long a reader waits on a port file Windows refuses while it is renamed into place: the writer's ladder.
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


# --- where things are -----------------------------------------------------------------------------


def _local_state() -> Path:
    """The platform's place for state: macOS's Application Support, else ``$XDG_STATE_HOME`` or
    ``~/.local/state`` -- on Windows too, out of the local application data an app package (the Claude
    desktop app, which starts this server) virtualizes."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")


def state_dir() -> Path:
    """Where this user's CAD state lives (``CAD_STATE_DIR`` overrides it)."""
    override = os.environ.get("CAD_STATE_DIR")
    if override:
        return Path(override)
    return _local_state() / "cad"


def version_dir(version: str) -> Path:
    """Version ``version``'s folder, ``versions/<version>`` in the state folder. ``ValueError`` for a name that
    is no version."""
    import re

    if not re.fullmatch(VERSION, version or ""):
        raise ValueError(f"not a version: {version!r}")
    return state_dir() / VERSIONS / version


def engines_dir() -> Path:
    """The engines' folder: ``CAD_ENGINE_DIR``, else ``default_engine_dir``; the flat door every server of 0.11.10 and
    earlier holds is in it directly, each version's engine in a folder of its own (``engine_dir``)."""
    override = os.environ.get("CAD_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def engine_dir(version: str | None = None) -> Path:
    """Where a server's door and lock live: version ``version``'s folder in the engines' folder; with none named,
    this transport's own version's (``PIN``), and for a transport with no version the engines' folder itself,
    the flat door of 0.11.10 and earlier."""
    version = version if version is not None else PIN.version
    if version is None:
        return engines_dir()
    version_dir(version)  # the same refusal of a name that is no version
    return engines_dir() / version


# --- this transport's version and channel -------------------------------------------------------------

# A delivery channel's name (the library's ``places.CHANNEL``); ``default`` is the default channel, none.
CHANNEL = r"[a-z0-9][a-z0-9._-]{0,31}"
DEFAULT_CHANNEL = "default"
# The pointers in the state folder (the server's ``pointers``): the default channel's, and a named one's.
DEFAULT_POINTER = "default"
CHANNELS = "channels"
# The installed marker of a version, its schema, and the variable a development install names its build by.
VERSION_MARKER = "cad-version.json"
VERSION_SCHEMA = "cad version/1"
INSTALLATION_ENV = "CAD_INSTALLATION_VERSION"
# A release's name, as the ``cad`` command tells one (the server's ``pins.RELEASED``): one the index has.
RELEASED = r"[0-9.abcoprst]+"
# The exit status of a pinned ``cad`` whose channel has moved past it (the server's ``cli_errors.REASONS``).
STALE_EXIT = 4
# The install command, and its form that installs one version and changes nothing else (the server's
# ``versions.add_command``), for the line a transport says when it cannot install its version.
INSTALL = "curl -fsSL https://texttocad.dev/install.sh | sh"
INSTALL_WINDOWS = "irm https://www.texttocad.dev/install.ps1 | iex"
# How long a version's install, and its own ``cad`` moving its channel, may take; and so the longest ``prepare``
# can take, its two runs, which bounds every wait for it.
PREPARE_SECONDS = 3600.0
READY_LIMIT = 2 * PREPARE_SECONDS + 60.0
# How long a request waits for its version to be ready before it is answered here (``unavailable``).
READY_SECONDS = 5.0
# How long a line the server sends through its door is waited for (``_line``).
DOOR_SECONDS = 30.0
# Why a transport cannot reach its server now (``unavailable``): its version is being installed (or its channel
# moved to it), its channel is on a newer version, or its version could not be made ready.
INSTALLING, STALE, FAILED = "installing", "stale", "failed"


class Pin:
    """This transport's version (None: a source tree, which has none) and channel (None: the default), set once
    at start (``configure``), and what preparing it found (``prepare``): ``ready`` once done, ``failed`` the one
    line saying why it cannot serve, ``stale`` the one line saying its channel has moved past it."""

    def __init__(self, version: str | None = None, channel: str | None = None) -> None:
        self.version = version
        self.channel = channel
        self.ready = threading.Event()
        self.failed: str | None = None
        self.stale: str | None = None
        if version is None:
            self.ready.set()

    @property
    def label(self) -> str:
        return self.channel or DEFAULT_CHANNEL


# With no version until ``configure``: the flat door and the current installation, as every client of 0.11.10.
PIN = Pin()


def channel_name(text: str | None) -> str | None:
    """``text`` as a channel (None, or ``default``: the default channel), or ``ValueError`` saying the rule."""
    import re

    if text is None or text == DEFAULT_CHANNEL:
        return None
    if re.fullmatch(CHANNEL, text):
        return text
    raise ValueError(f"not a channel: {text!r} (a channel is a lower-case letter or digit, then up to 31 lower-case "
                     "letters, digits, '.', '_' or '-')")


def own_version() -> str | None:
    """This transport's version: the build a development install names (``INSTALLATION_ENV``), else this package's
    own release; None for a source tree (a checkout: its tests, its development), which has no version."""
    import re

    from cad_mcp import __version__, source_tree

    named = os.environ.get(INSTALLATION_ENV, "").strip()
    if re.fullmatch(VERSION, named):
        return named
    if source_tree() or not re.fullmatch(RELEASED, __version__):
        return None
    return __version__


def configure(channel: str | None) -> Pin:
    """This transport's pin: its version (``own_version``) and channel ``channel``, which it reaches the server
    by from now on."""
    global PIN
    PIN = Pin(own_version(), channel_name(channel))
    return PIN


def pointer(channel: str | None = None) -> str | None:
    """The version channel ``channel``'s pointer names (None: the default's), or None with none: the server's
    ``pointers.read``, copied and held equal by a test."""
    import re

    inside = DEFAULT_POINTER if channel is None else f"{CHANNELS}/{channel}"
    data = _read(state_dir() / inside)
    text = data.decode("utf-8", "replace").strip() if data is not None else ""
    return text if re.fullmatch(VERSION, text) else None


def version_record(version: str) -> dict[str, Any] | None:
    """Version ``version``'s installed marker (``versions/<version>/code/cad-version.json``) while its Python and
    ``cad`` are there, else None: the library's ``places.version_record``, copied."""
    try:
        record = json.loads(_read(version_dir(version) / "code" / VERSION_MARKER) or b"null")
    except ValueError:
        return None
    if (not isinstance(record, dict) or record.get("schema") != VERSION_SCHEMA or record.get("version") != version
            or not all(isinstance(record.get(key), str) for key in ("python", "cad", "prefix"))):
        return None
    return record if os.path.isfile(record["python"]) and os.path.isfile(record["cad"]) else None


def add_command(version: str, system: str | None = None) -> str:
    """The install line that makes ``version`` present and changes nothing else (the server's
    ``versions.add_command``)."""
    if (system or os.name) == "nt":
        return f"& ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --add {version}"
    return f"{INSTALL} -s -- --add {version}"


# A release as PEP 440 spells one (the library's ``contract._RELEASE``), and a development build's name,
# ``<release>-dev.<stamp>`` (the server's ``versions.DEVELOPMENT``): how ``order`` reads a version.
_RELEASE = re.compile(
    r"v?(?:(?P<epoch>\d+)!)?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-_.]?(?P<pre>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>\d+)?)?"
    r"(?:-(?P<post_n1>\d+)|[-_.]?(?P<post>post|rev|r)[-_.]?(?P<post_n2>\d+)?)?"
    r"(?:[-_.]?(?P<dev>dev)[-_.]?(?P<dev_n>\d+)?)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?")
_PRE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_DEVELOPMENT = re.compile(r"(?P<release>.+)-dev\.(?P<stamp>[0-9]+)")
_LAST, _FIRST = float("inf"), float("-inf")


def order(name: str) -> tuple[Any, ...] | None:
    """Where version ``name`` sorts among versions, or None for a name that is no release: the server's
    ``versions.order``, copied and held equal by a test. Releases sort as PEP 440 sorts them; a development build,
    ``<release>-dev.<stamp>``, after the release whose numbers it carries and before the next."""
    built = _DEVELOPMENT.fullmatch(name or "")
    found = _RELEASE.fullmatch((built["release"] if built else name or "").strip().lower())
    if found is None:
        return None
    numbers = [int(part) for part in found["release"].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    post = found["post"] is not None or found["post_n1"] is not None
    dev = found["dev"] is not None
    if found["pre"] is not None:
        pre: tuple[Any, ...] = (_PRE[found["pre"]], int(found["pre_n"] or 0))
    else:
        pre = (_FIRST,) if dev and not post else (_LAST,)
    base = (int(found["epoch"] or 0), tuple(numbers), pre,
            (int(found["post_n1"] or found["post_n2"] or 0),) if post else (_FIRST,),
            (int(found["dev_n"] or 0),) if dev else (_LAST,))
    return (*base, (1, int(built["stamp"])) if built else (0, 0))


def older(one: str, other: str) -> bool:
    """Whether version ``one`` is older than ``other`` (``order``); a name that is no release is older than none
    and newer than none."""
    first, second = order(one), order(other)
    return first is not None and second is not None and first < second


def stale_line(version: str, channel: str | None, now: str | None) -> str:
    """What a transport whose channel moved past its version answers with, in one sentence: first which version this
    is (the transport is that version) and which its channel is on now (``now``; None where the pointer could not be
    read again: a newer one), the channel's half in the same words as the server's ``pins.channel_now`` (held equal by
    a test); then the repair for a tool call in a thread
    whose transport is old, cheapest first: a new thread, which starts the app's newer copy where it has one; then,
    where a new thread says the same, the app's copy brought up: ``cad update`` for the default channel, the plugin's
    update in the app that delivered it for a named one."""
    head = (f"this is text-to-cad {version}, and its channel ({channel or DEFAULT_CHANNEL}) is on "
            + (f"text-to-cad {now} now" if now else "a newer text-to-cad now"))
    repair = "run `cad update`" if channel is None else "update the text-to-cad plugin in the app it came from"
    return f"{head}: start a new thread; if a new thread says the same, {repair}"


def installing_line(version: str) -> str:
    """What a transport answers while its version is being installed, or its channel moved to it (``prepare``)."""
    return f"text-to-cad {version} is being installed on this computer: try again shortly"


def stale() -> str | None:
    """The line this transport answers with once its channel has moved past its version (``stale_line``): its
    channel's pointer, read now, names a newer version (``older``), or preparing it found so; else None."""
    pin = PIN
    if pin.version is None:
        return None
    if pin.stale is not None:
        return pin.stale
    now = pointer(pin.channel)
    return stale_line(pin.version, pin.channel, now) if now is not None and older(pin.version, now) else None


def unavailable(wait: float = 0.0) -> tuple[str, str] | None:
    """Why this transport cannot reach its server now, as ``(INSTALLING | STALE | FAILED, line)``, or None when it
    can: stale is said at once, whatever preparing is doing; else its version is waited for at most ``wait``
    seconds, and is still being installed past them, or could not be made ready."""
    line = stale()
    if line is not None:
        return STALE, line
    if not PIN.ready.wait(wait):
        return INSTALLING, installing_line(PIN.version or "")
    if PIN.failed is not None:
        return FAILED, PIN.failed
    line = stale()
    return (STALE, line) if line is not None else None


def _cad_environment(version: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    env[INSTALLATION_ENV] = version
    return env


def prepare(pin: Pin | None = None) -> Pin:
    """This transport's version made ready to serve (see the module), once, in the background, as the app starts
    it: ``pin.ready`` set when done, with ``failed`` or ``stale`` where it cannot serve. Its channel's pointer is
    read first: where it names a newer version the transport is stale at once, and nothing is installed or run
    (an app holding an older copy would otherwise install that version again on every thread, only to find it
    stale). Nothing for a transport with no version."""
    pin = pin or PIN
    try:
        if pin.version is None:
            return pin
        now = pointer(pin.channel)
        if now is not None and older(pin.version, now):
            pin.stale = stale_line(pin.version, pin.channel, now)
            return pin
        record = version_record(pin.version)
        if record is None:
            if not re.fullmatch(RELEASED, pin.version):
                pin.failed = (f"text-to-cad {pin.version} is not installed, and it is no release: a development "
                              "version is installed from its own checkout alone")
                return pin
            command = [*LAUNCHER, f"{SERVER}=={pin.version}", "cad", "setup", "--add", "--quiet"]
            said = _run(command, os.environ.copy())
            record = version_record(pin.version)
            if record is None:
                pin.failed = (f"text-to-cad {pin.version} is not installed, and it could not be installed here "
                              f"({said or 'uvx failed'}): run {add_command(pin.version)}")
                return pin
        if pointer(pin.channel) == pin.version:
            return pin
        word = f"+{pin.version}" + (f"@{pin.channel}" if pin.channel else "")
        code, said = _run_code([record["cad"], word, "setup", "--add", "--quiet"], _cad_environment(pin.version))
        if code == STALE_EXIT:  # the channel moved past it while it was installed
            pin.stale = stale_line(pin.version, pin.channel, pointer(pin.channel))
        elif code != 0:
            pin.failed = said or f"text-to-cad {pin.version} could not be started for the {pin.label} channel"
        return pin
    finally:
        pin.ready.set()


def _run(command: list[str], env: dict[str, str]) -> str:
    """``command`` run, quiet: the last line it said on stderr."""
    return _run_code(command, env)[1]


def _run_code(command: list[str], env: dict[str, str]) -> tuple[int, str]:
    """``command`` run, quiet: its exit status (127 when it could not run) and the last line it said."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=PREPARE_SECONDS, **_windowless())
    except (OSError, subprocess.SubprocessError) as error:
        return 127, f"{type(error).__name__}: {error}"
    lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
    said = lines[-1] if lines else ""
    return done.returncode, said.removeprefix("cad: ")


def default_engine_dir() -> str:
    """The engine folder when ``CAD_ENGINE_DIR`` names none: ``$XDG_RUNTIME_DIR/cad-engine``, else
    ``cad-engine`` in the user's own temporary folder (on macOS the one the system names, whatever
    ``TMPDIR`` a sandbox sets), else ``/tmp/cad-<uid>``; on Windows ``cad-engine`` beside the state folder,
    out of the local application data an app package virtualizes. 0.8's engines are in ``cadgen-engine``,
    which this never reads."""
    if WINDOWS:
        return str(_local_state() / "cad-engine")
    for parent in (os.environ.get("XDG_RUNTIME_DIR"), _darwin_temp() or os.environ.get("TMPDIR")):
        if parent and os.path.isabs(parent) and _users_own(parent):
            return os.path.join(parent, "cad-engine")
    return f"/tmp/cad-{os.getuid()}"


def _darwin_temp() -> str | None:
    """macOS's per-user temporary folder as the system names it (``_CS_DARWIN_USER_TEMP_DIR``)."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        buffer = ctypes.create_string_buffer(1024)
        size = ctypes.CDLL(None, use_errno=True).confstr(65537, buffer, len(buffer))
    except (OSError, AttributeError):
        return None
    return os.fsdecode(buffer.value) if 0 < size <= len(buffer) else None


def _users_own(folder: str) -> bool:
    try:
        found = os.stat(folder)
    except OSError:
        return False
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o022


def folder_refusal(folder: Path) -> str | None:
    """Why ``folder`` may not hold the server's door, or None: on POSIX it must be this user's alone."""
    if WINDOWS:
        return None
    try:
        found = os.lstat(folder)
    except OSError as error:
        return f"the engine's folder {folder} cannot be read: {error.strerror or error}"
    if not stat.S_ISDIR(found.st_mode):
        return f"the engine's folder {folder} is not a folder"
    if found.st_uid != os.getuid():
        return (f"the engine's folder {folder} belongs to another user (uid {found.st_uid}): "
                "set CAD_ENGINE_DIR to a folder of your own")
    if found.st_mode & 0o022:
        return (f"the engine's folder {folder} can be written by others (mode {stat.S_IMODE(found.st_mode):o}): "
                "run chmod go-w on it, or set CAD_ENGINE_DIR to a folder of your own")
    return None


def door_path() -> Path:
    return engine_dir() / f"{NAME}.door"


def port_path() -> Path:
    return engine_dir() / f"{NAME}.port"


def failure_path() -> Path:
    return engine_dir() / f"{NAME}.failed"


def address() -> Path:
    """Where the server is reached: its door, on Windows its port file."""
    return port_path() if WINDOWS else door_path()


# --- the installation the device runs ---------------------------------------------------------------


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def current() -> dict[str, Any] | None:
    """The current installation's record while its Python and console script are there, else None."""
    import re

    folder = state_dir()
    data = _read(folder / CURRENT)
    version = data.decode("utf-8", "replace").strip() if data is not None else ""
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", version):
        return None
    try:
        record = json.loads(_read(folder / INSTALLATIONS / f"{version}.json") or b"null")
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("version") != version or not all(
            isinstance(record.get(key), str) for key in ("python", "cad", "prefix")):
        return None
    return record if os.path.isfile(record["python"]) and os.path.isfile(record["cad"]) else None


def register() -> None:
    """On a device with no installation current: the server this transport's environment carries registers
    itself (a release's makes itself current; a checkout's registers nothing), else this transport's own
    release of the server is installed by uvx and registered -- the device's first. Quiet: its words are
    nobody's here, and a failure is the next start's to find (no installation, said by ``connect``)."""
    from cad_mcp import __version__

    if importlib.util.find_spec(SERVER_PACKAGE) is not None:
        command = [sys.executable, "-P", "-m", REGISTER]
    else:
        command = [*LAUNCHER, f"{SERVER}=={__version__}", "python", "-P", "-m", REGISTER]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       **_windowless())
    except OSError:
        pass


# --- the door: a client's half ----------------------------------------------------------------------

CLIENTS = "clients"
# The door protocol this transport speaks (the library's ``cad.engine.door``, which it does not import):
# its hello is ``<id> <protocol>`` and a newline, and the server's greeting ``ok <protocol>`` and a newline,
# the protocol the connection speaks, from 1 (0.8's bare ``ok`` is no greeting). Within a number only
# additions, each a field at the end of its line, which a reader of that number skips; a removal or a
# rename takes a new number.
DOOR_PROTOCOL = 1
ID_CHARACTERS = 32
HELLO_LIMIT = 512
GREETING_SECONDS = 15.0
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class Connection:
    """One connection to the server: the lines it reads (``reader``) and writes (``writer``), and the door
    protocol it speaks (``protocol``, the greeting's)."""

    def __init__(self, reader: BinaryIO, writer: BinaryIO, *closing: Any, protocol: int = DOOR_PROTOCOL) -> None:
        self.reader = reader
        self.writer = writer
        self.closing = closing or (reader, writer)
        self.protocol = protocol

    def close(self) -> None:
        for each in self.closing:
            try:
                each.close()
            except OSError:
                pass

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def _open(path: Path, flags: int) -> int:
    return os.open(path, flags | _NOFOLLOW | _CLOEXEC)


def _ours(fd: int) -> bool:
    found = os.fstat(fd)
    return stat.S_ISFIFO(found.st_mode) and found.st_uid == os.getuid()


def _private(folder: Path) -> bool:
    folder.mkdir(mode=0o700, exist_ok=True)
    found = os.lstat(folder)
    if stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and found.st_mode & 0o077:
        os.chmod(folder, 0o700)
        found = os.lstat(folder)
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o077


def _door_answering(door: Path) -> bool:
    """Whether a server reads ``door``: a FIFO of this user's that takes a writer."""
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        return _ours(fd)
    finally:
        os.close(fd)


def hello(ident: str) -> bytes:
    """The hello: the pair's id (on Windows, the port file's token), a space, this transport's door
    protocol and a newline."""
    return f"{ident} {DOOR_PROTOCOL}\n".encode("ascii")


def greeted(line: bytes) -> int | None:
    """The door protocol the server's greeting says the connection speaks (with or without its
    newline), 1 or more, or None for a line that is no greeting; fields after the number, a later
    release's additions, skipped."""
    word, spaced, rest = line.removesuffix(b"\n").partition(b" ")
    field = rest.split(b" ", 1)[0]
    number = int(field) if word == b"ok" and spaced and 0 < len(field) <= 6 and field.isdigit() else 0
    return number or None


def _knock(door: Path, ident: str, timeout: float) -> bool:
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except PermissionError:
        raise
    except OSError:
        return False
    try:
        if not _ours(fd):
            return False
        line = hello(ident)
        deadline = time.monotonic() + timeout
        while True:
            try:
                return os.write(fd, line) == len(line)
            except BlockingIOError:
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.001)
    finally:
        os.close(fd)


def _greeted(fd: int, door: Path, timeout: float) -> int | None:
    """The door protocol of the server's greeting (``greeted``), read a byte at a time to its newline
    and never past it; None when none comes, or the door goes while it waits."""
    try:
        identity = os.stat(door).st_ino
    except OSError:
        return None
    deadline = time.monotonic() + timeout
    got = b""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while not got.endswith(b"\n"):
            if len(got) >= HELLO_LIMIT:
                return None
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            if selector.select(min(left, 0.2)):
                got += os.read(fd, 1)
                continue
            try:
                if os.stat(door).st_ino != identity:
                    return None
            except OSError:
                return None
            if not _door_answering(door):
                return None
    return greeted(got)


def dial(door: Path, timeout: float = GREETING_SECONDS) -> Connection | None:
    """A connection to the server reading ``door``: a pair of FIFOs in its ``clients`` folder, a hello
    through the door, the greeting, then each FIFO opened for its one direction (the server's door
    protocol). None when none reads it or it never greets."""
    folder = door.parent / CLIENTS
    ident = secrets.token_hex(ID_CHARACTERS // 2)
    up, down = folder / f"{ident}.up", folder / f"{ident}.down"
    opened: list[int] = []

    def take(path: Path, flags: int) -> int:
        fd = _open(path, flags)
        opened.append(fd)
        return fd

    try:
        if not _private(folder):
            return None
        os.mkfifo(up, 0o600)
        os.mkfifo(down, 0o600)
        hold = take(down, os.O_RDWR)
        early = take(up, os.O_RDWR)
        if not _knock(door, ident, timeout):
            return None
        spoken = _greeted(hold, door, timeout)
        if spoken is None or spoken > DOOR_PROTOCOL:  # a protocol this transport does not speak
            return None
        reader = take(down, os.O_RDONLY | os.O_NONBLOCK)
        writer = take(up, os.O_WRONLY | os.O_NONBLOCK)
        if not (_ours(reader) and _ours(writer)):
            return None
        os.set_blocking(reader, True)
        os.set_blocking(writer, True)
        for fd in (hold, early):
            opened.remove(fd)
            os.close(fd)
        opened.clear()
        return Connection(open(reader, "rb"), open(writer, "wb"), protocol=spoken)
    except PermissionError:
        raise
    except OSError:
        return None
    finally:
        for fd in opened:
            os.close(fd)
        for path in (up, down):
            try:
                path.unlink()
            except OSError:
                pass


# --- reaching the server ----------------------------------------------------------------------------


def _port_text(path: Path) -> str:
    for delay in RETRY_DELAYS_SECONDS:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(delay)
    return path.read_text(encoding="utf-8")


def _denied(cause: str) -> ConnectionError:
    return ConnectionError(f"the system denies {SERVER}'s engine ({cause}); a sandbox that forbids "
                           "it does: run this command outside it, or with the sandbox's permission")


def _connect(where: Path | None = None) -> Connection | None:
    """A connection to the server at ``where`` (its door, on Windows its port file; by default the
    device's), or None when none answers there."""
    try:
        if WINDOWS:
            port, token = _port_text(where or port_path()).split()
            connection = socket.create_connection(("127.0.0.1", int(port)), timeout=5)
            stream = connection.makefile("rwb")
            try:  # the door's hello and greeting on the port: the token where a pair's id goes
                connection.settimeout(GREETING_SECONDS)
                stream.write(hello(token))
                stream.flush()
                spoken = greeted(stream.readline(HELLO_LIMIT))
                connection.settimeout(None)
            except OSError:
                spoken = None
            if spoken is None or spoken > DOOR_PROTOCOL:
                stream.close()
                connection.close()
                return None
            return Connection(stream, stream, stream, connection, protocol=spoken)
        door = where or door_path()
        if folder_refusal(door.parent) is not None or not door.exists():
            return None
        return dial(door)
    except PermissionError as error:
        raise _denied(f"opening a pipe in the engine's folder {engine_dir()}: {error.strerror or error}") from None
    except (OSError, ValueError):
        return None


def answering(where: Path) -> bool:
    """Whether a server answers at ``where``, asked without a request."""
    if not WINDOWS:
        return _door_answering(where)
    connection = _connect(where)
    if connection is None:
        return False
    connection.close()
    return True


def _windowless() -> dict[str, Any]:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if WINDOWS else {}


def _detached() -> dict[str, Any]:
    if WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def _same(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def _start() -> subprocess.Popen:
    """The server started, detached. With a version (``PIN``): that version's, from its own Python, told its name,
    and never another version's -- ``ConnectionError`` while it is not installed. With none: the current
    installation's, with its Python; on a device with none, one registered first (``register``); and with none
    still, the one this environment carries, if any."""
    if PIN.version is not None:
        record = version_record(PIN.version)
        if record is None:  # removed once its channel moved on: the thread is stale
            raise ConnectionError(stale() or PIN.failed or f"text-to-cad {PIN.version} is not installed on this "
                                                           f"computer: run {add_command(PIN.version)}")
        env = {name: value for name, value in _cad_environment(PIN.version).items() if name not in PER_PROCESS}
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # its server keeps its bytecode in its own code once it runs
        folder = engine_dir()
        cwd = (str(folder) if folder.is_dir() else None) if not WINDOWS else (
            str(folder.parent) if folder.parent.exists() else None)
        return subprocess.Popen([record["python"], "-P", "-m", DAEMON_MODULE], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=cwd, **_detached())
    found = current()
    if found is None:
        register()
        found = current()
    if found is not None:
        python, own = found["python"], _same(found["prefix"], sys.prefix)
    elif importlib.util.find_spec(SERVER_PACKAGE) is not None:
        python, own = sys.executable, True
    else:
        raise ConnectionError(f"no CAD server is installed on this computer, and installing {SERVER} "
                              "failed: run the install command, `curl -fsSL https://texttocad.dev/install.sh | sh`")
    env = {name: value for name, value in os.environ.items() if name not in PER_PROCESS}
    if not own:
        env.pop("PYTHONPATH", None)  # another installation imports its own server
    # Nothing written beside a library: the server keeps its bytecode in the cache folder once it runs.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    folder = engine_dir()
    cwd = (str(folder) if folder.is_dir() else None) if not WINDOWS else (
        str(folder.parent) if folder.parent.exists() else None)
    return subprocess.Popen([python, "-P", "-m", DAEMON_MODULE], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=cwd, **_detached())


def _not_started(code: int) -> ConnectionError:
    try:
        note = json.loads(failure_path().read_text(encoding="utf-8"))
        reason, denied = str(note["reason"]), bool(note.get("denied"))
    except (OSError, ValueError, KeyError, TypeError):
        reason, denied = f"it exited with code {code}", False
    if denied:
        return ConnectionError(f"{SANDBOXED} ({reason})")
    return ConnectionError(f"the engine server did not start: {reason}")


# One start at a time in this process: the hold (``shim.Holder``) and the host's first request both find no
# server on a device's first start, and two starts would register two installations at once.
_STARTING = threading.Lock()


def connect(*, start: bool = True, timeout: float = 60.0, wait: float = 0.0) -> Connection | None:
    """A connection to the server, started when ``start`` and none answers: by one thread of this process
    at a time, a thread that waited for another's start taking the server it started. With a version, only once it
    is ready (``prepare``, waited for at most ``wait`` seconds) and its channel's: ``ConnectionError`` saying why
    where it cannot serve now (``unavailable``) -- a stale transport never connects, nor starts a server."""
    why = unavailable(wait)
    if why is not None:
        raise ConnectionError(why[1])
    found = _connect()
    if found is not None or not start:
        return found
    if any(os.environ.get(name) == value for name, value in SANDBOXES):
        raise ConnectionError(SANDBOXED)
    with _STARTING:
        found = _connect()
        if found is not None:
            return found
        return _started(timeout)


def _started(timeout: float) -> Connection:
    """The server started (``_start``) and a connection to it once it answers."""
    try:
        engine_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as error:
        raise _denied(f"making the engine's folder: {error.strerror or error}") from None
    refusal = folder_refusal(engine_dir())
    if refusal is not None:
        raise ConnectionError(refusal)
    try:
        failure_path().unlink(missing_ok=True)
    except PermissionError as error:
        raise _denied(f"writing in the engine's folder: {error.strerror or error}") from None
    process = _start()
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        found = _connect()
        if found is not None:
            return found
        time.sleep(0.02)
        if process.poll():
            raise _not_started(process.returncode)
        if time.monotonic() - started > 1.0 and process.poll() == 0:
            process = _start()  # one stopping held the lock, and the one started left at once
            started = time.monotonic()
    raise ConnectionError("the engine server did not start")


def _line(connection: Connection, seconds: float | None = None) -> bytes:
    """The next line the server sends on ``connection`` (empty once it closed it), waited for at most ``seconds``
    (``DOOR_SECONDS``): ``ConnectionError`` past them, so a server that stopped answering never holds a request. Read
    a byte at a time, never past its newline, so whatever reads the connection next reads from where it ends."""
    seconds = DOOR_SECONDS if seconds is None else seconds
    deadline = time.monotonic() + seconds
    late = ConnectionError(f"the engine server did not answer within {seconds:g} seconds")
    if WINDOWS:  # the port's socket: its own timeout, and none again after
        sock = next((each for each in connection.closing if isinstance(each, socket.socket)), None)
        if sock is None:
            return connection.reader.readline()
        sock.settimeout(seconds)
        try:
            return connection.reader.readline()
        except TimeoutError:
            raise late from None
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass
    fd = connection.reader.fileno()
    got = b""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while not got.endswith(b"\n"):
            left = deadline - time.monotonic()
            if left <= 0 or not selector.select(left):
                raise late
            byte = os.read(fd, 1)
            if not byte:
                break
            got += byte
    return got


def _exchange(connection: Connection, message: dict[str, Any], where: Path | None = None) -> dict[str, Any]:
    if WINDOWS:  # the token in the request too, first, which the server checks as it did the hello's
        message = {"token": (where or port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        while line := _line(connection):
            answer = json.loads(line)
            if "log" in answer or set(answer) == {"progress"}:
                continue
            answer.pop("notice", None)
            return answer
    raise ConnectionError("the engine server closed the connection")


def request(message: dict[str, Any], *, start: bool = True) -> dict[str, Any] | None:
    """One request and its answer; None when no server runs and ``start`` is false."""
    connection = connect(start=start)
    if connection is None:
        return None
    return _exchange(connection, message)


def hold(*, start: bool = True, host: Callable[[], str | None] | None = None,
         holder: str | None = None) -> Connection | None:
    """A hold on the server, started when ``start`` and none runs: while the connection returned stays open
    the server counts this transport, and when it drops the server ends the sessions opened under
    ``holder``. ``host()``, asked once the server answers, names the agent app it serves."""
    connection = connect(start=start)
    if connection is None:
        return None
    try:
        message: dict[str, Any] = {"op": "hold"}
        named = host() if host is not None else None
        if named:
            message["host"] = named
        if holder:
            message["holder"] = holder
        if PIN.channel:
            message["channel"] = PIN.channel  # a named channel's, as every request of a pinned command says it
        if WINDOWS:
            message = {"token": port_path().read_text(encoding="utf-8").split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        if json.loads(_line(connection) or b"{}").get("ok") is not True:
            raise ConnectionError("the engine server did not take the hold")
    except BaseException:
        connection.close()
        raise
    return connection


# --- its HTTP endpoint ------------------------------------------------------------------------------


def _door(where: Path | None = None) -> Any:
    """Which server the door at ``where`` names now (its identity), or None when none answers there."""
    where = where or address()
    try:
        found = os.stat(where)
    except OSError:
        return None
    if WINDOWS:
        return found.st_ino, found.st_mtime_ns, found.st_size
    return (found.st_dev, found.st_ino) if answering(where) else None


class EngineClient:
    """The server's loopback endpoint as its door last named it, used only while that door still answers:
    a loopback port is anyone's once the server has let it go, and every call carries the user's page
    token. It is read from the door again whenever it may be stale: the server gone or replaced, after any
    answer that is not a success, after a connection error, and for a call that asks for a ``fresh`` one
    (an MCP ``initialize``)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.endpoint: dict[str, Any] | None = None
        self.door: Any = None
        self.address: Path | None = None

    def connect(self, *, fresh: bool = False, start: bool = True) -> dict[str, Any]:
        with self.lock:
            if self.endpoint is not None and not fresh and (self.door is None or _door(self.address) != self.door):
                self.endpoint = None
            if self.endpoint is None or fresh:
                self.endpoint = None
                answer = request({"op": "http"}, start=start)
                if not answer or "failed" in answer:
                    raise ConnectionError((answer or {}).get("failed", "engine did not answer"))
                self.address = address()
                self.endpoint, self.door = answer, _door(self.address)
            return self.endpoint

    def forget(self) -> None:
        with self.lock:
            self.endpoint = None

    def _forget(self, endpoint: dict[str, Any]) -> None:
        with self.lock:
            if self.endpoint is endpoint:
                self.endpoint = None

    def call(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None, *,
             fresh: bool = False, start: bool = True) -> tuple[int, dict[str, str], bytes]:
        endpoint = self.connect(fresh=fresh, start=start)
        for attempt in (1, 2):
            parsed = urlsplit(endpoint["url"])
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=600)
            try:
                conn.request(method, path, body=body, headers={**(headers or {}),
                             "Authorization": "Bearer " + endpoint["token"]})
                response = conn.getresponse()
                answer = response.status, dict(response.getheaders()), response.read()
            except ConnectionRefusedError:
                self._forget(endpoint)
                if attempt == 2:
                    raise
                endpoint = self.connect(fresh=True, start=start)
                continue
            except (OSError, http.client.HTTPException):
                self._forget(endpoint)
                raise
            finally:
                conn.close()
            if not 200 <= answer[0] < 300:
                self._forget(endpoint)
                if attempt == 1 and answer[0] == 403 and b"engine token required" in answer[2]:
                    endpoint = self.connect(fresh=True, start=start)
                    continue
            return answer
        raise ConnectionError("the engine server did not answer")
