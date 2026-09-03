"""THE artifact-status authority: freshness verdicts from pure file reads.

What this module deliberately does NOT decide is "is a build in flight". That
is kernel lock state (fcntl flock), and it must never be re-inferred from pids,
heartbeats, or age windows — see ``cadgen/coordination/lock.py`` for the
measured failure modes of that design. The caller supplies a snapshot
(``build_progress.py``) and this module reads it.

Nothing here imports cadgen. Status is answered for a directory of models by an
interpreter that may have no kernel installed at all, and every read degrades to
"no" rather than raising: a badge is not a render. The ONE exception is
containment — an out-of-root ``?file=`` ref raises before anything is read,
because that is a refusal rather than a missing file.

Freshness semantics:

* a package must exist, parse, declare the exact kind, and have every component
  payload on disk;
* nothing else is gated. The package KEY is ``<sha256(document)>-v<schema>``, so
  a package that resolved at all has the right schema and belongs to exactly
  these bytes — the old schema, bake, and per-poll digest gates all collapsed
  into content keying, and that digest re-hash was the one full-file read every
  status poll used to pay;
* generated outputs are DETACHED from their source code: no source checks, ever.
"""

from __future__ import annotations

import json
import os
import re

from .backend import require_contained
from .store_paths import (
    SOURCE_SIDECAR_SCHEMA_VERSION,
    render_package_dir,
    source_provenance_record_path,
    source_sidecar_path,
)

