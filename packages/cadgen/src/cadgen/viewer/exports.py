"""Session-owned, in-memory export jobs and explicitly requested temporary downloads.

No native save dialog: the destination is chosen on the browser's computer. Kernel
work goes through the engine worker. Disconnecting a request never cancels a job.

An artifact is deleted as soon as the browser has fetched it whole (the server saw its GET
end), and one nobody fetches within ``ARTIFACT_SECONDS`` (ten minutes) is deleted then; either
way its job is ``expired`` (``fetched`` says which), and the page offers to export it again. A
job's record lives as long as the engine that ran it -- the page session -- bounded by the
history, never by a day.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

FORMATS = {"step": ".step", "glb": ".glb", "stl": ".stl", "threemf": ".3mf", "dxf": ".dxf", "xbf": ".xbf", "original": ".xbf"}
from cadgen.jobs import Jobs, JobError as ExportError, STATUS_SECONDS, MAX_JOBS, TERMINAL

ARTIFACT_SECONDS = 600
MAX_RETAINED_BYTES = 4 * 1024**3
def specification(payload):
    # The document as its code built it: no part, no pose (the law of options).
    if not isinstance(payload, dict) or set(payload) != {"doc", "revision"}:
        raise ExportError("Export source is {doc, revision}.")
    if not all(isinstance(payload.get(k), str) and payload[k] for k in ("doc", "revision")):
        raise ExportError("Export requires the displayed document and revision.")
    return {"doc": payload["doc"], "revision": payload["revision"]}


class ExportJobs(Jobs):
    cancel_running = True

    def __init__(self, server, *, run=None, clock=time.time, root=None):
        self.server, self.clock = server, clock
        super().__init__(clock=clock)
        self.inspections = {}
        self.root = Path(root) if root else None
        self.run = run or self._worker
        self.started = False

    def _maintenance(self):
        # Crash recovery has no persistent job registry. Reap only this service's private
        # directories after a full day; living owners refresh their directory timestamp.
        for directory in (self.root or Path(tempfile.gettempdir())).glob("cadgen-download-*"):
            try:
                if directory.is_dir() and not directory.is_symlink() and time.time() - directory.stat().st_mtime > STATUS_SECONDS:
                    shutil.rmtree(directory)
            except OSError:
                pass
        while True:
            with self.changed:
                self.changed.wait(timeout=30)
                self._prune()
                for job in self.jobs.values():
                    if job["directory"]:
                        try:
                            os.utime(job["directory"], None)
                        except OSError:
                            pass
                active = any(j["state"] not in TERMINAL for j in self.jobs.values())
                active = active or any(not row["done"] for row in self.inspections.values())
            if active:
                self.server.touch()
            else:
                # Only run a janitor while this session owns anything.
                with self.changed:
                    if not self.jobs and not self.inspections:
                        self.started = False
                        return

    def keeps_alive(self):
        with self.changed:
            self._prune()
            return (any(job["state"] not in TERMINAL or job["state"] == "ready" for job in self.jobs.values())
                    or any(not row["done"] for row in self.inspections.values()))

    def _start(self):
        if not self.started:
            self.started = True
            threading.Thread(target=self._maintenance, daemon=True, name="cadgen-export-cleanup").start()

    def _prune(self):
        now = self.clock()
        for ident, job in list(self.jobs.items()):
            if job["state"] == "ready" and (job.get("fetched") or now >= job["expiresAt"]) and not job["readers"]:
                self._remove(job)
                self._change(job, state="expired", stage="Export downloaded" if job.get("fetched") else "Export expired")
        for key, row in list(self.inspections.items()):
            if row["done"] and now - row["at"] > 30:
                self.inspections.pop(key)

    def _source(self, spec):
        if self.server is None:
            raise ExportError("This host does not serve exportable documents.")
        from cadgen.engine.export import MESHES

        if Path(spec["doc"]).suffix.lower() in MESHES:
            return self._mesh_source(spec)
        with self.server.load_lock:
            doc = self.server.served.get(spec["doc"])
            if doc is None or doc.version != spec["revision"]:
                raise ExportError("The source changed. Open Export again to use the displayed revision.", 409)
            path, digest = str(doc.path), doc.structure.get("exportRevision")
            label = str(doc.structure.get("name") or "")
        from cadgen.engine.ids import is_id

        if is_id(path):
            # A document known by its id alone (a model's) is exported from what the engine holds,
            # never built again (``Daemon.document``).
            if not digest:
                raise ExportError("Reopen this model before exporting.", 409)
            source, expected = {"id": path}, {"digest": digest, "id": path, "modelRevision": spec["revision"]}
            return source, expected, label or "export"
        return {"path": path}, {"version": spec["revision"]}, Path(path).stem

    @staticmethod
    def _mesh_source(spec):
        """A mesh file the page shows (``doc`` its absolute path, ``revision`` the catalog's hash of
        the bytes on screen), exported to the other mesh kinds from the file as it is now: refused
        when its bytes are not the ones shown, and by the worker when it changes after this check
        (``{"version": "<mtime_ns>-<size>"}``, ``export/viewer.check``)."""
        from cadgen.viewer.scanner import _file_stats, _sha256_file, is_served_cad_asset

        path = Path(spec["doc"])
        stat = _file_stats(str(path)) if path.is_absolute() and is_served_cad_asset(str(path)) else None
        if stat is None or _sha256_file(str(path), stat) != spec["revision"]:
            raise ExportError("The source changed. Open Export again to use the displayed revision.", 409)
        return {"path": str(path)}, {"version": f"{stat.st_mtime_ns}-{stat.st_size}"}, path.stem

    def _worker(self, spec, target, progress):
        from cadgen.engine.client import request

        source, expected, _name = self._source(spec)
        answer = request({"op": "export", "source": source, "expected": expected,
                          "destinations": [str(target)] if target else [], "inspect": target is None,
                          "original": spec.get("format") == "original"}, on_progress=progress)
        if not answer or "failed" in answer:
            raise ExportError((answer or {}).get("failed", "The export worker disconnected."))
        return answer["done"]

    def options(self, payload):
        spec = specification(payload)
        key = json.dumps(spec, sort_keys=True)
        with self.changed:
            self._prune()
            row = self.inspections.get(key)
            if row is None:
                if sum(not r["done"] for r in self.inspections.values()) >= MAX_JOBS:
                    raise ExportError("Already checking formats. Try again shortly.", 429)
                row = self.inspections[key] = {"done": False, "at": self.clock()}
                self._start()
                threading.Thread(target=self._inspect, args=(row, spec), daemon=True).start()
            if not row["done"]:
                return 202, {"state": "checking", "retryMs": 500}
            if "error" in row:
                raise ExportError(row["error"], 409)
            return 200, {"epoch": self.epoch, "formats": row["formats"]}

    def _inspect(self, row, spec):
        try:
            formats = self.run(spec, None, lambda _p: None)["formats"]
            with self.changed:
                row["formats"] = formats
        except Exception as error:
            with self.changed:
                row["error"] = str(error)
        finally:
            with self.changed:
                row.update(done=True, at=self.clock())
                self.changed.notify_all()

    def create(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"requestId", "epoch", "source", "format"}:
            raise ExportError("Export requires requestId, epoch, source and format.")
        spec = specification(payload["source"])
        kind, request_id = payload["format"], payload["requestId"]
        if not isinstance(kind, str) or kind not in FORMATS or not isinstance(request_id, str) or not re.fullmatch(r"[\w-]{16,100}", request_id):
            raise ExportError("Invalid export format or request identity.")
        if payload["epoch"] != self.epoch:
            raise ExportError("The export session restarted. Open Export again.", 409)
        normalized = json.dumps(payload, sort_keys=True)
        with self.changed:
            self._prune()
            if request_id in self.requests:
                return self._submit(request_id, normalized)
            if sum(j.get("bytes", 0) for j in self.jobs.values() if j["state"] == "ready") >= MAX_RETAINED_BYTES:
                raise ExportError("Export storage is full. Release a previous export first.", 429)
            # A released, expired, failed or cancelled job holds no file: past the history bound
            # it is forgotten (its request ID stays a tombstone), so the session keeps exporting.
            for ident in [i for i, j in self.jobs.items() if j["state"] in TERMINAL and not j["directory"] and not j["readers"]]:
                if len(self.jobs) < 128:
                    break
                self.jobs.pop(ident)
            self._start()
            spec["format"] = kind
            return self._submit(request_id, normalized, spec=spec, expiresAt=0, readers=0,
                                directory=None, filename="export" + FORMATS[kind])

    def _perform(self, job, progress):
        _source, _expected, name = self._source(job["spec"])
        stem = (re.sub(r"[^\w .-]", "_", name)[:100].strip(" .") or "export")
        filename = stem + FORMATS[job["spec"]["format"]]
        directory = Path(tempfile.mkdtemp(prefix="cadgen-download-", dir=self.root))
        with self.changed:
            job["directory"] = directory
            self._change(job, filename=filename, stage="Preparing export")
            if job["cancel"]:
                return {}
        target = directory / filename
        self.run(job["spec"], target, progress)
        with self.changed:
            if job["cancel"]:
                return {}
            size = target.stat().st_size
            retained = sum(j.get("bytes", 0) for j in self.jobs.values() if j["state"] == "ready")
            if size + retained > MAX_RETAINED_BYTES:
                raise ExportError("Export exceeded the temporary storage limit.")
            return {"state": "ready", "stage": "Ready to save", "bytes": size,
                    "expiresAt": self.clock() + ARTIFACT_SECONDS}

    def _progress(self, job, frame):
        super()._progress(job, {**frame, "label": "Writing " + job["filename"]})

    def _finished(self, job):
        if job["state"] != "ready":
            self._remove(job)

    def close(self):
        """The engine is stopping: no artifact outlives the process that manages it."""
        with self.changed:
            for job in self.jobs.values():
                job["cancel"] = job["cancel"] or job["state"] not in TERMINAL
                self._remove(job)
                if job["state"] == "ready":
                    self._change(job, state="expired", stage="Export expired")
            self.changed.notify_all()

    def _remove(self, job):
        if job["directory"]:
            shutil.rmtree(job["directory"], ignore_errors=True)
            job["directory"] = None

    def public(self, job):
        fields = ("id", "requestId", "filename", "state", "stage", "sequence", "createdAt", "finishedAt", "expiresAt", "bytes",
                  "error", "fetched")
        return {**{k: job[k] for k in fields if k in job}, "epoch": self.epoch}

    def release(self, ident):
        with self.changed:
            self.get(ident)
            job = self.jobs[ident]
            if job["state"] not in TERMINAL:
                raise ExportError("Cancel this export before releasing it.", 409)
            job["expiresAt"] = 0
            self._prune()
            return self.public(job)

    def get(self, ident, after=None, wait=0):
        """A job's state; asked ``after`` its sequence, the answer waits for the next change, an
        unfinished job's as a ready one's, whose file going (fetched, or past its window) is what
        turns the page's Download again into Export again."""
        with self.changed:
            self._prune()
            job = self.jobs.get(ident)
            if job is not None and after is not None and job["sequence"] == after and job["state"] == "ready":
                self.changed.wait_for(lambda: job["sequence"] != after, timeout=min(25, max(0, wait)))
                return super().get(ident)
            return super().get(ident, after, wait)

    def fetched(self, ident):
        """The browser has the whole file: it is deleted now, its job expired as ``fetched``."""
        with self.changed:
            job = self.jobs.get(ident)
            if job is not None and job["state"] == "ready":
                job["fetched"] = True
                self._prune()

    @contextlib.contextmanager
    def artifact(self, ident):
        with self.changed:
            self.get(ident)
            job = self.jobs[ident]
            if job["state"] != "ready":
                raise ExportError("Export is not available for download.", 410 if job["state"] == "expired" else 409)
            job["readers"] += 1
            path = job["directory"] / job["filename"]
        try:
            yield path
        finally:
            with self.changed:
                job["readers"] -= 1
                self._prune()

    def handle(self, request, response):
        try:
            tail = request.path.removeprefix("/__cad/exports").strip("/").split("/")
            if request.method == "POST":
                if int(request.header("content-length") or 0) > 65536:
                    raise ExportError("Export request too large.", 413)
                if tail == ["options"]:
                    status, body = self.options(json.loads(request.body()))
                    return response.send_json(status, body)
                if tail == [""]:
                    return response.send_json(202, self.create(json.loads(request.body())))
                if len(tail) == 2 and tail[1] in ("cancel", "release"):
                    return response.send_json(200, getattr(self, tail[1])(tail[0]))
            elif request.method == "GET":
                if len(tail) == 1:
                    after = request.query.get("after")
                    return response.send_json(200, self.get(tail[0], int(after) if after is not None else None,
                                                           float(request.query.get("wait") or 0)))
                if len(tail) == 2 and tail[1] == "file":
                    with self.artifact(tail[0]) as path:
                        from urllib.parse import quote
                        # A plain browser download: every browser names it, the ASCII form for any
                        # that ignores RFC 5987 (the page's link names it too, with `download`).
                        plain = re.sub(r"[^ -~]", "_", path.name).replace('"', "_").replace("\\", "_")
                        response.stream_file(path, path.stat(), "application/octet-stream", [
                            ("content-disposition", f'attachment; filename="{plain}"; filename*=UTF-8\'\'{quote(path.name)}'),
                            ("x-content-type-options", "nosniff")])
                    # The whole file reached the browser -- no range, and the page did not hang up
                    # part way -- so it is deleted at once; a broken transfer keeps it for a retry.
                    whole = not (request.header("range") if hasattr(request, "header") else "")
                    if whole and getattr(response, "gone", False) is not True and request.method == "GET":
                        self.fetched(tail[0])
                    return None
            raise ExportError("Export route not found.", 404)
        except (ValueError, OSError) as error:
            response.send_json(getattr(error, "status", 400), {"error": str(error)})
