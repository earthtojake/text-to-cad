"""cadgen's telemetry: usage counts from the processes that do CAD's work -- ``cadgen mcp`` (the CAD
app in an agent app), ``cadgen viewer`` (the browser viewer) and the build daemon, which builds for
both and for every ``cadgen`` command and model script: how many people use CAD, how often, what they
make and how it goes -- counts, times and metadata, never what anything says. A ``cadgen`` command
sends nothing itself: it hands what it counted (a snapshot) to the daemon, and says, once, what is
sent (``notify``).

What is sent, at most every five minutes while there is something new and once more as a process
exits, each batch stamped with the time it arrives:

- who, by random ids only: an install id made on this machine, and an id for the sending process;
- what runs: which process (``app``, ``viewer`` or ``daemon``), cadgen's version, where it was
  installed from (its channel, ``cadgen/_internal/channel.py``: a plugin directory, the Cursor
  Marketplace, GitHub, a development install, or ``unknown``), the operating system and processor,
  and from the apps the agent app's name and version and how that app shows CAD (tabs, inline or
  text) -- or, from the browser viewer, ``cadgen-viewer`` and ``browser``;
- ``tool`` (the CAD app): how many times each CAD tool was called, and how many of those failed;
- ``view`` (the apps): how many times a CAD view was touched by a person or switched models --
  time spent looking at a model calls no tool, and is use all the same;
- ``files`` (the apps): how many distinct files of each format (``step``, ``stl``, ...) a CAD view
  showed for the first time that day -- told apart here, by path, and sent as a number;
- ``build`` (the daemon): for each format and who asked (``VIAS``), how many builds, how each
  ended (``OUTCOMES``: failed, lost its worker, or stopped when whoever asked left), how many the
  store answered without building, and how long they took;
- ``snapshot`` (the daemon, told by the command that rendered it): for each format, how many
  renders, how many failed, and how long they took;
- ``feature`` (the daemon): how many builds made an assembly or declared mesh exports, and how many
  snapshots posed joints or played an animation (``FEATURES``);
- ``health`` (the daemon): build workers started, crashed and recycled, and builds refused for
  want of memory.

Never a path, a file name, a model, an argument, a message, a prompt or anything typed. A batch with
nothing in it is never sent: a process the host started and nobody used counts for nothing. The
receiver (``cadgen/_internal/api.py``) is ours, so the service behind it can change without a
release.

It is sent by default once the person has been told, and never after their no. Strongest first:

1. The environment: ``DO_NOT_TRACK=1`` or ``CADGEN_TELEMETRY=0`` turns it off,
   ``CADGEN_TELEMETRY=1`` on.
2. The person's choice, kept as the ``telemetry`` section of their settings (``cadgen/settings.py``:
   ``settings.json`` in the state directory) and shared by every process: either app's menu,
   ``cadgen telemetry on|off``, or the agent's ``cad_telemetry`` (off only). A yes sends all of
   the above; a no, nothing.
3. Otherwise the default: all of the above, from the moment the person has been told -- one line,
   said once by the first ``cadgen`` command that may (``notify``). What a running process noted
   before that is never sent, and turning it off deletes what was. Nothing is sent by default in CI
   or from a development install (``_here``), where nobody is told, even where a person was told
   elsewhere: what runs there is a machine, or a developer at work.

A no is kept and never undone: not by a restart, an update, or more being sent. When more is
sent, a yes to less (``DISCLOSURE``) counts as no answer, and a default that grew (``NOTICE``)
is said again before it is sent. Nothing in a CAD app asks: the telling is the CLI's.

Before telemetry, cadgen 0.7.7 to 0.7.15 kept these answers as ``analytics`` (the settings section,
``cadgen analytics``, ``CADGEN_ANALYTICS``). Nothing of that carries over but a no: an ``analytics``
choice of off counts as off until the person answers here (``LEGACY``), and ``CADGEN_ANALYTICS=0``
turns telemetry off as ``CADGEN_TELEMETRY=0`` does.

Where CAD was installed from is only reported, as ``channel``: it decides nothing here but that a
development install sends nothing by default.

The install id exists only while sharing is on: turning it off deletes it here and asks the
receiver to delete what it holds under it -- again and again until it hears back -- and turning it
on again starts a new install, so nothing links the two.

Telemetry never gets in the way of CAD:

- Nothing here raises into the process that counts. Every ``Recorder`` method is guarded: a failure
  (an unreadable state directory, a broken receiver, a bug here) is logged at debug level, below
  what ``cadgen mcp`` prints, so nothing reaches a host's or an agent's logs, and answered with a
  safe default: not sharing, nothing sent, nothing said.
- No tool call, build or command waits on the network, and none needs it: offline, everything
  works and nothing is sent. Noting use is in memory; sending, and the deletion an opt-out asks
  for, run on a background thread. The one wait is the last send as a process exits, bounded by
  ``CLOSE_SECONDS``.
- A batch the receiver did not take (offline, a slow or broken receiver, or none answering
  there yet) is kept for the next one; it is never an error. One the receiver read and refused
  (``REFUSED``) is dropped: it would be refused again, and take everything after it down with it.

The answer is changed only under the settings lock (``settings.update_section``), so the processes
answering, opting out or making the install's id at once never undo one another. A settings file
that is there but cannot be read counts as no answer that can be kept ("unavailable"), never as no
answer yet, and is never written back over.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import math
import os
import platform as _platform
import re
import sys
import threading
import time
import uuid
from pathlib import Path

from typing import Any, Callable

from cadgen._internal.api import api_url
from cadgen._internal.atomic_replace import temp_suffix
from cadgen._internal.file_lock import exclusive
from cadgen.settings import LOCK, read_section, settings_path, update_section

LOG = logging.getLogger("cadgen.analytics")

PRIVACY_URL = "https://www.texttocad.dev/privacy-policy"
SCHEMA = 3  # 3: the build daemon's counts, and files as numbers; 2: the install's channel replaced `source`
# What a yes agreed to: the fields and events this module sends. Raise it when that grows, and a yes
# to less counts as no answer again; a no stays a no. Restarts and updates that send nothing new keep
# the answer: it lives in the person's state directory, not the install.
DISCLOSURE = 1
# What the notice told (``notify``): what is sent by default, without a yes. Raise it when that grows,
# and the next ``cadgen`` command says it again; nothing is sent by default until it has.
NOTICE = 1
NOTICE_TEXT = ("cadgen now sends usage stats, tagged with a random ID — never your files, paths or prompts. "
               f"Turn off: cadgen telemetry off · {PRIVACY_URL}")
# ``0``: what this command says reaches nobody -- a CAD app's own launch of one, its output thrown away.
NOTICE_ENV = "CADGEN_TELEMETRY_NOTICE"
# A batch is the counts of a window this long: a few events, however busy the window was.
FLUSH_SECONDS = 300
# How long a send waits for the receiver. Sends run in the background, so this delays nothing; a
# shorter wait would give up on a batch a cold receiver was still storing, and send it twice.
TIMEOUT_SECONDS = 10
CLOSE_SECONDS = 2  # the most an exiting process waits for its last send
# The page's plumbing: a view's once-a-second sync, its viewer requests (the home's re-reads of its
# library every couple of seconds among them) and its capture replies say nothing about use and would
# drown what does. A view's own activity is noted from its sync (``viewed``) and as it adds the model
# on screen to the library (``opened``).
UNCOUNTED = frozenset({"cad_sync", "cad_http", "cad_capture_reply"})
# A file's format, by extension: what the viewer opens (``cadgen.viewer.scanner.SOURCE_EXTENSIONS``).
FILE_KINDS = {".step": "step", ".stp": "step", ".stl": "stl", ".3mf": "3mf", ".glb": "glb", ".dxf": "dxf",
              ".urdf": "urdf", ".srdf": "srdf", ".sdf": "sdf"}
KINDS = frozenset(FILE_KINDS.values())  # a format, as every event names it
PROCESSES = frozenset({"app", "viewer", "daemon"})
# Who asked for a build: a model script (``python model.py``) or a ``cadgen`` command (``cadgen step build``, ...).
VIAS = frozenset({"script", "command"})
# How a build ended: built; failed (the model raised, or its command refused what it was given); crashed (its
# worker died under it); or cancelled (whoever asked left before it ended, and it was stopped).
OUTCOMES = frozenset({"ok", "failed", "crashed", "cancelled"})
# What a person used: a model with children, a model declaring mesh exports (``@stl``, ``@glb``, ``@threemf``),
# and a snapshot that posed joints or played an animation.
FEATURES = frozenset({"assembly", "declared_mesh", "kinematics", "animation"})
# The daemon's build workers: started (each imports the CAD kernel), crashed (died mid-job, or could not
# start), recycled (retired after their share of jobs), and builds refused for want of memory.
HEALTH = ("workers", "crashes", "recycles", "refusals")
# Each event: the names it is told apart by, and what it counts. A batch holds one event per event and
# names, its counts added up over the window -- ``longest`` is the longest.
EVENTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "tool": (("tool",), ("calls", "errors")),
    "view": ((), ("calls",)),
    "files": (("kind",), ("count",)),
    "build": (("kind", "via"), ("count", "failed", "crashed", "cancelled", "cached", "seconds", "longest")),
    "snapshot": (("kind",), ("count", "failed", "seconds")),
    "feature": (("feature",), ("count",)),
    "health": ((), HEALTH),
}
MAX_EVENTS = 64  # a batch's most (the receiver's too): any more wait for the next batch
# The receiver read the request and will never take it: malformed (400), too large (413), not JSON (415).
# Anything else -- a 404 where no receiver is deployed yet, a firewall's 403, a 429, a 5xx -- is tried
# again: dropping it would lose counts, and a deletion an opt-out owes, for good.
REFUSED = frozenset({400, 413, 415, 422})
FILES_PER_DAY = 1024  # past this many files in a day, a process tells no more apart
# What a status is when it cannot be read: not sharing, and nothing said either (a broken state
# directory must not say it on every command).
UNAVAILABLE = {"sharing": False, "reason": "unavailable", "id": None}

_OFF, _ON = ("0", "off", "false", "no"), ("1", "on", "true", "yes")


SECTION = "telemetry"  # this module's part of the settings file
# Where cadgen 0.7.7 to 0.7.15 kept the answer, and its environment variable: read for a no, and nothing else.
LEGACY = "analytics"


def _read(path: Path) -> dict[str, Any] | None:
    """The telemetry section, or ``None`` when the settings are there but cannot be read now. A no kept
    before telemetry (``LEGACY``) counts as this section's until the person answers here."""
    try:
        kept = read_section(SECTION, path=path)
        if "choice" not in kept and read_section(LEGACY, path=path).get("choice") == "off":
            kept = {**kept, "choice": "off"}
        return kept
    except OSError:
        LOG.debug("could not read the telemetry choice in %s", path, exc_info=True)
        return None


