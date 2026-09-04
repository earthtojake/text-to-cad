"""THE artifact-status authority: freshness verdicts from pure file reads.

What this module deliberately does NOT decide is "is a build in flight". The
caller supplies a snapshot (``build_progress.py``: the daemon's job ledger,
matched to the document by declared output path) and this module reads it.

Nothing here imports cadgen. Status is answered for a directory of models by an
interpreter that may have no kernel installed at all, and every read degrades to
"no" rather than raising: a badge is not a render. The ONE exception is
containment — an out-of-root ``?file=`` ref raises before anything is read,
because that is a refusal rather than a missing file.

Freshness semantics:

* a tree must exist, parse, declare the exact kind, and have every component
  payload on disk;
* nothing else is gated. The tree KEY is ``<sha256(document)>-v<schema>``, so
  a tree that resolved at all has the right schema and belongs to exactly
  these bytes — the old schema, bake, and per-poll digest gates all collapsed
  into content keying, and that digest re-hash was the one full-file read every
  status poll used to pay;
* generated outputs are DETACHED from their source code: no source checks, ever;
* the viewer never learns whether a document was generated. Nothing here opens a
  record, a script or a closure (STORE.md §2, the law): status is artifact-side —
  not compiled / compiling / rendered / failed — and "is this document behind its
  source" is ``cadgen store why``'s question.
"""

from __future__ import annotations

import json
import os
import re

from .backend import require_contained
from .store_paths import component_object_present, result_descriptor, result_tree

__all__ = [
    "ARTIFACT_STATE",
    "BUILDABLE_CODES",
    "artifact_status",
    "owns_artifact_path",
    "owns_dxf_path",
    "owns_step_path",
    "resolve_artifact_verdict",
]

STEP_PACKAGE_KIND = "assembly-package"
STEP_DESCRIPTOR_NAME = "assembly.json"

# Artifacts only: model scripts are not status subjects.
#
# ``\Z``, never ``$``: Python's ``$`` also matches immediately BEFORE a trailing
# newline, where JavaScript's does not. With ``$`` here, ``part.step\n`` owned a
# status it must not own, so ``?file=<abs>.step%0A`` turned Node's "rendered" into
# a not-compiled carrying a compile offer for a document that does not exist.
# Same trap ``tess_cache.py`` names and avoids with ``fullmatch``; these two are
# the whole set of anchored patterns in the backend (``url_norm`` and
# ``scanner`` anchor only at the START, where the two languages agree), and
# neither is spelled ``$`` any more.
_STEP_ENTRY_RE = re.compile(r"\.(step|stp)\Z", re.IGNORECASE)


class ARTIFACT_STATE:  # noqa: N801 - a namespace of wire constants, not a class
    RENDERED = "rendered"
    COMPILING = "compiling"
    NOT_COMPILED = "not-compiled"
    FAILED = "failed"


# Codes the client may build on. ``missing_source_path`` and
# ``missing_dxf_output`` are unreachable from ``_validate_step`` today; the set
# stays literal so a future code lands in the right branch rather than falling
# through to the error arm.
BUILDABLE_CODES = frozenset(
    {
        "missing_glb",
        "missing_step_topology",
        "unsupported_step_topology",
        "missing_source_path",
        "missing_dxf_output",
    }
)


