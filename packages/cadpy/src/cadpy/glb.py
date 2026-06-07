from __future__ import annotations

import json
import os
import struct
import time
from array import array
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cadpy.glb_mesh_payload import (
    CAD_TO_GLB_SCALE,
    DEFAULT_MATERIAL,
    ShapeGlbMeshPayload,
    color_key,
    normalize_rgba,
    occurrence_color_for_id,
    scene_glb_mesh_payload,
    scene_glb_mesh_payload_key,
)
from cadpy.glb_topology import (
    STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
    STEP_EDGE_CLASS_ATTRIBUTE,
    STEP_EDGE_SURFACE_CLASS_CODES,
    STEP_SURFACE_HALF_EDGE_COLUMNS,
    STEP_TOPOLOGY_EXTENSION,
    STEP_TOPOLOGY_SCHEMA_VERSION,
    step_topology_capabilities,
)
from cadpy.render import REPO_ROOT, part_glb_path, part_native_glb_path
from cadpy.step_scene import ColorRGBA, LoadedStepScene, OccurrenceNode, SelectorBundle, occurrence_selector_id


ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
FLOAT = 5126
UNSIGNED_BYTE = 5121
UNSIGNED_INT = 5125
TRIANGLES = 4
STEP_TOPOLOGY_LEGACY_IDENTITY_KEYS = frozenset({"cadRef", "cadPath"})
GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def export_part_glb_from_scene(
    step_path: Path,
    scene: LoadedStepScene,
    *,
    linear_deflection: float,
    angular_deflection: float,
    color: tuple[float, float, float, float] | None = None,
    selector_bundle: SelectorBundle | None = None,
    include_selector_topology: bool = True,
) -> Path:
    target_path = part_glb_path(step_path)
    # The hierarchical writer handles plain part scenes too, and unlike the
    # build123d GLB exporter it preserves XCAF colors and occurrence ids.
    _ = (linear_deflection, angular_deflection)
    return _HierarchicalGlbWriter(scene, color=color).write(
        target_path,
        selector_bundle=selector_bundle,
        include_selector_topology=include_selector_topology,
        entry_kind="part",
    )


def export_assembly_glb_from_scene(
    step_path: Path,
    scene: LoadedStepScene,
    *,
    linear_deflection: float,
    angular_deflection: float,
    color: tuple[float, float, float, float] | None = None,
    occurrence_colors: Mapping[str, ColorRGBA] | None = None,
    selector_bundle: SelectorBundle | None = None,
    include_selector_topology: bool = True,
) -> Path:
    target_path = part_glb_path(step_path)
    # The caller meshes the scene before scheduling artifact jobs. Keep the
    # deflection args on this API so assembly/part exports share one contract.
    _ = (linear_deflection, angular_deflection)
    return _HierarchicalGlbWriter(scene, color=color, occurrence_colors=occurrence_colors).write(
        target_path,
        selector_bundle=selector_bundle,
        include_selector_topology=include_selector_topology,
        entry_kind="assembly",
    )


def export_native_glb_from_scene(
    step_path: Path,
    scene: LoadedStepScene,
    *,
    target_path: Path | None = None,
    linear_deflection: float,
    angular_deflection: float,
    color: tuple[float, float, float, float] | None = None,
    occurrence_colors: Mapping[str, ColorRGBA] | None = None,
) -> Path:
    target_path = target_path or part_native_glb_path(step_path)
    # The caller meshes the scene before scheduling sidecar jobs. Keep the
    # deflection args on this API so all mesh sidecars share one contract.
    _ = (linear_deflection, angular_deflection)
    return _HierarchicalGlbWriter(
        scene,
        color=color,
        occurrence_colors=occurrence_colors,
        native_y_up=True,
        include_cad_extras=False,
    ).write(target_path)


def write_empty_glb(target_path: Path) -> Path:
    json_chunk = b'{"asset":{"version":"2.0"},"scenes":[{"nodes":[]}],"scene":0,"nodes":[]}'
    json_chunk += b" " * ((4 - (len(json_chunk) % 4)) % 4)
    chunk_header = len(json_chunk).to_bytes(4, "little") + b"JSON"
    payload = b"glTF" + (2).to_bytes(4, "little") + (12 + len(chunk_header) + len(json_chunk)).to_bytes(4, "little")
    _atomic_write_bytes(target_path, payload + chunk_header + json_chunk)
    return target_path


def _atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        temp_path.write_bytes(payload)
        temp_path.replace(target_path)
    finally:
        temp_path.unlink(missing_ok=True)


