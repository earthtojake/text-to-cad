from __future__ import annotations

import math
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from cadgen._internal.step_scene import ColorRGBA, LoadedStepScene, OccurrenceNode, _shape_hash, occurrence_selector_id


CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MODEL_REL_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
DEFAULT_MATERIAL: ColorRGBA = (0.4677837961, 0.5520114015, 0.6172065624, 1.0)
MATERIAL_RESOURCE_ID = "1"

ET.register_namespace("", CORE_NS)


@dataclass(frozen=True)
class _FaceMesh:
    face_hash: int
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]


class _MaterialRegistry:
    def __init__(self, default_color: ColorRGBA = DEFAULT_MATERIAL) -> None:
        self._materials: list[tuple[str, ColorRGBA]] = []
        self._indices: dict[tuple[int, int, int, int], int] = {}
        self._default_color = _normalize_rgba(default_color)

    @staticmethod
    def color_key(color: ColorRGBA) -> tuple[int, int, int, int]:
        red, green, blue, alpha = _normalize_rgba(color)
        return (
            _srgb_byte_from_linear(red),
            _srgb_byte_from_linear(green),
            _srgb_byte_from_linear(blue),
            _byte_from_unit_channel(alpha),
        )

    def index(self, color: ColorRGBA, *, name: str | None = None) -> int:
        normalized = _normalize_rgba(color)
        key = self.color_key(normalized)
        existing = self._indices.get(key)
        if existing is not None:
            return existing
        index = len(self._materials)
        self._indices[key] = index
        default_key = self.color_key(self._default_color)
        material_name = name or (
            "Default" if key == default_key else f"Color {key[0]:02X}{key[1]:02X}{key[2]:02X}{key[3]:02X}"
        )
        self._materials.append((material_name, normalized))
        return index

    def append_xml(self, resources: ET.Element) -> None:
        base_materials = ET.SubElement(resources, f"{{{CORE_NS}}}basematerials", {"id": MATERIAL_RESOURCE_ID})
        for name, color in self._materials:
            ET.SubElement(
                base_materials,
                f"{{{CORE_NS}}}base",
                {
                    "name": name,
                    "displaycolor": _display_color(color),
                },
            )


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def export_part_3mf_from_scene(
    step_path: Path,
    scene: LoadedStepScene,
    *,
    target_path: Path,
    color: ColorRGBA | None = None,
    occurrence_colors: Mapping[str, ColorRGBA] | None = None,
) -> Path:
    export_scene_3mf(scene, target_path, color=color, occurrence_colors=occurrence_colors)
    return target_path


def _normalize_rgba(color: ColorRGBA | tuple[float, float, float] | None) -> ColorRGBA:
    if color is None:
        return DEFAULT_MATERIAL
    if len(color) == 3:
        red, green, blue = color
        alpha = 1.0
    else:
        red, green, blue, alpha = color
    return (
        max(0.0, min(1.0, float(red))),
        max(0.0, min(1.0, float(green))),
        max(0.0, min(1.0, float(blue))),
        max(0.0, min(1.0, float(alpha))),
    )


def _byte_from_unit_channel(channel: float) -> int:
    return max(0, min(255, int(round(channel * 255.0))))


def _srgb_byte_from_linear(channel: float) -> int:
    if channel <= 0.0031308:
        encoded = 12.92 * channel
    else:
        encoded = 1.055 * math.pow(channel, 1.0 / 2.4) - 0.055
    return _byte_from_unit_channel(encoded)


def _display_color(color: ColorRGBA) -> str:
    red, green, blue, alpha = _MaterialRegistry.color_key(color)
    return f"#{red:02X}{green:02X}{blue:02X}{alpha:02X}"


def _point_from_occ(point: object, location: TopLoc_Location) -> tuple[float, float, float]:
    transformed = point.Transformed(location.Transformation())
    return (float(transformed.X()), float(transformed.Y()), float(transformed.Z()))


def _triangle_area_twice(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> float:
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


def _format_number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"3MF mesh coordinate must be finite, got {value!r}")
    return f"{value:.9g}"


