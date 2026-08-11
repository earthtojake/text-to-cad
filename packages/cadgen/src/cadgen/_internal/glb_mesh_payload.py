from __future__ import annotations

import math
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

try:
    import numpy
except ImportError:
    # Vendored skill runtimes may not ship numpy; keep the pure-Python path.
    numpy = None


ColorRGBA = tuple[float, float, float, float]
CAD_TO_GLB_SCALE = 0.001
DEFAULT_MATERIAL: ColorRGBA = (0.72, 0.72, 0.72, 1.0)


@dataclass
class ShapeGlbMeshPayload:
    positions: array
    normals: array
    barycentrics: array
    edge_classes: array
    primitives: list[tuple[ColorRGBA, array]]
    minimum: list[float]
    maximum: list[float]
    face_runs_by_hash: dict[int, tuple[int, int, int]]
    surface_half_edges_by_face_ordinal: dict[int, list[tuple[int, int, int, int, int]]]


def normalize_rgba(color: ColorRGBA | tuple[float, ...] | None) -> ColorRGBA:
    if color is None:
        return DEFAULT_MATERIAL
    values = tuple(max(0.0, min(1.0, float(component))) for component in color)
    if len(values) == 3:
        return (values[0], values[1], values[2], 1.0)
    if len(values) >= 4:
        return (values[0], values[1], values[2], values[3])
    return DEFAULT_MATERIAL


def color_key(color: ColorRGBA) -> tuple[int, int, int, int]:
    return tuple(int(round(max(0.0, min(1.0, component)) * 255.0)) for component in color)


def occurrence_color_for_id(
    occurrence_id: str,
    occurrence_colors: Mapping[str, ColorRGBA],
) -> ColorRGBA | None:
    current = occurrence_id
    while current:
        color = occurrence_colors.get(current)
        if color is not None:
            return normalize_rgba(color)
        if "." not in current:
            break
        current = current.rsplit(".", 1)[0]
    return None


def _empty_payload() -> ShapeGlbMeshPayload:
    return ShapeGlbMeshPayload(
        positions=array("f"),
        normals=array("f"),
        barycentrics=array("f"),
        edge_classes=array("B"),
        primitives=[],
        minimum=[0.0, 0.0, 0.0],
        maximum=[0.0, 0.0, 0.0],
        face_runs_by_hash={},
        surface_half_edges_by_face_ordinal={},
    )


def _triangle_side_key(left: int, right: int) -> tuple[int, int]:
    a = max(0, int(left))
    b = max(0, int(right))
    return (a, b) if a < b else (b, a)


def _triangle_area_twice(
    a: Sequence[float],
    b: Sequence[float],
    c: Sequence[float],
) -> float:
    abx = b[0] - a[0]
    aby = b[1] - a[1]
    abz = b[2] - a[2]
    acx = c[0] - a[0]
    acy = c[1] - a[1]
    acz = c[2] - a[2]
    cross_x = aby * acz - abz * acy
    cross_y = abz * acx - abx * acz
    cross_z = abx * acy - aby * acx
    return math.sqrt(cross_x * cross_x + cross_y * cross_y + cross_z * cross_z)


def _transform_point_from_occ(point: object, location: TopLoc_Location) -> list[float]:
    transformed = point.Transformed(location.Transformation())
    return [float(transformed.X()), float(transformed.Y()), float(transformed.Z())]


def transform_normal_from_occ(
    normal: object,
    location: TopLoc_Location,
    *,
    reversed_face: bool,
) -> tuple[float, float, float]:
    transformed = normal.Transformed(location.Transformation())
    x = float(transformed.X())
    y = float(transformed.Y())
    z = float(transformed.Z())
    if reversed_face:
        x, y, z = -x, -y, -z
    length = math.sqrt((x * x) + (y * y) + (z * z))
    if length <= 1e-15 or not math.isfinite(length):
        return (0.0, 0.0, 1.0)
    return (x / length, y / length, z / length)


# Encoded side keys pack a (low, high) node-index pair into one int64 as
# low * 2**32 + high; both components must stay below this bound so the
# encoding cannot collide or overflow.
_SIDE_KEY_COMPONENT_LIMIT = 1 << 31

# Per-triangle side node pairs are ((t1, t2), (t2, t0), (t0, t1)).
_SIDE_LEFT_COLUMNS = (1, 2, 0)
_SIDE_RIGHT_COLUMNS = (2, 0, 1)