def build_step_topology_index_manifest(
    manifest: Mapping[str, Any],
    *,
    entry_kind: str | None = None,
) -> dict[str, Any]:
    resolved_entry_kind = str(entry_kind or "").strip().lower()
    assembly = manifest.get("assembly")
    if not resolved_entry_kind:
        resolved_entry_kind = "assembly" if isinstance(assembly, Mapping) else "part"
    if resolved_entry_kind not in {"part", "assembly"}:
        resolved_entry_kind = "part"

    tables = manifest.get("tables") if isinstance(manifest.get("tables"), Mapping) else {}
    occurrence_columns = tables.get("occurrenceColumns") if isinstance(tables, Mapping) else None
    index: dict[str, Any] = {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "index",
        "entryKind": resolved_entry_kind,
    }
    for key in (
        "capabilities",
        "sourceKind",
        "sourcePath",
        "sourceHash",
        "generatedAt",
        "stepPath",
        "stepHash",
        "bbox",
        "stats",
        "edgeRendering",
        "mesh",
        "assemblyMates",
    ):
        value = manifest.get(key)
        if value is not None:
            index[key] = value
    if isinstance(occurrence_columns, list):
        index["tables"] = {"occurrenceColumns": occurrence_columns}
    occurrences = manifest.get("occurrences")
    if isinstance(occurrences, list):
        index["occurrences"] = occurrences
    if isinstance(assembly, Mapping):
        index["assembly"] = assembly
        index["entryKind"] = "assembly"
    return index


def _pick_buffer_views(buffer_views: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: buffer_views[name] for name in names if name in buffer_views}


def build_step_surface_edge_manifest(
    manifest: Mapping[str, Any],
    *,
    buffer_views: Mapping[str, Any],
) -> dict[str, Any]:
    stats = manifest.get("stats") if isinstance(manifest.get("stats"), Mapping) else {}
    edge_rendering = manifest.get("edgeRendering") if isinstance(manifest.get("edgeRendering"), Mapping) else {}
    generated_class_counts = (
        edge_rendering.get("generatedVisibilityClassCounts")
        if isinstance(edge_rendering.get("generatedVisibilityClassCounts"), Mapping)
        else {}
    )
    return {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "surface-edges",
        "sourceKind": manifest.get("sourceKind", "step"),
        "sourcePath": manifest.get("sourcePath"),
        "sourceHash": manifest.get("sourceHash"),
        "stepPath": manifest.get("stepPath"),
        "stepHash": manifest.get("stepHash"),
        "bbox": manifest.get("bbox"),
        "classCodes": STEP_EDGE_SURFACE_CLASS_CODES,
        "primitiveAttributes": {
            "barycentric": STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
            "class": STEP_EDGE_CLASS_ATTRIBUTE,
        },
        "halfEdgeColumns": list(STEP_SURFACE_HALF_EDGE_COLUMNS),
        "halfEdgesView": "surfaceHalfEdges",
        "edgeRendering": edge_rendering,
        "stats": {
            "edgeCount": int(stats.get("edgeCount") or 0),
            "surfaceHalfEdgeCount": int(stats.get("surfaceHalfEdgeCount") or 0),
            "generatedVisibilityClassCounts": dict(generated_class_counts),
        },
        "buffers": {
            "littleEndian": True,
            "views": _pick_buffer_views(buffer_views, ("surfaceHalfEdges",)),
        },
    }


def _gltf_matrix_from_transform(transform: tuple[float, ...]) -> list[float]:
    if len(transform) != 16:
        transform = IDENTITY_TRANSFORM
    return [
        float(transform[0]), float(transform[4]), float(transform[8]), 0.0,
        float(transform[1]), float(transform[5]), float(transform[9]), 0.0,
        float(transform[2]), float(transform[6]), float(transform[10]), 0.0,
        float(transform[3]) * CAD_TO_GLB_SCALE,
        float(transform[7]) * CAD_TO_GLB_SCALE,
        float(transform[11]) * CAD_TO_GLB_SCALE,
        1.0,
    ]


def _matmul3(a: tuple[tuple[float, float, float], ...], b: tuple[tuple[float, float, float], ...]) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        tuple(sum(a[row][inner] * b[inner][col] for inner in range(3)) for col in range(3))
        for row in range(3)
    )


def _native_y_up_vector(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (float(x), float(z), -float(y))


def _native_y_up_matrix_from_transform(transform: tuple[float, ...]) -> list[float]:
    if len(transform) != 16:
        transform = IDENTITY_TRANSFORM
    rotation = (
        (float(transform[0]), float(transform[1]), float(transform[2])),
        (float(transform[4]), float(transform[5]), float(transform[6])),
        (float(transform[8]), float(transform[9]), float(transform[10])),
    )
    cad_to_y_up = (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, -1.0, 0.0),
    )
    y_up_to_cad = (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        (0.0, 1.0, 0.0),
    )
    converted = _matmul3(_matmul3(cad_to_y_up, rotation), y_up_to_cad)
    tx, ty, tz = _native_y_up_vector(
        float(transform[3]) * CAD_TO_GLB_SCALE,
        float(transform[7]) * CAD_TO_GLB_SCALE,
        float(transform[11]) * CAD_TO_GLB_SCALE,
    )
    return [
        converted[0][0], converted[1][0], converted[2][0], 0.0,
        converted[0][1], converted[1][1], converted[2][1], 0.0,
        converted[0][2], converted[1][2], converted[2][2], 0.0,
        tx, ty, tz, 1.0,
    ]