_UNKEPT: set[Path] = set()  # settings a write failed for in this process: it asks about them no more
_UNREAD = object()  # a process's first batch, before its first use: the answer it began under is not read yet


def _update(path: Path, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any] | None:
    """Change the telemetry section under the settings lock: what is kept, or ``None`` when it
    could not be read or written -- and then this process stops asking (``_can_keep``)."""
    try:
        return update_section(SECTION, change, path=path)
    except OSError:
        LOG.debug("could not keep the telemetry choice in %s", path, exc_info=True)
        _UNKEPT.add(path)
        return None


# What an environment says (``_environment``): forwarded with every build a client asks the daemon for
# (``cadgen.daemon.client.FORWARDED_ENV_VARS``), so a client's no holds for its builds there too.
ENVIRONMENT = ("DO_NOT_TRACK", "CADGEN_TELEMETRY", "CADGEN_ANALYTICS")


def _environment(env: Any = None) -> bool | None:
    env = os.environ if env is None else env
    if str(env.get("DO_NOT_TRACK") or "").strip().lower() in _ON:
        return False
    if str(env.get("CADGEN_ANALYTICS") or "").strip().lower() in _OFF:  # a no set before telemetry (LEGACY)
        return False
    value = str(env.get("CADGEN_TELEMETRY") or "").strip().lower()
    return False if value in _OFF else True if value in _ON else None


