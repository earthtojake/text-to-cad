"""A URDF read into a robot's articulation (``robot_model``), and an SRDF's group states over the
URDF it plans for: what the stills (``formats/robot.py``) and the viewer's payload (the server's
``robot_payload``) each take a view of. In the engine, as ``mjcf_source`` is, because every reader of a
URDF reads it here; the standard library alone (``tests/python/global/test_robot_modules_stdlib_pure.py``).
The type's own check is the validation family's (``cad.urdf._source``), which the payload runs first.

**What is read**: the links and each one's visuals -- origin, a ``<mesh filename scale>`` resolved to
its file (``mesh_uri``: a path relative to the description, an absolute one, ``file:``, or
``package://`` in the ROS package the description is in; None where it names no local file), or a
box, cylinder or sphere in full sizes, a colour from the ``<material>``'s inline ``rgba`` or the
robot's material of its name -- and the joints (fixed, revolute, continuous, prismatic: origin, axis,
limits, ``<mimic>``, and the urdf skill's ``<tcad:four_bar>`` as written: the payload samples it into a
curve, the stills solve it). The links must form one tree; each frame is placed at rest in the
robot's space (every joint at zero), each joint's axis turned into it and made a unit vector. With
the dialect's ``facts``, what the description writes -- each visual's and collision's geometry,
origin and material, each link's inertial, each joint's origin, axis, limit -- is read as written.
What a consumer cannot draw (a mesh in a format it has no decoder for, one no file is at) is the
consumer's to refuse; this reads what the file says.

**An SRDF** (``read_srdf``) is the URDF it plans for -- the same-folder ``.urdf`` whose ``<robot
name>`` is its own, exactly one, unless the caller names it -- with its group states as poses
(``group/name``, each moving joint's value in degrees or metres; a mimic, which no state sets, left
out, and a four-bar's crank left for its consumer to leave out) and its ``home`` states the opening.
"""

from __future__ import annotations

import math
import os
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

from cad.engine import mesh_uri
from cad.engine.robot_model import (ANGULAR, IDENTITY, MOVING, Articulation, Dialect, LinkJoint, Visual, children,
                                    described_origin, first, hex_color, local_name, multiply, numbers,
                                    optional_number, optional_numbers, parse, pose, rotate, unit)

__all__ = ["FOUR_BAR_LENGTHS", "FOUR_BAR_ZEROS", "TCAD_NAMESPACE", "mesh_file", "read_srdf", "read_urdf", "tree_root"]

#: The urdf skill's namespace, whose ``<four_bar>`` on a joint makes it a four-bar linkage's crank.
TCAD_NAMESPACE = "https://text-to-cad.dev/urdf"
FOUR_BAR_LENGTHS = ("input_length", "ground_length", "output_length", "coupler_length")
FOUR_BAR_ZEROS = ("input_zero", "output_zero")
_INERTIA = ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")


def mesh_file(reference: str, base: Path, where: str) -> Path | None:
    """The file a mesh reference names, for a description in ``base``: a ``package://`` one in its ROS
    package (``mesh_uri.package_file``), any other local one beside the description; None where it
    names no local file, or a package no folder above the description is (``mesh_uri.package_file``
    says which, by name, to a consumer that refuses it)."""
    if mesh_uri.scheme(reference) == "package":
        try:
            return mesh_uri.package_file(reference, base, where)
        except mesh_uri.PackageError:
            return None
    local = mesh_uri.local_path(reference)  # a drive path is a path; file:///C:/x is C:\x on Windows
    return None if local is None else (Path(base) / local).resolve()


def _origin(element: ET.Element | None, where: str, dialect: Dialect) -> list[list[float]]:
    if element is None:
        return IDENTITY
    return pose(numbers(element.get("xyz"), 3, f"{where} origin xyz", dialect, default=[0.0, 0.0, 0.0]),
                numbers(element.get("rpy"), 3, f"{where} origin rpy", dialect, default=[0.0, 0.0, 0.0]))


def _origin_facts(element: ET.Element | None) -> dict[str, list[float]]:
    return described_origin(optional_numbers(element.get("xyz") if element is not None else None, 3),
                            optional_numbers(element.get("rpy") if element is not None else None, 3))


def _geometry_facts(geometry: ET.Element | None) -> dict[str, Any]:
    mesh = first(geometry, "mesh")
    if mesh is not None:
        return {"type": "mesh", "filename": str(mesh.get("filename") or "").strip(),
                "scale": optional_numbers(mesh.get("scale"), 3)}
    for shape in ("box", "cylinder", "sphere"):
        element = first(geometry, shape)
        if element is not None:
            facts: dict[str, Any] = {"type": shape, "filename": ""}
            if shape == "box":
                facts["size"] = optional_numbers(element.get("size"), 3)
            else:
                facts["radius"] = optional_number(element, "radius")
                if shape == "cylinder":
                    facts["length"] = optional_number(element, "length")
            return facts
    return {"type": "unknown", "filename": ""}