def _native_y_up_mesh_payload(payload: ShapeGlbMeshPayload) -> ShapeGlbMeshPayload:
    if not payload.positions:
        return payload
    positions = array("f")
    min_values = [float("inf"), float("inf"), float("inf")]
    max_values = [-float("inf"), -float("inf"), -float("inf")]
    for index in range(0, len(payload.positions), 3):
        x, y, z = _native_y_up_vector(
            payload.positions[index],
            payload.positions[index + 1],
            payload.positions[index + 2],
        )
        positions.extend((x, y, z))
        min_values[0] = min(min_values[0], x)
        min_values[1] = min(min_values[1], y)
        min_values[2] = min(min_values[2], z)
        max_values[0] = max(max_values[0], x)
        max_values[1] = max(max_values[1], y)
        max_values[2] = max(max_values[2], z)

    normals = array("f")
    for index in range(0, len(payload.normals), 3):
        normals.extend(
            _native_y_up_vector(
                payload.normals[index],
                payload.normals[index + 1],
                payload.normals[index + 2],
            )
        )

    return ShapeGlbMeshPayload(
        positions=positions,
        normals=normals,
        barycentrics=array("f", payload.barycentrics),
        edge_classes=array("B", payload.edge_classes),
        primitives=list(payload.primitives),
        minimum=min_values,
        maximum=max_values,
        face_runs_by_hash=dict(payload.face_runs_by_hash),
        surface_half_edges_by_face_ordinal={
            int(face_ordinal): list(half_edges)
            for face_ordinal, half_edges in payload.surface_half_edges_by_face_ordinal.items()
        },
    )


def _selector_occurrence_ids_by_row(selector_bundle: SelectorBundle | None) -> dict[int, str]:
    if selector_bundle is None:
        return {}
    manifest = selector_bundle.manifest if isinstance(selector_bundle.manifest, Mapping) else {}
    columns = manifest.get("tables", {}).get("occurrenceColumns") if isinstance(manifest.get("tables"), Mapping) else None
    id_column = columns.index("id") if isinstance(columns, list) and "id" in columns else 0
    occurrence_ids: dict[int, str] = {}
    occurrences = manifest.get("occurrences")
    if not isinstance(occurrences, list):
        return occurrence_ids
    for row_index, row in enumerate(occurrences):
        if not isinstance(row, list) or id_column >= len(row):
            continue
        occurrence_id = str(row[id_column] or "").strip()
        if occurrence_id:
            occurrence_ids[row_index] = occurrence_id
    return occurrence_ids


def _surface_half_edges_by_occurrence_id(
    selector_bundle: SelectorBundle | None,
) -> dict[str, list[tuple[int, int, int, int]]]:
    if selector_bundle is None:
        return {}
    occurrence_ids = _selector_occurrence_ids_by_row(selector_bundle)
    surface_half_edges = selector_bundle.buffers.get("surfaceHalfEdges")
    if not surface_half_edges:
        return {}
    grouped: dict[str, list[tuple[int, int, int, int]]] = {}
    for offset in range(0, len(surface_half_edges) - 6, 7):
        occurrence_id = occurrence_ids.get(int(surface_half_edges[offset + 2]))
        if not occurrence_id:
            continue
        class_code = int(surface_half_edges[offset + 6])
        if class_code <= 0:
            continue
        grouped.setdefault(occurrence_id, []).append(
            (
                int(surface_half_edges[offset + 3]),
                int(surface_half_edges[offset + 4]),
                int(surface_half_edges[offset + 5]),
                class_code,
            )
        )
    return grouped


def _surface_edge_class_signature(selector_bundle: SelectorBundle | None) -> tuple[str, ...]:
    edge_rendering = (
        selector_bundle.manifest.get("edgeRendering")
        if selector_bundle is not None and isinstance(selector_bundle.manifest, Mapping)
        else None
    )
    visibility_classes = edge_rendering.get("visibilityClasses") if isinstance(edge_rendering, Mapping) else None
    if not isinstance(visibility_classes, list):
        return ()
    return tuple(str(item or "").strip() for item in visibility_classes if str(item or "").strip())


def _apply_surface_edge_classes_to_payload(
    payload: ShapeGlbMeshPayload,
    surface_half_edges: list[tuple[int, int, int, int]],
) -> ShapeGlbMeshPayload:
    if not surface_half_edges or not payload.edge_classes or len(payload.edge_classes) != len(payload.positions):
        return payload
    for primitive_index, triangle_index, side, class_code in surface_half_edges:
        if primitive_index < 0 or primitive_index >= len(payload.primitives):
            continue
        if side < 0 or side > 2:
            continue
        indices = payload.primitives[primitive_index][1]
        index_offset = triangle_index * 3
        if index_offset < 0 or index_offset + 2 >= len(indices):
            continue
        for local_index in range(3):
            vertex_index = int(indices[index_offset + local_index])
            component_index = (vertex_index * 3) + side
            if 0 <= component_index < len(payload.edge_classes):
                payload.edge_classes[component_index] = max(int(payload.edge_classes[component_index]), int(class_code))
    return payload


