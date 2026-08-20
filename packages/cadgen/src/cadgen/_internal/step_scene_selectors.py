from __future__ import annotations

from array import array
from datetime import datetime
from datetime import timezone
import math
from pathlib import Path
import time
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopAbs import TopAbs_FACE
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopExp import TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS

from cadgen._internal.glb_mesh_payload import DEFAULT_MATERIAL as DEFAULT_TOPOLOGY_MATERIAL
from cadgen._internal.glb_mesh_payload import normalize_rgba as _normalize_rgba
from cadgen._internal.glb_mesh_payload import occurrence_color_for_id as _occurrence_color_for_id
from cadgen._internal.glb_mesh_payload import scene_glb_mesh_payload
from cadgen._internal.glb_topology import STEP_EDGE_VISIBILITY_CLASSES
from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadgen._internal.glb_topology import is_displayable_step_edge_surface_class_code
from cadgen._internal.glb_topology import normalize_step_edge_render_visibility_classes
from cadgen._internal.glb_topology import step_edge_surface_class_code
from cadgen._internal.glb_topology import step_topology_capabilities
from cadgen.selector_types import SelectorBundle
from cadgen.selector_types import SelectorProfile

from cadgen._internal.step_scene_geometry import _apply_transform_point, _apply_transform_vector, _bbox_from_points, _bbox_from_shape, _classify_edge, _compact_bbox, _curve_params, _distance, _edge_points_from_face_polygon, _edge_polygon_node_indices_from_face_mesh, _extract_edge_points_from_curve, _extract_face_geometry, _face_flags, _merge_bbox, _point_from_occ, _polyline_center, _polyline_length, _round_point, _round_transform, _round_value, _surface_params, _transform_bbox, _transform_param_dict, _triangle_side_key
from cadgen._internal.step_scene_loader import _relative_path_from_directory, _scene_step_hash, _selector_id, _shape_hash
from cadgen._internal.step_scene_mesh import mesh_step_scene
from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode, SelectorOptions, _enum_name


def _face_ordinals_from_shape(shape: Any, face_ord_by_hash: dict[int, int]) -> list[int]:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    ordinals: list[int] = []
    seen: set[int] = set()
    while explorer.More():
        ordinal = face_ord_by_hash.get(_shape_hash(explorer.Current()))
        if ordinal is not None and ordinal not in seen:
            ordinals.append(ordinal)
            seen.add(ordinal)
        explorer.Next()
    return ordinals


def _edge_ordinals_from_shape(shape: Any, edge_ord_by_hash: dict[int, int]) -> list[int]:
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    ordinals: list[int] = []
    seen: set[int] = set()
    while explorer.More():
        ordinal = edge_ord_by_hash.get(_shape_hash(explorer.Current()))
        if ordinal is not None and ordinal not in seen:
            ordinals.append(ordinal)
            seen.add(ordinal)
        explorer.Next()
    return ordinals


def _prototype_shape_entries(root_shape: Any) -> tuple[str, list[dict[str, Any]], dict[int, int], dict[int, int]]:
    solid_map = TopTools_IndexedMapOfShape()
    shell_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_SOLID, solid_map)
    TopExp.MapShapes_s(root_shape, TopAbs_SHELL, shell_map)

    entries: list[dict[str, Any]] = []
    face_to_shape: dict[int, int] = {}
    edge_to_shape: dict[int, int] = {}

    if solid_map.Extent() > 0:
        kind = "solid"
        map_source = solid_map
    elif shell_map.Extent() > 0:
        kind = "shell"
        map_source = shell_map
    else:
        kind = "compound"
        map_source = None

    if map_source is None:
        entries.append({"ordinal": 1, "shape": root_shape, "kind": kind})
        return kind, entries, face_to_shape, edge_to_shape

    for ordinal in range(1, map_source.Extent() + 1):
        entries.append({"ordinal": ordinal, "shape": map_source.FindKey(ordinal), "kind": kind})
    return kind, entries, face_to_shape, edge_to_shape


def _extract_summary_prototype(root_shape: Any, options: SelectorOptions) -> dict[str, Any]:
    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(root_shape, TopAbs_EDGE, edge_map)
    kind, shape_entries, _face_to_shape, _edge_to_shape = _prototype_shape_entries(root_shape)
    return {
        "kind": kind,
        "bbox": _bbox_from_shape(root_shape),
        "shapeCount": len(shape_entries) if shape_entries else 0,
        "faceCount": face_map.Extent(),
        "edgeCount": edge_map.Extent(),
    }


