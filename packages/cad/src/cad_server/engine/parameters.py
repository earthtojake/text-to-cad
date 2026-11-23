"""A model's parameters, the daemon's half: the viewer's Save, the one request that changes a script.

A build's report says where each parameter its model's script declares is spelled in the code
(``cad.engine.parameters.rows``: the file, the line, the bytes of the default and the digest of the file
they were found in). The book keeps those rows beside the model's record, in memory alone, while the
worker that recorded them is live (``models.Models.live``): a worker retired, or a build that records
others, and they are gone. The served structure lists the document's parameters through them
(``serve.Server.structure``: writable only where a live worker recorded the bytes of the value the
document holds).

The daemon's ``set`` (``Setting.set``) is what the page's Save reaches (``POST
/api/v1/documents/model/<id>/parameters``, the server's ``set_parameters``): the values checked against the rows
(``parameters.changes``), the script's bytes against the digest and the spans its last run recorded
(``parameters.standing``), and no build of the script under way, in any worker, nor another set of it
(``busy``), the script then the set's alone until it is done: a build asked meanwhile waits for it
(``Setting.building``); then each number spelled by
the library (``parameters.spelled``) and put in place of the one there (``parameters.splice``), the file
replaced at once (``atomic_replace.put``, its mode kept) only while it still holds the bytes that were
checked (``_write``), and the script's last run built again in the model's warm worker as that run was
asked (``ran``: its script, the models it called, its working folder, its environment and its Python).
The build is judged by what the change can break (``_failure``): a model or child model that failed in
the last run and fails the same way now is the script's own trouble, not the change's. A build that fails
otherwise puts the previous bytes back the same way -- only where the file still holds the bytes the engine
wrote: a file changed meanwhile is left as it is -- and builds again, so the document and the rows are the
last good ones, and the change is refused (``build_failed``) with the build's own words and what the file
holds now. The engine never reads a script outside a run but here (and in ``preview``, below), asked by a
person or an agent; nothing runs on its own.

``preview`` (``Previewing``) is what the page's Parameters tab asks as a person moves a value, before any Save
(``POST /api/v1/documents/model/<id>/preview``): the model on screen at those values, built in its warm worker
with nothing written. The values are checked as ``set`` checks them and the script's bytes against its last
run's (``standing``); then the worker loads the script with those values in place of the defaults its own
script declares and builds that one model (``cad.engine.build.preview``). The answer is held in the server's
memory for the page that asked (``serve.Server.keep_preview``, under an id of its own,
``<id>~preview-<token>``, which only that page is told) and is nothing else: not the document, its version,
its record, the engine's cache or the worker's last run, which ``set`` builds again. Per document one preview
builds at a time and one waits, the newest: a request that comes while one waits takes its place, and the one
it replaces is answered ``superseded``, never built. A build or a ``set`` of the script comes first: a preview
asked while one runs is refused ``busy``, and one waiting when one begins is answered ``busy``, never run
before it; one already building finishes (a kernel call is not cut short), and the build waits that long for
the worker's lease. A page holds two previews at most (the one shown and the next), the server sixteen; a
page's are dropped by its next answer, by values equal to the document's (Reset, a Save that landed), by a new
version of the document, and once nobody has read them for ``PREVIEW_IDLE`` seconds.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import stat
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterator

from cad.engine import parameters as declared
from cad.engine.parameters import ParameterRefused

__all__ = ["LAST_RUN", "PREVIEW_IDLE", "Changed", "Previewing", "Setting", "ran"]

# Where a worker keeps the run its last build was part of (``Process.state``): what ``set`` builds again.
LAST_RUN = "last_run"
# What of a build's order the run it was part of is built again with: the script, its working folder, its
# environment, its Python and the program that asked (``Daemon._handle``'s ``build``).
_KEPT = ("script", "cwd", "env", "interpreter", "program")


def _rows(answer: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Each model a build's answer reports, then each child model it called."""
    for report in answer.get("done") or []:
        if isinstance(report, dict):
            yield report
            yield from (row for row in (report.get("child_models") or {}).values() if isinstance(row, dict))