def _iter_shape_face_meshes(shape: object):
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None:
            nodes = [
                _point_from_occ(triangulation.Node(index), location)
                for index in range(1, triangulation.NbNodes() + 1)
            ]
            triangles: list[tuple[int, int, int]] = []
            for index in range(1, triangulation.NbTriangles() + 1):
                node_a, node_b, node_c = triangulation.Triangle(index).Get()
                vertex_indices = [node_a - 1, node_b - 1, node_c - 1]
                if face.Orientation() == TopAbs_REVERSED:
                    vertex_indices[1], vertex_indices[2] = vertex_indices[2], vertex_indices[1]
                vertices = [nodes[node_index] for node_index in vertex_indices]
                if _triangle_area_twice(vertices[0], vertices[1], vertices[2]) > 1e-12:
                    triangles.append(tuple(vertex_indices))
            if triangles:
                yield _FaceMesh(_shape_hash(face), nodes, triangles)
        explorer.Next()


def _object_name(name: str | None, fallback: str) -> str:
    normalized = " ".join((name or "").split())
    return normalized or fallback


def _identity_transform() -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _is_identity_transform(transform: tuple[float, ...] | None) -> bool:
    if transform is None or len(transform) != 16:
        return True
    identity = _identity_transform()
    return all(abs(float(actual) - expected) <= 1e-12 for actual, expected in zip(transform, identity))


def _format_transform(transform: tuple[float, ...] | None) -> str | None:
    if _is_identity_transform(transform):
        return None
    if transform is None or len(transform) != 16:
        raise ValueError("3MF component transform must be a 4x4 matrix")
    values = (
        transform[0],
        transform[4],
        transform[8],
        transform[1],
        transform[5],
        transform[9],
        transform[2],
        transform[6],
        transform[10],
        transform[3],
        transform[7],
        transform[11],
    )
    return " ".join(_format_number(value) for value in values)


def _append_mesh_object(
    resources: ET.Element,
    *,
    object_id: int,
    name: str,
    shape: object,
    materials: _MaterialRegistry,
    default_color: ColorRGBA,
    face_colors: dict[int, ColorRGBA],
) -> None:
    face_meshes = list(_iter_shape_face_meshes(shape))
    if not face_meshes:
        raise RuntimeError(f"Cannot write empty 3MF mesh object: {name}")

    triangle_materials: list[int] = []
    for face_mesh in face_meshes:
        triangle_materials.extend(
            [materials.index(face_colors.get(face_mesh.face_hash, default_color))] * len(face_mesh.triangles)
        )
    unique_materials = set(triangle_materials)

    object_attributes = {
        "id": str(object_id),
        "type": "model",
        "name": name,
    }
    if len(unique_materials) == 1:
        object_attributes["pid"] = MATERIAL_RESOURCE_ID
        object_attributes["pindex"] = str(next(iter(unique_materials)))
    model_object = ET.SubElement(resources, f"{{{CORE_NS}}}object", object_attributes)
    mesh = ET.SubElement(model_object, f"{{{CORE_NS}}}mesh")
    vertices_element = ET.SubElement(mesh, f"{{{CORE_NS}}}vertices")
    triangles_element = ET.SubElement(mesh, f"{{{CORE_NS}}}triangles")

    vertex_index = 0
    material_index = 0
    for face_mesh in face_meshes:
        for x, y, z in face_mesh.vertices:
            ET.SubElement(
                vertices_element,
                f"{{{CORE_NS}}}vertex",
                {
                    "x": _format_number(x),
                    "y": _format_number(y),
                    "z": _format_number(z),
                },
            )
        for a, b, c in face_mesh.triangles:
            triangle_attributes = {
                "v1": str(vertex_index + a),
                "v2": str(vertex_index + b),
                "v3": str(vertex_index + c),
            }
            if len(unique_materials) > 1:
                pindex = str(triangle_materials[material_index])
                triangle_attributes.update(
                    {
                        "pid": MATERIAL_RESOURCE_ID,
                        "p1": pindex,
                        "p2": pindex,
                        "p3": pindex,
                    }
                )
            ET.SubElement(triangles_element, f"{{{CORE_NS}}}triangle", triangle_attributes)
            material_index += 1
        vertex_index += len(face_mesh.vertices)


