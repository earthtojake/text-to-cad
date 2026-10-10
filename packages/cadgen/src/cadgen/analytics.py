"""cadgen's telemetry: usage counts and crash reports from the processes that do CAD's work --
``cadgen mcp`` (the CAD app in an agent app), ``cadgen viewer`` (the browser viewer) and the build
daemon, which builds for both and for every ``cadgen`` command and model script: how many people use
CAD, how often, what they make, how it goes and where cadgen's own code fails -- counts, times,
metadata and crash signatures, never what anything says. A ``cadgen`` command sends nothing itself:
it hands what it counted (a snapshot, a drawing, a crash) to a running daemon, and says, once, what
is sent (``notify``).

What is sent, at most every five minutes while there is something new and once more as a process
exits, each batch under an id of its own and stamped with the time it was made:

- who, by random ids only: an install id made on this machine, an id for the sending process, and one
  for the batch, so a batch sent again is never counted twice;
- what runs: which process (``app``, ``viewer`` or ``daemon``), cadgen's version, where it was
  installed from (its channel, ``cadgen/_internal/channel.py``: a plugin directory, the Cursor
  Marketplace, GitHub, a development install, or ``unknown``), the operating system and processor,
  and from the apps the agent app's name and version and how that app shows CAD (tabs, inline or
  text) -- or, from the browser viewer, ``cadgen-viewer`` and ``browser``;
- ``tool`` (the CAD app): how many times each CAD tool was called, and how many of those failed;
- ``tool_failure`` (the CAD app): how many of a tool's calls failed for each reason (``FAILURES``): one
  word cadgen chose where the call failed -- the caller named no file, or no view; a view that did not
  answer; the CAD Viewer that did not start; cadgen's own bug -- never the failure's message;
- ``view`` (the apps): how many times a CAD view was touched by a person or switched models --
  time spent looking at a model calls no tool, and is use all the same;
- ``files`` (the apps): how many distinct files of each format (``step``, ``stl``, ...) a CAD view
  showed for the first time that day -- told apart here, by path, and sent as a number;
- ``build`` (the daemon): for each format and who asked (``VIAS``), how many builds, how each
  ended (``OUTCOMES``: failed, lost its worker, or stopped: whoever asked left, or someone stopped its
  worker), how many the store answered without building, and how long they took;
- ``build_failure`` (the daemon): how many of those builds failed for each reason (``BUILD_FAILURES``),
  one word decided where the build failed (``build_failure``), from what the error is and whose code
  raised it -- the model's, the CAD kernel's under it, cadgen's -- never from its message;
- ``snapshot`` (the daemon, told by the command that rendered it): for each format, how many
  renders, how many failed, and how long they took;
- ``snapshot_failure``: how many of those failed for each reason (``SNAPSHOT_FAILURES``), decided as
  the snapshot failed (``snapshot_failure``);
- ``feature``: how many builds made an assembly or declared mesh exports, snapshots posed joints or
  played an animation, engineering drawings were made, and CAD views' Quick Edits were sent
  (``FEATURES``);
- ``health`` (the daemon): build workers started, crashed and recycled, and builds refused for
  want of memory;
- ``exception``: a crash in cadgen's own code (``signature``), and how many times it happened that
  window -- where (``WHERE``), the error's type, whether the process went on, and its innermost frames
  in code that may be named: each a file inside cadgen, the standard library or one of cadgen's
  dependencies (a page's: its script asset), a function and a line, the person's own code a bare
  ``<user>``; a build worker that died, its exit status. Never the error's message. Each process
  reports its own (``report``, ``collect_crashes``); a build worker's go to the daemon with its exit
  frame, a command's are handed to a running daemon, and a page's to the server that served it.

A command sends nothing itself. What it counts -- a build it made with no daemon to ask, a snapshot, a
drawing, a crash -- is handed to a running daemon (``cadgen.daemon.client.hand_over``), or, with none to
take it (``CADGEN_DAEMON=0``, a platform without one, none running), kept beside the settings for the next
process that sends (``spool``): only while sharing is on, under the answer in force, capped, and deleted by
a no.

Never a path or a file name of the person's, a model, an argument, a message, a prompt or anything
typed. A batch with nothing in it is never sent: a process the host started and nobody used counts
for nothing. The receiver (``cadgen/_internal/api.py``) is ours, so the service behind it can change
without a release.

It is sent by default once the person has been told, and never after their no. Strongest first:

1. The environment: ``DO_NOT_TRACK=1`` or ``CADGEN_TELEMETRY=0`` turns it off,
   ``CADGEN_TELEMETRY=1`` on, over the person's choice -- for the process it is set in, and the builds that process asks of the
   daemon, but never written to the settings, and not inherited by the processes it starts for others
   (``for_others``): the build daemon and a detached viewer go by the settings.
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
``cadgen analytics``), for a few days. No answer kept there carries over (``LEGACY``). One may
still be installed beside this one (a plugin not yet updated, while ``uvx cadgen`` runs the newest),
reading only ``analytics``: a no here is said there too, and the id it sent under is deleted with
this one's (``_stop_earlier``).

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
  for, run on a background thread. Nothing waits on it, an exit included: what a process noted since
  its last batch is kept beside the settings as it exits (``close``), and the next process that
  sends sends it, in the background, soon after it starts.
- A batch the receiver did not take (offline, a slow or broken receiver, or none answering
  there yet) is kept whole, its id and all, and sent again before anything newer, which waits for a
  later batch; it is never an error. The receiver may have taken it and its answer been lost: the id
  makes a second copy the first one, never more counts. One the receiver read and refused
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
import linecache
import logging
import math
import os
import platform as _platform
import re
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from typing import Any, Callable, Mapping

from cadgen._internal.api import api_url
from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen._internal.file_lock import exclusive
from cadgen.settings import LOCK, read_section, settings_path, update_section
from cadgen.viewer.content_types import COMPOUND_EXTENSIONS, extension_of

LOG = logging.getLogger("cadgen.analytics")

PRIVACY_URL = "https://www.texttocad.dev/privacy-policy"
# 5: why builds and snapshots failed, and each batch's id and time; 4: why tool calls failed; 3: the build
# daemon's counts, and files as numbers; 2: the install's channel replaced `source`
SCHEMA = 5
# What a yes agreed to: the fields and events this module sends. Raise it when that grows, and a yes
# to less counts as no answer again; a no stays a no. Restarts and updates that send nothing new keep
# the answer: it lives in the person's state directory, not the install. Neither schema 4 nor 5 raised it
# (nor ``NOTICE``): each says more of what was told already -- why a counted call, build or snapshot failed,
# in a word of ours -- and a batch's random id and time link nothing its process's id did not.
DISCLOSURE = 1
# What the notice told (``notify``): what is sent by default, without a yes. Raise it when that grows,
# and the next ``cadgen`` command says it again; nothing is sent by default until it has.
NOTICE = 1
NOTICE_TEXT = ("cadgen now sends usage stats and crash reports, tagged with a random ID — never your files, paths or "
               f"prompts. Turn off: uvx cadgen telemetry off · {PRIVACY_URL}")
# ``0``: what this command says reaches nobody -- a CAD app's own launch of one, its output thrown away.
NOTICE_ENV = "CADGEN_TELEMETRY_NOTICE"
# A batch is the counts of a window this long: a few events, however busy the window was.
FLUSH_SECONDS = 300
# How long a send waits for the receiver. Sends run in the background, so this delays nothing; a
# shorter wait would give up on a batch a cold receiver was still storing, and send it twice.
TIMEOUT_SECONDS = 10
# How soon after it starts a process sends the batches others kept as they exited (``Recorder.close``):
# a moment, so a start is never slowed and a short session's batch does not wait a whole window.
KEPT_SECONDS = 10
# Where a command keeps what it counted when no daemon can take it (``spool``), beside the settings, and
# the most it keeps there: past it, a command's counts are dropped until a sender takes the rest.
SPOOL = "telemetry-spool.jsonl"
SPOOL_BYTES = 256 * 1024
# Where an exiting process keeps its last batch (``Recorder.close``), whole, for the next process that
# sends; a file of its own, which a cadgen from before it never reads, capped as the spool is.
KEPT = "telemetry-batches.jsonl"
HANDED = 16  # the most of each kind one command's counts carry (``Recorder.take``)
# The page's plumbing: a view's once-a-second sync, its viewer requests (the home's re-reads of its
# library every couple of seconds among them) and its capture replies say nothing about use and would
# drown what does. A view's own activity is noted from its sync (``viewed``) and as it adds the model
# on screen to the library (``opened``).
UNCOUNTED = frozenset({"cad_sync", "cad_http", "cad_capture_reply"})
# A file's format, by extension: what the viewer opens (``cadgen.viewer.scanner.SOURCE_EXTENSIONS``).
FILE_KINDS = {".step": "step", ".stp": "step", ".stl": "stl", ".3mf": "3mf", ".glb": "glb", ".dxf": "dxf",
              ".urdf": "urdf", ".srdf": "srdf", ".sdf": "sdf", ".kicad_pcb": "kicad_pcb", ".kicad_sch": "kicad_sch",
              **COMPOUND_EXTENSIONS}
KINDS = frozenset(FILE_KINDS.values())  # a format, as every event names it
PROCESSES = frozenset({"app", "viewer", "daemon"})
# Who asked for a build: a model script (``python model.py``) or a ``cadgen`` command (``cadgen step build``, ...).
VIAS = frozenset({"script", "command"})
# How a build ended: built; failed (the model raised, or its command refused what it was given); crashed (its
# worker died under it); or cancelled (whoever asked left before it ended, and it was stopped, or someone
# stopped its worker: ``cadgen.daemon.pool.stopped``).
OUTCOMES = frozenset({"ok", "failed", "crashed", "cancelled"})
# Why a CAD tool's call failed, named where it failed (``cadgen.mcp.server.ToolFailed``), never read from its
# message. The caller's: it named no file (``no_path``), one by a relative path (``relative_path``), a path with
# no file (``no_file``) or a file CAD does not open (``not_cad``); no view, or one that is gone or shows no model
# (``no_view``); a view that shows its host's file alone (``wrong_view``); arguments the tool could not read
# (``bad_request``). The view's: it did not answer in time (``timeout``), answered with an error or without
# an image (``view_error``), or with one too large for the host (``too_large``). The machine's: the CAD Viewer
# did not start (``no_viewer``). cadgen's: anything else it raised (``bug``, reported as an ``exception`` too).
# ``other``: a failure that named none of these.
FAILURES = frozenset({"no_path", "relative_path", "no_file", "not_cad", "no_view", "wrong_view", "bad_request",
                      "timeout", "view_error", "too_large", "no_viewer", "bug", "other"})
# Why a build failed (``build_failure``), decided where it failed, never read from its message. The model's: its
# own code raised (``model_error``), or the CAD kernel or library it called refused what it asked (``kernel_error``:
# a fillet or a boolean that failed); cadgen refused what the model declared or returned, or what a command was
# given (``refused``: raised on purpose in cadgen's code); the script did not compile (``script_error``); its
# arguments were refused (``arguments``); a model it composes failed (``child_failed``). The machine's: a module
# that is not installed (``missing_module``), a file that is not there (``missing_file``), another file error -- a
# file locked or unwritable, a full disk (``io_error``) -- or out of time (``timeout``) or memory (``memory``).
# cadgen's: the kernel failed under cadgen's own code, writing or meshing what the model made (``export_error``),
# or a mistake in cadgen's code (``bug``, reported as an ``exception`` too). ``other``: none of these.
BUILD_FAILURES = frozenset({"model_error", "kernel_error", "refused", "script_error", "arguments", "child_failed",
                            "missing_module", "missing_file", "io_error", "timeout", "memory", "export_error", "bug",
                            "other"})
# Why a snapshot failed (``snapshot_failure``), decided as it failed: its request was refused (``bad_request``), a
# file it names is not there (``no_file``), its input could not be read or built (``input_error``), the headless
# browser did not start (``browser``), out of time (``timeout``) or memory (``memory``), the page did not render it
# (``render_error``), a mistake in cadgen's code (``bug``), or none of these (``other``).
SNAPSHOT_FAILURES = frozenset({"bad_request", "no_file", "input_error", "browser", "timeout", "memory", "render_error",
                               "bug", "other"})
# What a person used: a model with children, a model declaring mesh exports (``@stl``, ``@glb``, ``@threemf``),
# a snapshot that posed joints or played an animation, an engineering drawing (``@eng_drawing``), and a CAD
# view's Quick Edit sending its prompt.
FEATURES = frozenset({"assembly", "declared_mesh", "kinematics", "animation", "drawing", "quick_edit"})
# The daemon's build workers: started (each imports the CAD kernel), crashed (died mid-job, or could not
# start), recycled (retired after their share of jobs), and builds refused for want of memory.
HEALTH = ("workers", "crashes", "recycles", "refusals")
# Each event: the names it is told apart by, and what it counts. A batch holds one event per event and
# names, its counts added up over the window -- ``longest`` is the longest.
EVENTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "tool": (("tool",), ("calls", "errors")),
    "tool_failure": (("tool", "reason"), ("count",)),
    "view": ((), ("calls",)),
    "files": (("kind",), ("count",)),
    "build": (("kind", "via"), ("count", "failed", "crashed", "cancelled", "cached", "seconds", "longest")),
    "build_failure": (("kind", "via", "reason"), ("count",)),
    "snapshot": (("kind",), ("count", "failed", "seconds")),
    "snapshot_failure": (("kind", "reason"), ("count",)),
    "feature": (("feature",), ("count",)),
    "health": ((), HEALTH),
}
MAX_EVENTS = 64  # a batch's most (the receiver's too): any more wait for the next batch
# A crash (``signature``): where it happened -- a CAD tool's call, a viewer's route, another request a
# server answered (the daemon's, the CAD app's), a build a worker ran, a ``cadgen`` command, or a page --
# its type, and its frames.
WHERE = frozenset({"tool", "route", "request", "build", "command", "page"})
MAX_FRAMES = 30  # a crash's innermost frames: where it failed, and how it got there
CRASHES_PER_BATCH = 4  # a batch's most crashes, the rest the next batch's
CRASHES_PENDING = 16  # past this many different crashes waiting, a process counts only those it has
# Python's own words for a mistake in code, as against the errors cadgen raises on purpose for what it was
# given (a model that failed, a file that is not there, an argument it cannot take). Where cadgen reports a
# failure to the person anyway -- a build's, a command's -- only these are crashes, and only where Python
# raised them in cadgen's own code: never at a ``raise`` (``_RAISED``), where cadgen says the person's
# mistake in these words too ("@step returned a dict" is a TypeError). So cadgen code that takes what the
# person gave it -- a value, a name to forward (``cadgen.build123d``) -- checks it and says so at a raise:
# Python's error from using it unchecked would read as cadgen's own mistake.
BUGS = (AttributeError, LookupError, TypeError, NameError, AssertionError, ZeroDivisionError, RecursionError,
        NotImplementedError)
_RAISED = re.compile(r"(?:^|:)\s*raise\b")
# Errors that are never cadgen's bug: a command's own output closed by whatever read it (``cadgen ... | head``,
# which the command answers by stopping quietly) -- that pipe, not another the command wrote to (``stdout_closed``);
# a page leaving a viewer route mid-reply is the response writer's to swallow (``cadgen.viewer.response``), so a
# route's connection error that reaches here is cadgen's own connection failing, and is reported. And a
# ``RecursionError`` whose cycle is the person's: their code among its innermost frames, and of cadgen's only the
# decorator wrapper that calls it (``_THEIR_CYCLE``). The rule for the next noisy class: an error goes here only when,
# there, it can never be a mistake in cadgen's code -- never because it is frequent -- and in the same change the
# receiver drops it from the releases already out (``NEVER_OURS`` in the API's ``noise.mjs``), so it stops costing
# anything at once.
_THEIR_CYCLE = frozenset({"cadgen/authoring.py"})


def stdout_closed() -> bool:
    """Whether this process's own output is the pipe that closed: flushing it fails the same way, or -- a write too
    large for the buffer leaves nothing to flush -- its descriptor reports no reader (POLLERR on Linux, POLLHUP on
    macOS). Windows has no ``poll``, and says a closed pipe is EINVAL, not EPIPE: never there."""
    stream = sys.stdout
    if stream is None:
        return False
    try:
        stream.flush()
    except BrokenPipeError:
        return True
    except (OSError, ValueError):
        return False
    try:
        import select

        poller = select.poll()
        poller.register(stream.fileno(), select.POLLOUT)
        return any(events & (select.POLLERR | select.POLLHUP) for _, events in poller.poll(0))
    except (AttributeError, OSError, ValueError):  # no poll, or not a real file
        return False


USER = "<user>"  # the person's own code, a frame or an exception's type: never named
_CHUNK_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")  # a page chunk's debug id
_FILE = re.compile(r"(?!\.\.?(?:/|$))[A-Za-z0-9_.+-]{1,64}(?:/(?!\.\.?(?:/|$))[A-Za-z0-9_.+-]{1,64}){0,8}")
_FUNCTION = re.compile(r"[A-Za-z_$<][A-Za-z0-9_$.<>]{0,79}")
_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}")
_TOOL = re.compile(r"cad_[a-z_]{1,40}")
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
# Where cadgen 0.7.7 to 0.7.15 kept the answer: never read as one here, only told a no (``_stop_earlier``).
LEGACY = "analytics"


def _read(path: Path) -> dict[str, Any] | None:
    """The telemetry section, or ``None`` when the settings are there but cannot be read now."""
    try:
        return read_section(SECTION, path=path)
    except OSError:
        LOG.debug("could not read the telemetry choice in %s", path, exc_info=True)
        return None


def _earlier_id(path: Path) -> str | None:
    """The id an earlier cadgen keeps (``LEGACY``), if it was told yes there."""
    try:
        value = read_section(LEGACY, path=path).get("id")
    except OSError:
        return None
    return value if isinstance(value, str) else None


def _stop_earlier(path: Path, by: str) -> None:
    """Say a no where cadgen 0.7.7 to 0.7.15 reads one (``LEGACY``), as its own off would: a plugin
    not yet updated runs one beside this cadgen, and an earlier yes there would go on sending. Its id
    is already owed a deletion with this one's (``choose``). Nothing is written where no earlier
    cadgen answered."""

    def off(section: dict[str, Any]) -> dict[str, Any]:
        if not section or (section.get("choice") == "off" and "id" not in section and "salt" not in section):
            return section
        kept = {key: value for key, value in section.items() if key not in ("id", "salt")}
        return {**kept, "choice": "off", "by": by, "decidedAt": time.time()}

    try:
        if read_section(LEGACY, path=path):
            update_section(LEGACY, off, path=path)
    except OSError:
        LOG.debug("could not keep the no where an earlier cadgen reads it in %s", path, exc_info=True)


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
ENVIRONMENT = ("DO_NOT_TRACK", "CADGEN_TELEMETRY")


def _environment(env: Any = None) -> bool | None:
    env = os.environ if env is None else env
    if str(env.get("DO_NOT_TRACK") or "").strip().lower() in _ON:
        return False
    value = str(env.get("CADGEN_TELEMETRY") or "").strip().lower()
    return False if value in _OFF else True if value in _ON else None


def for_others(env: Mapping[str, str]) -> dict[str, str]:
    """``env`` without its telemetry switches (``ENVIRONMENT``), for a process started here that outlives
    this one or serves others -- the build daemon, a detached viewer: it goes by the person's settings, not
    by the environment of whichever process happened to start it."""
    return {name: value for name, value in env.items() if name not in ENVIRONMENT}


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
    earlier = None if share else _earlier_id(path)  # what an earlier cadgen sent is deleted with the rest

    def keep(section: dict[str, Any]) -> dict[str, Any]:
        previous = section["id"] if isinstance(section.get("id"), str) else None
        pending = _pending(section)
        told = {key: section[key] for key in ("notifiedAt", "notice") if key in section}  # a fact, whatever the answer
        if share:
            return {**told, **choice, "id": previous or str(uuid.uuid4()), **({"forget": pending} if pending else {})}
        for gone in (previous, earlier):
            if gone and gone not in pending:
                pending.append(gone)
        return {**told, **choice, **({"forget": pending} if pending else {})}

    if _update(path, keep) is None:
        return {"saved": False, "sharing": None}
    if share:
        return {"saved": True, "sharing": True}
    _stop_earlier(path, by)
    _drop_spool(path)
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


def _distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@functools.cache
def _places() -> tuple[tuple[tuple[str, str], ...], frozenset[str]]:
    """Where code a crash may name lives, the longest first: cadgen's own package, the folders installed
    packages live in, and the standard library's; and the import names of cadgen's dependencies, all the
    way down -- the only installed packages named, so a package of the person's own is never."""
    import site
    import sysconfig
    from importlib import metadata

    import cadgen

    places = [(os.path.realpath(os.path.dirname(cadgen.__file__)), "cadgen")]
    paths = sysconfig.get_paths()
    sites = [*site.getsitepackages(), paths["purelib"], paths["platlib"],
             *(entry for entry in sys.path if entry.endswith(("site-packages", "dist-packages")))]
    places += [(os.path.realpath(entry), "site") for entry in sites if entry]
    places += [(os.path.realpath(paths[key]), "stdlib") for key in ("stdlib", "platstdlib")]
    seen, todo = set(), ["cadgen"]
    while todo:
        name = _distribution(todo.pop())
        if name in seen:
            continue
        seen.add(name)
        try:
            requirements = metadata.requires(name) or ()
        except metadata.PackageNotFoundError:
            continue
        # What it needs to run, not an extra nobody asked for (a test runner, say).
        todo += [re.split(r"[\s;<>=!~\[(]", requirement, maxsplit=1)[0] for requirement in requirements
                 if "extra" not in requirement.partition(";")[2]]
    ours = frozenset(top for top, owners in metadata.packages_distributions().items()
                     if top != "__pycache__" and any(_distribution(owner) in seen for owner in owners))
    return tuple(sorted(set(places), key=lambda place: len(place[0]), reverse=True)), ours