def _extract_refs_prototype(
    root_shape: Any,
    options: SelectorOptions,
    *,
    include_buffers: bool,
    already_meshed: bool,
) -> dict[str, Any]:
    if not already_meshed:
        BRepMesh_IncrementalMesh(
            root_shape,
            options.linear_deflection,
            options.relative,
            options.angular_deflection,
            True,
        )

    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(root_shape, TopAbs_EDGE, edge_map)
    face_ord_by_hash = {_shape_hash(face_map.FindKey(index)): index for index in range(1, face_map.Extent() + 1)}
    edge_ord_by_hash = {_shape_hash(edge_map.FindKey(index)): index for index in range(1, edge_map.Extent() + 1)}

    kind, shape_entries, _face_to_shape, _edge_to_shape = _prototype_shape_entries(root_shape)
    if not shape_entries and (face_map.Extent() > 0 or edge_map.Extent() > 0):
        shape_entries = [{"ordinal": 1, "shape": root_shape, "kind": "compound"}]

    shape_local_by_face: dict[int, int] = {}
    shape_local_by_edge: dict[int, int] = {}
    for shape_entry in shape_entries:
        face_ordinals = _face_ordinals_from_shape(shape_entry["shape"], face_ord_by_hash)
        edge_ordinals = _edge_ordinals_from_shape(shape_entry["shape"], edge_ord_by_hash)
        shape_entry["faceOrdinals"] = face_ordinals
        shape_entry["edgeOrdinals"] = edge_ordinals
        for ordinal in face_ordinals:
            shape_local_by_face.setdefault(ordinal, shape_entry["ordinal"])
        for ordinal in edge_ordinals:
            shape_local_by_edge.setdefault(ordinal, shape_entry["ordinal"])

    face_edge_ordinals: dict[int, list[int]] = {}
    edge_face_ordinals: dict[int, list[int]] = {}
    edge_face_use_counts: dict[int, dict[int, int]] = {}
    face_edge_polygon_nodes: dict[int, dict[int, list[int]]] = {}

    face_boxes: dict[int, dict[str, Any]] = {}
    face_meshes: dict[int, dict[str, Any]] = {}
    total_face_area = 0.0
    faces: list[dict[str, Any]] = []
    for face_ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face_s(face_map.FindKey(face_ordinal))
        surface = BRepAdaptor_Surface(face)
        geometry = _extract_face_geometry(face)
        raw_edge_ordinals: list[int] = []
        edge_polygons: dict[int, list[int]] = {}
        edge_side_ordinals: dict[str, int] = {}
        edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())
            edge_ordinal = edge_ord_by_hash.get(_shape_hash(edge))
            if edge_ordinal is not None:
                raw_edge_ordinals.append(edge_ordinal)
                use_counts = edge_face_use_counts.setdefault(edge_ordinal, {})
                use_counts[face_ordinal] = use_counts.get(face_ordinal, 0) + 1
                polygon_nodes = _edge_polygon_node_indices_from_face_mesh(edge, geometry)
                if polygon_nodes:
                    edge_polygons.setdefault(edge_ordinal, polygon_nodes)
                    for left, right in zip(polygon_nodes, polygon_nodes[1:]):
                        edge_side_ordinals[_triangle_side_key(left, right)] = edge_ordinal
            edge_explorer.Next()
        edge_ordinals = list(dict.fromkeys(raw_edge_ordinals))
        face_edge_ordinals[face_ordinal] = edge_ordinals
        for edge_ordinal in edge_ordinals:
            edge_face_ordinals.setdefault(edge_ordinal, []).append(face_ordinal)
        face_edge_polygon_nodes[face_ordinal] = edge_polygons
        face_boxes[face_ordinal] = geometry["bbox"]
        face_meshes[face_ordinal] = geometry
        total_face_area += geometry["area"]
        face_data = {
            "ordinal": face_ordinal,
            "shapeOrdinal": shape_local_by_face.get(face_ordinal, 1),
            "shapeHash": _shape_hash(face),
            "surfaceType": _enum_name(surface.GetType(), "GeomAbs_"),
            "area": geometry["area"],
            "center": geometry["center"],
            "normal": geometry["normal"],
            "bbox": geometry["bbox"],
            "edgeOrdinals": tuple(face_edge_ordinals.get(face_ordinal, [])),
            "edgeSideOrdinals": edge_side_ordinals,
            "triangleNodes": geometry["nodes"],
            "triangleNormals": geometry["normals"],
            "triangles": geometry["triangles"],
        }
        if not (geometry["triangleCount"] > 0 and geometry["area"] > 1e-12):
            face_data["referenceable"] = False
        params = _surface_params(surface, options.digits)
        if params:
            face_data["params"] = params
        faces.append(face_data)

    global_box = _merge_bbox(list(face_boxes.values())) if face_boxes else _bbox_from_shape(root_shape)
    diag = max(global_box["diag"], 1e-9)
    edge_deflection = options.edge_deflection if options.edge_deflection is not None else diag * options.edge_deflection_ratio
    edge_deflection = max(edge_deflection, 1e-7)

    total_edge_length = 0.0
    edge_boxes: dict[int, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for edge_ordinal in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(edge_ordinal))
        curve = BRepAdaptor_Curve(edge)
        points: list[list[float]] = []
        for face_ordinal in edge_face_ordinals.get(edge_ordinal, []):
            polygon_nodes = face_edge_polygon_nodes.get(face_ordinal, {}).get(edge_ordinal, [])
            points = _edge_points_from_face_polygon(face_meshes[face_ordinal], polygon_nodes, options.max_edge_points)
            if points:
                break
        if not points:
            points = _extract_edge_points_from_curve(edge, edge_deflection, options.max_edge_points)
        closed = bool(BRep_Tool.IsClosed_s(edge))
        length = _polyline_length(points, closed)
        total_edge_length += length
        bbox = _bbox_from_points(points)
        edge_boxes[edge_ordinal] = bbox
        seam = any(BRep_Tool.IsClosed_s(edge, TopoDS.Face_s(face_map.FindKey(face_ordinal))) for face_ordinal in edge_face_ordinals.get(edge_ordinal, []))
        degenerated = bool(BRep_Tool.Degenerated_s(edge))
        edge_data = {
            "ordinal": edge_ordinal,
            "shapeOrdinal": shape_local_by_edge.get(edge_ordinal, 1),
            "curveType": _enum_name(curve.GetType(), "GeomAbs_"),
            "length": length,
            "center": _polyline_center(points),
            "bbox": bbox,
            "faceOrdinals": tuple(edge_face_ordinals.get(edge_ordinal, [])),
            "points": points,
        }
        if closed:
            edge_data["closed"] = True
        if degenerated:
            edge_data["degenerated"] = True
        if seam:
            edge_data["seam"] = True
        if degenerated or len(points) < 2:
            edge_data["referenceable"] = False
        params = _curve_params(curve, options.digits)
        if params:
            edge_data["params"] = params
        face_shapes = [
            TopoDS.Face_s(face_map.FindKey(face_ordinal))
            for face_ordinal in edge_face_ordinals.get(edge_ordinal, [])
            if 1 <= face_ordinal <= face_map.Extent()
        ]
        face_normals = [
            face_meshes.get(face_ordinal, {}).get("normal")
            for face_ordinal in edge_face_ordinals.get(edge_ordinal, [])
        ]
        _classify_edge(
            edge_data,
            edge=edge,
            face_shapes=face_shapes,
            face_normals=face_normals,
            face_use_counts=edge_face_use_counts.get(edge_ordinal, {}),
        )
        edge_data["surfaceClassCode"] = step_edge_surface_class_code(
            edge_data,
            enabled_visibility_classes=options.edge_visibility_classes,
        )
        edges.append(edge_data)

    total_area = max(total_face_area, 1e-12)
    total_length = max(total_edge_length, 1e-12)
    size_floor = max(diag * diag * 1e-6, 1e-12)
    length_floor = max(diag * 1e-5, 1e-12)

    for face_data in faces:
        area = float(face_data["area"])
        score = 100.0 * math.sqrt(max(area, 0.0) / total_area)
        if face_data["surfaceType"] in {"plane", "cylinder", "cone", "sphere", "torus"}:
            score += 8.0
        if area < size_floor:
            score -= 45.0
        if not face_data.get("referenceable", True):
            score = 0.0
        face_data["relevance"] = max(0, min(100, int(round(score))))
        face_data["flags"] = _face_flags(face_data)

    for edge_data in edges:
        length = float(edge_data["length"])
        score = 100.0 * math.sqrt(max(length, 0.0) / total_length)
        if edge_data["curveType"] in {"line", "circle", "ellipse"}:
            score += 10.0
        if edge_data.get("seam", False):
            score -= 30.0
        if edge_data.get("degenerated", False):
            score -= 80.0
        if length < length_floor:
            score -= 35.0
        if not edge_data.get("referenceable", True):
            score = 0.0
        edge_data["relevance"] = max(0, min(100, int(round(score))))

    for shape_entry in shape_entries:
        shape = shape_entry["shape"]
        face_ordinals = shape_entry.get("faceOrdinals", [])
        boxes = [face_boxes[ordinal] for ordinal in face_ordinals if ordinal in face_boxes]
        bbox = _merge_bbox(boxes) if boxes else _bbox_from_shape(shape)
        shape_entry["bbox"] = bbox
        shape_entry["area"] = sum(faces[ordinal - 1]["area"] for ordinal in face_ordinals)
        if shape_entry["kind"] == "solid":
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props, False, False, True)
            shape_entry["volume"] = props.Mass()
            shape_entry["center"] = _point_from_occ(props.CentreOfMass())
        else:
            shape_entry["center"] = bbox["center"]

    return {
        "kind": kind,
        "bbox": global_box,
        "shapeCount": len(shape_entries),
        "faceCount": len(faces),
        "edgeCount": len(edges),
        "shapes": shape_entries,
        "faces": faces,
        "edges": edges,
        "includeBuffers": include_buffers,
    }