def refused(env: Any = None) -> bool:
    """Whether an environment (this process's, or the one a client sent the daemon with a build) turns
    telemetry off: what is counted for it is never noted, whatever the process that counts was told."""
    try:
        return _environment(env) is False
    except Exception:  # noqa: BLE001 - an environment that cannot be read is no yes
        LOG.debug("could not read a telemetry environment", exc_info=True)
        return True


def _disclosure(kept: dict[str, Any]) -> int:
    value = kept.get("disclosure")
    return value if isinstance(value, int) else 0


def _pending(kept: dict[str, Any]) -> list[str]:
    value = kept.get("forget")
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _identified(kept: dict[str, Any]) -> bool:
    return isinstance(kept.get("id"), str)


def _told(kept: dict[str, Any]) -> float | None:
    """When the person was told what is sent by default (``notify``): ``None`` for never, or for a
    telling of less than is sent by default now (``NOTICE``)."""
    when, notice = kept.get("notifiedAt"), kept.get("notice")
    if isinstance(when, (int, float)) and isinstance(notice, int) and notice >= NOTICE:
        return float(when)
    return None


def _in_ci() -> bool:
    """Whether this runs in CI (``CI`` set, as the update check reads it): nobody there is told anything."""
    return str(os.environ.get("CI") or "").strip().lower() not in ("", *_OFF)