__all__ = [
    "ARTIFACT_STATE",
    "BUILDABLE_CODES",
    "artifact_status",
    "is_generated_document",
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
# status it must not own, so ``?file=<abs>.step%0A`` turned Node's "ready" into
# a needs-build carrying an import offer for a document that does not exist.
# Same trap ``tess_cache.py`` names and avoids with ``fullmatch``; these two are
# the whole set of anchored patterns in the backend (``url_norm`` and
# ``scanner`` anchor only at the START, where the two languages agree), and
# neither is spelled ``$`` any more.
_STEP_ENTRY_RE = re.compile(r"\.(step|stp)\Z", re.IGNORECASE)


class ARTIFACT_STATE:  # noqa: N801 - a namespace of wire constants, not a class
    READY = "ready"
    GENERATING = "generating"
    NEEDS_BUILD = "needs-build"
    ERROR = "error"


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
    ready model reported needs-build, offering to rebuild something already
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


def is_generated_document(step_path) -> bool:
    """Was this document GENERATED (a declaration owns it) or IMPORTED?

    This answers EXACTLY ONE question, and it is not a display question: may the
    viewer compile this document? Nothing about how a file came to exist reaches
    the catalog, the file explorer, or any status card — a generated model and
    an imported one are the same kind of thing to look at.

    The gate exists because the compile door is not neutral about generated
    documents: it calls ``require_current_document``, which re-hashes a
    generated model's recorded source closure and REFUSES a document that is
    stale relative to its script. Routing generated documents through it would
    make the viewer's ability to render depend on source code it must never
    consult — the tie that "generated outputs are detached" forbids. Imports are
    foreign files with no closure to check, so the door is safe for exactly the
    documents this predicate says no to.

    The AUTHORITY is the provenance record, which every generated build writes.
    That tier is evictable (``cadgen cache gc`` sweeps it), so "no record" is a
    routine state and costs one offer to compile a document the door may then
    refuse as stale, until the next build re-records it. A model-side sidecar at
    THIS schema is a fast yes on top of that; a file at any other schema is not
    a sidecar this viewer reads, so classification treats it as absent and falls
    through to the record. Loud refusal on a wrong-schema sidecar belongs to the
    RENDER path, not here.
    """
    sidecar = _read_json(source_sidecar_path(step_path))
    if sidecar is not None and sidecar.get("schemaVersion") == SOURCE_SIDECAR_SCHEMA_VERSION:
        return True
    record = _read_json(source_provenance_record_path(step_path))
    return bool(record is not None and str(record.get("sourceKind") or "").strip())


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
    """``Object.values(descriptor.components)`` semantics.

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
    """The package freshness verdict.

    ``generated`` is decided BEFORE the package gates and carried on every
    verdict including the failures. The import path reads
    ``rawStep and not generated``, and the case where that decision matters most
    is precisely a document with NO package — which would otherwise return
    before the classification ran, leaving it undefined and offering to import a
    model whose real fix is rerunning its script.
    """
    generated = is_generated_document(step_path)
    package_dir = render_package_dir(step_path)
    if not os.path.isdir(package_dir):
        return {"ok": False, "code": "missing_glb", "packageDir": package_dir, "generated": generated}
    descriptor = _read_json(os.path.join(package_dir, STEP_DESCRIPTOR_NAME))
    if descriptor is None:
        return {
            "ok": False,
            "code": "missing_step_topology",
            "packageDir": package_dir,
            "generated": generated,
        }
    if descriptor.get("kind") != STEP_PACKAGE_KIND:
        return {
            "ok": False,
            "code": "unsupported_step_topology",
            "packageDir": package_dir,
            "descriptor": descriptor,
            "generated": generated,
        }
    components = _component_values(descriptor)
    if not components:
        return {
            "ok": False,
            "code": "missing_glb",
            "packageDir": package_dir,
            "descriptor": descriptor,
            "generated": generated,
        }
    for component in components:
        surf = str((component or {}).get("surf") or "") if isinstance(component, dict) else ""
        if not surf or not os.path.exists(os.path.join(package_dir, surf)):
            return {
                "ok": False,
                "code": "missing_glb",
                "packageDir": package_dir,
                "descriptor": descriptor,
                "generated": generated,
            }
    return {"ok": True, "packageDir": package_dir, "descriptor": descriptor, "generated": generated}


def resolve_artifact_verdict(file_ref, root_dir) -> dict:
    candidate = resolve_candidate(file_ref, root_dir)
    if candidate is None:
        return {"error": f"Artifact source not found: {file_ref}"}
    if owns_step_path(candidate):
        # rawStep is character-identical to the ownership test above, so it is
        # always true here. Kept because the import gate reads it by name.
        return {"format": "step", "candidate": candidate, "rawStep": True, **_validate_step(candidate)}
    return {"error": f"No render-artifact format owns this entry: {file_ref}"}


def artifact_status(file_ref, root_dir, *, snapshot=None, verdict=None) -> dict:
    """The ``GET /__cad/artifact`` state machine.

    ``snapshot`` is the build view — ``{writing, busy, runId, progress}`` — or
    ``None`` when there is none. Key PRESENCE is the contract: an absent
    ``runId`` or ``progress`` must be absent, never ``None``.

    ``verdict`` lets a caller that already resolved one pass it in. The route
    needs the verdict again to decide whether to offer an import, and resolving
    twice per poll meant re-reading the sidecar and the provenance record on
    every 400ms tick of every build.
    """
    if verdict is None:
        verdict = resolve_artifact_verdict(file_ref, root_dir)
    if verdict.get("error"):
        return {"state": ARTIFACT_STATE.ERROR, "error": verdict["error"]}

    snapshot = snapshot or {}
    # Checked BEFORE verdict.ok, so a build in flight over a currently
    # resolvable package reports generating rather than ready.
    if snapshot.get("writing"):
        status = {"state": ARTIFACT_STATE.GENERATING}
        if snapshot.get("runId"):
            status["runId"] = snapshot["runId"]
        if snapshot.get("progress") is not None:
            status["progress"] = snapshot["progress"]
        return status

    if verdict.get("ok"):
        status = {"state": ARTIFACT_STATE.READY}
        if snapshot.get("busy"):
            status["busy"] = True
            if snapshot.get("runId"):
                status["runId"] = snapshot["runId"]
            if snapshot.get("progress") is not None:
                status["progress"] = snapshot["progress"]
        return status

    code = verdict.get("code")
    if code in BUILDABLE_CODES:
        status = {"state": ARTIFACT_STATE.NEEDS_BUILD, "reason": code}
        if snapshot.get("busy"):
            status["blocked"] = True
        return status

    # error and reason carry the same bare code string.
    return {"state": ARTIFACT_STATE.ERROR, "reason": code, "error": code}
