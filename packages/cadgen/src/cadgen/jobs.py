"""In-memory operation lifecycle shared by viewer delivery and agent operations.

Subclasses own the work and its outputs. The queue owns admission, request identity,
progress, bounded waits and cancellation. It never imports a CAD kernel or saves a registry.
"""
from __future__ import annotations

import secrets
import threading
import time

TERMINAL = frozenset({"ready", "succeeded", "failed", "cancelled", "expired"})
STATUS_SECONDS = 86400
MAX_JOBS = 16


class JobError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Jobs:
    # External file writes cannot be undone by discarding a returned value.
    cancel_running = False

    def __init__(self, *, clock=time.time):
        self.clock = clock
        self.epoch = secrets.token_urlsafe(18)
        self.changed = threading.Condition(threading.RLock())
        self.jobs, self.requests = {}, {}
        self.executing = False
        self.touched = self.clock()

    def _prune(self):
        for ident, job in list(self.jobs.items()):
            if job["state"] in TERMINAL and self.clock() - job["finishedAt"] >= STATUS_SECONDS:
                self.jobs.pop(ident)

    def idle_seconds(self):
        with self.changed:
            return self.clock() - self.touched

    def keeps_alive(self):
        with self.changed:
            return any(job["state"] not in TERMINAL for job in self.jobs.values())

    def _submit(self, request_id, normalized, **fields):
        """Under changed's lock: retries join an existing request, never repeat work."""
        self._prune()
        previous = self.requests.get(request_id)
        if previous:
            job = self.jobs.get(previous)
            if job is None:
                raise JobError("This operation expired; use a new request ID to start again.", 410)
            if job["request"] != normalized:
                raise JobError("This request ID already names another operation.", 409)
            return self.public(job)
        if len(self.jobs) >= 128 or len(self.requests) >= 4096:
            raise JobError("Operation history is full for this session.", 429)
        if sum(j["state"] not in TERMINAL for j in self.jobs.values()) >= MAX_JOBS:
            raise JobError("The operation queue is full. Wait or cancel a queued operation.", 429)
        ident = secrets.token_urlsafe(18)
        job = {"id": ident, "requestId": request_id, "request": normalized,
               "state": "queued", "stage": "Waiting for worker", "sequence": 0,
               "createdAt": self.clock(), "finishedAt": 0, "cancel": False, **fields}
        self.jobs[ident], self.requests[request_id] = job, ident
        threading.Thread(target=self._execute, args=(job,), daemon=True, name="cadgen-operation").start()
        return self.public(job)

    def _change(self, job, **fields):
        self.touched = self.clock()
        job.update(fields)
        job["sequence"] += 1
        self.changed.notify_all()

    def _progress(self, job, frame):
        with self.changed:
            if not job["cancel"]:
                self._change(job, progress=frame, stage=frame.get("label", "Working"))

    def _execute(self, job):
        admitted = False
        try:
            with self.changed:
                self.changed.wait_for(lambda: job["cancel"] or (not self.executing and next(
                    (j for j in self.jobs.values() if j["state"] == "queued"), None) is job))
                if job["cancel"]:
                    return
                self.executing = admitted = True
                self._change(job, state="running", stage="Preparing operation")
            result = self._perform(job, lambda frame: self._progress(job, frame))
            with self.changed:
                if not job["cancel"]:
                    self._change(job, finishedAt=self.clock(), **result)
        except Exception as error:
            with self.changed:
                if not job["cancel"]:
                    self._change(job, state="failed", stage="Operation failed", error=str(error), finishedAt=self.clock(), **self._failure(job, error))
        finally:
            with self.changed:
                if job["cancel"]:
                    self._change(job, state="cancelled", stage="Operation cancelled", finishedAt=self.clock())
                try:
                    self._finished(job)
                finally:
                    if admitted:
                        self.executing = False
                    self.changed.notify_all()

    def _perform(self, job, progress):
        raise NotImplementedError

    def _failure(self, job, error):
        return {}

    def _finished(self, job):
        pass

    def public(self, job):
        fields = ("id", "requestId", "operation", "state", "stage", "sequence", "createdAt", "finishedAt",
                  "progress", "result", "error")
        return {**{k: job[k] for k in fields if k in job}, "epoch": self.epoch,
                "cancellable": job["state"] == "queued" or (self.cancel_running and job["state"] == "running")}

    def get(self, ident, after=None, wait=0):
        with self.changed:
            self._prune()
            job = self.jobs.get(ident)
            if job is None:
                raise JobError("Operation no longer exists; the server may have restarted.", 404)
            if after is not None and job["sequence"] == after and job["state"] not in TERMINAL:
                self.changed.wait_for(lambda: job["sequence"] != after, timeout=min(25, max(0, wait)))
            return self.public(job)

    def cancel(self, ident):
        with self.changed:
            self.get(ident)
            job = self.jobs[ident]
            if job["state"] not in TERMINAL:
                if job["state"] != "queued" and not self.cancel_running:
                    raise JobError("This operation is already running and may write requested outputs; it cannot be cancelled.", 409)
                job["cancel"] = True
                if job["state"] == "queued":
                    self._change(job, state="cancelled", stage="Operation cancelled", finishedAt=self.clock())
                else:
                    self._change(job, state="cancelling", stage="Cancelling after the current step")
            return self.public(job)
