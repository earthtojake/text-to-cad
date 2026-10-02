"""Anonymous usage analytics for CAD's two apps -- ``cadgen mcp`` (the CAD app in an agent app) and
``cadgen viewer`` (the browser viewer): how many people use CAD, how often, and on how many files --
counts, times and metadata, never what anything says. Every CAD task shows its model in one or the
other, so between them they see CAD's use; the CLI and the library send nothing.

What is sent, at most once a minute while there is something new and once more as the server
exits, each batch stamped with the time it arrives:

- who, anonymously: a random install id, and a random id for this server process;
- what runs: cadgen's version, how it was installed, the operating system and processor, the
  agent app's name and version and how that app shows CAD (tabs, inline or text) -- or, from the
  browser viewer, ``cadgen-viewer`` and ``browser``;
- ``tool``: how many times each CAD tool was called, and how many of those failed;
- ``view``: how many times a CAD view was touched by a person or switched models -- time spent
  looking at a model calls no tool, and is use all the same;
- ``file``: each distinct file the agent showed or a person touched in a CAD view (a view left
  open on a model notes nothing), once a day per server process, as a
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
2. The person's choice, kept as the ``analytics`` section of their settings (``cadgen/settings.py``:
   ``settings.json`` in the state directory) and shared by both apps:
   either app's card or its Settings, ``cadgen analytics on|off``, or the agent's
   ``cad_analytics`` (off only).
3. Otherwise nothing is sent, and whichever app the person opens first asks once.

A no, or closing the card, is kept like a yes and never asked again: not after a restart, not
after an update, not when what is sent grows (``DISCLOSURE`` re-asks only a yes). Where an answer
could not be kept -- a state directory nothing can write -- the CAD app does not ask at all.

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
  one; it is never an error. One it refused (a 4xx) is dropped: it would be refused again, and
  take everything after it down with it.

The answer is changed only under the settings lock (``settings.update_section``), so the CAD app
and the browser viewer answering, opting out or making the install's id at once never undo one
another. A settings file that is there but cannot be read counts as no answer that can be kept
("unavailable"), never as no answer yet, and is never written back over.
"""

from __future__ import annotations

import contextlib
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

from cadgen._internal.atomic_replace import temp_suffix
from cadgen._internal.file_lock import exclusive
from cadgen.settings import LOCK, read_section, settings_path, update_section

LOG = logging.getLogger("cadgen.analytics")

ENDPOINT = "https://api.texttocad.dev/v1"
PRIVACY_URL = "https://www.texttocad.dev/privacy-policy"
SCHEMA = 1
# What a yes agreed to: the fields and events this module sends. Raise it when that grows, and the
# CAD app asks again everyone whose yes was to less; a no stays a no. Restarts and updates that
# send nothing new keep the answer: it lives in the person's state directory, not the install.
DISCLOSURE = 1
FLUSH_SECONDS = 60
# How long a send waits for the receiver. Sends run in the background, so this delays nothing; a
# shorter wait would give up on a batch a cold receiver was still storing, and send it twice.
TIMEOUT_SECONDS = 10
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


def endpoint() -> str:
    """The receiver: ``CADGEN_ANALYTICS_URL`` (for a local receiver) when it is http(s), else ours."""
    override = str(os.environ.get("CADGEN_ANALYTICS_URL") or "").strip().rstrip("/")
    return override if override.startswith(("https://", "http://")) else ENDPOINT


SECTION = "analytics"  # this module's part of the settings file


def _read(path: Path) -> dict[str, Any] | None:
    """The analytics section, or ``None`` when the settings are there but cannot be read now."""
    try:
        return read_section(SECTION, path=path)
    except OSError:
        LOG.debug("could not read the analytics choice in %s", path, exc_info=True)
        return None


_UNKEPT: set[Path] = set()  # settings a write failed for in this process: it asks about them no more


