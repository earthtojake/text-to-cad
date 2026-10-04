"""Artifact operations for a STATIC visualization tool.

The viewer's render path runs no generators: it renders what exists. Generation
belongs to model scripts and the doors. The one build-shaped thing the viewer
does is compiling a document whose bytes have no tree — making its tree current
in the shared store, which is exactly the cache action — and that is a compile
job in cadgen's pool (``compiles``), so the kernel never loads into the
long-lived server and a door compiling the same file is the same job.
"""

from __future__ import annotations

import os

from .artifact_status import (
    ARTIFACT_STATE,
    artifact_status as compute_artifact_status,
    owns_artifact_path,
    owns_step_path,
    resolve_artifact_verdict,
)
from .backend import absolute_path
from .build_progress import build_progress_snapshot
from .compiles import DocumentCompiler
from .store_paths import build_scope

__all__ = ["CadgenOps"]


class CadgenOps:
    def __init__(self, *, client=None) -> None:
        self.client = client if client is not None else DocumentCompiler()

    def shutdown(self) -> None:
        self.client.shutdown()

    # --- status -----------------------------------------------------------

    def artifact_status(self, file_ref) -> dict:
        candidate = absolute_path(file_ref)
        if not owns_artifact_path(candidate):
            # Not ours to have an opinion about: no disk read, no kernel.
            return {"state": ARTIFACT_STATE.COMPILED}

        build_key = build_scope(candidate)

        # The daemon's job ledger: any job with this document among its outputs,
        # whoever submitted it (a CLI build, a parent's child build, our compile).
        snapshot = build_progress_snapshot(candidate)
        if snapshot is None and self.client.in_flight(build_key):
            # Our own compile before the daemon lists it (or with no daemon at
            # all): an indeterminate compiling badge beats showing nothing, and
            # it is what the client's attach loop needs to attach TO.
            snapshot = {"writing": True, "busy": False, "runId": None, "progress": None}

        # Resolved once and threaded through both uses below.
        verdict = resolve_artifact_verdict(file_ref)
        status = compute_artifact_status(file_ref, snapshot=snapshot, verdict=verdict)
        if status.get("state") != ARTIFACT_STATE.NOT_COMPILED:
            return status

        # The one buildable state: a document with no tree for its bytes. The
        # viewer never asks who wrote it — a compile job builds the tree from
        # the bytes, whoever wrote them (STORE.md §2, §9).
        if verdict.get("rawStep"):
            # A compile of these very bytes already failed: say so, rather than offer it again.
            failure = self.client.failure(candidate)
            if failure is not None:
                answer = {"state": ARTIFACT_STATE.FAILED, "error": failure.get("error") or "Compiling the document failed."}
                if failure.get("errorType"):
                    answer["errorType"] = failure["errorType"]
                return answer
            # The compile offer is exactly three keys. It deliberately does
            # NOT carry `blocked` through from `status`.
            #
            # `blocked` is set by artifact_status when the snapshot says
            # `busy`, and NOTHING in this backend can say that: every
            # snapshot is minted by _snapshot_from_record or the synthetic
            # in-flight one, and both hardcode busy=False — as the Node
            # buildProgressSnapshot did before them. So the flag was
            # unreachable, and an unreachable flag that flips the client
            # from BUILD to ATTACH is a trap for the next reader, not a
            # safeguard. A compile already in flight for this document shows
            # as `compiling` above (its progress record, or our own
            # in-flight entry), which the client attaches to.
            #
            # busy/blocked stay in artifact_status.py: they are pinned there
            # by the ported spec, which supplies the snapshot directly.
            offer = {
                "state": ARTIFACT_STATE.NOT_COMPILED,
                "reason": status.get("reason"),
                "compile": True,
            }
            return offer
        return status

    # --- build ------------------------------------------------------------

    def build_artifact(self, file_ref, *, force: bool = False) -> dict:
        candidate = absolute_path(file_ref)
        if not owns_artifact_path(candidate):
            return {"ok": True, "state": ARTIFACT_STATE.COMPILED}

        if self._is_raw_step_file(candidate):
            # A job in the pool, started and left to run: this answers at once, and the
            # client follows the job through the status route (its progress, then
            # `compiled`, or `failed` with the job's BARE reason -- "failed to read STEP
            # file: ..." -- and the exception class apart, as `errorType`). A request
            # held for a compile's length would cost a host that relays requests
            # through a few shared slots one of them for that long.
            self.client.start(candidate, force=force)
            return {"ok": True, "state": ARTIFACT_STATE.COMPILING}
        return {"ok": False, "state": ARTIFACT_STATE.FAILED, "error": f"Artifact source not found: {file_ref}"}

    @staticmethod
    def _is_raw_step_file(candidate: str) -> bool:
        if not owns_step_path(candidate):
            return False
        try:
            return os.path.exists(candidate)
        except ValueError:
            return False
