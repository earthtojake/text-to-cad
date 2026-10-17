"""A build's preview revision (STORE.md §9b): what it announces the moment its result
exists, before its STEP is written -- the result tree, the part of every component in it
and its annotations -- artifact-side objects a viewer reads like any others and draws
labelled as a preview until the saved file replaces them in place.

The build's events name it, and the daemon's ledger keeps exactly those names
(``daemon/jobs.py``, ``_KEPT_RESULT_FIELDS``):

- ``preview``: the output path, the result tree's hash, the producer the parts are keyed
  under, ``{cid: part key}`` for every component whose part the store holds -- the stored
  parts first, then one event per part the build derives -- and whether that is all of
  them (``_internal/generation.py``, ``publish_preview``).
- ``annotations``: the hash of one content-addressed object, :func:`annotations_object`,
  resolving the model's declarations against the result tree exactly as the catalog
  resolves a saved file's sidecar (``viewer/scanner.py``): the articulation of its mates,
  its appearance and what that draws per occurrence, its clips baked to keyframes -- the
  very keyframes its sidecar carries, baked once per build. All of it is keyed by the
  tree's tokens, which the saved document mints again (README law 20), so the save
  confirms the annotations and nothing on screen moves.

The object is artifact-side and no GC root: the grace period keeps it while the build it
belongs to is the news, and nothing durable names it -- no sidecar binds to a preview, no
record or document entry carries the hash. :func:`read_annotations` is its one reader, for
the viewer's store route, and reads ``objects/`` alone (STORE.md §2, property 2).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

__all__ = ["PREVIEW_ANNOTATIONS_KIND", "PREVIEW_ANNOTATIONS_SCHEMA", "annotations_object", "read_annotations"]

PREVIEW_ANNOTATIONS_KIND = "preview-annotations"
# The object's shape: the catalog entry's annotation fields for a saved file, plus the
# tree they were resolved against. A change to what they carry bumps it.
PREVIEW_ANNOTATIONS_SCHEMA = 1


def annotations_object(tree_hash: str, *, kinematics: Mapping[str, Any] | None,
                       appearance: Mapping[str, Any] | None, animation: Mapping[str, Any] | None) -> str | None:
    """Resolve what the sidecar will carry against the result tree ``tree_hash`` and
    publish it as one object: its hash, or None when the model declares nothing.
    ``kinematics`` is the resolved block (``kinematics_resolve.resolve_kinematics_block``),
    ``appearance`` the result tree's own, ``animation`` the keyframes the model's
    ``animation=`` baked to against that tree (``animation_bake.bake_document_animation``).
    A declaration that fails to resolve raises, as it fails the build."""
    if not kinematics and appearance is None and animation is None:
        return None
    from cadgen._internal.component_package import canonical_json_bytes
    from cadgen._internal.source_sidecar import occurrence_display
    from cadgen.articulation import step_articulation
    from cadgen.store.objects import put_object
    from cadgen.store.trees import flatten

    descriptor = flatten(tree_hash)
    if descriptor is None:
        raise RuntimeError("the preview's tree disappeared before its annotations were resolved")
    payload = {
        "kind": PREVIEW_ANNOTATIONS_KIND,
        "schemaVersion": PREVIEW_ANNOTATIONS_SCHEMA,
        "tree": tree_hash,
        "articulation": step_articulation(descriptor, kinematics) if kinematics else None,
        "appearance": json.loads(json.dumps(appearance)) if appearance is not None else None,
        "display": occurrence_display(descriptor, appearance) if appearance is not None else None,
        "animation": animation,
    }
    return put_object(canonical_json_bytes(payload))


def read_annotations(object_hash: str) -> dict[str, Any] | None:
    """The annotations object ``object_hash`` names, or None when the store holds no such
    object (or another kind of object under that hash)."""
    from cadgen.store.objects import is_object_hash, object_path

    if not is_object_hash(object_hash):
        return None
    try:
        payload = json.loads(object_path(object_hash).read_bytes())
    except (OSError, ValueError):
        return None
    if (type(payload) is not dict or payload.get("kind") != PREVIEW_ANNOTATIONS_KIND
            or payload.get("schemaVersion") != PREVIEW_ANNOTATIONS_SCHEMA):
        return None
    return payload