def _located(path: str) -> tuple[str, str] | None:
    """Where a frame's file lives -- ``cadgen``, ``site`` (one of cadgen's dependencies) or ``stdlib`` -- and
    its path inside that, as a crash names it; or ``None``, for the person's own code, or anything else."""
    if path.startswith("<frozen "):
        return "stdlib", "<frozen>"
    resolved = os.path.realpath(path)
    places, ours = _places()
    for root, kind in places:
        if not resolved.startswith(root + os.sep):
            continue
        inside = resolved[len(root) + 1:].replace(os.sep, "/")
        if kind == "cadgen":
            inside = f"cadgen/{inside}"
        elif kind == "site" and inside.split("/", 1)[0].split(".", 1)[0] not in ours:
            return None
        elif kind == "stdlib" and ("site-packages/" in inside or "dist-packages/" in inside):
            return None  # a folder of installed packages the longest-first order did not name
        return kind, inside if _FILE.fullmatch(inside) else "<?>"
    return None


def _file_of(path: str) -> str | None:
    """A frame's file as a crash names it: its path inside cadgen, the standard library or one of
    cadgen's dependencies -- or ``None``, for the person's own code, or anything else."""
    found = _located(path)
    return found[1] if found else None


def _type_of(error: BaseException) -> str:
    kind = type(error)
    module = kind.__module__
    if module == "builtins":
        return kind.__qualname__ if _TYPE.fullmatch(kind.__qualname__) else "<?>"
    source = getattr(sys.modules.get(module), "__file__", None)
    if module not in sys.builtin_module_names and (not source or _file_of(source) is None):
        return USER  # an error the person's own code defined
    name = f"{module}.{kind.__qualname__}"
    return name if _TYPE.fullmatch(name) else "<?>"