def _encoded_edge_side_table(
    edge_side_ordinals: Mapping[tuple[int, int], int],
) -> tuple[Any, Any] | None:
    keys: list[int] = []
    ordinals: list[int] = []
    for pair, ordinal in edge_side_ordinals.items():
        if not isinstance(pair, tuple) or len(pair) != 2:
            continue
        left = int(pair[0])
        right = int(pair[1])
        if not (0 <= left < _SIDE_KEY_COMPONENT_LIMIT and 0 <= right < _SIDE_KEY_COMPONENT_LIMIT):
            continue
        keys.append((left << 32) | right)
        ordinals.append(int(ordinal))
    if not keys:
        return None
    key_array = numpy.asarray(keys, dtype=numpy.int64)
    ordinal_array = numpy.asarray(ordinals, dtype=numpy.int64)
    order = numpy.argsort(key_array)
    return key_array[order], ordinal_array[order]


def _append_face_payload(
    *,
    positions: array,
    normals: array,
    barycentrics: array,
    edge_classes: array,
    primitive_indices_by_key: dict[tuple[int, int, int, int], tuple[int, ColorRGBA, array]],
    face_runs_by_hash: dict[int, tuple[int, int, int]],
    surface_half_edges_by_face_ordinal: dict[int, list[tuple[int, int, int, int, int]]],
    min_values: list[float],
    max_values: list[float],
    face_hash: int,
    face_ordinal: int,
    default_color: ColorRGBA,
    face_colors: Mapping[int, ColorRGBA],
    edge_side_ordinals: Mapping[tuple[int, int], int],
    edge_surface_class_codes: Mapping[int, int],
    include_surface_edges: bool,
    nodes: Sequence[Sequence[float]],
    node_normals: Sequence[Sequence[float]],
    triangles: Sequence[Sequence[int]],
) -> None:
    if numpy is not None and _append_face_payload_numpy(
        positions=positions,
        normals=normals,
        barycentrics=barycentrics,
        edge_classes=edge_classes,
        primitive_indices_by_key=primitive_indices_by_key,
        face_runs_by_hash=face_runs_by_hash,
        surface_half_edges_by_face_ordinal=surface_half_edges_by_face_ordinal,
        min_values=min_values,
        max_values=max_values,
        face_hash=face_hash,
        face_ordinal=face_ordinal,
        default_color=default_color,
        face_colors=face_colors,
        edge_side_ordinals=edge_side_ordinals,
        edge_surface_class_codes=edge_surface_class_codes,
        include_surface_edges=include_surface_edges,
        nodes=nodes,
        node_normals=node_normals,
        triangles=triangles,
    ):
        return
    _append_face_payload_python(
        positions=positions,
        normals=normals,
        barycentrics=barycentrics,
        edge_classes=edge_classes,
        primitive_indices_by_key=primitive_indices_by_key,
        face_runs_by_hash=face_runs_by_hash,
        surface_half_edges_by_face_ordinal=surface_half_edges_by_face_ordinal,
        min_values=min_values,
        max_values=max_values,
        face_hash=face_hash,
        face_ordinal=face_ordinal,
        default_color=default_color,
        face_colors=face_colors,
        edge_side_ordinals=edge_side_ordinals,
        edge_surface_class_codes=edge_surface_class_codes,
        include_surface_edges=include_surface_edges,
        nodes=nodes,
        node_normals=node_normals,
        triangles=triangles,
    )


