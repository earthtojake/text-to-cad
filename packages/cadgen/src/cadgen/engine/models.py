"""The daemon's book of the model documents it has built, each by its id (``ids.model_id``).

Only metadata lives here: a document's structure and shape bytes are the server's
(``serve.Server``). Opening a document asks its worker for them; registration never meshes or
materializes an unviewed model. A document outlives its worker: before the pool retires a worker,
the daemon takes from it every ``pointer`` document of it the server does not hold yet
(``drain``), and the record stays with no worker (``held``) until memory evicts its bytes
(``evicted``). A ``memory`` document goes with its worker (``expired``). A ``shape`` document, a
shape a program handed over (``hand_over``), has no worker from the start: it is held as a drained
document is, and no command builds it again. A document held nowhere is never built here: whoever
asks for it is told the command that builds it again (``missing``), and the engine runs nothing.
The book is process memory.

What outlives the process is the registry's (``registry``): each ``pointer`` and ``shape`` document
is recorded there as it is registered (``record``, ``hand_over``), synchronously, so after a restart
its id is known -- ``evicted``, with the command that builds it again (none for a shape), or
``detached`` once its script is gone -- and nothing is run to bring it back. A ``memory`` document
has no record. A ``key=`` claims its id for one declaration: another declaration's build or hand-over
of that key is refused, naming the one that holds it (``claimed``). A served
document's generation (``version``, what a page shows and the viewer's export compares) is a token
of its build's own, never a counter that starts again, so an id and a generation never name two
documents across a restart; its record's ``revision`` is its build closure's key (``revision``), the
same for the same code, so a build that changed nothing rewrites no record.

What a restart opens at once is the cache's (``cache``): each ``pointer`` and ``shape`` document's
bytes, saved in its registry folder once it has been idle (and at its drain, and at shutdown). A
document with a cache file is ``held`` -- the engine answers it without a worker -- in memory, on
disk, or both (``where``): after a restart its id is taken up (``adopt``) from its record the first
time anything names it, and its bytes are read through the documents worker when a verb needs them
(``load``). It is the last built state, never a rerun: when a file its build read has changed since,
it says so (``stale``), with the command that builds it again.
"""
from __future__ import annotations

import base64
import os
import platform
import secrets
import shlex
import threading
import time
from pathlib import Path
from typing import Any

from cadgen.engine.cache import reads as cache_reads

# A document's states, as ``cadgen status`` lists them (``state``).
STATES = ("live", "held", "building", "failed", "evicted", "expired", "detached")


def revision(report: dict[str, Any]) -> str:
    """A model document's recorded revision: its closure's key (the same code, the same revision, in
    any process), else a token of this build's own."""
    key = (report.get("closure") or {}).get("key")
    return str(key) if key else f"t{secrets.token_hex(8)}"


def runtime() -> dict[str, str]:
    """What a recorded document was built on, by version only."""
    from cadgen.engine import previous

    return {"python": platform.python_version(), "cadgen": previous.version(), **previous._libraries()}