def signature(error: BaseException, where: str, *, tool: str | None = None, handled: bool = True,
              bugs_only: bool = False) -> dict[str, Any] | None:
    """A crash as telemetry sends it: where it happened (``WHERE``), the error's type, whether the
    process went on (``handled``), and its innermost frames in code we may name -- cadgen's, the
    standard library's, a dependency's -- each as its file inside that, its function and its line, with
    any run of the person's own code one bare ``<user>``. Never its message, a variable, or a path
    outside those. ``bugs_only``: only a mistake in cadgen's own code (one of ``BUGS``, raised where
    cadgen's code, not the person's, was last), never an error raised on purpose. ``None``: not one to
    send."""
    if where not in WHERE or not isinstance(error, Exception):  # an interrupt, an exit: no crash
        return None
    if where == "command" and isinstance(error, BrokenPipeError) and stdout_closed():  # its reader left: no crash
        return None
    if bugs_only and not isinstance(error, BUGS):  # before reading any frame: a failure is never kept waiting
        return None
    frames: list[dict[str, Any]] = []
    decisive = None  # the innermost frame of cadgen's or of the person's: whose code failed, and at which line
    for frame, line in traceback.walk_tb(error.__traceback__):
        file = _file_of(frame.f_code.co_filename)
        if file is None or file.startswith("cadgen/"):
            decisive = (file, frame.f_code.co_filename, int(line or 0))
        if file is None:
            if not frames or frames[-1]["file"] != USER:
                frames.append({"file": USER, "function": USER, "line": 0})
            continue
        function = frame.f_code.co_qualname
        frames.append({"file": file, "function": function if _FUNCTION.fullmatch(function) else "<?>", "line": int(line or 0)})
    if bugs_only and not (decisive is not None and decisive[0] is not None and _mistake(error, decisive[1], decisive[2])):
        return None
    frames = frames[-MAX_FRAMES:]
    if isinstance(error, RecursionError) and any(frame["file"] == USER for frame in frames) \
            and all(frame["file"] in _THEIR_CYCLE for frame in frames if frame["file"].startswith("cadgen/")):
        return None  # the person's recursion, through no cadgen code but the wrapper that calls their model
    found = {"where": where, "type": _type_of(error), "handled": bool(handled), "frames": frames}
    if tool is not None and _TOOL.fullmatch(str(tool)):
        found["tool"] = tool
    return found