def _here() -> bool:
    """Whether the default can hold in this process: never in CI or from a development install, where
    nobody is told (``notify``) -- a person told elsewhere is, here, a machine or a developer at work."""
    from cadgen._internal.channel import DEV, channel

    return not _in_ci() and channel() != DEV


def _decide(kept: dict[str, Any], forced: bool | None, here: bool = True) -> tuple[bool, str | None]:
    """Whether to share, and why (``None``: nothing decided and nobody told -- or not ``here`` -- so
    nothing is sent)."""
    if forced is not None:
        return forced, "environment"
    if kept.get("choice") == "off":
        return False, "choice"
    if kept.get("choice") == "on" and _disclosure(kept) >= DISCLOSURE:
        return True, "choice"
    if here and _told(kept) is not None:
        return True, "default"
    return False, None


def _answer(kept: dict[str, Any]) -> tuple[Any, Any]:
    """Which answer is in force: when the person chose, and when they were told. What a process noted
    under one answer is never sent under another (``Recorder.flush``): not before a yes given in
    another process, and not from before the person was told."""
    return kept.get("decidedAt"), kept.get("notifiedAt")


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


def status(*, path: Path | None = None, probe: bool = True) -> dict[str, Any]:
    """``{sharing, reason, id}``: whether counts are sent, why, and under which install id.

    ``reason`` is ``environment``, ``choice``, ``default`` (the person was told and chose nothing),
    ``untold`` (nothing is sent: nobody has been told yet, or not here -- ``_here``) or
    ``unavailable`` (nothing is sent, and nothing said: no answer could be kept). Sharing makes the
    install's id where it is missing. ``probe=False`` takes no answer that could be kept for
    ``unavailable`` without trying the state directory (``_can_keep``): a sender's question, which
    either way sends nothing.
    """
    path = path or settings_path()
    forced = _environment()
    kept = _read(path)
    if kept is None:  # there, but unreadable now: neither sent under nor said
        return {"sharing": False, "reason": "environment", "id": None} if forced is False else dict(UNAVAILABLE)
    here = _here()
    sharing, reason = _decide(kept, forced, here)
    if reason is None:  # a telling that could not be kept would be said again on every command
        return {"sharing": False, "reason": "untold" if not probe or _can_keep(path) else "unavailable", "id": None}
    if sharing and not _identified(kept):
        def identify(section: dict[str, Any]) -> dict[str, Any]:
            if not _decide(section, forced, here)[0] or _identified(section):  # changed meanwhile: as it is now
                return section
            return {**section, "id": str(uuid.uuid4())}

        kept = _update(path, identify)
        if kept is None:
            return dict(UNAVAILABLE)
        sharing, reason = _decide(kept, forced, here)
        if sharing and not _identified(kept):
            return dict(UNAVAILABLE)
    return {"sharing": sharing, "reason": reason, "id": kept["id"] if sharing else None}