def _append_face_payload_numpy(
    *,
    positions: array,
    normals: array,
    barycentrics: array,
    edge_classes: array,
    primitive_indices_by_key: dict[tuple[int, int, int, int], tuple[int, ColorRGBA, array]],
    face_runs_by_hash: dict[int, tuple[int, int, int]],
    surface_half_edges_by_face_ordinal: dict[int, list[tuple[int, int, int, int, int]]],
    min_values: list[float],
    max_values: list[float],
    face_hash: int,
    face_ordinal: int,
    default_color: ColorRGBA,
    face_colors: Mapping[int, ColorRGBA],
    edge_side_ordinals: Mapping[tuple[int, int], int],
    edge_surface_class_codes: Mapping[int, int],
    include_surface_edges: bool,
    nodes: Sequence[Sequence[float]],
    node_normals: Sequence[Sequence[float]],
    triangles: Sequence[Sequence[int]],
) -> bool:
    """Vectorized `_append_face_payload_python`; returns False to fall back.

    The output must stay byte-identical to the Python path, so any input this
    path cannot reproduce exactly is rejected before mutating the payload.
    """
    if not nodes or not triangles:
        return True
    if len(node_normals) != len(nodes):
        node_normals = [(0.0, 0.0, 1.0)] * len(nodes)
    try:
        node_array = numpy.asarray(nodes, dtype=numpy.float64)
        normal_array = numpy.asarray(node_normals, dtype=numpy.float64)
        triangle_array = numpy.asarray(triangles, dtype=numpy.int64)
        side_table = (
            _encoded_edge_side_table(edge_side_ordinals) if include_surface_edges else None
        )
    except (TypeError, ValueError, OverflowError):
        return False
    if (
        node_array.ndim != 2
        or node_array.shape[1] < 3
        or normal_array.ndim != 2
        or normal_array.shape[1] < 3
        or triangle_array.ndim != 2
        or triangle_array.shape[1] != 3
    ):
        return False
    if int(triangle_array.min()) < 0 or int(triangle_array.max()) >= min(
        len(nodes), _SIDE_KEY_COMPONENT_LIMIT
    ):
        # Out-of-range node references: let the Python path raise (or wrap
        # negative indices) exactly as before.
        return False

    normalized_color = normalize_rgba(face_colors.get(face_hash, default_color))
    key = color_key(normalized_color)
    bucket = primitive_indices_by_key.get(key)
    if bucket is None:
        bucket = (len(primitive_indices_by_key), normalized_color, array("I"))
        primitive_indices_by_key[key] = bucket
    primitive_index, _primitive_color, primitive_indices = bucket

    triangle_start = len(primitive_indices) // 3
    # Bounds must come from the float64 scaled values before the float32 cast,
    # and nanmin/nanmax mirror Python min()/max(), which never select NaN.
    scaled_nodes = node_array[:, :3] * CAD_TO_GLB_SCALE
    normal_columns = normal_array[:, :3]

    if not include_surface_edges:
        vertex_offset = len(positions) // 3
        minimum = numpy.nanmin(scaled_nodes, axis=0)
        maximum = numpy.nanmax(scaled_nodes, axis=0)
        for axis in range(3):
            min_values[axis] = min(min_values[axis], float(minimum[axis]))
            max_values[axis] = max(max_values[axis], float(maximum[axis]))
        positions.frombytes(scaled_nodes.astype(numpy.float32).tobytes())
        normals.frombytes(normal_columns.astype(numpy.float32).tobytes())
        primitive_indices.frombytes(
            (triangle_array + vertex_offset).astype(numpy.uint32).tobytes()
        )
        face_runs_by_hash[face_hash] = (primitive_index, triangle_start, len(triangles))
        return True

    triangle_count = int(triangle_array.shape[0])
    side_classes = numpy.zeros(triangle_count * 3, dtype=numpy.int64)
    matched_flat = matched_ordinals = matched_codes = None
    if side_table is not None:
        sorted_keys, sorted_ordinals = side_table
        left_nodes = triangle_array[:, _SIDE_LEFT_COLUMNS]
        right_nodes = triangle_array[:, _SIDE_RIGHT_COLUMNS]
        query_keys = (
            (numpy.minimum(left_nodes, right_nodes) << 32)
            | numpy.maximum(left_nodes, right_nodes)
        ).ravel()
        insert_at = numpy.searchsorted(sorted_keys, query_keys)
        matched = sorted_keys[numpy.minimum(insert_at, sorted_keys.size - 1)] == query_keys
        matched_flat = numpy.nonzero(matched)[0]
        if matched_flat.size:
            matched_ordinals = sorted_ordinals[insert_at[matched_flat]]
            unique_ordinals, inverse = numpy.unique(matched_ordinals, return_inverse=True)
            unique_codes = numpy.asarray(
                [
                    int(edge_surface_class_codes.get(int(ordinal), 0) or 0)
                    for ordinal in unique_ordinals.tolist()
                ],
                dtype=numpy.int64,
            )
            matched_codes = unique_codes[inverse]
            clamped_codes = numpy.maximum(matched_codes, 0)
            if int(clamped_codes.max()) > 255:
                # array('B') would raise OverflowError; let the Python path do so.
                return False
            side_classes[matched_flat] = clamped_codes
        else:
            matched_flat = None

    if matched_flat is not None:
        half_edge_mask = matched_codes != 0
        if bool(numpy.any(half_edge_mask)):
            half_edges = surface_half_edges_by_face_ordinal.setdefault(face_ordinal, [])
            for flat_side, edge_ordinal, class_code in zip(
                matched_flat[half_edge_mask].tolist(),
                matched_ordinals[half_edge_mask].tolist(),
                matched_codes[half_edge_mask].tolist(),
            ):
                half_edges.append(
                    (
                        edge_ordinal,
                        primitive_index,
                        triangle_start + flat_side // 3,
                        flat_side % 3,
                        class_code,
                    )
                )

    gathered_positions = scaled_nodes[triangle_array]
    minimum = numpy.nanmin(gathered_positions.reshape(-1, 3), axis=0)
    maximum = numpy.nanmax(gathered_positions.reshape(-1, 3), axis=0)
    for axis in range(3):
        min_values[axis] = min(min_values[axis], float(minimum[axis]))
        max_values[axis] = max(max_values[axis], float(maximum[axis]))

    vertex_base = len(positions) // 3
    positions.frombytes(gathered_positions.astype(numpy.float32).tobytes())
    normals.frombytes(normal_columns[triangle_array].astype(numpy.float32).tobytes())
    barycentrics.frombytes(
        numpy.tile(numpy.eye(3, dtype=numpy.float32), (triangle_count, 1)).tobytes()
    )
    # Every vertex of a triangle carries that triangle's full side triplet.
    edge_classes.frombytes(
        numpy.repeat(side_classes.reshape(triangle_count, 3), 3, axis=0)
        .astype(numpy.uint8)
        .tobytes()
    )
    primitive_indices.frombytes(
        numpy.arange(vertex_base, vertex_base + triangle_count * 3, dtype=numpy.uint32).tobytes()
    )
    face_runs_by_hash[face_hash] = (primitive_index, triangle_start, len(triangles))
    return True


