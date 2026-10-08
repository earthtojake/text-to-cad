"""``GET /__cad/tube-skins``: a document's bending tubes, bound as a CAD view plays them.

The payload is cadgen's (``cadgen._internal.tube_skin_payload``): every tube a clip
bends, refined and bound in its component's frame, and every key's joints. It is
derived from the document's stored meshes and its sidecar's animation, cached in
the store's ``skin`` index, and only numpy runs here: no CAD kernel, as for every
route of this server. This module is the route's decisions -- what may be opened,
and the HTTP answer. The catalog names the URL (``tubeSkinsUrl``) for a built
document whose animation bends a tube.

Statuses, in the order they are decided:

* no ``?file=``, a ref that is not an absolute path, or one that is not a STEP, or
  a tessellation that is not one -> 400 (through the GET funnel's JSON error).
* no such file, a document not built, a sidecar this cadgen cannot read or none,
  or an animation that bends no tube -> 404.
* ``documentHash`` naming other bytes than the file holds now -> 409: the view is
  behind the file, and its next catalog read names the current skins.
"""

from __future__ import annotations

import os

from .backend import absolute_path
from .encoding import encode_uri_component
from .scanner import node_basename
from .store_paths import result_snapshot

__all__ = ["TUBE_SKINS_ROUTE_PATH", "tube_skins_response", "tube_skins_url"]

TUBE_SKINS_ROUTE_PATH = "/__cad/tube-skins"
_STEP_SUFFIXES = (".step", ".stp")


def tube_skins_url(path: str, document_hash: str) -> str:
    """The route's URL for one document's bytes."""
    return (f"{TUBE_SKINS_ROUTE_PATH}?file={encode_uri_component(str(path))}"
            f"&documentHash={encode_uri_component(str(document_hash))}")


def _tolerance(value, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{TUBE_SKINS_ROUTE_PATH} {name} must be a number, got {value!r}") from None


def tube_skins_response(file_ref, document_hash=None, chord=None, angle=None) -> tuple[int, bytes | dict]:
    """``(status, body)``: the payload's bytes at 200, or a JSON error dict."""
    if not file_ref:
        raise ValueError(f"GET {TUBE_SKINS_ROUTE_PATH} needs ?file=<the absolute path of a .step>")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(_STEP_SUFFIXES):
        raise ValueError(f"{TUBE_SKINS_ROUTE_PATH} binds the tubes of STEP documents; "
                         f"{node_basename(candidate)} is not one")
    chord, angle = _tolerance(chord, "chord"), _tolerance(angle, "angle")
    if not os.path.isfile(candidate):
        return 404, {"error": "Not found"}
    snapshot = result_snapshot(candidate)
    if not snapshot:
        return 404, {"error": f"{node_basename(candidate)} is not built"}
    current, tree = snapshot
    if document_hash and str(document_hash).strip().lower() != current:
        return 409, {"error": f"{node_basename(candidate)} changed since this view read it"}

    from cadgen._internal.source_sidecar import (
        SidecarBindingError,
        SidecarSchemaError,
        read_source_sidecar,
    )
    from cadgen._internal.tube_skin_payload import tube_skins_bytes

    try:
        sidecar = read_source_sidecar(candidate, document_hash=current)
    except (SidecarBindingError, SidecarSchemaError):
        sidecar = None
    data = tube_skins_bytes(tree=tree, document_hash=current, animation=(sidecar or {}).get("animation"),
                            chord=chord, angle=angle)
    if data is None:
        return 404, {"error": f"{node_basename(candidate)} bends no tube"}
    return 200, data