def choose(share: bool, *, by: str, path: Path | None = None,
           forget: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Keep the person's choice: ``{saved, sharing}``, and for an off ``forgotten`` (nothing is
    owed a deletion any more). Turning sharing off deletes the install id here and queues it
    (``forget``) for the receiver to delete what it holds under it. The off is kept first and the
    receiver asked after -- through ``forget`` now, when one is given (a person at a terminal waits
    for it), else by the next flush (``forget_pending``) -- so an interrupted or unanswered request
    leaves sharing off with the deletion still owed. ``saved`` is false when the settings could not
    be written: the choice is then not kept, and nothing else changed."""
    path = path or settings_path()
    # When, and so which answer this is: what another process noted under an earlier one is never sent (``Recorder.flush``).
    choice = {"choice": "on" if share else "off", "disclosure": DISCLOSURE, "by": by, "decidedAt": time.time()}

    def keep(section: dict[str, Any]) -> dict[str, Any]:
        previous = section["id"] if isinstance(section.get("id"), str) else None
        pending = _pending(section)
        told = {key: section[key] for key in ("notifiedAt", "notice") if key in section}  # a fact, whatever the answer
        if share:
            return {**told, **choice, "id": previous or str(uuid.uuid4()), **({"forget": pending} if pending else {})}
        if previous and previous not in pending:
            pending.append(previous)
        return {**told, **choice, **({"forget": pending} if pending else {})}

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


def notify(stream: Any = None, *, path: Path | None = None) -> bool:
    """Tell the person, once, what is sent by default: ``NOTICE_TEXT``, a line on ``stream`` (stderr)
    from the first ``cadgen`` command that may say it, kept as said (``notifiedAt``): every process
    sends from then on, never what it noted before. Nothing is said where nothing would be sent by
    default: where the environment or the person decided, in CI or from a development install
    (``_here``), from a launch whose output reaches nobody (``NOTICE_ENV``), or where it could not be
    kept as said -- it would be said on every command. ``True`` when it was said. Never raises: the
    command it rides on comes first."""
    try:
        if _environment() is not None or os.environ.get(NOTICE_ENV) == "0" or not _here():
            return False
        path = path or settings_path()
        kept = _read(path)
        if kept is None or _decide(kept, None)[1] is not None or not _can_keep(path):
            return False
        out = stream if stream is not None else sys.stderr
        out.write(NOTICE_TEXT + "\n")
        out.flush()

        def tell(section: dict[str, Any]) -> dict[str, Any]:
            if _decide(section, None)[1] is not None:  # decided or told meanwhile: as it is now
                return section
            return {**section, "notifiedAt": time.time(), "notice": NOTICE}

        return _update(path, tell) is not None
    except Exception:  # noqa: BLE001 - the notice never fails the command it rides on
        LOG.debug("telemetry notice failed", exc_info=True)
        return False


def told_at(path: Path | None = None) -> float | None:
    """When the person was told what is sent by default (``notify``), or ``None``."""
    return _told(_read(path or settings_path()) or {})


def _post(url: str, payload: dict[str, Any] | None = None, *, method: str = "POST") -> str:
    """``ok`` (taken), ``refused`` (read and never to be taken: ``REFUSED``) or ``failed`` (offline,
    slow, broken or not there yet: worth trying again)."""
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
            LOG.debug("telemetry %s %s answered %s", method, url, refusal.code)
            return "refused" if refusal.code in REFUSED else "failed"
    except Exception:  # noqa: BLE001 - telemetry never fails anything
        LOG.debug("telemetry %s %s failed", method, url, exc_info=True)
        return "failed"


def request_deletion(install_id: str) -> bool:
    """Ask the receiver to delete what it holds under ``install_id``: whether that is settled (it
    did, or it refused an id it can never hold). Waits on the network."""
    # In the body, never the path: the receiver's host logs each request's path beside its IP address.
    return _post(f"{api_url()}/forget", {"install": install_id}) in ("ok", "refused")


def _token(value: Any, limit: int) -> str:
    """A short token the receiver takes (ASCII letters, digits and ``_.+:-``, as its own check reads
    them): a host's free-text name is kept recognisable, never refused."""
    return re.sub(r"[^A-Za-z0-9_.+:-]+", "-", str(value or "").strip())[:limit]


