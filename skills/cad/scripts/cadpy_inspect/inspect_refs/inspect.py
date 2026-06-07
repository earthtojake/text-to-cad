from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cadpy import cad_ref_syntax as syntax
from cadpy.reporting import (
    EntryReportOptions,
    entry_facts_payload,
    entry_positioning_payload,
    entry_report_payload,
    entry_summary_payload,
    major_planes_payload,
)
from cadpy.selector_types import SelectorProfile
from cadpy.step_targets import (
    CadRefError,
    ResolvedStepTarget,
    cad_path_from_target,
    cad_ref_error_payload,
    entry_target_from_target,
    resolve_step_target,
    step_path_from_target,
)
from cadpy import analysis
from cadpy import lookup

REPO_ROOT = Path.cwd().resolve()


@dataclass
class EntryContext:
    cad_path: str
    kind: str
    source_path: Path
    step_path: Path | None
    manifest: dict[str, object]
    selector_index: lookup.SelectorIndex | None


@dataclass
class TargetSelection:
    context: EntryContext
    selector_type: str
    row: dict[str, object]
    normalized_selector: str
    display_selector: str
    copy_text: str


EntryContextProvider = Callable[[str, SelectorProfile], EntryContext | None]


def inspect_cad_refs(
    entry_target: str,
    refs_text: str = "",
    *,
    detail: bool = False,
    include_topology: bool = False,
    facts: bool = False,
    positioning: bool = False,
    planes: bool = False,
    plane_coordinate_tolerance: float = 1e-3,
    plane_min_area_ratio: float = 0.05,
    plane_limit: int = 12,
    context_provider: EntryContextProvider | None = None,
) -> dict[str, object]:
    entry = entry_target_from_target(entry_target)
    parsed_tokens = _parse_entry_ref_tokens(entry.cad_path, refs_text)
    if not parsed_tokens:
        raise CadRefError(
            "No selector ref found. Expected refs like #o<path>, #o<path>.s<n>, #o<path>.f<n>, "
            "#o<path>.e<n>, #o<path>.v<n>, #m<n>, or #s<n>/#f<n>/#e<n>/#v<n> "
            "for single-occurrence entries."
        )

    contexts: dict[str, EntryContext] = {}
    errors: list[dict[str, object]] = []
    token_results: list[dict[str, object]] = []
    refs_required_by_cad_path: dict[str, bool] = {}
    report_options = EntryReportOptions(
        facts=facts,
        positioning=positioning,
        planes=planes,
        topology=include_topology,
        plane_coordinate_tolerance=plane_coordinate_tolerance,
        plane_min_area_ratio=plane_min_area_ratio,
        plane_limit=plane_limit,
    )

    for parsed in parsed_tokens:
        selectors = parsed.selectors or ()
        refs_required_by_cad_path[parsed.cad_path] = (
            refs_required_by_cad_path.get(parsed.cad_path, False)
            or bool(selectors)
            or report_options.refs_required
        )

    for parsed in parsed_tokens:
        context = contexts.get(parsed.cad_path)
        if context is None:
            try:
                context = _load_entry_context(
                    parsed.cad_path,
                    profile=SelectorProfile.REFS if refs_required_by_cad_path.get(parsed.cad_path) else SelectorProfile.SUMMARY,
                    context_provider=context_provider,
                )
            except CadRefError as exc:
                error = cad_ref_error_payload(exc)
                error.setdefault("line", parsed.line)
                error.setdefault("cadPath", parsed.cad_path)
                error.setdefault("selector", None)
                error.setdefault("kind", "input")
                errors.append(error)
                token_results.append(
                    {
                        "line": parsed.line,
                        "token": parsed.token,
                        "cadPath": parsed.cad_path,
                        "stepPath": "",
                        "summary": {},
                        "selections": [],
                        "warnings": [],
                    }
                )
                continue
            contexts[parsed.cad_path] = context

        token_result: dict[str, object] = {
            "line": parsed.line,
            "token": parsed.token,
            "cadPath": parsed.cad_path,
            "stepPath": _relative_to_repo(context.step_path) if context.step_path is not None else "",
            "stepHash": context.manifest.get("stepHash"),
            "summary": _entry_summary(context),
            "selections": [],
            "warnings": [],
        }
        report_payload = entry_report_payload(
            context.manifest,
            kind=context.kind,
            options=report_options,
            selector_index=context.selector_index,
        )
        token_result["summary"] = report_payload["summary"]
        if facts and "entryFacts" in report_payload:
            token_result["entryFacts"] = report_payload["entryFacts"]
        if planes and "planes" in report_payload:
            token_result["planes"] = report_payload["planes"]

        if parsed.selectors:
            for raw_selector in parsed.selectors:
                selection, selection_error = _inspect_selector(
                    parsed.cad_path,
                    raw_selector,
                    context,
                    detail=detail,
                    facts=facts,
                    positioning=positioning,
                )
                token_result["selections"].append(selection)
                if selection_error is not None:
                    errors.append(
                        {
                            "line": parsed.line,
                            "cadPath": parsed.cad_path,
                            "selector": raw_selector,
                            **selection_error,
                        }
                    )
        else:
            if include_topology and "topology" in report_payload:
                token_result["topology"] = report_payload["topology"]
            if positioning and "entryPositioning" in report_payload:
                token_result["entryPositioning"] = report_payload["entryPositioning"]

        token_results.append(token_result)

    return {
        "ok": not errors,
        "tokens": token_results,
        "errors": errors,
    }