class _GlbBuilder:
    def __init__(self) -> None:
        self.json: dict[str, object] = {
            "asset": {"version": "2.0", "generator": "tom-cad"},
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [],
            "meshes": [],
            "materials": [],
            "buffers": [{"byteLength": 0}],
            "bufferViews": [],
            "accessors": [],
        }
        self.binary = bytearray()

    def add_material(self, color: ColorRGBA, *, source_color: bool | None = None) -> int:
        materials = self.json["materials"]
        assert isinstance(materials, list)
        material: dict[str, object] = {
            "pbrMetallicRoughness": {
                "baseColorFactor": [float(color[0]), float(color[1]), float(color[2]), float(color[3])],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.55,
            },
            "doubleSided": True,
        }
        if source_color is not None:
            material["extras"] = {"cadSourceColor": bool(source_color)}
        materials.append(material)
        return len(materials) - 1

    def add_buffer_view(self, payload: bytes, *, target: int | None = None) -> int:
        while len(self.binary) % 4:
            self.binary.append(0)
        offset = len(self.binary)
        self.binary.extend(payload)
        while len(self.binary) % 4:
            self.binary.append(0)
        buffer_views = self.json["bufferViews"]
        assert isinstance(buffer_views, list)
        view: dict[str, object] = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(payload),
        }
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1

    def add_accessor(
        self,
        values: array,
        *,
        component_type: int,
        accessor_type: str,
        target: int,
        count: int,
        minimum: list[float] | None = None,
        maximum: list[float] | None = None,
    ) -> int:
        buffer_view = self.add_buffer_view(values.tobytes(), target=target)
        accessor: dict[str, object] = {
            "bufferView": buffer_view,
            "byteOffset": 0,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
        if minimum is not None:
            accessor["min"] = minimum
        if maximum is not None:
            accessor["max"] = maximum
        accessors = self.json["accessors"]
        assert isinstance(accessors, list)
        accessors.append(accessor)
        return len(accessors) - 1

    def add_mesh(
        self,
        positions: array,
        normals: array,
        primitives: list[tuple[array, int]],
        *,
        minimum: list[float],
        maximum: list[float],
        name: str,
        barycentrics: array | None = None,
        edge_classes: array | None = None,
    ) -> int | None:
        vertex_count = len(positions) // 3
        if vertex_count <= 0:
            return None
        position_accessor = self.add_accessor(
            positions,
            component_type=FLOAT,
            accessor_type="VEC3",
            target=ARRAY_BUFFER,
            count=vertex_count,
            minimum=minimum,
            maximum=maximum,
        )
        normal_accessor = None
        if len(normals) == len(positions):
            normal_accessor = self.add_accessor(
                normals,
                component_type=FLOAT,
                accessor_type="VEC3",
                target=ARRAY_BUFFER,
                count=vertex_count,
            )
        barycentric_accessor = None
        if barycentrics is not None and len(barycentrics) == len(positions):
            barycentric_accessor = self.add_accessor(
                barycentrics,
                component_type=FLOAT,
                accessor_type="VEC3",
                target=ARRAY_BUFFER,
                count=vertex_count,
            )
        edge_class_accessor = None
        if edge_classes is not None and len(edge_classes) == len(positions):
            edge_class_accessor = self.add_accessor(
                edge_classes,
                component_type=UNSIGNED_BYTE,
                accessor_type="VEC3",
                target=ARRAY_BUFFER,
                count=vertex_count,
            )
        mesh_primitives = []
        for indices, material in primitives:
            if not indices:
                continue
            index_accessor = self.add_accessor(
                indices,
                component_type=UNSIGNED_INT,
                accessor_type="SCALAR",
                target=ELEMENT_ARRAY_BUFFER,
                count=len(indices),
            )
            mesh_primitives.append(
                {
                    "attributes": {
                        "POSITION": position_accessor,
                        **({"NORMAL": normal_accessor} if normal_accessor is not None else {}),
                        **(
                            {STEP_EDGE_BARYCENTRIC_ATTRIBUTE: barycentric_accessor}
                            if barycentric_accessor is not None
                            else {}
                        ),
                        **(
                            {STEP_EDGE_CLASS_ATTRIBUTE: edge_class_accessor}
                            if edge_class_accessor is not None
                            else {}
                        ),
                    },
                    "indices": index_accessor,
                    "material": material,
                    "mode": TRIANGLES,
                }
            )
        if not mesh_primitives:
            return None
        meshes = self.json["meshes"]
        assert isinstance(meshes, list)
        meshes.append(
            {
                "name": name,
                "primitives": mesh_primitives,
            }
        )
        return len(meshes) - 1

    def add_node(self, node: dict[str, object]) -> int:
        nodes = self.json["nodes"]
        assert isinstance(nodes, list)
        nodes.append(node)
        return len(nodes) - 1

    def set_scene_nodes(self, node_indices: list[int]) -> None:
        scenes = self.json["scenes"]
        assert isinstance(scenes, list)
        scene = scenes[0]
        assert isinstance(scene, dict)
        scene["nodes"] = node_indices

    def add_step_topology(
        self,
        bundle: SelectorBundle,
        *,
        include_selector_topology: bool = True,
        entry_kind: str | None = None,
    ) -> None:
        selector_manifest = dict(bundle.manifest)
        selector_manifest["schemaVersion"] = STEP_TOPOLOGY_SCHEMA_VERSION
        selector_manifest["profile"] = "selector"
        selector_manifest.pop("assembly", None)
        selector_manifest.pop("buffers", None)
        for key in STEP_TOPOLOGY_LEGACY_IDENTITY_KEYS:
            selector_manifest.pop(key, None)

        index_manifest = build_step_topology_index_manifest(bundle.manifest, entry_kind=entry_kind)
        index_payload = json.dumps(index_manifest, separators=(",", ":")).encode("utf-8")
        index_view = self.add_buffer_view(index_payload)

        buffer_views: dict[str, object] = {}
        if bundle.buffers:
            for name, values in bundle.buffers.items():
                buffer_views[name] = {
                    "dtype": "float32" if values.typecode == "f" else "uint32",
                    "bufferView": self.add_buffer_view(values.tobytes()),
                    "byteOffset": 0,
                    "byteLength": len(values) * values.itemsize,
                    "count": len(values),
                    "itemSize": values.itemsize,
                }

        edge_manifest = build_step_surface_edge_manifest(bundle.manifest, buffer_views=buffer_views)
        edge_payload = json.dumps(edge_manifest, separators=(",", ":")).encode("utf-8")
        edge_view = self.add_buffer_view(edge_payload)

        selector_view: int | None = None
        if include_selector_topology:
            if bundle.buffers:
                selector_manifest["buffers"] = {
                    "littleEndian": True,
                    "views": buffer_views,
                }
            selector_payload = json.dumps(selector_manifest, separators=(",", ":")).encode("utf-8")
            selector_view = self.add_buffer_view(selector_payload)

        extensions_used = self.json.setdefault("extensionsUsed", [])
        assert isinstance(extensions_used, list)
        if STEP_TOPOLOGY_EXTENSION not in extensions_used:
            extensions_used.append(STEP_TOPOLOGY_EXTENSION)
        extensions = self.json.setdefault("extensions", {})
        assert isinstance(extensions, dict)
        extension: dict[str, object] = {
            "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
            "entryKind": index_manifest.get("entryKind", "part"),
            "indexView": index_view,
            "edgeView": edge_view,
            "encoding": "utf-8",
        }
        if isinstance(index_manifest.get("capabilities"), Mapping):
            extension["capabilities"] = index_manifest["capabilities"]
        else:
            extension["capabilities"] = step_topology_capabilities()
        if isinstance(index_manifest.get("stats"), Mapping):
            extension["stats"] = index_manifest["stats"]
        if selector_view is not None:
            extension["selectorView"] = selector_view
        extensions[STEP_TOPOLOGY_EXTENSION] = extension
        bundle.manifest = selector_manifest if include_selector_topology else index_manifest

    def write(self, target_path: Path) -> Path:
        if not self.binary:
            return write_empty_glb(target_path)
        buffers = self.json["buffers"]
        assert isinstance(buffers, list)
        buffer = buffers[0]
        assert isinstance(buffer, dict)
        buffer["byteLength"] = len(self.binary)
        json_chunk = json.dumps(self.json, separators=(",", ":")).encode("utf-8")
        json_chunk += b" " * ((4 - (len(json_chunk) % 4)) % 4)
        binary_chunk = bytes(self.binary)
        binary_chunk += b"\0" * ((4 - (len(binary_chunk) % 4)) % 4)
        payload_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
        _atomic_write_bytes(
            target_path,
            b"glTF"
            + struct.pack("<II", 2, payload_length)
            + struct.pack("<I4s", len(json_chunk), b"JSON")
            + json_chunk
            + struct.pack("<I4s", len(binary_chunk), b"BIN\0")
            + binary_chunk,
        )
        return target_path


class _HierarchicalGlbWriter:
    def __init__(
        self,
        scene: LoadedStepScene,
        *,
        color: tuple[float, float, float, float] | None,
        occurrence_colors: Mapping[str, ColorRGBA] | None = None,
        native_y_up: bool = False,
        include_cad_extras: bool = True,
    ) -> None:
        self.scene = scene
        self.color = color
        self.occurrence_colors = dict(occurrence_colors or {})
        self.native_y_up = native_y_up
        self.include_cad_extras = include_cad_extras
        self.builder = _GlbBuilder()
        self.materials_by_color: dict[tuple[tuple[int, int, int, int], bool | None], int] = {}
        self.meshes_by_key: dict[tuple[object, ...], int | None] = {}
        self.include_surface_edges = False
        self.surface_edge_class_signature: tuple[str, ...] = ()
        self.surface_half_edges_by_occurrence_id: dict[str, list[tuple[int, int, int, int]]] = {}

    def write(
        self,
        target_path: Path,
        *,
        selector_bundle: SelectorBundle | None = None,
        include_selector_topology: bool = True,
        entry_kind: str | None = None,
    ) -> Path:
        self.include_surface_edges = selector_bundle is not None and not self.native_y_up
        self.surface_edge_class_signature = _surface_edge_class_signature(selector_bundle)
        self.surface_half_edges_by_occurrence_id = _surface_half_edges_by_occurrence_id(selector_bundle)
        root_nodes = [self._node_index(root) for root in self.scene.roots]
        self.builder.set_scene_nodes(root_nodes)
        if selector_bundle is not None:
            self.builder.add_step_topology(
                selector_bundle,
                include_selector_topology=include_selector_topology,
                entry_kind=entry_kind,
            )
        return self.builder.write(target_path)

    def _occurrence_color_for_node(self, node: OccurrenceNode) -> ColorRGBA | None:
        occurrence_id = occurrence_selector_id(node)
        return occurrence_color_for_id(occurrence_id, self.occurrence_colors)

    def _color_for_node(self, node: OccurrenceNode) -> ColorRGBA:
        if self.color is not None:
            return normalize_rgba(self.color)
        occurrence_color = self._occurrence_color_for_node(node)
        if occurrence_color is not None:
            return occurrence_color
        if node.color is not None:
            return normalize_rgba(node.color)
        if node.prototype_key is not None and node.prototype_key in self.scene.prototype_colors:
            return normalize_rgba(self.scene.prototype_colors[node.prototype_key])
        return DEFAULT_MATERIAL

    def _node_default_color_is_source(self, node: OccurrenceNode) -> bool:
        if self.color is not None:
            return True
        if self._occurrence_color_for_node(node) is not None:
            return True
        if node.color is not None:
            return True
        return node.prototype_key is not None and node.prototype_key in self.scene.prototype_colors

    def _material_index(self, color: ColorRGBA, *, source_color: bool | None = None) -> int:
        key = (color_key(color), source_color)
        material = self.materials_by_color.get(key)
        if material is None:
            material = self.builder.add_material(color, source_color=source_color)
            self.materials_by_color[key] = material
        return material

    def _mesh_index(self, node: OccurrenceNode) -> int | None:
        if node.prototype_key is None:
            return None
        color = self._color_for_node(node)
        occurrence_color = self._occurrence_color_for_node(node)
        suppress_face_colors = self.color is not None or occurrence_color is not None
        key = scene_glb_mesh_payload_key(
            self.scene,
            node.prototype_key,
            default_color=color,
            suppress_face_colors=suppress_face_colors,
            include_surface_edges=self.include_surface_edges,
            surface_edge_class_signature=self.surface_edge_class_signature,
        )
        if key in self.meshes_by_key:
            return self.meshes_by_key[key]
        payload = scene_glb_mesh_payload(
            self.scene,
            node.prototype_key,
            default_color=color,
            suppress_face_colors=suppress_face_colors,
            include_surface_edges=self.include_surface_edges,
            surface_edge_class_signature=self.surface_edge_class_signature,
        )
        if self.include_surface_edges:
            payload = _apply_surface_edge_classes_to_payload(
                payload,
                self.surface_half_edges_by_occurrence_id.get(occurrence_selector_id(node), []),
            )
        if self.native_y_up:
            payload = _native_y_up_mesh_payload(payload)
        face_colors = (
            {}
            if suppress_face_colors
            else getattr(self.scene, "prototype_face_colors", {}).get(node.prototype_key, {})
        )
        source_face_color_keys = {color_key(normalize_rgba(color)) for color in face_colors.values()}
        default_color_is_source = self._node_default_color_is_source(node)
        mesh = self.builder.add_mesh(
            payload.positions,
            payload.normals,
            [
                (
                    indices,
                    self._material_index(
                        primitive_color,
                        source_color=default_color_is_source or color_key(normalize_rgba(primitive_color)) in source_face_color_keys,
                    ),
                )
                for primitive_color, indices in payload.primitives
            ],
            minimum=payload.minimum,
            maximum=payload.maximum,
            name=self.scene.prototype_names.get(node.prototype_key) or occurrence_selector_id(node),
            barycentrics=payload.barycentrics,
            edge_classes=payload.edge_classes,
        )
        self.meshes_by_key[key] = mesh
        return mesh

    def _node_index(self, occurrence: OccurrenceNode) -> int:
        occurrence_id = occurrence_selector_id(occurrence)
        native_name = " ".join(str(occurrence.name or occurrence.source_name or occurrence_id).split()) or occurrence_id
        node: dict[str, object] = {
            "name": (
                occurrence_id
                if self.include_cad_extras
                else native_name
            ),
        }
        if self.include_cad_extras:
            node["extras"] = {
                "cadOccurrenceId": occurrence_id,
                "cadName": occurrence.name or occurrence.source_name or "",
            }
        matrix_for_transform = _native_y_up_matrix_from_transform if self.native_y_up else _gltf_matrix_from_transform
        matrix = matrix_for_transform(occurrence.local_transform)
        if matrix != matrix_for_transform(IDENTITY_TRANSFORM):
            node["matrix"] = matrix
        mesh = self._mesh_index(occurrence)
        if mesh is not None:
            node["mesh"] = mesh
        children = [self._node_index(child) for child in occurrence.children]
        if children:
            node["children"] = children
        return self.builder.add_node(node)


def _parse_glb_header(path: Path, payload: bytes) -> tuple[int, int]:
    if len(payload) < 20:
        raise ValueError(f"Not a GLB file: {_display_path(path)}")
    magic, version, length = struct.unpack_from("<III", payload, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION or length > len(payload):
        raise ValueError(f"Not a GLB v2 file: {_display_path(path)}")
    return version, length


def _read_glb_chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.expanduser().resolve().read_bytes()
    _, length = _parse_glb_header(path, payload)
    offset = 12
    json_payload: bytes | None = None
    binary_payload = b""
    while offset + 8 <= length:
        chunk_length, chunk_type = struct.unpack_from("<I4s", payload, offset)
        offset += 8
        chunk = payload[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_payload = chunk
        elif chunk_type == b"BIN\0":
            binary_payload = chunk
    if json_payload is None:
        raise ValueError(f"GLB is missing JSON chunk: {_display_path(path)}")
    gltf = json.loads(json_payload.decode("utf-8").rstrip(" \t\r\n\0"))
    if not isinstance(gltf, dict):
        raise ValueError(f"GLB JSON chunk is not an object: {_display_path(path)}")
    return gltf, binary_payload


def _read_glb_json_and_bin_location(path: Path) -> tuple[dict[str, Any], int, int]:
    resolved = path.expanduser().resolve()
    with resolved.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError(f"Not a GLB file: {_display_path(path)}")
        magic, version, length = struct.unpack("<III", header)
        if magic != GLB_MAGIC or version != GLB_VERSION:
            raise ValueError(f"Not a GLB v2 file: {_display_path(path)}")
        file_size = resolved.stat().st_size
        if length > file_size:
            raise ValueError(f"Not a GLB v2 file: {_display_path(path)}")
        offset = 12
        json_payload: bytes | None = None
        binary_offset = 0
        binary_length = 0
        while offset + 8 <= length:
            handle.seek(offset)
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                break
            chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
            offset += 8
            if offset + chunk_length > length:
                raise ValueError(f"Invalid GLB chunk length: {_display_path(path)}")
            if chunk_type == b"JSON":
                json_payload = handle.read(chunk_length)
            elif chunk_type == b"BIN\0":
                binary_offset = offset
                binary_length = chunk_length
                handle.seek(chunk_length, os.SEEK_CUR)
            else:
                handle.seek(chunk_length, os.SEEK_CUR)
            offset += chunk_length
    if json_payload is None:
        raise ValueError(f"GLB is missing JSON chunk: {_display_path(path)}")
    gltf = json.loads(json_payload.decode("utf-8").rstrip(" \t\r\n\0"))
    if not isinstance(gltf, dict):
        raise ValueError(f"GLB JSON chunk is not an object: {_display_path(path)}")
    return gltf, binary_offset, binary_length


def _buffer_view_range(gltf: Mapping[str, Any], binary_offset: int, binary_length: int, view_index: object) -> tuple[int, int]:
    if not isinstance(view_index, int):
        raise ValueError("GLB bufferView index must be an integer")
    buffer_views = gltf.get("bufferViews")
    if not isinstance(buffer_views, list) or not (0 <= view_index < len(buffer_views)):
        raise ValueError(f"GLB bufferView index is out of range: {view_index}")
    view = buffer_views[view_index]
    if not isinstance(view, Mapping):
        raise ValueError(f"GLB bufferView is not an object: {view_index}")
    if int(view.get("buffer") or 0) != 0:
        raise ValueError("STEP topology only supports GLB buffer 0")
    byte_offset = int(view.get("byteOffset") or 0)
    byte_length = int(view.get("byteLength") or 0)
    if byte_offset < 0 or byte_length < 0 or byte_offset + byte_length > binary_length:
        raise ValueError(f"GLB bufferView range is invalid: {view_index}")
    return binary_offset + byte_offset, byte_length


def _read_file_range(path: Path, byte_offset: int, byte_length: int) -> bytes:
    with path.expanduser().resolve().open("rb") as handle:
        handle.seek(byte_offset)
        payload = handle.read(byte_length)
    if len(payload) != byte_length:
        raise ValueError("GLB bufferView range is invalid")
    return payload


def _buffer_view_bytes(gltf: Mapping[str, Any], binary_payload: bytes, view_index: object) -> bytes:
    byte_offset, byte_length = _buffer_view_range(gltf, 0, len(binary_payload), view_index)
    return binary_payload[byte_offset : byte_offset + byte_length]


def _array_from_view(gltf: Mapping[str, Any], binary_payload: bytes, view: Mapping[str, Any]) -> array:
    dtype = str(view.get("dtype") or "")
    typecode = "f" if dtype == "float32" else "I" if dtype == "uint32" else ""
    if not typecode:
        raise ValueError(f"Unsupported STEP topology buffer dtype: {dtype}")
    raw = _buffer_view_bytes(gltf, binary_payload, view.get("bufferView"))
    byte_offset = int(view.get("byteOffset") or 0)
    count = int(view.get("count") or 0)
    item_size = int(view.get("itemSize") or array(typecode).itemsize)
    byte_length = int(view.get("byteLength") or (count * item_size))
    if byte_offset < 0 or byte_length < 0 or byte_offset + byte_length > len(raw):
        raise ValueError("STEP topology buffer view range is invalid")
    values = array(typecode)
    values.frombytes(raw[byte_offset : byte_offset + byte_length])
    if count >= 0 and len(values) > count:
        del values[count:]
    return values


def _array_from_legacy_binary_view(binary_payload: bytes, view: Mapping[str, Any]) -> array:
    dtype = str(view.get("dtype") or "")
    typecode = "f" if dtype == "float32" else "I" if dtype == "uint32" else ""
    if not typecode:
        raise ValueError(f"Unsupported STEP topology buffer dtype: {dtype}")
    byte_offset = int(view.get("byteOffset") or 0)
    count = int(view.get("count") or 0)
    item_size = int(view.get("itemSize") or array(typecode).itemsize)
    byte_length = int(view.get("byteLength") or (count * item_size))
    if byte_offset < 0 or byte_length < 0 or byte_offset + byte_length > len(binary_payload):
        raise ValueError("STEP topology buffer view range is invalid")
    values = array(typecode)
    values.frombytes(binary_payload[byte_offset : byte_offset + byte_length])
    if count >= 0 and len(values) > count:
        del values[count:]
    return values


def _step_topology_extension(gltf: Mapping[str, Any]) -> Mapping[str, Any] | None:
    extensions = gltf.get("extensions")
    extension = extensions.get(STEP_TOPOLOGY_EXTENSION) if isinstance(extensions, Mapping) else None
    if not isinstance(extension, Mapping):
        return None
    if str(extension.get("encoding") or "utf-8").lower() != "utf-8":
        return None
    return extension


def _legacy_topology_manifest_path_for_glb(glb_path: Path) -> Path | None:
    resolved = glb_path.expanduser().resolve()
    if resolved.name != "model.glb":
        return None
    return resolved.parent / "topology.json"


def _read_legacy_topology_manifest(glb_path: Path) -> dict[str, Any] | None:
    manifest_path = _legacy_topology_manifest_path_for_glb(glb_path)
    if manifest_path is None or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _read_legacy_topology_bundle(glb_path: Path) -> SelectorBundle | None:
    manifest = _read_legacy_topology_manifest(glb_path)
    if manifest is None:
        return None
    buffers: dict[str, array] = {}
    buffer_spec = manifest.get("buffers")
    views = buffer_spec.get("views") if isinstance(buffer_spec, Mapping) else None
    uri = str(buffer_spec.get("uri") or "") if isinstance(buffer_spec, Mapping) else ""
    if isinstance(views, Mapping) and uri:
        manifest_path = _legacy_topology_manifest_path_for_glb(glb_path)
        bin_path = manifest_path.parent / uri if manifest_path is not None else Path(uri)
        try:
            binary_payload = bin_path.read_bytes()
        except OSError:
            binary_payload = b""
        if binary_payload:
            for name, view in views.items():
                if not isinstance(view, Mapping):
                    continue
                try:
                    buffers[str(name)] = _array_from_legacy_binary_view(binary_payload, view)
                except ValueError:
                    continue
    return SelectorBundle(manifest=manifest, buffers=buffers)


def read_step_topology_bundle_from_glb(glb_path: Path) -> SelectorBundle | None:
    try:
        gltf, binary_payload = _read_glb_chunks(glb_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return _read_legacy_topology_bundle(glb_path)
    extension = _step_topology_extension(gltf)
    if extension is None:
        return _read_legacy_topology_bundle(glb_path)
    try:
        manifest_bytes = _buffer_view_bytes(gltf, binary_payload, extension.get("selectorView"))
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return _read_legacy_topology_bundle(glb_path)
    if not isinstance(manifest, dict):
        return None
    buffers: dict[str, array] = {}
    views = manifest.get("buffers", {}).get("views") if isinstance(manifest.get("buffers"), Mapping) else None
    if isinstance(views, Mapping):
        for name, view in views.items():
            if not isinstance(view, Mapping):
                continue
            try:
                buffers[str(name)] = _array_from_view(gltf, binary_payload, view)
            except ValueError:
                continue
    return SelectorBundle(manifest=manifest, buffers=buffers)


def read_step_topology_index_from_glb(glb_path: Path) -> dict[str, Any] | None:
    try:
        gltf, binary_offset, binary_length = _read_glb_json_and_bin_location(glb_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return _read_legacy_topology_manifest(glb_path)
    extension = _step_topology_extension(gltf)
    if extension is None:
        return _read_legacy_topology_manifest(glb_path)
    try:
        manifest_offset, manifest_length = _buffer_view_range(
            gltf,
            binary_offset,
            binary_length,
            extension.get("indexView"),
        )
        manifest = json.loads(_read_file_range(glb_path, manifest_offset, manifest_length).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    return manifest if isinstance(manifest, dict) else None


def read_step_display_edge_manifest_from_glb(glb_path: Path) -> dict[str, Any] | None:
    try:
        gltf, binary_offset, binary_length = _read_glb_json_and_bin_location(glb_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    extension = _step_topology_extension(gltf)
    if extension is None:
        return None
    try:
        manifest_offset, manifest_length = _buffer_view_range(
            gltf,
            binary_offset,
            binary_length,
            extension.get("edgeView", extension.get("displayEdgeView")),
        )
        manifest = json.loads(_read_file_range(glb_path, manifest_offset, manifest_length).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    return manifest if isinstance(manifest, dict) else None


def read_step_topology_manifest_from_glb(glb_path: Path) -> dict[str, Any] | None:
    return read_step_topology_index_from_glb(glb_path)
