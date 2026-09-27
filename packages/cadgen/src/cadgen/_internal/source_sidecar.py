"""The source sidecar: everything SOURCE-derived a generated model carries.

The tree (in the user-level store, keyed by the document's content
hash) is a pure function of the STEP file's bytes plus schema versions — the
cache engine's world, freely evictable. The model's DECLARATIONS live in ONE
sidecar FILE BESIDE THE MODEL, ``<name>.step.json``: KINEMATICS
(typed mates with axes resolved to world numbers, couplings, pose presets)
and APPEARANCE (named materials assigned to canonical document occurrences),
plus an optional embedded ANIMATION module. The one hash here is
``documentHash``: an artifact binding that prevents declarations from being
applied to different STEP bytes after a partial copy or replacement. It is not
source identity or provenance. No source paths, closure hashes, or timestamps
belong here; provenance lives in the RECORDS tier below. The
sidecar sits beside the model because declarations cannot be re-derived from
the STEP bytes: evicting the store must never lose kinematics. New capability
= new SECTION + schema bump, never a second sidecar file.

A sidecar exists ONLY when the model NEEDS kinematics, appearance, or animation. A plain
model — geometry and nothing else — writes no sidecar at all; its provenance and freshness ride
the PROVENANCE RECORD in the evictable records tier (bottom of this module),
which every generated build writes and every gate reads — the ONE home of
source-derived identity. Eviction costs one rebuild, never correctness (an
evicted record simply reads as an import until the next build re-records it).
Imports write neither.

Write ordering matters: the named STEP and sidecar land before the model record
that makes their tree current, so a resolvable package never races a missing
sidecar.
Readers are lock-blind and tolerate a MISSING sidecar; a sidecar that is
present must declare ``SOURCE_SIDECAR_SCHEMA_VERSION``, because reading
sections out of a file written to a different shape is how a model silently
loses its kinematics.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix

# APPENDED to the artifact's whole name, so the pair sorts and reads together:
# `part.step` -> `part.step.json`. Never match a sidecar on this suffix alone —
# it is `.json`, which every unrelated JSON file also ends with. Construct the
# path from the artifact (:func:`source_sidecar_path`), or match the artifact
# suffix too (`.step.json` / `.stp.json`).
SOURCE_SIDECAR_SUFFIX = ".json"
# 7: documentHash binds resolved kinematics to the exact STEP bytes they name.
# 6: the animation and meshExports sections were removed. A mesh door
#    tessellates the document's tree and writes the file
#    it was asked for, and what a model declares lives in its record. A sidecar
#    is written for kinematics alone. 5 moved provenance OUT of the sidecar.
# 8: intrinsic PBR finishes were inline occurrence annotations.
# 9: named material libraries + assignments, and embedded animation.
SOURCE_SIDECAR_SCHEMA_VERSION = 9

# What a sidecar may CONTAIN: declarations plus the exact-document binding.
# Anything source-derived-as-provenance (paths, closure hashes, timestamps)
# belongs to the provenance record; a sidecar sits beside the artifact and
# ships with it.
_SIDECAR_SECTIONS = ("schemaVersion", "documentHash", "kinematics", "appearance", "animation")
MATERIAL_KEYS = ("baseColor", "roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity")
_NUMERIC_MATERIAL_KEYS = MATERIAL_KEYS[1:]
SOURCE_MATERIAL_DEFAULTS = {
    "roughness": 0.42,
    "metalness": 0.03,
    "clearcoat": 0.0,
    "clearcoatRoughness": 0.26,
    "opacity": 1.0,
}


def source_sidecar_path(step_path: Path | str) -> Path:
    """``<name>.step`` -> ``<name>.step.json``, beside the model."""
    artifact = Path(step_path)
    return artifact.with_name(artifact.name + SOURCE_SIDECAR_SUFFIX)


class SidecarSchemaError(ValueError):
    """A sidecar file that is not at the schema this cadgen reads."""


class SidecarBindingError(ValueError):
    """A sidecar bound to different STEP bytes than the adjacent document."""


class SidecarAppearanceError(ValueError):
    """An appearance annotation is invalid or targets a missing occurrence."""


def _material_id(value: object, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SidecarAppearanceError(f"{where} must be a nonempty string")
    return value.strip()


def _base_color(value: object, *, where: str) -> str:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#" or any(
        character not in "0123456789abcdefABCDEF" for character in value[1:]
    ):
        raise SidecarAppearanceError(f"{where} must be a #RRGGBB color")
    return value.upper()


def _channel(value: object, *, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise SidecarAppearanceError(f"{where} must be a finite number between 0 and 1")
    return float(value)


def _normalized_material(value: object, *, material_id: str, authored: bool) -> dict[str, Any]:
    allowed = set(MATERIAL_KEYS) | {"name"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise SidecarAppearanceError(
            f"material {material_id!r} must contain only name, {', '.join(MATERIAL_KEYS)}"
        )
    name = value.get("name", material_id) if authored else value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SidecarAppearanceError(f"material {material_id!r}.name must be a nonempty string")
    result: dict[str, Any] = {"name": name.strip()}
    if "baseColor" in value:
        result["baseColor"] = _base_color(value["baseColor"], where=f"material {material_id!r}.baseColor")
    for key in _NUMERIC_MATERIAL_KEYS:
        if key in value:
            result[key] = _channel(value[key], where=f"material {material_id!r}.{key}")
    return result


def normalize_appearance(block: object) -> dict[str, Any] | None:
    """Validate resolved schema-9 named materials and leaf assignments."""
    if block is None:
        return None
    if not isinstance(block, dict) or set(block) != {"materials", "assignments"}:
        raise SidecarAppearanceError("appearance must contain only materials and assignments objects")
    materials, assignments = block["materials"], block["assignments"]
    if not isinstance(materials, dict) or not isinstance(assignments, dict):
        raise SidecarAppearanceError("appearance.materials and appearance.assignments must be objects")
    normalized_materials = {
        _material_id(key, where="appearance material id"): _normalized_material(value, material_id=key, authored=False)
        for key, value in sorted(materials.items())
    }
    normalized_assignments: dict[str, str] = {}
    for occurrence_id, material_id in sorted(assignments.items()):
        occurrence_id = _material_id(occurrence_id, where="appearance assignment occurrence id")
        material_id = _material_id(material_id, where=f"appearance assignment {occurrence_id}")
        if material_id not in normalized_materials:
            raise SidecarAppearanceError(f"appearance assignment {occurrence_id} references unknown material {material_id!r}")
        normalized_assignments[occurrence_id] = material_id
    if not normalized_materials and not normalized_assignments:
        return None
    return {
        "materials": normalized_materials,
        "assignments": normalized_assignments,
    }


def normalize_materials(block: object, *, where: str = "materials") -> dict[str, Any] | None:
    """Validate the author-facing ``@step(materials=...)`` declaration."""
    if block is None:
        return None
    if not isinstance(block, dict) or set(block) != {"definitions", "assignments"}:
        raise SidecarAppearanceError(f"{where} must contain only definitions and assignments")
    definitions, assignments = block["definitions"], block["assignments"]
    if not isinstance(definitions, dict) or not definitions:
        raise SidecarAppearanceError("materials.definitions must be a nonempty object")
    normalized_definitions = {
        _material_id(key, where="material definition id"): _normalized_material(value, material_id=key, authored=True)
        for key, value in sorted(definitions.items())
    }
    if not isinstance(assignments, list):
        raise SidecarAppearanceError("materials.assignments must be a list")
    normalized_assignments = []
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, dict) or set(assignment) != {"targets", "material"}:
            raise SidecarAppearanceError(f"materials.assignments[{index}] must contain only targets and material")
        material_id = _material_id(assignment["material"], where=f"materials.assignments[{index}].material")
        if material_id not in normalized_definitions:
            raise SidecarAppearanceError(f"materials.assignments[{index}] references unknown material {material_id!r}")
        targets = assignment["targets"]
        if not isinstance(targets, list) or not targets:
            raise SidecarAppearanceError(f"materials.assignments[{index}].targets must be a nonempty list")
        normalized_targets = []
        for target in targets:
            if not isinstance(target, str) or not target.startswith("#") or not target[1:].strip():
                raise SidecarAppearanceError(f"materials.assignments[{index}] target {target!r} must be a #label or #occurrence")
            normalized_targets.append("#" + target[1:].strip())
        normalized_assignments.append({"targets": normalized_targets, "material": material_id})
    return {"definitions": normalized_definitions, "assignments": normalized_assignments}


def normalize_animation(block: object, *, where: str = "animation") -> dict[str, str] | None:
    if block is None:
        return None
    if isinstance(block, str):
        source = block
        block = {"language": "javascript", "source": source}
    if not isinstance(block, dict) or set(block) != {"language", "source"}:
        raise ValueError(f"{where} must contain only language and source")
    if block.get("language") != "javascript":
        raise ValueError(f"{where}.language must be 'javascript'")
    source = block.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"{where}.source must be a nonempty JavaScript module")
    return {"language": "javascript", "source": source}


def appearance_digest(block: object) -> str:
    """A stable variant input, including the absence of appearance overrides."""
    payload = json.dumps(normalize_appearance(block), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _descriptor_nodes(descriptor: Mapping[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    leaves = {str(item.get("id") or "") for item in descriptor.get("occurrences") or []}
    by_id: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}

    def visit(node: object) -> list[str]:
        if not isinstance(node, Mapping):
            return []
        node_id = str(node.get("id") or "").strip()
        members = [node_id] if node_id in leaves else []
        for child in node.get("children") or []:
            members.extend(visit(child))
        if node_id:
            by_id[node_id] = members
            name = str(node.get("name") or "").strip()
            if name:
                by_name.setdefault(name, []).append(node_id)
        return members

    assembly = descriptor.get("assembly")
    root = assembly.get("root") if isinstance(assembly, Mapping) else None
    visit(root)
    return by_id, by_name


def _available_material_id(existing: Mapping[str, Any], requested: str, *, namespace: str) -> str:
    if requested not in existing:
        return requested
    candidate = f"{namespace}/{requested}"
    suffix = 2
    while candidate in existing:
        candidate = f"{namespace}{suffix}/{requested}"
        suffix += 1
    return candidate


def resolve_materials(
    descriptor: Mapping[str, Any], block: object, *, inherited: object = None
) -> dict[str, Any] | None:
    """Resolve authored labels/groups to canonical leaf IDs.

    ``inherited`` is the flattened child appearance. It is retained, then each
    local assignment overrides its selected leaves. Conflicting material IDs
    receive a stable ``local/`` namespace while keeping their authored names.
    """
    declaration = normalize_materials(block, where="materials=")
    base = normalize_appearance(inherited)
    if declaration is None:
        return base
    materials = deepcopy((base or {}).get("materials") or {})
    assignments = deepcopy((base or {}).get("assignments") or {})
    local_ids: dict[str, str] = {}
    for material_id, definition in declaration["definitions"].items():
        if materials.get(material_id) == definition:
            resolved_id = material_id
        else:
            resolved_id = _available_material_id(materials, material_id, namespace="local")
            materials[resolved_id] = deepcopy(definition)
        local_ids[material_id] = resolved_id

    by_id, by_name = _descriptor_nodes(descriptor)
    for index, assignment in enumerate(declaration["assignments"]):
        for target in assignment["targets"]:
            selector = target[1:]
            if selector in by_id:
                node_ids = [selector]
            else:
                node_ids = by_name.get(selector) or []
            if len(node_ids) != 1:
                if node_ids:
                    raise SidecarAppearanceError(
                        f"materials.assignments[{index}] target {target!r} is ambiguous: {', '.join(node_ids)}"
                    )
                raise SidecarAppearanceError(
                    f"materials.assignments[{index}] target {target!r} does not name a part or group"
                )
            members = by_id.get(node_ids[0]) or []
            if not members:
                raise SidecarAppearanceError(
                    f"materials.assignments[{index}] target {target!r} contains no leaf occurrences"
                )
            for occurrence_id in members:
                assignments[occurrence_id] = local_ids[assignment["material"]]
    return normalize_appearance({"materials": materials, "assignments": assignments})


def remap_appearance(
    block: object, occurrence_map: Mapping[str, list[str]]
) -> dict[str, Any] | None:
    """Bind authored flattened leaf assignments to exact saved-document leaves."""
    appearance = normalize_appearance(block)
    if appearance is None:
        return None
    assignments: dict[str, str] = {}
    for authored_id, material_id in appearance["assignments"].items():
        document_ids = occurrence_map.get(authored_id) or []
        if not document_ids:
            raise SidecarAppearanceError(
                f"appearance assignment {authored_id} has no exact saved-document occurrence"
            )
        for document_id in document_ids:
            assignments[str(document_id)] = material_id
    return normalize_appearance({
        "materials": appearance["materials"], "assignments": assignments,
    })


def validate_appearance_targets(descriptor: Mapping[str, Any], block: object) -> dict[str, Any] | None:
    """Validate annotation targets without copying an assembly for catalog scans."""
    appearance = normalize_appearance(block)
    if appearance is None:
        return None
    occurrences = {str(item.get("id") or ""): item for item in descriptor.get("occurrences") or []}
    for occurrence_id in appearance["assignments"]:
        target = occurrences.get(occurrence_id)
        if target is None or not target.get("component"):
            raise SidecarAppearanceError(f"appearance targets missing document occurrence {occurrence_id}")
    return appearance


def apply_appearance(descriptor: Mapping[str, Any], block: object) -> dict[str, Any]:
    """Compose artifact annotations into an owned descriptor, never a tree object."""
    appearance = validate_appearance_targets(descriptor, block)
    result = deepcopy(dict(descriptor))
    if appearance:
        materials = appearance["materials"]
        assignments = appearance["assignments"]
        for occurrence in result.get("occurrences") or []:
            material_id = assignments.get(occurrence.get("id"))
            if material_id is not None:
                authored = materials[material_id]
                occurrence["material"] = {
                    **SOURCE_MATERIAL_DEFAULTS,
                    **{key: authored[key] for key in _NUMERIC_MATERIAL_KEYS if key in authored},
                }
                occurrence["materialId"] = material_id
                occurrence["materialName"] = authored["name"]
                if "baseColor" in authored:
                    occurrence["baseColor"] = authored["baseColor"]
                else:
                    occurrence.pop("baseColor", None)
    return result


def _raw_source_sidecar(step_path: Path | str) -> dict[str, Any] | None:
    """The sidecar's JSON with NO schema gate. Only the writer's no-op compare
    and the schema gate itself may use this; every consumer of the SECTIONS
    goes through :func:`read_source_sidecar`."""
    try:
        payload = json.loads(source_sidecar_path(step_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def sidecar_schema_is_current(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload) and payload.get("schemaVersion") == SOURCE_SIDECAR_SCHEMA_VERSION


def _verified_document_hash(step_path: Path | str, document_hash: str | None) -> str:
    if document_hash is None:
        from cadgen._internal.step_hash import step_file_hash

        return step_file_hash(Path(step_path))
    digest = str(document_hash).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"document_hash must be a sha256 hex digest, got {document_hash!r}")
    return digest


def _binding_error(step_path: Path | str, found: object, expected: str) -> SidecarBindingError:
    artifact = Path(step_path)
    return SidecarBindingError(
        f"{source_sidecar_path(artifact).name}: documentHash {found or 'none'} does not match "
        f"{artifact.name} sha256 {expected} — rebuild the model (python {artifact.stem}.py) "
        f"or re-annotate the document (cadgen step build)"
    )


def read_source_sidecar(
    step_path: Path | str,
    *,
    document_hash: str | None = None,
) -> dict[str, Any] | None:
    """The document's declarations, or ``None`` when it has no sidecar.

    A sidecar that IS there must declare this schema: reading sections out of
    a file written to a different shape is how a model silently loses its
    kinematics. Missing/unreadable stays ``None`` (an import, or a plain model
    that declares nothing); wrong schema or a binding to different STEP bytes
    is an error with the fix. ``document_hash`` may carry a digest already
    computed from the bytes being resolved, avoiding a second read.
    """
    payload = _raw_source_sidecar(step_path)
    if payload is None:
        return None
    if not sidecar_schema_is_current(payload):
        found = payload.get("schemaVersion", "none")
        artifact = Path(step_path)
        # Says what is lost and that it is a migration to DO: read as a passing warning,
        # a model keeps shipping with no kinematics, materials or routines at all.
        raise SidecarSchemaError(
            f"{source_sidecar_path(artifact).name}: unsupported sidecar schema {found} "
            f"(expected {SOURCE_SIDECAR_SCHEMA_VERSION}), so the kinematics, materials and "
            f"animation it declares cannot be read and this model poses and plays nothing. "
            f"Migrate it now: rebuild the model (python {artifact.stem}.py) or re-annotate "
            f"the document (cadgen step build)"
        )
    expected = _verified_document_hash(step_path, document_hash)
    found = str(payload.get("documentHash") or "").strip().lower()
    if found != expected:
        raise _binding_error(step_path, found, expected)
    unknown = set(payload) - set(_SIDECAR_SECTIONS)
    if unknown:
        raise SidecarSchemaError(f"{source_sidecar_path(step_path).name}: unknown sidecar fields: {', '.join(sorted(unknown))}")
    if "appearance" in payload:
        payload["appearance"] = normalize_appearance(payload["appearance"])
    if "animation" in payload:
        payload["animation"] = normalize_animation(payload["animation"])
    return payload


def model_is_generated(step_path: Path | str) -> bool:
    """Whether this artifact carries a sidecar this cadgen reads. Never
    raises: classification is not a render, and the loud refusal belongs to
    the readers of the SECTIONS."""
    return source_sidecar_matches_document(step_path)


def source_sidecar_matches_document(
    step_path: Path | str,
    *,
    document_hash: str | None = None,
) -> bool:
    """Whether a sidecar is current and bound to these STEP bytes.

    Classification and current gates need a non-throwing predicate. Readers
    use :func:`read_source_sidecar` to receive the teaching error.
    """
    payload = _raw_source_sidecar(step_path)
    if not sidecar_schema_is_current(payload):
        return False
    try:
        expected = _verified_document_hash(step_path, document_hash)
    except (OSError, ValueError):
        return False
    found = str(payload.get("documentHash") or "").strip().lower()
    return found == expected


# The sections that WARRANT a sidecar. Provenance alone does not: it also
# lives in the assembly.json, and a file per plain model is pure clutter.
_WARRANTING_SECTIONS = ("kinematics", "appearance", "animation")


def sidecar_is_warranted(payload: Mapping[str, Any] | None) -> bool:
    """Whether this payload carries anything the model actually needs a
    sidecar FOR. Kinematics and PBR finishes have artifact consumers;
    metadata with no reader beside the artifact belongs in the
    record, not in a file."""
    if not payload:
        return False
    return any(payload.get(section) for section in _WARRANTING_SECTIONS)


def write_source_sidecar(
    step_path: Path | str,
    payload: Mapping[str, Any],
    *,
    document_hash: str | None = None,
) -> None:
    """Write the sidecar — or, for a payload that warrants none, remove any
    stale one (a model that DROPPED its kinematics must lose the file).
    The written ``documentHash`` describes the adjacent STEP bytes, or the
    caller's already-verified digest for those bytes. Only the FILE: the
    build's provenance record stays."""
    body = {k: v for k, v in payload.items() if k in _SIDECAR_SECTIONS}
    if "appearance" in body:
        body["appearance"] = normalize_appearance(body["appearance"])
        if body["appearance"] is None:
            body.pop("appearance")
    if "animation" in body:
        body["animation"] = normalize_animation(body["animation"])
        if body["animation"] is None:
            body.pop("animation")
    if not sidecar_is_warranted(body):
        source_sidecar_path(step_path).unlink(missing_ok=True)
        return
    target = source_sidecar_path(step_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body["schemaVersion"] = SOURCE_SIDECAR_SCHEMA_VERSION
    body["documentHash"] = _verified_document_hash(step_path, document_hash)
    # A rewrite that changes nothing but the timestamp is pure churn — for
    # committed sidecars (imported/ projects) it dirties git on every no-op.
    if _raw_source_sidecar(step_path) == body:
        return
    temp = target.with_name(f".{target.name}{temp_suffix()}")
    temp.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    replace_atomic(temp, target)


def remove_source_sidecar(step_path: Path | str) -> None:
    """Imports must never leave a stale generated-marker behind (e.g. a
    re-import over a model that used to be generated)."""
    source_sidecar_path(step_path).unlink(missing_ok=True)


def read_source_provenance(step_path: Path | str) -> dict[str, Any] | None:
    """The document's source provenance, read from the STORE RECORD of the model
    behind it (``cadgen.store.records``): sourceKind, the script path relative
    to the document, and the closure. ``None`` for a document with no record.

    The provenance record file this used to read is gone; the model record is
    the one freshness memory (STORE.md)."""
    from cadgen.store.records import record_for_document, source_for_document

    document = Path(step_path)
    record = record_for_document(document)
    if record is None:
        return None
    from cadgen.store.index import split_model_ref

    source, _function = split_model_ref(source_for_document(document))
    payload: dict[str, Any] = {
        "sourceKind": str(record.get("sourceKind") or "python"),
        "sourceClosureHash": str((record.get("closure") or {}).get("hash") or ""),
        "sourceClosureFiles": list((record.get("closure") or {}).get("files") or []),
        "tree": str(record.get("tree") or ""),
    }
    for key in ("sourceHash", "annotationHash", "kinematics", "stepHash"):
        if record.get(key) is not None:
            payload[key] = record[key]
    try:
        document_resolved = document.expanduser().resolve()
    except (OSError, RuntimeError):
        document_resolved = document
    if str(source) != str(document_resolved):
        import os

        try:
            payload["sourcePath"] = os.path.relpath(str(source), str(document_resolved.parent))
        except ValueError:
            payload["sourcePath"] = str(source)
    return payload
