"""A model's parameters, the daemon's half: the one operation that changes a script (``set``).

A build's report says where each parameter its model's script declares is spelled in the code
(``cad.engine.parameters.rows``: the file, the line, the bytes of the default and the digest of the file
they were found in). The book keeps those rows beside the model's record, in memory alone, while the
worker that recorded them is live (``models.Models.live``): a worker retired, or a build that records
others, and they are gone. The served structure lists the document's parameters through them
(``serve.Server.structure``: writable only where a live worker recorded the bytes of the value the
document holds).

``set`` is what ``cad model set``, ``cad.model.set`` and the page's Save (``POST
/api/v1/documents/model/<id>/parameters``) reach, one code path: the values checked against the rows
(``parameters.changes``), the script's bytes against the digest and the spans its last run recorded
(``parameters.standing``), and no build of the script running (``busy``); then each number spelled by
the library (``parameters.spelled``) and put in place of the one there (``parameters.splice``), the file
replaced at once (``atomic_replace.put``, its mode kept), and the script's last run built again in the
model's warm worker as that run was asked (``ran``: its script, the models it called, its working
folder, its environment and its Python). A build that fails puts the previous bytes back the same way and
builds again, so the document and the rows are the last good ones, and the change is refused
(``build_failed``) with the build's own words. The engine never reads a script outside a run but here,
asked by a person or an agent; nothing runs on its own.
"""

from __future__ import annotations

import os
import secrets
import stat
import threading
from pathlib import Path
from typing import Any

from cad.engine import parameters as declared
from cad.engine.parameters import ParameterRefused

__all__ = ["LAST_RUN", "Setting", "ran"]

# Where a worker keeps the run its last build was part of (``Process.state``): what ``set`` builds again.
LAST_RUN = "last_run"
# What of a build's order the run it was part of is built again with: the script, its working folder, its
# environment, its Python and the program that asked (``Daemon._handle``'s ``build``).
_KEPT = ("script", "cwd", "env", "interpreter", "program")


def ran(worker: Any, request: dict[str, Any]) -> None:
    """A build ``worker`` ran for ``request``: kept as the run its parameters are set by building again. A
    run's builds share its token (``api._run``), each naming the models it called (``functions``; none: every
    model the script defines), so the run kept is the last one, with every model any of its builds named."""
    run = request.get("run")
    last = worker.state.get(LAST_RUN)
    if last is None or run is None or last.get("run") != run:
        last = {"run": run, "request": {key: request[key] for key in _KEPT if key in request}, "functions": []}
    functions = request.get("functions")
    if functions is None or last["functions"] is None:
        last["functions"] = None
    else:
        last["functions"] += [name for name in functions if isinstance(name, str) and name not in last["functions"]]
    worker.state[LAST_RUN] = last


def _failure(answer: dict[str, Any]) -> str | None:
    """Why a build's answer failed, in its own words (a model's error, the worker's), or None: every model
    it built, and every child model each called, built."""
    if "failed" in answer:
        return str(answer["failed"])
    for report in answer.get("done") or []:
        if not isinstance(report, dict):
            continue
        for row in [report, *(report.get("child_models") or {}).values()]:
            if not row.get("ok"):
                return str(row.get("error") or f"{row.get('model') or 'a model'} failed")
    return None


def _rebuilt(answer: dict[str, Any]) -> list[str]:
    """The ids of the documents a build made: each model's, then each child model's, once each."""
    found: list[str] = []
    for report in answer.get("done") or []:
        if not isinstance(report, dict):
            continue
        for row in [report, *(report.get("child_models") or {}).values()]:
            if row.get("ok") and row.get("id") and row["id"] not in found:
                found.append(str(row["id"]))
    return found


def _write(path: Path, data: bytes) -> None:
    """``path`` holding ``data``, replaced at once (``atomic_replace.put``) with the mode it had."""
    from cad.engine.atomic_replace import put

    mode = stat.S_IMODE(os.stat(path).st_mode)

    def write(temporary: Path) -> None:
        temporary.write_bytes(data)
        os.chmod(temporary, mode)

    put(path, write, compare=False)


def _last_line(text: str) -> str:
    """A build's error as one line: the last line of its traceback, which says the error and its words."""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else "the build failed"


class Setting:
    """The daemon's ``set``, one script at a time (``scripts``: the scripts a set is writing or building)."""

    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.lock = threading.Lock()
        self.scripts: set[str] = set()

    def set(self, ident: str, values: Any) -> dict[str, Any]:  # noqa: A003 - the operation's own name
        """Model document ``ident``'s parameters set to ``values`` (``{name: number}``): the steps of the
        module's docstring, answered ``{"id", "written", "rebuilt"}``. ``ParameterRefused`` before anything is
        written; ``serve.NotHeld`` for a document the engine does not hold."""
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
        key = os.path.normcase(str(script))
        with self.lock:
            building = key in self.scripts or (worker.leased and worker.op == "build")
            if not building:
                self.scripts.add(key)
        if building:
            raise ParameterRefused(f"{script.name} is building now", "busy", "set its parameters once its build is done")
        try:
            return self._written(ident, name, script, found, last)
        finally:
            with self.lock:
                self.scripts.discard(key)

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
        _write(script, made)
        answer = self._built(last)
        failure = _failure(answer)
        if failure is not None:
            # The bytes the last good run read, put back, and that run built again: its document and its rows.
            _write(script, data)
            self._built(last)
            refused = ParameterRefused(f"{name}: its build at the new values failed, and {script.name} is as it was: "
                                       f"{_last_line(failure)}", "build_failed",
                                       "fix the model's code for those values, or set others")
            refused.detail = failure  # type: ignore[attr-defined]  # the build's whole words
            raise refused
        return {"id": ident,
                "written": [{"name": row["name"], "from": row["value"], "to": value, "file": row["file"],
                             "line": row["line"]} for row, value in found],
                "rebuilt": _rebuilt(answer)}

    def _built(self, last: dict[str, Any]) -> dict[str, Any]:
        """The script's last run built again, in its worker, as it was asked: a build order of its own run,
        through the daemon's one build path, so its pages see the new version as a run's do."""
        order = {"op": "build", **last["request"], "functions": last["functions"],
                 "run": f"set:{secrets.token_hex(8)}"}
        replies: list[dict[str, Any]] = []
        self.daemon.handle(order, replies.append)
        return next((reply for reply in reversed(replies) if "done" in reply or "failed" in reply),
                    {"failed": "the build gave no answer"})
