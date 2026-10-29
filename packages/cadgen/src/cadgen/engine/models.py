"""The daemon's book of the model documents it has built, each by its id (``ids.model_id``).

Only metadata lives here: a document's structure and shape bytes are the server's
(``serve.Server``). Opening a document asks its worker for them; registration never meshes or
materializes an unviewed model. A document outlives its worker: before the pool retires a worker,
the daemon takes from it every document of it the server does not hold yet
(``drain``), and the record stays with no worker (``held``). A ``shape`` document, a
shape a program handed over (``hand_over``), has no worker from the start: it is held as a drained
document is, and no command builds it again. A document held nowhere is never built here: whoever
asks for it is told the command that builds it again (``missing``), and the engine runs nothing.
The book is process memory.

What outlives the process is the registry's (``registry``): each ``model`` and ``shape`` document
is recorded there as it is registered (``record``, ``hand_over``), synchronously, so after a restart
its id is known -- ``held`` from its cache file, or ``unsaved`` with the command that builds it
again (none for a shape) when the cache holds no file of it, or
``detached`` once its script is gone -- and nothing is run to bring it back. An explicit ``name=`` claims its id
for one declaration within its script folder: another declaration is refused, naming both
locations (``identity.claimed``), until the claiming file is gone or a run of it declares the name
no more (``identity.released``). A served
document's generation (``version``, what a page shows and the viewer's export compares) is a token
of its build's own, never a counter that starts again, so an id and a generation never name two
documents across a restart; a run of the same closure in the worker holding the last build keeps it
(nothing ran, nothing changed: no page fetches it again); its record's ``revision`` is its build closure's key (``revision``), the
same for the same code, so a build that changed nothing rewrites no record.

What a restart opens at once is the cache's (``cache``): each ``model`` and ``shape`` document's
bytes, saved in its registry folder once it has been idle (and at its drain, and at shutdown). A
document with a cache file is ``held`` -- the engine answers it without a worker -- in memory, on
disk, or both (``where``): after a restart its id is taken up (``adopt``) from its record the first
time anything names it, and its bytes are read through the documents worker when a verb needs them
(``load``). It is the last built state, never a rerun: the engine knows the document of its last
run, never whether the code on disk has changed since; when to run the code again is the agent's
call.
"""
from __future__ import annotations

import base64
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

# A document's states, as ``cadgen status`` lists them (``state``).
STATES = ("live", "held", "building", "failed", "unsaved", "detached")


def unsaved(name: str, ident: str, command: str | None, shown: str | None = None) -> str:
    """Why a model document is ``unsaved`` -- held by no worker and in no memory, its file missing from
    the engine's cache (deleted by hand, or the cache could not be written when it was to be saved),
    which nothing else empties -- in the words every surface says: with the command that builds it
    again, or, for a shape handed over (``shown``, the words its record keeps), the program that
    handed it over."""
    said = f"{name} ({ident}) is not saved: the engine's cache holds no file of its last "
    if command is None:
        return said + f"hand-over, and it is {shown}; run that program again to hand it over again"
    return said + f"build; run `{command}` to build it again"


def delete(held: Any, ident: str, book: "Models | None" = None) -> dict[str, Any] | None:
    """Delete document ``ident``: the one deletion, which ``cadgen delete`` and the home's Delete both
    are. What the engine holds of it goes first, where an engine runs (``book``: ``Models.forget``),
    then its record and its document in the engine's cache (``held``, the registry:
    ``Registry.delete``). Never a file of the person's: a model's script and its declared files, and a
    file a page opened, stay where they are. What was deleted, ``{"id", "name", "kind"}``, or None for
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


def revision(report: dict[str, Any]) -> str:
    """A model document's recorded revision: its closure's key (the same code, the same revision, in
    any process), else a token of this build's own."""
    key = (report.get("closure") or {}).get("key")
    return str(key) if key else f"t{secrets.token_hex(8)}"