def _update(path: Path, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any] | None:
    """Change the analytics section under the settings lock: what is kept, or ``None`` when it
    could not be read or written -- and then this process stops asking (``_can_keep``)."""
    try:
        return update_section(SECTION, change, path=path)
    except OSError:
        LOG.debug("could not keep the analytics choice in %s", path, exc_info=True)
        _UNKEPT.add(path)
        return None


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


def _identified(kept: dict[str, Any]) -> bool:
    return isinstance(kept.get("id"), str) and _is_salt(kept.get("salt"))


def _decide(kept: dict[str, Any], forced: bool | None) -> tuple[bool, str | None]:
    """Whether to share, and why (``None``: nothing decided, so the question is still open)."""
    if forced is not None:
        return forced, "environment"
    if kept.get("choice") == "off":
        return False, "choice"
    if kept.get("choice") == "on" and _disclosure(kept) >= DISCLOSURE:
        return True, "choice"
    return False, None


def _without(kept: dict[str, Any], done: list[str]) -> dict[str, Any]:
    """The section with ``done`` no longer owed a deletion."""
    left = [value for value in _pending(kept) if value not in done]
    kept = {key: value for key, value in kept.items() if key != "forget"}
    return {**kept, "forget": left} if left else kept


_KEEPS: set[Path] = set()  # state files whose folder took a file in this process


def _can_keep(path: Path) -> bool:
    """Whether an answer could be written to ``path``, found by doing what a write does -- a file
    beside it, and the settings lock opened and held -- rather than by ``os.access``, which calls
    every folder writable on Windows. A folder that passed is not tried again in this process, one
    that refused is, every time it matters; once a write has failed after all, this process asks
    no more (``_UNKEPT``)."""
    if path in _UNKEPT:
        return False
    if path in _KEEPS:
        return True
    try:
        if path.exists() and not os.access(path, os.W_OK):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.with_name(f"{path.name}{temp_suffix()}")
        probe.write_bytes(b"")
        try:
            with exclusive(path.with_name(LOCK)):
                pass
        finally:
            with contextlib.suppress(OSError):
                probe.unlink()
    except OSError:
        return False
    _KEEPS.add(path)
    return True


def status(*, path: Path | None = None) -> dict[str, Any]:
    """``{sharing, reason, id}``: whether counts are sent, why, and under which install id.

    ``reason`` is ``environment``, ``choice``, ``unasked`` (nothing is sent, and the CAD app asks) or
    ``unavailable`` (nothing is sent, and nobody is asked: no answer could be kept).
    Sharing makes the install's id and file salt where they are missing.
    """
    path = path or settings_path()
    forced = _environment()
    kept = _read(path)
    if kept is None:  # there, but unreadable now: neither sent under nor asked about
        return {"sharing": False, "reason": "environment", "id": None} if forced is False else dict(UNAVAILABLE)
    sharing, reason = _decide(kept, forced)
    if reason is None:  # an answer that could not be kept would be asked for again on every view
        return {"sharing": False, "reason": "unasked" if _can_keep(path) else "unavailable", "id": None}
    if sharing and not _identified(kept):
        def identify(section: dict[str, Any]) -> dict[str, Any]:
            if not _decide(section, forced)[0] or _identified(section):  # changed meanwhile: as it is now
                return section
            install_id = section["id"] if isinstance(section.get("id"), str) else str(uuid.uuid4())
            return {**section, "id": install_id, "salt": section["salt"] if _is_salt(section.get("salt")) else _new_salt()}

        kept = _update(path, identify)
        if kept is None:
            return dict(UNAVAILABLE)
        sharing, reason = _decide(kept, forced)
        if sharing and not _identified(kept):
            return dict(UNAVAILABLE)
    return {"sharing": sharing, "reason": reason, "id": kept["id"] if sharing else None}


def file_salt(path: Path | None = None) -> bytes | None:
    """This install's file salt: made with its id, never sent, gone when sharing is turned off."""
    value = (_read(path or settings_path()) or {}).get("salt")
    return bytes.fromhex(value) if _is_salt(value) else None