def _append_component_object(
    resources: ET.Element,
    *,
    object_id: int,
    name: str,
    components: list[tuple[int, tuple[float, ...] | None]],
) -> None:
    model_object = ET.SubElement(
        resources,
        f"{{{CORE_NS}}}object",
        {
            "id": str(object_id),
            "type": "model",
            "name": name,
        },
    )
    components_element = ET.SubElement(model_object, f"{{{CORE_NS}}}components")
    for component_object_id, transform in components:
        attributes = {"objectid": str(component_object_id)}
        transform_value = _format_transform(transform)
        if transform_value is not None:
            attributes["transform"] = transform_value
        ET.SubElement(components_element, f"{{{CORE_NS}}}component", attributes)


class _SceneObjectWriter:
    def __init__(
        self,
        scene: LoadedStepScene,
        resources: ET.Element,
        materials: _MaterialRegistry,
        *,
        source_color: ColorRGBA | None,
        occurrence_colors: Mapping[str, ColorRGBA] | None,
    ) -> None:
        self.scene = scene
        self.resources = resources
        self.materials = materials
        self.source_color = _normalize_rgba(source_color) if source_color is not None else None
        self.occurrence_colors = {
            str(key): _normalize_rgba(value)
            for key, value in (occurrence_colors or {}).items()
        }
        self.next_object_id = 2
        self.mesh_objects: dict[tuple[int, tuple[int, int, int, int]], int] = {}

    def _allocate_object_id(self) -> int:
        object_id = self.next_object_id
        self.next_object_id += 1
        return object_id

    def _occurrence_color_for_node(self, node: OccurrenceNode) -> ColorRGBA | None:
        occurrence_id = occurrence_selector_id(node)
        while occurrence_id:
            color = self.occurrence_colors.get(occurrence_id)
            if color is not None:
                return color
            if "." not in occurrence_id:
                return None
            occurrence_id = occurrence_id.rsplit(".", 1)[0]
        return None

    def _default_color_for_node(self, node: OccurrenceNode) -> ColorRGBA:
        occurrence_color = self._occurrence_color_for_node(node)
        if occurrence_color is not None:
            return occurrence_color
        if node.color is not None:
            return _normalize_rgba(node.color)
        if node.prototype_key is not None and node.prototype_key in self.scene.prototype_colors:
            return _normalize_rgba(self.scene.prototype_colors[node.prototype_key])
        if self.source_color is not None:
            return self.source_color
        return DEFAULT_MATERIAL

    def _mesh_object_for_node(self, node: OccurrenceNode) -> int:
        if node.prototype_key is None:
            raise RuntimeError(f"3MF leaf object has no prototype: {node.name or node.source_name or node.path}")
        shape = self.scene.prototype_shapes.get(node.prototype_key)
        if shape is None:
            raise RuntimeError(f"3MF leaf object has no prototype shape: {node.prototype_key}")
        default_color = self._default_color_for_node(node)
        object_key = (node.prototype_key, _MaterialRegistry.color_key(default_color))
        existing = self.mesh_objects.get(object_key)
        if existing is not None:
            return existing

        object_id = self._allocate_object_id()
        self.mesh_objects[object_key] = object_id
        name = _object_name(
            node.source_name or self.scene.prototype_names.get(node.prototype_key) or node.name,
            f"mesh-{object_id}",
        )
        face_colors = self.scene.prototype_face_colors.get(node.prototype_key, {})
        _append_mesh_object(
            self.resources,
            object_id=object_id,
            name=name,
            shape=shape,
            materials=self.materials,
            default_color=default_color,
            face_colors=face_colors,
        )
        return object_id

    def object_for_node(self, node: OccurrenceNode) -> int:
        if not node.children:
            return self._mesh_object_for_node(node)

        components: list[tuple[int, tuple[float, ...] | None]] = []
        for child in node.children:
            components.append((self.object_for_node(child), child.local_transform))
        object_id = self._allocate_object_id()
        _append_component_object(
            self.resources,
            object_id=object_id,
            name=_object_name(node.name or node.source_name, f"component-{object_id}"),
            components=components,
        )
        return object_id


def _build_model_root() -> tuple[ET.Element, ET.Element, ET.Element]:
    model = ET.Element(
        f"{{{CORE_NS}}}model",
        {
            "unit": "millimeter",
            "{http://www.w3.org/XML/1998/namespace}lang": "en-US",
        },
    )
    metadata = ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Application"})
    metadata.text = "tom-cad"
    resources = ET.SubElement(model, f"{{{CORE_NS}}}resources")
    build = ET.SubElement(model, f"{{{CORE_NS}}}build")
    return model, resources, build


