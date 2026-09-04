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
from .backend import require_contained
from .build_progress import build_progress_snapshot
from .compiles import DocumentCompiler
from .store_paths import build_scope

__all__ = ["CadgenOps", "create_cadgen_ops"]


class CadgenOps:
    def __init__(self, root_dir: str, *, client=None) -> None:
        # Resolved once. Containment compares this against every candidate, and
        # a root spelled relatively would make that comparison depend on the
        # process's current directory.
        self.root_dir = os.path.abspath(str(root_dir or ""))
        self.client = client if client is not None else DocumentCompiler()

    def shutdown(self) -> None:
        self.client.shutdown()

    def _candidate(self, file_ref) -> str:
        """The absolute path this ref names — refused if it leaves the root.

        The SAME containment rule the asset route enforces, and it belongs here
        as well as in ``resolve_candidate``: THIS is the value handed to
        ``client.compile``, and a check that inspects one string while the
        compile opens another is not a check. ``abspath`` collapses the dot
        segments so the path verified and the path used are one string.

        An absolute ref inside the root stays legal — the catalog absolutizes
        every entry's ``file`` and the client echoes that back — so what dies
        here is the absolute ref that lands OUTSIDE, which used to be compiled
        into the shared store and then read back, component by component,
        through ``/__cad/store``.
        """
        text = str(file_ref or "")
        candidate = os.path.abspath(
            text if os.path.isabs(text) else os.path.join(self.root_dir, text)
        )
        return require_contained(self.root_dir, candidate)

    # --- status -----------------------------------------------------------

    def artifact_status(self, file_ref) -> dict:
        if not owns_artifact_path(file_ref):
            # Not ours to have an opinion about: no candidate resolution, no
            # disk read, no kernel.
            return {"state": ARTIFACT_STATE.RENDERED}

        candidate = self._candidate(file_ref)
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
        verdict = resolve_artifact_verdict(file_ref, self.root_dir)
        status = compute_artifact_status(
            file_ref, self.root_dir, snapshot=snapshot, verdict=verdict
        )
        if status.get("state") != ARTIFACT_STATE.NOT_COMPILED:
            return status

        # The one buildable state: a document with no tree for its bytes. The
        # viewer never asks who wrote it — a compile job builds the tree from
        # the bytes, whoever wrote them (STORE.md §2, §9).
        if verdict.get("rawStep"):
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
            return {
                "state": ARTIFACT_STATE.NOT_COMPILED,
                "reason": status.get("reason"),
                "compile": True,
            }
        return status

    # --- build ------------------------------------------------------------

    def build_artifact(self, file_ref, *, force: bool = False) -> dict:
        if not owns_artifact_path(file_ref):
            return {"ok": True, "state": ARTIFACT_STATE.RENDERED}

        candidate = self._candidate(file_ref)
        if self._is_raw_step_file(candidate):
            # A job in the pool: it waits for a slot there if it must, so this
            # request thread simply waits for the answer (a peer's request for
            # the same document attaches to the same job).
            compiled = self.client.compile(candidate, force=force)
            if compiled.get("ok"):
                # The compile payload is spread LAST, so its own ok/document
                # land on the wire and its ok wins.
                return {
                    "ok": True,
                    "state": ARTIFACT_STATE.RENDERED,
                    "compiled": True,
                    **compiled,
                }
            # `error` is the BARE reason the compile job reported — "failed to
            # read STEP file: ..." — with no prefix: the client puts it under
            # its own title. The exception class, when there was one, rides as
            # its own field so a diagnostic can have it without the sentence
            # acquiring a "RuntimeError:" nobody asked for.
            failure = {
                "ok": False,
                "state": ARTIFACT_STATE.FAILED,
                "error": compiled.get("error") or "Compiling the document failed.",
            }
            if compiled.get("errorType"):
                failure["errorType"] = compiled["errorType"]
            return failure
        return {"ok": False, "state": ARTIFACT_STATE.FAILED, "error": f"Artifact source not found: {file_ref}"}

    @staticmethod
    def _is_raw_step_file(candidate: str) -> bool:
        if not owns_step_path(candidate):
            return False
        try:
            return os.path.exists(candidate)
        except ValueError:
            return False


def create_cadgen_ops(root_dir: str, **kwargs) -> CadgenOps:
    return CadgenOps(root_dir, **kwargs)