def _mistake(error: BaseException, filename: str, line: int) -> bool:
    """Whether ``error``, last in cadgen's code at ``filename``'s ``line``, is a mistake there: one of ``BUGS``,
    and never at a ``raise`` (``_RAISED``), where cadgen says what it was given in those words on purpose."""
    return isinstance(error, BUGS) and not _RAISED.search(linecache.getline(filename, line))


# Why a failure failed, where cadgen named it (``because``): a word of ``BUILD_FAILURES`` or ``SNAPSHOT_FAILURES``.
_BECAUSE = "__cadgen_failure__"
# Errors that say why by what they are, whoever raised them, by the first of their classes named here (a class
# by its module and name: importing it would import what defines it, the CAD kernel among them). Only a module
# that is not there is the machine's: another ``ImportError`` (``from build123d import Boxx``) is whoever's code
# asked for the name, decided below.
_BUILD_ERRORS: tuple[tuple[type[BaseException] | str, str], ...] = (
    (SyntaxError, "script_error"), (ModuleNotFoundError, "missing_module"), (FileNotFoundError, "missing_file"),
    ("cadgen.assets.AssetMissing", "missing_file"), ("cadgen.store.lazy.ChildBuildError", "child_failed"),
    (TimeoutError, "timeout"), (MemoryError, "memory"), (OSError, "io_error"))