class Models:
    def __init__(self, daemon: Any) -> None:
        self.daemon = daemon
        self.records: dict[str, dict[str, Any]] = {}
        # Each ``memory`` document whose worker went: what its id answers from then on (``expired``).
        self.expired: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        from cadgen.engine.cache import Cache

        self.cache = Cache(self)

    def register(self, worker: Any, answer: dict) -> None:
        done = answer.get("done")
        reports = done.get("reports", []) if isinstance(done, dict) else done
        if not isinstance(reports, list):
            return
        program = answer.get("program")
        for root in reports:
            for report in [root, *(root.get("child_models") or {}).values()]:
                ident, source = report.get("id"), report.get("source")
                if not report.get("ok") or not ident or not source:
                    continue
                version = secrets.token_hex(8)  # this build's generation: a rebuild is a new one
                recorded = revision(report)
                try:
                    self.claimed(ident, source, report.get("key"))
                    self.record(report, program, recorded)
                except ValueError as error:  # a key another declaration holds: the build is refused, by name
                    report["ok"], report["error"] = False, f"{source['name']}: {error}"
                    root["ok"] = False
                    root.setdefault("error", report["error"])
                    continue
                with self.lock:
                    old = self.records.get(ident) or self.expired.pop(ident, None)
                    self.records[ident] = {"id": ident, "source": source, "worker": worker,
                                           "program": program or (old or {}).get("program") or source["script"],
                                           "store": report.get("store") or "pointer",
                                           "builtAt": time.time(), "version": version,
                                           "files": list(report.get("files") or {}), "revision": recorded,
                                           "read": [] if report.get("store") == "memory" else
                                           cache_reads(report.get("closure"))}
                self.daemon.builders[ident] = worker
                server = self.register_page(ident)
                report["url"] = self.url(server, ident)
                self.cache.touch(ident)

    # --- the registry ------------------------------------------------------------------------

    @staticmethod
    def registry() -> Any:
        from cadgen.engine import registry

        return registry.current()

    def claimed(self, ident: str, source: dict[str, Any], key: str | None) -> None:
        """``key`` (the id ``ident`` its declaration gives) taken by ``source``'s declaration
        (``script::name``); refused, naming the other, while another declaration whose script (or a
        shape's scope) is still there holds it -- in this process's book or in the registry. A
        declaration whose script is gone (moved) gives its key up. Nothing for a derived id: its
        declaration is in it."""
        if not key:
            return
        from cadgen.engine import registry as registering
        from cadgen.engine.ids import canonical

        mine = f"{canonical(source['script'])}::{source['name']}"
        with self.lock:
            row = self.records.get(ident)
        other = None
        if row is not None:
            other = (row["source"]["script"], row["source"]["name"])
        else:
            held = self.registry()
            record = held.get(ident) if held is not None else None
            if record is not None and record.get("kind") == "model":
                other = (str(registering.home(held, record)), record.get("entry") or "")
        if other is None or not os.path.exists(other[0]):
            return
        theirs = f"{canonical(other[0])}::{other[1]}"
        if theirs != mine:
            raise ValueError(f"key {key!r} is claimed by {theirs}, so {mine} cannot take it: one key names one "
                             "document; give one of them another key")

    def record(self, report: dict[str, Any], program: str | None, recorded: str) -> None:
        """The registry's record of a document a build made (``registry``), written when it changed.
        Nothing for a ``memory`` document, or with no registry."""
        from cadgen.engine import registry as registering

        held = self.registry()
        if held is None or report.get("store") == "memory":
            return
        ident, source = report["id"], report["source"]
        script = Path(source["script"])
        closure = report.get("closure") or {}
        old = held.get(ident) or {}
        main = Path(program or script)
        root = os.path.commonpath([str(script.parent), str(main.parent)]) if script.anchor == main.anchor else str(script.parent)
        home, run = registering.relative(script, root), ["python", registering.relative(main, root)]
        base = Path(root)
        rows = [[row[0], *([registering.relative(row[1], base)] if row[0] in ("file", "read") else
                           [row[1], registering.relative(row[2], base) if row[2] else None, row[3]]), row[-1]]
                for row in closure.get("inputs") or []]
        found: dict[str, Any] = {
            "id": ident, "kind": "model", "store": "pointer", "root": root, "home": home,
            "entry": source["name"], "label": source["name"], "run": run,
            "revision": recorded,
            "built": old["built"] if old.get("revision") == recorded and old.get("built") else time.time(),
            "closure": {"key": closure.get("key"),
                        "modules": [[registering.relative(path, base), digest] for path, digest in closure.get("modules") or []],
                        "inputs": rows},
            "runtime": runtime()}
        if report.get("key"):
            found["key"] = report["key"]
        for key in ("opened", "pinned", "preview", "cache"):  # the home's and the cache's, kept across builds
            if key in old:
                found[key] = old[key]
        held.put(found)

    def hand_over(self, request: dict[str, Any]) -> dict[str, Any]:
        """A shape a program handed over (``api.hand_over``): its document's bytes read through the
        documents worker -- checked, and made the structure the server serves -- then held as a
        drained document is (``server.keep``, and the cache), its page registered, and recorded with
        ``store: "shape"``: a program the engine did not run showed it, so nothing builds it again
        (``run`` empty). Refused (``ValueError``) for a key another declaration holds, or bytes that
        are no document. The answer carries its page."""
        import hashlib

        from cadgen.engine import registry as registering
        from cadgen.engine.ids import is_id

        ident, name, scope = str(request.get("id")), str(request.get("name")), str(request.get("scope"))
        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        source = {"script": scope, "name": name}
        self.claimed(ident, source, request.get("key"))
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
            self.expired.pop(ident, None)
            old = self.records.get(ident)
            self.records[ident] = {"id": ident, "source": source, "worker": None, "program": program,
                                   "store": "shape", "builtAt": time.time(), "version": version, "files": [],
                                   "revision": recorded, "read": []}
        if old is not None and old.get("worker") is not None and self.daemon.builders.get(ident) is old["worker"]:
            del self.daemon.builders[ident]
        held = self.registry()
        if held is not None:
            root = scope if os.path.isdir(scope) else str(Path(scope).parent)
            previous = held.get(ident) or {}
            found: dict[str, Any] = {
                "id": ident, "kind": "model", "store": "shape", "root": root,
                "home": registering.relative(scope, root), "entry": name, "label": name, "run": [],
                "shown": self.shown(program), "revision": recorded,
                "built": previous["built"] if previous.get("revision") == recorded and previous.get("built")
                else time.time(), "runtime": runtime()}
            if request.get("key"):
                found["key"] = request["key"]
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
        """The page of document ``ident`` on ``server``: ``/<id>``, with the token that lets it in."""
        app = getattr(server.http, "app", None)
        token = app.token if app is not None else ""
        return f"{server.url}/{ident}" + (f"?token={token}" if token else "")

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
        if record["store"] == "memory":
            return None  # out of the pool, its worker is going: the document goes with it
        return record if self.where(ident) else None

    def _working(self, worker: Any) -> bool:
        """Whether ``worker`` holds its documents still: live in the pool, or out of it and alive --
        being retired, and drained (``drain``) before it goes."""
        return worker is not None and (self.daemon.pool.holds(worker) or worker.alive())

    def rebuild(self, ident: str) -> dict[str, Any] | None:
        """What the engine knows of a model document it does not hold: its state (``evicted``,
        ``expired``), the command that builds it again -- the program that built it, run with
        ``python`` -- and why, in words (the page's ``error``). None for a document it holds or
        never built. The engine never runs the command."""
        self.adopt(ident)
        with self.lock:
            record = self.records.get(ident)
            gone = self.expired.get(ident)
        if record is not None and self.held(ident) is not None:
            return None
        if record is not None and record["store"] == "memory":
            gone = record  # its worker is going, or gone: expired, whether or not pruned yet
        found = record or gone
        if found is None:
            return self.recorded(ident)
        command = self.command(ident)
        name = found["source"]["name"]
        if found.get("store") == "shape":
            return {"error": f"{name} ({ident}) is no longer held: it is {self.shown(found.get('program'))}; run "
                             "that program again to hand it over again", "state": "evicted", "rebuild": None}
        if gone is None and not Path(found["source"]["script"]).is_file():
            return {"error": f"{name} ({ident}) is detached: {found['source']['script']} is gone, and nothing "
                             "builds it again; remove it from the home", "state": "detached", "rebuild": None}
        if gone is not None:
            text = (f"{name} ({ident}) expired with its worker: it is kept in memory only; "
                    f"run `{command}` to build it again")
            return {"error": text, "state": "expired", "rebuild": command}
        return {"error": f"{name} ({ident}) is no longer held: run `{command}` to build it again",
                "state": "evicted", "rebuild": command}

    def command(self, ident: str) -> str | None:
        """The command that builds model document ``ident`` again: ``python`` and the program that
        built it (else its script), from this process's book or the registry's record. None for an id
        the engine never built."""
        with self.lock:
            found = self.records.get(ident) or self.expired.get(ident)
        if found is None:
            known = self.recorded(ident)
            return known["rebuild"] if known is not None else None
        if found.get("store") == "shape":
            return None  # handed over by a program the engine did not run: nothing builds it again
        return f"python {shlex.quote(str(found.get('program') or found['source']['script']))}"

    def recorded(self, ident: str) -> dict[str, Any] | None:
        """What the registry knows of a model document this process never built (one built before a
        restart): ``evicted``, with the command that builds it again, or ``detached`` when its script
        is gone. None for an id it has no model's record of. Nothing is run."""
        from cadgen.engine import registry as registering

        held = self.registry()
        found = held.get(ident) if held is not None else None
        if found is None or found.get("kind") != "model":
            return None
        name = found.get("label") or found.get("entry") or ident
        if found.get("store") == "shape":
            return {"error": f"{name} ({ident}) is no longer held: it is {found.get('shown') or self.shown(None)}; "
                             "run that program again to hand it over again", "state": "evicted", "rebuild": None}
        if registering.detached(held, found):
            return {"error": f"{name} ({ident}) is detached: {registering.home(held, found)} is gone, and nothing "
                             "builds it again; remove it from the home", "state": "detached", "rebuild": None}
        command = registering.command(held, found)
        return {"error": f"{name} ({ident}) is no longer held: run `{command}` to build it again",
                "state": "evicted", "rebuild": command}

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
            return NotHeld(self.missing(ident), "evicted", None)
        return NotHeld(found["error"], found["state"], found["rebuild"])

    def drain(self, worker: Any) -> None:
        """Before ``worker`` is retired: every ``pointer`` document of it the server does not hold
        whole at its version is taken from it -- its ``result``, never meshed, with the whole
        document as xbf bytes (``document.to_bytes``, its animations' record with it) -- so it outlives
        the worker and answers every verb as an on-disk xbf does, and a GLB of it as the build's GLB. A
        worker that is gone (a crash) drains nothing: its documents the server lacks are evicted."""
        server = self.daemon.server
        if server is None or not worker.alive():
            return
        from cadgen.engine.daemon import WorkerGone

        with self.lock:
            owed = [(ident, row["version"], row["revision"]) for ident, row in self.records.items()
                    if row["worker"] is worker and row["store"] != "memory"]
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
            self.daemon.handle({**order, "env": worker.environment, "via": worker.script}, replies.append)
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
        first); a ``memory`` document is forgotten with its worker, and its id answers ``expired``."""
        with self.lock:
            for ident, row in list(self.records.items()):
                worker = row["worker"]
                if worker is None or worker.alive() or self.daemon.pool.holds(worker):
                    continue  # a worker out of the pool but alive is being retired: drained first
                if self.daemon.builders.get(ident) is worker:
                    del self.daemon.builders[ident]
                if row["store"] == "memory":
                    self.records.pop(ident)
                    self.expired[ident] = {key: row[key] for key in ("id", "source", "program", "store",
                                                                     "version", "builtAt")}
                    if self.daemon.server is not None:
                        self.daemon.server.forget_model(ident)
                else:
                    row["worker"] = None

    def listing(self, every: bool = False) -> list[dict[str, Any]]:
        """The model documents (``every``: those with declared files too, and the expired), each with
        its ``state`` (``STATES``) and, for one not held, the command that builds it again."""
        self.prune()
        for ident in self.cache.documents():  # what the cache holds, listed after a restart too
            self.adopt(ident)
        with self.lock:
            rows = [row for row in self.records.values() if every or not row["files"]]
            rows += list(self.expired.values()) if every else []
            found = []
            for row in rows:
                ident = row["id"]
                entry = {"id": ident, "script": row["source"]["script"],
                         "name": row["source"]["name"], "builtAt": row["builtAt"], "version": row["version"],
                         "store": row["store"], "state": self.state(ident)}
                if entry["state"] == "held":
                    entry["held"] = self.where(ident)
                lost = self.rebuild(ident) if entry["state"] in ("evicted", "expired", "detached") else None
                if lost is not None and lost["rebuild"]:
                    entry["rebuild"] = lost["rebuild"]
                found.append(entry)
            return found

    def state(self, ident: str) -> str:
        """``live`` (a live worker holds it), ``held`` (the server holds its bytes; no worker),
        ``building``, ``failed`` (its last build), ``evicted`` (neither: memory evicted its bytes,
        its worker crashed, or the engine restarted since: the registry knows it), ``expired`` (a
        ``memory`` document whose worker went), or ``detached`` (not held, and its script is gone).
        ``held`` is in memory, on disk -- the cache's -- or both (``where``)."""
        self.adopt(ident)
        with self.lock:
            if ident in self.expired:
                return "expired"
            record = self.records.get(ident)
        server = self.daemon.server
        build = server.build_of(ident) if server is not None else {}
        if build.get("building"):
            return "building"
        if build.get("failed"):
            return "failed"
        if record is None:
            known = self.recorded(ident)
            return known["state"] if known is not None else "evicted"
        if self._working(record["worker"]):
            return "live"
        if record["store"] == "memory":
            return "expired"
        if self.where(ident):
            return "held"
        if record["store"] == "shape":
            return "evicted"  # nothing builds it again, and nothing of it goes missing
        return "evicted" if Path(record["source"]["script"]).is_file() else "detached"

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
        if record is None or record["store"] == "memory":
            return None
        server = self.daemon.server
        memory = server is not None and server.has(ident, record["version"])
        disk = self.cache.current(ident, record.get("revision"))
        return "memory and disk" if memory and disk else "memory" if memory else "disk" if disk else None

    def on_disk(self, ident: str, revision: str | None) -> None:
        """The cache file of document ``ident`` is at ``revision`` now (None: gone): held in memory at
        that revision, it is read again from disk once evicted, in the budget's first tier."""
        server = self.daemon.server
        if server is None:
            return
        with self.lock:
            record = self.records.get(ident)
            version = record["version"] if record is not None and revision and record.get("revision") == revision else None
        if version is None:
            server.on_disk.pop(ident, None)
        else:
            server.on_disk[ident] = version

    def adopt(self, ident: str) -> None:
        """A model document this process never built whose cache file is there (after a restart),
        taken into the book from its record: held on disk, no worker, a generation of its own, its
        page registered where the server runs. Nothing is read but its record, nothing is run."""
        from cadgen.engine.ids import is_id

        if not is_id(ident):
            return
        with self.lock:
            if ident in self.records or ident in self.expired:
                return
        found = self.cache.found(ident)
        if found is None:
            return
        from cadgen.engine import registry as registering

        record, meta = found
        held = self.registry()
        root = held.root(record)
        program = registering.program(held, record)
        row = {"id": ident, "source": {"script": str(registering.home(held, record)), "name": record["entry"]},
               "worker": None, "program": str(program) if program else None, "store": record.get("store") or "pointer",
               "builtAt": record.get("built") or meta.get("written_at"), "version": secrets.token_hex(8),
               "files": [], "revision": meta["revision"],
               "read": [[kind, os.path.normpath(root / path), digest] for kind, path, digest in meta.get("read") or []]}
        with self.lock:
            if ident in self.records or ident in self.expired:
                return
            self.records[ident] = row
        if self.daemon.server is not None:
            self.register_page(ident)
            self.on_disk(ident, row["revision"])

    def attach(self, server: Any) -> None:
        """The daemon's server, started after documents were taken up from the cache: each is
        registered with it."""
        with self.lock:
            idle = [ident for ident, row in self.records.items() if row["worker"] is None and row["store"] != "memory"]
        for ident in idle:
            row = self.row(ident)
            if row is not None and self.cache.current(ident, row.get("revision")):
                server.register_model(ident, row["source"]["name"], lambda ident=ident: self.load(ident), row["version"])
                self.on_disk(ident, row["revision"])

    def in_use(self) -> set[str]:
        """The documents whose cache file the cache's bound never evicts: those a live worker holds,
        and those a page watches."""
        server = self.daemon.server
        with self.lock:
            live = {ident for ident, row in self.records.items() if self._working(row["worker"])}
        return live | (server.watched() if server is not None else set())

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
        data = self.cache.read(ident)
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
            raise ValueError(answer.get("failed") or f"{name} ({ident}): its cache file could not be read")
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

    def stale(self, ident: str) -> dict[str, Any] | None:
        """For a model document no worker holds: whether the code changed since it was built -- each
        file its build read compared with the file now (``cache.changes``) -- as ``{"text",
        "changes", "rebuild"}``; None when it is as built, or a worker holds it. Nothing reruns."""
        with self.lock:
            record = self.records.get(ident)
        if record is None or record["store"] == "memory" or self._working(record["worker"]):
            return None
        from cadgen.engine.cache import changes

        script = Path(record["source"]["script"])
        changed = changes(record.get("read") or [], script.parent)
        if not changed:
            return None
        command = self.command(ident)
        name = record["source"]["name"]
        return {"text": f"{name} ({ident}): the code changed since this was built ({', '.join(changed)}); "
                        f"run `{command}` to build it again", "changes": changed, "rebuild": command}