def _build_shape_model_xml(shape: object, *, color: ColorRGBA | None = None) -> bytes:
    model, resources, build = _build_model_root()
    materials = _MaterialRegistry(_normalize_rgba(color))
    _append_mesh_object(
        resources,
        object_id=2,
        name="Model",
        shape=shape,
        materials=materials,
        default_color=_normalize_rgba(color),
        face_colors={},
    )
    objects = [child for child in list(resources) if child.tag == f"{{{CORE_NS}}}object"]
    for child in objects:
        resources.remove(child)
    materials.append_xml(resources)
    for child in objects:
        resources.append(child)
    ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": "2"})
    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def _build_scene_model_xml(
    scene: LoadedStepScene,
    *,
    color: ColorRGBA | None = None,
    occurrence_colors: Mapping[str, ColorRGBA] | None = None,
) -> bytes:
    if not scene.roots:
        raise RuntimeError(f"No CAD geometry available for 3MF export: {scene.step_path}")

    model, resources, build = _build_model_root()
    materials = _MaterialRegistry(_normalize_rgba(color))
    writer = _SceneObjectWriter(scene, resources, materials, source_color=color, occurrence_colors=occurrence_colors)

    root_components = [(writer.object_for_node(root), root.local_transform) for root in scene.roots]
    if len(root_components) == 1:
        root_object_id, root_transform = root_components[0]
        attributes = {"objectid": str(root_object_id)}
        transform = _format_transform(root_transform)
        if transform is not None:
            attributes["transform"] = transform
        ET.SubElement(build, f"{{{CORE_NS}}}item", attributes)
    else:
        root_object_id = writer._allocate_object_id()
        _append_component_object(
            resources,
            object_id=root_object_id,
            name=_object_name(scene.step_path.stem, f"component-{root_object_id}"),
            components=root_components,
        )
        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": str(root_object_id)})

    # 3MF resources can be referenced before they appear in the XML, but keeping
    # materials first makes the package easier to inspect and friendlier to parsers.
    objects = [child for child in list(resources) if child.tag == f"{{{CORE_NS}}}object"]
    for child in objects:
        resources.remove(child)
    materials.append_xml(resources)
    for child in objects:
        resources.append(child)

    return ET.tostring(model, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    types = ET.Element(f"{{{CONTENT_TYPES_NS}}}Types")
    ET.SubElement(
        types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {
            "Extension": "rels",
            "ContentType": "application/vnd.openxmlformats-package.relationships+xml",
        },
    )
    ET.SubElement(
        types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {
            "Extension": "model",
            "ContentType": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        },
    )
    return ET.tostring(types, encoding="utf-8", xml_declaration=True)


def _relationships_xml() -> bytes:
    relationships = ET.Element(f"{{{RELATIONSHIPS_NS}}}Relationships")
    ET.SubElement(
        relationships,
        f"{{{RELATIONSHIPS_NS}}}Relationship",
        {
            "Target": "/3D/3dmodel.model",
            "Id": "rel0",
            "Type": MODEL_REL_TYPE,
        },
    )
    return ET.tostring(relationships, encoding="utf-8", xml_declaration=True)


def _write_package(target_path: Path, model_xml: bytes) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _content_types_xml())
        package.writestr("_rels/.rels", _relationships_xml())
        package.writestr("3D/3dmodel.model", model_xml)
    if not target_path.exists() or target_path.stat().st_size <= 0:
        raise RuntimeError(f"Failed to write 3MF output: {_display_path(target_path)}")
    return target_path


def export_scene_3mf(
    scene: LoadedStepScene,
    target_path: Path,
    *,
    color: ColorRGBA | None = None,
    occurrence_colors: Mapping[str, ColorRGBA] | None = None,
) -> Path:
    return _write_package(target_path, _build_scene_model_xml(scene, color=color, occurrence_colors=occurrence_colors))


def export_shape_3mf(shape: object, target_path: Path) -> Path:
    return _write_package(target_path, _build_shape_model_xml(shape))