def _read_json(file_path):
    """Parse a JSON OBJECT, or ``None`` for anything else.

    Arrays are excluded here (unlike the sidecar-existence test in the scanner),
    matching ``!Array.isArray`` in the JS. Every read error is ``None``: the
    records tier is evictable and a missing marker must degrade, never raise.

    ``errors="replace"``, matching ``fs.readFileSync(path, "utf8")``, which
    substitutes U+FFFD rather than throwing. Strictness here was not a matter of
    taste: ``UnicodeDecodeError`` is a ``ValueError``, so one bad byte anywhere
    in a marker was swallowed as "absent" and the CLIENT'S STATE CHANGED — a
    rendered model reported not-compiled, offering to rebuild something already
    built. Node replaced the byte, parsed the JSON around it and answered ready.
    ``scanner.py`` already reads the same files with ``errors="replace"``, so
    strictness also put this backend in disagreement with itself about one file.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def owns_step_path(file_path) -> bool:
    return bool(_STEP_ENTRY_RE.search(str(file_path or "")))


def owns_dxf_path(file_path=None) -> bool:
    """Always false.

    Generated-DXF entries were ``.dxf.py`` scripts; scripts are no longer
    entries, and a plain ``.dxf`` renders directly with no artifact to manage.
    """
    return False


def owns_artifact_path(file_path) -> bool:
    """The entries whose render artifact the viewer reads from disk."""
    return owns_step_path(file_path) or owns_dxf_path(file_path)


def resolve_candidate(file_ref, root_dir) -> str | None:
    """An absolute path INSIDE ``root_dir`` that EXISTS, or ``None``.

    Backslashes become slashes before the absoluteness test, so on POSIX a
    Windows-shaped ``C:\\x`` becomes ``C:/x`` and is treated as relative.

    Containment is checked here and RAISES rather than answering ``None``,
    which is the one place this module departs from "every read degrades to no".
    It is not a read: an out-of-root ref is a refusal the route funnel turns
    into 403, exactly as the asset route already did, and answering ``None``
    would launder it into the far softer "Artifact source not found".
    """
    normalized = str(file_ref or "").strip().replace("\\", "/")
    if not normalized:
        return None
    if os.path.isabs(normalized):
        candidate = os.path.abspath(normalized)
    else:
        # ``lstrip("/")`` alone does not make a relative ref safe: "../.." still
        # walks out of the root once joined, which is why containment is
        # enforced on the RESULT rather than on the spelling.
        candidate = os.path.abspath(os.path.join(root_dir, normalized.lstrip("/")))
    require_contained(os.path.abspath(str(root_dir)), candidate)
    try:
        exists = os.path.exists(candidate)
    except ValueError:
        # A NUL byte in the path. Node's existsSync answers false rather than
        # throwing, and the caller turns that into "source not found".
        return None
    return candidate if exists else None


def _component_values(descriptor):
    """``Object.values(assembly.json.components)`` semantics.

    A JS array is ``typeof "object"`` too, so a list is accepted here exactly as
    the JS accepted it. cadgen never emits one; matching costs one branch.
    """
    components = descriptor.get("components")
    if isinstance(components, dict):
        return list(components.values())
    if isinstance(components, list):
        return list(components)
    return []


def _validate_step(step_path: str) -> dict:
    """The tree freshness verdict: a tree for these bytes, complete, or why not."""
    tree = result_tree(step_path)
    if tree is None:
        # No result for THESE bytes: never built, or its objects collected (the
        # lookup is by the bytes themselves, so an edited document simply misses).
        return {"ok": False, "code": "missing_glb", "tree": None}
    descriptor = result_descriptor(tree)
    if descriptor is None:
        return {
            "ok": False,
            "code": "missing_step_topology",
            "tree": tree,
        }
    if descriptor.get("kind") != STEP_PACKAGE_KIND:
        return {
            "ok": False,
            "code": "unsupported_step_topology",
            "tree": tree,
            "descriptor": descriptor,
        }
    components = _component_values(descriptor)
    if not components:
        return {
            "ok": False,
            "code": "missing_glb",
            "tree": tree,
            "descriptor": descriptor,
        }
    for component in components:
        surf = str((component or {}).get("surfObject") or "") if isinstance(component, dict) else ""
        if not surf or not component_object_present(surf):
            return {
                "ok": False,
                "code": "missing_glb",
                "tree": tree,
                "descriptor": descriptor,
            }
    return {"ok": True, "tree": tree, "descriptor": descriptor}


def resolve_artifact_verdict(file_ref, root_dir) -> dict:
    candidate = resolve_candidate(file_ref, root_dir)
    if candidate is None:
        return {"error": f"Artifact source not found: {file_ref}"}
    if owns_step_path(candidate):
        # rawStep is character-identical to the ownership test above, so it is
        # always true here. Kept because the compile gate reads it by name.
        return {"format": "step", "candidate": candidate, "rawStep": True, **_validate_step(candidate)}
    return {"error": f"No render-artifact format owns this entry: {file_ref}"}


def artifact_status(file_ref, root_dir, *, snapshot=None, verdict=None) -> dict:
    """The ``GET /__cad/artifact`` state machine.

    ``snapshot`` is the build view from the daemon's job ledger
    (``build_progress``) — ``{writing, busy, runId, progress}`` while a job with
    this document among its outputs runs, ``{failed: {...}}`` when the latest
    one failed — or ``None`` when there is none. Key PRESENCE is the contract:
    an absent ``runId`` or ``progress`` must be absent, never ``None``.

    ``verdict`` lets a caller that already resolved one pass it in: the route
    needs it again to decide whether to offer a compile.
    """
    if verdict is None:
        verdict = resolve_artifact_verdict(file_ref, root_dir)
    if verdict.get("error"):
        return {"state": ARTIFACT_STATE.FAILED, "error": verdict["error"]}

    snapshot = snapshot or {}
    # Checked BEFORE verdict.ok, so a build in flight over a currently
    # resolvable package reports compiling rather than rendered.
    if snapshot.get("writing"):
        status = {"state": ARTIFACT_STATE.COMPILING}
        if snapshot.get("runId"):
            status["runId"] = snapshot["runId"]
        if snapshot.get("progress") is not None:
            status["progress"] = snapshot["progress"]
        return status

    failed = snapshot.get("failed")
    if verdict.get("ok"):
        status = {"state": ARTIFACT_STATE.RENDERED}
        if isinstance(failed, dict):
            # The tree renders; the latest build of this document failed. Both
            # facts, the render first.
            status["failed"] = failed
        if snapshot.get("busy"):
            status["busy"] = True
            if snapshot.get("runId"):
                status["runId"] = snapshot["runId"]
            if snapshot.get("progress") is not None:
                status["progress"] = snapshot["progress"]
        return status

    code = verdict.get("code")
    if isinstance(failed, dict):
        # No tree for these bytes and the latest job for the document failed.
        # The reason is the job's own last word (the ledger keeps it); the
        # generic sentence is only for a ledger that has none.
        return {
            "state": ARTIFACT_STATE.FAILED,
            "reason": "build_failed",
            "error": str(failed.get("error") or "").strip() or "The last compile of this document failed.",
            "failed": failed,
        }
    if code in BUILDABLE_CODES:
        status = {"state": ARTIFACT_STATE.NOT_COMPILED, "reason": code}
        if snapshot.get("busy"):
            status["blocked"] = True
        return status

    # error and reason carry the same bare code string.
    return {"state": ARTIFACT_STATE.FAILED, "reason": code, "error": code}