def _append_face_payload_python(
    *,
    positions: array,
    normals: array,
    barycentrics: array,
    edge_classes: array,
    primitive_indices_by_key: dict[tuple[int, int, int, int], tuple[int, ColorRGBA, array]],
    face_runs_by_hash: dict[int, tuple[int, int, int]],
    surface_half_edges_by_face_ordinal: dict[int, list[tuple[int, int, int, int, int]]],
    min_values: list[float],
    max_values: list[float],
    face_hash: int,
    face_ordinal: int,
    default_color: ColorRGBA,
    face_colors: Mapping[int, ColorRGBA],
    edge_side_ordinals: Mapping[tuple[int, int], int],
    edge_surface_class_codes: Mapping[int, int],
    include_surface_edges: bool,
    nodes: Sequence[Sequence[float]],
    node_normals: Sequence[Sequence[float]],
    triangles: Sequence[Sequence[int]],
) -> None:
    if not nodes or not triangles:
        return

    normalized_color = normalize_rgba(face_colors.get(face_hash, default_color))
    key = color_key(normalized_color)
    bucket = primitive_indices_by_key.get(key)
    if bucket is None:
        bucket = (len(primitive_indices_by_key), normalized_color, array("I"))
        primitive_indices_by_key[key] = bucket
    primitive_index, _primitive_color, primitive_indices = bucket

    triangle_start = len(primitive_indices) // 3
    fallback_normal = (0.0, 0.0, 1.0)
    if len(node_normals) != len(nodes):
        node_normals = [fallback_normal] * len(nodes)
    if not include_surface_edges:
        vertex_offset = len(positions) // 3
        for node_index in range(len(nodes)):
            point = nodes[node_index]
            x = float(point[0]) * CAD_TO_GLB_SCALE
            y = float(point[1]) * CAD_TO_GLB_SCALE
            z = float(point[2]) * CAD_TO_GLB_SCALE
            positions.extend((x, y, z))
            min_values[0] = min(min_values[0], x)
            min_values[1] = min(min_values[1], y)
            min_values[2] = min(min_values[2], z)
            max_values[0] = max(max_values[0], x)
            max_values[1] = max(max_values[1], y)
            max_values[2] = max(max_values[2], z)
            normal = node_normals[node_index]
            normals.extend((float(normal[0]), float(normal[1]), float(normal[2])))
        for triangle in triangles:
            primitive_indices.extend(vertex_offset + int(node_index) for node_index in triangle)
        face_runs_by_hash[face_hash] = (primitive_index, triangle_start, len(triangles))
        return

    barycentric_triplet = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for triangle in triangles:
        triangle_index = len(primitive_indices) // 3
        side_pairs = (
            (int(triangle[1]), int(triangle[2])),
            (int(triangle[2]), int(triangle[0])),
            (int(triangle[0]), int(triangle[1])),
        )
        side_classes_list = [0, 0, 0]
        for side, (left, right) in enumerate(side_pairs):
            edge_ordinal = edge_side_ordinals.get((left, right) if left < right else (right, left))
            if edge_ordinal is None:
                continue
            class_code = int(edge_surface_class_codes.get(int(edge_ordinal), 0) or 0)
            side_classes_list[side] = max(0, class_code)
            if class_code:
                surface_half_edges_by_face_ordinal.setdefault(face_ordinal, []).append(
                    (
                        int(edge_ordinal),
                        int(primitive_index),
                        int(triangle_index),
                        int(side),
                        int(class_code),
                    )
                )
        side_classes = (side_classes_list[0], side_classes_list[1], side_classes_list[2])
        for local_vertex, node_index in enumerate(triangle):
            source_node_index = int(node_index)
            point = nodes[source_node_index]
            x = float(point[0]) * CAD_TO_GLB_SCALE
            y = float(point[1]) * CAD_TO_GLB_SCALE
            z = float(point[2]) * CAD_TO_GLB_SCALE
            positions.extend((x, y, z))
            min_values[0] = min(min_values[0], x)
            min_values[1] = min(min_values[1], y)
            min_values[2] = min(min_values[2], z)
            max_values[0] = max(max_values[0], x)
            max_values[1] = max(max_values[1], y)
            max_values[2] = max(max_values[2], z)
            normal = node_normals[source_node_index]
            normals.extend((float(normal[0]), float(normal[1]), float(normal[2])))
            barycentrics.extend(barycentric_triplet[local_vertex])
            edge_classes.extend(side_classes)
            primitive_indices.append((len(positions) // 3) - 1)
    face_runs_by_hash[face_hash] = (primitive_index, triangle_start, len(triangles))


def prototype_glb_mesh_payload(
    prototype: Mapping[str, Any],
    *,
    default_color: ColorRGBA,
    face_colors: Mapping[int, ColorRGBA],
    include_surface_edges: bool = False,
) -> ShapeGlbMeshPayload:
    positions = array("f")
    normals = array("f")
    barycentrics = array("f")
    edge_classes = array("B")
    primitive_indices_by_key: dict[tuple[int, int, int, int], tuple[int, ColorRGBA, array]] = {}
    face_runs_by_hash: dict[int, tuple[int, int, int]] = {}
    surface_half_edges_by_face_ordinal: dict[int, list[tuple[int, int, int, int, int]]] = {}
    min_values = [math.inf, math.inf, math.inf]
    max_values = [-math.inf, -math.inf, -math.inf]
    edge_surface_class_codes = {
        int(edge_entry.get("ordinal") or 0): int(edge_entry.get("surfaceClassCode") or 0)
        for edge_entry in prototype.get("edges", [])
        if isinstance(edge_entry, Mapping)
    }

    for face_entry in prototype.get("faces", []):
        if not isinstance(face_entry, Mapping):
            continue
        face_hash = int(face_entry.get("shapeHash") or 0)
        face_ordinal = int(face_entry.get("ordinal") or 0)
        triangles = face_entry.get("triangles", ())
        nodes = face_entry.get("triangleNodes", ())
        node_normals = face_entry.get("triangleNormals", ())
        if not node_normals:
            normal = face_entry.get("normal") or (0.0, 0.0, 1.0)
            node_normals = [normal] * len(nodes)
        _append_face_payload(
            positions=positions,
            normals=normals,
            barycentrics=barycentrics,
            edge_classes=edge_classes,
            primitive_indices_by_key=primitive_indices_by_key,
            face_runs_by_hash=face_runs_by_hash,
            surface_half_edges_by_face_ordinal=surface_half_edges_by_face_ordinal,
            min_values=min_values,
            max_values=max_values,
            face_hash=face_hash,
            face_ordinal=face_ordinal,
            default_color=default_color,
            face_colors=face_colors,
            edge_side_ordinals=face_entry.get("edgeSideOrdinals") or {},
            edge_surface_class_codes=edge_surface_class_codes,
            include_surface_edges=include_surface_edges,
            nodes=nodes,
            node_normals=node_normals,
            triangles=triangles,
        )

    if not positions or not all(math.isfinite(value) for value in min_values + max_values):
        return _empty_payload()
    primitives = [
        (primitive_color, primitive_indices)
        for _index, primitive_color, primitive_indices in sorted(
            primitive_indices_by_key.values(),
            key=lambda item: item[0],
        )
    ]
    return ShapeGlbMeshPayload(
        positions=positions,
        normals=normals,
        barycentrics=barycentrics,
        edge_classes=edge_classes,
        primitives=primitives,
        minimum=min_values,
        maximum=max_values,
        face_runs_by_hash=face_runs_by_hash,
        surface_half_edges_by_face_ordinal=surface_half_edges_by_face_ordinal,
    )


def shape_glb_mesh_payload(
    shape: object,
    *,
    default_color: ColorRGBA,
    face_colors: Mapping[int, ColorRGBA],
    include_surface_edges: bool = False,
) -> ShapeGlbMeshPayload:
    face_entries: list[dict[str, Any]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            explorer.Next()
            continue
        if not triangulation.HasNormals():
            triangulation.ComputeNormals()
        reversed_face = face.Orientation() == TopAbs_REVERSED
        nodes = [
            _transform_point_from_occ(triangulation.Node(index), location)
            for index in range(1, triangulation.NbNodes() + 1)
        ]
        node_normals = [
            transform_normal_from_occ(triangulation.Normal(index), location, reversed_face=reversed_face)
            for index in range(1, triangulation.NbNodes() + 1)
        ]
        triangles: list[tuple[int, int, int]] = []
        for index in range(1, triangulation.NbTriangles() + 1):
            node_a, node_b, node_c = triangulation.Triangle(index).Get()
            triangle = [node_a - 1, node_b - 1, node_c - 1]
            if reversed_face:
                triangle[1], triangle[2] = triangle[2], triangle[1]
            vertices = [nodes[node_index] for node_index in triangle]
            if _triangle_area_twice(vertices[0], vertices[1], vertices[2]) <= 1e-9:
                continue
            triangles.append((triangle[0], triangle[1], triangle[2]))
        if triangles:
            face_entries.append(
                {
                    "shapeHash": hash(face),
                    "triangleNodes": nodes,
                    "triangleNormals": node_normals,
                    "triangles": triangles,
                }
            )
        explorer.Next()
    return prototype_glb_mesh_payload(
        {"faces": face_entries},
        default_color=default_color,
        face_colors=face_colors,
        include_surface_edges=include_surface_edges,
    )


def scene_glb_mesh_payload_key(
    scene: object,
    prototype_key: int,
    *,
    default_color: ColorRGBA,
    suppress_face_colors: bool,
    include_surface_edges: bool = False,
    surface_edge_class_signature: Sequence[str] | tuple[str, ...] = (),
) -> tuple[object, ...]:
    return (
        int(prototype_key),
        color_key(normalize_rgba(default_color)),
        bool(suppress_face_colors),
        bool(include_surface_edges),
        tuple(str(item) for item in surface_edge_class_signature),
        getattr(scene, "mesh_signature", None),
    )


def scene_glb_mesh_payload(
    scene: object,
    prototype_key: int,
    *,
    default_color: ColorRGBA,
    suppress_face_colors: bool,
    prototype: Mapping[str, Any] | None = None,
    include_surface_edges: bool = False,
    surface_edge_class_signature: Sequence[str] | tuple[str, ...] = (),
) -> ShapeGlbMeshPayload:
    key = scene_glb_mesh_payload_key(
        scene,
        prototype_key,
        default_color=default_color,
        suppress_face_colors=suppress_face_colors,
        include_surface_edges=include_surface_edges,
        surface_edge_class_signature=surface_edge_class_signature,
    )
    cache = getattr(scene, "glb_mesh_payloads", None)
    if cache is None:
        cache = {}
        setattr(scene, "glb_mesh_payloads", cache)
    cached = cache.get(key)
    if cached is not None:
        return cached

    face_colors = (
        {}
        if suppress_face_colors
        else getattr(scene, "prototype_face_colors", {}).get(prototype_key, {})
    )
    if prototype is not None:
        payload = prototype_glb_mesh_payload(
            prototype,
            default_color=normalize_rgba(default_color),
            face_colors=face_colors,
            include_surface_edges=include_surface_edges,
        )
    else:
        shape = getattr(scene, "prototype_shapes", {}).get(prototype_key)
        payload = (
            _empty_payload()
            if shape is None
            else shape_glb_mesh_payload(
                shape,
                default_color=normalize_rgba(default_color),
                face_colors=face_colors,
                include_surface_edges=include_surface_edges,
            )
        )
    cache[key] = payload
    return payload
