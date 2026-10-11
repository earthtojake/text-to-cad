"""``cadgen glb build --animation``: the request, and what it refuses.

A GLB is the one mesh format with somewhere to put a clip, so this is the GLB
door's half of choreography. The other half -- the clip itself -- is the keyframes
baked into the document sidecar's ``animation`` section, which the export writes
into the file as glTF animation (``cadgen._internal.glb_animation``).

Two things live here and nowhere else. The first is the request's shape: a
closed key set (``clip``, ``seconds``, ``start``, ``drop``) whose values are
checked before any meshing. The second is what the export's freshness key has to
include beyond the document's bytes: the choreography is an annotation the STEP
does not hash, so an edited animation must invalidate a ledgered animated GLB
(:func:`animation_variant_token`) or the door would report an old clip current
forever.

``--animation`` is deliberately NOT ``snapshot --video``, which shares two of its
key names. A video is pixels: it has a camera, a quality and a playback rate. A
GLB carries the animation itself -- the clip's own keys, a pivot per moving part
and a skin per bending tube -- so it has none of those.

Stdlib only, like the mesh door it serves: nothing here may reach the CAD stack.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# The request's closed vocabulary. No camera, no quality and no frame rate: this
# writes the clip's keys, not pixels or samples, and a key that means nothing is a
# key that misleads.
ANIMATION_REQUEST_KEYS = frozenset({"clip", "seconds", "start", "drop"})

# How many times a window may repeat a looping clip: every repeat is its keys again
# in the file. 240 is four minutes of a one-second cycle.
MAX_LOOP_REPEATS = 240

# Effects glTF has no animated channel for, which `drop` may bake as static
# instead of having the export refuse them.
DROPPABLE_EFFECTS = ("opacity", "visible")


def normalize_animation_request(value: object, *, where: str) -> dict[str, object]:
    """The door's ``animation`` request, validated.

    Both spellings land here -- the flag's clip name or inline JSON, and a real
    dict from ``glb.build(animation={...})`` -- so one validator holds the shape.
    ``seconds`` stays ``None`` when the caller named none: the default is what is
    LEFT of the clip from ``start``, which only the export works out, holding the
    clip's duration and loop flag.
    """
    if not isinstance(value, dict):
        raise ValueError(
            f"{where} must be a clip name or a "
            f"{{{', '.join(sorted(ANIMATION_REQUEST_KEYS))}}} object"
        )
    unknown = sorted(set(value) - ANIMATION_REQUEST_KEYS)
    if unknown:
        raise ValueError(
            f"{where} has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(ANIMATION_REQUEST_KEYS))}"
        )

    clip = value.get("clip")
    if not isinstance(clip, str) or not clip.strip():
        raise ValueError(f"{where} must name a clip the document sidecar's animation declares")

    raw_seconds = value.get("seconds")
    seconds: float | None = None
    if raw_seconds is not None:
        seconds = _finite_number(raw_seconds, where=where, field="seconds")
        if seconds <= 0:
            raise ValueError(f"{where} seconds must be greater than 0, got {raw_seconds!r}")

    raw_start = value.get("start", 0)
    start = _finite_number(raw_start, where=where, field="start")
    if start < 0:
        raise ValueError(f"{where} start must be seconds >= 0, got {raw_start!r}")

    raw_drop = value.get("drop", [])
    if isinstance(raw_drop, str) or not isinstance(raw_drop, (list, tuple)):
        raise ValueError(
            f"{where} drop must be a list of effect names ({', '.join(DROPPABLE_EFFECTS)}), "
            f"got {raw_drop!r}"
        )
    drop = sorted({str(name).strip() for name in raw_drop})
    unknown_drop = [name for name in drop if name not in DROPPABLE_EFFECTS]
    if unknown_drop:
        raise ValueError(
            f"{where} drop names {', '.join(unknown_drop)}; only these effects can be baked "
            f"static: {', '.join(DROPPABLE_EFFECTS)}"
        )
    return {"clip": clip.strip(), "seconds": seconds, "start": start, "drop": drop}


def _finite_number(value: object, *, where: str, field: str, unit: str = "seconds") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} {field} must be a number of {unit}, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{where} {field} must be a finite number of {unit}, got {value!r}")
    return number


def parse_animation_option(raw_animation: object, *, where: str = "--animation") -> dict[str, object]:
    """``--animation`` in request form.

    Already an object when it came from a ``glb.build(animation={...})`` call;
    from argv it is one string, told apart by shape the way ``--kinematics`` is:
    text that opens with ``{`` is the inline JSON request, anything else is the
    NAME of a clip the document sidecar's animation declares. There is no file-path
    spelling -- a clip request is a handful of keys, not a document.
    """
    if isinstance(raw_animation, dict):
        return normalize_animation_request(raw_animation, where=where)
    text = str(raw_animation or "").strip()
    if not text:
        raise ValueError(
            f"{where} requires a clip name or a JSON object: "
            f"{{{', '.join(sorted(ANIMATION_REQUEST_KEYS))}}}"
        )
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON from {where}: {exc}") from exc
        return normalize_animation_request(parsed, where=where)
    return normalize_animation_request({"clip": text}, where=where)


def animation_variant_token(request: dict[str, object], animation_data: str) -> str:
    """This animated export's identity, for the mesh-export ledger.

    A static mesh is a pure function of the document's bytes and its tolerances,
    which is what the ledger keys on. An ANIMATED one is also a function of the
    request and the sidecar's keyframes. Folding both into the variant key makes
    a rebaked animation re-export motion without rebuilding geometry.
    """
    import hashlib

    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    # Admit only exports produced from the same captured keyframes as their token.
    digest = hashlib.sha256(b"cadgen-animation-gltf-keys-v2\0")
    digest.update(canonical.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(animation_data).encode("utf-8"))
    return digest.hexdigest()[:32]


@dataclass(frozen=True)
class AnimationSnapshot:
    """The sidecar's ``animation`` section as read once, canonical JSON text."""

    data: str
    document_hash: str
    appearance: dict | None


def resolve_animation(document: Path, request: dict[str, object]) -> tuple[AnimationSnapshot, str]:
    """``(animation snapshot, variant token)`` for an animated export.

    The clip NAME is checked HERE -- a typo must fail as a clean CLI error naming
    the clips the model has, before anything is meshed. Both the token and the
    sampler consume this same snapshot, even if the sidecar is rewritten during
    meshing.
    """
    from cadgen._internal.source_sidecar import read_source_sidecar
    from cadgen.catalog import artifact_file_hash

    document_hash = artifact_file_hash(document)
    if not document_hash:
        raise ValueError(f"Could not read STEP document: {document}")
    sidecar = read_source_sidecar(document, document_hash=document_hash) or {}
    animation = sidecar.get("animation")
    if animation is None:
        raise ValueError(f"{Path(document).name} has no animation in its sidecar. Declare animation= on @step.")
    clip_name = str(request["clip"])
    declared = [clip["id"] for clip in animation["clips"]]
    if clip_name not in declared:
        raise ValueError(f"Unknown animation clip: {clip_name}. This model declares: {', '.join(declared)}")
    data = json.dumps(animation, sort_keys=True, separators=(",", ":"))
    return AnimationSnapshot(data, document_hash, sidecar.get("appearance")), animation_variant_token(request, data)