def _model(row: dict[str, Any]) -> str:
    """What a model's report is known by from one build of its script to the next: its id, else its name."""
    return str(row.get("id") or row.get("model") or "")


def _error(row: dict[str, Any]) -> str:
    """A failed model's error, in its own words."""
    return str(row.get("error") or f"{row.get('model') or 'a model'} failed")


def ran(worker: Any, request: dict[str, Any], answer: dict[str, Any] | None = None) -> None:
    """A build ``worker`` ran for ``request``: kept as the run its parameters are set by building again. A
    run's builds share its token (``api._run``), each naming the models it called (``functions``; none: every
    model the script defines), so the run kept is the last one, with every model any of its builds named, and
    how each model of it last ended (``failed``: each model that failed, by ``_model``, the last line of its
    error), which ``_failure`` judges a set's build against."""
    run = request.get("run")
    last = worker.state.get(LAST_RUN)
    if last is None or run is None or last.get("run") != run:
        last = {"run": run, "request": {key: request[key] for key in _KEPT if key in request}, "functions": [],
                "failed": {}}
    functions = request.get("functions")
    if functions is None or last["functions"] is None:
        last["functions"] = None
    else:
        last["functions"] += [name for name in functions if isinstance(name, str) and name not in last["functions"]]
    failed = last.setdefault("failed", {})
    for row in _rows(answer or {}):
        if row.get("ok"):
            failed.pop(_model(row), None)
        else:
            failed[_model(row)] = _last_line(_error(row))
    worker.state[LAST_RUN] = last


def _failure(answer: dict[str, Any], before: dict[str, str] | None = None) -> str | None:
    """Why a set's build failed, in its own words (a model's error, the worker's), or None: every model it
    built, and every child model each called, built -- but one that failed in the run built again
    (``before``: ``ran``'s ``failed``) and fails the same way now (the last line of its error), which the
    change did not break. A model that built then and fails now, or fails otherwise, is the change's."""
    if "failed" in answer:
        return str(answer["failed"])
    before = before or {}
    for row in _rows(answer):
        if not row.get("ok") and before.get(_model(row)) != _last_line(_error(row)):
            return _error(row)
    return None


def _rebuilt(answer: dict[str, Any]) -> list[str]:
    """The ids of the documents a build made: each model's, then each child model's, once each."""
    found: list[str] = []
    for row in _rows(answer):
        if row.get("ok") and row.get("id") and row["id"] not in found:
            found.append(str(row["id"]))
    return found


class Changed(Exception):
    """The file ``_write`` was to replace no longer holds the bytes it was told it holds: another writer's."""


def _write(path: Path, data: bytes, holds: bytes) -> None:
    """``path`` holding ``data``, replaced at once (``atomic_replace.put``) with the mode it had -- only while it
    holds ``holds``, read again once the new file is made, just before it is moved over: ``Changed``, and the file
    left as it is, where another writer changed it since. (Nothing locks a file another program writes: the
    window is the rename's alone.)"""
    from cad.engine.atomic_replace import put

    mode = stat.S_IMODE(os.stat(path).st_mode)

    def write(temporary: Path) -> None:
        temporary.write_bytes(data)
        os.chmod(temporary, mode)
        try:
            now = path.read_bytes()
        except OSError:  # gone, or no longer readable: not the file that was checked
            now = None
        if now != holds:
            raise Changed(str(path))

    put(path, write, compare=False)


