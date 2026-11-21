"""A manufacturing check's life in the engine (``Runner``): asked, answered from what was kept or measured in a
checks process, and stopped when it must be.

Every check is measured in a checks process (``checks.Pool``), from a file's path or from the bytes of the
document the engine holds -- never in a model's warm worker, so a check holds up no build, inspection or
view of its document, and a build never has a check to cancel. Which process measures is the runner's choice
alone: what it asks of one -- to describe a document, to measure it -- and every key it keeps a result by say
nothing of where they run. Each asked check has one ``State``, changed under the runner's one lock:

- ``ASKED``: what was kept of it is looked for, and its document read.
- ``WAITING``: for a slot of the pool; it holds no process.
- ``STARTING``: a slot is its own, and the slot's checks process is leased, started where none lives.
- ``MEASURING``: that process is its own (``Asked.process``), from its first request to its last -- a describing
  of its document, then its measuring -- so its limits and every stop count them as one.
- ``ANSWERED``: its process answered all it was asked, or was lost.
- stopped by the engine, each the reason its callers are told (``FAILURES``): ``CANCELLED`` (every caller of
  it gone, its process given to a check someone waits for), ``STOPPED`` (the engine stops), ``OVER_TIME`` and
  ``OVER_MEMORY`` (past a check's own limits, ``Limits``), ``SUPERSEDED`` (its model was built again under it,
  ``Runner.built``).

A check is stopped only before it has ended (``_stop``): one waiting leaves the pool's queue, one
measuring has its process killed -- the process its own lease holds, signalled under the lock, which the
lease's end takes too before it lets the process go, so no stop ever reaches a process another check has
(a checks process holds nothing of anyone's: what it read for checks goes with it, and the next check
starts a fresh one).

A check that does not complete answers ``{"failed": words, "reason": ...}`` (``api.EngineError.reason``),
never a result: ``cancelled``, ``stopped``, ``over_time``, ``over_memory``, ``process_lost`` (its checks
process exited under it), ``no_kernel`` (none could be started) and ``superseded`` (its document was built
again, or its file rewritten, while it was measured: the result is of a version that is gone, so it is neither
kept nor answered).

**A document that moves on under its check.** A model built to a new generation while a check of it is asked
is told by the daemon as the build registers (``Runner.built``): the check stops at once, its process killed,
so it holds neither its slot nor its callers for a result no one can use. While a caller of it is still there
the check is then asked again, of the document as it is now (``READS`` times at most: a document built again
under each answers ``superseded``); with none it ends there. A build that changes nothing keeps its generation,
and one of another model is another document: neither stops a check.

**What is kept.** A manufacturing process's check by what was measured (``_content``,
``measurements.Measurements``): the record of what its document's version holds, which a checks process
describes once and the store remembers, says with no kernel which measurement the check reads, and that
measurement's report is found or made and kept under the record's key and its own -- so every check that reads
the same parts the same way finds it, whatever document, path, declared process or option its rules alone read
it came with, and each answers its own process, options and findings. The interference check, which keeps each
pair's answer itself, by its document's version and the whole check (``_versioned``, ``checks.Checks``). Under
the one lock a check's end keeps its result before it leaves ``running``, so the same check asked next finds it
kept or joins it; two checks that only read one measurement are no one check there, and each looks once more for
what the other kept as it gets its process.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import os
import secrets
import signal
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from cad.engine.client import WORKER_STDERR
from cad.engine.frames import failed_type
from cad.engine.worker import CHECK_SECONDS, check_limits, resident_of

from cad_server.engine.checks import Checks, Pool, Withdrawn, digest
from cad_server.engine.measurements import Measurements, build_token, file_token, is_record, model_token
from cad_server.engine.supervisor import Gone

__all__ = ["FAILURES", "SECONDS", "STOPPED", "SUPERSEDED", "Asked", "Limits", "Runner", "State", "file_key",
           "resident_of"]

# A check measured this long is stopped (``Limits``): ``CAD_ENGINE_CHECK_SECONDS``, by default half an hour.
SECONDS = CHECK_SECONDS
# How often the watchdog looks at the checks measuring (``Runner._watch``).
WATCH_SECONDS = 1.0
# How many times a check is asked of its document as it is now because a build replaced it, or its file was
# rewritten, before or while it was measured: past them it answers ``superseded``.
READS = 3


class State(enum.Enum):
    ASKED = "asked"
    WAITING = "waiting"
    STARTING = "starting"
    MEASURING = "measuring"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    STOPPED = "stopped"
    OVER_TIME = "over_time"
    OVER_MEMORY = "over_memory"
    SUPERSEDED = "superseded"


# The states a check can be stopped in: once it is in any other, it has ended.
LIVE = (State.ASKED, State.WAITING, State.STARTING, State.MEASURING)
STOPPED = ("the CAD server stopped while it measured the manufacturing check (an update or `cad stop` stops it): "
           "run the check again")
SUPERSEDED = ("the document changed while its manufacturing check ran, so nothing of that check is kept or "
              "answered: run the check again")
# What the callers of a check the engine stopped are told, by the state it was stopped in.
FAILURES = {
    State.CANCELLED: "the manufacturing check was stopped and its checks process given to another check: every "
                     "caller of it had gone; run the check again",
    State.STOPPED: STOPPED,
    State.OVER_TIME: "the manufacturing check was stopped after {seconds:.0f} s, over a check's time limit of "
                     "{limit:g} s: nothing was measured. Check a smaller part or fewer samples, or raise the limit "
                     "(CAD_ENGINE_CHECK_SECONDS, in the environment the CAD server starts in; 0 for none)",
    State.OVER_MEMORY: "the manufacturing check was stopped with its process at {resident:.0f} MB, over a check's "
                       "memory limit of {limit:.0f} MB: nothing was measured. The part may be too large to check "
                       "on this machine; check a smaller part, or raise the limit (CAD_ENGINE_CHECK_RSS_MB, in the "
                       "environment the CAD server starts in; 0 for none)",
    State.SUPERSEDED: SUPERSEDED,
}


class Limits:
    """What one check may take before the engine stops it: ``seconds`` measuring (None: no limit) and
    ``memory()``, its process's resident memory in MiB (None: no limit). ``notes``: what was said of a setting
    that is no number."""

    def __init__(self, seconds: float | None = SECONDS, memory: Callable[[], float | None] = lambda: None,
                 notes: tuple[str, ...] = ()) -> None:
        self.seconds, self.memory, self.notes = seconds, memory, notes

    @classmethod
    def of_environment(cls, cap: Callable[[], float | None]) -> "Limits":
        """The daemon's (``worker.check_limits``): ``CAD_ENGINE_CHECK_SECONDS`` (by default ``SECONDS``) and
        ``CAD_ENGINE_CHECK_RSS_MB`` (by default ``cap()``, the memory the engine holds all its processes to
        together, ``CAD_ENGINE_WORKER_RSS_MB``: one check alone never takes it all); ``0`` for no limit."""
        return cls(*check_limits(cap))

    def status(self) -> dict[str, Any]:
        return {"seconds": self.seconds, "rssMb": self.memory(), **({"notes": list(self.notes)} if self.notes else {})}


class Asked:
    """A check asked of the engine and not yet ended: its ``state``; what it is (``what``: its type, process and
    document or file); its callers (each one's ``gone``, set at its end of file: its own, then every one attached
    to it; None for one asked from within the engine, which never goes); its place in ``Runner.running``
    (``same``; None for a check kept under no version); the slot of the pool it holds and the checks process
    leased for it, while it has them; when it was asked and since when it measures; its answer, once it has
    one; and ``finished``, set when it has ended."""

    def __init__(self, token: str, what: dict[str, Any], gone: threading.Event | None,
                 same: tuple[str, str, str] | None) -> None:
        self.token, self.what, self.same = token, dict(what), same
        self.state = State.ASKED
        self.callers: list[threading.Event | None] = [gone]
        self.slot: str | None = None
        self.process: Any = None
        self.began = time.time()
        self.since: float | None = None
        self.why: dict[str, float] = {}  # what a stop's words say: the seconds, the memory, the limit
        self.answer: dict[str, Any] | None = None
        self.finished = threading.Event()

    def abandoned(self) -> bool:
        """Whether every caller of it, and every caller attached to it since, has gone."""
        return bool(self.callers) and all(gone is not None and gone.is_set() for gone in self.callers)

    def there(self) -> int:
        """How many of its callers are still there."""
        return sum(1 for gone in self.callers if gone is None or not gone.is_set())

    def failure(self) -> dict[str, Any]:
        """What its callers are told of the stop it is in (``FAILURES``)."""
        return {"failed": FAILURES[self.state].format(**self.why), "reason": self.state.value,
                **({"stopped": True} if self.state is State.STOPPED else {})}


class _Ended(Exception):
    """A check that ended with no answer of a checks process to go on from -- stopped, its process lost, none
    that could be started: what its callers are told (``answer``)."""

    def __init__(self, answer: dict[str, Any]) -> None:
        super().__init__(answer.get("reason"))
        self.answer = answer


@dataclasses.dataclass
class _Try:
    """One try of a check, of its document as it was when the try began: the request's source (``spec``) and
    ``check`` and what measures in its caller (``measures``); the document's id, for one the engine holds; its
    key among the checks (``document``) and its version then (``before``: a model's generation, the digest of a
    file's bytes; None for none); the id and version of it that outlive the engine (``durable``); how many
    times it had been deleted (``since``); and, for a manufacturing check, what the kept measurements name that
    version by (``token``: ``measurements.model_token``, ``build_token`` or ``file_token``; None for none)."""

    spec: dict[str, Any]
    check: dict[str, Any]
    measures: dict[str, Any]
    ident: str | None
    document: str
    before: str | None
    durable: tuple[str, str] | None
    since: int
    token: tuple[str, ...] | None = None


class Runner:
    """The engine's manufacturing checks (the module): ``check`` answers one, ``reap``, ``halt`` and the watchdog
    stop them, ``status`` lists them. Of the daemon it takes what it cannot know: ``store`` (the interference
    check's kept results, by a document's version), ``measurements`` (the manufacturing processes' kept
    measurements, by what was measured; by default a store in memory alone) and ``pool`` (the checks
    processes' slots); ``lease(slot)`` and ``release(process)``, a slot's checks process for one check's
    requests; ``version(ident)``, a model document's generation (None: no such document; ``ValueError``: a
    refusal); ``read(ident)``, the document as a checks process reads it -- ``({"path"}, b"")`` for a file's,
    ``({"document", "name"}, its xbf bytes)`` for a model's -- or ``ValueError``; ``durable(ident, version)``,
    the version of it that outlives the engine with its id, or None; ``stopping()``, whether the engine stops;
    ``limits``; and ``resident``, a process's memory read from outside it."""

    def __init__(self, store: Checks, pool: Pool, *, lease: Callable[[str], Any], release: Callable[[Any], None],
                 version: Callable[[str], str | None], read: Callable[[str], tuple[dict[str, Any], bytes]],
                 durable: Callable[[str, str | None], tuple[str, str] | None],
                 stopping: Callable[[], bool] = lambda: False, limits: Limits | None = None,
                 resident: Callable[[int | None], float | None] = resident_of,
                 measurements: Measurements | None = None) -> None:
        self.store, self.pool = store, pool
        self.measurements = measurements if measurements is not None else Measurements()
        self._lease, self._release, self._version, self._read, self._durable = lease, release, version, read, durable
        self.stopping, self.limits, self.resident = stopping, limits or Limits(), resident
        self.lock = threading.Lock()
        # The checks asked and not yet ended, by their token; and by what they check (document, version,
        # check), what the same check asked meanwhile attaches to.
        self.asked: dict[str, Asked] = {}
        self.running: dict[tuple[str, str, str], Asked] = {}
        self.watching = False

    # --- one check ----------------------------------------------------------------------------------

    def check(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None],
              gone: threading.Event | None = None) -> None:
        """A manufacturing check (an ``export`` request with ``check``, ``api.check``) of the document the
        request names, answered through ``send``; ``gone``: set once its caller has hung up.

        A check whose measurement was kept is answered from it (``reused``), in memory, else on disk, with no
        process asked and none of the document's bytes read where the engine knows what the version holds
        (``_content``: a manufacturing process's, by what was measured; ``_versioned``: the interference
        check's, by its document's version); the same check asked while it runs waits for it and answers with
        its answer, saying so, so it is measured once. Else it is measured in a checks process of the server's
        own library, when that is the caller's (its release, ``caller``, and what measures in it, ``measures``:
        ``contract.measures_for``): another's is answered at once with no ``checked``, and its caller measures
        the document its own way. A version is a model's generation, read before its bytes and again after the
        check, or the digest of a file's bytes: nothing is kept of a check whose document moved on under it,
        which is stopped (``built``) and asked again of the document as it is now while a caller of it is
        there, ``READS`` times at most, then answers ``superseded`` (the module). A check runs to its end
        whoever asked it: its caller going leaves it running and its result kept, unless a check whose caller
        is there needs its slot (``reap``)."""
        from cad.engine.contract import measures_for
        from cad.engine.ids import file_id
        from cad.engine.previous import version as release

        def told(message: dict[str, Any]) -> None:
            try:
                send(message)
            except OSError:
                pass  # its caller went: the check goes on, and its result is kept for the next to ask

        refusal = _refusal(request)
        if refusal is not None:
            told({"failed": refusal, "kind": "builtins:ValueError"})
            return
        spec, check = request["source"], request["check"]
        measures = request.get("measures")
        nobody = {"done": {"reports": [], "files": [], "release": release()}}
        if not isinstance(measures, dict) or request.get("caller") != release():
            told(nobody)  # another release's library, or one that does not say what measures in it
            return
        known = self.pool.known()
        if known is not None and not measures_for(measures, known):
            told(nobody)  # other code or libraries than the checks processes': never measured to be thrown away
            return
        # A manufacturing process's check is kept by what was measured (``_content``); the interference check, which
        # keeps its own answers by the pairs it measured, by its document's version (``_versioned``).
        content = check.get("process") != INTERFERENCE
        if content and not _digests(measures):
            told(nobody)  # no word of the code that measures each process: nothing of its is kept or found here
            return
        self.store.listed()  # once: what an earlier release kept by a document's version is removed, never read
        key = Checks.key(check, release(), measures.get("code"))
        ident = str(spec["id"]) if "id" in spec else None
        what = {"type": check.get("type"), "process": check.get("process"),
                **({"document": ident} if ident is not None else {"file": str(spec["path"])})}

        def serves(by: Any) -> bool:
            return measures_for(measures, by)

        reads = 0
        while True:
            try:
                if ident is not None:
                    document, before = f"model:{ident}", self._version(ident)
                    durable = self._durable(ident, before)
                    token = (None if before is None else
                             model_token(*durable) if durable is not None else build_token(ident, before))
                else:
                    path = str(spec["path"])
                    document, before = file_key(path), digest(Path(path))
                    durable = None if before is None else (file_id(os.path.normcase(os.path.realpath(path))), before)
                    token = None if before is None else file_token(before, path)
            except ValueError as error:
                told(_refused(error))
                return
            since = (self.measurements.epoch(ident) if content else
                     self.store.epoch(durable[0] if durable is not None else ident))
            attempt = _Try(spec, check, measures, ident, document, before, durable, since, token if content else None)
            same = (document, before, key) if before is not None else None
            with self.lock:
                # Under one lock with a check's end (which keeps its result, then leaves ``running``) and with
                # a reaping (which takes its victim out of it): a check of this version is kept, or running, or
                # this one is the one to run.
                running = self.running.get(same) if same is not None else None
                if running is None:
                    asked = Asked(str(check.get("token") or secrets.token_hex(8)), what, gone, same)
                    while asked.token in self.asked:
                        asked.token = secrets.token_hex(8)
                    self.asked[asked.token] = asked
                    if same is not None:
                        self.running[same] = asked
                else:
                    running.callers.append(gone)  # a caller of it too: while one is there, it is not abandoned
            if running is not None:
                self.store.attached()
                told({"log": "waiting for the same manufacturing check, started "
                             f"{time.time() - running.began:.0f} s ago", "stream": "waiting"})
                running.finished.wait()  # it ends with its process, which the watchdog holds to its limits
                done = (running.answer or {}).get("done")
                checked = done.get("checked") if isinstance(done, dict) else None
                if running.answer is None or (isinstance(done, dict) and not (
                        isinstance(checked, dict) and serves(checked.get("measures")))):
                    continue  # it read its document again, or its measurer measures for another: this one's own
                told(_attached(running.answer))
                return
            try:
                answer = (self._content(asked, attempt, told) if content else
                          self._versioned(asked, attempt, key, serves, told))
                if answer is None:
                    # A build landed as its bytes were read: nothing is measured of a version gone.
                    reads += 1
                    if reads < READS:
                        continue
                    answer = {"failed": SUPERSEDED, "reason": "superseded"}
                elif answer.get("reason") == State.SUPERSEDED.value:
                    reads += 1
                    if reads < READS and not asked.abandoned():
                        # Nothing of the version gone is answered: the document as it is now is checked, for
                        # its callers still there (those attached ask again as this one ends unanswered).
                        told({"log": "the document changed while its manufacturing check ran: checking it as "
                                     "it is now", "stream": "waiting"})
                        continue
                asked.answer = answer
                told(answer)
                return
            finally:
                with self.lock:
                    self.asked.pop(asked.token, None)
                    if same is not None and self.running.get(same) is asked:
                        self.running.pop(same)
                asked.finished.set()

    def _content(self, asked: Asked, attempt: _Try, told: Callable[[dict[str, Any]], None]) -> dict[str, Any] | None:
        """One try of a manufacturing check, kept by what was measured (``measurements.Measurements``): its
        answer; None where a build landed as its document's bytes were read, so nothing was asked of them.

        What the document's version holds is its content record: the one kept for it (its alias), else the one
        a checks process says of it (``describe``: read, nothing measured), kept from then on. The record says
        what the check asks, kernel-free (``kept.asked``): the process named -- the one the parts declare, for
        a check given none -- its options, and so the one measurement it reads (``kept.measure_key``); or that
        there is nothing to measure or the check is refused, answered from the record. That measurement's
        report is the one kept for it, else measured -- in the process that described the document, where one
        did, for the process named and with the options its measurement reads alone -- and kept unless its
        measurer says it is not to be (``_keepable``). Either way the answer is this check's own: its process,
        its options as resolved, and after the report's findings the one that says a process was declared.

        A describing is part of the check's life: under its lease, stopped and limited as its measuring is.
        A report is kept under the key of the record its measurer says it measured (``content_key``); where
        that is not the record the check was resolved from -- its alias told wrong, its file was rewritten
        between its describing and its measuring -- nothing of it is kept or answered, the alias is forgotten
        and the check asked again, as of a document that changed."""
        from cad._internal.dfm import kept
        from cad.engine.contract import measures_for
        from cad.engine.previous import version as release

        check, measures, store = attempt.check, attempt.measures, self.measurements
        superseded = {"failed": SUPERSEDED, "reason": State.SUPERSEDED.value}
        token = attempt.token
        # What an answer made here of the store alone says beside its result, as a checks process's does.
        here = {"release": release(), **({"digest": attempt.before} if attempt.ident is None else {})}

        def answered(checked: dict[str, Any], reused: bool = False) -> dict[str, Any]:
            return {"done": {"reports": [], "files": [], "checked": checked, **({"reused": True} if reused else {})}}

        def asks(record: dict[str, Any]) -> dict[str, Any]:
            """What the check asks of a document of ``record`` (``kept.asked``), with its measurement's key
            (``measure``) and whom a kept result of it must have been measured by (``by``): the digest of the
            code that measures its process in the caller, and the caller's libraries."""
            try:
                ask = kept.asked(record, check)
            except Exception as error:  # noqa: BLE001 - the check's own failure: its words, as a process says one
                return {"failed": f"{type(error).__name__}: {error}", "reason": "error"}
            if "process" in ask:
                code = measures["dfm"][ask["process"]]
                ask["measure"] = kept.measure_key(check["type"], ask["process"], bool(check.get("candidates")),
                                                  ask["resolved"], code)
                ask["by"] = {"code": code, "libraries": measures["libraries"]}
            return ask

        def mine(ask: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
            """``report`` as this check's ``measured``: for its process and options, the finding that says its
            process was declared after the report's own, where it was."""
            if ask["declared"] is not None:
                report = {**report, "findings": [*(report.get("findings") or ()), ask["declared"]]}
            return {"process": ask["process"], "resolved": ask["resolved"], "report": report}

        def found(record: dict[str, Any], ask: dict[str, Any], said: dict[str, Any]) -> dict[str, Any] | None:
            """The check's answer from the record and what is kept, ``said`` beside it; None for a measurement
            still to make."""
            if "failed" in ask:
                return ask
            if "process" not in ask:
                return answered({**ask, **said})  # nothing to measure, or refused: the record says so
            result = store.get(record["key"], ask["measure"], lambda by: measures_for(ask["by"], by))
            if result is None:
                return None
            return answered({"measured": mine(ask, result["report"]), **said}, reused=True)

        def known() -> dict[str, Any] | None:
            """The record kept for the try's version, where what described it describes for the caller."""
            return store.content(token, lambda by: measures_for(measures, by)) if token is not None else None

        record = known()
        ask: dict[str, Any] = {}
        if record is not None:
            ask = asks(record)
            answer = found(record, ask, here)
            if answer is not None:
                return answer
        if self.stopping():
            return {"failed": STOPPED, "reason": State.STOPPED.value, "stopped": True}
        try:
            read = self._read_at(attempt)
        except ValueError as error:
            return _refused(error)
        if read is None:
            return None
        source, payload = read
        order = {"id": 1, "op": "export", "source": source, "destinations": [], "cwd": None}
        try:
            with self._leased(asked, attempt.document, told) as request:
                # While it waited for its process, another check may have described this version, or kept the
                # measurement this one reads: each is looked for once more before the process is asked for it.
                if record is None:
                    record = known()
                    if record is not None:
                        ask = asks(record)
                if record is not None:
                    answer = found(record, ask, here)
                else:
                    answer = request({**order, "check": {"describe": True, "type": check["type"],
                                                         "token": asked.token, "measures": measures}}, payload, more=True)
                    described = _checked(answer)
                    if described is None:
                        return answer  # it failed there, or that process describes for another: nothing was measured
                    if described.get("changed"):
                        return superseded  # a file rewritten while it was read: of no version at all
                    store.counted(read=bool(described.get("read")))
                    record = described.get("content")
                    if record is None:
                        return answer  # a document that does not read: said as its check's answer, nothing kept
                    if not is_record(record):
                        return {"failed": "the checks process described the document as no content record",
                                "reason": "error"}
                    by = described.get("measures")
                    if attempt.ident is None:  # a file's alias is of the bytes that were described
                        token = file_token(described["digest"], attempt.spec["path"]) if isinstance(
                            described.get("digest"), str) else None
                    if token is not None and isinstance(by, dict):
                        store.name(token, record, {"code": by.get("code"), "libraries": by.get("libraries")},
                                   since=attempt.since)
                    ask = asks(record)
                    answer = found(record, ask, {name: said for name, said in described.items() if name != "content"})
                if answer is not None:
                    return answer
                with self.lock:
                    asked.what["process"] = ask["process"]
                answer = request({**order, "check": {
                    "type": check["type"], "process": ask["process"],
                    "resolved": kept.measuring(ask["process"], ask["resolved"]),
                    "candidates": bool(check.get("candidates")), "token": asked.token, "measures": measures}}, payload)
        except _Ended as ended:
            return ended.answer
        measured = _checked(answer)
        if measured is None:
            return answer  # the measuring failed there, or that process measures for another
        _current, moved = self._stood(attempt, measured)
        if not measured.get("changed"):
            self.store.counted(read=bool(measured.get("read")))
        if moved:
            return superseded
        if not (isinstance(measured.get("measured"), dict) and isinstance(measured["measured"].get("report"), dict)):
            return answer  # no part a process makes, a document that did not read: as said, never kept
        if measured.get("content_key") != record["key"]:
            # It measured other parts than the record says: the alias told wrong, or the file was rewritten since
            # it was described. Nothing of it stands for this check: asked again, of the document as it reads now.
            if token is not None:
                store.forget(token)
            return superseded
        by = measured.get("measures")
        made = ({"code": by["dfm"].get(ask["process"]), "libraries": by.get("libraries")}
                if isinstance(by, dict) and isinstance(by.get("dfm"), dict) else None)
        if _keepable(measured) and made is not None and measures_for(ask["by"], made):
            store.keep(record["key"], ask["measure"], {"report": measured["measured"]["report"]}, made)
        said = {name: value for name, value in measured.items() if name not in ("measured", "content_key", "transient")}
        return answered({"measured": mine(ask, measured["measured"]["report"]), **said})

    def _versioned(self, asked: Asked, attempt: _Try, key: str, serves: Callable[[Any], bool],
                   told: Callable[[dict[str, Any]], None]) -> dict[str, Any] | None:
        """One try of a check kept by its document's version (``checks.Checks``): what was kept of it, else its
        document read and the check measured in a checks process, its result kept where the version stood and
        it is clean. Its answer; None where a build landed as its bytes were read, so nothing was measured."""
        document, before = attempt.document, attempt.before
        kept = self.store.get(document, before, key, attempt.durable, serves) if before is not None else None
        if kept is not None:
            return {"done": {"reports": [], "files": [], "checked": kept, "reused": True}}
        if self.stopping():
            return {"failed": STOPPED, "reason": State.STOPPED.value, "stopped": True}
        try:
            read = self._read_at(attempt)
        except ValueError as error:
            return _refused(error)
        if read is None:
            return None
        source, payload = read
        order = {"id": 1, "op": "export", "source": source, "destinations": [], "cwd": None,
                 "check": {**attempt.check, "token": asked.token, "measures": attempt.measures}}
        answer = self._measure(asked, document, order, payload, told)
        done = answer.get("done")
        measured = done.get("checked") if isinstance(done, dict) else None
        if isinstance(measured, dict):
            current, moved = self._stood(attempt, measured)
            if not measured.get("changed"):
                self.store.counted(read=bool(measured.get("read")))
            if moved:
                answer = {"failed": SUPERSEDED, "reason": "superseded"}
            by = measured.get("measures")
            if "done" in answer and before is not None and current and _clean(measured) and serves(by):
                self.store.keep(document, before, key, _result(measured), attempt.durable, attempt.since, by)
        return answer

    def _read_at(self, attempt: _Try) -> tuple[dict[str, Any], bytes] | None:
        """The try's document as a checks process reads it (``read``; a file by its path), a model's bytes said
        to be of the try's version, so a process reads them once; None where a build landed as they were read:
        they are of no version asked. ``ValueError`` for a document the engine does not hold."""
        if attempt.ident is None:
            return {"path": str(attempt.spec["path"])}, b""
        source, payload = self._read(attempt.ident)
        if self._version(attempt.ident) != attempt.before:
            return None
        if "document" in source:
            source = {**source, "version": attempt.before}  # its bytes are this version's: read once there
        return source, payload

    def _stood(self, attempt: _Try, measured: dict[str, Any]) -> tuple[bool, bool]:
        """Whether what a checks process answered (``measured``) is of the try's version (``current``), and
        whether the document moved on under it, so nothing of the answer stands (``moved``): a model built
        again; a file rewritten while it was read, which is of no version at all (one rewritten before it was
        read is measured as it is now, and is of another version than the try's)."""
        if attempt.ident is not None:
            current = self._version(attempt.ident) == attempt.before
            return current, not current
        return measured.get("digest") == attempt.before, bool(measured.get("changed"))

    def _measure(self, asked: Asked, document: str, order: dict[str, Any], payload: bytes,
                 told: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """``order`` asked of a checks process leased for ``asked`` (``_leased``) and its answer returned -- or
        the failure of the stop it was in, of its process lost, or of none that could be started."""
        try:
            with self._leased(asked, document, told) as request:
                return request(order, payload)
        except _Ended as ended:
            return ended.answer

    @contextlib.contextmanager
    def _leased(self, asked: Asked, document: str, told: Callable[[dict[str, Any]], None]
                ) -> Iterator[Callable[..., dict[str, Any]]]:
        """A checks process for ``asked``, for as long as the block runs: a slot of the pool taken (waiting for
        one, said once) and its process leased, the check ``MEASURING`` from then on, so every request the
        block sends is one check's to the watchdog and to every stop (its time counted from the first), and
        the process and the slot let go as the block ends, however it does. It gives ``request(order, payload,
        more=False)``: the order asked of that process and its answer; ``more``, the check asks that process
        again after this, and without it the check is ``ANSWERED`` with the answer, which no stop then
        reaches. ``_Ended``, with what its callers are told, from the block's start, a request or its end: the
        failure of the stop the check is in, of its process lost, or of none that could be started."""
        with self.lock:
            if asked.state is not State.ASKED:
                raise _Ended(asked.failure())  # stopped as it read its document
            asked.state = State.WAITING
        try:
            slot = self.pool.take(document, lambda: asked.state is not State.WAITING,
                                  lambda said: told({"log": said, "stream": "waiting"}),
                                  lambda: self.reap(asked), lambda: self._defers(asked))
        except Withdrawn:
            raise _Ended(asked.failure()) from None  # stopped while it waited for a slot
        process: Any = None

        def request(order: dict[str, Any], payload: bytes = b"", more: bool = False) -> dict[str, Any]:
            answer = process.request(order, told, payload)
            with self.lock:
                if asked.state is not State.MEASURING:
                    raise _Ended(asked.failure())  # stopped as it answered: its process is killed, nothing of it kept
                if not more:
                    asked.state = State.ANSWERED
            self.pool.learn(process, answer)
            if "failed" in answer and "kind" not in answer:
                answer = {**answer, "reason": "error"}  # the check itself failed there: its words, nothing measured
            return answer

        try:
            with self.lock:
                if asked.state is not State.WAITING:
                    raise _Ended(asked.failure())  # stopped as it took its slot
                asked.state, asked.slot = State.STARTING, slot
            process = self._lease(slot)
            with self.lock:
                if asked.state is not State.STARTING:
                    raise _Ended(asked.failure())  # stopped as its process started
                asked.state, asked.process, asked.since = State.MEASURING, process, time.time()
                watch = not self.watching
                self.watching = True
            if watch:
                threading.Thread(target=self._watch, name="cad-check-watchdog", daemon=True).start()
            yield request
            with self.lock:
                if asked.state is State.MEASURING:
                    asked.state = State.ANSWERED  # it asks its process no more
                elif asked.state is not State.ANSWERED:
                    raise _Ended(asked.failure())  # stopped between its requests: nothing of them stands
        except Gone as error:
            with self.lock:
                if asked.state not in LIVE:
                    raise _Ended(asked.failure()) from None  # its process killed by the stop it is in
                asked.state = State.ANSWERED
            if self.stopping():
                raise _Ended({"failed": STOPPED, "reason": State.STOPPED.value, "stopped": True}) from None
            if error.during:
                raise _Ended({"failed": _lost(str(error), error.code), "reason": "process_lost"}) from None
            raise _Ended({"failed": str(error), "reason": "no_kernel", **failed_type(error)}) from None  # it never started
        except RuntimeError as error:
            from cad.engine.serve import KernelProcessesUnavailable

            if not isinstance(error, KernelProcessesUnavailable):
                raise
            # No kernel environment to start a checks process in: its line, and its type.
            raise _Ended({"failed": str(error), "reason": "no_kernel", **failed_type(error)}) from None
        finally:
            with self.lock:
                asked.process = None  # before it is let go: no stop reaches a process it no longer has
            if process is not None:
                self._release(process)
            with self.lock:
                asked.slot = None
            self.pool.give(slot)

    # --- stopping -----------------------------------------------------------------------------------

    def _stop(self, asked: Asked, why: State, **said: float) -> bool:
        """``asked`` stopped for ``why`` (call with the lock held), unless it has ended: one waiting leaves the
        pool's queue as it next looks, one measuring has the process its lease holds killed, and its request
        answers that it is gone. Whether it was stopped: one that has ended is left alone."""
        if asked.state not in LIVE:
            return False
        asked.state, asked.why = why, dict(said)
        if asked.process is not None:
            try:
                asked.process.popen.kill()
            except Exception:  # noqa: BLE001 - gone already
                pass
        return True

    def _defers(self, waiter: Asked) -> bool:
        """Whether a check waiting for a slot leaves a free one to another: its callers have all gone, and a
        check someone waits for waits too."""
        if not waiter.abandoned():
            return False
        with self.lock:
            return any(asked.state is State.WAITING and not asked.abandoned() for asked in self.asked.values())

    def reap(self, waiter: Asked) -> None:
        """A check waiting for a slot (``waiter``), its caller there: one check measuring whose callers have
        all gone gives up its process -- killed at once, nothing of it kept, and the pool starts a fresh one for
        the waiter -- one for each such waiter, the oldest first, a cancelled one counted until its slot is free
        again. It leaves ``running`` as it is cancelled, so the same check asked meanwhile runs anew. A check
        someone waits for is never cut short this way."""
        if waiter.abandoned():
            return
        with self.lock:
            waiters = sum(1 for asked in self.asked.values()
                          if asked.state is State.WAITING and not asked.abandoned())
            freeing = sum(1 for asked in self.asked.values()
                          if asked.state is State.CANCELLED and asked.slot is not None)
            victims = [asked for asked in self.asked.values() if asked.state is State.MEASURING and asked.abandoned()]
            if freeing >= waiters or not victims:
                return
            victim = min(victims, key=lambda asked: asked.began)
            self._stop(victim, State.CANCELLED)
            if victim.same is not None and self.running.get(victim.same) is victim:
                self.running.pop(victim.same)

    def built(self, ident: str) -> None:
        """Model document ``ident`` was built, handed over or deleted, as the daemon registers it: each check
        of it asked at another generation than the one it has now is stopped -- one waiting leaves the queue,
        one measuring has its process killed -- and leaves ``running``, so the same check asked from now on is
        of the new generation (``check`` asks it again for the callers still there). A build that kept its
        generation stops nothing, nor does one of another document."""
        try:
            now = self._version(ident)
        except ValueError:
            now = None
        document = f"model:{ident}"
        with self.lock:
            for asked in self.asked.values():
                if asked.same is None or asked.same[0] != document or asked.same[1] == now:
                    continue
                if self._stop(asked, State.SUPERSEDED) and self.running.get(asked.same) is asked:
                    self.running.pop(asked.same)

    def halt(self) -> None:
        """Every check stopped as the engine stops (an update's drain, ``cad stop``): those waiting leave the
        queue, the checks processes measuring are killed, all at once -- they hold nothing of anyone's, so nothing
        is waited for -- and their callers are told to run the check again (``api.Stopped``)."""
        with self.lock:
            for asked in self.asked.values():
                self._stop(asked, State.STOPPED)

    def _watch(self) -> None:
        """The watchdog, alive while a check measures: each one past a check's time limit, or whose process
        holds more than a check's memory limit (read from outside the process, so one inside a kernel call that
        never returns is seen all the same), is stopped. What it read is the process's memory as the supervisor
        counts it (``Process.rss``) from then on, so the engine's memory rule and the pool's room go by what a
        measuring process holds now, not by what it said after its last check."""
        while True:
            now = time.time()
            with self.lock:
                measuring = [(asked, asked.process.pid, asked.since or now) for asked in self.asked.values()
                             if asked.state is State.MEASURING and asked.process is not None]
                if not measuring:
                    self.watching = False
                    return
            seconds, memory = self.limits.seconds, self.limits.memory()
            for asked, pid, since in measuring:
                resident = self.resident(pid) if memory is not None else None
                with self.lock:
                    if resident is not None and asked.state is State.MEASURING:
                        asked.process.rss = resident
                    if seconds is not None and now - since > seconds:
                        self._stop(asked, State.OVER_TIME, seconds=now - since, limit=seconds)
                    elif memory is not None and resident is not None and resident > memory:
                        self._stop(asked, State.OVER_MEMORY, resident=resident, limit=memory)
            time.sleep(WATCH_SECONDS)

    # --- what it holds ------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """What ``status`` says of the checks: the store's counts, how many are asked, the pool, a check's
        limits, and each check asked and not ended (``running``): what, of which document or file, where (its
        checks process; None while it waits for one), since when, whether a caller still waits for it and how
        many do (a caller gone never counted)."""
        now = time.time()
        with self.lock:
            rows = [{**asked.what, "state": asked.state.value,
                     "where": getattr(asked.process, "key", None), "since": asked.began,
                     "seconds": round(now - asked.began, 1), "attached": not asked.abandoned(),
                     "callers": asked.there(), "waiting": asked.process is None}
                    for asked in sorted(self.asked.values(), key=lambda asked: asked.began)]
        return {**_counts(self.store.status(), self.measurements.status()), "asked": len(rows),
                "pool": self.pool.status(), "limits": self.limits.status(), "running": rows}


# The check that is no manufacturing process's but runs as one does (``cad._internal.interference``): which parts of
# the document share volume, measured by ``cad.build123d._interference`` in a checks process.
INTERFERENCE = "interference"


def _refusal(request: dict[str, Any]) -> str | None:
    """Why a check's request is none the engine measures, in one line, or None: it names a document the engine
    holds or a file, and a check of a B-rep type for a process it has (or the interference check,
    ``INTERFERENCE``), its options resolved."""
    from cad._internal.dfm import PROCESSES

    spec, check = request.get("source"), request.get("check")
    if not isinstance(spec, dict) or not ("id" in spec or "path" in spec):
        return "a check reads a document the engine holds, or a STEP's or an xbf's file"
    if not isinstance(check, dict) or check.get("type") not in ("model", "step", "xbf"):
        return "the engine measures a manufacturing check of a model, a STEP or an xbf"
    process = check.get("process")
    if process is None:
        return None if isinstance(check.get("given", {}), dict) else "a check's given options are a table"
    if process not in PROCESSES and process != INTERFERENCE:
        return f"a check's process is {', '.join(PROCESSES[:-1])} or {PROCESSES[-1]}, not {process!r}"
    return None if isinstance(check.get("resolved"), dict) else "a check's resolved options are a table"


def _refused(error: Exception) -> dict[str, Any]:
    """A refusal as the daemon answers one (``daemon.refused``)."""
    from cad_server.engine.daemon import refused

    return refused(error)


def _lost(said: str, code: int | None) -> str:
    """A checks process that exited while it measured a check, said as such: what went with it, and, for one
    the system killed, why it usually does."""
    head, tail, detail = said.partition(WORKER_STDERR)
    killed = getattr(signal, "SIGKILL", None)
    why = (": killed by the system, usually for memory -- the part may be too large to check on this machine"
           if killed is not None and code == -int(killed) else "")
    return f"{head}{why}. The check is not run again; the next check starts a fresh process{tail}{detail}"


def file_key(path: str) -> str:
    """A file as the checks key it: by its device and inode where the system gives one, so every name of one
    file -- a hard link, another spelling of its case -- is one key; else by its real path, its case folded where
    its file system folds it (asked of the system, never assumed)."""
    real = os.path.normcase(os.path.realpath(path))
    try:
        found = os.stat(real)
    except OSError:
        return f"file:{real}"
    if found.st_ino:
        return f"file:{found.st_dev}:{found.st_ino}"
    folder, name = os.path.split(real)
    other = os.path.join(folder, name.swapcase())
    try:
        folds = other != real and os.path.samefile(real, other)
    except OSError:
        folds = False  # no file by the other spelling: a file system that tells case apart
    return f"file:{real.casefold() if folds else real}"


def _result(checked: dict[str, Any]) -> dict[str, Any]:
    """A check's answer as it is kept and as a caller that waited for it is answered: without what only its
    first caller is told -- whether it read the document, what measured it."""
    return {name: value for name, value in checked.items() if name not in ("read", "measures")}


def _attached(answer: dict[str, Any]) -> dict[str, Any]:
    """What a caller that waited for the same check is answered: that check's answer, its result as reused; its
    failure as it was."""
    done = answer.get("done")
    if not (isinstance(done, dict) and isinstance(done.get("checked"), dict)):
        return answer
    return {"done": {**done, "checked": _result(done["checked"]), "reused": True}}


def _clean(checked: dict[str, Any]) -> bool:
    """Whether an interference check's answer is a result to keep: one fully measured -- never a document that
    did not read, a refusal, or pairs left unmeasured, which the next check goes on from."""
    report = (checked.get("measured") or {}).get("report")
    return isinstance(report, dict) and not report.get("partial") and not report.get("partial_sections")


def _keepable(checked: dict[str, Any]) -> bool:
    """Whether a manufacturing check's answer holds a measurement to keep: a report, with every family
    measured or not -- a family its code cannot measure of those parts it cannot measure the next time either
    -- unless its measurer says it ``transient``: made otherwise the next time (a search that ran out of its
    seconds, a family that ran out of memory, a table of the report that says it is not repeatable), which the
    next check may measure whole. Never a document that did not read, nor one with no part a process makes."""
    measured = checked.get("measured")
    return (isinstance(measured, dict) and isinstance(measured.get("report"), dict)
            and not checked.get("transient"))


def _checked(answer: dict[str, Any]) -> dict[str, Any] | None:
    """What a checks process answered of a check (``done``'s ``checked``), or None: it failed there, or
    measures for another caller than this one."""
    done = answer.get("done")
    checked = done.get("checked") if isinstance(done, dict) else None
    return checked if isinstance(checked, dict) else None


def _digests(measures: dict[str, Any]) -> bool:
    """Whether a caller says the code that measures each manufacturing process in it (``contract.measuring``'s
    ``dfm``), which a kept measurement is found and kept by, and its libraries."""
    from cad._internal.dfm import PROCESSES

    said = measures.get("dfm")
    return (isinstance(said, dict) and isinstance(measures.get("libraries"), dict)
            and all(isinstance(said.get(process), str) for process in PROCESSES))


def _counts(versions: dict[str, Any], content: dict[str, Any]) -> dict[str, Any]:
    """The two stores' counts as one (``checks.Checks``' and ``measurements.Measurements``'): what each holds
    and reused summed, in memory and on disk, with the aliases held and the documents described."""
    found = {**versions, **{name: versions[name] + content[name]
                            for name in ("held", "bytes", "reused", "restored", "read")},
             "aliases": content["aliases"], "described": content["described"]}
    listed = [disk for disk in (versions["disk"], content["disk"]) if disk is not None]
    held = [disk["held"] for disk in listed if disk["held"] is not None]
    found["disk"] = None if not listed else {
        "held": sum(held) if held else None, "bytes": sum(disk["bytes"] for disk in listed),
        **({"aliases": content["disk"]["aliases"]} if content["disk"] is not None else {})}
    return found