def because(error: BaseException, reason: str) -> BaseException:
    """Name why ``error`` failed (a word of ``BUILD_FAILURES`` or ``SNAPSHOT_FAILURES``) where cadgen raises or
    first catches it: the innermost name stands. ``error``, for ``raise because(...)``. Never raises."""
    with contextlib.suppress(Exception):
        if not isinstance(getattr(error, _BECAUSE, None), str):
            setattr(error, _BECAUSE, reason)
    return error


def _named(error: BaseException, vocabulary: frozenset[str]) -> str | None:
    reason = getattr(error, _BECAUSE, None)
    return reason if reason in vocabulary else None


def _is(error: BaseException, kind: type[BaseException] | str) -> bool:
    if not isinstance(kind, str):
        return isinstance(error, kind)
    return any(f"{cls.__module__}.{cls.__qualname__}" == kind for cls in type(error).__mro__)


def _whose(error: BaseException) -> tuple[str | None, tuple[str, str, int] | None]:
    """Whose code ``error`` came from: where its innermost frame lives (``cadgen``, ``site``, ``stdlib``, or
    ``user``: the person's), and its innermost frame of cadgen's or the person's -- whose, its file, its line."""
    innermost, decisive = None, None
    for frame, line in traceback.walk_tb(error.__traceback__):
        found = _located(frame.f_code.co_filename)
        innermost = found[0] if found else "user"
        if innermost in ("cadgen", "user"):
            decisive = (innermost, frame.f_code.co_filename, int(line or 0))
    return innermost, decisive


def _bug(error: BaseException, decisive: tuple[str, str, int] | None) -> bool:
    """A mistake in cadgen's own code: what ``signature(bugs_only=True)`` reports as a crash."""
    return decisive is not None and decisive[0] == "cadgen" and _mistake(error, decisive[1], decisive[2])


def build_failure(error: BaseException) -> str:
    """Why a build failed (one of ``BUILD_FAILURES``), from what ``error`` is and whose code raised it, never
    from what it says: cadgen's mistake (``bug``, as ``signature`` finds one); a reason cadgen named where it
    raised it (``because``); one its class says (``_BUILD_ERRORS``); else whose code was last -- the person's
    (``model_error``, or ``kernel_error`` when the CAD kernel or a library under it raised), or cadgen's (on
    purpose, ``refused``, or ``export_error`` when the kernel raised under it). Never raises."""
    try:
        innermost, decisive = _whose(error)
        if _bug(error, decisive):
            return "bug"
        named = _named(error, BUILD_FAILURES)
        if named:
            return named
        for kind, reason in _BUILD_ERRORS:
            if _is(error, kind):
                return reason
        if decisive is None:
            return "other"
        if decisive[0] == "user":
            return "kernel_error" if innermost == "site" else "model_error"
        return "export_error" if innermost == "site" else "refused"
    except Exception:  # noqa: BLE001 - a reason never fails the failure it names
        LOG.debug("could not tell why a build failed", exc_info=True)
        return "other"


def snapshot_failure(error: BaseException, otherwise: str = "other") -> str:
    """Why a snapshot failed (one of ``SNAPSHOT_FAILURES``), from what ``error`` is, never what it says:
    cadgen's mistake (``bug``), a reason cadgen named where it raised it (``because``: the browser that did not
    start), a file not there, time or memory run out -- else ``otherwise``, what the snapshot was doing when it
    failed (``cadgen.snapshot_cli``). Never raises."""
    try:
        if _bug(error, _whose(error)[1]):
            return "bug"
        named = _named(error, SNAPSHOT_FAILURES)
        if named:
            return named
        if isinstance(error, FileNotFoundError) or (_is(error, "cadgen.snapshot_core.RouteFileError")
                                                    and getattr(error, "status", None) == 404):
            return "no_file"
        if isinstance(error, TimeoutError) or type(error).__name__ == "TimeoutError":  # the browser's own
            return "timeout"
        if isinstance(error, MemoryError):
            return "memory"
        return otherwise if otherwise in SNAPSHOT_FAILURES else "other"
    except Exception:  # noqa: BLE001 - a reason never fails the failure it names
        LOG.debug("could not tell why a snapshot failed", exc_info=True)
        return "other"


def _exit_status(status: Any) -> bool:
    """Whether ``status`` reads as a process's exit status: an exit code or a signal (``-N``), or on
    Windows the exception code a fault ended it with (an NTSTATUS error, ``0xC0000000`` and up)."""
    return type(status) is int and (-512 < status < 512 or 0xC0000000 <= status <= 0xFFFFFFFF)


def died(status: Any) -> dict[str, Any]:
    """A build worker that died under a job (a native crash, or killed for memory): a crash with no
    frames to show, its exit status what there is to tell."""
    found = {"where": "build", "type": "WorkerDied", "handled": False, "frames": []}
    if _exit_status(status):
        found["status"] = status
    return found


def valid_signature(found: Any) -> bool:
    """Whether a crash another process made -- a page's, a worker's, a command's -- is one this module
    would have made: checked before it is noted, as the receiver checks it again."""
    if not isinstance(found, dict) or not set(found) <= {"where", "type", "handled", "frames", "tool", "status"}:
        return False
    frames = found.get("frames")
    if (found.get("where") not in WHERE or not isinstance(found.get("handled"), bool) or not isinstance(frames, list)
            or len(frames) > MAX_FRAMES or not isinstance(found.get("type"), str)
            or not (found["type"] in (USER, "<?>") or _TYPE.fullmatch(found["type"]))):
        return False
    if "tool" in found and not (isinstance(found["tool"], str) and _TOOL.fullmatch(found["tool"])):
        return False
    if "status" in found and not _exit_status(found["status"]):
        return False
    for frame in frames:
        if not isinstance(frame, dict) or not set(frame) <= {"file", "function", "line", "column", "chunk_id"}:
            return False
        # A page's chunk, by the debug id its build stamped on it and on its source map: nothing else.
        if "chunk_id" in frame and not (found["where"] == "page" and isinstance(frame["chunk_id"], str)
                                        and _CHUNK_ID.fullmatch(frame["chunk_id"])):
            return False
        file, function = frame.get("file"), frame.get("function")
        if not (isinstance(file, str) and (file in (USER, "<?>", "<frozen>") or _FILE.fullmatch(file))):
            return False
        if not (isinstance(function, str) and (function in (USER, "<?>") or _FUNCTION.fullmatch(function))):
            return False
        if any(key in frame and not (type(frame[key]) is int and 0 <= frame[key] < 10_000_000) for key in ("line", "column")):
            return False
    return True


_SINK: Callable[[dict[str, Any]], Any] | None = None  # where this process's crashes go (``collect_crashes``)


def collect_crashes(sink: Callable[[dict[str, Any]], Any] | None) -> None:
    """Where ``report`` puts a crash in this process: its recorder's (the CAD app, the viewer, the
    daemon), or a build worker's job (``cadgen.daemon.telemetry``). With none, it goes to a running
    daemon, which sends it with its own (a ``cadgen`` command's)."""
    global _SINK
    _SINK = sink


