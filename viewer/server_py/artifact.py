"""Render-artifact status/build for /__cad/artifact (the STEP component-GLB package, the
DXF drawing package and the implicit-CAD render package).

- Ownership is decided on entry.file. Imported `.step`/`.stp` and generated `.step.py`,
  imported `.dxf` and generated `.dxf.py`, and `.implicit.js`/`.implicit.mjs` models are ALL
  owned and get a freshness check; an entry with no built artifact reports `needs-build` and
  is built on demand (the viewer surfaces every model, built or not). An imported `.dxf` is
  owned for the same reason an imported `.step` is: its package's `preview.glb` is the only
  3D renderer it has, and an `.implicit.js` is owned for the same reason again — its baked
  `model.glb` is the only renderer it has.
- Freshness is a PURE descriptor read (descriptor + payload existence + schema version +
  bake hash; a generated entry re-hashes its recorded source closure, an imported entry
  compares the digest its format's spec-table row names) — **no OCP**. It DOES import cadgen, but only stdlib-only modules
  (`cadgen.coordination`, `cadgen._internal.source_hash`), so the long-lived server
  process never loads a CAD runtime. That is the invariant that matters, and it is
  pinned by tests/python/packages/cadgen/test_coordination_is_stdlib_only.py — the
  older "no cadgen import at all" rule was a proxy for it, and the price of that proxy
  was maintaining hand-written copies of the digest and the lock protocol here.
  STEP and generated-DXF packages run the SAME validator and the SAME content digest
  cadgen's CLI gate uses, so the two never disagree about staleness. State machine:
  ready | needs-build | generating | error.
- The build (POST) shells out to `cadgen.step_artifact_cli`, keeping OCP out of the
  server process (crash/memory isolation).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# The closure digest is cadgen's, imported rather than reimplemented: the viewer's copy
# of it was 133 lines that had to agree byte-for-byte with the producer's or a model
# would rebuild forever. cadgen._internal.source_hash is stdlib-only, so this costs the
# server process nothing.
from cadgen._internal.drawing_package import (
    DXF_PACKAGE_SCHEMA_VERSION,
    descriptor_is_drawing,
    drawing_payload_keys,
    drawing_preview_bake_settings,
)
from cadgen._internal.implicit_package import (
    IMPLICIT_DESCRIPTOR_NAME,
    IMPLICIT_PACKAGE_KIND,
    IMPLICIT_PACKAGE_SCHEMA_VERSION,
    IMPLICIT_SUFFIXES,
    implicit_bake_settings,
)
from cadgen._internal.package_freshness import (
    STEP_PACKAGE_VERSION,
    bake_hash_matches,
    canonical_bake_hash,
    schema_version_matches,
)
from cadgen._internal.source_hash import closure_hash_matches

from . import scanner

ARTIFACT_STATE_READY = "ready"
ARTIFACT_STATE_NEEDS_BUILD = "needs-build"
ARTIFACT_STATE_GENERATING = "generating"
ARTIFACT_STATE_ERROR = "error"

# Every freshness code a POST /__cad/artifact can fix by building. Not STEP-specific: one
# set spanning every artifact-managed format, because the client asks one question ("can
# this be built?") of one state machine.
BUILDABLE_ARTIFACT_CODES = frozenset([
    "missing_glb", "missing_step_topology", "missing_edge_topology",
    "missing_surface_edge_attributes", "missing_selector_topology",
    "missing_source_path", "missing_step_hash", "stale_step_artifact",
    "unsupported_step_topology",
    # Drawing package codes (same buildable semantics).
    "missing_dxf_artifact", "stale_dxf_artifact", "unsupported_dxf_artifact",
    # Implicit render package codes.
    "missing_implicit_artifact", "stale_implicit_artifact", "unsupported_implicit_artifact",
])

# Owns imported `.step`/`.stp` and generated `.step.py`/`.stp.py` entries.
_STEP_ENTRY_RE = re.compile(r"\.(step|stp)(\.py)?$", re.IGNORECASE)


def owns_step_entry(entry) -> bool:
    return bool(entry) and bool(_STEP_ENTRY_RE.search(str(entry.get("file") or "")))


# Owns generated `.dxf.py` drawings AND imported `.dxf` files. Both are artifact-managed:
# the drawing package's `preview.glb` is the only 3D DXF renderer there is, so an imported
# `.dxf` needs a build for exactly the reason an imported `.step` does. The viewer owns and
# builds them on demand; the gen CLI stays `.dxf.py`-only (design §0.1, §5.5).
_DXF_ENTRY_RE = re.compile(r"\.dxf(\.py)?$", re.IGNORECASE)


def owns_dxf_entry(entry) -> bool:
    return bool(entry) and bool(_DXF_ENTRY_RE.search(str(entry.get("file") or "")))


# Owns `.implicit.js` / `.implicit.mjs` models. The suffixes come from the PRODUCER
# (cadgen._internal.implicit_package), so the set of sources the viewer asks to build can
# never drift from the set the builder accepts.
def owns_implicit_entry(entry) -> bool:
    file_ref = str((entry or {}).get("file") or "").lower()
    return bool(entry) and any(file_ref.endswith(suffix) for suffix in IMPLICIT_SUFFIXES)


def owns_entry(entry) -> bool:
    return owns_step_entry(entry) or owns_dxf_entry(entry) or owns_implicit_entry(entry)


# --- pure freshness validation (shared by both package formats) ---
# Per-format descriptor names, package kinds, payload refs, schema versions, digest field
# names, bake ownership, and error codes. The validation ALGORITHM is identical for both;
# only this table differs. Anything format-specific belongs HERE, not in a branch inside
# the validator and not as a field alias: `stepHash` is load-bearing at a dozen cadgen
# sites beyond the render descriptor (GLB manifests, the BREP scene cache), so newer
# formats name their digest `sourceDigest` and the table says which.
_STEP_PACKAGE = {
    "descriptor": "assembly.json",
    "package_kind": "assembly-package",
    "schema_version": STEP_PACKAGE_VERSION,
    # The digest an IMPORTED entry's descriptor must record for its source file.
    "source_digest_field": "stepHash",
    "missing_digest": "missing_step_hash",
    # Callable returning the format's current bake settings, or None when the format bakes
    # no settings into its payload. STEP bakes none: components are geometry at recorded
    # mesh tolerances, which the producer compares separately.
    "bake_settings": None,
    "missing": "missing_glb",
    "unreadable": "missing_step_topology",
    "unsupported": "unsupported_step_topology",
    "stale": "stale_step_artifact",
}
_DRAWING_PACKAGE = {
    "descriptor": scanner.DRAWING_DESCRIPTOR_NAME,
    "package_kind": scanner.DRAWING_PACKAGE_KIND,
    "schema_version": DXF_PACKAGE_SCHEMA_VERSION,
    "source_digest_field": "sourceDigest",
    # No dedicated "the drawing descriptor recorded no digest" code exists and none is
    # minted: a package that cannot be shown to be current IS stale, and stale_dxf_artifact
    # is already buildable and already has client copy.
    "missing_digest": "stale_dxf_artifact",
    # The drawing package DOES bake settings: preview.glb froze a thickness, a bend state
    # and the mesher's geometry contract into itself, and nothing else here can see them
    # change. This is the producer's own callable (`drawing_package_current` calls the same
    # one), so the two authorities cannot drift apart by an edit.
    "bake_settings": drawing_preview_bake_settings,
    "missing": "missing_dxf_artifact",
    "unreadable": "missing_dxf_artifact",
    "unsupported": "unsupported_dxf_artifact",
    "stale": "stale_dxf_artifact",
}
_IMPLICIT_PACKAGE = {
    "descriptor": IMPLICIT_DESCRIPTOR_NAME,
    "package_kind": IMPLICIT_PACKAGE_KIND,
    "schema_version": IMPLICIT_PACKAGE_SCHEMA_VERSION,
    # An implicit model is a GENERATED entry (its descriptor records sourceKind "python" and
    # a JS source closure), so this field is never reached today. It is named anyway, and
    # named the same as every post-STEP format, so the imported branch cannot fail open if a
    # descriptor ever arrives with a different provenance.
    "source_digest_field": "sourceDigest",
    "missing_digest": "stale_implicit_artifact",
    # The bake IS the artifact here: model.glb froze one resolution, one cell cap and the
    # mesher's geometry contract into itself at the model's default parameter values, and
    # nothing else in the freshness stack can see any of them change. This is the producer's
    # own callable, so the two authorities cannot drift apart by an edit.
    "bake_settings": implicit_bake_settings,
    "missing": "missing_implicit_artifact",
    "unreadable": "missing_implicit_artifact",
    "unsupported": "unsupported_implicit_artifact",
    "stale": "stale_implicit_artifact",
}


def _step_payload_refs(descriptor):
    """Every component GLB the assembly descriptor claims."""
    components = descriptor.get("components") if isinstance(descriptor.get("components"), dict) else {}
    return [str((component or {}).get("glb") or "").strip() for component in components.values()]


def descriptor_declares_no_bake(descriptor):
    """Whether this descriptor legitimately records no bake at all.

    A drawing has no flat pattern, so it bakes nothing and records nothing -- but a drawing
    descriptor that DOES carry a bakeHash is not exempt: it is claiming a payload it never
    wrote, which is exactly what the gate is for."""
    if not descriptor_is_drawing(descriptor):
        return False
    return not str(descriptor.get("bakeHash") or "").strip()


def _drawing_payload_refs(descriptor):
    """The drawing package's one payload: the render GLB.

    It used to also carry an exchange DXF. That is gone: __cadgen__ caches what was COMPUTED,
    and a drawing's DXF is either the user's own file (imported) or reproducible on demand
    from its generator. Checking `preview.glb` is the check that matters -- a package whose
    GLB is missing or half-written would otherwise validate as `ready`, the viewer would
    render nothing, and no `needs-build` would ever explain why (design §4.7, §7.4.2).

    Mirrors ``drawing_package_current`` in cadgen's drawing_package.py; the two authorities
    must ask the same question or a build and a status GET disagree."""
    # A dimensioned drawing has no flat pattern, so its package holds no preview.glb and
    # never had a bake -- the payload list comes from cadgen so this side cannot drift into
    # demanding one and reporting every drawing stale forever (issue #246).
    return [str(descriptor.get(key) or "").strip() for key in drawing_payload_keys(descriptor)]


def _implicit_payload_refs(descriptor):
    """The one payload an implicit package has: the baked mesh."""
    return [str(descriptor.get("glb") or "").strip()]


def _validate_render_package(spec, source_path, payload_refs, model_folder):
    """Return (ok, code) — ok=True when fresh, else (False, <error_code>).

    One algorithm for both formats: the package dir and descriptor must exist, declare the
    expected kind and EXACTLY the current ``packageSchemaVersion``, every payload file the
    descriptor names must be on disk, its ``bakeHash`` must match the format's current bake
    settings, and then freshness is decided by provenance —

    * generated (``sourceKind: python``): the recorded source closure must still
      hash unchanged. This is the SAME content digest cadgen's CLI gate uses (see
      cadgen._internal.source_hash), so the two never disagree. A descriptor that records no
      usable closure is treated as STALE for both formats: it cannot be shown to be
      current, and a rebuild is cheap and self-correcting.
    * imported: the on-disk file must still hash to the digest the spec table names
      (``stepHash`` for STEP). This FAILS CLOSED — a descriptor recording no digest for a
      source file that exists reports needs-build, matching cadgen's producer gate, which
      compares the file's real hash against whatever the descriptor recorded and so has
      never accepted a blank one.

    Every gate here exists in the producer's currency predicate too
    (``generation._package_descriptor_matches_spec`` / ``drawing_package_current``);
    see cadgen._internal.package_freshness for why that is not optional.
    """
    package_dir = scanner.render_package_dir(source_path)
    if not os.path.isdir(package_dir):
        return (False, spec["missing"])
    descriptor_path = os.path.join(package_dir, spec["descriptor"])
    try:
        with open(descriptor_path, "r", encoding="utf-8") as handle:
            descriptor = json.load(handle)
    except (OSError, ValueError):
        return (False, spec["unreadable"])
    if not isinstance(descriptor, dict) or descriptor.get("kind") != spec["package_kind"]:
        return (False, spec["unsupported"])
    # Strict equality, no tolerant reader: the schema version is this stack's single
    # invalidation channel (bump it and every package of that kind rebuilds, lazily, on
    # reopen) in place of per-field compatibility branches.
    if not schema_version_matches(descriptor, spec["schema_version"]):
        return (False, spec["unsupported"])
    for ref in payload_refs(descriptor):
        if not ref or not os.path.isfile(os.path.join(package_dir, ref)):
            return (False, spec["missing"])
    bake_settings = spec["bake_settings"]
    # Two different "no bake" cases, and only one of them is legitimate:
    #
    # * a kind that bakes NOTHING (STEP) must still be checked, because a descriptor that
    #   records a bakeHash anyway is stale -- that is the check, not an exemption from it;
    # * a DRAWING profile genuinely has no flat pattern to bake, so demanding a bakeHash from
    #   it would report it stale on every poll: a rebuild that never finishes.
    if not descriptor_declares_no_bake(descriptor):
        if not bake_hash_matches(
            descriptor, canonical_bake_hash(bake_settings() if bake_settings else None)
        ):
            return (False, spec["stale"])
    if str(descriptor.get("sourceKind", "step")).strip().lower() == "python":
        if not os.path.isfile(source_path):
            return (False, "missing_source_path")
        closure = descriptor.get("sourceClosureFiles")
        if not isinstance(closure, list) or not closure:
            return (False, spec["stale"])
        if not closure_hash_matches(
            descriptor.get("sourceClosureHash"), closure, base=Path(model_folder)
        ):
            return (False, spec["stale"])
        return (True, None)
    recorded_digest = str(descriptor.get(spec["source_digest_field"], "")).strip()
    if scanner._file_stats(source_path):
        # Fail closed. A descriptor with no digest for a source file that is right there
        # cannot be shown to be current, and answering `ready` on it was this validator's
        # lone fail-open path -- the generated branch above and cadgen's own gate both
        # already treat missing provenance as a rebuild.
        if not recorded_digest:
            return (False, spec["missing_digest"])
        current = scanner._sha256_file(source_path)
        if current and recorded_digest != current:
            return (False, spec["stale"])
    return (True, None)


def validate_step_freshness(repo_root, source_path):
    """ok=True (fresh/ready) or (False, code). source_path is the entry's step path
    (the `.step.py` for a generated model, the `.step` for an imported one)."""
    del repo_root  # closure paths resolve against the model folder, not the repo root
    return _validate_render_package(
        _STEP_PACKAGE, source_path, _step_payload_refs, os.path.dirname(os.path.abspath(source_path))
    )


def validate_dxf_freshness(repo_root, source_path):
    """ok=True (fresh/ready) or (False, code). source_path is the `.dxf.py` generator for a
    generated drawing or the `.dxf` itself for an imported one; the package dir is
    entry-keyed exactly like the STEP package."""
    del repo_root
    return _validate_render_package(
        _DRAWING_PACKAGE, source_path, _drawing_payload_refs, os.path.dirname(os.path.abspath(source_path))
    )


def validate_implicit_freshness(repo_root, source_path):
    """ok=True (fresh/ready) or (False, code). source_path is the `.implicit.js` model; the
    package dir is entry-keyed exactly like the STEP and drawing packages."""
    del repo_root
    return _validate_render_package(
        _IMPLICIT_PACKAGE, source_path, _implicit_payload_refs, os.path.dirname(os.path.abspath(source_path))
    )


# --- generation state (ONE implementation, shared with the producer) -----------------
# This used to be a hand-written COPY of cadgen's lock and progress readers, kept in sync
# with the producer only by a test that compared path strings. The two had drifted into
# implementing different protocols from one primitive: the producer took a blocking
# exclusive lock to DO something, this side took a momentary EXCLUSIVE lock to ASK
# something -- and because flock conflicts per open file description, two concurrent
# probes conflicted with EACH OTHER and one reported a build that did not exist.
#
# cadgen.coordination is stdlib-only and importing it pulls in no CAD runtime, which is
# the property that actually matters for this process (pinned by
# tests/python/packages/cadgen/test_coordination_is_stdlib_only.py). Reading the state
# through the same code that writes it is what makes the two agree by construction.
def generation_snapshot(package_dir: str):
    """Non-blocking view of what is happening to ``package_dir`` right now.

    Returns a ``cadgen.coordination.Snapshot``: ``state`` is idle/writing/busy, decided by
    the KERNEL rather than by any written file, so a crashed or killed build reads as idle
    with no stale window. ``progress`` is attached only when the record on disk belongs to
    the run currently holding the lock.
    """
    from cadgen.coordination import snapshot

    return snapshot(package_dir)