def _shape_facts(element: ET.Element) -> dict[str, Any]:
    """A visual's or a collision's name, geometry and origin as written."""
    return {"name": str(element.get("name") or "").strip(), **_geometry_facts(first(element, "geometry")),
            "origin": _origin_facts(first(element, "origin"))}


def _shape(geometry: ET.Element | None, base: Path, where: str, dialect: Dialect) -> tuple[tuple, str]:
    """A visual's shape (``robot_model``'s) and its mesh reference as written ("" for a primitive);
    ``("unknown",)`` for geometry that is none of a mesh, box, cylinder or sphere."""
    mesh = first(geometry, "mesh")
    if mesh is not None:
        filename = str(mesh.get("filename") or "").strip()
        scale = numbers(mesh.get("scale"), 3, f"{where} mesh scale", dialect, default=[1.0, 1.0, 1.0])
        return ("file", mesh_file(filename, base, where) if filename else None, scale), filename
    box = first(geometry, "box")
    if box is not None:
        return ("box", {"size": numbers(box.get("size"), 3, f"{where} box size", dialect)}), ""
    cylinder = first(geometry, "cylinder")
    if cylinder is not None:
        dimensions = {key: optional_number(cylinder, key) for key in ("radius", "length")}
        return ("cylinder", {key: value for key, value in dimensions.items() if value is not None}), ""
    sphere = first(geometry, "sphere")
    if sphere is not None:
        radius = optional_number(sphere, "radius")
        return ("sphere", {} if radius is None else {"radius": radius}), ""
    return ("unknown",), ""


def _label(name: str, shape: tuple, reference: str) -> str:
    """What a row calls a visual: the name it was given, else its mesh file's, else its shape."""
    if name:
        return name
    if shape[0] == "file":
        return shape[1].name if shape[1] is not None else PurePosixPath(reference).name or "mesh"
    return shape[0]


def _four_bar(joint: ET.Element, name: str, file: str, dialect: Dialect) -> dict[str, Any] | None:
    """The joint's ``<tcad:four_bar>`` (an element named ``four_bar`` in any namespace; ``namespace``
    says which): its driver, lengths and zero angles."""
    elements = [child for child in joint if local_name(child.tag) == "four_bar"]
    if not elements:
        return None
    if len(elements) > 1 and dialect.refuses("four_bar_many"):
        raise dialect.error("four_bar_many", file=file, joint=name)
    tagged = [element for element in elements if element.tag == f"{{{TCAD_NAMESPACE}}}four_bar"]
    element = (tagged or elements)[0]
    found: dict[str, Any] = {"joint": name, "driver": str(element.get("driver") or "").strip(),
                             "namespace": element.tag[1:].split("}", 1)[0] if element.tag.startswith("{") else ""}
    for key in (*FOUR_BAR_LENGTHS, *FOUR_BAR_ZEROS):
        try:
            value: float | None = float(element.get(key))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = None
        if value is None and dialect.refuses("four_bar_number"):
            raise dialect.error("four_bar_number", file=file, joint=name, key=key)
        if value is None or (not math.isfinite(value) and not dialect.refuses("four_bar_number")):
            value = 0.0
        found[key] = value
    if (not found["driver"] or any(found[key] <= 0 for key in FOUR_BAR_LENGTHS)) and dialect.refuses("four_bar_lengths"):
        raise dialect.error("four_bar_lengths", file=file, joint=name)
    return found


def tree_root(file: str, links: list[str], joints: list[Any], dialect: Dialect) -> str:
    """The root link of a tree of ``links`` joined by ``joints`` (each with a ``parent`` and a ``child``),
    refused by name when they are not one."""
    children_of: set[str] = set()
    for joint in joints:
        if joint.child in children_of:
            raise dialect.error("tree_parents", file=file, link=joint.child)
        children_of.add(joint.child)
    roots = [link for link in links if link not in children_of]
    if len(roots) != 1:
        raise dialect.error("tree_roots", file=file, roots=", ".join(roots) or "none")
    reached: set[str] = set()
    pending = [roots[0]]
    by_parent: dict[str, list[str]] = {}
    for joint in joints:
        by_parent.setdefault(joint.parent, []).append(joint.child)
    while pending:
        link = pending.pop()
        if link in reached:
            raise dialect.error("tree_cycle", file=file, link=link)
        reached.add(link)
        pending.extend(by_parent.get(link, ()))
    if len(reached) != len(links):
        raise dialect.error("tree_loose", file=file, links=", ".join(sorted(set(links) - reached)))
    return roots[0]