def _artifact_relative_manifest_path(raw_path: str, artifact_dir: Path) -> str:
    value = str(raw_path or "").strip().replace("\\", "/")
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        return _relative_path_from_directory(path, artifact_dir)
    artifact_candidate = (artifact_dir / path).resolve()
    cwd_root = Path.cwd().resolve()
    repo_candidate = (cwd_root / path).resolve()
    try:
        repo_candidate.relative_to(cwd_root)
    except ValueError:
        return value
    if repo_candidate.exists() and repo_candidate != artifact_candidate:
        return _relative_path_from_directory(repo_candidate, artifact_dir)
    return value


def _normalize_selector_options(options: SelectorOptions | None) -> SelectorOptions:
    normalized_options = options or SelectorOptions()
    if normalized_options.digits is not None and normalized_options.digits < 0:
        return SelectorOptions(
            linear_deflection=normalized_options.linear_deflection,
            angular_deflection=normalized_options.angular_deflection,
            relative=normalized_options.relative,
            edge_deflection=normalized_options.edge_deflection,
            edge_deflection_ratio=normalized_options.edge_deflection_ratio,
            max_edge_points=normalized_options.max_edge_points,
            digits=None,
            mesh_resolution=normalized_options.mesh_resolution,
            edge_visibility_classes=normalize_step_edge_render_visibility_classes(
                normalized_options.edge_visibility_classes
            ),
        )
    return SelectorOptions(
        linear_deflection=normalized_options.linear_deflection,
        angular_deflection=normalized_options.angular_deflection,
        relative=normalized_options.relative,
        edge_deflection=normalized_options.edge_deflection,
        edge_deflection_ratio=normalized_options.edge_deflection_ratio,
        max_edge_points=normalized_options.max_edge_points,
        digits=normalized_options.digits,
        mesh_resolution=normalized_options.mesh_resolution,
        edge_visibility_classes=normalize_step_edge_render_visibility_classes(
            normalized_options.edge_visibility_classes
        ),
    )


