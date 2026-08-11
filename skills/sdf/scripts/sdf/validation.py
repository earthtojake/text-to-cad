from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from .findings import ValidationResult, format_findings

EXTERNAL_URI_SCHEMES = {"model", "package", "http", "https", "fuel"}
COMMON_JOINT_TYPES = {
    "ball",
    "continuous",
    "fixed",
    "gearbox",
    "prismatic",
    "revolute",
    "revolute2",
    "screw",
    "universal",
}
SECOND_AXIS_JOINT_TYPES = {"revolute2", "universal"}
BOOLEAN_VALUES = {"0", "1", "true", "false", "yes", "no", "on", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}
POSE_TOLERANCE = 1e-12
UNIT_TOLERANCE = 1e-6
PSD_TOLERANCE = 1e-9
KNOWN_SDF_VERSIONS = {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12"}
LIGHT_TYPES = {"point", "directional", "spot"}
KNOWN_SENSOR_TYPES = {
    "air_pressure", "air_speed", "altimeter", "boundingbox_camera", "camera",
    "contact", "custom", "depth_camera", "force_torque", "gps", "gpu_lidar",
    "gpu_ray", "imu", "lidar", "logical_camera", "magnetometer", "multicamera",
    "navsat", "ray", "rfid", "rfidtag", "rgbd_camera", "segmentation_camera",
    "sonar", "thermal_camera", "wide_angle_camera", "wireless_receiver",
    "wireless_transmitter",
}
KNOWN_MODEL_CHILDREN = {
    "pose", "static", "self_collide", "allow_auto_disable", "enable_wind",
    "frame", "link", "joint", "plugin", "gripper", "include", "model",
}
KNOWN_LINK_CHILDREN = {
    "pose", "inertial", "visual", "collision", "sensor", "light", "projector",
    "audio_sink", "audio_source", "battery", "particle_emitter", "enable_wind",
    "kinematic", "gravity", "self_collide", "velocity_decay", "must_be_base_link",
}
KNOWN_JOINT_CHILDREN = {
    "pose", "parent", "child", "axis", "axis2", "physics", "sensor",
    "gearbox_ratio", "gearbox_reference_body", "thread_pitch", "screw_thread_pitch",
}
KNOWN_GEOMETRY_OWNER_CHILDREN = {
    "pose", "geometry", "material", "transparency", "cast_shadows", "laser_retro",
    "surface", "plugin", "meta", "visibility_flags", "max_contacts",
}
KNOWN_INERTIAL_CHILDREN = {"pose", "mass", "inertia", "density", "auto", "fluid_added_mass"}
_UNKNOWN_ELEMENT_HINT = "Unknown elements are silently ignored by consumers; check for typos."


def validate_sdf_xml(
    xml_text: str,
    *,
    source_path: Path,
    base_dir: Path | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ValidationResult:
    result = ValidationResult()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.add(
            "error",
            "invalid_xml",
            f"{_display_path(source_path)} could not be parsed as SDF XML: {exc}",
            path="/",
        )
        return result
    result.extend(validate_sdf_root(root, source_path=source_path, base_dir=base_dir, metadata=metadata))
    return result


def validate_sdf_root(
    root: ET.Element,
    *,
    source_path: Path,
    base_dir: Path | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ValidationResult:
    del metadata
    result = ValidationResult()
    resolved_path = source_path.resolve()
    resolved_base_dir = Path(base_dir).resolve() if base_dir is not None else resolved_path.parent

    if _local_name(root.tag) != "sdf":
        result.add(
            "error",
            "invalid_root",
            f"{_display_path(resolved_path)} root element must be <sdf>",
            path="/",
        )
        return result

    version = str(root.attrib.get("version") or "").strip()
    if not version:
        result.add(
            "error",
            "missing_version",
            f"{_display_path(resolved_path)} SDF version is required",
            path="/sdf",
        )
    elif not re.match(r"^\d+\.\d+(?:\.\d+)?$", version):
        result.add(
            "warning",
            "unusual_version",
            f"SDF version {version!r} does not look like major.minor",
            path="/sdf",
        )
    elif version not in KNOWN_SDF_VERSIONS:
        result.add(
            "warning",
            "unknown_sdf_version",
            f"SDF version {version!r} is not a known SDFormat release ({', '.join(sorted(KNOWN_SDF_VERSIONS))})",
            path="/sdf",
        )

    meaningful_tags = {"model", "world", "actor", "light", "include", "plugin"}
    if not any(_local_name(child.tag) in meaningful_tags for child in list(root)):
        result.add(
            "error",
            "empty_document",
            f"{_display_path(resolved_path)} must define at least one <model>, <world>, or other SDF content",
            path="/sdf",
        )

    _check_unique_named(_children(root, "world"), result, "/sdf", "world")
    _check_unique_named(_children(root, "model"), result, "/sdf", "model")

    for include_element in _children(root, "include"):
        _validate_include(include_element, result, "/sdf/include")
    for plugin_element in _children(root, "plugin"):
        _validate_plugin(plugin_element, result, "/sdf/plugin")
    for world_element in _children(root, "world"):
        _validate_world(world_element, result, resolved_base_dir)
    for model_element in _children(root, "model"):
        _validate_model(model_element, result, resolved_base_dir, parent_targets={"world"})

    return result


def raise_for_validation_errors(result: ValidationResult, *, strict: bool = False) -> None:
    findings = result.errors + (result.warnings if strict else [])
    if findings:
        from .source import SdfSourceError

        raise SdfSourceError(format_findings(findings))


def _validate_world(world_element: ET.Element, result: ValidationResult, base_dir: Path) -> None:
    world_name = _required_name(world_element, result, _path("world", world_element), "world")
    world_path = _path("world", world_element, fallback="/sdf/world")
    if not world_name:
        world_name = "world"
    targets = {"world", world_name}

    _check_unique_named(_children(world_element, "model"), result, world_path, "model")
    _check_unique_named(_children(world_element, "frame"), result, world_path, "frame")

    frames = _children(world_element, "frame")
    frame_names = _names(frames)
    targets.update(frame_names)
    for frame_element in frames:
        _validate_frame(frame_element, result, targets, world_path)
    _validate_frame_cycles(frames, result, world_path)

    for pose_element in _children(world_element, "pose"):
        _validate_pose(pose_element, result, f"{world_path}/pose", targets)
    _check_unique_named(_children(world_element, "light"), result, world_path, "light")
    for light_element in _children(world_element, "light"):
        _validate_light(light_element, result, targets, world_path)
    for include_element in _children(world_element, "include"):
        _validate_include(include_element, result, f"{world_path}/include")
    for plugin_element in _children(world_element, "plugin"):
        _validate_plugin(plugin_element, result, f"{world_path}/plugin")
    for model_element in _children(world_element, "model"):
        _validate_model(model_element, result, base_dir, parent_targets=targets)


def _validate_model(
    model_element: ET.Element,
    result: ValidationResult,
    base_dir: Path,
    *,
    parent_targets: set[str],
) -> None:
    model_name = _required_name(model_element, result, _path("model", model_element), "model")
    model_path = _path("model", model_element, fallback="/sdf/model")
    if not model_name:
        model_name = "model"

    _warn_unknown_children(model_element, KNOWN_MODEL_CHILDREN, result, model_path)

    link_elements = _children(model_element, "link")
    joint_elements = _children(model_element, "joint")
    frame_elements = _children(model_element, "frame")
    nested_model_elements = _children(model_element, "model")
    include_elements = _children(model_element, "include")
    plugin_elements = _children(model_element, "plugin")

    _check_unique_named(link_elements, result, model_path, "link")
    _check_unique_named(joint_elements, result, model_path, "joint")
    _check_unique_named(frame_elements, result, model_path, "frame")
    _check_unique_named(nested_model_elements, result, model_path, "model")
    _check_cross_type_scope_names(
        result,
        model_path,
        link=set(_names(link_elements)),
        joint=set(_names(joint_elements)),
        frame=set(_names(frame_elements)),
        model=set(_names(nested_model_elements)),
    )
    if not link_elements and not include_elements and not nested_model_elements:
        result.add(
            "error",
            "empty_model",
            f"model {model_name!r} must contain at least one link, include, or nested model",
            path=model_path,
        )

    link_names = set(_names(link_elements))
    joint_names = set(_names(joint_elements))
    frame_names = set(_names(frame_elements))
    nested_model_names = set(_names(nested_model_elements))
    # SDFormat >= 1.7 frame graph: links, joints, and explicit frames are all
    # valid relative_to / attached_to / expressed_in targets.
    local_targets = {
        "world",
        "__model__",
        model_name,
        *parent_targets,
        *link_names,
        *joint_names,
        *frame_names,
        *nested_model_names,
    }

    for pose_element in _children(model_element, "pose"):
        _validate_pose(pose_element, result, f"{model_path}/pose", local_targets)

    for static_element in _children(model_element, "static"):
        _validate_boolean_text(static_element, result, f"{model_path}/static", "static")

    for frame_element in frame_elements:
        _validate_frame(frame_element, result, local_targets, model_path)
    _validate_frame_cycles(frame_elements, result, model_path)

    child_links = _joint_child_links(joint_elements)

    for link_element in link_elements:
        _validate_link(link_element, result, base_dir, local_targets, model_path)
    for joint_element in joint_elements:
        _validate_joint(joint_element, result, link_names, local_targets, model_path)
    for include_element in _children(model_element, "include"):
        _validate_include(include_element, result, f"{model_path}/include")
    for plugin_element in plugin_elements:
        _validate_plugin(plugin_element, result, f"{model_path}/plugin")

    if not _model_is_static(model_element):
        referenced_links = set(child_links)
        referenced_links.update(_joint_parent_links(joint_elements) - {"world"})
        for link_element in link_elements:
            name = _name(link_element)
            if (
                name
                and name in referenced_links
                and _children(link_element, "collision")
                and not _children(link_element, "inertial")
            ):
                result.add(
                    "warning",
                    "missing_inertial",
                    f"dynamic link {name!r} has collision geometry but no inertial data",
                    path=f"{model_path}/link[@name='{name}']",
                )

    for nested_model in nested_model_elements:
        _validate_model(nested_model, result, base_dir, parent_targets=local_targets)


def _validate_link(
    link_element: ET.Element,
    result: ValidationResult,
    base_dir: Path,
    targets: set[str],
    model_path: str,
) -> None:
    link_name = _required_name(link_element, result, f"{model_path}/link", "link")
    link_path = f"{model_path}/link[@name='{link_name}']" if link_name else f"{model_path}/link"

    _warn_unknown_children(link_element, KNOWN_LINK_CHILDREN, result, link_path)
    for pose_element in _children(link_element, "pose"):
        _validate_pose(pose_element, result, f"{link_path}/pose", targets)

    _check_unique_named(_children(link_element, "visual"), result, link_path, "visual")
    _check_unique_named(_children(link_element, "collision"), result, link_path, "collision")
    _check_unique_named(_children(link_element, "sensor"), result, link_path, "sensor")
    _check_unique_named(_children(link_element, "light"), result, link_path, "light")
    for light_element in _children(link_element, "light"):
        _validate_light(light_element, result, targets, link_path)

    visual_meshes: set[str] = set()
    for visual_element in _children(link_element, "visual"):
        visual_meshes.update(_validate_geometry_owner(visual_element, result, base_dir, targets, f"{link_path}/visual"))
    for collision_element in _children(link_element, "collision"):
        collision_meshes = _validate_geometry_owner(
            collision_element,
            result,
            base_dir,
            targets,
            f"{link_path}/collision",
        )
        for mesh_uri in collision_meshes:
            if mesh_uri in visual_meshes:
                result.add(
                    "warning",
                    "collision_reuses_visual_mesh",
                    f"collision geometry reuses visual mesh URI {mesh_uri!r}",
                    path=f"{link_path}/collision",
                    hint="Use simplified collision geometry for physics when possible.",
                )
    for inertial_element in _children(link_element, "inertial"):
        _validate_inertial(inertial_element, result, targets, f"{link_path}/inertial")
    for sensor_element in _children(link_element, "sensor"):
        _validate_sensor(sensor_element, result, targets, f"{link_path}/sensor")


def _validate_frame(frame_element: ET.Element, result: ValidationResult, targets: set[str], owner_path: str) -> None:
    frame_name = _required_name(frame_element, result, f"{owner_path}/frame", "frame")
    frame_path = f"{owner_path}/frame[@name='{frame_name}']" if frame_name else f"{owner_path}/frame"
    attached_to = str(frame_element.attrib.get("attached_to") or "").strip()
    if attached_to:
        _check_reference(attached_to, result, frame_path, "attached_to", targets)
    for pose_element in _children(frame_element, "pose"):
        _validate_pose(pose_element, result, f"{frame_path}/pose", targets)


def _validate_joint(
    joint_element: ET.Element,
    result: ValidationResult,
    link_names: set[str],
    targets: set[str],
    model_path: str,
) -> None:
    joint_name = _required_name(joint_element, result, f"{model_path}/joint", "joint")
    joint_path = f"{model_path}/joint[@name='{joint_name}']" if joint_name else f"{model_path}/joint"
    _warn_unknown_children(joint_element, KNOWN_JOINT_CHILDREN, result, joint_path)
    joint_type = str(joint_element.attrib.get("type") or "").strip()
    if not joint_type:
        result.add("error", "missing_joint_type", f"{joint_path} type is required", path=joint_path)
    elif joint_type not in COMMON_JOINT_TYPES:
        result.add("error", "unknown_joint_type", f"unsupported SDF joint type {joint_type!r}", path=joint_path)

    parent_link = _required_child_text(joint_element, "parent", result, f"{joint_path}/parent", "joint parent")
    child_link = _required_child_text(joint_element, "child", result, f"{joint_path}/child", "joint child")
    if parent_link:
        _validate_link_reference(parent_link, result, link_names, f"{joint_path}/parent", allow_world=True)
    if child_link:
        _validate_link_reference(child_link, result, link_names, f"{joint_path}/child", allow_world=False)

    for pose_element in _children(joint_element, "pose"):
        _validate_pose(pose_element, result, f"{joint_path}/pose", targets)

    axis_elements = _children(joint_element, "axis")
    axis2_elements = _children(joint_element, "axis2")
    if joint_type in {"continuous", "revolute", "prismatic"} and not axis_elements:
        result.add(
            "warning",
            "missing_joint_axis",
            f"{joint_type} joint {joint_name!r} does not declare an explicit axis",
            path=joint_path,
        )
    for axis_element in axis_elements:
        _validate_axis(axis_element, result, targets, f"{joint_path}/axis", joint_type=joint_type, axis_name="axis")
    for axis2_element in axis2_elements:
        if joint_type not in SECOND_AXIS_JOINT_TYPES:
            result.add(
                "error",
                "unsupported_axis2",
                f"joint type {joint_type!r} does not support axis2 in the lightweight validator",
                path=f"{joint_path}/axis2",
            )
        _validate_axis(axis2_element, result, targets, f"{joint_path}/axis2", joint_type=joint_type, axis_name="axis2")


def _validate_axis(
    axis_element: ET.Element,
    result: ValidationResult,
    targets: set[str],
    axis_path: str,
    *,
    joint_type: str,
    axis_name: str,
) -> None:
    del axis_name
    xyz_element = _first_child(axis_element, "xyz")
    if xyz_element is None:
        result.add("error", "missing_axis_xyz", "joint axis must contain <xyz>", path=axis_path)
    else:
        values = _parse_number_text(str(xyz_element.text or ""), 3, result, f"{axis_path}/xyz", "axis xyz")
        if values is not None:
            norm = _norm(values)
            if norm == 0:
                result.add("error", "zero_axis", "joint axis vector must be nonzero", path=f"{axis_path}/xyz")
            elif abs(norm - 1.0) > UNIT_TOLERANCE:
                result.add(
                    "warning",
                    "non_unit_axis",
                    f"joint axis vector length is {norm:.6g}, not 1",
                    path=f"{axis_path}/xyz",
                )
        expressed_in = str(xyz_element.attrib.get("expressed_in") or axis_element.attrib.get("expressed_in") or "").strip()
        if expressed_in:
            _check_reference(expressed_in, result, f"{axis_path}/xyz", "expressed_in", targets)

    for limit_element in _children(axis_element, "limit"):
        lower = _optional_number_child(limit_element, "lower", result, f"{axis_path}/limit/lower", allow_infinite=True)
        upper = _optional_number_child(limit_element, "upper", result, f"{axis_path}/limit/upper", allow_infinite=True)
        if lower is not None and upper is not None and lower > upper:
            result.add("error", "invalid_joint_limit", "joint lower limit exceeds upper limit", path=f"{axis_path}/limit")
        for tag in ("effort", "velocity", "stiffness", "dissipation"):
            value = _optional_number_child(limit_element, tag, result, f"{axis_path}/limit/{tag}", allow_infinite=True)
            # -1 is the SDFormat sentinel for "unlimited" effort/velocity.
            if value is not None and math.isfinite(value) and value < 0 and not (tag in {"effort", "velocity"} and value == -1):
                result.add(
                    "error",
                    f"negative_{tag}",
                    f"joint limit {tag} must be non-negative (or -1 for unlimited effort/velocity)",
                    path=f"{axis_path}/limit/{tag}",
                )
        if joint_type == "continuous" and (lower is not None or upper is not None):
            result.add(
                "warning",
                "continuous_joint_limits",
                "continuous joints usually should not use finite position limits",
                path=f"{axis_path}/limit",
            )
    for dynamics_element in _children(axis_element, "dynamics"):
        for tag in ("damping", "friction", "spring_stiffness"):
            value = _optional_number_child(dynamics_element, tag, result, f"{axis_path}/dynamics/{tag}")
            if value is not None and value < 0 and tag != "spring_stiffness":
                result.add(
                    "error",
                    f"negative_{tag}",
                    f"joint dynamics {tag} must be non-negative",
                    path=f"{axis_path}/dynamics/{tag}",
                )
        _optional_number_child(dynamics_element, "spring_reference", result, f"{axis_path}/dynamics/spring_reference")


def _validate_geometry_owner(
    owner: ET.Element,
    result: ValidationResult,
    base_dir: Path,
    targets: set[str],
    owner_path: str,
) -> set[str]:
    owner_name = _required_name(owner, result, owner_path, _local_name(owner.tag))
    path = f"{owner_path}[@name='{owner_name}']" if owner_name else owner_path
    _warn_unknown_children(owner, KNOWN_GEOMETRY_OWNER_CHILDREN, result, path)
    for pose_element in _children(owner, "pose"):
        # Visual/collision pose defaults to the owning link frame, which is
        # unambiguous; only flag explicit-but-unresolvable relative_to.
        _validate_pose(pose_element, result, f"{path}/pose", targets, warn_missing_relative_to=False)

    geometry_elements = _children(owner, "geometry")
    if len(geometry_elements) != 1:
        result.add(
            "error",
            "invalid_geometry_count",
            f"{_local_name(owner.tag)} must contain exactly one <geometry>",
            path=path,
        )
        return set()

    geometry = geometry_elements[0]
    known_children = [
        child for child in list(geometry) if _local_name(child.tag) in {"box", "sphere", "cylinder", "capsule", "plane", "mesh"}
    ]
    if len(known_children) != 1:
        result.add(
            "error",
            "invalid_geometry_shape",
            "geometry must contain exactly one recognized primitive or mesh child",
            path=f"{path}/geometry",
        )
        return set()

    shape = known_children[0]
    shape_name = _local_name(shape.tag)
    if shape_name == "box":
        _validate_positive_vector_child(shape, "size", 3, result, f"{path}/geometry/box/size")
    elif shape_name == "sphere":
        _validate_positive_number_child(shape, "radius", result, f"{path}/geometry/sphere/radius")
    elif shape_name == "cylinder":
        _validate_positive_number_child(shape, "radius", result, f"{path}/geometry/cylinder/radius")
        _validate_positive_number_child(shape, "length", result, f"{path}/geometry/cylinder/length")
    elif shape_name == "capsule":
        _validate_positive_number_child(shape, "radius", result, f"{path}/geometry/capsule/radius")
        _validate_positive_number_child(shape, "length", result, f"{path}/geometry/capsule/length")
    elif shape_name == "plane":
        _validate_positive_vector_child(shape, "size", 2, result, f"{path}/geometry/plane/size")
    elif shape_name == "mesh":
        uri = _required_child_text(shape, "uri", result, f"{path}/geometry/mesh/uri", "mesh uri")
        _validate_mesh_scale_child(shape, result, f"{path}/geometry/mesh/scale")
        if uri:
            _validate_mesh_uri(uri, result, base_dir, f"{path}/geometry/mesh/uri")
            return {uri}
    return set()


def _validate_inertial(inertial_element: ET.Element, result: ValidationResult, targets: set[str], inertial_path: str) -> None:
    _warn_unknown_children(inertial_element, KNOWN_INERTIAL_CHILDREN, result, inertial_path)
    for pose_element in _children(inertial_element, "pose"):
        # Inertial pose defaults to the owning link frame (unambiguous).
        _validate_pose(pose_element, result, f"{inertial_path}/pose", targets, warn_missing_relative_to=False)
    mass = _optional_number_child(inertial_element, "mass", result, f"{inertial_path}/mass", required=True)
    if mass is not None and mass <= 0:
        result.add("error", "invalid_mass", "inertial mass must be positive", path=f"{inertial_path}/mass")

    inertia_element = _first_child(inertial_element, "inertia")
    if inertia_element is None:
        result.add("warning", "missing_inertia_matrix", "inertial element has mass but no inertia matrix", path=inertial_path)
        return
    components: dict[str, float] = {}
    for tag in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz"):
        value = _optional_number_child(inertia_element, tag, result, f"{inertial_path}/inertia/{tag}", required=True)
        if value is not None:
            components[tag] = value
    if len(components) != 6:
        return
    if not _inertia_is_psd(components):
        result.add(
            "error",
            "invalid_inertia_matrix",
            "inertia matrix must be positive semidefinite within tolerance",
            path=f"{inertial_path}/inertia",
        )
        return
    low, mid, high = sorted(_symmetric_inertia_eigenvalues(components))
    scale = max(abs(value) for value in components.values())
    if low + mid + (scale * 1e-6 + 1e-12) < high:
        result.add(
            "warning",
            "inertia_triangle_inequality",
            "inertia principal moments violate the triangle inequality (l1 + l2 >= l3)",
            path=f"{inertial_path}/inertia",
            hint="Physical rigid bodies require it; recompute the tensor from the geometry.",
        )


def _validate_sensor(sensor_element: ET.Element, result: ValidationResult, targets: set[str], sensor_path: str) -> None:
    sensor_name = _required_name(sensor_element, result, sensor_path, "sensor")
    path = f"{sensor_path}[@name='{sensor_name}']" if sensor_name else sensor_path
    sensor_type = str(sensor_element.attrib.get("type") or "").strip()
    if not sensor_type:
        result.add("error", "missing_sensor_type", "sensor type is required", path=path)
    elif sensor_type not in KNOWN_SENSOR_TYPES:
        result.add(
            "warning",
            "unknown_sensor_type",
            f"sensor type {sensor_type!r} is not a known SDFormat sensor type",
            path=path,
            hint="Check for typos (e.g. 'gpu_lidar' vs 'lidar'); custom types need type=\"custom\".",
        )
    for pose_element in _children(sensor_element, "pose"):
        _validate_pose(pose_element, result, f"{path}/pose", targets)
    update_rate = _optional_number_child(sensor_element, "update_rate", result, f"{path}/update_rate")
    if update_rate is not None and update_rate < 0:
        result.add("error", "invalid_sensor_update_rate", "sensor update_rate must be non-negative", path=f"{path}/update_rate")


def _validate_plugin(plugin_element: ET.Element, result: ValidationResult, plugin_path: str) -> None:
    filename = str(plugin_element.attrib.get("filename") or "").strip()
    if not filename:
        result.add("error", "missing_plugin_filename", "plugin filename is required", path=plugin_path)
    if "name" in plugin_element.attrib and not str(plugin_element.attrib.get("name") or "").strip():
        result.add("error", "missing_plugin_name", "plugin name is empty", path=plugin_path)
    elif "name" not in plugin_element.attrib:
        result.add("warning", "missing_plugin_name", "plugin name is omitted", path=plugin_path)


def _validate_include(include_element: ET.Element, result: ValidationResult, include_path: str) -> None:
    _required_child_text(include_element, "uri", result, f"{include_path}/uri", "include uri")


def _validate_pose(
    pose_element: ET.Element,
    result: ValidationResult,
    pose_path: str,
    targets: set[str],
    *,
    warn_missing_relative_to: bool = True,
) -> None:
    rotation_format = str(pose_element.attrib.get("rotation_format") or "euler_rpy").strip()
    if rotation_format == "euler_rpy":
        values = _parse_number_text(str(pose_element.text or ""), 6, result, pose_path, "pose")
    elif rotation_format == "quat_xyzw":
        values = _parse_number_text(str(pose_element.text or ""), 7, result, pose_path, "pose")
        if values is not None:
            quat = values[3:]
            norm = _norm(quat)
            if norm == 0:
                result.add("error", "zero_quaternion", "quaternion pose has zero norm", path=pose_path)
            elif abs(norm - 1.0) > UNIT_TOLERANCE:
                result.add("warning", "non_unit_quaternion", f"quaternion pose norm is {norm:.6g}, not 1", path=pose_path)
    else:
        result.add("error", "unsupported_rotation_format", f"unsupported pose rotation_format {rotation_format!r}", path=pose_path)
        values = None

    degrees = str(pose_element.attrib.get("degrees") or "").strip().lower()
    if degrees and degrees not in BOOLEAN_VALUES:
        result.add("error", "invalid_pose_degrees", "pose degrees attribute must be boolean-like", path=pose_path)
    elif degrees in TRUE_VALUES:
        result.add("warning", "pose_uses_degrees", "pose uses degrees=true; SDF defaults to radians", path=pose_path)

    relative_to = str(pose_element.attrib.get("relative_to") or "").strip()
    if warn_missing_relative_to and values is not None and _nontrivial_pose(values) and not relative_to:
        result.add(
            "warning",
            "pose_missing_relative_to",
            "nontrivial pose omits explicit relative_to",
            path=pose_path,
        )
    if relative_to:
        _check_reference(relative_to, result, pose_path, "relative_to", targets)


def _validate_frame_cycles(frames: list[ET.Element], result: ValidationResult, owner_path: str) -> None:
    frame_names = set(_names(frames))
    edges: dict[str, str] = {}
    for frame in frames:
        name = _name(frame)
        target = str(frame.attrib.get("attached_to") or "").strip()
        if not target:
            pose_element = _first_child(frame, "pose")
            target = str(pose_element.attrib.get("relative_to") or "").strip() if pose_element is not None else ""
        if name and target in frame_names:
            edges[name] = target

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(frame_name: str, stack: list[str]) -> None:
        if frame_name in visited:
            return
        if frame_name in visiting:
            cycle = " -> ".join([*stack, frame_name])
            result.add("error", "frame_cycle", f"frame graph contains a cycle: {cycle}", path=f"{owner_path}/frame")
            return
        visiting.add(frame_name)
        target = edges.get(frame_name)
        if target:
            visit(target, [*stack, frame_name])
        visiting.remove(frame_name)
        visited.add(frame_name)

    for frame_name in edges:
        visit(frame_name, [])


def _validate_mesh_uri(uri: str, result: ValidationResult, base_dir: Path, uri_path: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme in EXTERNAL_URI_SCHEMES:
        return
    if parsed.scheme and parsed.scheme != "file":
        result.add(
            "warning",
            "unresolved_mesh_uri_scheme",
            f"mesh URI scheme {parsed.scheme!r} is not resolved by bundled validation",
            path=uri_path,
        )
        return
    mesh_path = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else (base_dir / uri).resolve()
    if not mesh_path.is_file():
        result.add(
            "error",
            "missing_mesh_file",
            f"references missing mesh file: {uri!r}",
            path=uri_path,
        )


def _validate_link_reference(
    link_ref: str,
    result: ValidationResult,
    link_names: set[str],
    path: str,
    *,
    allow_world: bool,
) -> None:
    if link_ref == "world":
        if allow_world:
            return
        result.add("error", "invalid_joint_child", "joint child may not be world", path=path)
        return
    if "::" in link_ref:
        result.add(
            "warning",
            "scoped_link_reference_unchecked",
            f"scoped link reference {link_ref!r} was not fully resolved by bundled validation",
            path=path,
        )
        return
    if link_ref not in link_names:
        result.add("error", "missing_link_reference", f"references missing link {link_ref!r}", path=path)


def _check_reference(ref: str, result: ValidationResult, path: str, attr: str, targets: set[str]) -> None:
    if "::" in ref:
        if any(part == "" for part in ref.split("::")):
            result.add("error", "invalid_scoped_reference", f"{attr} has malformed scoped reference {ref!r}", path=path)
        else:
            result.add(
                "warning",
                "scoped_reference_unchecked",
                f"{attr} scoped reference {ref!r} was not fully resolved by bundled validation",
                path=path,
            )
        return
    if ref not in targets:
        result.add("error", "unresolved_reference", f"{attr} references unknown frame or link {ref!r}", path=path)


def _check_unique_named(elements: list[ET.Element], result: ValidationResult, scope_path: str, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for element in elements:
        name = _required_name(element, result, f"{scope_path}/{label}", label)
        if not name:
            continue
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        duplicate_text = ", ".join(repr(item) for item in sorted(duplicates))
        result.add(
            "error",
            "duplicate_names",
            f"{label} names contain duplicates {duplicate_text}",
            path=f"{scope_path}/{label}",
        )


def _validate_positive_vector_child(
    parent: ET.Element,
    tag: str,
    expected_len: int,
    result: ValidationResult,
    path: str,
    *,
    required: bool = True,
) -> list[float] | None:
    child = _first_child(parent, tag)
    if child is None:
        if required:
            result.add("error", "missing_numeric_vector", f"{tag} is required", path=path)
        return None
    values = _parse_number_text(str(child.text or ""), expected_len, result, path, tag)
    if values is None:
        return None
    for value in values:
        if value <= 0:
            result.add("error", "invalid_dimension", f"{tag} values must be positive", path=path)
            break
    return values


def _validate_positive_number_child(parent: ET.Element, tag: str, result: ValidationResult, path: str) -> float | None:
    value = _optional_number_child(parent, tag, result, path, required=True)
    if value is not None and value <= 0:
        result.add("error", "invalid_dimension", f"{tag} must be positive", path=path)
    return value


def _optional_number_child(
    parent: ET.Element,
    tag: str,
    result: ValidationResult,
    path: str,
    *,
    required: bool = False,
    allow_infinite: bool = False,
) -> float | None:
    child = _first_child(parent, tag)
    if child is None or str(child.text or "").strip() == "":
        if required:
            result.add("error", "missing_number", f"{tag} is required", path=path)
        return None
    return _parse_optional_number(str(child.text or ""), result, path, tag, required=required, allow_infinite=allow_infinite)


def _parse_optional_number(
    value: str,
    result: ValidationResult,
    path: str,
    label: str,
    *,
    required: bool = False,
    allow_infinite: bool = False,
) -> float | None:
    value = str(value or "").strip()
    if not value:
        if required:
            result.add("error", "missing_number", f"{label} is required", path=path)
        return None
    try:
        number = float(value)
    except ValueError:
        result.add("error", "invalid_number", f"{label} must be numeric", path=path)
        return None
    if allow_infinite:
        if math.isnan(number):
            result.add("error", "invalid_number", f"{label} must not be NaN", path=path)
            return None
    elif not math.isfinite(number):
        result.add("error", "invalid_number", f"{label} must be finite", path=path)
        return None
    return number


def _parse_number_text(
    text: str,
    expected_len: int,
    result: ValidationResult,
    path: str,
    label: str,
) -> list[float] | None:
    parts = str(text or "").split()
    if len(parts) != expected_len:
        result.add("error", "invalid_numeric_vector", f"{label} must contain {expected_len} numeric values", path=path)
        return None
    values: list[float] = []
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            result.add("error", "invalid_number", f"{label} contains a non-numeric value {part!r}", path=path)
            return None
        if not math.isfinite(value):
            result.add("error", "invalid_number", f"{label} values must be finite", path=path)
            return None
        values.append(value)
    return values


def _validate_boolean_text(element: ET.Element, result: ValidationResult, path: str, label: str) -> None:
    value = str(element.text or "").strip().lower()
    if value and value not in BOOLEAN_VALUES:
        result.add("error", "invalid_boolean", f"{label} must be boolean-like", path=path)


def _required_name(element: ET.Element, result: ValidationResult, path: str, label: str) -> str:
    name = _name(element)
    if not name:
        result.add("error", "missing_name", f"{label} name is required", path=path)
    return name


def _required_child_text(
    parent: ET.Element,
    tag: str,
    result: ValidationResult,
    path: str,
    label: str,
) -> str:
    value = _child_text(parent, tag)
    if not value:
        result.add("error", "missing_child_text", f"{label} is required", path=path)
    return value


def _joint_child_links(joints: list[ET.Element]) -> set[str]:
    return {_child_text(joint, "child") for joint in joints if _child_text(joint, "child") and "::" not in _child_text(joint, "child")}


def _joint_parent_links(joints: list[ET.Element]) -> set[str]:
    return {_child_text(joint, "parent") for joint in joints if _child_text(joint, "parent") and "::" not in _child_text(joint, "parent")}


def _model_is_static(model_element: ET.Element) -> bool:
    value = _child_text(model_element, "static").lower()
    return value in TRUE_VALUES


def _inertia_is_psd(values: dict[str, float]) -> bool:
    ixx = values["ixx"]
    iyy = values["iyy"]
    izz = values["izz"]
    ixy = values["ixy"]
    ixz = values["ixz"]
    iyz = values["iyz"]
    minor_xy = (ixx * iyy) - (ixy * ixy)
    minor_xz = (ixx * izz) - (ixz * ixz)
    minor_yz = (iyy * izz) - (iyz * iyz)
    det = (ixx * iyy * izz) + (2 * ixy * ixz * iyz) - (ixx * iyz * iyz) - (iyy * ixz * ixz) - (izz * ixy * ixy)
    return (
        ixx >= -PSD_TOLERANCE
        and iyy >= -PSD_TOLERANCE
        and izz >= -PSD_TOLERANCE
        and minor_xy >= -PSD_TOLERANCE
        and minor_xz >= -PSD_TOLERANCE
        and minor_yz >= -PSD_TOLERANCE
        and det >= -PSD_TOLERANCE
    )


def _nontrivial_pose(values: list[float]) -> bool:
    return any(abs(value) > POSE_TOLERANCE for value in values)


def _norm(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _children(parent: ET.Element, tag_name: str) -> list[ET.Element]:
    return [child for child in list(parent) if _local_name(child.tag) == tag_name]


def _first_child(parent: ET.Element, tag_name: str) -> ET.Element | None:
    return next(iter(_children(parent, tag_name)), None)


def _child_text(parent: ET.Element, tag_name: str) -> str:
    child = _first_child(parent, tag_name)
    return str(child.text if child is not None else "").strip()


def _name(element: ET.Element) -> str:
    return str(element.attrib.get("name") or "").strip()


def _names(elements: list[ET.Element]) -> list[str]:
    return [_name(element) for element in elements if _name(element)]


def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _path(tag: str, element: ET.Element, *, fallback: str | None = None) -> str:
    name = _name(element)
    if name:
        return f"/sdf/{tag}[@name='{name}']"
    return fallback or f"/sdf/{tag}"


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_light(light_element: ET.Element, result: ValidationResult, targets: set[str], owner_path: str) -> None:
    light_name = _required_name(light_element, result, f"{owner_path}/light", "light")
    light_path = f"{owner_path}/light[@name='{light_name}']" if light_name else f"{owner_path}/light"
    light_type = str(light_element.attrib.get("type") or "").strip()
    if not light_type:
        result.add("error", "missing_light_type", "light type is required", path=light_path)
    elif light_type not in LIGHT_TYPES:
        result.add(
            "error",
            "unknown_light_type",
            f"light type {light_type!r} must be one of: " + ", ".join(sorted(LIGHT_TYPES)),
            path=light_path,
        )
    for pose_element in _children(light_element, "pose"):
        _validate_pose(pose_element, result, f"{light_path}/pose", targets)


def _validate_mesh_scale_child(shape: ET.Element, result: ValidationResult, scale_path: str) -> None:
    scale_element = _first_child(shape, "scale")
    if scale_element is None:
        return
    values = _parse_number_text(str(scale_element.text or ""), 3, result, scale_path, "mesh scale")
    if values is None:
        return
    if any(value == 0.0 for value in values):
        result.add("error", "zero_mesh_scale", "mesh scale values must be nonzero", path=scale_path)
        return
    if any(value < 0.0 for value in values):
        result.add(
            "warning",
            "negative_mesh_scale",
            "mesh uses negative scale (mirroring); consumer support varies and triangle winding flips",
            path=scale_path,
        )


def _check_cross_type_scope_names(
    result: ValidationResult,
    scope_path: str,
    **names_by_kind: set[str],
) -> None:
    # SDFormat frame-graph names (links, joints, frames, nested models) share
    # one namespace per scope; libsdformat rejects cross-type collisions.
    kinds = sorted(names_by_kind)
    for index, first_kind in enumerate(kinds):
        for second_kind in kinds[index + 1:]:
            shared = sorted(names_by_kind[first_kind] & names_by_kind[second_kind])
            if shared:
                result.add(
                    "error",
                    "cross_type_name_collision",
                    f"{first_kind} and {second_kind} names collide in the same scope: {shared!r}",
                    path=scope_path,
                )


def _warn_unknown_children(
    element: ET.Element,
    known_children: set[str],
    result: ValidationResult,
    path: str,
) -> None:
    for child in list(element):
        if not isinstance(child.tag, str):
            continue  # comments / processing instructions
        tag = _local_name(child.tag)
        if tag != child.tag:
            continue  # namespaced extensions pass through
        if tag not in known_children:
            result.add(
                "warning",
                "unknown_element",
                f"unknown element <{tag}> under {path}",
                path=f"{path}/{tag}",
                hint=_UNKNOWN_ELEMENT_HINT,
            )


def _symmetric_inertia_eigenvalues(values: dict[str, float]) -> tuple[float, float, float]:
    """Closed-form eigenvalues of the symmetric 3x3 inertia tensor."""
    ixx, iyy, izz = values["ixx"], values["iyy"], values["izz"]
    ixy, ixz, iyz = values["ixy"], values["ixz"], values["iyz"]
    p1 = ixy * ixy + ixz * ixz + iyz * iyz
    if p1 == 0.0:
        return ixx, iyy, izz
    q = (ixx + iyy + izz) / 3.0
    p2 = (ixx - q) ** 2 + (iyy - q) ** 2 + (izz - q) ** 2 + 2.0 * p1
    p = math.sqrt(p2 / 6.0)
    if p == 0.0:
        return q, q, q
    b_xx, b_yy, b_zz = (ixx - q) / p, (iyy - q) / p, (izz - q) / p
    b_xy, b_xz, b_yz = ixy / p, ixz / p, iyz / p
    det_b = (
        b_xx * (b_yy * b_zz - b_yz * b_yz)
        - b_xy * (b_xy * b_zz - b_yz * b_xz)
        + b_xz * (b_xy * b_yz - b_yy * b_xz)
    )
    r = max(-1.0, min(1.0, det_b / 2.0))
    phi = math.acos(r) / 3.0
    eig1 = q + 2.0 * p * math.cos(phi)
    eig3 = q + 2.0 * p * math.cos(phi + (2.0 * math.pi / 3.0))
    eig2 = 3.0 * q - eig1 - eig3
    return eig1, eig2, eig3
