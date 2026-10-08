from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from cadgen.sdf_validation import raise_for_validation_errors, validate_sdf_root
from cadgen.xml_common import duplicate_values, children, display_path, local_name

SDF_SUFFIX = ".sdf"
EXTERNAL_URI_SCHEMES = {"model", "package", "http", "https", "fuel"}


class SdfSourceError(ValueError):
    pass


@dataclass(frozen=True)
class SdfJoint:
    name: str
    joint_type: str
    parent_link: str
    child_link: str
    # Native SDF units from <axis><limit>: radians for revolute, meters for
    # prismatic. None for joints that have no position limits (continuous, fixed)
    # or that declare none.
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class SdfSource:
    file_ref: str
    source_path: Path
    version: str
    model_names: tuple[str, ...]
    world_names: tuple[str, ...]
    links: tuple[str, ...]
    joints: tuple[SdfJoint, ...]
    mesh_paths: tuple[Path, ...]
    visual_mesh_paths: tuple[Path, ...] = ()
    collision_mesh_paths: tuple[Path, ...] = ()


def file_ref_from_sdf_path(sdf_path: Path) -> str:
    resolved = sdf_path.resolve()
    if resolved.suffix.lower() != SDF_SUFFIX:
        raise SdfSourceError(f"{resolved} is not an SDF source file")
    return display_path(resolved)


