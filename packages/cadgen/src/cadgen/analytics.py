"""Anonymous usage analytics for ``cadgen mcp``: how many people use CAD, how often, and on how
many files -- counts, times and metadata, never what anything says.

What is sent, at most once a minute while there is something new and once more as the server
exits, each batch stamped with the time it arrives:

- who, anonymously: a random install id, and a random id for this server process;
- what runs: cadgen's version, how it was installed, the operating system and processor, the
  agent app's name and version, and how that app shows CAD (tabs, inline or text);
- ``tool``: how many times each CAD tool was called, and how many of those failed;
- ``view``: how many times a CAD view was touched by a person or switched models -- time spent
  looking at a model calls no tool, and is use all the same;
- ``file``: each distinct file a CAD view put on screen, once a day per server process, as a
  16-character code (an HMAC of its absolute path keyed by a random salt made on this machine
  and never sent) and its format (``step``, ``stl``, ...). The receiver can count distinct
  files and see one come back on another day; it cannot learn a path, a name or what is in a
  file, and a code means nothing on any other machine.

Never a path, a file name, a model, an argument, a prompt or anything typed. A batch with
nothing used in it is never sent: a server the host started and nobody used counts for
nothing. The receiver (``ENDPOINT``) is ours, so the service behind it can change without a
release.

Nothing is sent without the person's yes, however CAD was installed. Strongest first:

1. The environment: ``DO_NOT_TRACK=1`` or ``CADGEN_ANALYTICS=0`` turns it off,
   ``CADGEN_ANALYTICS=1`` on.
2. The person's choice, kept in the state directory (``analytics.json``): the CAD app's
   prompt or its Settings, ``cadgen analytics on|off``, or the agent's ``cad_analytics``
   (off only).
3. Otherwise nothing is sent, and the CAD app asks once.

How CAD was installed (``cadgen mcp --install store``, a plugin directory's) is only
reported, as ``source``: it decides nothing.

The install id and the file salt exist only while sharing is on: turning it off deletes both
here and asks the receiver to delete what it holds under the id -- again and again until it
hears back -- and turning it on again starts a new install with a new salt, so nothing links
the two.

Analytics never get in the way of CAD:

- Nothing here raises into the server. Every ``Recorder`` method is guarded: a failure (an
  unreadable state directory, a broken receiver, a bug here) is logged at debug level, below
  what ``cadgen mcp`` prints, so nothing reaches a host's or an agent's logs, and answered
  with a safe default: not sharing, nothing sent, nothing asked.
- No tool call waits on the network. Noting use is in memory; sending, and the deletion an
  opt-out asks for, run on a background thread. The one wait is the last send as the server
  exits, bounded by ``CLOSE_SECONDS``.
- A batch the receiver did not take (offline, a slow or broken receiver) is kept for the next
  one; it is never an error.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json
import logging
import os
import platform as _platform
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

LOG = logging.getLogger("cadgen.analytics")

ENDPOINT = "https://api.texttocad.dev/v1"
PRIVACY_URL = "https://www.texttocad.dev/privacy-policy"
SCHEMA = 1
# What a yes agreed to: the fields and events this module sends. Raise it when that grows, and the
# CAD app asks again everyone whose yes was to less; a no stays a no. Restarts and updates that
# send nothing new keep the answer: it lives in the person's state directory, not the install.
DISCLOSURE = 1
FLUSH_SECONDS = 60
TIMEOUT_SECONDS = 3
CLOSE_SECONDS = 2  # the most an exiting server waits for its last send
INSTALLS = ("store",)  # what `cadgen mcp --install` may name, reported as `source`; a manual install names none
# The page's plumbing: a view's once-a-second sync, its viewer requests, its capture replies and
# the home's re-reads of its library every couple of seconds say nothing about use and would
# drown what does. A view's own activity is noted from its sync instead (``viewed``, ``opened``).
UNCOUNTED = frozenset({"cad_sync", "cad_http", "cad_capture_reply", "cad_consent", "cad_recents"})
# A file's format, by extension: what the viewer opens (``cadgen.viewer.scanner.SOURCE_EXTENSIONS``).
FILE_KINDS = {".step": "step", ".stp": "step", ".stl": "stl", ".3mf": "3mf", ".glb": "glb", ".dxf": "dxf",
              ".urdf": "urdf", ".srdf": "srdf", ".sdf": "sdf"}
FILES_PER_BATCH = 32  # more wait for the next batch: the receiver takes 64 events at most
FILES_PENDING = 1024  # past this, a process notes no new file until a batch goes
# What a status is when it cannot be read: not sharing, and not asking either (a broken state
# directory must not nag on every view).
UNAVAILABLE = {"sharing": False, "reason": "unavailable", "id": None}

_OFF, _ON = ("0", "off", "false", "no"), ("1", "on", "true", "yes")


def state_path() -> Path:
    from cadgen.viewer.recents import state_dir

    return state_dir() / "analytics.json"


def endpoint() -> str:
    """The receiver: ``CADGEN_ANALYTICS_URL`` (for a local receiver) when it is http(s), else ours."""
    override = str(os.environ.get("CADGEN_ANALYTICS_URL") or "").strip().rstrip("/")
    return override if override.startswith(("https://", "http://")) else ENDPOINT


def _read(path: Path) -> dict[str, Any]:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _write(path: Path, kept: dict[str, Any]) -> None:
    # Named for this process and thread: the server's background sender and a tool call may both write.
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(kept), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:  # a state directory it cannot write leaves the choice unmade
        LOG.debug("could not keep the analytics choice in %s", path, exc_info=True)
        try:
            temporary.unlink()
        except OSError:
            pass


def _environment() -> bool | None:
    if str(os.environ.get("DO_NOT_TRACK") or "").strip().lower() in _ON:
        return False
    value = str(os.environ.get("CADGEN_ANALYTICS") or "").strip().lower()
    return False if value in _OFF else True if value in _ON else None


def _disclosure(kept: dict[str, Any]) -> int:
    value = kept.get("disclosure")
    return value if isinstance(value, int) else 0


def _pending(kept: dict[str, Any]) -> list[str]:
    value = kept.get("forget")
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _new_salt() -> str:
    return os.urandom(32).hex()


def _is_salt(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def status(*, path: Path | None = None) -> dict[str, Any]:
    """``{sharing, reason, id}``: whether counts are sent, why, and under which install id.

    ``reason`` is ``environment``, ``choice`` or ``unasked`` (nothing is sent, and the CAD app asks).
    Sharing makes the install's id and file salt where they are missing.
    """
    path = path or state_path()
    kept = _read(path)
    forced = _environment()
    if forced is not None:
        sharing, reason = forced, "environment"
    elif kept.get("choice") == "off" or (kept.get("choice") == "on" and _disclosure(kept) >= DISCLOSURE):
        sharing, reason = kept["choice"] == "on", "choice"
    else:
        sharing, reason = False, "unasked"
    install_id = kept.get("id") if isinstance(kept.get("id"), str) else None
    if sharing and (install_id is None or not _is_salt(kept.get("salt"))):
        install_id = install_id or str(uuid.uuid4())
        _write(path, {**kept, "id": install_id, "salt": kept["salt"] if _is_salt(kept.get("salt")) else _new_salt()})
    return {"sharing": sharing, "reason": reason, "id": install_id if sharing else None}


def file_salt(path: Path | None = None) -> bytes | None:
    """This install's file salt: made with its id, never sent, gone when sharing is turned off."""
    value = _read(path or state_path()).get("salt")
    return bytes.fromhex(value) if _is_salt(value) else None


