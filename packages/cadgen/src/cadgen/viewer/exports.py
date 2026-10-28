"""Session-owned, in-memory export jobs and explicitly requested temporary downloads.

No native save dialog: the destination is chosen on the browser's computer. Kernel
work goes through the engine worker. Disconnecting a request never cancels a job. Nothing is
inspected before a job: the page offers the formats a file's kind writes, and a job the engine
cannot write fails, saying why.

An artifact is deleted as soon as the browser has fetched it whole (the server saw its GET
end), and one nobody fetches within ``ARTIFACT_SECONDS`` (ten minutes) is deleted then; either
way its job is ``expired`` (``fetched`` says which), and the page offers to export it again. A
job's record lives as long as the engine that ran it -- the page session -- bounded by the
history, never by a day.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid
from pathlib import Path

FORMATS = {"step": ".step", "glb": ".glb", "stl": ".stl", "threemf": ".3mf", "dxf": ".dxf", "xbf": ".xbf", "original": ".xbf"}
from cadgen.jobs import Jobs, JobError as ExportError, STATUS_SECONDS, TERMINAL

ARTIFACT_SECONDS = 600
MAX_RETAINED_BYTES = 4 * 1024**3
MAX_OBSERVATION_BYTES = 1024**3
_OBSERVATION_EXTENSIONS = frozenset({".xbf", ".step", ".stp", ".glb", ".stl", ".3mf", ".dxf"})
def specification(payload):
    # The document as its code built it: no part, no pose (the law of options).
    if not isinstance(payload, dict) or set(payload) != {"doc", "revision"}:
        raise ExportError("Export source is {doc, revision}.")
    if not all(isinstance(payload.get(k), str) and payload[k] for k in ("doc", "revision")):
        raise ExportError("Export requires the displayed document and revision.")
    return {"doc": payload["doc"], "revision": payload["revision"]}


class ExportJobs(Jobs):
    def __init__(self, server, *, run=None, clock=time.time, root=None):
        self.server, self.clock = server, clock
        super().__init__(clock=clock)
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
            if active:
                if self.server is not None:
                    self.server.touch()
            else:
                # Only run a janitor while this session owns anything.
                with self.changed:
                    if not self.jobs:
                        self.started = False
                        return

    def keeps_alive(self):
        with self.changed:
            self._prune()
            return any(job["state"] not in TERMINAL or job["state"] == "ready" for job in self.jobs.values())

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
        answer = request({"op": "export", "source": source, "expected": expected, "destinations": [str(target)],
                          "original": spec.get("format") == "original"}, on_progress=progress)
        if not answer or "failed" in answer:
            raise ExportError((answer or {}).get("failed", "The export worker disconnected."))
        return answer["done"]

    def create(self, payload, *, _capture_file=False):
        if not isinstance(payload, dict) or set(payload) != {"requestId", "epoch", "source", "format"}:
            raise ExportError("Export requires requestId, epoch, source and format.")
        spec = specification(payload["source"])
        kind, request_id = payload["format"], payload["requestId"]
        if not isinstance(kind, str) or kind not in FORMATS or not isinstance(request_id, str) or not re.fullmatch(r"[\w-]{16,100}", request_id):
            raise ExportError("Invalid export format or request identity.")
        if payload["epoch"] != self.epoch:
            raise ExportError("The export session restarted. Open Export again.", 409)
        normalized = json.dumps({**payload, **({"captureFile": True} if _capture_file else {})}, sort_keys=True)
        with self.changed:
            self._prune()
            if request_id in self.requests:
                return self._submit(request_id, normalized)
            if sum(j.get("bytes", 0) for j in self.jobs.values() if j["state"] == "ready") >= MAX_RETAINED_BYTES:
                raise ExportError("Export storage is full. Download the exports waiting first.", 429)
            # An expired, failed or cancelled job holds no file: past the history bound
            # it is forgotten (its request ID stays a tombstone), so the session keeps exporting.
            for ident in [i for i, j in self.jobs.items() if j["state"] in TERMINAL and not j["directory"] and not j["readers"]]:
                if len(self.jobs) < 128:
                    break
                self.jobs.pop(ident)
            self._start()
            spec["format"] = kind
            if _capture_file:
                spec["captureFile"] = True
            return self._submit(request_id, normalized, spec=spec, expiresAt=0, readers=0,
                                directory=None, filename="export" + FORMATS[kind])

    def _perform(self, job, progress):
        spec = job["spec"]
        name = Path(spec["doc"]).stem if spec.get("captureFile") else self._source(spec)[2]
        stem = (re.sub(r"[^\w .-]", "_", name)[:100].strip(" .") or "export")
        extension = Path(spec["doc"]).suffix.lower() if spec.get("captureFile") else FORMATS[spec["format"]]
        filename = stem + extension
        directory = Path(tempfile.mkdtemp(prefix="cadgen-download-", dir=self.root))
        with self.changed:
            job["directory"] = directory
            self._change(job, filename=filename, stage="Preparing export")
            if job["cancel"]:
                return {}
        target = directory / filename
        if spec.get("captureFile"):
            self._copy_observation(spec, target)
        else:
            self.run(spec, target, progress)
        with self.changed:
            if job["cancel"]:
                return {}
            size = target.stat().st_size
            retained = sum(j.get("bytes", 0) for j in self.jobs.values() if j["state"] == "ready")
            if size + retained > MAX_RETAINED_BYTES:
                raise ExportError("Export exceeded the temporary storage limit.")
            return {"state": "ready", "stage": "Ready to save", "bytes": size,
                    "expiresAt": self.clock() + ARTIFACT_SECONDS}

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

    @staticmethod
    def _copy_observation(spec, target):
        source = Path(spec["doc"])
        if not source.is_absolute() or source.suffix.lower() not in _OBSERVATION_EXTENSIONS:
            raise ExportError("This CAD format cannot be preserved as a standalone observation.")
        digest = hashlib.sha256()
        with source.open("rb") as incoming, target.open("xb") as output:
            before = os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_OBSERVATION_BYTES:
                raise ExportError("The CAD observation is too large to preserve.")
            size = 0
            while chunk := incoming.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_OBSERVATION_BYTES:
                    raise ExportError("The CAD observation is too large to preserve.")
                digest.update(chunk)
                output.write(chunk)
            after = os.fstat(incoming.fileno())
        if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or digest.hexdigest() != spec["revision"]):
            raise ExportError("The selected CAD revision changed before it could be preserved.", 409)
        if source.suffix.lower() == ".glb":
            from cadgen._internal.primitive_mesh import GLB_MAGIC, GLB_JSON_CHUNK
            with target.open("rb") as incoming:
                header = incoming.read(20)
                if (len(header) != 20 or int.from_bytes(header[:4], "little") != GLB_MAGIC
                        or int.from_bytes(header[16:20], "little") != GLB_JSON_CHUNK):
                    raise ExportError("The GLB document has no readable scene.")
                length = int.from_bytes(header[12:16], "little")
                if length > 16 * 1024**2 or length + 20 > size:
                    raise ExportError("The GLB scene is too large to preserve.")
                scene = json.loads(incoming.read(length))
            from cadgen.engine.formats.glb import require_self_contained
            from cadgen.engine.formats import FormatError
            try:
                require_self_contained(target, scene)
            except FormatError as error:
                raise ExportError("This GLB references external files. Export a self-contained GLB to preserve it in history.") from error
        elif source.suffix.lower() == ".dxf":
            import ezdxf
            drawing = ezdxf.readfile(target)
            if any(block.block.dxf.flags & 12 for block in drawing.blocks) or drawing.objects.query("IMAGEDEF"):
                raise ExportError("This DXF references external files. Export a standalone document to preserve it in history.")

    def capture(self, source, *, copy_file=False):
        """Freeze a selected revision before handing its temporary artifact to a history-owning host."""
        job = self.create({"requestId": uuid.uuid4().hex, "epoch": self.epoch,
                           "source": source, "format": "xbf"}, _capture_file=copy_file)
        try:
            deadline = time.monotonic() + 180
            while job["state"] in ("queued", "running"):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise ExportError("The saved observation export did not finish in time.")
                job = self.get(job["id"], after=job["sequence"], wait=min(25, left))
            if job["state"] != "ready":
                raise ExportError(job.get("error") or "The saved observation export failed.")
            with self.artifact(job["id"]) as artifact:
                size = artifact.stat().st_size
                if size > MAX_OBSERVATION_BYTES:
                    raise ExportError("The CAD observation is too large to preserve.")
                with artifact.open("rb") as incoming:
                    digest = hashlib.file_digest(incoming, "sha256").hexdigest()
                return {"version": 1, "file": str(artifact), "format": artifact.suffix[1:].lower(),
                        "sha256": digest, "sizeBytes": size, "source": source["doc"], "revision": source["revision"]}
        except BaseException:
            with self.changed:
                owned = self.jobs[job["id"]]
                if owned["state"] in TERMINAL:
                    self._remove(owned)
                    if owned["state"] == "ready":
                        self._change(owned, state="expired", stage="Observation discarded")
                else:
                    owned["cancel"] = True
                self.changed.notify_all()
            raise

    @contextlib.contextmanager
    def artifact(self, ident):
        with self.changed:
            self.get(ident)
            job = self.jobs[ident]
            # Fetched whole or past its window, it is gone to a new reader at once, though
            # its file stays until an earlier download still finishing lets go of it (``_prune``).
            going = job["state"] == "ready" and (job.get("fetched") or self.clock() >= job["expiresAt"])
            if job["state"] != "ready" or going:
                raise ExportError("Export is not available for download.",
                                  410 if going or job["state"] == "expired" else 409)
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
                if tail == [""]:
                    return response.send_json(202, self.create(json.loads(request.body())))
            elif request.method == "GET":
                if tail == [""]:
                    # The session's epoch, which a new request names (``create``): a request a page
                    # kept across a reload is refused once this server has gone, never run again.
                    return response.send_json(200, {"epoch": self.epoch})
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