def read_sdf_source(sdf_path: Path) -> SdfSource:
    resolved_path = sdf_path.resolve()
    if resolved_path.suffix.lower() != SDF_SUFFIX:
        raise SdfSourceError(f"{resolved_path} is not an SDF source file")

    try:
        root = ET.fromstring(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise SdfSourceError(f"{display_path(resolved_path)} could not be parsed as SDF XML") from exc
    return parse_sdf_root(root, source_path=resolved_path, base_dir=resolved_path.parent)


def parse_sdf_xml(xml_text: str, *, source_path: Path, base_dir: Path | None = None) -> SdfSource:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SdfSourceError(f"{display_path(source_path)} could not be parsed as SDF XML") from exc
    return parse_sdf_root(root, source_path=source_path, base_dir=base_dir)


def parse_sdf_root(root: ET.Element, *, source_path: Path, base_dir: Path | None = None) -> SdfSource:
    resolved_path = source_path.resolve()
    resolved_base_dir = Path(base_dir).resolve() if base_dir is not None else resolved_path.parent
    validation = validate_sdf_root(root, source_path=resolved_path, base_dir=resolved_base_dir)
    raise_for_validation_errors(validation)

    if local_name(root.tag) != "sdf":
        raise SdfSourceError(f"{display_path(resolved_path)} root element must be <sdf>")
    version = str(root.attrib.get("version") or "").strip()
    if not version:
        raise SdfSourceError(f"{display_path(resolved_path)} SDF version is required")

    world_elements = children(root, "world")
    world_names = [_required_name(world, source_path=resolved_path, label="world") for world in world_elements]
    _raise_on_duplicates(world_names, source_path=resolved_path, label="world")

    model_elements = list(children(root, "model"))
    for world in world_elements:
        model_elements.extend(children(world, "model"))

    model_names: list[str] = []
    links: list[str] = []
    joints: list[SdfJoint] = []
    visual_mesh_paths: list[Path] = []
    collision_mesh_paths: list[Path] = []

    for model_element in model_elements:
        model_name = _required_name(model_element, source_path=resolved_path, label="model")
        model_names.append(model_name)
        model_links, model_joints, model_visual_meshes, model_collision_meshes = _read_model(
            model_element,
            source_path=resolved_path,
            base_dir=resolved_base_dir,
            model_name=model_name,
        )
        links.extend(model_links)
        joints.extend(model_joints)
        visual_mesh_paths.extend(model_visual_meshes)
        collision_mesh_paths.extend(model_collision_meshes)

    return SdfSource(
        file_ref=file_ref_from_sdf_path(resolved_path),
        source_path=resolved_path,
        version=version,
        model_names=tuple(model_names),
        world_names=tuple(world_names),
        links=tuple(links),
        joints=tuple(joints),
        mesh_paths=tuple(visual_mesh_paths + collision_mesh_paths),
        visual_mesh_paths=tuple(visual_mesh_paths),
        collision_mesh_paths=tuple(collision_mesh_paths),
    )


def _read_model(
    model_element: ET.Element,
    *,
    source_path: Path,
    base_dir: Path,
    model_name: str,
) -> tuple[list[str], list[SdfJoint], list[Path], list[Path]]:
    link_names = [
        _required_name(link_element, source_path=source_path, label=f"model {model_name!r} link")
        for link_element in children(model_element, "link")
    ]
    _raise_on_duplicates(link_names, source_path=source_path, label=f"model {model_name!r} link")
    link_name_set = set(link_names)

    visual_mesh_paths: list[Path] = []
    collision_mesh_paths: list[Path] = []
    for link_element in children(model_element, "link"):
        visual_mesh_paths.extend(
            _geometry_mesh_paths(
                link_element,
                element_name="visual",
                source_path=source_path,
                base_dir=base_dir,
            )
        )
        collision_mesh_paths.extend(
            _geometry_mesh_paths(
                link_element,
                element_name="collision",
                source_path=source_path,
                base_dir=base_dir,
            )
        )

    joint_names: list[str] = []
    joints: list[SdfJoint] = []
    for joint_element in children(model_element, "joint"):
        joint_name = _required_name(joint_element, source_path=source_path, label=f"model {model_name!r} joint")
        joint_names.append(joint_name)
        joint_type = str(joint_element.attrib.get("type") or "").strip()
        if not joint_type:
            raise SdfSourceError(
                f"{display_path(source_path)} model {model_name!r} joint {joint_name!r} type is required"
            )
        parent_link = _required_child_text(
            joint_element,
            "parent",
            source_path=source_path,
            label=f"model {model_name!r} joint {joint_name!r} parent",
        )
        child_link = _required_child_text(
            joint_element,
            "child",
            source_path=source_path,
            label=f"model {model_name!r} joint {joint_name!r} child",
        )
        _validate_link_reference(
            parent_link,
            link_names=link_name_set,
            source_path=source_path,
            context=f"model {model_name!r} joint {joint_name!r} parent",
        )
        _validate_link_reference(
            child_link,
            link_names=link_name_set,
            source_path=source_path,
            context=f"model {model_name!r} joint {joint_name!r} child",
            allow_world=False,
        )
        lower, upper = _joint_position_limits(joint_element, joint_type)
        joints.append(
            SdfJoint(
                name=joint_name,
                joint_type=joint_type,
                parent_link=parent_link,
                child_link=child_link,
                lower=lower,
                upper=upper,
            )
        )
    _raise_on_duplicates(joint_names, source_path=source_path, label=f"model {model_name!r} joint")

    return link_names, joints, visual_mesh_paths, collision_mesh_paths


def _joint_position_limits(joint_element: ET.Element, joint_type: str) -> tuple[float | None, float | None]:
    if joint_type not in ("revolute", "prismatic"):
        return None, None
    for axis_element in children(joint_element, "axis"):
        for limit_element in children(axis_element, "limit"):
            bounds = [children(limit_element, tag) for tag in ("lower", "upper")]
            if not all(bounds):
                return None, None
            try:
                return float(str(bounds[0][0].text).strip()), float(str(bounds[1][0].text).strip())
            except ValueError:
                return None, None
    return None, None


def _required_name(element: ET.Element, *, source_path: Path, label: str) -> str:
    name = str(element.attrib.get("name") or "").strip()
    if not name:
        raise SdfSourceError(f"{display_path(source_path)} {label} name is required")
    return name


def _required_child_text(
    parent: ET.Element,
    tag_name: str,
    *,
    source_path: Path,
    label: str,
) -> str:
    element = next(iter(children(parent, tag_name)), None)
    value = str(element.text if element is not None else "").strip()
    if not value:
        raise SdfSourceError(f"{display_path(source_path)} {label} is required")
    return value


def _validate_link_reference(
    link_ref: str,
    *,
    link_names: set[str],
    source_path: Path,
    context: str,
    allow_world: bool = True,
) -> None:
    if allow_world and link_ref == "world":
        return
    if "::" in link_ref:
        return
    if link_ref not in link_names:
        raise SdfSourceError(f"{display_path(source_path)} {context} references missing link {link_ref!r}")


def _geometry_mesh_paths(
    link_element: ET.Element,
    *,
    element_name: str,
    source_path: Path,
    base_dir: Path,
) -> list[Path]:
    mesh_paths: list[Path] = []
    for geometry_owner in children(link_element, element_name):
        geometry_element = next(iter(children(geometry_owner, "geometry")), None)
        if geometry_element is None:
            continue
        mesh_element = next(iter(children(geometry_element, "mesh")), None)
        if mesh_element is None:
            continue
        uri = _required_child_text(
            mesh_element,
            "uri",
            source_path=source_path,
            label=f"{element_name} mesh uri",
        )
        mesh_path = _resolve_local_mesh_uri(uri, base_dir=base_dir)
        if mesh_path is not None:
            if not mesh_path.is_file():
                raise SdfSourceError(
                    f"{display_path(source_path)} references missing mesh file: {uri!r}"
                )
            mesh_paths.append(mesh_path)
    return mesh_paths


def _resolve_local_mesh_uri(uri: str, *, base_dir: Path) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme in EXTERNAL_URI_SCHEMES:
        return None
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).resolve()
    return (base_dir / uri).resolve()


def _raise_on_duplicates(values: list[str], *, source_path: Path, label: str) -> None:
    duplicates = duplicate_values(values)
    if duplicates:
        duplicate_text = ", ".join(repr(item) for item in duplicates)
        raise SdfSourceError(
            f"{display_path(source_path)} {label} names contain duplicates {duplicate_text}"
        )


