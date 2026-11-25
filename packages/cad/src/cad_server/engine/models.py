"""The daemon's book of the model documents a live worker holds, each by its id: its ``.xbf``'s
(``ids.file_id``).

A model's document is its ``.xbf``: every run writes it (law 10), and the engine's live build is what makes
the page live while a worker holds it. Only metadata lives here: a document's structure and shape bytes are
the server's (``serve.Server``), asked of the worker that built it (``load``); registration never meshes or
materializes an unviewed model. A worker retired (``drain``) or gone (``prune``) takes its rows with it, and
its documents are their files from then on: the server reads each ``.xbf`` as it reads any file (``release``),
and so does a verb by its id (``file_of``). A document whose file is gone is never built here: whoever asks
for it is told the command that builds it again (``missing``), and the engine runs nothing. The book is
process memory. So are the rows a build's report gives of its model's parameters -- where each is spelled in
the code -- which the book keeps beside the record while the worker that recorded them is live (``live``),
and never writes or sends on (``parameters``).

What outlives the process is the registry's (``registry``): each ``model`` and ``shape`` document is recorded
at its ``.xbf``'s id as it is registered (``record``, ``hand_over``), synchronously, with the file's version as
written (``version``), so after a restart its id is known -- its file, or ``unsaved`` with the command that
builds it again (none for a shape) when the file is gone, or ``detached`` once its script is gone too -- and a
run takes the model from its file while the file is that version (``build._written_by_engine``). A record from
before a model's id was its file's is carried to it (``identity.carry``). A served document's generation
(``version``, what a page shows and the viewer's export compares) is a token of its build's own, never a counter
that starts again, so an id and a generation never name two documents across a restart; a run of the same
closure in the worker holding the last build keeps it (nothing ran, nothing changed: no page fetches it again);
its record's ``revision`` is its build closure's key (``revision``), with the parameters its document records
where it records any, the same for the same code and the same record, so a build that changed nothing rewrites
no record, and one whose script declares other values -- which its closure need not reach: a sibling model's
parameter -- is a new revision.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

# A document's states, as ``cad status`` lists them (``state``).
STATES = ("live", "held", "building", "failed", "unsaved", "detached")


def unsaved(name: str, ident: str, command: str | None, shown: str | None = None) -> str:
    """Why a model document is ``unsaved`` -- held by no worker, its ``.xbf`` gone (deleted or moved by hand, or
    never written) -- in the words every surface says: with the command that builds it again, or, for a shape
    handed over (``shown``, the words its record keeps), the program that handed it over."""
    said = f"{name} ({ident}) is not saved: its .xbf is gone"
    if command is None:
        return said + f", and it is {shown}; run that program again to hand it over again"
    return said + f"; run `{command}` to build it again"


def delete(held: Any, ident: str, book: "Models | None" = None) -> dict[str, Any] | None:
    """Delete document ``ident``: the one deletion, which ``cad delete`` and the home's Delete both
    are. What the engine holds of it goes first, where an engine runs (``book``: ``Models.forget``),
    then its record and what the engine's cache derived of it (``held``, the registry:
    ``Registry.delete``). Never a file of the person's: a model's script, its ``.xbf`` and its other declared
    files, and a file a page opened, stay where they are. What was deleted, ``{"id", "name", "kind"}``, or None for
    an id nothing records or holds."""
    record = held.get(ident) if held is not None else None
    row = book.forget(ident) if book is not None else None
    if held is not None:
        held.delete(ident)
    if record is not None:
        name = record.get("entry") or os.path.basename(str(record.get("home") or "")) or ident
        return {"id": ident, "name": name, "kind": record.get("kind")}
    if row is not None:
        return {"id": ident, "name": row["source"]["name"], "kind": row["kind"]}
    return None


def _given(given: list[str], header: dict[str, Any], script: Any) -> list[str]:
    """The requirements a model's record says ``cad run --with`` again (its ``with``): those ``--with`` gave
    its run, and those the inline metadata of the script ``cad run`` ran named (``header``) but where that
    script is the model's own, whose header ``cad run`` reads again -- a check script's are not."""
    named = [item for item in header.get("with") or [] if isinstance(item, str)]
    theirs = header.get("script")
    if not named or not isinstance(theirs, str) or not isinstance(script, str):
        return list(given)

    def same(path: str) -> str:
        return os.path.normcase(os.path.realpath(path))

    return list(given) if same(theirs) == same(script) else sorted(set(given) | set(named))


def _saving(path: Any) -> Path | None:
    """The ``.xbf`` a shape handed over is saved as (``hand_over``'s ``saved``), canonical; None for none."""
    if not isinstance(path, str) or not path.lower().endswith(".xbf") or not os.path.isabs(path):
        return None
    from cad.engine.ids import canonical

    try:
        return Path(canonical(path))
    except (OSError, ValueError):
        return None


def _xbf(report: dict[str, Any]) -> str | None:
    """The ``.xbf`` a model's build wrote or kept (its source's, else its report's ``files``): its document."""
    named = (report.get("source") or {}).get("xbf")
    if isinstance(named, str):
        return named
    return next((path for path, row in (report.get("files") or {}).items()
                 if isinstance(path, str) and isinstance(row, dict) and row.get("kind") == "xbf"), None)


def revision(report: dict[str, Any], parameters: Any = None) -> str:
    """A model document's recorded revision: its closure's key (the same code, the same revision, in
    any process), else a token of this build's own (``durable``: false). A document that records parameters
    (``parameters``: the report's rows, ``cad.engine.parameters.rows``) is that key with its record
    (``parameters.record``), digested: a model whose key a parameter does not reach -- one its body never
    reads -- holds the record all the same, so a record changed is a new revision and a new generation. A document with none keeps its key alone, as before parameters were recorded."""
    key = (report.get("closure") or {}).get("key")
    if not key:
        return f"{_TOKEN}{secrets.token_hex(8)}"
    from cad.engine.parameters import record

    recorded = record(parameters) if isinstance(parameters, list) else None
    if recorded is None:
        return str(key)
    return hashlib.sha256(f"{key}\n{recorded}".encode()).hexdigest()


# What starts a revision that is a build's own token (``revision``), never a closure's key (hexadecimal).
_TOKEN = "t"


def durable(recorded: Any) -> bool:
    """Whether a recorded revision outlives the engine: a closure's key, the same in any process, never a
    build's own token (``revision``)."""
    return isinstance(recorded, str) and bool(recorded) and not recorded.startswith(_TOKEN)


class Models:
    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.records: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.identity_lock = threading.RLock()

    def register(self, worker: Any, answer: dict) -> None:
        done = answer.get("done")
        reports = done.get("reports", []) if isinstance(done, dict) else done
        if not isinstance(reports, list):
            return
        program = answer.get("program")
        # How its run was made, which builds its documents again: the Python a run in its own builds with
        # (``Daemon.caller``), or how ``cad run`` named its packages (``given``, ``_given``); neither, the
        # base's, which ``cad run`` reaches.
        python = answer.get("python") if isinstance(answer.get("python"), str) else None
        given = [item for item in answer.get("with") or [] if isinstance(item, str)]
        header = answer.get("header") if isinstance(answer.get("header"), dict) else {}
        for root in reports:
            if not root.get("ok") and root.get("id") and self.held(root["id"]) is not None:
                root["previous"] = True  # the failed run's line says its previous good build is served
            for report in [root, *(root.get("child_models") or {}).values()]:
                ident, source = report.get("id"), report.get("source")
                # Where its parameters are spelled in the code, as the worker that built it recorded them
                # (``cad.engine.parameters.rows``): kept here, in memory alone, while that worker lives (``live``),
                # and never sent on.
                rows = report.pop("parameters", None)
                if not report.get("ok") or not ident or not source:
                    continue
                recorded = revision(report, rows)
                facts, before = self.facts(ident, report, recorded)
                mine = _given(given, header, source.get("script"))
                self.record(report, recorded, facts, python, mine)
                with self.lock:
                    old = self.records.get(ident)
                    # This build's generation. A document is what its last run made: a run of the same
                    # code and inputs (its closure's key) and the same parameters (``revision``) in the worker
                    # that holds the last build made that document again -- nothing ran, or it ran to the same
                    # bytes -- so its generation stands, no page fetches it again and an export of it is still
                    # the one displayed. Anything else is a new generation.
                    same = (old is not None and old.get("worker") is worker and old.get("revision") == recorded
                            and durable(recorded))
                    version = old["version"] if same else secrets.token_hex(8)
                    self.records[ident] = {"id": ident, "source": source, "worker": worker,
                                           "program": program or (old or {}).get("program") or source["script"],
                                           "kind": "model", "python": python, "with": mine,
                                           "builtAt": time.time(), "version": version,
                                           "files": list(report.get("files") or {}), "revision": recorded,
                                           "facts": facts, "parameters": rows if isinstance(rows, list) else None}
                previewing = getattr(self.daemon, "previewing", None)
                if not same and previewing is not None:
                    previewing.drop(ident)  # a page's look at other values of the version before (``parameters``)
                if facts is not None:
                    from cad.engine.delta import delta

                    report["delta"] = delta(facts, before)
                self.daemon.builders[ident] = worker
                server = self.register_page(ident)
                report["url"] = self.url(server, ident)

    def reattach(self, sources: list[dict[str, Any]], pid: int | None = None) -> list[str]:
        """A worker's models with nothing to take up (``build._reattach``: each its ``source``), each
        re-attached to the record of its script moved, or of its id before its id was its ``.xbf``'s
        (``identity.reattach``), before the worker reads its file; what the book holds of an old id is dropped.
        The lines that say what was re-attached."""
        from cad.engine.identity import reattach

        held = self.registry()
        if held is None:
            return []
        lines: list[str] = []
        with self.identity_lock:
            moved = [(old, new) for old, new in reattach(held, sources, log=lines.append) if old != new]
            for old, _new in moved:
                self.forget(old)
        return lines

    def facts(self, ident: str, report: dict[str, Any], recorded: str) -> tuple[dict | None, dict | None]:
        """A build's facts (``delta.facts``) and the last build's, of document ``ident``: the
        worker's, else -- a model taken from its key, nothing built -- the ones its record holds
        for this revision; the last from the book, else the registry (after a restart). None
        where there are none."""
        now = report.pop("facts", None)
        with self.lock:
            row = self.records.get(ident) or {}
        kept, at = row.get("facts"), row.get("revision")
        if kept is None:
            held = self.registry()
            record = held.get(ident) if held is not None else None
            kept, at = (record or {}).get("facts"), (record or {}).get("revision")
        if now is None and at == recorded:
            now = kept
        return now, kept

    def exported(self, answer: dict[str, Any]) -> None:
        """An export's answer (``worker._export``'s files): each .xbf it wrote counted (its document's parts'
        occurrences) on the file's record (``Registry.counted``) with the file's version as it now is: its row says
        Part or Assembly without the file ever being read. An ``.xbf`` exported is a file of its own, another model:
        its own id, its own card. A file with no record is given one, which no list shows until a page opens it
        (``file_record``: no ``opened``)."""
        done = answer.get("done")
        held = self.registry() if isinstance(done, dict) else None
        if held is None:
            return
        from cad.engine.ids import canonical, file_id
        from cad_server.engine.registry import file_version

        for row in done.get("files") or []:
            if not isinstance(row, dict) or row.get("kind") != "xbf" or type(row.get("parts")) is not int:
                continue
            try:
                found = canonical(row["path"])
            except (KeyError, OSError, TypeError, ValueError):
                continue
            version = file_version(found)
            if version is not None:
                held.counted(file_id(found), row["parts"], version, make=found)

    # --- the registry ------------------------------------------------------------------------

    @staticmethod
    def registry() -> Any:
        from cad_server.engine import registry

        return registry.current()

    def record(self, report: dict[str, Any], recorded: str, facts: dict[str, Any] | None = None,
               python: str | None = None, given: list[str] | None = None) -> dict[str, Any]:
        """The registry's record of a document a build made (``registry``), at its ``.xbf``'s id, written when it
        changed; the record it had (``{}``: none). ``python``: the Python a run in its own built it with, which its
        record names (``python``: absent, the base's); ``given``: the requirements ``cad run --with`` was given
        (``with``). What a record of its file there held of a person's use of its card, and the record of its id
        before its id was its file's (``identity.former``), are carried to it, that one dropped (``identity.carry``).
        Nothing with no registry."""
        from cad.engine.identity import carry, former
        from cad.engine.ids import canonical
        from cad_server.engine import registry as registering

        held = self.registry()
        if held is None:
            return {}
        ident, source = report["id"], report["source"]
        script = Path(source["script"])
        old = held.get(ident) or {}
        mine = old.get("kind") == "model" and old.get("home") is not None \
            and registering.home(held, old) == script and old.get("entry") == source["name"]
        root = str(script.parent)
        # What a restart needs of it and no more: what it is (``id``, ``kind``), where its code is (``root``,
        # ``home``, ``entry``: the command that builds it again is ``cad run`` of its home -- or, built in a Python
        # of its own, that Python of its home: ``python``), its file (``saved``) and that file's version as the
        # engine wrote or kept it (``version``: what a run takes it from), the revision the delta compares, when it
        # was built (the home's order) and when it was first built (``created``, the home's Created: kept from the
        # record it had; a record from before the time was kept stays without one). The closure is its document's
        # own (``previous``).
        found: dict[str, Any] = {
            "id": ident, "kind": "model", "root": root, "home": registering.relative(script, root),
            "entry": source["name"], "namespace": root, "name": source.get("explicit_name") or source["name"],
            "revision": recorded, "fingerprint": source.get("fingerprint"), "module": source.get("module"),
            "built": old["built"] if mine and old.get("revision") == recorded and old.get("built") else time.time()}
        if not old:
            found["created"] = found["built"]
        elif "created" in old:
            found["created"] = old["created"]
        if python is not None:
            found["python"] = python  # absent: built in the base, which ``cad run`` reaches
        if given:
            found["with"] = list(given)  # ``cad run --with`` builds it again
        if facts is not None:
            found["facts"] = facts
        path = _xbf(report)
        if path is not None:
            try:
                path = canonical(path)
                found["saved"] = registering.relative(path, root)
                version = registering.file_version(path)
                if version is not None:
                    found["version"] = version
            except (OSError, ValueError):
                pass
        for key in ("opened", "pinned", "preview", "aliases"):  # the home's, kept across builds
            if key in old:
                found[key] = old[key]
        if mine and "relocated" in old and (report.get("cache") or {}).get("used"):
            found["relocated"] = old["relocated"]  # a fresh document has paths at its new home
        before = former({**source, "kind": "model"})
        earlier = held.get(before) if before != ident else None
        if earlier is not None and earlier.get("kind") != "model":
            earlier = None
        found = carry(found, earlier)
        held.put(found)
        if earlier is not None:
            held.delete(before)
            self.forget(before)
        return old

    def hand_over(self, request: dict[str, Any]) -> dict[str, Any]:
        """A shape a program handed over (``api.hand_over``): its document's bytes read through the
        documents worker -- checked, and its parts counted -- then written as its ``.xbf`` (``_save``), recorded at
        that file's id as a ``kind: "shape"``, with the ``program`` that handed it over where there is one: the
        engine did not run it, so nothing builds it again. Its page is its file's, read as any file is. Refused
        (``ValueError``) for bytes that are no document. The answer carries its page."""
        from cad_server.engine import registry as registering
        from cad.engine.identity import carry, former
        from cad.engine.ids import canonical, file_id, is_id

        name, scope = str(request.get("name")), str(request.get("scope"))
        saving = _saving(request.get("saved"))
        if saving is None:
            raise ValueError(f"{name}: a shape handed over is saved as its .xbf, and names its path")
        ident = file_id(saving)
        if str(request.get("id")) != ident or not is_id(ident):
            raise ValueError(f"{request.get('id')!r} is not the id of {saving}")
        data = base64.b64decode(request.get("xbf") or "")
        replies: list[dict[str, Any]] = []
        self.daemon._call({"source": {"document": ident}, "cwd": request.get("cwd")},
                          {"id": 1, "op": "result", "document": True, "name": name}, replies.append, data)
        answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
        if "done" not in answer:
            raise ValueError(f"{name}: the shape handed over is no document: {answer.get('failed')}")
        parts = len(answer["done"]["structure"].get("instances") or [])
        written = self._save(saving, data)
        recorded = "h" + hashlib.blake2b(data, digest_size=16).hexdigest()
        program = request.get("program")
        held = self.registry()
        if held is not None:
            root = scope if os.path.isdir(scope) else str(Path(scope).parent)
            previous = held.get(ident) or {}
            found: dict[str, Any] = {
                "id": ident, "kind": "shape", "root": root,
                "home": registering.relative(scope, root), "entry": name, "namespace": root, "name": name,
                "revision": recorded, "saved": registering.relative(canonical(saving), root),
                # What its document holds at a glance, as a build's facts say it (``delta.facts``): its parts'
                # occurrences, which its row lists (``recents``), counted from the structure in hand.
                "facts": {"parts": parts},
                "built": previous["built"] if previous.get("revision") == recorded and previous.get("built")
                else time.time()}
            if not previous:  # first handed over now; an older record keeps what it has (``record``)
                found["created"] = found["built"]
            elif "created" in previous:
                found["created"] = previous["created"]
            if program:
                found["program"] = registering.relative(program, root)  # what its words name (``shown``)
            version = registering.file_version(saving) if written else None
            if version is not None:
                found["version"] = version
            for key in ("opened", "pinned", "preview", "aliases"):
                if key in previous:
                    found[key] = previous[key]
            before = former({"kind": "shape", "script": scope, "name": name})
            earlier = held.get(before) if before != ident else None
            found = carry(found, earlier if earlier is not None and earlier.get("kind") == "shape" else None)
            held.put(found)
            if earlier is not None and earlier.get("kind") == "shape":
                held.delete(before)
        server = self.daemon.serve({})
        self.forget(ident)  # a model's page at this id before: the file is the document now
        server.remember(saving)
        done: dict[str, Any] = {"id": ident, "url": self.url(server, ident)}
        if written:
            done["saved"] = True
        return {"done": done}

    @staticmethod
    def _save(found: Path, data: bytes) -> bool:
        """A shape handed over is saved as its ``.xbf`` (``api.hand_over``: law 10), which the engine writes, as a
        build's own ``.xbf`` is, only where it differs or is missing. Whether it was written or kept: a folder that
        refuses it is the caller's to write, which says why (``hand_over``'s answer has no ``saved``)."""
        from cad.engine.atomic_replace import put

        try:
            found.parent.mkdir(parents=True, exist_ok=True)
            put(found, lambda temporary: temporary.write_bytes(data), compare=True)
        except OSError:
            return False
        return True

    @staticmethod
    def shown(program: str | None) -> str:
        """What a shape's record says of where it came from: the program, which the engine did not run."""
        return (f"a shape handed over by {program}, a program the engine did not run: no script to rerun, and no "
                "command builds it again" if program else "a shape handed over from a Python session the engine did "
                "not run: no script to rerun, and no command builds it again")

    @staticmethod
    def url(server: Any, ident: str) -> str:
        """The page of document ``ident`` on ``server``: ``/<id>``, with the link that lets it in (the same text every
        build, until the token is rotated)."""
        app = getattr(server.http, "app", None)
        return f"{server.url}/{ident}" + (f"?token={app.link()}" if app is not None else "")

    def register_page(self, ident: str) -> Any:
        server = self.daemon.serve({})
        with self.lock:
            record = self.records[ident]
            record["opened"] = True
            version, name = record["version"], record["source"]["name"]
        server.register_model(ident, name, lambda: self.load(ident), version)
        return server

    def paths(self, worker: Any, model: str | None = None) -> list[str]:
        """The ids of the documents ``worker`` holds (of model ``model``'s name, when given)."""
        name = model.rsplit("::", 1)[-1] if model else None
        with self.lock:
            return [ident for ident, row in self.records.items() if row["worker"] is worker
                    and (name is None or row["source"]["name"] == name)]

    def held(self, ident: str) -> dict[str, Any] | None:
        """The row of the model document ``ident`` while a live worker holds it, else None: its file is the
        document then (``file_of``)."""
        with self.lock:
            record = self.records.get(ident)
        return record if record is not None and self._working(record["worker"]) else None

    def live(self, ident: str, version: Any = None) -> dict[str, Any] | None:
        """What the worker that built model document ``ident`` recorded of its parameters while it is live
        in the supervisor (``{"script", "name", "rows", "worker"}``: ``cad.engine.parameters.rows``, where each
        is spelled in the code), of its generation ``version`` where one is given; None for a document no
        live worker built, one built before parameters were recorded, or one of another generation. A
        worker retired or gone takes them with it (``prune``)."""
        with self.lock:
            record = self.records.get(ident)
        if record is None or not isinstance(record.get("parameters"), list):
            return None
        worker = record["worker"]
        if worker is None or not self.daemon.supervisor.holds(worker):
            return None
        if version is not None and record["version"] != version:
            return None
        return {"script": record["source"]["script"], "name": record["source"]["name"], "rows": record["parameters"],
                "worker": worker}

    def _working(self, worker: Any) -> bool:
        """Whether ``worker`` holds its documents still: live in the supervisor, or out of it and alive."""
        return worker is not None and (self.daemon.supervisor.holds(worker) or worker.alive())

    def file_of(self, ident: str) -> Path | None:
        """The ``.xbf`` of model (or shape) document ``ident`` where it is on disk, as its record names it: the
        document while no worker holds it. None for no such record, or a file that is gone."""
        held = self.registry()
        record = held.get(ident) if held is not None else None
        if record is None or record.get("kind") not in ("model", "shape"):
            return None
        from cad_server.engine.registry import xbf

        path = xbf(held, record)
        return path if path is not None and path.is_file() else None

    def rebuild(self, ident: str) -> dict[str, Any] | None:
        """What the engine knows of a model document no worker holds and whose ``.xbf`` is gone: its state
        (``unsaved``, ``detached``), the command that builds it again -- ``cad run`` and the script that defines
        it -- and why, in words (the page's ``error``). None for a document a worker holds, one whose file is
        there (the file is the document), or one the engine never built. The engine never runs the command."""
        if self.held(ident) is not None or self.file_of(ident) is not None:
            return None
        return self.recorded(ident)

    def command(self, ident: str) -> str | None:
        """The command that builds model document ``ident`` again: ``cad run`` and the script that
        defines its model -- never a program that imported it and called it -- or, for one its last run
        built in a Python of its own, that Python and the script; from this process's book or the
        registry's record. None for an id the engine never built."""
        with self.lock:
            found = self.records.get(ident)
        if found is None:
            known = self.recorded(ident)
            return known["rebuild"] if known is not None else None
        from cad_server.engine.registry import rerun

        return rerun(found["source"]["script"], found.get("python"), found.get("with"))

    def recorded(self, ident: str) -> dict[str, Any] | None:
        """What the registry knows of a model document whose ``.xbf`` is gone: ``unsaved``, with the command that
        builds it again, or ``detached`` when its script is gone too. None for an id it has no model's record of.
        Nothing is run."""
        from cad_server.engine import registry as registering

        held = self.registry()
        found = held.get(ident) if held is not None else None
        if found is None or found.get("kind") not in ("model", "shape"):
            return None
        name = found.get("entry") or ident
        if found["kind"] == "shape":
            program = registering.program(held, found)
            return {"error": unsaved(name, ident, None, self.shown(str(program) if program else None)), "state": "unsaved",
                    "rebuild": None}
        if registering.detached(held, found):
            return {"error": f"{name} ({ident}) is detached: its .xbf and {registering.home(held, found)} are gone, "
                             "and nothing builds it again; delete it from the home", "state": "detached", "rebuild": None}
        command = registering.command(held, found)
        return {"error": unsaved(name, ident, command), "state": "unsaved", "rebuild": command}

    def missing(self, ident: str) -> str:
        """Why no document ``ident`` is here, with the command that builds it again where the
        engine built it before: the engine never runs it."""
        found = self.rebuild(ident)
        return found["error"] if found is not None else f"no document {ident} is held"

    def not_held(self, ident: str) -> Exception:
        """The refusal for a model document the engine does not hold (``serve.NotHeld``)."""
        from cad.engine.serve import NotHeld

        found = self.rebuild(ident)
        if found is None:
            return NotHeld(self.missing(ident), "unsaved", None)
        return NotHeld(found["error"], found["state"], found["rebuild"])

    def drain(self, worker: Any) -> None:
        """Before ``worker`` is retired: each document of it is its ``.xbf`` from now on (``release``), which its
        build wrote. Nothing is taken from the worker: the file is the document."""
        for ident in self.paths(worker):
            self.release(ident, worker)

    def release(self, ident: str, worker: Any = None) -> None:
        """Model document ``ident`` held by no worker now (``worker``, where one is named: its row, unless a build
        since gave it another): its row dropped, and its page its ``.xbf``'s, read as any file is."""
        with self.lock:
            row = self.records.get(ident)
            if row is None or (worker is not None and row["worker"] is not worker):
                return
            del self.records[ident]
            if self.daemon.builders.get(ident) is row["worker"]:
                self.daemon.builders.pop(ident, None)
        server = self.daemon.server
        if server is not None:
            server.forget_model(ident)
            self.revive(ident)

    def revive(self, ident: str) -> None:
        """A model (or shape) document no worker holds, asked for by its id: its ``.xbf``, known to the server as a
        file from now on, read when a page or a verb asks. Nothing is read but its record, nothing is run."""
        server = self.daemon.server
        with self.lock:
            if ident in self.records:
                return
        path = self.file_of(ident) if server is not None else None
        if path is not None:
            server.remember(path)

    def serve(self, ident: str) -> tuple[Any, str]:
        """The server and the id of the model document ``ident`` a live worker holds; refused
        (``not_held``), naming its state and the command that builds it again, when none does.
        Nothing is built."""
        if self.held(ident) is None:
            raise self.not_held(ident)
        return self.register_page(ident), ident

    def load(self, ident: str) -> tuple:
        """A model document's structure and shape bytes, asked of the worker that holds it, through a lease.
        ``serve.NotHeld`` when no worker holds it: its file is the document then (``release``), and nothing is
        built to bring it back."""
        with self.lock:
            record = self.records.get(ident)
            if record is None:
                raise self.not_held(ident)
            source, version = record["source"], record["version"]
            worker = record["worker"]
        if worker is None or not self.daemon.supervisor.holds(worker):
            self.prune()
            raise self.not_held(ident)
        order = {"op": "result", "script": source["script"], "name": source["name"]}
        replies: list[dict[str, Any]] = []
        # Asked of the worker that built it (``via``, in the Python it runs): a child model's is its
        # parent's script's.
        held = getattr(worker, "python_key", None)
        self.daemon.handle({**order, "env": worker.environment, "via": worker.label, "held": ident,
                            **({"python_key": held} if held else {})}, replies.append)
        answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
        payload = base64.b64decode(answer.get("payload", ""))
        if "failed" in answer:
            raise ValueError(answer["failed"])
        done = answer["done"]
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + size]
            at += size
        from cad.engine.export.viewer import fingerprint

        structure = {**done["structure"], "exportRevision": fingerprint(done["structure"]), "path": ident,
                     "id": ident, "closure": done.get("closure"), "version": version}
        return structure, shapes

    def prune(self) -> None:
        """Each row whose worker is gone is released: its document is its ``.xbf`` (``release``)."""
        with self.lock:
            gone = [(ident, row["worker"]) for ident, row in self.records.items()
                    if row["worker"] is None or not (row["worker"].alive() or self.daemon.supervisor.holds(row["worker"]))]
        for ident, worker in gone:
            self.release(ident, worker)

    def listing(self) -> list[dict[str, Any]]:
        """The model documents a live worker holds, each with its ``state`` (``STATES``). One that declares files
        is listed like any other: they are exports."""
        self.prune()
        with self.lock:
            rows = list(self.records.values())
        return [{"id": row["id"], "script": row["source"]["script"], "name": row["source"]["name"],
                 "builtAt": row["builtAt"], "version": row["version"], "kind": row["kind"],
                 "state": self.state(row["id"])} for row in rows]

    def state(self, ident: str) -> str:
        """``live`` (a live worker holds it), ``building``, ``failed`` (its last build), ``held`` (no worker: its
        ``.xbf`` is the document), ``unsaved`` (no worker, and its ``.xbf`` is gone -- deleted or moved by hand, or
        never written -- the registry knows it), or ``detached`` (its ``.xbf`` and its script are gone)."""
        server = self.daemon.server
        build = server.build_of(ident) if server is not None else {}
        if build.get("building"):
            return "building"
        if build.get("failed"):
            return "failed"
        if self.held(ident) is not None:
            return "live"
        if self.file_of(ident) is not None:
            return "held"
        known = self.recorded(ident)
        return known["state"] if known is not None else "unsaved"

    def row(self, ident: str) -> dict[str, Any] | None:
        """This process's book's row of document ``ident`` (a copy of it), else None."""
        with self.lock:
            found = self.records.get(ident)
            return dict(found) if found is not None else None

    def delete(self, ident: str) -> dict[str, Any] | None:
        """``delete`` with this engine's book: what it holds of document ``ident`` dropped first."""
        return delete(self.registry(), ident, self)

    def forget(self, ident: str) -> dict[str, Any] | None:
        """What this engine holds of document ``ident``, dropped: its row in the book (a live
        document's too: its next run registers it again), the server's copy and its page. Its record is
        ``delete``'s. The row as it was, or None."""
        with self.lock:
            row = self.records.pop(ident, None)
        if self.daemon.builders.get(ident) is not None:
            self.daemon.builders.pop(ident, None)
        server = self.daemon.server
        if server is not None:
            server.forget_model(ident)
        return row
