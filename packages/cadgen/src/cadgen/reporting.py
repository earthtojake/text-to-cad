from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cadgen import analysis, lookup
from cadgen._internal.validators import geometry_summary_from_manifest


@dataclass(frozen=True)
class EntryReportOptions:
    json: bool = False
    facts: bool = False
    positioning: bool = False
    planes: bool = False
    topology: bool = False
    plane_coordinate_tolerance: float = 1e-3
    plane_min_area_ratio: float = 0.05
    plane_limit: int = 12

    @property
    def requested(self) -> bool:
        return self.json or self.facts or self.positioning or self.planes or self.topology

    @property
    def refs_required(self) -> bool:
        return self.facts or self.positioning or self.planes or self.topology


def entry_summary_payload(
    manifest: dict[str, Any],
    *,
    kind: str,
    selector_index: lookup.SelectorIndex | None = None,
) -> dict[str, object]:
    if selector_index is not None:
        summary = lookup.entry_summary(selector_index)
        summary["kind"] = kind
        return summary
    summary = geometry_summary_from_manifest(manifest)
    return {
        "kind": kind,
        "occurrenceCount": summary.get("occurrenceCount"),
        "shapeCount": summary.get("shapeCount"),
        "faceCount": summary.get("faceCount"),
        "edgeCount": summary.get("edgeCount"),
        "bounds": summary.get("bbox"),
    }


def major_planes_payload(
    selector_index: lookup.SelectorIndex | None,
    options: EntryReportOptions,
) -> list[dict[str, object]]:
    if selector_index is None:
        return []
    return analysis.major_planar_face_groups(
        selector_index,
        coordinate_tolerance=options.plane_coordinate_tolerance,
        min_area_ratio=options.plane_min_area_ratio,
        limit=options.plane_limit,
    )


def entry_facts_payload(
    manifest: dict[str, Any],
    *,
    kind: str,
    selector_index: lookup.SelectorIndex | None = None,
    options: EntryReportOptions = EntryReportOptions(),
    major_planes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    facts = analysis.bbox_facts(manifest.get("bbox"))
    facts["kind"] = kind
    return facts


def entry_positioning_payload(
    manifest: dict[str, Any],
    *,
    kind: str,
    selector_index: lookup.SelectorIndex | None = None,
    options: EntryReportOptions = EntryReportOptions(),
    major_planes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": kind,
        "bbox": manifest.get("bbox"),
    }
    bbox_facts = analysis.bbox_facts(manifest.get("bbox"))
    if bbox_facts:
        payload["bboxFacts"] = bbox_facts
    if selector_index is not None and major_planes is not None:
        payload["majorPlanes"] = major_planes
    return payload


def entry_report_payload(
    manifest: dict[str, Any],
    *,
    kind: str,
    options: EntryReportOptions,
    selector_index: lookup.SelectorIndex | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": entry_summary_payload(manifest, kind=kind, selector_index=selector_index),
    }
    major_planes = (
        major_planes_payload(selector_index, options)
        if selector_index is not None and options.planes
        else None
    )
    if options.facts:
        payload["entryFacts"] = entry_facts_payload(
            manifest,
            kind=kind,
            selector_index=selector_index,
            options=options,
            major_planes=major_planes,
        )
    if options.positioning:
        payload["entryPositioning"] = entry_positioning_payload(
            manifest,
            kind=kind,
            selector_index=selector_index,
            options=options,
            major_planes=major_planes,
        )
    if options.planes:
        payload["planes"] = major_planes if major_planes is not None else []
    if options.topology and selector_index is not None:
        payload["topology"] = lookup.topology_payload(selector_index)
    return payload