class Models:
    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.records: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.identity_lock = threading.RLock()
        from cadgen.engine.cache import Cache

        self.cache = Cache(self)

    def register(self, worker: Any, answer: dict) -> None:
        done = answer.get("done")
        reports = done.get("reports", []) if isinstance(done, dict) else done
        if not isinstance(reports, list):
            return
        program = answer.get("program")
        # Per script of the run: the explicit names it declares now, and those its models' records
        # say it declared before (None: no record says), to give up what it declares no more.
        declared: dict[str, tuple[list[str], set[str] | None]] = {}
        for root in reports:
            if not root.get("ok") and root.get("id") and self.held(root["id"]) is not None:
                root["previous"] = True  # the failed run's line says its previous good build is served
            for report in [root, *(root.get("child_models") or {}).values()]:
                ident, source = report.get("id"), report.get("source")
                if not report.get("ok") or not ident or not source:
                    continue
                recorded = revision(report)
                facts, before = self.facts(ident, report, recorded)
                try:
                    if source.get("explicit_name") is not None:
                        from cadgen.engine.identity import claimed

                        held = self.registry()
                        if held is not None:
                            claimed(held, source, source["explicit_name"])
                    had = self.record(report, recorded, facts)
                    if isinstance(source.get("declares"), list):
                        _now, was = declared.get(source["script"], (source["declares"], None))
                        if isinstance(had.get("declares"), list):
                            was = (was or set()) | set(had["declares"])
                        declared[source["script"]] = (source["declares"], was)
                except ValueError as error:  # a name another declaration holds: the build is refused, by name
                    report["ok"], report["error"] = False, f"{source['name']}: {error}"
                    root["ok"] = False
                    root.setdefault("error", report["error"])
                    continue
                with self.lock:
                    old = self.records.get(ident)
                    # This build's generation. A document is what its last run made: a run of the same
                    # code and inputs (its closure's key) in the worker that holds the last build made
                    # that document again -- nothing ran, or it ran to the same bytes -- so its generation
                    # stands, no page fetches it again and an export of it is still the one displayed.
                    # Anything else is a new generation.
                    same = (old is not None and old.get("worker") is worker and old.get("revision") == recorded
                            and not recorded.startswith("t"))
                    version = old["version"] if same else secrets.token_hex(8)
                    self.records[ident] = {"id": ident, "source": source, "worker": worker,
                                           "program": program or (old or {}).get("program") or source["script"],
                                           "kind": "model",
                                           "builtAt": time.time(), "version": version,
                                           "files": list(report.get("files") or {}), "revision": recorded,
                                           "facts": facts}
                if facts is not None:
                    from cadgen.engine.delta import delta

                    report["delta"] = delta(facts, before)
                self.daemon.builders[ident] = worker
                server = self.register_page(ident)
                report["url"] = self.url(server, ident)
                if (report.get("cache") or {}).get("unreadable"):
                    self.cache.refresh(ident)  # retain old bytes until this successful build is saved atomically
                self.cache.touch(ident)
        held = self.registry() if declared else None
        if held is not None:
            from cadgen.engine.identity import claims, released

            for script, (now, was) in declared.items():
                # What the script's records said it declared, else -- none of this run's models had a
                # record saying it -- the claims the registry holds of it, read once.
                released(held, script, (was if was is not None else claims(held, script)) - set(now))

    def reattach(self, sources: list[dict[str, Any]], pid: int | None = None) -> list[str]:
        """A worker's models with nothing to take up (``build._reattach``: each its ``source``), each
        re-attached to the record of its script moved (``identity.reattach``) before the worker reads
        its cache: a document this engine holds live and has not saved yet is saved first, from the
        bytes the server holds or the worker that holds it (never the asking worker, ``pid``, busy
        building), so its cache file moves with its record; what the book holds of an old id is
        dropped. The lines that say what was re-attached."""
        from cadgen.engine.identity import reattach

        held = self.registry()
        if held is None:
            return []
        lines: list[str] = []

        def save(record):
            row = self.row(record["id"])
            if row is None or self.cache.current(record["id"], row["revision"]):
                return
            try:
                data = self.held_bytes(record["id"], row["version"])
                worker = row.get("worker")
                if data is None and worker is not None and worker.pid != pid:
                    _structure, _shapes, data = self.load(record["id"], worker, whole=True)
                if data:
                    self.cache._write(record["id"], row["revision"], data)
            except Exception as error:  # noqa: BLE001 - its record moves all the same, with what its cache holds
                self.cache.failed(record["id"], f"{type(error).__name__}: {error}")

        with self.identity_lock:
            moved = [(old, new) for old, new in reattach(held, sources, before=save, log=lines.append) if old != new]
            for old, _new in moved:
                self.forget(old)
            if moved:
                with self.cache.lock:
                    self.cache.indexed = False  # the moved cache files: indexed again when next asked
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

    # --- the registry ------------------------------------------------------------------------

    @staticmethod
    def registry() -> Any:
        from cadgen.engine import registry

        return registry.current()

    def record(self, report: dict[str, Any], recorded: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
        """The registry's record of a document a build made (``registry``), written when it changed;
        the record it had (``{}``: none). Nothing with no registry."""
        from cadgen.engine import registry as registering

        held = self.registry()
        if held is None:
            return {}
        ident, source = report["id"], report["source"]
        script = Path(source["script"])
        with held._lock(ident):
            old = held.get(ident) or {}
            root = str(script.parent)
            # What a restart needs of it and no more: what it is (``id``, ``kind``, ``key``), where its
            # code is (``root``, ``home``, ``entry``: the command that builds it again is ``python``
            # of its home, always), the revision the cache and the delta compare, when it was built (the
            # home's order) and when it was first built (``created``, the home's Created: kept from the
            # record it had; a record from before the time was kept stays without one). The closure is
            # its document's own (``previous``); which files it declared is no one's: they are exports.
            found: dict[str, Any] = {
                "id": ident, "kind": "model", "root": root, "home": registering.relative(script, root),
                "entry": source["name"], "namespace": root, "name": source.get("explicit_name") or source["name"],
                "revision": recorded, "fingerprint": source.get("fingerprint"), "module": source.get("module"),
                "built": old["built"] if old.get("revision") == recorded and old.get("built") else time.time()}
            if not old:
                found["created"] = found["built"]
            elif "created" in old:
                found["created"] = old["created"]
            if source.get("explicit_name") is not None:
                found["line"] = source["line"]  # its claim of the name in its folder (``identity.claimed``)
            if isinstance(source.get("declares"), list):
                found["declares"] = source["declares"]  # the explicit names its script declared at this run
            if facts is not None:
                found["facts"] = facts
            for key in ("opened", "pinned", "preview", "cache", "relocated"):  # the home's and the cache's, kept across builds
                if key in old:
                    found[key] = old[key]
            if not (report.get("cache") or {}).get("used"):
                found.pop("relocated", None)  # a fresh document has paths at its new home
            held.put(found)
            return old

    def hand_over(self, request: dict[str, Any]) -> dict[str, Any]:
        """A shape a program handed over (``api.hand_over``): its document's bytes read through the
        documents worker -- checked, and made the structure the server serves -- then held as a
        drained document is (``server.keep``, and the cache), its page registered, and recorded as a
        ``kind: "shape"``, with the ``program`` that handed it over where there is one: the engine did
        not run it, so nothing builds it again. Refused (``ValueError``) for bytes that are no
        document, and under the id of a model a script declares (``identity.handed``). The answer
        carries its page."""
        import hashlib

        from cadgen.engine import registry as registering
        from cadgen.engine.ids import is_id

        ident, name, scope = str(request.get("id")), str(request.get("name")), str(request.get("scope"))
        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        held = self.registry()
        if held is not None:
            from cadgen.engine.identity import handed

            handed(held, ident, scope, name)  # one id is one document: a model's is not a shape's
        source = {"script": scope, "name": name}
        data = base64.b64decode(request.get("xbf") or "")
        replies: list[dict[str, Any]] = []
        self.daemon._call({"source": {"document": ident, "held": ident}, "cwd": request.get("cwd")},
                          {"id": 1, "op": "result", "document": True, "name": name}, replies.append, data)
        answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
        if "done" not in answer:
            raise ValueError(f"{name}: the shape handed over is no document: {answer.get('failed')}")
        payload = base64.b64decode(answer.get("payload", ""))
        done = answer["done"]
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + size]
            at += size
        from cadgen.engine.export.viewer import fingerprint

        version = secrets.token_hex(8)
        recorded = "h" + hashlib.blake2b(data, digest_size=16).hexdigest()
        structure = {**done["structure"], "exportRevision": fingerprint(done["structure"]), "path": ident,
                     "id": ident, "closure": None, "version": version}
        program = request.get("program")
        with self.lock:
            old = self.records.get(ident)
            self.records[ident] = {"id": ident, "source": source, "worker": None, "program": program,
                                   "kind": "shape", "builtAt": time.time(), "version": version, "files": [],
                                   "revision": recorded}
        if old is not None and old.get("worker") is not None and self.daemon.builders.get(ident) is old["worker"]:
            del self.daemon.builders[ident]
        held = self.registry()
        if held is not None:
            root = scope if os.path.isdir(scope) else str(Path(scope).parent)
            with held._lock(ident):
                previous = held.get(ident) or {}
                found: dict[str, Any] = {
                    "id": ident, "kind": "shape", "root": root,
                    "home": registering.relative(scope, root), "entry": name, "namespace": root, "name": name,
                    "revision": recorded,
                    "built": previous["built"] if previous.get("revision") == recorded and previous.get("built")
                    else time.time()}
                if not previous:  # first handed over now; an older record keeps what it has (``record``)
                    found["created"] = found["built"]
                elif "created" in previous:
                    found["created"] = previous["created"]
                if program:
                    found["program"] = registering.relative(program, root)  # what its words name (``shown``)
                for key in ("opened", "pinned", "preview", "cache"):
                    if key in previous:
                        found[key] = previous[key]
                held.put(found)
        server = self.register_page(ident)
        server.keep(ident, structure, shapes, version, data)
        self.cache.keep(ident, recorded, data)
        self.cache.touch(ident)
        return {"done": {"id": ident, "url": self.url(server, ident)}}

    @staticmethod
    def shown(program: str | None) -> str:
        """What a shape's record says of where it came from: the program, which the engine did not run."""
        return (f"a shape handed over by {program}, a program the engine did not run: no script to rerun, and no "
                "command builds it again" if program else "a shape handed over from a Python session the engine did "
                "not run: no script to rerun, and no command builds it again")

    @staticmethod
    def url(server: Any, ident: str) -> str:
        """The page of document ``ident`` on ``server``: ``/<id>``, with a fresh link that lets it in."""
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
        """The record of the model document ``ident`` while the engine holds it -- a live worker
        does, the server holds its bytes, or its cache file is at its revision (``where``) -- else None."""
        self.adopt(ident)
        with self.lock:
            record = self.records.get(ident)
        if record is None:
            return None
        if self._working(record["worker"]):
            return record
        return record if self.where(ident) else None

    def _working(self, worker: Any) -> bool:
        """Whether ``worker`` holds its documents still: live in the pool, or out of it and alive --
        being retired, and drained (``drain``) before it goes."""
        return worker is not None and (self.daemon.pool.holds(worker) or worker.alive())

    def rebuild(self, ident: str) -> dict[str, Any] | None:
        """What the engine knows of a model document it does not hold: its state (``unsaved``), the
        command that builds it again -- ``python`` and the script that defines it -- and why, in
        words (the page's ``error``). None for a document it holds or never built. The engine never
        runs the command."""
        self.adopt(ident)
        with self.lock:
            found = self.records.get(ident)
        if found is not None and self.held(ident) is not None:
            return None
        if found is None:
            return self.recorded(ident)
        command = self.command(ident)
        name = found["source"]["name"]
        if found["kind"] == "shape":
            known = self.recorded(ident) if found.get("program") is None else None
            if known is not None:
                return known  # taken up after a restart (``adopt``): its record's words name the program
            return {"error": unsaved(name, ident, None, self.shown(found.get("program"))), "state": "unsaved",
                    "rebuild": None}
        if not Path(found["source"]["script"]).is_file():
            return {"error": f"{name} ({ident}) is detached: {found['source']['script']} is gone, and nothing "
                             "builds it again; delete it from the home", "state": "detached", "rebuild": None}
        return {"error": unsaved(name, ident, command), "state": "unsaved", "rebuild": command}

    def command(self, ident: str) -> str | None:
        """The command that builds model document ``ident`` again: ``python`` and the script that
        defines its model -- never a program that imported it and called it -- from this process's
        book or the registry's record. None for an id the engine never built."""
        with self.lock:
            found = self.records.get(ident)
        if found is None:
            known = self.recorded(ident)
            return known["rebuild"] if known is not None else None
        if found["kind"] == "shape":
            return None  # handed over by a program the engine did not run: nothing builds it again
        from cadgen.engine.registry import rerun

        return rerun(found["source"]["script"])

    def recorded(self, ident: str) -> dict[str, Any] | None:
        """What the registry knows of a model document this process never built (one built before a
        restart) whose cache file is not there: ``unsaved``, with the command that builds it again, or
        ``detached`` when its script
        is gone. None for an id it has no model's record of. Nothing is run."""
        from cadgen.engine import registry as registering

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
            return {"error": f"{name} ({ident}) is detached: {registering.home(held, found)} is gone, and nothing "
                             "builds it again; delete it from the home", "state": "detached", "rebuild": None}
        command = registering.command(held, found)
        return {"error": unsaved(name, ident, command), "state": "unsaved", "rebuild": command}

    def missing(self, ident: str) -> str:
        """Why no document ``ident`` is here, with the command that builds it again where the
        engine built it before: the engine never runs it."""
        found = self.rebuild(ident)
        return found["error"] if found is not None else f"no document {ident} is held"

    def not_held(self, ident: str) -> Exception:
        """The refusal for a model document the engine does not hold (``serve.NotHeld``)."""
        from cadgen.engine.serve import NotHeld

        found = self.rebuild(ident)
        if found is None:
            return NotHeld(self.missing(ident), "unsaved", None)
        return NotHeld(found["error"], found["state"], found["rebuild"])

    def drain(self, worker: Any) -> None:
        """Before ``worker`` is retired: every document of it the server does not hold
        whole at its version is taken from it -- its ``result``, never meshed, with the whole
        document as xbf bytes (``document.to_bytes``, its animations' record with it) -- so it outlives
        the worker and answers every verb as an on-disk xbf does, and a GLB of it as the build's GLB. A
        worker that is gone (a crash) drains nothing: its documents the server and the cache lack are
        ``unsaved``."""
        server = self.daemon.server
        if server is None or not worker.alive():
            return
        from cadgen.engine.daemon import WorkerGone

        with self.lock:
            owed = [(ident, row["version"], row["revision"]) for ident, row in self.records.items()
                    if row["worker"] is worker]
        for ident, version, recorded in owed:
            if server.has(ident, version, whole=True):
                self.cache.keep(ident, recorded, self.held_bytes(ident, version) or b"")
                continue
            try:
                structure, shapes, whole = self.load(ident, worker, whole=True)
            except WorkerGone:
                return
            except (OSError, ValueError, KeyError):
                continue
            with self.lock:
                record = self.records.get(ident)
                current = record is not None and record["version"] == version
            if current:  # a build of it since, by another worker, is newer
                server.keep(ident, structure, shapes, version, whole)
                self.cache.keep(ident, recorded, whole)  # the cache's, at retirement (``cache``)

    def serve(self, ident: str) -> tuple[Any, str]:
        """The server and the id of the model document ``ident`` the engine holds; refused
        (``not_held``), naming its state and the command that builds it again, when it does not.
        Nothing is built."""
        if self.held(ident) is None:
            raise self.not_held(ident)
        return self.register_page(ident), ident

    def load(self, ident: str, leaving: Any = None, whole: bool = False) -> tuple:
        """A model document's structure and shape bytes, asked of the worker that holds it -- through
        the pool, or of ``leaving``, a worker being retired (``drain``), directly, and then
        (``whole``) with the whole document's xbf bytes third. ``serve.NotHeld`` when no worker holds
        it: nothing is built to bring it back. One no worker holds whose cache file is at its revision
        is read from it, through the documents worker (``from_disk``), its xbf bytes third."""
        with self.lock:
            record = self.records.get(ident)
            if record is None:
                raise self.not_held(ident)
            source, version = record["source"], record["version"]
            worker = leaving or record["worker"]
        if worker is None or not worker.alive():
            if leaving is None and self.cache.current(ident, record["revision"]):
                return self.from_disk(ident)
            raise self.not_held(ident)
        if leaving is None:
            self.cache.touch(ident)  # a read: its idle timer starts again
        order = {"op": "result", "script": source["script"], "name": source["name"]}
        if leaving is None and not whole and self.daemon.pool.holds(worker):
            replies = []
            # Asked of the worker that built it (``via``): a child model's is its parent's script's.
            self.daemon.handle({**order, "env": worker.environment, "via": worker.script,
                                "execution": getattr(worker, "execution", None)}, replies.append)
            answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
            payload = base64.b64decode(answer.get("payload", ""))
        else:
            # Out of the pool and still alive: being retired, and asked before it goes.
            answer = worker.build({"id": 1, **order, "whole": whole}, lambda _message: None)
            payload = answer.pop("payload", b"")
        if "failed" in answer:
            raise ValueError(answer["failed"])
        done = answer["done"]
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + size]
            at += size
        from cadgen.engine.export.viewer import fingerprint

        structure = {**done["structure"], "exportRevision": fingerprint(done["structure"]), "path": ident,
                     "id": ident, "closure": done.get("closure"), "version": version}
        if whole:
            return structure, shapes, payload[at:at + int(done.get("xbf") or 0)]
        return structure, shapes

    def prune(self) -> None:
        """Each record whose worker is gone keeps its document, with no worker (``drain`` took it
        first)."""
        with self.lock:
            for ident, row in list(self.records.items()):
                worker = row["worker"]
                if worker is None or worker.alive() or self.daemon.pool.holds(worker):
                    continue  # a worker out of the pool but alive is being retired: drained first
                if self.daemon.builders.get(ident) is worker:
                    del self.daemon.builders[ident]
                row["worker"] = None

    def listing(self) -> list[dict[str, Any]]:
        """The model documents, each with its ``state`` (``STATES``), and for one not held the command
        that builds it again. One that declares files is listed like any other: they are exports."""
        self.prune()
        for ident in self.cache.documents():  # what the cache holds, listed after a restart too
            self.adopt(ident)
        with self.lock:
            found = []
            for row in self.records.values():
                ident = row["id"]
                entry = {"id": ident, "script": row["source"]["script"],
                         "name": row["source"]["name"], "builtAt": row["builtAt"], "version": row["version"],
                         "kind": row["kind"], "state": self.state(ident)}
                if entry["state"] == "held":
                    entry["held"] = self.where(ident)
                lost = self.rebuild(ident) if entry["state"] in ("unsaved", "detached") else None
                if lost is not None and lost["rebuild"]:
                    entry["rebuild"] = lost["rebuild"]
                found.append(entry)
            return found

    def state(self, ident: str) -> str:
        """``live`` (a live worker holds it), ``held`` (the server holds its bytes; no worker),
        ``building``, ``failed`` (its last build), ``unsaved`` (neither, nor its file in the engine's
        cache: deleted by hand, or never written -- the cache could not be written, its worker crashed
        first -- the registry knows it), or ``detached`` (not held, and its script is
        gone). ``held`` is in memory, on disk -- the cache's -- or both (``where``)."""
        self.adopt(ident)
        with self.lock:
            record = self.records.get(ident)
        server = self.daemon.server
        build = server.build_of(ident) if server is not None else {}
        if build.get("building"):
            return "building"
        if build.get("failed"):
            return "failed"
        if record is None:
            known = self.recorded(ident)
            return known["state"] if known is not None else "unsaved"
        if self._working(record["worker"]):
            return "live"
        if self.where(ident):
            return "held"
        if record["kind"] == "shape":
            return "unsaved"  # nothing builds it again, and nothing of it goes missing
        return "unsaved" if Path(record["source"]["script"]).is_file() else "detached"

    # --- the cache (``cache``) ----------------------------------------------------------------

    def row(self, ident: str) -> dict[str, Any] | None:
        """This process's book's row of document ``ident`` (a copy of it), else None."""
        with self.lock:
            found = self.records.get(ident)
            return dict(found) if found is not None else None

    def where(self, ident: str) -> str | None:
        """Where the engine holds a model document no worker does: ``memory`` (the server holds its
        bytes at its generation), ``disk`` (its cache file is at its revision), ``memory and disk``,
        or None (neither)."""
        with self.lock:
            record = self.records.get(ident)
        if record is None:
            return None
        server = self.daemon.server
        memory = server is not None and server.has(ident, record["version"])
        disk = self.cache.current(ident, record.get("revision"))
        return "memory and disk" if memory and disk else "memory" if memory else "disk" if disk else None

    def delete(self, ident: str) -> dict[str, Any] | None:
        """``delete`` with this engine's book: what it holds of document ``ident`` dropped first."""
        return delete(self.registry(), ident, self)

    def forget(self, ident: str) -> dict[str, Any] | None:
        """What this engine holds of document ``ident``, dropped: its row in the book (a live
        document's too: its next run registers it again), the server's copy and its page, the cache's
        index and timer of it. Its record and its cache file are ``delete``'s. The row as it was, or
        None."""
        with self.lock:
            row = self.records.pop(ident, None)
        if self.daemon.builders.get(ident) is not None:
            self.daemon.builders.pop(ident, None)
        server = self.daemon.server
        if server is not None:
            server.forget_model(ident)
        self.cache.forget(ident)
        return row

    def leaving(self, ident: str, version: Any, data: bytes) -> None:
        """Document ``ident``'s xbf bytes at generation ``version``, leaving the server's memory for
        its budget (``serve.Server.trim``): kept by the cache when it does not hold that revision yet,
        so the document is read again from there. Bytes of a generation the book no longer holds (a
        build since made a newer one) are dropped: that build's save follows."""
        with self.lock:
            record = self.records.get(ident)
            revision = record["revision"] if record is not None and record["version"] == version else None
        if revision is not None:
            self.cache.keep(ident, revision, data)

    def adopt(self, ident: str) -> None:
        """A model document this process never built whose cache file is there (after a restart),
        taken into the book from its record: held on disk, no worker, a generation of its own, its
        page registered where the server runs. Nothing is read but its record, nothing is run."""
        from cadgen.engine.ids import is_id

        if not is_id(ident):
            return
        with self.lock:
            before = self.records.get(ident)
        if before is not None:
            if self._working(before["worker"]):
                return
            server = self.daemon.server
            if server is not None:
                with server.load_lock:
                    if ident in server.served and server.model_versions.get(ident) == before["version"]:
                        return
        found = self.cache.found(ident)
        if found is None:
            return
        from cadgen.engine import registry as registering

        record, meta = found
        if before is not None and before["revision"] == meta["revision"]:
            return
        held = self.registry()
        program = registering.program(held, record)
        row = {"id": ident, "source": {"script": str(registering.home(held, record)), "name": record["entry"]},
               "worker": None, "program": str(program) if program else None, "kind": record["kind"],
               "builtAt": record.get("built"), "version": secrets.token_hex(8),
               "files": [], "revision": meta["revision"]}
        with self.lock:
            if self.records.get(ident) is not before:
                return
            self.records[ident] = row
        if self.daemon.server is not None:
            self.register_page(ident)

    def attach(self, server: Any) -> None:
        """The daemon's server, started after documents were taken up from the cache: each is
        registered with it."""
        with self.lock:
            idle = [ident for ident, row in self.records.items() if row["worker"] is None]
        for ident in idle:
            row = self.row(ident)
            if row is not None and self.cache.current(ident, row.get("revision")):
                server.register_model(ident, row["source"]["name"], lambda ident=ident: self.load(ident), row["version"])

    def held_bytes(self, ident: str, version: str) -> bytes | None:
        """The whole document's xbf bytes the server holds of document ``ident`` at ``version``, else None."""
        server = self.daemon.server
        if server is None:
            return None
        with server.load_lock:
            doc = server.served.get(ident)
            return doc.xbf if doc is not None and server.model_versions.get(ident) == version else None

    def disk_bytes(self, ident: str) -> bytes | None:
        """The bytes of document ``ident``'s cache file when it is at the revision the book holds, its
        read noted (its idle timer and its recency); else None."""
        with self.lock:
            record = self.records.get(ident)
        if record is None or not self.cache.current(ident, record.get("revision")):
            return None
        data = self.cache.read(ident, record.get("revision"))
        if data is not None:
            self.cache.touch(ident)
        return data

    def from_disk(self, ident: str) -> tuple:
        """Document ``ident`` read from its cache file through the documents worker, as a held
        document's bytes are (``worker._result``): its structure, its shape bytes and its xbf bytes.
        ``serve.NotHeld`` when the file is gone."""
        data = self.disk_bytes(ident)
        with self.lock:
            record = self.records.get(ident)
        if data is None or record is None:
            raise self.not_held(ident)
        replies: list[dict[str, Any]] = []
        name = record["source"]["name"]
        self.daemon._call({"source": {"document": ident, "held": ident}},
                          {"id": 1, "op": "result", "document": True, "name": name}, replies.append, data)
        answer = next((row for row in reversed(replies) if "done" in row or "failed" in row), {})
        if "done" not in answer:
            from cadgen.engine.document_migrations import DocumentCompatibilityError

            error = DocumentCompatibilityError if answer.get("kind") == (
                "cadgen.engine.document_migrations:DocumentCompatibilityError") else ValueError
            raise error(answer.get("failed") or f"{name} ({ident}): its cache file could not be read")
        payload = base64.b64decode(answer.get("payload", ""))
        done = answer["done"]
        shapes, at = {}, 0
        for key, size in done["shapes"]:
            shapes[key] = payload[at:at + size]
            at += size
        from cadgen.engine.export.viewer import fingerprint

        structure = {**done["structure"], "exportRevision": fingerprint(done["structure"]), "path": ident,
                     "id": ident, "closure": done.get("closure"), "version": record["version"]}
        return structure, shapes, data