def _parse_entry_ref_tokens(cad_path: str, refs_text: str = "") -> list[syntax.ParsedToken]:
    text = str(refs_text or "").strip()
    if not text:
        return [
            syntax.ParsedToken(
                line=1,
                token=syntax.build_cad_token(cad_path),
                cad_path=cad_path,
                selectors=(),
            )
        ]
    tokens: list[syntax.ParsedToken] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        normalized_line = line.strip()
        if not normalized_line:
            continue
        parsed_tokens = syntax.parse_cad_tokens(normalized_line)
        if len(parsed_tokens) != 1 or parsed_tokens[0].token.strip() != normalized_line:
            raise CadRefError(f"Invalid selector ref {normalized_line!r}; expected #o1.2, #f1, #m1, or #o1.2.f1.")
        parsed = parsed_tokens[0]
        tokens.append(
            syntax.ParsedToken(
                line=line_no,
                token=parsed.token,
                cad_path=cad_path,
                selectors=parsed.selectors,
            )
        )
    return tokens


def _relative_to_repo(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_entry_context(
    cad_path: str,
    *,
    profile: SelectorProfile,
    context_provider: EntryContextProvider | None = None,
) -> EntryContext:
    if context_provider is not None:
        context = context_provider(cad_path, profile)
        if context is not None:
            return context

    target = resolve_step_target(cad_path)
    return _load_step_context(target, profile=profile)


def _load_step_context(
    target: ResolvedStepTarget,
    *,
    profile: SelectorProfile,
) -> EntryContext:
    from cadpy.step_artifacts import ensure_step_topology_artifact

    artifact = ensure_step_topology_artifact(
        target,
        require_selector=(profile != SelectorProfile.SUMMARY),
    )
    if artifact.selector_bundle is None:
        manifest = artifact.manifest
        selector_index = None
    else:
        manifest = artifact.selector_bundle.manifest
        selector_index = lookup.build_selector_index(manifest, buffers=artifact.selector_bundle.buffers)

    resolved_kind = _entry_kind_from_manifest(manifest, fallback=target.kind)
    return EntryContext(
        cad_path=target.cad_path,
        kind=resolved_kind,
        source_path=target.source_path,
        step_path=target.step_path,
        manifest=manifest,
        selector_index=selector_index,
    )


def _entry_kind_from_manifest(manifest: dict[str, object], *, fallback: str) -> str:
    entry_kind = str(manifest.get("entryKind") or "").strip().lower()
    if entry_kind in {"part", "assembly"}:
        return entry_kind
    assembly = manifest.get("assembly")
    if isinstance(assembly, dict):
        return "assembly"
    return fallback if fallback in {"part", "assembly"} else "part"


def _entry_summary(context: EntryContext) -> dict[str, object]:
    return entry_summary_payload(
        context.manifest,
        kind=context.kind,
        selector_index=context.selector_index,
    )


def _selection_label(selector_type: str, display_selector: str) -> str:
    noun = {
        "occurrence": "Occurrence",
        "shape": "Shape",
        "face": "Face",
        "edge": "Edge",
        "vertex": "Corner",
    }.get(selector_type, "Reference")
    return f"{noun} {display_selector}"


def _selection_summary(selector_type: str, row: dict[str, object]) -> str:
    if selector_type == "occurrence":
        name = str(row.get("name") or row.get("sourceName") or "").strip()
        return name or str(row.get("id") or "")
    if selector_type == "shape":
        kind = str(row.get("kind") or "shape")
        volume = row.get("volume")
        area = row.get("area")
        if volume not in {None, ""}:
            return f"{kind} volume={volume}"
        if area not in {None, ""}:
            return f"{kind} area={area}"
        return kind
    if selector_type == "face":
        return f"{row.get('surfaceType')} area={row.get('area')}"
    if selector_type == "edge":
        return f"{row.get('curveType')} length={row.get('length')}"
    return f"corner edges={row.get('edgeCount')}"


def _assembly_mate_rows(manifest: dict[str, object]) -> list[dict[str, object]]:
    rows = manifest.get("assemblyMates")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _assembly_mate_by_selector(context: EntryContext, raw_selector: str) -> dict[str, object] | None:
    normalized_selector = str(raw_selector or "").strip().replace("#", "", 1)
    if not normalized_selector:
        return None
    for row in _assembly_mate_rows(context.manifest):
        if str(row.get("id") or "").strip() == normalized_selector:
            return row
    return None


def _looks_like_assembly_mate_selector(raw_selector: str) -> bool:
    selector = str(raw_selector or "").strip().replace("#", "", 1)
    return len(selector) > 1 and selector[0] == "m" and selector[1:].isdigit()


def _assembly_mate_label(row: dict[str, object], selector: str) -> str:
    return (
        str(row.get("sourceLabel") or "").strip()
        or str(row.get("name") or "").strip()
        or str(row.get("label") or "").strip()
        or selector
    )


def _assembly_mate_summary(row: dict[str, object]) -> str:
    relation = str(row.get("type") or row.get("relation") or "mate").strip() or "mate"
    fixed = str(row.get("fixed") or "").strip()
    moving = str(row.get("moving") or "").strip()
    endpoints = f"{fixed} -> {moving}" if fixed and moving else fixed or moving
    return " ".join(part for part in (relation, endpoints) if part)


def _assembly_mate_detail(row: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": row.get("id"),
        "label": row.get("label"),
        "sourceLabel": row.get("sourceLabel"),
        "type": row.get("type") or row.get("relation"),
        "fixed": row.get("fixed"),
        "moving": row.get("moving"),
    }
    for key in ("parameters", "fixedEndpoint", "movingEndpoint"):
        if key in row:
            payload[key] = row.get(key)
    return payload


def _inspect_assembly_mate(
    cad_path: str,
    raw_selector: str,
    context: EntryContext,
    *,
    detail: bool,
    positioning: bool,
) -> tuple[dict[str, object], dict[str, object] | None]:
    selector = str(raw_selector or "").strip().replace("#", "", 1)
    row = _assembly_mate_by_selector(context, selector)
    if row is None:
        return (
            {
                "status": "error",
                "selectorType": "mate" if _looks_like_assembly_mate_selector(selector) else "opaque",
                "normalizedSelector": selector,
                "displaySelector": selector,
            },
            {
                "kind": "selector",
                "message": f"Selector '{raw_selector}' did not resolve against {cad_path}.",
            },
        )

    mate_id = str(row.get("id") or selector).strip() or selector
    selection: dict[str, object] = {
        "status": "resolved",
        "selectorType": "mate",
        "normalizedSelector": mate_id,
        "displaySelector": mate_id,
        "copyText": syntax.build_cad_token(cad_path, mate_id),
        "label": f"Mate {_assembly_mate_label(row, mate_id)}",
        "summary": _assembly_mate_summary(row),
    }
    if detail:
        selection["detail"] = _assembly_mate_detail(row)
    if positioning:
        selection["positioning"] = {
            "selectorType": "mate",
            "selector": mate_id,
            "fixedEndpoint": row.get("fixedEndpoint"),
            "movingEndpoint": row.get("movingEndpoint"),
        }
    return selection, None


def _occurrence_detail(row: dict[str, object], selector_index: lookup.SelectorIndex) -> dict[str, object]:
    occurrence_id = str(row.get("id") or "").strip()
    child_rows = [
        child
        for child in selector_index.occurrences
        if str(child.get("parentId") or "").strip() == occurrence_id
    ]
    descendant_ids: list[str] = []
    stack = list(reversed(child_rows))
    while stack:
        child = stack.pop()
        child_id = str(child.get("id") or "").strip()
        if child_id:
            descendant_ids.append(lookup.display_selector(child_id, selector_index))
            stack.extend(
                grandchild
                for grandchild in reversed(selector_index.occurrences)
                if str(grandchild.get("parentId") or "").strip() == child_id
            )
    return {
        "path": row.get("path"),
        "name": row.get("name"),
        "sourceName": row.get("sourceName"),
        "parentId": lookup.display_selector(str(row.get("parentId") or ""), selector_index),
        "childCount": len(child_rows),
        "descendantOccurrenceIds": descendant_ids,
        "transform": row.get("transform"),
        "bbox": row.get("bbox"),
        "shapeCount": row.get("shapeCount"),
        "faceCount": row.get("faceCount"),
        "edgeCount": row.get("edgeCount"),
        "vertexCount": row.get("vertexCount"),
    }


def _shape_detail(row: dict[str, object], selector_index: lookup.SelectorIndex) -> dict[str, object]:
    return {
        "occurrenceId": lookup.display_selector(str(row.get("occurrenceId") or ""), selector_index),
        "kind": row.get("kind"),
        "bbox": row.get("bbox"),
        "center": row.get("center"),
        "area": row.get("area"),
        "volume": row.get("volume"),
        "faceCount": row.get("faceCount"),
        "edgeCount": row.get("edgeCount"),
        "vertexCount": row.get("vertexCount"),
    }


def _face_detail(row: dict[str, object], selector_index: lookup.SelectorIndex) -> dict[str, object]:
    adjacent_edges = [
        lookup.display_selector(selector, selector_index)
        for selector in lookup.face_adjacent_edge_selectors(row, selector_index)
    ]
    return {
        "occurrenceId": lookup.display_selector(str(row.get("occurrenceId") or ""), selector_index),
        "shapeId": lookup.display_selector(str(row.get("shapeId") or ""), selector_index),
        "surfaceType": row.get("surfaceType"),
        "area": row.get("area"),
        "center": row.get("center"),
        "normal": row.get("normal"),
        "bbox": row.get("bbox"),
        "params": row.get("params"),
        "adjacentEdgeSelectors": adjacent_edges,
    }


def _edge_detail(row: dict[str, object], selector_index: lookup.SelectorIndex) -> dict[str, object]:
    adjacent_faces = [
        lookup.display_selector(selector, selector_index)
        for selector in lookup.edge_adjacent_face_selectors(row, selector_index)
    ]
    adjacent_vertices = [
        lookup.display_selector(selector, selector_index)
        for selector in lookup.edge_adjacent_vertex_selectors(row, selector_index)
    ]
    return {
        "occurrenceId": lookup.display_selector(str(row.get("occurrenceId") or ""), selector_index),
        "shapeId": lookup.display_selector(str(row.get("shapeId") or ""), selector_index),
        "curveType": row.get("curveType"),
        "length": row.get("length"),
        "center": row.get("center"),
        "bbox": row.get("bbox"),
        "params": row.get("params"),
        "adjacentFaceSelectors": adjacent_faces,
        "adjacentVertexSelectors": adjacent_vertices,
    }


def _vertex_detail(row: dict[str, object], selector_index: lookup.SelectorIndex) -> dict[str, object]:
    adjacent_edges = [
        lookup.display_selector(selector, selector_index)
        for selector in lookup.vertex_adjacent_edge_selectors(row, selector_index)
    ]
    adjacent_faces = [
        lookup.display_selector(selector, selector_index)
        for selector in lookup.vertex_adjacent_face_selectors(row, selector_index)
    ]
    return {
        "occurrenceId": lookup.display_selector(str(row.get("occurrenceId") or ""), selector_index),
        "shapeId": lookup.display_selector(str(row.get("shapeId") or ""), selector_index),
        "center": row.get("center"),
        "bbox": row.get("bbox"),
        "adjacentEdgeSelectors": adjacent_edges,
        "adjacentFaceSelectors": adjacent_faces,
    }


def _inspect_selector(
    cad_path: str,
    raw_selector: str,
    context: EntryContext,
    *,
    detail: bool,
    facts: bool,
    positioning: bool,
) -> tuple[dict[str, object], dict[str, object] | None]:
    parsed_selector = syntax.parse_selector(raw_selector)
    if parsed_selector is None:
        return (
            {
                "status": "error",
                "selectorType": "unknown",
                "normalizedSelector": raw_selector,
                "displaySelector": raw_selector,
            },
            {
                "kind": "selector",
                "message": f"Unsupported selector '{raw_selector}'.",
            },
        )

    if parsed_selector.selector_type == "opaque":
        mate_selection, mate_error = _inspect_assembly_mate(
            cad_path,
            raw_selector,
            context,
            detail=detail,
            positioning=positioning,
        )
        if mate_error is None or _looks_like_assembly_mate_selector(raw_selector):
            return mate_selection, mate_error

    if context.selector_index is None:
        raise CadRefError(f"Selector index unavailable for {cad_path}")

    lookup_result = lookup.lookup_selector(raw_selector, context.selector_index)
    normalized_selector = lookup.canonicalize_selector(raw_selector, context.selector_index) or parsed_selector.canonical
    display_selector = lookup.display_selector(normalized_selector, context.selector_index)
    if lookup_result is None:
        return (
            {
                "status": "error",
                "selectorType": parsed_selector.selector_type,
                "normalizedSelector": normalized_selector,
                "displaySelector": display_selector,
            },
            {
                "kind": "selector",
                "message": f"Selector '{raw_selector}' did not resolve against {cad_path}.",
            },
        )

    selector_type, row = lookup_result
    selection: dict[str, object] = {
        "status": "resolved",
        "selectorType": selector_type,
        "normalizedSelector": normalized_selector,
        "displaySelector": display_selector,
        "copyText": syntax.build_cad_token(cad_path, display_selector),
        "label": _selection_label(selector_type, display_selector),
        "summary": _selection_summary(selector_type, row),
    }
    if detail:
        if selector_type == "occurrence":
            selection["detail"] = _occurrence_detail(row, context.selector_index)
        elif selector_type == "shape":
            selection["detail"] = _shape_detail(row, context.selector_index)
        elif selector_type == "face":
            selection["detail"] = _face_detail(row, context.selector_index)
        elif selector_type == "edge":
            selection["detail"] = _edge_detail(row, context.selector_index)
        elif selector_type == "vertex":
            selection["detail"] = _vertex_detail(row, context.selector_index)
    if facts:
        selection["geometryFacts"] = analysis.geometry_facts_for_row(selector_type, row, context.selector_index)
    if positioning:
        selection["positioning"] = analysis.positioning_facts_for_row(selector_type, row, context.selector_index)
    return selection, None


def _entry_facts(context: EntryContext) -> dict[str, object]:
    return entry_facts_payload(context.manifest, kind=context.kind, selector_index=context.selector_index)


def _entry_positioning(context: EntryContext) -> dict[str, object]:
    return entry_positioning_payload(context.manifest, kind=context.kind, selector_index=context.selector_index)


def load_entry_context_for_target(
    target: str,
    *,
    profile: SelectorProfile = SelectorProfile.REFS,
    context_provider: EntryContextProvider | None = None,
) -> EntryContext:
    return _load_entry_context(cad_path_from_target(target), profile=profile, context_provider=context_provider)


def _parse_single_target_token(entry_target_text: str, selector: str = "") -> syntax.ParsedToken:
    entry_target = entry_target_from_target(entry_target_text)
    selector_text = str(selector or "").strip()
    if not selector_text:
        selectors: tuple[str, ...] = ()
    else:
        parsed_tokens = syntax.parse_cad_tokens(selector_text)
        if len(parsed_tokens) != 1 or parsed_tokens[0].token.strip() != selector_text:
            raise CadRefError(f"Expected exactly one selector ref such as #o1.2.f1; got {selector!r}.")
        selectors = parsed_tokens[0].selectors
    return syntax.ParsedToken(
        line=1,
        token=syntax.build_cad_token(entry_target.cad_path, ",".join(selectors)),
        cad_path=entry_target.cad_path,
        selectors=selectors,
    )


def _default_root_occurrence(index: lookup.SelectorIndex) -> dict[str, object]:
    roots = [
        row
        for row in index.occurrences
        if row.get("parentId") in {None, ""}
    ]
    if len(roots) == 1:
        return roots[0]
    if len(index.occurrences) == 1:
        return index.occurrences[0]
    raise CadRefError("Target has no selector and does not have exactly one root occurrence.")


def resolve_target_selection(
    entry_target: str,
    selector: str = "",
    *,
    default_root_occurrence: bool = False,
    context_provider: EntryContextProvider | None = None,
) -> TargetSelection:
    parsed = _parse_single_target_token(entry_target, selector)
    context = _load_entry_context(parsed.cad_path, profile=SelectorProfile.REFS, context_provider=context_provider)
    if context.selector_index is None:
        raise CadRefError(f"Selector index unavailable for {parsed.cad_path}")

    selectors = parsed.selectors
    if not selectors:
        if not default_root_occurrence:
            raise CadRefError(f"Expected a selector ref for target {entry_target!r}.")
        row = _default_root_occurrence(context.selector_index)
        normalized_selector = str(row.get("id") or "")
        display_selector = lookup.display_selector(normalized_selector, context.selector_index)
        return TargetSelection(
            context=context,
            selector_type="occurrence",
            row=row,
            normalized_selector=normalized_selector,
            display_selector=display_selector,
            copy_text=syntax.build_cad_token(parsed.cad_path, display_selector),
        )
    if len(selectors) != 1:
        raise CadRefError(f"Expected exactly one selector in target {entry_target!r}.")

    raw_selector = selectors[0]
    lookup_result = lookup.lookup_selector(raw_selector, context.selector_index)
    if lookup_result is None:
        raise CadRefError(f"Selector '{raw_selector}' did not resolve against {parsed.cad_path}.")
    selector_type, row = lookup_result
    normalized_selector = lookup.canonicalize_selector(raw_selector, context.selector_index) or raw_selector
    display_selector = lookup.display_selector(normalized_selector, context.selector_index)
    return TargetSelection(
        context=context,
        selector_type=selector_type,
        row=row,
        normalized_selector=normalized_selector,
        display_selector=display_selector,
        copy_text=syntax.build_cad_token(parsed.cad_path, display_selector),
    )


def _selection_positioning_payload(selection: TargetSelection) -> dict[str, object]:
    return analysis.positioning_facts_for_row(
        selection.selector_type,
        selection.row,
        selection.context.selector_index,
    )


def _selection_result_payload(selection: TargetSelection) -> dict[str, object]:
    return {
        "cadPath": selection.context.cad_path,
        "stepPath": _relative_to_repo(selection.context.step_path) if selection.context.step_path is not None else "",
        "selectorType": selection.selector_type,
        "normalizedSelector": selection.normalized_selector,
        "displaySelector": selection.display_selector,
        "copyText": selection.copy_text,
    }


def _axis_or_infer(axis: str | None, *positioning: dict[str, object]) -> str:
    if axis is not None and str(axis).strip():
        normalized = str(axis).strip().lower()
        if normalized not in analysis.AXIS_INDEX:
            raise CadRefError(f"Axis must be one of x, y, z; got {axis!r}.")
        return normalized
    inferred = analysis.infer_positioning_axis(*positioning)
    if inferred is None:
        raise CadRefError("Could not infer a shared axis; pass --axis x, --axis y, or --axis z.")
    return inferred


def _primary_vector(positioning: dict[str, object]) -> object:
    for key in ("normal", "direction", "axisVector"):
        value = positioning.get(key)
        if value is not None and value != "":
            return value
    return None


def inspect_target_frame(
    entry_target: str,
    selector: str = "",
    *,
    context_provider: EntryContextProvider | None = None,
) -> dict[str, object]:
    selection = resolve_target_selection(entry_target, selector, default_root_occurrence=True, context_provider=context_provider)
    if selection.selector_type == "occurrence":
        occurrence_row = selection.row
    else:
        occurrence_id = str(selection.row.get("occurrenceId") or "")
        occurrence_row = selection.context.selector_index.occurrence_by_id.get(occurrence_id) if selection.context.selector_index else None
        if occurrence_row is None:
            raise CadRefError(f"Target {entry_target!r} does not resolve to an occurrence-backed selector.")
    frame = analysis.positioning_facts_for_row("occurrence", occurrence_row, selection.context.selector_index)
    result = {
        "ok": True,
        **_selection_result_payload(selection),
        "frame": frame,
    }
    if selection.selector_type != "occurrence":
        result["selectionPositioning"] = _selection_positioning_payload(selection)
    return result


def measure_targets(
    entry_target: str,
    from_selector: str,
    to_selector: str,
    *,
    axis: str | None = None,
    context_provider: EntryContextProvider | None = None,
) -> dict[str, object]:
    from_selection = resolve_target_selection(entry_target, from_selector, default_root_occurrence=True, context_provider=context_provider)
    to_selection = resolve_target_selection(entry_target, to_selector, default_root_occurrence=True, context_provider=context_provider)
    from_positioning = _selection_positioning_payload(from_selection)
    to_positioning = _selection_positioning_payload(to_selection)
    resolved_axis = _axis_or_infer(axis, from_positioning, to_positioning)
    from_coordinate = analysis.positioning_coordinate(from_positioning, resolved_axis)
    to_coordinate = analysis.positioning_coordinate(to_positioning, resolved_axis)
    if from_coordinate is None or to_coordinate is None:
        raise CadRefError(f"Could not compute {resolved_axis}-axis coordinates for both targets.")

    from_point = analysis.positioning_point(from_positioning)
    to_point = analysis.positioning_point(to_positioning)
    euclidean_distance = None
    if from_point is not None and to_point is not None:
        euclidean_distance = sum(
            (float(to_point[index]) - float(from_point[index])) ** 2
            for index in range(3)
        ) ** 0.5

    vector_relationship = analysis.vector_relationship(
        _primary_vector(from_positioning),
        _primary_vector(to_positioning),
    )
    signed_distance = float(to_coordinate[0] - from_coordinate[0])
    return {
        "ok": True,
        "axis": resolved_axis,
        "from": {
            **_selection_result_payload(from_selection),
            "positioning": from_positioning,
            "coordinate": from_coordinate[0],
            "coordinateSource": from_coordinate[1],
        },
        "to": {
            **_selection_result_payload(to_selection),
            "positioning": to_positioning,
            "coordinate": to_coordinate[0],
            "coordinateSource": to_coordinate[1],
        },
        "measurement": {
            "signedDistance": signed_distance,
            "absoluteDistance": abs(signed_distance),
            "euclideanDistance": euclidean_distance,
            "vectorRelationship": vector_relationship,
        },
    }


def align_targets(
    entry_target: str,
    moving_selector: str,
    target_selector: str,
    *,
    mode: str = "flush",
    offset: float = 0.0,
    axis: str | None = None,
    context_provider: EntryContextProvider | None = None,
) -> dict[str, object]:
    moving_selection = resolve_target_selection(
        entry_target,
        moving_selector,
        default_root_occurrence=True,
        context_provider=context_provider,
    )
    target_selection = resolve_target_selection(
        entry_target,
        target_selector,
        default_root_occurrence=True,
        context_provider=context_provider,
    )
    moving_positioning = _selection_positioning_payload(moving_selection)
    target_positioning = _selection_positioning_payload(target_selection)
    normalized_mode = str(mode or "flush").strip().lower()
    if normalized_mode not in {"flush", "center"}:
        raise CadRefError(f"Unsupported alignment mode {mode!r}; expected 'flush' or 'center'.")

    if normalized_mode == "center":
        moving_point = analysis.positioning_point(moving_positioning)
        target_point = analysis.positioning_point(target_positioning)
        if moving_point is None or target_point is None:
            raise CadRefError("Center alignment requires both targets to expose a point, center, origin, or translation.")
        translation_vector = [float(target_point[index]) - float(moving_point[index]) for index in range(3)]
        resolved_axis = None
        if axis is not None and str(axis).strip():
            resolved_axis = _axis_or_infer(axis)
            axis_index = analysis.AXIS_INDEX[resolved_axis]
            translation_vector = [
                value if index == axis_index else 0.0
                for index, value in enumerate(translation_vector)
            ]
    else:
        resolved_axis = _axis_or_infer(axis, moving_positioning, target_positioning)
        moving_coordinate = analysis.positioning_coordinate(moving_positioning, resolved_axis)
        target_coordinate = analysis.positioning_coordinate(target_positioning, resolved_axis)
        if moving_coordinate is None or target_coordinate is None:
            raise CadRefError(f"Could not compute {resolved_axis}-axis coordinates for both alignment targets.")
        offset_sign = 1
        target_alignment = target_positioning.get("axisAlignment")
        if isinstance(target_alignment, dict) and target_alignment.get("axis") == resolved_axis:
            offset_sign = int(target_alignment.get("sign") or 1)
        distance = float(target_coordinate[0] + (float(offset) * offset_sign) - moving_coordinate[0])
        translation_vector = [0.0, 0.0, 0.0]
        translation_vector[analysis.AXIS_INDEX[resolved_axis]] = distance

    vector_relationship = analysis.vector_relationship(
        _primary_vector(moving_positioning),
        _primary_vector(target_positioning),
    )
    rotation_required = None
    if vector_relationship is not None:
        rotation_required = vector_relationship.get("relation") != "opposed"

    return {
        "ok": True,
        "mode": normalized_mode,
        "axis": resolved_axis,
        "offset": float(offset),
        "moving": {
            **_selection_result_payload(moving_selection),
            "positioning": moving_positioning,
        },
        "target": {
            **_selection_result_payload(target_selection),
            "positioning": target_positioning,
        },
        "alignment": {
            "translationVector": translation_vector,
            "transformTranslationDelta": {
                "3": translation_vector[0],
                "7": translation_vector[1],
                "11": translation_vector[2],
            },
            "vectorRelationship": vector_relationship,
            "rotationRequired": rotation_required,
        },
    }


def diff_entry_targets(
    left_target: str,
    right_target: str,
    *,
    planes: bool = False,
    plane_coordinate_tolerance: float = 1e-3,
    plane_min_area_ratio: float = 0.05,
    plane_limit: int = 12,
    context_provider: EntryContextProvider | None = None,
) -> dict[str, object]:
    left_context = load_entry_context_for_target(
        left_target,
        profile=SelectorProfile.REFS,
        context_provider=context_provider,
    )
    right_context = load_entry_context_for_target(
        right_target,
        profile=SelectorProfile.REFS,
        context_provider=context_provider,
    )

    diff_payload = analysis.selector_manifest_diff(left_context.manifest, right_context.manifest)
    bbox_left = left_context.manifest.get("bbox")
    bbox_right = right_context.manifest.get("bbox")
    size_left = analysis.bbox_size(bbox_left)
    size_right = analysis.bbox_size(bbox_right)
    center_left = analysis.bbox_center(bbox_left)
    center_right = analysis.bbox_center(bbox_right)

    result: dict[str, object] = {
        "ok": True,
        "left": {
            "cadPath": left_context.cad_path,
            "kind": left_context.kind,
            "stepPath": _relative_to_repo(left_context.step_path) if left_context.step_path is not None else "",
            "summary": _entry_summary(left_context),
            "entryFacts": _entry_facts(left_context),
        },
        "right": {
            "cadPath": right_context.cad_path,
            "kind": right_context.kind,
            "stepPath": _relative_to_repo(right_context.step_path) if right_context.step_path is not None else "",
            "summary": _entry_summary(right_context),
            "entryFacts": _entry_facts(right_context),
        },
        "diff": {
            "kindChanged": left_context.kind != right_context.kind,
            **diff_payload,
            "sizeDelta": (
                [float(size_right[index] - size_left[index]) for index in range(3)]
                if size_left is not None and size_right is not None
                else None
            ),
            "centerDelta": (
                [float(center_right[index] - center_left[index]) for index in range(3)]
                if center_left is not None and center_right is not None
                else None
            ),
        },
    }

    if planes and left_context.selector_index is not None and right_context.selector_index is not None:
        report_options = EntryReportOptions(
            planes=True,
            plane_coordinate_tolerance=plane_coordinate_tolerance,
            plane_min_area_ratio=plane_min_area_ratio,
            plane_limit=plane_limit,
        )
        result["diff"]["leftMajorPlanes"] = major_planes_payload(left_context.selector_index, report_options)
        result["diff"]["rightMajorPlanes"] = major_planes_payload(right_context.selector_index, report_options)
    return result