def read_urdf(path: Path, dialect: Dialect | None = None) -> Articulation:
    """``path`` read as a URDF into its articulation at rest, or refused by name (``SourceError``)."""
    dialect = dialect or Dialect()
    path = Path(path)
    file, base = dialect.display(path), path.parent
    root = parse(path, dialect)
    if local_name(root.tag) != "robot":
        raise dialect.error("urdf_root", file=file)
    named: dict[str, tuple[float, ...]] = {}
    for material in children(root, "material"):
        name = str(material.get("name") or "").strip()
        colour = first(material, "color")
        if name and colour is not None and colour.get("rgba"):
            rgba = numbers(colour.get("rgba"), 4, f"{file} material", dialect, code="rgba")
            if rgba is not None:
                named[name] = tuple(rgba)
    links: dict[str, list[list[float]]] = {}
    visuals: dict[str, list[Visual]] = {}
    collisions: dict[str, list[dict[str, Any]]] = {}
    inertials: dict[str, dict[str, Any]] = {}
    for link in children(root, "link"):
        link_name = str(link.get("name") or "").strip()
        if not link_name or link_name in links:
            raise dialect.error("link_name", file=file, name=link_name)
        links[link_name] = IDENTITY
        visuals[link_name] = []
        for index, element in enumerate(children(link, "visual"), 1):
            where = f"{file} link {link_name!r} visual {index}"
            shape, reference = _shape(first(element, "geometry"), base, where, dialect)
            material = first(element, "material")
            material_name, rgba = "", None
            if material is not None:
                material_name = str(material.get("name") or "").strip()
                inline = first(material, "color")
                if inline is not None and inline.get("rgba"):
                    found = numbers(inline.get("rgba"), 4, f"{where} material", dialect, code="rgba")
                    rgba = tuple(found) if found is not None else None
                if rgba is None:
                    rgba = named.get(material_name)
            color = hex_color(rgba) if rgba is not None else ""
            facts = None
            if dialect.facts:
                facts = {**_shape_facts(element), "color": color, "materialName": material_name}
                if shape[0] == "file" and shape[1] is not None:
                    facts["path"] = str(shape[1])
            name = str(element.get("name") or "").strip()
            visuals[link_name].append(Visual(f"{link_name}:v{index}", link_name, _origin(first(element, "origin"), where, dialect),
                                             shape, color, 1.0 if rgba is None else rgba[3], _label(name, shape, reference),
                                             reference=reference, rgba=rgba, facts=facts))
        if dialect.facts:
            collisions[link_name] = [_shape_facts(element) for element in children(link, "collision")]
            inertial = first(link, "inertial")
            if inertial is not None:
                inertia_element = first(inertial, "inertia")
                inertia = {key: optional_number(inertia_element, key) for key in _INERTIA}
                inertials[link_name] = {
                    "mass": optional_number(first(inertial, "mass"), "value"),
                    "origin": _origin_facts(first(inertial, "origin")),
                    "inertia": inertia if all(value is not None for value in inertia.values()) else None,
                }
    joints: list[LinkJoint] = []
    origins: list[tuple[list[list[float]], list[float] | None]] = []
    for element in children(root, "joint"):
        name = str(element.get("name") or "").strip()
        where = f"{file} joint {name!r}"
        kind = str(element.get("type") or "").strip().lower()
        if kind not in (*MOVING, "fixed"):
            raise dialect.error("urdf_joint_type", file=file, joint=name, kind=kind or "typeless")
        parent, child = (str(getattr(first(element, tag), "attrib", {}).get("link") or "").strip()
                         for tag in ("parent", "child"))
        if parent not in links or child not in links:
            raise dialect.error("joint_links", file=file, joint=name, parent=parent, child=child)
        joint = LinkJoint(name, kind, parent, child, IDENTITY, None, None, None)
        origin = _origin(first(element, "origin"), where, dialect)
        axis_element = first(element, "axis")
        axis = None
        if kind != "fixed":
            axis = numbers(axis_element.get("xyz") if axis_element is not None else None, 3, f"{where} axis", dialect,
                           default=[1.0, 0.0, 0.0])
            if axis is None or unit(axis) is None:
                raise dialect.error("axis_zero", file=file, joint=name)
        limit = first(element, "limit")
        if kind in ("revolute", "prismatic"):
            if limit is None:
                raise dialect.error("limit_missing", file=file, joint=name, kind=kind)
            joint.lower, joint.upper = (numbers(limit.get(key), 1, f"{where} limit {key}", dialect)[0]  # type: ignore[index]
                                        for key in ("lower", "upper"))
        mimic = first(element, "mimic")
        if mimic is not None:
            multiplier, offset = optional_number(mimic, "multiplier"), optional_number(mimic, "offset")
            joint.mimic = (str(mimic.get("joint") or "").strip(), 1.0 if multiplier is None else multiplier,
                           0.0 if offset is None else offset)
        joint.four_bar = _four_bar(element, name, file, dialect)
        if dialect.facts:
            limits = {key: optional_number(limit, key) for key in ("lower", "upper", "effort", "velocity")}
            joint.facts = {
                "name": name, "type": kind, "parent": parent, "child": child,
                "axis": None if kind == "fixed" else list(axis or []),
                "origin": _origin_facts(first(element, "origin")),
                "limit": {key: value for key, value in limits.items() if value is not None} if limit is not None else None,
            }
        joints.append(joint)
        origins.append((origin, axis))
    root_link = tree_root(file, list(links), joints, dialect)
    # Each joint's frame and axis, and each link's frame, at rest in the robot's space: parents first.
    by_parent: dict[str, list[int]] = {}
    for index, joint in enumerate(joints):
        by_parent.setdefault(joint.parent, []).append(index)
    pending = [root_link]
    while pending:
        parent_name = pending.pop(0)
        for index in by_parent.get(parent_name, ()):
            joint = joints[index]
            origin, axis = origins[index]
            joint.frame = multiply(links[parent_name], origin)
            joint.axis = None if axis is None else unit(rotate(joint.frame, axis))
            links[joint.child] = joint.frame
            pending.append(joint.child)
    return Articulation(root_link, links, visuals, joints, {}, inertials, name=str(root.get("name") or "").strip(),
                        collisions=collisions, sources=[path])


