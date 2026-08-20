from __future__ import annotations

from typing import Any

from cadgen.analysis import AXIS_INDEX, bbox_center, bbox_size, major_planar_face_groups
from cadgen.lookup import build_selector_index


def axis_index(axis: str) -> int:
    normalized = str(axis or "").strip().lower()
    if normalized not in AXIS_INDEX:
        raise ValueError(f"Axis must be one of x, y, z; got {axis!r}")
    return int(AXIS_INDEX[normalized])


def _coerce_bbox(bbox: object) -> dict[str, object]:
    if not isinstance(bbox, dict):
        raise ValueError("Expected bbox dict with min/max coordinates.")
    if not isinstance(bbox.get("min"), list) or not isinstance(bbox.get("max"), list):
        raise ValueError("BBox dict must include min/max coordinate lists.")
    return bbox


def bbox_coordinate(bbox: object, axis: str, side: str) -> float:
    normalized_bbox = _coerce_bbox(bbox)
    axis_idx = axis_index(axis)
    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"min", "max"}:
        raise ValueError(f"Side must be 'min' or 'max'; got {side!r}")
    return float(normalized_bbox[normalized_side][axis_idx])


def bbox_span(bbox: object, axis: str) -> float:
    size = bbox_size(_coerce_bbox(bbox))
    if size is None:
        raise ValueError("Failed to compute bbox span.")
    return float(size[axis_index(axis)])


def assert_close(actual: float, expected: float, *, tol: float = 1e-6, label: str = "value") -> float:
    actual_value = float(actual)
    expected_value = float(expected)
    if abs(actual_value - expected_value) > float(tol):
        raise AssertionError(
            f"{label} mismatch: expected {expected_value:.6f}, got {actual_value:.6f} (tol={float(tol):.6f})"
        )
    return actual_value


def assert_bbox_coordinate(
    bbox: object,
    axis: str,
    side: str,
    expected: float,
    *,
    tol: float = 1e-6,
    label: str | None = None,
) -> float:
    actual = bbox_coordinate(bbox, axis, side)
    return assert_close(actual, expected, tol=tol, label=label or f"bbox {side} {axis}")


def assert_bbox_span(
    bbox: object,
    axis: str,
    expected: float,
    *,
    tol: float = 1e-6,
    label: str | None = None,
) -> float:
    actual = bbox_span(bbox, axis)
    return assert_close(actual, expected, tol=tol, label=label or f"bbox span {axis}")


def selector_count(manifest: dict[str, Any], selector_type: str) -> int:
    stats = manifest.get("stats")
    if not isinstance(stats, dict):
        return 0
    if selector_type == "shape":
        return int(stats.get("shapeCount") or 0)
    if selector_type == "face":
        return int(stats.get("faceCount") or 0)
    if selector_type == "edge":
        return int(stats.get("edgeCount") or 0)
    if selector_type == "occurrence":
        return int(stats.get("occurrenceCount") or 0)
    raise ValueError(f"Unsupported selector_type {selector_type!r}")


def assert_selector_count(
    manifest: dict[str, Any],
    selector_type: str,
    expected: int,
    *,
    label: str | None = None,
) -> int:
    actual = selector_count(manifest, selector_type)
    if actual != int(expected):
        raise AssertionError(f"{label or selector_type} count mismatch: expected {int(expected)}, got {actual}")
    return actual


def geometry_summary_from_manifest(manifest: dict[str, Any]) -> dict[str, object]:
    bbox = _coerce_bbox(manifest.get("bbox"))
    summary: dict[str, object] = {
        "bbox": bbox,
        "center": bbox_center(bbox),
        "size": bbox_size(bbox),
        "occurrenceCount": selector_count(manifest, "occurrence"),
        "shapeCount": selector_count(manifest, "shape"),
        "faceCount": selector_count(manifest, "face"),
        "edgeCount": selector_count(manifest, "edge"),
    }
    try:
        index = build_selector_index(manifest)
    except Exception:  # noqa: BLE001 - a selector-index build failure must not fail the manifest summary
        return summary
    summary["majorPlanes"] = major_planar_face_groups(index)
    return summary
