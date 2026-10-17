from __future__ import annotations

from collections.abc import Mapping
from typing import Any

STEP_EDGE_CLASSIFICATION_ALGORITHM = "oc-brep-continuity-v1"
STEP_EDGE_SURFACE_ALGORITHM = "oc-polygon-on-triangulation-v1"
STEP_EDGE_ANGULAR_TOLERANCE_DEG = 2
STEP_EDGE_SAMPLE_COUNT = 3
STEP_EDGE_BARYCENTRIC_ATTRIBUTE = "_CAD_EDGE_BARYCENTRIC"
STEP_EDGE_CLASS_ATTRIBUTE = "_CAD_EDGE_CLASS"
STEP_EDGE_FLAGS = {
    "DEGENERATE": 1 << 1,
    "SEAM": 1 << 2,
    "NOT_REFERENCEABLE": 1 << 3,
    "BOUNDARY": 1 << 4,
    "NON_MANIFOLD": 1 << 5,
    "HARD": 1 << 6,
    "TANGENT": 1 << 7,
    "UNKNOWN_CONTINUITY": 1 << 8,
}
STEP_EDGE_VISIBILITY_CLASSES = {
    "FEATURE": "feature",
    "TANGENT": "tangent",
    "SEAM": "seam",
    "DEGENERATE": "degenerate",
    "BOUNDARY": "boundary",
    "NON_MANIFOLD": "nonManifold",
    "UNKNOWN": "unknown",
}
STEP_EDGE_RENDER_VISIBILITY_CLASSES = (
    STEP_EDGE_VISIBILITY_CLASSES["FEATURE"],
    STEP_EDGE_VISIBILITY_CLASSES["TANGENT"],
    STEP_EDGE_VISIBILITY_CLASSES["SEAM"],
    STEP_EDGE_VISIBILITY_CLASSES["DEGENERATE"],
)
STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES = STEP_EDGE_RENDER_VISIBILITY_CLASSES
STEP_EDGE_SURFACE_CLASS_CODES = {
    "none": 0,
    "feature": 1,
    "tangent": 2,
    "seam": 3,
    "degenerate": 4,
    "boundary": 5,
    "nonManifold": 6,
    "unknown": 7,
}


def normalize_step_edge_render_visibility_classes(value: object) -> tuple[str, ...]:
    if value is None:
        return STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES
    raw_values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    valid_values = set(STEP_EDGE_VISIBILITY_CLASSES.values())
    normalized: list[str] = []
    for raw in raw_values:
        normalized_value = str(raw or "").strip()
        if normalized_value in valid_values and normalized_value not in normalized:
            normalized.append(normalized_value)
    if STEP_EDGE_VISIBILITY_CLASSES["FEATURE"] not in normalized:
        normalized.insert(0, STEP_EDGE_VISIBILITY_CLASSES["FEATURE"])
    ordered = [
        class_id
        for class_id in STEP_EDGE_RENDER_VISIBILITY_CLASSES
        if class_id in normalized
    ]
    extras = [
        class_id
        for class_id in normalized
        if class_id not in STEP_EDGE_RENDER_VISIBILITY_CLASSES
    ]
    return tuple(ordered + extras)


def step_edge_capabilities(
    edge_visibility_classes: object = None,
) -> dict[str, Any]:
    visibility_classes = normalize_step_edge_render_visibility_classes(edge_visibility_classes)
    return {
        "edgeClassification": {
            "algorithm": STEP_EDGE_CLASSIFICATION_ALGORITHM,
            "angularToleranceDeg": STEP_EDGE_ANGULAR_TOLERANCE_DEG,
            "samples": STEP_EDGE_SAMPLE_COUNT,
        },
        "surfaceEdgeRendering": {
            "algorithm": STEP_EDGE_SURFACE_ALGORITHM,
            "primitiveAttributes": {
                "barycentric": STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
                "class": STEP_EDGE_CLASS_ATTRIBUTE,
            },
            "classCodes": STEP_EDGE_SURFACE_CLASS_CODES,
            "visibilityClasses": list(visibility_classes),
        },
    }


