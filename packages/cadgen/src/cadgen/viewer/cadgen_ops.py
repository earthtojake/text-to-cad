"""Artifact operations for a STATIC visualization tool.

The viewer's render path runs no generators: it renders what exists. Generation
belongs to model scripts and the doors. The one build-shaped thing the viewer
does is importing a raw FOREIGN ``.step`` — making its tree current in the
shared store, which is exactly the cache action — and that is a compile job in
cadgen's pool (``imports``), so the kernel never loads into the long-lived
server and a door importing the same file is the same job.
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
from .build_progress import ProgressRegistry, build_progress_snapshot
from .imports import ImportCompiler
from .store_paths import build_scope

__all__ = ["CadgenOps", "create_cadgen_ops"]


class CadgenOps:
    def __init__(self, root_dir: str, *, registry=None, client=None) -> None:
        # Resolved once. Containment compares this against every candidate, and
        # a root spelled relatively would make that comparison depend on the
        # process's current directory.
        self.root_dir = os.path.abspath(str(root_dir or ""))
        self.registry = registry if registry is not None else ProgressRegistry()
        self.client = client if client is not None else ImportCompiler()

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
            return {"state": ARTIFACT_STATE.READY}

        candidate = self._candidate(file_ref)
        build_key = build_scope(candidate)

        snapshot = build_progress_snapshot(candidate, registry=self.registry)
        if snapshot is None and self.client.in_flight(build_key):
            # Our worker is starting up but has not reported a phase yet. An
            # indeterminate generating badge beats showing nothing, and it is
            # what the client's attach loop needs in order to have something to
            # attach TO.
            snapshot = {"writing": True, "busy": False, "runId": None, "progress": None}

        # Resolved once and threaded through both uses below.
        verdict = resolve_artifact_verdict(file_ref, self.root_dir)
        status = compute_artifact_status(
            file_ref, self.root_dir, snapshot=snapshot, verdict=verdict
        )
        if status.get("state") != ARTIFACT_STATE.NEEDS_BUILD:
            return status

        # The one buildable state: a document with no tree for its bytes. The
        # viewer never asks who wrote it — a compile job builds the tree from
        # the bytes, generated or imported alike (STORE.md §2, §9).
        if verdict.get("rawStep"):
            # The import offer is exactly Node's three keys. It deliberately
            # does NOT carry `blocked` through from `status`.
            #
            # `blocked` is set by artifact_status when the snapshot says
            # `busy`, and NOTHING in this backend can say that: every
            # snapshot is minted by _snapshot_from_record or the synthetic
            # in-flight one, and both hardcode busy=False — as the Node
            # buildProgressSnapshot did before them. So the flag was
            # unreachable, and an unreachable flag that flips the client
            # from BUILD to ATTACH is a trap for the next reader, not a
            # safeguard. A compile already in flight for this document shows
            # as `generating` above (its progress record, or our own
            # in-flight entry), which the client attaches to.
            #
            # busy/blocked stay in artifact_status.py: they are pinned there
            # by the ported spec, which supplies the snapshot directly.
            return {
                "state": ARTIFACT_STATE.NEEDS_BUILD,
                "reason": status.get("reason"),
                "stepImport": True,
            }
        return status

    # --- build ------------------------------------------------------------

    def build_artifact(self, file_ref, *, force: bool = False) -> dict:
        if not owns_artifact_path(file_ref):
            return {"ok": True, "state": ARTIFACT_STATE.READY}

        candidate = self._candidate(file_ref)
        if self._is_raw_step_file(candidate):
            # A job in the pool: it waits for a slot there if it must, so this
            # request thread simply waits for the answer (a peer's request for
            # the same document attaches to the same job).
            imported = self.client.compile(candidate, force=force)
            if imported.get("ok"):
                # The compile payload is spread LAST, so its own ok/document
                # land on the wire and its ok wins.
                return {
                    "ok": True,
                    "state": ARTIFACT_STATE.READY,
                    "stepImport": True,
                    **imported,
                }
            # The human sentence carries the BARE message the compile reported —
            # "STEP import failed: failed to read STEP file: ...", which is what
            # the Node backend showed and what the import-failure card is
            # written for. The exception class, when there was one, rides as its
            # own field so a diagnostic can have it without the sentence
            # acquiring a "RuntimeError:" nobody asked for.
            failure = {
                "ok": False,
                "state": ARTIFACT_STATE.ERROR,
                "error": f"STEP import failed: {imported.get('error') or 'unknown error'}",
            }
            if imported.get("errorType"):
                failure["errorType"] = imported["errorType"]
            return failure
        return {"ok": False, "state": ARTIFACT_STATE.ERROR, "error": f"Artifact source not found: {file_ref}"}

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