def _last_line(text: str) -> str:
    """A build's error as one line: the last line of its traceback, which says the error and its words."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else "the build failed"


class Setting:
    """The daemon's ``set``, and the one turn every build and set of a script takes (``building``, ``_claim``):
    ``builds``, per script (its canonical path, a worker's label), the builds of it from request to answer;
    ``claims``, per script, the thread of the set writing it or building it again. A set claims its scripts
    only where none of them is building or claimed (else ``busy``), and a build of a claimed script waits
    until the set is done, but the set's own, from the thread that claimed it: so no set writes a file a
    build is reading, and no build starts between a set's check of the bytes and its build of them."""

    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.turn = threading.Condition()
        self.builds: dict[str, int] = {}
        self.claims: dict[str, int] = {}

    @contextlib.contextmanager
    def building(self, key: str | None, send: Any = None) -> Iterator[None]:
        """A build of the script ``key`` names, from its request to its answer (the daemon's build path): it
        waits while another thread's set claims the script (said once to ``send``, as a build behind another
        is), then counts, so a set of it is refused ``busy`` and a preview of it waiting is answered ``busy``."""
        if not key:
            yield
            return
        me = threading.get_ident()
        with self.turn:
            waits = self.claims.get(key, me) != me
        if waits and send is not None:
            send({"log": f"waiting for the parameters of {Path(key).name} to be set", "stream": "waiting"})
        with self.turn:
            while self.claims.get(key, me) != me:
                self.turn.wait()
            self.builds[key] = self.builds.get(key, 0) + 1
        previewing = getattr(self.daemon, "previewing", None)
        if previewing is not None:
            previewing.yield_to(key)
        try:
            yield
        finally:
            with self.turn:
                left = self.builds.get(key, 1) - 1
                if left > 0:
                    self.builds[key] = left
                else:
                    self.builds.pop(key, None)
                self.turn.notify_all()

    def under_way(self, *keys: str | None) -> bool:
        """Whether a build or a set of any of the scripts ``keys`` names is under way."""
        with self.turn:
            return any(key and (self.builds.get(key) or key in self.claims) for key in keys)

    def _claim(self, keys: set[str], worker: Any) -> bool:
        """``keys`` claimed for this thread's set, at once and only where none is building or claimed (nor the
        worker building, whatever asked it)."""
        with self.turn:
            if any(self.builds.get(key) or key in self.claims for key in keys) or (
                    getattr(worker, "leased", False) and getattr(worker, "op", None) == "build"):
                return False
            for key in keys:
                self.claims[key] = threading.get_ident()
            return True

    def _unclaim(self, keys: set[str]) -> None:
        with self.turn:
            for key in keys:
                self.claims.pop(key, None)
            self.turn.notify_all()

    def set(self, ident: str, values: Any) -> dict[str, Any]:  # noqa: A003 - the operation's own name
        """Model document ``ident``'s parameters set to ``values`` (``{name: number}``): the steps of the
        module's docstring, answered ``{"id", "written", "rebuilt"}``. ``ParameterRefused`` before anything is
        written; ``serve.NotHeld`` for a document the engine does not hold."""
        from cad.engine.ids import canonical

        if not isinstance(values, dict) or not all(isinstance(name, str) for name in values):
            raise ValueError('a change of parameters is {"values": {name: number, ...}}')
        models = self.daemon.models
        live = models.live(ident)
        if live is None:
            if models.held(ident) is None:
                raise models.not_held(ident)
            name = (models.row(ident) or {}).get("source", {}).get("name") or ident
            raise ParameterRefused(f"{name} ({ident}) has no live worker that recorded where its parameters are in "
                                   "the code", "no_worker", "run the model's script again, then set its parameters")
        found = declared.changes(live["rows"], values)
        if not found:
            return {"id": ident, "written": [], "rebuilt": []}
        worker, name = live["worker"], live["name"]
        last = worker.state.get(LAST_RUN)
        if not isinstance(last, dict) or not last.get("request", {}).get("script"):
            raise ParameterRefused(f"{name} ({ident}) has no run its worker can build again", "no_worker",
                                   "run the model's script again, then set its parameters")
        script = Path(str(found[0][0]["file"]))
        # The file written, and the script whose run is built again (a child model's may be another's): a build
        # of either, in any worker (another Python's is another worker), or a set of either, comes first.
        keys = {canonical(script), canonical(str(last["request"]["script"]))}
        if getattr(worker, "label", None):
            keys.add(str(worker.label))
        if not self._claim(keys, worker):
            raise ParameterRefused(f"{script.name} is building now", "busy", "set its parameters once its build is done")
        try:
            self._first(keys)
            return self._written(ident, name, script, found, last)
        finally:
            self._unclaim(keys)

    def _first(self, keys: set[str]) -> None:
        """A set begins: a preview of its scripts waiting to build is answered ``busy`` (``Previewing``)."""
        previewing = getattr(self.daemon, "previewing", None)
        if previewing is not None:
            for key in keys:
                previewing.yield_to(key)

    def _written(self, ident: str, name: str, script: Path, found: list, last: dict[str, Any]) -> dict[str, Any]:
        try:
            data = script.read_bytes()
        except OSError as error:
            raise ParameterRefused(f"{script} cannot be read ({error.strerror or error}): the engine knows where "
                                   "the parameters were, not where they are", "script_changed",
                                   "run the script first, then set the parameters") from None
        declared.standing(data, [row for row, _value in found], script.name)
        made = declared.splice(data, [(row["span"][0], row["span"][1], declared.spelled(value, row["kind"]))
                                      for row, value in found])
        try:
            _write(script, made, data)
        except Changed:
            raise ParameterRefused(f"{script.name} changed while its parameters were being set: nothing was written",
                                   "script_changed", "run the script first, then set the parameters") from None
        before = dict(last.get("failed") or {})  # how the run built again last ended: what the change cannot break
        answer = self._built(last)
        failure = _failure(answer, before)
        if failure is not None:
            raise self._put_back(name, script, data, made, last, failure)
        return {"id": ident,
                "written": [{"name": row["name"], "from": row["value"], "to": value, "file": row["file"],
                             "line": row["line"]} for row, value in found],
                "rebuilt": _rebuilt(answer)}

    def _put_back(self, name: str, script: Path, data: bytes, made: bytes, last: dict[str, Any],
                  failure: str) -> ParameterRefused:
        """A build at the new values that failed: the bytes the last good run read put back and that run built
        again (its document and its rows), where the file still holds the bytes the engine wrote; else the file
        is left as it is. The refusal (``build_failed``) says the build's last line and what the file holds."""
        try:
            _write(script, data, made)
        except Changed:
            held = (f"{script} changed while it built, so the engine did not put it back: it holds that change, "
                    "neither the bytes it had nor only the new values")
        except OSError as error:
            held = (f"{script} could not be put back ({error.strerror or error}): it holds the new values, which "
                    "failed to build")
        else:
            self._built(last)
            held = f"{script.name} is as it was"
        refused = ParameterRefused(f"{name}: its build at the new values failed, and {held}: {_last_line(failure)}",
                                   "build_failed", "fix the model's code for those values, or set others")
        refused.detail = failure  # type: ignore[attr-defined]  # the build's whole words
        return refused

    def _built(self, last: dict[str, Any]) -> dict[str, Any]:
        """The script's last run built again, in its worker, as it was asked: a build order of its own run,
        through the daemon's one build path, so its pages see the new version as a run's do."""
        order = {"op": "build", **last["request"], "functions": last["functions"],
                 "run": f"set:{secrets.token_hex(8)}"}
        replies: list[dict[str, Any]] = []
        self.daemon.handle(order, replies.append)
        return next((reply for reply in reversed(replies) if "done" in reply or "failed" in reply),
                    {"failed": "the build gave no answer"})


# How long a preview is held with nothing reading it, in seconds: a page that closed without dropping its own.
PREVIEW_IDLE = 120.0
# The previews held per page (the one on screen and the next) and pages held at once, the least recent dropped.
PREVIEWS_PER_PAGE = 2
PAGES_HELD = 8
# A page names itself with a token of its own making: what keeps one page's previews from another's.
_PAGE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class _Ticket:
    """One preview asked: its document, the worker's label its script is built by, and how it ended while it
    waited (``outcome``: ``go``, ``superseded`` or a refusal), told by ``event``."""

    def __init__(self, ident: str, label: str | None) -> None:
        self.ident, self.label = ident, label
        self.event = threading.Event()
        self.outcome: Any = None


class Previewing:
    """The daemon's ``preview``: the steps of the module's docstring. ``slots``: per document id, the ticket
    building and the one waiting (a build or a set of the script under way is ``Setting``'s turn to say);
    ``pages``: by ``(document, page)``, the preview ids that page holds, the newest last."""

    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.lock = threading.Lock()
        self.slots: dict[str, dict[str, _Ticket | None]] = {}
        self.pages: "OrderedDict[tuple[str, str], list[str]]" = OrderedDict()
        self.made: dict[str, float] = {}  # each preview id held, when it was made

    # --- a real run first ----------------------------------------------------------------------------

    def yield_to(self, label: str | None) -> None:
        """A build or a set of the script ``label`` names begins: each preview of it waiting is answered ``busy``."""
        if not label:
            return
        with self.lock:
            for slot in self.slots.values():
                waiting = slot.get("waiting")
                if waiting is not None and waiting.label == label:
                    slot["waiting"] = None
                    waiting.outcome = _busy("a build of the script came first")
                    waiting.event.set()

    def _busy(self, worker: Any, script: str) -> bool:
        """Whether a build or a set of ``worker``'s script, or of the file the values are in, is under way (the
        setting's turn, ``Setting.building``): it comes first."""
        from cad.engine.ids import canonical

        setting = getattr(self.daemon, "setting", None)
        if setting is not None and setting.under_way(getattr(worker, "label", None), canonical(script)):
            return True
        return bool(getattr(worker, "leased", False) and getattr(worker, "op", None) == "build")

    # --- one preview ---------------------------------------------------------------------------------

    def preview(self, ident: str, values: Any, page: Any) -> dict[str, Any]:
        """Model document ``ident`` at ``values`` (``{name: number}``), for the page ``page`` names: ``{"id",
        "preview": {"id", "version", "basis", "values", "seconds", "memo"}}``; ``{"id", "preview": null}`` where
        the values are the document's (that page's previews dropped, nothing built); ``{"id", "superseded":
        true}`` where a newer request took its place before it built. ``ParameterRefused`` by ``set``'s codes;
        ``serve.NotHeld`` for a document the engine does not hold."""
        if not isinstance(values, dict) or not all(isinstance(name, str) for name in values):
            raise ValueError('a preview is {"values": {name: number, ...}, "page": token}')
        if not isinstance(page, str) or not _PAGE.match(page):
            raise ValueError("a preview names its page by a token of letters, digits, - and _ (at most 64)")
        live, found = self._checked(ident, values)
        if not found:
            self.drop(ident, page)
            return {"id": ident, "preview": None}
        script = str(found[0][0]["file"])
        if self._busy(live["worker"], script):
            raise _busy(f"{Path(script).name} is building now")
        ticket = _Ticket(ident, getattr(live["worker"], "label", None))
        with self.lock:
            slot = self.slots.setdefault(ident, {"running": None, "waiting": None})
            if slot["running"] is None:
                slot["running"] = ticket
            else:
                replaced = slot["waiting"]
                if replaced is not None:
                    replaced.outcome = "superseded"
                    replaced.event.set()
                slot["waiting"] = ticket
        if slot["running"] is not ticket:
            ticket.event.wait()
            if ticket.outcome == "superseded":
                return {"id": ident, "superseded": True}
            if isinstance(ticket.outcome, BaseException):
                raise ticket.outcome
        try:
            return self._built(ident, values, page)
        finally:
            with self.lock:
                following = slot["waiting"]
                slot["waiting"], slot["running"] = None, following
                if following is not None:
                    following.outcome = "go"
                    following.event.set()
                elif self.slots.get(ident) is slot:
                    del self.slots[ident]

    def _checked(self, ident: str, values: dict[str, Any]) -> tuple[dict[str, Any], list]:
        """The model's live rows and what the values change of them (``parameters.changes``), as ``set`` checks
        them: ``no_worker``, ``unknown_parameter``, ``not_writable``, ``not_a_number``, ``out_of_range``."""
        models = self.daemon.models
        live = models.live(ident)
        if live is None:
            if models.held(ident) is None:
                raise models.not_held(ident)
            name = (models.row(ident) or {}).get("source", {}).get("name") or ident
            raise ParameterRefused(f"{name} ({ident}) has no live worker that recorded where its parameters are in "
                                   "the code", "no_worker", "run the model's script again, then change its parameters")
        return live, declared.changes(live["rows"], values)

    def _built(self, ident: str, values: dict[str, Any], page: str) -> dict[str, Any]:
        """The preview built, once it is this document's turn: checked again (a run may have landed while it
        waited), then asked of the model's worker under a lease of its own, and held for ``page``."""
        live, found = self._checked(ident, values)
        if not found:
            self.drop(ident, page)
            return {"id": ident, "preview": None}
        worker, name = live["worker"], live["name"]
        script = Path(str(found[0][0]["file"]))
        if self._busy(worker, str(script)):
            raise _busy(f"{script.name} is building now")
        try:
            data = script.read_bytes()
        except OSError as error:
            raise ParameterRefused(f"{script} cannot be read ({error.strerror or error})", "script_changed",
                                   "run the script first, then change the parameters") from None
        declared.standing(data, [row for row, _value in found], script.name)
        last = (worker.state.get(LAST_RUN) or {}).get("request") or {}
        basis = (self.daemon.models.row(ident) or {}).get("version")
        server = getattr(self.daemon, "server", None)
        known = server.preview_shapes(ident, self.held(ident, page)) if server is not None else {}
        asked = {row["name"]: value for row, value in found}
        order = {"id": 1, "op": "preview", "script": live["script"], "name": name, "values": asked,
                 "digest": found[0][0].get("digest"), "known": sorted(known), "cwd": last.get("cwd"),
                 "env": last.get("env") or getattr(worker, "environment", None) or {}}
        answer = self._asked(worker, order)
        if "failed" in answer:
            refused = ParameterRefused(f"{name}: the preview's build failed: {_last_line(str(answer['failed']))}",
                                       "build_failed", "try other values, or run the script again")
            refused.detail = str(answer["failed"])  # type: ignore[attr-defined]
            raise refused
        done = answer.get("done") or {}
        if not done.get("ok"):
            if done.get("code"):
                raise ParameterRefused(str(done.get("error")), str(done["code"]), done.get("hint"))
            refused = ParameterRefused(f"{name} does not build at these values: {_last_line(str(done.get('error')))}",
                                       "build_failed", "try other values, or fix the model's code for these")
            refused.detail = str(done.get("error"))  # type: ignore[attr-defined]
            raise refused
        payload = answer.get("payload") or b""
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + int(size)]
            at += int(size)
        for prototype in done["structure"].get("prototypes") or []:
            key = prototype.get("key")
            if key not in shapes and key in known:
                shapes[key] = known[key]
        token = secrets.token_hex(8)
        held = f"{ident}~preview-{token}"
        structure = {**done["structure"], "path": held, "id": held, "version": token,
                     "preview": {"of": ident, "basis": basis, "values": asked}}
        if server is not None:
            server.keep_preview(held, structure, shapes)
        self._hold(ident, page, held)
        return {"id": ident, "preview": {"id": held, "version": token, "basis": basis, "values": asked,
                                         "seconds": (done.get("timings") or {}).get("total"), "memo": done.get("memo")}}

    def _asked(self, worker: Any, order: dict[str, Any]) -> dict[str, Any]:
        """``order`` asked of ``worker`` itself, under a lease (a worker answers one request at a time, and a
        build waits for the lease): one that is no longer the live process of its script holds neither the
        rows nor the memo of its last run: ``no_worker``."""
        daemon = self.daemon
        python_key = getattr(worker, "python_key", None)
        gone = ParameterRefused("the model's worker is gone", "no_worker",
                                "run the model's script again, then change its parameters")
        if daemon.supervisor.live("worker", worker.label, python_key) is not worker:
            raise gone
        with daemon.busy_lock:
            daemon.busy += 1
        try:
            leased = daemon.lease(worker.label, worker.environment, None,
                                  python=worker.python if python_key else None, python_key=python_key)
            try:
                if leased is not worker:
                    raise gone
                return leased.request(order, lambda _message: None)
            finally:
                daemon.release(leased)
        except ParameterRefused:
            raise
        except Exception as error:  # noqa: BLE001 - the worker gone mid-request, a kernel environment missing
            return {"failed": f"{type(error).__name__}: {error}"}
        finally:
            with daemon.busy_lock:
                daemon.busy -= 1
                daemon.worked = time.monotonic()

    # --- what is held ----------------------------------------------------------------------------------

    def held(self, ident: str, page: str) -> list[str]:
        """The preview ids ``page`` holds of document ``ident``, the newest last."""
        with self.lock:
            return list(self.pages.get((ident, page)) or [])

    def _hold(self, ident: str, page: str, held: str) -> None:
        """``held`` kept for ``page``: its older ones beyond ``PREVIEWS_PER_PAGE`` and the least recent pages
        beyond ``PAGES_HELD`` dropped."""
        dropped: list[str] = []
        with self.lock:
            kept = self.pages.pop((ident, page), [])
            kept.append(held)
            self.made[held] = time.monotonic()
            dropped += kept[:-PREVIEWS_PER_PAGE]
            self.pages[(ident, page)] = kept[-PREVIEWS_PER_PAGE:]
            while len(self.pages) > PAGES_HELD:
                _place, older = self.pages.popitem(last=False)
                dropped += older
            for gone in dropped:
                self.made.pop(gone, None)
        self._let_go(dropped)

    def drop(self, ident: str, page: str | None = None) -> None:
        """Document ``ident``'s previews dropped: ``page``'s, else every page's (a new version of it)."""
        with self.lock:
            places = [place for place in self.pages if place[0] == ident and (page is None or place[1] == page)]
            dropped = [held for place in places for held in self.pages.pop(place)]
            for gone in dropped:
                self.made.pop(gone, None)
        self._let_go(dropped)

    def expire(self, now: float | None = None) -> None:
        """Previews no page has read for ``PREVIEW_IDLE`` seconds dropped (the daemon's ``tend``)."""
        now = time.monotonic() if now is None else now
        server = getattr(self.daemon, "server", None)
        with self.lock:
            stale = {held for held, made in self.made.items()
                     if now - max(made, server.preview_read(held) if server is not None else 0.0) > PREVIEW_IDLE}
            for place in list(self.pages):
                kept = [held for held in self.pages[place] if held not in stale]
                if kept:
                    self.pages[place] = kept
                else:
                    del self.pages[place]
            for gone in stale:
                self.made.pop(gone, None)
        self._let_go(sorted(stale))

    def _let_go(self, dropped: list[str]) -> None:
        server = getattr(self.daemon, "server", None)
        if dropped and server is not None:
            server.drop_previews(dropped)


def _busy(text: str) -> ParameterRefused:
    """A preview refused because a build or a set of its script comes first."""
    return ParameterRefused(text, "busy", "change the value again once the build is done")