def _extract_prototype(
    shape: Any,
    profile: SelectorProfile,
    options: SelectorOptions,
    *,
    already_meshed: bool = False,
) -> dict[str, Any]:
    if profile == SelectorProfile.SUMMARY:
        return _extract_summary_prototype(shape, options)
    return _extract_refs_prototype(
        shape,
        options,
        include_buffers=(profile == SelectorProfile.ARTIFACT),
        already_meshed=already_meshed,
    )


def extract_selectors_from_scene(
    scene: LoadedStepScene,
    *,
    cad_ref: str | None = None,
    profile: SelectorProfile = SelectorProfile.ARTIFACT,
    options: SelectorOptions | None = None,
    color: ColorRGBA | tuple[float, ...] | None = None,
    occurrence_colors: dict[str, ColorRGBA] | None = None,
) -> SelectorBundle:
    started = time.perf_counter()
    resolved_step_path = scene.step_path
    # Retain the argument for existing callers, but topology artifacts are
    # identified by their colocated STEP file plus stepHash, not by a stored
    # repo-relative CAD target.
    _ = cad_ref

    normalized_options = _normalize_selector_options(options)
    if profile != SelectorProfile.SUMMARY:
        mesh_step_scene(
            scene,
            linear_deflection=normalized_options.linear_deflection,
            angular_deflection=normalized_options.angular_deflection,
            relative=normalized_options.relative,
        )

    prototype_started = time.perf_counter()
    prototypes = {
        key: _extract_prototype(
            shape,
            profile,
            normalized_options,
            already_meshed=(profile != SelectorProfile.SUMMARY),
        )
        for key, shape in scene.prototype_shapes.items()
    }
    prototype_elapsed = time.perf_counter() - prototype_started
    load_elapsed = scene.load_elapsed

    roots = scene.roots
    override_color = None if color is None else _normalize_rgba(color)
    normalized_occurrence_colors = {
        str(key): _normalize_rgba(value)
        for key, value in (occurrence_colors or {}).items()
    }

    occurrence_columns = [
        "id",
        "path",
        "name",
        "sourceName",
        "parentId",
        "transform",
        "bbox",
        "shapeStart",
        "shapeCount",
        "faceStart",
        "faceCount",
        "edgeStart",
        "edgeCount",
    ]
    shape_columns = [
        "id",
        "occurrenceId",
        "ordinal",
        "kind",
        "name",
        "sourceName",
        "bbox",
        "center",
        "area",
        "volume",
        "faceStart",
        "faceCount",
        "edgeStart",
        "edgeCount",
    ]
    shape_face_start_column = shape_columns.index("faceStart")
    shape_edge_start_column = shape_columns.index("edgeStart")
    face_columns = [
        "id",
        "occurrenceId",
        "shapeId",
        "ordinal",
        "surfaceType",
        "area",
        "center",
        "normal",
        "bbox",
        "edgeStart",
        "edgeCount",
        "relevance",
        "flags",
        "params",
        "triangleStart",
        "triangleCount",
    ]
    edge_columns = [
        "id",
        "occurrenceId",
        "shapeId",
        "ordinal",
        "curveType",
        "length",
        "center",
        "bbox",
        "faceStart",
        "faceCount",
        "relevance",
        "flags",
        "params",
        "segmentStart",
        "segmentCount",
        "adjacentFaceCount",
        "continuity",
        "dihedralDeg",
        "visibilityClass",
        "surfaceHalfEdgeStart",
        "surfaceHalfEdgeCount",
    ]

    occurrence_rows: list[list[Any]] = []
    shape_rows: list[list[Any]] = []
    face_rows: list[list[Any]] = []
    edge_rows: list[list[Any]] = []

    face_edge_rows = array("I")
    edge_face_rows = array("I")
    face_proxy_runs = array("I")
    edge_proxy_positions = array("f")
    edge_proxy_indices = array("I")
    edge_proxy_ids = array("I")
    surface_half_edges = array("I")

    entry_bbox_boxes: list[dict[str, Any]] = []
    leaf_occurrence_count = 0
    summary_shape_count = 0
    summary_face_count = 0
    summary_edge_count = 0
    unmapped_surface_edges: list[str] = []
    edge_visibility_class_counts: dict[str, int] = {}
    generated_edge_visibility_class_counts: dict[str, int] = {}

    def append_occurrence_row(node: OccurrenceNode) -> str:
        occurrence_id = _selector_id(node.path)
        parent_id = _selector_id(node.path[:-1]) if len(node.path) > 1 else None
        node.row_index = len(occurrence_rows)
        occurrence_rows.append(
            [
                occurrence_id,
                ".".join(str(segment) for segment in node.path),
                node.name,
                node.source_name,
                parent_id,
                _round_transform(node.transform, normalized_options.digits),
                None,
                0,
                0,
                0,
                0,
                0,
                0,
            ]
        )
        return occurrence_id

    def finalize_occurrence_row(node: OccurrenceNode, bbox: dict[str, Any], ranges: dict[str, int]) -> None:
        occurrence_rows[node.row_index][6] = _compact_bbox(bbox, normalized_options.digits)
        occurrence_rows[node.row_index][7] = ranges["shapeStart"]
        occurrence_rows[node.row_index][8] = ranges["shapeCount"]
        occurrence_rows[node.row_index][9] = ranges["faceStart"]
        occurrence_rows[node.row_index][10] = ranges["faceCount"]
        occurrence_rows[node.row_index][11] = ranges["edgeStart"]
        occurrence_rows[node.row_index][12] = ranges["edgeCount"]

    def glb_default_color_for_node(node: OccurrenceNode, occurrence_id: str) -> tuple[ColorRGBA, bool]:
        if override_color is not None:
            return override_color, True
        occurrence_color = _occurrence_color_for_id(occurrence_id, normalized_occurrence_colors)
        if occurrence_color is not None:
            return occurrence_color, True
        if node.color is not None:
            return _normalize_rgba(node.color), False
        if node.prototype_key is not None and node.prototype_key in scene.prototype_colors:
            return _normalize_rgba(scene.prototype_colors[node.prototype_key]), False
        return DEFAULT_TOPOLOGY_MATERIAL, False

    def glb_face_runs_for_node(
        node: OccurrenceNode,
        occurrence_id: str,
        prototype: dict[str, Any],
    ) -> tuple[dict[int, tuple[int, int, int]], Any | None]:
        if node.prototype_key is None:
            return {}, None
        default_color, suppress_face_colors = glb_default_color_for_node(node, occurrence_id)
        payload = scene_glb_mesh_payload(
            scene,
            node.prototype_key,
            default_color=default_color,
            suppress_face_colors=suppress_face_colors,
            prototype=prototype,
            include_surface_edges=(profile == SelectorProfile.ARTIFACT),
            surface_edge_class_signature=normalized_options.edge_visibility_classes,
        )
        runs: dict[int, tuple[int, int, int]] = {}
        for face_entry in prototype.get("faces", []):
            face_hash = int(face_entry.get("shapeHash") or 0)
            runs[int(face_entry["ordinal"])] = payload.face_runs_by_hash.get(face_hash, (0, 0, 0))
        return runs, payload

    def emit_leaf(node: OccurrenceNode, occurrence_id: str, prototype: dict[str, Any]) -> dict[str, Any]:
        nonlocal leaf_occurrence_count, summary_shape_count, summary_face_count, summary_edge_count
        leaf_occurrence_count += 1

        start_shape = len(shape_rows)
        start_face = len(face_rows)
        start_edge = len(edge_rows)
        shape_count = len(prototype.get("shapes", []))
        prototype_name = (
            scene.prototype_names.get(node.prototype_key)
            if node.prototype_key is not None
            else None
        )
        occurrence_shape_name = node.name or node.source_name or prototype_name

        def scoped_shape_name(base: str | None, ordinal: int) -> str | None:
            text = str(base or "").strip()
            if not text:
                return None
            if shape_count <= 1:
                return text
            return f"{text}:s{ordinal}"

        if profile == SelectorProfile.SUMMARY:
            summary_shape_count += int(prototype.get("shapeCount") or 0)
            summary_face_count += int(prototype.get("faceCount") or 0)
            summary_edge_count += int(prototype.get("edgeCount") or 0)
            bbox = _transform_bbox(prototype["bbox"], node.transform)
            entry_bbox_boxes.append(bbox)
            return {
                "bbox": bbox,
                "shapeStart": 0,
                "shapeCount": int(prototype.get("shapeCount") or 0),
                "faceStart": 0,
                "faceCount": int(prototype.get("faceCount") or 0),
                "edgeStart": 0,
                "edgeCount": int(prototype.get("edgeCount") or 0),
            }

        local_shape_index_to_global_row: dict[int, int] = {}
        for shape_entry in prototype.get("shapes", []):
            shape_ordinal = int(shape_entry["ordinal"])
            local_shape_index_to_global_row[shape_ordinal] = len(shape_rows)
            shape_rows.append(
                [
                    f"{occurrence_id}.s{shape_ordinal}",
                    occurrence_id,
                    shape_ordinal,
                    shape_entry["kind"],
                    scoped_shape_name(occurrence_shape_name, shape_ordinal),
                    scoped_shape_name(prototype_name or node.source_name, shape_ordinal),
                    _compact_bbox(_transform_bbox(shape_entry["bbox"], node.transform), normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, shape_entry["center"]), normalized_options.digits),
                    _round_value(shape_entry.get("area", 0.0), normalized_options.digits),
                    None if shape_entry.get("volume") is None else _round_value(shape_entry["volume"], normalized_options.digits),
                    0,
                    len(shape_entry.get("faceOrdinals", [])),
                    0,
                    len(shape_entry.get("edgeOrdinals", [])),
                ]
            )

        local_face_index_to_global_row: dict[int, int] = {}
        for face_entry in prototype.get("faces", []):
            local_face_index_to_global_row[int(face_entry["ordinal"])] = len(face_rows)
            edge_start = len(face_edge_rows)
            face_rows.append(
                [
                    f"{occurrence_id}.f{face_entry['ordinal']}",
                    occurrence_id,
                    f"{occurrence_id}.s{face_entry['shapeOrdinal']}",
                    int(face_entry["ordinal"]),
                    face_entry["surfaceType"],
                    _round_value(face_entry["area"], normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, face_entry["center"]), normalized_options.digits),
                    None
                    if face_entry.get("normal") is None
                    else _round_point(_apply_transform_vector(node.transform, face_entry["normal"]) or face_entry["normal"], normalized_options.digits),
                    _compact_bbox(_transform_bbox(face_entry["bbox"], node.transform), normalized_options.digits),
                    edge_start,
                    len(face_entry["edgeOrdinals"]),
                    int(face_entry.get("relevance", 0)),
                    int(face_entry.get("flags", 0)),
                    None
                    if face_entry.get("params") is None
                    else _transform_param_dict(face_entry["params"], node.transform, normalized_options.digits),
                    0,
                    0,
                ]
            )

        local_edge_index_to_global_row: dict[int, int] = {}
        for edge_entry in prototype.get("edges", []):
            local_edge_index_to_global_row[int(edge_entry["ordinal"])] = len(edge_rows)
            visibility_class = str(edge_entry.get("visibilityClass") or STEP_EDGE_VISIBILITY_CLASSES["FEATURE"])
            edge_visibility_class_counts[visibility_class] = edge_visibility_class_counts.get(visibility_class, 0) + 1
            if int(edge_entry.get("surfaceClassCode") or 0) > 0:
                generated_edge_visibility_class_counts[visibility_class] = (
                    generated_edge_visibility_class_counts.get(visibility_class, 0) + 1
                )
            face_start = len(edge_face_rows)
            edge_rows.append(
                [
                    f"{occurrence_id}.e{edge_entry['ordinal']}",
                    occurrence_id,
                    f"{occurrence_id}.s{edge_entry['shapeOrdinal']}",
                    int(edge_entry["ordinal"]),
                    edge_entry["curveType"],
                    _round_value(edge_entry["length"], normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, edge_entry["center"]), normalized_options.digits),
                    _compact_bbox(_transform_bbox(edge_entry["bbox"], node.transform), normalized_options.digits),
                    face_start,
                    len(edge_entry["faceOrdinals"]),
                    int(edge_entry.get("relevance", 0)),
                    int(edge_entry.get("flags", 0)),
                    None
                    if edge_entry.get("params") is None
                    else _transform_param_dict(edge_entry["params"], node.transform, normalized_options.digits),
                    0,
                    0,
                    int(edge_entry.get("adjacentFaceCount") or 0),
                    str(edge_entry.get("continuity") or ""),
                    edge_entry.get("dihedralDeg"),
                    visibility_class,
                    0,
                    0,
                ]
            )

        for shape_entry in prototype.get("shapes", []):
            global_shape_row = local_shape_index_to_global_row[int(shape_entry["ordinal"])]
            if shape_entry.get("faceOrdinals"):
                first_face_global = local_face_index_to_global_row[shape_entry["faceOrdinals"][0]]
            else:
                first_face_global = len(face_rows)
            if shape_entry.get("edgeOrdinals"):
                first_edge_global = local_edge_index_to_global_row[shape_entry["edgeOrdinals"][0]]
            else:
                first_edge_global = len(edge_rows)
            shape_rows[global_shape_row][shape_face_start_column] = first_face_global
            shape_rows[global_shape_row][shape_edge_start_column] = first_edge_global

        for face_entry in prototype.get("faces", []):
            global_face_row = local_face_index_to_global_row[int(face_entry["ordinal"])]
            edge_start = len(face_edge_rows)
            face_rows[global_face_row][9] = edge_start
            for edge_ordinal in face_entry["edgeOrdinals"]:
                face_edge_rows.append(local_edge_index_to_global_row[int(edge_ordinal)])

        for edge_entry in prototype.get("edges", []):
            global_edge_row = local_edge_index_to_global_row[int(edge_entry["ordinal"])]
            face_start = len(edge_face_rows)
            edge_rows[global_edge_row][8] = face_start
            for face_ordinal in edge_entry["faceOrdinals"]:
                edge_face_rows.append(local_face_index_to_global_row[int(face_ordinal)])

        if profile == SelectorProfile.ARTIFACT:
            face_runs, glb_payload = glb_face_runs_for_node(node, occurrence_id, prototype)
            for face_entry in prototype.get("faces", []):
                global_face_row = local_face_index_to_global_row[int(face_entry["ordinal"])]
                primitive_index, triangle_start, triangle_count = face_runs.get(int(face_entry["ordinal"]), (0, 0, 0))
                face_rows[global_face_row][14] = triangle_start
                face_rows[global_face_row][15] = triangle_count
                if triangle_count > 0:
                    face_proxy_runs.extend([
                        int(node.row_index),
                        int(primitive_index),
                        int(triangle_start),
                        int(triangle_count),
                        int(global_face_row),
                    ])

            for face_ordinal, half_edges in (getattr(glb_payload, "surface_half_edges_by_face_ordinal", {}) or {}).items():
                global_face_row = local_face_index_to_global_row.get(int(face_ordinal))
                if not isinstance(global_face_row, int):
                    continue
                for edge_ordinal, primitive_index, triangle_index, side, class_code in half_edges:
                    global_edge_row = local_edge_index_to_global_row.get(int(edge_ordinal))
                    if not isinstance(global_edge_row, int):
                        continue
                    current_count = int(edge_rows[global_edge_row][20] or 0)
                    if current_count == 0:
                        edge_rows[global_edge_row][19] = len(surface_half_edges) // 7
                    edge_rows[global_edge_row][20] = current_count + 1
                    surface_half_edges.extend(
                        [
                            int(global_edge_row),
                            int(global_face_row),
                            int(node.row_index),
                            int(primitive_index),
                            int(triangle_index),
                            int(side),
                            int(class_code),
                        ]
                    )

            unmapped_edges = []
            for edge_entry in prototype.get("edges", []):
                class_code = int(edge_entry.get("surfaceClassCode") or 0)
                if not is_displayable_step_edge_surface_class_code(class_code):
                    continue
                global_edge_row = local_edge_index_to_global_row.get(int(edge_entry["ordinal"]))
                if isinstance(global_edge_row, int) and int(edge_rows[global_edge_row][20] or 0) <= 0:
                    unmapped_edges.append(f"{occurrence_id}.e{edge_entry['ordinal']}")
            if unmapped_edges:
                unmapped_surface_edges.extend(unmapped_edges)

            for edge_entry in prototype.get("edges", []):
                global_edge_row = local_edge_index_to_global_row[int(edge_entry["ordinal"])]
                points = edge_entry["points"]
                if len(points) < 2:
                    continue
                vertex_offset = len(edge_proxy_positions) // 3
                segment_start = len(edge_proxy_ids)
                for point in points:
                    transformed = _apply_transform_point(node.transform, point)
                    edge_proxy_positions.extend(_round_point(transformed, normalized_options.digits))
                for local_index in range(len(points) - 1):
                    edge_proxy_indices.extend([vertex_offset + local_index, vertex_offset + local_index + 1])
                    edge_proxy_ids.append(global_edge_row)
                if edge_entry.get("closed", False) and _distance(points[0], points[-1]) > 1e-9:
                    edge_proxy_indices.extend([vertex_offset + len(points) - 1, vertex_offset])
                    edge_proxy_ids.append(global_edge_row)
                edge_rows[global_edge_row][13] = segment_start
                edge_rows[global_edge_row][14] = len(edge_proxy_ids) - segment_start

        bbox = _transform_bbox(prototype["bbox"], node.transform)
        entry_bbox_boxes.append(bbox)
        return {
            "bbox": bbox,
            "shapeStart": start_shape,
            "shapeCount": len(shape_rows) - start_shape,
            "faceStart": start_face,
            "faceCount": len(face_rows) - start_face,
            "edgeStart": start_edge,
            "edgeCount": len(edge_rows) - start_edge,
        }

    def emit_node(node: OccurrenceNode) -> dict[str, Any]:
        occurrence_id = append_occurrence_row(node)
        shape_start = len(shape_rows)
        face_start = len(face_rows)
        edge_start = len(edge_rows)
        child_boxes: list[dict[str, Any]] = []
        aggregated_shape_count = 0
        aggregated_face_count = 0
        aggregated_edge_count = 0

        if node.prototype_key is not None:
            leaf_result = emit_leaf(node, occurrence_id, prototypes[node.prototype_key])
            child_boxes.append(leaf_result["bbox"])
            aggregated_shape_count += int(leaf_result["shapeCount"])
            aggregated_face_count += int(leaf_result["faceCount"])
            aggregated_edge_count += int(leaf_result["edgeCount"])

        for child in node.children:
            child_result = emit_node(child)
            child_boxes.append(child_result["bbox"])
            aggregated_shape_count += int(child_result["shapeCount"])
            aggregated_face_count += int(child_result["faceCount"])
            aggregated_edge_count += int(child_result["edgeCount"])

        bbox = _merge_bbox(child_boxes) if child_boxes else _bbox_from_points([])
        ranges = {
            "shapeStart": shape_start if profile != SelectorProfile.SUMMARY else 0,
            "shapeCount": aggregated_shape_count if profile == SelectorProfile.SUMMARY else len(shape_rows) - shape_start,
            "faceStart": face_start if profile != SelectorProfile.SUMMARY else 0,
            "faceCount": aggregated_face_count if profile == SelectorProfile.SUMMARY else len(face_rows) - face_start,
            "edgeStart": edge_start if profile != SelectorProfile.SUMMARY else 0,
            "edgeCount": aggregated_edge_count if profile == SelectorProfile.SUMMARY else len(edge_rows) - edge_start,
        }
        finalize_occurrence_row(node, bbox, ranges)
        return {"bbox": bbox, **ranges}

    for root in roots:
        emit_node(root)

    overall_bbox = _merge_bbox(entry_bbox_boxes) if entry_bbox_boxes else _bbox_from_points([])
    elapsed = load_elapsed + (time.perf_counter() - started)

    stats = {
        "occurrenceCount": len(occurrence_rows),
        "leafOccurrenceCount": leaf_occurrence_count,
        "shapeCount": summary_shape_count if profile == SelectorProfile.SUMMARY else len(shape_rows),
        "faceCount": summary_face_count if profile == SelectorProfile.SUMMARY else len(face_rows),
        "edgeCount": summary_edge_count if profile == SelectorProfile.SUMMARY else len(edge_rows),
        "faceProxyRunCount": len(face_proxy_runs) // 5 if profile == SelectorProfile.ARTIFACT else 0,
        "edgeProxyPointCount": len(edge_proxy_positions) // 3 if profile == SelectorProfile.ARTIFACT else 0,
        "edgeProxySegmentCount": len(edge_proxy_ids) if profile == SelectorProfile.ARTIFACT else 0,
        "surfaceHalfEdgeCount": len(surface_half_edges) // 7 if profile == SelectorProfile.ARTIFACT else 0,
        "unmappedSurfaceEdgeCount": (
            len(unmapped_surface_edges) if profile == SelectorProfile.ARTIFACT else 0
        ),
        "timingMs": {
            "load": round(load_elapsed * 1000.0, 1),
            "extract": round(prototype_elapsed * 1000.0, 1),
            "total": round(elapsed * 1000.0, 1),
        },
    }
    if unmapped_surface_edges and profile == SelectorProfile.ARTIFACT:
        stats["unmappedSurfaceEdgePreview"] = unmapped_surface_edges[:20]
    edge_rendering_manifest: dict[str, Any] = {
        "visibilityClasses": list(normalized_options.edge_visibility_classes),
        "generatedVisibilityClasses": [
            class_id
            for class_id in normalized_options.edge_visibility_classes
            if generated_edge_visibility_class_counts.get(class_id, 0) > 0
        ],
        "visibilityClassCounts": dict(sorted(edge_visibility_class_counts.items())),
        "generatedVisibilityClassCounts": dict(sorted(generated_edge_visibility_class_counts.items())),
    }
    mesh_manifest: dict[str, Any] = {
        "linearDeflection": float(normalized_options.linear_deflection),
        "angularDeflection": float(normalized_options.angular_deflection),
        "relative": bool(normalized_options.relative),
    }
    if isinstance(normalized_options.mesh_resolution, dict):
        mesh_manifest["resolution"] = normalized_options.mesh_resolution

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    if source_kind not in {"step", "python"}:
        source_kind = "step"
    artifact_dir = resolved_step_path.parent
    source_path = _artifact_relative_manifest_path(str(getattr(scene, "source_path", "") or ""), artifact_dir)
    if not source_path and source_kind != "python":
        source_path = _relative_path_from_directory(resolved_step_path, artifact_dir)
    if not source_path:
        raise RuntimeError(f"STEP_topology artifact sourcePath is required for {resolved_step_path}")

    manifest: dict[str, Any] = {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": profile.value,
        "capabilities": step_topology_capabilities(normalized_options.edge_visibility_classes),
        "sourceKind": source_kind,
        "sourcePath": source_path,
        "stepPath": _relative_path_from_directory(resolved_step_path, artifact_dir),
        "bbox": _compact_bbox(overall_bbox, normalized_options.digits),
        "stats": stats,
        "edgeRendering": edge_rendering_manifest,
        "mesh": mesh_manifest,
        "tables": {
            "occurrenceColumns": occurrence_columns,
            "shapeColumns": shape_columns,
            "faceColumns": face_columns,
            "edgeColumns": edge_columns,
        },
        "occurrences": occurrence_rows,
        "shapes": shape_rows,
        "faces": face_rows,
        "edges": edge_rows,
    }
    if source_kind == "python":
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            manifest["sourceHash"] = source_hash
        source_closure_hash = str(getattr(scene, "source_closure_hash", "") or "").strip()
        source_closure_files = getattr(scene, "source_closure_files", ()) or ()
        if source_closure_hash and source_closure_files:
            manifest["sourceClosureHash"] = source_closure_hash
            manifest["sourceClosureFiles"] = list(source_closure_files)
        manifest["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    step_hash = str(getattr(scene, "step_hash", "") or "").strip()
    if not step_hash and scene.step_path.is_file():
        step_hash = _scene_step_hash(scene)
    if step_hash:
        manifest["stepHash"] = step_hash
    assembly_mates = getattr(scene, "assembly_mates", None)
    if isinstance(assembly_mates, list) and assembly_mates:
        manifest["assemblyMates"] = assembly_mates

    if profile != SelectorProfile.SUMMARY:
        if profile == SelectorProfile.ARTIFACT:
            manifest["faceProxy"] = {
                "source": f".{scene.step_path.name}.glb",
                "runsView": "faceRuns",
                "runColumns": ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"],
            }
            manifest["edgeProxy"] = {
                "positionsView": "edgePositions",
                "indicesView": "edgeIndices",
                "edgeIdsView": "edgeIds",
            }
            manifest["relations"] = {
                "faceEdgeRowsView": "faceEdgeRows",
                "edgeFaceRowsView": "edgeFaceRows",
            }
            buffers = {
                "faceRuns": face_proxy_runs,
                "edgePositions": edge_proxy_positions,
                "edgeIndices": edge_proxy_indices,
                "edgeIds": edge_proxy_ids,
                "faceEdgeRows": face_edge_rows,
                "edgeFaceRows": edge_face_rows,
                "surfaceHalfEdges": surface_half_edges,
            }
            return SelectorBundle(manifest=manifest, buffers=buffers)

        manifest["relations"] = {
            "faceEdgeRows": list(face_edge_rows),
            "edgeFaceRows": list(edge_face_rows),
        }

    return SelectorBundle(manifest=manifest)