def file_code(salt: bytes, path: str) -> str:
    """A file's code: the first 16 hex characters of an HMAC-SHA256 of its absolute path under ``salt``."""
    return hmac.new(salt, os.path.abspath(path).encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()[:16]


def choose(share: bool, *, by: str, path: Path | None = None,
           forget: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Keep the person's choice. Turning sharing off deletes the install id and file salt here and
    asks the receiver, through ``forget``, to delete what it holds under the id (``forgotten``:
    whether it said it did). Without ``forget`` -- the server's way, which never waits on the
    network (``Recorder.choose``) -- or until the receiver answers, the id waits as ``forget``,
    used for nothing else, and every flush asks again (``forget_pending``)."""
    path = path or state_path()
    kept = _read(path)
    previous = kept.get("id") if isinstance(kept.get("id"), str) else None
    pending = _pending(kept)
    choice = {"choice": "on" if share else "off", "disclosure": DISCLOSURE, "by": by, "decidedAt": int(time.time())}
    if share:
        salt = kept["salt"] if previous and _is_salt(kept.get("salt")) else _new_salt()
        _write(path, {**choice, "id": previous or str(uuid.uuid4()), "salt": salt,
                      **({"forget": pending} if pending else {})})
        return {"sharing": True}
    forgotten = bool(previous) and forget is not None and forget(previous)
    if previous and not forgotten:
        pending.append(previous)
    _write(path, {**choice, **({"forget": pending} if pending else {})})
    return {"sharing": False, "forgotten": forgotten}


def forget_pending(*, path: Path | None = None, forget: Callable[[str], bool] | None = None) -> None:
    """Ask the receiver again to delete what it holds under ids turned off while it was not asked or not reached."""
    path = path or state_path()
    pending = _pending(_read(path))
    if not pending:
        return
    left = [value for value in pending if not (forget or request_deletion)(value)]
    kept = _read(path)  # the choice may have changed meanwhile: keep it, change only the list
    if left:
        kept["forget"] = left
    else:
        kept.pop("forget", None)
    _write(path, kept)


def _post(url: str, payload: dict[str, Any] | None = None, *, method: str = "POST") -> bool:
    try:
        import urllib.request

        data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"Content-Type": "application/json", "User-Agent": "cadgen"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`endpoint`)
            return 200 <= response.status < 300
    except Exception:  # noqa: BLE001 - analytics never fail anything
        LOG.debug("analytics %s %s failed", method, url, exc_info=True)
        return False


def request_deletion(install_id: str) -> bool:
    """Ask the receiver to delete what it holds under ``install_id``: whether it said it did. Waits on the network."""
    # In the body, never the path: the receiver's host logs each request's path beside its IP address.
    return _post(f"{endpoint()}/forget", {"install": install_id})


def _token(value: Any, limit: int) -> str:
    """A short token the receiver takes (ASCII letters, digits and ``_.+:-``, as its own check reads
    them): a host's free-text name is kept recognisable, never refused."""
    return re.sub(r"[^A-Za-z0-9_.+:-]+", "-", str(value or "").strip())[:limit]


def _platform_name() -> str:
    return sys.platform if sys.platform in ("darwin", "win32") else "linux" if sys.platform.startswith("linux") else "other"


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _guarded(default: Callable[[], Any]):
    """Never raise into the server: a failure is a debug line and ``default()``."""
    def decorate(method):
        @functools.wraps(method)
        def guarded(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except Exception:  # noqa: BLE001 - analytics never fail what they count
                LOG.debug("analytics %s failed", method.__name__, exc_info=True)
                return default()
        return guarded
    return decorate


class Recorder:
    """Notes one server process's use -- tool calls, view activity, files on screen -- and sends it
    while sharing is on. Every method is guarded (see the module docstring): it never raises, and
    none but ``close`` waits on the network."""

    def __init__(self, *, install: str | None = None, path: Path | None = None,
                 send: Callable[[dict[str, Any]], bool] | None = None, interval: float = FLUSH_SECONDS) -> None:
        self.install = install if install in INSTALLS else None
        self.path = path
        self._send = send or (lambda payload: _post(f"{endpoint()}/events", payload))
        self._interval = interval
        self._lock = threading.Lock()
        self._session = str(uuid.uuid4())
        self._context: dict[str, Any] = {"version": "unknown", "source": self.install or "manual", "platform": "other"}
        self._counts: dict[str, list[int]] = {}  # tool -> [calls, errors]
        self._views = 0
        self._files: dict[str, str] = {}  # absolute path -> kind; paths never leave this process
        self._sent: set[str] = set()  # "day:code" of files sent today: each goes once a day
        self._timer: threading.Event | None = None
        self._describe()

    @_guarded(lambda: None)
    def _describe(self) -> None:
        from cadgen import __version__

        self._context.update(version=_token(__version__, 32) or "unknown", platform=_platform_name(),
                             arch=_token(_platform.machine().lower(), 16))

    @_guarded(lambda: dict(UNAVAILABLE))
    def status(self) -> dict[str, Any]:
        return status(path=self.path)

    @_guarded(lambda: dict(UNAVAILABLE))
    def choose(self, share: bool, *, by: str) -> dict[str, Any]:
        """The person's click or the agent's off: kept now, and any deletion it owes asked for in the background."""
        with self._lock:  # nothing noted before a choice is sent after it
            self._counts.clear()
            self._views = 0
            self._files.clear()
        chosen = choose(share, by=by, path=self.path)  # forget=None: the id waits as pending
        if not share:
            self._background(lambda: forget_pending(path=self.path))
        return chosen

    @_guarded(lambda: None)
    def started(self, *, client: dict[str, Any], presentation: str) -> None:
        name, version = client.get("name"), client.get("version")
        with self._lock:
            self._context["client"] = {"name": _token(name or "unknown", 64), "version": _token(version, 32)}
            self._context["presentation"] = presentation

    @_guarded(lambda: None)
    def called(self, tool: str, ok: bool) -> None:
        # Noted in memory only: a flush without consent drops it (and reads nothing until then).
        if tool in UNCOUNTED:
            return
        with self._lock:
            calls = self._counts.setdefault(tool, [0, 0])
            calls[0] += 1
            calls[1] += 0 if ok else 1

    @_guarded(lambda: None)
    def viewed(self) -> None:
        """A person touched a CAD view, or it switched models."""
        with self._lock:
            self._views += 1

    @_guarded(lambda: None)
    def opened(self, path: Any) -> None:
        """A CAD view has this file on screen: noted by path here, sent only as its code."""
        if not isinstance(path, str) or not path:
            return
        kind = FILE_KINDS.get(os.path.splitext(path)[1].lower())
        if kind is None:
            return
        with self._lock:
            if path in self._files or len(self._files) < FILES_PENDING:
                self._files[path] = kind

    @_guarded(lambda: False)
    def flush(self) -> bool:
        """Send what was used since the last batch, if sharing is on; drop it if not. A deletion still owed
        is asked for first. A batch with no use in it is not sent. It waits on the network: only the
        background sender and ``close`` call it."""
        forget_pending(path=self.path)
        found = self.status()
        salt = file_salt(self.path) if found["sharing"] else None
        day = _day()
        with self._lock:
            counts, views, files = self._counts, self._views, self._files
            self._counts, self._views, self._files = {}, 0, {}
            context = dict(self._context)
            if not found["sharing"] or salt is None:
                return False
            self._sent = {entry for entry in self._sent if entry.startswith(f"{day}:")}
            fresh = [(path, kind, file_code(salt, path)) for path, kind in files.items()]
            fresh = [(path, kind, code) for path, kind, code in fresh if f"{day}:{code}" not in self._sent]
            sending, later = fresh[:FILES_PER_BATCH], fresh[FILES_PER_BATCH:]
            for path, kind, _ in later:  # past the batch's room: the next batch's
                self._files.setdefault(path, kind)
        events: list[dict[str, Any]] = [{"name": "tool", "tool": tool, "calls": calls, "errors": errors}
                                        for tool, (calls, errors) in sorted(counts.items())]
        if views:
            events.append({"name": "view", "calls": views})
        events += [{"name": "file", "file": code, "kind": kind} for _, kind, code in sending]
        if not events:
            return False
        sent = bool(self._send({"schema": SCHEMA, "install": found["id"], "session": self._session, **context,
                                "events": events}))
        with self._lock:
            if sent:
                self._sent.update(f"{day}:{code}" for _, _, code in sending)
            else:  # kept for the next batch, added to whatever came since
                for tool, (calls, errors) in counts.items():
                    kept = self._counts.setdefault(tool, [0, 0])
                    kept[0] += calls
                    kept[1] += errors
                self._views += views
                for path, kind, _ in sending:
                    self._files.setdefault(path, kind)
        return sent

    @_guarded(lambda: None)
    def start(self) -> None:
        """Send once a minute, in the background, until ``close``."""
        stop = self._timer = threading.Event()

        def loop() -> None:
            while not stop.wait(self._interval):
                self.flush()

        threading.Thread(target=loop, name="cadgen-analytics", daemon=True).start()

    @_guarded(lambda: None)
    def close(self) -> None:
        """The last send, as the server exits: waited for at most ``CLOSE_SECONDS``, then left behind."""
        if self._timer is not None:
            self._timer.set()
        self._background(self.flush).join(CLOSE_SECONDS)

    def _background(self, work: Callable[[], Any]) -> threading.Thread:
        def run() -> None:
            try:
                work()
            except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
                LOG.debug("analytics background work failed", exc_info=True)

        thread = threading.Thread(target=run, name="cadgen-analytics-once", daemon=True)
        thread.start()
        return thread