def file_code(salt: bytes, path: str) -> str:
    """A file's code: the first 16 hex characters of an HMAC-SHA256 of its absolute path under ``salt``."""
    return hmac.new(salt, os.path.abspath(path).encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()[:16]


def choose(share: bool, *, by: str, path: Path | None = None,
           forget: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Keep the person's choice: ``{saved, sharing}``, and for an off ``forgotten`` (nothing is
    owed a deletion any more). Turning sharing off deletes the install id and file salt here and
    queues the id (``forget``) for the receiver to delete what it holds under it. The off is kept
    first and the receiver asked after -- through ``forget`` now, when one is given (a person at a
    terminal waits for it), else by the next flush (``forget_pending``) -- so an interrupted or
    unanswered request leaves sharing off with the deletion still owed. ``saved`` is false when the
    settings could not be written: the choice is then not kept, and nothing else changed."""
    path = path or settings_path()
    # When, exactly: what another process noted before this is never sent (``Recorder.flush``).
    choice = {"choice": "on" if share else "off", "disclosure": DISCLOSURE, "by": by, "decidedAt": time.time()}

    def keep(section: dict[str, Any]) -> dict[str, Any]:
        previous = section["id"] if isinstance(section.get("id"), str) else None
        pending = _pending(section)
        if share:
            salt = section["salt"] if previous and _is_salt(section.get("salt")) else _new_salt()
            return {**choice, "id": previous or str(uuid.uuid4()), "salt": salt, **({"forget": pending} if pending else {})}
        if previous and previous not in pending:
            pending.append(previous)
        return {**choice, **({"forget": pending} if pending else {})}

    if _update(path, keep) is None:
        return {"saved": False, "sharing": None}
    if share:
        return {"saved": True, "sharing": True}
    if forget is not None:
        forget_pending(path=path, forget=forget)
    return {"saved": True, "sharing": False, "forgotten": not _pending(_read(path) or {})}


def forget_pending(*, path: Path | None = None, forget: Callable[[str], bool] | None = None) -> None:
    """Ask the receiver again to delete what it holds under ids turned off while it was not asked or not reached."""
    path = path or settings_path()
    pending = _pending(_read(path) or {})
    if not pending:
        return
    done = [value for value in pending if (forget or request_deletion)(value)]
    if done:  # only the list changes, under the lock: an answer given meanwhile stays as given
        _update(path, lambda section: _without(section, done))


def _post(url: str, payload: dict[str, Any] | None = None, *, method: str = "POST") -> str:
    """``ok`` (taken), ``refused`` (never to be taken: a 4xx other than 408 and 429) or ``failed``
    (offline, slow or broken: worth trying again)."""
    try:
        import urllib.error
        import urllib.request

        data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"Content-Type": "application/json", "User-Agent": "cadgen"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`endpoint`)
                return "ok" if 200 <= response.status < 300 else "failed"
        except urllib.error.HTTPError as refusal:
            LOG.debug("analytics %s %s answered %s", method, url, refusal.code)
            return "refused" if 400 <= refusal.code < 500 and refusal.code not in (408, 429) else "failed"
    except Exception:  # noqa: BLE001 - analytics never fail anything
        LOG.debug("analytics %s %s failed", method, url, exc_info=True)
        return "failed"


def request_deletion(install_id: str) -> bool:
    """Ask the receiver to delete what it holds under ``install_id``: whether that is settled (it
    did, or it refused an id it will never hold). Waits on the network."""
    # In the body, never the path: the receiver's host logs each request's path beside its IP address.
    return _post(f"{endpoint()}/forget", {"install": install_id}) in ("ok", "refused")


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
                 send: Callable[[dict[str, Any]], Any] | None = None, interval: float = FLUSH_SECONDS) -> None:
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
        self._since = time.time()  # when what is noted now began to be noted
        self._off = False  # a no this process could not keep: nothing more is sent from it
        self._timer: threading.Event | None = None
        self._describe()

    @_guarded(lambda: None)
    def _describe(self) -> None:
        from cadgen import __version__

        self._context.update(version=_token(__version__, 32) or "unknown", platform=_platform_name(),
                             arch=_token(_platform.machine().lower(), 16))

    @_guarded(lambda: dict(UNAVAILABLE))
    def status(self) -> dict[str, Any]:
        return dict(UNAVAILABLE) if self._off else status(path=self.path)

    @_guarded(lambda: {"saved": False, "sharing": None})
    def choose(self, share: bool, *, by: str) -> dict[str, Any]:
        """The person's click or the agent's off: kept now, and any deletion it owes asked for in the
        background. A no that could not be kept still holds for this process: it sends nothing more."""
        chosen = choose(share, by=by, path=self.path)  # forget=None: the id waits as pending
        with self._lock:  # nothing noted before a choice is sent after it
            self._counts.clear()
            self._views = 0
            self._files.clear()
            self._since = time.time()
        if not share:
            self._off = self._off or not chosen["saved"]
            self._background(lambda: forget_pending(path=self.path))
        elif chosen["saved"]:
            self._off = False
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
        path = os.path.abspath(path)  # one file, however a view spelled it: one code, once (the receiver refuses repeats)
        with self._lock:
            if path in self._files or len(self._files) < FILES_PENDING:
                self._files[path] = kind

    @_guarded(lambda: False)
    def flush(self) -> bool:
        """Send what was used since the last batch, if sharing is on; drop it if not. A deletion still owed
        is asked for first. A batch with no use in it is not sent. It waits on the network: only the
        background sender and ``close`` call it."""
        settings = self.path or settings_path()
        forget_pending(path=settings)
        found = self.status()
        kept = (_read(settings) or {}) if found["sharing"] else {}
        # The salt read with the id it belongs to; and when the person said yes.
        salt = bytes.fromhex(kept["salt"]) if kept.get("id") == found["id"] and _is_salt(kept.get("salt")) else None
        decided = kept.get("decidedAt")
        day = _day()
        with self._lock:
            counts, views, files, since = self._counts, self._views, self._files, self._since
            self._counts, self._views, self._files, self._since = {}, 0, {}, time.time()
            context = dict(self._context)
            if not found["sharing"] or salt is None:
                return False
            # Noted before a yes given in the other app (this one's own clears what it noted): never sent.
            if isinstance(decided, (int, float)) and decided > since:
                return False
            self._sent = {entry for entry in self._sent if entry.startswith(f"{day}:")}
            fresh = list({code: (path, kind, code) for path, kind in files.items()
                          for code in [file_code(salt, path)] if f"{day}:{code}" not in self._sent}.values())
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
        outcome = self._send({"schema": SCHEMA, "install": found["id"], "session": self._session, **context,
                              "events": events})
        outcome = "ok" if outcome is True else "failed" if outcome in (False, None) else outcome
        with self._lock:
            if outcome == "ok":
                self._sent.update(f"{day}:{code}" for _, _, code in sending)
            elif outcome == "failed":  # kept for the next batch, added to whatever came since
                for tool, (calls, errors) in counts.items():
                    noted = self._counts.setdefault(tool, [0, 0])
                    noted[0] += calls
                    noted[1] += errors
                self._views += views
                for file, kind, _ in sending:
                    self._files.setdefault(file, kind)
            # refused: dropped, or it would be refused again with everything after it
        if outcome == "ok":
            self._owe_deletion_if_gone(settings, found["id"])
        return outcome == "ok"

    def _owe_deletion_if_gone(self, path: Path, install_id: str) -> None:
        """A batch can land after the deletion an opt-out asked for (said here or in the other app
        while it was on its way): when ``install_id`` is no longer this install's, it is owed a
        deletion again, and the next flush asks for it."""
        kept = _read(path)
        if kept is None or kept.get("id") == install_id:
            return

        def owe(section: dict[str, Any]) -> dict[str, Any]:
            if section.get("id") == install_id or install_id in _pending(section):
                return section
            return {**section, "forget": [*_pending(section), install_id]}

        _update(path, owe)

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