def _platform_name() -> str:
    return sys.platform if sys.platform in ("darwin", "win32") else "linux" if sys.platform.startswith("linux") else "other"


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _seconds(value: Any) -> float:
    """A duration as a batch counts it: seconds, never negative, nor anything but a number."""
    return max(0.0, float(value)) if isinstance(value, (int, float)) and math.isfinite(value) else 0.0


def _guarded(default: Callable[[], Any]):
    """Never raise into the process that counts: a failure is a debug line and ``default()``."""
    def decorate(method):
        @functools.wraps(method)
        def guarded(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except Exception:  # noqa: BLE001 - telemetry never fails what it counts
                LOG.debug("telemetry %s failed", method.__name__, exc_info=True)
                return default()
        return guarded
    return decorate


class _Tally:
    """What a process noted since its last batch: counts under ``EVENTS``' names, and nothing else."""

    def __init__(self, rows: dict[tuple[str, ...], list[float]] | None = None) -> None:
        self.rows = rows if rows is not None else {}  # (event, *names) -> its counts, in ``EVENTS`` order

    def note(self, event: str, names: tuple[str, ...], counts: dict[str, float]) -> None:
        self._add((event, *names), [counts.get(name, 0) for name in EVENTS[event][1]])

    def _add(self, key: tuple[str, ...], values: list[float]) -> None:
        counted = EVENTS[key[0]][1]
        row = self.rows.setdefault(key, [0] * len(counted))
        for index, (name, value) in enumerate(zip(counted, values)):
            row[index] = max(row[index], value) if name == "longest" else row[index] + value

    def merge(self, other: _Tally) -> None:
        """Add ``other``'s counts to these: a batch the receiver did not take, kept for the next."""
        for key, values in other.rows.items():
            self._add(key, values)

    def split(self, limit: int) -> tuple[_Tally, _Tally]:
        """The first ``limit`` events, and the rest: what a batch has room for, and the next batch's."""
        keys = sorted(self.rows)
        return (_Tally({key: self.rows[key] for key in keys[:limit]}),
                _Tally({key: self.rows[key] for key in keys[limit:]}))

    def events(self) -> list[dict[str, Any]]:
        events = []
        for key in sorted(self.rows):
            names, counted = EVENTS[key[0]]
            events.append({"name": key[0], **dict(zip(names, key[1:])),
                           **{name: round(value, 1) if name in ("seconds", "longest") else int(value)
                              for name, value in zip(counted, self.rows[key])}})
        return events


class Recorder:
    """Notes one process's use -- tool calls, view activity, files on screen, builds, snapshots,
    features and the daemon's health -- and sends it while sharing is on. Every method is guarded
    (see the module docstring): it never raises, and none but ``close`` waits on the network."""

    def __init__(self, *, process: str = "app", path: Path | None = None,
                 send: Callable[[dict[str, Any]], Any] | None = None, interval: float = FLUSH_SECONDS,
                 collect: Callable[[Recorder], Any] | None = None) -> None:
        self.path = path
        # Called as each batch is made, to note what is counted elsewhere (the daemon's pool, ``cadgen.daemon.telemetry``).
        self._collect = collect
        self._send = send or (lambda payload: _post(f"{api_url()}/events", payload))
        self._interval = interval
        self._lock = threading.Lock()
        self._session = str(uuid.uuid4())
        self._context: dict[str, Any] = {"process": process if process in PROCESSES else "app", "version": "unknown",
                                         "channel": "unknown", "platform": "other"}
        self._tally = _Tally()
        self._day = ""
        self._shown: set[str] = set()  # the files a view showed today, by absolute path: never leaves this process
        self._basis: Any = _UNREAD  # the answer in force when what is noted now began to be noted
        self._off = False  # a no this process could not keep: nothing more is sent from it
        self._timer: threading.Event | None = None
        self._describe()

    @_guarded(lambda: None)
    def _describe(self) -> None:
        from cadgen import __version__
        from cadgen._internal.channel import channel

        self._context.update(version=_token(__version__, 32) or "unknown", channel=channel(),
                             platform=_platform_name(), arch=_token(_platform.machine().lower(), 16))

    @_guarded(lambda: None)
    def _decision(self) -> Any:
        """When the answer in force now was given, and when the person was told what is sent by default:
        which answer it is (``(None, None)``: none, or none readable)."""
        return _answer(_read(self.path or settings_path()) or {})

    def _first_use(self) -> Any:
        """The answer the first batch began under, read as its first use is noted -- not at start, where
        ``cadgen mcp`` reads nothing of the person's until a tool needs it -- and ``_UNREAD`` once known.
        Every later batch begins under the answer the flush before it read."""
        return self._decision() if self._basis is _UNREAD else _UNREAD

    def _begin(self, answer: Any) -> None:
        """Under the lock, before noting a use: the first batch's answer, unless a flush or choice set one."""
        if self._basis is _UNREAD:
            self._basis = answer

    def _note(self, event: str, names: tuple[str, ...], counts: dict[str, float]) -> None:
        """Count a use, in memory only: a flush without consent drops it. Only a process's first use reads
        anything before a flush: the answer it began under (``_first_use``)."""
        answer = self._first_use()
        with self._lock:
            self._begin(answer)
            self._tally.note(event, names, counts)

    @_guarded(lambda: dict(UNAVAILABLE))
    def status(self) -> dict[str, Any]:
        return dict(UNAVAILABLE) if self._off else status(path=self.path)

    @_guarded(lambda: {"saved": False, "sharing": None})
    def choose(self, share: bool, *, by: str) -> dict[str, Any]:
        """The person's click or the agent's off: kept now, and any deletion it owes asked for in the
        background. A no that could not be kept still holds for this process: it sends nothing more."""
        chosen = choose(share, by=by, path=self.path)  # forget=None: the id waits as pending
        decision = self._decision()
        with self._lock:  # nothing noted before a choice is sent after it
            self._tally = _Tally()
            self._basis = decision
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
        """The CAD app ran one of its tools: ``ok`` false when it failed."""
        if isinstance(tool, str) and tool not in UNCOUNTED:
            self._note("tool", (tool,), {"calls": 1, "errors": 0 if ok else 1})

    @_guarded(lambda: None)
    def viewed(self) -> None:
        """A person touched a CAD view, or it switched models."""
        self._note("view", (), {"calls": 1})

    @_guarded(lambda: None)
    def opened(self, path: Any) -> None:
        """A CAD view has this file on screen: counted by its format the first time today, told apart by
        its path here and never sent."""
        if not isinstance(path, str) or not path:
            return
        kind = FILE_KINDS.get(os.path.splitext(path)[1].lower())
        if kind is None:
            return
        path, day = os.path.abspath(path), _day()  # one file, however a view spelled it
        answer = self._first_use()
        with self._lock:
            self._begin(answer)
            if day != self._day:
                self._day, self._shown = day, set()
            if path in self._shown or len(self._shown) >= FILES_PER_DAY:
                return
            self._shown.add(path)
            self._tally.note("files", (kind,), {"count": 1})

    @_guarded(lambda: None)
    def built(self, kind: str, via: str, outcome: str, seconds: float = 0.0, *, cached: bool = False) -> None:
        """The daemon answered a build of a ``kind`` of model asked for ``via`` one of ``VIAS``, ended as one
        of ``OUTCOMES`` after ``seconds``; ``cached``: the store had it, and nothing was built."""
        if kind not in KINDS or via not in VIAS or outcome not in OUTCOMES:
            return
        took = _seconds(seconds)
        self._note("build", (kind, via), {"count": 1, "failed": outcome == "failed", "crashed": outcome == "crashed",
                                          "cancelled": outcome == "cancelled", "cached": bool(cached) and outcome == "ok",
                                          "seconds": took, "longest": took})

    @_guarded(lambda: None)
    def rendered(self, kind: str, ok: bool, seconds: float = 0.0) -> None:
        """A snapshot of a ``kind`` of file was rendered, or failed to be."""
        if kind in KINDS:
            self._note("snapshot", (kind,), {"count": 1, "failed": not ok, "seconds": _seconds(seconds)})

    @_guarded(lambda: None)
    def used(self, feature: str) -> None:
        """One of ``FEATURES`` was used."""
        if feature in FEATURES:
            self._note("feature", (feature,), {"count": 1})

    @_guarded(lambda: None)
    def health(self, name: str, count: int = 1) -> None:
        """The daemon's build workers: one of ``HEALTH`` happened ``count`` times."""
        if name in HEALTH and isinstance(count, int) and count > 0:
            self._note("health", (), {name: count})

    @_guarded(lambda: False)
    def flush(self) -> bool:
        """Send what was used since the last batch, if sharing is on; drop it if not. A deletion still owed
        is asked for first. A batch with no use in it is not sent. It waits on the network: only the
        background sender and ``close`` call it."""
        if self._collect is not None:
            self._collect(self)
        settings = self.path or settings_path()
        forget_pending(path=settings)
        with self._lock:
            if not self._tally.rows:  # nothing to send, nor an answer to read: the next use reads its own
                self._basis = _UNREAD
                return False
        found = dict(UNAVAILABLE) if self._off else status(path=self.path, probe=False)
        decided = _answer((_read(settings) or {}) if found["sharing"] else {})  # which answer is in force (``_answer``)
        with self._lock:
            tally, basis = self._tally, self._basis
            self._tally, self._basis = _Tally(), decided
            context = dict(self._context)
            # Noted under an earlier answer -- before a yes given in another process (this one's own clears
            # what it noted), before the person was told, or under one never read: never sent. Which answer,
            # not whether it came later: Windows' clock moves in 16 ms steps, so a yes and the batch it lands
            # in can share a time.
            if not found["sharing"] or decided != basis:
                return False
            sending, later = tally.split(MAX_EVENTS)
            self._tally.merge(later)  # past the batch's room: the next batch's
        events = sending.events()
        if not events:
            return False
        outcome = self._send({"schema": SCHEMA, "install": found["id"], "session": self._session, **context,
                              "events": events})
        outcome = "ok" if outcome is True else "failed" if outcome in (False, None) else outcome
        if outcome == "failed":  # kept for the next batch, added to whatever came since
            with self._lock:
                self._tally.merge(sending)
        # refused: dropped, or it would be refused again with everything after it
        if outcome == "ok":
            self._owe_deletion_if_gone(settings, found["id"])
        return outcome == "ok"

    def _owe_deletion_if_gone(self, path: Path, install_id: str) -> None:
        """A batch can land after the deletion an opt-out asked for (said here or in another process
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
        """Send every ``interval`` seconds (``FLUSH_SECONDS``), in the background, until ``close``."""
        stop = self._timer = threading.Event()

        def loop() -> None:
            while not stop.wait(self._interval):
                self.flush()

        threading.Thread(target=loop, name="cadgen-telemetry", daemon=True).start()

    @_guarded(lambda: None)
    def close(self) -> None:
        """The last send, as the process exits: waited for at most ``CLOSE_SECONDS``, then left behind."""
        if self._timer is not None:
            self._timer.set()
        self._background(self.flush).join(CLOSE_SECONDS)

    def _background(self, work: Callable[[], Any]) -> threading.Thread:
        def run() -> None:
            try:
                work()
            except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
                LOG.debug("telemetry background work failed", exc_info=True)

        thread = threading.Thread(target=run, name="cadgen-telemetry-once", daemon=True)
        thread.start()
        return thread