def report(error: BaseException, where: str, *, tool: str | None = None, handled: bool = True,
           bugs_only: bool = False) -> None:
    """Note a crash wherever cadgen runs (``signature``, ``collect_crashes``): in memory, or handed to a
    running daemon, never sent from here, and never raising into the code that failed."""
    try:
        found = signature(error, where, tool=tool, handled=handled, bugs_only=bugs_only)
        if found is None:
            return
        if _SINK is not None:
            _SINK(found)
            return
        from cadgen.daemon.client import hand_over

        hand_over({"crashes": [found]})
    except Exception:  # noqa: BLE001 - reporting a crash never makes another
        LOG.debug("could not report a crash", exc_info=True)


def spool(counts: dict[str, Any], *, path: Path | None = None) -> bool:
    """Keep a command's counts for the next process that sends (``Recorder.take``, by way of its flush):
    what it would have handed a running daemon (``cadgen.daemon.client.hand_over``), when there is none --
    ``CADGEN_DAEMON=0``, a platform without one, or none running. One line, under the answer in force
    (``_answer``), and only while sharing is on: a sender takes a line only under that same answer, and a
    no deletes them all (``choose``). Past ``SPOOL_BYTES`` nothing more is kept. Never raises."""
    try:
        if not isinstance(counts, dict) or not any(counts.get(name) for name in ("builds", "snapshots", "features", "crashes")):
            return False  # nothing counted, nothing to keep
        path = path or settings_path()
        if not status(path=path, probe=False)["sharing"]:
            return False
        return _keep(path, SPOOL, {"answer": list(_answer(_read(path) or {})), "counts": counts})
    except Exception:  # noqa: BLE001 - a count kept or not never fails the command that made it
        LOG.debug("could not keep a command's counts", exc_info=True)
        return False


def _take_spool(path: Path, name: str = SPOOL, key: str = "counts") -> list[dict[str, Any]]:
    """What commands kept (``spool``), or exiting processes (``KEPT``, each line a ``batch``), taken whole
    by one process: moved aside under the settings lock, so no line is taken twice or lost to a process
    appending meanwhile."""
    kept = path.with_name(name)
    if not kept.exists():
        return []
    taken = path.with_name(f"{name}{temp_suffix()}")
    with exclusive(path.with_name(LOCK)):
        try:
            replace_atomic(kept, taken)
        except FileNotFoundError:
            return []
    try:
        lines = taken.read_text(encoding="utf-8").splitlines()
    finally:
        with contextlib.suppress(OSError):
            taken.unlink()
    found = []
    for line in lines:
        with contextlib.suppress(ValueError):
            entry = json.loads(line)
            if isinstance(entry, dict) and isinstance(entry.get(key), dict):
                found.append(entry)
    return found


