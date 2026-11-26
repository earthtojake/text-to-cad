"""The daemon's book of the model documents a live worker holds, each by its id: its ``.xbf``'s
(``ids.file_id``).

A model's document is its ``.xbf``: every run writes it (law 10), and the engine's live build is what makes
the page live while a worker holds it. Only metadata lives here: a document's structure and shape bytes are
the server's (``serve.Server``), asked of the worker that built it (``load``); registration never meshes or
materializes an unviewed model. A worker retired (``drain``) or gone (``prune``) takes its rows with it, and
its documents are their files from then on: the server reads each ``.xbf`` as it reads any file (``release``),
and so does a verb by its id (``locate``). A document whose file is gone names nothing (``not_held``), and
the engine runs nothing to bring it back. The book is process memory. So are the rows a build's report gives
of its model's parameters -- where each is spelled in the code -- which the book keeps while the worker that
recorded them is live (``live``), and never writes or sends on (``parameters``).

Nothing of a document is recorded: what outlives the process is its file. A run's first build of an ``.xbf``
adds the file to the library (``library.Library.know``), so its id answers after a restart wherever the file
is, and its count is noted in the cache (``library.Notes.count``). A served document's generation
(``version``, what a page shows and the viewer's export compares) is a token of its build's own, never a counter
that starts again, so an id and a generation never name two documents across a restart; a run of the same
closure in the worker holding the last build keeps it (nothing ran, nothing changed: no page fetches it again);
a row's ``revision`` is its build closure's key (``revision``), with the parameters its document records
where it records any, the same for the same code and the same record, and one whose script declares other
values -- which its closure need not reach: a sibling model's parameter -- is a new revision.
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

# A document's states, as ``cad server status`` lists them (``state``).
STATES = ("live", "held", "building", "failed")


def _saving(path: Any) -> Path | None:
    """The ``.xbf`` a shape handed over is saved as (``hand_over``'s ``saved``), canonical; None for none."""
    if not isinstance(path, str) or not path.lower().endswith(".xbf") or not os.path.isabs(path):
        return None
    from cad.engine.ids import canonical

    try:
        return Path(canonical(path))
    except (OSError, ValueError):
        return None


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
        from cad_server.engine.library import Library, Notes

        self.library, self.notes = Library(), Notes()

    def register(self, worker: Any, answer: dict) -> None:
        done = answer.get("done")
        reports = done.get("reports", []) if isinstance(done, dict) else done
        if not isinstance(reports, list):
            return
        program = answer.get("program")
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
                if not source.get("xbf"):
                    self.unsaved(report)
                    continue
                facts, before = self.facts(ident, report, recorded)
                self.noted(source["xbf"], (facts or {}).get("parts"))
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
                                           "kind": "xbf",
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

    def unsaved(self, report: dict[str, Any]) -> None:
        """A function with file decorators alone, built: no ``.xbf``, so no model document -- no row, no
        page of its own. Its page is its first file's, served as that file (a STEP opened as a file)."""
        from cad.engine.delta import delta
        from cad.engine.ids import file_id

        facts = report.pop("facts", None)
        if facts is not None:
            report["delta"] = delta(facts, None)
        first = next((path for path in report.get("files") or {}), None)
        if first is None:
            return
        server = self.daemon.serve({})
        server.remember(first)
        report["url"] = self.url(server, file_id(first))

    def facts(self, ident: str, report: dict[str, Any], recorded: str) -> tuple[dict | None, dict | None]:
        """A build's facts (``delta.facts``) and the last build's, of document ``ident``: the
        worker's, else -- a model taken from its key, nothing built -- the ones its row holds
        for this revision; the last from the book. None where there are none."""
        now = report.pop("facts", None)
        with self.lock:
            row = self.records.get(ident) or {}
        kept, at = row.get("facts"), row.get("revision")
        if now is None and at == recorded:
            now = kept
        return now, kept

    def noted(self, xbf: Any, parts: Any) -> None:
        """A model's ``.xbf`` the engine wrote or kept, as the home lists it from now on: the library knows the
        file (a write the first time alone), and the cache notes its part occurrences where they are in hand.
        A state folder that cannot be written keeps nothing, and fails no build."""
        try:
            self.library.know(xbf)
        except OSError:
            pass
        if type(parts) is int:
            self.notes.count(xbf, parts)

    def exported(self, answer: dict[str, Any]) -> None:
        """An export's answer (``worker._export``'s files): each .xbf it wrote counted (its document's parts'
        occurrences) in the cache's note of the file as it now is (``library.Notes.count``): its row says Part
        or Assembly without the file ever being read. An ``.xbf`` exported is a file of its own, another model:
        its own id, its own card once a page opens it."""
        done = answer.get("done")
        for row in (done.get("files") or []) if isinstance(done, dict) else []:
            if isinstance(row, dict) and row.get("kind") == "xbf" and type(row.get("parts")) is int \
                    and isinstance(row.get("path"), str):
                self.notes.count(row["path"], row["parts"])

    def hand_over(self, request: dict[str, Any]) -> dict[str, Any]:
        """A shape a program handed over (``api.hand_over``): its document's bytes read through the
        documents worker -- checked, and its parts counted -- then written as its ``.xbf`` (``_save``), a file the
        library knows from then on (``noted``): the engine did not run it, so nothing builds it again. Its page
        is its file's, read as any file is. Refused (``ValueError``) for bytes that are no document. The answer
        carries its page."""
        from cad.engine.ids import file_id, is_id

        name = str(request.get("name"))
        saving = _saving(request.get("saved"))
        if saving is None:
            raise ValueError(f"{name}: a shape handed over is saved as its .xbf, and names its path")
        ident = file_id(saving)
        if str(request.get("id")) != ident or not is_id(ident):
            raise ValueError(f"{request.get('id')!r} is not the id of {saving}")
        data = base64.b64decode(request.get("xbf") or "")
        replies: list[dict[str, Any]] = []
        # Read by the documents worker in its caller's environment, as a file's or an .xbf's bytes are: a worker
        # started in none would lack what its interpreter needs to start (on Windows, the user's home).
        self.daemon._call({"source": {"document": ident}, "cwd": request.get("cwd"), "env": request.get("env")},
                          {"id": 1, "op": "result", "document": True, "name": name}, replies.append, data)
        answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
        if "done" not in answer:
            raise ValueError(f"{name}: the shape handed over is no document: {answer.get('failed')}")
        parts = len(answer["done"]["structure"].get("instances") or [])
        written = self._save(saving, data)
        if written:
            self.noted(saving, parts)
        server = self.daemon.serve({})
        self.drop(ident)  # a model's page at this id before: the file is the document now
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
            version, name, xbf = record["version"], record["source"]["name"], record["source"]["xbf"]
        server.remember(xbf)  # its file, which the server's route looks at (a model whose .xbf is gone is not held)
        server.register_model(ident, name, lambda: self.load(ident), version)
        return server

    def paths(self, worker: Any, model: str | None = None) -> list[str]:
        """The ids of the documents ``worker`` holds (of model ``model``'s name, when given)."""
        name = model.rsplit("::", 1)[-1] if model else None
        with self.lock:
            return [ident for ident, row in self.records.items() if row["worker"] is worker
                    and (name is None or row["source"]["name"] == name)]

    def held(self, ident: str) -> dict[str, Any] | None:
        """The row of the model document ``ident`` while a live worker holds it and its ``.xbf`` is at its path,
        else None: its file is the document then (``locate``), and a row whose file is gone is let go
        (``release``): the id names nothing, whatever the worker holds."""
        with self.lock:
            record = self.records.get(ident)
        if record is None or self._holds(record):
            return record
        self.release(ident, record["worker"])
        return None

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

    def _holds(self, row: dict[str, Any]) -> bool:
        """Whether ``row``'s worker holds its document still -- live in the supervisor, or out of it and alive --
        and its ``.xbf`` is at its path: a document whose file is gone is gone, whoever holds its build."""
        worker = row["worker"]
        return (worker is not None and (self.daemon.supervisor.holds(worker) or worker.alive())
                and os.path.isfile(row["source"]["xbf"]))

    def locate(self, ident: str) -> Path | None:
        """The file of document ``ident`` where it is now, with no record of it: the ``.xbf`` its row names
        (a model a live worker holds), else the one the server finds by its id (``serve.Server.locate``: a file it
        was named since it started, the library's, a project folder's). While nothing is served, the library's;
        and where the library has none and holds a project, the server is started to look in its folder. None
        for an id that names no file that is there."""
        with self.lock:
            row = self.records.get(ident)
        found = row["source"].get("xbf") if row is not None else None
        if not (found and os.path.isfile(found)):
            server = self.daemon.server
            found = server.locate(ident) if server is not None else self.library.path_of(ident)
            if server is None and not (found and os.path.isfile(found)) and self.library.read()["projects"]:
                found = self.daemon.serve({}).locate(ident)
        return Path(found) if found and os.path.isfile(found) else None

    @staticmethod
    def not_held(ident: str) -> Exception:
        """The refusal for an id that names no document (``serve.NotHeld``)."""
        from cad.engine.serve import NotHeld

        return NotHeld(f"no document {ident} is held")

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
            if os.path.isfile(row["source"].get("xbf") or ""):
                server.remember(row["source"]["xbf"])

    def serve(self, ident: str) -> tuple[Any, str]:
        """The server and the id of the model document ``ident`` a live worker holds; refused
        (``not_held``) when none does. Nothing is built."""
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
        """Each row whose worker is gone, or whose ``.xbf`` is, is released: its document is its ``.xbf``
        (``release``), or nothing."""
        with self.lock:
            gone = [(ident, row["worker"]) for ident, row in self.records.items() if not self._holds(row)]
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

    def state(self, ident: str) -> str | None:
        """``live`` (a live worker holds it), ``building``, ``failed`` (its last build), ``held`` (no worker: its
        file is the document); None for an id that names nothing: one whose file is gone, whatever its last build."""
        live = self.held(ident) is not None
        if not live and self.locate(ident) is None:
            return None
        server = self.daemon.server
        build = server.build_of(ident) if server is not None else {}
        if build.get("building"):
            return "building"
        if build.get("failed"):
            return "failed"
        return "live" if live else "held"

    def row(self, ident: str) -> dict[str, Any] | None:
        """This process's book's row of document ``ident`` (a copy of it), else None."""
        with self.lock:
            found = self.records.get(ident)
            return dict(found) if found is not None else None

    def forget(self, ident: str) -> None:
        """Document ``ident`` forgotten (the home's Remove): what this engine holds of it (``drop``) and its
        library entry. Never a file, nor what the cache derived of it (its note, its kept checks: facts of the
        file's bytes, whether or not it is in Recents): the document is its file still, and a project's folder
        lists it as before, with its count and its picture."""
        self.drop(ident)
        self.library.forget(ident)

    def drop(self, ident: str) -> dict[str, Any] | None:
        """What this engine holds of document ``ident``, dropped: its row in the book (a live
        document's too: its next run registers it again), the server's copy and its page. The row as it was, or
        None."""
        with self.lock:
            row = self.records.pop(ident, None)
        if self.daemon.builders.get(ident) is not None:
            self.daemon.builders.pop(ident, None)
        server = self.daemon.server
        if server is not None:
            server.forget_model(ident)
        return row