def _robot_name(path: Path) -> str | None:
    """The ``<robot name>`` a URDF's first element gives, or None (not a robot, not readable)."""
    try:
        for _event, element in ET.iterparse(str(path), events=("start",)):
            return str(element.get("name") or "").strip() if local_name(element.tag) == "robot" else None
    except (OSError, ET.ParseError):
        return None
    return None


def read_srdf(path: Path, dialect: Dialect | None = None, *, urdf: Path | None = None) -> Articulation:
    """An SRDF over the URDF it plans for (``urdf``, else the one same-folder ``.urdf`` whose ``<robot
    name>`` is the SRDF's): the URDF's articulation with the SRDF's group states as its poses
    (``group/name``: each control's value in degrees or metres) and its ``home`` states the opening."""
    dialect = dialect or Dialect()
    path = Path(path)
    file = dialect.display(path)
    root = parse(path, dialect)
    name = str(root.get("name") or "").strip()
    rule = "an SRDF draws the same-folder .urdf whose <robot name> is its own, and exactly one may be"
    if local_name(root.tag) != "robot" or not name:
        raise dialect.error("srdf_name", file=file, rule=rule)
    if urdf is None:
        # Each file once: on a case-insensitive file system (Windows, macOS) both patterns find it.
        candidates = {os.path.normcase(str(found.resolve())): found
                      for found in sorted(path.parent.glob("*.urdf")) + sorted(path.parent.glob("*.URDF"))}
        matches = [candidate for candidate in candidates.values() if _robot_name(candidate) == name]
        if len(matches) != 1:
            raise dialect.error("srdf_pair", file=file, found="no" if not matches else len(matches), folder=path.parent,
                                name=name, rule=rule)
        urdf = matches[0]
    articulation = read_urdf(urdf, dialect)
    articulation.sources = [path, *articulation.sources]
    by_name = {joint.name: joint for joint in articulation.joints}
    for state in children(root, "group_state"):
        state_name = str(state.get("name") or "").strip()
        key = f"{str(state.get('group') or '').strip()}/{state_name}"
        values: dict[str, float] = {}
        for element in children(state, "joint"):
            joint_name = str(element.get("name") or "").strip()
            joint = by_name.get(joint_name)
            if joint is None or joint.type not in MOVING or joint.mimic is not None:
                continue
            value = numbers(element.get("value"), 1, f"{file} group state {key!r} joint {joint_name!r}", dialect)[0]  # type: ignore[index]
            values[joint_name] = math.degrees(value) if joint.type in ANGULAR else value
        articulation.poses[key] = values
        if state_name.lower() == "home":
            articulation.home.update(values)
    return articulation