def _keep(path: Path, name: str, entry: dict[str, Any]) -> bool:
    """One line appended to the kept file ``name`` beside the settings, under the settings lock: past
    ``SPOOL_BYTES`` nothing more is kept. A local write, never the network."""
    line = json.dumps(entry, separators=(",", ":"))
    kept = path.with_name(name)
    with exclusive(path.with_name(LOCK)):
        size = kept.stat().st_size if kept.exists() else 0
        if size + len(line) + 1 > SPOOL_BYTES:
            return False
        with open(kept, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return True


def _drop_spool(path: Path) -> None:
    """A no: what commands and exiting processes kept for sending is deleted, not left to be dropped later."""
    with contextlib.suppress(OSError), exclusive(path.with_name(LOCK)):
        path.with_name(SPOOL).unlink(missing_ok=True)
        path.with_name(KEPT).unlink(missing_ok=True)


def _outcome(sent: Any) -> str:
    """What a send returned, read as ``ok``, ``refused`` or ``failed`` (``_post``; a test's sender may say
    ``True`` or ``False``)."""
    return "ok" if sent is True else "failed" if sent in (False, None) else sent


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
    """What a process noted since its last batch: counts under ``EVENTS``' names, and crashes, each
    sent once with how many times it happened."""

    def __init__(self, rows: dict[tuple[str, ...], list[float]] | None = None,
                 crashes: dict[str, list[Any]] | None = None) -> None:
        self.rows = rows if rows is not None else {}  # (event, *names) -> its counts, in ``EVENTS`` order
        self.crashes = crashes if crashes is not None else {}  # its key -> [signature, count]

    def __bool__(self) -> bool:
        return bool(self.rows or self.crashes)

    def crashed(self, found: dict[str, Any], count: int = 1) -> None:
        key = json.dumps(found, sort_keys=True)
        if key in self.crashes:
            self.crashes[key][1] += count
        elif len(self.crashes) < CRASHES_PENDING:
            self.crashes[key] = [found, count]

    def note(self, event: str, names: tuple[str, ...], counts: dict[str, float]) -> None:
        self._add((event, *names), [counts.get(name, 0) for name in EVENTS[event][1]])

    def _add(self, key: tuple[str, ...], values: list[float]) -> None:
        counted = EVENTS[key[0]][1]
        row = self.rows.setdefault(key, [0] * len(counted))
        for index, (name, value) in enumerate(zip(counted, values)):
            row[index] = max(row[index], value) if name == "longest" else row[index] + value

    def merge(self, other: _Tally) -> None:
        """Add ``other``'s counts to these: what a batch had no room for, kept for the next."""
        for key, values in other.rows.items():
            self._add(key, values)
        for found, count in other.crashes.values():
            self.crashed(found, count)

    def split(self, limit: int) -> tuple[_Tally, _Tally]:
        """The first ``limit`` events -- counts first, then up to ``CRASHES_PER_BATCH`` crashes -- and the
        rest: what a batch has room for, and the next batch's."""
        keys = sorted(self.rows)[:limit]
        crashes = list(self.crashes)[:max(0, min(CRASHES_PER_BATCH, limit - len(keys)))]
        return (_Tally({key: self.rows[key] for key in keys}, {key: self.crashes[key] for key in crashes}),
                _Tally({key: value for key, value in self.rows.items() if key not in keys},
                       {key: value for key, value in self.crashes.items() if key not in crashes}))

    def events(self) -> list[dict[str, Any]]:
        events = []
        for key in sorted(self.rows):
            names, counted = EVENTS[key[0]]
            events.append({"name": key[0], **dict(zip(names, key[1:])),
                           **{name: round(value, 1) if name in ("seconds", "longest") else int(value)
                              for name, value in zip(counted, self.rows[key])}})
        return events + [{"name": "exception", **found, "count": count} for found, count in self.crashes.values()]


class Recorder:
    """Notes one process's use -- tool calls, view activity, files on screen, builds, snapshots,
    features and the daemon's health -- and sends it while sharing is on. Every method is guarded
    (see the module docstring): it never raises, and none waits on the network."""

    def __init__(self, *, process: str = "app", path: Path | None = None,
                 send: Callable[[dict[str, Any]], Any] | None = None, interval: float = FLUSH_SECONDS,
                 collect: Callable[[Recorder], Any] | None = None, kept_after: float = KEPT_SECONDS) -> None:
        self.path = path
        # Called as each batch is made, to note what is counted elsewhere (the daemon's pool, ``cadgen.daemon.telemetry``).
        self._collect = collect
        self._send = send or (lambda payload: _post(f"{api_url()}/events", payload))
        self._interval = interval
        self._kept_after = kept_after
        self._lock = threading.Lock()
        self._session = str(uuid.uuid4())
        self._context: dict[str, Any] = {"process": process if process in PROCESSES else "app", "version": "unknown",
                                         "channel": "unknown", "platform": "other"}
        self._named: str | None = None  # the channel this process was told itself (``_channel``)
        self._tally = _Tally()
        # The batch the receiver did not take, whole, and the answer it was made under: sent again, as it is,
        # before anything newer (``flush``). One at most: what is noted meanwhile waits in the tally.
        self._unsent: tuple[dict[str, Any], Any] | None = None
        # The batch on its way now, and its answer: kept as the process exits too (``close``), since its send may
        # yet fail with nothing left to keep it. Sent again when it was taken after all, its ids make it one.
        self._sending: tuple[dict[str, Any], Any] | None = None
        self._day = ""
        self._shown: set[str] = set()  # the files a view showed today, by absolute path: never leaves this process
        self._basis: Any = _UNREAD  # the answer in force when what is noted now began to be noted
        self._choices = 0  # the choices made here: a batch that failed is kept only if none came since
        self._off = False  # a no this process could not keep: nothing more is sent from it
        self._timer: threading.Event | None = None
        self._describe()

    @_guarded(lambda: None)
    def _describe(self) -> None:
        from cadgen import __version__
        from cadgen._internal.channel import named

        self._named = named()
        self._context.update(version=_token(__version__, 32) or "unknown", channel=self._channel(),
                             platform=_platform_name(), arch=_token(_platform.machine().lower(), 16))

    def _channel(self) -> str:
        """Where this install came from: what this process was told itself, else the channel its plugin's server wrote
        down for its installation -- read again for each batch, as the daemon and the viewer outlive the server that
        wrote it -- but never for the CAD server, which only its own plugin names (``cadgen/_internal/channel.py``)."""
        from cadgen._internal.channel import RECORD, UNKNOWN, recorded

        if self._named is not None or self._context["process"] == "app":
            return self._named or UNKNOWN
        return recorded(path=self.path.with_name(RECORD) if self.path else None) or UNKNOWN  # beside the settings

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
            self._tally, self._unsent = _Tally(), None
            self._basis = decision
            self._choices += 1
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
    def called(self, tool: str, ok: bool, reason: str | None = None) -> None:
        """The CAD app ran one of its tools: ``ok`` false when it failed, for ``reason`` (one of ``FAILURES``)."""
        if isinstance(tool, str) and tool not in UNCOUNTED:
            self._note("tool", (tool,), {"calls": 1, "errors": 0 if ok else 1})
            if not ok:
                self._note("tool_failure", (tool, reason if reason in FAILURES else "other"), {"count": 1})

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
        # A compound suffix is one extension: `cable.harness.yml` is a harness, a plain `.yml` nothing.
        kind = FILE_KINDS.get(extension_of(path))
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
    def built(self, kind: str, via: str, outcome: str, seconds: float = 0.0, *, cached: bool = False,
              reason: str | None = None) -> None:
        """The daemon answered a build of a ``kind`` of model asked for ``via`` one of ``VIAS``, ended as one
        of ``OUTCOMES`` after ``seconds``; ``cached``: the store had it, and nothing was built. A failed one
        failed for ``reason`` (one of ``BUILD_FAILURES``; anything else is ``other``)."""
        if kind not in KINDS or via not in VIAS or outcome not in OUTCOMES:
            return
        took = _seconds(seconds)
        self._note("build", (kind, via), {"count": 1, "failed": outcome == "failed", "crashed": outcome == "crashed",
                                          "cancelled": outcome == "cancelled", "cached": bool(cached) and outcome == "ok",
                                          "seconds": took, "longest": took})
        if outcome == "failed":
            self._note("build_failure", (kind, via, reason if reason in BUILD_FAILURES else "other"), {"count": 1})

    @_guarded(lambda: None)
    def rendered(self, kind: str, ok: bool, seconds: float = 0.0, reason: str | None = None) -> None:
        """A snapshot of a ``kind`` of file was rendered, or failed to be, for ``reason`` (one of
        ``SNAPSHOT_FAILURES``; anything else is ``other``)."""
        if kind in KINDS:
            self._note("snapshot", (kind,), {"count": 1, "failed": not ok, "seconds": _seconds(seconds)})
            if not ok:
                self._note("snapshot_failure", (kind, reason if reason in SNAPSHOT_FAILURES else "other"), {"count": 1})

    @_guarded(lambda: None)
    def used(self, feature: str) -> None:
        """One of ``FEATURES`` was used."""
        if feature in FEATURES:
            self._note("feature", (feature,), {"count": 1})

    @_guarded(lambda: None)
    def crashed(self, error: BaseException | dict[str, Any], where: str = "", **detail: Any) -> None:
        """A crash: an error caught here, made into its ``signature``, or one another process made (a
        page's, a build worker's, a command's), noted only if it is one this module would make."""
        found = (signature(error, where, **detail) if isinstance(error, BaseException)
                 else error if valid_signature(error) else None)
        if found is None:
            return
        answer = self._first_use()
        with self._lock:
            self._begin(answer)
            self._tally.crashed(found)

    @_guarded(lambda: None)
    def health(self, name: str, count: int = 1) -> None:
        """The daemon's build workers: one of ``HEALTH`` happened ``count`` times."""
        if name in HEALTH and isinstance(count, int) and count > 0:
            self._note("health", (), {name: count})

    @_guarded(lambda: None)
    def take(self, counts: Any) -> None:
        """A command's counts, handed to this process (``cadgen.daemon.client.hand_over``) or kept for the
        next one that sends (``spool``): the builds it made itself, the snapshots it rendered, the features it
        used and its crashes. Anything else in it, or past ``HANDED`` of any, is not counted."""
        if not isinstance(counts, dict):
            return

        def each(name: str) -> list[Any]:
            found = counts.get(name)
            return found[:HANDED] if isinstance(found, list) else []

        for build in each("builds"):
            if isinstance(build, dict):
                self.built(build.get("kind"), build.get("via"), build.get("outcome"), build.get("seconds"),
                           cached=build.get("cached") is True, reason=build.get("reason"))
        for snapshot in each("snapshots"):
            if isinstance(snapshot, dict) and isinstance(snapshot.get("ok"), bool):
                self.rendered(snapshot.get("format"), snapshot["ok"], snapshot.get("seconds"), snapshot.get("reason"))
        for feature in each("features"):
            self.used(feature)
        for crash in each("crashes"):
            self.crashed(crash)  # checked there: a command is another process

    @_guarded(lambda: None)
    def _drain(self) -> None:
        """Take what commands kept for a sender (``spool``): only what they counted under the answer in force
        now -- the rest was noted under another, and is dropped as this process's own would be."""
        settings = self.path or settings_path()
        kept = _take_spool(settings)
        if not kept:
            return
        answer = list(_answer(_read(settings) or {}))
        for entry in kept:
            if entry.get("answer") == answer:
                self.take(entry["counts"])

    @_guarded(lambda: False)
    def flush(self) -> bool:
        """Send what was used since the last batch, if sharing is on; drop it if not. A deletion still owed
        is asked for first, then the batches exiting processes kept (``send_kept``), then the batch this one
        could not send (``_resend``): while that is still owed, what came since waits for a later batch. A
        batch with no use in it is not sent. It waits on the network: only the background sender calls it."""
        if self._collect is not None:
            self._collect(self)
        self._drain()
        settings = self.path or settings_path()
        forget_pending(path=settings)
        self.send_kept()
        if not self._resend(settings):
            return False
        taken = self._batch(settings)
        if taken is None:
            return False
        payload, answer, choices = taken
        with self._lock:
            self._sending = (payload, answer)
        try:
            outcome = _outcome(self._send(payload))
        finally:
            with self._lock:
                self._sending = None
        if outcome == "failed":  # kept whole, its id and all, to be sent again -- unless a choice made here
            with self._lock:     # while it was on its way cleared it (two answers can share a tick)
                if self._choices == choices:
                    self._unsent = (payload, answer)
        # refused: dropped, or it would be refused again with everything after it
        if outcome == "ok":
            self._owe_deletion_if_gone(settings, payload["install"])
        return outcome == "ok"

    def _resend(self, settings: Path) -> bool:
        """Send again, byte for byte, the batch the receiver did not take: the receiver may have taken it after
        all and its answer been lost, and its id (``batch``) tells it so. Only under the answer it was made
        under, as a kept batch is (``send_kept``): under another it is dropped. ``True`` when nothing is owed
        any more -- sent, refused or dropped -- and a new batch may go. It waits on the network."""
        with self._lock:
            unsent, choices = self._unsent, self._choices
        if unsent is None:
            return True
        payload, answer = unsent
        sharing = not self._off and status(path=self.path, probe=False)["sharing"]
        outcome = (_outcome(self._send(payload)) if sharing and _answer(_read(settings) or {}) == answer
                   else "dropped")
        with self._lock:
            if outcome == "failed" and self._choices == choices:
                return False  # still owed: offline, or the receiver is down
            if self._unsent is unsent:
                self._unsent = None
        if outcome == "ok":
            self._owe_deletion_if_gone(settings, payload["install"])
        return True

    def _batch(self, settings: Path) -> tuple[dict[str, Any], Any, int] | None:
        """The batch of what this process noted since its last, taken from it: its payload -- under an id of
        its own, stamped with the time it was made -- the answer it was made under, and the choices made here
        when it was taken; or ``None``, with nothing to send under the answer in force, which drops what was
        noted under another. Reads the settings, never the network."""
        with self._lock:
            if not self._tally:  # nothing to send, nor an answer to read: the next use reads its own
                self._basis = _UNREAD
                return None
        found = dict(UNAVAILABLE) if self._off else status(path=self.path, probe=False)
        decided = _answer((_read(settings) or {}) if found["sharing"] else {})  # which answer is in force (``_answer``)
        where = self._channel()
        with self._lock:
            tally, basis, choices = self._tally, self._basis, self._choices
            self._tally, self._basis = _Tally(), decided
            context = {**self._context, "channel": where}
            # Noted under an earlier answer -- before a yes given in another process (this one's own clears
            # what it noted), before the person was told, or under one never read: never sent. Which answer,
            # not whether it came later: Windows' clock moves in 16 ms steps, so a yes and the batch it lands
            # in can share a time.
            if not found["sharing"] or decided != basis:
                return None
            sending, later = tally.split(MAX_EVENTS)
            self._tally.merge(later)  # past the batch's room: the next batch's
        events = sending.events()
        if not events:
            return None
        return ({"schema": SCHEMA, "batch": str(uuid.uuid4()), "at": int(time.time()), "install": found["id"],
                 "session": self._session, **context, "events": events}, decided, choices)

    @_guarded(lambda: None)
    def send_kept(self) -> None:
        """Send the batches processes kept as they exited (``close``), each as it was made, while this one
        may send: only those made under the answer in force now, as their process would have. Those the
        receiver did not take are kept again for a later send. It waits on the network: only the
        background sender calls it."""
        settings = self.path or settings_path()
        if self._off or not status(path=self.path, probe=False)["sharing"]:
            return  # left for a process that may send: a no deletes them (``choose``)
        kept = _take_spool(settings, KEPT, "batch")
        answer = list(_answer(_read(settings) or {}))
        for index, entry in enumerate(kept):
            if entry.get("answer") != answer:
                continue
            outcome = _outcome(self._send(entry["batch"]))
            if outcome == "failed":  # offline, or the receiver is down: this one and the rest wait for later
                for rest in kept[index:]:
                    if rest.get("answer") == answer:
                        _keep(settings, KEPT, rest)
                return
            if outcome == "ok" and isinstance(entry["batch"].get("install"), str):
                self._owe_deletion_if_gone(settings, entry["batch"]["install"])

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
        """Send every ``interval`` seconds (``FLUSH_SECONDS``), in the background, until ``close`` -- and, a
        moment after it starts (``KEPT_SECONDS``), what processes kept as they exited."""
        stop = self._timer = threading.Event()

        def loop() -> None:
            if not stop.wait(self._kept_after):
                self.send_kept()
            while not stop.wait(self._interval):
                self.flush()

        threading.Thread(target=loop, name="cadgen-telemetry", daemon=True).start()

    @_guarded(lambda: None)
    def close(self) -> None:
        """As the process exits: the batch it could not send, the one on its way, and what it noted since, are kept
        beside the settings, each whole and in that order (``KEPT``), for the next process that sends (``send_kept``) --
        never sent from here, so an exit waits on nothing but a local file. Only under the answer each was made
        under, and only while that is still in force."""
        if self._timer is not None:
            self._timer.set()
        if self._collect is not None:
            self._collect(self)
        settings = self.path or settings_path()
        with self._lock:
            unsent, self._unsent = self._unsent, None
            sending = self._sending
        for owed in (unsent, sending):
            if owed is not None and not self._off and status(path=self.path, probe=False)["sharing"] \
                    and _answer(_read(settings) or {}) == owed[1]:
                _keep(settings, KEPT, {"answer": list(owed[1]), "batch": owed[0]})
        taken = self._batch(settings)
        if taken is not None:
            _keep(settings, KEPT, {"answer": list(taken[1]), "batch": taken[0]})

    def _background(self, work: Callable[[], Any]) -> threading.Thread:
        def run() -> None:
            try:
                work()
            except Exception:  # noqa: BLE001 - a thread's traceback would land in the host's logs
                LOG.debug("telemetry background work failed", exc_info=True)

        thread = threading.Thread(target=run, name="cadgen-telemetry-once", daemon=True)
        thread.start()
        return thread
